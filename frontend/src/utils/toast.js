// 极简全局 toast：无依赖、不引入组件树，动态插入 DOM 提示条，自动消失。
// 用法：import { toast } from '../utils/toast'; toast('已复制凭证', { type: 'success' })

let container = null

function ensureContainer() {
  if (!container) {
    container = document.createElement('div')
    container.style.cssText =
      'position:fixed;left:50%;bottom:30px;transform:translateX(-50%);z-index:99999;' +
      'display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;'
    document.body.appendChild(container)
  }
  return container
}

/**
 * 显示一条轻提示。
 * @param {string} msg 提示文本
 * @param {{type?: 'info'|'success'|'error', duration?: number}} [opts]
 */
export function toast(msg, { type = 'info', duration = 1800 } = {}) {
  const el = document.createElement('div')
  const bg =
    type === 'success' ? 'rgba(16,95,52,0.95)' :
    type === 'error' ? 'rgba(153,27,27,0.95)' :
    'rgba(34,34,52,0.95)'
  el.textContent = msg
  el.style.cssText =
    `background:${bg};color:#fff;border:1px solid rgba(255,255,255,0.16);` +
    'padding:7px 15px;border-radius:8px;font-size:12.5px;' +
    'box-shadow:0 8px 24px rgba(0,0,0,0.4);opacity:0;transform:translateY(6px);' +
    'transition:opacity 0.18s ease,transform 0.18s ease;max-width:82vw;text-align:center;'
  ensureContainer().appendChild(el)
  requestAnimationFrame(() => {
    el.style.opacity = '1'
    el.style.transform = 'translateY(0)'
  })
  setTimeout(() => {
    el.style.opacity = '0'
    el.style.transform = 'translateY(6px)'
    setTimeout(() => el.remove(), 220)
  }, duration)
  return el
}
