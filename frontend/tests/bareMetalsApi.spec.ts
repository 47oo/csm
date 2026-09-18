import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  BARE_METAL_STATUS_VALUES,
  createBareMetal,
  deleteBareMetal,
  getBareMetal,
  listBareMetals,
  updateBareMetal,
} from '../src/api/bareMetals'
import { ApiError } from '../src/api/http'

/**
 * BareMetal API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）与
 * 契约错误语义透传。契约依据：docs/api/f002-bare-metal.md（READY）。
 * fetch 全部桩替换，不触达真实后端。
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

describe('请求构造（契约 §3）', () => {
  it('listBareMetals 默认参数 → GET /api/bare-metals（无查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [BARE_METAL_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listBareMetals()

    expect(data).toEqual({ items: [BARE_METAL_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listBareMetals 显式分页 + clusterId → 查询参数拼接 cluster_id（契约 §3.2）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listBareMetals({ page: 2, page_size: 20, clusterId: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals?page=2&page_size=20&cluster_id=3',
      expect.anything(),
    )
  })

  it('listBareMetals 仅 clusterId → 只携带 cluster_id 查询参数', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [BARE_METAL_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listBareMetals({ clusterId: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals?cluster_id=3',
      expect.anything(),
    )
  })

  it('getBareMetal → GET /api/bare-metals/{id}（规范路径，写读均走 id）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, BARE_METAL_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getBareMetal(1)

    expect(data).toEqual(BARE_METAL_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals/1',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('createBareMetal → POST /api/bare-metals，JSON 请求体含必填字段与可选硬件字段', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(201, { ...BARE_METAL_A, id: 2, hostname: 'cn002' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createBareMetal({
      cluster_id: 3,
      hostname: 'cn002',
      vendor: 'Dell',
      gpu: null,
    })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ cluster_id: 3, hostname: 'cn002', vendor: 'Dell', gpu: null }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('updateBareMetal → PATCH /api/bare-metals/{id}（部分更新，含 status 与硬件字段 null 清空）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...BARE_METAL_A, status: 'ALLOC', updated_at: '2026-09-16T11:00:00Z' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateBareMetal(1, { status: 'ALLOC', memory: null })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals/1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ status: 'ALLOC', memory: null }),
      }),
    )
  })

  it('deleteBareMetal → DELETE /api/bare-metals/{id}（写操作一律走 id；不发送请求体，契约 §3.5）', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteBareMetal(1)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/bare-metals/1',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
    // 契约 §3.5：Request body 无，客户端不得发送 → 不携带 Content-Type。
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('状态封闭集合常量恰为契约四值（R-BM-003；UI 选项来源）', () => {
    expect([...BARE_METAL_STATUS_VALUES]).toEqual(['IDLE', 'ALLOC', 'DOWN', 'UNKNOWN'])
  })
})

describe('错误语义透传（契约 §8；api-conventions.md §5 / §6）', () => {
  it('getBareMetal 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §3.3）→ ApiError 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(getBareMetal(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('listBareMetals（clusterId 过滤）404 NOT_FOUND（父 Cluster 不存在或已删，契约 §3.2）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(listBareMetals({ clusterId: 999 }))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('listBareMetals Empty 语义（200 + items == []，契约 §9）→ 成功返回，不抛出', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 })),
    )

    await expect(listBareMetals()).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    })
  })

  it('createBareMetal 400 VALIDATION_ERROR（缺 hostname，契约 §3.1）→ 保留 details[].field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'hostname', message: '字段缺失' }],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createBareMetal({ cluster_id: 3, hostname: 'cn001' }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('hostname')
  })

  it('createBareMetal 409 CONFLICT（同 Cluster 活跃 hostname 重复，契约 §4.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '同一 Cluster 内 hostname 已存在',
            details: [
              { field: 'hostname', code: 'DUPLICATE', message: '同一 Cluster 内已存在活跃的同名 hostname' },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(createBareMetal({ cluster_id: 3, hostname: 'cn001' }))

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.field).toBe('hostname')
    expect(err.details[0]?.code).toBe('DUPLICATE')
  })

  it('createBareMetal 404 NOT_FOUND（引用不存在 / 已删 Cluster，契约 §3.1 / NQ-2）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(createBareMetal({ cluster_id: 999, hostname: 'cn001' }))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('deleteBareMetal 401 UNAUTHENTICATED（未认证，不改变任何数据）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
      ),
    )

    const err = await expectApiError(deleteBareMetal(1))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
