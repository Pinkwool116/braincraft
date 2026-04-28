"""
Todolist Tool

Structured todolist tool with 6 actions:
add / remove / update / set_status / move / overwrite

No 'read' action — todolist.md content is injected into the prompt.
IDs are visible in the prompt-rendered Markdown.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class TodolistTool:
    """
    Tool: todolist

    Manage your current short-term todos with structured operations.
    Daily operations (80%): add / set_status / update / remove
    Major refactors: overwrite

    IDs are visible in the todolist section of the system prompt —
    no need to call a separate read action.
    """

    name: str = "todolist"
    description: str = (
        "管理你的当前短期待办清单（todolist.md），支持嵌套。\n"
        "每条待办有唯一ID（如t1, t1.2），ID在提示词的待办清单中可见。\n"
        "日常操作：add(新增) / set_status(切换状态) / update(改文本) / remove(删除) / move(移动)\n"
        "兜底操作：overwrite(整文件替换，大重构时用——输出Markdown格式)\n"
        "参数示例：action='set_status', id='t1.2', status='in_progress'\n"
        "参数示例：action='add', text='收集木头', parent_id='t1', position='end'\n"
        "参数示例：action='overwrite', content='- [>] t1 建房子\\n  - [ ] t1.1 收集木头'"
    )

    def __init__(self, store):
        """
        Args:
            store: TodoListStore instance
        """
        self.store = store

    async def execute(self, args: dict) -> dict:
        action = args.get('action', 'add')

        try:
            if action == 'add':
                return await self._handle_add(args)
            elif action == 'remove':
                return await self._handle_remove(args)
            elif action == 'update':
                return await self._handle_update(args)
            elif action == 'set_status':
                return await self._handle_set_status(args)
            elif action == 'move':
                return await self._handle_move(args)
            elif action == 'overwrite':
                return await self._handle_overwrite(args)
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
        except KeyError as e:
            return {'success': False, 'error': str(e)}
        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"TodolistTool error: {e}")
            return {'success': False, 'error': str(e)}

    async def _handle_add(self, args: dict) -> dict:
        text = args.get('text', '')
        if not text:
            return {'success': False, 'error': 'text is required for add'}
        parent_id = args.get('parent_id')
        position = args.get('position', 'end')
        new_id = self.store.add(text=text, parent_id=parent_id, position=position)
        return {'success': True, 'id': new_id, 'message': f'Added {new_id}: {text[:80]}'}

    async def _handle_remove(self, args: dict) -> dict:
        item_id = args.get('id', '')
        if not item_id:
            return {'success': False, 'error': 'id is required for remove'}
        self.store.remove(item_id)
        return {'success': True, 'message': f'Removed {item_id} and its children'}

    async def _handle_update(self, args: dict) -> dict:
        item_id = args.get('id', '')
        text = args.get('text', '')
        if not item_id:
            return {'success': False, 'error': 'id is required for update'}
        if not text:
            return {'success': False, 'error': 'text is required for update'}
        self.store.update(item_id, text)
        return {'success': True, 'message': f'Updated {item_id}: {text[:80]}'}

    async def _handle_set_status(self, args: dict) -> dict:
        item_id = args.get('id', '')
        status = args.get('status', '')
        if not item_id:
            return {'success': False, 'error': 'id is required for set_status'}
        if status not in ('pending', 'in_progress', 'done', 'blocked'):
            return {'success': False, 'error': f'Invalid status: {status}'}
        result = self.store.set_status(item_id, status)
        extra = {}
        if result == 'new_focus':
            extra['draft_cleared'] = True
            extra['hint'] = 'Focus changed — update draft.md for the new task'
        elif result == 'same_focus':
            extra['hint'] = 'Same item already in_progress — draft preserved'
        return {'success': True, 'message': f'Set {item_id} to {status}', **extra}

    async def _handle_move(self, args: dict) -> dict:
        item_id = args.get('id', '')
        new_parent_id = args.get('new_parent_id', '')
        position = args.get('position', 'end')
        if not item_id:
            return {'success': False, 'error': 'id is required for move'}
        if not new_parent_id:
            return {'success': False, 'error': 'new_parent_id is required for move'}
        self.store.move(item_id, new_parent_id, position)
        return {'success': True, 'message': f'Moved {item_id} under {new_parent_id}'}

    async def _handle_overwrite(self, args: dict) -> dict:
        content = args.get('content', '')
        if not content:
            return {'success': False, 'error': 'content is required for overwrite'}
        self.store.overwrite(content)
        return {
            'success': True,
            'message': 'Todolist fully replaced',
            'crystallize_hint': True,
        }
