// 页面搜索输入状态机单测（架构 F008 §4.2，需求 §8.3）：从 useResourceList 抽取的
// 通用能力——300ms 防抖（连续输入重置计时、去首尾空格）、回车立即（取消未触发的防抖）、
// 清空回初始、请求序号竞态（beginLoad/isCurrent/invalidate）、resetQuiet 不触发搜索。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSearchInput } from './useSearchInput'

let onSearch: ReturnType<typeof vi.fn>

function setup(): ReturnType<typeof useSearchInput> {
  onSearch = vi.fn()
  return useSearchInput({ onSearch })
}

beforeEach(() => {
  vi.useFakeTimers()
  onSearch = vi.fn()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('q 防抖（§8.3：输入后约 300ms 自动更新）', () => {
  it('输入后 300ms 触发一次：关键词去首尾空格', () => {
    const s = setup()
    s.setQ('  cn001 ')
    expect(onSearch).not.toHaveBeenCalled()
    vi.advanceTimersByTime(300)
    expect(onSearch).toHaveBeenCalledTimes(1)
    expect(onSearch).toHaveBeenCalledWith('cn001')
    expect(s.q.value).toBe('  cn001 ') // 输入框展示值保留
    expect(s.appliedQ.value).toBe('cn001')
  })

  it('快速连续输入重置计时：只发一次，以最后一次为准', () => {
    const s = setup()
    s.setQ('c')
    vi.advanceTimersByTime(200)
    s.setQ('cn')
    vi.advanceTimersByTime(200) // 距首次输入 400ms，但距重置仅 200ms
    expect(onSearch).not.toHaveBeenCalled()
    vi.advanceTimersByTime(100)
    expect(onSearch).toHaveBeenCalledTimes(1)
    expect(onSearch).toHaveBeenCalledWith('cn')
  })

  it('纯空白输入：归一为空串（= 不搜索 / 初始候选）', () => {
    const s = setup()
    s.setQ('   ')
    vi.advanceTimersByTime(300)
    expect(onSearch).toHaveBeenCalledWith('')
  })
})

describe('回车立即（§8.3）', () => {
  it('跳过防抖立即触发，并取消未触发的防抖（不重复请求）', () => {
    const s = setup()
    s.setQ('cn001')
    vi.advanceTimersByTime(100) // 防抖期内
    s.searchNow()
    expect(onSearch).toHaveBeenCalledTimes(1)
    expect(onSearch).toHaveBeenCalledWith('cn001')
    // 防抖已被取消：不再产生第二次触发
    vi.advanceTimersByTime(300)
    expect(onSearch).toHaveBeenCalledTimes(1)
  })
})

describe('清空回初始（§8.3：清空关键词后回到初始候选）', () => {
  it('clear：关键词清空并立即以空关键词触发', () => {
    const s = setup()
    s.setQ('cn001')
    vi.advanceTimersByTime(300)
    expect(onSearch).toHaveBeenCalledWith('cn001')

    s.clear()
    expect(onSearch).toHaveBeenLastCalledWith('')
    expect(s.q.value).toBe('')
    expect(s.appliedQ.value).toBe('')
    vi.advanceTimersByTime(300)
    expect(onSearch).toHaveBeenCalledTimes(2) // 无重复触发
  })

  it('resetQuiet：取消未触发的防抖且不触发搜索（供整表重置）', () => {
    const s = setup()
    s.setQ('cn001')
    s.resetQuiet()
    vi.advanceTimersByTime(300)
    expect(onSearch).not.toHaveBeenCalled()
    expect(s.q.value).toBe('')
    expect(s.appliedQ.value).toBe('')
  })
})

describe('请求序号竞态（§8.3：旧请求不覆盖较新请求）', () => {
  it('beginLoad 返回递增序号；仅最新请求 isCurrent', () => {
    const s = setup()
    const first = s.beginLoad()
    expect(s.isCurrent(first)).toBe(true)
    const second = s.beginLoad()
    expect(s.isCurrent(first)).toBe(false)
    expect(s.isCurrent(second)).toBe(true)
  })

  it('搜索触发同样推进序号：onSearch 内捕获的旧加载被作废', () => {
    const loads: number[] = []
    const s = useSearchInput({
      onSearch: () => {
        loads.push(s.beginLoad())
      },
    })
    s.setQ('a')
    vi.advanceTimersByTime(300)
    s.setQ('ab')
    vi.advanceTimersByTime(300)
    // 每次搜索触发（fire）与其中每次加载（beginLoad）都推进序号；仅最后一次加载 isCurrent
    expect(loads).toEqual([2, 4])
    expect(s.isCurrent(loads[0]!)).toBe(false)
    expect(s.isCurrent(loads[1]!)).toBe(true)
  })

  it('invalidate 作废进行中的请求（如作用域清除）', () => {
    const s = setup()
    const current = s.beginLoad()
    expect(s.isCurrent(current)).toBe(true)
    s.invalidate()
    expect(s.isCurrent(current)).toBe(false)
  })
})
