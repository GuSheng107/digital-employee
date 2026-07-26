@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title Backend Data Service

cd /d "%~dp0..\..\backend-data\backend"

if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

REM 默认值，与 .env.example 保持一致
set APP_HOST=127.0.0.1
set APP_PORT=8010

REM 从 .env 读取 APP_HOST / APP_PORT，与 start.sh 的 get_env 行为对齐
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set _key=%%a
    if not "!_key:~0,1!"=="#" (
      if /i "%%a"=="APP_HOST" set APP_HOST=%%b
      if /i "%%a"=="APP_PORT" set APP_PORT=%%b
    )
  )
)

echo ===================================================
echo            Backend Data Service !APP_PORT!
echo ===================================================

echo [INFO] Starting Backend Data Service with uv...
echo   - Local URL: http://!APP_HOST!:!APP_PORT!
echo   - Health Check: http://!APP_HOST!:!APP_PORT!/health
echo   - API Docs:  http://!APP_HOST!:!APP_PORT!/docs
echo ===================================================

uv run uvicorn app.main:app --host !APP_HOST! --port !APP_PORT! --reload
endlocal
pause
