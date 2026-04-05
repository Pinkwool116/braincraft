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
from prompts.prompt_logger import PromptLogger

logger = logging.getLogger(__name__)


class AgentLoopLayer:
    """
    Main decision loop — the 'thinking' layer of the agent.

    Runs a loop: build_prompt → LLM → parse_tool_call → execute_tool → update_context → repeat
    """

    def __init__(self, shared_state, execution_layer, tool_registry, config, llm_model,
                 prompt_manager, task_manager, memory_manager=None, todolist_manager=None,
                 chat_log_manager=None):
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
            todolist_manager: TodoListManager for todolist.md access
            chat_log_manager: ChatLogManager for persisting received player messages
        """
        self.shared_state = shared_state
        self.execution_layer = execution_layer
        self.tool_registry = tool_registry
        self.config = config
        self.llm = llm_model
        self.prompt_manager = prompt_manager
        self.task_manager = task_manager
        self.memory_manager = memory_manager
        self.todolist_manager = todolist_manager
        self.chat_log_manager = chat_log_manager

        # Config parameters
        loop_config = config.get('agent_loop', {})
        self.idle_interval = loop_config.get('idle_interval_seconds', 30)

        # State
        self.running = False
        self.chat_queue = asyncio.Queue()
        self.last_tool_result = None
        self.last_tool_calls: List[dict] = []  # Recent calls for dead loop detection

        # Interrupt watch: wake_event is set when new chat arrives during tool execution
        self.wake_event = asyncio.Event()
        self.INTERRUPTIBLE_TOOLS = {'execute_step', 'wait'}

        # Prompt Logger
        agent_name = config.get('agent_name', 'BrainyBot')
        enable_logging = config.get('enable_prompt_logging', True)  # default true or use config
        self.prompt_logger = PromptLogger(
            base_dir=config.get('bots_dir', 'bots'),
            agent_name=agent_name, 
            enabled=enable_logging
        )

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
                # Build prompt
                prompt = await self.build_prompt()

                # Log the prompt
                prompt_file = self.prompt_logger.log_prompt(
                    prompt=prompt,
                    brain_layer="AgentLoop",
                    prompt_type="decision_loop"
                )

                # Call LLM
                messages = [{"role": "user", "content": prompt}]
                response = await self.llm.send_request(messages)

                # Update prompt log with response
                if prompt_file and response:
                    self.prompt_logger.update_response(prompt_file, response)

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

                # Execute tool (with interrupt watch for long-running tools)
                tool_name = tool_call.get('tool')
                if tool_name in self.INTERRUPTIBLE_TOOLS:
                    result = await self._execute_with_interrupt_watch(tool_call)
                else:
                    result = await self.execute_tool(tool_call)

                # Update context
                self.update_context(tool_call, result)

                # Memory maintenance: consolidate if needed
                await self._maybe_consolidate()

                # Memory maintenance: crystallize if task was just cleared
                await self._maybe_crystallize(tool_call, result)

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

        # Keep working memory context synced with current task
        self._sync_task_context(task_content)

        # Drain chat queue
        pending_chat = self._drain_chat_queue()

        # Format last tool result
        if self.last_tool_result:
            last_result_str = json.dumps(self.last_tool_result, ensure_ascii=False, indent=2)
        else:
            last_result_str = "无（这是第一轮决策）"

        # Detect repeated tool calls
        repeat_warning = self._check_repeat_calls()

        # Load SOUL from config or soul.md file
        if not hasattr(self, '_soul_content') or not self._soul_content:
            soul_content = self.config.get('soul', '')
            if not soul_content:
                try:
                    import os
                    soul_path = os.path.join(self.prompt_manager.prompts_dir, 'agent_loop', 'soul.md')
                    if os.path.exists(soul_path):
                        with open(soul_path, 'r', encoding='utf-8') as f:
                            soul_content = f.read()
                    else:
                        soul_content = "你是一个专业、乐于助人的 Minecraft 智能体。你的主要职责是根据玩家的指示在游戏世界中执行任务。请根据所给的游戏状态聪明地决策。"
                except Exception as e:
                    logger.error(f"Failed to load soul.md: {e}")
                    soul_content = ""
            self._soul_content = soul_content

        # Read todolist file
        todolist_content = self.todolist_manager.read() if self.todolist_manager else ''

        # Read recent chat history
        chat_history = self.chat_log_manager.get_recent() if self.chat_log_manager else ''

        # Build context for prompt rendering
        context = {
            'state': state,
            'agent_name': state.get('agent_name', 'BrainyBot'),
            'memory_manager': self.memory_manager,
            # Direct values for agent_loop/system.md
            'TASK_FILE': task_content if task_content else "(编码草稿板为空)",
            'TODOLIST_FILE': todolist_content if todolist_content else "(待办清单为空)",
            'PENDING_CHAT': pending_chat if pending_chat else "(无新消息)",
            'CHAT_HISTORY': chat_history if chat_history else "(无聊天记录)",
            'TOOL_DESCRIPTIONS': self.tool_registry.get_tool_descriptions(),
            'LAST_TOOL_RESULT': last_result_str,
            'SOUL': self._soul_content,
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

        Updates last_tool_result, records to tool call history,
        and logs a rich entry to working memory.
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

        # Log to working memory with rich context
        if self.memory_manager and hasattr(self.memory_manager, 'log'):
            try:
                self._log_to_working_memory(tool_call, result)
            except Exception as e:
                logger.debug(f"Failed to log to working memory: {e}")

    def _log_to_working_memory(self, tool_call: dict, result: dict):
        """Build and append a rich working memory entry for this tool call."""
        tool_name = tool_call.get('tool', 'unknown')
        thinking = tool_call.get('thinking', '')
        tool_args = tool_call.get('tool_args', {})
        success = result.get('success', True)

        metadata = {'thinking': thinking[:300]} if thinking else None

        if tool_name == 'execute_step':
            step_desc = tool_args.get('step_description', '')
            status = '成功' if success else '失败'
            detail_parts = [f"结果: {status}"]
            if result.get('output'):
                detail_parts.append(f"输出: {result['output'][:300]}")
            if not success and result.get('error'):
                detail_parts.append(f"错误: {result['error'][:300]}")
            self.memory_manager.log(
                entry_type='action',
                content=f"执行步骤: {step_desc}",
                detail='\n'.join(detail_parts),
                metadata=metadata,
            )

        elif tool_name == 'chat':
            message = tool_args.get('message', '')
            self.memory_manager.log(
                entry_type='interaction',
                content=f"发送消息: {message}",
                metadata=metadata,
            )

        elif tool_name == 'recall_memory':
            query = tool_args.get('query', '')
            memories = result.get('memories', '')
            self.memory_manager.log(
                entry_type='reasoning',
                content=f"查询记忆: {query}",
                detail=memories[:300] if memories else None,
                metadata=metadata,
            )

        elif tool_name == 'update_task':
            action = tool_args.get('action', 'write')
            content_preview = str(tool_args.get('content', ''))[:100]
            self.memory_manager.log(
                entry_type='reasoning',
                content=f"更新任务文件 (action={action}): {content_preview}",
                metadata=metadata,
            )

        elif tool_name == 'wait':
            seconds = tool_args.get('seconds', 10)
            self.memory_manager.log(
                entry_type='reasoning',
                content=f"主动等待 {seconds} 秒",
                metadata=metadata,
            )

        elif tool_name == 'todolist':
            action = tool_args.get('action', 'read')
            content_preview = str(tool_args.get('content', ''))[:100]
            self.memory_manager.log(
                entry_type='reasoning',
                content=f"管理待办清单 (action={action}): {content_preview}",
                metadata=metadata,
            )

        elif tool_name == 'interrupt_execution':
            self.memory_manager.log(
                entry_type='action',
                content='中断代码执行',
                detail=json.dumps(result, ensure_ascii=False)[:200],
                metadata=metadata,
            )

        else:
            self.memory_manager.log(
                entry_type='action',
                content=f"调用工具 '{tool_name}'",
                detail=json.dumps(result, ensure_ascii=False)[:300],
                metadata=metadata,
            )

    # ========== Interrupt Watch ==========

    async def _execute_with_interrupt_watch(self, tool_call: dict) -> dict:
        """
        Execute a long-running tool while monitoring wake_event for incoming messages.

        When a chat message arrives during execution, calls a lightweight LLM
        to decide whether to interrupt (stop current action) or just chat
        (reply without stopping).

        Args:
            tool_call: The tool call dict to execute

        Returns:
            Tool execution result dict
        """
        self.wake_event.clear()
        tool_task = asyncio.create_task(self.execute_tool(tool_call))

        while not tool_task.done():
            wake_task = asyncio.create_task(self.wake_event.wait())

            done, _ = await asyncio.wait(
                [tool_task, wake_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            if tool_task in done:
                wake_task.cancel()
                return tool_task.result()

            # Woken up by incoming message
            self.wake_event.clear()
            pending_chat = self._drain_chat_queue()
            if not pending_chat:
                continue  # Spurious wake (message already consumed elsewhere)

            logger.info(f"Interrupt watch: evaluating incoming chat during {tool_call.get('tool')}")
            decision = await self._evaluate_interruption(tool_call, pending_chat)

            if decision.get('action') == 'interrupt':
                # Interrupt current tool execution
                result = await self._interrupt_current_tool(tool_task)
                # Send reply message
                if decision.get('chat_message'):
                    await self.execution_layer.send_chat(decision['chat_message'])
                return result

            elif decision.get('action') == 'chat':
                # Reply without interrupting — continue waiting for tool_task
                if decision.get('chat_message'):
                    await self.execution_layer.send_chat(decision['chat_message'])

        return tool_task.result()

    async def _evaluate_interruption(self, current_tool_call: dict, pending_chat: str) -> dict:
        """
        Lightweight LLM call to decide whether to interrupt the current action.

        Args:
            current_tool_call: The currently executing tool call
            pending_chat: Formatted pending chat messages

        Returns:
            {'action': 'interrupt'|'chat', 'chat_message': str}
        """
        current_action = current_tool_call.get('thinking', '')
        tool_name = current_tool_call.get('tool')
        if tool_name == 'execute_step':
            step_desc = current_tool_call.get('tool_args', {}).get('step_description', '')
            current_action += f" (正在执行: {step_desc})"
        elif tool_name == 'wait':
            seconds = current_tool_call.get('tool_args', {}).get('seconds', '')
            current_action += f" (正在等待 {seconds} 秒)"

        # Load soul if not cached yet
        if not hasattr(self, '_soul_content') or not self._soul_content:
            self._soul_content = ''

        context = {
            'CURRENT_ACTION': current_action,
            'PENDING_MESSAGES': pending_chat,
            'SOUL': self._soul_content,
            'agent_name': self.config.get('agent_name', 'BrainyBot'),
        }

        try:
            prompt = await self.prompt_manager.render(
                'agent_loop/interruption.md', context=context, strict=False
            )

            messages = [{"role": "user", "content": prompt}]
            response = await self.llm.send_request(messages)

            return self._parse_interruption_response(response)
        except Exception as e:
            logger.error(f"Interruption evaluation failed: {e}", exc_info=True)
            # Default: don't interrupt on error
            return {'action': 'chat', 'chat_message': ''}

    def _parse_interruption_response(self, response: str) -> dict:
        """
        Parse the interruption LLM's JSON response.

        Expected format: {"action": "interrupt"|"chat", "chat_message": "..."}

        Args:
            response: Raw LLM response string

        Returns:
            Parsed decision dict
        """
        import re

        if not response:
            return {'action': 'chat', 'chat_message': ''}

        try:
            text = response.strip()
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                parsed = json.loads(json_match.group())
                action = parsed.get('action', 'chat')
                if action not in ('interrupt', 'chat'):
                    action = 'chat'
                return {
                    'action': action,
                    'chat_message': parsed.get('chat_message', '')
                }
        except Exception as e:
            logger.warning(f"Failed to parse interruption response: {e}")

        return {'action': 'chat', 'chat_message': ''}

    async def _interrupt_current_tool(self, tool_task: asyncio.Task) -> dict:
        """
        Interrupt the currently running tool execution.

        For execute_step: triggers the JS interrupt mechanism first.
        For all tools: cancels the asyncio task.

        Args:
            tool_task: The asyncio task running the tool

        Returns:
            Tool result dict (possibly with interrupted error)
        """
        logger.info("Interrupting current tool execution")

        # If JS code is executing, trigger the interrupt mechanism
        if self.execution_layer.is_executing:
            await self.execution_layer.interrupt()

        # Cancel the asyncio task
        tool_task.cancel()
        try:
            return await tool_task
        except asyncio.CancelledError:
            return {'success': False, 'error': 'Interrupted by player message'}

    # ========== Chat Queue ==========

    def enqueue_chat(self, player: str, message: str):
        """
        Enqueue a chat message for processing in the next loop iteration.

        Called by brain_coordinator when a chat message arrives from JS.
        Also signals wake_event to interrupt long-running tools.

        Args:
            player: Player name
            message: Chat message content
        """
        try:
            self.chat_queue.put_nowait({'player': player, 'message': message})
            self.wake_event.set()  # Wake up interrupt watch if active
            logger.info(f"Chat enqueued from {player}: {message[:50]}")
        except asyncio.QueueFull:
            logger.warning(f"Chat queue full, dropping message from {player}")

    # ========== Internal Helpers ==========

    def _drain_chat_queue(self) -> str:
        """Drain all pending chat messages, persist them to chat log, and format for prompt."""
        messages = []
        while not self.chat_queue.empty():
            try:
                msg = self.chat_queue.get_nowait()
                player = msg.get('player', 'Unknown')
                content = msg.get('message', '')
                messages.append(f"[{player}]: {content}")
                # Persist to chat log
                if self.chat_log_manager:
                    self.chat_log_manager.append(player, content)
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

    async def _maybe_consolidate(self):
        """Trigger working memory rolling consolidation if threshold reached."""
        if not self.memory_manager:
            return
        try:
            if self.memory_manager.should_consolidate():
                logger.debug("Triggering working memory consolidation...")
                await self.memory_manager.consolidate(self.llm)
        except Exception as e:
            logger.debug(f"Working memory consolidation failed: {e}")

    async def _maybe_crystallize(self, tool_call: dict, result: dict):
        """
        Trigger crystallize (working memory → long-term graph) when task is cleared.

        Crystallize when the agent calls update_task with action='clear', or
        writes empty content — meaning the current task episode has ended.
        """
        if not self.memory_manager:
            return
        tool_name = tool_call.get('tool')
        if tool_name != 'update_task':
            return
        action = tool_call.get('tool_args', {}).get('action', '')
        content = tool_call.get('tool_args', {}).get('content', '')
        if action == 'clear' or (action == 'write' and not content.strip()):
            try:
                logger.info("Task cleared — crystallizing working memory to long-term graph...")
                await self.memory_manager.crystallize(self.llm)
            except Exception as e:
                logger.warning(f"Memory crystallize failed: {e}")

    def _sync_task_context(self, task_content: str):
        """Keep working memory context.goal in sync with the current task.md content."""
        if not self.memory_manager:
            return
        try:
            wm = self.memory_manager.working_memory
            goal = task_content.strip()[:300] if task_content.strip() else '（空闲）'
            if wm.context.get('goal') != goal:
                wm.context['goal'] = goal
        except Exception:
            pass
