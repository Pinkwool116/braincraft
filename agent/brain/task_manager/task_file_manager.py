"""
Task File Manager

Manages the agent's task file (bots/{name}/task.md).
Replaces the old task_stack system with simple file-based task tracking.

The agent reads and writes this file to manage its own goals.
"""

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
        raise NotImplementedError("Phase 3: implement __init__")

    def read_task(self) -> str:
        """
        Read the current task file.

        Returns:
            Task file contents, or empty string if file doesn't exist
        """
        raise NotImplementedError("Phase 3: implement read_task")

    def write_task(self, content: str):
        """
        Write to the task file.

        Creates the file and parent directories if they don't exist.

        Args:
            content: Markdown content to write
        """
        raise NotImplementedError("Phase 3: implement write_task")

    def clear_task(self):
        """
        Clear the task file contents.

        Sets the file to empty string (does not delete the file).
        """
        raise NotImplementedError("Phase 3: implement clear_task")
