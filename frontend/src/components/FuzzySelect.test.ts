// 统一模糊搜索下拉单测（架构 F008 §4.2/§4.1，需求 §8.3、场景 41）：
// 稳定 ID 提交（非展示文本）、未匹配自由文本不提交且失焦回退、Esc 关闭保留已选值、
// 清空回到初始候选、无结果「没有匹配项」、防抖查询与回车立即、错误显式（可重试）。
// 数据层 useRemoteOptions 的状态机细节见 composables/useRemoteOptions.test.ts。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import ElementPlus from 'element-plus'
import FuzzySelect from './FuzzySelect.vue'
import { ApiError } from '../api/client'
import type { SearchOption, SearchOptionsPage } from '../utils/searchOptions'

const INITIAL: SearchOption[] = [
  { value: 1, label: 'N96P 生产集群' },
  { value: 2, label: 'N97P 测试集群' },
]

const MATCHED: SearchOption[] = [{ value: 42, label: 'cn001 · 192.168.1.10' }]

function page(items: SearchOption[], total = items.length): SearchOptionsPage {
  return { items, total }
}

type Recorded = {
  update: Array<unknown>
  change: Array<unknown>
  select: Array<unknown>
  clear: number
  noMatch: Array<unknown>
  error: Array<unknown>
}

let fetcher: ReturnType<typeof vi.fn>
let recorded: Recorded
let app: ReturnType<typeof createApp> | null = null
let exposed: {
  focus: () => void
  blur: () => void
  clear: () => void
  reload: () => void
  open: () => void
} | null = null

function mountSelect(props: Record<string, unknown> = {}): void {
  recorded = { update: [], change: [], select: [], clear: 0, noMatch: [], error: [] }
  const value = ref<number | string | Array<number | string> | null>(null)
  const Host = defineComponent({
    setup() {
      return () =>
        h(FuzzySelect, {
          ref: (r: unknown) => {
            exposed = r as typeof exposed
          },
          modelValue: value.value,
          fetcher,
          ...props,
          'onUpdate:modelValue': (v: number | string | null | Array<number | string>) => {
            value.value = v
            recorded.update.push(v)
          },
          onChange: (v: unknown) => recorded.change.push(v),
          onSelect: (o: unknown) => recorded.select.push(o),
          onClear: () => {
            recorded.clear += 1
          },
          onNoMatch: (q: unknown) => recorded.noMatch.push(q),
          onError: (e: unknown) => recorded.error.push(e),
        })
    },
  })
  app = createApp(Host)
  app.use(ElementPlus)
  app.mount(document.body.appendChild(document.createElement('div')))
}

async function flush(ticks = 12): Promise<void> {
  for (let i = 0; i < ticks; i++) await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  for (let i = 0; i < ticks; i++) await nextTick()
}

/** 等待真实防抖（默认 300ms）到期 */
async function waitForDebounce(ms = 380): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms))
  await flush()
}

function filterInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input.el-select__input')
  expect(input).not.toBeNull()
  return input!
}

function dropdownItems(): Array<HTMLElement> {
  return Array.from(document.querySelectorAll('.el-select-dropdown__item'))
}

function openDropdown(): void {
  const input = filterInput()
  input.dispatchEvent(new FocusEvent('focus', { bubbles: true }))
  input.click()
}

async function typeQuery(query: string): Promise<void> {
  const input = filterInput()
  input.value = query
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flush()
}

function pressKey(key: string): void {
  filterInput().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
}

/** 关闭下拉（点击外部） */
async function clickOutside(): Promise<void> {
  document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  document.body.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  await flush()
}

beforeEach(() => {
  document.body.innerHTML = ''
  exposed = null
  fetcher = vi.fn().mockResolvedValue(page(INITIAL))
})

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('初始候选与稳定 ID 提交（§4.1 #10、场景 41）', () => {
  it('挂载即加载初始候选（fetcher("", 1, pageSize)）；打开下拉展示', async () => {
    mountSelect()
    await flush()
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledWith('', 1, 20)

    openDropdown()
    await flush()
    expect(dropdownItems().map((el) => el.textContent?.trim())).toEqual([
      'N96P 生产集群',
      'N97P 测试集群',
    ])
  })

  it('选中提交稳定 ID（value），不提交展示文本；select 事件携带选项对象', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    const target = dropdownItems().find((el) => el.textContent?.includes('N96P'))!
    target.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(recorded.update).toEqual([1])
    expect(recorded.change).toEqual([1])
    expect(recorded.select).toEqual([{ value: 1, label: 'N96P 生产集群' }])
    // 展示文本来自选中项 label
    expect(document.querySelector('.el-select__wrapper')?.textContent).toContain('N96P 生产集群')
  })

  it('initialOptions：提供则免首次请求，直接作为初始候选', async () => {
    mountSelect({ initialOptions: INITIAL })
    await flush()
    expect(fetcher).not.toHaveBeenCalled()
    openDropdown()
    await flush()
    expect(dropdownItems()).toHaveLength(2)
  })
})

describe('远程查询（§8.3 防抖 / 回车立即）', () => {
  it('输入防抖后以关键词查询（服务端匹配，q 去首尾空格）', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    fetcher.mockClear()
    await typeQuery('  N96P ')
    await waitForDebounce()
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledWith('N96P', 1, 20)
  })

  it('回车立即查询（无高亮项时跳过防抖）', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    fetcher.mockClear()
    await typeQuery('N96')
    pressKey('Enter')
    await flush()
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledWith('N96', 1, 20)
  })
})

describe('未匹配自由文本不提交、失焦回退（§4.1 #11、场景 41）', () => {
  it('输入未匹配文本后失焦：不提交任何值，展示回退到上次有效选择', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    // 先做一次有效选择
    const target = dropdownItems()[0]!
    target.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(recorded.update).toEqual([1])
    recorded.update = []

    // 重新打开输入未匹配文本（fetcher 返回空）
    fetcher.mockResolvedValue(page([]))
    openDropdown()
    await flush()
    await typeQuery('不存在的输入')
    await waitForDebounce()
    await clickOutside()
    expect(recorded.update).toEqual([]) // 未匹配不提交
    // 失焦回退：输入清空，展示回退到已选 label
    expect(filterInput().value).toBe('')
    expect(document.querySelector('.el-select__wrapper')?.textContent).toContain('N96P 生产集群')
  })
})

describe('Esc 关闭（§4.1 #5）', () => {
  it('Esc 关闭下拉并保留已选值；不产生提交', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    const target = dropdownItems()[0]!
    target.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    recorded.update = []

    openDropdown()
    await flush()
    await typeQuery('N9')
    pressKey('Escape')
    await flush()
    expect(recorded.update).toEqual([]) // Esc 不提交
    expect(document.querySelector('.el-select__wrapper')?.textContent).toContain('N96P 生产集群')
  })
})

describe('清空回到初始候选（§4.1 #7）', () => {
  it('清除按钮：提交 null、发出 clear，并以空关键词回到初始候选', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    const target = dropdownItems()[0]!
    target.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(recorded.update).toEqual([1])
    // 从选中后状态开始验证清除语义
    recorded.update = []
    recorded.change = []
    recorded.select = []

    fetcher.mockClear()
    fetcher.mockResolvedValue(page(INITIAL))
    const input = filterInput()
    input.dispatchEvent(new FocusEvent('focus', { bubbles: true }))
    await flush()
    const clearIcon = document.querySelector('.el-select__clear')
    expect(clearIcon).not.toBeNull()
    clearIcon!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(recorded.update).toEqual([null])
    expect(recorded.change).toEqual([null])
    expect(recorded.select).toEqual([null])
    expect(recorded.clear).toBe(1)
    // 回到初始候选（无 q 第 1 页）
    expect(fetcher).toHaveBeenCalledWith('', 1, 20)
    expect(document.querySelector('.el-select__wrapper')?.textContent).not.toContain('N96P 生产集群')
  })

  it('exposed.clear()：程序化清空同语义', async () => {
    mountSelect()
    await flush()
    exposed!.clear()
    await flush()
    expect(recorded.update).toEqual([null])
    expect(recorded.clear).toBe(1)
    expect(fetcher).toHaveBeenCalledWith('', 1, 20)
  })
})

describe('无结果文案与事件（§4.1 #6）', () => {
  it('关键词无结果显示「没有匹配项」并发出 no-match', async () => {
    fetcher.mockResolvedValue(page([]))
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    await typeQuery('不存在')
    await waitForDebounce()
    expect(dropdownItems()).toHaveLength(0)
    expect(document.querySelector('.el-select-dropdown')?.textContent).toContain('没有匹配项')
    expect(recorded.noMatch).toEqual(['不存在'])
  })
})

describe('错误显式呈现（不伪装成空列表）', () => {
  it('加载失败显示错误与重试；重试成功恢复候选', async () => {
    fetcher.mockRejectedValueOnce(
      new ApiError(0, 'NETWORK_ERROR', '网络错误，请检查与服务器的连接后重试'),
    )
    mountSelect()
    await flush()
    expect(recorded.error).toHaveLength(1)

    openDropdown()
    await flush()
    const dropdownText = document.querySelector('.el-select-dropdown')?.textContent ?? ''
    expect(dropdownText).toContain('网络错误')
    expect(dropdownText).toContain('重试')
    expect(dropdownText).not.toContain('没有匹配项')

    fetcher.mockResolvedValue(page(INITIAL))
    const retryButton = Array.from(document.querySelectorAll('.el-select-dropdown button')).find(
      (b) => b.textContent?.includes('重试'),
    )
    expect(retryButton).toBeDefined()
    retryButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(dropdownItems().map((el) => el.textContent?.trim())).toEqual([
      'N96P 生产集群',
      'N97P 测试集群',
    ])
  })
})

describe('Exposed：open / reload', () => {
  it('open() 打开下拉；reload() 重新加载初始候选', async () => {
    mountSelect()
    await flush()
    exposed!.open()
    await flush()
    expect(dropdownItems()).toHaveLength(2)

    fetcher.mockClear()
    fetcher.mockResolvedValue(page(MATCHED))
    exposed!.reload()
    await flush()
    expect(fetcher).toHaveBeenCalledWith('', 1, 20)
    openDropdown()
    await flush()
    expect(dropdownItems().map((el) => el.textContent?.trim())).toEqual(['cn001 · 192.168.1.10'])
  })
})
