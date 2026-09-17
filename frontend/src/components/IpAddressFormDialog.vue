<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import { listNetworkInterfaces } from '../api/networkInterfaces'
import type { NetworkInterfaceRead } from '../api/networkInterfaces'
import { createIpAddress, updateIpAddress } from '../api/ipAddresses'
import type { IpAddressRead } from '../api/ipAddresses'

/**
 * IP 地址登记 / 编辑对话框（契约 docs/api/f005-ip-address.md §3.1 / §3.4）。
 *
 * - create 模式：所属网络接口（下拉，选项来自既有 GET /api/network-interfaces，
 *   F004 契约 §3.2）+ ip_address 文本输入 → POST /api/ip-addresses；若从
 *   NIC 详情 / NIC 过滤列表进入则预选该网络接口（可改选）；
 * - edit 模式：仅 ip_address 文本输入 → PATCH /api/ip-addresses/{id}；
 *   network_interface_id / id / created_at 不在 PATCH 可变集内（契约 §3.4），
 *   表单不提供其输入；
 * - 前端不重复实现业务守卫（§21）：ip_address 不做任何长度 / 空白 / 空串 /
 *   格式 / 正则校验，也不做去除空白 / 归一化 / 大小写折叠（契约 §7
 *   undefined_constraints，前端不得基于未定义项编写业务分支）；同 Cluster
 *   唯一性（409 CONFLICT + details[].code === 'DUPLICATE'）与父 NIC 存在性 /
 *   活跃性（404）一律由服务端裁决，本表单不预判、不拦截、不回填任何
 *   Cluster 归属、不禁用提交；
 * - 网络接口未选择（表单未完成）时提交按钮禁用 —— 这不是父存在性预判：
 *   任何已选择的值都直接提交，由服务端裁决；
 * - 失败按 error.code（必要时结合 details[].code / details[].field）分支渲染
 *   固定文案（不解析 message）：VALIDATION_ERROR → 字段级提示；
 *   NOT_FOUND → create：「请检查所选网络接口」；CONFLICT +
 *   details[].code === 'DUPLICATE' → 「该 IP 在所属 Cluster 内已被占用」；
 *   401 交由既有全局会话失效处理；提交中 Loading 且禁止重复提交。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** create 模式：预选的父网络接口 id（可改选）；edit 模式忽略。 */
  presetNetworkInterfaceId?: number | null
  /** edit 模式：当前 IPAddress（表单初值）；create 模式忽略。 */
  ipAddress?: IpAddressRead | null
}>()

const emit = defineEmits<{
  /** 登记或修正成功，携带服务端返回的 IpAddressRead。 */
  success: [ipAddress: IpAddressRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

interface IpAddressFormState {
  networkInterfaceId: number | null
  ipAddress: string
}

const form = reactive<IpAddressFormState>({
  networkInterfaceId: null,
  ipAddress: '',
})

const dialogTitle = computed(() => (props.mode === 'create' ? '登记 IP 地址' : '编辑 IP 地址'))
const submitLabel = computed(() => (props.mode === 'create' ? '登记' : '保存'))

// ---- 父网络接口选项（仅 create 模式加载） ----

const nicOptions = ref<NetworkInterfaceRead[]>([])
const nicOptionsLoading = ref(false)
const nicOptionsError = ref<ApiError | null>(null)

/** 拉取父网络接口选项。page_size 取契约上限 200（V1 内部规模下的最小实现）。 */
async function loadNicOptions(): Promise<void> {
  nicOptionsLoading.value = true
  nicOptionsError.value = null
  try {
    const data = await listNetworkInterfaces({ page: 1, page_size: 200 })
    nicOptions.value = data.items
  } catch (err) {
    nicOptions.value = []
    nicOptionsError.value =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
  } finally {
    nicOptionsLoading.value = false
  }
}

// ---- 打开时初始化表单 ----

watch(
  dialogVisible,
  (open) => {
    if (!open) return
    failure.value = null
    if (props.mode === 'edit' && props.ipAddress !== null && props.ipAddress !== undefined) {
      form.networkInterfaceId = props.ipAddress.network_interface_id
      form.ipAddress = props.ipAddress.ip_address
    } else {
      form.networkInterfaceId = props.presetNetworkInterfaceId ?? null
      form.ipAddress = ''
    }
    if (props.mode === 'create') {
      void loadNicOptions()
    }
  },
  { immediate: true },
)

// ---- 提交 ----

const submitting = ref(false)
const failure = ref<ApiError | null>(null)

/**
 * create 模式下父网络接口未选择 → 表单未完成，提交按钮禁用（非业务守卫，
 * 见头注）。edit 模式无需选择；ip_address 不设任何完成条件（空串等
 * 未定义约束由服务端裁决，契约 §7）。
 */
const submitDisabled = computed(() => props.mode === 'create' && form.networkInterfaceId === null)

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
      // 契约 §3.1 / §3.4：字段级提示（details[].field，如 ip_address /
      // network_interface_id / 未识别字段名）。
      return {
        code: error.code,
        title: '请求校验失败',
        description: '提交的内容不符合要求，请根据下方字段提示修改后重试。',
        details: error.details,
      }
    case 'NOT_FOUND':
      // create：父 NIC 不存在 / 已逻辑删除（或其宿主 BareMetal 不活跃，
      // 契约 §3.1）；edit：目标 IP 不存在或已被逻辑删除（契约 §3.4，两者不区分）。
      return props.mode === 'create'
        ? {
            code: error.code,
            title: '无法登记',
            description: '请检查所选网络接口，其可能不存在或已被删除。',
            details: [],
          }
        : {
            code: error.code,
            title: '无法保存',
            description: '该 IP 地址不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
    case 'CONFLICT': {
      // 契约 §4.1：稳定判别值为 error.code === 'CONFLICT' +
      // details[].code === 'DUPLICATE'（DB 兜底路径的 details[].field 为
      // best-effort，不构成契约；message 不构成契约）。
      const isDuplicate = error.details.some((detail) => detail.code === 'DUPLICATE')
      if (isDuplicate) {
        return {
          code: error.code,
          title: '该 IP 在所属 Cluster 内已被占用',
          description: '同一 Cluster 内已存在活跃的相同 IP 地址，请修改后重试。',
          details: error.details,
        }
      }
      // 契约内不存在其他 409 语义（FK 违规的 REFERENCE 映射路径在产品路径下
      // 不可达，契约 §4.3 补充）；按通用冲突渲染。
      return {
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

async function handleSubmit(): Promise<void> {
  if (submitting.value || submitDisabled.value) return
  submitting.value = true
  failure.value = null
  try {
    let saved: IpAddressRead
    if (props.mode === 'create') {
      // submitDisabled 已保证 create 模式下父网络接口已选择；此处再显式兜底。
      const networkInterfaceId = form.networkInterfaceId
      if (networkInterfaceId === null) return
      // ip_address 原样提交：不校验、不变换（契约 §7）；空串 / 首尾空白等
      // 未定义约束由服务端裁决，前端不编写业务分支（§21）。
      saved = await createIpAddress({
        network_interface_id: networkInterfaceId,
        ip_address: form.ipAddress,
      })
    } else {
      const target = props.ipAddress
      if (target === null || target === undefined) return
      // PATCH 可变字段封闭为 {ip_address}（契约 §3.4）；快照式提交该字段。
      saved = await updateIpAddress(target.id, { ip_address: form.ipAddress })
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
      class="ip-address-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="ip-address-form__failure-details">
        <p v-for="(detail, index) in failureView.details" :key="index">
          <el-tag size="small" type="danger">
            {{ detail.field ?? detail.code ?? '字段' }}
          </el-tag>
          <span v-if="detail.message">{{ detail.message }}</span>
        </p>
      </div>
    </el-alert>

    <el-form label-width="110px">
      <!-- create：所属网络接口（下拉选项来自 GET /api/network-interfaces，父存在性
           / 活跃性由服务端裁决，404 → 「请检查所选网络接口」）。name 无唯一性
           承诺，选项附带 ID 与宿主裸金属 ID 辅助区分。 -->
      <el-form-item v-if="mode === 'create'" label="所属网络接口">
        <el-select
          v-model="form.networkInterfaceId"
          class="ip-address-form__nic-select"
          placeholder="请选择所属网络接口"
          data-testid="ip-form-network-interface"
          :loading="nicOptionsLoading"
        >
          <el-option
            v-for="nic in nicOptions"
            :key="nic.id"
            :label="`${nic.name}（ID ${nic.id} · 宿主裸金属 #${nic.bare_metal_id}）`"
            :value="nic.id"
          />
        </el-select>
        <div v-if="nicOptionsError !== null" class="ip-address-form__hint">
          网络接口列表加载失败（{{ nicOptionsError.code }}）。
          <el-button link type="primary" @click="loadNicOptions">重试</el-button>
        </div>
        <div
          v-else-if="!nicOptionsLoading && nicOptions.length === 0"
          class="ip-address-form__hint"
        >
          暂无可选网络接口：IP 地址必须属于一个网络接口（IP→NIC 必选绑定），请先登记网络接口。
        </div>
      </el-form-item>

      <!-- IP 地址字面值：不做任何长度 / 空白 / 空串 / 格式 / 正则校验，也不做
           归一化（契约 §7）；唯一性由服务端裁决（§21），与既有行相同字面值
           仍直接提交。 -->
      <el-form-item label="IP 地址">
        <el-input
          v-model="form.ipAddress"
          placeholder="如 10.0.1.1/16"
          data-testid="ip-form-ip-address"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="ip-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ip-address-form__hint {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}

.ip-address-form__failure {
  margin-bottom: 16px;
}

.ip-address-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.ip-address-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
