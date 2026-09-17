import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * App 资源视图切换测试（F007，f007-container-handoff.md Frontend Work）：
 * 头部导航的全局容器列表（无载体过滤；载体筛选为列表页内能力）→ 容器详情 →
 * 返回列表；详情页「登记容器」成功后跳转到新容器的详情。仍不引入 vue-router。
 *
 * 响应体严格按 docs/api/f007-container.md 与 f001-cluster.md / f013-auth.md
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
const CONTAINER_A = {
  id: 11,
  carrier_type: 'BARE_METAL',
  carrier_id: 3,
  name: 'web',
  image: 'registry/nginx:1.25',
  cpu: '8 vCPU',
  memory: '4G',
  owner: 'ops',
  created_at: '2026-09-18T10:00:00Z',
  updated_at: '2026-09-18T10:00:00Z',
}
const CONTAINER_B = {
  ...CONTAINER_A,
  id: 12,
  carrier_type: 'VIRTUAL_MACHINE',
  carrier_id: 7,
  name: 'redis',
}
const CONTAINER_LIST_BODY = {
  items: [CONTAINER_A, CONTAINER_B],
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
    if (init?.method === 'POST' && url.includes('/api/containers')) {
      return jsonResponse(201, CONTAINER_B)
    }
    if (/\/api\/containers\/12/.test(url)) return jsonResponse(200, CONTAINER_B)
    if (/\/api\/containers\/\d+/.test(url)) return jsonResponse(200, CONTAINER_A)
    if (url.includes('/api/containers')) return jsonResponse(200, CONTAINER_LIST_BODY)
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

describe('App 头部导航：全局容器列表（无载体过滤）', () => {
  it('点击「容器」→ 列表请求不带 carrier_type / carrier_id；返回按钮回集群列表', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    // 头部导航进入全局容器列表（契约 §4.2：未提供载体对 → 全部活跃）。
    await findButton(wrapper, '容器').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('容器列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/containers?page=1&page_size=50',
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

  it('导航高亮随资源区域切换（container 区域下「容器」高亮）', async () => {
    stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '容器').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('容器列表')
    })
    const navContainer = wrapper.find('[data-testid="nav-containers"]')
    expect(navContainer.classes()).toContain('el-button--primary')

    // 切回集群区域：高亮恢复。
    await findButton(wrapper, '集群').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群列表')
    })
    expect(wrapper.find('[data-testid="nav-containers"]').classes()).not.toContain(
      'el-button--primary',
    )
    expect(wrapper.find('[data-testid="nav-clusters"]').classes()).toContain('el-button--primary')
  })
})

describe('App 视图切换：容器列表 → 容器详情 → 返回', () => {
  it('容器列表行「详情」→ 容器详情（GET /api/containers/{id}）→「返回列表」→ 容器列表', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '容器').trigger('click')
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    // 进入第一行（Container #11）的详情。
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('容器详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('web')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/containers/11', expect.anything())
    })

    // 返回列表：重新请求全局容器列表。
    await findButtonExact(wrapper, '返回列表').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('容器列表')
    })
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/containers?page=1&page_size=50',
        expect.objectContaining({ method: 'GET' }),
      )
    })
  })
})

describe('App 视图切换：容器详情登记成功 → 跳转新容器详情', () => {
  it('详情页「登记容器」→ POST 成功（201）→ 进入新容器（#12）的详情', async () => {
    const fetchMock = stubFetch()
    const wrapper = mountApp()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '容器').trigger('click')
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    await findButtonExact(wrapper, '详情').trigger('click')
    await waitForUi(() => {
      expect(wrapper.text()).toContain('web')
    })

    // 详情页登记入口：对话框预选当前载体（BARE_METAL #3），填写 name 后提交。
    await findButton(wrapper, '登记容器').trigger('click')
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="container-form-submit"]').exists()).toBe(true)
    })
    await waitForUi(() => {
      expect(
        wrapper.find('[data-testid="container-form-submit"]').attributes('disabled'),
      ).toBeUndefined()
    })
    await wrapper.find('[data-testid="container-form-name"]').setValue('redis')
    await wrapper.find('[data-testid="container-form-submit"]').trigger('click')

    // POST /api/containers 成功 → 视图切换到新容器 #12 的详情并读取。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('redis')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('VIRTUAL_MACHINE')
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/containers',
      expect.objectContaining({ method: 'POST' }),
    )
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/containers/12', expect.anything())
    })
  })
})
