<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    value: number
    tone?: 'accent' | 'success' | 'danger'
    class?: string
  }>(),
  { tone: 'accent' },
)

const pct = computed(() => Math.max(0, Math.min(100, Math.round(props.value))))
const toneClass: Record<'accent' | 'success' | 'danger', string> = {
  accent: 'bg-accent',
  success: 'bg-ok',
  danger: 'bg-danger',
}
</script>

<template>
  <div
    :class="cn('h-2 w-full overflow-hidden rounded-full bg-surface-sunken', props.class)"
    role="progressbar"
    :aria-valuenow="pct"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <div
      :class="cn('h-full rounded-full transition-[width] duration-300 ease-out', toneClass[props.tone])"
      :style="{ width: `${pct}%` }"
    />
  </div>
</template>