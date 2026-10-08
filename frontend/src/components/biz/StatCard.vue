<script setup lang="ts">
import type { Component } from 'vue'
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
</script>

<template>
  <div class="flex items-start justify-between gap-3 rounded-2xl border border-line bg-surface p-5 shadow-card">
    <div class="min-w-0">
      <p class="text-[12px] font-medium text-ink-3">{{ label }}</p>
      <p class="mt-1.5 text-[28px] font-semibold leading-8 tracking-tight text-ink num">{{ value }}</p>
      <p v-if="hint" class="mt-1 text-[11.5px] leading-4 text-ink-4">{{ hint }}</p>
    </div>
    <span
      v-if="icon"
      :class="cn('flex size-10 shrink-0 items-center justify-center rounded-xl', chip[tone])"
    >
      <component :is="icon" class="size-5" aria-hidden="true" />
    </span>
  </div>
</template>