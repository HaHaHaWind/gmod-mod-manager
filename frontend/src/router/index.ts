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
        { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '总览' } },
        { path: 'mods', name: 'mods', component: () => import('@/views/ModsView.vue'), meta: { title: 'Mod 库' } },
        { path: 'mods/:wid', name: 'mod-detail', component: () => import('@/views/ModDetailView.vue'), meta: { title: 'Mod 详情' } },
        { path: 'plans', name: 'plans', component: () => import('@/views/PlansView.vue'), meta: { title: '变更计划' } },
        { path: 'plans/:id', name: 'plan-detail', component: () => import('@/views/PlanDetailView.vue'), meta: { title: '计划详情' } },
        { path: 'tasks', name: 'tasks', component: () => import('@/views/TasksView.vue'), meta: { title: '任务中心' } },
        { path: 'trash', name: 'trash', component: () => import('@/views/TrashView.vue'), meta: { title: '回收站' } },
        { path: 'audit', name: 'audit', component: () => import('@/views/AuditView.vue'), meta: { title: '审计日志' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) await auth.probe()
  if (!to.meta.public && !auth.loggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.loggedIn) return { name: 'dashboard' }
  return true
})

export default router
