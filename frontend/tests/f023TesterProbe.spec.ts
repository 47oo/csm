import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import IpAddressAllocateDialog from '../src/components/IpAddressAllocateDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * F023 独立前端验收探针（Tester）。
 *
 * 只验证 AC-18 的可观察行为（不修改生产代码）：
 *  - 自动分配必须选择范围段方可提交（未选 → 禁用且不发起请求）；
 *  - 目标 Cluster 无活跃范围段 → Empty 态且禁用提交；
 *  - 三态互异（empty / loading / error / success）；
 *  - 新错误码分支（含 IP_ADDRESS_RANGE_UNAVAILABLE）按 error.code +
 *    details[].code 渲染固定文案，**不解析 message**。
 */

const ALLOCATED = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.0.5',
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
}

const BMC = {
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

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

interface Routes {
  ranges?: () => Response | Promise<Response>
  allocateAuto?: () => Response | Promise<Response>
}

function stub(routes: Routes = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (method === 'POST' && url === '/api/ip-addresses/allocate') {
      return routes.allocateAuto?.() ?? jsonResponse(201, ALLOCATED)
    }
    if (method === 'GET' && /^\/api\/network-interfaces\/\d+$/.test(url)) {
      return jsonResponse(200, { ...ALLOCATED, id: 12, bare_metal_id: 11 })
    }
    if (method === 'GET' && /^\/api\/bare-metals\/\d+$/.test(url)) {
      return jsonResponse(200, BMC)
    }
    if (method === 'GET' && /^\/api\/ip-address-ranges\?/.test(url)) {
      return (
        routes.ranges ??
        (() => jsonResponse(200, { items: [RANGE_A], total: 1, page: 1, page_size: 200 }))
      )()
    }
    return jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'unmatched' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountDialog() {
  return mount(IpAddressAllocateDialog, {
    props: { modelValue: true, mode: 'auto' as const, presetNetworkInterfaceId: 12 },
    global: { plugins: [ElementPlus] },
  })
}

function stateNode(w: VueWrapper) {
  return w.find('[data-testid="allocate-state"]')
}
function submitButton(w: VueWrapper) {
  return w.find('[data-testid="allocate-submit"]')
}
function rangeSelect(w: VueWrapper) {
  return w
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('ip-address-allocate__range-select'))!
}
async function waitForRangeLoaded(w: VueWrapper) {
  await vi.waitFor(
    () => {
      expect(rangeSelect(w).findAllComponents({ name: 'ElOption' }).length).toBeGreaterThan(0)
    },
    { timeout: 10000 },
  )
}
function postCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    ([input, init]) =>
      String(input) === '/api/ip-addresses/allocate' &&
      (init as RequestInit | undefined)?.method === 'POST',
  ).length
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('F023 独立前端探针（AC-18）', () => {
  it('范围段为必选：未选择时提交禁用且不发起 POST；选择后解除', async () => {
    const fetchMock = stub()
    const w = mountDialog()
    await waitForRangeLoaded(w)

    expect(submitButton(w).attributes('disabled')).toBeDefined()
    // 试图触发（已禁用按钮）不得产生请求。
    await submitButton(w).trigger('click')
    expect(postCount(fetchMock)).toBe(0)

    await rangeSelect(w).vm.$emit('update:modelValue', 7)
    expect(submitButton(w).attributes('disabled')).toBeUndefined()
  })

  it('目标 Cluster 无活跃范围段 → Empty 态提示且提交禁用', async () => {
    stub({ ranges: () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 200 }) })
    const w = mountDialog()
    await vi.waitFor(
      () => {
        expect(w.find('[data-testid="allocate-range-empty"]').exists()).toBe(true)
      },
      { timeout: 10000 },
    )
    expect(w.find('[data-testid="allocate-range-empty"]').text()).toContain('暂无可用地址范围段')
    expect(submitButton(w).attributes('disabled')).toBeDefined()
  })

  it('三态互异：empty → loading → success/error', async () => {
    let resolveAlloc!: (r: Response) => void
    const pending = new Promise<Response>((res) => {
      resolveAlloc = res
    })
    stub({ allocateAuto: () => pending })
    const w = mountDialog()
    await waitForRangeLoaded(w)

    expect(stateNode(w).attributes('data-state')).toBe('empty')
    expect(w.find('[data-testid="allocate-guidance"]').exists()).toBe(true)

    await rangeSelect(w).vm.$emit('update:modelValue', 7)
    await submitButton(w).trigger('click')
    await vi.waitFor(() => expect(stateNode(w).attributes('data-state')).toBe('loading'))
    // loading 与 error / success 互异：无结果区、无错误码。
    expect(w.find('[data-testid="allocate-result"]').exists()).toBe(false)
    expect(w.find('[data-error-code]').exists()).toBe(false)

    resolveAlloc(jsonResponse(201, ALLOCATED))
    await vi.waitFor(() => expect(stateNode(w).attributes('data-state')).toBe('success'))
    expect(w.find('[data-testid="allocate-result-ip"]').text()).toBe('10.0.0.5')
  })

  it('错误分支按 code/details 渲染固定文案，不解析 message（404 范围段）', async () => {
    const SENTINEL = 'SENTINEL_MESSAGE_MUST_NOT_RENDER'
    stub({
      allocateAuto: () =>
        jsonResponse(404, {
          error: {
            code: 'NOT_FOUND',
            message: SENTINEL,
            details: [
              { row: null, field: 'ip_address_range_id', code: 'IP_ADDRESS_RANGE_UNAVAILABLE', message: SENTINEL },
            ],
          },
        }),
    })
    const w = mountDialog()
    await waitForRangeLoaded(w)
    await rangeSelect(w).vm.$emit('update:modelValue', 7)
    await submitButton(w).trigger('click')

    await vi.waitFor(() =>
      expect(w.find('[data-error-code]').attributes('data-error-code')).toBe('NOT_FOUND'),
    )
    expect(w.find('[data-error-code]').attributes('data-error-detail-code')).toBe(
      'IP_ADDRESS_RANGE_UNAVAILABLE',
    )
    expect(w.find('[data-error-code]').text()).toContain('不存在或已删除')
    expect(w.html()).not.toContain(SENTINEL)
  })

  it('错误分支 409 + IP_ADDRESS_RANGE_UNAVAILABLE（跨 Cluster）', async () => {
    stub({
      allocateAuto: () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: 'msg',
            details: [
              { row: null, field: 'ip_address_range_id', code: 'IP_ADDRESS_RANGE_UNAVAILABLE', message: 'm' },
            ],
          },
        }),
    })
    const w = mountDialog()
    await waitForRangeLoaded(w)
    await rangeSelect(w).vm.$emit('update:modelValue', 7)
    await submitButton(w).trigger('click')

    await vi.waitFor(() =>
      expect(w.find('[data-error-code]').attributes('data-error-code')).toBe('CONFLICT'),
    )
    expect(w.find('[data-error-code]').attributes('data-error-detail-code')).toBe(
      'IP_ADDRESS_RANGE_UNAVAILABLE',
    )
    expect(w.find('[data-error-code]').text()).toContain('不属于该集群')
  })

  it('错误分支 409 + NO_AVAILABLE_IP（所选段耗尽）', async () => {
    stub({
      allocateAuto: () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: 'msg',
            details: [{ row: null, field: null, code: 'NO_AVAILABLE_IP', message: 'm' }],
          },
        }),
    })
    const w = mountDialog()
    await waitForRangeLoaded(w)
    await rangeSelect(w).vm.$emit('update:modelValue', 7)
    await submitButton(w).trigger('click')

    await vi.waitFor(() =>
      expect(w.find('[data-error-code]').attributes('data-error-detail-code')).toBe(
        'NO_AVAILABLE_IP',
      ),
    )
    expect(w.find('[data-error-code]').text()).toContain('已无可用 IP')
  })

  it('NIC 404（details == []）与范围段 404 文案互异', async () => {
    stub({
      allocateAuto: () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'm', details: [] } }),
    })
    const w = mountDialog()
    await waitForRangeLoaded(w)
    await rangeSelect(w).vm.$emit('update:modelValue', 7)
    await submitButton(w).trigger('click')

    await vi.waitFor(() =>
      expect(w.find('[data-error-code]').attributes('data-error-detail-code')).toBeUndefined(),
    )
    expect(w.find('[data-error-code]').text()).toContain('目标网络接口不存在或已停用')
  })
})