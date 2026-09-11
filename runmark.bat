@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  Iroh P2P Chat - portable one-click launcher (Windows)
REM  Everything stays inside the project folder, using the embedded
REM  runtime at python\ (replaces the old .venv):
REM    python/  embedded python + deps   .tmp   temp/caches
REM    data/  chat.db                    downloads/   cache/
REM ============================================================

set "PROJECT_ROOT=%~dp0"
set "VPY=%PROJECT_ROOT%python\python.exe"

if not exist "%VPY%" (
  echo [ERROR] embedded runtime not found at python\python.exe
  pause & exit /b 1
)

REM ---- redirect all temp/cache off the system drive ----
set "TEMP=%PROJECT_ROOT%.tmp"
set "TMP=%PROJECT_ROOT%.tmp"
set "PIP_CACHE_DIR=%PROJECT_ROOT%.tmp\pip-cache"
set "npm_config_cache=%PROJECT_ROOT%.tmp\npm-cache"
set "PYTHONPYCACHEPREFIX=%PROJECT_ROOT%.tmp\pycache"
if not exist "%TEMP%" mkdir "%TEMP%"

REM ---- backend deps: only install if missing (fast) ----
"%VPY%" -c "import fastapi, uvicorn, iroh, pydantic" >nul 2>nul
if errorlevel 1 (
  echo [init] backend deps missing, installing from Tsinghua mirror ...
  "%VPY%" -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r "%PROJECT_ROOT%backend\requirements.txt"
  if errorlevel 1 (echo [ERROR] backend dependency install failed & pause & exit /b 1)
)

REM ---- launch backend in its own window (port 8000) ----
REM Direct `start` on python.exe avoids nested cmd /k call quoting entirely.
REM The new window inherits this script's TEMP/TMP/PYTHONPYCACHEPREFIX env vars.
echo [start] launching backend on port 8000 ...
start "iroh-backend" /D "%PROJECT_ROOT%" "%VPY%" "%PROJECT_ROOT%backend\run.py" 8000

REM ---- wait for backend health ----
echo [start] waiting for backend ...
set /a tries=0
:wait
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/info;exit 0}catch{exit 1}" >nul 2>nul
if not errorlevel 1 goto backend_up
set /a tries+=1
if !tries! lss 40 goto wait
echo [ERROR] backend did not become ready in time. & pause & exit /b 1
:backend_up
echo [OK] backend ready.
echo M_AFTER_HEALTH

REM ---- frontend deps from npmmirror (see frontend\.npmrc) ----
if not exist "frontend\node_modules" (
echo M_AT_FRONT_IF
  echo [init] installing frontend deps (npmmirror) ...
  cd frontend
  call npm install --no-audit --no-fund
  if errorlevel 1 (cd .. & echo [ERROR] npm install failed & pause & exit /b 1)
  cd ..
)
echo M_AFTER_NPM_IF

REM ---- launch frontend dev server (blocks) ----
echo M_AFTER_REM_DEV
echo.
echo M_AFTER_ECHO_DOT
echo [OK] Iroh P2P Chat is running.
echo M_AFTER_ECHO_OK
echo      Backend  :  http://127.0.0.1:8000   (node credential is in the "iroh-backend" window)
echo      Frontend :  http://localhost:5173
echo.
echo   To STOP: run stop.bat  (kills backend + frontend)
echo            or close the "iroh-backend" window, then Ctrl+C here.
echo.
echo   This window stays open while the frontend runs.
echo M_AFTER_ECHOS
cd frontend
echo M_BEFORE_CD_FRONT
call npm run dev
cd ..
echo.
echo [OK] Frontend stopped. Closing.
pause
