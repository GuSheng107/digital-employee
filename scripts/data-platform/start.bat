@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title Backend Data Service

cd /d "%~dp0..\..\backend-data\backend"

echo ===================================================
echo            Backend Data Service (8010)             
echo ===================================================

REM 检查 .env 文件
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env 未找到，正在从 .env.example 复制...
        copy ".env.example" ".env" > nul
    ) else (
        echo [WARN] .env.example 未找到。
    )
)

echo [INFO] 正在启动数据平台后端 (uvicorn app.main:app)...
echo   - 接口服务: http://127.0.0.1:8010
echo   - 健康检查: http://127.0.0.1:8010/health
echo   - API 文档:  http://127.0.0.1:8010/docs
echo ===================================================

python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] 服务异常退出，错误码: !errorlevel!
)

pause
