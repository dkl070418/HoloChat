<script setup>
import { ref } from 'vue'
import { toast } from '../../utils/toast'
import { useIrohStore } from '../../stores/iroh'
import { shortId } from '../../utils/format'

const props = defineProps({
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

const iroh = useIrohStore()
const mode = ref('')            // '' | 'generate' | 'import'
const importKey = ref('')
const busy = ref(false)
const fileName = ref('')

/** Pick a secret.key file directly — browsers can't paste raw binary, so we
 * read the file as base64 and send it with the "b64:" prefix the backend
 * import_secret understands (raw file-bytes path). */
function pickKeyFile(e) {
  const f = e.target?.files?.[0]
  if (!f) return
  fileName.value = f.name
  const r = new FileReader()
  r.onload = () => {
    // r.result = "data:application/octet-stream;base64,<payload>"
    const payload = String(r.result).split(',')[1] || ''
    importKey.value = 'b64:' + payload
  }
  r.readAsDataURL(f)
}

async function doGenerate() {
  if (busy.value) return
  busy.value = true
  try {
    await iroh.identityGenerate()
    toast('已生成新的身份密钥，重启应用后生效', { type: 'success' })
    emit('close')
  } catch (e) {
    window.alert('生成失败：' + (e.message || e))
  } finally { busy.value = false }
}

async function doImport() {
  const key = importKey.value.trim()
  if (!key) { toast('请粘贴私钥内容', { type: 'error' }); return }
  if (busy.value) return
  busy.value = true
  try {
    await iroh.identityImport(key)
    toast('已导入身份密钥，重启应用后生效', { type: 'success' })
    emit('close')
  } catch (e) {
    window.alert('导入失败：' + (e.message || e))
  } finally { busy.value = false }
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-[110] flex items-center justify-center bg-black/60"
    @click.self="emit('close')"
  >
    <div class="w-[26rem] rounded-lg bg-tg-panel p-5 shadow-2xl">
      <div class="mb-1 text-[17px] font-bold text-white">设置你的身份</div>
      <div class="mb-4 text-[12px] leading-relaxed text-tg-textSec">
        首次启动没有找到身份密钥。你的节点身份决定了你的 Node ID 和凭证，
        设置后需要<b class="text-white/90">重启应用</b>才会生效。
      </div>

      <!-- generate -->
      <div class="mb-2 rounded-md bg-tg-input p-3" :class="mode === 'generate' ? 'ring-1 ring-tg-accent' : ''">
        <div class="mb-1 text-[14px] font-semibold text-white">生成新的身份</div>
        <div class="mb-2 text-[11px] text-tg-textSec">自动生成一套全新的密钥，得到一个新的 Node ID。</div>
        <div class="flex justify-end">
          <button
            class="rounded bg-tg-accent px-3 py-1.5 text-[13px] font-semibold text-white transition hover:bg-tg-accentHover disabled:opacity-50"
            :disabled="busy"
            @click="doGenerate"
          >{{ busy ? '处理中…' : '生成并设为我的身份' }}</button>
        </div>
      </div>

      <!-- import -->
      <div class="rounded-md bg-tg-input p-3" :class="mode === 'import' ? 'ring-1 ring-tg-accent' : ''">
        <div class="mb-1 text-[14px] font-semibold text-white">导入已有私钥</div>
        <div class="mb-2 text-[11px] text-tg-textSec">直接选择旧的 secret.key 文件，或粘贴密钥文本（Base64 / 十六进制）。</div>

        <!-- file picker (recommended: works with the raw binary key file) -->
        <label
          class="mb-2 flex cursor-pointer items-center gap-2 rounded bg-tg-bg px-2 py-1.5 text-[12px] text-tg-textSec transition hover:bg-black/30 hover:text-white"
          @click="mode = 'import'"
        >
          <span class="rounded bg-tg-accent px-2 py-0.5 text-[11px] font-semibold text-white">选择文件</span>
          <span class="truncate">{{ fileName || '选择旧的 secret.key 文件…' }}</span>
          <input type="file" class="hidden" accept=".key,.bin,application/octet-stream" @change="pickKeyFile" />
        </label>

        <textarea
          v-model="importKey"
          class="mb-2 h-16 w-full resize-none rounded bg-tg-bg px-2 py-1.5 font-mono text-[11px] text-white outline-none placeholder:text-tg-textSec"
          placeholder="或粘贴 Base64 / 十六进制密钥文本…"
        />
        <div class="flex justify-end">
          <button
            class="rounded bg-tg-accent px-3 py-1.5 text-[13px] font-semibold text-white transition hover:bg-tg-accentHover disabled:opacity-50"
            :disabled="busy || !importKey.trim()"
            @click="doImport"
          >{{ busy ? '处理中…' : '导入此身份' }}</button>
        </div>
      </div>

      <div class="mt-3 flex items-center justify-between">
        <span class="text-[11px] text-tg-textSec">
          当前节点 ID：{{ shortId(iroh.info?.id) }}…
        </span>
        <button class="rounded px-2 py-1 text-[12px] text-tg-textSec hover:text-white" @click="emit('close')">稍后再说</button>
      </div>
    </div>
  </div>
</template>
