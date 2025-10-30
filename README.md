# BrainCraft - 三层大脑架构智能体

## 概述

本项目以 [MindCraft](https://github.com/mindcraft-bots/mindcraft) 项目为模板，实现了一个基于**三层大脑架构**的 Minecraft 智能体系统，将人类认知模型映射到 AI 决策层次：

- **高层大脑 (Strategic)**: 人生目标、自我认知、战略规划、闲暇沉思
- **中层大脑 (Tactical)**: 任务执行、代码生成、智能重试、聊天处理
- **底层大脑 (Reflex)**: 战斗反射、自保反应、脱困机制

## 核心创新

### 🎯 双机制响应系统
高层大脑采用**事件驱动 + 定时轮询**双机制：
- **事件驱动**: 中层请求立即唤醒高层（毫秒级响应）
- **定时轮询**: 每15分钟检查空闲状态，进行深度沉思

### 💭 可打断的沉思机制
- 沉思过程可被中层紧急请求即时打断
- 使用 `asyncio.wait()` 实现真正的并发等待
- 自动保存沉思进度，空闲时恢复

### 🧠 类人心智系统
- **情绪模型**: 满足感、挫折感、好奇心
- **认知负荷**: 决策疲劳、过载检测
- **自我认知**: 人格特质、价值观、人生目标

### ⏰ 时间感知系统
- **世界时间**: 从世界创建开始计时（绝对时间）
- **代理年龄**: 从首次出生开始计时（相对时间）
- 支持死亡重生但保持连续的自我认知

## 架构图

```
┌──────────────────────────────────────────────────┐
│              高层大脑 (Strategic)                 │
│  • 人生愿景、长期目标、任务计划                   │
│  • 闲暇沉思（经验整合、自我反思）                 │
│  • 15分钟周期 + 事件驱动（可被中层即时唤醒）      │
│  • LLM: GPT-4 / Claude / Qwen                    │
└────────────────┬─────────────────────────────────┘
                 │ 任务计划 / 修改请求
                 ↓
┌──────────────────────────────────────────────────┐
│              中层大脑 (Tactical)                  │
│  • 任务执行、代码生成、聊天处理                   │
│  • 智能重试、向上请求指导                         │
│  • 1秒周期                                       │
│  • LLM: Qwen / DeepSeek                         │
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

## 核心组件

### 高层大脑组件
- **目标层级系统** (`GoalHierarchy`): 人生愿景 → 长期目标 → 任务计划
- **自我认知系统** (`SelfAwareness`): 身份、人格特质、价值观
- **沉思管理器** (`ContemplationManager`): 5种沉思模式（经验整合、创意连接、自我反思等）
- **心智状态** (`MentalState`): 情绪、认知负荷、注意力

### 中层大脑组件
- **任务执行器**: 读取高层任务计划，拆解为具体步骤
- **代码生成器**: 使用LLM生成 Mineflayer JavaScript 代码
- **智能重试**: 失败3次后向高层请求指导
- **聊天处理器**: 优先处理玩家对话

### 底层大脑组件
- **战斗反射**: 自动攻击、躲避
- **自保反射**: 灭火、浮出水面、逃离岩浆
- **脱困机制**: 检测卡住并自动脱困
- **事件队列**: 实时处理游戏事件

## 环境配置

### Python 环境

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### Node.js 依赖

```bash
# 安装主项目依赖
npm install

# 安装桥接模块依赖
cd python/bridge
npm install
cd ../..
```

### 配置文件

#### 1. 智能体配置

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
        "max_tokens": 2000
      },
      "interval_seconds": 900             // 15分钟 = 900秒
    },
    "mid_level_brain": {
      "model_name": "qwen-plus",          // 中层大脑模型
      "api": "qwen",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "params": {
        "temperature": 0.5,
        "max_tokens": 2000
      },
      "max_task_retries": 3               // 最大重试次数
    }
  }
}
```

**可选模型配置** (在 `alternative_models` 中):
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`
- **Claude**: `claude-3-5-sonnet-20241022`
- **DeepSeek**: `deepseek-chat`
- **本地 Ollama**: `llama3.1:8b`

#### 2. API 密钥配置

编辑 **项目根目录**的 `keys.json`:

```json
{
  "QWEN_API_KEY": "sk-your-qwen-key-here",
  "OPENAI_API_KEY": "sk-your-openai-key-here",
  "ANTHROPIC_API_KEY": "sk-your-claude-key-here",
  "DEEPSEEK_API_KEY": "sk-your-deepseek-key-here"
}
```

> ⚠️ **注意**: `keys.json` 在项目根目录，不在 `python/` 文件夹内。

#### 3. Minecraft 服务器配置

编辑 `settings.js` (Minecraft 连接设置):

```javascript
const settings = {
  "minecraft_version": "auto",        // 自动检测版本，或指定如 "1.20.4"
  "host": "127.0.0.1",                // Minecraft 服务器地址
  "port": 55916,                      // Minecraft 服务器端口
  "auth": "offline",                  // 认证方式: "offline" 或 "microsoft"
  
  // ... 其他配置（原项目使用）
}
```

> ⚠️ **重要**: 
> - `settings.js` 被**原项目和三层大脑项目共用**
> - Minecraft 连接参数 (host/port/version) 在 `settings.js` 中配置
> - 智能体配置 (agent_name/LLM模型) 在 `profiles/three_layer_brain.json` 中配置
> - 修改 `settings.js` 后，两个项目都会受影响

**配置优先级**:
```
三层大脑项目连接逻辑：
  ├─ Minecraft连接 → settings.js (host/port/version)
  ├─ 智能体名称 → three_layer_brain.json (agent_name)
  └─ LLM配置 → three_layer_brain.json (high_level_brain/mid_level_brain)
```

## 运行

### 启动流程

三层大脑系统需要两个进程协同工作：

#### 1. 启动 Python 大脑系统 (第一个终端)

```bash
python python/main.py
```

**输出示例**:
```
======================================================================
  BrainCraft Three-Layer Brain System
======================================================================
Loading configuration...
Agent: BrainCraft
High-level model: qwen-max
Mid-level model: qwen-plus
Initializing IPC server on port 9000...
IPC server started on ports 9000 (REP) and 9001 (PUB)
Initializing brain coordinator...
======================================================================
  Brain systems starting...
======================================================================
High-level brain initialized
Mid-level brain initialized
Low-level brain initialized with reflex system
```

#### 2. 启动 Minecraft 桥接 (第二个终端)

```bash
node python/bridge/minecraft_bridge.js
```

**输出示例**:
```
Loading config from: F:\...\profiles\three_layer_brain.json
Connecting to Minecraft server: localhost:25565
Bot spawned in world
Connected to Python brain via IPC
Sending state updates to brain...
```

### 启动顺序重要说明

⚠️ **必须先启动 Python 大脑，再启动 Minecraft 桥接**

原因：
1. Python 大脑启动 IPC 服务器（端口 9000/9001）
2. Minecraft 桥接连接到 IPC 服务器
3. 如果顺序颠倒，桥接会连接失败

### 验证运行状态

运行成功后，你会看到：

**Python 终端**:
```
📊 State update received from game
🎯 High-level brain: Periodic wake (contemplation check)
⚡ Mid-level brain: Processing task step
```

**JavaScript 终端**:
```
Bot position: Vec3(100, 64, 200)
Executing code from brain...
Code executed successfully
```

## 数据持久化

所有智能体数据保存在 `bots/{agent_name}/` 目录：

```
bots/BrainyBot/                  # agent_name 在 three_layer_brain.json 中配置
├── mind_state.json              # 心智状态（目标、自我认知）
├── memory.json                  # 短期记忆
├── learned_experience.json      # 长期经验（洞察、教训）
└── players.json                 # 玩家关系
```

### mind_state.json 结构

```json
{
  "goal_hierarchy": {
    "life_vision": {
      "vision": "成为一个优秀的建筑师",
      "created_at_days": 5
    },
    "long_term_goals": [
      {
        "id": 1,
        "goal": "建造一座城堡",
        "milestones": ["收集材料", "设计图纸", "建造地基"],
        "current_milestone": 1,
        "status": "active"
      }
    ],
    "task_plan": {
      "current_focus": "挖掘石头",
      "steps": ["找到石矿", "制作镐子", "挖掘100块"]
    }
  },
  "self_awareness": {
    "identity": {
      "name": "BrainCraft",
      "personality_traits": ["好奇", "勤奋"],
      "values": ["效率", "创新"]
    }
  },
  "mental_state": {
    "mood": {
      "satisfaction": 0.7,
      "frustration": 0.2
    }
  }
}
```

## 项目结构

```
BrainCraft/
├── python/                        # Python 大脑系统
│   ├── main.py                    # 入口文件
│   ├── brain/                     # 三层大脑
│   │   ├── brain_coordinator.py   # 大脑协调器
│   │   ├── high_level_brain.py    # 高层大脑
│   │   ├── mid_level_brain.py     # 中层大脑
│   │   ├── low_level_brain.py     # 底层大脑
│   │   ├── goal_hierarchy.py      # 目标层级系统
│   │   ├── self_awareness.py      # 自我认知系统
│   │   ├── mental_state.py        # 心智状态
│   │   └── contemplation/         # 沉思系统
│   │       ├── contemplation_manager.py
│   │       └── config.py
│   ├── models/                    # LLM 模型接口
│   │   ├── llm_wrapper.py         # 统一接口
│   │   ├── gpt.py                 # OpenAI GPT
│   │   ├── claude.py              # Anthropic Claude
│   │   ├── qwen.py                # 阿里通义千问
│   │   └── deepseek.py            # DeepSeek
│   ├── utils/                     # 工具模块
│   │   ├── memory_manager.py      # 记忆管理
│   │   └── ipc_server.py          # IPC 服务器
│   └── bridge/                    # JS-Python 桥接
│       └── minecraft_bridge.js    # Minecraft 桥接
├── bots/                          # 智能体数据
│   └── BrainyBot/                 # 对应 agent_name
│       ├── mind_state.json        # 心智状态
│       ├── memory.json            # 记忆
│       └── learned_experience.json
├── profiles/                      # 配置文件
│   ├── three_layer_brain.json     # **主要配置文件**
│   └── defaults/
├── keys.json                      # **API 密钥文件**（项目根目录）
├── settings.js                    # Minecraft 连接设置
└── docs/                          # 文档
    └── ARCHITECTURE.md            # 详细架构文档
```

## 高层沉思系统

高层大脑在空闲时会进行多种模式的深度思考：

| 沉思模式     | 功能                     | 输出           |
| ------------ | ------------------------ | -------------- |
| **经验整合** | 从多个经验中发现通用模式 | 通用原则和洞察 |
| **创意连接** | 连接看似无关的洞察       | 创新想法和假设 |
| **自我反思** | 思考自身状态和感受       | 人格洞察       |
| **存在思考** | 思考人生意义和目标       | 哲学思考       |
| **关系思考** | 思考与玩家的关系         | 社交理解       |

**沉思条件**:
- 高层处于空闲状态
- 心智负荷不过载
- 满足频率限制（每小时最多10次）

**沉思特性**:
- 可被中层紧急请求即时打断
- 自动保存进度，稍后恢复
- 沉思结果保存到 `mind_state.json`

## 双机制响应详解

### 事件驱动机制
```python
# 中层发送修改请求
await shared_state.update('modification_request', request)
await coordinator.wake_high_brain()  # ⚡ 立即唤醒

# 高层在毫秒内响应
async def think(woken_by_event=True):
    if modification_request:
        await interrupt_contemplation()  # 打断沉思
        await handle_modification_request()
```

### 定时轮询机制
```python
# 每15分钟定时唤醒
await asyncio.wait_for(wake_event.wait(), timeout=900)

# 检查是否空闲并沉思
if is_idle() and needs_contemplation():
    await idle_think()  # 可被打断
```

## 时间感知示例

```python
# 世界时间（绝对时间）
world_day = 42        # 世界创建后第42天
world_time = 846000   # 总游戏 tick 数

# 代理年龄（相对时间）
agent_age_days = 15      # 代理活了15天
agent_age_ticks = 302000 # 代理生存的 tick 数
birthday = 27            # 在世界第27天出生

# 重生后
# - world_day 继续增长
# - agent_age_days 重置为 0
# - 但记忆和人格保留！
```

## 开发指南

### 添加新的沉思模式

1. 在 `contemplation_manager.py` 中添加方法:
```python
async def _my_new_mode(self) -> bool:
    """我的新沉思模式"""
    # 生成 LLM prompt
    # 调用 LLM
    # 保存结果
    return True
```

2. 在 `config.py` 中注册模式:
```python
CONTEMPLATION_CONFIG = {
    'modes': {
        'my_new_mode': {
            'weight': 0.15,
            'description': '我的新沉思模式'
        }
    }
}
```

### 添加新的 LLM 模型

1. 在 `models/` 中创建新文件 `my_model.py`:
```python
class MyModel:
    async def send_request(self, messages, prompt):
        # 实现 API 调用
        return response
```

2. 在 `llm_wrapper.py` 中注册:
```python
MODEL_MAP = {
    'my-model': 'models.my_model.MyModel'
}
```

## 常见问题

### Q: 如何调整高层大脑的唤醒频率？
A: 修改 `profiles/three_layer_brain.json` 中的 `interval_seconds`:
```json
{
  "three_layer_brain_llm": {
    "high_level_brain": {
      "interval_seconds": 900  // 15分钟 = 900秒
    }
  }
}
```
**工作原理**: 
- 配置加载时，`three_layer_brain_llm.high_level_brain` 会被提取到 `config['high_level_brain']`
- `brain_coordinator.py` 从 `config['high_level_brain']['interval_seconds']` 读取此值
- 默认值为 900 秒（15分钟）
- 修改后重启 Python 大脑即可生效

**验证**: 启动时查看日志输出：
```
High-level brain started:
  - Periodic contemplation check: every 900s (15 minutes)
```

### Q: 如何切换 LLM 模型？
A: 修改 `profiles/three_layer_brain.json`，例如切换到 GPT-4:
```json
{
  "three_layer_brain_llm": {
    "high_level_brain": {
      "model_name": "gpt-4o",
      "api": "openai",
      "base_url": "https://api.openai.com/v1"
    }
  }
}
```
然后在 `keys.json` 中添加对应的 API 密钥。

### Q: 如何禁用沉思系统？
A: 暂时无法通过配置禁用，但可以修改代码中的 `needs_contemplation()` 方法返回 `False`。

### Q: 智能体死亡后会丢失记忆吗？
A: 不会。所有记忆、目标和人格都保存在 `bots/{agent_name}/` 目录，重生后自动加载。

### Q: 如何查看智能体的内部状态？
A: 查看 `bots/BrainyBot/mind_state.json` 文件（需要先运行过至少一次）。

### Q: IPC 连接失败怎么办？
A: 
1. 确保先启动 Python 大脑 (`python python/main.py`)
2. 检查端口 9000 和 9001 是否被占用
3. 查看 Python 终端是否显示 "IPC server started"

### Q: 如何连接不同的 Minecraft 服务器？
A: 修改 `settings.js` 中的连接参数：
```javascript
const settings = {
  "host": "your.server.ip",    // 服务器IP地址
  "port": 25565,               // 服务器端口
  "minecraft_version": "1.20.4", // 服务器版本
  "auth": "microsoft"          // 正版验证
}
```
**注意**: `settings.js` 是项目根目录的共享配置，修改会影响原项目和三层大脑项目。

### Q: settings.js 中的 profiles 配置有什么用？
A: `profiles` 数组是**原项目**使用的配置，三层大脑项目**不使用**这个配置。
```javascript
// settings.js 中的这个配置仅用于原项目
"profiles": [
  "./andy.json",  // 原项目的配置文件
]
```
三层大脑项目硬编码使用 `profiles/three_layer_brain.json`，不会读取 `settings.profiles`。

### Q: 配置文件总结 - 什么配置在哪里？
A: 

| 配置项               | 文件位置                 | 作用范围     | 示例                |
| -------------------- | ------------------------ | ------------ | ------------------- |
| **Minecraft 服务器** | `settings.js`            | 两个项目共用 | host, port, version |
| **智能体名称**       | `three_layer_brain.json` | 仅三层大脑   | agent_name          |
| **LLM 模型**         | `three_layer_brain.json` | 仅三层大脑   | model_name, api     |
| **API 密钥**         | `keys.json`              | 两个项目共用 | QWEN_API_KEY        |
| **IPC 端口**         | `three_layer_brain.json` | 仅三层大脑   | ipc_port            |
| **唤醒频率**         | `three_layer_brain.json` | 仅三层大脑   | interval_seconds    |

**文件位置**:
- `settings.js` → 项目根目录
- `three_layer_brain.json` → `profiles/` 文件夹
- `keys.json` → 项目根目录

### Q: 为什么智能体不执行任务？
A: 检查：
1. 高层大脑是否设定了任务计划（查看日志）
2. 中层大脑是否收到任务（查看 "Processing task step"）
3. JavaScript 桥接是否正常执行代码
4. 查看两个终端的错误信息

## 更多文档

- **详细架构文档**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **开发总结**: [DEVELOPMENT_SUMMARY.md](DEVELOPMENT_SUMMARY.md)
- **启动指南**: [STARTUP_GUIDE.md](STARTUP_GUIDE.md)

## 许可证

与原 MindCraft 项目相同的许可证
