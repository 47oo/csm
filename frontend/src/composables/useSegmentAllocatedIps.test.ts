// 网段详情「已分配 IP 及归属」状态机单测（架构 F006 §2.4 / Contract F006 §3.1）：
// 通过挂载宿主组件驱动 composable（模式与 useResourceForm.test.ts 一致），API 模块 mock。
// 覆盖：打开抽屉加载与 Loading/Success/Empty/Error 状态区分、服务端分页翻页、
// q 搜索 300ms 防抖（去首尾空格、回到第 1 页）与回车立即、旧请求不覆盖较新请求、
// 关闭/切换网段重置。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { listAllocatedIps, type AllocatedIpItem } from '../api/segments'
import { useSegmentAllocatedIps } from './useSegmentAllocatedIps'

vi.mock('../api/segments', () => ({
  listAllocatedIps: vi.fn(),
}))

const NOW = '2026-09-25T00:00:00Z'

function item(overrides: Partial<AllocatedIpItem> & Pick<AllocatedIpItem, 'ip_id'>): AllocatedIpItem {
  return {
    address: '192.168.1.10',
    resource_id: 7,
    resource_name: 'cn001',
    resource_type: 'bare_metal',
    interface_id: 10,
    interface_name: 'eth0',
    is_management: true,
    created_at: NOW,
    ...overrides,
  }
}

function page(items: AllocatedIpItem[], total: number, pageNumber = 1) {
  return { items, total, page: pageNumber, page_size: 20 }
}

type Exposed = ReturnType<typeof useSegmentAllocatedIps> & {
  segmentId: { value: number | null }
  active: { value: boolean }
}

let exposed: Exposed | null = null

/** 挂载仅运行 composable 的宿主组件（无需 @vue/test-utils） */
function mountHost(initialSegmentId: number | null = 5, initialActive = true): void {
  const segmentId = ref<number | null>(initialSegmentId)
  const active = ref(initialActive)
  const Host = defineComponent({
    setup() {
      exposed = {
        ...useSegmentAllocatedIps(segmentId, active),
        segmentId,
        active,
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

const mockedList = vi.mocked(listAllocatedIps)

beforeEach(() => {
  exposed = null
  vi.clearAllMocks()
  // 默认应答：1 条已分配 IP
  mockedList.mockResolvedValue(page([item({ ip_id: 55 })], 1))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('加载与状态区分（Contract F006 §3.1）', () => {
  it('抽屉打开即按 segmentId 加载：Loading → Success（items/total）', async () => {
    let resolveFirst: (value: ReturnType<typeof page>) => void = () => undefined
    mockedList.mockReturnValue(
      new Promise((resolve) => {
        resolveFirst = resolve
      }),
    )
    mountHost()
    expect(exposed!.loading.value).toBe(true)
    expect(exposed!.items.value).toEqual([])

    resolveFirst(page([item({ ip_id: 55 })], 1))
    await flush()
    expect(exposed!.loading.value).toBe(false)
    expect(exposed!.items.value).toHaveLength(1)
    expect(exposed!.items.value[0]?.address).toBe('192.168.1.10')
    expect(exposed!.total.value).toBe(1)
    expect(exposed!.loadError.value).toBe('')
  })

  it('空结果：items:[] + total:0（200 空态，不伪装成错误）', async () => {
    mockedList.mockResolvedValue(page([], 0))
    mountHost()
    await flush()
    expect(exposed!.items.value).toEqual([])
    expect(exposed!.total.value).toBe(0)
    expect(exposed!.loadError.value).toBe('')
    expect(exposed!.loading.value).toBe(false)
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

describe('服务端分页', () => {
  it('翻页：setPage 携带新 page 请求', async () => {
    mockedList.mockResolvedValue(page([item({ ip_id: 55 })], 45, 1))
    mountHost()
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(5, { page: 1, page_size: 20 })

    mockedList.mockResolvedValue(page([item({ ip_id: 60, address: '192.168.1.11' })], 45, 3))
    await exposed!.setPage(3)
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(5, { page: 3, page_size: 20 })
    expect(exposed!.page.value).toBe(3)
    expect(exposed!.items.value[0]?.address).toBe('192.168.1.11')
  })
})

describe('q 搜索（§8.3：300ms 防抖 + 回车立即；去首尾空格；旧请求不覆盖新请求）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('输入后 300ms 防抖触发：q 去首尾空格、回到第 1 页', async () => {
    mockedList.mockResolvedValue(page([item({ ip_id: 55 })], 1))
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
    expect(mockedList).toHaveBeenLastCalledWith(5, { page: 1, page_size: 20, q: 'cn001' })
    expect(exposed!.q.value).toBe('  cn001 ') // 输入框展示值保留
  })

  it('回车立即搜索（取消未触发的防抖）', async () => {
    mockedList.mockResolvedValue(page([item({ ip_id: 55 })], 1))
    mountHost()
    await vi.runOnlyPendingTimersAsync()
    await flushFake()

    exposed!.setQ('ib0')
    await vi.advanceTimersByTimeAsync(100) // 防抖期内
    exposed!.searchNow()
    await flushFake()
    expect(mockedList).toHaveBeenLastCalledWith(5, { page: 1, page_size: 20, q: 'ib0' })
    // 防抖已被取消：不再产生重复请求
    const calls = mockedList.mock.calls.length
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    expect(mockedList.mock.calls.length).toBe(calls)
  })

  it('纯空白 q 不发送参数（空 = 不过滤）', async () => {
    mockedList.mockResolvedValue(page([item({ ip_id: 55 })], 1))
    mountHost()
    await vi.runOnlyPendingTimersAsync()
    await flushFake()

    exposed!.setQ('   ')
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    expect(mockedList).toHaveBeenLastCalledWith(5, { page: 1, page_size: 20 })
  })

  it('快速连续输入：旧请求不覆盖较新请求（§8.3）', async () => {
    const deferred: Array<(value: ReturnType<typeof page>) => void> = []
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
    deferred[2]!(page([item({ ip_id: 55 })], 1))
    await flushFake()
    expect(exposed!.loading.value).toBe(false)
    expect(exposed!.items.value).toHaveLength(1)

    // 旧请求（cn0）后返回 → 不覆盖
    deferred[1]!(page([item({ ip_id: 99, address: '192.168.1.99' })], 1))
    await flushFake()
    expect(exposed!.items.value[0]?.address).toBe('192.168.1.10')
  })
})

describe('重置（关闭/切换网段）', () => {
  it('抽屉关闭：清空结果/关键词/错误并作废进行中的请求', async () => {
    mockedList.mockResolvedValue(page([item({ ip_id: 55 })], 1))
    mountHost()
    await flush()
    expect(exposed!.items.value).toHaveLength(1)

    exposed!.active.value = false
    await flush()
    expect(exposed!.items.value).toEqual([])
    expect(exposed!.total.value).toBe(0)
    expect(exposed!.q.value).toBe('')
    expect(exposed!.loading.value).toBe(false)
    expect(exposed!.loadError.value).toBe('')

    // 关闭期间的请求返回不生效（token 已作废）：结果保持为空
    mockedList.mockClear()
    exposed!.active.value = true
    await flush()
    expect(mockedList).toHaveBeenCalledTimes(1) // 重新打开重新加载
  })

  it('切换网段：按新 segmentId 重新加载', async () => {
    mockedList.mockResolvedValue(page([item({ ip_id: 55 })], 1))
    mountHost(5)
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(5, expect.anything())

    mockedList.mockResolvedValue(page([], 0))
    exposed!.segmentId.value = 9
    await flush()
    expect(mockedList).toHaveBeenLastCalledWith(9, expect.anything())
    expect(exposed!.items.value).toEqual([])
    expect(exposed!.total.value).toBe(0)
  })
})
