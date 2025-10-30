/**
 * State Reporter
 * 
 * Periodically reports game state to Python brain system.
 */

class StateReporter {
    constructor(bot, ipcClient, interval = 1000) {
        this.bot = bot;
        this.ipc = ipcClient;
        this.interval = interval;
        this.running = false;
    }

    start() {
        /**
         * Start reporting game state
         */
        if (this.running) return;

        this.running = true;
        console.log('State reporter started');

        this._reportLoop();
    }

    async _reportLoop() {
        /**
         * Main reporting loop
         */
        while (this.running) {
            try {
                const state = this._collectState();
                await this.ipc.sendStateUpdate(state);
            } catch (error) {
                console.error('Error reporting state:', error);
            }

            await new Promise(resolve => setTimeout(resolve, this.interval));
        }
    }

    _collectState() {
        /**
         * Collect current game state
         * 
         * @returns {Object} Current game state
         */
        const bot = this.bot;
        const pos = bot.entity.position;

        return {
            // Position
            position: {
                x: pos.x,
                y: pos.y,
                z: pos.z
            },

            // Health and hunger
            health: bot.health,
            food: bot.food,

            // Environment
            biome: bot.world?.getBiomeAt?.(pos) || 'unknown',
            time_of_day: bot.time.timeOfDay,
            weather: bot.isRaining ? 'rain' : 'clear',

            // Inventory
            inventory: this._getInventoryState(),

            // Nearby entities
            nearby_players: this._getNearbyPlayers(),
            nearby_mobs: this._getNearbyMobs(),

            // Current action
            current_action: 'idle', // TODO: Get from action manager

            timestamp: Date.now()
        };
    }

    _getInventoryState() {
        /**
         * Get inventory state
         * 
         * @returns {Object} Inventory counts
         */
        const inventory = {};

        for (const item of this.bot.inventory.items()) {
            inventory[item.name] = (inventory[item.name] || 0) + item.count;
        }

        return inventory;
    }

    _getNearbyPlayers() {
        /**
         * Get nearby players
         * 
         * @returns {Array} List of nearby player names
         */
        return Object.keys(this.bot.players).filter(name =>
            name !== this.bot.username
        );
    }

    _getNearbyMobs() {
        /**
         * Get nearby mobs
         * 
         * @returns {Array} List of nearby mob info
         */
        const mobs = [];
        const maxDistance = 16;

        for (const entity of Object.values(this.bot.entities)) {
            if (entity.type === 'mob' || entity.type === 'hostile') {
                const distance = this.bot.entity.position.distanceTo(entity.position);
                if (distance <= maxDistance) {
                    mobs.push({
                        type: entity.name,
                        id: entity.id,
                        distance: distance,
                        health: entity.health
                    });
                }
            }
        }

        return mobs;
    }

    stop() {
        /**
         * Stop reporting
         */
        this.running = false;
        console.log('State reporter stopped');
    }
}

module.exports = { StateReporter };
