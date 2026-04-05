param(
    [string]$EnvName = "braincraft_env"
)

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   MindCraft 智能体一键启动脚本" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

$BasePath = Join-Path $PSScriptRoot

# 1. 启动 Python 端
Write-Host "[1/2] 正在启动 Python 端 (Agent) ..." -ForegroundColor Green
$RootPath = Join-Path $BasePath ".."
$pythonCmd = "cd '$RootPath'; conda activate $EnvName; python agent/main.py"
Start-Process powershell -ArgumentList "-NoExit -Command `"$pythonCmd`""

# 等待 Python端 的 IPC 服务器启动
Write-Host "等待 5 秒，以确保 Python IPC 后端完全运行..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 2. 启动 Java/Node.js 端
Write-Host "[2/2] 正在启动 JavaScript/Java 端 (Node Bridge) ..." -ForegroundColor Green
$nodeCmd = "cd '$RootPath'; node agent/bridge/minecraft_bridge.js"

Write-Host ""
Write-Host "启动动作已完成！请查看弹出的两个窗口以确认服务运行状态。" -ForegroundColor Cyan
