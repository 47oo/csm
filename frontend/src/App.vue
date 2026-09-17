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
import NetworkInterfaceListPage from './pages/NetworkInterfaceListPage.vue'
import NetworkInterfaceDetailPage from './pages/NetworkInterfaceDetailPage.vue'
import IpAddressListPage from './pages/IpAddressListPage.vue'
import IpAddressDetailPage from './pages/IpAddressDetailPage.vue'
import ContainerListPage from './pages/ContainerListPage.vue'
import ContainerDetailPage from './pages/ContainerDetailPage.vue'
import ServiceListPage from './pages/ServiceListPage.vue'
import ServiceDetailPage from './pages/ServiceDetailPage.vue'

/**
 * 会话与视图状态（F013；仍不引入 vue-router，f013-auth-handoff.md PROPOSED-5；
 * F002 起扩展为 Cluster / BareMetal 两组资源视图，f002-bare-metal-handoff.md
 * Frontend Work #4；F006 起再增加 VirtualMachine 视图，f006-virtual-machine-
 * handoff.md Frontend Work #6；F004 起再增加 NetworkInterface 视图，
 * f004-network-interface-handoff.md Frontend Work #6；F005 起再增加
 * IPAddress 视图，f005-ip-address-handoff.md Frontend Work #6；F007 起再增加
 * Container 视图，f007-container-handoff.md Frontend Work；F008 起再增加
 * Service 视图，f008-service-handoff.md Frontend Work
 * （导航形式不构成产品规则）。
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
 *   returnClusterId 随视图链保留，返回时恢复；
 * - network-interface-list：网络接口列表（F004）；bareMetalId 非空 = 按宿主裸金属
 *   限定（从裸金属详情「查看网络接口」进入，携带 bare_metal_id），null = 全部；
 *   returnClusterId 记录进入前裸金属详情的集群过滤上下文，
 *   返回宿主详情时恢复该上下文；
 * - network-interface-detail：网络接口详情；bareMetalId / returnClusterId 随视图链
 *   保留，返回时恢复；
 * - ip-address-list：IP 地址列表（F005）；networkInterfaceId 非空 = 按父网络
 *   接口限定（从网络接口详情「查看 IP 地址」进入，携带 network_interface_id），
 *   null = 全部；returnBareMetalId / returnClusterId 记录进入前网络接口详情的
 *   列表过滤上下文，返回该详情时恢复该上下文；
 * - ip-address-detail：IP 地址详情；networkInterfaceId / returnBareMetalId /
 *   returnClusterId 随视图链保留，返回时恢复；
 * - container-list：容器列表（F007）；无 App 级过滤上下文（载体筛选为列表页
 *   内能力，carrier_type + carrier_id 成对），返回时回集群列表；
 * - container-detail：容器详情；登记成功后可跳转到新容器的详情（openDetail），
 *   返回时回容器列表；
 * - service-list：服务列表（F008）；无 App 级过滤上下文（载体筛选为列表页
 *   内能力，carrier_type + carrier_id 成对），返回时回集群列表；
 * - service-detail：服务详情；登记成功后可跳转到新服务的详情（openDetail），
 *   返回时回服务列表。
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
  | { kind: 'network-interface-list'; bareMetalId: number | null; returnClusterId: number | null }
  | {
      kind: 'network-interface-detail'
      networkInterfaceId: number
      bareMetalId: number | null
      returnClusterId: number | null
    }
  | {
      kind: 'ip-address-list'
      networkInterfaceId: number | null
      returnBareMetalId: number | null
      returnClusterId: number | null
    }
  | {
      kind: 'ip-address-detail'
      ipAddressId: number
      networkInterfaceId: number | null
      returnBareMetalId: number | null
      returnClusterId: number | null
    }
  | { kind: 'container-list' }
  | { kind: 'container-detail'; containerId: number }
  | { kind: 'service-list' }
  | { kind: 'service-detail'; serviceId: number }

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

// ---- 资源视图导航（NetworkInterface，F004） ----

/** 头部导航进入全局网络接口列表（无过滤）。 */
function openNetworkInterfaceList(): void {
  resourceView.value = {
    kind: 'network-interface-list',
    bareMetalId: null,
    returnClusterId: null,
  }
}

/**
 * 从裸金属详情进入该宿主的网络接口列表（携带 bare_metal_id）；
 * 同时捕获该详情的集群过滤上下文，返回宿主详情时恢复该上下文。
 */
function openBareMetalNetworkInterfaces(bareMetalId: number): void {
  const current = resourceView.value
  const returnClusterId = current.kind === 'bare-metal-detail' ? current.clusterId : null
  resourceView.value = { kind: 'network-interface-list', bareMetalId, returnClusterId }
}

/** 网络接口列表返回：从宿主详情进入的回到该裸金属详情（恢复该上下文），否则回集群列表。 */
function backFromNetworkInterfaceList(): void {
  const current = resourceView.value
  resourceView.value =
    current.kind === 'network-interface-list' && current.bareMetalId !== null
      ? {
          kind: 'bare-metal-detail',
          bareMetalId: current.bareMetalId,
          clusterId: current.returnClusterId,
        }
      : { kind: 'cluster-list' }
}

/** 进入网络接口详情，保留当前列表的过滤上下文（返回时恢复）。 */
function openNetworkInterfaceDetail(networkInterfaceId: number): void {
  const current = resourceView.value
  const bareMetalId = current.kind === 'network-interface-list' ? current.bareMetalId : null
  const returnClusterId =
    current.kind === 'network-interface-list' ? current.returnClusterId : null
  resourceView.value = {
    kind: 'network-interface-detail',
    networkInterfaceId,
    bareMetalId,
    returnClusterId,
  }
}

/** 网络接口详情返回：回到进入前的网络接口列表（保留过滤上下文）。 */
function backFromNetworkInterfaceDetail(): void {
  const current = resourceView.value
  const bareMetalId = current.kind === 'network-interface-detail' ? current.bareMetalId : null
  const returnClusterId =
    current.kind === 'network-interface-detail' ? current.returnClusterId : null
  resourceView.value = { kind: 'network-interface-list', bareMetalId, returnClusterId }
}

// ---- 资源视图导航（IPAddress，F005） ----

/** 头部导航进入全局 IP 地址列表（无过滤）。 */
function openIpAddressList(): void {
  resourceView.value = {
    kind: 'ip-address-list',
    networkInterfaceId: null,
    returnBareMetalId: null,
    returnClusterId: null,
  }
}

/**
 * 从网络接口详情进入该网络接口的 IP 地址列表（携带 network_interface_id）；
 * 同时捕获该详情的列表过滤上下文（宿主裸金属 / 集群），返回时恢复该上下文。
 */
function openNetworkInterfaceIpAddresses(networkInterfaceId: number): void {
  const current = resourceView.value
  const returnBareMetalId =
    current.kind === 'network-interface-detail' ? current.bareMetalId : null
  const returnClusterId =
    current.kind === 'network-interface-detail' ? current.returnClusterId : null
  resourceView.value = {
    kind: 'ip-address-list',
    networkInterfaceId,
    returnBareMetalId,
    returnClusterId,
  }
}

/** IP 地址列表返回：从网络接口详情进入的回到该网络接口详情（恢复该上下文），
 * 否则回集群列表。 */
function backFromIpAddressList(): void {
  const current = resourceView.value
  resourceView.value =
    current.kind === 'ip-address-list' && current.networkInterfaceId !== null
      ? {
          kind: 'network-interface-detail',
          networkInterfaceId: current.networkInterfaceId,
          bareMetalId: current.returnBareMetalId,
          returnClusterId: current.returnClusterId,
        }
      : { kind: 'cluster-list' }
}

/** 进入 IP 地址详情，保留当前列表的过滤上下文（返回时恢复）。 */
function openIpAddressDetail(ipAddressId: number): void {
  const current = resourceView.value
  const networkInterfaceId =
    current.kind === 'ip-address-list' ? current.networkInterfaceId : null
  const returnBareMetalId =
    current.kind === 'ip-address-list' ? current.returnBareMetalId : null
  const returnClusterId =
    current.kind === 'ip-address-list' ? current.returnClusterId : null
  resourceView.value = {
    kind: 'ip-address-detail',
    ipAddressId,
    networkInterfaceId,
    returnBareMetalId,
    returnClusterId,
  }
}

/** IP 地址详情返回：回到进入前的 IP 地址列表（保留过滤上下文）。 */
function backFromIpAddressDetail(): void {
  const current = resourceView.value
  const networkInterfaceId =
    current.kind === 'ip-address-detail' ? current.networkInterfaceId : null
  const returnBareMetalId =
    current.kind === 'ip-address-detail' ? current.returnBareMetalId : null
  const returnClusterId =
    current.kind === 'ip-address-detail' ? current.returnClusterId : null
  resourceView.value = {
    kind: 'ip-address-list',
    networkInterfaceId,
    returnBareMetalId,
    returnClusterId,
  }
}

// ---- 资源视图导航（Container，F007） ----

/** 头部导航进入全局容器列表（无过滤；载体筛选为列表页内能力）。 */
function openContainerList(): void {
  resourceView.value = { kind: 'container-list' }
}

/** 进入容器详情（列表行入口，或详情页登记成功后跳转到新容器）。 */
function openContainerDetail(containerId: number): void {
  resourceView.value = { kind: 'container-detail', containerId }
}

/** 容器详情返回：回到容器列表。 */
function backFromContainerDetail(): void {
  resourceView.value = { kind: 'container-list' }
}

// ---- 资源视图导航（Service，F008） ----

/** 头部导航进入全局服务列表（无过滤；载体筛选为列表页内能力）。 */
function openServiceList(): void {
  resourceView.value = { kind: 'service-list' }
}

/** 进入服务详情（列表行入口，或详情页登记成功后跳转到新服务）。 */
function openServiceDetail(serviceId: number): void {
  resourceView.value = { kind: 'service-detail', serviceId }
}

/** 服务详情返回：回到服务列表。 */
function backFromServiceDetail(): void {
  resourceView.value = { kind: 'service-list' }
}

/** 头部导航高亮：当前资源区域（cluster-* / bare-metal-* / virtual-machine-* /
 * network-interface-* / ip-address-* / container-* / service-*）。 */
const navSection = computed<
  | 'cluster'
  | 'bare-metal'
  | 'virtual-machine'
  | 'network-interface'
  | 'ip-address'
  | 'container'
  | 'service'
>(() => {
  const kind = resourceView.value.kind
  if (kind.startsWith('cluster')) return 'cluster'
  if (kind.startsWith('bare-metal')) return 'bare-metal'
  if (kind.startsWith('virtual-machine')) return 'virtual-machine'
  if (kind.startsWith('network-interface')) return 'network-interface'
  if (kind.startsWith('container')) return 'container'
  if (kind.startsWith('service')) return 'service'
  return 'ip-address'
})

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
            <el-button
              :type="navSection === 'network-interface' ? 'primary' : 'default'"
              data-testid="nav-network-interfaces"
              @click="openNetworkInterfaceList"
            >
              网络接口
            </el-button>
            <el-button
              :type="navSection === 'ip-address' ? 'primary' : 'default'"
              data-testid="nav-ip-addresses"
              @click="openIpAddressList"
            >
              IP 地址
            </el-button>
            <el-button
              :type="navSection === 'container' ? 'primary' : 'default'"
              data-testid="nav-containers"
              @click="openContainerList"
            >
              容器
            </el-button>
            <el-button
              :type="navSection === 'service' ? 'primary' : 'default'"
              data-testid="nav-services"
              @click="openServiceList"
            >
              服务
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
        @open-network-interfaces="openBareMetalNetworkInterfaces"
      />
      <VirtualMachineListPage
        v-else-if="resourceView.kind === 'virtual-machine-list'"
        :bare-metal-id="resourceView.bareMetalId"
        @open-detail="openVirtualMachineDetail"
        @back="backFromVirtualMachineList"
      />
      <VirtualMachineDetailPage
        v-else-if="resourceView.kind === 'virtual-machine-detail'"
        :virtual-machine-id="resourceView.virtualMachineId"
        @back="backFromVirtualMachineDetail"
      />
      <NetworkInterfaceListPage
        v-else-if="resourceView.kind === 'network-interface-list'"
        :bare-metal-id="resourceView.bareMetalId"
        @open-detail="openNetworkInterfaceDetail"
        @back="backFromNetworkInterfaceList"
      />
      <NetworkInterfaceDetailPage
        v-else-if="resourceView.kind === 'network-interface-detail'"
        :network-interface-id="resourceView.networkInterfaceId"
        @back="backFromNetworkInterfaceDetail"
        @open-ip-addresses="openNetworkInterfaceIpAddresses"
      />
      <IpAddressListPage
        v-else-if="resourceView.kind === 'ip-address-list'"
        :network-interface-id="resourceView.networkInterfaceId"
        @open-detail="openIpAddressDetail"
        @back="backFromIpAddressList"
      />
      <IpAddressDetailPage
        v-else-if="resourceView.kind === 'ip-address-detail'"
        :ip-address-id="resourceView.ipAddressId"
        @back="backFromIpAddressDetail"
      />
      <ContainerListPage
        v-else-if="resourceView.kind === 'container-list'"
        @open-detail="openContainerDetail"
        @back="backToClusterList"
      />
      <ContainerDetailPage
        v-else-if="resourceView.kind === 'container-detail'"
        :container-id="resourceView.containerId"
        @open-detail="openContainerDetail"
        @back="backFromContainerDetail"
      />
      <ServiceListPage
        v-else-if="resourceView.kind === 'service-list'"
        @open-detail="openServiceDetail"
        @back="backToClusterList"
      />
      <ServiceDetailPage
        v-else
        :service-id="resourceView.serviceId"
        @open-detail="openServiceDetail"
        @back="backFromServiceDetail"
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
