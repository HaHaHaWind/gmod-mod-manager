<script setup lang="ts">
/** 仪表盘首页:概览统计、模组状态分布、最近任务、进行中的变更与服务健康。 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight, Boxes, ListChecks, PackageOpen, RefreshCw, ScanLine, Trash2, TriangleAlert,
} from 'lucide-vue-next'
import {
  apiActivePlan, apiModList, apiStartScan, apiTaskList,
} from '@/api'
import { ApiRequestError } from '@/api/client'
import type { PlanView, TaskView } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { usePolling } from '@/composables/usePolling'
import { toast } from '@/composables/useToast'
import {
  TASK_KIND_ZH, TASK_STATUS_ZH, formatTime, planTitle, taskStatusTone,
} from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Panel from '@/components/ui/Panel.vue'
import Progress from '@/components/ui/Progress.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import StatCard from '@/components/biz/StatCard.vue'

const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()

const activePlan = ref<PlanView | null>(null)
const recentTasks = ref<TaskView[]>([])
const dist = ref<{ present: number | null; missing: number | null; invalid: number | null }>({
  present: null, missing: null, invalid: null,
})
const scanning = ref(false)

const counts = computed(() => system.status?.counts ?? {
  mods: 0, trashed: 0, queued_tasks: 0, requires_restart: 0,
})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const missingPaths = computed(() => {
  const p = system.status?.paths_configured
  if (!p) return []
  return Object.entries(p).filter(([, ok]) => !ok).map(([k]) => k)
})

/* ---------- 模组状态分布:按文件状态请求真实计数,page_size=1 仅取 total ---------- */
const distLoading = ref(true)
async function loadDist() {
  try {
    const [p, m, i] = await Promise.all([
      apiModList({ inventory_state: 'present', page: 1, page_size: 1 }),
      apiModList({ inventory_state: 'missing', page: 1, page_size: 1 }),
      apiModList({ inventory_state: 'invalid', page: 1, page_size: 1 }),
    ])
    dist.value = { present: p.total, missing: m.total, invalid: i.total }
  } catch { /* 仪表盘非关键数据,静默失败 */ } finally {
    distLoading.value = false
  }
}

const distTotal = computed(() =>
  (dist.value.present ?? 0) + (dist.value.missing ?? 0) + (dist.value.invalid ?? 0))
function distPct(n: number | null): number {
  if (n == null || distTotal.value === 0) return 0
  return (n * 100) / distTotal.value
}
const distSegments = computed(() => [
  { key: 'present', label: '正常', value: dist.value.present, cls: 'bg-ok' },
  { key: 'missing', label: '文件缺失', value: dist.value.missing, cls: 'bg-danger' },
  { key: 'invalid', label: '文件异常', value: dist.value.invalid, cls: 'bg-warn' },
])

/* ---------- 最近任务 ---------- */
function progressPct(t: TaskView): number {
  return t.total > 0 ? (t.progress * 100) / t.total : 0
}

async function refreshAll() {
  await system.refresh()
  try {
    const [plan, tasks] = await Promise.all([
      apiActivePlan(),
      apiTaskList(6),
    ])
    activePlan.value = plan.plan
    recentTasks.value = tasks.items
  } catch { /* 未登录等场景忽略,首屏数据已在 system 内 */ }
  if (distLoading.value) await loadDist()
}

async function startScan(deep: boolean) {
  if (system.readOnly) {
    toast.warning('当前为只读模式,无法发起扫描')
    return
  }
  scanning.value = true
  try {
    const resp = await apiStartScan(deep)
    toast.success(`扫描任务已创建,可在后台任务中查看进度(${resp.task.id.slice(0, 8)})`)
    router.push({ name: 'tasks' })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建扫描任务失败')
  } finally {
    scanning.value = false
  }
}

onMounted(refreshAll)
usePolling(refreshAll, 10000)
</script>

<template>
  <div class="space-y-4">
    <!-- 欢迎横幅 -->
    <section
      class="relative overflow-hidden rounded-2xl bg-gradient-to-r from-accent to-accent-strong p-6 text-white shadow-card"
    >
      <div
        class="pointer-events-none absolute -right-16 -top-24 size-64 rounded-full bg-white/10"
        aria-hidden="true"
      />
      <div
        class="pointer-events-none absolute -bottom-28 right-24 size-56 rounded-full bg-white/8"
        aria-hidden="true"
      />
      <div class="relative flex flex-wrap items-end justify-between gap-4">
        <div class="min-w-0">
          <h1 class="text-[22px] font-semibold leading-7 tracking-tight">
            {{ greeting }},{{ auth.username }}
          </h1>
          <p class="mt-1.5 max-w-xl text-[13px] leading-5 text-white/80">
            当前共 {{ counts.mods }} 个模组已入库<template v-if="counts.requires_restart > 0">,其中 {{ counts.requires_restart }} 个待重启生效</template>。
            所有写操作都会先生成变更预览,确认后才会应用。
          </p>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button
            class="border-white/25 bg-white/15 text-white hover:bg-white/25"
            variant="secondary"
            :loading="scanning"
            :disabled="system.readOnly"
            @click="startScan(false)"
          >
            <ScanLine class="size-3.5" aria-hidden="true" />
            快速扫描
          </Button>
          <Button
            class="border-white/25 bg-white/15 text-white hover:bg-white/25"
            variant="secondary"
            :loading="scanning"
            :disabled="system.readOnly"
            @click="startScan(true)"
          >
            全量扫描(校验文件)
          </Button>
        </div>
      </div>
    </section>

    <!-- 概览统计 -->
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="模组总数" :value="counts.mods" hint="扫描收录的 Workshop 条目" :icon="Boxes" tone="accent" />
      <StatCard label="待重启模组" :value="counts.requires_restart" hint="配置已应用,重启后生效" :icon="RefreshCw" tone="warning" />
      <StatCard label="排队任务" :value="counts.queued_tasks" hint="等待后台进程执行" :icon="ListChecks" tone="neutral" />
      <StatCard label="回收站条目" :value="counts.trashed" hint="保留期内可还原" :icon="Trash2" tone="danger" />
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <!-- 模组状态分布 -->
      <Panel title="模组状态分布" description="按本地文件状态统计" class="xl:col-span-2">
        <div v-if="distLoading" class="space-y-3 py-1">
          <Skeleton class="h-3 w-full" />
          <Skeleton class="h-4 w-2/3" />
        </div>
        <template v-else-if="distTotal > 0">
          <div class="flex h-3 w-full overflow-hidden rounded-full bg-surface-sunken" role="img" aria-label="模组文件状态分布">
            <div
              v-for="seg in distSegments"
              :key="seg.key"
              :class="seg.cls"
              :style="{ width: `${distPct(seg.value)}%` }"
            />
          </div>
          <div class="mt-3.5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div v-for="seg in distSegments" :key="seg.key" class="flex items-center gap-2">
              <span class="size-2.5 shrink-0 rounded-sm" :class="seg.cls" aria-hidden="true" />
              <span class="text-[12.5px] text-ink-3">{{ seg.label }}</span>
              <span class="num text-[13px] font-semibold text-ink">{{ seg.value ?? '-' }}</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="size-2.5 shrink-0 rounded-sm bg-surface-sunken" aria-hidden="true" />
              <span class="text-[12.5px] text-ink-3">回收站中</span>
              <span class="num text-[13px] font-semibold text-ink">{{ counts.trashed }}</span>
            </div>
          </div>
          <div class="mt-3.5 border-t border-line pt-3">
            <RouterLink
              :to="{ name: 'mods' }"
              class="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline"
            >
              进入模组库管理
              <ArrowRight class="size-3.5" aria-hidden="true" />
            </RouterLink>
          </div>
        </template>
        <EmptyState
          v-else
          title="还没有模组数据"
          description="先执行一次扫描,收录服务器上已有的模组文件。"
        >
          <template #action>
            <Button size="sm" variant="primary" :loading="scanning" :disabled="system.readOnly" @click="startScan(false)">
              <ScanLine class="size-3.5" aria-hidden="true" />
              快速扫描
            </Button>
          </template>
        </EmptyState>
      </Panel>

      <!-- 服务健康 -->
      <Panel title="服务健康" description="数据库与后台进程">
        <div class="space-y-2.5">
          <div class="flex items-center justify-between rounded-lg bg-surface-muted px-3 py-2.5">
            <span class="text-[13px] text-ink-2">数据库</span>
            <span
              class="inline-flex items-center gap-1.5 text-[13px] font-medium"
              :class="system.status == null ? 'text-ink-3' : system.status.db_ok ? 'text-ok' : 'text-danger'"
            >
              <span
                class="size-2 rounded-full"
                :class="system.status == null ? 'bg-ink-4' : system.status.db_ok ? 'bg-ok' : 'bg-danger'"
                aria-hidden="true"
              />
              {{ system.status == null ? '状态未知' : system.status.db_ok ? '正常' : '异常' }}
            </span>
          </div>
          <div class="flex items-center justify-between rounded-lg bg-surface-muted px-3 py-2.5">
            <span class="text-[13px] text-ink-2">后台进程</span>
            <span
              class="inline-flex items-center gap-1.5 text-[13px] font-medium"
              :class="system.status?.worker_alive == null ? 'text-ink-3' : system.status.worker_alive ? 'text-ok' : 'text-danger'"
            >
              <span
                class="size-2 rounded-full"
                :class="system.status?.worker_alive == null ? 'bg-ink-4' : system.status.worker_alive ? 'bg-ok' : 'bg-danger'"
                aria-hidden="true"
              />
              {{ system.status?.worker_alive == null ? '状态未知' : system.status.worker_alive ? '存活' : '已停止' }}
            </span>
          </div>
          <div v-if="system.readOnly" class="flex items-center justify-between rounded-lg bg-danger-soft px-3 py-2.5">
            <span class="text-[13px] text-ink-2">只读开关</span>
            <span class="text-[13px] font-medium text-danger">已开启</span>
          </div>
          <div
            v-if="missingPaths.length"
            class="flex items-start gap-2 rounded-lg border border-warn/30 bg-warn-soft px-3 py-2.5"
          >
            <TriangleAlert class="mt-0.5 size-4 shrink-0 text-warn" aria-hidden="true" />
            <p class="text-[12.5px] leading-5 text-ink-2">
              {{ missingPaths.length }} 个路径未配置或不存在
            </p>
          </div>
        </div>
        <div class="mt-3.5 border-t border-line pt-3">
          <RouterLink
            :to="{ name: 'system' }"
            class="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline"
          >
            查看完整服务状态
            <ArrowRight class="size-3.5" aria-hidden="true" />
          </RouterLink>
        </div>
      </Panel>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
      <!-- 最近后台任务 -->
      <Panel
        title="最近后台任务"
        description="扫描、更新信息与应用变更在此执行"
        class="xl:col-span-2"
      >
        <div v-if="recentTasks.length === 0" class="py-2">
          <EmptyState
            title="暂无后台任务"
            description="执行扫描、更新模组信息或应用变更后,任务会出现在这里。"
          />
        </div>
        <ul v-else class="divide-y divide-line">
          <li v-for="t in recentTasks" :key="t.id">
            <RouterLink
              :to="{ name: 'tasks' }"
              class="flex items-center gap-3 px-1.5 py-2.5 transition-colors hover:bg-surface-muted"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate text-[13px] font-medium text-ink">{{ TASK_KIND_ZH[t.kind] || t.kind }}</p>
                <p class="num tiny muted mt-0.5">{{ formatTime(t.created_at) }}</p>
              </div>
              <div v-if="t.status === 'running'" class="hidden w-24 sm:block">
                <Progress
                  v-if="t.total > 0"
                  :value="progressPct(t)"
                  class="h-1.5"
                />
                <Progress v-else :indeterminate="true" class="h-1.5" />
              </div>
              <Badge :variant="taskStatusTone(t.status)">
                {{ TASK_STATUS_ZH[t.status] || t.status }}
              </Badge>
            </RouterLink>
          </li>
        </ul>
        <div class="mt-3 border-t border-line pt-3">
          <RouterLink
            :to="{ name: 'tasks' }"
            class="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline"
          >
            查看全部任务
            <ArrowRight class="size-3.5" aria-hidden="true" />
          </RouterLink>
        </div>
      </Panel>

      <!-- 进行中的变更 -->
      <Panel title="进行中的变更" description="草稿 / 待应用 / 应用中">
        <template v-if="activePlan">
          <div class="space-y-2.5">
            <p class="text-[14px] font-semibold text-ink">{{ planTitle(activePlan.payload ?? []) }}</p>
            <div class="flex flex-wrap items-center gap-2">
              <Badge :variant="activePlan.status === 'applied' ? 'success' : 'warning'">
                {{ activePlan.status === 'applying' ? '应用中' : '待处理' }}
              </Badge>
              <span class="small muted">{{ activePlan.payload?.length ?? 0 }} 个变更项</span>
            </div>
            <Button
              size="sm"
              variant="primary"
              class="w-full"
              @click="router.push({ name: 'plan-detail', params: { id: activePlan.id } })"
            >
              继续处理
            </Button>
          </div>
        </template>
        <EmptyState
          v-else
          title="暂无进行中的变更"
          description="在模组库勾选条目并通过批量操作栏生成变更预览。"
        >
          <template #icon>
            <PackageOpen class="size-5" aria-hidden="true" />
          </template>
          <template #action>
            <Button size="sm" variant="secondary" @click="router.push({ name: 'mods' })">
              去模组库
            </Button>
          </template>
        </EmptyState>
      </Panel>
    </div>
  </div>
</template>
