// 固定枚举下拉单测（架构 F008 §4.2/§5.4，需求 §8.1–§8.3）：本地 filter-method
// 中文展示名/英文代码均可输入匹配（不区分大小写、去空格）、提交值为枚举代码（非展示文本）、
// 无结果显示「没有匹配项」、清空归一为 null。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import ElementPlus from 'element-plus'
import EnumSelect from './EnumSelect.vue'
import type { ResourceStatus } from '../api/resources'

const OPTIONS: Array<{ value: ResourceStatus; label: string }> = [
  { value: 'IDLE', label: '空闲' },
  { value: 'ALLOC', label: '已分配' },
  { value: 'DOWN', label: '宕机 / 不可用' },
  { value: 'UNKNOWN', label: '未知' },
]

type Events = {
  update: Array<string | null>
  change: Array<string | null>
}

let events: Events
let app: ReturnType<typeof createApp> | null = null

function mountSelect(props: Record<string, unknown> = {}): void {
  events = { update: [], change: [] }
  app = createApp(EnumSelect, {
    modelValue: null,
    options: OPTIONS,
    ...props,
    'onUpdate:modelValue': (v: string | null) => events.update.push(v),
    onChange: (v: string | null) => events.change.push(v),
  })
  app.use(ElementPlus)
  app.mount(document.body.appendChild(document.createElement('div')))
}

async function flush(ticks = 10): Promise<void> {
  for (let i = 0; i < ticks; i++) await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  for (let i = 0; i < ticks; i++) await nextTick()
}

function filterInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input.el-select__input')
  expect(input).not.toBeNull()
  return input!
}

function dropdownItems(): Array<HTMLElement> {
  return Array.from(document.querySelectorAll('.enum-select-dropdown .el-select-dropdown__item'))
}

function openDropdown(): void {
  filterInput().dispatchEvent(new FocusEvent('focus', { bubbles: true }))
  filterInput().click()
}

async function typeQuery(query: string): Promise<void> {
  const input = filterInput()
  input.value = query
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flush()
}

beforeEach(() => {
  document.body.innerHTML = ''
})

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('选项渲染与选择（提交值为枚举代码，非展示文本）', () => {
  it('打开下拉展示全部选项；点击选项提交 value（英文代码）', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    expect(dropdownItems().map((el) => el.textContent?.trim())).toEqual([
      '空闲',
      '已分配',
      '宕机 / 不可用',
      '未知',
    ])

    const idle = dropdownItems().find((el) => el.textContent?.trim() === '空闲')!
    idle.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(events.update).toEqual(['IDLE'])
    expect(events.change).toEqual(['IDLE'])
  })

  it('回显：modelValue=ALLOC 显示「已分配」', async () => {
    mountSelect({ modelValue: 'ALLOC' })
    await flush()
    expect(document.querySelector('.el-select__wrapper')?.textContent).toContain('已分配')
  })
})

describe('本地模糊匹配（中文展示名 / 英文代码，§8.1/§8.2）', () => {
  it('输入中文展示名过滤', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    await typeQuery('空闲')
    expect(dropdownItems().map((el) => el.textContent?.trim())).toEqual(['空闲'])
  })

  it('输入英文代码过滤：不区分大小写、去首尾空格', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    await typeQuery('  idle ')
    expect(dropdownItems().map((el) => el.textContent?.trim())).toEqual(['空闲'])

    await typeQuery('DOWN')
    expect(dropdownItems().map((el) => el.textContent?.trim())).toEqual(['宕机 / 不可用'])
  })

  it('无结果显示统一文案「没有匹配项」', async () => {
    mountSelect()
    await flush()
    openDropdown()
    await flush()
    await typeQuery('不存在的值')
    expect(dropdownItems()).toHaveLength(0)
    expect(document.querySelector('.enum-select-dropdown')?.textContent).toContain('没有匹配项')
  })
})

describe('清空（clearable）', () => {
  it('清除按钮归一为 null', async () => {
    mountSelect({ modelValue: 'IDLE', clearable: true })
    await flush()
    // 聚焦后显示清除按钮
    const input = filterInput()
    input.dispatchEvent(new FocusEvent('focus', { bubbles: true }))
    await flush()
    const clearIcon = document.querySelector('.el-select__clear')
    expect(clearIcon).not.toBeNull()
    clearIcon!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(events.update).toEqual([null])
    expect(events.change).toEqual([null])
  })
})
