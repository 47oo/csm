// 集群列表页单测：
// - 行内入口（F003）：「资源」任意已登录可见；「新增资源」仅 maintainer/admin；
// - F008 页面搜索统一交互：300ms 防抖（去空格、回第 1 页）、回车立即、清空回初始、
//   无结果文案、旧请求不覆盖较新请求。列表其余行为由 Contract F001 手工验证覆盖。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import ElementPlus from 'element-plus'
import { routes } from '../router'
import ClustersView from './ClustersView.vue'
import { useAuthStore } from '../stores/auth'
import { listClusters, type ClusterListItem } from '../api/clusters'
import type { CurrentUser } from '../api/types'

vi.mock('../api/clusters', () => ({
  createCluster: vi.fn(),
  deleteCluster: vi.fn(),
  getCluster: vi.fn(),
  listClusters: vi.fn(),
  updateCluster: vi.fn(),
}))

const mockedList = vi.mocked(listClusters)

const viewer: CurrentUser = {
  id: 3,
  username: 'view01',
  role: 'viewer',
  status: 'enabled',
  must_change_password: false,
}
const maintainer: CurrentUser = { ...viewer, id: 2, username: 'ops01', role: 'maintainer' }

const NOW = '2026-09-25T00:00:00Z'

const cluster: ClusterListItem = {
  id: 1,
  code: 'N96P',
  name: '生产集群',
  purpose: '训练',
  created_at: NOW,
  updated_at: NOW,
}

function pagedClusters(items: ClusterListItem[], total = items.length) {
  return { items, total, page: 1, page_size: 20 }
}

let router: Router
let pinia: Pinia
let app: ReturnType<typeof createApp> | null = null

function mountView(): void {
  app = createApp(ClustersView)
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

function findButton(text: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('button')).find(
    (b) => b.textContent?.trim() === text,
  )
}

/** 等待路由导航完成（懒加载路由组件需多个宏任务边界） */
async function waitFor(predicate: () => boolean, timeoutMs = 2000): Promise<void> {
  const start = Date.now()
  while (!predicate()) {
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 10))
    if (Date.now() - start > timeoutMs) throw new Error('waitFor 超时：条件未满足')
  }
}

function searchInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('[data-test-id="cluster-search-input"]')
  expect(input).not.toBeNull()
  return input!
}

async function typeQuery(query: string): Promise<void> {
  const input = searchInput()
  input.value = query
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flush()
}

/** 等待真实防抖（300ms）到期 */
async function waitForDebounce(ms = 380): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms))
  await flush()
}

function pressEnter(): void {
  searchInput().dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }))
}

function tableText(): string {
  return document.querySelector('.clusters-table')?.textContent ?? ''
}

beforeEach(async () => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  mockedList.mockResolvedValue(pagedClusters([cluster]))
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/clusters')
  await router.isReady()
})

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('集群行「资源」入口（F003；任意已登录可见）', () => {
  it('viewer 可见「资源」入口，点击跳转该集群的资源列表', async () => {
    useAuthStore().$patch({ user: viewer, initialized: true })
    mountView()
    await flush()
    const resourcesButton = findButton('资源')
    expect(resourcesButton).toBeDefined()
    resourcesButton!.click()
    await waitFor(() => router.currentRoute.value.name === 'cluster-resources')
    expect(router.currentRoute.value.params.clusterId).toBe('1')
  })

  it('viewer 不可见「新增资源」写入口；maintainer 可见', async () => {
    useAuthStore().$patch({ user: viewer, initialized: true })
    mountView()
    await flush()
    expect(findButton('新增资源')).toBeUndefined()

    app?.unmount()
    document.body.innerHTML = ''
    useAuthStore().$patch({ user: maintainer, initialized: true })
    mountView()
    await flush()
    expect(findButton('新增资源')).toBeDefined()
  })
})

describe('搜索（F008 §8.3 统一交互：防抖 + 竞态 + 清空回初始 + 无结果文案）', () => {
  it('首屏加载：无 q、默认 sort=code', async () => {
    mountView()
    await flush()
    expect(mockedList).toHaveBeenCalledWith({
      page: 1,
      page_size: 20,
      q: '',
      sort: 'code',
    })
  })

  it('输入后约 300ms 防抖触发：q 去首尾空格、回到第 1 页', async () => {
    mountView()
    await flush()
    mockedList.mockClear()

    await typeQuery('  N96P ')
    await waitForDebounce()
    expect(mockedList).toHaveBeenCalledTimes(1)
    expect(mockedList).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      q: 'N96P',
      sort: 'code',
    })
  })

  it('回车立即搜索（跳过防抖，不重复请求）', async () => {
    mountView()
    await flush()
    mockedList.mockClear()

    await typeQuery('N96')
    pressEnter()
    await flush()
    expect(mockedList).toHaveBeenCalledTimes(1)
    expect(mockedList).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'N96' }))
    await waitForDebounce()
    expect(mockedList).toHaveBeenCalledTimes(1)
  })

  it('清除按钮：立即回到初始候选（无 q）', async () => {
    mountView()
    await flush()
    await typeQuery('N96')
    await waitForDebounce()
    expect(mockedList).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'N96' }))

    mockedList.mockClear()
    const wrapper = searchInput().closest('.el-input')
    wrapper?.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false }))
    await flush()
    const clearIcon = document.querySelector('.el-input__clear')
    expect(clearIcon).not.toBeNull()
    clearIcon!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(mockedList).toHaveBeenCalledTimes(1)
    expect(mockedList).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      q: '',
      sort: 'code',
    })
  })

  it('无结果：显示「未找到匹配的集群」（区别于空数据文案）', async () => {
    mountView()
    await flush()
    mockedList.mockResolvedValue(pagedClusters([], 0))
    await typeQuery('不存在')
    await waitForDebounce()
    expect(tableText()).toContain('未找到匹配的集群')
    expect(tableText()).not.toContain('暂无集群')
  })

  it('旧请求不覆盖较新请求（§8.3 竞态）', async () => {
    const deferred: Array<(p: ReturnType<typeof pagedClusters>) => void> = []
    mockedList.mockImplementation(
      () =>
        new Promise((resolve) => {
          deferred.push(resolve)
        }),
    )
    mountView()
    await flush()
    expect(deferred).toHaveLength(1)

    await typeQuery('N9')
    await waitForDebounce()
    await typeQuery('N96')
    await waitForDebounce()
    expect(deferred).toHaveLength(3)

    // 较新请求（N96）先返回 → 生效
    deferred[2]!(pagedClusters([{ ...cluster, id: 2, name: '新结果集群' }]))
    await flush()
    expect(tableText()).toContain('新结果集群')

    // 较旧请求（N9）后返回 → 不覆盖
    deferred[1]!(pagedClusters([{ ...cluster, id: 3, name: '过期结果集群' }]))
    await flush()
    expect(tableText()).toContain('新结果集群')
    expect(tableText()).not.toContain('过期结果集群')
  })
})
