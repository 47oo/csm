// 资源列表状态机单测（架构 F003 §2.4/§7 / Contract F003 §2.1）：通过挂载宿主组件驱动
// composable（模式与 useSegmentAllocatedIps.test.ts 一致），API 模块 mock。
// 覆盖：加载与 Loading/Success/Empty/Error 状态区分、cluster_id 必填作用域与未选择集群
// 不发查询、类型/状态筛选（回到第 1 页）、排序、服务端分页（page/page_size）、
// q 搜索 300ms 防抖（去首尾空格、回到第 1 页）与回车立即、旧请求不覆盖较新请求、
// 作用域切换刷新列表（页码重置、搜索词保留）与作用域回显 scope。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { listResources, type PagedResources, type ResourceListItem } from '../api/resources'
import { useResourceList } from './useResourceList'

vi.mock('../api/resources', () => ({
  listResources: vi.fn(),
}))

const NOW = '2026-09-25T00:00:00Z'

function item(overrides: Partial<ResourceListItem> & Pick<ResourceListItem, 'id'>): ResourceListItem {
  return {
    name: `cn00${overrides.id}`,
    cluster_id: 1,
    cluster_code: 'N96P',
    cluster_name: '生产集群',
    resource_type: 'bare_metal',
    resource_type_label: '裸金属',
    status: 'ALLOC',
    status_label: '已分配',
    management_ip: null,
    updated_at: NOW,
    ...overrides,
  }
}

function paged(
  items: ResourceListItem[],
  total: number,
  pageNumber = 1,
  clusterId = 1,
): PagedResources {
  return {
    items,
    total,
    page: pageNumber,
    page_size: 20,
    scope: { cluster_id: clusterId, cluster_code: 'N96P', cluster_name: '生产集群' },
  }
}

type Exposed = ReturnType<typeof useResourceList> & {
  scopeClusterId: { value: number | null }
}

let exposed: Exposed | null = null

/** 挂载仅运行 composable 的宿主组件（无需 @vue/test-utils）；scopeClusterId 可变 */
function mountHost(initialClusterId: number | null = 1): void {
  const scopeClusterId = ref<number | null>(initialClusterId)
  const Host = defineComponent({
    setup() {
      exposed = {
        ...useResourceList(scopeClusterId),
        scopeClusterId,
      } as Exposed
      return () => h('div')
    },
  })
  const app = createApp(Host)
  app.mount(document.createElement('div'))
}

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i++) await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  for (let i = 0; i < 10; i++) await nextTick()
}

/** 假定时器下的排空（不依赖真实 setTimeout） */
async function flushFake(): Promise<void> {
  for (let i = 0; i < 10; i++) await nextTick()
  await vi.advanceTimersByTimeAsync(0)
  for (let i = 0; i < 10; i++) await nextTick()
}

const mockedList = vi.mocked(listResources)

beforeEach(() => {
  exposed = null
  vi.clearAllMocks()
  // 默认应答：1 条资源
  mockedList.mockResolvedValue(paged([item({ id: 7 })], 1))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('加载与状态区分（Contract F003 §2.1）', () => {
  it('挂载即加载：cluster_id 必填 + 默认 page/page_size/sort=name（服务端默认排序）', async () => {
    mountHost()
    expect(mockedList).toHaveBeenCalledWith({
      cluster_id: 1,
      page: 1,
      page_size: 20,
      sort: 'name',
    })
    await flush()
    expect(exposed!.loading.value).toBe(false)
    expect(exposed!.items.value).toHaveLength(1)
    expect(exposed!.total.value).toBe(1)
    expect(exposed!.loadError.value).toBe('')
    // 作用域回显（Contract §1 ClusterScope，页面显式展示用）
    expect(exposed!.scope.value).toEqual({
      cluster_id: 1,
      cluster_code: 'N96P',
      cluster_name: '生产集群',
    })
  })

  it('未选择集群（null）：不发起查询、清空结果（页面提示选择集群，不伪装成空列表）', async () => {
    mountHost(1)
    await flush()
    expect(mockedList).toHaveBeenCalledTimes(1)

    exposed!.scopeClusterId.value = null
    await flush()
    expect(mockedList).toHaveBeenCalledTimes(1) // 无新请求
    expect(exposed!.items.value).toEqual([])
    expect(exposed!.total.value).toBe(0)
    expect(exposed!.loading.value).toBe(false)
    expect(exposed!.loadError.value).toBe('')
  })

  it('空结果：items:[] + total:0（200 空态，不伪装成错误）', async () => {
    mockedList.mockResolvedValue(paged([], 0))
    mountHost()
    await flush()
    expect(exposed!.items.value).toEqual([])
    expect(exposed!.total.value).toBe(0)
    expect(exposed!.loadError.value).toBe('')
  })

  it('加载失败：loadError 显式呈现（不伪装成空列表）、items 清空，可重试', async () => {
    mockedList.mockRejectedValueOnce(new Error('boom'))
    mountHost()
    await flush()
    expect(exposed!.loadError.value).not.toBe('')
    expect(exposed!.items.value).toEqual([])
    expect(exposed!.loading.value).toBe(false)

    await exposed!.retry()
    await flush()
    expect(exposed!.loadError.value).toBe('')
    expect(exposed!.items.value).toHaveLength(1)
  })
})

describe('类型切换与状态筛选（§6.2：省略 = 全部）', () => {
  it('setType(bare_metal)：请求带 resource_type 并回到第 1 页', async () => {
    mountHost()
    await flush()
    exposed!.page.value = 3

    await exposed!.setType('bare_metal')
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith({
      cluster_id: 1,
      resource_type: 'bare_metal',
      page: 1,
      page_size: 20,
      sort: 'name',
    })
  })

  it('setType(virtual_machine)：裸金属/虚拟机切换', async () => {
    mountHost()
    await flush()
    await exposed!.setType('virtual_machine')
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ resource_type: 'virtual_machine' }),
    )
  })

  it("setType('')：回到全部（不发送 resource_type）", async () => {
    mountHost()
    await flush()
    await exposed!.setType('virtual_machine')
    await flush()
    await exposed!.setType('')
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith({
      cluster_id: 1,
      page: 1,
      page_size: 20,
      sort: 'name',
    })
  })

  it('setStatus(DOWN)：请求带 status 并回到第 1 页', async () => {
    mountHost()
    await flush()
    exposed!.page.value = 2

    await exposed!.setStatus('DOWN')
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'DOWN', page: 1 }),
    )
  })

  it('类型 + 状态 + 搜索组合筛选', async () => {
    mockedList.mockResolvedValue(paged([], 0))
    mountHost()
    await flush()
    await exposed!.setType('bare_metal')
    await exposed!.setStatus('IDLE')
    await exposed!.searchNow()
    // searchNow 使用 q 当前值（空 = 不搜索）
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith({
      cluster_id: 1,
      resource_type: 'bare_metal',
      status: 'IDLE',
      page: 1,
      page_size: 20,
      sort: 'name',
    })
  })
})

describe('排序与服务端分页（默认按名称排序，§6.2/§9.2）', () => {
  it('setSort(-updated_at)：请求带新排序并回到第 1 页', async () => {
    mountHost()
    await flush()
    exposed!.page.value = 4
    await exposed!.setSort('-updated_at')
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort: '-updated_at', page: 1 }),
    )
    expect(exposed!.sort.value).toBe('-updated_at')
  })

  it('翻页：setPage 携带新 page；setPageSize 回到第 1 页', async () => {
    mountHost()
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, page_size: 20 }),
    )

    await exposed!.setPage(3)
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 3, page_size: 20 }),
    )
    expect(exposed!.page.value).toBe(3)

    await exposed!.setPageSize(50)
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, page_size: 50 }),
    )
  })
})

describe('q 搜索（§8.3：300ms 防抖 + 回车立即；去首尾空格；旧请求不覆盖新请求）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('输入后 300ms 防抖触发：q 去首尾空格、回到第 1 页', async () => {
    mountHost()
    await vi.runOnlyPendingTimersAsync()
    await flushFake()
    expect(exposed!.page.value).toBe(1)

    // 先翻到第 3 页，再搜索：应回到第 1 页
    exposed!.page.value = 3
    exposed!.setQ('  cn001 ')
    // 防抖期内不请求
    expect(mockedList).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'cn001', page: 1 }),
    )
    expect(exposed!.q.value).toBe('  cn001 ') // 输入框展示值保留
  })

  it('回车立即搜索（取消未触发的防抖）', async () => {
    mountHost()
    await vi.runOnlyPendingTimersAsync()
    await flushFake()

    exposed!.setQ('192.168.1.')
    await vi.advanceTimersByTimeAsync(100) // 防抖期内
    exposed!.searchNow()
    await flushFake()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: '192.168.1.' }),
    )
    // 防抖已被取消：不再产生重复请求
    const calls = mockedList.mock.calls.length
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    expect(mockedList.mock.calls.length).toBe(calls)
  })

  it('纯空白 q 不发送参数（空 = 不搜索）', async () => {
    mountHost()
    await vi.runOnlyPendingTimersAsync()
    await flushFake()

    exposed!.setQ('   ')
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    expect(mockedList).toHaveBeenLastCalledWith({
      cluster_id: 1,
      page: 1,
      page_size: 20,
      sort: 'name',
    })
  })

  it('快速连续输入：旧请求不覆盖较新请求（§8.3）', async () => {
    const deferred: Array<(value: PagedResources) => void> = []
    mockedList.mockImplementation(
      () =>
        new Promise((resolve) => {
          deferred.push(resolve)
        }),
    )
    mountHost()
    await vi.runOnlyPendingTimersAsync()
    await flushFake()
    expect(deferred).toHaveLength(1)

    exposed!.setQ('cn0')
    await vi.advanceTimersByTimeAsync(300)
    exposed!.setQ('cn001') // 旧请求（cn0）尚未返回
    await vi.advanceTimersByTimeAsync(300)
    expect(deferred).toHaveLength(3)

    // 较新请求（cn001）先返回 → 生效
    deferred[2]!(paged([item({ id: 7 })], 1))
    await flushFake()
    expect(exposed!.loading.value).toBe(false)
    expect(exposed!.items.value).toHaveLength(1)

    // 旧请求（cn0）后返回 → 不覆盖
    deferred[1]!(paged([item({ id: 99 })], 1))
    await flushFake()
    expect(exposed!.items.value[0]?.id).toBe(7)
  })

  it('重置筛选：清空搜索/类型/状态并回到默认排序第 1 页', async () => {
    mountHost()
    await vi.runOnlyPendingTimersAsync()
    await flushFake()

    exposed!.setQ('cn001')
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    await exposed!.setType('bare_metal')
    await exposed!.setStatus('DOWN')
    await exposed!.setSort('-name')

    exposed!.resetFilters()
    await flushFake()
    expect(mockedList).toHaveBeenLastCalledWith({
      cluster_id: 1,
      page: 1,
      page_size: 20,
      sort: 'name',
    })
    expect(exposed!.q.value).toBe('')
    expect(exposed!.resourceType.value).toBe('')
    expect(exposed!.status.value).toBe('')
    expect(exposed!.sort.value).toBe('name')
  })
})

describe('作用域切换（切换集群刷新列表；不隐式切换作用域，BQ-H/场景 56）', () => {
  it('切换集群：以新 cluster_id 重新加载、页码重置、搜索词保留（仍限新集群）', async () => {
    mockedList.mockResolvedValue(paged([item({ id: 7 })], 100, 1))
    mountHost()
    await flush()
    exposed!.page.value = 5
    exposed!.q.value = 'cn001'
    await exposed!.searchNow()
    await flush()

    mockedList.mockResolvedValue(paged([item({ id: 8, cluster_id: 2 })], 1, 1, 2))
    exposed!.scopeClusterId.value = 2
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ cluster_id: 2, q: 'cn001', page: 1 }),
    )
    expect(exposed!.items.value[0]?.id).toBe(8)
    expect(exposed!.scope.value?.cluster_id).toBe(2)
  })
})
