"""
Chat Tool

Sends chat messages in the Minecraft game.
The agent uses this to communicate with players.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ChatTool:
    """
    Tool: chat

    Send a chat message in the Minecraft game to communicate with players.
    """

    name: str = "chat"
    description: str = (
        "Send a chat message in the Minecraft game to communicate with players."
    )

    def __init__(self, execution_layer):
        """
        Args:
            execution_layer: ExecutionLayer instance
        """
        self.execution_layer = execution_layer

    async def execute(self, args: dict) -> dict:
        """
        Send a chat message.

        Args:
            args: {'message': str}

        Returns:
            {'success': bool, 'message': str}
        """
        message = args.get('message', '')
        if not message:
            return {'success': False, 'error': 'No message provided'}
        return await self.execution_layer.send_chat(message)
