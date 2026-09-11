"""Project-root-relative paths for full portability.

The whole project must be self-contained (portable): an embedded Python runtime
lives at `<project>/python`, and every piece of runtime data is forced under the
project directory — never `~`, `AppData`, `Temp` or the system drive.

Layout under the project root:
    python/      embedded Python runtime + deps (replaces the old .venv)
    .tmp/        TEMP/TMP redirect target (run scripts point TMP here)
    data/        chat.db (SQLite history + peer metadata)
    downloads/   files received from peers (served for preview/playback)
    cache/       pip / npm build caches
    backend/     FastAPI + iroh source
    frontend/    Vue 3 SPA source
"""
import sys
from pathlib import Path

# Frozen (PyInstaller) note: when packed, `__file__` lives inside the extracted
# bundle (sys._MEIPASS), which is a read-only temp dir wiped on exit. So runtime
# state must live NEXT TO the executable (persistent + user-writable), while the
# bundled SPA (frontend/dist) is read from _MEIPASS. Under a source run the
# original project-relative layout is kept unchanged.
IS_FROZEN = bool(getattr(sys, "frozen", False))

# project root == parent of this file's parent (backend/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if IS_FROZEN:
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    APP_DIR = Path(sys.executable).resolve().parent  # folder holding IrohChat.exe
else:
    APP_DIR = PROJECT_ROOT

# Source-run only: allow a custom runtime-data root (used by automated multi-node
# tests to isolate each instance's data/secret). Ignored when frozen.
if not IS_FROZEN:
    _env_data = __import__("os").environ.get("IROH_DATA_DIR")
    if _env_data:
        APP_DIR = Path(_env_data).resolve()

# runtime paths (all APP_DIR-relative, created on demand)
DATA_DIR = APP_DIR / "data"
DOWNLOAD_DIR = APP_DIR / "downloads"
CACHE_DIR = APP_DIR / "cache"
TMP_DIR = APP_DIR / ".tmp"
# embedded runtime (python/...) replaces the old .venv; source-run only, irrelevant when frozen
PYTHON_DIR = PROJECT_ROOT / "python"

# default single-node database (portable, independent of which port runs)
DB_PATH = DATA_DIR / "chat.db"

# built SPA, served by the backend so a single exe is self-contained
if IS_FROZEN:
    FRONTEND_DIST = BUNDLE_DIR / "frontend" / "dist"
else:
    FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def ensure_dirs() -> None:
    for d in (DATA_DIR, DOWNLOAD_DIR, CACHE_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


ensure_dirs()
