<script setup>
import { ref, watch } from 'vue'
import { useIrohStore } from '../../stores/iroh'
import { api } from '../../api/client'

const props = defineProps({
  peer: { type: Object, required: true },   // { addr, alias, avatar }
  existing: { type: Object, default: null },
})
const emit = defineEmits(['close', 'saved'])

const iroh = useIrohStore()
const alias = ref(props.peer.alias || '')
const avatar = ref(props.peer.avatar || '')
const busy = ref(false)
const err = ref('')
const probing = ref(false)   // auto-fetching the remote's nickname/avatar
const remote = ref(null)     // probe result { peer_id, alias, avatar }

async function probe() {
  const addr = props.peer.addr
  if (!addr) { probing.value = false; return }
  probing.value = true
  try {
    // Try probe endpoint first (connects + identity handshake)
    const r = await iroh.probePeer(addr)
    remote.value = r
    if (r && r.peer_id) {
      if (!alias.value && r.alias) alias.value = r.alias
      if (!avatar.value && r.avatar) avatar.value = r.avatar
    }
  } catch (e) {
    // Fallback: try decode endpoint (parse-only, no network)
    try {
      const decoded = await api.decodeCredential(addr)
      if (decoded?.peer_id) {
        remote.value = { peer_id: decoded.peer_id, alias: null, avatar: null }
      }
    } catch { remote.value = null }
  } finally {
    probing.value = false
  }
}

watch(() => props.peer, (p) => {
  alias.value = p.alias || ''
  avatar.value = p.avatar || ''
  remote.value = null
  probe()
}, { immediate: true })

function parseId() {
  const addr = String(props.peer.addr || '')
  // legacy format: starts with 64-char hex node id
  const m = addr.match(/^([0-9a-fA-F]{64})/)
  if (m) return m[1]
  // iroh1: compact base64url format
  if (addr.startsWith('iroh1:')) {
    try {
      let b64 = addr.slice(6)
      b64 += '='.repeat((4 - b64.length % 4) % 4)
      const bin = Uint8Array.from(atob(b64.replace(/-/g, '+').replace(/_/g, '/')), c => c)
      if (bin[0] === 0x01 && bin.length >= 33) {
        const hex = Array.from(bin.slice(1, 33)).map(b => b.toString(16).padStart(2, '0')).join('')
        return hex
      }
    } catch { /* ignore */ }
  }
  return null
}

function onAvatarFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { avatar.value = reader.result }
  reader.readAsDataURL(file)
}

async function save() {
  busy.value = true
  err.value = ''
  try {
    // Priority: existing peer_id > probe result > parse from credential string
    const peerId = props.existing?.peer_id || remote.value?.peer_id || parseId()
    if (!peerId) throw new Error('无法从凭证解析 Node ID。请确认凭证完整且正确。')
    // For a NEW contact, the addr must be a usable endpoint string (contains
    // addrs/relay or a ticket), not a bare 64-char Node ID — a bare ID cannot be
    // dialed, which is exactly why sending would silently do nothing.
    if (!props.existing) {
      const a = String(props.peer.addr || '')
      const looksUsable = /addrs=/.test(a) || /relay=/.test(a) || /^iroh1:/.test(a) || /^(node|endpoint)[a-z0-9]+$/.test(a)
      if (!looksUsable) {
        throw new Error('这看起来只粘贴了 Node ID。请粘贴对方的完整凭证或短码\n（iroh1:…、<nodeid> relay=… addrs=…，或 node…/endpoint… ticket）')
      }
    }
    const addr = props.existing?.last_addr || props.peer.addr
    if (!props.existing) {
      // New contact: send a friend request (not just save + profile handshake)
      await iroh.sendFriendRequest(peerId, addr)
      // Also save locally so they appear in our contacts immediately
      await iroh.savePeer({
        peer_id: peerId,
        alias: alias.value || null,
        avatar: avatar.value || null,
        last_addr: addr,
      })
    } else {
      // Editing existing contact: just update
      await iroh.savePeer({
        peer_id: peerId,
        alias: alias.value || null,
        avatar: avatar.value || null,
        last_addr: addr,
      })
    }
    if (!iroh.activePeerId) iroh.activePeerId = peerId
    emit('saved')
  } catch (e) {
    err.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}

async function remove() {
  const peerId = props.existing?.peer_id
  if (!peerId) return
  if (!window.confirm(`确定删除联系人「${props.existing?.alias || peerId.slice(0, 8)}」吗？`)) return
  busy.value = true
  err.value = ''
  try {
    await iroh.deletePeer(peerId)
    emit('saved')
  } catch (e) {
    err.value = e.message || String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="emit('close')">
    <div class="w-80 rounded-lg bg-tg-panel p-4 shadow-2xl">
      <div class="mb-2 text-[15px] font-bold text-white">{{ existing ? '编辑联系人' : '添加联系人' }}</div>

      <div v-if="probing" class="mb-3 flex items-center gap-2 text-[12px] text-tg-textSec">
        <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-tg-textSec border-t-transparent"></span>
        正在获取对方昵称/头像…
      </div>
      <div v-else-if="!existing && remote?.peer_id" class="mb-3 text-[12px] text-tg-textSec">
        <template v-if="alias">已自动采用对方昵称「{{ alias }}」——你可在备注框改为自己的标记（手填优先）。</template>
        <template v-else>对方在线但未设置昵称，可手填备注，或直接保存用对方 ID。</template>
      </div>
      <div v-else-if="!existing && !probing" class="mb-3 text-[12px] text-tg-textSec">
        对方暂时不可达，可手填备注后保存（昵称会在对方上线后自动同步）。
      </div>

      <div class="mb-3 flex items-center gap-3">
        <img v-if="avatar" :src="avatar" class="h-14 w-14 rounded-full object-cover" alt="" />
        <div v-else class="flex h-14 w-14 items-center justify-center rounded-full bg-tg-accent text-xl font-bold text-white">
          {{ alias[0]?.toUpperCase() || '?' }}
        </div>
        <button class="rounded bg-tg-accent px-2 py-1 text-xs text-white hover:bg-tg-accentHover" @click="$refs.avatarInput.click()">
          {{ avatar ? '更换头像' : '上传头像' }}
        </button>
        <button v-if="avatar" class="text-xs text-tg-textSec hover:text-red-400" @click="avatar=''">清除</button>
        <input ref="avatarInput" type="file" accept="image/*" class="hidden" @change="onAvatarFile" />
      </div>

      <label class="mb-1 block text-[11px] uppercase tracking-wide text-tg-textSec">备注别名</label>
      <input v-model="alias" class="mb-3 w-full rounded-md bg-tg-bg px-2 py-1.5 text-sm text-white outline-none" placeholder="例如：家里的 NAS" />

      <div v-if="err" class="mb-2 rounded bg-red-500/20 px-2 py-1 text-[12px] text-red-300">{{ err }}</div>

      <div class="flex justify-end gap-2">
        <button v-if="existing" :disabled="busy" class="mr-auto rounded px-2 py-1.5 text-sm text-tg-textSec hover:text-red-400" @click="remove">删除此联系人</button>
        <button class="rounded px-3 py-1.5 text-sm text-tg-textSec hover:text-white" @click="emit('close')">取消</button>
        <button :disabled="busy" class="rounded bg-tg-accent px-3 py-1.5 text-sm text-white hover:bg-tg-accentHover disabled:opacity-50" @click="save">
          {{ busy ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>
