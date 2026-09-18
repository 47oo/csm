import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPagination, ElPopconfirm, ElSelect } from 'element-plus'
import BareMetalListPage from '../src/pages/BareMetalListPage.vue'
import BareMetalFormDialog from '../src/components/BareMetalFormDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * 裸金属列表页测试（T-FE-01 / AC-30）。
 *
 * 覆盖：三态互不相同、Empty（200 + items == []）与 Not Found（父 Cluster 404）
 * 可区分（R-QUERY-004）、错误按 error.code 分支（不解析 message）、按 Cluster
 * 过滤（cluster_id）、行级详情 / 删除入口（二次确认 / 204 刷新 / 409 / 404 / 401 /
 * 防重复）、登记表单入口（POST body 构造 / 409 DUPLICATE / 404 / 401 / 防重复）
 * 与「前端不重复实现业务守卫」（§21：重复 hostname 仍提交由服务端裁决、
 * 删除入口不预判、空 hostname 不做未定义约束分支）。
 *
 * 响应体严格按 docs/api/f002-bare-metal.md 构造（§2 资源表示 / §3.2 列表 /
 * §3.1 登记 / §3.5 删除 / §4 错误信封 / §9 Empty 与 Not Found）。
 */

const BARE_METAL_A = {
  id: 1,
  cluster_id: 3,
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
const BARE_METAL_B = {
  ...BARE_METAL_A,
  id: 2,
  hostname: 'cn002',
  status: 'DOWN',
  updated_at: '2026-09-16T11:30:00Z',
}

const LIST_BODY = { items: [BARE_METAL_A, BARE_METAL_B], total: 2, page: 1, page_size: 50 }
/** Empty 语义（契约 §9）：200 + items == [] + total == 0，不是 404。 */
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }

/** 登记表单所需集群选项（GET /api/clusters，f001 契约 §3.2 信封）。 */
const CLUSTER_LIST_BODY = {
  items: [{ id: 3, name: 'cluster-a', created_at: '2026-09-15T10:00:00Z', updated_at: '2026-09-15T10:00:00Z' }],
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

function noContent(): Response {
  return new Response(null, { status: 204 })
}

function mountPage(props: { clusterId?: number | null } = {}) {
  return mount(BareMetalListPage, {
    props,
    global: { plugins: [ElementPlus] },
  })
}

/**
 * vi.waitFor 包装：全量并行负载下 el-dialog 挂载 / 异步完成偶发超过
 * vi.waitFor 默认 1s（单文件运行稳定）。随测试文件数增长，已先后放宽到
 * 5s、10s；仅放宽超时上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('BareMetalListPage 三态互不相同（AC-30）', () => {
  it('请求进行中 → Loading 态（骨架屏），不渲染 Empty / Error / 表格', async () => {
    let resolveList!: (body: unknown) => void
    const listPromise = new Promise<Response>((res) => {
      resolveList = (body: unknown) => res(jsonResponse(200, body))
    })
    vi.stubGlobal('fetch', vi.fn(async () => listPromise))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('loading')
    })
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)

    resolveList(EMPTY_LIST_BODY)
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
  })

  it('200 + items 为空（无过滤）→ Empty 态「暂无裸金属」，不渲染骨架屏 / Error / 表格', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无裸金属')
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)
  })

  it('500 INTERNAL_ERROR → Error 态，按 error.code 渲染（不解析 message）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, INTERNAL_ERROR_BODY)))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(alert.text()).toContain('服务器内部错误')
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无裸金属')
  })

  it('携带 clusterId 请求 → 查询参数含 cluster_id（契约 §3.2）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage({ clusterId: 3 })

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals?page=1&page_size=50&cluster_id=3',
      expect.objectContaining({ method: 'GET' }),
    )
    // 过滤上下文可见：标题下展示集群过滤标签，返回按钮指向集群详情。
    expect(wrapper.text()).toContain('集群 #3')
    expect(wrapper.text()).toContain('返回集群详情')
    // Cluster 存在但无活跃 BareMetal → Empty 文案按过滤场景区分。
    expect(wrapper.text()).toContain('该集群暂无裸金属')
  })
})

describe('R-QUERY-004：Empty 与 Not Found 可区分（AC-30 / AC-15）', () => {
  it('父 Cluster 存在但无活跃裸金属（200 空）与父 Cluster 不存在 / 已删（404）渲染不同状态与文案', async () => {
    // Empty：200 + items == []（契约 §9）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))
    const emptyWrapper = mountPage({ clusterId: 3 })
    await waitForUi(() => {
      expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    // Not Found：GET /api/bare-metals?cluster_id=999 → 404 NOT_FOUND（契约 §3.2）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))
    const notFoundWrapper = mountPage({ clusterId: 999 })
    await waitForUi(() => {
      expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })

    // 不同的状态标记。
    expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')

    // 不同的文案：Empty 是「该集群暂无裸金属」；Not Found 按 error.code 渲染「未找到资源」。
    expect(emptyWrapper.text()).toContain('该集群暂无裸金属')
    expect(emptyWrapper.find('[role="alert"]').exists()).toBe(false)
    const alert = notFoundWrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(notFoundWrapper.text()).not.toContain('暂无裸金属')
  })
})

describe('BareMetalListPage 内容与分页', () => {
  it('成功 → 表格展示 id / 集群 ID / hostname / 状态 / 更新时间（契约原样值）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    const rows = wrapper.findAll('.el-table__row')
    expect(rows[0].text()).toContain('cn001')
    expect(rows[0].text()).toContain('2026-09-16T10:00:00Z')
    expect(rows[1].text()).toContain('cn002')
    // 状态以标签渲染契约原始值（R-BM-003 封闭集合，不改写）。
    const statusTags = wrapper.findAll('[data-status]')
    expect(statusTags.map((tag) => tag.attributes('data-status'))).toEqual(['IDLE', 'DOWN'])
  })

  it('分页器绑定契约信封值；翻页 → 以新 page 重新请求 /api/bare-metals', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [BARE_METAL_A], total: 120, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    const pager = wrapper.findComponent(ElPagination)
    expect(pager.props('total')).toBe(120)
    expect(pager.props('currentPage')).toBe(1)

    pager.vm.$emit('current-change', 3)
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/bare-metals?page=3&page_size=50',
        expect.anything(),
      )
    })
  })

  it('点击「详情」→ emit openDetail(bareMetalId)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()
    await waitForUi(() => {
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

/** 契约 §4.1：message 不构成契约；使用与展示无关的文案，证明前端分支与渲染均不解析 message。 */
const DELETE_CONFLICT_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的后端冲突文案',
    details: [
      { row: null, field: null, code: 'ACTIVE_CHILDREN_EXIST', message: '与展示无关的子项文案' },
    ],
  },
}
const DELETE_UNAUTHENTICATED_BODY = { error: { code: 'UNAUTHENTICATED', message: '未认证' } }
const DELETE_NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }

/** DELETE /api/bare-metals/{id} 的调用次数。 */
function deleteCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
  ).length
}

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

async function mountListWithRows(): Promise<VueWrapper> {
  const wrapper = mountPage()
  await waitForUi(() => {
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })
  return wrapper
}

function findRowDeleteButton(wrapper: VueWrapper, rowIndex: number) {
  const button = wrapper
    .findAll('.el-table__row')[rowIndex]
    .findAll('button')
    .find((b) => b.text().includes('删除'))
  expect(button).toBeDefined()
  return button!
}

function confirmRowDelete(wrapper: VueWrapper, rowIndex: number): void {
  wrapper.findAllComponents(ElPopconfirm)[rowIndex]!.vm.$emit('confirm', new MouseEvent('click'))
}

describe('BareMetalListPage 删除入口（T-FE-01 / AC-18）', () => {
  it('每行均有「删除」入口（ElPopconfirm 二次确认），空闲时全部可触发（前端不做业务预判，§21）', async () => {
    stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => noContent(),
    })

    const wrapper = await mountListWithRows()

    expect(wrapper.findAllComponents(ElPopconfirm)).toHaveLength(2)
    for (const row of wrapper.findAll('.el-table__row')) {
      const deleteButton = row.findAll('button').find((b) => b.text().includes('删除'))
      expect(deleteButton).toBeDefined()
      // 删除守卫由后端裁决：前端不禁用、不隐藏任何行的删除入口。
      expect(deleteButton!.attributes('disabled')).toBeUndefined()
    }
  })

  it('未通过二次确认（仅点击删除按钮 / 确认框取消）→ 不发送 DELETE 请求', async () => {
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => noContent(),
    })

    const wrapper = await mountListWithRows()

    await findRowDeleteButton(wrapper, 0).trigger('click')
    expect(deleteCalls(fetchMock)).toBe(0)

    wrapper.findAllComponents(ElPopconfirm)[0]!.vm.$emit('cancel', new MouseEvent('click'))
    expect(deleteCalls(fetchMock)).toBe(0)
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })

  it('二次确认通过 → DELETE /api/bare-metals/{id}（不发送请求体，契约 §3.5）', async () => {
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, LIST_BODY),
      remove: () => noContent(),
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(deleteCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/bare-metals/1',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
  })

  it('删除成功（204）→ 刷新列表，被删行消失', async () => {
    const activeList = { items: [BARE_METAL_A, BARE_METAL_B], total: 2, page: 1, page_size: 50 }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [BARE_METAL_B]
        activeList.total = 1
        return noContent()
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.findAll('.el-table__row')[0].text()).toContain('cn002')
    const getCalls = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method !== 'DELETE',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('删除成功且当前页变空 → Empty 态，不渲染表格 / 删除失败提示', async () => {
    const activeList = { items: [BARE_METAL_A], total: 1, page: 1, page_size: 50 }
    stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = []
        activeList.total = 0
        return noContent()
      },
    })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
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

    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const alert = wrapper.find('[data-delete-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法删除裸金属')
    expect(alert.text()).toContain('活跃子资源')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
  })

  it('404 NOT_FOUND（已不存在或已被逻辑删除）→ 与成功同构：刷新列表，不渲染删除失败提示', async () => {
    const activeList = { items: [BARE_METAL_A, BARE_METAL_B], total: 2, page: 1, page_size: 50 }
    stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [BARE_METAL_B]
        activeList.total = 1
        return jsonResponse(404, DELETE_NOT_FOUND_BODY)
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.find('[data-state]').attributes('data-state')).toBe('content')
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
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

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
    })
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })

  it('提交中：删除按钮 Loading / 其余行禁用，重复确认不产生第二个 DELETE（禁止重复提交）', async () => {
    let releaseDelete!: () => void
    const deleteGate = new Promise<void>((resolve) => {
      releaseDelete = resolve
    })
    const activeList = { items: [BARE_METAL_A, BARE_METAL_B], total: 2, page: 1, page_size: 50 }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: async () => {
        await deleteGate
        activeList.items = [BARE_METAL_B]
        activeList.total = 1
        return noContent()
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)
    await waitForUi(() => {
      expect(deleteCalls(fetchMock)).toBe(1)
    })

    await waitForUi(() => {
      expect(findRowDeleteButton(wrapper, 0).classes()).toContain('is-loading')
    })
    expect(findRowDeleteButton(wrapper, 1).attributes('disabled')).toBeDefined()

    confirmRowDelete(wrapper, 0)
    confirmRowDelete(wrapper, 1)
    expect(deleteCalls(fetchMock)).toBe(1)

    releaseDelete()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
  })
})

// ---- 登记表单入口（POST /api/bare-metals，契约 §3.1） ----

/** 契约 §4.1：message 不构成契约；使用与展示无关的文案。 */
const CREATE_DUPLICATE_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的重复文案',
    details: [{ field: 'hostname', code: 'DUPLICATE', message: '与展示无关的字段文案' }],
  },
}
const CREATE_CLUSTER_NOT_FOUND_BODY = {
  error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' },
}
const CREATE_VALIDATION_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '与展示无关的校验文案',
    details: [{ field: 'hostname', message: '与展示无关的字段提示' }],
  },
}

/** 按端点 / 方法分发的 fetch 桩（登记对话框会额外请求 GET /api/clusters）。 */
function stubCreateFetch(routes: {
  list: () => Response
  clusters?: () => Response
  create?: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'DELETE') return noContent()
    if (init?.method === 'POST') return routes.create?.() ?? noContent()
    if (url.includes('/api/clusters')) return (routes.clusters ?? (() => jsonResponse(200, CLUSTER_LIST_BODY)))()
    return routes.list()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** 打开登记对话框并等待表单渲染就绪（el-dialog 内容首开才挂载）。 */
async function openCreateDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-testid="open-create-dialog"]').trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="bare-metal-form-submit"]').exists()).toBe(true)
  })
}

/** 登记对话框的开闭状态（el-dialog 关闭后 DOM 仍在，以 modelValue 判定）。 */
function createDialogOpen(wrapper: VueWrapper): boolean {
  return wrapper.findComponent(BareMetalFormDialog).props('modelValue') === true
}

/**
 * 对话框内的所属集群下拉（el-select）。
 *
 * 注意不能用 findComponent(ElSelect) 直接取第一个：ElPagination 内部也渲染
 * ElSelect（page-size 选择器）；用根元素 class 精确定位对话框内那个。
 */
function findClusterSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('bare-metal-form__cluster-select'))
  expect(select, '期望找到所属集群下拉').toBeDefined()
  return select!
}

/** 选择所属集群（el-select 以 update:modelValue 驱动表单状态）。 */
async function selectCluster(wrapper: VueWrapper, clusterId: number): Promise<void> {
  await findClusterSelect(wrapper).vm.$emit('update:modelValue', clusterId)
}

/** POST /api/bare-metals 的调用次数。 */
function createCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
  ).length
}

describe('BareMetalListPage 登记入口（T-FE-01 / AC-01~08，§21 不预判）', () => {
  it('打开登记对话框 → 加载集群选项（GET /api/clusters，父存在性由服务端裁决）', async () => {
    const fetchMock = stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = await mountListWithRows()

    expect(wrapper.find('[data-testid="bare-metal-form-submit"]').exists()).toBe(false)
    await openCreateDialog(wrapper)

    expect(wrapper.text()).toContain('登记裸金属')
    await waitForUi(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/clusters'))).toBe(
        true,
      )
    })
  })

  it('未选择所属集群（表单未完成）→ 提交按钮禁用；这不属于父存在性预判（§21）', async () => {
    stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    const submit = wrapper.find('[data-testid="bare-metal-form-submit"]')
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('填表提交 → POST /api/bare-metals；硬件字段输入为空提交 null（契约 §3.1）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(201, BARE_METAL_A),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    // 选择所属集群（el-select 以 update:modelValue 驱动表单状态）。
    await selectCluster(wrapper, 3)
    await wrapper.find('[data-testid="bare-metal-form-hostname"]').setValue('cn001')
    await wrapper.find('[data-testid="bare-metal-form-gpu"]').setValue('4 x A100 80G')

    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/bare-metals',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          cluster_id: 3,
          hostname: 'cn001',
          vendor: null,
          model: null,
          serial_number: null,
          cpu: null,
          memory: null,
          gpu: '4 x A100 80G',
          storage: null,
        }),
      }),
    )
  })

  it('空 hostname 仍提交（契约 §7 未定义约束：前端不得基于空串编写业务分支）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectCluster(wrapper, 3)
    // hostname 留空：前端不拦截（是否拒绝空串由服务端裁决，当前契约不承诺）。
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      )![1] as RequestInit).body as string,
    )
    expect(body.hostname).toBe('')
  })

  it('登记成功（201）→ 关闭对话框并刷新列表', async () => {
    const activeList = { items: [BARE_METAL_B], total: 1, page: 1, page_size: 50 }
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, activeList),
      create: () => {
        activeList.items = [BARE_METAL_A, BARE_METAL_B]
        activeList.total = 2
        return jsonResponse(201, BARE_METAL_A)
      },
    })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await openCreateDialog(wrapper)
    await selectCluster(wrapper, 3)
    await wrapper.find('[data-testid="bare-metal-form-hostname"]').setValue('cn001')
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    // 对话框关闭 + 列表刷新（第二次 GET，两行）。
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    await waitForUi(() => {
      expect(createDialogOpen(wrapper)).toBe(false)
    })
    const getCalls = fetchMock.mock.calls.filter(
      (call) =>
        String(call[0]).includes('/api/bare-metals') &&
        (call[1] as RequestInit | undefined)?.method === 'GET',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('409 CONFLICT（hostname DUPLICATE）→ 前端仍提交（不预判唯一性，§21），按 error.code 渲染固定文案（不解析 message）', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(409, CREATE_DUPLICATE_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectCluster(wrapper, 3)
    // 与既有行重复的 hostname：前端不做唯一性预检，直接提交由服务端裁决。
    await wrapper.find('[data-testid="bare-metal-form-hostname"]').setValue('cn001')
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.text()).toContain('同一集群内已存在同名的 hostname')
    // 渲染文案为前端按稳定 code 生成的固定文案；后端 message 不参与渲染。
    expect(wrapper.text()).not.toContain('与展示无关的重复文案')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(createDialogOpen(wrapper)).toBe(true)
  })

  it('404 NOT_FOUND（所选集群不存在 / 已删，契约 §3.1 / NQ-2）→ 按error.code 渲染，不解析 message', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(404, CREATE_CLUSTER_NOT_FOUND_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectCluster(wrapper, 3)
    await wrapper.find('[data-testid="bare-metal-form-hostname"]').setValue('cn001')
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain('所选集群不存在或已被删除')
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
  })

  it('400 VALIDATION_ERROR → 对话框内展示字段级提示（details[].field）', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectCluster(wrapper, 3)
    await wrapper.find('[data-testid="bare-metal-form-hostname"]').setValue('cn001')
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('hostname')
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，对话框内不渲染本地失败提示', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectCluster(wrapper, 3)
    await wrapper.find('[data-testid="bare-metal-form-hostname"]').setValue('cn001')
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    })
  })

  it('提交中：提交按钮 Loading，重复点击不产生第二个 POST（禁止重复提交）', async () => {
    let releaseCreate!: () => void
    const createGate = new Promise<void>((resolve) => {
      releaseCreate = resolve
    })
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: async () => {
        await createGate
        return jsonResponse(201, BARE_METAL_A)
      },
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectCluster(wrapper, 3)
    await wrapper.find('[data-testid="bare-metal-form-hostname"]').setValue('cn001')
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="bare-metal-form-submit"]').classes()).toContain(
        'is-loading',
      )
    })

    // 连点不发出第二个 POST。
    await wrapper.find('[data-testid="bare-metal-form-submit"]').trigger('click')
    expect(createCalls(fetchMock)).toBe(1)

    releaseCreate()
    await waitForUi(() => {
      expect(createDialogOpen(wrapper)).toBe(false)
    })
  })
})
