import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import App from '../src/App.vue'

/**
 * App 极简视图状态测试：集群列表 ↔ 集群详情切换（不引入 vue-router，
 * f001-cluster-handoff.md Frontend Work #5）。fetch 桩替换，响应体严格按
 * docs/api/f001-cluster.md 构造。
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
      if (url.includes('/api/clusters/')) {
        return jsonResponse(200, CLUSTER_A)
      }
      return jsonResponse(200, LIST_BODY)
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App 视图切换（列表 ↔ 详情）', () => {
  it('初始渲染列表 → 点击「详情」进入详情页 → 点击「返回列表」回到列表', async () => {
    stubProductFetch()
    const wrapper = mount(App, { global: { plugins: [ElementPlus] } })

    // 初始：集群列表（请求 GET /api/clusters，展示契约字段）。
    await vi.waitFor(() => {
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

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('集群详情')
    })
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('2026-09-15T10:00:00Z')
    })
    expect(wrapper.text()).toContain('cluster-a')

    // 返回列表。
    const backButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('返回列表'))
    expect(backButton).toBeDefined()
    await backButton!.trigger('click')

    await vi.waitFor(() => {
      expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    })
    expect(wrapper.text()).toContain('集群列表')
  })
})
