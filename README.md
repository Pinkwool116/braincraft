# BrainCraft - 三层大脑架构智能体

## 概述

本项目基于 [MindCraft](https://github.com/mindcraft-bots/mindcraft) 项目，实现了一个**三层大脑架构 + 任务栈管理**的 Minecraft 智能体系统。系统采用异步架构，实现了战略规划、战术执行和反射响应的分层决策。

### 核心架构

- **高层大脑 (High-Level Brain)**: 战略规划、任务栈管理、玩家指令处理
- **中层大脑 (Mid-Level Brain)**: 任务执行、JavaScript 代码生成、智能重试
- **底层大脑 (Low-Level Brain)**: 战斗反射、自保反应、事件处理

## 核心特性

### 🎯 任务栈 (Task Stack) 管理系统
采用 **LIFO (后进先出)** 栈结构管理所有任务：
- **动态优先级**: 玩家请求或紧急子任务自动获得最高优先级
- **优雅中断**: 支持任务暂停-执行-恢复的非线性流程
- **智能恢复**: 子任务完成后自动恢复父任务
- **持久化**: 任务栈状态持久化，重启后无缝继续

### 🧠 智能求助机制
中层执行遇到困难时可向高层请求帮助：
- **修改步骤**: 高层优化当前任务的执行步骤
- **添加子任务**: 自动创建前置子任务解决瓶颈
- **替换任务**: 完全重新规划更合理的方案
- **放弃任务**: 智能判断不可行的目标并及时止损

### 👥 玩家交互系统
- **任务请求识别**: 自动从聊天中解析玩家的任务请求
- **关系管理**: 基于互动历史维护玩家关系
- **优先级权衡**: 根据任务重要性和玩家关系决定是否接受请求
- **智能反馈**: 任务完成或失败时主动向玩家汇报

### ⚡ 异步并发架构
- **三层独立运行**: 高层(10分钟)、中层(1秒)、底层(0.1秒)异步运行
- **事件驱动唤醒**: 中层请求可立即唤醒高层大脑响应
- **非阻塞执行**: 所有 LLM 调用和游戏操作完全异步

### 🌟 沉思系统（规划中）
高层大脑将具备深度沉思能力，在空闲时进行自我成长：
- **经验总结**: 从成功与失败中提炼通用原则和洞察
- **社交反思**: 思考与玩家的互动，理解关系动态
- **人生目标**: 反思长期愿景，调整价值观和优先级
- **创造性思考**: 跨领域连接知识，产生创新想法
- **人格塑造**: 反思个性特质，发展独特的行为模式
- **异步执行**: 沉思在后台进行，不影响紧急响应和任务执行

这将使智能体适应 AI Town 等需要复杂社交和长期规划的环境。

## 架构图

```
┌──────────────────────────────────────────────────┐
│              高层大脑 (Strategic)                 │
│  • 战略目标设定、任务栈管理                       │
│  • 玩家指令处理、智能求助响应                     │
│  • 深度沉思（经验总结、社交反思、人生规划）[规划中]│
│  • 10分钟周期 + 事件驱动（可被中层即时唤醒）      │
│  • LLM: Qwen-Max / GPT-4 / Claude                │
└────────────────┬─────────────────────────────────┘
                 │ 任务栈 / 修改请求响应
                 ↓
┌──────────────────────────────────────────────────┐
│              中层大脑 (Tactical)                  │
│  • 执行栈顶任务、生成 JavaScript 代码             │
│  • 聊天处理、智能重试、请求高层指导               │
│  • 1秒周期                                       │
│  • LLM: Qwen-Plus / GPT-4o-mini                 │
└────────────────┬─────────────────────────────────┘
                 │ 动作指令
                 ↓
┌──────────────────────────────────────────────────┐
│              底层大脑 (Reflex)                    │
│  • 战斗、自保、脱困                               │
│  • 0.1秒周期 (100ms)                            │
│  • 无需LLM的即时反应                             │
└──────────────────────────────────────────────────┘
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

编辑 **项目根目录**的 `keys.json`:

```json
{
  "QWEN_API_KEY": "sk-your-qwen-key-here",
  "OPENAI_API_KEY": "sk-your-openai-key-here",
  "ANTHROPIC_API_KEY": "sk-your-claude-key-here",
  "DEEPSEEK_API_KEY": "sk-your-deepseek-key-here"
}
```

> ⚠️ **注意**: `keys.json` 在项目根目录，不在 `agent/` 文件夹内。

#### 步骤 5: 配置智能体

编辑 `profiles/three_layer_brain.json`:

```json
{
  "agent_name": "BrainyBot",
  "ipc_port": 9000,
  "keys_file": "keys.json",
  "three_layer_brain_llm": {
    "high_level_brain": {
      "model_name": "qwen-max",           // 高层大脑模型
      "api": "qwen",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "params": {
        "temperature": 0.7,
        "max_tokens": 8000
      },
      "interval_seconds": 600             // 10分钟 = 600秒
    },
    "mid_level_brain": {
      "model_name": "qwen-plus",          // 中层大脑模型
      "api": "qwen",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "params": {
        "temperature": 0.5,
        "max_tokens": 4000
      },
      "max_task_retries": 3               // 最大重试次数
    }
  }
}
```

**可选模型配置**:
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`
- **Claude**: `claude-3-5-sonnet-20241022`
- **DeepSeek**: `deepseek-chat`
- **本地 Ollama**: `llama3.1:8b`

#### 步骤 6: 配置 Minecraft 服务器

编辑 `settings.js` (Minecraft 连接设置):

```javascript
const settings = {
  "minecraft_version": "auto",        // 自动检测版本，或指定如 "1.20.4"
  "host": "127.0.0.1",                // Minecraft 服务器地址
  "port": 55916,                      // Minecraft 服务器端口
  "auth": "offline"                   // 认证方式: "offline" 或 "microsoft"
}
```

> ⚠️ **重要**: 
> - `settings.js` 被**原项目和三层大脑项目共用**
> - Minecraft 连接参数 (host/port/version) 在 `settings.js` 中配置
> - 智能体配置 (agent_name/LLM模型) 在 `profiles/three_layer_brain.json` 中配置
> - 修改 `settings.js` 后，两个项目都会受影响

### 启动系统

### 启动系统

三层大脑系统需要两个进程协同工作：

#### 步骤 7: 启动 Minecraft 世界

```powershell
# 1. 打开 Minecraft Java Edition
# 2. 创建/加载世界
# 3. 按 ESC → 对局域网开放
# 4. 记下端口号（如 55916）
# 5. 在 settings.js 中设置正确的端口
```

#### 步骤 8: 启动 Python 大脑（第一个终端）

```bash
# 激活虚拟环境
conda activate braincraft  # 或 venv\Scripts\activate

# 启动 Python 大脑
python agent\main.py
```

**预期输出**:
```
======================================================================
  MindCraft Three-Layer Brain System
======================================================================
Loading configuration...
Agent: BrainyBot
High-level model: qwen-max
Mid-level model: qwen-plus
Initializing IPC server on port 9000...
IPC server started on ports 9000 (REP) and 9001 (PUB)
High-level brain initialized with refactored task stack management.
Mid-level brain initialized
Low-level brain initialized with reflex system
======================================================================
  Brain systems starting...
======================================================================
High-level brain started (interval: 600s)
Mid-level brain started (interval: 1s)
Low-level brain started (interval: 0.1s)
```

#### 步骤 9: 启动 Minecraft 桥接（第二个终端）

```bash
node agent\bridge\minecraft_bridge.js
```

**预期输出**:
```
Loading config from: F:\...\profiles\three_layer_brain.json
======================================================================
  Three-Layer Brain Bridge - Minecraft Connection
======================================================================
Connecting to Python brain on ports 9000-9001...
IPC connection established
Listening for commands from Python...
Initializing Mineflayer bot...
Connecting to 127.0.0.1:55916 as BrainyBot
Bot spawned in world at position Vec3(100, 64, 200)
```

### 启动顺序重要说明

⚠️ **必须先启动 Python 大脑，再启动 Minecraft 桥接**

**原因**:
1. Python 大脑启动 IPC 服务器（端口 9000/9001）
2. Minecraft 桥接连接到 IPC 服务器
3. 如果顺序颠倒，桥接会报错：`Error: Cannot connect to Python brain`

### 验证启动成功

**Python 终端应该显示**:
```
📊 State update received from game
Position: Vec3(100, 64, 200)
Health: 20/20, Food: 20/20
Biome: plains

🎯 High-level brain: Periodic wake (contemplation check)
Task stack empty - generating strategic goal

⚡ Mid-level brain: Processing task step 1/5
Executing: 寻找附近的树木
```

**JavaScript 终端应该显示**:
```
Bot position: Vec3(100, 64, 200)
Received command from Python: execute_code
Executing code from brain...
Code executed successfully
```

**在 Minecraft 中**:
你应该看到名为 `BrainyBot` 的玩家加入游戏，并开始执行任务。

### 停止系统

#### 正常停止

1. 在 JavaScript 终端按 `Ctrl+C`
2. 在 Python 终端按 `Ctrl+C`

系统会自动保存任务栈和心智状态到 `bots/BrainyBot/mind_state.json`。

#### 强制停止

如果系统无响应：

**Windows**:
```powershell
taskkill /F /IM python.exe
taskkill /F /IM node.exe
```

**Linux/Mac**:
```bash
pkill -9 python
pkill -9 node
```

### 重启后恢复

系统重启后会自动从 `bots/BrainyBot/mind_state.json` 恢复：

- ✅ 任务栈状态
- ✅ 战略目标
- ✅ 目标层级
- ✅ 自我认知
- ✅ 学习经验
- ✅ 玩家关系

重启后智能体会**无缝继续执行之前的任务**。

### 查看运行状态

#### 实时日志

观察 Python 终端和 JavaScript 终端的输出。

#### 持久化文件

```powershell
# 查看任务栈
cat bots\BrainyBot\mind_state.json

# 查看学习经验
cat bots\BrainyBot\learned_experience.json

# 查看玩家关系
cat bots\BrainyBot\players.json

# 查看聊天历史
cat bots\BrainyBot\chat_history.json
```

## 日常使用工作流程

### 1. 每次使用前

```powershell
# 启动 Minecraft 并对局域网开放
# 检查 settings.js 中的端口号是否正确
```

### 2. 启动智能体

```powershell
# 终端 1 - Python 大脑
conda activate braincraft
python agent\main.py

# 终端 2 - Minecraft 桥接
node agent\bridge\minecraft_bridge.js
```

### 3. 使用完毕

按 `Ctrl+C` 依次停止两个进程。

## 切换 LLM 模型

### 使用 OpenAI GPT-4

编辑 `profiles/three_layer_brain.json`:

```json
{
  "three_layer_brain_llm": {
    "high_level_brain": {
      "model_name": "gpt-4o",
      "api": "openai",
      "base_url": "https://api.openai.com/v1"
    },
    "mid_level_brain": {
      "model_name": "gpt-4o-mini",
      "api": "openai"
    }
  }
}
```

确保 `keys.json` 中有 `OPENAI_API_KEY`。

### 使用 Claude

```json
{
  "three_layer_brain_llm": {
    "high_level_brain": {
      "model_name": "claude-3-5-sonnet-20241022",
      "api": "anthropic"
    }
  }
}
```

确保 `keys.json` 中有 `ANTHROPIC_API_KEY`。

### 使用本地 Ollama

```json
{
  "three_layer_brain_llm": {
    "high_level_brain": {
      "model_name": "llama3.1:8b",
      "api": "ollama",
      "base_url": "http://localhost:11434"
    }
  }
}
```

确保 Ollama 已启动并下载了模型。

## 任务栈工作原理

### 任务栈结构

任务栈是一个 LIFO（后进先出）数据结构，存储所有 `task_plan` 对象：

```python
task_stack = [
    {
        "goal": "探索并收集资源",  # 基础任务
        "steps": [...],
        "status": "paused",
        "source": "internal"
    },
    {
        "goal": "为玩家建造庇护所",  # 玩家任务（中断了基础任务）
        "steps": [...],
        "status": "paused",
        "source": "player",
        "player_name": "Steve"
    },
    {
        "goal": "收集 20 个木头",  # 当前执行的子任务
        "steps": [...],
        "status": "active",       # 栈顶任务总是 active
        "source": "internal"
    }
]
```

### 任务执行流程

1. **中层执行**: 中层大脑只执行栈顶任务（`task_stack[-1]`）
2. **任务完成**: 栈顶任务完成后，自动弹出（pop）
3. **恢复父任务**: 弹出后，新的栈顶任务状态从 `paused` 变为 `active`
4. **继续执行**: 中层大脑继续执行被恢复的任务

### 玩家请求处理

当玩家在聊天中发送任务请求（如 "帮我建个房子"）：

1. **中层识别**: 中层大脑使用 LLM 判断是否为任务请求
2. **高层决策**: 
   - 评估玩家关系（从 `players.json` 读取）
   - 权衡当前任务的重要性
   - 决定接受或拒绝
3. **任务压栈**: 如果接受，创建新任务并压入栈顶，当前任务变为 `paused`
4. **执行**: 中层立即开始执行玩家任务

### 智能求助（修改请求）

当中层执行失败多次后：

1. **发送请求**: 中层向高层发送 `modification_request`
2. **立即唤醒**: 高层大脑被事件驱动机制唤醒
3. **LLM 分析**: 高层使用 LLM 分析失败原因和上下文
4. **决策响应**:
   - **REVISE_STEPS**: 修改当前任务的步骤
   - **ADD_SUB_TASK**: 创建子任务并压栈
   - **REPLACE_TASK**: 弹出当前任务，压入新任务
   - **DISCARD_TASK**: 弹出并放弃当前任务
   - **REJECT_REQUEST**: 拒绝修改，提供指导建议

## 数据持久化

所有智能体数据保存在 `bots/{agent_name}/` 目录：

```
bots/BrainyBot/                  # agent_name 在 three_layer_brain.json 中配置
├── mind_state.json              # 心智状态（任务栈、战略目标）
├── memory.json                  # 短期记忆
├── learned_experience.json      # 长期经验（洞察、教训）
├── players.json                 # 玩家关系
└── chat_history.json            # 聊天历史
```

### mind_state.json 结构

```json
{
  "task_stack": [
    {
      "goal": "探索并收集资源",
      "steps": [
        {"id": 1, "description": "寻找树木", "status": "completed"},
        {"id": 2, "description": "收集木头", "status": "in_progress"}
      ],
      "current_step_index": 1,
      "status": "active",
      "source": "internal"
    }
  ],
  "strategic_goal": "建立一个安全的基地",
  "goal_hierarchy": {
    "life_vision": {...},
    "long_term_goals": [...]
  },
  "self_awareness": {...},
  "mental_state": {...}
}
```

## 项目结构

```
braincraft/
├── agent/                        # 智能体系统
│   ├── main.py                    # 入口文件
│   ├── config.py                  # 配置管理
│   ├── brain/                     # 三层大脑
│   │   ├── three_layer_brain/     # 三层大脑核心
│   │   │   ├── brain_coordinator.py   # 大脑协调器
│   │   │   ├── high_level_brain.py    # 高层大脑
│   │   │   ├── mid_level_brain.py     # 中层大脑
│   │   │   ├── low_level_brain.py     # 底层大脑
│   │   │   └── execution_coordinator.py # 执行协调器
│   │   ├── task_stack/            # 任务栈管理
│   │   │   ├── task_stack_manager.py  # 任务栈核心
│   │   │   ├── task_planner.py        # 任务规划器
│   │   │   ├── task_handler.py        # 任务处理器
│   │   │   ├── task_persistence.py    # 持久化
│   │   │   └── TASK_STACK_DESIGN.md   # 设计文档
│   │   ├── mind_system/           # 心智系统
│   │   │   ├── goal_hierarchy.py      # 目标层级
│   │   │   ├── self_awareness.py      # 自我认知
│   │   │   └── mental_state.py        # 心智状态
│   │   └── contemplation/         # 沉思系统（规划中）
│   ├── models/                    # LLM 模型接口
│   │   ├── llm_wrapper.py         # 统一接口
│   │   ├── gpt.py                 # OpenAI GPT
│   │   ├── claude.py              # Anthropic Claude
│   │   ├── qwen.py                # 阿里通义千问
│   │   ├── deepseek.py            # DeepSeek
│   │   └── skill_library.py       # Minecraft 技能库
│   ├── utils/                     # 工具模块
│   │   ├── memory_manager.py      # 记忆管理
│   │   ├── mind_state_manager.py  # 心智状态管理
│   │   ├── chat_manager.py        # 聊天管理
│   │   ├── game_state_formatter.py # 游戏状态格式化
│   │   ├── prompt_loader.py       # 提示词加载
│   │   └── logger.py              # 日志系统
│   ├── communication/             # 通信模块
│   │   └── ipc_server.py          # IPC 服务器
│   ├── bridge/                    # JS-Python 桥接
│   │   ├── minecraft_bridge.js    # Minecraft 桥接
│   │   └── package.json           # 桥接依赖
│   └── prompts/                   # LLM 提示词
│       ├── high_level_planning_prompt.txt  # 高层规划提示
│       ├── mid_level_coding_prompt.txt     # 中层代码生成提示
│       ├── chat_prompt.txt                 # 聊天提示
│       └── experience_summary_prompt.txt   # 经验总结提示
├── bots/                          # 智能体数据（运行时生成）
│   └── BrainyBot/                 # 对应 agent_name
│       ├── mind_state.json        # 心智状态
│       ├── memory.json            # 记忆
│       ├── learned_experience.json # 学习经验
│       ├── players.json           # 玩家关系
│       └── chat_history.json      # 聊天历史
├── profiles/                      # 配置文件
│   ├── three_layer_brain.json     # 主要配置文件
│   └── defaults/
├── src/                           # 原 MindCraft 项目代码
│   ├── agent/library/             # 技能库（JavaScript）
│   │   ├── skills.js              # Minecraft 技能函数
│   │   └── world.js               # 世界查询函数
│   └── utils/                     # 工具函数
├── keys.json                      # ⭐ API 密钥文件（项目根目录）
├── settings.js                    # ⭐ Minecraft 连接设置
├── requirements.txt               # Python 依赖
└── README.md                      # 本文件
```

**注意**: `agent/` 是新的智能体系统目录，不是 `python/`。

## 常见问题排查

### Q1: IPC 连接失败

**错误信息**:
```
Error: Cannot connect to Python brain on port 9000
```

**解决方法**:
1. 确保 Python 大脑已经启动
2. 检查日志中是否显示 `IPC server started on ports 9000`
3. 检查端口 9000 和 9001 是否被其他程序占用
   ```powershell
   netstat -ano | findstr "9000"
   ```

### Q2: Bot 无法加入 Minecraft

**错误信息**:
```
Error: Connection refused to 127.0.0.1:25565
```

**解决方法**:
1. 确保 Minecraft 世界已经开启
2. 确保已经"对局域网开放"
3. 检查 `settings.js` 中的端口号是否正确
4. 如果使用正版验证，确保 `auth: "microsoft"` 且已登录

### Q3: LLM API 调用失败

**错误信息**:
```
Error: Invalid API key for Qwen
```

**解决方法**:
1. 检查 `keys.json` 中的 API 密钥是否正确
2. 确保 API 密钥有足够的额度
3. 检查网络连接

### Q4: Bot 不执行任务

**排查步骤**:
1. 查看 Python 终端，确认任务栈不为空:
   ```
   Task stack top: 探索并收集资源 (source=internal) - Step 1/5
   ```

2. 查看 JavaScript 终端，确认代码执行:
   ```
   Executing code from brain...
   ```

3. 检查 `bots/BrainyBot/mind_state.json`，查看任务栈状态

4. 查看日志中的错误信息

### Q5: 虚拟环境未激活

**症状**: 运行 `python agent\main.py` 时报错 `ModuleNotFoundError`

**解决方法**:
```powershell
# 确保激活虚拟环境
conda activate braincraft  # 或 venv\Scripts\activate

# 验证
python -c "import zmq; print('ZMQ installed')"
```

### Q6: 如何调整高层大脑的唤醒频率？
修改 `profiles/three_layer_brain.json` 中的 `interval_seconds`:
```json
{
  "three_layer_brain_llm": {
    "high_level_brain": {
      "interval_seconds": 600  // 10分钟 = 600秒
    }
  }
}
```

### Q7: 智能体死亡后会丢失记忆吗？
不会。所有记忆、目标和任务栈都保存在 `bots/{agent_name}/` 目录，重生后自动加载。

### Q8: 如何查看智能体的内部状态？
查看 `bots/BrainyBot/mind_state.json` 文件（需要先运行过至少一次）。

### Q9: 如何连接不同的 Minecraft 服务器？
修改 `settings.js` 中的连接参数：
```javascript
const settings = {
  "host": "your.server.ip",    // 服务器IP地址
  "port": 25565,               // 服务器端口
  "minecraft_version": "1.20.4", // 服务器版本
  "auth": "microsoft"          // 正版验证
}
```

### Q10: 任务栈如何查看？
查看 `bots/BrainyBot/mind_state.json` 中的 `task_stack` 字段，或观察 Python 终端的日志输出。

## 更多文档

- **详细架构文档**: [ARCHITECTURE.md](ARCHITECTURE.md)
  - 包含完整的沉思系统设计愿景 🌟
- **任务流程文档**: [TASK_FLOW.md](TASK_FLOW.md)
- **任务栈设计**: [agent/brain/task_stack/TASK_STACK_DESIGN.md](agent/brain/task_stack/TASK_STACK_DESIGN.md)

---

**项目版本**: 2.0  
**更新日期**: 2025-11-03  
**维护者**: BrainCraft Development Team  
**基于**: [MindCraft](https://github.com/mindcraft-bots/mindcraft)

## 许可证

与原 MindCraft 项目相同的许可证
