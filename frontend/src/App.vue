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
import SearchResultsPage from './pages/SearchResultsPage.vue'
import { listClusters } from './api/clusters'
import type { ClusterRead } from './api/clusters'
import { ApiError } from './api/http'

/**
 * 会话与视图状态（F013；仍不引入 vue-router，f013-auth-handoff.md PROPOSED-5；
 * F002 起扩展为 Cluster / BareMetal 两组资源视图，f002-bare-metal-handoff.md
 * Frontend Work #4；F006 起再增加 VirtualMachine 视图，f006-virtual-machine-
 * handoff.md Frontend Work #6；F004 起再增加 NetworkInterface 视图，
 * f004-network-interface-handoff.md Frontend Work #6；F005 起再增加
 * IPAddress 视图，f005-ip-address-handoff.md Frontend Work #6；F007 起再增加
 * Container 视图，f007-container-handoff.md Frontend Work；F008 起再增加
 * Service 视图，f008-service-handoff.md Frontend Work；F018 起侧边栏新增
 * 搜索区与 search 视图（f018-cluster-keyword-search-handoff.md Frontend
 * Work #2，R-QUERY-005 / AC-D5）
 * （导航形式不构成产品规则）。
 *
 * 视图状态：bootstrap（启动会话探测中）→ login（未认证 / 会话失效）↔ app（已认证）。
 *
 * - 挂载时 GET /api/auth/session（f013-auth.md §5.3）：已登录 → 直接进入 app；
 *   未登录（401）→ 登录页；
 * - 全局 401（未抑制的请求收到 UNAUTHENTICATED，如会话过期后的资源请求）→
 *   切回 login 并清除当前视图状态（不保留任何资源数据，含资源视图）；
 * - app 视图侧边栏会话区提供登出按钮：logout() 无论 204 还是 401 都切到 login
 *   （f013-auth.md §5.2 幂等语义：调用方把 204 与 401 归一为同一处理）；
 * - Cookie（csm_session，HttpOnly）由浏览器管理，前端不读不写任何令牌。
 */
type AppView = 'bootstrap' | 'login' | 'app'

/**
 * F010：从裸金属详情「关联资源」进入子资源详情时记录的返回目标
 * （保留返回上下文：裸金属详情及其集群过滤上下文），返回时恢复该视图。
 */
interface BareMetalDetailReturn {
  kind: 'bare-metal-detail'
  bareMetalId: number
  clusterId: number | null
}

/**
 * F018：从搜索结果进入资源详情时记录的返回目标（仿 F010 returnView 模式），
 * 保留搜索上下文（范围 Cluster 与关键字），返回时恢复搜索结果视图。
 */
interface SearchReturn {
  kind: 'search'
  clusterId: number
  keyword: string
}

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
 * - container-detail：容器详情；登记成功后可跳转到新容器的详情（openDetail）；
 *   F010 起从裸金属关联区进入的携带 returnView，返回时回裸金属详情，
 *   否则回容器列表；
 * - service-list：服务列表（F008）；无 App 级过滤上下文（载体筛选为列表页
 *   内能力，carrier_type + carrier_id 成对），返回时回集群列表；
 * - service-detail：服务详情；登记成功后可跳转到新服务的详情（openDetail）；
 *   F010 起从裸金属关联区进入的携带 returnView，返回时回裸金属详情，
 *   否则回服务列表；
 * - search：搜索结果（F018，R-QUERY-005）；单一混合列表（不分组），范围
 *   恒为触发搜索时选定的 Cluster，关键字原样保留；结果行进入六类详情时
 *   以 SearchReturn 携带本视图为返回目标。
 *
 * F010 起五个子资源详情视图均携带可选 returnView（从裸金属详情「关联资源」
 * 进入时的返回目标，保留集群过滤上下文；f010-resource-detail-handoff.md
 * Frontend Work #3，导航形式不构成产品规则）。F018 起六类详情视图从搜索
 * 结果进入时携带 SearchReturn（f018-cluster-keyword-search-handoff.md
 * Frontend Work #2；裸金属详情为 F018 新增的可选字段，其余五类 widening
 * 既有可选字段，未携带时行为不变）。
 */
type ResourceView =
  | { kind: 'cluster-list' }
  | { kind: 'cluster-detail'; clusterId: number }
  | { kind: 'bare-metal-list'; clusterId: number | null }
  | {
      kind: 'bare-metal-detail'
      bareMetalId: number
      clusterId: number | null
      /** F018：从搜索结果进入时的直接返回目标；缺省时返回裸金属列表（不变）。 */
      returnView?: SearchReturn
    }
  | { kind: 'virtual-machine-list'; bareMetalId: number | null; returnClusterId: number | null }
  | {
      kind: 'virtual-machine-detail'
      virtualMachineId: number
      bareMetalId: number | null
      returnClusterId: number | null
      /** F010：从裸金属关联区进入时的直接返回目标；F018 起亦可为搜索视图。 */
      returnView?: BareMetalDetailReturn | SearchReturn
    }
  | { kind: 'network-interface-list'; bareMetalId: number | null; returnClusterId: number | null }
  | {
      kind: 'network-interface-detail'
      networkInterfaceId: number
      bareMetalId: number | null
      returnClusterId: number | null
      /** F010：从裸金属关联区进入时的直接返回目标；F018 起亦可为搜索视图。 */
      returnView?: BareMetalDetailReturn | SearchReturn
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
      /** F010：从裸金属关联区进入时的直接返回目标；F018 起亦可为搜索视图。 */
      returnView?: BareMetalDetailReturn | SearchReturn
    }
  | { kind: 'container-list' }
  | {
      kind: 'container-detail'
      containerId: number
      /** F010：从裸金属关联区进入时的直接返回目标；F018 起亦可为搜索视图；
       * 否则返回容器列表。 */
      returnView?: BareMetalDetailReturn | SearchReturn
    }
  | { kind: 'service-list' }
  | {
      kind: 'service-detail'
      serviceId: number
      /** F010：从裸金属关联区进入时的直接返回目标；F018 起亦可为搜索视图；
       * 否则返回服务列表。 */
      returnView?: BareMetalDetailReturn | SearchReturn
    }
  | { kind: 'search'; clusterId: number; keyword: string }

const view = ref<AppView>('bootstrap')
const currentUser = ref<AuthenticatedUser | null>(null)
const resourceView = ref<ResourceView>({ kind: 'cluster-list' })
const loggingOut = ref(false)

// ---- 外壳搜索区（F018，R-QUERY-005 / AC-D5） ----

/** 搜索范围：已选定的 Cluster（与 resourceView 的集群上下文相互独立，
 * f018 handoff PROPOSED-4）。 */
const searchClusterId = ref<number | null>(null)
/** 搜索关键字（原样值；仅用于「仅空白不可发起」的 UI 前置，不 trim 提交）。 */
const searchKeyword = ref('')
/** Cluster 选项（懒加载：首次展开选择器时 listClusters）。 */
const searchClusterOptions = ref<ClusterRead[]>([])
const searchClusterOptionsLoading = ref(false)
const searchClusterOptionsError = ref<ApiError | null>(null)
/** 选项是否已成功加载（失败不置位，下次展开重试）。 */
let searchClusterOptionsLoaded = false

/** 懒加载 Cluster 选项（与登记对话框同一取法：单次请求取上限重选项）。 */
async function loadSearchClusterOptions(): Promise<void> {
  if (searchClusterOptionsLoaded || searchClusterOptionsLoading.value) return
  searchClusterOptionsLoading.value = true
  searchClusterOptionsError.value = null
  try {
    const data = await listClusters({ page: 1, page_size: 200 })
    searchClusterOptions.value = data.items
    searchClusterOptionsLoaded = true
  } catch (err) {
    searchClusterOptions.value = []
    searchClusterOptionsError.value =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
  } finally {
    searchClusterOptionsLoading.value = false
  }
}

/** 首次展开选择器时懒加载选项（不在挂载时请求，不影响既有页面加载）。 */
function handleSearchClusterVisible(visible: boolean): void {
  if (visible) void loadSearchClusterOptions()
}

/** 搜索发起前置（AC-D5 / R-QUERY-005）：已选定 Cluster 且关键字非仅空白。 */
const searchDisabled = computed(
  () => searchClusterId.value === null || searchKeyword.value.trim() === '',
)

/** 再次触发的序号：同条件重复搜索时强制重新挂载结果页（重新请求）。 */
const searchSequence = ref(0)

function openSearchResults(clusterId: number, keyword: string): void {
  searchSequence.value += 1
  resourceView.value = { kind: 'search', clusterId, keyword }
}

/** 发起搜索：未选定 Cluster 或关键字仅空白时不可发起（按钮禁用同一判定）。 */
function handleSearch(): void {
  if (searchClusterId.value === null) return
  if (searchKeyword.value.trim() === '') return
  openSearchResults(searchClusterId.value, searchKeyword.value)
}

/**
 * F018：捕获当前搜索视图作为返回目标（不在该视图时为 undefined，不生效）；
 * 从搜索结果进入六类资源详情时携带，详情「返回列表」直接回到搜索结果。
 */
function searchReturnView(): SearchReturn | undefined {
  const current = resourceView.value
  return current.kind === 'search'
    ? { kind: 'search', clusterId: current.clusterId, keyword: current.keyword }
    : undefined
}

/** 切回登录页并清除当前视图状态（不保留任何资源数据）。 */
function resetToLogin(): void {
  view.value = 'login'
  currentUser.value = null
  resourceView.value = { kind: 'cluster-list' }
  searchClusterId.value = null
  searchKeyword.value = ''
  searchClusterOptions.value = []
  searchClusterOptionsError.value = null
  searchClusterOptionsLoaded = false
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

/** 进入裸金属详情，保留当前列表的过滤上下文（返回时恢复）；F018 起从
 * 搜索结果进入时携带搜索视图为返回目标。 */
function openBareMetalDetail(bareMetalId: number): void {
  const current = resourceView.value
  const clusterId = current.kind === 'bare-metal-list' ? current.clusterId : null
  resourceView.value = {
    kind: 'bare-metal-detail',
    bareMetalId,
    clusterId,
    returnView: searchReturnView(),
  }
}

/** 裸金属详情返回：F018 搜索进入的优先回搜索结果（保留搜索上下文），
 * 否则回到进入前的裸金属列表（保留 cluster_id 过滤上下文）。 */
function backFromBareMetalDetail(): void {
  const current = resourceView.value
  if (current.kind === 'bare-metal-detail' && current.returnView !== undefined) {
    resourceView.value = { ...current.returnView }
    return
  }
  const clusterId = current.kind === 'bare-metal-detail' ? current.clusterId : null
  resourceView.value = { kind: 'bare-metal-list', clusterId }
}

// ---- 资源视图导航（VirtualMachine，F006） ----

/** 侧边栏导航进入全局虚拟机列表（无过滤）。 */
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

/** 进入虚拟机详情，保留当前列表的过滤上下文（返回时恢复）；F018 起从
 * 搜索结果进入时携带搜索视图为返回目标。 */
function openVirtualMachineDetail(virtualMachineId: number): void {
  const current = resourceView.value
  const bareMetalId = current.kind === 'virtual-machine-list' ? current.bareMetalId : null
  const returnClusterId = current.kind === 'virtual-machine-list' ? current.returnClusterId : null
  resourceView.value = {
    kind: 'virtual-machine-detail',
    virtualMachineId,
    bareMetalId,
    returnClusterId,
    returnView: searchReturnView(),
  }
}

/** 虚拟机详情返回：回到进入前的虚拟机列表（保留过滤上下文）；F010 关联
 * 区进入的优先直接回裸金属详情（保留返回上下文）。 */
function backFromVirtualMachineDetail(): void {
  const current = resourceView.value
  if (current.kind === 'virtual-machine-detail' && current.returnView !== undefined) {
    resourceView.value = { ...current.returnView }
    return
  }
  const bareMetalId = current.kind === 'virtual-machine-detail' ? current.bareMetalId : null
  const returnClusterId = current.kind === 'virtual-machine-detail' ? current.returnClusterId : null
  resourceView.value = { kind: 'virtual-machine-list', bareMetalId, returnClusterId }
}

// ---- 资源视图导航（NetworkInterface，F004） ----

/** 侧边栏导航进入全局网络接口列表（无过滤）。 */
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

/** 进入网络接口详情，保留当前列表的过滤上下文（返回时恢复）；F018 起从
 * 搜索结果进入时携带搜索视图为返回目标。 */
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
    returnView: searchReturnView(),
  }
}

/** 网络接口详情返回：回到进入前的网络接口列表（保留过滤上下文）；F010
 * 关联区进入的优先直接回裸金属详情（保留返回上下文）。 */
function backFromNetworkInterfaceDetail(): void {
  const current = resourceView.value
  if (current.kind === 'network-interface-detail' && current.returnView !== undefined) {
    resourceView.value = { ...current.returnView }
    return
  }
  const bareMetalId = current.kind === 'network-interface-detail' ? current.bareMetalId : null
  const returnClusterId =
    current.kind === 'network-interface-detail' ? current.returnClusterId : null
  resourceView.value = { kind: 'network-interface-list', bareMetalId, returnClusterId }
}

// ---- 资源视图导航（IPAddress，F005） ----

/** 侧边栏导航进入全局 IP 地址列表（无过滤）。 */
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

/** 进入 IP 地址详情，保留当前列表的过滤上下文（返回时恢复）；F018 起从
 * 搜索结果进入时携带搜索视图为返回目标。 */
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
    returnView: searchReturnView(),
  }
}

/** IP 地址详情返回：回到进入前的 IP 地址列表（保留过滤上下文）；F010
 * 关联区进入的优先直接回裸金属详情（保留返回上下文）。 */
function backFromIpAddressDetail(): void {
  const current = resourceView.value
  if (current.kind === 'ip-address-detail' && current.returnView !== undefined) {
    resourceView.value = { ...current.returnView }
    return
  }
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

/** 侧边栏导航进入全局容器列表（无过滤；载体筛选为列表页内能力）。 */
function openContainerList(): void {
  resourceView.value = { kind: 'container-list' }
}

/** 进入容器详情（列表行入口，或详情页登记成功后跳转到新容器）；F018 起
 * 从搜索结果进入时携带搜索视图为返回目标。 */
function openContainerDetail(containerId: number): void {
  resourceView.value = { kind: 'container-detail', containerId, returnView: searchReturnView() }
}

/** 容器详情返回：F010 关联区进入的回裸金属详情（保留返回上下文），否则回容器列表。 */
function backFromContainerDetail(): void {
  const current = resourceView.value
  if (current.kind === 'container-detail' && current.returnView !== undefined) {
    resourceView.value = { ...current.returnView }
    return
  }
  resourceView.value = { kind: 'container-list' }
}

// ---- 资源视图导航（Service，F008） ----

/** 侧边栏导航进入全局服务列表（无过滤；载体筛选为列表页内能力）。 */
function openServiceList(): void {
  resourceView.value = { kind: 'service-list' }
}

/** 进入服务详情（列表行入口，或详情页登记成功后跳转到新服务）；F018 起
 * 从搜索结果进入时携带搜索视图为返回目标。 */
function openServiceDetail(serviceId: number): void {
  resourceView.value = { kind: 'service-detail', serviceId, returnView: searchReturnView() }
}

/** 服务详情返回：F010 关联区进入的回裸金属详情（保留返回上下文），否则回服务列表。 */
function backFromServiceDetail(): void {
  const current = resourceView.value
  if (current.kind === 'service-detail' && current.returnView !== undefined) {
    resourceView.value = { ...current.returnView }
    return
  }
  resourceView.value = { kind: 'service-list' }
}

// ---- 资源视图导航（F010：裸金属详情「关联资源」入口） ----

/** 捕获当前裸金属详情视图作为返回目标（不在该视图时为 undefined，不生效）。 */
function bareMetalReturnView(): BareMetalDetailReturn | undefined {
  const current = resourceView.value
  return current.kind === 'bare-metal-detail'
    ? { kind: 'bare-metal-detail', bareMetalId: current.bareMetalId, clusterId: current.clusterId }
    : undefined
}

/**
 * 从裸金属关联区进入五类子资源详情（AC-17）：记录返回目标（裸金属详情及其
 * 集群过滤上下文），子详情「返回列表」直接回到该目标；同时保留各详情既有的
 * 链式返回上下文（如 NIC 详情 →「查看 IP 地址」后仍可沿链回到裸金属详情）。
 */
function openBareMetalRelatedNetworkInterface(networkInterfaceId: number): void {
  const current = resourceView.value
  const from = current.kind === 'bare-metal-detail' ? current : null
  resourceView.value = {
    kind: 'network-interface-detail',
    networkInterfaceId,
    bareMetalId: from?.bareMetalId ?? null,
    returnClusterId: from?.clusterId ?? null,
    returnView: bareMetalReturnView(),
  }
}

function openBareMetalRelatedIpAddress(ipAddressId: number, networkInterfaceId: number): void {
  const current = resourceView.value
  const from = current.kind === 'bare-metal-detail' ? current : null
  resourceView.value = {
    kind: 'ip-address-detail',
    ipAddressId,
    networkInterfaceId,
    returnBareMetalId: from?.bareMetalId ?? null,
    returnClusterId: from?.clusterId ?? null,
    returnView: bareMetalReturnView(),
  }
}

function openBareMetalRelatedVirtualMachine(virtualMachineId: number): void {
  const current = resourceView.value
  const from = current.kind === 'bare-metal-detail' ? current : null
  resourceView.value = {
    kind: 'virtual-machine-detail',
    virtualMachineId,
    bareMetalId: from?.bareMetalId ?? null,
    returnClusterId: from?.clusterId ?? null,
    returnView: bareMetalReturnView(),
  }
}

function openBareMetalRelatedContainer(containerId: number): void {
  resourceView.value = {
    kind: 'container-detail',
    containerId,
    returnView: bareMetalReturnView(),
  }
}

function openBareMetalRelatedService(serviceId: number): void {
  resourceView.value = {
    kind: 'service-detail',
    serviceId,
    returnView: bareMetalReturnView(),
  }
}

/** 侧边栏导航高亮：当前资源区域（cluster-* / bare-metal-* / virtual-machine-* /
 * network-interface-* / ip-address-* / container-* / service-*）；搜索视图为
 * 跨资源区域，不高亮任何导航项（F018；f018 handoff OPEN-5 的默认策略）。 */
const navSection = computed<
  | 'cluster'
  | 'bare-metal'
  | 'virtual-machine'
  | 'network-interface'
  | 'ip-address'
  | 'container'
  | 'service'
  | null
>(() => {
  const kind = resourceView.value.kind
  if (kind === 'search') return null
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
      <div class="app-shell__layout">
        <aside class="app-shell__sidebar" data-testid="app-sidebar">
          <div class="app-shell__brand">CSM<span>资源管理平台</span></div>
          <nav class="app-shell__nav">
            <el-button
              data-testid="nav-clusters"
              :class="{ 'app-shell__nav-item--active': navSection === 'cluster' }"
              :aria-current="navSection === 'cluster' ? 'true' : undefined"
              @click="openClusterList"
            >
              集群
            </el-button>
            <el-button
              data-testid="nav-bare-metals"
              :class="{ 'app-shell__nav-item--active': navSection === 'bare-metal' }"
              :aria-current="navSection === 'bare-metal' ? 'true' : undefined"
              @click="openBareMetalList"
            >
              裸金属
            </el-button>
            <el-button
              data-testid="nav-virtual-machines"
              :class="{ 'app-shell__nav-item--active': navSection === 'virtual-machine' }"
              :aria-current="navSection === 'virtual-machine' ? 'true' : undefined"
              @click="openVirtualMachineList"
            >
              虚拟机
            </el-button>
            <el-button
              data-testid="nav-network-interfaces"
              :class="{ 'app-shell__nav-item--active': navSection === 'network-interface' }"
              :aria-current="navSection === 'network-interface' ? 'true' : undefined"
              @click="openNetworkInterfaceList"
            >
              网络接口
            </el-button>
            <el-button
              data-testid="nav-ip-addresses"
              :class="{ 'app-shell__nav-item--active': navSection === 'ip-address' }"
              :aria-current="navSection === 'ip-address' ? 'true' : undefined"
              @click="openIpAddressList"
            >
              IP 地址
            </el-button>
            <el-button
              data-testid="nav-containers"
              :class="{ 'app-shell__nav-item--active': navSection === 'container' }"
              :aria-current="navSection === 'container' ? 'true' : undefined"
              @click="openContainerList"
            >
              容器
            </el-button>
            <el-button
              data-testid="nav-services"
              :class="{ 'app-shell__nav-item--active': navSection === 'service' }"
              :aria-current="navSection === 'service' ? 'true' : undefined"
              @click="openServiceList"
            >
              服务
            </el-button>
          </nav>
          <!-- F018 外壳搜索区（R-QUERY-005 / AC-D5）：位于 nav 之后、会话区之前；
               未选定范围或关键字仅空白时按钮禁用、不可发起。搜索控件文本不
               含导航项文案（F017 Risks #1：避免 findButton 首个子串匹配误中）。 -->
          <div class="app-shell__search" data-testid="shell-search-area">
            <div class="app-shell__search-label">资源搜索</div>
            <el-select
              v-model="searchClusterId"
              class="app-shell__search-cluster"
              placeholder="搜索范围"
              size="small"
              data-testid="shell-search-cluster"
              :loading="searchClusterOptionsLoading"
              @visible-change="handleSearchClusterVisible"
            >
              <el-option
                v-for="cluster in searchClusterOptions"
                :key="cluster.id"
                :label="cluster.name"
                :value="cluster.id"
              />
            </el-select>
            <div
              v-if="searchClusterOptionsError !== null"
              class="app-shell__search-hint"
              :data-error-code="searchClusterOptionsError.code"
            >
              搜索范围加载失败（{{ searchClusterOptionsError.code }}）。
              <el-button link type="primary" size="small" @click="loadSearchClusterOptions">
                重试
              </el-button>
            </div>
            <el-input
              v-model="searchKeyword"
              class="app-shell__search-keyword"
              placeholder="关键字"
              size="small"
              data-testid="shell-search-keyword"
            />
            <el-button
              class="app-shell__search-button"
              type="primary"
              size="small"
              data-testid="shell-search"
              :disabled="searchDisabled"
              @click="handleSearch"
            >
              搜索
            </el-button>
          </div>
          <div class="app-shell__session">
            <span v-if="currentUser !== null" class="app-shell__username">
              {{ currentUser.username }}
            </span>
            <el-button :loading="loggingOut" @click="handleLogout">登出</el-button>
          </div>
        </aside>
        <main class="app-shell__content">
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
            @open-network-interface-detail="openBareMetalRelatedNetworkInterface"
            @open-ip-address-detail="openBareMetalRelatedIpAddress"
            @open-virtual-machine-detail="openBareMetalRelatedVirtualMachine"
            @open-container-detail="openBareMetalRelatedContainer"
            @open-service-detail="openBareMetalRelatedService"
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
          <!-- F018 搜索结果：单一混合列表（不分组、不承诺排序）；再次触发搜索时
               以序号 key 强制重新挂载（重新请求）。 -->
          <SearchResultsPage
            v-else-if="resourceView.kind === 'search'"
            :key="searchSequence"
            :cluster-id="resourceView.clusterId"
            :keyword="resourceView.keyword"
            @open-bare-metal-detail="openBareMetalDetail"
            @open-network-interface-detail="openNetworkInterfaceDetail"
            @open-ip-address-detail="openIpAddressDetail"
            @open-virtual-machine-detail="openVirtualMachineDetail"
            @open-container-detail="openContainerDetail"
            @open-service-detail="openServiceDetail"
            @back="backToClusterList"
          />
          <ServiceDetailPage
            v-else
            :service-id="resourceView.serviceId"
            @open-detail="openServiceDetail"
            @back="backFromServiceDetail"
          />
        </main>
      </div>
    </template>
  </div>
</template>

<style scoped>
.app-shell__bootstrap {
  padding: 48px 16px;
  color: #909399;
  text-align: center;
}

.app-shell__layout {
  display: flex;
  align-items: stretch;
  min-height: 100vh;
}

.app-shell__sidebar {
  position: sticky;
  top: 0;
  height: 100dvh;
  overflow-y: auto;
  flex: 0 0 224px;
  width: 224px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 28px 20px 20px;
  background: #fff;
  border-right: 1px solid var(--el-border-color-lighter);
}

.app-shell__brand {
  padding: 0 12px;
  font-size: 25px;
  font-weight: 750;
  letter-spacing: -0.8px;
  color: #1e293b;
}

.app-shell__brand span {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  font-weight: 400;
  letter-spacing: 1px;
  color: #64748b;
}

.app-shell__nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.app-shell__nav .el-button {
  width: 100%;
  height: 40px;
  padding: 0 14px;
  justify-content: flex-start;
  border-color: transparent;
  background: transparent;
  color: #475569;
  border-radius: 8px;
}

.app-shell__nav .el-button:not(.app-shell__nav-item--active):hover {
  background: #f1f5f9;
  color: #1e40af;
}

.app-shell__nav .el-button:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

/* Element Plus 给相邻按钮默认加 margin-left: 12px，纵向堆叠时表现为缩进，复位为 0。 */
.app-shell__nav .el-button + .el-button {
  margin-left: 0;
}

/* 活跃态：当前资源区导航项（class 由 navSection 单一真相源派生，仅呈现）。 */
.app-shell__nav .app-shell__nav-item--active {
  color: #1d4ed8;
  background-color: #eff6ff;
  border-color: transparent;
  font-weight: 600;
  box-shadow: inset 3px 0 0 #2563eb;
}

/* F018 外壳搜索区：nav 之后、会话区之前。 */
.app-shell__search {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  padding: 16px 12px;
  border: 1px solid #e8edf4;
  border-radius: 10px;
  background: #f8fafc;
}

.app-shell__search-label {
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.app-shell__search .el-select,
.app-shell__search .el-input {
  width: 100%;
}

.app-shell__search-hint {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  color: #f56c6c;
  font-size: 12px;
}

.app-shell__search .app-shell__search-button {
  width: 100%;
  height: 32px;
}

.app-shell__search :deep(.el-input__wrapper),
.app-shell__search :deep(.el-select__wrapper) {
  min-height: 32px;
}

.app-shell__session {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.app-shell__username {
  color: #606266;
}

.app-shell__content {
  flex: 1;
  min-width: 0;
  padding: 12px 16px;
}

@media (max-width: 760px) {
  .app-shell__layout {
    flex-direction: column;
  }

  .app-shell__sidebar {
    position: static;
    flex: none;
    width: 100%;
    height: auto;
    overflow: visible;
    padding: 16px;
    gap: 16px;
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  .app-shell__brand {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 0;
    font-size: 22px;
  }

  .app-shell__nav {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .app-shell__nav .el-button {
    justify-content: center;
    padding: 0 4px;
    font-size: 13px;
  }

  .app-shell__search {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    padding: 12px;
  }

  .app-shell__search-label,
  .app-shell__search-hint,
  .app-shell__search-button {
    grid-column: 1 / -1;
  }

  .app-shell__session {
    margin-top: 0;
    padding-top: 0;
    border: 0;
  }

  .app-shell__content {
    padding: 0;
  }
}
</style>
