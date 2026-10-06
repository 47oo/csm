// 资源页面集群作用域单测（架构 F003 §2.4/§7，对齐 F005 useSegmentPageScope）：
// 路由参数与集群选择双向同步；切换集群 → 跳转到新集群的资源列表（页面刷新列表）；
// 详情页直接进入同步选择且不跳转；在详情页切换集群回到列表（原详情属于旧集群，
// 不得在 URL 中保留）；清除选择留在本页（作用域为空，页面提示选择集群）。
// 通过在真实 router（memory history）+ pinia 下挂载宿主组件驱动 composable。
import { beforeEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, nextTick } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { routes } from '../router'
import { useClusterStore } from '../stores/clusters'
import { useResourcePageScope } from './useResourcePageScope'

let router: Router
let pinia: Pinia
let exposed: ReturnType<typeof useResourcePageScope> | null = null

/** 挂载仅运行 composable 的宿主组件（无需 @vue/test-utils） */
function mountHost(): void {
  const Host = defineComponent({
    setup() {
      exposed = useResourcePageScope()
      return () => h('div')
    },
  })
  const app = createApp(Host)
  app.use(pinia)
  app.use(router)
  app.mount(document.createElement('div'))
}

/** 等待 watcher → router.replace 导航链完成：router 导航为深层 promise 链，
 * 除微任务（nextTick）外还需一次宏任务边界（setTimeout）才能全部排空；
 * 尾部再排一次 watcher 队列（路由更新后触发 route watcher 同步）。 */
async function flush(): Promise<void> {
  for (let i = 0; i < 10; i++) {
    await nextTick()
  }
  await new Promise((resolve) => setTimeout(resolve, 0))
  for (let i = 0; i < 10; i++) {
    await nextTick()
  }
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  window.localStorage.clear()
  router = createRouter({ history: createMemoryHistory(), routes })
  exposed = null
})

describe('路由匹配（/clusters/:clusterId/resources 与 /:resourceId 详情）', () => {
  it('数字集群/资源 ID 匹配；非数字不匹配（落入 404 兜底重定向）', () => {
    expect(router.resolve('/clusters/3/resources').name).toBe('cluster-resources')
    expect(router.resolve('/clusters/3/resources/7').name).toBe('resource-detail')
    expect(router.resolve('/clusters/abc/resources').name).not.toBe('cluster-resources')
    expect(router.resolve('/clusters/3/resources/x').name).not.toBe('resource-detail')
    // F002 既有写路由不受影响
    expect(router.resolve('/clusters/3/resources/new').name).toBe('resource-new')
    expect(router.resolve('/clusters/3/resources/7/edit').name).toBe('resource-edit')
  })
})

describe('URL 路由参数 → store 选择（直接进入 / 前进后退 / 集群列表入口）', () => {
  it('进入 /clusters/3/resources：作用域为集群 3，并同步为 store 当前选择', async () => {
    await router.push('/clusters/3/resources')
    await router.isReady()
    mountHost()
    const store = useClusterStore()
    expect(exposed?.scopeClusterId.value).toBe(3)
    expect(store.currentClusterId).toBe(3)
  })

  it('直接进入资源详情 /clusters/3/resources/7：同步 store 选择且不跳转', async () => {
    await router.push('/clusters/3/resources/7')
    await router.isReady()
    mountHost()
    await flush()
    expect(useClusterStore().currentClusterId).toBe(3)
    expect(router.currentRoute.value.name).toBe('resource-detail')
  })

  it('路由前进到另一集群的资源页：同步 store 选择（页面据此刷新列表）', async () => {
    await router.push('/clusters/3/resources')
    await router.isReady()
    mountHost()
    await router.push('/clusters/9/resources')
    await flush()
    expect(exposed?.scopeClusterId.value).toBe(9)
    expect(useClusterStore().currentClusterId).toBe(9)
  })
})

describe('store 选择 → 路由（页头切换集群刷新列表；选择仅改变作用域不改变权限）', () => {
  it('页头切换集群：跳转到新集群的资源列表', async () => {
    await router.push('/clusters/3/resources')
    await router.isReady()
    mountHost()
    useClusterStore().selectCluster(7)
    await flush()
    expect(router.currentRoute.value.fullPath).toBe('/clusters/7/resources')
    expect(exposed?.scopeClusterId.value).toBe(7)
  })

  it('在详情页切换集群：回到新集群的资源列表（原详情属于旧集群，不保留在 URL）', async () => {
    await router.push('/clusters/3/resources/7')
    await router.isReady()
    mountHost()
    useClusterStore().selectCluster(7)
    await flush()
    expect(router.currentRoute.value.fullPath).toBe('/clusters/7/resources')
  })

  it('清除选择（null）：留在本页，作用域为空（页面提示选择集群，不发起查询）', async () => {
    await router.push('/clusters/3/resources')
    await router.isReady()
    mountHost()
    useClusterStore().selectCluster(null)
    await flush()
    expect(router.currentRoute.value.fullPath).toBe('/clusters/3/resources')
    expect(exposed?.scopeClusterId.value).toBeNull()
  })

  it('重复选择同一集群不产生路由跳转（避免循环）', async () => {
    await router.push('/clusters/3/resources')
    await router.isReady()
    mountHost()
    const before = router.currentRoute.value.fullPath
    useClusterStore().selectCluster(3)
    await flush()
    expect(router.currentRoute.value.fullPath).toBe(before)
  })
})

describe('选择失效回退（F001 store.validateSelection 协同）', () => {
  it('store 清除选择（如集群被删除后校验回退）后作用域为空，重新选择后路由恢复', async () => {
    await router.push('/clusters/3/resources')
    await router.isReady()
    mountHost()
    const store = useClusterStore()
    expect(exposed?.scopeClusterId.value).toBe(3)
    // 模拟 F001 validateSelection 失效回退（集群不存在 → 选择置空并提示）
    store.currentClusterId = null
    await flush()
    expect(exposed?.scopeClusterId.value).toBeNull()
    // 作用域恢复（重新选择）后路由随之回到对应集群
    store.selectCluster(5)
    await flush()
    expect(router.currentRoute.value.fullPath).toBe('/clusters/5/resources')
  })
})
