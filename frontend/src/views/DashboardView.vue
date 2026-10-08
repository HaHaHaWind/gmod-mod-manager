<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Boxes, ListChecks, RefreshCw, ScanLine, Trash2, TriangleAlert } from 'lucide-vue-next'
import { apiActivePlan, apiStartScan } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { PlanView } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { usePolling } from '@/composables/usePolling'
import { toast } from '@/composables/useToast'
import {
  MANAGEMENT_MODE_ZH, PLAN_STATUS_ZH, formatTime, planStatusTone,
} from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Panel from '@/components/ui/Panel.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import SpecGrid, { type SpecItem } from '@/components/ui/SpecGrid.vue'
import StatCard from '@/components/biz/StatCard.vue'

const router = useRouter()
const system = useSystemStore()
const activePlan = ref<PlanView | null>(null)
const scanning = ref(false)

const counts = computed(() => system.status?.counts ?? {
  mods: 0, trashed: 0, queued_tasks: 0, requires_restart: 0,
})

const missingPaths = computed(() => {
  const p = system.status?.paths_configured
  if (!p) return []
  return Object.entries(p).filter(([, ok]) => !ok).map(([k]) => k)
})

const healthRows = computed<SpecItem[]>(() => [
  {
    label: '管理模式',
    value: system.status
      ? (MANAGEMENT_MODE_ZH[system.status.management_mode] ?? system.status.management_mode)
      : '-',
  },
  { label: '部署策略', value: system.status?.local_managed_strategy || '-' },
  {
    label: '服务器控制',
    value: system.status?.server_control_mode === 'systemd' ? 'systemd(不自动重启)' : 'manual(不自动重启)',
  },
  {
    label: '数据库',
    badge: system.status?.db_ok ? '正常' : '异常',
    tone: system.status?.db_ok ? 'success' : 'danger',
  },
  {
    label: '后台进程',
    badge: system.status?.worker_alive == null ? '未知' : system.status.worker_alive ? '存活' : '已停止',
    tone: system.status?.worker_alive == null ? 'neutral' : system.status.worker_alive ? 'success' : 'danger',
  },
  { label: '只读开关', badge: system.readOnly ? '已开启' : '关闭', tone: system.readOnly ? 'danger' : 'success' },
])

async function refreshAll() {
  await system.refresh()
  try {
    activePlan.value = (await apiActivePlan()).plan
  } catch { /* 未登录时忽略 */ }
}

async function startScan(deep: boolean) {
  if (system.readOnly) {
    toast.warning('当前为只读模式,无法发起扫描')
    return
  }
  scanning.value = true
  try {
    const resp = await apiStartScan(deep)
    toast.success(`扫描任务已创建(${resp.task.id.slice(0, 8)}),可在任务中心查看进度`)
    router.push({ name: 'tasks' })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建扫描任务失败')
  } finally {
    scanning.value = false
  }
}

usePolling(refreshAll, 10000)
</script>

<template>
  <div class="space-y-4">
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard label="已登记 Mod" :value="counts.mods" hint="扫描收录的 Workshop 条目" :icon="Boxes" tone="accent" />
      <StatCard label="回收站条目" :value="counts.trashed" hint="可在保留期内还原" :icon="Trash2" />
      <StatCard label="排队任务" :value="counts.queued_tasks" hint="等待后台进程执行" :icon="ListChecks" tone="warning" />
      <StatCard label="待重启 Mod" :value="counts.requires_restart" hint="配置已应用,需重启生效" :icon="RefreshCw" tone="danger" />
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <Panel title="系统健康" description="后端服务、数据库与后台进程的实时状态">
        <template #actions>
          <Button size="sm" :loading="scanning" :disabled="system.readOnly" @click="startScan(false)">
            <ScanLine class="size-3.5" aria-hidden="true" />
            快速扫描
          </Button>
          <Button size="sm" variant="primary" :loading="scanning" :disabled="system.readOnly" @click="startScan(true)">
            全量扫描(校验文件)
          </Button>
        </template>

        <SpecGrid :items="healthRows" :cols="2" />

        <div
          v-if="missingPaths.length"
          class="mt-3 flex items-start gap-2 rounded-lg border border-warn/30 bg-warn-soft px-3 py-2.5"
        >
          <TriangleAlert class="mt-0.5 size-4 shrink-0 text-warn" aria-hidden="true" />
          <div class="text-[12.5px] leading-5">
            <p class="font-medium text-ink">以下路径未配置或不存在:{{ missingPaths.join('、') }}</p>
            <p class="text-ink-3">请检查 .env 配置后重启后端服务。</p>
          </div>
        </div>
      </Panel>

      <Panel title="进行中的变更计划" description="草稿 / 待应用 / 应用中的计划">
        <template v-if="activePlan">
          <div class="space-y-3">
            <p class="mono truncate text-[12px] text-ink-3" :title="activePlan.id">{{ activePlan.id }}</p>
            <div class="flex flex-wrap items-center gap-2">
              <Badge :variant="planStatusTone(activePlan.status)">
                {{ PLAN_STATUS_ZH[activePlan.status] || activePlan.status }}
              </Badge>
              <span class="small muted">{{ activePlan.payload?.length ?? 0 }} 个变更项</span>
              <span class="small muted">{{ formatTime(activePlan.created_at) }}</span>
            </div>
            <Button
              size="sm"
              variant="primary"
              @click="router.push({ name: 'plan-detail', params: { id: activePlan.id } })"
            >
              查看详情
            </Button>
          </div>
        </template>
        <EmptyState
          v-else-if="system.status"
          title="当前没有进行中的计划"
          description="在 Mod 库中勾选条目即可创建变更计划。"
        />
        <div v-else class="space-y-2.5">
          <Skeleton class="h-4 w-2/3" />
          <Skeleton class="h-4 w-1/3" />
          <Skeleton class="h-8 w-28" />
        </div>
      </Panel>
    </div>
  </div>
</template>