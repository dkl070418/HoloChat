@echo off
setlocal
REM  Backend window wrapper for run.bat: sets portable temp dirs, then runs the
REM  backend with the embedded python. Called via:  cmd /k call "backend\run_backend.bat" [port]
REM  Keeping the quoting here (in a file) avoids the nested-quote error you get
REM  when writing "%VPY%" inside a `start "title" cmd /k "..."` string.
cd /d "%~dp0\.."

set "ROOT=%CD%"
set "TEMP=%ROOT%\.tmp"
set "TMP=%ROOT%\.tmp"
set "PYTHONPYCACHEPREFIX=%ROOT%\.tmp\pycache"
if not exist "%TEMP%" mkdir "%TEMP%"

set "VPY=%ROOT%\python\python.exe"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"

echo [start] Iroh backend on http://127.0.0.1:%PORT%  (port %PORT%)
"%VPY%" "%ROOT%\backend\run.py" %PORT%
