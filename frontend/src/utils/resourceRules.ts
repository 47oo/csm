// 计算资源（F002）表单校验、网卡 op 映射、错误定位与提示文案：
// 与 Contract docs/api/F002.md §0/§1/§2、架构 F002 §2.4/§4/§5/§6、
// 需求 §4.1–§4.5/§6.4/§7 及 BQ-AA/BQ-W/BQ-Z 一致。
// 前端校验仅用于即时反馈（§7.2）；唯一性、归属关系、权限、并发由服务端最终保证。
// 422/400 字段级错误（errors[].code：NAME_FORMAT/RESOURCE_TYPE_INVALID/STATUS_INVALID/
// INTERFACE_NAME_FORMAT/INTERFACE_NAME_DUPLICATE_IN_PAYLOAD/INTERFACE_NOT_FOUND/
// INTERFACE_SEGMENT_INVALID/INTERFACE_SEGMENT_CLUSTER_MISMATCH/RESOURCE_TYPE_IMMUTABLE/
// RESOURCE_CLUSTER_IMMUTABLE/NO_FIELDS/INVALID_INTERFACE_OP）透传服务端 message 呈现，
// 此处负责把它们定位到表单字段与具体网卡卡片（§7.3）。

import type { FieldError, Role } from '../api/types'
import type {
  NetworkInterfaceCreateItem,
  NetworkInterfaceOpItem,
  ResourceStatus,
  ResourceType,
} from '../api/resources'

// ---------- 枚举展示（状态必须含文字，需求 §6.2/§9.4） ----------

export const RESOURCE_TYPE_LABELS: Record<ResourceType, string> = {
  bare_metal: '裸金属',
  virtual_machine: '虚拟机',
}

export const RESOURCE_TYPE_OPTIONS: Array<{ value: ResourceType; label: string }> = [
  { value: 'bare_metal', label: RESOURCE_TYPE_LABELS.bare_metal },
  { value: 'virtual_machine', label: RESOURCE_TYPE_LABELS.virtual_machine },
]

export function resourceTypeLabel(type: string): string {
  return RESOURCE_TYPE_LABELS[type as ResourceType] ?? type
}

export const RESOURCE_STATUS_LABELS: Record<ResourceStatus, string> = {
  IDLE: '空闲',
  ALLOC: '已分配',
  DOWN: '宕机 / 不可用',
  UNKNOWN: '未知',
}

export const RESOURCE_STATUS_OPTIONS: Array<{ value: ResourceStatus; label: string }> = [
  { value: 'IDLE', label: RESOURCE_STATUS_LABELS.IDLE },
  { value: 'ALLOC', label: RESOURCE_STATUS_LABELS.ALLOC },
  { value: 'DOWN', label: RESOURCE_STATUS_LABELS.DOWN },
  { value: 'UNKNOWN', label: RESOURCE_STATUS_LABELS.UNKNOWN },
]

export function resourceStatusLabel(status: string): string {
  return RESOURCE_STATUS_LABELS[status as ResourceStatus] ?? status
}

// ---------- 字段即时校验（§7.2 前端基础校验） ----------

/** 资源名：去首尾空格非空、长度 ≤128（架构 §4.1；同集群唯一由服务端保证） */
export const RESOURCE_NAME_RULE_MESSAGE = '资源名称去首尾空格后不能为空，长度不超过 128 个字符'

export function validateResourceName(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '' || trimmed.length > 128) return RESOURCE_NAME_RULE_MESSAGE
  return null
}

/** 接口名：去首尾空格非空、长度 ≤128（架构 §4.5；同资源唯一由服务端保证） */
export const INTERFACE_NAME_RULE_MESSAGE = '接口名去首尾空格后不能为空，长度不超过 128 个字符'

export function validateInterfaceName(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '' || trimmed.length > 128) return INTERFACE_NAME_RULE_MESSAGE
  return null
}

/** 同表单接口名重复（§7.2）：去首尾空格、区分大小写比较（与服务端口径一致，BQ-W）。
 * 返回重复涉及的卡片 key 集合（含首张与后续重复张）。 */
export const INTERFACE_NAME_DUPLICATE_MESSAGE =
  '同一表单内接口名重复（去首尾空格、区分大小写）；同一资源下接口名必须唯一'

export function findDuplicateInterfaceKeys(cards: Array<{ key: string; name: string }>): Set<string> {
  const firstByKey = new Map<string, string>()
  const duplicated = new Set<string>()
  for (const card of cards) {
    const trimmed = card.name.trim()
    if (trimmed === '') continue
    const first = firstByKey.get(trimmed)
    if (first === undefined) {
      firstByKey.set(trimmed, card.key)
    } else {
      duplicated.add(first)
      duplicated.add(card.key)
    }
  }
  return duplicated
}

// ---------- 真实删除二次确认（BQ-Z、Contract §2.4） ----------

/** 删除确认：输入去首尾空格后须等于资源名称（区分大小写；仅名称）。 */
export function resourceDeleteConfirmMatches(input: string, resource: { name: string }): boolean {
  const trimmed = input.trim()
  return trimmed !== '' && trimmed === resource.name
}

// ---------- 权限入口可见性（架构 §7.2；服务端为最终校验） ----------

/** 资源写操作（新增/编辑/删除）入口是否可见：仅 maintainer/admin；viewer 只读 */
export function canManageResources(role: Role | null | undefined): boolean {
  return role === 'maintainer' || role === 'admin'
}

// ---------- 网卡卡片状态与请求体映射（架构 §5.3 显式 op） ----------

/** 表单内网卡卡片：id=null 为新增网卡；removed 标记编辑时「将删除」（可恢复） */
export interface InterfaceCard {
  /** 表单内稳定 key（错误定位用） */
  key: string
  /** 既有网卡 ID；null = 新增网卡 */
  id: number | null
  name: string
  /** 关联网段（0..1）；null = 未选 */
  segmentId: number | null
  /** 编辑加载时的原值（新增卡片为 ''） */
  originalName: string
  /** 编辑加载时的原值 */
  originalSegmentId: number | null
  /** 编辑时标记删除：提交映射 op:'delete'；未列入提交 = 未修改 */
  removed: boolean
}

/** 编辑提交的网卡显式操作构建结果：ops 与 cardKeys 按下标一一对应
 * （errors[].field 的 interfaces[i] 定位回第 i 个操作所属的卡片） */
export interface InterfaceOpsBuild {
  ops: NetworkInterfaceOpItem[]
  cardKeys: string[]
}

/**
 * 编辑提交的网卡显式操作（架构 §5.3、Contract §2.3）：
 * - 标记删除的既有网卡 → { op:'delete', id }；
 * - 有变化的既有网卡（名称或网段，按去首尾空格口径比较）→ { op:'update', id, ...仅变化字段 }
 *   （segment_id 变化时显式传值或 null=清空）；
 * - 新增网卡 → { op:'create', name, segment_id }；
 * - 未修改的既有网卡不列入（= 未修改）。
 * 返回空数组时调用方应省略 interfaces 字段（缺省 = 不改动网卡）。
 */
export function buildInterfaceOps(cards: InterfaceCard[]): InterfaceOpsBuild {
  const ops: NetworkInterfaceOpItem[] = []
  const cardKeys: string[] = []
  for (const card of cards) {
    if (card.id !== null && card.removed) {
      ops.push({ op: 'delete', id: card.id })
      cardKeys.push(card.key)
      continue
    }
    if (card.id === null) {
      ops.push({ op: 'create', name: card.name, segment_id: card.segmentId })
      cardKeys.push(card.key)
      continue
    }
    const nameChanged = card.name.trim() !== card.originalName
    const segmentChanged = card.segmentId !== card.originalSegmentId
    if (!nameChanged && !segmentChanged) continue // 未修改：不列入 interfaces[]
    const op: NetworkInterfaceOpItem = { op: 'update', id: card.id }
    if (nameChanged) op.name = card.name
    if (segmentChanged) op.segment_id = card.segmentId
    ops.push(op)
    cardKeys.push(card.key)
  }
  return { ops, cardKeys }
}

/** 新增提交的网卡列表构建结果（items 与 cardKeys 按下标一一对应） */
export interface InterfaceItemsBuild {
  items: NetworkInterfaceCreateItem[]
  cardKeys: string[]
}

/** 新增提交的网卡项（Contract §2.1 NetworkInterfaceCreate[]；新增模式无 removed 概念，
 * 删除卡片即从列表移除）。空数组 = 无网卡（interfaces 省略）。 */
export function buildCreateInterfaceItems(cards: InterfaceCard[]): InterfaceItemsBuild {
  const items: NetworkInterfaceCreateItem[] = []
  const cardKeys: string[] = []
  for (const card of cards) {
    if (card.removed) continue
    items.push({ name: card.name, segment_id: card.segmentId })
    cardKeys.push(card.key)
  }
  return { items, cardKeys }
}

// ---------- errors[] → 表单字段与网卡卡片定位（§7.3 错误定位到具体字段和记录） ----------

/** 单张网卡的错误槽位 */
export interface InterfaceCardErrors {
  name: string
  segment_id: string
  /** 其它网卡级错误（如 interfaces[0].op / interfaces[0].id / INTERFACE_NOT_FOUND） */
  other: string
}

/** 表单错误集合：字段级 + 网卡卡片级（按卡片 key）+ 记录级 */
export interface ResourceFormErrors {
  name: string
  resource_type: string
  status: string
  cluster_id: string
  cards: Record<string, InterfaceCardErrors>
  /** 无法定位到字段/卡片的记录级错误文案 */
  general: string[]
}

export function emptyResourceFormErrors(): ResourceFormErrors {
  return { name: '', resource_type: '', status: '', cluster_id: '', cards: {}, general: [] }
}

/** errors[].field 的网卡下标定位（如 interfaces[1].name → ['1','name']） */
const INTERFACE_FIELD_PATTERN = /^interfaces\[(\d+)\]\.(.+)$/

/** 仅按 errors[].code 兜底定位（field 缺失/无法解析时） */
const CODE_FIELD_FALLBACKS: Record<string, 'name' | 'resource_type' | 'status' | 'cluster_id'> = {
  NAME_FORMAT: 'name',
  RESOURCE_TYPE_INVALID: 'resource_type',
  RESOURCE_TYPE_IMMUTABLE: 'resource_type',
  STATUS_INVALID: 'status',
  RESOURCE_CLUSTER_IMMUTABLE: 'cluster_id',
}

/**
 * 解析 problem+json errors[]（400 INVALID_REQUEST / 422 VALIDATION_ERROR）：
 * - interfaces[i].name / .segment_id / 其它子字段 → 按 cardKeys[i] 定位到具体网卡卡片；
 * - name / resource_type / status / cluster_id → 表单字段；
 * - field 缺失时按 code 兜底定位；其余归入 general（记录级提示）。
 * message 一律透传服务端文案（§9.4 错误指出具体字段和冲突对象）。
 */
export function parseResourceFieldErrors(errors: FieldError[], cardKeys: string[]): ResourceFormErrors {
  const result = emptyResourceFormErrors()
  for (const error of errors) {
    const message = error.message || error.code
    const indexed = INTERFACE_FIELD_PATTERN.exec(error.field)
    if (indexed !== null) {
      const index = Number(indexed[1])
      const subField = indexed[2]
      const cardKey = cardKeys[index]
      if (cardKey !== undefined) {
        const card = result.cards[cardKey] ?? { name: '', segment_id: '', other: '' }
        if (subField === 'name') card.name = message
        else if (subField === 'segment_id') card.segment_id = message
        else card.other = message
        result.cards[cardKey] = card
        continue
      }
      // 下标越界（不应发生）：归入记录级
      result.general.push(message)
      continue
    }
    if (error.field === 'name' || error.field === 'resource_type' || error.field === 'status' || error.field === 'cluster_id') {
      result[error.field] = message
      continue
    }
    const fallback = CODE_FIELD_FALLBACKS[error.code]
    if (fallback !== undefined && result[fallback] === '') {
      result[fallback] = message
      continue
    }
    result.general.push(message)
  }
  return result
}

// ---------- 服务端错误码 → 用户提示（409/400/422 记录级，Contract §0） ----------

const RESOURCE_CONFLICT_MESSAGES: Record<string, string> = {
  RESOURCE_NAME_EXISTS: '该集群已存在同名仍存资源（去首尾空格、区分大小写）；跨集群允许同名',
  INTERFACE_NAME_TAKEN: '同一资源下已存在该接口名（去首尾空格、区分大小写）',
  RESOURCE_HAS_INTERFACES: '该资源仍有网卡未删除：须先在编辑表单中逐项删除全部网卡并保存，才能删除资源',
  VERSION_CONFLICT: '该资源已被其他人修改（并发冲突），请刷新确认后重试',
  DELETE_CONFIRMATION_MISMATCH: '确认输入与资源名称不匹配（资源可能已被其他人修改），未执行删除',
  RESOURCE_TYPE_IMMUTABLE: '资源类型创建后不可修改',
  RESOURCE_CLUSTER_IMMUTABLE: '所属集群创建后不可修改',
  NO_FIELDS: '没有可保存的修改',
  INVALID_INTERFACE_OP: '网卡操作类型非法（仅允许 create / update / delete）',
  RESOURCE_NOT_FOUND: '该资源不存在或已被删除',
  CLUSTER_NOT_FOUND: '所选集群不存在，请重新选择集群',
}

/** 记录级错误码 → 用户提示文案；无映射返回 undefined（按通用错误处理） */
export function resourceConflictMessage(code: string): string | undefined {
  return RESOURCE_CONFLICT_MESSAGES[code]
}
