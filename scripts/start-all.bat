@echo off
chcp 65001 >nul

echo ===================================================
echo   Digital Employee - Start All Services
echo ===================================================
echo.

set SCRIPT_DIR=%~dp0
where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv was not found in PATH.
    exit /b 1
)

uv run python "%SCRIPT_DIR%start-all.py"
exit /b %errorlevel%
