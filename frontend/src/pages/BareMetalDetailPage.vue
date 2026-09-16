<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BARE_METAL_HARDWARE_FIELDS, getBareMetal } from '../api/bareMetals'
import type { BareMetalHardwareField, BareMetalRead } from '../api/bareMetals'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useBareMetalDelete } from '../composables/useBareMetalDelete'
import ErrorState from '../components/ErrorState.vue'
import BareMetalStatusTag from '../components/BareMetalStatusTag.vue'
import BareMetalFormDialog from '../components/BareMetalFormDialog.vue'

/**
 * 裸金属详情页（F002 产品页）。
 *
 * - 调用 GET /api/bare-metals/{id}（契约 §3.3，规范路径），展示全部 13 字段
 *   （契约 §2 封闭集合）：R-BM-007 七字段 null 渲染为「—」（与契约「返回 null
 *   而非省略」一致）；时间为不透明字符串原样展示；hostname 原样展示（契约 §7）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同状态
 *   （R-QUERY-004）；
 * - 状态修改入口（BareMetalFormDialog，PATCH 契约 §3.4）：status + R-BM-007
 *   七字段可编辑；hostname / cluster_id 不在 PATCH 可变集内，不提供编辑输入；
 * - 删除入口（ElPopconfirm）→ DELETE /api/bare-metals/{id}（契约 §3.5）。
 *   删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取 → 404 →
 *   既有独立 Not Found 态；409 按error.code 渲染冲突提示；401 交由全局会话
 *   失效处理；提交中 Loading 且禁重复提交。删除守卫由后端裁决（§21）；
 * - 修改 / 删除失败均按 error.code 分支渲染，不解析 message；
 * - F006：「查看虚拟机」入口 → 进入该宿主的虚拟机列表
 *   （GET /api/virtual-machines?bare_metal_id={id}，契约 f006-virtual-machine.md
 *   §3.2）；本页仍不呈现虚拟机数据（关联查询视图归 F010，F010 必须复用该能力）；
 * - F004：「查看网络接口」入口 → 进入该宿主的网络接口列表
 *   （GET /api/network-interfaces?bare_metal_id={id}，契约
 *   f004-network-interface.md §3.2）；本页仍不呈现网络接口数据（关联查询
 *   视图归 F010，F010 必须复用该能力）。
 */
const props = defineProps<{ bareMetalId: number }>()

const emit = defineEmits<{
  back: []
  openVirtualMachines: [bareMetalId: number]
  openNetworkInterfaces: [bareMetalId: number]
}>()

const { data, loading, error, run } = useAsyncQuery(() => getBareMetal(props.bareMetalId))

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useBareMetalDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
  // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态。
  onRemoved: () => run(),
})

onMounted(() => {
  void run()
})

/** R-BM-007 硬件字段展示标签。 */
const HARDWARE_LABELS: Record<BareMetalHardwareField, string> = {
  vendor: '厂商',
  model: '型号',
  serial_number: '序列号',
  cpu: 'CPU',
  memory: '内存',
  gpu: 'GPU',
  storage: '存储',
}

interface DetailItem {
  key: string
  label: string
  /** 展示值：硬件字段 null → 「—」；其余为契约原样值。 */
  value: string
  /** 状态字段以标签渲染（R-BM-003 原始值）。 */
  isStatus?: boolean
}

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const detailItems = computed<DetailItem[]>(() => {
  const bareMetal = data.value
  if (bareMetal === null) return []
  return [
    { key: 'id', label: 'ID', value: String(bareMetal.id) },
    { key: 'cluster_id', label: '所属集群 ID', value: String(bareMetal.cluster_id) },
    { key: 'hostname', label: 'hostname', value: bareMetal.hostname },
    { key: 'status', label: '状态', value: bareMetal.status, isStatus: true },
    ...BARE_METAL_HARDWARE_FIELDS.map((field) => ({
      key: field,
      label: HARDWARE_LABELS[field],
      value: bareMetal[field] ?? '—',
    })),
    { key: 'created_at', label: '登记时间', value: bareMetal.created_at },
    { key: 'updated_at', label: '更新时间', value: bareMetal.updated_at },
  ]
})

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（AC-30 / R-QUERY-004）；
 * - 首次请求尚未返回（data 与 error 均为空）按 Loading 处理，避免闪现空内容。
 */
const state = computed<'loading' | 'not-found' | 'error' | 'content'>(() => {
  if (loading.value) return 'loading'
  if (error.value !== null) {
    return error.value.code === 'NOT_FOUND' ? 'not-found' : 'error'
  }
  return data.value !== null ? 'content' : 'loading'
})

function backToList(): void {
  emit('back')
}

/** F006：进入该宿主的虚拟机列表（携带 bare_metal_id）。 */
function openVirtualMachines(): void {
  emit('openVirtualMachines', props.bareMetalId)
}

/** F004：进入该宿主的网络接口列表（携带 bare_metal_id）。 */
function openNetworkInterfaces(): void {
  emit('openNetworkInterfaces', props.bareMetalId)
}

/** 二次确认通过后删除当前裸金属；状态管理与错误渲染见 useBareMetalDelete。 */
function confirmDelete(): void {
  void requestDelete(props.bareMetalId)
}

// ---- 状态 / 硬件字段修改入口（PATCH） ----

const editDialogVisible = ref(false)

function handleUpdated(): void {
  // 保存成功 → 重新读取详情（data 更新为服务端返回的最新值）。
  void run()
}
</script>

<template>
  <main class="bare-metal-detail" :data-state="state">
    <header class="bare-metal-detail__header">
      <div class="bare-metal-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="bare-metal-detail__title">裸金属详情</h1>
      </div>
      <!-- 状态 / 硬件字段修改入口与删除入口：仅内容态出现；hostname / cluster_id
           不可变（契约 §3.4），不提供编辑；删除守卫由后端 409 裁决（§21）。
           F006「查看虚拟机」与 F004「查看网络接口」入口：跳转对应宿主过滤列表。 -->
      <div v-if="state === 'content'" class="bare-metal-detail__actions">
        <el-button type="primary" plain data-testid="open-virtual-machines" @click="openVirtualMachines">
          查看虚拟机
        </el-button>
        <el-button
          type="primary"
          plain
          data-testid="open-network-interfaces"
          @click="openNetworkInterfaces"
        >
          查看网络接口
        </el-button>
        <el-button type="primary" plain data-testid="open-edit-dialog" @click="editDialogVisible = true">
          编辑
        </el-button>
        <el-popconfirm
          title="确定删除该裸金属吗？删除后不可恢复。"
          confirm-button-text="删除"
          cancel-button-text="取消"
          confirm-button-type="danger"
          :width="200"
          @confirm="confirmDelete"
        >
          <template #reference>
            <el-button type="danger" plain :loading="deletingId !== null">删除</el-button>
          </template>
        </el-popconfirm>
      </div>
    </header>

    <section class="bare-metal-detail__body">
      <div v-if="state === 'loading'" class="bare-metal-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="bare-metal-detail__delete-error"
          :data-delete-error-code="deleteErrorView.code"
        >
          <el-alert
            type="error"
            :title="deleteErrorView.title"
            :description="deleteErrorView.description"
            show-icon
            closable
            @close="clearDeleteError"
          />
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item
            v-for="item in detailItems"
            :key="item.key"
            :label="item.label"
          >
            <BareMetalStatusTag v-if="item.isStatus" :status="item.value" />
            <template v-else>{{ item.value }}</template>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </section>

    <!-- 编辑表单（PATCH）：status + R-BM-007 七字段；hostname / cluster_id 不在其中。 -->
    <BareMetalFormDialog
      v-model="editDialogVisible"
      mode="edit"
      :bare-metal="data"
      @success="handleUpdated"
    />
  </main>
</template>

<style scoped>
.bare-metal-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.bare-metal-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.bare-metal-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bare-metal-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bare-metal-detail__title {
  margin: 0;
  font-size: 20px;
}

.bare-metal-detail__body {
  margin-top: 16px;
}

.bare-metal-detail__loading {
  padding: 8px 0;
}

.bare-metal-detail__delete-error {
  margin-bottom: 16px;
}
</style>
