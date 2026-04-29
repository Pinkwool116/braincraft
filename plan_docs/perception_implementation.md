# 感知层实现方案

## 总览

基于 [perception.md](perception.md) 的设计方案，本文档描述具体的代码实现方案。遵循以下原则：
- **封装**：每个感知模块是独立的类/文件，对外暴露最小接口
- **解耦**：模块之间通过 IPC 消息或共享状态通信，不直接调用对方内部方法
- **渐进**：按 P0 → P1 → P2 → P3 分阶段实现，每阶段可独立上线

### 新增/修改文件清单

| 文件 | 操作 | 所属模块 |
|------|------|---------|
| `agent/bridge/perception_worker.js` | **新增** | JS 感知 Worker（多级扫描 + 紧急事件推送） |
| `agent/bridge/minecraft_bridge.js` | 修改 | 集成 PerceptionWorker、扩展状态字段 |
| `agent/brain/perception/__init__.py` | **新增** | Python 感知模块 |
| `agent/brain/perception/perception_buffer.py` | **新增** | 原始感知缓冲区 |
| `agent/brain/perception/event_ticker.py` | **新增** | EventTicker — 纯代码事件聚合（每 2s → WorkingMemory） |
| `agent/brain/perception/terrain_analyzer.py` | **新增** | TerrainAnalyzer — Flash LLM 地形理解（每 30s → WorkingMemory） |
| `agent/brain/perception/perception_manager.py` | **新增** | 感知总管（协调 buffer + ticker + analyzer） |
| `agent/brain/agent_brain/brain_coordinator.py` | 修改 | 集成 PerceptionManager、新增 IPC handler |
| `agent/brain/agent_brain/reflex_layer.py` | 修改 | 战斗结果写入 WorkingMemory、紧急事件响应 |
| `agent/brain/data_manager/memory_graph/working_memory.py` | 修改 | observation 条目不计入 consolidate 配额 |
| `agent/prompts/agent_loop/system.md` | 修改 | 任务粒度约束 |
| `agent/brain/tools/scan_area_tool.py` | **新增** | 按需观察工具 |
| `agent/brain/tools/tool_registry.py` | 修改 | 注册新工具 |

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
    constructor(bot, onEvent, onUrgent, options = {}) {
        this.bot = bot;
        this.onEvent = onEvent;    // 解耦：通过回调向外推送普通原始事件
        this.onUrgent = onUrgent;  // 解耦：紧急事件直推 Reflex Layer（不经过缓冲区）
        this.options = {
            quickScanIntervalMs: 5000,        // 快速扫描间隔（8方向平视）
            fullScanIntervalMs: 30000,        // 完整扫描间隔（16方向×3俯仰）
            blockStatsIntervalMs: 60000,      // 区域方块统计间隔
            entityMoveThrottleMs: 3000,       // entityMoved 节流
            blockUpdateThrottleMs: 1000,      // blockUpdate 节流
            ...options
        };
    }

    start()  { /* 绑定事件 + 启动多级扫描定时器 */ }
    stop()   { /* 解绑事件 + 清除定时器 */ }
}
```

**多级主动扫描**（三级定时器，互不阻塞）：

| 扫描级别 | 间隔 | 内容 | 输出 event_type |
|---------|------|------|----------------|
| 快速扫描 | 5s | 8 方向平视射线 | `quick_scan` |
| 完整扫描 | 30s | 16 方向 × 3 俯仰层（48 采样点） | `full_scan` |
| 方块统计 | 60s | `findBlocks` 8 格范围聚合统计 | `block_stats` |

**紧急事件直推**（不经过缓冲区，直接走 `onUrgent` 回调）：

| 紧急事件 | 触发条件 | 推送给 |
|---------|---------|--------|
| `hostile_close` | 敌对实体进入 8 格且正在靠近 | Reflex Layer |
| `lava_nearby` | 前方 3 格内射线命中 lava | Reflex Layer |
| `cliff_ahead` | 下方 3 格外命中 air + skyLight=15 | Reflex Layer |
| `drowning` | 头部在水中 + 氧气 < 5 | Reflex Layer |

这些紧急事件绕过 PerceptionBuffer → Flash Summarizer 的慢通道，直接推送 Reflex Layer 做毫秒级反应。

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
    // onEvent: 普通感知事件 → 累积批次 → 定时推送到 Python PerceptionBuffer
    (eventType, data) => {
        this._rawPerceptionEvents.push({
            event_type: eventType,
            data: data,
            timestamp: Date.now()
        });
    },
    // onUrgent: 紧急事件 → 立即单条推送到 Python Reflex Layer
    (urgentType, data) => {
        this.sendMessage({
            type: 'perception_urgent',
            data: { event_type: urgentType, data: data, timestamp: Date.now() }
        }).catch(() => {});
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

在 `_register_ipc_handlers()` 中新增两个 handler：

```python
# 普通感知事件 → 写入 PerceptionBuffer（阶段二集成后）
async def handle_perception_events(data):
    events = data.get('events', [])
    if events and hasattr(self, 'perception_manager'):
        await self.perception_manager.buffer.extend(events)
    # 阶段一临时：暂存到 SharedState
    elif events:
        current = await self.shared_state.get('raw_perception_events')
        current.extend(events)
        if len(current) > 500:
            current = current[-500:]
        await self.shared_state.update({'raw_perception_events': current})

# 紧急感知事件 → 直接推送到 Reflex Layer
async def handle_perception_urgent(data):
    event_type = data.get('event_type')
    event_data = data.get('data', {})
    if hasattr(self, 'reflex_layer'):
        await self.reflex_layer.handle_perception_urgent(event_type, event_data)

self.ipc_server.register_handler('perception_events', handle_perception_events)
self.ipc_server.register_handler('perception_urgent', handle_perception_urgent)
```

在 SharedState 中新增字段 `raw_perception_events = []`（阶段一临时使用，阶段二由 PerceptionBuffer 接管）。

**ReflexLayer 新增方法**：`handle_perception_urgent(event_type, data)` — 接收来自 PerceptionWorker 的紧急推送，触发对应的 Reflex 响应（切换战斗模式、紧急规避等），无需等待 Agent Loop 的下一次轮询。

**影响范围总结**：JS 端新增 `perception_worker.js`（~200 行），`minecraft_bridge.js` 新增 ~35 行。Python 端 `brain_coordinator.py` 新增 ~25 行，`reflex_layer.py` 新增 ~20 行。现有逻辑不受影响。

---

## 阶段二：P1 — EventTicker（纯代码事件聚合）+ 感知总管

**目标**：用纯代码（无 LLM）将原始感知事件每 2 秒聚合为结构化 observation 条目，写入 WorkingMemory。

**前置验证**：无需验证（不调用 LLM）。

### 2.1 模块结构

```
agent/brain/perception/
├── __init__.py           # 导出 PerceptionManager
├── perception_buffer.py  # 环形缓冲区
├── event_ticker.py       # EventTicker — 纯代码事件聚合（每 2s → WorkingMemory）
├── terrain_analyzer.py   # TerrainAnalyzer — Flash LLM 地形理解（阶段四）
└── perception_manager.py # 感知总管（协调 buffer + ticker + analyzer）
```

### 2.2 PerceptionBuffer — 原始感知缓冲区

**文件**：`agent/brain/perception/perception_buffer.py`

内存中的环形缓冲区，使用 `asyncio.Lock` 保证线程安全。

对外接口：
- `async append(event)` — 追加单条事件
- `async extend(events)` — 批量追加
- `async consume()` — 取出全部事件并清空（供 EventTicker 消费）
- `is_empty` — 属性，是否有待处理事件

内部限制 `max_size=500`，超出时自动丢弃最早的事件。

### 2.3 EventTicker — 纯代码事件聚合器

**文件**：`agent/brain/perception/event_ticker.py`

核心职责：从原始感知事件中按规则聚合，生成结构化 observation 文本。**不调用 LLM**。

**关键概念——连续监视，不是定时采样**：PerceptionWorker 的 Mineflayer 事件监听器在 JS 端**持续运行**，游戏事件（entitySpawn、blockUpdate、soundEffectHeard 等）发生的瞬间就被捕获并推入缓冲区。2 秒只是 EventTicker 的**消费节奏**——从缓冲区取出这段时间积累的事件、聚合、写入记忆。不存在"观测时才去看"的问题——事件是服务端主动推送的，Worker 一直在听。

```python
class EventTicker:
    """纯代码事件聚合器。每 2 秒消费缓冲区事件，生成 observation 条目。"""

    def __init__(self, max_entities: int = 5, max_sounds: int = 5):
        self.max_entities = max_entities
        self.max_sounds = max_sounds
        # 跨 tick 追踪：实体需记录 firstSeen 才能判断"新出现"和"消失"
        self._known_entities: dict[str, dict] = {}

    def aggregate(self, events: list) -> str | None:
        """
        聚合一批事件为 observation 文本。
        返回 None 表示没有任何值得记录的内容（此时不写入 WorkingMemory）。
        """
```

**聚合规则实现**（纯代码，无 LLM）：

```python
def aggregate(self, events: list) -> str | None:
    new_entities = []       # 新出现的实体
    approaching = []        # 敌对实体靠近中
    gone_entities = []      # 消失的实体
    sounds = []             # 声音事件（去重）
    weather_changes = []    # 天气变化
    block_changes = []      # 重要方块变化

    for event in events:
        match event['event_type']:
            case 'entity_spawn':
                self._handle_entity_spawn(event, new_entities)
            case 'entity_approaching':
                self._handle_approaching(event, approaching)
            case 'entity_gone':
                self._handle_entity_gone(event, gone_entities)
            case 'sound_heard':
                self._handle_sound(event, sounds)
            case 'weather_change':
                weather_changes.append(event['data']['new_weather'])
            case 'block_update':
                self._handle_block_update(event, block_changes)

    # 组装输出
    parts = []
    if new_entities:
        items = [f"{e['name']}({e['direction']}{e['distance']}格)" for e in new_entities[:self.max_entities]]
        parts.append(f"新实体: {', '.join(items)}")
    if approaching:
        items = [f"{e['name']}({e['direction']}{e['distance']}格靠近中)" for e in approaching]
        parts.append(f"威胁靠近: {', '.join(items)}")
    if gone_entities:
        names = list(set(e['name'] for e in gone_entities))[:self.max_entities]
        parts.append(f"实体消失: {', '.join(names)}")
    if sounds:
        items = [f"{s['name']}({s['direction']}{s['distance']}格)" for s in sounds[:self.max_sounds]]
        parts.append(f"声音: {', '.join(items)}")
    if weather_changes:
        parts.append(f"天气: {' → '.join(weather_changes)}")
    if block_changes:
        parts.append(f"方块变化: {', '.join(block_changes[:5])}")

    if not parts:
        return None  # 不写入 WorkingMemory

    timestamp = datetime.now().strftime('%H:%M:%S')
    return f"[感知 {timestamp}] " + " | ".join(parts)
```

**关键实现细节**：

- **方向计算**：根据 Agent 当前位置和事件坐标，计算相对方向（东/南/西/北/东北等）。如果事件不含坐标（如部分声音），省略方向
- **实体追踪**：`_known_entities` 字典跨 tick 维护。新事件中出现的 entityId 不在字典中 → "新实体"；ticker 消费时发现上次在字典中但本轮未出现的实体 → "实体消失"（仅在消失后第一次写入，之后不再重复）
- **声音去重**：同一声音类型 + 同一来源方向 → 5 秒内只记录一次，标注次数（如"僵尸低吼×3"）
- **方块变化过滤**：只记录矿石（`*_ore`）、液体（`water`、`lava`）、爆炸相关（`tnt`）、以及 Agent 附近集中发生的变化（同方向 > 3 次/5s）

**输出示例**：
```
[感知 12:03:05] 新实体: 骷髅(东8格), 僵尸(北6格), 玩家Steve(南15格) | 威胁靠近: 僵尸(北6格靠近中) | 声音: 骷髅咯咯声(东8格), 僵尸低吼×2(北6格) | 天气: Clear → Rain
```

### 2.4 PerceptionManager — 感知总管

**文件**：`agent/brain/perception/perception_manager.py`

```python
class PerceptionManager:
    def __init__(self, memory_router, llm=None,
                 ticker_interval=2.0, terrain_interval=30.0):
        self.buffer = PerceptionBuffer(max_size=500)
        self.ticker = EventTicker()
        self.terrain_analyzer = TerrainAnalyzer(llm) if llm else None
        self.memory_router = memory_router

        self._ticker_interval = ticker_interval
        self._terrain_interval = terrain_interval
        self._last_terrain_position = None
        self._running = False

    async def start(self):
        """启动后台循环（ticker + terrain 各自独立定时器）。"""
        self._running = True
        self._ticker_task = asyncio.create_task(self._ticker_loop())
        if self.terrain_analyzer:
            self._terrain_task = asyncio.create_task(self._terrain_loop())

    async def stop(self):
        self._running = False
        for task in [getattr(self, '_ticker_task', None),
                     getattr(self, '_terrain_task', None)]:
            if task:
                task.cancel()
```

**EventTicker 循环**（每 2 秒，纯代码，不调用 LLM）：

```python
async def _ticker_loop(self):
    while self._running:
        await asyncio.sleep(self._ticker_interval)
        if self.buffer.is_empty:
            continue
        events = await self.buffer.consume()
        text = self.ticker.aggregate(events)
        if text:
            await self.memory_router.log('observation', text,
                                         consolidate_weight=0)
```

**TerrainAnalyzer 循环**（每 30 秒或位置变化 > 8 格，调用 Flash LLM）：

```python
async def _terrain_loop(self):
    while self._running:
        await asyncio.sleep(self._terrain_interval)
        pos = self._get_current_position()
        if self._last_terrain_position and self._distance(pos, self._last_terrain_position) < 8:
            continue  # 位置变化不大，跳过
        scan_data = await self._get_latest_scan()
        if not scan_data:
            continue
        text = await self.terrain_analyzer.analyze(scan_data)
        if text:
            await self.memory_router.log('observation', text,
                                         consolidate_weight=0)
            self._last_terrain_position = pos
```

**关键设计**：ticker 和 terrain 是**两个独立的后台定时器**，互不阻塞。ticker 永远准时每 2 秒运行（纯代码，< 1ms）；terrain 在后台异步调用 Flash LLM（2-3 秒），不影响 ticker。

### 2.5 WorkingMemory consolidate 配额修改

**文件**：`agent/data_manager/memory_graph/working_memory.py`

修改 `log()` 方法，新增 `consolidate_weight` 参数：

```python
async def log(self, entry_type: str, content: str,
              consolidate_weight: int = 1):
    """
    consolidate_weight:
      1  — 计入 consolidate 触发配额（action, reasoning, interaction 等）
      0  — 不计入配额，但仍参与 consolidate 内容合并（observation）
    """
    entry = {
        'type': entry_type,
        'content': content,
        'timestamp': time.time(),
        'consolidate_weight': consolidate_weight
    }
    self.timeline.append(entry)
    if consolidate_weight > 0:
        self._entries_since_last_consolidation += consolidate_weight
```

这样 EventTicker 和 TerrainAnalyzer 写入的 observation 条目（`consolidate_weight=0`）不会触发 consolidate，但 consolidate 发生时它们的环境上下文会一并合并到摘要中。

### 2.6 在 BrainCoordinator 中集成

**文件**：`agent/brain/agent_brain/brain_coordinator.py`

修改点：
- `__init__` 中创建 `PerceptionManager` 实例（传入 `memory_router` 和 `llm`）
- `start()` 中调用 `await self.perception_manager.start()`
- `_register_ipc_handlers` 中：
  - `handle_perception_events` → 写入 `self.perception_manager.buffer`
  - `handle_perception_urgent` → 路由到 `self.reflex_layer.handle_perception_urgent()`
- `shutdown()` 中调用 `await self.perception_manager.stop()`

**不需要修改的文件（已删除）**：
- ~~`agent_loop_layer.py`~~ — 不需要注入 `$ENV_SUMMARY`
- ~~`system.md`~~ — 不需要新增环境观测区域（observation 已在 `$WORKING_MEMORY` 中）
- ~~`variable_config.yaml`~~ — 不需要新变量映射
- ~~`data_providers.py`~~ — 不需要 `get_env_summary` 函数

### 2.7 构建 Prompt 前的主动观察

Agent Loop 构建 prompt 时，`$WORKING_MEMORY` 已包含最近的 observation 条目。为确保即时环境信息也是最新的，在 `build_prompt()` 之前增加一步：

```python
# agent_loop_layer.py — build_prompt() 开头
async def build_prompt(self, ...):
    # 确保状态快照是最新的（触发一次即时刷新）
    await self.shared_state.refresh_if_stale(max_age_seconds=2.0)
    # ... 继续构建 prompt
```

这确保 `$NEARBY_BLOCKS`、`$NEARBY_ENTITIES` 等 prompt 变量反映的是当前时刻（而非上次状态推送）的数据。这不涉及记忆写入，只是状态刷新。

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
  → 每次执行后，先检查执行结果和 $WORKING_MEMORY 中的 observation 条目，再决定下一步。
```

---

## 阶段四：P2 — TerrainAnalyzer（Flash LLM 地形理解）

**目标**：用 Flash LLM 从扫描数据中理解地形结构，写入 WorkingMemory。

**前置验证**：用测试脚本验证 DeepSeek Flash API 延迟。测试表明简短输出约 2 秒，冗长输出约 10 秒。地形分析 prompt 目标输出控制在 200 字以内，预估 2-3 秒。

### 4.1 TerrainAnalyzer 实现

**文件**：`agent/brain/perception/terrain_analyzer.py`

```python
class TerrainAnalyzer:
    """Flash LLM 地形理解。从扫描数据中推理空间结构。"""

    def __init__(self, llm, model="deepseek-v4-flash"):
        self.llm = llm
        self.model = model
        self._last_result = ""
        self._consecutive_failures = 0
        self._max_failures = 3

    async def analyze(self, scan_data: dict) -> str | None:
        """
        输入: scan_data = {
            'ray_samples': [(yaw, pitch, block_name, distance, light), ...],
            'block_stats': "聚合方块统计文本",
            'biome': "plains",
            'time_label': "Day"
        }
        返回: 地形描述文本，或 None（失败时）
        """
```

**Prompt 设计**：
- 输入：48 个采样点的格式化列表 + 区域方块统计 + 生物群系 + 时间
- 输出：一段 100-200 字的自然语言地形描述
- 不提及 Agent 任务，纯客观地形描述
- `max_tokens=256`

**容错**：同 EventTicker 无关。Flash API 失败时保留上一次结果。连续失败 3 次后降级为模板拼接（不调用 LLM）。

### 4.2 集成到 PerceptionManager

已在阶段二的 `PerceptionManager._terrain_loop()` 中实现。TerrainAnalyzer 作为可选组件（`llm` 为 None 时跳过）。

---

## 阶段五：P2 — Reflex Layer 战斗记忆

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

## 阶段六：P3 — 按需观察工具

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
 │ (entitySpawn...) │                         └──────────┬──────────┘
 └──────────────────┘                                    │
                                                         ▼
 ┌──────────────────┐                         ┌─────────────────────┐
 │ 多级主动扫描      │──→ scans ────→ IPC ──→  │  EventTicker         │
 │ (5s/30s/60s)     │                         │  纯代码, 每 2s       │
 └──────────────────┘                         │  → observation       │
                                              └──────────┬──────────┘
 ┌──────────────────┐                                    │
 │ 紧急事件          │──→ urgent ──→ IPC ──→              ├──→ WorkingMemory
 │ (怪物靠近/熔岩)   │         Reflex Layer              │    (observation,
 └──────────────────┘                                    │     consolidate_weight=0)
                                              ┌──────────┴──────────┐
                                              │  TerrainAnalyzer     │
                                              │  Flash LLM, 每 30s  │
                                              │  → observation       │
                                              └──────────┬──────────┘
                                                         │
                                                         ▼
                                                  WorkingMemory
                                                  (Agent Loop 通过
                                                   $WORKING_MEMORY 读取)
```

**不再需要 `$ENV_SUMMARY` 注入**。所有感知数据通过 WorkingMemory 的 observation 条目呈现，Agent Loop 通过现有的 `$WORKING_MEMORY` 变量自然读取。所有模块之间的通信都通过已有接口（IPC 消息、SharedState、MemoryRouter），不产生跨模块的深层依赖。

---

## 实现顺序

| 步骤 | 内容 | 涉及文件 | 预计工作量 |
|------|------|---------|-----------|
| 1 | 扩大扫描范围（8 格方块、32 格实体） | `minecraft_bridge.js` 2 处 | 5 分钟 |
| 2 | 创建 PerceptionWorker（多级扫描 + 紧急事件推送） + 集成到 BrainBridge | `perception_worker.js`(新) + `minecraft_bridge.js` | 1.5 小时 |
| 3 | Python 端接收感知事件（普通 + 紧急） + ReflexLayer 响应紧急事件 | `brain_coordinator.py` + `reflex_layer.py` | 30 分钟 |
| 4 | 创建 PerceptionBuffer + EventTicker + PerceptionManager | 3 个新文件（buffer, ticker, manager） | 1.5 小时 |
| 5 | 修改 WorkingMemory：observation 条目不计入 consolidate 配额 | `working_memory.py` | 20 分钟 |
| 6 | 集成 PerceptionManager 到 BrainCoordinator | `brain_coordinator.py` | 15 分钟 |
| 7 | 修改 system.md 任务粒度约束 | `system.md` | 10 分钟 |
| 8 | 创建 TerrainAnalyzer（Flash LLM 地形理解） + 集成到 PerceptionManager | `terrain_analyzer.py`(新) + `perception_manager.py` | 1 小时 |
| 9 | Reflex Layer 战斗记忆写入 | `reflex_layer.py` | 30 分钟 |
| 10 | 按需观察工具 scan_area | `scan_area_tool.py`(新) + `minecraft_bridge.js` + `brain_coordinator.py` | 1 小时 |

**与旧方案的关键差异**：
- 不再需要 `$ENV_SUMMARY` 注入 → 省去 `agent_loop_layer.py`、`variable_config.yaml`、`data_providers.py` 的修改
- 不再需要 Flash LLM 总结事件 → 省去 `summarizer.py`，替换为纯代码 `event_ticker.py`
- 新增 `working_memory.py` 的 consolidate_weight 修改
- TerrainAnalyzer 从"阶段五"提前到独立阶段（P2），与 EventTicker 解耦
