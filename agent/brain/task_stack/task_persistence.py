"""
Task Persistence Handler

Handles saving and loading the task stack to/from a file.
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TaskPersistence:
    def __init__(self, mind_state_manager):
        """
        Initialize task persistence handler
        
        Args:
            mind_state_manager: Instance of MindStateManager for accessing mind_state.json
        """
        self.mind_state_manager = mind_state_manager

    def save_state(self, task_stack: List[Dict[str, Any]]):
        """Saves the entire task stack to the mind_state.json file."""
        try:
            self.mind_state_manager.update_mind_state_field('task_stack', task_stack)
            logger.debug("Task stack state persisted.")
        except Exception as e:
            logger.error("Failed to save task stack state: %s", e, exc_info=True)

    def load_state(self) -> List[Dict[str, Any]]:
        """Loads the task stack from the mind_state.json file."""
        try:
            return self.mind_state_manager.get_mind_state_field('task_stack', [])
        except Exception as e:
            logger.error("Failed to load task stack state: %s", e, exc_info=True)
            return []
