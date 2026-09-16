<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getCurrentSession, logout } from './api/auth'
import type { AuthenticatedUser } from './api/auth'
import { setUnauthenticatedHandler } from './api/http'
import LoginPage from './pages/LoginPage.vue'
import ClusterListPage from './pages/ClusterListPage.vue'
import ClusterDetailPage from './pages/ClusterDetailPage.vue'

/**
 * 会话与视图状态（F013；仍不引入 vue-router，f013-auth-handoff.md PROPOSED-5）。
 *
 * 视图状态：bootstrap（启动会话探测中）→ login（未认证 / 会话失效）↔ app（已认证）。
 *
 * - 挂载时 GET /api/auth/session（f013-auth.md §5.3）：已登录 → 直接进入 app；
 *   未登录（401）→ 登录页；
 * - 全局 401（未抑制的请求收到 UNAUTHENTICATED，如会话过期后的资源请求）→
 *   切回 login 并清除当前视图状态（不保留任何资源数据，含 selectedClusterId）；
 * - app 视图头部提供登出按钮：logout() 无论 204 还是 401 都切到 login
 *   （f013-auth.md §5.2 幂等语义：调用方把 204 与 401 归一为同一处理）；
 * - Cookie（csm_session，HttpOnly）由浏览器管理，前端不读不写任何令牌。
 */
type AppView = 'bootstrap' | 'login' | 'app'

const view = ref<AppView>('bootstrap')
const currentUser = ref<AuthenticatedUser | null>(null)
/** 资源视图状态：null → 集群列表；非 null → 集群详情（按 id 读取）。 */
const selectedClusterId = ref<number | null>(null)
const loggingOut = ref(false)

/** 切回登录页并清除当前视图状态（不保留任何资源数据）。 */
function resetToLogin(): void {
  view.value = 'login'
  currentUser.value = null
  selectedClusterId.value = null
}

/** 登录成功 / 启动会话有效 → 进入系统（资源视图从列表开始）。 */
function enterApp(user: AuthenticatedUser): void {
  currentUser.value = user
  selectedClusterId.value = null
  view.value = 'app'
}

function openDetail(clusterId: number): void {
  selectedClusterId.value = clusterId
}

function backToList(): void {
  selectedClusterId.value = null
}

/**
 * 全局未认证处理（api/http.ts）：任意未抑制的请求收到 UNAUTHENTICATED
 * → 会话已失效，引导登录页并清除本地状态。
 */
setUnauthenticatedHandler(resetToLogin)

onMounted(() => {
  void getCurrentSession()
    .then(enterApp)
    .catch(() => {
      // 401 UNAUTHENTICATED → 尚未登录（f013-auth.md §5.3），进入登录页；
      // 其他失败（网络错误等）同样落在登录页，由后续登录尝试暴露服务状态。
      resetToLogin()
    })
})

/**
 * 登出：无论 204 还是 401 都切到 login（f013-auth.md §5.2：登出的幂等语义，
 * 调用方必须把两种结果归一为「清理本地状态 + 跳转登录页」）。
 * 其他失败同样切回登录页：登出请求已发出，本地会话状态不可再作为依据。
 */
async function handleLogout(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await logout()
  } catch {
    // 401 = 会话本已失效（幂等登出）；与 204 走同一归一处理。
  } finally {
    loggingOut.value = false
    resetToLogin()
  }
}
</script>

<template>
  <div class="app-shell" :data-view="view">
    <div v-if="view === 'bootstrap'" class="app-shell__bootstrap">正在加载…</div>
    <LoginPage v-else-if="view === 'login'" @success="enterApp" />
    <template v-else>
      <header class="app-shell__header">
        <span class="app-shell__brand">CSM</span>
        <div class="app-shell__session">
          <span v-if="currentUser !== null" class="app-shell__username">
            {{ currentUser.username }}
          </span>
          <el-button :loading="loggingOut" @click="handleLogout">登出</el-button>
        </div>
      </header>
      <ClusterListPage v-if="selectedClusterId === null" @open-detail="openDetail" />
      <ClusterDetailPage v-else :cluster-id="selectedClusterId" @back="backToList" />
    </template>
  </div>
</template>

<style scoped>
.app-shell__bootstrap {
  padding: 48px 16px;
  color: #909399;
  text-align: center;
}

.app-shell__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 24px;
  background-color: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.app-shell__brand {
  font-size: 18px;
  font-weight: 600;
}

.app-shell__session {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-shell__username {
  color: #606266;
}
</style>
