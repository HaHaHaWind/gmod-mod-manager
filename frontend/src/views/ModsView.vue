<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, RefreshCw, ScanLine, Search, X } from 'lucide-vue-next'
import { apiCreatePlan, apiModList, apiRefreshMeta, apiStartScan } from '@/api'
import type { ModListQuery, PlanItemInput } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { ModView } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { toast } from '@/composables/useToast'
import { ACTION_ZH } from '@/utils/format'
import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import Input from '@/components/ui/Input.vue'
import Pagination from '@/components/ui/Pagination.vue'
import Select from '@/components/ui/Select.vue'
import ModGrid from '@/components/biz/ModGrid.vue'

type Action = 'enable' | 'disable' | 'delete'

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
const selected = ref<string[]>([])
const acting = ref(false)

const inventoryOptions = [
  { value: '', label: '清单:全部' },
  { value: 'present', label: '清单:正常' },
  { value: 'missing', label: '清单:缺失' },
  { value: 'invalid', label: '清单:异常' },
  { value: 'trashed', label: '清单:回收站' },
]
const desiredOptions = [
  { value: '', label: '期望:全部' },
  { value: 'enabled', label: '期望启用' },
  { value: 'disabled', label: '期望禁用' },
  { value: 'unmanaged', label: '期望:未接管' },
]
const applyOptions = [
  { value: '', label: '应用:全部' },
  { value: 'synced', label: '已同步(待重启)' },
  { value: 'pending', label: '待应用' },
  { value: 'failed', label: '应用失败' },
  { value: 'conflict', label: '存在冲突' },
  { value: 'unmanaged', label: '未接管' },
]
const actionOptions = Object.entries(ACTION_ZH).map(([value, label]) => ({ value, label }))

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
    const visible = new Set(resp.items.map((m) => m.workshop_id))
    selected.value = selected.value.filter((id) => visible.has(id))
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '加载 Mod 列表失败')
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

function requireWritable(): boolean {
  if (system.readOnly) {
    toast.warning('当前为只读模式,无法执行该操作')
    return false
  }
  return true
}

const scanning = ref(false)
async function startScan() {
  if (!requireWritable()) return
  scanning.value = true
  try {
    await apiStartScan(false)
    toast.success('扫描任务已创建')
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建扫描任务失败')
  } finally {
    scanning.value = false
  }
}

const refreshingMeta = ref(false)
async function refreshMeta() {
  if (!requireWritable()) return
  if (!selected.value.length) { toast.warning('请先勾选要刷新的 Mod'); return }
  refreshingMeta.value = true
  try {
    const resp = await apiRefreshMeta(selected.value)
    toast.success(`元数据刷新任务已创建,共 ${resp.ids.length} 项`)
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建刷新任务失败')
  } finally {
    refreshingMeta.value = false
  }
}

async function refreshOne(wid: string) {
  if (!requireWritable()) return
  try {
    await apiRefreshMeta([wid])
    toast.success('元数据刷新任务已创建')
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建刷新任务失败')
  }
}

async function quickPlan(wid: string, action: Action) {
  if (!requireWritable()) return
  acting.value = true
  try {
    const plan = await apiCreatePlan([{ action, workshop_id: wid }])
    toast.success(`已创建单项${ACTION_ZH[action]}计划,请确认预览`)
    router.push({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建计划失败')
  } finally {
    acting.value = false
  }
}

function toggle(wid: string) {
  selected.value = selected.value.includes(wid)
    ? selected.value.filter((id) => id !== wid)
    : [...selected.value, wid]
}

const selectedMods = computed(() => rows.value.filter((m) => selected.value.includes(m.workshop_id)))

const planOpen = ref(false)
const planSubmitting = ref(false)
const planActions = ref<Record<string, string>>({})

function defaultAction(m: ModView): Action {
  return m.desired_state === 'enabled' ? 'disable' : 'enable'
}

function openPlan() {
  if (!selected.value.length) { toast.warning('请先勾选要变更的 Mod'); return }
  const map: Record<string, string> = {}
  for (const m of selectedMods.value) map[m.workshop_id] = defaultAction(m)
  planActions.value = map
  planOpen.value = true
}

async function submitPlan() {
  const items: PlanItemInput[] = selectedMods.value.map((m) => ({
    action: planActions.value[m.workshop_id] as Action,
    workshop_id: m.workshop_id,
  }))
  planSubmitting.value = true
  try {
    const plan = await apiCreatePlan(items)
    planOpen.value = false
    toast.success('变更计划已创建,请确认预览后提交')
    router.push({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建计划失败')
  } finally {
    planSubmitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="toolbar">
      <div class="relative w-full sm:w-[280px]">
        <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-4" aria-hidden="true" />
        <Input v-model="q" class="pl-9" placeholder="搜索标题 / 文件夹名 / Workshop ID" />
      </div>
      <Select v-model="inventoryState" :options="inventoryOptions" class="w-[136px]" aria-label="清单状态筛选" />
      <Select v-model="desiredState" :options="desiredOptions" class="w-[136px]" aria-label="期望状态筛选" />
      <Select v-model="applyState" :options="applyOptions" class="w-[164px]" aria-label="应用状态筛选" />
      <span class="spacer" />
      <Button :loading="scanning" :disabled="system.readOnly" @click="startScan">
        <ScanLine class="size-3.5" aria-hidden="true" />
        扫描缓存
      </Button>
      <Button :loading="refreshingMeta" :disabled="system.readOnly || !selected.length" @click="refreshMeta">
        <RefreshCw class="size-3.5" aria-hidden="true" />
        刷新元数据
      </Button>
      <Button variant="primary" :disabled="system.readOnly || !selected.length" @click="openPlan">
        <Plus class="size-3.5" aria-hidden="true" />
        创建变更计划({{ selected.length }})
      </Button>
    </div>

    <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <span class="small muted num">共 {{ total }} 个 Mod</span>
      <template v-if="selected.length">
        <span class="small muted num">已选 {{ selected.length }} 项</span>
        <Button size="sm" variant="ghost" @click="selected = []">
          <X class="size-3" aria-hidden="true" />
          清空选择
        </Button>
      </template>
    </div>

    <ModGrid
      :mods="rows"
      :loading="loading"
      :read-only="system.readOnly"
      :selected="selected"
      @open="(wid) => router.push({ name: 'mod-detail', params: { wid } })"
      @toggle="toggle"
      @enable="(wid) => quickPlan(wid, 'enable')"
      @disable="(wid) => quickPlan(wid, 'disable')"
      @remove="(wid) => quickPlan(wid, 'delete')"
      @refresh="refreshOne"
    />

    <div v-if="total > 0" class="flex justify-end pt-1">
      <Pagination v-model:page="page" v-model:page-size="pageSize" :total="total" />
    </div>

    <Dialog
      v-model:open="planOpen"
      title="创建变更计划"
      description="先预览,后提交;应用前可随时取消。计划 30 分钟未提交将过期。"
      width-class="max-w-2xl"
    >
      <div class="space-y-2">
        <div
          v-for="m in selectedMods"
          :key="m.workshop_id"
          class="flex items-center gap-3 rounded-lg border border-line px-3 py-2"
        >
          <div class="min-w-0 flex-1">
            <p class="truncate text-[13px] font-medium text-ink">{{ m.title || m.folder_name }}</p>
            <p class="mono tiny muted">
              ID {{ m.workshop_id }} · 当前期望 {{ m.desired_zh || m.desired_state }}
            </p>
          </div>
          <Select v-model="planActions[m.workshop_id]" :options="actionOptions" class="w-[112px]" />
        </div>
      </div>
      <template #footer>
        <Button variant="secondary" @click="planOpen = false">取消</Button>
        <Button variant="primary" :loading="planSubmitting" @click="submitPlan">生成预览</Button>
      </template>
    </Dialog>
  </div>
</template>