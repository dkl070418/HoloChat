"""Pydantic schema shared across the API."""
from typing import Optional, List
from pydantic import BaseModel


# ---------- requests ----------
class SendTextReq(BaseModel):
    peer_addr: str
    content: str
    reply_to: Optional[int] = None  # message id being quoted, if any


class SavePeerReq(BaseModel):
    peer_id: str            # full node id (64 hex chars)
    alias: Optional[str] = None
    avatar: Optional[str] = None   # data URL (base64) or null to clear
    favorite: Optional[bool] = None
    last_addr: Optional[str] = None


class ProbeReq(BaseModel):
    addr: str               # endpoint string to dial + identity-handshake for


class SetIdentityReq(BaseModel):
    alias: Optional[str] = None
    avatar: Optional[str] = None


class CreateGroupReq(BaseModel):
    name: str
    topic: Optional[str] = ""


class GroupMemberReq(BaseModel):
    group_id: str
    peer_id: str            # full node id (64 hex chars)
    addr: Optional[str] = None


class GroupTextReq(BaseModel):
    group_id: str
    content: str
    reply_to: Optional[int] = None


class GroupInviteReq(BaseModel):
    group_id: str
    peer_id: str            # full node id (64 hex chars)
    name: str
    topic: Optional[str] = ""
    addr: Optional[str] = None   # dialable endpoint of the invitee, if known


class GroupAcceptReq(BaseModel):
    group_id: str
    name: str
    topic: Optional[str] = ""
    inviter_id: Optional[str] = None    # who invited us (so we can add + handshake)
    inviter_addr: Optional[str] = None  # their dialable credential, if known


class GroupLeaveReq(BaseModel):
    group_id: str


class ImportSecretReq(BaseModel):
    key: str               # Base64 (or raw hex) Ed25519 secret seed / key pair


class FriendRequestReq(BaseModel):
    peer_id: str            # target peer's full node id
    addr: Optional[str] = None  # target peer's dialable credential


class FriendRequestActionReq(BaseModel):
    from_peer_id: str       # who sent the request
    addr: Optional[str] = None  # their dialable credential (for accept reply)


# ---------- responses / events ----------
class MessageOut(BaseModel):
    id: Optional[int] = None
    peer_id: str
    peer_id_short: Optional[str] = None
    direction: str          # 'in' | 'out'
    msg_type: str           # 'text' | 'file'
    content: Optional[str] = ""
    filename: Optional[str] = None
    filesize: Optional[int] = 0
    file_url: Optional[str] = None
    reply_to: Optional[int] = None
    created_at: float = 0.0


class LinkStatus(BaseModel):
    peer_id: str
    link_type: str          # 'direct' | 'relay' | 'unknown'
    rtt: Optional[int] = None   # milliseconds
    ts: float = 0.0


class Presence(BaseModel):
    peer_id: str
    online: bool
    link_type: str = "unknown"
    rtt: Optional[int] = None
    ts: float = 0.0
