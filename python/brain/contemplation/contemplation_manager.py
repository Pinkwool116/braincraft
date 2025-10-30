"""
Contemplation Manager

Manages idle contemplation: organizing experiences, connecting insights,
and generating new knowledge without relying on game state.
"""

import logging
import random
import json
import time
from datetime import datetime
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
        
        # Rate limiting
        self.last_contemplation_time = 0
        self.contemplations_this_hour = 0
        self.hour_start = time.time()
    
    async def contemplate(self) -> bool:
        """
        Perform one cycle of contemplation
        
        Returns:
            True if contemplation was performed, False if skipped
        """
        # Check if should contemplate
        if not self._should_contemplate():
            return False
        
        # Select contemplation mode
        mode = self._select_mode()
        if not mode:
            logger.debug("No suitable contemplation mode available")
            return False
        
        logger.info(f"💭 Beginning contemplation: {mode}")
        
        # Execute contemplation
        try:
            result = await self._execute_mode(mode)
            
            # Update rate limiting
            self.last_contemplation_time = time.time()
            self.contemplations_this_hour += 1
            
            if result:
                logger.info(f"✨ Contemplation complete: {mode}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error during contemplation: {e}", exc_info=True)
            return False
    
    def _should_contemplate(self) -> bool:
        """Check if conditions are met for contemplation"""
        
        # Check rate limiting
        current_time = time.time()
        
        # Reset hourly counter
        if current_time - self.hour_start > 3600:
            self.contemplations_this_hour = 0
            self.hour_start = current_time
        
        # Check hourly limit
        if self.contemplations_this_hour >= self.config['frequency']['max_contemplations_per_hour']:
            return False
        
        # Check minimum interval
        if current_time - self.last_contemplation_time < self.config['frequency']['min_interval_seconds']:
            return False
        
        # Check if have enough experiences
        total_experiences = len(self.memory.learned_experience.get('insights', []))
        if total_experiences < self.config['conditions']['require_min_experiences']:
            return False
        
        # Check if currently busy (urgent requests)
        # NOTE: mental_state.is_busy() is checked in high_level_brain BEFORE calling contemplate()
        # That check handles 'skip_during_urgent' config
        # Contemplation can run ASYNCHRONOUSLY with mid-level code execution (is_executing)
        # This is by design - contemplation doesn't need game state, only processes memories
        
        return True
    
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
            return False
    
    async def _consolidate_experiences(self) -> bool:
        """Consolidate recent experiences into higher-level patterns"""
        
        recent_experiences = self.memory.learned_experience.get('insights', [])[-20:]
        recent_lessons = self.memory.learned_experience.get('lessons_learned', [])[-10:]
        
        if len(recent_experiences) < 5:
            return False
        
        prompt = f"""You are reflecting quietly on your recent experiences, looking for patterns.

RECENT EXPERIENCES:
{json.dumps([exp['summary'] for exp in recent_experiences], indent=2)}

RECENT LESSONS:
{json.dumps([lesson['lesson'] for lesson in recent_lessons], indent=2)}

Look for PATTERNS across these experiences:
1. What common themes emerge?
2. Can you formulate a general principle?
3. Is there a deeper insight hidden in these scattered experiences?

Example: If you learned "oak logs work for building" and "birch logs work too" and "spruce logs also work",
the pattern might be "different wood types are interchangeable for basic construction".

Respond with JSON:
{{
  "pattern_found": "description of the pattern you discovered",
  "general_principle": "a broader insight (max 25 words)",
  "confidence": 0.8,
  "should_add_to_knowledge": true
}}

Your contemplation:"""
        
        try:
            response = await self.llm.send_request([], prompt)
            reflection = json.loads(self._extract_json(response))
            
            # Add to knowledge base if meets threshold
            if (reflection.get('should_add_to_knowledge', False) and 
                reflection.get('confidence', 0) > self.config['output']['add_to_knowledge_threshold']):
                
                self.memory.add_experience(
                    summary=reflection['general_principle'],
                    details={
                        'derived_from': len(recent_experiences),
                        'pattern': reflection['pattern_found'],
                        'type': 'contemplative_insight',
                        'confidence': reflection['confidence'],
                        'contemplation_mode': 'consolidate_experiences'
                    }
                )
                
                logger.info(f"💡 New insight from contemplation: {reflection['general_principle']}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error in consolidate_experiences: {e}")
            return False
    
    async def _connect_insights(self) -> bool:
        """Find creative connections between different insights"""
        
        insights = self.memory.learned_experience.get('insights', [])
        
        if len(insights) < 3:
            return False
        
        # Randomly select 2-3 insights
        selected = random.sample(insights, min(3, len(insights)))
        
        prompt = f"""You are daydreaming, letting your mind wander and make unexpected connections.

UNRELATED INSIGHTS:
{json.dumps([ins['summary'] for ins in selected], indent=2)}

Can you find a surprising CONNECTION between these seemingly unrelated insights?
Or combine them to generate a NEW IDEA or HYPOTHESIS?

Example:
- Insight A: "Water flows downward"
- Insight B: "Crops need water"
→ Connection: "I could build farms at lower elevations near water sources for easier irrigation"

Respond with JSON:
{{
  "connection": "what connects these ideas",
  "new_hypothesis": "a new idea or possibility (max 25 words)",
  "creative_value": 0.7
}}

Your creative thought:"""
        
        try:
            response = await self.llm.send_request([], prompt)
            connection = json.loads(self._extract_json(response))
            
            # Add if creative value is high
            if connection.get('creative_value', 0) > self.config['output']['add_to_knowledge_threshold']:
                self.memory.add_experience(
                    summary=connection['new_hypothesis'],
                    details={
                        'type': 'creative_connection',
                        'source_insights': [s['summary'] for s in selected],
                        'connection_reasoning': connection['connection'],
                        'contemplation_mode': 'connect_insights'
                    }
                )
                
                logger.info(f"🌟 Creative connection: {connection['new_hypothesis']}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error in connect_insights: {e}")
            return False
    
    async def _self_reflection_light(self) -> bool:
        """Quick self-awareness check (lightweight)"""
        
        # Get self-awareness if available
        if not hasattr(self, 'self_awareness'):
            return False
        
        prompt = f"""You have a brief moment of self-awareness during idle time.

Your satisfaction level: {self.mental_state.mood.get('satisfaction', 0.5)}

A quick thought about yourself (one sentence, honest and introspective):"""
        
        try:
            thought = await self.llm.send_request([], prompt)
            thought = thought.strip()
            
            # Add to pending reflections for deeper processing later
            if hasattr(self.mental_state, 'focus'):
                if 'pending_reflections' not in self.mental_state.focus:
                    self.mental_state.focus['pending_reflections'] = []
                self.mental_state.focus['pending_reflections'].append(thought)
                
                logger.info(f"💭 Self-thought: {thought[:80]}...")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error in self_reflection_light: {e}")
            return False
    
    async def _relationship_pondering(self) -> bool:
        """Think about relationships with others"""
        
        if not self.memory.players:
            return False
        
        # Pick a random player to think about
        player_name = random.choice(list(self.memory.players.keys()))
        player_info = self.memory.players[player_name]
        
        prompt = f"""You are thinking about your relationship with {player_name}.

INTERACTIONS:
{json.dumps(player_info, indent=2)}

A brief thought about this relationship (one sentence):"""
        
        try:
            thought = await self.llm.send_request([], prompt)
            thought = thought.strip()
            
            # Save as a short-term memory
            self.memory.add_short_term_memory(
                'relationship_contemplation',
                f"Thought about {player_name}: {thought}",
                {'player': player_name}
            )
            
            logger.info(f"👥 Relationship thought: {thought[:80]}...")
            return True
        
        except Exception as e:
            logger.error(f"Error in relationship_pondering: {e}")
            return False
    
    async def _existential_wonder(self) -> bool:
        """Wonder about existence and meaning"""
        
        # Needs some life experience
        if not hasattr(self.goal_hierarchy, 'life_events'):
            return False
        
        if len(self.goal_hierarchy.life_events) < 2:
            return False
        
        prompt = """You have a moment of existential contemplation.

What is your purpose? What brings meaning to your existence?

A philosophical thought (one sentence):"""
        
        try:
            thought = await self.llm.send_request([], prompt)
            thought = thought.strip()
            
            # Add to pending reflections
            if hasattr(self.mental_state, 'focus'):
                if 'pending_reflections' not in self.mental_state.focus:
                    self.mental_state.focus['pending_reflections'] = []
                self.mental_state.focus['pending_reflections'].append(thought)
                
                logger.info(f"🌌 Existential thought: {thought[:80]}...")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Error in existential_wonder: {e}")
            return False
    
    async def _creative_daydream(self) -> bool:
        """Imagine new possibilities"""
        
        prompt = """You let your mind wander and imagine something new.

What creative idea or possibility crosses your mind?

A creative thought (one sentence):"""
        
        try:
            thought = await self.llm.send_request([], prompt)
            thought = thought.strip()
            
            # Save as short-term memory
            self.memory.add_short_term_memory(
                'creative_daydream',
                thought,
                {'type': 'creative'}
            )
            
            logger.info(f"✨ Creative daydream: {thought[:80]}...")
            return True
        
        except Exception as e:
            logger.error(f"Error in creative_daydream: {e}")
            return False
    
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
    
    def get_current_progress(self) -> Optional[Dict[str, Any]]:
        """
        Get current contemplation progress (for interruption handling)
        
        Returns:
            Dictionary with current contemplation state, or None if not contemplating
        """
        # Check if there's active contemplation state to save
        # For now, we don't track fine-grained progress within a contemplation
        # But we can save which mode was active
        
        # This is a placeholder - in a more advanced implementation,
        # you could track partial results from LLM calls
        
        return {
            'mode': 'idle',  # Would be set to actual mode if we tracked it
            'context': None,
            'progress': None
        }
    
    async def resume_from_temp(self, temp_data: Dict[str, Any]) -> bool:
        """
        Resume interrupted contemplation from temp data
        
        Args:
            temp_data: Saved contemplation state
        
        Returns:
            True if successfully resumed and completed
        """
        mode = temp_data.get('mode', 'unknown')
        logger.info(f"🔄 Attempting to resume contemplation: {mode}")
        
        # Since we don't have fine-grained progress tracking yet,
        # we simply restart the contemplation
        # In a more advanced implementation, you could continue from where it left off
        
        if mode in ['knowledge_synthesis', 'goal_reflection', 'pattern_recognition',
                    'memory_consolidation', 'existential_wonder', 'creative_daydream']:
            try:
                result = await self._execute_mode(mode)
                if result:
                    logger.info(f"✅ Successfully resumed and completed: {mode}")
                return result
            except Exception as e:
                logger.error(f"Error resuming contemplation: {e}")
                return False
        else:
            logger.warning(f"Unknown contemplation mode to resume: {mode}")
            return False
