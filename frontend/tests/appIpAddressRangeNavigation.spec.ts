import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * App 资源视图切换测试（F020，f020-ip-address-range-handoff.md Frontend
 * Work）：侧边栏新增「IP 地址范围段」导航入口（只增不减，既有 nav-* 全部
 * 保留），全局范围段列表（无过滤）→ 页内集群筛选（?cluster_id=）→ 范围段
 * 详情 → 返回列表；导航高亮随 ip-address-range 区域切换。仍不引入 vue-router。
 *
 * 响应体严格按 docs/api/f020-ip-address-range.md 与 f001-cluster.md /
 * f013-auth.md 构造；fetch 桩替换，不触达真实后端。
 */

const SESSION_USER = { id: 1, username: 'admin' }
const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const CLUSTER_LIST_BODY = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }
const IP_ADDRESS_RANGE_A = {
  id: 7,
  cluster_id: 1,
  start_ip: '10.0.0.1',
  end_ip: '10.0.0.255',
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
}
const IP_ADDRESS_RANGE_LIST_BODY = {
  items: [IP_ADDRESS_RANGE_A],
  total: 1,
  page: 1,
  page_size: 50,
}
/** 筛选后（cluster_id=1）的可区分响应：不同范围值，便于确定性等待重渲染。 */
const IP_ADDRESS_RANGE_B = {
  id: 8,
  cluster_id: 1,
  start_ip: '192.168.10.0',
  end_ip: '192.168.10.255',
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
}
const IP_ADDRESS_RANGE_FILTERED_LIST_BODY = {
  items: [IP_ADDRESS_RANGE_B],
  total: 1,
  page: 1,
  page_size: 50,
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function notFound(): Response {
  return jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'not found' } })
}

/** 按端点分发的 fetch 桩。 */
function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/auth/session')) return jsonResponse(200, SESSION_USER)
    if (/\/api\/ip-address-ranges\/8/.test(url)) {
      return jsonResponse(200, IP_ADDRESS_RANGE_B)
    }
    if (/\/api\/ip-address-ranges\/\d+/.test(url)) {
      return jsonResponse(200, IP_ADDRESS_RANGE_A)
    }
    if (url.includes('cluster_id=1')) {
      return jsonResponse(200, IP_ADDRESS_RANGE_FILTERED_LIST_BODY)
    }
    if (url.includes('/api/ip-address-ranges')) {
      return jsonResponse(200, IP_ADDRESS_RANGE_LIST_BODY)
    }
    if (url.includes('/api/clusters')) return jsonResponse(200, CLUSTER_LIST_BODY)
    return notFound()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountApp() {
  return mount(App, { global: { plugins: [ElementPlus] } })
}

function findButton(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text().includes(text))
  expect(button, `期望找到「${text}」按钮`).toBeDefined()
  return button!
}

/** 按精确文本找按钮（避免「详情」误匹配「返回集群详情」等包含式文案）。 */
function findButtonExact(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text() === text)
  expect(button, `期望找到文本恰为「${text}」的按钮`).toBeDefined()
  return button!
}

/**
 * vi.waitFor 包装：全量并行负载下页面挂载 / el-dialog 挂载 / 异步完成偶发超过
 * vi.waitFor 默认 1s（单文件运行稳定）。仅放宽超时上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/** 范围段列表页的集群筛选下拉（按 class 定位；外壳搜索区 / 分页器亦有 ElSelect）。 */
function findFilterSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('range-list__filter-cluster'))
  expect(select, '期望找到集群筛选下拉').toBeDefined()
  return select!
}

afterEach(() => {
  vi.unstubAllGlobals()
  // App 挂载时会注册全局未认证处理器，卸载后清除，保证测试隔离。
  setUnauthenticatedHandler(null)
})

describe('App 头部导航：全局 IP 地址范围段列表（无过滤）', () => {
  it('侧边栏存在 nav-ip-address-ranges 入口；点击 → 列表请求不带 cluster_id；返回按钮回集群列表', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    // 集群列表就绪。
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.text()).toContain('集群列表')

    // 新导航入口存在（只增不减：既有 nav-* 全部保留）。
    expect(wrapper.find('[data-testid="nav-ip-address-ranges"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-clusters"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-ip-addresses"]').exists()).toBe(true)

    // 侧边栏导航进入全局范围段列表。
    await findButton(wrapper, 'IP 地址范围段').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址范围段列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/ip-address-ranges?page=1&page_size=50',
        expect.objectContaining({ method: 'GET' }),
      )
    })
    // 无过滤上下文：返回按钮指向集群列表。
    expect(wrapper.text()).toContain('返回集群列表')

    await findButton(wrapper, '返回集群列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群列表')
    })
  })

  it('导航高亮随资源区域切换（ip-address-range 区域下「IP 地址范围段」高亮、「IP 地址」不高亮）', async () => {
    stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, 'IP 地址范围段').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址范围段列表')
    })
    const navRange = wrapper.find('[data-testid="nav-ip-address-ranges"]')
    expect(navRange.classes()).toContain('app-shell__nav-item--active')
    expect(navRange.attributes('aria-current')).toBe('true')
    // 相邻的 IP 地址区域不受影响（不同资源区域）。
    expect(wrapper.find('[data-testid="nav-ip-addresses"]').classes()).not.toContain(
      'app-shell__nav-item--active',
    )

    // 切回集群区域：高亮恢复。
    await findButton(wrapper, '集群').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群列表')
    })
    expect(wrapper.find('[data-testid="nav-ip-address-ranges"]').classes()).not.toContain(
      'app-shell__nav-item--active',
    )
    expect(wrapper.find('[data-testid="nav-clusters"]').classes()).toContain(
      'app-shell__nav-item--active',
    )
  })

  it('既有「IP 地址」导航入口不被新按钮劫持（首个子串匹配仍命中 IP 地址列表）', async () => {
    stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, 'IP 地址').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址列表')
    })
    // IP 地址区域高亮，而非范围段区域。
    expect(wrapper.find('[data-testid="nav-ip-addresses"]').classes()).toContain(
      'app-shell__nav-item--active',
    )
    expect(wrapper.find('[data-testid="nav-ip-address-ranges"]').classes()).not.toContain(
      'app-shell__nav-item--active',
    )
  })
})

describe('App 范围段视图：页内集群筛选与详情往返', () => {
  it('集群筛选 → 请求携带 cluster_id → 行「详情」→ 范围段详情 → 「返回列表」回列表', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, 'IP 地址范围段').trigger('click')
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    // 列表内容展示 start_ip – end_ip 与 cluster_id（契约原样值）。
    expect(wrapper.text()).toContain('10.0.0.1 – 10.0.0.255')

    // 页内集群筛选：展开下拉（懒加载选项）→ 选择集群 → 应用。筛选后的响应
    // 使用可区分内容（192.168.10.0 – 192.168.10.255），避免旧表格 DOM 上的
    // 竞态误判。
    const filterSelect = findFilterSelect(wrapper)
    filterSelect.vm.$emit('visible-change', true)
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes('/api/clusters')),
      ).toBe(true)
    })
    await filterSelect.vm.$emit('update:modelValue', 1)
    await wrapper.find('[data-testid="range-filter-apply"]').trigger('click')
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/ip-address-ranges?page=1&page_size=50&cluster_id=1',
        expect.objectContaining({ method: 'GET' }),
      )
    })
    // 等待筛选后的内容渲染就绪（可区分值出现 → 表格已重渲染）。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('192.168.10.0 – 192.168.10.255')
    })
    expect(wrapper.text()).toContain('集群 #1')

    // 进入范围段详情。
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址范围段详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('192.168.10.0')
    })
    // 详情视图仍属 ip-address-range 区域。
    expect(wrapper.find('[data-testid="nav-ip-address-ranges"]').classes()).toContain(
      'app-shell__nav-item--active',
    )

    // 返回列表。
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址范围段列表')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
  })
})
