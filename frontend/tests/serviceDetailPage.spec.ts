import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElInputNumber, ElPopconfirm, ElSelect } from 'element-plus'
import ServiceDetailPage from '../src/pages/ServiceDetailPage.vue'
import ServiceFormDialog from '../src/components/ServiceFormDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * Service 详情页测试（AC-16、AC-20、AC-21、AC-28、AC-30、AC-54）。
 *
 * 覆盖：404 独立 Not Found 态（与列表 Empty 可区分）、全部 11 字段展示
 * （6 个可选字段 null 渲染「—」；carriers 列表全量展示；无状态 / 无
 * Cluster 归属字段）、登记入口（多载体选择，预选当前服务载体；成功后跳转
 * 新详情）、可选字段修改入口（PATCH：仅 6 字段；name / 载体绑定不可编辑）、
 * 修改失败按 error.code 分支（400 / 404 / 401）、删除入口（204 →
 * Not Found 态 / 409 / 404 / 提交中防重复）。
 *
 * 响应体严格按 docs/api/f008-service.md 构造（§2 资源表示 / §4.3 读取 /
 * §4.4 更新 / §4.5 删除 / §5 错误信封 / Empty 与 Not Found 语义）。
 */

const SERVICE_NULLS = {
  id: 7,
  name: 'mon',
  service_type: null,
  url: null,
  port: null,
  protocol: null,
  owner: null,
  description: null,
  carriers: [
    { carrier_type: 'BARE_METAL', carrier_id: 3 },
    { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 5 },
    { carrier_type: 'CONTAINER', carrier_id: 11 },
  ],
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
}

const SERVICE_FULL = {
  ...SERVICE_NULLS,
  service_type: '自研',
  url: '这不是一个 URL',
  port: '8080-8090',
  protocol: '自定义协议',
  owner: 'ops',
  description: '第一行\n第二行',
}

const SERVICE_OTHER = {
  ...SERVICE_NULLS,
  id: 8,
  name: 'storage',
  carriers: [{ carrier_type: 'BARE_METAL', carrier_id: 4 }],
}

const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '资源不存在' } }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function noContent(): Response {
  return new Response(null, { status: 204 })
}

function mountDetailPage(serviceId = 7) {
  return mount(ServiceDetailPage, {
    props: { serviceId },
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

describe('ServiceDetailPage 状态渲染', () => {
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

    resolveDetail(SERVICE_NULLS)
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })
  })

  it('成功（6 字段全 null）→ 展示全部 11 字段与全部载体绑定，null 渲染「—」（契约 §2）；无状态 / 无 Cluster 归属字段（AC-16 / AC-20 / AC-28）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, SERVICE_NULLS)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('服务详情')
    // 身份 / 时间字段：契约原样值，不做任何变换。
    expect(text).toContain('mon')
    expect(text).toContain('2026-09-20T10:00:00Z')
    // 6 个可选字段 null → 「—」（逐行断言 label → content 对应）。
    const rows = wrapper.findAll('.el-descriptions table tbody tr')
    const contentOf = (label: string): string => {
      const row = rows.find((r) => r.find('.el-descriptions__label').text() === label)
      expect(row, `期望存在字段行「${label}」`).toBeDefined()
      return row!.find('.el-descriptions__content').text()
    }
    for (const label of ['服务类型', 'URL', '端口', '协议', '负责人', '描述']) {
      expect(contentOf(label)).toBe('—')
    }
    // 载体绑定（AC-16）：全部 3 条绑定逐项展示（契约 §2 稳定顺序原样值）。
    const carrierTags = wrapper.findAll('[data-testid="service-carrier"]')
    expect(carrierTags).toHaveLength(3)
    expect(carrierTags[0].text()).toBe('BARE_METAL #3')
    expect(carrierTags[1].text()).toBe('VIRTUAL_MACHINE #5')
    expect(carrierTags[2].text()).toBe('CONTAINER #11')
    expect(contentOf('运行载体')).toContain('共 3 项')
    // Service 无状态（Q-002=B）：不渲染状态标签 / 状态行。
    expect(wrapper.find('[data-status]').exists()).toBe(false)
    expect(text).not.toContain('状态')
    // 不暴露 deleted_at / Cluster 归属（契约 §2：字段集合封闭；AC-20/21）。
    expect(text).not.toContain('deleted_at')
    expect(text).not.toContain('cluster_id')
    expect(text).not.toContain('集群')
  })

  it('成功（6 字段已登记）→ 原样展示纯文本值（不拆分 / 不归一，AC-14）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, SERVICE_FULL)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('自研')
    expect(text).toContain('这不是一个 URL')
    expect(text).toContain('8080-8090')
    expect(text).toContain('自定义协议')
    expect(text).toContain('ops')
    expect(text).toContain('第一行\n第二行')
  })

  it('成功（单载体）→ 载体绑定原样展示（共 1 项）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, SERVICE_OTHER)))

    const wrapper = mountDetailPage(8)

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const carrierTags = wrapper.findAll('[data-testid="service-carrier"]')
    expect(carrierTags).toHaveLength(1)
    expect(carrierTags[0].text()).toBe('BARE_METAL #4')
    expect(wrapper.text()).toContain('共 1 项')
  })

  it('404 NOT_FOUND（不存在或已逻辑删除，两者不区分）→ 独立 Not Found 态，不渲染 Empty / 内容 / 操作入口', async () => {
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
    expect(wrapper.find('.el-descriptions').exists()).toBe(false)
    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无服务')
  })

  it('500 INTERNAL_ERROR → Error 态按 error.code 渲染（与 not-found 态可区分）', async () => {
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
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, SERVICE_NULLS)))

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

  it('serviceId 变化（复用组件，如详情页登记成功后跳转新服务）→ 重新读取新目标', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/services/8')) return jsonResponse(200, SERVICE_OTHER)
      return jsonResponse(200, SERVICE_NULLS)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountDetailPage(7)
    await waitForUi(() => {
      expect(wrapper.text()).toContain('mon')
    })

    await wrapper.setProps({ serviceId: 8 })

    await waitForUi(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/services/8', expect.anything())
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('storage')
    })
    expect(wrapper.findAll('[data-testid="service-carrier"]')).toHaveLength(1)
  })
})

// ---- 登记入口（POST /api/services，契约 §4.1）与编辑入口（PATCH，契约 §4.4） ----

function stubDetailFetch(routes: {
  detail: () => Response
  patch?: () => Response | Promise<Response>
  create?: () => Response | Promise<Response>
  remove?: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'PATCH') return routes.patch?.() ?? noContent()
    if (init?.method === 'POST') return routes.create?.() ?? jsonResponse(201, SERVICE_NULLS)
    if (init?.method === 'DELETE') return routes.remove?.() ?? noContent()
    return routes.detail()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function mountDetailContent(): Promise<VueWrapper> {
  const wrapper = mountDetailPage()
  await waitForUi(() => {
    expect(wrapper.attributes('data-state')).toBe('content')
  })
  return wrapper
}

/** 按模式取对话框组件（详情页同时挂载 create / edit 两个实例）。 */
function findDialog(wrapper: VueWrapper, mode: 'create' | 'edit') {
  const dialog = wrapper
    .findAllComponents(ServiceFormDialog)
    .find((d) => d.props('mode') === mode)
  expect(dialog, `期望找到 mode=${mode} 的对话框`).toBeDefined()
  return dialog!
}

/** 打开登记对话框并等待表单渲染就绪（el-dialog 内容首开才挂载）。 */
async function openCreateDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-testid="open-create-dialog"]').trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="service-form-submit"]').exists()).toBe(true)
  })
}

/** 打开编辑对话框并等待表单渲染就绪。 */
async function openEditDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-testid="open-edit-dialog"]').trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="service-form-submit"]').exists()).toBe(true)
  })
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

function patchCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
  ).length
}

function createCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
  ).length
}

describe('ServiceDetailPage 登记入口（POST，契约 §4.1；多载体选择）', () => {
  it('内容态存在「登记服务」入口；对话框含多载体选择（三种类型 + 载体 ID），且预选当前服务的全部载体', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, SERVICE_NULLS) })

    const wrapper = await mountDetailContent()

    expect(wrapper.find('[data-testid="open-create-dialog"]').exists()).toBe(true)
    await openCreateDialog(wrapper)

    expect(wrapper.find('[data-testid="service-form-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="service-form-carrier-type"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="service-form-carrier-id"]').exists()).toBe(true)
    // 预选载体 = 当前服务的 3 条载体 → 表单已完整，提交可用（选择仍可增删改，
    // 存在性由服务端裁决）。
    expect(findFormCarrierTypeSelects(wrapper)).toHaveLength(3)
    expect(findFormCarrierIdInputs(wrapper)).toHaveLength(3)
    await waitForUi(() => {
      expect(
        wrapper.find('[data-testid="service-form-submit"]').attributes('disabled'),
      ).toBeUndefined()
    })
  })

  it('登记另一服务 → POST /api/services：请求体携带预选载体集合 + name + 6 字段（契约 §4.1）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      create: () => jsonResponse(201, { ...SERVICE_OTHER, id: 9, name: 'redis' }),
    })

    const wrapper = await mountDetailContent()
    await openCreateDialog(wrapper)

    await wrapper.find('[data-testid="service-form-name"]').setValue('redis')
    await wrapper.find('[data-testid="service-form-owner"]').setValue('ops2')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(createCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/services',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          name: 'redis',
          carriers: [
            { carrier_type: 'BARE_METAL', carrier_id: 3 },
            { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 5 },
            { carrier_type: 'CONTAINER', carrier_id: 11 },
          ],
          service_type: null,
          url: null,
          port: null,
          protocol: null,
          owner: 'ops2',
          description: null,
        }),
      }),
    )
  })

  it('登记成功（201）→ emit openDetail(新服务 id)，跳转到新服务详情', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      create: () => jsonResponse(201, { ...SERVICE_OTHER, id: 9, name: 'redis' }),
    })

    const wrapper = await mountDetailContent()
    await openCreateDialog(wrapper)

    await wrapper.find('[data-testid="service-form-name"]').setValue('redis')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.emitted('openDetail')).toEqual([[9]])
    })
    // 对话框关闭（跳转由 App 处理；当前详情不重新读取，仍展示原服务）。
    await waitForUi(() => {
      expect(findDialog(wrapper, 'create').props('modelValue')).toBe(false)
    })
  })

  it('增删改预选载体后登记 → 请求体携带修改后的载体集合（前端不锁定预选值）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      create: () => jsonResponse(201, { ...SERVICE_NULLS, id: 9 }),
    })

    const wrapper = await mountDetailContent()
    await openCreateDialog(wrapper)

    // 修改第 0 行为 VIRTUAL_MACHINE #7；移除第 2 行（CONTAINER #11）。
    await findFormCarrierTypeSelects(wrapper)[0]!.vm.$emit('update:modelValue', 'VIRTUAL_MACHINE')
    await findFormCarrierIdInputs(wrapper)[0]!.vm.$emit('update:modelValue', 7)
    await wrapper.findAll('[data-testid="service-form-remove-carrier"]')[2]!.trigger('click')
    await wrapper.find('[data-testid="service-form-name"]').setValue('redis')
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
      { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 7 },
      { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 5 },
    ])
  })

  it('409 CONFLICT（name DUPLICATE）→ 对话框内按 error.code 渲染全局唯一固定文案（不解析 message），不跳转', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      create: () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '与展示无关的重复文案',
            details: [{ field: 'name', code: 'DUPLICATE', message: '与展示无关的字段文案' }],
          },
        }),
    })

    const wrapper = await mountDetailContent()
    await openCreateDialog(wrapper)

    await wrapper.find('[data-testid="service-form-name"]').setValue('mon')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="CONFLICT"]').text()).toContain(
      '已存在活跃的同名服务',
    )
    expect(wrapper.text()).not.toContain('与展示无关的重复文案')
    // 失败不跳转、对话框保持打开。
    expect(wrapper.emitted('openDetail')).toBeUndefined()
    expect(findDialog(wrapper, 'create').props('modelValue')).toBe(true)
  })

  it('404 NOT_FOUND（任一载体不存在 / 已删，契约 §4.1）→ 对话框内按 error.code 渲染固定文案，不解析 message', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      create: () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }),
    })

    const wrapper = await mountDetailContent()
    await openCreateDialog(wrapper)

    // 改选为不存在的载体（存在性由服务端裁决，前端不预判）。
    await findFormCarrierIdInputs(wrapper)[0]!.vm.$emit('update:modelValue', 999)
    await wrapper.find('[data-testid="service-form-name"]').setValue('redis')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain(
      '载体不存在或已被删除，请检查载体类型与载体 ID',
    )
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，不渲染本地失败提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      create: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountDetailContent()
    await openCreateDialog(wrapper)

    await wrapper.find('[data-testid="service-form-name"]').setValue('redis')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    })
  })
})

describe('ServiceDetailPage 编辑入口（PATCH，契约 §4.4 / NQ-01）', () => {
  it('内容态存在「编辑」入口；表单不含 name 与载体输入（不可变，契约 §4.4 / NQ-01/NQ-02）', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, SERVICE_NULLS) })

    const wrapper = await mountDetailContent()

    expect(wrapper.find('[data-testid="open-edit-dialog"]').exists()).toBe(true)
    await openEditDialog(wrapper)

    // name / 载体绑定不在 PATCH 可变集内 → 表单不提供输入。
    expect(wrapper.find('[data-testid="service-form-name"]').exists()).toBe(false)
    expect(wrapper.find('.service-form__carrier-type').exists()).toBe(false)
    expect(wrapper.find('.service-form__carrier-id').exists()).toBe(false)
    expect(wrapper.find('[data-testid="service-form-add-carrier"]').exists()).toBe(false)
    // 6 字段在表单中。
    for (const field of ['service_type', 'url', 'port', 'protocol', 'owner', 'description']) {
      expect(wrapper.find(`[data-testid="service-form-${field}"]`).exists()).toBe(true)
    }
  })

  it('修改可选字段 → PATCH /api/services/{id}：body 为 6 字段快照（null → null，契约 §4.4）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_FULL),
      patch: () => jsonResponse(200, { ...SERVICE_FULL, port: '8080' }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="service-form-port"]').setValue('8080')
    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/services/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          service_type: '自研',
          url: '这不是一个 URL',
          port: '8080',
          protocol: '自定义协议',
          owner: 'ops',
          description: '第一行\n第二行',
        }),
      }),
    )
  })

  it('清空可选字段 → 提交 null（契约 §4.4：显式 null 表示清空）；body 不含 name / carriers / id / status（schema 封闭）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_FULL),
      patch: () => jsonResponse(200, { ...SERVICE_FULL, url: null }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="service-form-url"]').setValue('')
    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
      )![1] as RequestInit).body as string,
    )
    expect(body.url).toBeNull()
    expect(body.port).toBe('8080-8090')
    // PATCH 可变字段封闭为 6 字段：不含 name / carriers / id / status / cluster_id。
    expect(body.name).toBeUndefined()
    expect(body.carriers).toBeUndefined()
    expect(body.carrier_type).toBeUndefined()
    expect(body.carrier_id).toBeUndefined()
    expect(body.id).toBeUndefined()
    expect(body.status).toBeUndefined()
    expect(body.cluster_id).toBeUndefined()
  })

  it('保存成功（200）→ 关闭对话框并重新读取，展示新值', async () => {
    const updated = {
      ...SERVICE_NULLS,
      owner: 'ops2',
      updated_at: '2026-09-20T12:00:00Z',
    }
    const mutable = { detail: () => jsonResponse(200, SERVICE_NULLS) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      patch: () => {
        mutable.detail = () => jsonResponse(200, updated)
        return jsonResponse(200, updated)
      },
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="service-form-owner"]').setValue('ops2')
    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    // 详情重新读取并展示服务端返回的新值。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('ops2')
    })
    expect(wrapper.text()).toContain('2026-09-20T12:00:00Z')
    // 请求序列：初始 GET → PATCH → 重新读取 GET。
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/services/7')
  })

  it('400 VALIDATION_ERROR（含不可变字段等，契约 §4.4）→ 对话框内按 error.code 渲染字段级提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      patch: () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '与展示无关的校验文案',
            details: [{ field: 'name', code: 'INVALID', message: '与展示无关的字段提示' }],
          },
        }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('name')
    // 详情内容保留，用户可修改后重试。
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.find('[data-testid="service-form-submit"]').exists()).toBe(true)
  })

  it('404 NOT_FOUND（已被其他操作删除）→ 对话框内按 error.code 渲染固定文案，不解析 message', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      patch: () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain(
      '该服务不存在或已被删除',
    )
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，不渲染本地失败提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      patch: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    })
  })

  it('提交中：提交按钮 Loading，重复点击不产生第二个 PATCH（禁止重复提交）', async () => {
    let releasePatch!: () => void
    const patchGate = new Promise<void>((resolve) => {
      releasePatch = resolve
    })
    const updated = { ...SERVICE_NULLS, owner: 'ops2' }
    const mutable = { detail: () => jsonResponse(200, SERVICE_NULLS) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      patch: async () => {
        await patchGate
        mutable.detail = () => jsonResponse(200, updated)
        return jsonResponse(200, updated)
      },
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="service-form-owner"]').setValue('ops2')
    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="service-form-submit"]').classes()).toContain('is-loading')
    })

    await wrapper.find('[data-testid="service-form-submit"]').trigger('click')
    expect(patchCalls(fetchMock)).toBe(1)

    releasePatch()
    await waitForUi(() => {
      expect(wrapper.text()).toContain('ops2')
    })
  })
})

// ---- 删除入口（DELETE，契约 §4.5） ----

/** 契约 §5：message 不构成契约；使用与展示无关的文案。 */
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

function confirmDelete(wrapper: VueWrapper): void {
  wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))
}

describe('ServiceDetailPage 删除入口（契约 §4.5）', () => {
  it('内容态存在删除入口（ElPopconfirm 二次确认），空闲时可触发（前端不预判，§21）', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, SERVICE_NULLS) })

    const wrapper = await mountDetailContent()

    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
    const deleteButton = wrapper.findAll('button').find((b) => b.text().trim() === '删除')
    expect(deleteButton).toBeDefined()
    expect(deleteButton!.attributes('disabled')).toBeUndefined()
  })

  it('未通过二次确认（确认框取消）→ 不发送 DELETE 请求', async () => {
    const fetchMock = stubDetailFetch({ detail: () => jsonResponse(200, SERVICE_NULLS) })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('cancel', new MouseEvent('click'))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.attributes('data-state')).toBe('content')
  })

  it('删除成功（204）→ 重新读取得到 404 → 进入既有独立 Not Found 态', async () => {
    const mutable = { detail: () => jsonResponse(200, SERVICE_NULLS) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      remove: () => {
        mutable.detail = () => jsonResponse(404, NOT_FOUND_BODY)
        return noContent()
      },
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('资源不存在，或已被删除')
    expect(wrapper.find('.el-descriptions').exists()).toBe(false)
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
    // 请求序列：初始 GET → DELETE → 重新读取 GET（404）。
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/services/7')
  })

  it('非 404 失败（如 409 CONFLICT）→ 保留详情内容并按 error.code 渲染冲突提示（不解析 message）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, SERVICE_NULLS),
      remove: () => jsonResponse(409, DELETE_CONFLICT_BODY),
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.text()).toContain('mon')
    const alert = wrapper.find('[data-delete-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法删除服务')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
    // 失败后可重试：删除入口仍在。
    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
  })

  it('删除返回 404（已被其他操作删除）→ 同样进入独立 Not Found 态，不渲染删除失败提示', async () => {
    const mutable = { detail: () => jsonResponse(200, SERVICE_NULLS) }
    stubDetailFetch({
      detail: () => mutable.detail(),
      remove: () => {
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
    const mutable = { detail: () => jsonResponse(200, SERVICE_NULLS) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      remove: async () => {
        await deleteGate
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

    await waitForUi(() => {
      const deleteButton = wrapper.findAll('button').find((b) => b.text().trim() === '删除')
      expect(deleteButton!.classes()).toContain('is-loading')
    })

    confirmDelete(wrapper)
    expect(
      fetchMock.mock.calls.filter(
        (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
      ),
    ).toHaveLength(1)

    releaseDelete()
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
  })
})
