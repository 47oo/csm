import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPopconfirm, ElSelect } from 'element-plus'
import NetworkInterfaceDetailPage from '../src/pages/NetworkInterfaceDetailPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * 网络接口详情页测试（T-FE-01 / AC-34）。
 *
 * 覆盖：404 独立 Not Found 态（与列表 Empty 可区分）、7 字段展示（时间不透明
 * 字符串；枚举字面值原样展示）、无状态展示（Q-002=B）、枚举修改入口（PATCH：
 * 仅 technology_type / purpose；name / bare_metal_id 不可编辑）、修改失败按
 * error.code 分支（400 / 404 / 401）、删除入口（204 → Not Found 态 / 409 /
 * 404 / 提交中防重复）。
 *
 * 响应体严格按 docs/api/f004-network-interface.md 构造（§2 资源表示 / §3.3 读取 /
 * §3.4 更新 / §3.5 删除 / §4 错误信封 / §9 Empty 与 Not Found）。
 */

const NETWORK_INTERFACE_A = {
  id: 12,
  bare_metal_id: 3,
  name: 'eth0',
  technology_type: 'Ethernet',
  purpose: 'Business',
  created_at: '2026-09-17T10:00:00Z',
  updated_at: '2026-09-17T10:00:00Z',
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

function mountDetailPage(networkInterfaceId = 12) {
  return mount(NetworkInterfaceDetailPage, {
    props: { networkInterfaceId },
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

describe('NetworkInterfaceDetailPage 状态渲染', () => {
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

    resolveDetail(NETWORK_INTERFACE_A)
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })
  })

  it('成功 → 展示全部 7 字段（契约原样值，时间不透明字符串；枚举字面值原样展示，不做中文映射）；无状态字段（Q-002=B）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, NETWORK_INTERFACE_A)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('网络接口详情')
    // 全部 7 字段：契约原样值，不做任何变换。
    expect(text).toContain('宿主裸金属 ID')
    expect(text).toContain('3')
    expect(text).toContain('eth0')
    expect(text).toContain('Ethernet')
    expect(text).toContain('Business')
    expect(text).toContain('2026-09-17T10:00:00Z')
    // 枚举字面值原样展示，不做中文映射（契约 §1.5）。
    expect(text).not.toContain('以太网')
    expect(text).not.toContain('业务')
    // NIC 无状态（Q-002=B）：不渲染状态标签 / 状态行。
    expect(wrapper.find('[data-status]').exists()).toBe(false)
    expect(text).not.toContain('状态')
    // 不暴露 deleted_at / cluster_id（契约 §2：字段集合封闭）。
    expect(text).not.toContain('deleted_at')
    expect(text).not.toContain('cluster_id')
    expect(text).not.toContain('集群')
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
    expect(wrapper.text()).not.toContain('暂无网络接口')
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
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, NETWORK_INTERFACE_A)))

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
})

// ---- 枚举修改入口（PATCH，契约 §3.4） ----

function stubDetailFetch(routes: {
  detail: () => Response
  patch?: () => Response | Promise<Response>
  remove?: () => Response | Promise<Response>
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'PATCH') return routes.patch?.() ?? noContent()
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

/** 打开编辑对话框并等待表单渲染就绪（el-dialog 内容首开才挂载）。 */
async function openEditDialog(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('[data-testid="open-edit-dialog"]').trigger('click')
  await waitForUi(() => {
    expect(wrapper.find('[data-testid="nic-form-submit"]').exists()).toBe(true)
  })
}

function patchCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
  ).length
}

/** 对话框内的枚举下拉（el-select，按 data-testid 定位）。 */
function findEnumSelect(wrapper: VueWrapper, testId: string) {
  const select = wrapper
    .findAllComponents(ElSelect)
    .find((s) => s.attributes('data-testid') === testId)
  expect(select, `期望找到下拉 ${testId}`).toBeDefined()
  return select!
}

describe('NetworkInterfaceDetailPage 编辑入口（PATCH，T-FE-01 / AC-18~20）', () => {
  it('内容态存在「编辑」入口；表单不含 name / 宿主裸金属输入（不可变，契约 §3.4 / NQ-3）', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, NETWORK_INTERFACE_A) })

    const wrapper = await mountDetailContent()

    expect(wrapper.find('[data-testid="open-edit-dialog"]').exists()).toBe(true)
    await openEditDialog(wrapper)

    // name / bare_metal_id 不在 PATCH 可变集内 → 表单不提供输入。
    expect(wrapper.find('[data-testid="nic-form-name"]').exists()).toBe(false)
    expect(wrapper.find('.network-interface-form__host-select').exists()).toBe(false)
    // 两个枚举下拉在表单中，且初值为当前记录的字面值。
    expect(wrapper.find('[data-testid="nic-form-technology-type"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nic-form-purpose"]').exists()).toBe(true)
    expect(findEnumSelect(wrapper, 'nic-form-technology-type').props('modelValue')).toBe(
      'Ethernet',
    )
    expect(findEnumSelect(wrapper, 'nic-form-purpose').props('modelValue')).toBe('Business')
  })

  it('修改枚举 → PATCH /api/network-interfaces/{id}：body 恰为两个可变枚举字段快照（契约 §3.4 / NQ-7）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, NETWORK_INTERFACE_A),
      patch: () =>
        jsonResponse(200, {
          ...NETWORK_INTERFACE_A,
          technology_type: 'InfiniBand',
          purpose: 'Compute',
        }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await findEnumSelect(wrapper, 'nic-form-technology-type').vm.$emit(
      'update:modelValue',
      'InfiniBand',
    )
    await findEnumSelect(wrapper, 'nic-form-purpose').vm.$emit('update:modelValue', 'Compute')
    await wrapper.find('[data-testid="nic-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/network-interfaces/12',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ technology_type: 'InfiniBand', purpose: 'Compute' }),
      }),
    )
  })

  it('保存成功（200）→ 关闭对话框并重新读取，展示新值', async () => {
    const updated = {
      ...NETWORK_INTERFACE_A,
      technology_type: 'RoCE',
      purpose: 'Storage',
      updated_at: '2026-09-17T12:00:00Z',
    }
    const mutable = { detail: () => jsonResponse(200, NETWORK_INTERFACE_A) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      patch: () => {
        mutable.detail = () => jsonResponse(200, updated)
        return jsonResponse(200, updated)
      },
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await findEnumSelect(wrapper, 'nic-form-technology-type').vm.$emit('update:modelValue', 'RoCE')
    await findEnumSelect(wrapper, 'nic-form-purpose').vm.$emit('update:modelValue', 'Storage')
    await wrapper.find('[data-testid="nic-form-submit"]').trigger('click')

    // 等待重新读取完成：新 updated_at 只会出现在重新读取后的详情内容中
    // （对话框内只有两个枚举，不会提前出现该值，避免对话框旧 DOM 造成的误判）。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('2026-09-17T12:00:00Z')
    })
    // 详情重新读取并展示服务端返回的新值。
    expect(wrapper.text()).toContain('RoCE')
    expect(wrapper.text()).toContain('Storage')
    // 请求序列：初始 GET → PATCH → 重新读取 GET。
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/network-interfaces/12')
  })

  it('400 VALIDATION_ERROR → 对话框内按 error.code 渲染字段级提示（details[].field）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, NETWORK_INTERFACE_A),
      patch: () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '与展示无关的校验文案',
            details: [
              { field: 'purpose', code: 'INVALID', message: '与展示无关的字段提示' },
            ],
          },
        }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="nic-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('purpose')
    // 详情内容保留，用户可修改后重试。
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.find('[data-testid="nic-form-submit"]').exists()).toBe(true)
  })

  it('404 NOT_FOUND（已被其他操作删除）→ 对话框内按 error.code 渲染固定文案，不解析 message', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, NETWORK_INTERFACE_A),
      patch: () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="nic-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain(
      '该网络接口不存在或已被删除',
    )
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，不渲染本地失败提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, NETWORK_INTERFACE_A),
      patch: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="nic-form-submit"]').trigger('click')

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
    const updated = {
      ...NETWORK_INTERFACE_A,
      purpose: 'DataTransfer',
      updated_at: '2026-09-17T13:00:00Z',
    }
    const mutable = { detail: () => jsonResponse(200, NETWORK_INTERFACE_A) }
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

    await findEnumSelect(wrapper, 'nic-form-purpose').vm.$emit(
      'update:modelValue',
      'DataTransfer',
    )
    await wrapper.find('[data-testid="nic-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="nic-form-submit"]').classes()).toContain('is-loading')
    })

    await wrapper.find('[data-testid="nic-form-submit"]').trigger('click')
    expect(patchCalls(fetchMock)).toBe(1)

    releasePatch()
    // 等待重新读取完成：新 updated_at 只会出现在重新读取后的详情内容中。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('2026-09-17T13:00:00Z')
    })
    expect(wrapper.text()).toContain('DataTransfer')
  })
})

// ---- 删除入口（DELETE，契约 §3.5） ----

/** 契约 §4.1：message 不构成契约；使用与展示无关的文案。 */
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

describe('NetworkInterfaceDetailPage 删除入口（T-FE-01 / AC-21）', () => {
  it('内容态存在删除入口（ElPopconfirm 二次确认），空闲时可触发（前端不预判，§21）', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, NETWORK_INTERFACE_A) })

    const wrapper = await mountDetailContent()

    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
    const deleteButton = wrapper.findAll('button').find((b) => b.text().trim() === '删除')
    expect(deleteButton).toBeDefined()
    expect(deleteButton!.attributes('disabled')).toBeUndefined()
  })

  it('未通过二次确认（确认框取消）→ 不发送 DELETE 请求', async () => {
    const fetchMock = stubDetailFetch({ detail: () => jsonResponse(200, NETWORK_INTERFACE_A) })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('cancel', new MouseEvent('click'))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.attributes('data-state')).toBe('content')
  })

  it('删除成功（204）→ 重新读取得到 404 → 进入既有独立 Not Found 态', async () => {
    const mutable = { detail: () => jsonResponse(200, NETWORK_INTERFACE_A) }
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
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/network-interfaces/12')
  })

  it('409 CONFLICT（ACTIVE_CHILDREN_EXIST）→ 保留详情内容并按 error.code 渲染冲突提示（不解析 message）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, NETWORK_INTERFACE_A),
      remove: () => jsonResponse(409, DELETE_CONFLICT_BODY),
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.text()).toContain('eth0')
    const alert = wrapper.find('[data-delete-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法删除网络接口')
    expect(alert.text()).toContain('活跃子资源')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
    // 失败后可重试：删除入口仍在。
    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
  })

  it('删除返回 404（已被其他操作删除）→ 同样进入独立 Not Found 态，不渲染删除失败提示', async () => {
    const mutable = { detail: () => jsonResponse(200, NETWORK_INTERFACE_A) }
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
    const mutable = { detail: () => jsonResponse(200, NETWORK_INTERFACE_A) }
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
