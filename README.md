# BrainCraft - Agent Loop 架构智能体

## 概述

本项目基于 [MindCraft](https://github.com/mindcraft-bots/mindcraft) 项目，实现了一个以 **Agent Loop** 为核心的主动式 Minecraft 智能体系统。系统采用异步架构与工具调用（Tool Calling）机制，实现了自主规划、任务执行和生存反射的高度解耦。

### 核心架构

- **Agent Loop Layer (决策层)**: 系统的"思考主循环"，自主读取游戏状态、记忆与周边环境，并通过工具调用（Tool Calling）向下一层派发任务，管理整个宏观目标。
- **Execution Layer (执行层)**: 充当高级代码生成器工具，仅在被决策层调用时生效。通过专门的 Coding LLM 生成 JavaScript 代码来驱动 Minecraft 物理动作，并带有智能重试机制。
- **Reflex Layer (反射层)**: 底层神经反射，与 LLM 无关。以高频（100ms）心跳运行，自动处理生存相关的本能动作（如吃东西、燃烧时跳水、跌落保护、被攻击反击等）。

## 核心特性

### 🎯 文本化任务管理 (Task.md)
采用基于 `task.md` 的纯文件与文本管理策略：
- **全局视野**: Agent Loop 在每次迭代时都会读取 `task.md` 来了解当前目标和进度。
- **自由修改**: 拥有完全访问权，可根据游戏形势随时追加计划、调整优先级、跳过不可行步骤或增加补充信息（使用 `update_task` 工具）。
- **无缝中断**: 利用 `interrupt` 工具可在紧急情况下切断当前正在执行的长耗时底层代码。

### 🛠️ 工具调用机制 (Tool Calling)
将所有能力封装为可被模型识别的工具。目前支持：
- `execute_step`: 生成与执行 JavaScript 脚本行动。
- `update_task`: 更新目标清单与笔记文件。
- `chat`: 与玩家交流。
- `recall_memory`: 从复杂的记忆图谱中检索信息。
- `interrupt`: 打断当前行动，用于遇险或突发指令。

### 🧠 主动探索机制（Idle-Thinking）
- 没有任务就主动探索。
- 当系统处于无玩家任务的完全空闲 (Idle) 时，Agent 不会死板地挂起休息，而是依然拥有决策权，可以主动决定是散步探索、收集物资或主动找玩家交互。

### 🌟 灵活的提示词配置系统 (soul.md)
引入 `soul.md` 作为机器人的内在人格配置：
- **人格塑造**: 允许用户配置专属的行事风格和最终目标（如探险家、生存专家、幽默的同伴、专注建筑等）。
- **语言风格**: 影响 Bot 全局的思考逻辑和与玩家对话时的情绪反馈。

## 架构图

```text
┌─────────────────────────────────────────────────────────┐
│              Agent Loop Layer (主控循环层)               │
│  • 读取世界态、内存、task.md 等                         │
│  • 驱动主决策 LLM 行动                                  │
│  • 统一派发工具调用（Chat、Execute、Memory等）           │
└──────────────┬───────────────────────────┬──────────────┘
               │ 触发 execute_step          │ 读写 task.md
               ↓                           │
┌──────────────────────────────────────┐   │
│           Execution Layer            │   │
│  • 根据目标请求 Coding LLM 生成代码    │   │
│  • 将 JS 送入 IPC 执行               │   │
│  • 发生失败则局部请求重试             │   │
└──────────────┬───────────────────────┘   │
               │ JS 动作指令               │
               ↓                           ↓
┌─────────────────────────────────────────────────────────┐
│               Reflex Layer (高频反射层)                  │
│  • 生命垂危、燃烧、窒息的本能抢救                        │
│  • 脱困(Stuck) 防护                                     │
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
- `$TASK_FILE`: `task.md` 文件的实时文本内容。
- `$PENDING_CHAT`: 玩家发送且尚未处理的新消息。
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
│   │   └── task_manager/         # 文件系统驱动的任务追踪 (task.md)
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
│       ├── task.md               # 机器人当前的行动计划提纲
│       ├── prompts/              # 思路轨迹监控输出
│       └── memory_*.json         # 记忆与聊天存档记录
├── profiles/                     # Bot 模型环境配置 (agent_brain.json 等)
├── keys.json                     # API密钥统筹
└── settings.js                   # Node侧的连服务器端口设置
```
---

**更新日期**: 2026-03-26  
**基于核心**: [MindCraft](https://github.com/mindcraft-bots/mindcraft)
