"""
Game State Formatter
Formats game state information for LLM prompts.
Inspired by original MindCraft's approach to presenting environment information.
"""

from typing import Dict, Any, List, Set


class GameStateFormatter:
    """
    Formats game state data for presentation in LLM prompts.
    Provides clear, readable information about the bot's environment.
    """
    
    @staticmethod
    def format_stats(state: Dict[str, Any]) -> str:
        """
        Format bot status information (health, food, position).
        
        Args:
            state: Game state dictionary
            
        Returns:
            Formatted stats string
        """
        position = state.get('position', {})
        health = state.get('health', 20)
        food = state.get('food', 20)
        
        stats = f"""Health: {health}/20
Food: {food}/20
Position: x:{position.get('x', 0):.1f}, y:{position.get('y', 0):.1f}, z:{position.get('z', 0):.1f}"""
        
        return stats
    
    @staticmethod
    def format_inventory(state: Dict[str, Any]) -> str:
        """
        Format inventory information.
        
        Args:
            state: Game state dictionary
            
        Returns:
            Formatted inventory string
        """
        inventory = state.get('inventory', {})
        
        if not inventory:
            return "Empty"
        
        # Sort items by name for consistency
        items = sorted(inventory.items())
        return "\n".join([f"- {name}: {count}" for name, count in items])
    
    @staticmethod
    def format_time_of_day(time_of_day: int) -> str:
        """
        Convert Minecraft time (0-23999 ticks) to readable format.
        
        Args:
            time_of_day: Minecraft time in ticks (0-23999)
            
        Returns:
            Formatted time string like "12:00 (6000 ticks)"
        """
        # Minecraft day starts at 6 AM (tick 0)
        minecraft_hour = int((time_of_day / 1000) + 6) % 24
        return f"{minecraft_hour}:00 ({time_of_day} ticks)"
    
    @staticmethod
    def format_surrounding_blocks(state: Dict[str, Any]) -> Dict[str, str]:
        """
        Format immediate surrounding blocks (below, legs, head, above).
        Like original MindCraft's getSurroundingBlocks.
        
        Args:
            state: Game state dictionary
            
        Returns:
            Dictionary with keys: below, legs, head, above
        """
        surrounding = state.get('surrounding_blocks', {})
        
        return {
            'below': surrounding.get('below', 'unknown'),
            'legs': surrounding.get('legs', 'unknown'),
            'head': surrounding.get('head', 'unknown'),
            'above': surrounding.get('firstAbove', 'none')
        }
    
    @staticmethod
    def format_nearby_blocks(state: Dict[str, Any]) -> str:
        """
        Format nearby blocks list with water/lava state details.
        Like original MindCraft's getNearbyBlockTypes.
        
        Args:
            state: Game state dictionary
            
        Returns:
            Formatted nearby blocks string (bullet list)
        """
        nearby_blocks = state.get('nearby_blocks', [])
        
        if not nearby_blocks or not isinstance(nearby_blocks, list):
            return "- No block scan data"
        
        # Get unique block types (like original getNearbyBlockTypes)
        block_types: Set[str] = set()
        
        for block in nearby_blocks:
            block_name = block.get('name', 'unknown')
            
            # Add water/lava state info like original
            if block_name in ['water', 'lava']:
                metadata = block.get('metadata', 0)
                state_str = 'source' if metadata == 0 else 'flowing'
                details = f"{block_name} ({state_str})"
                block_types.add(details)
            else:
                block_types.add(block_name)
        
        if not block_types:
            return "- None"
        
        # Format as bullet list, sorted for consistency
        return '\n'.join([f"- {name}" for name in sorted(block_types)])
    
    @staticmethod
    def format_nearby_entities(state: Dict[str, Any]) -> str:
        """
        Format nearby entities list, separating human players from mobs.
        Like original MindCraft's entity listing approach.
        
        Args:
            state: Game state dictionary
            
        Returns:
            Formatted nearby entities string (bullet list)
        """
        nearby_entities = state.get('nearby_entities', [])
        
        if not nearby_entities or not isinstance(nearby_entities, list):
            return "- No entity scan data"
        
        entity_types: Set[str] = set()
        human_players: List[str] = []
        
        for entity in nearby_entities:
            entity_type = entity.get('type', 'unknown')
            entity_name = entity.get('name', entity_type)
            
            # Separate human players (like original)
            if entity_type == 'player':
                human_players.append(entity_name)
            # Filter out items and players (like original)
            elif entity_type not in ['item']:
                entity_types.add(entity_type)
        
        # Build formatted list
        entities_list: List[str] = []
        
        # Add human players first
        for player in sorted(human_players):
            entities_list.append(f"- Human player: {player}")
        
        # Add other entities
        for entity_type in sorted(entity_types):
            entities_list.append(f"- {entity_type}")
        
        if not entities_list:
            return "- None"
        
        return '\n'.join(entities_list)
    
    @staticmethod
    def format_environment_info(state: Dict[str, Any]) -> Dict[str, str]:
        """
        Format general environment information (biome, time, day, weather, dimension).
        
        Args:
            state: Game state dictionary
            
        Returns:
            Dictionary with keys: biome, time_of_day, time_label, world_day, agent_age, weather, dimension, gamemode
        """
        biome = state.get('biome', 'unknown')
        time_of_day = state.get('time_of_day', 0)
        time_label = state.get('time_label', 'Night')
        world_day = state.get('world_day', 0)
        agent_age_days = state.get('agent_age_days', 0)
        agent_age_ticks = state.get('agent_age_ticks', 0)
        weather = state.get('weather', 'Clear')
        dimension = state.get('dimension', 'unknown')
        gamemode = state.get('gamemode', 'survival')
        
        # Format agent age nicely
        agent_age_str = f"{agent_age_days} days"
        if agent_age_days == 0 and agent_age_ticks > 0:
            # Less than 1 day - show hours
            hours = agent_age_ticks // 1000
            agent_age_str = f"{hours} hours"
        
        return {
            'biome': biome,
            'time_of_day': GameStateFormatter.format_time_of_day(time_of_day),
            'time_label': time_label,
            'world_day': str(world_day),
            'agent_age': agent_age_str,
            'weather': weather,
            'dimension': dimension,
            'gamemode': gamemode
        }
    
    @staticmethod
    def format_equipment(state: Dict[str, Any]) -> str:
        """
        Format equipment information (armor and held item).
        
        Args:
            state: Game state dictionary
            
        Returns:
            Formatted equipment string
        """
        equipment = state.get('equipment', {})
        
        if not equipment or all(v is None for v in equipment.values()):
            return "No equipment"
        
        items = []
        if equipment.get('helmet'):
            items.append(f"- Helmet: {equipment['helmet']}")
        if equipment.get('chestplate'):
            items.append(f"- Chestplate: {equipment['chestplate']}")
        if equipment.get('leggings'):
            items.append(f"- Leggings: {equipment['leggings']}")
        if equipment.get('boots'):
            items.append(f"- Boots: {equipment['boots']}")
        if equipment.get('mainHand'):
            items.append(f"- Holding: {equipment['mainHand']}")
        
        return '\n'.join(items) if items else "No equipment"
    
    @staticmethod
    def populate_prompt_placeholders(prompt: str, state: Dict[str, Any], agent_name: str = 'BrainyBot') -> str:
        """
        Populate all game state placeholders in a prompt template.
        
        Args:
            prompt: Prompt template with $PLACEHOLDER markers
            state: Game state dictionary
            agent_name: Bot name
            
        Returns:
            Prompt with all placeholders replaced
        """
        # Basic info
        prompt = prompt.replace('$NAME', agent_name)
        
        # Position (for high-level prompts)
        if '$POSITION' in prompt:
            position = state.get('position', {})
            position_str = f"x:{position.get('x', 0):.1f}, y:{position.get('y', 0):.1f}, z:{position.get('z', 0):.1f}"
            prompt = prompt.replace('$POSITION', position_str)
        
        # Health and Food (for high-level prompts)
        if '$HEALTH' in prompt:
            prompt = prompt.replace('$HEALTH', str(state.get('health', 20)))
        if '$FOOD' in prompt:
            prompt = prompt.replace('$FOOD', str(state.get('food', 20)))
        
        # Stats
        stats = GameStateFormatter.format_stats(state)
        prompt = prompt.replace('$STATS', stats)
        
        # Inventory
        inventory = GameStateFormatter.format_inventory(state)
        prompt = prompt.replace('$INVENTORY', inventory)
        
        # Equipment (if placeholder exists)
        if '$EQUIPMENT' in prompt:
            equipment = GameStateFormatter.format_equipment(state)
            prompt = prompt.replace('$EQUIPMENT', equipment)
        
        # Environment
        env_info = GameStateFormatter.format_environment_info(state)
        prompt = prompt.replace('$BIOME', env_info['biome'])
        prompt = prompt.replace('$TIME_OF_DAY', env_info['time_of_day'])
        prompt = prompt.replace('$WORLD_DAY', env_info['world_day'])
        
        # Agent age (optional placeholder for self-awareness prompts)
        if '$AGENT_AGE' in prompt:
            prompt = prompt.replace('$AGENT_AGE', env_info['agent_age'])
        
        # Optional environment placeholders (for advanced prompts)
        if '$TIME_LABEL' in prompt:
            prompt = prompt.replace('$TIME_LABEL', env_info['time_label'])
        if '$WEATHER' in prompt:
            prompt = prompt.replace('$WEATHER', env_info['weather'])
        if '$DIMENSION' in prompt:
            prompt = prompt.replace('$DIMENSION', env_info['dimension'])
        if '$GAMEMODE' in prompt:
            prompt = prompt.replace('$GAMEMODE', env_info['gamemode'])
        
        # Surrounding blocks (immediate position)
        surrounding = GameStateFormatter.format_surrounding_blocks(state)
        prompt = prompt.replace('$BLOCK_BELOW', surrounding['below'])
        prompt = prompt.replace('$BLOCK_LEGS', surrounding['legs'])
        prompt = prompt.replace('$BLOCK_HEAD', surrounding['head'])
        prompt = prompt.replace('$BLOCK_ABOVE', surrounding['above'])
        
        # Nearby blocks (within scan range)
        nearby_blocks = GameStateFormatter.format_nearby_blocks(state)
        prompt = prompt.replace('$NEARBY_BLOCKS', nearby_blocks)
        
        # Nearby entities
        nearby_entities = GameStateFormatter.format_nearby_entities(state)
        prompt = prompt.replace('$NEARBY_ENTITIES', nearby_entities)
        
        return prompt