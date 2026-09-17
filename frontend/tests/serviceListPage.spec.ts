import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElInputNumber, ElPagination, ElPopconfirm, ElSelect } from 'element-plus'
import ServiceListPage from '../src/pages/ServiceListPage.vue'
import ServiceFormDialog from '../src/components/ServiceFormDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * Service 列表页测试（AC-29、AC-31、AC-32、AC-54）。
 *
 * 覆盖：三态互不相同、Empty（200 + items == []）与 Not Found（载体 404）可区分
 * （R-QUERY-004）、载体筛选（carrier_type + carrier_id 成对，契约 §4.2）、
 * 错误按 error.code 分支（不解析 message）、无状态列 / Cluster 列（Q-002=B /
 * R-SVC-004/006）、行级详情 / 删除入口（二次确认 / 204 刷新 / 409 / 404 /
 * 401 / 防重复）、登记表单入口（多载体选择：三种类型 + 载体 ID、至少一项
 * 才能提交；POST body 构造 / 409 DUPLICATE / 404 / 400 / 401 / 防重复 /
 * 不去重、不预判）与「前端不重复实现业务守卫」（§21）。
 *
 * 响应体严格按 docs/api/f008-service.md 构造（§2 资源表示 / §4.2 列表 /
 * §4.1 登记 / §4.5 删除 / §5 错误信封 / Empty 与 Not Found 语义）。
 */

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
  updated_at: '2026-09-20T11:30:00Z',
}

const LIST_BODY = {
  items: [SERVICE_A, SERVICE_B],
  total: 2,
  page: 1,
  page_size: 50,
}
/** Empty 语义（契约 §4.2）：200 + items == [] + total == 0，不是 404。 */
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }

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
  return mount(ServiceListPage, {
    global: { plugins: [ElementPlus] },
  })
}

/**
 * vi.waitFor 包装：全量并行负载下 el-dialog 挂载 / 异步完成偶发超过
 * vi.waitFor 默认 1s（单文件运行稳定）。仅放宽超时上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('ServiceListPage 三态互不相同（AC-54）', () => {
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

  it('200 + items 为空（无过滤）→ Empty 态「暂无服务」，不渲染骨架屏 / Error / 表格', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无服务')
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
    expect(wrapper.text()).not.toContain('暂无服务')
  })
})

// ---- 载体筛选（carrier_type + carrier_id 成对，契约 §4.2） ----

/** 列表页筛选区的载体类型下拉（按 class 精确定位，避开 el-pagination 内嵌 select）。 */
function findFilterTypeSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('service-list__filter-type'))
  expect(select, '期望找到载体类型下拉').toBeDefined()
  return select!
}

/** 列表页筛选区的载体 ID 输入（el-input-number，按 class 精确定位）。 */
function findFilterIdInput(wrapper: VueWrapper) {
  const input = wrapper
    .findAllComponents(ElInputNumber)
    .find((c) => c.classes().includes('service-list__filter-id'))
  expect(input, '期望找到载体 ID 输入').toBeDefined()
  return input!
}

async function applyCarrierFilter(
  wrapper: VueWrapper,
  carrierType: 'BARE_METAL' | 'VIRTUAL_MACHINE' | 'CONTAINER',
  carrierId: number,
): Promise<void> {
  await findFilterTypeSelect(wrapper).vm.$emit('update:modelValue', carrierType)
  await findFilterIdInput(wrapper).vm.$emit('update:modelValue', carrierId)
  await wrapper.find('[data-testid="service-filter-apply"]').trigger('click')
}

describe('ServiceListPage 载体筛选（契约 §4.2：carrier_type + carrier_id 成对）', () => {
  it('仅填载体类型或仅填载体 ID（筛选未完整）→「筛选」按钮禁用（成对规则，非业务预判）', async () => {
    // 场景一：仅选择载体类型（缺载体 ID）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))
    const typeOnlyWrapper = mountPage()
    await waitForUi(() => {
      expect(typeOnlyWrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    await findFilterTypeSelect(typeOnlyWrapper).vm.$emit('update:modelValue', 'BARE_METAL')
    expect(
      typeOnlyWrapper.find('[data-testid="service-filter-apply"]').attributes('disabled'),
    ).toBeDefined()

    // 场景二：仅填载体 ID（缺载体类型）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))
    const idOnlyWrapper = mountPage()
    await waitForUi(() => {
      expect(idOnlyWrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    await findFilterIdInput(idOnlyWrapper).vm.$emit('update:modelValue', 3)
    expect(
      idOnlyWrapper.find('[data-testid="service-filter-apply"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('应用筛选 → 请求成对携带 carrier_type 与 carrier_id；过滤上下文与 Empty 文案按载体区分', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.text()).toContain('暂无服务')

    await applyCarrierFilter(wrapper, 'BARE_METAL', 3)

    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/services?page=1&page_size=50&carrier_type=BARE_METAL&carrier_id=3',
        expect.objectContaining({ method: 'GET' }),
      )
    })
    // 过滤上下文可见：标题下展示载体过滤标签；Empty 文案按载体场景区分。
    expect(wrapper.text()).toContain('载体 BARE_METAL #3')
    expect(wrapper.text()).toContain('该载体暂无服务')
    expect(wrapper.attributes('data-carrier-filter')).toBe('BARE_METAL:3')
  })

  it.each(['VIRTUAL_MACHINE', 'CONTAINER'] as const)(
    '%s 载体同样成对请求（三种载体类型均成立，AC-31）',
    async (carrierType) => {
      const fetchMock = vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY))
      vi.stubGlobal('fetch', fetchMock)

      const wrapper = mountPage()
      await waitForUi(() => {
        expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
      })

      await applyCarrierFilter(wrapper, carrierType, 7)

      await waitForUi(() => {
        expect(fetchMock).toHaveBeenLastCalledWith(
          `/api/services?page=1&page_size=50&carrier_type=${carrierType}&carrier_id=7`,
          expect.objectContaining({ method: 'GET' }),
        )
      })
    },
  )

  it('「重置」→ 清除载体筛选，回到全局列表请求', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    await applyCarrierFilter(wrapper, 'BARE_METAL', 3)
    await waitForUi(() => {
      expect(wrapper.attributes('data-carrier-filter')).toBe('BARE_METAL:3')
    })

    await wrapper.find('[data-testid="service-filter-clear"]').trigger('click')

    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        '/api/services?page=1&page_size=50',
        expect.objectContaining({ method: 'GET' }),
      )
    })
    expect(wrapper.text()).toContain('暂无服务')
    expect(wrapper.text()).not.toContain('载体 BARE_METAL #3')
  })

  it('R-QUERY-004：载体存在但无活跃服务（200 空）与载体不存在 / 已删（404）渲染不同状态与文案', async () => {
    // Empty：200 + items == []（契约 §4.2）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))
    const emptyWrapper = mountPage()
    await waitForUi(() => {
      expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    await applyCarrierFilter(emptyWrapper, 'BARE_METAL', 3)
    await waitForUi(() => {
      expect(emptyWrapper.text()).toContain('该载体暂无服务')
    })
    expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')

    // Not Found：GET /api/services?carrier_type=BARE_METAL&carrier_id=999 → 404（契约 §4.2）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))
    const notFoundWrapper = mountPage()
    await waitForUi(() => {
      expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    await applyCarrierFilter(notFoundWrapper, 'BARE_METAL', 999)
    await waitForUi(() => {
      expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })

    // 不同的状态标记：Empty 是 empty；Not Found 是 error。
    expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')

    // 不同的文案：Empty 是「该载体暂无服务」；Not Found 按 error.code 渲染「未找到资源」。
    expect(emptyWrapper.find('[role="alert"]').exists()).toBe(false)
    const alert = notFoundWrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(notFoundWrapper.text()).not.toContain('该载体暂无服务')
  })
})

describe('ServiceListPage 内容与分页', () => {
  it('成功 → 表格展示 id / name / 运行载体（契约 §2 稳定顺序原样值）/ 更新时间；无状态列、无 Cluster 列（AC-20 / AC-28）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    const rows = wrapper.findAll('.el-table__row')
    expect(rows[0].text()).toContain('mon')
    expect(rows[0].text()).toContain('BARE_METAL #3')
    expect(rows[0].text()).toContain('VIRTUAL_MACHINE #5')
    expect(rows[0].text()).toContain('CONTAINER #11')
    expect(rows[0].text()).toContain('2026-09-20T10:00:00Z')
    expect(rows[1].text()).toContain('storage')
    expect(rows[1].text()).toContain('BARE_METAL #4')
    // Service 无状态（Q-002=B）：不渲染状态标签 / 状态列。
    expect(wrapper.find('[data-status]').exists()).toBe(false)
    expect(wrapper.find('.el-table__header').text()).not.toContain('状态')
    // Cluster 归属不暴露（R-SVC-004/006）：无 Cluster 列 / Cluster 字样。
    expect(wrapper.find('.el-table__header').text()).not.toContain('集群')
    expect(wrapper.text()).not.toContain('cluster_id')
  })

  it('分页器绑定契约信封值；翻页 → 以新 page 重新请求 /api/services', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [SERVICE_A], total: 120, page: 1, page_size: 50 }),
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
        '/api/services?page=3&page_size=50',
        expect.anything(),
      )
    })
  })

  it('点击「详情」→ emit openDetail(serviceId)', async () => {
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

    expect(wrapper.emitted('openDetail')).toEqual([[7]])
  })

  it('点击「返回集群列表」→ emit back', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    await wrapper.findAll('button').find((b) => b.text() === '返回集群列表')!.trigger('click')

    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})

// ---- 删除入口（DELETE /api/services/{id}，契约 §4.5） ----

/** 契约 §5：message 不构成契约；使用与展示无关的文案，证明前端分支与渲染均不解析 message。 */
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

/** DELETE /api/services/{id} 的调用次数。 */
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

describe('ServiceListPage 删除入口（契约 §4.5）', () => {
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

  it('二次确认通过 → DELETE /api/services/{id}（不发送请求体，契约 §4.5）', async () => {
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
      '/api/services/7',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
  })

  it('删除成功（204）→ 刷新列表，被删行消失', async () => {
    const activeList = {
      items: [SERVICE_A, SERVICE_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [SERVICE_B]
        activeList.total = 1
        return noContent()
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.findAll('.el-table__row')[0].text()).toContain('storage')
    const getCalls = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method !== 'DELETE',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('删除成功且当前页变空 → Empty 态，不渲染表格 / 删除失败提示', async () => {
    const activeList = { items: [SERVICE_A], total: 1, page: 1, page_size: 50 }
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

  it('非 404 失败（如 409 CONFLICT）→ 保留行、不刷新列表，按 error.code 渲染冲突提示（不解析 message）', async () => {
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
    expect(alert.text()).toContain('无法删除服务')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
  })

  it('404 NOT_FOUND（已不存在或已被逻辑删除）→ 与成功同构：刷新列表，不渲染删除失败提示', async () => {
    const activeList = {
      items: [SERVICE_A, SERVICE_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [SERVICE_B]
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
    const activeList = {
      items: [SERVICE_A, SERVICE_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: async () => {
        await deleteGate
        activeList.items = [SERVICE_B]
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

// ---- 登记入口（POST /api/services，契约 §4.1） ----

/** 契约 §5：message 不构成契约；使用与展示无关的文案。 */
const CREATE_DUPLICATE_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的重复文案',
    details: [{ field: 'name', code: 'DUPLICATE', message: '与展示无关的字段文案' }],
  },
}
const CREATE_CARRIER_NOT_FOUND_BODY = {
  error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' },
}
const CREATE_VALIDATION_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '与展示无关的校验文案',
    details: [{ field: 'carriers', code: 'DUPLICATE', message: '与展示无关的字段提示' }],
  },
}

function stubCreateFetch(routes: {
  list: () => Response
  create?: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'DELETE') return noContent()
    if (init?.method === 'POST') return routes.create?.() ?? jsonResponse(201, SERVICE_A)
    return routes.list()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** 打开登记对话框并等待表单渲染就绪（el-dialog 内容首开才挂载）。 */
async function openCreateDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-testid="open-create-dialog"]').trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="service-form-submit"]').exists()).toBe(true)
  })
}

/** 登记对话框的开闭状态（el-dialog 关闭后 DOM 仍在，以 modelValue 判定）。 */
function createDialogOpen(wrapper: VueWrapper): boolean {
  return wrapper.findComponent(ServiceFormDialog).props('modelValue') === true
}

/** 对话框内的载体类型下拉集合（按 class 精确定位；第 i 项 = 第 i 条载体行）。 */
function findFormCarrierTypeSelects(wrapper: VueWrapper) {
  const selects = wrapper
    .findAllComponents(ElSelect)
    .filter((s) => s.classes().includes('service-form__carrier-type'))
  expect(selects.length, '期望至少一条载体行').toBeGreaterThan(0)
  return selects
}

/** 对话框内的载体 ID 输入集合（按 class 精确定位；第 i 项 = 第 i 条载体行）。 */
function findFormCarrierIdInputs(wrapper: VueWrapper) {
  const inputs = wrapper
    .findAllComponents(ElInputNumber)
    .filter((c) => c.classes().includes('service-form__carrier-id'))
  expect(inputs.length, '期望至少一条载体行').toBeGreaterThan(0)
  return inputs
}

/** 填写第 index 条载体行（类型 + ID）。 */
async function fillCarrierRow(
  wrapper: VueWrapper,
  index: number,
  carrierType: 'BARE_METAL' | 'VIRTUAL_MACHINE' | 'CONTAINER',
  carrierId: number,
): Promise<void> {
  await findFormCarrierTypeSelects(wrapper)[index]!.vm.$emit('update:modelValue', carrierType)
  await findFormCarrierIdInputs(wrapper)[index]!.vm.$emit('update:modelValue', carrierId)
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
    expect(
      wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
    ).toBeUndefined()
  })
  await wrapper.find('[data-testid="service-form-submit"]').trigger('click')
}

/** POST /api/services 的调用次数。 */
function createCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
  ).length
}

describe('ServiceListPage 登记入口（契约 §4.1；多载体选择，AC-54 / §21 不预判）', () => {
  it('打开登记对话框 → 含 name、多载体选择（类型 + ID 行 + 添加 / 移除）与 6 个可选字段', async () => {
    stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = await mountListWithRows()

    expect(wrapper.find('[data-testid="service-form-submit"]').exists()).toBe(false)
    await openCreateDialog(wrapper)

    expect(wrapper.text()).toContain('登记服务')
    expect(wrapper.find('[data-testid="service-form-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="service-form-carrier-type"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="service-form-carrier-id"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="service-form-add-carrier"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="service-form-remove-carrier"]').exists()).toBe(true)
    for (const field of ['service_type', 'url', 'port', 'protocol', 'owner', 'description']) {
      expect(wrapper.find(`[data-testid="service-form-${field}"]`).exists()).toBe(true)
    }
  })

  it('载体类型下拉恰提供三种封闭值（BARE_METAL / VIRTUAL_MACHINE / CONTAINER，契约 §2）', async () => {
    stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    const select = findFormCarrierTypeSelects(wrapper)[0]!
    const options = select.findAllComponents({ name: 'ElOption' })
    expect(options).toHaveLength(3)
    const values = options.map((option) => option.props('value'))
    expect(values).toEqual(['BARE_METAL', 'VIRTUAL_MACHINE', 'CONTAINER'])
  })

  it('「至少一项载体」是唯一的表单完整性约束：无载体行或任一行未填完整 → 提交禁用；name 为空不阻止提交', async () => {
    stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    // 初始：一条空载体行（类型与 ID 均缺）→ 禁用。
    expect(
      wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
    ).toBeDefined()

    // 仅选类型 → 仍缺 ID。
    await findFormCarrierTypeSelects(wrapper)[0]!.vm.$emit('update:modelValue', 'BARE_METAL')
    expect(
      wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
    ).toBeDefined()

    // 补齐 ID → 表单完成（name 仍为空：空 name 是否合法由服务端裁决，契约 §8）。
    await findFormCarrierIdInputs(wrapper)[0]!.vm.$emit('update:modelValue', 3)
    expect(
      wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
    ).toBeUndefined()

    // 追加一条未填完整的新行 → 任一行不完整即禁用。
    await wrapper.find('[data-testid="service-form-add-carrier"]').trigger('click')
    expect(
      wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
    ).toBeDefined()

    // 移除该行（回到一条完整行）→ 重新可提交。
    await wrapper.findAll('[data-testid="service-form-remove-carrier"]')[1]!.trigger('click')
    expect(
      wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
    ).toBeUndefined()

    // 移除全部载体行 → 零载体（R-SVC-005）→ 禁用。
    await wrapper.findAll('[data-testid="service-form-remove-carrier"]')[0]!.trigger('click')
    expect(wrapper.find('[data-testid="service-form-remove-carrier"]').exists()).toBe(false)
    expect(
      wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('多载体填表提交 → POST /api/services：body 恰为 name + carriers 数组 + 6 字段（输入为空提交 null，契约 §4.1）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(201, SERVICE_A),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    await wrapper.find('[data-testid="service-form-add-carrier"]').trigger('click')
    await fillCarrierRow(wrapper, 1, 'CONTAINER', 11)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
    await wrapper.find('[data-testid="service-form-service_type"]').setValue('自研')
    await wrapper.find('[data-testid="service-form-port"]').setValue('8080-8090')

    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/services',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'mon',
          carriers: [
            { carrier_type: 'BARE_METAL', carrier_id: 3 },
            { carrier_type: 'CONTAINER', carrier_id: 11 },
          ],
          service_type: '自研',
          url: null,
          port: '8080-8090',
          protocol: null,
          owner: null,
          description: null,
        }),
      }),
    )
  })

  it('同一请求内重复给出同一载体 → 前端不去重、不预判，原样提交由服务端裁决（契约 §4.1：400 DUPLICATE）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    await wrapper.find('[data-testid="service-form-add-carrier"]').trigger('click')
    await fillCarrierRow(wrapper, 1, 'BARE_METAL', 3)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')

    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      )![1] as RequestInit).body as string,
    )
    expect(body.carriers).toEqual([
      { carrier_type: 'BARE_METAL', carrier_id: 3 },
      { carrier_type: 'BARE_METAL', carrier_id: 3 },
    ])
  })

  it('空 name 仍提交（契约 §8 未定义约束：前端不得基于空串编写业务分支）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    // name 留空：前端不拦截（是否拒绝空串由服务端裁决，当前契约不承诺）。
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      )![1] as RequestInit).body as string,
    )
    expect(body.name).toBe('')
  })

  it('从已筛选载体打开 → 预选该载体（可增删改）；请求体携带预选载体', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') return jsonResponse(201, SERVICE_A)
      return jsonResponse(200, EMPTY_LIST_BODY)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    await applyCarrierFilter(wrapper, 'BARE_METAL', 3)
    await waitForUi(() => {
      expect(wrapper.attributes('data-carrier-filter')).toBe('BARE_METAL:3')
    })

    await openCreateDialog(wrapper)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
    // 预选载体 = 筛选载体（BARE_METAL #3）→ 表单已完整。
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      )![1] as RequestInit).body as string,
    )
    expect(body.carriers).toEqual([{ carrier_type: 'BARE_METAL', carrier_id: 3 }])
  })

  it('登记成功（201）→ 关闭对话框并刷新列表', async () => {
    const activeList: { items: unknown[]; total: number; page: number; page_size: number } = {
      items: [SERVICE_B],
      total: 1,
      page: 1,
      page_size: 50,
    }
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, activeList),
      create: () => {
        activeList.items = [SERVICE_A, SERVICE_B]
        activeList.total = 2
        return jsonResponse(201, SERVICE_A)
      },
    })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await openCreateDialog(wrapper)
    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
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
        String(call[0]).includes('/api/services') &&
        (call[1] as RequestInit | undefined)?.method === 'GET',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('409 CONFLICT（name DUPLICATE）→ 前端仍提交（不预判唯一性，§21），按 error.code 渲染全局唯一固定文案（不解析 message）', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(409, CREATE_DUPLICATE_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    // 与既有行重复的 name：前端不做唯一性预检，直接提交由服务端裁决。
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    // Service 唯一性边界是全局（R-SVC-008），与 Container 的载体内唯一对照。
    expect(alert.text()).toContain('已存在活跃的同名服务')
    expect(alert.text()).toContain('全局唯一')
    // 渲染文案为前端按稳定 code 生成的固定文案；后端 message 不参与渲染。
    expect(wrapper.text()).not.toContain('与展示无关的重复文案')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(createDialogOpen(wrapper)).toBe(true)
  })

  it('404 NOT_FOUND（任一载体不存在 / 已删 / 类型不一致，契约 §4.1）→ 按 error.code 渲染，不解析 message', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(404, CREATE_CARRIER_NOT_FOUND_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await fillCarrierRow(wrapper, 0, 'VIRTUAL_MACHINE', 999)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain(
      '载体不存在或已被删除，请检查载体类型与载体 ID',
    )
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
  })

  it('400 VALIDATION_ERROR → 对话框内展示字段级提示（details[].field / code）', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('carriers')
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

    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
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
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: async () => {
        await createGate
        return jsonResponse(201, SERVICE_A)
      },
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await fillCarrierRow(wrapper, 0, 'BARE_METAL', 3)
    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="service-form-submit"]').classes()).toContain('is-loading')
    })

    // 连点不发出第二个 POST。
    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')
    expect(createCalls(fetchMock)).toBe(1)

    releaseCreate()
    await waitForUi(() => {
      expect(createDialogOpen(wrapper)).toBe(false)
    })
  })
})
