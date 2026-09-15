import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ClusterDetailPage from '../src/pages/ClusterDetailPage.vue'
import ClusterListPage from '../src/pages/ClusterListPage.vue'

/**
 * 集群详情页（骨架）测试。
 *
 * - 仅呈现 Cluster 自身字段（契约 §2 封闭集合）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty 渲染不同文本与不同状态（AC-14 / A16）；
 * - 响应体严格按 docs/api/f001-cluster.md 构造；fetch 桩替换，不触达真实后端。
 */

const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mountDetailPage(clusterId = 1) {
  return mount(ClusterDetailPage, {
    props: { clusterId },
    global: { plugins: [ElementPlus] },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ClusterDetailPage 状态渲染', () => {
  it('请求进行中 → Loading 态（骨架屏）', async () => {
    let resolveDetail!: (body: unknown) => void
    const detailPromise = new Promise<Response>((res) => {
      resolveDetail = (body: unknown) => res(jsonResponse(200, body))
    })
    vi.stubGlobal('fetch', vi.fn(async () => detailPromise))

    const wrapper = mountDetailPage()

    await vi.waitFor(() => {
      expect(wrapper.attributes('data-state')).toBe('loading')
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    resolveDetail(CLUSTER_A)
    await vi.waitFor(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })
  })

  it('成功 → 仅呈现 Cluster 自身 4 个字段（原样值），无 BareMetal / 删除入口 / 跨资源内容', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, CLUSTER_A)))

    const wrapper = mountDetailPage()

    await vi.waitFor(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('集群详情')
    expect(text).toContain('cluster-a')
    // 时间为 RFC 3339 不透明字符串，原样展示（契约 §2）。
    expect(text).toContain('2026-09-15T10:00:00Z')
    // 详情页骨架边界：不呈现 BareMetal（F009）、删除入口（F014）、
    // 跨资源视图（F010）、deleted_at / 状态 / 位置字段（契约 §2）。
    expect(text).not.toContain('裸金属')
    expect(text).not.toContain('删除')
    expect(text).not.toContain('deleted_at')
    expect(text).not.toContain('状态')
  })

  it('404 NOT_FOUND → 独立的「资源不存在或已被删除」态，不渲染 Empty 文案', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))

    const wrapper = mountDetailPage(999)

    await vi.waitFor(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(alert.text()).toContain('资源不存在，或已被删除')
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无集群')
  })

  it('500 INTERNAL_ERROR → Error 态按 error.code 渲染', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, INTERNAL_ERROR_BODY)))

    const wrapper = mountDetailPage()

    await vi.waitFor(() => {
      expect(wrapper.attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(alert.text()).toContain('服务器内部错误')
  })

  it('点击「返回列表」→ emit back', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, CLUSTER_A)))

    const wrapper = mountDetailPage()
    await vi.waitFor(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const backButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('返回列表'))
    expect(backButton).toBeDefined()
    await backButton!.trigger('click')

    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})

describe('A16：详情 404 态与列表 Empty 态可区分（R-QUERY-004）', () => {
  it('两者渲染不同的状态标记与不同的文案', async () => {
    // 列表 Empty：200 + items 为空（契约 §9）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))
    const listWrapper = mount(ClusterListPage, {
      global: { plugins: [ElementPlus] },
    })
    await vi.waitFor(() => {
      expect(listWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    // 详情 404：GET /api/clusters/{id} → 404 NOT_FOUND。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))
    const detailWrapper = mountDetailPage(999)
    await vi.waitFor(() => {
      expect(detailWrapper.attributes('data-state')).toBe('not-found')
    })

    // 不同的状态标记。
    expect(listWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    expect(detailWrapper.attributes('data-state')).toBe('not-found')

    // 不同的文案：Empty 是「暂无集群」，Not Found 是「资源不存在或已被删除」。
    expect(listWrapper.text()).toContain('暂无集群')
    expect(listWrapper.text()).not.toContain('已被删除')
    expect(detailWrapper.text()).toContain('已被删除')
    expect(detailWrapper.text()).not.toContain('暂无集群')
  })
})
