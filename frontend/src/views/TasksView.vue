<script setup lang="ts">
/** 任务中心:列表 + 轮询(存在进行中任务时 5s 刷新)+ 结果展开。 */
import { computed, onMounted, ref } from 'vue'
import { Activity, ChevronDown } from 'lucide-vue-next'
import { apiTaskList } from '@/api'
import type { TaskView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { toast } from '@/composables/useToast'
import { usePolling } from '@/composables/usePolling'
import { TASK_KIND_ZH, TASK_STATUS_ZH, formatTime, taskStatusTone } from '@/utils/format'
import { cn } from '@/lib/utils'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Panel from '@/components/ui/Panel.vue'
import Progress from '@/components/ui/Progress.vue'
import Skeleton from '@/components/ui/Skeleton.vue'

const loading = ref(false)
const rows = ref<TaskView[]>([])
const expanded = ref('')

const hasActive = computed(() =>
  rows.value.some((t) => t.status === 'queued' || t.status === 'running'))

function progressPct(t: TaskView): number {
  return t.total > 0 ? (t.progress * 100) / t.total : 0
}

function progressTone(t: TaskView): 'accent' | 'success' | 'danger' {
  if (t.status === 'failed' || t.status === 'interrupted') return 'danger'
  if (t.status === 'succeeded') return 'success'
  return 'accent'
}

function prettyJson(v: unknown): string {
  if (v === null || v === undefined) return '-'
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function toggle(id: string) {
  expanded.value = expanded.value === id ? '' : id
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    rows.value = (await apiTaskList(30)).items
  } catch (e) {
    if (!silent) toast.error(e instanceof ApiRequestError ? e.message : '加载任务列表失败')
  } finally {
    if (!silent) loading.value = false
  }
}

usePolling(() => load(true), 5000, { immediate: false })
onMounted(() => load())
</script>

<template>
  <Panel
    title="任务中心"
    description="后台任务由独立进程执行;应用计划、扫描、元数据刷新均在此排队"
    :padded="false"
  >
    <template #actions>
      <Badge v-if="hasActive" variant="warning">
        <Activity class="size-3" aria-hidden="true" />
        自动刷新中
      </Badge>
      <Button size="sm" :loading="loading" @click="load()">刷新</Button>
    </template>

    <div v-if="loading && rows.length === 0" class="space-y-2 p-4">
      <Skeleton v-for="i in 5" :key="i" class="h-11 w-full" />
    </div>

    <EmptyState
      v-else-if="rows.length === 0"
      title="暂无任务"
      description="执行扫描、刷新元数据或应用计划后,任务会出现在这里。"
    />

    <div v-else class="overflow-x-auto">
      <table class="tbl">
        <thead>
          <tr>
            <th style="width: 170px">任务</th>
            <th style="width: 100px">状态</th>
            <th style="width: 180px">进度</th>
            <th style="width: 130px">关联计划</th>
            <th style="width: 168px">创建时间</th>
            <th style="width: 168px">结束时间</th>
            <th style="width: 52px"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.id">
            <tr>
              <td>
                <p class="font-medium text-ink">{{ TASK_KIND_ZH[row.kind] || row.kind }}</p>
                <p class="mono tiny muted">{{ row.id.slice(0, 12) }}…</p>
              </td>
              <td>
                <Badge :variant="taskStatusTone(row.status)">
                  {{ TASK_STATUS_ZH[row.status] || row.status }}
                </Badge>
              </td>
              <td>
                <template v-if="row.total > 0">
                  <Progress :value="progressPct(row)" :tone="progressTone(row)" />
                  <p class="num tiny muted mt-1">{{ row.progress }} / {{ row.total }}</p>
                </template>
                <span v-else class="muted">-</span>
              </td>
              <td>
                <router-link
                  v-if="row.plan_id"
                  class="mono text-[12.5px] text-accent hover:underline"
                  :to="{ name: 'plan-detail', params: { id: row.plan_id } }"
                >
                  {{ row.plan_id.slice(0, 10) }}…
                </router-link>
                <span v-else class="muted">-</span>
              </td>
              <td class="muted num">{{ formatTime(row.created_at) }}</td>
              <td class="muted num">{{ formatTime(row.finished_at) }}</td>
              <td>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  :aria-label="expanded === row.id ? '收起详情' : '展开详情'"
                  :aria-expanded="expanded === row.id"
                  @click="toggle(row.id)"
                >
                  <ChevronDown
                    :class="cn('size-3.5 transition-transform duration-200', expanded === row.id && 'rotate-180')"
                    aria-hidden="true"
                  />
                </Button>
              </td>
            </tr>
            <tr v-if="expanded === row.id">
              <td colspan="7" class="bg-surface-muted/60">
                <p v-if="row.error" class="mb-2 text-[12.5px] text-danger">错误:{{ row.error }}</p>
                <pre class="mono m-0 max-h-64 overflow-auto rounded-md bg-surface p-3 text-[12px] leading-6 text-ink-2">{{ prettyJson(row.result) }}</pre>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </Panel>
</template>