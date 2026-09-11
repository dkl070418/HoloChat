<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import Sidebar from '../components/layout/Sidebar.vue'
import ChatWindow from '../components/chat/ChatWindow.vue'
import DragOverlay from '../components/chat/DragOverlay.vue'
import { useIrohStore } from '../stores/iroh'
import { useChatStore } from '../stores/chat'

const iroh = useIrohStore()
const chat = useChatStore()

const dragActive = ref(false)
let dragDepth = 0

function clearDrag() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragActive.value = false
}

onMounted(() => {
  window.addEventListener('dragenter', onDragEnter)
  window.addEventListener('dragleave', onDragLeave)
  window.addEventListener('dragover', onDragOver)
  window.addEventListener('drop', onDrop)
})
onBeforeUnmount(() => {
  window.removeEventListener('dragenter', onDragEnter)
  window.removeEventListener('dragleave', onDragLeave)
  window.removeEventListener('dragover', onDragOver)
  window.removeEventListener('drop', onDrop)
})

function onDragEnter(e) {
  if (!e.dataTransfer?.types?.includes('Files')) return
  dragDepth++
  dragActive.value = true
}
function onDragLeave() { clearDrag() }
function onDragOver(e) { if (e.dataTransfer?.types?.includes('Files')) e.preventDefault() }
function onDrop(e) {
  e.preventDefault()
  dragDepth = 0
  dragActive.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) {
    const evt = new CustomEvent('dsh-send-files', { detail: { files } })
    window.dispatchEvent(evt)
  }
}

watch(() => iroh.activePeerId, (id) => {
  if (id) iroh.activeRoomId = null   // opening a DM closes any open room
  chat.clear()
  if (id) chat.loadHistory({ peerId: id })
})

watch(() => iroh.activeRoomId, (gid) => {
  if (gid) iroh.activePeerId = null  // opening a room closes any open DM
  chat.clear()
  if (gid) chat.loadHistory({ roomId: gid })
})
</script>

<template>
  <div class="flex h-full w-full bg-tg-bg">
    <!-- left: unified conversation list -->
    <Sidebar />
    <!-- right: chat area -->
    <ChatWindow />
    <DragOverlay v-if="dragActive" />
  </div>
</template>
