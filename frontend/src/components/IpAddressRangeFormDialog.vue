<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import { ApiError } from '../api/http'
import { listClusters } from '../api/clusters'
import type { ClusterRead } from '../api/clusters'
import { createIpAddressRange, updateIpAddressRange } from '../api/ipAddressRanges'
import type { IpAddressRangeRead } from '../api/ipAddressRanges'

/**
 * IP 地址范围段登记 / 编辑对话框（契约 docs/api/f020-ip-address-range.md
 * §3.1 / §3.4，含 F022 修订）。
 *
 * - create 模式：所属集群（下拉，选项来自既有 GET /api/clusters，f001 契约
 *   §3.2）+ start_ip / end_ip 文本输入 + 三个可选元数据输入（F022：名称
 *   文本 / 子网掩码文本 / VLAN 数字）→ POST /api/ip-address-ranges；若从
 *   已按集群筛选的列表进入则预选该集群（可改选）；三个可选输入缺省即空，
 *   提交时输入为空 → null（缺省 / null 均视为未登记，契约 §3.1）；
 * - edit 模式：start_ip / end_ip 文本输入 + 三个可选元数据输入 → PATCH
 *   /api/ip-address-ranges/{id}；预填当前值（null → 空），清空输入即提交
 *   null（清空，契约 §3.4）；快照式提交 5 个可变字段 {start_ip, end_ip,
 *   name, subnet_mask, vlan}；cluster_id / id / created_at 不在 PATCH 可
 *   变集内（契约 §3.4），表单不提供其输入；
 * - 表单字段仅 cluster_id（create）/ start_ip / end_ip / name /
 *   subnet_mask / vlan：不出现状态字段（Q-002=B，范围段无状态）、
 *   description / 用途 / CIDR / 前缀长度等未确认字段（契约 §2 / §10）；
 * - 前端不重复实现业务守卫（§21）：start_ip / end_ip 不做任何 IPv4 格式
 *   校验 / 解析 / 归一化 / 去除空白，不做 start<=end 预判，也不做同 Cluster
 *   重叠预检（契约 §7 / AC-07 / AC-08 / AC-10 均由服务端裁决）；name 不做
 *   唯一 / 长度 / 空串 / 字符集校验（契约 §7.3），subnet_mask 不做格式校验，
 *   VLAN 不设取值范围约束（不设 min / max，1–4094 由服务端裁决）—— 本表
 *   单不预判、不拦截、不禁用提交；
 * - 集群未选择（表单未完成）时提交按钮禁用 —— 这不是父存在性预判：任何
 *   已选择的值都直接提交，由服务端裁决；
 * - 失败按 error.code（必要时结合 details[].code / details[].field）分支
 *   渲染固定文案（不解析 message）：VALIDATION_ERROR → 字段级提示（
 *   details[].field，如 name / subnet_mask / vlan / start_ip / end_ip /
 *   cluster_id / 未识别字段名）；NOT_FOUND → create：「请检查所选集群」；
 *   CONFLICT + details[].code === 'OVERLAP' → 「与该 Cluster 已有范围段
 *   重叠」；CONFLICT + details[].code === 'DUPLICATE'（F022，同 Cluster
 *   活跃同名，DB 兜底路径 details[].field 为 best-effort，只按 code 分支）
 *   → 「该集群已存在同名网段」；401 交由既有全局会话失效处理；提交中
 *   Loading 且禁止重复提交。
 */
const props = defineProps<{
  mode: 'create' | 'edit'
  /** create 模式：预选的归属集群 id（可改选）；edit 模式忽略。 */
  presetClusterId?: number | null
  /** edit 模式：当前范围段（表单初值）；create 模式忽略。 */
  ipAddressRange?: IpAddressRangeRead | null
}>()

const emit = defineEmits<{
  /** 登记或修正成功，携带服务端返回的 IpAddressRangeRead。 */
  success: [ipAddressRange: IpAddressRangeRead]
}>()

const dialogVisible = defineModel<boolean>({ required: true })

interface IpAddressRangeFormState {
  clusterId: number | null
  startIp: string
  endIp: string
  /** F022 可选元数据：文本输入，空串表示未登记 / 清空。 */
  name: string
  subnetMask: string
  /** F022 可选元数据：数字输入，null 表示未登记 / 清空。 */
  vlan: number | null
}

const form = reactive<IpAddressRangeFormState>({
  clusterId: null,
  startIp: '',
  endIp: '',
  name: '',
  subnetMask: '',
  vlan: null,
})

const dialogTitle = computed(() =>
  props.mode === 'create' ? '登记 IP 地址范围段' : '编辑 IP 地址范围段',
)
const submitLabel = computed(() => (props.mode === 'create' ? '登记' : '保存'))

// ---- 归属集群选项（仅 create 模式加载） ----

const clusterOptions = ref<ClusterRead[]>([])
const clusterOptionsLoading = ref(false)
const clusterOptionsError = ref<ApiError | null>(null)

/** 拉取归属集群选项。page_size 取契约上限 200（V1 内部规模下的最小实现）。 */
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
    if (props.mode === 'edit' && props.ipAddressRange !== null && props.ipAddressRange !== undefined) {
      form.clusterId = props.ipAddressRange.cluster_id
      form.startIp = props.ipAddressRange.start_ip
      form.endIp = props.ipAddressRange.end_ip
      // F022：预填当前值（null → 空，清空输入即提交 null，契约 §3.4）。
      form.name = props.ipAddressRange.name ?? ''
      form.subnetMask = props.ipAddressRange.subnet_mask ?? ''
      form.vlan = props.ipAddressRange.vlan
    } else {
      form.clusterId = props.presetClusterId ?? null
      form.startIp = ''
      form.endIp = ''
      form.name = ''
      form.subnetMask = ''
      form.vlan = null
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

/**
 * create 模式下归属集群未选择 → 表单未完成，提交按钮禁用（非业务守卫，
 * 见头注）。edit 模式无需选择；start_ip / end_ip 不设任何完成条件（空串、
 * 非法 IPv4、start > end 等均由服务端裁决，前端不编写业务分支，§21）。
 */
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
      // 契约 §3.1 / §3.4：字段级提示（details[].field，如 start_ip / end_ip /
      // cluster_id / 未识别字段名）。
      return {
        code: error.code,
        title: '请求校验失败',
        description: '提交的内容不符合要求，请根据下方字段提示修改后重试。',
        details: error.details,
      }
    case 'NOT_FOUND':
      // create：父 Cluster 不存在或已逻辑删除（契约 §3.1）；edit：目标范围段
      // 不存在或已被逻辑删除（契约 §3.4，两者不区分）。
      return props.mode === 'create'
        ? {
            code: error.code,
            title: '无法登记',
            description: '请检查所选集群，其可能不存在或已被删除。',
            details: [],
          }
        : {
            code: error.code,
            title: '无法保存',
            description: '该范围段不存在或已被删除，可能已被其他操作移除。',
            details: [],
          }
    case 'CONFLICT': {
      // 契约 §4.1：稳定判别值为 error.code === 'CONFLICT' + details[].code ===
      // 'OVERLAP'（DB 兜底路径的 details[].field 为 best-effort，不构成契约；
      // message 不构成契约）。
      const isOverlap = error.details.some((detail) => detail.code === 'OVERLAP')
      if (isOverlap) {
        return {
          code: error.code,
          title: '与该 Cluster 已有范围段重叠',
          description: '同一 Cluster 内已存在与该范围重叠的活跃范围段，请修改后重试。',
          details: error.details,
        }
      }
      // 契约 §4.2（F022）：稳定判别值为 details[].code === 'DUPLICATE'（同
      // Cluster 活跃同名 name；应用层路径 details[].field === 'name'，DB 兜底
      // 路径为 best-effort，不构成契约 → 只按 code 分支）。
      const isDuplicateName = error.details.some((detail) => detail.code === 'DUPLICATE')
      if (isDuplicateName) {
        return {
          code: error.code,
          title: '该集群已存在同名网段',
          description:
            '同一集群内已存在同名的活跃范围段（名称在集群内唯一、区分大小写），请修改名称后重试。',
          // 与 F007 Container 同名分支同款：固定文案已表达冲突语义，不再罗列
          // details（其中 message 不构成契约）。
          details: [],
        }
      }
      // 契约内不存在其他 409 语义；按通用冲突渲染。
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

/**
 * 组装 F022 三个可选元数据字段请求体：文本输入为空 → null（清空 / 保持
 * 未登记，契约 §3.1 / §3.4）；VLAN 数字输入为 null（清空）即提交 null。
 * 不做任何 trim / 归一化 / 取值范围预判（§21）。
 */
function metadataBody(): {
  name: string | null
  subnet_mask: string | null
  vlan: number | null
} {
  return {
    name: form.name === '' ? null : form.name,
    subnet_mask: form.subnetMask === '' ? null : form.subnetMask,
    vlan: form.vlan,
  }
}

async function handleSubmit(): Promise<void> {
  if (submitting.value || submitDisabled.value) return
  submitting.value = true
  failure.value = null
  try {
    let saved: IpAddressRangeRead
    if (props.mode === 'create') {
      // submitDisabled 已保证 create 模式下归属集群已选择；此处再显式兜底。
      const clusterId = form.clusterId
      if (clusterId === null) return
      // start_ip / end_ip 原样提交：不校验、不变换（契约 §7）；非法 IPv4 /
      // start > end / 重叠 / 重名 / 非法掩码 / 越界 VLAN 均由服务端裁决，
      // 前端不编写业务分支（§21）。可选字段输入为空 → null（未登记）。
      saved = await createIpAddressRange({
        cluster_id: clusterId,
        start_ip: form.startIp,
        end_ip: form.endIp,
        ...metadataBody(),
      })
    } else {
      const target = props.ipAddressRange
      if (target === null || target === undefined) return
      // PATCH 可变字段封闭为 {start_ip, end_ip, name, subnet_mask, vlan}
      // （契约 §3.4，含 F022 修订）；快照式提交 5 字段，清空的可选字段 → null。
      saved = await updateIpAddressRange(target.id, {
        start_ip: form.startIp,
        end_ip: form.endIp,
        ...metadataBody(),
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
      class="ip-address-range-form__failure"
      type="error"
      :title="failureView.title"
      :description="failureView.description"
      show-icon
      closable
      :data-error-code="failureView.code"
      @close="failure = null"
    >
      <div v-if="failureView.details.length > 0" class="ip-address-range-form__failure-details">
        <p v-for="(detail, index) in failureView.details" :key="index">
          <el-tag size="small" type="danger">
            {{ detail.field ?? detail.code ?? '字段' }}
          </el-tag>
          <span v-if="detail.message">{{ detail.message }}</span>
        </p>
      </div>
    </el-alert>

    <el-form label-width="110px">
      <!-- create：归属集群（下拉选项来自 GET /api/clusters，父存在性 / 活跃性
           由服务端裁决，404 → 「请检查所选集群」）。Cluster 名称无唯一性承诺，
           选项附带 ID 辅助区分。edit 模式 cluster_id 不可变（契约 §3.4），
           不渲染该输入。 -->
      <el-form-item v-if="mode === 'create'" label="所属集群">
        <el-select
          v-model="form.clusterId"
          class="ip-address-range-form__cluster-select"
          placeholder="请选择所属集群"
          data-testid="range-form-cluster"
          :loading="clusterOptionsLoading"
        >
          <el-option
            v-for="cluster in clusterOptions"
            :key="cluster.id"
            :label="`${cluster.name}（ID ${cluster.id}）`"
            :value="cluster.id"
          />
        </el-select>
        <div v-if="clusterOptionsError !== null" class="ip-address-range-form__hint">
          集群列表加载失败（{{ clusterOptionsError.code }}）。
          <el-button link type="primary" @click="loadClusterOptions">重试</el-button>
        </div>
        <div
          v-else-if="!clusterOptionsLoading && clusterOptions.length === 0"
          class="ip-address-range-form__hint"
        >
          暂无可选集群：范围段必须归属一个集群，请先登记集群。
        </div>
      </el-form-item>

      <!-- start_ip / end_ip：不做任何 IPv4 格式校验 / 解析 / 归一化 / 去除空白，
           不做 start<=end 预判（契约 §7 / §21）；重叠由服务端裁决，直接提交。 -->
      <el-form-item label="起始 IP">
        <el-input
          v-model="form.startIp"
          placeholder="如 10.0.0.1"
          data-testid="range-form-start-ip"
        />
      </el-form-item>
      <el-form-item label="结束 IP">
        <el-input
          v-model="form.endIp"
          placeholder="如 10.0.0.255"
          data-testid="range-form-end-ip"
        />
      </el-form-item>

      <!-- F022 三个可选元数据输入：不做任何业务校验（§21）——name 不做唯一 /
           长度 / 空串 / 字符集校验（契约 §7.3）；subnet_mask 不做格式校验；
           VLAN 不设取值范围约束（不设 min / max，1–4094 由服务端裁决）。
           输入为空 → 提交 null（未登记 / 清空）。 -->
      <el-form-item label="名称">
        <el-input
          v-model="form.name"
          placeholder="可选，如 业务网"
          data-testid="range-form-name"
        />
      </el-form-item>
      <el-form-item label="子网掩码">
        <el-input
          v-model="form.subnetMask"
          placeholder="可选，如 255.255.255.0"
          data-testid="range-form-subnet-mask"
        />
      </el-form-item>
      <el-form-item label="VLAN">
        <el-input-number
          v-model="form.vlan"
          class="ip-address-range-form__vlan"
          placeholder="可选，如 100"
          :controls="false"
          data-testid="range-form-vlan"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="submitting" @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="submitDisabled"
        data-testid="range-form-submit"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ip-address-range-form__hint {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}

.ip-address-range-form__failure {
  margin-bottom: 16px;
}

.ip-address-range-form__failure-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.ip-address-range-form__failure-details p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
