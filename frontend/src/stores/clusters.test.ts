import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ApiError } from '../api/client'
import type { ClusterListItem, PagedClusters } from '../api/clusters'
import { useClusterStore } from './clusters'

// 替换 API 模块：store 单测只验证状态逻辑，不发真实请求
vi.mock('../api/clusters', () => ({
  listClusters: vi.fn(),
}))

import * as clustersApi from '../api/clusters'

const STORAGE_KEY = 'csm.cluster.currentClusterId'

function cluster(id: number, code: string, name: string): ClusterListItem {
  return {
    id,
    code,
    name,
    purpose: '用途',
    created_at: '2026-09-25T00:00:00Z',
    updated_at: '2026-09-25T00:00:00Z',
  }
}

function paged(items: ClusterListItem[], total = items.length, page = 1): PagedClusters {
  return { items, total, page, page_size: 100 }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  window.localStorage.clear()
})

describe('useClusterStore：选择记忆（localStorage 持久化）', () => {
  it('selectCluster 写入 localStorage，清除选择时移除', () => {
    const store = useClusterStore()
    store.selectCluster(3)
    expect(store.currentClusterId).toBe(3)
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('3')

    store.selectCluster(null)
    expect(store.currentClusterId).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('restoreSelection 恢复记忆的选择并加载列表（刷新恢复）', async () => {
    window.localStorage.setItem(STORAGE_KEY, '3')
    vi.mocked(clustersApi.listClusters).mockResolvedValue(
      paged([cluster(1, 'A01', '集群一'), cluster(3, 'N96P', '生产集群')]),
    )
    const store = useClusterStore()
    await store.restoreSelection()
    expect(store.currentClusterId).toBe(3)
    expect(store.currentCluster?.code).toBe('N96P')
    expect(store.loaded).toBe(true)
    expect(store.selectionDropped).toBe(false)
  })

  it('无记忆时 restoreSelection 不预选任何集群', async () => {
    vi.mocked(clustersApi.listClusters).mockResolvedValue(paged([cluster(1, 'A01', '集群一')]))
    const store = useClusterStore()
    await store.restoreSelection()
    expect(store.currentClusterId).toBeNull()
    expect(store.currentCluster).toBeNull()
  })

  it('切换选择只改查询作用域，不影响角色权限状态（场景 40/57：权限由服务端校验）', () => {
    const store = useClusterStore()
    store.selectCluster(1)
    store.selectCluster(2)
    expect(store.currentClusterId).toBe(2)
    // store 不保存/不改写任何角色信息；权限始终来自 auth store 与服务端
    expect('role' in store.$state).toBe(false)
  })
})

describe('useClusterStore：选择失效回退（架构 §2.3 首屏恢复）', () => {
  it('记忆的集群已不存在 → 回退为空、清除持久化并标记 selectionDropped', async () => {
    window.localStorage.setItem(STORAGE_KEY, '99')
    vi.mocked(clustersApi.listClusters).mockResolvedValue(paged([cluster(1, 'A01', '集群一')]))
    const store = useClusterStore()
    await store.restoreSelection()
    expect(store.currentClusterId).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull()
    expect(store.selectionDropped).toBe(true)

    store.acknowledgeSelectionDrop()
    expect(store.selectionDropped).toBe(false)
  })

  it('强制刷新后当前选择被删除（列表页删除联动）→ 清除选择并标记', async () => {
    vi.mocked(clustersApi.listClusters)
      .mockResolvedValueOnce(paged([cluster(1, 'A01', '集群一'), cluster(3, 'N96P', '生产集群')]))
      .mockResolvedValueOnce(paged([cluster(1, 'A01', '集群一')]))
    const store = useClusterStore()
    await store.loadClusters()
    store.selectCluster(3)
    expect(store.currentClusterId).toBe(3)

    await store.loadClusters(true)
    expect(store.currentClusterId).toBeNull()
    expect(store.selectionDropped).toBe(true)
  })

  it('加载失败时不误判选择失效（保留记忆，等待重试）', async () => {
    window.localStorage.setItem(STORAGE_KEY, '3')
    vi.mocked(clustersApi.listClusters).mockRejectedValue(
      new ApiError(0, 'NETWORK_ERROR', '网络错误，请检查与服务器的连接后重试'),
    )
    const store = useClusterStore()
    await store.restoreSelection()
    // 列表未加载成功：无法证明选择失效，保留记忆与缓存，记录错误
    expect(store.currentClusterId).toBe(3)
    expect(store.selectionDropped).toBe(false)
    expect(store.loaded).toBe(false)
    expect(store.loadError).toBe('网络错误，请检查与服务器的连接后重试')
  })
})

describe('useClusterStore：列表缓存加载', () => {
  it('逐页拉取直到 total（page_size 上限 100，Contract §2.1）', async () => {
    const firstPage = Array.from({ length: 100 }, (_, i) => cluster(i + 1, `C${i + 1}`, `集群${i + 1}`))
    const secondPage = [cluster(101, 'C101', '集群101'), cluster(102, 'C102', '集群102')]
    vi.mocked(clustersApi.listClusters).mockImplementation(async (query) => {
      if (query.page === 1) return paged(firstPage, 102, 1)
      return paged(secondPage, 102, 2)
    })
    const store = useClusterStore()
    await store.loadClusters()
    expect(clustersApi.listClusters).toHaveBeenCalledTimes(2)
    expect(clustersApi.listClusters).toHaveBeenNthCalledWith(1, { page: 1, page_size: 100, sort: 'code' })
    expect(clustersApi.listClusters).toHaveBeenNthCalledWith(2, { page: 2, page_size: 100, sort: 'code' })
    expect(store.clusters).toHaveLength(102)
    expect(store.loaded).toBe(true)
    expect(store.loadError).toBeNull()
  })

  it('已加载且非 force 时不重复请求；force 时重新拉取', async () => {
    vi.mocked(clustersApi.listClusters).mockResolvedValue(paged([cluster(1, 'A01', '集群一')]))
    const store = useClusterStore()
    await store.loadClusters()
    await store.loadClusters()
    expect(clustersApi.listClusters).toHaveBeenCalledTimes(1)

    await store.loadClusters(true)
    expect(clustersApi.listClusters).toHaveBeenCalledTimes(2)
  })

  it('加载失败保留原缓存（不伪装成空列表）并记录 loadError', async () => {
    vi.mocked(clustersApi.listClusters)
      .mockResolvedValueOnce(paged([cluster(1, 'A01', '集群一')]))
      .mockRejectedValueOnce(new ApiError(500, 'UNKNOWN', '服务器错误'))
    const store = useClusterStore()
    await store.loadClusters()
    expect(store.clusters).toHaveLength(1)

    await store.loadClusters(true)
    expect(store.clusters).toHaveLength(1) // 保留原缓存
    expect(store.loaded).toBe(true)
    // apiErrorMessage：5xx 未知错误统一为服务器错误文案
    expect(store.loadError).toBe('服务器错误（HTTP 500），请稍后重试')
  })

  it('空列表（total 0）正常加载，不报错', async () => {
    vi.mocked(clustersApi.listClusters).mockResolvedValue(paged([], 0))
    const store = useClusterStore()
    await store.loadClusters()
    expect(store.clusters).toEqual([])
    expect(store.loaded).toBe(true)
    expect(store.loadError).toBeNull()
  })
})
