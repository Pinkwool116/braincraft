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
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
from utils.memory_manager import MemoryManager

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
        
        # Skill library (create once and reuse)
        from models.skill_library import SkillLibrary
        self.skill_lib = SkillLibrary()
        
        # Execution queue (temporary, generated from current task plan step)
        self.execution_queue = []
        self.current_execution = None
        
        # Execution history
        self.action_history = []
        self.chat_history = []
        
        # Execution state
        self.is_executing = False
        self.is_waiting_for_guidance = False  # Waiting for high-level response
        
        # Coordinator reference (set by coordinator after initialization)
        self.coordinator = None
        
        # Bot ready state tracking (to avoid spam)
        self._waiting_for_bot = False
        self._last_waiting_log_time = 0
        
        # Load system prompt
        self.system_prompt = self._load_system_prompt()
        
        # Configuration
        self.max_retries = config.get('mid_level_brain', {}).get('max_task_retries', 3)
        
        logger.info("Mid-level brain initialized (simplified version with single LLM)")
    
    def _load_system_prompt(self) -> str:
        """Load system prompt from file"""
        prompt_file = self.config.get('mid_level_brain', {}).get('system_prompt_file')
        if not prompt_file:
            return "You are a tactical execution AI for a Minecraft agent."
        
        try:
            # Handle relative paths
            import os
            if not os.path.isabs(prompt_file):
                # Relative to project root
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                prompt_file = os.path.join(project_root, prompt_file)
            
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt = f.read()
            logger.info(f"Loaded system prompt from {prompt_file}")
            return prompt
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return "You are a tactical execution AI for a Minecraft agent."
    
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
        # Get task plan from shared state (managed by high-level brain)
        task_plan = await self.shared_state.get('task_plan')
        
        if not task_plan or task_plan.get('status') != 'active':
            # No active task plan
            return
        
        current_step_index = task_plan.get('current_step_index', -1)
        steps = task_plan.get('steps', [])
        
        if current_step_index < 0 or current_step_index >= len(steps):
            # Invalid step index or plan completed
            return
        
        current_step = steps[current_step_index]
        step_status = current_step.get('status', 'pending')
        
        if step_status == 'completed':
            # This step is done, high-level should move to next
            return
        
        # Execute current step
        logger.info(f"Executing task plan step {current_step_index + 1}/{len(steps)}: {current_step['description']}")
        
        # Check if bot is ready
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
                task_plan = await self.shared_state.get('task_plan')
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
                await self._request_modification('modify_step', current_step_index, 
                                               reason="Failed after multiple attempts",
                                               failures=current_step.get('failures', []))
        
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
    
    async def _update_step_status(self, step_index: int, status: str):
        """
        Update step status in task plan
        
        Args:
            step_index: Step index
            status: New status
        """
        task_plan = await self.shared_state.get('task_plan')
        if task_plan and 0 <= step_index < len(task_plan.get('steps', [])):
            task_plan['steps'][step_index]['status'] = status
            await self.shared_state.update('task_plan', task_plan)
    
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
                    
                    success = result.get('success', False)
                    error_msg = result.get('error', 'Unknown error')
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
                            await self._request_modification('modify_step', step_index,
                                                           reason=f"Failed {attempt + 1} times, may not be achievable",
                                                           failures=failures)
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
    
    async def _request_modification(self, mod_type: str, step_index: int, reason: str, failures: List[str] = None, suggestion: str = "", player_name: str = None):
        """
        Request task plan modification from high-level brain
        
        Args:
            mod_type: Type of modification
            step_index: Current step index
            reason: Reason for request
            failures: List of failures
            suggestion: Suggested modification
            player_name: Player who requested this (if from chat)
        """
        logger.info(f"Requesting modification: {mod_type} for step {step_index + 1}")
        
        # Generate suggestion if not provided
        if not suggestion and failures:
            suggestion = await self._generate_modification_suggestion(step_index, failures)
        
        request = {
            'type': mod_type,
            'reason': reason,
            'current_step_index': step_index,
            'suggestion': suggestion,
            'failures': failures or [],
            'context': f"Attempted {len(failures or [])} times",
            'timestamp': datetime.now().isoformat(),
            'processed': False,
            'player_name': player_name  # Include player info for relationship check
        }
        
        # Send to high-level brain
        await self.shared_state.update('modification_request', request)
        
        # Immediately wake up high-level brain for urgent attention
        if self.coordinator:
            await self.coordinator.wake_high_brain()
            logger.info("⚡ High-level brain wake signal sent")
        else:
            logger.warning("Coordinator reference not set - cannot wake high-level brain immediately")
        
        # Wait for response
        self.is_waiting_for_guidance = True
        logger.info("Waiting for high-level brain guidance...")
    
    async def _generate_modification_suggestion(self, step_index: int, failures: List[str]) -> str:
        """
        Generate modification suggestion based on failures
        
        Args:
            step_index: Step index
            failures: List of failures
        
        Returns:
            Suggested modification
        """
        task_plan = await self.shared_state.get('task_plan')
        if not task_plan:
            return ""
        
        current_step = task_plan['steps'][step_index]
        failures_text = "\n".join([f"- {f}" for f in failures[-3:]])
        
        prompt = f"""Suggest a modification to this task step based on failures.

Current Step: {current_step['description']}

Failures:
{failures_text}

Suggest a modified version of this step that might work better.
Be specific and practical. Keep it brief (one sentence).

Suggestion:"""
        
        try:
            response = await self.llm.send_request([], prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating suggestion: {e}")
            return "Try a simpler approach"
    
    async def _handle_guidance_response(self, response: Dict[str, Any]):
        """
        Handle guidance response from high-level brain
        
        Args:
            response: Response from high-level brain
        """
        decision = response.get('decision', 'reject')
        explanation = response.get('explanation', '')
        guidance = response.get('guidance', '')
        
        logger.info(f"Received guidance: {decision} - {explanation}")
        
        if decision == 'approve' or decision == 'revise':
            # Task plan has been updated by high-level
            logger.info("Task plan modified by high-level brain")
            
            # Learn from this modification - add lesson
            task_plan = await self.shared_state.get('task_plan')
            if task_plan:
                current_step = task_plan['steps'][task_plan.get('current_step_index', 0)]
                lesson = f"Modified approach: {explanation}"
                self.memory.add_lesson(
                    lesson=lesson,
                    context=current_step.get('description', 'Unknown step')
                )
            # Task plan is already updated in shared_state by high-level
            # Just continue execution
        
        elif decision == 'reject':
            # High-level rejected modification, provided alternative guidance
            logger.info(f"Modification rejected. Guidance: {guidance}")
            # Store guidance for next attempt
            # Continue trying with current step
    
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
        
        # Get current game state
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
                else:
                    # Execution failed, prepare error message for retry
                    error_msg = result.get('message', 'Unknown error')
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
        
        # Replace placeholders
        prompt = prompt.replace('$NAME', state.get('agent_name', 'Agent'))
        
        CODE_RULES = """
            CRITICAL: Error handling rules:
            1. Check results: if (!success) { throw new Error("Failed") }
            2. Never swallow errors: catch(e) { throw e } or re-throw
            3. Don't use empty catch blocks
        """
        prompt = prompt.replace('$TASK', f"{task.get('description', 'No description')}\n\n{CODE_RULES}")
        
        # Add task plan context
        task_plan = await self.shared_state.get('task_plan')
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
        
        # Stats
        position = state.get('position', {})
        stats = f"""Health: {state.get('health', 20)}/20
Food: {state.get('food', 20)}/20
Position: x:{position.get('x', 0):.1f}, y:{position.get('y', 0):.1f}, z:{position.get('z', 0):.1f}"""
        prompt = prompt.replace('$STATS', stats)
        
        # Inventory
        inventory = state.get('inventory', {})
        inv_str = "\n".join([f"- {k}: {v}" for k, v in inventory.items()]) if inventory else "Empty"
        prompt = prompt.replace('$INVENTORY', inv_str)
        
        # Code docs (skill library) - use cached instance
        from models.skill_library import WORLD_FUNCTIONS
        relevant_skills = self.skill_lib.get_relevant_skills(task.get('description', ''), max_skills=10)
        code_docs = self.skill_lib.get_skill_docs(relevant_skills)
        code_docs += "\n" + WORLD_FUNCTIONS
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
            'setTimeout': "Do not use setTimeout - use await skills.wait() instead",
            'setInterval': "Do not use setInterval",
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
                    # Request high-level brain to add this as a new step to task plan
                    await self._request_modification(
                        'add_step',
                        step_index=-1,  # Add to end
                        reason=f"Player {player} requested: {message}",
                        suggestion=task['description'],
                        player_name=player  # Include player name for relationship check
                    )
                    logger.info(f"Requested to add step from chat: {task['description']}")
                    # Send acknowledgment
                    await self._send_chat_response(f"Okay {player}, I'll work on that", player)
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
        Generate chat response
        
        Args:
            player: Player name
            message: Chat message
        
        Returns:
            Response string
        """
        # Get agent info
        state = await self.shared_state.get_all()
        agent_name = state.get('agent_name', 'BrainyBot')
        agent_age_days = state.get('agent_age_days', 0)
        
        # Get recent chat history
        recent_chats = self.chat_history[-5:] if self.chat_history else []
        chat_context = "\n".join([
            f"{c['player']}: {c['message']}" for c in recent_chats
        ])
        
        prompt = f"""You are {agent_name}, a friendly Minecraft bot. You are {agent_age_days} days old in this world.
Respond to the player's message briefly and naturally.

Recent conversation:
{chat_context}

{player}: {message}

Your response (keep it short and friendly, 1-2 sentences):"""
        
        try:
            response = await self.llm.send_request([], prompt)
            
            # Add to memory
            self.memory.add_short_term_memory(
                'chat',
                f"{player}: {message}",
                {'response': response.strip()}
            )
            
            # Check if message contains important player information
            await self._extract_player_info_from_chat(player, message, response)
            
            # Record in history
            self.chat_history.append({
                'player': player,
                'message': message,
                'response': response.strip(),
                'timestamp': datetime.now().isoformat()
            })
            
            # Keep only last 20 chat messages
            if len(self.chat_history) > 20:
                self.chat_history = self.chat_history[-20:]
            
            return response.strip()
        
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return "Sorry, I didn't catch that."
    
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
