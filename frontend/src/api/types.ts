/** 后端 API 响应类型(与 backend/app/api/views.py 序列化结构一一对应)。 */

export interface ApiErrorBody {
  code: string
  message: string
  request_id?: string
  details?: unknown
}

export interface LoginResp {
  username: string
  is_admin: boolean
  csrf_token: string
  expires_at: string | null
}

export interface ModView {
  workshop_id: string
  folder_name: string
  title: string
  title_remote: string | null
  title_local: string | null
  author_name: string | null
  author_steamid: string | null
  tags: string[]
  preview_url: string | null
  size_bytes: number
  file_count: number
  inventory_state: string
  inventory_zh: string
  desired_state: string
  desired_zh: string
  apply_state: string
  apply_zh: string
  runtime_state: string
  runtime_zh: string
  requires_restart: boolean
  load_source: string
  load_sources: string[]
  protected: boolean
  protected_reason: string
  metadata_state: string
  metadata_error: string
  time_updated: string | null
  remote_file_size: number | null
  inventory_detail: Record<string, unknown>
}

export interface ModDetail extends ModView {
  description: string
  deploy: {
    version: number
    path: string
    size: number
    deployed_at: string | null
    source_changed: boolean
  }
  cache_path: string
  cache_mtime: number
  last_scan_at: string | null
  metadata_fetched_at: string | null
  metadata_source: string
  time_published: string | null
  remote_visibility: string
  files: { rel_path: string; size: number; note: string }[]
}

export interface PlanPreviewItem {
  workshop_id: string
  action: string
  title: string
  from: { inventory_state: string; desired_state: string; apply_state: string } | null
  to: { inventory_state?: string; desired_state: string; apply_state: string } | null
  warnings: string[]
  blocked: boolean
  block_reason: string
}

export interface PlanView {
  id: string
  kind: string
  status: string
  payload: { action: string; workshop_id: string; params: Record<string, unknown> }[]
  diff: {
    per_item: PlanPreviewItem[]
    blockers: { workshop_id: string; action: string; reason: string }[]
    summary: Record<string, number>
    mode: string
    strategy: string
  }
  base_revision: number
  revision: number
  created_by: string
  created_at: string | null
  expires_at: string | null
  applied_at: string | null
  error: string | null
  items?: PlanItemView[]
}

export interface PlanItemView {
  id: number
  workshop_id: string
  action: string
  status: string
  params: Record<string, unknown>
  error: string
  result: Record<string, unknown>
}

export interface TaskView {
  id: string
  kind: string
  status: string
  progress: number
  total: number
  error: string | null
  result: Record<string, unknown>
  plan_id: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface TrashView {
  id: string
  workshop_id: string
  title: string
  folder_name: string
  original_path: string
  trash_path: string
  status: string
  original_desired_state: string
  size_bytes: number
  file_count: number
  deleted_at: string | null
  deleted_by: string
  note: string
}

export interface AuditView {
  id: number
  ts: string | null
  actor: string
  action: string
  outcome: string
  target_type: string
  target_id: string
  detail: Record<string, unknown>
  request_id: string
  ip: string
}

export interface SystemStatus {
  management_mode: string
  local_managed_strategy: string
  server_control_mode: string
  read_only: boolean
  db_ok: boolean
  worker_alive: boolean | null
  active_plan_id: string | null
  counts: {
    mods: number
    trashed: number
    queued_tasks: number
    requires_restart: number
  }
  paths_configured: Record<string, boolean>
}

export interface PageResp<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
