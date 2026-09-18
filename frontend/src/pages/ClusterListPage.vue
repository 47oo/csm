<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listClusters } from '../api/clusters'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useClusterDelete } from '../composables/useClusterDelete'
import ListStates from '../components/ListStates.vue'

/**
 * 集群列表页（F001 产品页；F014 起提供行级删除入口）。
 *
 * - 调用 GET /api/clusters（契约 f001-cluster.md §3.2），展示 id / name /
 *   created_at / updated_at 与分页（page / page_size）；
 * - 三态互不相同（AC-14）：Loading（请求中）/ Empty（200 + items 为空，「暂无集群」）/
 *   Error（按 error.code 分支渲染，不解析 message）；
 * - F014：每行删除入口（ElPopconfirm 二次确认）→ DELETE /api/clusters/{id}
 *   （契约 f014-soft-delete.md §3.1）。删除成功（204）或目标已不存在（404，
 *   两者不区分）→ 刷新列表：被删行消失、当前页变空 → Empty 态；
 *   409 CONFLICT（存在活跃子资源）→ 保留行并按 error.code 渲染冲突提示；
 *   401 → 既有全局会话失效处理；提交中 Loading 且禁止重复提交。
 *   删除守卫由后端裁决（§21），前端不预判、不禁用、不隐藏入口；
 * - 时间字段按不透明字符串原样展示（契约 §2：不解析、不假设时区）；
 * - name 原样展示，不假设非空或已 trim（契约 §7 undefined_constraints）；
 * - 分页参数合法性（page ≥ 1、1 ≤ page_size ≤ 200）由服务端校验
 *   （400 VALIDATION_ERROR → Error 态渲染）；本页仅提供合法区间内的固定选项。
 */

const emit = defineEmits<{ openDetail: [clusterId: number] }>()

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

const {
  data: clusterData,
  loading,
  error,
  run,
} = useAsyncQuery(() => listClusters({ page: page.value, page_size: pageSize.value }))

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useClusterDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 刷新列表：
  // 被删行消失；当前页因此变空 → Empty 态。
  onRemoved: () => run(),
})

const clusters = computed(() => clusterData.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容（空表格 + total=0 的分页器）。
 */
const isLoading = computed(
  () => loading.value || (clusterData.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（api-conventions.md §7）。 */
const listEmpty = computed(
  () => clusterData.value !== null && clusterData.value.items.length === 0,
)

const total = computed(() => clusterData.value?.total ?? 0)

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

function openDetail(clusterId: number): void {
  emit('openDetail', clusterId)
}

/** 二次确认通过后删除该行集群；状态管理与错误渲染见 useClusterDelete。 */
function confirmDelete(clusterId: number): void {
  void requestDelete(clusterId)
}
</script>

<template>
  <main class="cluster-list">
    <header class="cluster-list__header">
      <h1 class="cluster-list__title">集群列表</h1>
      <el-button :loading="loading" @click="refresh">刷新</el-button>
    </header>

    <section class="cluster-list__body">
      <ListStates
        :loading="isLoading"
        :error="error"
        :empty="listEmpty"
        empty-description="暂无集群"
      >
        <!-- 删除失败提示（409 等）：仅在内容态与表格同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="cluster-list__delete-error"
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

        <el-table :data="clusters" class="cluster-list__table">
          <el-table-column prop="id" label="ID" width="80" />
          <!-- name / created_at / updated_at 均为契约原样值，不做任何变换。 -->
          <el-table-column prop="name" label="名称" min-width="200" />
          <el-table-column prop="created_at" label="登记时间" min-width="220" />
          <el-table-column prop="updated_at" label="更新时间" min-width="220" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
              <!-- F014 删除入口：对所有行开放；「是否存在活跃子资源」由后端 409 裁决
                   （§21），前端不预判（不禁用、不隐藏任何行的删除入口）。 -->
              <el-popconfirm
                title="确定删除该集群吗？删除后不可恢复。"
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

        <div class="cluster-list__pagination">
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
  </main>
</template>

<style scoped>
.cluster-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.cluster-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.cluster-list__title {
  margin: 0;
  font-size: 20px;
}

.cluster-list__body {
  margin-top: 16px;
}

.cluster-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.cluster-list__delete-error {
  margin-bottom: 16px;
}
</style>
