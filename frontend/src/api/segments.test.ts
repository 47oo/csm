// 网段 API 单测：9 端点请求构造（路径/方法/参数/请求体，Contract docs/api/F005.md
// §2/§3）与错误映射透传（409/404/422 problem+json → ApiError；401/403 全局处理）。
import { afterEach, describe, expect, it, vi } from 'vitest'
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { client, isApiError, resetApiHandlers, setApiHandlers } from './client'
import {
  clearNetworkSegmentGateway,
  createNetworkSegment,
  createReservedAddress,
  deleteNetworkSegment,
  deleteReservedAddress,
  getNetworkSegment,
  listNetworkSegments,
  listReservedAddresses,
  updateNetworkSegment,
  type NetworkSegmentDetail,
  type PagedNetworkSegments,
  type ReservedAddress,
} from './segments'

const originalAdapter = client.defaults.adapter

interface CapturedRequest {
  method?: string
  url?: string
  params?: Record<string, unknown>
  data?: unknown
}

/** 捕获请求并返回固定响应 */
function captureRequests(
  respond: (config: InternalAxiosRequestConfig) => unknown,
): CapturedRequest[] {
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
  status = 422,
) {
  return {
    type: 'about:blank',
    title: code,
    status,
    code,
    message,
    ...(errors ? { errors } : {}),
  }
}

afterEach(() => {
  resetApiHandlers()
  client.defaults.adapter = originalAdapter
})

const reserved: ReservedAddress = {
  id: 11,
  start_ip: '192.168.1.100',
  end_ip: '192.168.1.110',
  is_range: true,
  created_at: '2026-09-25T00:00:00Z',
}

const detail: NetworkSegmentDetail = {
  id: 5,
  cluster_id: 1,
  cluster_code: 'N96P',
  cluster_name: '生产集群',
  name: 'management',
  cidr: '192.168.1.0/24',
  purpose: '管理',
  technology: 'Ethernet',
  vlan: 100,
  gateway: '192.168.1.1',
  auto_alloc_start: '192.168.1.20',
  auto_alloc_end: '192.168.1.30',
  auto_alloc_enabled: true,
  reserved_addresses: [reserved],
  reserved_address_count: 1,
  allocated_count: 0,
  auto_assignable_count: 9,
  has_overlap: true,
  overlaps: [{ segment_id: 6, name: 'storage', cidr: '192.168.1.128/25' }],
  created_at: '2026-09-25T00:00:00Z',
  updated_at: '2026-09-25T00:00:00Z',
  version: 3,
}

const paged: PagedNetworkSegments = { items: [], total: 0, page: 1, page_size: 20 }

describe('listNetworkSegments（Contract §2.1：cluster_id/page/page_size/q/sort）', () => {
  it('传递全部查询参数；q 去首尾空格', async () => {
    const captured = captureRequests(() => paged)
    await listNetworkSegments({ cluster_id: 1, page: 2, page_size: 50, q: '  mgmt  ', sort: '-created_at' })
    expect(captured).toHaveLength(1)
    expect(captured[0].method).toBe('get')
    expect(captured[0].url).toBe('/network-segments')
    expect(captured[0].params).toEqual({
      cluster_id: '1',
      page: '2',
      page_size: '50',
      q: 'mgmt',
      sort: '-created_at',
    })
  })

  it('空 q 与空 sort 不发送；省略 cluster_id 时跨集群查询', async () => {
    const captured = captureRequests(() => paged)
    await listNetworkSegments({ q: '   ', sort: '' })
    expect(captured[0].params).toEqual({})
  })
})

describe('网段本体端点（Contract §2.2–2.5）', () => {
  it('createNetworkSegment：POST /network-segments，body 含全部字段（空值显式 null）', async () => {
    const captured = captureRequests(() => detail)
    await createNetworkSegment({
      cluster_id: 1,
      name: 'management',
      cidr: '192.168.1.0/24',
      purpose: '管理',
      technology: 'Ethernet',
      vlan: null,
      gateway: null,
      auto_alloc_start: null,
      auto_alloc_end: null,
    })
    expect(captured[0].method).toBe('post')
    expect(captured[0].url).toBe('/network-segments')
    expect(JSON.parse(captured[0].data as string)).toEqual({
      cluster_id: 1,
      name: 'management',
      cidr: '192.168.1.0/24',
      purpose: '管理',
      technology: 'Ethernet',
      vlan: null,
      gateway: null,
      auto_alloc_start: null,
      auto_alloc_end: null,
    })
  })

  it('getNetworkSegment：GET /network-segments/{segment_id}，返回详情（含 version/保留地址/重叠）', async () => {
    const captured = captureRequests(() => detail)
    const result = await getNetworkSegment(5)
    expect(captured[0].method).toBe('get')
    expect(captured[0].url).toBe('/network-segments/5')
    expect(result.version).toBe(3)
    expect(result.reserved_addresses).toHaveLength(1)
    expect(result.overlaps[0]?.cidr).toBe('192.168.1.128/25')
  })

  it('updateNetworkSegment：PATCH /network-segments/{id}；省略字段不出现在 body（= 不修改）', async () => {
    const captured = captureRequests(() => detail)
    await updateNetworkSegment(5, { gateway: '192.168.1.254', version: 3 })
    expect(captured[0].method).toBe('patch')
    expect(captured[0].url).toBe('/network-segments/5')
    const body = JSON.parse(captured[0].data as string) as Record<string, unknown>
    expect(body).toEqual({ gateway: '192.168.1.254', version: 3 })
    expect('name' in body).toBe(false)
    expect('cidr' in body).toBe(false)
  })

  it('updateNetworkSegment：null 显式清空可空字段（vlan/网关/自动范围）', async () => {
    const captured = captureRequests(() => detail)
    await updateNetworkSegment(5, {
      vlan: null,
      gateway: null,
      auto_alloc_start: null,
      auto_alloc_end: null,
      version: 4,
    })
    expect(JSON.parse(captured[0].data as string)).toEqual({
      vlan: null,
      gateway: null,
      auto_alloc_start: null,
      auto_alloc_end: null,
      version: 4,
    })
  })

  it('deleteNetworkSegment：DELETE /network-segments/{id}?confirm=&version=（二次确认 + 乐观锁经 query）', async () => {
    const captured = captureRequests(() => null)
    await deleteNetworkSegment(5, { confirm: 'management', version: 3 })
    expect(captured[0].method).toBe('delete')
    expect(captured[0].url).toBe('/network-segments/5')
    expect(captured[0].params).toEqual({ confirm: 'management', version: 3 })
  })
})

describe('保留地址与网关端点（Contract §3.1–3.4）', () => {
  it('listReservedAddresses：GET /network-segments/{id}/reserved-addresses', async () => {
    const captured = captureRequests(() => ({ items: [reserved] }))
    const result = await listReservedAddresses(5)
    expect(captured[0].method).toBe('get')
    expect(captured[0].url).toBe('/network-segments/5/reserved-addresses')
    expect(result.items[0]?.start_ip).toBe('192.168.1.100')
  })

  it('createReservedAddress：POST body 含 start_ip 与 end_ip（范围）', async () => {
    const captured = captureRequests(() => reserved)
    await createReservedAddress(5, { start_ip: '192.168.1.100', end_ip: '192.168.1.110' })
    expect(captured[0].method).toBe('post')
    expect(captured[0].url).toBe('/network-segments/5/reserved-addresses')
    expect(JSON.parse(captured[0].data as string)).toEqual({
      start_ip: '192.168.1.100',
      end_ip: '192.168.1.110',
    })
  })

  it('createReservedAddress：end_ip 为 null/空时省略（单地址）', async () => {
    const captured = captureRequests(() => ({ ...reserved, end_ip: '192.168.1.100', is_range: false }))
    await createReservedAddress(5, { start_ip: '192.168.1.100', end_ip: null })
    expect(JSON.parse(captured[0].data as string)).toEqual({ start_ip: '192.168.1.100' })
  })

  it('deleteReservedAddress：DELETE /network-segments/{id}/reserved-addresses/{reserved_id}', async () => {
    const captured = captureRequests(() => null)
    await deleteReservedAddress(5, 11)
    expect(captured[0].method).toBe('delete')
    expect(captured[0].url).toBe('/network-segments/5/reserved-addresses/11')
  })

  it('clearNetworkSegmentGateway：DELETE /network-segments/{id}/gateway?version=', async () => {
    const captured = captureRequests(() => null)
    await clearNetworkSegmentGateway(5, 3)
    expect(captured[0].method).toBe('delete')
    expect(captured[0].url).toBe('/network-segments/5/gateway')
    expect(captured[0].params).toEqual({ version: 3 })
  })
})

describe('网段错误映射（problem+json → ApiError；401/403 走全局，其余由页面处理）', () => {
  it.each([
    'SEGMENT_NAME_TAKEN',
    'SEGMENT_CIDR_TAKEN',
    'SEGMENT_HAS_RESERVED_ADDRESSES',
    'SEGMENT_GATEWAY_NOT_CLEARED',
    'SEGMENT_HAS_INTERFACES',
    'SEGMENT_HAS_ALLOCATIONS',
    'CIDR_IMMUTABLE',
    'VERSION_CONFLICT',
  ])('409 %s → ApiError 原样抛给页面，不触发全局处理器（页面保留输入提示）', async (code) => {
    const handlers = {
      onUnauthorized: vi.fn(),
      onForbidden: vi.fn(),
      onPasswordChangeRequired: vi.fn(),
    }
    setApiHandlers(handlers)
    useTestAdapter(() => ({ status: 409, data: problemBody(code, '冲突', undefined, 409) }))

    const error = await client.post('/network-segments', {}).catch((e: unknown) => e)
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
  })

  it('422 DELETE_CONFIRMATION_MISMATCH → code 可读（删除确认不匹配，页面保留对话框）', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('DELETE_CONFIRMATION_MISMATCH', '确认输入与网段名称不匹配'),
    }))
    const error = await client
      .delete('/network-segments/5', { params: { confirm: 'x', version: 3 } })
      .catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(422)
      expect(error.code).toBe('DELETE_CONFIRMATION_MISMATCH')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('422 VALIDATION_ERROR（gateway GATEWAY_OUT_OF_CIDR）→ errors[] 可经 fieldError 读取', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('VALIDATION_ERROR', '字段校验失败', [
        { field: 'gateway', code: 'GATEWAY_OUT_OF_CIDR', message: '网关必须落在所属网段 CIDR 内' },
      ]),
    }))
    const error = await client.post('/network-segments', {}).catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.code).toBe('VALIDATION_ERROR')
      expect(error.fieldError('gateway')).toBe('网关必须落在所属网段 CIDR 内')
      expect(error.fieldError('cidr')).toBeUndefined()
    } else {
      expect.unreachable('应为 ApiError')
    }
  })

  it('422 VALIDATION_ERROR（保留地址 RESERVED_OVERLAP）→ 字段级错误可读', async () => {
    useTestAdapter(() => ({
      status: 422,
      data: problemBody('VALIDATION_ERROR', '字段校验失败', [
        { field: 'start_ip', code: 'RESERVED_OVERLAP', message: '与既有保留范围重叠' },
      ]),
    }))
    const error = await client
      .post('/network-segments/5/reserved-addresses', { start_ip: '192.168.1.100' })
      .catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.code).toBe('VALIDATION_ERROR')
      expect(error.fieldError('start_ip')).toBe('与既有保留范围重叠')
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
    useTestAdapter(() => ({ status: 403, data: problemBody('FORBIDDEN', '没有权限', undefined, 403) }))
    await client.post('/network-segments', {}).catch(() => undefined)
    expect(onForbidden).toHaveBeenCalledTimes(1)
  })

  it('401 UNAUTHENTICATED → 触发全局 onUnauthorized（跳登录）', async () => {
    const onUnauthorized = vi.fn()
    setApiHandlers({
      onUnauthorized,
      onForbidden: vi.fn(),
      onPasswordChangeRequired: vi.fn(),
    })
    useTestAdapter(() => ({ status: 401, data: problemBody('UNAUTHENTICATED', '未登录', undefined, 401) }))
    await client.get('/network-segments').catch(() => undefined)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('404 SEGMENT_NOT_FOUND / RESERVED_ADDRESS_NOT_FOUND → ApiError 携带 code，由页面刷新', async () => {
    useTestAdapter(() => ({ status: 404, data: problemBody('SEGMENT_NOT_FOUND', '网段不存在', undefined, 404) }))
    const error = await client.get('/network-segments/999').catch((e: unknown) => e)
    if (isApiError(error)) {
      expect(error.status).toBe(404)
      expect(error.code).toBe('SEGMENT_NOT_FOUND')
    } else {
      expect.unreachable('应为 ApiError')
    }
  })
})
