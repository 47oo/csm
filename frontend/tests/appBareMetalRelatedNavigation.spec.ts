import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * App 视图切换测试（F010，f010-resource-detail-handoff.md Frontend Work #3）：
 * 从裸金属详情「关联资源」条目直接进入五类子资源详情，返回时回到裸金属详情
 * （保留返回上下文，含集群过滤上下文）。仍不引入 vue-router。
 *
 * 响应体严格按 docs/api/f010-resource-detail.md §2 与各资源 canonical 契约
 * （f002 / f004 / f005 / f006 / f007 / f008）构造；fetch 桩替换，不触达真实
 * 后端。沿用 tests/setup/monotonic-date-now.ts（时钟回跳会静默吞掉点击）。
 */

const SESSION_USER = { id: 1, username: 'admin' }
const TS = '2026-09-18T10:00:00Z'

const CLUSTER_A = { id: 1, name: 'cluster-a', created_at: TS, updated_at: TS }
const CLUSTER_LIST_BODY = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }

const BARE_METAL_A = {
  id: 1,
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
  created_at: TS,
  updated_at: TS,
}
const BARE_METAL_LIST_BODY = { items: [BARE_METAL_A], total: 1, page: 1, page_size: 50 }

/** 各类一条的关联聚合（契约 §2；用于从关联区进入详情）。 */
const RELATED_BODY = {
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
    ],
    total: 1,
  },
  ip_addresses: {
    items: [{ id: 21, network_interface_id: 11, ip_address: '10.0.0.5/16', created_at: TS, updated_at: TS }],
    total: 1,
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
    ],
    total: 1,
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
    ],
    total: 1,
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
    ],
    total: 1,
  },
}

/** 各子资源 canonical 详情响应（进入后由对应详情页读取）。 */
const NIC_DETAIL = RELATED_BODY.network_interfaces.items[0]!
const IP_DETAIL = RELATED_BODY.ip_addresses.items[0]!
const VM_DETAIL = RELATED_BODY.virtual_machines.items[0]!
const CONTAINER_DETAIL = RELATED_BODY.containers.items[0]!
const SERVICE_DETAIL = RELATED_BODY.services.items[0]!

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 按端点分发的 fetch 桩（覆盖登录会话、集群 / 裸金属、关联聚合与五类详情）。 */
function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/auth/session')) return jsonResponse(200, SESSION_USER)
    if (url === '/api/bare-metals/1/related') return jsonResponse(200, RELATED_BODY)
    if (url === '/api/bare-metals/1') return jsonResponse(200, BARE_METAL_A)
    if (url.includes('/api/bare-metals')) return jsonResponse(200, BARE_METAL_LIST_BODY)
    if (url === '/api/network-interfaces/11') return jsonResponse(200, NIC_DETAIL)
    if (url === '/api/ip-addresses/21') return jsonResponse(200, IP_DETAIL)
    if (url === '/api/virtual-machines/31') return jsonResponse(200, VM_DETAIL)
    if (url === '/api/containers/41') return jsonResponse(200, CONTAINER_DETAIL)
    if (url === '/api/services/51') return jsonResponse(200, SERVICE_DETAIL)
    if (/\/api\/clusters\/\d+/.test(url)) return jsonResponse(200, CLUSTER_A)
    if (url.includes('/api/clusters')) return jsonResponse(200, CLUSTER_LIST_BODY)
    return jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'not found' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mountApp() {
  return mount(App, { global: { plugins: [ElementPlus] } })
}

function findButton(wrapper: ReturnType<typeof mountApp>, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text() === text)
  expect(button, `期望找到文本为「${text}」的按钮`).toBeDefined()
  return button!
}

/**
 * vi.waitFor 包装：全量并行负载下页面挂载 / 异步完成偶发超过 vi.waitFor
 * 默认 1s（与既有 spec 相同），仅放宽时序上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/**
 * 等待按钮渲染且未禁用后再点击（monotonic-date-now setup 头注中的历史
 * MEDIUM：宿主机时钟回跳会使 Vue invoker 去重静默吞掉点击；与既有
 * submitWhenEnabled helper 同一 rationale）。
 */
async function clickWhenEnabled(
  wrapper: ReturnType<typeof mountApp>,
  selector: string,
): Promise<void> {
  const target = wrapper.find(selector)
  expect(target.exists(), `期望存在「${selector}」`).toBe(true)
  await waitForUi(() => {
    expect(target.attributes('disabled')).toBeUndefined()
  })
  await target.trigger('click')
}

/** 导航到裸金属详情（集群列表 → 集群详情 → 该集群裸金属列表 → 裸金属详情）。 */
async function gotoBareMetalDetail(wrapper: ReturnType<typeof mountApp>): Promise<void> {
  await waitForUi(() => {
    expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
  })
  await findButton(wrapper, '详情').trigger('click')
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
  await findButton(wrapper, '详情').trigger('click')
  await waitForUi(() => {
    expect(wrapper.text()).toContain('裸金属详情')
  })
  // 关联区内容就绪（五类均非空）。
  await waitForUi(() => {
    expect(wrapper.find('[data-related="services"]').find('.list-states').attributes('data-state')).toBe(
      'content',
    )
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('App 视图切换：裸金属详情「关联资源」→ 五类子资源详情（F010 / AC-17）', () => {
  it.each([
    {
      category: 'network_interfaces',
      detailUrl: '/api/network-interfaces/11',
      title: '网络接口详情',
      identity: 'eth0',
    },
    {
      category: 'ip_addresses',
      detailUrl: '/api/ip-addresses/21',
      title: 'IP 地址详情',
      identity: '10.0.0.5/16',
    },
    {
      category: 'virtual_machines',
      detailUrl: '/api/virtual-machines/31',
      title: '虚拟机详情',
      identity: 'vm-a',
    },
    {
      category: 'containers',
      detailUrl: '/api/containers/41',
      title: '容器详情',
      identity: 'c-direct',
    },
    {
      category: 'services',
      detailUrl: '/api/services/51',
      title: '服务详情',
      identity: 'svc-direct',
    },
  ])(
    '从「$category」条目进入详情（$detailUrl）→ 返回列表 → 回到裸金属详情',
    async ({ category, detailUrl, title, identity }) => {
      const fetchMock = stubFetch()
      const wrapper = mountApp()

      await gotoBareMetalDetail(wrapper)

      // 从关联条目直接进入该类详情（不经过该资源的全局列表页）。
      await clickWhenEnabled(
        wrapper,
        `[data-related="${category}"] [data-testid="related-detail"]`,
      )
      await waitForUi(() => {
        expect(wrapper.text()).toContain(title)
      })
      await waitForUi(() => {
        expect(wrapper.text()).toContain(identity)
      })
      expect(fetchMock).toHaveBeenCalledWith(
        detailUrl,
        expect.objectContaining({ method: 'GET' }),
      )

      // 返回列表 → 直接回到裸金属详情（保留返回上下文），关联区仍在。
      await findButton(wrapper, '返回列表').trigger('click')
      await waitForUi(() => {
        expect(wrapper.text()).toContain('裸金属详情')
      })
      await waitForUi(() => {
        expect(wrapper.text()).toContain('cn001')
      })
      expect(wrapper.find('[data-testid="related-resources"]').exists()).toBe(true)
    },
  )

  it('返回上下文完整保留：关联区进入 → 返回裸金属详情 → 返回列表仍携带 cluster_id → 返回集群详情', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await gotoBareMetalDetail(wrapper)

    // 从关联区进入网络接口详情再返回（携带 returnView）。
    await clickWhenEnabled(
      wrapper,
      '[data-related="network_interfaces"] [data-testid="related-detail"]',
    )
    await waitForUi(() => {
      expect(wrapper.text()).toContain('网络接口详情')
    })
    await findButton(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('裸金属详情')
    })

    // 裸金属详情返回列表：仍携带 cluster_id 过滤上下文（进入时从集群详情保留）。
    await findButton(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('裸金属列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/bare-metals?page=1&page_size=50&cluster_id=1',
        expect.objectContaining({ method: 'GET' }),
      )
    })

    // 过滤列表返回 → 回到集群详情。
    await findButton(wrapper, '返回集群详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('cluster-a')
    })
  })
})
