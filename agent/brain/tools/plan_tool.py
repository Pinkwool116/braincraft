"""
Plan Tool

Writes the agent's long-term plan file (plan.md).
No 'read' action — plan.md content is injected into the prompt by build_prompt().
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PlanTool:
    """
    Tool: plan

    Write or clear the agent's long-term plan (plan.md).
    Used for strategic goals, long-term milestones, background constraints,
    and deferred reminders — NOT for concrete todos (use todolist) or
    current-step thinking (use draft).
    """

    name: str = "plan"
    description: str = (
        "修改你的长期规划（plan.md）。用于记录阶段目标、长期方向、背景约束、延后备忘等宏观战略。\n"
        "不要写具体执行步骤（那是 todolist 的事），不要写当前思路（那是 draft 的事）。\n"
        "参数：action='write'|'clear', content='...'(write时必填，整文件替换)"
    )

    def __init__(self, plan_manager):
        self.plan_manager = plan_manager

    async def execute(self, args: dict) -> dict:
        action = args.get('action', 'write')

        try:
            if action == 'write':
                content = args.get('content', '')
                self.plan_manager.write(content)
                return {'success': True, 'content': content}
            elif action == 'clear':
                self.plan_manager.clear()
                return {'success': True, 'content': ''}
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
        except Exception as e:
            logger.error(f"PlanTool error: {e}")
            return {'success': False, 'error': str(e)}
