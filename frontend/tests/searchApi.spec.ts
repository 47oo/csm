import { afterEach, describe, expect, it, vi } from 'vitest'
import { searchClusterResources } from '../src/api/search'
import { ApiError } from '../src/api/http'

/**
 * 搜索 API 客户端测试（F019）：请求构造（路径 / 方法 / 查询参数）与契约
 * 错误语义透传。契约依据：docs/api/f019-search-result-aggregation.md（READY，
 * 唯一权威）——恰一个只读端点 GET /api/clusters/{cluster_id}/search
 * （method / path / 参数与 F018 相同，响应形态为聚合行列表）；keyword 必填
 * 且原样提交（不 trim / 不归一化）；分页按组织单元计数，复用通用信封。
 * fetch 全部桩替换，不触达真实后端。
 */

const TS = '2026-09-18T10:00:00Z'

/**
 * 契约 §4 Response 200 示例结构：一个组织单元（BareMetal 命中行 + 其 NIC /
 * IP 关联行，含 derivation_path；同单元共享 group_key）。
 */
const SEARCH_BODY = {
  items: [
    {
      resource_type: 'BARE_METAL',
      id: 101,
      role: 'HIT',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: ['hostname'],
      derivation_path: null,
      resource: {
        id: 101,
        cluster_id: 3,
        hostname: 'cn001-gpu',
        status: 'IDLE',
        vendor: null,
        model: null,
        serial_number: null,
        cpu: null,
        memory: null,
        gpu: null,
        storage: null,
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'NETWORK_INTERFACE',
      id: 12,
      role: 'RELATED',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'NETWORK_INTERFACE', id: 12 },
      ],
      resource: {
        id: 12,
        bare_metal_id: 101,
        name: 'eth0',
        technology_type: 'Ethernet',
        purpose: 'Management',
        created_at: TS,
        updated_at: TS,
      },
    },
    {
      resource_type: 'IP_ADDRESS',
      id: 41,
      role: 'RELATED',
      group_key: { resource_type: 'BARE_METAL', id: 101 },
      matched_fields: [],
      derivation_path: [
        { resource_type: 'BARE_METAL', id: 101 },
        { resource_type: 'NETWORK_INTERFACE', id: 12 },
        { resource_type: 'IP_ADDRESS', id: 41 },
      ],
      resource: {
        id: 41,
        network_interface_id: 12,
        ip_address: '10.0.1.1/16',
        created_at: TS,
        updated_at: TS,
      },
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
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
  it('searchClusterResources → GET /api/clusters/{id}/search，keyword 原样拼接；聚合行列表原样透传', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SEARCH_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const data = await searchClusterResources(3, { keyword: 'cn001', page: 1, page_size: 50 })

    expect(data).toEqual(SEARCH_BODY)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters/3/search?keyword=cn001&page=1&page_size=50',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('分页参数缺省 → 仅携带 keyword（服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SEARCH_BODY))
    vi.stubGlobal('fetch', fetchMock)

    await searchClusterResources(3, { keyword: 'gpu' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters/3/search?keyword=gpu',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('关键字原样提交：空白不 trim、特殊字符按 URL 编码（契约 §2「不 trim、不归一化」）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SEARCH_BODY))
    vi.stubGlobal('fetch', fetchMock)

    await searchClusterResources(3, { keyword: '  a b&c  ' })

    // URLSearchParams 按表单编码：空格 +、& %26；原样（含首尾空白）提交，不 trim。
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/clusters/3/search?keyword=++a+b%26c++',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('无命中（Empty）→ 200 + items == [] 原样返回，不抛出', async () => {
    const emptyBody = { items: [], total: 0, page: 1, page_size: 50 }
    const fetchMock = vi.fn(async () => jsonResponse(200, emptyBody))
    vi.stubGlobal('fetch', fetchMock)

    const data = await searchClusterResources(3, { keyword: 'zzz' })

    expect(data).toEqual(emptyBody)
  })
})

describe('错误语义透传（契约 §5 Error Semantics / §6）', () => {
  it('Cluster 不存在或已逻辑删除 → 404 NOT_FOUND（两者不区分）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在或已被逻辑删除', details: [] } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const error = await expectApiError(searchClusterResources(999, { keyword: 'x' }))

    expect(error.status).toBe(404)
    expect(error.code).toBe('NOT_FOUND')
  })

  it('空 / 仅空白 keyword 由服务端裁决 → 400 VALIDATION_ERROR（details[].field == "keyword"）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(400, {
        error: {
          code: 'VALIDATION_ERROR',
          message: '请求校验失败',
          details: [{ field: 'keyword', code: 'INVALID', message: '关键字不能为空' }],
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const error = await expectApiError(searchClusterResources(3, { keyword: '  ' }))

    expect(error.status).toBe(400)
    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.details[0]?.field).toBe('keyword')
  })

  it('未认证 → 401 UNAUTHENTICATED（由全局会话失效处理，本层透传 code）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证', details: [] } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const error = await expectApiError(searchClusterResources(3, { keyword: 'x' }))

    expect(error.status).toBe(401)
    expect(error.code).toBe('UNAUTHENTICATED')
  })

  it('网络失败 → 归一为 NETWORK_ERROR（status 0）', async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError('fetch failed')
    })
    vi.stubGlobal('fetch', fetchMock)

    const error = await expectApiError(searchClusterResources(3, { keyword: 'x' }))

    expect(error.status).toBe(0)
    expect(error.code).toBe('NETWORK_ERROR')
  })
})
