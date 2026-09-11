<script setup>
import { computed } from 'vue'
import { useChatStore } from '../../stores/chat'
import { formatBytes, formatSpeed, fileExtension } from '../../utils/format'
import MediaPreview from './MediaPreview.vue'

const props = defineProps({
  message: { type: Object, required: true },
  direction: { type: String, default: 'in' },
})

const chat = useChatStore()

const ext = computed(() => fileExtension(props.message.filename || 'file'))
const size = computed(() => props.message.filesize || 0)

// live transfer progress for THIS file (keyed out:filename)
const transfer = computed(() => {
  if (props.direction === 'out') {
    return chat.transfers[`out:${props.message.filename}`]
  }
  return null
})

const progress = computed(() => {
  const t = transfer.value
  if (!t) return null
  if (t.total === 0) return 100
  return Math.min(100, Math.round((t.bytes_sent / t.total) * 100))
})
const done = computed(() => !!transfer.value?.done || props.direction === 'in')
// whether to render inline preview: any file whose bytes we hold locally
// (received: downloaded to backend; outbound: keep_sender_copy) has a URL
const canPreview = computed(() => !!props.message.file_url)

const icon = computed(() => {
  const img = ['png','jpg','jpeg','gif','webp','svg','bmp']
  const vid = ['mp4','webm','mov','mkv']
  const aud = ['mp3','wav','ogg','m4a','flac']
  if (img.includes(ext.value)) return '🖼'
  if (vid.includes(ext.value)) return '🎬'
  if (aud.includes(ext.value)) return '🎵'
  if (['zip','rar','7z','gz','tar'].includes(ext.value)) return '📦'
  if (['pdf'].includes(ext.value)) return '📄'
  if (['py','js','ts','rs','go','java','html','css'].includes(ext.value)) return '🧾'
  return '📁'
})

function download() {
  const url = props.message.file_url
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = props.message.filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}
</script>

<template>
  <div class="mt-1 max-w-[320px] overflow-hidden rounded-xl bg-black/25">
    <div class="flex items-center gap-2.5 p-2.5">
      <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/10 text-[20px]">{{ icon }}</div>
      <div class="min-w-0 flex-1">
        <div class="truncate text-[13px] font-semibold text-white" :title="message.filename">{{ message.filename }}</div>
        <div class="flex items-center gap-2 text-[11px]" :class="direction === 'out' ? 'text-blue-100/80' : 'text-tg-textSec'">
          <span>{{ formatBytes(size) }}</span>
          <span v-if="transfer && transfer.speed_bps > 0">{{ formatSpeed(transfer.speed_bps) }}</span>
          <span v-if="progress != null && progress < 100">{{ progress }}%</span>
          <span v-else-if="done" class="inline-flex items-center gap-0.5">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M4 12l6 6L20 6"/></svg>
            已完成
          </span>
        </div>
      </div>
      <!-- download for received files -->
      <button
        v-if="direction === 'in' && message.file_url"
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-white transition-all duration-150 hover:bg-white/20 active:scale-90"
        title="下载文件"
        @click.stop="download"
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
      </button>
    </div>

    <!-- progress bar (outbound live / inbound completed) -->
    <div class="h-1 w-full bg-black/30">
      <div
        class="h-full transition-all duration-300"
        :class="done ? (direction === 'out' ? 'bg-blue-200' : 'bg-tg-green') : 'bg-tg-accent'"
        :style="{ width: (progress ?? (done ? 100 : 0)) + '%' }"
      />
    </div>

    <!-- inline preview for received media -->
    <MediaPreview v-if="canPreview" :filename="message.filename" :file-url="message.file_url" :local="true" />
  </div>
</template>
