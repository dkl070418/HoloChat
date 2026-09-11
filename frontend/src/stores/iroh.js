import { defineStore } from 'pinia'
import { reactive, ref, watch, computed } from 'vue'
import { api } from '../api/client'
import { shortId } from '../utils/format'

/**
 * Global P2P state: local node identity, live peer presence/link-status map,
 * contacts metadata and connected relays.
 */
export const useIrohStore = defineStore('iroh', () => {
  const info = ref(null)              // local node info from /api/info
  const peers = ref([])               // contacts list from /api/peers
  const relays = ref([])              // connected DERP relays
  const connections = ref([])         // live outgoing connection snapshot
  const presence = reactive({})       // peer_id -> {online, link_type, rtt, ts}
  const activePeerId = ref(null)      // currently-open chat peer (DM)
  const groups = ref([])              // group rooms from /api/groups
  const activeRoomId = ref(null)      // currently-open group room (when not DM)
  const ownAlias = ref('')            // this node's nickname
  const ownAvatar = ref(null)         // this node's avatar data URL
  const ownId = ref('')               // this node's own peer id (from /api/info.id)
  const identityPending = ref(false)  // first-run: no persistent secret key yet
  // unread message badge counts: key = peer_id (DM) or group_id (channel) -> count
  const unread = reactive({})
  // muted conversations: key = peer_id (DM) or group_id (channel) -> true
  // Persisted locally; mute only suppresses system notify + sound, unread badges stay.
  const MUTE_KEY = 'iroh_muted'
  const muted = reactive(loadMutedMap())
  function loadMutedMap() {
    try {
      const raw = JSON.parse(localStorage.getItem(MUTE_KEY) || '[]')
      const map = {}
      for (const k of Array.isArray(raw) ? raw : []) if (k) map[k] = true
      return map
    } catch { return {} }
  }
  function persistMuted() {
    try { localStorage.setItem(MUTE_KEY, JSON.stringify(Object.keys(muted))) } catch { /* ignore */ }
  }
  function isMuted(convoKey) {
    return !!(convoKey && muted[convoKey])
  }
  function toggleMute(convoKey) {
    if (!convoKey) return false
    if (muted[convoKey]) delete muted[convoKey]
    else muted[convoKey] = true
    persistMuted()
    return !!muted[convoKey]
  }
  const friendRequests = ref([])           // incoming friend requests
  const sentFriendRequests = ref([])       // outgoing friend requests

  async function loadInfo() {
    try {
      info.value = await api.info()
      ownId.value = info.value?.id || ''
      // reflect our own persisted identity (nickname/avatar) after a reload
      ownAlias.value = info.value?.alias || ownAlias.value
      ownAvatar.value = info.value?.avatar || ownAvatar.value
      identityPending.value = !!info.value?.identity_pending
    } catch (e) { console.error('loadInfo', e) }
  }

  async function loadPeers() {
    try {
      const res = await api.peers()
      peers.value = res.peers || []
    } catch (e) { console.error('loadPeers', e) }
  }

  async function loadConnections() {
    try {
      const res = await api.connections()
      connections.value = res.connections || []
    } catch (e) { /* noop */ }
  }

  async function loadGroups() {
    try {
      const res = await api.groups()
      groups.value = res.groups || []
    } catch (e) { console.error('loadGroups', e) }
  }

  async function createGroup(name, topic) {
    const res = await api.createGroup({ name, topic: topic || '' })
    await loadGroups()
    return res.group
  }

  async function addGroupMember(group_id, peer_id, addr) {
    const res = await api.groupMember({ group_id, peer_id, addr })
    await loadGroups()
    return res
  }

  /** Invite a peer to a channel (their UI shows accept/ignore). We register
   * them locally so fan-out can reach them; they truly join on accept. */
  async function inviteToGroup(group_id, peer_id, addr, name, topic) {
    const res = await api.groupInvite({ group_id, peer_id, addr, name, topic: topic || '' })
    await loadGroups()
    return res
  }

  /** Accept a remote's channel invite: create the group locally with their id
   * and join as a member, then open it. We also tell the inviter we joined and
   * pull the current roster so we can see everyone in the channel. */
  async function acceptGroupInvite(group_id, name, topic, inviterId, inviterAddr) {
    const res = await api.groupAccept({
      group_id, name, topic: topic || '',
      inviter_id: inviterId || null,
      inviter_addr: inviterAddr || null,
    })
    await loadGroups()
    const g = res.group
    if (g) activeRoomId.value = g.id
    return res
  }

  /** Leave a channel: backend broadcasts our departure to members and removes it. */
  async function leaveGroup(groupId) {
    const res = await api.groupLeave({ group_id: groupId })
    if (activeRoomId.value === groupId) activeRoomId.value = null
    await loadGroups()
    return res
  }

  /** Save this node's own nickname/avatar and reflect it immediately. */
  async function setIdentity(alias, avatar) {
    const res = await api.identity({ alias, avatar })
    ownAlias.value = res.identity?.alias ?? alias ?? ''
    ownAvatar.value = res.identity?.avatar ?? avatar ?? null
    return res
  }

  /** First-run secret-key setup: generate a brand-new identity (takes effect
   * after restart), or import an existing Base64/hex key. Returns the API body. */
  async function identityGenerate() {
    const res = await api.identityGenerate()
    return res
  }
  async function identityImport(key) {
    const res = await api.identityImport(key)
    return res
  }
  async function identityExport() {
    const res = await api.identityExport()
    return res
  }
  async function identityStatus() {
    return await api.identityStatus()
  }

  async function savePeer(peer) {
    try {
      const res = await api.savePeer(peer)
      await loadPeers()
      return res.peer
    } catch (e) { throw e }
  }

  /** Dial a peer + identity-handshake; returns { peer_id, alias, avatar }. */
  async function probePeer(addr) {
    const res = await api.probePeer(addr)
    return res
  }

  async function deletePeer(peerId) {
    try {
      await api.deletePeer(peerId)
      await loadPeers()
      if (activePeerId.value === peerId) activePeerId.value = null
    } catch (e) { throw e }
  }

  async function loadFriendRequests() {
    try {
      const res = await api.friendRequests('pending')
      friendRequests.value = res.requests || []
    } catch (e) { console.error('loadFriendRequests', e) }
  }

  async function loadSentFriendRequests() {
    try {
      const res = await api.sentFriendRequests()
      sentFriendRequests.value = res.requests || []
    } catch (e) { console.error('loadSentFriendRequests', e) }
  }

  async function sendFriendRequest(peerId, addr) {
    const res = await api.sendFriendRequest({ peer_id: peerId, addr })
    await loadSentFriendRequests()
    return res
  }

  async function acceptFriendRequest(fromPeerId, addr) {
    const res = await api.acceptFriendRequest({ from_peer_id: fromPeerId, addr })
    await loadFriendRequests()
    await loadPeers()
    return res
  }

  async function rejectFriendRequest(fromPeerId, addr) {
    const res = await api.rejectFriendRequest({ from_peer_id: fromPeerId, addr })
    await loadFriendRequests()
    return res
  }

  async function createGroupWith(name, topic) {
    return await createGroup(name, topic)
  }

  async function deleteGroup(groupId) {
    await api.deleteGroup(groupId)
    if (activeRoomId.value === groupId) activeRoomId.value = null
    await loadGroups()
  }

  async function removeGroupMember(groupId, peerId) {
    await api.groupMemberRemove(groupId, peerId)
    await loadGroups()
  }

  async function createAndOpenGroup(name, topic) {
    const g = await createGroup(name, topic)
    activeRoomId.value = g.id
    await loadGroups()
    return g
  }

  /** Keep a contact's display info (alias/avatar) fresh. */
  function peerMeta(peerId) {
    return peers.value.find((p) => p.peer_id === peerId) || null
  }

  /** Display name: alias > short id. */
  function displayName(peerId) {
    const meta = peerMeta(peerId)
    if (meta && meta.alias) return meta.alias
    return shortId(peerId)
  }

  function applyPresence(p) {
    presence[p.peer_id] = {
      online: !!p.online,
      link_type: p.link_type || 'unknown',
      rtt: p.rtt ?? null,
      ts: p.ts || Date.now() / 1000,
    }
  }

  /** Mark presence entries whose heartbeat went silent (older than `maxAge`
   *  seconds) as offline, so contact dots grey out shortly after a peer
   *  actually disconnects (P2P: absence of heartbeats is the only signal). */
  function expirePresence(maxAge = 35) {
    const now = Date.now() / 1000
    for (const pid in presence) {
      if (presence[pid].ts && now - presence[pid].ts > maxAge) {
        presence[pid].online = false
      }
    }
  }

  // ---- unread message badges ----
  /** Increment the unread counter for a conversation (peer DM or channel). */
  function bumpUnread(convoKey) {
    if (!convoKey) return
    unread[convoKey] = (unread[convoKey] || 0) + 1
  }

  /** Zero out a conversation's unread counter (opened/viewed it). */
  function clearUnread(convoKey) {
    if (convoKey && unread[convoKey]) delete unread[convoKey]
  }

  /** Unread count for display: 1..99 as-is, anything above shows "…". */
  function unreadLabel(convoKey) {
    const n = unread[convoKey] || 0
    if (n === 0) return null
    return n <= 99 ? String(n) : '…'
  }

  /** Switch the UI back to the contacts / direct-message list (no open conversation). */
  function showContacts() {
    activePeerId.value = null
    activeRoomId.value = null
  }

  /** A compact label (or null) for the TOTAL unread DMs across all contacts. */
  const dmsUnreadLabel = computed(() => {
    let n = 0
    for (const p of peers.value) n += unread[p.peer_id] || 0
    return n === 0 ? null : (n <= 99 ? String(n) : '…')
  })

  /** A compact label (or null) for the TOTAL unread messages across all channels. */
  const groupsUnreadLabel = computed(() => {
    let n = 0
    for (const g of groups.value) n += unread[g.id] || 0
    return n === 0 ? null : (n <= 99 ? String(n) : '…')
  })

  /** Number of pending incoming friend requests (for badge display). */
  const pendingFriendRequestCount = computed(() => friendRequests.value.length)

  // Opening a conversation (DM or channel) clears its badge.
  watch(activePeerId, (id) => { if (id) clearUnread(id) })
  watch(activeRoomId, (id) => { if (id) clearUnread(id) })

  return {
    info, peers, relays, connections, presence, activePeerId,
    groups, activeRoomId, ownAlias, ownAvatar, ownId, identityPending,
    unread, bumpUnread, clearUnread, unreadLabel,
    muted, isMuted, toggleMute,
    friendRequests, sentFriendRequests, pendingFriendRequestCount,
    showContacts, dmsUnreadLabel, groupsUnreadLabel,
    loadInfo, loadPeers, loadConnections, loadGroups, createGroup, addGroupMember,
    setIdentity, savePeer, probePeer, deletePeer, deleteGroup, removeGroupMember, createAndOpenGroup,
    inviteToGroup, acceptGroupInvite, leaveGroup,
    loadFriendRequests, loadSentFriendRequests,
    sendFriendRequest, acceptFriendRequest, rejectFriendRequest,
    identityGenerate, identityImport, identityExport, identityStatus,
    peerMeta, displayName, applyPresence, expirePresence,
  }
})
