"""
Task Planner

Responsible for decomposing goals into a sequence of steps using an LLM.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from prompts.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

class TaskPlanner:
    def __init__(self, llm, memory_manager, shared_state, prompt_logger=None):
        self.llm = llm
        self.memory_manager = memory_manager
        self.shared_state = shared_state
        self.prompt_logger = prompt_logger  # Optional prompt logger
        
        # Initialize PromptManager
        self.prompt_manager = PromptManager()

    async def decompose_goal_to_steps(self, goal: str, strategic_guidance: str, source: str, player_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Uses an LLM to decompose a high-level goal into a structured task plan.
        Returns None if decomposition fails or results in no valid steps.
        """
        logger.info("Decomposing goal: %s", goal)
        
        # Get current game state
        state = await self.shared_state.get_all()
        
        # Use PromptManager to render decomposition prompt
        # All game state variables ($STATS, $INVENTORY, $NAME, etc.) are auto-resolved from state
        prompt = await self.prompt_manager.render(
            'task_stack/task_decomposition.txt',
            context={
                'state': state,
                'memory_manager': self.memory_manager,
                'goal': goal,
                'strategic_guidance': strategic_guidance or 'None'
            }
        )
        
        try:
            # Log prompt if logger available
            if self.prompt_logger:
                prompt_file = self.prompt_logger.log_prompt(
                    prompt=prompt,
                    brain_layer="high",
                    prompt_type="task_decomposition",
                    metadata={
                        "goal": goal,
                        "source": source,
                        "player_name": player_name
                    }
                )
                logger.debug(f"Task decomposition prompt saved to: {prompt_file}")
            
            response_json = await self.llm.send_request([], prompt)
            
            # Update with response
            if self.prompt_logger and 'prompt_file' in locals():
                self.prompt_logger.update_response(prompt_file, response_json)
            
            parsed_response = self._parse_llm_json(response_json)
            
            if not parsed_response or 'steps' not in parsed_response:
                logger.error("Failed to decompose goal: LLM response was invalid.")
                return None
            
            steps = parsed_response['steps']
            if not steps or len(steps) == 0:
                logger.error(f"Failed to decompose goal '{goal}': LLM returned empty steps array.")
                return None

            task_plan = self._build_task_plan(
                goal=goal,
                steps=steps,
                source=source,
                player_name=player_name,
                strategic_guidance=strategic_guidance
            )
            
            # Validate that normalization didn't filter out all steps
            if not task_plan.get('steps') or len(task_plan['steps']) == 0:
                logger.error(f"Failed to decompose goal '{goal}': All steps were filtered out during normalization.")
                return None
            
            logger.info(f"Successfully decomposed goal into {len(task_plan['steps'])} steps")
            return task_plan
            
        except Exception as e:
            logger.error("Error during goal decomposition: %s", e, exc_info=True)
            return None

    def _build_task_plan(self, goal: str, steps: List[Dict[str, Any]], source: str, player_name: Optional[str], strategic_guidance: str) -> Dict[str, Any]:
        """Constructs a standardized task plan dictionary."""
        # This logic is moved from high_level_brain
        normalized_steps = self._normalize_steps(steps)
        
        return {
            'goal': goal,
            'steps': normalized_steps,
            'status': 'active',
            'current_step_index': 0,
            'source': source,
            'player_name': player_name,
            'strategic_guidance': strategic_guidance,
            'created_at': datetime.now().isoformat(),
        }

    def _normalize_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensures all steps have required fields (id, status, etc.)."""
        # This logic is moved from high_level_brain
        normalized = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or 'description' not in step:
                logger.warning("Skipping invalid step during normalization: %s", step)
                continue
            
            normalized.append({
                'id': i + 1,
                'description': step['description'],
                'status': 'pending',
                'failures': [],
            })
        return normalized

    def format_task_plan_for_prompt(self, task_plan: Optional[Dict[str, Any]] = None) -> str:
        """Format a task plan for inclusion in prompts."""

        plan = task_plan
        if not plan or not plan.get('steps'):
            return "No active task plan."

        goal = plan.get('goal', 'Unknown')
        current_idx = plan.get('current_step_index', 0)
        steps = plan.get('steps', [])
        source = plan.get('source', 'internal')
        status = plan.get('status', 'idle')

        lines = [
            f"Goal: {goal}",
            f"Source: {source}",
            f"Status: {status}",
            f"Progress: Step {min(current_idx + 1, len(steps) if steps else 1)}/{len(steps)}",
            ""
        ]

        for idx, step in enumerate(steps):
            step_status = step.get('status', 'pending')
            if step_status == 'completed':
                marker = '✓'
            elif step_status == 'failed':
                marker = '✗'
            elif idx == current_idx and step_status in ('pending', 'in_progress'):
                marker = '→'
            else:
                marker = '○'
            desc = step.get('description', '')
            lines.append(f"{marker} Step {idx + 1}: {desc} [{step_status}]")

        return "\n".join(lines)

    def _parse_llm_json(self, json_string: str) -> Optional[Dict[str, Any]]:
        """Safely parses a JSON string from an LLM response."""
        try:
            # Clean up the string first
            if "```json" in json_string:
                json_string = json_string.split("```json")[1].split("```")[0]
            
            return json.loads(json_string)
        except (json.JSONDecodeError, IndexError) as e:
            logger.error("Failed to parse LLM JSON response: %s\nResponse: %s", e, json_string)
            return None

import json
