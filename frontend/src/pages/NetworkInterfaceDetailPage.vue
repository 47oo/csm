<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getNetworkInterface } from '../api/networkInterfaces'
import type { NetworkInterfaceRead } from '../api/networkInterfaces'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useNetworkInterfaceDelete } from '../composables/useNetworkInterfaceDelete'
import ErrorState from '../components/ErrorState.vue'
import NetworkInterfaceFormDialog from '../components/NetworkInterfaceFormDialog.vue'

/**
 * 网络接口详情页（F004 产品页）。
 *
 * - 调用 GET /api/network-interfaces/{id}（契约 §3.3，规范路径），展示全部
 *   7 字段（契约 §2 封闭集合）；时间为不透明字符串原样展示；name 原样展示
 *   （契约 §7）；枚举按内部字面值原样展示，不做中文映射（契约 §1.5）；
 *   无状态字段展示 / 编辑（Q-002=B，NIC 不设状态）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同状态
 *   （R-QUERY-004）；
 * - 枚举修改入口（NetworkInterfaceFormDialog，PATCH 契约 §3.4）：
 *   technology_type / purpose 可编辑；name / bare_metal_id 不在 PATCH 可变集内
 *   （NQ-3，登记后不可变），不提供编辑输入；
 * - 删除入口（ElPopconfirm）→ DELETE /api/network-interfaces/{id}（契约 §3.5）。
 *   删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取 → 404 →
 *   既有独立 Not Found 态；409 按 error.code 渲染冲突提示；401 交由全局会话
 *   失效处理；提交中 Loading 且禁重复提交。删除守卫由后端裁决（§21）；
 * - 修改 / 删除失败均按 error.code 分支渲染，不解析 message；
 * - F005：「查看 IP 地址」入口 → 进入该网络接口的 IP 地址列表
 *   （GET /api/ip-addresses?network_interface_id={id}，契约
 *   f005-ip-address.md §3.2）；本页仍不呈现 IP 数据（关联查询视图归 F010，
 *   F010 必须复用该能力）。
 */
const props = defineProps<{ networkInterfaceId: number }>()

const emit = defineEmits<{
  back: []
  openIpAddresses: [networkInterfaceId: number]
}>()

const { data, loading, error, run } = useAsyncQuery(() =>
  getNetworkInterface(props.networkInterfaceId),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useNetworkInterfaceDelete(
  {
    // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
    // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态。
    onRemoved: () => run(),
  },
)

onMounted(() => {
  void run()
})

interface DetailItem {
  key: string
  label: string
  /** 展示值：契约原样值，不做任何变换。 */
  value: string
}

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const detailItems = computed<DetailItem[]>(() => {
  const networkInterface: NetworkInterfaceRead | null = data.value
  if (networkInterface === null) return []
  return [
    { key: 'id', label: 'ID', value: String(networkInterface.id) },
    {
      key: 'bare_metal_id',
      label: '宿主裸金属 ID',
      value: String(networkInterface.bare_metal_id),
    },
    { key: 'name', label: '名称', value: networkInterface.name },
    { key: 'technology_type', label: '技术类型', value: networkInterface.technology_type },
    { key: 'purpose', label: '用途', value: networkInterface.purpose },
    { key: 'created_at', label: '登记时间', value: networkInterface.created_at },
    { key: 'updated_at', label: '更新时间', value: networkInterface.updated_at },
  ]
})

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（AC-34 / R-QUERY-004）；
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

/** F005：进入该网络接口的 IP 地址列表（携带 network_interface_id）。 */
function openIpAddresses(): void {
  emit('openIpAddresses', props.networkInterfaceId)
}

/** 二次确认通过后删除当前网络接口；状态管理与错误渲染见 useNetworkInterfaceDelete。 */
function confirmDelete(): void {
  void requestDelete(props.networkInterfaceId)
}

// ---- 枚举修改入口（PATCH） ----

const editDialogVisible = ref(false)

function handleUpdated(): void {
  // 保存成功 → 重新读取详情（data 更新为服务端返回的最新值）。
  void run()
}
</script>

<template>
  <main class="network-interface-detail" :data-state="state">
    <header class="network-interface-detail__header">
      <div class="network-interface-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="network-interface-detail__title">网络接口详情</h1>
      </div>
      <!-- 枚举修改入口与删除入口：仅内容态出现；name / bare_metal_id 不可变
           （契约 §3.4 / NQ-3），不提供编辑；删除守卫由后端 409 裁决（§21）。
           F005「查看 IP 地址」入口：跳转该网络接口的 IP 过滤列表。 -->
      <div v-if="state === 'content'" class="network-interface-detail__actions">
        <el-button
          type="primary"
          plain
          data-testid="open-ip-addresses"
          @click="openIpAddresses"
        >
          查看 IP 地址
        </el-button>
        <el-button type="primary" plain data-testid="open-edit-dialog" @click="editDialogVisible = true">
          编辑
        </el-button>
        <el-popconfirm
          title="确定删除该网络接口吗？删除后不可恢复。"
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

    <section class="network-interface-detail__body">
      <div v-if="state === 'loading'" class="network-interface-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="network-interface-detail__delete-error"
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

    <!-- 编辑表单（PATCH）：仅 technology_type / purpose；name / bare_metal_id 不在其中。 -->
    <NetworkInterfaceFormDialog
      v-model="editDialogVisible"
      mode="edit"
      :network-interface="data"
      @success="handleUpdated"
    />
  </main>
</template>

<style scoped>
.network-interface-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.network-interface-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.network-interface-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.network-interface-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.network-interface-detail__title {
  margin: 0;
  font-size: 20px;
}

.network-interface-detail__body {
  margin-top: 16px;
}

.network-interface-detail__loading {
  padding: 8px 0;
}

.network-interface-detail__delete-error {
  margin-bottom: 16px;
}
</style>
