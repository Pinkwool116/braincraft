"""
Todolist Tool

Manages the agent's todolist (todolist.md).
Used for high-level planning: long-term goals, deferred tasks,
conditional reminders, and notable locations.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class TodolistTool:
    """
    Tool: todolist

    Read or update your todolist (todolist.md).
    Use this for long-term planning, deferred tasks, conditional reminders,
    and notable coordinates — your personal planning memo.
    """

    name: str = "todolist"
    description: str = (
        "管理你的待办清单（todolist.md）。用于记录长期目标、延后任务、"
        "条件触发事项（如'天黑后提醒玩家'）、重要坐标备忘等宏观规划。\n"
        "参数：action='read'|'write'|'clear', content='...'(write时必填)"
    )

    def __init__(self, todolist_manager):
        """
        Args:
            todolist_manager: TodoListManager instance
        """
        self.todolist_manager = todolist_manager

    async def execute(self, args: dict) -> dict:
        """
        Read or update todolist file.

        Args:
            args: {
                'action': 'read' | 'write' | 'clear',
                'content': str (required for 'write')
            }

        Returns:
            {'success': bool, 'content': str}
        """
        action = args.get('action', 'read')

        try:
            if action == 'read':
                content = self.todolist_manager.read()
                return {'success': True, 'content': content}
            elif action == 'write':
                content = args.get('content', '')
                self.todolist_manager.write(content)
                return {'success': True, 'content': content}
            elif action == 'clear':
                self.todolist_manager.clear()
                return {'success': True, 'content': ''}
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
        except Exception as e:
            logger.error(f"TodolistTool error: {e}")
            return {'success': False, 'error': str(e)}
