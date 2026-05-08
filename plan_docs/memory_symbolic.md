# 意图层神经符号记忆扩展计划

目标：先只在 **Agent Loop 意图层** 实现 WALL-E 风格的神经符号校验。代码层先不做，等意图层调试稳定后再考虑迁移。

这个模块的职责不是生成代码，也不是检查生成后的 JavaScript，而是在 Agent Loop 准备调用 `execute_step` 前，对自然语言步骤做三件事：

1. 判断这个意图在当前环境下是否可行。
2. 给出执行层可用的高层指导，例如建议使用哪个已有 `skills/world` 函数或避免哪类策略。
3. 在执行完成后重新判定“意图是否达成、是否部分达成、是否值得继续”，而不是直接相信执行层返回的 `success=true/false`。

核心原则：神经符号模块与 `MemoryRouter / GraphEngine / WorkingMemory` 解耦。它有自己的 transition buffer、Rule Store 和判定逻辑，只通过接口读取当前上下文、记录执行结果、向 Agent Loop 返回约束和建议。长期图谱最多保存规则摘要引用，不保存完整规则，也不承担规则执行。

---

## 依据与边界

WALL-E 2.0 的核心思想是从真实轨迹和 world model 预测轨迹的成功/失败差异中归纳符号规则，再把规则编译成可执行校验函数，并用最大覆盖剪枝保留有用规则。其重点是校准“动作在某个状态下是否会成功”的预测，而不是保存更多文本记忆。见论文 [3.1 NeuroSymbolic Learning of Code Rules](https://arxiv.org/html/2504.15785v1)，代码demo[WALL-E 仓库](https://github.com/elated-sawyer/WALL-E)。

本项目当前更适合先做 **one-step 意图校验**：

```text
当前状态 + 当前任务 + step_description
  -> 意图解析
  -> 环境可行性校验
  -> 执行建议
  -> execute_step
  -> 意图达成度复核
  -> transition 记录和规则学习
```

暂不做：

- 代码生成后的静态规则检查。
- Coding LLM 内部 retry。
- 多步 MPC / 候选轨迹搜索。
- GraphEngine 的 `NodeType/EdgeRelation` 扩展。

代码层以后可以复用 Rule Store、DSL 和 transition 记录思路，但本阶段计划只覆盖意图层。

---

## 当前代码中的接入点

相关文件：

- `braincraft/agent/brain/agent_brain/agent_loop_layer.py`
- `braincraft/agent/brain/tools/execute_step_tool.py`
- `braincraft/agent/brain/agent_brain/execution_layer.py`
- `braincraft/agent/prompts/agent_loop/system.md`
- `braincraft/agent/prompts/data_providers.py`
- `braincraft/agent/prompts/variable_config.yaml`

当前 Agent Loop 决策流程：

```text
AgentLoopLayer.build_prompt()
  -> Agent Loop LLM 输出工具调用
  -> parse_tool_call()
  -> execute_tool()
  -> ExecuteStepTool.execute({"step_description": ...})
  -> ExecutionLayer.execute_step(step_description)
```

推荐接入点：

1. **决策前规则召回**

   在 `AgentLoopLayer.build_prompt()` 中加入：

   ```python
   neurosymbolic_context = await ns_service.retrieve_intent_context(decision_context)
   ```

   将少量高置信环境规则和当前建议注入 Agent Loop prompt。作用是让 Agent Loop 在生成 `execute_step` 之前就避开明显不可行步骤。

2. **execute_step 前预检**

   在 `ExecuteStepTool.execute()` 中调用：

   ```python
   guard = await ns_service.precheck_intent(step_description, decision_context)
   ```

   如果 `guard.action == "block"`，不调用 Execution Layer，直接返回一个结构化失败结果给 Agent Loop。

   如果 `guard.action == "advise"`，允许执行，但把建议写入 `draft.md` 或追加到传给执行层的上下文中。由于当前 `execute_step` 只接受自然语言步骤，不接受额外字段，最保守做法是让 Agent Loop 先通过 `draft` 工具写入指导；后续也可以让 `ExecutionLayer._build_execution_context()` 读取神经符号建议。

3. **execute_step 后复核**

   在 `ExecutionLayer.execute_step()` 返回后，或在 `ExecuteStepTool.execute()` 包装层中调用：

   ```python
   verdict = await ns_service.verify_intent_result(step_description, pre_state, execution_result, post_state)
   ```

   这个 verdict 才是意图层 transition 的核心标签。它不等同于执行层 `success`。

---

## 判定输入：使用尽可能丰富的环境信息

神经符号判定不能只看 inventory。它应接近 `decision_loop` 当前提示词能看到的完整环境。

当前 Agent Loop 已注入的环境变量包括：

- `STATS`: 生命值、饥饿值、位置等机器人状态
- `INVENTORY`: 物品栏
- `BIOME`: 当前生物群系
- `TIME_OF_DAY`, `WORLD_DAY`: 时间与世界天数
- `BLOCK_BELOW`, `BLOCK_LEGS`, `BLOCK_HEAD`, `BLOCK_ABOVE`: 身体周围关键方块
- `NEARBY_BLOCKS`: 附近方块
- `NEARBY_ENTITIES`: 附近实体
- `WORKING_MEMORY`: 近期经历和 observation
- `LONG_TERM_MEMORY`: 相关长期记忆图谱切片
- `PLAN_FILE`, `TODOLIST_FILE`, `DRAFT_FILE`: 当前目标、短期待办和执行层技术指导
- `LAST_TOOL_RESULT`: 上一轮工具结果
- `CHAT_HISTORY`, `PENDING_CHAT`: 社交和玩家指令上下文

因此，神经符号模块内部应构造一个 `DecisionContext`，而不是只传 `state`：

```json
{
  "state": {
    "position": {},
    "health": 20,
    "food": 20,
    "inventory": {},
    "equipment": {},
    "biome": "plains",
    "time_of_day": 6000,
    "world_day": 0,
    "weather": "Clear",
    "nearby_blocks": [],
    "nearby_entities": [],
    "surrounding_blocks": {
      "below": "grass_block",
      "legs": "air",
      "head": "air",
      "firstAbove": "none"
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
    "recent_chat": "...",
    "pending_chat": "..."
  }
}
```

短期实现上，`DecisionContext` 可以直接由 `AgentLoopLayer.build_prompt()` 已经拿到的 `state / todolist / plan / draft / last_tool_result` 组装；`WORKING_MEMORY` 和 `LONG_TERM_MEMORY` 可以通过 `MemoryRouter` 同步或异步检索获得。

---

## 意图表示

`step_description` 需要被解析成结构化意图，供规则判断和结果复核使用。

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
    "avoid_strategies": ["blind wandering without checking nearby blocks"],
    "notes": "若附近只有少量橡木，收集到部分数量也算有效进展，下一轮继续搜索。"
  },
  "confidence": 0.82
}
```

第一阶段固定类别即可，避免 LLM 自动扩展导致漂移：

```text
collect_block, mine_block, craft_item, place_block, move_to,
attack_entity, collect_item, build_structure, smelt_item,
explore_area, equip_item, eat_food, store_item, wait, inspect
```

意图分类流程：

```text
step_description
  -> 规则/关键词解析 category、target、quantity
  -> LLM 在固定类别中补全不确定字段
  -> 低置信则 category="unknown"，只记录 transition，不做 hard block
```

---

## 预检输出

预检不只是 `pass/fail`，而是给 Agent Loop 一个可执行的决策建议。

```json
{
  "action": "allow | advise | block | ask_inspect | rewrite_step",
  "reason": "precondition | insufficient_context | high_risk | already_satisfied | inefficient_strategy",
  "confidence": 0.84,
  "matched_rules": ["env_collect_oak_requires_nearby_oak_or_search_plan"],
  "feedback": "附近方块列表中没有 oak_log，直接收集 10 个橡木原木成功率低。",
  "suggestion": "先 inspect_surroundings 或 scan_terrain 搜索树木；如果目标是任意木头，可改为收集附近可见树种。",
  "execution_guidance": {
    "suggested_functions": ["world.getNearestBlock", "skills.collectBlock", "skills.breakBlockAt"],
    "avoid_strategies": ["直接假设 oak_log 在附近"],
    "draft_patch": "本步先检查 nearby_blocks/world.getNearestBlock；若没有 oak_log，改找 birch_log/spruce_log 或返回未找到。"
  }
}
```

`action` 含义：

- `allow`: 不干预，直接执行。
- `advise`: 可以执行，但建议写入 draft 或 execution context。
- `block`: 当前意图明显不可行，返回失败给 Agent Loop，让它重新决策。
- `ask_inspect`: 环境信息不足，建议先调用 `inspect_surroundings` 或 `scan_terrain`。
- `rewrite_step`: 当前步骤描述过大或目标不清，建议 Agent Loop 改写为更可验证的一步。

这比单纯 hard guard 更适合早期调试：规则不成熟时先减少误杀；规则足够确定时再 block。

---

## 更好的结果判定方法

执行层返回的 `success` 只能说明代码执行是否报错或是否被中断，不能直接代表意图是否完成。

需要把结果拆成四层：

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
    "new_risk": []
  },
  "next_recommendation": "continue_same_intent | retry_with_guidance | replan | inspect | stop",
  "reason": "收集到 5/10 个 oak_log，虽然未达到数量目标，但已经取得有效进展。建议继续搜索附近树木。"
}
```

### 判定原则

1. **数量型目标按完成度判定**

   “挖 10 个木头但只挖 5 个”不应简单记为失败。应判为：

   ```text
   execution_status = completed
   intent_status = partially_achieved
   progress.ratio = 0.5
   next_recommendation = continue_same_intent
   ```

   这类 transition 对规则学习很重要：它说明当前策略有用，但环境资源不足或步骤目标过大。

2. **代码无异常但世界状态没变，不算意图达成**

   例如步骤是“挖铁矿”，执行层 `success=true`，但 inventory 没增加、附近铁矿仍存在、输出也没有 “Broke iron_ore”。应判为 `not_achieved` 或 `unknown`，并记录原因。

3. **执行层失败但意图可能部分达成**

   例如代码最后超时或被中断，但已经采到 3 个木头。应判为 `partially_achieved`，同时保留 `execution_status=timeout/interrupted`。

4. **安全和副作用单独记录**

   如果目标达成但生命值大幅下降、掉进洞里、进入夜晚高风险区域，不能简单当作完美成功。规则学习需要知道“能完成但代价高”。

5. **无法验证时显式 unknown**

   某些目标如“探索附近区域”没有直接 inventory delta。需要依赖 position delta、scan 结果、working memory observation 或输出日志。证据不足时不要强行标成功/失败。

### 常见意图的验证信号

| 意图类型 | 主要验证信号 | 部分成功示例 |
|---|---|---|
| `collect_block` / `mine_block` | inventory delta、方块破坏日志、nearby_blocks 变化 | 目标 10 个，获得 1-9 个 |
| `craft_item` | inventory 目标物增加、材料减少、输出日志 | 目标 4 个，只合成 1 个 |
| `place_block` | 目标方块出现在周围/指定位置、inventory 减少 | 放置了部分结构 |
| `move_to` | position 接近目标、biome/landmark 改变 | 距离目标明显缩短但未到达 |
| `attack_entity` | 实体消失、掉落物出现、health side effect | 杀死部分目标或造成战斗进展 |
| `explore_area` | position delta、new blocks/entities、terrain scan | 发现部分资源但未找到目标 |
| `inspect` | scan/inspection result 非空 | 信息不足但获得新环境数据 |

---

## Transition 结构

transition 在意图层记录，不依赖 `crystallize()` 后从摘要中反推。

```json
{
  "transition_id": "uuid",
  "step_description": "找到附近最近的橡树并收集 10 个橡木原木",
  "decision_context": {
    "state": {},
    "task_context": {},
    "memory_context": {}
  },
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
    "success": false,
    "output": "...",
    "error": "Execution timeout",
    "state_before": {},
    "state_after": {}
  },
  "post_state": {},
  "intent_verdict": {
    "execution_status": "timeout",
    "intent_status": "partially_achieved",
    "progress": {"target": "oak_log", "requested": 10, "actual_delta": 5, "ratio": 0.5},
    "next_recommendation": "continue_same_intent",
    "reason": "超时前已经获得 5 个 oak_log。"
  },
  "learnable_failure_modes": [
    "quantity_too_large_for_single_step",
    "nearby_resource_insufficient"
  ]
}
```

注意：Python 侧应在调用执行层前后各读一次 `shared_state.get_all()`，不要只依赖 JS bridge 的 `state_before/state_after`。当前 JS 成功结果有前后状态，失败结果不稳定包含状态；Python 侧快照可以补齐。

---

## Rule Store 与 DSL

规则只覆盖意图层环境判断和结果判定。

规则记录示例：

```json
{
  "rule_id": "intent_collect_oak_requires_visible_or_searchable_tree",
  "domain": "intent_environment",
  "intent_category": "collect_block",
  "description": "收集指定树种前，应先确认 nearby_blocks 中有该树种，或步骤中包含搜索策略。",
  "dsl": {
    "all": [
      {"eq": ["intent.category", "collect_block"]},
      {"target_tag": "log"},
      {"not_nearby_block": "intent.target"},
      {"not_step_mentions_any": ["寻找", "搜索", "search", "nearest", "附近最近"]}
    ],
    "result": {
      "action": "ask_inspect",
      "feedback": "附近未确认存在目标树种。",
      "suggestion": "先检查附近方块或把步骤改成'寻找最近的目标树并收集'。"
    }
  },
  "support_count": 3,
  "counterexample_count": 0,
  "confidence": 0.78,
  "hard_block": false
}
```

DSL 第一阶段使用 JSON 白名单解释器：

```text
eq, neq, gt, gte, lt, lte,
contains, not_contains,
step_mentions_any, not_step_mentions_any,
inventory_has, inventory_lacks,
equipment_is, equipment_at_least,
nearby_block, not_nearby_block,
nearby_entity, surrounding_block_is,
health_below, food_below,
time_is, biome_is,
last_result_status_is,
progress_ratio_at_least
```

暂不执行 LLM 生成的 Python。规则先以“可解释、可回放、可剪枝”为优先。

---

## 模块边界

新增独立包建议：

```text
braincraft/agent/neurosymbolic/
  __init__.py
  service.py                 # retrieve_intent_context / precheck_intent / verify_intent_result / record_transition
  schemas.py                 # DecisionContext, Intent, GuardResult, IntentVerdict, Transition
  decision_context.py        # 从 state + plan/todolist/draft/memory/last_result 组装判定上下文
  intent_classifier.py       # 固定类别解析 + LLM fallback
  intent_prechecker.py       # 规则预检，输出 allow/advise/block/ask_inspect/rewrite_step
  intent_verifier.py         # 执行后复核 achieved/partial/not/unknown
  transition_recorder.py     # JSONL 记录
  rule_store.py              # 独立规则存储
  rule_validator.py          # JSON DSL 解释器
  rule_miner.py              # LLM 从 transitions 归纳意图规则
  rule_pruner.py             # 最大覆盖剪枝
```

存储：

```text
bots/{agent}/neurosymbolic/
  intent_transitions.jsonl
  intent_rules.json
  intent_rule_metrics.json
  intent_candidates.json
```

与 MemoryRouter 的关系：

- 读取 working memory / long-term memory 作为上下文证据。
- 执行后可以把意图判定摘要写入 working memory，方便 Agent Loop 下一轮读到。
- 不修改 `crystallize()` 内部逻辑。
- 后期可选把稳定规则摘要写入 `pattern` 节点，但完整规则仍在 Rule Store。

---

## 反馈给 Agent Loop 的方式

意图层神经符号模块的输出应该能驱动 Agent Loop 改行为。

### 预检失败

返回工具结果：

```json
{
  "success": false,
  "neurosymbolic_guard": true,
  "failure_reason": "precondition",
  "feedback": "没有可见 oak_log，直接收集 10 个橡木原木成功率低。",
  "suggestion": "先 inspect_surroundings 搜索树木，或改为收集附近任意原木。"
}
```

### 预检建议

建议进入 draft 或 execution context：

```text
神经符号建议：
- 目标：收集 10 个 oak_log
- 先用 world.getNearestBlock / nearby_blocks 确认 oak_log
- 若附近 oak_log 不足，收集部分数量后返回已获得数量，不要把部分成功当作完全失败
```

### 执行后复核

在 `LAST_TOOL_RESULT` 或 working memory 中保留：

```json
{
  "intent_status": "partially_achieved",
  "progress": "5/10 oak_log",
  "recommendation": "继续同一意图，但把目标改为再收集 5 个，或先搜索更密集树林。"
}
```

这样 Agent Loop 下一轮可以继续、改写步骤或重新规划，而不是被执行层的布尔 success 误导。

---

## 评估指标

只评估意图层。

- `precheck_precision`: 被 block/ask_inspect 的步骤中，后续证明确实不可行或信息不足的比例
- `false_block_rate`: 被规则阻止但实际可成功的比例
- `partial_success_detection_rate`: 部分成功是否被正确识别
- `intent_verdict_accuracy`: achieved/partial/not/unknown 的人工抽样准确率
- `repeat_failure_rate`: 同类不可行意图是否减少
- `planning_revision_rate`: Agent Loop 因神经符号反馈改写步骤的频率
- `task_progress_delta`: 引入意图层校验后任务推进是否更稳定

---

## 实施步骤

### 阶段一：只记录，不干预

- 新建 `neurosymbolic` 包和 `intent_transitions.jsonl`。
- 在 `execute_step` 前后记录 `DecisionContext / Intent / execution_result / IntentVerdict`。
- 实现基础 Intent Classifier 和 Intent Verifier。
- 先不 block，只观察判定质量。

### 阶段二：软预检和执行指导

- 实现 `retrieve_intent_context()`，把高置信规则注入 Agent Loop prompt。
- 实现 `precheck_intent()`，只输出 `allow/advise/ask_inspect/rewrite_step`。
- 将 `execution_guidance` 写入 draft 或 execution context，指导执行层用合适函数。

### 阶段三：有限 hard guard

- 对确定性高的规则启用 `block`，例如缺少必要材料、生命值过低还要战斗、目标方块完全不在可见/可搜索范围且步骤没有搜索策略。
- 加入 false block 监控，误杀高的规则自动降级为 advise。

### 阶段四：规则学习和剪枝

- 从 transition 中归纳意图层规则。
- 编译成 JSON DSL 并离线回放历史 transitions。
- 用 coverage/counterexample 做最大覆盖剪枝。

### 阶段五：弱联动长期记忆

- 将稳定规则摘要可选写入 `pattern` 节点，metadata 标记 `source=neurosymbolic` 和 `rule_id`。
- 继续保持完整规则、判定逻辑和 transition buffer 独立。

---

## 结论

当前阶段应把神经符号模块限定为 **意图层环境判定 + 意图结果复核**。它读取与 decision loop 等价甚至更结构化的环境信息，先判断步骤是否值得执行，再在执行后用状态差异和目标完成度重新解释结果。

这样可以解决两个关键问题：

- 执行前：避免 Agent Loop 提出明显不可行、过大或缺少环境证据的步骤，同时给执行层函数级指导。
- 执行后：不再把 `success=true/false` 当作最终真相，而是区分完全成功、部分成功、无进展、未知和高副作用成功。

代码层校验暂时不纳入本计划，等意图层稳定后再复用这套 Rule Store / DSL / transition 机制迁移。
