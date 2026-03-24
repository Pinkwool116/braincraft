"""
Execution Layer

Handles code generation and execution for the agent.
Called as a tool by the Agent Loop Layer.

Responsibilities:
- Generate JavaScript code via Coding LLM
- Send code to Minecraft Bridge via IPC
- Wait for execution result
- Handle interruption
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ExecutionLayer:
    """
    Code generation and execution layer.

    Generates JavaScript code using a coding LLM, sends it to the
    Minecraft Bridge for execution, and returns the result.
    """

    is_executing: bool = False

    def __init__(self, shared_state, ipc_server, exec_coordinator, config, coding_llm, prompt_manager):
        """
        Initialize the Execution Layer.

        Args:
            shared_state: SharedState instance
            ipc_server: IPC server for communicating with JavaScript bridge
            exec_coordinator: ExecutionCoordinator for priority management
            config: Configuration dictionary
            coding_llm: LLM model for code generation
            prompt_manager: PromptManager for building coding prompts
        """
        raise NotImplementedError("Phase 3: implement __init__")

    async def execute_step(self, step_description: str) -> dict:
        """
        Generate code for a step and execute it.

        Flow: step_description → build_coding_prompt → Coding LLM → parse code → IPC execute → result

        Args:
            step_description: Natural language description of what to do

        Returns:
            {
                'success': bool,
                'code': str,          # Generated code
                'output': str,        # Execution output
                'error': str,         # Error message if failed
                'analysis': str,      # LLM's analysis
            }
        """
        raise NotImplementedError("Phase 3: implement execute_step")

    async def send_chat(self, message: str) -> dict:
        """
        Send a chat message in game.

        Args:
            message: Chat message to send

        Returns:
            {'success': bool, 'message': str}
        """
        raise NotImplementedError("Phase 3: implement send_chat")

    async def interrupt(self) -> dict:
        """
        Interrupt the currently executing code.

        Uses ExecutionCoordinator's interrupt mechanism.

        Returns:
            {'success': bool, 'was_executing': bool}
        """
        raise NotImplementedError("Phase 3: implement interrupt")

    async def _build_coding_prompt(self, step_description: str) -> str:
        """
        Build the coding prompt for the LLM.

        Uses PromptManager to render mid_level/coding.md with current context.

        Args:
            step_description: What the code should accomplish

        Returns:
            Complete coding prompt string
        """
        raise NotImplementedError("Phase 3: implement _build_coding_prompt")
