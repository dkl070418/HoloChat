"""SQLite persistence: chat history + peer (contact) metadata.

All data lives in the project-relative `data/chat.db` so the app is portable
and never writes to user home / AppData / Temp / system drives.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from .paths import DB_PATH

# thread-local connections so the async event loop and worker threads
# each get their own sqlite handle (sqlite3 is not thread-shared safely).
_local = threading.local()

_db_path: Path = DB_PATH


def configure(path: Path) -> None:
    global _db_path
    _db_path = path


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return conn


def init_db() -> None:
    c = _conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_id TEXT,
            room_id TEXT,
            direction TEXT,
            msg_type TEXT,
            content TEXT,
            filename TEXT,
            filesize INTEGER,
            reply_to INTEGER,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS peers (
            peer_id TEXT PRIMARY KEY,
            alias TEXT,
            avatar TEXT,
            last_addr TEXT,
            favorite INTEGER DEFAULT 0,
            contact INTEGER DEFAULT 0,
            last_seen REAL,
            first_seen REAL
        );
        CREATE TABLE IF NOT EXISTS groups (
            id TEXT PRIMARY KEY,
            name TEXT,
            topic TEXT,
            owner TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS group_members (
            group_id TEXT,
            peer_id TEXT,
            joined_at REAL,
            PRIMARY KEY (group_id, peer_id)
        );
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_id TEXT,
            room_id TEXT,
            direction TEXT,
            filename TEXT,
            size INTEGER,
            sha256 TEXT,
            stored_path TEXT,
            status TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS friend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_peer_id TEXT NOT NULL,
            to_peer_id TEXT NOT NULL,
            from_alias TEXT,
            from_avatar TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            updated_at REAL,
            UNIQUE(from_peer_id, to_peer_id)
        );
        """
    )
    # migrate older DBs: add room_id column if missing (messages table may pre-exist)
    cols = {r[1] for r in c.execute("PRAGMA table_info(messages)").fetchall()}
    if "room_id" not in cols:
        c.execute("ALTER TABLE messages ADD COLUMN room_id TEXT")

    # migrate older DBs: the peers table may exist without a unique constraint
    # if it was created by an older exe. Without one, upsert_peer's
    # select-then-insert race can write two rows for the same peer_id (observed
    # on peer C having duplicate e0414b98b1e5 rows). Rebuild the table with a
    # PRIMARY KEY, deduplicating in one pass: keep the row with a non-empty
    # last_addr, otherwise the most recently seen one. Idempotent — skipped when
    # the table already has a PK / UNIQUE (our own DBs are). Wrapped so a failed
    # rebuild rolls back the whole init transaction.
    peer_ddl = ""
    peer_row = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='peers'"
    ).fetchone()
    if peer_row and peer_row[0]:
        peer_ddl = peer_row[0].upper()
    if peer_ddl and "PRIMARY KEY" not in peer_ddl and "UNIQUE" not in peer_ddl:
        c.execute("ALTER TABLE peers RENAME TO peers_dup")
        c.execute(
            """CREATE TABLE peers (
                peer_id TEXT PRIMARY KEY,
                alias TEXT,
                avatar TEXT,
                last_addr TEXT,
                favorite INTEGER DEFAULT 0,
                contact INTEGER DEFAULT 0,
                last_seen REAL,
                first_seen REAL
            )"""
        )
        c.execute(
            """INSERT OR REPLACE INTO peers
                (peer_id, alias, avatar, last_addr, favorite, contact, last_seen, first_seen)
                SELECT peer_id, alias, avatar, last_addr, favorite, 1 as contact, last_seen, first_seen FROM (
                    SELECT peer_id, alias, avatar, last_addr, favorite, last_seen, first_seen,
                           ROW_NUMBER() OVER (
                               PARTITION BY peer_id
                               ORDER BY (last_addr IS NULL), last_seen DESC
                           ) AS rn
                    FROM peers_dup
                ) WHERE rn = 1"""
        )
        c.execute("DROP TABLE peers_dup")

    # migrate older DBs: add the `contact` column (explicitly-added contacts).
    # Old rows are indistinguishable between "user-added" and "auto-remembered",
    # but rows whose alias equals the raw node id (or is empty) are the tell-tale
    # of an auto-remembered / roster-synced peer -- the old group_members query
    # COALESCEd alias to peer_id, so ghost contacts literally had their node id
    # as "alias". Keep those out of the contact list; only rows with a real,
    # non-node-id alias (or an explicitly remembered favorite) are treated as
    # contacts so the user's contact list stays intact.
    pcols = {r[1] for r in c.execute("PRAGMA table_info(peers)").fetchall()}
    if "contact" not in pcols:
        c.execute("ALTER TABLE peers ADD COLUMN contact INTEGER DEFAULT 0")
        c.execute(
            """UPDATE peers SET contact=1
               WHERE (alias IS NOT NULL AND alias <> '' AND alias <> peer_id)
                  OR favorite=1"""
        )
    c.commit()


# Self-initialize on import so the schema + migrations always apply, no matter
# how the app is entered (FastAPI startup OR direct IrohNode/store use). This is
# idempotent: CREATE IF NOT EXISTS + guarded ALTER + commit.
init_db()


# ---------------- messages ----------------
def save_message(peer_id, direction, msg_type, content="", filename=None,
                 filesize=0, reply_to=None, room_id=None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO messages (peer_id, room_id, direction, msg_type, content, filename, filesize, reply_to, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (peer_id, room_id, direction, msg_type, content, filename, filesize, reply_to, time.time()),
    )
    c.commit()
    return cur.lastrowid


def load_messages(peer_id: Optional[str] = None, room_id: Optional[str] = None,
                  limit: int = 500) -> List[Dict[str, Any]]:
    c = _conn()
    cols = "id, peer_id, room_id, direction, msg_type, content, filename, filesize, reply_to, created_at"
    if peer_id and room_id:
        cur = c.execute(
            f"SELECT {cols} FROM messages WHERE peer_id=? AND room_id=? ORDER BY id DESC LIMIT ?",
            (peer_id, room_id, limit),
        )
    elif peer_id:
        cur = c.execute(
            f"SELECT {cols} FROM messages WHERE peer_id=? ORDER BY id DESC LIMIT ?",
            (peer_id, limit),
        )
    elif room_id:
        cur = c.execute(
            f"SELECT {cols} FROM messages WHERE room_id=? ORDER BY id DESC LIMIT ?",
            (room_id, limit),
        )
    else:
        cur = c.execute(f"SELECT {cols} FROM messages ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    rows.reverse()
    return [dict(r) for r in rows]


# ---------------- peers (contacts) ----------------
def upsert_peer(peer_id: str, **fields) -> Dict[str, Any]:
    c = _conn()
    existing = c.execute("SELECT * FROM peers WHERE peer_id=?", (peer_id,)).fetchone()
    now = time.time()
    if existing is None:
        # A brand-new peer row defaults to NOT being a contact: rows are created
        # automatically by roster sync / message handshakes (`touch_peer`,
        # `merge_group_roster`, `_apply_remote_identity`). Only the explicit
        # add-contact endpoint sets contact=1, so auto-remembered peers never
        # appear in the contact list.
        row = {
            "peer_id": peer_id,
            "alias": fields.get("alias"),
            "avatar": fields.get("avatar"),
            "last_addr": fields.get("last_addr"),
            "favorite": 1 if fields.get("favorite") else 0,
            "contact": 1 if fields.get("contact") else 0,
            "last_seen": fields.get("last_seen", now),
            "first_seen": now,
        }
        try:
            c.execute(
                "INSERT INTO peers (peer_id, alias, avatar, last_addr, favorite, contact, last_seen, first_seen)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (row["peer_id"], row["alias"], row["avatar"], row["last_addr"],
                 row["favorite"], row["contact"], row["last_seen"], row["first_seen"]),
            )
        except sqlite3.IntegrityError:
            # A concurrent upsert for the same peer_id won the race (table now
            # has a PK via migration). Fall back to an update without touching
            # the field semantics.
            c.execute(
                "UPDATE peers SET alias=?, avatar=?, last_addr=?, favorite=?, contact=?, last_seen=? WHERE peer_id=?",
                (row["alias"], row["avatar"], row["last_addr"], row["favorite"],
                 row["contact"], now, peer_id),
            )
    else:
        vals = {
            "alias": fields["alias"] if "alias" in fields and fields["alias"] is not None else existing["alias"],
            "avatar": fields["avatar"] if "avatar" in fields else existing["avatar"],
            "last_addr": fields["last_addr"] if "last_addr" in fields and fields["last_addr"] else existing["last_addr"],
            "favorite": (1 if fields["favorite"] else existing["favorite"]) if "favorite" in fields and fields["favorite"] is not None else existing["favorite"],
            "contact": (1 if fields["contact"] else existing["contact"]) if "contact" in fields and fields["contact"] is not None else existing["contact"],
        }
        c.execute(
            "UPDATE peers SET alias=?, avatar=?, last_addr=?, favorite=?, contact=?, last_seen=? WHERE peer_id=?",
            (vals["alias"], vals["avatar"], vals["last_addr"], vals["favorite"],
             vals["contact"], now, peer_id),
        )
    c.commit()
    return get_peer(peer_id)


def get_peer(peer_id: str) -> Optional[Dict[str, Any]]:
    c = _conn()
    r = c.execute("SELECT * FROM peers WHERE peer_id=?", (peer_id,)).fetchone()
    return dict(r) if r else None


def list_peers() -> List[Dict[str, Any]]:
    c = _conn()
    rows = c.execute("SELECT * FROM peers ORDER BY favorite DESC, last_seen DESC").fetchall()
    return [dict(r) for r in rows]


def list_contacts() -> List[Dict[str, Any]]:
    """Contacts: ONLY peers the user explicitly added (contact=1).

    Peers auto-remembered by roster sync / inbound messages / heartbeats are
    still stored (they carry dialable addrs we need to reply and fan-out), but
    they are not "contacts" and must never show up in the UI contact list.
    """
    c = _conn()
    rows = c.execute(
        "SELECT * FROM peers WHERE contact=1 ORDER BY favorite DESC, last_seen DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def set_contact(peer_id: str, contact: bool) -> Optional[Dict[str, Any]]:
    """Explicitly mark a peer as (or unmark from) a user-added contact."""
    p = get_peer(peer_id)
    if p is None:
        return upsert_peer(peer_id, contact=contact)
    return upsert_peer(peer_id, contact=contact)


def touch_peer(peer_id: str, addr: Optional[str] = None) -> Optional[Dict[str, Any]]:
    now = time.time()
    peer = get_peer(peer_id)
    # remember every peer we ever interact with (roster sync, inbound msgs,
    # heartbeats) -- WITHOUT turning them into a contact.
    if peer is None:
        return upsert_peer(peer_id, last_addr=addr, last_seen=now)
    upsert_peer(peer_id, last_addr=addr, last_seen=now)
    return get_peer(peer_id)


def delete_peer(peer_id: str) -> bool:
    """Remove a saved contact (peers row). Returns True if a row was deleted."""
    c = _conn()
    cur = c.execute("DELETE FROM peers WHERE peer_id=?", (peer_id,))
    c.commit()
    return cur.rowcount > 0



# ---------------- groups (rooms) ----------------
def create_group(name: str, topic: str = "", owner: Optional[str] = None) -> Dict[str, Any]:
    import uuid
    gid = uuid.uuid4().hex[:16]
    c = _conn()
    now = time.time()
    c.execute(
        "INSERT INTO groups (id, name, topic, owner, created_at) VALUES (?,?,?,?,?)",
        (gid, name, topic, owner, now),
    )
    c.commit()
    return get_group(gid)


def get_group(gid: str) -> Optional[Dict[str, Any]]:
    c = _conn()
    r = c.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
    return dict(r) if r else None


def ensure_group(gid: str, name: str, topic: str = "", owner: Optional[str] = None) -> Dict[str, Any]:
    """Create a group with a caller-supplied id (used when a remote invites us to
    join THEIR group, so the room_id matches on both ends). No-op if it exists."""
    c = _conn()
    now = time.time()
    c.execute(
        "INSERT OR IGNORE INTO groups (id, name, topic, owner, created_at) VALUES (?,?,?,?,?)",
        (gid, name, topic, owner, now),
    )
    c.commit()
    return get_group(gid)


def list_groups() -> List[Dict[str, Any]]:
    c = _conn()
    rows = c.execute("SELECT * FROM groups ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        g = dict(r)
        g["members"] = group_members(g["id"])
        out.append(g)
    return out


def add_group_member(gid: str, peer_id: str) -> None:
    c = _conn()
    c.execute(
        "INSERT OR IGNORE INTO group_members (group_id, peer_id, joined_at) VALUES (?,?,?)",
        (gid, peer_id, time.time()),
    )
    c.commit()


def group_members(gid: str) -> List[Dict[str, Any]]:
    c = _conn()
    rows = c.execute(
        "SELECT m.peer_id, p.alias AS alias, p.avatar AS avatar, p.last_addr, m.joined_at"
        " FROM group_members m LEFT JOIN peers p ON p.peer_id = m.peer_id"
        " WHERE m.group_id=? ORDER BY m.joined_at", (gid,),
    ).fetchall()
    return [dict(r) for r in rows]


def remove_group_member(gid: str, peer_id: str) -> bool:
    c = _conn()
    cur = c.execute("DELETE FROM group_members WHERE group_id=? AND peer_id=?", (gid, peer_id))
    c.commit()
    return cur.rowcount > 0


def delete_group(gid: str) -> bool:
    """Remove a group/channel and all its members. Returns True if deleted."""
    c = _conn()
    c.execute("DELETE FROM group_members WHERE group_id=?", (gid,))
    cur = c.execute("DELETE FROM groups WHERE id=?", (gid,))
    c.commit()
    return cur.rowcount > 0


def group_owner(gid: str) -> Optional[str]:
    """Return the owner (creator) peer id of a group, if any."""
    g = get_group(gid)
    return g.get("owner") if g else None


def merge_group_roster(gid: str, members: List[Dict[str, Any]]) -> None:
    """Upsert a remote's roster snapshot into our local roster.

    For every member in `members` (each {peer_id, alias?, avatar?, last_addr?})
    we make sure the peer is known (so fan-out has an address / display name) and
    that it is a member of this group. This is how a joiner learns "who is in
    this channel" without a central server.
    """
    for m in members or []:
        pid = m.get("peer_id")
        if not pid:
            continue
        upsert_peer(
            pid,
            alias=m.get("alias") if m.get("alias") else None,
            avatar=m.get("avatar") if m.get("avatar") else None,
            last_addr=m.get("last_addr") or m.get("addr") or None,
        )
        add_group_member(gid, pid)





# ---------------- files (transfer records) ----------------
def save_file_record(peer_id: str, direction: str, filename: str, size: int,
                     sha256: Optional[str] = None, stored_path: Optional[str] = None,
                     status: str = "complete", room_id: Optional[str] = None) -> int:
    c = _conn()
    cur = c.execute(
        "INSERT INTO files (peer_id, room_id, direction, filename, size, sha256, stored_path, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (peer_id, room_id, direction, filename, size, sha256, stored_path, status, time.time()),
    )
    c.commit()
    return cur.lastrowid


def list_files(peer_id: Optional[str] = None) -> List[Dict[str, Any]]:
    c = _conn()
    if peer_id:
        cur = c.execute(
            "SELECT * FROM files WHERE peer_id=? ORDER BY id DESC", (peer_id,),
        )
    else:
        cur = c.execute("SELECT * FROM files ORDER BY id DESC")
    return [dict(r) for r in cur.fetchall()]


# ---------------- friend requests ----------------
def save_friend_request(from_peer_id: str, to_peer_id: str,
                        from_alias: Optional[str] = None,
                        from_avatar: Optional[str] = None) -> Dict[str, Any]:
    """Create or update a friend request. Returns the request row."""
    c = _conn()
    now = time.time()
    existing = c.execute(
        "SELECT * FROM friend_requests WHERE from_peer_id=? AND to_peer_id=?",
        (from_peer_id, to_peer_id),
    ).fetchone()
    if existing:
        c.execute(
            "UPDATE friend_requests SET from_alias=?, from_avatar=?, status='pending', updated_at=?"
            " WHERE from_peer_id=? AND to_peer_id=?",
            (from_alias, from_avatar, now, from_peer_id, to_peer_id),
        )
    else:
        c.execute(
            "INSERT INTO friend_requests (from_peer_id, to_peer_id, from_alias, from_avatar, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (from_peer_id, to_peer_id, from_alias, from_avatar, "pending", now, now),
        )
    c.commit()
    return get_friend_request(from_peer_id, to_peer_id)


def get_friend_request(from_peer_id: str, to_peer_id: str) -> Optional[Dict[str, Any]]:
    c = _conn()
    r = c.execute(
        "SELECT * FROM friend_requests WHERE from_peer_id=? AND to_peer_id=?",
        (from_peer_id, to_peer_id),
    ).fetchone()
    return dict(r) if r else None


def list_friend_requests(to_peer_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List friend requests sent TO a peer (incoming requests)."""
    c = _conn()
    if status:
        rows = c.execute(
            "SELECT * FROM friend_requests WHERE to_peer_id=? AND status=? ORDER BY created_at DESC",
            (to_peer_id, status),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM friend_requests WHERE to_peer_id=? ORDER BY created_at DESC",
            (to_peer_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_sent_friend_requests(from_peer_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List friend requests sent BY a peer (outgoing requests)."""
    c = _conn()
    if status:
        rows = c.execute(
            "SELECT * FROM friend_requests WHERE from_peer_id=? AND status=? ORDER BY created_at DESC",
            (from_peer_id, status),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM friend_requests WHERE from_peer_id=? ORDER BY created_at DESC",
            (from_peer_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_friend_request(from_peer_id: str, to_peer_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Update a friend request's status (accepted/rejected)."""
    c = _conn()
    now = time.time()
    c.execute(
        "UPDATE friend_requests SET status=?, updated_at=? WHERE from_peer_id=? AND to_peer_id=?",
        (status, now, from_peer_id, to_peer_id),
    )
    c.commit()
    return get_friend_request(from_peer_id, to_peer_id)


def has_pending_friend_request(from_peer_id: str, to_peer_id: str) -> bool:
    """Check if there's a pending friend request between two peers."""
    c = _conn()
    r = c.execute(
        "SELECT 1 FROM friend_requests WHERE from_peer_id=? AND to_peer_id=? AND status='pending'",
        (from_peer_id, to_peer_id),
    ).fetchone()
    return r is not None
