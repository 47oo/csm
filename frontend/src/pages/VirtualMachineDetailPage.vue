<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { VIRTUAL_MACHINE_OPTIONAL_FIELDS, getVirtualMachine } from '../api/virtualMachines'
import type { VirtualMachineOptionalField, VirtualMachineRead } from '../api/virtualMachines'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useVirtualMachineDelete } from '../composables/useVirtualMachineDelete'
import ErrorState from '../components/ErrorState.vue'
import VirtualMachineFormDialog from '../components/VirtualMachineFormDialog.vue'

/**
 * 虚拟机详情页（F006 产品页）。
 *
 * - 调用 GET /api/virtual-machines/{id}（契约 §3.3，规范路径），展示全部 11 字段
 *   （契约 §2 封闭集合）：R-VM-006 六字段 null 渲染为「—」（与契约「返回 null
 *   而非省略」一致）；时间为不透明字符串原样展示；name 原样展示（契约 §7）；
 *   无状态字段展示 / 编辑（Q-002=B，VM 无状态）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同状态
 *   （R-QUERY-004）；
 * - 可选字段修改入口（VirtualMachineFormDialog，PATCH 契约 §3.4）：R-VM-006
 *   六字段可编辑；name / bare_metal_id 不在 PATCH 可变集内（NQ-1，登记后
 *   不可变），不提供编辑输入；
 * - 删除入口（ElPopconfirm）→ DELETE /api/virtual-machines/{id}（契约 §3.5）。
 *   删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取 → 404 →
 *   既有独立 Not Found 态；409 按 error.code 渲染冲突提示；401 交由全局会话
 *   失效处理；提交中 Loading 且禁重复提交。删除守卫由后端裁决（§21）；
 * - 修改 / 删除失败均按 error.code 分支渲染，不解析 message。
 */
const props = defineProps<{ virtualMachineId: number }>()

const emit = defineEmits<{ back: [] }>()

const { data, loading, error, run } = useAsyncQuery(() =>
  getVirtualMachine(props.virtualMachineId),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useVirtualMachineDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
  // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态。
  onRemoved: () => run(),
})

onMounted(() => {
  void run()
})

/** R-VM-006 可选字段展示标签。 */
const OPTIONAL_LABELS: Record<VirtualMachineOptionalField, string> = {
  cpu: 'CPU',
  memory: '内存',
  disk: '磁盘',
  os: '操作系统',
  hypervisor: 'Hypervisor',
  owner: '负责人',
}

interface DetailItem {
  key: string
  label: string
  /** 展示值：可选字段 null → 「—」；其余为契约原样值。 */
  value: string
}

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const detailItems = computed<DetailItem[]>(() => {
  const virtualMachine = data.value
  if (virtualMachine === null) return []
  return [
    { key: 'id', label: 'ID', value: String(virtualMachine.id) },
    { key: 'bare_metal_id', label: '宿主裸金属 ID', value: String(virtualMachine.bare_metal_id) },
    { key: 'name', label: '名称', value: virtualMachine.name },
    ...VIRTUAL_MACHINE_OPTIONAL_FIELDS.map((field) => ({
      key: field,
      label: OPTIONAL_LABELS[field],
      value: virtualMachine[field] ?? '—',
    })),
    { key: 'created_at', label: '登记时间', value: virtualMachine.created_at },
    { key: 'updated_at', label: '更新时间', value: virtualMachine.updated_at },
  ]
})

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（AC-32 / R-QUERY-004）；
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

/** 二次确认通过后删除当前虚拟机；状态管理与错误渲染见 useVirtualMachineDelete。 */
function confirmDelete(): void {
  void requestDelete(props.virtualMachineId)
}

// ---- 可选字段修改入口（PATCH） ----

const editDialogVisible = ref(false)

function handleUpdated(): void {
  // 保存成功 → 重新读取详情（data 更新为服务端返回的最新值）。
  void run()
}
</script>

<template>
  <main class="virtual-machine-detail" :data-state="state">
    <header class="virtual-machine-detail__header">
      <div class="virtual-machine-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="virtual-machine-detail__title">虚拟机详情</h1>
      </div>
      <!-- 可选字段修改入口与删除入口：仅内容态出现；name / bare_metal_id 不可变
           （契约 §3.4 / NQ-1），不提供编辑；删除守卫由后端 409 裁决（§21）。 -->
      <div v-if="state === 'content'" class="virtual-machine-detail__actions">
        <el-button type="primary" plain data-testid="open-edit-dialog" @click="editDialogVisible = true">
          编辑
        </el-button>
        <el-popconfirm
          title="确定删除该虚拟机吗？删除后不可恢复。"
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

    <section class="virtual-machine-detail__body">
      <div v-if="state === 'loading'" class="virtual-machine-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="virtual-machine-detail__delete-error"
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
            {{ item.value }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </section>

    <!-- 编辑表单（PATCH）：R-VM-006 六字段；name / bare_metal_id 不在其中。 -->
    <VirtualMachineFormDialog
      v-model="editDialogVisible"
      mode="edit"
      :virtual-machine="data"
      @success="handleUpdated"
    />
  </main>
</template>

<style scoped>
.virtual-machine-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.virtual-machine-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.virtual-machine-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.virtual-machine-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.virtual-machine-detail__title {
  margin: 0;
  font-size: 20px;
}

.virtual-machine-detail__body {
  margin-top: 16px;
}

.virtual-machine-detail__loading {
  padding: 8px 0;
}

.virtual-machine-detail__delete-error {
  margin-bottom: 16px;
}
</style>
