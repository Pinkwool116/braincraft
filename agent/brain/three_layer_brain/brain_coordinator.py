"""
Brain Coordinator

Coordinates the three-layer brain system with asynchronous execution.
"""

import sys
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
            'agent_name': 'BrainyBot',
            'dimension': 'unknown',
            'gamemode': 'survival',
            'weather': 'Clear',
            'time_label': 'Day',
            'nearby_entities': [],
            'nearby_blocks': [],
            'surrounding_blocks': {
                'below': 'unknown',
                'legs': 'unknown',
                'head': 'unknown',
                'firstAbove': 'none'
            },
            'equipment': {
                'helmet': None,
                'chestplate': None,
                'leggings': None,
                'boots': None,
                'mainHand': None
            },
            
            # World time (current world only, may reset)
            'world_day': 0,         # Days since current world creation
            'world_time': 0,        # Total ticks since current world creation
            
            # Agent age (cumulative across all worlds)
            'agent_age_days': 0,    # Cumulative game days played (total_ticks / 24000)
            'agent_age_ticks': 0,   # Cumulative game ticks played (persists across worlds)
            'agent_age_hours': 0,   # Hours within current day (for display)
            
            # Strategic level
            'strategic_goal': None,
            'task_stack': [],
            'task_stack_summary': '',
            'active_task': None,
            'modification_request': None,
            'modification_response': None,
            
            # Tactical level
            'pending_chat': None,
            'current_task': None,
            'is_executing': False,  # Whether mid-level brain is currently executing code
            
            # Reflex level
            'last_reflex': None,
            'in_combat': False,
            
            # Interrupt mechanism (like original project)
            'interrupt_code': False,  # Flag for interrupting JavaScript code execution

            # Bot connection/status
            'bot_ready': False,
            'bot_status': 'connecting',  # connecting | online | dead | reconnecting
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
        
        # Initialize three brain layers
        self.high_brain = HighLevelBrain(self.shared_state, config, high_llm)
        self.mid_brain = MidLevelBrain(self.shared_state, ipc_server, config, mid_llm, self.high_brain)
        self.low_brain = LowLevelBrain(self.shared_state, ipc_server, config)
        
        # Initialization flag for high-level brain
        self.high_brain_initialized = False
        
        # Event for waking high-level brain immediately
        self.high_brain_wake_event = asyncio.Event()
        
        # Shutdown flag
        self.shutdown_requested = False
        
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
            await self.shared_state.update('dimension', data.get('dimension', 'unknown'))
            await self.shared_state.update('gamemode', data.get('gamemode', 'survival'))
            await self.shared_state.update('time_of_day', data.get('time_of_day', 0))
            await self.shared_state.update('time_label', data.get('time_label', 'Night'))
            await self.shared_state.update('weather', data.get('weather', 'Clear'))
            await self.shared_state.update('nearby_entities', data.get('nearby_entities', []))
            await self.shared_state.update('nearby_blocks', data.get('nearby_blocks', []))
            await self.shared_state.update('surrounding_blocks', data.get('surrounding_blocks', {}))
            await self.shared_state.update('equipment', data.get('equipment', {}))
            
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
            await self.shared_state.update('bot_status', 'online')
            
            # Record birthday (world day when agent first spawned)
            birthday = data.get('birthday')
            birthday_ticks = data.get('birthday_ticks')
            if birthday is not None:
                await self.shared_state.update('birthday', birthday)
                await self.shared_state.update('birthday_ticks', birthday_ticks)
                logger.info(f"Agent birthday: World day {birthday} (tick {birthday_ticks})")
            
            # Log current world time and agent age
            # Backward/forward compatible field names
            current_day = data.get('current_day', data.get('world_day', 0))
            current_ticks = data.get('current_ticks', data.get('world_ticks', 0))
            age_days = current_day - birthday if birthday is not None else 0
            
            logger.info(f"Current world: Day {current_day}, Tick {current_ticks}")
            logger.info(f"Agent age: {age_days} days old")
            
            # Mark high-level brain as ready for initialization
            logger.info("🚀 Bot ready - High-level brain can now initialize")
            self.high_brain_initialized = True
            
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
            await self.shared_state.update('bot_status', 'dead')
            await self.shared_state.update('bot_ready', False)
            return {'status': 'ok'}
        
        async def handle_bot_disconnected(data):
            """Handle bot disconnection"""
            reason = data.get('reason', 'Unknown')
            logger.warning(f"🔌 Bot disconnected: {reason}")
            await self.shared_state.update('bot_ready', False)
            await self.shared_state.update('bot_status', 'reconnecting')
            # Clear execution state to stop tasks
            await self.shared_state.update('is_executing', False)
            return {'status': 'ok'}
        
        async def handle_shutdown(data):
            """Handle shutdown request from JavaScript bridge"""
            reason = data.get('reason', 'Unknown')
            logger.warning(f"🛑 Shutdown requested: {reason}")
            
            # Set shutdown flag to stop all brain loops
            self.shutdown_requested = True
            
            # Cancel all brain tasks immediately
            asyncio.create_task(self.cancel_all_tasks())
            
            # Return response immediately so JS knows we received the message
            return {'status': 'ok', 'message': 'Shutdown initiated'}
        
        self.ipc_server.register_handler('combat_engaged', handle_combat_engaged)
        self.ipc_server.register_handler('low_health', handle_low_health)
        self.ipc_server.register_handler('damage_taken', handle_damage_taken)
        self.ipc_server.register_handler('death', handle_death)
        self.ipc_server.register_handler('bot_disconnected', handle_bot_disconnected)
        self.ipc_server.register_handler('shutdown', handle_shutdown)
        
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
                sys.exit(1)
    
    async def start(self):
        """
        Start all three brain layers asynchronously
        
        Each layer runs in its own event loop without blocking others.
        """
        logger.info("Starting three-layer brain system...")
        
        # Create tasks for all three brain layers
        self.high_task = asyncio.create_task(self._run_high_brain())
        self.mid_task = asyncio.create_task(self._run_mid_brain())
        self.low_task = asyncio.create_task(self._run_low_brain())
        
        # Store tasks for cancellation
        self.brain_tasks = [self.high_task, self.mid_task, self.low_task]
        
        # Wait for all tasks to complete (or be cancelled)
        try:
            await asyncio.gather(
                self.high_task,
                self.mid_task,
                self.low_task,
                return_exceptions=True
            )
        except asyncio.CancelledError:
            logger.info("Brain coordinator tasks cancelled")
    
    async def cancel_all_tasks(self):
        """Cancel all running brain tasks"""
        logger.info("Cancelling all brain tasks...")
        for task in self.brain_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to be cancelled
        await asyncio.gather(*self.brain_tasks, return_exceptions=True)
        logger.info("All brain tasks cancelled")
    
    async def _run_high_brain(self):
        """
        Run high-level brain loop
        
        Process:
        - Initial run: Generate first task plan when bot is ready
        - Periodic runs: Every 10 minutes, generate new strategic plans
        """
        contemplation_interval = self.config.get('high_level_brain', {}).get('interval_seconds', 600)  # 10 minutes
        logger.info(f"High-level brain started (periodic interval: {contemplation_interval}s)")
        
        first_run = True
        
        try:
            while not self.shutdown_requested:
                try:
                    # First run: wait for bot to be ready
                    if first_run:
                        logger.info("⏰ High-level brain waiting for bot to be ready...")
                        while not self.high_brain_initialized and not self.shutdown_requested:
                            await asyncio.sleep(0.1)  # Check every 100ms
                        if self.shutdown_requested:
                            break
                        first_run = False
                        logger.info("✅ Bot ready, executing initial high-level brain cycle...")
                        await self.high_brain.think(woken_by_event=False)
                        continue
                    
                    # Wait for either periodic interval OR immediate wake event
                    try:
                        await asyncio.wait_for(
                            self.high_brain_wake_event.wait(),
                            timeout=contemplation_interval
                        )
                        # Event was set - immediate wake
                        self.high_brain_wake_event.clear()
                        logger.info("⚡ High-level brain woken by event")
                        await self.high_brain.think(woken_by_event=True)
                    except asyncio.TimeoutError:
                        # Timeout reached - periodic wake
                        logger.info("⏰ High-level periodic wake")
                        await self.high_brain.think(woken_by_event=False)
                    
                except asyncio.CancelledError:
                    logger.info("High-level brain cancelled")
                    raise
                except Exception as e:
                    logger.error(f"High-level brain error: {e}", exc_info=True)
                    await asyncio.sleep(1)  # Brief pause before retry
        except asyncio.CancelledError:
            logger.info("High-level brain task cancelled during shutdown")
        
        logger.info("High-level brain stopped")
    
    async def _run_mid_brain(self):
        """
        Run mid-level brain loop
        
        Executes every second for tactical task management.
        """
        interval = self.config.get('mid_level_brain', {}).get('interval_seconds', 1)
        logger.info(f"Mid-level brain started (interval: {interval}s)")
        
        while not self.shutdown_requested:
            try:
                await self.mid_brain.process()
            except Exception as e:
                logger.error(f"Mid-level brain error: {e}", exc_info=True)
            
            # Wait before next iteration
            await asyncio.sleep(interval)
        
        logger.info("Mid-level brain stopped")
    
    async def _run_low_brain(self):
        """
        Run low-level brain loop
        
        Handles real-time events and reflexes.
        """
        interval = self.config.get('low_level_brain', {}).get('interval_seconds', 0.1)
        logger.info(f"Low-level brain started (interval: {interval}s)")
        
        while not self.shutdown_requested:
            try:
                await self.low_brain.handle_events()
            except Exception as e:
                logger.error(f"Low-level brain error: {e}", exc_info=True)
            
            # Very short interval for real-time responses
            await asyncio.sleep(interval)
        
        logger.info("Low-level brain stopped")
    
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
