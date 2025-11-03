"""
Mid-Level Brain

Responsible for:
- Executing task steps from high-level brain's task plan
- Code generation and execution
- Reporting problems and requesting guidance when stuck
- Chat handling with interrupt support
- Learning from failures and successes
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import logging
from pathlib import Path
from utils.game_state_formatter import GameStateFormatter
from datetime import datetime
from utils.memory_manager import MemoryManager
from utils.chat_manager import ChatManager
from utils.prompt_loader import load_system_prompt

logger = logging.getLogger(__name__)

class MidLevelBrain:
    """
    Mid-level brain for tactical execution
    
    Core responsibilities:
    - Execute task steps from high-level brain's task plan (read from shared_state)
    - Generate JavaScript code to accomplish each step
    - Handle execution failures with retry mechanism
    - Request guidance from high-level brain when stuck (modification requests)
    - Handle chat messages with interrupt support
    - Learn from experiences and report to high-level brain
    
    Key features:
    - Priority-based processing (chat > guidance wait > task execution)
    - Interrupt support for chat messages
    - Smart failure detection and guidance requests
    - Background summarization (non-blocking)
    """
    
    def __init__(self, shared_state, ipc_server, config, llm_model, high_level_brain):
        """
        Initialize mid-level brain
        
        Args:
            shared_state: Shared state object
            ipc_server: IPC server for communication with JS
            config: Configuration object
            llm_model: Single LLM model instance (Qwen by default)
            high_level_brain: Reference to high-level brain
        """
        self.shared_state = shared_state
        self.ipc_server = ipc_server
        self.config = config
        self.llm = llm_model
        self.high_brain = high_level_brain
        
        # Memory manager for persistence
        agent_name = config.get('agent_name', 'BrainyBot')
        self.memory = MemoryManager(agent_name)
        
        # Chat manager for chat history persistence
        self.chat_manager = ChatManager(agent_name)
        
        # Skill library (create once and reuse)
        from models.skill_library import SkillLibrary
        self.skill_lib = SkillLibrary()
        
        # Execution state
        self.is_executing = False
        self.is_waiting_for_guidance = False  # Waiting for high-level response
        
        # Coordinator reference (set by coordinator after initialization)
        self.coordinator = None
        
        # Bot ready state tracking (to avoid spam)
        self._waiting_for_bot = False
        self._last_waiting_log_time = 0
        
        # Load system prompt (STRICT - exits on failure)
        self.system_prompt = load_system_prompt(config, 'mid_level_brain')
        
        # Configuration
        self.max_retries = config.get('mid_level_brain', {}).get('max_task_retries', 3)
        
        logger.info("Mid-level brain initialized (simplified version with single LLM)")
    
    async def process(self):
        """
        Main processing cycle for mid-level brain
        
        Called every second by the coordinator.
        
        Priority order:
        1. Check for chat messages (can interrupt execution)
        2. Check for guidance response from high-level (if waiting)
        3. Execute current task plan step
        """
        # Priority 1: Chat messages are now handled directly via _handle_pending_chat()
        # No need to check chat_queue here since brain_coordinator calls handler directly
        
        # Priority 2: Check for guidance response (if waiting)
        if self.is_waiting_for_guidance:
            mod_response = await self.shared_state.get('modification_response')
            if mod_response:
                await self._handle_guidance_response(mod_response)
                await self.shared_state.update('modification_response', None)
                self.is_waiting_for_guidance = False
            else:
                # Still waiting, don't execute tasks
                return
        
        # Priority 3: Execute current task plan step
        if not self.is_executing:
            await self._process_task_plan()
    
    async def _process_task_plan(self):
        """
        Process current task plan from high-level brain
        
        Reads task_plan from shared_state and executes current step.
        """
        # Get active task plan from shared state (managed by high-level brain)
        task_plan = await self.shared_state.get('active_task')
        
        if not task_plan or task_plan.get('status') != 'active':
            return
        
        current_step_index = task_plan.get('current_step_index', -1)
        steps = task_plan.get('steps', [])
        
        if current_step_index < 0 or current_step_index >= len(steps):
            return
        
        current_step = steps[current_step_index]
        step_status = current_step.get('status', 'pending')
        
        if step_status == 'completed':
            return
        
        # Check if bot is ready BEFORE logging execution
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            import time
            current_time = time.time()
            
            if not self._waiting_for_bot:
                logger.warning("Bot not in game yet - waiting for bot to spawn...")
                self._waiting_for_bot = True
                self._last_waiting_log_time = current_time
            elif current_time - self._last_waiting_log_time > 300:
                logger.info(f"Still waiting for bot to spawn...")
                self._last_waiting_log_time = current_time
            return
        
        if self._waiting_for_bot:
            logger.info("Bot spawned! Continuing task execution")
            self._waiting_for_bot = False
        
        # Log execution AFTER confirming bot is ready
        logger.info(f"Executing task plan step {current_step_index + 1}/{len(steps)}: {current_step['description']}")
        
        # Mark step as in_progress
        if step_status == 'pending':
            await self._update_step_status(current_step_index, 'in_progress')
        
        # Execute the step (similar to self-prompter loop)
        self.is_executing = True
        await self.shared_state.update('is_executing', True)  # Sync to shared state
        
        try:
            success = await self._execute_step_with_retry(current_step, current_step_index)
            
            if success:
                # Step succeeded
                logger.info(f"Step {current_step_index + 1} completed successfully")
                await self._update_step_status(current_step_index, 'completed')
                
                # Notify high-level to move to next step
                await self.high_brain.mark_step_completed(current_step_index)
                
                # Add to short-term memory
                self.memory.add_short_term_memory(
                    'step_success',
                    f"Completed: {current_step['description']}",
                    {'step_index': current_step_index}
                )
                
                # Add to learned experience (if significant)
                task_plan = await self.shared_state.get('active_task')
                if task_plan:
                    goal = task_plan.get('goal', '')
                    self.memory.add_experience(
                        summary=f"Successfully: {current_step['description']}",
                        details={
                            'step': current_step['description'],
                            'step_index': current_step_index,
                            'goal': goal
                        }
                    )
            else:
                # Step failed after retries
                logger.warning(f"Step {current_step_index + 1} failed after multiple attempts")
                await self._update_step_status(current_step_index, 'failed')
                
                # Request guidance from high-level
                await self._request_modification(
                    'stuck_task',
                    step_index=current_step_index,
                    reason="Failed after multiple attempts",
                    failures=current_step.get('failures', [])
                )
        
        except asyncio.CancelledError:
            # Step was interrupted by higher priority action
            # Don't mark as failed, will be resumed by ExecutionCoordinator
            logger.info(f"⚠️ Step {current_step_index + 1} was interrupted, will resume when possible")
            # Keep status as 'in_progress' so it can be resumed
        
        except Exception as e:
            logger.error(f"Error executing step: {e}", exc_info=True)
            await self._update_step_status(current_step_index, 'failed')
        
        finally:
            self.is_executing = False
            await self.shared_state.update('is_executing', False)  # Sync to shared state
    
    async def _update_step_status(self, step_index: int, status: str, failure_reason: Optional[str] = None):
        """Update the status of the active task's current step."""

        await self.high_brain.update_active_task_step(step_index, status, failure_reason)
    
    async def _execute_step_with_retry(self, step: Dict[str, Any], step_index: int, max_attempts: int = 5) -> bool:
        """
        Execute a step with retry mechanism (similar to self-prompter)
        
        Args:
            step: Step dictionary
            step_index: Step index
            max_attempts: Maximum attempts
        
        Returns:
            True if successful, False otherwise
        """
        failures = []
        
        for attempt in range(max_attempts):
            logger.info(f"Attempt {attempt + 1}/{max_attempts} for step: {step['description']}")
            
            try:
                # use ExecutionCoordinator
                if hasattr(self, 'exec_coordinator') and self.exec_coordinator:
                    result = await self.exec_coordinator.execute_action(
                        layer='mid',
                        label=f'task:{step["description"][:30]}',
                        action_fn=lambda: self._execute_task_internal({'description': step['description']}),
                        can_interrupt=['low_reflex', 'low_mode', 'unstuck'],
                        auto_resume=True
                    )
                    
                    if result.get('blocked'):
                        logger.debug("Task execution blocked by higher priority action")
                        return False
                    
                    # Handle cancellation - will be resumed later
                    if result.get('cancelled'):
                        logger.info("⚠️ Task was cancelled by higher priority action - will resume")
                        raise asyncio.CancelledError("Task interrupted by higher priority action")
                    
                    # Check the actual execution result from action_fn
                    # ExecutionCoordinator wraps the return value in result['result']
                    task_success = result.get('result', False)
                    
                    # Also check if there was an error in the wrapper
                    if result.get('error'):
                        error_msg = result.get('error', 'Unknown error')
                        success = False
                    else:
                        success = task_success
                        error_msg = 'Task returned False' if not success else ''
                else:
                    success, error_msg = await self._execute_task({'description': step['description']})
                
                if success:
                    return True
                else:
                    failures.append(error_msg)
                    logger.warning(f"Attempt {attempt + 1} failed: {error_msg}")
                    
                    # Store failures in step
                    step['failures'] = failures
                    
                    # Check if should request guidance early
                    if attempt >= 2:  # After 3 failures
                        # Evaluate if step is achievable
                        should_request = await self._evaluate_if_should_request_help(step, failures)
                        if should_request:
                            logger.info("Requesting guidance from high-level brain")
                            await self._request_modification(
                                'stuck_task',
                                step_index=step_index,
                                reason=f"Failed {attempt + 1} times, may not be achievable",
                                failures=failures
                            )
                            return False
            
            except asyncio.CancelledError:
                # Task was interrupted by higher priority action
                # Don't count as failure, re-raise to propagate cancellation
                logger.info(f"⚠️ Attempt {attempt + 1} was interrupted by higher priority action")
                raise
            
            except Exception as e:
                logger.error(f"Error in attempt {attempt + 1}: {e}", exc_info=True)
                failures.append(str(e))
        
        # All attempts failed
        logger.error(f"Step failed after {max_attempts} attempts")
        step['failures'] = failures
        return False
    
    async def _evaluate_if_should_request_help(self, step: Dict[str, Any], failures: List[str]) -> bool:
        """
        Use LLM to evaluate if step should request high-level guidance
        
        Args:
            step: Current step
            failures: List of failure messages
        
        Returns:
            True if should request help
        """
        failures_text = "\n".join([f"- {f}" for f in failures[-3:]])  # Last 3 failures
        
        prompt = f"""Evaluate if this task step is achievable or needs modification.

Step: {step['description']}

Recent Failures:
{failures_text}

Can this step be completed with more attempts, or does it need strategic revision?

Respond with ONE WORD:
- "retry" if it can be completed with better approach/more attempts
- "modify" if the step itself needs to be changed

Response:"""
        
        try:
            response = await self.llm.send_request([], prompt)
            decision = response.strip().lower()
            
            return 'modify' in decision
        
        except Exception as e:
            logger.error(f"Error evaluating help need: {e}")
            return False  # Default to retry
    
    async def _request_modification(
        self,
        request_type: str,
        step_index: Optional[int] = None,
        reason: str = "",
        failures: Optional[List[str]] = None,
        player_name: Optional[str] = None,
        directive: Optional[str] = None
    ):
        """
        Request guidance or a new task from the high-level brain.
        
        Mid-level brain only reports problems and player directives.
        High-level brain decides what action to take.
        """
        logger.info("Requesting high-level guidance: %s", request_type)

        active_task = await self.shared_state.get('active_task')
        task_source = active_task.get('source', 'internal') if active_task else 'internal'
        task_goal = active_task.get('goal') if active_task else None
        resolved_player_name = player_name or (active_task.get('player_name') if active_task else None)
        
        # Mid-level brain only reports problems - high-level brain generates suggestions
        
        request: Dict[str, Any] = {
            'request_type': request_type,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'processed': False,
            'task_source': task_source,
            'active_task_goal': task_goal,
            'active_task_snapshot': active_task,
        }

        if resolved_player_name:
            request['player_name'] = resolved_player_name

        if request_type == 'stuck_task':
            request.update({
                'current_step_index': step_index,
                'failures': failures or [],
                'context': f"Attempted {len(failures or [])} times"
            })
        elif request_type == 'player_directive':
            request.update({
                'directive': directive or reason,
            })
        
        # Send to high-level brain
        await self.shared_state.update('modification_request', request)
        
        # Immediately wake up high-level brain for urgent processing
        if self.coordinator and hasattr(self.coordinator, 'high_brain_wake_event'):
            self.coordinator.high_brain_wake_event.set()
            logger.info("⚡ Triggered immediate high-level brain wake")
        
        # Wait for response (high-level brain will check modification_request)
        self.is_waiting_for_guidance = True
        logger.info("Waiting for high-level brain guidance...")
    
    async def _handle_guidance_response(self, response: Dict[str, Any]):
        """
        Handle guidance response from high-level brain
        
        Args:
            response: Response from high-level brain
        """
        decision = response.get('decision', 'no_change')
        explanation = response.get('explanation', '')
        guidance = response.get('guidance', '')
        player_message = response.get('player_message')
        player_name = response.get('player_name')

        logger.info("High-level decision: %s (%s)", decision, explanation or guidance)

        if player_message and player_name:
            await self._send_chat_response(player_message, player_name)

        if decision in ('updated_task', 'pushed_sub_task', 'accepted_player_task'):
            task_plan = await self.shared_state.get('active_task')
            if task_plan and task_plan.get('steps'):
                current_idx = task_plan.get('current_step_index', 0)
                current_step = task_plan['steps'][min(current_idx, len(task_plan['steps']) - 1)]
                lesson = explanation or guidance or 'High-level plan adjustment.'
                self.memory.add_lesson(
                    lesson=lesson,
                    context=current_step.get('description', 'Unknown step')
                )

        elif decision in ('discarded_task', 'rejected_player_task'):
            self.memory.add_short_term_memory(
                'task_update',
                f"High-level discarded task: {explanation or guidance}",
                {'decision': decision}
            )

        else:
            # Treat as guidance only
            logger.info("Guidance from high-level: %s", guidance)
    
    async def _execute_task(self, task: Dict[str, Any]) -> tuple:
        """
        Execute a task (return tuple)
        
        Args:
            task: Task dictionary
        
        Returns:
            (success: bool, error_msg: str)
        """
        result = await self._execute_task_internal(task)
        if isinstance(result, dict):
            return result.get('success', False), result.get('error', 'Unknown error')
        return result
    
    async def _execute_task_internal(self, task: Dict[str, Any]) -> bool:
        """
        Execute a task by generating code and sending to JavaScript
        Uses retry mechanism similar to original Coder class
        
        Args:
            task: Task dictionary
        
        Returns:
            True if successful, False otherwise
        """
        logger.debug(f"Executing task: {task.get('description')}")
        
        # Request fresh game state BEFORE code generation
        # This ensures the LLM has the latest inventory, position, etc.
        await self._refresh_game_state()
        
        # Get current game state (now up-to-date)
        state = await self.shared_state.get_all()
        
        # Build message history for code generation
        messages = []
        
        # Add task context
        task_description = task.get('description', 'No description')
        messages.append({
            'role': 'system',
            'content': f'Code generation started. Task: {task_description}'
        })
        
        MAX_ATTEMPTS = 5
        MAX_NO_CODE_FAILURES = 3
        no_code_failures = 0
        
        for attempt in range(MAX_ATTEMPTS):
            logger.info(f"Code generation attempt {attempt + 1}/{MAX_ATTEMPTS}")
            
            try:
                # Refresh state before each retry attempt (inventory may have changed)
                if attempt > 0:
                    await self._refresh_game_state()
                    state = await self.shared_state.get_all()
                
                # Prepare prompt for code generation
                prompt = await self._prepare_code_generation_prompt(task, state, messages)
                
                # Generate code using LLM
                response = await self.llm.send_request([], prompt)
                
                # Check if response contains code
                if '```' not in response:
                    # No code block found
                    if no_code_failures >= MAX_NO_CODE_FAILURES:
                        logger.error("Agent refused to write code after multiple attempts")
                        task['last_error'] = "Agent would not write code"
                        return False
                    
                    messages.append({
                        'role': 'assistant',
                        'content': response
                    })
                    messages.append({
                        'role': 'system',
                        'content': 'Error: no code provided. Write code in codeblock in your response. ``` // example ```'
                    })
                    no_code_failures += 1
                    logger.warning("No code block generated, retrying...")
                    continue
                
                # Extract code from response
                code = self._extract_code(response)
                
                if not code:
                    logger.error("Failed to extract code from response")
                    task['last_error'] = "No code extracted"
                    return False
                
                logger.info(f"Generated code:\n{code}")
                
                # Validate code (basic checks)
                validation_error = await self._validate_code(code)
                if validation_error:
                    logger.warning(f"Code validation error: {validation_error}")
                    messages.append({
                        'role': 'assistant',
                        'content': response
                    })
                    messages.append({
                        'role': 'system',
                        'content': f'Code validation error:\n{validation_error}\nPlease fix and try again.'
                    })
                    continue
                
                # Inject interrupt checks into code (like original project)
                code = self._inject_interrupt_checks(code)
                
                # Send code to JavaScript for execution
                result = await self._send_code_to_javascript(code)
                
                # Refresh game state AFTER code execution
                # This ensures next attempt or step has accurate state
                await self._refresh_game_state()
                
                # Check execution result
                if result.get('success'):
                    # Success! Log output and return
                    output = result.get('message', 'Code executed successfully')
                    logger.info(f"Task completed: {output}")
                    
                    # Add to memory
                    self.memory.add_short_term_memory(
                        'task_success',
                        f"Task: {task.get('description')}",
                        {'output': output}
                    )
                    
                    return True
                
                # If code throws an error, result.get('success') will be false
                # The JS bridge now propagates the error correctly
                error_msg = result.get('message', 'Unknown error during execution')
                logger.warning(f"Code execution failed: {error_msg}")
                
                # Add to memory
                self.memory.add_short_term_memory(
                    'code_execution_failed',
                    f"Task: {task.get('description')} - Error: {error_msg}",
                    {'error': error_msg, 'code': code}
                )
                
                messages.append({
                    'role': 'assistant',
                    'content': response
                })
                messages.append({
                    'role': 'system',
                    'content': f'CODE EXECUTION ERROR: {error_msg}\nPlease analyze the error and try again.'
                })
                # Continue to next attempt
            
            except Exception as e:
                logger.error(f"Error in code generation attempt: {e}", exc_info=True)
                messages.append({
                    'role': 'system',
                    'content': f'Error during code generation: {str(e)}\nPlease try again.'
                })
        
        # All attempts failed
        logger.error(f"Code generation failed after {MAX_ATTEMPTS} attempts")
        task['last_error'] = f'Code generation failed after {MAX_ATTEMPTS} attempts'
        return False
    
    async def _prepare_code_generation_prompt(self, task: Dict[str, Any], state: Dict[str, Any], conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Prepare prompt for code generation with conversation history
        
        Args:
            task: Task to generate code for
            state: Current game state
            conversation_history: Previous attempts and errors
        
        Returns:
            Formatted prompt string
        """
        prompt = self.system_prompt
        
        # Get agent name
        agent_name = state.get('agent_name', 'BrainyBot')
        
        # Use GameStateFormatter to populate basic placeholders
        prompt = GameStateFormatter.populate_prompt_placeholders(prompt, state, agent_name)
        
        # Add task-specific information
        CODE_RULES = """
            CRITICAL: Error handling rules:
            1. Check results: if (!success) { throw new Error("Failed") }
            2. Never swallow errors: catch(e) { throw e } or re-throw
            3. Don't use empty catch blocks
        """
        prompt = prompt.replace('$TASK', f"{task.get('description', 'No description')}\n\n{CODE_RULES}")
        
        # Add task plan context
        task_plan = await self.shared_state.get('active_task')
        if task_plan and task_plan.get('steps'):
            current_idx = task_plan.get('current_step_index', 0)
            total_steps = len(task_plan.get('steps', []))
            goal = task_plan.get('goal', 'Unknown')
            task_plan_context = f"""Goal: {goal}
Current Step: {current_idx + 1}/{total_steps}
This step: {task.get('description', 'Unknown')}"""
        else:
            task_plan_context = "No active task plan"
        prompt = prompt.replace('$TASK_PLAN_CONTEXT', task_plan_context)
        
        # Add learned experience
        learned_exp = self.memory.get_learned_experience_summary(max_insights=3, max_lessons=5)
        prompt = prompt.replace('$LEARNED_EXPERIENCE', learned_exp)
        
        # Extract just lessons for LESSONS_LEARNED placeholder
        lessons_text = ""
        learned_data = self.memory.learned_experience.get('lessons_learned', [])
        if learned_data:
            lessons_text = "\n".join([f"- {lesson['lesson']}" for lesson in learned_data[-5:]])
        else:
            lessons_text = "No lessons learned yet."
        prompt = prompt.replace('$LESSONS_LEARNED', lessons_text)
        
        # Code docs (skill library) - use FULL API documentation
        from utils.api_docs_generator import get_full_api_docs
        code_docs = get_full_api_docs()
        prompt = prompt.replace('$CODE_DOCS', code_docs)
        
        # Examples - use empty for now
        prompt = prompt.replace('$EXAMPLES', "")
        
        # Add conversation history if provided (for retry attempts)
        if conversation_history:
            history_text = "\n\n## Previous Attempts\n"
            for msg in conversation_history:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                history_text += f"\n**{role.upper()}**: {content}\n"
            prompt += history_text
        
        return prompt
    
    async def _validate_code(self, code: str) -> str:
        """
        Validate generated code for common issues
        Similar to original Coder._lintCode
        
        Args:
            code: JavaScript code to validate
        
        Returns:
            Error message if validation fails, None if code is valid
        """
        errors = []
        
        # Check for await statements (code must be async)
        if 'await ' not in code:
            errors.append("Code must contain at least one 'await' statement for async operations")
        
        # Check for forbidden patterns
        forbidden_patterns = {
            'setTimeout': "Do not use setTimeout - use await skills.wait(bot, milliseconds) instead",
            'setInterval': "Do not use setInterval - use a while loop with await skills.wait() instead",
            'console.log': "Do not use console.log() - use log(bot, message) instead",
            'require(': "Do not use require() - all needed modules are already imported",
            'import ': "Do not use import statements - all needed modules are already imported"
        }
        
        for pattern, error_msg in forbidden_patterns.items():
            if pattern in code:
                errors.append(error_msg)
        
        # Check for reserved variable names (like 'log' which is a function)
        import re
        # Check for 'let log =', 'const log =', 'var log =' declarations
        if re.search(r'\b(let|const|var)\s+log\s*=', code):
            errors.append("Do not use 'log' as a variable name - it's a reserved function. Use 'logBlock', 'oakLog', etc.")
        
        # Check for skills/world function calls
        import re
        skill_pattern = r'(?:skills|world)\.(\w+)\('
        matches = re.findall(skill_pattern, code)
        
        if matches:
            # Validate that these functions exist - use cached instance
            all_skills = self.skill_lib.get_all_skill_names()
            
            for func_name in matches:
                if func_name not in all_skills:
                    errors.append(f"Function '{func_name}' does not exist in skills/world library")
        
        if errors:
            return "### CODE VALIDATION ERRORS ###\n" + "\n".join(f"- {err}" for err in errors)
        
        return None
    
    def _extract_code(self, response: str) -> Optional[str]:
        """
        Extract code from LLM response
        
        Args:
            response: LLM response text
        
        Returns:
            Extracted code or None
        """
        # Look for code blocks
        if '```' in response:
            # Find code between ``` markers
            parts = response.split('```')
            for i, part in enumerate(parts):
                if i % 2 == 1:  # Odd indices are code blocks
                    # Remove language identifier if present
                    code = part.strip()
                    if code.startswith('javascript') or code.startswith('js'):
                        code = code.split('\n', 1)[1] if '\n' in code else code
                    return code.strip()
        
        logger.warning("No code block found in response")
        return None
    
    def _inject_interrupt_checks(self, code: str) -> str:
        """
        Inject interrupt checks into generated code (like original project)
        
        This allows real-time interruption by checking bot.interrupt_code after each statement.
        Based on original MindCraft's approach: replaceAll(';\n', '; if(bot.interrupt_code) {log(bot, "Code interrupted.");return;}\n')
        
        Args:
            code: Original JavaScript code
        
        Returns:
            Code with interrupt checks injected
        """
        # Replace semicolon + newline with interrupt check
        # This ensures every statement is followed by an interrupt check
        injected_code = code.replace(';\n', '; if(bot.interrupt_code) {log(bot, "Code interrupted.");return;}\n')
        
        # Also handle semicolons at end of code
        if injected_code.endswith(';'):
            injected_code += ' if(bot.interrupt_code) {log(bot, "Code interrupted.");return;}'
        
        logger.debug("Injected interrupt checks into code")
        return injected_code
    
    async def _send_code_to_javascript(self, code: str) -> Dict[str, Any]:
        """
        Send generated code to JavaScript for execution and wait for result
        
        Args:
            code: JavaScript code to execute
        
        Returns:
            Execution result dict with 'success' and 'message'/'error'
        """
        logger.debug("Sending code to JavaScript...")
        
        try:
            # Check if bot is in game
            bot_ready = await self.shared_state.get('bot_ready') or False
            
            if not bot_ready:
                logger.warning("Bot not in game - cannot execute code")
                return {
                    'success': False,
                    'message': 'Bot not spawned in game yet. Please wait for bot to connect.'
                }
            
            # Clear previous execution result
            await self.shared_state.update('last_execution_result', None)
            
            # Reset interrupt_code flag before execution
            await self.shared_state.update('interrupt_code', False)
            
            # Send code via IPC with interrupt_code flag
            interrupt_flag = await self.shared_state.get('interrupt_code')
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': code,
                    'interrupt_code': interrupt_flag  # Sync flag to JavaScript
                }
            })
            
            # Wait for execution result (with timeout)
            timeout = 30  # 30 seconds timeout
            start_time = asyncio.get_event_loop().time()
            poll_interval = 0.1  # Check every 100ms
            
            while True:
                # Sync interrupt_code flag periodically to JavaScript
                current_interrupt_flag = await self.shared_state.get('interrupt_code')
                if current_interrupt_flag:
                    # Notify JavaScript to set bot.interrupt_code = true
                    await self.ipc_server.send_command({
                        'type': 'set_interrupt_flag',
                        'data': {'value': True}
                    })
                
                result = await self.shared_state.get('last_execution_result')
                
                if result is not None:
                    # Got result from JavaScript
                    logger.info(f"Received execution result: {'success' if result.get('success') else 'failed'}")
                    return result
                
                # Check timeout
                if asyncio.get_event_loop().time() - start_time > timeout:
                    logger.error("Execution timeout - no response from JavaScript")
                    
                    # Clean up interrupt flag (Python + JavaScript)
                    await self.shared_state.update('interrupt_code', False)
                    await self.ipc_server.send_command({
                        'type': 'set_interrupt_flag',
                        'data': {'value': False}
                    })
                    
                    return {
                        'success': False,
                        'message': 'Execution timeout - bot may be stuck or code took too long'
                    }
                
                # Wait before next check
                await asyncio.sleep(poll_interval)
                
                # Wait a bit before checking again (this is a cancellation point)
                await asyncio.sleep(0.1)
        
        except asyncio.CancelledError:
            # Task was cancelled by higher priority action (e.g., low health reflex)
            logger.warning("⚠️ Code execution cancelled by higher priority action")
            # Clear execution result to avoid confusion
            await self.shared_state.update('last_execution_result', None)
            raise  # Re-raise to propagate cancellation
            
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    async def _handle_pending_chat(self, chat_data: Dict[str, Any]):
        """
        Handle chat message from player
        
        Args:
            chat_data: Chat message data {player, message}
        """
        player = chat_data.get('player', 'Player')
        message = chat_data.get('message', '')
        
        logger.info(f"Handling chat from {player}: {message}")
        
        self.is_executing = True
        await self.shared_state.update('is_executing', True)  # Sync to shared state
        
        try:
            # Check if message contains a command or request
            if await self._is_action_request(message):
                # Create task from chat message
                task = await self._create_task_from_chat(player, message)
                if task:
                    # Request high-level brain to evaluate player directive
                    await self._request_modification(
                        'player_directive',
                        reason=f"Player {player} requested: {message}",
                        player_name=player,
                        directive=task['description']
                    )
                    logger.info(f"Requested high-level evaluation for player directive: {task['description']}")
                    # Send neutral acknowledgment while waiting for high-level decision
                    await self._send_chat_response(f"Got it {player}, let me think about that.", player)
            else:
                # Just chat response
                response = await self._generate_chat_response(player, message)
                await self._send_chat_response(response, player)
        
        except Exception as e:
            logger.error(f"Error handling chat: {e}", exc_info=True)
        
        finally:
            self.is_executing = False
            await self.shared_state.update('is_executing', False)  # Sync to shared state
    
    async def _is_action_request(self, message: str) -> bool:
        """
        Check if message is an action request for the bot using LLM
        
        Args:
            message: Chat message
        
        Returns:
            True if message requests an action from the bot
        """
        # Quick filter for obvious system messages
        message_lower = message.lower()
        system_indicators = ['set ', 'game mode', 'gamemode', 'changed to', 'joined the game', 'left the game']
        if any(indicator in message_lower for indicator in system_indicators):
            return False
        
        # Use LLM to determine if this is an action request
        prompt = f"""Is the following message asking the bot to perform an action in Minecraft?

Message: "{message}"

An action request is a message that asks the bot to do something (mine, build, collect, follow, etc.).
NOT an action request: greetings, questions, general chat, game system messages, observations.

Respond with ONLY "yes" or "no"."""

        try:
            response = await self.llm.send_request([], prompt)
            response_lower = response.strip().lower()
            
            # Check for yes/no
            if 'yes' in response_lower:
                logger.debug(f"LLM determined message is action request: {message}")
                return True
            else:
                logger.debug(f"LLM determined message is NOT action request: {message}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking if message is action request: {e}")
            # Fallback to keyword check
            action_keywords = ['collect', 'mine', 'build', 'craft', 'go', 'come', 'follow', 
                              'attack', 'kill', 'get', 'make', 'create', 'find', 'dig', 'chop']
            return any(keyword in message_lower for keyword in action_keywords)
    
    async def _create_task_from_chat(self, player: str, message: str) -> Optional[Dict[str, Any]]:
        """
        Create a task from chat message
        
        Args:
            player: Player name
            message: Chat message
        
        Returns:
            Task dictionary or None
        """
        # Use LLM to interpret message and create task
        prompt = f"""Convert this chat message into a Minecraft task description.

Player: {player}
Message: {message}

Respond with ONLY the task description (what the bot should do), no explanation.
Example: "collect 10 oak logs" or "go to player {player}" or "build a small house"

Task description:"""
        
        try:
            response = await self.llm.send_request([], prompt)
            task_desc = response.strip()
            
            return {
                'description': task_desc,
                'type': 'chat_request',
                'requester': player,
                'retry_count': 0
            }
        except Exception as e:
            logger.error(f"Error creating task from chat: {e}")
            return None
    
    async def _generate_chat_response(self, player: str, message: str) -> str:
        """
        Generate chat response using a detailed prompt template.
        
        Args:
            player: Player name
            message: Chat message
        
        Returns:
            Response string
        """
        try:
            # 1. Load the chat prompt template (directly from file, not from config)
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            chat_prompt_path = os.path.join(project_root, 'agent', 'prompts', 'chat_prompt.txt')
            
            try:
                with open(chat_prompt_path, 'r', encoding='utf-8') as f:
                    prompt_template = f.read()
            except FileNotFoundError:
                logger.error(f"Chat prompt template not found at {chat_prompt_path}")
                return "I'm at a loss for words."
            
            # 2. Refresh game state to get latest inventory
            await self._refresh_game_state()
            await asyncio.sleep(0.15)  # Give JS time to update state

            # 3. Gather all necessary context
            state = await self.shared_state.get_all()
            
            # Agent Info
            agent_name = state.get('agent_name', 'BrainyBot')
            
            # Task Info - handle strategic_goal which might be a dict or None
            strategic_goal_data = state.get('strategic_goal')
            if isinstance(strategic_goal_data, dict):
                strategic_goal = strategic_goal_data.get('goal_priority', 'exploring the world')
            elif isinstance(strategic_goal_data, str):
                strategic_goal = strategic_goal_data
            else:
                strategic_goal = 'exploring the world'
            
            task_stack_summary = state.get('task_stack_summary', 'No tasks in the stack.')
            active_task_dict = state.get('active_task')
            if active_task_dict and active_task_dict.get('steps'):
                current_idx = active_task_dict.get('current_step_index', 0)
                current_step = active_task_dict['steps'][min(current_idx, len(active_task_dict['steps']) - 1)]
                active_task_summary = current_step.get('description', 'figuring out what to do next')
            else:
                active_task_summary = 'currently idle'

            # Memory - get recent short-term memories and format them
            recent_memory_entries = self.memory.get_recent_memories(count=5)
            if recent_memory_entries:
                memory_lines = []
                for entry in recent_memory_entries:
                    event_type = entry.get('type', 'event')
                    content = entry.get('content', '')
                    memory_lines.append(f"- [{event_type}] {content}")
                recent_memories = "\n".join(memory_lines)
            else:
                recent_memories = "No recent memories."
            
            # Player Info - use get_player_data to get dictionary
            player_data = self.memory.get_player_data(player)
            if player_data:
                player_opinion = player_data.get('relationship', 'neutral')
                personality_list = player_data.get('personality', [])
                preferences_list = player_data.get('preferences', [])
                player_info_summary = f"Personality: {', '.join(personality_list[-3:]) if personality_list else 'unknown'}, Preferences: {', '.join(preferences_list[-3:]) if preferences_list else 'unknown'}"
            else:
                player_opinion = 'neutral'
                player_info_summary = "Personality: unknown, Preferences: unknown"

            # Chat History - ensure it's a string
            chat_context = self.chat_manager.get_player_chat_context(player, limit=5)
            if not chat_context or chat_context is None:
                chat_context = "No previous conversation."

            # 3. Populate the prompt template using GameStateFormatter
            # First populate all environment placeholders ($STATS, $INVENTORY, etc.)
            prompt = GameStateFormatter.populate_prompt_placeholders(
                prompt_template, 
                state, 
                agent_name
            )
            
            # Then populate chat-specific placeholders
            prompt = prompt.replace('$AGENT_NAME', str(agent_name))
            prompt = prompt.replace('$STRATEGIC_GOAL', str(strategic_goal))
            prompt = prompt.replace('$TASK_STACK', str(task_stack_summary))
            prompt = prompt.replace('$ACTIVE_TASK', str(active_task_summary))
            prompt = prompt.replace('$RECENT_MEMORIES', str(recent_memories))
            prompt = prompt.replace('$PLAYER_NAME', str(player))
            prompt = prompt.replace('$PLAYER_INFO', str(player_info_summary))
            prompt = prompt.replace('$PLAYER_OPINION', str(player_opinion))
            prompt = prompt.replace('$CHAT_CONTEXT', str(chat_context))
            prompt = prompt.replace('$MESSAGE', str(message))
            
            # 4. Send to LLM and get response
            response = await self.llm.send_request([], prompt)
            response_text = response.strip()
            
            # 5. Store chat and extracted info
            self.chat_manager.add_chat(player, message, response_text)
            await self._extract_player_info_from_chat(player, message, response_text)
            
            return response_text
        
        except Exception as e:
            logger.error(f"Error generating detailed chat response: {e}", exc_info=True)
            return "Sorry, my brain just short-circuited. What were we talking about?"
    
    async def _send_chat_response(self, message: str, player: str = None):
        """
        Send chat message via IPC
        
        Args:
            message: Message to send
            player: Player name to whisper to (optional, uses whisper if provided)
        """
        logger.info(f"Sending chat: {message}")
        
        try:
            # Send via IPC with player name for whisper support
            await self.ipc_server.send_command({
                'type': 'chat',
                'data': {
                    'message': message,
                    'player_name': player  # Include player for whisper in 1.19+
                }
            })
        except Exception as e:
            logger.error(f"Error sending chat: {e}")
    
    async def _extract_player_info_from_chat(self, player: str, message: str, bot_response: str):
        """
        Extract and store player information from chat
        
        Args:
            player: Player name
            message: Player's message
            bot_response: Bot's response
        """
        # Use LLM to detect if this reveals important player information
        prompt = f"""Analyze this conversation for important player information.

Player: {player}
Message: {message}
Bot response: {bot_response}

Does this reveal any important information about the player's:
1. Personality traits (e.g., "friendly", "impatient", "curious", "helpful")
2. Preferences (e.g., "likes building", "prefers survival mode", "enjoys combat")
3. Specific requests or goals

If YES, respond with a brief description (max 10 words). If NO, respond with "none".
Example responses:
- "friendly and curious, enjoys exploring"
- "prefers building, dislikes combat"
- "none"

Analysis:"""
        
        try:
            analysis = await self.llm.send_request([], prompt)
            analysis = analysis.strip().lower()
            
            if analysis != "none" and len(analysis) > 3:
                # Extract information type
                if any(word in analysis for word in ['friendly', 'impatient', 'curious', 'helpful', 'aggressive']):
                    self.memory.update_player_info(player, 'personality', analysis)
                    logger.info(f"Learned about {player}'s personality: {analysis}")
                elif any(word in analysis for word in ['likes', 'prefers', 'enjoys', 'wants', 'dislikes']):
                    self.memory.update_player_info(player, 'preference', analysis)
                    logger.info(f"Learned about {player}'s preferences: {analysis}")
                else:
                    self.memory.update_player_info(player, 'interaction', analysis)
                
                logger.info(f"Stored player information for {player}")
        
        except Exception as e:
            logger.debug(f"Error extracting player info: {e}")
    
    async def _refresh_game_state(self):
        """
        Request fresh game state from JavaScript bridge
        
        This is CRITICAL for ensuring the mid-level brain has accurate information
        about the bot's inventory, position, health, etc. before generating code.
        
        The JavaScript bridge will send back a state_update message which will be
        processed by brain_coordinator's handle_state_update handler.
        """
        try:
            # Request state update from JavaScript
            await self.ipc_server.send_command({
                'type': 'request_state_update',
                'data': {}
            })
            
            # Give JavaScript a moment to respond (100ms should be enough)
            await asyncio.sleep(0.1)
            
            logger.debug("🔄 Refreshed game state from JavaScript")
        
        except Exception as e:
            logger.warning(f"Failed to refresh game state: {e}")
