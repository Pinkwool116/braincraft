"""
Reflex Layer

Handles survival reflexes and automatic behaviors.
Runs independently of the Agent Loop, reacting to game events.

This is a direct evolution of the original LowLevelBrain.
The reflex logic is preserved; only the class name and some interfaces change.

Responsibilities:
- Survival reflexes (fire, drowning, low health, combat)
- Stuck detection and recovery
- Quick actions (item collecting, elbow room)
- Autonomous modes (hunting, torch placing)

Priority levels (managed by ExecutionCoordinator):
- low_reflex (5): Survival reflexes — highest priority
- unstuck (4): Stuck detection
- low_quick (1): Quick actions
- low_auto (1): Autonomous modes
"""

import asyncio
import logging
import time
import random
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ReflexLayer:
    """
    Reflex layer for automatic survival behaviors.

    Runs as a separate async task alongside the Agent Loop.
    Uses ExecutionCoordinator for priority-based interruption.
    """

    def __init__(self, shared_state, exec_coordinator, ipc_server, config,
                 memory_manager=None):
        """
        Initialize the Reflex Layer.

        Args:
            shared_state: SharedState instance
            exec_coordinator: ExecutionCoordinator for priority management
            ipc_server: IPC server for sending commands to JS
            config: Configuration dictionary (full config with 'reflex' key)
            memory_manager: MemoryRouter for logging reflex events to working memory
        """
        self.shared_state = shared_state
        self.exec_coordinator = exec_coordinator
        self.ipc_server = ipc_server
        self.config = config
        self.memory_manager = memory_manager

        # Reflex log debounce (seconds between same-type entries)
        self._last_reflex_log: Dict[str, float] = {}
        reflex_config = config.get('reflex', {})
        self.modes_config = reflex_config.get('modes', {})
        self.interval = reflex_config.get('interval_seconds', 0.1)

        # Event queue for incoming events from JS
        self.event_queue = asyncio.Queue(maxsize=100)

        # Unstuck tracking
        self.prev_location = None
        self.stuck_time = 0
        self.last_check_time = time.time()
        self.stuck_distance_threshold = 2.0  # blocks
        self.max_stuck_time = 20  # seconds

        # Damage tracking
        self.last_damage_time = 0
        self.last_damage_amount = 0

        # Low health debounce
        self._last_low_health_escape_time = 0

        # Drowning debounce
        self._last_drowning_reflex_time = 0

        # Item collecting tracking
        self.prev_item = None
        self.item_noticed_at = -1
        self.item_wait_time = 2  # seconds

        # Torch placing tracking
        self.last_torch_place = time.time()
        self.torch_cooldown = 5  # seconds

        # Idle staring tracking
        self.staring = False
        self.last_entity = None
        self.next_stare_change = 0

        # Running flag
        self.running = False

        # Event handlers map
        self.event_handlers = {
            'combat_engaged': self.handle_combat,
            'low_health': self.handle_low_health,
            'on_fire': self._handle_on_fire,
            'drowning': self._handle_drowning,
            'stuck': self._handle_stuck,
            'state_update': self._handle_state_update,
            'execution_result': self._handle_execution_result,
            'damage_taken': self.handle_damage,
        }

        logger.info("ReflexLayer initialized")

    # ========== Memory Logging ==========

    def _log_reflex(self, event_type: str, content: str):
        """Log a reflex event to working memory with debounce (30s per type)."""
        if not self.memory_manager:
            return
        now = time.time()
        if now - self._last_reflex_log.get(event_type, 0) < 30:
            return
        self._last_reflex_log[event_type] = now
        try:
            self.memory_manager.log(entry_type='observation', content=content)
        except Exception as e:
            logger.debug(f"Failed to log reflex event: {e}")

    # ========== Execution Helper ==========

    async def _execute_with_coordinator(self, layer: str, label: str, action_fn, auto_resume: bool = True):
        """Execute an action through the ExecutionCoordinator."""
        result = await self.exec_coordinator.execute_action(
            layer=layer,
            label=label,
            action_fn=action_fn,
            can_interrupt=None,
            auto_resume=auto_resume
        )

        if result.get('blocked'):
            logger.debug(f"{label} blocked by higher priority action")
        elif result.get('cancelled'):
            logger.warning(f"{label} was cancelled by higher priority action")

        return result

    # ========== Main Loop ==========

    async def run(self):
        """
        Main reflex loop. Runs every ~100ms.

        Priority order:
        1. Process queued events
        2. Self-preservation checks
        3. Hunting / Item collecting
        4. Stuck detection
        5. Torch placing, Elbow room, Idle staring
        """
        self.running = True
        logger.info("ReflexLayer loop started")

        while self.running:
            try:
                # Process queued events (non-blocking)
                try:
                    event = self.event_queue.get_nowait()
                    await self._process_event(event)
                except asyncio.QueueEmpty:
                    pass

                # Priority 1: Self-preservation reflexes
                await self._check_self_preservation()

                # Priority 2: Hunting / Item collecting
                await self._check_hunting()
                await self._check_item_collecting()

                # Priority 3: Stuck detection
                await self._check_stuck()

                # Priority 4: Other modes
                await self._check_torch_placing()
                await self._check_elbow_room()
                await self._check_idle_staring()

            except asyncio.CancelledError:
                logger.info("ReflexLayer loop cancelled")
                break
            except Exception as e:
                logger.error(f"ReflexLayer loop error: {e}", exc_info=True)

            await asyncio.sleep(self.interval)

        logger.info("ReflexLayer loop stopped")

    def stop(self):
        """Stop the reflex loop."""
        self.running = False

    # ========== Event Handling ==========

    async def handle_event(self, event_type: str, data: Dict[str, Any]):
        """
        Receive event from brain_coordinator.

        Args:
            event_type: Event type string
            data: Event data
        """
        event = {'type': event_type, **data}
        try:
            self.event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Reflex event queue full, dropping: {event_type}")

    async def handle_perception_urgent(self, event_type: str, data: Dict[str, Any]):
        """
        Handle urgent perception threat pushed directly from PerceptionWorker.

        These bypass the perception buffer and EventTicker — they need immediate
        reflex response (combat, flee, stop movement).

        Args:
            event_type: 'hostile_close', 'lava_nearby', 'cliff_ahead', 'drowning'
            data: Threat details (distance, direction, entity info, etc.)
        """
        logger.info(f"Urgent perception threat: {event_type} data={data}")

        if event_type == 'hostile_close':
            entity_name = data.get('name', 'unknown')
            distance = data.get('distance', 0)
            logger.warning(f"Hostile mob nearby: {entity_name} at {distance} blocks")
            self._log_reflex('hostile_close',
                             f"感知层紧急预警: {entity_name} 出现在 {data.get('direction', '?')}侧{distance}格处")
            # Trigger combat reflex immediately
            await self.handle_combat({
                'enemy_type': entity_name,
                'distance': distance,
                'entity_id': data.get('entity_id')
            })

        elif event_type == 'lava_nearby':
            distance = data.get('distance', 0)
            direction = data.get('direction', 'forward')
            logger.warning(f"Lava nearby: {direction} at {distance} blocks")
            self._log_reflex('lava_nearby',
                             f"感知层紧急预警: {direction}方向{distance}格处检测到熔岩")
            # Cancel pathfinding, back up
            try:
                await self.ipc_server.send_command({
                    'type': 'execute_code',
                    'data': {
                        'code': """
                            bot.pathfinder.setGoal(null);
                            await skills.moveAway(bot, 5);
                            log(bot, "Backed away from lava!");
                        """,
                        'no_response': True
                    }
                })
            except Exception as e:
                logger.error(f"Lava reflex error: {e}")

        elif event_type == 'cliff_ahead':
            # Pathfinder natively avoids cliffs (maxDropDown=4) — no reflex needed.
            # Canceling pathfinding here would create a harmful conflict loop where
            # goto is repeatedly interrupted by cliff detection, breaking movement.
            distance = data.get('distance', 0)
            logger.debug(f"Cliff ahead at {distance} blocks (ignored — pathfinder handles this)")

        elif event_type == 'drowning':
            logger.warning("Drowning detected by perception worker")
            self._log_reflex('drowning_perception', '感知层紧急预警: 检测到溺水')
            await self._handle_drowning({'oxygen': data.get('oxygen', 'unknown')})

    async def _process_event(self, event: Dict[str, Any]):
        """Process a single event from the queue."""
        event_type = event.get('type')
        handler = self.event_handlers.get(event_type)
        if handler:
            logger.debug(f"Processing reflex event: {event_type}")
            await handler(event)
        else:
            logger.debug(f"Unknown reflex event type: {event_type}")

    # ========== Survival Reflexes (Priority 1) ==========

    async def handle_combat(self, data: dict):
        """
        Handle combat engagement — fight nearby enemies.
        Uses defendSelf skill with 8 block range.
        """
        enemy_type = data.get('enemy_type', 'enemy')
        logger.info(f"Combat reflex triggered: Fighting {enemy_type}!")
        self._log_reflex('combat', f"反射层触发战斗: 与 {enemy_type} 交战")

        await self._execute_with_coordinator(
            layer='low_reflex',
            label='reflex:combat',
            action_fn=lambda: self._execute_combat(enemy_type),
            auto_resume=True
        )

    async def _execute_combat(self, enemy_type: str):
        """Execute combat action via IPC."""
        try:
            await self.shared_state.update('reflex_triggered', 'combat')
            await self.shared_state.update('in_combat', True)

            await self.ipc_server.send_command({
                'type': 'execute_skill',
                'data': {
                    'skill': 'defendSelf',
                    'params': [8]
                }
            })

            await self.shared_state.update('last_reflex', 'combat')
        except asyncio.CancelledError:
            logger.warning("Combat was cancelled")
            raise
        except Exception as e:
            logger.error(f"Combat reflex error: {e}")
        finally:
            await self.shared_state.update('reflex_triggered', None)
            await self.shared_state.update('in_combat', False)

    async def handle_low_health(self, data: dict):
        """
        Handle low health — escape 20 blocks away.
        Triggers when health < 5 or last damage >= current health.
        """
        health = data.get('health', 20)

        # Debounce
        current_time = time.time()
        if (current_time - self._last_low_health_escape_time) < 5.0:
            return

        logger.warning(f"Low health reflex triggered: health={health}")
        self._log_reflex('low_health', f"反射层触发低血量逃生: 血量={health}, 向远处逃离")

        await self._execute_with_coordinator(
            layer='low_reflex',
            label='reflex:low_health',
            action_fn=lambda: self._execute_escape(health, 20, 'low_health'),
        )
        self._last_low_health_escape_time = current_time

    async def handle_damage(self, data: dict):
        """Track damage for self-preservation checks."""
        self.last_damage_time = data.get('timestamp', time.time())
        self.last_damage_amount = data.get('damage', 0)
        logger.debug(f"Damage taken: {self.last_damage_amount}")
        if self.last_damage_amount >= 3:
            self._log_reflex('damage', f"反射层检测到受伤: 受到 {self.last_damage_amount} 点伤害")

    async def _handle_on_fire(self, event: Dict[str, Any]):
        """
        Handle on fire — find water or escape.
        Priority: water bucket > nearest water > move away.
        """
        logger.warning("On fire reflex triggered!")
        self._log_reflex('on_fire', '反射层触发着火逃生: 正在寻找水源或逃离')
        position = event.get('position', {})
        has_water_bucket = event.get('has_water_bucket', False)

        await self._execute_with_coordinator(
            layer='low_reflex',
            label='reflex:on_fire',
            action_fn=lambda: self._execute_on_fire_escape(position, has_water_bucket),
        )

    async def _execute_on_fire_escape(self, position: Dict[str, Any], has_water_bucket: bool):
        """Execute on-fire escape via IPC."""
        try:
            if has_water_bucket:
                x = position.get('x', 0)
                y = position.get('y', 0)
                z = position.get('z', 0)
                await self.ipc_server.send_command({
                    'type': 'execute_code',
                    'data': {
                        'code': f"""
                            bot.pathfinder.setGoal(null);
                            await skills.placeBlock(bot, 'water_bucket', {x}, {y}, {z});
                            log(bot, "Placed water bucket to extinguish fire");
                        """,
                        'no_response': True
                    }
                })
            else:
                await self.ipc_server.send_command({
                    'type': 'execute_code',
                    'data': {
                        'code': """
                            bot.pathfinder.setGoal(null);
                            let nearestWater = world.getNearestBlock(bot, 'water', 20);
                            if (nearestWater) {
                                const pos = nearestWater.position;
                                await skills.goToPosition(bot, pos.x, pos.y, pos.z, 0.2);
                                log(bot, "Found water!");
                            } else {
                                await skills.moveAway(bot, 5);
                            }
                        """,
                        'no_response': True
                    }
                })
            await self.shared_state.update('last_reflex', 'on_fire')
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"On fire reflex error: {e}")

    async def _handle_drowning(self, event: Dict[str, Any]):
        """
        Handle drowning — jump to swim up.
        Only active when bot is NOT pathfinding.
        """
        current_time = time.time()
        if (current_time - self._last_drowning_reflex_time) < 1.0:
            return

        logger.debug("Drowning reflex: swimming up")
        self._log_reflex('drowning', '反射层触发溺水逃生: 正在向上游')
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        if (!bot.pathfinder.goal) {
                            bot.setControlState('jump', true);
                        }
                    """,
                    'no_response': True
                }
            })
            await self.shared_state.update('last_reflex', 'drowning')
            self._last_drowning_reflex_time = current_time
        except Exception as e:
            logger.error(f"Drowning reflex error: {e}")

    async def _execute_escape(self, health: float, distance: int, label: str):
        """Generic escape action — cancel pathfinding and move away."""
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': f"""
                        bot.pathfinder.setGoal(null);
                        await skills.moveAway(bot, {distance});
                        log(bot, "Escaped from danger!");
                    """,
                    'no_response': True
                }
            })
            await self.shared_state.update('health', health)
            await self.shared_state.update('last_reflex', label)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Escape ({label}) error: {e}")

    # ========== Self-Preservation Check ==========

    async def _check_self_preservation(self):
        """Check low health after recent damage."""
        if not self.modes_config.get('self_preservation', True):
            return

        state = await self.shared_state.get_all()
        health = state.get('health', 20)
        time_since_damage = time.time() - self.last_damage_time

        if time_since_damage < 3.0 and (health < 5 or self.last_damage_amount >= health):
            # Debounce
            current_time = time.time()
            if (current_time - self._last_low_health_escape_time) < 5.0:
                return

            await self._execute_with_coordinator(
                layer='low_reflex',
                label='reflex:low_health',
                action_fn=lambda: self._execute_escape(health, 20, 'low_health'),
                auto_resume=True
            )
            self._last_low_health_escape_time = current_time

    # ========== Stuck Detection (Priority 3) ==========

    async def _handle_stuck(self, event: Dict[str, Any]):
        """Handle explicit stuck event."""
        logger.warning("Stuck reflex triggered!")
        self._log_reflex('stuck', '反射层触发卡住逃生: 正在脱离卡住位置')
        await self._execute_with_coordinator(
            layer='unstuck',
            label='reflex:unstuck',
            action_fn=self._execute_unstuck,
        )

    async def _check_stuck(self):
        """Periodic stuck detection based on position tracking."""
        state = await self.shared_state.get_all()
        is_idle = state.get('is_idle', True)
        position = state.get('position', {})

        if is_idle:
            self.prev_location = None
            self.stuck_time = 0
            return

        current_pos = (position.get('x', 0), position.get('y', 0), position.get('z', 0))
        current_time = time.time()
        time_delta = current_time - self.last_check_time
        self.last_check_time = current_time

        if self.prev_location is None:
            self.prev_location = current_pos
            return

        distance = self._calculate_distance(self.prev_location, current_pos)

        if distance < self.stuck_distance_threshold:
            self.stuck_time += time_delta
        else:
            self.prev_location = current_pos
            self.stuck_time = 0

        if self.stuck_time > self.max_stuck_time:
            logger.warning(f"Stuck detected: {self.stuck_time:.1f}s in same location")
            self._log_reflex('stuck', f"反射层自动检测到卡住: {self.stuck_time:.0f}秒未移动, 正在脱离")
            result = await self._execute_with_coordinator(
                layer='unstuck',
                label='mode:unstuck',
                action_fn=self._execute_unstuck,
                auto_resume=True
            )
            if not result.get('blocked') and not result.get('cancelled'):
                self.stuck_time = 0

    async def _execute_unstuck(self):
        """Move away 5 blocks to escape stuck position."""
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        bot.pathfinder.setGoal(null);
                        await skills.moveAway(bot, 5);
                        log(bot, "Escaped from stuck position");
                    """,
                    'no_response': True
                }
            })
            self.prev_location = None
            self.stuck_time = 0
            await self.shared_state.update('last_reflex', 'unstuck')
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Unstuck reflex error: {e}")

    # ========== Autonomous Modes ==========

    async def _check_hunting(self):
        """Hunt nearby animals within 8 blocks when idle."""
        if not self.modes_config.get('hunting', True):
            return
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return

        await self._execute_with_coordinator(
            layer='low_auto',
            label='hunting',
            action_fn=self._execute_hunting,
            auto_resume=False
        )

    async def _execute_hunting(self):
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        const huntable = world.getNearestEntityWhere(
                            bot, entity => mc.isHuntable(entity), 8
                        );
                        if (huntable && await world.isClearPath(bot, huntable)) {
                            log(bot, `Hunting ${huntable.name}!`);
                            await skills.attackEntity(bot, huntable);
                        }
                    """,
                    'no_response': True
                }
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Hunting error: {e}")

    async def _check_item_collecting(self):
        """Collect nearby items after a wait period."""
        if not self.modes_config.get('item_collecting', True):
            self.item_noticed_at = -1
            return
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return

        if self.item_noticed_at > 0:
            if time.time() - self.item_noticed_at > self.item_wait_time:
                result = await self._execute_with_coordinator(
                    layer='low_quick',
                    label='item_collecting',
                    action_fn=self._execute_item_collecting,
                    auto_resume=False
                )
                if result.get('blocked') or result.get('cancelled'):
                    self.item_noticed_at = -1
                    return
                self.item_noticed_at = -1

    async def _execute_item_collecting(self):
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        log(bot, 'Picking up item!');
                        await skills.pickupNearbyItems(bot);
                    """,
                    'no_response': True
                }
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Item collecting error: {e}")

    async def _check_torch_placing(self):
        """Place torches in dark areas."""
        if not self.modes_config.get('torch_placing', True):
            return
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return
        if time.time() - self.last_torch_place < self.torch_cooldown:
            return

        result = await self._execute_with_coordinator(
            layer='low_auto',
            label='torch_placing',
            action_fn=self._execute_torch_placing,
            auto_resume=False
        )
        if not result.get('blocked') and not result.get('cancelled'):
            self.last_torch_place = time.time()

    async def _execute_torch_placing(self):
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        if (world.shouldPlaceTorch(bot)) {
                            const pos = bot.entity.position;
                            await skills.placeBlock(bot, 'torch', pos.x, pos.y, pos.z, 'bottom', true);
                        }
                    """,
                    'no_response': True
                }
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Torch placing error: {e}")

    async def _check_elbow_room(self):
        """Move away from players that are too close."""
        if not self.modes_config.get('elbow_room', True):
            return
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return

        await self._execute_with_coordinator(
            layer='low_quick',
            label='elbow_room',
            action_fn=self._execute_elbow_room,
            auto_resume=False
        )

    async def _execute_elbow_room(self):
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        const player = world.getNearestEntityWhere(
                            bot, entity => entity.type === 'player', 0.5
                        );
                        if (player) {
                            const wait_time = Math.random() * 1000;
                            await new Promise(resolve => setTimeout(resolve, wait_time));
                            if (player.position.distanceTo(bot.entity.position) < 0.5) {
                                await skills.moveAwayFromEntity(bot, player, 0.5);
                            }
                        }
                    """,
                    'no_response': True
                }
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Elbow room error: {e}")

    async def _check_idle_staring(self):
        """Look at nearby entities when idle — makes bot feel alive."""
        if not self.modes_config.get('idle_staring', True):
            return

        try:
            current_time = time.time()
            if current_time > self.next_stare_change:
                self.staring = random.random() < 0.3

                if not self.staring:
                    await self.ipc_server.send_command({
                        'type': 'execute_code',
                        'data': {
                            'code': """
                                const yaw = Math.random() * Math.PI * 2;
                                const pitch = (Math.random() * Math.PI/2) - Math.PI/4;
                                bot.look(yaw, pitch, false);
                            """,
                            'no_response': True
                        }
                    })

                self.next_stare_change = current_time + random.random() * 10 + 2

            if self.staring:
                await self.ipc_server.send_command({
                    'type': 'execute_code',
                    'data': {
                        'code': """
                            const entity = bot.nearestEntity();
                            let entity_in_view = entity &&
                                entity.position.distanceTo(bot.entity.position) < 10 &&
                                entity.name !== 'enderman';
                            if (entity_in_view) {
                                let isbaby = entity.type !== 'player' && entity.metadata[16];
                                let height = isbaby ? entity.height/2 : entity.height;
                                bot.lookAt(entity.position.offset(0, height, 0));
                            }
                        """,
                        'no_response': True
                    }
                })
        except Exception as e:
            logger.error(f"Idle staring error: {e}")

    # ========== State Event Handlers ==========

    async def _handle_state_update(self, event: Dict[str, Any]):
        """Update shared state from JS state updates."""
        state_data = event.get('data', event)
        for key, value in state_data.items():
            if key != 'type':
                await self.shared_state.update(key, value)

    async def _handle_execution_result(self, event: Dict[str, Any]):
        """Store execution result in shared state."""
        result = event.get('data', event)
        await self.shared_state.update('last_execution_result', result)

    # ========== Utility ==========

    @staticmethod
    def _calculate_distance(pos1: tuple, pos2: tuple) -> float:
        """Calculate 3D distance between two positions."""
        return ((pos1[0] - pos2[0])**2 +
                (pos1[1] - pos2[1])**2 +
                (pos1[2] - pos2[2])**2) ** 0.5
