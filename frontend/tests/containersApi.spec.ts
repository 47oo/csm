import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  CONTAINER_CARRIER_TYPES,
  CONTAINER_OPTIONAL_FIELDS,
  createContainer,
  deleteContainer,
  getContainer,
  listContainers,
  updateContainer,
} from '../src/api/containers'
import { ApiError } from '../src/api/http'

/**
 * Container API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）与
 * 契约错误语义透传。契约依据：docs/api/f007-container.md（READY）。
 * fetch 全部桩替换，不触达真实后端。
 */

const CONTAINER_A = {
  id: 11,
  carrier_type: 'BARE_METAL',
  carrier_id: 3,
  name: 'web',
  image: 'registry/nginx:1.25',
  cpu: '8 vCPU',
  memory: '4G',
  owner: 'ops',
  created_at: '2026-09-18T10:00:00Z',
  updated_at: '2026-09-18T10:00:00Z',
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

describe('请求构造（契约 §4）', () => {
  it('listContainers 默认参数 → GET /api/containers（无载体查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [CONTAINER_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listContainers()

    expect(data).toEqual({ items: [CONTAINER_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/containers',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listContainers 显式分页 + 载体（BARE_METAL）→ 查询参数成对拼接 carrier_type 与 carrier_id（契约 §4.2）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listContainers({
      page: 2,
      page_size: 20,
      carrier: { carrier_type: 'BARE_METAL', carrier_id: 3 },
    })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/containers?page=2&page_size=20&carrier_type=BARE_METAL&carrier_id=3',
      expect.anything(),
    )
  })

  it('listContainers 载体（VIRTUAL_MACHINE）→ 同一成对参数形态（两种载体类型均成立，AC-26）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [CONTAINER_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listContainers({ carrier: { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 7 } })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/containers?carrier_type=VIRTUAL_MACHINE&carrier_id=7',
      expect.anything(),
    )
  })

  it('getContainer → GET /api/containers/{id}（规范路径，读写均走 id）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, CONTAINER_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getContainer(11)

    expect(data).toEqual(CONTAINER_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/containers/11',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('createContainer → POST /api/containers，JSON 请求体恰为载体对 + name + 可选字段（契约 §4.1 schema 封闭）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, { ...CONTAINER_A, id: 12 }))
    vi.stubGlobal('fetch', fetchMock)

    await createContainer({
      carrier_type: 'BARE_METAL',
      carrier_id: 3,
      name: 'web',
      image: 'registry/nginx:1.25',
      cpu: null,
    })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/containers',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          carrier_type: 'BARE_METAL',
          carrier_id: 3,
          name: 'web',
          image: 'registry/nginx:1.25',
          cpu: null,
        }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('updateContainer → PATCH /api/containers/{id}（部分更新，仅四字段；null 清空，契约 §4.4）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...CONTAINER_A, cpu: '16 vCPU', memory: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateContainer(11, { cpu: '16 vCPU', memory: null })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/containers/11',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ cpu: '16 vCPU', memory: null }),
      }),
    )
  })

  it('deleteContainer → DELETE /api/containers/{id}（写操作一律走 id；不发送请求体，契约 §4.5）', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteContainer(11)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/containers/11',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
    // 契约 §4.5：Request body 无，客户端不得发送 → 不携带 Content-Type。
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('R-CONTAINER-004 可选字段常量恰为四字段（image / cpu / memory / owner）', () => {
    expect([...CONTAINER_OPTIONAL_FIELDS]).toEqual(['image', 'cpu', 'memory', 'owner'])
  })

  it('载体类型封闭集合恰为 BARE_METAL / VIRTUAL_MACHINE（契约 §2；R-CONTAINER-002）', () => {
    expect([...CONTAINER_CARRIER_TYPES]).toEqual(['BARE_METAL', 'VIRTUAL_MACHINE'])
  })
})

describe('错误语义透传（契约 §5；api-conventions.md §5 / §6）', () => {
  it('getContainer 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §4.3）→ ApiError 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(getContainer(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('listContainers（载体过滤）404 NOT_FOUND（载体不存在 / 已删 / 类型与标识不一致，契约 §4.2）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(
      listContainers({ carrier: { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 999 } }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('listContainers Empty 语义（200 + items == []，契约 §4.2）→ 成功返回，不抛出', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 })),
    )

    await expect(listContainers()).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    })
  })

  it('createContainer 400 VALIDATION_ERROR（缺 name 等，契约 §4.1）→ 保留 details[].field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'name', message: '字段缺失' }],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createContainer({ carrier_type: 'BARE_METAL', carrier_id: 3, name: 'web' }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('name')
  })

  it('createContainer 409 CONFLICT（载体内活跃 name 重复，契约 §5.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: 'Container 名称已存在',
            details: [
              {
                field: 'name',
                code: 'DUPLICATE',
                message: '同一载体内已存在活跃的同名 Container',
              },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createContainer({ carrier_type: 'BARE_METAL', carrier_id: 3, name: 'web' }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.field).toBe('name')
    expect(err.details[0]?.code).toBe('DUPLICATE')
  })

  it('createContainer 404 NOT_FOUND（载体不存在 / 已删 / 类型与标识不一致，契约 §4.1 / NQ-2）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(
      createContainer({ carrier_type: 'BARE_METAL', carrier_id: 999, name: 'web' }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('deleteContainer 401 UNAUTHENTICATED（未认证，不改变任何数据）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
      ),
    )

    const err = await expectApiError(deleteContainer(11))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
