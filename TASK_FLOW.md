# 任务执行流程说明

## 概述

三层大脑系统中，任务有两个来源：
1. **高层大脑自动生成的任务计划**（战略目标）
2. **玩家通过聊天发送的任务请求**（即时任务）

## 详细流程

### 1. 高层大脑自动生成任务

**触发条件**：
- Bot 进入游戏后立即触发一次
- 之后每 5-15 分钟周期性检查
- 当前任务计划状态为 `idle` 或 `completed` 时

**流程**：
```
高层大脑周期性唤醒
  ↓
检查 task_plan.status
  ↓
status == 'idle' 或 'completed'？
  ↓ 是
生成战略计划 (_generate_strategic_plan)
  ↓
使用 LLM 分析当前状态
  - 健康、食物、库存
  - 环境（生物群系、时间）
  - 已学习的经验
  ↓
返回战略目标（如 "Exploration and gathering"）
  ↓
创建任务计划 (create_task_plan)
  ↓
使用 LLM 将目标分解为 5-15 个步骤
  ↓
保存到 shared_state['task_plan']
  {
    'status': 'active',
    'goal': '探索和收集资源',
    'current_step_index': 0,
    'steps': [
      {'id': 1, 'description': '寻找树木', 'status': 'pending'},
      {'id': 2, 'description': '收集木头', 'status': 'pending'},
      ...
    ]
  }
  ↓
中层大脑每秒检测到 task_plan 存在
  ↓
开始执行步骤
```

### 2. 玩家发送任务请求

**触发条件**：
- 玩家在聊天中发送包含动作关键词的消息
- 例如："go collect some wood"、"mine stone"、"build a house"

**流程**：
```
玩家发送聊天消息
  ↓
minecraft_bridge.js 接收并发送到 Python
  ↓
brain_coordinator 将消息放入 chat_queue
  ↓
中层大脑检测到 chat_queue 有消息（优先级最高）
  ↓
_handle_pending_chat(chat_data)
  ↓
调用 _is_action_request(message) [使用 LLM 异步判断]
  ↓
是动作请求？
  ↓ 是
_create_task_from_chat(player, message)
  - 使用 LLM 将聊天转换为任务描述
  - 例："go collect some wood" → "collect 10 oak logs"
  ↓
向高层大脑请求添加步骤
  _request_modification('add_step', ...)
  **同时传递玩家名字用于关系判断**
  ↓
设置 is_waiting_for_guidance = True
  ↓
发送确认消息给玩家："Okay {player}, I'll work on that"
  ↓
等待高层大脑响应
  ↓
高层大脑被唤醒（事件驱动）
  ↓
handle_modification_request(mod_request)
  **读取玩家数据（relationship, trust_level, interactions, personality, preferences）**
  **提供给 LLM 作为信息，不做显式判断指导**
  ↓
  - 使用 LLM 评估请求的合理性
  - LLM 会根据提供的信息自主决定
  - 决定：approve / revise / reject
  ↓
如果 approve：
  将新步骤添加到 task_plan.steps
  ↓
将响应写入 shared_state['modification_response']
  ↓
中层大脑检测到响应
  ↓
_handle_guidance_response(response)
  ↓
继续执行任务
```

### 3. 中层执行步骤

**每秒执行的优先级系统**：

```python
async def process(self):
    # 优先级 1: 聊天消息（可打断任务）
    if chat_queue:
        await _handle_pending_chat()
        return
    
    # 优先级 2: 等待高层指导
    if is_waiting_for_guidance:
        if modification_response:
            await _handle_guidance_response()
        return
    
    # 优先级 3: 执行任务计划
    await _process_task_plan()
```

**执行单个步骤（类似原项目 self-prompter 逻辑）**：

```
_process_task_plan()
  ↓
读取 task_plan.steps[current_step_index]
  ↓
_execute_step_with_retry(step, index)
  ↓
循环最多 5 次尝试：
  ↓
  _generate_code_for_step(step)
    **【Self-Prompter 逻辑】**
    - 使用 LLM 生成 JavaScript 代码
    - 提供技能库文档作为上下文
    - 提供当前游戏状态
    
    **【对话历史反馈循环】**
    - 维护 messages 数组记录每次尝试
    - 如果代码验证失败：
      → 将错误信息添加到 messages
      → LLM 看到之前的错误和代码
      → 生成改进版本
    - 如果代码执行失败：
      → 将执行错误添加到 messages
      → LLM 根据错误调整策略
      → 再次生成代码
    
    **类似原项目 self_prompter.js 的循环机制**
  ↓
  发送代码到 minecraft_bridge.js 执行
  ↓
  等待执行结果
  ↓
  成功？
    ↓ 是
    标记步骤为 'completed'
    task_plan.current_step_index++
    返回 success
    ↓ 否
    记录错误
    重试次数 < 5？
      ↓ 是
      **将错误反馈给 LLM，继续循环**
      ↓ 否
      使用 LLM 评估失败原因
        - retry: 继续重试
        - modify: 向高层请求修改步骤
        - abort: 放弃该步骤
```

## 异步调用说明

### Self-Prompter 逻辑对比

**原项目 (self_prompter.js)**:
- 循环向 agent 发送提示
- 每次等待 agent 响应并执行命令
- 如果连续 3 次没有使用命令则停止
- 使用 `cooldown` 控制循环间隔

**三层大脑 (mid_level_brain.py)**:
- 类似的重试循环机制（最多 5 次）
- 维护 **messages 数组** 记录对话历史
- 每次失败后将错误反馈给 LLM
- LLM 看到之前的尝试和错误，生成改进版本
- 更智能的失败处理：验证错误 vs 执行错误

**关键改进**：
```python
# 原项目：简单的成功/失败判断
used_command = await handleMessage(msg)
if (!used_command) no_command_count++

# 三层大脑：对话历史反馈
messages.append({'role': 'assistant', 'content': response})
messages.append({'role': 'system', 'content': f'ERROR: {error}'})
# 下次生成时 LLM 会看到这些历史
```

### 当前的异步调用

1. **所有 LLM 调用都是异步的**：
   ```python
   response = await self.llm.send_request([], prompt)
   ```

2. **判断是否为动作请求**（已修复为异步）：
   ```python
   async def _is_action_request(self, message: str) -> bool:
       # 使用 LLM 异步判断
       response = await self.llm.send_request([], prompt)
       return 'yes' in response.lower()
   ```

3. **生成聊天回复**（异步）：
   ```python
   async def _generate_chat_response(self, player: str, message: str) -> str:
       response = await self.llm.send_request([], prompt)
       return response.strip()
   ```

4. **代码生成**（异步）：
   ```python
   async def _generate_code_for_step(self, task: Dict[str, Any]) -> str:
       response = await self.llm.send_request([], prompt)
       return extracted_code
   ```

### 为什么使用异步

1. **非阻塞执行**：LLM 请求可能需要几秒钟，异步调用允许其他任务继续运行
2. **并发处理**：可以同时等待多个 LLM 响应
3. **响应性**：即使在等待 LLM 时，bot 仍然可以响应聊天、处理伤害等

## 任务来源的协调

### 两种任务的关系

1. **高层任务计划**：长期战略目标，持续执行
2. **玩家任务请求**：即时任务，通过 `add_step` 插入到当前计划中

**协调机制**：
- 玩家任务被添加到 task_plan.steps 数组中
- 插入位置：当前步骤之后（`step_index + 1`）
- 执行顺序：按 steps 数组顺序依次执行
- 打断机制：聊天消息到达时会立即打断当前执行

**示例场景**：

```
初始状态（高层生成的计划）：
  steps: [
    1. 探索周围环境 ← current_step_index = 0 (正在执行)
    2. 寻找树木
    3. 收集木头
  ]

玩家发送："mine some stone"
  ↓
中层判断为动作请求
  ↓
向高层请求添加步骤："mine 10 cobblestone"
  ↓
高层批准并插入
  ↓
更新后的计划：
  steps: [
    1. 探索周围环境 ← current_step_index = 0 (刚完成)
    2. mine 10 cobblestone ← 新插入的步骤
    3. 寻找树木
    4. 收集木头
  ]
  ↓
中层继续执行，下一步会执行 "mine 10 cobblestone"
```

## 关键代码位置

- **高层生成战略计划**：`high_level_brain.py:_generate_strategic_plan()`
- **高层创建任务计划**：`high_level_brain.py:create_task_plan()`
- **高层处理修改请求**：`high_level_brain.py:handle_modification_request()` [含玩家关系判断]
- **中层优先级处理**：`mid_level_brain.py:process()`
- **聊天处理**：`mid_level_brain.py:_handle_pending_chat()`
- **判断动作请求**：`mid_level_brain.py:_is_action_request()` [异步]
- **执行步骤**：`mid_level_brain.py:_execute_step_with_retry()`
- **代码生成**：`mid_level_brain.py:_generate_code_for_step()` [异步]
- **玩家数据管理**：`memory_manager.py:get_player_data()`

## 玩家关系系统

### 架构一致性设计

遵循三层大脑的职责分工：
- **中层大脑（观察者）**：记录玩家互动事实
- **高层大脑（分析者）**：周期性分析并更新关系

### 数据结构

每个玩家的信息存储在 `bots/{agent_name}/players.json`：

```json
{
  "PlayerName": {
    "first_met": "2025-01-29T10:30:00",
    "personality": ["friendly", "helpful"],
    "preferences": ["likes building", "prefers daytime"],
    "interactions": [
      {"timestamp": "...", "content": "chat: hello"}
    ],
    "relationship": "friendly",  // neutral, friendly, hostile
    "trust_level": 0.8  // 0.0 - 1.0
  }
}
```

### 更新机制

#### 1. 中层记录事实（不做判断）

当玩家互动发生时，中层只记录到 memory_manager：

```python
# 玩家发送聊天
self.memory_manager.update_player_info(player, 'interaction', f"chat: {msg}")

# 完成玩家任务
self.memory_manager.update_player_info(player, 'interaction', f"completed: {task}")
```

#### 2. 高层周期性分析

**时机 A：每 5-15 分钟的战略规划**

高层在 `_generate_strategic_plan()` 时，LLM 会看到 `$PLAYERS_INFO`（所有玩家及其互动记录），并在 JSON 响应中返回：

```json
{
  "goal_priority": "...",
  "player_relationship_updates": [
    {
      "player_name": "PlayerA",
      "trust_delta": +0.1,
      "new_relationship": "friendly",
      "reason": "Helped complete task"
    }
  ]
}
```

**时机 B：处理玩家任务请求时**（未来可实现）

在 `handle_modification_request()` 中，如果 `player_name` 存在，LLM 可以立即更新关系。

#### 3. 高层应用更新

```python
# 从 LLM 响应提取
for update in plan['player_relationship_updates']:
    player = update['player_name']
    trust_delta = update['trust_delta']
    new_rel = update['new_relationship']
    
    # 直接修改 memory_manager 数据
    old_trust = self.memory_manager.players[player]['trust_level']
    new_trust = max(0.0, min(1.0, old_trust + trust_delta))
    self.memory_manager.players[player]['trust_level'] = new_trust
    
    if new_rel:
        self.memory_manager.players[player]['relationship'] = new_rel
    
    # 保存到磁盘
    self.memory_manager._save_json(...)
```

### 优势

1. **架构一致性**：
   - 中层只观察和记录
   - 高层做分析和决策
   - 与经验总结机制一致

2. **智能化**：
   - LLM 根据完整上下文自主分析
   - 不是硬编码规则（如固定 +0.1）
   - LLM 决定信任度变化幅度

3. **周期性批处理**：
   - 不是每次互动都立即更新
   - 在沉思时统一分析多个玩家
   - 减少频繁的 LLM 调用

### 关系更新示例

玩家 "Steve" 帮助智能体完成采集任务：

1. **中层记录**（即时）：
   ```python
   memory_manager.update_player_info("Steve", "interaction", "helped collect wood")
   ```

2. **高层分析**（5-15分钟后）：
   ```
   LLM 看到：
   - Steve: 3 interactions
   - Recent: "helped collect wood"
   - Current trust: 0.5
   
   LLM 返回：
   {
     "player_name": "Steve",
     "trust_delta": +0.15,
     "new_relationship": "friendly",
     "reason": "Steve helped us with task, showing cooperation"
   }
   ```

3. **应用更新**：
   ```
   Trust: 0.5 → 0.65
   Relationship: neutral → friendly
   ```

### 关系更新（待实现）

未来可以根据互动结果更新关系：
- 成功完成任务 → trust_level += 0.1
- 玩家攻击智能体 → trust_level -= 0.3, relationship = 'hostile'
- 玩家给予物品 → trust_level += 0.2, relationship = 'friendly'

## 调试技巧

1. 查看日志中的 "Executing task plan step X/Y"
2. 查看 `bots/BrainyBot/learned_experience.json` 了解失败记录
3. 检查 `modification_request` 和 `modification_response` 的内容
4. 观察 `chat_queue` 的处理顺序
5. **查看 `bots/BrainyBot/players.json` 了解玩家关系数据**
