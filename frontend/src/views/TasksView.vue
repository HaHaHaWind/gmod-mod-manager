<script setup lang="ts">
/** 任务中心:列表 + 轮询(存在进行中任务时 5s 刷新)+ 结果展开。 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiTaskList } from '@/api'
import type { TaskView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { TASK_KIND_ZH, TASK_STATUS_ZH, formatTime, taskStatusTag } from '@/utils/format'

const loading = ref(false)
const rows = ref<TaskView[]>([])
let timer: number | undefined

const hasActive = computed(() =>
  rows.value.some((t) => t.status === 'queued' || t.status === 'running'))

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const resp = await apiTaskList(30)
    rows.value = resp.items
  } catch (e) {
    if (!silent) ElMessage.error(e instanceof ApiRequestError ? e.message : '加载任务列表失败')
  } finally {
    if (!silent) loading.value = false
  }
}

function prettyJson(v: unknown): string {
  if (v === null || v === undefined) return '-'
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

onMounted(() => {
  load()
  timer = window.setInterval(() => load(true), 5000)
})
onUnmounted(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <div class="page-card">
    <div class="toolbar">
      <span class="muted small">后台任务由独立进程执行;应用计划、扫描、元数据刷新均在此排队。</span>
      <div class="toolbar-space" />
      <el-tag v-if="hasActive" type="warning" effect="plain" size="small">
        有进行中任务,自动刷新中
      </el-tag>
      <el-button size="small" @click="load()">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading">
      <el-table-column label="任务" width="150">
        <template #default="{ row }">
          {{ TASK_KIND_ZH[row.kind] || row.kind }}
          <div class="mono muted tiny">{{ row.id.slice(0, 12) }}…</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="taskStatusTag(row.status)" size="small">
            {{ TASK_STATUS_ZH[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="200">
        <template #default="{ row }">
          <el-progress v-if="row.total > 0"
                       :percentage="Math.min(100, Math.round(row.progress * 100 / row.total))"
                       :status="row.status === 'failed' ? 'exception'
                         : row.status === 'succeeded' ? 'success' : undefined"
                       :stroke-width="10" />
          <span v-else class="muted small">-</span>
        </template>
      </el-table-column>
      <el-table-column label="关联计划" width="130">
        <template #default="{ row }">
          <router-link v-if="row.plan_id" class="task-link mono small"
                       :to="{ name: 'plan-detail', params: { id: row.plan_id } }">
            {{ row.plan_id.slice(0, 10) }}…
          </router-link>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结束时间" width="160">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.finished_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="task-expand">
            <div v-if="row.error" class="task-err">错误:{{ row.error }}</div>
            <pre class="mono task-json">{{ prettyJson(row.result) }}</pre>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.toolbar-space { flex: 1; }
.tiny { font-size: 11px; }
.small { font-size: 12px; }
.task-link { color: var(--el-color-primary); text-decoration: none; }
.task-expand { padding: 8px 16px; }
.task-err { color: var(--el-color-danger); font-size: 13px; margin-bottom: 6px; }
.task-json {
  margin: 0; font-size: 12px; background: #fafafa; padding: 10px;
  border-radius: 4px; overflow: auto; max-height: 260px; line-height: 1.6;
}
</style>
