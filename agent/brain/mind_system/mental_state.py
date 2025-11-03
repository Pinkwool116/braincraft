"""
Mental State System

Tracks agent's current mental/emotional state and focus
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class MentalState:
    """
    Tracks agent's mental and emotional state
    
    Includes:
    - Mood/emotional state
    - Current focus and attention
    - Stress/fatigue levels
    - Pending thoughts and reflections
    """
    
    def __init__(self, shared_state):
        """
        Initialize mental state
        
        Args:
            shared_state: SharedState instance
        """
        self.shared_state = shared_state
        
        # Mood/emotional state
        self.mood = {
            'satisfaction': 0.5,  # 0-1: How satisfied with current state
            'stress': 0.0,        # 0-1: Stress level
            'excitement': 0.5,    # 0-1: Excitement/interest level
            'loneliness': 0.5,    # 0-1: Social connection need
        }
        
        # Current focus
        self.focus = {
            'current_priority': None,  # What's most important right now
            'attention_on': None,      # What we're actively thinking about
            'distractions': [],        # Things competing for attention
            'pending_reflections': []  # Thoughts to process later
        }
    
    def update_mood(
        self,
        satisfaction: Optional[float] = None,
        stress: Optional[float] = None,
        excitement: Optional[float] = None,
        loneliness: Optional[float] = None
    ):
        """Update mood parameters"""
        if satisfaction is not None:
            self.mood['satisfaction'] = max(0.0, min(1.0, satisfaction))
        if stress is not None:
            self.mood['stress'] = max(0.0, min(1.0, stress))
        if excitement is not None:
            self.mood['excitement'] = max(0.0, min(1.0, excitement))
        if loneliness is not None:
            self.mood['loneliness'] = max(0.0, min(1.0, loneliness))
    
    def set_focus(self, priority: str, attention_on: Optional[str] = None):
        """Set current mental focus"""
        self.focus['current_priority'] = priority
        if attention_on:
            self.focus['attention_on'] = attention_on
        
        logger.info(f"🎯 Focus: {priority}")
    
    def add_distraction(self, distraction: str):
        """Add something competing for attention"""
        self.focus['distractions'].append(distraction)
        # Keep only recent distractions
        if len(self.focus['distractions']) > 5:
            self.focus['distractions'] = self.focus['distractions'][-5:]
    
    def clear_focus(self):
        """Clear current focus (free attention)"""
        self.focus['current_priority'] = None
        self.focus['attention_on'] = None
        self.focus['distractions'] = []
    
    def add_pending_reflection(self, thought: str):
        """Add a thought to process later"""
        self.focus['pending_reflections'].append(thought)
        # Keep only recent pending thoughts
        if len(self.focus['pending_reflections']) > 20:
            self.focus['pending_reflections'] = self.focus['pending_reflections'][-20:]
    
    def get_pending_reflections(self, clear: bool = True) -> List[str]:
        """Get and optionally clear pending reflections"""
        reflections = self.focus['pending_reflections'].copy()
        if clear:
            self.focus['pending_reflections'] = []
        return reflections
    
    def get_mental_state_summary(self) -> str:
        """Get human-readable mental state summary"""
        summary = "MENTAL STATE:\n"
        summary += f"Satisfaction: {self.mood['satisfaction']:.2f}\n"
        summary += f"Stress: {self.mood['stress']:.2f}\n"
        summary += f"Excitement: {self.mood['excitement']:.2f}\n"
        
        if self.focus['current_priority']:
            summary += f"\nFocus: {self.focus['current_priority']}\n"
        
        if self.focus['distractions']:
            summary += f"Distractions: {len(self.focus['distractions'])}\n"
        
        if self.focus['pending_reflections']:
            summary += f"Pending thoughts: {len(self.focus['pending_reflections'])}\n"
        
        return summary
    
    def get_context_for_prompt(self) -> str:
        """Generate context for LLM prompts"""
        context = ""
        
        # Only include if relevant
        if self.focus['current_priority']:
            context += f"Current priority: {self.focus['current_priority']}\n"
        
        if self.mood['stress'] > 0.6:
            context += f"(Feeling stressed: {self.mood['stress']:.1f})\n"
        
        if self.mood['satisfaction'] < 0.3:
            context += "(Feeling unsatisfied with current progress)\n"
        
        if self.focus['pending_reflections']:
            context += f"({len(self.focus['pending_reflections'])} thoughts to process later)\n"
        
        return context
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for saving"""
        return {
            'mood': self.mood,
            'focus': self.focus
        }
    
    def from_dict(self, data: Dict):
        """Load from dictionary"""
        self.mood = data.get('mood', self.mood)
        self.focus = data.get('focus', self.focus)
