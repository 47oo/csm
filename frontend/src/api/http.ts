/**
 * CSM 前端统一 HTTP 请求封装与错误归一化（API client 基座）。
 *
 * 职责：
 * - 集中发送请求：页面组件不得散落 fetch 调用；
 * - 按 docs/api/api-conventions.md §5 解析统一错误信封，归一为 ApiError；
 * - 网络失败 / 非 JSON 响应等「未按契约得到响应」的情况归一为前端本地码
 *   （NETWORK_ERROR / UNKNOWN_ERROR），避免组件层各自猜测。
 *
 * 消费方分支渲染只依据 ApiError.code；error.message 仅用于展示，不参与任何判断。
 */
import type { ApiErrorDetail, ApiErrorEnvelope } from '../types/api'

/** 归一化后的 API 错误。 */
export class ApiError extends Error {
  /** HTTP 状态码；请求未到达服务器（网络失败）时为 0。 */
  readonly status: number
  /** 稳定机器可读错误码：后端 error.code，或前端本地码（NETWORK_ERROR / UNKNOWN_ERROR）。 */
  readonly code: string
  /** 字段级错误详情（api-conventions.md §5 details[]）；无则为空数组。 */
  readonly details: readonly ApiErrorDetail[]

  constructor(init: {
    status: number
    code: string
    message: string
    details?: readonly ApiErrorDetail[]
  }) {
    super(init.message)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.details = init.details ? [...init.details] : []
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  /** 查询参数；值为 undefined 的项不会出现在 URL 中。 */
  query?: Record<string, string | number | undefined>
  /** 请求体；非 undefined 时以 JSON 发送。 */
  body?: unknown
}

function buildUrl(path: string, query: RequestOptions['query']): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      params.append(key, String(value))
    }
  }
  const queryString = params.toString()
  return queryString ? `${path}?${queryString}` : path
}

function isApiErrorEnvelope(payload: unknown): payload is ApiErrorEnvelope {
  if (typeof payload !== 'object' || payload === null) return false
  const error = (payload as { error?: unknown }).error
  if (typeof error !== 'object' || error === null) return false
  return typeof (error as { code?: unknown }).code === 'string'
}

/** 从错误响应体解析统一错误信封；无法按契约解析时归一为 UNKNOWN_ERROR。 */
function toApiError(status: number, payload: unknown): ApiError {
  if (isApiErrorEnvelope(payload)) {
    return new ApiError({
      status,
      code: payload.error.code,
      message: typeof payload.error.message === 'string' ? payload.error.message : '',
      details: Array.isArray(payload.error.details) ? payload.error.details : [],
    })
  }
  return new ApiError({
    status,
    code: 'UNKNOWN_ERROR',
    message: `服务器返回了无法解析的错误响应（HTTP ${status}）。`,
  })
}

/**
 * 发送 API 请求并解析响应。
 *
 * - 2xx + JSON → 解析后的数据；
 * - 204 → undefined；
 * - 非 2xx → 抛出 ApiError（携带后端 error.code / details）；
 * - 网络失败 / 非 JSON → 抛出 ApiError（NETWORK_ERROR / UNKNOWN_ERROR）。
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers: {
        Accept: 'application/json',
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    // fetch 只在网络层失败时 reject（DNS 解析失败、连接拒绝、中断等）。
    throw new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: '无法连接服务器，请检查网络或服务状态后重试。',
    })
  }

  if (response.status === 204) {
    return undefined as T
  }

  let payload: unknown = null
  let parseFailed = false
  try {
    payload = await response.json()
  } catch {
    parseFailed = true
  }

  if (!response.ok) {
    throw toApiError(response.status, parseFailed ? null : payload)
  }
  if (parseFailed) {
    // 2xx 但响应体不是 JSON：不符合契约，按未知错误归一。
    throw new ApiError({
      status: response.status,
      code: 'UNKNOWN_ERROR',
      message: '服务器响应不是有效的 JSON。',
    })
  }
  return payload as T
}
