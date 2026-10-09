<script setup lang="ts">
/**
 * 顶部路由加载进度条(NProgress 风格):
 * 路由开始时快速推进到 30%,随后缓慢爬升;完成后冲顶 100% 再淡出。
 * 覆盖懒加载 chunk 与会话探测期间的等待反馈。
 */
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const visible = ref(false)
const width = ref(0)

let running = false
let slowTimers: number[] = []
let hideTimer: number | undefined

function clearSlow() {
  slowTimers.forEach((t) => window.clearTimeout(t))
  slowTimers = []
}

function start() {
  if (running) return
  running = true
  window.clearTimeout(hideTimer)
  visible.value = true
  width.value = 0
  requestAnimationFrame(() => {
    width.value = 30
  })
  slowTimers.push(window.setTimeout(() => { width.value = Math.max(width.value, 55) }, 320))
  slowTimers.push(window.setTimeout(() => { width.value = Math.max(width.value, 75) }, 900))
  slowTimers.push(window.setTimeout(() => { width.value = Math.max(width.value, 88) }, 1800))
}

function done() {
  if (!running) return
  running = false
  clearSlow()
  width.value = 100
  hideTimer = window.setTimeout(() => {
    visible.value = false
  }, 360)
}

router.beforeEach(() => {
  start()
})
router.afterEach(() => {
  done()
})
router.onError(() => {
  done()
})

onBeforeUnmount(() => {
  clearSlow()
  window.clearTimeout(hideTimer)
})
</script>

<template>
  <div
    class="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[3px]"
    :class="visible ? 'opacity-100' : 'opacity-0'"
    style="transition: opacity 280ms ease 100ms"
    role="progressbar"
    :aria-label="visible ? '页面加载中' : undefined"
    :aria-hidden="!visible"
  >
    <div
      class="h-full rounded-r-full bg-accent"
      :style="{
        width: `${width}%`,
        boxShadow: '0 0 10px rgb(59 110 245 / 0.5)',
        transition: width >= 100
          ? 'width 240ms ease-out'
          : 'width 620ms cubic-bezier(0.16, 1, 0.3, 1)',
      }"
    />
  </div>
</template>
