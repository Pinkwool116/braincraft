/**
 * Reflex Controller
 * 
 * Pure reflex system without LLM involvement.
 * Handles immediate threats and survival needs.
 */

import * as skills from './library/skills.js';

export class ReflexController {
    constructor(bot, ipcClient) {
        this.bot = bot;
        this.ipc = ipcClient;

        // Initialize reflexes with priority levels
        this.reflexes = this._initReflexes();
        this.activeReflex = null;

        console.log('Reflex controller initialized');
    }

    _initReflexes() {
        /**
         * Initialize all reflex behaviors
         * 
         * @returns {Array} Array of reflex definitions
         */
        return [
            {
                name: 'combat_reflex',
                priority: 100,
                check: () => this._checkCombat(),
                action: () => this._handleCombat()
            },
            {
                name: 'survival_reflex',
                priority: 90,
                check: () => this.bot.health < 5,
                action: () => this._handleLowHealth()
            },
            {
                name: 'fire_reflex',
                priority: 85,
                check: () => this._checkOnFire(),
                action: () => this._handleOnFire()
            },
            {
                name: 'drowning_reflex',
                priority: 80,
                check: () => this._checkDrowning(),
                action: () => this._handleDrowning()
            },
            {
                name: 'stuck_reflex',
                priority: 50,
                check: () => this._checkStuck(),
                action: () => this._handleStuck()
            }
        ];
    }

    async update() {
        /**
         * Update reflex system (called every tick)
         */
        // Skip if a reflex is already active
        if (this.activeReflex) return;

        // Check reflexes in priority order
        for (const reflex of this.reflexes) {
            if (reflex.check()) {
                await this._triggerReflex(reflex);
                break;
            }
        }
    }

    async _triggerReflex(reflex) {
        /**
         * Trigger a reflex action
         * 
         * @param {Object} reflex - Reflex to trigger
         */
        this.activeReflex = reflex;
        console.log(`Reflex triggered: ${reflex.name}`);

        try {
            await reflex.action();

            // Send event to Python
            await this.ipc.sendEvent({
                type: 'reflex_triggered',
                data: {
                    name: reflex.name,
                    timestamp: Date.now()
                }
            });

        } catch (error) {
            console.error(`Reflex error (${reflex.name}):`, error);
        } finally {
            this.activeReflex = null;
        }
    }

    // ========== Check Functions ==========

    _checkCombat() {
        /**
         * Check if enemy is nearby
         * 
         * @returns {boolean} True if enemy detected
         */
        // TODO: Implement enemy detection
        // const enemy = this._getNearestEnemy(8);
        // return enemy !== null;

        return false;
    }

    _checkOnFire() {
        /**
         * Check if bot is on fire
         * 
         * @returns {boolean} True if on fire
         */
        const block = this.bot.blockAt(this.bot.entity.position);
        const blockAbove = this.bot.blockAt(this.bot.entity.position.offset(0, 1, 0));

        return (block?.name === 'fire' || block?.name === 'lava' ||
            blockAbove?.name === 'fire' || blockAbove?.name === 'lava');
    }

    _checkDrowning() {
        /**
         * Check if bot is drowning
         * 
         * @returns {boolean} True if underwater
         */
        const blockAbove = this.bot.blockAt(this.bot.entity.position.offset(0, 1, 0));
        return blockAbove?.name === 'water';
    }

    _checkStuck() {
        /**
         * Check if bot is stuck
         * 
         * TODO: Implement stuck detection
         * - Track position over time
         * - Detect if not moving while pathfinding
         * 
         * @returns {boolean} True if stuck
         */
        return false;
    }

    // ========== Action Functions ==========

    async _handleCombat() {
        /**
         * Handle combat reflex
         */
        console.log('Combat reflex: Engaging enemy');

        // TODO: Implement combat
        // await skills.defendSelf(this.bot, 8);

        // Notify Python
        await this.ipc.sendEvent({
            type: 'combat_engaged',
            data: { timestamp: Date.now() }
        });
    }

    async _handleLowHealth() {
        /**
         * Handle low health reflex
         */
        console.log('Survival reflex: Low health, escaping');

        // TODO: Implement escape
        // await skills.moveAway(this.bot, 20);

        // Notify Python
        await this.ipc.sendEvent({
            type: 'low_health',
            data: { health: this.bot.health }
        });
    }

    async _handleOnFire() {
        /**
         * Handle on fire reflex
         */
        console.log('Fire reflex: On fire, seeking water');

        // TODO: Implement fire escape
        // - Check for water bucket
        // - Place water if available
        // - Otherwise move to water source

        await this.ipc.sendEvent({
            type: 'on_fire',
            data: { timestamp: Date.now() }
        });
    }

    async _handleDrowning() {
        /**
         * Handle drowning reflex
         */
        console.log('Drowning reflex: Swimming up');

        // Simple reflex: jump to surface
        this.bot.setControlState('jump', true);

        await this.ipc.sendEvent({
            type: 'drowning',
            data: { timestamp: Date.now() }
        });
    }

    async _handleStuck() {
        /**
         * Handle stuck reflex
         */
        console.log('Stuck reflex: Attempting to unstuck');

        // TODO: Implement unstuck behavior
        // await skills.moveAway(this.bot, 5);

        await this.ipc.sendEvent({
            type: 'stuck',
            data: { timestamp: Date.now() }
        });
    }
}
