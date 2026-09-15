import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DevSelfCheckPage from '../src/pages/DevSelfCheckPage.vue'

/**
 * dev 自检页整链路测试：组件 → useAsyncQuery → apiRequest（fetch 桩）
 * → 契约响应 → ListStates / ErrorState 三态渲染。
 *
 * 响应体严格按 docs/api/f012-project-foundation.md §4 的契约构造
 * （列表信封 / Empty 语义 / 确定性 500 错误信封）。
 */

const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function stubFoundationFetch(): void {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/_foundation/error')) {
      return jsonResponse(500, INTERNAL_ERROR_BODY)
    }
    return jsonResponse(200, EMPTY_LIST_BODY)
  })
  vi.stubGlobal('fetch', fetchMock)
}

function mountPage() {
  return mount(DevSelfCheckPage, {
    global: { plugins: [ElementPlus] },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DevSelfCheckPage 三态渲染（dev 验证面的行为基线）', () => {
  it('页面明确标注为非产品 dev 自检用途', async () => {
    stubFoundationFetch()
    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    const text = wrapper.text()
    expect(text).toContain('DEV ONLY')
    expect(text).toContain('非产品自检页')
    expect(text).toContain('/_foundation')
  })

  it('挂载后自动请求列表：先 Loading，请求成功且 items 为空 → Empty 态', async () => {
    // 用可控的 deferred 让请求保持进行中，使 Loading 态可确定性观察。
    let resolveList!: (body: unknown) => void
    const listPromise = new Promise<Response>((res) => {
      resolveList = (body: unknown) => res(jsonResponse(200, body))
    })
    vi.stubGlobal('fetch', vi.fn(async () => listPromise))

    const wrapper = mountPage()

    // 请求进行中：Loading 态（骨架屏）。
    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('loading')
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)

    // 请求完成：Empty 态（200 + items 为空数组，不是错误）。
    resolveList(EMPTY_LIST_BODY)
    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.text()).toContain('暂无数据')
    expect(wrapper.text()).toContain('items 为空数组')
  })

  it('点击「触发错误请求」：确定性 500 INTERNAL_ERROR → Error 态按 error.code 渲染', async () => {
    stubFoundationFetch()
    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    const trigger = wrapper.findAll('button').find((button) =>
      button.text().includes('触发错误请求'),
    )
    expect(trigger).toBeDefined()
    await trigger!.trigger('click')

    await vi.waitFor(() => {
      const states = wrapper.findAll('[data-state]').map((node) => node.attributes('data-state'))
      expect(states).toContain('error')
    })

    const errorCardText = wrapper.findAll('[data-state="error"]').map((n) => n.text()).join('\n')
    expect(errorCardText).toContain('服务器内部错误')
    expect(errorCardText).toContain('INTERNAL_ERROR')
    // 列表区不受影响，仍为 Empty 态。
    expect(wrapper.findAll('[data-state]').map((n) => n.attributes('data-state'))).toContain('empty')
  })
})
