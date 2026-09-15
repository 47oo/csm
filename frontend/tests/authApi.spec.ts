import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCurrentSession, login, logout } from '../src/api/auth'
import { ApiError, setUnauthenticatedHandler } from '../src/api/http'

/**
 * 认证 API 客户端测试：请求构造（路径 / 方法 / 请求体）与 401 语义透传、
 * 全局 401 跳转抑制（T-18）。契约依据：docs/api/f013-auth.md（READY）。
 * fetch 全部桩替换，不触达真实后端。
 */

const SESSION_USER = { id: 1, username: 'admin' }
/** 契约 §5.1 统一失败语义：三情形返回完全相同的 401（R-AUTH-006）。 */
const UNAUTHENTICATED_BODY = {
  error: { code: 'UNAUTHENTICATED', message: '用户名或口令不正确', details: [] },
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
  setUnauthenticatedHandler(null)
})

describe('login（契约 §5.1，唯一豁免端点）', () => {
  it('POST /api/auth/login，请求体 username / password 原样 JSON 提交（不 trim / 不变换）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SESSION_USER))
    vi.stubGlobal('fetch', fetchMock)

    const user = await login({ username: ' admin ', password: 'x' })

    expect(user).toEqual(SESSION_USER)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: ' admin ', password: 'x' }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('401 UNAUTHENTICATED（用户名不存在 / 口令错误 / 账号停用，不可区分）→ 抛 ApiError，不触发全局 401 跳转', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, UNAUTHENTICATED_BODY)))
    const handler = vi.fn()
    setUnauthenticatedHandler(handler)

    const err = await expectApiError(login({ username: 'admin', password: 'wrong' }))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
    expect(err.details).toEqual([])
    expect(handler).not.toHaveBeenCalled()
  })

  it('400 VALIDATION_ERROR（请求体字段非法，契约 §5.1）→ 抛 ApiError 保留 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'password', message: 'password 必填' }],
          },
        }),
      ),
    )

    const err = await expectApiError(login({ username: 'admin', password: '' }))

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('password')
  })
})

describe('logout（契约 §5.2）', () => {
  it('POST /api/auth/logout，无请求体；204 → undefined', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(logout()).resolves.toBeUndefined()

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/auth/logout',
      expect.objectContaining({ method: 'POST', body: undefined }),
    )
  })

  it('401 UNAUTHENTICATED（会话已失效）→ 抛 ApiError（由调用方与 204 归一为同一处理）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, UNAUTHENTICATED_BODY)))

    const err = await expectApiError(logout())

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})

describe('getCurrentSession（契约 §5.3）', () => {
  it('GET /api/auth/session；200 → AuthenticatedUser', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SESSION_USER))
    vi.stubGlobal('fetch', fetchMock)

    const user = await getCurrentSession()

    expect(user).toEqual(SESSION_USER)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/auth/session',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('401 UNAUTHENTICATED（无有效会话）→ 抛 ApiError，不触发全局 401 跳转（启动期探测自行处理）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, UNAUTHENTICATED_BODY)))
    const handler = vi.fn()
    setUnauthenticatedHandler(handler)

    const err = await expectApiError(getCurrentSession())

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
    expect(handler).not.toHaveBeenCalled()
  })
})
