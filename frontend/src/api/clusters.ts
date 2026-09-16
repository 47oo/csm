/**
 * Cluster 产品 API 客户端。
 *
 * 契约依据：docs/api/f001-cluster.md（READY）与 docs/api/f014-soft-delete.md
 * （READY，Cluster 删除端点）。
 * - 字段集合封闭（f001 契约 §2）：仅 id / name / created_at / updated_at；
 *   不存在 deleted_at、状态字段或位置字段；
 * - 时间字段为 RFC 3339 字符串，作为不透明字符串展示 / 传递，
 *   不解析、不假设时区（契约 §2）；
 * - 领域校验（`/` 禁令、活跃唯一性）全部在服务端（契约 §3.1 / §3.5）；
 *   本层不做任何业务校验，也不对 name 做任何变换（trim / 大小写折叠 / 归一化，
 *   契约 §7 undefined_constraints）；
 * - 错误语义由 api/http.ts 统一解析为 ApiError，消费方按 error.code 分支。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** Cluster 资源表示（契约 §2；所有返回单对象的端点共用该结构）。 */
export interface ClusterRead {
  /** 不可变代理主键；写操作一律使用该值（ADR-0003）。 */
  id: number
  /** 集群名称，原样存取（不假设非空或已 trim）。 */
  name: string
  /** 登记时间（RFC 3339 不透明字符串）。 */
  created_at: string
  /** 最近更新时间（RFC 3339 不透明字符串；不是并发控制依据）。 */
  updated_at: string
}

/** 写请求体（契约 §3.1 POST / §3.5 PATCH，两者规则完全相同）：仅 name，必填。 */
export interface ClusterWriteBody {
  name: string
}

/** 列出活跃 Cluster（契约 §3.2）。空列表 → 200 + items 为 []（Empty 语义，非错误）。 */
export function listClusters(params: PageParams = {}): Promise<Paginated<ClusterRead>> {
  return apiRequest<Paginated<ClusterRead>>('/api/clusters', {
    method: 'GET',
    query: params,
  })
}

/** 按 id 读取 Cluster（契约 §3.3，规范路径）。不存在或已逻辑删除 → 404 NOT_FOUND（不区分）。 */
export function getCluster(clusterId: number): Promise<ClusterRead> {
  return apiRequest<ClusterRead>(`/api/clusters/${clusterId}`, { method: 'GET' })
}

/**
 * 按名称读取 Cluster（契约 §3.4，只读别名；不存在按名称的写端点）。
 *
 * - 名称按字面值、大小写敏感等值匹配（服务端行为，R-CLUSTER-002 / §22）；
 * - 本函数仅按 RFC 3986 对名称做百分号编码（UTF-8，单个路径段），
 *   不做 trim、大小写折叠或 Unicode 归一化（契约 §3.4 / §7）。
 */
export function getClusterByName(clusterName: string): Promise<ClusterRead> {
  return apiRequest<ClusterRead>(`/api/clusters/by-name/${encodeURIComponent(clusterName)}`, {
    method: 'GET',
  })
}

/** 登记 Cluster（契约 §3.1）。成功 → 201 + ClusterRead；`/` 或活跃重名由服务端拒绝。 */
export function createCluster(body: ClusterWriteBody): Promise<ClusterRead> {
  return apiRequest<ClusterRead>('/api/clusters', {
    method: 'POST',
    body,
  })
}

/** 更新 Cluster 名称（契约 §3.5；name 是唯一可变字段，必须提供）。 */
export function updateCluster(clusterId: number, body: ClusterWriteBody): Promise<ClusterRead> {
  return apiRequest<ClusterRead>(`/api/clusters/${clusterId}`, {
    method: 'PATCH',
    body,
  })
}

/**
 * 逻辑删除 Cluster（契约 f014-soft-delete.md §3.1）。
 *
 * - `DELETE /api/clusters/{cluster_id}`：写操作一律走 `id`（ADR-0003 §2），
 *   不存在按名称的删除别名；
 * - 成功 → `204`（无响应体，apiRequest 归一为 undefined，不抛出）；
 * - `404 NOT_FOUND`：`cluster_id` 不存在或已被逻辑删除（两者不区分，
 *   重复删除同一 id 亦返回 404）；
 * - `409 CONFLICT`：存在活跃子资源（`details[].code === 'ACTIVE_CHILDREN_EXIST'`）；
 * - `401 UNAUTHENTICATED`：未认证且不改变任何数据（由全局会话失效处理）；
 * - 不发送请求体（契约 §3.1：Request body 无，客户端不得发送）。
 */
export function deleteCluster(clusterId: number): Promise<void> {
  return apiRequest<void>(`/api/clusters/${clusterId}`, { method: 'DELETE' })
}
