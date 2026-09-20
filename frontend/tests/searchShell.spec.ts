import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * App 外壳搜索区测试（F018，T-FE-18-1 / T-FE-18-2 / T-FE-18-5 / T-FE-18-6；
 * R-QUERY-005 / AC-D5）。
 *
 * 覆盖：
 * - **前置条件**（T-FE-18-1 / T-FE-18-2）：未选 Cluster 或关键字仅空白时
 *   搜索按钮禁用、不可发起（不发任何搜索请求）；选项懒加载：首次展开
 *   选择器时 GET /api/clusters（仅一次，不在挂载时请求）；
 * - **单请求**（T-FE-18-5）：点击「搜索」→ 恰一个搜索请求
 *   （GET /api/clusters/{id}/search），无浏览器端拼接；再次触发重新请求；
 * - **详情导航与返回搜索**（T-FE-18-6）：结果行「查看」进入详情，
 *   「返回列表」回到搜索结果（携带搜索上下文重新请求）；含裸金属详情
 *   （F018 新增返回分支）与容器详情（既有 returnView 分支 widening）；
 * - 搜索视图为跨资源区域，不高亮任何导航项。
 *
 * 搜索响应体严格按 docs/api/f019-search-result-aggregation.md §4 构造
 * （F019 聚合形态：一个组织单元 = 裸金属命中行 + 容器关联行，含
 * derivation_path；resource 逐字段复用各 canonical Read）；fetch 桩替换，
 * 不触达真实后端；沿用 tests/setup/monotonic-date-now.ts。
 */

const SESSION_USER = { id: 1, username: 'admin' }
const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const CLUSTER_LIST_BODY = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }

const TS = '2026-09-18T10:00:00Z'

/**
 * 搜索响应（f019 契约 §4 聚合形态）：一个组织单元 = 裸金属命中行（keyword
 * 「gpu」命中 hostname）+ 其容器关联行（携带推导路径）。
 */
const SEARCH_BODY = {
  items: [
    {
      resource_type: 'BARE_METAL',
      id: 101,
      role: 'HIT',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: ['hostname'],
      derivation_path: null,
      resource: {
        id: 101,
        cluster_id: 1,
        hostname: 'cn001-gpu',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: '8 x A100',
        storage: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'CONTAINER',
      id: 41,
      role: 'RELATED',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'CONTAINER', id: 41 },
      ],
      resource: {
        id: 41,
        carrier_type: 'BARE_METAL',
        carrier_id: 101,
        name: 'web',
        image: 'registry/nginx:1.25',
        cpu: null,
        memory: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
}

const BARE_METAL = SEARCH_BODY.items[0]!.resource
const CONTAINER = SEARCH_BODY.items[1]!.resource

/** F010：空五类关联聚合（裸金属详情页挂载时并行请求）。 */
const RELATED_EMPTY_BODY = {
  network_interfaces: { items: [], total: 0 },
  ip_addresses: { items: [], total: 0 },
  virtual_machines: { items: [], total: 0 },
  containers: { items: [], total: 0 },
  services: { items: [], total: 0 },
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

/** 按端点分发的 fetch 桩（顺序敏感：search / 选项懒加载 / canonical 各自先行）。 */
function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/auth/session')) return jsonResponse(200, SESSION_USER)
    if (/\/api\/clusters\/\d+\/search/.test(url)) return jsonResponse(200, SEARCH_BODY)
    // 外壳选择器懒加载（与集群列表页的默认分页 URL 不同，可区分断言）。
    if (url.includes('/api/clusters?page=1&page_size=200')) return jsonResponse(200, CLUSTER_LIST_BODY)
    if (/\/api\/containers\/\d+/.test(url)) return jsonResponse(200, CONTAINER)
    if (/\/api\/bare-metals\/\d+\/related/.test(url)) return jsonResponse(200, RELATED_EMPTY_BODY)
    if (/\/api\/bare-metals\/\d+/.test(url)) return jsonResponse(200, BARE_METAL)
    if (url.includes('/api/clusters')) return jsonResponse(200, CLUSTER_LIST_BODY)
    return notFound()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountApp() {
  return mount(App, { global: { plugins: [ElementPlus] } })
}

function findButtonExact(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text() === text)
  expect(button, `期望找到文本恰为「${text}」的按钮`).toBeDefined()
  return button!
}

/** 外壳搜索按钮。 */
function searchButton(wrapper: VueWrapper) {
  const button = wrapper.find('[data-testid="shell-search"]')
  expect(button.exists(), '期望存在外壳搜索按钮').toBe(true)
  return button
}

/** 外壳搜索区的范围选择器（按 class 精确定位，避开分页内嵌 select）。 */
function findShellClusterSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('app-shell__search-cluster'))
  expect(select, '期望找到外壳范围选择器').toBeDefined()
  return select!
}

/** 搜索端点（GET /api/clusters/{id}/search）的调用次数。 */
function searchCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call) => String(call[0]).includes('/search')).length
}

/** 选项懒加载（GET /api/clusters?page=1&page_size=200）的调用次数。 */
function optionLoadCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call) =>
    String(call[0]).includes('/api/clusters?page=1&page_size=200'),
  ).length
}

/**
 * vi.waitFor 包装（与既有 spec 相同）：仅放宽时序上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/** 展开选择器（触发懒加载）并选定 Cluster。 */
async function selectSearchCluster(wrapper: VueWrapper, clusterId: number): Promise<void> {
  const select = findShellClusterSelect(wrapper)
  await select.vm.$emit('visible-change', true)
  await select.vm.$emit('update:modelValue', clusterId)
}

/** 输入关键字（el-input 以 update:modelValue 驱动）。 */
async function typeKeyword(wrapper: VueWrapper, keyword: string): Promise<void> {
  await wrapper.find('[data-testid="shell-search-keyword"]').setValue(keyword)
}

afterEach(() => {
  vi.unstubAllGlobals()
  // App 挂载时会注册全局未认证处理器，卸载后清除，保证测试隔离。
  setUnauthenticatedHandler(null)
})

describe('App 外壳搜索区：前置条件（T-FE-18-1 / T-FE-18-2 / AC-D5）', () => {
  it('未选 Cluster：按钮禁用、不可发起；挂载不预载选项，展开时懒加载且仅一次', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    // 集群列表就绪（挂载只请求列表页默认分页，不预载搜索选项）。
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(optionLoadCalls(fetchMock)).toBe(0)

    // 未选范围、未输入关键字：禁用；尝试点击也不发任何搜索请求。
    expect(searchButton(wrapper).attributes('disabled')).toBeDefined()
    await searchButton(wrapper).trigger('click')
    expect(searchCalls(fetchMock)).toBe(0)

    // 首次展开 → 懒加载选项（GET /api/clusters，page_size=200 单次取全）。
    const select = findShellClusterSelect(wrapper)
    await select.vm.$emit('visible-change', true)
    await waitForUi(() => {
      expect(optionLoadCalls(fetchMock)).toBe(1)
    })

    // 仍未选定范围：依旧禁用、不可发起。
    expect(searchButton(wrapper).attributes('disabled')).toBeDefined()
    await searchButton(wrapper).trigger('click')
    expect(searchCalls(fetchMock)).toBe(0)

    // 再次展开：选项已加载，不重复请求。
    await select.vm.$emit('visible-change', false)
    await select.vm.$emit('visible-change', true)
    expect(optionLoadCalls(fetchMock)).toBe(1)
  })

  it('已选 Cluster 但关键字为空 / 仅空白：按钮禁用、不可发起；有效关键字后可发起', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await selectSearchCluster(wrapper, 1)

    // 空关键字：禁用。
    await typeKeyword(wrapper, '')
    expect(searchButton(wrapper).attributes('disabled')).toBeDefined()
    await searchButton(wrapper).trigger('click')
    expect(searchCalls(fetchMock)).toBe(0)

    // 仅空白关键字（R-QUERY-005：不构成有效搜索）：禁用、不可发起。
    await typeKeyword(wrapper, '   ')
    expect(searchButton(wrapper).attributes('disabled')).toBeDefined()
    await searchButton(wrapper).trigger('click')
    expect(searchCalls(fetchMock)).toBe(0)

    // 有效关键字：按钮可用。
    await typeKeyword(wrapper, 'gpu')
    await waitForUi(() => {
      expect(searchButton(wrapper).attributes('disabled')).toBeUndefined()
    })
  })
})

describe('App 外壳搜索：发起、单请求与结果视图（T-FE-18-5 / AC-D4）', () => {
  it('点击「搜索」→ 搜索结果视图：恰一个搜索请求；无导航高亮；再次触发重新请求', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await selectSearchCluster(wrapper, 1)
    await typeKeyword(wrapper, 'gpu')
    await waitForUi(() => {
      expect(searchButton(wrapper).attributes('disabled')).toBeUndefined()
    })
    await searchButton(wrapper).trigger('click')

    // 搜索结果视图：聚合列表渲染（裸金属命中行 + 容器关联行同表、不分区）。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('搜索结果')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    expect(wrapper.text()).toContain('cn001-gpu')
    expect(wrapper.text()).toContain('web')
    // 命中 / 关联行徽标可区分（F019 聚合视图）。
    expect(wrapper.text()).toContain('命中')
    expect(wrapper.text()).toContain('关联')
    expect(wrapper.text()).toContain('裸金属 cn001-gpu → 容器 web')
    // 搜索上下文（范围 Cluster 与关键字，原样值）。
    expect(wrapper.text()).toContain('集群 #1')
    expect(wrapper.text()).toContain('关键字「gpu」')

    // 单请求（T-FE-18-5）：恰一个搜索请求，无浏览器端拼接。
    expect(searchCalls(fetchMock)).toBe(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/clusters/1/search?keyword=gpu&page=1&page_size=50',
      expect.objectContaining({ method: 'GET' }),
    )

    // 搜索视图为跨资源区域：7 个导航项均不高亮。
    for (const testid of [
      'nav-clusters',
      'nav-bare-metals',
      'nav-virtual-machines',
      'nav-network-interfaces',
      'nav-ip-addresses',
      'nav-containers',
      'nav-services',
    ]) {
      expect(wrapper.find(`[data-testid="${testid}"]`).classes()).not.toContain(
        'app-shell__nav-item--active',
      )
    }

    // 同条件再次触发：强制重新挂载结果页 → 重新请求（仍单请求/次）。
    await searchButton(wrapper).trigger('click')
    await waitForUi(() => {
      expect(searchCalls(fetchMock)).toBe(2)
    })
  })

  it('结果行「查看」容器 → 容器详情 →「返回列表」→ 回到搜索结果（携带搜索上下文）', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await selectSearchCluster(wrapper, 1)
    await typeKeyword(wrapper, 'gpu')
    await waitForUi(() => {
      expect(searchButton(wrapper).attributes('disabled')).toBeUndefined()
    })
    await searchButton(wrapper).trigger('click')
    await waitForUi(() => {
      expect(wrapper.findAll('[data-testid="search-result-detail"]')).toHaveLength(2)
    })

    // 容器行（第二行）「查看」→ 容器详情（复用既有 openContainerDetail）。
    const detailButtons = wrapper.findAll('[data-testid="search-result-detail"]')
    await detailButtons[1]!.trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('容器详情')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/containers/41', expect.anything())
    })

    // 「返回列表」→ 直接回到搜索结果（SearchReturn），重新请求搜索端点。
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('搜索结果')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    expect(searchCalls(fetchMock)).toBe(2)
    expect(wrapper.text()).toContain('cn001-gpu')
  })

  it('结果行「查看」裸金属 → 裸金属详情 →「返回列表」→ 回到搜索结果', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await selectSearchCluster(wrapper, 1)
    await typeKeyword(wrapper, 'gpu')
    await waitForUi(() => {
      expect(searchButton(wrapper).attributes('disabled')).toBeUndefined()
    })
    await searchButton(wrapper).trigger('click')
    await waitForUi(() => {
      expect(wrapper.findAll('[data-testid="search-result-detail"]')).toHaveLength(2)
    })

    // 裸金属行（第一行）「查看」→ 裸金属详情。
    const detailButtons = wrapper.findAll('[data-testid="search-result-detail"]')
    await detailButtons[0]!.trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('裸金属详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('cn001-gpu')
    })

    // 「返回列表」→ 直接回到搜索结果（F018 为裸金属详情新增的返回分支）。
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('搜索结果')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    expect(searchCalls(fetchMock)).toBe(2)
  })
})
