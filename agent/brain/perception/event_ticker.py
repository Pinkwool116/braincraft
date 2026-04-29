"""
EventTicker — Pure-code event aggregator (no LLM).

Consumes raw perception events every 2 seconds and produces
structured observation text for WorkingMemory.

Aggregation rules are purely positional/statistical — no semantic understanding needed.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Hostile mobs that should always be flagged when approaching
HOSTILE_MOBS = {
    'zombie', 'skeleton', 'spider', 'creeper', 'enderman',
    'witch', 'slime', 'phantom', 'drowned', 'husk', 'stray',
    'cave_spider', 'blaze', 'ghast', 'magma_cube', 'hoglin',
    'piglin', 'piglin_brute', 'zoglin', 'wither_skeleton',
    'vindicator', 'evoker', 'pillager', 'ravager', 'vex',
    'guardian', 'elder_guardian', 'warden'
}

# Ore blocks worth flagging in block changes
ORE_BLOCKS = {
    'coal_ore', 'iron_ore', 'gold_ore', 'diamond_ore', 'emerald_ore',
    'copper_ore', 'lapis_ore', 'redstone_ore', 'nether_quartz_ore',
    'ancient_debris', 'deepslate_coal_ore', 'deepslate_iron_ore',
    'deepslate_gold_ore', 'deepslate_diamond_ore', 'deepslate_emerald_ore',
    'deepslate_copper_ore', 'deepslate_lapis_ore', 'deepslate_redstone_ore'
}


class EventTicker:
    """Pure-code event aggregator. Runs every 2s, produces observation text."""

    def __init__(self, max_entities: int = 5, max_sounds: int = 5):
        self.max_entities = max_entities
        self.max_sounds = max_sounds
        # Cross-tick entity tracking: entity_id → {name, type, first_seen, last_seen}
        self._known_entities: dict = {}

    def aggregate(self, events: list) -> Optional[str]:
        """
        Aggregate a batch of raw events into observation text.
        Returns None if nothing worth recording happened.
        """
        new_entities = []
        approaching = []
        gone_entities = []
        sounds = []
        weather_changes = []
        block_changes = []

        for event in events:
            etype = event.get('event_type', '')
            data = event.get('data', {})

            if etype == 'entity_spawn':
                self._handle_spawn(data, new_entities)
            elif etype == 'entity_approaching':
                self._handle_approaching(data, approaching)
            elif etype == 'entity_gone':
                self._handle_gone(data, gone_entities)
            elif etype == 'sound_heard':
                self._handle_sound(data, sounds)
            elif etype == 'weather_change':
                weather_changes.append(data.get('new_weather', 'unknown'))
            elif etype == 'block_update':
                self._handle_block_change(data, block_changes)

        # Assemble output
        parts = []

        if new_entities:
            items = []
            for e in new_entities[:self.max_entities]:
                items.append(f"{e['name']}({e['direction']}{e['distance']}格)")
            parts.append(f"新实体: {', '.join(items)}")

        if approaching:
            items = []
            for e in approaching:
                items.append(f"{e['name']}({e['direction']}{e['distance']}格靠近中)")
            parts.append(f"威胁靠近: {', '.join(items)}")

        if gone_entities:
            names = list(dict.fromkeys(e['name'] for e in gone_entities))[:self.max_entities]
            parts.append(f"实体消失: {', '.join(names)}")

        if sounds:
            # Deduplicate: same sound+direction → count
            deduped = {}
            for s in sounds:
                key = f"{s['name']}|{s.get('direction', '?')}"
                if key in deduped:
                    deduped[key]['count'] += 1
                else:
                    deduped[key] = {**s, 'count': 1}
            items = []
            for s in list(deduped.values())[:self.max_sounds]:
                label = f"{s['name']}({s.get('direction', '?')}{s.get('distance', '?')}格)"
                if s['count'] > 1:
                    label += f"×{s['count']}"
                items.append(label)
            parts.append(f"声音: {', '.join(items)}")

        if weather_changes:
            parts.append(f"天气: {' → '.join(weather_changes)}")

        if block_changes:
            parts.append(f"方块变化: {', '.join(block_changes[:5])}")

        if not parts:
            return None

        timestamp = datetime.now().strftime('%H:%M:%S')
        return f"[感知 {timestamp}] " + " | ".join(parts)

    # ---- internal handlers ----

    def _handle_spawn(self, data: dict, new_entities: list):
        eid = data.get('entity_id')
        name = data.get('name', 'unknown')
        self._known_entities[eid] = {
            'name': name,
            'type': data.get('type', ''),
            'is_hostile': data.get('is_hostile', False),
            'first_seen': data.get('timestamp', 0),
            'last_seen': data.get('timestamp', 0),
        }
        new_entities.append({
            'name': name,
            'direction': data.get('direction', '?'),
            'distance': data.get('distance', 0),
        })

    def _handle_approaching(self, data: dict, approaching: list):
        eid = data.get('entity_id')
        name = data.get('name', 'unknown')
        if eid in self._known_entities:
            self._known_entities[eid]['last_seen'] = data.get('timestamp', 0)
        if data.get('is_hostile') or HOSTILE_MOBS.intersection({name}):
            approaching.append({
                'name': name,
                'direction': data.get('direction', '?'),
                'distance': data.get('distance', 0),
            })

    def _handle_gone(self, data: dict, gone_entities: list):
        eid = data.get('entity_id')
        known = self._known_entities.pop(eid, None)
        gone_entities.append({
            'name': data.get('name') or (known['name'] if known else 'unknown'),
        })

    def _handle_sound(self, data: dict, sounds: list):
        name = data.get('sound_name', 'unknown')
        # Simplify sound names: strip namespace prefix
        short_name = name.split('.')[-1] if '.' in name else name
        sounds.append({
            'name': short_name,
            'direction': data.get('direction', '?'),
            'distance': data.get('distance', 0),
        })

    def _handle_block_change(self, data: dict, block_changes: list):
        old_b = data.get('old_block', '')
        new_b = data.get('new_block', '')
        dist = data.get('distance', 0)

        # Agent-caused changes (air↔solid) near the agent
        if old_b in ('air', 'cave_air') and new_b not in ('air', 'cave_air'):
            block_changes.append(f"放置{new_b}({data.get('direction', '?')}{dist}格)")
        elif new_b in ('air', 'cave_air') and old_b not in ('air', 'cave_air'):
            block_changes.append(f"破坏{old_b}({data.get('direction', '?')}{dist}格)")
        # Ore/liquid/tnt changes
        elif new_b in ('water', 'lava') or old_b in ('water', 'lava'):
            block_changes.append(f"{old_b}→{new_b}({data.get('direction', '?')}{dist}格)")
        elif new_b in ORE_BLOCKS or old_b in ORE_BLOCKS:
            block_changes.append(f"{old_b}→{new_b}({data.get('direction', '?')}{dist}格)")
        elif new_b == 'tnt' or old_b == 'tnt':
            block_changes.append(f"{old_b}→{new_b}({data.get('direction', '?')}{dist}格)")
