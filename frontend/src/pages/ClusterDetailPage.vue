<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { getCluster, type ClusterRead } from '../api/clusters'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useClusterDelete } from '../composables/useClusterDelete'
import ErrorState from '../components/ErrorState.vue'

/**
 * 集群详情页（F001 骨架页；F014 起提供删除入口）。
 *
 * - 调用 GET /api/clusters/{id}（契约 f001-cluster.md §3.3，规范路径），仅呈现 Cluster 自身字段
 *   （id / name / created_at / updated_at，契约 §2 封闭集合）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同状态（R-QUERY-004）；
 * - 其他错误按 error.code 由 ErrorState 渲染（不解析 message）；
 * - F014：内容态提供删除入口（ElPopconfirm 二次确认）→ DELETE /api/clusters/{id}
 *   （契约 f014-soft-delete.md §3.1）。删除成功（204）或目标已不存在（404，
 *   两者不区分）→ 重新读取 → 404 → 进入既有独立 Not Found 态；409 CONFLICT →
 *   保留详情内容并按 error.code 渲染冲突提示；401 → 既有全局会话失效处理；
 *   提交中 Loading 且禁止重复提交。删除守卫由后端裁决（§21），前端不预判；
 * - 时间字段按不透明字符串原样展示（契约 §2）；
 * - 不呈现 BareMetal 列表 / 状态（F009）、不呈现跨资源视图（F010）。
 */

const props = defineProps<{ clusterId: number }>()

const emit = defineEmits<{ back: [] }>()

const { data, loading, error, run } = useAsyncQuery(() => getCluster(props.clusterId))

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useClusterDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
  // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态，不新造状态。
  onRemoved: () => run(),
})

onMounted(() => {
  void run()
})

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const DETAIL_FIELDS: ReadonlyArray<{ key: keyof ClusterRead; label: string }> = [
  { key: 'id', label: 'ID' },
  { key: 'name', label: '名称' },
  { key: 'created_at', label: '登记时间' },
  { key: 'updated_at', label: '更新时间' },
]

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（AC-14 / R-QUERY-004）；
 * - 首次请求尚未返回（data 与 error 均为空）按 Loading 处理，避免闪现空内容。
 */
const state = computed<'loading' | 'not-found' | 'error' | 'content'>(() => {
  if (loading.value) return 'loading'
  if (error.value !== null) {
    return error.value.code === 'NOT_FOUND' ? 'not-found' : 'error'
  }
  return data.value !== null ? 'content' : 'loading'
})

/** 永不为 null 的字段值列表（供模板直接渲染，避免可空解引用）。 */
const fieldValues = computed(() => {
  const cluster = data.value
  if (cluster === null) return []
  return DETAIL_FIELDS.map((field) => ({
    key: field.key,
    label: field.label,
    value: cluster[field.key],
  }))
})

function backToList(): void {
  emit('back')
}

/** 二次确认通过后删除当前集群；状态管理与错误渲染见 useClusterDelete。 */
function confirmDelete(): void {
  void requestDelete(props.clusterId)
}
</script>

<template>
  <main class="cluster-detail" :data-state="state">
    <header class="cluster-detail__header">
      <div class="cluster-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="cluster-detail__title">集群详情</h1>
      </div>
      <!-- F014 删除入口：仅内容态出现；「是否存在活跃子资源」由后端 409 裁决
           （§21），前端不预判。 -->
      <el-popconfirm
        v-if="state === 'content'"
        title="确定删除该集群吗？删除后不可恢复。"
        confirm-button-text="删除"
        cancel-button-text="取消"
        confirm-button-type="danger"
        :width="200"
        @confirm="confirmDelete"
      >
        <template #reference>
          <el-button type="danger" plain :loading="deletingId !== null">删除集群</el-button>
        </template>
      </el-popconfirm>
    </header>

    <section class="cluster-detail__body">
      <div v-if="state === 'loading'" class="cluster-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="cluster-detail__delete-error"
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
            v-for="field in fieldValues"
            :key="field.key"
            :label="field.label"
          >
            {{ field.value }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </section>
  </main>
</template>

<style scoped>
.cluster-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.cluster-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.cluster-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cluster-detail__delete-error {
  margin-bottom: 16px;
}

.cluster-detail__title {
  margin: 0;
  font-size: 20px;
}

.cluster-detail__body {
  margin-top: 16px;
}

.cluster-detail__loading {
  padding: 8px 0;
}
</style>
