// 资源详情页单测（架构 F003 §2.4/§5，需求 §6.3 / 场景 8）：真实 router（memory history）
// + pinia + Element Plus 下整页挂载，复用 F002/F006 GET /resources/{id}（mock）。
// 覆盖：公共信息渲染（名称/集群/类型/状态含文字/状态来源/状态更新时间/更新时间/管理 IP）、
// 网卡（含 segment 只读摘要）与 IP 表格、无 IP 网卡正常显示（场景 8）、管理 IP 标识、
// 「服务」占位（由后续能力提供）、404 与错误态区分。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import ElementPlus from 'element-plus'
import { routes } from '../router'
import ResourceDetailView from './ResourceDetailView.vue'
import { useClusterStore } from '../stores/clusters'
import { ApiError } from '../api/client'
import { getResource, type ResourceFormDetail } from '../api/resources'

vi.mock('../api/resources', () => ({
  listResources: vi.fn(),
  getResource: vi.fn(),
}))

const mockedGet = vi.mocked(getResource)

const NOW = '2026-09-25T00:00:00Z'

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
  status_updated_at: NOW,
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
      ips: [
        {
          id: 55,
          address: '192.168.1.10',
          segment_id: 3,
          interface_id: 10,
          is_management: true,
          created_at: NOW,
        },
        {
          id: 56,
          address: '192.168.1.11',
          segment_id: 3,
          interface_id: 10,
          is_management: false,
          created_at: NOW,
        },
      ],
      created_at: NOW,
      updated_at: NOW,
    },
    {
      // 场景 8：无 IP 网卡正常显示（ips: []），且未关联网段
      id: 11,
      name: 'ib0',
      segment_id: null,
      segment: null,
      ips: [],
      created_at: NOW,
      updated_at: NOW,
    },
  ],
  management_ip: {
    ip_id: 55,
    address: '192.168.1.10',
    interface_id: 10,
    interface_name: 'eth0',
  },
  version: 3,
  created_at: NOW,
  updated_at: NOW,
}

let router: Router
let pinia: Pinia
let app: ReturnType<typeof createApp> | null = null

function mountView(): void {
  app = createApp(ResourceDetailView)
  app.use(pinia)
  app.use(router)
  app.use(ElementPlus)
  app.mount(document.body.appendChild(document.createElement('div')))
}

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i++) await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  for (let i = 0; i < 10; i++) await nextTick()
}

function pageText(): string {
  return document.body.textContent ?? ''
}

beforeEach(async () => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  mockedGet.mockResolvedValue(detail)
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/clusters/1/resources/7')
  await router.isReady()
})

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('公共信息（§6.3：名称/集群/类型/状态/状态来源/更新时间/管理 IP）', () => {
  it('渲染公共字段：状态含文字、状态来源为操作者用户名（BQ-AA）、时间本地显示', async () => {
    mountView()
    await flush()
    const text = pageText()
    expect(text).toContain('cn001')
    expect(text).toContain('N96P 生产集群')
    expect(text).toContain('裸金属')
    expect(text).toContain('已分配')
    expect(text).toContain('ops01')
    // 管理 IP（资源级摘要：地址 + 所属网卡）
    expect(text).toContain('192.168.1.10')
    expect(text).toContain('eth0')
    // 时间按时区显示（UTC ISO → 本地 YYYY-MM-DD HH:mm:ss）
    expect(text).toMatch(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)
    expect(mockedGet).toHaveBeenCalledWith(7)
  })

  it('无管理 IP：显示占位「—」而非报错', async () => {
    mockedGet.mockResolvedValue({ ...detail, management_ip: null })
    mountView()
    await flush()
    // 描述表：定位「管理 IP」标签单元格，取相邻内容单元格
    const cells = Array.from(document.querySelectorAll('.el-descriptions__cell'))
    const labelIndex = cells.findIndex((c) => c.textContent?.trim() === '管理 IP')
    expect(labelIndex).toBeGreaterThanOrEqual(0)
    expect(cells[labelIndex + 1]?.textContent).toContain('—')
  })
})

describe('网卡与 IP（含无 IP 网卡，场景 8；网段只读摘要；管理 IP 标识）', () => {
  it('渲染网卡名、网段只读摘要（名称/CIDR/用途/技术/VLAN）与各 IP 地址', async () => {
    mountView()
    await flush()
    const text = pageText()
    expect(text).toContain('eth0')
    expect(text).toContain('ib0')
    expect(text).toContain('management')
    expect(text).toContain('192.168.1.0/24')
    expect(text).toContain('管理')
    expect(text).toContain('Ethernet')
    expect(text).toContain('VLAN 100')
    expect(text).toContain('192.168.1.10')
    expect(text).toContain('192.168.1.11')
    // 未关联网段的网卡正常显示
    expect(text).toContain('未关联网段')
  })

  it('无 IP 网卡正常显示「该网卡暂无 IP」（ips: [] 为合法状态）', async () => {
    mountView()
    await flush()
    expect(pageText()).toContain('该网卡暂无 IP')
  })

  it('管理 IP 标识：is_management 的 IP 行带「管理 IP」标识', async () => {
    mountView()
    await flush()
    const tags = Array.from(document.querySelectorAll('.resource-detail-ip-table .el-tag'))
    expect(tags).toHaveLength(1)
    expect(tags[0]?.textContent).toContain('管理 IP')
  })

  it('无网卡资源：显示「该资源尚未登记网卡」（interfaces: [] 合法）', async () => {
    mockedGet.mockResolvedValue({ ...detail, interfaces: [] })
    mountView()
    await flush()
    expect(pageText()).toContain('该资源尚未登记网卡')
  })
})

describe('「服务」占位（F007 后续扩展，本 Feature 仅占位）', () => {
  it('展示服务占位说明（由后续版本提供）', async () => {
    mountView()
    await flush()
    const sections = Array.from(document.querySelectorAll('.resource-detail-section-title'))
    expect(sections.map((s) => s.textContent)).toContain('服务')
    expect(pageText()).toContain('该资源关联的服务与部署实例展示将由后续版本提供')
  })
})

describe('状态区分（404 / 错误，错误不伪装成空详情）', () => {
  it('资源不存在（404）：提示并引导返回资源列表', async () => {
    mockedGet.mockRejectedValueOnce(
      new ApiError(404, 'RESOURCE_NOT_FOUND', '资源不存在', [], {}),
    )
    mountView()
    await flush()
    expect(pageText()).toContain('资源不存在或已被删除')
    const back = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent?.includes('返回资源列表'))
    expect(back).toBeDefined()
  })

  it('加载失败（网络/服务器）：显式错误与重试，不显示为空详情', async () => {
    mockedGet.mockRejectedValueOnce(new Error('boom'))
    mountView()
    await flush()
    expect(pageText()).not.toContain('cn001')
    const retry = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent?.includes('重试'))
    expect(retry).toBeDefined()

    mockedGet.mockResolvedValue(detail)
    retry!.click()
    await flush()
    expect(pageText()).toContain('cn001')
  })
})

describe('返回列表与集群作用域同步', () => {
  it('「返回资源列表」跳转详情所属集群的资源列表', async () => {
    mountView()
    await flush()
    const back = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent?.includes('返回资源列表'))
    back!.click()
    for (let i = 0; i < 50; i++) {
      await nextTick()
      await new Promise((resolve) => setTimeout(resolve, 10))
      if (router.currentRoute.value.name === 'cluster-resources') break
    }
    expect(router.currentRoute.value.name).toBe('cluster-resources')
    expect(router.currentRoute.value.params.clusterId).toBe('1')
  })

  it('直接进入详情页同步集群选择（页头选择与 URL 一致）', async () => {
    mountView()
    await flush()
    expect(useClusterStore().currentClusterId).toBe(1)
  })
})
