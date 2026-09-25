// 用户与角色管理 API（Contract §3，仅 admin；越权 403 由全局处理器提示）。
import { client } from './client'
import type { PagedUsers, Role, UserDetail, UserStatus } from './types'

export interface UserCreatePayload {
  username: string
  password: string
  role: Role
}

export interface UserUpdatePayload {
  role: Role
  /** 乐观锁版本号，必填（Contract §3.4） */
  version: number
}

export interface UserResetPasswordPayload {
  new_password: string
}

/** 列表查询输入：过滤项允许空字符串（表示不过滤），空项不发送 */
export interface UserListQueryInput {
  page?: number
  page_size?: number
  q?: string
  role?: Role | ''
  status?: UserStatus | ''
  sort?: 'username' | '-username' | 'created_at' | '-created_at' | ''
}

/** GET /users：分页/筛选列表（Contract §3.1） */
export function listUsers(query: UserListQueryInput): Promise<PagedUsers> {
  const params: Record<string, string> = {}
  if (query.page !== undefined) params.page = String(query.page)
  if (query.page_size !== undefined) params.page_size = String(query.page_size)
  if (query.q !== undefined && query.q.trim() !== '') params.q = query.q.trim()
  if (query.role !== undefined && query.role !== '') params.role = query.role
  if (query.status !== undefined && query.status !== '') params.status = query.status
  if (query.sort !== undefined && query.sort !== '') params.sort = query.sort
  return client.get<PagedUsers>('/users', { params }).then((res) => res.data)
}

/** POST /users：新增用户（201 → UserDetail；409 USERNAME_TAKEN 由页面保留输入提示） */
export function createUser(payload: UserCreatePayload): Promise<UserDetail> {
  return client.post<UserDetail>('/users', payload).then((res) => res.data)
}

/** GET /users/{user_id}：详情（含 version，供编辑/删除乐观锁） */
export function getUser(userId: number): Promise<UserDetail> {
  return client.get<UserDetail>(`/users/${userId}`).then((res) => res.data)
}

/** PATCH /users/{user_id}：仅修改角色（用户名创建后不可改，BQ-X）；version 乐观锁 */
export function updateUser(userId: number, payload: UserUpdatePayload): Promise<UserDetail> {
  return client.patch<UserDetail>(`/users/${userId}`, payload).then((res) => res.data)
}

/** DELETE /users/{user_id}?version=：删除（乐观锁经 query 传递，Contract §3.5） */
export function deleteUser(userId: number, version: number): Promise<void> {
  return client
    .delete<void>(`/users/${userId}`, { params: { version } })
    .then(() => undefined)
}

/** POST /users/{user_id}/disable：禁用（幂等；最后一个启用中的管理员 409 LAST_ADMIN） */
export function disableUser(userId: number): Promise<void> {
  return client
    .post<void>(`/users/${userId}/disable`)
    .then(() => undefined)
}

/** POST /users/{user_id}/enable：启用（幂等） */
export function enableUser(userId: number): Promise<void> {
  return client
    .post<void>(`/users/${userId}/enable`)
    .then(() => undefined)
}

/** POST /users/{user_id}/reset-password：管理员重置口令 */
export function resetPassword(userId: number, payload: UserResetPasswordPayload): Promise<void> {
  return client
    .post<void>(`/users/${userId}/reset-password`, payload)
    .then(() => undefined)
}
