"""WebSocket hub: fan events to all connected frontend clients.

Used by both the iroh network layer (incoming messages, progress, presence)
and FastAPI (send endpoints) to push real-time updates.
"""
from typing import List, Dict, Any
from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._clients: List[WebSocket] = []

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)

    def unregister(self, ws: WebSocket) -> None:
        if ws in self._clients:
            self._clients.remove(ws)

    async def shutdown(self) -> None:
        """Close every frontend WebSocket politely (server-side close handshake).

        Called by packaged_launcher before stopping uvicorn, so the window-close
        path doesn't leave half-open sockets that make uvicorn's own shutdown
        raise InvalidState/10054 tracebacks.
        """
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()

    async def broadcast(self, event: str, payload: Dict[str, Any]) -> None:
        msg = {"event": event, **payload}
        dead: List[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)

    def count(self) -> int:
        return len(self._clients)


hub = Hub()
