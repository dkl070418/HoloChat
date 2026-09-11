<script setup>
import { ref, computed } from 'vue'
import { useIrohStore } from '../../stores/iroh'
import { shortId } from '../../utils/format'
import { copyText } from '../../utils/clipboard'
import { toast } from '../../utils/toast'
import { api } from '../../api/client'
import ContextMenu from '../common/ContextMenu.vue'

const iroh = useIrohStore()

const natType = computed(() => {
  const a = iroh.info
  if (!a) return '—'
  const direct = (a.direct_addresses || []).length > 0
  const relayed = !!a.relay_url
  if (direct && relayed) return 'Direct + Relay'
  if (relayed) return 'Relay'
  if (direct) return 'Direct'
  return '未知'
})

function copyFullCredential() {
  const full = iroh.info?.addr || ''
  if (!full) {
    toast('节点尚未就绪，请稍后再试', { type: 'error' })
    return
  }
  copyText(full, '完整凭证')
}

async function copyShortCredential() {
  const short = iroh.info?.addr_short
  if (short) {
    copyText(short, '短凭证')
    return
  }
  // Fallback: ask the backend (handles the window between loadInfo and relay-up)
  try {
    const res = await api.shortCredential()
    if (res?.short) {
      copyText(res.short, '短凭证')
      return
    }
    toast('中继尚未就绪，短码暂不可用。可先用「完整凭证」', { type: 'error' })
  } catch {
    toast('中继尚未就绪，短码暂不可用。可先用「完整凭证」', { type: 'error' })
  }
}

// ---- identity (nickname / avatar) editing ----
const editing = ref(false)
const saving = ref(false)
const aliasDraft = ref('')
const avatarPreview = ref(null)

// in-card popover menu for own avatar
const avatarMenu = ref(false)

function startEdit() {
  aliasDraft.value = iroh.ownAlias || ''
  avatarPreview.value = iroh.ownAvatar || null
  editing.value = true
  avatarMenu.value = false
}
function closeEdit() { editing.value = false }
function pickAvatar(e) {
  const f = e.target?.files?.[0]
  if (!f) return
  const r = new FileReader()
  r.onload = () => { avatarPreview.value = r.result }
  r.readAsDataURL(f)
}
async function saveEdit() {
  saving.value = true
  try {
    await iroh.setIdentity(aliasDraft.value || '', avatarPreview.value || null)
    editing.value = false
  } finally { saving.value = false }
}

async function setDefaultAvatar() {
  iroh.ownAvatar = null
  avatarMenu.value = false
  // persist + broadcast the cleared avatar so it survives reload and reaches peers
  try { await iroh.setIdentity(iroh.ownAlias, null) } catch (e) { console.error(e) }
}
function toggleAvatarMenu() {
  avatarMenu.value = !avatarMenu.value
}
const avatarMenuItems = [
  { label: '修改昵称/头像', onClick: startEdit },
  { label: '恢复默认头像', onClick: setDefaultAvatar },
  { label: '复制凭证（完整）', onClick: copyFullCredential },
  { label: '复制凭证（短码）', onClick: copyShortCredential },
]

// independent context menu for the own-status card (right-click)
const ownMenu = ref(null)
function openOwnMenu(e) {
  e.preventDefault()
  e.stopPropagation()
  ownMenu.value = { x: e.clientX, y: e.clientY, items: avatarMenuItems.slice() }
}
</script>

<template>
  <div class="shrink-0 border-t border-tg-border bg-tg-panel p-2">
    <!-- self identity -->
    <button
      class="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors duration-150 hover:bg-tg-hover"
      title="点击设置昵称/头像，右键更多操作"
      @click="startEdit"
      @contextmenu.prevent.stop="openOwnMenu"
    >
      <div class="relative shrink-0">
        <img v-if="iroh.ownAvatar" :src="iroh.ownAvatar" class="h-9 w-9 rounded-full object-cover" alt="avatar" />
        <div v-else class="flex h-9 w-9 items-center justify-center rounded-full bg-tg-accent text-sm font-bold text-white">
          {{ (iroh.ownAlias || shortId(iroh.info?.id))[0]?.toUpperCase() || '?' }}
        </div>
        <span class="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-tg-panel bg-tg-green" title="本机在线" />
      </div>
      <div class="min-w-0 flex-1">
        <div class="truncate text-[13px] font-semibold text-white">{{ iroh.ownAlias || '本机节点' }}</div>
        <div class="truncate font-mono text-[11px] text-tg-textSec" :title="iroh.info?.id">
          {{ shortId(iroh.info?.id) }}… · {{ natType }}
        </div>
      </div>
      <span
        class="shrink-0 rounded-full p-1 text-[14px] leading-none text-tg-textSec transition hover:bg-tg-input hover:text-white"
        title="更多操作"
        @click.stop="toggleAvatarMenu"
      >⋯</span>
    </button>

    <!-- identity editor -->
    <Transition name="tg-pop">
      <div v-if="editing" class="mt-2 flex flex-col gap-2 rounded-lg bg-tg-input p-2.5">
        <input v-model="aliasDraft" class="w-full rounded-md bg-tg-bg px-2 py-1.5 text-[12px] text-white outline-none placeholder:text-tg-textSec" placeholder="输入你的昵称" />
        <label class="cursor-pointer rounded-md bg-tg-accent px-2 py-1.5 text-center text-[12px] font-medium text-white transition hover:bg-tg-accentHover">
          选择头像
          <input type="file" accept="image/*" class="hidden" @change="pickAvatar" />
        </label>
        <div class="flex items-center gap-2">
          <img v-if="avatarPreview" :src="avatarPreview" class="h-10 w-10 rounded-full object-cover" alt="avatar preview" />
          <button v-else class="h-10 w-10 rounded-full bg-tg-accent text-[11px] font-bold text-white" @click="avatarPreview = null">无</button>
          <div class="flex flex-1 gap-2">
            <button class="flex-1 rounded-md bg-tg-accent px-2 py-1.5 text-[12px] font-semibold text-white transition hover:bg-tg-accentHover disabled:opacity-50" :disabled="saving" @click="saveEdit">{{ saving ? '保存中…' : '保存' }}</button>
            <button class="flex-1 rounded-md bg-tg-hover px-2 py-1.5 text-[12px] text-white transition hover:bg-tg-selected" @click="closeEdit">取消</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- in-card avatar menu (closes on mouse-leave) -->
    <Transition name="tg-pop">
      <div v-if="avatarMenu" class="relative z-40 mt-1 rounded-lg bg-tg-input py-1 shadow-2xl" @mouseleave="avatarMenu = false">
        <button
          v-for="(item, i) in avatarMenuItems"
          :key="i"
          class="block w-full px-3 py-1.5 text-left text-[13px] transition-colors duration-150"
          :class="item.danger ? 'text-tg-red' : 'text-tg-textSec hover:bg-tg-hover hover:text-white'"
          @click="item.onClick()"
        >
          {{ item.label }}
        </button>
      </div>
    </Transition>
  </div>

  <!-- independent right-click context menu for the own identity card -->
  <ContextMenu v-model="ownMenu" />
</template>
