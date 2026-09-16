import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPagination, ElPopconfirm } from 'element-plus'
import ClusterListPage from '../src/pages/ClusterListPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * 集群列表页三态测试（AC-14 / A16）。
 *
 * F012 判据 6（前端三态基座）的验证力自 F001 起由本产品页承载：
 * 整链路 组件 → useAsyncQuery → apiRequest（fetch 桩）→ 契约响应
 * → ListStates / ErrorState 渲染。响应体严格按 docs/api/f001-cluster.md
 * 构造（列表信封 §3.2 / Empty 语义 §9 / 错误信封 §5）。
 *
 * F014 起另覆盖删除入口（T-FE-01）：入口 / 二次确认 / 成功刷新 / 409 / 404 /
 * 401 / 提交中防重复，响应体严格按 docs/api/f014-soft-delete.md 构造。
 */

const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const CLUSTER_B = {
  id: 2,
  name: 'Cluster-A',
  created_at: '2026-09-15T11:00:00Z',
  updated_at: '2026-09-15T11:30:00Z',
}

const LIST_BODY = { items: [CLUSTER_A, CLUSTER_B], total: 2, page: 1, page_size: 50 }
/** Empty 语义（契约 §9）：200 + items == [] + total == 0，不是 404。 */
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }
/** 契约 §3.2：page < 1 → 400 VALIDATION_ERROR，details[].field == "page"。 */
const PAGE_VALIDATION_ERROR_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '请求校验失败',
    details: [{ field: 'page', message: 'page 必须大于等于 1' }],
  },
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mountPage() {
  return mount(ClusterListPage, {
    global: { plugins: [ElementPlus] },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  // 401 用例注册的全局未认证处理器在用例后清除，保证隔离。
  setUnauthenticatedHandler(null)
})

describe('ClusterListPage 三态互不相同（AC-14）', () => {
  it('请求进行中 → Loading 态（骨架屏），不渲染 Empty / Error / 表格', async () => {
    // 用可控的 deferred 让请求保持进行中，使 Loading 态可确定性观察。
    let resolveList!: (body: unknown) => void
    const listPromise = new Promise<Response>((res) => {
      resolveList = (body: unknown) => res(jsonResponse(200, body))
    })
    vi.stubGlobal('fetch', vi.fn(async () => listPromise))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('loading')
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)

    // 让挂起的请求落地，避免测试结束后残留未决 promise。
    resolveList(EMPTY_LIST_BODY)
    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
  })

  it('200 + items 为空 → Empty 态（暂无集群），不渲染骨架屏 / Error / 表格', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无集群')
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)
  })

  it('500 INTERNAL_ERROR → Error 态，按 error.code 渲染（不解析 message）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, INTERNAL_ERROR_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(alert.text()).toContain('服务器内部错误')
    expect(alert.text()).toContain('INTERNAL_ERROR')
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无集群')
  })

  it('400 VALIDATION_ERROR（details[].field == "page"）→ Error 态展示校验失败与字段提示', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(400, PAGE_VALIDATION_ERROR_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('VALIDATION_ERROR')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('page')
    expect(wrapper.text()).not.toContain('暂无集群')
  })
})

describe('ClusterListPage 内容与分页', () => {
  it('成功 → 表格展示 id / name / created_at / updated_at（时间为契约原样字符串）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    const rows = wrapper.findAll('.el-table__row')
    expect(rows[0].text()).toContain('cluster-a')
    expect(rows[0].text()).toContain('2026-09-15T10:00:00Z')
    expect(rows[1].text()).toContain('Cluster-A')
    expect(rows[1].text()).toContain('2026-09-15T11:30:00Z')
  })

  it('分页器绑定契约信封值：total / page / page_size', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()

    await vi.waitFor(() => {
      expect(wrapper.findComponent(ElPagination).exists()).toBe(true)
    })

    const pager = wrapper.findComponent(ElPagination)
    expect(pager.props('total')).toBe(2)
    expect(pager.props('currentPage')).toBe(1)
    expect(pager.props('pageSize')).toBe(50)
  })

  it('翻页（current-change）→ 以新 page 重新请求 /api/clusters', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [CLUSTER_A], total: 120, page: 2, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    wrapper.findComponent(ElPagination).vm.$emit('current-change', 2)

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/clusters?page=2&page_size=50',
        expect.anything(),
      )
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('调整 page_size（size-change）→ 回到第 1 页并以新 page_size 请求', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [CLUSTER_A], total: 120, page: 2, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    wrapper.findComponent(ElPagination).vm.$emit('size-change', 20)

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/clusters?page=1&page_size=20',
        expect.anything(),
      )
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('点击「详情」→ emit openDetail(clusterId)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    const detailButtons = wrapper
      .findAll('button')
      .filter((button) => button.text().includes('详情'))
    expect(detailButtons).toHaveLength(2)
    await detailButtons[0].trigger('click')

    expect(wrapper.emitted('openDetail')).toEqual([[1]])
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
const DELETE_UNAUTHENTICATED_BODY = { error: { code: 'UNAUTHENTICATED', message: '未认证' } }

function noContent(): Response {
  return new Response(null, { status: 204 })
}

/** DELETE /api/clusters/{id} 的调用次数。 */
function deleteCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
  ).length
}

/** 按方法分发的 fetch 桩：DELETE → remove()；其余（GET 列表）→ list()。 */
function stubListFetch(routes: {
  list: () => Response
  remove: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'DELETE') return routes.remove()
    return routes.list()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** 挂载并等待两行数据就绪（内容态）。 */
async function mountListWithRows(): Promise<VueWrapper> {
  const wrapper = mountPage()
  await vi.waitFor(() => {
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })
  return wrapper
}

/** 取某行内的「删除」按钮。 */
function findRowDeleteButton(wrapper: VueWrapper, rowIndex: number) {
  const button = wrapper
    .findAll('.el-table__row')[rowIndex]
    .findAll('button')
    .find((b) => b.text().includes('删除'))
  expect(button).toBeDefined()
  return button!
}

/** 在某行的 ElPopconfirm 上触发「确认」（携带 MouseEvent 以通过 emits 校验器）。 */
function confirmRowDelete(wrapper: VueWrapper, rowIndex: number): void {
  wrapper.findAllComponents(ElPopconfirm)[rowIndex]!.vm.$emit('confirm', new MouseEvent('click'))
}

describe('ClusterListPage 删除入口（F014，T-FE-01 / AC-10）', () => {
  it('每行均有「删除」入口（ElPopconfirm 二次确认），空闲时全部可触发（前端不做业务预判，§21）', async () => {
    stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => noContent(),
    })

    const wrapper = await mountListWithRows()

    expect(wrapper.findAllComponents(ElPopconfirm)).toHaveLength(2)
    for (const row of wrapper.findAll('.el-table__row')) {
      const deleteButton = row
        .findAll('button')
        .find((b) => b.text().includes('删除'))
      expect(deleteButton).toBeDefined()
      // 删除守卫（活跃子资源）由后端裁决：前端不禁用、不隐藏任何行的删除入口。
      expect(deleteButton!.attributes('disabled')).toBeUndefined()
    }
  })

  it('未通过二次确认（仅点击删除按钮 / 确认框取消）→ 不发送 DELETE 请求', async () => {
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => noContent(),
    })

    const wrapper = await mountListWithRows()

    // 点击行内删除按钮仅打开确认气泡，不直接发出请求。
    await findRowDeleteButton(wrapper, 0).trigger('click')
    expect(deleteCalls(fetchMock)).toBe(0)

    // 在确认框中选择取消 → 同样不发请求，行保留。
    wrapper.findAllComponents(ElPopconfirm)[0]!.vm.$emit('cancel', new MouseEvent('click'))
    expect(deleteCalls(fetchMock)).toBe(0)
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })

  it('二次确认通过 → DELETE /api/clusters/{id}（不发送请求体，契约 f014 §3.1）', async () => {
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => noContent(),
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await vi.waitFor(() => {
      expect(deleteCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/clusters/1',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
  })

  it('删除成功（204）→ 刷新列表，被删行消失', async () => {
    const activeList = { items: [CLUSTER_A, CLUSTER_B], total: 2, page: 1, page_size: 50 }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [CLUSTER_B]
        activeList.total = 1
        return noContent()
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.findAll('.el-table__row')[0]!.text()).toContain('Cluster-A')
    // 删除后发生了列表刷新（第二次 GET）。
    const getCalls = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method !== 'DELETE',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('删除成功且当前页变空 → Empty 态（暂无集群），不渲染表格 / 删除失败提示', async () => {
    const activeList = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }
    stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = []
        activeList.total = 0
        return noContent()
      },
    })

    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    confirmRowDelete(wrapper, 0)

    await vi.waitFor(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.text()).toContain('暂无集群')
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
  })

  it('409 CONFLICT（ACTIVE_CHILDREN_EXIST）→ 保留行、不刷新列表，按 error.code 渲染冲突提示（不解析 message）', async () => {
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => jsonResponse(409, DELETE_CONFLICT_BODY),
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await vi.waitFor(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })
    // 行保留（未因失败消失），且未触发列表刷新（仍只有首次 GET + 一次 DELETE）。
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    // 渲染文案为前端按稳定 code 生成的固定文案；后端 message 不参与渲染。
    const alert = wrapper.find('[data-delete-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法删除集群')
    expect(alert.text()).toContain('活跃子资源')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
  })

  it('409 冲突提示可手动关闭（关闭后提示消失，列表数据不动）', async () => {
    stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => jsonResponse(409, DELETE_CONFLICT_BODY),
    })

    const wrapper = await mountListWithRows()
    confirmRowDelete(wrapper, 0)
    await vi.waitFor(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })

    await wrapper.find('.el-alert__close-btn').trigger('click')

    await vi.waitFor(() => {
      expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
    })
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })

  it('404 NOT_FOUND（已不存在或已被逻辑删除）→ 刷新列表，不渲染删除失败提示 / 未知错误', async () => {
    const activeList = { items: [CLUSTER_A, CLUSTER_B], total: 2, page: 1, page_size: 50 }
    stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [CLUSTER_B]
        activeList.total = 1
        return jsonResponse(404, DELETE_NOT_FOUND_BODY)
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    // 404 与成功同构：刷新列表，行消失，无任何错误渲染。
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.find('[data-state]').attributes('data-state')).toBe('content')
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，本页不渲染删除失败提示', async () => {
    stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => jsonResponse(401, DELETE_UNAUTHENTICATED_BODY),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await vi.waitFor(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    // 401 不产生删除失败提示（会话失效由 App 全局处理切回登录页）；行保留。
    await vi.waitFor(() => {
      expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
    })
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })

  it('提交中：删除按钮 Loading / 其余行禁用，重复确认不产生第二个 DELETE（禁止重复提交）', async () => {
    let releaseDelete!: () => void
    const deleteGate = new Promise<void>((resolve) => {
      releaseDelete = resolve
    })
    const activeList = { items: [CLUSTER_A, CLUSTER_B], total: 2, page: 1, page_size: 50 }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: async () => {
        await deleteGate
        activeList.items = [CLUSTER_B]
        activeList.total = 1
        return noContent()
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)
    await vi.waitFor(() => {
      expect(deleteCalls(fetchMock)).toBe(1)
    })

    // 提交中：目标行按钮 Loading，其余行删除入口禁用。
    await vi.waitFor(() => {
      expect(findRowDeleteButton(wrapper, 0).classes()).toContain('is-loading')
    })
    expect(findRowDeleteButton(wrapper, 1).attributes('disabled')).toBeDefined()

    // 二次确认连点（同行 + 其他行）不发出第二个 DELETE。
    confirmRowDelete(wrapper, 0)
    confirmRowDelete(wrapper, 1)
    expect(deleteCalls(fetchMock)).toBe(1)

    // 请求落地（204）→ 刷新列表，被删行消失。
    releaseDelete()
    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
  })
})
