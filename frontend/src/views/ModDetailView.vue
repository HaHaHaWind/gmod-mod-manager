<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, ExternalLink, FolderOpen, ImageOff, Info, RefreshCw, Trash2, Wrench,
} from 'lucide-vue-next'
import { apiCreatePlan, apiModDetail, apiRefreshMeta, localPreview } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { ModDetail } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { toast } from '@/composables/useToast'
import {
  ACTION_ZH, LOAD_SOURCE_ZH, applyTone, desiredTone, formatBytes, formatTime,
  inventoryTone, primaryModStatus,
} from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import CopyButton from '@/components/ui/CopyButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import SpecGrid, { type SpecItem } from '@/components/ui/SpecGrid.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

type Action = 'enable' | 'disable' | 'delete'
type TabKey = 'about' | 'files' | 'tech'

const route = useRoute()
const router = useRouter()
const system = useSystemStore()

const wid = computed(() => String(route.params.wid || ''))
const mod = ref<ModDetail | null>(null)
const loading = ref(false)
const acting = ref(false)
const failed = ref(false)

const title = computed(() => {
  const m = mod.value
  if (!m) return ''
  return m.title || m.folder_name || m.workshop_id
})
const workshopUrl = computed(
  () => `https://steamcommunity.com/sharedfiles/filedetails/?id=${wid.value}`,
)
const hasPreview = computed(() => !!mod.value?.preview_url && !failed.value)

/** 单一主状态:由五维技术状态推导,hint 作为 Tooltip 补充说明 */
const status = computed(() =>
  mod.value
    ? primaryModStatus(mod.value)
    : { label: '加载中', tone: 'neutral' as const },
)

/* ---------- 页签:状态写回 query,刷新/返回后保持 ---------- */
const tabDefs: { key: TabKey; label: string; icon: Component }[] = [
  { key: 'about', label: '简介', icon: Info },
  { key: 'files', label: '文件清单', icon: FolderOpen },
  { key: 'tech', label: '技术详情', icon: Wrench },
]
function normalizeTab(v: unknown): TabKey {
  return tabDefs.some((t) => t.key === v) ? (v as TabKey) : 'about'
}
const activeTab = ref<TabKey>(normalizeTab(route.query.tab))
watch(activeTab, (t) => {
  router.replace({ query: { ...route.query, tab: t === 'about' ? undefined : t } }).catch(() => {})
})

/* ---------- 返回:优先回退历史,直接打开 URL 时回模组库 ---------- */
function goBack() {
  if (window.history.state?.back) router.back()
  else router.push({ name: 'mods' })
}

async function load() {
  loading.value = true
  try {
    mod.value = await apiModDetail(wid.value)
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '加载模组详情失败')
  } finally {
    loading.value = false
  }
}

function requireWritable(): boolean {
  if (system.readOnly) {
    toast.warning('当前为只读模式,无法执行该操作')
    return false
  }
  return true
}

async function refreshMeta() {
  if (!requireWritable()) return
  acting.value = true
  try {
    await apiRefreshMeta([wid.value])
    toast.success('更新任务已创建')
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建更新任务失败')
  } finally {
    acting.value = false
  }
}

/* ---------- 单项变更:统一生成预览,提交前可随时取消 ---------- */
const mainAction = computed<Action>(() =>
  mod.value?.desired_state === 'enabled' ? 'disable' : 'enable',
)
const changeLocked = computed(() => mod.value?.apply_state === 'applying')

async function quickPlan(action: Action) {
  if (!requireWritable()) return
  acting.value = true
  try {
    const plan = await apiCreatePlan([{ action, workshop_id: wid.value }])
    toast.success(`已生成${ACTION_ZH[action]}预览,请确认后提交`)
    router.push({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建变更预览失败')
  } finally {
    acting.value = false
  }
}

/* ---------- 技术详情:五维状态 ---------- */
const stateItems = computed<SpecItem[]>(() => {
  const m = mod.value
  if (!m) return []
  const invReason = typeof m.inventory_detail?.reason === 'string' ? m.inventory_detail.reason : ''
  const invWarning = typeof m.inventory_detail?.warning === 'string' ? m.inventory_detail.warning : ''
  return [
    {
      label: '清单',
      badge: m.inventory_zh || m.inventory_state,
      tone: inventoryTone(m.inventory_state),
      note: m.inventory_state === 'invalid' && invReason ? invReason : (invWarning || undefined),
    },
    { label: '期望', badge: m.desired_zh || m.desired_state, tone: desiredTone(m.desired_state) },
    { label: '应用', badge: m.apply_zh || m.apply_state, tone: applyTone(m.apply_state) },
    { label: '运行时', value: m.runtime_zh || m.runtime_state },
    { label: '需重启', badge: m.requires_restart ? '是' : '否', tone: m.requires_restart ? 'warning' : 'neutral' },
  ]
})

const loadItems = computed<SpecItem[]>(() => {
  const m = mod.value
  if (!m) return []
  return [
    {
      label: '加载来源',
      value: LOAD_SOURCE_ZH[m.load_source] || m.load_source,
      note: m.load_sources.length > 1 ? `共 ${m.load_sources.length} 处:${m.load_sources.join('、')}` : undefined,
    },
    { label: '缓存大小', value: formatBytes(m.size_bytes), note: `${m.file_count} 个文件` },
    { label: '最近扫描', value: formatTime(m.last_scan_at) },
    { label: 'Workshop 更新', value: formatTime(m.time_updated) },
    { label: '远端大小', value: m.remote_file_size == null ? '未知' : formatBytes(m.remote_file_size) },
  ]
})

const deployItems = computed<SpecItem[]>(() => {
  const m = mod.value
  if (!m) return []
  return [
    { label: '部署版本', value: `v${m.deploy?.version ?? '-'}` },
    { label: '部署时间', value: formatTime(m.deploy?.deployed_at) },
    { label: '部署路径', value: m.deploy?.path || '-', mono: true },
    {
      label: '部署大小',
      value: m.deploy?.size ? formatBytes(m.deploy.size) : '-',
      badge: m.deploy?.source_changed ? '缓存已有更新' : undefined,
      tone: 'warning',
    },
  ]
})

const metaItems = computed<SpecItem[]>(() => {
  const m = mod.value
  if (!m) return []
  return [
    { label: '类型', value: m.category_zh || m.category || '未分类' },
    {
      label: '抓取状态',
      value: m.metadata_zh || m.metadata_state || '未抓取',
      note: m.metadata_error || undefined,
    },
    { label: '抓取时间', value: formatTime(m.metadata_fetched_at) },
    { label: '来源', value: m.metadata_source || '-' },
    { label: '发布时间', value: formatTime(m.time_published) },
  ]
})

const filesTotalSize = computed(
  () => mod.value?.files.reduce((s, f) => s + f.size, 0) ?? 0,
)

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <!-- 加载骨架 -->
    <div v-if="loading && !mod" class="space-y-4">
      <Skeleton class="h-9 w-40 rounded-xl" />
      <div class="rounded-2xl border border-line bg-surface p-5 shadow-card">
        <div class="flex flex-col gap-5 lg:flex-row">
          <Skeleton class="aspect-video w-full rounded-lg lg:w-[320px]" />
          <div class="flex-1 space-y-2.5">
            <Skeleton class="h-6 w-2/3" />
            <Skeleton class="h-4 w-1/3" />
            <Skeleton class="h-4 w-1/2" />
            <Skeleton class="h-9 w-72" />
          </div>
        </div>
      </div>
      <Skeleton class="h-48 w-full rounded-xl" />
    </div>

    <EmptyState
      v-else-if="!mod"
      title="未找到该模组"
      description="该条目可能已被移除,或 Workshop ID 不正确。"
    >
      <template #action>
        <Button variant="secondary" size="sm" @click="goBack">
          <ArrowLeft class="size-3.5" aria-hidden="true" />
          返回模组库
        </Button>
      </template>
    </EmptyState>

    <template v-else>
      <!-- 返回入口 -->
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-lg px-1.5 py-1 text-[13px] font-medium text-ink-3 transition-colors duration-150 hover:bg-surface-muted hover:text-ink"
        @click="goBack"
      >
        <ArrowLeft class="size-4" aria-hidden="true" />
        返回模组库
      </button>

      <!-- 头卡:封面 / 名称 / 作者 / 分类 / 主状态 / 操作 -->
      <section class="rounded-2xl border border-line bg-surface shadow-card">
        <div class="flex flex-col gap-5 p-5 lg:flex-row">
          <div class="w-full shrink-0 lg:w-[320px]">
            <div class="aspect-video overflow-hidden rounded-xl bg-surface-muted">
              <img
                v-if="hasPreview"
                :src="localPreview(mod.workshop_id)"
                :alt="title"
                class="size-full object-cover"
                @error="failed = true"
              >
              <div v-else class="flex size-full flex-col items-center justify-center gap-1.5 text-ink-4">
                <ImageOff class="size-5" aria-hidden="true" />
                <span class="text-[12px]">无预览图</span>
              </div>
            </div>
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <Tooltip v-if="status.hint" :content="status.hint">
                <Badge :variant="status.tone">{{ status.label }}</Badge>
              </Tooltip>
              <Badge v-else :variant="status.tone">{{ status.label }}</Badge>
              <Badge v-if="mod.category_zh || mod.category" variant="outline">
                {{ mod.category_zh || mod.category }}
              </Badge>
              <Badge v-if="mod.protected" variant="danger">受保护</Badge>
            </div>

            <h1 class="mt-2 text-[22px] font-semibold leading-7 tracking-tight text-ink">{{ title }}</h1>

            <p class="small muted mt-1">
              作者:{{ mod.author_name || '未知' }}
              <template v-if="mod.author_steamid">({{ mod.author_steamid }})</template>
            </p>

            <div class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[12px] text-ink-4">
              <span class="mono">{{ mod.workshop_id }}</span>
              <CopyButton :text="mod.workshop_id" label="Workshop ID" />
              <a
                :href="workshopUrl"
                target="_blank"
                rel="noopener"
                class="inline-flex items-center gap-1 font-medium text-accent transition-colors hover:text-accent-strong hover:underline"
              >
                打开创意工坊页面
                <ExternalLink class="size-3" aria-hidden="true" />
              </a>
            </div>

            <div v-if="mod.tags.length" class="mt-2.5 flex flex-wrap gap-1.5">
              <Badge v-for="t in mod.tags" :key="t" variant="outline">{{ t }}</Badge>
            </div>

            <p v-if="mod.protected" class="mt-2 text-[12.5px] text-warn">
              受保护:{{ mod.protected_reason }}
            </p>

            <div class="mt-4 flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                :loading="acting"
                :disabled="system.readOnly || changeLocked"
                @click="quickPlan(mainAction)"
              >
                {{ mainAction === 'enable' ? '配置为启用' : '配置为禁用' }}
              </Button>
              <Button
                variant="secondary"
                :loading="acting"
                :disabled="system.readOnly"
                @click="refreshMeta"
              >
                <RefreshCw class="size-3.5" aria-hidden="true" />
                更新模组信息
              </Button>
              <a
                :href="workshopUrl"
                target="_blank"
                rel="noopener"
                class="inline-flex h-9 select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-xl border border-line bg-surface px-3.5 text-[13px] font-medium text-ink-2 shadow-[0_1px_2px_rgb(13_21_34/0.04)] transition-all duration-150 hover:border-line-strong hover:bg-surface-muted hover:text-ink"
              >
                在创意工坊打开
                <ExternalLink class="size-3.5" aria-hidden="true" />
              </a>
              <Button
                variant="danger-outline"
                :loading="acting"
                :disabled="system.readOnly || mod.protected"
                :title="mod.protected ? mod.protected_reason : ''"
                @click="quickPlan('delete')"
              >
                <Trash2 class="size-3.5" aria-hidden="true" />
                移至回收站
              </Button>
            </div>
          </div>
        </div>
      </section>

      <!-- 页签:简介 / 文件清单 / 技术详情 -->
      <section class="overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
        <div role="tablist" aria-label="模组详情分区" class="flex gap-1 border-b border-line px-3">
          <button
            v-for="t in tabDefs"
            :key="t.key"
            role="tab"
            :aria-selected="activeTab === t.key"
            class="-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors duration-150"
            :class="activeTab === t.key
              ? 'border-accent text-accent-strong'
              : 'border-transparent text-ink-3 hover:border-line-strong hover:text-ink'"
            @click="activeTab = t.key"
          >
            <component :is="t.icon" class="size-4" aria-hidden="true" />
            {{ t.label }}
            <span v-if="t.key === 'files' && mod.files.length" class="num text-[12px] text-ink-4">
              {{ mod.files.length }}
            </span>
          </button>
        </div>

        <!-- 简介:纯文本渲染,不解析富文本 -->
        <div v-show="activeTab === 'about'" class="p-5">
          <p v-if="mod.description" class="whitespace-pre-wrap text-[13.5px] leading-6 text-ink-2">
            {{ mod.description }}
          </p>
          <p v-else class="text-[13.5px] text-ink-4">暂无简介。可在创意工坊页面查看完整描述。</p>
        </div>

        <!-- 文件清单:局部滚动 -->
        <div v-show="activeTab === 'files'">
          <div v-if="mod.files.length">
            <div class="flex items-center justify-between px-5 pb-2 pt-4">
              <p class="text-[12.5px] text-ink-3">
                共 {{ mod.files.length }} 个文件 · 总计 {{ formatBytes(filesTotalSize) }}
              </p>
            </div>
            <div class="max-h-[480px] overflow-auto border-t border-line">
              <table class="tbl">
                <thead>
                  <tr>
                    <th>相对路径</th>
                    <th style="width: 120px">大小</th>
                    <th style="width: 200px">备注</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="f in mod.files" :key="f.rel_path">
                    <td class="mono break-all">{{ f.rel_path }}</td>
                    <td class="mono num">{{ formatBytes(f.size) }}</td>
                    <td>{{ f.note || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <EmptyState v-else title="没有文件记录" description="缓存扫描尚未记录该模组的文件清单,可尝试重新扫描。" />
        </div>

        <!-- 技术详情:五维状态 / 标识与路径 / 部署 / 元数据 -->
        <div v-show="activeTab === 'tech'" class="space-y-6 p-5">
          <div>
            <h3 class="mb-2 text-[12.5px] font-semibold text-ink-3">运行状态(五维)</h3>
            <SpecGrid :items="stateItems" :cols="5" />
            <p class="mt-2 text-[12px] text-ink-4">
              页面上的主状态「{{ status.label }}」由以上技术状态推导;完整定义以服务端状态机为准。
            </p>
          </div>

          <div>
            <h3 class="mb-2 text-[12.5px] font-semibold text-ink-3">标识与路径</h3>
            <div class="divide-y divide-line overflow-hidden rounded-lg border border-line">
              <div class="flex items-center gap-3 px-3 py-2">
                <span class="w-24 shrink-0 text-[12px] text-ink-4">Workshop ID</span>
                <span class="mono min-w-0 flex-1 break-all text-[13px] text-ink">{{ mod.workshop_id }}</span>
                <CopyButton :text="mod.workshop_id" label="Workshop ID" />
              </div>
              <div class="flex items-center gap-3 px-3 py-2">
                <span class="w-24 shrink-0 text-[12px] text-ink-4">文件夹名</span>
                <span class="mono min-w-0 flex-1 break-all text-[13px] text-ink">{{ mod.folder_name || '-' }}</span>
                <CopyButton v-if="mod.folder_name" :text="mod.folder_name" label="文件夹名" />
              </div>
              <div class="flex items-center gap-3 px-3 py-2">
                <span class="w-24 shrink-0 text-[12px] text-ink-4">缓存路径</span>
                <span class="mono min-w-0 flex-1 break-all text-[13px] text-ink">{{ mod.cache_path || '-' }}</span>
                <CopyButton v-if="mod.cache_path" :text="mod.cache_path" label="缓存路径" />
              </div>
              <div v-if="mod.deploy?.path" class="flex items-center gap-3 px-3 py-2">
                <span class="w-24 shrink-0 text-[12px] text-ink-4">部署路径</span>
                <span class="mono min-w-0 flex-1 break-all text-[13px] text-ink">{{ mod.deploy.path }}</span>
                <CopyButton :text="mod.deploy.path" label="部署路径" />
              </div>
            </div>
          </div>

          <div>
            <h3 class="mb-2 text-[12.5px] font-semibold text-ink-3">加载与文件</h3>
            <SpecGrid :items="loadItems" :cols="2" />
          </div>

          <div>
            <h3 class="mb-2 text-[12.5px] font-semibold text-ink-3">部署信息</h3>
            <SpecGrid :items="deployItems" :cols="2" />
          </div>

          <div>
            <h3 class="mb-2 text-[12.5px] font-semibold text-ink-3">元数据</h3>
            <SpecGrid :items="metaItems" :cols="2" />
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
