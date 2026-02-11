"""
Self-Awareness System
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class SelfAwareness:
    """
    Agent's self-perception and identity
    
    Tracks:
    - Identity (dynamic name from game, personality traits)
    - Skill self-assessment
    - Relationships with others
    """
    
    def __init__(self, shared_state, memory_manager):
        """
        Initialize self-awareness
        
        Args:
            shared_state: SharedState instance
            memory_manager: MemoryManager instance
        """
        self.shared_state = shared_state
        self.memory = memory_manager
    
    async def get_name(self) -> str:
        """Get agent's name from shared state (game username)"""
        name = await self.shared_state.get('agent_name')
        return name if name else 'Unknown'
    
    async def get_full_context(self) -> str:
        """Get complete self-awareness context for prompts"""
        # TODO
        context = ""
        return context
    def to_dict(self) -> Dict:
        """Convert to dictionary for persistence"""
        # Currently no persistent fields
        return {}
    
    def from_dict(self, data: Dict):
        """Load from dictionary"""
        # Currently no persistent fields
        pass