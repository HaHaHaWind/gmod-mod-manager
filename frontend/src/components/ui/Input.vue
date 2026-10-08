<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    type?: string
    placeholder?: string
    disabled?: boolean
    autocomplete?: string
    ariaLabel?: string
  }>(),
  { type: 'text' },
)

const model = defineModel<string>({ default: '' })
const attrs = useAttrs()
const restAttrs = computed(() => {
  const { class: _ignored, ...rest } = attrs
  return rest
})
const classes = computed(() =>
  cn(
    'h-[34px] w-full rounded-lg border border-line bg-surface px-3 text-[13px] text-ink transition-colors',
    'placeholder:text-ink-4 hover:border-line-strong',
    'focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25',
    'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-3',
    attrs.class as string,
  ),
)
</script>

<template>
  <input
    v-bind="restAttrs"
    v-model="model"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    :autocomplete="autocomplete"
    :aria-label="ariaLabel"
    :class="classes"
  />
</template>