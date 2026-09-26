<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormItemRule } from 'element-plus'
import {
  createUser,
  deleteUser,
  disableUser,
  enableUser,
  getUser,
  listUsers,
  resetPassword,
  updateUser,
} from '../api/users'
import { apiErrorMessage, isApiError } from '../api/client'
import type { Role, UserListItem, UserStatus } from '../api/types'
import {
  PASSWORD_POLICY_MESSAGE,
  ROLE_OPTIONS,
  STATUS_LABELS,
  isProtectedAdmin,
  roleLabel,
  statusLabel,
  validatePassword,
  validateUsername,
} from '../utils/validation'

// ---------- 列表查询（Contract §3.1：page/page_size/q/role/status/sort） ----------
const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  role: '' as Role | '',
  status: '' as UserStatus | '',
  sort: 'username' as 'username' | '-username' | 'created_at' | '-created_at',
})

const items = ref<UserListItem[]>([])
const total = ref(0)
const loading = ref(false)
const listError = ref('')

const hasFilter = computed(() => query.q.trim() !== '' || query.role !== '' || query.status !== '')

async function load(): Promise<void> {
  loading.value = true
  listError.value = ''
  try {
    const data = await listUsers({
      page: query.page,
      page_size: query.page_size,
      q: query.q,
      role: query.role === '' ? undefined : query.role,
      status: query.status === '' ? undefined : query.status,
      sort: query.sort,
    })
    items.value = data.items
    total.value = data.total
  } catch (error) {
    // 错误状态显式呈现，不伪装成空列表
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
  query.role = ''
  query.status = ''
  query.sort = 'username'
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

/** 404 USER_NOT_FOUND：目标已不存在，刷新列表 */
function isNotFound(error: unknown): boolean {
  return isApiError(error) && error.status === 404
}

function handleActionError(error: unknown): void {
  if (isNotFound(error)) {
    ElMessage.warning('该用户已不存在，列表已刷新')
    void load()
    return
  }
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

// ---------- 新增用户（Contract §3.2） ----------
const createVisible = ref(false)
const createSubmitting = ref(false)
const createFormRef = ref<FormInstance>()
const createServerErrors = reactive({ username: '', password: '' })
const createForm = reactive({ username: '', password: '', confirmPassword: '', role: 'viewer' as Role })

const usernameRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validateUsername(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  },
]
const passwordRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validatePassword(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  },
]
const createConfirmRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      if ((value ?? '') === '') callback(new Error('请再次输入口令'))
      else if (value !== createForm.password) callback(new Error('两次输入的口令不一致'))
      else callback()
    },
    trigger: 'blur',
  },
]

function openCreate(): void {
  createForm.username = ''
  createForm.password = ''
  createForm.confirmPassword = ''
  createServerErrors.username = ''
  createServerErrors.password = ''
  createVisible.value = true
}

async function handleCreate(): Promise<void> {
  createServerErrors.username = ''
  createServerErrors.password = ''
  const valid = await createFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  createSubmitting.value = true
  try {
    await createUser({
      username: createForm.username,
      password: createForm.password,
      role: createForm.role,
    })
    ElMessage.success('用户已创建')
    createVisible.value = false
    void load()
  } catch (error) {
    if (isApiError(error)) {
      // 409 USERNAME_TAKEN：保留输入并提示（不关闭、不清空表单）
      if (error.code === 'USERNAME_TAKEN') {
        createServerErrors.username =
          '用户名已被占用（包括已删除用户，用户名不可复用）'
      } else if (error.status === 422) {
        createServerErrors.username = error.fieldError('username') ?? ''
        createServerErrors.password = error.fieldError('password') ?? ''
      } else {
        ElMessage.error(apiErrorMessage(error))
      }
    } else {
      ElMessage.error(apiErrorMessage(error))
    }
  } finally {
    createSubmitting.value = false
  }
}

// ---------- 编辑角色（Contract §3.4：仅角色可改，用户名创建后不可改） ----------
const editVisible = ref(false)
const editSubmitting = ref(false)
const editLoading = ref(false)
const editConflict = ref('')
const editServerErrors = reactive({ role: '' })
const editForm = reactive({ id: 0, username: '', role: 'viewer' as Role, version: 0 })

async function openEdit(row: UserListItem): Promise<void> {
  editConflict.value = ''
  editServerErrors.role = ''
  editVisible.value = true
  editLoading.value = true
  try {
    // 列表项不含 version，编辑前取详情获得乐观锁版本
    const detail = await getUser(row.id)
    editForm.id = detail.id
    editForm.username = detail.username
    editForm.role = detail.role
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
  editServerErrors.role = ''
  editSubmitting.value = true
  try {
    await updateUser(editForm.id, { role: editForm.role, version: editForm.version })
    ElMessage.success('角色已更新')
    editVisible.value = false
    void load()
  } catch (error) {
    if (isApiError(error)) {
      if (error.code === 'VERSION_CONFLICT') {
        // 保留输入并提示；用户可关闭后重新打开以获取最新版本
        editConflict.value = '该用户已被其他人修改，当前编辑内容未提交。请关闭后重新打开编辑。'
      } else if (error.code === 'PROTECTED_ADMIN') {
        // 内置账号 admin 角色不可修改（BQ-Y）；列表入口已禁用，此处为服务端拒绝的兜底处理
        editVisible.value = false
        ElMessage.error('内置管理员账号不可修改角色')
      } else if (error.status === 422) {
        editServerErrors.role = error.fieldError('role') ?? ''
      } else {
        ElMessage.error(apiErrorMessage(error))
      }
    } else {
      ElMessage.error(apiErrorMessage(error))
    }
  } finally {
    editSubmitting.value = false
  }
}

// ---------- 删除（Contract §3.5：version 经 query；内置账号 admin 409 PROTECTED_ADMIN，BQ-Y） ----------
async function handleDelete(row: UserListItem): Promise<void> {
  let version: number
  try {
    const detail = await getUser(row.id)
    version = detail.version
  } catch (error) {
    handleActionError(error)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除用户「${row.username}」吗？删除后该用户不能再登录，且用户名不可复用。`,
      '删除用户',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await deleteUser(row.id, version)
    ElMessage.success('用户已删除')
    void load()
  } catch (error) {
    if (isApiError(error) && error.code === 'PROTECTED_ADMIN') {
      ElMessage.error('内置管理员账号不可删除')
    } else if (isApiError(error) && error.code === 'VERSION_CONFLICT') {
      ElMessage.error('该用户已被其他人修改，请刷新后重试')
      void load()
    } else {
      handleActionError(error)
    }
  }
}

// ---------- 禁用 / 启用（Contract §3.6/§3.7） ----------
async function handleToggleStatus(row: UserListItem): Promise<void> {
  if (row.status === 'enabled') {
    try {
      await ElMessageBox.confirm(
        `确定禁用用户「${row.username}」吗？禁用后该用户不能登录，可重新启用。`,
        '禁用用户',
        { type: 'warning', confirmButtonText: '禁用', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    try {
      await disableUser(row.id)
      ElMessage.success('用户已禁用')
      void load()
    } catch (error) {
      if (isApiError(error) && error.code === 'PROTECTED_ADMIN') {
        ElMessage.error('内置管理员账号不可禁用')
      } else {
        handleActionError(error)
      }
    }
  } else {
    try {
      await ElMessageBox.confirm(
        `确定启用用户「${row.username}」吗？启用后该用户可重新登录。`,
        '启用用户',
        { type: 'info', confirmButtonText: '启用', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
    try {
      await enableUser(row.id)
      ElMessage.success('用户已启用')
      void load()
    } catch (error) {
      handleActionError(error)
    }
  }
}

// ---------- 重置口令（Contract §3.8） ----------
const resetVisible = ref(false)
const resetSubmitting = ref(false)
const resetFormRef = ref<FormInstance>()
const resetServerErrors = reactive({ new_password: '' })
const resetTarget = ref<UserListItem | null>(null)
const resetForm = reactive({ newPassword: '', confirmPassword: '' })

const resetPasswordRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validatePassword(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  },
]
const resetConfirmRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      if ((value ?? '') === '') callback(new Error('请再次输入新口令'))
      else if (value !== resetForm.newPassword) callback(new Error('两次输入的新口令不一致'))
      else callback()
    },
    trigger: 'blur',
  },
]

function openReset(row: UserListItem): void {
  resetTarget.value = row
  resetForm.newPassword = ''
  resetForm.confirmPassword = ''
  resetServerErrors.new_password = ''
  resetVisible.value = true
}

async function handleReset(): Promise<void> {
  if (!resetTarget.value) return
  resetServerErrors.new_password = ''
  const valid = await resetFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  resetSubmitting.value = true
  try {
    await resetPassword(resetTarget.value.id, { new_password: resetForm.newPassword })
    ElMessage.success(`已重置「${resetTarget.value.username}」的口令，该用户下次登录须先修改口令`)
    resetVisible.value = false
    void load()
  } catch (error) {
    if (isApiError(error) && error.status === 422) {
      resetServerErrors.new_password = error.fieldError('new_password') ?? PASSWORD_POLICY_MESSAGE
    } else {
      handleActionError(error)
    }
  } finally {
    resetSubmitting.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="users-page">
    <!-- 筛选区 -->
    <el-card class="users-filter" shadow="never">
      <el-form inline @submit.prevent="handleSearch">
        <el-form-item label="用户名">
          <el-input
            v-model="query.q"
            placeholder="用户名包含匹配"
            clearable
            style="width: 200px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="query.role" clearable placeholder="全部" style="width: 150px" @change="handleSearch">
            <el-option v-for="opt in ROLE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 120px" @change="handleSearch">
            <el-option value="enabled" :label="STATUS_LABELS.enabled" />
            <el-option value="disabled" :label="STATUS_LABELS.disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-select v-model="query.sort" style="width: 160px" @change="handleSearch">
            <el-option value="username" label="用户名 升序" />
            <el-option value="-username" label="用户名 降序" />
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
      <div class="users-toolbar">
        <h3 class="users-title">用户列表</h3>
        <el-button type="primary" @click="openCreate">新增用户</el-button>
      </div>

      <el-alert
        v-if="listError"
        type="error"
        :closable="false"
        show-icon
        :title="listError"
        class="users-error"
      >
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-else v-loading="loading" :data="items" class="users-table">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="160" show-overflow-tooltip />
        <el-table-column label="角色" width="130">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'maintainer' ? 'warning' : 'info'">
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'enabled' ? 'success' : 'info'">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="首登须改密" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.must_change_password" type="warning" size="small">须改密</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <!-- 内置管理员账号（BQ-Y）：删除/禁用/修改角色（编辑）不可用，仅可重置口令。
                 此处仅为交互提示，服务端仍以 409 PROTECTED_ADMIN 做最终校验。 -->
            <el-tooltip
              v-if="isProtectedAdmin(row.username)"
              content="内置管理员账号不可删除、不可禁用、不可修改角色"
              placement="top"
            >
              <span class="protected-ops">
                <el-button link type="primary" disabled>编辑</el-button>
                <el-button link type="primary" @click="openReset(row)">重置口令</el-button>
                <el-button link type="warning" disabled>禁用</el-button>
                <el-button link type="danger" disabled>删除</el-button>
              </span>
            </el-tooltip>
            <template v-else>
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="primary" @click="openReset(row)">重置口令</el-button>
              <el-button link :type="row.status === 'enabled' ? 'warning' : 'success'" @click="handleToggleStatus(row)">
                {{ row.status === 'enabled' ? '禁用' : '启用' }}
              </el-button>
              <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="hasFilter ? '未找到匹配的用户' : '暂无用户'" />
        </template>
      </el-table>

      <div class="users-pagination">
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

    <!-- 新增用户 -->
    <el-dialog v-model="createVisible" title="新增用户" width="460px" :close-on-click-modal="false">
      <el-form
        ref="createFormRef"
        :model="createForm"
        label-position="top"
        @submit.prevent="handleCreate"
      >
        <el-form-item
          label="用户名"
          prop="username"
          :rules="usernameRule"
          :error="createServerErrors.username || undefined"
        >
          <el-input
            v-model="createForm.username"
            placeholder="仅字母与数字，长度 1–128，创建后不可修改"
            @input="createServerErrors.username = ''"
          />
        </el-form-item>
        <el-form-item
          label="初始口令"
          prop="password"
          :rules="passwordRule"
          :error="createServerErrors.password || undefined"
        >
          <el-input
            v-model="createForm.password"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="PASSWORD_POLICY_MESSAGE"
            @input="createServerErrors.password = ''"
          />
        </el-form-item>
        <el-form-item label="确认口令" prop="confirmPassword" :rules="createConfirmRule">
          <el-input
            v-model="createForm.confirmPassword"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="handleCreate"
          />
        </el-form-item>
        <el-form-item label="角色" prop="role" required>
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option v-for="opt in ROLE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSubmitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑角色（用户名创建后不可修改，BQ-X） -->
    <el-dialog v-model="editVisible" title="编辑用户" width="460px" :close-on-click-modal="false">
      <el-form v-loading="editLoading" :model="editForm" label-position="top" @submit.prevent="handleEdit">
        <el-form-item label="用户名（创建后不可修改）">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="角色" required :error="editServerErrors.role || undefined">
          <el-select v-model="editForm.role" style="width: 100%" @change="editServerErrors.role = ''">
            <el-option v-for="opt in ROLE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
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

    <!-- 重置口令 -->
    <el-dialog v-model="resetVisible" title="重置口令" width="460px" :close-on-click-modal="false">
      <p v-if="resetTarget" class="reset-target">
        目标用户：<strong>{{ resetTarget.username }}</strong>
      </p>
      <el-form
        ref="resetFormRef"
        :model="resetForm"
        label-position="top"
        @submit.prevent="handleReset"
      >
        <el-form-item
          label="新口令"
          prop="newPassword"
          :rules="resetPasswordRule"
          :error="resetServerErrors.new_password || undefined"
        >
          <el-input
            v-model="resetForm.newPassword"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="PASSWORD_POLICY_MESSAGE"
            @input="resetServerErrors.new_password = ''"
          />
        </el-form-item>
        <el-form-item label="确认新口令" prop="confirmPassword" :rules="resetConfirmRule">
          <el-input
            v-model="resetForm.confirmPassword"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="handleReset"
          />
        </el-form-item>
      </el-form>
      <p class="reset-hint">重置后该用户的旧口令失效、现有会话失效，该用户下次登录须先修改口令。</p>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetSubmitting" @click="handleReset">重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.users-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.users-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.users-title {
  margin: 0;
  font-size: 16px;
}
.users-error {
  margin-bottom: 12px;
}
.users-table {
  width: 100%;
}
.users-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.reset-target {
  margin: 0 0 12px;
}
/* 内置管理员操作区（BQ-Y）：包裹禁用按钮，保证 tooltip 悬停可用 */
.protected-ops {
  display: inline-block;
}
.reset-hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
</style>
