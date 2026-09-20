/**
 * 集群内资源关键字搜索 API 客户端（F018 端点，F019 聚合响应）。
 *
 * 契约依据：docs/api/f019-search-result-aggregation.md（READY，唯一权威）。
 * - 恰一个只读端点 `GET /api/clusters/{cluster_id}/search`（契约 §3）：method /
 *   path / 请求参数与 F018 相同，**响应形态被本契约取代**（契约 §2.6）——一次
 *   请求返回「命中项 + 其关联链」的**单一扁平聚合行列表**；前端不得在浏览器端
 *   拼接多个列表或推导资源关系（架构 Handoff 裁定 1 / 契约 §2.3）；
 * - `resource_type` 封闭六值（契约 §4.1）：BARE_METAL / NETWORK_INTERFACE /
 *   IP_ADDRESS / VIRTUAL_MACHINE / CONTAINER / SERVICE，与 `resource` 的
 *   canonical `*Read` 一一对应（判别字段）；`role` 封闭两值 `HIT` | `RELATED`，
 *   每个组织单元首行为 `HIT`（契约 §2.2）；
 * - `group_key` / `derivation_path` 元素为 `ResourceRef`（恰 `{resource_type, id}`
 *   两字段，契约 §4.2）：同单元各行共享同一 `group_key`；`HIT` 行
 *   `derivation_path == null`，`RELATED` 行非空且首元素 = 本单元命中项、
 *   末元素 = 本行（契约 §4.1 / §4.3），前端原样消费、不推导；
 * - `resource` 逐字段复用各资源 canonical `*Read`（本模块只引用类型，不另立
 *   一份）；`matched_fields` 为本行**自身**命中字段名（`HIT` 恒非空；`RELATED`
 *   可为 `[]` 或非空——该行自身也命中时，契约 §4.1），前端原样渲染、不解释；
 * - `keyword` 必填、**原样**提交（不 trim、不归一化，f018 契约 §2「关键字处理」
 *   仍为匹配语义唯一权威）；空 / 仅空白关键字在 UI 侧不可发起（R-QUERY-005
 *   前置），后端返回 400 VALIDATION_ERROR —— 前端不重复实现该业务校验，仅按
 *   UI 前置（未选定 Cluster / 关键字仅空白时按钮禁用）拦截发起；
 * - 分页按**组织单元（命中项）计数**（契约 §3 语义 4 / §4）：`total` = 单元
 *   全量数，`items` 为该页单元的展平行（`len(items)` 可大于 `page_size`）；
 *   分页参数合法性由服务端校验；
 * - Empty / Not Found 分离（契约 §6 / R-QUERY-004）：Cluster 活跃但无命中
 *   → 200 + items == [] + total == 0（Empty，不得渲染为错误）；Cluster 不存在
 *   或已逻辑删除 → 404 NOT_FOUND（两者不区分）；未认证 → 401
 *   UNAUTHENTICATED（由全局会话失效处理）；
 * - 错误语义由 api/http.ts 统一解析为 ApiError，消费方按 error.code 分支，
 *   不解析 message。
 */
import type { PageParams, Paginated } from '../types/api'
import { apiRequest } from './http'
import type { BareMetalRead } from './bareMetals'
import type { NetworkInterfaceRead } from './networkInterfaces'
import type { IpAddressRead } from './ipAddresses'
import type { VirtualMachineRead } from './virtualMachines'
import type { ContainerRead } from './containers'
import type { ServiceRead } from './services'

/** resource_type 封闭集合（契约 §4.1；恰六值）。 */
export const SEARCH_RESOURCE_TYPES = [
  'BARE_METAL',
  'NETWORK_INTERFACE',
  'IP_ADDRESS',
  'VIRTUAL_MACHINE',
  'CONTAINER',
  'SERVICE',
] as const

/** 搜索结果的资源类型（判别字段，契约 §4.1）。 */
export type SearchResourceType = (typeof SEARCH_RESOURCE_TYPES)[number]

/** 行角色（契约 §4.1 封闭两值）：HIT = 单元首行（自身字段命中）；RELATED = 关联行。 */
export type SearchResultRole = 'HIT' | 'RELATED'

/**
 * 资源引用（契约 §4.2，封闭字段集合）：`group_key` 与 `derivation_path`
 * 元素共用；恰 `{resource_type, id}` 两字段。
 */
export interface ResourceRef {
  resource_type: SearchResourceType
  id: number
}

/**
 * `SearchResultRow` 各变体的公共字段（契约 §4.1；除判别字段外逐行一致）。
 */
interface SearchResultRowBase {
  /** 本行在本组织单元中的角色；每单元首行为 HIT（契约 §2.2）。 */
  role: SearchResultRole
  /** 本行所属组织单元（= 一个命中项）的身份；同单元各行一致（契约 §4.1）。 */
  group_key: ResourceRef
  /** 本行自身命中字段名（可为 []；HIT 行恒非空，契约 §4.1）。 */
  matched_fields: string[]
  /** HIT → null；RELATED → 非空，首元素 = 本单元命中项、末元素 = 本行（契约 §4.1）。 */
  derivation_path: ResourceRef[] | null
}

/**
 * 搜索结果行（契约 §4 Response 200 的 items[] 元素）。
 *
 * 以 `resource_type` 为判别的可辨识联合：`resource` 的类型由 `resource_type`
 * 决定（契约 §4.1：逐字段复用对应 canonical `*Read`）。
 */
export type SearchResultRow =
  | (SearchResultRowBase & {
      resource_type: 'BARE_METAL'
      id: number
      resource: BareMetalRead
    })
  | (SearchResultRowBase & {
      resource_type: 'NETWORK_INTERFACE'
      id: number
      resource: NetworkInterfaceRead
    })
  | (SearchResultRowBase & {
      resource_type: 'IP_ADDRESS'
      id: number
      resource: IpAddressRead
    })
  | (SearchResultRowBase & {
      resource_type: 'VIRTUAL_MACHINE'
      id: number
      resource: VirtualMachineRead
    })
  | (SearchResultRowBase & {
      resource_type: 'CONTAINER'
      id: number
      resource: ContainerRead
    })
  | (SearchResultRowBase & {
      resource_type: 'SERVICE'
      id: number
      resource: ServiceRead
    })

/** 搜索查询参数（契约 §3）：keyword 必填（原样提交）；page / page_size 通用分页
 * （按组织单元计数，契约 §3 语义 4）。 */
export interface SearchClusterResourcesParams extends PageParams {
  /** 单关键字，原样提交（不 trim / 不归一化，f018 契约 §2）。 */
  keyword: string
}

/**
 * 在单个 Cluster 内按关键字搜索（契约 §3，唯一搜索端点，只读）。
 *
 * - 成功 → 200 + `Paginated<SearchResultRow>`（单一扁平聚合行列表；无命中 →
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
): Promise<Paginated<SearchResultRow>> {
  return apiRequest<Paginated<SearchResultRow>>(`/api/clusters/${clusterId}/search`, {
    method: 'GET',
    query: {
      keyword: params.keyword,
      page: params.page,
      page_size: params.page_size,
    },
  })
}
