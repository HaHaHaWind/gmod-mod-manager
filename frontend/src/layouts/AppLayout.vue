<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuPortal,
  DropdownMenuRoot, DropdownMenuSeparator, DropdownMenuTrigger,
} from 'reka-ui'
import {
  ChevronDown, FolderOpen, Gauge, ListChecks, LogOut, Menu, ScrollText, Server, Ticket, Trash2,
} from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { usePolling } from '@/composables/usePolling'
import { toast } from '@/composables/useToast'
import { MANAGEMENT_MODE_ZH } from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { cn } from '@/lib/utils'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()

const navOpen = ref(false)
const pageTitle = computed(() => (route.meta.title as string) || '总览')

const nav = [
  { name: 'dashboard', to: { name: 'dashboard' }, label: '总览', icon: Gauge },
  { name: 'mods', to: { name: 'mods' }, label: 'Mod 库', icon: FolderOpen },
  { name: 'plans', to: { name: 'plans' }, label: '变更计划', icon: Ticket },
  { name: 'trash', to: { name: 'trash' }, label: '回收站', icon: Trash2 },
  { name: 'tasks', to: { name: 'tasks' }, label: '任务中心', icon: ListChecks },
  { name: 'audit', to: { name: 'audit' }, label: '审计日志', icon: ScrollText },
]

function isActive(name: string): boolean {
  const current = String(route.name ?? '')
  if (name === 'mods') return current.startsWith('mod')
  if (name === 'plans') return current.startsWith('plan')
  return current === name
}

usePolling(() => system.refresh(), 15000)

async function onLogout() {
  await auth.logout()
  system.$reset()
  toast.success('已退出登录')
  router.push({ name: 'login' })
}

const workerText = computed(() =>
  system.status?.worker_alive == null ? '未知' : system.status.worker_alive ? '正常' : '异常',
)
const restartCount = computed(() => system.status?.counts.requires_restart ?? 0)
</script>

<template>
  <div class="min-h-screen bg-canvas lg:grid lg:grid-cols-[236px_minmax(0,1fr)]">
    <div v-if="navOpen" class="fixed inset-0 z-40 bg-ink/35 lg:hidden" @click="navOpen = false" />

    <aside
      :class="cn(
        'fixed inset-y-0 left-0 z-50 flex w-[236px] flex-col border-r border-line bg-surface',
        'transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
        navOpen ? 'translate-x-0' : '-translate-x-full',
      )"
    >
      <div class="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4">
        <span class="flex size-8 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Server class="size-4" aria-hidden="true" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-[13px] font-semibold leading-4 text-ink">GMod Mod 管理面板</p>
          <p class="truncate text-[11px] leading-4 text-ink-4">Workshop 服务端</p>
        </div>
        <Button
          size="icon-sm"
          variant="ghost"
          class="lg:hidden"
          aria-label="关闭导航"
          @click="navOpen = false"
        >
          <Menu class="size-4" aria-hidden="true" />
        </Button>
      </div>

      <nav class="flex-1 space-y-0.5 overflow-y-auto p-2">
        <RouterLink
          v-for="item in nav"
          :key="item.name"
          :to="item.to"
          :class="cn(
            'group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors',
            isActive(item.name)
              ? 'bg-accent-soft text-accent-strong'
              : 'text-ink-2 hover:bg-surface-muted hover:text-ink',
          )"
          @click="navOpen = false"
        >
          <component
            :is="item.icon"
            :class="cn('size-4 shrink-0', isActive(item.name) ? 'text-accent' : 'text-ink-4 group-hover:text-ink-3')"
            aria-hidden="true"
          />
          <span>{{ item.label }}</span>
          <span
            v-if="item.name === 'plans' && system.activePlanId"
            class="ml-auto size-1.5 rounded-full bg-warn"
            aria-label="有进行中的计划"
          />
        </RouterLink>
      </nav>

      <div class="shrink-0 border-t border-line p-3">
        <div class="rounded-lg bg-surface-muted px-2.5 py-2">
          <p class="text-[11px] font-medium text-ink-3">系统状态</p>
          <div class="mt-1.5 space-y-1 text-[11.5px]">
            <div class="flex items-center justify-between">
              <span class="text-ink-3">数据库</span>
              <span class="inline-flex items-center gap-1.5" :class="system.status?.db_ok ? 'text-ok' : 'text-danger'">
                <span class="size-1.5 rounded-full" :class="system.status?.db_ok ? 'bg-ok' : 'bg-danger'" />
                {{ system.status?.db_ok ? '正常' : '异常' }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-ink-3">后台进程</span>
              <span
                class="inline-flex items-center gap-1.5"
                :class="system.status?.worker_alive == null ? 'text-ink-3' : system.status?.worker_alive ? 'text-ok' : 'text-danger'"
              >
                <span
                  class="size-1.5 rounded-full"
                  :class="system.status?.worker_alive == null ? 'bg-ink-4' : system.status?.worker_alive ? 'bg-ok' : 'bg-danger'"
                />
                {{ workerText }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <div class="flex min-h-screen min-w-0 flex-col">
      <header
        class="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur lg:px-6"
      >
        <Button
          size="icon-sm"
          variant="ghost"
          class="lg:hidden"
          aria-label="打开导航"
          @click="navOpen = true"
        >
          <Menu class="size-4" aria-hidden="true" />
        </Button>
        <h1 class="truncate text-[15px] font-semibold tracking-tight text-ink">{{ pageTitle }}</h1>
        <span class="spacer" />

        <div class="hidden items-center gap-1.5 md:flex">
          <Tooltip v-if="system.readOnly" content="只读开关开启时,所有写操作将被拒绝">
            <Badge variant="danger">只读</Badge>
          </Tooltip>
          <Badge variant="neutral">
            {{ MANAGEMENT_MODE_ZH[system.managementMode] || system.managementMode }}
          </Badge>
          <Badge v-if="restartCount > 0" variant="warning">待重启 {{ restartCount }}</Badge>
          <RouterLink v-if="system.activePlanId" :to="{ name: 'plan-detail', params: { id: system.activePlanId } }">
            <Badge variant="warning">有进行中的计划</Badge>
          </RouterLink>
          <Tooltip :content="system.status?.worker_alive ? '后台任务进程正常' : '后台任务进程不可用'">
            <Badge :variant="system.status?.worker_alive ? 'success' : 'danger'">
              worker {{ workerText }}
            </Badge>
          </Tooltip>
        </div>

        <DropdownMenuRoot>
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-lg px-1.5 py-1.5 text-[13px] text-ink-2 transition-colors hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
            >
              <span class="flex size-6 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold uppercase text-accent-strong">
                {{ (auth.username || '?').slice(0, 1) }}
              </span>
              <span class="hidden max-w-[120px] truncate sm:inline">{{ auth.username }}</span>
              <ChevronDown class="size-3.5 text-ink-4" aria-hidden="true" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent
              align="end"
              :side-offset="6"
              class="z-50 min-w-44 animate-ui-in rounded-lg border border-line bg-surface p-1 shadow-lg shadow-ink/10"
            >
              <DropdownMenuLabel class="px-2 py-1.5 text-[11px] text-ink-4">
                {{ auth.isAdmin ? '管理员' : '普通用户' }}
              </DropdownMenuLabel>
              <DropdownMenuSeparator class="my-1 h-px bg-line" />
              <DropdownMenuItem
                class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-surface-muted"
                @select="onLogout"
              >
                <LogOut class="size-3.5 text-ink-4" aria-hidden="true" />
                退出登录
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenuRoot>
      </header>

      <main class="flex-1 px-4 py-5 lg:px-6 lg:py-6">
        <div class="mx-auto w-full max-w-[1440px]">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
</template>