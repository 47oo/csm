/**
 * CSM 前端共享 API 类型。
 *
 * 依据（单一权威来源，代码中不得另立约定）：
 * - docs/api/api-conventions.md —— 错误信封（§5）、状态码与 error.code（§6）、
 *   分页信封（§3）、Empty / Not Found 语义（§7）；
 * - docs/api/f012-project-foundation.md —— F012 契约（含非产品自检面 §4）。
 */

/** 后端统一错误信封中的稳定错误码（api-conventions.md §6）。 */
export type BackendApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'INTERNAL_ERROR'

/**
 * 前端可依赖的错误码全集。
 *
 * - 后端码见 api-conventions.md §6（`BackendApiErrorCode`）；
 * - `NETWORK_ERROR` / `UNKNOWN_ERROR` 是前端本地补充码，表示请求未按契约
 *   得到可解析的后端响应（网络失败、非 JSON 响应等），不是后端契约值；
 * - 后端未来可能新增码（前端未同步更新时），ApiError.code 保留原始字符串，
 *   由 ErrorState 的兜底分支渲染，不得丢失或改写。
 */
export type ApiErrorCode = BackendApiErrorCode | 'NETWORK_ERROR' | 'UNKNOWN_ERROR'

/** 错误信封 `details[]` 单项（api-conventions.md §5）。 */
export interface ApiErrorDetail {
  /** 仅导入等行式请求出现（F011）；普通请求省略。 */
  row?: number
  /** 出问题的字段名（如 "name"）。 */
  field?: string
  /** 详情级错误码（如 "DUPLICATE"）。 */
  code?: string
  /** 人类可读原因，可随文案调整，不构成契约。 */
  message?: string
}

/** 统一错误信封（api-conventions.md §5）。 */
export interface ApiErrorEnvelope {
  error: {
    code: string
    message: string
    details?: ApiErrorDetail[]
  }
}

/** 分页列表信封（api-conventions.md §3）。 */
export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/**
 * 分页查询参数（api-conventions.md §3）。
 * F012 契约 §4.2：page 从 1 起（默认 1）；page_size 默认 50，上限 200；
 * 非法值由后端返回 400 VALIDATION_ERROR（不在前端自行猜测规则）。
 */
export type PageParams = {
  page?: number
  page_size?: number
}
