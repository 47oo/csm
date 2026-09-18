import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ClusterFormDialog from '../src/components/ClusterFormDialog.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * F016 ClusterFormDialog 组件级探针（Architecture Handoff「形式 B」）。
 *
 * 直接挂载对话框组件（create / edit 两模式），验证：
 * - 表单最小性（AC-04）：恰一个 name 输入，无状态 / 位置 / 上级 / 计数 /
 *   关系 / deleted_at 字段；
 * - 零业务校验 / 变换（AC-05）：空名可提交（提交按钮不因空串禁用）、含斜杠
 *   与首尾空白的名称逐字节原样提交、不做重名预检（GET 桩件在场仍恰一次
 *   POST，若实现误加预检会出现 GET）；
 * - 请求构造（AC-06 / AC-09）：POST /api/clusters body 恰为 {name}；PATCH
 *   /api/clusters/{id} body 恰为 {name}（写操作走 id，ADR-0003 §2）；
 * - 错误分支按 error.code（必要时 details[].code / details[].field）渲染
 *   固定文案，不解析 message（AC-07 / AC-10）：注入与分支语义矛盾的顶层
 *   message 证伪「按 message 分支」；
 * - 401 交全局会话失效处理、不渲染本地提示（AC-07 / AC-10）；
 * - 提交中 Loading + 防重复（AC-13）、取消不写入（AC-14）、失败提示可关闭
 *   后再次提交（AC-15）、改为自身当前名不误报冲突（AC-11）、改名后旧名
 *   可再登记（AC-12，前端无本地占用状态）。
 *
 * 响应体严格按 docs/api/f001-cluster.md 构造（§2 / §3.1 / §3.5 / §5）。
 * 配套的静态 guard 见 clusterFormNoClientValidation.spec.ts（形式 A）。
 */

const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const CREATED = {
  id: 9,
  name: 'cluster-x',
  created_at: '2026-09-18T10:00:00Z',
  updated_at: '2026-09-18T10:00:00Z',
}
const RENAMED = {
  id: 1,
  name: 'cluster-b',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-18T12:00:00Z',
}

/** 契约 §5：message 不构成契约；使用与展示无关 / 与分支语义矛盾的文案。 */
const VALIDATION_ERROR_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    // 矛盾 message（证伪「按 message 分支」）：文案像是 409 冲突。
    message: '已存在活跃的同名集群',
    details: [{ field: 'name', code: 'INVALID_CHARACTER', message: '与展示无关的字段文案' }],
  },
}
const DUPLICATE_CONFLICT_BODY = {
  error: {
    code: 'CONFLICT',
    // 矛盾 message（证伪「按 message 分支」）：文案像是 400 校验失败。
    message: '请求校验失败',
    details: [{ field: 'name', code: 'DUPLICATE', message: '与展示无关的字段文案' }],
  },
}
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }
const UNAUTHENTICATED_BODY = { error: { code: 'UNAUTHENTICATED', message: '未认证' } }
const INTERNAL_ERROR_BODY = {
  error: { code: 'INTERNAL_ERROR', message: '与展示无关的内部错误文案' },
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/**
 * vi.waitFor 包装：全量并行负载下 el-dialog 挂载 / 异步完成偶发超过
 * vi.waitFor 默认 1s（单文件运行稳定）。沿用既有 spec 的 10s 上限，
 * 仅放宽超时，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/** 直接挂载对话框（v-model 初始 true，打开态）。 */
function mountDialog(mode: 'create' | 'edit', cluster: typeof CLUSTER_A | null = null) {
  return mount(ClusterFormDialog, {
    props: { mode, cluster, modelValue: true },
    global: { plugins: [ElementPlus] },
  })
}

/** 等待对话框表单渲染就绪（el-dialog 内容首开才挂载）。 */
async function waitForDialogReady(wrapper: VueWrapper): Promise<void> {
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="cluster-form-submit"]').exists()).toBe(true)
  })
}

/**
 * 等待提交按钮解除 disabled 后再点击（沿用既有 spec 的 submitWhenEnabled
 * 形态：真实用户只能点击已启用的按钮）。本对话框的禁用条件仅为提交中。
 */
async function submitWhenEnabled(wrapper: VueWrapper): Promise<void> {
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="cluster-form-submit"]').attributes('disabled')).toBeUndefined()
  })
  await wrapper.find('[data-testid="cluster-form-submit"]').trigger('click')
}

function nameInput(wrapper: VueWrapper) {
  return wrapper.find('[data-testid="cluster-form-name"]')
}

function nameValue(wrapper: VueWrapper): string {
  return (nameInput(wrapper).element as HTMLInputElement).value
}

/** 对话框是否已被组件置为关闭（直接挂载无父级 v-model，以发射判定）。 */
function dialogClosed(wrapper: VueWrapper): boolean {
  return (wrapper.emitted('update:modelValue') ?? []).some((args) => args[0] === false)
}

/** 指定 method 的 fetch 调用次数。 */
function methodCalls(fetchMock: ReturnType<typeof vi.fn>, method: string): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === method,
  ).length
}

/**
 * 按方法分发的 fetch 桩：POST → create()；PATCH → patch()；GET → get()
 * （探针 3：若实现误加唯一性 / 存在性预检，会出现 GET）。
 */
function stubDialogFetch(routes: {
  create?: () => Response | Promise<Response>
  patch?: () => Response | Promise<Response>
  get?: () => Response
}) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return routes.create?.() ?? jsonResponse(201, CREATED)
    if (init?.method === 'PATCH') return routes.patch?.() ?? jsonResponse(200, RENAMED)
    if (init?.method === 'GET') {
      return routes.get?.() ?? jsonResponse(200, { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 })
    }
    return jsonResponse(500, INTERNAL_ERROR_BODY)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  // 401 用例注册的全局未认证处理器在用例后清除，保证隔离。
  setUnauthenticatedHandler(null)
})

describe('ClusterFormDialog create 模式（登记，契约 §3.1）', () => {
  it('恰一个输入字段 name（AC-04）：无状态 / 位置 / 上级 / 计数 / 关系 / deleted_at 输入', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    expect(wrapper.text()).toContain('登记集群')
    expect(nameInput(wrapper).exists()).toBe(true)
    // 恰一个表单项；无下拉 / 数字输入等任何其他控件。
    expect(wrapper.findAll('.el-form-item')).toHaveLength(1)
    expect(wrapper.findAll('.el-select')).toHaveLength(0)
    expect(wrapper.findAll('.el-input-number')).toHaveLength(0)
    const text = wrapper.text()
    expect(text).not.toContain('状态')
    expect(text).not.toContain('DataCenter')
    expect(text).not.toContain('机柜')
    expect(text).not.toContain('上级')
    expect(text).not.toContain('deleted_at')
  })

  it('打开对话框不发起任何请求（无选项加载；架构 Handoff REQUIRED #6）', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('空名称可提交（AC-05 探针 1）：提交按钮不因空串禁用；POST body 恰为 {"name":""}', async () => {
    const fetchMock = stubDialogFetch({})

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    expect(nameValue(wrapper)).toBe('')
    // 空串行为属 undefined_constraints（契约 §7）：前端不得据此禁用提交。
    expect(wrapper.find('[data-testid="cluster-form-submit"]').attributes('disabled')).toBeUndefined()

    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'POST')).toBe(1)
    })
    // 恰一次 POST、无任何其他请求（无预检读）。
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/clusters',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: '' }) }),
    )
  })

  it('含斜杠与首尾空白的名称逐字节原样提交（AC-05 探针 2）：body 恰为 {"name":" a/b "}，未被拦截、未变换', async () => {
    const fetchMock = stubDialogFetch({})

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue(' a/b ')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'POST')).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/clusters',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: ' a/b ' }) }),
    )
  })

  it('不做重名预检（AC-05 探针 3）：GET 桩返回同名集群，提交仍恰一次 POST；409 按固定文案渲染（AC-07 / AC-08）', async () => {
    const fetchMock = stubDialogFetch({
      get: () => jsonResponse(200, { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }),
      create: () => jsonResponse(409, DUPLICATE_CONFLICT_BODY),
    })

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    // 与 GET 桩中集群同名的输入：前端不预检，直接提交由服务端裁决。
    await nameInput(wrapper).setValue('cluster-a')
    await submitWhenEnabled(wrapper)

    // 恰一次 POST、零 GET（若实现误加唯一性预检，此处会出现 GET）。
    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'POST')).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法登记')
    expect(alert.text()).toContain('已存在活跃的同名集群')
    // 按 code 分支：矛盾 message（文案像是校验失败）不参与渲染。
    expect(alert.text()).not.toContain('请求校验失败')
    // 失败不关闭对话框、不清空已填内容、不误报成功（AC-07 / AC-08）。
    expect(dialogClosed(wrapper)).toBe(false)
    expect(nameValue(wrapper)).toBe('cluster-a')
    expect(wrapper.emitted('success')).toBeUndefined()
  })

  it('登记成功（201）→ emit success(ClusterRead) 且对话框关闭（AC-06）', async () => {
    stubDialogFetch({})

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-x')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.emitted('success')).toEqual([[CREATED]])
    })
    expect(dialogClosed(wrapper)).toBe(true)
  })

  it('400 VALIDATION_ERROR → 字段级提示指向 name（AC-07；矛盾 message 证伪按 code 分支）', async () => {
    stubDialogFetch({ create: () => jsonResponse(400, VALIDATION_ERROR_BODY) })

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('a/b')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('name')
    // 按 code 分支：顶层 message 写成冲突文案也不会渲染冲突分支，也不透出该 message。
    expect(alert.text()).not.toContain('已存在活跃的同名集群')
    expect(alert.text()).not.toContain('名称在所有当前有效集群中全局唯一')
    // 失败不关闭对话框。
    expect(dialogClosed(wrapper)).toBe(false)
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，不渲染本地失败提示（AC-07）', async () => {
    stubDialogFetch({ create: () => jsonResponse(401, UNAUTHENTICATED_BODY) })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-x')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
  })

  it('网络错误 → NETWORK_ERROR 固定文案（AC-07 其他错误）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('网络中断')
      }),
    )

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-x')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NETWORK_ERROR"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NETWORK_ERROR"]').text()).toContain('无法连接服务器')
    expect(dialogClosed(wrapper)).toBe(false)
  })

  it('500 INTERNAL_ERROR → 通用失败提示（按 code 原样展示，AC-07 其他错误）', async () => {
    stubDialogFetch({ create: () => jsonResponse(500, INTERNAL_ERROR_BODY) })

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-x')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="INTERNAL_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="INTERNAL_ERROR"]')
    expect(alert.text()).toContain('提交失败')
    expect(alert.text()).toContain('请求未成功（INTERNAL_ERROR）')
    expect(alert.text()).not.toContain('与展示无关的内部错误文案')
  })

  it('404（POST 契约上不产生；防御性兜底）→ 按 code 原样展示，不误渲染 edit 专属文案（AC-07 其他错误）', async () => {
    stubDialogFetch({ create: () => jsonResponse(404, NOT_FOUND_BODY) })

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-x')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.text()).toContain('提交失败')
    expect(alert.text()).toContain('请求未成功（NOT_FOUND）')
    expect(alert.text()).not.toContain('该集群不存在或已被删除')
    expect(alert.text()).not.toContain('与展示无关的未找到文案')
  })

  it('提交中：提交按钮 Loading，重复点击不产生第二个 POST（AC-13）', async () => {
    let releaseCreate!: () => void
    const createGate = new Promise<void>((resolve) => {
      releaseCreate = resolve
    })
    const fetchMock = stubDialogFetch({
      create: async () => {
        await createGate
        return jsonResponse(201, CREATED)
      },
    })

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-x')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'POST')).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="cluster-form-submit"]').classes()).toContain('is-loading')
    })

    // 连点不发出第二个 POST。
    await wrapper.find('[data-testid="cluster-form-submit"]').trigger('click')
    expect(methodCalls(fetchMock, 'POST')).toBe(1)

    releaseCreate()
    await waitForUi(() => {
      expect(wrapper.emitted('success')).toEqual([[CREATED]])
    })
  })

  it('取消 → 不发送任何写请求，仅关闭对话框（AC-14）', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-x')
    const cancelButton = wrapper.findAll('button').find((b) => b.text() === '取消')
    expect(cancelButton).toBeDefined()
    await cancelButton!.trigger('click')

    expect(fetchMock).not.toHaveBeenCalled()
    expect(dialogClosed(wrapper)).toBe(true)
    expect(wrapper.emitted('success')).toBeUndefined()
  })

  it('失败提示可关闭，关闭后可修改再次提交（AC-15）', async () => {
    let createResponse: () => Response = () => jsonResponse(409, DUPLICATE_CONFLICT_BODY)
    const fetchMock = stubDialogFetch({ create: () => createResponse() })

    const wrapper = mountDialog('create')
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-a')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })

    // 关闭失败提示。
    await wrapper.find('.el-alert__close-btn').trigger('click')
    await waitForUi(() => {
      expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    })

    // 修改内容后可再次提交。
    createResponse = () => jsonResponse(201, CREATED)
    await nameInput(wrapper).setValue('cluster-y')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'POST')).toBe(2)
    })
    const secondBody = (fetchMock.mock.calls[1]![1] as RequestInit).body as string
    expect(secondBody).toBe(JSON.stringify({ name: 'cluster-y' }))
    await waitForUi(() => {
      expect(wrapper.emitted('success')).toEqual([[CREATED]])
    })
  })
})

describe('ClusterFormDialog edit 模式（改名，契约 §3.5）', () => {
  it('预填当前 name（AC-02）；标题与提交文案为改名形态；打开不发起任何请求（AC-03：与登记同一组件）', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    expect(wrapper.text()).toContain('集群改名')
    expect(wrapper.find('[data-testid="cluster-form-submit"]').text()).toContain('保存')
    expect(nameValue(wrapper)).toBe('cluster-a')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('改名提交 → PATCH /api/clusters/{id}，body 恰为 {name}（AC-09）', async () => {
    const fetchMock = stubDialogFetch({})

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-b')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'PATCH')).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/clusters/1',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ name: 'cluster-b' }) }),
    )
  })

  it('改名成功（200）→ emit success(ClusterRead) 且对话框关闭（AC-09）', async () => {
    stubDialogFetch({})

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-b')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.emitted('success')).toEqual([[RENAMED]])
    })
    expect(dialogClosed(wrapper)).toBe(true)
  })

  it('改为自身当前名称 → 按 200 处理为成功，不显示冲突提示（AC-11，契约 §3.5）', async () => {
    const fetchMock = stubDialogFetch({ patch: () => jsonResponse(200, CLUSTER_A) })

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    // 不修改预填的当前名称，直接提交。
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'PATCH')).toBe(1)
    })
    expect(wrapper.emitted('success')).toEqual([[CLUSTER_A]])
    // 不误报冲突，也不渲染任何本地失败提示。
    expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(false)
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    expect(dialogClosed(wrapper)).toBe(true)
  })

  it('409 CONFLICT（DUPLICATE）→ 「无法保存」+ 固定文案，对话框保持打开、内容保留（AC-10）', async () => {
    stubDialogFetch({ patch: () => jsonResponse(409, DUPLICATE_CONFLICT_BODY) })

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-b')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法保存')
    expect(alert.text()).toContain('已存在活跃的同名集群')
    // 按 code 分支：矛盾 message 不参与渲染。
    expect(alert.text()).not.toContain('请求校验失败')
    expect(dialogClosed(wrapper)).toBe(false)
    expect(nameValue(wrapper)).toBe('cluster-b')
  })

  it('400 VALIDATION_ERROR（edit）→ 字段级提示指向 name（AC-10）', async () => {
    stubDialogFetch({ patch: () => jsonResponse(400, VALIDATION_ERROR_BODY) })

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('a/b')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('name')
    expect(alert.text()).not.toContain('已存在活跃的同名集群')
    expect(dialogClosed(wrapper)).toBe(false)
  })

  it('404 NOT_FOUND（目标不存在或已逻辑删除，两者不区分）→ 固定文案，不解析 message（AC-10）', async () => {
    stubDialogFetch({ patch: () => jsonResponse(404, NOT_FOUND_BODY) })

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-b')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.text()).toContain('无法保存')
    expect(alert.text()).toContain('该集群不存在或已被删除')
    expect(alert.text()).not.toContain('与展示无关的未找到文案')
    expect(dialogClosed(wrapper)).toBe(false)
  })

  it('401 UNAUTHENTICATED（edit）→ 触发全局会话失效处理，不渲染本地失败提示（AC-10）', async () => {
    stubDialogFetch({ patch: () => jsonResponse(401, UNAUTHENTICATED_BODY) })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(wrapper)

    await nameInput(wrapper).setValue('cluster-b')
    await submitWhenEnabled(wrapper)

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
  })

  it('改名成功后以旧名登记其他集群不被拦截（AC-12：前端不维护「旧名已被占用」状态）', async () => {
    const fetchMock = stubDialogFetch({})

    // 先改名：cluster-a → cluster-b（PATCH 200）。
    const editWrapper = mountDialog('edit', CLUSTER_A)
    await waitForDialogReady(editWrapper)
    await nameInput(editWrapper).setValue('cluster-b')
    await submitWhenEnabled(editWrapper)
    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'PATCH')).toBe(1)
    })

    // 再以刚释放的旧名登记：create 对话框不做任何本地占用判断，直接 POST。
    const createWrapper = mountDialog('create')
    await waitForDialogReady(createWrapper)
    await nameInput(createWrapper).setValue('cluster-a')
    await submitWhenEnabled(createWrapper)

    await waitForUi(() => {
      expect(methodCalls(fetchMock, 'POST')).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/clusters',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: 'cluster-a' }) }),
    )
  })
})
