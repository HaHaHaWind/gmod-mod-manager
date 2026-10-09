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
  scan: '扫描模组', metadata_refresh: '更新模组信息',
  collection_snapshot: '同步合集信息', apply_plan: '应用变更计划',
}

export const OUTCOME_ZH: Record<string, string> = {
  ok: '成功', fail: '失败', blocked: '被阻止',
}

export const TRASH_STATUS_ZH: Record<string, string> = {
  in_trash: '回收站中', restored: '已还原', purged: '已彻底清除',
}

export const ACTION_ZH: Record<string, string> = {
  enable: '启用', disable: '禁用', delete: '移至回收站',
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

/** ============================================================
 *  主状态映射表:把五维技术状态组合为用户可读的单一主状态。
 *  输入:inventory / desired / apply / runtime / requires_restart
 *  原则:
 *  - runtime 未知时不断言"正在运行";
 *  - apply=synced 表示配置与部署一致(仍可能需要重启生效);
 *  - 不确定时使用保守文案,完整技术状态始终可在详情页查看。
 *  ============================================================ */
export interface PrimaryStatus {
  label: string
  tone: Tone
  /** 保守的补充说明,仅在有确切依据时提供 */
  hint?: string
}

export function primaryModStatus(m: {
  inventory_state: string
  desired_state: string
  apply_state: string
  runtime_state: string
  requires_restart: boolean
}): PrimaryStatus {
  // 回收站条目不再描述运行语义
  if (m.inventory_state === 'trashed') {
    return { label: '回收站中', tone: 'warning', hint: '已移入回收站,可随时恢复' }
  }
  // 文件层面异常优先暴露
  if (m.inventory_state === 'missing') {
    return { label: '文件缺失', tone: 'danger', hint: '本地文件丢失,无法保证可用' }
  }
  if (m.inventory_state === 'invalid') {
    return { label: '文件异常', tone: 'danger', hint: '本地文件校验失败' }
  }
  // 应用链路:失败/冲突/进行中/等待应用
  if (m.apply_state === 'failed') {
    return { label: '应用失败', tone: 'danger', hint: '上一次变更未成功,请在变更记录中查看' }
  }
  if (m.apply_state === 'conflict') {
    return { label: '存在冲突', tone: 'danger', hint: '与其他变更冲突,需人工处理' }
  }
  if (m.apply_state === 'applying') {
    return { label: '正在应用变更', tone: 'warning' }
  }
  if (m.apply_state === 'pending') {
    const target =
      m.desired_state === 'enabled' ? '启用' : m.desired_state === 'disabled' ? '禁用' : ''
    return { label: target ? `等待应用${target}设置` : '等待应用变更', tone: 'warning' }
  }
  // 已同步但需重启:配置正确,等待服务器重启生效
  if (m.apply_state === 'synced' && m.requires_restart) {
    return {
      label: m.desired_state === 'enabled' ? '已配置启用,待重启生效' : '配置已更新,待重启生效',
      tone: 'accent',
      hint: '服务器重启后设置生效',
    }
  }
  // 稳定态:按期望状态给结论;运行状态仅在确凿时展示
  if (m.apply_state === 'synced') {
    if (m.desired_state === 'enabled') {
      if (m.runtime_state === 'loaded') return { label: '运行中', tone: 'success' }
      if (m.runtime_state === 'not_loaded') {
        return { label: '已启用,当前未加载', tone: 'neutral' }
      }
      return { label: '已启用', tone: 'success' }
    }
    if (m.desired_state === 'disabled') return { label: '已禁用', tone: 'neutral' }
    return { label: '未纳管', tone: 'neutral' }
  }
  if (m.apply_state === 'unmanaged') return { label: '未纳管', tone: 'neutral' }
  return { label: '状态未知', tone: 'neutral' }
}

/** 复制文本到剪贴板,返回是否成功(供 UI 反馈)。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/** 从计划 payload 推导人类可读标题,如"启用 3 个模组"。 */
export function planTitle(payload: { action: string }[]): string {
  if (!payload || payload.length === 0) return '空变更'
  const counts = new Map<string, number>()
  for (const p of payload) counts.set(p.action, (counts.get(p.action) ?? 0) + 1)
  if (counts.size === 1) {
    const [action, n] = [...counts.entries()][0]
    return `${ACTION_ZH[action] ?? action} ${n} 个模组`
  }
  return [...counts.entries()].map(([a, n]) => `${ACTION_ZH[a] ?? a} ${n} 个`).join('、')
}
