<script setup>
import { computed } from 'vue'
import { useIrohStore } from '../../stores/iroh'

const props = defineProps({ peerId: { type: String, required: true } })
const iroh = useIrohStore()

const p = computed(() => iroh.presence[props.peerId])

const linkText = computed(() => {
  const t = p.value?.link_type
  if (t === 'direct') return 'Direct P2P'
  if (t === 'relay') return 'DERP Relayed'
  return '链路未知'
})
const dot = computed(() => {
  const t = p.value?.link_type
  if (t === 'direct') return 'bg-tg-green'
  if (t === 'relay') return 'bg-tg-yellow'
  return 'bg-tg-textSec'
})
const rtt = computed(() => p.value?.rtt ?? null)
</script>

<template>
  <div
    class="flex items-center gap-2 rounded-full bg-tg-panel px-2.5 py-1 text-[11px] text-tg-textSec"
    :title="`链路类型：${linkText}${rtt != null ? `，RTT ${rtt}ms` : ''}`"
  >
    <span class="h-1.5 w-1.5 rounded-full" :class="dot" />
    <!-- status color based on RTT health -->
    <span class="hidden text-tg-textSec sm:inline">{{ props.peerId ? linkText : '未连接' }}</span>
    <span
      v-if="rtt != null"
      class="font-mono font-semibold"
      :class="rtt < 120 ? 'text-green-400' : rtt < 300 ? 'text-yellow-400' : 'text-red-400'"
    >{{ rtt }} ms</span>
  </div>
</template>
