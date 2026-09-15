import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus, { ElPagination } from 'element-plus'
import ClusterListPage from '../src/pages/ClusterListPage.vue'

/**
 * 集群列表页三态测试（AC-14 / A16）。
 *
 * F012 判据 6（前端三态基座）的验证力自 F001 起由本产品页承载：
 * 整链路 组件 → useAsyncQuery → apiRequest（fetch 桩）→ 契约响应
 * → ListStates / ErrorState 渲染。响应体严格按 docs/api/f001-cluster.md
 * 构造（列表信封 §3.2 / Empty 语义 §9 / 错误信封 §5）。
 */

const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const CLUSTER_B = {
  id: 2,
  name: 'Cluster-A',
  created_at: '2026-09-15T11:00:00Z',
  updated_at: '2026-09-15T11:30:00Z',
}

const LIST_BODY = { items: [CLUSTER_A, CLUSTER_B], total: 2, page: 1, page_size: 50 }
/** Empty 语义（契约 §9）：200 + items == [] + total == 0，不是 404。 */
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }
/** 契约 §3.2：page < 1 → 400 VALIDATION_ERROR，details[].field == "page"。 */
const PAGE_VALIDATION_ERROR_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '请求校验失败',
    details: [{ field: 'page', message: 'page 必须大于等于 1' }],
  },
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mountPage() {
  return mount(ClusterListPage, {
    global: { plugins: [ElementPlus] },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ClusterListPage 三态互不相同（AC-14）', () => {
  it('请求进行中 → Loading 态（骨架屏），不渲染 Empty / Error / 表格', async () => {
    // 用可控的 deferred 让请求保持进行中，使 Loading 态可确定性观察。
    let resolveList!: (body: unknown) => void
    const listPromise = new Promise<Response>((res) => {
      resolveList = (body: unknown) => res(jsonResponse(200, body))
    })
    vi.stubGlobal('fetch', vi.fn(async () => listPromise))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('loading')
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)

    // 让挂起的请求落地，避免测试结束后残留未决 promise。
    resolveList(EMPTY_LIST_BODY)
    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
  })

  it('200 + items 为空 → Empty 态（暂无集群），不渲染骨架屏 / Error / 表格', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无集群')
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)
  })

  it('500 INTERNAL_ERROR → Error 态，按 error.code 渲染（不解析 message）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, INTERNAL_ERROR_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(alert.text()).toContain('服务器内部错误')
    expect(alert.text()).toContain('INTERNAL_ERROR')
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无集群')
  })

  it('400 VALIDATION_ERROR（details[].field == "page"）→ Error 态展示校验失败与字段提示', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(400, PAGE_VALIDATION_ERROR_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('VALIDATION_ERROR')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('page')
    expect(wrapper.text()).not.toContain('暂无集群')
  })
})

describe('ClusterListPage 内容与分页', () => {
  it('成功 → 表格展示 id / name / created_at / updated_at（时间为契约原样字符串）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    const rows = wrapper.findAll('.el-table__row')
    expect(rows[0].text()).toContain('cluster-a')
    expect(rows[0].text()).toContain('2026-09-15T10:00:00Z')
    expect(rows[1].text()).toContain('Cluster-A')
    expect(rows[1].text()).toContain('2026-09-15T11:30:00Z')
  })

  it('分页器绑定契约信封值：total / page / page_size', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.findComponent(ElPagination).exists()).toBe(true)
    })

    const pager = wrapper.findComponent(ElPagination)
    expect(pager.props('total')).toBe(2)
    expect(pager.props('currentPage')).toBe(1)
    expect(pager.props('pageSize')).toBe(50)
  })

  it('翻页（current-change）→ 以新 page 重新请求 /api/clusters', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [CLUSTER_A], total: 120, page: 2, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    wrapper.findComponent(ElPagination).vm.$emit('current-change', 2)

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/clusters?page=2&page_size=50',
        expect.anything(),
      )
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('调整 page_size（size-change）→ 回到第 1 页并以新 page_size 请求', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [CLUSTER_A], total: 120, page: 2, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    wrapper.findComponent(ElPagination).vm.$emit('size-change', 20)

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/clusters?page=1&page_size=20',
        expect.anything(),
      )
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('点击「详情」→ emit openDetail(clusterId)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    const detailButtons = wrapper
      .findAll('button')
      .filter((button) => button.text().includes('详情'))
    expect(detailButtons).toHaveLength(2)
    await detailButtons[0].trigger('click')

    expect(wrapper.emitted('openDetail')).toEqual([[1]])
  })
})
