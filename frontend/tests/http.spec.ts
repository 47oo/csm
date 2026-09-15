import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest } from '../src/api/http'

/**
 * API client 基座测试：统一错误信封解析与归一化
 * （docs/api/api-conventions.md §5 / §6；docs/api/f012-project-foundation.md）。
 */

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

describe('apiRequest 成功路径', () => {
  it('2xx JSON 响应解析为数据，GET 默认无请求体', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await apiRequest<{ items: unknown[] }>('/_foundation/clusters')

    expect(data).toEqual({ items: [], total: 0, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/_foundation/clusters',
      expect.objectContaining({
        method: 'GET',
        body: undefined,
        headers: expect.objectContaining({ Accept: 'application/json' }),
      }),
    )
  })

  it('query 参数被拼接且 undefined 项被忽略', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/_foundation/clusters', {
      method: 'GET',
      query: { page: 1, page_size: 50, extra: undefined },
    })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/_foundation/clusters?page=1&page_size=50',
      expect.anything(),
    )
  })

  it('204 无内容 → 返回 undefined', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 204 })),
    )

    await expect(apiRequest('/_foundation/clusters/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})

describe('apiRequest 错误信封解析（契约 §5）', () => {
  it('500 INTERNAL_ERROR（即 GET /_foundation/error 的确定性响应）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(500, { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }),
      ),
    )

    const err = await expectApiError(apiRequest('/_foundation/error'))

    expect(err.status).toBe(500)
    expect(err.code).toBe('INTERNAL_ERROR')
    expect(err.message).toBe('内部错误')
    expect(err.details).toEqual([])
  })

  it('400 VALIDATION_ERROR → 保留 details[].field（AC-06）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'page', message: 'page 必须大于等于 1' }],
          },
        }),
      ),
    )

    const err = await expectApiError(apiRequest('/_foundation/clusters?page=0'))

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details).toEqual([{ field: 'page', message: 'page 必须大于等于 1' }])
  })

  it('404 NOT_FOUND（不存在或已软删）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(apiRequest('/_foundation/clusters/999'))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('契约之外的未知 code 原样保留，不被改写', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, { error: { code: 'SOME_FUTURE_CODE', message: 'x' } }),
      ),
    )

    const err = await expectApiError(apiRequest('/_foundation/clusters'))

    expect(err.code).toBe('SOME_FUTURE_CODE')
  })
})

describe('apiRequest 未按契约响应的归一化', () => {
  it('网络失败（fetch reject）→ NETWORK_ERROR，status 为 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )

    const err = await expectApiError(apiRequest('/_foundation/clusters'))

    expect(err.status).toBe(0)
    expect(err.code).toBe('NETWORK_ERROR')
  })

  it('错误响应体不是 JSON（如代理返回 HTML）→ UNKNOWN_ERROR', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response('<html>Internal Server Error</html>', {
            status: 500,
            headers: { 'Content-Type': 'text/html' },
          }),
      ),
    )

    const err = await expectApiError(apiRequest('/_foundation/clusters'))

    expect(err.status).toBe(500)
    expect(err.code).toBe('UNKNOWN_ERROR')
  })

  it('2xx 但响应体不是 JSON → UNKNOWN_ERROR', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('not json', { status: 200 })),
    )

    const err = await expectApiError(apiRequest('/_foundation/clusters'))

    expect(err.status).toBe(200)
    expect(err.code).toBe('UNKNOWN_ERROR')
  })

  it('响应体是 JSON 但不符合错误信封结构 → UNKNOWN_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, { unexpected: true })))

    const err = await expectApiError(apiRequest('/_foundation/clusters'))

    expect(err.status).toBe(500)
    expect(err.code).toBe('UNKNOWN_ERROR')
  })
})
