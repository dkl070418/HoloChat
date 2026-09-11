#!/usr/bin/env bash
# ============================================================
#  Iroh P2P Chat - portable one-click launcher (macOS / Linux / WSL)
#  Everything stays inside the project folder, using the embedded
#  runtime under python/ (replaces the old .venv):
#    python/  embedded python + deps   .tmp   temp/caches
#    data/  chat.db                    downloads/   cache/
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

# ---- redirect all temp/cache off the system dirs ----
export TEMP="$ROOT/.tmp" TMP="$ROOT/.tmp"
export PIP_CACHE_DIR="$ROOT/.tmp/pip-cache"
export npm_config_cache="$ROOT/.tmp/npm-cache"
export PYTHONPYCACHEPREFIX="$ROOT/.tmp/pycache"
mkdir -p "$TEMP"

# embedded runtime (adjust per platform: linux uses bin/python3, win uses python.exe)
VPY="$ROOT/python/bin/python3"
[ -x "$VPY" ] || VPY="$ROOT/python/python.exe"
if [ ! -x "$VPY" ]; then
  echo "[ERROR] embedded runtime not found under python/ (python/bin/python3 or python/python.exe)"
  exit 1
fi

# ---- backend deps: only install if missing (fast) ----
if ! "$VPY" -c "import fastapi, uvicorn, iroh, pydantic" >/dev/null 2>&1; then
  echo "[init] backend deps missing, installing (Tsinghua mirror) ..."
  "$VPY" -m pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r "$ROOT/backend/requirements.txt"
fi

# ---- launch backend in the background (port 8000) ----
echo "[start] launching backend on port 8000 ..."
"$VPY" "$ROOT/backend/run.py" 8000 &
BACK_PID=$!
trap 'kill $BACK_PID 2>/dev/null || true' EXIT

# ---- wait for backend health ----
echo "[start] waiting for backend ..."
for i in $(seq 1 40); do
  if curl -sf -o /dev/null http://127.0.0.1:8000/api/info; then
    echo "[OK] backend ready."
    break
  fi
  sleep 1
done
if ! curl -sf -o /dev/null http://127.0.0.1:8000/api/info; then
  echo "[ERROR] backend did not become ready."; exit 1
fi

# ---- frontend deps (npmmirror via frontend/.npmrc) ----
if [ ! -d "frontend/node_modules" ]; then
  echo "[init] installing frontend deps (npmmirror) ..."
  ( cd frontend && npm install --no-audit --no-fund )
fi

# ---- launch frontend dev server (blocks) ----
echo
echo "[OK] Iroh P2P Chat is running."
echo "     Backend  : http://127.0.0.1:8000   (node credential is printed in the backend log)"
echo "     Frontend : http://localhost:5173"
echo
( cd frontend && npm run dev )
