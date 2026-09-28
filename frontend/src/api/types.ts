// F013 API 类型定义，字段与 docs/api/F013.md Contract 严格一致。

/** 角色固定枚举（Contract §0；中文展示由前端映射） */
export type Role = 'viewer' | 'maintainer' | 'admin'

/** 用户状态枚举（Contract §0） */
export type UserStatus = 'enabled' | 'disabled'

/** GET /auth/me、POST /auth/login 响应（Contract §1） */
export interface CurrentUser {
  id: number
  username: string
  role: Role
  status: UserStatus
  must_change_password: boolean
}

/** GET /users 列表项（Contract §1） */
export interface UserListItem {
  id: number
  username: string
  role: Role
  status: UserStatus
  must_change_password: boolean
  created_at: string
  updated_at: string
}

/** GET /users/{id}、POST /users、PATCH /users/{id} 响应（Contract §1） */
export interface UserDetail extends UserListItem {
  version: number
}

/** GET /users 分页响应（Contract §1） */
export interface PagedUsers {
  items: UserListItem[]
  total: number
  page: number
  page_size: number
}

/** problem+json 字段级错误（Contract §0） */
export interface FieldError {
  field: string
  code: string
  message: string
}

/** problem+json 响应体（Contract §0） */
export interface ProblemBody {
  type?: string
  title?: string
  status?: number
  code?: string
  message?: string
  errors?: FieldError[]
}
