// axios 统一客户端：baseURL /api/v1、withCredentials、application/problem+json
// 错误归一化与 401/403 全局处理入口（架构 §2.4 / ADR-004）。
//
// 401 → onUnauthorized（跳登录页）；403 PASSWORD_CHANGE_REQUIRED →
// onPasswordChangeRequired（强制改密）；403 其它 → onForbidden（提示）；
// 409（USERNAME_TAKEN / VERSION_CONFLICT / LAST_ADMIN）不跳转，错误原样抛出，
// 由页面保留输入并提示。处理器经 setApiHandlers 注入（main.ts 装配），
// 避免本模块直接依赖 router / Element Plus（便于单测）。

import axios, { type AxiosInstance } from 'axios'
import type { FieldError, ProblemBody } from './types'

/** 归一化后的 API 错误：承载 problem+json 的 code/message/errors[] */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly errors: FieldError[]

  constructor(status: number, code: string, message: string, errors: FieldError[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.errors = errors
  }

  /** 取某字段的字段级错误信息（无则 undefined） */
  fieldError(field: string): string | undefined {
    return this.errors.find((e) => e.field === field)?.message
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 跳过全局 401/403 处理（用于 /auth/login、/auth/me 等自身负责错误呈现的请求） */
    skipGlobalErrorHandling?: boolean
  }
}

export interface ApiHandlers {
  onUnauthorized: (error: ApiError) => void
  onForbidden: (error: ApiError) => void
  onPasswordChangeRequired: (error: ApiError) => void
}

let handlers: ApiHandlers | null = null

/** 注入全局 401/403 处理器（应用启动时调用一次；测试可替换） */
export function setApiHandlers(next: ApiHandlers): void {
  handlers = next
}

/** 清除全局处理器（测试隔离用） */
export function resetApiHandlers(): void {
  handlers = null
}

export const client: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 15000,
})

/** 把任意 axios/网络错误归一化为 ApiError（problem+json 优先） */
export function normalizeApiError(error: unknown): ApiError {
  if (isApiError(error)) return error
  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? 0
    const body = error.response?.data as unknown
    if (body !== null && typeof body === 'object' && 'code' in (body as object)) {
      const problem = body as ProblemBody
      return new ApiError(
        status,
        typeof problem.code === 'string' && problem.code ? problem.code : 'UNKNOWN',
        typeof problem.message === 'string' && problem.message ? problem.message : `请求失败（HTTP ${status}）`,
        Array.isArray(problem.errors) ? problem.errors : [],
      )
    }
    if (error.response) {
      return new ApiError(status, 'UNKNOWN', `请求失败（HTTP ${status}）`)
    }
    return new ApiError(0, 'NETWORK_ERROR', '网络错误，请检查与服务器的连接后重试')
  }
  return new ApiError(0, 'UNKNOWN', '未知错误')
}

client.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const apiError = normalizeApiError(error)
    const skip =
      axios.isAxiosError(error) && (error.config as unknown as { skipGlobalErrorHandling?: boolean } | undefined)
        ?.skipGlobalErrorHandling === true
    if (!skip && handlers) {
      if (apiError.status === 401) {
        handlers.onUnauthorized(apiError)
      } else if (apiError.status === 403 && apiError.code === 'PASSWORD_CHANGE_REQUIRED') {
        handlers.onPasswordChangeRequired(apiError)
      } else if (apiError.status === 403) {
        handlers.onForbidden(apiError)
      }
    }
    return Promise.reject(apiError)
  },
)

/** 页面通用错误提示文案：优先使用 problem+json 的 message */
export function apiErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status >= 500 && error.code === 'UNKNOWN') {
      return `服务器错误（HTTP ${error.status}），请稍后重试`
    }
    return error.message
  }
  return '操作失败，请稍后重试'
}
