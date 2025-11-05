"""
Low-Level Brain

Responsible for:
- Reflex system (ported from modes.js)
- Real-time event handling
- Immediate threat responses
- Event-driven task execution without LLM involvement

Modes implemented (from original modes.js):
1. Self-preservation (fire, lava, drowning, low health) - PRIORITY 1
2. Unstuck mechanism - PRIORITY 2
3. Self-defense (combat) / Cowardice (flee) - PRIORITY 3
4. Hunting (hunt animals when idle) - PRIORITY 4
5. Item collecting (pick up items when idle) - PRIORITY 5
6. Torch placing (auto lighting when idle) - PRIORITY 6
7. Elbow room (avoid players when idle) - PRIORITY 7
8. Idle staring (look around when idle) - PRIORITY 8
"""

import asyncio
import logging
from typing import Dict, Any
import time

logger = logging.getLogger(__name__)

class LowLevelBrain:
    """
    Low-level brain for reflex responses
    
    Handles real-time events from the game without LLM involvement:
    - Combat reflexes
    - Survival reflexes (fire, drowning, low health)
    - Unstuck mechanism
    - Interrupt handling
    
    Ported from original MindCraft modes.js
    """
    
    def __init__(self, shared_state, ipc_server, config):
        """
        Initialize low-level brain
        
        Args:
            shared_state: Shared state object
            ipc_server: IPC server for communication with JS
            config: Configuration object (full config with low_level_brain key)
        """
        self.shared_state = shared_state
        self.ipc_server = ipc_server
        self.config = config
        
        # Extract low-level brain specific config
        low_config = config.get('low_level_brain', {})
        self.modes_config = low_config.get('modes', {})
        
        self.event_queue = asyncio.Queue(maxsize=100)
        self.reflex_active = False
        
        # Unstuck tracking (ported from modes.js unstuck mode)
        self.prev_location = None
        self.stuck_time = 0
        self.last_check_time = time.time()
        self.stuck_distance_threshold = 2.0  # blocks
        self.max_stuck_time = 20  # seconds
        
        # Damage tracking (for self-preservation)
        self.last_damage_time = 0
        self.last_damage_amount = 0
        
        # Item collecting tracking (ported from modes.js)
        self.prev_item = None
        self.item_noticed_at = -1
        self.item_wait_time = 2  # seconds
        
        # Torch placing tracking (ported from modes.js)
        self.last_torch_place = time.time()
        self.torch_cooldown = 5  # seconds
        
        # Idle staring tracking (ported from modes.js)
        self.staring = False
        self.last_entity = None
        self.next_stare_change = 0
        
        # Register event handlers
        self.event_handlers = {
            'combat_engaged': self._handle_combat,
            'low_health': self._handle_low_health,
            'on_fire': self._handle_on_fire,
            'drowning': self._handle_drowning,
            'stuck': self._handle_stuck,
            'state_update': self._handle_state_update,
            'execution_result': self._handle_execution_result,
            'damage_taken': self._handle_damage,
        }
        
        logger.info("Low-level brain initialized with reflex system")
    
    async def handle_events(self):
        """
        Main event handling loop
        
        Called every 100ms by the coordinator to process events.
        Also performs periodic checks (stuck detection, modes, etc.).
        
        Priority order:
        1. Self-preservation (fire, drowning, low health) - Reflexes
        2. Combat / Hunting - Modes
        3. Item collecting - Modes
        4. Unstuck
        5. Torch placing, Elbow room, Idle staring - Other modes
        """
        # Process queued events
        try:
            # Get event from queue (non-blocking)
            event = self.event_queue.get_nowait()
            await self._process_event(event)
        except asyncio.QueueEmpty:
            # No events to process
            pass
        
        # Periodic checks (following priority order)
        # ExecutionCoordinator now manages concurrency, no need for mode_active
        
        # Priority 1: Reflexes 
        await self._check_self_preservation()
        
        # Priority 2: Modes 
        await self.check_hunting()         # Hunt animals when idle
        await self.check_item_collecting() # Collect items when idle
        
        # Priority 3: Unstuck
        await self._check_stuck()
        
        # Priority 4: Other modes
        await self.check_torch_placing()   # Place torches when dark and idle
        await self.check_elbow_room()      # Move away from players when idle
        await self.check_idle_staring()    # Look around when idle
    
    async def receive_event(self, event: Dict[str, Any]):
        """
        Receive event from JavaScript via IPC
        
        Args:
            event: Event dictionary from JS
        """
        await self.event_queue.put(event)
    
    async def handle_event(self, event_type: str, data: Dict[str, Any]):
        """
        Handle event from brain coordinator
        
        This is called by brain_coordinator when it receives messages from JS.
        
        Args:
            event_type: Type of event (e.g., 'combat_engaged', 'low_health')
            data: Event data
        """
        event = {'type': event_type, 'data': data, **data}
        await self.event_queue.put(event)
    
    async def _process_event(self, event: Dict[str, Any]):
        """
        Process a single event
        
        Args:
            event: Event to process
        """
        event_type = event.get('type')
        
        if event_type in self.event_handlers:
            logger.debug(f"Processing event: {event_type}")
            await self.event_handlers[event_type](event)
        else:
            logger.warning(f"Unknown event type: {event_type}")
    
    async def _handle_combat(self, event: Dict[str, Any]):
        """
        Handle combat reflex (ported from modes.js self_defense)
        
        Immediately respond to nearby enemies without LLM.
        Uses the defendSelf skill with 8 block range.
        Highest priority - can interrupt modes and mid-level tasks.
        
        Args:
            event: Combat event data with enemy_type, enemy_id
        """
        if self.reflex_active:
            return
        
        self.reflex_active = True
        enemy_type = event.get('enemy_type', 'enemy')
        logger.info(f"Combat reflex triggered: Fighting {enemy_type}!")
        
        try:
            # Notify other layers that reflex is active
            await self.shared_state.update('reflex_triggered', 'combat')
            
            # Send defend command to JavaScript
            await self.ipc_server.send_command({
                'type': 'execute_skill',
                'data': {
                    'skill': 'defendSelf',
                    'params': [8]  # 8 block range
                }
            })
            
            # Update shared state
            await self.shared_state.update('in_combat', True)
            await self.shared_state.update('last_reflex', 'combat')
            
        except Exception as e:
            logger.error(f"Combat reflex error: {e}")
        finally:
            self.reflex_active = False
            await self.shared_state.update('reflex_triggered', None)
    
    async def _handle_low_health(self, event: Dict[str, Any]):
        """
        Handle low health reflex (ported from modes.js self_preservation)
        
        Triggers when health < 5 or last damage >= current health.
        Escapes by moving 20 blocks away.
        
        Args:
            event: Health event data with health value
        """
        if self.reflex_active:
            return
        
        health = event.get('health', 20)
        
        self.reflex_active = True
        logger.warning(f"Low health reflex triggered: I'm dying! Health={health}")
        
        try:
            # Send escape command (moveAway 20 blocks)
            await self.ipc_server.send_command({
                'type': 'execute_skill',
                'data': {
                    'skill': 'moveAway',
                    'params': [20]
                }
            })
            
            # Update shared state
            await self.shared_state.update('health', health)
            await self.shared_state.update('last_reflex', 'low_health')
            
        except Exception as e:
            logger.error(f"Low health reflex error: {e}")
        finally:
            self.reflex_active = False
    
    async def _handle_on_fire(self, event: Dict[str, Any]):
        """
        Handle on fire reflex (ported from modes.js self_preservation)
        
        Priority:
        1. Use water bucket if available
        2. Find nearest water source
        3. Move away from fire/lava
        """
        if self.reflex_active:
            return
        
        self.reflex_active = True
        logger.warning("On fire reflex triggered: I'm on fire!")
        
        try:
            position = event.get('position', {})
            has_water_bucket = event.get('has_water_bucket', False)
            
            if has_water_bucket:
                # Place water at current position
                await self.ipc_server.send_command({
                    'type': 'execute_skill',
                    'data': {
                        'skill': 'placeBlock',
                        'params': ['water_bucket', position.get('x'), 
                                  position.get('y'), position.get('z')]
                    }
                })
                logger.info("Placed water bucket to extinguish fire")
            else:
                # Try to find water
                await self.ipc_server.send_command({
                    'type': 'execute_code',
                    'data': {
                        'code': """
                            // Find nearest water and go to it
                            let nearestWater = world.getNearestBlock(bot, 'water', 20);
                            if (nearestWater) {
                                const pos = nearestWater.position;
                                await skills.goToPosition(bot, pos.x, pos.y, pos.z, 0.2);
                                log(bot, "Found water, ahhhh that's better!");
                            } else {
                                await skills.moveAway(bot, 5);
                            }
                        """,
                        'no_response': True
                    }
                })
            
            await self.shared_state.update('last_reflex', 'on_fire')
            
        except Exception as e:
            logger.error(f"On fire reflex error: {e}")
        finally:
            self.reflex_active = False
    
    async def _handle_drowning(self, event: Dict[str, Any]):
        """
        Handle drowning reflex (ported from modes.js self_preservation)
        
        Simply jumps to swim to surface.
        This is called when blockAbove is water.
        """
        logger.warning("Drowning reflex triggered: Swimming to surface")
        
        try:
            # Send jump command (doesn't interrupt current goal)
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': 'bot.setControlState("jump", true);',
                    'no_response': True
                }
            })
            
            await self.shared_state.update('last_reflex', 'drowning')
            
        except Exception as e:
            logger.error(f"Drowning reflex error: {e}")
    
    async def _handle_stuck(self, event: Dict[str, Any]):
        """
        Handle stuck reflex (ported from modes.js unstuck mode)
        
        Triggered when agent is in same position for too long while active.
        Attempts to escape by moving away 5 blocks.
        """
        if self.reflex_active:
            return
        
        self.reflex_active = True
        logger.warning("Stuck reflex triggered: I'm stuck!")
        
        try:
            # Move away 5 blocks to get unstuck
            await self.ipc_server.send_command({
                'type': 'execute_skill',
                'data': {
                    'skill': 'moveAway',
                    'params': [5]
                }
            })
            
            # Reset stuck tracking
            self.prev_location = None
            self.stuck_time = 0
            
            await self.shared_state.update('last_reflex', 'unstuck')
            logger.info("Unstuck attempt completed")
            
        except Exception as e:
            logger.error(f"Unstuck reflex error: {e}")
        finally:
            self.reflex_active = False
    
    async def _handle_state_update(self, event: Dict[str, Any]):
        """
        Handle game state update from JS
        
        Args:
            event: State update event
        """
        state_data = event.get('data', {})
        
        # Update shared state
        for key, value in state_data.items():
            await self.shared_state.update(key, value)
        
        logger.debug(f"State updated: {list(state_data.keys())}")
    
    async def _handle_execution_result(self, event: Dict[str, Any]):
        """
        Handle code execution result from JS
        
        Args:
            event: Execution result event
        """
        result = event.get('data', {})
        
        # Update shared state with result (mid-level brain can check this)
        await self.shared_state.update('last_execution_result', result)
        
        logger.debug(f"Execution result: {result.get('success')}")
    
    async def _wait_for_execution_result(self, timeout: float = 30.0, expect_response: bool = True):
        """
        Wait for execution result from JavaScript
        
        Args:
            timeout: Maximum time to wait in seconds
        
        Returns:
            Execution result dictionary
        """
        # Only clear previous result when the caller expects a response.
        # Low-level fire-and-forget calls use no_response=True and should
        # not clear or wait for a result (to avoid clobbering mid-level results).
        if expect_response:
            await self.shared_state.update('last_execution_result', None)
        
        start_time = asyncio.get_event_loop().time()
        poll_interval = 0.1
        
        while True:
            result = await self.shared_state.get('last_execution_result')
            
            if result is not None:
                return result
            
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout:
                logger.error("Execution timeout - no response from JavaScript")
                return {
                    'success': False,
                    'message': 'Execution timeout'
                }
            
            # Wait before next check (this is a cancellation point)
            await asyncio.sleep(poll_interval)
    
    async def _handle_damage(self, event: Dict[str, Any]):
        """
        Handle damage event
        
        Args:
            event: Damage event with damage amount and timestamp
        """
        self.last_damage_time = event.get('timestamp', time.time())
        self.last_damage_amount = event.get('damage', 0)
        
        logger.debug(f"Damage taken: {self.last_damage_amount}")
    
    async def _check_stuck(self):
        """
        Check if agent is stuck (ported from modes.js unstuck mode)
        
        Tracks position over time and triggers unstuck reflex if:
        - Agent hasn't moved more than 2 blocks in 20 seconds
        - Agent is currently active (not idle)
        """
        # Get current state
        state = await self.shared_state.get_all()
        is_idle = state.get('is_idle', True)
        position = state.get('position', {})
        
        if is_idle:
            # Reset tracking when idle
            self.prev_location = None
            self.stuck_time = 0
            return
        
        # Get position as tuple for comparison
        current_pos = (position.get('x', 0), position.get('y', 0), position.get('z', 0))
        current_time = time.time()
        time_delta = current_time - self.last_check_time
        self.last_check_time = current_time
        
        if self.prev_location is None:
            self.prev_location = current_pos
            return
        
        # Calculate distance moved
        distance = self._calculate_distance(self.prev_location, current_pos)
        
        if distance < self.stuck_distance_threshold:
            # Not moving much, accumulate stuck time
            self.stuck_time += time_delta
        else:
            # Moving normally, reset
            self.prev_location = current_pos
            self.stuck_time = 0
        
        # Trigger unstuck reflex if stuck too long
        if self.stuck_time > self.max_stuck_time:
            logger.warning(f"Stuck detected: {self.stuck_time:.1f}s in same location")
            
            # Use ExecutionCoordinator
            if hasattr(self, 'exec_coordinator') and self.exec_coordinator:
                result = await self.exec_coordinator.execute_action(
                    layer='unstuck',
                    label='mode:unstuck',
                    action_fn=lambda: self._get_unstuck(),
                    can_interrupt=['low_reflex', 'low_mode'],  # Can be interrupted by reflexes and modes
                    auto_resume=True
                )
                
                if result.get('cancelled'):
                    logger.info("Unstuck was cancelled by higher priority action")
                    return
                
                if not result.get('blocked'):
                    self.stuck_time = 0  # Reset stuck time
            else:
                # Backward compatibility
                await self._handle_stuck({})
    
    async def _get_unstuck(self):
        """Execute unstuck action"""
        logger.warning("🚨 Getting unstuck!")
        
        try:
            # Send unstuck command - use moveAway like original project
            await self.send_immediate_command({
                'type': 'execute_skill',
                'data': {
                    'skill': 'moveAway',
                    'params': [5]  # Move away 5 blocks to get unstuck
                }
            })
            
            await asyncio.sleep(1)
            
            self.prev_location = None
            
        except asyncio.CancelledError:
            logger.warning("⚠️ Unstuck action cancelled by higher priority action")
            raise  # Re-raise to propagate cancellation
            
        except Exception as e:
            logger.error(f"Error getting unstuck: {e}")
    
    async def _check_self_preservation(self):
        """
        Check self-preservation conditions (ported from modes.js self_preservation)
        
        Checks for:
        - Low health after recent damage
        - On fire (lava/fire blocks)
        - Drowning (water above)
        - Falling blocks above
        """
        # Check if self-preservation is enabled in config
        self_preservation_enabled = self.modes_config.get('self_preservation', True)
        if not self_preservation_enabled:
            return
        
        state = await self.shared_state.get_all()
        
        # Check low health condition
        health = state.get('health', 20)
        time_since_damage = time.time() - self.last_damage_time
        
        if time_since_damage < 3.0 and (health < 5 or self.last_damage_amount >= health):

            if hasattr(self, 'exec_coordinator') and self.exec_coordinator:
                result = await self.exec_coordinator.execute_action(
                    layer='low_reflex',
                    label='reflex:low_health',
                    action_fn=lambda: self._escape_low_health(health),
                    can_interrupt=None,
                    auto_resume=True
                )
                
                # Reflex actions shouldn't be cancelled (highest priority)
                # But check anyway for robustness
                if result.get('cancelled'):
                    logger.warning("⚠️ Reflex was cancelled (should not happen!)")
                    return
                
                # Low health reflex executed
            else:
                
                await self.receive_event({
                    'type': 'low_health',
                    'health': health
                })
            return
        
        # Other checks would be triggered by state_update events from JS
        # (fire, drowning, etc. are detected in reflex_controller.js)
    
    async def _escape_low_health(self, health: float):
        logger.warning(f"⚠️ Low health reflex: {health}/20 - Escaping!")
        
        try:
            
            await self.send_immediate_command({
                'type': 'execute_skill',
                'data': {
                    'skill': 'moveAway',
                    'params': [20]
                }
            })
            
            
            await self.shared_state.update('last_reflex', 'low_health')
            
            
            await asyncio.sleep(2)
            
        except asyncio.CancelledError:
            logger.warning("⚠️ Low health escape cancelled (should not happen - highest priority!)")
            raise  # Re-raise to propagate cancellation
            
        except Exception as e:
            logger.error(f"Error during low health escape: {e}")
    
    def _calculate_distance(self, pos1: tuple, pos2: tuple) -> float:
        """
        Calculate 3D distance between two positions
        
        Args:
            pos1: (x, y, z) tuple
            pos2: (x, y, z) tuple
        
        Returns:
            Distance in blocks
        """
        return ((pos1[0] - pos2[0])**2 + 
                (pos1[1] - pos2[1])**2 + 
                (pos1[2] - pos2[2])**2) ** 0.5
    
    async def send_immediate_command(self, command: Dict[str, Any]):
        """
        Send immediate command to JavaScript
        
        Used for reflex actions that bypass normal task queue.
        
        Args:
            command: Command dictionary
        """
        try:
            await self.ipc_server.send_command(command)
            logger.debug(f"Immediate command sent: {command.get('type')}")
        except Exception as e:
            logger.error(f"Error sending immediate command: {e}")
    
    # ========== Additional Modes from modes.js ==========
    
    async def check_cowardice(self):
        """
        Cowardice mode: Run away from enemies (ported from modes.js)
        
        Checks for hostile entities within 16 blocks and runs away.
        Higher priority than hunting/self-defense (runs first).
        """
        if self.reflex_active:
            return
        
        # Check if mode is enabled in config
        cowardice_enabled = self.modes_config.get('cowardice', False)
        if not cowardice_enabled:
            return
        
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        // Check for nearby hostile entities
                        const enemy = world.getNearestEntityWhere(
                            bot, 
                            entity => mc.isHostile(entity), 
                            16
                        );
                        if (enemy && await world.isClearPath(bot, enemy)) {
                            log(bot, `Aaa! A ${enemy.name.replace("_", " ")}!`);
                            await skills.avoidEnemies(bot, 24);
                        }
                    """,
                    'no_response': True
                }
            })
        except Exception as e:
            logger.error(f"Cowardice check error: {e}")
    
    async def check_hunting(self):
        """
        Hunting mode: Hunt nearby animals (ported from modes.js)
        
        Hunts animals within 8 blocks when idle.
        """
        if self.reflex_active:
            return
        
        # Check if bot is ready
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return
        
        hunting_enabled = self.modes_config.get('hunting', True)
        if not hunting_enabled:
            return
        
        # Use ExecutionCoordinator to manage execution
        if hasattr(self, 'exec_coordinator') and self.exec_coordinator:
            result = await self.exec_coordinator.execute_action(
                layer='low_auto',  # Autonomous mode - low priority, won't interrupt mid
                label='hunting',
                action_fn=lambda: self._execute_hunting(),
                can_interrupt=[],  # Same priority modes don't interrupt each other
                auto_resume=False
            )
            
            if result.get('blocked'):
                # Higher priority task is executing, skip silently
                return
            
            if result.get('cancelled'):
                logger.debug("Hunting was cancelled by higher priority action")
                return
    
    async def _execute_hunting(self):
        """Execute hunting mode code"""
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        const huntable = world.getNearestEntityWhere(
                            bot, 
                            entity => mc.isHuntable(entity), 
                            8
                        );
                        if (huntable && await world.isClearPath(bot, huntable)) {
                            log(bot, `Hunting ${huntable.name}!`);
                            await skills.attackEntity(bot, huntable);
                        }
                    """,
                    'no_response': True
                }
            })
            
            # Wait for execution result (we sent no_response=True so do not expect one)
            await self._wait_for_execution_result(expect_response=False)
            
        except asyncio.CancelledError:
            logger.debug("Hunting execution cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during hunting: {e}")
    
    async def check_item_collecting(self):
        """
        Item collecting mode: Collect nearby items when idle (ported from modes.js)
        
        Waits 2 seconds after noticing an item before picking it up.
        """
        if self.reflex_active:
            return
        
        # Check if bot is ready
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return
        
        collecting_enabled = self.modes_config.get('item_collecting', True)
        if not collecting_enabled:
            self.item_noticed_at = -1
            return
        
        try:
            # Check if we've noticed an item
            if self.item_noticed_at > 0:
                if time.time() - self.item_noticed_at > self.item_wait_time:
                    # Time to pick it up - use ExecutionCoordinator
                    if hasattr(self, 'exec_coordinator') and self.exec_coordinator:
                        result = await self.exec_coordinator.execute_action(
                            layer='low_quick',  # Quick action - low priority, won't interrupt mid
                            label='item_collecting',
                            action_fn=lambda: self._execute_item_collecting(),
                            can_interrupt=[],
                            auto_resume=False
                        )
                        
                        if result.get('blocked'):
                            # Higher priority task executing, reset timer
                            self.item_noticed_at = -1
                            return
                        
                        if result.get('cancelled'):
                            logger.debug("Item collecting cancelled")
                            self.item_noticed_at = -1
                            return
                    
                    self.item_noticed_at = -1
            else:
                # Check for new items (lightweight check, don't use ExecutionCoordinator)
                # This is just observation, not action
                # TODO: Implement item detection logic
                pass
                
        except Exception as e:
            logger.error(f"Item collecting check error: {e}")
    
    async def _execute_item_collecting(self):
        """Execute item collecting mode code"""
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
            
            # Wait for execution result (we sent no_response=True so do not expect one)
            await self._wait_for_execution_result(expect_response=False)
            
        except asyncio.CancelledError:
            logger.debug("Item collecting execution cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during item collecting: {e}")
    
    async def check_torch_placing(self):
        """
        Torch placing mode: Place torches when dark (ported from modes.js)
        
        Places torches when idle and no torches nearby.
        Has cooldown to avoid spamming.
        """
        if self.reflex_active:
            return
        
        # Check if bot is ready
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return
        
        torch_enabled = self.modes_config.get('torch_placing', True)
        if not torch_enabled:
            return
        
        if time.time() - self.last_torch_place < self.torch_cooldown:
            return
        
        # Use ExecutionCoordinator to manage execution
        if hasattr(self, 'exec_coordinator') and self.exec_coordinator:
            result = await self.exec_coordinator.execute_action(
                layer='low_auto',  # Autonomous mode - low priority, won't interrupt mid
                label='torch_placing',
                action_fn=lambda: self._execute_torch_placing(),
                can_interrupt=[],
                auto_resume=False
            )
            
            if result.get('blocked'):
                # Higher priority task executing, skip
                return
            
            if result.get('cancelled'):
                logger.debug("Torch placing cancelled")
                return
            
            # Update cooldown after execution
            self.last_torch_place = time.time()
    
    async def _execute_torch_placing(self):
        """Execute torch placing mode code"""
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
            
            # Wait for execution result (we sent no_response=True so do not expect one)
            await self._wait_for_execution_result(expect_response=False)
            
        except asyncio.CancelledError:
            logger.debug("Torch placing execution cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during torch placing: {e}")
    
    async def check_elbow_room(self):
        """
        Elbow room mode: Move away from players (ported from modes.js)
        
        Maintains minimum distance from other players when idle.
        Only executes when a player is actually too close.
        """
        if self.reflex_active:
            return
        
        # Check if bot is ready
        bot_ready = await self.shared_state.get('bot_ready') or False
        if not bot_ready:
            return
        
        elbow_room_enabled = self.modes_config.get('elbow_room', True)
        if not elbow_room_enabled:
            return
        
        # Use ExecutionCoordinator to manage execution
        if hasattr(self, 'exec_coordinator') and self.exec_coordinator:
            result = await self.exec_coordinator.execute_action(
                layer='low_quick',  # Quick action - low priority, won't interrupt mid
                label='elbow_room',
                action_fn=lambda: self._execute_elbow_room(),
                can_interrupt=[],
                auto_resume=False
            )
            
            if result.get('blocked'):
                # Higher priority task executing, skip silently
                return
            
            if result.get('cancelled'):
                logger.debug("Elbow room cancelled")
                return
    
    async def _execute_elbow_room(self):
        """Execute elbow room mode code"""
        try:
            await self.ipc_server.send_command({
                'type': 'execute_code',
                'data': {
                    'code': """
                        const player = world.getNearestEntityWhere(
                            bot,
                            entity => entity.type === 'player',
                            0.5
                        );
                        if (player) {
                            // Random wait to avoid identical movements
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
            
            # Wait for execution result (we sent no_response=True so do not expect one)
            await self._wait_for_execution_result(expect_response=False)
            
        except asyncio.CancelledError:
            logger.debug("Elbow room execution cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during elbow room: {e}")
    
    async def check_idle_staring(self):
        """
        Idle staring mode: Look at nearby entities (ported from modes.js)
        
        Animation to make the bot look more alive when idle.
        Uses bot.lookAt() which doesn't need execute() as it's non-blocking.
        """
        staring_enabled = self.modes_config.get('idle_staring', True)
        if not staring_enabled:
            return
        
        try:
            current_time = time.time()
            
            if current_time > self.next_stare_change:
                # Time to change behavior
                import random
                self.staring = random.random() < 0.3
                
                if not self.staring:
                    # Look in random direction (non-blocking, no mode_active needed)
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
                # Look at nearest entity (non-blocking, no mode_active needed)
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
            logger.error(f"Idle staring check error: {e}")
