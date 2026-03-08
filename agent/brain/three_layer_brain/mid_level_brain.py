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
import asyncio
import logging
from datetime import datetime
from data_manager.memory_graph.memory_router import MemoryRouter
from data_manager.chat_manager import ChatManager
from prompts.prompt_logger import PromptLogger
from prompts.prompt_manager import PromptManager
from utils.json_parser import parse_code_generation_response, parse_chat_response

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
        self.memory = MemoryRouter(agent_name)
        
        # Chat manager for chat history persistence
        self.chat_manager = ChatManager(agent_name)
        
        # Prompt logger for debugging
        enable_logging = config.get('enable_prompt_logging', False)
        self.prompt_logger = PromptLogger('bots', agent_name, enabled=enable_logging)
        
        # Skill library (create once and reuse)
        from minecraft.skill_library import SkillLibrary
        self.skill_lib = SkillLibrary()
        
        # Execution state
        self.is_executing = False
        self.is_waiting_for_guidance = False  # Waiting for high-level response
        
        self.coordinator = None
        self.exec_coordinator = None
        
        # Bot ready state tracking (to avoid spam)
        self._waiting_for_bot = False
        self._last_waiting_log_time = 0
        self._last_bot_status = None
        
        self.prompt_manager = PromptManager()
        
        # 工作记忆：当前跟踪的任务目标（用于检测任务切换）
        self._tracked_task_goal = None
        
        # Configuration
        self.max_retries = config.get('mid_level_brain', {}).get('max_task_retries', 3)
        
        logger.info("Mid-level brain initialized")
    
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

    async def _check_task_transition(self, current_goal: str, task_plan: dict):
        """
        检测任务切换，管理工作记忆的生命周期。
        在 _process_task_plan 的开头调用。
        """
        if current_goal == self._tracked_task_goal:
            return  # 同一个任务，无需操作

        # 旧任务结束
        if self._tracked_task_goal is not None:
            if self.memory.working_memory.is_active:
                self.memory.end_task("success", f"任务完成: {self._tracked_task_goal}")
                await self.memory.crystallize(self.llm)

        # 新任务开始
        if current_goal is not None:
            environment = ""
            game_state = await self.shared_state.get('game_state')
            if game_state:
                pos = game_state.get('position', {})
                biome = game_state.get('biome', '')
                environment = f"位置: ({pos.get('x', '?')}, {pos.get('y', '?')}, {pos.get('z', '?')}), 生物群系: {biome}"
            self.memory.begin_task(current_goal, environment)

        self._tracked_task_goal = current_goal

    async def _process_task_plan(self):
        """
        Process current task plan from high-level brain
        
        Reads task_plan from shared_state and executes current step.
        """
        # Get active task plan from shared state (managed by high-level brain)
        task_plan = await self.shared_state.get('active_task')
        
        # 检测任务切换，管理工作记忆生命周期
        current_goal = task_plan.get('goal') if task_plan and task_plan.get('status') == 'active' else None
        await self._check_task_transition(current_goal, task_plan)
        
        if not task_plan or task_plan.get('status') != 'active':
            return
        
        current_step_index = task_plan.get('current_step_index', -1)
        steps = task_plan.get('steps', []) 
        
        if current_step_index < 0 or current_step_index >= len(steps):
            return
        
        current_step = steps[current_step_index]
        step_status = current_step.get('status', 'pending')
        
        # Handle failed steps: 
        # If a step previously failed (e.g., from a previous session), we should:
        # 1. Request high-level brain intervention to decide next action
        # 2. OR reset to pending if no modification was requested yet
        if step_status == 'failed':
            # Check if we've already requested modification for this failure
            if not current_step.get('modification_requested'):
                logger.warning(f"⚠️ Step {current_step_index + 1} previously failed - requesting high-level brain intervention")
                # Request modification from high-level brain
                failures = current_step.get('failures', [])
                await self._request_modification(
                    request_type='stuck_task',
                    step_index=current_step_index,
                    reason=f"Step failed in previous session ({len(failures)} attempts)",
                    failures=failures
                )
                # Mark that we've requested modification to avoid spamming
                current_step['modification_requested'] = True
                return  # Wait for high-level brain to process
            else:
                # Already requested modification, waiting for high-level response
                logger.debug(f"Step {current_step_index + 1} failed - waiting for high-level brain intervention")
                return
        
        # Don't execute if step is already completed
        if step_status == 'completed':
            logger.debug(f"Step {current_step_index + 1} already completed - waiting for high-level brain to move to next step")
            return
        
        # Check if bot is ready BEFORE logging execution
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            import time
            current_time = time.time()
            bot_status = await self.shared_state.get('bot_status') or 'connecting'
            # Log when status changes, and then rate-limit periodic reminders
            if self._last_bot_status != bot_status:
                if bot_status == 'dead':
                    logger.warning("Bot died - waiting for respawn...")
                elif bot_status == 'reconnecting':
                    logger.warning("Bot disconnected - waiting for reconnection...")
                else:
                    logger.warning("Bot not in game yet - waiting for bot to spawn...")
                self._last_bot_status = bot_status
            
            if not self._waiting_for_bot:
                self._waiting_for_bot = True
                self._last_waiting_log_time = current_time
            elif current_time - self._last_waiting_log_time > 300:
                if bot_status == 'dead':
                    logger.info("Still waiting: bot respawn...")
                elif bot_status == 'reconnecting':
                    logger.info("Still waiting: bot reconnection...")
                else:
                    logger.info("Still waiting for bot to spawn...")
                self._last_waiting_log_time = current_time
            return
        
        if self._waiting_for_bot:
            logger.info("Bot spawned! Continuing task execution")
            self._waiting_for_bot = False
            self._last_bot_status = 'online'
        
        # Log execution AFTER confirming bot is ready
        logger.info(f"Executing task plan step {current_step_index + 1}/{len(steps)}: {current_step['description']}")
        
        # Mark step as in_progress and clear any previous flags
        if step_status == 'pending':
            await self._update_step_status(current_step_index, 'in_progress')
        
        # Clear modification_requested flag when starting execution
        if 'modification_requested' in current_step:
            del current_step['modification_requested']
        
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
                
                # 记录到工作记忆
                self.memory.log("action", f"完成步骤: {current_step.get('description', 'unknown')}")
            else:
                # Step failed - LLM has already requested modification or safety limit reached
                logger.warning(f"Step {current_step_index + 1} execution stopped (modification requested or limit reached)")
                await self._update_step_status(current_step_index, 'failed')
                
        
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
    
    async def _update_step_failures(self, step_index: int, failures: List[Dict[str, Any]]):
        """Update the failures list of a step and persist to storage."""
        active_task = await self.shared_state.get('active_task')
        if not active_task:
            return
        
        steps = active_task.get('steps', [])
        if 0 <= step_index < len(steps):
            steps[step_index]['failures'] = failures
            # Notify high-level brain to save
            self.high_brain.task_stack_manager.persistence.save_state(
                self.high_brain.task_stack_manager.task_stack
            )
            logger.debug(f"Updated step {step_index} failures: {len(failures)} total")
    
    async def _execute_step_with_retry(self, step: Dict[str, Any], step_index: int) -> bool:
        """
        Execute a step with retry mechanism and intelligent reflection.
        Model decides when to request modification based on analysis.
        
        Args:
            step: Step dictionary
            step_index: Index of the step in the task plan (0-indexed)
        
        Returns:
            True if successful, False otherwise
        """
        # Resume from previous failures if any
        existing_failures = step.get('failures', [])
        failures = existing_failures.copy() if existing_failures else []
        
        # Start attempt from the last failure + 1, or from 1 if no previous failures
        attempt = len(failures)
        
        # No hard limit - let model decide when to request modification
        # Soft limit of 20 for safety (log warning if exceeded)
        while True:
            attempt += 1
            
            # Safety check: log warning if too many attempts
            if attempt > 10:
                logger.warning(f"⚠️ Step has been attempted {attempt} times - model should consider requesting modification")
            if attempt > 20:
                logger.error(f"❌ Step exceeded 20 attempts - forcing modification request")
                await self._request_modification(
                    request_type='stuck_task',
                    step_index=step_index,
                    reason=f"Exceeded maximum retry limit ({attempt} attempts)",
                    failures=failures
                )
                return False
            
            logger.info(f"Attempt {attempt} for step: {step['description']}")
            
            try:
                result = await self.exec_coordinator.execute_action(
                    layer='mid',
                    label=f'task:{step["description"][:30]}',
                    action_fn=lambda a=attempt, f=failures, s=step, idx=step_index: self._execute_step_by_code_generation(
                        step=s,
                        step_index=idx,
                        attempt=a,
                        failures=f.copy()
                    ),
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
                
                # Check for modification request flag set by _execute_step_by_code_generation
                if step.get('modification_requested'):
                    # Model requested modification, stop retrying
                    logger.info("Model requested modification, exiting retry loop")
                    # Clear the flag immediately after detecting it to avoid affecting future logic
                    del step['modification_requested']
                    return False
                
                # Check the actual execution result from action_fn
                task_success = result.get('result', False)
                
                # Also check if there was an error in the wrapper
                if result.get('error'):
                    error_msg = result.get('error', 'Unknown error')
                    success = False
                else:
                    success = task_success
                    # Get detailed error from task's last_error field
                    error_msg = step.get('last_error', 'Task returned False') if not success else ''
                
                if success:
                    return True
                else:
                    # Create detailed failure record
                    failure_record = {
                        'attempt': attempt,
                        'error': error_msg,
                        'code': step.get('last_code', None)  # Will be set by _execute_step_by_code_generation
                    }
                    failures.append(failure_record)
                    logger.warning(f"Attempt {attempt} failed: {error_msg}")
                    
                    step['failures'] = failures
                    await self._update_step_failures(step_index, failures)
            
            except asyncio.CancelledError:
                # Task was interrupted by higher priority action
                # Don't count as failure, re-raise to propagate cancellation
                logger.info(f"⚠️ Attempt {attempt} was interrupted by higher priority action")
                raise
            
            except Exception as e:
                logger.error(f"Error in attempt {attempt}: {e}", exc_info=True)
                failure_record = {
                    'attempt': attempt,
                    'error': f"Exception: {str(e)}",
                    'code': step.get('last_code', None)
                }
                failures.append(failure_record)
                step['failures'] = failures
                await self._update_step_failures(step_index, failures)
    
    async def _request_modification(
        self,
        request_type: str,
        step_index: Optional[int] = None,
        reason: str = "",
        failures: Optional[List[str]] = None,
        player_name: Optional[str] = None,
        directive: Optional[str] = None,
        suggestion: str = "",
        mid_level_analysis: Optional[Dict[str, Any]] = None
    ):
        """
        Request guidance or a new task from the high-level brain.
        
        Mid-level brain only reports problems and player directives.
        High-level brain decides what action to take.
        
        Args:
            request_type: Type of request ('stuck_task' or 'player_directive')
            step_index: Index of the failed step (0-indexed, for stuck_task)
            reason: Reason for the request
            failures: List of failure messages
            player_name: Name of the player (for player_directive)
            directive: Player directive text
            suggestion: Suggestion from mid-level brain (optional)
            mid_level_analysis: Analysis from mid-level brain (optional)
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
                'context': f"Attempted {len(failures or [])} times",
                'suggestion': suggestion,  # Add suggestion field
                'mid_level_analysis': mid_level_analysis  # Add analysis field
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
        task_plan = await self.shared_state.get('active_task')
        if task_plan and task_plan.get('steps'):
            current_idx = task_plan.get('current_step_index', 0)
            steps = task_plan.get('steps', [])
            if 0 <= current_idx < len(steps):
                current_step = steps[current_idx]
                if 'modification_requested' in current_step:
                    del current_step['modification_requested']
                    logger.debug(f"Cleared modification_requested flag from step {current_idx + 1}")
                
                # Reset failed steps to pending based on high-level decision
                if current_step.get('status') == 'failed':
                    if decision == 'pushed_sub_task':
                        # Sub-task was added - reset to pending to retry after sub-task completes
                        current_step['status'] = 'pending'
                        logger.info(f"Reset step {current_idx + 1} to 'pending' - will retry after sub-task completes")
                    elif decision == 'no_change':
                        # High-level says to continue trying - reset to pending
                        current_step['status'] = 'pending'
                        logger.info(f"Reset step {current_idx + 1} to 'pending' - high-level says continue trying")
                    # For 'updated_task' and 'discarded_task', the task/step will be replaced/removed anyway

        if player_message and player_name:
            await self._send_chat_response(player_message, player_name)
            # Add high-level response to chat history
            # Get the most recent chat to find the original player message
            recent_chats = self.chat_manager.get_player_chat_history(player_name, limit=1)
            player_last_msg = recent_chats[0]['player_message'] if recent_chats else "player request"
            self.chat_manager.add_chat(player_name, player_last_msg, player_message)

        if decision in ('updated_task', 'pushed_sub_task', 'accepted_player_task'):
            task_plan = await self.shared_state.get('active_task')
            if task_plan and task_plan.get('steps'):
                current_idx = task_plan.get('current_step_index', 0)
                current_step = task_plan['steps'][min(current_idx, len(task_plan['steps']) - 1)]
                lesson = explanation or guidance or 'High-level plan adjustment.'
                self.memory.log("observation", f"经验教训: {lesson}")

        elif decision in ('discarded_task', 'rejected_player_task'):
            self.memory.log("observation", f"任务被放弃: {explanation or guidance}")
            # 任务被放弃，结束工作记忆并反思
            self.memory.end_task("abandoned", explanation or guidance or '')
            await self.memory.crystallize(self.llm)
            self._tracked_task_goal = None

        else:
            # Treat as guidance only
            logger.info("Guidance from high-level: %s", guidance)
    
    async def _execute_step_by_code_generation(
        self,
        step: Dict[str, Any],
        step_index: int,
        attempt: int = 1,
        failures: Optional[List[str]] = None
    ) -> bool:
        """
        Execute a task step by generating code and sending to JavaScript.
        Uses LLM with reflection capability to decide between retrying and requesting help.
        
        This method is called once per retry attempt by _execute_step_with_retry.
        It generates code, executes it, and returns success/failure.
        
        Args:
            step: Step dictionary from the task plan
            step_index: Index of the step in the task plan (0-indexed)
            attempt: Current attempt number (1-indexed)
            failures: List of previous failure messages
        
        Returns:
            True if successful, False otherwise
        """
        if failures is None:
            failures = []
            
        logger.debug(f"Executing step (attempt {attempt}): {step.get('description')}")
        
        # Request fresh game state BEFORE code generation
        # This ensures the LLM has the latest inventory, position, etc.
        await self._refresh_game_state()
        
        # Get current game state (now up-to-date)
        state = await self.shared_state.get_all()
        
        # Build conversation history (empty for now, can be extended later)
        messages = []
        
        step_description = step.get('description', 'No description')
        
        try:
            # Prepare prompt for code generation with attempt/failures context
            prompt = await self._prepare_code_generation_prompt(
                step, state, messages, attempt=attempt, failures=failures
            )
            
            # Log prompt before sending
            prompt_file = self.prompt_logger.log_prompt(
                prompt=prompt,
                brain_layer="mid",
                prompt_type="code_generation",
                metadata={
                    "step_description": step_description,
                    "attempt": attempt
                }
            )
            logger.debug(f"Code generation prompt saved to: {prompt_file}")
            
            # Generate code using LLM
            response = await self.llm.send_request([], prompt)
            
            self.prompt_logger.update_response(prompt_file, response)
            
            # Try to parse JSON response (new reflection format)
            try:
                parsed = parse_code_generation_response(response)
                self._validate_code_generation_response(parsed)
                
                analysis = parsed.get('analysis', '')
                decision = parsed.get('decision', 'continue')
                modification_request = parsed.get('modification_request', '')
                code_from_json = parsed.get('code', '')
                
                logger.info(f"LLM Analysis: {analysis}")
                logger.info(f"LLM Decision: {decision}")
                
                # Handle decision to request modification
                if decision == 'request_modification':
                    logger.warning(f"LLM requests modification: {modification_request}")
                    
                    # Request help from high-level brain
                    await self._request_modification(
                        request_type='stuck_task',
                        step_index=step_index,
                        reason=modification_request,
                        failures=failures,
                        suggestion=modification_request,
                        mid_level_analysis={'analysis': analysis, 'decision': decision}
                    )
                    
                    # Set flag to exit retry loop
                    step['modification_requested'] = True
                    return False
                
                # Decision is 'continue' - extract code from JSON
                # The code field may contain markdown markers, so extract the actual code
                code = self._extract_code_from_field(code_from_json)
                
            except ValueError as e:
                # JSON parsing failed - LLM didn't follow the format
                # Provide detailed error message for debugging
                error_msg = f"LLM response format error: {str(e)}"
                
                # Include response snippet in error for better debugging
                response_snippet = response[:500] if len(response) > 500 else response
                detailed_error = f"{error_msg}\n\nResponse snippet:\n{response_snippet}"
                
                logger.warning(error_msg)
                logger.debug(f"Full response that failed to parse:\n{response}")
                
                # Store detailed error for failure tracking
                step['last_error'] = detailed_error
                step['last_code'] = None  # No code was generated
                return False
            
            if not code:
                logger.error("Failed to extract code from response")
                step['last_error'] = "No code extracted"
                return False
            
            logger.info(f"Generated code:\n{code}")
            
            # Save the generated code to step for failure tracking
            step['last_code'] = code
            
            validation_error = await self._validate_code(code)
            if validation_error:
                logger.warning(f"Code validation error: {validation_error}")
                step['last_error'] = f"Code validation failed: {validation_error}"
                return False
            
            code = self._inject_interrupt_checks(code)
            result = await self._send_code_to_javascript(code)
            await self._refresh_game_state()
            
            if result.get('success'):
                output = result.get('message', 'Code executed successfully')
                logger.info(f"Step completed: {output}")
                
                self.memory.log("action", f"代码执行成功: {step.get('description')}")
                
                return True
            
            error_msg = result.get('message', 'Unknown error during execution')
            logger.warning(f"Code execution failed: {error_msg}")
            
            self.memory.log("failure", f"代码执行失败: {step.get('description')}", detail=error_msg)
            
            step['last_error'] = error_msg
            return False
        
        except Exception as e:
            logger.error(f"Error in code generation: {e}", exc_info=True)
            step['last_error'] = f"Exception during code generation: {str(e)}"
            return False
    
    def _validate_code_generation_response(self, parsed: Dict[str, Any]) -> None:
        """
        Validate code generation response fields.
        
        Args:
            parsed: Parsed code generation response JSON
            
        Raises:
            ValueError: If validation fails
        """
        decision = parsed.get('decision')
        if decision not in ['continue', 'request_modification']:
            raise ValueError(
                f"Invalid decision value: {decision}. "
                "Must be 'continue' or 'request_modification'"
            )
    
    async def _prepare_code_generation_prompt(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        conversation_history: List[Dict[str, str]] = None,
        attempt: int = 1,
        failures: Optional[List[str]] = None
    ) -> str:
        """
        Prepare prompt for code generation with conversation history
        
        Args:
            step: Step to generate code for
            state: Current game state
            conversation_history: Previous attempts and errors
            attempt: Current attempt number (1-indexed)
            failures: List of previous failure messages
        
        Returns:
            Formatted prompt string
        """
        # Get current game state
        state = await self.shared_state.get_all()
        
        # Get step description
        step_description = step.get('description', 'No description')
        
        # Prepare execution context for prompt injection
        execution_context = f"This is attempt #{attempt}"
        if failures:
            execution_context += f"\n\nPrevious failures ({len(failures)} total):\n"
            for i, failure in enumerate(failures, 1):
                # Handle both old string format and new dict format
                if isinstance(failure, dict):
                    execution_context += f"\nAttempt #{failure.get('attempt', i)}:\n"
                    execution_context += f"  Error: {failure.get('error', 'Unknown error')}\n"
                    if failure.get('code'):
                        # Truncate code if too long
                        code_snippet = failure['code']
                        execution_context += f"  Code that failed:\n{code_snippet}\n"
                else:
                    # Old format: just a string
                    execution_context += f"{i}. {failure}\n"
        
        # Format failure_history for the prompt template
        failure_history_text = ""
        if failures:
            for i, failure in enumerate(failures, 1):
                if isinstance(failure, dict):
                    failure_history_text += f"Attempt {failure.get('attempt', i)}: {failure.get('error', 'Unknown')}\n"
                else:
                    failure_history_text += f"{i}. {failure}\n"
        else:
            failure_history_text = "No previous failures"
        
        # Get task source and player info
        active_task = await self.shared_state.get('active_task')
        task_source = active_task.get('source', 'internal') if active_task else 'internal'
        player_name = active_task.get('player_name') if active_task else None
        
        # Use PromptManager to render code generation prompt
        # All variables auto-resolved from config (including $CODE_DOCS)
        prompt = await self.prompt_manager.render(
            'mid_level/coding.txt',
            context={
                'state': state,
                'memory_manager': self.memory,
                'task_stack_manager': self.shared_state,
                'examples': "",  # Empty for now
                'task': step_description,
                'attempt': str(attempt),
                'failure_history': failure_history_text,
                'execution_context': execution_context,
                'task_source': task_source,
                'player_name': player_name or 'N/A'
            }
        )
        
        # Add conversation history for retry attempts (shows previous failures to LLM)
        # This helps LLM learn from errors and generate corrected code
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
        
        # Check for await statements (code should be async for most operations)
        # Note: We relax this check because some simple synchronous operations are valid
        # The wrapping function is async anyway, so it's fine
        # if 'await ' not in code:
        #     errors.append("Code must contain at least one 'await' statement for async operations")
        
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
    
    def _extract_code_from_field(self, text: str) -> Optional[str]:
        """
        Extract JavaScript code from text that may or may not contain markdown code blocks.
        
        This handles both formats:
        1. Code wrapped in ```javascript or ```js or ``` markers
        2. Plain code without markers
        
        Args:
            text: Text that may contain code (from JSON field or full response)
        
        Returns:
            Extracted JavaScript code or None if no valid code found
        """
        if not text or not text.strip():
            return None
        
        text = text.strip()
        
        # Check if text contains markdown code blocks
        if '```' in text:
            # Extract code from markdown blocks
            parts = text.split('```')
            for i, part in enumerate(parts):
                if i % 2 == 1:  # Odd indices are code blocks
                    code = part.strip()
                    # Remove language identifier if present
                    if code.startswith('javascript') or code.startswith('js'):
                        # Split by newline and take everything after language identifier
                        lines = code.split('\n', 1)
                        code = lines[1] if len(lines) > 1 else ''
                    
                    code = code.strip()
                    if code:  # Found non-empty code
                        return code
            
            # No valid code found in markdown blocks
            logger.warning("Found ``` markers but no valid code block")
            return None
        else:
            return text
    
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
            timeout = 120  # 120 seconds timeout
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
        await self.shared_state.update('is_executing', True)
        
        try:
            chat_result = await self._process_chat_message(player, message)
            
            if chat_result.get('message'):
                await self._send_chat_response(chat_result['message'], player)
                # Store chat history
                self.chat_manager.add_chat(player, message, chat_result['message'])
                
                # Update player description if provided
                player_description = chat_result.get('update_player_description')
                if player_description and isinstance(player_description, str) and player_description.strip():
                    self.memory.log("interaction", f"与 {player} 交流，印象: {player_description}")
                    logger.info(f"Updated player description for {player}")
            
            task_desc = chat_result.get('task')
            logger.debug(f"Task field value: {repr(task_desc)}, type: {type(task_desc)}")
            if task_desc and task_desc.strip().lower() != 'none':
                logger.info(f"Chat contains task request: {task_desc}")
                await self._request_modification(
                    'player_directive',
                    reason=f"Player {player} requested: {message}",
                    player_name=player,
                    directive=task_desc
                )
                logger.info(f"Requested high-level evaluation for player directive: {task_desc}")
        
        except Exception as e:
            logger.error(f"Error handling chat: {e}", exc_info=True)
            # Send fallback response
            await self._send_chat_response("Sorry, I had trouble understanding that. Can you try again?", player)
        
        finally:
            self.is_executing = False
            await self.shared_state.update('is_executing', False)
    
    async def _process_chat_message(self, player: str, message: str) -> Dict[str, Any]:
        """
        Process chat message and extract response + potential task
        
        Uses unified chat_handler.txt prompt to get both message and task in one LLM call.
        
        Args:
            player: Player name
            message: Chat message
        
        Returns:
            Dict with 'message' (response text) and 'task' (task description or None)
        """
        try:
            # Refresh game state
            await self._refresh_game_state()
            await asyncio.sleep(0.15)
            
            # Get current state
            state = await self.shared_state.get_all()
            
            prompt = await self.prompt_manager.render(
                'mid_level/chat_handler.txt',
                context={
                    'state': state,
                    'memory_manager': self.memory,
                    'chat_manager': self.chat_manager,
                    'agent_name': self.config.get('agent_name', 'BrainyBot'),
                    'player': player,
                    'player_name': player,
                    'message': message
                }
            )
            
            # Log prompt before sending
            prompt_file = self.prompt_logger.log_prompt(
                prompt=prompt,
                brain_layer="mid",
                prompt_type="chat_handler",
                metadata={
                    "player_name": player,
                    "message": message
                }
            )
            logger.debug(f"Chat prompt saved to: {prompt_file}")
            
            response = await self.llm.send_request([], prompt)
            response_text = response.strip()
            
            # Update with response
            self.prompt_logger.update_response(prompt_file, response)
            
            # DEBUG: Log raw LLM response
            logger.debug(f"LLM raw response: {response_text[:300]}")
            
            # Parse JSON using robust parser
            try:
                result = parse_chat_response(response_text)
            except ValueError as e:
                logger.error(f"Failed to parse chat response: {e}")
                logger.debug(f"Response was: {response_text[:500]}")
                result = {
                    'message': "Sorry, I had trouble processing that. Can you rephrase?",
                    'task': None,
                    'update_player_description': None
                }
            
            logger.info(f"Parsed chat result: message='{result['message'][:50]}...', task={repr(result['task'])}, player_update={bool(result['update_player_description'])}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing chat message: {e}", exc_info=True)
            return {
                'message': "Oops, something went wrong in my brain. What were we talking about?",
                'task': None,
                'update_player_description': None
            }
    
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