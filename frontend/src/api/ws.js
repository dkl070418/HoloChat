/** Reconnecting WebSocket service that fans incoming events to a callback. */
import { reactive } from 'vue'
import { api } from './client'
import { useIrohStore } from '../stores/iroh'
import { useChatStore } from '../stores/chat'

let ws = null
let reconnectTimer = null
const listeners = new Set()

export function onWsEvent(fn) { listeners.add(fn); return () => listeners.delete(fn) }

function dispatch(data) {
  for (const fn of listeners) {
    try { fn(data) } catch (e) { console.error(e) }
  }
}

export function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws`)
  ws.onmessage = (e) => {
    let data
    try { data = JSON.parse(e.data) } catch { return }
    dispatch(data)
  }
  ws.onclose = () => {
    reconnectTimer = setTimeout(connect, 1500)
  }
}

export function sendControl(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload))
}
