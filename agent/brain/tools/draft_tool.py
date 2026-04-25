"""
Draft Tool

Writes the agent's current-step technical thinking (draft.md).
Replaces update_task with clearer semantics: draft = coding scratchpad,
NOT a task plan. No 'read' action — draft.md is injected into the prompt.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class DraftTool:
    """
    Tool: draft

    Write or clear the current-step technical thinking (draft.md).
    This is the coding scratchpad that the Coding LLM can read —
    write technical approach, failed attempts, API notes here.
    NOT for long-term goals (use plan) or task sequencing (use todolist).
    """

    name: str = "draft"
    description: str = (
        "修改当前步骤的技术思路草稿（draft.md）。用于记录当前这一步的解题思路、"
        "失败尝试和错误信息、下一步打算——给 Coding LLM 看的技术提示。\n"
        "不要写长期规划（那是 plan 的事），不要写待办步骤（那是 todolist 的事）。\n"
        "参数：action='write'|'clear', content='...'(write时必填，整文件替换)"
    )

    def __init__(self, draft_manager):
        self.draft_manager = draft_manager

    async def execute(self, args: dict) -> dict:
        action = args.get('action', 'write')

        try:
            if action == 'write':
                content = args.get('content', '')
                self.draft_manager.write(content)
                return {'success': True, 'content': content}
            elif action == 'clear':
                self.draft_manager.clear()
                return {'success': True, 'content': ''}
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
        except Exception as e:
            logger.error(f"DraftTool error: {e}")
            return {'success': False, 'error': str(e)}
