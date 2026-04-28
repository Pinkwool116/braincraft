# 智能体感知层完善方案

## 一、当前感知层的核心缺陷

1. **感知半径极小**：方块仅 3x3x3（自身 1 格半径），实体仅 16 格
2. **快照式而非流式**：环境信息仅在 LLM 被唤醒时采样，两次调用之间的事件全部丢失
3. **无空间理解**：不知道地形结构（悬崖/洞穴/水域/森林），不知道前方有什么
4. **无听觉**：`soundEffectHeard` 事件完全未使用
5. **执行期间盲跑**：代码执行时 Agent Loop 被阻塞，无法感知环境变化
6. **感知数据与记忆混杂**：原始环境数据直接注入 LLM prompt，与推理/计划/对话混在一起

---

## 二、感知层整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Minecraft 世界                         │
└─────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
   │ 被动事件监听  │ │ 主动地形扫描  │ │ 状态快照采集  │
   │ (事件驱动)    │ │ (定时触发)    │ │ (周期性)      │
   └──────────────┘ └──────────────┘ └──────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                  ┌────────────────┐
                  │  原始感知缓冲区  │  ← 高频、大容量、原始数据
                  └────────────────┘
                           │
                           ▼
                  ┌────────────────┐
                  │ Perception      │  ← Flash LLM（低延迟、低成本）
                  │ Summarizer     │     纯观测：去噪 → 聚合 → 结构化
                  └────────────────┘
                           │
                    ┌──────┴──────┐
                    ▼              ▼
           ┌────────────┐  ┌────────────┐
           │ 环境摘要    │  │ 显著事件    │
           │ → 主LLM注入 │  │ → 工作记忆  │
           └────────────┘  └────────────┘
```

**三层感知，互不阻塞**：
- **被动事件监听**：Mineflayer 事件驱动，JS 端持续运行，不受 Python Agent Loop 状态影响
- **主动地形扫描**：独立感知 Worker，定期执行，不受代码执行阻塞
- **Perception Summarizer**：独立 Flash LLM 调用，不占用主 LLM 的上下文窗口

---

## 三、环境检测层 —— 如何获取更多环境信息

### 3.1 被动事件监听（扩展现有 Mineflayer 事件）

当前仅监听 `chat`、`health`、`death`、`entityHurt`。需要新增以下事件，建立一个**连续的环境事件流**：

| 事件 | 用途 | 记录内容 |
|------|------|---------|
| `entitySpawn` | 实体进入视野 | 实体类型、名称、坐标、出现时间 |
| `entityGone` | 实体离开视野 | 实体类型、名称、最后坐标 |
| `entityMoved` | 实体移动 | 仅在「实体正在靠近 Agent」或「实体状态变化」时记录 |
| `blockUpdate` | 方块变化 | 旧方块→新方块、坐标（区分玩家操作 vs 自然变化）|
| `soundEffectHeard` | 听觉感知 | 声音名称、来源坐标、距离、音量 |
| `playerJoined` | 玩家上线 | 玩家名、时间 |
| `playerLeft` | 玩家下线 | 玩家名、时间 |
| `rain` | 天气变化 | 开始/停止下雨或雷暴 |
| `explosion` | 爆炸事件 | 来源坐标、距离 |

**关键设计点**：
- 这些事件**不直接推送给 Agent Loop**，而是写入**原始感知缓冲区**
- JS 端独立运行，不依赖 Python 端的任何状态
- 高频事件（如 `entityMoved`）需要节流：同一实体每 N 秒最多记录一次

### 3.2 主动地形扫描 —— 如何了解地形

利用 `bot.look(yaw, pitch)` + `bot.blockAtCursor(distance)` 实现**多点射线扫描**，类似雷达/激光雷达（LiDAR）：

#### 3.2.1 扫描策略

**水平扫描 + 俯仰分层**：

```
对每个水平方向（每 22.5° 一个采样，共 16 个方向）：
  对每个俯仰角（-45° 看下方, 0° 平视, +30° 看上方）：
    bot.look(yaw, pitch)
    block = bot.blockAtCursor(64)  ← 64 格射线
    记录：(yaw, pitch, 命中方块名, 距离, 坐标, 光照)
```

一次完整扫描产生 16×3=48 个采样点，足以拼出周围的地形结构。

**关键信息提取**：
- **地形判断**：近距离命中 `stone`/`dirt` = 山壁；向下命中 `air` 且距离远 = 峡谷/悬崖；命中 `water` = 水域；命中 `lava` = 危险
- **空洞检测**：命中方块但 `skyLight=0` = 可能处于洞穴中
- **资源分布**：哪个方向有树木（`oak_log`）、矿石
- **威胁预警**：近距离命中 `lava`、视线方向有敌对生物

#### 3.2.2 补充：区域方块统计

在主动扫描之外，扩大 `findBlocks` 的范围：

- 当前：`maxDistance: 3`（仅 3x3x3 = 27 格）
- 改进：`maxDistance: 8`（8x6x8 = ~384 格），但只返回**聚合统计**而非逐格列出

```
聚合输出示例：
  方块统计 (8格半径内):
  - 橡木原木: 12 个，集中在东北方向
  - 草方块: ~200 个 (地表)
  - 石头: ~50 个 (地下暴露)
  - 水源: 3 个 (东南方向 5 格外)
  - 铁矿石: 2 个 (脚下 3-5 格)
```

#### 3.2.3 可用函数清单

| 函数 | 用途 | 当前使用情况 |
|------|------|-------------|
| `bot.blockAtCursor(n)` | 视线射线追踪 | 仅在视觉截图中使用 |
| `bot.blockAt(pos)` | 指定坐标方块查询 | 已使用（周边方块、脚下/头部） |
| `bot.findBlocks({matching, maxDistance, count})` | 区域方块搜索 | 仅 3 格范围，应扩大到 8 |
| `bot.canSeeBlock(block)` | 视线遮挡检测 | **完全未使用** |
| `bot.world.raycast(origin, direction, range)` | 底层射线追踪 | **完全未使用** |
| `bot.entities` (遍历) | 实体列表 | 已使用（16 格范围） |
| `bot.nearestEntity(filter)` | 最近实体查询 | 已使用 |
| `bot.blockAtEntityCursor(entity, range)` | 任意实体视线追踪 | **完全未使用** |
| `block.light` / `block.skyLight` | 光照等级 | **完全未使用** |
| `block.hardness` / `block.diggable` | 可挖掘性 | **完全未使用** |
| `block.biome` | 方块级生物群系 | **完全未使用** |

### 3.3 实体状态跟踪

不只是在 LLM prompt 中列出附近的实体名称，而是建立一个**实体追踪表**（JS 端维护），记录每个实体的生命周期：

```
实体追踪表 (EntityTracker)：
  entityId → {
    type, name,
    firstSeen: tick,
    lastSeen: tick,
    lastPosition: Vec3,
    approachDirection: "toward" | "away" | "stationary",
    interactionCount: number,
    isHostile: boolean,
  }
```

显著事件触发记录：
- 实体**首次出现** → 写入感知缓冲区
- 实体**从远处移动到近处**（跨过 16→8 格阈值）→ 写入感知缓冲区
- 实体**消失** → 写入感知缓冲区
- 实体**状态变化**（被激怒、开始燃烧等）→ 写入感知缓冲区

（注：当前 Agent 已有 `entityHurt` 事件用于伤害检测，可用于 `isHostile` 判断）

---

## 四、感知数据处理层 —— Flash LLM 总结

### 4.1 为什么需要独立总结

原始感知数据量巨大且噪声多：
- 每 10 秒可能产生 50+ 个原始事件（方块变化、实体移动、声音...）
- 大部分是「草方块旁边还是草方块」这类无用信息
- 直接全量注入主 LLM 会填满上下文窗口，且与记忆混淆

### 4.2 Flash Summarizer 设计

```
原始感知缓冲区（累积 N 秒或 N 条事件）
       │
       ▼
┌─────────────────────────┐
│  Perception Summarizer   │  ← Flash LLM（低延迟、低成本）
│                         │
│  输入：原始事件流 + 上次摘要
│  输出：结构化环境摘要
└─────────────────────────┘
       │
       ├──→ 「环境摘要」→ 注入主 LLM 的 $ENV_SUMMARY 占位符
       ├──→ 「显著事件」→ 写入 WorkingMemory (type=observation)
       └──→ 「异常标记」→ 写入 WorkingMemory (type=discovery)
```

**Flash LLM 的职责**：

1. **去噪**：剔除平凡事件——「草方块旁边还是草方块」、同一个实体反复移动一像素等。Flash 不需要知道 Agent 的任务是什么，只需判断事件本身是否值得关注
2. **聚合**：将离散事件提炼为自然语言描述
   - 输入：`blockUpdate: grass→dirt` × 30 次 + `entitySpawn: sheep` × 5
   - 输出：「西南方向有一群羊（约 5 只）在草地上活动」
3. **趋势识别**：检测随时间的变化模式
   - 「天色逐渐变暗」
   - 「一名玩家（Steve）正在靠近，已从 20 格缩短到 10 格」
4. **异常标记**：发现客观上不寻常的事件
   - 「脚下 3 格处发现钻石矿！」
   - 「后方突然出现苦力怕，距离仅 4 格！」
   - 「听到 TNT 点燃的声音，来源在东南方向 10 格处」

**设计原则**：Flash **不需要知道 Agent 当前在做什么任务**。它只负责回答一个问题——「这段时间世界里发生了什么值得注意的事情？」——然后输出结构化的环境摘要。摘要是否有用、和任务是否相关，由 Agent Loop 的主 LLM 自己判断。

**触发频率分级**：

| 场景 | 总结频率 | 原因 |
|------|---------|------|
| 空闲/漫游 | 每 15-30 秒 | 环境变化慢，无需高频总结 |
| 代码执行中 | 每 5-10 秒 | 执行期间环境仍在变化，需要持续记录 |
| 战斗中 | 不触发 Flash | 战斗由 Reflex Layer 全权处理，毫秒级反应；战斗结果事后写入 WorkingMemory |
| 与玩家对话 | 按需 | 对话中提及环境时触发 |

### 4.3 精细信息的获取：按需观察工具

Flash Summarizer 提供的是**高层环境摘要**，不含精确坐标。当 Agent 需要精细信息（如建房子时需要知道具体哪些坐标有橡木原木）时，由 **Agent Loop 主动调用观察工具**获取：

**观察工具示例**：

| 工具 | 用途 | 返回值 |
|------|------|--------|
| `!scanArea(center, radius)` | 扫描指定区域的所有方块 | `[{name, position, light, ...}]` 精确列表 |
| `!getBlockAt(x, y, z)` | 查询单个方块的详细信息 | 方块名、光照、硬度、可挖掘性等 |
| `!getEntities(type, radius)` | 查询指定类型实体的精确位置 | `[{type, name, position, health}]` |
| `!rayScan(yaw, pitch, distance)` | 指定方向的射线扫描 | 命中方块、距离、坐标、光照 |

**调用流程**：

```
Agent Loop:
  1. 读取 $ENV_SUMMARY → 「前方是一片橡树林，大约有 8 棵树」
  2. LLM 判断：需要知道确切的树木坐标才能建房子
  3. 调用观察工具 !scanArea(自身位置, 16)
  4. 工具返回 [{oak_log, (112,64,-203)}, {oak_log, (115,64,-200)}, ...]
  5. 返回值作为工具调用结果，写入 WorkingMemory（type=action，与其他工具调用同级）
  6. 下一步 Agent Loop 的上下文中包含这些精确坐标，LLM 据此生成操作代码
```

**设计要点**：
- 观察工具的返回值在 WorkingMemory 中属于**工具执行结果**（与其他 action 同级），不单独开辟 observation 通道
- Agent 不需要坐标时，完全不调用观察工具——不浪费上下文
- 观察工具内部直接调用 JS 端的 `bot.blockAt()`、`bot.findBlocks()` 等函数，不走 Flash Summarizer

### 4.4 感知记忆与行动记忆分离

在记忆系统中，感知数据使用独立通道：

```
WorkingMemory 条目类型：
  - action          ← Agent 自身操作（含观察工具的调用结果）
  - observation     ← 环境感知（Flash Summarizer 总结的结果）
  - interaction     ← 与玩家对话
  - failure         ← 操作失败
  - discovery       ← 值得注意的发现（Flash LLM 异常标记）
  - reasoning       ← LLM 内部推理

Memory Graph 节点：
  - NodeType.event  ← 用 subtype 区分 "perception" vs "action"
```

**设计原则**：主 LLM 通过 `$ENV_SUMMARY` 获得**当前环境的清晰快照**，通过 WorkingMemory 的 `observation` 条目获得**最近的环境变化时间线**，通过观察工具获得**按需的精确坐标**，通过长期记忆 Graph 获得**过去在类似环境中的经验**。四者各司其职，不混杂。

---

## 五、代码执行期间的非阻塞感知

### 5.1 问题回顾

执行 `execute_step` 时，Agent Loop 在 `_execute_code()` 的 polling loop 中被阻塞，等待 JS 返回执行结果。这期间：
- Agent Loop 不能做任何决策
- Python 端不能主动发起感知查询
- JS 端生成的代码不会自发调用感知函数
- 仅有 Reflex Layer 可以处理生存级紧急事件

### 5.2 解决策略

#### 核心方案：JS 端感知 Worker + Agent Loop 提示词约束

**（1）提示词约束 —— 让 Agent Loop 拆分更细的任务步骤**

任务拆分的决策者是 **Agent Loop 的 LLM**（其系统提示词在 `agent/prompts/agent_loop/system.md`），而非 Coding LLM。Coding LLM 只负责根据 `step_description` 生成代码，不参与任务粒度判断。

当前 `system.md` 已有基础的拆分指引（第 40 行：「每条要能被 1-3 次 execute_step 完成」、第 114 行：「合理拆分步骤，不要试图用一次 execute_step 完成复杂任务」），但缺少**单步耗时和原子性**的具体约束。需要在 system.md 的「重要规则」中补充：

```
新增规则（约第 116 行之后）：
  - 每个 execute_step 的 step_description 应该对应一个能在 10-30 秒内完成的原子操作。
    好的描述："找到最近的橡树并收集 5 个橡木原木"
    好的描述："在工作台合成一把石镐"
    不好的描述："收集木头、合成工作台、做石镐、然后下矿挖铁直到找到钻石"
    → 这种过于庞大的描述应该拆分为 4-5 个独立的 execute_step，用 todolist 管理顺序。
```

这样每段代码执行时间短（通常 < 10 秒），自然减少了盲跑窗口。Agent Loop 在每轮循环中会根据 `$LAST_TOOL_RESULT` 看到上一步的结果，配合 Flash Summarizer 在此期间产生的 `observation` 条目，做出下一步决策。

**（2）JS 端感知 Worker —— 执行期间环境数据持续流入**

在 `minecraft_bridge.js` 中增加独立的**异步感知 Worker**，不依赖 Agent Loop 的指令：

```
JS 端三线并行：
  1. 状态推送：sendStateUpdate() 每 1 秒
  2. 代码执行：executeCode() 运行 LLM 生成的代码
  3. 感知 Worker：持续监听事件 + 定时主动扫描（新增）

感知 Worker 职责：
  - 监听所有被动事件（entitySpawn、blockUpdate、soundEffectHeard ...）
  - 每 N 秒执行一次主动扫描（blockAtCursor 多点射线）
  - 写入原始感知缓冲区
  - 通过 IPC 异步推送「紧急感知事件」（如苦力怕靠近）到 Reflex Layer
```

**关键**：感知 Worker 使用 `setInterval` 或 `while(true)` + `await`，与 `executeCode()` 共享 Node.js 事件循环但不互相阻塞。代码执行期间，被动事件和主动扫描照常运行，感知数据不会中断。

**（3）工作记忆记录时机 —— 执行前 + 执行后**

```
Execution Layer:
  1. [执行前] 将当前 $ENV_SUMMARY + 代码意图写入 WorkingMemory
     条目类型: action, 内容: "开始执行: 收集前方橡木"
  
  2. [执行中] 感知 Worker 持续记录环境事件到原始感知缓冲区
     Flash Summarizer 异步运行，产生 observation 条目写入 WorkingMemory
     代码自身可以通过 interrupt_code 机制被 Reflex 中断
  
  3. [执行后] 将执行结果 + 代码返回值写入 WorkingMemory
     条目类型: action, 内容: "执行完成: 收集了 5 个橡木原木，耗时 8 秒"
```

**与旧方案的对比**：

| | 旧方案 | 新方案 |
|---|---|---|
| 代码长度 | 无约束，可能几十到上百行 | Prompt 约束，建议 < 30 行 |
| 执行期间感知 | 完全盲跑 | 感知 Worker 持续记录 |
| 工作记忆收录 | 执行完后一次性收录 | 执行前收录一次 + 执行后收录一次 |
| 感知数据流向 | 无 | 事件 → 缓冲区 → Flash Summarizer → observation 条目 |
| Agent Loop 状态 | 阻塞在 polling loop | 仍然阻塞，但执行时间短 + 有感知数据持续流入记忆 |

### 5.3 Reflex Layer 的战斗处理与记忆记录

**战斗由 Reflex Layer 自动处理**，不经过 Agent Loop 或 Flash Summarizer：

- Reflex Layer 检测到敌对实体 → 自动切换到战斗模式 → `bot.pvp.attack(entity)`
- 战斗期间 Agent Loop 可以继续感知和决策（不阻塞），但 Reflex 优先级高于 Agent Loop 的操作
- **战斗结果写入 WorkingMemory**：战斗结束后，Reflex Layer 将战斗摘要（对手、伤害量、结果、消耗的物品）作为 `observation` 条目写入 WorkingMemory，供后续 Agent Loop 和长期记忆消化

**Reflex Layer 扩展感知能力**：

利用感知 Worker 推送的「紧急感知事件」扩展 Reflex 的检测范围：

| 新增 Reflex 检测 | 触发条件 | 动作 |
|-----------------|---------|------|
| 熔岩接近 | 前方 3 格内 blockAtCursor 命中 lava | 立即停止前进，后退 |
| 悬崖检测 | 下方 2 格 skyLight=15 + 下方 3 格外命中 air | 停止前进 |
| 溺水预警 | 头部在水中 + 氧气 < 5 | 向上游 |
| 怪物靠近 | 8 格内敌对实体正在靠近 | 自动切换战斗，中断 Agent Loop 当前操作 |

---

## 六、自主持续观察机制

### 6.1 空闲时主动环境扫描

Agent 在**非执行态**（没有代码在跑，没有 LLM 调用在进行）时，应主动进行环境扫描：

```
空闲扫描循环（感知 Worker 负责）：
  每 5 秒：快速扫描（blockAtCursor 水平 8 方向 + 平视）
  每 30 秒：完整扫描（blockAtCursor 16 方向 × 3 俯仰层）
  每 60 秒：区域方块统计（findBlocks 8 格范围聚合）
```

### 6.2 显著变化触发记录

不是所有扫描结果都记录——只有**显著变化**才写入感知缓冲区：

- 上次扫描没有的实体类型，现在出现了
- 上次扫描看到的方块，现在变了（被破坏/被放置）
- 光照水平急剧变化（天黑了/进入洞穴/离开洞穴）
- 生物群系变化（移动到了不同的生态区）
- 血量/饱食度变化（受到伤害/饥饿）

### 6.3 感知频率分级

| Agent 状态 | 被动事件监听 | 主动扫描频率 | Flash 总结频率 | 说明 |
|-----------|------------|------------|--------------|------|
| 空闲 | 全量 | 每 30 秒完整 | 每 30 秒 | 低频即可，环境变化慢 |
| 代码执行中 | 全量 | 每 10 秒快速 | 每 5-10 秒 | 执行期间环境仍在变化，感知 Worker 持续记录 |
| 战斗中 | Reflex Layer 自动操作 | 不执行主动扫描 | 不触发 Flash | 战斗由 Reflex 全权处理，结果事后写入 WorkingMemory |
| 与玩家对话 | 全量 | 按需（对话中提及环境时）| 按需 | |

**战斗中感知的特殊处理**：
- Reflex Layer 在战斗中不使用 Flash Summarizer——战斗需要的是毫秒级反应，不是语义总结
- 战斗结束后，Reflex Layer 将战斗过程摘要（对手类型、伤害量、结果、消耗物品）作为 `observation` 条目写入 WorkingMemory
- Agent Loop 在下一轮感知时，会从 WorkingMemory 中读取到「刚才经历了一场战斗」的信息

---

## 七、数据流总览

```
Minecraft 世界
    │
    ├──→ 被动事件（entitySpawn, blockUpdate, soundEffectHeard, ...）
    │       │
    │       ▼
    ├──→ 主动扫描（blockAtCursor 多点射线, findBlocks 区域统计）
    │       │
    │       ▼
    ├──→ 状态快照（health, food, position, inventory）每 1 秒
    │       │
    │       ▼
    │   原始感知缓冲区
    │       │
    │       ▼
    │   Flash LLM Summarizer（纯观测，不感知任务）
    │       │
    │       ├──→ $ENV_SUMMARY → 注入主 LLM Prompt（环境理解）
    │       ├──→ observation 条目 → WorkingMemory（环境变化时间线）
    │       └──→ discovery 条目 → WorkingMemory（异常标记）
    │
    ├──→ 紧急感知事件 ──→ Reflex Layer
    │       │                │
    │       │                ├──→ 战斗自动操作 (pvp.attack)
    │       │                ├──→ 熔岩/悬崖/溺水紧急规避
    │       │                └──→ 战斗摘要写入 WorkingMemory
    │       │                    (战后，作为 observation 条目)
    │
    └──→ Agent Loop
             │
             ├──→ 读取 $ENV_SUMMARY（环境理解）
             ├──→ 读取 WorkingMemory（最近事件 + 上次执行结果）
             ├──→ [按需] 调用观察工具（!scanArea 等）
             │         → 返回值写入 WorkingMemory（作为工具调用结果）
             ├──→ 主 LLM 决策
             ├──→ 生成代码（Prompt 约束：简短，< 30 行）
             ├──→ [执行前] 记录代码意图 → WorkingMemory
             ├──→ 执行代码（感知 Worker 在后台持续记录）
             ├──→ [执行后] 记录执行结果 → WorkingMemory
             └──→ 回到循环
```

---

## 八、实现优先级建议

| 优先级 | 模块 | 收益 | 复杂度 |
|--------|------|------|--------|
| P0 | 扩大感知半径（3→8 格方块，16→32 格实体） | 立竿见影 | 低 |
| P0 | 被动事件监听（entitySpawn/Gone，blockUpdate，soundEffectHeard，rain） | 建立连续事件流 | 低 |
| P1 | 感知 Worker 独立运行（JS 端定时扫描 + 异步推送紧急事件） | 被动感知独立于 Agent Loop | 中 |
| P1 | Perception Summarizer（Flash LLM 纯观测总结，不管任务） | 解决数据过载和记忆混杂 | 中 |
| P1 | Prompt 约束代码长度 + 工作记忆执行前/后分别收录 | 缩短盲跑窗口，感知数据持续流入 | 低 |
| P2 | Reflex Layer 战斗结果写入 WorkingMemory | 战斗经验可被记忆和复盘 | 低 |
| P2 | 主动射线扫描（blockAtCursor 多点采样，地形理解） | 空间结构感知 | 中 |
| P2 | 实体状态跟踪表 | 趋势感知、威胁预警 | 中 |
| P3 | 按需观察工具（!scanArea, !getBlockAt 等） | 精细化操作时获取精确坐标 | 低 |
