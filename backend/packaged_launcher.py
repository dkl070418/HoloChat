"""PyInstaller single-exe entry point with an embedded WebView2 window.

Starts the FastAPI backend (same io as run.py) and opens a native WebView2
window pointing at the local SPA — no external browser needed. Falls back to
printing the URL if WebView2 is unavailable, so the app stays usable.

Usage:
    IrohChat.exe [port]
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

import uvicorn

# make `backend/` importable when run from source (PyInstaller sets pathex already)
_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# import the package so its modules are collected as part of the bundle
from app.main import app  # noqa: F401 (app is used below); also triggers iroh node setup
from app.hub import hub


def _silence_connection_reset_noise() -> None:
    """Mute the well-known Windows Proactor shutdown noise.

    On close, WebView2's socket dies with WinError 10054 while asyncio's
    Proactor event loop is still finalizing transports; the resulting
    'Exception in callback _ProactorBasePipeTransport._call_connection_lost'
    traceback is harmless. Patch the loop's exception handler to swallow it.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return

    def _handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return  # remote closed on us during teardown — expected
        loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)


def _open_console() -> None:
    """Spawn a real terminal window and redirect our stdout/stderr into it.

    Used with the windowed (console=False) build via `IrohChat.exe --console`:
    no black box by default, but full debug output when requested.
    """
    if os.name != "nt":
        return
    # allocate a console to THIS process and rebind the standard handles to it
    import ctypes
    k32 = ctypes.windll.kernel32
    if not k32.AllocConsole():
        return  # already has a console (e.g. launched from PowerShell)
    try:
        sys.stdout.flush(); sys.stderr.flush()
    except Exception:
        pass
    for name, mode in (("CONOUT$", "w"), ("CONIN$", "r")):
        try:
            pyh = open(name, mode, encoding="utf-8", errors="replace",
                       buffering=1 if mode == "w" else -1)
        except Exception:
            continue
        if name == "CONOUT$":
            sys.stdout = pyh
            sys.stderr = open(name, "w", encoding="utf-8", errors="replace", buffering=1)
        else:
            sys.stdin = pyh


def _run_backend(server: uvicorn.Server) -> None:
    """Run the uvicorn server (blocks) inside a worker thread."""
    try:
        server.run()
    except Exception as e:  # pragma: no cover - defensive
        print(f"[error] backend exited: {e!r}", flush=True)
    finally:
        # install after the loop exists (server.run creates/sets it)
        _silence_connection_reset_noise()


def main() -> None:
    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    except ValueError:
        port = 8000

    # LAN debug mode: `IrohChat.exe <port> --lan` binds 0.0.0.0 so other
    # devices on the same network can open the chat page in a browser.
    # Default stays loopback-only (safer). The WebView window always uses
    # 127.0.0.1 regardless.
    lan_mode = "--lan" in sys.argv
    bind_host = "0.0.0.0" if lan_mode else "127.0.0.1"

    # Console window: the exe is built windowed (no black box). `--console`
    # re-opens a real terminal at runtime and redirects stdout/stderr into it,
    # so node credentials and debug output stay available on demand.
    if "--console" in sys.argv:
        _open_console()

    # Windowed (console=False) builds have sys.stdout/sys.stderr = None, which
    # crashes uvicorn's logging setup ('NoneType' has no attribute 'isatty').
    # Point them at devnull unless a console was just allocated above.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    # uvicorn's default formatter also touches sys.stdin via colour detection
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r")

    config = uvicorn.Config(app, host=bind_host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    backend_thread = threading.Thread(target=_run_backend, args=(server,), daemon=True)
    backend_thread.start()

    url = f"http://127.0.0.1:{port}"
    print(f"[start] Iroh P2P Chat backend on {url}", flush=True)
    if lan_mode:
        print("[start] LAN mode ON — other devices can open http://<this-pc-ip>:" + str(port), flush=True)
    print("[start] opening WebView2 window…", flush=True)

    # ---- native window via WebView2 (pywebview) ----
    try:
        import webview
        win = webview.create_window(
            "HoloChat",
            url=url,
            width=1280,
            height=800,
            min_size=(900, 600),
            background_color="#1e1f22",
        )
        # when the window is closed, stop the backend server so the process exits
        def _on_closed():
            print("[exit] window closed, shutting down backend…", flush=True)
            try:
                # 1) politely close every frontend WebSocket first, so uvicorn's
                #    shutdown doesn't try to close already-dead sockets (which
                #    raised InvalidState / ConnectionResetError tracebacks).
                fut = asyncio.run_coroutine_threadsafe(
                    hub.shutdown(), server.config.loop)
                try:
                    fut.result(timeout=3)
                except Exception:
                    pass
                # 2) then ask the server to exit
                server.should_exit = True
            except Exception:
                pass

        def _defer_close_hook():
            try:
                win.events.closed += _on_closed
            except Exception as e:
                print(f"[warn] close hook unavailable: {e!r}", flush=True)

        import threading as _t
        _t.Timer(0.5, _defer_close_hook).start()

        webview.start(debug=False)
    except Exception as e:
        # WebView2 unavailable (e.g. old EdgeHTML-only Windows 10 without the
        # Evergreen WebView2 Runtime): don't strand the user on a console —
        # open the system default browser automatically, backend stays alive.
        print(f"[warn] WebView2 window failed ({e!r}) — opening {url} in your browser.", flush=True)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as be:
            print(f"[warn] could not auto-open browser ({be!r}); open {url} manually.", flush=True)
        # keep backend alive so the user can browse: wait forever
        try:
            while True:
                threading.Event().wait(3600)
        except KeyboardInterrupt:
            pass
    finally:
        try:
            server.should_exit = True
            backend_thread.join(timeout=3)
        except Exception:
            pass


if __name__ == "__main__":
    main()