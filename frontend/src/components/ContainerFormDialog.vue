<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import {
  CONTAINER_CARRIER_TYPES,
  CONTAINER_OPTIONAL_FIELDS,
  createContainer,
  updateContainer,
} from '../api/containers'
import type {
  ContainerCarrier,
  ContainerCarrierType,
  ContainerOptionalField,
  ContainerRead,
} from '../api/containers'

/**
 * 容器登记 / 编辑对话框（契约 docs/api/f007-container.md §4.1 / §4.4）。
 *
 * - create 模式：载体类型（封闭枚举 BARE_METAL / VIRTUAL_MACHINE，R-CONTAINER-002）
 *   + 载体 ID + name + R-CONTAINER-004 四字段（可选）→ POST /api/containers；
 * - edit 模式：R-CONTAINER-004 四字段 → PATCH；name / 载体绑定不在 PATCH 可变集内
 *   （契约 §4.4 / NQ-1，登记后不可变），表单不提供其输入；
 * - 前端不重复实现业务守卫（§21）：载体内 name 唯一（409）、载体存在性 /
 *   活跃性 / 类型一致性（404）一律由服务端裁决，本表单不预判、不拦截；name
 *   不做任何长度 / 空串 / 字符 / 格式校验（契约 §8 undefined_constraints，
 *   前端不得基于未定义项编写业务分支）；载体 ID 接受任意整数（不设最小值
 *   等约束），存在性与类型一致性由服务端裁决；
 * - 载体类型未选择或载体 ID 未填写（表单未完成）时提交按钮禁用 —— 这不是
 *   载体存在性预判：任何已填写的载体对都直接提交，由服务端裁决（并发删除
 *   → 404 渲染）；
 * - 失败按 error.code（必要时结合 details[].code / details[].field）分支渲染
 *   固定文案（不解析 message）：VALIDATION_ERROR → 字段级提示；
 *   NOT_FOUND → create：「请检查载体类型与载体 ID」；CONFLICT +
 *   details[].code === 'DUPLICATE' → 「同一载体内已存在活跃的同名容器」
 *   （唯一性边界是载体而非全局 / Cluster，R-CONTAINER-003）；401 交由既有
 *   全局会话失效处理；提交中 Loading 且禁止重复提交；
 * - 四字段输入为空 → 提交 null（清空 / 保持为 null，契约 §4.1 / §4.4）。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** create 模式：预选的载体（可改选）；edit 模式忽略。 */
  presetCarrier?: ContainerCarrier | null
  /** edit 模式：当前 Container（表单初值）；create 模式忽略。 */
  container?: ContainerRead | null
}>()

const emit = defineEmits<{
  /** 登记或更新成功，携带服务端返回的 ContainerRead。 */
  success: [container: ContainerRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

const OPTIONAL_FIELD_DEFS: ReadonlyArray<{
  key: ContainerOptionalField
  label: string
  placeholder: string
}> = [
  { key: 'image', label: 'Image', placeholder: '可选，纯文本' },
  { key: 'cpu', label: 'CPU', placeholder: '可选，纯文本' },
  { key: 'memory', label: '内存', placeholder: '可选，纯文本' },
  { key: 'owner', label: '负责人', placeholder: '可选，纯文本' },
]

interface ContainerFormState {
  carrierType: ContainerCarrierType | null
  carrierId: number | null
  name: string
  optional: Record<ContainerOptionalField, string>
}

function emptyOptional(): Record<ContainerOptionalField, string> {
  return { image: '', cpu: '', memory: '', owner: '' }
}

const form = reactive<ContainerFormState>({
  carrierType: null,
  carrierId: null,
  name: '',
  optional: emptyOptional(),
})

const dialogTitle = computed(() => (props.mode === 'create' ? '登记容器' : '编辑容器'))
const submitLabel = computed(() => (props.mode === 'create' ? '登记' : '保存'))

// ---- 打开时初始化表单 ----

watch(
  dialogVisible,
  (open) => {
    if (!open) return
    failure.value = null
    if (props.mode === 'edit' && props.container !== null && props.container !== undefined) {
      form.carrierType = props.container.carrier_type
      form.carrierId = props.container.carrier_id
      form.name = props.container.name
      for (const field of CONTAINER_OPTIONAL_FIELDS) {
        form.optional[field] = props.container[field] ?? ''
      }
    } else {
      form.carrierType = props.presetCarrier?.carrier_type ?? null
      form.carrierId = props.presetCarrier?.carrier_id ?? null
      form.name = ''
      form.optional = emptyOptional()
    }
  },
  { immediate: true },
)

// ---- 提交 ----

const submitting = ref(false)
const failure = ref<ApiError | null>(null)

/**
 * create 模式下载体类型未选或载体 ID 未填 → 表单未完成，提交按钮禁用（非业务
 * 守卫，见头注）。edit 模式无需填写载体。
 */
const submitDisabled = computed(
  () => props.mode === 'create' && (form.carrierType === null || form.carrierId === null),
)

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
    case 'NOT_FOUND':
      // create：载体不存在 / 已逻辑删除 / 类型与标识不一致（契约 §4.1，三者
      // 不区分）；edit：目标 Container 不存在或已被逻辑删除（契约 §4.4）。
      return props.mode === 'create'
        ? {
            code: error.code,
            title: '无法登记',
            description: '载体不存在或已被删除，请检查载体类型与载体 ID 后重试。',
            details: [],
          }
        : {
            code: error.code,
            title: '无法保存',
            description: '该容器不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
    case 'CONFLICT': {
      // 契约 §5.1：稳定判别值为 details[].field === 'name' +
      // details[].code === 'DUPLICATE'（同一载体内活跃重名，R-CONTAINER-003）。
      const duplicateName = error.details.some(
        (detail) => detail.field === 'name' && detail.code === 'DUPLICATE',
      )
      return duplicateName
        ? {
            code: error.code,
            title: '无法登记',
            description: '同一载体内已存在活跃的同名容器（名称在载体内唯一、区分大小写）。',
            details: [],
          }
        : {
            code: error.code,
            title: '数据冲突',
            description: '保存的内容与现有数据冲突，请稍后重试。',
            details: [],
          }
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

/** 组装 R-CONTAINER-004 四字段请求体：输入为空 → null（清空 / 保持 null）。 */
function optionalBody(): Record<ContainerOptionalField, string | null> {
  const body = {} as Record<ContainerOptionalField, string | null>
  for (const field of CONTAINER_OPTIONAL_FIELDS) {
    const value = form.optional[field]
    body[field] = value === '' ? null : value
  }
  return body
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || submitDisabled.value) return
  submitting.value = true
  failure.value = null
  try {
    let saved: ContainerRead
    if (props.mode === 'create') {
      // submitDisabled 已保证 create 模式下载体对已填写；此处再显式兜底。
      const carrierType = form.carrierType
      const carrierId = form.carrierId
      if (carrierType === null || carrierId === null) return
      // name 原样提交：不校验、不变换（契约 §8）；空串 / 首尾空白等未定义
      // 约束由服务端裁决，前端不编写业务分支（§21）。
      saved = await createContainer({
        carrier_type: carrierType,
        carrier_id: carrierId,
        name: form.name,
        ...optionalBody(),
      })
    } else {
      const target = props.container
      if (target === null || target === undefined) return
      saved = await updateContainer(target.id, optionalBody())
    }
    emit('success', saved)
    dialogVisible.value = false
  } catch (err) {
    const apiError =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
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
      class="container-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="container-form__failure-details">
        <p v-for="(detail, index) in failureView.details" :key="index">
          <el-tag size="small" type="danger">
            {{ detail.field ?? detail.code ?? '字段' }}
          </el-tag>
          <span v-if="detail.message">{{ detail.message }}</span>
        </p>
      </div>
    </el-alert>

    <el-form label-width="90px">
      <!-- create：载体类型（封闭枚举，R-CONTAINER-002；契约原样值展示，不做翻译）。
           载体存在性 / 活跃性 / 类型一致性由服务端裁决（404 → 固定文案）。 -->
      <el-form-item v-if="mode === 'create'" label="载体类型">
        <el-select
          v-model="form.carrierType"
          class="container-form__carrier-type"
          placeholder="BARE_METAL 或 VIRTUAL_MACHINE"
          data-testid="container-form-carrier-type"
        >
          <el-option
            v-for="carrierType in CONTAINER_CARRIER_TYPES"
            :key="carrierType"
            :label="carrierType"
            :value="carrierType"
          />
        </el-select>
      </el-form-item>

      <!-- create：载体 ID（整数，不设最小值等约束；任何已填写的值都直接提交，
           由服务端裁决）。 -->
      <el-form-item v-if="mode === 'create'" label="载体 ID">
        <el-input-number
          v-model="form.carrierId"
          class="container-form__carrier-id"
          placeholder="载体在该类型下的 id"
          :controls="false"
          data-testid="container-form-carrier-id"
        />
      </el-form-item>

      <!-- create：name。不做任何长度 / 空串 / 字符 / 格式校验（契约 §8 未定义约束）。 -->
      <el-form-item v-if="mode === 'create'" label="名称">
        <el-input
          v-model="form.name"
          placeholder="同一载体内唯一（由服务端校验）"
          data-testid="container-form-name"
        />
      </el-form-item>

      <!-- R-CONTAINER-004 四字段：可选、纯文本；输入为空提交 null（清空）。 -->
      <el-form-item
        v-for="field in OPTIONAL_FIELD_DEFS"
        :key="field.key"
        :label="field.label"
      >
        <el-input
          v-model="form.optional[field.key]"
          :placeholder="field.placeholder"
          :data-testid="`container-form-${field.key}`"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="container-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.container-form__failure {
  margin-bottom: 16px;
}

.container-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.container-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
