<script setup lang="ts">
import {
  DialogClose, DialogContent, DialogDescription, DialogOverlay,
  DialogPortal, DialogRoot, DialogTitle,
} from 'reka-ui'
import { X } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

const open = defineModel<boolean>('open', { default: false })

const props = withDefaults(
  defineProps<{
    title?: string
    description?: string
    widthClass?: string
  }>(),
  { widthClass: 'max-w-lg' },
)
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay
        class="fixed inset-0 z-50 bg-black/45 backdrop-blur-[4px] backdrop-saturate-[1.1] data-[state=open]:animate-ui-in"
      />
      <DialogContent
        :class="cn(
          'fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2',
          'flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-pop focus:outline-none',
          props.widthClass,
        )"
      >
        <header class="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div class="min-w-0">
            <DialogTitle class="text-[15px] font-semibold tracking-tight text-ink">{{ title }}</DialogTitle>
            <DialogDescription class="mt-0.5 text-[12.5px] leading-5 text-ink-3">
              {{ description }}
            </DialogDescription>
          </div>
          <DialogClose
            class="shrink-0 rounded-lg p-1 text-ink-4 transition-colors hover:bg-surface-muted hover:text-ink"
            aria-label="关闭"
          >
            <X class="size-4" aria-hidden="true" />
          </DialogClose>
        </header>
        <div class="min-h-0 flex-1 overflow-auto px-6 py-5">
          <slot />
        </div>
        <footer
          v-if="$slots.footer"
          class="flex items-center justify-end gap-2 border-t border-line px-6 py-4"
        >
          <slot name="footer" />
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>