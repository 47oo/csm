// 网段（F005）前端校验、确认匹配与错误/提示文案映射：
// 与 Contract docs/api/F005.md §0/§2/§3、架构 F005 §4/§5/§6、需求 §4.6/§5/§6.5
// 及 BQ-M/N/O/R/W/Z 一致。前端校验仅用于即时反馈；服务端为最终保证。
// 422 字段级错误（errors[].code：CIDR_INVALID/CIDR_NOT_IPV4/NAME_FORMAT/
// PURPOSE_INVALID/TECHNOLOGY_INVALID/VLAN_INVALID/GATEWAY_OUT_OF_CIDR/
// AUTO_RANGE_INVALID/RESERVED_OUT_OF_CIDR/RESERVED_RANGE_INVALID/RESERVED_OVERLAP）
// 由 client.fieldError 透传服务端 message 呈现，此处不重复枚举文案。

import type { Role } from '../api/types'
import type { OverlapWarning } from '../api/segments'
import { ipIntInCidr, ipv4ToInt, parseIpv4Cidr } from './ip'

// ---------- 字段即时校验 ----------

/** 网段名称：去首尾空格非空（区分大小写判重由服务端保证）、长度 ≤ 128（架构 §4.1） */
export const SEGMENT_NAME_RULE_MESSAGE = '网段名称去首尾空格后不能为空，长度不超过 128 个字符'

export function validateSegmentName(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '' || trimmed.length > 128) return SEGMENT_NAME_RULE_MESSAGE
  return null
}

/** 用途：去首尾空格非空、长度 ≤ 200（架构 §4.3） */
export const SEGMENT_PURPOSE_RULE_MESSAGE = '用途去首尾空格后不能为空，长度不超过 200 个字符'

export function validateSegmentPurpose(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '' || trimmed.length > 200) return SEGMENT_PURPOSE_RULE_MESSAGE
  return null
}

/** 技术类型：去首尾空格非空、长度 ≤ 100（架构 §4.3） */
export const SEGMENT_TECHNOLOGY_RULE_MESSAGE = '技术类型去首尾空格后不能为空，长度不超过 100 个字符'

export function validateSegmentTechnology(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '' || trimmed.length > 100) return SEGMENT_TECHNOLOGY_RULE_MESSAGE
  return null
}

/** CIDR：仅 IPv4、前缀 /0–/32；带主机位输入由服务端规范化（架构 §4.2） */
export const SEGMENT_CIDR_RULE_MESSAGE = 'CIDR 须为 IPv4 格式（前缀 /0–/32），如 192.168.1.0/24'

export function validateSegmentCidr(value: string): string | null {
  return parseIpv4Cidr(value) === null ? SEGMENT_CIDR_RULE_MESSAGE : null
}

/** VLAN：空（null/undefined）或整数 1–4094（架构 §4.4） */
export const SEGMENT_VLAN_RULE_MESSAGE = 'VLAN 须为 1–4094 的整数，或留空'

export function validateSegmentVlan(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null
  if (!Number.isInteger(value) || value < 1 || value > 4094) return SEGMENT_VLAN_RULE_MESSAGE
  return null
}

/** 网关：空串表示未设置；非空须为合法 IPv4 且落在 CIDR 内（数值比较；架构 §4.5、场景 53）。
 * CIDR 本身非法时返回 null（该错误由 CIDR 字段呈现），避免双重报错。 */
export const SEGMENT_GATEWAY_RULE_MESSAGE = '网关须为合法 IPv4 地址，且必须落在网段 CIDR 内'

export function validateGatewayInCidr(gateway: string, cidr: string): string | null {
  if (gateway === '') return null
  const parsedCidr = parseIpv4Cidr(cidr)
  if (parsedCidr === null) return null
  const gatewayInt = ipv4ToInt(gateway)
  if (gatewayInt === null || !ipIntInCidr(gatewayInt, parsedCidr)) return SEGMENT_GATEWAY_RULE_MESSAGE
  return null
}

/** 自动分配范围：两端成对（同为空或同为非空）、均为合法 IPv4 且落在 CIDR 内、起 ≤ 止
 * （需求 §5、架构 §4.6）。CIDR 非法时返回 null（由 CIDR 字段呈现）。 */
export const SEGMENT_AUTO_RANGE_RULE_MESSAGE =
  '自动分配范围：起始与结束须成对填写，均为合法 IPv4 且落在网段 CIDR 内，且起始不大于结束'

export function validateAutoAllocRange(start: string, end: string, cidr: string): string | null {
  if (start === '' && end === '') return null
  if (start === '' || end === '') return SEGMENT_AUTO_RANGE_RULE_MESSAGE
  const parsedCidr = parseIpv4Cidr(cidr)
  if (parsedCidr === null) return null
  const startInt = ipv4ToInt(start)
  const endInt = ipv4ToInt(end)
  if (
    startInt === null ||
    endInt === null ||
    !ipIntInCidr(startInt, parsedCidr) ||
    !ipIntInCidr(endInt, parsedCidr) ||
    startInt > endInt
  ) {
    return SEGMENT_AUTO_RANGE_RULE_MESSAGE
  }
  return null
}

/** 保留地址/范围：起止均为合法 IPv4 且落在 CIDR 内、起 ≤ 止；结束空串表示单地址
 * （需求 §5、架构 §4.7、场景 53）。CIDR 非法时返回 null（由 CIDR 字段呈现）。
 * 与既有保留范围的重叠（RESERVED_OVERLAP）由服务端校验。 */
export const SEGMENT_RESERVED_RULE_MESSAGE =
  '保留地址：起止均须为合法 IPv4 且落在网段 CIDR 内，且起始不大于结束；结束留空表示单个地址'

export function validateReservedRange(start: string, end: string, cidr: string): string | null {
  const parsedCidr = parseIpv4Cidr(cidr)
  if (parsedCidr === null) return null
  const startInt = ipv4ToInt(start)
  if (startInt === null || !ipIntInCidr(startInt, parsedCidr)) return SEGMENT_RESERVED_RULE_MESSAGE
  if (end !== '') {
    const endInt = ipv4ToInt(end)
    if (endInt === null || !ipIntInCidr(endInt, parsedCidr) || endInt < startInt) {
      return SEGMENT_RESERVED_RULE_MESSAGE
    }
  }
  return null
}

// ---------- 真实删除二次确认（BQ-Z、Contract §2.5） ----------

/** 删除确认：输入去首尾空格后须等于网段名称（区分大小写；仅名称，无 code）。 */
export function segmentDeleteConfirmMatches(input: string, segment: { name: string }): boolean {
  const trimmed = input.trim()
  return trimmed !== '' && trimmed === segment.name
}

// ---------- 重叠风险提示（需求 §4.6.5：仅提示、允许保存） ----------

/** 重叠提示文案；无重叠返回 null。 */
export function overlapWarningText(detail: {
  has_overlap: boolean
  overlaps: OverlapWarning[]
}): string | null {
  if (!detail.has_overlap) return null
  const names = detail.overlaps.map((o) => `${o.name}（${o.cidr}）`).join('、')
  if (names === '') return '该网段与同集群其它仍存网段重叠。重叠仅提示风险、允许保存。'
  return `该网段与同集群仍存网段重叠：${names}。重叠仅提示风险、允许保存；名称/CIDR 唯一性与分配排除规则不受豁免。`
}

// ---------- 服务端错误码 → 用户提示（409/422 业务语义，Contract §0） ----------

const SEGMENT_CONFLICT_MESSAGES: Record<string, string> = {
  SEGMENT_NAME_TAKEN: '同集群仍存网段中已有该名称（去首尾空格、区分大小写）；跨集群允许同名',
  SEGMENT_CIDR_TAKEN: '同集群已存在相同 CIDR 的网段（规范化后比较）；跨集群允许相同 CIDR',
  SEGMENT_HAS_RESERVED_ADDRESSES: '该网段仍有保留地址：须先逐条删除全部保留地址，才能删除网段',
  SEGMENT_GATEWAY_NOT_CLEARED: '该网段网关尚未清空：须先显式清空网关，才能删除网段',
  SEGMENT_HAS_INTERFACES:
    '该网段仍被网卡引用：须先解除对应网卡关联，才能删除网段（网卡录入由后续能力提供）',
  SEGMENT_HAS_ALLOCATIONS:
    '该网段仍有已分配 IP：须先逐项删除已分配地址，才能删除网段（IP 分配由后续能力提供）',
  CIDR_IMMUTABLE: '该网段存在已分配 IP，禁止修改 CIDR（IP 分配由后续能力提供）',
  VERSION_CONFLICT: '该网段已被其他人修改（并发冲突），请刷新后重试',
  DELETE_CONFIRMATION_MISMATCH: '确认输入与网段名称不匹配（网段可能已被其他人修改），未执行删除',
}

/** 409/422 业务错误码 → 用户提示文案；无映射返回 undefined（按通用错误处理） */
export function segmentConflictMessage(code: string): string | undefined {
  return SEGMENT_CONFLICT_MESSAGES[code]
}

// ---------- 权限入口可见性（架构 §8.2；服务端为最终校验） ----------

/** 网段写操作（新增/编辑/删除/保留地址/网关）入口是否可见：仅 maintainer/admin */
export function canManageSegments(role: Role | null | undefined): boolean {
  return role === 'maintainer' || role === 'admin'
}
