@echo off
REM Development startup script for digital-employee

echo === Digital Employee Dev Setup ===

echo [1/3] Starting backend-agent...
start "backend-agent" cmd /k "cd /d %~dp0..\backend-agent && python main.py"

echo [2/3] Starting backend-gateway...
start "backend-gateway" cmd /k "cd /d %~dp0..\backend-gateway\cmd\cc-connect && go run ."

echo [3/3] Starting frontend...
start "frontend" cmd /k "cd /d %~dp0..\frontend && npm run dev"

echo.
echo All services started!
echo   Backend Agent:   http://localhost:8000
echo   Backend Gateway: http://localhost:8080
echo   Frontend:        http://localhost:3000
