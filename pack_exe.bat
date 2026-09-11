@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  Iroh P2P Chat - PyInstaller onefile build (Windows)
REM  Uses embedded python\python.exe and its PyInstaller to build.
REM  Output: dist\IrohChat.exe
REM ============================================================

set "PROJECT_ROOT=%~dp0"
set "VPY=%PROJECT_ROOT%python\python.exe"

if not exist "%VPY%" (
  echo [ERROR] embedded runtime not found at python\python.exe
  exit /b 1
)

echo [1/3] checking frontend build (frontend\dist) ...
if not exist "%PROJECT_ROOT%frontend\dist\index.html" (
  echo [ERROR] frontend not built. Run:  cd frontend ^&^& npm run build
  exit /b 1
)

echo [2/3] ensuring PyInstaller in embedded runtime ...
"%VPY%" -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
  echo   installing PyInstaller (Tsinghua mirror) ...
  "%VPY%" -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
  if errorlevel 1 ( echo [ERROR] PyInstaller install failed & exit /b 1 )
)

echo [3/3] running PyInstaller (onefile) ...
"%VPY%" -m PyInstaller --noconfirm "iroh.spec"
if errorlevel 1 ( echo [ERROR] PyInstaller build failed & exit /b 1 )

echo.
echo [OK] Build complete.
echo      Single exe : dist\IrohChat.exe
echo      Console shows the node credential on first launch.
echo      Runtime data (data/, downloads/) is created next to the exe.
pause
