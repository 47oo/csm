// 前端校验规则与展示映射（与 Contract §0、需求 §4.9.3/§4.9.8 一致；
// 集群规则见 F001 Contract docs/api/F001.md §0、需求 §4.1/§4.4、BQ-W/BQ-Z；
// 服务端校验为最终保证，前端校验仅用于即时反馈）。

import type { Role, UserStatus } from '../api/types'

/** 用户名：仅字母与数字，长度 1–128（BQ-W/BQ-X） */
export const USERNAME_PATTERN = /^[A-Za-z0-9]{1,128}$/

export const USERNAME_RULE_MESSAGE = '用户名仅允许字母与数字，长度 1–128'

/** 内置管理员账号名（BQ-Y）：固定为 `admin`，由部署预置；不可删除、不可禁用、不可修改角色，可修改口令。
 * 前端据此做交互提示（禁用对应操作），服务端仍以 409 PROTECTED_ADMIN 做最终校验。 */
export const BUILT_IN_ADMIN_USERNAME = 'admin'

/** 是否内置管理员账号（BQ-Y：仅保护该账号，其它管理员可正常操作；用户名区分大小写） */
export function isProtectedAdmin(username: string): boolean {
  return username === BUILT_IN_ADMIN_USERNAME
}

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

// ---------- 集群（F001：需求 §4.1/§4.4、BQ-W/BQ-Z、Contract §0） ----------

/** 集群 code 规范化（BQ-Z）：去首尾空格 + 统一大写（与服务端 normalize_cluster_code 一致） */
export function normalizeClusterCode(raw: string): string {
  return raw.trim().toUpperCase()
}

/** 规范化后的 code 仅允许大写字母与数字、长度 1–32（BQ-Z：`^[A-Z0-9]{1,32}$`） */
export const CLUSTER_CODE_PATTERN = /^[A-Z0-9]{1,32}$/

export const CLUSTER_CODE_RULE_MESSAGE =
  '集群编号去首尾空格并转为大写后，仅允许大写字母与数字，长度 1–32'

/** 集群名称：仅字母/中文/下划线/数字，长度 1–64；含空格（首/尾/中）直接拒绝、不裁剪（BQ-W） */
export const CLUSTER_NAME_PATTERN = /^[A-Za-z0-9_\u4e00-\u9fff]{1,64}$/

export const CLUSTER_NAME_RULE_MESSAGE =
  '集群名称仅允许字母、中文、下划线、数字，长度 1–64，不能包含空格'

/** 用途：非空（架构 §8 PROPOSED-2：长度上限 200） */
export const CLUSTER_PURPOSE_RULE_MESSAGE = '用途不能为空，且长度不超过 200 个字符'

/** 校验集群 code：规范化后匹配 `^[A-Z0-9]{1,32}$`；合法返回 null */
export function validateClusterCode(value: string): string | null {
  if (!CLUSTER_CODE_PATTERN.test(normalizeClusterCode(value))) {
    return CLUSTER_CODE_RULE_MESSAGE
  }
  return null
}

/** 校验集群名称：合法返回 null（含空格直接拒绝，不做裁剪） */
export function validateClusterName(value: string): string | null {
  if (!CLUSTER_NAME_PATTERN.test(value)) {
    return CLUSTER_NAME_RULE_MESSAGE
  }
  return null
}

/** 校验集群用途：非空（纯空白拒绝）；合法返回 null */
export function validateClusterPurpose(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '' || trimmed.length > 200) {
    return CLUSTER_PURPOSE_RULE_MESSAGE
  }
  return null
}

/**
 * 真实删除二次确认匹配（BQ-Z / Contract §2.5）：输入去首尾空格后等于集群名称
 * （区分大小写），或规范化后等于集群 code（大小写不敏感）。不匹配不允许提交；
 * 服务端仍按同一口径做最终校验。
 */
export function clusterDeleteConfirmMatches(
  input: string,
  cluster: { code: string; name: string },
): boolean {
  const trimmed = input.trim()
  if (trimmed === '') return false
  return (
    trimmed === cluster.name || normalizeClusterCode(trimmed) === normalizeClusterCode(cluster.code)
  )
}
