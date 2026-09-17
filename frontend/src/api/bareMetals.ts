/**
 * BareMetal 产品 API 客户端。
 *
 * 契约依据：docs/api/f002-bare-metal.md（READY，唯一权威）。
 * - 字段集合封闭（契约 §2）：恰为 13 字段；不存在 deleted_at、位置 / 上级字段、
 *   NIC / IP / VM / Container / Service 相关字段；
 * - 硬件七字段（R-BM-007）均为 string | null：未登记为 null，响应返回 null
 *   而非省略（api-conventions.md §4）；
 * - status 为封闭枚举 {IDLE, ALLOC, DOWN, UNKNOWN}（R-BM-003），永不为 null
 *   （R-BM-005）；本层不校验取值，合法性由服务端裁决（§21）；
 * - 时间字段为 RFC 3339 不透明字符串，不解析、不假设时区（契约 §2）；
 * - hostname 原样存取（契约 §7 undefined_constraints）：不 trim、不归一化、
 *   不假设非空、不做长度 / 字符 / 空串分支；
 * - 写操作一律走 id（ADR-0003）；错误语义由 api/http.ts 统一解析为 ApiError，
 *   消费方按 error.code 分支，不解析 message。
 * - F010（f010-resource-detail.md §2）：新增唯一只读聚合端点
 *   GET /api/bare-metals/{bare_metal_id}/related，一次返回五类关联；元素
 *   schema 复用各资源 canonical Read（本模块只引用，不另立一份）。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'
import type { ContainerRead } from './containers'
import type { IpAddressRead } from './ipAddresses'
import type { NetworkInterfaceRead } from './networkInterfaces'
import type { ServiceRead } from './services'
import type { VirtualMachineRead } from './virtualMachines'

/** BareMetal 状态封闭集合（R-BM-003；domain-model.md §7.1，仅 BareMetal 有状态）。 */
export type BareMetalStatus = 'IDLE' | 'ALLOC' | 'DOWN' | 'UNKNOWN'

/**
 * 状态取值列表（契约 §1 / R-BM-003）。
 * 仅作为 UI 选择项来源；取值合法性由服务端裁决，前端不做校验分支（§21）。
 */
export const BARE_METAL_STATUS_VALUES: readonly BareMetalStatus[] = [
  'IDLE',
  'ALLOC',
  'DOWN',
  'UNKNOWN',
]

/** BareMetal 资源表示（契约 §2；所有返回单对象的端点共用该结构）。 */
export interface BareMetalRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 所属 Cluster 的 id（R-BM-001，必属恰好一个 Cluster）。 */
  cluster_id: number
  /** 主机名，同 Cluster 内区分机器（R-BM-002）；原样存取（契约 §7）。 */
  hostname: string
  /** 状态（R-BM-003 封闭集合）；永不为 null（R-BM-005）。 */
  status: BareMetalStatus
  /** R-BM-007 硬件字段：可选、纯文本、未登记为 null。 */
  vendor: string | null
  model: string | null
  /** 序列号；不参与唯一性（R-BM-007）。 */
  serial_number: string | null
  cpu: string | null
  memory: string | null
  gpu: string | null
  storage: string | null
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/** R-BM-007 硬件字段键列表（登记 / 编辑表单与详情展示共用）。 */
export const BARE_METAL_HARDWARE_FIELDS = [
  'vendor',
  'model',
  'serial_number',
  'cpu',
  'memory',
  'gpu',
  'storage',
] as const

/** 硬件字段键（R-BM-007 七字段子集）。 */
export type BareMetalHardwareField = (typeof BARE_METAL_HARDWARE_FIELDS)[number]

/** 登记 BareMetal 请求体（契约 §3.1）。cluster_id + hostname 必填，其余可选。 */
export interface BareMetalCreateBody {
  /** 父 Cluster 的 id；必须存在且活跃（由服务端裁决，不存在 / 已删 → 404）。 */
  cluster_id: number
  /** 同 Cluster 内唯一、大小写敏感（由服务端裁决，重复 → 409）。 */
  hostname: string
  /**
   * 可选状态，缺省 IDLE（R-BM-004）。契约允许显式提供（NQ-3），当前 UI
   * 不提供该输入，登记一律走服务端默认。
   */
  status?: BareMetalStatus
  /** R-BM-007 字段：缺省 / null 均存为 null。 */
  vendor?: string | null
  model?: string | null
  serial_number?: string | null
  cpu?: string | null
  memory?: string | null
  gpu?: string | null
  storage?: string | null
}

/**
 * 更新 BareMetal 请求体（契约 §3.4，部分更新）。
 * 可变字段封闭为 status + R-BM-007 七字段；hostname / cluster_id 不可变
 * （NQ-1 未确认，F002 不提供），不得出现在请求体中。
 */
export interface BareMetalUpdateBody {
  /** 提供时必须在封闭集合内（由服务端裁决）；不得为 null（R-BM-005）。 */
  status?: BareMetalStatus
  /** 提供 null 表示清空该字段；缺省表示不修改。 */
  vendor?: string | null
  model?: string | null
  serial_number?: string | null
  cpu?: string | null
  memory?: string | null
  gpu?: string | null
  storage?: string | null
}

/** 列表查询参数（契约 §3.2）。 */
export interface BareMetalListParams extends PageParams {
  /** 按 Cluster 限定（R-CLUSTER-004 的 F002 侧）；未提供时返回全部活跃 BareMetal。 */
  clusterId?: number
}

/**
 * 列出活跃 BareMetal（契约 §3.2）。
 *
 * - 未提供 clusterId → 全部活跃 BareMetal；无活跃 → 200 + items == []（Empty）；
 * - 提供 clusterId → 该 Cluster 的活跃 BareMetal：Cluster 不存在或已逻辑删除 →
 *   404 NOT_FOUND（Not Found，与 Empty 是不同状态）；Cluster 存在但无活跃
 *   BareMetal → 200 + items == []（Empty）；
 * - 已逻辑删除的 BareMetal 不出现在 items / total（R-DELETE-002）。
 */
export function listBareMetals(
  params: BareMetalListParams = {},
): Promise<Paginated<BareMetalRead>> {
  return apiRequest<Paginated<BareMetalRead>>('/api/bare-metals', {
    method: 'GET',
    query: {
      page: params.page,
      page_size: params.page_size,
      cluster_id: params.clusterId,
    },
  })
}

/**
 * 按 id 读取 BareMetal（契约 §3.3，规范路径）。
 * 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分）。
 */
export function getBareMetal(bareMetalId: number): Promise<BareMetalRead> {
  return apiRequest<BareMetalRead>(`/api/bare-metals/${bareMetalId}`, { method: 'GET' })
}

/** 单一类别的关联集合（F010 契约 §2）：恰为 {items, total}，total == items.length。 */
export interface RelatedSet<T> {
  items: T[]
  total: number
}

/**
 * BareMetal 五类关联聚合结果（F010 契约 §2）。
 *
 * - 顶层字段集合封闭：恰为五类键，无其他资源字段；
 * - items 元素 schema **逐字段等于**对应 canonical Read：NetworkInterfaceRead /
 *   IpAddressRead（无 cluster_id）/ VirtualMachineRead / ContainerRead（载体以
 *   carrier_type + carrier_id 表达）/ ServiceRead（含 carriers）；
 * - 不存在 deleted_at、cluster_id、推导 Cluster 归属、状态 / 位置 / 发现字段
 *   （契约 §2 / §7）；各类 items 按 id 升序，已逻辑删除资源不出现也不计入 total；
 * - 非分页快照（契约 §7：不提供聚合级分页 / 排序 / 关键字）。
 */
export interface RelatedResources {
  /** 活跃 NIC 且 nic.bare_metal_id = B.id（1 跳）。 */
  network_interfaces: RelatedSet<NetworkInterfaceRead>
  /** 活跃 IP 且 ip.network_interface_id ∈ {B 的活跃 NIC}（2 跳；IP 无 bare_metal_id）。 */
  ip_addresses: RelatedSet<IpAddressRead>
  /** 活跃 VM 且 vm.bare_metal_id = B.id（1 跳）。 */
  virtual_machines: RelatedSet<VirtualMachineRead>
  /** 活跃 Container，载体为 B 或 B 的活跃 VM（1~2 跳，含间接；BQ-1 裁定）。 */
  containers: RelatedSet<ContainerRead>
  /** 活跃 Service，载体与 R(B) 有交集（1~3 跳，含间接；BQ-2 裁定；按 id 去重）。 */
  services: RelatedSet<ServiceRead>
}

/**
 * 读取 BareMetal 的五类关联聚合（F010 契约 §2，本 Feature 唯一新增端点，只读）。
 *
 * - 一次请求获得五类清单及每类空 / 非空（R-QUERY-003「一次获得、无需拼接」）；
 *   前端不得在浏览器端拼接 / 推导 IP / Container / Service 的关联
 *   （NQ-5 裁定 a1：单一聚合端点），一律消费本端点返回的五类清单；
 * - 主体 BareMetal 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分；五类
 *   共用同一 404 判定，任何一类为空绝不产生 404）；主体存在且活跃但某类
 *   （或全部类）无关联 → 200 且该类 { items: [], total: 0 }（Empty，不得
 *   渲染为错误，R-QUERY-004）；
 * - 401 UNAUTHENTICATED 由全局会话失效处理；其余错误按 error.code 分支，
 *   不解析 message；
 * - 无 query 参数、无请求体（契约 §2：客户端不得发送）。
 */
export function getBareMetalRelated(bareMetalId: number): Promise<RelatedResources> {
  return apiRequest<RelatedResources>(`/api/bare-metals/${bareMetalId}/related`, {
    method: 'GET',
  })
}

/**
 * 登记 BareMetal（契约 §3.1）。成功 → 201 + BareMetalRead。
 * 唯一性（409）、父 Cluster 存在性（404）、字段合法性（400）均由服务端裁决。
 */
export function createBareMetal(body: BareMetalCreateBody): Promise<BareMetalRead> {
  return apiRequest<BareMetalRead>('/api/bare-metals', {
    method: 'POST',
    body,
  })
}

/**
 * 更新状态 / 硬件字段（契约 §3.4，部分更新）。成功 → 200 + BareMetalRead。
 * 请求体至少含一个可变字段（空 body → 400）；hostname / cluster_id 不在可变集内。
 */
export function updateBareMetal(
  bareMetalId: number,
  body: BareMetalUpdateBody,
): Promise<BareMetalRead> {
  return apiRequest<BareMetalRead>(`/api/bare-metals/${bareMetalId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除 BareMetal（契约 §3.5）。
 *
 * - `DELETE /api/bare-metals/{bare_metal_id}`：写操作一律走 id；
 * - 成功 → 204（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - 404 NOT_FOUND：不存在或已被逻辑删除（两者不区分，重复删除亦 404）；
 * - 409 CONFLICT：存在活跃子资源（details[].code === 'ACTIVE_CHILDREN_EXIST'；
 *   当前 BareMetal 无子资源表，该分支在本 Feature 内不可达，由后续 Feature 触发）；
 * - 401 UNAUTHENTICATED：由全局会话失效处理；
 * - 不发送请求体（契约 §3.5：客户端不得发送）。
 */
export function deleteBareMetal(bareMetalId: number): Promise<void> {
  return apiRequest<void>(`/api/bare-metals/${bareMetalId}`, { method: 'DELETE' })
}
