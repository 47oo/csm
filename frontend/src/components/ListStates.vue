<script setup lang="ts">
import { computed } from 'vue'
import type { ApiError } from '../api/http'
import ErrorState from './ErrorState.vue'

/**
 * 列表状态基座：Loading / Error / Empty / 内容（默认插槽）。
 *
 * 状态判定优先级：loading > error > empty > 内容。
 * - Empty：请求成功（200）但 items 为空（api-conventions.md §7），渲染「暂无数据」；
 * - Not Found：属于 **Error** 态（404 NOT_FOUND 由 ErrorState 渲染为「未找到资源」），
 *   与 Empty 是不同的状态，不得混用；
 * - 未提供 data 判定：Empty 由调用方依据已加载数据计算（如 items.length === 0）。
 */
const props = defineProps<{
  loading: boolean
  error: ApiError | null
  /** 请求已成功且列表为空时为 true（例如 items.length === 0）。 */
  empty: boolean
  /** Empty 态文案；默认「暂无数据」。 */
  emptyDescription?: string
}>()

const state = computed<'loading' | 'error' | 'empty' | 'content'>(() => {
  if (props.loading) return 'loading'
  if (props.error !== null) return 'error'
  if (props.empty) return 'empty'
  return 'content'
})
</script>

<template>
  <div class="list-states" :data-state="state">
    <div v-if="loading" class="list-states__loading">
      <el-skeleton :rows="4" animated />
    </div>
    <ErrorState v-else-if="error !== null" :error="error" />
    <el-empty v-else-if="empty" :description="emptyDescription ?? '暂无数据'" />
    <slot v-else />
  </div>
</template>

<style scoped>
.list-states__loading {
  padding: 8px 0;
}
</style>
