"""
Complete API Documentation Generator

Generates comprehensive API documentation for LLM code generation prompts.
Includes bot object, skills library, and world query functions.
"""

def get_bot_api_docs() -> str:
    """Get documentation for bot object properties and methods"""
    return """## Bot Object API (bot.*)

### Bot Properties
- **bot.entity.position**: Vec3 - The bot's current position {x, y, z}
- **bot.health**: number - Current health (0-20)
- **bot.food**: number - Current food level (0-20)
- **bot.heldItem**: Item|null - Item currently in the bot's main hand
- **bot.inventory**: Inventory - Bot's inventory object
- **bot.username**: string - Bot's username
- **bot.game.dimension**: string - Current dimension ('overworld', 'nether', 'end')
- **bot.game.gameMode**: string - Current game mode ('survival', 'creative', 'adventure')
- **bot.time.timeOfDay**: number - Time of day in ticks (0-23999)
- **bot.rainState**: number - Rain intensity (0 = no rain)
- **bot.thunderState**: number - Thunder intensity (0 = no thunder)

### Bot Methods (RARELY NEEDED - use skills.* instead)
- **bot.quit()**: Disconnect from server
- **bot.chat(message)**: Send a chat message
- **bot.setControlState(control, state)**: Set movement control (e.g., 'forward', true)

### Important Notes:
- DO NOT use bot methods directly for movement, mining, crafting, etc.
- ALWAYS use the skills.* library for game actions
- bot object is mainly for reading state (position, health, inventory)
- For inventory counts, use world.getInventoryCounts(bot) instead of bot.inventory
"""


def get_skills_api_docs() -> str:
    """Get complete documentation for skills library"""
    return """## Skills Library (skills.*)

### Movement Skills
- **async skills.goToPlayer(bot, username, distance=3)**: Navigate to a player's position
  - Returns: boolean (true if reached, false if failed)
  - Example: `await skills.goToPlayer(bot, 'Steve', 2);`

- **async skills.goToPosition(bot, x, y, z, min_distance=0.5)**: Navigate to specific coordinates
  - Returns: boolean (true if reached, false if failed)
  - Example: `await skills.goToPosition(bot, 100, 64, -200, 1.0);`

- **async skills.moveAway(bot, distance)**: Move away from current position
  - Returns: void
  - Example: `await skills.moveAway(bot, 10);`

- **async skills.followPlayer(bot, username, distance=3)**: Follow a player continuously
  - Returns: void
  - Example: `await skills.followPlayer(bot, 'Steve', 5);`

### Resource Gathering Skills
- **async skills.collectBlock(bot, blockType, num=1, exclude=null)**: Mine and collect blocks
  - Returns: number (actual amount collected, may be less than requested)
  - Example: `await skills.collectBlock(bot, 'oak_log', 10);`
  - Example with exclude: `await skills.collectBlock(bot, 'oak_log', 5, ['oak_leaves']);`
  - Note: Requires proper tool for some blocks (pickaxe for stone/ore, axe for logs faster)
  - **IMPORTANT**: Parameters are positional - do NOT use object syntax like `{exclude: [...], range: ...}`
  - exclude: Array of block names to ignore during collection (e.g., ['oak_leaves'])
  - **NO range parameter** - function automatically searches nearby area

- **async skills.pickupNearbyItems(bot)**: Pick up items on the ground
  - Returns: number (items picked up)
  - Example: `await skills.pickupNearbyItems(bot);`

### Combat Skills
- **async skills.attackEntity(bot, entity, kill=true)**: Attack a specific entity
  - Returns: boolean (success)
  - Example: `let zombie = world.getNearestEntityWhere(bot, e => e.name === 'zombie', 16); await skills.attackEntity(bot, zombie);`

- **async skills.defendSelf(bot, range=8)**: Defend against nearby enemies
  - Returns: void
  - Example: `await skills.defendSelf(bot, 16);`

- **async skills.avoidEnemies(bot, distance=16)**: Move away from all nearby enemies
  - Returns: void
  - Example: `await skills.avoidEnemies(bot, 20);`

### Crafting Skills
- **async skills.craftRecipe(bot, itemName, num=1)**: Craft items using available materials
  - Returns: boolean (success)
  - Example: `await skills.craftRecipe(bot, 'wooden_pickaxe', 1);`
  - Note: Will find crafting table if needed

- **async skills.smeltItem(bot, itemName, num=1)**: Smelt items in a furnace
  - Returns: number (amount smelted)
  - Example: `await skills.smeltItem(bot, 'iron_ore', 8);`
  - Note: Requires furnace and fuel

### Building Skills
- **async skills.placeBlock(bot, blockType, x, y, z, placeOn='bottom', dontCheat=false)**: Place a block at ABSOLUTE world coordinates
  - Parameters: x, y, z are ABSOLUTE world coordinates (NOT relative offsets!)
  - Returns: boolean (success)
  - Example: `let pos = world.getPosition(bot); await skills.placeBlock(bot, 'stone', pos.x + 2, pos.y, pos.z);`
  - Example: `await skills.placeBlock(bot, 'torch', 100, 64, 200, 'side');`
  - placeOn: 'top', 'bottom', 'north', 'south', 'east', 'west', 'side' (preferred side to place on)
  - dontCheat: set to true to override cheat mode and place normally
  - Note: Must have adjacent block to place against, cannot place in mid-air

### Inventory Skills
- **async skills.equip(bot, itemName)**: Equip an item from inventory to proper body part (hand, head, torso, legs, feet)
  - Returns: boolean (success)
  - Example: `await skills.equip(bot, 'diamond_sword');`
  - Note: Automatically detects item type and equips to correct slot (armor to armor slot, tools to hand)

### Interaction Skills
- **async skills.discard(bot, itemName, num=1)**: Drop items from inventory
  - Returns: boolean (success)
  - Example: `await skills.discard(bot, 'dirt', 64);`

### Advanced Movement Skills
- **async skills.goToNearestBlock(bot, blockType, min_distance=2, range=64)**: Go to nearest block of type
  - Returns: boolean (success)
  - Example: `await skills.goToNearestBlock(bot, 'crafting_table', 3, 32);`
  - Note: More convenient than getNearestBlock + goToPosition

- **async skills.goToNearestEntity(bot, entityType, min_distance=2, range=64)**: Go to nearest entity of type
  - Returns: boolean (success)
  - Example: `await skills.goToNearestEntity(bot, 'cow', 2, 32);`

- **async skills.goToGoal(bot, goal)**: Navigate to a pathfinder goal using optimized movements
  - Returns: boolean (success)
  - Example: `await skills.goToGoal(bot, new pf.goals.GoalNear(100, 64, 200, 1));`
  - Note: Use pathfinder goals like GoalNear, GoalBlock, GoalXZ, etc.

- **async skills.moveAwayFromEntity(bot, entity, distance=16)**: Move away from specific entity
  - Returns: void
  - Example: `let creeper = world.getNearestEntityWhere(bot, e => e.name === 'creeper', 16); await skills.moveAwayFromEntity(bot, creeper, 10);`

### Storage & Chest Skills
- **async skills.putInChest(bot, itemName, num=-1)**: Put items into nearest chest
  - Returns: boolean (success)
  - Example: `await skills.putInChest(bot, 'dirt', 64);`
  - Note: num=-1 means put all of that item

- **async skills.takeFromChest(bot, itemName, num=-1)**: Take items from nearest chest
  - Returns: boolean (success)
  - Example: `await skills.takeFromChest(bot, 'iron_ingot', 10);`

- **async skills.viewChest(bot)**: View contents of nearest chest
  - Returns: string (chest contents description)
  - Example: `let contents = await skills.viewChest(bot);`

### Advanced Combat Skills
- **async skills.attackNearest(bot, mobType, kill=true)**: Attack nearest mob of specific type
  - Returns: boolean (success)
  - Example: `await skills.attackNearest(bot, 'zombie', true);`
  - Note: More convenient than getNearestEntityWhere + attackEntity

### Building & Block Skills
- **async skills.breakBlockAt(bot, x, y, z)**: Break block at specific position (doesn't collect drops)
  - Returns: boolean (success)
  - Example: `await skills.breakBlockAt(bot, 100, 64, 200);`
  - Note: Different from collectBlock - this just breaks without collecting

- **async skills.activateNearestBlock(bot, type)**: Activate nearest block (button, lever, etc.)
  - Returns: boolean (success)
  - Example: `await skills.activateNearestBlock(bot, 'lever');`

### Survival & Daily Skills
- **async skills.consume(bot, itemName="")**: Eat food or drink potion
  - Returns: boolean (success)
  - Example: `await skills.consume(bot, 'bread');`
  - Note: More versatile than eat() - works with potions too

- **async skills.goToBed(bot)**: Sleep in nearest bed
  - Returns: boolean (success)
  - Example: `await skills.goToBed(bot);`
  - Note: Automatically finds and sleeps in bed to skip night

- **async skills.stay(bot, seconds=30)**: Stay in place for specified time
  - Returns: void
  - Example: `await skills.stay(bot, 60);`

- **async skills.useDoor(bot, door_pos=null)**: Use/open door
  - Returns: boolean (success)
  - Example: `await skills.useDoor(bot);` (finds nearest) or `await skills.useDoor(bot, door_position);`

### Farming Skills
- **async skills.tillAndSow(bot, x, y, z, seedType=null)**: Till ground and plant seeds
  - Returns: boolean (success)
  - Example: `await skills.tillAndSow(bot, 100, 64, 200, 'wheat_seeds');`

### Furnace Skills
- **async skills.clearNearestFurnace(bot)**: Clear items from nearest furnace
  - Returns: boolean (success)
  - Example: `await skills.clearNearestFurnace(bot);`

### Villager Trading Skills
- **async skills.showVillagerTrades(bot, id)**: Show available trades from villager
  - Returns: string (trade list)
  - Example: `let trades = await skills.showVillagerTrades(bot, '12345');`

- **async skills.tradeWithVillager(bot, id, index, count)**: Trade with villager
  - Returns: boolean (success)
  - Example: `await skills.tradeWithVillager(bot, '12345', 0, 1);`

### Mining & Exploration Skills
- **async skills.digDown(bot, distance=10)**: Safely dig straight down with automatic safety checks
  - Returns: boolean (true if successfully dug, false if stopped early due to hazards)
  - Safety: Automatically stops if it reaches lava, water, or a fall > 2 blocks
  - Example: `await skills.digDown(bot, 20);`
  - **PREFERRED over manual downward digging** - has built-in safety

- **async skills.goToSurface(bot)**: Navigate to the surface (highest non-air block)
  - Returns: boolean (success)
  - Use when: Underground, in a cave, or stuck in a hole
  - Example: `await skills.goToSurface(bot);`

### Tool Usage Skills
- **async skills.useToolOn(bot, toolName, targetName)**: Use tool on target block/entity
  - Returns: boolean (success)
  - Example: `await skills.useToolOn(bot, 'shears', 'sheep');`

- **async skills.useToolOnBlock(bot, toolName, block)**: Use tool on specific block
  - Returns: boolean (success)
  - Example: `let log = world.getNearestBlock(bot, 'oak_log', 16); await skills.useToolOnBlock(bot, 'diamond_axe', log);`

### Social Skills
- **async skills.giveToPlayer(bot, itemType, username, num=1)**: Give items to player
  - Returns: boolean (success)
  - Example: `await skills.giveToPlayer(bot, 'diamond', 'Steve', 5);`

### Timing & Control Skills
- **async skills.wait(bot, milliseconds)**: Wait for specified time (SAFE, supports interruption)
  - Returns: boolean (true if completed, false if interrupted)
  - Example: `await skills.wait(bot, 5000);` (wait 5 seconds)
  - Note: This is the CORRECT way to wait - NOT setTimeout!

### Utility Skills
- **skills.log(bot, message)**: Log a message (ALWAYS use this instead of console.log)
  - Returns: void
  - Example: `log(bot, 'Task completed!');`
  - NOTE: This is NOT async, no await needed

### Important Notes:
- ALL skills (except log) are async and MUST be awaited
- skills.log(bot, message) is NOT async - do NOT use await
- Use skills.collectBlock, NOT skills.mineBlock (mineBlock doesn't exist)
- Use skills.wait(bot, ms) for delays, NOT setTimeout
- Always check return values to verify success
- For mining, the bot needs appropriate tools (pickaxe for stone/ores, etc.)
- **CRITICAL**: All skill functions use POSITIONAL parameters - do NOT use object syntax
  - ❌ WRONG: `await skills.collectBlock(bot, 'oak_log', { num: 5, exclude: ['leaves'] })`
  - ✅ CORRECT: `await skills.collectBlock(bot, 'oak_log', 5, ['leaves'])`

### CRITICAL: Coordinate System Usage
**ABSOLUTE COORDINATES (world coordinates):**
- skills.placeBlock(bot, type, x, y, z) - uses ABSOLUTE world coordinates
- skills.goToPosition(bot, x, y, z) - uses ABSOLUTE world coordinates
- Block.position - contains ABSOLUTE world coordinates
- world.getPosition(bot) - returns ABSOLUTE world coordinates
- Example: If bot is at (100, 64, 200), to place block 2 blocks north use: placeBlock(bot, 'stone', 100, 64, 198)

**RELATIVE COORDINATES (offset from bot):**
- world.getBlockAtPosition(bot, x, y, z) - uses RELATIVE offsets from bot's position
- Example: To check block 2 blocks north of bot use: getBlockAtPosition(bot, 0, 0, -2)
- Example: To check block below bot use: getBlockAtPosition(bot, 0, -1, 0)
- Example: To check block 1 east and 1 up use: getBlockAtPosition(bot, 1, 1, 0)
"""


def get_world_api_docs() -> str:
    """Get complete documentation for world query functions"""
    return """## World Query Library (world.*)

### Spatial Awareness Functions
**Use these to understand your environment and avoid getting stuck/trapped:**

- **world.getSurroundingBlocks(bot)**: Get blocks around bot (below, legs, head)
  - Returns: Array of strings ["Block Below: grass", "Block at Legs: air", "Block at Head: air"]
  - Use to check: Am I standing on solid ground? Am I in water/lava?
  - Example: `let surrounding = world.getSurroundingBlocks(bot);`

- **world.getFirstBlockAboveHead(bot, ignore_types=null, distance=32)**: Find first solid block above
  - Returns: string (e.g., "stone (5 blocks up)") or "none"
  - **Critical for cave/hole detection**: 
    * "none" = outdoors/open sky
    * "stone (2 blocks up)" = in a cave or hole
    * "leaves (15 blocks up)" = under a tree
  - Example: `let above = world.getFirstBlockAboveHead(bot, null, 32);`

- **world.getBlockAtPosition(bot, x, y, z)**: Get block at RELATIVE offset from bot's position
  - Parameters: x, y, z are RELATIVE offsets (NOT absolute world coordinates!)
  - Returns: Block object {name, position, ...}
  - Example: `let blockBelow = world.getBlockAtPosition(bot, 0, -1, 0);` (directly below)
  - Example: `let blockNorth = world.getBlockAtPosition(bot, 0, 0, -2);` (2 blocks north)
  - Example: `let blockEastAndUp = world.getBlockAtPosition(bot, 1, 1, 0);` (1 east, 1 up)
  - WARNING: Do NOT use absolute coordinates like getBlockAtPosition(bot, 587, 72, 121)!

### Block Query Functions
- **world.getNearestBlock(bot, block_type, distance=16)**: Find nearest block of a type
  - Returns: Block object {name, position, ...} or null
  - Example: `let tree = world.getNearestBlock(bot, 'oak_log', 32);`

- **world.getNearestBlocks(bot, block_types=null, distance=8, count=10000)**: Get list of nearest blocks
  - Returns: Array of Block objects
  - Example: `let trees = world.getNearestBlocks(bot, ['oak_log', 'birch_log'], 32);`
  - Note: block_types can be null to get all blocks, or array of block names

- **world.getNearestBlocksWhere(bot, predicate, distance=8, count=10000)**: Get blocks matching predicate function
  - Returns: Array of Block objects
  - Example: `let waterBlocks = world.getNearestBlocksWhere(bot, block => block.name === 'water', 16, 10);`
  - Note: More flexible than getNearestBlocks - use custom predicate function

- **world.getNearbyBlockTypes(bot, distance=16)**: Get unique block types nearby
  - Returns: Array of block names (strings)
  - Example: `let blockTypes = world.getNearbyBlockTypes(bot, 32);`

### Entity Query Functions
- **world.getNearbyEntities(bot, maxDistance=16)**: Get all nearby entities
  - Returns: Array of Entity objects
  - Example: `let entities = world.getNearbyEntities(bot, 20);`

- **world.getNearestEntityWhere(bot, predicate, maxDistance=16)**: Find entity matching condition
  - Returns: Entity object or null
  - Example: `let cow = world.getNearestEntityWhere(bot, e => e.name === 'cow', 16);`

- **world.getNearbyPlayers(bot, maxDistance=16)**: Get nearby players
  - Returns: Array of Player entities
  - Example: `let players = world.getNearbyPlayers(bot, 32);`

- **world.getNearbyPlayerNames(bot)**: Get nearby player usernames
  - Returns: Array of strings (player names)
  - Example: `let playerNames = world.getNearbyPlayerNames(bot);`

- **world.getNearbyEntityTypes(bot)**: Get unique entity types nearby
  - Returns: Array of entity type names
  - Example: `let entityTypes = world.getNearbyEntityTypes(bot);`

- **world.isEntityType(name)**: Check if a name is a valid entity type
  - Returns: boolean
  - Example: `if (world.isEntityType('zombie')) { ... }`

- **world.getVillagerProfession(entity)**: Get villager's profession from entity
  - Returns: string (profession name like 'Farmer', 'Librarian', 'Unemployed', etc.)
  - Example: `let villager = world.getNearestEntityWhere(bot, e => e.name === 'villager', 16); let job = world.getVillagerProfession(villager);`
  - Note: Returns profession based on villager metadata

### Path & Navigation Functions
- **async world.isClearPath(bot, target)**: Check if there's a clear path to target without digging/placing
  - Returns: boolean (true if path exists without obstacles)
  - Example: `let canReach = await world.isClearPath(bot, targetEntity);`
  - Note: This is async - must use await. Checks pathfinding without breaking/placing blocks

### Inventory & Crafting Functions
- **world.getInventoryCounts(bot)**: Get inventory as {item: count} object
  - Returns: Object {item_name: count, ...}
  - Example: `let inv = world.getInventoryCounts(bot);`
  - Example usage: `let logs = inv['oak_log'] || 0;`

- **world.getInventoryStacks(bot)**: Get all inventory item stacks
  - Returns: Array of Item objects
  - Example: `let stacks = world.getInventoryStacks(bot);`

- **world.getCraftableItems(bot)**: Get list of craftable items with current inventory
  - Returns: Array of craftable item names
  - Example: `let craftable = world.getCraftableItems(bot);`

### Position & Environment Functions
- **world.getPosition(bot)**: Get bot's current position
  - Returns: Vec3 {x, y, z}
  - Example: `let pos = world.getPosition(bot);`

- **world.getBiomeName(bot)**: Get current biome name
  - Returns: string (biome name)
  - Example: `let biome = world.getBiomeName(bot);`

- **world.getNearestFreeSpace(bot, size=1, distance=8)**: Find nearest empty space
  - Returns: Vec3 position or null
  - Example: `let freeSpace = world.getNearestFreeSpace(bot, 2, 16);`

### Utility Functions
- **world.shouldPlaceTorch(bot)**: Check if light level is low enough to place torch
  - Returns: boolean
  - Example: `if (world.shouldPlaceTorch(bot)) { await skills.placeBlock(bot, 'torch', ...); }`

### Important Notes:
- MOST world functions are synchronous (NOT async) - do NOT use await
- EXCEPTION: world.isClearPath is async and MUST use await
- world.getInventoryCounts is the preferred way to check inventory
- Block objects have properties: name, position, type, metadata
- Entity objects have properties: name, position, type, health
- Use Vec3 for positions: has x, y, z properties
"""


def get_full_api_docs() -> str:
    """
    Get complete API documentation including bot, skills, and world libraries
    
    Returns:
        Formatted markdown documentation string
    """
    docs = "# Complete Minecraft Bot API Documentation\n\n"
    docs += "This is a comprehensive reference of all available APIs for writing bot code.\n\n"
    docs += "## Quick Reference\n"
    docs += "- **bot.*** - Bot object properties (read-only, for state checking)\n"
    docs += "- **skills.*** - Action functions (async, use await)\n"
    docs += "- **world.*** - Query functions (sync, no await)\n"
    docs += "- **Vec3** - Position/vector class with x, y, z properties\n"
    docs += "- **log(bot, message)** - Logging function (NOT async)\n\n"
    
    docs += "---\n\n"
    docs += get_bot_api_docs()
    docs += "\n---\n\n"
    docs += get_skills_api_docs()
    docs += "\n---\n\n"
    docs += get_world_api_docs()
    
    docs += "\n---\n\n"
    docs += "## Common Patterns\n\n"
    docs += """### Check inventory before action:
```javascript
const inventory = world.getInventoryCounts(bot);
const hasPickaxe = Object.keys(inventory).some(item => item.includes('pickaxe'));
if (!hasPickaxe) {
    throw new Error("Need a pickaxe to mine stone!");
}
```

### Find and collect a block:
```javascript
const coalOre = world.getNearestBlock(bot, 'coal_ore', 32);
if (!coalOre) {
    throw new Error("No coal ore found nearby");
}
await skills.collectBlock(bot, 'coal_ore', 1);
```

### Verify success by checking inventory:
```javascript
const invBefore = world.getInventoryCounts(bot);
const coalBefore = invBefore['coal'] || 0;

await skills.collectBlock(bot, 'coal_ore', 5);

const invAfter = world.getInventoryCounts(bot);
const coalAfter = invAfter['coal'] || 0;
const actualCollected = coalAfter - coalBefore;

if (actualCollected < 5) {
    throw new Error(`Only collected ${actualCollected} coal, expected 5`);
}
```

### Attack nearest enemy:
```javascript
const zombie = world.getNearestEntityWhere(bot, e => e.name === 'zombie', 16);
if (zombie) {
    await skills.attackEntity(bot, zombie);
    log(bot, 'Attacked zombie!');
}
```

## CRITICAL REMINDERS:
1. ✅ Use `await` for ALL skills.* functions (except skills.log)
2. ❌ Do NOT use `await` for world.* functions (they are synchronous)
3. ✅ Use `log(bot, message)` for logging, NOT console.log
4. ✅ Use `skills.collectBlock`, NOT `skills.mineBlock` (doesn't exist)
5. ✅ Use `await skills.wait(bot, milliseconds)` for delays, NOT setTimeout
6. ✅ Always verify actions by checking state before/after
7. ✅ Throw errors when goals aren't met: `throw new Error("message")`
8. ✅ Use skills.goToNearestBlock instead of world.getNearestBlock + skills.goToPosition
9. ✅ Use skills.consume for eating, skills.goToBed for sleeping
10. ✅ Check inventory with world.getInventoryCounts(bot) before crafting/using items
"""
    
    return docs
