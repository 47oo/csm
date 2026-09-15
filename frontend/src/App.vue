<script setup lang="ts">
import { ref } from 'vue'
import ClusterListPage from './pages/ClusterListPage.vue'
import ClusterDetailPage from './pages/ClusterDetailPage.vue'

/**
 * 极简视图状态：在「集群列表」与「集群详情」间切换。
 *
 * F001 不引入 vue-router（docs/architecture/f001-cluster-handoff.md
 * Frontend Work #5 / OPEN #3）：当前只有单一资源页面，用组件状态切换即可；
 * 多资源导航出现（F009 / F010）前再决策路由方案。
 *
 * selectedClusterId 为 null → 列表视图；非 null → 详情视图（按 id 读取）。
 */
const selectedClusterId = ref<number | null>(null)

function openDetail(clusterId: number): void {
  selectedClusterId.value = clusterId
}

function backToList(): void {
  selectedClusterId.value = null
}
</script>

<template>
  <ClusterListPage v-if="selectedClusterId === null" @open-detail="openDetail" />
  <ClusterDetailPage v-else :cluster-id="selectedClusterId" @back="backToList" />
</template>
