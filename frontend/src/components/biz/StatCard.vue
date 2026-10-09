<script setup lang="ts">
import { onBeforeUnmount, ref, watch, type Component } from 'vue'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    label: string
    value: number | string
    hint?: string
    icon?: Component
    tone?: 'accent' | 'success' | 'warning' | 'danger' | 'neutral'
  }>(),
  { tone: 'neutral' },
)

const chip: Record<NonNullable<typeof props.tone>, string> = {
  accent: 'bg-accent-soft text-accent',
  success: 'bg-ok-soft text-ok',
  warning: 'bg-warn-soft text-warn',
  danger: 'bg-danger-soft text-danger',
  neutral: 'bg-surface-muted text-ink-3',
}

/* 数字滚动:值变化时 rAF 计数过渡(ease-out),非数值直接显示;尊重减少动态偏好 */
const shown = ref<number | string>(props.value)
let raf = 0
const reduceMotion = typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches
watch(() => props.value, (v) => {
  if (typeof v !== 'number' || reduceMotion) {
    shown.value = v
    return
  }
  const target = v
  const from = typeof shown.value === 'number' ? shown.value : 0
  cancelAnimationFrame(raf)
  if (from === target) {
    shown.value = target
    return
  }
  const t0 = performance.now()
  const dur = 520
  const ease = (t: number) => 1 - Math.pow(1 - t, 3)
  const step = (now: number) => {
    const p = Math.min(1, (now - t0) / dur)
    shown.value = Math.round(from + (target - from) * ease(p))
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}, { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <div
    class="flex items-start justify-between gap-3 rounded-xl border border-card-border bg-surface p-5 shadow-card transition-[box-shadow] duration-[400ms] ease-in-out hover:shadow-card-hover"
  >
    <div class="min-w-0">
      <p class="text-[12px] font-medium text-ink-3">{{ label }}</p>
      <p class="mt-1.5 text-[28px] font-semibold leading-8 tracking-tight text-ink num">{{ shown }}</p>
      <p v-if="hint" class="mt-1 text-[11.5px] leading-4 text-ink-4">{{ hint }}</p>
    </div>
    <span
      v-if="icon"
      :class="cn('flex size-10 shrink-0 items-center justify-center rounded-lg', chip[tone])"
    >
      <component :is="icon" class="size-5" aria-hidden="true" />
    </span>
  </div>
</template>