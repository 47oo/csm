<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CONTAINER_CARRIER_TYPES, listContainers } from '../api/containers'
import type { ContainerCarrier, ContainerCarrierType } from '../api/containers'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useContainerDelete } from '../composables/useContainerDelete'
import ListStates from '../components/ListStates.vue'
import ContainerFormDialog from '../components/ContainerFormDialog.vue'

/**
 * 容器列表页（F007 产品页）。
 *
 * - 调用 GET /api/containers（契约 §4.2）；本页提供载体筛选（carrier_type +
 *   carrier_id 成对，契约 §4.2：两者必须同时提供，仅提供其一 → 400 VALIDATION_
 *   ERROR，故「筛选」按钮在筛选未填完整时禁用 —— 这不是载体存在性预判（§21）：
 *   任何已填写的载体对都直接提交，由服务端裁决载体不存在 / 已删 / 类型与标识
 *   不一致 → 404 渲染）；
 * - 三态互不相同（AC-44）：Loading / Empty（200 + items 为空，「暂无容器」）/
 *   Error（按 error.code 分支渲染，不解析 message）；
 * - Empty 与 Not Found 可区分（R-QUERY-004 / AC-26）：载体存在但无活跃
 *   Container → 200 + items == []（Empty 态，「该载体暂无容器」）；载体不存在 /
 *   已逻辑删除 / 类型与标识不一致 → 404 NOT_FOUND（Error 态渲染「未找到资源」）；
 * - 每行提供详情 / 删除入口；删除二次确认（ElPopconfirm）→ DELETE
 *   /api/containers/{id}（契约 §4.5）。204 / 404 同构刷新；409 按 error.code
 *   渲染；401 交由全局会话失效处理；提交中 Loading 且禁重复提交。删除守卫由
 *   后端裁决（§21），前端不预判、不禁用、不隐藏入口；
 * - 登记表单入口（ContainerFormDialog，POST）：载体内 name 唯一性 / 载体
 *   存在性均由服务端裁决，前端不预判；从已筛选的载体打开时预选该载体（可改选）；
 * - 时间字段按不透明字符串原样展示（契约 §2）；name 原样展示（契约 §8）；
 *   载体类型按契约原样枚举值展示（不发明领域文案）；本页无状态列 / 状态筛选
 *   （Q-002=B，AC-23）、无 Cluster 列 / Cluster 筛选（R-CONTAINER-002，AC-21）；
 * - 分页参数合法性由服务端校验（400 VALIDATION_ERROR → Error 态渲染）；
 *   本页仅提供合法区间内的固定选项。
 */
const emit = defineEmits<{
  openDetail: [containerId: number]
  back: []
}>()

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

// ---- 载体筛选（carrier_type + carrier_id 成对，契约 §4.2） ----

/** 筛选输入（未应用）：载体类型与载体 ID 均已填写时筛选才可应用（成对规则）。 */
const filterCarrierType = ref<ContainerCarrierType | null>(null)
const filterCarrierId = ref<number | null>(null)

/** 已应用的载体筛选；null = 全部活跃 Container。查询只依据该状态。 */
const appliedCarrier = ref<ContainerCarrier | null>(null)

const filterApplyDisabled = computed(
  () => filterCarrierType.value === null || filterCarrierId.value === null,
)

function applyFilter(): void {
  const carrierType = filterCarrierType.value
  const carrierId = filterCarrierId.value
  if (carrierType === null || carrierId === null) return
  appliedCarrier.value = { carrier_type: carrierType, carrier_id: carrierId }
  page.value = 1
  void run()
}

function clearFilter(): void {
  filterCarrierType.value = null
  filterCarrierId.value = null
  appliedCarrier.value = null
  page.value = 1
  void run()
}

const {
  data: containerData,
  loading,
  error,
  run,
} = useAsyncQuery(() =>
  listContainers({
    page: page.value,
    page_size: pageSize.value,
    carrier: appliedCarrier.value ?? undefined,
  }),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useContainerDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 刷新列表。
  onRemoved: () => run(),
})

const containers = computed(() => containerData.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容。
 */
const isLoading = computed(
  () => loading.value || (containerData.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（api-conventions.md §7）。 */
const listEmpty = computed(
  () => containerData.value !== null && containerData.value.items.length === 0,
)

const total = computed(() => containerData.value?.total ?? 0)

/** 过滤上下文文案：Empty 态与标题下的过滤标签随载体筛选区分。 */
const carrierFilterLabel = computed(() =>
  appliedCarrier.value !== null
    ? `载体 ${appliedCarrier.value.carrier_type} #${appliedCarrier.value.carrier_id}`
    : null,
)
const emptyDescription = computed(() =>
  appliedCarrier.value !== null ? '该载体暂无容器' : '暂无容器',
)

onMounted(() => {
  void run()
})

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

function openDetail(containerId: number): void {
  emit('openDetail', containerId)
}

function goBack(): void {
  emit('back')
}

/** 二次确认通过后删除该行容器；状态管理与错误渲染见 useContainerDelete。 */
function confirmDelete(containerId: number): void {
  void requestDelete(containerId)
}

// ---- 登记入口（POST /api/containers） ----

const createDialogVisible = ref(false)

function handleCreated(): void {
  // 登记成功 → 刷新列表（新记录按 id 升序可能位于其他页，刷新当前页即可）。
  void run()
}
</script>

<template>
  <main
    class="container-list"
    :data-carrier-filter="
      appliedCarrier !== null
        ? `${appliedCarrier.carrier_type}:${appliedCarrier.carrier_id}`
        : 'none'
    "
  >
    <header class="container-list__header">
      <div class="container-list__nav">
        <el-button @click="goBack">返回集群列表</el-button>
        <h1 class="container-list__title">
          容器列表
          <el-tag v-if="carrierFilterLabel !== null" class="container-list__filter">
            {{ carrierFilterLabel }}
          </el-tag>
        </h1>
      </div>
      <div class="container-list__actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
        <el-button type="primary" data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记容器
        </el-button>
      </div>
    </header>

    <!-- 载体筛选（契约 §4.2：carrier_type 与 carrier_id 必须成对出现；
         载体存在性由服务端裁决，前端不预判）。 -->
    <section class="container-list__filter-bar">
      <el-select
        v-model="filterCarrierType"
        class="container-list__filter-type"
        placeholder="载体类型"
        data-testid="container-filter-type"
      >
        <el-option
          v-for="carrierType in CONTAINER_CARRIER_TYPES"
          :key="carrierType"
          :label="carrierType"
          :value="carrierType"
        />
      </el-select>
      <el-input-number
        v-model="filterCarrierId"
        class="container-list__filter-id"
        placeholder="载体 ID"
        :controls="false"
        data-testid="container-filter-id"
      />
      <el-button
        type="primary"
        plain
        data-testid="container-filter-apply"
        :disabled="filterApplyDisabled"
        @click="applyFilter"
      >
        筛选
      </el-button>
      <el-button data-testid="container-filter-clear" @click="clearFilter">重置</el-button>
    </section>

    <section class="container-list__body">
      <ListStates
        :loading="isLoading"
        :error="error"
        :empty="listEmpty"
        :empty-description="emptyDescription"
      >
        <!-- 删除失败提示（409 等）：仅在内容态与表格同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="container-list__delete-error"
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

        <el-table :data="containers" class="container-list__table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="carrier_type" label="载体类型" width="160" />
          <el-table-column prop="carrier_id" label="载体 ID" width="100" />
          <!-- name / created_at / updated_at 均为契约原样值，不做任何变换。 -->
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="updated_at" label="更新时间" min-width="200" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
              <!-- 删除入口：对所有行开放；删除守卫由后端 409 裁决（§21），
                   前端不预判（不禁用、不隐藏任何行的删除入口）。 -->
              <el-popconfirm
                title="确定删除该容器吗？删除后不可恢复。"
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

        <div class="container-list__pagination">
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

    <!-- 登记表单（POST）：载体内 name 唯一性 / 载体存在性 / 字段合法性由服务端裁决。 -->
    <ContainerFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-carrier="appliedCarrier"
      @success="handleCreated"
    />
  </main>
</template>

<style scoped>
.container-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.container-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.container-list__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.container-list__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.container-list__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.container-list__filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}

.container-list__filter-type {
  width: 180px;
}

.container-list__filter-id {
  width: 140px;
}

.container-list__body {
  margin-top: 16px;
}

.container-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.container-list__delete-error {
  margin-bottom: 16px;
}
</style>
