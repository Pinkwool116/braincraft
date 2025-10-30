"""
Task Decomposer

Decomposes high-level goals into step-by-step task sequences.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TaskDecomposer:
    """
    Task decomposer for breaking down goals into tasks
    
    Uses mid-level LLM to decompose complex goals.
    """
    
    def __init__(self, llm):
        """
        Initialize task decomposer
        
        Args:
            llm: LLM instance for task decomposition
        """
        self.llm = llm
        logger.info("Task decomposer initialized")
    
    async def decompose(self, goal: str, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Decompose goal into task sequence
        
        Args:
            goal: High-level goal (e.g., "Build a house")
            context: Current game context (inventory, position, etc.)
            
        Returns:
            List of task dictionaries
        """
        logger.info(f"Decomposing goal: {goal}")
        
        # Build decomposition prompt
        prompt = self._build_decomposition_prompt(goal, context)
        
        try:
            # Call LLM to generate task sequence
            response = await self.llm.send_request([], prompt)
            
            # Parse JSON response
            import json
            if '```json' in response:
                json_start = response.find('```json') + 7
                json_end = response.find('```', json_start)
                json_str = response[json_start:json_end].strip()
            elif '[' in response:
                json_start = response.find('[')
                json_end = response.rfind(']') + 1
                json_str = response[json_start:json_end]
            else:
                json_str = response
            
            tasks = json.loads(json_str)
            
            # Add metadata to each task
            for task in tasks:
                task['type'] = task.get('type', 'strategic')
                task['retry_count'] = 0
            
            logger.info(f"Decomposed into {len(tasks)} tasks")
            return tasks
            
        except Exception as e:
            logger.error(f"Error decomposing goal: {e}")
            return []
    
    def _build_decomposition_prompt(self, goal: str, context: Dict[str, Any] = None) -> str:
        """Build prompt for goal decomposition"""
        
        inventory = context.get('inventory', {}) if context else {}
        position = context.get('position', {}) if context else {}
        
        prompt = f"""Decompose this Minecraft goal into a sequence of tasks.

Goal: {goal}

Current Context:
- Position: x:{position.get('x', 0)}, y:{position.get('y', 0)}, z:{position.get('z', 0)}
- Inventory: {', '.join([f'{k}: {v}' for k, v in list(inventory.items())[:5]]) or 'Empty'}

Break down the goal into specific, actionable tasks. Each task should be concrete and achievable.

Examples:
Goal: "Build a wooden house"
Tasks:
[
  {{"description": "collect 64 oak logs", "type": "collect"}},
  {{"description": "craft oak planks from logs", "type": "craft"}},
  {{"description": "craft crafting table", "type": "craft"}},
  {{"description": "place crafting table", "type": "place"}},
  {{"description": "craft wooden planks into building materials", "type": "craft"}},
  {{"description": "build house structure", "type": "build"}}
]

Goal: "{goal}"
Tasks (respond with JSON array only):"""
        
        return prompt
    
    def validate_tasks(self, tasks: List[Dict[str, Any]]) -> bool:
        """
        Validate task sequence
        
        Args:
            tasks: List of tasks to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not tasks or not isinstance(tasks, list):
            return False
        
        valid_types = ['collect', 'craft', 'build', 'place', 'go', 'attack', 'chat', 'strategic']
        
        for task in tasks:
            # Check has description
            if 'description' not in task:
                logger.warning(f"Task missing description: {task}")
                return False
            
            # Check type if specified
            task_type = task.get('type')
            if task_type and task_type not in valid_types:
                logger.warning(f"Invalid task type: {task_type}")
                return False
        
        return True
