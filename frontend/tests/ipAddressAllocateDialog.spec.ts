import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import IpAddressAllocateDialog from '../src/components/IpAddressAllocateDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * F021 / F023 分配对话框测试（AC-18 / AC-33 / f023 handoff Frontend Work）。
 *
 * 覆盖：
 * - 自动分配（F023 修订）：选定 NIC 后按架构方案 1 只读链加载该 NIC 所属
 *   Cluster 的活跃范围段（GET /api/network-interfaces/{id}（仅 NIC 上下文
 *   入口）→ GET /api/bare-metals/{id} → GET /api/ip-address-ranges?
 *   cluster_id=…&page=1&page_size=200）并渲染必选「目标地址范围」下拉；
 *   未选择范围段不得提交（基础必填）；目标 Cluster 无活跃范围段 → Empty
 *   态提示且禁用提交；加载失败按 error.code 分支（404 = NIC / BM 已失效；
 *   401 交既有全局会话处理）；切换 NIC → 已选范围段清空并重新加载；
 * - 两个端点的调用与请求体（恰为契约封闭字段集合：自动
 *   {network_interface_id, ip_address_range_id}，手动
 *   {network_interface_id, ip_address}）；
 * - 分配动作三态互异（Empty = 尚未分配结果 / Loading = 提交中拦截重复 /
 *   Error = 按 error.code 分支）与错误分支（400 字段级 / 401 全局处理 /
 *   404 NIC / 404 + IP_ADDRESS_RANGE_UNAVAILABLE / 409 +
 *   IP_ADDRESS_RANGE_UNAVAILABLE / 409 NO_AVAILABLE_IP（所选段耗尽，不表述
 *   集群并集）/ 409 OUT_OF_RANGE / 409 DUPLICATE，均不解析 message）；
 * - 成功结果区（新 ip_address 与 id + emit success）与「前端不做客户端
 *   业务校验」（§21：非法 IPv4 / 首尾空白 / 前导零 / 仅空白串均原样提交，
 *   仅空串按基础必填禁用）；手动分配不走范围段选择（F023 不影响）。
 *
 * 响应体严格按 docs/api/f021-ip-address-allocation.md（含 F023 修订）构造
 * （§2 资源表示（复用 F005）/ §3 两个端点 / §4 错误信封）；只读链响应体按
 * f004 §2 / f002 §2 / f020 §2 契约构造。fetch 全部桩替换。
 */

const ALLOCATED = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.0.5',
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
}

/** 目标网络接口选项（GET /api/network-interfaces，f004 契约 §3.2 信封）。 */
const NIC_READ = {
  id: 12,
  bare_metal_id: 11,
  name: 'eth0',
  technology_type: 'Ethernet',
  purpose: 'Business',
  created_at: '2026-09-17T10:00:00Z',
  updated_at: '2026-09-17T10:00:00Z',
}

const NIC_LIST_BODY = {
  items: [NIC_READ],
  total: 1,
  page: 1,
  page_size: 200,
}

/** 第二个 NIC（宿主裸金属 #12 → Cluster 2），用于切换目标 NIC 用例。 */
const NIC_2_READ = { ...NIC_READ, id: 13, bare_metal_id: 12, name: 'eth1' }
const NIC_LIST_TWO_BODY = {
  items: [NIC_READ, NIC_2_READ],
  total: 2,
  page: 1,
  page_size: 200,
}

/** 宿主裸金属（GET /api/bare-metals/{id}，f002 契约 §2）。 */
const BARE_METAL_READ = {
  id: 11,
  cluster_id: 1,
  hostname: 'bm-1',
  status: 'IDLE',
  vendor: null,
  model: null,
  serial_number: null,
  cpu: null,
  memory: null,
  gpu: null,
  storage: null,
  created_at: '2026-09-17T09:00:00Z',
  updated_at: '2026-09-17T09:00:00Z',
}
const BARE_METAL_2_READ = { ...BARE_METAL_READ, id: 12, cluster_id: 2, hostname: 'bm-2' }

/** 活跃范围段（GET /api/ip-address-ranges，f020 契约 §2 / §3.2 信封，含 F022 元数据）。 */
const RANGE_A = {
  id: 7,
  cluster_id: 1,
  start_ip: '10.0.0.1',
  end_ip: '10.0.0.255',
  name: '业务网',
  subnet_mask: '255.255.255.0',
  vlan: 10,
  created_at: '2026-09-18T10:00:00Z',
  updated_at: '2026-09-18T10:00:00Z',
}
const RANGE_B = {
  id: 8,
  cluster_id: 1,
  start_ip: '10.0.1.1',
  end_ip: '10.0.1.255',
  name: null,
  subnet_mask: null,
  vlan: null,
  created_at: '2026-09-18T10:01:00Z',
  updated_at: '2026-09-18T10:01:00Z',
}
const RANGE_C = {
  id: 9,
  cluster_id: 2,
  start_ip: '192.168.1.1',
  end_ip: '192.168.1.254',
  name: '管理网',
  subnet_mask: '255.255.255.0',
  vlan: 20,
  created_at: '2026-09-18T10:02:00Z',
  updated_at: '2026-09-18T10:02:00Z',
}

const RANGE_LIST_BODY = {
  items: [RANGE_A, RANGE_B],
  total: 2,
  page: 1,
  page_size: 200,
}
const RANGE_LIST_CLUSTER_2_BODY = {
  items: [RANGE_C],
  total: 1,
  page: 1,
  page_size: 200,
}
const RANGE_LIST_EMPTY_BODY = { items: [], total: 0, page: 1, page_size: 200 }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

interface AllocateRoutes {
  networkInterfaceList?: (url: string) => Response
  networkInterface?: (url: string) => Response
  bareMetal?: (url: string) => Response
  ipAddressRanges?: (url: string) => Response | Promise<Response>
  allocateAuto?: () => Response | Promise<Response>
  allocateManual?: () => Response | Promise<Response>
}

/** 按端点分发的 fetch 桩；未配置的路由返回 404 以暴露意外请求。 */
function stubFetch(routes: AllocateRoutes = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (method === 'POST' && url === '/api/ip-addresses/allocate') {
      return routes.allocateAuto?.() ?? jsonResponse(201, ALLOCATED)
    }
    if (method === 'POST' && url === '/api/ip-addresses/allocate-manual') {
      return routes.allocateManual?.() ?? jsonResponse(201, ALLOCATED)
    }
    if (method === 'GET' && url === '/api/network-interfaces?page=1&page_size=200') {
      return (routes.networkInterfaceList ?? (() => jsonResponse(200, NIC_LIST_BODY)))(url)
    }
    if (method === 'GET' && /^\/api\/network-interfaces\/\d+$/.test(url)) {
      return (routes.networkInterface ?? (() => jsonResponse(200, NIC_READ)))(url)
    }
    if (method === 'GET' && /^\/api\/bare-metals\/\d+$/.test(url)) {
      return (routes.bareMetal ?? (() => jsonResponse(200, BARE_METAL_READ)))(url)
    }
    if (method === 'GET' && /^\/api\/ip-address-ranges\?/.test(url)) {
      return (routes.ipAddressRanges ?? (() => jsonResponse(200, RANGE_LIST_BODY)))(url)
    }
    return jsonResponse(404, { error: { code: 'NOT_FOUND', message: '未匹配的桩路由' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountDialog(props: { mode: 'auto' | 'manual'; presetNetworkInterfaceId?: number | null }) {
  return mount(IpAddressAllocateDialog, {
    props: { modelValue: true, ...props },
    global: { plugins: [ElementPlus] },
  })
}

/** 对话框根状态节点（data-testid="allocate-state"，携带互异 data-state）。 */
function stateNode(wrapper: VueWrapper) {
  return wrapper.find('[data-testid="allocate-state"]')
}

async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/** 等待提交按钮解除 disabled 后点击（真实用户只能点击已启用的按钮）。 */
async function submitWhenEnabled(wrapper: VueWrapper): Promise<void> {
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })
  await wrapper.find('[data-testid="allocate-submit"]').trigger('click')
}

/** 对话框内的目标网络接口下拉（el-select，按 class 精确定位）。 */
function findNicSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('ip-address-allocate__nic-select'))
  expect(select, '期望找到目标网络接口下拉').toBeDefined()
  return select!
}

async function selectNic(wrapper: VueWrapper, networkInterfaceId: number): Promise<void> {
  await findNicSelect(wrapper).vm.$emit('update:modelValue', networkInterfaceId)
}

/** 对话框内的目标地址范围下拉（仅 auto 模式，按 class 精确定位）。 */
function findRangeSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('ip-address-allocate__range-select'))
  expect(select, '期望找到目标地址范围下拉').toBeDefined()
  return select!
}

async function selectRange(wrapper: VueWrapper, ipAddressRangeId: number): Promise<void> {
  await findRangeSelect(wrapper).vm.$emit('update:modelValue', ipAddressRangeId)
}

/** 等待范围段选项加载完成（选项数稳定为 count；与加载失败 / 加载中互异）。 */
async function waitForRangeOptions(wrapper: VueWrapper, count = 2): Promise<void> {
  await waitForUi(() => {
    expect(findRangeSelect(wrapper).findAllComponents({ name: 'ElOption' })).toHaveLength(count)
  })
}

/** 某分配端点的 POST 调用次数。 */
function allocateCalls(
  fetchMock: ReturnType<typeof vi.fn>,
  url: '/api/ip-addresses/allocate' | '/api/ip-addresses/allocate-manual',
): number {
  return fetchMock.mock.calls.filter(
    (call) => String(call[0]) === url && (call[1] as RequestInit | undefined)?.method === 'POST',
  ).length
}

/** 某分配端点最近一次请求的已解析请求体。 */
function lastAllocateBody(
  fetchMock: ReturnType<typeof vi.fn>,
  url: '/api/ip-addresses/allocate' | '/api/ip-addresses/allocate-manual',
): Record<string, unknown> {
  const calls = fetchMock.mock.calls.filter(
    (call) => String(call[0]) === url && (call[1] as RequestInit | undefined)?.method === 'POST',
  )
  if (calls.length === 0) throw new Error(`期望存在对 ${url} 的 POST 调用`)
  return JSON.parse((calls[calls.length - 1]![1] as RequestInit).body as string) as Record<
    string,
    unknown
  >
}

/** 某次调用是否发生（按 URL 前缀 / 全串匹配）。 */
function hasCall(fetchMock: ReturnType<typeof vi.fn>, url: string): boolean {
  return fetchMock.mock.calls.some(([input]) => String(input) === url)
}

/** 全部 GET 调用的 URL（按发生顺序），用于断言只读链顺序。 */
function getCallUrls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls
    .filter((call) => (call[1] as RequestInit | undefined)?.method === 'GET')
    .map((call) => String(call[0]))
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('自动分配：范围段选择（F023 / AC-18，NIC 上下文预设目标 NIC）', () => {
  it('打开 → 只读展示目标 NIC 并按方案 1 只读链加载范围段（network-interfaces/{id} → bare-metals/{id} → ip-address-ranges?cluster_id=…）；未选范围段提交禁用；Empty 态', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('[data-testid="allocate-preset-nic"]').text()).toContain('网络接口 #12')
    // NIC 上下文：目标已由上下文固定，不渲染 NIC 选择器，也不请求网络接口列表。
    expect(
      wrapper
        .findAllComponents(ElSelect)
        .filter((s) => s.classes().includes('ip-address-allocate__nic-select')),
    ).toHaveLength(0)
    expect(hasCall(fetchMock, '/api/network-interfaces?page=1&page_size=200')).toBe(false)

    // 方案 1 只读链（顺序固定）：单条 NIC → 宿主 BareMetal → 该 Cluster 活跃范围段。
    await waitForRangeOptions(wrapper)
    expect(getCallUrls(fetchMock)).toEqual([
      '/api/network-interfaces/12',
      '/api/bare-metals/11',
      '/api/ip-address-ranges?page=1&page_size=200&cluster_id=1',
    ])

    // Empty 态：引导文案可见；无失败提示、无成功结果。
    expect(wrapper.find('[data-testid="allocate-guidance"]').exists()).toBe(true)
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocate-result"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocate-range-empty"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocate-range-error"]').exists()).toBe(false)
    // 基础必填（AC-18）：未选择范围段 → 提交禁用。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()
  })

  it('范围段选项展示契约原样字段（name / start_ip / end_ip；name 未登记 → 地址范围 + ID 区分）', async () => {
    stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)

    const options = findRangeSelect(wrapper).findAllComponents({ name: 'ElOption' })
    expect(options.map((option) => option.props('value'))).toEqual([7, 8])
    expect(options[0]!.props('label')).toBe('业务网（10.0.0.1 – 10.0.0.255 · ID 7）')
    expect(options[1]!.props('label')).toBe('10.0.1.1 – 10.0.1.255（ID 8）')
  })

  it('选择范围段 → 提交解除禁用（基础必填；服务端仍独立校验，§21）', async () => {
    stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()

    await selectRange(wrapper, 7)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('选择范围段后提交 → POST /api/ip-addresses/allocate，请求体恰为 {network_interface_id, ip_address_range_id}（§3.1 封闭，F023）；成功 → 结果区展示 ip_address 与 id、emit success、对话框保持打开', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate')).toBe(1)
    })
    expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate')).toEqual({
      network_interface_id: 12,
      ip_address_range_id: 7,
    })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('success')
    })
    expect(wrapper.find('[data-testid="allocate-result-ip"]').text()).toBe('10.0.0.5')
    expect(wrapper.find('[data-testid="allocate-result-id"]').text()).toBe('41')
    expect(wrapper.emitted('success')).toEqual([[ALLOCATED]])
    // 成功后对话框不自动关闭（结果区由用户确认后关闭）。
    expect(wrapper.props('modelValue')).toBe(true)
  })

  it('关闭后重新打开 → 重置为 Empty 态、清空已选范围段并重新加载（同一预设 NIC 也重新走只读链）', async () => {
    const fetchMock = stubFetch({ allocateAuto: () => jsonResponse(201, ALLOCATED) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('success')
    })

    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('[data-testid="allocate-guidance"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="allocate-result"]').exists()).toBe(false)
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    // 已选范围段被清空（基础必填重新生效）并重新加载只读链。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.filter(
          (call) =>
            String(call[0]) === '/api/ip-address-ranges?page=1&page_size=200&cluster_id=1',
        ).length,
      ).toBe(2)
    })
  })
})

describe('目标地址范围选项加载（F023 方案 1 只读链）', () => {
  it('全局入口：选定 NIC 后从选项取 bare_metal_id（不请求单条 NIC）→ 宿主 BareMetal → 范围段列表', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: null })
    await waitForUi(() => {
      expect(findNicSelect(wrapper)).toBeDefined()
    })
    await waitForUi(() => {
      expect(hasCall(fetchMock, '/api/network-interfaces?page=1&page_size=200')).toBe(true)
    })
    await selectNic(wrapper, 12)
    await waitForRangeOptions(wrapper)

    // 全局入口的选项已携带 bare_metal_id（f004 §2），只读链不再请求单条 NIC。
    expect(hasCall(fetchMock, '/api/network-interfaces/12')).toBe(false)
    expect(getCallUrls(fetchMock).slice(-2)).toEqual([
      '/api/bare-metals/11',
      '/api/ip-address-ranges?page=1&page_size=200&cluster_id=1',
    ])
  })

  it('切换目标 NIC → 已选范围段清空（提交重新禁用）并按新 Cluster 重新加载选项', async () => {
    const fetchMock = stubFetch({
      networkInterfaceList: () => jsonResponse(200, NIC_LIST_TWO_BODY),
      bareMetal: (url) =>
        jsonResponse(200, url === '/api/bare-metals/12' ? BARE_METAL_2_READ : BARE_METAL_READ),
      ipAddressRanges: (url) =>
        jsonResponse(
          200,
          url.includes('cluster_id=2') ? RANGE_LIST_CLUSTER_2_BODY : RANGE_LIST_BODY,
        ),
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: null })
    await waitForUi(() => {
      expect(findNicSelect(wrapper)).toBeDefined()
    })

    await selectNic(wrapper, 12)
    await waitForRangeOptions(wrapper, 2)
    await selectRange(wrapper, 7)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()

    // 切换到 NIC #13（宿主裸金属 #12 → Cluster 2）。
    await selectNic(wrapper, 13)
    await waitForRangeOptions(wrapper, 1)
    expect(hasCall(fetchMock, '/api/ip-address-ranges?page=1&page_size=200&cluster_id=2')).toBe(true)
    // 已选范围段（属 Cluster 1）被清空：提交回到禁用，直到重新选择。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()
    await selectRange(wrapper, 9)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('加载在途时切换目标 NIC → 旧链响应被丢弃，不得覆盖新 Cluster 的选项（时序防护，非业务预检）', async () => {
    let releaseCluster1Ranges!: () => void
    const cluster1Gate = new Promise<void>((resolve) => {
      releaseCluster1Ranges = resolve
    })
    let cluster1Responded = false
    const fetchMock = stubFetch({
      networkInterfaceList: () => jsonResponse(200, NIC_LIST_TWO_BODY),
      bareMetal: (url) =>
        jsonResponse(200, url === '/api/bare-metals/12' ? BARE_METAL_2_READ : BARE_METAL_READ),
      ipAddressRanges: (url) => {
        if (url.includes('cluster_id=2')) {
          return jsonResponse(200, RANGE_LIST_CLUSTER_2_BODY)
        }
        return cluster1Gate.then(() => {
          cluster1Responded = true
          return jsonResponse(200, RANGE_LIST_BODY)
        })
      },
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: null })
    await waitForUi(() => {
      expect(findNicSelect(wrapper)).toBeDefined()
    })

    // 选 NIC #12：Cluster 1 链被闸门挂起（在途）。
    await selectNic(wrapper, 12)
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.some(
          ([url]) => String(url) === '/api/ip-address-ranges?page=1&page_size=200&cluster_id=1',
        ),
      ).toBe(true)
    })

    // 在途时切换到 NIC #13（Cluster 2）：新链完成，选项仅为 RANGE_C（ID 9）。
    await selectNic(wrapper, 13)
    await waitForRangeOptions(wrapper, 1)
    expect(
      findRangeSelect(wrapper)
        .findAllComponents({ name: 'ElOption' })
        .map((option) => option.props('value')),
    ).toEqual([9])

    // 释放 Cluster 1 的旧响应：被序号防护丢弃，不得覆盖 Cluster 2 的选项。
    releaseCluster1Ranges()
    await waitForUi(() => {
      expect(cluster1Responded).toBe(true)
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))
    const options = findRangeSelect(wrapper).findAllComponents({ name: 'ElOption' })
    expect(options).toHaveLength(1)
    expect(options[0]!.props('value')).toBe(9)
  })

  it('加载链 404（单条 NIC 读取：NIC 已失效）→ 提示「目标网络接口或其宿主裸金属已失效」，提交禁用，可重试', async () => {
    let nicReadFails = true
    stubFetch({
      networkInterface: () =>
        nicReadFails
          ? jsonResponse(404, { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } })
          : jsonResponse(200, NIC_READ),
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="allocate-range-error"]').exists()).toBe(true)
    })
    const hint = wrapper.find('[data-testid="allocate-range-error"]')
    expect(hint.text()).toContain('目标网络接口或其宿主裸金属已失效')
    expect(hint.text()).not.toContain('与展示无关的未找到文案')
    // 加载失败（无范围段可选）→ 提交禁用。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()

    // 重试：恢复后链路成功，选项可选、提交解除禁用。
    nicReadFails = false
    await hint.find('button').trigger('click')
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('加载链 404（宿主 BareMetal 读取）→ 同样提示 NIC / BM 已失效（两者不区分）', async () => {
    stubFetch({
      bareMetal: () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }),
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="allocate-range-error"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-testid="allocate-range-error"]').text()).toContain(
      '目标网络接口或其宿主裸金属已失效',
    )
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()
  })

  it('加载链非 404 失败（如 500 INTERNAL_ERROR）→ 通用加载失败提示（含 error.code）+ 重试', async () => {
    stubFetch({
      ipAddressRanges: () =>
        jsonResponse(500, {
          error: { code: 'INTERNAL_ERROR', message: '与展示无关的服务器错误文案' },
        }),
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="allocate-range-error"]').exists()).toBe(true)
    })
    const hint = wrapper.find('[data-testid="allocate-range-error"]')
    expect(hint.text()).toContain('地址范围列表加载失败（INTERNAL_ERROR）')
    expect(hint.text()).not.toContain('与展示无关的服务器错误文案')
    expect(hint.find('button').exists()).toBe(true)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()
  })

  it('目标 Cluster 无活跃范围段 → Empty 态提示「该集群暂无可用地址范围段」且禁用自动提交（客户端提示，非业务守卫）', async () => {
    stubFetch({ ipAddressRanges: () => jsonResponse(200, RANGE_LIST_EMPTY_BODY) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="allocate-range-empty"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-testid="allocate-range-empty"]').text()).toContain(
      '该集群暂无可用地址范围段',
    )
    // Empty 与加载失败互异：不渲染错误提示。
    expect(wrapper.find('[data-testid="allocate-range-error"]').exists()).toBe(false)
    // 禁用自动提交：无可选范围段（选择值保持 null）。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()
  })

  it('加载链 401 → 触发既有全局会话失效处理（api/http.ts），不渲染 NIC / BM 已失效提示', async () => {
    stubFetch({
      networkInterface: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '与展示无关的未认证文案' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="allocate-range-error"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-testid="allocate-range-error"]').text()).not.toContain('已失效')
    expect(wrapper.text()).not.toContain('与展示无关的未认证文案')
  })
})

describe('全局入口（无预设 NIC，先选 NIC）', () => {
  it('打开 → 加载网络接口选项（GET /api/network-interfaces?page=1&page_size=200）；未选择时提交禁用', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: null })
    await waitForUi(() => {
      expect(findNicSelect(wrapper)).toBeDefined()
    })

    await waitForUi(() => {
      expect(hasCall(fetchMock, '/api/network-interfaces?page=1&page_size=200')).toBe(true)
    })
    // 基础必填：目标 NIC 未选择 → 表单未完成。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()

    await selectNic(wrapper, 12)
    await waitForRangeOptions(wrapper)
    // NIC 已选但范围段未选 → 仍禁用（AC-18）。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()
    await selectRange(wrapper, 7)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('选择目标 NIC + 范围段后提交（自动）→ POST /api/ip-addresses/allocate，请求体恰为两字段', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: null })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await selectNic(wrapper, 12)
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 8)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate')).toBe(1)
    })
    expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate')).toEqual({
      network_interface_id: 12,
      ip_address_range_id: 8,
    })
  })

  it('选择目标 NIC + 输入地址后提交（手动）→ POST /api/ip-addresses/allocate-manual，请求体恰为两字段；手动模式不走范围段只读链', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: null })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('10.0.0.5')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate-manual')).toBe(1)
    })
    expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate-manual')).toEqual({
      network_interface_id: 12,
      ip_address: '10.0.0.5',
    })
    // F023 不影响手动分配：不请求 BareMetal / 范围段 / 单条 NIC，也不渲染范围段下拉。
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/api/bare-metals')),
    ).toBe(false)
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/api/ip-address-ranges')),
    ).toBe(false)
    expect(
      wrapper
        .findAllComponents(ElSelect)
        .filter((s) => s.classes().includes('ip-address-allocate__range-select')),
    ).toHaveLength(0)
  })

  it('手动分配（NIC 上下文预设）→ 不触发范围段只读链；请求体仍恰为 {network_interface_id, ip_address}', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/api/bare-metals')),
    ).toBe(false)
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/api/ip-address-ranges')),
    ).toBe(false)
    expect(hasCall(fetchMock, '/api/network-interfaces/12')).toBe(false)

    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('10.0.0.5')
    await submitWhenEnabled(wrapper)
    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate-manual')).toBe(1)
    })
    expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate-manual')).toEqual({
      network_interface_id: 12,
      ip_address: '10.0.0.5',
    })
  })
})

describe('手动分配不实现客户端业务校验（§21 / AC-33）', () => {
  it('非法 IPv4（abc / 10.0.0.256 / 1.2.3.4/24）均为表单已完成并原样提交（格式由服务端裁决）', async () => {
    const fetchMock = stubFetch({
      allocateManual: () => jsonResponse(400, {
        error: {
          code: 'VALIDATION_ERROR',
          message: '与展示无关的校验文案',
          details: [{ field: 'ip_address', code: 'INVALID', message: '与展示无关的字段提示' }],
        },
      }),
    })

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })

    for (const value of ['abc', '10.0.0.256', '1.2.3.4/24']) {
      await wrapper.find('[data-testid="allocate-ip-address"]').setValue(value)
      await submitWhenEnabled(wrapper)
      await waitForUi(() => {
        expect(
          allocateCalls(fetchMock, '/api/ip-addresses/allocate-manual'),
        ).toBeGreaterThanOrEqual(1)
      })
      expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate-manual')).toEqual({
        network_interface_id: 12,
        ip_address: value,
      })
      // 失败后表单仍可继续提交（400 渲染见错误分支用例）。
      await waitForUi(() => {
        expect(stateNode(wrapper).attributes('data-state')).toBe('error')
      })
    }
    expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate-manual')).toBe(3)
  })

  it('首尾空白 / 前导零原样提交（不做 trim / 归一化；规范化由服务端完成）', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })

    for (const value of [' 10.0.0.5 ', '010.0.0.5']) {
      await wrapper.find('[data-testid="allocate-ip-address"]').setValue(value)
      await submitWhenEnabled(wrapper)
      await waitForUi(() => {
        expect(
          allocateCalls(fetchMock, '/api/ip-addresses/allocate-manual'),
        ).toBeGreaterThanOrEqual(1)
      })
      expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate-manual')).toEqual({
        network_interface_id: 12,
        ip_address: value,
      })
    }
    expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate-manual')).toBe(2)
  })

  it('空串 → 表单未完成（基础必填），提交禁用；仅空白串仍可提交（不做 trim 预判，契约 §7）', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })

    // 空串：基础必填未完成。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()

    // 仅空白串：非空串 → 表单已完成，原样提交（是否非法由服务端裁决）。
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue(' ')
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
    await submitWhenEnabled(wrapper)
    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate-manual')).toBe(1)
    })
    expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate-manual')).toEqual({
      network_interface_id: 12,
      ip_address: ' ',
    })
  })
})

/** 契约 §4：message 不构成契约；使用与展示无关的文案，证明渲染不解析 message。 */
const VALIDATION_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '与展示无关的校验文案',
    details: [
      {
        field: 'ip_address_range_id',
        code: 'INVALID',
        message: '与展示无关的字段提示',
      },
    ],
  },
}
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }
const RANGE_UNAVAILABLE_NOT_FOUND_BODY = {
  error: {
    code: 'NOT_FOUND',
    message: '与展示无关的范围段未找到文案',
    details: [
      {
        row: null,
        field: 'ip_address_range_id',
        code: 'IP_ADDRESS_RANGE_UNAVAILABLE',
        message: '与展示无关的范围段未找到详情',
      },
    ],
  },
}
const RANGE_UNAVAILABLE_CONFLICT_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的范围段冲突文案',
    details: [
      {
        row: null,
        field: 'ip_address_range_id',
        code: 'IP_ADDRESS_RANGE_UNAVAILABLE',
        message: '与展示无关的范围段冲突详情',
      },
    ],
  },
}
const NO_AVAILABLE_IP_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的耗尽文案',
    details: [
      { row: null, field: null, code: 'NO_AVAILABLE_IP', message: '与展示无关的耗尽详情' },
    ],
  },
}
const OUT_OF_RANGE_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的范围文案',
    details: [
      { row: null, field: 'ip_address', code: 'OUT_OF_RANGE', message: '与展示无关的范围详情' },
    ],
  },
}
const DUPLICATE_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的占用文案',
    details: [
      { row: null, field: 'ip_address', code: 'DUPLICATE', message: '与展示无关的占用详情' },
    ],
  },
}

describe('错误分支（契约 §4 稳定判别值；不解析 message）', () => {
  it('400 VALIDATION_ERROR（details[].field = ip_address_range_id）→ 字段级提示，对话框保持打开', async () => {
    stubFetch({ allocateAuto: () => jsonResponse(400, VALIDATION_BODY) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('ip_address_range_id')
    expect(wrapper.text()).not.toContain('与展示无关的校验文案')
    expect(wrapper.props('modelValue')).toBe(true)
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，本地不渲染失败提示', async () => {
    stubFetch({
      allocateManual: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '与展示无关的未认证文案' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('10.0.0.5')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    })
    expect(wrapper.text()).not.toContain('与展示无关的未认证文案')
  })

  it('404 NOT_FOUND（details == []：目标 NIC 不存在 / 已删 / 宿主不活跃）→ 「目标网络接口不存在或已停用」', async () => {
    stubFetch({ allocateAuto: () => jsonResponse(404, NOT_FOUND_BODY) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('无法分配')
    expect(alert.text()).toContain('目标网络接口不存在或已停用')
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
    expect(wrapper.props('modelValue')).toBe(true)
  })

  it('404 NOT_FOUND + IP_ADDRESS_RANGE_UNAVAILABLE（所选范围段不存在 / 已删）→ 「所选地址范围段不存在或已删除，请重新选择」', async () => {
    stubFetch({ allocateAuto: () => jsonResponse(404, RANGE_UNAVAILABLE_NOT_FOUND_BODY) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-detail-code')).toBe('IP_ADDRESS_RANGE_UNAVAILABLE')
    expect(alert.text()).toContain('所选地址范围段不存在或已删除，请重新选择')
    // 与 NIC 404（details == []）分支互异：不误报网络接口失效。
    expect(alert.text()).not.toContain('目标网络接口不存在或已停用')
    expect(wrapper.text()).not.toContain('与展示无关的范围段未找到文案')
    expect(wrapper.text()).not.toContain('与展示无关的范围段未找到详情')
  })

  it('409 CONFLICT + IP_ADDRESS_RANGE_UNAVAILABLE（所选范围段属于其它 Cluster）→ 「所选地址范围段不属于该集群，请重新选择」', async () => {
    stubFetch({ allocateAuto: () => jsonResponse(409, RANGE_UNAVAILABLE_CONFLICT_BODY) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-detail-code')).toBe('IP_ADDRESS_RANGE_UNAVAILABLE')
    expect(alert.text()).toContain('所选地址范围段不属于该集群，请重新选择')
    expect(wrapper.text()).not.toContain('与展示无关的范围段冲突文案')
    expect(wrapper.text()).not.toContain('与展示无关的范围段冲突详情')
  })

  it('409 CONFLICT + NO_AVAILABLE_IP（所选范围段耗尽，不回退）→ 「所选地址范围段已无可用 IP」（不表述集群并集）；更换范围段后重试成功', async () => {
    let calls = 0
    stubFetch({
      allocateAuto: () => {
        calls += 1
        return calls === 1 ? jsonResponse(409, NO_AVAILABLE_IP_BODY) : jsonResponse(201, ALLOCATED)
      },
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-detail-code')).toBe('NO_AVAILABLE_IP')
    expect(alert.text()).toContain('所选地址范围段已无可用 IP')
    // F023 文案边界：不再表述「整个集群并集 / 地址池」。
    expect(alert.text()).not.toContain('集群地址池')
    expect(alert.text()).not.toContain('并集')
    expect(wrapper.text()).not.toContain('与展示无关的耗尽文案')
    expect(wrapper.text()).not.toContain('与展示无关的耗尽详情')

    // 可重试：更换范围段（ID 8）后再次提交 → 成功态。
    await selectRange(wrapper, 8)
    await submitWhenEnabled(wrapper)
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('success')
    })
    expect(wrapper.emitted('success')).toEqual([[ALLOCATED]])
  })

  it('409 CONFLICT + OUT_OF_RANGE（手动范围外）→ 「该地址不在任何活跃地址范围内」', async () => {
    stubFetch({ allocateManual: () => jsonResponse(409, OUT_OF_RANGE_BODY) })

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('192.168.1.1')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-detail-code')).toBe('OUT_OF_RANGE')
    expect(alert.text()).toContain('该地址不在任何活跃地址范围内')
    expect(wrapper.text()).not.toContain('与展示无关的范围文案')
    expect(wrapper.text()).not.toContain('与展示无关的范围详情')
  })

  it('409 CONFLICT + DUPLICATE（已占用 / 并发冲突）→ 「该地址已被占用」；修改后重试成功 → 成功态', async () => {
    let calls = 0
    stubFetch({
      allocateManual: () => {
        calls += 1
        return calls === 1 ? jsonResponse(409, DUPLICATE_BODY) : jsonResponse(201, ALLOCATED)
      },
    })

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('10.0.0.5')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-detail-code')).toBe('DUPLICATE')
    expect(alert.text()).toContain('该地址已被占用')
    expect(alert.text()).toContain('重试')
    expect(wrapper.text()).not.toContain('与展示无关的占用文案')
    expect(wrapper.text()).not.toContain('与展示无关的占用详情')

    // 可重试：修改地址后再次提交 → 成功态。
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('10.0.0.6')
    await submitWhenEnabled(wrapper)
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('success')
    })
    expect(wrapper.emitted('success')).toEqual([[ALLOCATED]])
  })
})

describe('分配动作三态互异（Loading / Empty / Error）', () => {
  it('提交中 → Loading 态：提交按钮 Loading、无引导文案 / 无失败提示 / 无结果；重复点击不产生第二个 POST', async () => {
    let releaseAllocate!: () => void
    const allocateGate = new Promise<void>((resolve) => {
      releaseAllocate = resolve
    })
    const fetchMock = stubFetch({
      allocateAuto: async () => {
        await allocateGate
        return jsonResponse(201, ALLOCATED)
      },
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate')).toBe(1)
    })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('loading')
    })
    // Loading 态标记互异：引导文案 / 失败提示 / 结果区均不渲染。
    expect(wrapper.find('[data-testid="allocate-guidance"]').exists()).toBe(false)
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocate-result"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocate-submit"]').classes()).toContain('is-loading')

    // 连点不发出第二个 POST（提交中拦截重复提交）。
    await wrapper.find('[data-testid="allocate-submit"]').trigger('click')
    expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate')).toBe(1)

    releaseAllocate()
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('success')
    })
  })

  it('Empty / Loading / Error 三态标记互异：同一对话框先后呈现 empty → loading → error →（重试）success', async () => {
    let calls = 0
    let releaseAllocate: () => void = () => {}
    let allocateGate: Promise<void> = Promise.resolve()
    stubFetch({
      allocateAuto: () => {
        calls += 1
        if (calls === 1) {
          return jsonResponse(409, NO_AVAILABLE_IP_BODY)
        }
        allocateGate = new Promise<void>((resolve) => {
          releaseAllocate = resolve
        })
        return allocateGate.then(() => jsonResponse(201, ALLOCATED))
      },
    })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForRangeOptions(wrapper)
    await selectRange(wrapper, 7)
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    const emptyMarker = stateNode(wrapper).attributes('data-state')

    await submitWhenEnabled(wrapper)
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const errorMarker = stateNode(wrapper).attributes('data-state')
    // Error 态：失败提示可见、引导文案不渲染（与 Empty 互异）。
    expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="allocate-guidance"]').exists()).toBe(false)

    await submitWhenEnabled(wrapper)
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('loading')
    })
    const loadingMarker = stateNode(wrapper).attributes('data-state')
    // Loading 态：失败提示与引导文案均不渲染（与 Empty / Error 互异）。
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocate-guidance"]').exists()).toBe(false)

    releaseAllocate()
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('success')
    })

    expect(new Set([emptyMarker, errorMarker, loadingMarker])).toEqual(
      new Set(['empty', 'error', 'loading']),
    )
  })
})
