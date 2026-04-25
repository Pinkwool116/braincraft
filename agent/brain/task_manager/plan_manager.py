"""
Plan Manager

Manages the agent's long-term plan file (bots/{name}/plan.md).
Used for strategic goals, long-term milestones, background constraints,
and deferred/conditional reminders — distinct from todolist (concrete todos)
and draft (current step thinking).
"""

import os
import logging

logger = logging.getLogger(__name__)


class PlanManager:
    """
    Manages the agent's plan.md file.

    The plan file records strategic-level content:
    - Current phase goal
    - Long-term milestones
    - Background constraints and preferences
    - Deferred / conditional reminders

    File location: bots/{agent_name}/plan.md
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.plan_dir = os.path.join(str(project_root), 'bots', agent_name)
        self.plan_file = os.path.join(self.plan_dir, 'plan.md')
        logger.info(f"PlanManager initialized: {self.plan_file}")

    def read(self) -> str:
        try:
            with open(self.plan_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.debug(f"Read plan file ({len(content)} chars)")
            return content
        except FileNotFoundError:
            logger.debug("Plan file does not exist, returning empty string")
            return ''
        except Exception as e:
            logger.error(f"Error reading plan file: {e}")
            return ''

    def write(self, content: str):
        try:
            os.makedirs(self.plan_dir, exist_ok=True)
            with open(self.plan_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"Wrote plan file ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Error writing plan file: {e}")
            raise

    def clear(self):
        self.write('')
        logger.info("Plan file cleared")
