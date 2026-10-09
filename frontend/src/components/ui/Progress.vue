<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
      value?: number
      tone?: 'accent' | 'success' | 'danger'
      indeterminate?: boolean
      class?: string
    }>(),
    { tone: 'accent', indeterminate: false },
  )

const pct = computed(() => Math.max(0, Math.min(100, Math.round(props.value ?? 0))))
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
    :aria-valuenow="indeterminate ? undefined : pct"
    :aria-busy="indeterminate ? 'true' : undefined"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <div
      v-if="indeterminate"
      class="progress-indeterminate h-full w-1/3 rounded-full"
      :class="toneClass[props.tone]"
    />
    <div
      v-else
      :class="cn('h-full rounded-full transition-[width] duration-300 ease-out', toneClass[props.tone])"
      :style="{ width: `${pct}%` }"
    />
  </div>
</template>

<style scoped>
@media (prefers-reduced-motion: no-preference) {
  .progress-indeterminate {
    animation: progress-slide 1.4s ease-in-out infinite;
  }
  @keyframes progress-slide {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(400%); }
  }
}
</style>