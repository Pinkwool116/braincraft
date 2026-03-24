"""
Brain Coordinator

Coordinates the Agent Loop + Reflex architecture.
Initializes all layers, tools, and manages lifecycle.
"""

import sys
import asyncio
import logging
from typing import Dict, Any
from .execution_coordinator import ExecutionCoordinator
from .agent_loop_layer import AgentLoopLayer
from .execution_layer import ExecutionLayer
from .reflex_layer import ReflexLayer
from ..tools import ToolRegistry
from ..task_manager import TaskFileManager
from llm.llm_wrapper import create_llm_model

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

            # Execution state
            'is_executing': False,  # Whether execution layer is currently running code

            # Reflex level
            'last_reflex': None,
            'in_combat': False,

            # Interrupt mechanism
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
    Coordinates the Agent Loop + Reflex brain system.

    Initializes and manages:
    - AgentLoopLayer: Main decision loop (LLM + tool calling)
    - ExecutionLayer: Code generation and execution
    - ReflexLayer: Survival reflexes and automatic behaviors
    - ToolRegistry: Available tools for the Agent Loop
    - TaskFileManager: File-based task tracking
    """

    def __init__(self, ipc_server, config):
        self.config = config
        self.ipc_server = ipc_server

        # Shared state across all layers
        self.shared_state = SharedState()

        # Shutdown flag
        self.shutdown_requested = False

        # Execution coordinator (priority-based interrupt mechanism)
        self.exec_coordinator = ExecutionCoordinator(
            shared_state=self.shared_state,
            high_brain=None,
            ipc_server=self.ipc_server
        )

        # TODO (Phase 3): Initialize LLM models from config
        # agent_loop_llm = self._create_llm('agent_loop')
        # coding_llm = self._create_llm('coding')

        # TODO (Phase 3): Initialize layers and tools
        # self.task_manager = TaskFileManager(config.get('agent_name', 'BrainyBot'))
        # self.tool_registry = ToolRegistry()
        # self.execution_layer = ExecutionLayer(...)
        # self.reflex_layer = ReflexLayer(...)
        # self._register_tools()
        # self.agent_loop = AgentLoopLayer(...)

        logger.info("Brain coordinator initialized")

        # Register IPC message handlers
        self._register_ipc_handlers()

    def _register_ipc_handlers(self):
        """Register handlers for messages from JavaScript"""
        logger.info("Registering IPC message handlers...")

        # Handle state updates from JavaScript
        async def handle_state_update(data):
            """Handle game state update from JavaScript"""
            logger.debug("Received state update from game")

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
            await self.shared_state.update('world_day', data.get('world_day', 0))
            await self.shared_state.update('world_time', data.get('world_time', 0))

            # Agent age (cumulative playtime across all worlds)
            await self.shared_state.update('agent_age_days', data.get('agent_age_days', 0))
            await self.shared_state.update('agent_age_ticks', data.get('agent_age_ticks', 0))
            await self.shared_state.update('agent_age_hours', data.get('agent_age_hours', 0))

            # Composite game_state for memory system
            await self.shared_state.update('game_state', {
                'position': data.get('position', {}),
                'health': data.get('health', 20),
                'food': data.get('food', 20),
                'inventory': data.get('inventory', {}),
                'biome': data.get('biome', 'unknown'),
                'dimension': data.get('dimension', 'unknown'),
                'gamemode': data.get('gamemode', 'survival'),
                'time_of_day': data.get('time_of_day', 0),
                'time_label': data.get('time_label', 'Night'),
                'weather': data.get('weather', 'Clear'),
                'nearby_entities': data.get('nearby_entities', []),
                'nearby_blocks': data.get('nearby_blocks', []),
                'surrounding_blocks': data.get('surrounding_blocks', {}),
                'equipment': data.get('equipment', {}),
            })

            return {'status': 'ok'}

        # Handle chat messages from JavaScript
        async def handle_chat_message(data):
            """Handle chat message — enqueue for Agent Loop to process"""
            player = data.get('player', 'Unknown')
            message = data.get('message', '')
            logger.info(f"Chat from {player}: {message}")

            # TODO (Phase 3): Enqueue message for Agent Loop to process
            # For now, just log it

            return {'status': 'ok', 'response': 'Message received'}

        # Handle execution results from JavaScript
        async def handle_execution_result(data):
            """Handle code execution result from JavaScript"""
            success = data.get('success', False)
            error = data.get('error', '')

            if success:
                logger.debug("Code execution successful")
            else:
                logger.error(f"Code execution failed: {error}")

            await self.shared_state.update('last_execution_result', data)
            return {'status': 'ok'}

        # Handle bot spawn event
        async def handle_bot_ready(data):
            """Handle bot spawn/ready event from JavaScript"""
            logger.info("Bot has spawned in game - brain system is now active")

            await self.shared_state.update('bot_ready', True)
            await self.shared_state.update('bot_status', 'online')

            # Record birthday
            birthday = data.get('birthday')
            birthday_ticks = data.get('birthday_ticks')
            if birthday is not None:
                await self.shared_state.update('birthday', birthday)
                await self.shared_state.update('birthday_ticks', birthday_ticks)
                logger.info(f"Agent birthday: World day {birthday} (tick {birthday_ticks})")

            current_day = data.get('current_day', data.get('world_day', 0))
            current_ticks = data.get('current_ticks', data.get('world_ticks', 0))
            age_days = current_day - birthday if birthday is not None else 0

            logger.info(f"Current world: Day {current_day}, Tick {current_ticks}")
            logger.info(f"Agent age: {age_days} days old")

            return {'status': 'ok'}

        # Register core handlers
        self.ipc_server.register_handler('state_update', handle_state_update)
        self.ipc_server.register_handler('chat_message', handle_chat_message)
        self.ipc_server.register_handler('execution_result', handle_execution_result)
        self.ipc_server.register_handler('bot_ready', handle_bot_ready)

        # Register low-level reflex handlers
        async def handle_combat_engaged(data):
            # TODO (Phase 3): Forward to ReflexLayer
            return {'status': 'ok'}

        async def handle_low_health(data):
            # TODO (Phase 3): Forward to ReflexLayer
            return {'status': 'ok'}

        async def handle_damage_taken(data):
            # TODO (Phase 3): Forward to ReflexLayer
            return {'status': 'ok'}

        async def handle_death(data):
            logger.warning("Agent died!")
            await self.shared_state.update('health', 0)
            await self.shared_state.update('bot_status', 'dead')
            await self.shared_state.update('bot_ready', False)
            return {'status': 'ok'}

        async def handle_bot_disconnected(data):
            reason = data.get('reason', 'Unknown')
            logger.warning(f"Bot disconnected: {reason}")
            await self.shared_state.update('bot_ready', False)
            await self.shared_state.update('bot_status', 'reconnecting')
            await self.shared_state.update('is_executing', False)
            return {'status': 'ok'}

        async def handle_shutdown(data):
            reason = data.get('reason', 'Unknown')
            logger.warning(f"Shutdown requested: {reason}")
            self.shutdown_requested = True
            asyncio.create_task(self.cancel_all_tasks())
            return {'status': 'ok', 'message': 'Shutdown initiated'}

        self.ipc_server.register_handler('combat_engaged', handle_combat_engaged)
        self.ipc_server.register_handler('low_health', handle_low_health)
        self.ipc_server.register_handler('damage_taken', handle_damage_taken)
        self.ipc_server.register_handler('death', handle_death)
        self.ipc_server.register_handler('bot_disconnected', handle_bot_disconnected)
        self.ipc_server.register_handler('shutdown', handle_shutdown)

        logger.info("IPC message handlers registered")

    def _inject_api_keys(self, llm_config: Dict[str, Any]):
        """Inject API keys from keys.json into LLM config"""
        import os
        import json

        keys_file = self.config.get('keys_file', 'keys.json')
        if os.path.exists(keys_file):
            try:
                with open(keys_file, 'r') as f:
                    keys = json.load(f)

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
        """Start the brain system — launches Agent Loop and Reflex Layer"""
        logger.info("Starting brain system...")

        self.brain_tasks = []

        # TODO (Phase 3): Start actual loops
        # self.brain_tasks.append(asyncio.create_task(self._run_agent_loop()))
        # self.brain_tasks.append(asyncio.create_task(self._run_reflex()))

        # Keep alive until shutdown
        try:
            while not self.shutdown_requested:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Brain coordinator cancelled")

    async def _run_agent_loop(self):
        """Run the Agent Loop Layer (main decision loop)"""
        # TODO (Phase 3): Wait for bot_ready, then start agent_loop.run_loop()
        raise NotImplementedError("Phase 3: implement _run_agent_loop")

    async def _run_reflex(self):
        """Run the Reflex Layer (survival reflexes)"""
        # TODO (Phase 3): Wait for bot_ready, then start reflex_layer.run()
        raise NotImplementedError("Phase 3: implement _run_reflex")

    async def cancel_all_tasks(self):
        """Cancel all running brain tasks"""
        logger.info("Cancelling all brain tasks...")
        for task in getattr(self, 'brain_tasks', []):
            if not task.done():
                task.cancel()

        if hasattr(self, 'brain_tasks') and self.brain_tasks:
            await asyncio.gather(*self.brain_tasks, return_exceptions=True)
        logger.info("All brain tasks cancelled")

    async def shutdown(self):
        """Graceful shutdown of all brain systems"""
        logger.info("Shutting down brain coordinator...")
        # TODO (Phase 3): Save any necessary state
        logger.info("Brain coordinator shutdown complete")
