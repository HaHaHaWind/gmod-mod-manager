import { onMounted, onUnmounted, ref } from 'vue'

/**
 * 定时轮询:挂载后立即执行一次,随后按 interval 重复。
 * - 上一轮未结束时跳过本次触发,避免慢请求堆叠;
 * - 页面切到后台自动暂停,回到前台立即补一次;
 * - 组件卸载时清理定时器与监听。
 */
export function usePolling(
  fn: () => void | Promise<void>,
  interval: number,
  opts: { immediate?: boolean } = {},
) {
  const immediate = opts.immediate ?? true
  const busy = ref(false)
  let timer: number | undefined

  async function tick() {
    if (busy.value) return
    busy.value = true
    try {
      await fn()
    } finally {
      busy.value = false
    }
  }

  function start() {
    if (timer === undefined) timer = window.setInterval(tick, interval)
  }

  function stop() {
    if (timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
    }
  }

  function onVisibility() {
    if (document.hidden) {
      stop()
    } else {
      start()
      void tick()
    }
  }

  onMounted(() => {
    if (immediate) void tick()
    start()
    document.addEventListener('visibilitychange', onVisibility)
  })

  onUnmounted(() => {
    stop()
    document.removeEventListener('visibilitychange', onVisibility)
  })

  return { tick, start, stop, busy }
}