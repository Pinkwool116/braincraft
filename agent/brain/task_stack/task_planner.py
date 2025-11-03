"""
Task Planner

Responsible for decomposing goals into a sequence of steps using an LLM.
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from utils.game_state_formatter import GameStateFormatter

logger = logging.getLogger(__name__)

class TaskPlanner:
    def __init__(self, llm, memory_manager, shared_state):
        self.llm = llm
        self.memory_manager = memory_manager
        self.shared_state = shared_state

    async def decompose_goal_to_steps(self, goal: str, strategic_guidance: str, source: str, player_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Uses an LLM to decompose a high-level goal into a structured task plan.
        Returns None if decomposition fails or results in no valid steps.
        """
        logger.info("Decomposing goal: %s", goal)
        
        # Get current game state and agent info
        state = await self.shared_state.get_all()
        agent_name = state.get('agent_name', 'BrainyBot')
        
        # Get learned experience and lessons
        learned_experience = self._get_learned_experience()
        lessons_learned = self._get_lessons_learned()
        
        prompt = self._build_decomposition_prompt(
            goal, 
            strategic_guidance, 
            state, 
            agent_name,
            learned_experience,
            lessons_learned
        )
        
        try:
            response_json = await self.llm.send_request([], prompt)
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
    
    def _get_learned_experience(self) -> str:
        """Get accumulated knowledge from memory."""
        insights = self.memory_manager.learned_experience.get('insights', [])
        if not insights:
            return "No accumulated experience yet."
        
        lines = []
        # Get last 10 insights
        for exp in insights[-10:]:
            summary = exp.get('summary', '')
            if summary:
                lines.append(f"- {summary}")
        return "\n".join(lines) if lines else "No accumulated experience yet."
    
    def _get_lessons_learned(self) -> str:
        """Get lessons learned from memory."""
        lessons = self.memory_manager.learned_experience.get('lessons_learned', [])
        if not lessons:
            return "No lessons learned yet."
        
        lines = []
        # Get last 10 lessons
        for lesson in lessons[-10:]:
            lesson_text = lesson.get('lesson', '')
            context = lesson.get('context', '')
            if lesson_text:
                if context:
                    lines.append(f"- {lesson_text} (Context: {context})")
                else:
                    lines.append(f"- {lesson_text}")
        return "\n".join(lines) if lines else "No lessons learned yet."

    def _build_decomposition_prompt(
        self, 
        goal: str, 
        strategic_guidance: str,
        state: Dict[str, Any],
        agent_name: str,
        learned_experience: str,
        lessons_learned: str
    ) -> str:
        """Builds the prompt for the LLM to decompose a goal."""
        
        # Get formatted game state details
        stats = GameStateFormatter.format_stats(state)
        inventory = GameStateFormatter.format_inventory(state)
        equipment = GameStateFormatter.format_equipment(state)
        biome = state.get('biome', 'Unknown')
        time_of_day = state.get('time_of_day', 'Unknown')
        world_day = state.get('world_day', 0)
        weather = state.get('weather', 'Unknown')
        block_below = state.get('block_below', 'Unknown')
        block_legs = state.get('block_at_legs', 'Unknown')
        block_head = state.get('block_at_head', 'Unknown')
        block_above = state.get('block_above', 'Unknown')
        nearby_blocks = GameStateFormatter.format_nearby_blocks(state)
        nearby_entities = GameStateFormatter.format_nearby_entities(state)
        
        return f"""
You are a master planner for {agent_name}, a Minecraft agent. Decompose the following goal into a sequence of concrete, actionable steps.

## Current Game State

### Bot Status
{stats}

### Inventory
{inventory}

### Equipment
{equipment}

### Environment
Biome: {biome}
Time of Day: {time_of_day}
World Day: {world_day}
Weather: {weather}

### Immediate Surroundings
Block Below (at feet): {block_below}
Block at Legs: {block_legs}
Block at Head: {block_head}
First Solid Block Above: {block_above}

### Nearby Blocks (within 3x3x3)
{nearby_blocks}

### Nearby Entities (within 16 blocks)
{nearby_entities}

## Your Experience

### Accumulated Knowledge
{learned_experience}

### Lessons Learned
{lessons_learned}

## Task to Decompose

GOAL: {goal}

STRATEGIC GUIDANCE: {strategic_guidance or 'None'}

## Instructions

Decompose the goal into 3-12 concrete, actionable steps. Consider your current inventory, surroundings, and learned experience when planning.

Respond with a JSON object containing a "steps" array. Each step must be a dictionary with a "description" field.
Example:
{{
  "steps": [
    {{ "description": "Find and chop down a tree to get 3 oak logs." }},
    {{ "description": "Next step." }},
    ...
  ]
}}

CRITICAL RULES:
- 3 to 12 concise steps.
- Each step MUST be completable and have a clear end condition.
- DO NOT create ongoing/continuous tasks (e.g., "stay alert for zombies", "keep exploring forever", "always watch for danger").
- Focus on concrete, achievable actions with measurable outcomes.
- Keep steps simple and focused on a single action.
- Consider your current inventory - use items you already have.
- Consider your surroundings - use nearby resources when possible.
- Learn from past lessons - avoid repeating failed approaches.
- Do not number inside the description text.
- The response must be ONLY the JSON object.

EXAMPLES OF BAD STEPS (never finishable or too vague):
❌ "Stay vigilant for hostile mobs"
❌ "Keep exploring the area"
❌ "Maintain awareness of surroundings"
❌ "Be prepared for combat"

EXAMPLES OF GOOD STEPS (concrete and achievable):
✓ "Collect 10 pieces of wood by chopping trees"
✓ "Craft a stone pickaxe using 3 cobblestone and 2 sticks"
✓ "Mine 5 iron ore blocks from the nearby cave"
✓ "Build a 5x5x4 shelter with 4 walls and a roof"
"""

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
