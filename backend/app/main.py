"""FastAPI entrypoint exposing the REST + WebSocket surface that the SPA consumes."""
from __future__ import annotations

import sys
import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import store
from .hub import hub
from .iroh_net import node, DOWNLOAD_DIR, parse_peer_string, addr_to_share_string
from .models import (SendTextReq, SavePeerReq, SetIdentityReq, CreateGroupReq,
                     GroupMemberReq, GroupTextReq, ProbeReq,
                     GroupInviteReq, GroupAcceptReq, GroupLeaveReq, ImportSecretReq,
                     FriendRequestReq, FriendRequestActionReq)
from .paths import FRONTEND_DIST

def _arg_port(default: int = 8000) -> int:
    """First purely-numeric CLI arg is the port; flags like --lan are skipped.

    (packaged_launcher passes the port through; module-level int(sys.argv[1])
    used to crash on `IrohChat.exe --lan` because '--lan' isn't numeric.)
    """
    for a in sys.argv[1:]:
        if a.isdigit():
            return int(a)
    return default


PORT = _arg_port()

app = FastAPI(title="HoloChat API")

# The SPA runs on a different origin during dev; allow it explicitly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    store.init_db()
    await node.start()
    info = node.info()
    print(f"\n[OK] Iroh node ready on port {PORT}")
    print(f"  Node ID : {info.get('id_short')}...")
    print(f"  Credential : {info.get('addr')}\n", flush=True)


@app.on_event("shutdown")
async def shutdown():
    await node.close()


# --------------------------------------------------------------------------
# info / topology
# --------------------------------------------------------------------------
@app.get("/api/info")
async def get_info():
    return node.info()


@app.get("/api/credential/short")
async def get_short_credential():
    """Return the short ``iroh1:...`` compact credential for easy sharing.

    ``short`` is null until the home relay is connected — encoding before that
    would produce an undialable bare Node ID packed as iroh1:.
    """
    addr = node.ep.addr()
    relay = addr.relay_url()
    return {
        "short": addr_to_share_string(addr) if relay else None,
        "full": str(addr),
        "relay_ready": bool(relay),
        "relay_url": relay,
    }


@app.post("/api/credential/decode")
async def decode_credential_endpoint(req: ProbeReq):
    """Decode any credential format and return the node_id + relay info."""
    try:
        target = parse_peer_string(req.addr)
        return {"peer_id": str(target.id()), "relay_url": target.relay_url()}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/relays")
async def get_relays():
    return {"relays": node.relays()}


@app.get("/api/connections")
async def get_connections():
    return {"connections": node.outgoing_connections()}


# --------------------------------------------------------------------------
# peers (contacts)
# --------------------------------------------------------------------------
@app.get("/api/peers")
async def list_peers():
    # Contacts list = ONLY explicitly-added peers. Auto-remembered peers (channel
    # members, inbound message senders, heartbeat connections) stay in the store
    # for reconnect/fan-out but never show up here -- that was the "mystery user"
    # bug (a peer you never added, or deleted, reappearing in your contacts).
    return {"peers": store.list_contacts()}


@app.post("/api/peers")
async def save_peer(req: SavePeerReq):
    peer = store.upsert_peer(
        req.peer_id, alias=req.alias, avatar=req.avatar,
        last_addr=req.last_addr,
        favorite=(bool(req.favorite) if req.favorite is not None else None),
        contact=True,   # explicit user action -> this peer IS a contact
    )
    # A contact was just added/updated with a dialable addr: reach out and pull
    # the remote's nickname/avatar so it shows up without typing a note by hand.
    # No-op (background, exception-safe) when the peer is offline — identity then
    # syncs on the first real message.
    if req.last_addr:
        asyncio.create_task(node.fetch_remote_identity(req.last_addr))
    return {"peer": peer}


@app.post("/api/peers/probe")
async def peer_probe(req: ProbeReq):
    """Dial a peer and run an identity handshake to pull its current
    nickname/avatar so the add-contact dialog can show them while (or before)
    the user confirms. Returns empty fields when the peer is offline/unreachable."""
    try:
        peer_id = str(parse_peer_string(req.addr).id())
    except Exception:
        return {"peer_id": None, "alias": None, "avatar": None}
    # Fire the handshake in the background — fetch_remote_identity only *sends*
    # the profile; the remote's reply arrives asynchronously through the receive
    # loop and is written to the store. So poll the store until the reply lands
    # (or we time out so the dialog never hangs on an unreachable peer).
    asyncio.create_task(node.fetch_remote_identity(req.addr))
    alias = avatar = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        p = store.get_peer(peer_id)
        if p:
            alias = p.get("alias")
            avatar = p.get("avatar")
            if alias or avatar:
                break
        await asyncio.sleep(0.25)
    return {"peer_id": peer_id, "alias": alias, "avatar": avatar}


@app.delete("/api/peers/{peer_id}")
async def delete_peer(peer_id: str):
    deleted = store.delete_peer(peer_id)
    return {"status": "ok", "deleted": deleted}


# --------------------------------------------------------------------------
# friend requests
# --------------------------------------------------------------------------
@app.get("/api/friend_requests")
async def list_friend_requests(status: str = None):
    """List incoming friend requests for the current user."""
    self_id = str(node.ep.id()) if node.ep else None
    if not self_id:
        return {"requests": []}
    return {"requests": store.list_friend_requests(self_id, status=status)}


@app.get("/api/friend_requests/sent")
async def list_sent_friend_requests(status: str = None):
    """List outgoing friend requests sent by the current user."""
    self_id = str(node.ep.id()) if node.ep else None
    if not self_id:
        return {"requests": []}
    return {"requests": store.list_sent_friend_requests(self_id, status=status)}


@app.post("/api/friend_requests/send")
async def send_friend_request(req: FriendRequestReq):
    """Send a friend request to a peer. Saves them as a contact and sends
    a friend_request message so their UI shows an accept/reject prompt."""
    self_id = str(node.ep.id()) if node.ep else None
    if not self_id:
        return JSONResponse(status_code=500, content={"status": "error", "detail": "node not ready"})

    # Resolve the dialable address
    addr = req.addr
    if not addr:
        remembered = store.get_peer(req.peer_id) or {}
        addr = remembered.get("last_addr")
    if not addr:
        return JSONResponse(status_code=400, content={"status": "error", "detail": "no address for peer"})

    # Save locally as a contact
    store.upsert_peer(req.peer_id, last_addr=addr, contact=True)
    # Record the outgoing request
    store.save_friend_request(self_id, req.peer_id,
                              from_alias=node._alias,
                              from_avatar=node._avatar)
    # Send the friend_request message over P2P
    sent = False
    try:
        await node.send_friend_request(addr)
        sent = True
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)})
    return {"status": "ok", "sent": sent}


@app.post("/api/friend_requests/accept")
async def accept_friend_request(req: FriendRequestActionReq):
    """Accept an incoming friend request: mark them as a contact, notify the
    sender via P2P, and return the updated request."""
    self_id = str(node.ep.id()) if node.ep else None
    if not self_id:
        return JSONResponse(status_code=500, content={"status": "error", "detail": "node not ready"})

    store.update_friend_request(req.from_peer_id, self_id, "accepted")
    # Add the requester as a contact
    addr = req.addr
    if not addr:
        remembered = store.get_peer(req.from_peer_id) or {}
        addr = remembered.get("last_addr")
    store.upsert_peer(req.from_peer_id, last_addr=addr, contact=True)

    # Notify the sender that we accepted
    if addr:
        try:
            await node.send_friend_request_accept(addr)
        except Exception:
            pass

    return {"status": "ok", "request": store.get_friend_request(req.from_peer_id, self_id)}


@app.post("/api/friend_requests/reject")
async def reject_friend_request(req: FriendRequestActionReq):
    """Reject an incoming friend request: mark it rejected and notify the sender."""
    self_id = str(node.ep.id()) if node.ep else None
    if not self_id:
        return JSONResponse(status_code=500, content={"status": "error", "detail": "node not ready"})

    store.update_friend_request(req.from_peer_id, self_id, "rejected")

    # Notify the sender that we rejected
    addr = req.addr
    if not addr:
        remembered = store.get_peer(req.from_peer_id) or {}
        addr = remembered.get("last_addr")
    if addr:
        try:
            await node.send_friend_request_reject(addr)
        except Exception:
            pass

    return {"status": "ok", "request": store.get_friend_request(req.from_peer_id, self_id)}


# --------------------------------------------------------------------------
# identity (nickname / avatar) - broadcast to peers on next message
# --------------------------------------------------------------------------
@app.post("/api/identity")
async def set_identity(req: SetIdentityReq):
    node.set_identity(**req.model_dump(exclude_unset=True))
    return {"status": "ok", "identity": {"alias": node._alias, "avatar": node._avatar}}


# -- identity / secret-key setup -------------------------------------------
@app.get("/api/identity/status")
async def identity_status():
    """First-run guidance: whether a persistent secret key exists and whether the
    node is currently running a throwaway (un-persisted) identity."""
    return {
        "secret_key_exists": node.secret_key_exists(),
        "identity_pending": bool(getattr(node, "_identity_pending", False)),
    }


@app.post("/api/identity/generate")
async def identity_generate():
    """Generate a brand-new persistent secret key. Takes effect after restart."""
    key = node.generate_new_secret()
    if key is None:
        return JSONResponse(status_code=500, content={"status": "error", "detail": "failed to write key"})
    return {"status": "ok", "generated": True, "restart_required": True}


@app.post("/api/identity/import")
async def identity_import(req: ImportSecretReq):
    """Import an existing secret key (Base64 or raw hex) as this node's identity.
    Takes effect after restart."""
    key = node.import_secret(req.key)
    if key is None:
        return JSONResponse(status_code=400, content={"status": "error", "detail": "invalid secret key"})
    return {"status": "ok", "imported": True, "restart_required": True}


@app.get("/api/identity/export")
async def identity_export():
    """Export the current persistent secret key as Base64 (for backup/migration)."""
    key = node.export_secret()
    if key is None:
        return JSONResponse(status_code=404, content={"status": "error", "detail": "no persistent key"})
    return {"status": "ok", "key": key}


# --------------------------------------------------------------------------
# groups (multi-person rooms) - PRD: point-to-point mesh broadcast
# --------------------------------------------------------------------------
@app.get("/api/groups")
async def list_groups():
    return {"groups": store.list_groups()}


@app.post("/api/groups")
async def create_group(req: CreateGroupReq):
    owner = str(node.ep.id()) if node.ep else None
    g = store.create_group(req.name, topic=req.topic, owner=owner)
    if owner:
        # the creator is a member too (sees a 👑 badge + a correct member count)
        store.add_group_member(g["id"], owner)
    return {"group": g}


@app.post("/api/groups/member")
async def group_add_member(req: GroupMemberReq):
    # track the member's addr so fan-out can reach it
    store.upsert_peer(req.peer_id, last_addr=req.addr if req.addr else None)
    store.add_group_member(req.group_id, req.peer_id)
    return {"status": "ok", "group": store.get_group(req.group_id),
            "members": store.group_members(req.group_id)}


@app.post("/api/groups/member/remove")
async def group_remove_member(req: GroupMemberReq):
    """Remove a member from a channel. Only the channel owner (creator) may kick;
    the kicked peer is notified so their UI drops the channel, and the other
    members' rosters are updated too."""
    self_id = str(node.ep.id()) if node.ep else None
    owner = store.group_owner(req.group_id)
    if owner and owner != self_id:
        return JSONResponse(status_code=403, content={"status": "error",
                                                      "detail": "只有频道创建者可以移除成员"})
    removed = store.remove_group_member(req.group_id, req.peer_id)
    if removed:
        # tell the kicked peer they were removed -> they delete the channel locally
        addr = node.peer_addr(req.peer_id) or (store.get_peer(req.peer_id) or {}).get("last_addr")
        if addr:
            try:
                await node.send_group_removed(addr, req.group_id)
            except Exception:
                pass
        # drop the kicked peer from every other member's roster
        for m in store.group_members(req.group_id):
            pid = m["peer_id"]
            if pid == self_id:
                continue
            a = node.peer_addr(pid) or m.get("last_addr")
            if a:
                try:
                    await node.send_group_leave(a, req.group_id, subject_id=req.peer_id)
                except Exception:
                    pass
    return {"status": "ok", "removed": removed,
            "members": store.group_members(req.group_id)}


@app.post("/api/groups/invite")
async def group_invite(req: GroupInviteReq):
    """Invite a peer to one of our channels. We register them as a member locally
    (so our fan-out can reach them) and push a group_invite message so their UI
    shows an accept/ignore prompt. They only truly join by accepting."""
    # dialable addr falls back to the peer's remembered address when not provided
    addr = req.addr
    if not addr:
        remembered = store.get_peer(req.peer_id) or {}
        addr = remembered.get("last_addr")
    store.add_group_member(req.group_id, req.peer_id)
    if req.addr:
        store.upsert_peer(req.peer_id, last_addr=req.addr)
    sent = False
    if addr:
        try:
            await node.send_group_invite(addr, req.group_id, req.name, req.topic)
            sent = True
        except Exception as e:
            return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)})
    return {"status": "ok", "sent": sent,
            "group": store.get_group(req.group_id),
            "members": store.group_members(req.group_id)}


@app.post("/api/groups/accept")
async def group_accept(req: GroupAcceptReq):
    """Accept a remote's channel invitation: create the group with the inviter's
    id and add ourselves as a member, so the shared room_id now matches on both
    ends. We also add the inviter and ask for the current roster, so we learn
    everyone already in the channel (and can send/list them) — mesh membership
    sync, no central server."""
    self_id = str(node.ep.id()) if node.ep else None
    # the channel owner is whoever invited us (the creator), NOT ourselves — so a
    # joiner can't later kick members they never owned.
    owner = req.inviter_id or self_id
    g = store.ensure_group(req.group_id, req.name, req.topic, owner=owner)
    store.add_group_member(req.group_id, self_id)
    if owner != self_id and req.inviter_id:
        inv_addr = (req.inviter_addr
                    or (store.get_peer(req.inviter_id) or {}).get("last_addr")
                    or node.peer_addr(req.inviter_id))
        if inv_addr:
            # the inviter is a member we can now reach
            store.add_group_member(req.group_id, req.inviter_id)
            store.upsert_peer(req.inviter_id, last_addr=inv_addr)
            member = {"peer_id": self_id,
                      "alias": node._alias or None,
                      "avatar": node._avatar,
                      "addr": str(node.ep.addr()) if node.ep else None}
            # announce our join + request the roster (the reply arrives async via
            # the receive loop and triggers a frontend refresh)
            asyncio.create_task(node.send_group_join(inv_addr, req.group_id, member))
    return {"status": "ok", "group": g,
            "members": store.group_members(req.group_id)}


@app.post("/api/groups/leave")
async def group_leave(req: GroupLeaveReq):
    """Leave a channel: broadcast our departure to the other members (so they
    drop us from their roster), then remove the channel locally."""
    self_id = str(node.ep.id()) if node.ep else None
    for m in store.group_members(req.group_id):
        pid = m["peer_id"]
        if pid == self_id:
            continue
        addr = node.peer_addr(pid) or m.get("last_addr")
        if addr:
            try:
                await node.send_group_leave(addr, req.group_id, subject_id=self_id)
            except Exception:
                pass
    store.delete_group(req.group_id)
    return {"status": "ok", "left": True}


@app.post("/api/groups/send_text")
async def group_send_text(req: GroupTextReq):
    try:
        results = await node.send_group_text(req.group_id, req.content, reply_to=req.reply_to)
        return {"status": "ok", "deliveries": results}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)})



@app.post("/api/groups/send_file")
async def group_send_file(group_id: str = "", file: UploadFile = File(...)):
    try:
        data = await file.read()
        results = await node.send_group_file(group_id, file.filename or "file", data)
        return {"status": "ok", "deliveries": results}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)})


@app.get("/api/groups/{gid}/members")
async def group_get_members(gid: str):
    return {"members": store.group_members(gid)}


@app.delete("/api/groups/{gid}")
async def delete_group(gid: str):
    deleted = store.delete_group(gid)
    return {"status": "ok", "deleted": deleted}


# --------------------------------------------------------------------------
# transfer records (files table)
# --------------------------------------------------------------------------
@app.get("/api/files")
async def list_file_records(peer_id: str = None):
    return {"files": store.list_files(peer_id)}


# --------------------------------------------------------------------------
# history / send
# --------------------------------------------------------------------------
@app.get("/api/history")
async def get_history(peer_id: str = None, room_id: str = None):
    messages = store.load_messages(peer_id, room_id=room_id)
    # Received file messages are served from the local download dir; attach a
    # working download/preview URL (the DB stores no url, so derive it here so
    # the UI can show download/preview even after a reload).
    for m in messages:
        # Attach a working preview/download URL for file messages whose bytes we
        # hold locally: received files live in the download dir, and outbound
        # sends keep a sender copy there too (keep_sender_copy) so the sender
        # can preview its own uploads, even after a reload.
        if m.get("msg_type") == "file" and m.get("filename"):
            if (DOWNLOAD_DIR / Path(m["filename"]).name).exists():
                m["file_url"] = f"/api/files/{Path(m['filename']).name}"
    return {"messages": messages}


@app.post("/api/send_text")
async def api_send_text(req: SendTextReq):
    try:
        result = await node.send_text(req.peer_addr, req.content, reply_to=req.reply_to)
        return {"status": "ok", "message": result}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)})


@app.post("/api/send_file")
async def api_send_file(peer_addr: str = "", file: UploadFile = File(...)):
    try:
        data = await file.read()
        result = await node.send_file(peer_addr, file.filename or "file", data)
        # keep a local copy so the SENDER can preview/re-download its own file
        result["file_url"] = node.keep_sender_copy(file.filename or "file", data)
        return {"status": "ok", "message": result}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)})


# --------------------------------------------------------------------------
# received-file serving (preview / playback)
# --------------------------------------------------------------------------
@app.get("/api/files/{filename}")
async def get_file(filename: str):
    safe = Path(filename).name
    path = DOWNLOAD_DIR / safe
    if not path.exists():
        return JSONResponse(status_code=404, content={"detail": "not found"})
    media_type = _guess_media(safe)
    return FileResponse(path, media_type=media_type, filename=safe)


def _guess_media(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        ".bmp": "image/bmp",
        ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
        ".m4a": "audio/mp4", ".flac": "audio/flac",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


# --------------------------------------------------------------------------
# websocket
# --------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await hub.register(ws)
    # push current snapshot on connect
    try:
        await ws.send_json({"event": "node_info", **node.info()})
    except Exception:
        pass
    try:
        while True:
            msg = await ws.receive_text()
            # client->server control messages (kept minimal)
            import json as _json
            try:
                data = _json.loads(msg)
                ev = data.get("type")
                if ev == "get_status":
                    for peer_id in list(store.list_peers()):
                        pid = peer_id["peer_id"]
                        ls = node.link_status(pid)
                        await ws.send_json({"event": "presence",
                                            "peer_id": pid,
                                            "online": pid in node._connections,
                                            "link_type": ls["link_type"],
                                            "rtt": ls["rtt"],
                                            "ts": ls["ts"]})
            except Exception:
                pass
    except WebSocketDisconnect:
        hub.unregister(ws)
    except Exception:
        hub.unregister(ws)


# --------------------------------------------------------------------------
# bundled SPA (single-exe distribution): serve frontend/dist at the root.
# Registered LAST so /api and /ws keep precedence. Harmless under source-run
# (dev uses the Vite server on :5173); only relevant once PyInstaller packs the
# dist inside the exe. When dist is absent (not built) these routes are skipped.
# --------------------------------------------------------------------------
if FRONTEND_DIST.exists():
    _dist_assets = FRONTEND_DIST / "assets"
    if _dist_assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_dist_assets)), name="assets")

    @app.get("/", include_in_schema=False)
    async def _serve_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_spa(full_path: str):
        # serve a real static file if it exists (e.g. /favicon.ico),
        # otherwise fall back to index.html so client-side routing works
        candidate = (FRONTEND_DIST / full_path).resolve()
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
