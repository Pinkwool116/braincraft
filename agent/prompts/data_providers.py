"""
Data Providers for Prompt Variables

This module provides all data retrieval functions used for prompt variable substitution.
Each function receives a context dictionary and returns a formatted string.

Context parameters:
- state: Game state dictionary (required for most providers)
- agent_name: Agent name string
- memory_manager: MemoryManager instance (optional, for memory-related providers)
- task_stack_manager: TaskStackManager instance (optional, for task-related providers)
- high_brain: HighLevelBrain instance (optional, for high-level specific providers)
- self_awareness: SelfAwareness instance (optional, for agent info)
- player: Player name string (optional, for player-specific providers)
- memory_count: Number of memories to retrieve (optional, default: 5)
"""

import datetime
from typing import Dict, Any
from utils.game_state_formatter import GameStateFormatter


class DataProviders:
    """
    Centralized data provider functions for prompt variable substitution.
    All methods are static and receive a context dictionary.
    """
    
    # ========== Basic Game State ==========
    
    @staticmethod
    def get_stats(context: Dict[str, Any]) -> str:
        """
        Get agent status information (health, food, position).
        Maps to $STATS variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Formatted stats string with health, food, and position
        """
        state = context.get('state', {})
        return GameStateFormatter.format_stats(state)
    
    @staticmethod
    def get_inventory(context: Dict[str, Any]) -> str:
        """
        Get inventory information.
        Maps to $INVENTORY variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Formatted inventory list (bullet points) or "Empty"
        """
        state = context.get('state', {})
        return GameStateFormatter.format_inventory(state)
    
    @staticmethod
    def get_equipment(context: Dict[str, Any]) -> str:
        """
        Get equipment information (armor and held item).
        Maps to $EQUIPMENT variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Formatted equipment list or "No equipment"
        """
        state = context.get('state', {})
        return GameStateFormatter.format_equipment(state)
    
    @staticmethod
    def get_position(context: Dict[str, Any]) -> str:
        """
        Get current position coordinates.
        Maps to $POSITION variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Position string like "x:100.5, y:64.0, z:-200.3"
        """
        state = context.get('state', {})
        position = state.get('position', {})
        x = position.get('x', 0)
        y = position.get('y', 0)
        z = position.get('z', 0)
        return f"x:{x:.1f}, y:{y:.1f}, z:{z:.1f}"
    
    @staticmethod
    def get_health(context: Dict[str, Any]) -> str:
        """
        Get health value.
        Maps to $HEALTH variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Health string like "18/20"
        """
        state = context.get('state', {})
        health = state.get('health', 20)
        return f"{health}/20"
    
    @staticmethod
    def get_food(context: Dict[str, Any]) -> str:
        """
        Get food/hunger value.
        Maps to $FOOD variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Food string like "15/20"
        """
        state = context.get('state', {})
        food = state.get('food', 20)
        return f"{food}/20"
    
    @staticmethod
    def get_biome(context: Dict[str, Any]) -> str:
        """
        Get current biome.
        Maps to $BIOME variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Biome name like "plains" or "forest"
        """
        state = context.get('state', {})
        return state.get('biome', 'unknown')
    
    @staticmethod
    def get_time_of_day(context: Dict[str, Any]) -> str:
        """
        Get formatted time of day.
        Maps to $TIME_OF_DAY variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Formatted time like "12:00 (6000 ticks)"
        """
        state = context.get('state', {})
        time_of_day = state.get('time_of_day', 0)
        return GameStateFormatter.format_time_of_day(time_of_day)
    
    @staticmethod
    def get_world_day(context: Dict[str, Any]) -> str:
        """
        Get world day number.
        Maps to $WORLD_DAY variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Day number as string
        """
        state = context.get('state', {})
        world_day = state.get('world_day', 0)
        return str(world_day)
    
    @staticmethod
    def get_weather(context: Dict[str, Any]) -> str:
        """
        Get current weather.
        Maps to $WEATHER variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Weather like "Clear", "Rain", or "Thunder"
        """
        state = context.get('state', {})
        weather = state.get('weather', 'Clear')
        return weather
    
    # ========== Surrounding Environment ==========
    
    @staticmethod
    def get_block_below(context: Dict[str, Any]) -> str:
        """
        Get block directly below agent.
        Maps to $BLOCK_BELOW variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Block name or "unknown"
        """
        state = context.get('state', {})
        surrounding = state.get('surrounding_blocks', {})
        return surrounding.get('below', 'unknown')
    
    @staticmethod
    def get_block_legs(context: Dict[str, Any]) -> str:
        """
        Get block at leg level.
        Maps to $BLOCK_LEGS variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Block name or "unknown"
        """
        state = context.get('state', {})
        surrounding = state.get('surrounding_blocks', {})
        return surrounding.get('legs', 'unknown')
    
    @staticmethod
    def get_block_head(context: Dict[str, Any]) -> str:
        """
        Get block at head level.
        Maps to $BLOCK_HEAD variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Block name or "unknown"
        """
        state = context.get('state', {})
        surrounding = state.get('surrounding_blocks', {})
        return surrounding.get('head', 'unknown')
    
    @staticmethod
    def get_block_above(context: Dict[str, Any]) -> str:
        """
        Get first block above agent.
        Maps to $BLOCK_ABOVE variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Block name or "none"
        """
        state = context.get('state', {})
        surrounding = state.get('surrounding_blocks', {})
        return surrounding.get('firstAbove', 'none')
    
    @staticmethod
    def get_nearby_blocks(context: Dict[str, Any]) -> str:
        """
        Get nearby blocks list with water/lava state details.
        Maps to $NEARBY_BLOCKS variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Formatted bullet list of nearby block types
        """
        state = context.get('state', {})
        return GameStateFormatter.format_nearby_blocks(state)
    
    @staticmethod
    def get_nearby_entities(context: Dict[str, Any]) -> str:
        """
        Get nearby entities list, separating players from mobs.
        Maps to $NEARBY_ENTITIES variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Formatted bullet list of nearby entities
        """
        state = context.get('state', {})
        return GameStateFormatter.format_nearby_entities(state)
    
    # ========== High-Level Brain Specific ==========
    
    @staticmethod
    async def get_mind_context(context: Dict[str, Any]) -> str:
        """
        Get mind context from high-level brain.
        Maps to $MIND_CONTEXT variable.
        
        Args:
            context: Must contain 'high_brain' key
            
        Returns:
            Mind context string or empty string
        """
        high_brain = context.get('high_brain')
        if high_brain and hasattr(high_brain, 'get_mind_context_for_prompt'):
            return await high_brain.get_mind_context_for_prompt()
        return ""
    
    @staticmethod
    def get_learned_experience(context: Dict[str, Any]) -> str:
        """
        Get learned experience summary (insights + lessons + player relationships).
        Maps to $LEARNED_EXPERIENCE variable.
        
        This is the complete experience summary including both learned insights/lessons
        and player relationship information.
        
        Args:
            context: Must contain 'memory_manager' key
            
        Returns:
            Formatted learned experience string or "No learned experience yet."
        """
        memory_manager = context.get('memory_manager')
        if not memory_manager:
            raise ValueError("memory_manager is required in context for get_learned_experience")
        
        # Get insights and lessons (max 10 insights, 20 lessons)
        learned_exp = memory_manager.get_learned_experience_summary(
            max_insights=10,
            max_lessons=20
        )
        
        # Add player relationship summary
        players_info = memory_manager.get_all_players_summary()
        if players_info and players_info != "No players known yet.":
            learned_exp += "\n\n" + players_info
        
        return learned_exp if learned_exp else "No learned experience yet."
    
    @staticmethod
    def get_lessons_learned(context: Dict[str, Any]) -> str:
        """
        Get lessons learned (failures and mistakes).
        Maps to $LESSONS_LEARNED variable.
        
        This extracts only the "lessons learned" portion (from failures),
        separate from general insights.
        
        Args:
            context: Must contain 'memory_manager' key
            
        Returns:
            Formatted lessons learned string or empty string
        """
        memory_manager = context.get('memory_manager')
        if not memory_manager:
            raise ValueError("memory_manager is required in context for get_lessons_learned")
        
        lessons = memory_manager.learned_experience.get('lessons_learned', [])
        if not lessons:
            return ""
        
        # Get last 10 lessons
        recent_lessons = lessons[-10:]
        lesson_lines = []
        for lesson in recent_lessons:
            lesson_lines.append(f"- {lesson['lesson']}")
        
        return "\n".join(lesson_lines)
    
    @staticmethod
    def get_task_plan(context: Dict[str, Any]) -> str:
        """
        Get current task plan summary.
        Maps to $TASK_PLAN variable.
        
        Args:
            context: Must contain 'task_stack_manager' key
            
        Returns:
            Task plan summary or "No active tasks"
        """
        task_stack_manager = context.get('task_stack_manager')
        if not task_stack_manager:
            raise ValueError("task_stack_manager is required in context for get_task_plan")
        if hasattr(task_stack_manager, 'generate_task_stack_summary'):
            return task_stack_manager.generate_task_stack_summary()
        return "No active tasks"
    
    # ========== Memory Related ==========
    
    @staticmethod
    def get_players_info(context: Dict[str, Any]) -> str:
        """
        Get all players summary from memory.
        Maps to $PLAYERS_INFO variable.
        
        Args:
            context: Must contain 'memory_manager' key
            
        Returns:
            Players summary or "No players encountered yet."
        """
        memory_manager = context.get('memory_manager')
        if not memory_manager:
            raise ValueError("memory_manager is required in context for get_players_info")
        if hasattr(memory_manager, 'get_all_players_summary'):
            players_info = memory_manager.get_all_players_summary()
            return players_info if players_info else "No players encountered yet."
        return "No players encountered yet."
    
    @staticmethod
    def get_player_info(context: Dict[str, Any]) -> str:
        """
        Get specific player personality and preferences.
        Maps to $PLAYER_INFO variable.
        
        Args:
            context: Must contain 'player' and 'memory_manager' keys
            
        Returns:
            Formatted string like "Personality: calm, helpful, Preferences: building, exploring"
        """
        player = context.get('player')
        memory_manager = context.get('memory_manager')
        
        if not player or not memory_manager:
            raise ValueError("player and memory_manager are required in context for get_player_info")
        
        player_data = memory_manager.get_player_data(player)
        if not player_data:
            return "Personality: unknown, Preferences: unknown"
        
        personality_list = player_data.get('personality', [])
        preferences_list = player_data.get('preferences', [])
        
        # Get last 3 entries for each
        personality = ', '.join(personality_list[-3:]) if personality_list else 'unknown'
        preferences = ', '.join(preferences_list[-3:]) if preferences_list else 'unknown'
        
        return f"Personality: {personality}, Preferences: {preferences}"
    
    @staticmethod
    def get_player_relationship(context: Dict[str, Any]) -> str:
        """
        Get relationship status with a player.
        Maps to $PLAYER_RELATIONSHIP variable.
        
        Args:
            context: Must contain 'player' and 'memory_manager' keys
            
        Returns:
            Relationship like "neutral", "friendly", or "hostile"
        """
        player = context.get('player')
        memory_manager = context.get('memory_manager')
        
        if not player or not memory_manager:
            raise ValueError("player and memory_manager are required in context for get_player_relationship")
        
        player_data = memory_manager.get_player_data(player)
        if not player_data:
            return "neutral"
        
        return player_data.get('relationship', 'neutral')
    
    @staticmethod
    def get_recent_memories(context: Dict[str, Any]) -> str:
        """
        Get recent memories list.
        Maps to $MEMORY variable.
        
        Args:
            context: Must contain 'memory_manager' key
                    Optional: 'memory_count' (default: 20)
            
        Returns:
            Formatted bullet list of recent memories or "No recent memories."
        """
        memory_manager = context.get('memory_manager')
        count = context.get('memory_count', 20)
        
        if not memory_manager:
            raise ValueError("memory_manager is required in context for get_recent_memories")

        if not hasattr(memory_manager, 'get_recent_memories'):
            return "No recent memories."
        
        recent_memory_entries = memory_manager.get_recent_memories(count=count)
        if not recent_memory_entries:
            return "No recent memories."
        
        memory_lines = []
        for entry in recent_memory_entries:
            event_type = entry.get('type', 'event')
            content = entry.get('content', '')
            memory_lines.append(f"- [{event_type}] {content}")
        
        return "\n".join(memory_lines)
    
    # ========== Auxiliary Information ==========
    
    @staticmethod
    def get_timestamp(context: Dict[str, Any]) -> str:
        """
        Get current timestamp.
        Maps to $TIMESTAMP variable.
        
        Returns:
            Formatted timestamp like "2025-11-04 14:30:00"
        """
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def get_agent_age(context: Dict[str, Any]) -> str:
        """
        Get agent age formatted nicely.
        Maps to $AGENT_AGE variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Formatted age like "2 days" or "5 hours"
        """
        state = context.get('state', {})
        agent_age_days = state.get('agent_age_days', 0)
        agent_age_ticks = state.get('agent_age_ticks', 0)
        
        if agent_age_days == 0 and agent_age_ticks > 0:
            # Less than 1 day - show hours
            hours = agent_age_ticks // 1000
            return f"{hours} hours"
        
        return f"{agent_age_days} days"
    
    @staticmethod
    def get_inventory_summary(context: Dict[str, Any]) -> str:
        """
        Get simplified inventory summary (comma-separated list).
        Maps to $INVENTORY_SUMMARY variable.
        
        Args:
            context: Must contain 'state' key
            
        Returns:
            Comma-separated inventory like "wood: 10, stone: 5" or "Empty inventory"
        """
        state = context.get('state', {})
        inventory = state.get('inventory', {})
        
        if not inventory:
            return "Empty inventory"
        
        # Sort by name and format as "name: count"
        items = ', '.join([f"{name}: {count}" for name, count in sorted(inventory.items())])
        return items
    
    @staticmethod
    def get_agent_name(context: Dict[str, Any]) -> str:
        """
        Get agent name.
        Maps to $NAME variable.
        
        Args:
            context: Must contain 'agent_name' key
            
        Returns:
            Agent name or "BrainyBot"
        """
        return context.get('agent_name', 'BrainyBot')
    
    @staticmethod
    async def get_task_plan_context(context: Dict[str, Any]) -> str:
        """
        Get formatted task plan context for mid-level brain code generation.
        Shows current goal, step progress, and current step description.
        
        Args:
            context: Must contain 'state' dict or 'task_stack_manager'
        
        Returns:
            Formatted task plan context
        """
        # Try to get from shared_state/task_stack_manager
        task_stack_manager = context.get('task_stack_manager')
        if task_stack_manager and hasattr(task_stack_manager, 'get'):
            # It's shared_state object
            task_plan = await task_stack_manager.get('active_task')
        else:
            # Fallback to state dict
            state = context.get('state', {})
            task_plan = state.get('active_task')
        
        if task_plan and task_plan.get('steps'):
            current_idx = task_plan.get('current_step_index', 0)
            total_steps = len(task_plan.get('steps', []))
            goal = task_plan.get('goal', 'Unknown')
            current_step = task_plan['steps'][min(current_idx, len(task_plan['steps']) - 1)]
            return f"""Goal: {goal}
Current Step: {current_idx + 1}/{total_steps}
This step: {current_step.get('description', 'Unknown')}"""
        else:
            return "No active task plan"
    
    @staticmethod
    def get_code_docs(context: Dict[str, Any]) -> str:
        """
        Get full API documentation for code generation.
        
        Args:
            context: Not used, but required for consistency
        
        Returns:
            Full API documentation string
        """
        from prompts.api_docs_generator import get_full_api_docs
        return get_full_api_docs()
    
    @staticmethod
    def get_strategic_goal(context: Dict[str, Any]) -> str:
        """
        Get current strategic goal for chat context.
        
        Args:
            context: Must contain 'state' dict
        
        Returns:
            Strategic goal string
        """
        state = context.get('state', {})
        strategic_goal_data = state.get('strategic_goal')
        
        if isinstance(strategic_goal_data, dict):
            return strategic_goal_data.get('goal_priority', 'exploring the world')
        elif isinstance(strategic_goal_data, str):
            return strategic_goal_data
        else:
            return 'exploring the world'
    
    @staticmethod
    def get_task_stack_summary(context: Dict[str, Any]) -> str:
        """
        Get task stack summary for chat context.
        
        Args:
            context: Must contain 'state' dict
        
        Returns:
            Task stack summary string
        """
        state = context.get('state', {})
        return state.get('task_stack_summary', 'No tasks in the stack.')
    
    @staticmethod
    def get_active_task_summary(context: Dict[str, Any]) -> str:
        """
        Get active task summary for chat context.
        
        Args:
            context: Must contain 'state' dict
        
        Returns:
            Active task summary string
        """
        state = context.get('state', {})
        active_task_dict = state.get('active_task')
        
        if active_task_dict and active_task_dict.get('steps'):
            current_idx = active_task_dict.get('current_step_index', 0)
            steps = active_task_dict.get('steps', [])
            if steps and current_idx < len(steps):
                current_step = steps[current_idx]
                return current_step.get('description', 'figuring out what to do next')
        
        return 'currently idle'
    
    @staticmethod
    def get_recent_memories_chat(context: Dict[str, Any]) -> str:
        """
        Get recent memories formatted for chat (differs from $MEMORY).
        
        Args:
            context: Must contain 'memory_manager'
        
        Returns:
            Formatted recent memories
        """
        memory_manager = context.get('memory_manager')
        if not memory_manager:
            return "No recent memories."
        
        recent_memory_entries = memory_manager.get_recent_memories(count=5)
        if recent_memory_entries:
            memory_lines = []
            for entry in recent_memory_entries:
                event_type = entry.get('type', 'event')
                content = entry.get('content', '')
                memory_lines.append(f"- [{event_type}] {content}")
            return "\n".join(memory_lines)
        else:
            return "No recent memories."
    
    @staticmethod
    def get_player_info_summary(context: Dict[str, Any]) -> str:
        """
        Get player info summary for chat.
        Requires PLAYER_NAME to be set in context.
        
        Args:
            context: Must contain 'memory_manager' and 'PLAYER_NAME'
        
        Returns:
            Player info summary string
        """
        memory_manager = context.get('memory_manager')
        player_name = context.get('player_name')
        
        if not memory_manager or not player_name:
            return "Personality: unknown, Preferences: unknown"
        
        player_data = memory_manager.get_player_data(player_name)
        if player_data:
            personality_list = player_data.get('personality', [])
            preferences_list = player_data.get('preferences', [])
            personality = ', '.join(personality_list[-3:]) if personality_list else 'unknown'
            preferences = ', '.join(preferences_list[-3:]) if preferences_list else 'unknown'
            return f"Personality: {personality}, Preferences: {preferences}"
        else:
            return "Personality: unknown, Preferences: unknown"
    
    @staticmethod
    def get_player_opinion(context: Dict[str, Any]) -> str:
        """
        Get player relationship opinion for chat.
        Requires PLAYER_NAME to be set in context.
        
        Args:
            context: Must contain 'memory_manager' and 'PLAYER_NAME'
        
        Returns:
            Player opinion string
        """
        memory_manager = context.get('memory_manager')
        player_name = context.get('player_name')
        
        if not memory_manager or not player_name:
            return "neutral"
        
        player_data = memory_manager.get_player_data(player_name)
        if player_data:
            return player_data.get('relationship', 'neutral')
        else:
            return "neutral"
    
    @staticmethod
    def get_chat_context(context: Dict[str, Any]) -> str:
        """
        Get chat history context.
        Requires PLAYER_NAME and chat_manager to be set in context.
        
        Args:
            context: Must contain 'chat_manager' and 'PLAYER_NAME'
        
        Returns:
            Chat context string
        """
        chat_manager = context.get('chat_manager')
        player_name = context.get('player_name')
        
        if not chat_manager or not player_name:
            return "No previous conversation."
        
        chat_context = chat_manager.get_player_chat_context(player_name, limit=5)
        if not chat_context or chat_context is None:
            return "No previous conversation."
        
        return chat_context


# Export function mapping dictionary
# This allows variable_config.yaml to reference functions by name
PROVIDER_FUNCTIONS = {
    # Basic game state
    'get_stats': DataProviders.get_stats,
    'get_inventory': DataProviders.get_inventory,
    'get_equipment': DataProviders.get_equipment,
    'get_position': DataProviders.get_position,
    'get_health': DataProviders.get_health,
    'get_food': DataProviders.get_food,
    'get_biome': DataProviders.get_biome,
    'get_time_of_day': DataProviders.get_time_of_day,
    'get_world_day': DataProviders.get_world_day,
    'get_weather': DataProviders.get_weather,
    
    # Surrounding environment
    'get_block_below': DataProviders.get_block_below,
    'get_block_legs': DataProviders.get_block_legs,
    'get_block_head': DataProviders.get_block_head,
    'get_block_above': DataProviders.get_block_above,
    'get_nearby_blocks': DataProviders.get_nearby_blocks,
    'get_nearby_entities': DataProviders.get_nearby_entities,
    
    # High-level brain specific
    'get_mind_context': DataProviders.get_mind_context,
    'get_learned_experience': DataProviders.get_learned_experience,
    'get_lessons_learned': DataProviders.get_lessons_learned,
    'get_task_plan': DataProviders.get_task_plan,
    
    # Memory related
    'get_players_info': DataProviders.get_players_info,
    'get_player_info': DataProviders.get_player_info,
    'get_player_relationship': DataProviders.get_player_relationship,
    'get_recent_memories': DataProviders.get_recent_memories,
    
    # Auxiliary information
    'get_timestamp': DataProviders.get_timestamp,
    'get_agent_age': DataProviders.get_agent_age,
    'get_inventory_summary': DataProviders.get_inventory_summary,
    'get_agent_name': DataProviders.get_agent_name,
    'get_task_plan_context': DataProviders.get_task_plan_context,
    'get_code_docs': DataProviders.get_code_docs,
    
    # Chat-specific
    'get_strategic_goal': DataProviders.get_strategic_goal,
    'get_task_stack_summary': DataProviders.get_task_stack_summary,
    'get_active_task_summary': DataProviders.get_active_task_summary,
    'get_recent_memories_chat': DataProviders.get_recent_memories_chat,
    'get_player_info_summary': DataProviders.get_player_info_summary,
    'get_player_opinion': DataProviders.get_player_opinion,
    'get_chat_context': DataProviders.get_chat_context,
}
