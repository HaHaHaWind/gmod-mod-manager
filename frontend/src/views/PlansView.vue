<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiPlanList } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { PlanView } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { toast } from '@/composables/useToast'
import { PLAN_STATUS_ZH, formatTime, planStatusTone, planTitle } from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import CopyButton from '@/components/ui/CopyButton.vue'
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
    toast.error(e instanceof ApiRequestError ? e.message : '加载变更记录失败')
  } finally {
    loading.value = false
  }
}

function openPlan(id: string) {
  router.push({ name: 'plan-detail', params: { id } })
}

onMounted(() => { load(); system.refresh() })
</script>

<template>
  <div class="space-y-4">
    <!-- 页面标题区 -->
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
      <h2 class="text-2xl font-semibold tracking-tight text-ink">变更记录</h2>
      <span class="small muted">所有变更先形成预览,确认提交后再应用,可随时取消</span>
      <span class="spacer" />
      <Select v-model="statusFilter" :options="statusOptions" class="w-[168px]" aria-label="状态筛选" @update:model-value="load" />
      <Button variant="secondary" :loading="loading" @click="load">刷新</Button>
    </div>

    <Panel :padded="false">
      <div v-if="loading && rows.length === 0" class="space-y-2 p-4">
        <Skeleton v-for="i in 6" :key="i" class="h-12 w-full" />
      </div>

      <EmptyState
        v-else-if="rows.length === 0"
        title="没有符合条件的变更记录"
        description="在模组库勾选条目后,通过底部批量操作栏即可生成变更预览。"
      />

      <div v-else class="overflow-x-auto">
        <table class="tbl">
          <thead>
            <tr>
              <th>变更</th>
              <th style="width: 130px">状态</th>
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
                  class="text-left text-[13.5px] font-medium text-accent hover:underline"
                  @click="openPlan(row.id)"
                >
                  {{ planTitle(row.payload) }}
                </button>
                <span class="mono mt-0.5 flex items-center gap-1.5 text-[11.5px] text-ink-4">
                  {{ row.id.slice(0, 12) }}…
                  <CopyButton :text="row.id" label="计划 ID" />
                  <Badge v-if="row.id === activeId" variant="warning">进行中</Badge>
                </span>
              </td>
              <td>
                <Badge :variant="planStatusTone(row.status)">
                  {{ PLAN_STATUS_ZH[row.status] || row.status }}
                </Badge>
              </td>
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
