<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'

// 通用自定义右键菜单。
// 用法：
//   <ContextMenu v-model="menuState" />
// menuState = null | { x, y, items: [{label, danger?, onClick}] }
// 由显示方在 @contextmenu.prevent 时赋值即可。
const props = defineProps({
  modelValue: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const MENU_W = 176
const MENU_H = 42 // 每项高度，用于防溢出估算

const style = computed(() => {
  if (!props.modelValue) return {}
  const vw = window.innerWidth
  const vh = window.innerHeight
  let x = props.modelValue.x
  let y = props.modelValue.y
  const n = (props.modelValue.items || []).length
  const w = MENU_W
  const h = n * 32 + 16 // 每项约 32px，上下 padding 合计 16
  if (x + w > vw) x = Math.max(0, vw - w - 8)
  if (y + h > vh) y = Math.max(0, vh - h - 8)
  return { left: x + 'px', top: y + 'px' }
})

function close() {
  emit('update:modelValue', null)
}

function onItem(item) {
  close()
  if (item.onClick) item.onClick()
}

// 点击任意处 / 按 Esc / 窗口尺寸变化 → 关闭
function onGlobalClick(e) {
  // teleport 到 body，点击菜单内部项会触发 item 处理；这里只关外部点击
  close()
}
function onKey(e) {
  if (e.key === 'Escape') close()
}
function onResize() {
  close()
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      // 下一帧注册监听，避免本次右键的 contextmenu/click 冒泡立刻关掉
      requestAnimationFrame(() => {
        document.addEventListener('click', onGlobalClick, { capture: true })
      })
    } else {
      document.removeEventListener('click', onGlobalClick, { capture: true })
    }
  }
)

onMounted(() => {
  document.addEventListener('keydown', onKey)
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onGlobalClick, { capture: true })
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="ctx">
    <div
      v-if="modelValue"
      class="fixed z-[100] rounded-md border border-tg-border bg-tg-input py-2 shadow-2xl"
      :style="style"
      @click.stop
      @contextmenu.prevent.stop
    >
      <button
        v-for="(item, i) in modelValue.items"
        :key="i"
        class="block w-full px-3 py-1.5 text-left text-[13px] transition hover:bg-tg-hover"
        :class="item.danger ? 'text-red-400 hover:text-red-300' : 'text-tg-textSec hover:text-white'"
        @click="onItem(item)"
      >
        {{ item.label }}
      </button>
    </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ctx-enter-active,
.ctx-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
  transform-origin: top left;
}
.ctx-enter-from,
.ctx-leave-to {
  opacity: 0;
  transform: scale(0.96);
}
</style>
