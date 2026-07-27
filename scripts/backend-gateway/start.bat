@echo off
chcp 65001 >nul

title Backend Gateway Service

cd /d "%~dp0..\..\backend-gateway"

echo ===================================================
echo            Backend Gateway Service 8864
echo ===================================================

if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul
if not exist "config\bot.json" if exist "config\bot.template.json" copy "config\bot.template.json" "config\bot.json" >nul

echo [INFO] Starting Gateway Service with uv...
echo   - Local URL: http://localhost:8864
echo   - Health Check: http://localhost:8864/api/v1/health
echo ===================================================

uv run python -m src.main
pause
