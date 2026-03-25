"""
Execute Step Tool

Calls ExecutionLayer to generate and run code for a task step.
This is the primary tool for the agent to interact with the game world.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ExecuteStepTool:
    """
    Tool: execute_step

    Generates JavaScript code and executes it in the game.
    Used when the agent needs to perform an action in Minecraft.
    """

    name: str = "execute_step"
    description: str = (
        "Generate and execute JavaScript code to perform an action in Minecraft. "
        "Use this when you need to interact with the game world (mine, build, craft, move, etc.)."
    )

    def __init__(self, execution_layer):
        """
        Args:
            execution_layer: ExecutionLayer instance
        """
        self.execution_layer = execution_layer

    async def execute(self, args: dict) -> dict:
        """
        Execute a step.

        Args:
            args: {'step_description': str} or {'step': str}

        Returns:
            ExecutionLayer result dict
        """
        step = args.get('step_description') or args.get('step', '')
        if not step:
            return {'success': False, 'error': 'No step description provided'}
        return await self.execution_layer.execute_step(step)
