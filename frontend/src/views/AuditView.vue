<script setup lang="ts">
/** 审计日志:分页 + 详情展开(敏感字段已由后端脱敏),仅管理员可见。 */
import { onMounted, ref, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { apiAuditList } from '@/api'
import type { AuditView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { toast } from '@/composables/useToast'
import { OUTCOME_ZH, formatTime, outcomeTone } from '@/utils/format'
import { cn } from '@/lib/utils'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Pagination from '@/components/ui/Pagination.vue'
import Panel from '@/components/ui/Panel.vue'
import Skeleton from '@/components/ui/Skeleton.vue'

const loading = ref(false)
const rows = ref<AuditView[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const expanded = ref<number | null>(null)

function prettyJson(v: unknown): string {
  if (v === null || v === undefined) return '-'
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function toggle(id: number) {
  expanded.value = expanded.value === id ? null : id
}

async function load() {
  loading.value = true
  try {
    const resp = await apiAuditList(page.value, pageSize.value)
    rows.value = resp.items
    total.value = resp.total
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '加载审计日志失败')
  } finally {
    loading.value = false
  }
}

watch([page, pageSize], () => { expanded.value = null; load() })
onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-[24px] font-semibold tracking-tight text-ink">审计日志</h1>
        <p class="mt-1 text-[13.5px] text-ink-3">
          所有管理操作(含被拒绝的请求)均有记录,共 {{ total }} 条。
        </p>
      </div>
      <Button size="sm" :loading="loading" @click="load">刷新</Button>
    </div>

    <Panel :padded="false">
      <div v-if="loading && rows.length === 0" class="space-y-2 p-4">
        <Skeleton v-for="i in 8" :key="i" class="h-10 w-full" />
      </div>

      <EmptyState
        v-else-if="rows.length === 0"
        title="暂无审计记录"
        description="管理操作发生后会记录在此。"
      />

      <div v-else class="overflow-x-auto">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width: 110px">操作人</th>
              <th style="width: 190px">动作</th>
              <th style="width: 200px">对象</th>
              <th style="width: 90px">结果</th>
              <th style="width: 168px">时间</th>
              <th style="width: 130px">来源 IP</th>
              <th style="width: 150px">request_id</th>
              <th style="width: 52px"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in rows" :key="row.id">
              <tr>
                <td>{{ row.actor || '-' }}</td>
                <td><span class="mono text-[12.5px]">{{ row.action }}</span></td>
                <td><span class="mono text-[12.5px]">{{ row.target_type }}:{{ row.target_id || '-' }}</span></td>
                <td>
                  <Badge :variant="outcomeTone(row.outcome)">
                    {{ OUTCOME_ZH[row.outcome] || row.outcome }}
                  </Badge>
                </td>
                <td class="muted num">{{ formatTime(row.ts) }}</td>
                <td><span class="mono text-[12.5px]">{{ row.ip || '-' }}</span></td>
                <td>
                  <span class="mono tiny muted">
                    {{ row.request_id ? row.request_id.slice(0, 10) + '…' : '-' }}
                  </span>
                </td>
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
                <td colspan="8" class="bg-surface-muted/60">
                  <pre class="mono m-0 max-h-64 overflow-auto rounded-md bg-surface p-3 text-[12px] leading-6 text-ink-2">{{ prettyJson(row.detail) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </Panel>

    <div v-if="total > 0" class="flex justify-end">
      <Pagination v-model:page="page" v-model:page-size="pageSize" :total="total" />
    </div>
  </div>
</template>
