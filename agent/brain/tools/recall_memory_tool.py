"""
Recall Memory Tool

Retrieves relevant memories from the agent's long-term memory.
Supports two modes:
- context: Retrieve memories related to a query via spreading activation.
- path: Find how two entities are connected through past experiences.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class RecallMemoryTool:
    """
    Tool: recall_memory

    Search the agent's long-term memory graph.
    """

    name: str = "recall_memory"
    description: str = (
        "Search the agent's long-term memory. Two modes:\n"
        "- context mode: Retrieve memories related to a query. "
        "Use this to recall past experiences, known locations, learned patterns, "
        "or previous solutions to similar problems.\n"
        "- path mode: Find how two entities (places, items, people) are connected "
        "through past experiences. Use this to discover relationships, "
        "e.g. how you know a player or how a location was reached from another."
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
            args: {
                'query': str,                                    # context mode
                'mode': 'context' | 'path' (optional, default: 'context'),
                'entity_a': str (required for path mode),
                'entity_b': str (required for path mode),
            }

        Returns:
            {'success': bool, 'memories': str}
        """
        if self.memory_manager is None:
            return {'success': False, 'error': 'Memory system not available'}

        mode = args.get('mode', 'context')

        try:
            if mode == 'path':
                entity_a = args.get('entity_a', '')
                entity_b = args.get('entity_b', '')
                if not entity_a or not entity_b:
                    return {'success': False,
                            'error': 'Path mode requires both entity_a and entity_b'}

                paths = self.memory_manager.retriever.find_paths(
                    entity_a, entity_b, max_length=4
                )
                if not paths:
                    return {'success': True,
                            'memories': f'(No known path between "{entity_a}" and "{entity_b}" in memory)'}

                lines = [f'=== Paths connecting "{entity_a}" and "{entity_b}" ===']
                for i, p in enumerate(paths, 1):
                    lines.append(f"Path {i} ({p['length']} hops): {p['description']}")
                return {'success': True, 'memories': '\n'.join(lines)}

            else:
                query = args.get('query', '')
                if not query:
                    return {'success': False, 'error': 'No query provided'}
                memories = await self.memory_manager.retrieve_context_async([query])
                return {'success': True,
                        'memories': memories if memories else '(no relevant memories found)'}

        except Exception as e:
            logger.error(f"RecallMemoryTool error: {e}")
            return {'success': False, 'error': str(e)}
