import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createCluster,
  getCluster,
  getClusterByName,
  listClusters,
  updateCluster,
} from '../src/api/clusters'
import { ApiError } from '../src/api/http'

/**
 * Cluster API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）与
 * 契约错误语义透传。契约依据：docs/api/f001-cluster.md（READY）。
 * fetch 全部桩替换，不触达真实后端。
 */

const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
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
  it('listClusters 默认参数 → GET /api/clusters（无查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listClusters()

    expect(data).toEqual({ items: [CLUSTER_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listClusters 显式分页 → 查询参数拼接', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listClusters({ page: 2, page_size: 20 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters?page=2&page_size=20',
      expect.anything(),
    )
  })

  it('getCluster → GET /api/clusters/{id}（规范路径）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, CLUSTER_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getCluster(1)

    expect(data).toEqual(CLUSTER_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters/1',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('getClusterByName → GET /api/clusters/by-name/{name}，中文名按 RFC 3986 百分号编码（UTF-8，契约 §3.4）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, CLUSTER_A))
    vi.stubGlobal('fetch', fetchMock)

    await getClusterByName('高性能计算集群-A')

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters/by-name/%E9%AB%98%E6%80%A7%E8%83%BD%E8%AE%A1%E7%AE%97%E9%9B%86%E7%BE%A4-A',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('getClusterByName 不 trim、不做大小写折叠或归一化（契约 §3.4 / §7）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expectApiError(getClusterByName(' Cluster-A '))

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters/by-name/%20Cluster-A%20',
      expect.anything(),
    )
  })

  it('createCluster → POST /api/clusters，JSON 请求体仅含 name', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(201, { ...CLUSTER_A, id: 2, name: 'cluster-b' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createCluster({ name: 'cluster-b' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'cluster-b' }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('updateCluster → PATCH /api/clusters/{id}（写操作一律走 id，契约 §3.5）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...CLUSTER_A, name: 'cluster-b', updated_at: '2026-09-16T10:00:00Z' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateCluster(1, { name: 'cluster-b' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters/1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'cluster-b' }),
      }),
    )
  })
})

describe('错误语义透传（契约 §5；api-conventions.md §5 / §6）', () => {
  it('getCluster 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §3.3）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(getCluster(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('createCluster 400 VALIDATION_ERROR（name 含 /，契约 §3.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'name', code: 'INVALID_CHARACTER', message: '名称不得包含 /' }],
          },
        }),
      ),
    )

    const err = await expectApiError(createCluster({ name: 'a/b' }))

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details).toEqual([
      { field: 'name', code: 'INVALID_CHARACTER', message: '名称不得包含 /' },
    ])
  })

  it('createCluster 409 CONFLICT（活跃重名，契约 §3.1）→ 保留 details[].field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '名称已存在',
            details: [{ field: 'name', code: 'DUPLICATE', message: '同名 Cluster 已存在' }],
          },
        }),
      ),
    )

    const err = await expectApiError(createCluster({ name: 'cluster-a' }))

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.field).toBe('name')
  })

  it('列表信封字段按契约原样解析（items / total / page / page_size）', async () => {
    const body = { items: [], total: 0, page: 1, page_size: 50 }
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, body)))

    const data = await listClusters({ page: 1, page_size: 50 })

    expect(data).toEqual(body)
  })
})
