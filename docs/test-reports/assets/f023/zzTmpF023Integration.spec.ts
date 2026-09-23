// @vitest-environment node
/**
 * 临时 F023 真实前后端集成探针（Tester）。
 *
 * 用真实 `frontend/src/api/**` 客户端经 cookie 罐直连真实 uvicorn + 真实 PG。
 * 运行方式（先外部启动 uvicorn 于端口 8800）：
 *
 *   F023_BASE=http://127.0.0.1:8800 npx vitest run tests/zzTmpF023Integration.spec.ts
 *
 * 运行后删除，不保留源码改动。
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { login } from '../src/api/auth'
import { createCluster } from '../src/api/clusters'
import { createBareMetal } from '../src/api/bareMetals'
import { createNetworkInterface } from '../src/api/networkInterfaces'
import {
  createIpAddressRange,
  deleteIpAddressRange,
  listIpAddressRanges,
} from '../src/api/ipAddressRanges'
import {
  allocateIpAddress,
  allocateIpAddressManual,
  createIpAddress,
} from '../src/api/ipAddresses'
import { ApiError } from '../src/api/http'

const BASE = process.env.F023_BASE ?? 'http://127.0.0.1:8800'
const READ_FIELDS = ['id', 'network_interface_id', 'ip_address', 'created_at', 'updated_at']

let originalFetch: typeof fetch
let cookie = ''

beforeAll(() => {
  originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    let url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    if (url.startsWith('/')) url = BASE + url
    const headers = new Headers(init?.headers ?? {})
    if (cookie) headers.set('cookie', cookie)
    const res = await originalFetch(url, { ...init, headers })
    const anyHeaders = res.headers as unknown as { getSetCookie?: () => string[] }
    const setCookies = typeof anyHeaders.getSetCookie === 'function' ? anyHeaders.getSetCookie() : []
    if (setCookies.length > 0) {
      cookie = setCookies.map((c) => c.split(';')[0]).join('; ')
    } else {
      const sc = res.headers.get('set-cookie')
      if (sc) cookie = sc.split(';')[0]
    }
    return res
  }) as typeof fetch
})

afterAll(() => {
  globalThis.fetch = originalFetch
})

describe('F023 真实前后端集成（真实前端 client → 真实 uvicorn）', () => {
  it('未认证 → 401 UNAUTHENTICATED；登录后完整契约闭环', async () => {
    // 1) 未认证
    await expect(
      allocateIpAddress({ network_interface_id: 1, ip_address_range_id: 1 }),
    ).rejects.toMatchObject({ status: 401, code: 'UNAUTHENTICATED' })

    // 2) 登录（真实 cookie）
    const user = await login({ username: 'tester', password: 'tester-password-123' })
    expect(user.username).toBe('tester')

    // 3) 建链
    const cluster = await createCluster({ name: `f023int-${Date.now()}` })
    const bm = await createBareMetal({ cluster_id: cluster.id, hostname: 'int-n1' })
    const nic = await createNetworkInterface({
      bare_metal_id: bm.id,
      name: 'eth0',
      technology_type: 'Ethernet',
      purpose: 'Business',
    })
    const low = await createIpAddressRange({
      cluster_id: cluster.id,
      start_ip: '10.0.0.1',
      end_ip: '10.0.0.3',
    })
    const high = await createIpAddressRange({
      cluster_id: cluster.id,
      start_ip: '10.0.0.10',
      end_ip: '10.0.0.12',
    })

    // 4) 前端只读链：按 cluster_id 列活跃范围段（对话框下拉的数据来源）
    const listed = await listIpAddressRanges({
      cluster_id: cluster.id,
      page: 1,
      page_size: 200,
    })
    expect(listed.items.map((r) => r.id).sort()).toEqual([low.id, high.id].sort())

    // 5) 自动分配：仅在所选 high 段取最小（不取 low 更小值）
    const a1 = await allocateIpAddress({
      network_interface_id: nic.id,
      ip_address_range_id: high.id,
    })
    expect(Object.keys(a1).sort()).toEqual([...READ_FIELDS].sort())
    expect(a1.ip_address).toBe('10.0.0.10')

    // 6) 跳过已占用 → 下一个
    const a2 = await allocateIpAddress({
      network_interface_id: nic.id,
      ip_address_range_id: high.id,
    })
    expect(a2.ip_address).toBe('10.0.0.11')

    // 7) 手动分配规范化
    const m = await allocateIpAddressManual({
      network_interface_id: nic.id,
      ip_address: '010.000.000.002',
    })
    expect(m.ip_address).toBe('10.0.0.2')

    // 8) 引用其它 Cluster 的活跃范围段 → 409 + IP_ADDRESS_RANGE_UNAVAILABLE
    const cluster2 = await createCluster({ name: `f023int2-${Date.now()}` })
    const other = await createIpAddressRange({
      cluster_id: cluster2.id,
      start_ip: '10.9.0.1',
      end_ip: '10.9.0.9',
    })
    const crossErr = await allocateIpAddress({
      network_interface_id: nic.id,
      ip_address_range_id: other.id,
    }).catch((e: unknown) => e)
    expect(crossErr).toBeInstanceOf(ApiError)
    expect(crossErr as ApiError).toMatchObject({ status: 409, code: 'CONFLICT' })
    expect((crossErr as ApiError).details[0]?.code).toBe('IP_ADDRESS_RANGE_UNAVAILABLE')

    // 9) 不存在的范围段 → 404 + 同 code
    const missingErr = await allocateIpAddress({
      network_interface_id: nic.id,
      ip_address_range_id: 999999999,
    }).catch((e: unknown) => e)
    expect(missingErr as ApiError).toMatchObject({ status: 404, code: 'NOT_FOUND' })
    expect((missingErr as ApiError).details[0]?.code).toBe('IP_ADDRESS_RANGE_UNAVAILABLE')

    // 10) 缺 ip_address_range_id → 400 + field
    const invalidErr = await allocateIpAddress({
      network_interface_id: nic.id,
    } as unknown as { network_interface_id: number; ip_address_range_id: number }).catch(
      (e: unknown) => e,
    )
    expect(invalidErr as ApiError).toMatchObject({ status: 400, code: 'VALIDATION_ERROR' })
    expect((invalidErr as ApiError).details.some((d) => d.field === 'ip_address_range_id')).toBe(
      true,
    )

    // 11) 耗尽 → 409 NO_AVAILABLE_IP（另一个段仍有可用，但不回退）
    const tiny = await createIpAddressRange({
      cluster_id: cluster.id,
      start_ip: '10.0.1.1',
      end_ip: '10.0.1.1',
    })
    const t1 = await allocateIpAddress({
      network_interface_id: nic.id,
      ip_address_range_id: tiny.id,
    })
    expect(t1.ip_address).toBe('10.0.1.1')
    const exhaustedErr = await allocateIpAddress({
      network_interface_id: nic.id,
      ip_address_range_id: tiny.id,
    }).catch((e: unknown) => e)
    expect(exhaustedErr as ApiError).toMatchObject({ status: 409, code: 'CONFLICT' })
    expect((exhaustedErr as ApiError).details[0]?.code).toBe('NO_AVAILABLE_IP')

    // 12) F005 登记端点：范围外字面仍 201
    const f005 = await createIpAddress({
      network_interface_id: nic.id,
      ip_address: '203.0.113.9/32',
    })
    expect(f005.ip_address).toBe('203.0.113.9/32')

    // 13) 软删范围段 → 404 + IP_ADDRESS_RANGE_UNAVAILABLE
    const doomed = await createIpAddressRange({
      cluster_id: cluster.id,
      start_ip: '10.0.0.20',
      end_ip: '10.0.0.22',
    })
    await deleteIpAddressRange(doomed.id)
    const deletedErr = await allocateIpAddress({
      network_interface_id: nic.id,
      ip_address_range_id: doomed.id,
    }).catch((e: unknown) => e)
    expect(deletedErr as ApiError).toMatchObject({ status: 404, code: 'NOT_FOUND' })
    expect((deletedErr as ApiError).details[0]?.code).toBe('IP_ADDRESS_RANGE_UNAVAILABLE')
  })
})