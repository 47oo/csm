// 集群 API（Contract docs/api/F001.md §2：列表/新增/详情/编辑/真实删除）。
// 字段与错误语义严格按 Contract；401/403 全局处理、409/422 由页面按 code 呈现。
import { client } from './client'

/** 集群列表项（Contract §1 ClusterListItem；不含聚合计数——属 F010） */
export interface ClusterListItem {
  id: number
  /** 展示编号：去首尾空格后的用户输入形态，保留大小写（ADR-002） */
  code: string
  name: string
  purpose: string
  created_at: string
  updated_at: string
}

/** 集群详情（= ClusterListItem + version 乐观锁，Contract §1） */
export interface ClusterDetail extends ClusterListItem {
  version: number
}

/** GET /clusters 分页响应（Contract §1 PagedClusters） */
export interface PagedClusters {
  items: ClusterListItem[]
  total: number
  page: number
  page_size: number
}

/** POST /clusters 请求体（Contract §2.2） */
export interface ClusterCreatePayload {
  code: string
  name: string
  purpose: string
}

/** PATCH /clusters/{id} 请求体（Contract §2.4：code 不可改，仅名称/用途 + 乐观锁） */
export interface ClusterUpdatePayload {
  name: string
  purpose: string
  /** 乐观锁版本号，必填 */
  version: number
}

/** DELETE /clusters/{id} 查询参数（Contract §2.5：二次确认 + 乐观锁） */
export interface ClusterDeleteQuery {
  /** 二次确认输入（BQ-Z：服务端去首尾空格后与名称或规范化 code 比对） */
  confirm: string
  /** 乐观锁版本号，必填 */
  version: number
}

/** 排序键（Contract §2.1；默认 code） */
export type ClusterSort = 'code' | '-code' | 'name' | '-name' | 'created_at' | '-created_at'

/** 列表查询输入：q 允许空字符串（表示不过滤），空项不发送 */
export interface ClusterListQueryInput {
  page?: number
  page_size?: number
  q?: string
  sort?: ClusterSort | ''
}

/** GET /clusters：分页/搜索/排序列表（Contract §2.1；空结果为 items:[] + total:0） */
export function listClusters(query: ClusterListQueryInput): Promise<PagedClusters> {
  const params: Record<string, string> = {}
  if (query.page !== undefined) params.page = String(query.page)
  if (query.page_size !== undefined) params.page_size = String(query.page_size)
  if (query.q !== undefined && query.q.trim() !== '') params.q = query.q.trim()
  if (query.sort !== undefined && query.sort !== '') params.sort = query.sort
  return client.get<PagedClusters>('/clusters', { params }).then((res) => res.data)
}

/** POST /clusters：新增（201 → ClusterDetail；409 CLUSTER_CODE_TAKEN/CLUSTER_NAME_TAKEN 由页面提示） */
export function createCluster(payload: ClusterCreatePayload): Promise<ClusterDetail> {
  return client.post<ClusterDetail>('/clusters', payload).then((res) => res.data)
}

/** GET /clusters/{cluster_id}：详情（含 version，供编辑/删除乐观锁） */
export function getCluster(clusterId: number): Promise<ClusterDetail> {
  return client.get<ClusterDetail>(`/clusters/${clusterId}`).then((res) => res.data)
}

/** PATCH /clusters/{cluster_id}：仅修改名称/用途（code 创建后不可改）；version 乐观锁 */
export function updateCluster(clusterId: number, payload: ClusterUpdatePayload): Promise<ClusterDetail> {
  return client.patch<ClusterDetail>(`/clusters/${clusterId}`, payload).then((res) => res.data)
}

/** DELETE /clusters/{cluster_id}?confirm=&version=：真实删除（二次确认 + 乐观锁，BQ-Z） */
export function deleteCluster(clusterId: number, query: ClusterDeleteQuery): Promise<void> {
  return client
    .delete<void>(`/clusters/${clusterId}`, { params: { confirm: query.confirm, version: query.version } })
    .then(() => undefined)
}
