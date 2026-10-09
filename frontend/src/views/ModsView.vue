<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronDown, Filter, RefreshCw, ScanLine, Search, SlidersHorizontal, X } from 'lucide-vue-next'
import {
  DropdownMenuContent, DropdownMenuItem, DropdownMenuPortal, DropdownMenuRoot, DropdownMenuTrigger,
  PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger,
} from 'reka-ui'
import { apiCreatePlan, apiModCategories, apiModList, apiRefreshMeta, apiStartScan } from '@/api'
import type { ModListQuery, PlanItemInput } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { ModView } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { toast } from '@/composables/useToast'
import { ACTION_ZH } from '@/utils/format'
import Button from '@/components/ui/Button.vue'
import Checkbox from '@/components/ui/Checkbox.vue'
import Input from '@/components/ui/Input.vue'
import Pagination from '@/components/ui/Pagination.vue'
import Select from '@/components/ui/Select.vue'
import ModGrid from '@/components/biz/ModGrid.vue'

type Action = 'enable' | 'disable' | 'delete'

const router = useRouter()
const route = useRoute()
const system = useSystemStore()

const loading = ref(false)
const rows = ref<ModView[]>([])
const total = ref(0)
const page = ref(1)
const PAGE_SIZE_KEY = 'gmod_mm_page_size'
const pageSize = ref(Number(localStorage.getItem(PAGE_SIZE_KEY)) || 20)
watch(pageSize, (v) => localStorage.setItem(PAGE_SIZE_KEY, String(v)))

const q = ref('')
const inventoryState = ref('')
const desiredState = ref('')
const applyState = ref('')
const category = ref('')
const categoryOptions = ref<{ value: string; label: string }[]>([{ value: '', label: '全部类型' }])
const selected = ref<string[]>([])

/* ---------- 筛选选项 ---------- */
const inventoryOptions = [
  { value: '', label: '文件状态:全部' },
  { value: 'present', label: '文件正常' },
  { value: 'missing', label: '文件缺失' },
  { value: 'invalid', label: '文件异常' },
  { value: 'trashed', label: '已在回收站' },
]
const desiredOptions = [
  { value: '', label: '配置状态:全部' },
  { value: 'enabled', label: '配置为启用' },
  { value: 'disabled', label: '配置为禁用' },
  { value: 'unmanaged', label: '未纳管' },
]
const applyOptions = [
  { value: '', label: '应用状态:全部' },
  { value: 'synced', label: '已同步(待重启)' },
  { value: 'pending', label: '等待应用' },
  { value: 'applying', label: '正在应用' },
  { value: 'failed', label: '应用失败' },
  { value: 'conflict', label: '存在冲突' },
  { value: 'unmanaged', label: '未纳管' },
]

/* ---------- 数据加载:300ms 防抖 + 过期响应丢弃 ---------- */
let reqSeq = 0
async function load() {
  const seq = ++reqSeq
  loading.value = true
  try {
    const query: ModListQuery = {
      q: q.value || undefined,
      inventory_state: inventoryState.value || undefined,
      desired_state: desiredState.value || undefined,
      apply_state: applyState.value || undefined,
      category: category.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    }
    const resp = await apiModList(query)
    if (seq !== reqSeq) return // 已有更新的请求,丢弃过期响应
    rows.value = resp.items
    total.value = resp.total
    // "全选本页"语义:选择范围始终与当前页可见项一致
    const visible = new Set(resp.items.map((m) => m.workshop_id))
    selected.value = selected.value.filter((id) => visible.has(id))
  } catch (e) {
    if (seq !== reqSeq) return
    toast.error(e instanceof ApiRequestError ? e.message : '加载模组列表失败')
  } finally {
    if (seq === reqSeq) loading.value = false
  }
}

async function loadCategories() {
  const resp = await apiModCategories().catch(() => null)
  if (!resp) return
  categoryOptions.value = [{ value: '', label: '全部类型' },
    ...resp.items.map((c) => ({ value: c.value, label: `${c.label} (${c.count})` }))]
}

let searchTimer: number | undefined
watch(q, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => { page.value = 1; load() }, 300)
})
watch([inventoryState, desiredState, applyState, category], () => { page.value = 1; load() })
watch(pageSize, () => { page.value = 1; load() })
watch(page, load)

/* ---------- URL 上下文:搜索/筛选/页码写回 query,从详情页返回时完整恢复 ---------- */
function currentQuery(): Record<string, string> {
  const query: Record<string, string> = {}
  if (q.value) query.q = q.value
  if (category.value) query.cat = category.value
  if (inventoryState.value) query.inv = inventoryState.value
  if (desiredState.value) query.des = desiredState.value
  if (applyState.value) query.app = applyState.value
  if (page.value > 1) query.page = String(page.value)
  return query
}

let syncTimer: number | undefined
function syncQuery() {
  window.clearTimeout(syncTimer)
  syncTimer = window.setTimeout(() => {
    router.replace({ query: currentQuery() }).catch(() => {})
  }, 200)
}
watch([q, inventoryState, desiredState, applyState, category, page], syncQuery)

function restoreFromQuery() {
  const query = route.query
  if (typeof query.q === 'string') q.value = query.q
  if (typeof query.cat === 'string') category.value = query.cat
  if (typeof query.inv === 'string') inventoryState.value = query.inv
  if (typeof query.des === 'string') desiredState.value = query.des
  if (typeof query.app === 'string') applyState.value = query.app
  const p = Number(query.page)
  if (Number.isInteger(p) && p >= 1) page.value = p
}

/* ---------- 滚动恢复:进入详情/变更页前记录位置,数据返回后恢复一次 ---------- */
const SCROLL_KEY = 'gmod_mm_scroll'
let pendingScroll = Number(sessionStorage.getItem(SCROLL_KEY)) || 0

function leaveWithScroll(location: { name: string; params?: Record<string, string> }) {
  sessionStorage.setItem(SCROLL_KEY, String(window.scrollY))
  router.push(location)
}

async function restoreScrollOnce() {
  if (pendingScroll <= 0) return
  const target = pendingScroll
  pendingScroll = 0
  sessionStorage.removeItem(SCROLL_KEY)
  await nextTick()
  window.scrollTo({ top: target })
}
watch(rows, () => { restoreScrollOnce() })

/* ---------- 已生效筛选条件 chips ---------- */
type Chip = { key: 'category' | 'inventory' | 'desired' | 'apply'; label: string }
const activeFilters = computed<Chip[]>(() => {
  const chips: Chip[] = []
  const cat = categoryOptions.value.find((o) => o.value === category.value)
  if (category.value && cat) {
    chips.push({ key: 'category', label: `类型:${cat.label.replace(/\s*\(\d+\)$/, '')}` })
  }
  const inv = inventoryOptions.find((o) => o.value === inventoryState.value)
  if (inventoryState.value && inv) chips.push({ key: 'inventory', label: inv.label })
  const des = desiredOptions.find((o) => o.value === desiredState.value)
  if (desiredState.value && des) chips.push({ key: 'desired', label: des.label })
  const app = applyOptions.find((o) => o.value === applyState.value)
  if (applyState.value && app) chips.push({ key: 'apply', label: app.label })
  return chips
})
const extraFilterCount = computed(
  () => (inventoryState.value ? 1 : 0) + (desiredState.value ? 1 : 0) + (applyState.value ? 1 : 0),
)
const hasFilters = computed(() => activeFilters.value.length > 0)

function removeFilter(key: Chip['key']) {
  if (key === 'category') category.value = ''
  else if (key === 'inventory') inventoryState.value = ''
  else if (key === 'desired') desiredState.value = ''
  else applyState.value = ''
}
function clearFilters() {
  category.value = ''
  inventoryState.value = ''
  desiredState.value = ''
  applyState.value = ''
}

/* ---------- 扫描:快速为主操作,全量收次级菜单 ---------- */
function requireWritable(): boolean {
  if (system.readOnly) {
    toast.warning('当前为只读模式,无法执行该操作')
    return false
  }
  return true
}

const scanning = ref(false)
async function startScan(deep = false) {
  if (!requireWritable()) return
  scanning.value = true
  try {
    await apiStartScan(deep)
    toast.success(deep ? '全量扫描任务已创建,耗时较长' : '扫描任务已创建')
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建扫描任务失败')
  } finally {
    scanning.value = false
  }
}

/* ---------- 元数据更新 ---------- */
const refreshingMeta = ref(false)
async function refreshMeta() {
  if (!requireWritable()) return
  if (!selected.value.length) { toast.warning('请先勾选要更新的模组'); return }
  refreshingMeta.value = true
  try {
    const resp = await apiRefreshMeta(selected.value)
    toast.success(`更新任务已创建,共 ${resp.ids.length} 项`)
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建更新任务失败')
  } finally {
    refreshingMeta.value = false
  }
}
async function refreshOne(wid: string) {
  if (!requireWritable()) return
  try {
    await apiRefreshMeta([wid])
    toast.success('更新任务已创建')
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建更新任务失败')
  }
}

/* ---------- 选择 ---------- */
function toggle(wid: string) {
  selected.value = selected.value.includes(wid)
    ? selected.value.filter((id) => id !== wid)
    : [...selected.value, wid]
}
const pageIds = computed(() => rows.value.map((m) => m.workshop_id))
const allSelected = computed(
  () => pageIds.value.length > 0 && pageIds.value.every((id) => selected.value.includes(id)),
)
const partialSelected = computed(() => !allSelected.value && selected.value.length > 0)
const selectAll = computed({
  get: () => allSelected.value,
  set: (v: boolean) => { selected.value = v ? [...pageIds.value] : [] },
})

/* ---------- 批量操作:直接生成预览,提交前可随时取消 ---------- */
const byId = computed(() => new Map(rows.value.map((m) => [m.workshop_id, m])))

function idsForAction(action: Action): string[] {
  return selected.value.filter((id) => {
    const m = byId.value.get(id)
    if (!m) return false
    if (action === 'enable') return m.desired_state !== 'enabled'
    if (action === 'disable') return m.desired_state !== 'disabled'
    return m.inventory_state !== 'trashed'
  })
}

const bulkActing = ref(false)
async function bulkPlan(action: Action) {
  if (!requireWritable()) return
  const ids = idsForAction(action)
  if (!ids.length) {
    toast.warning(action === 'delete'
      ? '选中项中没有可移除的模组'
      : '选中项均已处于该配置,无需变更')
    return
  }
  bulkActing.value = true
  try {
    const items: PlanItemInput[] = ids.map((id) => ({ action, workshop_id: id }))
    const plan = await apiCreatePlan(items)
    toast.success('已生成变更预览,请确认后提交')
    leaveWithScroll({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建变更预览失败')
  } finally {
    bulkActing.value = false
  }
}

async function quickPlan(wid: string, action: Action) {
  if (!requireWritable()) return
  try {
    const plan = await apiCreatePlan([{ action, workshop_id: wid }])
    toast.success(`已生成${ACTION_ZH[action]}预览,请确认后提交`)
    leaveWithScroll({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建变更预览失败')
  }
}

onMounted(() => {
  restoreFromQuery()
  load(); loadCategories()
})
</script>

<template>
  <div class="space-y-4" :class="selected.length ? 'pb-24' : ''">
    <!-- 页面标题区 -->
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
      <h2 class="text-2xl font-semibold tracking-tight text-ink">模组库</h2>
      <span class="small num text-ink-3">共 {{ total }} 个模组</span>
      <span class="spacer" />
      <div class="flex items-center">
        <Button
          variant="primary"
          class="rounded-r-none"
          :loading="scanning"
          :disabled="system.readOnly"
          @click="startScan(false)"
        >
          <ScanLine class="size-4" aria-hidden="true" />
          扫描模组
        </Button>
        <DropdownMenuRoot>
          <DropdownMenuTrigger as-child>
            <Button
              variant="primary"
              class="rounded-l-none border-l border-white/30 px-1.5"
              :disabled="system.readOnly"
              aria-label="更多扫描选项"
            >
              <ChevronDown class="size-3.5" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent
              align="end"
              :side-offset="6"
              class="z-50 min-w-44 data-[state=open]:animate-ui-in data-[state=closed]:animate-ui-out rounded-xl border border-line bg-surface p-1 shadow-pop"
            >
              <DropdownMenuItem
                class="flex cursor-pointer select-none flex-col items-start gap-0.5 rounded-md px-2.5 py-2 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-surface-muted"
                @select="startScan(true)"
              >
                <span class="font-medium">全量扫描</span>
                <span class="text-[12px] text-ink-4">重新校验全部文件,耗时较长</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenuRoot>
      </div>
    </div>

    <!-- 搜索 + 筛选 -->
    <div class="toolbar">
      <div class="relative min-w-[240px] flex-1 sm:max-w-[520px]">
        <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-4" aria-hidden="true" />
        <Input v-model="q" class="pl-9" placeholder="搜索模组名称、作者或 Workshop ID" aria-label="搜索模组" />
      </div>
      <Select v-model="category" :options="categoryOptions" class="w-[168px]" aria-label="类型筛选" />
      <PopoverRoot>
        <PopoverTrigger as-child>
          <Button variant="secondary" class="gap-1.5">
            <SlidersHorizontal class="size-3.5" aria-hidden="true" />
            更多筛选
            <span
              v-if="extraFilterCount"
              class="inline-flex size-[18px] items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-white"
            >
              {{ extraFilterCount }}
            </span>
          </Button>
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent
            align="end"
            :side-offset="6"
            class="z-50 w-64 data-[state=open]:animate-ui-in data-[state=closed]:animate-ui-out space-y-2.5 rounded-xl border border-line bg-surface p-3 shadow-pop"
          >
            <p class="text-[13px] font-medium text-ink">状态筛选</p>
            <Select v-model="inventoryState" :options="inventoryOptions" aria-label="文件状态筛选" />
            <Select v-model="desiredState" :options="desiredOptions" aria-label="配置状态筛选" />
            <Select v-model="applyState" :options="applyOptions" aria-label="应用状态筛选" />
            <Button variant="secondary" size="sm" class="w-full" @click="clearFilters">
              清除状态筛选
            </Button>
          </PopoverContent>
        </PopoverPortal>
      </PopoverRoot>
    </div>

    <!-- 已生效条件 -->
    <div v-if="hasFilters" class="flex flex-wrap items-center gap-1.5">
      <Filter class="size-3.5 text-ink-4" aria-hidden="true" />
      <span
        v-for="f in activeFilters"
        :key="f.key"
        class="inline-flex items-center gap-1 rounded-full border border-accent-line bg-accent-soft py-0.5 pl-2.5 pr-1.5 text-[12px] font-medium text-accent-strong"
      >
        {{ f.label }}
        <button
          type="button"
          class="rounded-full p-0.5 transition-colors hover:bg-accent/15"
          :aria-label="`移除筛选:${f.label}`"
          @click="removeFilter(f.key)"
        >
          <X class="size-3" aria-hidden="true" />
        </button>
      </span>
      <Button size="sm" variant="ghost" class="h-6 text-ink-3" @click="clearFilters">
        清除筛选
      </Button>
    </div>

    <!-- 全选本页 -->
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <Checkbox
        v-model="selectAll"
        :indeterminate="partialSelected"
        :disabled="!rows.length"
        label="全选本页"
      />
      <span v-if="!selected.length" class="small num text-ink-3">共 {{ total }} 项结果</span>
    </div>

    <ModGrid
      :mods="rows"
      :loading="loading"
      :read-only="system.readOnly"
      :selected="selected"
      @open="(wid) => leaveWithScroll({ name: 'mod-detail', params: { wid } })"
      @toggle="toggle"
      @enable="(wid) => quickPlan(wid, 'enable')"
      @disable="(wid) => quickPlan(wid, 'disable')"
      @remove="(wid) => quickPlan(wid, 'delete')"
      @refresh="refreshOne"
    />

    <div v-if="total > 0" class="flex justify-end pt-1">
      <Pagination v-model:page="page" v-model:page-size="pageSize" :total="total" />
    </div>

    <!-- 底部批量操作栏 -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="translate-y-2 opacity-0"
      leave-active-class="transition duration-100 ease-in"
      leave-to-class="translate-y-2 opacity-0"
    >
      <div
        v-if="selected.length"
        class="fixed inset-x-0 bottom-5 z-30 flex justify-center px-4 lg:pl-[224px]"
      >
        <div
          class="flex flex-wrap items-center gap-1 rounded-xl border border-line bg-surface/95 py-2 pl-4 pr-2 shadow-pop backdrop-blur"
          role="toolbar"
          aria-label="批量操作"
        >
          <span class="num small mr-1 font-medium text-ink">已选 {{ selected.length }} 项</span>
          <span class="mx-1 h-5 w-px bg-line" aria-hidden="true" />
          <Button
            size="sm"
            variant="secondary"
            :loading="bulkActing"
            :disabled="system.readOnly"
            @click="bulkPlan('enable')"
          >
            启用
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :loading="bulkActing"
            :disabled="system.readOnly"
            @click="bulkPlan('disable')"
          >
            禁用
          </Button>
          <Button
            size="sm"
            variant="secondary"
            :loading="bulkActing"
            :disabled="system.readOnly"
            @click="bulkPlan('delete')"
          >
            移至回收站
          </Button>
          <Button
            size="sm"
            variant="ghost"
            :loading="refreshingMeta"
            :disabled="system.readOnly"
            @click="refreshMeta"
          >
            <RefreshCw class="size-3.5" aria-hidden="true" />
            更新信息
          </Button>
          <span class="mx-1 h-5 w-px bg-line" aria-hidden="true" />
          <Button size="sm" variant="ghost" class="text-ink-3" @click="selected = []">
            <X class="size-3.5" aria-hidden="true" />
            取消选择
          </Button>
        </div>
      </div>
    </Transition>
  </div>
</template>
