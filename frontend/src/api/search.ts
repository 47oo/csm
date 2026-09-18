/**
 * 集群内资源关键字搜索 API 客户端（F018）。
 *
 * 契约依据：docs/api/f018-cluster-keyword-search.md（READY，唯一权威）。
 * - 恰一个只读端点 `GET /api/clusters/{cluster_id}/search`（契约 §3）：一次
 *   请求返回该 Cluster 内命中资源的**单一混合列表**（不分组、不承诺排序）；
 *   前端不得在浏览器端拼接多个列表或推导资源关系（架构 Handoff 裁定 1）；
 * - `resource_type` 封闭六值（契约 §2）：BARE_METAL / NETWORK_INTERFACE /
 *   IP_ADDRESS / VIRTUAL_MACHINE / CONTAINER / SERVICE，与 `resource` 的
 *   canonical `*Read` 一一对应（判别字段，契约 §3 Response 200）；
 * - `resource` 逐字段复用各资源 canonical `*Read`（本模块只引用类型，不另立
 *   一份）；`matched_fields` 为非空字符串数组（命中字段名，元素取自契约 §2
 *   对应类型的字段清单，顺序为契约声明顺序），前端原样渲染、不解释；
 * - `keyword` 必填、**原样**提交（不 trim、不归一化，契约 §2「关键字处理」）；
 *   空 / 仅空白关键字在 UI 侧不可发起（R-QUERY-005 前置），后端返回 400
 *   VALIDATION_ERROR —— 前端不重复实现该业务校验，仅按 R-QUERY-005 的
 *   UI 前置（未选定 Cluster / 关键字仅空白时按钮禁用）拦截发起；
 * - Empty / Not Found 分离（契约 §3 / R-QUERY-004）：Cluster 活跃但无命中
 *   → 200 + items == []（Empty，不得渲染为错误）；Cluster 不存在或已逻辑
 *   删除 → 404 NOT_FOUND（两者不区分）；未认证 → 401 UNAUTHENTICATED
 *   （由全局会话失效处理）；
 * - 分页复用通用信封 {items, total, page, page_size}（契约 §3；分页参数
 *   合法性由服务端校验）；错误语义由 api/http.ts 统一解析为 ApiError，
 *   消费方按 error.code 分支，不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'
import type { BareMetalRead } from './bareMetals'
import type { NetworkInterfaceRead } from './networkInterfaces'
import type { IpAddressRead } from './ipAddresses'
import type { VirtualMachineRead } from './virtualMachines'
import type { ContainerRead } from './containers'
import type { ServiceRead } from './services'

/** resource_type 封闭集合（契约 §2 / §3；恰六值）。 */
export const SEARCH_RESOURCE_TYPES = [
  'BARE_METAL',
  'NETWORK_INTERFACE',
  'IP_ADDRESS',
  'VIRTUAL_MACHINE',
  'CONTAINER',
  'SERVICE',
] as const

/** 搜索结果的资源类型（判别字段，契约 §3）。 */
export type SearchResourceType = (typeof SEARCH_RESOURCE_TYPES)[number]

/**
 * 搜索结果元素（契约 §3 Response 200 的 items[]）。
 *
 * 以 `resource_type` 为判别的可辨识联合：`resource` 的类型由 `resource_type`
 * 决定（契约 §2：逐字段复用对应 canonical `*Read`）。
 */
export type SearchResultItem =
  | { resource_type: 'BARE_METAL'; id: number; matched_fields: string[]; resource: BareMetalRead }
  | {
      resource_type: 'NETWORK_INTERFACE'
      id: number
      matched_fields: string[]
      resource: NetworkInterfaceRead
    }
  | { resource_type: 'IP_ADDRESS'; id: number; matched_fields: string[]; resource: IpAddressRead }
  | {
      resource_type: 'VIRTUAL_MACHINE'
      id: number
      matched_fields: string[]
      resource: VirtualMachineRead
    }
  | { resource_type: 'CONTAINER'; id: number; matched_fields: string[]; resource: ContainerRead }
  | { resource_type: 'SERVICE'; id: number; matched_fields: string[]; resource: ServiceRead }

/** 搜索查询参数（契约 §3）：keyword 必填（原样提交）；page / page_size 通用分页。 */
export interface SearchClusterResourcesParams extends PageParams {
  /** 单关键字，原样提交（不 trim / 不归一化，契约 §2）。 */
  keyword: string
}

/**
 * 在单个 Cluster 内按关键字搜索（契约 §3，唯一搜索端点，只读）。
 *
 * - 成功 → 200 + `Paginated<SearchResultItem>`（单一混合列表；无命中 →
 *   items == [] 且 total == 0，Empty，不得渲染为错误）；
 * - `keyword` 缺失 / 空 / 仅空白，或分页参数非法 → 400 VALIDATION_ERROR
 *   （`details[].field` 为 "keyword" 等；由服务端裁决，前端不重复实现）；
 * - Cluster 不存在或已逻辑删除 → 404 NOT_FOUND（两者不区分）；
 * - 401 UNAUTHENTICATED 由全局会话失效处理；
 * - 无请求体（契约 §3：客户端不得发送）。
 */
export function searchClusterResources(
  clusterId: number,
  params: SearchClusterResourcesParams,
): Promise<Paginated<SearchResultItem>> {
  return apiRequest<Paginated<SearchResultItem>>(`/api/clusters/${clusterId}/search`, {
    method: 'GET',
    query: {
      keyword: params.keyword,
      page: params.page,
      page_size: params.page_size,
    },
  })
}
