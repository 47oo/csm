import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * App 资源视图切换测试（F008，f008-service-handoff.md Frontend Work）：
 * 头部导航的全局服务列表（无载体过滤；载体筛选为列表页内能力）→ 服务详情 →
 * 返回列表；详情页「登记服务」成功后跳转到新服务的详情。仍不引入 vue-router。
 *
 * 响应体严格按 docs/api/f008-service.md 与 f001-cluster.md / f013-auth.md
 * 构造；fetch 桩替换，不触达真实后端。
 */

const SESSION_USER = { id: 1, username: 'admin' }
const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const CLUSTER_LIST_BODY = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }
const SERVICE_A = {
  id: 7,
  name: 'mon',
  service_type: '自研',
  url: null,
  port: '8080-8090',
  protocol: '自定义协议',
  owner: 'ops',
  description: null,
  carriers: [
    { carrier_type: 'BARE_METAL', carrier_id: 3 },
    { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 5 },
    { carrier_type: 'CONTAINER', carrier_id: 11 },
  ],
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
}
const SERVICE_B = {
  ...SERVICE_A,
  id: 8,
  name: 'storage',
  service_type: null,
  url: null,
  port: null,
  protocol: null,
  owner: null,
  description: null,
  carriers: [{ carrier_type: 'BARE_METAL', carrier_id: 4 }],
}
const SERVICE_LIST_BODY = {
  items: [SERVICE_A, SERVICE_B],
  total: 2,
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
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/api/auth/session')) return jsonResponse(200, SESSION_USER)
    if (init?.method === 'POST' && url.includes('/api/services')) {
      return jsonResponse(201, SERVICE_B)
    }
    if (/\/api\/services\/8/.test(url)) return jsonResponse(200, SERVICE_B)
    if (/\/api\/services\/\d+/.test(url)) return jsonResponse(200, SERVICE_A)
    if (url.includes('/api/services')) return jsonResponse(200, SERVICE_LIST_BODY)
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
 * vi.waitFor 默认 1s（单文件运行稳定）。仅放宽超时上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

afterEach(() => {
  vi.unstubAllGlobals()
  // App 挂载时会注册全局未认证处理器，卸载后清除，保证测试隔离。
  setUnauthenticatedHandler(null)
})

describe('App 头部导航：全局服务列表（无载体过滤）', () => {
  it('点击「服务」→ 列表请求不带 carrier_type / carrier_id；返回按钮回集群列表', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    // 头部导航进入全局服务列表（契约 §4.2：未提供载体对 → 全部活跃）。
    await findButton(wrapper, '服务').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('服务列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/services?page=1&page_size=50',
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

  it('导航高亮随资源区域切换（service 区域下「服务」高亮）', async () => {
    stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '服务').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('服务列表')
    })
    const navService = wrapper.find('[data-testid="nav-services"]')
    expect(navService.classes()).toContain('app-shell__nav-item--active')

    // 切回集群区域：高亮恢复。
    await findButton(wrapper, '集群').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群列表')
    })
    expect(wrapper.find('[data-testid="nav-services"]').classes()).not.toContain(
      'app-shell__nav-item--active',
    )
    expect(wrapper.find('[data-testid="nav-clusters"]').classes()).toContain('app-shell__nav-item--active')
  })
})

describe('App 视图切换：服务列表 → 服务详情 → 返回', () => {
  it('服务列表行「详情」→ 服务详情（GET /api/services/{id}）→「返回列表」→ 服务列表', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '服务').trigger('click')
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    // 进入第一行（Service #7）的详情。
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('服务详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('mon')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/services/7', expect.anything())
    })
    // 载体绑定在详情中全量展示。
    await waitForUi(() => {
      expect(wrapper.findAll('[data-testid="service-carrier"]')).toHaveLength(3)
    })

    // 返回列表：重新请求全局服务列表。
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('服务列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/services?page=1&page_size=50',
        expect.objectContaining({ method: 'GET' }),
      )
    })
  })
})

describe('App 视图切换：服务详情登记成功 → 跳转新服务详情', () => {
  it('详情页「登记服务」→ POST 成功（201）→ 进入新服务（#8）的详情', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '服务').trigger('click')
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('mon')
    })

    // 详情页登记入口：对话框预选当前服务的 3 条载体，填写 name 后提交。
    await findButton(wrapper, '登记服务').trigger('click')
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="service-form-submit"]').exists()).toBe(true)
    })
    await waitForUi(() => {
      expect(
        wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
      ).toBeUndefined()
    })
    await wrapper.find('[data-testid="service-form-name"]').setValue('storage')
    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    // POST /api/services 成功 → 视图切换到新服务 #8 的详情并读取。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('storage')
    })
    await waitForUi(() => {
      expect(wrapper.findAll('[data-testid="service-carrier"]')).toHaveLength(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/services',
      expect.objectContaining({ method: 'POST' }),
    )
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/services/8', expect.anything())
    })
  })
})
