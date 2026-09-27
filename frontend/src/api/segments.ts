// 网段 API（Contract docs/api/F005.md：网段列表/新增/详情/编辑/删除 +
// 保留地址列表/新增/删除 + 网关显式清空，共 9 端点）。
// 字段与错误语义严格按 Contract；401/403 全局处理（client 拦截），
// 409/422 由页面按 code/字段呈现（utils/segmentRules 的文案映射）。
import { client } from './client'

// ---------- Schema（Contract §1，唯一字段清单） ----------

/** 保留地址（Contract §1 ReservedAddress） */
export interface ReservedAddress {
  id: number
  /** 起始 IPv4（单个地址时等于 end_ip） */
  start_ip: string
  /** 结束 IPv4 */
  end_ip: string
  /** start_ip != end_ip */
  is_range: boolean
  created_at: string
}

/** 重叠提示（Contract §1 OverlapWarning；仅提示、允许保存） */
export interface OverlapWarning {
  segment_id: number
  name: string
  cidr: string
}

/** 网段列表项（Contract §1 NetworkSegmentListItem） */
export interface NetworkSegmentListItem {
  id: number
  cluster_id: number
  /** 所属集群展示编号（便利字段） */
  cluster_code: string
  /** 所属集群名称（便利字段） */
  cluster_name: string
  name: string
  /** 规范化 IPv4 CIDR */
  cidr: string
  purpose: string
  technology: string
  /** 未填为 null */
  vlan: number | null
  /** 未设为 null */
  gateway: string | null
  /** 未启用为 null */
  auto_alloc_start: string | null
  auto_alloc_end: string | null
  /** 两端是否均非空 */
  auto_alloc_enabled: boolean
  reserved_address_count: number
  /** F005 阶段恒为 0（F006 扩展） */
  allocated_count: number
  /** 可自动分配数量（§5 快照） */
  auto_assignable_count: number
  has_overlap: boolean
  created_at: string
  updated_at: string
}

/** 网段详情（= ListItem + version + 保留地址/重叠子项，Contract §1） */
export interface NetworkSegmentDetail extends NetworkSegmentListItem {
  /** 空为 [] */
  reserved_addresses: ReservedAddress[]
  /** 空为 [] */
  overlaps: OverlapWarning[]
  version: number
}

/** GET /network-segments 分页响应（Contract §1 PagedNetworkSegments） */
export interface PagedNetworkSegments {
  items: NetworkSegmentListItem[]
  total: number
  page: number
  page_size: number
}

/** GET .../reserved-addresses 响应（Contract §1 ReservedAddressList） */
export interface ReservedAddressList {
  items: ReservedAddress[]
}

// ---------- 请求类型（Contract §2/§3） ----------

/** 排序键（Contract §0/§2.1；默认 name） */
export type SegmentSort = 'name' | '-name' | 'cidr' | '-cidr' | 'created_at' | '-created_at'

/** 列表查询输入：q 允许空字符串（表示不过滤）；空项不发送；cluster_id 省略则跨集群返回 */
export interface SegmentListQueryInput {
  cluster_id?: number
  page?: number
  page_size?: number
  q?: string
  sort?: SegmentSort | ''
}

/** POST /network-segments 请求体（Contract §2.2） */
export interface SegmentCreatePayload {
  cluster_id: number
  name: string
  cidr: string
  purpose: string
  technology: string
  vlan?: number | null
  gateway?: string | null
  auto_alloc_start?: string | null
  auto_alloc_end?: string | null
}

/** PATCH /network-segments/{id} 请求体（Contract §2.4：省略=不修改；null=显式清空可空字段；
 * version 必填）。undefined 字段经 JSON 序列化自然省略。 */
export interface SegmentUpdatePayload {
  name?: string
  cidr?: string
  purpose?: string
  technology?: string
  vlan?: number | null
  gateway?: string | null
  auto_alloc_start?: string | null
  auto_alloc_end?: string | null
  version: number
}

/** DELETE /network-segments/{id} 查询参数（Contract §2.5：二次确认 + 乐观锁） */
export interface SegmentDeleteQuery {
  /** 去首尾空格后须等于网段名称（区分大小写，BQ-Z） */
  confirm: string
  version: number
}

/** POST .../reserved-addresses 请求体（Contract §3.2；end_ip 省略/null = 单地址） */
export interface ReservedAddressCreatePayload {
  start_ip: string
  end_ip?: string | null
}

// ---------- 端点（Contract §2/§3） ----------

/** GET /network-segments：分页/搜索/排序列表（Contract §2.1；空结果 items:[] + total:0；
 * cluster_id 不存在 → 200 空列表） */
export function listNetworkSegments(query: SegmentListQueryInput): Promise<PagedNetworkSegments> {
  const params: Record<string, string> = {}
  if (query.cluster_id !== undefined) params.cluster_id = String(query.cluster_id)
  if (query.page !== undefined) params.page = String(query.page)
  if (query.page_size !== undefined) params.page_size = String(query.page_size)
  if (query.q !== undefined && query.q.trim() !== '') params.q = query.q.trim()
  if (query.sort !== undefined && query.sort !== '') params.sort = query.sort
  return client.get<PagedNetworkSegments>('/network-segments', { params }).then((res) => res.data)
}

/** POST /network-segments：新增（201 → NetworkSegmentDetail，含 overlaps/has_overlap 与计数；
 * 409 SEGMENT_NAME_TAKEN/SEGMENT_CIDR_TAKEN、404 CLUSTER_NOT_FOUND 由页面提示） */
export function createNetworkSegment(payload: SegmentCreatePayload): Promise<NetworkSegmentDetail> {
  return client.post<NetworkSegmentDetail>('/network-segments', payload).then((res) => res.data)
}

/** GET /network-segments/{segment_id}：详情（含 version/保留地址/重叠，Contract §2.3） */
export function getNetworkSegment(segmentId: number): Promise<NetworkSegmentDetail> {
  return client.get<NetworkSegmentDetail>(`/network-segments/${segmentId}`).then((res) => res.data)
}

/** PATCH /network-segments/{segment_id}：编辑属性（乐观锁；CIDR 条件可变，Contract §2.4） */
export function updateNetworkSegment(
  segmentId: number,
  payload: SegmentUpdatePayload,
): Promise<NetworkSegmentDetail> {
  return client
    .patch<NetworkSegmentDetail>(`/network-segments/${segmentId}`, payload)
    .then((res) => res.data)
}

/** DELETE /network-segments/{segment_id}?confirm=&version=：真实删除
 * （二次确认 + 乐观锁 + 删除前置，Contract §2.5/BQ-Z） */
export function deleteNetworkSegment(segmentId: number, query: SegmentDeleteQuery): Promise<void> {
  return client
    .delete<void>(`/network-segments/${segmentId}`, { params: { confirm: query.confirm, version: query.version } })
    .then(() => undefined)
}

/** GET /network-segments/{segment_id}/reserved-addresses：保留地址列表（按 start_ip 升序） */
export function listReservedAddresses(segmentId: number): Promise<ReservedAddressList> {
  return client
    .get<ReservedAddressList>(`/network-segments/${segmentId}/reserved-addresses`)
    .then((res) => res.data)
}

/** POST /network-segments/{segment_id}/reserved-addresses：新增保留地址/范围
 * （Contract §3.2；end_ip 省略表示单地址） */
export function createReservedAddress(
  segmentId: number,
  payload: ReservedAddressCreatePayload,
): Promise<ReservedAddress> {
  const body: { start_ip: string; end_ip?: string } = { start_ip: payload.start_ip }
  if (payload.end_ip != null && payload.end_ip !== '') body.end_ip = payload.end_ip
  return client
    .post<ReservedAddress>(`/network-segments/${segmentId}/reserved-addresses`, body)
    .then((res) => res.data)
}

/** DELETE /network-segments/{segment_id}/reserved-addresses/{reserved_id}：删除单条保留地址
 * （逐条真实删除，Contract §3.3） */
export function deleteReservedAddress(segmentId: number, reservedId: number): Promise<void> {
  return client
    .delete<void>(`/network-segments/${segmentId}/reserved-addresses/${reservedId}`)
    .then(() => undefined)
}

/** DELETE /network-segments/{segment_id}/gateway?version=：显式清空网关
 * （幂等；Contract §3.4；删除前置之一，BQ-O） */
export function clearNetworkSegmentGateway(segmentId: number, version: number): Promise<void> {
  return client
    .delete<void>(`/network-segments/${segmentId}/gateway`, { params: { version } })
    .then(() => undefined)
}
