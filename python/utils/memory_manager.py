"""
Memory and Learned Experience Manager

Manages persistent storage of:
- Short-term memory (recent events, conversations)
- Long-term learned experience (insights from successes/failures, lessons learned)
- Player information (personality traits, preferences)
"""

import json
import os
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

class MemoryManager:
    """
    Manages memory and learned experience persistence
    
    File structure:
    - bots/{agent_name}/memory.json - Short-term memory
    - bots/{agent_name}/learned_experience.json - Long-term learned experience
    - bots/{agent_name}/players.json - Player information
    """
    
    def __init__(self, agent_name: str = "BrainyBot"):
        """
        Initialize memory manager
        
        Args:
            agent_name: Name of the agent (for file paths)
        """
        self.agent_name = agent_name
        self.base_dir = os.path.join("bots", agent_name)
        
        # Create directory if needed
        os.makedirs(self.base_dir, exist_ok=True)
        
        # File paths
        self.memory_file = os.path.join(self.base_dir, "memory.json")
        self.experience_file = os.path.join(self.base_dir, "learned_experience.json")
        self.players_file = os.path.join(self.base_dir, "players.json")
        
        # Load existing data
        self.memory = self._load_json(self.memory_file, default={"short_term": []})
        self.learned_experience = self._load_json(self.experience_file, default={"insights": [], "lessons_learned": []})
        self.players = self._load_json(self.players_file, default={})
        
        logger.info(f"Memory manager initialized for agent: {agent_name}")
    
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
    
    # ===== SHORT-TERM MEMORY =====
    
    def add_short_term_memory(self, event_type: str, content: str, metadata: Dict[str, Any] = None):
        """
        Add short-term memory event
        
        Args:
            event_type: Type of event (e.g., "code_execution", "chat", "task_completion")
            content: Event content/description
            metadata: Additional metadata
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'content': content,
            'metadata': metadata or {}
        }
        
        self.memory['short_term'].append(entry)
        
        # Keep only last 50 short-term memories
        if len(self.memory['short_term']) > 50:
            self.memory['short_term'] = self.memory['short_term'][-50:]
        
        self._save_json(self.memory_file, self.memory)
        logger.debug(f"Added short-term memory: {event_type}")
    
    def get_recent_memories(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent short-term memories"""
        return self.memory['short_term'][-count:]
    
    # ===== LONG-TERM LEARNED EXPERIENCE =====
    
    def add_experience(self, summary: str, details: Dict[str, Any]):
        """
        Add learned experience/insight
        
        Args:
            summary: Brief insight learned from experience (complete description)
            details: Detailed information (successes, failures, context)
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'summary': summary,
            'details': details
        }
        
        self.learned_experience['insights'].append(entry)
        
        # Keep only last 100 insights
        if len(self.learned_experience['insights']) > 100:
            self.learned_experience['insights'] = self.learned_experience['insights'][-100:]
        
        self._save_json(self.experience_file, self.learned_experience)
        logger.info(f"Added learned insight: {summary}")
    
    def add_lesson(self, lesson: str, context: str = ""):
        """
        Add learned lesson
        
        Args:
            lesson: Lesson learned from failure/mistake (complete description)
            context: Context in which lesson was learned
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'lesson': lesson,
            'context': context
        }
        
        self.learned_experience['lessons_learned'].append(entry)
        
        # Keep only last 50 lessons
        if len(self.learned_experience['lessons_learned']) > 50:
            self.learned_experience['lessons_learned'] = self.learned_experience['lessons_learned'][-50:]
        
        self._save_json(self.experience_file, self.learned_experience)
        logger.info(f"Added lesson learned: {lesson}")
    
    def get_learned_experience_summary(self, max_insights: int = 5, max_lessons: int = 10) -> str:
        """
        Get formatted learned experience summary for prompts
        
        Args:
            max_insights: Max recent insights to include
            max_lessons: Max recent lessons to include
        
        Returns:
            Formatted learned experience string
        """
        lines = []
        
        # Recent insights
        if self.learned_experience['insights']:
            lines.append("=== LEARNED INSIGHTS ===")
            for exp in self.learned_experience['insights'][-max_insights:]:
                timestamp = exp['timestamp'][:10]  # Date only
                lines.append(f"- [{timestamp}] {exp['summary']}")
            lines.append("")
        
        # Learned lessons
        if self.learned_experience['lessons_learned']:
            lines.append("=== LESSONS LEARNED ===")
            for lesson in self.learned_experience['lessons_learned'][-max_lessons:]:
                lines.append(f"- {lesson['lesson']}")
            lines.append("")
        
        return "\n".join(lines) if lines else "No learned experience yet."
    
    # ===== PLAYER INFORMATION =====
    
    def update_player_info(self, player_name: str, info_type: str, content: str):
        """
        Update player information
        
        Args:
            player_name: Player username
            info_type: Type of info (e.g., "personality", "preference", "relationship")
            content: Information content
        """
        if player_name not in self.players:
            self.players[player_name] = {
                'first_met': datetime.now().isoformat(),
                'personality': [],
                'preferences': [],
                'interactions': [],
                'relationship': 'neutral',  # neutral, friendly, hostile
                'trust_level': 0.5  # 0.0 to 1.0
            }
        
        # Add to appropriate category
        if info_type == "personality":
            self.players[player_name]['personality'].append(content)
            # Keep only last 5 personality traits
            self.players[player_name]['personality'] = self.players[player_name]['personality'][-5:]
        elif info_type == "preference":
            self.players[player_name]['preferences'].append(content)
            self.players[player_name]['preferences'] = self.players[player_name]['preferences'][-5:]
        else:
            # General interaction
            self.players[player_name]['interactions'].append({
                'timestamp': datetime.now().isoformat(),
                'content': content
            })
            # Keep only last 10 interactions
            self.players[player_name]['interactions'] = self.players[player_name]['interactions'][-10:]
        
        self._save_json(self.players_file, self.players)
        logger.info(f"Updated player info for {player_name}: {info_type}")
    
    def get_player_info(self, player_name: str) -> str:
        """
        Get formatted player information
        
        Args:
            player_name: Player username
        
        Returns:
            Formatted player info string
        """
        if player_name not in self.players:
            return f"No information about {player_name} yet."
        
        info = self.players[player_name]
        lines = [f"=== {player_name} ==="]
        
        if info.get('personality'):
            lines.append("Personality: " + ", ".join(info['personality']))
        if info.get('preferences'):
            lines.append("Preferences: " + ", ".join(info['preferences']))
        
        return "\n".join(lines)
    
    def get_player_data(self, player_name: str) -> dict:
        """
        Get raw player data
        
        Args:
            player_name: Player username
        
        Returns:
            Player data dict or None if player not found
        """
        return self.players.get(player_name, None)
    
    def get_all_players_summary(self) -> str:
        """Get summary of all known players"""
        if not self.players:
            return "No players known yet."
        
        lines = ["=== KNOWN PLAYERS ==="]
        for name, info in self.players.items():
            personality = info.get('personality', [])
            if personality:
                lines.append(f"- {name}: {', '.join(personality[:2])}")
            else:
                lines.append(f"- {name}")
        
        return "\n".join(lines)
