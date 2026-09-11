#!/usr/bin/env bash
# Iroh P2P Chat - PyInstaller single-exe build script (Unix/macOS - optional).
# Produces a single executable in dist/ ; Windows users should use pack_exe.bat.
set -euo pipefail
cd "$(dirname "$0")"

VPY="python/bin/python3"
[ -x "$VPY" ] || VPY="python/python.exe"
[ -x "$VPY" ] || { echo "[ERROR] embedded runtime not found under python/"; exit 1; }
[ -f frontend/dist/index.html ] || { echo "[ERROR] run 'cd frontend && npm run build' first"; exit 1; }

"$VPY" -m pip show pyinstaller >/dev/null 2>&1 || \
  "$VPY" -m pip install pyinstaller

"$VPY" -m PyInstaller --noconfirm iroh.spec
echo "[OK] Build complete -> dist/"