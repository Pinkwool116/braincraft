"""
MindCraft Agent Brain - Main Entry Point

Entry point for the Agent Loop + Reflex brain architecture.
(Phase 1: cleaned of old three-layer references)
"""

import asyncio
import logging
import json
import sys
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import os
# Force working directory to the 'braincraft' project root, 
# so relative paths like "bots", "keys.json", and "profiles" work everywhere.
project_root = Path(__file__).resolve().parent.parent
os.chdir(project_root)

from brain.agent_brain.brain_coordinator import BrainCoordinator
from bridge.ipc_server import IPCServer
from utils.logger import setup_logger

async def load_config(profile_path: str = None):
    """
    Load configuration from profile

    Args:
        profile_path: Path to profile JSON file

    Returns:
        Configuration dictionary
    """
    if not profile_path:
        # Use config.json relative to this script
        profile_path = str(Path(__file__).resolve().parent / "config.json")

    logger = logging.getLogger(__name__)
    logger.info(f"Loading configuration from {profile_path}")

    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if 'keys_file' not in config:
            config['keys_file'] = 'keys.json'
            
        # 设置正确的 bots 文件夹基路径
        project_root = Path(__file__).resolve().parent.parent
        config['bots_dir'] = str(project_root / 'bots')
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {profile_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        sys.exit(1)

async def main():
    """Main entry point for the brain system"""

    # Setup logging
    logger = setup_logger(level=logging.INFO)
    logger.info("=" * 70)
    logger.info("  MindCraft Agent Brain System")
    logger.info("=" * 70)

    ipc_server = None
    coordinator = None

    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = await load_config()
        agent_name = config.get('agent_name', 'BrainyBot')
        logger.info(f"Agent: {agent_name}")

        # Validate new-style config sections
        if 'agent_loop' not in config:
            logger.warning("Config missing 'agent_loop' section — check config.json")
        else:
            loop_model = config['agent_loop'].get('model_name', '?')
            loop_api = config['agent_loop'].get('api', '?')
            logger.info(f"Agent Loop model: {loop_model} ({loop_api})")

        if 'execution' not in config:
            logger.warning("Config missing 'execution' section — check config.json")
        else:
            exec_model = config['execution'].get('model_name', '?')
            exec_api = config['execution'].get('api', '?')
            logger.info(f"Execution model: {exec_model} ({exec_api})")

        if 'memory' in config:
            logger.info(f"Memory: consolidate_interval={config['memory'].get('consolidate_interval', 5)}, "
                        f"crystallize={config['memory'].get('enable_crystallize', True)}")

        if 'embedding' in config:
            embed_model = config['embedding'].get('model', '?')
            logger.info(f"Embedding model: {embed_model}")

        # Initialize IPC server for communication with JavaScript
        ipc_port = config.get('ipc_port', 9000)
        logger.info(f"Initializing IPC server on port {ipc_port}...")
        ipc_server = IPCServer(port=ipc_port)
        await ipc_server.start()
        logger.info(f"IPC server started on ports {ipc_port} (REP) and {ipc_port+1} (PUB)")

        # Initialize and start the brain coordinator
        logger.info("Initializing brain coordinator...")
        coordinator = BrainCoordinator(ipc_server, config)

        # Start the coordinator (this will run until shutdown_requested is set)
        logger.info("=" * 70)
        logger.info("  Brain systems starting...")
        logger.info("=" * 70)
        await coordinator.start()

        # If we reach here, shutdown was requested
        logger.info("Brain systems stopped. Cleaning up...")

    except KeyboardInterrupt:
        logger.info("\n" + "=" * 70)
        logger.info("  Shutdown requested by user (Ctrl+C)")
        logger.info("=" * 70)

        if coordinator:
            coordinator.shutdown_requested = True
            logger.info("Cancelling all brain tasks...")
            await coordinator.cancel_all_tasks()
            logger.info("Saving brain state...")
            await coordinator.shutdown()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

    finally:
        if ipc_server:
            try:
                logger.info("Closing IPC server...")
                await ipc_server.stop()
            except Exception as e:
                logger.error(f"Error closing IPC server: {e}")

        logger.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())


