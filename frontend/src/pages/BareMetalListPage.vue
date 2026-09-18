<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { listBareMetals } from '../api/bareMetals'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useBareMetalDelete } from '../composables/useBareMetalDelete'
import ListStates from '../components/ListStates.vue'
import BareMetalStatusTag from '../components/BareMetalStatusTag.vue'
import BareMetalFormDialog from '../components/BareMetalFormDialog.vue'

/**
 * 裸金属列表页（F002 产品页）。
 *
 * - 调用 GET /api/bare-metals（契约 §3.2），可选 cluster_id 限定（供
 * 「该集群裸金属」入口复用，R-CLUSTER-004 的 F002 侧）；
 * - 三态互不相同（AC-30）：Loading / Empty（200 + items 为空，「暂无裸金属」）/
 *   Error（按 error.code 分支渲染，不解析 message）；
 * - Empty 与 Not Found 可区分（R-QUERY-004）：Cluster 存在但无活跃裸金属 →
 *   200 + items == []（Empty 态）；Cluster 不存在或已逻辑删除 → 404 NOT_FOUND
 *   （Error 态渲染「未找到资源」）；
 * - 每行提供详情 / 删除入口；删除二次确认（ElPopconfirm）→ DELETE
 *   /api/bare-metals/{id}（契约 §3.5）。204 / 404 同构刷新；409 按error.code
 *   渲染；401 交由全局会话失效处理；提交中 Loading 且禁重复提交。删除守卫由
 *   后端裁决（§21），前端不预判、不禁用、不隐藏入口；
 * - 登记表单入口（BareMetalFormDialog，POST）：唯一性 / 父存在性 / 状态合法性
 *   均由服务端裁决，前端不预判；
 * - 时间字段按不透明字符串原样展示（契约 §2）；hostname 原样展示（契约 §7）；
 * - 分页参数合法性由服务端校验（400 VALIDATION_ERROR → Error 态渲染）；
 *   本页仅提供合法区间内的固定选项。
 */
const props = withDefaults(defineProps<{ clusterId?: number | null }>(), {
  clusterId: null,
})

const emit = defineEmits<{
  openDetail: [bareMetalId: number]
  back: []
}>()

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

const {
  data: bareMetalData,
  loading,
  error,
  run,
} = useAsyncQuery(() =>
  listBareMetals({
    page: page.value,
    page_size: pageSize.value,
    clusterId: props.clusterId ?? undefined,
  }),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useBareMetalDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 刷新列表。
  onRemoved: () => run(),
})

const bareMetals = computed(() => bareMetalData.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容。
 */
const isLoading = computed(
  () => loading.value || (bareMetalData.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（api-conventions.md §7）。 */
const listEmpty = computed(
  () => bareMetalData.value !== null && bareMetalData.value.items.length === 0,
)

const total = computed(() => bareMetalData.value?.total ?? 0)

/** 过滤上下文文案：Empty 态与标题下的过滤标签随 clusterId 区分。 */
const clusterFilterLabel = computed(() =>
  props.clusterId !== null ? `集群 #${props.clusterId}` : null,
)
const emptyDescription = computed(() =>
  props.clusterId !== null ? '该集群暂无裸金属' : '暂无裸金属',
)
const backLabel = computed(() =>
  props.clusterId !== null ? '返回集群详情' : '返回集群列表',
)

onMounted(() => {
  void run()
})

// App 视图切换可能只改变 clusterId 而复用本组件（如从「该集群裸金属」切到
// 全局列表）：回到第 1 页并重新查询。
watch(
  () => props.clusterId,
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

function openDetail(bareMetalId: number): void {
  emit('openDetail', bareMetalId)
}

function goBack(): void {
  emit('back')
}

/** 二次确认通过后删除该行裸金属；状态管理与错误渲染见 useBareMetalDelete。 */
function confirmDelete(bareMetalId: number): void {
  void requestDelete(bareMetalId)
}

// ---- 登记入口（POST /api/bare-metals） ----

const createDialogVisible = ref(false)

function handleCreated(): void {
  // 登记成功 → 刷新列表（新记录按 id 升序可能位于其他页，刷新当前页即可）。
  void run()
}
</script>

<template>
  <main class="bare-metal-list" :data-cluster-filter="clusterId ?? 'none'">
    <header class="bare-metal-list__header">
      <div class="bare-metal-list__nav">
        <el-button @click="goBack">{{ backLabel }}</el-button>
        <h1 class="bare-metal-list__title">
          裸金属列表
          <el-tag v-if="clusterFilterLabel !== null" class="bare-metal-list__filter">
            {{ clusterFilterLabel }}
          </el-tag>
        </h1>
      </div>
      <div class="bare-metal-list__actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
        <el-button type="primary" data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记裸金属
        </el-button>
      </div>
    </header>

    <section class="bare-metal-list__body">
      <ListStates
        :loading="isLoading"
        :error="error"
        :empty="listEmpty"
        :empty-description="emptyDescription"
      >
        <!-- 删除失败提示（409 等）：仅在内容态与表格同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="bare-metal-list__delete-error"
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

        <el-table :data="bareMetals" class="bare-metal-list__table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="cluster_id" label="集群 ID" width="100" />
          <!-- hostname / created_at / updated_at 均为契约原样值，不做任何变换。 -->
          <el-table-column prop="hostname" label="hostname" min-width="160" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <BareMetalStatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" min-width="200" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
              <!-- 删除入口：对所有行开放；删除守卫由后端 409 裁决（§21），
                   前端不预判（不禁用、不隐藏任何行的删除入口）。 -->
              <el-popconfirm
                title="确定删除该裸金属吗？删除后不可恢复。"
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

        <div class="bare-metal-list__pagination">
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

    <!-- 登记表单（POST）：唯一性 / 父存在性 / 字段合法性由服务端裁决。 -->
    <BareMetalFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-cluster-id="clusterId"
      @success="handleCreated"
    />
  </main>
</template>

<style scoped>
.bare-metal-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.bare-metal-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.bare-metal-list__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bare-metal-list__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bare-metal-list__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.bare-metal-list__body {
  margin-top: 16px;
}

.bare-metal-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.bare-metal-list__delete-error {
  margin-bottom: 16px;
}
</style>
