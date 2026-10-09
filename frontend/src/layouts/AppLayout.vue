<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuPortal,
  DropdownMenuRoot, DropdownMenuSeparator, DropdownMenuTrigger,
} from 'reka-ui'
import {
  Activity, ChevronDown, ChevronsRight, History, LayoutDashboard, ListChecks, LogOut,
  Menu, Moon, Package, PanelLeftClose, PanelLeftOpen, ScrollText, Server, Sun, Ticket, Trash2,
} from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { usePolling } from '@/composables/usePolling'
import { useTheme } from '@/composables/useTheme'
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
const { theme, toggleTheme } = useTheme()

const navOpen = ref(false)

/* ---------- 可折叠侧栏:状态持久化,仅影响 lg+ 布局 ---------- */
const SIDEBAR_KEY = 'gmod_mm_sidebar'
const collapsed = ref(localStorage.getItem(SIDEBAR_KEY) === '1')
function toggleCollapsed() {
  collapsed.value = !collapsed.value
  localStorage.setItem(SIDEBAR_KEY, collapsed.value ? '1' : '0')
}

/* ---------- 导航结构:主入口 + 操作记录 + 次级系统入口 ---------- */
const mainNav = [
  { name: 'dashboard', to: { name: 'dashboard' }, label: '仪表盘', icon: LayoutDashboard },
  { name: 'mods', to: { name: 'mods' }, label: '模组库', icon: Package },
  { name: 'trash', to: { name: 'trash' }, label: '回收站', icon: Trash2 },
]
const systemNav = [
  { name: 'system', to: { name: 'system' }, label: '服务状态', icon: Activity },
  { name: 'audit', to: { name: 'audit' }, label: '审计日志', icon: ScrollText, adminOnly: true },
]

function isActivityRoute(name: unknown = route.name): boolean {
  const current = String(name ?? '')
  return current.startsWith('plan') || current.startsWith('task')
}
const activityOpen = ref(isActivityRoute())
watch(() => route.name, (n) => { if (isActivityRoute(n)) activityOpen.value = true })

function isActive(name: string): boolean {
  const current = String(route.name ?? '')
  if (name === 'dashboard') return current === 'dashboard'
  if (name === 'mods') return current.startsWith('mod')
  return current === name
}
const isActivityActive = computed(() => isActivityRoute())

usePolling(() => system.refresh(), 15000)

async function onLogout() {
  await auth.logout()
  system.$reset()
  toast.success('已退出登录')
  router.push({ name: 'login' })
}

const restartCount = computed(() => system.status?.counts.requires_restart ?? 0)

const pageTitle = computed(() => {
  const t = route.meta?.title
  return typeof t === 'string' && t ? t : 'GMod 模组管理器'
})

/* ---------- 面包屑:根级仪表盘 + 父级上下文 ---------- */
const crumbs = computed<{ label: string; to?: unknown }[]>(() => {
  const name = String(route.name ?? '')
  const parent = name === 'mod-detail'
    ? { label: '模组库', to: { name: 'mods' } }
    : name === 'plan-detail'
      ? { label: '变更记录', to: { name: 'plans' } }
      : null
  const items: { label: string; to?: unknown }[] = [{ label: '仪表盘', to: { name: 'dashboard' } }]
  if (parent && pageTitle.value !== parent.label) items.push(parent)
  if (pageTitle.value !== '仪表盘') items.push({ label: pageTitle.value })
  return items
})
</script>

<template>
  <div
    :class="cn(
      'min-h-screen bg-canvas lg:grid',
      collapsed ? 'lg:grid-cols-[68px_minmax(0,1fr)]' : 'lg:grid-cols-[224px_minmax(0,1fr)]',
    )"
  >
    <div v-if="navOpen" class="fixed inset-0 z-40 bg-black/45 lg:hidden" @click="navOpen = false" />

    <aside
      :class="cn(
        'fixed inset-y-0 left-0 z-50 flex w-[224px] flex-col border-r border-line bg-surface/80 backdrop-blur-xl',
        'transition-[width,transform] duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
        collapsed ? 'lg:w-[68px]' : 'lg:w-[224px]',
        navOpen ? 'translate-x-0' : '-translate-x-full',
      )"
    >
      <!-- 品牌区 -->
      <div class="flex h-16 shrink-0 items-center gap-3 border-b border-line px-5 lg:px-3.5">
        <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-white shadow-[0_6px_16px_-6px_rgb(59_110_245/0.6)]">
          <Server class="size-[18px]" aria-hidden="true" />
        </span>
        <div v-if="!collapsed" class="min-w-0 flex-1">
          <p class="truncate text-[14px] font-semibold leading-5 tracking-tight text-ink">GMod 模组管理器</p>
          <p class="truncate text-[12px] leading-4 text-ink-4">Workshop 服务端</p>
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

      <nav class="flex-1 space-y-0.5 overflow-y-auto p-3 lg:px-2.5">
        <!-- 主入口 -->
        <RouterLink
          v-for="item in mainNav"
          :key="item.name"
          :to="item.to"
          :title="collapsed ? item.label : undefined"
          :class="cn(
            'group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] font-medium transition-colors duration-150',
            collapsed && 'lg:justify-center lg:px-0',
            isActive(item.name)
              ? 'bg-accent-soft text-accent-strong ring-1 ring-inset ring-accent-line/70'
              : 'text-ink-2 hover:bg-surface-muted hover:text-ink',
          )"
          @click="navOpen = false"
        >
          <component
            :is="item.icon"
            :class="cn('size-4 shrink-0', isActive(item.name) ? 'text-accent' : 'text-ink-4 group-hover:text-ink-3')"
            aria-hidden="true"
          />
          <span v-if="!collapsed">{{ item.label }}</span>
        </RouterLink>

        <!-- 操作记录:含变更记录 / 后台任务两个子入口 -->
        <div>
          <!-- 折叠态:图标 + 弹出子菜单 -->
          <DropdownMenuRoot v-if="collapsed">
            <DropdownMenuTrigger as-child>
              <button
                type="button"
                title="操作记录"
                :class="cn(
                  'group relative flex w-full items-center justify-center rounded-lg py-2 text-[14px] font-medium transition-colors duration-150',
                  isActivityActive ? 'bg-accent-soft text-accent-strong' : 'text-ink-2 hover:bg-surface-muted hover:text-ink',
                )"
                :aria-label="isActivityActive ? '操作记录(当前所在)' : '操作记录'"
              >
                <History
                  :class="cn('size-4', isActivityActive ? 'text-accent' : 'text-ink-4 group-hover:text-ink-3')"
                  aria-hidden="true"
                />
                <span
                  v-if="system.activePlanId"
                  class="absolute right-4 top-2 size-1.5 rounded-full bg-warn"
                  aria-hidden="true"
                />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuPortal>
              <DropdownMenuContent
                :side-offset="6"
                class="z-50 min-w-40 animate-ui-in rounded-xl border border-line bg-surface p-1 shadow-pop"
              >
                <DropdownMenuLabel class="px-2 py-1.5 text-[12px] text-ink-4">操作记录</DropdownMenuLabel>
                <DropdownMenuSeparator class="my-1 h-px bg-line" />
                <DropdownMenuItem
                  class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-surface-muted"
                  @select="router.push({ name: 'plans' })"
                >
                  <Ticket class="size-3.5 text-ink-4" aria-hidden="true" />
                  变更记录
                </DropdownMenuItem>
                <DropdownMenuItem
                  class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-surface-muted"
                  @select="router.push({ name: 'tasks' })"
                >
                  <ListChecks class="size-3.5 text-ink-4" aria-hidden="true" />
                  后台任务
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenuPortal>
          </DropdownMenuRoot>

          <!-- 展开态:可折叠分组 -->
          <template v-else>
            <button
              type="button"
              :class="cn(
                'group flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] font-medium transition-colors duration-150',
                isActivityActive ? 'text-ink' : 'text-ink-2 hover:bg-surface-muted hover:text-ink',
              )"
              :aria-expanded="activityOpen"
              @click="activityOpen = !activityOpen"
            >
              <History
                :class="cn('size-4 shrink-0', isActivityActive ? 'text-accent' : 'text-ink-4 group-hover:text-ink-3')"
                aria-hidden="true"
              />
              <span>操作记录</span>
              <span
                v-if="system.activePlanId"
                class="size-1.5 rounded-full bg-warn"
                aria-label="有进行中的变更"
              />
              <ChevronDown
                class="ml-auto size-3.5 text-ink-4 transition-transform duration-150"
                :class="activityOpen ? '' : '-rotate-90'"
                aria-hidden="true"
              />
            </button>
            <div v-show="activityOpen" class="mt-0.5 space-y-0.5 pl-[30px]">
              <RouterLink
                :to="{ name: 'plans' }"
                :class="cn(
                  'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] transition-colors duration-150',
                  isActive('plans') || route.name === 'plan-detail'
                    ? 'bg-accent-soft font-medium text-accent-strong'
                    : 'text-ink-3 hover:bg-surface-muted hover:text-ink',
                )"
                @click="navOpen = false"
              >
                <Ticket class="size-3.5 shrink-0" aria-hidden="true" />
                变更记录
              </RouterLink>
              <RouterLink
                :to="{ name: 'tasks' }"
                :class="cn(
                  'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] transition-colors duration-150',
                  isActive('tasks')
                    ? 'bg-accent-soft font-medium text-accent-strong'
                    : 'text-ink-3 hover:bg-surface-muted hover:text-ink',
                )"
                @click="navOpen = false"
              >
                <ListChecks class="size-3.5 shrink-0" aria-hidden="true" />
                后台任务
              </RouterLink>
            </div>
          </template>
        </div>

        <!-- 次级:系统 -->
        <div class="pt-4">
          <p v-if="!collapsed" class="px-3 pb-1 text-[12px] font-medium text-ink-4">系统</p>
          <template v-for="item in systemNav" :key="item.name">
            <RouterLink
              v-if="!item.adminOnly || auth.isAdmin"
              :to="item.to"
              :title="collapsed ? item.label : undefined"
              :class="cn(
                'group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] font-medium transition-colors duration-150',
                collapsed && 'lg:justify-center lg:px-0',
                isActive(item.name)
                  ? 'bg-accent-soft text-accent-strong ring-1 ring-inset ring-accent-line/70'
                  : 'text-ink-2 hover:bg-surface-muted hover:text-ink',
              )"
              @click="navOpen = false"
            >
              <component
                :is="item.icon"
                :class="cn('size-4 shrink-0', isActive(item.name) ? 'text-accent' : 'text-ink-4 group-hover:text-ink-3')"
                aria-hidden="true"
              />
              <span v-if="!collapsed">{{ item.label }}</span>
            </RouterLink>
          </template>
        </div>
      </nav>

      <!-- 侧栏底部 -->
      <div class="shrink-0 border-t border-line p-3 lg:px-2.5">
        <template v-if="!collapsed">
          <RouterLink
            :to="{ name: 'system' }"
            class="block rounded-lg transition-colors hover:bg-surface-muted/60"
            aria-label="查看服务状态详情"
          >
            <div class="rounded-lg bg-surface-muted px-3 py-2.5">
              <p class="text-[12px] font-medium text-ink-3">服务概要</p>
              <div class="mt-1.5 space-y-1 text-[12px]">
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
                    {{ system.status?.worker_alive == null ? '未知' : system.status?.worker_alive ? '正常' : '异常' }}
                  </span>
                </div>
              </div>
            </div>
          </RouterLink>
          <button
            type="button"
            class="mt-2 hidden w-full items-center justify-center gap-2 rounded-lg px-3 py-1.5 text-[12.5px] text-ink-3 transition-colors hover:bg-surface-muted hover:text-ink lg:flex"
            aria-label="收起侧栏"
            @click="toggleCollapsed"
          >
            <PanelLeftClose class="size-4" aria-hidden="true" />
            收起侧栏
          </button>
        </template>
        <button
          v-else
          type="button"
          class="hidden w-full items-center justify-center rounded-lg py-2 text-ink-3 transition-colors hover:bg-surface-muted hover:text-ink lg:flex"
          aria-label="展开侧栏"
          title="展开侧栏"
          @click="toggleCollapsed"
        >
          <PanelLeftOpen class="size-4" aria-hidden="true" />
        </button>
        <Button
          size="icon-sm"
          variant="ghost"
          class="mt-2 w-full lg:hidden"
          aria-label="展开侧栏"
          @click="toggleCollapsed"
        >
          <ChevronsRight class="size-4" aria-hidden="true" />
        </Button>
      </div>
    </aside>

    <div class="flex min-h-screen min-w-0 flex-col">
      <!-- 顶栏:面包屑 + 必要提醒 + 主题切换 + 账户菜单 -->
      <header
        class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-surface/80 px-4 backdrop-blur-xl lg:px-8"
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

        <!-- 面包屑:路由变化时轻微淡入,避免标题瞬间跳变 -->
        <Transition name="crumb" mode="out-in">
          <nav :key="String(route.name)" aria-label="面包屑" class="flex min-w-0 items-center gap-1.5 text-[13.5px]">
          <template v-for="(c, i) in crumbs" :key="i">
            <span v-if="i > 0" class="text-ink-4" aria-hidden="true">/</span>
            <RouterLink
              v-if="c.to && i < crumbs.length - 1"
              :to="c.to"
              class="shrink-0 text-ink-3 transition-colors hover:text-accent"
            >
              {{ c.label }}
            </RouterLink>
            <span
              v-else
              class="truncate font-semibold tracking-tight"
              :class="i === crumbs.length - 1 ? 'text-ink' : 'text-ink-3'"
              :aria-current="i === crumbs.length - 1 ? 'page' : undefined"
            >
              {{ c.label }}
            </span>
          </template>
          </nav>
        </Transition>
        <span class="spacer" />

        <div class="hidden items-center gap-1.5 md:flex">
          <Tooltip v-if="system.readOnly" content="只读开关开启时,所有写操作将被拒绝">
            <Badge variant="danger">只读</Badge>
          </Tooltip>
          <Tooltip v-if="system.managementMode !== 'local_managed'" content="当前管理模式不为本工具完全接管,部分操作可能不可用">
            <Badge variant="neutral">
              {{ MANAGEMENT_MODE_ZH[system.managementMode] || system.managementMode }}
            </Badge>
          </Tooltip>
          <Tooltip v-if="restartCount > 0" content="有模组的配置已更新,等待服务器重启后生效">
            <Badge variant="warning">待重启 {{ restartCount }}</Badge>
          </Tooltip>
          <RouterLink v-if="system.activePlanId" :to="{ name: 'plan-detail', params: { id: system.activePlanId } }">
            <Badge variant="warning">有进行中的变更</Badge>
          </RouterLink>
        </div>

        <!-- 主题切换 -->
        <button
          type="button"
          class="inline-flex size-8 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-surface-muted hover:text-ink"
          :aria-label="theme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'"
          :title="theme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'"
          @click="toggleTheme"
        >
          <Sun v-if="theme === 'dark'" class="size-4" aria-hidden="true" />
          <Moon v-else class="size-4" aria-hidden="true" />
        </button>

        <DropdownMenuRoot>
          <DropdownMenuTrigger as-child>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-lg px-1.5 py-1.5 text-[13px] text-ink-2 transition-colors hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
            >
              <span class="flex size-6 items-center justify-center rounded-full bg-accent-soft text-[12px] font-semibold uppercase text-accent-strong">
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
              class="z-50 min-w-44 animate-ui-in rounded-xl border border-line bg-surface p-1 shadow-pop"
            >
              <DropdownMenuLabel class="px-2 py-1.5 text-[12px] text-ink-4">
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

      <main class="flex-1 px-4 py-6 lg:px-8 lg:py-8">
        <div class="mx-auto w-full max-w-[1400px]">
          <RouterView v-slot="{ Component }">
            <Transition name="page" mode="out-in">
              <component :is="Component" :key="route.fullPath" />
            </Transition>
          </RouterView>
        </div>
      </main>
    </div>
  </div>
</template>
