import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        // 模组库是产品主入口:根路径直接落到模组库
        { path: '', redirect: { name: 'mods' } },
        { path: 'mods', name: 'mods', component: () => import('@/views/ModsView.vue'), meta: { title: '模组库' } },
        { path: 'mods/:wid', name: 'mod-detail', component: () => import('@/views/ModDetailView.vue'), meta: { title: '模组详情' } },
        // 操作记录:变更记录 + 后台任务,复用原 URL 与命名路由
        { path: 'plans', name: 'plans', component: () => import('@/views/PlansView.vue'), meta: { title: '变更记录' } },
        { path: 'plans/:id', name: 'plan-detail', component: () => import('@/views/PlanDetailView.vue'), meta: { title: '变更详情' } },
        { path: 'tasks', name: 'tasks', component: () => import('@/views/TasksView.vue'), meta: { title: '后台任务' } },
        { path: 'trash', name: 'trash', component: () => import('@/views/TrashView.vue'), meta: { title: '回收站' } },
        // 原"总览"调整为次级"服务状态";旧 /dashboard 链接兼容跳转
        { path: 'system', name: 'system', component: () => import('@/views/DashboardView.vue'), meta: { title: '服务状态' } },
        { path: 'dashboard', redirect: { name: 'system' } },
        // 审计日志:管理员次级入口
        { path: 'audit', name: 'audit', component: () => import('@/views/AuditView.vue'), meta: { title: '审计日志', adminOnly: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: { name: 'mods' } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) await auth.probe()
  if (!to.meta.public && !auth.loggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.loggedIn) return { name: 'mods' }
  // 管理员专属页面:非管理员落回模组库
  if (to.meta.adminOnly && !auth.isAdmin) return { name: 'mods' }
  return true
})

export default router
