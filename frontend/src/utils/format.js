/** Formatting helpers shared across components. */

export function formatBytes(n) {
  if (!n && n !== 0) return '—'
  if (n === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatSpeed(bps) {
  if (bps == null || bps <= 0) return ''
  return `${formatBytes(bps)}/s`
}

export function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const hm = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return hm
  return `${d.getMonth() + 1}/${d.getDate()} ${hm}`
}

export function shortId(id) {
  if (!id) return ''
  return id.length > 12 ? id.slice(0, 12) : id
}

export function shortAddr(addr) {
  // addr form: <64hex> addrs=[...] relay=...
  if (!addr) return ''
  return addr.slice(0, 12) + '…'
}

export function fileExtension(filename) {
  const i = filename.lastIndexOf('.')
  return i >= 0 ? filename.slice(i + 1).toLowerCase() : ''
}

/** Detect whether a filename is an image, video or audio for preview. */
export function mediaKind(filename) {
  const ext = fileExtension(filename)
  const img = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp']
  const vid = ['mp4', 'webm', 'mov', 'mkv', 'm4v']
  const aud = ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac']
  if (img.includes(ext)) return 'image'
  if (vid.includes(ext)) return 'video'
  if (aud.includes(ext)) return 'audio'
  return 'file'
}
