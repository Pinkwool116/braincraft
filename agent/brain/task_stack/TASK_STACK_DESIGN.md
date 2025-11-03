# 设计文档：基于任务栈（Task Stack）的动态任务管理系统

## 1. 引言与问题陈述

当前的任务管理系统使用一个扁平化的 `task_plan` 结构。该系统在执行线性、无中断的任务时表现良好，但在处理复杂场景时暴露了以下局限性：

- **无法处理任务中断**：当玩家提出新请求时，系统没有优雅的机制来暂停当前任务、执行玩家请求、然后再恢复原任务。
- **子任务管理困难**：当一个宏大任务（如“建造庇护所”）中的某一步（如“收集木头”）遇到困难时，系统无法动态地创建一个临时的、更简单的子任务来解决当前瓶颈。
- **职责混淆**：`handle_modification_request` 函数同时处理内部任务失败和外部玩家请求，逻辑耦合，难以扩展。
- **决策上下文不足**：当中层大脑求助时，高层大脑缺乏足够的短期记忆和对整体任务背景的了解来分析失败的根本原因。

为了解决这些问题，我们引入一个基于**任务栈（Task Stack）**的动态任务管理系统。

## 2. 核心概念：任务栈 (`Task Stack`)

任务栈是一个后进先出（LIFO）的数据结构，用于存储和管理所有的 `task_plan` 对象。

- **当前任务**: 栈顶 (`task_stack[-1]`) 的 `task_plan` 永远是Agent当前需要执行的任务。
- **任务压栈 (Push)**: 当一个更高优先级的任务出现时（如玩家请求或解决困难的子任务），它会被创建并压入栈顶。当前任务的状态会被自动设置为 `paused`。
- **任务弹栈 (Pop)**: 当栈顶任务完成后，它会从栈中被弹出。如果栈中还有其他任务，新的栈顶任务（即之前被暂停的任务）的状态会被恢复为 `active`，Agent将继续执行。

**优势**:
- **优雅的中断与恢复**: 完美支持“暂停-执行-恢复”的非线性任务流。
- **优先级管理**: 玩家任务或紧急子任务可以自然地获得最高执行优先级。
- **逻辑解耦**: 将任务的生成、执行和调度清晰地分离开来。

## 3. 数据结构变更

### 3.1. `HighLevelBrain` 的核心变量

在 `high_level_brain.py` 的 `__init__` 方法中，引入以下核心变量。

```python
# high_level_brain.py

class HighLevelBrain:
    def __init__(self, ...):
        # ...
        # self.task_plan = { ... }  <-- 删除旧结构
        self.task_stack = []  # <-- 引入新结构：一个存储 task_plan 对象的列表
        self.task_stack_summary = "" # <-- 引入新结构：任务栈的文本摘要，用于LLM决策
        # ...
```

### 3.2. 扩展的 `task_plan` 对象结构

每个 `task_plan` 对象将包含更丰富的元数据。

```json
{
  "goal": "任务的总体目标，例如：为玩家Lagranye建造一个小型庇护所",
  "steps": [
    {"id": 1, "description": "收集20个橡木原木", "status": "pending"},
    {"id": 2, "description": "制作一个工作台", "status": "pending"}
  ],
  "current_step_index": 0,
  "status": "active", // "active" | "paused" | "completed"
  "source": "internal" | "player", // 任务来源
  "player_name": "Lagranye" // 如果 source 是 'player'，则记录玩家名
}
```

## 4. 架构重构：函数职责分离

我们将 `handle_modification_request` 拆分为两个职责清晰的新函数。

### 4.1. `handle_stuck_task(request)` - 处理内部任务卡顿

- **职责**: 专门处理中层大脑因执行困难而发出的求助。
- **触发**: 中层大脑在多次重试一个步骤失败后调用。
- **核心流程**:
    1. 接收请求，包含失败步骤、失败原因等。
    2. **（新）** 从 `memory_manager` 获取最近50条短期记忆。
    3. **（新）** 更新并获取 `task_stack_summary`。
    4. 构建包含**失败上下文**、**短期记忆**和**任务栈摘要**的丰富提示词。
    5. LLM基于丰富信息做出决策：
        - **针对内部任务 (`source: 'internal'`)**:
            - **`REVISE_AND_REPLACE`**: 认为当前任务步骤不合理。此时，**弹出**当前任务，生成一个具有更合理步骤的新 `task_plan`，然后**压入**栈顶。
            - **`ADD_SUB_TASK`**: 认为当前任务过于宏大或缺少前置条件。此时，保留当前任务，创建一个新的、更小的 `task_plan`（例如“制作一把石斧来更快地砍树”），并将其**压入**栈顶作为子任务。
            - **`DISCARD_TASK`**: 认为当前任务目标不合理或无法实现。此时，直接**弹出**并放弃该任务。
            - **`REJECT_REQUEST`**: 认为中层应该继续尝试。此时，向中层返回指导性建议。
        - **针对玩家任务 (`source: 'player'`)**:
            - **`REVISE_STEPS`**: 保证总体目标不变，修改或优化 `steps`。
            - **`DISCARD_AND_REPORT`**: 认为任务不可能实现。此时，**弹出**任务，并生成需要向玩家报告的原因。
            - **`ADD_SUB_TASK`**: 同上，为玩家任务增加一个前置子任务。
            - **`REJECT_REQUEST`**: 同上，指导中层继续尝试。

- **增强后的提示词示例**:
  ```prompt
  You are a strategic planner. Your tactical executor is stuck on a task.

  OVERALL TASK STACK:
  {task_stack_summary}

  CURRENT TASK (Top of Stack):
  {current_plan_text}

  FAILED STEP:
  {failed_step_description}

  RECENT FAILURES:
  - Error: Cannot find any oak trees in the current area.
  - Error: Execution timed out while searching for trees.

  RECENT SHORT-TERM MEMORY (last 50 events):
  - [timestamp] event: 'world_update', content: 'biome is now desert'
  - [timestamp] event: 'code_execution', content: 'bot.findBlock({ matching: "oak_log" }) failed'
  - ... (48 more events)

  Based on the task source ('internal' or 'player'), choose an appropriate action from the list below.

  If source is 'internal':
  1. REVISE_AND_REPLACE: Discard the current task and push a new one with better steps.
  2. ADD_SUB_TASK: Keep the current task and push a smaller prerequisite task on top.
  3. DISCARD_TASK: Give up on the current task entirely.
  4. REJECT_REQUEST: Provide guidance for the mid-level brain to retry.

  If source is 'player':
  1. REVISE_STEPS: Modify the steps of the current task while keeping the goal.
  2. DISCARD_AND_REPORT: Give up and generate a reason to report to the player.
  3. ADD_SUB_TASK: Keep the current task and push a smaller prerequisite task on top.
  4. REJECT_REQUEST: Provide guidance for the mid-level brain to retry.

  Respond with JSON containing your decision and the required data.
  ```

### 4.2. `handle_player_directive(request)` - 处理玩家任务指令

- **职责**: 专门处理从聊天中解析出的玩家任务请求。
- **触发**: 中层大脑检测到聊天内容包含任务意图时调用。
- **核心流程**:
    1. 接收请求，包含玩家名和任务描述（如“帮我盖个房子”）。
    2. **决策分析**:
        - 当前任务栈是否为空？如果空闲，接受任务的倾向更高。
        - 当前任务是什么？重要性如何？（LLM需要权衡中断成本）
        - 与该玩家的关系如何？（`players.json`）
    3. **如果接受**:
        a. 调用 `create_task_plan` 生成一个全新的 `task_plan`。
        b. 设置 `source: 'player'` 和 `player_name`。
        c. **暂停当前任务**: 如果任务栈不为空，将栈顶任务的 `status` 设为 `paused`。
        d. **压入新任务**: 将新创建的玩家任务 `task_plan` 压入栈顶。
    4. **如果拒绝**: 生成礼貌的拒绝理由（例如“对不起，我正在执行一个非常重要的任务，稍后可以吗？”），并交由中层大脑（chat部分）回应。

## 5. 详细工作流

### 5.1. 工作流：任务完成与恢复

1.  **执行**: 中层大脑始终只关注 `task_stack` 的栈顶任务 (`task_stack[-1]`)。
2.  **完成**: 当栈顶任务的所有步骤都完成后，中层大脑通知高层大脑。
3.  **弹栈**: 高层大脑将该任务从栈中**弹出** (`task_stack.pop()`)。
4.  **恢复**:
    - 弹栈后，高层检查任务栈是否为空。
    - 如果不为空，说明有被暂停的父任务。
    - 高层大脑取出新的栈顶任务，将其 `status` 从 `paused` 修改为 `active`。
    - 中层大脑在下一个处理周期中，会自动开始执行这个被恢复的父任务。

## 6. 高级机制与边缘情况处理

为了使系统更健壮和智能，我们加入以下机制：

### 6.1. 任务栈的持久化

- **保存**: 在 `_save_persisted_state` 函数中，将 `self.task_stack` 完整地序列化并存入 `mind_state.json`。
- **加载**: 在 `_load_persisted_state` 函数中，从 `mind_state.json` 恢复 `self.task_stack`。
- **效果**: Agent重启后，可以无缝地继续执行之前的任务，包括被中断的复杂任务流。

### 6.2. 上下文切换成本管理

在 `handle_player_directive` 的决策提示词中，明确告知LLM中断当前任务的成本。

```prompt
A player named {player_name} has asked you to: "{directive}".

You are currently working on the following task:
- Goal: {current_task_goal}
- Progress: Step {current_step + 1} of {total_steps}

Decide whether to accept the player's request.

Consider:
- Your relationship with {player_name} is {relationship_status}.
- Interrupting your current task will delay its completion. Is the player's request more urgent or important?

Respond with JSON: { "decision": "accept" | "reject", "reason": "..." }
```

### 6.3. 栈深度限制

（可以不用设置，让模型通过stack_summary自行判断）

### 6.4. 任务超时与放弃机制

对于来源为 `'player'` 的任务，可以引入一个超时或失败次数上限。

（这里我建议不这样做，模型尽量完成玩家的任务。如果不能完成，就删除，然后向玩家说明原因，让玩家重新分配或者取消）

- 在 `task_plan` 中增加字段：`max_retries` 或 `deadline_timestamp`。
- 当任务执行超过限制仍未完成时，高层大脑可以触发一个特殊的“任务失败”流程：
    1.  主动向玩家报告：“对不起，我尝试了多次，但无法完成你交给我的任务‘{goal}’，原因可能是...”。
    2.  将该任务从栈中弹出。
    3.  恢复执行之前的任务。
- 这使得Agent在面对无法完成的指令时，表现得更像一个智能的合作者，而不是一个卡住的机器。

## 7. 总结

通过引入任务栈，我们不仅解决了当前系统在任务管理上的核心痛点，还为Agent赋予了更高级的规划、中断、恢复和沟通能力。这套架构将使Agent的行为模式更加动态、健壮和类人。
