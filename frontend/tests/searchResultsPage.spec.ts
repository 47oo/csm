import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPagination } from 'element-plus'
import SearchResultsPage from '../src/pages/SearchResultsPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * 搜索结果页测试（F019 聚合视图，T-FE-19-1 / T-FE-19-2 / T-FE-19-3）。
 *
 * 覆盖：
 * - **三态互不相同**（T-FE-19-2 / AC-07）：Loading（骨架屏）/ Empty
 *   （200 + items == []，「无匹配结果」，非错误、不触发全局会话失效）/
 *   Error（按 error.code 分支渲染，不解析 message）互不相同；Empty 与
 *   Not Found（404）可区分；
 * - **聚合视图渲染**（T-FE-19-1 / AC-A1 / A2 / A5 / A8）：单一扁平列表按
 *   items 顺序渲染；每个组织单元（连续相同 group_key）命中行（徽标「命中」）
 *   居首、关联行（徽标「关联」+ 缩进）紧随；derivation_path 生成路径文案
 *   （首 = 命中项、末 = 本行）；matched_fields 原样标签（含自身也命中的
 *   关联行）；跨单元不去重（同一资源多单元重复出现）；
 * - **单请求**（T-FE-19-3 / AC-06）：页面只调用唯一搜索端点
 *   GET /api/clusters/{id}/search，不做任何浏览器端拼接 / 关联推导；
 * - **分页**（契约 §3 语义 4）：按 total（组织单元数）驱动；len(items)
 *   可大于 total / page_size；换页携带 page 参数重新请求；
 * - **详情导航**：六类资源行（命中行与关联行同权）「查看」emit 对应导航事件。
 *
 * 响应体严格按 docs/api/f019-search-result-aggregation.md §4 构造（行含
 * role / group_key / matched_fields / derivation_path；resource 逐字段复用
 * 各 canonical Read）。沿用 tests/setup/monotonic-date-now.ts。
 */

const TS = '2026-09-18T10:00:00Z'

/** 裸金属 cn001-gpu（id 101）挂 eth0-mgmt（id 11）与 10.0.1.1/16（id 21），宿 vm-gpu-01（id 31）。 */
const BM_101 = {
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
}
const NIC_11 = {
  id: 11,
  bare_metal_id: 101,
  name: 'eth0-mgmt',
  technology_type: 'Ethernet',
  purpose: 'Management',
  created_at: TS,
  updated_at: TS,
}
const IP_21 = {
  id: 21,
  network_interface_id: 11,
  ip_address: '10.0.1.1/16',
  created_at: TS,
  updated_at: TS,
}
const VM_31 = {
  id: 31,
  bare_metal_id: 101,
  name: 'vm-gpu-01',
  cpu: null,
  memory: null,
  disk: null,
  os: null,
  hypervisor: null,
  owner: null,
  created_at: TS,
  updated_at: TS,
}

/**
 * 聚合响应 A（契约 §4；关键字「gpu」命中 cn001-gpu 的 hostname 与 vm-gpu-01
 * 的 name，两个组织单元）：单元 1 = 裸金属命中行 + NIC/IP/VM 关联行；单元 2 =
 * 虚拟机命中行 + 裸金属/NIC/IP 关联行。四类资源跨单元各出现两次（AC-A5 不去重）；
 * VM 在单元 1 为关联行但自身命中（matched_fields 非空，PROPOSED-1）。
 */
const SEARCH_AGGREGATION_BODY = {
  items: [
    {
      resource_type: 'BARE_METAL',
      id: 101,
      role: 'HIT',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: ['hostname'],
      derivation_path: null,
      resource: BM_101,
    },
    {
      resource_type: 'NETWORK_INTERFACE',
      id: 11,
      role: 'RELATED',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'NETWORK_INTERFACE', id: 11 },
      ],
      resource: NIC_11,
    },
    {
      resource_type: 'IP_ADDRESS',
      id: 21,
      role: 'RELATED',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'NETWORK_INTERFACE', id: 11 },
        { resource_type: 'IP_ADDRESS', id: 21 },
      ],
      resource: IP_21,
    },
    {
      resource_type: 'VIRTUAL_MACHINE',
      id: 31,
      role: 'RELATED',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: ['name'],
      derivation_path: [
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'VIRTUAL_MACHINE', id: 31 },
      ],
      resource: VM_31,
    },
    {
      resource_type: 'VIRTUAL_MACHINE',
      id: 31,
      role: 'HIT',
      group_key: { resource_type: 'VIRTUAL_MACHINE', id: 31 },
      matched_fields: ['name'],
      derivation_path: null,
      resource: VM_31,
    },
    {
      resource_type: 'BARE_METAL',
      id: 101,
      role: 'RELATED',
      group_key: { resource_type: 'VIRTUAL_MACHINE', id: 31 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'VIRTUAL_MACHINE', id: 31 },
        { resource_type: 'BARE_METAL', id: 101 },
      ],
      resource: BM_101,
    },
    {
      resource_type: 'NETWORK_INTERFACE',
      id: 11,
      role: 'RELATED',
      group_key: { resource_type: 'VIRTUAL_MACHINE', id: 31 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'VIRTUAL_MACHINE', id: 31 },
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'NETWORK_INTERFACE', id: 11 },
      ],
      resource: NIC_11,
    },
    {
      resource_type: 'IP_ADDRESS',
      id: 21,
      role: 'RELATED',
      group_key: { resource_type: 'VIRTUAL_MACHINE', id: 31 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'VIRTUAL_MACHINE', id: 31 },
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'NETWORK_INTERFACE', id: 11 },
        { resource_type: 'IP_ADDRESS', id: 21 },
      ],
      resource: IP_21,
    },
  ],
  total: 2,
  page: 1,
  page_size: 50,
}

/**
 * 聚合响应 B（关键字「10」六类各命中一项，六个组织单元 / 12 行）：覆盖六类
 * resource_type 的命中行与关联行（含「仅命中行、无关联行」的最小单元：裸金属
 * cn101 无关联资源）。
 */
const SEARCH_SIX_TYPES_BODY = {
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
        cluster_id: 3,
        hostname: 'cn101',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: null,
        storage: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'NETWORK_INTERFACE',
      id: 11,
      role: 'HIT',
      group_key: { resource_type: 'NETWORK_INTERFACE', id: 11 },
      matched_fields: ['name'],
      derivation_path: null,
      resource: {
        id: 11,
        bare_metal_id: 102,
        name: 'eth10',
        technology_type: 'Ethernet',
        purpose: 'Management',
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'BARE_METAL',
      id: 102,
      role: 'RELATED',
      group_key: { resource_type: 'NETWORK_INTERFACE', id: 11 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'NETWORK_INTERFACE', id: 11 },
        { resource_type: 'BARE_METAL', id: 102 },
      ],
      resource: {
        id: 102,
        cluster_id: 3,
        hostname: 'cn002',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: null,
        storage: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'IP_ADDRESS',
      id: 21,
      role: 'HIT',
      group_key: { resource_type: 'IP_ADDRESS', id: 21 },
      matched_fields: ['ip_address'],
      derivation_path: null,
      resource: {
        id: 21,
        network_interface_id: 12,
        ip_address: '10.0.1.1/16',
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'BARE_METAL',
      id: 103,
      role: 'RELATED',
      group_key: { resource_type: 'IP_ADDRESS', id: 21 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'IP_ADDRESS', id: 21 },
        { resource_type: 'NETWORK_INTERFACE', id: 12 },
        { resource_type: 'BARE_METAL', id: 103 },
      ],
      resource: {
        id: 103,
        cluster_id: 3,
        hostname: 'cn003',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: null,
        storage: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'NETWORK_INTERFACE',
      id: 12,
      role: 'RELATED',
      group_key: { resource_type: 'IP_ADDRESS', id: 21 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'IP_ADDRESS', id: 21 },
        { resource_type: 'NETWORK_INTERFACE', id: 12 },
      ],
      resource: {
        id: 12,
        bare_metal_id: 103,
        name: 'ib0',
        technology_type: 'InfiniBand',
        purpose: 'Compute',
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'VIRTUAL_MACHINE',
      id: 31,
      role: 'HIT',
      group_key: { resource_type: 'VIRTUAL_MACHINE', id: 31 },
      matched_fields: ['name'],
      derivation_path: null,
      resource: {
        id: 31,
        bare_metal_id: 104,
        name: 'vm-10',
        cpu: null,
        memory: null,
        disk: null,
        os: null,
        hypervisor: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'BARE_METAL',
      id: 104,
      role: 'RELATED',
      group_key: { resource_type: 'VIRTUAL_MACHINE', id: 31 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'VIRTUAL_MACHINE', id: 31 },
        { resource_type: 'BARE_METAL', id: 104 },
      ],
      resource: {
        id: 104,
        cluster_id: 3,
        hostname: 'cn004',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: null,
        storage: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'CONTAINER',
      id: 41,
      role: 'HIT',
      group_key: { resource_type: 'CONTAINER', id: 41 },
      matched_fields: ['name'],
      derivation_path: null,
      resource: {
        id: 41,
        carrier_type: 'BARE_METAL',
        carrier_id: 105,
        name: 'web-10',
        image: 'registry/nginx:1.25',
        cpu: null,
        memory: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'BARE_METAL',
      id: 105,
      role: 'RELATED',
      group_key: { resource_type: 'CONTAINER', id: 41 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'CONTAINER', id: 41 },
        { resource_type: 'BARE_METAL', id: 105 },
      ],
      resource: {
        id: 105,
        cluster_id: 3,
        hostname: 'cn005',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: null,
        storage: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'SERVICE',
      id: 51,
      role: 'HIT',
      group_key: { resource_type: 'SERVICE', id: 51 },
      matched_fields: ['name'],
      derivation_path: null,
      resource: {
        id: 51,
        name: 'svc-10',
        service_type: null,
        url: null,
        port: null,
        protocol: null,
        owner: null,
        description: null,
        carriers: [{ carrier_type: 'BARE_METAL', carrier_id: 106 }],
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'BARE_METAL',
      id: 106,
      role: 'RELATED',
      group_key: { resource_type: 'SERVICE', id: 51 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'SERVICE', id: 51 },
        { resource_type: 'BARE_METAL', id: 106 },
      ],
      resource: {
        id: 106,
        cluster_id: 3,
        hostname: 'cn006',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: null,
        storage: null,
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

/** 各结果行的标注徽标文本（命中 / 关联）。 */
function roleTexts(wrapper: VueWrapper): string[] {
  return wrapper.findAll('[data-testid="search-result-role"]').map((badge) => badge.text())
}

/** 各结果行标识列文本（按行顺序）。 */
function identifierTexts(wrapper: VueWrapper): string[] {
  return wrapper.findAll('.search-results__identifier').map((node) => node.text())
}

/** 各结果行 matched_fields 标签文本（按行顺序）。 */
function matchedFieldTexts(wrapper: VueWrapper): string[][] {
  return wrapper
    .findAll('.el-table__row')
    .map((row) => row.findAll('.search-results__matched').map((tag) => tag.text()))
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('SearchResultsPage 三态互不相同（T-FE-19-2 / AC-07）', () => {
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

    resolveSearch(SEARCH_AGGREGATION_BODY)
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

    // Empty 文案（R-QUERY-004 Empty 语义，AC-04）。
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

describe('SearchResultsPage 错误按 error.code 渲染，不解析 message（AC-07）', () => {
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

describe('SearchResultsPage 聚合视图：命中行 / 缩进关联行 / 推导路径（T-FE-19-1 / AC-A1/A2/A8）', () => {
  it('单一扁平列表按 items 顺序渲染：每单元命中行居首、关联行紧随；徽标「命中」/「关联」可区分', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_AGGREGATION_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(8)
    })

    // 单一扁平列表（同一表格、不按类型分区），行顺序 = items 原样顺序：
    // 单元 1（group_key BM 101）命中行 + 3 关联行，单元 2（group_key VM 31）
    // 命中行 + 3 关联行（AC-A8：关联行紧随其命中行）。
    expect(roleTexts(wrapper)).toEqual([
      '命中',
      '关联',
      '关联',
      '关联',
      '命中',
      '关联',
      '关联',
      '关联',
    ])
    // 标识字段按行顺序原样渲染（跨单元重复出现，见下方不去重断言）。
    expect(identifierTexts(wrapper)).toEqual([
      'cn001-gpu',
      'eth0-mgmt',
      '10.0.1.1/16',
      'vm-gpu-01',
      'vm-gpu-01',
      'cn001-gpu',
      'eth0-mgmt',
      '10.0.1.1/16',
    ])

    // 关联行缩进（标识缩进类 + 行底色类），命中行不缩进。
    const rows = wrapper.findAll('.el-table__row')
    const relatedRowIndexes = [1, 2, 3, 5, 6, 7]
    const hitRowIndexes = [0, 4]
    for (const index of relatedRowIndexes) {
      expect(rows[index]!.classes(), `第 ${index} 行应为关联行`).toContain(
        'search-results__row--related',
      )
      expect(
        rows[index]!.find('.search-results__identifier').classes(),
      ).toContain('search-results__identifier--related')
    }
    for (const index of hitRowIndexes) {
      expect(rows[index]!.classes(), `第 ${index} 行应为命中行`).not.toContain(
        'search-results__row--related',
      )
      expect(
        rows[index]!.find('.search-results__identifier').classes(),
      ).not.toContain('search-results__identifier--related')
    }

    // 搜索上下文可见（范围 Cluster 与关键字，原样值）。
    expect(wrapper.text()).toContain('集群 #3')
    expect(wrapper.text()).toContain('关键字「gpu」')
  })

  it('推导路径文案由 derivation_path 生成（首 = 命中项、末 = 本行）；命中行不渲染路径', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_AGGREGATION_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(8)
    })

    const paths = wrapper.findAll('[data-testid="search-derivation-path"]')
    // 仅 6 条关联行携带路径；2 条命中行（derivation_path == null）不渲染。
    expect(paths).toHaveLength(6)
    // 按行顺序：单元 1 的 NIC / IP / VM 关联行，随后单元 2 的 BM / NIC / IP 关联行。
    expect(paths[0]!.text()).toBe('裸金属 cn001-gpu → 网络接口 eth0-mgmt')
    expect(paths[1]!.text()).toBe('裸金属 cn001-gpu → 网络接口 eth0-mgmt → IP 地址 10.0.1.1/16')
    expect(paths[2]!.text()).toBe('裸金属 cn001-gpu → 虚拟机 vm-gpu-01')
    expect(paths[3]!.text()).toBe('虚拟机 vm-gpu-01 → 裸金属 cn001-gpu')
    expect(paths[4]!.text()).toBe('虚拟机 vm-gpu-01 → 裸金属 cn001-gpu → 网络接口 eth0-mgmt')
    expect(paths[5]!.text()).toBe(
      '虚拟机 vm-gpu-01 → 裸金属 cn001-gpu → 网络接口 eth0-mgmt → IP 地址 10.0.1.1/16',
    )
  })

  it('matched_fields 原样标签：命中行恒非空；自身也命中的关联行携带其命中字段；未命中为空', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_AGGREGATION_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(8)
    })

    // 行 0：BM 命中（hostname）；行 3：VM 关联行但自身命中（name，契约 §4.1
    // RELATED 行携带自身命中字段）；行 4：VM 命中（name）；其余关联行未命中为空。
    expect(matchedFieldTexts(wrapper)).toEqual([
      ['hostname'],
      [],
      [],
      ['name'],
      ['name'],
      [],
      [],
      [],
    ])
  })

  it('跨单元不去重（AC-A5）：同一资源在多个组织单元各出现一次，不合并', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_AGGREGATION_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(8)
    })

    // 四类资源均跨两个组织单元各出现一次（每单元 4 行 × 2 = 8 行）。
    const identifiers = identifierTexts(wrapper)
    expect(identifiers.filter((value) => value === 'cn001-gpu')).toHaveLength(2)
    expect(identifiers.filter((value) => value === 'eth0-mgmt')).toHaveLength(2)
    expect(identifiers.filter((value) => value === '10.0.1.1/16')).toHaveLength(2)
    expect(identifiers.filter((value) => value === 'vm-gpu-01')).toHaveLength(2)

    // vm-gpu-01 既出现在自身单元（命中行），又出现在裸金属单元（关联行）：
    // 两处角色不同、均保留，不合并为一条。
    const rows = wrapper.findAll('.el-table__row')
    expect(
      rows[3]!.find('[data-testid="search-result-role"]').text(),
    ).toBe('关联')
    expect(rows[3]!.find('.search-results__identifier').text()).toBe('vm-gpu-01')
    expect(
      rows[4]!.find('[data-testid="search-result-role"]').text(),
    ).toBe('命中')
    expect(rows[4]!.find('.search-results__identifier').text()).toBe('vm-gpu-01')

    // total = 组织单元（命中项）数 = 2（非行数 8）。
    expect(wrapper.find('[data-testid="search-unit-count"]').text()).toBe('共 2 个命中项')
  })
})

describe('SearchResultsPage 单请求与分页（T-FE-19-3 / AC-06；契约 §3）', () => {
  it('一次搜索恰一个请求：仅调用唯一搜索端点，无任何浏览器端拼接 / 关联推导', async () => {
    const fetchMock = stubFetch(() => jsonResponse(200, SEARCH_AGGREGATION_BODY))

    const wrapper = mountSearchResultsPage({ clusterId: 3, keyword: 'gpu' })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(8)
    })

    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls).toHaveLength(1)
    expect(urls[0]).toBe('/api/clusters/3/search?keyword=gpu&page=1&page_size=50')
    // 不请求任何 canonical 列表 / 关联端点（架构裁定 1：禁止浏览器端拼接）。
    expect(urls.every((url) => url.startsWith('/api/clusters/3/search'))).toBe(true)
  })

  it('props 变化（同组件复用换关键字）→ 重置到第 1 页重新请求（仍单请求/次）', async () => {
    const fetchMock = stubFetch(() => jsonResponse(200, SEARCH_AGGREGATION_BODY))

    const wrapper = mountSearchResultsPage({ clusterId: 3, keyword: 'gpu' })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(8)
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

  it('分页按 total（组织单元数）驱动：行数可大于单元数；换页携带 page 参数重新请求', async () => {
    const fetchMock = stubFetch(() => jsonResponse(200, SEARCH_SIX_TYPES_BODY))

    const wrapper = mountSearchResultsPage({ keyword: '10' })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(12)
    })

    // len(items) = 12（6 命中行 + 6 关联行）> total = 6 个组织单元
    // （契约 §3 语义 4 / §4：page_size 按单元计数）。
    const pager = wrapper.findComponent(ElPagination)
    expect(pager.exists()).toBe(true)
    expect(pager.props('total')).toBe(6)
    expect(pager.props('currentPage')).toBe(1)
    expect(wrapper.find('[data-testid="search-unit-count"]').text()).toBe('共 6 个命中项')

    pager.vm.$emit('current-change', 2)
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/clusters/3/search?keyword=10&page=2&page_size=50',
        expect.objectContaining({ method: 'GET' }),
      )
    })
  })
})

describe('SearchResultsPage 详情导航（命中行与关联行同权）', () => {
  it('六类资源行「查看」→ emit 对应导航事件（复用既有 open*Detail 链路）', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_SIX_TYPES_BODY))

    const wrapper = mountSearchResultsPage({ keyword: '10' })
    await waitForUi(() => {
      expect(wrapper.findAll('[data-testid="search-result-detail"]')).toHaveLength(12)
    })

    const detailButtons = wrapper.findAll('[data-testid="search-result-detail"]')
    for (const button of detailButtons) {
      await button.trigger('click')
    }

    // 按行顺序：BM101（命中）→ NIC11（命中）→ BM102（关联）→ IP21（命中）→
    // BM103（关联）→ NIC12（关联）→ VM31（命中）→ BM104（关联）→
    // C41（命中）→ BM105（关联）→ S51（命中）→ BM106（关联）。
    expect(wrapper.emitted('openBareMetalDetail')).toEqual([[101], [102], [103], [104], [105], [106]])
    expect(wrapper.emitted('openNetworkInterfaceDetail')).toEqual([[11], [12]])
    expect(wrapper.emitted('openIpAddressDetail')).toEqual([[21]])
    expect(wrapper.emitted('openVirtualMachineDetail')).toEqual([[31]])
    expect(wrapper.emitted('openContainerDetail')).toEqual([[41]])
    expect(wrapper.emitted('openServiceDetail')).toEqual([[51]])
  })

  it('「返回集群列表」→ emit back（App 侧接线回集群列表）', async () => {
    stubFetch(() => jsonResponse(200, SEARCH_AGGREGATION_BODY))

    const wrapper = mountSearchResultsPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(8)
    })

    const backButton = wrapper.findAll('button').find((b) => b.text() === '返回集群列表')
    expect(backButton, '期望找到「返回集群列表」按钮').toBeDefined()
    await backButton!.trigger('click')

    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})
