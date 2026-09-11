<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useIrohStore } from '../../stores/iroh'
import { useChatStore } from '../../stores/chat'
import { api } from '../../api/client'
import StickerPicker from './StickerPicker.vue'

const iroh = useIrohStore()
const chat = useChatStore()

const text = ref('')
const fileInput = ref(null)
const sending = ref(false)
const stickerOpen = ref(false)

const active = () => iroh.peerMeta(iroh.activePeerId)
const peerAddrForSend = () => active()?.last_addr || null
const roomId = () => iroh.activeRoomId
const targetActive = () => !!(roomId() || active())

function onSendFilesEvent(e) {
  sendFiles(e.detail?.files || [])
}

onMounted(() => window.addEventListener('dsh-send-files', onSendFilesEvent))
onBeforeUnmount(() => window.removeEventListener('dsh-send-files', onSendFilesEvent))

async function sendText() {
  const content = text.value.trim()
  const rid = roomId()
  const addr = peerAddrForSend()
  if (!content || (!rid && !addr)) return
  sending.value = true
  chat.error = null
  const replyTo = chat.quoteTarget?.id ?? null
  chat.quoteTarget = null
  text.value = ''
  if (rid) {
    // group room: fan-out via backend, then reload room history
    chat.optimisticText('room', content, replyTo)
    try {
      await api.groupSendText(rid, content, replyTo)
      await chat.loadHistory({ roomId: rid })
    } catch (e) {
      chat.error = e.message || String(e)
      chat.loadHistory({ roomId: rid })
    }
  } else {
    const peerId = iroh.activePeerId
    chat.optimisticText(peerId, content, replyTo)
    try {
      const res = await api.sendText(addr, content, replyTo)
      chat.upsertMessage(res.message)
    } catch (e) {
      chat.error = e.message || String(e)
      chat.loadHistory({ peerId })
    }
  }
  sending.value = false
}

async function sendFiles(files) {
  const rid = roomId()
  const addr = peerAddrForSend()
  if (!rid && !addr) return
  for (const file of files) {
    chat.error = null
    if (rid) {
      chat.optimisticFile('room', file)
      try {
        await api.groupSendFile(rid, file)
        await chat.loadHistory({ roomId: rid })
      } catch (e) {
        chat.error = e.message || String(e)
        chat.loadHistory({ roomId: rid })
      }
    } else {
      const peerId = iroh.activePeerId
      chat.optimisticFile(peerId, file)
      try {
        const res = await api.sendFile(addr, file)
        chat.upsertMessage(res.message)
      } catch (e) {
        chat.error = e.message || String(e)
        chat.loadHistory({ peerId })
      }
    }
  }
  if (fileInput.value) fileInput.value.value = ''
}

function onPickFile(e) {
  sendFiles(Array.from(e.target.files || []))
}

function onStickerPick(code) {
  // send the sticker as a text message containing its :shortcode: reference —
  // the receiver renders the same bundled image locally (no bytes transferred)
  if (targetActive()) {
    text.value = `::${code}::`
    sendText()
  } else {
    text.value = text.value
      ? `${text.value} ::${code}::`
      : `::${code}::`
  }
  stickerOpen.value = false
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendText()
  }
}

function cancelQuote() { chat.quoteTarget = null }

// scroll input cursor to end on quote
onMounted(() => nextTick(() => text.value = text.value))
</script>

<template>
  <div class="relative shrink-0 border-t border-tg-border bg-tg-panel px-3 pb-3 pt-2">
    <!-- sticker picker panel -->
    <StickerPicker :open="stickerOpen" @pick="onStickerPick" @close="stickerOpen = false" />

    <!-- quote reply bar -->
    <Transition name="tg-pop">
      <div v-if="chat.quoteTarget" class="mb-2 flex items-center gap-2 rounded-lg border-l-2 border-tg-accent bg-black/25 px-2.5 py-1.5 text-[12px]">
        <span class="font-semibold text-tg-textLink">回复</span>
        <span class="truncate text-tg-textSec">
          {{ chat.quoteTarget.msg_type === 'file' ? `📁 ${chat.quoteTarget.filename}` : (chat.quoteTarget.content || '').slice(0, 60) }}
        </span>
        <button class="ml-auto shrink-0 rounded-full p-0.5 text-tg-textSec transition hover:bg-tg-hover hover:text-white" @click="cancelQuote">✕</button>
      </div>
    </Transition>

    <!-- error toast -->
    <Transition name="tg-pop">
      <div v-if="chat.error" class="mb-2 rounded-lg bg-tg-red/20 px-2.5 py-1.5 text-[12px] text-red-300">
        ⚠ {{ chat.error }}
      </div>
    </Transition>

    <div class="flex items-end gap-1.5">
      <!-- emoji / sticker -->
      <button
        class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[18px] text-tg-textSec transition-all duration-150 hover:bg-tg-hover hover:text-white active:scale-90"
        :class="{ 'bg-tg-hover text-white': stickerOpen }"
        title="贴纸"
        @click="stickerOpen = !stickerOpen"
      >😀</button>

      <!-- attach file -->
      <button
        class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[17px] text-tg-textSec transition-all duration-150 hover:bg-tg-hover hover:text-white active:scale-90 disabled:opacity-40"
        title="发送文件"
        :disabled="!targetActive()"
        @click="fileInput && fileInput.click()"
      >📎</button>

      <!-- input -->
      <textarea
        v-model="text"
        :rows="Math.min(5, Math.max(1, text.split('\n').length))"
        class="max-h-36 min-h-[42px] flex-1 resize-none rounded-2xl bg-tg-input px-4 py-2.5 text-[14px] leading-snug text-white outline-none transition-colors duration-150 placeholder:text-tg-textSec focus:bg-[#2b5278]/40"
        :placeholder="active() ? '写下消息… Enter 发送，Shift+Enter 换行' : '请先在左侧选择或添加一个会话'"
        :disabled="!targetActive()"
        @keydown="onKey"
      />

      <!-- send -->
      <button
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-white shadow-md transition-all duration-150 active:scale-90 disabled:opacity-40"
        :class="text.trim() ? 'bg-tg-accent hover:bg-tg-accentHover' : 'bg-tg-input text-tg-textSec'"
        :title="sending ? '发送中…' : '发送'"
        :disabled="!targetActive() || !text.trim() || sending"
        @click="sendText"
      >
        <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor"><path d="M3.4 20.4l17.45-7.48a1 1 0 000-1.84L3.4 3.6a.993.993 0 00-1.39.91L2 9.12c0 .5.37.93.87.99L17 12 2.87 13.88c-.5.07-.87.5-.87 1l.01 4.61c0 .71.73 1.2 1.39.91z"/></svg>
      </button>
      <input ref="fileInput" type="file" class="hidden" @change="onPickFile" />
    </div>
  </div>
</template>
