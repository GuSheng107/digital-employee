@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title Backend Gateway Service

REM 切换到 backend-gateway 根目录
cd /d "%~dp0..\..\backend-gateway"

echo ===================================================
echo            Backend Gateway Service                 
echo ===================================================

REM 检查 .env 文件
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env 未找到，正在从 .env.example 复制...
        copy ".env.example" ".env" > nul
    ) else (
        echo [WARN] .env.example 未找到，请手动配置环境变量。
    )
)

REM 检查 config\bot.json 文件
if not exist "config\bot.json" (
    if exist "config\bot.template.json" (
        echo [INFO] config\bot.json 未找到，正在从 config\bot.template.json 复制...
        copy "config\bot.template.json" "config\bot.json" > nul
    ) else (
        echo [WARN] config\bot.template.json 未找到。
    )
)

REM 检查虚拟环境
if not exist ".venv" (
    echo [INFO] .venv 目录未找到，正在运行 uv sync...
    uv sync
    if !errorlevel! neq 0 (
        echo [ERROR] 运行 uv sync 失败。
        pause
        exit /b !errorlevel!
    )
)

echo [INFO] 正在启动网关服务 (uv run python -m src.main)...
echo ===================================================

uv run python -m src.main

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] 服务异常退出，错误码: !errorlevel!
)

pause
