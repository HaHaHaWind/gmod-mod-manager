<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const badgeVariants = cva(
  'inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] font-medium leading-[16px]',
  {
    variants: {
      variant: {
        neutral: 'border-line bg-surface-muted text-ink-3',
        accent: 'border-accent-line bg-accent-soft text-accent-strong',
        success: 'border-ok/25 bg-ok-soft text-ok',
        warning: 'border-warn/25 bg-warn-soft text-warn',
        danger: 'border-danger/25 bg-danger-soft text-danger',
        outline: 'border-line bg-surface text-ink-3',
      },
    },
    defaultVariants: { variant: 'neutral' },
  },
)

type Variants = VariantProps<typeof badgeVariants>

const props = withDefaults(
  defineProps<{ variant?: Variants['variant']; mono?: boolean }>(),
  { variant: 'neutral' },
)

const attrs = useAttrs()
const classes = computed(() =>
  cn(badgeVariants({ variant: props.variant }), props.mono && 'font-mono', attrs.class as string),
)
</script>

<template>
  <span :class="classes"><slot /></span>
</template>