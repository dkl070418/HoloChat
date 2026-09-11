<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { connect, onWsEvent } from './api/ws'
import { useIrohStore } from './stores/iroh'
import { useChatStore } from './stores/chat'
import GroupInviteDialog from './components/common/GroupInviteDialog.vue'
import IdentitySetupDialog from './components/common/IdentitySetupDialog.vue'
import {
  notify as notifyBrowser, playMessageSound, requestNotificationPermission,
  initTitleListener, bumpUnread, getSoundOn,
} from './utils/notify'
import { shortId } from './utils/format'
import { toast } from './utils/toast'

const iroh = useIrohStore()
const chat = useChatStore()

// pending channel invitation surfaced to the global dialog
const pendingInvite = ref(null)
// first-run identity setup dialog (shown only when no persistent secret key)
const showIdentitySetup = ref(false)
const identityPrompted = ref(false)

/** Decide whether an inbound WS event is for the conversation currently on screen. */
function isActiveConversation(data) {
  if (data.room_id) return data.room_id === iroh.activeRoomId
  return data.peer_id === iroh.activePeerId
}

/** Fire browser notification + chime + title badge for an event we're not looking at. */
function notifyIncoming(data, title, body) {
  // per-conversation mute: suppress system notify/sound; unread badges still update
  const key = data.room_id || data.peer_id || (data.from_peer_id || data.from_id) || 'dm'
  if (iroh.isMuted(key)) return
  notifyBrowser({ title, body, tag: data.room_id || data.peer_id || 'dm' })
  if (getSoundOn()) playMessageSound()
  bumpUnread(body || title)
}

// ---- global websocket event routing ----
onMounted(() => {
  iroh.loadInfo().then(() => {
    // first run without a persistent secret key -> guide identity setup (once)
    if (iroh.identityPending && !identityPrompted.value) {
      identityPrompted.value = true
      showIdentitySetup.value = true
    }
  })
  iroh.loadPeers()
  iroh.loadGroups()
  iroh.loadFriendRequests()
  connect()
  // ask once for native browser notification permission (idempotent)
  requestNotificationPermission()
  initTitleListener()

  // presence TTL: grey out contact dots whose heartbeat has been silent for
  // >35s (a peer that actually went offline stops sending presence events)
  setInterval(() => iroh.expirePresence(), 10000)

  onWsEvent((data) => {
    switch (data.event) {
      case 'node_info':
        // always refresh identity from the authoritative backend
        iroh.loadInfo()
        if (typeof data.relays !== 'undefined') iroh.relays = data.relays || []
        break
      case 'identity':
        // a contact's (or our own) nickname/avatar changed — refresh contact list
        iroh.loadPeers()
        iroh.loadGroups()
        break
      case 'groups_changed':
        // a channel's membership changed remotely (join/leave/kick/roster) — refresh
        iroh.loadGroups()
        break
      case 'friend_request':
        // someone wants to add us as a friend — refresh the pending list
        iroh.loadFriendRequests()
        // browser notification for the friend request
        notifyIncoming(
          data,
          '好友请求',
          `${data.from_alias || shortId(data.from_peer_id)} 想加你为好友`,
        )
        break
      case 'friend_request_accepted':
        // our friend request was accepted — refresh contacts
        iroh.loadPeers()
        iroh.loadSentFriendRequests()
        toast(`好友请求已被对方接受`, { type: 'success' })
        break
      case 'friend_request_rejected':
        // our friend request was rejected — refresh sent list
        iroh.loadSentFriendRequests()
        break
      case 'presence':
        iroh.applyPresence(data)
        break
      case 'group_invite':
        // a peer wants us to join their channel — show the accept/ignore dialog
        if (data.group_id) {
          pendingInvite.value = {
            group_id: data.group_id,
            name: data.name || '',
            topic: data.topic || '',
            from_id: data.from_id || '',
            from_addr: data.from_addr || '',
            from_alias: data.from_alias || '',
          }
          // native notification + chime + title badge for the invite
          notifyIncoming(
            data,
            `频道邀请 · ${data.from_alias || shortId(data.from_id)}`,
            `邀请你加入频道「${data.name || '未命名'}」`,
          )
        }
        break
      case 'message': {
        // show for the matching DM peer OR the matching open group room
        if (data.room_id) {
          if (data.room_id === iroh.activeRoomId) chat.upsertMessage(data)
        } else if (data.peer_id === iroh.activePeerId) {
          chat.upsertMessage(data)
        }
        // refresh presence + contacts whenever a peer contacts us
        if (data.direction === 'in') {
          iroh.loadPeers()
          iroh.loadGroups()
        }
        // browser notification for inbound messages from a conversation we're NOT
        // currently looking at (different channel, or DM we haven't opened)
        if (data.direction === 'in' && !isActiveConversation(data)) {
          const sender = iroh.displayName(data.peer_id)
          const channel = data.room_id
            ? (iroh.groups.find((g) => g.id === data.room_id)?.name || '频道')
            : null
          const title = channel ? `[${channel}] ${sender}` : sender
          const body = data.msg_type === 'file'
            ? (data.filename ? `发来文件：${data.filename}` : '发来一个文件')
            : (data.content || '新消息')
          notifyIncoming(data, title, body)
          // unread badge for the conversation we're not viewing
          iroh.bumpUnread(data.room_id || data.peer_id)
        }
        break
      }
      case 'file_progress': {
        // only track outbound progress in the UI; inbound completion is reflected
        // by the message + file_url reaching the chat (direction avoids clobbering
        // `out:<filename>` with a same-named inbound file)
        if (data.direction !== 'in') {
          const key = `out:${data.filename}`
          chat.transfers[key] = {
            done: data.done, bytes_sent: data.bytes_sent,
            total: data.total, speed_bps: data.speed_bps,
          }
        }
        break
      }
      case 'error':
        chat.error = data.detail || 'unknown error'
        break
      default:
        break
    }
  })
})
</script>

<template>
  <router-view />
  <GroupInviteDialog :invite="pendingInvite" @close="pendingInvite = null" />
  <IdentitySetupDialog :visible="showIdentitySetup" @close="showIdentitySetup = false" />
</template>
