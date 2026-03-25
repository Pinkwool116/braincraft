"""
Interrupt Tool

Interrupts the currently executing code.
Used when the agent decides to stop the current action.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class InterruptTool:
    """
    Tool: interrupt_execution

    Stop the currently running code execution.
    Use this when you need to abort the current action
    (e.g., the approach isn't working, priorities changed).
    """

    name: str = "interrupt_execution"
    description: str = (
        "Stop the currently running code execution. "
        "Use when you need to abort the current action."
    )

    def __init__(self, execution_layer):
        """
        Args:
            execution_layer: ExecutionLayer instance
        """
        self.execution_layer = execution_layer

    async def execute(self, args: dict) -> dict:
        """
        Interrupt current execution.

        Args:
            args: {} (no arguments needed)

        Returns:
            {'success': bool, 'was_executing': bool}
        """
        return await self.execution_layer.interrupt()
