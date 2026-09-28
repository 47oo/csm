// 资源表单状态机（架构 F002 §2.4 + F006 §2.4）：新增/编辑共用，一次提交公共信息 +
// 全部网卡 + 全部 IP + 管理 IP（整单原子 §4.5）。
// - 新增：集群可选（切换清除不再匹配的网段选择，§7.1）；资源类型必选；创建后只读；
// - 编辑：集群/类型只读回显；网卡卡片区分「删除 / 未修改 / 新增或修改」映射 interfaces[] 显式 op（§5.3）；
//   IP 嵌套显式 op（F006 §5.1：未列出=未修改；不可改地址，改址=删除后重新分配）；
// - IP 分配：每张网卡手动输入 / 自动分配；未选网段禁用分配（§4.6.7、场景 31）；
//   切换网段清除待分配地址（§7.4）；改网段须先释放既有 IP（§7.4/场景 30）；
// - 管理 IP：资源级引用，候选为本表单将保存的 IP（§4.2.9）；删除当前管理 IP/其网卡时
//   强制显式清空/重选，否则前端阻断并提示（§4.2.11/场景 46，MANAGEMENT_IP_REQUIRED）；
// - 同名：409 RESOURCE_NAME_EXISTS → existing_resource_id 弹确认进入编辑（§4.1.10、场景 2/45）；
// - 冲突：409 VERSION_CONFLICT / IP_ALREADY_IN_USE 保留输入（§4.5、场景 47；conflicts 展示归属）；
// - 删除：二次确认须输入资源名称（BQ-Z）；409 RESOURCE_HAS_INTERFACES 引导先删网卡（§6.2）；
// - 字段级错误：errors[]（含 interfaces[i].ips[j].address）定位到具体字段、网卡卡片与 IP 条目，
//   保留已填内容（§7.3）。
// 401/403 由 client 全局拦截；前端权限仅控制入口/按钮可见，服务端为最终校验（§7.2）。
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as resourcesApi from '../api/resources'
import type {
  InterfaceSegmentSummary,
  ManagementIpRef,
  ResourceFormDetail,
  ResourceStatus,
  ResourceType,
} from '../api/resources'
import { getNetworkSegment, listNetworkSegments } from '../api/segments'
import { apiErrorMessage, isApiError } from '../api/client'
import {
  clusterToSearchOption,
  fetchClusterSearchOptions,
  fetchSegmentSearchOptions,
  segmentToSearchOption,
  type SearchOption,
  type SearchOptionsPage,
} from '../utils/searchOptions'
import { useAuthStore } from '../stores/auth'
import { useClusterStore } from '../stores/clusters'
import {
  IP_DUPLICATE_MESSAGE,
  buildCreateInterfaceItems,
  buildInterfaceOps,
  canManageResources,
  emptyInterfaceCardErrors,
  emptyResourceFormErrors,
  findDuplicateInterfaceKeys,
  findDuplicateIpKeys,
  INTERFACE_NAME_DUPLICATE_MESSAGE,
  ipConflictsNotice,
  parseResourceFieldErrors,
  readIpConflicts,
  resourceConflictMessage,
  resourceDeleteConfirmMatches,
  validateInterfaceName,
  validateIpInSegment,
  validateIpv4Address,
  validateResourceName,
  type InterfaceCard,
  type InterfaceCardErrors,
  type InterfaceIpErrors,
  type ResourceFormErrors,
} from '../utils/resourceRules'

export type ResourceFormMode = 'create' | 'edit'

/** 管理 IP 选择（§4.2.9/§4.2.11、Contract F006 §1 ManagementIpRef）：
 * - keep：编辑模式省略 management_ip=不修改（初始）；
 * - none：显式无管理 IP（编辑=清空 management_ip:null；创建=省略）；
 * - pick：选中本表单将保存的某个 IP（cardKey+ipKey 定位，提交解析为
 *   既有 {ip_id} 或本请求内 {interface_index,address}）。 */
export type ManagementIpChoice =
  | { kind: 'keep' }
  | { kind: 'none' }
  | { kind: 'pick'; cardKey: string; ipKey: string }

/** 管理 IP 下拉特殊选项值（与卡片/IP 组合值 `${cardKey}::${ipKey}` 无冲突） */
export const MANAGEMENT_IP_KEEP = '__keep__'
export const MANAGEMENT_IP_NONE = '__none__'

/** 表单网段选项：F002 摘要 + 自动分配范围是否启用（来自 F005 列表数据，用于
 * 「自动分配」入口禁用与提示；编辑兑底摘要未知时为 null——不禁用，由服务端权威判定） */
export interface SegmentOption extends InterfaceSegmentSummary {
  autoAllocEnabled: boolean | null
}

/** 同名确认提示（Contract §0 扩展成员） */
export interface SameNamePrompt {
  existingId: number
  existingType: string
}

/** 网段选项分页拉取保护上限（100/页 × 25 页 = 2500 条） */
const SEGMENT_MAX_PAGES = 25

let cardKeySeq = 0

function nextCardKey(): string {
  cardKeySeq += 1
  return `nic-${cardKeySeq}`
}

let ipKeySeq = 0

function nextIpKey(): string {
  ipKeySeq += 1
  return `ip-${ipKeySeq}`
}

function parsePositiveInt(value: unknown): number | null {
  if (typeof value !== 'string' || !/^\d+$/.test(value)) return null
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : null
}

/** NetworkSegmentListItem → 表单网段选项（含自动分配范围信息） */
function toSegmentOption(s: {
  id: number
  name: string
  cidr: string
  purpose: string
  technology: string
  vlan: number | null
  gateway: string | null
  auto_alloc_enabled: boolean
}): SegmentOption {
  return {
    id: s.id,
    name: s.name,
    cidr: s.cidr,
    purpose: s.purpose,
    technology: s.technology,
    vlan: s.vlan,
    gateway: s.gateway,
    autoAllocEnabled: s.auto_alloc_enabled,
  }
}

export function useResourceForm() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()
  const clusterStore = useClusterStore()

  const mode = computed<ResourceFormMode>(() => (route.name === 'resource-edit' ? 'edit' : 'create'))
  /** 写操作入口可见（服务端为最终校验）；viewer 只读 */
  const canManage = computed(() => canManageResources(auth.user?.role))

  // ---------- 页面加载状态 ----------
  const loading = ref(false)
  const loadError = ref('')
  /** 编辑：资源不存在 / 已被他人删除（404） */
  const notFound = ref(false)

  // ---------- 表单字段 ----------
  const name = ref('')
  const resourceType = ref<ResourceType | ''>('')
  const status = ref<ResourceStatus>('ALLOC')
  const cards = ref<InterfaceCard[]>([])
  /** 编辑中的资源详情（新增为 null；冲突刷新后更新为最新基线） */
  const detail = ref<ResourceFormDetail | null>(null)
  /** 乐观锁版本 */
  const version = ref(0)
  /** 新增模式的集群选择（编辑固定为 detail.cluster_id） */
  const selectedClusterId = ref<number | null>(null)

  // ---------- 网段选项（仅当前集群仍存网段，F005 API；§7.1 显示「名称 · CIDR · 用途」） ----------
  const segmentOptions = ref<SegmentOption[]>([])
  const segmentsLoading = ref(false)
  const segmentsError = ref('')
  /** 编辑加载时网卡已关联网段的摘要兜底（正常情况下均在选项内：RESTRICT 保证仍存；
   * 摘要无自动范围信息 → autoAllocEnabled=null，不禁用自动分配，由服务端权威判定） */
  const detailSegmentById = ref(new Map<number, SegmentOption>())
  let segmentsToken = 0

  // ---------- 提交与错误 ----------
  const submitting = ref(false)
  /** 409 VERSION_CONFLICT：保留输入，须刷新确认后重提（提交被阻止） */
  const conflict = ref(false)
  /** 已刷新版本（保留输入），待用户确认重提 */
  const conflictResolved = ref(false)
  const refreshingVersion = ref(false)
  /** 记录级提示（INTERFACE_NAME_TAKEN / NO_FIELDS / IP 冲突等） */
  const formNotice = ref('')
  /** 字段与网卡卡片/IP 条目级错误（前端校验 + 服务端 errors[] 合并呈现） */
  const fieldErrors = reactive<ResourceFormErrors>(emptyResourceFormErrors())

  // ---------- 管理 IP（§4.2.9/§4.2.11、架构 F006 §5.3） ----------
  const managementIpChoice = ref<ManagementIpChoice>({ kind: 'none' })

  /** 管理 IP 候选：本表单将保存的 IP（既有未删 + 待分配 manual；auto 地址未定不可选） */
  const managementIpCandidates = computed(() => {
    const result: Array<{
      value: string
      cardKey: string
      ipKey: string
      address: string
      interfaceName: string
      label: string
    }> = []
    for (const card of cards.value) {
      if (card.removed) continue
      for (const ip of card.ips) {
        if (ip.removed) continue
        if (ip.id === null && (ip.mode !== 'manual' || ip.address.trim() === '')) continue
        const address = ip.id !== null ? ip.address : ip.address.trim()
        const interfaceName = card.name.trim() !== '' ? card.name.trim() : '未命名网卡'
        result.push({
          value: `${card.key}::${ip.key}`,
          cardKey: card.key,
          ipKey: ip.key,
          address,
          interfaceName,
          label: `${address}（${interfaceName}）`,
        })
      }
    }
    return result
  })

  /** 基线中的当前管理 IP 是否会在本次提交中被删除（其 IP 标记删除或所属网卡标记删除） */
  const currentManagementIpRemoved = computed(() => {
    const current = detail.value?.management_ip
    if (current == null) return false
    for (const card of cards.value) {
      for (const ip of card.ips) {
        if (ip.id === current.ip_id) return ip.removed || card.removed
      }
    }
    return false // 未找到（不应发生）；服务端 MANAGEMENT_IP_REQUIRED 兜底
  })

  /** 所选候选是否仍有效（候选 IP/网卡未在选出后被删除） */
  const pickedManagementIpValid = computed(() => {
    const choice = managementIpChoice.value
    if (choice.kind !== 'pick') return true
    return managementIpCandidates.value.some(
      (c) => c.cardKey === choice.cardKey && c.ipKey === choice.ipKey,
    )
  })

  /** 编辑模式「保持当前」选项文案 */
  const managementKeepLabel = computed(() => {
    const current = detail.value?.management_ip
    return current == null
      ? '保持当前：无管理 IP'
      : `保持当前：${current.address}（${current.interface_name}）`
  })

  /** 管理 IP 下拉当前值（特殊选项值或 `${cardKey}::${ipKey}`） */
  const managementIpValue = computed(() => {
    const choice = managementIpChoice.value
    if (choice.kind === 'keep') return MANAGEMENT_IP_KEEP
    if (choice.kind === 'none') return MANAGEMENT_IP_NONE
    return `${choice.cardKey}::${choice.ipKey}`
  })

  function setManagementIpValue(value: string): void {
    if (!canManage.value) return
    fieldErrors.management_ip = ''
    if (value === MANAGEMENT_IP_KEEP) {
      managementIpChoice.value = { kind: 'keep' }
      return
    }
    if (value === MANAGEMENT_IP_NONE) {
      managementIpChoice.value = { kind: 'none' }
      return
    }
    const candidate = managementIpCandidates.value.find((c) => c.value === value)
    if (candidate !== undefined) {
      managementIpChoice.value = { kind: 'pick', cardKey: candidate.cardKey, ipKey: candidate.ipKey }
    }
  }

  /** 当前基线中某 IP 是否为管理 IP（卡片 IP 列表「管理」标记展示用） */
  function isCurrentManagementIp(ipId: number | null): boolean {
    return ipId !== null && detail.value?.management_ip?.ip_id === ipId
  }

  // ---------- 同名处理（§4.1.10、场景 2/45） ----------
  const sameNamePrompt = ref<SameNamePrompt | null>(null)

  // ---------- 真实删除（BQ-Z + 删除前置） ----------
  const deleteVisible = ref(false)
  const deleteConfirmInput = ref('')
  const deleteSubmitting = ref(false)
  const deleteConfirmError = ref('')
  /** 409 RESOURCE_HAS_INTERFACES / VERSION_CONFLICT 等：保留对话框提示处理路径 */
  const deleteBlockError = ref('')
  const deleteVersionConflict = ref(false)

  // ---------- 工具 ----------

  function cardErrorSlots(key: string): InterfaceCardErrors {
    const existing = fieldErrors.cards[key]
    if (existing !== undefined) return existing
    const created = emptyInterfaceCardErrors()
    fieldErrors.cards[key] = created
    return created
  }

  /** IP 条目错误槽位（首次访问时创建） */
  function cardIpErrorSlots(key: string, ipKey: string): InterfaceIpErrors {
    const card = cardErrorSlots(key)
    const existing = card.ips[ipKey]
    if (existing !== undefined) return existing
    const created: InterfaceIpErrors = { address: '', other: '' }
    card.ips[ipKey] = created
    return created
  }

  function clearAllErrors(): void {
    fieldErrors.name = ''
    fieldErrors.resource_type = ''
    fieldErrors.status = ''
    fieldErrors.cluster_id = ''
    fieldErrors.management_ip = ''
    fieldErrors.cards = {}
    fieldErrors.general = []
  }

  function clearCardError(key: string, slot: 'name' | 'segment_id' | 'other'): void {
    const card = fieldErrors.cards[key]
    if (card !== undefined) card[slot] = ''
  }

  function clearCardIpError(key: string, ipKey: string, slot: 'address' | 'other'): void {
    const ip = fieldErrors.cards[key]?.ips[ipKey]
    if (ip !== undefined) ip[slot] = ''
  }

  /** 选定网段的只读选项（含自动分配范围信息；选项优先，编辑加载的兜底次之） */
  function segmentSummary(segmentId: number | null): SegmentOption | null {
    if (segmentId === null) return null
    for (const s of segmentOptions.value) {
      if (s.id === segmentId) return s
    }
    return detailSegmentById.value.get(segmentId) ?? null
  }

  /** 前端基础校验（§7.2）：必填、接口名非空、同表单接口名/IP 重复、IPv4 语法与
   * CIDR 内（本机可判）、未选网段禁用分配、改网段须释放旧 IP、管理 IP 强制清空/重选；
   * 唯一性/归属/权限/自动分配可用性由服务端最终保证 */
  function validateForm(): boolean {
    let ok = true
    fieldErrors.name = validateResourceName(name.value) ?? ''
    if (fieldErrors.name !== '') ok = false
    if (mode.value === 'create') {
      if (selectedClusterId.value === null) {
        fieldErrors.cluster_id = '请选择所属集群'
        ok = false
      }
      if (resourceType.value === '') {
        fieldErrors.resource_type = '请选择资源类型（创建后不可修改）'
        ok = false
      }
    }
    const liveCards = cards.value.filter((c) => !c.removed)
    const duplicatedKeys = findDuplicateInterfaceKeys(liveCards)
    for (const card of liveCards) {
      const invalid = validateInterfaceName(card.name)
      if (invalid !== null) {
        cardErrorSlots(card.key).name = invalid
        ok = false
      } else if (duplicatedKeys.has(card.key)) {
        cardErrorSlots(card.key).name = INTERFACE_NAME_DUPLICATE_MESSAGE
        ok = false
      }
      // 分配 IP 前必须选定网段（§4.6.7、场景 31；正常路径由入口禁用保证，此处兜底）
      if (card.ips.some((ip) => ip.id === null) && card.segmentId === null) {
        cardErrorSlots(card.key).segment_id = resourceConflictMessage('SEGMENT_NOT_SELECTED') ?? '请先选择网段，再分配 IP'
        ok = false
      }
      // 已有 IP 的网卡不能只改网段后保留旧地址（§7.4、场景 30；须先显式释放）
      if (
        card.id !== null &&
        card.segmentId !== card.originalSegmentId &&
        card.ips.some((ip) => ip.id !== null && !ip.removed)
      ) {
        cardErrorSlots(card.key).segment_id =
          resourceConflictMessage('INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE') ?? '改网段前须先删除该网卡的全部 IP'
        ok = false
      }
    }
    // IP 条目：manual 地址语法、CIDR 内（本机客户端判断）、同表单重复（§7.2）
    const duplicatedIpKeys = findDuplicateIpKeys(liveCards)
    for (const card of liveCards) {
      for (const ip of card.ips) {
        if (ip.removed) continue
        if (ip.id === null && ip.mode === 'manual') {
          const syntaxError = validateIpv4Address(ip.address)
          if (syntaxError !== null) {
            cardIpErrorSlots(card.key, ip.key).address = syntaxError
            ok = false
            continue
          }
          const cidr = segmentSummary(card.segmentId)?.cidr
          const inSegmentError = validateIpInSegment(ip.address, cidr)
          if (inSegmentError !== null) {
            cardIpErrorSlots(card.key, ip.key).address = inSegmentError
            ok = false
            continue
          }
        }
        if (duplicatedIpKeys.has(ip.key)) {
          cardIpErrorSlots(card.key, ip.key).address = IP_DUPLICATE_MESSAGE
          ok = false
        }
      }
    }
    // 管理 IP（§4.2.11/场景 46）：删除当前管理 IP/其网卡时须同次显式清空/重选，前端阻断
    if (mode.value === 'edit' && managementIpChoice.value.kind === 'keep' && currentManagementIpRemoved.value) {
      fieldErrors.management_ip = resourceConflictMessage('MANAGEMENT_IP_REQUIRED') ?? '请显式清空或重选管理 IP'
      ok = false
    }
    if (!pickedManagementIpValid.value) {
      fieldErrors.management_ip = '所选管理 IP 对应的 IP 或网卡已被删除：请重新选择或显式清空管理 IP'
      ok = false
    }
    return ok
  }

  // ---------- 网段选项加载 ----------

  async function loadSegmentOptions(clusterId: number): Promise<void> {
    const token = ++segmentsToken
    segmentsLoading.value = true
    segmentsError.value = ''
    try {
      const items: SegmentOption[] = []
      let page = 1
      while (page <= SEGMENT_MAX_PAGES) {
        const data = await listNetworkSegments({ cluster_id: clusterId, page, page_size: 100, sort: 'name' })
        if (token !== segmentsToken) return
        for (const s of data.items) items.push(toSegmentOption(s))
        if (items.length >= data.total || data.items.length === 0) break
        page += 1
      }
      segmentOptions.value = items
    } catch (error) {
      // 失败保留旧选项并显式提示（不伪装成空列表）
      if (token === segmentsToken) segmentsError.value = apiErrorMessage(error)
    } finally {
      if (token === segmentsToken) segmentsLoading.value = false
    }
  }

  function retryLoadSegments(): void {
    const clusterId = selectedClusterId.value
    if (clusterId !== null) void loadSegmentOptions(clusterId)
  }

  // ---------- 网段/集群下拉数据源（F008 §4.2/§5.1、需求 §8.1：服务端 q 模糊匹配） ----------

  /** 网段下拉初始候选与选中回显（全量列表 → SearchOption；label=名称·CIDR·用途，§7.1）。
   * 列表加载失败或加载后新建的网段由 segmentFetcher 服务端搜索补充，选中后
   * ensureSegmentSummary 补取摘要 */
  const segmentSearchOptions = computed<SearchOption[]>(() =>
    segmentOptions.value.map(segmentToSearchOption),
  )

  /** 集群下拉初始候选与回显（F001 store 缓存 → SearchOption；label=编号 名称） */
  const clusterSearchOptions = computed<SearchOption[]>(() =>
    clusterStore.clusters.map(clusterToSearchOption),
  )

  /** 网段下拉数据源（F008 §5.1）：服务端 q 匹配 网段名称/CIDR/用途/技术类型，
   * cluster_id 作用域 + sort=name + 小 page_size；匹配与排序在服务端完成（§8.2）。
   * 未选集群时不请求（§7.1 只列出当前集群网段，无作用域不提供候选） */
  function segmentFetcher(query: string, page: number, pageSize: number): Promise<SearchOptionsPage> {
    const clusterId = selectedClusterId.value
    if (clusterId === null) return Promise.resolve({ items: [], total: 0 })
    return fetchSegmentSearchOptions(clusterId, query, page, pageSize)
  }

  /** 集群下拉数据源（F008 §5.1）：服务端 q 匹配 集群名称/编号；sort=name + 小 page_size */
  function clusterFetcher(query: string, page: number, pageSize: number): Promise<SearchOptionsPage> {
    return fetchClusterSearchOptions(query, page, pageSize)
  }

  /** 选中网段但全量列表无摘要（列表加载失败 / 加载后才新建的网段）时补取详情，
   * 供只读带出（§4.2.7/§7.1）与自动分配范围提示；补取失败不阻断选择，
   * 网段存在性/归属由服务端在提交时权威校验 */
  async function ensureSegmentSummary(segmentId: number): Promise<void> {
    if (segmentSummary(segmentId) !== null) return
    try {
      const d = await getNetworkSegment(segmentId)
      // 竞态/跨集群防护：响应所属集群与当前选择不一致（切换中或已过期）时丢弃
      if (d.cluster_id !== selectedClusterId.value) return
      if (segmentSummary(segmentId) !== null) return
      segmentOptions.value = [...segmentOptions.value, toSegmentOption(d)]
    } catch {
      // 补取失败：只读带出保持缺失；不伪装数据，提交仍由服务端校验
    }
  }

  // ---------- 详情应用 ----------

  function applyDetail(d: ResourceFormDetail): void {
    detail.value = d
    version.value = d.version
    name.value = d.name
    resourceType.value = d.resource_type
    status.value = d.status
    selectedClusterId.value = d.cluster_id
    cards.value = d.interfaces.map((i) => ({
      key: nextCardKey(),
      id: i.id,
      name: i.name,
      segmentId: i.segment_id,
      originalName: i.name,
      originalSegmentId: i.segment_id,
      removed: false,
      ips: i.ips.map((ip) => ({
        key: nextIpKey(),
        id: ip.id,
        mode: 'manual' as const,
        address: ip.address,
        segmentId: ip.segment_id,
        removed: false,
      })),
    }))
    detailSegmentById.value = new Map(
      d.interfaces
        .filter((i) => i.segment !== null)
        .map((i) => [i.segment!.id, { ...i.segment!, autoAllocEnabled: null }]),
    )
    // 保存成功/加载详情后以响应为基线：管理 IP 回到「保持当前」
    managementIpChoice.value = { kind: 'keep' }
  }

  // ---------- 初始化（路由驱动：新增 ↔ 编辑 / 不同资源均重新加载） ----------

  async function init(): Promise<void> {
    loading.value = true
    loadError.value = ''
    notFound.value = false
    conflict.value = false
    conflictResolved.value = false
    formNotice.value = ''
    sameNamePrompt.value = null
    deleteVisible.value = false
    clearAllErrors()
    cards.value = []
    name.value = ''
    resourceType.value = ''
    status.value = 'ALLOC'
    detail.value = null
    version.value = 0
    selectedClusterId.value = null
    segmentOptions.value = []
    detailSegmentById.value = new Map()
    // 新增模式无基线管理 IP；编辑模式在 applyDetail 中重置为「保持当前」
    managementIpChoice.value = { kind: 'none' }
    try {
      if (mode.value === 'create') {
        const clusterId = parsePositiveInt(route.params.clusterId)
        if (clusterId === null) {
          loadError.value = '路由参数非法：集群 ID 必须为正整数'
          return
        }
        selectedClusterId.value = clusterId
        // 集群选择数据源（复用 F001 store 缓存）；加载失败由 store 记录并可在视图重试
        await clusterStore.loadClusters()
        // URL 即作用域：同步为当前集群选择（与 F005 页面一致；仅改作用域，不改权限）
        clusterStore.selectCluster(clusterId)
        if (clusterStore.loaded && !clusterStore.clusters.some((c) => c.id === clusterId)) {
          loadError.value = '所选集群不存在或已被删除，请返回集群列表重新选择'
          return
        }
        await loadSegmentOptions(clusterId)
      } else {
        const resourceId = parsePositiveInt(route.params.resourceId)
        if (resourceId === null) {
          loadError.value = '路由参数非法：资源 ID 必须为正整数'
          return
        }
        const d = await resourcesApi.getResource(resourceId)
        applyDetail(d)
        clusterStore.selectCluster(d.cluster_id)
        await loadSegmentOptions(d.cluster_id)
      }
    } catch (error) {
      if (isApiError(error) && error.code === 'RESOURCE_NOT_FOUND') {
        notFound.value = true
      } else if (!(isApiError(error) && (error.status === 401 || error.status === 403))) {
        // 401/403 已由全局处理器处理；其余错误显式呈现
        loadError.value = apiErrorMessage(error)
      }
    } finally {
      loading.value = false
    }
  }

  watch(
    () => route.fullPath,
    () => {
      if (route.name === 'resource-new' || route.name === 'resource-edit') {
        void init()
      }
    },
    { immediate: true },
  )

  // ---------- 集群选择（仅新增模式；切换清除不再匹配的网段选择，§7.1） ----------

  async function selectCluster(id: number | null): Promise<void> {
    if (mode.value !== 'create') return
    selectedClusterId.value = id
    fieldErrors.cluster_id = ''
    if (id === null) {
      segmentOptions.value = []
      segmentsError.value = ''
      segmentsToken += 1
      segmentsLoading.value = false
      for (const card of cards.value) {
        card.segmentId = null
        // 切换集群后原网段选择失效：待分配地址一并清除（§7.1/§7.4）
        card.ips = card.ips.filter((ip) => ip.id !== null)
      }
      return
    }
    // 切换集群即失效旧作用域：先清空旧集群候选再加载新集群（§7.1）。
    // 加载失败也不回退旧集群列表——网段下拉（FuzzySelect 服务端搜索）随 selectedClusterId
    // 重建并自行取新集群初始候选，不依赖此全量列表；全量列表仅供摘要/自动分配范围/清理判定
    segmentOptions.value = []
    await loadSegmentOptions(id)
    for (const card of cards.value) {
      if (card.segmentId !== null && !segmentOptions.value.some((s) => s.id === card.segmentId)) {
        // 原网段不再匹配：清除选择并清除其待分配地址（§7.1/§7.4）
        card.segmentId = null
        card.ips = card.ips.filter((ip) => ip.id !== null)
      }
    }
  }

  // ---------- 网卡卡片与 IP 条目 ----------

  function addInterface(): void {
    if (!canManage.value) return
    cards.value.push({
      key: nextCardKey(),
      id: null,
      name: '',
      segmentId: null,
      originalName: '',
      originalSegmentId: null,
      removed: false,
      ips: [],
    })
  }

  /** 删除网卡：编辑模式的既有网卡标记「将删除」（可恢复，提交映射 op:'delete'，
   * 同项携带其全部既有 IP 的显式删除——否则服务端 INTERFACE_HAS_IPS；待分配条目随卡片取消）；
   * 新增网卡/新增模式直接移除卡片 */
  function removeInterface(key: string): void {
    if (!canManage.value) return
    const card = cards.value.find((c) => c.key === key)
    if (card === undefined) return
    if (mode.value === 'edit' && card.id !== null) {
      card.removed = true
      for (const ip of card.ips) {
        if (ip.id !== null) ip.removed = true
      }
      card.ips = card.ips.filter((ip) => ip.id !== null)
    } else {
      cards.value = cards.value.filter((c) => c.key !== key)
    }
    delete fieldErrors.cards[key]
  }

  /** 恢复网卡：一并恢复其 IP 的删除标记（此前单独标记删除的 IP 也随之恢复，可再单独删除） */
  function restoreInterface(key: string): void {
    if (!canManage.value) return
    const card = cards.value.find((c) => c.key === key)
    if (card === undefined) return
    card.removed = false
    for (const ip of card.ips) ip.removed = false
  }

  /** 切换网卡网段（§7.4）：清除原网段的待分配地址并提示重新选择分配方式；
   * 既有 IP 不自动清除（改网段须先显式释放，见提交校验 INTERFACE_SEGMENT_CHANGE_REQUIRES_IP_RELEASE） */
  function setCardSegment(card: InterfaceCard, segmentId: number | null): void {
    if (card.segmentId === segmentId) {
      card.segmentId = segmentId
      return
    }
    card.segmentId = segmentId
    clearCardError(card.key, 'segment_id')
    // 服务端搜索选中的网段可能不在全量列表（列表加载失败/加载后新建）：补取摘要供只读带出
    if (segmentId !== null) void ensureSegmentSummary(segmentId)
    const pendingCount = card.ips.filter((ip) => ip.id === null).length
    if (pendingCount > 0) {
      card.ips = card.ips.filter((ip) => ip.id !== null)
      ElMessage.info('已清除原网段的待分配 IP 地址，请重新选择分配方式')
    }
  }

  // ---------- 网卡 IP 条目（F006：手动输入 / 自动分配；未选网段禁用） ----------

  /** 新增待分配 IP 条目：manual 须随后填写地址；auto 由服务端在网段启用范围内选址。
   * 未选网段时禁止分配（§4.6.7、场景 31）——入口已禁用，此处兜底 */
  function addCardIp(card: InterfaceCard, ipMode: 'manual' | 'auto'): void {
    if (!canManage.value || card.removed || card.segmentId === null) return
    card.ips.push({
      key: nextIpKey(),
      id: null,
      mode: ipMode,
      address: '',
      segmentId: card.segmentId,
      removed: false,
    })
  }

  /** 删除 IP：既有 IP 标记「将删除」（可恢复，提交映射 op:'delete'，真实删除释放占用）；
   * 待分配条目直接移除 */
  function removeCardIp(card: InterfaceCard, ipKey: string): void {
    if (!canManage.value) return
    const index = card.ips.findIndex((ip) => ip.key === ipKey)
    if (index === -1) return
    const ip = card.ips[index]!
    if (ip.id !== null && mode.value === 'edit') {
      ip.removed = true
    } else {
      card.ips.splice(index, 1)
    }
  }

  function restoreCardIp(card: InterfaceCard, ipKey: string): void {
    if (!canManage.value) return
    const ip = card.ips.find((i) => i.key === ipKey)
    if (ip !== undefined) ip.removed = false
  }

  // ---------- 同名处理（§4.1.10、场景 2/45） ----------

  function dismissSameName(): void {
    sameNamePrompt.value = null
  }

  /** 确认进入既有资源编辑（按稳定 ID；不创建第二条、不覆盖、不合并） */
  function confirmSameNameGoEdit(): void {
    const prompt = sameNamePrompt.value
    const clusterId = selectedClusterId.value
    if (prompt === null || clusterId === null) return
    sameNamePrompt.value = null
    void router.push({
      name: 'resource-edit',
      params: { clusterId: String(clusterId), resourceId: String(prompt.existingId) },
    })
  }

  // ---------- 提交错误呈现（409/400/422/404；401/403 全局处理） ----------

  function handleSubmitError(error: unknown, cardKeys: string[], ipKeys: string[][] = []): void {
    if (!isApiError(error)) {
      formNotice.value = apiErrorMessage(error)
      return
    }
    if (error.status === 401 || error.status === 403) return
    if (error.code === 'RESOURCE_NAME_EXISTS') {
      if (mode.value === 'create') {
        // §4.1.10：用扩展成员 existing_resource_id 弹确认进入编辑；输入保留
        const existingId = error.extensions['existing_resource_id']
        if (typeof existingId === 'number' && Number.isInteger(existingId) && existingId > 0) {
          const existingType = error.extensions['existing_resource_type']
          sameNamePrompt.value = {
            existingId,
            existingType: typeof existingType === 'string' ? existingType : '',
          }
        } else {
          formNotice.value = resourceConflictMessage('RESOURCE_NAME_EXISTS') ?? apiErrorMessage(error)
        }
      } else {
        // 改名冲突：定位到名称字段，保留输入
        fieldErrors.name = resourceConflictMessage('RESOURCE_NAME_EXISTS') ?? error.message
      }
      return
    }
    if (error.code === 'VERSION_CONFLICT') {
      // §4.5/场景 47：保留输入并提示；刷新确认后才能重提
      conflict.value = true
      conflictResolved.value = false
      return
    }
    if (error.code === 'INTERFACE_NAME_TAKEN') {
      formNotice.value = resourceConflictMessage('INTERFACE_NAME_TAKEN') ?? error.message
      return
    }
    if (error.code === 'CLUSTER_NOT_FOUND') {
      formNotice.value = resourceConflictMessage('CLUSTER_NOT_FOUND') ?? error.message
      return
    }
    if (error.code === 'RESOURCE_NOT_FOUND') {
      notFound.value = true
      return
    }
    if (error.code === 'NO_FIELDS') {
      formNotice.value = resourceConflictMessage('NO_FIELDS') ?? error.message
      return
    }
    // ---- F006：IP 冲突（409，附 conflicts 归属；保留输入） ----
    if (
      error.code === 'IP_ALREADY_IN_USE' ||
      error.code === 'NO_AVAILABLE_ADDRESS' ||
      error.code === 'INTERFACE_HAS_IPS'
    ) {
      // errors[]（如有 interfaces[i].ips[j] 下标）定位到具体网卡卡片与 IP 条目，保留输入
      const parsed = applyProblemFieldErrors(error, cardKeys, ipKeys)
      const conflictsNotice = ipConflictsNotice(readIpConflicts(error.extensions))
      if (conflictsNotice !== '') {
        formNotice.value = conflictsNotice
      } else if (parsed.general.length > 0) {
        formNotice.value = parsed.general.join('；')
      } else {
        formNotice.value = resourceConflictMessage(error.code) ?? error.message
      }
      return
    }
    // ---- F006：管理 IP 强制清空/重选（422） ----
    if (error.code === 'MANAGEMENT_IP_REQUIRED' || error.code === 'MANAGEMENT_IP_INVALID') {
      const parsed = applyProblemFieldErrors(error, cardKeys, ipKeys)
      if (parsed.management_ip === '') {
        fieldErrors.management_ip = resourceConflictMessage(error.code) ?? error.message
      }
      if (parsed.general.length > 0) {
        formNotice.value = parsed.general.join('；')
      }
      return
    }
    if (
      (error.status === 400 && error.code === 'INVALID_REQUEST') ||
      (error.status === 422 && error.code === 'VALIDATION_ERROR')
    ) {
      // 字段级 errors[]：定位到表单字段、网卡卡片与 IP 条目（含 interfaces[i].xxx /
      // interfaces[i].ips[j].xxx 下标），保留输入
      const parsed = applyProblemFieldErrors(error, cardKeys, ipKeys)
      if (parsed.general.length > 0) {
        formNotice.value = parsed.general.join('；')
      } else if (
        parsed.name === '' &&
        parsed.resource_type === '' &&
        parsed.status === '' &&
        parsed.cluster_id === '' &&
        parsed.management_ip === '' &&
        Object.keys(parsed.cards).length === 0
      ) {
        formNotice.value = error.message
      }
      return
    }
    formNotice.value = apiErrorMessage(error)
  }

  /** problem+json errors[] → 表单字段/卡片/IP 条目定位（保留输入；§7.3） */
  function applyProblemFieldErrors(
    error: { errors: Parameters<typeof parseResourceFieldErrors>[0] },
    cardKeys: string[],
    ipKeys: string[][],
  ) {
    const parsed = parseResourceFieldErrors(error.errors, cardKeys, ipKeys)
    fieldErrors.name = parsed.name
    fieldErrors.resource_type = parsed.resource_type
    fieldErrors.status = parsed.status
    fieldErrors.cluster_id = parsed.cluster_id
    fieldErrors.management_ip = parsed.management_ip
    for (const [key, cardError] of Object.entries(parsed.cards)) {
      fieldErrors.cards[key] = cardError
    }
    return parsed
  }

  // ---------- 管理 IP 引用解析（Contract F006 §1 ManagementIpRef / §2） ----------

  /** 解析管理 IP 选择为请求引用：既有 IP → { ip_id }；本请求内新建 IP →
   * { interface_index, address }（interface_index = 请求 interfaces[] 0 基下标，由构建
   * 结果的 cardKeys 反查）；keep → undefined（省略=不修改，仅编辑）；none → 编辑显式
   * 清空（null）/创建省略 */
  function buildManagementIpRef(
    choice: ManagementIpChoice,
    cardKeys: string[],
  ): ManagementIpRef | null | undefined {
    if (choice.kind === 'keep') return undefined
    if (choice.kind === 'none') return mode.value === 'edit' ? null : undefined
    const card = cards.value.find((c) => c.key === choice.cardKey)
    const ip = card?.ips.find((i) => i.key === choice.ipKey)
    if (card === undefined || ip === undefined) return undefined
    // 既有 IP（含未列入 interfaces[] 的未修改网卡上的）：以 ip_id 引用，无需下标
    if (ip.id !== null) return { ip_id: ip.id }
    // 本请求内新建的 IP：以 {interface_index, address} 引用；其网卡必然在 interfaces[]
    // 内（携带 ips 显式操作），cardKeys 反查 0 基下标
    const cardIndex = cardKeys.indexOf(choice.cardKey)
    if (cardIndex === -1) return undefined
    return { interface_index: cardIndex, address: ip.address.trim() }
  }

  // ---------- 提交（一次提交公共信息 + 全部网卡 + 全部 IP + 管理 IP，整单原子 §4.5） ----------

  async function submit(): Promise<void> {
    if (submitting.value || !canManage.value || conflict.value) return
    clearAllErrors()
    formNotice.value = ''
    if (!validateForm()) return

    submitting.value = true
    try {
      if (mode.value === 'create') {
        const { items, cardKeys } = buildCreateInterfaceItems(cards.value)
        const clusterId = selectedClusterId.value
        if (clusterId === null) return
        const managementRef = buildManagementIpRef(managementIpChoice.value, cardKeys)
        const created = await resourcesApi.createResource({
          cluster_id: clusterId,
          name: name.value,
          resource_type: resourceType.value as ResourceType,
          status: status.value,
          ...(items.length > 0 ? { interfaces: items } : {}),
          ...(managementRef !== undefined ? { management_ip: managementRef } : {}),
        })
        ElMessage.success('资源已创建')
        // 成功后进入该资源的编辑表单展示保存结果（统一详情页属 F003）
        void router.replace({
          name: 'resource-edit',
          params: { clusterId: String(created.cluster_id), resourceId: String(created.id) },
        })
      } else {
        const d = detail.value
        if (d === null) return
        const { ops, cardKeys } = buildInterfaceOps(cards.value)
        const nameChanged = name.value.trim() !== d.name
        const statusChanged = status.value !== d.status
        const managementChanged = managementIpChoice.value.kind !== 'keep'
        if (!nameChanged && !statusChanged && ops.length === 0 && !managementChanged) {
          // 无可改字段（Contract §2.3 NO_FIELDS 语义；前端预检）
          formNotice.value = '没有可保存的修改：未修改任何公共信息、网卡、IP 或管理 IP'
          return
        }
        const managementRef = buildManagementIpRef(managementIpChoice.value, cardKeys)
        const updated = await resourcesApi.updateResource(d.id, {
          ...(nameChanged ? { name: name.value } : {}),
          ...(statusChanged ? { status: status.value } : {}),
          ...(ops.length > 0 ? { interfaces: ops } : {}),
          ...(managementRef !== undefined ? { management_ip: managementRef } : {}),
          version: version.value,
        })
        // 展示保存结果：以响应重建表单基线（含自增 version 与网卡最新状态）
        applyDetail(updated)
        conflict.value = false
        conflictResolved.value = false
        ElMessage.success('资源已保存')
      }
    } catch (error) {
      const build =
        mode.value === 'create' ? buildCreateInterfaceItems(cards.value) : buildInterfaceOps(cards.value)
      handleSubmitError(error, build.cardKeys, build.ipKeys)
    } finally {
      submitting.value = false
    }
  }

  // ---------- 冲突后刷新版本（§4.5：刷新确认后重提；保留当前输入） ----------

  async function refreshVersionKeepInput(): Promise<void> {
    const d = detail.value
    if (d === null || refreshingVersion.value) return
    refreshingVersion.value = true
    try {
      const latest = await resourcesApi.getResource(d.id)
      // 仅更新版本与基线（名称比较基准/只读回显）；用户输入全部保留
      detail.value = latest
      version.value = latest.version
      conflict.value = false
      conflictResolved.value = true
      deleteVersionConflict.value = false
      deleteBlockError.value = ''
    } catch (error) {
      if (isApiError(error) && error.code === 'RESOURCE_NOT_FOUND') {
        notFound.value = true
        deleteVisible.value = false
      } else if (!(isApiError(error) && (error.status === 401 || error.status === 403))) {
        ElMessage.error(apiErrorMessage(error))
      }
    } finally {
      refreshingVersion.value = false
    }
  }

  // ---------- 真实删除（BQ-Z 二次确认 + 删除前置 §6.2） ----------

  /** 二次确认输入与资源名称匹配（去首尾空格、区分大小写）才允许提交 */
  const deleteConfirmMatched = computed(
    () => detail.value !== null && resourceDeleteConfirmMatches(deleteConfirmInput.value, detail.value),
  )

  /** 仍存（未标记删除）的既有网卡数量：删除前置提示 */
  const remainingInterfaceCount = computed(
    () => cards.value.filter((c) => c.id !== null && !c.removed).length,
  )

  function openDelete(): void {
    if (mode.value !== 'edit' || detail.value === null || !canManage.value) return
    deleteConfirmInput.value = ''
    deleteConfirmError.value = ''
    deleteBlockError.value = ''
    deleteVersionConflict.value = false
    deleteVisible.value = true
  }

  function closeDelete(): void {
    deleteVisible.value = false
  }

  async function submitDelete(): Promise<void> {
    const d = detail.value
    if (d === null || !deleteConfirmMatched.value || deleteSubmitting.value) return
    deleteConfirmError.value = ''
    deleteBlockError.value = ''
    deleteSubmitting.value = true
    try {
      await resourcesApi.deleteResource(d.id, {
        confirm: deleteConfirmInput.value,
        version: version.value,
      })
      ElMessage.success(`资源「${d.name}」已删除`)
      deleteVisible.value = false
      // 删除成功离开（统一资源列表/详情页属 F003）
      void router.push({ name: 'clusters' })
    } catch (error) {
      if (!isApiError(error)) {
        deleteBlockError.value = apiErrorMessage(error)
        return
      }
      if (error.status === 401 || error.status === 403) return
      if (error.code === 'DELETE_CONFIRMATION_MISMATCH') {
        // 422：确认不匹配，不执行删除；保留对话框与输入
        deleteConfirmError.value = resourceConflictMessage('DELETE_CONFIRMATION_MISMATCH') ?? error.message
      } else if (error.code === 'RESOURCE_HAS_INTERFACES') {
        // 删除前置：仍有网卡未逐项删除，引导先删网卡（对话框保留）
        deleteBlockError.value = resourceConflictMessage('RESOURCE_HAS_INTERFACES') ?? error.message
      } else if (error.code === 'VERSION_CONFLICT') {
        // 保留对话框与确认输入；刷新版本后可重试
        deleteVersionConflict.value = true
        deleteBlockError.value =
          '该资源已被其他人修改（并发冲突）。可刷新版本后重试；确认输入已保留。'
      } else if (error.code === 'RESOURCE_NOT_FOUND') {
        deleteVisible.value = false
        notFound.value = true
      } else {
        deleteBlockError.value = apiErrorMessage(error)
      }
    } finally {
      deleteSubmitting.value = false
    }
  }

  return {
    // 状态
    mode,
    canManage,
    loading,
    loadError,
    notFound,
    name,
    resourceType,
    status,
    cards,
    detail,
    version,
    selectedClusterId,
    segmentOptions,
    segmentsLoading,
    segmentsError,
    // 网段/集群下拉数据源（F008 §5.1：服务端 q + 稳定 ID 提交）
    segmentSearchOptions,
    clusterSearchOptions,
    segmentFetcher,
    clusterFetcher,
    submitting,
    conflict,
    conflictResolved,
    refreshingVersion,
    formNotice,
    fieldErrors,
    sameNamePrompt,
    deleteVisible,
    deleteConfirmInput,
    deleteSubmitting,
    deleteConfirmError,
    deleteBlockError,
    deleteVersionConflict,
    deleteConfirmMatched,
    remainingInterfaceCount,
    // 管理 IP（F006）
    managementIpChoice,
    managementIpCandidates,
    managementIpValue,
    managementKeepLabel,
    currentManagementIpRemoved,
    clusterOptions: computed(() => clusterStore.clusters),
    clusterLoadError: computed(() => clusterStore.loadError),
    // 动作
    init,
    retryLoadClusters: () => void clusterStore.loadClusters(true),
    retryLoadSegments,
    selectCluster,
    addInterface,
    removeInterface,
    restoreInterface,
    setCardSegment,
    clearCardError,
    segmentSummary,
    submit,
    // IP 条目动作（F006）
    addCardIp,
    removeCardIp,
    restoreCardIp,
    clearCardIpError,
    // 管理 IP 动作（F006）
    setManagementIpValue,
    isCurrentManagementIp,
    dismissSameName,
    confirmSameNameGoEdit,
    refreshVersionKeepInput,
    openDelete,
    closeDelete,
    submitDelete,
  }
}
