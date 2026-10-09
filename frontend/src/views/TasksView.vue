<script setup lang="ts">
/** 后台任务:列表 + 轮询(存在进行中任务时 5s 刷新)+ 结果展开。 */
import { computed, onMounted, ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
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
  <div class="space-y-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-[24px] font-semibold tracking-tight text-ink">后台任务</h1>
        <p class="mt-1 text-[13.5px] text-ink-3">
          扫描模组、更新模组信息、应用变更等操作在此排队执行;任务结束不代表每一项都成功,展开可查看结果。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Badge v-if="hasActive" variant="warning">
          <span class="relative flex size-1.5" aria-hidden="true">
            <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-warn opacity-60" />
            <span class="relative inline-flex size-1.5 rounded-full bg-warn" />
          </span>
          有任务进行中,自动刷新
        </Badge>
        <Button size="sm" :loading="loading" @click="load()">刷新</Button>
      </div>
    </div>

    <Panel :padded="false">
      <div v-if="loading && rows.length === 0" class="space-y-2 p-4">
        <Skeleton v-for="i in 5" :key="i" class="h-11 w-full" />
      </div>

      <EmptyState
        v-else-if="rows.length === 0"
        title="暂无后台任务"
        description="扫描模组、更新模组信息或应用变更后,任务会出现在这里。"
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
                  <template v-else-if="row.status === 'running'">
                    <Progress :tone="progressTone(row)" indeterminate />
                    <p class="tiny muted mt-1">总数未知,执行中</p>
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
                  <p v-if="row.error" class="mb-2 text-[12.5px] text-danger">
                    <span class="font-medium">失败原因:</span>{{ row.error }}
                  </p>
                  <p v-else-if="row.status === 'succeeded'" class="mb-2 text-[12.5px] text-ink-3">
                    任务已结束。以下为后台返回的处理摘要,涉及条目的最终状态以模组库为准。
                  </p>
                  <pre class="mono m-0 max-h-64 overflow-auto rounded-md bg-surface p-3 text-[12px] leading-6 text-ink-2">{{ prettyJson(row.result) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </Panel>
  </div>
</template>
