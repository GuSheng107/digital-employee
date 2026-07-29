@echo off
chcp 65001 >nul

title Backend Auth Service
cd /d "%~dp0..\..\backend-auth"

if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

echo ===================================================
echo            Backend Auth Service 8020
echo ===================================================
echo [INFO] Starting Backend Auth Service with uv...
echo   - Local URL: http://localhost:8020
echo   - Health Check: http://localhost:8020/api/v1/health
echo ===================================================

uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
pause
