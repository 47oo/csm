// 前端校验规则与展示映射（与 Contract §0、需求 §4.9.3/§4.9.8 一致；
// 服务端校验为最终保证，前端校验仅用于即时反馈）。

import type { Role, UserStatus } from '../api/types'

/** 用户名：仅字母与数字，长度 1–128（BQ-W/BQ-X） */
export const USERNAME_PATTERN = /^[A-Za-z0-9]{1,128}$/

export const USERNAME_RULE_MESSAGE = '用户名仅允许字母与数字，长度 1–128'

/** 口令策略：≥8 位且同时包含字母与数字（§4.9.8） */
export const PASSWORD_POLICY_MESSAGE = '口令至少 8 位且同时包含字母与数字'

/** 校验用户名：合法返回 null，否则返回错误信息 */
export function validateUsername(value: string): string | null {
  if (!USERNAME_PATTERN.test(value)) {
    return USERNAME_RULE_MESSAGE
  }
  return null
}

/** 校验口令策略：合法返回 null，否则返回错误信息 */
export function validatePassword(value: string): string | null {
  if (value.length < 8 || !/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) {
    return PASSWORD_POLICY_MESSAGE
  }
  return null
}

/** 角色中文展示映射（Contract §5：三角色固定枚举） */
export const ROLE_LABELS: Record<Role, string> = {
  viewer: '运维查看者',
  maintainer: '资源维护者',
  admin: '平台管理员',
}

export const ROLE_OPTIONS: Array<{ value: Role; label: string }> = [
  { value: 'viewer', label: ROLE_LABELS.viewer },
  { value: 'maintainer', label: ROLE_LABELS.maintainer },
  { value: 'admin', label: ROLE_LABELS.admin },
]

export function roleLabel(role: Role): string {
  return ROLE_LABELS[role] ?? role
}

/** 状态中文展示映射 */
export const STATUS_LABELS: Record<UserStatus, string> = {
  enabled: '启用',
  disabled: '禁用',
}

export function statusLabel(status: UserStatus): string {
  return STATUS_LABELS[status] ?? status
}
