<script setup>
import { ref, computed } from 'vue'
import { toast } from '../../utils/toast'
import { useIrohStore } from '../../stores/iroh'
import { shortId } from '../../utils/format'

const props = defineProps({
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const iroh = useIrohStore()
const loading = ref(false)

const requests = computed(() => iroh.friendRequests || [])

async function accept(req) {
  loading.value = true
  try {
    await iroh.acceptFriendRequest(req.from_peer_id, req.from_addr)
    toast(`已接受 ${req.from_alias || shortId(req.from_peer_id)} 的好友请求`, { type: 'success' })
  } catch (e) {
    window.alert('接受失败：' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function reject(req) {
  loading.value = true
  try {
    await iroh.rejectFriendRequest(req.from_peer_id, req.from_addr)
    toast(`已拒绝 ${req.from_alias || shortId(req.from_peer_id)} 的好友请求`, { type: 'success' })
  } catch (e) {
    window.alert('拒绝失败：' + (e.message || e))
  } finally {
    loading.value = false
  }
}

const AVATAR_COLORS = ['#e17076', '#eda86c', '#a695e7', '#7bc862', '#6ec9cb', '#65aadd', '#ee7aae']
function avatarColor(id) {
  let h = 0
  for (let i = 0; i < (id || '').length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible && requests.length"
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/60"
      @click.self="emit('close')"
    >
      <div class="w-80 rounded-lg bg-tg-panel p-4 shadow-2xl">
        <div class="mb-3 text-[15px] font-bold text-white">好友请求</div>

        <div class="max-h-64 space-y-2 overflow-y-auto">
          <div
            v-for="req in requests"
            :key="req.from_peer_id"
            class="flex items-center gap-3 rounded-lg bg-tg-input px-3 py-2.5"
          >
            <!-- avatar -->
            <div
              v-if="!req.from_avatar"
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[14px] font-bold text-white"
              :style="{ background: avatarColor(req.from_peer_id) }"
            >{{ (req.from_alias || '?')[0]?.toUpperCase() || '?' }}</div>
            <img v-else :src="req.from_avatar" class="h-10 w-10 shrink-0 rounded-full object-cover" alt="" />

            <div class="min-w-0 flex-1">
              <div class="truncate text-[13px] font-semibold text-white">{{ req.from_alias || shortId(req.from_peer_id) }}</div>
              <div class="truncate text-[11px] text-tg-textSec">想加你为好友</div>
            </div>

            <div class="flex shrink-0 gap-1.5">
              <button
                :disabled="loading"
                class="rounded bg-tg-accent px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-tg-accentHover disabled:opacity-50"
                @click="accept(req)"
              >接受</button>
              <button
                :disabled="loading"
                class="rounded px-2.5 py-1 text-[11px] text-tg-textSec transition hover:text-red-400 disabled:opacity-50"
                @click="reject(req)"
              >拒绝</button>
            </div>
          </div>
        </div>

        <div class="mt-3 flex justify-end">
          <button class="rounded px-3 py-1.5 text-sm text-tg-textSec transition hover:text-white" @click="emit('close')">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
