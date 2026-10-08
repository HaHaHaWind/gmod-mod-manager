/** 前端通用格式化:字节/时间/状态中文映射/状态色调映射。 */

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '-'
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
    `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export const PLAN_STATUS_ZH: Record<string, string> = {
  draft: '草稿', staged: '已提交待应用', applying: '应用中',
  applied: '已应用', failed: '失败', cancelled: '已取消',
  recovery_required: '需要恢复',
}

export const ITEM_STATUS_ZH: Record<string, string> = {
  pending: '待处理', staged: '已暂存', done: '完成',
  failed: '失败', skipped: '已跳过',
}

export const TASK_STATUS_ZH: Record<string, string> = {
  queued: '排队中', running: '执行中', succeeded: '成功',
  failed: '失败', cancelled: '已取消', interrupted: '被中断',
}

export const TASK_KIND_ZH: Record<string, string> = {
  scan: '扫描缓存', metadata_refresh: '刷新元数据',
  collection_snapshot: '集合快照', apply_plan: '应用变更计划',
}

export const TRASH_STATUS_ZH: Record<string, string> = {
  in_trash: '回收站中', restored: '已还原', purged: '已彻底清除',
}

export const ACTION_ZH: Record<string, string> = {
  enable: '启用', disable: '禁用', delete: '删除',
}

export const MANAGEMENT_MODE_ZH: Record<string, string> = {
  observe: '观察模式(只读)', native_ids: '原生 ID 清单', local_managed: '本地受管',
}

export const LOAD_SOURCE_ZH: Record<string, string> = {
  unmanaged_cache: '未接管缓存', native_ids: '原生 ID 清单',
  local_managed: '本地受管副本', external_collection: '外部集合引入',
  external_addons: '外部本地插件', unknown: '未知',
}

/** 状态色调:直接对应 Badge 组件的 variant。 */
export type Tone = 'success' | 'warning' | 'danger' | 'accent' | 'neutral'

export function planStatusTone(s: string): Tone {
  if (s === 'applied') return 'success'
  if (s === 'failed' || s === 'recovery_required') return 'danger'
  if (s === 'applying' || s === 'staged') return 'warning'
  return 'neutral'
}

export function itemStatusTone(s: string): Tone {
  if (s === 'done') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'pending' || s === 'staged') return 'warning'
  return 'neutral'
}

export function taskStatusTone(s: string): Tone {
  if (s === 'succeeded') return 'success'
  if (s === 'failed' || s === 'interrupted') return 'danger'
  if (s === 'running' || s === 'queued') return 'warning'
  return 'neutral'
}

export function trashStatusTone(s: string): Tone {
  if (s === 'in_trash') return 'warning'
  if (s === 'restored') return 'success'
  return 'neutral'
}

export function inventoryTone(s: string): Tone {
  if (s === 'present') return 'success'
  if (s === 'missing' || s === 'invalid') return 'danger'
  return 'neutral'
}

export function applyTone(s: string): Tone {
  if (s === 'synced') return 'success'
  if (s === 'pending' || s === 'applying') return 'warning'
  if (s === 'failed' || s === 'conflict') return 'danger'
  return 'neutral'
}

/** 期望状态:启用为强调色,禁用为中性。 */
export function desiredTone(s: string): Tone {
  if (s === 'enabled') return 'accent'
  if (s === 'disabled') return 'neutral'
  return 'neutral'
}

export function outcomeTone(o: string): Tone {
  if (o === 'ok' || o === 'success') return 'success'
  if (o === 'denied' || o === 'error') return 'danger'
  if (o === 'blocked') return 'warning'
  return 'neutral'
}
