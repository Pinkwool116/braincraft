"""
Mental State System
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class MentalState:
    """
    Tracks agent's mental and emotional state
    """
    
    def __init__(self, shared_state):
        """
        Initialize mental state
        
        Args:
            shared_state: SharedState instance
        """
        self.shared_state = shared_state
    
    def get_context_for_prompt(self) -> str:
        """Generate context for LLM prompts"""
        context = ""
        return context
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for saving"""
        # Currently no persistent fields
        return {}
    
    def from_dict(self, data: Dict):
        """Load from dictionary"""
        # Currently no persistent fields
        pass
