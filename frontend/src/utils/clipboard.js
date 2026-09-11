// 可靠复制到剪贴板：优先 navigator.clipboard（仅 secure context），失败回退
// hidden textarea + document.execCommand('copy')。无论成败都给出 toast 反馈。
import { toast } from './toast'

/**
 * 复制文本并提示。
 * @param {string} text 要复制的文本
 * @param {string} [label] 反馈文案里的名称，如 '凭证'、'Node ID'
 * @returns {Promise<boolean>}
 */
export async function copyText(text, label = '内容') {
  const t = text || ''
  let ok = false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(t)
      ok = true
    }
  } catch (e) {
    ok = false
  }
  if (!ok) {
    try {
      const ta = document.createElement('textarea')
      ta.value = t
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      ta.readOnly = true
      document.body.appendChild(ta)
      ta.select()
      ok = document.execCommand('copy')
      ta.remove()
    } catch (e) {
      ok = false
    }
  }
  if (t && ok) toast(`已复制${label} ✓`, { type: 'success' })
  else toast('复制失败，请手动选择复制', { type: 'error' })
  return ok
}
