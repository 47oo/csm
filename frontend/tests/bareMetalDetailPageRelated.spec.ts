import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import BareMetalDetailPage from '../src/pages/BareMetalDetailPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * 裸金属详情页「关联资源」区测试（F010，T-FE-10 / AC-13 / AC-17）。
 *
 * 覆盖：
 * - 五类清单渲染与每条目的关系依据（AC-01~AC-08：NIC→bare_metal_id；
 *   IP→network_interface_id；VM→bare_metal_id；Container→carrier_type +
 *   carrier_id；Service→carriers 原样展示全部绑定，不做交集筛选）；
 * - **只消费聚合端点**：断言页面仅调用 GET /api/bare-metals/{id} 与
 *   GET /api/bare-metals/{id}/related，不自行调用任何 canonical 列表端点、
 *   不在浏览器端推导（NQ-5 裁定 a1）；
 * - 三态可区分（AC-13）：每类 Loading / Empty（200 + items == []，渲染
 *   「该裸金属暂无××」）与页面级 Not Found（404，独立 not-found 态、
 *   「未找到资源」文案）互不相同（不同 data-state / 不同文案）；
 * - Empty 不渲染错误、不触发全局会话失效（仅 UNAUTHENTICATED 触发）；
 * - 关联请求失败按 error.code 分支渲染，不解析 message；
 * - 从关联条目进入五类详情（emit 导航事件，保留返回上下文由 App 侧接线）。
 *
 * 响应体严格按 docs/api/f010-resource-detail.md §2 构造（元素 schema 等于
 * 各资源 canonical Read，枚举字面值取 f004 等契约的封闭集合成员）。
 * 沿用 tests/setup/monotonic-date-now.ts（宿主机时钟回跳会令 Vue 事件
 * invoker 静默吞掉 trigger 点击，见该 setup 头注）；所有点击均先等待目标
 * 渲染且可用（clickWhenEnabled，与既有 submitWhenEnabled 同一 rationale）。
 */

const BARE_METAL = {
  id: 1,
  cluster_id: 3,
  hostname: 'cn001',
  status: 'IDLE',
  vendor: null,
  model: null,
  serial_number: null,
  cpu: null,
  memory: null,
  gpu: null,
  storage: null,
  created_at: '2026-09-16T10:00:00Z',
  updated_at: '2026-09-16T10:00:00Z',
}

const TS = '2026-09-18T10:00:00Z'

/** 五类关联聚合（契约 §2 示例结构；含直接 + 间接关联，BQ-1 / BQ-2 均含间接）。 */
const RELATED_FULL_BODY = {
  network_interfaces: {
    items: [
      {
        id: 11,
        bare_metal_id: 1,
        name: 'eth0',
        technology_type: 'Ethernet',
        purpose: 'Business',
        created_at: TS,
        updated_at: TS,
      },
      {
        id: 12,
        bare_metal_id: 1,
        name: '管理口-1',
        technology_type: 'Ethernet',
        purpose: 'BMC',
        created_at: TS,
        updated_at: TS,
      },
    ],
    total: 2,
  },
  ip_addresses: {
    items: [
      { id: 21, network_interface_id: 11, ip_address: '10.0.0.5/16', created_at: TS, updated_at: TS },
      { id: 22, network_interface_id: 11, ip_address: 'fd00::1/64', created_at: TS, updated_at: TS },
      { id: 23, network_interface_id: 12, ip_address: '10.0.0.6/16', created_at: TS, updated_at: TS },
    ],
    total: 3,
  },
  virtual_machines: {
    items: [
      {
        id: 31,
        bare_metal_id: 1,
        name: 'vm-a',
        cpu: null,
        memory: null,
        disk: null,
        os: null,
        hypervisor: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
      {
        id: 32,
        bare_metal_id: 1,
        name: '虚拟机-生产-01',
        cpu: null,
        memory: null,
        disk: null,
        os: null,
        hypervisor: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
    ],
    total: 2,
  },
  containers: {
    items: [
      {
        id: 41,
        carrier_type: 'BARE_METAL',
        carrier_id: 1,
        name: 'c-direct',
        image: null,
        cpu: null,
        memory: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
      {
        id: 42,
        carrier_type: 'VIRTUAL_MACHINE',
        carrier_id: 31,
        name: 'c-on-vm',
        image: null,
        cpu: null,
        memory: null,
        owner: null,
        created_at: TS,
        updated_at: TS,
      },
    ],
    total: 2,
  },
  services: {
    items: [
      {
        id: 51,
        name: 'svc-direct',
        service_type: null,
        url: null,
        port: null,
        protocol: null,
        owner: null,
        description: null,
        carriers: [{ carrier_type: 'BARE_METAL', carrier_id: 1 }],
        created_at: TS,
        updated_at: TS,
      },
      {
        id: 52,
        name: 'svc-multi',
        service_type: null,
        url: null,
        port: null,
        protocol: null,
        owner: null,
        description: null,
        // 多载体：既含与本机无关的载体（BARE_METAL #2），也含本机上的 VM #31；
        // evidence 原样展示全部绑定，前端不做交集筛选（AC-08 / 不自行推导）。
        carriers: [
          { carrier_type: 'BARE_METAL', carrier_id: 2 },
          { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 31 },
        ],
        created_at: TS,
        updated_at: TS,
      },
      {
        id: 53,
        name: 'svc-on-container',
        service_type: null,
        url: null,
        port: null,
        protocol: null,
        owner: null,
        description: null,
        // 经 Container #42（载体为本机 VM #31）间接相关（BQ-2 含间接）。
        carriers: [{ carrier_type: 'CONTAINER', carrier_id: 42 }],
        created_at: TS,
        updated_at: TS,
      },
    ],
    total: 3,
  },
}

/** 全空五类（契约 §2 Empty：主体活跃，各类 { items: [], total: 0 }）。 */
const RELATED_EMPTY_BODY = {
  network_interfaces: { items: [], total: 0 },
  ip_addresses: { items: [], total: 0 },
  virtual_machines: { items: [], total: 0 },
  containers: { items: [], total: 0 },
  services: { items: [], total: 0 },
}

const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 详情页两个 GET 的路由桩（F010 起并行发出详情 + 关联聚合请求）。 */
function stubPageFetch(routes: {
  detail: () => Response | Promise<Response>
  related: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).endsWith('/related')) return routes.related()
    return routes.detail()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountDetailPage(bareMetalId = 1) {
  return mount(BareMetalDetailPage, {
    props: { bareMetalId },
    global: { plugins: [ElementPlus] },
  })
}

/**
 * vi.waitFor 包装：全量并行负载下 el-dialog / el-table 挂载偶发超过默认
 * 1s（与既有 spec 相同），仅放宽时序上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/**
 * 等待目标渲染且未禁用后再点击（monotonic-date-now setup 头注中的历史
 * MEDIUM：宿主机时钟回跳会使 Vue invoker 去重静默吞掉点击；与既有
 * submitWhenEnabled helper 同一 rationale，先确认可用再触发）。
 */
async function clickWhenEnabled(wrapper: VueWrapper, selector: string): Promise<void> {
  const target = wrapper.find(selector)
  expect(target.exists(), `期望存在「${selector}」`).toBe(true)
  await waitForUi(() => {
    expect(target.attributes('disabled')).toBeUndefined()
  })
  await target.trigger('click')
}

/** 某类关联区的当前 ListStates 状态（loading / error / empty / content）。 */
function categoryState(wrapper: VueWrapper, category: string): string {
  const states = wrapper.find(`[data-related="${category}"] .list-states`)
  expect(states.exists(), `期望存在「${category}」关联区`).toBe(true)
  return states.attributes('data-state') ?? ''
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('BareMetalDetailPage 关联资源：五类渲染与关系依据（AC-01~AC-08）', () => {
  it('一次请求获知五类：各类条目、计数与关系依据按契约原样展示', async () => {
    const fetchMock = stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () => jsonResponse(200, RELATED_FULL_BODY),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })
    await waitForUi(() => {
      expect(categoryState(wrapper, 'services')).toBe('content')
    })

    // 网络接口：条目 + 关系依据（bare_metal_id，直接父）。
    const nicRows = wrapper.findAll('[data-related="network_interfaces"] .el-table__row')
    expect(nicRows).toHaveLength(2)
    expect(nicRows[0]!.text()).toContain('eth0')
    expect(nicRows[0]!.text()).toContain('Ethernet')
    expect(nicRows[0]!.text()).toContain('Business')
    expect(nicRows[0]!.text()).toContain('宿主裸金属 #1（bare_metal_id）')
    // AC-09：中文字面值原样往返。
    expect(nicRows[1]!.text()).toContain('管理口-1')

    // IP 地址：条目 + 关系依据（network_interface_id，经 NIC 间接；IP 无 bare_metal_id）。
    const ipRows = wrapper.findAll('[data-related="ip_addresses"] .el-table__row')
    expect(ipRows).toHaveLength(3)
    expect(ipRows[0]!.text()).toContain('10.0.0.5/16')
    expect(ipRows[0]!.text()).toContain('所属网络接口 #11（network_interface_id）')
    expect(ipRows[2]!.text()).toContain('所属网络接口 #12（network_interface_id）')

    // 虚拟机：条目 + 关系依据（宿主 bare_metal_id）。
    const vmRows = wrapper.findAll('[data-related="virtual_machines"] .el-table__row')
    expect(vmRows).toHaveLength(2)
    expect(vmRows[0]!.text()).toContain('vm-a')
    expect(vmRows[0]!.text()).toContain('宿主裸金属 #1（bare_metal_id）')
    expect(vmRows[1]!.text()).toContain('虚拟机-生产-01')

    // 容器：直接载体与经 VM 的间接载体（BQ-1 含间接）均出现，依据为载体二元组。
    const containerRows = wrapper.findAll('[data-related="containers"] .el-table__row')
    expect(containerRows).toHaveLength(2)
    expect(containerRows[0]!.text()).toContain('c-direct')
    expect(containerRows[0]!.text()).toContain('载体 BARE_METAL #1（carrier_type + carrier_id）')
    expect(containerRows[1]!.text()).toContain('c-on-vm')
    expect(containerRows[1]!.text()).toContain('载体 VIRTUAL_MACHINE #31（carrier_type + carrier_id）')

    // 服务：直接 / 多载体 / 经 Container 间接（BQ-2 含间接）；carriers 原样
    // 展示全部绑定（含与本机无关的 BARE_METAL #2），不做交集筛选。
    const serviceRows = wrapper.findAll('[data-related="services"] .el-table__row')
    expect(serviceRows).toHaveLength(3)
    expect(serviceRows[0]!.text()).toContain('svc-direct')
    expect(serviceRows[0]!.text()).toContain('BARE_METAL #1')
    expect(serviceRows[1]!.text()).toContain('svc-multi')
    expect(serviceRows[1]!.text()).toContain('BARE_METAL #2')
    expect(serviceRows[1]!.text()).toContain('VIRTUAL_MACHINE #31')
    expect(serviceRows[2]!.text()).toContain('svc-on-container')
    expect(serviceRows[2]!.text()).toContain('CONTAINER #42')

    // 各类计数（契约 §2：total == items.length）。
    const relatedText = wrapper.find('[data-testid="related-resources"]').text()
    expect(relatedText).toContain('（共 2 项）')
    expect(relatedText).toContain('（共 3 项）')
  })

  it('不自行推导：仅调用聚合端点，不请求任何 canonical 列表端点（NQ-5 裁定 a1）', async () => {
    const fetchMock = stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () => jsonResponse(200, RELATED_FULL_BODY),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(categoryState(wrapper, 'services')).toBe('content')
    })

    // 页面只发起两个 GET：详情 + 关联聚合；无任何 canonical 端点调用。
    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls).toHaveLength(2)
    expect(urls).toContain('/api/bare-metals/1')
    expect(urls).toContain('/api/bare-metals/1/related')
    expect(urls).not.toContain('/api/network-interfaces?bare_metal_id=1')
    expect(urls).not.toContain('/api/ip-addresses?network_interface_id=11')
    expect(urls).not.toContain('/api/virtual-machines?bare_metal_id=1')
    expect(urls).not.toContain('/api/containers?carrier_type=BARE_METAL&carrier_id=1')
    expect(urls).not.toContain('/api/services?carrier_type=BARE_METAL&carrier_id=1')
    expect(urls.every((url) => url === '/api/bare-metals/1' || url === '/api/bare-metals/1/related')).toBe(true)
  })
})

describe('BareMetalDetailPage 关联资源：三态与 Empty / Not Found 区分（AC-13）', () => {
  it('聚合请求进行中 → 每类 Loading 态（骨架屏）', async () => {
    let resolveRelated!: (body: unknown) => void
    const relatedPromise = new Promise<Response>((res) => {
      resolveRelated = (body: unknown) => res(jsonResponse(200, body))
    })
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () => relatedPromise,
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    for (const category of [
      'network_interfaces',
      'ip_addresses',
      'virtual_machines',
      'containers',
      'services',
    ]) {
      expect(categoryState(wrapper, category)).toBe('loading')
      expect(
        wrapper.find(`[data-related="${category}"] .el-skeleton`).exists(),
      ).toBe(true)
    }

    resolveRelated(RELATED_FULL_BODY)
    await waitForUi(() => {
      expect(categoryState(wrapper, 'services')).toBe('content')
    })
  })

  it('主体活跃但某类为空 → 该类 Empty（「该裸金属暂无××」），非错误、非表格', async () => {
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () => jsonResponse(200, RELATED_EMPTY_BODY),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const emptyTexts: Record<string, string> = {
      network_interfaces: '该裸金属暂无网络接口',
      ip_addresses: '该裸金属暂无 IP 地址',
      virtual_machines: '该裸金属暂无虚拟机',
      containers: '该裸金属暂无容器',
      services: '该裸金属暂无服务',
    }
    for (const [category, text] of Object.entries(emptyTexts)) {
      expect(categoryState(wrapper, category)).toBe('empty')
      expect(wrapper.find(`[data-related="${category}"]`).text()).toContain(text)
      // Empty 不是错误：不渲染 ErrorState，也不渲染表格。
      expect(wrapper.find(`[data-related="${category}"] [role="alert"]`).exists()).toBe(false)
      expect(wrapper.find(`[data-related="${category}"] .el-table`).exists()).toBe(false)
    }
  })

  it('部分类为空、部分类非空 → 空与非空类并存，互不影响（AC-12 界面侧）', async () => {
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () =>
        jsonResponse(200, {
          ...RELATED_FULL_BODY,
          containers: { items: [], total: 0 },
        }),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(categoryState(wrapper, 'containers')).toBe('empty')
    })

    expect(categoryState(wrapper, 'network_interfaces')).toBe('content')
    expect(categoryState(wrapper, 'ip_addresses')).toBe('content')
    expect(categoryState(wrapper, 'virtual_machines')).toBe('content')
    expect(categoryState(wrapper, 'services')).toBe('content')
    expect(wrapper.find('[data-related="containers"]').text()).toContain('该裸金属暂无容器')
    expect(wrapper.findAll('[data-related="network_interfaces"] .el-table__row')).toHaveLength(2)
  })

  it('主体不存在或已删（404，两者不区分）→ 页面级 not-found 态，关联区不渲染，与 Empty 可区分', async () => {
    stubPageFetch({
      detail: () => jsonResponse(404, NOT_FOUND_BODY),
      related: () => jsonResponse(404, NOT_FOUND_BODY),
    })

    const wrapper = mountDetailPage(999)

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('未找到资源')
    expect(alert.text()).toContain('资源不存在，或已被删除')
    // 与 Empty 不同的 data-state（页面级 not-found vs 类级 empty）与不同文案。
    expect(wrapper.find('[data-testid="related-resources"]').exists()).toBe(false)
    const text = wrapper.text()
    expect(text).not.toContain('该裸金属暂无网络接口')
    expect(text).not.toContain('该裸金属暂无 IP 地址')
    expect(text).not.toContain('该裸金属暂无虚拟机')
    expect(text).not.toContain('该裸金属暂无容器')
    expect(text).not.toContain('该裸金属暂无服务')
  })

  it('聚合请求 500 INTERNAL_ERROR → 每类 Error 态按 error.code 渲染，不解析 message；页面详情仍为内容态', async () => {
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () =>
        jsonResponse(500, {
          error: { code: 'INTERNAL_ERROR', message: '与展示无关的服务端错误文案' },
        }),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(categoryState(wrapper, 'services')).toBe('error')
    })

    for (const category of [
      'network_interfaces',
      'ip_addresses',
      'virtual_machines',
      'containers',
      'services',
    ]) {
      expect(categoryState(wrapper, category)).toBe('error')
      const alert = wrapper.find(`[data-related="${category}"] [data-error-code]`)
      expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
      expect(alert.text()).toContain('服务器内部错误')
    }
    // 页面级详情不受影响；Empty 文案不出现（错误与 Empty 是不同状态）。
    // 分支只依赖 error.code（固定文案 + data-error-code），message 仅作
    // 补充展示，不参与分支判断（跨 Feature 渲染约定）。
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.text()).toContain('cn001')
    expect(wrapper.text()).not.toContain('该裸金属暂无网络接口')
    expect(wrapper.text()).toContain('服务器处理请求时发生错误，请稍后重试。')
  })

  it('聚合请求 404（主体已被删除的竞态）→ 每类 Error 态（NOT_FOUND 文案），与 Empty 可区分', async () => {
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () => jsonResponse(404, NOT_FOUND_BODY),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(categoryState(wrapper, 'network_interfaces')).toBe('error')
    })

    expect(categoryState(wrapper, 'ip_addresses')).toBe('error')
    const alert = wrapper.find('[data-related="ip_addresses"] [data-error-code]')
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(wrapper.find('[data-related="ip_addresses"]').text()).not.toContain('该裸金属暂无 IP 地址')
  })

  it('Empty 不触发全局会话失效；仅 UNAUTHENTICATED 触发（AC-13）', async () => {
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () => jsonResponse(200, RELATED_EMPTY_BODY),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(categoryState(wrapper, 'services')).toBe('empty')
    })

    // Empty（200 + 空集合）不触发全局会话失效。
    expect(unauthenticated).not.toHaveBeenCalled()
    expect(wrapper.attributes('data-state')).toBe('content')

    // 对照：聚合请求返回 401 UNAUTHENTICATED → 触发全局处理。
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const wrapper2 = mountDetailPage()
    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    expect(wrapper2.attributes('data-state')).toBe('content')
  })
})

describe('BareMetalDetailPage 关联资源：从条目进入详情（AC-17）', () => {
  it('点击各类条目「详情」→ emit 对应导航事件（IP 携带 network_interface_id）', async () => {
    stubPageFetch({
      detail: () => jsonResponse(200, BARE_METAL),
      related: () => jsonResponse(200, RELATED_FULL_BODY),
    })

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(categoryState(wrapper, 'services')).toBe('content')
    })

    await clickWhenEnabled(wrapper, '[data-related="network_interfaces"] [data-testid="related-detail"]')
    expect(wrapper.emitted('openNetworkInterfaceDetail')).toEqual([[11]])

    await clickWhenEnabled(wrapper, '[data-related="ip_addresses"] [data-testid="related-detail"]')
    expect(wrapper.emitted('openIpAddressDetail')).toEqual([[21, 11]])

    await clickWhenEnabled(wrapper, '[data-related="virtual_machines"] [data-testid="related-detail"]')
    expect(wrapper.emitted('openVirtualMachineDetail')).toEqual([[31]])

    await clickWhenEnabled(wrapper, '[data-related="containers"] [data-testid="related-detail"]')
    expect(wrapper.emitted('openContainerDetail')).toEqual([[41]])

    await clickWhenEnabled(wrapper, '[data-related="services"] [data-testid="related-detail"]')
    expect(wrapper.emitted('openServiceDetail')).toEqual([[51]])
  })
})
