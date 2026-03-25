"""
Tool Registry

Central registry for all tools available to the Agent Loop.
Manages tool registration, lookup, and description generation for LLM prompts.
"""

import json
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry of tools available to the Agent Loop LLM.

    Provides:
    - Tool registration and lookup
    - Tool description generation (for LLM system prompt)
    - Tool call parsing from LLM response
    """

    def __init__(self):
        """Initialize empty registry."""
        self._tools: Dict[str, Any] = {}
        logger.info("ToolRegistry initialized")

    def register(self, name: str, tool):
        """
        Register a tool.

        Args:
            name: Tool name (used in LLM tool calls)
            tool: Tool instance (must have .execute(args) async method)
        """
        if name in self._tools:
            logger.warning(f"Overwriting existing tool: {name}")
        self._tools[name] = tool
        logger.info(f"Tool registered: {name}")

    def get(self, name: str):
        """
        Get a registered tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance, or None if not found
        """
        tool = self._tools.get(name)
        if tool is None:
            logger.warning(f"Tool not found: {name}")
        return tool

    def get_tool_descriptions(self) -> str:
        """
        Generate tool descriptions for the LLM prompt.

        Each tool should have 'name' and 'description' attributes.

        Returns:
            Formatted string describing all available tools
        """
        if not self._tools:
            return "(no tools available)"

        lines = []
        for name, tool in self._tools.items():
            desc = getattr(tool, 'description', '(no description)')
            lines.append(f"- **{name}**: {desc}")

        return '\n'.join(lines)

    def parse_tool_call(self, response: str) -> dict:
        """
        Parse a tool call from LLM response.

        Expected JSON format:
        {
            "thinking": "...",
            "tool": "tool_name",
            "tool_args": { ... }
        }

        Handles common LLM quirks: markdown code fences, trailing commas, etc.

        Args:
            response: Raw LLM response string

        Returns:
            Parsed dict with 'thinking', 'tool', and 'tool_args' keys.
            On parse failure, returns {'tool': None, 'tool_args': {}, 'error': '...'}.
        """
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith('```'):
            # Remove opening fence (```json or ```)
            text = re.sub(r'^```\w*\s*', '', text)
            # Remove closing fence
            text = re.sub(r'\s*```\s*$', '', text)
            text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object from the response
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool call JSON: {e}")
                    return {'tool': None, 'tool_args': {}, 'error': f'JSON parse error: {e}'}
            else:
                logger.error("No JSON object found in LLM response")
                return {'tool': None, 'tool_args': {}, 'error': 'No JSON found in response'}

        tool_name = parsed.get('tool')
        tool_args = parsed.get('tool_args', {})
        thinking = parsed.get('thinking', '')

        # Validate tool exists
        if tool_name and tool_name not in self._tools:
            logger.warning(f"LLM called unknown tool: {tool_name}")

        return {
            'thinking': thinking,
            'tool': tool_name,
            'tool_args': tool_args,
        }
