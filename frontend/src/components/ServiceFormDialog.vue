<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import {
  SERVICE_CARRIER_TYPES,
  SERVICE_OPTIONAL_FIELDS,
  createService,
  updateService,
} from '../api/services'
import type {
  ServiceCarrier,
  ServiceCarrierType,
  ServiceOptionalField,
  ServiceRead,
} from '../api/services'

/**
 * Service 登记 / 编辑对话框（契约 docs/api/f008-service.md §4.1 / §4.4）。
 *
 * - create 模式：name + 多载体选择（三种载体类型 + 载体 ID，可多选）+
 *   6 个可选字段 → POST /api/services；
 * - edit 模式：仅 6 个可选字段 → PATCH；name 与载体绑定不在 PATCH 可变集内
 *   （契约 §4.4 / NQ-01，登记时一次确定、登记后不可变），表单不提供其输入；
 * - 前端不重复实现业务守卫（§21）：name 全局唯一（409）、载体存在性 /
 *   活跃性 / 类型一致性（404）、同一请求内重复载体（400 DUPLICATE）一律由
 *   服务端裁决，本表单不预判、不拦截、不去重；name 不做任何长度 / 空串 /
 *   字符 / 格式校验（契约 §8 undefined_constraints，前端不得基于未定义项
 *   编写业务分支）；载体 ID 接受任意整数（不设最小值等约束）；
 * - 「至少一项载体」（R-SVC-005）是唯一的表单完整性约束：无载体行，或任一
 *   载体行的类型 / ID 未填完整时提交按钮禁用 —— 这不是载体存在性预判：
 *   任何已填完整的载体对都直接提交，由服务端裁决（并发删除 → 404 渲染）；
 * - 失败按 error.code（必要时结合 details[].code / details[].field）分支渲染
 *   固定文案（不解析 message）：VALIDATION_ERROR → 字段级提示（含
 *   carriers / carriers.<i>.* 嵌套路径与重复载体 DUPLICATE）；NOT_FOUND →
 *   create：「请检查载体类型与载体 ID」（任一载体无效，整请求失败，契约
 *   §4.1）；CONFLICT + details[].code === 'DUPLICATE'（field === 'name'）→
 *   「已存在活跃的同名 Service」（唯一性边界是全局，R-SVC-008，与
 *   Container 的载体内唯一对照，不得混用）；401 交由既有全局会话失效
 *   处理；提交中 Loading 且禁止重复提交；
 * - 6 字段输入为空 → 提交 null（清空 / 保持为 null，契约 §4.1 / §4.4）。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** create 模式：预选的载体集合（可增删改）；edit 模式忽略。 */
  presetCarriers?: ServiceCarrier[] | null
  /** edit 模式：当前 Service（表单初值）；create 模式忽略。 */
  service?: ServiceRead | null
}>()

const emit = defineEmits<{
  /** 登记或更新成功，携带服务端返回的 ServiceRead。 */
  success: [service: ServiceRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

const OPTIONAL_FIELD_DEFS: ReadonlyArray<{
  key: ServiceOptionalField
  label: string
  placeholder: string
  textarea?: boolean
}> = [
  { key: 'service_type', label: '服务类型', placeholder: '可选，纯文本' },
  { key: 'url', label: 'URL', placeholder: '可选，纯文本，不校验格式' },
  { key: 'port', label: '端口', placeholder: '可选，纯文本，不校验数字' },
  { key: 'protocol', label: '协议', placeholder: '可选，纯文本' },
  { key: 'owner', label: '负责人', placeholder: '可选，纯文本' },
  { key: 'description', label: '描述', placeholder: '可选，纯文本，可含换行', textarea: true },
]

/** 载体行（表单态）：类型与 ID 均填写才算一条完整载体。 */
interface CarrierRow {
  carrierType: ServiceCarrierType | null
  carrierId: number | null
}

interface ServiceFormState {
  name: string
  carrierRows: CarrierRow[]
  optional: Record<ServiceOptionalField, string>
}

function emptyOptional(): Record<ServiceOptionalField, string> {
  return {
    service_type: '',
    url: '',
    port: '',
    protocol: '',
    owner: '',
    description: '',
  }
}

const form = reactive<ServiceFormState>({
  name: '',
  carrierRows: [],
  optional: emptyOptional(),
})

const dialogTitle = computed(() => (props.mode === 'create' ? '登记服务' : '编辑服务'))
const submitLabel = computed(() => (props.mode === 'create' ? '登记' : '保存'))

// ---- 打开时初始化表单 ----

watch(
  dialogVisible,
  (open) => {
    if (!open) return
    failure.value = null
    if (props.mode === 'edit' && props.service !== null && props.service !== undefined) {
      form.name = props.service.name
      form.carrierRows = []
      for (const field of SERVICE_OPTIONAL_FIELDS) {
        form.optional[field] = props.service[field] ?? ''
      }
    } else {
      form.name = ''
      // 预选载体集合（如从列表载体筛选 / 详情页进入）逐行复制；无预选时
      // 提供一条空行（用户填写或删除；提交仍受「至少一项完整载体」约束）。
      form.carrierRows =
        props.presetCarriers !== null && props.presetCarriers !== undefined
          ? props.presetCarriers.map((carrier) => ({
              carrierType: carrier.carrier_type,
              carrierId: carrier.carrier_id,
            }))
          : [{ carrierType: null, carrierId: null }]
      form.optional = emptyOptional()
    }
  },
  { immediate: true },
)

// ---- 多载体行编辑 ----

/** 追加一条空载体行（类型 / ID 未填，提交按钮相应禁用，见头注）。 */
function addCarrierRow(): void {
  form.carrierRows.push({ carrierType: null, carrierId: null })
}

/** 删除指定载体行；行数可为 0（提交按钮因「至少一项载体」禁用）。 */
function removeCarrierRow(index: number): void {
  form.carrierRows.splice(index, 1)
}

// ---- 提交 ----

const submitting = ref(false)
const failure = ref<ApiError | null>(null)

/**
 * create 模式的表单完整性约束（R-SVC-005）：至少一条载体行，且每行
 * 类型与 ID 均已填写（不完整的载体无法按契约表达）；这不是业务守卫
 * （见头注）。edit 模式无需填写载体。
 */
const submitDisabled = computed(
  () =>
    props.mode === 'create' &&
    (form.carrierRows.length === 0 ||
      form.carrierRows.some((row) => row.carrierType === null || row.carrierId === null)),
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
      // create：任一载体不存在 / 已逻辑删除 / 类型与标识不一致（契约 §4.1，
      // 整请求失败，三者不区分）；edit：目标 Service 不存在或已被逻辑删除
      // （契约 §4.4）。
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
            description: '该服务不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
    case 'CONFLICT': {
      // 契约 §5.1：稳定判别值为 details[].field === 'name' +
      // details[].code === 'DUPLICATE'（全局活跃重名，R-SVC-008）。
      const duplicateName = error.details.some(
        (detail) => detail.field === 'name' && detail.code === 'DUPLICATE',
      )
      return duplicateName
        ? {
            code: error.code,
            title: '无法登记',
            description: '已存在活跃的同名服务（服务名称全局唯一、区分大小写）。',
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

/** 组装 6 个可选字段请求体：输入为空 → null（清空 / 保持 null）。 */
function optionalBody(): Record<ServiceOptionalField, string | null> {
  const body = {} as Record<ServiceOptionalField, string | null>
  for (const field of SERVICE_OPTIONAL_FIELDS) {
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
    let saved: ServiceRead
    if (props.mode === 'create') {
      // submitDisabled 已保证 create 模式下载体行均完整且非空；此处再显式兜底。
      const carriers: ServiceCarrier[] = []
      for (const row of form.carrierRows) {
        if (row.carrierType === null || row.carrierId === null) return
        carriers.push({ carrier_type: row.carrierType, carrier_id: row.carrierId })
      }
      if (carriers.length === 0) return
      // name 原样提交：不校验、不变换（契约 §8）；空串 / 首尾空白等未定义
      // 约束由服务端裁决，前端不编写业务分支（§21）。重复载体不去重、
      // 不预判（契约 §4.1：同一请求内重复载体 → 400，服务端裁决）。
      saved = await createService({
        name: form.name,
        carriers,
        ...optionalBody(),
      })
    } else {
      const target = props.service
      if (target === null || target === undefined) return
      saved = await updateService(target.id, optionalBody())
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
    width="560px"
  >
    <!-- 提交失败提示：按 error.code 生成固定文案，可关闭；message 不参与分支。 -->
    <el-alert
      v-if="failureView !== null"
      class="service-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="service-form__failure-details">
        <p v-for="(detail, index) in failureView.details" :key="index">
          <el-tag size="small" type="danger">
            {{ detail.field ?? detail.code ?? '字段' }}
          </el-tag>
          <span v-if="detail.message">{{ detail.message }}</span>
        </p>
      </div>
    </el-alert>

    <el-form label-width="90px">
      <!-- create：name。不做任何长度 / 空串 / 字符 / 格式校验（契约 §8 未定义约束；
           是否要求非空由服务端裁决，前端不编写业务分支）。 -->
      <el-form-item v-if="mode === 'create'" label="名称">
        <el-input
          v-model="form.name"
          placeholder="全局唯一（由服务端校验）"
          data-testid="service-form-name"
        />
      </el-form-item>

      <!-- create：多载体选择（三种载体类型，契约 §2 封闭三值；可多选，至少
           一项才能提交，R-SVC-005）。载体存在性 / 活跃性 / 类型一致性由
           服务端裁决（404 → 固定文案）；同一载体重复给出不去重（服务端 400）。 -->
      <el-form-item v-if="mode === 'create'" label="运行载体">
        <div class="service-form__carriers">
          <div
            v-for="(row, index) in form.carrierRows"
            :key="index"
            class="service-form__carrier-row"
            :data-testid="`service-form-carrier-row-${index}`"
          >
            <el-select
              v-model="row.carrierType"
              class="service-form__carrier-type"
              placeholder="载体类型"
              data-testid="service-form-carrier-type"
            >
              <el-option
                v-for="carrierType in SERVICE_CARRIER_TYPES"
                :key="carrierType"
                :label="carrierType"
                :value="carrierType"
              />
            </el-select>
            <el-input-number
              v-model="row.carrierId"
              class="service-form__carrier-id"
              placeholder="载体 ID"
              :controls="false"
              data-testid="service-form-carrier-id"
            />
            <el-button
              link
              type="danger"
              data-testid="service-form-remove-carrier"
              @click="removeCarrierRow(index)"
            >
              移除
            </el-button>
          </div>
          <el-button
            plain
            size="small"
            data-testid="service-form-add-carrier"
            @click="addCarrierRow"
          >
            添加载体
          </el-button>
        </div>
      </el-form-item>

      <!-- 6 个可选字段：可选、纯文本；输入为空提交 null（清空）。 -->
      <el-form-item
        v-for="field in OPTIONAL_FIELD_DEFS"
        :key="field.key"
        :label="field.label"
      >
        <el-input
          v-model="form.optional[field.key]"
          :placeholder="field.placeholder"
          :type="field.textarea === true ? 'textarea' : 'text'"
          :rows="field.textarea === true ? 2 : undefined"
          :data-testid="`service-form-${field.key}`"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="service-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.service-form__failure {
  margin-bottom: 16px;
}

.service-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.service-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.service-form__carriers {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.service-form__carrier-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.service-form__carrier-type {
  width: 180px;
}

.service-form__carrier-id {
  flex: 1;
}
</style>
