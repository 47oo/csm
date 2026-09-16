import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  VIRTUAL_MACHINE_OPTIONAL_FIELDS,
  createVirtualMachine,
  deleteVirtualMachine,
  getVirtualMachine,
  listVirtualMachines,
  updateVirtualMachine,
} from '../src/api/virtualMachines'
import { ApiError } from '../src/api/http'

/**
 * VirtualMachine API 客户端测试：请求构造（路径 / 方法 / 查询 / 请求体）与
 * 契约错误语义透传。契约依据：docs/api/f006-virtual-machine.md（READY）。
 * fetch 全部桩替换，不触达真实后端。
 */

const VIRTUAL_MACHINE_A = {
  id: 7,
  bare_metal_id: 3,
  name: 'vm1',
  cpu: '8 vCPU',
  memory: '32 GB',
  disk: '500 GB',
  os: 'Ubuntu 22.04',
  hypervisor: 'PVE',
  owner: 'ops',
  created_at: '2026-09-16T10:00:00Z',
  updated_at: '2026-09-16T10:00:00Z',
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
  it('listVirtualMachines 默认参数 → GET /api/virtual-machines（无查询串，服务端默认 page=1 / page_size=50）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [VIRTUAL_MACHINE_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await listVirtualMachines()

    expect(data).toEqual({ items: [VIRTUAL_MACHINE_A], total: 1, page: 1, page_size: 50 })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/virtual-machines',
      expect.objectContaining({ method: 'GET', body: undefined }),
    )
  })

  it('listVirtualMachines 显式分页 + bareMetalId → 查询参数拼接 bare_metal_id（契约 §3.2）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 2, page_size: 20 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listVirtualMachines({ page: 2, page_size: 20, bareMetalId: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/virtual-machines?page=2&page_size=20&bare_metal_id=3',
      expect.anything(),
    )
  })

  it('listVirtualMachines 仅 bareMetalId → 只携带 bare_metal_id 查询参数', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { items: [VIRTUAL_MACHINE_A], total: 1, page: 1, page_size: 50 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await listVirtualMachines({ bareMetalId: 3 })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/virtual-machines?bare_metal_id=3',
      expect.anything(),
    )
  })

  it('getVirtualMachine → GET /api/virtual-machines/{id}（规范路径，写读均走 id）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, VIRTUAL_MACHINE_A))
    vi.stubGlobal('fetch', fetchMock)

    const data = await getVirtualMachine(7)

    expect(data).toEqual(VIRTUAL_MACHINE_A)
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/virtual-machines/7',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('createVirtualMachine → POST /api/virtual-machines，JSON 请求体含必填字段与可选字段', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(201, { ...VIRTUAL_MACHINE_A, id: 8, name: 'vm2' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await createVirtualMachine({
      bare_metal_id: 3,
      name: 'vm2',
      cpu: '8 vCPU',
      owner: null,
    })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/virtual-machines',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ bare_metal_id: 3, name: 'vm2', cpu: '8 vCPU', owner: null }),
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('updateVirtualMachine → PATCH /api/virtual-machines/{id}（部分更新，仅六字段；null 清空）', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { ...VIRTUAL_MACHINE_A, cpu: '16 vCPU', memory: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateVirtualMachine(7, { cpu: '16 vCPU', memory: null })

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/virtual-machines/7',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ cpu: '16 vCPU', memory: null }),
      }),
    )
  })

  it('deleteVirtualMachine → DELETE /api/virtual-machines/{id}（写操作一律走 id；不发送请求体，契约 §3.5）', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await deleteVirtualMachine(7)

    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/virtual-machines/7',
      expect.objectContaining({ method: 'DELETE', body: undefined }),
    )
    // 契约 §3.5：Request body 无，客户端不得发送 → 不携带 Content-Type。
    const headers = (fetchMock.mock.calls[0]![1] as RequestInit).headers as Record<string, string>
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('R-VM-006 可选字段常量恰为六字段（cpu / memory / disk / os / hypervisor / owner）', () => {
    expect([...VIRTUAL_MACHINE_OPTIONAL_FIELDS]).toEqual([
      'cpu',
      'memory',
      'disk',
      'os',
      'hypervisor',
      'owner',
    ])
  })
})

describe('错误语义透传（契约 §8；api-conventions.md §5 / §6）', () => {
  it('getVirtualMachine 404 NOT_FOUND（不存在或已逻辑删除，两者不区分，契约 §3.3）→ ApiError 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(getVirtualMachine(999))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('listVirtualMachines（bareMetalId 过滤）404 NOT_FOUND（宿主不存在或已删，契约 §3.2）→ 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在' } }),
      ),
    )

    const err = await expectApiError(listVirtualMachines({ bareMetalId: 999 }))

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
  })

  it('listVirtualMachines Empty 语义（200 + items == []，契约 §9）→ 成功返回，不抛出', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 50 })),
    )

    await expect(listVirtualMachines()).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    })
  })

  it('createVirtualMachine 400 VALIDATION_ERROR（缺 name，契约 §3.1）→ 保留 details[].field', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(400, {
          error: {
            code: 'VALIDATION_ERROR',
            message: '请求校验失败',
            details: [{ field: 'name', message: '字段缺失' }],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createVirtualMachine({ bare_metal_id: 3, name: 'vm1' }),
    )

    expect(err.status).toBe(400)
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.details[0]?.field).toBe('name')
  })

  it('createVirtualMachine 409 CONFLICT（全局活跃 name 重复，契约 §4.1）→ 保留 details[].field / code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(409, {
          error: {
            code: 'CONFLICT',
            message: 'VirtualMachine 名称已存在',
            details: [
              { field: 'name', code: 'DUPLICATE', message: '已存在活跃的同名 VirtualMachine' },
            ],
          },
        }),
      ),
    )

    const err = await expectApiError(
      createVirtualMachine({ bare_metal_id: 3, name: 'vm1' }),
    )

    expect(err.status).toBe(409)
    expect(err.code).toBe('CONFLICT')
    expect(err.details[0]?.field).toBe('name')
    expect(err.details[0]?.code).toBe('DUPLICATE')
  })

  it('createVirtualMachine 404 NOT_FOUND（引用不存在 / 已删宿主，契约 §3.1 / NQ-2）→ 保留 code 与空 details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(404, { error: { code: 'NOT_FOUND', message: '资源不存在', details: [] } }),
      ),
    )

    const err = await expectApiError(
      createVirtualMachine({ bare_metal_id: 999, name: 'vm1' }),
    )

    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.details).toEqual([])
  })

  it('deleteVirtualMachine 401 UNAUTHENTICATED（未认证，不改变任何数据）→ ApiError 保留 code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '未认证' } }),
      ),
    )

    const err = await expectApiError(deleteVirtualMachine(7))

    expect(err.status).toBe(401)
    expect(err.code).toBe('UNAUTHENTICATED')
  })
})
