import { ref } from 'vue'

export interface ConfirmOptions {
  title: string
  description?: string
  confirmText?: string
  cancelText?: string
  /** 危险操作:确认按钮用危险色,并提示不可恢复。 */
  danger?: boolean
}

interface ConfirmState extends ConfirmOptions {
  open: boolean
}

const state = ref<ConfirmState | null>(null)
let resolver: ((ok: boolean) => void) | null = null

/** 以 Promise 形式弹出确认框:await 得到 true/false,替代命令式弹窗。 */
export function confirmDialog(opts: ConfirmOptions): Promise<boolean> {
  if (resolver) {
    resolver(false)
    resolver = null
  }
  state.value = { open: true, ...opts }
  return new Promise<boolean>((resolve) => {
    resolver = resolve
  })
}

export function settleConfirm(ok: boolean): void {
  state.value = null
  const done = resolver
  resolver = null
  done?.(ok)
}

export function useConfirm() {
  return { state, settleConfirm }
}