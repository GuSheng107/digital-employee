@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title Backend Gateway Service

REM Switch to backend-gateway root directory
cd /d "%~dp0.."

echo ===================================================
echo            Backend Gateway Service                 
echo ===================================================

REM Check .env file
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env not found. Copying from .env.example...
        copy ".env.example" ".env" > nul
    ) else (
        echo [WARN] .env.example not found. Please set environment variables manually.
    )
)

REM Check config\bot.json file
if not exist "config\bot.json" (
    if exist "config\bot.template.json" (
        echo [INFO] config\bot.json not found. Copying from config\bot.template.json...
        copy "config\bot.template.json" "config\bot.json" > nul
    ) else (
        echo [WARN] config\bot.template.json not found.
    )
)

REM Check virtualenv
if not exist ".venv" (
    echo [INFO] .venv directory not found. Running uv sync...
    uv sync
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to run uv sync.
        pause
        exit /b !errorlevel!
    )
)

echo [INFO] Starting gateway service (uv run python -m src.main)...
echo ===================================================

uv run python -m src.main

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Service exited with code: !errorlevel!
)

pause
