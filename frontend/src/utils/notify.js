/**
 * Browser notifications + soft message chime (Scene A: in-page notifications).
 *
 * No Service Worker / Push / server needed — we only fire native browser
 * notifications from the live WebSocket events while the page is open, plus a
 * gentle synthesized chime and a title-tab unread badge. The notification
 * sound can be toggled by the user (persisted to localStorage).
 */
import { ref } from 'vue'

const SOUND_KEY = 'iroh_sound_on'
export const soundOn = ref(localStorage.getItem(SOUND_KEY) !== '0')
let audioCtx = null

export function getSoundOn() { return soundOn.value }
export function setSoundOn(v) {
  soundOn.value = !!v
  try { localStorage.setItem(SOUND_KEY, soundOn.value ? '1' : '0') } catch { /* ignore */ }
}
export function toggleSound() { setSoundOn(!soundOn.value); return soundOn.value }

/* ---- browser Notification permission ---- */
export function notificationsSupported() {
  return typeof window !== 'undefined' && 'Notification' in window
}

export function notificationPermission() {
  if (!notificationsSupported()) return 'unsupported'
  return Notification.permission
}

/** Ask the user once (only when not already decided). Returns the permission. */
export async function requestNotificationPermission() {
  if (!notificationsSupported()) return 'unsupported'
  if (Notification.permission === 'granted' || Notification.permission === 'denied') {
    return Notification.permission
  }
  try {
    return await Notification.requestPermission()
  } catch { return 'denied' }
}

/** Show a native browser notification when permitted. Clicks focus the window. */
export function notify({ title, body, icon, tag }) {
  if (!notificationsSupported() || Notification.permission !== 'granted') return
  try {
    const n = new Notification(title, {
      body: body || '',
      icon: icon || undefined,
      tag: tag || undefined,
      silent: true,
    })
    n.onclick = () => {
      try { window.focus() } catch { /* ignore */ }
      n.close()
    }
  } catch { /* ignore */ }
}

/* ---- soft synthesized chime (Web Audio, no asset file) ---- */
export function playMessageSound() {
  if (!soundOn.value) return
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)()
    if (audioCtx.state === 'suspended') audioCtx.resume()
    // two gentle sine tones, low volume, quick decay => a soft "ding"
    tone(audioCtx, 740, 0.0, 0.14, 0.09)
    tone(audioCtx, 988, 0.12, 0.14, 0.12)
  } catch { /* ignore */ }
}

function tone(ctx, freq, start, gain, dur) {
  const osc = ctx.createOscillator()
  const g = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.value = freq
  g.gain.setValueAtTime(0.0001, ctx.currentTime + start)
  g.gain.exponentialRampToValueAtTime(gain, ctx.currentTime + start + 0.015)
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + dur)
  osc.connect(g)
  g.connect(ctx.destination)
  osc.start(ctx.currentTime + start)
  osc.stop(ctx.currentTime + start + dur + 0.02)
}

/**
 * Unread tab-title badge — shows "(N)" + the message summary while the tab is
 * hidden; clears whenever the document becomes visible again.
 */
const DEFAULT_TITLE = document.title
let unread = 0
let summary = ''

export function resetTitle() {
  unread = 0
  summary = ''
  document.title = DEFAULT_TITLE
}

export function bumpUnread(text) {
  unread += 1
  summary = text || summary
  if (!document.hidden) return // visible tab: no need to badge
  document.title = `(${unread}) ${summary}`
}

export function initTitleListener() {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) resetTitle()
  })
}
