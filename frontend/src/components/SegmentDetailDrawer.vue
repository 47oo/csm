<script setup lang="ts">
// 网段详情抽屉（架构 F005 §2.4 / 需求 §6.5）：
// - §6.5 全字段展示 + 计数快照（保留地址条目数、已分配数量——F005 阶段恒 0、
//   可自动分配数量——§5 BQ-R 快照）；
// - 重叠提示（§4.6.5）；
// - 保留地址增删控件（显式子项操作，Contract §3.1–3.3）；
// - 网关设置（PATCH，Contract §2.4）与显式清空（DELETE /gateway，Contract §3.4，
//   幂等 + 乐观锁；删除前置之一，BQ-O）；
// - 「已分配 IP 及归属」空态占位：数据由后续能力（IP 分配，F006）提供。
// 写操作入口仅 maintainer/admin 可见；服务端为最终校验（架构 §8.2）。
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormItemRule } from 'element-plus'
import {
  clearNetworkSegmentGateway,
  createReservedAddress,
  deleteReservedAddress,
  getNetworkSegment,
  updateNetworkSegment,
  type NetworkSegmentDetail,
  type ReservedAddress,
} from '../api/segments'
import { apiErrorMessage, isApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { formatDateTime } from '../utils/format'
import {
  canManageSegments,
  overlapWarningText,
  segmentConflictMessage,
  validateGatewayInCidr,
  validateReservedRange,
} from '../utils/segmentRules'

const props = defineProps<{
  /** 抽屉可见性（v-model） */
  modelValue: boolean
  /** 目标网段 ID；null = 未指定 */
  segmentId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  /** 网段数据（保留地址/网关/计数）发生变化，父级应刷新列表 */
  (e: 'changed'): void
}>()

const auth = useAuthStore()
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

// 写操作入口可见性：仅 maintainer/admin（服务端为最终校验）
const canManage = computed(() => canManageSegments(auth.user?.role))

// ---------- 详情加载（Contract §2.3） ----------
const detail = ref<NetworkSegmentDetail | null>(null)
const loading = ref(false)
const loadError = ref('')

async function loadDetail(): Promise<void> {
  const id = props.segmentId
  if (id === null) return
  loading.value = true
  loadError.value = ''
  try {
    detail.value = await getNetworkSegment(id)
  } catch (error) {
    // 错误显式呈现，不伪装成空详情
    detail.value = null
    loadError.value = apiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.segmentId] as const,
  ([open]) => {
    if (open) void loadDetail()
  },
)

const overlapText = computed(() => (detail.value === null ? null : overlapWarningText(detail.value)))

// ---------- 子操作错误呈现（409/404/422；401/403 全局处理） ----------
function isGloballyHandled(error: unknown): boolean {
  return isApiError(error) && (error.status === 401 || error.status === 403)
}

/**
 * 子操作（保留地址/网关）错误呈现：
 * - VERSION_CONFLICT：重新加载详情取最新 version；
 * - 422：优先字段级 message（RESERVED_OUT_OF_CIDR/RESERVED_RANGE_INVALID/
 *   RESERVED_OVERLAP/GATEWAY_OUT_OF_CIDR），否则 problem message；
 * - 409：按 segmentConflictMessage 提示；
 * - 404：网段已不存在，关闭抽屉并通知父级刷新。
 */
function handleSubActionError(
  error: unknown,
  opts: { fields?: string[]; onFieldError?: (message: string) => void },
): void {
  if (!isApiError(error)) {
    ElMessage.error(apiErrorMessage(error))
    return
  }
  if (error.code === 'VERSION_CONFLICT') {
    ElMessage.error('该网段已被其他人修改，正在重新加载详情')
    void loadDetail()
    return
  }
  if (error.status === 422 && opts.onFieldError) {
    const fieldMessage = (opts.fields ?? []).map((f) => error.fieldError(f)).find((m) => m !== undefined)
    opts.onFieldError(fieldMessage ?? error.message)
    return
  }
  if (error.status === 409) {
    ElMessage.error(segmentConflictMessage(error.code) ?? apiErrorMessage(error))
    return
  }
  if (error.status === 404) {
    ElMessage.warning('该网段已不存在')
    visible.value = false
    emit('changed')
    return
  }
  if (!isGloballyHandled(error)) {
    ElMessage.error(apiErrorMessage(error))
  }
}

// ---------- 网关：设置（PATCH，Contract §2.4）/ 显式清空（DELETE /gateway，Contract §3.4） ----------
const gatewayInput = ref('')
const gatewayError = ref('')
const gatewaySaving = ref(false)
const gatewayClearing = ref(false)

watch(detail, () => {
  gatewayInput.value = detail.value?.gateway ?? ''
  gatewayError.value = ''
})

async function handleSaveGateway(): Promise<void> {
  const current = detail.value
  if (!current) return
  gatewayError.value = ''
  if (gatewayInput.value === '') {
    gatewayError.value = '如需清空网关，请使用「显式清空网关」'
    return
  }
  gatewayError.value = validateGatewayInCidr(gatewayInput.value, current.cidr) ?? ''
  if (gatewayError.value !== '') return
  gatewaySaving.value = true
  try {
    detail.value = await updateNetworkSegment(current.id, {
      gateway: gatewayInput.value,
      version: current.version,
    })
    ElMessage.success('网关已设置')
    emit('changed')
  } catch (error) {
    handleSubActionError(error, { fields: ['gateway'], onFieldError: (m) => (gatewayError.value = m) })
  } finally {
    gatewaySaving.value = false
  }
}

async function handleClearGateway(): Promise<void> {
  const current = detail.value
  if (!current) return
  gatewayError.value = ''
  gatewayClearing.value = true
  try {
    await clearNetworkSegmentGateway(current.id, current.version)
    await loadDetail()
    ElMessage.success('网关已清空')
    emit('changed')
  } catch (error) {
    handleSubActionError(error, {})
  } finally {
    gatewayClearing.value = false
  }
}

// ---------- 保留地址：增（Contract §3.2）/ 删（Contract §3.3） ----------
const reservedFormRef = ref<FormInstance>()
const reservedSubmitting = ref(false)
const reservedForm = reactive({ start_ip: '', end_ip: '' })
const reservedServerError = ref('')

const reservedRule: FormItemRule = {
  required: true,
  validator: (_rule, _value: string, callback) => {
    if (!detail.value) {
      callback()
      return
    }
    callback(
      validateReservedRange(reservedForm.start_ip, reservedForm.end_ip, detail.value.cidr) ?? undefined,
    )
  },
  trigger: 'blur',
}
const reservedRules: Record<string, FormItemRule[]> = {
  start_ip: [reservedRule],
  end_ip: [reservedRule],
}

async function handleAddReserved(): Promise<void> {
  const current = detail.value
  if (!current) return
  reservedServerError.value = ''
  const valid = await reservedFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  reservedSubmitting.value = true
  try {
    await createReservedAddress(current.id, {
      start_ip: reservedForm.start_ip,
      end_ip: reservedForm.end_ip === '' ? null : reservedForm.end_ip,
    })
    ElMessage.success('保留地址已添加')
    reservedForm.start_ip = ''
    reservedForm.end_ip = ''
    await loadDetail()
    emit('changed')
  } catch (error) {
    handleSubActionError(error, {
      fields: ['start_ip', 'end_ip'],
      onFieldError: (m) => (reservedServerError.value = m),
    })
  } finally {
    reservedSubmitting.value = false
  }
}

async function handleDeleteReserved(row: ReservedAddress): Promise<void> {
  const current = detail.value
  if (!current) return
  const rangeText = row.is_range ? `${row.start_ip} – ${row.end_ip}` : row.start_ip
  try {
    await ElMessageBox.confirm(`确定删除保留地址 ${rangeText}？此操作不可恢复。`, '删除保留地址', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteReservedAddress(current.id, row.id)
    ElMessage.success('保留地址已删除')
    await loadDetail()
    emit('changed')
  } catch (error) {
    handleSubActionError(error, {})
  }
}
</script>

<template>
  <el-drawer v-model="visible" title="网段详情" size="600px" destroy-on-close>
    <div v-loading="loading" class="drawer-body">
      <el-alert
        v-if="loadError"
        type="error"
        :closable="false"
        show-icon
        :title="loadError"
        class="drawer-alert"
      >
        <el-button size="small" @click="loadDetail">重试</el-button>
      </el-alert>

      <template v-if="detail">
        <!-- 重叠风险提示（§4.6.5：仅提示、允许保存） -->
        <el-alert
          v-if="overlapText"
          type="warning"
          :closable="false"
          show-icon
          :title="overlapText"
          class="drawer-alert"
        />

        <!-- §6.5 全字段 -->
        <el-descriptions :column="1" border size="small" class="drawer-section">
          <el-descriptions-item label="所属集群">
            {{ detail.cluster_code }} {{ detail.cluster_name }}
          </el-descriptions-item>
          <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="IPv4 CIDR">
            <code class="segment-code">{{ detail.cidr }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="用途">{{ detail.purpose }}</el-descriptions-item>
          <el-descriptions-item label="技术类型">{{ detail.technology }}</el-descriptions-item>
          <el-descriptions-item label="VLAN">{{ detail.vlan ?? '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="自动分配范围">
            <code v-if="detail.auto_alloc_enabled" class="segment-code">
              {{ detail.auto_alloc_start }} – {{ detail.auto_alloc_end }}
            </code>
            <span v-else class="segment-muted">未启用</span>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatDateTime(detail.updated_at) }}</el-descriptions-item>
        </el-descriptions>

        <!-- 计数快照（§5 BQ-R：随记录变化的快照、非预占） -->
        <h4 class="drawer-heading">数量快照</h4>
        <el-descriptions :column="3" border size="small" class="drawer-section">
          <el-descriptions-item label="保留地址条目">
            {{ detail.reserved_address_count }}
          </el-descriptions-item>
          <el-descriptions-item label="已分配数量">
            {{ detail.allocated_count }}
            <span class="segment-muted">（当前阶段恒为 0）</span>
          </el-descriptions-item>
          <el-descriptions-item label="可自动分配数量">
            {{ detail.auto_assignable_count }}
          </el-descriptions-item>
        </el-descriptions>
        <p class="drawer-hint">可自动分配数量为当前查询时的快照，不预占地址、不保证下一次分配成功。</p>

        <!-- 网关：设置 / 显式清空（删除前置之一，BQ-O） -->
        <h4 class="drawer-heading">网关</h4>
        <p class="drawer-current">
          当前网关：
          <code v-if="detail.gateway" class="segment-code">{{ detail.gateway }}</code>
          <span v-else class="segment-muted">未设置</span>
        </p>
        <div v-if="canManage" class="drawer-gateway">
          <el-input
            v-model="gatewayInput"
            placeholder="新网关 IPv4，须落在 CIDR 内"
            class="drawer-gateway-input"
            @input="gatewayError = ''"
          />
          <el-button type="primary" :loading="gatewaySaving" @click="handleSaveGateway">
            保存网关
          </el-button>
          <el-button
            :loading="gatewayClearing"
            :disabled="!detail.gateway"
            @click="handleClearGateway"
          >
            显式清空网关
          </el-button>
          <div v-if="gatewayError" class="drawer-field-error">{{ gatewayError }}</div>
        </div>

        <!-- 保留地址（显式子项操作；删网段前须逐条删除，BQ-N/O） -->
        <h4 class="drawer-heading">保留地址（{{ detail.reserved_addresses.length }} 条）</h4>
        <el-table :data="detail.reserved_addresses" size="small" class="drawer-section">
          <el-table-column prop="start_ip" label="起始地址" width="140">
            <template #default="{ row }">
              <code class="segment-code">{{ row.start_ip }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="end_ip" label="结束地址" width="140">
            <template #default="{ row }">
              <code class="segment-code">{{ row.end_ip }}</code>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="80">
            <template #default="{ row }">{{ row.is_range ? '范围' : '单地址' }}</template>
          </el-table-column>
          <el-table-column label="添加时间" min-width="150">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column v-if="canManage" label="操作" width="70">
            <template #default="{ row }">
              <el-button link type="danger" @click="handleDeleteReserved(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无保留地址" :image-size="48" />
          </template>
        </el-table>
        <el-form
          v-if="canManage"
          ref="reservedFormRef"
          :model="reservedForm"
          :rules="reservedRules"
          inline
          class="drawer-reserved-form"
          @submit.prevent="handleAddReserved"
        >
          <el-form-item prop="start_ip" :error="reservedServerError || undefined">
            <el-input
              v-model="reservedForm.start_ip"
              placeholder="起始 IP，如 192.168.1.100"
              style="width: 170px"
              @input="reservedServerError = ''"
            />
          </el-form-item>
          <el-form-item prop="end_ip">
            <el-input
              v-model="reservedForm.end_ip"
              placeholder="结束 IP（留空 = 单地址）"
              style="width: 180px"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="reservedSubmitting" @click="handleAddReserved">
              添加保留地址
            </el-button>
          </el-form-item>
        </el-form>

        <!-- 「已分配 IP 及归属」空态占位（数据由 F006 提供） -->
        <h4 class="drawer-heading">已分配 IP 及归属</h4>
        <el-empty
          description="「已分配 IP 及归属」列表将由后续能力（IP 分配）提供；当前阶段该网段无已分配 IP（已分配数量恒为 0）。"
          :image-size="60"
          class="drawer-section"
        />
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.drawer-alert {
  margin-bottom: 12px;
}
.drawer-heading {
  margin: 16px 0 8px;
  font-size: 14px;
}
.drawer-section {
  margin-bottom: 4px;
}
.drawer-hint {
  margin: 4px 0 0;
  color: #909399;
  font-size: 12px;
}
.drawer-current {
  margin: 0 0 8px;
}
.drawer-gateway {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.drawer-gateway-input {
  width: 220px;
}
.drawer-field-error {
  width: 100%;
  color: #f56c6c;
  font-size: 12px;
  line-height: 1.4;
}
.drawer-reserved-form {
  margin-top: 8px;
}
.segment-code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
.segment-muted {
  color: #909399;
  font-size: 12px;
}
</style>
