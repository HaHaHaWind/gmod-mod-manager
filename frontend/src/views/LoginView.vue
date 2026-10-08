<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Lock, Server, ShieldCheck, User } from 'lucide-vue-next'
import { ApiRequestError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { toast } from '@/composables/useToast'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()

const loading = ref(false)
const errorMsg = ref('')
const username = ref('')
const password = ref('')

const canSubmit = computed(() => username.value.trim() !== '' && password.value !== '' && !loading.value)

async function submit() {
  errorMsg.value = ''
  if (!username.value.trim() || !password.value) {
    errorMsg.value = '请输入用户名与密码'
    return
  }
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    await system.refresh()
    toast.success(`欢迎,${auth.username}`)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch (e) {
    errorMsg.value = e instanceof ApiRequestError
      ? (e.code === 'invalid_credentials' ? '用户名或密码错误' : e.message)
      : '登录失败,请稍后重试'
  } finally {
    loading.value = false
  }
}

const gridStyle = {
  backgroundImage:
    'radial-gradient(70% 55% at 15% 0%, rgba(37,99,235,0.45), transparent 68%),' +
    'linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px),' +
    'linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)',
  backgroundSize: 'auto, 34px 34px, 34px 34px',
}
</script>

<template>
  <div class="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
    <section
      class="relative hidden flex-col justify-between overflow-hidden bg-ink p-12 text-white lg:flex"
      :style="gridStyle"
    >
      <div class="flex items-center gap-2.5">
        <span class="flex size-9 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15">
          <Server class="size-[18px]" aria-hidden="true" />
        </span>
        <span class="text-[14px] font-semibold tracking-tight">GMod Mod 管理面板</span>
      </div>

      <div class="max-w-md">
        <h1 class="text-[34px] font-semibold leading-[1.15] tracking-tight">
          Workshop 内容的<br>集中化管控台
        </h1>
        <p class="mt-4 text-[13.5px] leading-6 text-white/65">
          面向 Garry's Mod 专用服务器:扫描收录、状态巡检、批量变更与审计留痕,
          所有写操作都经预览确认后落地。
        </p>
        <ul class="mt-8 space-y-3 text-[13px] text-white/75">
          <li class="flex items-center gap-2.5">
            <ShieldCheck class="size-4 text-white/50" aria-hidden="true" />
            只读开关 + 变更计划双重保护
          </li>
          <li class="flex items-center gap-2.5">
            <ShieldCheck class="size-4 text-white/50" aria-hidden="true" />
            预览图卡片化浏览,快速挑选取舍
          </li>
          <li class="flex items-center gap-2.5">
            <ShieldCheck class="size-4 text-white/50" aria-hidden="true" />
            全量操作审计,可回溯到 request_id
          </li>
        </ul>
      </div>

      <p class="text-[11.5px] text-white/40">服务端管理面板 · 部署于专用服务器</p>
    </section>

    <section class="flex items-center justify-center bg-canvas px-5 py-10">
      <div class="w-full max-w-[360px]">
        <div class="mb-7 lg:hidden">
          <span class="flex size-9 items-center justify-center rounded-xl bg-accent-soft text-accent">
            <Server class="size-[18px]" aria-hidden="true" />
          </span>
        </div>

        <h2 class="text-[20px] font-semibold tracking-tight text-ink">登录管理面板</h2>
        <p class="mt-1 text-[13px] text-ink-3">使用管理员账号继续</p>

        <form class="mt-6 space-y-4" @submit.prevent="submit">
          <div>
            <label for="login-user" class="mb-1.5 block text-[12.5px] font-medium text-ink-2">用户名</label>
            <div class="relative">
              <User class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-4" aria-hidden="true" />
              <Input
                id="login-user"
                v-model="username"
                class="pl-9"
                placeholder="管理员用户名"
                autocomplete="username"
              />
            </div>
          </div>

          <div>
            <label for="login-pass" class="mb-1.5 block text-[12.5px] font-medium text-ink-2">密码</label>
            <div class="relative">
              <Lock class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-4" aria-hidden="true" />
              <Input
                id="login-pass"
                v-model="password"
                type="password"
                class="pl-9"
                placeholder="密码"
                autocomplete="current-password"
              />
            </div>
          </div>

          <div
            v-if="errorMsg"
            class="rounded-xl border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-[12.5px] leading-5 text-danger"
            role="alert"
          >
            {{ errorMsg }}
          </div>

          <Button type="submit" variant="primary" size="lg" class="w-full" :loading="loading" :disabled="!canSubmit">
            登 录
          </Button>
        </form>

        <p class="mt-5 text-center text-[11.5px] leading-5 text-ink-4">
          首次部署请用命令行创建管理员账号(见 README)。
        </p>
      </div>
    </section>
  </div>
</template>