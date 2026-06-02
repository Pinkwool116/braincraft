# BrainCraft - Agent Loop 架构 Minecraft 智能体

## 概述

本项目基于 [MindCraft](https://github.com/mindcraft-bots/mindcraft) 构建，在其 Mineflayer 桥接层和游戏交互能力之上，实现了一套以 **Agent Loop** 为核心的主动式智能体系统。

> **代码组织**：本项目的核心代码全部位于 `agent/` 目录下。项目根目录的其他模块（`main.js`、`src/`、`services/`、`tasks/`、`settings.js` 等）是 MindCraft 原有代码，部分仍被复用（如 Minecraft 连接配置）。

### 核心架构

系统采用异步架构与工具调用（Tool Calling）机制，实现自主规划、任务执行和生存反射的解耦：

- **Agent Loop Layer（决策层）**：系统的"思考主循环"，自主读取游戏状态、记忆与周边环境，通过工具调用向下一层派发任务，管理宏观目标。
- **Execution Layer（执行层）**：仅在 Agent Loop 调用 `execute_step` 时生效。通过 Coding LLM 将自然语言步骤描述生成为 JavaScript 代码，经 IPC 发送至 Mineflayer Bridge 执行。
- **Reflex Layer（反射层）**：底层神经反射，与 LLM 无关。以高频（100ms）心跳运行，通过可配置的模式开关处理生存本能动作。
- **Execution Coordinator（执行协调器）**：统一管理不同来源的代码执行优先级。反射层优先级最高（可中断执行层任务），普通自动行为优先级较低。
- **Minecraft Bridge（桥接层）**：Node.js 进程，负责 Mineflayer 游戏交互、IPC 通信和感知事件推送。

## 核心特性

### 三层文本化任务管理

采用 `plan.md` + `todolist.md` + `draft.md` 三层文件架构，按时间尺度与抽象层次完全正交：

| 层 | 文件 | 时间尺度 | 抽象层次 | 工具 |
|---|---|---|---|---|
| 宏观 | `plan.md` | 几天～整局 | 阶段目标、长期方向、背景约束、延后备忘 | `plan` |
| 中观 | `todolist.md` | 几分钟～几小时 | 结构化待办，支持嵌套和 ID 寻址 | `todolist` |
| 微观 | `draft.md` | 当前这一步 | 技术思路、失败尝试、给 Coding LLM 的提示 | `draft` |

- **结构化 todolist**：支持 ID 编号（`t1` → `t1.2` → `t1.2.3`）和缩进双重保证嵌套；每条可精确寻址（`add / remove / set_status / move / overwrite`）；同一时刻只有一条 `in_progress`。
- **内容注入**：三个文件内容由 `build_prompt()` 读取并注入提示词，工具仅负责任修改操作。

### 工具调用机制 (Tool Calling)

所有能力封装为可被模型识别的工具。目前支持：

| 工具 | 用途 |
|---|---|
| `execute_step` | 将自然语言步骤描述交给执行层生成代码并执行 |
| `plan` | 写入/清空长期规划（plan.md） |
| `todolist` | 结构化增删改短期待办（add / remove / update / set_status / move / overwrite） |
| `draft` | 写入/清空当前步骤技术思路（draft.md） |
| `chat` | 与玩家交流 |
| `recall_memory` | 从长期记忆图谱中检索信息 |
| `inspect_surroundings` | 按需扫描周围方块和实体（建造前必用） |
| `scan_terrain` | 请求感知层对周边地形进行 LLM 分析 |
| `interrupt_execution` | 打断当前代码执行，用于遇险或突发指令 |
| `wait` | 主动休眠等待 N 秒 |

### 感知系统 (Perception)

独立于 Agent Loop 的双通道感知管线，持续观察环境并写入工作记忆：

- **EventTicker（高频通道，每 2 秒）**：纯代码逻辑，消费来自 JS PerceptionWorker 的离散事件（实体/声音/方块/天气变化），聚合后写入 `observation` 条目。
- **PerceptionLLM（低频通道，每 300 秒）**：由 Flash LLM 对 JavaScript 端的全量地形扫描快照进行分析，生成自然环境描述写入工作记忆。

两个通道的数据完全隔离——扫描是快照，事件是连续流。

### 记忆系统 (Memory)

多层记忆架构，从短期到长期逐级蒸馏：

- **Working Memory（工作记忆）**：线性缓冲区，记录 reasoning / action / interaction / code_attempt / observation 五种条目。配置项：`consolidate_interval = 25`（每 25 条触发一次 LLM 滚动压缩）。
- **Memory Graph（长期记忆图谱）**：工作记忆经 crystallize 后提取为结构化知识节点和边，存入持久化图谱。
- **Embedding Provider**：基于文本嵌入的语义检索，支持 `recall_memory` 工具按相似度查询。
- **Dream（梦境维护）**：后台协程定期检查图谱，触发社区聚类（GraphCluster）和图谱清理（去重、弱边剪枝、归档），形成概念关联网络。
- **持久化路径**：`bots/{name}/working_memory_raw.json` + `working_memory_summary.md` + 记忆图谱存储。

### Reflex Layer 可配置模式

Reflex Layer 的各类行为通过 `config.json` 中的 `reflex.modes` 开关独立控制：

| 模式 | 说明 |
|---|---|
| `self_preservation` | 生存反射（着火、溺水、低血量逃生） |
| `cowardice` | 怯战模式（遇敌自动逃跑） |
| `hunting` | 自动狩猎敌对生物 |
| `item_collecting` | 自动拾取附近掉落物 |
| `torch_placing` | 自动在暗处放置火把 |
| `elbow_room` | 自动清理卡住的方块 |
| `idle_staring` | 空闲时环顾四周 |

### 灵活的提示词配置 (soul.md)

引入 `soul.md` 作为智能体的内在人格配置：
- **人格塑造**：配置行事风格和最终目标（探险家、生存专家、幽默同伴、专注建筑等）。
- **语言风格**：影响 Bot 全局的思考逻辑和与玩家对话时的情绪反馈。
- **`soul_task/` 子目录**：支持按任务类型加载不同的行为提示词片段。

## 架构图

```text
┌──────────────────────────────────────────────────────────────┐
│                   Agent Loop Layer (主控循环层)                │
│  • 读取游戏状态、记忆、plan / todolist / draft                │
│  • 驱动决策 LLM 选择工具调用                                  │
│  • 统一派发工具（execute_step、chat、todolist、plan 等）       │
└──────┬──────────────────┬──────────────────┬─────────────────┘
       │ 触发             │ 读写 plan/draft/  │ 查询记忆
       │ execute_step     │ todolist 三文件   │ recall_memory
       ↓                  │                   ↓
┌──────────────────┐      │          ┌─────────────────────────┐
│  Execution Layer │      │          │     Memory System        │
│  • Coding LLM    │      │          │  • Working Memory Buffer │
│  • 生成 JS 代码   │      │          │  • Memory Graph         │
│  • IPC 发送执行   │      │          │  • Embedding Provider   │
└────────┬─────────┘      │          │  • Dream 定期维护        │
         │ 代码指令        │          └─────────────────────────┘
         ↓                ↓
┌──────────────────────────────────────────────────────────────┐
│                Execution Coordinator (优先级调度)              │
│  5:low_reflex > 4:unstuck > 3:chat > 2:mid > 1:low_quick     │
└──────────────────────────┬───────────────────────────────────┘
                           │ JS 动作指令
                           ↓
┌──────────────────────────────────────────────────────────────┐
│                Reflex Layer (高频反射层, 100ms)                │
│  • 可配置模式开关（生存/战斗/拾取/火把/脱困等）                 │
│  • 反射事件自动写入工作记忆（observation）                     │
└──────────────────────────────────────────────────────────────┘
         ↑                               ↓
         │ 感知事件（PerceptionWorker）    │ 代码执行
         │                               ↓
┌──────────────────────────────────────────────────────────────┐
│         Perception System (感知系统，独立双通道)                │
│  • EventTicker: 2s 心跳，聚合离散事件 → working memory         │
│  • PerceptionLLM: 300s 间隔，LLM 分析地形扫描快照              │
└──────────────────────────────────────────────────────────────┘
                           ↑            ↓
                    ┌──────┴────────────┴──────┐
                    │   Minecraft Bridge (JS)   │
                    │  • minecraft_bridge.js    │
                    │  • perception_worker.js   │
                    │  • Mineflayer + skills    │
                    └───────────────────────────┘
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
pip install -r requirements.txt
```

#### 步骤 3: 安装 JavaScript 依赖

```powershell
# 安装主项目依赖（MindCraft 原有模块需要）
npm install

# 安装桥接模块依赖
cd agent\bridge
npm install
cd ..\..
```

#### 步骤 4: 配置 API 密钥

在项目根目录下创建 `keys.json`：

```json
{
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "DEEPSEEK_API_KEY": "",
    "QWEN_API_KEY": "",
    "...": ""
}
```

#### 步骤 5: 配置智能体

编辑 `agent/config.json`，核心配置项：

```json
{
    "agent_name": "BrainyBot",
    "ipc_port": 9000,
    "enable_prompt_logging": true,

    "agent_loop": {
        "model": "deepseek_v4_pro",
        "idle_interval_seconds": 30
    },

    "execution": {
        "model": "deepseek_v4_flash_think",
        "timeout": 120
    },

    "reflex": {
        "interval_seconds": 0.1,
        "modes": {
            "self_preservation": false,
            "cowardice": false,
            "hunting": false,
            "item_collecting": true,
            "torch_placing": true,
            "elbow_room": true,
            "idle_staring": true
        }
    },

    "memory": {
        "model": "deepseek_v4_flash_think",
        "consolidate_interval": 25,
        "crystallize_min_consolidations": 5,
        "dream_interval": 10,
        "dream_min_nodes": 30
    },

    "perception": {
        "ticker_interval": 2.0,
        "terrain_interval": 300.0
    },

    "perception_llm": {
        "model": "deepseek_v4_flash"
    },

    "embedding": {
        "api": "qwen",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "text-embedding-v3"
    },

    "model_presets": {
        "deepseek_v4_pro": {
            "model_name": "deepseek-v4-pro",
            "api": "deepseek",
            "base_url": "https://api.deepseek.com",
            "params": { "temperature": 0.7, "max_tokens": 20000 }
        }
    }
}
```

> **model_presets 机制**：`agent_loop`、`execution`、`memory`、`perception_llm` 中的 `model` 字段引用 `model_presets` 中的预设键名，各层可在引用基础上叠加独立参数（如 timeout）。

#### 步骤 6: 配置 Minecraft 连接

编辑 `settings.js`：

```javascript
const settings = {
  "minecraft_version": "auto",
  "host": "127.0.0.1",
  "port": 55916,           // Minecraft 局域网开放端口
  "auth": "offline"
}
```

### 启动系统

系统采用双进程分离结构：Python 大脑（决策+记忆+感知） + Node.js 身体（Mineflayer 游戏交互）。先启动 Python 端，再启动 Node.js 端。

#### 一键启动

```powershell
cd agent
.\start.ps1
```

#### 手动分步启动

**a. 启动世界**：在 Minecraft 客户端中开启游戏世界并「对局域网开放」，将端口配置到 `settings.js`。

**b. 启动 Python 主控脑（终端 1）**

```bash
conda activate braincraft_env
python agent/main.py
```

**c. 启动 Node 连接桥（终端 2）**

```bash
node agent/bridge/minecraft_bridge.js
```

### 验证启动成功

Python 终端输出：
```
Agent Loop model: deepseek-v4-pro (deepseek)
Execution model: deepseek-v4-flash (deepseek)
Memory model: deepseek-v4-flash (deepseek)
IPC server started on ports 9000 (REP) and 9001 (PUB)
MemoryRouter initialized
PerceptionManager initialized
Brain coordinator initialized
```

Node 终端反馈 Bot 注入了游戏世界并登录。

## Prompt 日志监控

配置文件中开启 `"enable_prompt_logging": true` 后，所有向 LLM 提交的 Prompt 与工具生成的代码结果将保存在本地。

路径为 `bots/{AgentName}/prompts/` 下，分为多个子系统：
- `agent_loop/` — 决策层 Prompt 与响应
- `execution_layer/` — 执行层 Code Generation Prompt 与响应
- `memory/` — 记忆系统（consolidation / crystallize / dream）Prompt 与响应
- `perception/` — 感知 LLM 的地形分析 Prompt 与响应

日志保存为 JSON 格式，同时自动双向解析为 `_PROMPT.md` 与 `_RESPONSE.md` 文件供直观调试。

## 提示词模板与变量系统

BrainCraft 支持动态变量替换，提示词中使用 `$VARIABLE_NAME` 格式的变量，渲染时自动替换：

### 游戏状态变量
- `$STATS`：位置、生命值、饥饿度等状态摘要
- `$INVENTORY`：背包物品详情
- `$EQUIPMENT`：装备栏详情
- `$POSITION` / `$HEALTH` / `$FOOD`：单项状态
- `$BIOME`：当前生物群系
- `$TIME_OF_DAY`：游戏时间（tick 和时间标签）
- `$WORLD_DAY`：世界天数
- `$WEATHER`：天气状态
- `$NEARBY_BLOCKS`：附近方块信息
- `$NEARBY_ENTITIES`：附近实体信息
- `$BLOCK_BELOW` / `$BLOCK_LEGS` / `$BLOCK_HEAD` / `$BLOCK_ABOVE`：周边方块

### AI 状态与工具变量
- `$PLAN_FILE`：plan.md 内容（长期宏观规划）
- `$TODOLIST_FILE`：todolist.md 结构化待办（含 ID 和嵌套）
- `$DRAFT_FILE`：draft.md 内容
- `$CHAT_HISTORY`：近期聊天记录
- `$PENDING_CHAT`：玩家发送且尚未处理的新消息
- `$TOOL_DESCRIPTIONS`：可供 Agent Loop 调用的所有工具文档
- `$LAST_TOOL_RESULT`：上一步工具执行的结果
- `$WORKING_MEMORY`：近期经历（工作记忆摘要）
- `$LONG_TERM_MEMORY`：相关长期记忆
- `$SOUL`：soul.md 加载的人格设定
- `$NAME` / `$AGENT_NAME`：智能体名称
- `$AGENT_AGE`：智能体累计游戏时长

### 变量注册

在 `agent/prompts/variable_config.yaml` 中注册新变量，并在 `agent/prompts/data_providers.py` 中绑定获取数据的函数。

## 项目文件结构

```text
braincraft/
├── agent/                              # 本项目核心代码
│   ├── main.py                         # Python 入口
│   ├── config.json                     # 智能体配置（模型、反射、记忆、感知）
│   ├── start.ps1                       # 一键启动脚本
│   ├── requirements.txt                # Python 依赖
│   │
│   ├── brain/                          # 智能体大脑模块
│   │   ├── agent_brain/                # 核心层
│   │   │   ├── brain_coordinator.py    # 总协调器（初始化各层、注册工具、IPC 处理）
│   │   │   ├── agent_loop_layer.py     # Agent Loop 决策循环
│   │   │   ├── execution_layer.py      # 代码生成与 IPC 执行
│   │   │   ├── reflex_layer.py         # 高频反射层
│   │   │   └── execution_coordinator.py # 优先级执行协调
│   │   ├── perception/                 # 感知系统
│   │   │   ├── perception_manager.py   # 双通道感知协调器
│   │   │   ├── perception_buffer.py    # 事件缓冲区
│   │   │   ├── event_ticker.py         # 高频事件聚合器
│   │   │   └── perception_llm.py       # LLM 地形分析
│   │   ├── tools/                      # 工具系统
│   │   │   ├── tool_registry.py        # 工具注册中心
│   │   │   ├── execute_step_tool.py    # 执行步骤
│   │   │   ├── chat_tool.py            # 聊天
│   │   │   ├── recall_memory_tool.py   # 记忆检索
│   │   │   ├── interrupt_tool.py       # 中断执行
│   │   │   ├── wait_tool.py            # 休眠等待
│   │   │   ├── plan_tool.py            # 修改 plan.md
│   │   │   ├── draft_tool.py           # 修改 draft.md
│   │   │   ├── todolist_tool.py        # 结构化操作 todolist.md
│   │   │   ├── inspect_surroundings_tool.py # 扫描周围环境
│   │   │   └── scan_terrain_tool.py    # 请求地形分析
│   │   └── task_manager/               # 文件驱动任务管理
│   │       ├── plan_manager.py         # plan.md 读写
│   │       ├── todolist_store.py       # 结构化解析/渲染/操作引擎
│   │       ├── draft_manager.py        # draft.md 读写
│   │       └── chat_log_manager.py     # 聊天记录管理
│   │
│   ├── data_manager/                   # 数据管理
│   │   ├── chat_manager.py             # 聊天管理器（MindCraft 遗留）
│   │   ├── mind_state_manager.py       # 状态管理器
│   │   └── memory_graph/               # 记忆图谱子系统
│   │       ├── memory_router.py        # 记忆统一接口
│   │       ├── working_memory.py       # 工作记忆缓冲区
│   │       ├── graph_engine.py         # 图谱 CRUD 引擎
│   │       ├── graph_store.py          # 图谱持久化
│   │       ├── graph_types.py          # 数据类型定义
│   │       ├── graph_retriever.py      # 图谱检索
│   │       ├── graph_dream.py          # Dream 梦境维护
│   │       ├── graph_cluster.py        # 社区聚类
│   │       ├── embedding_provider.py   # 嵌入向量提供器
│   │       └── viz/                    # 图谱可视化
│   │
│   ├── prompts/                        # 提示词体系
│   │   ├── prompt_manager.py           # 模板渲染引擎
│   │   ├── prompt_logger.py            # 轨迹全量日志记录
│   │   ├── variable_config.yaml        # 变量到数据提供器的映射
│   │   ├── data_providers.py           # 动态数据提供器函数
│   │   ├── api_docs_generator.py       # Coding LLM API 文档生成
│   │   ├── agent_loop/                 # Agent Loop 提示词
│   │   │   ├── system.md               # 主系统提示词
│   │   │   ├── soul.md                 # 人格设定
│   │   │   ├── interruption.md         # 中断提示词
│   │   │   └── soul_task/              # 按任务类型的行为片段
│   │   ├── execution_layer/            # 执行层提示词
│   │   │   └── coding.md               # Coding LLM 系统提示词
│   │   ├── memory/                     # 记忆系统提示词
│   │   │   ├── working_memory_consolidation.md
│   │   │   ├── memory_graph_extraction.md
│   │   │   ├── memory_dream.md
│   │   │   └── community_clustering.md
│   │   └── perception/                 # 感知系统提示词
│   │       ├── terrain_analysis.md
│   │       └── inspect_surroundings_summary.md
│   │
│   ├── llm/                            # LLM 封装
│   │   └── llm_wrapper.py              # 多 API 统一接口
│   │
│   ├── bridge/                         # JS-Python IPC 桥接
│   │   ├── ipc_server.py               # Python 端 IPC 服务器（ZeroMQ）
│   │   ├── minecraft_bridge.js         # Node.js 端桥接主模块
│   │   ├── perception_worker.js        # JS 端感知事件采集 Worker
│   │   ├── package.json                # 桥接层 JS 依赖
│   │   └── node_modules/               # JS 依赖（mineflayer 系列）
│   │
│   ├── minecraft/                      # Minecraft 技能
│   │   └── skill_library.py            # Mineflayer 技能接口封装
│   │
│   ├── utils/                          # 工具
│   │   ├── game_state_formatter.py     # 游戏状态格式化
│   │   ├── json_parser.py              # LLM JSON 响应解析
│   │   └── logger.py                   # 日志配置
│   │
│   └── neurosymbolic/                  # 预留：神经符号模块（未激活）
│
├── bots/                               # 智能体持久化数据
│   └── {AgentName}/
│       ├── plan.md                     # 长期宏观规划
│       ├── todolist.md                 # 结构化短期待办
│       ├── draft.md                    # 当前步骤技术思路
│       ├── prompts/                    # Prompt 日志输出
│       ├── playtime.json               # 游戏时长记录
│       ├── working_memory_raw.json     # 工作记忆原始时间线
│       ├── working_memory_summary.md   # 滚动压缩摘要
│       └── memory_graph/               # 长期记忆图谱持久化
│
├── profiles/                           # MindCraft 遗留的模型配置文件
├── keys.json                           # API 密钥
├── settings.js                         # Minecraft 服务器连接配置
├── main.js                             # MindCraft 原始入口（本系统不使用）
├── src/                                # MindCraft 原有模块
├── services/                           # MindCraft 原有服务
└── tasks/                              # MindCraft 原有任务模块
```

---

**更新日期**: 2026-06-02
**基于核心**: [MindCraft](https://github.com/mindcraft-bots/mindcraft)
