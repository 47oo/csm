<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { getCluster, type ClusterRead } from '../api/clusters'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import ErrorState from '../components/ErrorState.vue'

/**
 * 集群详情页（F001 骨架页）。
 *
 * - 调用 GET /api/clusters/{id}（契约 §3.3，规范路径），仅呈现 Cluster 自身字段
 *   （id / name / created_at / updated_at，契约 §2 封闭集合）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同状态（R-QUERY-004）；
 * - 其他错误按 error.code 由 ErrorState 渲染（不解析 message）；
 * - 时间字段按不透明字符串原样展示（契约 §2）；
 * - 不呈现 BareMetal 列表 / 状态（F009）、不呈现跨资源视图（F010）、
 *   不提供删除入口（F014）。
 */

const props = defineProps<{ clusterId: number }>()

const emit = defineEmits<{ back: [] }>()

const { data, loading, error, run } = useAsyncQuery(() => getCluster(props.clusterId))

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
</script>

<template>
  <main class="cluster-detail" :data-state="state">
    <header class="cluster-detail__header">
      <el-button @click="backToList">返回列表</el-button>
      <h1 class="cluster-detail__title">集群详情</h1>
    </header>

    <section class="cluster-detail__body">
      <div v-if="state === 'loading'" class="cluster-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <el-descriptions v-else :column="1" border>
        <el-descriptions-item
          v-for="field in fieldValues"
          :key="field.key"
          :label="field.label"
        >
          {{ field.value }}
        </el-descriptions-item>
      </el-descriptions>
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
  gap: 12px;
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
