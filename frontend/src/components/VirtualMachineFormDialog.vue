<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import { listBareMetals } from '../api/bareMetals'
import type { BareMetalRead } from '../api/bareMetals'
import {
  VIRTUAL_MACHINE_OPTIONAL_FIELDS,
  createVirtualMachine,
  updateVirtualMachine,
} from '../api/virtualMachines'
import type {
  VirtualMachineOptionalField,
  VirtualMachineRead,
} from '../api/virtualMachines'

/**
 * 虚拟机登记 / 编辑对话框（契约 docs/api/f006-virtual-machine.md §3.1 / §3.4）。
 *
 * - create 模式：宿主裸金属（下拉，选项来自既有 GET /api/bare-metals）+ name +
 *   R-VM-006 六字段（可选）→ POST /api/virtual-machines；
 * - edit 模式：R-VM-006 六字段 → PATCH；name / bare_metal_id 不在 PATCH 可变集内
 *   （契约 §3.4 / NQ-1，登记后不可变），表单不提供其输入；
 * - 前端不重复实现业务守卫（§21）：全局 name 唯一（409）、宿主存在性 / 活跃性
 *   （404）一律由服务端裁决，本表单不预判、不拦截；name 不做任何长度 / 空串 /
 *   字符校验（契约 §7 undefined_constraints，前端不得基于未定义项编写业务分支）；
 * - 宿主裸金属未选择（表单未完成）时提交按钮禁用 —— 这不是宿主存在性预判：
 *   任何已选择的宿主都直接提交，由服务端裁决（并发删除 → 404 渲染）；
 * - 失败按 error.code 分支渲染固定文案（不解析 message）；401 交由既有全局
 *   会话失效处理；提交中 Loading 且禁止重复提交；
 * - 六字段输入为空 → 提交 null（清空 / 保持为 null，契约 §3.4）。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** create 模式：预选的宿主裸金属 id（可改选）；edit 模式忽略。 */
  presetBareMetalId?: number | null
  /** edit 模式：当前 VirtualMachine（表单初值）；create 模式忽略。 */
  virtualMachine?: VirtualMachineRead | null
}>()

const emit = defineEmits<{
  /** 登记或更新成功，携带服务端返回的 VirtualMachineRead。 */
  success: [virtualMachine: VirtualMachineRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

const OPTIONAL_FIELD_DEFS: ReadonlyArray<{
  key: VirtualMachineOptionalField
  label: string
  placeholder: string
}> = [
  { key: 'cpu', label: 'CPU', placeholder: '可选，纯文本' },
  { key: 'memory', label: '内存', placeholder: '可选，纯文本' },
  { key: 'disk', label: '磁盘', placeholder: '可选，纯文本' },
  { key: 'os', label: '操作系统', placeholder: '可选，纯文本' },
  { key: 'hypervisor', label: 'Hypervisor', placeholder: '可选，纯文本登记字段' },
  { key: 'owner', label: '负责人', placeholder: '可选，纯文本' },
]

interface VirtualMachineFormState {
  bareMetalId: number | null
  name: string
  optional: Record<VirtualMachineOptionalField, string>
}

function emptyOptional(): Record<VirtualMachineOptionalField, string> {
  return { cpu: '', memory: '', disk: '', os: '', hypervisor: '', owner: '' }
}

const form = reactive<VirtualMachineFormState>({
  bareMetalId: null,
  name: '',
  optional: emptyOptional(),
})

const dialogTitle = computed(() =>
  props.mode === 'create' ? '登记虚拟机' : '编辑虚拟机',
)
const submitLabel = computed(() => (props.mode === 'create' ? '登记' : '保存'))

// ---- 宿主裸金属选项（仅 create 模式加载） ----

const hostOptions = ref<BareMetalRead[]>([])
const hostOptionsLoading = ref(false)
const hostOptionsError = ref<ApiError | null>(null)

/** 拉取宿主裸金属选项。page_size 取契约上限 200（V1 内部规模下的最小实现）。 */
async function loadHostOptions(): Promise<void> {
  hostOptionsLoading.value = true
  hostOptionsError.value = null
  try {
    const data = await listBareMetals({ page: 1, page_size: 200 })
    hostOptions.value = data.items
  } catch (err) {
    hostOptions.value = []
    hostOptionsError.value =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
  } finally {
    hostOptionsLoading.value = false
  }
}

// ---- 打开时初始化表单 ----

watch(
  dialogVisible,
  (open) => {
    if (!open) return
    failure.value = null
    if (props.mode === 'edit' && props.virtualMachine !== null && props.virtualMachine !== undefined) {
      form.bareMetalId = props.virtualMachine.bare_metal_id
      form.name = props.virtualMachine.name
      for (const field of VIRTUAL_MACHINE_OPTIONAL_FIELDS) {
        form.optional[field] = props.virtualMachine[field] ?? ''
      }
    } else {
      form.bareMetalId = props.presetBareMetalId ?? null
      form.name = ''
      form.optional = emptyOptional()
    }
    if (props.mode === 'create') {
      void loadHostOptions()
    }
  },
  { immediate: true },
)

// ---- 提交 ----

const submitting = ref(false)
const failure = ref<ApiError | null>(null)

/** create 模式下宿主未选择 → 表单未完成，提交按钮禁用（非业务守卫，见头注）。 */
const submitDisabled = computed(() => props.mode === 'create' && form.bareMetalId === null)

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
      // create：宿主 BareMetal 不存在或已逻辑删除（契约 §3.1 / NQ-2）；
      // edit：目标 VirtualMachine 不存在或已被逻辑删除（契约 §3.4，两者不区分）。
      return props.mode === 'create'
        ? {
            code: error.code,
            title: '无法登记',
            description: '所选宿主裸金属不存在或已被删除，请重新选择后重试。',
            details: [],
          }
        : {
            code: error.code,
            title: '无法保存',
            description: '该虚拟机不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
    case 'CONFLICT': {
      // 契约 §4.1：稳定判别值为 details[].field === 'name' +
      // details[].code === 'DUPLICATE'（全局活跃重名，跨宿主跨 Cluster）。
      const duplicateName = error.details.some(
        (detail) => detail.field === 'name' && detail.code === 'DUPLICATE',
      )
      return duplicateName
        ? {
            code: error.code,
            title: '无法登记',
            description: '已存在同名的活跃虚拟机（名称全局唯一，不区分宿主与集群）。',
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

/** 组装 R-VM-006 六字段请求体：输入为空 → null（清空 / 保持 null）。 */
function optionalBody(): Record<VirtualMachineOptionalField, string | null> {
  const body = {} as Record<VirtualMachineOptionalField, string | null>
  for (const field of VIRTUAL_MACHINE_OPTIONAL_FIELDS) {
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
    let saved: VirtualMachineRead
    if (props.mode === 'create') {
      // submitDisabled 已保证 create 模式下已选择宿主；此处再显式兜底。
      const bareMetalId = form.bareMetalId
      if (bareMetalId === null) return
      saved = await createVirtualMachine({
        bare_metal_id: bareMetalId,
        name: form.name,
        ...optionalBody(),
      })
    } else {
      const target = props.virtualMachine
      if (target === null || target === undefined) return
      saved = await updateVirtualMachine(target.id, optionalBody())
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
      class="virtual-machine-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="virtual-machine-form__failure-details">
        <p v-for="(detail, index) in failureView.details" :key="index">
          <el-tag size="small" type="danger">
            {{ detail.field ?? detail.code ?? '字段' }}
          </el-tag>
          <span v-if="detail.message">{{ detail.message }}</span>
        </p>
      </div>
    </el-alert>

    <el-form label-width="90px">
      <!-- create：宿主裸金属（下拉选项来自 GET /api/bare-metals，父存在性由服务端裁决）。
           hostname 仅在同 Cluster 内唯一，选项附带集群 ID 辅助区分。 -->
      <el-form-item v-if="mode === 'create'" label="宿主裸金属">
        <el-select
          v-model="form.bareMetalId"
          class="virtual-machine-form__host-select"
          placeholder="请选择宿主裸金属"
          :loading="hostOptionsLoading"
        >
          <el-option
            v-for="host in hostOptions"
            :key="host.id"
            :label="`${host.hostname}（集群 #${host.cluster_id}）`"
            :value="host.id"
          />
        </el-select>
        <div v-if="hostOptionsError !== null" class="virtual-machine-form__hint">
          裸金属列表加载失败（{{ hostOptionsError.code }}）。
          <el-button link type="primary" @click="loadHostOptions">重试</el-button>
        </div>
        <div
          v-else-if="!hostOptionsLoading && hostOptions.length === 0"
          class="virtual-machine-form__hint"
        >
          暂无可选裸金属：虚拟机必须属于一个宿主裸金属（R-VM-005），请先登记裸金属。
        </div>
      </el-form-item>

      <!-- create：name。不做任何长度 / 空串 / 字符校验（契约 §7 未定义约束）。 -->
      <el-form-item v-if="mode === 'create'" label="名称">
        <el-input
          v-model="form.name"
          placeholder="全局唯一（由服务端校验）"
          data-testid="vm-form-name"
        />
      </el-form-item>

      <!-- R-VM-006 六字段：可选、纯文本；输入为空提交 null（清空）。 -->
      <el-form-item
        v-for="field in OPTIONAL_FIELD_DEFS"
        :key="field.key"
        :label="field.label"
      >
        <el-input
          v-model="form.optional[field.key]"
          :placeholder="field.placeholder"
          :data-testid="`vm-form-${field.key}`"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="vm-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.virtual-machine-form__hint {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}

.virtual-machine-form__failure {
  margin-bottom: 16px;
}

.virtual-machine-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.virtual-machine-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
