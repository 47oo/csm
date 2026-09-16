import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  PURPOSE_OPTIONS,
  TECHNOLOGY_TYPE_OPTIONS,
  createNetworkInterface,
  deleteNetworkInterface,
  getNetworkInterface,
  listNetworkInterfaces,
  updateNetworkInterface,
} from '../src/api/networkInterfaces'
import { ApiError } from '../src/api/http'

/**
 * NetworkInterface API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）、
 * 枚举选项常量与契约错误语义透传。契约依据：docs/api/f004-network-interface.md
 * （READY）。fetch 全部桩替换，不触达真实后端。
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

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 捕获 promise 的 reject 结果，断言其为 ApiError 并返回。 */
async function expectApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (err) {
    if (err instanceof ApiError) return err
    throw new Error(`期望抛出 ApiError，实际抛出：${String(err)}`)
  }
  throw new Error('期望 promise 以 ApiError reject，实际成功返回')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('枚举选项常量（契约 §1.5 / R-NIC-001 / R-NIC-002）', () => {
  it('TECHNOLOGY_TYPE_OPTIONS 恰为四个封闭取值（Ethernet / InfiniBand / RoCE / Other）', () => {
    expect([...TECHNOLOGY_TYPE_OPTIONS]).toEqual(['Ethernet', 'InfiniBand', 'RoCE', 'Other'])
  })

  it('PURPOSE_OPTIONS 恰为七个封闭取值（BMC / Management / Business / Compute / Storage / DataTransfer / Other）', () => {
    expect([...PURPOSE_OPTIONS]).toEqual([
      'BMC',
      'Management',
      'Business',
      'Compute',
      'Storage',
      'DataTransfer',
      'Other',
    ])
  })
})

describe('请求构造（契约 §3）', () => {
  it('listNetworkInterfaces 默认参数 → GET /api/network-interfaces（无查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [NETWORK_INTERFACE_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listNetworkInterfaces()

    expect(data).toEqual({ items: [NETWORK_INTERFACE_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/network-interfaces',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listNetworkInterfaces 显式分页 + bareMetalId → 查询参数拼接 bare_metal_id（契约 §3.2）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listNetworkInterfaces({ page: 2, page_size: 20, bareMetalId: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/network-interfaces?page=2&page_size=20&bare_metal_id=3',
      expect.anything(),
    )
  })

  it('listNetworkInterfaces 仅 bareMetalId → 只携带 bare_metal_id 查询参数', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [NETWORK_INTERFACE_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listNetworkInterfaces({ bareMetalId: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/network-interfaces?bare_metal_id=3',
      expect.anything(),
    )
  })

  it('getNetworkInterface → GET /api/network-interfaces/{id}（规范路径，写读均走 id；无 by-name）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, NETWORK_INTERFACE_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getNetworkInterface(12)

    expect(data).toEqual(NETWORK_INTERFACE_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/network-interfaces/12',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('createNetworkInterface → POST /api/network-interfaces，JSON 请求体恰为四字段（契约 §3.1 schema 封闭）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, NETWORK_INTERFACE_A))
    vi.stubGlobal('fetch', fetchMock)

    await createNetworkInterface({
      bare_metal_id: 3,
      name: 'eth0',
      technology_type: 'Ethernet',
      purpose: 'Business',
    })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/network-interfaces',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          bare_metal_id: 3,
          name: 'eth0',
          technology_type: 'Ethernet',
          purpose: 'Business',
        }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('updateNetworkInterface → PATCH /api/network-interfaces/{id}（仅两个可变枚举字段，契约 §3.4 / NQ-7）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, {
        ...NETWORK_INTERFACE_A,
        technology_type: 'InfiniBand',
        purpose: 'Compute',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateNetworkInterface(12, { technology_type: 'InfiniBand', purpose: 'Compute' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/network-interfaces/12',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ technology_type: 'InfiniBand', purpose: 'Compute' }),
      }),
    )
  })

  it('deleteNetworkInterface → DELETE /api/network-interfaces/{id}（写操作一律走 id；不发送请求体，契约 §3.5）', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteNetworkInterface(12)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/network-interfaces/12',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
    // 契约 §3.5：Request body 无，客户端不得发送 → 不携带 Content-Type。
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })
})

describe('错误语义透传（契约 §8；api-conventions.md §5 / §6）', () => {
  it('getNetworkInterface 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §3.3）→ ApiError 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(getNetworkInterface(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('listNetworkInterfaces（bareMetalId 过滤）404 NOT_FOUND（宿主不存在或已删，契约 §3.2）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(listNetworkInterfaces({ bareMetalId: 999 }))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('listNetworkInterfaces Empty 语义（200 + items == []，契约 §9）→ 成功返回，不抛出', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 })),
    )

    await expect(listNetworkInterfaces()).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    })
  })

  it('createNetworkInterface 400 VALIDATION_ERROR（非法枚举，契约 §3.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [
              { field: 'technology_type', code: 'INVALID', message: '非法取值' },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createNetworkInterface({
        bare_metal_id: 3,
        name: 'eth0',
        // 类型断言仅为通过编译：非法值直接透传给服务端裁决（前端不校验）。
        technology_type: 'FibreChannel' as never,
        purpose: 'Business',
      }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('technology_type')
    expect(err.details[0]?.code).toBe('INVALID')
  })

  it('createNetworkInterface 404 NOT_FOUND（引用不存在 / 已删宿主，契约 §3.1 / NQ-5）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(
      createNetworkInterface({
        bare_metal_id: 999,
        name: 'eth0',
        technology_type: 'Ethernet',
        purpose: 'Business',
      }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('deleteNetworkInterface 409 CONFLICT（活跃子资源，契约 §3.5 / §4.1）→ 保留 details[].code（当前不可达，F005 触发）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '父资源存在活跃子资源，无法删除',
            details: [
              { row: null, field: null, code: 'ACTIVE_CHILDREN_EXIST', message: '资源仍存在活跃子资源' },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(deleteNetworkInterface(12))

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('ACTIVE_CHILDREN_EXIST')
  })

  it('deleteNetworkInterface 401 UNAUTHENTICATED（未认证，不改变任何数据）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
      ),
    )

    const err = await expectApiError(deleteNetworkInterface(12))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
