<script setup lang="ts">
/** 复制按钮:点击复制指定文本,成功后图标切换为对勾作为反馈。 */
import { ref } from 'vue'
import { Check, Copy } from 'lucide-vue-next'
import { copyText } from '@/utils/format'

const props = defineProps<{ text: string; label?: string }>()

const copied = ref(false)
let timer: number | undefined

async function onCopy() {
  const ok = await copyText(props.text)
  if (!ok) return
  copied.value = true
  window.clearTimeout(timer)
  timer = window.setTimeout(() => { copied.value = false }, 1600)
}
</script>

<template>
  <button
    type="button"
    class="inline-flex size-6 shrink-0 items-center justify-center rounded-md border border-line bg-surface text-ink-3 transition-colors duration-150 hover:bg-surface-muted hover:text-ink"
    :aria-label="label ? `复制${label}` : '复制'"
    :title="copied ? '已复制' : '复制'"
    @click="onCopy"
  >
    <Check v-if="copied" class="size-3.5 text-ok" aria-hidden="true" />
    <Copy v-else class="size-3.5" aria-hidden="true" />
  </button>
</template>
