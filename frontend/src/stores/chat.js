import { defineStore } from 'pinia'
import { reactive, ref, computed } from 'vue'
import { api } from '../api/client'

/**
 * Chat state: per-peer message history, in-flight optimistic sends and
 * real-time file-transfer progress.
 */
export const useChatStore = defineStore('chat', () => {
  const messages = ref([])            // flat list for the active peer
  const transfers = reactive({})      // key -> transfer progress
  const sending = ref(false)
  const error = ref(null)
  const quoteTarget = ref(null)       // message being quoted (reply), if any

  async function loadHistory(scope) {
    // scope: { peerId } for DM or { roomId } for a group room
    try {
      const res = scope?.roomId
        ? await api.groupHistory(scope.roomId)
        : await api.history(scope?.peerId)
      messages.value = res.messages || []
      // reset progress tracking for loaded files
      for (const m of messages.value) {
        if (m.msg_type === 'file') {
          markDone(m)
        }
      }
    } catch (e) { console.error('loadHistory', e) }
  }

  function markDone(m) {
    const key = transferKey(m)
    if (key && !transfers[key]) {
      transfers[key] = { done: true, bytes_sent: m.filesize || 0, total: m.filesize || 0, speed_bps: 0 }
    }
  }

  function transferKey(m) {
    // key by direction+filename for outgoing optimistic; by id for incoming
    if (m.direction === 'out') return `out:${m.filename}`
    if (m.id) return `in:${m.id}`
    return null
  }

  /** Append a server-acknowledged (or incoming) message. */
  function upsertMessage(m) {
    // Optimistic placeholders carry a synthetic id `opt-...`; the server-confirmed
    // message carries a real numeric id. Match by direction+filename/content on an
    // `opt-` placeholder so the optimistic entry is REPLACED (not duplicated).
    const isOpt = (x) => (x.id != null) && String(x.id).startsWith('opt-')
    // replace optimistic placeholder if it matches by filename for outgoing
    if (m.direction === 'out' && m.msg_type === 'file') {
      const idx = messages.value.findIndex((x) =>
        x.direction === 'out' && x.msg_type === 'file' && x.filename === m.filename && isOpt(x))
      if (idx >= 0) messages.value[idx] = { ...messages.value[idx], ...m }
      else messages.value.push(m)
      return
    }
    if (m.direction === 'out' && m.msg_type === 'text') {
      const idx = messages.value.findIndex((x) =>
        x.direction === 'out' && x.msg_type === 'text' && x.content === m.content && isOpt(x))
      if (idx >= 0) messages.value[idx] = { ...messages.value[idx], ...m }
      else messages.value.push(m)
      return
    }
    // leave a timestamp non-opt placeholder (e.g. an earlier optimistic row that
    // never got a server ack) — not matched here, so it stays until reload
    messages.value.push(m)
  }

  function optimisticText(peerId, content, replyTo) {
    messages.value.push({
      id: `opt-${Date.now()}`, peer_id: peerId, direction: 'out',
      msg_type: 'text', content, reply_to: replyTo, created_at: Date.now() / 1000,
    })
  }

  function optimisticFile(peerId, file) {
    messages.value.push({
      id: `opt-${Date.now()}`, peer_id: peerId, direction: 'out', msg_type: 'file',
      filename: file.name, filesize: file.size, created_at: Date.now() / 1000,
      _localFile: true,
    })
  }

  function removeOptimistic(m) {
    const idx = messages.value.findIndex((x) => x.id === m.id)
    if (idx >= 0) messages.value.splice(idx, 1)
  }

  function clear() { messages.value = []; quoteTarget.value = null }

  return {
    messages, transfers, sending, error, quoteTarget,
    loadHistory, upsertMessage, optimisticText, optimisticFile, removeOptimistic,
    clear, transferKey,
  }
})
