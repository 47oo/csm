<script setup lang="ts">
import { computed } from 'vue'

/**
 * BareMetal 状态标签（R-BM-003 封闭集合 {IDLE, ALLOC, DOWN, UNKNOWN} 的展示）。
 *
 * - 文本为契约原始值，不做翻译 / 改写（不发明领域文案；domain-model.md §7.1）；
 * - 颜色仅为视觉辅助：IDLE → 空闲（success）、ALLOC → 已分配（primary）、
 *   DOWN → 宕机（danger）、UNKNOWN → 未知（info）；意外值兜底 info；
 * - 本组件不做任何状态合法性判断（§21：封闭集合由服务端裁决）。
 */
const props = defineProps<{ status: string }>()

const TAG_TYPES: Readonly<Record<string, 'success' | 'primary' | 'danger' | 'info'>> = {
  IDLE: 'success',
  ALLOC: 'primary',
  DOWN: 'danger',
  UNKNOWN: 'info',
}

const tagType = computed(() => TAG_TYPES[props.status] ?? 'info')
</script>

<template>
  <el-tag :type="tagType" :data-status="status">{{ status }}</el-tag>
</template>
