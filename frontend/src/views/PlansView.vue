<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiPlanList } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { PlanView } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { toast } from '@/composables/useToast'
import { ACTION_ZH, PLAN_STATUS_ZH, formatTime, planStatusTone } from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Panel from '@/components/ui/Panel.vue'
import Select from '@/components/ui/Select.vue'
import Skeleton from '@/components/ui/Skeleton.vue'

const router = useRouter()
const system = useSystemStore()

const loading = ref(false)
const rows = ref<PlanView[]>([])
const statusFilter = ref('')

const statusOptions = [
  { value: '', label: '状态:全部' },
  { value: 'draft', label: '草稿' },
  { value: 'staged', label: '已提交待应用' },
  { value: 'applying', label: '应用中' },
  { value: 'applied', label: '已应用' },
  { value: 'failed', label: '失败' },
  { value: 'recovery_required', label: '需要恢复' },
  { value: 'cancelled', label: '已取消' },
]

const activeId = computed(() => system.activePlanId)

async function load() {
  loading.value = true
  try {
    rows.value = (await apiPlanList(statusFilter.value, 50)).items
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '加载计划列表失败')
  } finally {
    loading.value = false
  }
}

function summaryOf(p: PlanView): string {
  const s = p.diff?.summary ?? {}
  const parts: string[] = []
  for (const act of ['enable', 'disable', 'delete']) {
    const n = Number(s[act] ?? 0)
    if (n > 0) parts.push(`${ACTION_ZH[act]} × ${n}`)
  }
  return parts.length ? parts.join(' / ') : '无变更项'
}

function openPlan(id: string) {
  router.push({ name: 'plan-detail', params: { id } })
}

onMounted(() => { load(); system.refresh() })
</script>

<template>
  <div>
    <Panel title="变更计划" description="所有变更都先形成计划,预览确认后再提交与应用">
      <template #actions>
        <Select v-model="statusFilter" :options="statusOptions" class="w-[168px]" aria-label="状态筛选" @update:model-value="load" />
        <Button size="sm" :loading="loading" @click="load">刷新</Button>
      </template>

      <div v-if="loading && rows.length === 0" class="space-y-2">
        <Skeleton v-for="i in 6" :key="i" class="h-10 w-full" />
      </div>

      <EmptyState
        v-else-if="rows.length === 0"
        title="没有符合条件的计划"
        description="在 Mod 库中勾选条目即可创建变更计划。"
      />

      <div v-else class="-mx-4 -mb-4 overflow-x-auto">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width: 220px">计划 ID</th>
              <th style="width: 130px">状态</th>
              <th>变更摘要</th>
              <th style="width: 110px">创建人</th>
              <th style="width: 168px">创建时间</th>
              <th style="width: 168px">应用时间</th>
              <th style="width: 84px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id" :class="row.id === activeId ? 'bg-warn-soft' : ''">
              <td>
                <button
                  type="button"
                  class="mono text-[12.5px] text-accent hover:underline"
                  :title="row.id"
                  @click="openPlan(row.id)"
                >
                  {{ row.id.slice(0, 12) }}…
                </button>
                <Badge v-if="row.id === activeId" variant="warning" class="ml-1.5">进行中</Badge>
              </td>
              <td>
                <Badge :variant="planStatusTone(row.status)">
                  {{ PLAN_STATUS_ZH[row.status] || row.status }}
                </Badge>
              </td>
              <td>{{ summaryOf(row) }}</td>
              <td>{{ row.created_by || '-' }}</td>
              <td class="muted num">{{ formatTime(row.created_at) }}</td>
              <td class="muted num">{{ formatTime(row.applied_at) }}</td>
              <td>
                <Button size="sm" variant="ghost" class="text-accent hover:bg-accent-soft" @click="openPlan(row.id)">
                  详情
                </Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>
  </div>
</template>