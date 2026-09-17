import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPagination, ElPopconfirm, ElSelect } from 'element-plus'
import IpAddressListPage from '../src/pages/IpAddressListPage.vue'
import IpAddressFormDialog from '../src/components/IpAddressFormDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * IP 地址列表页测试（T-41 / AC-41）。
 *
 * 覆盖：三态互不相同、Empty（200 + items == []）与 Not Found（父 NIC 404）可区分
 * （R-QUERY-004）、错误按 error.code 分支（不解析 message）、按父 NIC 过滤
 * （network_interface_id）、无状态列 / 无 Cluster 列（Q-002=B / NQ-4）、行级
 * 详情 / 删除入口（二次确认 / 204 刷新 / 409 / 404 / 401 / 防重复）、登记表单
 * 入口（POST body 构造 / 404 / 400 / 409 DUPLICATE / 401 / 防重复）与「前端不
 * 重复实现业务守卫」（§21：与既有行相同字面值仍提交由服务端裁决、空串不做
 * 未定义约束分支、删除入口不预判）。
 *
 * 响应体严格按 docs/api/f005-ip-address.md 构造（§2 资源表示 / §3.2 列表 /
 * §3.1 登记 / §3.5 删除 / §4 错误信封 / §9 Empty 与 Not Found）。
 */

const IP_ADDRESS_A = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.1.1/16',
  created_at: '2026-09-18T10:00:00Z',
  updated_at: '2026-09-18T10:00:00Z',
}
const IP_ADDRESS_B = {
  ...IP_ADDRESS_A,
  id: 42,
  ip_address: '2001:DB8::1',
  updated_at: '2026-09-18T11:30:00Z',
}

const LIST_BODY = {
  items: [IP_ADDRESS_A, IP_ADDRESS_B],
  total: 2,
  page: 1,
  page_size: 50,
}
/** Empty 语义（契约 §9）：200 + items == [] + total == 0，不是 404。 */
const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }

/** 登记表单所需父网络接口选项（GET /api/network-interfaces，f004 契约 §3.2 信封）。 */
const NIC_LIST_BODY = {
  items: [
    {
      id: 12,
      bare_metal_id: 11,
      name: 'eth0',
      technology_type: 'Ethernet',
      purpose: 'Business',
      created_at: '2026-09-17T10:00:00Z',
      updated_at: '2026-09-17T10:00:00Z',
    },
  ],
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

function mountPage(props: { networkInterfaceId?: number | null } = {}) {
  return mount(IpAddressListPage, {
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

describe('IpAddressListPage 三态互不相同（AC-41）', () => {
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

  it('200 + items 为空（无过滤）→ Empty 态「暂无 IP 地址」，不渲染骨架屏 / Error / 表格', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无 IP 地址')
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
    expect(wrapper.text()).not.toContain('暂无 IP 地址')
  })

  it('携带 networkInterfaceId 请求 → 查询参数含 network_interface_id（契约 §3.2）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage({ networkInterfaceId: 12 })

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses?page=1&page_size=50&network_interface_id=12',
      expect.objectContaining({ method: 'GET' }),
    )
    // 过滤上下文可见：标题下展示父 NIC 过滤标签，返回按钮指向网络接口详情。
    expect(wrapper.text()).toContain('网络接口 #12')
    expect(wrapper.text()).toContain('返回网络接口详情')
    // 父 NIC 存在但无活跃 IP → Empty 文案按过滤场景区分。
    expect(wrapper.text()).toContain('该网络接口暂无 IP 地址')
  })
})

describe('R-QUERY-004：Empty 与 Not Found 可区分（AC-41）', () => {
  it('父 NIC 存在但无活跃 IP（200 空）与父 NIC 不存在 / 已删（404）渲染不同状态与文案', async () => {
    // Empty：200 + items == []（契约 §9）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))
    const emptyWrapper = mountPage({ networkInterfaceId: 12 })
    await waitForUi(() => {
      expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })

    // Not Found：GET /api/ip-addresses?network_interface_id=999 → 404 NOT_FOUND（契约 §3.2）。
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))
    const notFoundWrapper = mountPage({ networkInterfaceId: 999 })
    await waitForUi(() => {
      expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })

    // 不同的状态标记。
    expect(emptyWrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    expect(notFoundWrapper.find('[data-state]').attributes('data-state')).toBe('error')

    // 不同的文案：Empty 是「该网络接口暂无 IP 地址」；Not Found 按 error.code
    // 渲染「未找到资源」。
    expect(emptyWrapper.text()).toContain('该网络接口暂无 IP 地址')
    expect(emptyWrapper.find('[role="alert"]').exists()).toBe(false)
    const alert = notFoundWrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(notFoundWrapper.text()).not.toContain('暂无 IP 地址')
  })
})

describe('IpAddressListPage 内容与分页', () => {
  it('成功 → 表格展示 id / 所属网络接口 ID / IP 地址 / 更新时间（契约原样值）；无状态列（Q-002=B）、无 Cluster 列（NQ-4）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, LIST_BODY)))

    const wrapper = mountPage()

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })

    const rows = wrapper.findAll('.el-table__row')
    expect(rows[0].text()).toContain('10.0.1.1/16')
    expect(rows[0].text()).toContain('12')
    expect(rows[0].text()).toContain('2026-09-18T10:00:00Z')
    expect(rows[1].text()).toContain('2001:DB8::1')
    // 字面值原样展示：不做大小写折叠（§22 / AC-10）。
    expect(rows[1].text()).toContain('2001:DB8::1')
    // 无状态（Q-002=B）：不渲染状态标签 / 状态列。
    expect(wrapper.find('[data-status]').exists()).toBe(false)
    expect(wrapper.find('.el-table__header').text()).not.toContain('状态')
    // 无 Cluster 列（NQ-4：Cluster 归属不暴露；聚合呈现归 F010）。
    expect(wrapper.find('.el-table__header').text()).not.toContain('集群')
    expect(wrapper.find('.el-table__header').text()).not.toContain('Cluster')
    // 不暴露 deleted_at（契约 §2：字段集合封闭）。
    expect(wrapper.find('.el-table__header').text()).not.toContain('deleted_at')
  })

  it('分页器绑定契约信封值；翻页 → 以新 page 重新请求 /api/ip-addresses', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [IP_ADDRESS_A], total: 120, page: 1, page_size: 50 }),
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
        '/api/ip-addresses?page=3&page_size=50',
        expect.anything(),
      )
    })
  })

  it('点击「详情」→ emit openDetail(ipAddressId)', async () => {
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

    expect(wrapper.emitted('openDetail')).toEqual([[41]])
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

/** DELETE /api/ip-addresses/{id} 的调用次数。 */
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

describe('IpAddressListPage 删除入口（T-41）', () => {
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

  it('二次确认通过 → DELETE /api/ip-addresses/{id}（不发送请求体，契约 §3.5）', async () => {
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
      '/api/ip-addresses/41',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
  })

  it('删除成功（204）→ 刷新列表，被删行消失', async () => {
    const activeList = {
      items: [IP_ADDRESS_A, IP_ADDRESS_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [IP_ADDRESS_B]
        activeList.total = 1
        return noContent()
      },
    })

    const wrapper = await mountListWithRows()

    confirmRowDelete(wrapper, 0)

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.findAll('.el-table__row')[0].text()).toContain('2001:DB8::1')
    const getCalls = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method !== 'DELETE',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('删除成功且当前页变空 → Empty 态，不渲染表格 / 删除失败提示', async () => {
    const activeList = { items: [IP_ADDRESS_A], total: 1, page: 1, page_size: 50 }
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

  it('409 CONFLICT → 保留行、不刷新列表，按 error.code 渲染冲突提示（不解析 message）', async () => {
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
    expect(alert.text()).toContain('无法删除IP 地址')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
  })

  it('404 NOT_FOUND（已不存在或已被逻辑删除）→ 与成功同构：刷新列表，不渲染删除失败提示', async () => {
    const activeList = {
      items: [IP_ADDRESS_A, IP_ADDRESS_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: () => {
        activeList.items = [IP_ADDRESS_B]
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
      items: [IP_ADDRESS_A, IP_ADDRESS_B],
      total: 2,
      page: 1,
      page_size: 50,
    }
    const fetchMock = stubListFetch({
      list: () => jsonResponse(200, activeList),
      remove: async () => {
        await deleteGate
        activeList.items = [IP_ADDRESS_B]
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

// ---- 登记表单入口（POST /api/ip-addresses，契约 §3.1） ----

/** 契约 §4：message 不构成契约；使用与展示无关的文案。 */
const CREATE_NIC_NOT_FOUND_BODY = {
  error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' },
}
const CREATE_VALIDATION_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '与展示无关的校验文案',
    details: [{ field: 'ip_address', code: 'INVALID', message: '与展示无关的字段提示' }],
  },
}
const CREATE_DUPLICATE_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的冲突文案',
    details: [{ field: 'ip_address', code: 'DUPLICATE', message: '与展示无关的重复提示' }],
  },
}

/** 按端点 / 方法分发的 fetch 桩（登记对话框会额外请求 GET /api/network-interfaces）。 */
function stubCreateFetch(routes: {
  list: () => Response
  networkInterfaces?: () => Response
  create?: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'DELETE') return noContent()
    if (init?.method === 'POST') return routes.create?.() ?? jsonResponse(201, IP_ADDRESS_A)
    if (url.includes('/api/network-interfaces')) {
      return (routes.networkInterfaces ?? (() => jsonResponse(200, NIC_LIST_BODY)))()
    }
    return routes.list()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** 打开登记对话框并等待表单渲染就绪（el-dialog 内容首开才挂载）。 */
async function openCreateDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-testid="open-create-dialog"]').trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="ip-form-submit"]').exists()).toBe(true)
  })
}

/** 登记对话框的开闭状态（el-dialog 关闭后 DOM 仍在，以 modelValue 判定）。 */
function createDialogOpen(wrapper: VueWrapper): boolean {
  return wrapper.findComponent(IpAddressFormDialog).props('modelValue') === true
}

/**
 * 对话框内的父网络接口下拉（el-select，按 class 定位）。
 *
 * 注意不能用 findComponent(ElSelect) 直接取第一个：ElPagination 内部也渲染
 * ElSelect（page-size 选择器）；以稳定属性精确定位。
 */
function findNicSelect(wrapper: VueWrapper) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.classes().includes('ip-address-form__nic-select'))
  expect(select, '期望找到所属网络接口下拉').toBeDefined()
  return select!
}

/** 选择父网络接口（el-select 以 update:modelValue 驱动表单状态）。 */
async function selectNic(wrapper: VueWrapper, networkInterfaceId: number): Promise<void> {
  await findNicSelect(wrapper).vm.$emit('update:modelValue', networkInterfaceId)
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
    expect(wrapper.find('[data-testid="ip-form-submit"]').attributes('disabled')).toBeUndefined()
  })
  await wrapper.find('[data-testid="ip-form-submit"]').trigger('click')
}

/** POST /api/ip-addresses 的调用次数。 */
function createCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
  ).length
}

describe('IpAddressListPage 登记入口（T-41 / AC-01~08，§21 不预判）', () => {
  it('打开登记对话框 → 加载父网络接口选项（GET /api/network-interfaces，父存在性由服务端裁决）', async () => {
    const fetchMock = stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = await mountListWithRows()

    expect(wrapper.find('[data-testid="ip-form-submit"]').exists()).toBe(false)
    await openCreateDialog(wrapper)

    expect(wrapper.text()).toContain('登记 IP 地址')
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).includes('/api/network-interfaces')),
      ).toBe(true)
    })
  })

  it('父网络接口未选择（表单未完成）→ 提交按钮禁用；ip_address 为空不禁用（未定义约束不做分支，契约 §7）', async () => {
    stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    // 初始：父网络接口未选择。
    expect(wrapper.find('[data-testid="ip-form-submit"]').attributes('disabled')).toBeDefined()

    // 选择父网络接口后即可提交：ip_address 留空不禁用（空串是否允许由服务端
    // 裁决，前端不基于未定义项编写业务分支）。
    await selectNic(wrapper, 12)
    expect(wrapper.find('[data-testid="ip-form-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('从父 NIC 过滤列表打开 → 父网络接口预选为该 NIC（presetNetworkInterfaceId），可直接提交', async () => {
    stubCreateFetch({ list: () => jsonResponse(200, LIST_BODY) })

    const wrapper = mountPage({ networkInterfaceId: 12 })
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(2)
    })
    await openCreateDialog(wrapper)

    // 预选父 NIC = 表单已完成（选择仍可更改，存在性由服务端裁决）。
    expect(wrapper.find('[data-testid="ip-form-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('填表提交 → POST /api/ip-addresses；请求体恰为两字段（契约 §3.1 schema 封闭）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(201, IP_ADDRESS_A),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/ip-addresses',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ network_interface_id: 12, ip_address: '10.0.1.1/16' }),
      }),
    )
  })

  it('空 ip_address 仍提交（契约 §7 未定义约束：前端不得基于空串编写业务分支）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    // ip_address 留空：前端不拦截（是否拒绝空串由服务端裁决，当前契约不承诺）。
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      )![1] as RequestInit).body as string,
    )
    expect(body.ip_address).toBe('')
  })

  it('与既有行相同字面值的 ip_address 仍提交（§21：前端不做唯一性预检）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(409, CREATE_DUPLICATE_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    // 与既有行相同字面值 '10.0.1.1/16'：前端直接提交，唯一性由服务端裁决。
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      )![1] as RequestInit).body as string,
    )
    expect(body.ip_address).toBe('10.0.1.1/16')
  })

  it('首尾空白的 ip_address 原样提交（契约 §7：不做去除空白 / 归一化）', async () => {
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(201, { ...IP_ADDRESS_A, id: 43 }),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue(' 10.0.1.1/16 ')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      )![1] as RequestInit).body as string,
    )
    expect(body.ip_address).toBe(' 10.0.1.1/16 ')
  })

  it('登记成功（201）→ 关闭对话框并刷新列表', async () => {
    const activeList = { items: [IP_ADDRESS_B], total: 1, page: 1, page_size: 50 }
    const fetchMock = stubCreateFetch({
      list: () => jsonResponse(200, activeList),
      create: () => {
        activeList.items = [IP_ADDRESS_A, IP_ADDRESS_B]
        activeList.total = 2
        return jsonResponse(201, IP_ADDRESS_A)
      },
    })

    const wrapper = mountPage()
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })

    await openCreateDialog(wrapper)
    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
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
        String(call[0]).includes('/api/ip-addresses') &&
        (call[1] as RequestInit | undefined)?.method === 'GET',
    )
    expect(getCalls.length).toBeGreaterThanOrEqual(2)
  })

  it('404 NOT_FOUND（所选父 NIC 不存在 / 已删 / 宿主不活跃，契约 §3.1）→ 「请检查所选网络接口」，不解析 message', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(404, CREATE_NIC_NOT_FOUND_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain('请检查所选网络接口')
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(createDialogOpen(wrapper)).toBe(true)
  })

  it('400 VALIDATION_ERROR → 对话框内展示字段级提示（details[].field）', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(400, CREATE_VALIDATION_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('ip_address')
  })

  it('409 CONFLICT + details[].code === DUPLICATE → 「该 IP 在所属 Cluster 内已被占用」（不解析 message）', async () => {
    stubCreateFetch({
      list: () => jsonResponse(200, LIST_BODY),
      create: () => jsonResponse(409, CREATE_DUPLICATE_BODY),
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.text()).toContain('该 IP 在所属 Cluster 内已被占用')
    expect(wrapper.text()).not.toContain('与展示无关的冲突文案')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(createDialogOpen(wrapper)).toBe(true)
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

    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
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
        return jsonResponse(201, IP_ADDRESS_A)
      },
    })

    const wrapper = await mountListWithRows()
    await openCreateDialog(wrapper)

    await selectNic(wrapper, 12)
    await wrapper.find('[data-testid="ip-form-ip-address"]').setValue('10.0.1.1/16')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="ip-form-submit"]').classes()).toContain('is-loading')
    })

    // 连点不发出第二个 POST（提交中按钮 Loading/disabled，重复点击应被丢弃）。
    await wrapper.find('[data-testid="ip-form-submit"]').trigger('click')
    expect(createCalls(fetchMock)).toBe(1)

    releaseCreate()
    await waitForUi(() => {
      expect(createDialogOpen(wrapper)).toBe(false)
    })
  })
})
