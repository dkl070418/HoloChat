<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({ src: { type: String, required: true }, alt: { type: String, default: '' } })
const emit = defineEmits(['close'])

function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="fixed inset-0 z-[60] flex items-center justify-center bg-black/80" @click.self="emit('close')">
    <button class="absolute right-4 top-4 text-2xl text-white/70 hover:text-white" @click="emit('close')">✕</button>
    <img :src="src" :alt="alt" class="max-h-[90vh] max-w-[90vw] rounded object-contain shadow-2xl" />
  </div>
</template>
