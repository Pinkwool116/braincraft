"""
Task File Manager

Manages the agent's task file (bots/{name}/task.md).
Replaces the old task_stack system with simple file-based task tracking.

The agent reads and writes this file to manage its own goals.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TaskFileManager:
    """
    Manages the agent's task.md file.

    The task file is a simple markdown file where the agent tracks:
    - Current goal
    - Progress and completed steps
    - Next steps planned

    File location: bots/{agent_name}/task.md
    """

    def __init__(self, agent_name: str):
        """
        Initialize task file manager.

        Args:
            agent_name: Agent name (used for file path: bots/{name}/task.md)
        """
        self.agent_name = agent_name
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.task_dir = os.path.join(str(project_root), 'bots', agent_name)
        self.task_file = os.path.join(self.task_dir, 'task.md')
        logger.info(f"TaskFileManager initialized: {self.task_file}")

    def read_task(self) -> str:
        """
        Read the current task file.

        Returns:
            Task file contents, or empty string if file doesn't exist
        """
        try:
            with open(self.task_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.debug(f"Read task file ({len(content)} chars)")
            return content
        except FileNotFoundError:
            logger.debug("Task file does not exist, returning empty string")
            return ''
        except Exception as e:
            logger.error(f"Error reading task file: {e}")
            return ''

    def write_task(self, content: str):
        """
        Write to the task file.

        Creates the file and parent directories if they don't exist.

        Args:
            content: Markdown content to write
        """
        try:
            os.makedirs(self.task_dir, exist_ok=True)
            with open(self.task_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"Wrote task file ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Error writing task file: {e}")
            raise

    def clear_task(self):
        """
        Clear the task file contents.

        Sets the file to empty string (does not delete the file).
        """
        self.write_task('')
        logger.info("Task file cleared")
