"""
Agent Loop Layer

Main decision loop that drives the agent's behavior.
Uses LLM to decide which tool to call next based on current context.

Responsibilities:
- Build prompt with current game state, task, memory
- Call LLM to get tool selection
- Execute selected tool and feed result back
- Manage conversation context window
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AgentLoopLayer:
    """
    Main decision loop — the 'thinking' layer of the agent.

    Runs a loop: build_prompt → LLM → parse_tool_call → execute_tool → update_context → repeat
    """

    def __init__(self, shared_state, execution_layer, tool_registry, config, llm_model):
        """
        Initialize the Agent Loop Layer.

        Args:
            shared_state: SharedState instance
            execution_layer: ExecutionLayer instance (for code execution)
            tool_registry: ToolRegistry instance (available tools)
            config: Configuration dictionary
            llm_model: LLM model for decision making
        """
        raise NotImplementedError("Phase 3: implement __init__")

    async def run_loop(self):
        """
        Main decision loop.

        Continuously:
        1. Build prompt from current context
        2. Call LLM for next action
        3. Parse tool call from response
        4. Execute tool
        5. Update context with result
        6. Repeat
        """
        raise NotImplementedError("Phase 3: implement run_loop")

    async def build_prompt(self) -> str:
        """
        Assemble the full prompt for the LLM.

        Includes: system prompt, game state, task, memory, tool descriptions,
        and recent conversation history.

        Returns:
            Complete prompt string
        """
        raise NotImplementedError("Phase 3: implement build_prompt")

    def parse_tool_call(self, response: str) -> dict:
        """
        Parse LLM output to extract tool call.

        Expected format: {"tool": "tool_name", "tool_args": {...}}

        Args:
            response: Raw LLM response string

        Returns:
            Parsed tool call dict with 'tool' and 'tool_args' keys
        """
        raise NotImplementedError("Phase 3: implement parse_tool_call")

    async def execute_tool(self, tool_call: dict) -> dict:
        """
        Execute a tool and return its result.

        Args:
            tool_call: Dict with 'tool' name and 'tool_args'

        Returns:
            Tool execution result dict
        """
        raise NotImplementedError("Phase 3: implement execute_tool")

    def update_context(self, tool_call: dict, result: dict):
        """
        Add tool call and result to conversation context.

        Manages context window size (truncation/summarization when needed).

        Args:
            tool_call: The tool call that was executed
            result: The result from tool execution
        """
        raise NotImplementedError("Phase 3: implement update_context")
