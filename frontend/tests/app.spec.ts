import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * vi.waitFor 包装：全量并行负载下页面挂载 / el-dialog 挂载 / 异步完成偶发超过
 * vi.waitFor 默认 1s（单文件运行稳定）。随测试文件数增长，已先后放宽到
 * 5s、10s；仅放宽超时上限，不改变断言语义。
 */
async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

/**
 * App 极简视图状态测试：集群列表 ↔ 集群详情切换（不引入 vue-router，
 * f001-cluster-handoff.md Frontend Work #5）。fetch 桩替换，响应体严格按
 * docs/api/f001-cluster.md 与 docs/api/f013-auth.md 构造。
 * F013 起 App 增加会话门控：本组用例模拟「已有会话」直接进入 app 视图；
 * 会话失效 / 登录 / 登出流程见 appAuth.spec.ts。
 */

const CLUSTER_A = {
  id: 1,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}
const LIST_BODY = { items: [CLUSTER_A], total: 1, page: 1, page_size: 50 }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function stubProductFetch(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/auth/session')) {
        return jsonResponse(200, { id: 1, username: 'admin' })
      }
      if (url.includes('/api/clusters/')) {
        return jsonResponse(200, CLUSTER_A)
      }
      return jsonResponse(200, LIST_BODY)
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  // App 挂载时会注册全局未认证处理器，卸载后清除，保证测试隔离。
  setUnauthenticatedHandler(null)
})

describe('App 视图切换（列表 ↔ 详情）', () => {
  it('初始渲染列表 → 点击「详情」进入详情页 → 点击「返回列表」回到列表', async () => {
    stubProductFetch()
    const wrapper = mount(App, { global: { plugins: [ElementPlus] } })

    // 启动会话探测通过后进入 app 视图：集群列表（请求 GET /api/clusters）。
    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.text()).toContain('集群列表')
    expect(wrapper.text()).toContain('cluster-a')

    // 进入详情：请求 GET /api/clusters/1，仅呈现 Cluster 自身字段。
    const detailButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('详情'))
    expect(detailButton).toBeDefined()
    await detailButton!.trigger('click')

    await waitForUi(() => {
      expect(wrapper.text()).toContain('集群详情')
    })
    await waitForUi(() => {
      expect(wrapper.text()).toContain('2026-09-15T10:00:00Z')
    })
    expect(wrapper.text()).toContain('cluster-a')

    // 返回列表。
    const backButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('返回列表'))
    expect(backButton).toBeDefined()
    await backButton!.trigger('click')

    await waitForUi(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.text()).toContain('集群列表')
  })
})
