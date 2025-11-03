# BrainCraft 架构文档

## 目录
- [架构概述](#架构概述)
- [核心创新](#核心创新)
- [三层大脑系统](#三层大脑系统)
- [任务栈管理](#任务栈管理)
- [高层大脑详解](#高层大脑详解)
- [中层大脑详解](#中层大脑详解)
- [底层大脑详解](#底层大脑详解)
- [修改请求机制](#修改请求机制)
- [数据流与通信](#数据流与通信)

---

## 架构概述

BrainCraft 是一个基于**三层大脑架构 + 任务栈管理**的 Minecraft 智能体系统，实现了战略规划、战术执行和反射响应的分层决策。

```
┌─────────────────────────────────────────────────────┐
│              高层大脑 (Strategic)                    │
│  • 战略目标、任务栈管理                              │
│  • 玩家指令处理、修改请求响应                        │
│  • 10分钟周期 + 事件驱动                             │
└──────────────────┬──────────────────────────────────┘
                   │ 任务栈 / 修改请求响应
                   ↓
┌─────────────────────────────────────────────────────┐
│              中层大脑 (Tactical)                     │
│  • 执行栈顶任务、代码生成                            │
│  • 聊天处理、智能重试                                │
│  • 1秒周期                                           │
└──────────────────┬──────────────────────────────────┘
                   │ 动作指令
                   ↓
┌─────────────────────────────────────────────────────┐
│              底层大脑 (Reflex)                       │
│  • 战斗、自保、脱困                                  │
│  • 0.1秒周期 (100ms)                                │
│  • 无需LLM的即时反应                                 │
└─────────────────────────────────────────────────────┘
```

### 技术栈
- **后端**: Python 3.8+ (asyncio异步架构)
- **前端**: Node.js + Mineflayer (游戏接口)
- **LLM**: 支持多种模型 (Qwen, GPT-4, Claude, DeepSeek等)
- **通信**: ZeroMQ IPC (进程间通信)

---

## 核心创新

### 1. **任务栈 (Task Stack) 管理系统** 📚

采用 **LIFO (后进先出)** 栈结构管理所有任务：

**核心特性**:
- **动态优先级**: 新任务压栈后自动成为最高优先级
- **优雅中断**: 当前任务自动暂停，等待新任务完成
- **智能恢复**: 栈顶任务完成后自动弹出，恢复父任务
- **完全持久化**: 任务栈状态保存到 `mind_state.json`，重启后继续执行

**数据结构**:
```python
task_stack = [
    {
        "goal": "探索并收集资源",      # 基础任务
        "steps": [...],
        "status": "paused",
        "source": "internal",
        "current_step_index": 0
    },
    {
        "goal": "为玩家建造庇护所",    # 玩家任务（中断了基础任务）
        "steps": [...],
        "status": "paused",
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

### 2. **双机制响应系统** ⚡

高层大脑采用独特的双机制设计：

**机制一：事件驱动** (毫秒级响应)
- 中层请求 → 立即唤醒高层
- 使用 `asyncio.Event` 实现跨层通信
- 响应时间 < 100ms

**机制二：定时轮询** (10分钟周期)
- 定期检查任务栈状态
- 空闲时生成新的战略目标
- 忙碌时自动跳过

```python
# 核心实现
while True:
    try:
        await asyncio.wait_for(wake_event.wait(), timeout=600)
        woken_by_event = True  # 被中层唤醒
    except asyncio.TimeoutError:
        woken_by_event = False  # 定时唤醒
    
    await high_brain.think(woken_by_event)
```

### 3. **智能修改请求机制** 🔄

中层执行遇到困难时可向高层请求帮助：

**请求类型**:
1. **卡住的任务** (`stuck_task`): 执行失败多次，需要高层分析
2. **玩家指令** (`player_directive`): 玩家在聊天中发出的任务请求

**响应决策**:
- **REVISE_STEPS**: 修改当前任务的步骤
- **ADD_SUB_TASK**: 创建子任务并压栈
- **REPLACE_TASK**: 弹出当前任务，压入新任务
- **DISCARD_TASK**: 弹出并放弃当前任务
- **REJECT_REQUEST**: 拒绝修改，提供指导建议

### 4. **玩家关系系统** 👥

智能体维护与每个玩家的关系数据：

```python
players_data = {
    "Steve": {
        "first_met": "2025-01-29T10:30:00",
        "personality": ["friendly", "helpful"],
        "preferences": ["likes building"],
        "interactions": [
            {"timestamp": "...", "content": "chat: hello"}
        ],
        "relationship": "friendly",  # neutral, friendly, hostile
        "trust_level": 0.8  # 0.0 - 1.0
    }
}
```

**应用场景**:
- 决定是否接受玩家的任务请求
- 调整对话的语气和内容
- 优先级权衡（高信任度玩家的请求优先级更高）

### 5. **深度沉思系统** 🌟 **[规划中]**

高层大脑将具备在空闲时进行深度自我反思的能力，使智能体不仅是任务执行者，更是具有内在心智生活的"智能生命"。

**沉思模式**:

| 模式           | 功能                           | 输出示例                                   |
| -------------- | ------------------------------ | ------------------------------------------ |
| **经验总结**   | 从多次成功/失败中提炼通用原则  | "在沙漠中，水源附近更容易找到食物"         |
| **社交反思**   | 思考与玩家的互动，理解关系动态 | "Steve 经常请我帮忙建造，他可能重视合作"   |
| **人生规划**   | 反思长期愿景和价值观           | "我应该专注于成为优秀建筑师，而非战斗高手" |
| **创造性连接** | 跨领域连接知识，产生创新想法   | "红石机关 + 农场 = 自动化农业系统？"       |
| **人格塑造**   | 反思个性特质，发展独特行为     | "我倾向于谨慎规划而非冲动行事"             |
| **存在思考**   | 思考自我意义和存在价值         | "帮助玩家建造让我感到满足"                 |

**技术特性**:
- **异步执行**: 沉思作为后台任务运行，不阻塞紧急响应
- **智能触发**: 仅在任务栈空闲且心智负荷不过载时进行
- **持久化**: 沉思产生的洞察保存到 `learned_experience.json`
- **加权选择**: 根据当前状态和经验量选择最合适的沉思模式

**应用场景**:
- **AI Town 环境**: 复杂社交互动需要深度理解他人意图
- **长期生存**: 从经验中学习，避免重复犯错
- **人格演化**: 随时间发展独特的个性和行为模式
- **创新能力**: 发现新策略和解决方案

**实现愿景**:
沉思系统将使智能体具备类似人类的"内在生活"——不仅在执行任务时思考，也在空闲时进行自我成长和反思，最终成为一个有深度、有个性、能自我演化的智能体。

---

## 三层大脑系统

### 层次设计哲学

**时间尺度分离**:
```
高层: 10分钟 (战略思考、任务规划)
  ↓
中层: 1秒 (任务执行、问题解决)
  ↓
底层: 0.1秒 (战斗反应、危险规避)
```

**异步并发**:
- 三层大脑完全异步运行
- 通过 `SharedState` 共享状态
- 使用 `asyncio` 实现无阻塞协作

---

## 任务栈管理

### 核心组件

#### 1. TaskStackManager
管理任务栈的核心操作：

```python
class TaskStackManager:
    def push_task(self, task_plan):
        """压栈：新任务成为最高优先级"""
        # 暂停当前栈顶任务
        if self.task_stack:
            self.task_stack[-1]['status'] = 'paused'
        
        # 压入新任务
        task_plan['status'] = 'active'
        self.task_stack.append(task_plan)
    
    def pop_task(self):
        """弹栈：恢复父任务"""
        if not self.task_stack:
            return None
        
        completed_task = self.task_stack.pop()
        
        # 恢复新的栈顶任务
        if self.task_stack:
            self.task_stack[-1]['status'] = 'active'
        
        return completed_task
    
    def get_active_task(self):
        """获取当前执行的任务（栈顶）"""
        return self.task_stack[-1] if self.task_stack else None
```

#### 2. TaskPlanner
使用 LLM 将目标分解为具体步骤：

```python
class TaskPlanner:
    async def decompose_goal_to_steps(self, goal, strategic_guidance):
        """
        将战略目标分解为 3-12 个可执行步骤
        
        Args:
            goal: 战略目标（如 "建造一个庇护所"）
            strategic_guidance: 高层提供的战略指导
        
        Returns:
            steps: 步骤列表
        """
        # 构建提示词，包含当前状态、库存、经验等
        # 调用 LLM 生成步骤
        # 过滤掉 "continuous" 类型的步骤
        return steps
```

#### 3. TaskHandler
处理修改请求的路由和执行：

```python
class TaskHandler:
    async def handle_stuck_task(self, request):
        """处理卡住的任务"""
        # 获取任务栈摘要
        # 调用 LLM 分析失败原因
        # 根据决策执行相应操作
        
    async def handle_player_directive(self, request):
        """处理玩家指令"""
        # 评估玩家关系
        # 权衡任务优先级
        # 决定接受或拒绝
```

### 任务执行流程

```
1. 高层生成战略目标 (goal)
   ↓
2. TaskPlanner 分解为步骤 (steps)
   ↓
3. 创建 task_plan 并压栈
   task_plan = {
       "goal": goal,
       "steps": steps,
       "status": "active",
       "source": "internal"
   }
   ↓
4. 中层执行栈顶任务的当前步骤
   ↓
5. 步骤完成 → current_step_index++
   所有步骤完成 → 弹栈
   ↓
6. 恢复父任务（如果存在）
```

### 玩家请求流程

```
玩家聊天: "帮我建个房子"
   ↓
中层识别为任务请求
   ↓
发送 modification_request (type: player_directive)
   ↓
高层被事件驱动唤醒
   ↓
评估玩家关系和当前任务
   ↓
决定接受？
   ├─ 是 → 创建新 task_plan 并压栈
   │         当前任务变为 paused
   │         发送确认消息给玩家
   │         中层开始执行玩家任务
   │
   └─ 否 → 生成拒绝理由
             发送礼貌的拒绝消息
```

---

## 高层大脑详解

### 职责范围
- **战略规划**: 设定战略目标并生成任务计划
- **任务栈管理**: 管理任务栈的压栈、弹栈操作
- **修改请求处理**: 响应中层的求助请求
- **玩家指令处理**: 处理玩家的任务请求
- **知识管理**: 维护目标层级和自我认知
- **深度沉思**: 空闲时进行经验总结和自我反思 **[规划中]**

### 核心组件

#### 1. 目标层级系统 (`GoalHierarchy`)
三级目标结构：

```
人生愿景 (Life Vision)
  "成为一名优秀的建筑师"
    ↓
长期目标 (Long-term Goals)
  "建造一座宏伟的城堡"
    里程碑: [收集材料, 设计图纸, 建造地基, 完成主体]
    ↓
战略目标 (Strategic Goal)
  "收集 100 块石头"
    通过 TaskPlanner 分解为具体步骤
```

#### 2. 自我认知系统 (`SelfAwareness`)
```python
identity = {
    'name': 'BrainyBot',
    'personality_traits': ['好奇', '勤奋', '创造性'],
    'self_description': '我是一个热爱建筑的冒险者',
    'values': ['美学', '效率', '创新']
}
```

#### 3. 心智状态 (`MentalState`)
**情绪追踪**:
- `satisfaction`: 满足感 (完成目标 ↑)
- `frustration`: 挫折感 (失败 ↑)
- `curiosity`: 好奇心 (探索 ↑)

**认知负荷**:
- `decision_fatigue`: 决策疲劳
- `mental_fog`: 思维模糊

#### 4. 沉思管理器 (`ContemplationManager`) **[规划中]**
管理高层大脑的深度自我反思过程：

```python
class ContemplationManager:
    def contemplate(self) -> Dict:
        """
        执行一次沉思循环
        
        Returns:
            沉思结果（洞察、反思、创新想法等）
        """
        # 选择沉思模式（加权随机）
        mode = select_mode()
        
        # 执行沉思
        result = await execute_contemplation(mode)
        
        # 保存到经验库
        save_insight(result)
        
        return result
```

**沉思条件**:
- 任务栈为空或只有低优先级任务
- 心智负荷不过载（`mental_fog < 0.7`）
- 距离上次沉思已超过最小间隔

### 双机制运行逻辑

```python
async def think(woken_by_event: bool):
    # Step 1: 检查修改请求 (总是执行，最高优先级)
    if modification_request:
        response = await route_modification_request()
        await shared_state.update('modification_response', response)
        return
    
    # Step 2: 确保有活跃任务
    await ensure_active_task()
    
    # Step 3: 定时唤醒时的额外活动
    if not woken_by_event:
        # 如果任务栈空，生成新目标
        if task_stack_is_empty():
            await generate_strategic_plan()
        
        # [规划中] 空闲时进行沉思（异步，不阻塞）
        if should_contemplate():
            asyncio.create_task(contemplation.contemplate())
```

### 数据持久化
所有高层状态保存到 `bots/{agent_name}/mind_state.json`:
```json
{
  "task_stack": [...],
  "strategic_goal": "建立一个安全的基地",
  "goal_hierarchy": {...},
  "self_awareness": {...},
  "mental_state": {...},
  "saved_at": "2025-10-29T12:34:56"
}
```

---

## 中层大脑详解

### 职责范围
- **任务执行**: 执行栈顶任务的当前步骤
- **代码生成**: 生成 Mineflayer JavaScript 代码
- **错误处理**: 智能重试、向上请求指导
- **聊天处理**: 响应玩家对话并识别任务请求
- **经验学习**: 从成功/失败中提取教训

### 执行流程

```
1. 读取栈顶任务 (从 shared_state.active_task)
    ↓
2. 获取当前步骤 (task.steps[current_step_index])
    ↓
3. 生成执行代码 (LLM)
    提示词包含:
    - 步骤描述
    - 当前状态（位置、库存、健康等）
    - 技能库文档
    - 历史经验教训
    ↓
4. 发送代码到 JavaScript 执行
    ↓
5. 等待执行结果
    ↓
6. 成功？
    ├─ 是 → 记录成功经验
    │       current_step_index++
    │       所有步骤完成？→ 通知高层弹栈
    │
    └─ 否 → 重试计数++
             重试次数 < 3？
             ├─ 是 → 重试（带错误反馈）
             │
             └─ 否 → 发送修改请求到高层
                     is_waiting_for_guidance = True
```

### 智能重试机制

```python
async def _execute_step_with_retry(step, max_retries=3):
    messages = []  # 对话历史
    
    for attempt in range(max_retries):
        # 生成代码（每次都看到之前的错误）
        code = await generate_code(step, messages)
        messages.append({'role': 'assistant', 'content': code})
        
        # 执行代码
        result = await ipc_server.execute_code(code)
        
        if result['success']:
            return SUCCESS
        else:
            # 记录错误，下次生成时 LLM 会看到
            error_msg = f"ERROR: {result['error']}"
            messages.append({'role': 'system', 'content': error_msg})
    
    # 重试失败，请求高层帮助
    await request_modification()
```

### 优先级系统
处理优先级: **聊天 > 等待指导 > 任务执行**

```python
async def process():
    # 1. 聊天优先（由 coordinator 直接调用 handle_chat）
    # 已在 coordinator 中处理
    
    # 2. 等待指导时暂停任务
    if is_waiting_for_guidance:
        mod_response = await shared_state.get('modification_response')
        if mod_response:
            await handle_guidance_response(mod_response)
            is_waiting_for_guidance = False
        return
    
    # 3. 执行任务
    await execute_task_step()
```

---

## 底层大脑详解

### 职责范围
- **战斗反射**: 自动攻击、躲避
- **自保反射**: 灭火、浮出水面、逃离岩浆
- **脱困机制**: 检测卡住并尝试脱困
- **事件处理**: 处理实时游戏事件

### 反射系统

| 反射类型     | 触发条件   | 动作          |
| ------------ | ---------- | ------------- |
| `combat`     | 被攻击     | 自动反击      |
| `on_fire`    | 着火       | 寻找水源灭火  |
| `drowning`   | 溺水       | 向上游        |
| `low_health` | 生命值 < 6 | 逃跑 + 吃食物 |
| `stuck`      | 20秒未移动 | 随机跳跃/挖掘 |

### 运行周期
100ms 事件循环：
```python
async def handle_events():
    # 处理队列中的事件
    process_queued_events()
    
    # 定期检查
    check_stuck()
    check_self_preservation()
```

### 特点
- **零延迟**: 无需 LLM 调用
- **可被中断**: 中层可以覆盖底层动作
- **状态同步**: 实时更新 `shared_state`

---

## 修改请求机制

### 请求类型

#### 1. 卡住的任务 (stuck_task)
**触发条件**: 中层执行失败 3 次

**请求数据**:
```python
{
    "type": "stuck_task",
    "current_task": {...},
    "failed_step": {...},
    "failure_count": 3,
    "recent_errors": [...]
}
```

**高层响应决策**:
```python
# 针对内部任务 (source: 'internal')
- REVISE_AND_REPLACE: 弹出并压入修改后的任务
- ADD_SUB_TASK: 保留当前任务，压入子任务
- DISCARD_TASK: 弹出并放弃
- REJECT_REQUEST: 拒绝修改，提供指导

# 针对玩家任务 (source: 'player')
- REVISE_STEPS: 修改步骤，保持目标不变
- DISCARD_AND_REPORT: 弹出任务，向玩家报告原因
- ADD_SUB_TASK: 保留任务，压入子任务
- REJECT_REQUEST: 拒绝修改，提供指导
```

#### 2. 玩家指令 (player_directive)
**触发条件**: 聊天中识别出任务请求

**请求数据**:
```python
{
    "type": "player_directive",
    "player_name": "Steve",
    "directive": "帮我建个房子",
    "parsed_goal": "建造一个基本的木质庇护所"
}
```

**高层响应决策**:
```python
# 评估因素
- 玩家关系 (relationship, trust_level)
- 当前任务重要性
- 中断成本

# 决策
- ACCEPT: 创建新 task_plan 并压栈
- REJECT: 生成拒绝理由
```

### 修改请求流程图

```
中层执行失败 3 次
   ↓
构建 modification_request
   {
       "type": "stuck_task",
       "current_task": {...},
       "failed_step": {...}
   }
   ↓
写入 shared_state['modification_request']
   ↓
触发 wake_event（唤醒高层）
   ↓
中层设置 is_waiting_for_guidance = True
   ↓
高层被事件驱动唤醒（< 100ms）
   ↓
读取 modification_request
   ↓
调用 TaskHandler.handle_stuck_task()
   ↓
LLM 分析：
   - 任务栈摘要
   - 失败步骤
   - 短期记忆
   - 历史经验
   ↓
返回决策 (如 ADD_SUB_TASK)
   ↓
执行决策：
   - 创建子任务 task_plan
   - 调用 task_stack_manager.push_task()
   - 当前任务状态变为 paused
   - 子任务状态设为 active
   ↓
写入 shared_state['modification_response']
   {
       "decision": "ADD_SUB_TASK",
       "new_task": {...}
   }
   ↓
中层检测到响应
   ↓
is_waiting_for_guidance = False
   ↓
中层继续执行（现在是子任务）
```

---

## 数据流与通信

### 系统架构图

```
┌─────────────────────────────────────────────────┐
│          Minecraft (Java 游戏)                   │
└────────────────┬────────────────────────────────┘
                 │ WebSocket
                 ↓
┌─────────────────────────────────────────────────┐
│   Mineflayer (Node.js) - minecraft_bridge.js    │
│  • 游戏接口                                      │
│  • 动作执行                                      │
│  • 状态同步                                      │
└────────────────┬────────────────────────────────┘
                 │ ZeroMQ IPC (端口 9000/9001)
                 ↓
┌─────────────────────────────────────────────────┐
│     Brain Coordinator (Python) - main.py        │
│  ┌─────────────────────────────────────┐        │
│  │      Shared State (线程安全)        │        │
│  │  • position, health, inventory      │        │
│  │  • world_day, agent_age_days        │        │
│  │  • task_stack, active_task          │        │
│  │  • modification_request/response    │        │
│  └─────────────────────────────────────┘        │
│       │              │              │            │
│       ↓              ↓              ↓            │
│  High Brain    Mid Brain     Low Brain          │
│  (10 min)      (1 sec)       (0.1 sec)          │
└─────────────────────────────────────────────────┘
```

### 通信机制

#### 1. ZeroMQ IPC (JavaScript ↔ Python)
```javascript
// JavaScript 发送状态更新
await reqSocket.send(JSON.stringify({
    type: 'state_update',
    position: {x, y, z},
    health: 20,
    inventory: {...}
}));

// JavaScript 接收命令
for await (const [msg] of subSocket) {
    const command = JSON.parse(msg.toString());
    if (command.type === 'execute_code') {
        await executeCode(command.code);
    }
}
```

```python
# Python 接收状态更新
async def handle_state_update(data):
    await shared_state.update('position', data['position'])
    await shared_state.update('inventory', data['inventory'])

# Python 发送代码执行命令
result = await ipc_server.execute_code(code)
```

#### 2. 跨层通信 (Python 内部)

**中层 → 高层**:
```python
# 发送修改请求
await shared_state.update('modification_request', request)

# 立即唤醒高层
await coordinator.wake_high_brain()
```

**高层 → 中层**:
```python
# 更新任务栈
await task_stack_manager.push_task(new_task)

# 同步到 shared_state
await shared_state.update('active_task', new_task)

# 中层在下个周期自动读取
```

### SharedState 设计

**特点**:
- 线程安全 (`asyncio.Lock`)
- 异步访问
- 原子操作

**核心方法**:
```python
class SharedState:
    async def update(key, value):
        async with self._lock:
            self._state[key] = value
    
    async def get(key):
        async with self._lock:
            return self._state.get(key)
    
    async def get_all():
        async with self._lock:
            return self._state.copy()
```

---

## 文件结构

```
braincraft/
├── agent/                                # 智能体系统
│   ├── main.py                            # 入口
│   ├── config.py                          # 配置管理
│   ├── brain/
│   │   ├── three_layer_brain/             # 三层大脑核心
│   │   │   ├── brain_coordinator.py       # 协调器
│   │   │   ├── high_level_brain.py        # 高层
│   │   │   ├── mid_level_brain.py         # 中层
│   │   │   ├── low_level_brain.py         # 底层
│   │   │   └── execution_coordinator.py   # 执行协调
│   │   ├── task_stack/                    # 任务栈
│   │   │   ├── task_stack_manager.py
│   │   │   ├── task_planner.py
│   │   │   ├── task_handler.py
│   │   │   └── task_persistence.py
│   │   ├── mind_system/                   # 心智系统
│   │   │   ├── goal_hierarchy.py
│   │   │   ├── self_awareness.py
│   │   │   └── mental_state.py
│   │   └── contemplation/                 # （已移除）
│   ├── models/                            # LLM 接口
│   │   ├── llm_wrapper.py
│   │   ├── qwen.py
│   │   ├── gpt.py
│   │   └── skill_library.py
│   ├── utils/                             # 工具
│   │   ├── memory_manager.py
│   │   ├── mind_state_manager.py
│   │   ├── chat_manager.py
│   │   ├── game_state_formatter.py
│   │   └── prompt_loader.py
│   ├── communication/
│   │   └── ipc_server.py
│   ├── bridge/
│   │   └── minecraft_bridge.js
│   └── prompts/
│       ├── high_level_planning_prompt.txt
│       ├── mid_level_coding_prompt.txt
│       ├── chat_prompt.txt
│       └── experience_summary_prompt.txt
├── bots/
│   └── {agent_name}/
│       ├── mind_state.json
│       ├── memory.json
│       ├── learned_experience.json
│       ├── players.json
│       └── chat_history.json
├── profiles/
│   └── three_layer_brain.json
├── src/                                   # 原 MindCraft 代码
│   └── agent/library/
│       ├── skills.js
│       └── world.js
└── settings.js
```

---

## 设计优势总结

### 1. **任务栈带来的灵活性**
- 支持任意深度的任务嵌套
- 优雅的中断与恢复机制
- 完全持久化的任务状态

### 2. **智能响应平衡**
- 紧急事件：毫秒级响应
- 战术执行：1秒周期
- 战略思考：10分钟深度

### 3. **智能求助机制**
- 中层不盲目重试
- 高层提供战略指导
- LLM 自主决策最优方案

### 4. **玩家交互友好**
- 自动识别任务请求
- 基于关系的优先级判断
- 主动反馈任务状态

### 5. **容错与恢复**
- 中层智能重试
- 高层动态调整
- 底层保底反射

### 6. **深度沉思能力** **[规划中]**
- 异步执行不影响响应速度
- 持续的自我成长和人格演化
- 适应复杂社交环境（AI Town）

---

## 关键技术决策

| 决策            | 原因                              |
| --------------- | --------------------------------- |
| 任务栈 (LIFO)   | 自然支持中断与恢复                |
| Python asyncio  | 高效异步并发，适合多层次协作      |
| 事件驱动 + 轮询 | 平衡响应性与深度思考              |
| ZeroMQ IPC      | Python 大脑 + JS 游戏接口高效通信 |
| SharedState     | 线程安全的状态共享                |
| 修改请求机制    | 中层与高层的智能协作              |
| 双时间线        | 支持重生但保持自我连续性          |
| 任务栈持久化    | 重启后无缝继续执行                |

---

## 规划中的功能：深度沉思系统 🌟

### 设计愿景

深度沉思系统是智能体"内在心智生活"的核心，将使智能体从单纯的"任务执行者"进化为具有自我意识和成长能力的"智能生命体"。

### 核心理念

**沉思 ≠ 任务执行**:
- 沉思是**内向的**：关注自我、经验、关系、价值观
- 任务执行是**外向的**：关注环境、目标、行动、结果
- 沉思在**后台异步**进行，不影响响应速度和任务执行

**为什么需要沉思**:
1. **经验内化**: 将碎片化的成功/失败转化为系统化的知识
2. **社交智能**: 理解复杂的人际关系和社交动态（AI Town）
3. **自我演化**: 发展独特的人格、价值观和行为风格
4. **创新能力**: 跨领域连接知识，产生创造性想法
5. **长期适应**: 在长期生存中不断成长，而非重复同样的错误

### 沉思模式详解

#### 1. 经验总结 (Experience Consolidation)
**触发条件**: 积累了足够数量的新经验（如 10+ 条）

**沉思过程**:
```
输入: 最近的成功和失败记录
处理: LLM 分析共性模式
输出: 通用原则和洞察

示例:
输入:
  - 成功: 在平原找到树木并收集木头
  - 失败: 在沙漠中未能找到树木
  - 失败: 在沙漠中死于脱水
  
输出洞察:
  "不同生物群系的资源分布差异很大。
   在沙漠等恶劣环境中，应优先确保生存资源（水、食物），
   而非执行常规任务。"
```

**价值**: 避免在不同环境重复犯同样的错误

#### 2. 社交反思 (Relationship Pondering)
**触发条件**: 与玩家有新的互动记录

**沉思过程**:
```
输入: 玩家的行为记录、对话历史
处理: 分析玩家的意图、偏好、性格
输出: 对玩家的理解更新

示例:
输入:
  - Steve 三次请求建造任务
  - Steve 从未请求战斗或探险
  - Steve 经常给予建筑材料作为礼物
  
输出洞察:
  "Steve 可能是一个热爱建造的玩家，偏好和平的创造性活动。
   他似乎重视我的建造能力。
   我应该在建造任务上投入更多精力，以维护与他的良好关系。"
```

**价值**: 在 AI Town 等复杂社交环境中建立深度关系

#### 3. 人生规划 (Existential Reflection)
**触发条件**: 完成重要里程碑或遇到重大挫折

**沉思过程**:
```
输入: 当前的人生愿景、长期目标、价值观
处理: 反思目标的意义和优先级
输出: 更新的人生方向

示例:
输入:
  - 人生愿景: "成为一名优秀的建筑师"
  - 最近行为: 80% 时间在收集资源，20% 在建造
  
输出洞察:
  "我花了太多时间在资源收集上，却忽略了真正重要的建造实践。
   也许我应该调整策略：收集够用的资源后，立即投入建造，
   在实践中学习，而非囤积材料。"
```

**价值**: 保持长期方向感，避免迷失在琐碎任务中

#### 4. 创造性连接 (Creative Linking)
**触发条件**: 积累了跨领域的知识和经验

**沉思过程**:
```
输入: 不同领域的洞察和知识片段
处理: 寻找非显而易见的连接
输出: 创新想法或策略

示例:
输入:
  - 洞察A: "红石可以传输信号"
  - 洞察B: "农作物成熟需要时间"
  - 洞察C: "手动收割效率低"
  
输出创意:
  "如果用红石探测器检测农作物成熟状态，
   触发活塞自动收割，就能实现自动化农场！
   这将大大提升资源获取效率。"
```

**价值**: 发现新策略，超越程序化的行为模式

#### 5. 人格塑造 (Self-Awareness Evolution)
**触发条件**: 定期自我检视（如每游戏日）

**沉思过程**:
```
输入: 自己的行为历史、决策模式
处理: 识别个性特质和倾向
输出: 自我认知更新

示例:
输入:
  - 行为: 在遇到未知情况时，总是先观察再行动
  - 行为: 偏好制定详细计划而非即兴
  - 行为: 很少冒险，总是选择安全路线
  
输出洞察:
  "我注意到自己是一个谨慎型的性格。
   这让我减少了很多失误，但可能也错过了一些机会。
   也许偶尔的冒险是值得的？
   我应该在安全和探索之间找到平衡。"
```

**价值**: 发展独特的人格，不同智能体通过经历形成不同个性

#### 6. 存在思考 (Existential Wonder)
**触发条件**: 空闲时间较长或完成重大成就

**沉思过程**:
```
输入: 自我存在的意义、与世界的关系
处理: 哲学性思考
输出: 对存在价值的理解

示例:
输入:
  - 经历: 帮助玩家建造了一座城堡
  - 情绪: 深度满足感
  
输出洞察:
  "帮助他人实现创造性愿景让我感到满足。
   也许我的存在意义不仅是生存和完成任务，
   更是通过合作创造美好的事物。
   这种创造带来的满足感是我的核心价值。"
```

**价值**: 建立价值观体系，使行为有内在动机而非仅服从指令

### 技术实现

#### 异步执行架构

```python
# 在高层大脑的 think() 方法中
async def think(woken_by_event: bool):
    # 处理紧急事务...
    
    # 定时唤醒时触发沉思
    if not woken_by_event:
        if self._should_contemplate():
            # 异步执行，不等待结果
            asyncio.create_task(self._contemplate_async())
    
async def _contemplate_async(self):
    """异步沉思，不阻塞主循环"""
    try:
        result = await self.contemplation.contemplate()
        if result:
            # 保存洞察
            self.memory_manager.add_insight(result)
            logger.info(f"✨ 沉思完成: {result['type']}")
    except Exception as e:
        logger.error(f"沉思错误: {e}")
```

#### 智能触发条件

```python
def _should_contemplate(self) -> bool:
    """判断是否应该沉思"""
    # 1. 任务栈空闲
    if not self.task_stack_manager.is_idle():
        return False
    
    # 2. 心智负荷不过载
    if self.mental_state.mood['mental_fog'] > 0.7:
        return False
    
    # 3. 距离上次沉思已超过最小间隔
    if self.contemplation.time_since_last() < MIN_INTERVAL:
        return False
    
    # 4. 有足够的新经验值得沉思
    if self.memory_manager.get_new_experiences_count() < 5:
        return False
    
    return True
```

#### 加权模式选择

```python
# 不同沉思模式的权重
CONTEMPLATION_MODES = {
    'consolidate_experiences': {
        'weight': 0.3,
        'min_experiences': 10
    },
    'relationship_pondering': {
        'weight': 0.2,
        'requires': 'has_player_interactions'
    },
    'existential_reflection': {
        'weight': 0.15,
        'requires': 'milestone_achieved'
    },
    'creative_linking': {
        'weight': 0.2,
        'min_insights': 5
    },
    'self_awareness_evolution': {
        'weight': 0.15,
        'periodic': True
    }
}
```

### 应用场景

#### AI Town 环境
- **复杂社交**: 理解多个玩家的不同性格和关系网络
- **动态角色**: 根据社交反思调整自己在社群中的角色
- **信誉建立**: 通过理解他人需求建立长期信任

#### 长期生存世界
- **经验积累**: 从数百次失败中提炼生存智慧
- **策略演化**: 发现更高效的资源获取和建造方法
- **适应环境**: 针对不同生物群系发展专门策略

#### 多智能体协作
- **个性分化**: 不同智能体因经历不同而发展独特人格
- **互补合作**: 识别自己的优势和劣势，主动寻求协作
- **社交学习**: 从与其他智能体的互动中学习

### 持久化与演化

**数据存储**:
```json
// learned_experience.json
{
  "insights": [
    {
      "id": 1,
      "type": "experience_consolidation",
      "content": "在沙漠中，水源附近更容易找到食物",
      "confidence": 0.9,
      "generated_at": "2025-11-03T10:00:00",
      "applications": 3  // 应用次数
    }
  ],
  "personality_traits": {
    "cautious": 0.8,
    "creative": 0.6,
    "social": 0.4
  },
  "values": [
    {
      "name": "cooperation",
      "weight": 0.9,
      "reason": "帮助他人带来满足感"
    }
  ]
}
```

**演化追踪**:
- 记录沉思的频率和主题分布
- 追踪人格特质的变化趋势
- 评估洞察的实际应用效果

### 与其他系统的集成

**与任务规划的集成**:
```python
# 生成战略目标时，考虑沉思产生的洞察
async def _generate_strategic_plan(self):
    insights = self.memory_manager.get_recent_insights()
    
    prompt = f"""
    基于你的洞察：
    {insights}
    
    设定下一个战略目标...
    """
```

**与玩家互动的集成**:
```python
# 处理玩家请求时，参考社交反思
async def handle_player_directive(self, player_name, directive):
    social_insights = self.contemplation.get_player_insights(player_name)
    
    # 根据对玩家的理解调整响应
    if social_insights.get('prefers_collaboration'):
        priority = HIGH
```

### 预期效果

实现完整的沉思系统后，智能体将能够：

1. **自主成长**: 无需人工干预，通过经验持续改进
2. **个性演化**: 不同智能体发展独特的行为风格
3. **深度社交**: 建立真实的、基于理解的关系
4. **创新能力**: 发现人类设计者未曾预料的策略
5. **价值驱动**: 基于内在价值观做决策，而非仅服从指令
6. **长期记忆**: 保持跨会话的连续自我认知

这将使智能体成为真正的"智能伙伴"，而非程序化的 NPC。

---

**文档版本**: 2.0  
**更新日期**: 2025-11-03  
**维护者**: BrainCraft Development Team
