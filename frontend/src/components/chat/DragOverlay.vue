<script setup>
</script>

<template>
  <div class="drag-overlay pointer-events-none fixed inset-0 z-[70] flex items-center justify-center bg-tg-accent/20 backdrop-blur-sm">
    <div class="rounded-2xl border-2 border-dashed border-tg-accent bg-tg-panel/95 px-10 py-8 text-center shadow-2xl">
      <div class="mb-2 text-4xl">📥</div>
      <div class="text-lg font-bold text-white">松开以发送文件</div>
      <div class="text-[12px] text-tg-textSec">拖拽文件到窗口中即可发起 P2P 传输</div>
    </div>
  </div>
</template>
