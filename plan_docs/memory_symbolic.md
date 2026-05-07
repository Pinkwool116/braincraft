# 神经符号记忆扩展计划

目标：把 WALL-E 2.0 的神经符号方法作为当前记忆系统的旁路扩展，用于两类校验：

1. **Agent Loop 层的意图/步骤可行性校验**：高层模型提出 `execute_step` 的自然语言步骤后，先判断该意图在当前游戏状态下是否可能成功。
2. **Coding Agent 的代码生成校验**：Coding LLM 生成 JavaScript 后，执行前检查稳定的 Mineflayer/项目技能库代码错误模式。

核心原则仍然是：**神经符号模块与现有 MemoryRouter / GraphEngine 解耦**。它有自己的 Rule Store 和 transition buffer，只通过明确接口读取状态、执行结果和少量检索上下文。长期记忆图谱最多保存规则摘要引用，不保存完整规则，也不承担规则执行。

---

## 依据与边界

WALL-E 2.0 的核心机制是从真实轨迹和 world model 预测轨迹的成功/失败差异中归纳符号知识，包括 action rules、knowledge graph、scene graph，再把这些知识翻译成可执行代码规则，并用最大覆盖剪枝保留最有用的规则。论文把规则用于校准 LLM world model 对 `(observation, action)` 是否成功的预测，而不是直接训练策略或保存大量原始轨迹。见论文 [3.1 NeuroSymbolic Learning of Code Rules](https://arxiv.org/html/2504.15785v1)。

官方 demo 代码比较简化：`Demo/ruleminer.py` 主要按 `act_name` 对 transition buffer 分批做规则新增和规则改进；`Demo/buffer.py` 通过 `exec()` 加载规则函数，并在 world model 预测阶段依次运行规则函数。见 [WALL-E 仓库](https://github.com/elated-sawyer/WALL-E)、[ruleminer.py](https://raw.githubusercontent.com/elated-sawyer/WALL-E/main/Demo/ruleminer.py)、[buffer.py](https://raw.githubusercontent.com/elated-sawyer/WALL-E/main/Demo/buffer.py)。

因此，本项目可借鉴的是：

- 从执行轨迹归纳紧凑规则，而不是把所有失败经历都塞进 prompt。
- 规则必须可执行、可评估、可剪枝。
- 规则优先服务于“动作是否会成功”的预测/校验。

需要调整的是：

- **代码模式校验不是 WALL-E 原生目标**，而是本项目因为存在 Coding LLM 和 Mineflayer API 才引入的工程扩展。
- 环境规则和代码模式规则可以共用 Rule Store、LLM 归纳、DSL 编译、剪枝指标，但 transition 抽取和验证器输入不同，不能强行说是完全同一管道。
- 不能照搬 demo 的 `exec()` 执行规则函数；本项目第一阶段应使用 JSON DSL + 本地解释器，避免执行 LLM 生成的任意 Python。

---

## 对原计划中不准确/不合理处的修正

1. **“crystallize 之后再提取 transition”不合适**

   当前 `MemoryRouter.crystallize()` 会把 working memory 蒸馏进图谱，然后清空 working memory。transition 需要保留执行前后状态、生成代码、错误、输出、意图验证结果，这些结构化信息应在 `execute_step` 执行边界直接记录，而不是等 crystallize 后从摘要里反推。

2. **“预检接口同时检查环境规则和代码模式规则”时序不对**

   Agent Loop 产出的只有自然语言 `step_description`，此时还没有代码。环境意图可行性可以在 Coding LLM 调用前检查；代码模式规则必须在 `ExecutionLayer.execute_step()` 中，Coding LLM 生成 `code` 之后、真正 IPC 执行之前检查。

3. **“代码模式规则可更早设为硬约束”表述过强**

   Mineflayer API 相对稳定，但项目大量使用 `skills.*` 和 `world.*` 封装，很多错误与任务上下文、游戏状态、封装函数行为有关。代码规则可以先做强提示和 lint-like warning，只有低误杀率、稳定复现的规则才进入 hard block。

4. **“完整规则摘要写入 pattern 节点并改 graph_retriever 加权”会削弱解耦**

   当前 `GraphRetriever.spread_activation()` 只做图扩散和权重衰减，没有按 metadata subtype 加权的机制。为了保持解耦，第一阶段不修改图检索器。Rule Store 自己提供检索接口；长期图谱只在后期可选写入摘要 pattern，用于让普通记忆召回时能发现“有相关规则存在”。

5. **“KG/Scene Graph 直接写入现有长期图谱”与独立规则模块目标冲突**

   现有 `NodeType` 只有 `event/place/person/item/time/pattern/thought/community`，`EdgeRelation` 也没有 `REQUIRES/CONSUMES/ENABLES`。第一阶段不要扩展 GraphEngine 枚举；KG constraint 和 scene fact 先存在 Rule Store 内部。等规则稳定后，再考虑把摘要或事实映射到现有 `item/place/pattern` 节点。

6. **“意图分类自动扩展类别”过早**

   当前系统没有规则审核、人类确认或离线评估闭环。LLM 自动新增 intent category 容易导致类别漂移。第一阶段使用固定类别 + 低置信 fallback；新类别只记录到候选日志，不参与 hard guard。

7. **“MPC”不应作为早期目标**

   当前 Agent Loop 是工具调用循环，不是候选轨迹规划器。早期只做 one-step guard：当前步骤被判定不可行时，把失败原因作为工具结果交还 Agent Loop 重新决策。多步 look-ahead/MPC 放到最后。

---

## 当前代码中的真实接入点

### Agent Loop 层

相关文件：

- `braincraft/agent/brain/agent_brain/agent_loop_layer.py`
- `braincraft/agent/brain/tools/execute_step_tool.py`
- `braincraft/agent/prompts/agent_loop/system.md`

当前流程是：

```text
build_prompt()
  -> Agent Loop LLM 选择工具
  -> parse_tool_call()
  -> execute_tool()
  -> ExecuteStepTool.execute()
  -> ExecutionLayer.execute_step(step_description)
```

适合加入两处环境规则能力：

1. **意图生成前的软约束检索**
   在 `AgentLoopLayer.build_prompt()` 中根据当前 `state + todolist + draft + last_tool_result` 调用 `neurosymbolic.retrieve_rules(domain="environment")`，把少量高置信规则注入 Agent Loop prompt。作用是让高层模型在生成步骤前就避开明显不可行意图。

2. **步骤执行前的硬/软预检**
   在 `ExecuteStepTool.execute()` 或 `ExecutionLayer.execute_step()` 开头调用：

   ```python
   precheck_step(step_description, current_state) -> GuardResult
   ```

   如果是 hard block，直接返回：

   ```json
   {
     "success": false,
     "failure_reason": "precondition",
     "error": "神经符号规则判定当前步骤不可行：缺少 stone_pickaxe",
     "suggestion": "先合成或装备 stone_pickaxe，再挖 iron_ore"
   }
   ```

   这样 Agent Loop 会在下一轮看到工具失败结果并重新决策，符合当前“Execution Layer 不内部重试”的架构。

### Coding Agent / Execution Layer

相关文件：

- `braincraft/agent/brain/agent_brain/execution_layer.py`
- `braincraft/agent/prompts/execution_layer/coding.md`
- `braincraft/agent/bridge/minecraft_bridge.js`
- `braincraft/src/agent/library/skills.js`

当前 `ExecutionLayer.execute_step()` 流程是：

```text
_build_coding_prompt(step_description)
  -> Coding LLM
  -> _parse_coding_response()
  -> _validate_code()
  -> _inject_interrupt_checks()
  -> _execute_code()
```

适合加入两处代码规则能力：

1. **代码生成前的规则提示**
   在 `_build_execution_context()` 或 `_build_coding_prompt()` 中追加：

   ```python
   retrieve_rules(domain="code_pattern", query=step_description)
   ```

   用于提示 Coding LLM 避免已知模式，例如缺少 `await`、错误使用不存在的 `skills/world` 函数、坐标参数写错等。

2. **生成代码后的静态/DSL 校验**
   在 `_parse_coding_response()` 后、现有 `_validate_code()` 前后调用：

   ```python
   validate_code(step_description, intent, code, current_state) -> GuardResult
   ```

   失败时不要直接执行代码。第一阶段返回失败结果交给 Agent Loop；后期可以考虑在 Execution Layer 内做一次带规则反馈的重新生成，但这会改变当前“无内部 retry”的边界，应单独设计。

### Transition 记录

当前 JS bridge 成功执行时会返回：

```json
{
  "success": true,
  "output": "...",
  "state_before": {"position": ..., "health": ..., "food": ..., "inventory": ...},
  "state_after": {"position": ..., "health": ..., "food": ..., "inventory": ...},
  "changes": {"position_changed": true, "inventory_changed": false}
}
```

失败时目前主要返回 `error/error_stack/output`，不稳定包含执行前后状态。因此 transition recorder 不能只依赖 JS 返回值。Python 侧应在 `ExecutionLayer.execute_step()` 开始时从 `shared_state.get_all()` 捕获 `pre_state`，执行结束后再读取一次 `post_state`，与 JS 返回的 `state_before/state_after` 互补。

---

## 模块边界

新增独立包建议：

```text
braincraft/agent/neurosymbolic/
  __init__.py
  service.py                 # 对外门面：precheck_step / validate_code / record_transition / retrieve_rules
  schemas.py                 # GuardResult, Intent, Transition, RuleRecord
  intent_classifier.py       # 固定类别 + 低置信 LLM fallback
  transition_recorder.py     # 执行前后状态、代码、错误、输出、意图结果
  intent_verifier.py         # 判断代码成功但意图是否达成
  rule_store.py              # bots/{agent}/neurosymbolic/*.json
  rule_miner.py              # LLM 归纳文本规则
  rule_compiler.py           # 文本规则 -> JSON DSL
  rule_validator.py          # DSL 解释器
  rule_pruner.py             # 最大覆盖剪枝
```

存储建议：

```text
bots/{agent}/neurosymbolic/
  transitions.jsonl
  rules_environment.json
  rules_code_pattern.json
  rule_metrics.json
  intent_candidates.json
```

不要把完整规则存入 `memory_graph/`。如果后期需要与图谱联动，只写入类似下面的摘要节点：

```json
{
  "type": "pattern",
  "content": "规则摘要：挖 iron_ore 前需要 stone_pickaxe 或更高等级镐",
  "metadata": {
    "source": "neurosymbolic",
    "rule_id": "env_mine_iron_requires_stone_pickaxe",
    "domain": "environment"
  }
}
```

---

## 规则域设计

### 1. 环境规则域

用途：判断自然语言步骤对应的意图在当前状态下是否可行。

输入：

```json
{
  "step_description": "挖掘附近的 3 块铁矿石",
  "intent": {"category": "mine", "target": "iron_ore", "quantity": 3},
  "state": {
    "inventory": {},
    "equipment": {"mainHand": "wooden_pickaxe"},
    "nearby_blocks": [],
    "biome": "plains"
  }
}
```

输出：

```json
{
  "pass": false,
  "domain": "environment",
  "failure_reason": "precondition",
  "matched_rules": ["env_mine_iron_requires_stone_pickaxe"],
  "feedback": "当前工具不足，挖 iron_ore 很可能失败。",
  "suggestion": "先合成并装备 stone_pickaxe 或更高等级镐。",
  "confidence": 0.86,
  "hard_block": false
}
```

环境规则第一阶段默认不 hard block，只作为强提示；对确定性非常高且有足够样本支持的规则再升级。

### 2. 代码模式域

用途：检查生成的 JavaScript 是否违反稳定的项目代码/技能库约束。

输入：

```json
{
  "step_description": "在当前位置下方挖一格",
  "intent": {"category": "mine", "target": "block_below"},
  "code": "await skills.breakBlockAt(bot, p.x, p.y - 1, p.x);",
  "state": {}
}
```

输出：

```json
{
  "pass": false,
  "domain": "code_pattern",
  "failure_reason": "code_pattern",
  "matched_rules": ["code_breakblockat_z_arg_not_x"],
  "feedback": "skills.breakBlockAt(bot, x, y, z) 的第三个坐标参数疑似误用了 x。",
  "suggestion": "改为 await skills.breakBlockAt(bot, p.x, p.y - 1, p.z);",
  "confidence": 0.92,
  "hard_block": true
}
```

代码规则更适合与现有 `_validate_code()` 并列：现有校验处理禁止模式和函数存在性，神经符号校验处理从历史失败中学到的更具体模式。

---

## Transition 结构

```json
{
  "transition_id": "uuid",
  "timestamp": 0,
  "step_description": "挖掘附近的 3 块铁矿石",
  "intent": {
    "category": "mine",
    "target": "iron_ore",
    "quantity": 3,
    "confidence": 0.78
  },
  "pre_state": {
    "position": {},
    "biome": "unknown",
    "inventory": {},
    "equipment": {},
    "health": 20,
    "food": 20,
    "nearby_blocks": [],
    "nearby_entities": []
  },
  "code": "...",
  "execution": {
    "code_success": true,
    "output": "...",
    "error": "",
    "error_stack": "",
    "error_signature": null
  },
  "post_state": {
    "position": {},
    "inventory": {}
  },
  "intent_result": {
    "intent_achieved": false,
    "state_delta": {"inventory": {"iron_ore": 0}},
    "reason": "代码无异常，但目标物品数量未增加"
  },
  "failure_reason": "none | precondition | code_pattern | intent_not_achieved | runtime_error",
  "rule_hits": []
}
```

关键点：`success=True` 只能说明 JS 没抛异常，不一定说明意图达成。必须增加 `IntentVerifier`，基于执行前后 inventory、position、health、nearby state 和输出日志做弱验证。

---

## Intent 分类策略

第一阶段使用固定类别，避免类别漂移：

```text
mine, craft, place, move_to, attack, collect, build, smelt, explore, equip, eat, store, wait, chat, inspect
```

流程：

```text
step_description
  -> 关键词/正则规则匹配
  -> 低置信时 LLM 在固定类别中选择
  -> 仍低置信则 category="unknown"，只记录 transition，不用于 hard guard
```

LLM 提案的新类别只写入 `intent_candidates.json`，不自动参与规则执行。等有评估指标后再考虑候选提升。

---

## Rule Store 与 DSL

规则记录：

```json
{
  "rule_id": "env_mine_iron_requires_stone_pickaxe",
  "domain": "environment",
  "intent_category": "mine",
  "description": "挖 iron_ore 需要 stone_pickaxe 或更高等级镐",
  "dsl": {
    "all": [
      {"eq": ["intent.category", "mine"]},
      {"eq": ["intent.target", "iron_ore"]},
      {"not_inventory_tool_at_least": "stone_pickaxe"}
    ],
    "result": {
      "pass": false,
      "feedback": "当前工具不足，挖 iron_ore 很可能失败。",
      "suggestion": "先合成或装备 stone_pickaxe。"
    }
  },
  "support_count": 4,
  "counterexample_count": 0,
  "confidence": 0.86,
  "hard_block": false,
  "covered_transition_ids": []
}
```

DSL 第一阶段只支持白名单操作：

```text
eq, neq, contains, not_contains, any, all,
inventory_has, inventory_lacks,
equipment_is, nearby_block_exists,
state_delta_matches,
code_contains, code_regex,
function_call_exists
```

不要在第一阶段执行 LLM 生成的 Python。后期如确实需要 Python AST 规则，也应先做白名单 AST 校验和隔离执行。

---

## 剪枝与评估

按 domain 分开统计，避免环境规则和代码规则互相污染。

指标：

- `prediction_accuracy`: 规则对 transition 成功/失败预测的准确率
- `rule_coverage`: 失败 transition 中有多少被规则解释
- `false_block_rate`: 规则预测失败但后续证明可成功的比例
- `repeat_error_rate`: 同类失败是否减少
- `code_retry_rate`: 因代码规则返回失败后重新生成代码的频率
- `planning_revision_rate`: 因环境规则反馈导致 Agent Loop 改步骤的频率

剪枝：

```text
1. 过滤 support_count 太低或 counterexample 太多的规则
2. 合并同 domain 下语义/DSL 等价规则
3. 用 greedy maximum coverage 选择能覆盖最多失败 transition 的规则子集
4. 对 hard_block 规则使用更严格的 false_block_rate 阈值
```

---

## 实施步骤

### 阶段一：旁路记录与软提示

- 新建 `neurosymbolic` 包、Rule Store、transition buffer。
- 在 `BrainCoordinator` 初始化服务，并传给 Agent Loop / Execution Layer。
- 在 `ExecutionLayer.execute_step()` 前后记录 transition，先不改变行为。
- 在 Agent Loop prompt 和 Coding prompt 中注入少量高置信手写规则/历史规则文本。

### 阶段二：环境意图预检

- 实现固定类别 Intent Classifier。
- 实现环境规则 JSON DSL 和解释器。
- 在 `ExecuteStepTool` 或 `ExecutionLayer.execute_step()` 开头加入 `precheck_step()`。
- 默认 soft guard；确定性规则可配置为 hard block。

### 阶段三：代码模式校验

- 从代码、错误栈、输出日志中抽取 error signature。
- 实现 `validate_code()`，接入 `_parse_coding_response()` 后、实际执行前。
- 先返回 warning/失败结果，不在 Execution Layer 内部做自动多轮 retry。

### 阶段四：规则归纳与剪枝

- 用 LLM 从 transitions 分 domain 归纳文本规则。
- 编译为 JSON DSL，离线回放 transitions 计算 coverage/counterexample。
- 引入最大覆盖剪枝，生成 active rule set。

### 阶段五：与长期图谱弱联动

- 只把稳定规则摘要写入 `pattern` 节点，metadata 带 `source=neurosymbolic` 和 `rule_id`。
- 保持完整规则和执行逻辑在 Rule Store 内。
- 暂不扩展 `NodeType/EdgeRelation`；KG/scene facts 先存在神经符号模块内部。

### 阶段六：有限 look-ahead

- 在 one-step guard 稳定后，让 Agent Loop 对被拒绝意图生成替代步骤。
- 后续再考虑多步候选计划或 WALL-E 风格 MPC。

---

## 结论

WALL-E 2.0 适合本项目的核心点是“从执行轨迹中归纳可执行规则，用规则校准动作成功/失败预测”。在当前 MindCraft 架构中，最合理的落点不是改造 MemoryRouter，而是新增一个独立神经符号服务：

- Agent Loop 侧负责意图规则检索和步骤可行性预检。
- Execution Layer 侧负责代码规则提示和生成后校验。
- Transition 在执行边界直接记录，不依赖 crystallize。
- Rule Store 独立持久化，图谱记忆只做可选摘要引用。

这样既能实现“Agent Loop 意图生成 + Coding Agent 代码生成双层校验”，又不会把现有图谱记忆系统变成规则引擎。
