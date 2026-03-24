"""
Update Task Tool

Reads and writes the agent's task file (task.md).
Allows the agent to manage its own goals and progress tracking.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class UpdateTaskTool:
    """
    Tool: update_task

    Read or update the agent's task file (bots/{name}/task.md).
    The agent uses this to track its current goals and progress.
    """

    name: str = "update_task"
    description: str = (
        "Read or update your task file (task.md). "
        "Use this to check your current goals, update progress, or set new objectives."
    )

    def __init__(self, task_file_manager):
        """
        Args:
            task_file_manager: TaskFileManager instance
        """
        raise NotImplementedError("Phase 3: implement __init__")

    async def execute(self, args: dict) -> dict:
        """
        Read or update task file.

        Args:
            args: {
                'action': 'read' | 'write' | 'clear',
                'content': str (required for 'write')
            }

        Returns:
            {'success': bool, 'content': str}
        """
        raise NotImplementedError("Phase 3: implement execute")
