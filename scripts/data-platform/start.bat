@echo off
chcp 65001 >nul

title Backend Data Service

cd /d "%~dp0..\..\backend-data\backend"

echo ===================================================
echo            Backend Data Service 8010             
echo ===================================================

if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

echo [INFO] Starting Backend Data Service with uv...
echo   - Local URL: http://127.0.0.1:8010
echo   - Health Check: http://127.0.0.1:8010/health
echo   - API Docs:  http://127.0.0.1:8010/docs
echo ===================================================

uv run uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
pause
