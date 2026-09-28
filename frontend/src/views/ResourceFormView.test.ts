// 资源表单页单测（F008 修复轮 D-F008-01：网络范围/集群下拉接入 FuzzySelect 服务端搜索）：
// 真实 router（memory history）+ pinia + Element Plus 下整页挂载，API 模块 mock。覆盖：
// - 网段下拉服务端 q（cluster_id 作用域、sort=name、小 page_size）与「名称 · CIDR · 用途」展示；
// - 选中网段带出只读摘要（技术类型/用途/CIDR/网关，§4.2.7/§7.1）；
// - 未匹配自由文本不提交、不产生选择（场景 41）；
// - 切换集群清除不再匹配的网段选择，且下拉候选随集群重建（不残留旧集群，§7.1）；
// - 未选网段仍可保存（场景 30）；编辑模式集群只读回显（§4.1.8 已登记资源不允许切换集群）。
// 提交映射/校验/冲突等状态机细节见 composables/useResourceForm.test.ts。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import ElementPlus from 'element-plus'
import { routes } from '../router'
import ResourceFormView from './ResourceFormView.vue'
import { useAuthStore } from '../stores/auth'
import { createResource, getResource, type ResourceFormDetail } from '../api/resources'
import { getNetworkSegment, listNetworkSegments, type NetworkSegmentListItem } from '../api/segments'
import { listClusters } from '../api/clusters'
import type { CurrentUser } from '../api/types'

vi.mock('../api/resources', () => ({
  createResource: vi.fn(),
  getResource: vi.fn(),
  updateResource: vi.fn(),
  deleteResource: vi.fn(),
}))

vi.mock('../api/segments', () => ({
  listNetworkSegments: vi.fn(),
  getNetworkSegment: vi.fn(),
}))

vi.mock('../api/clusters', () => ({
  listClusters: vi.fn(),
}))

const mockedCreate = vi.mocked(createResource)
const mockedGet = vi.mocked(getResource)
const mockedListSegments = vi.mocked(listNetworkSegments)
const mockedGetSegment = vi.mocked(getNetworkSegment)
const mockedListClusters = vi.mocked(listClusters)

const NOW = '2026-09-26T00:00:00Z'

const maintainer: CurrentUser = {
  id: 2,
  username: 'ops01',
  role: 'maintainer',
  status: 'enabled',
  must_change_password: false,
}

function segment(overrides: Partial<NetworkSegmentListItem> & Pick<NetworkSegmentListItem, 'id' | 'cluster_id'>): NetworkSegmentListItem {
  return {
    name: `seg${overrides.id}`,
    cluster_code: 'N96P',
    cluster_name: '生产集群',
    cidr: '192.168.1.0/24',
    purpose: '管理',
    technology: 'Ethernet',
    vlan: 100,
    gateway: '192.168.1.1',
    auto_alloc_start: null,
    auto_alloc_end: null,
    auto_alloc_enabled: false,
    reserved_address_count: 0,
    allocated_count: 0,
    auto_assignable_count: 0,
    has_overlap: false,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  }
}

/** 集群 1：management（Ethernet/管理）；集群 2：storage（InfiniBand/存储） */
const CLUSTER_1_SEGMENTS = [segment({ id: 3, cluster_id: 1, name: 'management', cidr: '192.168.1.0/24', purpose: '管理', technology: 'Ethernet' })]
const CLUSTER_2_SEGMENTS = [
  segment({ id: 5, cluster_id: 2, cluster_code: 'N97P', cluster_name: '测试集群', name: 'storage', cidr: '10.0.0.0/24', purpose: '存储', technology: 'InfiniBand', vlan: 200, gateway: '10.0.0.1' }),
]

/** 编辑基线（F002 形态：eth0 关联网段 3、ib0 无网段，无 IP/管理 IP） */
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
      segment: { id: 3, name: 'management', cidr: '192.168.1.0/24', purpose: '管理', technology: 'Ethernet', vlan: 100, gateway: '192.168.1.1' },
      ips: [],
      created_at: NOW,
      updated_at: NOW,
    },
    { id: 11, name: 'ib0', segment_id: null, segment: null, ips: [], created_at: NOW, updated_at: NOW },
  ],
  management_ip: null,
  version: 3,
  created_at: NOW,
  updated_at: NOW,
}

let router: Router
let pinia: Pinia
let app: ReturnType<typeof createApp> | null = null

function mountView(): void {
  app = createApp(ResourceFormView)
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

/** 等待条件成立（轮询真实定时器；覆盖防抖/懒加载路由等异步链） */
async function waitFor(predicate: () => boolean, timeoutMs = 2000): Promise<void> {
  const start = Date.now()
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) throw new Error('waitFor 超时：条件未满足')
    await new Promise((resolve) => setTimeout(resolve, 10))
    for (let i = 0; i < 5; i++) await nextTick()
  }
}

/** 等待 FuzzySelect 真实防抖（默认 300ms）到期并返回结果（条件轮询，负载不敏感） */
async function waitForSegmentQuery(q: string): Promise<void> {
  await waitFor(() => mockedListSegments.mock.calls.some((c) => c[0]?.q === q))
  await flush()
}

/** 下拉输入框（按表单内选择器 class 作用域定位，避免多下拉串扰） */
function selectInput(scope: string): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>(`${scope} input.el-select__input`)
  expect(input).not.toBeNull()
  return input!
}

function openSelect(scope: string): void {
  const input = selectInput(scope)
  input.dispatchEvent(new FocusEvent('focus', { bubbles: true }))
  input.click()
}

/** 指定下拉（popper-class 作用域，teleport 到 body）的选项 */
function dropdownItems(popper: string): Array<HTMLElement> {
  return Array.from(document.querySelectorAll(`.${popper} .el-select-dropdown__item`))
}

function dropdownText(popper: string): string {
  return document.querySelector(`.${popper}`)?.textContent ?? ''
}

async function clickItem(popper: string, text: string): Promise<void> {
  const item = dropdownItems(popper).find((el) => el.textContent?.includes(text))
  expect(item, `下拉选项「${text}」未找到`).toBeDefined()
  item!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flush()
}

async function typeIntoSelect(scope: string, text: string): Promise<void> {
  const input = selectInput(scope)
  input.value = text
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flush()
}

function setNativeInput(input: HTMLInputElement, text: string): void {
  input.value = text
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

async function clickOutside(): Promise<void> {
  document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  document.body.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  await flush()
}

function findButton(text: string): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find(
    (b) => b.textContent?.trim() === text,
  )
  expect(button, `按钮「${text}」未找到`).toBeDefined()
  return button!
}

async function mountCreateForm(): Promise<void> {
  await router.push('/clusters/1/resources/new')
  await router.isReady()
  mountView()
  await flush()
}

/** 网段列表应答：按集群返回，q 非空时模拟服务端匹配 名称/CIDR/用途/技术类型（§8.1） */
function segmentsByQuery(): void {
  mockedListSegments.mockImplementation(async (query) => {
    const all = query.cluster_id === 2 ? CLUSTER_2_SEGMENTS : CLUSTER_1_SEGMENTS
    const q = query.q?.trim() ?? ''
    const items = q === '' ? all : all.filter((s) => `${s.name} ${s.cidr} ${s.purpose} ${s.technology}`.includes(q))
    return { items, total: items.length, page: 1, page_size: query.page_size ?? 20 }
  })
}

beforeEach(async () => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  pinia = createPinia()
  setActivePinia(pinia)
  window.localStorage.clear()
  useAuthStore().$patch({ user: { ...maintainer }, initialized: true })
  router = createRouter({ history: createMemoryHistory(), routes })
  mockedListClusters.mockResolvedValue({
    items: [
      { id: 1, code: 'N96P', name: '生产集群', purpose: '训练', created_at: NOW, updated_at: NOW },
      { id: 2, code: 'N97P', name: '测试集群', purpose: '测试', created_at: NOW, updated_at: NOW },
    ],
    total: 2,
    page: 1,
    page_size: 100,
  })
  segmentsByQuery()
  mockedGetSegment.mockImplementation(async (id) =>
    id === 5
      ? { ...CLUSTER_2_SEGMENTS[0]!, version: 1, reserved_addresses: [], overlaps: [] }
      : { ...CLUSTER_1_SEGMENTS[0]!, id, name: `seg${id}`, version: 1, reserved_addresses: [], overlaps: [] },
  )
  mockedGet.mockResolvedValue(detail)
  mockedCreate.mockResolvedValue(detail)
})

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('网段下拉服务端搜索（F008 §8.1：名称/CIDR/用途/技术类型）', () => {
  it(
    '输入关键词发起服务端 q：cluster_id 作用域 + sort=name + 小 page_size；展示「名称 · CIDR · 用途」',
    async () => {
      await mountCreateForm()
      findButton('添加网卡').click()
      await flush()
      // 初始候选来自全量列表（挂载后无重复请求）
      expect(mockedListSegments).toHaveBeenCalledTimes(1)
      expect(mockedListSegments).toHaveBeenLastCalledWith(
        expect.objectContaining({ cluster_id: 1, page: 1, page_size: 100, sort: 'name' }),
      )

      openSelect('.resource-segment-select')
      await flush()
      // 按技术类型输入匹配（本地过滤不可匹配的维度，后端已支持）
      await typeIntoSelect('.resource-segment-select', 'Ethernet')
      await waitForSegmentQuery('Ethernet')
      expect(mockedListSegments).toHaveBeenLastCalledWith({
        cluster_id: 1,
        q: 'Ethernet',
        page: 1,
        page_size: 20,
        sort: 'name',
      })
      expect(dropdownItems('resource-segment-dropdown').map((el) => el.textContent?.trim())).toEqual([
        'management · 192.168.1.0/24 · 管理',
      ])
    },
    15000,
  )

  it(
    '选中提交稳定 segment_id 并带出只读摘要（技术类型/用途/CIDR/网关，§4.2.7/§7.1）',
    async () => {
      await mountCreateForm()
      findButton('添加网卡').click()
      await flush()
      openSelect('.resource-segment-select')
      await clickItem('resource-segment-dropdown', 'management · 192.168.1.0/24 · 管理')

      const summary = document.querySelector('.nic-segment-info')
      expect(summary).not.toBeNull()
      expect(summary?.textContent).toContain('Ethernet')
      expect(summary?.textContent).toContain('管理')
      expect(summary?.textContent).toContain('192.168.1.0/24')
      expect(summary?.textContent).toContain('192.168.1.1')
      // 选中回显 label
      expect(document.querySelector('.resource-segment-select .el-select__wrapper')?.textContent).toContain(
        'management · 192.168.1.0/24 · 管理',
      )
    },
    15000,
  )

  it(
    '未匹配自由文本不提交、不产生选择（场景 41）：失焦后回退，无只读带出',
    async () => {
      await mountCreateForm()
      findButton('添加网卡').click()
      await flush()
      openSelect('.resource-segment-select')
      await typeIntoSelect('.resource-segment-select', '不存在的输入')
      await waitForSegmentQuery('不存在的输入')
      expect(dropdownItems('resource-segment-dropdown')).toHaveLength(0)
      expect(dropdownText('resource-segment-dropdown')).toContain('没有匹配项')

      await clickOutside()
      // 未产生选择：无只读摘要；展示回退（未选中任何网段）
      expect(document.querySelector('.nic-segment-info')).toBeNull()
      expect(document.querySelector('.resource-segment-select .el-select__wrapper')?.textContent).not.toContain(
        '不存在的输入',
      )
    },
    15000,
  )
})

describe('切换集群（§7.1：清除不再匹配的网段选择；候选随集群重建）', () => {
  it(
    '选中网段后切换集群：选择被清除、无只读摘要；下拉候选换为新集群且不残留旧集群',
    async () => {
      await mountCreateForm()
      findButton('添加网卡').click()
      await flush()
      openSelect('.resource-segment-select')
      await clickItem('resource-segment-dropdown', 'management · 192.168.1.0/24 · 管理')
      expect(document.querySelector('.nic-segment-info')).not.toBeNull()

      // 切换集群（FuzzySelect 集群选择器，候选来自集群列表）
      openSelect('.resource-cluster-select')
      await clickItem('resource-cluster-dropdown', 'N97P 测试集群')
      await waitFor(() => document.querySelector('.nic-segment-info') === null)
      await waitFor(
        () => mockedListSegments.mock.calls.some((c) => c[0]?.cluster_id === 2 && c[0]?.page_size === 20),
      )
      await flush()

      // 原网段选择被清除（§7.1）；集群回显新选择
      expect(document.querySelector('.nic-segment-info')).toBeNull()
      expect(document.querySelector('.resource-cluster-select .el-select__wrapper')?.textContent).toContain(
        'N97P 测试集群',
      )
      // 网段下拉以新集群重新取初始候选（不残留旧集群网段）
      openSelect('.resource-segment-select')
      await flush()
      const items = dropdownItems('resource-segment-dropdown').map((el) => el.textContent?.trim())
      expect(items).toEqual(['storage · 10.0.0.0/24 · 存储'])
      expect(items.join()).not.toContain('management')
    },
    15000,
  )
})

describe('未选网段仍可保存（§7.1/场景 30）', () => {
  it(
    '网卡无网段无 IP：创建提交 segment_id:null，不发起网段详情请求',
    async () => {
      await mountCreateForm()
      setNativeInput(document.querySelector<HTMLInputElement>('input[placeholder^="同集群内唯一"]')!, 'ib-host')
      openSelect('.resource-type-select')
      // EnumSelect 固定 popper-class=enum-select-dropdown（中文展示名/英文代码均可匹配，F008）
      await clickItem('enum-select-dropdown', '裸金属')
      findButton('添加网卡').click()
      await flush()
      setNativeInput(document.querySelector<HTMLInputElement>('input[placeholder^="如 eth0"]')!, 'ib0')

      findButton('创建').click()
      await waitFor(() => mockedCreate.mock.calls.length > 0)
      await flush()

      expect(mockedCreate).toHaveBeenCalledWith({
        cluster_id: 1,
        name: 'ib-host',
        resource_type: 'bare_metal',
        status: 'ALLOC',
        interfaces: [{ name: 'ib0', segment_id: null }],
      })
      expect(mockedGetSegment).not.toHaveBeenCalled()
    },
    15000,
  )
})

describe('编辑模式（§4.1.8：已登记资源不允许切换集群）', () => {
  it(
    '集群只读回显（无集群下拉）；已选网段回显 label 与只读摘要',
    async () => {
      await router.push('/clusters/1/resources/7/edit')
      await router.isReady()
      mountView()
      await flush()

      expect(document.querySelector('.resource-cluster-select')).toBeNull()
      const readonly = Array.from(document.querySelectorAll<HTMLInputElement>('input[disabled]')).find((i) =>
        i.value.includes('N96P'),
      )
      expect(readonly?.value).toContain('N96P 生产集群')
      // eth0 已选网段 3：回显 label 与只读摘要（带出 technology/purpose/CIDR/网关）
      expect(document.querySelector('.resource-segment-select .el-select__wrapper')?.textContent).toContain(
        'management · 192.168.1.0/24 · 管理',
      )
      expect(document.querySelector('.nic-segment-info')?.textContent).toContain('Ethernet')
    },
    15000,
  )
})
