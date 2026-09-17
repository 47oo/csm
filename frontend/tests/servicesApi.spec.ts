import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  SERVICE_CARRIER_TYPES,
  SERVICE_OPTIONAL_FIELDS,
  createService,
  deleteService,
  getService,
  listServices,
  updateService,
} from '../src/api/services'
import { ApiError } from '../src/api/http'

/**
 * Service API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）与
 * 契约错误语义透传。契约依据：docs/api/f008-service.md（READY）。
 * fetch 全部桩替换，不触达真实后端。
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
  it('listServices 默认参数 → GET /api/services（无载体查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [SERVICE_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listServices()

    expect(data).toEqual({ items: [SERVICE_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/services',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listServices 显式分页 + 载体（BARE_METAL）→ 查询参数成对拼接 carrier_type 与 carrier_id（契约 §4.2）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listServices({
      page: 2,
      page_size: 20,
      carrier: { carrier_type: 'BARE_METAL', carrier_id: 3 },
    })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/services?page=2&page_size=20&carrier_type=BARE_METAL&carrier_id=3',
      expect.anything(),
    )
  })

  it.each(['VIRTUAL_MACHINE', 'CONTAINER'] as const)(
    'listServices 载体（%s）→ 同一成对参数形态（三种载体类型均成立，AC-31）',
    async (carrierType) => {
      const fetchMock = vi.fn(async () =>
        jsonResponse(200, { items: [SERVICE_A], total: 1, page: 1, page_size: 50 }),
      )
      vi.stubGlobal('fetch', fetchMock)

      await listServices({ carrier: { carrier_type: carrierType, carrier_id: 7 } })

      expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
        `/api/services?carrier_type=${carrierType}&carrier_id=7`,
        expect.anything(),
      )
    },
  )

  it('getService → GET /api/services/{id}（规范路径，读写均走 id）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SERVICE_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getService(7)

    expect(data).toEqual(SERVICE_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/services/7',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('createService → POST /api/services，JSON 请求体恰为 name + carriers + 可选字段（契约 §4.1 schema 封闭）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, { ...SERVICE_A, id: 8 }))
    vi.stubGlobal('fetch', fetchMock)

    await createService({
      name: 'mon',
      carriers: [
        { carrier_type: 'BARE_METAL', carrier_id: 3 },
        { carrier_type: 'CONTAINER', carrier_id: 11 },
      ],
      service_type: '自研',
      port: '8080-8090',
    })

    // 客户端原样传递调用方给出的字段；未提供的可选字段不出现在请求体中
    //（由服务端存为 null，契约 §4.1）。
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
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
          port: '8080-8090',
        }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('updateService → PATCH /api/services/{id}（部分更新，仅 6 字段；null 清空，契约 §4.4）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...SERVICE_A, port: '8080', owner: 'ops2' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateService(7, { port: '8080', owner: 'ops2', description: null })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/services/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ port: '8080', owner: 'ops2', description: null }),
      }),
    )
  })

  it('deleteService → DELETE /api/services/{id}（写操作一律走 id；不发送请求体，契约 §4.5）', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteService(7)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/services/7',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
    // 契约 §4.5：Request body 无，客户端不得发送 → 不携带 Content-Type。
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('6 个可选字段常量恰为 service_type / url / port / protocol / owner / description（契约 §2）', () => {
    expect([...SERVICE_OPTIONAL_FIELDS]).toEqual([
      'service_type',
      'url',
      'port',
      'protocol',
      'owner',
      'description',
    ])
  })

  it('载体类型封闭集合恰为 BARE_METAL / VIRTUAL_MACHINE / CONTAINER（契约 §2；R-SVC-002）', () => {
    expect([...SERVICE_CARRIER_TYPES]).toEqual(['BARE_METAL', 'VIRTUAL_MACHINE', 'CONTAINER'])
  })
})

describe('错误语义透传（契约 §5；api-conventions.md §5 / §6）', () => {
  it('getService 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §4.3）→ ApiError 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(getService(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('listServices（载体过滤）404 NOT_FOUND（载体不存在 / 已删 / 类型与标识不一致，契约 §4.2）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(
      listServices({ carrier: { carrier_type: 'CONTAINER', carrier_id: 999 } }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('listServices Empty 语义（200 + items == []，契约 §4.2）→ 成功返回，不抛出', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 })),
    )

    await expect(listServices()).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    })
  })

  it('createService 400 VALIDATION_ERROR（同一请求内重复载体，契约 §4.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'carriers', code: 'DUPLICATE', message: '重复载体' }],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createService({
        name: 'mon',
        carriers: [
          { carrier_type: 'BARE_METAL', carrier_id: 3 },
          { carrier_type: 'BARE_METAL', carrier_id: 3 },
        ],
      }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('carriers')
    expect(err.details[0]?.code).toBe('DUPLICATE')
  })

  it('createService 409 CONFLICT（全局活跃 name 重复，契约 §5.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: 'Service 名称已存在',
            details: [
              { field: 'name', code: 'DUPLICATE', message: '已存在活跃的同名 Service' },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createService({ name: 'mon', carriers: [{ carrier_type: 'BARE_METAL', carrier_id: 3 }] }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.field).toBe('name')
    expect(err.details[0]?.code).toBe('DUPLICATE')
  })

  it('createService 404 NOT_FOUND（任一载体不存在 / 已删 / 类型与标识不一致，契约 §4.1）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(
      createService({
        name: 'mon',
        carriers: [
          { carrier_type: 'BARE_METAL', carrier_id: 3 },
          { carrier_type: 'VIRTUAL_MACHINE', carrier_id: 999 },
        ],
      }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('updateService 400 VALIDATION_ERROR（含不可变字段，契约 §4.4）→ 保留 details[].field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'name', code: 'INVALID', message: '不可变字段' }],
          },
        }),
      ),
    )

    const err = await expectApiError(updateService(7, { owner: 'ops2' }))

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('name')
  })

  it('deleteService 401 UNAUTHENTICATED（未认证，不改变任何数据）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
      ),
    )

    const err = await expectApiError(deleteService(7))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
