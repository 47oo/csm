<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import { listNetworkInterfaces } from '../api/networkInterfaces'
import type { NetworkInterfaceRead } from '../api/networkInterfaces'
import { allocateIpAddress, allocateIpAddressManual } from '../api/ipAddresses'
import type { IpAddressRead } from '../api/ipAddresses'

/**
 * IP 地址分配对话框（F021，契约 docs/api/f021-ip-address-allocation.md §3）。
 *
 * - mode === 'auto'：提交 → POST /api/ip-addresses/allocate，请求体恰为
 *   { network_interface_id }（契约 §3.1 schema 封闭）；服务端在目标
 *   Cluster 全部活跃范围段并集内取数值最小的未占用 IPv4；
 * - mode === 'manual'：提交 → POST /api/ip-addresses/allocate-manual，
 *   请求体恰为 { network_interface_id, ip_address }（契约 §3.2）；
 * - 目标 NIC：presetNetworkInterfaceId 已就绪（NIC 上下文入口）时只读展示，
 *   不提供改选；未提供（全局入口，先选 NIC）时以下拉选择，选项来自既有
 *   GET /api/network-interfaces（F004 契约 §3.2）；
 * - 前端不重复实现业务守卫（§21 / AC-33）：ip_address 仅做基础必填
 *   （空串 = 表单未完成）与类型提示（placeholder），**不做** IPv4 格式 /
 *   修剪 / 范围 / 占用预判；非法格式（400）、范围外（409 OUT_OF_RANGE）、
 *   已占用（409 DUPLICATE）、耗尽（409 NO_AVAILABLE_IP）一律由服务端裁决，
 *   输入值原样提交（含首尾空白 / 前导零），规范化由服务端完成；
 * - 分配动作状态互异：Empty（尚未分配结果，引导文案）/ Loading（提交中，
 *   控件禁用、拦截重复提交）/ Error（按 error.code 分支渲染固定文案）；
 *   成功为第四个互异状态（结果区展示新 ip_address 与 id，本对话框不自动
 *   关闭，由用户确认后关闭）；
 * - 错误分支按契约 §4 稳定判别值，不解析 message：400 VALIDATION_ERROR →
 *   字段级提示（details[].field）；401 → 既有全局会话失效处理
 *   （api/http.ts）；404 NOT_FOUND → 「目标网络接口不存在或已停用」；
 *   409 CONFLICT + details[].code === 'NO_AVAILABLE_IP' → 「该集群地址池
 *   已无可用 IP」；OUT_OF_RANGE → 「该地址不在任何活跃地址范围内」；
 *   DUPLICATE → 「该地址已被占用」并可重试；
 * - 成功 → emit('success', IpAddressRead)，由接线页面刷新列表；响应
 *   ip_address 为服务端规范化值，原样展示。
 */
const props = withDefaults(
  defineProps<{
    mode: 'auto' | 'manual'
    /** NIC 上下文入口的目标 NIC id；null = 全局入口（对话框内先选择）。 */
    presetNetworkInterfaceId?: number | null
  }>(),
  { presetNetworkInterfaceId: null },
)

const emit = defineEmits<{
  /** 分配成功，携带服务端返回的 IpAddressRead（接线页面刷新列表）。 */
  success: [ipAddress: IpAddressRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

interface AllocateFormState {
  networkInterfaceId: number | null
  ipAddress: string
}

const form = reactive<AllocateFormState>({
  networkInterfaceId: null,
  ipAddress: '',
})

const dialogTitle = computed(() =>
  props.mode === 'auto' ? '自动分配 IP 地址' : '手动分配 IP 地址',
)
const submitLabel = computed(() => (props.mode === 'auto' ? '自动分配' : '手动分配'))

// ---- 目标网络接口选项（仅全局入口加载） ----

const nicOptions = ref<NetworkInterfaceRead[]>([])
const nicOptionsLoading = ref(false)
const nicOptionsError = ref<ApiError | null>(null)

/** 拉取目标网络接口选项。page_size 取契约上限 200（V1 内部规模下的最小实现）。 */
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

// ---- 提交与状态 ----

const submitting = ref(false)
const failure = ref<ApiError | null>(null)
const result = ref<IpAddressRead | null>(null)

/**
 * 分配动作状态（互异）：
 * - loading：提交进行中（控件禁用、拦截重复提交）；
 * - error：最近一次提交失败（按 error.code 渲染固定文案）；
 * - success：最近一次提交成功（结果区展示新 ip_address 与 id）；
 * - empty：尚无分配结果（引导文案）。
 */
const state = computed<'loading' | 'error' | 'success' | 'empty'>(() => {
  if (submitting.value) return 'loading'
  if (failure.value !== null) return 'error'
  if (result.value !== null) return 'success'
  return 'empty'
})

/** Empty 态引导文案：按模式说明服务端裁决规则，不含任何客户端预判。 */
const guidance = computed(() =>
  props.mode === 'auto'
    ? '尚未分配。提交后将在目标集群全部活跃地址范围的并集内自动选取数值最小的未占用 IPv4。'
    : '尚未分配。地址须为合法 IPv4、落在目标集群某个活跃地址范围内且未被占用，均由服务端裁决。',
)

// 打开时初始化表单与状态；全局入口同时加载网络接口选项。
watch(
  dialogVisible,
  (open) => {
    if (!open) return
    form.networkInterfaceId = props.presetNetworkInterfaceId
    form.ipAddress = ''
    failure.value = null
    result.value = null
    if (props.presetNetworkInterfaceId === null) {
      void loadNicOptions()
    }
  },
  { immediate: true },
)

/**
 * 表单完成判定（基础必填，非业务守卫）：目标 NIC 未选择 → 未完成；
 * manual 模式 ip_address 为空串 → 未完成（恰为契约 §3.2 必填字段的基础
 * 形状检查）。任何非空取值（含 'abc'、' 10.0.0.5 '、'010.0.0.5'）均为
 * 表单已完成、原样提交，IPv4 格式 / 范围 / 占用等业务裁决全在服务端。
 */
const submitDisabled = computed(
  () =>
    form.networkInterfaceId === null || (props.mode === 'manual' && form.ipAddress === ''),
)

interface AllocateFailureView {
  code: string
  /** 409 分支的稳定判别值（details[].code）；无则为 null。 */
  detailCode: string | null
  title: string
  description: string
  details: readonly ApiErrorDetail[]
}

/**
 * 失败提示视图：按 error.code（必要时结合 details[].code）分支生成固定
 * 文案，不解析 message（契约 §4：message 不构成契约）。
 */
const failureView = computed<AllocateFailureView | null>(() => {
  const error = failure.value
  if (error === null) return null
  switch (error.code) {
    case 'VALIDATION_ERROR':
      // 契约 §3.1 / §3.2 / §4.4：字段级提示（details[].field，如
      // ip_address / network_interface_id / 未识别字段名）。
      return {
        code: error.code,
        detailCode: null,
        title: '请求校验失败',
        description: '提交的内容不符合要求，请根据下方字段提示修改后重试。',
        details: error.details,
      }
    case 'NOT_FOUND':
      // 契约 §3.1 / §3.2：目标 NIC 不存在 / 已逻辑删除 / 宿主 BareMetal
      // 不活跃（三者不区分）。
      return {
        code: error.code,
        detailCode: null,
        title: '无法分配',
        description: '目标网络接口不存在或已停用，请检查后重试。',
        details: [],
      }
    case 'CONFLICT': {
      // 契约 §4.1 ~ §4.3：409 的稳定判别值为 details[].code
      // （NO_AVAILABLE_IP / OUT_OF_RANGE / DUPLICATE）。
      const detailCode = error.details.find((detail) => detail.code !== undefined)?.code ?? null
      if (detailCode === 'NO_AVAILABLE_IP') {
        return {
          code: error.code,
          detailCode,
          title: '该集群地址池已无可用 IP',
          description:
            '目标集群的全部活跃地址范围内已无未被占用的 IPv4，可先调整地址范围段后重试。',
          details: [],
        }
      }
      if (detailCode === 'OUT_OF_RANGE') {
        return {
          code: error.code,
          detailCode,
          title: '该地址不在任何活跃地址范围内',
          description: '输入的地址不落在目标集群的任何活跃 IP 地址范围内，请修改后重试。',
          details: [],
        }
      }
      if (detailCode === 'DUPLICATE') {
        return {
          code: error.code,
          detailCode,
          title: '该地址已被占用',
          description: '该地址已被占用或与其他操作并发冲突，可修改地址或重试。',
          details: [],
        }
      }
      return {
        code: error.code,
        detailCode: null,
        title: '数据冲突',
        description: '分配请求与现有数据冲突，请稍后重试。',
        details: [],
      }
    }
    case 'NETWORK_ERROR':
      return {
        code: error.code,
        detailCode: null,
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
        detailCode: null,
        title: '分配失败',
        description: `请求未成功（${error.code}），请稍后重试。`,
        details: [],
      }
  }
})

async function handleSubmit(): Promise<void> {
  if (submitting.value || submitDisabled.value) return
  const networkInterfaceId = form.networkInterfaceId
  if (networkInterfaceId === null) return
  submitting.value = true
  failure.value = null
  result.value = null
  try {
    const allocated =
      props.mode === 'auto'
        ? await allocateIpAddress({ network_interface_id: networkInterfaceId })
        : await allocateIpAddressManual({
            network_interface_id: networkInterfaceId,
            // 原样提交：不校验、不修剪、不变换（§21）；规范化由服务端完成，
            // 响应 ip_address 为规范化值，原样展示。
            ip_address: form.ipAddress,
          })
    result.value = allocated
    emit('success', allocated)
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
    <div class="ip-address-allocate" data-testid="allocate-state" :data-state="state">
      <!-- 失败提示：按 error.code（必要时结合 details[].code）生成固定文案，
           可关闭；message 不参与分支（契约 §4）。 -->
      <el-alert
        v-if="failureView !== null"
        class="ip-address-allocate__failure"
        type="error"
        :title="failureView.title"
        :description="failureView.description"
        show-icon
        closable
        :data-error-code="failureView.code"
        :data-error-detail-code="failureView.detailCode"
        @close="failure = null"
      >
        <div v-if="failureView.details.length > 0" class="ip-address-allocate__failure-details">
          <p v-for="(detail, index) in failureView.details" :key="index">
            <el-tag size="small" type="danger">
              {{ detail.field ?? detail.code ?? '字段' }}
            </el-tag>
            <span v-if="detail.message">{{ detail.message }}</span>
          </p>
        </div>
      </el-alert>

      <!-- 成功结果区：展示新 ip_address 与 id；值为服务端返回的规范化结果，
           原样展示（契约 §2）。 -->
      <el-result
        v-else-if="state === 'success' && result !== null"
        class="ip-address-allocate__result"
        icon="success"
        title="分配成功"
        data-testid="allocate-result"
      >
        <template #extra>
          <div class="ip-address-allocate__result-fields">
            <p>
              IP 地址：<code data-testid="allocate-result-ip">{{ result.ip_address }}</code>
            </p>
            <p>ID：<span data-testid="allocate-result-id">{{ result.id }}</span></p>
          </div>
        </template>
      </el-result>

      <!-- Empty 态引导文案：尚未分配结果（与 Loading / Error / 成功互异）。 -->
      <div
        v-else-if="state === 'empty'"
        class="ip-address-allocate__guidance"
        data-testid="allocate-guidance"
      >
        {{ guidance }}
      </div>

      <el-form label-width="110px">
        <!-- 目标网络接口：全局入口（未预设）以下拉选择，选项来自既有
             GET /api/network-interfaces（F004 契约 §3.2），存在性 / 活跃性由
             服务端裁决（404）；NIC 上下文入口已由上下文固定，只读展示。 -->
        <el-form-item v-if="presetNetworkInterfaceId === null" label="目标网络接口">
          <el-select
            v-model="form.networkInterfaceId"
            class="ip-address-allocate__nic-select"
            placeholder="请选择目标网络接口"
            :loading="nicOptionsLoading"
            :disabled="submitting"
          >
            <el-option
              v-for="nic in nicOptions"
              :key="nic.id"
              :label="`${nic.name}（ID ${nic.id} · 宿主裸金属 #${nic.bare_metal_id}）`"
              :value="nic.id"
            />
          </el-select>
          <div v-if="nicOptionsError !== null" class="ip-address-allocate__hint">
            网络接口列表加载失败（{{ nicOptionsError.code }}）。
            <el-button link type="primary" @click="loadNicOptions">重试</el-button>
          </div>
          <div
            v-else-if="!nicOptionsLoading && nicOptions.length === 0"
            class="ip-address-allocate__hint"
          >
            暂无可选网络接口：IP 地址必须属于一个网络接口，请先登记网络接口。
          </div>
        </el-form-item>
        <el-form-item v-else label="目标网络接口">
          <span class="ip-address-allocate__preset" data-testid="allocate-preset-nic">
            网络接口 #{{ presetNetworkInterfaceId }}
          </span>
        </el-form-item>

        <!-- 手动分配的 IP 地址输入：仅基础必填（空串 = 表单未完成）与类型
             提示（placeholder）；不做格式 / 修剪 / 范围 / 占用预判（§21）。 -->
        <el-form-item v-if="mode === 'manual'" label="IP 地址">
          <el-input
            v-model="form.ipAddress"
            placeholder="如 10.0.0.5"
            data-testid="allocate-ip-address"
            :disabled="submitting"
          />
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">关闭</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="allocate-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ip-address-allocate__failure {
  margin-bottom: 16px;
}

.ip-address-allocate__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.ip-address-allocate__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.ip-address-allocate__guidance {
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}

.ip-address-allocate__result {
  padding: 8px 0 16px;
}

.ip-address-allocate__result-fields {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ip-address-allocate__result-fields p {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 14px;
}

.ip-address-allocate__result-fields code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 14px;
}

.ip-address-allocate__preset {
  color: var(--el-text-color-primary);
}

.ip-address-allocate__nic-select {
  width: 100%;
}

.ip-address-allocate__hint {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}
</style>
