"""
Skill Library Interface

Provides Python interface to JavaScript mineflayer skills.
Mid-level brain uses this to generate code and execute skills.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class SkillLibrary:
    """
    Interface to mineflayer skill library
    
    Provides:
    - Skill documentation for LLM prompts
    - Skill validation
    - Code template generation
    """
    
    def __init__(self):
        """Initialize skill library"""
        self.skills = self._load_skill_definitions()
        logger.info(f"Skill library initialized with {len(self.skills)} skills")
    
    def _load_skill_definitions(self) -> Dict[str, Dict[str, Any]]:
        """
        Load skill definitions from mineflayer skills.js
        
        Returns:
            Dictionary mapping skill names to their definitions
        """
        # TODO: Parse actual skills.js file or load from JSON
        # For now, define core skills manually
        
        return {
            # Movement skills
            "goToPlayer": {
                "params": ["username", "min_distance"],
                "description": "Go to a player's position",
                "returns": "boolean (success)",
                "example": "await skills.goToPlayer(bot, 'steve', 3);"
            },
            "goToPosition": {
                "params": ["x", "y", "z", "min_distance"],
                "description": "Go to a specific position",
                "returns": "boolean (success)",
                "example": "await skills.goToPosition(bot, 100, 64, 200, 0.5);"
            },
            "goToNearestBlock": {
                "params": ["block_type", "min_distance", "range"],
                "description": "Go to nearest block of specified type",
                "returns": "boolean (success)",
                "example": "await skills.goToNearestBlock(bot, 'crafting_table', 3, 32);"
            },
            "goToNearestEntity": {
                "params": ["entity_type", "min_distance", "range"],
                "description": "Go to nearest entity of specified type",
                "returns": "boolean (success)",
                "example": "await skills.goToNearestEntity(bot, 'cow', 2, 32);"
            },
            "moveAway": {
                "params": ["distance"],
                "description": "Move away from current position",
                "returns": "void",
                "example": "await skills.moveAway(bot, 10);"
            },
            "moveAwayFromEntity": {
                "params": ["entity", "distance"],
                "description": "Move away from a specific entity",
                "returns": "void",
                "example": "await skills.moveAwayFromEntity(bot, zombie, 5);"
            },
            "followPlayer": {
                "params": ["username", "follow_distance"],
                "description": "Follow a player continuously",
                "returns": "void",
                "example": "await skills.followPlayer(bot, 'steve', 3);"
            },
            "stay": {
                "params": ["seconds"],
                "description": "Stay in place for specified time",
                "returns": "void",
                "example": "await skills.stay(bot, 30);"
            },
            
            # Resource gathering
            "collectBlock": {
                "params": ["block_type", "count"],
                "description": "Collect blocks of a specific type",
                "returns": "number (amount collected)",
                "example": "await skills.collectBlock(bot, 'oak_log', 10);"
            },
            "breakBlockAt": {
                "params": ["x", "y", "z"],
                "description": "Break block at position (doesn't collect drops)",
                "returns": "boolean (success)",
                "example": "await skills.breakBlockAt(bot, 100, 64, 200);"
            },
            "pickupNearbyItems": {
                "params": [],
                "description": "Pick up items on the ground nearby",
                "returns": "number (items picked up)",
                "example": "await skills.pickupNearbyItems(bot);"
            },
            
            # Combat
            "attackEntity": {
                "params": ["entity"],
                "description": "Attack a specific entity",
                "returns": "boolean (success)",
                "example": "await skills.attackEntity(bot, zombie);"
            },
            "attackNearest": {
                "params": ["mob_type", "kill"],
                "description": "Attack nearest mob of specified type",
                "returns": "boolean (success)",
                "example": "await skills.attackNearest(bot, 'zombie', true);"
            },
            "defendSelf": {
                "params": ["range"],
                "description": "Defend against nearby enemies within range",
                "returns": "void",
                "example": "await skills.defendSelf(bot, 8);"
            },
            "avoidEnemies": {
                "params": ["range"],
                "description": "Move away from all nearby enemies",
                "returns": "void",
                "example": "await skills.avoidEnemies(bot, 16);"
            },
            
            # Crafting
            "craftRecipe": {
                "params": ["item_name", "count"],
                "description": "Craft items using available materials",
                "returns": "boolean (success)",
                "example": "await skills.craftRecipe(bot, 'wooden_pickaxe', 1);"
            },
            "smeltItem": {
                "params": ["item_name", "count"],
                "description": "Smelt items in a furnace",
                "returns": "number (amount smelted)",
                "example": "await skills.smeltItem(bot, 'iron_ore', 8);"
            },
            "clearNearestFurnace": {
                "params": [],
                "description": "Clear items from nearest furnace",
                "returns": "boolean (success)",
                "example": "await skills.clearNearestFurnace(bot);"
            },
            
            # Building
            "placeBlock": {
                "params": ["block_type", "x", "y", "z", "placement_side", "offset"],
                "description": "Place a block at specific coordinates",
                "returns": "boolean (success)",
                "example": "await skills.placeBlock(bot, 'cobblestone', 100, 64, 200, 'top', false);"
            },
            "activateNearestBlock": {
                "params": ["block_type"],
                "description": "Activate nearest block (button, lever, etc.)",
                "returns": "boolean (success)",
                "example": "await skills.activateNearestBlock(bot, 'lever');"
            },
            
            # Inventory & Storage
            "equipItem": {
                "params": ["item_name"],
                "description": "Equip an item from inventory",
                "returns": "boolean (success)",
                "example": "await skills.equipItem(bot, 'diamond_sword');"
            },
            "discard": {
                "params": ["item_name", "num"],
                "description": "Discard items from inventory",
                "returns": "boolean (success)",
                "example": "await skills.discard(bot, 'dirt', 64);"
            },
            "putInChest": {
                "params": ["item_name", "num"],
                "description": "Put items into nearest chest",
                "returns": "boolean (success)",
                "example": "await skills.putInChest(bot, 'dirt', 64);"
            },
            "takeFromChest": {
                "params": ["item_name", "num"],
                "description": "Take items from nearest chest",
                "returns": "boolean (success)",
                "example": "await skills.takeFromChest(bot, 'iron_ingot', 10);"
            },
            "viewChest": {
                "params": [],
                "description": "View contents of nearest chest",
                "returns": "string (chest contents)",
                "example": "await skills.viewChest(bot);"
            },
            
            # Survival
            "consume": {
                "params": ["item_name"],
                "description": "Eat food or drink potion",
                "returns": "boolean (success)",
                "example": "await skills.consume(bot, 'bread');"
            },
            "goToBed": {
                "params": [],
                "description": "Sleep in nearest bed",
                "returns": "boolean (success)",
                "example": "await skills.goToBed(bot);"
            },
            
            # Farming
            "tillAndSow": {
                "params": ["x", "y", "z", "seed_type"],
                "description": "Till ground and plant seeds",
                "returns": "boolean (success)",
                "example": "await skills.tillAndSow(bot, 100, 64, 200, 'wheat_seeds');"
            },
            
            # Interaction
            "useBlock": {
                "params": ["block"],
                "description": "Use/interact with a block",
                "returns": "boolean (success)",
                "example": "await skills.useBlock(bot, door);"
            },
            "useDoor": {
                "params": ["door_pos"],
                "description": "Use/open door",
                "returns": "boolean (success)",
                "example": "await skills.useDoor(bot);"
            },
            "giveToPlayer": {
                "params": ["item_type", "username", "num"],
                "description": "Give items to player",
                "returns": "boolean (success)",
                "example": "await skills.giveToPlayer(bot, 'diamond', 'Steve', 5);"
            },
            
            # Villager trading
            "showVillagerTrades": {
                "params": ["villager_id"],
                "description": "Show available trades from villager",
                "returns": "string (trade list)",
                "example": "await skills.showVillagerTrades(bot, '12345');"
            },
            "tradeWithVillager": {
                "params": ["villager_id", "trade_index", "count"],
                "description": "Trade with villager",
                "returns": "boolean (success)",
                "example": "await skills.tradeWithVillager(bot, '12345', 0, 1);"
            },
            
            # Mining & Exploration
            "digDown": {
                "params": ["distance"],
                "description": "Dig straight down (dangerous!)",
                "returns": "boolean (success)",
                "example": "await skills.digDown(bot, 10);"
            },
            "goToSurface": {
                "params": [],
                "description": "Navigate to surface",
                "returns": "boolean (success)",
                "example": "await skills.goToSurface(bot);"
            },
            
            # Tool usage
            "useToolOn": {
                "params": ["tool_name", "target_name"],
                "description": "Use tool on target",
                "returns": "boolean (success)",
                "example": "await skills.useToolOn(bot, 'shears', 'sheep');"
            },
            "useToolOnBlock": {
                "params": ["tool_name", "block"],
                "description": "Use tool on specific block",
                "returns": "boolean (success)",
                "example": "await skills.useToolOnBlock(bot, 'diamond_axe', log);"
            },
            
            # Timing & Utility
            "wait": {
                "params": ["milliseconds"],
                "description": "Wait for specified time (safe, supports interruption)",
                "returns": "boolean (true if completed, false if interrupted)",
                "example": "await skills.wait(bot, 5000);"
            },
            "lookAtPlayer": {
                "params": ["username"],
                "description": "Look at a player",
                "returns": "void",
                "example": "await skills.lookAtPlayer(bot, 'steve');"
            },
            "lookAtPosition": {
                "params": ["x", "y", "z"],
                "description": "Look at specific coordinates",
                "returns": "void",
                "example": "await skills.lookAtPosition(bot, 100, 64, 200);"
            },
            "log": {
                "params": ["bot", "message"],
                "description": "Log a message (use instead of console.log)",
                "returns": "void",
                "example": "log(bot, 'Task completed!');"
            }
        }
    
    def get_skill_docs(self, skill_names: List[str] = None) -> str:
        """
        Get documentation for specific skills
        
        Args:
            skill_names: List of skill names (None = all skills)
        
        Returns:
            Formatted documentation string
        """
        if skill_names is None:
            skill_names = list(self.skills.keys())
        
        docs = "## Available Skills\n\n"
        
        for skill_name in skill_names:
            if skill_name not in self.skills:
                continue
            
            skill = self.skills[skill_name]
            params_str = ", ".join(skill['params'])
            
            docs += f"### {skill_name}({params_str})\n"
            docs += f"{skill['description']}\n"
            docs += f"Returns: {skill['returns']}\n"
            docs += f"Example: {skill['example']}\n\n"
        
        return docs
    
    def get_all_skill_names(self) -> List[str]:
        """Get list of all available skill and world function names"""
        # Include both skills and world functions
        all_names = list(self.skills.keys())
        # Add world functions from world.js
        world_funcs = [
            # From world.js export functions
            'getNearestFreeSpace', 'getBlockAtPosition', 'getSurroundingBlocks',
            'getFirstBlockAboveHead', 'getNearestBlocks', 'getNearestBlocksWhere',
            'getNearestBlock', 'getNearbyEntities', 'getNearestEntityWhere',
            'getNearbyPlayers', 'getVillagerProfession', 'getInventoryStacks',
            'getInventoryCounts', 'getCraftableItems', 'getPosition',
            'getNearbyEntityTypes', 'isEntityType', 'getNearbyPlayerNames',
            'getNearbyBlockTypes', 'shouldPlaceTorch', 'getBiomeName'
        ]
        all_names.extend(world_funcs)
        return all_names
    
    def validate_skill(self, skill_name: str, params: List[Any]) -> bool:
        """
        Validate skill name and parameter count
        
        Args:
            skill_name: Name of skill to validate
            params: List of parameters
        
        Returns:
            True if valid, False otherwise
        """
        if skill_name not in self.skills:
            logger.warning(f"Unknown skill: {skill_name}")
            return False
        
        expected_params = len(self.skills[skill_name]['params'])
        actual_params = len(params)
        
        if actual_params != expected_params:
            logger.warning(
                f"Skill {skill_name} expects {expected_params} params, "
                f"got {actual_params}"
            )
            return False
        
        return True
    
    def get_relevant_skills(self, task_description: str, max_skills: int = 10) -> List[str]:
        """
        Get relevant skills for a task
        
        Args:
            task_description: Description of the task
            max_skills: Maximum number of skills to return
        
        Returns:
            List of relevant skill names
        """
        # Keyword-based matching (simple but effective)
        task_lower = task_description.lower()
        relevant = []
        
        # Keyword-based matching
        keywords = {
            'move': ['goToPlayer', 'goToPosition', 'goToNearestBlock', 'goToNearestEntity', 'moveAway', 'followPlayer'],
            'go': ['goToPlayer', 'goToPosition', 'goToNearestBlock', 'goToNearestEntity', 'goToSurface'],
            'collect': ['collectBlock', 'pickupNearbyItems'],
            'mine': ['collectBlock', 'digDown'],
            'gather': ['collectBlock', 'pickupNearbyItems'],
            'attack': ['attackEntity', 'attackNearest', 'defendSelf'],
            'fight': ['defendSelf', 'attackEntity', 'attackNearest', 'avoidEnemies'],
            'kill': ['attackEntity', 'attackNearest', 'defendSelf'],
            'craft': ['craftRecipe', 'smeltItem'],
            'make': ['craftRecipe', 'placeBlock'],
            'build': ['placeBlock'],
            'place': ['placeBlock'],
            'look': ['lookAtPlayer', 'lookAtPosition'],
            'follow': ['followPlayer'],
            'avoid': ['avoidEnemies', 'moveAway', 'moveAwayFromEntity'],
            'eat': ['consume'],
            'food': ['consume'],
            'sleep': ['goToBed'],
            'bed': ['goToBed'],
            'equip': ['equipItem'],
            'chest': ['putInChest', 'takeFromChest', 'viewChest'],
            'store': ['putInChest'],
            'storage': ['putInChest', 'takeFromChest'],
            'trade': ['showVillagerTrades', 'tradeWithVillager'],
            'villager': ['showVillagerTrades', 'tradeWithVillager'],
            'farm': ['tillAndSow'],
            'plant': ['tillAndSow'],
            'door': ['useDoor'],
            'wait': ['wait', 'stay'],
            'give': ['giveToPlayer'],
            'dig': ['digDown', 'breakBlockAt'],
            'break': ['breakBlockAt'],
            'tool': ['useToolOn', 'useToolOnBlock'],
            'furnace': ['smeltItem', 'clearNearestFurnace'],
            'activate': ['activateNearestBlock'],
        }
        
        for keyword, skills in keywords.items():
            if keyword in task_lower:
                relevant.extend(skills)
        
        # Remove duplicates and limit
        relevant = list(dict.fromkeys(relevant))[:max_skills]
        
        # If no matches, return common skills
        if not relevant:
            relevant = ['goToPosition', 'goToNearestBlock', 'collectBlock', 'placeBlock', 
                       'craftRecipe', 'defendSelf', 'wait', 'consume']
        
        logger.debug(f"Relevant skills for '{task_description}': {relevant}")
        return relevant

# World query functions (from world.js)
WORLD_FUNCTIONS = """
## World Query Functions (use with world.functionName(bot, ...))

### world.getNearestBlock(bot, block_type, max_distance=16)
Find nearest block of a specific type
Returns: Block object or null
Example: let oakLog = world.getNearestBlock(bot, 'oak_log', 20);

### world.getNearestEntityWhere(bot, predicate, maxDistance=16)
Find nearest entity matching a filter predicate
Returns: Entity object or null
Example: let cow = world.getNearestEntityWhere(bot, e => e.name === 'cow', 16);

### world.getNearbyEntities(bot, maxDistance=16)
Get all nearby entities
Returns: Array of entities
Example: let entities = world.getNearbyEntities(bot, 20);

### world.getPosition(bot)
Get bot's current position
Returns: {x, y, z}
Example: let pos = world.getPosition(bot);

### world.getBiomeName(bot)
Get current biome name
Returns: Biome name string
Example: let biome = world.getBiomeName(bot);

### world.getInventoryCounts(bot)
Get inventory item counts as object
Returns: {item_name: count, ...}
Example: let inv = world.getInventoryCounts(bot);

### world.getNearbyPlayers(bot, maxDistance=16)
Get nearby players
Returns: Array of player entities
Example: let players = world.getNearbyPlayers(bot, 20);

### world.getNearestBlocks(bot, block_types=null, distance=8, count=10000)
Get list of nearest blocks of specified types
Returns: Array of block positions
Example: let trees = world.getNearestBlocks(bot, ['oak_log', 'birch_log'], 30);

### world.shouldPlaceTorch(bot)
Check if it's dark enough to place torch
Returns: boolean
Example: if (world.shouldPlaceTorch(bot)) { /* place torch */ }

### world.getCraftableItems(bot)
Get list of items that can be crafted with current inventory
Returns: Array of craftable item names
Example: let craftable = world.getCraftableItems(bot);
"""
