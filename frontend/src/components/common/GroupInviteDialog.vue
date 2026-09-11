<script setup>
import { ref } from 'vue'
import { toast } from '../../utils/toast'
import { useIrohStore } from '../../stores/iroh'

const props = defineProps({
  invite: { type: Object, default: null },   // { group_id, name, topic, from_id, from_alias }
})
const emit = defineEmits(['close'])

const iroh = useIrohStore()
const accepting = ref(false)

async function accept() {
  if (!props.invite) return
  accepting.value = true
  try {
    const g = await iroh.acceptGroupInvite(
      props.invite.group_id,
      props.invite.name,
      props.invite.topic,
      props.invite.from_id,
      props.invite.from_addr,
    )
    toast(`已加入频道「${g?.name || props.invite.name}」`, { type: 'success' })
    emit('close')
  } catch (e) {
    window.alert('加入失败：' + (e.message || e))
  } finally {
    accepting.value = false
  }
}

function decline() { emit('close') }
</script>

<template>
  <Teleport to="body">
    <div
      v-if="invite"
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/60"
      @click.self="decline"
    >
      <div class="w-80 rounded-lg bg-tg-panel p-4 shadow-2xl">
        <div class="mb-2 flex items-center gap-2">
          <span class="flex h-9 w-9 items-center justify-center rounded-md bg-tg-accent text-lg">#</span>
          <div class="min-w-0">
            <div class="truncate text-[15px] font-bold text-white">{{ invite.name || '未命名频道' }}</div>
            <div class="truncate text-[11px] text-tg-textSec">{{ invite.topic || '频道邀请' }}</div>
          </div>
        </div>
        <div class="mb-4 mt-1 rounded-md bg-tg-input px-3 py-2 text-[13px] leading-relaxed text-white/90">
          <span class="font-semibold text-white">{{ invite.from_alias || '一位联系人' }}</span>
          邀请你加入频道「<span class="text-white">{{ invite.name }}</span>」。
        </div>
        <div class="flex justify-end gap-2">
          <button
            class="rounded px-3 py-1.5 text-sm text-tg-textSec transition hover:text-white"
            :disabled="accepting"
            @click="decline"
          >忽略</button>
          <button
            class="rounded bg-tg-accent px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-tg-accentHover disabled:opacity-50"
            :disabled="accepting"
            @click="accept"
          >{{ accepting ? '加入中…' : '加入频道' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
