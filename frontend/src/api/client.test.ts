import { afterEach, describe, expect, it, vi } from 'vitest'
import axios, { type AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import {
  ApiError,
  apiErrorMessage,
  client,
  isApiError,
  normalizeApiError,
  resetApiHandlers,
  setApiHandlers,
} from './client'

const originalAdapter = client.defaults.adapter

type TestResponse = { status: number; data?: unknown } | { networkError: true }

/** 构造测试用 axios 适配器：按 status/body 应答（模拟 problem+json） */
function useTestAdapter(respond: (config: InternalAxiosRequestConfig) => TestResponse): void {
  client.defaults.adapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    const result = respond(config)
    if ('networkError' in result) {
      throw axios.AxiosError.from(
        new Error('connect ECONNREFUSED'),
        axios.AxiosError.ERR_NETWORK,
        config,
      )
    }
    const response: AxiosResponse = {
      status: result.status,
      statusText: 'test',
      data: (result.data ?? null) as AxiosResponse['data'],
      headers: {},
      config,
    }
    if (result.status >= 400) {
      throw axios.AxiosError.from(
        new Error(`Request failed with status code ${result.status}`),
        axios.AxiosError.ERR_BAD_RESPONSE,
        config,
        undefined,
        response,
      )
    }
    return response
  }
}

function problemBody(
  code: string,
  message: string,
  errors?: Array<{ field: string; code: string; message: string }>,
) {
  return {
    type: 'about:blank',
    title: code,
    status: 422,
    code,
    message,
    ...(errors ? { errors } : {}),
  }
}

afterEach(() => {
  resetApiHandlers()
  client.defaults.adapter = originalAdapter
})

describe('normalizeApiError：problem+json 归一化（Contract §0）', () => {
  it('映射 problem+json 的 code/message 与 errors[]', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('VALIDATION_ERROR', '字段校验失败', [
        { field: 'password', code: 'PASSWORD_POLICY', message: '口令至少 8 位且包含字母与数字' },
      ]),
    }))
    const error = await client.get('/users').catch((e: unknown) => e)
    expect(isApiError(error)).toBe(true)
    if (isApiError(error)) {
      expect(error.status).toBe(422)
      expect(error.code).toBe('VALIDATION_ERROR')
      expect(error.message).toBe('字段校验失败')
      expect(error.errors).toHaveLength(1)
      expect(error.errors[0]).toEqual({
        field: 'password',
        code: 'PASSWORD_POLICY',
        message: '口令至少 8 位且包含字母与数字',
      })
      expect(error.fieldError('password')).toBe('口令至少 8 位且包含字母与数字')
      expect(error.fieldError('username')).toBeUndefined()
    }
  })

  it('errors 缺省时归一化为空数组', async () => {
    useTestAdapter(() => ({ status: 409, data: problemBody('USERNAME_TAKEN', '用户名已被占用') }))
    const error = await client.post('/users', {}).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.errors).toEqual([])
      expect(error.code).toBe('USERNAME_TAKEN')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('非 JSON 错误响应（如网关 502）归一化为通用错误', async () => {
    useTestAdapter(() => ({ status: 502, data: '<html>Bad Gateway</html>' }))
    const error = await client.get('/users').catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(502)
      expect(error.code).toBe('UNKNOWN')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('网络错误归一化为 NETWORK_ERROR', () => {
    const networkError = axios.AxiosError.from(new Error('connect refused'), 'ERR_NETWORK')
    const error = normalizeApiError(networkError)
    expect(error.status).toBe(0)
    expect(error.code).toBe('NETWORK_ERROR')
  })

  it('ApiError 原样透传', () => {
    const original = new ApiError(404, 'USER_NOT_FOUND', '用户不存在')
    expect(normalizeApiError(original)).toBe(original)
  })

  it('非 axios 异常归一化为通用错误', () => {
    const error = normalizeApiError(new Error('boom'))
    expect(error.status).toBe(0)
    expect(error.code).toBe('UNKNOWN')
  })
})

describe('axios 客户端基础配置', () => {
  it('baseURL 为 /api/v1 且 withCredentials（HttpOnly Cookie 会话）', () => {
    expect(client.defaults.baseURL).toBe('/api/v1')
    expect(client.defaults.withCredentials).toBe(true)
  })
})

describe('全局 401/403/409 处理分支', () => {
  it('401 → 调用 onUnauthorized 并以 ApiError 拒绝', async () => {
    const onUnauthorized = vi.fn()
    const onForbidden = vi.fn()
    const onPasswordChangeRequired = vi.fn()
    setApiHandlers({ onUnauthorized, onForbidden, onPasswordChangeRequired })
    useTestAdapter(() => ({ status: 401, data: problemBody('UNAUTHENTICATED', '未登录') }))

    const error = await client.get('/users').catch((e: unknown) => e)
    expect(isApiError(error)).toBe(true)
    if (isApiError(error)) expect(error.code).toBe('UNAUTHENTICATED')
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(onForbidden).not.toHaveBeenCalled()
    expect(onPasswordChangeRequired).not.toHaveBeenCalled()
  })

  it('skipGlobalErrorHandling 的请求（如登录本身 401）不触发全局跳转', async () => {
    const onUnauthorized = vi.fn()
    setApiHandlers({
      onUnauthorized,
      onForbidden: vi.fn(),
      onPasswordChangeRequired: vi.fn(),
    })
    useTestAdapter(() => ({ status: 401, data: problemBody('INVALID_CREDENTIALS', '用户名或口令错误') }))

    const error = await client
      .post('/auth/login', { username: 'a', password: 'b' }, { skipGlobalErrorHandling: true })
      .catch((e: unknown) => e)
    expect(isApiError(error)).toBe(true)
    if (isApiError(error)) expect(error.code).toBe('INVALID_CREDENTIALS')
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('403 PASSWORD_CHANGE_REQUIRED → 只触发 onPasswordChangeRequired', async () => {
    const onUnauthorized = vi.fn()
    const onForbidden = vi.fn()
    const onPasswordChangeRequired = vi.fn()
    setApiHandlers({ onUnauthorized, onForbidden, onPasswordChangeRequired })
    useTestAdapter(() => ({ status: 403, data: problemBody('PASSWORD_CHANGE_REQUIRED', '须先修改口令') }))

    await client.get('/users').catch(() => undefined)
    expect(onPasswordChangeRequired).toHaveBeenCalledTimes(1)
    expect(onForbidden).not.toHaveBeenCalled()
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('403 其它（FORBIDDEN / ACCOUNT_DISABLED）→ 触发 onForbidden', async () => {
    const onForbidden = vi.fn()
    const onPasswordChangeRequired = vi.fn()
    setApiHandlers({
      onUnauthorized: vi.fn(),
      onForbidden,
      onPasswordChangeRequired,
    })
    useTestAdapter(() => ({ status: 403, data: problemBody('FORBIDDEN', '没有权限') }))

    await client.get('/users').catch(() => undefined)
    expect(onForbidden).toHaveBeenCalledTimes(1)
    expect(onPasswordChangeRequired).not.toHaveBeenCalled()
  })

  it.each(['USERNAME_TAKEN', 'VERSION_CONFLICT', 'LAST_ADMIN'])(
    '409 %s → 不触发任何全局处理器，错误原样抛给页面（保留输入由页面处理）',
    async (code) => {
      const handlers = {
        onUnauthorized: vi.fn(),
        onForbidden: vi.fn(),
        onPasswordChangeRequired: vi.fn(),
      }
      setApiHandlers(handlers)
      useTestAdapter(() => ({ status: 409, data: problemBody(code, '冲突') }))

      const error = await client.post('/users', {}).catch((e: unknown) => e)
      if (isApiError(error)) {
        expect(error.status).toBe(409)
        expect(error.code).toBe(code)
      } else {
        expect.unreachable('应为 ApiError')
      }
      expect(handlers.onUnauthorized).not.toHaveBeenCalled()
      expect(handlers.onForbidden).not.toHaveBeenCalled()
      expect(handlers.onPasswordChangeRequired).not.toHaveBeenCalled()
    },
  )

  it('未注册处理器时不崩溃，仍以 ApiError 拒绝', async () => {
    useTestAdapter(() => ({ status: 401, data: problemBody('UNAUTHENTICATED', '未登录') }))
    const error = await client.get('/users').catch((e: unknown) => e)
    expect(isApiError(error)).toBe(true)
  })
})

describe('apiErrorMessage', () => {
  it('优先使用 problem+json 的 message', () => {
    expect(apiErrorMessage(new ApiError(409, 'USERNAME_TAKEN', '用户名已被占用'))).toBe('用户名已被占用')
  })

  it('5xx 未知错误使用服务器错误文案', () => {
    expect(apiErrorMessage(new ApiError(502, 'UNKNOWN', '请求失败（HTTP 502）'))).toBe(
      '服务器错误（HTTP 502），请稍后重试',
    )
  })

  it('非 ApiError 时返回通用文案', () => {
    expect(apiErrorMessage(new Error('boom'))).toBe('操作失败，请稍后重试')
  })
})

describe('isApiError', () => {
  it('识别 AxiosError 与普通 Error 的区别', () => {
    expect(isApiError(new ApiError(400, 'X', 'x'))).toBe(true)
    expect(isApiError(new Error('x'))).toBe(false)
    const axiosError = axios.AxiosError.from(new Error('x')) as AxiosError
    expect(isApiError(axiosError)).toBe(false)
  })
})
