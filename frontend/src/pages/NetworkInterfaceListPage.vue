<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { listNetworkInterfaces } from '../api/networkInterfaces'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useNetworkInterfaceDelete } from '../composables/useNetworkInterfaceDelete'
import ListStates from '../components/ListStates.vue'
import NetworkInterfaceFormDialog from '../components/NetworkInterfaceFormDialog.vue'

/**
 * 网络接口列表页（F004 产品页）。
 *
 * - 调用 GET /api/network-interfaces（契约 §3.2），可选 bare_metal_id 限定
 *   （R-QUERY-003 的 F004 侧 canonical 能力，供「该宿主网络接口」入口与
 *   F010 复用，F010 不得另写一份过滤）；
 * - 三态互不相同（AC-34）：Loading / Empty（200 + items 为空，「暂无网络接口」）/
 *   Error（按 error.code 分支渲染，不解析 message）；
 * - Empty 与 Not Found 可区分（R-QUERY-004）：宿主存在但无活跃 NIC → 200 +
 *   items == []（Empty 态）；宿主不存在或已逻辑删除 → 404 NOT_FOUND
 *   （Error 态渲染「未找到资源」）；
 * - 每行提供详情 / 删除入口；删除二次确认（ElPopconfirm）→ DELETE
 *   /api/network-interfaces/{id}（契约 §3.5）。204 / 404 同构刷新；409 按
 *   error.code 渲染；401 交由全局会话失效处理；提交中 Loading 且禁重复提交。
 *   删除守卫由后端裁决（§21），前端不预判、不禁用、不隐藏入口；
 * - 登记表单入口（NetworkInterfaceFormDialog，POST）：枚举封闭集合 / 宿主
 *   存在性均由服务端裁决，前端不预判；
 * - 时间字段按不透明字符串原样展示（契约 §2）；name 原样展示（契约 §7）；
 *   本页无状态列 / 状态筛选（Q-002=B，NIC 不设状态）；
 * - 分页参数合法性由服务端校验（400 VALIDATION_ERROR → Error 态渲染）；
 *   本页仅提供合法区间内的固定选项。
 */
const props = withDefaults(defineProps<{ bareMetalId?: number | null }>(), {
  bareMetalId: null,
})

const emit = defineEmits<{
  openDetail: [networkInterfaceId: number]
  back: []
}>()

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

const {
  data: networkInterfaceData,
  loading,
  error,
  run,
} = useAsyncQuery(() =>
  listNetworkInterfaces({
    page: page.value,
    page_size: pageSize.value,
    bareMetalId: props.bareMetalId ?? undefined,
  }),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useNetworkInterfaceDelete(
  {
    // 删除成功（204）或目标已不存在（404，两者不区分）→ 刷新列表。
    onRemoved: () => run(),
  },
)

const networkInterfaces = computed(() => networkInterfaceData.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容。
 */
const isLoading = computed(
  () => loading.value || (networkInterfaceData.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（api-conventions.md §7）。 */
const listEmpty = computed(
  () => networkInterfaceData.value !== null && networkInterfaceData.value.items.length === 0,
)

const total = computed(() => networkInterfaceData.value?.total ?? 0)

/** 过滤上下文文案：Empty 态与标题下的过滤标签随 bareMetalId 区分。 */
const hostFilterLabel = computed(() =>
  props.bareMetalId !== null ? `裸金属 #${props.bareMetalId}` : null,
)
const emptyDescription = computed(() =>
  props.bareMetalId !== null ? '该裸金属暂无网络接口' : '暂无网络接口',
)
const backLabel = computed(() =>
  props.bareMetalId !== null ? '返回裸金属详情' : '返回集群列表',
)

onMounted(() => {
  void run()
})

// App 视图切换可能只改变 bareMetalId 而复用本组件（如从「该宿主网络接口」切到
// 全局列表）：回到第 1 页并重新查询。
watch(
  () => props.bareMetalId,
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

function openDetail(networkInterfaceId: number): void {
  emit('openDetail', networkInterfaceId)
}

function goBack(): void {
  emit('back')
}

/** 二次确认通过后删除该行网络接口；状态管理与错误渲染见 useNetworkInterfaceDelete。 */
function confirmDelete(networkInterfaceId: number): void {
  void requestDelete(networkInterfaceId)
}

// ---- 登记入口（POST /api/network-interfaces） ----

const createDialogVisible = ref(false)

function handleCreated(): void {
  // 登记成功 → 刷新列表（新记录按 id 升序可能位于其他页，刷新当前页即可）。
  void run()
}
</script>

<template>
  <main class="network-interface-list" :data-host-filter="bareMetalId ?? 'none'">
    <header class="network-interface-list__header">
      <div class="network-interface-list__nav">
        <el-button @click="goBack">{{ backLabel }}</el-button>
        <h1 class="network-interface-list__title">
          网络接口列表
          <el-tag v-if="hostFilterLabel !== null" class="network-interface-list__filter">
            {{ hostFilterLabel }}
          </el-tag>
        </h1>
      </div>
      <div class="network-interface-list__actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
        <el-button type="primary" data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记网络接口
        </el-button>
      </div>
    </header>

    <section class="network-interface-list__body">
      <ListStates
        :loading="isLoading"
        :error="error"
        :empty="listEmpty"
        :empty-description="emptyDescription"
      >
        <!-- 删除失败提示（409 等）：仅在内容态与表格同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="network-interface-list__delete-error"
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

        <el-table :data="networkInterfaces" class="network-interface-list__table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="bare_metal_id" label="宿主裸金属 ID" width="140" />
          <!-- name / technology_type / purpose / created_at / updated_at 均为契约
               原样值，不做任何变换（枚举不做中文映射，契约 §1.5）。 -->
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="technology_type" label="技术类型" min-width="120" />
          <el-table-column prop="purpose" label="用途" min-width="120" />
          <el-table-column prop="updated_at" label="更新时间" min-width="200" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
              <!-- 删除入口：对所有行开放；删除守卫由后端 409 裁决（§21），
                   前端不预判（不禁用、不隐藏任何行的删除入口）。 -->
              <el-popconfirm
                title="确定删除该网络接口吗？删除后不可恢复。"
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

        <div class="network-interface-list__pagination">
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

    <!-- 登记表单（POST）：枚举封闭集合 / 宿主存在性 / 字段合法性由服务端裁决。 -->
    <NetworkInterfaceFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-bare-metal-id="bareMetalId"
      @success="handleCreated"
    />
  </main>
</template>

<style scoped>
.network-interface-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.network-interface-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.network-interface-list__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.network-interface-list__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.network-interface-list__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.network-interface-list__body {
  margin-top: 16px;
}

.network-interface-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.network-interface-list__delete-error {
  margin-bottom: 16px;
}
</style>
