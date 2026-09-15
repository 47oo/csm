import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * App 会话流测试（T-18 / T-19，AC-05）：
 * - 启动期 getCurrentSession 探测（已登录直接进入 / 未登录到登录页）；
 * - 全局 401（未抑制请求收到 UNAUTHENTICATED）→ 切回登录页且不渲染任何资源数据；
 * - 登出（204 与 401 归一为同一处理，f013-auth.md §5.2）；
 * - 会话失效后重新登录 → 资源数据重新请求，不显示旧数据。
 * 响应体严格按 docs/api/f013-auth.md 与 docs/api/f001-cluster.md 构造。
 */

const SESSION_USER = { id: 1, username: 'admin' }
const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const LIST_BODY = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }
const UNAUTHENTICATED_BODY = {
  error: { code: 'UNAUTHENTICATED', message: '未认证', details: [] },
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function noContent(): Response {
  return new Response(null, { status: 204 })
}

function notFound(): Response {
  return jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'not found' } })
}

/** 按端点分发的可变 fetch 桩：各路由的响应函数可在测试中途替换（模拟会话失效）。 */
function stubFetch(routes: {
  session?: () => Response
  login?: () => Response
  logout?: () => Response
  clusters?: () => Response
  clusterDetail?: () => Response
}) {
  const mutable = { ...routes }
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/auth/session')) return (mutable.session ?? notFound)()
    if (url.includes('/api/auth/login')) return (mutable.login ?? notFound)()
    if (url.includes('/api/auth/logout')) return (mutable.logout ?? noContent)()
    if (/\/api\/clusters\/\d+/.test(url)) return (mutable.clusterDetail ?? notFound)()
    if (url.includes('/api/clusters')) return (mutable.clusters ?? notFound)()
    return notFound()
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, routes: mutable }
}

function mountApp() {
  return mount(App, { global: { plugins: [ElementPlus] } })
}

function viewOf(wrapper: ReturnType<typeof mountApp>): string {
  const view = wrapper.find('[data-view]').attributes('data-view')
  expect(view).toBeDefined()
  return view!
}

function findButton(wrapper: ReturnType<typeof mountApp>, text: string) {
  const button = wrapper.findAll('button').find((b) => b.text().includes(text))
  expect(button, `期望找到「${text}」按钮`).toBeDefined()
  return button!
}

afterEach(() => {
  vi.unstubAllGlobals()
  // App 挂载时会注册全局未认证处理器，卸载后清除，保证测试隔离。
  setUnauthenticatedHandler(null)
})

describe('启动会话探测（T-18）', () => {
  it('已有会话 → 跳过登录页直接进入 app 视图', async () => {
    const { fetchMock } = stubFetch({
      session: () => jsonResponse(200, SESSION_USER),
      clusters: () => jsonResponse(200, LIST_BODY),
    })

    const wrapper = mountApp()
    // 挂载后先处于 bootstrap（会话探测进行中）。
    expect(viewOf(wrapper)).toBe('bootstrap')

    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('app')
    })
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/session',
      expect.objectContaining({ method: 'GET' }),
    )
    // 未出现登录表单；头部展示当前身份。
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('admin')
  })

  it('无会话（401）→ 登录页；启动期只探测会话，不发起资源请求', async () => {
    const { fetchMock } = stubFetch({
      session: () => jsonResponse(401, UNAUTHENTICATED_BODY),
    })

    const wrapper = mountApp()

    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('login')
    })
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/session',
      expect.objectContaining({ method: 'GET' }),
    )
  })
})

describe('登录流程：未登录启动 → 失败停留 → 成功进入（T-17 / T-18 集成）', () => {
  it('登录失败（401）停留登录页并提示；登录成功进入系统', async () => {
    const { routes } = stubFetch({
      session: () => jsonResponse(401, UNAUTHENTICATED_BODY),
      login: () => jsonResponse(401, UNAUTHENTICATED_BODY),
      clusters: () => jsonResponse(200, LIST_BODY),
    })

    const wrapper = mountApp()
    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('login')
    })

    // 第一次登录：凭据错误 → 401 → 停留登录页 + 固定失败提示（不触发全局跳转）。
    await wrapper.find('input[autocomplete="username"]').setValue('admin')
    await wrapper.find('input[autocomplete="current-password"]').setValue('wrong')
    await wrapper.find('form').trigger('submit')

    await vi.waitFor(() => {
      expect(wrapper.find('[data-error-code="UNAUTHENTICATED"]').exists()).toBe(true)
    })
    expect(viewOf(wrapper)).toBe('login')
    expect(wrapper.text()).toContain('用户名或口令不正确')

    // 第二次登录：成功 → 进入系统，列表加载。
    routes.login = () => jsonResponse(200, SESSION_USER)
    await wrapper.find('input[autocomplete="current-password"]').setValue('correct horse')
    await wrapper.find('form').trigger('submit')

    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('app')
    })
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
  })
})

describe('全局 401：会话失效切回登录页（T-18 / AC-05）', () => {
  it('app 内资源请求返回 401 UNAUTHENTICATED → 切回登录页，不渲染任何资源数据', async () => {
    const { routes } = stubFetch({
      session: () => jsonResponse(200, SESSION_USER),
      clusters: () => jsonResponse(200, LIST_BODY),
    })

    const wrapper = mountApp()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.text()).toContain('cluster-a')

    // 会话过期：下一次资源请求返回 401（登录 / 会话探测之外的一切请求均不抑制跳转）。
    routes.clusters = () => jsonResponse(401, UNAUTHENTICATED_BODY)
    await findButton(wrapper, '刷新').trigger('click')

    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('login')
    })
    // 不渲染任何资源数据：表格、行、页面标题、旧身份均消失。
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.findAll('.el-table__row')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('cluster-a')
    expect(wrapper.text()).not.toContain('集群列表')
    expect(wrapper.text()).not.toContain('admin')
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
  })
})

describe('登出（T-19 / AC-05）', () => {
  it('登出成功（204）→ 切回登录页，资源数据不保留', async () => {
    const { fetchMock } = stubFetch({
      session: () => jsonResponse(200, SESSION_USER),
      clusters: () => jsonResponse(200, LIST_BODY),
      logout: () => noContent(),
    })

    const wrapper = mountApp()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '登出').trigger('click')

    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('login')
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/logout',
      expect.objectContaining({ method: 'POST', body: undefined }),
    )
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('cluster-a')
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
  })

  it('登出返回 401（会话已失效）→ 与 204 归一：同样切回登录页（契约 §5.2 幂等语义）', async () => {
    stubFetch({
      session: () => jsonResponse(200, SESSION_USER),
      clusters: () => jsonResponse(200, LIST_BODY),
      logout: () => jsonResponse(401, UNAUTHENTICATED_BODY),
    })

    const wrapper = mountApp()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await findButton(wrapper, '登出').trigger('click')

    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('login')
    })
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('cluster-a')
  })
})

describe('会话失效后重新登录（T-19）', () => {
  it('401 被切回登录页后重新登录 → 回到列表视图并重新请求，不显示旧数据', async () => {
    const { fetchMock, routes } = stubFetch({
      session: () => jsonResponse(200, SESSION_USER),
      clusters: () => jsonResponse(200, LIST_BODY),
    })

    const wrapper = mountApp()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    // 会话失效 → 登录页。
    routes.clusters = () => jsonResponse(401, UNAUTHENTICATED_BODY)
    await findButton(wrapper, '刷新').trigger('click')
    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('login')
    })

    // 重新登录（另一身份）：列表重新请求，展示新会话身份与数据。
    routes.login = () => jsonResponse(200, { id: 2, username: 'ops' })
    routes.clusters = () => jsonResponse(200, LIST_BODY)
    await wrapper.find('input[autocomplete="username"]').setValue('ops')
    await wrapper.find('input[autocomplete="current-password"]').setValue('correct horse')
    await wrapper.find('form').trigger('submit')

    await vi.waitFor(() => {
      expect(viewOf(wrapper)).toBe('app')
    })
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.text()).toContain('ops')
    // 列表在重新登录后再次请求（重新挂载触发，而非沿用旧数据）。
    const clusterCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes('/api/clusters'),
    )
    expect(clusterCalls.length).toBeGreaterThanOrEqual(2)
  })
})
