"""
Todolist Manager

Manages the agent's todolist file (bots/{name}/todolist.md).
Used for high-level planning, deferred tasks, conditional reminders,
and long-term goals — distinct from task.md (coding scratchpad).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TodoListManager:
    """
    Manages the agent's todolist.md file.

    The todolist file is a markdown memo where the agent tracks:
    - Long-term goals and staged plans
    - Deferred tasks that can't be executed immediately
    - Conditional triggers (e.g., "remind player when night falls")
    - Notable coordinates and resource locations

    File location: bots/{agent_name}/todolist.md
    """

    def __init__(self, agent_name: str):
        """
        Initialize todolist manager.

        Args:
            agent_name: Agent name (used for file path: bots/{name}/todolist.md)
        """
        self.agent_name = agent_name
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.todolist_dir = os.path.join(str(project_root), 'bots', agent_name)
        self.todolist_file = os.path.join(self.todolist_dir, 'todolist.md')
        logger.info(f"TodoListManager initialized: {self.todolist_file}")

    def read(self) -> str:
        """
        Read the current todolist file.

        Returns:
            Todolist file contents, or empty string if file doesn't exist
        """
        try:
            with open(self.todolist_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.debug(f"Read todolist file ({len(content)} chars)")
            return content
        except FileNotFoundError:
            logger.debug("Todolist file does not exist, returning empty string")
            return ''
        except Exception as e:
            logger.error(f"Error reading todolist file: {e}")
            return ''

    def write(self, content: str):
        """
        Write to the todolist file.

        Creates the file and parent directories if they don't exist.

        Args:
            content: Markdown content to write
        """
        try:
            os.makedirs(self.todolist_dir, exist_ok=True)
            with open(self.todolist_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"Wrote todolist file ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Error writing todolist file: {e}")
            raise

    def clear(self):
        """
        Clear the todolist file contents.

        Sets the file to empty string (does not delete the file).
        """
        self.write('')
        logger.info("Todolist file cleared")
