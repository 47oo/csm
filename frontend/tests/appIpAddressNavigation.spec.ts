import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * App 资源视图切换测试（F005，f005-ip-address-handoff.md Frontend Work #6）：
 * 头部导航的全局 IP 地址列表（无过滤），以及从网络接口详情进入「查看 IP 地址」
 * （携带 network_interface_id 的过滤视图）→ IP 地址详情 → 返回（过滤上下文
 * 保留）→ 返回网络接口详情（其列表过滤上下文恢复）。仍不引入 vue-router。
 *
 * 响应体严格按 docs/api/f005-ip-address.md 与 f004-network-interface.md /
 * f002-bare-metal.md / f001-cluster.md / f013-auth.md 构造；fetch 桩替换，
 * 不触达真实后端。
 */

const SESSION_USER = { id: 1, username: 'admin' }
const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const CLUSTER_LIST_BODY = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }
const BARE_METAL_A = {
  id: 11,
  cluster_id: 1,
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
const BARE_METAL_LIST_BODY = { items: [BARE_METAL_A], total: 1, page: 1, page_size: 50 }

/**
 * F010：空五类关联聚合响应体（f010-resource-detail.md §2）。裸金属详情页
 * 挂载时会并行请求 GET /api/bare-metals/{id}/related。
 */
const RELATED_EMPTY_BODY = {
  network_interfaces: { items: [], total: 0 },
  ip_addresses: { items: [], total: 0 },
  virtual_machines: { items: [], total: 0 },
  containers: { items: [], total: 0 },
  services: { items: [], total: 0 },
}
const NETWORK_INTERFACE_A = {
  id: 12,
  bare_metal_id: 11,
  name: 'eth0',
  technology_type: 'Ethernet',
  purpose: 'Business',
  created_at: '2026-09-17T10:00:00Z',
  updated_at: '2026-09-17T10:00:00Z',
}
const NETWORK_INTERFACE_LIST_BODY = {
  items: [NETWORK_INTERFACE_A],
  total: 1,
  page: 1,
  page_size: 50,
}
const IP_ADDRESS_A = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.1.1/16',
  created_at: '2026-09-18T10:00:00Z',
  updated_at: '2026-09-18T10:00:00Z',
}
const IP_ADDRESS_LIST_BODY = {
  items: [IP_ADDRESS_A],
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
    if (/\/api\/ip-addresses\/\d+/.test(url)) {
      return jsonResponse(200, IP_ADDRESS_A)
    }
    if (url.includes('/api/ip-addresses')) {
      return jsonResponse(200, IP_ADDRESS_LIST_BODY)
    }
    if (/\/api\/network-interfaces\/\d+/.test(url)) {
      return jsonResponse(200, NETWORK_INTERFACE_A)
    }
    if (url.includes('/api/network-interfaces')) {
      return jsonResponse(200, NETWORK_INTERFACE_LIST_BODY)
    }
    if (/\/api\/bare-metals\/\d+\/related/.test(url)) return jsonResponse(200, RELATED_EMPTY_BODY)
    if (/\/api\/bare-metals\/\d+/.test(url)) return jsonResponse(200, BARE_METAL_A)
    if (url.includes('/api/bare-metals')) return jsonResponse(200, BARE_METAL_LIST_BODY)
    if (/\/api\/clusters\/\d+/.test(url)) return jsonResponse(200, CLUSTER_A)
    if (url.includes('/api/clusters')) return jsonResponse(200, CLUSTER_LIST_BODY)
    return notFound()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountApp() {
  return mount(App, { global: { plugins: [ElementPlus] } })
}

function findButton(wrapper: ReturnType<typeof mountApp>, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text().includes(text))
  expect(button, `期望找到「${text}」按钮`).toBeDefined()
  return button!
}

/** 按精确文本找按钮（避免「详情」误匹配「返回集群详情」等包含式文案）。 */
function findButtonExact(wrapper: ReturnType<typeof mountApp>, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text() === text)
  expect(button, `期望找到文本恰为「${text}」的按钮`).toBeDefined()
  return button!
}

/**
 * vi.waitFor 包装：全量并行负载下页面挂载 / el-dialog 挂载 / 异步完成偶发超过
 * vi.waitFor 默认 1s（单文件运行稳定）。随测试文件数增长，已先后放宽到
 * 5s、10s；仅放宽超时上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

afterEach(() => {
  vi.unstubAllGlobals()
  // App 挂载时会注册全局未认证处理器，卸载后清除，保证测试隔离。
  setUnauthenticatedHandler(null)
})

describe('App 视图切换：网络接口详情 → 该网络接口 IP 地址（携带 network_interface_id）', () => {
  it('网络接口详情 →「查看 IP 地址」→ IP 列表（请求携带 network_interface_id）→ 详情 → 返回（过滤上下文保留）→ 返回网络接口详情（上下文恢复）', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    // 集群列表就绪。
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.text()).toContain('集群列表')

    // 集群详情 → 该集群裸金属列表（携带 cluster_id）→ 裸金属详情 →
    // 该宿主网络接口列表（携带 bare_metal_id）→ 网络接口详情。
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('cluster-a')
    })
    await findButton(wrapper, '查看裸金属').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('裸金属列表')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('裸金属详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('cn001')
    })
    await findButton(wrapper, '查看网络接口').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('网络接口列表')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('网络接口详情')
    })
    // 等待内容态就绪（入口仅内容态出现）。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('eth0')
    })

    // 从网络接口详情进入该 NIC 的 IP 地址列表（携带 network_interface_id，
    // 契约 §3.2）。
    await findButton(wrapper, '查看 IP 地址').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址列表')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/ip-addresses?page=1&page_size=50&network_interface_id=12',
        expect.objectContaining({ method: 'GET' }),
      )
    })
    // 过滤上下文与返回语义可见。
    expect(wrapper.text()).toContain('网络接口 #12')
    expect(wrapper.text()).toContain('返回网络接口详情')

    // 进入 IP 地址详情。
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('10.0.1.1/16')
    })

    // 返回列表：过滤上下文保留（仍携带 network_interface_id 重新请求）。
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址列表')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/ip-addresses?page=1&page_size=50&network_interface_id=12',
        expect.objectContaining({ method: 'GET' }),
      )
    })

    // 从过滤列表返回 → 回到网络接口详情（其列表过滤上下文恢复）。
    await findButton(wrapper, '返回网络接口详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('网络接口详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('eth0')
    })

    // 网络接口详情返回 → 网络接口列表仍携带 bare_metal_id（上下文未被 IP
    // 视图破坏）。
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('网络接口列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/network-interfaces?page=1&page_size=50&bare_metal_id=11',
        expect.objectContaining({ method: 'GET' }),
      )
    })

    // 网络接口列表返回 → 裸金属详情（集群过滤上下文恢复）→ 裸金属列表仍携带
    // cluster_id。
    await findButton(wrapper, '返回裸金属详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('裸金属详情')
    })
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('裸金属列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/bare-metals?page=1&page_size=50&cluster_id=1',
        expect.objectContaining({ method: 'GET' }),
      )
    })
  })
})

describe('App 头部导航：全局 IP 地址列表（无过滤）', () => {
  it('点击「IP 地址」→ 列表请求不带 network_interface_id；返回按钮回集群列表', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    // 头部导航进入全局 IP 地址列表。
    await findButton(wrapper, 'IP 地址').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/ip-addresses?page=1&page_size=50',
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

  it('导航高亮随资源区域切换（ip-address 区域下「IP 地址」高亮）', async () => {
    stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, 'IP 地址').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('IP 地址列表')
    })
    const navIp = wrapper.find('[data-testid="nav-ip-addresses"]')
    expect(navIp.classes()).toContain('el-button--primary')

    // 切回集群区域：高亮恢复。
    await findButton(wrapper, '集群').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群列表')
    })
    expect(wrapper.find('[data-testid="nav-ip-addresses"]').classes()).not.toContain(
      'el-button--primary',
    )
    expect(wrapper.find('[data-testid="nav-clusters"]').classes()).toContain('el-button--primary')
  })
})
