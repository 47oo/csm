// 远程下拉选项状态机单测（架构 F008 §4.2，需求 §8.3；FuzzySelect 数据层）：
// 300ms 防抖只发一次（连续输入重置计时）、回车立即、旧请求响应不覆盖较新请求、
// 清空回初始候选、错误态显式（可重试，不伪装成空列表）、无结果 hasNoMatch、
// 立即初始加载与分页（setPage 追加 / hasMore）。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRemoteOptions, type RemoteOptionsPage, type UseRemoteOptionsInput } from './useRemoteOptions'

interface Item {
  value: number
  label: string
}

function page(items: Array<{ value: number; label: string }>, total: number): RemoteOptionsPage<Item> {
  return { items, total }
}

function setup(
  fetcherImpl: (query: string, p: number, pageSize: number) => Promise<RemoteOptionsPage<Item>>,
  overrides: Partial<UseRemoteOptionsInput<Item>> = {},
): ReturnType<typeof useRemoteOptions<Item>> {
  return useRemoteOptions<Item>({ fetcher: fetcherImpl, ...overrides })
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

/** 假定时器下的排空 */
async function flushFake(): Promise<void> {
  for (let i = 0; i < 5; i++) await vi.advanceTimersByTimeAsync(0)
}

describe('初始加载（immediateInitial 默认 true）', () => {
  it('建立时立即以空关键词加载第 1 页（初始候选）', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([{ value: 1, label: 'a' }], 1))
    const s = setup(fetcher)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledWith('', 1, 20)
    await flushFake()
    expect(s.options.value).toHaveLength(1)
    expect(s.loading.value).toBe(false)
    expect(s.error.value).toBe('')
    expect(s.hasMore.value).toBe(false)
  })

  it('immediateInitial=false 不发起首次请求（如已提供 initialOptions）', async () => {
    const fetcher = vi.fn()
    setup(fetcher, { immediateInitial: false })
    await flushFake()
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('pageSize/debounceMs 透传给 fetcher/防抖', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([], 0))
    const s = setup(fetcher, { pageSize: 50, debounceMs: 100, immediateInitial: false })
    s.search('x')
    await vi.advanceTimersByTimeAsync(99)
    expect(fetcher).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(fetcher).toHaveBeenCalledWith('x', 1, 50)
  })
})

describe('q 防抖（§8.3：300ms 防抖只发一次）', () => {
  it('连续输入重置计时：只发一次，以最后一次为准，回到第 1 页', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([], 0))
    const s = setup(fetcher)
    s.search('c')
    s.search('cn')
    s.search('  cn001 ')
    await vi.advanceTimersByTimeAsync(300)
    expect(fetcher).toHaveBeenCalledTimes(2) // 初始 1 次 + 搜索 1 次
    expect(fetcher).toHaveBeenLastCalledWith('cn001', 1, 20)
    expect(s.query.value).toBe('  cn001 ') // 输入框展示值保留
  })
})

describe('回车立即（§8.3）', () => {
  it('searchNow 跳过防抖立即查询，且不重复请求', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([], 0))
    const s = setup(fetcher)
    s.search('cn001')
    await vi.advanceTimersByTimeAsync(100) // 防抖期内
    s.searchNow()
    await flushFake()
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(fetcher).toHaveBeenLastCalledWith('cn001', 1, 20)
    await vi.advanceTimersByTimeAsync(300)
    expect(fetcher).toHaveBeenCalledTimes(2) // 防抖已取消
  })
})

describe('竞态（§8.3：旧请求响应不覆盖较新请求）', () => {
  it('较新请求先返回生效；较旧请求后返回被丢弃', async () => {
    const deferred: Array<(p: RemoteOptionsPage<Item>) => void> = []
    const fetcher = vi.fn().mockImplementation(
      () =>
        new Promise<RemoteOptionsPage<Item>>((resolve) => {
          deferred.push(resolve)
        }),
    )
    const s = setup(fetcher)
    await flushFake()
    expect(deferred).toHaveLength(1) // 初始

    s.search('cn0')
    await vi.advanceTimersByTimeAsync(300)
    s.search('cn001') // 旧请求（cn0）尚未返回
    await vi.advanceTimersByTimeAsync(300)
    expect(deferred).toHaveLength(3)

    deferred[2]!(page([{ value: 7, label: 'new' }], 1))
    await flushFake()
    expect(s.options.value[0]?.value).toBe(7)

    deferred[1]!(page([{ value: 99, label: 'stale' }], 1))
    await flushFake()
    expect(s.options.value[0]?.value).toBe(7) // 旧响应不覆盖
    expect(s.loading.value).toBe(false)
  })
})

describe('清空回初始（§8.3）', () => {
  it('clear：关键词清空并以空关键词回到第 1 页', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([{ value: 1, label: 'a' }], 1))
    const s = setup(fetcher)
    s.search('cn001')
    await vi.advanceTimersByTimeAsync(300)
    expect(fetcher).toHaveBeenLastCalledWith('cn001', 1, 20)

    s.clear()
    await flushFake()
    expect(fetcher).toHaveBeenLastCalledWith('', 1, 20)
    expect(s.query.value).toBe('')
    expect(s.options.value).toHaveLength(1)
  })

  it('loadInitial：同样回到无 q 第 1 页（下拉打开/重载初始候选）', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([], 0))
    const s = setup(fetcher)
    s.search('x')
    await vi.advanceTimersByTimeAsync(300)
    s.loadInitial()
    await flushFake()
    expect(fetcher).toHaveBeenLastCalledWith('', 1, 20)
    expect(s.query.value).toBe('')
  })
})

describe('错误态（显式呈现，不伪装成空列表）', () => {
  it('失败：error 置文案、options 清空、loading 复位、hasNoMatch 为 false', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error('网络错误'))
    const s = setup(fetcher)
    await flushFake()
    expect(s.error.value).not.toBe('')
    expect(s.options.value).toEqual([])
    expect(s.loading.value).toBe(false)
    expect(s.hasNoMatch.value).toBe(false) // 错误不是「无结果」

    // retry 重放同参数并成功恢复
    fetcher.mockResolvedValue(page([{ value: 1, label: 'a' }], 1))
    s.retry()
    await flushFake()
    expect(s.error.value).toBe('')
    expect(s.options.value).toHaveLength(1)
  })

  it('搜索失败的 retry 重放同一关键词与页码', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([{ value: 1, label: 'a' }], 1))
    const s = setup(fetcher)
    s.search('cn001')
    await vi.advanceTimersByTimeAsync(300)
    fetcher.mockRejectedValueOnce(new Error('boom'))
    s.retry()
    await flushFake()
    expect(s.error.value).not.toBe('')
    fetcher.mockResolvedValue(page([{ value: 2, label: 'b' }], 1))
    s.retry()
    await flushFake()
    expect(fetcher).toHaveBeenLastCalledWith('cn001', 1, 20)
    expect(s.options.value[0]?.value).toBe(2)
  })
})

describe('无结果 hasNoMatch（§8.3「没有匹配项」）', () => {
  it('有效关键词无结果 → true；初始候选为空 → false（区别于「暂无数据」）', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([], 0))
    const s = setup(fetcher)
    await flushFake()
    expect(s.hasNoMatch.value).toBe(false) // 初始空 = 暂无数据

    s.search('不存在')
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    expect(s.hasNoMatch.value).toBe(true)

    // 纯空白关键词 = 不搜索 → 初始候选语义
    s.search('   ')
    await vi.advanceTimersByTimeAsync(300)
    await flushFake()
    expect(s.hasNoMatch.value).toBe(false)
  })
})

describe('分页（服务端分页加载）', () => {
  it('setPage(n>1) 追加第 n 页；hasMore 反映 total；setPage(1) 替换回第 1 页', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(page([{ value: 1, label: 'a1' }, { value: 2, label: 'a2' }], 5))
      .mockResolvedValueOnce(page([{ value: 3, label: 'a3' }], 5))
      .mockResolvedValueOnce(page([{ value: 1, label: 'a1' }, { value: 2, label: 'a2' }], 5))
    const s = setup(fetcher)
    await flushFake()
    expect(s.hasMore.value).toBe(true)

    s.setPage(2)
    await flushFake()
    expect(fetcher).toHaveBeenLastCalledWith('', 2, 20)
    expect(s.options.value.map((o) => o.value)).toEqual([1, 2, 3])
    expect(s.page.value).toBe(2)

    s.setPage(1)
    await flushFake()
    expect(s.options.value.map((o) => o.value)).toEqual([1, 2])
    expect(s.page.value).toBe(1)
  })
})
