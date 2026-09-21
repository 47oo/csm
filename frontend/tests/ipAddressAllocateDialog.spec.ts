import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import IpAddressAllocateDialog from '../src/components/IpAddressAllocateDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * F021 分配对话框测试（AC-33 / f021 handoff Frontend Work）。
 *
 * 覆盖：两个端点的调用与请求体（恰为契约封闭字段集合）、分配动作三态互异
 * （Empty = 尚未分配结果 / Loading = 提交中拦截重复 / Error = 按
 * error.code 分支）、六类错误分支（400 字段级 / 401 全局处理 / 404 /
 * 409 NO_AVAILABLE_IP / 409 OUT_OF_RANGE / 409 DUPLICATE，均不解析
 * message）、成功结果区（新 ip_address 与 id + emit success）与「前端不做
 * 客户端业务校验」（§21：非法 IPv4 / 首尾空白 / 前导零 / 仅空白串均原样
 * 提交，仅空串按基础必填禁用）。
 *
 * 响应体严格按 docs/api/f021-ip-address-allocation.md 构造（§2 资源表示
 * （复用 F005）/ §3 两个端点 / §4 错误信封）。fetch 全部桩替换。
 */

const ALLOCATED = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.0.5',
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
}

/** 目标网络接口选项（GET /api/network-interfaces，f004 契约 §3.2 信封）。 */
const NIC_LIST_BODY = {
  items: [
    {
      id: 12,
      bare_metal_id: 11,
      name: 'eth0',
      technology_type: 'Ethernet',
      purpose: 'Business',
      created_at: '2026-09-17T10:00:00Z',
      updated_at: '2026-09-17T10:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 200,
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

interface AllocateRoutes {
  networkInterfaces?: () => Response
  allocateAuto?: () => Response | Promise<Response>
  allocateManual?: () => Response | Promise<Response>
}

/** 按端点分发的 fetch 桩；未配置的路由返回 404 以暴露意外请求。 */
function stubFetch(routes: AllocateRoutes = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'POST' && url === '/api/ip-addresses/allocate') {
      return routes.allocateAuto?.() ?? jsonResponse(201, ALLOCATED)
    }
    if (init?.method === 'POST' && url === '/api/ip-addresses/allocate-manual') {
      return routes.allocateManual?.() ?? jsonResponse(201, ALLOCATED)
    }
    if (url.includes('/api/network-interfaces')) {
      return (routes.networkInterfaces ?? (() => jsonResponse(200, NIC_LIST_BODY)))()
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

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('自动分配（NIC 上下文预设目标 NIC）', () => {
  it('打开 → 只读展示目标 NIC（不渲染下拉）；Empty 态：引导文案可见，无失败提示 / 无结果', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })

    await waitForUi(() => {
      expect(stateNode(wrapper).exists()).toBe(true)
    })
    expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    expect(wrapper.find('[data-testid="allocate-preset-nic"]').text()).toContain('网络接口 #12')
    // NIC 上下文：目标已由上下文固定，不渲染选择器，也不请求网络接口列表。
    expect(wrapper.findAllComponents(ElSelect)).toHaveLength(0)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/network-interfaces'))).toBe(false)
    // Empty 态：引导文案可见；无失败提示、无成功结果。
    expect(wrapper.find('[data-testid="allocate-guidance"]').exists()).toBe(true)
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="allocate-result"]').exists()).toBe(false)
    // 表单已完成（基础必填：NIC 已由上下文预设），可直接提交。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('提交 → POST /api/ip-addresses/allocate，请求体恰为 {network_interface_id}（§3.1 封闭）；成功 → 结果区展示 ip_address 与 id、emit success、对话框保持打开', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })

    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate')).toBe(1)
    })
    expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate')).toEqual({
      network_interface_id: 12,
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

  it('关闭后重新打开 → 重置为 Empty 态（无结果 / 无失败，引导文案重新可见）', async () => {
    stubFetch({ allocateAuto: () => jsonResponse(201, ALLOCATED) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
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
      expect(
        fetchMock.mock.calls.some(([url]) => String(url) === '/api/network-interfaces?page=1&page_size=200'),
      ).toBe(true)
    })
    // 基础必填：目标 NIC 未选择 → 表单未完成。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()

    await selectNic(wrapper, 12)
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('选择目标 NIC 后提交（自动）→ POST /api/ip-addresses/allocate，请求体恰为 {network_interface_id}', async () => {
    const fetchMock = stubFetch()

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: null })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await selectNic(wrapper, 12)
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(allocateCalls(fetchMock, '/api/ip-addresses/allocate')).toBe(1)
    })
    expect(lastAllocateBody(fetchMock, '/api/ip-addresses/allocate')).toEqual({
      network_interface_id: 12,
    })
  })

  it('选择目标 NIC + 输入地址后提交（手动）→ POST /api/ip-addresses/allocate-manual，请求体恰为两字段', async () => {
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
      // 成功 → 回到 Empty 由重开或直接继续：成功后结果区清空前值，继续提交
      // 会再次进入 Loading；此处重置为下一次探测输入即可。
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
    details: [{ field: 'ip_address', code: 'INVALID', message: '与展示无关的字段提示' }],
  },
}
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }
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
  it('400 VALIDATION_ERROR → 字段级提示（details[].field），对话框保持打开', async () => {
    stubFetch({ allocateManual: () => jsonResponse(400, VALIDATION_BODY) })

    const wrapper = mountDialog({ mode: 'manual', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('10.0.0.256')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('ip_address')
    // 分支与固定文案不解析 message：顶层 error.message 不参与渲染；
    // details[].message 作为服务端字段级提示原样展示（与 IpAddressFormDialog /
    // ErrorState 同一策略，展示不影响分支）。
    expect(wrapper.text()).not.toContain('与展示无关的校验文案')
    // 失败不关闭对话框（用户可修改后重试）。
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

  it('404 NOT_FOUND（目标 NIC 不存在 / 已删 / 宿主不活跃）→ 「目标网络接口不存在或已停用」', async () => {
    stubFetch({ allocateAuto: () => jsonResponse(404, NOT_FOUND_BODY) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 999 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
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

  it('409 CONFLICT + NO_AVAILABLE_IP（自动分配耗尽）→ 「该集群地址池已无可用 IP」', async () => {
    stubFetch({ allocateAuto: () => jsonResponse(409, NO_AVAILABLE_IP_BODY) })

    const wrapper = mountDialog({ mode: 'auto', presetNetworkInterfaceId: 12 })
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-detail-code')).toBe('NO_AVAILABLE_IP')
    expect(alert.text()).toContain('该集群地址池已无可用 IP')
    expect(wrapper.text()).not.toContain('与展示无关的耗尽文案')
    expect(wrapper.text()).not.toContain('与展示无关的耗尽详情')
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
    await waitForUi(() => {
      expect(stateNode(wrapper).attributes('data-state')).toBe('empty')
    })
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
