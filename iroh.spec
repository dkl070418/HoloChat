# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — build Iroh P2P Chat into a SINGLE .exe (onefile).

Build (from the project root, using the embedded runtime):
    python\\python.exe -m PyInstaller iroh.spec --noconfirm

...or just run `pack_exe.bat` (uses the embedded runtime's PyInstaller).

Assumptions (spec lives at the project root):
    <root>/iroh.spec                         <- this file
    <root>/backend/packaged_launcher.py      <- entry point (imports app.main)
    <root>/frontend/dist                     <- built SPA (run `npm run build` first)

The native `iroh_ffi.dll` and Python glue are collected from the installed
`iroh` package; iroh_ffi.py loads the DLL from its own directory, so the DLL
must land beside it inside the bundle (collect_all handles this).
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# SPECPATH = directory containing this spec (injected by PyInstaller)
SPEC_DIR = Path(SPECPATH)
BACKEND = SPEC_DIR / "backend"
FRONTEND_DIST = SPEC_DIR / "frontend" / "dist"

if not FRONTEND_DIST.exists():
    raise SystemExit(
        "\n[ERROR] frontend/dist not found — build the SPA first:\n"
        "    cd frontend && npm run build\n"
    )

# --- iroh: native DLL + Python glue + data files --------------------------
datas, binaries, hiddenimports = collect_all("iroh")

# --- pywebview (embedded WebView2 window); dynamic imports need collecting ----
_wv_datas, _wv_binaries, _wv_hidden = collect_all("webview")
datas += _wv_datas
binaries += _wv_binaries
hiddenimports += _wv_hidden
for _mod in ("clr_loader", "bottle", "pythonnet"):
    try:
        _d, _b, _h = collect_all(_mod)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _e:  # pragma: no cover
        print(f"[spec] collect_all({_mod}) failed: {_e!r}")

# --- bundle the built SPA: one exe serves the whole app --------------------
frontend_datas = [(str(FRONTEND_DIST), "frontend/dist")]

a = Analysis(
    [str(BACKEND / "packaged_launcher.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas + frontend_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# OneFile: everything (scripts + binaries + datas) is packed into the EXE and
# extracted to a temp dir at launch; `paths.py` reads `sys._MEIPASS` for the
# bundled SPA and puts persistent data next to IrohChat.exe.
#
# console=False (windowed): no black console box by default. `--console` still
# works — packaged_launcher spawns a real terminal window at runtime when the
# flag is passed, so debug output stays available on demand.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="IrohChat",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # disable UPX by default: iroh_ffi.dll is already compressed
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # windowed app; --console re-opens a terminal at runtime
    icon=str(SPEC_DIR / "assets" / "app_icon.ico"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
