// 集群列表行「资源」入口单测（架构 F003 §7：任意已登录可见；沿用既有「网段」入口风格）：
// F003 起「资源」跳转该集群的资源列表（cluster-resources）；原 F002 新增表单入口改为
// 「新增资源」并保持仅 maintainer/admin 可见（viewer 只读，服务端为最终校验）。
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

beforeEach(async () => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  mockedList.mockResolvedValue({ items: [cluster], total: 1, page: 1, page_size: 20 })
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
