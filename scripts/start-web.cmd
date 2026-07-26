@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo   Starting Frontend Dev Server (React)...
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

if not exist "%PROJECT_ROOT%\frontend\package.json" (
  echo [ERROR] 前端项目文件未找到: "%PROJECT_ROOT%\frontend\package.json"
  pause
  exit /b 1
)

cd /d "%PROJECT_ROOT%\frontend"
echo [INFO] 切换至前端目录: %PROJECT_ROOT%\frontend
echo [INFO] 正在执行 npm run dev 启动开发服务 (http://localhost:5173)...
echo.

npm run dev

if errorlevel 1 (
  echo.
  echo [ERROR] 前端服务启动失败，错误码: %errorlevel%
  pause
)

endlocal
