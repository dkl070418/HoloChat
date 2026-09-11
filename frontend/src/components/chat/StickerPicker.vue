<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { loadStickerMap } from '../../utils/stickers'

const props = defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['pick', 'close'])

const manifest = ref([])
const loaded = ref(false)

onMounted(async () => {
  const { manifest: man } = await loadStickerMap()
  manifest.value = man || []
  loaded.value = true
})

function onPick(s) {
  emit('pick', s)
  emit('close')
}
</script>

<template>
  <div
    v-if="open"
    class="absolute bottom-14 left-0 z-50 flex max-h-[320px] w-[300px] flex-col overflow-hidden rounded-xl border border-tg-border bg-tg-panel shadow-2xl"
    @mouseleave="emit('close')"
  >
    <div class="border-b border-tg-border px-3 py-2 text-[12px] font-semibold text-tg-textSec">
      😀 贴纸
      <span class="ml-1 text-[10px] font-normal text-tg-textSec">
        {{ loaded ? `${manifest.length} 张本地贴纸 · 随包分发` : '加载中…' }}
      </span>
    </div>
    <div class="flex-1 overflow-y-auto p-2">
      <div v-if="!loaded" class="p-3 text-center text-[12px] text-tg-textSec">加载贴纸库…</div>
      <div v-else-if="!manifest.length" class="p-3 text-center text-[12px] text-tg-textSec">
        未找到贴纸资源
      </div>
      <div v-else class="grid grid-cols-5 gap-1">
        <button
          v-for="st in manifest"
          :key="st.h"
          class="rounded-lg p-1 transition hover:bg-tg-hover"
          :title="`:${st.s}:`"
          @click="onPick(st.s)"
        >
          <img :src="`/stickers/${st.h}.png`" :alt="st.s" class="h-9 w-9 object-contain" draggable="false" loading="lazy" />
        </button>
      </div>
    </div>
  </div>
</template>
