"""
Chat History Manager

Manages persistent storage of chat conversations with players.
Chat history is organized by player name, with each player having
a maximum of 30 stored messages.

File structure:
- bots/{agent_name}/chat_history.json - Chat messages organized by player
"""

import json
import os
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ChatManager:
    """
    Manages chat history persistence
    
    Each player's chat history is stored separately with max 30 messages per player.
    Chat data structure:
    {
        "player_name": [
            {
                "timestamp": "ISO format",
                "player_message": "what player said",
                "bot_response": "what bot responded"
            },
            ...
        ]
    }
    """
    
    MAX_MESSAGES_PER_PLAYER = 30
    
    def __init__(self, agent_name: str = "BrainyBot"):
        """
        Initialize chat manager
        
        Args:
            agent_name: Name of the agent (for file paths)
        """
        self.agent_name = agent_name
        self.base_dir = os.path.join("bots", agent_name)
        
        # Create directory if needed
        os.makedirs(self.base_dir, exist_ok=True)
        
        # File path
        self.chat_file = os.path.join(self.base_dir, "chat_history.json")
        
        # Load existing chat data
        self.chat_history = self._load_json(self.chat_file, default={})
        
        logger.info(f"Chat manager initialized for agent: {agent_name}")
    
    def _load_json(self, filepath: str, default: Any = None) -> Any:
        """Load JSON file, return default if not found"""
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load {filepath}: {e}")
        return default or {}
    
    def _save_json(self, filepath: str, data: Any):
        """Save JSON file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save {filepath}: {e}")
    
    def add_chat(self, player_name: str, player_message: str, bot_response: str):
        """
        Add a chat exchange to history
        
        Args:
            player_name: Name of the player
            player_message: Message from player
            bot_response: Response from bot
        """
        if player_name not in self.chat_history:
            self.chat_history[player_name] = []
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'player_message': player_message,
            'bot_response': bot_response
        }
        
        self.chat_history[player_name].append(entry)
        
        # Keep only last MAX_MESSAGES_PER_PLAYER for this player
        if len(self.chat_history[player_name]) > self.MAX_MESSAGES_PER_PLAYER:
            self.chat_history[player_name] = self.chat_history[player_name][-self.MAX_MESSAGES_PER_PLAYER:]
        
        self._save_json(self.chat_file, self.chat_history)
        logger.debug(f"Added chat from {player_name}: {player_message[:50]}")
    
    def get_player_chat_history(self, player_name: str, limit: int = None) -> List[Dict[str, Any]]:
        """
        Get chat history for a specific player
        
        Args:
            player_name: Name of the player
            limit: Maximum number of recent messages to return (None for all)
        
        Returns:
            List of chat exchanges
        """
        if player_name not in self.chat_history:
            return []
        
        history = self.chat_history[player_name]
        if limit:
            history = history[-limit:]
        
        return history
    
    def get_player_chat_context(self, player_name: str, limit: int = 5) -> str:
        """
        Get formatted chat context for a specific player for use in prompts
        
        Args:
            player_name: Name of the player
            limit: Maximum number of recent messages to include
        
        Returns:
            Formatted chat context string
        """
        history = self.get_player_chat_history(player_name, limit=limit)
        
        if not history:
            return f"No previous conversation history with {player_name}."
        
        lines = [f"=== CONVERSATION WITH {player_name.upper()} ==="]
        for exchange in history:
            lines.append(f"{player_name}: {exchange['player_message']}")
            lines.append(f"Bot: {exchange['bot_response']}")
        
        return "\n".join(lines)
    
    def get_all_players_with_chat(self) -> List[str]:
        """
        Get list of all players who have chat history
        
        Returns:
            List of player names
        """
        return list(self.chat_history.keys())
    
    def get_chat_summary(self) -> str:
        """
        Get summary of all chat interactions
        
        Returns:
            Formatted summary string
        """
        if not self.chat_history:
            return "No chat history."
        
        lines = ["=== CHAT HISTORY SUMMARY ==="]
        for player_name, messages in self.chat_history.items():
            lines.append(f"- {player_name}: {len(messages)} messages")
        
        return "\n".join(lines)
    
    def clear_player_chat(self, player_name: str):
        """
        Clear chat history for a specific player
        
        Args:
            player_name: Name of the player
        """
        if player_name in self.chat_history:
            del self.chat_history[player_name]
            self._save_json(self.chat_file, self.chat_history)
            logger.info(f"Cleared chat history for {player_name}")
    
    def clear_all_chat(self):
        """Clear all chat history"""
        self.chat_history = {}
        self._save_json(self.chat_file, self.chat_history)
        logger.info("Cleared all chat history")
