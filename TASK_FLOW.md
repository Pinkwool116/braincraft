# 任务执行流程说明

## 概述

三层大脑系统采用**任务栈 (Task Stack)** 管理所有任务。任务有两个主要来源：

1. **高层大脑自动生成的战略任务**（内部任务）
2. **玩家通过聊天发送的任务请求**（玩家任务）

所有任务都被组织为 LIFO（后进先出）栈结构，新任务自动获得最高优先级。

---

## 核心概念

### 任务栈 (Task Stack)

任务栈是一个后进先出（LIFO）的数据结构：

```python
task_stack = [
    {
        "goal": "探索并收集资源",      # 基础任务
        "steps": [...],
        "status": "paused",           # 被更高优先级任务中断
        "source": "internal",
        "current_step_index": 2
    },
    {
        "goal": "为玩家建造庇护所",    # 玩家任务
        "steps": [...],
        "status": "paused",           # 被子任务中断
        "source": "player",
        "player_name": "Steve"
    },
    {
        "goal": "收集 20 个木头",      # 当前执行的子任务
        "steps": [...],
        "status": "active",           # 栈顶任务总是 active
        "source": "internal"
    }
]
```

**关键规则**:
- **栈顶任务** (`task_stack[-1]`): 永远是当前执行的任务
- **压栈 (Push)**: 新任务压入栈顶，当前任务自动变为 `paused`
- **弹栈 (Pop)**: 栈顶任务完成后弹出，新的栈顶任务自动变为 `active`

---

## 详细流程

### 1. 高层大脑自动生成任务

**触发条件**：
- Bot 进入游戏后立即触发一次
- 之后每 10 分钟周期性检查
- 任务栈为空时

**流程**：
```
高层大脑周期性唤醒 (每10分钟)
  ↓
检查 task_stack 是否为空
  ↓
为空？
  ↓ 是
生成战略目标 (_generate_strategic_plan)
  ↓
使用 LLM 分析当前状态:
  - 健康、食物、库存
  - 环境（生物群系、时间）
  - 已学习的经验
  - 人生愿景和长期目标
  ↓
返回战略目标（如 "探索并收集基础资源"）
和战略指导（如 "优先收集木头和石头"）
  ↓
调用 TaskPlanner.decompose_goal_to_steps()
  ↓
使用 LLM 将目标分解为 3-12 个步骤:
  输入：
    - goal: "探索并收集基础资源"
    - strategic_guidance: "优先收集木头和石头"
    - 当前状态（位置、库存等）
    - 历史经验
  输出：
    steps = [
      {"id": 1, "description": "寻找附近的树木", "status": "pending"},
      {"id": 2, "description": "收集 20 个橡木原木", "status": "pending"},
      {"id": 3, "description": "寻找石头矿脉", "status": "pending"},
      ...
    ]
  ↓
创建 task_plan 对象:
  {
    'goal': '探索并收集基础资源',
    'steps': steps,
    'current_step_index': 0,
    'status': 'active',
    'source': 'internal'
  }
  ↓
压栈: task_stack_manager.push_task(task_plan)
  ↓
同步到 shared_state['active_task']
  ↓
中层大脑在下一个周期检测到 active_task
  ↓
开始执行步骤
```

### 2. 玩家发送任务请求

**触发条件**：
- 玩家在聊天中发送包含动作关键词的消息
- 例如："帮我建个房子"、"收集一些木头"、"去挖矿"

**流程**：
```
玩家发送聊天消息
  ↓
minecraft_bridge.js 接收并发送到 Python
  ↓
brain_coordinator 将消息放入 chat_queue
  ↓
coordinator 调用 mid_brain.handle_pending_chat(chat_data)
  ↓
_is_action_request(message) [使用 LLM 异步判断]
  ↓
是任务请求？
  ↓ 是
解析任务意图:
  输入: "帮我建个房子"
  输出: "建造一个基本的木质庇护所"
  ↓
构建 modification_request:
  {
    "type": "player_directive",
    "player_name": "Steve",
    "directive": "帮我建个房子",
    "parsed_goal": "建造一个基本的木质庇护所"
  }
  ↓
写入 shared_state['modification_request']
  ↓
触发 wake_event（立即唤醒高层）
  ↓
设置 is_waiting_for_guidance = True
  ↓
发送确认消息给玩家："好的 Steve，我会帮你建造"
  ↓
等待高层响应
  ↓
高层大脑被事件驱动唤醒（< 100ms）
  ↓
读取 modification_request
  ↓
调用 TaskHandler.handle_player_directive(request)
  ↓
评估是否接受:
  - 读取玩家数据 (relationship, trust_level)
  - 评估当前任务重要性
  - LLM 自主决策
  ↓
决策: ACCEPT 或 REJECT
  ↓
如果 ACCEPT:
  1. 调用 TaskPlanner.decompose_goal_to_steps()
     将 "建造庇护所" 分解为具体步骤
  
  2. 创建新 task_plan:
     {
       "goal": "建造一个基本的木质庇护所",
       "steps": [...],
       "status": "active",
       "source": "player",
       "player_name": "Steve"
     }
  
  3. 压栈: task_stack_manager.push_task(new_task)
     - 当前栈顶任务（如果有）状态变为 'paused'
     - 新任务成为栈顶，状态为 'active'
  
  4. 构建响应:
     {
       "decision": "ACCEPT",
       "message": "我会为你建造庇护所",
       "new_task": {...}
     }
  ↓
如果 REJECT:
  {
    "decision": "REJECT",
    "reason": "我正在执行一个重要任务，稍后可以吗？"
  }
  ↓
写入 shared_state['modification_response']
  ↓
中层检测到响应
  ↓
_handle_guidance_response(response)
  ↓
is_waiting_for_guidance = False
  ↓
如果 ACCEPT:
  - 向玩家发送确认消息
  - 继续执行（现在是玩家任务）
  ↓
如果 REJECT:
  - 向玩家发送拒绝消息
  - 继续执行原任务
```

### 3. 中层执行任务步骤

**每秒执行的优先级系统**：

```python
async def process(self):
    # 优先级 1: 聊天消息（由 coordinator 直接调用）
    # 已在 coordinator 中处理
    
    # 优先级 2: 等待高层指导
    if is_waiting_for_guidance:
        mod_response = await shared_state.get('modification_response')
        if mod_response:
            await _handle_guidance_response(mod_response)
            is_waiting_for_guidance = False
        return  # 等待期间不执行任务
    
    # 优先级 3: 执行任务计划
    await _process_task_plan()
```

**执行单个步骤（带智能重试）**：

```
_process_task_plan()
  ↓
读取 active_task (栈顶任务)
  ↓
获取当前步骤:
  step = task.steps[task.current_step_index]
  ↓
如果 step.status == 'completed':
  return  # 已完成，跳过
  ↓
_execute_step_with_retry(step, max_retries=3)
  ↓
循环最多 3 次尝试：
  ↓
  _generate_code_for_step(step, messages)
    输入:
      - step.description: "收集 20 个橡木原木"
      - 当前游戏状态
      - 技能库文档
      - 历史对话（包含之前的错误）
    
    输出:
      JavaScript 代码:
      ```javascript
      const success = await skills.collectBlock(bot, 'oak_log', 20);
      if (!success) {
          throw new Error("Failed to collect oak logs");
      }
      log(bot, "Successfully collected 20 oak logs!");
      ```
  ↓
  发送代码到 minecraft_bridge.js 执行
  ↓
  等待执行结果
  ↓
  成功？
    ↓ 是
    标记步骤为 'completed'
    current_step_index++
    
    所有步骤都完成？
      ↓ 是
      通知高层: 任务完成
      高层弹栈: task_stack_manager.pop_task()
        - 弹出当前任务
        - 新的栈顶任务状态变为 'active'
      记录成功经验
      return SUCCESS
      
      ↓ 否
      继续执行下一步
    
    ↓ 否 (失败)
    记录错误信息
    将错误添加到 messages:
      messages.append({
        'role': 'system',
        'content': 'ERROR: No oak logs found nearby'
      })
    
    重试次数 < 3？
      ↓ 是
      继续循环（LLM 会看到错误，生成改进代码）
      
      ↓ 否
      构建 modification_request:
        {
          "type": "stuck_task",
          "current_task": {...},
          "failed_step": {...},
          "failure_count": 3,
          "recent_errors": [...]
        }
      
      发送到高层并等待响应
```

### 4. 高层处理"卡住的任务"

**中层连续失败 3 次后的流程**：

```
中层发送 modification_request (type: stuck_task)
  ↓
触发 wake_event（立即唤醒高层）
  ↓
高层大脑被唤醒（< 100ms）
  ↓
调用 TaskHandler.handle_stuck_task(request)
  ↓
准备上下文信息:
  - 任务栈摘要 (task_stack_summary)
  - 当前任务详情
  - 失败步骤
  - 失败原因和错误信息
  - 短期记忆（最近50条事件）
  - 历史经验教训
  ↓
LLM 分析并决策:
  提示词包含所有上下文
  LLM 输出决策
  ↓
决策类型（针对不同任务来源）:

如果 source == 'internal':
  1. REVISE_AND_REPLACE: 
     - 弹出当前任务
     - 创建修改后的任务
     - 压入栈顶
  
  2. ADD_SUB_TASK:
     - 保留当前任务（状态变为 paused）
     - 创建子任务（如 "制作更好的工具"）
     - 压入栈顶
  
  3. DISCARD_TASK:
     - 弹出并放弃当前任务
     - 恢复父任务（如果存在）
  
  4. REJECT_REQUEST:
     - 拒绝修改
     - 提供指导建议给中层
     - 中层继续重试

如果 source == 'player':
  1. REVISE_STEPS:
     - 修改当前任务的 steps
     - 保持 goal 不变
  
  2. DISCARD_AND_REPORT:
     - 弹出任务
     - 生成向玩家报告的理由
     - 中层发送消息给玩家
  
  3. ADD_SUB_TASK:
     - 保留玩家任务
     - 创建前置子任务
     - 压入栈顶
  
  4. REJECT_REQUEST:
     - 拒绝修改
     - 提供指导建议
  ↓
执行决策（如 ADD_SUB_TASK）:
  1. 调用 TaskPlanner.decompose_goal_to_steps()
     创建子任务的步骤
  
  2. 创建 sub_task_plan:
     {
       "goal": "制作石镐",
       "steps": [...],
       "status": "active",
       "source": "internal"
     }
  
  3. 压栈: task_stack_manager.push_task(sub_task)
     - 原任务状态变为 'paused'
     - 子任务成为栈顶
  
  4. 构建响应:
     {
       "decision": "ADD_SUB_TASK",
       "guidance": "先制作石镐再继续挖矿",
       "new_task": {...}
     }
  ↓
写入 shared_state['modification_response']
  ↓
中层检测到响应
  ↓
处理响应并继续执行（现在是子任务）
```

---

## 任务完成与恢复机制

### 任务完成流程

```
中层执行完栈顶任务的最后一步
  ↓
所有步骤的 status 都是 'completed'
  ↓
调用 task_stack_manager.pop_task()
  ↓
弹出栈顶任务:
  completed_task = task_stack.pop()
  ↓
如果 completed_task.source == 'player':
  向玩家发送完成消息:
  "Steve，我已经完成了你要求的庇护所！"
  ↓
记录成功经验到 learned_experience.json
  ↓
检查任务栈是否为空:
  
  如果为空:
    - active_task = None
    - 高层在下次周期会生成新目标
  
  如果不为空:
    - 新的栈顶任务状态从 'paused' 变为 'active'
    - 同步到 shared_state['active_task']
    - 中层在下个周期继续执行被恢复的任务
```

### 任务恢复示例

```
初始任务栈:
[
  {goal: "探索", status: "paused"},
  {goal: "建造庇护所", status: "paused"},
  {goal: "收集木头", status: "active"}  ← 栈顶
]

"收集木头" 完成
  ↓
弹栈后:
[
  {goal: "探索", status: "paused"},
  {goal: "建造庇护所", status: "active"}  ← 新的栈顶
]

中层继续执行 "建造庇护所"
  ↓
"建造庇护所" 完成
  ↓
弹栈后:
[
  {goal: "探索", status: "active"}  ← 新的栈顶
]

中层继续执行 "探索"
```

---

## 异步调用说明

### 所有 LLM 调用都是异步的

```python
# 判断是否为任务请求
is_task = await _is_action_request(message)

# 生成任务步骤
steps = await task_planner.decompose_goal_to_steps(goal)

# 生成执行代码
code = await _generate_code_for_step(step)

# 处理修改请求
response = await task_handler.handle_stuck_task(request)
```

### 为什么使用异步

1. **非阻塞执行**: LLM 请求可能需要几秒钟，异步调用允许其他任务继续运行
2. **并发处理**: 可以同时等待多个操作（如状态更新 + LLM 响应）
3. **响应性**: 即使在等待 LLM 时，bot 仍然可以响应聊天、处理伤害等

---

## 关键代码位置

### 高层大脑
- **生成战略目标**: `high_level_brain.py:_generate_strategic_plan()`
- **处理修改请求**: `high_level_brain.py:_route_modification_request()`
- **确保有活跃任务**: `high_level_brain.py:_ensure_active_task()`

### 任务栈管理
- **任务栈核心**: `task_stack/task_stack_manager.py`
- **任务规划器**: `task_stack/task_planner.py:decompose_goal_to_steps()`
- **修改请求处理**: `task_stack/task_handler.py`
  - `handle_stuck_task()`: 处理卡住的任务
  - `handle_player_directive()`: 处理玩家指令

### 中层大脑
- **优先级处理**: `mid_level_brain.py:process()`
- **聊天处理**: `mid_level_brain.py:_handle_pending_chat()`
- **判断任务请求**: `mid_level_brain.py:_is_action_request()` [异步]
- **执行步骤**: `mid_level_brain.py:_execute_step_with_retry()`
- **代码生成**: `mid_level_brain.py:_generate_code_for_step()` [异步]

### 持久化
- **任务栈持久化**: `task_stack/task_persistence.py`
- **心智状态管理**: `utils/mind_state_manager.py`
- **玩家数据管理**: `utils/memory_manager.py:get_player_data()`

---

## 调试技巧

### 查看任务栈状态

1. **实时日志**:
   ```
   Task stack top: 收集木头 (source=internal) - Step 2/5
   ```

2. **持久化文件**:
   ```bash
   cat bots/BrainyBot/mind_state.json | grep -A 20 "task_stack"
   ```

### 查看修改请求

观察日志中的:
```
⚠️ Processing modification request from mid-level
✅ Modification request processed: ADD_SUB_TASK
```

### 查看玩家关系

```bash
cat bots/BrainyBot/players.json
```

### 查看学习经验

```bash
cat bots/BrainyBot/learned_experience.json
```

---

## 规划中的功能：深度沉思系统 🌟

### 愿景

未来的沉思系统将使智能体具备真正的"内在生活"，不仅在执行任务时思考，也在空闲时进行自我成长。

### 沉思模式

**1. 经验总结 (Experience Consolidation)**
- 从成功和失败中提炼通用原则
- 发现跨任务的共性模式
- 示例输出："在没有工具时，应该先制作工作台，而不是尝试徒手采集"

**2. 社交反思 (Relationship Pondering)**
- 思考与玩家的互动
- 理解他人的意图和偏好
- 示例输出："Steve 总是请我建造，但从不要求战斗。他可能是一个和平主义者"

**3. 人生规划 (Existential Reflection)**
- 反思长期愿景和价值观
- 调整目标优先级
- 示例输出："我想成为一个优秀的建筑师。也许应该多花时间研究建筑技巧，而非盲目收集资源"

**4. 创造性连接 (Creative Linking)**
- 跨领域连接知识
- 产生创新想法
- 示例输出："如果把红石机关和农场结合，可以实现自动化收割？"

**5. 人格塑造 (Self-Awareness Evolution)**
- 反思个性特质
- 发展独特的行为风格
- 示例输出："我注意到自己倾向于谨慎规划。这让我少犯错，但可能错过一些机会"

### 技术设计

**异步执行**:
```python
# 沉思在后台运行，不阻塞紧急响应
if should_contemplate():
    asyncio.create_task(contemplation_manager.contemplate())
```

**智能触发条件**:
- 任务栈为空或只有低优先级任务
- 心智负荷不过载（`mental_fog < 0.7`）
- 距离上次沉思已超过最小间隔（如 1 小时）

**结果持久化**:
沉思产生的洞察自动保存到 `learned_experience.json`：
```json
{
  "insights": [
    {
      "type": "social_reflection",
      "content": "Steve 倾向于合作而非竞争",
      "timestamp": "2025-11-03T14:30:00",
      "confidence": 0.8
    }
  ]
}
```

### 应用场景

**AI Town 环境**:
- 复杂的多人社交互动
- 需要理解他人意图和建立关系
- 沉思帮助智能体从互动中学习社交规则

**长期生存世界**:
- 从经验中学习，避免重复错误
- 发展个人风格和策略偏好
- 随时间成长为更智能的存在

**人格演化**:
- 不同的智能体通过不同的经历发展出独特人格
- 从"任务执行者"进化为"有个性的伙伴"

---

## 总结

任务栈系统的核心优势：

1. **优雅的中断与恢复**: 完美支持"暂停-执行-恢复"的非线性任务流
2. **动态优先级**: 玩家任务或紧急子任务自动获得最高优先级
3. **智能求助**: 中层失败时高层提供战略级指导
4. **完全持久化**: 重启后无缝继续执行
5. **职责清晰**: 高层规划、中层执行、底层反射，各司其职
6. **[未来] 深度心智**: 沉思系统将赋予智能体自我成长和人格演化的能力

这套架构使 Agent 的行为模式更加动态、健壮和类人化，并为未来的高级认知功能奠定基础。
