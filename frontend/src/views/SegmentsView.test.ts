// 网段列表页搜索单测（架构 F008 §4.2/§10，需求 §8.3）：统一搜索交互接入——
// 300ms 防抖（连续输入重置计时、去首尾空格）、回车立即、旧请求不覆盖较新请求、
// 清空回初始候选、无结果文案；列表/表单/删除等其余行为由 SegmentsView 既有手工验证
// 与本文件的首屏作用域用例覆盖。API 模块 mock，Contract 见 docs/api/F005.md。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import ElementPlus from 'element-plus'
import { routes } from '../router'
import SegmentsView from './SegmentsView.vue'
import { useClusterStore } from '../stores/clusters'
import {
  listNetworkSegments,
  type NetworkSegmentListItem,
  type PagedNetworkSegments,
} from '../api/segments'

vi.mock('../api/segments', () => ({
  createNetworkSegment: vi.fn(),
  deleteNetworkSegment: vi.fn(),
  getNetworkSegment: vi.fn(),
  listNetworkSegments: vi.fn(),
  listReservedAddresses: vi.fn(),
  updateNetworkSegment: vi.fn(),
  clearNetworkSegmentGateway: vi.fn(),
  createReservedAddress: vi.fn(),
  deleteReservedAddress: vi.fn(),
  listAllocatedIps: vi.fn(),
}))

const mockedList = vi.mocked(listNetworkSegments)

const NOW = '2026-09-26T00:00:00Z'

function segment(overrides: Partial<NetworkSegmentListItem> & Pick<NetworkSegmentListItem, 'id'>): NetworkSegmentListItem {
  return {
    cluster_id: 1,
    cluster_code: 'N96P',
    cluster_name: '生产集群',
    name: `管理网段${overrides.id}`,
    cidr: `192.168.${overrides.id}.0/24`,
    purpose: '管理网络',
    technology: 'Ethernet',
    vlan: null,
    gateway: null,
    auto_alloc_start: null,
    auto_alloc_end: null,
    auto_alloc_enabled: false,
    reserved_address_count: 0,
    allocated_count: 0,
    auto_assignable_count: 250,
    has_overlap: false,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  }
}

function paged(items: NetworkSegmentListItem[], total = items.length): PagedNetworkSegments {
  return { items, total, page: 1, page_size: 20 }
}

let router: Router
let pinia: Pinia
let app: ReturnType<typeof createApp> | null = null

function mountView(): void {
  app = createApp(SegmentsView)
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

/** 等待真实防抖（300ms）到期 */
async function waitForDebounce(ms = 380): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms))
  await flush()
}

function searchInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('[data-test-id="segment-search-input"]')
  expect(input).not.toBeNull()
  return input!
}

async function typeQuery(query: string): Promise<void> {
  const input = searchInput()
  input.value = query
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flush()
}

function pressEnter(): void {
  searchInput().dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }))
}

function tableText(): string {
  return document.querySelector('.segments-table')?.textContent ?? ''
}

beforeEach(async () => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  mockedList.mockResolvedValue(paged([segment({ id: 11 }), segment({ id: 12 })]))
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/clusters/1/segments')
  await router.isReady()
})

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('首屏（集群作用域，Contract §2.1）', () => {
  it('以路由集群作用域加载列表（cluster_id=1、无 q、默认 sort=name）', async () => {
    mountView()
    await flush()
    expect(mockedList).toHaveBeenCalledWith({
      cluster_id: 1,
      page: 1,
      page_size: 20,
      q: '',
      sort: 'name',
    })
    expect(tableText()).toContain('管理网段11')
  })

  it('切换集群：以新作用域重新加载（页码重置）', async () => {
    mountView()
    await flush()
    useClusterStore().selectCluster(2)
    await flush()
    // 路由同步 + 列表刷新均以新集群为作用域
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ cluster_id: 2, page: 1 }),
    )
  })
})

describe('搜索（§8.3 统一交互：防抖 + 竞态 + 清空回初始 + 无结果文案）', () => {
  it('输入后约 300ms 防抖触发：q 去首尾空格、回到第 1 页', async () => {
    mountView()
    await flush()
    mockedList.mockClear()

    await typeQuery('  192.168 ')
    await waitForDebounce()
    expect(mockedList).toHaveBeenCalledTimes(1)
    expect(mockedList).toHaveBeenLastCalledWith({
      cluster_id: 1,
      page: 1,
      page_size: 20,
      q: '192.168',
      sort: 'name',
    })
  })

  it('连续输入重置计时：防抖期内不请求，仅以最后一次为准', async () => {
    mountView()
    await flush()
    mockedList.mockClear()

    await typeQuery('19')
    await new Promise((resolve) => setTimeout(resolve, 150))
    await typeQuery('192.16')
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(mockedList).not.toHaveBeenCalled()
    await waitForDebounce()
    expect(mockedList).toHaveBeenCalledTimes(1)
    expect(mockedList).toHaveBeenLastCalledWith(expect.objectContaining({ q: '192.16' }))
  })

  it('回车立即搜索（跳过防抖，不重复请求）', async () => {
    mountView()
    await flush()
    mockedList.mockClear()

    await typeQuery('管理')
    pressEnter()
    await flush()
    expect(mockedList).toHaveBeenCalledTimes(1)
    expect(mockedList).toHaveBeenLastCalledWith(expect.objectContaining({ q: '管理' }))
    // 防抖已被取消
    await waitForDebounce()
    expect(mockedList).toHaveBeenCalledTimes(1)
  })

  it('清除按钮：立即回到初始候选（无 q 第 1 页）', async () => {
    mountView()
    await flush()
    await typeQuery('管理')
    await waitForDebounce()
    expect(mockedList).toHaveBeenLastCalledWith(expect.objectContaining({ q: '管理' }))

    mockedList.mockClear()
    // 显示清除按钮（el-input hover 态）并点击
    const wrapper = searchInput().closest('.el-input')
    wrapper?.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false }))
    await flush()
    const clearIcon = document.querySelector('.el-input__clear')
    expect(clearIcon).not.toBeNull()
    clearIcon!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(mockedList).toHaveBeenCalledTimes(1)
    expect(mockedList).toHaveBeenLastCalledWith({
      cluster_id: 1,
      page: 1,
      page_size: 20,
      q: '',
      sort: 'name',
    })
  })

  it('无结果：显示「未找到匹配的网段」（区别于空数据文案）', async () => {
    mountView()
    await flush()
    mockedList.mockResolvedValue(paged([], 0))
    await typeQuery('不存在')
    await waitForDebounce()
    expect(tableText()).toContain('未找到匹配的网段')
    expect(tableText()).not.toContain('该集群暂无网段')
  })

  it('旧请求不覆盖较新请求（§8.3 竞态）', async () => {
    const deferred: Array<(p: PagedNetworkSegments) => void> = []
    mockedList.mockImplementation(
      () =>
        new Promise<PagedNetworkSegments>((resolve) => {
          deferred.push(resolve)
        }),
    )
    mountView()
    await flush()
    expect(deferred).toHaveLength(1)

    await typeQuery('cn0')
    await waitForDebounce()
    await typeQuery('cn01')
    await waitForDebounce()
    expect(deferred).toHaveLength(3)

    // 较新请求（cn01）先返回 → 生效
    deferred[2]!(paged([segment({ id: 21, name: '新结果' })]))
    await flush()
    expect(tableText()).toContain('新结果')

    // 较旧请求（cn0）后返回 → 不覆盖
    deferred[1]!(paged([segment({ id: 99, name: '过期结果' })]))
    await flush()
    expect(tableText()).toContain('新结果')
    expect(tableText()).not.toContain('过期结果')
  })
})
