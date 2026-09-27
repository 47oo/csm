// 资源表单状态机（架构 F002 §2.4）：新增/编辑共用，一次提交公共信息 + 全部网卡（整单原子 §4.5）。
// - 新增：集群可选（切换清除不再匹配的网段选择，§7.1）；资源类型必选；创建后只读；
// - 编辑：集群/类型只读回显；网卡卡片区分「删除 / 未修改 / 新增或修改」映射 interfaces[] 显式 op（§5.3）；
// - 同名：409 RESOURCE_NAME_EXISTS → existing_resource_id 弹确认进入编辑（§4.1.10、场景 2/45）；
// - 冲突：409 VERSION_CONFLICT 保留输入，刷新确认后重提（§4.5、场景 47）；
// - 删除：二次确认须输入资源名称（BQ-Z）；409 RESOURCE_HAS_INTERFACES 引导先删网卡（§6.2）；
// - 字段级错误：errors[]（含 interfaces[i].xxx）定位到具体字段与网卡卡片，保留已填内容（§7.3）。
// 401/403 由 client 全局拦截；前端权限仅控制入口/按钮可见，服务端为最终校验（§7.2）。
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as resourcesApi from '../api/resources'
import type {
  InterfaceSegmentSummary,
  ResourceFormDetail,
  ResourceStatus,
  ResourceType,
} from '../api/resources'
import { listNetworkSegments } from '../api/segments'
import { apiErrorMessage, isApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useClusterStore } from '../stores/clusters'
import {
  buildCreateInterfaceItems,
  buildInterfaceOps,
  canManageResources,
  emptyResourceFormErrors,
  findDuplicateInterfaceKeys,
  INTERFACE_NAME_DUPLICATE_MESSAGE,
  parseResourceFieldErrors,
  resourceConflictMessage,
  resourceDeleteConfirmMatches,
  validateInterfaceName,
  validateResourceName,
  type InterfaceCard,
  type InterfaceCardErrors,
  type ResourceFormErrors,
} from '../utils/resourceRules'

export type ResourceFormMode = 'create' | 'edit'

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

function parsePositiveInt(value: unknown): number | null {
  if (typeof value !== 'string' || !/^\d+$/.test(value)) return null
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : null
}

/** NetworkSegmentListItem → 表单网段摘要（仅取 InterfaceSegmentSummary 字段） */
function toSegmentSummary(s: {
  id: number
  name: string
  cidr: string
  purpose: string
  technology: string
  vlan: number | null
  gateway: string | null
}): InterfaceSegmentSummary {
  return {
    id: s.id,
    name: s.name,
    cidr: s.cidr,
    purpose: s.purpose,
    technology: s.technology,
    vlan: s.vlan,
    gateway: s.gateway,
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
  const segmentOptions = ref<InterfaceSegmentSummary[]>([])
  const segmentsLoading = ref(false)
  const segmentsError = ref('')
  /** 编辑加载时网卡已关联网段的摘要兜底（正常情况下均在选项内：RESTRICT 保证仍存） */
  const detailSegmentById = ref(new Map<number, InterfaceSegmentSummary>())
  let segmentsToken = 0

  // ---------- 提交与错误 ----------
  const submitting = ref(false)
  /** 409 VERSION_CONFLICT：保留输入，须刷新确认后重提（提交被阻止） */
  const conflict = ref(false)
  /** 已刷新版本（保留输入），待用户确认重提 */
  const conflictResolved = ref(false)
  const refreshingVersion = ref(false)
  /** 记录级提示（INTERFACE_NAME_TAKEN / NO_FIELDS 等） */
  const formNotice = ref('')
  /** 字段与网卡卡片级错误（前端校验 + 服务端 errors[] 合并呈现） */
  const fieldErrors = reactive<ResourceFormErrors>(emptyResourceFormErrors())

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
    const created: InterfaceCardErrors = { name: '', segment_id: '', other: '' }
    fieldErrors.cards[key] = created
    return created
  }

  function clearAllErrors(): void {
    fieldErrors.name = ''
    fieldErrors.resource_type = ''
    fieldErrors.status = ''
    fieldErrors.cluster_id = ''
    fieldErrors.cards = {}
    fieldErrors.general = []
  }

  function clearCardError(key: string, slot: 'name' | 'segment_id' | 'other'): void {
    const card = fieldErrors.cards[key]
    if (card !== undefined) card[slot] = ''
  }

  /** 选定网段的只读摘要（选项优先；编辑加载的兜底次之） */
  function segmentSummary(segmentId: number | null): InterfaceSegmentSummary | null {
    if (segmentId === null) return null
    for (const s of segmentOptions.value) {
      if (s.id === segmentId) return s
    }
    return detailSegmentById.value.get(segmentId) ?? null
  }

  /** 前端基础校验（§7.2）：必填、接口名非空、同表单接口名重复；其余由服务端最终保证 */
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
    }
    return ok
  }

  // ---------- 网段选项加载 ----------

  async function loadSegmentOptions(clusterId: number): Promise<void> {
    const token = ++segmentsToken
    segmentsLoading.value = true
    segmentsError.value = ''
    try {
      const items: InterfaceSegmentSummary[] = []
      let page = 1
      while (page <= SEGMENT_MAX_PAGES) {
        const data = await listNetworkSegments({ cluster_id: clusterId, page, page_size: 100, sort: 'name' })
        if (token !== segmentsToken) return
        for (const s of data.items) items.push(toSegmentSummary(s))
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
    }))
    detailSegmentById.value = new Map(
      d.interfaces.filter((i) => i.segment !== null).map((i) => [i.segment!.id, i.segment!]),
    )
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
      for (const card of cards.value) card.segmentId = null
      return
    }
    await loadSegmentOptions(id)
    for (const card of cards.value) {
      if (card.segmentId !== null && !segmentOptions.value.some((s) => s.id === card.segmentId)) {
        card.segmentId = null
      }
    }
  }

  // ---------- 网卡卡片 ----------

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
    })
  }

  /** 删除网卡：编辑模式的既有网卡标记「将删除」（可恢复，提交映射 op:'delete'）；
   * 新增网卡/新增模式直接移除卡片 */
  function removeInterface(key: string): void {
    if (!canManage.value) return
    const card = cards.value.find((c) => c.key === key)
    if (card === undefined) return
    if (mode.value === 'edit' && card.id !== null) {
      card.removed = true
    } else {
      cards.value = cards.value.filter((c) => c.key !== key)
    }
    delete fieldErrors.cards[key]
  }

  function restoreInterface(key: string): void {
    if (!canManage.value) return
    const card = cards.value.find((c) => c.key === key)
    if (card !== undefined) card.removed = false
  }

  function setCardSegment(card: InterfaceCard, segmentId: number | null): void {
    card.segmentId = segmentId
    clearCardError(card.key, 'segment_id')
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

  function handleSubmitError(error: unknown, cardKeys: string[]): void {
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
    if (
      (error.status === 400 && error.code === 'INVALID_REQUEST') ||
      (error.status === 422 && error.code === 'VALIDATION_ERROR')
    ) {
      // 字段级 errors[]：定位到表单字段与网卡卡片（含 interfaces[i].xxx 下标），保留输入
      const parsed = parseResourceFieldErrors(error.errors, cardKeys)
      fieldErrors.name = parsed.name
      fieldErrors.resource_type = parsed.resource_type
      fieldErrors.status = parsed.status
      fieldErrors.cluster_id = parsed.cluster_id
      for (const [key, cardError] of Object.entries(parsed.cards)) {
        fieldErrors.cards[key] = cardError
      }
      if (parsed.general.length > 0) {
        formNotice.value = parsed.general.join('；')
      } else if (
        parsed.name === '' &&
        parsed.resource_type === '' &&
        parsed.status === '' &&
        parsed.cluster_id === '' &&
        Object.keys(parsed.cards).length === 0
      ) {
        formNotice.value = error.message
      }
      return
    }
    formNotice.value = apiErrorMessage(error)
  }

  // ---------- 提交（一次提交公共信息 + 全部网卡，整单原子 §4.5） ----------

  async function submit(): Promise<void> {
    if (submitting.value || !canManage.value || conflict.value) return
    clearAllErrors()
    formNotice.value = ''
    if (!validateForm()) return

    submitting.value = true
    try {
      if (mode.value === 'create') {
        const { items } = buildCreateInterfaceItems(cards.value)
        const clusterId = selectedClusterId.value
        if (clusterId === null) return
        const created = await resourcesApi.createResource({
          cluster_id: clusterId,
          name: name.value,
          resource_type: resourceType.value as ResourceType,
          status: status.value,
          ...(items.length > 0 ? { interfaces: items } : {}),
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
        const { ops } = buildInterfaceOps(cards.value)
        const nameChanged = name.value.trim() !== d.name
        const statusChanged = status.value !== d.status
        if (!nameChanged && !statusChanged && ops.length === 0) {
          // 无可改字段（Contract §2.3 NO_FIELDS 语义；前端预检）
          formNotice.value = '没有可保存的修改：未修改任何公共信息或网卡'
          return
        }
        const updated = await resourcesApi.updateResource(d.id, {
          ...(nameChanged ? { name: name.value } : {}),
          ...(statusChanged ? { status: status.value } : {}),
          ...(ops.length > 0 ? { interfaces: ops } : {}),
          version: version.value,
        })
        // 展示保存结果：以响应重建表单基线（含自增 version 与网卡最新状态）
        applyDetail(updated)
        conflict.value = false
        conflictResolved.value = false
        ElMessage.success('资源已保存')
      }
    } catch (error) {
      const cardKeys =
        mode.value === 'create'
          ? buildCreateInterfaceItems(cards.value).cardKeys
          : buildInterfaceOps(cards.value).cardKeys
      handleSubmitError(error, cardKeys)
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
    dismissSameName,
    confirmSameNameGoEdit,
    refreshVersionKeepInput,
    openDelete,
    closeDelete,
    submitDelete,
  }
}
