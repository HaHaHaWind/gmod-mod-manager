<script setup lang="ts">
/** 变更计划列表:状态筛选 + 活跃计划高亮。 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiPlanList } from '@/api'
import type { PlanView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { useSystemStore } from '@/stores/system'
import { PLAN_STATUS_ZH, ACTION_ZH, formatTime, planStatusTag } from '@/utils/format'

const router = useRouter()
const system = useSystemStore()

const loading = ref(false)
const rows = ref<PlanView[]>([])
const statusFilter = ref('')

const statusOptions = [
  { value: '', label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'staged', label: '已提交待应用' },
  { value: 'applying', label: '应用中' },
  { value: 'applied', label: '已应用' },
  { value: 'failed', label: '失败' },
  { value: 'recovery_required', label: '需要恢复' },
  { value: 'cancelled', label: '已取消' },
]

async function load() {
  loading.value = true
  try {
    const resp = await apiPlanList(statusFilter.value, 50)
    rows.value = resp.items
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '加载计划列表失败')
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

const activeId = computed(() => system.activePlanId)

function rowClass({ row }: { row: PlanView }): string {
  return row.id === activeId.value ? 'active-row' : ''
}

onMounted(() => { load(); system.refresh() })
</script>

<template>
  <div class="page-card">
    <div class="toolbar">
      <el-select v-model="statusFilter" style="width: 160px" @change="load">
        <el-option v-for="o in statusOptions" :key="o.value" :label="`状态:${o.label}`"
                   :value="o.value" />
      </el-select>
      <div class="toolbar-space" />
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" :row-class-name="rowClass">
      <el-table-column label="计划 ID" width="200">
        <template #default="{ row }">
          <router-link class="mono plan-link"
                       :to="{ name: 'plan-detail', params: { id: row.id } }">
            {{ row.id.slice(0, 12) }}…
          </router-link>
          <el-tag v-if="row.id === activeId" type="warning" size="small" class="active-tag">
            进行中
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="planStatusTag(row.status)" size="small">
            {{ PLAN_STATUS_ZH[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="变更摘要" min-width="180">
        <template #default="{ row }">{{ summaryOf(row) }}</template>
      </el-table-column>
      <el-table-column prop="created_by" label="创建人" width="110" />
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应用时间" width="160">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.applied_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary"
                     @click="router.push({ name: 'plan-detail', params: { id: row.id } })">
            详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.toolbar-space { flex: 1; }
.plan-link { color: var(--el-color-primary); text-decoration: none; }
.active-tag { margin-left: 6px; }
:deep(.active-row) { background: var(--el-color-warning-light-9); }
</style>
