<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import { listBareMetals } from '../api/bareMetals'
import type { BareMetalRead } from '../api/bareMetals'
import {
  PURPOSE_OPTIONS,
  TECHNOLOGY_TYPE_OPTIONS,
  createNetworkInterface,
  updateNetworkInterface,
} from '../api/networkInterfaces'
import type {
  NetworkInterfacePurpose,
  NetworkInterfaceRead,
  NetworkInterfaceTechnologyType,
} from '../api/networkInterfaces'

/**
 * 网络接口登记 / 编辑对话框（契约 docs/api/f004-network-interface.md §3.1 / §3.4）。
 *
 * - create 模式：宿主裸金属（下拉，选项来自既有 GET /api/bare-metals）+ name +
 *   两个枚举下拉（technology_type / purpose）→ POST /api/network-interfaces；
 * - edit 模式：仅两个枚举下拉 → PATCH；name / bare_metal_id 不在 PATCH 可变集内
 *   （契约 §3.4 / NQ-3，登记后不可变），表单不提供其输入；
 * - 前端不重复实现业务守卫（§21）：枚举封闭集合（400）、宿主存在性 / 活跃性
 *   （404）一律由服务端裁决，本表单不预判、不拦截；name 不做任何长度 / 空串 /
 *   字符校验（契约 §7 undefined_constraints，前端不得基于未定义项编写业务分支），
 *   也不做唯一性预检（NQ-2 未确认，契约不存在 409 DUPLICATE 分支）；
 * - 枚举选项常量（TECHNOLOGY_TYPE_OPTIONS / PURPOSE_OPTIONS）仅用于下拉渲染，
 *   不作为业务校验依据；下拉未选择（表单未完成）时提交按钮禁用 —— 这不是
 *   枚举合法性预判：任何已选择的值都直接提交，由服务端裁决；宿主未选择同理；
 * - 失败按 error.code 分支渲染固定文案（不解析 message）；VALIDATION_ERROR
 *   展示 details[].field 字段级提示；401 交由既有全局会话失效处理；
 *   提交中 Loading 且禁止重复提交。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** create 模式：预选的宿主裸金属 id（可改选）；edit 模式忽略。 */
  presetBareMetalId?: number | null
  /** edit 模式：当前 NetworkInterface（表单初值）；create 模式忽略。 */
  networkInterface?: NetworkInterfaceRead | null
}>()

const emit = defineEmits<{
  /** 登记或更新成功，携带服务端返回的 NetworkInterfaceRead。 */
  success: [networkInterface: NetworkInterfaceRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

interface NetworkInterfaceFormState {
  bareMetalId: number | null
  name: string
  technologyType: NetworkInterfaceTechnologyType | null
  purpose: NetworkInterfacePurpose | null
}

const form = reactive<NetworkInterfaceFormState>({
  bareMetalId: null,
  name: '',
  technologyType: null,
  purpose: null,
})

const dialogTitle = computed(() =>
  props.mode === 'create' ? '登记网络接口' : '编辑网络接口',
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
    if (
      props.mode === 'edit' &&
      props.networkInterface !== null &&
      props.networkInterface !== undefined
    ) {
      form.bareMetalId = props.networkInterface.bare_metal_id
      form.name = props.networkInterface.name
      form.technologyType = props.networkInterface.technology_type
      form.purpose = props.networkInterface.purpose
    } else {
      form.bareMetalId = props.presetBareMetalId ?? null
      form.name = ''
      form.technologyType = null
      form.purpose = null
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

/**
 * create 模式下宿主或枚举未选择 → 表单未完成，提交按钮禁用（非业务守卫，
 * 见头注）。edit 模式初值来自当前记录（枚举永不为 null），不额外限制。
 */
const submitDisabled = computed(
  () =>
    props.mode === 'create' &&
    (form.bareMetalId === null || form.technologyType === null || form.purpose === null),
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
      // 契约 §3.1 / §3.4：字段级提示（details[].field，如 name /
      // technology_type / purpose / bare_metal_id / 未识别字段名）。
      return {
        code: error.code,
        title: '请求校验失败',
        description: '提交的内容不符合要求，请根据下方字段提示修改后重试。',
        details: error.details,
      }
    case 'NOT_FOUND':
      // create：宿主 BareMetal 不存在或已逻辑删除（契约 §3.1 / NQ-5）；
      // edit：目标 NetworkInterface 不存在或已被逻辑删除（契约 §3.4，两者不区分）。
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
            description: '该网络接口不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
    case 'CONFLICT':
      // 契约 §4.2：NetworkInterface 无唯一性规则，不存在 409 DUPLICATE 分支；
      // 不为 CONFLICT 编写唯一性文案，按通用冲突渲染（FK 违规的 409 REFERENCE
      // 映射路径在产品路径下不可达，契约 §4.2 补充）。
      return {
        code: error.code,
        title: '数据冲突',
        description: '保存的内容与现有数据冲突，请稍后重试。',
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
  if (submitting.value || submitDisabled.value) return
  submitting.value = true
  failure.value = null
  try {
    let saved: NetworkInterfaceRead
    if (props.mode === 'create') {
      // submitDisabled 已保证 create 模式下宿主与两个枚举均已选择；此处再显式兜底。
      const bareMetalId = form.bareMetalId
      const technologyType = form.technologyType
      const purpose = form.purpose
      if (bareMetalId === null || technologyType === null || purpose === null) return
      saved = await createNetworkInterface({
        bare_metal_id: bareMetalId,
        name: form.name,
        technology_type: technologyType,
        purpose,
      })
    } else {
      const target = props.networkInterface
      if (target === null || target === undefined) return
      // edit 模式表单初值来自当前记录，两个枚举必有值；此处再显式兜底。
      const technologyType = form.technologyType
      const purpose = form.purpose
      if (technologyType === null || purpose === null) return
      // PATCH 可变字段封闭为两个枚举（契约 §3.4 / NQ-7）；快照式提交两字段。
      saved = await updateNetworkInterface(target.id, {
        technology_type: technologyType,
        purpose,
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
      class="network-interface-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="network-interface-form__failure-details">
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
          class="network-interface-form__host-select"
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
        <div v-if="hostOptionsError !== null" class="network-interface-form__hint">
          裸金属列表加载失败（{{ hostOptionsError.code }}）。
          <el-button link type="primary" @click="loadHostOptions">重试</el-button>
        </div>
        <div
          v-else-if="!hostOptionsLoading && hostOptions.length === 0"
          class="network-interface-form__hint"
        >
          暂无可选裸金属：网络接口必须属于一个宿主裸金属（R-NIC-003），请先登记裸金属。
        </div>
      </el-form-item>

      <!-- create：name。不做任何长度 / 空串 / 字符校验（契约 §7 未定义约束），
           也不做唯一性预检（NQ-2 未确认）。 -->
      <el-form-item v-if="mode === 'create'" label="名称">
        <el-input
          v-model="form.name"
          placeholder="如 eth0 / ib0"
          data-testid="nic-form-name"
        />
      </el-form-item>

      <!-- 技术类型（R-NIC-001 封闭集合；选项仅用于下拉渲染，合法性由服务端裁决）。 -->
      <el-form-item label="技术类型">
        <el-select
          v-model="form.technologyType"
          placeholder="请选择技术类型"
          data-testid="nic-form-technology-type"
        >
          <el-option
            v-for="technologyType in TECHNOLOGY_TYPE_OPTIONS"
            :key="technologyType"
            :label="technologyType"
            :value="technologyType"
          />
        </el-select>
      </el-form-item>

      <!-- 用途（R-NIC-002 封闭集合；选项仅用于下拉渲染，合法性由服务端裁决）。 -->
      <el-form-item label="用途">
        <el-select
          v-model="form.purpose"
          placeholder="请选择用途"
          data-testid="nic-form-purpose"
        >
          <el-option
            v-for="purpose in PURPOSE_OPTIONS"
            :key="purpose"
            :label="purpose"
            :value="purpose"
          />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="nic-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.network-interface-form__hint {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}

.network-interface-form__failure {
  margin-bottom: 16px;
}

.network-interface-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.network-interface-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
