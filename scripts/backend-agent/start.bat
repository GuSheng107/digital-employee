@echo off
chcp 65001 >nul

echo ========================================
echo   Digital Employee Backend Agent Starting
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..\..") do set REPO_ROOT=%%~fI
set PROJECT_ROOT=%REPO_ROOT%\backend-agent
set PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe

if not exist "%PYTHON%" goto NO_PYTHON

echo [INFO] Project root: %PROJECT_ROOT%
echo.

echo [INFO] Step 1/2: Cleaning __pycache__...
"%PYTHON%" "%SCRIPT_DIR%..\clean-pycache.py" 2>nul
echo.

echo [INFO] Step 2/2: Starting backend-agent service...
echo   - Local access: http://localhost:8765
echo.

cd /d "%PROJECT_ROOT%"
"%PYTHON%" "%PROJECT_ROOT%\main.py" --project-root "%PROJECT_ROOT%"
goto END

:NO_PYTHON
echo [ERROR] Python virtual environment not found: "%PYTHON%"
echo Please install dependencies first:
echo   cd backend-agent
echo   uv sync
pause
exit /b 1

:END
