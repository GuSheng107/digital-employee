@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo   WeCom Bot Agent Starting...
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo [ERROR] Python virtual environment not found: "%PYTHON%"
  echo Please install dependencies first.
  pause
  exit /b 1
)

echo [INFO] Project root: %PROJECT_ROOT%
echo.

echo [INFO] Step 1/2: Cleaning __pycache__ directories...
"%PYTHON%" "%SCRIPT_DIR%\clean-pycache.py"
if errorlevel 1 (
  echo [WARN] Cleanup encountered an error, continuing anyway...
)
echo.

echo [INFO] Step 2/2: Starting backend service...
set "LAN_IP=localhost"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ip=[System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) | Where-Object { $_.AddressFamily -eq 'InterNetwork' -and $_.IPAddressToString -notmatch '^(127|169\.254)\.' } | Select-Object -First 1; if ($ip) { $ip.IPAddressToString } else { 'localhost' }"`) do set "LAN_IP=%%I"
echo   - Local access: http://localhost:8765
echo   - LAN access:  http://%LAN_IP%:8765
echo.

cd /d "%PROJECT_ROOT%"
"%PYTHON%" "%PROJECT_ROOT%\main.py" --project-root "%PROJECT_ROOT%"

if errorlevel 1 (
  echo.
  echo [ERROR] Program exited with error code: %errorlevel%
  pause
)

endlocal
