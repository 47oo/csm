<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { listIpAddresses } from '../api/ipAddresses'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useIpAddressDelete } from '../composables/useIpAddressDelete'
import ListStates from '../components/ListStates.vue'
import IpAddressFormDialog from '../components/IpAddressFormDialog.vue'
import IpAddressAllocateDialog from '../components/IpAddressAllocateDialog.vue'

/**
 * IP 地址列表页（F005 产品页）。
 *
 * - 调用 GET /api/ip-addresses（契约 §3.2），可选 network_interface_id 限定
 *   （R-QUERY-004 的 F005 侧 canonical 能力，供「该网络接口 IP」入口与
 *   F010 复用，F010 不得另写一份过滤）；
 * - 三态互不相同（AC-41）：Loading / Empty（200 + items 为空，「暂无 IP
 *   地址」）/ Error（按 error.code 分支渲染，不解析 message）；
 * - Empty 与 Not Found 可区分（R-QUERY-004）：父 NIC 存在但无活跃 IP →
 *   200 + items == []（Empty 态）；父 NIC 不存在或已逻辑删除 → 404
 *   NOT_FOUND（Error 态渲染「未找到资源」）；
 * - 每行提供详情 / 删除入口；删除二次确认（ElPopconfirm）→ DELETE
 *   /api/ip-addresses/{id}（契约 §3.5）。204 / 404 同构刷新；409 按
 *   error.code 渲染；401 交由全局会话失效处理；提交中 Loading 且禁重复提交。
 *   删除守卫由后端裁决（§21），前端不预判、不禁用、不隐藏入口；
 * - 登记表单入口（IpAddressFormDialog，POST）：父 NIC 存在性 / 活跃性（404）、
 *   字段合法性（400）、同 Cluster 唯一性（409 DUPLICATE）均由服务端裁决，
 *   前端不预判、不做唯一性预检；
 * - 分配入口（F021，IpAddressAllocateDialog）：自动分配（POST
 *   /api/ip-addresses/allocate）与手动分配（POST
 *   /api/ip-addresses/allocate-manual）两个动作；NIC 上下文预选目标 NIC
 *  （对话框只读展示），全局入口在对话框内先选择目标 NIC；手动输入仅做
 *   基础必填（空串 = 表单未完成），不做 IPv4 格式 / 修剪 / 范围 / 占用
 *   预判（§21，业务裁决全在服务端）；错误按 error.code（结合
 *   details[].code）分支；成功 → 刷新列表并在对话框结果区展示新
 *   ip_address 与 id；401 交由全局会话失效处理；
 * - 时间字段按不透明字符串原样展示（契约 §2）；ip_address 字面值原样展示
 *   （契约 §7）；本页无状态列 / 状态筛选（Q-002=B，IP 不设状态）、无
 *   Cluster 列（Cluster 归属不暴露，NQ-4；聚合呈现归 F010）；
 * - 分页参数合法性由服务端校验（400 VALIDATION_ERROR → Error 态渲染）；
 *   本页仅提供合法区间内的固定选项。
 */
const props = withDefaults(defineProps<{ networkInterfaceId?: number | null }>(), {
  networkInterfaceId: null,
})

const emit = defineEmits<{
  openDetail: [ipAddressId: number]
  back: []
}>()

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

const {
  data: ipAddressData,
  loading,
  error,
  run,
} = useAsyncQuery(() =>
  listIpAddresses({
    page: page.value,
    page_size: pageSize.value,
    networkInterfaceId: props.networkInterfaceId ?? undefined,
  }),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useIpAddressDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 刷新列表。
  onRemoved: () => run(),
})

const ipAddresses = computed(() => ipAddressData.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容。
 */
const isLoading = computed(
  () => loading.value || (ipAddressData.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（api-conventions.md §7）。 */
const listEmpty = computed(
  () => ipAddressData.value !== null && ipAddressData.value.items.length === 0,
)

const total = computed(() => ipAddressData.value?.total ?? 0)

/** 过滤上下文文案：Empty 态与标题下的过滤标签随 networkInterfaceId 区分。 */
const nicFilterLabel = computed(() =>
  props.networkInterfaceId !== null ? `网络接口 #${props.networkInterfaceId}` : null,
)
const emptyDescription = computed(() =>
  props.networkInterfaceId !== null ? '该网络接口暂无 IP 地址' : '暂无 IP 地址',
)
const backLabel = computed(() =>
  props.networkInterfaceId !== null ? '返回网络接口详情' : '返回集群列表',
)

onMounted(() => {
  void run()
})

// App 视图切换可能只改变 networkInterfaceId 而复用本组件（如从「该网络接口
// IP」切到全局列表）：回到第 1 页并重新查询。
watch(
  () => props.networkInterfaceId,
  () => {
    page.value = 1
    void run()
  },
)

function refresh(): void {
  void run()
}

function handlePageChange(next: number): void {
  page.value = next
  void run()
}

function handleSizeChange(size: number): void {
  pageSize.value = size
  page.value = 1
  void run()
}

function openDetail(ipAddressId: number): void {
  emit('openDetail', ipAddressId)
}

function goBack(): void {
  emit('back')
}

/** 二次确认通过后删除该行 IP 地址；状态管理与错误渲染见 useIpAddressDelete。 */
function confirmDelete(ipAddressId: number): void {
  void requestDelete(ipAddressId)
}

// ---- 登记入口（POST /api/ip-addresses） ----

const createDialogVisible = ref(false)

function handleCreated(): void {
  // 登记成功 → 刷新列表（新记录按 id 升序可能位于其他页，刷新当前页即可）。
  void run()
}

// ---- 分配入口（F021，POST /api/ip-addresses/allocate[-manual]） ----

const allocateDialogVisible = ref(false)
const allocateMode = ref<'auto' | 'manual'>('auto')

/** 打开分配对话框；目标 NIC 由 networkInterfaceId 预设（null = 对话框内先选择）。 */
function openAllocate(mode: 'auto' | 'manual'): void {
  allocateMode.value = mode
  allocateDialogVisible.value = true
}

function handleAllocated(): void {
  // 分配成功 → 刷新列表（新记录按 id 升序可能位于其他页，刷新当前页即可）。
  void run()
}
</script>

<template>
  <main class="ip-address-list" :data-nic-filter="networkInterfaceId ?? 'none'">
    <header class="ip-address-list__header">
      <div class="ip-address-list__nav">
        <el-button @click="goBack">{{ backLabel }}</el-button>
        <h1 class="ip-address-list__title">
          IP 地址列表
          <el-tag v-if="nicFilterLabel !== null" class="ip-address-list__filter">
            {{ nicFilterLabel }}
          </el-tag>
        </h1>
      </div>
      <div class="ip-address-list__actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
        <!-- F021 分配入口：NIC 上下文与全局入口均提供自动 / 手动两个动作；
             地址池耗尽 / 范围 / 占用等业务裁决全在服务端（§21），
             不预判、不禁用入口。 -->
        <el-button
          type="primary"
          plain
          data-testid="open-allocate-auto"
          @click="openAllocate('auto')"
        >
          自动分配 IP
        </el-button>
        <el-button
          type="primary"
          plain
          data-testid="open-allocate-manual"
          @click="openAllocate('manual')"
        >
          手动分配 IP
        </el-button>
        <el-button type="primary" data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记 IP 地址
        </el-button>
      </div>
    </header>

    <section class="ip-address-list__body">
      <ListStates
        :loading="isLoading"
        :error="error"
        :empty="listEmpty"
        :empty-description="emptyDescription"
      >
        <!-- 删除失败提示（409 等）：仅在内容态与表格同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="ip-address-list__delete-error"
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

        <!-- 列集合封闭：id / network_interface_id / ip_address / updated_at；
             无状态列（Q-002=B）、无 Cluster 列（NQ-4，聚合呈现归 F010）。 -->
        <el-table :data="ipAddresses" class="ip-address-list__table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="network_interface_id" label="所属网络接口 ID" width="170" />
          <!-- ip_address / updated_at 均为契约原样值，不做任何变换（契约 §2 / §7）。 -->
          <el-table-column prop="ip_address" label="IP 地址" min-width="180" />
          <el-table-column prop="updated_at" label="更新时间" min-width="200" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
              <!-- 删除入口：对所有行开放；删除守卫由后端裁决（§21），
                   前端不预判（不禁用、不隐藏任何行的删除入口）。 -->
              <el-popconfirm
                title="确定删除该 IP 地址吗？删除后不可恢复。"
                confirm-button-text="删除"
                cancel-button-text="取消"
                confirm-button-type="danger"
                :width="200"
                @confirm="confirmDelete(row.id)"
              >
                <template #reference>
                  <el-button
                    link
                    type="danger"
                    :loading="deletingId === row.id"
                    :disabled="deletingId !== null"
                  >
                    删除
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <div class="ip-address-list__pagination">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </ListStates>
    </section>

    <!-- 登记表单（POST）：父 NIC 存在性 / 字段合法性 / 同 Cluster 唯一性
         均由服务端裁决；从 NIC 过滤列表进入时预选该网络接口。 -->
    <IpAddressFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-network-interface-id="networkInterfaceId"
      @success="handleCreated"
    />

    <!-- F021 分配对话框（自动 / 手动）：成功 → 刷新列表并在对话框结果区展示
         新 ip_address 与 id；错误按 error.code（结合 details[].code）分支，
         见组件头注。 -->
    <IpAddressAllocateDialog
      v-model="allocateDialogVisible"
      :mode="allocateMode"
      :preset-network-interface-id="networkInterfaceId"
      @success="handleAllocated"
    />
  </main>
</template>

<style scoped>
.ip-address-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.ip-address-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ip-address-list__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ip-address-list__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ip-address-list__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.ip-address-list__body {
  margin-top: 16px;
}

.ip-address-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.ip-address-list__delete-error {
  margin-bottom: 16px;
}
</style>
