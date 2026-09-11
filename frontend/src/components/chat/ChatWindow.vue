<script setup>
import { ref, watch, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useIrohStore } from '../../stores/iroh'
import { useChatStore } from '../../stores/chat'
import { shortId } from '../../utils/format'
import SignalBadge from './SignalBadge.vue'
import MessageBubble from './MessageBubble.vue'
import MessageInput from './MessageInput.vue'

const iroh = useIrohStore()
const chat = useChatStore()
const listEl = ref(null)
const stickToBottom = ref(true)

/** Grouping flags: Telegram merges consecutive messages by the same sender. */
const GAP_SECS = 5 * 60 // new group after 5 minutes of silence
function isFirst(i) {
  const m = chat.messages[i]
  const prev = chat.messages[i - 1]
  if (!prev) return true
  if (prev.direction !== m.direction) return true
  if (prev.peer_id !== m.peer_id) return true
  if (m.created_at && prev.created_at && m.created_at - prev.created_at > GAP_SECS) return true
  return false
}
function isLast(i) {
  const m = chat.messages[i]
  const next = chat.messages[i + 1]
  if (!next) return true
  if (next.direction !== m.direction) return true
  if (next.peer_id !== m.peer_id) return true
  if (m.created_at && next.created_at && next.created_at - m.created_at > GAP_SECS) return true
  return false
}

function onScroll() {
  const el = listEl.value
  if (!el) return
  // user is "at the bottom" when within 80px — keep auto-following new messages
  stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollToBottom() {
  const el = listEl.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => chat.messages.length, async () => {
  await nextTick()
  if (stickToBottom.value) scrollToBottom()
})

// jump to bottom when switching conversation
watch([() => iroh.activePeerId, () => iroh.activeRoomId], async () => {
  await nextTick()
  stickToBottom.value = true
  scrollToBottom()
})

/** Scroll a quoted message into view and flash-highlight it. */
const highlightId = ref(null)
let highlightTimer = null
function locateMessage(msg) {
  const el = document.getElementById(`msg-${msg.id}`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  highlightId.value = msg.id
  clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => { highlightId.value = null }, 1600)
}
onBeforeUnmount(() => clearTimeout(highlightTimer))

function onQuote(msg) {
  chat.quoteTarget = msg
}

const activeGroup = computed(() => iroh.groups.find((g) => g.id === iroh.activeRoomId) || null)

const title = computed(() => {
  if (activeGroup.value) return activeGroup.value.name || '群组房间'
  const id = iroh.activePeerId
  if (!id) return 'HoloChat'
  return iroh.displayName(id)
})

const subtitle = computed(() => {
  if (activeGroup.value) {
    const online = (activeGroup.value.members || []).filter((m) => iroh.presence[m.peer_id]?.online).length
    return `${(activeGroup.value.members || []).length} 名成员${online ? ` · ${online} 人在线` : ''}`
  }
  const id = iroh.activePeerId
  if (!id) return ''
  const p = iroh.presence[id]
  if (p?.online) return p.link_type === 'direct' ? `在线 · 直连 ${p.rtt != null ? p.rtt + 'ms' : ''}` : '在线 · 中继'
  return shortId(id) + '…'
})
</script>

<template>
  <main class="flex h-full min-w-0 flex-1 flex-col bg-tg-bg">
    <!-- top bar -->
    <header class="flex h-[52px] shrink-0 items-center justify-between border-b border-tg-border px-4">
      <div class="min-w-0">
        <div class="truncate text-[15px] font-bold text-white">{{ title }}</div>
        <div class="truncate text-[12px] text-tg-textSec">{{ subtitle }}</div>
      </div>
      <SignalBadge v-if="iroh.activePeerId && !iroh.activeRoomId" :peer-id="iroh.activePeerId" />
    </header>

    <!-- empty state -->
    <div v-if="!iroh.activePeerId && !iroh.activeRoomId" class="flex flex-1 items-center justify-center text-tg-textSec">
      <div class="tg-fade text-center">
        <div class="mb-3 text-5xl opacity-80">💬</div>
        <div class="text-[14px]">从左侧选择一个会话开始 P2P 聊天</div>
        <div class="mt-1 text-[12px] opacity-70">消息与文件全部点对点直传，不经任何服务器</div>
      </div>
    </div>

    <!-- message list -->
    <div v-else ref="listEl" class="min-h-0 flex-1 overflow-y-auto py-2" @scroll="onScroll">
      <div v-if="!chat.messages.length" class="px-4 pt-6 text-center text-[13px] text-tg-textSec">还没有消息，打个招呼吧～</div>

      <TransitionGroup name="tg-msg" tag="div">
        <div
          v-for="(m, i) in chat.messages"
          :id="'msg-' + m.id"
          :key="m.id ?? m.filename"
          class="transition-colors duration-500"
          :class="highlightId === m.id ? 'bg-tg-accent/20' : ''"
        >
          <MessageBubble :message="m" :first="isFirst(i)" :last="isLast(i)" @quote="onQuote" @locate="locateMessage" />
        </div>
      </TransitionGroup>
    </div>

    <!-- scroll-to-bottom floating button -->
    <Transition name="tg-pop">
      <button
        v-if="!stickToBottom && (iroh.activePeerId || iroh.activeRoomId)"
        class="absolute bottom-24 right-6 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-tg-panel text-tg-textSec shadow-xl transition hover:text-white"
        title="回到底部"
        @click="stickToBottom = true; scrollToBottom()"
      >
        ↓
      </button>
    </Transition>

    <MessageInput />
  </main>
</template>
