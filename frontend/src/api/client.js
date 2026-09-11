/** Thin REST client for the FastAPI backend (proxied through Vite dev). */

async function request(path, opts = {}) {
  const res = await fetch(path, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  info: () => request('/api/info'),
  relays: () => request('/api/relays'),
  connections: () => request('/api/connections'),
  peers: () => request('/api/peers'),
  savePeer: (body) => request('/api/peers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  deletePeer: (peerId) => request(`/api/peers/${encodeURIComponent(peerId)}`, { method: 'DELETE' }),
  probePeer: (addr) => request('/api/peers/probe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ addr }),
  }),
  history: (peerId) => request(`/api/history${peerId ? `?peer_id=${encodeURIComponent(peerId)}` : ''}`),
    groupHistory: (roomId) => request(`/api/history?room_id=${encodeURIComponent(roomId)}`),
    identity: (body) => request('/api/identity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    identityStatus: () => request('/api/identity/status'),
    identityGenerate: () => request('/api/identity/generate', { method: 'POST' }),
    identityImport: (key) => request('/api/identity/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    }),
    identityExport: () => request('/api/identity/export'),
    groups: () => request('/api/groups'),
    createGroup: (body) => request('/api/groups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    groupMember: (body) => request('/api/groups/member', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    groupSendText: (group_id, content, replyTo) => request('/api/groups/send_text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id, content, reply_to: replyTo ?? null }),
    }),
      groupSendFile: (group_id, file) => {
        const fd = new FormData()
        fd.append('file', file)
        return request(`/api/groups/send_file?group_id=${encodeURIComponent(group_id)}`, {
          method: 'POST',
          body: fd,
        })
      },
    groupMembers: (gid) => request(`/api/groups/${encodeURIComponent(gid)}/members`),
    deleteGroup: (gid) => request(`/api/groups/${encodeURIComponent(gid)}`, { method: 'DELETE' }),
    groupMemberRemove: (group_id, peer_id) => request('/api/groups/member/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id, peer_id }),
    }),
    groupInvite: (body) => request('/api/groups/invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    groupAccept: (body) => request('/api/groups/accept', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    groupLeave: (body) => request('/api/groups/leave', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    files: () => request('/api/files'),
  sendText: (peerAddr, content, replyTo) => request('/api/send_text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ peer_addr: peerAddr, content, reply_to: replyTo ?? null }),
  }),
  sendFile: (peerAddr, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/api/send_file?peer_addr=${encodeURIComponent(peerAddr)}`, {
      method: 'POST',
      body: fd,
    })
  },
  // friend requests
  friendRequests: (status) => request(`/api/friend_requests${status ? `?status=${status}` : ''}`),
  sentFriendRequests: (status) => request(`/api/friend_requests/sent${status ? `?status=${status}` : ''}`),
  sendFriendRequest: (body) => request('/api/friend_requests/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  acceptFriendRequest: (body) => request('/api/friend_requests/accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  rejectFriendRequest: (body) => request('/api/friend_requests/reject', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }),
  shortCredential: () => request('/api/credential/short'),
  decodeCredential: (addr) => request('/api/credential/decode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ addr }),
  }),
}
