# 意图层神经符号记忆扩展计划

> **适用范围**: 仅 Agent Loop 意图层。Coding Agent 的代码生成层暂不接入，等意图层调试稳定后再考虑。

## 一、这个模块做什么（三句话）

在 Agent Loop 调用 `execute_step` 的**前后**，对自然语言步骤做三件事：

1. **执行前** — 判断当前意图在环境中是否可行，给出函数级执行建议。
2. **执行后** — 区分"代码没报错但目标没达成 / 代码报错但已有部分进展"等情况，替代执行层返回的布尔 `success`。
3. **长期** — 从历史意图的成败模式中归纳符号规则，减少重复犯错。

它不是记忆模块的附属品。它与 `MemoryRouter` / `GraphEngine` / `WorkingMemoryBuffer` 平行存在，有自己独立的 transition 记录、规则存储和判定逻辑，只通过接口读写环境信息和记录结果。

## 二、依据：WALL-E 核心思想

WALL-E 2.0 (论文 [NeuroSymbolic Learning of Code Rules](https://arxiv.org/html/2504.15785v1)，代码 [WALL-E 仓库](https://github.com/elated-sawyer/WALL-E)) 的核心思路：

```
真实执行轨迹 → 对比成功/失败轨迹的状态差异 → 归纳符号规则 → 编译为可执行校验函数 → 最大覆盖剪枝
``` 

关键点在于：规则是从"世界状态变化"中归纳出来的，不是从文本记忆中总结的。校验的是"动作在某个状态下是否会成功"，而不是"这段代码对不对"。

本项目当前阶段做的是一个简化版：**单步意图校验**（one-step intent guard），而非多步轨迹搜索。

### 本阶段明确不做的事

- 代码生成后的静态规则检查（那是 Coding Agent 的事）
- Coding LLM 内部 retry
- 多步 MPC / 候选轨迹搜索
- `GraphEngine` 的 `NodeType` / `EdgeRelation` 扩展

## 三、当前代码的真实情况

### 3.1 决策流程（代码中实际发生的）

```
AgentLoopLayer.build_prompt()           # agent_loop_layer.py:182
  ├─ shared_state.get_all()             # 获取游戏状态
  ├─ _drain_chat_queue()                # 获取待处理聊天
  ├─ todolist_store.get_markdown()      # 当前待办
  ├─ plan_manager.read()                # 长期计划
  ├─ draft_manager.read()               # 执行层技术指导
  ├─ chat_log_manager.get_recent()      # 近期聊天
  └─ prompt_manager.render("agent_loop/system.md")
       └─ 渲染过程中 DataProviders 异步注入:
            WORKING_MEMORY, LONG_TERM_MEMORY 等

Agent Loop LLM 输出工具调用
  └─ parse_tool_call()                  # agent_loop_layer.py:266
       └─ execute_tool()                # agent_loop_layer.py:280
            └─ ExecuteStepTool.execute({"step_description": ...})
                 └─ ExecutionLayer.execute_step(step_description)
                      ├─ _build_coding_prompt()  # 读取 draft.md 作为上下文
                      ├─ Coding LLM 生成 JS 代码
                      ├─ _validate_code()        # 静态校验
                      ├─ _execute_code()         # IPC → JS bridge 执行
                      └─ 轮询 shared_state 等结果
                           └─ 返回 {success, code, output, error, analysis}
```

### 3.2 关键文件对照

| 角色 | 文件 |
|---|---|
| Agent Loop 主循环 | [agent_loop_layer.py](../agent/brain/agent_brain/agent_loop_layer.py) |
| execute_step 工具 | [execute_step_tool.py](../agent/brain/tools/execute_step_tool.py) |
| 代码生成与执行 | [execution_layer.py](../agent/brain/agent_brain/execution_layer.py) |
| Agent Loop 提示词 | [agent_loop/system.md](../agent/prompts/agent_loop/system.md) |
| 提示词变量配置 | [variable_config.yaml](../agent/prompts/variable_config.yaml) |
| 变量数据提供者 | [data_providers.py](../agent/prompts/data_providers.py) |
| 记忆路由器 | [memory_router.py](../agent/data_manager/memory_graph/memory_router.py) |
| 工作记忆缓冲区 | [working_memory.py](../agent/data_manager/memory_graph/working_memory.py) |
| 图谱引擎 | [graph_engine.py](../agent/data_manager/memory_graph/graph_engine.py) |
| 大脑协调器 | [brain_coordinator.py](../agent/brain/agent_brain/brain_coordinator.py) |

### 3.3 现有环境变量（Agent Loop 提示词实际注入的）

来自 `variable_config.yaml` 和 `data_providers.py`：

```
STATS              # 生命、饥饿、位置等
INVENTORY          # 物品栏
EQUIPMENT          # 装备栏（护甲 + 手持物品）
BIOME              # 当前生物群系
TIME_OF_DAY        # 游戏内时间
WORLD_DAY          # 世界天数
WEATHER            # 天气（Clear / Rain / Thunder）
BLOCK_BELOW        # 脚下方块
BLOCK_LEGS         # 腿部方块
BLOCK_HEAD         # 头部方块
BLOCK_ABOVE        # 头顶第一个固体方块
NEARBY_BLOCKS      # 附近方块
NEARBY_ENTITIES    # 附近实体
WORKING_MEMORY     # WorkingMemoryBuffer 的内容
LONG_TERM_MEMORY   # 长期图谱检索切片
PLAN_FILE          # plan.md
TODOLIST_FILE      # todolist.md
DRAFT_FILE         # draft.md
LAST_TOOL_RESULT   # 上一轮工具结果
CHAT_HISTORY       # 近期聊天记录
PENDING_CHAT       # 待处理的新消息
```

### 3.4 执行结果的实际情况 

当前 `ExecutionLayer.execute_step()` 返回的结果结构：

```json
{
  "success": true,       // JS 代码是否执行完成且未抛异常
  "code": "...",         // 生成的 JS 代码
  "output": "...",       // 执行输出（log 内容）
  "error": "",           // 错误信息（如果有）
  "analysis": "..."      // Coding LLM 的分析
}
```

**`success` 的含义仅仅是"代码执行完成且无异常"**。以下情况都会被记为 `success=true` 但意图并未实现：

- 代码正常执行完毕，但没有找到目标方块（空跑）
- 代码正确执行了"挖 10 个木头"的前半部分，但在中途被中断
- 代码执行完成但 inventory 实际变化与预期不符

同样，`success=false` 也不等于意图完全失败：
- 执行超时，但实际已经收集了部分资源
- 代码报错在第 8 步，但前 7 步已经产生了有效状态变化

这是设计神经符号结果判定的直接动机。

## 四、接入点设计（改后）

### 4.1 三个接入点

```
AgentLoopLayer.build_prompt()
  │
  ├── [接入点 1] 决策前规则召回
  │    将高置信环境规则和建议注入 Agent Loop 提示词
  │    → 让 Agent Loop 在生成 execute_step 之前就避开明显不可行的步骤
  │
  ▼
Agent Loop LLM 输出 execute_step
  │
  ├── [接入点 2] execute_step 前预检
  │    在 ExecuteStepTool.execute() 中调用
  │    若 block: 不调用 ExecutionLayer，直接返回结构化失败
  │    若 advise/ask_inspect/rewrite: 把建议注入 draft.md（Agent Loop 可先调用 draft 工具写入）
  │
  ▼
ExecutionLayer.execute_step()
  │
  ├── [接入点 3] execute_step 后复核
  │    比较执行前后的 shared_state 快照
  │    判定意图达成度（而非直接相信 success 布尔值）
  │    将 verdict 和 transition 记录到独立存储
  │    将判定摘要写入 WorkingMemoryBuffer（供 Agent Loop 下一轮读取）
```

### 4.2 关于 draft.md 注入的具体做法

当前 `ExecuteStepTool.execute()` 只接受 `step_description`（字符串），不接受额外参数。神经符号模块要传递执行建议，最直接的路径是 **在 Agent Loop 调用 execute_step 之前，先通过 `draft` 工具写入建议**：

1. 神经符号预检返回 `action=advise`，附带 `execution_guidance`。
2. Agent Loop 收到预检结果后，先调用 `draft` 工具把建议写入 `draft.md`。
3. 然后调用 `execute_step`，`ExecutionLayer._build_coding_prompt()` 会自动读取 `draft.md` 注入 Coding LLM 的上下文。

后续可以给 `execute_step` 增加一个可选的 `context_hints` 字段，让建议直接传入而不依赖文件系统。

## 五、判定输入：DecisionContext

### 5.1 结构

神经符号判定需要接近 Agent Loop 提示词所见的完整环境。构造一个结构化的 `DecisionContext` 而非散装传入：

```json
{
  "state": {
    "position": {"x": 0, "y": 64, "z": 0},
    "health": 20,
    "food": 20,
    "inventory": {},
    "equipment": {},
    "biome": "plains",
    "dimension": "overworld",
    "gamemode": "survival",
    "time_of_day": 6000,
    "world_day": 0,
    "weather": "Clear",
    "nearby_blocks": [],
    "nearby_entities": [],
    "surrounding_blocks": {
      "below": "grass_block",
      "legs": "air",
      "head": "air",
      "above": "none"
    }
  },
  "task_context": {
    "plan": "...",
    "todolist": "...",
    "draft": "...",
    "last_tool_result": {}
  },
  "memory_context": {
    "working_memory": "...",
    "long_term_memory": "..."
  },
  "chat_context": {
    "chat_history": "...",
    "pending_chat": "..."
  }
}
```

> 原文档遗漏了 `dimension`、`gamemode`、`weather`、`equipment` 字段。

### 5.2 数据来源

`DecisionContext` 在 `AgentLoopLayer.build_prompt()` 组装时就可以一并构建，因为此时 `state`、`todolist`、`plan`、`draft`、`last_tool_result` 都在手边。`WORKING_MEMORY` 和 `LONG_TERM_MEMORY` 可以通过 `MemoryRouter.working_memory.get_buffer_text()` 和 `MemoryRouter.retrieve_context_async()` 获取（与 DataProviders 相同的调用方式）。

## 六、意图表示与分类

### 6.1 结构化意图

```json
{
  "raw_step": "找到附近最近的橡树并收集 10 个橡木原木",
  "category": "collect_block",
  "target": "oak_log",
  "quantity": 10,
  "location_constraint": "nearby",
  "success_criteria": {
    "inventory_delta": {"oak_log": 10},
    "acceptable_min_delta": {"oak_log": 1},
    "partial_threshold": 0.5
  },
  "risk_factors": ["night", "hostile_mobs_nearby"],
  "execution_guidance": {
    "suggested_functions": ["world.getNearestBlock", "skills.breakBlockAt"],
    "avoid_strategies": ["无目标地四处走动"],
    "notes": "若附近橡木不足，收集到部分数量也是有效进展，下一轮继续。"
  },
  "confidence": 0.82
}
```

### 6.2 意图类别（固定集合，避免 LLM 扩展漂移）

| 类别 | 说明 | 与相近类别的区别 |
|---|---|---|
| `collect_block` | 破坏方块并收集掉落物（如砍树、挖矿） | 与 `mine_block` 合并：在 Minecraft 中两者本质相同 |
| `craft_item` | 在工作台/背包中合成物品 | |
| `place_block` | 在世界中放置方块 | |
| `move_to` | 移动到指定位置/区域 | |
| `attack_entity` | 攻击生物 | |
| `pickup_item` | 捡起地面掉落物 | 区别于 `collect_block`（需要破坏方块） |
| `build_structure` | 按蓝图放置多个方块 | 区别于 `place_block`（单方块） |
| `smelt_item` | 在熔炉中烧炼物品 | |
| `explore_area` | 探索未知区域 | |
| `equip_item` | 装备护甲或手持物品 | |
| `eat_food` | 食用食物 | |
| `store_item` | 将物品放入容器 | |
| `interact_block` | 与方块交互（开门、开箱、使用工作台等） | 新增，原文档缺少 |
| `wait` | 主动等待 | |
| `inspect` | 观察/扫描环境获取信息 | |

> 改动说明：合并了原文档中重叠的 `collect_block` 和 `mine_block`；`collect_item` 重命名为 `pickup_item` 以区分于破坏方块收集；新增 `interact_block`（原文档遗漏了与容器/门/工作台的交互场景）。

### 6.3 意图分类流程

```
step_description
  → 规则/关键词匹配 category、target、quantity
  → LLM 在固定类别中补全 success_criteria、risk_factors、execution_guidance
  → 低置信度时 category="unknown"，只记录 transition，不做 hard block
```

## 七、预检输出

预检不只是一个布尔值，而是给 Agent Loop 一个可操作的决策建议：

```json
{
  "action": "allow | advise | block | ask_inspect | rewrite_step",
  "reason": "precondition | insufficient_context | high_risk | already_satisfied | inefficient_strategy",
  "confidence": 0.84,
  "matched_rules": ["intent_collect_block_requires_visible_or_searchable_tree"],
  "feedback": "nearby_blocks 中未检测到 oak_log，直接收集 10 个橡木原木成功率极低。",
  "suggestion": "先 inspect_surroundings 搜索树木；或改为收集附近可见的任意原木。",
  "execution_guidance": {
    "suggested_functions": ["world.getNearestBlock", "skills.collectBlock"],
    "avoid_strategies": ["假设 oak_log 一定在附近"],
    "draft_hint": "先搜索附近方块确认橡木位置；若无橡木，收集 birch_log/spruce_log 作为替代。"
  }
}
```

### action 含义

| action | 含义 | Agent Loop 应如何处理 |
|---|---|---|
| `allow` | 不干预，直接执行 | 正常调用 execute_step |
| `advise` | 可以执行，但有建议 | 先调用 draft 工具写入建议，再调用 execute_step |
| `block` | 明显不可行 | 不调用 execute_step，直接记入 last_tool_result，重新决策 |
| `ask_inspect` | 环境信息不足 | 建议先调用 inspect_surroundings 或 scan_terrain |
| `rewrite_step` | 步骤过大或目标不清 | 建议 Agent Loop 将步骤拆分为更可验证的小步 |

`block` 只在规则置信度足够高时才启用（Phase 3），早期阶段以 `advise` 和 `ask_inspect` 为主。

## 八、更好的结果判定方法

### 8.1 四层判定结构

执行层返回的 `success` 只说明代码是否执行完毕。神经符号判定把结果拆为四层：

```json
{
  "execution_status": "completed | runtime_error | interrupted | blocked | timeout",
  "intent_status": "achieved | partially_achieved | not_achieved | over_achieved | unknown",
  "progress": {
    "target": "oak_log",
    "requested": 10,
    "actual_delta": 5,
    "ratio": 0.5
  },
  "side_effects": {
    "health_delta": 0,
    "food_delta": -1,
    "position_changed": true,
    "new_risks": []
  },
  "next_recommendation": "continue_same_intent | retry_with_guidance | replan | inspect | stop",
  "reason": "已获得 5/10 oak_log，虽然未达数量目标但取得有效进展。建议继续搜索附近树木。"
}
```

### 8.2 判定原则

**原则一：数量型目标按完成度判定，不做二值化**

"挖 10 个木头但只挖了 5 个" → `partially_achieved`，`ratio=0.5`，`next=continue_same_intent`。

这种 transition 对规则学习的价值很高：说明策略有效但步骤目标过大或资源不足。

**原则二：代码无异常但世界状态无变化 → 视为未达成**

步骤"挖铁矿"，`success=true`，但 inventory 无增加，nearby_blocks 中铁矿仍在，output 中没有 "Broke iron_ore" 日志。应判为 `not_achieved` 并记录"空跑"。

**原则三：执行层报告失败但已有部分进展 → 保留部分达成**

代码超时或被中断，但已经获得一些资源。判为 `partially_achieved`，同时保留 `execution_status=timeout/interrupted`。

**原则四：副作用单独记录，不混入成败判定**

目标达成但生命值大幅下降、掉入深坑、进入夜晚高风险区域——不能简单标为完美成功。规则学习需要知道"能完成但代价高"的模式。

**原则五：证据不足时显式标为 unknown**

"探索附近区域"这类意图没有直接的 inventory delta。需要依赖 position delta、scan 结果、working memory 中的 observation 或 output 日志。证据不足时标 `unknown`，不强行判定。

### 8.3 常见意图的验证信号

| 意图类型 | 主要验证信号 | 部分成功示例 |
|---|---|---|
| `collect_block` | inventory delta、方块破坏日志、"Broke" 输出 | 目标 10 个，获得 1-9 个 |
| `craft_item` | inventory 目标物增加、材料减少 | 目标 4 个，只合成了 1 个 |
| `place_block` | 周围方块变化、inventory 方块减少 | 放置了部分结构 |
| `move_to` | position 接近目标、biome/landmark 变化 | 距离明显缩短但未到达 |
| `attack_entity` | 实体消失、掉落物出现、health 变化 | 造成伤害但未击杀 |
| `explore_area` | position delta、new blocks/entities | 发现部分资源但未找到目标 |
| `inspect` | scan/inspection 结果非空 | 获得部分环境数据 |
| `interact_block` | 容器打开日志、方块状态变化 | 打开了容器但未完成存取 |
| `pickup_item` | inventory 增加、地面物品消失 | 捡起部分物品 |

### 8.4 状态快照机制

当前 JS 执行结果（通过 `shared_state` 的 `last_execution_result`）只返回 `{success, output, error}`，**不包含**前后状态快照。因此神经符号模块需要在 Python 侧主动记录：

```
执行前: pre_state = await shared_state.get_all()
执行:   result = await execution_layer.execute_step(step)
执行后: post_state = await shared_state.get_all()
判定:   verdict = compare_and_judge(pre_state, post_state, step, result)
```

注意：`shared_state.get_all()` 在 execution_layer 内部也会调用（用于构建 coding prompt），神经符号模块应该获取独立的快照，避免依赖 execution_layer 内部的状态读取时机。

## 九、Transition 记录

### 9.1 Transition 结构

每次 `execute_step` 前后记录一条 transition：

```json
{
  "transition_id": "uuid",
  "timestamp": 1700000000,
  "step_description": "找到附近最近的橡树并收集 10 个橡木原木",
  "pre_state": { "...": "执行前的 shared_state 快照" },
  "intent": {
    "category": "collect_block",
    "target": "oak_log",
    "quantity": 10,
    "success_criteria": {}
  },
  "precheck": {
    "action": "advise",
    "matched_rules": [],
    "execution_guidance": {}
  },
  "execution_result": {
    "success": true,
    "output": "...",
    "error": ""
  },
  "post_state": { "...": "执行后的 shared_state 快照" },
  "intent_verdict": {
    "execution_status": "completed",
    "intent_status": "partially_achieved",
    "progress": {"target": "oak_log", "requested": 10, "actual_delta": 5, "ratio": 0.5},
    "next_recommendation": "continue_same_intent",
    "reason": "获得 5 个 oak_log，但目标数量为 10。"
  },
  "learnable_patterns": [
    "quantity_too_large_for_single_step",
    "nearby_resource_insufficient"
  ]
}
```

### 9.2 Transition Buffer 与 WorkingMemoryBuffer 的关系

| | Transition Buffer (神经符号) | WorkingMemoryBuffer |
|---|---|---|
| 存储格式 | JSONL（结构化） | raw JSON + summary MD |
| 记录粒度 | 每次 execute_step 一条 | 各类工具调用混合 |
| 消费方式 | 规则归纳 (Phase 4) | consolidate → crystallize → 图谱 |
| 生命周期 | 长期累积（定期剪枝） | 任务内 → 压缩 → 蒸馏 |
| 写入内容 | 完整 pre/post state + verdict | 简短摘要文本 |

两者**独立存储、独立消费**，不互相依赖。但神经符号模块在判定完成后，会**将意图判定摘要写入 WorkingMemoryBuffer**（通过 `MemoryRouter.log()`），让 Agent Loop 下一轮能读到判定结果。

## 十、Rule Store 与 DSL

### 10.1 规则示例

```json
{
  "rule_id": "intent_collect_block_nearby_unknown",
  "domain": "intent_environment",
  "intent_category": "collect_block",
  "description": "收集指定方块前，nearby_blocks 中未检测到目标且步骤未包含搜索策略 → 不应直接执行。",
  "dsl": {
    "all": [
      {"eq": ["intent.category", "collect_block"]},
      {"target_tag": "log"},
      {"nearby_blocks_lacks": "intent.target"},
      {"step_not_mentions_any": ["寻找", "搜索", "search", "nearest", "附近最近"]}
    ],
    "result": {
      "action": "ask_inspect",
      "feedback": "nearby_blocks 中未检测到目标方块。"
    }
  },
  "support_count": 3,
  "counterexample_count": 0,
  "confidence": 0.78,
  "hard_block": false
}
```

### 10.2 DSL 谓词（仅 JSON 白名单解释器，不执行 LLM 生成的 Python）

```
eq, neq, gt, gte, lt, lte,
contains, not_contains,
step_mentions_any, step_not_mentions_any,
inventory_has, inventory_lacks,
equipment_is, equipment_at_least,
nearby_blocks_has, nearby_blocks_lacks,     # 注意：lacks 意思是"未检测到"而非"确定没有"
nearby_entity_present, nearby_entity_absent,
surrounding_block_is,
health_below, food_below,
time_is, biome_is, dimension_is,
last_result_status_is,
progress_ratio_at_least
```

> 修正：原文档中的 `not_nearby_block` 改为 `nearby_blocks_lacks`，语义是"nearby_blocks 快照中未包含"，而非"世界中不存在"。nearby_blocks 只是有限半径的采样。

## 十一、模块边界

### 11.1 目录结构

```
braincraft/agent/neurosymbolic/
  __init__.py
  service.py                # 统一入口：retrieve / precheck / verify / record
  schemas.py                # DecisionContext, Intent, GuardResult, IntentVerdict, Transition
  decision_context.py       # 从 shared_state + plan/todolist/draft/memory 组装 DecisionContext
  intent_classifier.py      # 固定类别匹配 + LLM fallback
  intent_prechecker.py      # 规则 DSL 解释器 → allow/advise/block/ask_inspect/rewrite_step
  intent_verifier.py        # pre/post state diff → achieved/partial/not/unknown
  transition_recorder.py    # JSONL append
  rule_store.py             # 规则 CRUD + DSL 编译
  rule_miner.py             # LLM 从 transitions 归纳规则（Phase 4）
  rule_pruner.py            # 最大覆盖剪枝（Phase 4）
```

### 11.2 存储路径

```
bots/{agent}/neurosymbolic/
  intent_transitions.jsonl    # 按时间追加，每条一行
  intent_rules.json           # 规则 + DSL
  intent_rule_metrics.json    # 每条规则的支持/反例/误杀计数
```

### 11.3 与现有系统的交互边界

```
                    ┌──────────────────┐
                    │  NeuroSymbolic   │
                    │    Service       │
                    └──────┬───────────┘
           ┌───────────────┼───────────────┐
           │ 读取          │ 写入          │ 不修改
           ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────────┐
    │SharedState│    │WorkingMem│    │ GraphEngine  │
    │(get_all)  │    │Buffer.log│    │ (暂不扩展)   │
    └──────────┘    └──────────┘    └──────────────┘
                           │
                    ┌──────┴───────┐
                    │ Agent Loop   │
                    │ 下一轮读取   │
                    └──────────────┘
```

- 读取 `SharedState.get_all()` → 组装 DecisionContext
- 读取 `MemoryRouter.working_memory.get_buffer_text()` → 工作记忆上下文
- 读取 `MemoryRouter.retrieve_context_async()` → 长期记忆上下文
- 写入 `MemoryRouter.log()` → 将意图判定摘要写入 WorkingMemoryBuffer
- **不修改** `crystallize()` 内部逻辑
- **不修改** `GraphEngine` 的节点类型和边关系定义
- 后期可选将稳定规则摘要作为 `NodeType.PATTERN` 节点写入图谱（metadata 标记 `source=neurosymbolic`），但完整规则仍在 Rule Store

## 十二、反馈给 Agent Loop 的方式

### 12.1 预检失败 → 结构化工具结果

```json
{
  "success": false,
  "neurosymbolic_guard": true,
  "failure_reason": "precondition",
  "feedback": "nearby_blocks 中未检测到 oak_log。",
  "suggestion": "先 inspect_surroundings 搜索树木位置。"
}
```

直接作为 `LAST_TOOL_RESULT` 的一部分。Agent Loop 下一轮看到这个结果，会重新决策。

### 12.2 预检建议 → draft.md 注入

神经符号预检返回 advice 后，Agent Loop 应在调用 execute_step 前先调用 draft 工具，将执行建议写入：

```
[神经符号建议]
- 目标：收集 10 个 oak_log
- 环境：nearby_blocks 中检测到 oak_log → 可执行
- 建议函数：world.getNearestBlock("oak_log") + skills.breakBlockAt()
- 若收集数量不足 10 个也属正常，后续继续即可
```

Coding LLM 在生成代码时会自动读到 draft.md 中的这些内容。

### 12.3 执行后复核 → WorkingMemoryBuffer

```json
{
  "intent_status": "partially_achieved",
  "progress": "5/10 oak_log",
  "recommendation": "继续同一意图，目标改为再收集 5 个。"
}
```

写入 WorkingMemoryBuffer（通过 `MemoryRouter.log()`），在下一轮 Agent Loop 的 `WORKING_MEMORY` 提示词变量中可见。

## 十三、评估指标

| 指标 | 说明 |
|---|---|
| `precheck_precision` | 被 block/ask_inspect 的步骤中，后续证明确实不可行或信息不足的比例 |
| `false_block_rate` | 被规则阻止但实际可成功的比例（误杀率） |
| `partial_success_detection_rate` | 部分成功是否被正确识别（而非简单标成功/失败） |
| `intent_verdict_accuracy` | achieved/partial/not/unknown 的人工抽样准确率 |
| `repeat_failure_rate` | 同类不可行意图的重复出现频率 |
| `planning_revision_rate` | Agent Loop 因神经符号反馈而改写步骤的频率 |
| `task_progress_delta` | 引入意图层校验后，任务推进是否更稳定 |

## 十四、实施步骤

### Phase 1: 只记录，不干预

**目标**: 搭好数据管道，验证分类和判定逻辑的质量。

- 新建 `neurosymbolic` 包，实现 `schemas.py`、`decision_context.py`。
- 实现基础 `IntentClassifier`：关键词 + 规则匹配为主，LLM fallback 为辅，输出固定类别的意图。
- 实现基础 `IntentVerifier`：pre/post state diff，按验证信号表判定 achieved/partial/not/unknown。
- 在 `ExecuteStepTool.execute()` 中插入 pre/post state 快照获取和 transition 记录。
- 过渡期不阻止任何 execute_step，只写 `intent_transitions.jsonl` 日志。
- **验收标准**: 收集到 50+ 条有效 transition，分类和判定结果通过人工抽检（准确率 > 80%）。

### Phase 2: 软预检 + 执行指导

**目标**: 规则起作用但不误杀，验证预检建议的实际价值。

- 实现 `intent_prechecker.py` 和 JSON DSL 解释器。
- 手写第一批环境规则（约 10-15 条），覆盖高频不可行场景：
  - 收集/挖掘 nearby_blocks 中不存在的目标
  - 生命值/饥饿值过低时执行高风险动作
  - 缺少必要工具的挖掘任务
  - 夜晚无光照时远离庇护所
- 实现 `retrieve_intent_context()`，将匹配规则注入 Agent Loop 提示词。
- 实现 `precheck_intent()`，输出 `allow/advise/ask_inspect/rewrite_step`（暂不启用 `block`）。
- 将 `execution_guidance` 通过 draft.md 注入执行层。
- **验收标准**: `planning_revision_rate` 上升（Agent Loop 开始根据建议改写步骤），没有出现因误判导致的正确步骤受阻。

### Phase 3: 有限 hard guard

**目标**: 对高置信规则启用 block，用监控保障不退化。

- 对确定性高的规则（支持数 ≥ 5，反例 = 0）启用 `block`。
- 实现 `false_block_rate` 监控——误杀率高的规则自动降级为 `advise`。
- 规则降级/升降机制做成配置化，不硬编码。
- **验收标准**: `false_block_rate < 5%`，`repeat_failure_rate` 有明显下降。

### Phase 4: 规则学习与剪枝

**目标**: 从 transition 历史中自动归纳新规则，减少人工维护成本。

- 实现 `rule_miner.py`：LLM 从标记了 `learnable_patterns` 的 transition 批次中归纳规则（参考 WALL-E 的对比成功/失败轨迹差异的方法）。
- 规则编译为 JSON DSL 后，离线回放历史 transitions 验证精度。
- 实现 `rule_pruner.py`：用 coverage/counterexample 指标做最大覆盖剪枝，保留有用的规则子集。
- **验收标准**: 自动归纳的规则在回放中 `precheck_precision > 70%`，剪枝后规则数量不膨胀。

### Phase 5: 长期记忆弱联动

**目标**: 最稳定的规则摘要写入图谱，但不耦合。

- 将置信度 > 0.9、支持数 > 20 的规则摘要作为 `NodeType.PATTERN` 节点写入图谱。
- metadata 标记 `source=neurosymbolic` 和 `rule_id`，可双向追溯。
- 完整规则、判定逻辑、transition buffer 继续保持独立。
- **验收标准**: 图谱中出现 neurosymbolic 规则节点，可通过 metadata 追溯到完整规则定义。

---

## 十五、简要总结

这个计划的本质是把 Agent Loop 的决策质量从"完全依赖 LLM 的常识"升级为"LLM + 对环境状态的符号校验"。两处最关键的改动：

1. **执行前**: 不再无条件信任 LLM 输出的步骤描述——用结构化规则检查当前环境是否支持这个意图，并给出具体到函数的执行建议。
2. **执行后**: 不再把 `success=true/false` 当作最终答案——比较执行前后的世界状态变化，区分"代码完成了但目标没达成"和"代码失败了但已有进展"。

Coding Agent 的代码生成层暂不涉及。等意图层稳定后，Rule Store、DSL 解释器和 transition 记录机制可以复用到代码层。
