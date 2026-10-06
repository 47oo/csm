import { afterEach, describe, expect, it, vi } from 'vitest'
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { client, isApiError, resetApiHandlers, setApiHandlers } from './client'
import { createCluster, deleteCluster, getCluster, listClusters, updateCluster } from './clusters'
import type { ClusterDetail, PagedClusters } from './clusters'

const originalAdapter = client.defaults.adapter

interface CapturedRequest {
  method?: string
  url?: string
  params?: Record<string, unknown>
  data?: unknown
}

/** 捕获请求并返回固定响应 */
function captureRequests(respond: (config: InternalAxiosRequestConfig) => unknown): CapturedRequest[] {
  const captured: CapturedRequest[] = []
  client.defaults.adapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    captured.push({
      method: config.method,
      url: config.url,
      params: config.params as Record<string, unknown> | undefined,
      data: config.data,
    })
    return {
      status: 200,
      statusText: 'test',
      data: respond(config),
      headers: {},
      config,
    }
  }
  return captured
}

type TestResponse = { status: number; data?: unknown } | { networkError: true }

/** 构造测试用 axios 适配器：按 status/body 应答（模拟 problem+json） */
function useTestAdapter(respond: (config: InternalAxiosRequestConfig) => TestResponse): void {
  client.defaults.adapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    const result = respond(config)
    if ('networkError' in result) {
      throw axios.AxiosError.from(new Error('connect ECONNREFUSED'), axios.AxiosError.ERR_NETWORK, config)
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

const paged: PagedClusters = { items: [], total: 0, page: 1, page_size: 20 }
const detail: ClusterDetail = {
  id: 3,
  code: 'N96P',
  name: '生产集群',
  purpose: '训练',
  created_at: '2026-09-25T00:00:00Z',
  updated_at: '2026-09-25T00:00:00Z',
  version: 5,
}

describe('listClusters（Contract §2.1：page/page_size/q/sort）', () => {
  it('传递全部查询参数，q 去首尾空格', async () => {
    const captured = captureRequests(() => paged)
    await listClusters({ page: 2, page_size: 50, q: '  n96  ', sort: '-created_at' })
    expect(captured).toHaveLength(1)
    expect(captured[0].method).toBe('get')
    expect(captured[0].url).toBe('/clusters')
    expect(captured[0].params).toEqual({
      page: '2',
      page_size: '50',
      q: 'n96',
      sort: '-created_at',
    })
  })

  it('空 q 与空 sort 不作为参数发送（默认排序由服务端应用）', async () => {
    const captured = captureRequests(() => paged)
    await listClusters({ q: '   ', sort: '' })
    expect(captured[0].params).toEqual({})
  })
})

describe('集群端点路径与方法（Contract §2.2–2.5）', () => {
  it('createCluster：POST /clusters，body 含 code/name/purpose', async () => {
    const captured = captureRequests(() => detail)
    await createCluster({ code: 'N96P', name: '生产集群', purpose: '训练' })
    expect(captured[0].method).toBe('post')
    expect(captured[0].url).toBe('/clusters')
    expect(JSON.parse(captured[0].data as string)).toEqual({
      code: 'N96P',
      name: '生产集群',
      purpose: '训练',
    })
  })

  it('getCluster：GET /clusters/{cluster_id}', async () => {
    const captured = captureRequests(() => detail)
    await getCluster(3)
    expect(captured[0].method).toBe('get')
    expect(captured[0].url).toBe('/clusters/3')
  })

  it('updateCluster：PATCH /clusters/{id}，body 仅 name/purpose/version（code 不可改）', async () => {
    const captured = captureRequests(() => detail)
    await updateCluster(3, { name: '生产集群', purpose: '训练与推理', version: 5 })
    expect(captured[0].method).toBe('patch')
    expect(captured[0].url).toBe('/clusters/3')
    const body = JSON.parse(captured[0].data as string)
    expect(body).toEqual({ name: '生产集群', purpose: '训练与推理', version: 5 })
    expect('code' in body).toBe(false)
  })

  it('deleteCluster：DELETE /clusters/{id}?confirm=&version=（二次确认 + 乐观锁经 query）', async () => {
    const captured = captureRequests(() => null)
    await deleteCluster(3, { confirm: 'N96P', version: 5 })
    expect(captured[0].method).toBe('delete')
    expect(captured[0].url).toBe('/clusters/3')
    expect(captured[0].params).toEqual({ confirm: 'N96P', version: 5 })
  })
})

describe('集群错误映射（problem+json → ApiError；401/403 走全局，其余由页面处理）', () => {
  it.each(['CLUSTER_CODE_TAKEN', 'CLUSTER_NAME_TAKEN', 'CLUSTER_HAS_ASSOCIATIONS', 'VERSION_CONFLICT'])(
    '409 %s → ApiError 原样抛给页面，不触发全局处理器（页面保留输入提示）',
    async (code) => {
      const handlers = {
        onUnauthorized: vi.fn(),
        onForbidden: vi.fn(),
        onPasswordChangeRequired: vi.fn(),
      }
      setApiHandlers(handlers)
      useTestAdapter(() => ({ status: 409, data: problemBody(code, '冲突') }))

      const error = await client.post('/clusters', {}).catch((e: unknown) => e)
      if (isApiError(error)) {
        expect(error.status).toBe(409)
        expect(error.code).toBe(code)
        expect(error.message).toBe('冲突')
      } else {
        expect.unreachable('应为 ApiError')
      }
      expect(handlers.onUnauthorized).not.toHaveBeenCalled()
      expect(handlers.onForbidden).not.toHaveBeenCalled()
      expect(handlers.onPasswordChangeRequired).not.toHaveBeenCalled()
    },
  )

  it('422 DELETE_CONFIRMATION_MISMATCH → 字段级错误可经 fieldError 读取（confirm 字段）', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('DELETE_CONFIRMATION_MISMATCH', '确认输入不匹配', [
        { field: 'confirm', code: 'CONFIRM_MISMATCH', message: '输入与集群名称或编号不匹配' },
      ]),
    }))
    const error = await client.delete('/clusters/3', { params: { confirm: 'x', version: 1 } }).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(422)
      expect(error.code).toBe('DELETE_CONFIRMATION_MISMATCH')
      expect(error.fieldError('confirm')).toBe('输入与集群名称或编号不匹配')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('422 VALIDATION_ERROR（code 字段级 CODE_FORMAT）→ errors[] 可读', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('VALIDATION_ERROR', '字段校验失败', [
        { field: 'code', code: 'CODE_FORMAT', message: '集群 code 规范化后仅允许大写字母与数字，长度 1–32' },
      ]),
    }))
    const error = await client.post('/clusters', {}).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.code).toBe('VALIDATION_ERROR')
      expect(error.fieldError('code')).toBe('集群 code 规范化后仅允许大写字母与数字，长度 1–32')
      expect(error.fieldError('name')).toBeUndefined()
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('403 FORBIDDEN（越权）→ 触发全局 onForbidden（页面不重复提示）', async () => {
    const onForbidden = vi.fn()
    setApiHandlers({
      onUnauthorized: vi.fn(),
      onForbidden,
      onPasswordChangeRequired: vi.fn(),
    })
    useTestAdapter(() => ({ status: 403, data: problemBody('FORBIDDEN', '没有权限') }))
    await client.post('/clusters', {}).catch(() => undefined)
    expect(onForbidden).toHaveBeenCalledTimes(1)
  })

  it('401 UNAUTHENTICATED → 触发全局 onUnauthorized（跳登录）', async () => {
    const onUnauthorized = vi.fn()
    setApiHandlers({
      onUnauthorized,
      onForbidden: vi.fn(),
      onPasswordChangeRequired: vi.fn(),
    })
    useTestAdapter(() => ({ status: 401, data: problemBody('UNAUTHENTICATED', '未登录') }))
    await client.get('/clusters').catch(() => undefined)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('404 CLUSTER_NOT_FOUND → ApiError 携带 code，由页面刷新列表', async () => {
    useTestAdapter(() => ({ status: 404, data: problemBody('CLUSTER_NOT_FOUND', '集群不存在') }))
    const error = await client.get('/clusters/999').catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(404)
      expect(error.code).toBe('CLUSTER_NOT_FOUND')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })
})
