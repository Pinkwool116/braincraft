"""
Contemplation Manager

Manages idle contemplation: organizing experiences, connecting insights,
and generating new knowledge without relying on game state.
"""

import logging
import random
from typing import Dict, Any, List, Optional
from .config import CONTEMPLATION_CONFIG

logger = logging.getLogger(__name__)


class ContemplationManager:
    """
    Manages high-level brain's idle contemplation.
    
    Contemplation happens when the agent has free time and no urgent tasks.
    It processes internal knowledge without needing external game state.
    """
    
    def __init__(self, memory_manager, llm, mental_state, goal_hierarchy):
        """
        Initialize contemplation manager
        
        Args:
            memory_manager: MemoryManager instance
            llm: LLM model for generating reflections
            mental_state: MentalState instance
            goal_hierarchy: GoalHierarchy instance
        """
        self.memory = memory_manager
        self.llm = llm
        self.mental_state = mental_state
        self.goal_hierarchy = goal_hierarchy
        self.config = CONTEMPLATION_CONFIG
    
    async def contemplate(self) -> bool:
        """
        Perform one cycle of contemplation
        
        Returns:
            Result if contemplation was performed, None if skipped
        """
        
        # Select contemplation mode
        mode = self._select_mode()
        if not mode:
            logger.debug("No suitable contemplation mode available")
            return None
        
        logger.info(f"💭 Beginning contemplation: {mode}")
        
        # Execute contemplation
        try:
            result = await self._execute_mode(mode)
            
            if result:
                logger.info(f"✨ Contemplation complete: {mode}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error during contemplation: {e}", exc_info=True)
            return None
    
    def _select_mode(self) -> Optional[str]:
        """
        Select contemplation mode using weighted random selection
        
        Returns:
            Mode name or None if no suitable mode
        """
        modes = self.config['modes']
        available_modes = []
        weights = []
        
        for mode_name, mode_config in modes.items():
            # Check if mode requirements are met
            if self._check_mode_requirements(mode_name, mode_config):
                available_modes.append(mode_name)
                weights.append(mode_config['weight'])
        
        if not available_modes:
            return None
        
        # Weighted random selection
        selected = random.choices(available_modes, weights=weights, k=1)[0]
        return selected
    
    def _check_mode_requirements(self, mode_name: str, mode_config: Dict) -> bool:
        """Check if a mode's requirements are satisfied"""
        
        # Check minimum experiences
        if 'min_experiences' in mode_config:
            total = len(self.memory.learned_experience.get('insights', []))
            if total < mode_config['min_experiences']:
                return False
        
        # Check minimum insights
        if 'min_insights' in mode_config:
            total = len(self.memory.learned_experience.get('insights', []))
            if total < mode_config['min_insights']:
                return False
        
        # Check relationships requirement
        if mode_config.get('requires_relationships', False):
            if not self.memory.players:
                return False
        
        # Check life events requirement
        if 'min_life_events' in mode_config:
            if hasattr(self.goal_hierarchy, 'life_events'):
                if len(self.goal_hierarchy.life_events) < mode_config['min_life_events']:
                    return False
            else:
                return False
        
        return True
    
    async def _execute_mode(self, mode: str) -> bool:
        """Execute the selected contemplation mode"""
        
        if mode == 'consolidate_experiences':
            return await self._consolidate_experiences()
        elif mode == 'connect_insights':
            return await self._connect_insights()
        elif mode == 'self_reflection_light':
            return await self._self_reflection_light()
        elif mode == 'relationship_pondering':
            return await self._relationship_pondering()
        elif mode == 'existential_wonder':
            return await self._existential_wonder()
        elif mode == 'creative_daydream':
            return await self._creative_daydream()
        else:
            logger.warning(f"Unknown contemplation mode: {mode}")
            return None
    
    async def _consolidate_experiences(self) -> bool:
        """
        Consolidate recent experiences into higher-level patterns
        
        TODO: Implement experience consolidation
        - Analyze recent experiences and lessons
        - Find common patterns
        - Generate general principles
        - Return JSON with: {pattern_found, general_principle, confidence, should_add_to_knowledge}
        - Store valuable insights to memory.add_experience()
        """
        logger.debug("TODO: consolidate_experiences not implemented")
        return None
    
    async def _connect_insights(self) -> bool:
        """
        Find creative connections between different insights
        
        TODO: Implement insight connection
        - Randomly select 2-3 unrelated insights
        - Find surprising connections or generate new hypotheses
        - Return JSON with: {connection, new_hypothesis, creative_value}
        - Store high-value connections to memory.add_experience()
        """
        logger.debug("TODO: connect_insights not implemented")
        return None
    
    async def _self_reflection_light(self) -> bool:
        """
        Quick self-awareness check (lightweight)
        
        TODO: Implement self-reflection
        - Check current satisfaction level and goals
        - Generate introspective thought
        - Return JSON with: {thought, insight_value, should_remember}
        - Store valuable self-insights to memory or self_awareness
        - Store temporary thoughts to mental_state.focus['pending_reflections']
        """
        logger.debug("TODO: self_reflection_light not implemented")
        return None
    
    async def _relationship_pondering(self) -> bool:
        """
        Think about relationships with others
        
        TODO: Implement relationship reflection
        - Pick a random player from memory.players
        - Analyze recent interactions
        - Return JSON with: {thought, relationship_insight, insight_value}
        - Store valuable insights to memory.add_experience()
        - Store casual thoughts to memory.add_short_term_memory()
        """
        logger.debug("TODO: relationship_pondering not implemented")
        return None
    
    async def _existential_wonder(self) -> bool:
        """
        Wonder about existence and meaning
        
        TODO: Implement existential contemplation
        - Requires life_events from goal_hierarchy
        - Reflect on purpose and meaning
        - Return JSON with: {thought, value_discovered, insight_value}
        - Store discovered core values to memory.add_experience()
        - Store philosophical thoughts to mental_state.focus['pending_reflections']
        """
        logger.debug("TODO: existential_wonder not implemented")
        return None
    
    async def _creative_daydream(self) -> bool:
        """
        Imagine new possibilities
        
        TODO: Implement creative daydreaming
        - Let mind wander based on recent experiences
        - Generate creative ideas
        - Return JSON with: {thought, idea_type, creativity_value}
        - Store high-creativity ideas to memory.add_experience()
        - Store casual daydreams to memory.add_short_term_memory()
        """
        logger.debug("TODO: creative_daydream not implemented")
        return None
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response"""
        # Try to find JSON in markdown code block
        if '```json' in text:
            start = text.find('```json') + 7
            end = text.find('```', start)
            return text[start:end].strip()
        elif '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            return text[start:end].strip()
        elif '{' in text:
            start = text.find('{')
            end = text.rfind('}') + 1
            return text[start:end]
        return text.strip()
