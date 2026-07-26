@echo off
chcp 65001 >nul

echo ===================================================
echo   Digital Employee - Start All Services
echo ===================================================
echo.

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI

echo [INFO] Step 1/5: Cleaning python __pycache__...
python "%SCRIPT_DIR%clean-pycache.py" 2>nul
echo.

echo [INFO] Step 2/5: Starting Backend Agent Service...
start "Backend-Agent-Service" cmd /k "%SCRIPT_DIR%backend-agent\start.bat"

echo [INFO] Step 3/5: Starting Backend Gateway Service...
start "Backend-Gateway-Service" cmd /k "%SCRIPT_DIR%backend-gateway\start.bat"

echo [INFO] Step 4/5: Starting Backend Data Service...
start "Backend-Data-Service" cmd /k "%SCRIPT_DIR%data-platform\start.bat"

echo [INFO] Step 5/5: Starting Frontend Dev Server...
start "Frontend-Dev-Server" cmd /k "%SCRIPT_DIR%start-web.bat"

echo.
echo ===================================================
echo   All service launch commands sent successfully!
echo   Check real-time logs in each opened console window.
echo ===================================================
echo.
pause
