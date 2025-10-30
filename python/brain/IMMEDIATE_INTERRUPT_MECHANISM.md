# 立即打断机制实现说明

## ✨ 新特性：真正的立即打断

使用 `asyncio.Task.cancel()` 实现了真正的立即打断机制，高优先级事件可以**立即中断**正在执行的低优先级任务。

## 🔧 实现原理

### 1. Task 跟踪

ExecutionCoordinator 现在跟踪当前正在执行的 asyncio Task：

```python
class ExecutionCoordinator:
    def __init__(self, ...):
        self.current_task = None  # 当前执行的 Task
        self.current_layer = None  # 当前执行层级
```

### 2. 立即取消机制

当高优先级动作到来时，立即取消当前任务：

```python
async def execute_action(self, layer, label, action_fn, ...):
    # 1. 检查优先级
    if executing_layer and self._can_interrupt(executing_layer, layer):
        
        # 2. ⚡ 立即取消当前任务
        if self.current_task and not self.current_task.done():
            logger.warning(f"🛑 Cancelling {executing_layer} to execute {layer}:{label}")
            self.current_task.cancel()
            
            # 等待取消完成（最多0.5秒）
            try:
                await asyncio.wait_for(self.current_task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass  # 预期的 - 任务已取消
    
    # 3. 创建新的可取消任务
    self.current_task = asyncio.create_task(action_fn())
    
    try:
        result = await self.current_task
        return {'success': True, 'result': result}
        
    except asyncio.CancelledError:
        # 任务被更高优先级动作取消
        return {'success': False, 'cancelled': True}
```

### 3. 取消点（Cancellation Points）

被执行的函数需要包含 `await` 语句作为取消点：

```python
# mid_level_brain.py
async def _send_code_to_javascript(self, code):
    while True:
        result = await self.shared_state.get('last_execution_result')
        if result:
            return result
        
        # ⚡ 这里是取消点 - 任务可以在这里被立即取消
        await asyncio.sleep(0.1)
```

当 `task.cancel()` 被调用时，下一个 `await` 语句会抛出 `asyncio.CancelledError`。

### 4. 异常处理

```python
async def _send_code_to_javascript(self, code):
    try:
        # ... 执行代码 ...
        
    except asyncio.CancelledError:
        logger.warning("⚠️ Code execution cancelled by higher priority action")
        await self.shared_state.update('last_execution_result', None)
        raise  # 重新抛出以传播取消信号
```

### 5. 自动恢复

被取消的任务会自动保存状态并在高优先级任务完成后恢复：

```python
# ExecutionCoordinator 自动处理
if result.get('cancelled'):
    # 保存被中断的任务信息
    await self._save_interrupted_action(executing_layer, layer)
    
# 高优先级任务完成后
if auto_resume:
    await self._resume_interrupted_action()
```

## 📊 执行流程示例

### 场景：低血量打断采集任务

```
T=0s    Mid-level 开始执行：收集木头（发送代码到 JavaScript）
        → ExecutionCoordinator.current_task = Task(collect_wood)
        → executing_layer = 'mid'
        
T=5s    进入等待循环：while True: await asyncio.sleep(0.1)
        
T=10s   玩家血量降至 3/20
        → Low-level brain 检测到低血量
        
T=10.0s Low-level 调用 ExecutionCoordinator:
        → execute_action(layer='low_reflex', label='reflex:low_health', ...)
        → 检查优先级: low_reflex(5) > mid(2) ✅
        → 🛑 current_task.cancel()  # 立即取消收集木头任务！
        
T=10.1s Mid-level 的 await asyncio.sleep(0.1) 抛出 CancelledError
        → 任务被中断
        → 保存中断信息：{'layer': 'mid', 'step_index': 1, ...}
        
T=10.1s Low-level 反射动作开始执行
        → 发送逃跑命令
        → await asyncio.sleep(2)
        
T=12.1s 反射动作完成
        → ExecutionCoordinator 检查 auto_resume=True
        → 调用 _resume_interrupted_action()
        → 设置 shared_state['mid_task_resume_requested'] = True
        
T=13s   Mid-level brain 主循环检查到 resume_requested
        → 从 step_index=1 继续执行任务
        → ✅ 恢复收集木头任务
```

## ⚡ 打断响应时间

| 场景               | 之前                 | 现在                          |
| ------------------ | -------------------- | ----------------------------- |
| 低血量打断代码执行 | 最多30秒（等待超时） | **最多0.2秒**（下一个 await） |
| 拾取物品打断任务   | 最多30秒             | **最多0.2秒**                 |
| 聊天打断任务       | 最多30秒             | **立即**（已绕过）            |
| 脱困打断任务       | 最多30秒             | **最多0.2秒**                 |

## 🎯 优先级表

| 优先级   | 层级       | 能打断             | 被打断                        |
| -------- | ---------- | ------------------ | ----------------------------- |
| 5 (最高) | low_reflex | 所有               | 无                            |
| 4        | low_mode   | unstuck, mid, high | low_reflex                    |
| 3        | unstuck    | mid, high          | low_reflex, low_mode          |
| 2        | mid        | high               | low_reflex, low_mode, unstuck |
| 1 (最低) | high       | 无                 | 所有                          |

## 🔍 关键代码位置

### ExecutionCoordinator (python/brain/execution_coordinator.py)

- **第35-38行**：Task 跟踪变量
- **第85-95行**：立即取消逻辑
- **第100-102行**：创建可取消任务
- **第115-120行**：处理 CancelledError

### Mid-level Brain (python/brain/mid_level_brain.py)

- **第867行**：取消点（await asyncio.sleep）
- **第869-873行**：CancelledError 处理
- **第324-327行**：处理被取消的任务结果

## ✅ 测试检查清单

- [ ] 低血量反射打断代码执行（采集、制作等）
- [ ] 拾取物品打断卡住检测
- [ ] 脱困打断低优先级模式
- [ ] 被打断任务能正确恢复
- [ ] 取消期间状态清理正确
- [ ] 日志显示清晰的打断信息

## 🚀 使用示例

### 在你的代码中使用

```python
# 高优先级任务（可以打断其他任务）
result = await exec_coordinator.execute_action(
    layer='low_reflex',
    label='reflex:escape',
    action_fn=lambda: self._escape_danger(),
    can_interrupt=None,  # 不可被打断
    auto_resume=True      # 完成后恢复被打断的任务
)

if result.get('success'):
    print("反射动作完成")
    # 被打断的任务会自动恢复
```

### 可被打断的任务

```python
# 低优先级任务（可以被打断）
result = await exec_coordinator.execute_action(
    layer='mid',
    label='task:collect_wood',
    action_fn=lambda: self._collect_wood(),
    can_interrupt=['low_reflex', 'low_mode', 'unstuck'],  # 可被这些层级打断
    auto_resume=True
)

if result.get('cancelled'):
    print("任务被高优先级动作打断")
    # 不用担心 - 会自动恢复
```

## 🐛 调试技巧

### 日志标记

打断发生时会看到以下日志：

```
WARNING - 🛑 Cancelling mid task to execute higher priority low_reflex:reflex:low_health
WARNING - ⚠️ Code execution cancelled by higher priority action
INFO    - ⚠️ task:collect_wood was cancelled by higher priority action
INFO    - ✅ Resuming interrupted mid-level task
```

### 检查共享状态

```python
executing_layer = await shared_state.get('executing_layer')
interrupted_action = await shared_state.get('interrupted_action')
print(f"当前执行: {executing_layer}")
print(f"被打断的: {interrupted_action}")
```

## 📝 注意事项

1. **必须有 await 点**：被执行的函数必须包含 `await` 语句，否则无法被取消
2. **清理资源**：在 `except asyncio.CancelledError` 中清理资源后，必须 `raise` 以传播取消信号
3. **避免过长操作**：单个操作不要超过 0.5 秒，否则打断延迟会增加
4. **测试取消路径**：确保所有可能被打断的代码路径都经过测试

## 🎉 总结

现在系统支持真正的立即打断！高优先级事件（如低血量逃跑）可以在 **0.1-0.2 秒内**打断正在执行的低优先级任务（如采集木头），而不是等待 30 秒超时。被打断的任务会自动保存状态并在高优先级任务完成后恢复执行。
