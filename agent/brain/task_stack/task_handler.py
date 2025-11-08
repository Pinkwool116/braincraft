import logging
from typing import Dict, Any, Optional
import json
from prompts.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class TaskHandler:
    def __init__(self, llm, task_stack_manager, task_planner, memory_manager, chat_manager, prompt_logger=None):
        self.llm = llm
        self.task_stack_manager = task_stack_manager
        self.task_planner = task_planner
        self.memory_manager = memory_manager
        self.chat_manager = chat_manager  # Optional ChatManager for chat context
        self.prompt_logger = prompt_logger  # Optional prompt logger
        
        # Initialize PromptManager
        self.prompt_manager = PromptManager()

    async def handle_stuck_task(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle internal stuck-task requests from the mid-level brain."""

        active_task = self.task_stack_manager.get_active_task()
        if not active_task:
            logger.warning("Received stuck-task request but the task stack is empty")
            return {
                'decision': 'no_change',
                'explanation': 'No active task to modify.',
                'guidance': 'Wait for a new task from the high-level brain.'
            }

        task_source = active_task.get('source', 'internal')
        player_name = active_task.get('player_name')
        step_index = request.get('current_step_index', active_task.get('current_step_index', 0))
        failures = request.get('failures', [])
        suggestion = request.get('suggestion', '')
        reason = request.get('reason', '')

        steps = active_task.get('steps', [])
        failed_step = steps[step_index] if 0 <= step_index < len(steps) else {}

        stack_summary = self.task_stack_manager.generate_task_stack_summary()
        current_plan_text = self.task_planner.format_task_plan_for_prompt(active_task)

        # Build context for stuck task prompt
        context = {
            'memory_manager': self.memory_manager,
            'stack_summary': stack_summary or 'Task stack is empty.',
            'task_source': task_source,
            'current_plan_text': current_plan_text,
            'step_index': str(step_index + 1),
            'failed_step_description': failed_step.get('description', 'Unknown'),
            'reason': reason or 'Not specified',
            'failure_list': self._format_failure_list(failures),
            'suggestion': suggestion or 'None provided'
        }
        
        # Add player context (empty for internal tasks)
        if player_name:
            context['player'] = player_name  # For $PLAYER_INFO variable
            context['player_name'] = player_name  # For $PLAYER_NAME variable
        else:
            context['player'] = None  # Will trigger default in get_player_info
            context['player_name'] = 'N/A (internal task)'
        
        # Use PromptManager to render stuck task handling prompt
        prompt = await self.prompt_manager.render(
            'task_stack/handle_stuck_task.txt',
            context=context
        )

        try:
            # Log prompt if logger available
            if self.prompt_logger:
                prompt_file = self.prompt_logger.log_prompt(
                    prompt=prompt,
                    brain_layer="high",
                    prompt_type="stuck_task_handling",
                    metadata={
                        "task_goal": active_task.get('goal', 'unknown'),
                        "step_index": step_index,
                        "task_source": task_source,
                        "player_name": player_name
                    }
                )
                logger.debug(f"Stuck task handling prompt saved to: {prompt_file}")
            
            decision_payload = await self.llm.send_request([], prompt)
            
            # Update with response
            if self.prompt_logger and 'prompt_file' in locals():
                self.prompt_logger.update_response(prompt_file, decision_payload)
                
        except Exception as exc:
            logger.error("Failed to obtain stuck-task decision from LLM: %s", exc)
            return {
                'decision': 'no_change',
                'explanation': 'LLM decision unavailable.',
                'guidance': suggestion or 'Retry with a slightly different approach.'
            }
        decision_data = self._parse_llm_json(decision_payload)

        decision = decision_data.get('decision', 'REJECT_REQUEST').upper()
        explanation = decision_data.get('explanation', '')
        guidance = decision_data.get('guidance', '')
        player_message = decision_data.get('player_message')
        new_goal = decision_data.get('new_goal', '')
        strategic_guidance = decision_data.get('strategic_guidance', '')

        result_decision = 'no_change'

        # Handle internal tasks
        if task_source == 'internal':
            if decision == 'REVISE_AND_REPLACE':
                goal_text = new_goal or active_task.get('goal')
                logger.info(f"Decomposing revised goal: {goal_text}")
                
                replacement = await self.task_planner.decompose_goal_to_steps(
                    goal=goal_text,
                    strategic_guidance=strategic_guidance or active_task.get('strategic_guidance', ''),
                    source=task_source,
                    player_name=player_name
                )
                
                if replacement:
                    await self.task_stack_manager.replace_active_task(replacement)
                    result_decision = 'updated_task'
                else:
                    logger.error(f"Failed to decompose revised goal: {goal_text}")
                    result_decision = 'no_change'

            elif decision == 'ADD_SUB_TASK':
                sub_goal = new_goal or f"Resolve prerequisite for: {failed_step.get('description', 'current step')}"
                logger.info(f"Decomposing sub-task goal: {sub_goal}")
                
                sub_task = await self.task_planner.decompose_goal_to_steps(
                    goal=sub_goal,
                    strategic_guidance=strategic_guidance,
                    source='internal',
                    player_name=player_name
                )
                
                if sub_task:
                    sub_task['parent_goal'] = active_task.get('goal')
                    await self.task_stack_manager.push_task_plan(sub_task)
                    result_decision = 'pushed_sub_task'
                else:
                    logger.error(f"Failed to decompose sub-task goal: {sub_goal}")
                    result_decision = 'no_change'

            elif decision == 'DISCARD_TASK':
                await self.task_stack_manager.discard_active_task(reason=explanation or guidance)
                result_decision = 'discarded_task'

        # Handle player tasks
        else:
            if decision == 'REVISE_STEPS':
                goal_text = active_task.get('goal')
                logger.info(f"Re-decomposing player task with new guidance: {goal_text}")
                
                revised_plan = await self.task_planner.decompose_goal_to_steps(
                    goal=goal_text,
                    strategic_guidance=strategic_guidance or 'Try a different approach to achieve this goal.',
                    source='player',
                    player_name=player_name
                )
                
                if revised_plan:
                    await self.task_stack_manager.replace_active_task(revised_plan)
                    result_decision = 'updated_task'
                else:
                    logger.error(f"Failed to re-decompose player task: {goal_text}")
                    result_decision = 'no_change'

            elif decision == 'DISCARD_AND_REPORT':
                await self.task_stack_manager.discard_active_task(reason=explanation or guidance)
                if not player_message:
                    player_message = f"Sorry {player_name}, I cannot complete '{active_task.get('goal', 'your request')}'."
                result_decision = 'discarded_task'

            elif decision == 'ADD_SUB_TASK':
                sub_goal = new_goal or f"Prerequisite for player request: {active_task.get('goal')}"
                logger.info(f"Decomposing sub-task for player request: {sub_goal}")
                
                sub_task = await self.task_planner.decompose_goal_to_steps(
                    goal=sub_goal,
                    strategic_guidance=strategic_guidance,
                    source='internal',
                    player_name=player_name
                )
                
                if sub_task:
                    sub_task['parent_goal'] = active_task.get('goal')
                    await self.task_stack_manager.push_task_plan(sub_task)
                    result_decision = 'pushed_sub_task'
                else:
                    logger.error(f"Failed to decompose sub-task: {sub_goal}")
                    result_decision = 'no_change'

        # Fallback guidance
        if not guidance:
            if result_decision == 'pushed_sub_task':
                guidance = 'Execute the newly added prerequisite task first.'
            elif result_decision == 'updated_task':
                guidance = 'Follow the updated task plan.'
            elif result_decision == 'discarded_task':
                guidance = 'Await further instructions from the high-level brain.'
            else:
                guidance = suggestion or 'Retry with a different approach.'

        return {
            'decision': result_decision,
            'explanation': explanation or guidance,
            'guidance': guidance,
            'player_message': player_message,
            'player_name': player_name,
            'task_source': task_source
        }

    async def handle_player_directive(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle new task directives originating from a player."""

        player_name = request.get('player_name') or 'Unknown'
        directive = request.get('directive') or request.get('suggestion') or ''
        if not directive:
            logger.warning("Player directive request missing directive text")
            return {
                'decision': 'reject_player_request',
                'explanation': 'No actionable directive provided.',
                'guidance': 'Politely ask the player to restate their request.'
            }

        stack_summary = self.task_stack_manager.generate_task_stack_summary()
        active_task = self.task_stack_manager.get_active_task()
        current_task_text = self.task_planner.format_task_plan_for_prompt(active_task)

        # Build context for prompt
        context = {
            'memory_manager': self.memory_manager,
            'player': player_name,  # For $PLAYER_INFO variable
            'player_name': player_name,  # For $PLAYER_NAME variable
            'directive': directive,
            'stack_summary': stack_summary or 'Task stack is empty.',
            'current_task_text': current_task_text
        }
        
        # Add chat_manager if available
        if self.chat_manager:
            context['chat_manager'] = self.chat_manager
        
        # Use PromptManager to render player directive handling prompt
        prompt = await self.prompt_manager.render(
            'task_stack/handle_player_directive.txt',
            context=context
        )

        try:
            # Log prompt if logger available
            if self.prompt_logger:
                prompt_file = self.prompt_logger.log_prompt(
                    prompt=prompt,
                    brain_layer="high",
                    prompt_type="player_directive_handling",
                    metadata={
                        "player_name": player_name,
                        "directive": directive
                    }
                )
                logger.debug(f"Player directive handling prompt saved to: {prompt_file}")
            
            decision_payload = await self.llm.send_request([], prompt)
            
            # Update with response
            if self.prompt_logger and 'prompt_file' in locals():
                self.prompt_logger.update_response(prompt_file, decision_payload)
                
        except Exception as exc:
            logger.error("Failed to evaluate player directive via LLM: %s", exc)
            fallback_message = (
                f"Sorry {player_name}, I cannot take on that request right now." if player_name else
                "Sorry, I cannot take on that request right now."
            )
            return {
                'decision': 'rejected_player_task',
                'explanation': 'LLM decision unavailable.',
                'guidance': 'Continue current priorities.',
                'player_message': fallback_message,
                'player_name': player_name
            }
        decision_data = self._parse_llm_json(decision_payload)

        decision = decision_data.get('decision', 'reject').lower()
        reason = decision_data.get('reason', '')
        player_message = decision_data.get('player_message')
        task_goal = decision_data.get('task_goal')
        strategic_guidance = decision_data.get('strategic_guidance', '')

        if decision == 'accept':
            goal_text = task_goal or f"Assist {player_name}: {directive}"
            
            # Always decompose the goal into steps
            logger.info(f"Decomposing accepted player directive: {goal_text}")
            task_plan = await self.task_planner.decompose_goal_to_steps(
                goal=goal_text,
                strategic_guidance=strategic_guidance,
                source='player',
                player_name=player_name
            )
            
            if task_plan:
                await self.task_stack_manager.push_task_plan(task_plan)
                logger.info("Accepted player directive from %s: %s", player_name, goal_text)
            else:
                logger.error("Failed to decompose player directive: %s", goal_text)
                return {
                    'decision': 'rejected_player_task',
                    'explanation': 'Failed to create task plan.',
                    'guidance': 'Continue with current priorities.',
                    'player_message': f"Sorry {player_name}, I couldn't figure out how to do that.",
                    'player_name': player_name
                }

            if not player_message:
                player_message = f"Okay {player_name}, I'll start working on '{goal_text}'."

            return {
                'decision': 'accepted_player_task',
                'explanation': reason or 'Accepted player directive.',
                'guidance': 'Begin executing the newly accepted player task.',
                'player_message': player_message,
                'player_name': player_name
            }

        # Reject path
        if not player_message:
            player_message = (
                f"Sorry {player_name}, I cannot take on that request right now. "
                "I will let you know when I'm available."
            )

        logger.info("Rejected player directive from %s: %s", player_name, directive)

        return {
            'decision': 'rejected_player_task',
            'explanation': reason or 'Rejected player directive.',
            'guidance': reason or 'Continue with current priorities.',
            'player_message': player_message,
            'player_name': player_name
        }

    def _format_failure_list(self, failures: list) -> str:
        if not failures:
            return 'No failure messages provided.'
        return "\n".join(f"- {failure}" for failure in failures[-5:])

    def _parse_llm_json(self, response: str) -> Dict[str, Any]:
        """Extract JSON payload from an LLM response."""
        if not response:
            return {}
        try:
            if '```json' in response:
                start = response.find('```json') + 7
                end = response.find('```', start)
                payload = response[start:end].strip()
            elif '```' in response:
                start = response.find('```') + 3
                end = response.find('```', start)
                payload = response[start:end].strip()
            else:
                start = response.find('{')
                end = response.rfind('}') + 1
                payload = response[start:end]
            return json.loads(payload)
        except Exception as exc:
            logger.error("Failed to parse LLM JSON response: %s", exc)
            logger.debug("LLM response: %s", response)
            return {}
