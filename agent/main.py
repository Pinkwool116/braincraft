"""
MindCraft Three-Layer Brain - Main Entry Point

This is the entry point for the three-layer asynchronous brain architecture:
- High-Level Brain: Strategic planning and experience summarization (every 5 minutes)
- Mid-Level Brain: Tactical execution and task management (every second)
- Low-Level Brain: Reflex system for immediate responses (every 100ms)

Author: AI Town Team
Date: 2025-10-28
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

from brain.three_layer_brain.brain_coordinator import BrainCoordinator
from communication.ipc_server import IPCServer
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
        profile_path = "profiles/three_layer_brain.json"
    
    logger = logging.getLogger(__name__)
    logger.info(f"Loading configuration from {profile_path}")
    
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)
        
        # Extract brain configuration from nested structure if present
        if 'three_layer_brain_llm' in raw_config:
            config = raw_config.copy()
            brain_config = raw_config['three_layer_brain_llm']
            config['high_level_brain'] = brain_config.get('high_level_brain', {})
            config['mid_level_brain'] = brain_config.get('mid_level_brain', {})
            config['low_level_brain'] = brain_config.get('low_level_brain', {})
        else:
            config = raw_config
        
        # Add keys file path
        if 'keys_file' not in config:
            config['keys_file'] = 'keys.json'
        
        logger.info("Configuration loaded successfully")
        return config
        
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {profile_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        raise

async def main():
    """Main entry point for the Three-Layer Brain system"""
    
    # Setup logging
    logger = setup_logger(level=logging.INFO)
    logger.info("=" * 70)
    logger.info("  MindCraft Three-Layer Brain System")
    logger.info("=" * 70)
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = await load_config()
        logger.info(f"Agent: {config.get('agent_name', 'BrainyBot')}")
        logger.info(f"High-level model: {config.get('high_level_brain', {}).get('model_name', 'unknown')}")
        logger.info(f"Mid-level model: {config.get('mid_level_brain', {}).get('model_name', 'unknown')}")
        
        # Initialize IPC server for communication with JavaScript
        ipc_port = config.get('ipc_port', 9000)
        logger.info(f"Initializing IPC server on port {ipc_port}...")
        ipc_server = IPCServer(port=ipc_port)
        await ipc_server.start()
        logger.info(f"IPC server started on ports {ipc_port} (REP) and {ipc_port+1} (PUB)")
        
        # Initialize and start the three-layer brain coordinator
        logger.info("Initializing brain coordinator...")
        coordinator = BrainCoordinator(ipc_server, config)
        
        # Start the coordinator (this will run indefinitely)
        logger.info("=" * 70)
        logger.info("  Brain systems starting...")
        logger.info("=" * 70)
        await coordinator.start()
        
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 70)
        logger.info("  Shutdown requested by user")
        logger.info("=" * 70)
        
        # Graceful shutdown
        try:
            # Notify JavaScript to disconnect bot
            await ipc_server.send_command({
                'type': 'shutdown',
                'data': {'reason': 'User requested shutdown'}
            })
            await asyncio.sleep(1)  # Give JS time to process
            
            # Shutdown coordinator (saves state)
            await coordinator.shutdown()
            
            # Close IPC server
            await ipc_server.stop()
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutdown complete")

if __name__ == "__main__":
    # Set environment variables if needed
    # os.environ['QWEN_API_KEY'] = 'your-key-here'
    
    asyncio.run(main())
