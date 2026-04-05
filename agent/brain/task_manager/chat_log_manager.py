"""
Chat Log Manager

Persists received player messages to bots/{name}/chat_log.md.
Provides recent chat history for injection into prompts.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Maximum lines to keep in the log file before trimming
_MAX_LINES = 200
# How many recent lines to return for prompt context
_DEFAULT_RECENT = 30


class ChatLogManager:
    """
    Appends received player chat messages to chat_log.md and
    provides recent history for prompt injection.

    File location: bots/{agent_name}/chat_log.md
    Format per line:  [HH:MM] <Player> message
    """

    def __init__(self, agent_name: str, recent_lines: int = _DEFAULT_RECENT):
        self.agent_name = agent_name
        self.recent_lines = recent_lines
        self._dir = os.path.join('bots', agent_name)
        self._file = os.path.join(self._dir, 'chat_log.md')
        logger.info(f"ChatLogManager initialized: {self._file}")

    def append(self, player: str, message: str):
        """
        Append a single received message to the log file.

        Args:
            player:  Player name
            message: Message text
        """
        try:
            os.makedirs(self._dir, exist_ok=True)
            timestamp = datetime.now().strftime('%H:%M')
            line = f"[{timestamp}] <{player}> {message}\n"
            with open(self._file, 'a', encoding='utf-8') as f:
                f.write(line)
            self._trim_if_needed()
        except Exception as e:
            logger.error(f"ChatLogManager.append error: {e}")

    def get_recent(self) -> str:
        """
        Return the last N lines of the chat log as a formatted string.

        Returns:
            Multi-line string, or empty string if log is empty / missing.
        """
        try:
            with open(self._file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            recent = lines[-self.recent_lines:]
            return ''.join(recent).strip()
        except FileNotFoundError:
            return ''
        except Exception as e:
            logger.error(f"ChatLogManager.get_recent error: {e}")
            return ''

    def _trim_if_needed(self):
        """Keep the file under _MAX_LINES to prevent unbounded growth."""
        try:
            with open(self._file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) > _MAX_LINES:
                with open(self._file, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-_MAX_LINES:])
        except Exception:
            pass
