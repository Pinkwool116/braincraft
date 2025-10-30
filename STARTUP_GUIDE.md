# 三层大脑系统 - 启动指南

## 使用 Conda/Venv 虚拟环境（推荐）

### 步骤 1: 激活虚拟环境并安装 Python 依赖
```powershell
# 激活你的 conda 环境
conda activate your_env_name

# 安装 Python 依赖
pip install -r requirements.txt
```

### 步骤 2: 安装 JavaScript 依赖
```powershell
cd python\bridge
npm install
cd ..\..
```

### 步骤 3: 启动 Python 大脑（终端 1）
```powershell
# 确保虚拟环境已激活
conda activate your_env_name

# 启动 Python 大脑
python python\main.py
```

### 步骤 4: 启动 JavaScript 桥接（终端 2）
```powershell
# 在新终端中
cd python\bridge
node minecraft_bridge.js
```

---

## 依赖安装

### Python 依赖 (requirements.txt)
```bash
pip install -r requirements.txt
```

### JavaScript 依赖 (python/bridge/package.json)
```bash
cd python\bridge
npm install
```

---

## 验证启动

### Python 大脑应该显示：
```
======================================================================
  BrainCraft Three-Layer Brain System
======================================================================
Loading configuration...
Initializing IPC server on port 9000...
IPC server started on ports 9000 (REP) and 9001 (PUB)
High-level brain started (interval: 300s)
Mid-level brain started (interval: 1s)
Low-level brain started (interval: 0.1s)
```

### JavaScript 桥接应该显示：
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
```

---

## 推荐工作流程

1. **首次设置**:
   ```powershell
   # 创建并激活虚拟环境
   conda create -n env_name python=3.10
   conda activate env_name
   
   # 安装依赖
   pip install -r requirements.txt
   cd python\bridge
   npm install
   cd ..\..
   ```

2. **日常使用**:
   ```powershell
   # 终端 1: Python 大脑
   conda activate env_name
   python python\main.py
   
   # 终端 2: JavaScript 桥接
   conda activate env_name
   cd python\bridge
   node minecraft_bridge.js
   ```

3. **连接 Minecraft**:
   - 打开 Minecraft Java Edition
   - 创建/加载世界
   - 按 ESC → 对局域网开放
   - 记下端口号（如 55916）
   - 在 `settings.js` 中设置正确的端口
