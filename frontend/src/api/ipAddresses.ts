/**
 * IPAddress 产品 API 客户端。
 *
 * 契约依据：docs/api/f005-ip-address.md（READY，唯一权威）；文末 F021 节的
 * 两个分配端点依据 docs/api/f021-ip-address-allocation.md（READY，唯一
 * 权威），不改变上方 F005 端点的任何语义。
 *
 * - 字段集合封闭（契约 §2）：恰为 5 字段；不存在 deleted_at（不对外暴露）、
 *   Cluster 归属字段（NQ-4 裁定：Cluster 归属是受控推导的反规范化内部值，
 *   请求侧永不被接受、响应侧不暴露；需要展示时沿既有端点链
 *   network_interface_id → 宿主 BareMetal → Cluster 只读取得，聚合呈现归
 *   F010）、状态字段（Q-002=B，IP 不设状态）、VRF / 网络命名空间维度
 *   （R-IP-003）、IP 池 / 网段 / DHCP / DNS / 自动发现 / 多态父载体字段
 *   （契约 §10）；
 * - ip_address 为字面值，**原样存取**：长度 / 首尾空白 / 空字符串 / IPv4 /
 *   IPv6 格式 / CIDR 语义 / 大小写折叠 / Unicode 归一化均属未定义约束
 *   （契约 §7）。本模块**不提供**任何 IP 格式校验 / 归一化 / 去除空白 /
 *   唯一性预检辅助函数：字段合法性与同 Cluster 唯一性由服务端裁决（§21），
 *   前端不得重复实现业务守卫，也不得基于未定义项编写业务分支；
 * - IPAddress 必属恰好一个 NetworkInterface（N:1 Mandatory，2026-09-15 用户
 *   裁定，不存在无主 IP）；父绑定 network_interface_id 登记后不可变
 *   （NQ-2 未确认 → 不提供变更）；PATCH 可变字段封闭为 {ip_address}
 *   （契约 §3.4，恰此一个）；
 * - 时间字段为 RFC 3339 不透明字符串，不解析、不假设时区（契约 §2）；
 * - 写操作一律走 id（ADR-0003）；不提供 by-name 别名（ip_address 仅按
 *   Cluster 唯一、不是全局唯一，契约 §1.11）；错误语义由 api/http.ts 统一
 *   解析为 ApiError，消费方按 error.code（必要时结合 details[].code）分支，
 *   不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** IPAddress 资源表示（契约 §2；所有返回单对象的端点共用该结构）。 */
export interface IpAddressRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 直接父 NetworkInterface 的 id（N:1 Mandatory，恰好一个父；登记后不可变）。 */
  network_interface_id: number
  /** IP 地址字面值（示例 10.0.1.1/16）；原样存取，不做任何变换（契约 §7）。 */
  ip_address: string
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/** 登记 IPAddress 请求体（契约 §3.1）。恰为 2 字段，均必填；请求 schema 封闭。 */
export interface IpAddressCreateBody {
  /** 直接父 NIC 的 id；必须存在且活跃且其宿主 BareMetal 活跃（由服务端裁决，
   * 不存在 / 已删 → 404 NOT_FOUND）。 */
  network_interface_id: number
  /** IP 地址字面值；不做任何前端校验（契约 §7 未定义约束）；同 Cluster 唯一性
   * 由服务端裁决（409 CONFLICT + details[].code === 'DUPLICATE'，§21）。 */
  ip_address: string
}

/**
 * 修正 IPAddress 请求体（契约 §3.4，部分更新）。
 * 可变字段封闭为 {ip_address}（恰此一个）；id / network_interface_id /
 * created_at 不可变，不得出现在请求体中。至少需包含一个可变字段
 * （空 body → 400）；ip_address 提供时不得为 null（null → 400）。
 */
export interface IpAddressUpdateBody {
  /** 新字面值；原样提交，不做任何变换；修正后唯一性由服务端重新裁决。 */
  ip_address?: string
}

/** 列表查询参数（契约 §3.2）。 */
export interface IpAddressListParams extends PageParams {
  /**
   * 按父 NIC 限定（R-QUERY-004 的 F005 侧 canonical 能力，F010 复用、不得
   * 另写一份过滤）；未提供时返回全部活跃 IPAddress。
   */
  networkInterfaceId?: number
}

/**
 * 列出活跃 IPAddress（契约 §3.2）。
 *
 * - 未提供 networkInterfaceId → 全部活跃 IP；无活跃 → 200 + items == []
 *   （Empty，不得 404）；
 * - 提供 networkInterfaceId → 该父 NIC 的活跃 IP：父 NIC 不存在或已逻辑删除
 *   → 404 NOT_FOUND（Not Found，与 Empty 是不同状态，R-QUERY-004）；父 NIC
 *   存在但无活跃 IP → 200 + items == []（Empty）；
 * - 已逻辑删除的 IP 不出现在 items / total（R-DELETE-002）；
 * - items 按 id 升序；total 为活跃数（受过滤时为该过滤域内活跃数）。
 */
export function listIpAddresses(
  params: IpAddressListParams = {},
): Promise<Paginated<IpAddressRead>> {
  return apiRequest<Paginated<IpAddressRead>>('/api/ip-addresses', {
    method: 'GET',
    query: {
      page: params.page,
      page_size: params.page_size,
      network_interface_id: params.networkInterfaceId,
    },
  })
}

/**
 * 按 id 读取 IPAddress（契约 §3.3）。
 * 不存在或已被逻辑删除 → 404 NOT_FOUND（两者不区分，契约 §9）。
 */
export function getIpAddress(ipAddressId: number): Promise<IpAddressRead> {
  return apiRequest<IpAddressRead>(`/api/ip-addresses/${ipAddressId}`, { method: 'GET' })
}

/**
 * 登记 IPAddress（契约 §3.1）。成功 → 201 + IpAddressRead。
 * 父 NIC 存在性 / 活跃性（404）、字段合法性（400，含请求携带未识别字段）、
 * 同 Cluster 唯一性（409 CONFLICT + details[].code === 'DUPLICATE'）均由
 * 服务端裁决（§21）；前端不回填 Cluster 归属、不做唯一性预检、不预判父
 * NIC 状态、不禁用入口。
 */
export function createIpAddress(body: IpAddressCreateBody): Promise<IpAddressRead> {
  return apiRequest<IpAddressRead>('/api/ip-addresses', { method: 'POST', body })
}

/**
 * 修正 ip_address 字面值（契约 §3.4，部分更新）。成功 → 200 + IpAddressRead；
 * id / network_interface_id / created_at 保持不变。修正后的唯一性由服务端
 * 在目标 Cluster 内重新裁决（另一 Cluster 已占用而目标未占用 → 成功）；
 * 无并发控制（最后提交生效，updated_at 不是并发控制依据）。
 */
export function updateIpAddress(
  ipAddressId: number,
  body: IpAddressUpdateBody,
): Promise<IpAddressRead> {
  return apiRequest<IpAddressRead>(`/api/ip-addresses/${ipAddressId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除 IPAddress（契约 §3.5）。
 *
 * - `DELETE /api/ip-addresses/{ip_address_id}`：写操作一律走 id；
 * - 成功 → 204（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - 404 NOT_FOUND：不存在或已被逻辑删除（两者不区分，重复删除亦 404）；
 * - 契约 §3.5：V1 不存在 409 触发路径（IP 是叶子资源），但消费方
 *   **不得假定「IP 永远无子资源」**——删除守卫一律由后端裁决（§21），
 *   useResourceDelete 已按 error.code 通用分支；
 * - 401 UNAUTHENTICATED：由全局会话失效处理；
 * - 不发送请求体（契约 §3.5：客户端不得发送）。
 */
export function deleteIpAddress(ipAddressId: number): Promise<void> {
  return apiRequest<void>(`/api/ip-addresses/${ipAddressId}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// F021：IP 地址自动 / 手动分配（契约 docs/api/f021-ip-address-allocation.md，
// READY）。分配不是独立领域对象：唯一产物是创建一条 IPAddress（复用上方
// F005 的 IpAddressRead 表示）；每次分配恰指定一个活跃 NetworkInterface，
// Cluster 归属由 NIC 经既有推导链受控推导（请求与响应均不含该内部值）。
// ---------------------------------------------------------------------------

/**
 * 自动分配请求体（F021 契约 §3.1）。恰为 1 字段；请求 schema 封闭
 * （extra="forbid"），不接受 Cluster 归属、状态、模式、保留地址等任何
 * 未识别字段（→ 400 VALIDATION_ERROR）。
 */
export interface IpAddressAutoAllocateBody {
  /** 目标 NIC 的 id；必须存在且活跃且其宿主 BareMetal 活跃（由服务端
   * 裁决，不命中 → 404 NOT_FOUND）。 */
  network_interface_id: number
}

/**
 * 手动分配请求体（F021 契约 §3.2）。恰为 2 字段；请求 schema 封闭
 * （extra="forbid"），不接受任何未识别字段（→ 400 VALIDATION_ERROR）。
 */
export interface IpAddressManualAllocateBody {
  /** 目标 NIC 的 id；语义同自动分配（存在性 / 活跃性由服务端裁决）。 */
  network_interface_id: number
  /** 手动指定的 IP 地址字面值。本客户端**不做**任何格式校验 / 修剪 /
   * 归一化（§21，业务裁决全在服务端）：非法 IPv4 → 400 VALIDATION_ERROR
   * （details[].field === 'ip_address'）；范围外 / 已占用 → 409 CONFLICT
   * （details[].code === 'OUT_OF_RANGE' / 'DUPLICATE'）。 */
  ip_address: string
}

/**
 * 自动分配 IP 地址（F021 契约 §3.1）。`POST /api/ip-addresses/allocate`。
 *
 * - 服务端在目标 Cluster 全部活跃范围段的并集内取数值最小的未占用 IPv4
 *  （跨范围段全局最小，无隐式保留地址），写入规范化 dotted-quad；
 * - 成功 → 201 + IpAddressRead（复用 F005 表示，恰 5 字段）；
 * - 404 NOT_FOUND：目标 NIC 不存在 / 已逻辑删除 / 宿主 BareMetal 不活跃
 *  （三者不区分）；
 * - 409 CONFLICT + details[].code === 'NO_AVAILABLE_IP'：并集耗尽（含该
 *  Cluster 无任何活跃范围段），不创建任何记录；
 * - 409 CONFLICT + details[].code === 'DUPLICATE'：并发选中同一地址的
 *  落败方（服务端不自动重试，可由用户重试）；
 * - 前端不预判地址池状态、不禁用入口（§21）。
 */
export function allocateIpAddress(body: IpAddressAutoAllocateBody): Promise<IpAddressRead> {
  return apiRequest<IpAddressRead>('/api/ip-addresses/allocate', { method: 'POST', body })
}

/**
 * 手动分配 IP 地址（F021 契约 §3.2）。
 * `POST /api/ip-addresses/allocate-manual`。
 *
 * - 成功 → 201 + IpAddressRead；ip_address 为服务端规范化后的 canonical
 *  dotted-quad（如 010.0.0.5 → 10.0.0.5），前端按响应值原样展示，
 *  不自行变换；
 * - 400 VALIDATION_ERROR：ip_address 非法 IPv4（10.0.0.256、10.0.0、abc、
 *  1.2.3.4/24、IPv6、空串、含空白等）等字段形状问题
 *  （details[].field === 'ip_address'）；
 * - 404 NOT_FOUND：目标 NIC 不存在 / 已删 / 宿主不活跃；
 * - 409 CONFLICT + details[].code === 'OUT_OF_RANGE'：合法 IPv4 但其数值
 *  不落在目标 Cluster 任何活跃范围段内；
 * - 409 CONFLICT + details[].code === 'DUPLICATE'：范围内但已被占用，
 *  或并发写入同一地址的落败方；
 * - 范围外字面值不经本端点：如需登记范围外任意字面 IP，仍走上方 F005
 *  既有 createIpAddress（不受本契约拦截）。
 */
export function allocateIpAddressManual(
  body: IpAddressManualAllocateBody,
): Promise<IpAddressRead> {
  return apiRequest<IpAddressRead>('/api/ip-addresses/allocate-manual', {
    method: 'POST',
    body,
  })
}
