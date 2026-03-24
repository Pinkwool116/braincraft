"""
Tool Registry

Central registry for all tools available to the Agent Loop.
Manages tool registration, lookup, and description generation for LLM prompts.
"""

import logging
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
        raise NotImplementedError("Phase 3: implement __init__")

    def register(self, name: str, tool):
        """
        Register a tool.

        Args:
            name: Tool name (used in LLM tool calls)
            tool: Tool instance (must have .execute() method)
        """
        raise NotImplementedError("Phase 3: implement register")

    def get(self, name: str):
        """
        Get a registered tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance, or None if not found
        """
        raise NotImplementedError("Phase 3: implement get")

    def get_tool_descriptions(self) -> str:
        """
        Generate tool descriptions for the LLM prompt.

        Returns:
            Formatted string describing all available tools
        """
        raise NotImplementedError("Phase 3: implement get_tool_descriptions")

    def parse_tool_call(self, response: str) -> dict:
        """
        Parse a tool call from LLM response.

        Expected JSON format: {"tool": "name", "tool_args": {...}}

        Args:
            response: Raw LLM response

        Returns:
            Parsed dict with 'tool' and 'tool_args' keys
        """
        raise NotImplementedError("Phase 3: implement parse_tool_call")
