<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import { createCluster, updateCluster } from '../api/clusters'
import type { ClusterRead } from '../api/clusters'

/**
 * 集群登记 / 改名对话框（F016；契约 docs/api/f001-cluster.md §3.1 / §3.5）。
 *
 * - create 模式：name → POST /api/clusters；edit 模式：name → PATCH
 *   /api/clusters/{id}（写操作一律走 id，ADR-0003 §2）。登记与改名共用本
 *   组件，仅模式不同（AC-03），不存在第二套表单；
 * - 表单恰一个字段 name（AC-04）：无运行状态（R-CLUSTER-003）、无
 *   DataCenter / 位置 / 机柜 / U 位（§6、§13）、无上级 / BareMetal 计数 /
 *   关系、无 deleted_at（契约 §2 字段集合封闭）；
 * - 前端不实现任何业务校验或名称变换（AC-05、§21）：`/` 禁令、活跃全局
 *   唯一（区分大小写）、逻辑删除语义的唯一裁决方是后端 + 数据库。本组件
 *   不检测 `/`、不发起唯一性 / 存在性预检（不引用任何读 API）、不做大小写
 *   折叠、不做首尾空白处理、不做 Unicode 归一化、不做长度判断；name 原样
 *   提交。空串 / 首尾空白等取值属 undefined_constraints（契约 §7），前端
 *   不得据此拦截——提交按钮的禁用条件仅为提交中，不依赖 form.name（与
 *   既有 FormDialog 按表单完成度禁用的做法不同，原因即此）；
 * - 打开时不发起任何请求（无选项加载，与 BareMetalFormDialog 不同）；
 * - 失败按 error.code（必要时结合 details[].code / details[].field）分支
 *   渲染固定文案，不解析 message（契约 §5）：VALIDATION_ERROR → 字段级
 *   提示指向 name；CONFLICT + DUPLICATE → 「已存在活跃的同名集群」；
 *   NOT_FOUND（仅 PATCH 契约上产生）→ 「该集群不存在或已被删除」；401 交由
 *   既有全局会话失效处理（api/http.ts），不渲染本地提示；提交中 Loading
 *   且禁止重复提交；失败提示可关闭，关闭后可修改再次提交。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** edit 模式：当前 Cluster（表单初值）；create 模式忽略。 */
  cluster?: ClusterRead | null
}>()

const emit = defineEmits<{
  /** 登记或改名成功，携带服务端返回的 ClusterRead（201 / 200）。 */
  success: [cluster: ClusterRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

const form = reactive({ name: '' })

const dialogTitle = computed(() => (props.mode === 'create' ? '登记集群' : '集群改名'))
const submitLabel = computed(() => (props.mode === 'create' ? '登记' : '保存'))

const submitting = ref(false)
const failure = ref<ApiError | null>(null)

// ---- 打开时初始化表单（不发起任何请求） ----

watch(
  dialogVisible,
  (open) => {
    if (!open) return
    failure.value = null
    if (props.mode === 'edit' && props.cluster !== null && props.cluster !== undefined) {
      form.name = props.cluster.name
    } else {
      form.name = ''
    }
  },
  { immediate: true },
)

// ---- 提交 ----

interface FailureView {
  code: string
  title: string
  description: string
  details: readonly ApiErrorDetail[]
}

/** 失败提示视图：按 error.code 分支生成固定文案，不解析 message。 */
const failureView = computed<FailureView | null>(() => {
  const error = failure.value
  if (error === null) return null
  switch (error.code) {
    case 'VALIDATION_ERROR':
      return {
        code: error.code,
        title: '请求校验失败',
        description: '提交的内容不符合要求，请根据下方字段提示修改后重试。',
        details: error.details,
      }
    case 'CONFLICT': {
      // 契约 §3.1 / §3.5：活跃同名（全局唯一、区分大小写）→
      // details[].field === 'name' 且 details[].code === 'DUPLICATE'。
      const duplicateName = error.details.some(
        (detail) => detail.field === 'name' && detail.code === 'DUPLICATE',
      )
      if (duplicateName) {
        return {
          code: error.code,
          title: props.mode === 'create' ? '无法登记' : '无法保存',
          description: '已存在活跃的同名集群（名称在所有当前有效集群中全局唯一、区分大小写）。',
          details: [],
        }
      }
      return {
        code: error.code,
        title: '数据冲突',
        description: '保存的内容与现有数据冲突，请稍后重试。',
        details: [],
      }
    }
    case 'NOT_FOUND':
      // 契约 §3.5：仅 PATCH 产生 404（目标不存在或已逻辑删除，两者不区分）。
      // create 分支为防御性兜底（按 code 原样展示）；POST 契约上不产生 404。
      return props.mode === 'edit'
        ? {
            code: error.code,
            title: '无法保存',
            description: '该集群不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
        : {
            code: error.code,
            title: '提交失败',
            description: '请求未成功（NOT_FOUND），请稍后重试。',
            details: [],
          }
    case 'NETWORK_ERROR':
      return {
        code: error.code,
        title: '无法连接服务器',
        description: '请求未能送达服务器，请检查网络或服务状态后重试。',
        details: [],
      }
    case 'UNAUTHENTICATED':
      // 401 由全局会话失效处理（api/http.ts → App 切回登录页），不渲染本地提示。
      return null
    default:
      return {
        code: error.code,
        title: '提交失败',
        description: `请求未成功（${error.code}），请稍后重试。`,
        details: [],
      }
  }
})

async function handleSubmit(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  failure.value = null
  try {
    let saved: ClusterRead
    if (props.mode === 'create') {
      // name 原样提交：不校验、不变换（契约 §7 undefined_constraints）；空串 /
      // 首尾空白 / 含斜杠等均由服务端裁决，前端不编写业务分支（§21）。
      saved = await createCluster({ name: form.name })
    } else {
      const target = props.cluster
      if (target === null || target === undefined) return
      saved = await updateCluster(target.id, { name: form.name })
    }
    emit('success', saved)
    dialogVisible.value = false
  } catch (err) {
    const apiError =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
    // 401 交由全局会话失效处理（api/http.ts 已在抛出前调用处理器），不设置本地失败。
    if (apiError.code !== 'UNAUTHENTICATED') {
      failure.value = apiError
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    :close-on-click-modal="false"
    width="520px"
  >
    <!-- 提交失败提示：按 error.code 生成固定文案，可关闭；message 不参与分支。 -->
    <el-alert
      v-if="failureView !== null"
      class="cluster-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="cluster-form__failure-details">
        <p v-for="(detail, index) in failureView.details" :key="index">
          <el-tag size="small" type="danger">
            {{ detail.field ?? detail.code ?? '字段' }}
          </el-tag>
          <span v-if="detail.message">{{ detail.message }}</span>
        </p>
      </div>
    </el-alert>

    <el-form label-width="90px">
      <!-- 唯一字段 name（AC-04）。不做任何长度 / 空串 / 字符 / 格式校验（契约 §7 未定义约束）。 -->
      <el-form-item label="名称">
        <el-input
          v-model="form.name"
          placeholder="全局唯一（由服务端校验）"
          data-testid="cluster-form-name"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <!-- 禁用条件仅为提交中：不依赖 form.name（空串行为属 undefined_constraints，AC-05）。 -->
      <el-button
        type="primary"
        :loading="submitting"
        data-testid="cluster-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.cluster-form__failure {
  margin-bottom: 16px;
}

.cluster-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.cluster-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
