import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as ipAddressRangesApi from '../src/api/ipAddressRanges'
import {
  createIpAddressRange,
  deleteIpAddressRange,
  getIpAddressRange,
  listIpAddressRanges,
  updateIpAddressRange,
} from '../src/api/ipAddressRanges'
import type { IpAddressRangeRead } from '../src/api/ipAddressRanges'
import { ApiError } from '../src/api/http'

/**
 * IPAddressRange API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）、
 * 契约错误语义透传与结构性约束（字段封闭、无状态 / 无 name / 无 deleted_at、
 * 无 IPv4 校验 / 归一化 / start<=end 预判 / 重叠预检辅助）。契约依据：
 * docs/api/f020-ip-address-range.md（READY）。fetch 全部桩替换，不触达真实后端。
 */

/** 契约 §2 示例资源：恰 6 字段。 */
const IP_ADDRESS_RANGE_A = {
  id: 7,
  cluster_id: 3,
  start_ip: '10.0.0.1',
  end_ip: '10.0.0.255',
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-20T10:00:00Z',
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

describe('结构性约束（字段封闭 / §21 不重复实现业务守卫）', () => {
  const source = readFileSync(resolve(process.cwd(), 'src/api/ipAddressRanges.ts'), 'utf-8')

  it('运行时导出面恰为 5 个端点函数：无 IPv4 校验 / 归一化 / start<=end 预判 / 重叠预检辅助（契约 §7 / §21）', () => {
    expect(Object.keys(ipAddressRangesApi).sort()).toEqual([
      'createIpAddressRange',
      'deleteIpAddressRange',
      'getIpAddressRange',
      'listIpAddressRanges',
      'updateIpAddressRange',
    ])
  })

  it('源码不含变换 / 解析调用（去除空白 / 大小写折叠 / Unicode 归一化 / 正则 / 数值解析）', () => {
    for (const token of ['.trim(', '.toLowerCase(', '.toUpperCase(', '.normalize(', 'RegExp', 'parseInt']) {
      expect(source).not.toContain(token)
    }
  })

  it('IpAddressRangeRead 字段集合封闭（契约 §2）：恰为 6 字段（编译期穷举断言）', () => {
    // 若 IpAddressRangeRead 增删字段，该字面量的多余 / 缺失属性均导致 typecheck 失败。
    // 不存在 status / deleted_at / name / description（契约 §2 / §10）。
    const exhaustive: Record<keyof IpAddressRangeRead, true> = {
      id: true,
      cluster_id: true,
      start_ip: true,
      end_ip: true,
      created_at: true,
      updated_at: true,
    }
    expect(exhaustive).toBeDefined()
  })

  it('契约 §2 示例资源恰为 6 字段（运行时字段集合与类型声明一致）', () => {
    expect(Object.keys(IP_ADDRESS_RANGE_A).sort()).toEqual([
      'cluster_id',
      'created_at',
      'end_ip',
      'id',
      'start_ip',
      'updated_at',
    ])
  })
})

describe('请求构造（契约 §3）', () => {
  it('listIpAddressRanges 默认参数 → GET /api/ip-address-ranges（无查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [IP_ADDRESS_RANGE_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listIpAddressRanges()

    expect(data).toEqual({ items: [IP_ADDRESS_RANGE_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listIpAddressRanges 显式分页 + cluster_id → 查询参数拼接 cluster_id（契约 §3.2）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listIpAddressRanges({ page: 2, page_size: 20, cluster_id: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges?page=2&page_size=20&cluster_id=3',
      expect.anything(),
    )
  })

  it('listIpAddressRanges 仅 cluster_id → 只携带 cluster_id 查询参数', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [IP_ADDRESS_RANGE_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listIpAddressRanges({ cluster_id: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges?cluster_id=3',
      expect.anything(),
    )
  })

  it('getIpAddressRange → GET /api/ip-address-ranges/{id}（规范路径，写读均走 id；无 by-name）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, IP_ADDRESS_RANGE_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getIpAddressRange(7)

    expect(data).toEqual(IP_ADDRESS_RANGE_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges/7',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('createIpAddressRange → POST /api/ip-address-ranges，JSON 请求体恰为三字段（契约 §3.1 schema 封闭）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, IP_ADDRESS_RANGE_A))
    vi.stubGlobal('fetch', fetchMock)

    await createIpAddressRange({ cluster_id: 3, start_ip: '10.0.0.1', end_ip: '10.0.0.255' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ cluster_id: 3, start_ip: '10.0.0.1', end_ip: '10.0.0.255' }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('createIpAddressRange 原样提交未定义 / 非法 / 反序取值（契约 §7 / §21：不做任何变换与预判）', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(201, { ...IP_ADDRESS_RANGE_A, id: 8 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    // 非规范写法（前导零）、非法 IPv4、start > end、首尾空白均不做校验 / 修剪 /
    // 归一化，按用户输入原样提交，由服务端裁决（§21）。
    await createIpAddressRange({ cluster_id: 3, start_ip: '010.000.000.001', end_ip: '10.0.0.255' })
    await createIpAddressRange({ cluster_id: 3, start_ip: 'abc', end_ip: '10.0.0.256' })
    await createIpAddressRange({ cluster_id: 3, start_ip: '10.0.1.9', end_ip: '10.0.1.1' })
    await createIpAddressRange({ cluster_id: 3, start_ip: ' 10.0.0.1 ', end_ip: ' 10.0.0.255 ' })

    const bodies = fetchMock.mock.calls.map(
      (call) => JSON.parse((call[1] as RequestInit).body as string) as Record<string, string>,
    )
    expect(bodies.map((body) => [body.start_ip, body.end_ip])).toEqual([
      ['010.000.000.001', '10.0.0.255'],
      ['abc', '10.0.0.256'],
      ['10.0.1.9', '10.0.1.1'],
      [' 10.0.0.1 ', ' 10.0.0.255 '],
    ])
  })

  it('updateIpAddressRange → PATCH /api/ip-address-ranges/{id}（可变字段恰为 start_ip / end_ip，契约 §3.4）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...IP_ADDRESS_RANGE_A, end_ip: '10.0.1.255' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateIpAddressRange(7, { start_ip: '10.0.0.1', end_ip: '10.0.1.255' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ start_ip: '10.0.0.1', end_ip: '10.0.1.255' }),
      }),
    )
  })

  it('updateIpAddressRange 部分更新 → 仅提交提供的可变字段（契约 §3.4 部分更新语义）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, IP_ADDRESS_RANGE_A))
    vi.stubGlobal('fetch', fetchMock)

    await updateIpAddressRange(7, { end_ip: '10.0.0.254' })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ end_ip: '10.0.0.254' }),
      }),
    )
  })

  it('deleteIpAddressRange → DELETE /api/ip-address-ranges/{id}（写操作一律走 id；不发送请求体，契约 §3.5）', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteIpAddressRange(7)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/ip-address-ranges/7',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
    // 契约 §3.5：Request body 无，客户端不得发送 → 不携带 Content-Type。
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })
})

describe('错误语义透传（契约 §4 / §8；api-conventions.md §5 / §6）', () => {
  it('listIpAddressRanges（cluster_id 过滤）Empty 语义（Cluster 存在但无活跃范围段，契约 §9）→ 200 + items == []，不抛出', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 })),
    )

    await expect(listIpAddressRanges({ cluster_id: 3 })).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    })
  })

  it('listIpAddressRanges（cluster_id 过滤）404 NOT_FOUND（Cluster 不存在或已删，契约 §3.2）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(listIpAddressRanges({ cluster_id: 999 }))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('getIpAddressRange 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §3.3）→ ApiError 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(getIpAddressRange(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('createIpAddressRange 400 VALIDATION_ERROR（非法 start_ip，契约 §3.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'start_ip', code: 'INVALID', message: '缺少字段' }],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createIpAddressRange({ cluster_id: 3, start_ip: 'x', end_ip: '10.0.0.255' }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('start_ip')
    expect(err.details[0]?.code).toBe('INVALID')
  })

  it('createIpAddressRange 404 NOT_FOUND（父 Cluster 不存在 / 已删，契约 §3.1）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(
      createIpAddressRange({ cluster_id: 999, start_ip: '10.0.0.1', end_ip: '10.0.0.255' }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('createIpAddressRange 409 CONFLICT + details[].code === OVERLAP（同 Cluster 重叠，契约 §3.1 / §4.1）→ 保留判别值', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '与展示无关的冲突文案',
            details: [
              { row: null, field: null, code: 'OVERLAP', message: '与展示无关的重叠文案' },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createIpAddressRange({ cluster_id: 3, start_ip: '10.0.0.100', end_ip: '10.0.0.200' }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('OVERLAP')
  })

  it('updateIpAddressRange 409 CONFLICT + details[].code === OVERLAP（修正后重叠，契约 §3.4 / §4.1）→ 保留判别值', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '范围段重叠',
            details: [{ row: null, field: null, code: 'OVERLAP', message: '重叠' }],
          },
        }),
      ),
    )

    const err = await expectApiError(
      updateIpAddressRange(7, { start_ip: '10.0.0.1', end_ip: '10.0.5.255' }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('OVERLAP')
  })

  it('updateIpAddressRange 404 NOT_FOUND（目标不存在或已删，契约 §3.4）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(updateIpAddressRange(999, { start_ip: '10.0.0.1' }))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('deleteIpAddressRange 409 CONFLICT + details[].code === ACTIVE_CHILDREN_EXIST（范围内仍有活跃 IP，契约 §3.5 / §4.2）→ 保留判别值', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: '与展示无关的父资源冲突文案',
            details: [
              {
                row: null,
                field: null,
                code: 'ACTIVE_CHILDREN_EXIST',
                message: '与展示无关的子项文案',
              },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(deleteIpAddressRange(7))

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.code).toBe('ACTIVE_CHILDREN_EXIST')
  })

  it('deleteIpAddressRange 404 NOT_FOUND（重复删除已删记录，契约 §3.5）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(deleteIpAddressRange(7))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('deleteIpAddressRange 401 UNAUTHENTICATED（未认证，不改变任何数据）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
      ),
    )

    const err = await expectApiError(deleteIpAddressRange(7))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
