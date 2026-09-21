import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPagination, ElPopconfirm, ElSelect } from 'element-plus'
import IpAddressRangeListPage from '../src/pages/IpAddressRangeListPage.vue'
import IpAddressRangeFormDialog from '../src/components/IpAddressRangeFormDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * IP 地址范围段列表页测试（F020）。
 *
 * 覆盖：三态互不相同、Empty（200 + items == []）与 Not Found（所筛选 Cluster
 * 404）可区分（R-QUERY-004）、挂载单请求（集群选项懒加载）、错误按 error.code
 * 分支（不解析 message）、按集群筛选（?cluster_id=）、字段封闭（无状态列 /
 * 无 name 列，Q-002=B / 契约 §2）、行级详情 / 删除入口（二次确认 / 204 刷新 /
 * 409 ACTIVE_CHILDREN_EXIST / 409 OVERLAP / 404 / 401 / 防重复）、登记表单
 * 入口（POST body 构造 / 404 / 400 / 409 OVERLAP / 401 / 防重复 / §21 不
 * 预判：非法 IPv4 / start>end / 与既有行重叠取值仍提交）。
 *
 * 响应体严格按 docs/api/f020-ip-address-range.md 构造（§2 资源表示 / §3.2
 * 列表 / §3.1 登记 / §3.5 删除 / §4 错误信封 / §9 Empty 与 Not Found）；
 * 集群选项响应按 docs/api/f001-cluster.md §3.2 构造。
 */

const IP_ADDRESS_RANGE_A = {
  id: 7,
  cluster_id: 3,
  start_ip: '10.0.0.1',
  end_ip: '10.0.0.255',
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
}
const IP_ADDRESS_RANGE_B = {
  ...IP_ADDRESS_RANGE_A,
  id: 8,
  cluster_id: 4,
  start_ip: '192.168.1.1',
  end_ip: '192.168.1.254',
  updated_at: '2026-09-20T11:30:00Z',
}

const LIST_BODY = {
  items: [IP_ADDRESS_RANGE_A, IP_ADDRESS_RANGE_B],
  total: 2,
  page: 1,
  page_size: 50,
}
/** Empty 语义（契约 §9）：200 + items == [] + total == 0，不是 404。 */
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }

/** 集群选项响应（GET /api/clusters，f001 契约 §3.2 信封）。 */
const CLUSTER_LIST_BODY = {
  items: [
    { id: 3, name: 'cluster-a', created_at: '2026-09-15T10:00:00Z', updated_at: '2026-09-15T10:00:00Z' },
    { id: 4, name: 'cluster-b', created_at: '2026-09-15T11:00:00Z', updated_at: '2026-09-15T11:00:00Z' },
  ],
  total: 2,
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

function mountPage() {
  return mount(IpAddressRangeListPage, {
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

/** 按端点 / 方法分发的 fetch 桩。 */
function stubFetch(routes: {
  list?: (url: string) => Response
  clusters?: () => Response
  create?: () => Response | Promise<Response>
  remove?: (url: string) => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'POST') return routes.create?.() ?? jsonResponse(201, IP_ADDRESS_RANGE_A)
    if (init?.method === 'DELETE') return routes.remove?.(url) ?? noContent()
    if (init?.method === 'GET' && url.includes('/api/clusters')) {
      return (routes.clusters ?? (() => jsonResponse(200, CLUSTER_LIST_BODY)))()
    }
    return routes.list?.(url) ?? jsonResponse(200, LIST_BODY)
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

/** 列表页的集群筛选下拉（el-select，按 class 定位；分页器内部亦有 ElSelect）。 */
function findFilterSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('range-list__filter-cluster'))
  expect(select, '期望找到集群筛选下拉').toBeDefined()
  return select!
}

describe('IpAddressRangeListPage 三态互不相同与挂载单请求', () => {
  it('挂载 → 恰一次 GET /api/ip-address-ranges（集群选项懒加载，不随挂载请求）', async () => {
    const fetchMock = stubFetch({})

    await mountListWithRows()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges?page=1&page_size=50',
      expect.objectContaining({ method: 'GET' }),
    )
  })

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

  it('200 + items 为空（未筛选）→ Empty 态「暂无 IP 地址范围段」，不渲染骨架屏 / Error / 表格', async () => {
    stubFetch({ list: () => jsonResponse(200, EMPTY_LIST_BODY) })

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无 IP 地址范围段')
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.el-table').exists()).toBe(false)
  })

  it('500 INTERNAL_ERROR → Error 态，按 error.code 渲染（不解析 message）', async () => {
    stubFetch({ list: () => jsonResponse(500, INTERNAL_ERROR_BODY) })

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
    expect(wrapper.text()).not.toContain('暂无 IP 地址范围段')
  })
})

describe('R-QUERY-004：Empty 与 Not Found 可区分（集群筛选，契约 §3.2 / §9）', () => {
  /** 展开筛选下拉（懒加载选项）→ 选择集群 → 点击「筛选」。 */
  async function applyClusterFilter(wrapper: VueWrapper, clusterId: number): Promise<void> {
    const filterSelect = findFilterSelect(wrapper)
    filterSelect.vm.$emit('visible-change', true)
    await waitForUi(() => {
      expect(filterSelect.props('loading')).toBe(false)
    })
    await filterSelect.vm.$emit('update:modelValue', clusterId)
    await wrapper.find('[data-testid="range-filter-apply"]').trigger('click')
  }

  it('所筛选 Cluster 存在但无活跃范围段（200 空）与 Cluster 不存在 / 已删（404）渲染不同状态与文案', async () => {
    // Empty：GET /api/ip-address-ranges?cluster_id=3 → 200 + items == []（契约 §9）。
    stubFetch({ list: () => jsonResponse(200, EMPTY_LIST_BODY) })
    const emptyWrapper = mountPage()
    await applyClusterFilter(emptyWrapper, 3)
    await waitForUi(() => {
      expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    // Not Found：GET /api/ip-address-ranges?cluster_id=999 → 404 NOT_FOUND（契约 §3.2）。
    stubFetch({ list: () => jsonResponse(404, NOT_FOUND_BODY) })
    const notFoundWrapper = mountPage()
    await applyClusterFilter(notFoundWrapper, 999)
    await waitForUi(() => {
      expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })

    // 不同的状态标记。
    expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')

    // 不同的文案：Empty 是「该集群暂无 IP 地址范围段」；Not Found 按 error.code
    // 渲染「未找到资源」。
    expect(emptyWrapper.text()).toContain('该集群暂无 IP 地址范围段')
    expect(emptyWrapper.find('[role="alert"]').exists()).toBe(false)
    const alert = notFoundWrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(notFoundWrapper.text()).not.toContain('暂无 IP 地址范围段')
    expect(notFoundWrapper.find('.el-empty').exists()).toBe(false)
    // 请求确实携带了 cluster_id（由服务端裁决 404，前端不预判）。
    expect(notFoundWrapper.attributes('data-cluster-filter')).toBe('999')
  })

  it('所筛选 Cluster 存在但无活跃范围段 → Empty 态「该集群暂无 IP 地址范围段」+ 过滤标签', async () => {
    stubFetch({ list: () => jsonResponse(200, EMPTY_LIST_BODY) })

    const wrapper = mountPage()
    await applyClusterFilter(wrapper, 3)
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('该集群暂无 IP 地址范围段')
    // 过滤上下文可见：标题下展示集群过滤标签。
    expect(wrapper.text()).toContain('集群 #3')
    expect(wrapper.attributes('data-cluster-filter')).toBe('3')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})

describe('IpAddressRangeListPage 集群筛选（页内能力，契约 §3.2 ?cluster_id=）', () => {
  it('首次展开下拉 → 懒加载集群选项（GET /api/clusters）；挂载阶段不请求', async () => {
    const fetchMock = stubFetch({})

    const wrapper = await mountListWithRows()

    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/clusters'))).toBe(false)

    findFilterSelect(wrapper).vm.$emit('visible-change', true)
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes('/api/clusters')),
      ).toBe(true)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/clusters?page=1&page_size=200',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('选择集群并应用 → 列表请求携带 cluster_id（契约 §3.2）；重置 → 回到全局列表', async () => {
    const fetchMock = stubFetch({})

    const wrapper = await mountListWithRows()

    const filterSelect = findFilterSelect(wrapper)
    filterSelect.vm.$emit('visible-change', true)
    await filterSelect.vm.$emit('update:modelValue', 3)
    // 未选择集群时筛选按钮禁用；选择后可应用。
    expect(wrapper.find('[data-testid="range-filter-apply"]').attributes('disabled')).toBeUndefined()
    await wrapper.find('[data-testid="range-filter-apply"]').trigger('click')

    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/ip-address-ranges?page=1&page_size=50&cluster_id=3',
        expect.objectContaining({ method: 'GET' }),
      )
    })

    await wrapper.find('[data-testid="range-filter-clear"]').trigger('click')
    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/ip-address-ranges?page=1&page_size=50',
        expect.objectContaining({ method: 'GET' }),
      )
    })
    expect(wrapper.attributes('data-cluster-filter')).toBe('none')
  })

  it('未选择集群时「筛选」按钮禁用（表单未完成；已选值直接提交，非存在性预判）', async () => {
    stubFetch({})

    const wrapper = await mountListWithRows()

    expect(wrapper.find('[data-testid="range-filter-apply"]').attributes('disabled')).toBeDefined()
  })

  it('集群选项加载失败 → 展示错误码与重试入口；重试成功后恢复', async () => {
    let clustersFail = true
    const fetchMock = stubFetch({
      clusters: () =>
        clustersFail
          ? jsonResponse(500, INTERNAL_ERROR_BODY)
          : jsonResponse(200, CLUSTER_LIST_BODY),
    })

    const wrapper = await mountListWithRows()

    findFilterSelect(wrapper).vm.$emit('visible-change', true)
    await waitForUi(() => {
      expect(wrapper.find('.range-list__filter-hint').exists()).toBe(true)
    })
    expect(wrapper.find('.range-list__filter-hint').text()).toContain('INTERNAL_ERROR')

    clustersFail = false
    await wrapper.find('.range-list__filter-hint').find('button').trigger('click')
    await waitForUi(() => {
      expect(wrapper.find('.range-list__filter-hint').exists()).toBe(false)
    })
    // 重试成功后选项可用。
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/clusters')).length).toBe(2)
  })
})

describe('IpAddressRangeListPage 内容 / 字段封闭与分页', () => {
  it('成功 → 表格展示 id / 所属集群 ID / start_ip – end_ip / 更新时间（契约原样值）；无状态列 / 无 name 列（Q-002=B / 契约 §2）', async () => {
    stubFetch({})

    const wrapper = await mountListWithRows()

    const rows = wrapper.findAll('.el-table__row')
    expect(rows[0].text()).toContain('10.0.0.1 – 10.0.0.255')
    expect(rows[0].text()).toContain('3')
    expect(rows[0].text()).toContain('2026-09-20T10:00:00Z')
    expect(rows[1].text()).toContain('192.168.1.1 – 192.168.1.254')
    expect(rows[1].text()).toContain('4')
    // 无状态（Q-002=B）：不渲染状态标签 / 状态列。
    expect(wrapper.find('[data-status]').exists()).toBe(false)
    expect(wrapper.find('.el-table__header').text()).not.toContain('状态')
    // 无 name / description 列（契约 §2 字段封闭）。
    expect(wrapper.find('.el-table__header').text()).not.toContain('名称')
    expect(wrapper.find('.el-table__header').text()).not.toContain('name')
    // 不暴露 deleted_at（契约 §2：字段集合封闭）。
    expect(wrapper.find('.el-table__header').text()).not.toContain('deleted_at')
  })

  it('分页器绑定契约信封值；翻页 → 以新 page 重新请求 /api/ip-address-ranges', async () => {
    const fetchMock = stubFetch({
      list: () => jsonResponse(200, { items: [IP_ADDRESS_RANGE_A], total: 120, page: 1, page_size: 50 }),
    })

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
        '/api/ip-address-ranges?page=3&page_size=50',
        expect.anything(),
      )
    })
  })

  it('点击「详情」→ emit openDetail(ipAddressRangeId)', async () => {
    stubFetch({})

    const wrapper = await mountListWithRows()

    const detailButtons = wrapper
      .findAll('button')
      .filter((button) => button.text().includes('详情'))
    expect(detailButtons).toHaveLength(2)
    await detailButtons[0].trigger('click')

    expect(wrapper.emitted('openDetail')).toEqual([[7]])
  })

  it('点击「返回集群列表」→ emit back', async () => {
    stubFetch({})

    const wrapper = await mountListWithRows()

    const backButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('返回集群列表'))
    expect(backButton).toBeDefined()
    await backButton!.trigger('click')

    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})

/** 契约 §4：message 不构成契约；使用与展示无关的文案，证明前端分支与渲染均不解析 message。 */
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

/** DELETE /api/ip-address-ranges/{id} 的调用次数。 */
function deleteCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
  ).length
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

describe('IpAddressRangeListPage 删除入口（契约 §3.5）', () => {
  it('每行均有「删除」入口（ElPopconfirm 二次确认），空闲时全部可触发（前端不做业务预判，§21）', async () => {
    stubFetch({})

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
    const fetchMock = stubFetch({})

    const wrapper = await mountListWithRows()

    await findRowDeleteButton(wrapper, 0).trigger('click')
    expect(deleteCalls(fetchMock)).toBe(0)

    wrapper.findAllComponents(ElPopconfirm)[0]!.vm.$emit('cancel', new MouseEvent('click'))
    expect(deleteCalls(fetchMock)).toBe(0)
    expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
  })

  it('二次确认通过 → DELETE /api/ip-address-ranges/{id}（不发送请求体，契约 §3.5）', async () => {
    const fetchMock = stubFetch({})

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(deleteCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/ip-address-ranges/7',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
  })

  it('删除成功（204）→ 刷新列表，被删行消失', async () => {
    const activeList = {
      items: [IP_ADDRESS_RANGE_A, IP_ADDRESS_RANGE_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    const fetchMock = stubFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [IP_ADDRESS_RANGE_B]
        activeList.total = 1
        return noContent()
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.findAll('.el-table__row')[0].text()).toContain('192.168.1.1')
    const getCalls = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method !== 'DELETE',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('删除成功且当前页变空 → Empty 态，不渲染表格 / 删除失败提示', async () => {
    const activeList = { items: [IP_ADDRESS_RANGE_A], total: 1, page: 1, page_size: 50 }
    stubFetch({
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

  it('409 CONFLICT + ACTIVE_CHILDREN_EXIST → 保留行、不刷新列表，渲染「范围内仍有活跃 IP」（不解析 message）', async () => {
    const fetchMock = stubFetch({
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
    expect(alert.text()).toContain('无法删除IP 地址范围段')
    expect(alert.text()).toContain('该范围内仍有活跃 IP，无法删除')
    expect(alert.text()).toContain('请先软删范围内的活跃 IP')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
    expect(wrapper.text()).not.toContain('与展示无关的子项文案')
  })

  it('404 NOT_FOUND（已不存在或已被逻辑删除）→ 与成功同构：刷新列表，不渲染删除失败提示', async () => {
    const activeList = {
      items: [IP_ADDRESS_RANGE_A, IP_ADDRESS_RANGE_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    stubFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [IP_ADDRESS_RANGE_B]
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
    stubFetch({
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
    const activeList = {
      items: [IP_ADDRESS_RANGE_A, IP_ADDRESS_RANGE_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    const fetchMock = stubFetch({
      list: () => jsonResponse(200, activeList),
      remove: async () => {
        await deleteGate
        activeList.items = [IP_ADDRESS_RANGE_B]
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

// ---- 登记表单入口（POST /api/ip-address-ranges，契约 §3.1） ----

/** 契约 §4：message 不构成契约；使用与展示无关的文案。 */
const CREATE_CLUSTER_NOT_FOUND_BODY = {
  error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' },
}
const CREATE_VALIDATION_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '与展示无关的校验文案',
    details: [{ field: 'start_ip', code: 'INVALID', message: '与展示无关的字段提示' }],
  },
}
const CREATE_OVERLAP_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的冲突文案',
    details: [{ row: null, field: null, code: 'OVERLAP', message: '与展示无关的重叠提示' }],
  },
}

/** 打开登记对话框并等待表单渲染就绪（el-dialog 内容首开才挂载）。 */
async function openCreateDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-testid="open-create-dialog"]').trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="range-form-submit"]').exists()).toBe(true)
  })
}

/** 登记对话框的开闭状态（el-dialog 关闭后 DOM 仍在，以 modelValue 判定）。 */
function createDialogOpen(wrapper: VueWrapper): boolean {
  return wrapper.findComponent(IpAddressRangeFormDialog).props('modelValue') === true
}

/** 登记对话框内的归属集群下拉（el-select，按 class 定位）。 */
function findFormClusterSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('ip-address-range-form__cluster-select'))
  expect(select, '期望找到归属集群下拉').toBeDefined()
  return select!
}

/** 选择归属集群（el-select 以 update:modelValue 驱动表单状态）。 */
async function selectFormCluster(wrapper: VueWrapper, clusterId: number): Promise<void> {
  await findFormClusterSelect(wrapper).vm.$emit('update:modelValue', clusterId)
}

/**
 * 等待提交按钮解除 disabled（表单完成）后再点击。
 *
 * 真实用户只能点击已启用的按钮；测试同样先等 DOM 就绪再交互，
 * 避免「update:modelValue 已更新表单状态但按钮 disabled 尚未反映到
 * DOM」时点击被丢弃（VTU trigger 对 disabled 元素不分发事件）。
 */
async function submitWhenEnabled(wrapper: VueWrapper): Promise<void> {
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="range-form-submit"]').attributes('disabled')).toBeUndefined()
  })
  await wrapper.find('[data-testid="range-form-submit"]').trigger('click')
}

/** POST /api/ip-address-ranges 的调用次数。 */
function createCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
  ).length
}

describe('IpAddressRangeListPage 登记入口（契约 §3.1，§21 不预判）', () => {
  it('打开登记对话框 → 加载归属集群选项（GET /api/clusters，父存在性由服务端裁决）', async () => {
    const fetchMock = stubFetch({})

    const wrapper = await mountListWithRows()

    expect(wrapper.find('[data-testid="range-form-submit"]').exists()).toBe(false)
    await openCreateDialog(wrapper)

    expect(wrapper.text()).toContain('登记 IP 地址范围段')
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes('/api/clusters')),
      ).toBe(true)
    })
  })

  it('表单字段仅 cluster_id（下拉）/ start_ip / end_ip：无状态、name / description 输入（契约 §2 封闭）', async () => {
    stubFetch({})

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    expect(wrapper.find('[data-testid="range-form-cluster"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="range-form-start-ip"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="range-form-end-ip"]').exists()).toBe(true)
    const dialogText = wrapper.find('.el-dialog').text()
    expect(dialogText).not.toContain('状态')
    expect(dialogText).not.toContain('名称')
    expect(dialogText).not.toContain('用途')
  })

  it('归属集群未选择（表单未完成）→ 提交按钮禁用；start_ip / end_ip 为空不禁用（合法性由服务端裁决）', async () => {
    stubFetch({})

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    // 初始：归属集群未选择。
    expect(wrapper.find('[data-testid="range-form-submit"]').attributes('disabled')).toBeDefined()

    // 选择归属集群后即可提交：start_ip / end_ip 留空不禁用（是否拒绝空串 /
    // 非法 IPv4 由服务端裁决，前端不基于未定义项编写业务分支）。
    await selectFormCluster(wrapper, 3)
    expect(wrapper.find('[data-testid="range-form-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('填表提交 → POST /api/ip-address-ranges；请求体恰为三字段（契约 §3.1 schema 封闭）', async () => {
    const fetchMock = stubFetch({})

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/ip-address-ranges',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ cluster_id: 3, start_ip: '10.0.0.1', end_ip: '10.0.0.255' }),
      }),
    )
  })

  it('§21 不预判：start > end、非法 IPv4、与既有行重叠的取值均原样提交（服务端裁决）', async () => {
    const fetchMock = stubFetch({
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    // start > end：前端不预判（契约 §3.1 由服务端 400 裁决）。
    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.1.9')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.1.1')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })

    // 非法 IPv4（含 CIDR 前缀）：原样提交，不做格式校验 / 归一化。
    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.0/24')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('abc')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(2)
    })

    // 与既有行完全重叠的取值：直接提交，重叠由服务端 409 裁决。
    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(3)
    })
    const bodies = fetchMock.mock.calls
      .filter((call) => (call[1] as RequestInit | undefined)?.method === 'POST')
      .map((call) => JSON.parse((call[1] as RequestInit).body as string))
    expect(bodies).toEqual([
      { cluster_id: 3, start_ip: '10.0.1.9', end_ip: '10.0.1.1' },
      { cluster_id: 3, start_ip: '10.0.0.0/24', end_ip: 'abc' },
      { cluster_id: 3, start_ip: '10.0.0.1', end_ip: '10.0.0.255' },
    ])
  })

  it('从已筛选集群打开 → 归属集群预选为该集群（presetClusterId），可直接提交', async () => {
    stubFetch({})

    const wrapper = await mountListWithRows()

    // 应用集群筛选 → 打开登记对话框 → 预选该集群。
    const filterSelect = findFilterSelect(wrapper)
    filterSelect.vm.$emit('visible-change', true)
    await filterSelect.vm.$emit('update:modelValue', 3)
    await wrapper.find('[data-testid="range-filter-apply"]').trigger('click')
    await waitForUi(() => {
      expect(wrapper.attributes('data-cluster-filter')).toBe('3')
    })

    await openCreateDialog(wrapper)

    // 预选集群 = 表单已完成（选择仍可更改，存在性由服务端裁决）。
    expect(wrapper.find('[data-testid="range-form-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('登记成功（201）→ 关闭对话框并刷新列表', async () => {
    const activeList = { items: [IP_ADDRESS_RANGE_B], total: 1, page: 1, page_size: 50 }
    const fetchMock = stubFetch({
      list: () => jsonResponse(200, activeList),
      create: () => {
        activeList.items = [IP_ADDRESS_RANGE_A, IP_ADDRESS_RANGE_B]
        activeList.total = 2
        return jsonResponse(201, IP_ADDRESS_RANGE_A)
      },
    })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await openCreateDialog(wrapper)
    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

    // 对话框关闭 + 列表刷新（第二次 GET，两行）。
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    await waitForUi(() => {
      expect(createDialogOpen(wrapper)).toBe(false)
    })
    const getCalls = fetchMock.mock.calls.filter(
      (call) =>
        String(call[0]).includes('/api/ip-address-ranges') &&
        (call[1] as RequestInit | undefined)?.method === 'GET',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('404 NOT_FOUND（所选集群不存在 / 已删，契约 §3.1）→ 「请检查所选集群」，不解析 message', async () => {
    stubFetch({
      create: () => jsonResponse(404, CREATE_CLUSTER_NOT_FOUND_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain('请检查所选集群')
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(createDialogOpen(wrapper)).toBe(true)
  })

  it('400 VALIDATION_ERROR → 对话框内展示字段级提示（details[].field）', async () => {
    stubFetch({
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('start_ip')
  })

  it('409 CONFLICT + details[].code === OVERLAP → 「与该 Cluster 已有范围段重叠」（不解析 message）', async () => {
    stubFetch({
      create: () => jsonResponse(409, CREATE_OVERLAP_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.text()).toContain('与该 Cluster 已有范围段重叠')
    expect(wrapper.text()).not.toContain('与展示无关的冲突文案')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(createDialogOpen(wrapper)).toBe(true)
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，对话框内不渲染本地失败提示', async () => {
    stubFetch({
      create: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

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
    const fetchMock = stubFetch({
      create: async () => {
        await createGate
        return jsonResponse(201, IP_ADDRESS_RANGE_A)
      },
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectFormCluster(wrapper, 3)
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.255')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="range-form-submit"]').classes()).toContain('is-loading')
    })

    // 连点不发出第二个 POST（提交中按钮 Loading/disabled，重复点击应被丢弃）。
    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')
    expect(createCalls(fetchMock)).toBe(1)

    releaseCreate()
    await waitForUi(() => {
      expect(createDialogOpen(wrapper)).toBe(false)
    })
  })
})
