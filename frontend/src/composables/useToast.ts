import { ref } from 'vue'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: number
  variant: ToastVariant
  message: string
}

/** 全局单例队列:由 App 内的 Toaster 渲染。 */
const items = ref<ToastItem[]>([])
let seq = 0

function push(variant: ToastVariant, message: string, duration: number) {
  const id = ++seq
  items.value = [...items.value, { id, variant, message }]
  window.setTimeout(() => dismiss(id), duration)
}

export function dismiss(id: number): void {
  items.value = items.value.filter((t) => t.id !== id)
}

export const toast = {
  success: (message: string) => push('success', message, 3000),
  error: (message: string) => push('error', message, 5200),
  warning: (message: string) => push('warning', message, 4200),
  info: (message: string) => push('info', message, 3200),
}

export function useToast() {
  return { items, dismiss, toast }
}