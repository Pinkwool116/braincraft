# 三层大脑系统 - 启动指南

## 快速开始

### 前置要求

- **Python**: 3.8 或更高版本 （建议3.13.5）
- **Node.js**: 18.x 或更高版本 （建议v22.20.0）
- **Minecraft Java Edition**: 1.22.6以下（建议1.22.6）

---

## 使用 Conda/Venv 虚拟环境（推荐）

### 步骤 1: 创建并激活虚拟环境

```powershell
# 使用 Conda（推荐）
conda create -n braincraft python=3.13.5
conda activate braincraft

# 或使用 venv
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

### 步骤 2: 安装 Python 依赖

```powershell
# 确保虚拟环境已激活
pip install -r requirements.txt
```

### 步骤 3: 安装 JavaScript 依赖

```powershell
# 安装主项目依赖
npm install

# 安装桥接模块依赖
cd agent\bridge
npm install
cd ..\..
```

### 步骤 4: 配置 API 密钥

编辑项目根目录的 `keys.json`:

```json
{
  "QWEN_API_KEY": "sk-your-qwen-key-here",
  "OPENAI_API_KEY": "sk-your-openai-key-here",
  "ANTHROPIC_API_KEY": "sk-your-claude-key-here"
}
```

### 步骤 5: 配置智能体

编辑 `profiles/three_layer_brain.json`:

```json
{
  "agent_name": "BrainyBot",
  "ipc_port": 9000,
  "keys_file": "keys.json",
  "three_layer_brain_llm": {
    "high_level_brain": {
      "model_name": "qwen-max",
      "api": "qwen",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "interval_seconds": 600
    },
    "mid_level_brain": {
      "model_name": "qwen-plus",
      "api": "qwen",
      "max_task_retries": 3
    }
  }
}
```

### 步骤 6: 配置 Minecraft 服务器

编辑 `settings.js`:

```javascript
const settings = {
  "minecraft_version": "auto",
  "host": "127.0.0.1",
  "port": 25565,
  "auth": "offline"
}
```

### 步骤 7: 启动系统

**终端 1 - Python 大脑**:
```powershell
conda activate braincraft  # 或 venv\Scripts\activate
python agent\main.py
```

**终端 2 - Minecraft 桥接**:
```powershell
node agent\bridge\minecraft_bridge.js
```

---

## 日常使用工作流程

### 1. 启动 Minecraft 服务器

```powershell
# 启动单人世界
# 1. 打开 Minecraft Java Edition
# 2. 创建/加载世界
# 3. 按 ESC → 对局域网开放
# 4. 记下端口号（如 25565）
# 5. 在 settings.js 中设置正确的端口
```

### 2. 启动 Python 大脑（终端 1）

```powershell
# 激活虚拟环境
conda activate braincraft

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

### 3. 启动 Minecraft 桥接（终端 2）

```powershell
# 切换到桥接目录
cd agent\bridge

# 启动桥接
node minecraft_bridge.js
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
Connecting to 127.0.0.1:25565 as BrainyBot
Bot spawned in world at position Vec3(100, 64, 200)
```

---

## 验证启动成功

### Python 终端应该显示

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

### JavaScript 终端应该显示

```
Bot position: Vec3(100, 64, 200)
Received command from Python: execute_code
Executing code from brain...
Code executed successfully
```

### 在 Minecraft 中

你应该看到名为 `BrainyBot` 的玩家加入游戏，并开始执行任务。

---

## 启动顺序重要说明

⚠️ **必须先启动 Python 大脑，再启动 Minecraft 桥接**

**原因**:
1. Python 大脑启动 IPC 服务器（端口 9000/9001）
2. Minecraft 桥接连接到 IPC 服务器
3. 如果顺序颠倒，桥接会报错：`Error: Cannot connect to Python brain`

---

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

---

## 目录结构说明

```
braincraft/
├── agent/                        # 智能体系统（新）
│   ├── main.py                    # 入口文件
│   ├── brain/                     # 三层大脑
│   ├── models/                    # LLM 接口
│   ├── utils/                     # 工具模块
│   ├── communication/             # IPC 通信
│   ├── bridge/                    # JS-Python 桥接
│   │   └── minecraft_bridge.js    # ⭐ 启动这个文件
│   └── prompts/                   # LLM 提示词
├── bots/                          # 智能体数据（运行时生成）
│   └── BrainyBot/
├── profiles/                      # 配置文件
│   └── three_layer_brain.json     # ⭐ 主配置文件
├── src/                           # 原 MindCraft 代码
│   └── agent/library/             # JavaScript 技能库
├── keys.json                      # ⭐ API 密钥
├── settings.js                    # ⭐ Minecraft 连接配置
└── requirements.txt               # Python 依赖
```

**注意**: `agent/` 是新的智能体系统目录，不是 `python/`。

---

## 配置文件说明

### 1. `keys.json` (项目根目录)

存储所有 LLM API 密钥：

```json
{
  "QWEN_API_KEY": "sk-xxx",
  "OPENAI_API_KEY": "sk-xxx",
  "ANTHROPIC_API_KEY": "sk-ant-xxx",
  "DEEPSEEK_API_KEY": "sk-xxx"
}
```

### 2. `profiles/three_layer_brain.json`

智能体配置：

| 配置项                     | 说明                        | 默认值    |
| -------------------------- | --------------------------- | --------- |
| `agent_name`               | 智能体名称                  | BrainyBot |
| `ipc_port`                 | IPC 通信端口                | 9000      |
| `high_level_brain.model_name` | 高层大脑使用的 LLM 模型 | qwen-max  |
| `mid_level_brain.model_name`  | 中层大脑使用的 LLM 模型 | qwen-plus |
| `interval_seconds`         | 高层唤醒间隔（秒）          | 600       |
| `max_task_retries`         | 中层最大重试次数            | 3         |

### 3. `settings.js` (项目根目录)

Minecraft 连接配置（与原 MindCraft 项目共用）：

```javascript
{
  "minecraft_version": "auto",  // 自动检测或指定版本
  "host": "127.0.0.1",          // 服务器地址
  "port": 25565,                // 服务器端口
  "auth": "offline"             // 认证方式
}
```

---

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

---

## 停止系统

### 正常停止

1. 在 JavaScript 终端按 `Ctrl+C`
2. 在 Python 终端按 `Ctrl+C`

系统会自动保存任务栈和心智状态到 `bots/BrainyBot/mind_state.json`。

### 强制停止

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

---

## 重启后恢复

系统重启后会自动从 `bots/BrainyBot/mind_state.json` 恢复：

- ✅ 任务栈状态
- ✅ 战略目标
- ✅ 目标层级
- ✅ 自我认知
- ✅ 学习经验
- ✅ 玩家关系

重启后智能体会**无缝继续执行之前的任务**。

---

## 查看运行状态

### 实时日志

观察 Python 终端和 JavaScript 终端的输出。

### 持久化文件

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

---

## 下一步

- 阅读 [ARCHITECTURE.md](ARCHITECTURE.md) 了解系统架构
- 阅读 [TASK_FLOW.md](TASK_FLOW.md) 了解任务执行流程
- 查看 `agent/prompts/` 目录了解如何自定义 LLM 提示词

---

**文档版本**: 2.0  
**更新日期**: 2025-11-03  
**维护者**: BrainCraft Development Team
