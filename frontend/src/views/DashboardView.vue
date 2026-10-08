<script setup lang="ts">
/** 总览:统计卡 + 系统健康 + 活跃计划 + 快捷操作。 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiActivePlan, apiStartScan } from '@/api'
import { useSystemStore } from '@/stores/system'
import { ApiRequestError } from '@/api/client'
import { PLAN_STATUS_ZH, formatTime, planStatusTag } from '@/utils/format'
import type { PlanView } from '@/api/types'

const router = useRouter()
const system = useSystemStore()
const activePlan = ref<PlanView | null>(null)
const scanning = ref(false)
let timer: number | undefined

const counts = computed(() => system.status?.counts ?? {
  mods: 0, trashed: 0, queued_tasks: 0, requires_restart: 0,
})

const missingPaths = computed(() => {
  const p = system.status?.paths_configured
  if (!p) return []
  return Object.entries(p).filter(([, ok]) => !ok).map(([k]) => k)
})

async function refreshAll() {
  await system.refresh()
  try {
    const cur = await apiActivePlan()
    activePlan.value = cur.plan
  } catch { /* 未登录时忽略 */ }
}

async function startScan(deep: boolean) {
  if (system.readOnly) {
    ElMessage.warning('当前为只读模式,无法发起扫描')
    return
  }
  scanning.value = true
  try {
    const resp = await apiStartScan(deep)
    ElMessage.success(`扫描任务已创建(${resp.task.id.slice(0, 8)}),可在任务中心查看进度`)
    router.push({ name: 'tasks' })
  } catch (e) {
    ElMessage.error(e instanceof ApiRequestError ? e.message : '创建扫描任务失败')
  } finally {
    scanning.value = false
  }
}

onMounted(() => {
  refreshAll()
  timer = window.setInterval(refreshAll, 10000)
})
onUnmounted(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <div class="dash">
    <el-row :gutter="12">
      <el-col :span="6" v-for="card in [
        { label: '已登记 Mod', value: counts.mods, desc: '扫描收录的 Workshop 条目' },
        { label: '回收站条目', value: counts.trashed, desc: '可在保留期内还原' },
        { label: '排队任务', value: counts.queued_tasks, desc: '等待后台进程执行' },
        { label: '待重启 Mod', value: counts.requires_restart, desc: '配置已应用,需重启生效' },
      ]" :key="card.label">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-desc">{{ card.desc }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="dash-row">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>系统健康</span>
              <div>
                <el-button size="small" :loading="scanning" :disabled="system.readOnly"
                           @click="startScan(false)">
                  快速扫描
                </el-button>
                <el-button size="small" type="primary" plain :loading="scanning"
                           :disabled="system.readOnly" @click="startScan(true)">
                  全量扫描(校验文件)
                </el-button>
              </div>
            </div>
          </template>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="管理模式">
              {{ system.status ? (system.status.management_mode === 'observe'
                ? '观察模式(只读)' : system.status.management_mode === 'native_ids'
                ? '原生 ID 清单' : '本地受管') : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="部署策略" v-if="system.status">
              {{ system.status.local_managed_strategy || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="服务器控制">
              {{ system.status?.server_control_mode === 'systemd' ? 'systemd(不自动重启)' : 'manual(不自动重启)' }}
            </el-descriptions-item>
            <el-descriptions-item label="数据库">
              <el-tag :type="system.status?.db_ok ? 'success' : 'danger'" size="small">
                {{ system.status?.db_ok ? '正常' : '异常' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="后台进程">
              <el-tag :type="system.status?.worker_alive ? 'success' : 'danger'" size="small">
                {{ system.status?.worker_alive == null ? '未知' : system.status?.worker_alive ? '存活' : '已停止' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="只读开关">
              <el-tag :type="system.readOnly ? 'danger' : 'success'" size="small">
                {{ system.readOnly ? '已开启' : '关闭' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <el-alert v-if="missingPaths.length" type="warning" show-icon :closable="false"
                    class="dash-paths"
                    :title="`以下路径未配置或不存在:${missingPaths.join('、')}`"
                    description="请检查 .env 配置后重启后端服务。" />
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never">
          <template #header><span>进行中的变更计划</span></template>
          <template v-if="activePlan">
            <div class="active-plan">
              <div class="mono small">{{ activePlan.id }}</div>
              <div class="active-plan-meta">
                <el-tag :type="planStatusTag(activePlan.status)" size="small">
                  {{ PLAN_STATUS_ZH[activePlan.status] || activePlan.status }}
                </el-tag>
                <span class="muted">{{ activePlan.payload?.length ?? 0 }} 个变更项</span>
                <span class="muted">{{ formatTime(activePlan.created_at) }}</span>
              </div>
              <el-button size="small" type="primary" plain
                         @click="router.push({ name: 'plan-detail', params: { id: activePlan.id } })">
                查看详情
              </el-button>
            </div>
          </template>
          <el-empty v-else description="当前没有进行中的计划" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stat-card { text-align: left; }
.stat-value { font-size: 28px; font-weight: 600; }
.stat-label { margin-top: 2px; font-size: 13px; color: #303133; }
.stat-desc { margin-top: 4px; font-size: 12px; color: #909399; }
.dash-row { margin-top: 12px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.dash-paths { margin-top: 12px; }
.active-plan { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.active-plan-meta { display: flex; gap: 10px; align-items: center; }
.small { font-size: 12px; }
</style>
