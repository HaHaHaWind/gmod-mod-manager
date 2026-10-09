<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RotateCcw, Trash2 } from 'lucide-vue-next'
import { apiTrashList, apiTrashPurge, apiTrashRestore } from '@/api'
import { ApiRequestError } from '@/api/client'
import type { TrashView } from '@/api/types'
import { useSystemStore } from '@/stores/system'
import { confirmDialog } from '@/composables/useConfirm'
import { toast } from '@/composables/useToast'
import { TRASH_STATUS_ZH, formatBytes, formatTime, trashStatusTone } from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import Panel from '@/components/ui/Panel.vue'
import Skeleton from '@/components/ui/Skeleton.vue'

const system = useSystemStore()
const loading = ref(false)
const rows = ref<TrashView[]>([])
const acting = ref(false)

async function load() {
  loading.value = true
  try {
    rows.value = (await apiTrashList()).items
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '加载回收站失败')
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

async function restore(row: TrashView) {
  if (!requireWritable()) return
  const ok = await confirmDialog({
    title: '还原确认',
    description: `将 "${row.title}"(ID ${row.workshop_id})从回收站还原到原位置。若原位置已被占用将还原失败并提示。`,
    confirmText: '还原',
  })
  if (!ok) return
  acting.value = true
  try {
    const resp = await apiTrashRestore(row.id)
    toast.success(`已还原到 ${resp.path}`)
    await load()
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '还原失败')
  } finally {
    acting.value = false
  }
}

async function purge(row: TrashView) {
  if (!requireWritable()) return
  const ok = await confirmDialog({
    title: '永久删除确认',
    description: `将永久删除 "${row.title}"(ID ${row.workshop_id})的磁盘文件,大小 ${formatBytes(row.size_bytes)}。该操作不可恢复,删除后只能重新从创意工坊下载。`,
    confirmText: '永久删除',
    danger: true,
  })
  if (!ok) return
  acting.value = true
  try {
    const resp = await apiTrashPurge(row.id)
    toast.success(resp.removed ? '已永久删除磁盘文件' : '磁盘文件已不存在,记录已标记清除')
    await load()
  } catch (e) {
    toast.error(e instanceof ApiRequestError ? e.message : '删除失败')
  } finally {
    acting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-[24px] font-semibold tracking-tight text-ink">回收站</h1>
        <p class="mt-1 text-[13.5px] text-ink-3">共 {{ rows.length }} 条记录</p>
      </div>
      <Button size="sm" :loading="loading" @click="load">刷新</Button>
    </div>

    <div class="flex items-start gap-2 rounded-lg border border-accent-line bg-accent-soft px-3 py-2.5">
      <Trash2 class="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
      <p class="text-[12.5px] leading-5 text-ink-2">
        在模组库中删除的模组会先移入回收站(仅移动文件,不会立即删除),保留一段时间后由后台自动清理;期间可随时还原。
      </p>
    </div>

    <Panel :padded="false">
      <div v-if="loading && rows.length === 0" class="space-y-2 p-4">
        <Skeleton v-for="i in 5" :key="i" class="h-11 w-full" />
      </div>

      <EmptyState
        v-else-if="rows.length === 0"
        title="回收站为空"
        description="被删除的模组会先出现在这里,可在自动清理前还原。"
      />

      <div v-else class="overflow-x-auto">
        <table class="tbl">
          <thead>
            <tr>
              <th>名称</th>
              <th style="width: 110px">状态</th>
              <th style="width: 96px">大小</th>
              <th style="width: 168px">删除时间</th>
              <th style="width: 100px">操作人</th>
              <th style="width: 160px">备注</th>
              <th style="width: 190px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>
                <p class="font-medium text-ink">{{ row.title || row.folder_name }}</p>
                <p class="mono tiny muted">ID {{ row.workshop_id }}</p>
              </td>
              <td>
                <Badge :variant="trashStatusTone(row.status)">
                  {{ TRASH_STATUS_ZH[row.status] || row.status }}
                </Badge>
              </td>
              <td class="mono num">{{ formatBytes(row.size_bytes) }}</td>
              <td class="muted">{{ formatTime(row.deleted_at) }}</td>
              <td>{{ row.deleted_by || '-' }}</td>
              <td class="muted">{{ row.note || '-' }}</td>
              <td>
                <div class="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="secondary"
                    class="text-ok hover:bg-ok-soft hover:text-ok"
                    :loading="acting"
                    :disabled="system.readOnly || row.status !== 'in_trash'"
                    @click="restore(row)"
                  >
                    <RotateCcw class="size-3.5" aria-hidden="true" />
                    还原
                  </Button>
                  <Button
                    size="sm"
                    variant="danger-outline"
                    :loading="acting"
                    :disabled="system.readOnly || row.status !== 'in_trash'"
                    @click="purge(row)"
                  >
                    永久删除
                  </Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>
  </div>
</template>
