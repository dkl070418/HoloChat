<script setup>
import { computed, ref } from 'vue'
import { mediaKind } from '../../utils/format'
import ImageLightbox from './ImageLightbox.vue'

const props = defineProps({
  filename: { type: String, required: true },
  fileUrl: { type: String, default: null },
  local: { type: Boolean, default: false },   // incoming file already downloaded to backend
})
const showLightbox = ref(false)
const kind = computed(() => (props.local ? mediaKind(props.filename) : null))
const src = computed(() => {
  if (props.local && props.fileUrl) return props.fileUrl
  return null
})
</script>

<template>
  <!-- image : inline thumbnail + click to zoom -->
  <div v-if="kind === 'image' && src" class="mt-1 max-w-[280px] cursor-zoom-in overflow-hidden rounded-lg border border-white/10"
       @click="showLightbox = true">
    <img :src="src" :alt="filename" class="block max-h-56 w-full object-cover" />
  </div>

  <!-- video : inline HTML5 player -->
  <video v-else-if="kind === 'video' && src" :src="src" controls preload="metadata"
         class="mt-1 max-h-72 w-full max-w-[360px] rounded-lg border border-white/10" />

  <!-- audio : inline HTML5 player -->
  <audio v-else-if="kind === 'audio' && src" :src="src" controls preload="metadata"
         class="mt-1 w-full max-w-[360px]" />

  <ImageLightbox v-if="showLightbox" :src="src" :alt="filename" @close="showLightbox = false" />
</template>
