import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPagination } from 'element-plus'
import SearchResultsPage from '../src/pages/SearchResultsPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * 搜索结果页测试（F018，T-FE-18-3 / T-FE-18-4 / T-FE-18-5 / T-FE-18-6）。
 *
 * 覆盖：
 * - **单请求**（T-FE-18-5 / AC-D4）：页面只调用唯一搜索端点
 *   GET /api/clusters/{id}/search，不做任何浏览器端拼接（不请求任何
 *   canonical 列表端点）；
 * - **三态互不相同**（T-FE-18-3 / AC-07）：Loading（骨架屏）/ Empty
 *   （200 + items == []，「无匹配结果」，非错误、不触发全局会话失效）/
 *   Error（按 error.code 分支渲染，不解析 message）互不相同；
 * - **错误按 error.code 渲染**（T-FE-18-4）：NOT_FOUND → 「未找到资源」、
 *   VALIDATION_ERROR → 校验失败、NETWORK_ERROR → 连接失败；
 * - **命中字段与混合列表**（T-FE-18-6 / AC-D4）：六类 resource_type 可读标签 +
 *   标识字段 + matched_fields 标签原样渲染；单一混合列表（不分组）；
 * - **详情导航**（T-FE-18-6）：六类结果行「查看」emit 对应导航事件。
 *
 * 响应体严格按 docs/api/f018-cluster-keyword-search.md §3 构造（元素
 * resource 逐字段复用各 canonical Read）。沿用 tests/setup/monotonic-date-now.ts。
 */

const TS = '2026-09-18T10:00:00Z'

/** 六类各一条的混合列表（契约 §3 Response 200；matched_fields 含多字段命中）。 */
const SEARCH_FULL_BODY = {
  items: [
    {
      resource_type: 'BARE_METAL',
      id: 101,
      matched_fields: ['hostname', 'gpu'],
      resource: {
        id: 101,
        cluster_id: 3,
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
      resource_type: 'NETWORK_INTERFACE',
      id: 11,
      matched_fields: ['name'],
      resource: {
        id: 11,
        bare_metal_id: 101,
        name: 'eth0-mgmt',
        technology_type: 'Ethernet',
        purpose: 'Management',
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'IP_ADDRESS',
      id: 21,
      matched_fields: ['ip_address'],
      resource: {
        id: 21,
        network_interface_id: 11,
        ip_address: '10.0.1.1/16',
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'VIRTUAL_MACHINE',
      id: 31,
      matched_fields: ['name', 'os'],
      resource: {
        id: 31,
        bare_metal_id: 101,
        name: 'vm-gpu-01',
        cpu: null,
        memory: null,
        disk: null,
        os: 'Ubuntu 22.04',
        hypervisor: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'CONTAINER',
      id: 41,
      matched_fields: ['image'],
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
    {
      resource_type: 'SERVICE',
      id: 51,
      matched_fields: ['name', 'port'],
      resource: {
        id: 51,
        name: 'svc-gpu',
        service_type: null,
        url: null,
        port: '8443',
        protocol: null,
        owner: null,
        description: null,
        carriers: [{ carrier_type: 'BARE_METAL', carrier_id: 101 }],
        created_at: TS,
        updated_at: TS,
      },
    },
  ],
  total: 6,
  page: 1,
  page_size: 50,
}

const SEARCH_EMPTY_BODY = { items: [], total: 0, page: 1, page_size: 50 }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/**
 * 搜索页 fetch 桩：全部请求按同一响应工厂应答（页面只应请求搜索端点；
 * 其他端点若被请求会以 404 兜底并在「单请求」断言中暴露）。
 */
function stubFetch(respond: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL) => respond())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountSearchResultsPage(props?: { clusterId?: number; keyword?: string }) {
  return mount(SearchResultsPage, {
    props: {
      clusterId: props?.clusterId ?? 3,
      keyword: props?.keyword ?? 'gpu',
    },
    global: { plugins: [ElementPlus] },
  })
}

/**
 * vi.waitFor 包装：全量并行负载下页面挂载偶发超过默认 1s（与既有 spec
 * 相同），仅放宽时序上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/** 结果页根节点的当前 ListStates 状态（loading / error / empty / content）。 */
function listState(wrapper: VueWrapper): string {
  const states = wrapper.find('.list-states')
  expect(states.exists(), '期望存在 .list-states').toBe(true)
  return states.attributes('data-state') ?? ''
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('SearchResultsPage 三态互不相同（T-FE-18-3 / AC-07）', () => {
  it('请求进行中 → Loading 态（骨架屏）', async () => {
    let resolveSearch!: (body: unknown) => void
    const pending = new Promise<Response>((res) => {
      resolveSearch = (body: unknown) => res(jsonResponse(200, body))
    })
    stubFetch(() => pending)

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(listState(wrapper)).toBe('loading')
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    // Loading 态不渲染表格 / Empty / Error。
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    resolveSearch(SEARCH_FULL_BODY)
    await waitForUi(() => {
      expect(listState(wrapper)).toBe('content')
    })
  })

  it('Cluster 活跃但无命中 → Empty 态（「无匹配结果」），非错误、不触发全局 401', async () => {
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)
    stubFetch(() => jsonResponse(200, SEARCH_EMPTY_BODY))

    const wrapper = mountSearchResultsPage({ keyword: 'zzz' })
    await waitForUi(() => {
      expect(listState(wrapper)).toBe('empty')
    })

    // Empty 文案（R-QUERY-004 Empty 语义，AC-D4）。
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('无匹配结果')
    // Empty 不是错误：不渲染 ErrorState / 表格。
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)
    // Empty（200 + 空列表）不触发全局会话失效。
    expect(unauthenticated).not.toHaveBeenCalled()
  })

  it('Cluster 不存在或已逻辑删除 → Error 态（NOT_FOUND →「未找到资源」），与 Empty 可区分', async () => {
    stubFetch(() =>
      jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在或已被逻辑删除', details: [] } }),
    )

    const wrapper = mountSearchResultsPage({ clusterId: 999 })
    await waitForUi(() => {
      expect(listState(wrapper)).toBe('error')
    })

    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('未找到资源')
    // 与 Empty 不同的 data-state 与不同文案。
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('无匹配结果')
  })
})

describe('SearchResultsPage 错误按 error.code 渲染，不解析 message（T-FE-18-4 / AC-07）', () => {
  it('VALIDATION_ERROR → 校验失败文案（服务端裁决，前端不重复实现校验）', async () => {
    stubFetch(() =>
      jsonResponse(400, {
        error: {
          code: 'VALIDATION_ERROR',
          message: '与展示无关的服务端错误文案',
          details: [{ field: 'keyword', code: 'INVALID', message: '关键字不能为空' }],
        },
      }),
    )

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(listState(wrapper)).toBe('error')
    })

    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('请求校验失败')
  })

  it('网络失败 → NETWORK_ERROR → 连接失败文案', async () => {
    stubFetch(() => {
      throw new TypeError('fetch failed')
    })

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(listState(wrapper)).toBe('error')
    })

    const alert = wrapper.find('[data-error-code="NETWORK_ERROR"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('无法连接服务器')
  })
})

describe('SearchResultsPage 单请求（T-FE-18-5 / AC-D4）', () => {
  it('一次搜索恰一个请求：仅调用唯一搜索端点，无任何浏览器端拼接', async () => {
    const fetchMock = stubFetch(() => jsonResponse(200, SEARCH_FULL_BODY))

    const wrapper = mountSearchResultsPage({ clusterId: 3, keyword: 'gpu' })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(6)
    })

    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls).toHaveLength(1)
    expect(urls[0]).toBe('/api/clusters/3/search?keyword=gpu&page=1&page_size=50')
    // 不请求任何 canonical 列表端点（架构裁定 1：禁止浏览器端拼接）。
    expect(urls.every((url) => url.startsWith('/api/clusters/3/search'))).toBe(true)
  })

  it('props 变化（同组件复用换关键字）→ 重置到第 1 页重新请求（仍单请求/次）', async () => {
    const fetchMock = stubFetch(() => jsonResponse(200, SEARCH_FULL_BODY))

    const wrapper = mountSearchResultsPage({ clusterId: 3, keyword: 'gpu' })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(6)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ keyword: 'abc' })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/clusters/3/search?keyword=abc&page=1&page_size=50',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('分页换页 → 携带 page 参数重新请求（消费契约分页信封）', async () => {
    const fetchMock = stubFetch(() => jsonResponse(200, SEARCH_FULL_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(6)
    })

    const pager = wrapper.findComponent(ElPagination)
    expect(pager.exists()).toBe(true)
    expect(pager.props('total')).toBe(6)
    expect(pager.props('currentPage')).toBe(1)

    pager.vm.$emit('current-change', 2)
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/clusters/3/search?keyword=gpu&page=2&page_size=50',
        expect.objectContaining({ method: 'GET' }),
      )
    })
  })
})

describe('SearchResultsPage 混合列表与命中字段（T-FE-18-6 / AC-D4）', () => {
  it('六类结果混合呈现：resource_type 可读标签 + 标识字段 + matched_fields 原样标签，不分组', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_FULL_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(6)
    })

    const rows = wrapper.findAll('.el-table__row')
    // 单一混合列表（同一表格、不分组）：按返回顺序原样渲染（不承诺排序）。
    const texts = rows.map((row) => row.text())
    expect(texts[0]).toContain('裸金属')
    expect(texts[0]).toContain('cn001-gpu')
    expect(texts[0]).toContain('hostname')
    expect(texts[0]).toContain('gpu')
    expect(texts[1]).toContain('网络接口')
    expect(texts[1]).toContain('eth0-mgmt')
    expect(texts[1]).toContain('name')
    expect(texts[2]).toContain('IP 地址')
    expect(texts[2]).toContain('10.0.1.1/16')
    expect(texts[2]).toContain('ip_address')
    expect(texts[3]).toContain('虚拟机')
    expect(texts[3]).toContain('vm-gpu-01')
    expect(texts[3]).toContain('os')
    expect(texts[4]).toContain('容器')
    expect(texts[4]).toContain('web')
    expect(texts[4]).toContain('image')
    expect(texts[5]).toContain('服务')
    expect(texts[5]).toContain('svc-gpu')
    expect(texts[5]).toContain('port')
    // 搜索上下文可见（范围 Cluster 与关键字，原样值）。
    expect(wrapper.text()).toContain('集群 #3')
    expect(wrapper.text()).toContain('关键字「gpu」')
    // total 展示（契约信封）。
    expect(wrapper.text()).toContain('6')
  })

  it('六类结果行「查看」→ emit 对应导航事件（复用既有 open*Detail 链路）', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_FULL_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('[data-testid="search-result-detail"]')).toHaveLength(6)
    })

    const detailButtons = wrapper.findAll('[data-testid="search-result-detail"]')
    for (const button of detailButtons) {
      await button.trigger('click')
    }

    expect(wrapper.emitted('openBareMetalDetail')).toEqual([[101]])
    expect(wrapper.emitted('openNetworkInterfaceDetail')).toEqual([[11]])
    expect(wrapper.emitted('openIpAddressDetail')).toEqual([[21]])
    expect(wrapper.emitted('openVirtualMachineDetail')).toEqual([[31]])
    expect(wrapper.emitted('openContainerDetail')).toEqual([[41]])
    expect(wrapper.emitted('openServiceDetail')).toEqual([[51]])
  })

  it('「返回集群列表」→ emit back（App 侧接线回集群列表）', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_FULL_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(6)
    })

    const backButton = wrapper.findAll('button').find((b) => b.text() === '返回集群列表')
    expect(backButton, '期望找到「返回集群列表」按钮').toBeDefined()
    await backButton!.trigger('click')

    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})
