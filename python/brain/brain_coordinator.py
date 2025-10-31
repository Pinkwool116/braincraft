"""
Brain Coordinator

Coordinates the three-layer brain system with asynchronous execution.
"""

import asyncio
import logging
from typing import Dict, Any
from .high_level_brain import HighLevelBrain
from .mid_level_brain import MidLevelBrain
from .low_level_brain import LowLevelBrain
from .execution_coordinator import ExecutionCoordinator
from models.llm_wrapper import create_llm_model

logger = logging.getLogger(__name__)

class SharedState:
    """Shared state between all brain layers"""
    
    def __init__(self):
        self._state = {
            # Game state
            'position': {'x': 0, 'y': 0, 'z': 0},
            'health': 20,
            'food': 20,
            'inventory': {},
            'biome': 'unknown',
            'time_of_day': 0,
            'agent_name': 'Agent',
            
            # World time (current world only, may reset)
            'world_day': 0,         # Days since current world creation
            'world_time': 0,        # Total ticks since current world creation
            
            # Agent age (cumulative across all worlds)
            'agent_age_days': 0,    # Cumulative game days played (total_ticks / 24000)
            'agent_age_ticks': 0,   # Cumulative game ticks played (persists across worlds)
            'agent_age_hours': 0,   # Hours within current day (for display)
            
            # Strategic level
            'strategic_goal': None,
            
            # Tactical level
            'pending_chat': None,
            'current_task': None,
            'is_executing': False,  # Whether mid-level brain is currently executing code
            
            # Reflex level
            'last_reflex': None,
            'in_combat': False,
            
            # Interrupt mechanism (like original project)
            'interrupt_code': False,  # Flag for interrupting JavaScript code execution
        }
        self._lock = asyncio.Lock()
    
    async def update(self, key: str, value: Any):
        """Thread-safe state update"""
        async with self._lock:
            self._state[key] = value
    
    async def get(self, key: str) -> Any:
        """Thread-safe state retrieval"""
        async with self._lock:
            return self._state.get(key)
    
    async def get_all(self) -> Dict[str, Any]:
        """Get all state (for prompts)"""
        async with self._lock:
            return self._state.copy()

class BrainCoordinator:
    """
    Coordinates the three-layer brain system:
    - High-level brain runs asynchronously every 5 minutes
    - Mid-level brain runs asynchronously every second
    - Low-level brain handles events in real-time
    """
    
    def __init__(self, ipc_server, config):
        """
        Initialize brain coordinator
        
        Args:
            ipc_server: IPC server for communication with JavaScript
            config: Configuration object
        """
        self.config = config
        self.ipc_server = ipc_server
        
        # Shared state across all layers
        self.shared_state = SharedState()
        
        # Create LLM models
        logger.info("Creating LLM models...")
        high_config = config.get('high_level_brain', {})
        mid_config = config.get('mid_level_brain', {})
        
        # Add API keys from keys.json or environment
        self._inject_api_keys(high_config)
        self._inject_api_keys(mid_config)
        
        high_llm = create_llm_model(high_config)
        mid_llm = create_llm_model(mid_config)
        
        # Event-driven mechanism for high-level brain
        self.high_brain_wake_event = asyncio.Event()
        
        # Initialize three brain layers (pass wake_event to high_brain)
        self.high_brain = HighLevelBrain(self.shared_state, config, high_llm, wake_event=self.high_brain_wake_event)
        self.mid_brain = MidLevelBrain(self.shared_state, ipc_server, config, mid_llm, self.high_brain)
        self.low_brain = LowLevelBrain(self.shared_state, ipc_server, config)
        
        # Create execution coordinator
        self.exec_coordinator = ExecutionCoordinator(
            shared_state=self.shared_state,
            high_brain=self.high_brain,
            ipc_server=self.ipc_server  # Pass IPC server for JavaScript synchronization
        )
        
        # Pass coordinator references
        self.mid_brain.coordinator = self
        self.high_brain.exec_coordinator = self.exec_coordinator
        self.mid_brain.exec_coordinator = self.exec_coordinator
        self.low_brain.exec_coordinator = self.exec_coordinator
        
        logger.info("Brain coordinator initialized with ExecutionCoordinator")
        
        # Register IPC message handlers
        self._register_ipc_handlers()
    
    def _register_ipc_handlers(self):
        """Register handlers for messages from JavaScript"""
        logger.info("Registering IPC message handlers...")
        
        # Handle state updates from JavaScript
        async def handle_state_update(data):
            """Handle game state update from JavaScript"""
            logger.debug("Received state update from game")
            
            # Update shared state
            await self.shared_state.update('position', data.get('position', {}))
            await self.shared_state.update('health', data.get('health', 20))
            await self.shared_state.update('food', data.get('food', 20))
            await self.shared_state.update('inventory', data.get('inventory', {}))
            await self.shared_state.update('biome', data.get('biome', 'unknown'))
            await self.shared_state.update('time_of_day', data.get('time_of_day', 0))
            await self.shared_state.update('nearby_entities', data.get('nearby_entities', []))
            await self.shared_state.update('nearby_blocks', data.get('nearby_blocks', []))
            
            # Update time tracking
            # World time (current world only, may reset)
            await self.shared_state.update('world_day', data.get('world_day', 0))
            await self.shared_state.update('world_time', data.get('world_time', 0))
            
            # Agent age (cumulative playtime across all worlds)
            await self.shared_state.update('agent_age_days', data.get('agent_age_days', 0))
            await self.shared_state.update('agent_age_ticks', data.get('agent_age_ticks', 0))
            await self.shared_state.update('agent_age_hours', data.get('agent_age_hours', 0))
            
            return {'status': 'ok'}
        
        # Handle chat messages from JavaScript
        async def handle_chat_message(data):
            """Handle chat message from game"""
            player = data.get('player', 'Unknown')
            message = data.get('message', '')
            
            logger.info(f"Chat from {player}: {message}")
            
            # Use ExecutionCoordinator to handle chat - this will automatically:
            # 1. Interrupt ongoing code execution by setting interrupt_code flag
            # 2. Wait for code to stop (via polling in ExecutionCoordinator)
            # 3. Execute chat handler
            # 4. Resume interrupted task (if any)
            # NOTE: Use 'chat' layer (priority 3) to interrupt mid-level tasks (priority 2)
            asyncio.create_task(
                self.exec_coordinator.execute_action(
                    layer='chat',
                    label=f'chat:{player}',
                    action_fn=lambda: self.mid_brain._handle_pending_chat({
                        'player': player, 
                        'message': message
                    }),
                    can_interrupt=['low_reflex', 'low_mode', 'unstuck'],
                    auto_resume=True
                )
            )
            
            return {'status': 'ok', 'response': 'Message received'}
        
        # Handle execution results from JavaScript
        async def handle_execution_result(data):
            """Handle code execution result from JavaScript"""
            success = data.get('success', False)
            error = data.get('error', '')
            
            if success:
                logger.debug(f"Code execution successful")
            else:
                logger.error(f"Code execution failed: {error}")
            
            # Update mid-level brain about result
            await self.shared_state.update('last_execution_result', data)
            
            return {'status': 'ok'}
        
        # Handle bot spawn event (bot entered game)
        async def handle_bot_ready(data):
            """Handle bot spawn/ready event from JavaScript"""
            logger.info("Bot has spawned in game - brain system is now active")
            
            # Update bot ready state
            await self.shared_state.update('bot_ready', True)
            await self.shared_state.update('agent_name', data.get('username', 'Agent'))
            
            # Record birthday (world day when agent first spawned)
            birthday = data.get('birthday')
            birthday_ticks = data.get('birthday_ticks')
            if birthday is not None:
                await self.shared_state.update('birthday', birthday)
                await self.shared_state.update('birthday_ticks', birthday_ticks)
                logger.info(f"Agent birthday: World day {birthday} (tick {birthday_ticks})")
            
            # Log current world time and agent age
            current_day = data.get('current_day', 0)
            current_ticks = data.get('current_ticks', 0)
            age_days = current_day - birthday if birthday is not None else 0
            
            logger.info(f"Current world: Day {current_day}, Tick {current_ticks}")
            logger.info(f"Agent age: {age_days} days old")
            
            # Trigger immediate high-level brain wake to generate initial task plan
            logger.info("🚀 Triggering initial high-level brain wake...")
            await self.wake_high_brain()
            
            return {'status': 'ok'}
        
        # Register all handlers
        self.ipc_server.register_handler('state_update', handle_state_update)
        self.ipc_server.register_handler('chat_message', handle_chat_message)
        self.ipc_server.register_handler('execution_result', handle_execution_result)
        self.ipc_server.register_handler('bot_ready', handle_bot_ready)
        
        # Register low-level reflex handlers (combat, low health, etc.)
        async def handle_combat_engaged(data):
            """Forward combat event to low-level brain"""
            await self.low_brain.handle_event('combat_engaged', data)
            return {'status': 'ok'}
        
        async def handle_low_health(data):
            """Forward low health event to low-level brain"""
            await self.low_brain.handle_event('low_health', data)
            return {'status': 'ok'}
        
        async def handle_damage_taken(data):
            """Forward damage event to low-level brain"""
            await self.low_brain.handle_event('damage_taken', data)
            return {'status': 'ok'}
        
        async def handle_death(data):
            """Handle death event (informational)"""
            logger.warning("⚠️  Agent died!")
            await self.shared_state.update('health', 0)
            return {'status': 'ok'}
        
        async def handle_bot_disconnected(data):
            """Handle bot disconnection"""
            reason = data.get('reason', 'Unknown')
            logger.warning(f"🔌 Bot disconnected: {reason}")
            await self.shared_state.update('bot_ready', False)
            # Clear execution state to stop tasks
            await self.shared_state.update('is_executing', False)
            return {'status': 'ok'}
        
        self.ipc_server.register_handler('combat_engaged', handle_combat_engaged)
        self.ipc_server.register_handler('low_health', handle_low_health)
        self.ipc_server.register_handler('damage_taken', handle_damage_taken)
        self.ipc_server.register_handler('death', handle_death)
        self.ipc_server.register_handler('bot_disconnected', handle_bot_disconnected)
        
        logger.info("IPC message handlers registered")
    
    def _inject_api_keys(self, llm_config: Dict[str, Any]):
        """
        Inject API keys from keys.json into LLM config
        
        Args:
            llm_config: LLM configuration dict
        """
        import os
        import json
        
        # Try to load keys.json
        keys_file = self.config.get('keys_file', 'keys.json')
        if os.path.exists(keys_file):
            try:
                with open(keys_file, 'r') as f:
                    keys = json.load(f)
                
                # Map API types to key names
                api_type = llm_config.get('api', 'qwen')
                key_map = {
                    'qwen': 'QWEN_API_KEY',
                    'openai': 'OPENAI_API_KEY',
                    'anthropic': 'ANTHROPIC_API_KEY',
                    'claude': 'ANTHROPIC_API_KEY',
                    'deepseek': 'DEEPSEEK_API_KEY',
                }
                
                key_name = key_map.get(api_type)
                if key_name and key_name in keys:
                    llm_config['api_key'] = keys[key_name]
                    logger.info(f"Loaded API key for {api_type} from {keys_file}")
                    
            except Exception as e:
                logger.warning(f"Failed to load keys from {keys_file}: {e}")
    
    async def start(self):
        """
        Start all three brain layers asynchronously
        
        Each layer runs in its own event loop without blocking others.
        """
        logger.info("Starting three-layer brain system...")
        
        # Start all three layers concurrently
        await asyncio.gather(
            self._run_high_brain(),
            self._run_mid_brain(),
            self._run_low_brain(),
            return_exceptions=True
        )
    
    async def _run_high_brain(self):
        """
        Run high-level brain loop
        
        Dual mechanism:
        1. Event-driven: Mid-level requests wake up high-level instantly
        2. Periodic check: Every 15 minutes, check if idle for contemplation
        
        - Mid-level modification requests trigger immediate wake (event-driven)
        - Contemplation only happens during periodic wake if not busy
        """
        contemplation_interval = self.config.get('high_level_brain', {}).get('interval_seconds', 600)  # 10 minutes
        logger.info(f"High-level brain started:")
        logger.info(f"  - Event-driven: Instant response to mid-level requests")
        logger.info(f"  - Periodic contemplation check: every {contemplation_interval}s ({contemplation_interval/60:.0f} minutes)")
        
        while True:
            try:
                # Wait for wake event OR timeout (15 minutes)
                woken_by_event = False
                try:
                    await asyncio.wait_for(
                        self.high_brain_wake_event.wait(),
                        timeout=contemplation_interval
                    )
                    woken_by_event = True
                    logger.info("⚡ High-level woken by event (mid-level request)")
                except asyncio.TimeoutError:
                    logger.info("⏰ High-level periodic wake (contemplation check)")
                
                # Clear the event flag
                self.high_brain_wake_event.clear()
                
                # Execute thinking cycle (knows if it's event-driven or periodic)
                await self.high_brain.think(woken_by_event=woken_by_event)
                
            except Exception as e:
                logger.error(f"High-level brain error: {e}", exc_info=True)
                await asyncio.sleep(1)  # Brief pause before retry
    
    async def _run_mid_brain(self):
        """
        Run mid-level brain loop
        
        Executes every second for tactical task management.
        """
        interval = self.config.get('mid_level_brain', {}).get('interval_seconds', 1)
        logger.info(f"Mid-level brain started (interval: {interval}s)")
        
        while True:
            try:
                await self.mid_brain.process()
            except Exception as e:
                logger.error(f"Mid-level brain error: {e}", exc_info=True)
            
            # Wait before next iteration
            await asyncio.sleep(interval)
    
    async def _run_low_brain(self):
        """
        Run low-level brain loop
        
        Handles real-time events and reflexes.
        """
        interval = self.config.get('low_level_brain', {}).get('interval_seconds', 0.1)
        logger.info(f"Low-level brain started (interval: {interval}s)")
        
        while True:
            try:
                await self.low_brain.handle_events()
            except Exception as e:
                logger.error(f"Low-level brain error: {e}", exc_info=True)
            
            # Very short interval for real-time responses
            await asyncio.sleep(interval)
    
    async def wake_high_brain(self):
        """
        Wake up high-level brain immediately
        
        Called by mid-level brain when it needs immediate attention
        (e.g., modification request, critical failure)
        """
        logger.info("⚡ Mid-level requests immediate high-level attention")
        self.high_brain_wake_event.set()
    
    async def shutdown(self):
        """Graceful shutdown of all brain systems"""
        logger.info("Shutting down brain coordinator...")
        
        # Save current state
        try:
            # Save high-level brain state (mind state)
            logger.info("Saving high-level brain state...")
            await self.high_brain.save_state()
            
            # Save mid-level brain state (if needed)
            logger.info("Saving mid-level brain state...")
            # Mid-level brain auto-saves to memory_manager
            
            # No need to save low-level brain (reflexes are stateless)
            
            logger.info("All brain states saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving state during shutdown: {e}")
        
        logger.info("Brain coordinator shutdown complete")
