<script setup lang="ts">
/** Mod 详情:五维状态 + 元数据 + 部署信息 + 文件清单。 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiCreatePlan, apiModDetail, apiRefreshMeta, localPreview } from '@/api'
import type { ModDetail } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { useSystemStore } from '@/stores/system'
import {
  ACTION_ZH, LOAD_SOURCE_ZH, applyTag, formatBytes, formatTime, inventoryTag,
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const system = useSystemStore()

const wid = computed(() => String(route.params.wid || ''))
const mod = ref<ModDetail | null>(null)
const loading = ref(false)
const acting = ref(false)

async function load() {
  loading.value = true
  try {
    mod.value = await apiModDetail(wid.value)
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '加载 Mod 详情失败')
  } finally {
    loading.value = false
  }
}

async function refreshMeta() {
  if (system.readOnly) { ElMessage.warning('当前为只读模式,无法执行该操作'); return }
  acting.value = true
  try {
    await apiRefreshMeta([wid.value])
    ElMessage.success('元数据刷新任务已创建')
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '创建刷新任务失败')
  } finally {
    acting.value = false
  }
}

async function quickPlan(action: 'enable' | 'disable' | 'delete') {
  if (system.readOnly) { ElMessage.warning('当前为只读模式,无法执行该操作'); return }
  acting.value = true
  try {
    const plan = await apiCreatePlan([{ action, workshop_id: wid.value }])
    ElMessage.success(`已创建单项${ACTION_ZH[action]}计划,请确认预览`)
    router.push({ name: 'plan-detail', params: { id: plan.id } })
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '创建计划失败')
  } finally {
    acting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="page-card">
    <template v-if="mod">
      <div class="detail-head">
        <el-image class="detail-thumb" :src="mod.preview_url ? localPreview(mod.workshop_id) : ''"
                  fit="cover">
          <template #error><div class="detail-thumb-err">无预览图</div></template>
        </el-image>
        <div class="detail-head-text">
          <h2 class="detail-title">{{ mod.title || mod.folder_name || mod.workshop_id }}</h2>
          <div class="mono muted small">
            Workshop ID {{ mod.workshop_id }} ·
            <a :href="'https://steamcommunity.com/sharedfiles/filedetails/?id=' + mod.workshop_id"
               target="_blank" rel="noopener">打开创意工坊页面</a>
            <template v-if="mod.folder_name"> · {{ mod.folder_name }}</template>
          </div>
          <div class="detail-author muted small">
            作者:{{ mod.author_name || '未知' }}
            <template v-if="mod.author_steamid">({{ mod.author_steamid }})</template>
          </div>
          <div class="detail-tags">
            <el-tag v-for="t in mod.tags" :key="t" size="small" effect="plain">{{ t }}</el-tag>
            <el-tag v-if="mod.protected" type="danger" size="small" effect="dark">
              受保护:{{ mod.protected_reason }}
            </el-tag>
          </div>
        </div>
        <div class="detail-actions">
          <el-button size="small" :loading="acting" :disabled="system.readOnly"
                     @click="refreshMeta">刷新元数据</el-button>
          <el-button size="small" type="success" plain :loading="acting"
                     :disabled="system.readOnly" @click="quickPlan('enable')">启用</el-button>
          <el-button size="small" type="warning" plain :loading="acting"
                     :disabled="system.readOnly" @click="quickPlan('disable')">禁用</el-button>
          <el-button size="small" type="danger" plain :loading="acting"
                     :disabled="system.readOnly || mod.protected" @click="quickPlan('delete')">
            删除
          </el-button>
        </div>
      </div>

      <el-descriptions title="五维状态" :column="5" border size="small" class="detail-section">
        <el-descriptions-item label="清单">
          <el-tag :type="inventoryTag(mod.inventory_state)" size="small">
            {{ mod.inventory_zh || mod.inventory_state }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="期望">{{ mod.desired_zh || mod.desired_state }}</el-descriptions-item>
        <el-descriptions-item label="应用">
          <el-tag :type="applyTag(mod.apply_state)" size="small">
            {{ mod.apply_zh || mod.apply_state }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="运行时">{{ mod.runtime_zh || mod.runtime_state }}</el-descriptions-item>
        <el-descriptions-item label="需重启">
          <el-tag :type="mod.requires_restart ? 'warning' : 'info'" size="small">
            {{ mod.requires_restart ? '是' : '否' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-descriptions title="加载与文件" :column="2" border size="small" class="detail-section">
        <el-descriptions-item label="加载来源">
          {{ LOAD_SOURCE_ZH[mod.load_source] || mod.load_source }}
          <span v-if="mod.load_sources.length > 1" class="muted small">
            (共 {{ mod.load_sources.length }} 处:{{ mod.load_sources.join('、') }})
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="缓存大小">
          <span class="mono">{{ formatBytes(mod.size_bytes) }}</span>
          <span class="muted small">({{ mod.file_count }} 个文件)</span>
        </el-descriptions-item>
        <el-descriptions-item label="缓存路径">
          <span class="mono small">{{ mod.cache_path || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="最近扫描">{{ formatTime(mod.last_scan_at) }}</el-descriptions-item>
        <el-descriptions-item label="Workshop 更新">{{ formatTime(mod.time_updated) }}</el-descriptions-item>
        <el-descriptions-item label="远端大小">
          {{ mod.remote_file_size == null ? '未知' : formatBytes(mod.remote_file_size) }}
        </el-descriptions-item>
      </el-descriptions>

      <el-descriptions title="部署信息(local_managed)" :column="2" border size="small"
                       class="detail-section">
        <el-descriptions-item label="部署版本">v{{ mod.deploy?.version ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="部署时间">{{ formatTime(mod.deploy?.deployed_at) }}</el-descriptions-item>
        <el-descriptions-item label="部署路径">
          <span class="mono small">{{ mod.deploy?.path || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="部署大小">
          {{ mod.deploy?.size ? formatBytes(mod.deploy.size) : '-' }}
          <el-tag v-if="mod.deploy?.source_changed" type="warning" size="small">缓存已有更新</el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-descriptions title="元数据" :column="2" border size="small" class="detail-section">
        <el-descriptions-item label="抓取状态">
          {{ mod.metadata_state || '未抓取' }}
          <span v-if="mod.metadata_error" class="detail-err">{{ mod.metadata_error }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="抓取时间">{{ formatTime(mod.metadata_fetched_at) }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ mod.metadata_source || '-' }}</el-descriptions-item>
        <el-descriptions-item label="发布时间">{{ formatTime(mod.time_published) }}</el-descriptions-item>
      </el-descriptions>

      <div class="detail-section">
        <h4 class="detail-sub">简介</h4>
        <div class="detail-desc">{{ mod.description || '(无简介)' }}</div>
      </div>

      <div class="detail-section">
        <h4 class="detail-sub">文件清单({{ mod.files.length }})</h4>
        <el-table :data="mod.files" size="small" max-height="320">
          <el-table-column prop="rel_path" label="相对路径" min-width="280">
            <template #default="{ row }"><span class="mono">{{ row.rel_path }}</span></template>
          </el-table-column>
          <el-table-column label="大小" width="110">
            <template #default="{ row }">
              <span class="mono">{{ formatBytes(row.size) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" width="180" />
        </el-table>
      </div>
    </template>
    <el-empty v-else-if="!loading" description="未找到该 Mod" />
  </div>
</template>

<style scoped>
.detail-head { display: flex; gap: 16px; align-items: flex-start; }
.detail-thumb {
  width: 184px; height: 104px; border-radius: 6px; background: #f0f2f5; flex: none;
}
.detail-thumb-err {
  width: 184px; height: 104px; display: flex; align-items: center; justify-content: center;
  color: #c0c4cc; font-size: 12px;
}
.detail-head-text { flex: 1; min-width: 0; }
.detail-title { margin: 0 0 4px; font-size: 18px; }
.detail-author { margin-top: 2px; }
.detail-tags { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
.detail-actions { display: flex; flex-direction: column; gap: 8px; align-items: stretch; }
.detail-section { margin-top: 18px; }
.detail-sub { margin: 0 0 8px; font-size: 14px; color: #303133; }
.detail-desc {
  white-space: pre-wrap; font-size: 13px; color: #606266; line-height: 1.7;
  max-height: 240px; overflow: auto; background: #fafafa; padding: 10px; border-radius: 4px;
}
.detail-err { color: var(--el-color-danger); margin-left: 8px; font-size: 12px; }
.small { font-size: 12px; }
</style>
