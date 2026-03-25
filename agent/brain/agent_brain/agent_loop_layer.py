"""
Agent Loop Layer

Main decision loop that drives the agent's behavior.
Uses LLM to decide which tool to call next based on current context.

Responsibilities:
- Build prompt with current game state, task, memory
- Call LLM to get tool selection
- Execute selected tool and feed result back
- Manage conversation context window
- Dead loop protection
- Chat message queue processing
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class AgentLoopLayer:
    """
    Main decision loop — the 'thinking' layer of the agent.

    Runs a loop: build_prompt → LLM → parse_tool_call → execute_tool → update_context → repeat
    """

    def __init__(self, shared_state, execution_layer, tool_registry, config, llm_model,
                 prompt_manager, task_manager, memory_manager=None):
        """
        Initialize the Agent Loop Layer.

        Args:
            shared_state: SharedState instance
            execution_layer: ExecutionLayer instance (for code execution)
            tool_registry: ToolRegistry instance (available tools)
            config: Configuration dictionary
            llm_model: LLM model for decision making
            prompt_manager: PromptManager for building prompts
            task_manager: TaskFileManager for task.md access
            memory_manager: MemoryRouter instance (None in Phase 3)
        """
        self.shared_state = shared_state
        self.execution_layer = execution_layer
        self.tool_registry = tool_registry
        self.config = config
        self.llm = llm_model
        self.prompt_manager = prompt_manager
        self.task_manager = task_manager
        self.memory_manager = memory_manager

        # Config parameters
        loop_config = config.get('agent_loop', {})
        self.max_consecutive_loops = loop_config.get('max_consecutive_loops', 50)
        self.idle_interval = loop_config.get('idle_interval_seconds', 30)

        # State
        self.running = False
        self.chat_queue = asyncio.Queue()
        self.last_tool_result = None
        self.consecutive_loops = 0
        self.last_tool_calls: List[dict] = []  # Recent calls for dead loop detection

        logger.info("AgentLoopLayer initialized")

    async def run_loop(self):
        """
        Main decision loop.

        Continuously:
        1. Check dead loop protection
        2. Build prompt from current context
        3. Call LLM for next action
        4. Parse tool call from response
        5. Execute tool
        6. Update context with result
        7. Repeat
        """
        self.running = True
        logger.info("Agent Loop started")

        while self.running:
            try:
                # Dead loop protection: max consecutive loops
                if self.consecutive_loops >= self.max_consecutive_loops:
                    logger.warning(
                        f"Max consecutive loops ({self.max_consecutive_loops}) reached. "
                        f"Pausing for {self.idle_interval}s."
                    )
                    await asyncio.sleep(self.idle_interval)
                    self.consecutive_loops = 0

                # Check if there's anything to do
                has_chat = not self.chat_queue.empty()
                has_task = bool(self.task_manager.read_task().strip())
                has_pending_result = self.last_tool_result is not None

                # If idle (no chat, no task, no pending result), sleep
                if not has_chat and not has_task and not has_pending_result:
                    await asyncio.sleep(self.idle_interval)
                    # Re-check after sleep
                    if self.chat_queue.empty() and not self.task_manager.read_task().strip():
                        continue

                # Build prompt
                prompt = await self.build_prompt()

                # Call LLM
                messages = [{"role": "user", "content": prompt}]
                response = await self.llm.send_request(messages)

                if not response:
                    logger.warning("LLM returned empty response")
                    await asyncio.sleep(5)
                    continue

                # Parse tool call
                tool_call = self.parse_tool_call(response)

                if not tool_call.get('tool'):
                    logger.warning(f"No tool in LLM response: {tool_call.get('error', 'unknown')}")
                    # Record the thinking even if no tool
                    if tool_call.get('thinking'):
                        logger.info(f"Agent thinking: {tool_call['thinking'][:100]}")
                    await asyncio.sleep(5)
                    continue

                # Log the decision
                thinking = tool_call.get('thinking', '')
                logger.info(
                    f"Agent decision: tool={tool_call['tool']}, "
                    f"thinking={thinking[:80]}..."
                )

                # Execute tool
                result = await self.execute_tool(tool_call)

                # Update context
                self.update_context(tool_call, result)

                self.consecutive_loops += 1

            except asyncio.CancelledError:
                logger.info("Agent Loop cancelled")
                break
            except Exception as e:
                logger.error(f"Agent Loop error: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("Agent Loop stopped")

    async def build_prompt(self) -> str:
        """
        Assemble the full prompt for the LLM.

        Renders agent_loop/system.md with current context including:
        game state, task, memory, tool descriptions, chat messages, last result.

        Returns:
            Complete prompt string
        """
        state = await self.shared_state.get_all()

        # Read task file
        task_content = self.task_manager.read_task()

        # Drain chat queue
        pending_chat = self._drain_chat_queue()

        # Format last tool result
        if self.last_tool_result:
            last_result_str = json.dumps(self.last_tool_result, ensure_ascii=False, indent=2)
        else:
            last_result_str = "无（这是第一轮决策）"

        # Detect repeated tool calls
        repeat_warning = self._check_repeat_calls()

        # Build context for prompt rendering
        context = {
            'state': state,
            'agent_name': state.get('agent_name', 'BrainyBot'),
            'memory_manager': self.memory_manager,
            # Direct values for agent_loop/system.md
            'TASK_FILE': task_content if task_content else "(任务为空——你可以自由决定做什么)",
            'PENDING_CHAT': pending_chat if pending_chat else "(无新消息)",
            'TOOL_DESCRIPTIONS': self.tool_registry.get_tool_descriptions(),
            'LAST_TOOL_RESULT': last_result_str,
            'SOUL': self.config.get('soul', ''),
        }

        prompt = await self.prompt_manager.render(
            'agent_loop/system.md',
            context=context,
            strict=False
        )

        # Append repeat warning if detected
        if repeat_warning:
            prompt += f"\n\n⚠️ 注意：{repeat_warning}"

        return prompt

    def parse_tool_call(self, response: str) -> dict:
        """
        Parse LLM output to extract tool call.

        Delegates to ToolRegistry.parse_tool_call().

        Args:
            response: Raw LLM response string

        Returns:
            Parsed tool call dict with 'thinking', 'tool', and 'tool_args' keys
        """
        return self.tool_registry.parse_tool_call(response)

    async def execute_tool(self, tool_call: dict) -> dict:
        """
        Execute a tool and return its result.

        Args:
            tool_call: Dict with 'tool' name and 'tool_args'

        Returns:
            Tool execution result dict
        """
        tool_name = tool_call.get('tool')
        tool_args = tool_call.get('tool_args', {})

        tool = self.tool_registry.get(tool_name)
        if tool is None:
            return {'success': False, 'error': f'Unknown tool: {tool_name}'}

        try:
            return await tool.execute(tool_args)
        except Exception as e:
            logger.error(f"Tool {tool_name} execution error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def update_context(self, tool_call: dict, result: dict):
        """
        Add tool call and result to conversation context.

        Updates last_tool_result and records to tool call history.

        Args:
            tool_call: The tool call that was executed
            result: The result from tool execution
        """
        self.last_tool_result = {
            'tool': tool_call.get('tool'),
            'args': tool_call.get('tool_args', {}),
            'result': result,
        }

        # Record for dead loop detection (keep last 10)
        self.last_tool_calls.append({
            'tool': tool_call.get('tool'),
            'args': tool_call.get('tool_args', {}),
        })
        if len(self.last_tool_calls) > 10:
            self.last_tool_calls = self.last_tool_calls[-10:]

        # Log to working memory if available
        if self.memory_manager and hasattr(self.memory_manager, 'log'):
            try:
                tool_name = tool_call.get('tool', 'unknown')
                success = result.get('success', False)
                self.memory_manager.log(
                    entry_type='action',
                    content=f"Used tool '{tool_name}': {'success' if success else 'failed'}",
                    detail=json.dumps(result, ensure_ascii=False)[:500],
                )
            except Exception as e:
                logger.debug(f"Failed to log to working memory: {e}")

    def enqueue_chat(self, player: str, message: str):
        """
        Enqueue a chat message for processing in the next loop iteration.

        Called by brain_coordinator when a chat message arrives from JS.

        Args:
            player: Player name
            message: Chat message content
        """
        try:
            self.chat_queue.put_nowait({'player': player, 'message': message})
            logger.info(f"Chat enqueued from {player}: {message[:50]}")
        except asyncio.QueueFull:
            logger.warning(f"Chat queue full, dropping message from {player}")

    # ========== Internal Helpers ==========

    def _drain_chat_queue(self) -> str:
        """Drain all pending chat messages and format them."""
        messages = []
        while not self.chat_queue.empty():
            try:
                msg = self.chat_queue.get_nowait()
                player = msg.get('player', 'Unknown')
                content = msg.get('message', '')
                messages.append(f"[{player}]: {content}")
            except asyncio.QueueEmpty:
                break

        return '\n'.join(messages)

    def _check_repeat_calls(self) -> str:
        """
        Check if the agent is making repeated identical tool calls.

        Returns warning message if detected, empty string otherwise.
        """
        if len(self.last_tool_calls) < 3:
            return ''

        # Check last 3 calls
        recent = self.last_tool_calls[-3:]
        if all(
            c['tool'] == recent[0]['tool'] and
            json.dumps(c['args'], sort_keys=True) == json.dumps(recent[0]['args'], sort_keys=True)
            for c in recent
        ):
            tool_name = recent[0]['tool']
            return (
                f"你已经连续 3 次调用了相同的工具 '{tool_name}' 并使用相同的参数。"
                f"请尝试不同的方法或工具。"
            )

        return ''
