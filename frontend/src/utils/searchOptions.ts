// 对象 → SearchOption 适配器（架构 F008 §4.2/§5.1/§5.5，Contract F008 §2/§6）：
// - 只做展示映射与既有 list 端点的参数封装，不复制业务校验/唯一性规则；
// - 下拉 value 恒为稳定 ID（集群 id / 计算资源 id / 网段 id），提交只提交 ID（场景 41）；
// - 下拉建议参数：page_size 小值（默认 20，上限 100）、sort=name
//   （§8.2 同级按名称及 ID 稳定排序；匹配与排序在服务端完成）。
import { listClusters, type ClusterListItem } from '../api/clusters'
import { listResources, type ResourceListItem } from '../api/resources'
import { listNetworkSegments } from '../api/segments'

/** 统一下拉选项（架构 F008 §4.2）：value=稳定 ID；keywords 仅用于客户端本地过滤场景 */
export interface SearchOption {
  value: number | string
  label: string
  keywords?: string
  disabled?: boolean
}

/** 下拉数据源分页结果（与各 list 端点 items/total 对齐） */
export interface SearchOptionsPage {
  items: SearchOption[]
  total: number
}

/** 下拉默认每页数量（架构 §5.1 建议小值；Contract 上限 100） */
export const SEARCH_OPTIONS_PAGE_SIZE = 20

/** 集群 → SearchOption：value=id；label=「编号 名称」；keywords=编号+名称 */
export function clusterToSearchOption(cluster: ClusterListItem): SearchOption {
  return {
    value: cluster.id,
    label: `${cluster.code} ${cluster.name}`,
    keywords: `${cluster.code} ${cluster.name}`,
  }
}

/** 计算资源 → SearchOption：value=id；label=名称；keywords=名称+管理 IP+集群编号 */
export function resourceToSearchOption(resource: ResourceListItem): SearchOption {
  const managementIp = resource.management_ip?.address ?? ''
  return {
    value: resource.id,
    label: resource.name,
    keywords: [resource.name, managementIp, resource.cluster_code]
      .filter((part) => part !== '')
      .join(' '),
  }
}

/** 网段下拉展示字段（segmentToSearchOption 只读取这些字段；NetworkSegmentListItem 与
 * 资源表单的 SegmentOption 均结构满足） */
export interface SegmentSearchFields {
  id: number
  name: string
  cidr: string
  purpose: string
  technology: string
}

/** 网段 → SearchOption：value=id；label=「名称 · CIDR · 用途」；keywords=名称+CIDR+用途+技术类型 */
export function segmentToSearchOption(segment: SegmentSearchFields): SearchOption {
  return {
    value: segment.id,
    label: `${segment.name} · ${segment.cidr} · ${segment.purpose}`,
    keywords: [segment.name, segment.cidr, segment.purpose, segment.technology].join(' '),
  }
}

/**
 * GET /clusters → SearchOption 分页（下拉数据源，架构 §5.1）：
 * q 匹配编号/名称、rank 排序由服务端完成；sort=name 满足 §8.2 同级名称稳定排序。
 */
export async function fetchClusterSearchOptions(
  query: string,
  page = 1,
  pageSize: number = SEARCH_OPTIONS_PAGE_SIZE,
): Promise<SearchOptionsPage> {
  const data = await listClusters({ q: query, page, page_size: pageSize, sort: 'name' })
  return { items: data.items.map(clusterToSearchOption), total: data.total }
}

/**
 * GET /resources（cluster_id 必填作用域）→ SearchOption 分页（下拉数据源，架构 §5.1）：
 * q 匹配名称/资源 ID/本集群已登记 IPv4 由服务端完成；F004 宿主选择在此规范上适配。
 */
export async function fetchResourceSearchOptions(
  clusterId: number,
  query: string,
  page = 1,
  pageSize: number = SEARCH_OPTIONS_PAGE_SIZE,
): Promise<SearchOptionsPage> {
  const data = await listResources({
    cluster_id: clusterId,
    q: query,
    page,
    page_size: pageSize,
    sort: 'name',
  })
  return { items: data.items.map(resourceToSearchOption), total: data.total }
}

/**
 * GET /network-segments（可限集群作用域）→ SearchOption 分页（下拉数据源，架构 §5.1）：
 * q 匹配名称/CIDR/用途/技术类型由服务端完成；clusterId=null 时跨集群返回。
 */
export async function fetchSegmentSearchOptions(
  clusterId: number | null,
  query: string,
  page = 1,
  pageSize: number = SEARCH_OPTIONS_PAGE_SIZE,
): Promise<SearchOptionsPage> {
  const data = await listNetworkSegments({
    ...(clusterId !== null ? { cluster_id: clusterId } : {}),
    q: query,
    page,
    page_size: pageSize,
    sort: 'name',
  })
  return { items: data.items.map(segmentToSearchOption), total: data.total }
}
