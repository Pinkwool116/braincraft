"""
Prompt Logger - Save all prompts sent to LLM for debugging

Saves prompts to bots/{agent_name}/prompts/ directory with timestamps.
Controlled by 'enable_prompt_logging' config option.
"""

import os
import json
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PromptLogger:
    """Log all LLM prompts to files for debugging"""
    
    def __init__(self, base_dir: str, agent_name: str, enabled: bool = True):
        """
        Initialize prompt logger
        
        Args:
            base_dir: Base directory for bot data (e.g., 'bots')
            agent_name: Agent name (e.g., 'BrainyBot')
            enabled: Whether logging is enabled (controlled by config)
        """
        self.agent_name = agent_name
        self.enabled = enabled
        self.prompts_dir = os.path.join(base_dir, agent_name, "prompts")
        
        if self.enabled:
            # Create prompts directory if it doesn't exist
            os.makedirs(self.prompts_dir, exist_ok=True)
            logger.info(f"Prompt logging ENABLED - saving to: {self.prompts_dir}")
        
        # Counter for naming files (per prompt type for better organization)
        self.prompt_counters = {}
        
    def log_prompt(self, 
                   prompt: str, 
                   response: Optional[str] = None,
                   brain_layer: str = "unknown",
                   prompt_type: str = "unknown",
                   metadata: Optional[dict] = None) -> Optional[str]:
        """
        Log a prompt (and optionally response) to a file
        
        Args:
            prompt: The prompt text sent to LLM
            response: The LLM response (optional, can be added later)
            brain_layer: Which brain layer sent this (high/mid/low)
            prompt_type: Type of prompt (task_decomposition, code_generation, chat, etc)
            metadata: Additional metadata to save
            
        Returns:
            Path to the saved prompt file, or None if logging is disabled
        """
        if not self.enabled:
            return None
        
        if prompt_type not in self.prompt_counters:
            self.prompt_counters[prompt_type] = 0
        self.prompt_counters[prompt_type] += 1
        counter = self.prompt_counters[prompt_type]
        
        try:
            # Create timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            type_dir = os.path.join(self.prompts_dir, prompt_type)
            os.makedirs(type_dir, exist_ok=True)
            
            filename = f"{prompt_type}_{counter:04d}_{timestamp}_{brain_layer}.json"
            filepath = os.path.join(type_dir, filename)
            
            # Prepare data to save
            data = {
                "counter": counter,
                "timestamp": timestamp,
                "brain_layer": brain_layer,
                "prompt_type": prompt_type,
                "agent_name": self.agent_name,
                "prompt": prompt,
                "response": response,
                "metadata": metadata or {}
            }
            
            # Save to file with pretty formatting
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Create a more readable version with separated prompt/response
            self._save_readable_txt(filepath, data)
            
            return filepath
        except Exception as e:
            logger.error(f"Failed to log prompt: {e}")
            return None
    
    def _save_readable_txt(self, original_filepath: str, data: dict):
        """
        Save a readable version with prompt and response in separate files
        
        Args:
            original_filepath: Path to the original JSON file
            data: The data dictionary
        """
        try:
            base_path = original_filepath.replace('.json', '')
            
            # Save prompt as separate .md file for easy reading
            prompt_file = f"{base_path}_PROMPT.md"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"PROMPT - {data['prompt_type']} ({data['brain_layer']} layer)\n")
                f.write(f"Timestamp: {data['timestamp']}\n")
                f.write("=" * 80 + "\n\n")
                f.write(data['prompt'])
            
            # Save response as separate .md file if exists
            if data.get('response'):
                response_file = f"{base_path}_RESPONSE.md"
                with open(response_file, 'w', encoding='utf-8') as f:
                    f.write("=" * 80 + "\n")
                    f.write(f"RESPONSE - {data['prompt_type']} ({data['brain_layer']} layer)\n")
                    f.write(f"Timestamp: {data['timestamp']}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(data['response'])
            
        except Exception as e:
            logger.debug(f"Failed to save readable version: {e}")
    
    def update_response(self, filepath: Optional[str], response: str):
        """
        Update an existing prompt file with the LLM response
        
        Args:
            filepath: Path to the prompt file (can be None if logging disabled)
            response: The LLM response to add
        """
        if not self.enabled or not filepath or not os.path.exists(filepath):
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            data['response'] = response
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Update readable version with response
            self._save_readable_txt(filepath, data)
            
        except Exception as e:
            logger.error(f"Failed to update prompt response: {e}")
    
    def get_recent_prompts(self, n: int = 10) -> list:
        """
        Get the N most recent prompt files
        
        Args:
            n: Number of recent prompts to retrieve
            
        Returns:
            List of filepaths, newest first
        """
        if not self.enabled:
            return []
            
        try:
            files = [
                os.path.join(self.prompts_dir, f)
                for f in os.listdir(self.prompts_dir)
                if f.endswith('.json')
            ]
            
            # Sort by modification time, newest first
            files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            
            return files[:n]
        except Exception as e:
            logger.error(f"Failed to get recent prompts: {e}")
            return []
    
    def clear_old_prompts(self, keep_n: int = 100):
        """
        Delete old prompt files, keeping only the N most recent
        
        Args:
            keep_n: Number of recent prompts to keep
        """
        if not self.enabled:
            return 0
            
        try:
            files = [
                os.path.join(self.prompts_dir, f)
                for f in os.listdir(self.prompts_dir)
                if f.endswith('.json')
            ]
            
            # Sort by modification time, oldest first
            files.sort(key=lambda x: os.path.getmtime(x))
            
            # Delete all but the last keep_n
            to_delete = files[:-keep_n] if len(files) > keep_n else []
            
            for filepath in to_delete:
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            
            if to_delete:
                logger.info(f"Cleaned up {len(to_delete)} old prompt files")
            
            return len(to_delete)
        except Exception as e:
            logger.error(f"Failed to clear old prompts: {e}")
            return 0
