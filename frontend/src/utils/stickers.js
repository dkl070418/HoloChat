/**
 * Sticker helpers: map a :shortcode: in message content to a locally-bundled
 * OpenMoji image. The sticker library ships with the app (frontend/public/stickers)
 * so sending a sticker only transfers its shortcode text — the receiver renders
 * the same image from its own copy. No image bytes cross the wire.
 */
let map = null        // { shortcode: hex }
let manifest = null   // [{s,h,e}]
let loadPromise = null

/** Load the shortcode->hex mapping (fetched once, cached). */
export async function loadStickerMap() {
  if (!loadPromise) {
    loadPromise = (async () => {
      try {
        const [m, man] = await Promise.all([
          fetch('/stickers/shortcode-map.json').then((r) => (r.ok ? r.json() : {})),
          fetch('/stickers/sticker-manifest.json').then((r) => (r.ok ? r.json() : [])),
        ])
        map = m || {}
        manifest = Array.isArray(man) ? man : []
      } catch (e) {
        map = {}
        manifest = []
        console.error('loadStickerMap', e)
      }
    })()
  }
  await loadPromise
  return { map: map || {}, manifest: manifest || [] }
}

/** URL for a shortcode, or null if unknown. */
export function stickerUrl(shortcode) {
  if (!map) return null
  const hex = map[shortcode]
  return hex ? `/stickers/${hex}.png` : null
}

/** True when a message's whole content is exactly one sticker shortcode. */
export function isSingleSticker(content) {
  if (!content) return false
  const m = /^\s*::([a-z0-9_]+)::\s*$/.exec(content)
  if (!m) return false
  return !!stickerUrl(m[1])
}

/** Extract all :shortcode: tokens present in text (for mixed rendering later). */
export function extractStickerCodes(text) {
  const out = []
  if (!text) return out
  const re = /::([a-z0-9_]+)::/g
  let m
  while ((m = re.exec(text))) out.push(m[1])
  return out
}
