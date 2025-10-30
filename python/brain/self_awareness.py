"""
Self-Awareness System

Manages agent's self-perception, identity, and relationships
Name is dynamically retrieved from shared state
"""

import logging
from typing import Dict, Any, List, Optional

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
        
        # Identity (name comes from shared_state)
        self.identity = {
            'personality_traits': [],  # e.g., "curious", "cautious", "bold"
            'self_description': None,  # How I see myself
            'values': []  # What I care about
        }
        
        # Skill self-assessment
        self.skill_assessment = {
            'mining': {'level': 'beginner', 'confidence': 0.5, 'notes': []},
            'building': {'level': 'beginner', 'confidence': 0.5, 'notes': []},
            'combat': {'level': 'beginner', 'confidence': 0.5, 'notes': []},
            'farming': {'level': 'beginner', 'confidence': 0.5, 'notes': []},
            'exploration': {'level': 'beginner', 'confidence': 0.5, 'notes': []},
            'social': {'level': 'beginner', 'confidence': 0.5, 'notes': []}
        }
        
        # Relationship tracking (beyond what memory_manager has)
        self.relationships = {}
        # Format: {
        #     'player_name': {
        #         'trust_level': 0.5,  # 0-1
        #         'relationship_type': 'friend'/'ally'/'neutral'/'rival',
        #         'first_met_days': game_days,
        #         'last_interaction_days': game_days,
        #         'significant_moments': []
        #     }
        # }
    
    async def get_name(self) -> str:
        """Get agent's name from shared state (game username)"""
        name = await self.shared_state.get('agent_name')
        return name if name else 'Unknown'
    
    def add_personality_trait(self, trait: str):
        """Add a personality trait"""
        if trait not in self.identity['personality_traits']:
            self.identity['personality_traits'].append(trait)
            logger.info(f"💭 Personality trait added: {trait}")
    
    def set_self_description(self, description: str):
        """Set how the agent sees itself"""
        self.identity['self_description'] = description
        logger.info(f"💭 Self-description updated: {description}")
    
    def add_value(self, value: str):
        """Add a core value"""
        if value not in self.identity['values']:
            self.identity['values'].append(value)
            logger.info(f"💭 Core value added: {value}")
    
    def update_skill(
        self, 
        skill: str, 
        level: Optional[str] = None,
        confidence: Optional[float] = None,
        note: Optional[str] = None
    ):
        """
        Update skill self-assessment
        
        Args:
            skill: Skill name (mining, building, etc.)
            level: 'beginner'/'intermediate'/'advanced'/'expert'
            confidence: 0-1 confidence level
            note: Note about this update
        """
        if skill not in self.skill_assessment:
            logger.warning(f"Unknown skill: {skill}")
            return
        
        if level:
            old_level = self.skill_assessment[skill]['level']
            self.skill_assessment[skill]['level'] = level
            if old_level != level:
                logger.info(f"📈 Skill level up: {skill} {old_level} → {level}")
        
        if confidence is not None:
            self.skill_assessment[skill]['confidence'] = max(0.0, min(1.0, confidence))
        
        if note:
            self.skill_assessment[skill]['notes'].append(note)
            # Keep only recent notes
            if len(self.skill_assessment[skill]['notes']) > 10:
                self.skill_assessment[skill]['notes'] = self.skill_assessment[skill]['notes'][-10:]
    
    def update_relationship(
        self,
        player_name: str,
        trust_delta: Optional[float] = None,
        relationship_type: Optional[str] = None,
        significant_moment: Optional[str] = None
    ):
        """
        Update relationship with a player
        
        Args:
            player_name: Player's name
            trust_delta: Change in trust (-1 to 1)
            relationship_type: New relationship type
            significant_moment: Notable event in relationship
        """
        current_days = self.shared_state.get('agent_age_days', 0)
        
        # Initialize if first time
        if player_name not in self.relationships:
            self.relationships[player_name] = {
                'trust_level': 0.5,
                'relationship_type': 'neutral',
                'first_met_days': current_days,
                'last_interaction_days': current_days,
                'significant_moments': []
            }
        
        rel = self.relationships[player_name]
        
        # Update trust
        if trust_delta is not None:
            old_trust = rel['trust_level']
            rel['trust_level'] = max(0.0, min(1.0, rel['trust_level'] + trust_delta))
            
            if abs(rel['trust_level'] - old_trust) > 0.2:
                logger.info(f"👥 Trust change with {player_name}: {old_trust:.2f} → {rel['trust_level']:.2f}")
        
        # Update relationship type
        if relationship_type:
            if rel['relationship_type'] != relationship_type:
                logger.info(f"👥 Relationship with {player_name}: {rel['relationship_type']} → {relationship_type}")
                rel['relationship_type'] = relationship_type
        
        # Record significant moment
        if significant_moment:
            rel['significant_moments'].append({
                'day': current_days,
                'moment': significant_moment
            })
            # Keep last 20 moments
            if len(rel['significant_moments']) > 20:
                rel['significant_moments'] = rel['significant_moments'][-20:]
        
        # Update last interaction
        rel['last_interaction_days'] = current_days
    
    def get_relationship_summary(self, player_name: str) -> Optional[str]:
        """Get human-readable relationship summary"""
        if player_name not in self.relationships:
            return None
        
        rel = self.relationships[player_name]
        current_days = self.shared_state.get('agent_age_days', 0)
        days_since_meeting = current_days - rel['first_met_days']
        days_since_interaction = current_days - rel['last_interaction_days']
        
        summary = f"Relationship with {player_name}:\n"
        summary += f"Type: {rel['relationship_type']}\n"
        summary += f"Trust: {rel['trust_level']:.2f}\n"
        summary += f"Known for: {days_since_meeting} days\n"
        summary += f"Last interaction: {days_since_interaction} days ago\n"
        
        if rel['significant_moments']:
            summary += "Recent moments:\n"
            for moment in rel['significant_moments'][-3:]:
                summary += f"  - Day {moment['day']}: {moment['moment']}\n"
        
        return summary
    
    async def get_identity_context(self) -> str:
        """Generate identity context for LLM prompts"""
        name = await self.get_name()
        
        context = f"YOUR IDENTITY:\n"
        context += f"Name: {name}\n"
        
        if self.identity['self_description']:
            context += f"Self-view: {self.identity['self_description']}\n"
        
        if self.identity['personality_traits']:
            context += f"Traits: {', '.join(self.identity['personality_traits'])}\n"
        
        if self.identity['values']:
            context += f"Values: {', '.join(self.identity['values'])}\n"
        
        context += "\n"
        return context
    
    def get_skills_context(self) -> str:
        """Generate skills context for LLM prompts"""
        context = "YOUR SKILLS:\n"
        
        for skill, data in self.skill_assessment.items():
            context += f"- {skill.capitalize()}: {data['level']} (confidence: {data['confidence']:.1f})\n"
        
        context += "\n"
        return context
    
    def get_relationships_context(self) -> str:
        """Generate relationships context for LLM prompts"""
        if not self.relationships:
            return ""
        
        context = "YOUR RELATIONSHIPS:\n"
        
        # Sort by last interaction (most recent first)
        sorted_rels = sorted(
            self.relationships.items(),
            key=lambda x: x[1]['last_interaction_days'],
            reverse=True
        )
        
        for player_name, rel in sorted_rels[:5]:  # Top 5 recent
            context += f"- {player_name}: {rel['relationship_type']} (trust: {rel['trust_level']:.1f})\n"
        
        context += "\n"
        return context
    
    async def get_full_context(self) -> str:
        """Get complete self-awareness context for prompts"""
        context = await self.get_identity_context()
        context += self.get_skills_context()
        context += self.get_relationships_context()
        return context
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for saving"""
        return {
            'identity': self.identity,
            'skill_assessment': self.skill_assessment,
            'relationships': self.relationships
        }
    
    def from_dict(self, data: Dict):
        """Load from dictionary"""
        self.identity = data.get('identity', self.identity)
        self.skill_assessment = data.get('skill_assessment', self.skill_assessment)
        self.relationships = data.get('relationships', {})
