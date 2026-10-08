<script setup lang="ts">
/** Mod 库:筛选 + 分页表格 + 多选创建变更计划。 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiCreatePlan, apiModList, apiRefreshMeta, apiStartScan, localPreview } from '@/api'
import type { ModListQuery, PlanItemInput } from '@/api'
import type { ModView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { useSystemStore } from '@/stores/system'
import { ACTION_ZH, applyTag, formatBytes, formatTime, inventoryTag } from '@/utils/format'

const router = useRouter()
const system = useSystemStore()

const loading = ref(false)
const rows = ref<ModView[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const q = ref('')
const inventoryState = ref('')
const desiredState = ref('')
const applyState = ref('')
const selected = ref<ModView[]>([])

async function load() {
  loading.value = true
  try {
    const query: ModListQuery = {
      q: q.value || undefined,
      inventory_state: inventoryState.value || undefined,
      desired_state: desiredState.value || undefined,
      apply_state: applyState.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    }
    const resp = await apiModList(query)
    rows.value = resp.items
    total.value = resp.total
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '加载 Mod 列表失败')
  } finally {
    loading.value = false
  }
}

let searchTimer: number | undefined
watch(q, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => { page.value = 1; load() }, 400)
})
watch([inventoryState, desiredState, applyState], () => { page.value = 1; load() })
watch(pageSize, () => { page.value = 1; load() })
watch(page, load)

// ---- 创建变更计划对话框 ----
const planVisible = ref(false)
const planSubmitting = ref(false)
const planActions = ref<Record<string, 'enable' | 'disable' | 'delete'>>({})

function defaultAction(m: ModView): 'enable' | 'disable' | 'delete' {
  if (m.desired_state === 'enabled') return 'disable'
  return 'enable'
}

function openPlanDialog() {
  if (!selected.value.length) { ElMessage.warning('请先勾选要变更的 Mod'); return }
  const map: Record<string, 'enable' | 'disable' | 'delete'> = {}
  for (const m of selected.value) map[m.workshop_id] = defaultAction(m)
  planActions.value = map
  planVisible.value = true
}

async function submitPlan() {
  const items: PlanItemInput[] = selected.value.map((m) => ({
    action: planActions.value[m.workshop_id],
    workshop_id: m.workshop_id,
  }))
  planSubmitting.value = true
  try {
    const plan = await apiCreatePlan(items)
    planVisible.value = false
    ElMessage.success('变更计划已创建,请确认预览后提交')
    router.push({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '创建计划失败')
  } finally {
    planSubmitting.value = false
  }
}

// ---- 扫描 / 元数据 ----
function requireWritable(): boolean {
  if (system.readOnly) {
    ElMessage.warning('当前为只读模式,无法执行该操作')
    return false
  }
  return true
}

const scanning = ref(false)
async function startScan(deep: boolean) {
  if (!requireWritable()) return
  scanning.value = true
  try {
    await apiStartScan(deep)
    ElMessage.success('扫描任务已创建')
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '创建扫描任务失败')
  } finally {
    scanning.value = false
  }
}

const refreshingMeta = ref(false)
async function refreshMeta() {
  if (!requireWritable()) return
  if (!selected.value.length) { ElMessage.warning('请先勾选要刷新的 Mod'); return }
  refreshingMeta.value = true
  try {
    const resp = await apiRefreshMeta(selected.value.map((m) => m.workshop_id))
    ElMessage.success(`元数据刷新任务已创建,共 ${resp.ids.length} 项`)
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '创建刷新任务失败')
  } finally {
    refreshingMeta.value = false
  }
}

const stateOptions = computed(() => [
  { value: '', label: '全部' },
  { value: 'present', label: '正常' },
  { value: 'missing', label: '缺失' },
  { value: 'invalid', label: '异常' },
  { value: 'trashed', label: '回收站' },
])
const desiredOptions = [
  { value: '', label: '全部' },
  { value: 'enabled', label: '期望启用' },
  { value: 'disabled', label: '期望禁用' },
  { value: 'unmanaged', label: '未接管' },
]
const applyOptions = [
  { value: '', label: '全部' },
  { value: 'synced', label: '已同步(待重启)' },
  { value: 'pending', label: '待应用' },
  { value: 'failed', label: '应用失败' },
  { value: 'conflict', label: '存在冲突' },
  { value: 'unmanaged', label: '未接管' },
]

onMounted(load)
</script>

<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="q" placeholder="搜索标题 / 文件夹名 / Workshop ID" clearable
                style="width: 280px" />
      <el-select v-model="inventoryState" style="width: 120px">
        <el-option v-for="o in stateOptions" :key="o.value" :label="`清单:${o.label}`"
                   :value="o.value" />
      </el-select>
      <el-select v-model="desiredState" style="width: 130px">
        <el-option v-for="o in desiredOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-model="applyState" style="width: 160px">
        <el-option v-for="o in applyOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <div class="toolbar-space" />
      <el-button :loading="scanning" :disabled="system.readOnly" @click="startScan(false)">
        扫描缓存
      </el-button>
      <el-button :loading="refreshingMeta" :disabled="system.readOnly" @click="refreshMeta">
        刷新元数据
      </el-button>
      <el-button type="primary" :disabled="system.readOnly || !selected.length"
                 @click="openPlanDialog">
        创建变更计划({{ selected.length }})
      </el-button>
    </div>

    <el-table :data="rows" v-loading="loading" @selection-change="(v: ModView[]) => selected = v"
              row-key="workshop_id" size="default">
      <el-table-column type="selection" width="42" />
      <el-table-column label="Mod" min-width="320">
        <template #default="{ row }">
          <div class="mod-cell">
            <el-image class="mod-thumb" :src="row.preview_url ? localPreview(row.workshop_id) : ''"
                      fit="cover" lazy>
              <template #error><div class="mod-thumb-err">无预览</div></template>
            </el-image>
            <div class="mod-cell-text">
              <router-link class="mod-title" :to="{ name: 'mod-detail', params: { wid: row.workshop_id } }">
                {{ row.title || row.folder_name || row.workshop_id }}
              </router-link>
              <div class="mono muted small">
                ID {{ row.workshop_id }}
                <a :href="'https://steamcommunity.com/sharedfiles/filedetails/?id=' + row.workshop_id"
                   target="_blank" rel="noopener">工坊页面</a>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="清单状态" width="90">
        <template #default="{ row }">
          <el-tag :type="inventoryTag(row.inventory_state)" size="small">
            {{ row.inventory_zh || row.inventory_state }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="期望状态" width="96">
        <template #default="{ row }">{{ row.desired_zh || row.desired_state }}</template>
      </el-table-column>
      <el-table-column label="应用状态" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.apply_state !== 'unmanaged'" :type="applyTag(row.apply_state)" size="small">
            {{ row.apply_zh || row.apply_state }}
          </el-tag>
          <span v-else class="muted">未接管</span>
        </template>
      </el-table-column>
      <el-table-column label="运行时" width="70">
        <template #default="{ row }">
          <span :class="row.requires_restart ? 'restart-flag' : 'muted'">
            {{ row.requires_restart ? '待重启' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">
          <span class="mono">{{ formatBytes(row.size_bytes) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="150">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.time_updated) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary"
                     @click="router.push({ name: 'mod-detail', params: { wid: row.workshop_id } })">
            详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize"
                     :total="total" :page-sizes="[20, 50, 100]"
                     layout="total, sizes, prev, pager, next" background />
    </div>

    <el-dialog v-model="planVisible" title="创建变更计划" width="640px">
      <el-alert type="info" show-icon :closable="false" class="plan-tip"
                title="先预览,后提交;应用前可随时取消。计划 30 分钟未提交将过期。" />
      <el-table :data="selected" size="small" max-height="360">
        <el-table-column label="Mod" min-width="200">
          <template #default="{ row }">
            {{ row.title || row.folder_name }}
            <div class="mono muted small">ID {{ row.workshop_id }}</div>
          </template>
        </el-table-column>
        <el-table-column label="当前期望" width="110">
          <template #default="{ row }">{{ row.desired_zh || row.desired_state }}</template>
        </el-table-column>
        <el-table-column label="目标动作" width="150">
          <template #default="{ row }">
            <el-select v-model="planActions[row.workshop_id]" size="small">
              <el-option v-for="(zh, act) in ACTION_ZH" :key="act" :label="zh" :value="act" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="planVisible = false">取消</el-button>
        <el-button type="primary" :loading="planSubmitting" @click="submitPlan">
          生成预览
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.toolbar-space { flex: 1; }
.mod-cell { display: flex; gap: 10px; align-items: center; }
.mod-thumb { width: 72px; height: 42px; border-radius: 4px; background: #f0f2f5; flex: none; }
.mod-thumb-err {
  width: 72px; height: 42px; display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: #c0c4cc; background: #f5f7fa;
}
.mod-cell-text { min-width: 0; }
.mod-title { color: #303133; text-decoration: none; font-weight: 500; }
.mod-title:hover { color: var(--el-color-primary); }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.plan-tip { margin-bottom: 12px; }
.restart-flag { color: var(--el-color-warning); font-weight: 600; }
</style>
