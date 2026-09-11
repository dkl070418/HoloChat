<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

const props = defineProps({ text: { type: String, default: '' } })

marked.setOptions({ breaks: true, gfm: true })

/** Strip dangerous HTML (scripts/iframes/on-handlers/javascript links). */
function sanitize(html) {
  return String(html)
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, '')
    .replace(/\s+on\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]*)/gi, '')
    .replace(/(href|src)\s*=\s*("|')javascript:[^"']*\2/gi, '')
}

function render(text) {
  try {
    return sanitize(marked.parse(text || '') || '')
  } catch (e) {
    return sanitize(String(text || ''))
  }
}

const html = ref('')
const rootEl = ref(null)

function highlight() {
  const root = rootEl.value
  if (!root) return
  root.querySelectorAll('pre code').forEach((el) => {
    const langMatch = (el.className || '').match(/language-(\w+)/)
    const lang = langMatch ? langMatch[1] : ''
    let result = ''
    if (lang && hljs.getLanguage(lang)) {
      try { result = hljs.highlight(el.textContent, { language: lang }).value } catch { result = '' }
    }
    if (!result) {
      try { result = hljs.highlightAuto(el.textContent).value } catch { result = '' }
    }
    if (result) el.innerHTML = result
  })
}

watch(() => props.text, async () => {
  html.value = render(props.text)
  await nextTick()
  highlight()
}, { immediate: true })

onMounted(() => nextTick(highlight))
</script>

<template>
  <div
    ref="rootEl"
    class="markdown-body break-words [&_a]:text-tg-textLink [&_a]:underline [&_pre]:bg-black/30 [&_pre]:rounded-lg [&_pre]:p-2 [&_pre]:overflow-x-auto [&_pre]:my-1 [&_code]:text-[12px] [&_pre_code]:bg-transparent [&_blockquote]:border-l-4 [&_blockquote]:border-tg-accent [&_blockquote]:pl-2 [&_blockquote]:text-tg-textSec [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5"
    v-html="html"
  />
</template>
