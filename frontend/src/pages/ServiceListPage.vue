<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { SERVICE_CARRIER_TYPES, listServices } from '../api/services'
import type { ServiceCarrier, ServiceCarrierType } from '../api/services'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useServiceDelete } from '../composables/useServiceDelete'
import ListStates from '../components/ListStates.vue'
import ServiceFormDialog from '../components/ServiceFormDialog.vue'

/**
 * Service 列表页（F008 产品页）。
 *
 * - 调用 GET /api/services（契约 §4.2）；本页提供载体筛选（carrier_type +
 *   carrier_id 成对，契约 §4.2：两者必须同时提供，仅提供其一 → 400
 *   VALIDATION_ERROR，故「筛选」按钮在筛选未填完整时禁用 —— 这不是载体
 *   存在性预判（§21）：任何已填写的载体对都直接提交，由服务端裁决载体
 *   不存在 / 已删 / 类型与标识不一致 → 404 渲染）；
 * - 三态互不相同（AC-54）：Loading / Empty（200 + items 为空，「暂无服务」）/
 *   Error（按 error.code 分支渲染，不解析 message）；
 * - Empty 与 Not Found 可区分（R-QUERY-004 / AC-31）：载体存在但无活跃
 *   Service 绑定 → 200 + items == []（Empty 态，「该载体暂无服务」）；
 *   载体不存在 / 已逻辑删除 / 类型与标识不一致 → 404 NOT_FOUND（Error 态
 *   渲染「未找到资源」）；
 * - 每行提供详情 / 删除入口；删除二次确认（ElPopconfirm）→ DELETE
 *   /api/services/{id}（契约 §4.5）。204 / 404 同构刷新；409 按 error.code
 *   渲染；401 交由全局会话失效处理；提交中 Loading 且禁重复提交。删除守卫由
 *   后端裁决（§21），前端不预判、不禁用、不隐藏入口；
 * - 登记表单入口（ServiceFormDialog，POST 契约 §4.1）：多载体选择（三种
 *   类型 + 载体 ID，至少一项）；name 全局唯一 / 载体存在性均由服务端裁决，
 *   前端不预判；从已筛选的载体打开时预选该载体（可增删改）；
 * - 载体列按契约 §2 稳定顺序原样展示（carrier_type #carrier_id，不发明
 *   领域文案）；时间字段按不透明字符串原样展示；name 原样展示（契约 §8）；
 *   本页无状态列 / 状态筛选（Q-002=B，AC-28）、无 Cluster 列 / Cluster
 *   筛选（R-SVC-004/006，AC-20/21）；
 * - 分页参数合法性由服务端校验（400 VALIDATION_ERROR → Error 态渲染）；
 *   本页仅提供合法区间内的固定选项。
 */
const emit = defineEmits<{
  openDetail: [serviceId: number]
  back: []
}>()

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

// ---- 载体筛选（carrier_type + carrier_id 成对，契约 §4.2） ----

/** 筛选输入（未应用）：载体类型与载体 ID 均已填写时筛选才可应用（成对规则）。 */
const filterCarrierType = ref<ServiceCarrierType | null>(null)
const filterCarrierId = ref<number | null>(null)

/** 已应用的载体筛选；null = 全部活跃 Service。查询只依据该状态。 */
const appliedCarrier = ref<ServiceCarrier | null>(null)

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
  data: serviceData,
  loading,
  error,
  run,
} = useAsyncQuery(() =>
  listServices({
    page: page.value,
    page_size: pageSize.value,
    carrier: appliedCarrier.value ?? undefined,
  }),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useServiceDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 刷新列表。
  onRemoved: () => run(),
})

const services = computed(() => serviceData.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容。
 */
const isLoading = computed(
  () => loading.value || (serviceData.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（api-conventions.md §7）。 */
const listEmpty = computed(
  () => serviceData.value !== null && serviceData.value.items.length === 0,
)

const total = computed(() => serviceData.value?.total ?? 0)

/** 过滤上下文文案：Empty 态与标题下的过滤标签随载体筛选区分。 */
const carrierFilterLabel = computed(() =>
  appliedCarrier.value !== null
    ? `载体 ${appliedCarrier.value.carrier_type} #${appliedCarrier.value.carrier_id}`
    : null,
)
const emptyDescription = computed(() =>
  appliedCarrier.value !== null ? '该载体暂无服务' : '暂无服务',
)

/** 载体列摘要：按契约 §2 稳定顺序原样展示每条绑定（类型 #ID，不翻译枚举值）。 */
function formatCarriers(carriers: ServiceCarrier[]): string {
  return carriers.map((carrier) => `${carrier.carrier_type} #${carrier.carrier_id}`).join('、')
}

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

function openDetail(serviceId: number): void {
  emit('openDetail', serviceId)
}

function goBack(): void {
  emit('back')
}

/** 二次确认通过后删除该行服务；状态管理与错误渲染见 useServiceDelete。 */
function confirmDelete(serviceId: number): void {
  void requestDelete(serviceId)
}

// ---- 登记入口（POST /api/services） ----

const createDialogVisible = ref(false)

/** 登记表单预选载体：当前应用的载体筛选（单条；可增删改）。 */
const presetCarriers = computed(() =>
  appliedCarrier.value !== null ? [appliedCarrier.value] : null,
)

function handleCreated(): void {
  // 登记成功 → 刷新列表（新记录按 id 升序可能位于其他页，刷新当前页即可）。
  void run()
}
</script>

<template>
  <main
    class="service-list"
    :data-carrier-filter="
      appliedCarrier !== null
        ? `${appliedCarrier.carrier_type}:${appliedCarrier.carrier_id}`
        : 'none'
    "
  >
    <header class="service-list__header">
      <div class="service-list__nav">
        <el-button @click="goBack">返回集群列表</el-button>
        <h1 class="service-list__title">
          服务列表
          <el-tag v-if="carrierFilterLabel !== null" class="service-list__filter">
            {{ carrierFilterLabel }}
          </el-tag>
        </h1>
      </div>
      <div class="service-list__actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
        <el-button type="primary" data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记服务
        </el-button>
      </div>
    </header>

    <!-- 载体筛选（契约 §4.2：carrier_type 与 carrier_id 必须成对出现；
         载体存在性由服务端裁决，前端不预判）。 -->
    <section class="service-list__filter-bar">
      <el-select
        v-model="filterCarrierType"
        class="service-list__filter-type"
        placeholder="载体类型"
        data-testid="service-filter-type"
      >
        <el-option
          v-for="carrierType in SERVICE_CARRIER_TYPES"
          :key="carrierType"
          :label="carrierType"
          :value="carrierType"
        />
      </el-select>
      <el-input-number
        v-model="filterCarrierId"
        class="service-list__filter-id"
        placeholder="载体 ID"
        :controls="false"
        data-testid="service-filter-id"
      />
      <el-button
        type="primary"
        plain
        data-testid="service-filter-apply"
        :disabled="filterApplyDisabled"
        @click="applyFilter"
      >
        筛选
      </el-button>
      <el-button data-testid="service-filter-clear" @click="clearFilter">重置</el-button>
    </section>

    <section class="service-list__body">
      <ListStates
        :loading="isLoading"
        :error="error"
        :empty="listEmpty"
        :empty-description="emptyDescription"
      >
        <!-- 删除失败提示（409 等）：仅在内容态与表格同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="service-list__delete-error"
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

        <el-table :data="services" class="service-list__table">
          <el-table-column prop="id" label="ID" width="80" />
          <!-- name / created_at / updated_at 均为契约原样值，不做任何变换。 -->
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column label="运行载体" min-width="280">
            <template #default="{ row }">
              <span class="service-list__carriers">{{ formatCarriers(row.carriers) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" min-width="200" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
              <!-- 删除入口：对所有行开放；删除守卫由后端 409 裁决（§21），
                   前端不预判（不禁用、不隐藏任何行的删除入口）。 -->
              <el-popconfirm
                title="确定删除该服务吗？删除后不可恢复。"
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

        <div class="service-list__pagination">
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

    <!-- 登记表单（POST）：多载体选择；name 全局唯一 / 载体存在性 / 字段合法性
         由服务端裁决。 -->
    <ServiceFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-carriers="presetCarriers"
      @success="handleCreated"
    />
  </main>
</template>

<style scoped>
.service-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.service-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.service-list__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.service-list__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.service-list__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.service-list__filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}

.service-list__filter-type {
  width: 180px;
}

.service-list__filter-id {
  width: 140px;
}

.service-list__body {
  margin-top: 16px;
}

.service-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.service-list__delete-error {
  margin-bottom: 16px;
}

.service-list__carriers {
  word-break: break-all;
}
</style>
