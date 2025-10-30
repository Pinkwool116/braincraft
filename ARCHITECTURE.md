# BrainCraft 智能体架构文档

## 目录
- [架构概述](#架构概述)
- [核心创新](#核心创新)
- [三层大脑系统](#三层大脑系统)
- [高层大脑详解](#高层大脑详解)
- [中层大脑详解](#中层大脑详解)
- [底层大脑详解](#底层大脑详解)
- [心智系统](#心智系统)
- [时间感知系统](#时间感知系统)
- [数据流与通信](#数据流与通信)

---

## 架构概述

BrainCraft 是一个基于**三层大脑架构**的 Minecraft 智能体系统，将人类认知模型映射到 AI 决策层次：

```
┌─────────────────────────────────────────────────────┐
│              高层大脑 (Strategic)                    │
│  • 人生目标、自我认知、战略规划                      │
│  • 15分钟周期 + 事件驱动                             │
│  • 闲暇沉思、目标调整                                │
└──────────────────┬──────────────────────────────────┘
                   │ 任务计划 / 修改请求
                   ↓
┌─────────────────────────────────────────────────────┐
│              中层大脑 (Tactical)                     │
│  • 任务执行、代码生成、聊天处理                      │
│  • 1秒周期                                           │
│  • 智能重试、向上请求指导                            │
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
- **LLM**: 支持多种模型 (GPT-4, Claude, Qwen, DeepSeek等)
- **通信**: IPC (进程间通信)

---

## 核心创新

### 1. **双机制响应系统** ⚡
高层大脑采用独特的双机制设计，平衡深度思考与即时响应：

**机制一：事件驱动** (毫秒级响应)
- 中层请求 → 立即唤醒高层
- 使用 `asyncio.Event` 实现跨层通信
- 响应时间 < 100ms

**机制二：定时轮询** (15分钟周期)
- 定期检查是否空闲
- 空闲时进行深度沉思
- 忙碌时自动跳过

```python
# 核心实现
while True:
    try:
        await asyncio.wait_for(wake_event.wait(), timeout=900)
        woken_by_event = True  # 被中层唤醒
    except asyncio.TimeoutError:
        woken_by_event = False  # 定时唤醒
    
    await high_brain.think(woken_by_event)
```

### 2. **可打断的沉思机制** 💭
高层沉思过程可被中层紧急请求即时打断：

**打断流程**:
1. 沉思进行中 (1-3分钟)
2. 中层发送请求 → 设置 `wake_event`
3. `asyncio.wait()` 立即返回
4. 保存沉思进度到 `interrupted_contemplation`
5. 处理中层请求
6. 下次空闲时从断点恢复沉思

**技术亮点**:
```python
# 同时等待两个事件：沉思完成 OR 唤醒信号
done, pending = await asyncio.wait(
    {contemplation_task, wake_task},
    return_when=asyncio.FIRST_COMPLETED
)

if wake_task in done:
    # 被打断！保存进度
    progress = get_current_progress()
    interrupted_contemplation = {...}
```

### 3. **心智系统** 🧠
智能体拥有类人的内部心理状态：

- **情绪系统**: 满足感、挫折感、好奇心
- **能量管理**: 认知负荷、决策疲劳
- **注意力机制**: 专注度、分心检测
- **自我认知**: 人格特质、价值观、自我描述

### 4. **时间感知** ⏰
区分"世界时间"与"代理年龄"：

- **世界时间** (`world_day`): 从世界创建开始计时
- **代理年龄** (`agent_age_days`): 从首次出生开始计时
- 支持死亡重生，保持连续的自我认知

### 5. **闲暇沉思系统** 🌟
高层大脑在空闲时进行多种模式的思考：

| 模式                      | 功能               | 输出     |
| ------------------------- | ------------------ | -------- |
| `consolidate_experiences` | 整合经验，发现模式 | 通用原则 |
| `connect_insights`        | 跨领域创造性连接   | 新假设   |
| `self_reflection`         | 自我反思           | 人格洞察 |
| `existential_wonder`      | 存在思考           | 人生意义 |
| `relationship_pondering`  | 关系思考           | 社交理解 |

---

## 三层大脑系统

### 层次设计哲学

**设计灵感**: 人类大脑的三层结构
- **爬行脑** (Reptilian) → 底层大脑 (生存反射)
- **哺乳脑** (Limbic) → 中层大脑 (情感与执行)
- **新皮质** (Neocortex) → 高层大脑 (理性与规划)

**时间尺度分离**:
```
高层: 15分钟 (战略思考、人生规划)
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

## 高层大脑详解

### 职责范围
- **战略规划**: 制定长期目标和里程碑
- **人生愿景**: 设定并修订人生方向
- **任务调整**: 响应中层的修改请求
- **闲暇沉思**: 自我反思、经验整合
- **知识管理**: 维护目标层级和自我认知

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
任务计划 (Task Plan)
  "挖掘100块石头"
    步骤: [找到石矿, 制作镐子, 挖掘]
```

**特点**:
- 使用里程碑而非数值进度
- 支持目标暂停、放弃、重启
- 记录重要生命事件

#### 2. 自我认知系统 (`SelfAwareness`)
```python
identity = {
    'name': 'Andy',
    'personality_traits': ['好奇', '勤奋', '创造性'],
    'self_description': '我是一个热爱建筑的冒险者',
    'values': ['美学', '效率', '创新']
}
```

#### 3. 沉思管理器 (`ContemplationManager`)
**沉思条件**:
- 高层处于空闲状态
- 心智负荷不过载
- 满足频率限制 (每小时最多10次)

**沉思流程**:
```python
选择沉思模式 → 调用LLM生成思考 → 评估价值 → 保存洞察
```

#### 4. 心智状态 (`MentalState`)
**情绪追踪**:
- `satisfaction`: 满足感 (完成目标 ↑)
- `frustration`: 挫折感 (失败 ↑)
- `curiosity`: 好奇心 (探索 ↑)

**认知负荷**:
- `decision_fatigue`: 决策疲劳
- `mental_fog`: 思维模糊
- 过载时拒绝新任务

### 双机制运行逻辑

```python
async def think(woken_by_event: bool):
    # Step 1: 检查中层请求 (总是执行)
    if modification_request:
        interrupt_contemplation()  # 打断沉思
        handle_modification_request()
        return
    
    # Step 2: 更新任务计划 (总是执行)
    update_task_plan()
    
    # Step 3: 沉思 (仅定时唤醒 + 空闲时)
    if not woken_by_event:  # 定时唤醒
        if is_idle() and needs_contemplation():
            await idle_think()  # 可被打断的沉思
```

### 数据持久化
所有高层状态保存到 `bots/{agent_name}/mind_state.json`:
```json
{
  "goal_hierarchy": {...},
  "self_awareness": {...},
  "mental_state": {...},
  "saved_at": "2025-10-29T12:34:56"
}
```

---

## 中层大脑详解

### 职责范围
- **任务执行**: 将高层任务计划拆解为具体动作
- **代码生成**: 生成 Mineflayer JavaScript 代码
- **错误处理**: 智能重试、向上请求指导
- **聊天处理**: 响应玩家对话
- **经验学习**: 从成功/失败中提取教训

### 执行流程

```
1. 读取任务计划 (从 shared_state)
    ↓
2. 生成执行代码 (LLM)
    ↓
3. 发送到 JavaScript 执行
    ↓
4. 等待执行结果
    ↓
5. 成功 → 记录经验 → 下一步
   失败 → 智能重试或请求指导
```

### 智能重试机制

```python
if failure_count < MAX_RETRIES:
    # 尝试自行修复
    retry_with_different_approach()
else:
    # 向高层求助
    send_modification_request()
    wake_high_brain()  # ⚡ 立即唤醒
    wait_for_guidance()
```

### 优先级系统
处理优先级: **聊天 > 等待指导 > 任务执行**

```python
async def process():
    # 1. 聊天优先
    if pending_chat:
        await handle_chat()
        return
    
    # 2. 等待指导时暂停任务
    if is_waiting_for_guidance:
        return
    
    # 3. 执行任务
    await execute_task_step()
```

### 修改请求 (Modification Request)
中层向高层请求调整计划的机制：

```python
request = {
    'reason': '遇到未知怪物，无法继续挖矿',
    'context': '当前任务: 挖掘石头, 失败3次',
    'suggestion': '需要先击败怪物或改变策略'
}

await shared_state.update('modification_request', request)
await coordinator.wake_high_brain()  # 立即唤醒高层
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

## 心智系统

### 情绪模型

**情绪维度**:
```python
mood = {
    'satisfaction': 0.7,    # 满足感 [0, 1]
    'frustration': 0.2,     # 挫折感 [0, 1]
    'curiosity': 0.5,       # 好奇心 [0, 1]
    'confidence': 0.6       # 自信心 [0, 1]
}
```

**情绪变化**:
- 完成目标 → `satisfaction ↑`
- 任务失败 → `frustration ↑`
- 探索新区域 → `curiosity ↑`
- 连续成功 → `confidence ↑`

### 认知负荷

**负荷指标**:
```python
cognitive_load = {
    'decision_fatigue': 0.3,   # 决策疲劳
    'mental_fog': 0.1,         # 思维模糊
    'overwhelm': 0.0           # 过载
}
```

**负荷管理**:
- 过载时 (`is_busy()`) 拒绝新任务
- 沉思后降低 `decision_fatigue`
- 休息时恢复认知能量

### 注意力机制

**注意力状态**:
- `focused`: 专注于当前任务
- `distracted`: 容易被打断
- `wandering`: 思维游荡 (触发沉思)

---

## 时间感知系统

### 双时间线设计

**世界时间** (绝对时间):
```python
world_day = 42        # 世界创建后第42天
world_time = 846000   # 总游戏 tick 数
```

**代理年龄** (相对时间):
```python
agent_age_days = 15      # 代理活了15天
agent_age_ticks = 302000 # 代理生存的 tick 数
birthday = 27            # 在世界第27天出生
```

### 重生机制
```python
if just_respawned:
    # 世界时间继续前进
    world_day += 1
    
    # 代理年龄重置为0
    agent_age_days = 0
    
    # 但记忆和目标保留！
    load_mind_state()  # 恢复人格和目标
```

### 时间感知应用
- 目标设定使用 `agent_age_days` (相对时间)
- 世界事件使用 `world_day` (绝对时间)
- 自我认知基于 `agent_age_days` (持续自我)

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
│     Mineflayer (Node.js) - minecraft_bridge.js  │
│  • 游戏接口                                      │
│  • 动作执行                                      │
│  • 状态同步                                      │
└────────────────┬────────────────────────────────┘
                 │ IPC (进程间通信)
                 ↓
┌─────────────────────────────────────────────────┐
│     Brain Coordinator (Python) - main.py        │
│  ┌─────────────────────────────────────┐        │
│  │      Shared State (线程安全)        │        │
│  │  • position, health, inventory      │        │
│  │  • world_day, agent_age_days        │        │
│  │  • task_plan, strategic_goal        │        │
│  └─────────────────────────────────────┘        │
│       │              │              │            │
│       ↓              ↓              ↓            │
│  High Brain    Mid Brain     Low Brain          │
│  (15 min)      (1 sec)       (0.1 sec)          │
└─────────────────────────────────────────────────┘
```

### 通信机制

#### 1. IPC 消息 (JavaScript → Python)
```javascript
// JavaScript 发送状态更新
ipc.send('state_update', {
    position: {x, y, z},
    health: 20,
    inventory: {...},
    world_day: 42,
    agent_age_days: 15
});
```

```python
# Python 接收
async def handle_state_update(data):
    await shared_state.update('position', data['position'])
    await shared_state.update('world_day', data['world_day'])
    # ...
```

#### 2. 动作执行 (Python → JavaScript)
```python
# Python 生成代码
code = """
await bot.pathfinder.goto(new Vec3(100, 64, 100));
"""

# 发送执行
result = await ipc_server.execute_code(code)
```

#### 3. 跨层通信 (Python 内部)

**中层 → 高层**:
```python
# 发送修改请求
await shared_state.update('modification_request', request)

# 立即唤醒高层
await coordinator.wake_high_brain()
```

**高层 → 中层**:
```python
# 更新任务计划
await shared_state.update('current_task', new_task_plan)

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
```

---

## 文件结构

```
python/
├── brain/
│   ├── brain_coordinator.py      # 大脑协调器
│   ├── high_level_brain.py        # 高层大脑
│   ├── mid_level_brain.py         # 中层大脑
│   ├── low_level_brain.py         # 底层大脑
│   ├── goal_hierarchy.py          # 目标层级
│   ├── self_awareness.py          # 自我认知
│   ├── mental_state.py            # 心智状态
│   └── contemplation/
│       ├── contemplation_manager.py  # 沉思管理器
│       └── config.py                 # 沉思配置
├── models/
│   ├── llm_wrapper.py             # LLM 统一接口
│   ├── gpt.py, claude.py, qwen.py # 各模型实现
│   └── ...
├── utils/
│   ├── memory_manager.py          # 记忆管理
│   └── ipc_server.py              # IPC 服务器
└── main.py                        # 程序入口

bots/{agent_name}/
├── mind_state.json               # 心智状态 (目标、自我认知)
├── memory.json                   # 短期记忆
├── learned_experience.json       # 长期经验
└── players.json                  # 玩家关系
```

---

## 设计优势总结

### 1. **真正的异步并发**
- 三层大脑独立运行，互不阻塞
- 高层沉思不影响中层执行
- 底层反射零延迟

### 2. **智能响应平衡**
- 紧急事件：毫秒级响应
- 战术执行：1秒周期
- 战略思考：15分钟深度

### 3. **类人心智模型**
- 情绪影响决策
- 认知负荷管理
- 自我认知演化

### 4. **容错与恢复**
- 中层智能重试
- 高层动态调整
- 底层保底反射

### 5. **持续自我**
- 跨重生的记忆
- 演化的人格
- 积累的智慧

---

## 关键技术决策

| 决策            | 原因                          |
| --------------- | ----------------------------- |
| Python asyncio  | 高效异步并发，适合多层次协作  |
| 事件驱动 + 轮询 | 平衡响应性与深度思考          |
| asyncio.wait()  | 实现可打断的沉思              |
| SharedState     | 线程安全的状态共享            |
| IPC 分离        | Python 大脑 + JS 游戏接口解耦 |
| 双时间线        | 支持重生但保持自我连续性      |
| 里程碑而非进度  | 更自然的目标追踪              |

---

**文档版本**: 1.0  
**更新日期**: 2025-10-29  
**维护者**: BrainCraft Development Team
