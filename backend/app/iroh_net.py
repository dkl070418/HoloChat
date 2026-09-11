"""Iroh P2P core: endpoint lifecycle, send/receive, presence heartbeat,
link-status detection and relay/topology tracking.

This module owns the single `iroh.Endpoint` for the process and exposes
async helpers used by the FastAPI routes and the WebSocket hub.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import iroh
from . import store
from .hub import hub
from .paths import DOWNLOAD_DIR, DATA_DIR

ALPN = b"iroh-p2p-chat/1.0"
CHUNK = 64 * 1024
# contact-presence probing: dial contacts with no live connection so online
# status stays accurate without waiting for a user action
PROBE_INTERVAL_SECS = 10   # loop cadence
PROBE_RETRY_SECS = 45      # min gap between redials of an unreachable contact


# ---------------------------------------------------------------------------
# peer string parsing — we accept both the raw `str(addr())` form and a node
# ticket (`endpoint...` / `node...`) so anything the user copies in works.
# ---------------------------------------------------------------------------
def parse_peer_string(s: str) -> iroh.EndpointAddr:
    """Turn a user-pasted peer string into an `EndpointAddr`.

    Supports:
      * ``iroh1:<base64>`` compact credential (new canonical format)
      * ``str(endpoint.addr())``  e.g. ``<nodeid> [relay=<url>] [addrs=[ip:port, ...]]``
      * a node/endpoint ticket      e.g. ``endpointacqld...``
    """
    s = s.strip()
    if not s:
        raise ValueError("empty peer address")
    # compact iroh1: credential — decode back to the legacy form and re-parse
    if s.startswith("iroh1:"):
        legacy = decode_credential(s)
        if legacy:
            return parse_peer_string(legacy)
        raise ValueError("invalid iroh1 credential")
    # ticket path
    if s.startswith("endpoint") or s.startswith("node"):
        try:
            ticket = iroh.EndpointTicket.from_string(s)
            return ticket.endpoint_addr()
        except Exception:
            pass  # fall through to raw parsing
    # raw addr path — parse manually (IPv6 brackets make a simple regex fragile)
    node = None
    relay = None
    addrs: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        # skip whitespace
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break
        if s.startswith("relay=", i):
            i += len("relay=")
            j = i
            while j < n and not s[j].isspace():
                j += 1
            relay = s[i:j]
            i = j
        elif s.startswith("addrs=[", i):
            i += len("addrs=[")
            depth = 1
            body = []
            while i < n and depth > 0:
                if s[i] == "[":
                    depth += 1
                elif s[i] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                body.append(s[i])
                i += 1
            i += 1  # consume closing ]
            for tok in "".join(body).split(","):
                tok = tok.strip()
                if tok:
                    addrs.append(tok)
        else:
            # leading token is the node id (64 hex chars)
            m = re.match(r"([0-9a-fA-F]{64})", s[i:])
            if m:
                node = m.group(1)
                i += len(node)
            else:
                # any other token (e.g. a stray word) — skip to next whitespace
                while i < n and not s[i].isspace():
                    i += 1
    if not node:
        raise ValueError(f"unrecognized peer format: {s[:40]}...")
    try:
        node_id = iroh.EndpointId.from_string(node)
    except Exception as e:
        raise ValueError(f"bad node id: {node[:16]}...") from e
    return iroh.EndpointAddr(node_id, relay, addrs)


def addr_to_share_string(addr: iroh.EndpointAddr) -> str:
    """Compact share credential for copy/paste — uses base64 encoding.

    Form: ``iroh1:<base64>`` — much shorter than the raw ``str(addr())``
    representation.  The payload is: 1-byte version + 32-byte node_id +
    null-terminated relay URL.  ``parse_peer_string`` handles both this
    compact format and the legacy ``<nodeid> relay=...`` form.
    """
    import base64 as _b64
    node = str(addr.id())
    relay = addr.relay_url() or ""
    # binary payload: version(1) + node_id(32) + relay_url(var, null-term)
    node_bytes = bytes.fromhex(node)
    relay_bytes = relay.encode("utf-8") + b"\x00"
    payload = b"\x01" + node_bytes + relay_bytes
    return "iroh1:" + _b64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_credential(encoded: str) -> Optional[str]:
    """Decode a ``iroh1:...`` compact credential back to a full address string.

    Returns the legacy ``<nodeid> relay=<url>`` string that ``parse_peer_string``
    already understands, or *None* if the input is invalid.
    """
    import base64 as _b64
    s = encoded.strip()
    if not s.startswith("iroh1:"):
        return None
    try:
        pad = s[6:] + "=" * (-len(s[6:]) % 4)
        data = _b64.urlsafe_b64decode(pad)
        if len(data) < 33 or data[0] != 0x01:
            return None
        node_hex = data[1:33].hex()
        relay_end = data.index(b"\x00", 33)
        relay = data[33:relay_end].decode("utf-8")
        parts = [node_hex]
        if relay:
            parts.append(f"relay={relay}")
        return " ".join(parts)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# node
# ---------------------------------------------------------------------------
class IrohNode:
    def __init__(self, secret_key_path: Optional[Path] = None) -> None:
        self.ep: Optional[iroh.Endpoint] = None
        self._connections: Dict[str, iroh.Connection] = {}   # peer_id -> conn (any: inbound overwrites possible)
        self._outgoing: set = set()                          # legacy: peer_ids we dialed, keep for compat
        self._outgoing_conns: Dict[str, iroh.Connection] = {}  # peer_id -> OUR outbound conn (send-safe only)
        self._peer_addr: Dict[str, str] = {}                 # peer_id -> addr string
        self._relays_cache: List[str] = []
        self._alias: str = ""
        self._avatar: Optional[str] = None
        self._identity_pending: bool = False
        # stable local-first identity: when a secret_key_path is provided, persist
        # the Ed25519 secret key there so the Node ID survives restarts. `None`
        # means a throwaway identity (random key) — used in tests.
        self._secret_key_path = secret_key_path
        # per-group peers we've already announced ourselves to (breaks the
        # roster/join handshake loop in the mesh membership sync)
        self._group_announced: Dict[str, set] = {}
        # peer_id -> last contact-probe attempt time (rate-limits redials)
        self._probe_ts: Dict[str, float] = {}

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        import secrets as _secrets_mod
        self._identity_pending = False
        if self._secret_key_path and not self._secret_key_path.exists():
            # No persisted key yet -> run with a throwaway identity and tell the
            # frontend to guide first-run setup (generate a new key or import an
            # existing one). Do NOT auto-persist here; the user decides.
            self._identity_pending = True
            secret_key = _secrets_mod.token_bytes(32)  # temp, not written to disk
        else:
            secret_key = self._load_or_create_secret_key()
        kwargs: Dict[str, Any] = dict(preset=iroh.preset_n0(), alpns=[ALPN])
        if secret_key is not None:
            kwargs["secret_key"] = secret_key
        self.ep = await iroh.Endpoint.bind(iroh.EndpointOptions(**kwargs))
        asyncio.create_task(self._accept_loop())
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._presence_probe_loop())
        self._refresh_relays()
        self._restore_identity()

    def _load_or_create_secret_key(self) -> Optional[bytes]:
        """Return a persisted Ed25519 secret key (stable Node ID) or None.

        A random 32-byte value is a valid Ed25519 secret seed, so we create one
        once and reuse it on every start. `secret_key_path=None` disables
        persistence (throwaway identity for tests).
        """
        if not self._secret_key_path:
            return None
        try:
            if self._secret_key_path.exists():
                data = self._secret_key_path.read_bytes()
                if len(data) in (32, 64):
                    return data
            import secrets
            key = secrets.token_bytes(32)
            self._secret_key_path.parent.mkdir(parents=True, exist_ok=True)
            self._secret_key_path.write_bytes(key)
            return key
        except Exception:
            return None

    # -- identity / secret-key management -----------------------------------
    def secret_key_path(self) -> Optional[Path]:
        return self._secret_key_path

    def secret_key_exists(self) -> bool:
        return bool(self._secret_key_path and self._secret_key_path.exists())

    def _write_secret(self, data: bytes) -> bool:
        """Atomically persist a raw secret key (32-byte seed or 64-byte pair)."""
        if not self._secret_key_path or len(data) not in (32, 64):
            return False
        try:
            self._secret_key_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._secret_key_path.with_suffix(".key.tmp")
            tmp.write_bytes(data)
            tmp.replace(self._secret_key_path)
            return True
        except Exception:
            return False

    def generate_new_secret(self) -> Optional[bytes]:
        """Generate a brand-new identity seed and persist it (replaces any old
        key). Takes effect after the node restarts with the new key."""
        import secrets
        key = secrets.token_bytes(32)
        return key if self._write_secret(key) else None

    def import_secret(self, encoded: str) -> Optional[bytes]:
        """Import a secret key from Base64 / raw-hex / raw 32-byte binary.

        Accepts:
          * Base64 text (44/88 chars) or hex text (64/128 chars)
          * raw binary bytes of the secret.key file (32 or 64 bytes) — browsers
            can't paste those, so the frontend reads the file as base64 and
            sends it prefixed with "b64:" to distinguish from key-text.
        """
        if not encoded:
            return None
        try:
            import base64
            enc = encoded.strip()
            # frontend file-picker path: raw file content already re-encoded as
            # base64 by the browser — decode it straight to bytes.
            if enc.startswith("b64:"):
                data = base64.b64decode(enc[4:], validate=False)
                if len(data) in (32, 64):
                    return data if self._write_secret(data) else None
                return None
            if len(enc) in (44, 88, 64, 128):
                enc += "=" * (-len(enc) % 4)
            try:
                data = base64.b64decode(enc, validate=True)
            except Exception:
                try:
                    data = bytes.fromhex(encoded)
                except Exception:
                    return None
            if len(data) not in (32, 64):
                return None
            return data if self._write_secret(data) else None
        except Exception:
            return None

    def export_secret(self) -> Optional[str]:
        """Return the current secret key as Base64 (for backup/migration), or
        None when no persisted key exists (e.g. a throwaway test identity)."""
        if not self._secret_key_path or not self._secret_key_path.exists():
            return None
        try:
            import base64
            return base64.b64encode(self._secret_key_path.read_bytes()).decode()
        except Exception:
            return None

    def _refresh_relays(self) -> None:
        self._relays_cache = self._relay_urls()

    def _restore_identity(self) -> None:
        """On startup, reload this node's own nickname/avatar from the contacts
        store (saved under our own id by set_identity). Without this, a restart
        resets _alias/_avatar to empty and the node "forgets" its identity."""
        try:
            me = store.get_peer(str(self.ep.id()))
            if me:
                if me.get("alias"):
                    self._alias = me["alias"]
                if me.get("avatar"):
                    self._avatar = me["avatar"]
        except Exception:
            pass

    def set_identity(self, **kwargs) -> None:
        """Set this node's nickname/avatar; carried on every message to peers.

        Only keys explicitly present in the request are applied, so callers can
        clear a field by sending its key (alias -> "" / avatar -> None) without
        clobbering the other field.
        """
        if "alias" in kwargs:
            self._alias = kwargs["alias"] or ""
        if "avatar" in kwargs:
            self._avatar = kwargs["avatar"] or None
        # persist our own identity in the contacts table under our own id
        try:
            store.upsert_peer(str(self.ep.id()), alias=self._alias, avatar=self._avatar)
        except Exception:
            pass
        # proactively push our fresh identity to every known peer (so the other
        # side sees the change immediately, not only when we next send a message)
        # and notify our own frontend clients to refresh.
        try:
            asyncio.create_task(self._broadcast_identity())
        except Exception:
            pass

    async def _broadcast_identity(self) -> None:
        """Fan out our current identity to all saved contacts (profile message)
        and tell every connected frontend to refresh."""
        try:
            await hub.broadcast("identity", {"peer_id": str(self.ep.id()),
                                             "alias": self._alias, "avatar": self._avatar})
        except Exception:
            pass
        seen: set = set()
        try:
            for p in store.list_peers():
                pid = p.get("peer_id")
                addr = p.get("last_addr")
                if not pid or not addr or pid == str(self.ep.id()) or addr in seen:
                    continue
                seen.add(addr)
                try:
                    await self.send_profile(addr)
                except Exception:
                    continue
        except Exception:
            pass

    def _identity_header(self) -> Dict[str, Any]:
        return {"sender_id": str(self.ep.id()), "alias": self._alias, "avatar": self._avatar}

    async def close(self) -> None:
        if self.ep is not None:
            try:
                await self.ep.close()
            except Exception:
                pass

    # -- info ---------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        if self.ep is None:
            return {}
        addr = self.ep.addr()
        node_id = str(self.ep.id())
        short = addr_to_share_string(addr)
        relay = addr.relay_url()
        return {
            "id": node_id,
            "id_short": self._short(node_id),
            # full dialable form (node + relay + direct addrs) — the reliable one
            "addr": str(addr),
            # compact iroh1: form (node + relay only). null until home relay is
            # up, because encoding before that yields an undialable bare Node ID.
            "addr_short": short if relay else None,
            "relay_ready": bool(relay),
            "relay_url": relay,
            "direct_addresses": list(addr.direct_addresses() or []),
            "downloads_dir": str(DOWNLOAD_DIR.resolve()),
            "alias": self._alias,
            "avatar": self._avatar,
            "identity_pending": bool(self._identity_pending),
            "secret_key_ready": self.secret_key_exists(),
            "ts": time.time(),
        }

    @staticmethod
    def _short(node_id: str) -> str:
        return node_id[:12] if len(node_id) > 12 else node_id

    def peer_addr(self, peer_id: str) -> Optional[str]:
        # rebuild share string from a tracked connection's remote id
        if peer_id in self._peer_addr:
            return self._peer_addr[peer_id]
        return None

    # -- accept incoming ----------------------------------------------------
    async def _accept_loop(self) -> None:
        while True:
            try:
                incoming = await self.ep.accept_next()
                if incoming is not None:
                    # modern iroh (>=1.0) handshake chain:
                    #   Incoming.accept() -> Accepting ; Accepting.connect() -> Connection
                    accepting = await incoming.accept()
                    conn = await accepting.connect()
                    asyncio.create_task(self._accept_streams(conn))
            except Exception:
                await asyncio.sleep(1)

    async def _accept_streams(self, conn: iroh.Connection) -> None:
        try:
            remote_id = str(conn.remote_id())
            self._connections[remote_id] = conn
            while True:
                bi = await conn.accept_bi()
                asyncio.create_task(self._handle_incoming(bi.recv(), remote_id))
        except Exception:
            pass
        finally:
            self._connections.pop(remote_id, None)

    async def _handle_incoming(self, recv: iroh.RecvStream, peer_id: str) -> None:
        try:
            header_len = int.from_bytes(await recv.read_exact(4), "big")
            header_bytes = await recv.read_exact(header_len)
            header = json.loads(header_bytes.decode())
            msg_type = header.get("type")
            room_id = header.get("room_id")

            # learn the remote's identity from any message header (P2P profile sync)
            self._apply_remote_identity(peer_id, header)
            # learn the sender's own dialable address so we can reply even when
            # this was an inbound connection (inbound conns carry no usable addr)
            self._learn_sender_addr(peer_id, header)

            if msg_type == "profile":
                # identity broadcast; record already upserted above. If the sender
                # asked for a reply, hand back our own profile so it gets ours too.
                if header.get("reply"):
                    try:
                        peer_addr = header.get("sender_addr") or self._peer_addr.get(peer_id)
                        if peer_addr:
                            await self.send_profile(peer_addr)
                    except Exception:
                        pass
                return

            if msg_type == "friend_request":
                # Someone wants to add us as a friend. Store the request and
                # notify our frontend so the user can accept/reject.
                try:
                    store.save_friend_request(
                        peer_id,
                        str(self.ep.id()),
                        from_alias=header.get("alias"),
                        from_avatar=header.get("avatar"),
                    )
                    await hub.broadcast("friend_request", {
                        "event": "friend_request",
                        "from_peer_id": peer_id,
                        "from_alias": header.get("alias") or self._short(peer_id),
                        "from_avatar": header.get("avatar"),
                        "from_addr": header.get("sender_addr") or self._peer_addr.get(peer_id),
                        "status": "pending",
                    })
                except Exception:
                    pass
                return

            if msg_type == "friend_request_accept":
                # The remote accepted our friend request. Mark it and notify frontend.
                try:
                    store.update_friend_request(str(self.ep.id()), peer_id, "accepted")
                    # Also add them as a contact so they appear in our list
                    store.upsert_peer(peer_id, contact=True)
                    await hub.broadcast("friend_request_accepted", {
                        "event": "friend_request_accepted",
                        "peer_id": peer_id,
                    })
                except Exception:
                    pass
                return

            if msg_type == "friend_request_reject":
                # The remote rejected our friend request. Mark it and notify frontend.
                try:
                    store.update_friend_request(str(self.ep.id()), peer_id, "rejected")
                    await hub.broadcast("friend_request_rejected", {
                        "event": "friend_request_rejected",
                        "peer_id": peer_id,
                    })
                except Exception:
                    pass
                return

            if msg_type == "group_invite":
                # A remote peer wants us to join their channel. Surface a prompt to
                # the frontend; the user decides whether to accept (which then
                # ensure_group + adds itself as a member) or ignore.
                try:
                    await hub.broadcast("group_invite", {
                        "group_id": header.get("group_id"),
                        "name": header.get("group_name", ""),
                        "topic": header.get("group_topic", ""),
                        "from_id": peer_id,
                        "from_addr": header.get("sender_addr") or self._peer_addr.get(peer_id),
                        "from_alias": header.get("alias") or self._short(peer_id),
                        "is_group_invite": True,
                    })
                except Exception:
                    pass
                return

            if msg_type == "group_join":
                # A peer joined (or confirmed their place in) one of OUR channels:
                # record them and reply with the roster so they learn everyone.
                room = header.get("group_id") or header.get("room_id")
                member = header.get("member") or {}
                if room and member.get("peer_id"):
                    store.merge_group_roster(room, [member])
                    try:
                        peer_addr = header.get("sender_addr") or self._peer_addr.get(peer_id)
                        if peer_addr:
                            await self.send_group_roster(peer_addr, room)
                    except Exception:
                        pass
                await self._notify_groups_changed()
                return

            if msg_type == "group_roster":
                # The remote answered our join with the full member list: merge it
                # so we can see everyone and fan-out to them. Then announce
                # ourselves to every OTHER member we just learned about, so the
                # whole mesh knows we're here (one-shot — their group_join handler
                # only replies, it never re-fans, so no loop).
                room = header.get("group_id") or header.get("room_id")
                members = header.get("members") or []
                if room:
                    store.merge_group_roster(room, members)
                    me = {"peer_id": str(self.ep.id()),
                          "alias": self._alias or None,
                          "avatar": self._avatar,
                          "addr": str(self.ep.addr()) if self.ep else None}
                    announced = self._group_announced.setdefault(room, set())
                    for m in store.group_members(room):
                        pid = m["peer_id"]
                        if pid == me["peer_id"] or pid in announced:
                            continue
                        a = self._peer_addr.get(pid) or m.get("last_addr")
                        if a:
                            announced.add(pid)
                            try:
                                await self.send_group_join(a, room, me)
                            except Exception:
                                pass
                await self._notify_groups_changed()
                return

            if msg_type == "group_leave":
                # A member left (or was removed from) one of our channels: drop that
                # peer from our roster. `peer_id` defaults to the sender.
                room = header.get("group_id") or header.get("room_id")
                gone = header.get("peer_id") or peer_id
                if room:
                    store.remove_group_member(room, gone)
                await self._notify_groups_changed()
                return

            if msg_type == "group_removed":
                # The owner kicked us out of a channel: delete it locally.
                room = header.get("group_id") or header.get("room_id")
                if room:
                    store.delete_group(room)
                await self._notify_groups_changed()
                return

            if msg_type == "text":
                content = header.get("content", "")
                reply_to = header.get("reply_to")
                mid = store.save_message(peer_id, "in", "text", content=content,
                                         reply_to=reply_to, room_id=room_id)
                await hub.broadcast("message", {
                    "id": mid, "peer_id": peer_id, "peer_id_short": self._short(peer_id),
                    "direction": "in", "msg_type": "text", "content": content,
                    "room_id": room_id, "created_at": time.time(), "reply_to": reply_to or None,
                })

            elif msg_type == "file":
                filename = header.get("filename", "file")
                filesize = header.get("filesize", 0)
                safe = Path(filename).name  # strip any path traversal
                save_path = DOWNLOAD_DIR / safe
                t0 = time.time()
                received = 0
                with open(save_path, "wb") as f:
                    remaining = filesize
                    while remaining > 0:
                        n = min(CHUNK, remaining)
                        chunk = await recv.read_exact(n)
                        f.write(chunk)
                        remaining -= len(chunk)
                        received += len(chunk)
                        await self._emit_progress(peer_id, safe, received, filesize, t0, direction="in")
                mid = store.save_message(peer_id, "in", "file", filename=safe,
                                         filesize=filesize, room_id=room_id)
                try:
                    store.save_file_record(
                        peer_id, "in", safe, filesize,
                        sha256=self._sha256_file(save_path),
                        stored_path=str(save_path), status="complete", room_id=room_id,
                    )
                except Exception:
                    pass
                await hub.broadcast("message", {
                    "id": mid, "peer_id": peer_id, "peer_id_short": self._short(peer_id),
                    "direction": "in", "msg_type": "file", "filename": safe,
                    "filesize": filesize, "room_id": room_id, "file_url": f"/api/files/{safe}",
                    "created_at": time.time(),
                })
        except Exception as e:
            print(f"[iroh] receive error: {e!r}")

    def _learn_sender_addr(self, peer_id: str, header: Dict[str, Any]) -> None:
        """Auto-learn the sender's own dialable addr from a message header so we
        can reply, even when this message arrived over an inbound connection."""
        addr = header.get("sender_addr")
        if addr:
            try:
                store.touch_peer(peer_id, addr=addr)
                self._peer_addr[peer_id] = addr
            except Exception:
                pass

    def _apply_remote_identity(self, peer_id: str, header: Dict[str, Any]) -> None:
        alias = header.get("alias")
        avatar = header.get("avatar")
        # ignore empty profile fields: a blank alias/avatar means "not set", so
        # we neither overwrite a previously learned value nor fan out noise.
        has_alias = bool(alias)
        has_avatar = bool(avatar)
        if not (has_alias or has_avatar):
            return
        try:
            store.upsert_peer(peer_id,
                              alias=alias if has_alias else (store.get_peer(peer_id) or {}).get("alias"),
                              avatar=avatar if has_avatar else (store.get_peer(peer_id) or {}).get("avatar"))
        except Exception:
            pass
        # tell our frontend clients a contact's identity changed so they
        # refresh the contact list / message bubbles immediately.
        try:
            asyncio.create_task(hub.broadcast(
                "identity", {"peer_id": peer_id,
                             "alias": alias if has_alias else None,
                             "avatar": avatar if has_avatar else None}))
        except Exception:
            pass

    @staticmethod
    def _sha256_file(path: Path) -> str:
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()

    # -- send ---------------------------------------------------------------
    def _base_header(self, msg_type: str, room_id: Optional[str] = None) -> Dict[str, Any]:
        h = {"type": msg_type, "room_id": room_id}
        h.update(self._identity_header())
        # advertise our own dialable endpoint so the receiver can automatically
        # learn our last_addr and reply — fixes "remote sent to me first, but I
        # can't send back" (inbound connections carry no usable peer address).
        try:
            h["sender_addr"] = str(self.ep.addr())
        except Exception:
            pass
        return h

    async def send_text(self, peer_addr_str: str, content: str, reply_to: Optional[int] = None,
                        room_id: Optional[str] = None, save: bool = True) -> Dict[str, Any]:
        target = parse_peer_string(peer_addr_str)
        peer_id = str(target.id())
        header = self._base_header("text", room_id=room_id)
        header["content"] = content
        header["reply_to"] = reply_to
        await self._send(peer_addr_str, header, peer_id=peer_id)
        # save=False for group fan-out: the group sender persists ONE own row
        # (see send_group_text), per-member deliveries are wire-only.
        mid = (store.save_message(peer_id, "out", "text", content=content,
                                  reply_to=reply_to, room_id=room_id)
               if save else None)
        self._remember(peer_id, peer_addr_str)
        return {"id": mid, "peer_id": peer_id, "peer_id_short": self._short(peer_id),
                "direction": "out", "msg_type": "text", "content": content,
                "room_id": room_id, "created_at": time.time(), "reply_to": reply_to or None}

    async def send_file(self, peer_addr_str: str, filename: str, data: bytes,
                        room_id: Optional[str] = None, save: bool = True) -> Dict[str, Any]:
        safe = Path(filename).name
        target = parse_peer_string(peer_addr_str)
        peer_id = str(target.id())
        header = self._base_header("file", room_id=room_id)
        header["filename"] = safe
        header["filesize"] = len(data)
        await self._send(peer_addr_str, header, file_bytes=data, peer_id=peer_id, filename=safe)
        # save=False for group fan-out (sender row is persisted once by the
        # caller); for DM the row is saved here and the sender copy + file
        # record are persisted by main.py's keep_sender_copy.
        mid = (store.save_message(peer_id, "out", "file", filename=safe,
                                  filesize=len(data), room_id=room_id)
               if save else None)
        self._remember(peer_id, peer_addr_str)
        return {"id": mid, "peer_id": peer_id, "peer_id_short": self._short(peer_id),
                "direction": "out", "msg_type": "file", "filename": safe,
                "filesize": len(data), "room_id": room_id, "file_url": None,
                "created_at": time.time()}

    def keep_sender_copy(self, filename: str, data: bytes,
                         room_id: Optional[str] = None) -> str:
        """Persist a local copy of an outbound file so THIS node (the sender)
        can preview / re-download it later via /api/files/<name>, exactly like a
        received file. Group fan-out calls this once (not once per member).
        Returns the /api/files URL."""
        safe = Path(filename).name
        save_path = DOWNLOAD_DIR / safe
        tmp_path = save_path.with_suffix(save_path.suffix + ".tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(save_path)
        try:
            store.save_file_record(
                str(self.ep.id()), "out", safe, len(data),
                sha256=self._sha256_file(save_path),
                stored_path=str(save_path), status="complete", room_id=room_id,
            )
        except Exception:
            pass
        return f"/api/files/{safe}"

    async def send_profile(self, peer_addr_str: str, reply: bool = False) -> Dict[str, Any]:
        """Explicitly broadcast this node's nickname/avatar to a peer.

        With reply=True the receiver replies with its own profile (identity
        handshake) so the caller learns the remote's nickname/avatar too.
        """
        header = self._base_header("profile")
        if reply:
            header["reply"] = True
        await self._send(peer_addr_str, header)
        return {"status": "ok"}

    async def send_friend_request(self, peer_addr_str: str) -> Dict[str, Any]:
        """Send a friend request to a peer. The receiver gets a notification
        and can accept/reject. Our identity rides along in the header."""
        header = self._base_header("friend_request")
        target = parse_peer_string(peer_addr_str)
        await self._send(peer_addr_str, header, peer_id=str(target.id()))
        return {"status": "ok", "peer_id": str(target.id())}

    async def send_friend_request_accept(self, peer_addr_str: str) -> Dict[str, Any]:
        """Accept a friend request: notify the sender that we accepted."""
        header = self._base_header("friend_request_accept")
        target = parse_peer_string(peer_addr_str)
        await self._send(peer_addr_str, header, peer_id=str(target.id()))
        return {"status": "ok", "peer_id": str(target.id())}

    async def send_friend_request_reject(self, peer_addr_str: str) -> Dict[str, Any]:
        """Reject a friend request: notify the sender that we rejected."""
        header = self._base_header("friend_request_reject")
        target = parse_peer_string(peer_addr_str)
        await self._send(peer_addr_str, header, peer_id=str(target.id()))
        return {"status": "ok", "peer_id": str(target.id())}

    async def fetch_remote_identity(self, peer_addr_str: str) -> None:
        """Dial a peer and run an identity handshake to pull its nickname/avatar.

        Called after adding a new contact so the remote's alias shows up right
        away instead of only after its next message. No-op if the peer is
        offline (dial fails) — identity sync then happens on first real message.
        """
        try:
            await self.send_profile(peer_addr_str, reply=True)
        except Exception:
            pass

    async def send_group_invite(self, peer_addr_str: str, group_id: str,
                                name: str, topic: str = "") -> Dict[str, Any]:
        """Ask a peer to join one of our channels. This is delivered as a
        group_invite message (not stored as a chat message) and the remote
        decides whether to accept. Our alias rides along in the identity header
        so the invite shows the inviter's nickname."""
        header = self._base_header("group_invite")
        header["group_id"] = group_id
        header["group_name"] = name
        header["group_topic"] = topic
        target = parse_peer_string(peer_addr_str)
        await self._send(peer_addr_str, header, peer_id=str(target.id()))
        return {"status": "ok", "peer_id": str(target.id())}

    # -- mesh membership sync (no central server) ---------------------------
    def _roster(self, group_id: str) -> List[Dict[str, Any]]:
        """Our full view of a channel's roster, always including ourselves, each
        member carrying a usable dialable addr so fan-out can reach them."""
        members = store.group_members(group_id)
        self_id = str(self.ep.id())
        if not any(m["peer_id"] == self_id for m in members):
            members.insert(0, {"peer_id": self_id, "alias": self._alias or None,
                               "avatar": self._avatar,
                               "last_addr": str(self.ep.addr()) if self.ep else None})
        out = []
        for m in members:
            pid = m["peer_id"]
            out.append({"peer_id": pid,
                        "alias": m.get("alias"),
                        "avatar": m.get("avatar"),
                        "addr": self._peer_addr.get(pid) or m.get("last_addr")})
        return out

    async def _notify_groups_changed(self) -> None:
        try:
            await hub.broadcast("groups_changed", {})
        except Exception:
            pass

    async def send_group_join(self, peer_addr_str: str, group_id: str,
                              member: Dict[str, Any]) -> None:
        """Tell a peer we joined their channel; they reply with the roster."""
        header = self._base_header("group_join")
        header["group_id"] = group_id
        header["member"] = member
        await self._send(peer_addr_str, header)

    async def send_group_roster(self, peer_addr_str: str, group_id: str) -> None:
        """Send our current channel roster (used as the reply to a join)."""
        header = self._base_header("group_roster")
        header["group_id"] = group_id
        header["members"] = self._roster(group_id)
        await self._send(peer_addr_str, header)

    async def send_group_leave(self, peer_addr_str: str, group_id: str,
                               subject_id: Optional[str] = None) -> None:
        """Tell a peer that `subject_id` (default: us) left / was removed from a
        channel, so they drop that peer from their roster."""
        header = self._base_header("group_leave")
        header["group_id"] = group_id
        if subject_id:
            header["peer_id"] = subject_id
        await self._send(peer_addr_str, header)

    async def send_group_removed(self, peer_addr_str: str, group_id: str) -> None:
        """Tell a peer they were kicked out of a channel; they delete it."""
        header = self._base_header("group_removed")
        header["group_id"] = group_id
        await self._send(peer_addr_str, header)

    async def send_group_text(self, group_id: str, content: str,
                              reply_to: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fan-out a text message to every member of a group (point-to-point mesh).

        The PRD explicitly allows point-to-point mesh forwarding as the group
        transport; we deliver by sending to each member's known address with the
        shared room_id set, so every member stores it under the same room.

        The sender persists ONE own record under the room; per-member deliveries
        are wire-only (save=False) so the sender's history shows a single copy.
        """
        members = store.group_members(group_id)
        self_id = str(self.ep.id())
        store.save_message(self_id, "out", "text", content=content,
                           reply_to=reply_to, room_id=group_id)
        results = []
        for member in members:
            if member["peer_id"] == self_id:
                continue
            addr = self._peer_addr.get(member["peer_id"]) or member.get("last_addr")
            if not addr:
                continue
            try:
                results.append(await self.send_text(addr, content, reply_to=reply_to,
                                                    room_id=group_id, save=False))
            except Exception as e:
                results.append({"peer_id": member["peer_id"], "error": str(e)})
        return results

    async def send_group_file(self, group_id: str, filename: str, data: bytes) -> List[Dict[str, Any]]:
        """Fan-out a file to every member (mesh), persisting ONE sender-side
        history row + a local copy so the sender can preview its own upload."""
        members = store.group_members(group_id)
        self_id = str(self.ep.id())
        safe = Path(filename).name
        try:
            self.keep_sender_copy(safe, data, room_id=group_id)
        except Exception as e:
            print(f"[iroh] keep_sender_copy failed: {e!r}")
        store.save_message(self_id, "out", "file", filename=safe,
                           filesize=len(data), room_id=group_id)
        results = []
        for member in members:
            if member["peer_id"] == self_id:
                continue
            addr = self._peer_addr.get(member["peer_id"]) or member.get("last_addr")
            if not addr:
                continue
            try:
                results.append(await self.send_file(addr, filename, data,
                                                    room_id=group_id, save=False))
            except Exception as e:
                results.append({"peer_id": member["peer_id"], "error": str(e)})
        return results

    async def _send(self, peer_addr_str: str, header: dict, file_bytes: bytes = None,
                    peer_id: str = None, filename: str = None) -> None:
        target = parse_peer_string(peer_addr_str)
        if peer_id is None:
            peer_id = str(target.id())
        # SEND-SAFE connection reuse. We keep OUR outbound connections in a
        # separate map (_outgoing_conns) so an inbound connection can never be
        # picked for sending. iroh silently swallows writes sent on an inbound
        # connection without raising, which would drop messages with no error.
        # inbound conns (in _connections only) are for receiving, never sending.
        conn = self._outgoing_conns.get(peer_id)
        if conn is None:
            conn = await self.ep.connect(target, ALPN)
            self._outgoing_conns[peer_id] = conn
            self._connections[peer_id] = conn
            self._outgoing.add(peer_id)
        try:
            bi = await conn.open_bi()
        except Exception:
            # stale/closed connection — reconnect once and retry
            try:
                conn = await self.ep.connect(target, ALPN)
                self._outgoing_conns[peer_id] = conn
                self._connections[peer_id] = conn
                self._outgoing.add(peer_id)
                bi = await conn.open_bi()
            except Exception:
                raise
        snd = bi.send()
        hdr_json = json.dumps(header).encode()
        await snd.write_all(len(hdr_json).to_bytes(4, "big"))
        await snd.write_all(hdr_json)
        if file_bytes:
            total = len(file_bytes)
            sent = 0
            t0 = time.time()
            while sent < total:
                n = min(CHUNK, total - sent)
                await snd.write_all(file_bytes[sent:sent + n])
                sent += n
                await self._emit_progress(peer_id, filename, sent, total, t0)
        await snd.finish()

    async def _emit_progress(self, peer_id, filename, sent, total, t0, direction="out"):
        if filename is None or total == 0:
            return
        elapsed = max(time.time() - t0, 1e-6)
        speed = sent / elapsed
        await hub.broadcast("file_progress", {
            "peer_id": peer_id, "filename": filename, "direction": direction,
            "bytes_sent": sent, "total": total, "speed_bps": speed,
            "done": sent >= total,
        })

    def _remember(self, peer_id: str, peer_addr_str: str) -> None:
        self._peer_addr[peer_id] = peer_addr_str
        try:
            store.touch_peer(peer_id, addr=peer_addr_str)
        except Exception:
            pass

    # -- presence / link status --------------------------------------------
    async def _presence_probe_loop(self) -> None:
        """Dial contacts with no live connection so presence reflects reality
        without waiting for a user action (send, open chat, ...).

        Successful dials stay open and double as send-safe outbound connections
        (reused by _send). Dead connections are pruned here — inbound conns are
        removed by their own close handler, but OUTBOUND conns have no close
        callback, so without this pruning we would never redial a peer whose
        connection dropped.
        """
        while True:
            try:
                self_id = str(self.ep.id())
                for peer in store.list_contacts():
                    pid = peer.get("peer_id")
                    if not pid or pid == self_id:
                        continue
                    if pid in self._connections:
                        # tracked conn: prune if stale, else heartbeat broadcasts it
                        try:
                            self._connections[pid].rtt()
                            continue
                        except Exception:
                            self._connections.pop(pid, None)
                            self._outgoing_conns.pop(pid, None)
                    addr = peer.get("last_addr") or self._peer_addr.get(pid)
                    if not addr:
                        continue
                    last = self._probe_ts.get(pid, 0)
                    if time.time() - last < PROBE_RETRY_SECS:
                        continue
                    self._probe_ts[pid] = time.time()
                    try:
                        target = parse_peer_string(addr)
                        conn = await self.ep.connect(target, ALPN)
                        self._outgoing_conns[pid] = conn
                        self._connections[pid] = conn
                        print(f"[probe] connected {self._short(pid)}", flush=True)
                    except Exception:
                        pass  # offline/unreachable — retry after PROBE_RETRY_SECS
            except Exception:
                pass
            await asyncio.sleep(PROBE_INTERVAL_SECS)

    async def _heartbeat_loop(self) -> None:
        """Periodically ping every known connection to refresh presence + RTT."""
        while True:
            try:
                for peer_id, conn in list(self._connections.items()):
                    try:
                        rtt = conn.rtt()
                        link = self._classify_link(conn, peer_id)
                        await hub.broadcast("presence", {
                            "peer_id": peer_id, "online": True,
                            "link_type": link, "rtt": rtt, "ts": time.time(),
                        })
                        store.touch_peer(peer_id)
                    except Exception:
                        pass
            except Exception:
                pass
            await asyncio.sleep(5)

    def _classify_link(self, conn: iroh.Connection, peer_id: str) -> str:
        """Best-effort Direct vs Relay classification for a live connection.

        The installed iroh Python binding (1.1.0) exposes no per-path
        direct/relay discriminator: `Connection.paths()` returns `PathSnapshot`
        objects with no public fields and `str(paths()) == '[PathSnapshot()]'`.
        We therefore classify from the peer's advertised addresses instead:
        a relay URL implies the path may be relayed; only direct addresses
        implies a direct (hole-punched) connection.
        """
        pa = self._peer_addr.get(peer_id) or ""
        if "relay=" in pa:
            return "relay"     # peer advertises a relay → path may be relayed
        # direct only when it advertises at least one concrete direct address
        m = re.search(r"addrs=\[([^\]]*)\]", pa)
        if m and m.group(1).strip():
            return "direct"
        return "unknown"

    def link_status(self, peer_id: str) -> Dict[str, Any]:
        conn = self._connections.get(peer_id)
        if conn is None:
            return {"peer_id": peer_id, "link_type": "unknown", "rtt": None, "ts": time.time()}
        try:
            rtt = conn.rtt()
        except Exception:
            rtt = None
        return {"peer_id": peer_id, "link_type": self._classify_link(conn, peer_id),
                "rtt": rtt, "ts": time.time()}

    # -- topology / relays --------------------------------------------------
    def relays(self) -> List[Dict[str, Any]]:
        try:
            urls = self.ep.bound_sockets()  # not relays; kept for completeness
        except Exception:
            urls = None
        out = []
        try:
            for r in self._relay_urls():
                out.append({"url": r, "connected": True, "ts": time.time()})
        except Exception:
            pass
        return out

    def _relay_urls(self) -> List[str]:
        # EndpointAddr.relay_url() is a METHOD returning a single URL string
        # (or None), NOT a collection — list() on a str would split it into
        # characters. Wrap the single value (or nothing) in a list.
        try:
            url = self.ep.addr().relay_url()
            return [url] if url else []
        except Exception:
            return []

    def outgoing_connections(self) -> List[Dict[str, Any]]:
        out = []
        for peer_id, conn in self._connections.items():
            out.append({
                "peer_id": peer_id,
                "peer_id_short": self._short(peer_id),
                "rtt": conn.rtt(),
                "link_type": self._classify_link(conn, peer_id),
            })
        return out


# app singleton: persist its secret key under data/ for a stable Node ID
node = IrohNode(secret_key_path=DATA_DIR / "secret.key")
