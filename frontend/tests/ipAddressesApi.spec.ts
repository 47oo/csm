import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as ipAddressesApi from '../src/api/ipAddresses'
import {
  createIpAddress,
  deleteIpAddress,
  getIpAddress,
  listIpAddresses,
  updateIpAddress,
} from '../src/api/ipAddresses'
import type { IpAddressRead } from '../src/api/ipAddresses'
import { ApiError } from '../src/api/http'

/**
 * IPAddress API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）、契约错误
 * 语义透传与结构性约束（G-17 / AC-42：字段封闭、无 cluster_id、无格式校验 /
 * 归一化 / 唯一性预检辅助）。契约依据：docs/api/f005-ip-address.md（READY）。
 * fetch 全部桩替换，不触达真实后端。
 */

/** 契约 §2 示例资源：恰 5 字段。 */
const IP_ADDRESS_A = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.1.1/16',
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

describe('结构性约束（G-17 / AC-07 / AC-42）', () => {
  const source = readFileSync(resolve(process.cwd(), 'src/api/ipAddresses.ts'), 'utf-8')

  it('客户端不存在 cluster_id 字样（NQ-4：请求侧永不被接受、响应侧不暴露）', () => {
    expect(source).not.toContain('cluster_id')
  })

  it('运行时导出面恰为 5 个端点函数：无格式校验 / 归一化 / 唯一性预检辅助（契约 §7 / §21）', () => {
    expect(Object.keys(ipAddressesApi).sort()).toEqual([
      'createIpAddress',
      'deleteIpAddress',
      'getIpAddress',
      'listIpAddresses',
      'updateIpAddress',
    ])
  })

  it('源码不含变换调用（去除空白 / 大小写折叠 / Unicode 归一化 / 正则）', () => {
    for (const token of ['.trim(', '.toLowerCase(', '.toUpperCase(', '.normalize(', 'RegExp']) {
      expect(source).not.toContain(token)
    }
  })

  it('IpAddressRead 字段集合封闭（契约 §2）：恰为 5 字段（编译期穷举断言）', () => {
    // 若 IpAddressRead 增删字段，该字面量的多余 / 缺失属性均导致 typecheck 失败。
    const exhaustive: Record<keyof IpAddressRead, true> = {
      id: true,
      network_interface_id: true,
      ip_address: true,
      created_at: true,
      updated_at: true,
    }
    expect(exhaustive).toBeDefined()
  })
})

describe('请求构造（契约 §3）', () => {
  it('listIpAddresses 默认参数 → GET /api/ip-addresses（无查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [IP_ADDRESS_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listIpAddresses()

    expect(data).toEqual({ items: [IP_ADDRESS_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listIpAddresses 显式分页 + networkInterfaceId → 查询参数拼接 network_interface_id（契约 §3.2）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listIpAddresses({ page: 2, page_size: 20, networkInterfaceId: 12 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses?page=2&page_size=20&network_interface_id=12',
      expect.anything(),
    )
  })

  it('listIpAddresses 仅 networkInterfaceId → 只携带 network_interface_id 查询参数', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [IP_ADDRESS_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listIpAddresses({ networkInterfaceId: 12 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses?network_interface_id=12',
      expect.anything(),
    )
  })

  it('getIpAddress → GET /api/ip-addresses/{id}（规范路径，写读均走 id；无 by-name）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, IP_ADDRESS_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getIpAddress(41)

    expect(data).toEqual(IP_ADDRESS_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses/41',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('createIpAddress → POST /api/ip-addresses，JSON 请求体恰为两字段（契约 §3.1 schema 封闭）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, IP_ADDRESS_A))
    vi.stubGlobal('fetch', fetchMock)

    await createIpAddress({ network_interface_id: 12, ip_address: '10.0.1.1/16' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ network_interface_id: 12, ip_address: '10.0.1.1/16' }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('createIpAddress 原样提交未定义约束取值（空串 / 首尾空白 / not-an-ip，契约 §7：不做任何变换）', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(201, { ...IP_ADDRESS_A, id: 42 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    // 三个字面值均不做校验 / 修剪 / 归一化，按用户输入原样提交。
    await createIpAddress({ network_interface_id: 12, ip_address: '' })
    await createIpAddress({ network_interface_id: 12, ip_address: ' 10.0.1.1/16 ' })
    await createIpAddress({ network_interface_id: 12, ip_address: 'not-an-ip' })

    const bodies = fetchMock.mock.calls.map(
      (call) => JSON.parse((call[1] as RequestInit).body as string) as { ip_address: string },
    )
    expect(bodies.map((body) => body.ip_address)).toEqual(['', ' 10.0.1.1/16 ', 'not-an-ip'])
  })

  it('updateIpAddress → PATCH /api/ip-addresses/{id}（可变字段恰为 ip_address，契约 §3.4）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...IP_ADDRESS_A, ip_address: '10.0.1.2/16' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateIpAddress(41, { ip_address: '10.0.1.2/16' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses/41',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ ip_address: '10.0.1.2/16' }),
      }),
    )
  })

  it('deleteIpAddress → DELETE /api/ip-addresses/{id}（写操作一律走 id；不发送请求体，契约 §3.5）', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteIpAddress(41)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses/41',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
    // 契约 §3.5：Request body 无，客户端不得发送 → 不携带 Content-Type。
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })
})

describe('错误语义透传（契约 §4 / §8；api-conventions.md §5 / §6）', () => {
  it('getIpAddress 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §3.3）→ ApiError 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(getIpAddress(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('listIpAddresses（networkInterfaceId 过滤）Empty 语义（父 NIC 存在但无活跃 IP，契约 §9）→ 200 + items == []，不抛出', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 })),
    )

    await expect(listIpAddresses({ networkInterfaceId: 12 })).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    })
  })

  it('listIpAddresses（networkInterfaceId 过滤）404 NOT_FOUND（父 NIC 不存在或已删，契约 §3.2）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(listIpAddresses({ networkInterfaceId: 999 }))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('createIpAddress 400 VALIDATION_ERROR（缺 ip_address，契约 §3.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'ip_address', code: 'INVALID', message: '缺少字段' }],
          },
        }),
      ),
    )

    // 类型断言仅为通过编译：构造缺字段场景由服务端响应表达。
    const err = await expectApiError(
      createIpAddress({ network_interface_id: 12, ip_address: 'x' }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('ip_address')
    expect(err.details[0]?.code).toBe('INVALID')
  })

  it('createIpAddress 404 NOT_FOUND（父 NIC 不存在 / 已删 / 宿主不活跃，契约 §3.1）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(
      createIpAddress({ network_interface_id: 999, ip_address: '10.0.1.1/16' }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('createIpAddress 409 CONFLICT（同 Cluster 活跃字面重复，契约 §3.1 / §4.1）→ 保留 details[].code === DUPLICATE', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '与展示无关的冲突文案',
            details: [
              {
                field: 'ip_address',
                code: 'DUPLICATE',
                message: '与展示无关的字段文案',
              },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createIpAddress({ network_interface_id: 12, ip_address: '10.0.0.10' }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.field).toBe('ip_address')
    expect(err.details[0]?.code).toBe('DUPLICATE')
  })

  it('updateIpAddress 409 CONFLICT（修正后目标 Cluster 内重复，契约 §3.4 / §4.1）→ 保留 DUPLICATE 判别值', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: 'IP 地址已存在',
            details: [{ field: 'ip_address', code: 'DUPLICATE', message: '重复' }],
          },
        }),
      ),
    )

    const err = await expectApiError(updateIpAddress(41, { ip_address: '10.0.0.10' }))

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('DUPLICATE')
  })

  it('deleteIpAddress 404 NOT_FOUND（重复删除已删记录，契约 §3.5）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(deleteIpAddress(41))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('deleteIpAddress 401 UNAUTHENTICATED（未认证，不改变任何数据）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
      ),
    )

    const err = await expectApiError(deleteIpAddress(41))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
