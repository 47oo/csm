// 资源列表页单测（架构 F003 §2.4/§7，需求 §6.2）：真实 router（memory history）+ pinia +
// Element Plus 下整页挂载，API 模块 mock。覆盖：首屏加载与作用域显式展示（响应回显
// scope）、状态含文字（服务端 status_label，不只靠颜色）、未选择集群提示（不隐式切换）、
// 类型切换触发筛选请求、空态与错误态区分（错误不伪装成空列表）、viewer 权限隐藏新增入口、
// 行内名称进入详情。筛选/分页/搜索/竞态的请求构造与状态机见 useResourceList.test.ts。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import ElementPlus from 'element-plus'
import { routes } from '../router'
import ClusterResourcesView from './ClusterResourcesView.vue'
import { useAuthStore } from '../stores/auth'
import { useClusterStore } from '../stores/clusters'
import { listResources, type PagedResources, type ResourceListItem } from '../api/resources'
import type { CurrentUser } from '../api/types'

vi.mock('../api/resources', () => ({
  listResources: vi.fn(),
  getResource: vi.fn(),
}))

const mocked = vi.mocked(listResources)

const NOW = '2026-09-25T00:00:00Z'

const maintainer: CurrentUser = {
  id: 2,
  username: 'ops01',
  role: 'maintainer',
  status: 'enabled',
  must_change_password: false,
}
const viewer: CurrentUser = { ...maintainer, id: 3, username: 'view01', role: 'viewer' }

function item(overrides: Partial<ResourceListItem> & Pick<ResourceListItem, 'id'>): ResourceListItem {
  return {
    name: `cn00${overrides.id}`,
    cluster_id: 1,
    cluster_code: 'N96P',
    cluster_name: '生产集群',
    resource_type: 'bare_metal',
    resource_type_label: '裸金属',
    status: 'ALLOC',
    status_label: '已分配',
    management_ip: null,
    updated_at: NOW,
    ...overrides,
  }
}

function paged(items: ResourceListItem[], total: number): PagedResources {
  return {
    items,
    total,
    page: 1,
    page_size: 20,
    scope: { cluster_id: 1, cluster_code: 'N96P', cluster_name: '生产集群' },
  }
}

let router: Router
let pinia: Pinia
let app: ReturnType<typeof createApp> | null = null

/** 挂载整页视图（Element Plus 全量注册；挂到 body 以便 DOM 断言） */
function mountView(): void {
  app = createApp(ClusterResourcesView)
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

/** 等待路由导航完成：懒加载路由组件（动态 import）在 vitest 下可能需要多个
 * 宏任务边界才解析，轮询至断言满足（超时拋错） */
async function waitFor(
  predicate: () => boolean,
  timeoutMs = 2000,
): Promise<void> {
  const start = Date.now()
  while (!predicate()) {
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 10))
    if (Date.now() - start > timeoutMs) {
      throw new Error('waitFor 超时：条件未满足')
    }
  }
}

/** 页面主体文本（表格行等；不含 teleport 到 body 的下拉浮层） */
function pageText(): string {
  return document.body.textContent ?? ''
}

/** 表格区域文本（避免命中下拉选项文字） */
function tableText(): string {
  return document.querySelector('.resources-table')?.textContent ?? ''
}

beforeEach(async () => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
  mocked.mockResolvedValue(paged([item({ id: 7 })], 1))
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/clusters/1/resources')
  await router.isReady()
})

afterEach(() => {
  app?.unmount()
  app = null
  document.body.innerHTML = ''
})

describe('首屏加载与作用域展示（§6.2：搜索限当前集群并显式展示作用域）', () => {
  it('以路由集群作用域加载列表，显式展示「当前集群：CODE 名称」（响应回显 scope）', async () => {
    mountView()
    await flush()
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({ cluster_id: 1, page: 1, page_size: 20, sort: 'name' }),
    )
    const scopeEl = document.querySelector('[data-test-id="resource-search-scope"]')
    expect(scopeEl?.textContent).toContain('当前集群：N96P 生产集群')
    expect(scopeEl?.textContent).toContain('IP 搜索仅限本集群')
  })

  it('列表行渲染公共列：状态含服务端文字（不只靠颜色，§9.4）与管理 IP', async () => {
    mocked.mockResolvedValue(
      paged([
        item({
          id: 7,
          status: 'DOWN',
          status_label: '宕机',
          resource_type: 'virtual_machine',
          resource_type_label: '虚拟机',
          management_ip: {
            ip_id: 55,
            address: '192.168.1.10',
            interface_id: 10,
            interface_name: 'eth0',
          },
        }),
      ], 1),
    )
    mountView()
    await flush()
    const text = tableText()
    expect(text).toContain('cn007')
    expect(text).toContain('N96P 生产集群')
    expect(text).toContain('虚拟机')
    expect(text).toContain('宕机')
    expect(text).toContain('192.168.1.10')
    // 状态以标签呈现（颜色辅助 + 文字必需）
    expect(document.querySelector('.resources-table .el-tag')?.textContent).toContain('宕机')
  })

  it('清除集群选择：提示选择集群且不再查询（不隐式切换作用域）', async () => {
    mountView()
    await flush()
    expect(mocked).toHaveBeenCalledTimes(1)

    useClusterStore().selectCluster(null)
    await flush()
    expect(pageText()).toContain('尚未选择集群')
    expect(mocked).toHaveBeenCalledTimes(1) // 未发起跨集群查询
  })
})

describe('类型切换（全部/裸金属/虚拟机）', () => {
  it('点击「裸金属」：以 resource_type 筛选重新请求', async () => {
    mocked.mockResolvedValue(paged([], 0))
    mountView()
    await flush()

    const radio = document.querySelector<HTMLInputElement>('.resources-filter input[value="bare_metal"]')
    expect(radio).not.toBeNull()
    radio!.click()
    await flush()
    expect(mocked).toHaveBeenLastCalledWith(
      expect.objectContaining({ cluster_id: 1, resource_type: 'bare_metal', page: 1 }),
    )
  })
})

describe('状态筛选（F008 EnumSelect：中文展示名/英文代码输入匹配）', () => {
  it('输入中文「空闲」过滤并选中：以 status=IDLE 筛选重新请求', async () => {
    mocked.mockResolvedValue(paged([], 0))
    mountView()
    await flush()
    mocked.mockClear()

    const filter = document.querySelector('[data-test-id="resource-status-filter"]')
    expect(filter).not.toBeNull()
    const input = filter!.querySelector<HTMLInputElement>('input.el-select__input')!
    input.dispatchEvent(new FocusEvent('focus', { bubbles: true }))
    input.click()
    await flush()
    // 本地过滤：下拉展示全部选项（含「全部状态」伪选项）
    const items = Array.from(document.querySelectorAll('.enum-select-dropdown .el-select-dropdown__item')).map(
      (el) => el.textContent?.trim(),
    )
    expect(items).toContain('全部状态')
    expect(items).toContain('空闲')

    input.value = '空闲'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await flush()
    const matched = Array.from(document.querySelectorAll('.enum-select-dropdown .el-select-dropdown__item'))
    expect(matched.map((el) => el.textContent?.trim())).toEqual(['空闲'])

    matched[0]!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flush()
    expect(mocked).toHaveBeenLastCalledWith(
      expect.objectContaining({ cluster_id: 1, status: 'IDLE', page: 1 }),
    )
  })
})

describe('空态 / 错误态区分（错误不伪装成空列表）', () => {
  it('无资源：空态文案（该集群暂无计算资源）', async () => {
    mocked.mockResolvedValue(paged([], 0))
    mountView()
    await flush()
    expect(tableText()).toContain('该集群暂无计算资源')
    expect(pageText()).not.toContain('请求失败')
  })

  it('加载失败：显式错误与重试（不显示为空列表）', async () => {
    mocked.mockRejectedValueOnce(new Error('服务器错误'))
    mountView()
    await flush()
    expect(document.querySelector('.resources-error')).not.toBeNull()
    expect(pageText()).not.toContain('该集群暂无计算资源')

    // 重试恢复
    await flush()
    const retryButton = Array.from(document.querySelectorAll<HTMLButtonElement>('.resources-error button'))
      .find((b) => b.textContent?.includes('重试'))
    retryButton?.click()
    await flush()
    expect(tableText()).toContain('cn007')
  })
})

describe('权限（前端仅隐藏入口，服务端为最终校验）', () => {
  it('viewer 只读：不显示「新增资源」入口', async () => {
    useAuthStore().$patch({ user: viewer, initialized: true })
    mountView()
    await flush()
    expect(pageText()).not.toContain('新增资源')
  })

  it('maintainer：显示「新增资源」入口，跳转新增表单（F002 写入口）', async () => {
    useAuthStore().$patch({ user: maintainer, initialized: true })
    mountView()
    await flush()
    const createButton = Array.from(document.querySelectorAll('button'))
      .find((b) => b.textContent?.trim() === '新增资源')
    expect(createButton).toBeDefined()
    createButton!.click()
    await waitFor(() => router.currentRoute.value.name === 'resource-new')
    expect(router.currentRoute.value.params.clusterId).toBe('1')
  })
})

describe('进入详情', () => {
  it('点击资源名称：跳转该资源的详情页', async () => {
    mountView()
    await flush()
    const nameButton = Array.from(document.querySelectorAll<HTMLButtonElement>('.resources-table button'))
      .find((b) => b.textContent?.trim() === 'cn007')
    expect(nameButton).toBeDefined()
    nameButton!.click()
    await waitFor(() => router.currentRoute.value.name === 'resource-detail')
    expect(router.currentRoute.value.params).toMatchObject({ clusterId: '1', resourceId: '7' })
  })
})
