@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo   Digital Employee Backend Agent Starting...
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "PROJECT_ROOT=%REPO_ROOT%\backend-agent"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo [ERROR] Python 虚拟环境不存在: "%PYTHON%"
  echo 请先安装依赖:
  echo   cd backend-agent
  echo   uv sync
  pause
  exit /b 1
)

echo [INFO] 项目根目录: %PROJECT_ROOT%
echo.

echo [INFO] 步骤 1/2: 清理 __pycache__ 目录...
"%PYTHON%" "%SCRIPT_DIR%..\clean-pycache.py"
if errorlevel 1 (
  echo [WARN] 清理过程遇到警告，继续执行...
)
echo.

echo [INFO] 步骤 2/2: 启动 backend-agent 服务...
set "LAN_IP=localhost"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ip=[System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) | Where-Object { $_.AddressFamily -eq 'InterNetwork' -and $_.IPAddressToString -notmatch '^(127|169\.254)\.' } | Select-Object -First 1; if ($ip) { $ip.IPAddressToString } else { 'localhost' }"`) do set "LAN_IP=%%I"
echo   - 本地访问: http://localhost:8765
echo   - 局域网访问: http://%LAN_IP%:8765
echo.

cd /d "%PROJECT_ROOT%"
"%PYTHON%" "%PROJECT_ROOT%\main.py" --project-root "%PROJECT_ROOT%"

if errorlevel 1 (
  echo.
  echo [ERROR] 程序异常退出，退出码: %errorlevel%
  pause
)

endlocal
