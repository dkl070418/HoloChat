<script setup>
import { computed } from 'vue'
import { stickerUrl } from '../../utils/stickers'

const props = defineProps({ message: { type: Object, required: true } })

// content is exactly one ::shortcode:: here
const url = computed(() => {
  const m = /^\s*::([a-z0-9_]+)::\s*$/.exec(props.message.content || '')
  return m ? stickerUrl(m[1]) : null
})
</script>

<template>
  <div v-if="url" class="py-1">
    <img :src="url" :alt="message.content" class="h-20 w-20 object-contain" draggable="false" />
  </div>
  <!-- fallback: unknown code -> show the text as-is -->
  <span v-else class="break-words whitespace-pre-wrap">{{ message.content }}</span>
</template>
