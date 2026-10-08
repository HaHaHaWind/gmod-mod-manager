/** 端点函数:与后端 routers 一一对应。 */
import { get, post } from './client'
import type {
  AuditView, LoginResp, ModDetail, ModView, PageResp, PlanView,
  SystemStatus, TaskView, TrashView,
} from './types'

// ---- auth ----
export const apiLogin = (username: string, password: string) =>
  post<LoginResp>('/api/auth/login', { username, password })
export const apiLogout = () => post<{ ok: boolean }>('/api/auth/logout')
export const apiMe = () => get<LoginResp>('/api/auth/me')

// ---- system ----
export const apiSystemStatus = () => get<SystemStatus>('/api/system/status')
export const apiAuditList = (page = 1, pageSize = 50) =>
  get<{ items: AuditView[]; total: number; page: number; page_size: number }>(
    '/api/system/audit', { page, page_size: pageSize })
export const apiCollectionSnapshot = (collectionId: string) =>
  post<{ task: TaskView }>('/api/collections/snapshot', { collection_id: collectionId })
export const previewUrl = (url: string) =>
  `/api/preview?url=${encodeURIComponent(url)}`
// 本地预览图:扫描后已落盘的封面直接走后端文件(未落盘时后端自动回退在线代理)
export const localPreview = (wid: string) => `/api/mods/${wid}/preview`

// ---- mods ----
export interface ModListQuery {
  q?: string
  inventory_state?: string
  desired_state?: string
  apply_state?: string
  page?: number
  page_size?: number
}
export const apiModList = (query: ModListQuery = {}) =>
  get<PageResp<ModView>>('/api/mods', query as Record<string, string | number>)
export const apiModDetail = (wid: string) => get<ModDetail>(`/api/mods/${wid}`)
export const apiStartScan = (deep: boolean) =>
  post<{ task: TaskView }>('/api/mods/scan', { deep })
export const apiRefreshMeta = (ids: string[]) =>
  post<{ task: TaskView; ids: string[] }>('/api/mods/metadata/refresh', { ids })

// ---- plans ----
export interface PlanItemInput {
  action: 'enable' | 'disable' | 'delete'
  workshop_id: string
  params?: Record<string, unknown>
}
export const apiCreatePlan = (items: PlanItemInput[], kind = 'batch') =>
  post<PlanView>('/api/plans', { items, kind })
export const apiPlanList = (status = '', limit = 20) =>
  get<{ items: PlanView[] }>('/api/plans', { status, limit })
export const apiPlanDetail = (planId: string) => get<PlanView>(`/api/plans/${planId}`)
export const apiActivePlan = () =>
  get<{ plan: PlanView | null }>('/api/plans/active/current')
export const apiPlanSubmit = (planId: string) =>
  post<PlanView>(`/api/plans/${planId}/submit`)
export const apiPlanApply = (planId: string) =>
  post<{ task: TaskView }>(`/api/plans/${planId}/apply`)
export const apiPlanCancel = (planId: string) =>
  post<PlanView>(`/api/plans/${planId}/cancel`)
export const apiPlanRetry = (planId: string) =>
  post<{ task: TaskView }>(`/api/plans/${planId}/retry`)

// ---- tasks ----
export const apiTaskList = (limit = 30) =>
  get<{ items: TaskView[] }>('/api/tasks', { limit })
export const apiTaskDetail = (taskId: string) => get<TaskView>(`/api/tasks/${taskId}`)

// ---- trash ----
export const apiTrashList = () => get<{ items: TrashView[] }>('/api/trash')
export const apiTrashRestore = (entryId: string) =>
  post<{ path: string }>(`/api/trash/${entryId}/restore`)
export const apiTrashPurge = (entryId: string) =>
  post<{ removed: boolean }>(`/api/trash/${entryId}/purge`)
