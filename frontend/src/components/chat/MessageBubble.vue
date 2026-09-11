<script setup>
import { computed, ref, onMounted } from 'vue'
import { useIrohStore } from '../../stores/iroh'
import { useChatStore } from '../../stores/chat'
import { shortId, formatTime } from '../../utils/format'
import MarkdownText from './MarkdownText.vue'
import FileTransferCard from './FileTransferCard.vue'
import StickerMessage from './StickerMessage.vue'
import { loadStickerMap, isSingleSticker } from '../../utils/stickers'

const props = defineProps({
  message: { type: Object, required: true },
  // grouping hints computed by the parent list
  first: { type: Boolean, default: true },   // first bubble of a group
  last: { type: Boolean, default: true },    // last bubble of a group (show time)
})
const emit = defineEmits(['quote'])

const iroh = useIrohStore()
const chat = useChatStore()

const stickerReady = ref(false)
onMounted(async () => { await loadStickerMap(); stickerReady.value = true })

const isOut = computed(() => props.message.direction === 'out')
const singleSticker = computed(() =>
  props.message.msg_type === 'text' && stickerReady.value && isSingleSticker(props.message.content))

// for incoming messages we show the sender metadata
const displayName = computed(() => {
  if (isOut.value) return '我'
  return iroh.displayName(props.message.peer_id)
})
const avatarChar = computed(() => displayName.value[0]?.toUpperCase() || '?')

// deterministic pastel avatar color per peer id (Telegram-style)
const AVATAR_COLORS = ['#e17076', '#eda86c', '#a695e7', '#7bc862', '#6ec9cb', '#65aadd', '#ee7aae']
const avatarColor = computed(() => {
  const id = props.message.peer_id || ''
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
})

const quoted = computed(() => {
  const id = props.message.reply_to
  if (!id) return null
  return chat.messages.find((m) => m.id === id) || null
})

const time = computed(() => formatTime(props.message.created_at))
</script>

<template>
  <!-- Telegram row: avatar only on the LAST message of an incoming group -->
  <div
    class="group flex items-end gap-2 px-4"
    :class="[isOut ? 'flex-row-reverse' : '', first ? 'mt-2' : 'mt-0.5']"
  >
    <!-- avatar column (incoming only; keeps alignment for outgoing) -->
    <div class="w-[34px] shrink-0">
      <img
        v-if="!isOut && last && message.avatar"
        :src="message.avatar"
        class="h-[34px] w-[34px] rounded-full object-cover"
        alt=""
      />
      <div
        v-else-if="!isOut && last"
        class="flex h-[34px] w-[34px] items-center justify-center rounded-full text-[13px] font-bold text-white"
        :style="{ background: avatarColor }"
      >{{ avatarChar }}</div>
    </div>

    <!-- body -->
    <div class="flex min-w-0 max-w-[70%] flex-col" :class="isOut ? 'items-end' : 'items-start'">
      <!-- sender name above the group (first of incoming group) -->
      <span v-if="!isOut && first && !singleSticker" class="mb-0.5 px-1 text-[12px] font-semibold" :style="{ color: avatarColor }">
        {{ displayName }}
      </span>

      <!-- quote reply (Telegram-style inset) -->
      <button
        v-if="quoted"
        class="mb-0.5 flex max-w-full items-center gap-1.5 rounded-lg border-l-2 border-tg-accent bg-black/20 px-2 py-1 text-left text-[11px] text-tg-textSec transition hover:bg-black/30"
        :title="'定位引用消息'"
        @click="emit('locate', quoted)"
      >
        <span class="shrink-0 font-semibold text-tg-textLink">{{ quoted.direction === 'out' ? '我' : iroh.displayName(quoted.peer_id) }}</span>
        <span class="truncate">{{ quoted.msg_type === 'file' ? `📁 ${quoted.filename}` : (quoted.content || '').slice(0, 60) }}</span>
      </button>

      <!-- the bubble -->
      <div
        class="relative inline-block max-w-full cursor-pointer rounded-[14px] px-3 text-left shadow-sm transition-colors duration-150 tg-pop"
        :class="[
          isOut ? 'bg-tg-bubbleOut text-white hover:bg-tg-bubbleOutHover' : 'bg-tg-bubbleIn text-[#e8edf2] hover:bg-[#1d2c3c]',
          isOut ? (last ? 'rounded-br-[4px]' : '') : (last ? 'rounded-bl-[4px]' : ''),
          last ? 'pb-[18px]' : 'py-1.5',
        ]"
        :title="`${displayName} · ${time} — 点击回复`"
        @click="emit('quote', message)"
      >
        <!-- content wrapper: keeps vertical padding consistent whether or not
             the meta row reserves space below -->
        <div :class="last ? 'pt-1.5' : ''">
          <StickerMessage v-if="singleSticker" :message="message" />
          <MarkdownText v-else-if="message.msg_type === 'text'" :text="message.content || ''" />
          <FileTransferCard v-else :message="message" :direction="message.direction" />
        </div>

        <!-- timestamp + check, absolutely positioned in the reserved bottom
             strip — never participates in layout (Telegram style) -->
        <span
          v-if="last"
          class="pointer-events-none absolute bottom-[3px] right-2 select-none whitespace-nowrap font-mono text-[10px] leading-none opacity-60 transition-opacity duration-150 group-hover:opacity-100"
        >{{ time }}</span>
      </div>
    </div>
  </div>
</template>
