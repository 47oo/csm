<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import { listClusters } from '../api/clusters'
import type { ClusterRead } from '../api/clusters'
import {
  BARE_METAL_HARDWARE_FIELDS,
  BARE_METAL_STATUS_VALUES,
  createBareMetal,
  updateBareMetal,
} from '../api/bareMetals'
import type {
  BareMetalHardwareField,
  BareMetalRead,
  BareMetalStatus,
} from '../api/bareMetals'

/**
 * 裸金属登记 / 编辑对话框（契约 docs/api/f002-bare-metal.md §3.1 / §3.4）。
 *
 * - create 模式：所属集群（下拉，选项来自 GET /api/clusters）+ hostname +
 *   R-BM-007 七字段（可选）→ POST /api/bare-metals；
 * - edit 模式：status（封闭集合下拉）+ R-BM-007 七字段 → PATCH；hostname /
 *   cluster_id 不在 PATCH 可变集内（契约 §3.4），表单不提供其输入；
 * - 前端不重复实现业务守卫（§21）：同 Cluster hostname 唯一（409）、父 Cluster
 *   存在性 / 活跃性（404）、状态封闭集合（400）一律由服务端裁决，本表单不预判、
 *   不拦截；hostname 不做任何长度 / 空串 / 字符校验（契约 §7 undefined_constraints，
 *   前端不得基于未定义项编写业务分支）；
 * - 所属集群未选择（表单未完成）时提交按钮禁用 —— 这不是父存在性预判：任何
 *   已选择的集群都直接提交，由服务端裁决（并发删除 → 404 渲染）；
 * - 失败按 error.code 分支渲染固定文案（不解析 message）；401 交由既有全局
 *   会话失效处理；提交中 Loading 且禁止重复提交；
 * - 硬件字段输入为空 → 提交 null（清空 / 保持为 null，契约 §3.4）；登记时
 *   status 不提供输入，走服务端默认 IDLE（R-BM-004；显式指定属 NQ-3 未确认）。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** create 模式：预选的所属集群 id（可改选）；edit 模式忽略。 */
  presetClusterId?: number | null
  /** edit 模式：当前 BareMetal（表单初值）；create 模式忽略。 */
  bareMetal?: BareMetalRead | null
}>()

const emit = defineEmits<{
  /** 登记或更新成功，携带服务端返回的 BareMetalRead。 */
  success: [bareMetal: BareMetalRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

const HARDWARE_FIELD_DEFS: ReadonlyArray<{
  key: BareMetalHardwareField
  label: string
  placeholder: string
}> = [
  { key: 'vendor', label: '厂商', placeholder: '可选，纯文本' },
  { key: 'model', label: '型号', placeholder: '可选，纯文本' },
  { key: 'serial_number', label: '序列号', placeholder: '可选，不参与唯一性' },
  { key: 'cpu', label: 'CPU', placeholder: '可选，纯文本' },
  { key: 'memory', label: '内存', placeholder: '可选，纯文本' },
  { key: 'gpu', label: 'GPU', placeholder: '可选，纯文本' },
  { key: 'storage', label: '存储', placeholder: '可选，纯文本' },
]

interface BareMetalFormState {
  clusterId: number | null
  hostname: string
  status: BareMetalStatus
  hardware: Record<BareMetalHardwareField, string>
}

function emptyHardware(): Record<BareMetalHardwareField, string> {
  return { vendor: '', model: '', serial_number: '', cpu: '', memory: '', gpu: '', storage: '' }
}

const form = reactive<BareMetalFormState>({
  clusterId: null,
  hostname: '',
  status: 'IDLE',
  hardware: emptyHardware(),
})

const dialogTitle = computed(() =>
  props.mode === 'create' ? '登记裸金属' : '编辑裸金属',
)
const submitLabel = computed(() => (props.mode === 'create' ? '登记' : '保存'))

// ---- 所属集群选项（仅 create 模式加载） ----

const clusterOptions = ref<ClusterRead[]>([])
const clusterOptionsLoading = ref(false)
const clusterOptionsError = ref<ApiError | null>(null)

/** 拉取集群选项。page_size 取契约上限 200（V1 内部规模下的最小实现）。 */
async function loadClusterOptions(): Promise<void> {
  clusterOptionsLoading.value = true
  clusterOptionsError.value = null
  try {
    const data = await listClusters({ page: 1, page_size: 200 })
    clusterOptions.value = data.items
  } catch (err) {
    clusterOptions.value = []
    clusterOptionsError.value =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
  } finally {
    clusterOptionsLoading.value = false
  }
}

// ---- 打开时初始化表单 ----

watch(
  dialogVisible,
  (open) => {
    if (!open) return
    failure.value = null
    if (props.mode === 'edit' && props.bareMetal !== null && props.bareMetal !== undefined) {
      form.clusterId = props.bareMetal.cluster_id
      form.hostname = props.bareMetal.hostname
      form.status = props.bareMetal.status
      for (const field of BARE_METAL_HARDWARE_FIELDS) {
        form.hardware[field] = props.bareMetal[field] ?? ''
      }
    } else {
      form.clusterId = props.presetClusterId ?? null
      form.hostname = ''
      form.status = 'IDLE'
      form.hardware = emptyHardware()
    }
    if (props.mode === 'create') {
      void loadClusterOptions()
    }
  },
  { immediate: true },
)

// ---- 提交 ----

const submitting = ref(false)
const failure = ref<ApiError | null>(null)

/** create 模式下所属集群未选择 → 表单未完成，提交按钮禁用（非业务守卫，见头注）。 */
const submitDisabled = computed(() => props.mode === 'create' && form.clusterId === null)

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
      // create：父 Cluster 不存在或已逻辑删除（契约 §3.1 / NQ-2）；
      // edit：目标 BareMetal 不存在或已被逻辑删除（契约 §3.4，两者不区分）。
      return props.mode === 'create'
        ? {
            code: error.code,
            title: '无法登记',
            description: '所选集群不存在或已被删除，请重新选择后重试。',
            details: [],
          }
        : {
            code: error.code,
            title: '无法保存',
            description: '该裸金属不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
    case 'CONFLICT': {
      // 契约 §4.1：稳定判别值为 details[].field === 'hostname' +
      // details[].code === 'DUPLICATE'（同 Cluster 活跃重名）。
      const duplicateHostname = error.details.some(
        (detail) => detail.field === 'hostname' && detail.code === 'DUPLICATE',
      )
      return duplicateHostname
        ? {
            code: error.code,
            title: '无法登记',
            description: '同一集群内已存在同名的 hostname。',
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

/** 组装 R-BM-007 七字段请求体：输入为空 → null（清空 / 保持 null）。 */
function hardwareBody(): Record<BareMetalHardwareField, string | null> {
  const body = {} as Record<BareMetalHardwareField, string | null>
  for (const field of BARE_METAL_HARDWARE_FIELDS) {
    const value = form.hardware[field]
    body[field] = value === '' ? null : value
  }
  return body
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || submitDisabled.value) return
  submitting.value = true
  failure.value = null
  try {
    let saved: BareMetalRead
    if (props.mode === 'create') {
      // submitDisabled 已保证 create 模式下已选择集群；此处再显式兜底。
      const clusterId = form.clusterId
      if (clusterId === null) return
      saved = await createBareMetal({
        cluster_id: clusterId,
        hostname: form.hostname,
        ...hardwareBody(),
      })
    } else {
      const target = props.bareMetal
      if (target === null || target === undefined) return
      saved = await updateBareMetal(target.id, {
        status: form.status,
        ...hardwareBody(),
      })
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
      class="bare-metal-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="bare-metal-form__failure-details">
        <p v-for="(detail, index) in failureView.details" :key="index">
          <el-tag size="small" type="danger">
            {{ detail.field ?? detail.code ?? '字段' }}
          </el-tag>
          <span v-if="detail.message">{{ detail.message }}</span>
        </p>
      </div>
    </el-alert>

    <el-form label-width="90px">
      <!-- create：所属集群（下拉选项来自 GET /api/clusters，父存在性由服务端裁决）。 -->
      <el-form-item v-if="mode === 'create'" label="所属集群">
        <el-select
          v-model="form.clusterId"
          class="bare-metal-form__cluster-select"
          placeholder="请选择所属集群"
          :loading="clusterOptionsLoading"
        >
          <el-option
            v-for="cluster in clusterOptions"
            :key="cluster.id"
            :label="cluster.name"
            :value="cluster.id"
          />
        </el-select>
        <div v-if="clusterOptionsError !== null" class="bare-metal-form__hint">
          集群列表加载失败（{{ clusterOptionsError.code }}）。
          <el-button link type="primary" @click="loadClusterOptions">重试</el-button>
        </div>
        <div
          v-else-if="!clusterOptionsLoading && clusterOptions.length === 0"
          class="bare-metal-form__hint"
        >
          暂无可选集群：裸金属必须属于一个集群（R-BM-001），请先登记集群。
        </div>
      </el-form-item>

      <!-- create：hostname。不做任何长度 / 空串 / 字符校验（契约 §7 未定义约束）。 -->
      <el-form-item v-if="mode === 'create'" label="hostname">
        <el-input
          v-model="form.hostname"
          placeholder="同集群内唯一（由服务端校验）"
          data-testid="bare-metal-form-hostname"
        />
      </el-form-item>

      <!-- edit：状态（R-BM-003 封闭集合；取值合法性由服务端裁决）。 -->
      <el-form-item v-if="mode === 'edit'" label="状态">
        <el-select v-model="form.status" class="bare-metal-form__status-select">
          <el-option
            v-for="status in BARE_METAL_STATUS_VALUES"
            :key="status"
            :label="status"
            :value="status"
          />
        </el-select>
      </el-form-item>

      <!-- R-BM-007 硬件字段：可选、纯文本；输入为空提交 null（清空）。 -->
      <el-form-item
        v-for="field in HARDWARE_FIELD_DEFS"
        :key="field.key"
        :label="field.label"
      >
        <el-input
          v-model="form.hardware[field.key]"
          :placeholder="field.placeholder"
          :data-testid="`bare-metal-form-${field.key}`"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="bare-metal-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.bare-metal-form__control {
  width: 100%;
}

.bare-metal-form__hint {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}

.bare-metal-form__failure {
  margin-bottom: 16px;
}

.bare-metal-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.bare-metal-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
