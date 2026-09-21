import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import IpAddressListPage from '../src/pages/IpAddressListPage.vue'
import IpAddressAllocateDialog from '../src/components/IpAddressAllocateDialog.vue'

/**
 * F021 分配入口接线测试（IpAddressListPage；f021 handoff Frontend Work
 * 「入口落点」）。
 *
 * 覆盖：全局列表页与 NIC 限定列表页均提供「自动分配 IP」/「手动分配 IP」
 * 两个入口；全局入口在对话框内先选择目标 NIC（GET /api/network-interfaces
 * 选择器），NIC 上下文入口预选目标 NIC（只读展示）；分配成功 → 刷新列表。
 * 错误分支与三态见 ipAddressAllocateDialog.spec.ts；请求构造另见
 * ipAddressAllocationApi.spec.ts。
 */

const IP_ADDRESS_EXISTING = {
  id: 40,
  network_interface_id: 12,
  ip_address: '10.0.0.4',
  created_at: '2026-09-21T09:00:00Z',
  updated_at: '2026-09-21T09:00:00Z',
}
const ALLOCATED = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.0.5',
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
}

const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }

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

interface PageRoutes {
  list?: () => Response
  networkInterfaces?: () => Response
  allocateAuto?: () => Response | Promise<Response>
  allocateManual?: () => Response | Promise<Response>
}

/** 按端点分发的 fetch 桩；未配置的路由返回 404 以暴露意外请求。 */
function stubFetch(routes: PageRoutes = {}) {
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
    if (url.includes('/api/ip-addresses')) {
      return routes.list?.() ?? jsonResponse(200, EMPTY_LIST_BODY)
    }
    return jsonResponse(404, { error: { code: 'NOT_FOUND', message: '未匹配的桩路由' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountPage(props: { networkInterfaceId?: number | null } = {}) {
  return mount(IpAddressListPage, {
    props,
    global: { plugins: [ElementPlus] },
  })
}

async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/** 打开分配对话框并等待内容挂载（el-dialog 首开才挂载）。 */
async function openAllocate(
  wrapper: VueWrapper,
  testid: 'open-allocate-auto' | 'open-allocate-manual',
): Promise<void> {
  await wrapper.find(`[data-testid="${testid}"]`).trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="allocate-submit"]').exists()).toBe(true)
  })
}

/** 页面内分配对话框的目标网络接口下拉（全局入口）。 */
function findNicSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findComponent(IpAddressAllocateDialog)
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('ip-address-allocate__nic-select'))
  expect(select, '期望找到目标网络接口下拉').toBeDefined()
  return select!
}

/** 等待分配提交按钮解除 disabled 后点击。 */
async function submitAllocateWhenEnabled(wrapper: VueWrapper): Promise<void> {
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })
  await wrapper.find('[data-testid="allocate-submit"]').trigger('click')
}

function listGetCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) =>
      String(call[0]).includes('/api/ip-addresses') &&
      (call[1] as RequestInit | undefined)?.method !== 'POST',
  ).length
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('IpAddressListPage 分配入口（F021）', () => {
  it('全局列表页：提供「自动分配 IP」与「手动分配 IP」两个入口（Empty 态仍可达，不依赖内容态）', async () => {
    stubFetch({ list: () => jsonResponse(200, EMPTY_LIST_BODY) })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    expect(wrapper.find('[data-testid="open-allocate-auto"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="open-allocate-manual"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="open-allocate-auto"]').text()).toContain('自动分配 IP')
    expect(wrapper.find('[data-testid="open-allocate-manual"]').text()).toContain('手动分配 IP')
  })

  it('全局入口（自动）：先在对话框内选择目标 NIC（GET /api/network-interfaces），再提交', async () => {
    const fetchMock = stubFetch({ list: () => jsonResponse(200, EMPTY_LIST_BODY) })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    await openAllocate(wrapper, 'open-allocate-auto')

    // 全局入口：对话框内渲染目标网络接口下拉并加载选项（先选 NIC）。
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url) === '/api/network-interfaces?page=1&page_size=200'),
      ).toBe(true)
    })
    expect(findNicSelect(wrapper)).toBeDefined()
    // 未选择 NIC → 提交禁用（基础必填）。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeDefined()

    await findNicSelect(wrapper).vm.$emit('update:modelValue', 12)
    await submitAllocateWhenEnabled(wrapper)

    await waitForUi(() => {
      const allocateCalls = fetchMock.mock.calls.filter(
        (call) =>
          String(call[0]) === '/api/ip-addresses/allocate' &&
          (call[1] as RequestInit | undefined)?.method === 'POST',
      )
      expect(allocateCalls).toHaveLength(1)
      expect(JSON.parse((allocateCalls[0]![1] as RequestInit).body as string)).toEqual({
        network_interface_id: 12,
      })
    })
  })

  it('全局入口（手动）：选择目标 NIC + 输入地址 → POST /api/ip-addresses/allocate-manual', async () => {
    const fetchMock = stubFetch({ list: () => jsonResponse(200, EMPTY_LIST_BODY) })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    await openAllocate(wrapper, 'open-allocate-manual')
    await findNicSelect(wrapper).vm.$emit('update:modelValue', 12)
    await wrapper.find('[data-testid="allocate-ip-address"]').setValue('10.0.0.5')
    await submitAllocateWhenEnabled(wrapper)

    await waitForUi(() => {
      const manualCalls = fetchMock.mock.calls.filter(
        (call) =>
          String(call[0]) === '/api/ip-addresses/allocate-manual' &&
          (call[1] as RequestInit | undefined)?.method === 'POST',
      )
      expect(manualCalls).toHaveLength(1)
      expect(JSON.parse((manualCalls[0]![1] as RequestInit).body as string)).toEqual({
        network_interface_id: 12,
        ip_address: '10.0.0.5',
      })
    })
  })

  it('NIC 限定列表页：入口打开的对话框只读展示目标 NIC（不渲染下拉、不请求网络接口列表）', async () => {
    const fetchMock = stubFetch({
      list: () => jsonResponse(200, EMPTY_LIST_BODY),
    })

    const wrapper = mountPage({ networkInterfaceId: 12 })
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    await openAllocate(wrapper, 'open-allocate-auto')

    const dialog = wrapper.findComponent(IpAddressAllocateDialog)
    expect(dialog.find('[data-testid="allocate-preset-nic"]').text()).toContain('网络接口 #12')
    expect(dialog.findAllComponents(ElSelect)).toHaveLength(0)
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/api/network-interfaces')),
    ).toBe(false)
    // 目标已由上下文预设 → 表单已完成，可直接提交。
    expect(wrapper.find('[data-testid="allocate-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('NIC 限定列表页：自动分配成功（201）→ 刷新列表，新行出现；结果区展示新 ip_address 与 id', async () => {
    const activeList = { items: [IP_ADDRESS_EXISTING], total: 1, page: 1, page_size: 50 }
    const fetchMock = stubFetch({
      list: () => jsonResponse(200, activeList),
      allocateAuto: () => {
        activeList.items = [IP_ADDRESS_EXISTING, ALLOCATED]
        activeList.total = 2
        return jsonResponse(201, ALLOCATED)
      },
    })

    const wrapper = mountPage({ networkInterfaceId: 12 })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    const listCallsBefore = listGetCalls(fetchMock)

    await openAllocate(wrapper, 'open-allocate-auto')
    await submitAllocateWhenEnabled(wrapper)

    // 成功 → 刷新列表（第二次 GET，两行）。
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    expect(listGetCalls(fetchMock)).toBeGreaterThanOrEqual(listCallsBefore + 1)
    expect(wrapper.findAll('.el-table__row')[1]!.text()).toContain('10.0.0.5')
    // 对话框结果区展示新 ip_address 与 id。
    expect(wrapper.find('[data-testid="allocate-result-ip"]').text()).toBe('10.0.0.5')
    expect(wrapper.find('[data-testid="allocate-result-id"]').text()).toBe('41')
  })
})
