"""
Recall Memory Tool

Retrieves relevant memories from the agent's long-term memory.
Used when the agent needs to recall past experiences or knowledge.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class RecallMemoryTool:
    """
    Tool: recall_memory

    Retrieve relevant memories from past experiences.
    Use this to recall how you solved similar problems before,
    what resources you found, or important locations.
    """

    name: str = "recall_memory"
    description: str = (
        "Retrieve relevant memories from past experiences. "
        "Use this to recall how you solved similar problems before, "
        "what resources you found, or important locations."
    )

    def __init__(self, memory_manager):
        """
        Args:
            memory_manager: MemoryRouter instance (can be None)
        """
        self.memory_manager = memory_manager

    async def execute(self, args: dict) -> dict:
        """
        Query memory system.

        Args:
            args: {'query': str}

        Returns:
            {'success': bool, 'memories': str}
        """
        if self.memory_manager is None:
            return {'success': False, 'error': 'Memory system not available'}

        query = args.get('query', '')
        if not query:
            return {'success': False, 'error': 'No query provided'}

        try:
            memories = await self.memory_manager.retrieve_context_async([query])
            return {'success': True, 'memories': memories if memories else '(no relevant memories found)'}
        except Exception as e:
            logger.error(f"RecallMemoryTool error: {e}")
            return {'success': False, 'error': str(e)}
