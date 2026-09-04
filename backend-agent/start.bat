@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

set "UV_EXE="
if defined DIGITAL_EMPLOYEE_UV if exist "%DIGITAL_EMPLOYEE_UV%" set "UV_EXE=%DIGITAL_EMPLOYEE_UV%"
if not defined UV_EXE if exist "%PROJECT_ROOT%\..\.venv\tools\uv\uv.exe" set "UV_EXE=%PROJECT_ROOT%\..\.venv\tools\uv\uv.exe"
if not defined UV_EXE for /f "delims=" %%I in ('where uv 2^>nul') do if not defined UV_EXE set "UV_EXE=%%I"

if not defined UV_EXE (
    echo [ERROR] 未找到 uv，请安装 uv 或通过 DIGITAL_EMPLOYEE_UV 指定 uv.exe。
    exit /b 1
)

pushd "%PROJECT_ROOT%" >nul
if not exist ".env" copy /y ".env.example" ".env" >nul

"%UV_EXE%" sync --locked
if errorlevel 1 (
    popd >nul
    echo [ERROR] Agent 依赖同步失败。
    exit /b 1
)

"%UV_EXE%" run python "scripts\service_manager.py" start %*
set "EXIT_CODE=!ERRORLEVEL!"
popd >nul
exit /b !EXIT_CODE!
