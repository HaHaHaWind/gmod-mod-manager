<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'

defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
    <div class="flex size-11 items-center justify-center rounded-full bg-surface-muted text-ink-4">
      <slot name="icon"><Inbox class="size-5" aria-hidden="true" /></slot>
    </div>
    <p class="text-[13.5px] font-medium text-ink-2">{{ title }}</p>
    <p v-if="description" class="max-w-sm text-[12px] leading-5 text-ink-3">{{ description }}</p>
    <div v-if="$slots.action" class="mt-1"><slot name="action" /></div>
  </div>
</template>