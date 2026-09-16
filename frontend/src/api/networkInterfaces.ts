/**
 * NetworkInterface 产品 API 客户端。
 *
 * 契约依据：docs/api/f004-network-interface.md（READY，唯一权威）。
 * - 字段集合封闭（契约 §2）：恰为 7 字段；不存在 deleted_at、status（Q-002=B，
 *   NIC 不设状态）、cluster_id（Cluster 归属由宿主推导、不单独记录）、
 *   IP / MAC / 速率 / MTU / 光模块 / 端口号（§23 未确认字段）、
 *   vm_id / container_id / service_id / 载体类型选择器（NQ-1 未确认，不预留）；
 * - technology_type 封闭集合 Ethernet / InfiniBand / RoCE / Other（R-NIC-001）、
 *   purpose 封闭集合 BMC / Management / Business / Compute / Storage /
 *   DataTransfer / Other（R-NIC-002）；字面精确匹配，不做大小写折叠 / trim /
 *   归一 / 中文映射；本层的 OPTIONS 常量**仅用于下拉渲染**，不作为业务校验
 *   依据，取值合法性由服务端裁决（§21）；
 * - name 为必填登记字段，**无唯一性承诺**（NQ-2 未确认，契约不存在
 *   409 DUPLICATE 分支）；其长度 / 首尾空白 / 空字符串 / 非法字符等属
 *   未定义约束（契约 §7），原样存取，前端不做任何校验分支；
 * - 时间字段为 RFC 3339 不透明字符串，不解析、不假设时区（契约 §2）；
 * - 写操作一律走 id（ADR-0003）；不提供 by-name 别名（name 唯一性未确认）；
 *   PATCH 可变字段封闭为 technology_type / purpose（NQ-7），name /
 *   bare_metal_id 登记后不可变（NQ-3）；错误语义由 api/http.ts 统一解析为
 *   ApiError，消费方按 error.code 分支，不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** technology_type 封闭集合成员（R-NIC-001；契约 §3.1）。 */
export type NetworkInterfaceTechnologyType = 'Ethernet' | 'InfiniBand' | 'RoCE' | 'Other'

/** purpose 封闭集合成员（R-NIC-002；契约 §3.1）。 */
export type NetworkInterfacePurpose =
  | 'BMC'
  | 'Management'
  | 'Business'
  | 'Compute'
  | 'Storage'
  | 'DataTransfer'
  | 'Other'

/**
 * technology_type 下拉选项（R-NIC-001 封闭集合）。
 * **仅用于下拉渲染**，不作为业务校验依据；取值合法性由服务端裁决（§21）。
 */
export const TECHNOLOGY_TYPE_OPTIONS: readonly NetworkInterfaceTechnologyType[] = [
  'Ethernet',
  'InfiniBand',
  'RoCE',
  'Other',
]

/**
 * purpose 下拉选项（R-NIC-002 封闭集合）。
 * **仅用于下拉渲染**，不作为业务校验依据；取值合法性由服务端裁决（§21）。
 */
export const PURPOSE_OPTIONS: readonly NetworkInterfacePurpose[] = [
  'BMC',
  'Management',
  'Business',
  'Compute',
  'Storage',
  'DataTransfer',
  'Other',
]

/** NetworkInterface 资源表示（契约 §2；所有返回单对象的端点共用该结构）。 */
export interface NetworkInterfaceRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 宿主 BareMetal 的 id（R-NIC-003，必属恰好一个宿主）。 */
  bare_metal_id: number
  /** 接口名；原样存取，不做 trim / 归一化（契约 §7）；无唯一性承诺（NQ-2）。 */
  name: string
  /** 技术类型（R-NIC-001 封闭集合）。 */
  technology_type: NetworkInterfaceTechnologyType
  /** 用途（R-NIC-002 封闭集合）。 */
  purpose: NetworkInterfacePurpose
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/** 登记 NetworkInterface 请求体（契约 §3.1）。四字段均必填。 */
export interface NetworkInterfaceCreateBody {
  /** 宿主 BareMetal 的 id；必须存在且活跃（由服务端裁决，不存在 / 已删 → 404）。 */
  bare_metal_id: number
  /** 接口名；不做任何前端校验（契约 §7 未定义约束）；不校验唯一性（NQ-2）。 */
  name: string
  /** 必须逐字属于封闭集合（由服务端裁决）。 */
  technology_type: NetworkInterfaceTechnologyType
  /** 必须逐字属于封闭集合（由服务端裁决）。 */
  purpose: NetworkInterfacePurpose
}

/**
 * 更新 NetworkInterface 请求体（契约 §3.4，部分更新）。
 * 可变字段封闭为两个枚举（NQ-7）；id / bare_metal_id / name / created_at
 * 不可变（NQ-3），不得出现在请求体中。至少需包含一个可变字段（空 body → 400）。
 */
export interface NetworkInterfaceUpdateBody {
  /** 提供时必须在封闭集合内（由服务端裁决）；不得为 null。 */
  technology_type?: NetworkInterfaceTechnologyType
  /** 提供时必须在封闭集合内（由服务端裁决）；不得为 null。 */
  purpose?: NetworkInterfacePurpose
}

/** 列表查询参数（契约 §3.2）。 */
export interface NetworkInterfaceListParams extends PageParams {
  /**
   * 按宿主 BareMetal 限定（R-QUERY-003 的 F004 侧 canonical 能力，F010 复用，
   * 不得另写一份过滤）；未提供时返回全部活跃 NetworkInterface。
   */
  bareMetalId?: number
}

/**
 * 列出活跃 NetworkInterface（契约 §3.2）。
 *
 * - 未提供 bareMetalId → 全部活跃 NIC；无活跃 → 200 + items == []（Empty）；
 * - 提供 bareMetalId → 该宿主的活跃 NIC：宿主不存在或已逻辑删除 →
 *   404 NOT_FOUND（Not Found，与 Empty 是不同状态）；宿主存在但无活跃
 *   NIC → 200 + items == []（Empty）；
 * - 已逻辑删除的 NIC 不出现在 items / total（R-DELETE-002）。
 */
export function listNetworkInterfaces(
  params: NetworkInterfaceListParams = {},
): Promise<Paginated<NetworkInterfaceRead>> {
  return apiRequest<Paginated<NetworkInterfaceRead>>('/api/network-interfaces', {
    method: 'GET',
    query: {
      page: params.page,
      page_size: params.page_size,
      bare_metal_id: params.bareMetalId,
    },
  })
}

/**
 * 按 id 读取 NetworkInterface（契约 §3.3，规范路径）。
 * 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分）。
 */
export function getNetworkInterface(networkInterfaceId: number): Promise<NetworkInterfaceRead> {
  return apiRequest<NetworkInterfaceRead>(`/api/network-interfaces/${networkInterfaceId}`, {
    method: 'GET',
  })
}

/**
 * 登记 NetworkInterface（契约 §3.1）。成功 → 201 + NetworkInterfaceRead。
 * 宿主存在性 / 活跃性（404）、枚举与字段合法性（400）均由服务端裁决（§21）；
 * 同宿主同名登记不会被本契约拒绝（无唯一性规则，NQ-2）。
 */
export function createNetworkInterface(
  body: NetworkInterfaceCreateBody,
): Promise<NetworkInterfaceRead> {
  return apiRequest<NetworkInterfaceRead>('/api/network-interfaces', {
    method: 'POST',
    body,
  })
}

/**
 * 更新技术类型 / 用途（契约 §3.4，部分更新）。成功 → 200 + NetworkInterfaceRead。
 * 请求体至少含一个可变字段（空 body → 400）；name / bare_metal_id 不在可变集内。
 */
export function updateNetworkInterface(
  networkInterfaceId: number,
  body: NetworkInterfaceUpdateBody,
): Promise<NetworkInterfaceRead> {
  return apiRequest<NetworkInterfaceRead>(`/api/network-interfaces/${networkInterfaceId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除 NetworkInterface（契约 §3.5）。
 *
 * - `DELETE /api/network-interfaces/{network_interface_id}`：写操作一律走 id；
 * - 成功 → 204（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - 404 NOT_FOUND：不存在或已被逻辑删除（两者不区分，重复删除亦 404）；
 * - 409 CONFLICT：目标存在活跃子资源（details[].code === 'ACTIVE_CHILDREN_EXIST'；
 *   当前 ip_addresses 表尚不存在，该分支在本 Feature 内不可达，由 F005 落地
 *   IPAddress 后触发；**不得因此假定「NIC 永远无子资源」**）；
 * - 401 UNAUTHENTICATED：由全局会话失效处理；
 * - 不发送请求体（契约 §3.5：客户端不得发送）。
 */
export function deleteNetworkInterface(networkInterfaceId: number): Promise<void> {
  return apiRequest<void>(`/api/network-interfaces/${networkInterfaceId}`, { method: 'DELETE' })
}
