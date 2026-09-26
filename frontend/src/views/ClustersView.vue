<script setup lang="ts">
// 集群列表页 /clusters（架构 F001 §2.3）：分页/q 搜索/排序；新增与编辑仅 admin、
// 真实删除 maintainer/admin（含 BQ-Z 二次确认：须输入集群名称或 code 匹配后才可提交）。
// 前端权限仅用于隐藏入口，最终权限由服务端校验（架构 §2.3）。
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormItemRule } from 'element-plus'
import {
  createCluster,
  deleteCluster,
  getCluster,
  listClusters,
  updateCluster,
  type ClusterDetail,
  type ClusterListItem,
  type ClusterSort,
} from '../api/clusters'
import { apiErrorMessage, isApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useClusterStore } from '../stores/clusters'
import {
  CLUSTER_NAME_RULE_MESSAGE,
  clusterDeleteConfirmMatches,
  validateClusterCode,
  validateClusterName,
  validateClusterPurpose,
} from '../utils/validation'

const auth = useAuthStore()
const clusterStore = useClusterStore()

// 操作入口可见性（服务端为最终校验）：新增/编辑仅 admin；删除 maintainer/admin
const canCreate = computed(() => auth.isAdmin)
const canDelete = computed(() => auth.user?.role === 'maintainer' || auth.user?.role === 'admin')

// ---------- 列表查询（Contract §2.1：page/page_size/q/sort） ----------
const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  sort: 'code' as ClusterSort,
})

const items = ref<ClusterListItem[]>([])
const total = ref(0)
const loading = ref(false)
const listError = ref('')

const hasFilter = computed(() => query.q.trim() !== '')

async function load(): Promise<void> {
  loading.value = true
  listError.value = ''
  try {
    const data = await listClusters({
      page: query.page,
      page_size: query.page_size,
      q: query.q,
      sort: query.sort,
    })
    items.value = data.items
    total.value = data.total
  } catch (error) {
    // 错误显式呈现，不伪装成空列表
    items.value = []
    total.value = 0
    listError.value = apiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  query.page = 1
  void load()
}

function handleResetFilters(): void {
  query.q = ''
  query.sort = 'code'
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

/** 集群数据变更后同步刷新选择器缓存（并联动校验当前选择仍存在） */
function refreshClusterCache(): void {
  void clusterStore.loadClusters(true)
}

/** 401/403 已由全局处理器提示/跳转，页面不再重复提示 */
function isGloballyHandled(error: unknown): boolean {
  return isApiError(error) && (error.status === 401 || error.status === 403)
}

function handleActionError(error: unknown): void {
  if (isApiError(error) && error.status === 404) {
    ElMessage.warning('该集群已不存在，列表已刷新')
    void load()
    refreshClusterCache()
    return
  }
  if (isGloballyHandled(error)) return
  ElMessage.error(apiErrorMessage(error))
}

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number): string => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}

// ---------- 表单校验规则（与 Contract §0 一致；服务端为最终保证） ----------
const clusterCodeRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validateClusterCode(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  },
]
const clusterNameRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validateClusterName(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  },
]
const clusterPurposeRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validateClusterPurpose(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  },
]

// ---------- 新增集群（Contract §2.2：仅 admin） ----------
const createVisible = ref(false)
const createSubmitting = ref(false)
const createFormRef = ref<FormInstance>()
const createServerErrors = reactive({ code: '', name: '', purpose: '' })
const createForm = reactive({ code: '', name: '', purpose: '' })

function openCreate(): void {
  createForm.code = ''
  createForm.name = ''
  createForm.purpose = ''
  createServerErrors.code = ''
  createServerErrors.name = ''
  createServerErrors.purpose = ''
  createVisible.value = true
}

async function handleCreate(): Promise<void> {
  createServerErrors.code = ''
  createServerErrors.name = ''
  createServerErrors.purpose = ''
  const valid = await createFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  createSubmitting.value = true
  try {
    await createCluster({ code: createForm.code, name: createForm.name, purpose: createForm.purpose })
    ElMessage.success('集群已创建')
    createVisible.value = false
    void load()
    refreshClusterCache()
  } catch (error) {
    if (isApiError(error)) {
      // 409：保留输入并提示（不关闭、不清空表单）
      if (error.code === 'CLUSTER_CODE_TAKEN') {
        createServerErrors.code = '该编号已被使用（包括已真实删除的集群，编号不可复用）'
      } else if (error.code === 'CLUSTER_NAME_TAKEN') {
        createServerErrors.name = '该名称与仍存集群重复（区分大小写）'
      } else if (error.status === 422) {
        // 422 VALIDATION_ERROR：字段级错误
        createServerErrors.code = error.fieldError('code') ?? ''
        createServerErrors.name = error.fieldError('name') ?? ''
        createServerErrors.purpose = error.fieldError('purpose') ?? ''
      } else if (!isGloballyHandled(error)) {
        ElMessage.error(apiErrorMessage(error))
      }
    } else {
      ElMessage.error(apiErrorMessage(error))
    }
  } finally {
    createSubmitting.value = false
  }
}

// ---------- 编辑（Contract §2.4：仅名称/用途可改，code 不可改；仅 admin） ----------
const editVisible = ref(false)
const editSubmitting = ref(false)
const editLoading = ref(false)
const editFormRef = ref<FormInstance>()
const editConflict = ref('')
const editServerErrors = reactive({ name: '', purpose: '' })
const editForm = reactive({ id: 0, code: '', name: '', purpose: '', version: 0 })

async function openEdit(row: ClusterListItem): Promise<void> {
  editConflict.value = ''
  editServerErrors.name = ''
  editServerErrors.purpose = ''
  editVisible.value = true
  editLoading.value = true
  try {
    // 列表项不含 version，编辑前取详情获得乐观锁版本
    const detail = await getCluster(row.id)
    editForm.id = detail.id
    editForm.code = detail.code
    editForm.name = detail.name
    editForm.purpose = detail.purpose
    editForm.version = detail.version
  } catch (error) {
    editVisible.value = false
    handleActionError(error)
  } finally {
    editLoading.value = false
  }
}

async function handleEdit(): Promise<void> {
  editConflict.value = ''
  editServerErrors.name = ''
  editServerErrors.purpose = ''
  const valid = await editFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  editSubmitting.value = true
  try {
    await updateCluster(editForm.id, {
      name: editForm.name,
      purpose: editForm.purpose,
      version: editForm.version,
    })
    ElMessage.success('集群已更新')
    editVisible.value = false
    void load()
    refreshClusterCache()
  } catch (error) {
    if (isApiError(error)) {
      if (error.code === 'VERSION_CONFLICT') {
        // 乐观锁冲突：保留输入并提示；关闭重开可获取最新版本
        editConflict.value = '该集群已被其他人修改，当前编辑内容未提交。请关闭后重新打开编辑。'
      } else if (error.code === 'CLUSTER_NAME_TAKEN') {
        editServerErrors.name = '该名称与仍存集群重复（区分大小写）'
      } else if (error.status === 422) {
        editServerErrors.name = error.fieldError('name') ?? ''
        editServerErrors.purpose = error.fieldError('purpose') ?? ''
      } else if (!isGloballyHandled(error)) {
        ElMessage.error(apiErrorMessage(error))
      }
    } else {
      ElMessage.error(apiErrorMessage(error))
    }
  } finally {
    editSubmitting.value = false
  }
}

// ---------- 真实删除（Contract §2.5：confirm + version；BQ-Z 二次确认） ----------
const deleteVisible = ref(false)
const deleteLoading = ref(false)
const deleteSubmitting = ref(false)
const deleteTarget = ref<ClusterDetail | null>(null)
const deleteConfirmInput = ref('')
const deleteServerConfirmError = ref('')
const deleteAssocConflict = ref('')

/** 二次确认输入与目标集群名称/code 匹配才允许提交（BQ-Z） */
const deleteConfirmMatched = computed(() =>
  deleteTarget.value !== null && clusterDeleteConfirmMatches(deleteConfirmInput.value, deleteTarget.value),
)

async function openDelete(row: ClusterListItem): Promise<void> {
  deleteServerConfirmError.value = ''
  deleteAssocConflict.value = ''
  deleteConfirmInput.value = ''
  deleteTarget.value = null
  deleteVisible.value = true
  deleteLoading.value = true
  try {
    // 列表项不含 version，删除前取详情获得乐观锁版本与最新名称/code
    deleteTarget.value = await getCluster(row.id)
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
  deleteServerConfirmError.value = ''
  deleteAssocConflict.value = ''
  deleteSubmitting.value = true
  try {
    await deleteCluster(target.id, { confirm: deleteConfirmInput.value, version: target.version })
    ElMessage.success(`集群「${target.name}」已删除`)
    deleteVisible.value = false
    void load()
    refreshClusterCache()
  } catch (error) {
    if (isApiError(error)) {
      if (error.code === 'DELETE_CONFIRMATION_MISMATCH') {
        // 422：确认不匹配，不执行删除；保留对话框与输入
        deleteServerConfirmError.value =
          '确认输入与该集群的名称或编号不匹配（集群可能已被其他人修改），未执行删除'
      } else if (error.code === 'CLUSTER_HAS_ASSOCIATIONS') {
        // 409 关联保护：仍存计算资源/网段/服务关联，须先显式处理，不级联
        deleteAssocConflict.value =
          '该集群仍有关联的计算资源、网段或服务，须先逐项删除或解除相应关联后才能删除'
      } else if (error.code === 'VERSION_CONFLICT') {
        deleteVisible.value = false
        ElMessage.error('该集群已被其他人修改，请重试')
        void load()
        refreshClusterCache()
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

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="clusters-page">
    <!-- 搜索/排序区 -->
    <el-card class="clusters-filter" shadow="never">
      <el-form inline @submit.prevent="handleSearch">
        <el-form-item label="搜索">
          <el-input
            v-model="query.q"
            placeholder="集群编号或名称包含匹配"
            clearable
            style="width: 240px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-select v-model="query.sort" style="width: 160px" @change="handleSearch">
            <el-option value="code" label="编号 升序" />
            <el-option value="-code" label="编号 降序" />
            <el-option value="name" label="名称 升序" />
            <el-option value="-name" label="名称 降序" />
            <el-option value="created_at" label="创建时间 升序" />
            <el-option value="-created_at" label="创建时间 降序" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleResetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表区 -->
    <el-card shadow="never">
      <div class="clusters-toolbar">
        <h3 class="clusters-title">集群列表</h3>
        <!-- 新增仅平台管理员（服务端校验为最终保证） -->
        <el-button v-if="canCreate" type="primary" @click="openCreate">新增集群</el-button>
      </div>

      <el-alert
        v-if="listError"
        type="error"
        :closable="false"
        show-icon
        :title="listError"
        class="clusters-error"
      >
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-else v-loading="loading" :data="items" class="clusters-table">
        <el-table-column prop="code" label="编号" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="cluster-code">{{ row.code }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="purpose" label="用途" min-width="220" show-overflow-tooltip />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column v-if="canCreate || canDelete" label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <!-- 编辑仅平台管理员；删除 maintainer/admin；查看者无操作入口 -->
            <el-button v-if="canCreate" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canDelete" link type="danger" @click="openDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="hasFilter ? '未找到匹配的集群' : '暂无集群'" />
        </template>
      </el-table>

      <div class="clusters-pagination">
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

    <!-- 新增集群 -->
    <el-dialog v-model="createVisible" title="新增集群" width="480px" :close-on-click-modal="false">
      <el-form
        ref="createFormRef"
        :model="createForm"
        label-position="top"
        @submit.prevent="handleCreate"
      >
        <el-form-item
          label="集群编号（code）"
          prop="code"
          :rules="clusterCodeRule"
          :error="createServerErrors.code || undefined"
        >
          <el-input
            v-model="createForm.code"
            placeholder="如 N96P；创建后不可修改，真实删除后不可复用"
            @input="createServerErrors.code = ''"
          />
        </el-form-item>
        <el-form-item
          label="集群名称"
          prop="name"
          :rules="clusterNameRule"
          :error="createServerErrors.name || undefined"
        >
          <el-input
            v-model="createForm.name"
            :placeholder="CLUSTER_NAME_RULE_MESSAGE"
            @input="createServerErrors.name = ''"
          />
        </el-form-item>
        <el-form-item
          label="用途"
          prop="purpose"
          :rules="clusterPurposeRule"
          :error="createServerErrors.purpose || undefined"
        >
          <el-input
            v-model="createForm.purpose"
            type="textarea"
            :rows="2"
            placeholder="如：训练集群 / 推理集群"
            @input="createServerErrors.purpose = ''"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSubmitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑集群（code 创建后不可改，仅名称/用途可编辑） -->
    <el-dialog v-model="editVisible" title="编辑集群" width="480px" :close-on-click-modal="false">
      <el-form
        ref="editFormRef"
        v-loading="editLoading"
        :model="editForm"
        label-position="top"
        @submit.prevent="handleEdit"
      >
        <el-form-item label="集群编号（创建后不可修改）">
          <el-input :model-value="editForm.code" disabled />
        </el-form-item>
        <el-form-item
          label="集群名称"
          prop="name"
          :rules="clusterNameRule"
          :error="editServerErrors.name || undefined"
        >
          <el-input v-model="editForm.name" @input="editServerErrors.name = ''" />
        </el-form-item>
        <el-form-item
          label="用途"
          prop="purpose"
          :rules="clusterPurposeRule"
          :error="editServerErrors.purpose || undefined"
        >
          <el-input
            v-model="editForm.purpose"
            type="textarea"
            :rows="2"
            @input="editServerErrors.purpose = ''"
          />
        </el-form-item>
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

    <!-- 真实删除：二次确认须输入集群名称或 code 匹配（BQ-Z） -->
    <el-dialog v-model="deleteVisible" title="删除集群" width="500px" :close-on-click-modal="false">
      <div v-loading="deleteLoading">
        <template v-if="deleteTarget">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="真实删除不可恢复：删除后集群编号（code）永不复用；审计与资源历史保留"
            class="delete-warning"
          />
          <p class="delete-target">
            将删除集群：<strong>{{ deleteTarget.name }}</strong>（编号
            <code class="cluster-code">{{ deleteTarget.code }}</code>）
          </p>
          <el-form @submit.prevent="handleDelete">
            <el-form-item
              label="请输入集群名称或编号以确认删除"
              :error="deleteServerConfirmError || undefined"
            >
              <el-input
                v-model="deleteConfirmInput"
                :placeholder="`输入「${deleteTarget.name}」或「${deleteTarget.code}」`"
                @input="deleteServerConfirmError = ''"
              />
            </el-form-item>
          </el-form>
          <el-alert
            v-if="deleteAssocConflict"
            type="error"
            :closable="false"
            show-icon
            :title="deleteAssocConflict"
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
  </div>
</template>

<style scoped>
.clusters-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.clusters-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.clusters-title {
  margin: 0;
  font-size: 16px;
}
.clusters-error {
  margin-bottom: 12px;
}
.clusters-table {
  width: 100%;
}
.clusters-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.cluster-code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
.delete-warning {
  margin-bottom: 12px;
}
.delete-target {
  margin: 0 0 12px;
}
</style>
