@echo off
chcp 65001 >nul

echo ===================================================
echo   Digital Employee - Start All Services
echo ===================================================
echo.

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI

echo [INFO] Step 1/4: Cleaning python __pycache__...
if exist "%SCRIPT_DIR%clean-pycache.py" (
    where uv >nul 2>&1 && uv run python "%SCRIPT_DIR%clean-pycache.py" 2>nul || python "%SCRIPT_DIR%clean-pycache.py" 2>nul
)
echo.

echo [INFO] Step 2/4: Starting Backend Gateway Service (8864)...
start "Backend-Gateway-Service" cmd /k "%SCRIPT_DIR%backend-gateway\start.bat"

echo [INFO] Step 3/4: Starting Backend Data Service (8010)...
start "Backend-Data-Service" cmd /k "%SCRIPT_DIR%data-platform\start.bat"

echo [INFO] Step 4/4: Starting Frontend Dev Server (5173)...
start "Frontend-Dev-Server" cmd /k "%SCRIPT_DIR%frontend\start-web.bat"

echo.
echo ===================================================
echo   All service launch commands sent successfully!
echo   Check real-time logs in each opened console window.
echo ===================================================
echo.
pause
