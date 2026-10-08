/** 系统状态:管理模式/只读/活跃计划,布局与页面共享。 */
import { defineStore } from 'pinia'
import { apiActivePlan, apiSystemStatus } from '@/api'
import type { SystemStatus } from '@/api/types'

export const useSystemStore = defineStore('system', {
  state: () => ({
    status: null as SystemStatus | null,
    activePlanId: '' as string,
  }),
  getters: {
    readOnly: (s) => s.status?.read_only ?? true,
    managementMode: (s) => s.status?.management_mode ?? 'observe',
  },
  actions: {
    async refresh() {
      try {
        this.status = await apiSystemStatus()
        const cur = await apiActivePlan()
        this.activePlanId = cur.plan?.id ?? ''
      } catch {
        /* 未登录/后端离线时静默,页面各自处理 */
      }
    },
  },
})
