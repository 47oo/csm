<script setup lang="ts">
// 网段列表页 /clusters/:clusterId/segments（架构 F005 §2.4，集群内列表）：
// - 列表：分页、q 搜索（名称/CIDR/用途/技术类型）、排序；
// - 新增/编辑对话框（仅 maintainer/admin 可见入口）：名称、规范化 CIDR、用途、
//   技术类型、VLAN、网关、自动分配范围（前端即时校验见 utils/segmentRules）；
// - 真实删除二次确认（BQ-Z）：须输入网段名称匹配后才可提交；删除前置
//   （保留地址/网关/已分配 IP/网卡引用）由服务端校验并按 409 提示；
// - 重叠风险提示（§4.6.5：仅提示、允许保存）；
// - 详情抽屉：保留地址增删、网关设置/显式清空、计数快照、「已分配 IP 及归属」占位；
// - 409 冲突保留输入不关窗；401/403 由全局拦截器处理。
// F008：页面搜索接入统一交互（useSearchInput：300ms 防抖 / 回车立即 / 竞态丢弃 /
// 清空回初始 / 无结果文案；保留「查询」按钮作为可访问性补充）。
// 前端权限仅隐藏入口，服务端为最终校验（架构 §8.2）。
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormItemRule } from 'element-plus'
import {
  createNetworkSegment,
  deleteNetworkSegment,
  getNetworkSegment,
  listNetworkSegments,
  updateNetworkSegment,
  type NetworkSegmentDetail,
  type NetworkSegmentListItem,
  type SegmentSort,
} from '../api/segments'
import { apiErrorMessage, isApiError, type ApiError } from '../api/client'
import { useSearchInput, SEARCH_DEBOUNCE_MS } from '../composables/useSearchInput'
import { useAuthStore } from '../stores/auth'
import { useSegmentPageScope } from '../composables/useSegmentPageScope'
import SegmentDetailDrawer from '../components/SegmentDetailDrawer.vue'
import {
  canManageSegments,
  overlapWarningText,
  segmentConflictMessage,
  segmentDeleteConfirmMatches,
  validateAutoAllocRange,
  validateGatewayInCidr,
  validateSegmentCidr,
  validateSegmentName,
  validateSegmentPurpose,
  validateSegmentTechnology,
  validateSegmentVlan,
} from '../utils/segmentRules'

const router = useRouter()
const auth = useAuthStore()
const { scopeClusterId, scopeCluster } = useSegmentPageScope()

// 写操作入口可见性（服务端为最终校验）：新增/编辑/删除/保留地址/网关仅 maintainer/admin
const canManage = computed(() => canManageSegments(auth.user?.role))

// ---------- 列表查询（Contract §2.1：cluster_id/page/page_size/q/sort；F008 统一搜索交互） ----------
const query = reactive({
  page: 1,
  page_size: 20,
  sort: 'name' as SegmentSort,
})

const items = ref<NetworkSegmentListItem[]>([])
const total = ref(0)
const loading = ref(false)
const listError = ref('')
/** 最近一次保存（新增/编辑）成功后的重叠风险提示；空 = 无 */
const overlapNotice = ref('')

// 搜索输入状态机（§8.3）：q 防抖 / 回车立即 / 请求序号竞态 / 清空回初始
const { q: searchQ, appliedQ, setQ, searchNow, resetQuiet, beginLoad, isCurrent, invalidate } =
  useSearchInput({
    debounceMs: SEARCH_DEBOUNCE_MS,
    onSearch: () => {
      query.page = 1
      void load()
    },
  })

const hasFilter = computed(() => appliedQ.value !== '')

async function load(): Promise<void> {
  const clusterId = scopeClusterId.value
  if (clusterId === null) {
    // 无选中集群：不发起查询（页面提示选择集群），不伪装成空列表；作废进行中的请求
    invalidate()
    items.value = []
    total.value = 0
    listError.value = ''
    loading.value = false
    return
  }
  const current = beginLoad()
  loading.value = true
  listError.value = ''
  try {
    const data = await listNetworkSegments({
      cluster_id: clusterId,
      page: query.page,
      page_size: query.page_size,
      q: appliedQ.value,
      sort: query.sort,
    })
    if (!isCurrent(current)) return // 旧请求不覆盖较新请求
    items.value = data.items
    total.value = data.total
  } catch (error) {
    if (!isCurrent(current)) return
    // 错误显式呈现，不伪装成空结果
    items.value = []
    total.value = 0
    listError.value = apiErrorMessage(error)
  } finally {
    if (isCurrent(current)) loading.value = false
  }
}

// 切换集群刷新列表（架构 §2.4）：页码重置、清除过期提示（搜索词保留，仍限新集群）
watch(scopeClusterId, () => {
  query.page = 1
  overlapNotice.value = ''
  void load()
})

/** 排序切换：回到第 1 页重新加载 */
function handleSortChange(): void {
  query.page = 1
  void load()
}

function handleResetFilters(): void {
  resetQuiet()
  query.sort = 'name'
  query.page = 1
  void load()
}

function handlePageChange(page: number): void {
  query.page = page
  void load()
}

function handlePageSizeChange(size: number): void {
  query.page_size = size
  query.page = 1
  void load()
}

/** 401/403 已由全局处理器提示/跳转，页面不再重复提示 */
function isGloballyHandled(error: unknown): boolean {
  return isApiError(error) && (error.status === 401 || error.status === 403)
}

function handleActionError(error: unknown): void {
  if (isApiError(error) && error.status === 404) {
    ElMessage.warning('该网段已不存在，列表已刷新')
    void load()
    return
  }
  if (isGloballyHandled(error)) return
  ElMessage.error(apiErrorMessage(error))
}

function rangeText(row: NetworkSegmentListItem): string {
  return row.auto_alloc_enabled ? `${row.auto_alloc_start} – ${row.auto_alloc_end}` : '未启用'
}

// ---------- 表单状态/校验（与 Contract §0/§2.2/§2.4 一致；服务端为最终保证） ----------

interface SegmentFormState {
  name: string
  cidr: string
  purpose: string
  technology: string
  vlan: number | undefined
  gateway: string
  auto_alloc_start: string
  auto_alloc_end: string
}

/** 与服务端字段名一致的表单键（422 errors[].field 直接映射到表单项） */
const SEGMENT_FIELD_KEYS = [
  'name',
  'cidr',
  'purpose',
  'technology',
  'vlan',
  'gateway',
  'auto_alloc_start',
  'auto_alloc_end',
] as const

function emptyServerErrors(): Record<string, string> {
  return { name: '', cidr: '', purpose: '', technology: '', vlan: '', gateway: '', auto_alloc_start: '', auto_alloc_end: '' }
}

function clearServerErrors(target: Record<string, string>): void {
  for (const key of Object.keys(target)) target[key] = ''
}

function applyValidationErrors(error: ApiError, target: Record<string, string>): void {
  for (const key of SEGMENT_FIELD_KEYS) target[key] = error.fieldError(key) ?? ''
}

function resetSegmentForm(form: SegmentFormState): void {
  form.name = ''
  form.cidr = ''
  form.purpose = ''
  form.technology = ''
  form.vlan = undefined
  form.gateway = ''
  form.auto_alloc_start = ''
  form.auto_alloc_end = ''
}

/** 表单值 → 请求体字段（空串转 null；vlan undefined 转 null） */
function segmentPayload(form: SegmentFormState) {
  return {
    name: form.name,
    cidr: form.cidr,
    purpose: form.purpose,
    technology: form.technology,
    vlan: form.vlan ?? null,
    gateway: form.gateway === '' ? null : form.gateway,
    auto_alloc_start: form.auto_alloc_start === '' ? null : form.auto_alloc_start,
    auto_alloc_end: form.auto_alloc_end === '' ? null : form.auto_alloc_end,
  }
}

/** 校验规则（跨字段校验读取当前表单值：网关/自动范围须落在 CIDR 内） */
function segmentFormRules(form: SegmentFormState): Record<string, FormItemRule[]> {
  const requiredText = (validate: (value: string) => string | null): FormItemRule => ({
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validate(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  })
  const autoRangeRule: FormItemRule = {
    validator: (_rule, _value: string, callback) => {
      callback(
        validateAutoAllocRange(form.auto_alloc_start, form.auto_alloc_end, form.cidr) ?? undefined,
      )
    },
    trigger: 'blur',
  }
  return {
    name: [requiredText(validateSegmentName)],
    cidr: [requiredText(validateSegmentCidr)],
    purpose: [requiredText(validateSegmentPurpose)],
    technology: [requiredText(validateSegmentTechnology)],
    vlan: [
      {
        validator: (_rule, value: number | undefined, callback) => {
          callback(validateSegmentVlan(value) ?? undefined)
        },
        trigger: 'blur',
      },
    ],
    gateway: [
      {
        validator: (_rule, value: string, callback) => {
          callback(validateGatewayInCidr(value ?? '', form.cidr) ?? undefined)
        },
        trigger: 'blur',
      },
    ],
    auto_alloc_start: [autoRangeRule],
    auto_alloc_end: [autoRangeRule],
  }
}

/** 保存成功后的重叠风险提示（§4.6.5：仅提示、允许保存） */
function noticeOverlap(detail: NetworkSegmentDetail): void {
  const text = overlapWarningText(detail)
  overlapNotice.value = text === null ? '' : `「${detail.name}」${text}`
}

// ---------- 新增（Contract §2.2：maintainer/admin） ----------
const createVisible = ref(false)
const createSubmitting = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive<SegmentFormState>({
  name: '',
  cidr: '',
  purpose: '',
  technology: '',
  vlan: undefined,
  gateway: '',
  auto_alloc_start: '',
  auto_alloc_end: '',
})
const createRules = segmentFormRules(createForm)
const createServerErrors = reactive<Record<string, string>>(emptyServerErrors())

function openCreate(): void {
  resetSegmentForm(createForm)
  clearServerErrors(createServerErrors)
  createVisible.value = true
}

/** 新增/编辑共用的提交错误呈现：409 保留输入不关窗、422 字段级映射 */
function handleFormError(error: unknown, serverErrors: Record<string, string>): void {
  if (isApiError(error)) {
    if (error.code === 'SEGMENT_NAME_TAKEN') {
      serverErrors.name = segmentConflictMessage('SEGMENT_NAME_TAKEN') ?? ''
    } else if (error.code === 'SEGMENT_CIDR_TAKEN') {
      serverErrors.cidr = segmentConflictMessage('SEGMENT_CIDR_TAKEN') ?? ''
    } else if (error.code === 'CIDR_IMMUTABLE') {
      ElMessage.error(segmentConflictMessage('CIDR_IMMUTABLE') ?? apiErrorMessage(error))
    } else if (error.code === 'CLUSTER_NOT_FOUND') {
      ElMessage.warning('所选集群已不存在，请重新选择集群')
    } else if (error.status === 422 && error.code === 'VALIDATION_ERROR') {
      applyValidationErrors(error, serverErrors)
    } else if (!isGloballyHandled(error)) {
      ElMessage.error(apiErrorMessage(error))
    }
  } else {
    ElMessage.error(apiErrorMessage(error))
  }
}

async function handleCreate(): Promise<void> {
  clearServerErrors(createServerErrors)
  const valid = await createFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  const clusterId = scopeClusterId.value
  if (clusterId === null) {
    // 作用域集群被清除（如页头清空选择）：不提交，提示后由用户重新选择
    ElMessage.warning('尚未选择集群，无法创建网段')
    return
  }
  createSubmitting.value = true
  try {
    const detail = await createNetworkSegment({ cluster_id: clusterId, ...segmentPayload(createForm) })
    createVisible.value = false
    ElMessage.success('网段已创建')
    noticeOverlap(detail)
    query.page = 1
    void load()
  } catch (error) {
    handleFormError(error, createServerErrors)
  } finally {
    createSubmitting.value = false
  }
}

// ---------- 编辑（Contract §2.4：乐观锁；CIDR 条件可变） ----------
const editVisible = ref(false)
const editSubmitting = ref(false)
const editLoading = ref(false)
const editFormRef = ref<FormInstance>()
const editConflict = ref('')
const editForm = reactive<SegmentFormState & { id: number; version: number; cluster_code: string; cluster_name: string }>({
  id: 0,
  version: 0,
  cluster_code: '',
  cluster_name: '',
  name: '',
  cidr: '',
  purpose: '',
  technology: '',
  vlan: undefined,
  gateway: '',
  auto_alloc_start: '',
  auto_alloc_end: '',
})
const editRules = segmentFormRules(editForm)
const editServerErrors = reactive<Record<string, string>>(emptyServerErrors())

async function openEdit(row: NetworkSegmentListItem): Promise<void> {
  editConflict.value = ''
  clearServerErrors(editServerErrors)
  editVisible.value = true
  editLoading.value = true
  try {
    // 列表项不含 version/保留地址，编辑前取详情获得乐观锁版本
    const detail = await getNetworkSegment(row.id)
    editForm.id = detail.id
    editForm.version = detail.version
    editForm.cluster_code = detail.cluster_code
    editForm.cluster_name = detail.cluster_name
    editForm.name = detail.name
    editForm.cidr = detail.cidr
    editForm.purpose = detail.purpose
    editForm.technology = detail.technology
    editForm.vlan = detail.vlan ?? undefined
    editForm.gateway = detail.gateway ?? ''
    editForm.auto_alloc_start = detail.auto_alloc_start ?? ''
    editForm.auto_alloc_end = detail.auto_alloc_end ?? ''
  } catch (error) {
    editVisible.value = false
    handleActionError(error)
  } finally {
    editLoading.value = false
  }
}

async function handleEdit(): Promise<void> {
  clearServerErrors(editServerErrors)
  editConflict.value = ''
  const valid = await editFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  editSubmitting.value = true
  try {
    const detail = await updateNetworkSegment(editForm.id, {
      ...segmentPayload(editForm),
      version: editForm.version,
    })
    editVisible.value = false
    ElMessage.success('网段已更新')
    noticeOverlap(detail)
    void load()
  } catch (error) {
    if (isApiError(error) && error.code === 'VERSION_CONFLICT') {
      // 乐观锁冲突：保留输入并提示；关闭重开可获取最新版本
      editConflict.value = '该网段已被其他人修改，当前编辑内容未提交。请关闭后重新打开编辑。'
    } else {
      handleFormError(error, editServerErrors)
    }
  } finally {
    editSubmitting.value = false
  }
}

// ---------- 真实删除（Contract §2.5：confirm + version + 删除前置；BQ-Z） ----------
const deleteVisible = ref(false)
const deleteLoading = ref(false)
const deleteSubmitting = ref(false)
const deleteTarget = ref<NetworkSegmentDetail | null>(null)
const deleteConfirmInput = ref('')
const deleteServerError = ref('')
const deleteConflict = ref('')

/** 二次确认输入与目标网段名称匹配（去首尾空格、区分大小写）才允许提交（BQ-Z） */
const deleteConfirmMatched = computed(
  () => deleteTarget.value !== null && segmentDeleteConfirmMatches(deleteConfirmInput.value, deleteTarget.value),
)

async function openDelete(row: NetworkSegmentListItem): Promise<void> {
  deleteServerError.value = ''
  deleteConflict.value = ''
  deleteConfirmInput.value = ''
  deleteTarget.value = null
  deleteVisible.value = true
  deleteLoading.value = true
  try {
    // 删除前取详情：乐观锁版本 + 最新名称 + 删除前置状态（保留地址/网关/已分配数）
    deleteTarget.value = await getNetworkSegment(row.id)
  } catch (error) {
    deleteVisible.value = false
    handleActionError(error)
  } finally {
    deleteLoading.value = false
  }
}

async function handleDelete(): Promise<void> {
  const target = deleteTarget.value
  if (!target || !deleteConfirmMatched.value) return
  deleteServerError.value = ''
  deleteConflict.value = ''
  deleteSubmitting.value = true
  try {
    await deleteNetworkSegment(target.id, { confirm: deleteConfirmInput.value, version: target.version })
    ElMessage.success(`网段「${target.name}」已删除`)
    deleteVisible.value = false
    void load()
  } catch (error) {
    if (isApiError(error)) {
      if (error.code === 'DELETE_CONFIRMATION_MISMATCH') {
        // 422：确认不匹配，不执行删除；保留对话框与输入
        deleteServerError.value = segmentConflictMessage('DELETE_CONFIRMATION_MISMATCH') ?? ''
      } else if (error.code === 'VERSION_CONFLICT') {
        deleteVisible.value = false
        ElMessage.error('该网段已被其他人修改，请重试')
        void load()
      } else if (error.status === 409) {
        // 删除前置冲突（SEGMENT_HAS_RESERVED_ADDRESSES/SEGMENT_GATEWAY_NOT_CLEARED/
        // SEGMENT_HAS_INTERFACES/SEGMENT_HAS_ALLOCATIONS）：保留对话框提示处理路径
        deleteConflict.value = segmentConflictMessage(error.code) ?? apiErrorMessage(error)
      } else if (!isGloballyHandled(error)) {
        ElMessage.error(apiErrorMessage(error))
      }
    } else {
      ElMessage.error(apiErrorMessage(error))
    }
  } finally {
    deleteSubmitting.value = false
  }
}

// ---------- 详情抽屉（保留地址增删/网关/计数/占位） ----------
const detailVisible = ref(false)
const detailSegmentId = ref<number | null>(null)

function openDetail(row: NetworkSegmentListItem): void {
  detailSegmentId.value = row.id
  detailVisible.value = true
}

/** 抽屉内保留地址/网关变化后刷新列表计数 */
function handleDetailChanged(): void {
  void load()
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="segments-page">
    <!-- 无选中集群：提示选择（集群作用域决定列表，不改变权限） -->
    <el-card v-if="scopeClusterId === null" shadow="never">
      <el-empty description="尚未选择集群：网段按集群登记与展示，请先在页头选择集群作用域">
        <el-button type="primary" @click="router.push({ name: 'clusters' })">前往集群列表</el-button>
      </el-empty>
    </el-card>

    <template v-else>
      <!-- 集群作用域标题 -->
      <div class="segments-scope">
        <h2 class="segments-title">网段</h2>
        <span class="segments-cluster">
          集群作用域：
          <strong v-if="scopeCluster">{{ scopeCluster.code }} {{ scopeCluster.name }}</strong>
          <span v-else>#{{ scopeClusterId }}</span>
          <span class="segments-cluster-hint">（可在页头切换集群，切换后列表刷新）</span>
        </span>
      </div>

      <!-- 搜索/排序区 -->
      <el-card class="segments-filter" shadow="never">
        <el-form inline @submit.prevent="searchNow">
          <el-form-item label="搜索">
            <el-input
              :model-value="searchQ"
              placeholder="名称 / CIDR / 用途 / 技术类型模糊匹配"
              clearable
              style="width: 260px"
              data-test-id="segment-search-input"
              @update:model-value="setQ"
              @keyup.enter="searchNow"
              @clear="searchNow"
            />
          </el-form-item>
          <el-form-item label="排序">
            <el-select v-model="query.sort" style="width: 150px" @change="handleSortChange">
              <el-option value="name" label="名称 升序" />
              <el-option value="-name" label="名称 降序" />
              <el-option value="cidr" label="CIDR 升序" />
              <el-option value="-cidr" label="CIDR 降序" />
              <el-option value="created_at" label="创建时间 升序" />
              <el-option value="-created_at" label="创建时间 降序" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <!-- 可访问性补充：显式查询按钮（搜索本身已防抖自动更新，§8.3） -->
            <el-button type="primary" @click="searchNow">查询</el-button>
            <el-button @click="handleResetFilters">重置</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 列表区 -->
      <el-card shadow="never">
        <div class="segments-toolbar">
          <h3 class="segments-list-title">网段列表</h3>
          <!-- 新增仅 maintainer/admin（服务端校验为最终保证） -->
          <el-button v-if="canManage" type="primary" @click="openCreate">新增网段</el-button>
        </div>

        <!-- 最近一次保存的重叠风险提示（§4.6.5：仅提示、允许保存） -->
        <el-alert
          v-if="overlapNotice"
          type="warning"
          :closable="true"
          show-icon
          :title="overlapNotice"
          class="segments-overlap-notice"
          @close="overlapNotice = ''"
        />

        <el-alert
          v-if="listError"
          type="error"
          :closable="false"
          show-icon
          :title="listError"
          class="segments-error"
        >
          <el-button size="small" @click="load">重试</el-button>
        </el-alert>

        <el-table v-else v-loading="loading" :data="items" class="segments-table">
          <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="segment-name">
                {{ row.name }}
                <el-tooltip
                  v-if="row.has_overlap"
                  content="与同集群其它仍存网段重叠（仅提示风险，允许保存）"
                  placement="top"
                >
                  <el-tag type="warning" size="small" class="segment-overlap-tag">重叠</el-tag>
                </el-tooltip>
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="cidr" label="CIDR" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <code class="segment-code">{{ row.cidr }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="purpose" label="用途" min-width="130" show-overflow-tooltip />
          <el-table-column prop="technology" label="技术类型" min-width="110" show-overflow-tooltip />
          <el-table-column label="VLAN" width="80">
            <template #default="{ row }">{{ row.vlan ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="网关" width="130">
            <template #default="{ row }">
              <code v-if="row.gateway" class="segment-code">{{ row.gateway }}</code>
              <span v-else class="segment-muted">未设置</span>
            </template>
          </el-table-column>
          <el-table-column label="自动分配范围" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <code v-if="row.auto_alloc_enabled" class="segment-code">{{ rangeText(row) }}</code>
              <span v-else class="segment-muted">未启用</span>
            </template>
          </el-table-column>
          <el-table-column prop="reserved_address_count" label="保留地址数" width="100" align="right" />
          <el-table-column prop="allocated_count" label="已分配数" width="95" align="right" />
          <el-table-column prop="auto_assignable_count" label="可自动分配数" width="115" align="right" />
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <!-- 详情：任意已登录；编辑/删除仅 maintainer/admin -->
              <el-button link type="primary" @click="openDetail(row)">详情</el-button>
              <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="canManage" link type="danger" @click="openDelete(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :description="hasFilter ? '未找到匹配的网段' : '该集群暂无网段'" />
          </template>
        </el-table>

        <div class="segments-pagination">
          <el-pagination
            :current-page="query.page"
            :page-size="query.page_size"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </el-card>
    </template>

    <!-- 新增网段 -->
    <el-dialog v-model="createVisible" title="新增网段" width="560px" :close-on-click-modal="false">
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-position="top"
        @submit.prevent="handleCreate"
      >
        <el-form-item label="网段名称" prop="name" :error="createServerErrors.name || undefined">
          <el-input
            v-model="createForm.name"
            placeholder="同集群内唯一（去首尾空格、区分大小写）"
            @input="createServerErrors.name = ''"
          />
        </el-form-item>
        <el-form-item label="CIDR（IPv4）" prop="cidr" :error="createServerErrors.cidr || undefined">
          <el-input
            v-model="createForm.cidr"
            placeholder="如 192.168.1.0/24；带主机位的输入将按网络地址规范化"
            @input="createServerErrors.cidr = ''"
          />
        </el-form-item>
        <el-form-item label="用途" prop="purpose" :error="createServerErrors.purpose || undefined">
          <el-input
            v-model="createForm.purpose"
            placeholder="如：管理网络 / 计算网络"
            @input="createServerErrors.purpose = ''"
          />
        </el-form-item>
        <el-form-item label="技术类型" prop="technology" :error="createServerErrors.technology || undefined">
          <el-input
            v-model="createForm.technology"
            placeholder="如：Ethernet / InfiniBand"
            @input="createServerErrors.technology = ''"
          />
        </el-form-item>
        <el-form-item label="VLAN（可留空）" prop="vlan" :error="createServerErrors.vlan || undefined">
          <el-input-number
            v-model="createForm.vlan"
            :min="1"
            :max="4094"
            placeholder="1–4094"
            class="segment-vlan-input"
          />
        </el-form-item>
        <el-form-item label="网关（可留空）" prop="gateway" :error="createServerErrors.gateway || undefined">
          <el-input
            v-model="createForm.gateway"
            placeholder="单个 IPv4，须落在 CIDR 内；留空表示未设置"
            @input="createServerErrors.gateway = ''"
          />
        </el-form-item>
        <div class="segment-range-row">
          <el-form-item
            label="自动分配起始（可留空）"
            prop="auto_alloc_start"
            :error="createServerErrors.auto_alloc_start || undefined"
            class="segment-range-item"
          >
            <el-input
              v-model="createForm.auto_alloc_start"
              placeholder="如 192.168.1.20"
              @input="createServerErrors.auto_alloc_start = ''"
            />
          </el-form-item>
          <span class="segment-range-sep">–</span>
          <el-form-item
            label="自动分配结束（可留空）"
            prop="auto_alloc_end"
            :error="createServerErrors.auto_alloc_end || undefined"
            class="segment-range-item"
          >
            <el-input
              v-model="createForm.auto_alloc_end"
              placeholder="如 192.168.1.30"
              @input="createServerErrors.auto_alloc_end = ''"
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSubmitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑网段（乐观锁；CIDR 条件可变） -->
    <el-dialog v-model="editVisible" title="编辑网段" width="560px" :close-on-click-modal="false">
      <el-form
        ref="editFormRef"
        v-loading="editLoading"
        :model="editForm"
        :rules="editRules"
        label-position="top"
        @submit.prevent="handleEdit"
      >
        <el-form-item label="所属集群（不可修改）">
          <el-input :model-value="`${editForm.cluster_code} ${editForm.cluster_name}`" disabled />
        </el-form-item>
        <el-form-item label="网段名称" prop="name" :error="editServerErrors.name || undefined">
          <el-input v-model="editForm.name" @input="editServerErrors.name = ''" />
        </el-form-item>
        <el-form-item label="CIDR（IPv4）" prop="cidr" :error="editServerErrors.cidr || undefined">
          <el-input
            v-model="editForm.cidr"
            placeholder="修改 CIDR 须容纳既有网关/自动范围/保留地址"
            @input="editServerErrors.cidr = ''"
          />
        </el-form-item>
        <el-form-item label="用途" prop="purpose" :error="editServerErrors.purpose || undefined">
          <el-input v-model="editForm.purpose" @input="editServerErrors.purpose = ''" />
        </el-form-item>
        <el-form-item label="技术类型" prop="technology" :error="editServerErrors.technology || undefined">
          <el-input v-model="editForm.technology" @input="editServerErrors.technology = ''" />
        </el-form-item>
        <el-form-item label="VLAN（可留空）" prop="vlan" :error="editServerErrors.vlan || undefined">
          <el-input-number
            v-model="editForm.vlan"
            :min="1"
            :max="4094"
            placeholder="1–4094"
            class="segment-vlan-input"
          />
        </el-form-item>
        <el-form-item label="网关（可留空）" prop="gateway" :error="editServerErrors.gateway || undefined">
          <el-input
            v-model="editForm.gateway"
            placeholder="单个 IPv4，须落在 CIDR 内；留空表示清空"
            @input="editServerErrors.gateway = ''"
          />
        </el-form-item>
        <div class="segment-range-row">
          <el-form-item
            label="自动分配起始（可留空）"
            prop="auto_alloc_start"
            :error="editServerErrors.auto_alloc_start || undefined"
            class="segment-range-item"
          >
            <el-input v-model="editForm.auto_alloc_start" @input="editServerErrors.auto_alloc_start = ''" />
          </el-form-item>
          <span class="segment-range-sep">–</span>
          <el-form-item
            label="自动分配结束（可留空）"
            prop="auto_alloc_end"
            :error="editServerErrors.auto_alloc_end || undefined"
            class="segment-range-item"
          >
            <el-input v-model="editForm.auto_alloc_end" @input="editServerErrors.auto_alloc_end = ''" />
          </el-form-item>
        </div>
        <el-alert
          v-if="editConflict"
          type="warning"
          :closable="false"
          show-icon
          :title="editConflict"
        />
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">关闭</el-button>
        <el-button type="primary" :loading="editSubmitting" :disabled="editLoading" @click="handleEdit">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 真实删除：二次确认须输入网段名称（BQ-Z）+ 删除前置提示 -->
    <el-dialog v-model="deleteVisible" title="删除网段" width="540px" :close-on-click-modal="false">
      <div v-loading="deleteLoading">
        <template v-if="deleteTarget">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="真实删除不可恢复：删除前须先逐条删除保留地址、显式清空网关，并处理全部已分配 IP 与网卡引用；审计与资源历史保留"
            class="delete-warning"
          />
          <p class="delete-target">
            将删除网段：<strong>{{ deleteTarget.name }}</strong>（<code class="segment-code">{{ deleteTarget.cidr }}</code
            >，所属集群 {{ deleteTarget.cluster_code }} {{ deleteTarget.cluster_name }}）
          </p>
          <el-descriptions :column="1" border size="small" class="delete-prereq">
            <el-descriptions-item label="保留地址">
              {{ deleteTarget.reserved_address_count }} 条（删除前须逐条删除）
            </el-descriptions-item>
            <el-descriptions-item label="网关">
              <template v-if="deleteTarget.gateway">
                <code class="segment-code">{{ deleteTarget.gateway }}</code>（删除前须显式清空）
              </template>
              <span v-else class="segment-muted">未设置</span>
            </el-descriptions-item>
            <el-descriptions-item label="已分配 IP">
              {{ deleteTarget.allocated_count }} 条（删除前须逐项删除）
            </el-descriptions-item>
          </el-descriptions>
          <el-form @submit.prevent="handleDelete">
            <el-form-item
              label="请输入网段名称以确认删除"
              :error="deleteServerError || undefined"
            >
              <el-input
                v-model="deleteConfirmInput"
                :placeholder="`输入「${deleteTarget.name}」`"
                @input="deleteServerError = ''"
              />
            </el-form-item>
          </el-form>
          <el-alert
            v-if="deleteConflict"
            type="error"
            :closable="false"
            show-icon
            :title="deleteConflict"
          />
        </template>
      </div>
      <template #footer>
        <el-button @click="deleteVisible = false">取消</el-button>
        <el-button
          type="danger"
          :loading="deleteSubmitting"
          :disabled="!deleteConfirmMatched"
          @click="handleDelete"
        >
          删除
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情抽屉：保留地址增删、网关设置/显式清空、计数、已分配 IP 占位 -->
    <SegmentDetailDrawer
      v-model="detailVisible"
      :segment-id="detailSegmentId"
      @changed="handleDetailChanged"
    />
  </div>
</template>

<style scoped>
.segments-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.segments-scope {
  display: flex;
  align-items: baseline;
  gap: 16px;
}
.segments-title {
  margin: 0;
  font-size: 20px;
}
.segments-cluster {
  color: #606266;
}
.segments-cluster-hint {
  color: #909399;
  font-size: 12px;
}
.segments-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.segments-list-title {
  margin: 0;
  font-size: 16px;
}
.segments-overlap-notice {
  margin-bottom: 12px;
}
.segments-error {
  margin-bottom: 12px;
}
.segments-table {
  width: 100%;
}
.segments-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.segment-code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
.segment-muted {
  color: #909399;
}
.segment-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.segment-overlap-tag {
  flex: none;
}
.segment-vlan-input {
  width: 160px;
}
.segment-range-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.segment-range-item {
  flex: 1;
}
.segment-range-sep {
  line-height: 32px;
  color: #909399;
}
.delete-warning {
  margin-bottom: 12px;
}
.delete-target {
  margin: 0 0 12px;
}
.delete-prereq {
  margin-bottom: 12px;
}
</style>
