"""
Configuration Management

Centralized configuration for the AI Town agent.
"""

import json
import os
from typing import Dict, Any

class Config:
    """Configuration manager for the AI Town agent"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize configuration
        
        Args:
            config_path: Path to configuration file (optional)
        """
        # Default configuration
        self.agent_name = "BrainyBot"
        
        # IPC Settings
        self.ipc_port = 9000
        self.ipc_pub_port = 9001
        
        # Brain Settings
        self.high_brain_interval = 300  # 5 minutes
        self.mid_brain_interval = 1     # 1 second
        self.low_brain_interval = 0.1   # 100ms
        
        # LLM Settings
        self.high_llm_model = "gpt-4"
        self.mid_llm_model = "gpt-4o-mini"
        self.chat_llm_model = "gpt-4o-mini"
        self.summary_llm_model = "gpt-4o-mini"
        
        # Task Management
        self.max_task_retries = 5
        self.task_timeout = 600  # 10 minutes
        
        # Memory Settings
        self.experience_db_path = "./data/experiences"
        self.memory_max_size = 1000
        self.retrieval_top_k = 3
        
        # Load from file if provided
        if config_path and os.path.exists(config_path):
            self.load_from_file(config_path)
    
    def load_from_file(self, path: str):
        """Load configuration from JSON file"""
        with open(path, 'r') as f:
            data = json.load(f)
            for key, value in data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    def save_to_file(self, path: str):
        """Save configuration to JSON file"""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
