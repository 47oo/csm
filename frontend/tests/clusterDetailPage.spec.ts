import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPopconfirm } from 'element-plus'
import ClusterDetailPage from '../src/pages/ClusterDetailPage.vue'
import ClusterListPage from '../src/pages/ClusterListPage.vue'

/**
 * vi.waitFor 包装：全量并行负载下页面挂载 / el-dialog 挂载 / 异步完成偶发超过
 * vi.waitFor 默认 1s（单文件运行稳定）。随测试文件数增长，已先后放宽到
 * 5s、10s；仅放宽超时上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/**
 * 集群详情页（骨架）测试。
 *
 * - 仅呈现 Cluster 自身字段（契约 §2 封闭集合）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty 渲染不同文本与不同状态（AC-14 / A16）；
 * - 响应体严格按 docs/api/f001-cluster.md 构造；fetch 桩替换，不触达真实后端；
 * - F014 起另覆盖删除入口（T-FE-01）：入口 / 成功进入独立 Not Found 态 /
 *   409 / 404 / 提交中防重复，响应体严格按 docs/api/f014-soft-delete.md 构造。
 */

const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mountDetailPage(clusterId = 1) {
  return mount(ClusterDetailPage, {
    props: { clusterId },
    global: { plugins: [ElementPlus] },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ClusterDetailPage 状态渲染', () => {
  it('请求进行中 → Loading 态（骨架屏）', async () => {
    let resolveDetail!: (body: unknown) => void
    const detailPromise = new Promise<Response>((res) => {
      resolveDetail = (body: unknown) => res(jsonResponse(200, body))
    })
    vi.stubGlobal('fetch', vi.fn(async () => detailPromise))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('loading')
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    resolveDetail(CLUSTER_A)
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })
  })

  it('成功 → 仅呈现 Cluster 自身 4 个字段（原样值），无裸金属数据 / 跨资源内容', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, CLUSTER_A)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('集群详情')
    expect(text).toContain('cluster-a')
    // 时间为 RFC 3339 不透明字符串，原样展示（契约 §2）。
    expect(text).toContain('2026-09-15T10:00:00Z')
    // 详情页边界：不呈现裸金属数据（Cluster 视角成员列表属 F009）、跨资源视图
    // （F010）、deleted_at / 状态 / 位置字段（契约 §2）。
    // F002 起「查看裸金属」为导航入口（f002-bare-metal-handoff.md Frontend Work #4，
    // 跳转该集群裸金属列表），不属数据呈现，见下方 F002 用例。
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(text).not.toContain('deleted_at')
    expect(text).not.toContain('状态')
  })

  it('404 NOT_FOUND → 独立的「资源不存在或已被删除」态，不渲染 Empty 文案', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))

    const wrapper = mountDetailPage(999)

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(alert.text()).toContain('资源不存在，或已被删除')
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无集群')
  })

  it('500 INTERNAL_ERROR → Error 态按 error.code 渲染', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, INTERNAL_ERROR_BODY)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(alert.text()).toContain('服务器内部错误')
  })

  it('点击「返回列表」→ emit back', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, CLUSTER_A)))

    const wrapper = mountDetailPage()
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const backButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('返回列表'))
    expect(backButton).toBeDefined()
    await backButton!.trigger('click')

    expect(wrapper.emitted('back')).toHaveLength(1)
  })

  it('F002：内容态存在「查看裸金属」入口 → emit openBareMetals(clusterId)（携带 cluster_id）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, CLUSTER_A)))

    const wrapper = mountDetailPage(7)
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const bareMetalsButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('查看裸金属'))
    expect(bareMetalsButton).toBeDefined()
    await bareMetalsButton!.trigger('click')

    expect(wrapper.emitted('openBareMetals')).toEqual([[7]])
  })
})

describe('A16：详情 404 态与列表 Empty 态可区分（R-QUERY-004）', () => {
  it('两者渲染不同的状态标记与不同的文案', async () => {
    // 列表 Empty：200 + items 为空（契约 §9）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))
    const listWrapper = mount(ClusterListPage, {
      global: { plugins: [ElementPlus] },
    })
    await waitForUi(() => {
      expect(listWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    // 详情 404：GET /api/clusters/{id} → 404 NOT_FOUND。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))
    const detailWrapper = mountDetailPage(999)
    await waitForUi(() => {
      expect(detailWrapper.attributes('data-state')).toBe('not-found')
    })

    // 不同的状态标记。
    expect(listWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    expect(detailWrapper.attributes('data-state')).toBe('not-found')

    // 不同的文案：Empty 是「暂无集群」，Not Found 是「资源不存在或已被删除」。
    expect(listWrapper.text()).toContain('暂无集群')
    expect(listWrapper.text()).not.toContain('已被删除')
    expect(detailWrapper.text()).toContain('已被删除')
    expect(detailWrapper.text()).not.toContain('暂无集群')
  })
})

/** f014-soft-delete.md §4.1：message 不构成契约；使用与展示无关的文案，
 * 证明前端分支与渲染均不解析 message。 */
const DELETE_CONFLICT_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的后端冲突文案',
    details: [
      { row: null, field: null, code: 'ACTIVE_CHILDREN_EXIST', message: '与展示无关的子项文案' },
    ],
  },
}
const DELETE_NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }

function noContent(): Response {
  return new Response(null, { status: 204 })
}

/** 按方法分发的 fetch 桩：DELETE → remove()；其余（GET 详情）→ detail()。 */
function stubDetailFetch(routes: {
  detail: () => Response
  remove: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'DELETE') return routes.remove()
    return routes.detail()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** 挂载并等待内容态就绪。 */
async function mountDetailContent(): Promise<VueWrapper> {
  const wrapper = mountDetailPage()
  await waitForUi(() => {
    expect(wrapper.attributes('data-state')).toBe('content')
  })
  return wrapper
}

/** 在删除入口的 ElPopconfirm 上触发「确认」。 */
function confirmDelete(wrapper: VueWrapper): void {
  wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))
}

describe('ClusterDetailPage 删除入口（F014，T-FE-01 / AC-10）', () => {
  it('内容态存在「删除集群」入口（ElPopconfirm 二次确认），空闲时可触发', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, CLUSTER_A),
      remove: () => noContent(),
    })

    const wrapper = await mountDetailContent()

    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
    const deleteButton = wrapper
      .findAll('button')
      .find((b) => b.text().includes('删除集群'))
    expect(deleteButton).toBeDefined()
    // 删除守卫（活跃子资源）由后端裁决（§21）：前端不预判，不禁用入口。
    expect(deleteButton!.attributes('disabled')).toBeUndefined()
  })

  it('Not Found 态（404 读取）不渲染删除入口', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))

    const wrapper = mountDetailPage(999)

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(false)
  })

  it('未通过二次确认（确认框取消）→ 不发送 DELETE 请求', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, CLUSTER_A),
      remove: () => noContent(),
    })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('cancel', new MouseEvent('click'))

    // 仍只有初始 GET，未发出 DELETE，停留内容态。
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.attributes('data-state')).toBe('content')
  })

  it('删除成功（204）→ 重新读取得到 404 → 进入既有独立 Not Found 态（不显示为普通错误或空白）', async () => {
    const mutable = { detail: () => jsonResponse(200, CLUSTER_A) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      remove: () => {
        // 删除后重新读取：服务端按契约对已删资源返回 404（R-DELETE-002 读取侧后果）。
        mutable.detail = () => jsonResponse(404, NOT_FOUND_BODY)
        return noContent()
      },
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    // 独立 Not Found 态：ErrorState 渲染 NOT_FOUND 分支，详情内容不再呈现。
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('资源不存在，或已被删除')
    expect(wrapper.find('.el-descriptions').exists()).toBe(false)
    // 成功路径不渲染删除失败提示。
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
    // 请求序列：初始 GET → DELETE → 重新读取 GET（404）。
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/clusters/1')
  })

  it('409 CONFLICT（ACTIVE_CHILDREN_EXIST）→ 保留详情内容并按 error.code 渲染冲突提示（不解析 message）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, CLUSTER_A),
      remove: () => jsonResponse(409, DELETE_CONFLICT_BODY),
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })
    // 详情内容保留（删除守卫由后端裁决，失败后资源仍存在且可查看），仍处内容态。
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.text()).toContain('cluster-a')
    const alert = wrapper.find('[data-delete-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法删除集群')
    expect(alert.text()).toContain('活跃子资源')
    // 渲染文案为前端按稳定 code 生成的固定文案；后端 message 不参与渲染。
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
    // 失败后可重试：删除入口仍在。
    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
  })

  it('删除返回 404（已被其他操作删除）→ 同样进入独立 Not Found 态，不渲染删除失败提示', async () => {
    const mutable = { detail: () => jsonResponse(200, CLUSTER_A) }
    stubDetailFetch({
      detail: () => mutable.detail(),
      remove: () => {
        // 404 后重新读取：服务端按契约对已删资源返回 404。
        mutable.detail = () => jsonResponse(404, NOT_FOUND_BODY)
        return jsonResponse(404, DELETE_NOT_FOUND_BODY)
      },
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
  })

  it('提交中：删除按钮 Loading，重复确认不产生第二个 DELETE（禁止重复提交）', async () => {
    let releaseDelete!: () => void
    const deleteGate = new Promise<void>((resolve) => {
      releaseDelete = resolve
    })
    const mutable = { detail: () => jsonResponse(200, CLUSTER_A) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      remove: async () => {
        await deleteGate
        // 请求落地（204）后重新读取：服务端按契约对已删资源返回 404。
        mutable.detail = () => jsonResponse(404, NOT_FOUND_BODY)
        return noContent()
      },
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.filter(
          (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
        ),
      ).toHaveLength(1)
    })

    // 提交中：删除按钮 Loading（el-button loading 隐含禁用）。
    await waitForUi(() => {
      const deleteButton = wrapper
        .findAll('button')
        .find((b) => b.text().includes('删除集群'))
      expect(deleteButton!.classes()).toContain('is-loading')
    })

    // 连点确认不发出第二个 DELETE。
    confirmDelete(wrapper)
    expect(
      fetchMock.mock.calls.filter(
        (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
      ),
    ).toHaveLength(1)

    // 请求落地（204）→ 重新读取 404 → 独立 Not Found 态。
    releaseDelete()
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
  })
})
