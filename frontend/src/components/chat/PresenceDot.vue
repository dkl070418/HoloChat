<script setup>
import { computed } from 'vue'
import { useIrohStore } from '../../stores/iroh'

const props = defineProps({ peerId: { type: String, required: true } })
const iroh = useIrohStore()

const online = computed(() => iroh.presence[props.peerId]?.online ?? false)
const rtt = computed(() => iroh.presence[props.peerId]?.rtt ?? null)

const color = computed(() => {
  if (!online.value) return 'bg-tg-textSec'
  if (rtt.value != null && rtt.value < 120) return 'bg-tg-green'
  if (rtt.value != null && rtt.value < 300) return 'bg-tg-yellow'
  return 'bg-tg-green'
})
</script>

<template>
  <span
    class="h-2.5 w-2.5 shrink-0 rounded-full"
    :class="color"
    :title="online ? `在线${rtt != null ? ` · ${rtt}ms` : ''}` : '离线'"
  />
</template>
