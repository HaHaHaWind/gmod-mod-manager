<script setup lang="ts">
/** 计划详情:预览 diff + 阻塞项 + 提交/应用/取消/重试 + 应用结果。 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiPlanApply, apiPlanCancel, apiPlanDetail, apiPlanRetry, apiPlanSubmit } from '@/api'
import type { PlanView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { useSystemStore } from '@/stores/system'
import {
  ACTION_ZH, ITEM_STATUS_ZH, PLAN_STATUS_ZH, itemStatusTag, formatTime, planStatusTag,
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const system = useSystemStore()

const planId = computed(() => String(route.params.id || ''))
const plan = ref<PlanView | null>(null)
const loading = ref(false)
const acting = ref(false)
let timer: number | undefined

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    plan.value = await apiPlanDetail(planId.value)
  } catch (e) {
    if (!silent) ElMessage.error(e instanceof ApiRequestError ? e.message : '加载计划失败')
  } finally {
    if (!silent) loading.value = false
  }
}

async function runAction(fn: () => Promise<unknown>, okMsg: string) {
  acting.value = true
  try {
    await fn()
    ElMessage.success(okMsg)
    await load(true)
    await system.refresh()
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '操作失败')
  } finally {
    acting.value = false
  }
}

function confirmThen(message: string, fn: () => Promise<unknown>, okMsg: string) {
  ElMessageBox.confirm(message, '操作确认', {
    confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning',
  }).then(() => runAction(fn, okMsg)).catch(() => undefined)
}

const submitPlan = () =>
  confirmThen('提交后期望状态将立即更新(服务器尚未生效),确认提交?', () => apiPlanSubmit(planId.value), '计划已提交')
const applyPlan = () =>
  confirmThen('将对服务器配置执行变更(不会自动重启服务器),确认应用?', () => apiPlanApply(planId.value), '应用任务已启动')
const cancelPlan = () =>
  confirmThen('取消后该计划不可再用,确认取消?', () => apiPlanCancel(planId.value), '计划已取消')
const retryPlan = () => runAction(() => apiPlanRetry(planId.value), '重试任务已启动')

const status = computed(() => plan.value?.status ?? '')
const canSubmit = computed(() => status.value === 'draft')
const canApply = computed(() => status.value === 'staged')
const canCancel = computed(() => ['draft', 'staged'].includes(status.value))
const canRetry = computed(() => ['failed', 'recovery_required'].includes(status.value))

const blockers = computed(() => plan.value?.diff?.blockers ?? [])
const perItems = computed(() => plan.value?.diff?.per_item ?? [])
const items = computed(() => plan.value?.items ?? [])
const summary = computed(() => plan.value?.diff?.summary ?? {})

onMounted(() => {
  load()
  timer = window.setInterval(() => {
    if (['draft', 'staged'].includes(status.value)) return
    load(true)
  }, 5000)
})
onUnmounted(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <div v-loading="loading" class="page-card">
    <template v-if="plan">
      <div class="plan-head">
        <div>
          <div class="mono muted small">{{ plan.id }}</div>
          <div class="plan-head-status">
            <el-tag :type="planStatusTag(plan.status)">
              {{ PLAN_STATUS_ZH[plan.status] || plan.status }}
            </el-tag>
            <span class="muted">创建人 {{ plan.created_by }}</span>
            <span class="muted">创建于 {{ formatTime(plan.created_at) }}</span>
            <span v-if="plan.expires_at" class="muted">过期于 {{ formatTime(plan.expires_at) }}</span>
            <span v-if="plan.applied_at" class="muted">应用于 {{ formatTime(plan.applied_at) }}</span>
          </div>
        </div>
        <div class="plan-actions">
          <el-button v-if="canSubmit" type="primary" :loading="acting" @click="submitPlan">
            提交计划
          </el-button>
          <el-button v-if="canApply" type="success" :loading="acting" @click="applyPlan">
            应用到服务器
          </el-button>
          <el-button v-if="canRetry" type="warning" plain :loading="acting" @click="retryPlan">
            重试失败项
          </el-button>
          <el-button v-if="canCancel" :loading="acting" @click="cancelPlan">取消计划</el-button>
          <el-button link @click="router.push({ name: 'plans' })">返回列表</el-button>
        </div>
      </div>

      <el-alert v-if="plan.error" type="error" show-icon :closable="false" class="plan-err"
                :title="plan.error" />

      <div class="plan-summary">
        <el-tag v-for="(n, act) in summary" :key="act" effect="plain" class="sum-tag"
                :type="act === 'delete' ? 'danger' : act === 'disable' ? 'warning' : 'success'">
          {{ ACTION_ZH[act] || act }} × {{ n }}
        </el-tag>
        <span class="muted small">
          模式:{{ plan.diff?.mode }} / 策略:{{ plan.diff?.strategy || '-' }} /
          基线版本 r{{ plan.base_revision }}
        </span>
      </div>

      <template v-if="blockers.length">
        <h4 class="plan-sub">阻塞项(必须先解决)</h4>
        <el-alert v-for="(b, i) in blockers" :key="i" type="error" show-icon :closable="false"
                  class="blocker"
                  :title="`${b.workshop_id}(${ACTION_ZH[b.action] || b.action}):${b.reason}`" />
      </template>

      <h4 class="plan-sub">预览({{ perItems.length }} 项)</h4>
      <el-table :data="perItems" size="small">
        <el-table-column label="Mod" min-width="200">
          <template #default="{ row }">
            {{ row.title || '-' }}
            <div class="mono muted small">ID {{ row.workshop_id }}</div>
          </template>
        </el-table-column>
        <el-table-column label="动作" width="80">
          <template #default="{ row }">{{ ACTION_ZH[row.action] || row.action }}</template>
        </el-table-column>
        <el-table-column label="变更" min-width="200">
          <template #default="{ row }">
            <span v-if="row.from" class="muted small">
              清单 {{ row.from.inventory_state }} / 期望 {{ row.from.desired_state }} →
            </span>
            <span v-if="row.to" class="small">
              清单 {{ row.to.inventory_state ?? '-' }} / 期望 {{ row.to.desired_state }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="警告 / 阻塞" min-width="200">
          <template #default="{ row }">
            <template v-if="row.blocked">
              <el-tag type="danger" size="small">已阻塞</el-tag>
              <span class="block-reason">{{ row.block_reason }}</span>
            </template>
            <template v-else-if="row.warnings.length">
              <el-tag v-for="(w, i) in row.warnings" :key="i" type="warning" size="small"
                      class="warn-tag">{{ w }}</el-tag>
            </template>
            <span v-else class="muted small">-</span>
          </template>
        </el-table-column>
      </el-table>

      <template v-if="items.length">
        <h4 class="plan-sub">执行结果({{ items.length }} 项)</h4>
        <el-table :data="items" size="small">
          <el-table-column label="Workshop ID" width="140">
            <template #default="{ row }">
              <router-link class="mono item-link"
                           :to="{ name: 'mod-detail', params: { wid: row.workshop_id } }">
                {{ row.workshop_id }}
              </router-link>
            </template>
          </el-table-column>
          <el-table-column label="动作" width="80">
            <template #default="{ row }">{{ ACTION_ZH[row.action] || row.action }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="itemStatusTag(row.status)" size="small">
                {{ ITEM_STATUS_ZH[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="错误" min-width="220">
            <template #default="{ row }">
              <span class="item-err">{{ row.error || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </template>
    <el-empty v-else-if="!loading" description="未找到该计划" />
  </div>
</template>

<style scoped>
.plan-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.plan-head-status { margin-top: 8px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.plan-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.plan-err { margin-top: 12px; }
.plan-summary { margin-top: 14px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sum-tag { font-weight: 500; }
.plan-sub { margin: 18px 0 8px; font-size: 14px; color: #303133; }
.blocker { margin-bottom: 6px; }
.block-reason { margin-left: 6px; color: var(--el-color-danger); font-size: 12px; }
.warn-tag { margin-right: 4px; }
.item-link { color: var(--el-color-primary); text-decoration: none; }
.item-err { color: var(--el-color-danger); font-size: 12px; }
.small { font-size: 12px; }
</style>
