import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElPopconfirm } from 'element-plus'
import IpAddressRangeDetailPage from '../src/pages/IpAddressRangeDetailPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * IP 地址范围段详情页测试（F020）。
 *
 * 覆盖：404 独立 Not Found 态（与列表 Empty 可区分）、6 字段展示（时间不
 * 透明字符串；start_ip / end_ip 服务端规范化值原样展示）、无状态展示
 * （Q-002=B）、无 name / description（契约 §2 封闭）、start_ip / end_ip
 * 修正入口（PATCH：仅此两字段可编辑；cluster_id 不可编辑）、修改失败按
 * error.code 分支（400 / 404 / 409 OVERLAP / 401 / 防重复）、删除入口
 * （204 → Not Found 态 / 409 ACTIVE_CHILDREN_EXIST / 404 / 提交中防重复）。
 *
 * 响应体严格按 docs/api/f020-ip-address-range.md 构造（§2 资源表示 / §3.3
 * 读取 / §3.4 更新 / §3.5 删除 / §4 错误信封 / §9 Empty 与 Not Found）。
 */

const IP_ADDRESS_RANGE_A = {
  id: 7,
  cluster_id: 3,
  start_ip: '10.0.0.1',
  end_ip: '10.0.0.255',
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
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

function mountDetailPage(ipAddressRangeId = 7) {
  return mount(IpAddressRangeDetailPage, {
    props: { ipAddressRangeId },
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
    expect(wrapper.find('[data-testid="range-form-submit"]').exists()).toBe(true)
  })
}

function patchCalls(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(
    (call) => (call[1] as RequestInit | undefined)?.method === 'PATCH',
  ).length
}

describe('IpAddressRangeDetailPage 状态渲染', () => {
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

    resolveDetail(IP_ADDRESS_RANGE_A)
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })
  })

  it('成功 → 展示全部 6 字段（契约原样值，时间不透明字符串）；无状态字段 / 无 name（Q-002=B / 契约 §2 封闭）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, IP_ADDRESS_RANGE_A)))

    const wrapper = mountDetailPage()

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('content')
    })

    const text = wrapper.text()
    expect(text).toContain('IP 地址范围段详情')
    // 全部 6 字段：契约原样值，不做任何变换。
    expect(text).toContain('ID')
    expect(text).toContain('所属集群 ID')
    expect(text).toContain('3')
    expect(text).toContain('起始 IP')
    expect(text).toContain('10.0.0.1')
    expect(text).toContain('结束 IP')
    expect(text).toContain('10.0.0.255')
    expect(text).toContain('登记时间')
    expect(text).toContain('2026-09-20T10:00:00Z')
    expect(text).toContain('更新时间')
    // 范围段无状态（Q-002=B）：不渲染状态标签 / 状态行。
    expect(wrapper.find('[data-status]').exists()).toBe(false)
    // 无 name / description / 用途（契约 §2 字段封闭）。
    expect(text).not.toContain('名称')
    expect(text).not.toContain('用途')
    // 不暴露 deleted_at（契约 §2：字段集合封闭）。
    expect(text).not.toContain('deleted_at')
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
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('.el-descriptions').exists()).toBe(false)
    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(false)
    expect(wrapper.text()).not.toContain('暂无 IP 地址范围段')
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
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, IP_ADDRESS_RANGE_A)))

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

describe('IpAddressRangeDetailPage 编辑入口（PATCH，契约 §3.4）', () => {
  it('内容态存在「编辑」入口；表单仅 start_ip / end_ip 输入，不含归属集群选择（不可变，契约 §3.4）', async () => {
    stubDetailFetch({ detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A) })

    const wrapper = await mountDetailContent()

    expect(wrapper.find('[data-testid="open-edit-dialog"]').exists()).toBe(true)
    await openEditDialog(wrapper)

    // cluster_id 不在 PATCH 可变集内 → 表单不提供选择。
    expect(wrapper.find('.ip-address-range-form__cluster-select').exists()).toBe(false)
    // start_ip / end_ip 输入在表单中，且初值为当前记录的契约原样值。
    expect(
      (wrapper.find('[data-testid="range-form-start-ip"]').element as HTMLInputElement).value,
    ).toBe('10.0.0.1')
    expect(
      (wrapper.find('[data-testid="range-form-end-ip"]').element as HTMLInputElement).value,
    ).toBe('10.0.0.255')
  })

  it('修改范围 → PATCH /api/ip-address-ranges/{id}：body 恰为 {start_ip, end_ip}（可变字段封闭，契约 §3.4）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      patch: () => jsonResponse(200, { ...IP_ADDRESS_RANGE_A, end_ip: '10.0.1.255' }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.1.255')
    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/ip-address-ranges/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ start_ip: '10.0.0.1', end_ip: '10.0.1.255' }),
      }),
    )
  })

  it('§21 不预判：start > end、非法 IPv4、与同 Cluster 其它范围重叠的取值均原样提交（服务端裁决）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      patch: () => jsonResponse(400, {
        error: {
          code: 'VALIDATION_ERROR',
          message: '与展示无关的校验文案',
          details: [{ field: 'start_ip', code: 'INVALID', message: '与展示无关的字段提示' }],
        },
      }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    // start > end：前端不预判（契约 §3.4 由服务端 400 裁决）。
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.0.1.9')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.1.1')
    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')
    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })

    // 非法 IPv4：原样提交，不做格式校验 / 归一化。
    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('abc')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.0.256')
    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')
    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(2)
    })

    const bodies = fetchMock.mock.calls
      .filter((call) => (call[1] as RequestInit | undefined)?.method === 'PATCH')
      .map((call) => JSON.parse((call[1] as RequestInit).body as string))
    expect(bodies).toEqual([
      { start_ip: '10.0.1.9', end_ip: '10.0.1.1' },
      { start_ip: 'abc', end_ip: '10.0.0.256' },
    ])
  })

  it('保存成功（200）→ 关闭对话框并重新读取，展示新值；cluster_id / created_at 不变', async () => {
    const updated = {
      ...IP_ADDRESS_RANGE_A,
      start_ip: '10.1.0.1',
      end_ip: '10.1.0.254',
      updated_at: '2026-09-20T12:00:00Z',
    }
    const mutable = { detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      patch: () => {
        mutable.detail = () => jsonResponse(200, updated)
        return jsonResponse(200, updated)
      },
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="range-form-start-ip"]').setValue('10.1.0.1')
    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.1.0.254')
    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')

    // 等待重新读取完成：新 updated_at 只会出现在重新读取后的详情内容中。
    await waitForUi(() => {
      expect(wrapper.text()).toContain('2026-09-20T12:00:00Z')
    })
    // 详情重新读取并展示服务端返回的新值；不可变字段保持。
    expect(wrapper.text()).toContain('10.1.0.1')
    expect(wrapper.text()).toContain('10.1.0.254')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('2026-09-20T10:00:00Z')
    // 请求序列：初始 GET → PATCH → 重新读取 GET。
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2]![0]).toBe('/api/ip-address-ranges/7')
  })

  it('400 VALIDATION_ERROR → 对话框内按 error.code 渲染字段级提示（details[].field）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      patch: () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '与展示无关的校验文案',
            details: [{ field: 'end_ip', code: 'INVALID', message: '与展示无关的字段提示' }],
          },
        }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="VALIDATION_ERROR"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="VALIDATION_ERROR"]')
    expect(alert.text()).toContain('请求校验失败')
    expect(alert.text()).toContain('end_ip')
    // 详情内容保留，用户可修改后重试。
    expect(wrapper.attributes('data-state')).toBe('content')
  })

  it('409 CONFLICT + OVERLAP → 「与该 Cluster 已有范围段重叠」（不解析 message）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      patch: () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '与展示无关的冲突文案',
            details: [{ row: null, field: null, code: 'OVERLAP', message: '与展示无关的重叠提示' }],
          },
        }),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="range-form-end-ip"]').setValue('10.0.5.255')
    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="CONFLICT"]')
    expect(alert.text()).toContain('与该 Cluster 已有范围段重叠')
    expect(wrapper.text()).not.toContain('与展示无关的冲突文案')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(wrapper.find('[data-testid="range-form-submit"]').exists()).toBe(true)
  })

  it('404 NOT_FOUND（目标不存在或已删，契约 §3.4）→ 「该范围段不存在或已被删除」', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      patch: () => jsonResponse(404, NOT_FOUND_BODY),
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')

    await waitForUi(() => {
      expect(wrapper.find('[data-error-code="NOT_FOUND"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-error-code="NOT_FOUND"]')
    expect(alert.text()).toContain('该范围段不存在或已被删除')
    // 对话框保持打开（失败不关闭，用户可修改后重试）。
    expect(wrapper.find('[data-testid="range-form-submit"]').exists()).toBe(true)
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，对话框内不渲染本地失败提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      patch: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')

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
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      patch: async () => {
        await patchGate
        return jsonResponse(200, IP_ADDRESS_RANGE_A)
      },
    })

    const wrapper = await mountDetailContent()
    await openEditDialog(wrapper)

    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')
    await waitForUi(() => {
      expect(patchCalls(fetchMock)).toBe(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-testid="range-form-submit"]').classes()).toContain('is-loading')
    })

    // 连点不发出第二个 PATCH。
    await wrapper.find('[data-testid="range-form-submit"]').trigger('click')
    expect(patchCalls(fetchMock)).toBe(1)

    releasePatch()
    await waitForUi(() => {
      expect(wrapper.text()).toContain('2026-09-20T10:00:00Z')
    })
  })
})

// ---- 删除入口（DELETE /api/ip-address-ranges/{id}，契约 §3.5） ----

describe('IpAddressRangeDetailPage 删除入口（契约 §3.5）', () => {
  it('内容态存在「删除」入口（ElPopconfirm 二次确认）；未确认不发送 DELETE', async () => {
    const fetchMock = stubDetailFetch({ detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A) })

    const wrapper = await mountDetailContent()

    expect(wrapper.findComponent(ElPopconfirm).exists()).toBe(true)
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '删除')!
      .trigger('click')
    // 仅点击删除按钮（未通过二次确认）→ 不发送 DELETE。
    expect(
      fetchMock.mock.calls.filter(
        (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
      ).length,
    ).toBe(0)
  })

  it('二次确认通过 → DELETE /api/ip-address-ranges/{id}（不发送请求体，契约 §3.5）', async () => {
    const fetchMock = stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      remove: () => noContent(),
    })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))

    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.filter(
          (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
        ).length,
      ).toBe(1)
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/ip-address-ranges/7',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
  })

  it('删除成功（204）→ 重新读取 → 404 → 独立 Not Found 态', async () => {
    const mutable = { detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A) }
    stubDetailFetch({
      detail: () => mutable.detail(),
      remove: () => {
        mutable.detail = () => jsonResponse(404, NOT_FOUND_BODY)
        return noContent()
      },
    })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
  })

  it('409 CONFLICT + ACTIVE_CHILDREN_EXIST（范围内仍有活跃 IP）→ 渲染「该范围内仍有活跃 IP」（不解析 message）', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      remove: () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '与展示无关的后端冲突文案',
            details: [
              {
                row: null,
                field: null,
                code: 'ACTIVE_CHILDREN_EXIST',
                message: '与展示无关的子项文案',
              },
            ],
          },
        }),
    })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))

    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code="CONFLICT"]').exists()).toBe(true)
    })
    const alert = wrapper.find('[data-delete-error-code="CONFLICT"]')
    expect(alert.text()).toContain('无法删除IP 地址范围段')
    expect(alert.text()).toContain('该范围内仍有活跃 IP，无法删除')
    expect(wrapper.text()).not.toContain('与展示无关的后端冲突文案')
    // 详情内容保留（无部分写入；409 不改变目标行）。
    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.text()).toContain('10.0.0.1')
  })

  it('404 NOT_FOUND（重复删除）→ 与成功同构：重新读取 → Not Found 态，不渲染删除失败提示', async () => {
    const mutable = { detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A) }
    stubDetailFetch({
      detail: () => mutable.detail(),
      remove: () => {
        mutable.detail = () => jsonResponse(404, NOT_FOUND_BODY)
        return jsonResponse(404, NOT_FOUND_BODY)
      },
    })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))

    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
    expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
  })

  it('401 UNAUTHENTICATED → 触发既有全局会话失效处理，本页不渲染删除失败提示', async () => {
    stubDetailFetch({
      detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A),
      remove: () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
    })
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))

    await waitForUi(() => {
      expect(unauthenticated).toHaveBeenCalledTimes(1)
    })
    await waitForUi(() => {
      expect(wrapper.find('[data-delete-error-code]').exists()).toBe(false)
    })
  })

  it('提交中：删除按钮 Loading，重复确认不产生第二个 DELETE（禁止重复提交）', async () => {
    let releaseDelete!: () => void
    const deleteGate = new Promise<void>((resolve) => {
      releaseDelete = resolve
    })
    const mutable = { detail: () => jsonResponse(200, IP_ADDRESS_RANGE_A) }
    const fetchMock = stubDetailFetch({
      detail: () => mutable.detail(),
      remove: async () => {
        await deleteGate
        mutable.detail = () => jsonResponse(404, NOT_FOUND_BODY)
        return noContent()
      },
    })

    const wrapper = await mountDetailContent()

    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))
    await waitForUi(() => {
      expect(
        fetchMock.mock.calls.filter(
          (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
        ).length,
      ).toBe(1)
    })

    const deleteButton = wrapper.findAll('button').find((b) => b.text() === '删除')
    expect(deleteButton).toBeDefined()
    await waitForUi(() => {
      expect(deleteButton!.classes()).toContain('is-loading')
    })

    // 重复确认不产生第二个 DELETE。
    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))
    expect(
      fetchMock.mock.calls.filter(
        (call) => (call[1] as RequestInit | undefined)?.method === 'DELETE',
      ).length,
    ).toBe(1)

    releaseDelete()
    await waitForUi(() => {
      expect(wrapper.attributes('data-state')).toBe('not-found')
    })
  })
})
