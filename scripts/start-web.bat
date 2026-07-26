@echo off
chcp 65001 >nul

echo ========================================
echo   Starting Frontend Dev Server
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI

if not exist "%PROJECT_ROOT%\frontend\package.json" goto NO_FRONTEND

cd /d "%PROJECT_ROOT%\frontend"
echo [INFO] Project dir: %PROJECT_ROOT%\frontend

if not exist "%PROJECT_ROOT%\frontend\node_modules" (
  echo [INFO] node_modules not found, installing dependencies via npm...
  npm install
)

echo [INFO] Running npm run dev...
echo   - Local URL: http://localhost:5173
echo.

npm run dev
goto END

:NO_FRONTEND
echo [ERROR] Frontend project file not found: "%PROJECT_ROOT%\frontend\package.json"
pause
exit /b 1

:END
