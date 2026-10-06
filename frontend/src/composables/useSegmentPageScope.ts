// 网段页面集群作用域（架构 F005 §2.4）：复用 F001 useClusterStore——
// 当前集群决定网段页面作用域；切换集群（页头选择器）→ 路由跳转到新集群的
// 网段页并由页面刷新列表；直接以 URL 进入/前进后退 → 同步 store 选择；
// 清除选择（null）留在本页，由页面提示“请选择集群”。
// 选择只改变查询作用域，不改变角色权限（需求 §2.1、场景 40/57）。
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useClusterStore } from '../stores/clusters'

/** 路由参数是否为合法集群 ID（路由本身以 \d+ 约束，此处为防御性解析） */
function parseClusterIdParam(param: unknown): number | null {
  if (typeof param !== 'string' || !/^\d+$/.test(param)) return null
  return Number(param)
}

/**
 * 建立路由参数与集群选择的双向同步。
 * - route.params.clusterId → store.selectCluster（URL 即所选集群）；
 * - store.currentClusterId → router.replace（页头切换集群刷新列表）；
 * - 清除选择不导航，scopeClusterId 变为 null，由页面提示选择集群。
 */
export function useSegmentPageScope() {
  const route = useRoute()
  const router = useRouter()
  const clusterStore = useClusterStore()

  // URL 路由参数 → store 选择（直接进入 / 前进后退 / 集群列表行内入口）
  watch(
    () => route.params.clusterId,
    (param) => {
      const id = parseClusterIdParam(param)
      if (id !== null && clusterStore.currentClusterId !== id) {
        clusterStore.selectCluster(id)
      }
    },
    { immediate: true },
  )

  // store 选择 → 路由（页头切换集群）；清除选择（null）留在本页提示
  watch(
    () => clusterStore.currentClusterId,
    (id) => {
      if (id === null) return
      if (route.params.clusterId !== String(id)) {
        void router.replace({ name: 'cluster-segments', params: { clusterId: String(id) } })
      }
    },
  )

  const scopeClusterId = computed(() => clusterStore.currentClusterId)
  const scopeCluster = computed(() => clusterStore.currentCluster)

  return { scopeClusterId, scopeCluster }
}
