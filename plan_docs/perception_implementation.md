# 感知层实现方案

## 总览

基于 [perception.md](perception.md) 的设计方案，本文档描述具体的代码实现方案。遵循以下原则：
- **封装**：每个感知模块是独立的类/文件，对外暴露最小接口
- **解耦**：模块之间通过 IPC 消息或共享状态通信，不直接调用对方内部方法
- **渐进**：按 P0 → P1 → P2 → P3 分阶段实现，每阶段可独立上线

### 新增/修改文件清单

| 文件 | 操作 | 所属模块 |
|------|------|---------|
| `agent/bridge/perception_worker.js` | **新增** | JS 感知 Worker |
| `agent/bridge/minecraft_bridge.js` | 修改 | 集成 PerceptionWorker、扩展状态字段 |
| `agent/brain/perception/__init__.py` | **新增** | Python 感知模块 |
| `agent/brain/perception/perception_buffer.py` | **新增** | 原始感知缓冲区 |
| `agent/brain/perception/summarizer.py` | **新增** | Flash LLM 总结器 |
| `agent/brain/perception/perception_manager.py` | **新增** | 感知总管（协调 buffer + summarizer）|
| `agent/brain/agent_brain/brain_coordinator.py` | 修改 | 集成 PerceptionManager、新增 IPC handler |
| `agent/brain/agent_brain/agent_loop_layer.py` | 修改 | 注入 $ENV_SUMMARY、新增观察工具 |
| `agent/brain/agent_brain/reflex_layer.py` | 修改 | 战斗结果写入 WorkingMemory |
| `agent/prompts/agent_loop/system.md` | 修改 | 任务粒度约束 |
| `agent/brain/tools/scan_area_tool.py` | **新增** | 按需观察工具 |
| `agent/brain/tools/tool_registry.py` | 修改 | 注册新工具 |
| `agent/prompts/variable_config.yaml` | 修改 | 新增 $ENV_SUMMARY 映射 |
| `agent/prompts/data_providers.py` | 修改 | 新增 get_env_summary 函数 |

---

## 阶段一：P0 — 扩大感知半径 + 被动事件流

**目标**：最小改动、最快见效。扩大扫描范围，建立连续事件流。

### 1.1 扩大方块扫描范围

**文件**：`agent/bridge/minecraft_bridge.js`

修改 `getNearbyBlocks()` 方法（~第 730 行），将 `maxDistance` 从 3 改为 8，同时增加 count 上限。返回值结构不变（仍是去重后的 blocks 数组），Python 端无需任何修改。`$NEARBY_BLOCKS` 占位符的输出自动包含更多方块。

### 1.2 扩大实体扫描范围

**文件**：`agent/bridge/minecraft_bridge.js`

修改 `getNearbyEntities()` 方法（~第 710 行），将距离阈值从 16 改为 32。返回值结构不变，Python 端无需修改。

### 1.3 创建 JS 感知 Worker

**新文件**：`agent/bridge/perception_worker.js`

独立的 JS 类 `PerceptionWorker`，负责被动事件监听和定时主动扫描。与 `BrainBridge` 通过回调函数 `onEvent(eventType, data)` 解耦——Worker 不持有 BrainBridge 引用，不知道外部如何处理事件。

**核心结构**：

```javascript
class PerceptionWorker {
    constructor(bot, onEvent, options = {}) {
        this.bot = bot;
        this.onEvent = onEvent;  // 解耦：通过回调向外推送原始事件
        this.options = {
            scanIntervalMs: 10000,            // 主动扫描间隔
            entityMoveThrottleMs: 3000,       // entityMoved 节流
            blockUpdateThrottleMs: 1000,      // blockUpdate 节流
            ...options
        };
    }

    start()  { /* 绑定事件 + 启动扫描定时器 */ }
    stop()   { /* 解绑事件 + 清除定时器 */ }
}
```

**绑定的被动事件**：

| 事件 | 回调 | 输出 event_type | 备注 |
|------|------|----------------|------|
| `entitySpawn` | `_onEntitySpawn` | `entity_spawn` | 过滤自身 |
| `entityGone` | `_onEntityGone` | `entity_gone` | 过滤自身 |
| `entityMoved` | `_onEntityMoved` | `entity_approaching` | 节流 3s + 仅靠近时推送 |
| `blockUpdate` | `_onBlockUpdate` | `block_update` | 节流 1s |
| `soundEffectHeard` | `_onSoundHeard` | `sound_heard` | 过滤距离 > 32 格、音量 < 0.3 |
| `playerJoined` | `_onPlayerJoined` | `player_joined` | |
| `playerLeft` | `_onPlayerLeft` | `player_left` | |
| `rain` | `_onRain` | `weather_change` | |

**主动扫描**：每 `scanIntervalMs`（默认 10 秒）执行一次 8 方向平视射线扫描 + 1 次向下 45° 扫描（悬崖检测）。输出 event_type 为 `quick_scan`。

**节流策略**：
- `entityMoved`：同一 entityId 每 3 秒最多推送一次，且仅当距离缩短超过 1 格时（即实体正在靠近）才推送
- `blockUpdate`：同一坐标每秒最多推送一次

### 1.4 在 BrainBridge 中集成 PerceptionWorker

**文件**：`agent/bridge/minecraft_bridge.js`

最小的集成量。在 `BrainBridge` 构造函数中新增两个属性：

```javascript
this.perceptionWorker = null;
this._rawPerceptionEvents = [];   // 累积批次
```

在 `spawn` 事件处理中（`stateUpdateInterval` 启动之后）创建并启动 Worker：

```javascript
const PerceptionWorker = require('./perception_worker.js');
this.perceptionWorker = new PerceptionWorker(
    this.bot,
    (eventType, data) => {
        this._rawPerceptionEvents.push({
            event_type: eventType,
            data: data,
            timestamp: Date.now()
        });
    }
);
this.perceptionWorker.start();
```

新增一个推送间隔（每 3 秒将累积的感知事件批量发送给 Python）：

```javascript
this._perceptionPushInterval = setInterval(() => {
    if (this._rawPerceptionEvents.length > 0) {
        const batch = this._rawPerceptionEvents.splice(0);
        this.sendMessage({
            type: 'perception_events',
            data: { events: batch }
        }).catch(() => {});
    }
}, 3000);
```

在 `gracefulShutdown()` 中清理：

```javascript
if (this.perceptionWorker) this.perceptionWorker.stop();
if (this._perceptionPushInterval) clearInterval(this._perceptionPushInterval);
```

### 1.5 Python 端接收感知事件

**文件**：`agent/brain/agent_brain/brain_coordinator.py`

在 `_register_ipc_handlers()` 中新增一个 handler，将 JS 推送的感知事件暂存到 SharedState：

```python
async def handle_perception_events(data):
    events = data.get('events', [])
    if events:
        current = await self.shared_state.get('raw_perception_events')
        current.extend(events)
        if len(current) > 500:
            current = current[-500:]
        await self.shared_state.update({'raw_perception_events': current})

self.ipc_server.register_handler('perception_events', handle_perception_events)
```

在 SharedState 中新增字段 `raw_perception_events = []`。

**影响范围总结**：JS 端新增 `perception_worker.js`（~160 行），`minecraft_bridge.js` 新增 ~25 行。Python 端 `brain_coordinator.py` 新增 ~15 行。现有逻辑不受影响。

---

## 阶段二：P1 — Flash LLM 总结器 + 感知总管

**目标**：用 Flash LLM 将原始感知事件定期总结为结构化的环境摘要，并将显著事件写入记忆。

### 2.1 模块结构

```
agent/brain/perception/
├── __init__.py          # 导出 PerceptionManager
├── perception_buffer.py # 线程安全的环形缓冲区
├── summarizer.py        # Flash LLM 总结器
└── perception_manager.py # 感知总管（对外唯一接口）
```

### 2.2 PerceptionBuffer — 原始感知缓冲区

**文件**：`agent/brain/perception/perception_buffer.py`

内存中的环形缓冲区，使用 `asyncio.Lock` 保证线程安全。

对外接口：
- `async append(event)` — 追加单条事件
- `async extend(events)` — 批量追加
- `async consume()` — 取出全部事件并清空（供 Summarizer 消费）
- `is_empty` — 属性，是否有待处理事件

内部限制 `max_size=500`，超出时自动丢弃最早的事件。

### 2.3 PerceptionSummarizer — Flash LLM 总结器

**文件**：`agent/brain/perception/summarizer.py`

核心职责：消费原始感知事件 → 调用 Flash LLM → 产出结构化结果。

```python
class PerceptionSummarizer:
    def __init__(self, llm, model="claude-haiku-4-5"):
        self.llm = llm
        self.model = model
        self._previous_summary = ""

    async def summarize(events) -> {
        "env_summary": str,     # 注入 $ENV_SUMMARY
        "observations": [str],  # 写入 WorkingMemory (type=observation)
        "discoveries": [str],   # 写入 WorkingMemory (type=discovery)
    }
```

**Prompt 设计要点**：
- 输入包含：上次摘要（保证连续性）+ 最近的事件列表（每事件一行，简洁格式）
- 明确指示：纯观测心态，不知道 Agent 的任务
- 输出严格 JSON，三个字段分别对应环境快照、日常变化、异常发现
- `max_tokens=512`，Flash 模型输出简短

**事件格式化示例**：
```
[实体出现] mob:skeleton 于 (105,64,200)
[声音] mob.zombie.groan 来自 (110,63,200) 距离 12 格 音量 0.8
[方块变化] (100,64,200) grass_block → dirt
[扫描] 命中: oak_log (5格, 光照:15/15); water (12格, 光照:15/15)
```

### 2.4 PerceptionManager — 感知总管

**文件**：`agent/brain/perception/perception_manager.py`

对外仅暴露三个接口，内部定时循环独立运行：

```python
class PerceptionManager:
    def __init__(self, memory_router, llm, summarizer_model, default_summary_interval=15.0):
        self.buffer = PerceptionBuffer(max_size=500)
        self.summarizer = PerceptionSummarizer(llm, model=summarizer_model)
        self.memory_router = memory_router

    async def start(self)  # 启动后台总结循环
    async def stop(self)   # 停止循环
    def get_env_summary(self) -> str  # 返回当前环境摘要（供 Agent Loop 注入）
```

**内部循环逻辑**：每 `default_summary_interval` 秒（默认 15 秒）：
1. 检查 buffer 是否有事件
2. 消费事件 → 调用 Summarizer → 更新 `_env_summary`
3. 将 `observations` 和 `discoveries` 分别写入 `memory_router`

### 2.5 在 BrainCoordinator 中集成

**文件**：`agent/brain/agent_brain/brain_coordinator.py`

三处修改：
- `__init__` 中创建 `PerceptionManager` 实例
- `start()` 中调用 `await self.perception_manager.start()`
- `_register_ipc_handlers` 中的 `handle_perception_events` 改为直接写入 `perception_manager.buffer`
- `shutdown()` 中调用 `await self.perception_manager.stop()`

### 2.6 在 Agent Loop 中注入 $ENV_SUMMARY

四文件联动，仅需各增几行：

**`agent_loop_layer.py`** — 在 `build_prompt()` 的 context 字典中新增：

```python
context['ENV_SUMMARY'] = self.brain.perception_manager.get_env_summary()
```

**`system.md`** — 在「当前游戏状态」区域新增：

```markdown
## 环境观测（持续感知）

$ENV_SUMMARY

> 以上环境观测由独立的感知系统持续记录和总结。
> 它不关心你当前的任务，只是告诉你世界发生了什么。
```

**`variable_config.yaml`** — 新增一行映射：

```yaml
ENV_SUMMARY: get_env_summary
```

**`data_providers.py`** — 新增函数并在 PROVIDER_FUNCTIONS 中注册：

```python
@staticmethod
def get_env_summary(context):
    return context.get('ENV_SUMMARY', '暂无环境信息。')
```

---

## 阶段三：P1 — Agent Loop 任务粒度约束

**文件**：`agent/prompts/agent_loop/system.md`

在「重要规则」（~第 116 行）中新增一条：

```markdown
- 每个 execute_step 的 step_description 应对应一个能在 **10-30 秒内完成** 的原子操作。
  **好的描述（单一目标）**：
    "找到最近的橡树并收集 5 个橡木原木"
    "在工作台合成一把石镐"
    "走到坐标 (100, 64, -200) 并放置一个火把"
  **不好的描述（跨多个子目标）**：
    "收集木头、合成工作台、做石镐、然后下矿挖铁直到找到钻石"
  → 这种描述必须拆分为多个独立的 execute_step，用 todolist 管理顺序。
  → 每次执行后，先检查执行结果和 $ENV_SUMMARY 中的环境变化，再决定下一步。
```

---

## 阶段四：P2 — Reflex Layer 战斗记忆

**文件**：`agent/brain/agent_brain/reflex_layer.py`

在战斗模式退出时（self_defense / cowardice 结束），将战斗摘要写入 WorkingMemory：

```python
async def _finalize_combat(self, combat_info: dict):
    summary = (
        f"战斗：对手 {combat_info['entity_type']}，"
        f"起始血量 {combat_info['initial_health']}，"
        f"结束血量 {combat_info['final_health']}，"
        f"结果 {combat_info['result']}"
    )
    await self.memory_router.log('observation', summary)
```

在 self_defense 和 cowardice 模式中记录 `initial_health`（进入时）和 `final_health`（退出时），退出时调用 `_finalize_combat` 写入。

---

## 阶段五：P3 — 按需观察工具

**目标**：当 Agent 需要精确坐标时，调用观察工具获取详细方块/实体数据。

### 5.1 ScanAreaTool

**新文件**：`agent/brain/tools/scan_area_tool.py`

```python
class ScanAreaTool:
    """扫描指定坐标半径内的所有非空气方块，返回精确坐标列表。"""

    @property
    def description(self) -> str:
        return (
            "**scan_area(center_x, center_y, center_z, radius)**："
            "扫描指定坐标半径内所有非空气方块的精确位置。"
            "当你需要建房子、挖矿、或做任何需要精确坐标的操作时使用。"
        )

    async def execute(self, args: dict) -> str:
        # 通过 IPC 发送 scan_area 命令到 JS
        # JS 端执行 bot.findBlocks() → 返回方块名+坐标列表
        # 格式化返回给 Agent Loop
```

### 5.2 JS 端支持

在 `minecraft_bridge.js` 的 `handleCommand()` switch 中新增 `scan_area` case，调用 `bot.findBlocks()` 后通过 `sendMessage` 返回结果。

### 5.3 注册工具

在 `brain_coordinator.py` 的 `_register_tools()` 中添加：

```python
from brain.tools.scan_area_tool import ScanAreaTool
self.tool_registry.register('scan_area', ScanAreaTool(self.ipc_server))
```

---

## 数据流总览

```
 PerceptionWorker (JS)                       PerceptionManager (Python)
 ════════════════════                       ═══════════════════════════
                                              ┌─────────────────────┐
 ┌──────────────────┐                         │  PerceptionBuffer    │
 │ 被动事件监听      │──→ raw events ──→ IPC ──→ │  (累积原始事件)       │
 │ (entitySpawn...) │                         └─────────┬───────────┘
 └──────────────────┘                                   │
                                                        ▼
 ┌──────────────────┐                         ┌─────────────────────┐
 │ 主动扫描          │──→ quick_scan ──→ IPC ──→ │  Summarizer (Flash) │
 │ (8方向射线)       │                         │  → env_summary      │
 └──────────────────┘                         │  → observations     │
                                              │  → discoveries      │
                                              └─────────┬───────────┘
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                    $ENV_SUMMARY  WorkingMemory  WorkingMemory
                                    (Agent Loop)  (observation) (discovery)
```

所有模块之间的通信都通过已有接口（IPC 消息、SharedState、MemoryRouter），不产生跨模块的深层依赖。

---

## 实现顺序

| 步骤 | 内容 | 涉及文件 | 预计工作量 |
|------|------|---------|-----------|
| 1 | 扩大扫描范围（8 格方块、32 格实体） | `minecraft_bridge.js` 2 处 | 5 分钟 |
| 2 | 创建 PerceptionWorker + 集成到 BrainBridge | `perception_worker.js`(新) + `minecraft_bridge.js` | 1 小时 |
| 3 | Python 端接收感知事件 | `brain_coordinator.py` | 15 分钟 |
| 4 | 创建 PerceptionBuffer + Summarizer + Manager | 3 个新文件 | 1.5 小时 |
| 5 | 集成 PerceptionManager 到 BrainCoordinator | `brain_coordinator.py` | 15 分钟 |
| 6 | 注入 $ENV_SUMMARY 到 Agent Loop | `agent_loop_layer.py` + `system.md` + `variable_config.yaml` + `data_providers.py` | 20 分钟 |
| 7 | 修改 system.md 任务粒度约束 | `system.md` | 10 分钟 |
| 8 | Reflex Layer 战斗记忆写入 | `reflex_layer.py` | 30 分钟 |
| 9 | 按需观察工具 scan_area | `scan_area_tool.py`(新) + `minecraft_bridge.js` + `brain_coordinator.py` | 1 小时 |
