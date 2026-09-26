<script setup lang="ts">
// 应用页头：导航、集群选择器（架构 F001 §2.3：本次选择持久化 localStorage、
// 刷新恢复；选择仅改变查询作用域，不改变角色权限——场景 40/57）与会话操作。
import { onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiErrorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useClusterStore } from '../stores/clusters'
import { roleLabel } from '../utils/validation'

const router = useRouter()
const auth = useAuthStore()
const clusterStore = useClusterStore()

// 首屏恢复：加载集群列表并恢复记忆的选择（失效时由 store 标记 selectionDropped）
onMounted(() => {
  void clusterStore.restoreSelection()
})

// 记忆的选择已失效（如集群被真实删除）→ 提示重新选择（回退为空）
watch(
  () => clusterStore.selectionDropped,
  (dropped) => {
    if (dropped) {
      ElMessage.warning('之前选择的集群已不存在，请重新选择')
      clusterStore.acknowledgeSelectionDrop()
    }
  },
)

function handleClusterChange(id: number | null | undefined): void {
  // el-select 清空时 change 回调收到 undefined（Element Plus 默认 valueOnClear），统一归一为 null
  clusterStore.selectCluster(typeof id === 'number' ? id : null)
}

async function handleLogout(): Promise<void> {
  try {
    await auth.logout()
    ElMessage.success('已退出登录')
  } catch (error) {
    // 登出接口异常时本地会话已在 store 中清除，仍返回登录页
    ElMessage.warning(`已返回登录页（${apiErrorMessage(error)}）`)
  }
  void router.push({ name: 'login' })
}
</script>

<template>
  <header class="app-header">
    <div class="app-header-inner">
      <div class="app-header-left">
        <span class="app-title">CSM 资源管理平台</span>
        <el-button link type="primary" class="app-nav" @click="router.push({ name: 'clusters' })">
          集群
        </el-button>
        <el-button
          v-if="auth.isAdmin"
          link
          type="primary"
          class="app-nav"
          @click="router.push({ name: 'admin-users' })"
        >
          用户管理
        </el-button>
      </div>
      <div v-if="auth.user" class="app-user">
        <!-- 集群选择器：仅查询作用域，不改变权限（场景 40/57） -->
        <div class="cluster-picker">
          <el-select
            :model-value="clusterStore.currentClusterId"
            clearable
            filterable
            placeholder="集群作用域：全部"
            class="cluster-select"
            data-test-id="cluster-select"
            @change="handleClusterChange"
          >
            <el-option
              v-for="c in clusterStore.clusters"
              :key="c.id"
              :value="c.id"
              :label="`${c.code} ${c.name}`"
            />
          </el-select>
          <el-button
            v-if="clusterStore.loadError"
            link
            type="danger"
            class="cluster-retry"
            @click="clusterStore.loadClusters(true)"
          >
            集群列表加载失败，点击重试
          </el-button>
        </div>
        <span class="app-user-name">
          {{ auth.user.username }}（{{ roleLabel(auth.user.role) }}）
        </span>
        <el-button link type="primary" @click="router.push({ name: 'change-password' })">
          修改密码
        </el-button>
        <el-button link @click="handleLogout">退出登录</el-button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  background-color: #1f2d3d;
  color: #fff;
}
.app-header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.app-header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}
.app-title {
  font-size: 16px;
  font-weight: 600;
  margin-right: 12px;
  white-space: nowrap;
}
.app-nav {
  color: #cfd8e3;
}
.app-user {
  display: flex;
  align-items: center;
  gap: 4px;
}
.cluster-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 12px;
}
.cluster-select {
  width: 200px;
}
.cluster-retry {
  white-space: nowrap;
}
.app-user-name {
  margin-right: 8px;
  color: #cfd8e3;
  white-space: nowrap;
}
</style>
