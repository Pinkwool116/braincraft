"""
Execution Layer

Handles code generation and execution for the agent.
Called as a tool by the Agent Loop Layer.

Responsibilities:
- Generate JavaScript code via Coding LLM
- Send code to Minecraft Bridge via IPC
- Wait for execution result
- Handle interruption
- Send chat messages
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ExecutionLayer:
    """
    Code generation and execution layer.

    Generates JavaScript code using a coding LLM, sends it to the
    Minecraft Bridge for execution, and returns the result.

    Called by Agent Loop tools — no internal loop or retry logic.
    """

    is_executing: bool = False

    def __init__(self, shared_state, ipc_server, exec_coordinator, config,
                 coding_llm, prompt_manager, memory_manager=None):
        """
        Initialize the Execution Layer.

        Args:
            shared_state: SharedState instance
            ipc_server: IPC server for communicating with JavaScript bridge
            exec_coordinator: ExecutionCoordinator for priority management
            config: Configuration dictionary
            coding_llm: LLM model for code generation
            prompt_manager: PromptManager for building coding prompts
            memory_manager: MemoryRouter instance (None in Phase 3)
        """
        self.shared_state = shared_state
        self.ipc_server = ipc_server
        self.exec_coordinator = exec_coordinator
        self.config = config
        self.coding_llm = coding_llm
        self.prompt_manager = prompt_manager
        self.memory_manager = memory_manager
        self.is_executing = False

        # Execution result timeout
        self.execution_timeout = config.get('execution', {}).get('timeout', 120)

        # Skill library for code validation (lazy init)
        self._skill_lib = None

        logger.info("ExecutionLayer initialized")

    @property
    def skill_lib(self):
        """Lazy-init SkillLibrary for code validation."""
        if self._skill_lib is None:
            from minecraft.skill_library import SkillLibrary
            self._skill_lib = SkillLibrary()
        return self._skill_lib

    async def execute_step(self, step_description: str) -> dict:
        """
        Generate code for a step and execute it.

        Flow: step_description → build coding prompt → Coding LLM → parse code → IPC execute → result

        No internal retry — Agent Loop decides whether to retry.

        Args:
            step_description: Natural language description of what to do

        Returns:
            {
                'success': bool,
                'code': str,          # Generated code
                'output': str,        # Execution output
                'error': str,         # Error message if failed
                'analysis': str,      # LLM's analysis
            }
        """
        self.is_executing = True
        await self.shared_state.update('is_executing', True)

        try:
            # 1. Build coding prompt (system prompt)
            system_prompt = await self._build_coding_prompt(step_description)

            # 2. Call Coding LLM
            messages = [{"role": "user", "content": f"执行步骤：{step_description}"}]
            response = await self.coding_llm.send_request(messages, system_prompt=system_prompt)

            if not response:
                return {
                    'success': False,
                    'code': '',
                    'output': '',
                    'error': 'LLM returned empty response',
                    'analysis': '',
                }

            # 3. Parse LLM response (extract analysis and code)
            analysis, code = self._parse_coding_response(response)

            if not code:
                return {
                    'success': False,
                    'code': '',
                    'output': '',
                    'error': f'LLM did not generate code. Response: {response[:200]}',
                    'analysis': analysis,
                }

            # 3.5. Validate generated code
            validation_error = self._validate_code(code)
            if validation_error:
                return {
                    'success': False,
                    'code': code,
                    'output': '',
                    'error': f'Code validation failed: {validation_error}',
                    'analysis': analysis,
                }

            # 3.6. Inject interrupt checks (bot.interrupt_code after every statement)
            code = self._inject_interrupt_checks(code)

            # 4. Execute code through ExecutionCoordinator
            result = await self.exec_coordinator.execute_action(
                layer='mid',
                label='execute_step',
                action_fn=lambda: self._execute_code(code),
                auto_resume=True
            )

            if result.get('blocked'):
                return {
                    'success': False,
                    'code': code,
                    'output': '',
                    'error': 'Execution blocked by higher priority action',
                    'analysis': analysis,
                }

            if result.get('cancelled'):
                return {
                    'success': False,
                    'code': code,
                    'output': '',
                    'error': 'Execution interrupted by higher priority action',
                    'analysis': analysis,
                }

            # 5. Extract execution result
            exec_result = result.get('result', {})
            return {
                'success': exec_result.get('success', False),
                'code': code,
                'output': exec_result.get('output', ''),
                'error': exec_result.get('error', ''),
                'analysis': analysis,
            }

        except asyncio.CancelledError:
            logger.warning("execute_step was cancelled")
            return {
                'success': False,
                'code': '',
                'output': '',
                'error': 'Execution cancelled',
                'analysis': '',
            }
        except Exception as e:
            logger.error(f"execute_step error: {e}", exc_info=True)
            return {
                'success': False,
                'code': '',
                'output': '',
                'error': str(e),
                'analysis': '',
            }
        finally:
            self.is_executing = False
            await self.shared_state.update('is_executing', False)

    async def send_chat(self, message: str) -> dict:
        """
        Send a chat message in game via IPC.

        Args:
            message: Chat message to send

        Returns:
            {'success': bool, 'message': str}
        """
        try:
            # Escape quotes for JS string
            escaped = message.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': f'bot.chat("{escaped}");',
                    'no_response': True
                }
            })
            logger.info(f"Chat sent: {message[:50]}")
            return {'success': True, 'message': message}
        except Exception as e:
            logger.error(f"send_chat error: {e}")
            return {'success': False, 'message': message, 'error': str(e)}

    async def interrupt(self) -> dict:
        """
        Interrupt the currently executing code.

        Sets interrupt_code flag in both Python shared_state and JavaScript.

        Returns:
            {'success': bool, 'was_executing': bool}
        """
        was_executing = self.is_executing

        if not was_executing:
            return {'success': True, 'was_executing': False}

        try:
            # Set interrupt flag (Python side)
            await self.shared_state.update('interrupt_code', True)

            # Set interrupt flag (JavaScript side)
            await self.ipc_server.send_command({
                'type': 'set_interrupt_flag',
                'data': {'value': True}
            })

            logger.info("Interrupt signal sent")

            # Wait briefly for JS to respond
            await asyncio.sleep(0.5)

            # Clear interrupt flag
            await self.shared_state.update('interrupt_code', False)
            await self.ipc_server.send_command({
                'type': 'set_interrupt_flag',
                'data': {'value': False}
            })

            self.is_executing = False
            await self.shared_state.update('is_executing', False)

            return {'success': True, 'was_executing': True}

        except Exception as e:
            logger.error(f"interrupt error: {e}")
            return {'success': False, 'was_executing': was_executing, 'error': str(e)}

    async def _build_coding_prompt(self, step_description: str) -> str:
        """
        Build the coding prompt for the LLM.

        Uses PromptManager to render execution_layer/coding.md with current context.
        The rendered result is used as system_prompt for the Coding LLM.

        Args:
            step_description: What the code should accomplish

        Returns:
            Complete coding prompt string (as system prompt)
        """
        # Get current game state for context
        state = await self.shared_state.get_all()

        # Build execution context (memory-enriched)
        execution_context = await self._build_execution_context(step_description)

        # Context for prompt variable resolution
        context = {
            'state': state,
            'agent_name': state.get('agent_name', 'BrainyBot'),
            'memory_manager': self.memory_manager,
            # Direct values (Special Direct Values per variable_config.yaml)
            'TASK': step_description,
            'EXECUTION_CONTEXT': execution_context,
            'EXAMPLES': '',  # TODO: Load code examples from file
        }

        return await self.prompt_manager.render(
            'execution_layer/coding.md',
            context=context,
            strict=False
        )

    async def _build_execution_context(self, step_description: str) -> str:
        """
        Build execution context with memory for the Coding LLM.

        Includes:
        1. Working memory: recent execution history
        2. Long-term memory: relevant code execution experience

        Args:
            step_description: Current step for memory retrieval

        Returns:
            Formatted execution context string
        """
        if not self.memory_manager:
            return "(无历史执行上下文)"

        parts = []
        try:
            # Working memory: recent operations
            if hasattr(self.memory_manager, 'working_memory') and self.memory_manager.working_memory.has_content:
                parts.append("### 近期操作记录\n" + self.memory_manager.working_memory.get_buffer_text())

            # Long-term memory: relevant experience
            if hasattr(self.memory_manager, 'retrieve_context_async'):
                relevant = await self.memory_manager.retrieve_context_async([step_description])
                if relevant:
                    parts.append("### 相关经验\n" + relevant)
        except Exception as e:
            logger.warning(f"Failed to build execution context: {e}")

        return "\n\n".join(parts) if parts else "(无历史执行上下文)"

    async def _execute_code(self, code: str) -> dict:
        """
        Send code to JavaScript for execution and wait for result.

        Args:
            code: JavaScript code to execute

        Returns:
            Execution result dict with 'success', 'output', 'error' keys
        """
        # Clear previous result
        await self.shared_state.update('last_execution_result', None)

        # Send code to JS bridge
        await self.ipc_server.send_command({
            'type': 'execute_code',
            'data': {'code': code}
        })

        # Poll for result
        start_time = asyncio.get_event_loop().time()
        poll_interval = 0.2

        while True:
            result = await self.shared_state.get('last_execution_result')
            if result is not None:
                return result

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.execution_timeout:
                logger.error(f"Code execution timeout after {self.execution_timeout}s")
                return {
                    'success': False,
                    'output': '',
                    'error': f'Execution timeout ({self.execution_timeout}s)'
                }

            # This sleep is a cancellation point for interrupt
            await asyncio.sleep(poll_interval)

    def _parse_coding_response(self, response: str) -> tuple:
        """
        Parse Coding LLM response to extract analysis and code.

        Expected JSON format: {"analysis": "...", "code": "..."}
        Also handles code in markdown code blocks as fallback.

        Args:
            response: Raw LLM response

        Returns:
            (analysis, code) tuple
        """
        text = response.strip()

        # Try JSON parse first
        try:
            # Strip markdown code fences if wrapping the entire response
            json_text = text
            if json_text.startswith('```'):
                json_text = re.sub(r'^```\w*\s*', '', json_text)
                json_text = re.sub(r'\s*```\s*$', '', json_text)
                json_text = json_text.strip()

            parsed = json.loads(json_text)
            analysis = parsed.get('analysis', '')
            code = parsed.get('code', '')
            return analysis, code
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                analysis = parsed.get('analysis', '')
                code = parsed.get('code', '')
                return analysis, code
            except json.JSONDecodeError:
                pass

        # Fallback: extract code from markdown code blocks
        code_match = re.search(r'```(?:javascript|js)?\s*\n?([\s\S]*?)\n?```', text)
        if code_match:
            code = code_match.group(1).strip()
            return '', code

        # Last resort: treat entire response as code if it looks like JS
        if 'await ' in text or 'bot.' in text or 'skills.' in text:
            return '', text

        logger.warning(f"Could not parse code from LLM response: {text[:200]}")
        return '', ''

    def _validate_code(self, code: str) -> Optional[str]:
        """
        Validate generated code for common issues.
        Ported from old MidLevelBrain._validate_code.

        Checks:
        - Forbidden patterns (setTimeout, console.log, require, import)
        - Reserved variable names (log)
        - skills/world function existence

        Args:
            code: JavaScript code to validate

        Returns:
            Error message string if invalid, None if valid
        """
        errors = []

        # Forbidden patterns
        forbidden_patterns = {
            'setTimeout': "Do not use setTimeout - use await skills.wait(bot, milliseconds) instead",
            'setInterval': "Do not use setInterval - use a while loop with await skills.wait() instead",
            'console.log': "Do not use console.log() - use log(bot, message) instead",
            'require(': "Do not use require() - all needed modules are already imported",
            'import ': "Do not use import statements - all needed modules are already imported",
        }

        for pattern, error_msg in forbidden_patterns.items():
            if pattern in code:
                errors.append(error_msg)

        # Check for reserved variable names
        if re.search(r'\b(let|const|var)\s+log\s*=', code):
            errors.append(
                "Do not use 'log' as a variable name - it's a reserved function. "
                "Use 'logBlock', 'oakLog', etc."
            )

        # Validate skills/world function calls exist
        skill_pattern = r'(?:skills|world)\.(\w+)\('
        matches = re.findall(skill_pattern, code)
        if matches:
            try:
                all_skills = self.skill_lib.get_all_skill_names()
                for func_name in matches:
                    if func_name not in all_skills:
                        errors.append(f"Function '{func_name}' does not exist in skills/world library")
            except Exception as e:
                logger.debug(f"Could not validate skill functions: {e}")

        if errors:
            return "\n".join(f"- {err}" for err in errors)
        return None

    def _inject_interrupt_checks(self, code: str) -> str:
        """
        Inject interrupt checks into generated code.
        Ported from old MidLevelBrain / original MindCraft coder.js.

        After every statement (`;\\n`), inserts a check:
            if(bot.interrupt_code) {log(bot, "Code interrupted.");return;}

        This allows real-time interruption from Python via the interrupt_code flag.

        Args:
            code: Original JavaScript code

        Returns:
            Code with interrupt checks injected after every statement
        """
        injected = code.replace(
            ';\n',
            '; if(bot.interrupt_code) {log(bot, "Code interrupted.");return;}\n'
        )
        # Also handle last statement if it ends with ;
        if injected.rstrip().endswith(';'):
            injected = injected.rstrip() + ' if(bot.interrupt_code) {log(bot, "Code interrupted.");return;}'

        return injected
