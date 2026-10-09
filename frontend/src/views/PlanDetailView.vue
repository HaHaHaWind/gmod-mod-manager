<script setup lang="ts">
/** 计划详情:预览 diff + 阻塞项 + 提交/应用/取消/重试 + 应用结果。 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, Check, Loader2, Play, RotateCw, ShieldAlert, TriangleAlert, X,
} from 'lucide-vue-next'
import { apiPlanApply, apiPlanCancel, apiPlanDetail, apiPlanRetry, apiPlanSubmit } from '@/api'
import type { PlanView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { useSystemStore } from '@/stores/system'
import { confirmDialog } from '@/composables/useConfirm'
import { toast } from '@/composables/useToast'
import { usePolling } from '@/composables/usePolling'
import {
  ACTION_ZH, ITEM_STATUS_ZH, PLAN_STATUS_ZH,
  formatTime, itemStatusTone, planStatusTone, planTitle, type Tone,
} from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import CopyButton from '@/components/ui/CopyButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Panel from '@/components/ui/Panel.vue'
import Skeleton from '@/components/ui/Skeleton.vue'

const route = useRoute()
const router = useRouter()
const system = useSystemStore()

const planId = computed(() => String(route.params.id || ''))
const plan = ref<PlanView | null>(null)
const loading = ref(false)
const acting = ref(false)

const status = computed(() => plan.value?.status ?? '')
const blockers = computed(() => plan.value?.diff?.blockers ?? [])
const perItems = computed(() => plan.value?.diff?.per_item ?? [])
const items = computed(() => plan.value?.items ?? [])
const summaryEntries = computed(() =>
  Object.entries(plan.value?.diff?.summary ?? {}).filter(([, n]) => Number(n) > 0),
)

const canSubmit = computed(() => status.value === 'draft' && blockers.value.length === 0)
const canApply = computed(() => status.value === 'staged')
const canCancel = computed(() => ['draft', 'staged'].includes(status.value))
const canRetry = computed(() => ['failed', 'recovery_required'].includes(status.value))

/* ---------- 三阶段进度:预览 → 提交 → 应用 ---------- */
type StepState = 'done' | 'current' | 'pending' | 'error'
const steps = computed<{ label: string; state: StepState; spinning?: boolean }[]>(() => {
  const s = status.value
  const submitted = ['staged', 'applying', 'applied', 'failed', 'recovery_required'].includes(s)
  return [
    { label: '生成预览', state: 'done' },
    { label: '提交配置', state: s === 'draft' ? 'current' : submitted ? 'done' : 'pending' },
    {
      label: '应用到服务器',
      state: s === 'applied' ? 'done'
        : s === 'failed' || s === 'recovery_required' ? 'error'
          : submitted ? 'current' : 'pending',
      spinning: s === 'applying',
    },
  ]
})

function stepClass(state: StepState): string {
  if (state === 'done') return 'bg-ok-soft text-ok'
  if (state === 'current') return 'bg-accent-soft text-accent-strong'
  if (state === 'error') return 'bg-danger-soft text-danger'
  return 'bg-surface-muted text-ink-4'
}

/** 阶段引导:明确当前应做什么、结果语义是什么 */
const stageHint = computed(() => {
  const s = status.value
  if (s === 'draft') return '请核对下方变更预览与阻塞项,确认无误后提交。提交后期望状态即更新,但服务器尚未生效。'
  if (s === 'staged') return '已提交:期望状态已更新。还需「应用到服务器」才会写入配置;应用不会自动重启服务器。'
  if (s === 'applying') return '变更正在应用,由后台异步执行。任务结束不代表每一项都成功,请以执行结果与模组状态为准。'
  if (s === 'applied') return '变更已应用。运行中的服务器可能需要重启后,部分设置才会生效。'
  if (s === 'failed') return '应用过程中出现失败项。可排查原因后重试失败项,或取消该计划。'
  if (s === 'recovery_required') return '应用中断,需要人工恢复。请查看执行结果定位异常项。'
  if (s === 'cancelled') return '该计划已取消,不可再执行。'
  return ''
})

// 稳定态无需轮询:草稿/已提交等待人工操作,已应用/已取消为终态。
const STABLE = ['draft', 'staged', 'applied', 'cancelled']

function actionTone(act: string): Tone {
  if (act === 'delete') return 'danger'
  if (act === 'disable') return 'warning'
  if (act === 'enable') return 'success'
  return 'neutral'
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    plan.value = await apiPlanDetail(planId.value)
  } catch (e) {
    if (!silent) toast.error(e instanceof ApiRequestError ? e.message : '加载变更详情失败')
  } finally {
    if (!silent) loading.value = false
  }
}

usePolling(() => {
  if (STABLE.includes(status.value)) return
  return load(true)
}, 5000, { immediate: false })

async function runAction(fn: () => Promise<unknown>, okMsg: string) {
  if (acting.value) return // 防重复提交
  acting.value = true
  try {
    await fn()
    toast.success(okMsg)
    await load(true)
    await system.refresh()
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '操作失败')
  } finally {
    acting.value = false
  }
}

async function confirmThen(
  title: string, description: string, fn: () => Promise<unknown>, okMsg: string, danger = false,
) {
  if (system.readOnly) {
    toast.warning('当前为只读模式,无法执行该操作')
    return
  }
  const ok = await confirmDialog({ title, description, confirmText: '确认', danger })
  if (!ok) return
  await runAction(fn, okMsg)
}

const submitPlan = () => confirmThen(
  '提交计划', '提交后期望状态将立即更新(服务器尚未生效),确认提交?',
  () => apiPlanSubmit(planId.value), '计划已提交',
)
const applyPlan = () => confirmThen(
  '应用到服务器', '将对服务器配置执行变更(不会自动重启服务器),确认应用?',
  () => apiPlanApply(planId.value), '应用任务已启动,执行结果请稍后查看',
)
const cancelPlan = () => confirmThen(
  '取消计划', '取消后该计划不可再用,确认取消?',
  () => apiPlanCancel(planId.value), '计划已取消', true,
)
async function retryPlan() {
  if (system.readOnly) {
    toast.warning('当前为只读模式,无法执行该操作')
    return
  }
  await runAction(() => apiPlanRetry(planId.value), '重试任务已启动,执行结果请稍后查看')
}

onMounted(() => load())
</script>

<template>
  <div class="space-y-4">
    <div v-if="loading && !plan" class="space-y-3">
      <Skeleton class="h-28 w-full" />
      <Skeleton class="h-44 w-full" />
    </div>

    <EmptyState
      v-else-if="!plan"
      title="未找到该变更"
      description="计划可能已过期或被清理。"
    >
      <template #action>
        <Button variant="secondary" @click="router.push({ name: 'plans' })">返回变更记录</Button>
      </template>
    </EmptyState>

    <template v-else>
      <!-- 头卡:标题(payload 推导) / 状态 / ID / 三阶段进度 / 主操作 -->
      <div class="rounded-2xl border border-line bg-surface shadow-card">
        <div class="flex flex-col gap-4 p-5 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0">
            <div class="flex items-start gap-2.5">
              <Button
                size="icon-sm"
                variant="ghost"
                class="mt-0.5"
                aria-label="返回变更记录"
                @click="router.push({ name: 'plans' })"
              >
                <ArrowLeft class="size-4" aria-hidden="true" />
              </Button>
              <div class="min-w-0">
                <h1 class="truncate text-[18px] font-semibold leading-6 tracking-tight text-ink">
                  {{ planTitle(plan.payload) }}
                </h1>
                <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Badge :variant="planStatusTone(plan.status)">
                    {{ PLAN_STATUS_ZH[plan.status] || plan.status }}
                  </Badge>
                  <span class="mono text-[11.5px] text-ink-4">{{ plan.id.slice(0, 12) }}…</span>
                  <CopyButton :text="plan.id" label="计划 ID" />
                </div>
              </div>
            </div>

            <!-- 三阶段进度 -->
            <ol class="mt-3.5 flex flex-wrap items-center gap-1.5" aria-label="变更流程进度">
              <li v-for="(st, i) in steps" :key="st.label" class="flex items-center gap-1.5">
                <span v-if="i > 0" class="h-px w-5 bg-line" aria-hidden="true" />
                <span
                  class="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium"
                  :class="stepClass(st.state)"
                >
                  <Loader2 v-if="st.spinning" class="size-3 animate-spin" aria-hidden="true" />
                  <Check v-else-if="st.state === 'done'" class="size-3" aria-hidden="true" />
                  <X v-else-if="st.state === 'error'" class="size-3" aria-hidden="true" />
                  {{ st.label }}
                </span>
              </li>
            </ol>

            <div class="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-ink-3">
              <span>创建人 {{ plan.created_by || '-' }}</span>
              <span>创建于 {{ formatTime(plan.created_at) }}</span>
              <span v-if="plan.expires_at">过期于 {{ formatTime(plan.expires_at) }}</span>
              <span v-if="plan.applied_at">应用于 {{ formatTime(plan.applied_at) }}</span>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2 lg:justify-end">
            <Button
              v-if="status === 'draft'"
              variant="primary"
              :loading="acting"
              :disabled="!canSubmit || system.readOnly"
              :title="blockers.length ? '存在阻塞项,解决后才能提交' : ''"
              @click="submitPlan"
            >
              提交配置
            </Button>
            <Button
              v-if="canApply"
              variant="success"
              :loading="acting"
              :disabled="system.readOnly"
              @click="applyPlan"
            >
              <Play class="size-3.5" aria-hidden="true" />
              应用到服务器
            </Button>
            <Button
              v-if="canRetry"
              variant="secondary"
              class="text-warn hover:bg-warn-soft hover:text-warn"
              :loading="acting"
              :disabled="system.readOnly"
              @click="retryPlan"
            >
              <RotateCw class="size-3.5" aria-hidden="true" />
              重试失败项
            </Button>
            <Button
              v-if="canCancel"
              variant="danger-outline"
              :loading="acting"
              :disabled="system.readOnly"
              @click="cancelPlan"
            >
              取消计划
            </Button>
          </div>
        </div>

        <!-- 阶段引导 -->
        <p
          v-if="stageHint"
          class="border-t border-line bg-surface-muted/60 px-5 py-2.5 text-[12.5px] leading-5 text-ink-3"
        >
          {{ stageHint }}
        </p>
      </div>

      <div
        v-if="plan.error"
        class="flex items-start gap-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5"
      >
        <TriangleAlert class="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
        <p class="text-[12.5px] leading-5 text-danger">{{ plan.error }}</p>
      </div>

      <Panel title="变更摘要">
        <div class="flex flex-wrap items-center gap-2">
          <Badge v-for="[act, n] in summaryEntries" :key="act" :variant="actionTone(act)">
            {{ ACTION_ZH[act] || act }} × {{ n }}
          </Badge>
          <span v-if="!summaryEntries.length" class="small muted">无变更项</span>
          <span class="spacer" />
          <span class="small muted num">
            模式 {{ plan.diff?.mode || '-' }} · 策略 {{ plan.diff?.strategy || '-' }} ·
            基线版本 r{{ plan.base_revision }}
          </span>
        </div>
      </Panel>

      <Panel
        v-if="blockers.length"
        :title="`阻塞项(${blockers.length})`"
        description="必须先解决以下问题才能提交"
      >
        <ul class="space-y-2">
          <li
            v-for="(b, i) in blockers"
            :key="i"
            class="flex items-start gap-2 rounded-lg border border-danger/25 bg-danger-soft px-3 py-2"
          >
            <ShieldAlert class="mt-0.5 size-4 shrink-0 text-danger" aria-hidden="true" />
            <p class="text-[12.5px] leading-5 text-danger">
              <span class="mono">{{ b.workshop_id }}</span>
              ({{ ACTION_ZH[b.action] || b.action }}):{{ b.reason }}
            </p>
          </li>
        </ul>
      </Panel>

      <Panel :title="`变更预览(${perItems.length})`" :padded="false">
        <div v-if="perItems.length" class="overflow-x-auto">
          <table class="tbl">
            <thead>
              <tr>
                <th>模组</th>
                <th style="width: 96px">动作</th>
                <th style="width: 320px">变更</th>
                <th style="width: 260px">警告 / 阻塞</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in perItems" :key="`${row.workshop_id}-${row.action}`">
                <td>
                  <router-link
                    v-if="row.title"
                    class="font-medium text-accent hover:underline"
                    :to="{ name: 'mod-detail', params: { wid: row.workshop_id } }"
                  >
                    {{ row.title }}
                  </router-link>
                  <span v-else class="font-medium text-ink">-</span>
                  <p class="mono tiny muted">ID {{ row.workshop_id }}</p>
                </td>
                <td>{{ ACTION_ZH[row.action] || row.action }}</td>
                <td class="text-[12.5px]">
                  <span v-if="row.from" class="muted">
                    清单 {{ row.from.inventory_state }} / 期望 {{ row.from.desired_state }} →
                  </span>
                  <span v-if="row.to">
                    清单 {{ row.to.inventory_state ?? '-' }} / 期望 {{ row.to.desired_state }}
                  </span>
                </td>
                <td>
                  <div v-if="row.blocked" class="flex items-center gap-1.5">
                    <Badge variant="danger">已阻塞</Badge>
                    <span class="text-[12px] text-danger">{{ row.block_reason }}</span>
                  </div>
                  <div v-else-if="row.warnings.length" class="flex flex-wrap gap-1">
                    <Badge v-for="(w, i) in row.warnings" :key="i" variant="warning">{{ w }}</Badge>
                  </div>
                  <span v-else class="muted">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState v-else title="没有预览项" />
      </Panel>

      <Panel v-if="items.length" :title="`执行结果(${items.length})`" :padded="false">
        <div class="border-b border-line px-5 py-2.5">
          <p class="text-[12px] text-ink-4">
            执行结果逐项记录,失败项不影响其他条目;「完成」表示该条目已按预期写入。
          </p>
        </div>
        <div class="overflow-x-auto">
          <table class="tbl">
            <thead>
              <tr>
                <th style="width: 150px">Workshop ID</th>
                <th style="width: 96px">动作</th>
                <th style="width: 96px">状态</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in items" :key="row.id">
                <td>
                  <router-link
                    class="mono text-[12.5px] text-accent hover:underline"
                    :to="{ name: 'mod-detail', params: { wid: row.workshop_id } }"
                  >
                    {{ row.workshop_id }}
                  </router-link>
                </td>
                <td>{{ ACTION_ZH[row.action] || row.action }}</td>
                <td>
                  <Badge :variant="itemStatusTone(row.status)">
                    {{ ITEM_STATUS_ZH[row.status] || row.status }}
                  </Badge>
                </td>
                <td class="text-[12.5px] text-danger">{{ row.error || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>
    </template>
  </div>
</template>
