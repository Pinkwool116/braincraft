/**
 * Perception Worker
 *
 * Standalone JS perception module that runs independently of Agent Loop.
 * Continuously listens to Mineflayer events and performs active scanning.
 *
 * Three duties:
 *   1. Passive event listening (entitySpawn, blockUpdate, soundEffectHeard, ...)
 *   2. Active terrain scanning (full scan every 300s)
 *   3. Urgent threat detection → direct push to Reflex Layer
 *
 * Decoupled from BrainBridge via callbacks: onEvent(normal) + onUrgent(emergency).
 */

import Vec3 from 'vec3';

const HOSTILE_MOBS = new Set([
  'zombie', 'skeleton', 'spider', 'creeper', 'enderman',
  'witch', 'slime', 'phantom', 'drowned', 'husk', 'stray',
  'cave_spider', 'blaze', 'ghast', 'magma_cube', 'hoglin',
  'piglin', 'piglin_brute', 'zoglin', 'wither_skeleton',
  'vindicator', 'evoker', 'pillager', 'ravager', 'vex',
  'guardian', 'elder_guardian', 'warden'
]);

// Ambient / cosmetic mobs that are never worth recording
const IGNORED_MOBS = new Set([
  'bat', 'bee', 'glow_squid', 'cod', 'salmon', 'pufferfish',
  'tropical_fish', 'squid', 'fox', 'ocelot', 'rabbit',
  'parrot', 'turtle', 'axolotl', 'tadpole', 'frog'
]);

const URGENT_HOSTILE_DISTANCE = 8;
const MAX_BLOCK_UPDATE_DISTANCE = 32;  // ignore block changes farther than this

export class PerceptionWorker {
  constructor(bot, onEvent, onUrgent, onScan, options = {}) {
    this.bot = bot;
    this.onEvent = onEvent;
    this.onUrgent = onUrgent;
    this.onScan = onScan;  // terrain scan snapshots — separate channel from events
    this.options = {
      fullScanIntervalMs: 300000,
      perceptionPushIntervalMs: 3000,
      entityMoveThrottleMs: 3000,
      blockUpdateThrottleMs: 1000,
      soundMinVolume: 0.3,
      soundMaxDistance: 32,
      rayRange: 128,
      urgentCheckIntervalMs: 500,
      ...options
    };

    // Entity tracking: entityId → { name, type, position, firstSeen, lastSeen, prevDistance }
    this._knownEntities = new Map();

    // Throttle trackers
    this._lastEntityMoveTime = new Map();   // entityId → last push timestamp
    this._lastBlockUpdateTime = new Map();  // "x,y,z" → last push timestamp

    // Sound dedup: "soundName|direction" → { count, lastTime }
    this._soundDedup = new Map();

    // Active scan interval handles
    this._fullScanTimer = null;
    this._urgentCheckTimer = null;

    // Bound handlers for cleanup
    this._handlers = {};
    this._running = false;
  }

  // ==================== Lifecycle ====================

  start() {
    if (this._running) return;
    this._running = true;
    this._bindEvents();
    this._scanExistingEntities();  // catch entities already present before worker started
    this._startScanTimers();
    this._startUrgentCheck();
  }

  stop() {
    this._running = false;
    this._unbindEvents();
    this._clearTimers();
    this._knownEntities.clear();
    this._lastEntityMoveTime.clear();
    this._lastBlockUpdateTime.clear();
    this._soundDedup.clear();
  }

  // ==================== Initial entity scan ====================

  _scanExistingEntities() {
    // Catch entities that already exist before event listeners were bound.
    // Without this, chickens and other passive mobs nearby would never be recorded.
    if (!this.bot?.entity) return;
    const now = Date.now();
    for (const entity of Object.values(this.bot.entities)) {
      if (entity === this.bot.entity) continue;
      const name = entity.type === 'player'
        ? ((entity.username || entity.name || '') + ' (player)')
        : (entity.name || entity.username || '');
      if (IGNORED_MOBS.has(name)) continue;
      const dist = entity.position.distanceTo(this.bot.entity.position);
      if (dist > 32) continue;

      // Resolve dropped item entities to their real item name via metadata
      const resolved = (entity.type === 'object' || entity.type === 'other') &&
                       (name === 'Item' || name === 'item')
        ? this._resolveItemName(entity) : null;
      const isItem = !!resolved;
      const itemName = resolved ? (resolved + ' (item)') : name;

      this._knownEntities.set(entity.id, {
        name: name,
        type: entity.type,
        position: entity.position.clone(),
        firstSeen: now,
        lastSeen: now,
        distance: dist
      });
      this.onEvent('entity_spawn', {
        entity_id: entity.id,
        name: name,
        type: entity.type,
        position: { x: entity.position.x, y: entity.position.y, z: entity.position.z },
        distance: Math.round(dist),
        direction: this._directionTo(entity.position),
        is_hostile: HOSTILE_MOBS.has(name),
        is_item: isItem,
        item_name: itemName
      });
    }
  }

  // ==================== Event Binding ====================

  _bindEvents() {
    this._handlers.entitySpawn = (entity) => this._onEntitySpawn(entity);
    this._handlers.entityGone = (entity) => this._onEntityGone(entity);
    this._handlers.entityMoved = (entity) => this._onEntityMoved(entity);
    this._handlers.blockUpdate = (oldBlock, newBlock) => this._onBlockUpdate(oldBlock, newBlock);
    this._handlers.soundEffectHeard = (soundName, position, volume, pitch) =>
      this._onSoundHeard(soundName, position, volume, pitch);
    this._handlers.playerJoined = (player) => this._onPlayerJoined(player);
    this._handlers.playerLeft = (player) => this._onPlayerLeft(player);
    this._handlers.playerCollect = (collector, collected) => this._onPlayerCollect(collector, collected);
    this._handlers.itemDrop = (entity) => this._onItemDrop(entity);
    this._handlers.rain = () => this._onWeatherChange();

    this.bot.on('entitySpawn', this._handlers.entitySpawn);
    this.bot.on('entityGone', this._handlers.entityGone);
    this.bot.on('entityMoved', this._handlers.entityMoved);
    this.bot.on('blockUpdate', this._handlers.blockUpdate);
    this.bot.on('soundEffectHeard', this._handlers.soundEffectHeard);
    this.bot.on('playerJoined', this._handlers.playerJoined);
    this.bot.on('playerLeft', this._handlers.playerLeft);
    this.bot.on('playerCollect', this._handlers.playerCollect);
    this.bot.on('itemDrop', this._handlers.itemDrop);
    // rain event: some versions fire with no args, some don't fire at all
    // we also check weather changes in urgent check loop
    try { this.bot.on('rain', this._handlers.rain); } catch (_) { /* ignore if unsupported */ }
  }

  _unbindEvents() {
    if (!this.bot) return;
    this.bot.removeListener('entitySpawn', this._handlers.entitySpawn);
    this.bot.removeListener('entityGone', this._handlers.entityGone);
    this.bot.removeListener('entityMoved', this._handlers.entityMoved);
    this.bot.removeListener('blockUpdate', this._handlers.blockUpdate);
    this.bot.removeListener('soundEffectHeard', this._handlers.soundEffectHeard);
    this.bot.removeListener('playerJoined', this._handlers.playerJoined);
    this.bot.removeListener('playerLeft', this._handlers.playerLeft);
    this.bot.removeListener('playerCollect', this._handlers.playerCollect);
    this.bot.removeListener('itemDrop', this._handlers.itemDrop);
    try { this.bot.removeListener('rain', this._handlers.rain); } catch (_) { /* ignore */ }
  }

  _startScanTimers() {
    this._fullScanTimer = setInterval(() => this._doFullScan(), this.options.fullScanIntervalMs);
  }

  _startUrgentCheck() {
    this._urgentCheckTimer = setInterval(() => this._checkUrgentThreats(), this.options.urgentCheckIntervalMs);
  }

  _clearTimers() {
    if (this._fullScanTimer) { clearInterval(this._fullScanTimer); this._fullScanTimer = null; }
    if (this._urgentCheckTimer) { clearInterval(this._urgentCheckTimer); this._urgentCheckTimer = null; }
  }

  // ==================== Passive Event Handlers ====================

  _onEntitySpawn(entity) {
    if (!this._running || !this.bot?.entity) return;
    // Filter self
    if (entity === this.bot.entity) return;
    // Filter ambient / cosmetic mobs
    const mobName = entity.name || '';
    if (IGNORED_MOBS.has(mobName)) return;
    // Filter far entities (> 32 blocks)
    const dist = entity.position.distanceTo(this.bot.entity.position);
    if (dist > 32) return;

    // Player entities use username for display, mobs use entity name
    const displayName = entity.type === 'player'
      ? ((entity.username || entity.name || 'unknown') + ' (player)')
      : (entity.name || entity.username || 'unknown');

    const now = Date.now();
    this._knownEntities.set(entity.id, {
      name: displayName,
      type: entity.type,
      position: entity.position.clone(),
      firstSeen: now,
      lastSeen: now,
      distance: dist
    });

    // Resolve dropped item entities to their real item name via metadata.
    // When metadata hasn't arrived yet, defer — _onItemDrop will re-emit.
    let isItem = false;
    let itemName = null;
    if ((entity.type === 'object' || entity.type === 'other') &&
        (entity.name === 'Item' || entity.name === 'item')) {
      itemName = this._resolveItemName(entity);
      if (itemName) {
        itemName = itemName + ' (item)';
        isItem = true;
        // Store resolved name so _onEntityGone can show it
        const known = this._knownEntities.get(entity.id);
        if (known) known.itemName = itemName;
      } else {
        // Metadata not available yet — register as pending, defer emission
        this._knownEntities.set(entity.id, {
          name: displayName,
          type: entity.type,
          position: entity.position.clone(),
          firstSeen: now,
          lastSeen: now,
          distance: dist,
          _itemPending: true
        });
        return;
      }
    }

    this.onEvent('entity_spawn', {
      entity_id: entity.id,
      name: displayName,
      type: entity.type,
      position: { x: entity.position.x, y: entity.position.y, z: entity.position.z },
      distance: Math.round(dist),
      direction: this._directionTo(entity.position),
      is_hostile: HOSTILE_MOBS.has(entity.name),
      is_item: isItem,
      item_name: itemName || entity.name
    });
  }

  _onEntityGone(entity) {
    if (!this._running || !this.bot?.entity) return;
    if (entity === this.bot.entity) return;

    const known = this._knownEntities.get(entity.id);
    // Skip if we never tracked this entity (ambient mob filtered at spawn)
    if (!known) return;
    this._knownEntities.delete(entity.id);

    // Use resolved item name if available, otherwise fall back to entity type name
    const displayName = known.itemName || known.name;

    this.onEvent('entity_gone', {
      entity_id: entity.id,
      name: displayName,
      type: entity.type
    });
  }

  _onPlayerCollect(collector, collected) {
    if (!this._running || !this.bot?.entity) return;
    // Only track items collected by our own bot
    if (collector !== this.bot.entity) return;

    // Extract the actual item name from the collected entity's metadata key 8
    // (Minecraft 1.20.x: item entity metadata index 8 = ITEM_STACK)
    let itemName = collected.name || 'unknown';
    let count = 1;
    try {
      const slot = this._extractItemSlot(collected.metadata);
      if (slot) {
        count = slot.count || 1;
        const itemId = slot.itemId != null ? slot.itemId : (slot.blockId != null ? slot.blockId : null);
        if (itemId != null && this.bot?.registry?.items) {
          const item = this.bot.registry.items[itemId];
          if (item) itemName = item.name;
        }
      }
    } catch (_) { /* fall through with defaults */ }

    const dist = collected.position.distanceTo(this.bot.entity.position);

    this.onEvent('item_picked_up', {
      item_name: itemName,
      count: count,
      distance: Math.round(dist),
      direction: this._directionTo(collected.position)
    });
  }

  /** Mineflayer's itemDrop fires when entity_metadata reveals the real item data.
   *  Corrects spawn events that were deferred because metadata wasn't ready yet. */
  _onItemDrop(entity) {
    if (!this._running || !this.bot?.entity) return;
    if (entity === this.bot.entity) return;

    const known = this._knownEntities.get(entity.id);
    if (!known) return;

    const resolved = this._resolveItemName(entity);
    if (!resolved) return; // still no metadata, nothing to correct

    const itemName = resolved + ' (item)';
    const dist = entity.position.distanceTo(this.bot.entity.position);
    if (dist > 32) return;

    known.itemName = itemName;
    delete known._itemPending;

    // Re-emit with the real item name
    this.onEvent('entity_spawn', {
      entity_id: entity.id,
      name: entity.name || 'Item',
      type: entity.type,
      position: { x: entity.position.x, y: entity.position.y, z: entity.position.z },
      distance: Math.round(dist),
      direction: this._directionTo(entity.position),
      is_hostile: false,
      is_item: true,
      item_name: itemName
    });
  }

  _onEntityMoved(entity) {
    if (!this._running || !this.bot?.entity) return;
    if (entity === this.bot.entity) return;

    const now = Date.now();
    const lastTime = this._lastEntityMoveTime.get(entity.id) || 0;
    if (now - lastTime < this.options.entityMoveThrottleMs) return;

    const dist = entity.position.distanceTo(this.bot.entity.position);
    if (dist > 32) return;

    const known = this._knownEntities.get(entity.id);
    if (!known) return; // only track entities we've seen spawn

    const prevDist = known.distance;
    known.position = entity.position.clone();
    known.distance = dist;
    known.lastSeen = now;

    // Only push when entity is getting closer (approaching)
    if (prevDist - dist < 1) return;

    this._lastEntityMoveTime.set(entity.id, now);

    this.onEvent('entity_approaching', {
      entity_id: entity.id,
      name: known.name,
      type: entity.type,
      distance: Math.round(dist),
      prev_distance: Math.round(prevDist),
      direction: this._directionTo(entity.position),
      is_hostile: HOSTILE_MOBS.has(known.name)
    });
  }

  _onBlockUpdate(oldBlock, newBlock) {
    if (!this._running || !this.bot?.entity) return;
    if (!oldBlock || !newBlock) return;

    // Filter distance first (cheap, eliminates most far-away noise)
    const dist = oldBlock.position.distanceTo(this.bot.entity.position);
    if (dist > MAX_BLOCK_UPDATE_DISTANCE) return;

    // Filter significance before throttle — non-significant changes
    // must not prevent significant ones from being recorded
    const isSignificant = this._isSignificantBlockChange(oldBlock.name, newBlock.name);
    if (!isSignificant) return;

    // Throttle: same position once per second (only for significant changes)
    const now = Date.now();
    const posKey = `${oldBlock.position.x},${oldBlock.position.y},${oldBlock.position.z}`;
    const lastTime = this._lastBlockUpdateTime.get(posKey) || 0;
    if (now - lastTime < this.options.blockUpdateThrottleMs) return;
    this._lastBlockUpdateTime.set(posKey, now);

    this.onEvent('block_update', {
      position: { x: oldBlock.position.x, y: oldBlock.position.y, z: oldBlock.position.z },
      old_block: oldBlock.name,
      new_block: newBlock.name,
      distance: Math.round(dist),
      direction: this._directionTo(oldBlock.position)
    });
  }

  _isSignificantBlockChange(oldName, newName) {
    // Always record: ore exposure, liquids, TNT, explosions, air→solid, solid→air
    if (oldName === 'air' || oldName === 'cave_air' || newName === 'air' || newName === 'cave_air') return true;
    if (oldName.includes('ore') || newName.includes('ore')) return true;
    if (oldName === 'water' || oldName === 'lava' || newName === 'water' || newName === 'lava') return true;
    if (oldName === 'tnt' || newName === 'tnt') return true;
    // Agent-caused changes: crafting tables, furnaces, chests, beds
    if (newName.includes('crafting_table') || newName.includes('furnace') ||
        newName.includes('chest') || newName.includes('bed')) return true;
    return false;
  }

  _onSoundHeard(soundName, position, volume, pitch) {
    if (!this._running || !this.bot?.entity) return;
    if (volume < this.options.soundMinVolume) return;

    const dist = position.distanceTo(this.bot.entity.position);
    if (dist > this.options.soundMaxDistance) return;

    const direction = this._directionTo(position);
    const dedupKey = `${soundName}|${direction}`;
    const now = Date.now();
    const existing = this._soundDedup.get(dedupKey);

    if (existing && (now - existing.lastTime) < 5000) {
      existing.count++;
      existing.lastTime = now;
      return; // don't push duplicate, will be consolidated by EventTicker
    }

    this._soundDedup.set(dedupKey, { count: 1, lastTime: now });

    this.onEvent('sound_heard', {
      sound_name: soundName,
      position: { x: position.x, y: position.y, z: position.z },
      distance: Math.round(dist),
      direction: direction,
      volume: Math.round(volume * 100) / 100
    });
  }

  _onPlayerJoined(player) {
    if (!this._running) return;
    this.onEvent('player_joined', {
      player_name: player.username || player.name || 'unknown'
    });
  }

  _onPlayerLeft(player) {
    if (!this._running) return;
    this.onEvent('player_left', {
      player_name: player.username || player.name || 'unknown'
    });
  }

  _onWeatherChange() {
    if (!this._running) return;
    const weather = this.bot.thunderState > 0.1 ? 'Thunderstorm' :
                    this.bot.rainState > 0.1 ? 'Rain' : 'Clear';
    this.onEvent('weather_change', { new_weather: weather });
  }

  // ==================== Active Scanning (snapshot, separate channel) ====================

  _doFullScan() {
    if (!this._running || !this.bot?.entity) return;
    const samples = [];
    for (let i = 0; i < 16; i++) {
      const yaw = i * 22.5;
      for (const pitch of [-45, 0, 30]) {
        const result = this._rayScanAt(yaw, pitch);
        if (result) samples.push(result);
      }
    }
    // Full scan is a terrain snapshot — independent channel, not mixed with events
    if (this.onScan) this.onScan('full_scan', { samples });
  }

  // ---- Public method for on-demand scan ----

  forceFullScan() {
    if (!this._running || !this.bot?.entity) return;
    this._doFullScan();
  }

  forceBlockStats() {
    if (!this._running || !this.bot?.entity) return;
    this._doBlockStats();
  }

  /**
   * Ray scan using bot.world.raycast for arbitrary directions.
   * This avoids changing the bot's actual look direction.
   */
  _rayScanAt(yawDeg, pitchDeg) {
    // yaw: 0=south(+Z), 90=west(-X), 180=north(-Z), 270=east(+X)
    const yaw = (yawDeg * Math.PI) / 180;
    const pitch = (pitchDeg * Math.PI) / 180;
    const dx = -Math.sin(yaw) * Math.cos(pitch);
    const dy = -Math.sin(pitch);
    const dz = Math.cos(yaw) * Math.cos(pitch);
    const origin = this.bot.entity.position.offset(0, 1.6, 0); // eye height

    try {
      const hit = this.bot.world.raycast(origin, new Vec3(dx, dy, dz), this.options.rayRange);
      if (hit) {
        const block = this.bot.blockAt(hit.position);
        return {
          yaw: yawDeg,
          pitch: pitchDeg,
          block_name: block ? block.name : 'unknown',
          distance: Math.round(hit.position.distanceTo(origin)),
          position: { x: hit.position.x, y: hit.position.y, z: hit.position.z },
          sky_light: block ? block.skyLight : null,
          light: block ? block.light : null
        };
      }
      return {
        yaw: yawDeg,
        pitch: pitchDeg,
        block_name: 'air',
        distance: this.options.rayRange,
        position: null,
        sky_light: 15,
        light: 15
      };
    } catch (_) {
      return null;
    }
  }

  _doBlockStats() {
    if (!this._running || !this.bot?.entity) return;

    try {
      const positions = this.bot.findBlocks({
        matching: (block) => block && block.name !== 'air' && block.name !== 'cave_air',
        maxDistance: 8,
        count: 2000
      });

      // Aggregate by block name and direction
      const stats = {};
      for (const pos of positions) {
        const block = this.bot.blockAt(pos);
        if (!block) continue;
        const name = block.name;
        if (!stats[name]) {
          stats[name] = { count: 0, directions: {} };
        }
        stats[name].count++;
        const dir = this._directionTo(pos);
        stats[name].directions[dir] = (stats[name].directions[dir] || 0) + 1;
      }

      if (this.onScan) this.onScan('block_stats', { stats, agent_position: this._botPosition() });
    } catch (_) {
      // findBlocks may fail if world not loaded
    }
  }

  // ==================== Urgent Threat Detection ====================

  _checkUrgentThreats() {
    if (!this._running || !this.bot?.entity) return;
    this._checkHostileClose();
    this._checkLavaNearby();
    this._checkCliffAhead();
    this._checkDrowning();
      this._checkWeatherUrgent();
  }

  _checkHostileClose() {
    if (!this.bot?.entity) return;
    for (const entity of Object.values(this.bot.entities)) {
      if (!entity || entity === this.bot.entity) continue;
      if (!HOSTILE_MOBS.has(entity.name) && entity.type !== 'hostile') continue;

      const dist = entity.position.distanceTo(this.bot.entity.position);
      if (dist > URGENT_HOSTILE_DISTANCE) continue;

      // Check if approaching
      const known = this._knownEntities.get(entity.id);
      const isApproaching = known && known.distance > dist;

      this.onUrgent('hostile_close', {
        entity_id: entity.id,
        name: entity.name || 'unknown',
        type: entity.type,
        distance: Math.round(dist),
        direction: this._directionTo(entity.position),
        approaching: isApproaching
      });
    }
  }

  _checkLavaNearby() {
    if (!this.bot?.entity) return;
    const origin = this.bot.entity.position.offset(0, 1.6, 0);
    const yaw = this.bot.entity.yaw;
    const pitch = 0;

    // Check forward 3 blocks
    for (let dist = 1; dist <= 3; dist++) {
      const dx = -Math.sin(yaw) * Math.cos(pitch) * dist;
      const dz = -Math.cos(yaw) * Math.cos(pitch) * dist;
      const pos = origin.offset(dx, 0, dz);
      const block = this.bot.blockAt(pos);
      if (block && block.name === 'lava') {
        this.onUrgent('lava_nearby', {
          distance: dist,
          direction: 'forward',
          position: { x: pos.x, y: pos.y, z: pos.z }
        });
        return;
      }
    }
    // Also check block below
    const below = this.bot.blockAt(this.bot.entity.position.offset(0, -1, 0));
    if (below && below.name === 'lava') {
      this.onUrgent('lava_nearby', {
        distance: 0,
        direction: 'below',
        position: { x: below.position.x, y: below.position.y, z: below.position.z }
      });
    }
  }

  _checkCliffAhead() {
    if (!this.bot?.entity) return;
    const yaw = this.bot.entity.yaw;
    const origin = this.bot.entity.position.offset(0, 0, 0);

    // Check blocks 1-4 ahead at y-1, y-2, y-3
    for (let ahead = 1; ahead <= 4; ahead++) {
      const dx = -Math.sin(yaw) * ahead;
      const dz = -Math.cos(yaw) * ahead;
      let allAir = true;
      for (let down = 1; down <= 3; down++) {
        const pos = origin.offset(dx, -down, dz);
        const block = this.bot.blockAt(pos);
        if (block && block.name !== 'air' && block.name !== 'cave_air') {
          allAir = false;
          break;
        }
      }
      if (allAir) {
        this.onUrgent('cliff_ahead', {
          distance: ahead,
          direction: this._directionTo(origin.offset(dx, 0, dz))
        });
        return;
      }
    }
  }

  _checkDrowning() {
    if (!this.bot?.entity) return;
    const headBlock = this.bot.blockAt(this.bot.entity.position.offset(0, 1, 0));
    if (!headBlock) return;
    const inWater = headBlock.name === 'water';

    // Check oxygen level (bot.oxygen is available in some mineflayer versions)
    const oxygen = this.bot.oxygen;
    if (inWater && oxygen !== undefined && oxygen < 5) {
      this.onUrgent('drowning', {
        oxygen: oxygen,
        position: this._botPosition()
      });
      return;
    }
    // If oxygen API not available, check if submerged for too long
    // by checking if head and block above head are both water
    if (inWater) {
      const aboveHead = this.bot.blockAt(this.bot.entity.position.offset(0, 2, 0));
      if (aboveHead && aboveHead.name === 'water') {
        this.onUrgent('drowning', {
          oxygen: oxygen || 'unknown',
          position: this._botPosition()
        });
      }
    }
  }

  _checkWeatherUrgent() {
    // Fallback weather detection if 'rain' event isn't firing reliably
    if (!this.bot) return;
    const currentWeather = this.bot.thunderState > 0 ? 'Thunderstorm' :
                           this.bot.rainState > 0 ? 'Rain' : 'Clear';
    if (this._lastWeather && this._lastWeather !== currentWeather) {
      this.onEvent('weather_change', { new_weather: currentWeather });
    }
    this._lastWeather = currentWeather;
  }

  // ==================== Helpers ====================

  /** Item entity metadata format (sparse array, length 9):
   *    [0..7] → null
   *    [8]    → { itemId, itemCount, components[], ... }
   *  itemId is the raw Minecraft item ID, resolved to a display name via
   *  registry.items[id].name (e.g. 28 → "bone").
   *
   *  Returns the slot at index 8 (the object with itemId/itemCount), or null. */
  _extractItemSlot(metadata) {
    if (!metadata) return null;
    if (Array.isArray(metadata)) {
      const slot = metadata[8];
      if (slot && (slot.itemId != null || slot.blockId != null)) return slot;
      if (slot?.value && (slot.value.itemId != null || slot.value.blockId != null)) return slot.value;
      return null;
    }
    return metadata[8] || null;
  }

  /** Try to resolve a dropped item entity to its real display name via registry.
   *  Returns the name (e.g. "spruce_log") or null. */
  _resolveItemName(entity) {
    try {
      const slot = this._extractItemSlot(entity.metadata);
      if (!slot) return null;
      const itemId = slot.itemId != null ? slot.itemId : (slot.blockId != null ? slot.blockId : null);
      if (itemId == null) return null;
      const item = this.bot?.registry?.items?.[itemId];
      return item?.name || null;
    } catch (_) {
      return null;
    }
  }

  _directionTo(targetPos) {
    if (!this.bot?.entity) return 'unknown';
    const dx = targetPos.x - this.bot.entity.position.x;
    const dy = targetPos.y - this.bot.entity.position.y;
    const dz = targetPos.z - this.bot.entity.position.z;
    const angle = (Math.atan2(dx, dz) * 180) / Math.PI;

    let h = '';
    if (angle >= -22.5 && angle < 22.5) h = '北';
    else if (angle >= 22.5 && angle < 67.5) h = '东北';
    else if (angle >= 67.5 && angle < 112.5) h = '东';
    else if (angle >= 112.5 && angle < 157.5) h = '东南';
    else if (angle >= 157.5 || angle < -157.5) h = '南';
    else if (angle >= -157.5 && angle < -112.5) h = '西南';
    else if (angle >= -112.5 && angle < -67.5) h = '西';
    else if (angle >= -67.5 && angle < -22.5) h = '西北';

    // Vertical direction (threshold: 2 blocks)
    if (dy > 2) return h + '（上方' + Math.abs(dy) + "格）";
    if (dy < -2) return h + '（下方' + Math.abs(dy) + "格）";
    return h || '未知';
  }

  _botPosition() {
    if (!this.bot?.entity) return null;
    const p = this.bot.entity.position;
    return { x: p.x, y: p.y, z: p.z };
  }
}
