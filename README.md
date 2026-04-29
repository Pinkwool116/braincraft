# BrainCraft - Agent Loop 架构智能体

## 概述

本项目基于 [MindCraft](https://github.com/mindcraft-bots/mindcraft) 项目，实现了一个以 **Agent Loop** 为核心的主动式 Minecraft 智能体系统。系统采用异步架构与工具调用（Tool Calling）机制，实现了自主规划、任务执行和生存反射的高度解耦。

### 核心架构

- **Agent Loop Layer (决策层)**: 系统的"思考主循环"，自主读取游戏状态、记忆与周边环境，并通过工具调用（Tool Calling）向下一层派发任务，管理整个宏观目标。
- **Execution Layer (执行层)**: 充当高级代码生成器工具，仅在被决策层调用时生效。通过专门的 Coding LLM 生成 JavaScript 代码来驱动 Minecraft 物理动作，并带有智能重试机制。
- **Reflex Layer (反射层)**: 底层神经反射，与 LLM 无关。以高频（100ms）心跳运行，自动处理生存相关的本能动作（如吃东西、燃烧时跳水、跌落保护、被攻击反击等）。

## 核心特性

### 🎯 三层文本化任务管理
采用 `plan.md` + `todolist.md` + `draft.md` 三层文件架构，按时间尺度与抽象层次完全正交：

| 层 | 文件 | 时间尺度 | 抽象层次 | 工具 |
|---|---|---|---|---|
| 宏观 | `plan.md` | 几天～整局 | 阶段目标、长期方向、背景约束、延后备忘 | `plan` |
| 中观 | `todolist.md` | 几分钟～几小时 | 结构化待办，支持嵌套和 ID 寻址 | `todolist` |
| 微观 | `draft.md` | 当前这一步 | 技术思路、失败尝试、给 Coding LLM 的提示 | `draft` |

- **结构化 todolist**：支持 ID 编号（`t1` → `t1.2` → `t1.2.3`）和缩进双重保证嵌套；每条可精确寻址（`add / remove / set_status / move / overwrite`）。
- **内容注入**：三个文件的内容由 `build_prompt()` 读取并注入提示词，工具仅负责任修改操作（无 `read` action）。

### 🛠️ 工具调用机制 (Tool Calling)
将所有能力封装为可被模型识别的工具。目前支持：
- `execute_step`: 生成与执行 JavaScript 脚本行动。
- `plan`: 写入/清空长期规划（plan.md）。
- `todolist`: 结构化增删改短期待办（add / remove / update / set_status / move / overwrite）。
- `draft`: 写入/清空当前步骤技术思路（draft.md）。
- `chat`: 与玩家交流。
- `recall_memory`: 从复杂的记忆图谱中检索信息。
- `interrupt_execution`: 打断当前行动，用于遇险或突发指令。
- `wait`: 主动休眠等待 N 秒。

### 🧠 主动探索机制（Idle-Thinking）
- 没有任务就主动探索。
- 当系统处于无玩家任务的完全空闲 (Idle) 时，Agent 不会死板地挂起休息，而是依然拥有决策权，可以主动决定是散步探索、收集物资或主动找玩家交互。

### 🧩 工作记忆系统 (Working Memory)
所有关键信息自动写入短期记忆（线性缓冲区），定期滚动压缩（consolidate），任务阶段结束时蒸馏为长期记忆图谱（crystallize）。

**写入的信息类型（entry_type）**：

| entry_type | 来源 | 内容 |
|---|---|---|
| `reasoning` | Agent Loop 每轮决策 | LLM 的 thinking 全文（本轮决策的 WHY） |
| `action` | Agent Loop 工具调用 | execute_step 执行结果、todolist 结构化修改、interrupt 等 |
| `interaction` | 玩家消息 + Bot 发言 | `收到消息 [Player]: ...` 和 `发送消息: ...` |
| `code_attempt` | Execution Layer 每次代码生成 | 分析（analysis）+ 代码 + 执行输出/错误（全量，不截断） |
| `observation` | Reflex Layer 反射触发 | 战斗、低血逃生、着火、溺水、受伤、卡住脱困（30s debounce） |

**关键设计**：
- 反射事件视为环境信息：`observation` 条目是底层生存反射自动触发的，Agent 无法手动控制（系统提示词中明确说明）
- `consolidate_interval = 30`：每 30 条原始条目触发一次 LLM 滚动压缩
- 持久化：`bots/{name}/working_memory_raw.json` + `working_memory_summary.md`

### 🌟 灵活的提示词配置系统 (soul.md)
引入 `soul.md` 作为机器人的内在人格配置：
- **人格塑造**: 允许用户配置专属的行事风格和最终目标（如探险家、生存专家、幽默的同伴、专注建筑等）。
- **语言风格**: 影响 Bot 全局的思考逻辑和与玩家对话时的情绪反馈。

## 架构图

```text
┌─────────────────────────────────────────────────────────┐
│              Agent Loop Layer (主控循环层)               │
│  • 读取世界态、记忆、plan / todolist / draft            │
│  • 驱动主决策 LLM 行动                                  │
│  • 统一派发工具调用（plan、todolist、draft、chat 等）    │
└──────────────┬──────────────────────────┬───────────────┘
               │ 触发 execute_step         │ 读写 plan/draft/
               ↓                           │ todolist 三文件
┌──────────────────────────────────────┐   │
│           Execution Layer            │   │
│  • 根据目标请求 Coding LLM 生成代码    │   │
│  • 将 JS 送入 IPC 执行               │   │
│  • 读取 draft.md 获取决策层技术提示   │   │
└──────────────┬──────────────────────┘   │
               │ JS 动作指令              │
               ↓                          ↓
┌─────────────────────────────────────────────────────────┐
│               Reflex Layer (高频反射层)                  │
│  • 生命垂危、燃烧、窒息的本能抢救                        │
│  • 脱困(Stuck) 防护                                     │
│  • 触发事件自动写入工作记忆（observation）               │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 前置要求

- **Python**: 3.8 或更高版本（建议 3.13.5）
- **Node.js**: 18.x 或更高版本（建议 v22.20.0）
- **Minecraft Java Edition**: 1.22.6 及以下（建议 1.22.6）

### 环境配置

#### 步骤 1: 创建并激活虚拟环境（推荐）

```powershell
# 使用 Conda（推荐）
conda create -n braincraft python=3.13.5
conda activate braincraft

# 或使用 venv
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

#### 步骤 2: 安装 Python 依赖

```powershell
# 确保虚拟环境已激活
pip install -r requirements.txt
```

#### 步骤 3: 安装 JavaScript 依赖

```powershell
# 安装主项目依赖
npm install

# 安装桥接模块依赖
cd agent\bridge
npm install
cd ..\..
```

#### 步骤 4: 配置 API 密钥

在 **项目根目录**下创建 `keys.json`，填入你的 API 密钥:

```json
{
    "OPENAI_API_KEY": "",
    "OPENAI_ORG_ID": "",
    "GEMINI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "REPLICATE_API_KEY": "",
    "GROQCLOUD_API_KEY": "",
    "HUGGINGFACE_API_KEY": "",
    "QWEN_API_KEY": "",
    "XAI_API_KEY": "",
    "MISTRAL_API_KEY": "",
    "DEEPSEEK_API_KEY": "",
    "GHLF_API_KEY": "",
    "HYPERBOLIC_API_KEY": "",
    "NOVITA_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    "CEREBRAS_API_KEY": "",
    "MERCURY_API_KEY": ""
}
```

> ⚠️ **注意**: `keys.json` 在项目根目录，不在 `agent/` 文件夹内。

#### 步骤 5: 配置智能体

为了匹配我们的新架构，我们预设了 `profiles/agent_brain.json` 作为默认入口:

```json
{
    "agent_name": "BrainyBot",
    "ipc_port": 9000,
    "keys_file": "keys.json",
    "enable_prompt_logging": true,

    "agent_loop": {
        "model_name": "qwen-max",
        "api": "qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "params": { "temperature": 0.7, "max_tokens": 8000 }
    },
    "execution": {
        "model_name": "qwen-plus",
        "api": "qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "params": { "temperature": 0.3, "max_tokens": 4000 }
    }
}
```

#### 步骤 6: 配置 Minecraft 服务器

编辑 `settings.js` (Minecraft 连接设置):

```javascript
const settings = {
  "minecraft_version": "auto",        // 自动检测版本
  "host": "127.0.0.1",                // Minecraft 服务器地址
  "port": 55916,                      // Minecraft 局域网开放端口
  "auth": "offline"                   // 离线登入 "offline" 或微软账号登陆 "microsoft"
}
```

### 启动系统

本系统采取**双进程核心分离结构**，包含 Python 大脑模型通信以及 Node.js 的 Mineflayer 环境。启动时**先启动 Python 脑，再挂载 Node.js 游戏身体**以免丢失通信连接。

#### 一键启动
运行位于 `agent` 目录下的 `start.ps1` 脚本，自动激活环境并弹窗启动所需的双端进程：
```powershell
cd agent
.\start.ps1
```

#### 手动分步启动

**a. 启动世界**
在 Minecraft 客户端开启游戏世界并「对局域网开放」，在 `settings.js` 内配置好暴露的局域网端口号。

**b. 启动 Python 主控脑 (终端 1)**
```bash
conda activate braincraft_env
# 默认会根据 main.py 内自动选择 profiles 下的配置
python agent/main.py
```

**c. 启动 Node 连接桥 (终端 2)**
```bash
# 激活桥接器
node agent\bridge\minecraft_bridge.js
```

### 验证启动成功

Python 终端会有类似反馈：
```
AgentLoopLayer initialized
ExecutionLayer initialized
ReflexLayer initialized
[INFO] Agent Loop started
[等待] 组装任务及游戏态...
```
Node 终端则会反馈注入了游戏世界，Bot 将以设定好的名字登录服务器。

## Prompt 日志监控与回看

架构支持全局的透明日志跟踪：只要配置文件中开启了 `"enable_prompt_logging": true`，所有向 LLM 提交的 Prompt 与工具生成的代码结果将会保存在本地。
路径为 `bots/[Agent_Name]/prompts/` 下：
- 分为 `decision_loop`（决策层 Prompt） 以及 `execute_step` （执行层 Prompt 代码）两个大类。
- 日志不仅保存为 JSON，更会自动双向解析成更易读的 `_PROMPT.md` 与 `_RESPONSE.md` 文件供用户直观调试模型能力。

## 提示词模板与变量系统

BrainCraft 支持动态变量替换和模块化组织，提示词中可以使用 `$VARIABLE_NAME` 格式的变量，在渲染时会自动被替换：

### 游戏状态变量
- `$STATS`: 位置、生命值、饥饿度、经验等级等状态。
- `$INVENTORY`: 背包物品详情。
- `$NEARBY_BLOCKS`: 附近 16 格内的方块与地质信息。
- `$NEARBY_ENTITIES`: 附近的实体（玩家、敌对生物、友好生物）。
- `$TIME_OF_DAY`: 游戏时间和天数。

### AI 状态与工具变量
- `$PLAN_FILE`: `plan.md` 文件内容（长期宏观规划）。
- `$TODOLIST_FILE`: `todolist.md` 结构化待办（含 ID 和嵌套）。
- `$DRAFT_FILE`: `draft.md` 文件内容（当前步骤技术思路，同时注入给 Coding LLM）。
- `$PENDING_CHAT`: 玩家发送且尚未处理的新消息。
- `$CHAT_HISTORY`: 近期聊天记录。
- `$TOOL_DESCRIPTIONS`: 目前可供 Agent Loop Layer 调用的所有工具文档和参数说明。
- `$LAST_TOOL_RESULT`: 上一步工具执行的结果（成功/失败、代码输出或报错）。
- `$SOUL`: `soul.md` 文件内加载的 Bot 深度人格设定或系统要求。

### 自定义指令与变量添加
你可以在 `agent/prompts/variable_config.yaml` 注册新变量，并通过底层 `data_providers.py` 为新变量绑定获取游戏数据的方法。

## 项目文件结构一览

```text
braincraft/
├── agent/                        # Python 系统层
│   ├── main.py                   # 骨干入口
│   ├── config.py                 # 分发和注入配置
│   ├── brain/                    # 智能体核心模块
│   │   ├── agent_brain/          # 新版三层脑架构实体
│   │   │   ├── agent_loop_layer.py  # 决策循环
│   │   │   ├── execution_layer.py   # 代码撰写与桥接执行
│   │   │   └── reflex_layer.py      # 生理高频控制
│   │   ├── tools/                # 所有对模型暴露的能力工具
│   │   │   ├── plan_tool.py      # 修改 plan.md
│   │   │   ├── draft_tool.py     # 修改 draft.md
│   │   │   └── todolist_tool.py  # 结构化增删改 todolist.md
│   │   ├── task_manager/         # 文件系统驱动的三层任务管理
│   │   │   ├── plan_manager.py   # plan.md 读写
│   │   │   ├── draft_manager.py  # draft.md 读写
│   │   │   ├── todolist_store.py # todolist.md 结构化解析/渲染/操作引擎
│   │   │   └── chat_log_manager.py
│   ├── bridge/                   # JS-Python IPC 桥接层
│   └── prompts/                  # Prompt 核心体系
│       ├── prompt_manager.py     # 模板渲染
│       ├── prompt_logger.py      # 轨迹全量日志追踪记录
│       ├── variable_config.yaml  # 替换变量动态数据提供器
│       └── agent_loop/
│           ├── system.md         # 规划模型的主系统提示词
│           └── soul.md           # 人格属性动态配置
├── bots/                         # 机器人的持久化与记录资源
│   └── BrainyBot/
│       ├── plan.md               # 长期宏观规划
│       ├── todolist.md           # 结构化短期待办（含 ID 和嵌套）
│       ├── draft.md              # 当前步骤技术思路
│       ├── prompts/              # 思路轨迹监控输出
│       ├── working_memory_raw.json    # 工作记忆原始时间线
│       ├── working_memory_summary.md  # 滚动压缩摘要
│       └── memory_graph/         # 长期记忆图谱
├── profiles/                     # Bot 模型环境配置 (agent_brain.json 等)
├── keys.json                     # API密钥统筹
└── settings.js                   # Node侧的连服务器端口设置
```
---

## 已知问题与手动修复

### Minecraft 1.21.5+ 发送聊天崩溃：`RangeError [ERR_OUT_OF_RANGE] ... Received 130`

**现象**：Bot 在 Minecraft 1.21.5 / 1.21.6 / 1.21.8 服务器上调用 `bot.chat()` 发送消息时，抛出如下错误并崩溃：

```
RangeError [ERR_OUT_OF_RANGE]: Write error for undefined : The value of "value" is out of range.
It must be >= -128 and <= 127. Received 130
    at Object.writer [as i8] (...)
    at Object.packet_chat_message (...)
```

**根本原因**：`minecraft-data` 的协议定义文件（`protocol.json`）中，1.21.5 新增的 `packet_chat_message.checksum` 字段被错误地声明为 `i8`（有符号字节，范围 -128\~127），而实际的校验和计算结果是无符号字节（范围 0\~255）。当校验和值超过 127 时（如 130），`protodef` 调用 `writeInt8` 写入失败。

**手动修复步骤**：

打开以下三个文件（根据你实际安装的 Minecraft 版本，修改对应文件即可）：

```
agent/bridge/node_modules/minecraft-data/minecraft-data/data/pc/1.21.5/protocol.json
agent/bridge/node_modules/minecraft-data/minecraft-data/data/pc/1.21.6/protocol.json
agent/bridge/node_modules/minecraft-data/minecraft-data/data/pc/1.21.8/protocol.json
```

在每个文件中，搜索 `packet_chat_message`（位于 `play.toServer.types` 下），找到其中的 `checksum` 字段，将类型从 `"i8"` 改为 `"u8"`：

**修改前：**
```json
{"name": "checksum", "type": "i8"}
```

**修改后：**
```json
{"name": "checksum", "type": "u8"}
```

> 注意：每次执行 `npm install` 后，`node_modules` 目录会被重置，需要重新手动修复。

---

### mineflayer-pathfinder：门/栅栏门交互时物理 tick 空指针崩溃

**现象**：Bot 在执行包含开门/开栅栏门的寻路路径时，Node.js 进程直接崩溃。日志显示 bot 成功完成门交互后立即崩溃：

```
Code executed: Placed oak_door at (-28, 65, 74).
Successfully placed oak door at the entrance

TypeError: Cannot read properties of undefined (reading 'y')
    at EventEmitter.monitorMovement (mineflayer-pathfinder/index.js:538)
    at EventEmitter.emit (node:events:531:35)
    at tickPhysics (mineflayer/lib/plugins/physics.js:82:11)
```

**根本原因**：`mineflayer-pathfinder` 的 `monitorMovement` 注册在 `physicsTick` 事件上。当寻路路径包含 `useOne` 动作（门/栅栏门）时，`bot.activateBlock()` 异步激活方块，回调中 `placingBlock` 被替换为队列中的下一个路径点。在门交互完成的瞬间，`bot.entity.position.floored()` 可能返回 `undefined`，而 `monitorMovement` 直接访问 `.y` 属性，未做空值检查导致崩溃。同样的问题也存在于 bot 死亡后 `bot.entity` 变为 `null` 的场景。

**手动修复步骤**：

打开 `agent/bridge/node_modules/mineflayer-pathfinder/index.js`，修改三处：

**1. 第 419 行 `monitorMovement` 函数入口** — 添加总守卫：

```js
function monitorMovement () {
  if (!bot.entity || !bot.entity.position) return  // ← 新增
  // Test freemotion
```

**2. 第 538 行** — 放置方块时加空值判断（约第 539 行）：

```js
// 修改前：
if (bot.pathfinder.LOSWhenPlacingBlocks && placingBlock.y === bot.entity.position.floored().y - 1 && placingBlock.dy === 0) {
// 修改后：
if (bot.pathfinder.LOSWhenPlacingBlocks && bot.entity && bot.entity.position && placingBlock.y === bot.entity.position.floored().y - 1 && placingBlock.dy === 0) {
```

**3. 第 544 行** — 跳跃放置时加空值判断：

```js
// 修改前：
canPlace = placingBlock.y + 1 < bot.entity.position.y
// 修改后：
canPlace = bot.entity && bot.entity.position && placingBlock.y + 1 < bot.entity.position.y
```

> 注意：每次执行 `npm install` 后，`node_modules` 目录会被重置，需要重新手动修复。建议使用 `patch-package` 持久化此补丁。

---

**更新日期**: 2026-04-29  
**基于核心**: [MindCraft](https://github.com/mindcraft-bots/mindcraft)
