@echo off
setlocal
REM ============================================================
REM  Iroh P2P Chat - stop backend + frontend (Windows)
REM  按端口精确停止本项目服务，不会误杀其他 node/python 进程
REM  （例如 DSH 的服务、你的其他项目）。
REM  后端 : port 8000   前端 dev server : port 5173
REM ============================================================

echo [stop] 正在停止本项目后端(8000)与前端(5173) ...

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-server.ps1"

echo.
echo [OK] 已停止。相关窗口若仍残留可手动关闭。
pause
