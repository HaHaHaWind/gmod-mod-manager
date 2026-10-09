<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ImageOff, RefreshCw } from 'lucide-vue-next'
import { apiCreatePlan, apiModDetail, apiRefreshMeta, localPreview } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { ModDetail } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { toast } from '@/composables/useToast'
import {
  ACTION_ZH, LOAD_SOURCE_ZH, applyTone, formatBytes, formatTime, inventoryTone,
} from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Panel from '@/components/ui/Panel.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import SpecGrid, { type SpecItem } from '@/components/ui/SpecGrid.vue'

type Action = 'enable' | 'disable' | 'delete'

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

async function load() {
  loading.value = true
  try {
    mod.value = await apiModDetail(wid.value)
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '加载 Mod 详情失败')
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
    toast.success('元数据刷新任务已创建')
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建刷新任务失败')
  } finally {
    acting.value = false
  }
}

async function quickPlan(action: Action) {
  if (!requireWritable()) return
  acting.value = true
  try {
    const plan = await apiCreatePlan([{ action, workshop_id: wid.value }])
    toast.success(`已创建单项${ACTION_ZH[action]}计划,请确认预览`)
    router.push({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '创建计划失败')
  } finally {
    acting.value = false
  }
}

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
    { label: '期望', value: m.desired_zh || m.desired_state },
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
    { label: '缓存路径', value: m.cache_path || '-', mono: true },
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
    {
      label: '抓取状态',
      value: m.metadata_state || '未抓取',
      note: m.metadata_error || undefined,
    },
    { label: '抓取时间', value: formatTime(m.metadata_fetched_at) },
    { label: '来源', value: m.metadata_source || '-' },
    { label: '发布时间', value: formatTime(m.time_published) },
  ]
})

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div v-if="loading && !mod" class="space-y-4">
      <div class="rounded-2xl border border-line bg-surface p-5 shadow-card">
        <div class="flex flex-col gap-4 sm:flex-row">
          <Skeleton class="aspect-video w-full rounded-lg sm:w-[280px]" />
          <div class="flex-1 space-y-2.5">
            <Skeleton class="h-5 w-2/3" />
            <Skeleton class="h-3.5 w-1/2" />
            <Skeleton class="h-6 w-40" />
            <Skeleton class="h-8 w-64" />
          </div>
        </div>
      </div>
      <Skeleton class="h-24 w-full rounded-xl" />
      <Skeleton class="h-40 w-full rounded-xl" />
    </div>

    <EmptyState v-else-if="!mod" title="未找到该 Mod" description="该条目可能已被移除,或 Workshop ID 不正确。" />

    <template v-else>
      <div class="rounded-2xl border border-line bg-surface shadow-card">
        <div class="flex flex-col gap-4 p-5 sm:flex-row">
          <div class="w-full shrink-0 sm:w-[280px]">
            <div class="aspect-video overflow-hidden rounded-lg bg-surface-muted">
              <img
                v-if="hasPreview"
                :src="localPreview(mod.workshop_id)"
                :alt="title"
                class="size-full object-cover"
                @error="failed = true"
              >
              <div v-else class="flex size-full flex-col items-center justify-center gap-1.5 text-ink-4">
                <ImageOff class="size-5" aria-hidden="true" />
                <span class="text-[11px]">无预览图</span>
              </div>
            </div>
          </div>

          <div class="min-w-0 flex-1">
            <h2 class="text-[17px] font-semibold leading-6 tracking-tight text-ink">{{ title }}</h2>
            <p class="mono tiny muted mt-1.5">
              Workshop ID {{ mod.workshop_id }} ·
              <a :href="workshopUrl" target="_blank" rel="noopener" class="text-accent hover:underline">打开创意工坊页面</a>
              <template v-if="mod.folder_name"> · {{ mod.folder_name }}</template>
            </p>
            <p class="small muted mt-1">
              作者:{{ mod.author_name || '未知' }}
              <template v-if="mod.author_steamid">({{ mod.author_steamid }})</template>
            </p>

            <div class="mt-2.5 flex flex-wrap gap-1.5">
              <Badge v-for="t in mod.tags" :key="t" variant="outline">{{ t }}</Badge>
              <Badge v-if="mod.protected" variant="danger">受保护:{{ mod.protected_reason }}</Badge>
            </div>

            <div class="mt-3.5 flex flex-wrap gap-2">
              <Button size="sm" :loading="acting" :disabled="system.readOnly" @click="refreshMeta">
                <RefreshCw class="size-3.5" aria-hidden="true" />
                刷新元数据
              </Button>
              <Button
                size="sm"
                variant="secondary"
                class="text-ok hover:bg-ok-soft hover:text-ok"
                :loading="acting"
                :disabled="system.readOnly || mod.desired_state === 'enabled'"
                @click="quickPlan('enable')"
              >
                启用
              </Button>
              <Button
                size="sm"
                variant="secondary"
                class="text-warn hover:bg-warn-soft hover:text-warn"
                :loading="acting"
                :disabled="system.readOnly || mod.desired_state === 'disabled'"
                @click="quickPlan('disable')"
              >
                禁用
              </Button>
              <Button
                size="sm"
                variant="danger-outline"
                :loading="acting"
                :disabled="system.readOnly || mod.protected"
                :title="mod.protected ? mod.protected_reason : ''"
                @click="quickPlan('delete')"
              >
                删除
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Panel title="五维状态">
        <SpecGrid :items="stateItems" :cols="5" />
      </Panel>

      <Panel title="加载与文件">
        <SpecGrid :items="loadItems" :cols="2" />
      </Panel>

      <Panel title="部署信息(local_managed)">
        <SpecGrid :items="deployItems" :cols="2" />
      </Panel>

      <Panel title="元数据">
        <SpecGrid :items="metaItems" :cols="2" />
      </Panel>

      <Panel title="简介">
        <p class="whitespace-pre-wrap text-[13px] leading-6 text-ink-2">{{ mod.description || '(无简介)' }}</p>
      </Panel>

      <Panel :title="`文件清单(${mod.files.length})`" :padded="false">
        <div v-if="mod.files.length" class="max-h-[360px] overflow-auto">
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
        <EmptyState v-else title="没有文件记录" />
      </Panel>
    </template>
  </div>
</template>