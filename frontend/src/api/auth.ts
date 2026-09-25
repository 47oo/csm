// 认证与会话 API（Contract §2）。
import { client } from './client'
import type { CurrentUser } from './types'

export interface LoginPayload {
  username: string
  password: string
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
}

/** POST /auth/login：登录建立会话（错误由登录页自行呈现，跳过全局 401 处理） */
export function login(payload: LoginPayload): Promise<CurrentUser> {
  return client
    .post<CurrentUser>('/auth/login', payload, { skipGlobalErrorHandling: true })
    .then((res) => res.data)
}

/** POST /auth/logout：登出（幂等 204） */
export function logout(): Promise<void> {
  // 登出失败（如会话已失效）不应触发全局跳转，由 store 统一清理本地状态。
  return client
    .post<void>('/auth/logout', undefined, { skipGlobalErrorHandling: true })
    .then(() => undefined)
}

/** GET /auth/me：当前操作者（401 属于正常未登录状态，由调用方处理，不走全局跳转） */
export function me(): Promise<CurrentUser> {
  return client
    .get<CurrentUser>('/auth/me', { skipGlobalErrorHandling: true })
    .then((res) => res.data)
}

/** POST /auth/change-password：自助改密（含 must_change_password 用户） */
export function changePassword(payload: ChangePasswordPayload): Promise<void> {
  return client
    .post<void>('/auth/change-password', payload)
    .then(() => undefined)
}
