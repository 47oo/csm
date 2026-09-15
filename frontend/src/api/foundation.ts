/**
 * `/_foundation/*` 非产品自检面客户端。
 *
 * ⚠️ 非产品端点（docs/api/f012-project-foundation.md §4）：
 * - 仅在 dev/test 配置下由后端挂载，生产环境不可达（请求返回 404）；
 * - 不含任何 Cluster 领域规则；`clusters` 仅作基座验证载体；
 * - 本模块仅供 F012 前端基座自检（Loading / Empty / Error 三态）使用，
 *   不得被产品页面使用；
 * - F001 交付产品 Cluster API（/api/clusters）后，本自检面将移除或降级为测试夹具。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'

/** 自检载体行（契约 §4.1 单对象结构；`deleted_at` 不对外暴露）。 */
export interface FoundationCluster {
  id: number
  name: string
  created_at: string
  updated_at: string
}

/**
 * 列出活跃载体行（契约 §4.2）。
 * 空列表 → 200 + items 为 []（Empty 语义，不是错误）。
 */
export function listFoundationClusters(
  params: PageParams = {},
): Promise<Paginated<FoundationCluster>> {
  return apiRequest<Paginated<FoundationCluster>>('/_foundation/clusters', {
    method: 'GET',
    query: params,
  })
}

/**
 * 触发确定性 500 INTERNAL_ERROR（契约 §4.6），用于驱动前端 Error 态。
 * 该端点永远失败，本函数永远 reject。
 */
export function getFoundationError(): Promise<never> {
  return apiRequest<never>('/_foundation/error', { method: 'GET' })
}
