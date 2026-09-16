import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPopconfirm } from 'element-plus'
import VirtualMachineDetailPage from '../src/pages/VirtualMachineDetailPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * 虚拟机详情页测试（T-FE-01 / AC-32）。
 *
 * 覆盖：404 独立 Not Found 态（与列表 Empty 可区分）、全部字段展示（R-VM-006
 * 六字段 null 渲染「—」）、无状态展示（Q-002=B）、可选字段修改入口（PATCH：
 * 仅六字段；name / bare_metal_id 不可编辑）、修改失败按 error.code 分支
 * （400 / 404 / 401）、删除入口（204 → Not Found 态 / 409 / 404 / 提交中防重复）。
 *
 * 响应体严格按 docs/api/f006-virtual-machine.md 构造（§2 资源表示 / §3.3 读取 /
 * §3.4 更新 / §3.5 删除 / §4 错误信封 / §9 Empty 与 Not Found）。
 */

const VIRTUAL_MACHINE_NULLS = {
  id: 7,
  bare_metal_id: 3,
  name: 'vm1',
  cpu: null,
  memory: null,
  disk: null,
  os: null,
  hypervisor: null,
  owner: null,
  created_at: '2026-09-16T10:00:00Z',
  updated_at: '2026-09-16T10:00:00Z',
}

const VIRTUAL_MACHINE_FULL = {
  ...VIRTUAL_MACHINE_NULLS,
  cpu: '8 vCPU',
  memory: '32 GB',
  disk: '500 GB',
  os: 'Ubuntu 22.04',
  hypervisor: 'PVE',
  owner: 'ops',
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

function mountDetailPage(virtualMachineId = 7) {
  return mount(VirtualMachineDetailPage, {
    props: { virtualMachineId },
    global: { plugins: [ElementPlus] },
  })
}

/**
 * vi.waitFor 包装：全量并行负载下 el-dialog 挂载 / 异步完成偶发超过 vi.waitFor
 * 默认 1s（单文件运行稳定），统一放宽到 5s；不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 5000 })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('VirtualMachineDetailPage 状态渲染', () => {
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

    resolveDetail(VIRTUAL_MACHINE_NULLS)
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })
  })

  it('成功（六字段全 null）→ 展示全部 11 字段，null 渲染「—」（契约 §2：返回 null 而非省略）；无状态字段（Q-002=B）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, VIRTUAL_MACHINE_NULLS)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('虚拟机详情')
    // 身份 / 关系 / 时间字段：契约原样值，不做任何变换。
    expect(text).toContain('宿主裸金属 ID')
    expect(text).toContain('3')
    expect(text).toContain('vm1')
    expect(text).toContain('2026-09-16T10:00:00Z')
    // R-VM-006 六字段 null → 「—」（逐行断言 label → content 对应）。
    const rows = wrapper.findAll('.el-descriptions table tbody tr')
    const contentOf = (label: string): string => {
      const row = rows.find((r) => r.find('.el-descriptions__label').text() === label)
      expect(row, `期望存在字段行「${label}」`).toBeDefined()
      return row!.find('.el-descriptions__content').text()
    }
    for (const label of ['CPU', '内存', '磁盘', '操作系统', 'Hypervisor', '负责人']) {
      expect(contentOf(label)).toBe('—')
    }
    // VM 无状态（Q-002=B）：不渲染状态标签 / 状态行。
    expect(wrapper.find('[data-status]').exists()).toBe(false)
    expect(text).not.toContain('状态')
    // 不暴露 deleted_at / cluster_id（契约 §2：字段集合封闭）。
    expect(text).not.toContain('deleted_at')
    expect(text).not.toContain('cluster_id')
    expect(text).not.toContain('集群')
  })

  it('成功（六字段已登记）→ 原样展示纯文本值', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, VIRTUAL_MACHINE_FULL)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('8 vCPU')
    expect(text).toContain('32 GB')
    expect(text).toContain('500 GB')
    expect(text).toContain('Ubuntu 22.04')
    expect(text).toContain('PVE')
    expect(text).toContain('ops')
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
    expect(wrapper.text()).not.toContain('暂无虚拟机')
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
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, VIRTUAL_MACHINE_NULLS)))

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

// ---- 可选字段修改入口（PATCH，契约 §3.4） ----

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
    expect(wrapper.find('[data-testid="vm-form-submit"]').exists()).toBe(true)
  })
}

function patchCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
  ).length
}

describe('VirtualMachineDetailPage 编辑入口（PATCH，T-FE-01 / AC-19）', () => {
  it('内容态存在「编辑」入口；表单不含 name / 宿主裸金属输入（不可变，契约 §3.4 / NQ-1）', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) })

    const wrapper = await mountDetailContent()

    expect(wrapper.find('[data-testid="open-edit-dialog"]').exists()).toBe(true)
    await openEditDialog(wrapper)

    // name / bare_metal_id 不在 PATCH 可变集内 → 表单不提供输入。
    expect(wrapper.find('[data-testid="vm-form-name"]').exists()).toBe(false)
    expect(wrapper.find('.virtual-machine-form__host-select').exists()).toBe(false)
    // 六字段在表单中。
    expect(wrapper.find('[data-testid="vm-form-cpu"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="vm-form-owner"]').exists()).toBe(true)
  })

  it('修改可选字段 → PATCH /api/virtual-machines/{id}：body 为六字段快照（null → null，契约 §3.4）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, VIRTUAL_MACHINE_FULL),
      patch: () => jsonResponse(200, { ...VIRTUAL_MACHINE_FULL, cpu: '16 vCPU' }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="vm-form-cpu"]').setValue('16 vCPU')
    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/virtual-machines/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          cpu: '16 vCPU',
          memory: '32 GB',
          disk: '500 GB',
          os: 'Ubuntu 22.04',
          hypervisor: 'PVE',
          owner: 'ops',
        }),
      }),
    )
  })

  it('清空可选字段 → 提交 null（契约 §3.4：显式 null 表示清空）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, VIRTUAL_MACHINE_FULL),
      patch: () => jsonResponse(200, { ...VIRTUAL_MACHINE_FULL, os: null }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="vm-form-os"]').setValue('')
    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    const body = JSON.parse(
      (fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
      )![1] as RequestInit).body as string,
    )
    expect(body.os).toBeNull()
    expect(body.cpu).toBe('8 vCPU')
    // PATCH 可变字段封闭为六字段：不含 name / bare_metal_id / id / status。
    expect(body.name).toBeUndefined()
    expect(body.bare_metal_id).toBeUndefined()
    expect(body.id).toBeUndefined()
    expect(body.status).toBeUndefined()
  })

  it('保存成功（200）→ 关闭对话框并重新读取，展示新值', async () => {
    const updated = {
      ...VIRTUAL_MACHINE_NULLS,
      owner: 'ops2',
      updated_at: '2026-09-16T12:00:00Z',
    }
    const mutable = { detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      patch: () => {
        mutable.detail = () => jsonResponse(200, updated)
        return jsonResponse(200, updated)
      },
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="vm-form-owner"]').setValue('ops2')
    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')

    // 详情重新读取并展示服务端返回的新值。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('ops2')
    })
    expect(wrapper.text()).toContain('2026-09-16T12:00:00Z')
    // 请求序列：初始 GET → PATCH → 重新读取 GET。
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/virtual-machines/7')
  })

  it('400 VALIDATION_ERROR（含不可变字段等，契约 §3.4）→ 对话框内按 error.code 渲染字段级提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS),
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

    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('name')
    // 详情内容保留，用户可修改后重试。
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.find('[data-testid="vm-form-submit"]').exists()).toBe(true)
  })

  it('404 NOT_FOUND（已被其他操作删除）→ 对话框内按 error.code 渲染固定文案，不解析 message', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS),
      patch: () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    expect(wrapper.find('[data-error-code="NOT_FOUND"]').text()).toContain(
      '该虚拟机不存在或已被删除',
    )
    expect(wrapper.text()).not.toContain('与展示无关的未找到文案')
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，不渲染本地失败提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS),
      patch: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')

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
    const updated = { ...VIRTUAL_MACHINE_NULLS, owner: 'ops2' }
    const mutable = { detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) }
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

    await wrapper.find('[data-testid="vm-form-owner"]').setValue('ops2')
    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="vm-form-submit"]').classes()).toContain('is-loading')
    })

    await wrapper.find('[data-testid="vm-form-submit"]').trigger('click')
    expect(patchCalls(fetchMock)).toBe(1)

    releasePatch()
    await waitForUi(() => {
      expect(wrapper.text()).toContain('ops2')
    })
  })
})

// ---- 删除入口（DELETE，契约 §3.5） ----

/** 契约 §4.2：message 不构成契约；使用与展示无关的文案。 */
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

describe('VirtualMachineDetailPage 删除入口（T-FE-01 / AC-21）', () => {
  it('内容态存在删除入口（ElPopconfirm 二次确认），空闲时可触发（前端不预判，§21）', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) })

    const wrapper = await mountDetailContent()

    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
    const deleteButton = wrapper.findAll('button').find((b) => b.text().trim() === '删除')
    expect(deleteButton).toBeDefined()
    expect(deleteButton!.attributes('disabled')).toBeUndefined()
  })

  it('未通过二次确认（确认框取消）→ 不发送 DELETE 请求', async () => {
    const fetchMock = stubDetailFetch({ detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('cancel', new MouseEvent('click'))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.attributes('data-state')).toBe('content')
  })

  it('删除成功（204）→ 重新读取得到 404 → 进入既有独立 Not Found 态', async () => {
    const mutable = { detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) }
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
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/virtual-machines/7')
  })

  it('409 CONFLICT → 保留详情内容并按 error.code 渲染冲突提示（不解析 message）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS),
      remove: () => jsonResponse(409, DELETE_CONFLICT_BODY),
    })

    const wrapper = await mountDetailContent()

    confirmDelete(wrapper)

    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.text()).toContain('vm1')
    const alert = wrapper.find('[data-delete-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法删除虚拟机')
    expect(alert.text()).toContain('活跃子资源')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
    // 失败后可重试：删除入口仍在。
    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
  })

  it('删除返回 404（已被其他操作删除）→ 同样进入独立 Not Found 态，不渲染删除失败提示', async () => {
    const mutable = { detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) }
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
    const mutable = { detail: () => jsonResponse(200, VIRTUAL_MACHINE_NULLS) }
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
