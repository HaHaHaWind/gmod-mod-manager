<script lang="ts">
import type { Tone } from '@/utils/format'

export interface SpecItem {
  label: string
  value?: string
  note?: string
  badge?: string
  tone?: Tone
  mono?: boolean
}
</script>

<script setup lang="ts">
import { computed } from 'vue'
import Badge from './Badge.vue'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{ items: SpecItem[]; cols?: 2 | 3 | 5 }>(), { cols: 2 })

const colsClass = computed(() => {
  if (props.cols === 5) return 'grid-cols-2 sm:grid-cols-5'
  if (props.cols === 3) return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
  return 'grid-cols-1 sm:grid-cols-2'
})
</script>

<template>
  <div :class="cn('grid gap-px overflow-hidden rounded-lg border border-line bg-line', colsClass)">
    <div
      v-for="it in items"
      :key="it.label"
      class="flex flex-col gap-0.5 bg-surface px-3 py-2.5"
    >
      <span class="text-[11.5px] text-ink-4">{{ it.label }}</span>
      <div class="flex flex-wrap items-baseline gap-1.5">
        <Badge v-if="it.badge" :variant="it.tone">{{ it.badge }}</Badge>
        <span
          v-if="it.value !== undefined"
          :class="cn('text-[13px] text-ink', it.mono && 'mono break-all')"
        >{{ it.value }}</span>
        <span v-if="it.note" class="small muted">{{ it.note }}</span>
      </div>
    </div>
  </div>
</template>