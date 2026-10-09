<script setup lang="ts">
/** 服务状态:连接、数据库、后台进程、配置检查与维护入口,面向排障场景。 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { RefreshCw, TriangleAlert } from 'lucide-vue-next'
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
import Panel from '@/components/ui/Panel.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import SpecGrid, { type SpecItem } from '@/components/ui/SpecGrid.vue'

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
    label: '数据库',
    badge: system.status ? (system.status.db_ok ? '正常' : '异常') : '状态未知',
    tone: system.status ? (system.status.db_ok ? 'success' : 'danger') : 'neutral',
  },
  {
    label: '后台进程',
    badge: system.status?.worker_alive == null ? '状态未知' : system.status.worker_alive ? '存活' : '已停止',
    tone: system.status?.worker_alive == null ? 'neutral' : system.status.worker_alive ? 'success' : 'danger',
  },
  {
    label: '管理模式',
    value: system.status
      ? (MANAGEMENT_MODE_ZH[system.status.management_mode] ?? system.status.management_mode)
      : '正在连接',
  },
])

const configRows = computed<SpecItem[]>(() => [
  { label: '部署策略', value: system.status?.local_managed_strategy || '-' },
  {
    label: '服务器控制',
    value: system.status?.server_control_mode === 'systemd' ? 'systemd(不自动重启)' : 'manual(不自动重启)',
  },
  {
    label: '只读开关',
    badge: system.readOnly ? '已开启' : '关闭',
    tone: system.readOnly ? 'danger' : 'success',
  },
  { label: '模组总数', value: system.status ? String(counts.value.mods) : '状态未知' },
  { label: '回收站条目', value: system.status ? String(counts.value.trashed) : '状态未知' },
  { label: '排队任务', value: system.status ? String(counts.value.queued_tasks) : '状态未知' },
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
    toast.success(`扫描任务已创建,可在操作记录的后台任务中查看进度(${resp.task.id.slice(0, 8)})`)
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
    <div>
      <h1 class="text-[24px] font-semibold tracking-tight text-ink">服务状态</h1>
      <p class="mt-1 text-[13.5px] text-ink-3">
        数据库、后台进程与配置检查;日常使用无需关注这里,排障时可在此找到线索。
      </p>
    </div>

    <p
      v-if="!system.status"
      class="rounded-lg border border-line bg-surface px-3 py-2.5 text-[13px] text-ink-3"
      role="status"
    >
      正在连接服务,状态未知…
    </p>

    <Panel title="运行状况" description="数据库与后台进程是否正常">
      <SpecGrid :items="healthRows" :cols="3" />

      <div
        v-if="system.status && counts.requires_restart > 0"
        class="mt-3 flex items-start gap-2 rounded-lg border border-warn/30 bg-warn-soft px-3 py-2.5"
      >
        <RefreshCw class="mt-0.5 size-4 shrink-0 text-warn" aria-hidden="true" />
        <p class="text-[12.5px] leading-5 text-ink-2">
          {{ counts.requires_restart }} 个模组的配置已写入,待服务器重启后生效。
        </p>
      </div>

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

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Panel title="配置与统计" description="当前运行配置与内容概况">
        <SpecGrid :items="configRows" :cols="2" />
      </Panel>

      <Panel title="维护操作">
        <p class="text-[12.5px] leading-5 text-ink-3">
          重新扫描服务器已有文件以更新模组库,不会下载或安装新内容;全量扫描会额外校验文件完整性,耗时更长。
        </p>
        <div class="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" :loading="scanning" :disabled="system.readOnly" @click="startScan(false)">
            快速扫描
          </Button>
          <Button variant="primary" :loading="scanning" :disabled="system.readOnly" @click="startScan(true)">
            全量扫描(校验文件)
          </Button>
        </div>

        <div v-if="activePlan" class="mt-4 border-t border-line pt-3.5">
          <p class="text-[13px] font-medium text-ink">进行中的变更计划</p>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <Badge :variant="planStatusTone(activePlan.status)">
              {{ PLAN_STATUS_ZH[activePlan.status] || activePlan.status }}
            </Badge>
            <span class="small muted">{{ activePlan.payload?.length ?? 0 }} 个变更项</span>
            <span class="small muted">{{ formatTime(activePlan.created_at) }}</span>
          </div>
          <Button
            size="sm"
            variant="secondary"
            class="mt-2.5"
            @click="router.push({ name: 'plan-detail', params: { id: activePlan.id } })"
          >
            查看详情
          </Button>
        </div>
        <p v-else-if="system.status" class="mt-4 border-t border-line pt-3.5 text-[13px] text-ink-3">
          当前没有进行中的变更计划。
        </p>
        <div v-else class="mt-4 space-y-2.5 border-t border-line pt-3.5">
          <Skeleton class="h-4 w-2/3" />
          <Skeleton class="h-4 w-1/3" />
        </div>
      </Panel>
    </div>
  </div>
</template>
