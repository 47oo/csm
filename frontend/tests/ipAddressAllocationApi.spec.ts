import { afterEach, describe, expect, it, vi } from 'vitest'
import { allocateIpAddress, allocateIpAddressManual } from '../src/api/ipAddresses'
import type { IpAddressRead } from '../src/api/ipAddresses'
import { ApiError } from '../src/api/http'

/**
 * F021 分配 API 客户端测试：请求构造（路径 / 方法 / 请求体恰为契约封闭
 * 字段集合）、原样提交（不校验 / 不修剪 / 不归一化）与契约错误语义透传。
 * 契约依据：docs/api/f021-ip-address-allocation.md（READY，唯一权威）；
 * 错误信封复用 api-conventions.md §5。fetch 全部桩替换，不触达真实后端。
 */

/** 契约 §2 示例资源：复用 F005 IPAddress 表示，恰 5 字段。 */
const ALLOCATED = {
  id: 41,
  network_interface_id: 12,
  ip_address: '10.0.0.5',
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
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

/** 取某次 POST 调用的已解析请求体。 */
function postedBody(fetchMock: ReturnType<typeof vi.fn>, url: string): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(
    ([input, init]) => String(input) === url && (init as RequestInit | undefined)?.method === 'POST',
  )
  if (call === undefined) throw new Error(`期望存在对 ${url} 的 POST 调用`)
  return JSON.parse((call[1] as RequestInit).body as string) as Record<string, unknown>
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('请求构造（契约 §3）', () => {
  it('allocateIpAddress → POST /api/ip-addresses/allocate，请求体恰为 {network_interface_id}（§3.1 schema 封闭）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, ALLOCATED))
    vi.stubGlobal('fetch', fetchMock)

    const data = await allocateIpAddress({ network_interface_id: 12 })

    expect(data).toEqual(ALLOCATED)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses/allocate',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ network_interface_id: 12 }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
    // 字段集合封闭：不携带任何未识别字段（cluster 归属 / 状态 / 模式等均属 400）。
    expect(postedBody(fetchMock, '/api/ip-addresses/allocate')).toEqual({
      network_interface_id: 12,
    })
  })

  it('allocateIpAddressManual → POST /api/ip-addresses/allocate-manual，请求体恰为两字段（§3.2 schema 封闭）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, ALLOCATED))
    vi.stubGlobal('fetch', fetchMock)

    const data = await allocateIpAddressManual({ network_interface_id: 12, ip_address: '10.0.0.5' })

    expect(data).toEqual(ALLOCATED)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-addresses/allocate-manual',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ network_interface_id: 12, ip_address: '10.0.0.5' }),
      }),
    )
    expect(postedBody(fetchMock, '/api/ip-addresses/allocate-manual')).toEqual({
      network_interface_id: 12,
      ip_address: '10.0.0.5',
    })
  })

  it('allocateIpAddressManual 原样提交客户端不做裁决的取值（非法格式 / 首尾空白 / 前导零），不做任何变换（§21 / 契约 §7）', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(201, { ...ALLOCATED, id: 42 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    // 三个字面值均不做校验 / 修剪 / 归一化，按用户输入原样提交：
    // 格式 / 范围 / 占用与规范化全部由服务端裁决。
    await allocateIpAddressManual({ network_interface_id: 12, ip_address: 'abc' })
    await allocateIpAddressManual({ network_interface_id: 12, ip_address: ' 10.0.0.5 ' })
    await allocateIpAddressManual({ network_interface_id: 12, ip_address: '010.0.0.5' })

    const bodies = fetchMock.mock.calls.map(
      (call) => JSON.parse((call[1] as RequestInit).body as string) as { ip_address: string },
    )
    expect(bodies.map((body) => body.ip_address)).toEqual(['abc', ' 10.0.0.5 ', '010.0.0.5'])
  })

  it('成功响应（201）复用 F005 IPAddress 表示（恰 5 字段，编译期穷举断言）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) =>
        String(_input).endsWith('/allocate')
          ? jsonResponse(201, ALLOCATED)
          : jsonResponse(201, { ...ALLOCATED, ip_address: '10.0.0.6' }),
      ),
    )

    const auto = await allocateIpAddress({ network_interface_id: 12 })
    const manual = await allocateIpAddressManual({ network_interface_id: 12, ip_address: '10.0.0.6' })

    // 若 IpAddressRead 增删字段，该字面量的多余 / 缺失属性均导致 typecheck 失败。
    const exhaustiveAuto: Record<keyof IpAddressRead, true> = {
      id: true,
      network_interface_id: true,
      ip_address: true,
      created_at: true,
      updated_at: true,
    }
    expect(exhaustiveAuto).toBeDefined()
    expect(Object.keys(auto).sort()).toEqual([
      'created_at',
      'id',
      'ip_address',
      'network_interface_id',
      'updated_at',
    ])
    expect(Object.keys(manual).sort()).toEqual([
      'created_at',
      'id',
      'ip_address',
      'network_interface_id',
      'updated_at',
    ])
  })
})

/** 契约 §4：message 不构成契约；使用与展示无关的文案，证明前端不解析 message。 */
const VALIDATION_BODY = {
  error: {
    code: 'VALIDATION_ERROR',
    message: '与展示无关的校验文案',
    details: [{ field: 'ip_address', code: 'INVALID', message: '与展示无关的字段提示' }],
  },
}
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }
const NO_AVAILABLE_IP_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的耗尽文案',
    details: [
      { row: null, field: null, code: 'NO_AVAILABLE_IP', message: '与展示无关的耗尽详情' },
    ],
  },
}
const OUT_OF_RANGE_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的范围文案',
    details: [
      { row: null, field: 'ip_address', code: 'OUT_OF_RANGE', message: '与展示无关的范围详情' },
    ],
  },
}
const DUPLICATE_BODY = {
  error: {
    code: 'CONFLICT',
    message: '与展示无关的占用文案',
    details: [
      { row: null, field: 'ip_address', code: 'DUPLICATE', message: '与展示无关的占用详情' },
    ],
  },
}
const UNAUTHENTICATED_BODY = { error: { code: 'UNAUTHENTICATED', message: '与展示无关的未认证文案' } }

describe('错误语义透传（契约 §4 / §8；api-conventions.md §5 / §6）', () => {
  it('400 VALIDATION_ERROR（ip_address 非法 IPv4，契约 §3.2）→ 保留 details[].field / details[].code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(400, VALIDATION_BODY)))

    const err = await expectApiError(
      allocateIpAddressManual({ network_interface_id: 12, ip_address: '10.0.0.256' }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('ip_address')
    expect(err.details[0]?.code).toBe('INVALID')
  })

  it('404 NOT_FOUND（目标 NIC 不存在 / 已删 / 宿主 BareMetal 不活跃，契约 §3.1 / §3.2）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } })),
    )

    const autoErr = await expectApiError(allocateIpAddress({ network_interface_id: 999 }))
    const manualErr = await expectApiError(
      allocateIpAddressManual({ network_interface_id: 999, ip_address: '10.0.0.5' }),
    )

    expect(autoErr.status).toBe(404)
    expect(autoErr.code).toBe('NOT_FOUND')
    expect(autoErr.details).toEqual([])
    expect(manualErr.code).toBe('NOT_FOUND')
    expect(manualErr.details).toEqual([])
  })

  it('409 CONFLICT + NO_AVAILABLE_IP（自动分配：并集耗尽 / 无活跃范围段，契约 §4.1）→ 保留稳定判别值', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(409, NO_AVAILABLE_IP_BODY)))

    const err = await expectApiError(allocateIpAddress({ network_interface_id: 12 }))

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('NO_AVAILABLE_IP')
    expect(err.details[0]?.field).toBeNull()
  })

  it('409 CONFLICT + OUT_OF_RANGE（手动分配：合法 IPv4 范围外，契约 §4.2）→ 保留稳定判别值', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(409, OUT_OF_RANGE_BODY)))

    const err = await expectApiError(
      allocateIpAddressManual({ network_interface_id: 12, ip_address: '192.168.1.1' }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('OUT_OF_RANGE')
    expect(err.details[0]?.field).toBe('ip_address')
  })

  it('409 CONFLICT + DUPLICATE（已占用 / 并发落败，契约 §4.3）→ 保留稳定判别值', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(409, DUPLICATE_BODY)))

    const err = await expectApiError(
      allocateIpAddressManual({ network_interface_id: 12, ip_address: '10.0.0.5' }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('DUPLICATE')
    expect(err.details[0]?.field).toBe('ip_address')
  })

  it('401 UNAUTHENTICATED（未认证，不改变任何数据，契约 §5）→ 保留 code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, UNAUTHENTICATED_BODY)))

    const err = await expectApiError(allocateIpAddress({ network_interface_id: 12 }))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
