// 资源页面集群作用域（架构 F003 §2.4/§7，对齐 F005 useSegmentPageScope）：复用
// F001 useClusterStore——当前集群决定资源列表/详情页作用域；切换集群（页头选择器）→
// 路由跳转到新集群的资源列表并由页面刷新；直接以 URL 进入/前进后退 → 同步 store 选择；
// 清除选择（null）留在本页，由列表页提示“请选择集群”。
// 选择只改变查询作用域，不改变角色权限（需求 §2.1、§6.2、BQ-H；场景 40/57）。
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
 * - route.params.clusterId → store.selectCluster（URL 即所选集群；含资源详情页直接进入）；
 * - store.currentClusterId → router.replace 到 cluster-resources（页头切换集群刷新列表；
 *   详情页下切换集群同样回到列表——原详情资源属于旧集群，不得在 URL 中保留）；
 * - 清除选择不导航，scopeClusterId 变为 null，由页面提示选择集群。
 */
export function useResourcePageScope() {
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
        void router.replace({ name: 'cluster-resources', params: { clusterId: String(id) } })
      }
    },
  )

  const scopeClusterId = computed(() => clusterStore.currentClusterId)
  const scopeCluster = computed(() => clusterStore.currentCluster)

  return { scopeClusterId, scopeCluster }
}
