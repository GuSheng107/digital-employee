@echo off
chcp 65001 >nul
setlocal

echo ===================================================
echo   Digital Employee - 一键启动所有服务
echo ===================================================
echo.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

echo [INFO] 步骤 1/5: 清理全项目 Python 缓存...
python "%SCRIPT_DIR%clean-pycache.py"
echo.

echo [INFO] 步骤 2/5: 在新窗口中启动 Backend Agent 服务 (8765)...
start "Backend Agent (8765)" cmd /k "%SCRIPT_DIR%backend-agent\start.cmd"

echo [INFO] 步骤 3/5: 在新窗口中启动 Backend Gateway 网关服务...
start "Backend Gateway Service" cmd /k "%SCRIPT_DIR%backend-gateway\start.bat"

echo [INFO] 步骤 4/5: 在新窗口中启动 Backend Data 数据平台服务 (8010)...
start "Backend Data Service (8010)" cmd /k "%SCRIPT_DIR%data-platform\start.bat"

echo [INFO] 步骤 5/5: 在新窗口中启动 Frontend 前端开发服务 (5173)...
start "Frontend Dev Server (5173)" cmd /k "%SCRIPT_DIR%start-web.cmd"

echo.
echo ===================================================
echo   所有服务启动命令已发送！
echo   请在弹出的各个控制台窗口中查看对应服务的实时日志。
echo ===================================================
echo.
pause
