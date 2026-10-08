<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-vue-next'
import { useToast, type ToastVariant } from '@/composables/useToast'
import { cn } from '@/lib/utils'

const { items, dismiss } = useToast()

const meta: Record<ToastVariant, { icon: unknown; color: string }> = {
  success: { icon: CheckCircle2, color: 'text-ok' },
  error: { icon: XCircle, color: 'text-danger' },
  warning: { icon: AlertTriangle, color: 'text-warn' },
  info: { icon: Info, color: 'text-accent' },
}
</script>

<template>
  <div
    class="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2"
    role="region"
    aria-label="通知"
  >
    <TransitionGroup name="toast">
      <div
        v-for="t in items"
        :key="t.id"
        class="pointer-events-auto flex items-start gap-2.5 rounded-lg border border-line bg-surface px-3.5 py-2.5 shadow-lg shadow-ink/10"
      >
        <component
          :is="meta[t.variant].icon"
          :class="cn('mt-px size-4 shrink-0', meta[t.variant].color)"
          aria-hidden="true"
        />
        <p class="flex-1 text-[13px] leading-5 text-ink-2">{{ t.message }}</p>
        <button
          type="button"
          class="shrink-0 rounded p-0.5 text-ink-4 transition-colors hover:bg-surface-muted hover:text-ink"
          aria-label="关闭通知"
          @click="dismiss(t.id)"
        >
          <X class="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: opacity 180ms cubic-bezier(0.16, 1, 0.3, 1),
    transform 180ms cubic-bezier(0.16, 1, 0.3, 1);
}
.toast-enter-from { opacity: 0; transform: translateY(8px) scale(0.98); }
.toast-leave-to { opacity: 0; transform: translateX(12px); }
.toast-move { transition: transform 180ms ease; }
</style>