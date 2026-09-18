import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import BareMetalListPage from '../src/pages/BareMetalListPage.vue'
import ClusterDetailPage from '../src/pages/ClusterDetailPage.vue'
import { setUnauthenticatedHandler } from '../src/api/http'

/**
 * F009 Cluster 视角资源查询 —— 前端回归（Architecture Handoff Test Work
 * T-FE-09 / T-FE-10 / T-FE-11）。
 *
 * F009 不新增前端实现：Cluster 视角视图复用 F002 已交付的、以 `clusterId`
 * 限定的 `BareMetalListPage`。本文件把「Empty vs Not Found vs Error 三态可区分」
 * 「Empty 不触发全局会话失效」「Cluster 详情入口」「无 restore / undelete /
 * include_deleted / 回收站 入口」固定为会失败的回归测试。
 */

const EMPTY_LIST_BODY = { items: [], total: 0, page: 1, page_size: 50 }
const NOT_FOUND_BODY = { error: { code: 'NOT_FOUND', message: '与展示无关的未找到文案' } }
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }
const CLUSTER_DETAIL_BODY = {
  id: 7,
  name: 'cluster-a',
  created_at: '2026-09-15T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function waitForUi(callback: () => void | Promise<void>): Promise<void> {
  await vi.waitFor(callback, { timeout: 10000 })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
})

describe('T-FE-09：clusterId 限定下 Empty / Not Found / Error 三态互不相同', () => {
  it('Empty（200 + items==[]）→ empty 态「该集群暂无裸金属」，且不触发全局会话失效', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, EMPTY_LIST_BODY)))
    const unauthenticated = vi.fn()
    setUnauthenticatedHandler(unauthenticated)

    const wrapper = mount(BareMetalListPage, {
      props: { clusterId: 7 },
      global: { plugins: [ElementPlus] },
    })

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('empty')
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('该集群暂无裸金属')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    // Empty 不是错误，更不触发全局 401 会话失效处理。
    expect(unauthenticated).not.toHaveBeenCalled()
  })

  it('Not Found（父 Cluster 404）→ error 态，按 error.code 渲染「未找到资源」，与 Empty 文案 / 状态均不同', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, NOT_FOUND_BODY)))

    const wrapper = mount(BareMetalListPage, {
      props: { clusterId: 999 },
      global: { plugins: [ElementPlus] },
    })

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('NOT_FOUND')
    expect(alert.text()).toContain('未找到资源')
    expect(wrapper.text()).not.toContain('该集群暂无裸金属')
    expect(wrapper.find('.el-empty').exists()).toBe(false)
  })

  it('Error（500）与 Not Found、Empty 三者状态标记互相不同', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, INTERNAL_ERROR_BODY)))

    const wrapper = mount(BareMetalListPage, {
      props: { clusterId: 7 },
      global: { plugins: [ElementPlus] },
    })

    await waitForUi(() => {
      expect(wrapper.find('[data-state]').attributes('data-state')).toBe('error')
    })
    const alert = wrapper.find('[role="alert"]')
    expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(alert.text()).toContain('服务器内部错误')
    expect(wrapper.text()).not.toContain('该集群暂无裸金属')
    expect(wrapper.text()).not.toContain('未找到资源')
  })
})

describe('T-FE-10：Cluster 详情「查看裸金属」入口进入 clusterId 限定的成员列表', () => {
  it('内容态「查看裸金属」→ emit openBareMetals(clusterId)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, CLUSTER_DETAIL_BODY)))

    const wrapper = mount(ClusterDetailPage, {
      props: { clusterId: 7 },
      global: { plugins: [ElementPlus] },
    })

    await waitForUi(() => {
      expect(wrapper.find('[data-testid="open-bare-metals"]').exists()).toBe(true)
    })
    await wrapper.find('[data-testid="open-bare-metals"]').trigger('click')
    expect(wrapper.emitted('openBareMetals')).toEqual([[7]])
  })
})

describe('T-FE-11：Cluster 视角视图无 restore / undelete / include_deleted / 回收站 入口', () => {
  const clusterViewSources = [
    'src/pages/BareMetalListPage.vue',
    'src/pages/ClusterDetailPage.vue',
    'src/App.vue',
    'src/api/bareMetals.ts',
  ]

  it('源码不含恢复 / 已删资源入口 token（「不可恢复」除外）', () => {
    const offenders: string[] = []
    for (const relative of clusterViewSources) {
      const text = readFileSync(resolve(process.cwd(), relative), 'utf-8')
      // 去掉「不可恢复（删除后不可逆）」与「返回时恢复该上下文（视图过滤上下文）」
      // 这类合法措辞后，检查是否残留恢复语义入口。
      const scrubbed = text
        .replace(/不可恢复/g, '')
        .replace(/恢复该上下文/g, '')
        .replace(/返回时恢复/g, '')
      for (const token of ['restore', 'undelete', 'include_deleted', '回收站', '恢复']) {
        if (scrubbed.includes(token)) offenders.push(`${relative}: ${token}`)
      }
    }
    expect(offenders).toEqual([])
  })
})
