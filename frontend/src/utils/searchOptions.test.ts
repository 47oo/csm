// 对象 → SearchOption 适配器单测（架构 F008 §4.2/§5.1，Contract F008 §2/§6）：
// value 恒为稳定 ID；label/keywords 展示映射；fetcher 参数封装
// （page_size 小值、sort=name；资源 cluster_id 必填作用域；网段作用域可选）。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listClusters } from '../api/clusters'
import { listResources } from '../api/resources'
import { listNetworkSegments } from '../api/segments'
import {
  clusterToSearchOption,
  fetchClusterSearchOptions,
  fetchResourceSearchOptions,
  fetchSegmentSearchOptions,
  resourceToSearchOption,
  segmentToSearchOption,
} from './searchOptions'
import type { ClusterListItem } from '../api/clusters'
import type { ResourceListItem } from '../api/resources'
import type { NetworkSegmentListItem } from '../api/segments'

vi.mock('../api/clusters', () => ({ listClusters: vi.fn() }))
vi.mock('../api/resources', () => ({ listResources: vi.fn() }))
vi.mock('../api/segments', () => ({ listNetworkSegments: vi.fn() }))

const mockedListClusters = vi.mocked(listClusters)
const mockedListResources = vi.mocked(listResources)
const mockedListSegments = vi.mocked(listNetworkSegments)

const NOW = '2026-09-26T00:00:00Z'

const cluster: ClusterListItem = {
  id: 7,
  code: 'N96P',
  name: '生产集群',
  purpose: '训练',
  created_at: NOW,
  updated_at: NOW,
}

const resource: ResourceListItem = {
  id: 42,
  name: 'cn001',
  cluster_id: 7,
  cluster_code: 'N96P',
  cluster_name: '生产集群',
  resource_type: 'bare_metal',
  resource_type_label: '裸金属',
  status: 'ALLOC',
  status_label: '已分配',
  management_ip: { ip_id: 55, address: '192.168.1.10', interface_id: 10, interface_name: 'eth0' },
  updated_at: NOW,
}

const segment: NetworkSegmentListItem = {
  id: 12,
  cluster_id: 7,
  cluster_code: 'N96P',
  cluster_name: '生产集群',
  name: '管理网段',
  cidr: '192.168.1.0/24',
  purpose: '管理网络',
  technology: 'Ethernet',
  vlan: 10,
  gateway: '192.168.1.1',
  auto_alloc_start: '192.168.1.20',
  auto_alloc_end: '192.168.1.30',
  auto_alloc_enabled: true,
  reserved_address_count: 0,
  allocated_count: 3,
  auto_assignable_count: 200,
  has_overlap: false,
  created_at: NOW,
  updated_at: NOW,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SearchOption 映射（value = 稳定 ID，架构 §4.2/§5.5）', () => {
  it('集群：value=id；label=「编号 名称」；keywords=编号+名称', () => {
    expect(clusterToSearchOption(cluster)).toEqual({
      value: 7,
      label: 'N96P 生产集群',
      keywords: 'N96P 生产集群',
    })
  })

  it('计算资源：value=id；label=名称；keywords=名称+管理 IP+集群编号', () => {
    expect(resourceToSearchOption(resource)).toEqual({
      value: 42,
      label: 'cn001',
      keywords: 'cn001 192.168.1.10 N96P',
    })
    // 无管理 IP 时 keywords 不含空段
    expect(resourceToSearchOption({ ...resource, management_ip: null }).keywords).toBe('cn001 N96P')
  })

  it('网段：value=id；label=「名称 · CIDR · 用途」；keywords=名称+CIDR+用途+技术类型', () => {
    expect(segmentToSearchOption(segment)).toEqual({
      value: 12,
      label: '管理网段 · 192.168.1.0/24 · 管理网络',
      keywords: '管理网段 192.168.1.0/24 管理网络 Ethernet',
    })
  })
})

describe('fetcher 参数封装（架构 §5.1：page_size 小值、sort=name；作用域）', () => {
  it('集群：GET /clusters（q/page/page_size/sort=name）并映射为 SearchOption', async () => {
    mockedListClusters.mockResolvedValue({ items: [cluster], total: 1, page: 1, page_size: 20 })
    const page = await fetchClusterSearchOptions('N96P', 2)
    expect(mockedListClusters).toHaveBeenCalledWith({
      q: 'N96P',
      page: 2,
      page_size: 20,
      sort: 'name',
    })
    expect(page).toEqual({ items: [{ value: 7, label: 'N96P 生产集群', keywords: 'N96P 生产集群' }], total: 1 })
  })

  it('计算资源：GET /resources（cluster_id 必填作用域）并映射', async () => {
    mockedListResources.mockResolvedValue({
      items: [resource],
      total: 1,
      page: 1,
      page_size: 20,
      scope: { cluster_id: 7, cluster_code: 'N96P', cluster_name: '生产集群' },
    })
    const page = await fetchResourceSearchOptions(7, 'cn0', 1, 50)
    expect(mockedListResources).toHaveBeenCalledWith({
      cluster_id: 7,
      q: 'cn0',
      page: 1,
      page_size: 50,
      sort: 'name',
    })
    expect(page.items[0]?.value).toBe(42)
    expect(page.items[0]?.label).toBe('cn001')
  })

  it('网段：GET /network-segments；clusterId=null 时省略作用域（跨集群）', async () => {
    mockedListSegments.mockResolvedValue({ items: [segment], total: 1, page: 1, page_size: 20 })
    await fetchSegmentSearchOptions(7, '192.168')
    expect(mockedListSegments).toHaveBeenLastCalledWith({
      cluster_id: 7,
      q: '192.168',
      page: 1,
      page_size: 20,
      sort: 'name',
    })

    await fetchSegmentSearchOptions(null, '管理')
    expect(mockedListSegments).toHaveBeenLastCalledWith({
      q: '管理',
      page: 1,
      page_size: 20,
      sort: 'name',
    })
  })
})
