<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getCurrentSession, logout } from './api/auth'
import type { AuthenticatedUser } from './api/auth'
import { setUnauthenticatedHandler } from './api/http'
import LoginPage from './pages/LoginPage.vue'
import ClusterListPage from './pages/ClusterListPage.vue'
import ClusterDetailPage from './pages/ClusterDetailPage.vue'
import BareMetalListPage from './pages/BareMetalListPage.vue'
import BareMetalDetailPage from './pages/BareMetalDetailPage.vue'
import VirtualMachineListPage from './pages/VirtualMachineListPage.vue'
import VirtualMachineDetailPage from './pages/VirtualMachineDetailPage.vue'

/**
 * 会话与视图状态（F013；仍不引入 vue-router，f013-auth-handoff.md PROPOSED-5；
 * F002 起扩展为 Cluster / BareMetal 两组资源视图，f002-bare-metal-handoff.md
 * Frontend Work #4；F006 起再增加 VirtualMachine 视图，f006-virtual-machine-
 * handoff.md Frontend Work #6：导航形式不构成产品规则）。
 *
 * 视图状态：bootstrap（启动会话探测中）→ login（未认证 / 会话失效）↔ app（已认证）。
 *
 * - 挂载时 GET /api/auth/session（f013-auth.md §5.3）：已登录 → 直接进入 app；
 *   未登录（401）→ 登录页；
 * - 全局 401（未抑制的请求收到 UNAUTHENTICATED，如会话过期后的资源请求）→
 *   切回 login 并清除当前视图状态（不保留任何资源数据，含资源视图）；
 * - app 视图头部提供登出按钮：logout() 无论 204 还是 401 都切到 login
 *   （f013-auth.md §5.2 幂等语义：调用方把 204 与 401 归一为同一处理）；
 * - Cookie（csm_session，HttpOnly）由浏览器管理，前端不读不写任何令牌。
 */
type AppView = 'bootstrap' | 'login' | 'app'

/**
 * 资源视图状态（F002 起含 BareMetal；F006 起含 VirtualMachine）：
 * - cluster-list / cluster-detail：F001 既有视图；
 * - bare-metal-list：裸金属列表；clusterId 非空 = 按 Cluster 限定
 *   （从集群详情「查看裸金属」进入，携带 cluster_id），null = 全部；
 * - bare-metal-detail：裸金属详情；clusterId 记录进入前的列表过滤上下文，
 *   返回时恢复该上下文；
 * - virtual-machine-list：虚拟机列表（F006）；bareMetalId 非空 = 按宿主裸金属
 *   限定（从裸金属详情「查看虚拟机」进入，携带 bare_metal_id），null = 全部；
 *   returnClusterId 记录进入前裸金属详情的集群过滤上下文，
 *   返回宿主详情时恢复该上下文；
 * - virtual-machine-detail：虚拟机详情；bareMetalId 记录进入前的列表过滤上下文，
 *   returnClusterId 随视图链保留，返回时恢复。
 */
type ResourceView =
  | { kind: 'cluster-list' }
  | { kind: 'cluster-detail'; clusterId: number }
  | { kind: 'bare-metal-list'; clusterId: number | null }
  | { kind: 'bare-metal-detail'; bareMetalId: number; clusterId: number | null }
  | { kind: 'virtual-machine-list'; bareMetalId: number | null; returnClusterId: number | null }
  | {
      kind: 'virtual-machine-detail'
      virtualMachineId: number
      bareMetalId: number | null
      returnClusterId: number | null
    }

const view = ref<AppView>('bootstrap')
const currentUser = ref<AuthenticatedUser | null>(null)
const resourceView = ref<ResourceView>({ kind: 'cluster-list' })
const loggingOut = ref(false)

/** 切回登录页并清除当前视图状态（不保留任何资源数据）。 */
function resetToLogin(): void {
  view.value = 'login'
  currentUser.value = null
  resourceView.value = { kind: 'cluster-list' }
}

/** 登录成功 / 启动会话有效 → 进入系统（资源视图从集群列表开始）。 */
function enterApp(user: AuthenticatedUser): void {
  currentUser.value = user
  resourceView.value = { kind: 'cluster-list' }
  view.value = 'app'
}

// ---- 资源视图导航（Cluster ↔ BareMetal） ----

function openClusterList(): void {
  resourceView.value = { kind: 'cluster-list' }
}

function openBareMetalList(): void {
  resourceView.value = { kind: 'bare-metal-list', clusterId: null }
}

function openClusterDetail(clusterId: number): void {
  resourceView.value = { kind: 'cluster-detail', clusterId }
}

function backToClusterList(): void {
  resourceView.value = { kind: 'cluster-list' }
}

/** 从集群详情进入该集群的裸金属列表（携带 cluster_id）。 */
function openClusterBareMetals(clusterId: number): void {
  resourceView.value = { kind: 'bare-metal-list', clusterId }
}

/** 裸金属列表返回：从集群详情进入的回到该集群详情，否则回集群列表。 */
function backFromBareMetalList(): void {
  const current = resourceView.value
  resourceView.value =
    current.kind === 'bare-metal-list' && current.clusterId !== null
      ? { kind: 'cluster-detail', clusterId: current.clusterId }
      : { kind: 'cluster-list' }
}

/** 进入裸金属详情，保留当前列表的过滤上下文（返回时恢复）。 */
function openBareMetalDetail(bareMetalId: number): void {
  const current = resourceView.value
  const clusterId = current.kind === 'bare-metal-list' ? current.clusterId : null
  resourceView.value = { kind: 'bare-metal-detail', bareMetalId, clusterId }
}

/** 裸金属详情返回：回到进入前的裸金属列表（保留 cluster_id 过滤上下文）。 */
function backFromBareMetalDetail(): void {
  const current = resourceView.value
  const clusterId = current.kind === 'bare-metal-detail' ? current.clusterId : null
  resourceView.value = { kind: 'bare-metal-list', clusterId }
}

// ---- 资源视图导航（VirtualMachine，F006） ----

/** 头部导航进入全局虚拟机列表（无过滤）。 */
function openVirtualMachineList(): void {
  resourceView.value = { kind: 'virtual-machine-list', bareMetalId: null, returnClusterId: null }
}

/**
 * 从裸金属详情进入该宿主的虚拟机列表（携带 bare_metal_id）；
 * 同时捕获该详情的集群过滤上下文，返回宿主详情时恢复该上下文。
 */
function openBareMetalVirtualMachines(bareMetalId: number): void {
  const current = resourceView.value
  const returnClusterId = current.kind === 'bare-metal-detail' ? current.clusterId : null
  resourceView.value = { kind: 'virtual-machine-list', bareMetalId, returnClusterId }
}

/** 虚拟机列表返回：从宿主详情进入的回到该裸金属详情（恢复该上下文），否则回集群列表。 */
function backFromVirtualMachineList(): void {
  const current = resourceView.value
  resourceView.value =
    current.kind === 'virtual-machine-list' && current.bareMetalId !== null
      ? { kind: 'bare-metal-detail', bareMetalId: current.bareMetalId, clusterId: current.returnClusterId }
      : { kind: 'cluster-list' }
}

/** 进入虚拟机详情，保留当前列表的过滤上下文（返回时恢复）。 */
function openVirtualMachineDetail(virtualMachineId: number): void {
  const current = resourceView.value
  const bareMetalId = current.kind === 'virtual-machine-list' ? current.bareMetalId : null
  const returnClusterId = current.kind === 'virtual-machine-list' ? current.returnClusterId : null
  resourceView.value = {
    kind: 'virtual-machine-detail',
    virtualMachineId,
    bareMetalId,
    returnClusterId,
  }
}

/** 虚拟机详情返回：回到进入前的虚拟机列表（保留过滤上下文）。 */
function backFromVirtualMachineDetail(): void {
  const current = resourceView.value
  const bareMetalId = current.kind === 'virtual-machine-detail' ? current.bareMetalId : null
  const returnClusterId = current.kind === 'virtual-machine-detail' ? current.returnClusterId : null
  resourceView.value = { kind: 'virtual-machine-list', bareMetalId, returnClusterId }
}

/** 头部导航高亮：当前资源区域（cluster-* / bare-metal-* / virtual-machine-*）。 */
const navSection = computed<'cluster' | 'bare-metal' | 'virtual-machine'>(() =>
  resourceView.value.kind.startsWith('cluster')
    ? 'cluster'
    : resourceView.value.kind.startsWith('bare-metal')
      ? 'bare-metal'
      : 'virtual-machine',
)

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
        <div class="app-shell__brand-nav">
          <span class="app-shell__brand">CSM</span>
          <nav class="app-shell__nav">
            <el-button
              :type="navSection === 'cluster' ? 'primary' : 'default'"
              data-testid="nav-clusters"
              @click="openClusterList"
            >
              集群
            </el-button>
            <el-button
              :type="navSection === 'bare-metal' ? 'primary' : 'default'"
              data-testid="nav-bare-metals"
              @click="openBareMetalList"
            >
              裸金属
            </el-button>
            <el-button
              :type="navSection === 'virtual-machine' ? 'primary' : 'default'"
              data-testid="nav-virtual-machines"
              @click="openVirtualMachineList"
            >
              虚拟机
            </el-button>
          </nav>
        </div>
        <div class="app-shell__session">
          <span v-if="currentUser !== null" class="app-shell__username">
            {{ currentUser.username }}
          </span>
          <el-button :loading="loggingOut" @click="handleLogout">登出</el-button>
        </div>
      </header>
      <ClusterListPage
        v-if="resourceView.kind === 'cluster-list'"
        @open-detail="openClusterDetail"
      />
      <ClusterDetailPage
        v-else-if="resourceView.kind === 'cluster-detail'"
        :cluster-id="resourceView.clusterId"
        @back="backToClusterList"
        @open-bare-metals="openClusterBareMetals"
      />
      <BareMetalListPage
        v-else-if="resourceView.kind === 'bare-metal-list'"
        :cluster-id="resourceView.clusterId"
        @open-detail="openBareMetalDetail"
        @back="backFromBareMetalList"
      />
      <BareMetalDetailPage
        v-else-if="resourceView.kind === 'bare-metal-detail'"
        :bare-metal-id="resourceView.bareMetalId"
        @back="backFromBareMetalDetail"
        @open-virtual-machines="openBareMetalVirtualMachines"
      />
      <VirtualMachineListPage
        v-else-if="resourceView.kind === 'virtual-machine-list'"
        :bare-metal-id="resourceView.bareMetalId"
        @open-detail="openVirtualMachineDetail"
        @back="backFromVirtualMachineList"
      />
      <VirtualMachineDetailPage
        v-else
        :virtual-machine-id="resourceView.virtualMachineId"
        @back="backFromVirtualMachineDetail"
      />
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

.app-shell__brand-nav {
  display: flex;
  align-items: center;
  gap: 24px;
}

.app-shell__brand {
  font-size: 18px;
  font-weight: 600;
}

.app-shell__nav {
  display: flex;
  align-items: center;
  gap: 8px;
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
