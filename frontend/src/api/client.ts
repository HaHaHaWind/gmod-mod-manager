/** fetch 封装:HttpOnly Cookie 会话 + x-csrf-token 头 + 统一错误结构。 */
import type { ApiErrorBody } from './types'

let csrfToken = ''

export function setCsrfToken(token: string): void {
  csrfToken = token
}

export function getCsrfToken(): string {
  return csrfToken
}

/** 业务错误:携带后端 code/message/request_id,页面按需提示。 */
export class ApiRequestError extends Error {
  readonly code: string
  readonly status: number
  readonly requestId: string
  readonly details: unknown

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || `请求失败(HTTP ${status})`)
    this.code = body.code || 'unknown'
    this.status = status
    this.requestId = body.request_id || ''
    this.details = body.details
  }
}

/** 会话失效(401):由 router 全局处理跳登录页。 */
export class UnauthorizedError extends Error {
  constructor() {
    super('登录状态已失效,请重新登录')
  }
}

interface Opts {
  method?: string
  json?: unknown
  query?: Record<string, string | number | boolean | undefined>
}

export async function request<T>(path: string, opts: Opts = {}): Promise<T> {
  const method = (opts.method || 'GET').toUpperCase()
  const url = new URL(path, window.location.origin)
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v))
    }
  }
  const headers: Record<string, string> = {}
  let body: string | undefined
  if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  }
  if (method !== 'GET') headers['x-csrf-token'] = csrfToken

  let resp: Response
  try {
    resp = await fetch(url.pathname + url.search, {
      method, headers, body, credentials: 'same-origin',
    })
  } catch {
    throw new ApiRequestError(0, { code: 'network_error', message: '无法连接到管理面板后端' })
  }

  if (resp.status === 401) throw new UnauthorizedError()

  const text = await resp.text()
  let data: unknown = null
  if (text) {
    try { data = JSON.parse(text) } catch { data = null }
  }

  if (!resp.ok) {
    const errBody = (data && typeof data === 'object'
      && 'code' in data) ? data as ApiErrorBody : { code: 'http_error', message: `请求失败(HTTP ${resp.status})` }
    throw new ApiRequestError(resp.status, errBody)
  }
  return data as T
}

export const get = <T>(path: string, query?: Opts['query']) =>
  request<T>(path, { query })
export const post = <T>(path: string, json?: unknown) =>
  request<T>(path, { method: 'POST', json })
