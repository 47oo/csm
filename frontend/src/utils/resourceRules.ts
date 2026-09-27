// 计算资源（F002+F006）表单校验、网卡/IP op 映射、管理 IP 候选、错误定位与提示文案：
// 与 Contract docs/api/F002.md §0/§1/§2、docs/api/F006.md §0/§1/§2/§3、
// 架构 F002 §2.4/§4/§5/§6、F006 §2.4/§4/§5、
// 需求 §4.1–§4.5/§6.4/§7 及 BQ-AA/BQ-W/BQ-Z 一致。
// 前端校验仅用于即时反馈（§7.2）；唯一性、归属关系、权限、并发、自动分配可用性由服务端最终保证。
// 422/400 字段级错误（errors[].code：NAME_FORMAT/RESOURCE_TYPE_INVALID/STATUS_INVALID/
// INTERFACE_NAME_FORMAT/INTERFACE_NAME_DUPLICATE_IN_PAYLOAD/INTERFACE_NOT_FOUND/
// INTERFACE_SEGMENT_INVALID/INTERFACE_SEGMENT_CLUSTER_MISMATCH/RESOURCE_TYPE_IMMUTABLE/
// RESOURCE_CLUSTER_IMMUTABLE/NO_FIELDS/INVALID_INTERFACE_OP；F006 增：IP_OUT_OF_SEGMENT/
// IP_RESERVED/IP_GATEWAY/IP_NETWORK_ADDRESS/IP_BROADCAST_ADDRESS/SEGMENT_NOT_SELECTED/
// AUTO_RANGE_NOT_ENABLED/IP_NOT_FOUND）透传服务端 message 呈现，
// 此处负责把它们定位到表单字段、具体网卡卡片与具体 IP（interfaces[i].ips[j]，§7.3）。

import type { FieldError, Role } from '../api/types'
import type {
  IpCreateItem,
  IpOpItem,
  NetworkInterfaceCreateItem,
  NetworkInterfaceOpItem,
  ResourceStatus,
  ResourceType,
} from '../api/resources'
import { ipv4ToInt, parseIpv4Cidr, ipIntInCidr } from './ip'

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

/** 手动分配 IPv4：合法点分十进制（严格格式，与服务端口径一致；不做 trim） */
export const IP_ADDRESS_RULE_MESSAGE = '请输入合法 IPv4 地址（点分十进制，每段 0–255）'

export function validateIpv4Address(value: string): string | null {
  if (value.trim() === '' || ipv4ToInt(value.trim()) === null) return IP_ADDRESS_RULE_MESSAGE
  return null
}

/** 手动分配地址须落在所选网段 CIDR 内（本机客户端判断；服务端权威，场景 11/20）。
 * CIDR 未知（编辑兑底摘要缺失）时返回 null，交由服务端判定。 */
export const IP_OUT_OF_SEGMENT_RULE_MESSAGE = '地址不在所选网段 CIDR 内，请确认后重新输入'

export function validateIpInSegment(address: string, cidr: string | null | undefined): string | null {
  if (cidr === null || cidr === undefined || cidr === '') return null
  const parsedCidr = parseIpv4Cidr(cidr)
  if (parsedCidr === null) return null
  const ipInt = ipv4ToInt(address.trim())
  if (ipInt === null) return null // 语法错误已由 validateIpv4Address 呈现
  if (!ipIntInCidr(ipInt, parsedCidr)) return IP_OUT_OF_SEGMENT_RULE_MESSAGE
  return null
}

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

// ---------- 网卡卡片与 IP 条目状态、请求体映射（架构 F002 §5.3 + F006 §5.1 显式 op） ----------

/** 表单内网卡 IP 条目（F006）：id=null 为本次新增（提交映射 op:'create'）；
 * 既有 IP 标记 removed（提交映射 op:'delete'）；未列出=未修改；IP 不可改地址 */
export interface InterfaceIpItem {
  /** 表单内稳定 key（错误定位用） */
  key: string
  /** 既有 IP ID；null = 本次新增 */
  id: number | null
  /** 本次新增的分配方式（既有 IP 无意义）；auto 提交后由服务端选址 */
  mode: 'manual' | 'auto'
  /** 既有 IP 的规范化地址；新增 manual 为用户输入；新增 auto 为 ''（提交后回填） */
  address: string
  /** 既有 IP 分配时所选网段 ID（回显用；新增条目随网卡当前网段） */
  segmentId: number | null
  /** 编辑时标记删除（提交映射 op:'delete'）；新增条目直接移除卡片内条目 */
  removed: boolean
}

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
  /** IP 条目（既有回显 + 待分配；F006） */
  ips: InterfaceIpItem[]
}

/** 编辑提交的网卡显式操作构建结果：ops 与 cardKeys 按下标一一对应
 * （errors[].field 的 interfaces[i] 定位回第 i 个操作所属的卡片；
 * ipKeys[i] 与 ops[i].ips 下标一一对应，供 interfaces[i].ips[j] 定位与管理 IP
 * interface_index 解析） */
export interface InterfaceOpsBuild {
  ops: NetworkInterfaceOpItem[]
  cardKeys: string[]
  /** 与 ops[i].ips 下标一一对应的 IP 表单 key */
  ipKeys: string[][]
}

/** 卡片的 IP 显式操作（含下标对齐）：
 * - 既有标记删除 → { op:'delete', id }（仅编辑模式）；
 * - 新增条目 → 编辑：{ op:'create', mode, address? }；新增模式：{ mode, address? }（无 op 字段）；
 * - 既有未标记删除的 IP 不列入（= 未修改）。 */
function buildCardIpOps(card: InterfaceCard): {
  ops: IpOpItem[]
  creates: IpCreateItem[]
  keys: string[]
} {
  const ops: IpOpItem[] = []
  const creates: IpCreateItem[] = []
  const keys: string[] = []
  for (const ip of card.ips) {
    if (ip.id !== null && (ip.removed || card.removed)) {
      ops.push({ op: 'delete', id: ip.id })
      keys.push(ip.key)
      continue
    }
    if (ip.id === null && !card.removed) {
      if (ip.mode === 'manual') {
        ops.push({ op: 'create', mode: 'manual', address: ip.address.trim() })
        creates.push({ mode: 'manual', address: ip.address.trim() })
      } else {
        ops.push({ op: 'create', mode: 'auto' })
        creates.push({ mode: 'auto' })
      }
      keys.push(ip.key)
    }
  }
  return { ops, creates, keys }
}

/** 卡片是否有 IP 变更（决定未改名/未改网段的既有网卡是否需要 op:'update'） */
function cardHasIpOps(card: InterfaceCard): boolean {
  return (
    card.ips.some((ip) => (ip.id !== null && ip.removed) || ip.id === null) || card.removed
  )
}

/**
 * 编辑提交的网卡显式操作（架构 F005.3、Contract F002 §2.3 + F006 §2.3）：
 * - 标记删除的既有网卡 → { op:'delete', id, ips? }（同项携带其既有 IP 显式删除，
 *   否则服务端 INTERFACE_HAS_IPS；新增条目随卡片取消不提交）；
 * - 有变化的既有网卡（名称/网段变化，或有 IP 增/删）→ { op:'update', id, ...仅变化字段, ips? }；
 * - 新增网卡 → { op:'create', name, segment_id, ips? }；
 * - 未修改的既有网卡不列入（= 未修改；其既有 IP 未列入 ips 同样=未修改）。
 * 返回空数组时调用方应省略 interfaces 字段（缺省 = 不改动网卡）。
 */
export function buildInterfaceOps(cards: InterfaceCard[]): InterfaceOpsBuild {
  const ops: NetworkInterfaceOpItem[] = []
  const cardKeys: string[] = []
  const ipKeys: string[][] = []
  for (const card of cards) {
    const { ops: ipOps, keys } = buildCardIpOps(card)
    if (card.id !== null && card.removed) {
      ops.push(
        ipOps.length > 0
          ? { op: 'delete', id: card.id, ips: ipOps }
          : { op: 'delete', id: card.id },
      )
      cardKeys.push(card.key)
      ipKeys.push(keys)
      continue
    }
    if (card.id === null) {
      ops.push(
        ipOps.length > 0
          ? { op: 'create', name: card.name, segment_id: card.segmentId, ips: ipOps }
          : { op: 'create', name: card.name, segment_id: card.segmentId },
      )
      cardKeys.push(card.key)
      ipKeys.push(keys)
      continue
    }
    const nameChanged = card.name.trim() !== card.originalName
    const segmentChanged = card.segmentId !== card.originalSegmentId
    if (!nameChanged && !segmentChanged && !cardHasIpOps(card)) continue // 未修改：不列入 interfaces[]
    const op: NetworkInterfaceOpItem = { op: 'update', id: card.id }
    if (nameChanged) op.name = card.name
    if (segmentChanged) op.segment_id = card.segmentId
    if (ipOps.length > 0) op.ips = ipOps
    ops.push(op)
    cardKeys.push(card.key)
    ipKeys.push(keys)
  }
  return { ops, cardKeys, ipKeys }
}

/** 新增提交的网卡列表构建结果（items 与 cardKeys 按下标一一对应；ipKeys 同上） */
export interface InterfaceItemsBuild {
  items: NetworkInterfaceCreateItem[]
  cardKeys: string[]
  /** 与 items[i].ips 下标一一对应的 IP 表单 key */
  ipKeys: string[][]
}

/** 新增提交的网卡项（Contract §2.1 NetworkInterfaceCreate[] + F006 ips；新增模式无 removed
 * 概念，删除卡片即从列表移除）。空数组 = 无网卡（interfaces 省略）。 */
export function buildCreateInterfaceItems(cards: InterfaceCard[]): InterfaceItemsBuild {
  const items: NetworkInterfaceCreateItem[] = []
  const cardKeys: string[] = []
  const ipKeys: string[][] = []
  for (const card of cards) {
    if (card.removed) continue
    const { creates, keys } = buildCardIpOps(card)
    items.push(
      creates.length > 0
        ? { name: card.name, segment_id: card.segmentId, ips: creates }
        : { name: card.name, segment_id: card.segmentId },
    )
    cardKeys.push(card.key)
    ipKeys.push(keys)
  }
  return { items, cardKeys, ipKeys }
}

// ---------- errors[] → 表单字段与网卡卡片/IP 定位（§7.3 错误定位到具体字段和记录） ----------

/** 单个 IP 条目的错误槽位 */
export interface InterfaceIpErrors {
  address: string
  /** 其它 IP 级错误（如 interfaces[0].ips[1].op / .id / .mode / AUTO_RANGE_NOT_ENABLED） */
  other: string
}

/** 单张网卡的错误槽位 */
export interface InterfaceCardErrors {
  name: string
  segment_id: string
  /** 其它网卡级错误（如 interfaces[0].op / interfaces[0].id / INTERFACE_NOT_FOUND） */
  other: string
  /** IP 条目级错误（按 IP 表单 key；F006 interfaces[i].ips[j].xxx） */
  ips: Record<string, InterfaceIpErrors>
}

/** 表单错误集合：字段级 + 网卡卡片级（按卡片 key）+ 记录级 */
export interface ResourceFormErrors {
  name: string
  resource_type: string
  status: string
  cluster_id: string
  /** 管理 IP 字段错误（MANAGEMENT_IP_REQUIRED / MANAGEMENT_IP_INVALID 等，F006） */
  management_ip: string
  cards: Record<string, InterfaceCardErrors>
  /** 无法定位到字段/卡片的记录级错误文案 */
  general: string[]
}

export function emptyResourceFormErrors(): ResourceFormErrors {
  return {
    name: '',
    resource_type: '',
    status: '',
    cluster_id: '',
    management_ip: '',
    cards: {},
    general: [],
  }
}

export function emptyInterfaceCardErrors(): InterfaceCardErrors {
  return { name: '', segment_id: '', other: '', ips: {} }
}

/** errors[].field 的网卡下标定位（如 interfaces[1].name → ['1','name']） */
const INTERFACE_FIELD_PATTERN = /^interfaces\[(\d+)\]\.(.+)$/

/** errors[].field 的网卡 IP 下标定位（如 interfaces[1].ips[0].address；裸 ips[0] 也匹配） */
const INTERFACE_IP_FIELD_PATTERN = /^interfaces\[(\d+)\]\.ips\[(\d+)\](?:\.(.+))?$/

/** 仅按 errors[].code 兜底定位（field 缺失/无法解析时） */
const CODE_FIELD_FALLBACKS: Record<
  string,
  'name' | 'resource_type' | 'status' | 'cluster_id' | 'management_ip'
> = {
  NAME_FORMAT: 'name',
  RESOURCE_TYPE_INVALID: 'resource_type',
  RESOURCE_TYPE_IMMUTABLE: 'resource_type',
  STATUS_INVALID: 'status',
  RESOURCE_CLUSTER_IMMUTABLE: 'cluster_id',
  MANAGEMENT_IP_REQUIRED: 'management_ip',
  MANAGEMENT_IP_INVALID: 'management_ip',
}

/**
 * 解析 problem+json errors[]（400 INVALID_REQUEST / 422 VALIDATION_ERROR / 409 IP 冲突）：
 * - interfaces[i].ips[j].address / .op / .id / .mode / 裸 ips[j] → 按 cardKeys[i] +
 *   ipKeys[i][j] 定位到具体网卡卡片的具体 IP 条目；
 * - interfaces[i].name / .segment_id / 其它子字段 → 按 cardKeys[i] 定位到具体网卡卡片；
 * - name / resource_type / status / cluster_id / management_ip → 表单字段；
 * - field 缺失时按 code 兜底定位；其余归入 general（记录级提示）。
 * message 一律透传服务端文案（§9.4 错误指出具体字段和冲突对象）。
 */
export function parseResourceFieldErrors(
  errors: FieldError[],
  cardKeys: string[],
  ipKeys: string[][] = [],
): ResourceFormErrors {
  const result = emptyResourceFormErrors()
  for (const error of errors) {
    const message = error.message || error.code
    const ipIndexed = INTERFACE_IP_FIELD_PATTERN.exec(error.field)
    if (ipIndexed !== null) {
      const cardKey = cardKeys[Number(ipIndexed[1])]
      const ipKey =
        cardKey === undefined
          ? undefined
          : ipKeys[Number(ipIndexed[1])]?.[Number(ipIndexed[2])]
      if (cardKey !== undefined && ipKey !== undefined) {
        const card = result.cards[cardKey] ?? emptyInterfaceCardErrors()
        const ip = card.ips[ipKey] ?? { address: '', other: '' }
        // 裸 ips[j]（无子字段，如 AUTO_RANGE_NOT_ENABLED / NO_AVAILABLE_ADDRESS）为条目级错误 → other
        if (ipIndexed[3] === 'address') ip.address = message
        else ip.other = message
        card.ips[ipKey] = ip
        result.cards[cardKey] = card
        continue
      }
      // 下标越界（不应发生）：归入记录级
      result.general.push(message)
      continue
    }
    const indexed = INTERFACE_FIELD_PATTERN.exec(error.field)
    if (indexed !== null) {
      const index = Number(indexed[1])
      const subField = indexed[2]
      const cardKey = cardKeys[index]
      if (cardKey !== undefined) {
        const card = result.cards[cardKey] ?? emptyInterfaceCardErrors()
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
    if (
      error.field === 'name' ||
      error.field === 'resource_type' ||
      error.field === 'status' ||
      error.field === 'cluster_id' ||
      error.field === 'management_ip'
    ) {
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

// ---------- 同表单重复 IP（§7.2 前端基础校验；唯一性由服务端最终保证） ----------

export const IP_DUPLICATE_MESSAGE =
  '同一表单内 IP 重复；同集群内有效 IP 全局唯一，请修改后重新提交'

/** 收集本表单将保存的全部 IP 地址（既有未删 + 待分配 manual；auto 地址未定不参与），
 * 返回重复地址涉及的 IP 条目 key 集合（含首个与后续重复项）。 */
export function findDuplicateIpKeys(cards: InterfaceCard[]): Set<string> {
  const firstByAddress = new Map<string, string>()
  const duplicated = new Set<string>()
  for (const card of cards) {
    if (card.removed) continue
    for (const ip of card.ips) {
      if (ip.removed) continue
      if (ip.id === null && ip.mode !== 'manual') continue // auto 地址未定，不参与判重
      const address = ip.address.trim()
      if (address === '') continue
      const first = firstByAddress.get(address)
      if (first === undefined) {
        firstByAddress.set(address, ip.key)
      } else {
        duplicated.add(first)
        duplicated.add(ip.key)
      }
    }
  }
  return duplicated
}

// ---------- 服务端错误码 → 用户提示（409/400/422 记录级，Contract §0 + F006 §0） ----------

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
  // ---- F006（Contract docs/api/F006.md §0） ----
  SEGMENT_NOT_SELECTED: '请先选择网段，再分配 IP（分配 IP 前必须选定网段）',
  AUTO_RANGE_NOT_ENABLED: '该网段未启用自动分配范围，只能手动分配',
  IP_NOT_FOUND: '待删除的 IP 不属于该网卡/资源（可能已被其他人修改），请刷新后重试',
  INTERFACE_HAS_IPS: '该网卡仍有 IP 未删除：删除网卡前须先逐项删除其全部 IP',
  INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE:
    '该网卡已有 IP：改网段前须先删除（释放）其全部 IP，再在新网段重新分配',
  MANAGEMENT_IP_REQUIRED:
    '当前管理 IP 或其所属网卡将被删除：必须在同一次提交中显式清空或重选管理 IP，不会静默清空或改指',
  MANAGEMENT_IP_INVALID: '管理 IP 引用无效：须选择保存后仍属于本资源的有效网卡 IP',
  NO_AVAILABLE_ADDRESS:
    '当前网段自动分配范围内已无可用地址（不会自动切换其它网段）：可改用手动分配、扩大范围或先释放地址后重试',
}

/** 记录级错误码 → 用户提示文案；无映射返回 undefined（按通用错误处理） */
export function resourceConflictMessage(code: string): string | undefined {
  return RESOURCE_CONFLICT_MESSAGES[code]
}

// ---------- IP_ALREADY_IN_USE 冲突归属展示（Contract F006 §0 conflicts 扩展成员） ----------

/** conflicts 单项（Contract F006 §0：ip/resource_id/resource_name/interface_id/interface_name） */
export interface IpConflictItem {
  ip: string
  resource_id: number
  resource_name: string
  interface_id: number
  interface_name: string
}

/** 从 problem+json 扩展成员提取 conflicts（缺失/形状非法 → []，不伪装） */
export function readIpConflicts(extensions: Record<string, unknown>): IpConflictItem[] {
  const raw = extensions['conflicts']
  if (!Array.isArray(raw)) return []
  const result: IpConflictItem[] = []
  for (const item of raw) {
    if (item === null || typeof item !== 'object') continue
    const c = item as Record<string, unknown>
    if (
      typeof c['ip'] === 'string' &&
      typeof c['resource_name'] === 'string' &&
      typeof c['interface_name'] === 'string'
    ) {
      result.push({
        ip: c['ip'],
        resource_id: Number(c['resource_id']),
        resource_name: c['resource_name'],
        interface_id: Number(c['interface_id']),
        interface_name: c['interface_name'],
      })
    }
  }
  return result
}

/** conflicts → 「已被本集群 X/Y 使用」展示文案（§7.3 错误指出具体字段和冲突对象）；
 * 无冲突返回 '' */
export function ipConflictsNotice(conflicts: IpConflictItem[]): string {
  if (conflicts.length === 0) return ''
  const parts = conflicts.map((c) => `${c.ip} 已被本集群 ${c.resource_name}/${c.interface_name} 使用`)
  return parts.length === 1 ? parts[0]! : parts.join('；')
}
