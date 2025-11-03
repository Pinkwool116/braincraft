"""
Prompt Loader Utility

Centralized prompt file loading with strict error handling.
"""

import os
import logging
import sys

logger = logging.getLogger(__name__)


def load_system_prompt(config: dict, brain_type: str) -> str:
    """
    Load system prompt from file (STRICT mode - exits on failure)
    
    Args:
        config: Configuration dictionary
        brain_type: Brain type ('high_level_brain' or 'mid_level_brain')
    
    Returns:
        System prompt string
    
    Raises:
        SystemExit: If prompt file not found or loading fails
    """
    # Get prompt file path from config
    brain_config = config.get(brain_type, {})
    prompt_file = brain_config.get('system_prompt_file')
    
    if not prompt_file:
        logger.error(f"❌ CRITICAL: No system_prompt_file specified in config for {brain_type}")
        logger.error(f"   Please add 'system_prompt_file' to '{brain_type}' in your config file")
        sys.exit(1)
    
    # Handle relative paths
    if not os.path.isabs(prompt_file):
        # Relative to project root (3 levels up from utils/)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        prompt_file = os.path.join(project_root, prompt_file)
    
    # Check if file exists
    if not os.path.exists(prompt_file):
        logger.error(f"❌ CRITICAL: System prompt file not found: {prompt_file}")
        logger.error(f"   Expected path: {os.path.abspath(prompt_file)}")
        logger.error(f"   Brain type: {brain_type}")
        sys.exit(1)
    
    # Load file
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt = f.read()
        
        if not prompt.strip():
            logger.error(f"❌ CRITICAL: System prompt file is empty: {prompt_file}")
            sys.exit(1)
        
        logger.info(f"✓ Loaded system prompt for {brain_type} from {os.path.basename(prompt_file)}")
        return prompt
    
    except UnicodeDecodeError as e:
        logger.error(f"❌ CRITICAL: Failed to decode prompt file (encoding issue): {prompt_file}")
        logger.error(f"   Error: {e}")
        logger.error(f"   Please ensure the file is UTF-8 encoded")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to load system prompt from {prompt_file}")
        logger.error(f"   Error: {e}")
        sys.exit(1)
