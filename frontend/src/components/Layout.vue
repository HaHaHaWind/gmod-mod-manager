<script setup lang="ts">
/** 全局布局:侧边导航 + 顶栏(系统状态徽章 / 用户菜单)。 */
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Refresh, Monitor, FolderOpened, Tickets, Delete, Document, Odometer, ArrowDown,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { MANAGEMENT_MODE_ZH } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()

const pageTitle = computed(() => (route.meta.title as string) || '')
let timer: number | undefined

onMounted(() => {
  system.refresh()
  timer = window.setInterval(() => system.refresh(), 15000)
})
onUnmounted(() => { if (timer) window.clearInterval(timer) })

async function onLogout() {
  await auth.logout()
  system.$reset()
  ElMessage.success('已退出登录')
  router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="layout-root">
    <el-aside width="220px" class="layout-aside">
      <div class="layout-logo">
        <el-icon :size="22"><Monitor /></el-icon>
        <div class="layout-logo-text">
          <div class="t1">GMod Mod 管理面板</div>
          <div class="t2">Workshop 服务端</div>
        </div>
      </div>
      <el-menu :default-active="$route.path" router class="layout-menu">
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon><span>总览</span>
        </el-menu-item>
        <el-menu-item index="/mods">
          <el-icon><FolderOpened /></el-icon><span>Mod 库</span>
        </el-menu-item>
        <el-menu-item index="/plans">
          <el-icon><Tickets /></el-icon><span>变更计划</span>
        </el-menu-item>
        <el-menu-item index="/trash">
          <el-icon><Delete /></el-icon><span>回收站</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><Refresh /></el-icon><span>任务中心</span>
        </el-menu-item>
        <el-menu-item index="/audit">
          <el-icon><Document /></el-icon><span>审计日志</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="layout-header" height="56px">
        <div class="layout-title">{{ pageTitle }}</div>
        <div class="layout-badges">
          <el-tooltip content="只读开关开启时,所有写操作将被拒绝" placement="bottom">
            <el-tag v-if="system.readOnly" type="danger" effect="plain">只读</el-tag>
          </el-tooltip>
          <el-tag type="info" effect="plain">
            {{ MANAGEMENT_MODE_ZH[system.managementMode] || system.managementMode }}
          </el-tag>
          <el-tag v-if="(system.status?.counts.requires_restart ?? 0) > 0"
                  type="warning" effect="plain">
            待重启 {{ system.status?.counts.requires_restart }}
          </el-tag>
          <el-tag v-if="system.activePlanId" type="warning" effect="light">
            有进行中的计划
          </el-tag>
          <el-tooltip :content="system.status?.worker_alive ? '后台任务进程正常' : '后台任务进程不可用'"
                      placement="bottom">
            <el-tag :type="system.status?.worker_alive ? 'success' : 'danger'" effect="plain">
              worker {{ system.status?.worker_alive ? '正常' : '异常' }}
            </el-tag>
          </el-tooltip>
        </div>
        <div class="layout-user">
          <el-dropdown @command="(cmd: string) => cmd === 'logout' && onLogout()">
            <span class="layout-username">
              {{ auth.username }}<el-icon style="margin-left:4px"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  {{ auth.isAdmin ? '管理员' : '普通用户' }}
                </el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-root { height: 100vh; }
.layout-aside {
  border-right: 1px solid var(--el-border-color-light);
  background: #fff;
  display: flex; flex-direction: column;
}
.layout-logo {
  display: flex; align-items: center; gap: 10px;
  padding: 16px 16px 12px;
  color: var(--el-color-primary);
}
.layout-logo-text .t1 { font-weight: 600; font-size: 15px; color: #303133; }
.layout-logo-text .t2 { font-size: 12px; color: #909399; }
.layout-menu { border-right: none; flex: 1; }
.layout-header {
  display: flex; align-items: center; gap: 16px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: #fff;
}
.layout-title { font-size: 16px; font-weight: 600; }
.layout-badges { display: flex; gap: 8px; align-items: center; flex: 1; }
.layout-user { cursor: pointer; }
.layout-username {
  display: inline-flex; align-items: center;
  font-size: 14px; color: #303133; outline: none;
}
.layout-main { background: #f5f7fa; padding: 16px; }
</style>
