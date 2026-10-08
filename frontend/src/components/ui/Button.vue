<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const buttonVariants = cva(
  'inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-xl border font-medium ' +
    'transition-all duration-150 active:scale-[0.985] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/35 ' +
    'disabled:pointer-events-none disabled:opacity-45 disabled:active:scale-100',
  {
    variants: {
      variant: {
        primary:
          'border-transparent bg-accent text-white shadow-[0_1px_2px_rgb(13_21_34/0.10)] hover:bg-accent-strong hover:shadow-[0_2px_8px_rgb(37_99_235/0.28)]',
        secondary:
          'border-line bg-surface text-ink-2 shadow-[0_1px_2px_rgb(13_21_34/0.04)] hover:border-line-strong hover:bg-surface-muted hover:text-ink',
        ghost: 'border-transparent bg-transparent text-ink-3 hover:bg-surface-muted hover:text-ink',
        success: 'border-transparent bg-ok text-white shadow-[0_1px_2px_rgb(13_21_34/0.10)] hover:bg-ok/90',
        danger: 'border-transparent bg-danger text-white shadow-[0_1px_2px_rgb(13_21_34/0.10)] hover:bg-danger/90',
        'danger-outline': 'border-danger/35 bg-surface text-danger hover:bg-danger-soft',
      },
      size: {
        sm: 'h-8 px-3 text-[12.5px]',
        md: 'h-9 px-3.5 text-[13px]',
        lg: 'h-10 px-5 text-[13.5px]',
        icon: 'h-9 w-9 p-0',
        'icon-sm': 'h-8 w-8 p-0',
      },
    },
    defaultVariants: { variant: 'secondary', size: 'md' },
  },
)

type Variants = VariantProps<typeof buttonVariants>

const props = withDefaults(
  defineProps<{
    variant?: Variants['variant']
    size?: Variants['size']
    loading?: boolean
    disabled?: boolean
    type?: 'button' | 'submit' | 'reset'
  }>(),
  { variant: 'secondary', size: 'md', type: 'button' },
)

const attrs = useAttrs()
const restAttrs = computed(() => {
  const { class: _ignored, ...rest } = attrs
  return rest
})
const classes = computed(() =>
  cn(buttonVariants({ variant: props.variant, size: props.size }), attrs.class as string),
)
</script>

<template>
  <button
    v-bind="restAttrs"
    :type="type"
    :class="classes"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <Loader2 v-if="loading" class="size-3.5 shrink-0 animate-spin" aria-hidden="true" />
    <slot />
  </button>
</template>