/**
 * Three-Layer Brain Bridge
 * 
 * Connects JavaScript Mineflayer bot to Python Three-Layer Brain system via IPC (ZeroMQ).
 * 
 * Responsibilities:
 * - Initialize Mineflayer bot and connect to Minecraft server
 * - Send game state updates to Python brain
 * - Receive and execute code from Python brain
 * - Handle chat messages
 */

import { createBot } from 'mineflayer';
import pathfinderPkg from 'mineflayer-pathfinder';
const { pathfinder, Movements, goals } = pathfinderPkg;
import pvpPkg from 'mineflayer-pvp';
import collectblockPkg from 'mineflayer-collectblock';
import autoEatPkg from 'mineflayer-auto-eat';
import armorManagerPkg from 'mineflayer-armor-manager';

// Extract plugin functions from CommonJS modules
const pvpPlugin = pvpPkg.plugin || pvpPkg.default?.plugin || pvpPkg.default || pvpPkg;
const collectblockPlugin = collectblockPkg.plugin || collectblockPkg.default?.plugin || collectblockPkg.default || collectblockPkg;
const autoEatPlugin = autoEatPkg.plugin || autoEatPkg.default?.plugin || autoEatPkg.default || autoEatPkg;
const armorManagerPlugin = armorManagerPkg.plugin || armorManagerPkg.default?.plugin || armorManagerPkg.default || armorManagerPkg;

// Import skills and world libraries from original agent code
import * as skills from '../../src/agent/library/skills.js';
import * as world from '../../src/agent/library/world.js';
import * as mcdata from '../../src/utils/mcdata.js';

import zmq from 'zeromq';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import Vec3 from 'vec3';

// Get directory path for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load configuration from project root (2 levels up from agent/bridge)
const projectRoot = path.resolve(__dirname, '../..');
const configPath = path.join(projectRoot, 'profiles', 'three_layer_brain.json');

console.log('Loading config from:', configPath);

const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

// Import settings.js directly (same as original project)
const settingsModule = await import('../../settings.js');
const settings = settingsModule.default;

class BrainBridge {
    constructor() {
        this.bot = null;
        this.reqSocket = null;  // REQ socket for requests to Python
        this.subSocket = null;  // SUB socket for commands from Python
        this.config = config;  // Store config reference
        this.pythonPort = config.ipc_port || 9000;
        this.connected = false;

        // Message queue to prevent REQ socket EBUSY errors
        this.messageQueue = [];
        this.isSending = false;

        // Time tracking for agent age calculation
        // Track total game ticks played across all worlds/sessions
        this.totalTicksPlayed = 0;  // Cumulative ticks played (persists across worlds)
        this.lastTimeOfDay = null;  // Last recorded timeOfDay (0-23999), null on init

        // Track background code execution (for concurrent command handling)
        this.codeExecutionPromise = null;
    }

    async initIPC() {
        console.log(`Connecting to Python brain on ports ${this.pythonPort}-${this.pythonPort + 1}...`);

        // REQ socket for sending state to Python
        this.reqSocket = new zmq.Request();
        await this.reqSocket.connect(`tcp://localhost:${this.pythonPort}`);

        // SUB socket for receiving commands from Python
        this.subSocket = new zmq.Subscriber();
        await this.subSocket.connect(`tcp://localhost:${this.pythonPort + 1}`);
        this.subSocket.subscribe(''); // Subscribe to all messages

        console.log('IPC connection established');
        this.connected = true;

        // Start listening for commands
        this.startCommandListener();
    }

    async startCommandListener() {
        console.log('Listening for commands from Python...');

        for await (const [msg] of this.subSocket) {
            try {
                const command = JSON.parse(msg.toString());
                // 🔥 Remove await to enable concurrent command handling
                this.handleCommand(command);
            } catch (error) {
                console.error('Error handling command:', error);
            }
        }
    }

    handleCommand(command) {
        const { type, data } = command;

        // Only log important commands (not frequent execution commands)
        if (type !== 'execute_code' && type !== 'execute_skill' && type !== 'reflex' && type !== 'set_interrupt_flag') {
            console.log(`Received command: ${type}`);
        }

        switch (type) {
            case 'execute_code':
                // Execute code in background, don't block other commands
                // Pass priority flag if provided (for low-level mode checks)
                this.executeCodeInBackground(data.code, data.priority || 'normal');
                break;

            case 'set_interrupt_flag':
                // ⚡ Set interrupt flag immediately - code interrupt checks will take effect in real-time
                if (this.bot && typeof data.value === 'boolean') {
                    this.bot.interrupt_code = data.value;
                    if (data.value) {
                        console.log('🛑 Interrupt flag set: bot.interrupt_code = true');
                    } else {
                        console.log('✅ Interrupt flag cleared: bot.interrupt_code = false');
                    }
                }
                break;

            case 'chat':
            case 'reflex':
            case 'execute_skill':
                // Execute immediate commands without blocking
                this.handleImmediateCommand(type, data);
                break;

            case 'request_state_update':
                // Python requested fresh state - send it immediately
                this.sendStateUpdate();
                break;

            case 'shutdown':
                // Graceful shutdown requested
                console.log(`Shutdown requested: ${data.reason}`);
                this.gracefulShutdown(data.reason);
                break;

            default:
                console.warn(`Unknown command type: ${type}`);
        }
    }

    executeCodeInBackground(code) {
        // ExecutionCoordinator now manages concurrency at Python level
        // JavaScript just executes what Python sends

        // Start new code execution (non-blocking)
        this.codeExecutionPromise = this.executeCode(code)
            .catch(err => {
                console.error('Background code execution error:', err);
                // Send error result to Python
                this.sendMessage({
                    type: 'execution_result',
                    data: {
                        success: false,
                        message: err.message || 'Code execution error'
                    }
                });
            })
            .finally(() => {
                this.codeExecutionPromise = null;
            });
        // Function returns immediately, code runs in background
    }

    async executeCode(code) {
        // console.log('Executing generated code...');  // Too verbose for modes
        // console.log('Code:', code);  // Too verbose for modes

        try {
            // Initialize bot.output for logging (similar to original agent)
            this.bot.output = '';

            // Reset interrupt flag before execution
            this.bot.interrupt_code = false;

            // Get state before execution
            const stateBefore = {
                position: this.bot.entity.position.clone(),
                health: this.bot.health,
                food: this.bot.food,
                inventory: world.getInventoryCounts(this.bot)
            };

            // Create execution context with skills and world (matching original agent)
            // This matches the original Coder's execution environment
            const context = {
                bot: this.bot,
                skills: skills,
                world: world,
                goals: goals,
                Vec3: Vec3,
                log: skills.log  // Provide log function
            };

            // Wrap code in async function (same as original Coder)
            // Important: We need to return the Promise so errors can be caught
            const wrappedCode = `
                return (async function(bot, skills, world, goals, Vec3, log) {
                    ${code}
                })(context.bot, context.skills, context.world, context.goals, context.Vec3, context.log);
            `;

            // Execute code and properly await the returned Promise
            // This ensures errors thrown inside the async function are caught
            // console.log('Starting code execution...');  // Too verbose for modes
            const executeFunction = new Function('context', wrappedCode);
            await executeFunction(context);
            // console.log('Code execution completed');  // Too verbose for modes

            // Check if code was interrupted
            if (this.bot.interrupt_code) {
                // Code was interrupted by chat - mark task as failed
                const code_output = this.bot.output || 'No output';

                await this.sendMessage({
                    type: 'execution_result',
                    data: {
                        success: false,
                        interrupted: true,
                        output: code_output,
                        message: `Task interrupted by chat message. No need to summarize, just try again. Output: ${code_output}`
                    }
                });

                console.log('⚠️ Code execution interrupted by chat');
                return;
            }

            // Get state after execution
            const stateAfter = {
                position: this.bot.entity.position.clone(),
                health: this.bot.health,
                food: this.bot.food,
                inventory: world.getInventoryCounts(this.bot)
            };

            // Get bot output (logs generated by skills.log())
            const code_output = this.bot.output || 'No output';

            // Calculate what changed
            const changes = {
                position_changed: !stateBefore.position.equals(stateAfter.position),
                health_changed: stateBefore.health !== stateAfter.health,
                food_changed: stateBefore.food !== stateAfter.food,
                inventory_changed: JSON.stringify(stateBefore.inventory) !== JSON.stringify(stateAfter.inventory)
            };

            // Send detailed result back to Python
            await this.sendMessage({
                type: 'execution_result',
                data: {
                    success: true,
                    output: code_output,
                    state_before: stateBefore,
                    state_after: stateAfter,
                    changes: changes,
                    message: `Code executed successfully. Output: ${code_output}`
                }
            });

            // Only log if there's meaningful output or changes
            if (code_output !== 'No output' || Object.values(changes).some(c => c)) {
                console.log('Code executed:', code_output);
            }

        } catch (error) {
            console.error('Code execution failed:', error);
            console.error('Stack trace:', error.stack);

            // Get any output that was generated before the error
            const code_output = this.bot.output || 'No output before error';

            await this.sendMessage({
                type: 'execution_result',
                data: {
                    success: false,
                    error: error.message,
                    error_stack: error.stack,
                    output: code_output,
                    message: `Execution failed: ${error.message}\nOutput before error: ${code_output}`
                }
            });
        } finally {
            // Clean up
            this.bot.output = '';
        }
    }

    async handleImmediateCommand(type, data) {
        // Handle immediate commands that should not be blocked by code execution
        switch (type) {
            case 'chat':
                // Send chat message immediately
                try {
                    const playerName = data.player_name || data.player;

                    // Remove emojis and non-ASCII characters, replacing with space to avoid word merging
                    let cleanMessage = data.message
                        .replace(/[\u{1F600}-\u{1F64F}]/gu, ' ')  // Emoticons
                        .replace(/[\u{1F300}-\u{1F5FF}]/gu, ' ')  // Misc Symbols and Pictographs
                        .replace(/[\u{1F680}-\u{1F6FF}]/gu, ' ')  // Transport and Map
                        .replace(/[\u{2600}-\u{26FF}]/gu, ' ')   // Misc symbols
                        .replace(/[\u{2700}-\u{27BF}]/gu, ' ')   // Dingbats
                        .replace(/[\u{1F900}-\u{1F9FF}]/gu, ' ')  // Supplemental Symbols and Pictographs
                        .replace(/[\u{1F1E6}-\u{1F1FF}]/gu, ' ')  // Flags
                        .replace(/[^\x20-\x7E]/g, ' ')           // Replace non-ASCII with space
                        .replace(/\s+/g, ' ')                    // Collapse multiple spaces
                        .trim();

                    if (cleanMessage) {
                        console.log(`💬 Immediate chat: ${cleanMessage}`);

                        // Use /say command to broadcast to all players (bypasses chat signing)
                        this.bot.chat(`/say ${cleanMessage}`);
                    } else {
                        console.warn('Chat message became empty after filtering');
                    }
                } catch (err) {
                    console.error('Failed to send chat message:', err.message);
                }
                break;

            case 'reflex':
                // Execute immediate reflex action
                await this.executeReflex(data);
                break;

            case 'execute_skill':
                // Execute a specific skill
                await this.executeSkill(data);
                break;

            default:
                console.warn(`Unknown immediate command type: ${type}`);
        }
    }
    async executeReflex(data) {
        // Execute immediate reflex actions
        const { action, params } = data;

        try {
            switch (action) {
                case 'combat':
                    // Auto-attack nearest enemy
                    const enemy = this.bot.nearestEntity(e => e.type === 'mob');
                    if (enemy) {
                        this.bot.pvp.attack(enemy);
                    }
                    break;

                case 'flee':
                    // Run away
                    this.bot.pathfinder.setGoal(null);
                    break;

                case 'eat':
                    // Eat food
                    await this.bot.autoEat.eat();
                    break;

                default:
                    console.warn(`Unknown reflex action: ${action}`);
            }
        } catch (error) {
            console.error('Reflex execution failed:', error);
        }
    }

    async executeSkill(data) {
        // Execute a skill call from low-level brain
        const { skill, params } = data;

        try {
            // Check if skill exists in skills module
            if (typeof skills[skill] !== 'function') {
                console.error(`Skill not found: ${skill}`);
                return;
            }

            // Call the skill with bot and parameters
            // Most skills expect (bot, ...params) signature
            await skills[skill](this.bot, ...params);

        } catch (error) {
            console.error(`Skill execution failed (${skill}):`, error.message);
        }
    }

    async loadPlaytime() {
        /**
         * Load agent's cumulative playtime from disk
         * 
         * Playtime is stored as total game ticks played across all worlds.
         * Age = totalTicksPlayed / 24000 (game days)
         */
        const agentName = config.agent_name || 'BrainyBot';
        const playtimeFile = path.join(projectRoot, 'bots', agentName, 'playtime.json');

        console.log(`[Playtime] Loading from: ${playtimeFile}`);

        try {
            // Try to load existing playtime
            if (fs.existsSync(playtimeFile)) {
                const data = JSON.parse(fs.readFileSync(playtimeFile, 'utf8'));
                this.totalTicksPlayed = data.total_ticks_played || 0;

                const ageDays = Math.floor(this.totalTicksPlayed / 24000);
                console.log(`[Playtime] Loaded: ${this.totalTicksPlayed} ticks (${ageDays} game days)`);
            } else {
                // First spawn - start from zero
                this.totalTicksPlayed = 0;
                console.log(`[Playtime] First spawn! Starting playtime tracking from 0`);

                // Save initial playtime file
                this.savePlaytime();
            }
        } catch (error) {
            console.error('[Playtime] Error loading playtime:', error);
            this.totalTicksPlayed = 0;
        }
    }

    savePlaytime() {
        /**
         * Save cumulative playtime to disk
         */
        try {
            const agentName = config.agent_name || 'BrainyBot';
            const playtimeFile = path.join(projectRoot, 'bots', agentName, 'playtime.json');

            // Create directory if doesn't exist
            const dir = path.dirname(playtimeFile);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
                console.log(`[Playtime] Created directory: ${dir}`);
            }

            const ageDays = Math.floor(this.totalTicksPlayed / 24000);

            const data = {
                agent_name: this.config.agent_name || 'BrainyBot',
                minecraft_username: this.bot?.username,
                total_ticks_played: this.totalTicksPlayed,
                age_in_game_days: ageDays,
                last_updated: new Date().toISOString()
            };

            fs.writeFileSync(playtimeFile, JSON.stringify(data, null, 2));
            console.log(`[Playtime] Saved to ${playtimeFile}`);
        } catch (error) {
            console.error('[Playtime] Error saving playtime:', error);
        }
    }

    async gracefulShutdown(reason) {
        /**
         * Gracefully shutdown the bot
         * - Save playtime
         * - Disconnect from server
         * - Exit process
         */
        console.log(`\n=== GRACEFUL SHUTDOWN ===`);
        console.log(`Reason: ${reason}`);

        try {
            // Save final playtime
            console.log('Saving playtime...');
            this.savePlaytime();
            console.log('Playtime saved successfully');

            // Disconnect from server
            if (this.bot) {
                console.log('Disconnecting from Minecraft server...');
                this.bot.quit('Shutting down gracefully');
            }

            // Close ZMQ sockets
            if (this.reqSocket) {
                this.reqSocket.close();
            }
            if (this.subSocket) {
                this.subSocket.close();
            }

            console.log('Shutdown complete. Exiting...');

            // Exit process after a short delay to ensure everything is flushed
            setTimeout(() => {
                process.exit(0);
            }, 500);

        } catch (error) {
            console.error('Error during graceful shutdown:', error);
            process.exit(1);
        }
    }

    async sendMessage(message) {
        if (!this.connected) return;

        // Add message to queue
        return new Promise((resolve, reject) => {
            this.messageQueue.push({ message, resolve, reject });
            this.processMessageQueue();
        });
    }

    async processMessageQueue() {
        // If already processing, return (queue will be processed)
        if (this.isSending || this.messageQueue.length === 0) {
            return;
        }

        this.isSending = true;

        while (this.messageQueue.length > 0) {
            const { message, resolve, reject } = this.messageQueue.shift();

            try {
                await this.reqSocket.send(JSON.stringify(message));
                const [response] = await this.reqSocket.receive();
                resolve(JSON.parse(response.toString()));
            } catch (error) {
                console.error('Error sending message to Python:', error);
                reject(error);
            }
        }

        this.isSending = false;
    }

    async sendStateUpdate() {
        if (!this.bot || !this.connected) return;

        // Calculate agent age using cumulative playtime (totalTicksPlayed)
        // This ensures age persists across world changes and reflects actual playtime
        const currentDay = this.bot.time.day;  // Current world day
        const currentTimeOfDay = this.bot.time.timeOfDay;  // 0-23999
        const currentTotalTicks = Number(this.bot.time.bigTime);  // Current world ticks

        // Agent age is based on cumulative playtime (already updated by interval)
        const ageDays = Math.floor(this.totalTicksPlayed / 24000);
        const ageHours = Math.floor((this.totalTicksPlayed % 24000) / 1000);

        // Weather state (like original MindCraft)
        let weather = 'Clear';
        if (this.bot.thunderState > 0) weather = 'Thunderstorm';
        else if (this.bot.rainState > 0) weather = 'Rain';

        // Time label (like original MindCraft)
        let timeLabel = 'Night';
        if (currentTimeOfDay < 6000) timeLabel = 'Morning';
        else if (currentTimeOfDay < 12000) timeLabel = 'Afternoon';

        // Equipment (like original MindCraft)
        const helmet = this.bot.inventory.slots[5];
        const chestplate = this.bot.inventory.slots[6];
        const leggings = this.bot.inventory.slots[7];
        const boots = this.bot.inventory.slots[8];
        const equipment = {
            helmet: helmet ? helmet.name : null,
            chestplate: chestplate ? chestplate.name : null,
            leggings: leggings ? leggings.name : null,
            boots: boots ? boots.name : null,
            mainHand: this.bot.heldItem ? this.bot.heldItem.name : null
        };

        const state = {
            type: 'state_update',
            data: {
                position: this.bot.entity.position,
                health: this.bot.health,
                food: this.bot.food,
                inventory: this.getInventory(),
                biome: this.bot.game.dimension,
                dimension: this.bot.game.dimension,
                gamemode: this.bot.game.gameMode,
                time_of_day: currentTimeOfDay,
                time_label: timeLabel,
                weather: weather,

                // World time (current world only, may reset)
                world_day: currentDay,
                world_time: currentTotalTicks,

                // Agent age (cumulative across all worlds)
                agent_age_days: ageDays,
                agent_age_hours: ageHours,
                agent_age_ticks: this.totalTicksPlayed,

                nearby_entities: this.getNearbyEntities(),
                nearby_blocks: this.getNearbyBlocks(),
                surrounding_blocks: this.getSurroundingBlocks(),  // Add detailed position blocks
                equipment: equipment
            }
        };

        await this.sendMessage(state);
    }

    getInventory() {
        const inv = {};
        this.bot.inventory.items().forEach(item => {
            inv[item.name] = (inv[item.name] || 0) + item.count;
        });
        return inv;
    }

    getNearbyEntities() {
        return Object.values(this.bot.entities)
            .filter(e => e.position.distanceTo(this.bot.entity.position) < 16)
            .map(e => ({
                type: e.type,
                name: e.type === 'player' ? e.username : e.name,
                position: e.position,
                health: e.metadata[7]
            }));
    }

    getNearbyBlocks() {
        // Simplified - get blocks in 3x3x3 area
        const blocks = [];
        const pos = this.bot.entity.position;

        for (let x = -1; x <= 1; x++) {
            for (let y = -1; y <= 1; y++) {
                for (let z = -1; z <= 1; z++) {
                    const block = this.bot.blockAt(pos.offset(x, y, z));
                    if (block && block.name !== 'air') {
                        blocks.push({
                            name: block.name,
                            position: block.position,
                            metadata: block.metadata || 0
                        });
                    }
                }
            }
        }

        return blocks;
    }

    getSurroundingBlocks() {
        // Like original MindCraft: get blocks at specific positions
        const pos = this.bot.entity.position;
        const below = this.bot.blockAt(pos.offset(0, -1, 0));
        const legs = this.bot.blockAt(pos.offset(0, 0, 0));
        const head = this.bot.blockAt(pos.offset(0, 1, 0));

        // Find first solid block above head
        let firstAbove = null;
        for (let i = 2; i < 10; i++) {
            const block = this.bot.blockAt(pos.offset(0, i, 0));
            if (block && block.name !== 'air') {
                firstAbove = block;
                break;
            }
        }

        return {
            below: below ? below.name : 'void',
            legs: legs ? legs.name : 'air',
            head: head ? head.name : 'air',
            firstAbove: firstAbove ? firstAbove.name : 'none'
        };
    }

    async initBot() {
        console.log('Initializing Mineflayer bot...');

        // Use same logic as original project's initBot function
        const options = {
            username: config.agent_name || 'BrainyBot',
            host: settings.host,
            port: settings.port,
            auth: settings.auth,
            version: settings.minecraft_version,
            // Disable chat signing for Minecraft 1.19.1+ compatibility
            // This fixes the "value out of range" error when sending chat messages
            chatLengthLimit: 256,
            hideErrors: false,  // Show errors for debugging
            // Skip session server for offline mode (prevents authentication issues)
            skipValidation: settings.auth === 'offline',
            // Disable chat signing to prevent i8 range errors in 1.19+
            sessionServer: false,
            checkTimeoutInterval: 60 * 1000
        };

        // Auto-detect version if set to "auto" (original project logic)
        if (!settings.minecraft_version || settings.minecraft_version === "auto") {
            delete options.version;
        }

        console.log(`Connecting to ${options.host}:${options.port} as ${options.username}`);
        console.log(`Auth: ${options.auth}, Version: ${options.version || 'auto-detect'}`);

        this.bot = createBot(options);

        // Add modes stub for skills.js compatibility immediately after bot creation
        // (Original project uses modes system, we don't need it but skills.js expects it)
        this.bot.modes = {
            isOn: (mode) => false,  // Never use cheat mode
            flushBehaviorLog: () => '',  // No behavior log in three-layer brain
            pause: (mode) => { },  // Stub for skills that pause modes
            unpause: (mode) => { },  // Stub for skills that unpause modes
            behavior_log: ''  // Skills.js may append to this
        };

        // Load basic plugins first (don't require bot.version)
        this.bot.loadPlugin(pathfinder);
        this.bot.loadPlugin(pvpPlugin);
        this.bot.loadPlugin(collectblockPlugin);

        // Load version-dependent plugins after login (when bot.version is available)
        this.bot.once('login', () => {
            console.log(`Bot logged in as ${this.bot.username}`);

            // Now bot.version is available, load version-dependent plugins
            this.bot.loadPlugin(autoEatPlugin);
            this.bot.loadPlugin(armorManagerPlugin);
        });

        // Accept resource packs (original project logic)
        this.bot.once('resourcePack', () => {
            this.bot.acceptResourcePack();
        });

        // Setup event handlers
        this.setupEventHandlers();
    }

    setupEventHandlers() {
        // Spawn event (bot enters world)
        this.bot.once('spawn', async () => {
            console.log('Bot spawned in world');

            // Initialize interrupt_code flag (for real-time code interruption)
            this.bot.interrupt_code = false;

            // Initialize mcdata for world functions (CRITICAL!)
            // This must be done after spawn when bot.version is available
            await mcdata.init(this.bot);

            // Setup pathfinder (original project logic)
            const minecraftData = (await import('minecraft-data')).default;
            const mcData = minecraftData(this.bot.version);
            const defaultMove = new Movements(this.bot, mcData);
            this.bot.pathfinder.setMovements(defaultMove);

            // Load cumulative playtime (age = total ticks / 24000)
            await this.loadPlaytime();

            // Initialize lastTimeOfDay to current time
            this.lastTimeOfDay = this.bot.time.timeOfDay;
            console.log(`Session started at time of day: ${this.lastTimeOfDay}`);

            // Calculate current age
            const ageDays = Math.floor(this.totalTicksPlayed / 24000);
            const ageHours = Math.floor((this.totalTicksPlayed % 24000) / 1000);

            // Notify Python brain that bot is ready
            await this.sendMessage({
                type: 'bot_ready',
                data: {
                    agent_name: this.config.agent_name || 'BrainyBot',  // Configuration name
                    minecraft_username: this.bot.username,  // Actual Minecraft login name
                    gamemode: this.bot.game.gameMode,
                    dimension: this.bot.game.dimension,
                    agent_age_days: ageDays,
                    agent_age_ticks: this.totalTicksPlayed,
                    world_day: this.bot.time.day,
                    world_ticks: Number(this.bot.time.bigTime)
                }
            });

            console.log('Bot ready notification sent to Python brain');
            console.log(`Agent age: ${ageDays} game days, ${ageHours} hours (${this.totalTicksPlayed} total ticks)`);
            console.log(`Current world: Day ${this.bot.time.day}, Time of day: ${this.lastTimeOfDay}`);

            this.bot.on('physicsTick', () => {
                this.totalTicksPlayed++;

                // Auto-save every 1 minutes (1200 ticks)
                if (this.totalTicksPlayed % 1200 === 0) {
                    this.savePlaytime();
                    const ageDays = Math.floor(this.totalTicksPlayed / 24000);
                    console.log(`[Playtime] Auto-saved: ${this.totalTicksPlayed} ticks (${ageDays} days)`);
                }
            });

            // Start state update loop
            setInterval(() => this.sendStateUpdate(), 1000);
        });

        // Chat event
        this.bot.on('chat', async (username, message) => {
            if (username === this.bot.username) return;

            console.log(`<${username}> ${message}`);

            // Send chat to Python brain
            await this.sendMessage({
                type: 'chat_message',
                data: {
                    player: username,
                    message: message
                }
            });
        });

        // Health tracking (original project logic)
        let prev_health = this.bot.health;
        this.bot.lastDamageTime = 0;
        this.bot.lastDamageTaken = 0;

        this.bot.on('health', () => {
            // Track damage taken
            if (this.bot.health < prev_health) {
                this.bot.lastDamageTime = Date.now();
                this.bot.lastDamageTaken = prev_health - this.bot.health;
            }
            prev_health = this.bot.health;

            // Send low health alert
            if (this.bot.health < 10) {
                this.sendMessage({
                    type: 'low_health',
                    data: {
                        health: this.bot.health,
                        damage_taken: this.bot.lastDamageTaken
                    }
                });
            }
        });

        // Death event
        this.bot.on('death', () => {
            console.log('Bot died!');
            this.sendMessage({
                type: 'death',
                data: { timestamp: Date.now() }
            });
        });

        // Error handling (original project logic)
        this.bot.on('error', (err) => {
            console.error('Bot error:', err);

            // Check if it's a connection error
            if (err.code === 'ECONNRESET' || err.code === 'ECONNREFUSED') {
                console.error('\n Cannot connect to Minecraft server!');
                console.error(`   Make sure server is running on ${settings.host}:${settings.port}`);
                console.error('   Check server version compatibility');
            }
        });

        // Disconnect handling (original project logic)
        this.bot.on('end', async (reason) => {
            console.warn('Bot disconnected!', reason);

            // Stop playtime update interval
            if (this.playtimeInterval) {
                clearInterval(this.playtimeInterval);
                this.playtimeInterval = null;
            }

            // Notify Python brain that bot disconnected
            try {
                await this.sendMessage({
                    type: 'bot_disconnected',
                    data: {
                        reason: reason || 'Unknown',
                        timestamp: Date.now()
                    }
                });
            } catch (err) {
                console.error('Failed to notify Python about disconnect:', err.message);
            }

            // Don't save on disconnect - losing a few seconds of age is fine
            // (Auto-save already happens every minute)

            // Auto-reconnect after 5 seconds
            console.log('\n  Bot disconnected. Attempting to reconnect in 5 seconds...');
            setTimeout(async () => {
                console.log('Attempting to reconnect...');
                try {
                    await this.initBot();
                    console.log('Reconnected successfully!');
                } catch (err) {
                    console.error('Failed to reconnect:', err.message);
                    console.log('Please restart manually.');
                }
            }, 5000);
        });        // Kicked event (original project logic)
        this.bot.on('kicked', (reason) => {
            console.warn('Bot was kicked:', reason);
            console.error('\n Bot was kicked from server!');
            console.error('   Reason:', reason);
        });

        // Entity hurt tracking
        this.bot.on('entityHurt', (entity) => {
            if (entity === this.bot.entity) {
                this.sendMessage({
                    type: 'damage_taken',
                    data: {
                        health: this.bot.health,
                        damage: this.bot.lastDamageTaken,
                        timestamp: Date.now()
                    }
                });
            }
        });
    }

    startIdleBehavior() {
        /**
         * Idle behavior: Look around at entities when not executing tasks
         * Based on original project's idle_staring mode
         */
        const idleState = {
            staring: false,
            lastEntity: null,
            nextChange: 0
        };

        const updateIdleBehavior = () => {
            // Only do idle animations when bot is not executing code
            // (We don't have access to agent.isIdle(), so we assume idle between tasks)

            const entity = this.bot.nearestEntity();
            const entityInView = entity &&
                entity.position.distanceTo(this.bot.entity.position) < 10 &&
                entity.name !== 'enderman';  // Don't stare at endermen!

            // Start staring at new entity
            if (entityInView && entity !== idleState.lastEntity) {
                idleState.staring = true;
                idleState.lastEntity = entity;
                idleState.nextChange = Date.now() + Math.random() * 1000 + 4000; // 4-5 seconds
            }

            // Look at entity
            if (entityInView && idleState.staring) {
                try {
                    // Check if entity is a baby (metadata[16] for mobs)
                    const isBaby = entity.type !== 'player' && entity.metadata && entity.metadata[16];
                    const height = isBaby ? entity.height / 2 : entity.height;
                    this.bot.lookAt(entity.position.offset(0, height, 0));
                } catch (err) {
                    // Ignore lookAt errors
                }
            }

            // Clear last entity if out of view
            if (!entityInView) {
                idleState.lastEntity = null;
            }

            // Time to change behavior
            if (Date.now() > idleState.nextChange) {
                // 30% chance to stare, 70% chance to look randomly
                idleState.staring = Math.random() < 0.3;

                if (!idleState.staring) {
                    // Look in random direction
                    const yaw = Math.random() * Math.PI * 2;
                    const pitch = (Math.random() * Math.PI / 2) - Math.PI / 4;
                    try {
                        this.bot.look(yaw, pitch, false);
                    } catch (err) {
                        // Ignore look errors
                    }
                }

                idleState.nextChange = Date.now() + Math.random() * 10000 + 2000; // 2-12 seconds
            }
        };

        // Update idle behavior every 100ms
        setInterval(updateIdleBehavior, 100);
    }

    startCombatDetection() {
        /**
         * Combat detection: Check for nearby hostile mobs and send combat event
         * Based on original project's self_defense mode
         */
        const checkForEnemies = () => {
            // Find nearest hostile entity within 8 blocks
            const hostileTypes = ['zombie', 'skeleton', 'spider', 'creeper', 'enderman',
                'witch', 'slime', 'phantom', 'drowned', 'husk'];

            const enemies = Object.values(this.bot.entities)
                .filter(e => {
                    if (!e || !e.position) return false;
                    const distance = e.position.distanceTo(this.bot.entity.position);
                    const isHostile = hostileTypes.includes(e.name) || e.type === 'hostile' || e.type === 'mob';
                    return isHostile && distance < 8;
                });

            if (enemies.length > 0) {
                const nearest = enemies[0];
                // Send combat event to Python
                this.sendMessage({
                    type: 'combat_engaged',
                    data: {
                        enemy_type: nearest.name,
                        enemy_id: nearest.id,
                        distance: nearest.position.distanceTo(this.bot.entity.position)
                    }
                });
            }
        };

        // Check for enemies every 500ms
        setInterval(checkForEnemies, 500);
    }

    async start() {
        console.log('='.repeat(70));
        console.log('  Three-Layer Brain Bridge - Minecraft Connection');
        console.log('='.repeat(70));

        try {
            // Initialize bot first
            await this.initBot();

            // Wait for spawn
            await new Promise(resolve => this.bot.once('spawn', resolve));

            // Then connect to Python
            await this.initIPC();

            // Start idle behavior (looking around, staring at entities)
            this.startIdleBehavior();

            // Start combat detection (check for nearby enemies)
            this.startCombatDetection();

            console.log('='.repeat(70));
            console.log('  Bridge active - Bot connected to brain');
            console.log('='.repeat(70));

        } catch (error) {
            console.error('Failed to start bridge:', error);
            process.exit(1);
        }
    }
}

// Start the bridge
const bridge = new BrainBridge();
bridge.start().catch(console.error);
