@echo off
chcp 65001 >nul

echo ========================================
echo   Digital Employee Backend Agent Starting
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..\..") do set REPO_ROOT=%%~fI
set PROJECT_ROOT=%REPO_ROOT%\backend-agent

echo [INFO] Project root: %PROJECT_ROOT%
echo.

echo [INFO] Step 1/2: Cleaning __pycache__...
uv run python "%SCRIPT_DIR%..\clean-pycache.py" 2>nul
echo.

echo [INFO] Step 2/2: Starting backend-agent service with uv...
echo   - Local access: http://localhost:8765
echo.

cd /d "%PROJECT_ROOT%"
uv run main.py --project-root "%PROJECT_ROOT%"
pause
