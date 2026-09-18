<script setup lang="ts">
import { computed } from 'vue'
import type { ApiErrorDetail } from '../types/api'
import type { ApiError } from '../api/http'

interface ErrorView {
  title: string
  description: string
}

const props = defineProps<{
  error: ApiError
}>()

/**
 * 按 error.code 分支渲染（api-conventions.md §5：前端按 code 分支，不解析 message）。
 *
 * - NOT_FOUND 属于 Error 态，与列表 Empty（200 + items 为空）是**不同**状态；
 * - UNAUTHENTICATED / FORBIDDEN 分支为 F013 预留（F012 不实现认证，暂不触发）；
 * - 未知 code 走兜底分支，并展示原始 code，不改写、不丢失。
 */
const view = computed<ErrorView>(() => {
  switch (props.error.code) {
    case 'VALIDATION_ERROR':
      return {
        title: '请求校验失败',
        description: '提交的内容不符合要求，请根据下方字段提示修改后重试。',
      }
    case 'UNAUTHENTICATED':
      return { title: '未登录', description: '尚未登录，或登录状态已过期。' }
    case 'FORBIDDEN':
      return { title: '没有访问权限', description: '当前用户无权访问该资源。' }
    case 'NOT_FOUND':
      return { title: '未找到资源', description: '请求的资源不存在，或已被删除。' }
    case 'CONFLICT':
      return {
        title: '数据冲突',
        description: '保存的内容与现有数据冲突，请根据下方字段提示检查后重试。',
      }
    case 'INTERNAL_ERROR':
      return { title: '服务器内部错误', description: '服务器处理请求时发生错误，请稍后重试。' }
    case 'NETWORK_ERROR':
      return {
        title: '无法连接服务器',
        description: '请求未能送达服务器，请检查网络或服务状态后重试。',
      }
    default:
      return { title: '请求失败', description: '发生未预期的错误，请稍后重试。' }
  }
})

const hasDetails = computed(() => props.error.details.length > 0)

/** 组装 details 项的标签：行号（导入场景，F011）+ 字段名。 */
function detailLabel(detail: ApiErrorDetail): string | null {
  const parts: string[] = []
  if (detail.row !== undefined) parts.push(`第 ${detail.row} 行`)
  if (detail.field !== undefined) parts.push(detail.field)
  if (detail.code !== undefined && parts.length === 0) parts.push(detail.code)
  return parts.length > 0 ? parts.join(' · ') : null
}
</script>

<template>
  <div class="error-state" role="alert" :data-error-code="error.code">
    <el-result icon="error" :title="view.title" :sub-title="view.description">
      <template #extra>
        <div v-if="hasDetails" class="error-state__details">
          <p
            v-for="(detail, index) in error.details"
            :key="index"
            class="error-state__detail"
          >
            <el-tag v-if="detailLabel(detail) !== null" size="small" type="danger">
              {{ detailLabel(detail) }}
            </el-tag>
            <span v-if="detail.message">{{ detail.message }}</span>
          </p>
        </div>
        <p class="error-state__meta">
          <span>{{ error.status > 0 ? `HTTP ${error.status}` : '无 HTTP 响应' }}</span>
          <span class="error-state__code">{{ error.code }}</span>
        </p>
        <p v-if="error.message" class="error-state__message">{{ error.message }}</p>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.error-state {
  padding: 8px 0;
}

.error-state__details {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin: 0 0 8px;
}

.error-state__detail {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: #606266;
  font-size: 13px;
}

.error-state__meta {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin: 0;
  color: #909399;
  font-size: 12px;
}

.error-state__code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.error-state__message {
  margin: 4px 0 0;
  color: #909399;
  font-size: 12px;
}
</style>
