<script setup lang="ts">
/** 回收站:还原(冲突自动提示)/ 彻底清除(危险确认)。 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiTrashList, apiTrashPurge, apiTrashRestore } from '@/api'
import type { TrashView } from '@/api/types'
import { ApiRequestError } from '@/api/client'
import { useSystemStore } from '@/stores/system'
import { TRASH_STATUS_ZH, formatBytes, formatTime, trashStatusTag } from '@/utils/format'

const system = useSystemStore()
const loading = ref(false)
const rows = ref<TrashView[]>([])
const acting = ref(false)

async function load() {
  loading.value = true
  try {
    const resp = await apiTrashList()
    rows.value = resp.items
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '加载回收站失败')
  } finally {
    loading.value = false
  }
}

function requireWritable(): boolean {
  if (system.readOnly) {
    ElMessage.warning('当前为只读模式,无法执行该操作')
    return false
  }
  return true
}

async function restore(row: TrashView) {
  if (!requireWritable()) return
  try {
    await ElMessageBox.confirm(
      `将 "${row.title}"(ID ${row.workshop_id})从回收站还原到原位置。` +
      '若原位置已被占用将还原失败并提示。',
      '还原确认', { confirmButtonText: '还原', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  acting.value = true
  try {
    const resp = await apiTrashRestore(row.id)
    ElMessage.success(`已还原到 ${resp.path}`)
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '还原失败')
  } finally {
    acting.value = false
  }
}

async function purge(row: TrashView) {
  if (!requireWritable()) return
  try {
    await ElMessageBox.confirm(
      `将永久删除 "${row.title}"(ID ${row.workshop_id})的磁盘文件,` +
      `大小 ${formatBytes(row.size_bytes)}。该操作不可恢复!`,
      '彻底删除确认', {
        confirmButtonText: '永久删除', cancelButtonText: '取消',
        type: 'error', confirmButtonClass: 'el-button--danger',
      })
  } catch { return }
  acting.value = true
  try {
    const resp = await apiTrashPurge(row.id)
    ElMessage.success(resp.removed ? '已彻底删除磁盘文件' : '磁盘文件已不存在,记录已标记清除')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '删除失败')
  } finally {
    acting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-card">
    <el-alert type="info" show-icon :closable="false" class="trash-tip"
              title="删除的 Mod 会先移入回收站(移动文件,非立即删除),超过保留期后由后台自动清理。" />
    <div class="toolbar">
      <span class="muted small">共 {{ rows.length }} 条记录</span>
      <div class="toolbar-space" />
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading">
      <el-table-column label="Mod" min-width="220">
        <template #default="{ row }">
          {{ row.title || row.folder_name }}
          <div class="mono muted small">ID {{ row.workshop_id }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="trashStatusTag(row.status)" size="small">
            {{ TRASH_STATUS_ZH[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">
          <span class="mono">{{ formatBytes(row.size_bytes) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="删除时间" width="160">
        <template #default="{ row }">
          <span class="muted">{{ formatTime(row.deleted_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="deleted_by" label="操作人" width="100" />
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">{{ row.note || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="success" plain :loading="acting"
                     :disabled="system.readOnly || row.status !== 'in_trash'"
                     @click="restore(row)">
            还原
          </el-button>
          <el-button size="small" type="danger" plain :loading="acting"
                     :disabled="system.readOnly || row.status !== 'in_trash'"
                     @click="purge(row)">
            彻底删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.trash-tip { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.toolbar-space { flex: 1; }
.small { font-size: 12px; }
</style>
