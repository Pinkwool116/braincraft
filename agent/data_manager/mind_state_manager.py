"""
Mind State Manager

Manages persistent storage of the agent's mind state including:
- Goal hierarchy
- Self-awareness
- Mental state
- Task stack

This data is stored in mind_state.json
"""

import json
import os
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MindStateManager:
    """
    Manages the persistence of mind state to mind_state.json
    
    This is separate from MemoryRouter which handles:
    - Five-layer memory (semantic, spatial, episodic, social, self-narrative)
    """
    
    def __init__(self, agent_name: str = "BrainyBot"):
        """
        Initialize mind state manager
        
        Args:
            agent_name: Name of the agent (for file paths)
        """
        self.agent_name = agent_name
        self.base_dir = os.path.join("bots", agent_name)
        
        # Create directory if needed
        os.makedirs(self.base_dir, exist_ok=True)
        
        # File path
        self.state_file = os.path.join(self.base_dir, "mind_state.json")
        
        logger.info(f"Mind state manager initialized for agent: {agent_name}")
    
    def load_mind_state(self) -> Dict[str, Any]:
        """
        Load complete mind state from disk
        
        Returns:
            Dictionary containing mind state, or empty dict if file doesn't exist
        """
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug("Loaded mind state from disk")
                return data
            except Exception as e:
                logger.error(f"Failed to load mind state: {e}")
                return {}
        else:
            logger.info("No mind_state.json found - will create on first save")
            return {}
    
    def save_mind_state(self, state_data: Dict[str, Any]):
        """
        Save complete mind state to disk
        
        Args:
            state_data: Complete mind state dictionary to save
        """
        try:
            # Add timestamp
            state_data['saved_at'] = datetime.now().isoformat()
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            logger.debug("Saved mind state to disk")
        except Exception as e:
            logger.error(f"Failed to save mind state: {e}")
    
    def update_mind_state_field(self, field_name: str, field_value: Any):
        """
        Update a specific field in the mind state
        
        This is useful for updating individual components (like task_stack)
        without having to rebuild the entire state dictionary.
        
        Args:
            field_name: Name of the field to update (e.g., 'task_stack')
            field_value: New value for the field
        """
        try:
            # Load current state
            current_state = self.load_mind_state()
            
            # Update the specific field
            current_state[field_name] = field_value
            
            # Save back
            self.save_mind_state(current_state)
            logger.debug(f"Updated mind state field: {field_name}")
        except Exception as e:
            logger.error(f"Failed to update mind state field {field_name}: {e}")
    
    def get_mind_state_field(self, field_name: str, default: Any = None) -> Any:
        """
        Get a specific field from the mind state
        
        Args:
            field_name: Name of the field to retrieve
            default: Default value if field doesn't exist
        
        Returns:
            Field value or default
        """
        state = self.load_mind_state()
        return state.get(field_name, default)
