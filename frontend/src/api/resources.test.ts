// 计算资源 API 单测：4 端点请求构造（路径/方法/参数/请求体，Contract
// docs/api/F002.md §2）与错误映射透传（409/404/400/422 problem+json → ApiError；
// RESOURCE_NAME_EXISTS 扩展成员 existing_resource_id/existing_resource_type 可读；
// 401/403 全局处理）。适配器模式与 segments.test.ts 一致。
import { afterEach, describe, expect, it, vi } from 'vitest'
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { client, isApiError, resetApiHandlers, setApiHandlers } from './client'
import {
  createResource,
  deleteResource,
  getResource,
  updateResource,
  type ResourceFormDetail,
} from './resources'

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
    return { status: 200, statusText: 'test', data: respond(config), headers: {}, config }
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
  status: number,
  extra?: Record<string, unknown>,
  errors?: Array<{ field: string; code: string; message: string }>,
) {
  return {
    type: 'about:blank',
    title: code,
    status,
    code,
    message,
    ...(extra ?? {}),
    ...(errors ? { errors } : {}),
  }
}

afterEach(() => {
  resetApiHandlers()
  client.defaults.adapter = originalAdapter
})

const detail: ResourceFormDetail = {
  id: 7,
  cluster_id: 1,
  cluster_code: 'N96P',
  cluster_name: '生产集群',
  name: 'cn001',
  resource_type: 'bare_metal',
  status: 'ALLOC',
  status_updated_by: 2,
  status_updated_by_username: 'ops01',
  status_updated_at: '2026-09-25T00:00:00Z',
  interfaces: [
    {
      id: 10,
      name: 'eth0',
      segment_id: 3,
      segment: {
        id: 3,
        name: 'management',
        cidr: '192.168.1.0/24',
        purpose: '管理',
        technology: 'Ethernet',
        vlan: 100,
        gateway: '192.168.1.1',
      },
      created_at: '2026-09-25T00:00:00Z',
      updated_at: '2026-09-25T00:00:00Z',
    },
    {
      id: 11,
      name: 'ib0',
      segment_id: null,
      segment: null,
      created_at: '2026-09-25T00:00:00Z',
      updated_at: '2026-09-25T00:00:00Z',
    },
  ],
  version: 3,
  created_at: '2026-09-25T00:00:00Z',
  updated_at: '2026-09-25T00:00:00Z',
}

describe('createResource（Contract §2.1：POST /resources）', () => {
  it('请求体含 cluster_id/name/resource_type/status 与网卡项（segment_id null=不选）', async () => {
    const captured = captureRequests(() => detail)
    await createResource({
      cluster_id: 1,
      name: 'cn001',
      resource_type: 'bare_metal',
      status: 'DOWN',
      interfaces: [
        { name: 'eth0', segment_id: 3 },
        { name: 'ib0', segment_id: null },
      ],
    })
    expect(captured[0]?.method).toBe('post')
    expect(captured[0]?.url).toBe('/resources')
    expect(JSON.parse(captured[0]?.data as string)).toEqual({
      cluster_id: 1,
      name: 'cn001',
      resource_type: 'bare_metal',
      status: 'DOWN',
      interfaces: [
        { name: 'eth0', segment_id: 3 },
        { name: 'ib0', segment_id: null },
      ],
    })
  })

  it('interfaces 缺省=空数组：不出现在请求体', async () => {
    const captured = captureRequests(() => detail)
    await createResource({ cluster_id: 1, name: 'cn001', resource_type: 'virtual_machine' })
    const body = JSON.parse(captured[0]?.data as string) as Record<string, unknown>
    expect(body).toEqual({ cluster_id: 1, name: 'cn001', resource_type: 'virtual_machine' })
    expect('interfaces' in body).toBe(false)
  })
})

describe('getResource（Contract §2.2：GET /resources/{id}）', () => {
  it('路径含资源 ID；返回详情（含网卡与 version）', async () => {
    const captured = captureRequests(() => detail)
    const result = await getResource(7)
    expect(captured[0]?.method).toBe('get')
    expect(captured[0]?.url).toBe('/resources/7')
    expect(result.version).toBe(3)
    expect(result.interfaces).toHaveLength(2)
    expect(result.interfaces[0]?.segment?.cidr).toBe('192.168.1.0/24')
  })
})

describe('updateResource（Contract §2.3：PATCH /resources/{id}，网卡显式 op）', () => {
  it('interfaces[] 各项带 op：create 带名称与网段、update 仅变化字段（省略=不修改）、delete 仅 id', async () => {
    const captured = captureRequests(() => detail)
    await updateResource(7, {
      name: 'cn001-new',
      status: 'DOWN',
      interfaces: [
        { op: 'create', name: 'ib1', segment_id: 4 },
        { op: 'update', id: 10, segment_id: 5 },
        { op: 'update', id: 12, name: 'eth1' },
        { op: 'delete', id: 11 },
      ],
      version: 3,
    })
    expect(captured[0]?.method).toBe('patch')
    expect(captured[0]?.url).toBe('/resources/7')
    expect(JSON.parse(captured[0]?.data as string)).toEqual({
      name: 'cn001-new',
      status: 'DOWN',
      interfaces: [
        { op: 'create', name: 'ib1', segment_id: 4 },
        { op: 'update', id: 10, segment_id: 5 },
        { op: 'update', id: 12, name: 'eth1' },
        { op: 'delete', id: 11 },
      ],
      version: 3,
    })
  })

  it('update 的 segment_id null=清空网段；interfaces 省略=不改动网卡', async () => {
    const captured = captureRequests(() => detail)
    await updateResource(7, {
      interfaces: [{ op: 'update', id: 10, segment_id: null }],
      version: 3,
    })
    const body = JSON.parse(captured[0]?.data as string) as Record<string, unknown>
    expect(body.interfaces).toEqual([{ op: 'update', id: 10, segment_id: null }])
    expect('name' in body).toBe(false)

    await updateResource(7, { name: 'cn002', version: 4 })
    const body2 = JSON.parse(captured[1]?.data as string) as Record<string, unknown>
    expect(body2).toEqual({ name: 'cn002', version: 4 })
    expect('interfaces' in body2).toBe(false)
  })
})

describe('deleteResource（Contract §2.4：DELETE /resources/{id}?confirm=&version=）', () => {
  it('二次确认与乐观锁经 query 传递', async () => {
    const captured = captureRequests(() => null)
    await deleteResource(7, { confirm: 'cn001', version: 3 })
    expect(captured[0]?.method).toBe('delete')
    expect(captured[0]?.url).toBe('/resources/7')
    expect(captured[0]?.params).toEqual({ confirm: 'cn001', version: 3 })
  })
})

describe('错误映射（problem+json → ApiError；401/403 走全局，其余由页面处理）', () => {
  it('409 RESOURCE_NAME_EXISTS：扩展成员 existing_resource_id/existing_resource_type 可读（Contract §0）', async () => {
    const handlers = {
      onUnauthorized: vi.fn(),
      onForbidden: vi.fn(),
      onPasswordChangeRequired: vi.fn(),
    }
    setApiHandlers(handlers)
    useTestAdapter(() => ({
      status: 409,
      data: problemBody('RESOURCE_NAME_EXISTS', '该集群已存在同名资源', 409, {
        existing_resource_id: 42,
        existing_resource_type: 'bare_metal',
      }),
    }))
    const error = await createResource({
      cluster_id: 1,
      name: 'cn001',
      resource_type: 'bare_metal',
    }).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(409)
      expect(error.code).toBe('RESOURCE_NAME_EXISTS')
      expect(error.extensions['existing_resource_id']).toBe(42)
      expect(error.extensions['existing_resource_type']).toBe('bare_metal')
    } else {
      expect.unreachable('应为 ApiError')
    }
    expect(handlers.onUnauthorized).not.toHaveBeenCalled()
    expect(handlers.onForbidden).not.toHaveBeenCalled()
  })

  it.each([
    'INTERFACE_NAME_TAKEN',
    'RESOURCE_HAS_INTERFACES',
    'VERSION_CONFLICT',
  ])('409 %s → ApiError 原样抛给页面，不触发全局处理器（页面保留输入提示）', async (code) => {
    const handlers = {
      onUnauthorized: vi.fn(),
      onForbidden: vi.fn(),
      onPasswordChangeRequired: vi.fn(),
    }
    setApiHandlers(handlers)
    useTestAdapter(() => ({ status: 409, data: problemBody(code, '冲突', 409) }))
    const error = await updateResource(7, { version: 3 }).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(409)
      expect(error.code).toBe(code)
    } else {
      expect.unreachable('应为 ApiError')
    }
    expect(handlers.onUnauthorized).not.toHaveBeenCalled()
    expect(handlers.onForbidden).not.toHaveBeenCalled()
  })

  it('422 DELETE_CONFIRMATION_MISMATCH → code 可读（删除确认不匹配，页面保留对话框）', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('DELETE_CONFIRMATION_MISMATCH', '确认输入与资源名称不匹配', 422),
    }))
    const error = await deleteResource(7, { confirm: 'cn002', version: 3 }).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(422)
      expect(error.code).toBe('DELETE_CONFIRMATION_MISMATCH')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('422 VALIDATION_ERROR：errors[] 含 interfaces[1].name 下标定位，可经 fieldError/errors 读取', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('VALIDATION_ERROR', '字段校验失败', 422, undefined, [
        { field: 'name', code: 'NAME_FORMAT', message: '资源名称不能为空' },
        { field: 'interfaces[1].name', code: 'INTERFACE_NAME_FORMAT', message: '接口名不能为空' },
        {
          field: 'interfaces[1].segment_id',
          code: 'INTERFACE_SEGMENT_CLUSTER_MISMATCH',
          message: '网段必须与本资源同集群',
        },
      ]),
    }))
    const error = await createResource({
      cluster_id: 1,
      name: ' ',
      resource_type: 'bare_metal',
    }).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.code).toBe('VALIDATION_ERROR')
      expect(error.fieldError('name')).toBe('资源名称不能为空')
      expect(error.fieldError('interfaces[1].name')).toBe('接口名不能为空')
      expect(error.errors).toHaveLength(3)
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('400 INVALID_REQUEST（errors[].code=RESOURCE_TYPE_IMMUTABLE）→ 状态码与顶层 code 可读', async () => {
    useTestAdapter(() => ({
      status: 400,
      data: problemBody('INVALID_REQUEST', '请求体非法', 400, undefined, [
        { field: 'resource_type', code: 'RESOURCE_TYPE_IMMUTABLE', message: '资源类型创建后不可修改' },
      ]),
    }))
    const error = await updateResource(7, { version: 3 }).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(400)
      expect(error.code).toBe('INVALID_REQUEST')
      expect(error.errors[0]?.code).toBe('RESOURCE_TYPE_IMMUTABLE')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('403 FORBIDDEN（viewer 越权写）→ 触发全局 onForbidden（页面不重复提示）', async () => {
    const onForbidden = vi.fn()
    setApiHandlers({
      onUnauthorized: vi.fn(),
      onForbidden,
      onPasswordChangeRequired: vi.fn(),
    })
    useTestAdapter(() => ({ status: 403, data: problemBody('FORBIDDEN', '没有权限', 403) }))
    await createResource({ cluster_id: 1, name: 'x', resource_type: 'bare_metal' }).catch(() => undefined)
    expect(onForbidden).toHaveBeenCalledTimes(1)
  })

  it('401 UNAUTHENTICATED → 触发全局 onUnauthorized（跳登录）', async () => {
    const onUnauthorized = vi.fn()
    setApiHandlers({
      onUnauthorized,
      onForbidden: vi.fn(),
      onPasswordChangeRequired: vi.fn(),
    })
    useTestAdapter(() => ({ status: 401, data: problemBody('UNAUTHENTICATED', '未登录', 401) }))
    await getResource(7).catch(() => undefined)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('404 RESOURCE_NOT_FOUND / CLUSTER_NOT_FOUND → ApiError 携带 code，由页面呈现', async () => {
    useTestAdapter(() => ({ status: 404, data: problemBody('RESOURCE_NOT_FOUND', '资源不存在', 404) }))
    const error = await getResource(999).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(404)
      expect(error.code).toBe('RESOURCE_NOT_FOUND')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('扩展成员缺省时 extensions 为空对象（不误读）', async () => {
    useTestAdapter(() => ({ status: 409, data: problemBody('VERSION_CONFLICT', '冲突', 409) }))
    const error = await updateResource(7, { version: 3 }).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.extensions).toEqual({})
    } else {
      expect.unreachable('应为 ApiError')
    }
  })
})
