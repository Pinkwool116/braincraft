"""
Wait Tool

Allows the agent to intentionally pause its loop for a specified number of seconds.
Used when the agent wants to observe, rest, or wait for an event.
"""

import asyncio


class WaitTool:
    """Tool that pauses execution for N seconds."""

    name = "wait"
    description = "等待指定秒数，不执行任何操作。当没有任务、等待某事发生、或需要休息时使用。"

    def __init__(self, default_wait_seconds: int = 10):
        self.default_wait_seconds = default_wait_seconds

    async def execute(self, args: dict) -> dict:
        """
        Execute the wait operation.

        Args:
            args: Dict containing 'seconds' (optional)

        Returns:
            Dict with 'success' and 'waited_seconds'
        """
        try:
            seconds_raw = args.get("seconds", self.default_wait_seconds)
            seconds = int(seconds_raw)
        except (ValueError, TypeError):
            seconds = self.default_wait_seconds

        # Constrain to 1-120 seconds to prevent the agent from sleeping forever
        seconds = min(max(seconds, 1), 120)

        await asyncio.sleep(seconds)

        return {"success": True, "waited_seconds": seconds}
