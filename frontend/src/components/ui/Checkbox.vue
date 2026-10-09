<script setup lang="ts">
import { Check, Minus } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    label?: string
    indeterminate?: boolean
    disabled?: boolean
    ariaLabel?: string
  }>(),
  { label: '', indeterminate: false, disabled: false },
)

const model = defineModel<boolean>({ default: false })
</script>

<template>
  <label
    :class="cn(
      'inline-flex select-none items-center gap-2 text-[13px] leading-4 text-ink-2',
      props.disabled ? 'cursor-not-allowed opacity-55' : 'cursor-pointer',
    )"
  >
    <span class="relative inline-flex size-4 shrink-0 items-center justify-center">
      <input
        v-model="model"
        type="checkbox"
        :disabled="props.disabled"
        :indeterminate="props.indeterminate"
        :aria-label="props.ariaLabel || props.label || undefined"
        :class="cn(
          'size-4 appearance-none rounded-[5px] border bg-surface transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/35',
          props.disabled ? 'cursor-not-allowed' : 'cursor-pointer',
          model || props.indeterminate
            ? 'border-accent bg-accent'
            : 'border-line-strong hover:border-accent',
        )"
      >
      <Minus v-if="props.indeterminate" class="pointer-events-none absolute size-3 text-white" aria-hidden="true" />
      <Check v-else-if="model" class="pointer-events-none absolute size-3 text-white" aria-hidden="true" />
    </span>
    <span v-if="props.label">{{ props.label }}</span>
  </label>
</template>