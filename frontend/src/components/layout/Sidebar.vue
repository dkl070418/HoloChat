<script setup>
import { ref, computed } from 'vue'
import { useIrohStore } from '../../stores/iroh'
import { useChatStore } from '../../stores/chat'
import { shortId, formatTime } from '../../utils/format'
import { toast } from '../../utils/toast'
import PresenceDot from '../chat/PresenceDot.vue'
import UserStatusCard from './UserStatusCard.vue'
import PeerEditDialog from '../peers/PeerEditDialog.vue'
import ContextMenu from '../common/ContextMenu.vue'
import FriendRequestDialog from '../common/FriendRequestDialog.vue'

const iroh = useIrohStore()
const chat = useChatStore()

// ---- search & tabs ----
const searchText = ref('')
const activeTab = ref('all') // all | dms | groups

/** A unified conversation entry: DM contact or group channel. */
const conversations = computed(() => {
  const dmList = (iroh.peers || [])
    .filter((p) => p.peer_id !== iroh.ownId)
    .map((p) => ({
      kind: 'dm',
      id: p.peer_id,
      name: p.alias || shortId(p.peer_id),
      avatar: p.avatar || null,
      sub: p.last_msg_preview || '',
      time: p.last_active || null,
      unread: iroh.unread[p.peer_id] || 0,
      online: !!(iroh.presence[p.peer_id] && iroh.presence[p.peer_id].online),
      raw: p,
    }))
  const groupList = (iroh.groups || []).map((g) => ({
    kind: 'group',
    id: g.id,
    name: g.name || '未命名频道',
    avatar: null,
    sub: `${(g.members || []).length} 名成员`,
    time: null,
    unread: iroh.unread[g.id] || 0,
    online: false,
    raw: g,
  }))
  return [...dmList, ...groupList]
})

const filtered = computed(() => {
  let list = conversations.value
  if (activeTab.value === 'dms') list = list.filter((c) => c.kind === 'dm')
  if (activeTab.value === 'groups') list = list.filter((c) => c.kind === 'group')
  const q = searchText.value.trim().toLowerCase()
  if (q) list = list.filter((c) => c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q))
  // unread first, then by recency, then alphabetical — Telegram-like ordering
  return [...list].sort((a, b) => {
    if ((b.unread > 0) - (a.unread > 0)) return (b.unread > 0) - (a.unread > 0)
    return a.name.localeCompare(b.name, 'zh-CN')
  })
})

const counts = computed(() => ({
  all: conversations.value.length,
  dms: conversations.value.filter((c) => c.kind === 'dm').length,
  groups: conversations.value.filter((c) => c.kind === 'group').length,
}))

function openConvo(c) {
  if (c.kind === 'dm') iroh.activePeerId = c.id
  else iroh.activeRoomId = c.id
}

const isActive = (c) => (c.kind === 'dm' ? iroh.activePeerId === c.id : iroh.activeRoomId === c.id)

// ---- add peer (paste credential) ----
const editingPeer = ref(null)
const editingExisting = ref(null)
function onAddPeer() {
  const val = searchText.value.trim()
  if (!val) return
  editingPeer.value = { addr: val }
  editingExisting.value = null
}
function openEdit(peer) {
  editingExisting.value = peer
  editingPeer.value = { addr: peer.last_addr || '', alias: peer.alias, avatar: peer.avatar }
}
function closeDialog() { editingPeer.value = null; editingExisting.value = null }

async function deleteContact(peer) {
  const name = peer.alias || shortId(peer.peer_id)
  if (!window.confirm(`确定删除联系人「${name}」吗？`)) return
  try { await iroh.deletePeer(peer.peer_id) } catch (e) { window.alert('删除失败：' + (e.message || e)) }
}

// ---- create channel ----
const showCreateGroup = ref(false)
const newGroupName = ref('')
const creatingGroup = ref(false)
async function onCreateGroup() {
  const name = newGroupName.value.trim()
  if (!name) return
  creatingGroup.value = true
  try {
    await iroh.createAndOpenGroup(name)
    newGroupName.value = ''
    showCreateGroup.value = false
  } catch (e) { window.alert('创建失败：' + (e.message || e)) } finally { creatingGroup.value = false }
}

async function deleteGroup(g) {
  if (!window.confirm(`确定删除频道「${g.name}」吗？`)) return
  try { await iroh.deleteGroup(g.id) } catch (e) { window.alert('删除失败：' + (e.message || e)) }
}
async function leaveChannel(g) {
  if (!window.confirm(`确定退出频道「${g.name}」吗？`)) return
  try {
    await iroh.leaveGroup(g.id)
    toast(`已退出频道「${g.name}」`, { type: 'success' })
  } catch (e) { window.alert('退出失败：' + (e.message || e)) }
}

// ---- invite contact to channel ----
const showAddToGroup = ref(false)
const addTargetPeer = ref(null)
const addingToGroup = ref(false)
function startAddToGroup(p) {
  addTargetPeer.value = p
  showAddToGroup.value = true
}
async function confirmAddToGroup(g) {
  const p = addTargetPeer.value
  if (!p) return
  addingToGroup.value = true
  try {
    await iroh.inviteToGroup(g.id, p.peer_id, p.last_addr || undefined, g.name, g.topic)
    toast(`已邀请 ${p.alias || shortId(p.peer_id)} 加入频道「${g.name}」，等待对方确认`, { type: 'success' })
    showAddToGroup.value = false
  } catch (err) { window.alert('邀请失败：' + (err.message || err)) } finally { addingToGroup.value = false }
}

// ---- context menus ----
const ctxMenu = ref(null)
function toggleMuteConvo(c) {
  const on = iroh.toggleMute(c.id)
  const name = c.name || '会话'
  toast(on ? `已对「${name}」开启消息免打扰` : `已取消「${name}」的消息免打扰`, { type: 'success' })
}

function onDmCtx(e, c) {
  e.preventDefault()
  ctxMenu.value = {
    x: e.clientX, y: e.clientY,
    items: [
      { label: '打开聊天', onClick: () => openConvo(c) },
      { label: '编辑资料', onClick: () => openEdit(c.raw) },
      { label: '邀请加入频道…', onClick: () => startAddToGroup(c.raw) },
      {
        label: iroh.isMuted(c.id) ? '取消消息免打扰' : '消息免打扰',
        onClick: () => toggleMuteConvo(c),
      },
      { label: '删除联系人', danger: true, onClick: () => deleteContact(c.raw) },
    ],
  }
}
function onGroupCtx(e, c) {
  e.preventDefault()
  ctxMenu.value = {
    x: e.clientX, y: e.clientY,
    items: [
      { label: '打开频道', onClick: () => openConvo(c) },
      {
        label: iroh.isMuted(c.id) ? '取消消息免打扰' : '消息免打扰',
        onClick: () => toggleMuteConvo(c),
      },
      { label: '退出频道', onClick: () => leaveChannel(c.raw) },
      { label: '删除频道', danger: true, onClick: () => deleteGroup(c.raw) },
    ],
  }
}

const initials = (name) => name[0]?.toUpperCase() || '?'

// ---- friend request dialog ----
const showFriendRequests = ref(false)

// deterministic pastel avatar color from the id (Telegram-style colored avatars)
const AVATAR_COLORS = ['#e17076', '#eda86c', '#a695e7', '#7bc862', '#6ec9cb', '#65aadd', '#ee7aae']
function avatarColor(id) {
  let h = 0
  for (let i = 0; i < (id || '').length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}
</script>

<template>
  <aside class="flex h-full w-[300px] shrink-0 flex-col border-r border-tg-border bg-tg-panel">
    <!-- header: app title + buttons -->
    <div class="flex h-[52px] shrink-0 items-center justify-between px-4">
      <div class="flex items-center gap-2">
        <span class="text-[17px] font-bold text-white">HoloChat</span>
        <span v-if="iroh.info" class="rounded bg-tg-input px-1.5 py-0.5 font-mono text-[10px] text-tg-textSec" title="本机节点在线状态">
          P2P
        </span>
      </div>
      <div class="flex items-center gap-1">
        <!-- friend request notification button -->
        <button
          v-if="iroh.pendingFriendRequestCount > 0"
          class="relative flex h-8 w-8 items-center justify-center rounded-full text-tg-accent transition-colors duration-150 hover:bg-tg-hover"
          title="好友请求"
          @click="showFriendRequests = true"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/></svg>
          <span class="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-tg-accent px-1 text-[10px] font-bold leading-none text-white">{{ iroh.pendingFriendRequestCount }}</span>
        </button>
        <button
          class="flex h-8 w-8 items-center justify-center rounded-full text-tg-textSec transition-colors duration-150 hover:bg-tg-hover hover:text-white"
          title="新建频道"
          @click="showCreateGroup = true"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        </button>
      </div>
    </div>

    <!-- search box -->
    <div class="px-2 pb-1.5">
      <div class="flex h-9 items-center gap-2 rounded-lg bg-tg-input px-3 transition-colors duration-150 focus-within:bg-[#2b5278]/40">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#7f91a4" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input
          v-model="searchText"
          class="w-full bg-transparent text-[14px] text-white outline-none placeholder:text-tg-textSec"
          placeholder="搜索会话，或粘贴 Iroh 凭证添加联系人"
          @keydown.enter="onAddPeer"
        />
        <button
          v-if="searchText"
          class="shrink-0 text-tg-textSec hover:text-white"
          @click="searchText = ''"
        >✕</button>
      </div>
    </div>

    <!-- tabs -->
    <div class="flex shrink-0 border-b border-tg-border px-2">
      <button
        v-for="t in [
          { key: 'all', label: '全部' },
          { key: 'dms', label: '私聊' },
          { key: 'groups', label: '频道' },
        ]"
        :key="t.key"
        class="relative flex-1 py-2 text-[13px] font-medium transition-colors duration-150"
        :class="activeTab === t.key ? 'text-tg-accent' : 'text-tg-textSec hover:text-white'"
        @click="activeTab = t.key"
      >
        {{ t.label }}
        <span
          v-if="counts[t.key]"
          class="ml-1 rounded-full bg-tg-input px-1.5 text-[10px] leading-4 text-tg-textSec"
        >{{ counts[t.key] }}</span>
        <span
          v-if="activeTab === t.key"
          class="absolute inset-x-3 bottom-0 h-[2px] rounded-full bg-tg-accent"
        />
      </button>
    </div>

    <!-- conversation list -->
    <div class="min-h-0 flex-1 overflow-y-auto px-1.5 py-1">
      <div v-if="!filtered.length" class="px-3 py-8 text-center text-[13px] leading-relaxed text-tg-textSec">
        <template v-if="searchText">
          没有匹配的会话。<br />按 Enter 可将输入内容作为凭证添加新联系人。
        </template>
        <template v-else>还没有会话，粘贴对方 Iroh 凭证添加联系人。</template>
      </div>

      <TransitionGroup name="tg-slide">
        <button
          v-for="c in filtered"
          :key="c.kind + ':' + c.id"
          class="group mb-0.5 flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors duration-150"
          :class="isActive(c) ? 'bg-tg-selected' : 'hover:bg-tg-hover'"
          @click="openConvo(c)"
          @dblclick="c.kind === 'dm' && openEdit(c.raw)"
          @contextmenu="c.kind === 'dm' ? onDmCtx($event, c) : onGroupCtx($event, c)"
        >
          <!-- avatar -->
          <div class="relative shrink-0">
            <img v-if="c.avatar" :src="c.avatar" class="h-[46px] w-[46px] rounded-full object-cover" alt="" />
            <div
              v-else
              class="flex h-[46px] w-[46px] items-center justify-center rounded-full text-[17px] font-bold text-white"
              :style="{ background: c.kind === 'group' ? '#5288c1' : avatarColor(c.id) }"
            >{{ c.kind === 'group' ? '#' : initials(c.name) }}</div>
            <PresenceDot v-if="c.kind === 'dm'" :peer-id="c.id" class="absolute bottom-0 right-0" />
          </div>

          <!-- texts -->
          <div class="min-w-0 flex-1">
            <div class="flex items-baseline gap-2">
              <span class="truncate text-[14px] font-semibold text-white">{{ c.name }}</span>
              <span class="ml-auto shrink-0 text-[11px] text-tg-textSec">{{ formatTime(c.time) }}</span>
            </div>
            <div class="mt-0.5 flex items-center gap-2">
              <span v-if="iroh.isMuted(c.id)" class="shrink-0 text-[12px] text-tg-textSec" title="消息免打扰">🔕</span>
              <span class="truncate text-[13px] text-tg-textSec">{{ c.sub || shortId(c.id) }}</span>
              <span
                v-if="c.unread"
                class="ml-auto flex h-[20px] min-w-[20px] shrink-0 items-center justify-center rounded-full px-1.5 text-[11px] font-bold leading-none text-white tg-pop"
                :class="iroh.isMuted(c.id) ? 'bg-tg-textSec' : 'bg-tg-accent'"
                :key="'u' + c.unread"
              >{{ c.unread > 99 ? '99+' : c.unread }}</span>
            </div>
          </div>
        </button>
      </TransitionGroup>
    </div>

    <!-- bottom: own account card -->
    <UserStatusCard />

    <PeerEditDialog v-if="editingPeer" :peer="editingPeer" :existing="editingExisting" @close="closeDialog" @saved="closeDialog" />

    <!-- create channel dialog -->
    <Transition name="tg-fade">
      <div v-if="showCreateGroup" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showCreateGroup = false">
        <div class="w-80 rounded-xl bg-tg-panel p-5 shadow-2xl tg-pop">
          <div class="mb-3 text-[16px] font-bold text-white">新建频道</div>
          <input
            v-model="newGroupName"
            class="mb-3 w-full rounded-lg bg-tg-input px-3 py-2 text-sm text-white outline-none ring-tg-accent/60 transition focus:ring-2 placeholder:text-tg-textSec"
            placeholder="频道名称，例如：项目讨论"
            @keydown.enter="onCreateGroup"
          />
          <div class="flex justify-end gap-2">
            <button class="rounded-lg px-3 py-1.5 text-sm text-tg-textSec transition hover:text-white" @click="showCreateGroup = false">取消</button>
            <button
              :disabled="creatingGroup"
              class="rounded-lg bg-tg-accent px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-tg-accentHover disabled:opacity-50"
              @click="onCreateGroup"
            >{{ creatingGroup ? '创建中…' : '创建' }}</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- invite contact to channel dialog -->
    <Transition name="tg-fade">
      <div v-if="showAddToGroup" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showAddToGroup = false">
        <div class="w-80 rounded-xl bg-tg-panel p-5 shadow-2xl tg-pop">
          <div class="mb-1 text-[16px] font-bold text-white">邀请联系人加入频道</div>
          <div class="mb-3 truncate text-[12px] text-tg-textSec">{{ addTargetPeer?.alias || shortId(addTargetPeer?.peer_id) }}</div>
          <div v-if="!(iroh.groups || []).length" class="mb-2 rounded-lg bg-tg-input px-3 py-2 text-[12px] text-tg-textSec">
            还没有频道，先点右上角「＋」新建一个。
          </div>
          <div class="max-h-56 overflow-y-auto">
            <button
              v-for="g in iroh.groups"
              :key="g.id"
              class="mb-1 flex w-full items-center gap-2 rounded-lg bg-tg-input px-3 py-2 text-left text-[13px] text-white transition hover:bg-tg-hover disabled:opacity-50"
              :disabled="addingToGroup"
              @click="confirmAddToGroup(g)"
            >
              <span class="text-tg-textSec">#</span>
              <span class="truncate">{{ g.name }}</span>
              <span class="ml-auto shrink-0 text-[10px] text-tg-textSec">{{ (g.members || []).length }} 成员</span>
            </button>
          </div>
          <div class="mt-3 flex justify-end">
            <button class="rounded-lg px-3 py-1.5 text-sm text-tg-textSec hover:text-white" @click="showAddToGroup = false">取消</button>
          </div>
        </div>
      </div>
    </Transition>

    <ContextMenu v-model="ctxMenu" />
    <FriendRequestDialog :visible="showFriendRequests" @close="showFriendRequests = false" />
  </aside>
</template>
