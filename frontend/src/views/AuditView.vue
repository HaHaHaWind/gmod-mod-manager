<script setup lang="ts">
/** 审计日志:分页 + 详情展开(敏感字段已由后端脱敏)。 */
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiAuditList } from '@/api'
import type { AuditView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { formatTime } from '@/utils/format'

const loading = ref(false)
const rows = ref<AuditView[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)

async function load() {
  loading.value = true
  try {
    const resp = await apiAuditList(page.value, pageSize.value)
    rows.value = resp.items
    total.value = resp.total
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '加载审计日志失败')
  } finally {
    loading.value = false
  }
}

function prettyJson(v: unknown): string {
  if (v === null || v === undefined) return '-'
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function outcomeTag(o: string): 'success' | 'danger' | 'warning' | 'info' {
  if (o === 'ok' || o === 'success') return 'success'
  if (o === 'denied' || o === 'error') return 'danger'
  if (o === 'blocked') return 'warning'
  return 'info'
}

watch([page, pageSize], load)
onMounted(load)
</script>

<template>
  <div class="page-card">
    <div class="toolbar">
      <span class="muted small">所有管理操作(含被拒绝的请求)均有记录,共 {{ total }} 条。</span>
      <div class="toolbar-space" />
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" size="small">
      <el-table-column label="时间" width="160">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.ts) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="actor" label="操作人" width="110" />
      <el-table-column prop="action" label="动作" width="180">
        <template #default="{ row }"><span class="mono">{{ row.action }}</span></template>
      </el-table-column>
      <el-table-column label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="outcomeTag(row.outcome)" size="small">{{ row.outcome }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="目标" min-width="180">
        <template #default="{ row }">
          <span class="mono small">{{ row.target_type }}:{{ row.target_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="来源 IP" width="130">
        <template #default="{ row }"><span class="mono small">{{ row.ip || '-' }}</span></template>
      </el-table-column>
      <el-table-column label="request_id" width="150">
        <template #default="{ row }">
          <span class="mono tiny muted">{{ row.request_id ? row.request_id.slice(0, 10) + '…' : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column type="expand">
        <template #default="{ row }">
          <pre class="audit-json mono">{{ prettyJson(row.detail) }}</pre>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
                     :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next"
                     background />
    </div>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.toolbar-space { flex: 1; }
.small { font-size: 12px; }
.tiny { font-size: 11px; }
.audit-json {
  margin: 0; font-size: 12px; background: #fafafa; padding: 10px;
  border-radius: 4px; overflow: auto; max-height: 260px; line-height: 1.6;
}
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
</style>
