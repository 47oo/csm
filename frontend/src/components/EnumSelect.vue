<script setup lang="ts" generic="T extends string">
// 固定枚举下拉（架构 F008 §4.2/§5.4，需求 §8.1–§8.3）：基于 el-select filterable +
// 本地 filter-method（utils/enumSearch）——中文展示名/英文代码均可输入匹配、
// 英文不区分大小写、去首尾空格，命中按 完全 > 前缀 > 包含 稳定排序。
// 值集来自调用方传入的既有枚举映射（resource_type / status / 角色等），
// 本组件不新增取值；提交值为枚举代码（value），不提交展示文本。
import { computed, ref } from 'vue'
import { filterEnumOptions } from '../utils/enumSearch'

const props = withDefaults(
  defineProps<{
    /** 当前值（枚举代码）；null = 未选择 */
    modelValue: T | null
    /** 枚举选项（value=英文代码，label=中文展示名） */
    options: Array<{ value: T; label: string }>
    disabled?: boolean
    clearable?: boolean
    placeholder?: string
  }>(),
  {
    disabled: false,
    clearable: false,
    placeholder: '请选择',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: T | null): void
  (e: 'change', value: T | null): void
}>()

/** 本地过滤词（el-select filter-method 输入）；下拉关闭后复位 */
const filterQuery = ref('')

/** 过滤结果：空输入（含仅空白）= 全部选项；否则按 rank 稳定排序（utils/enumSearch） */
const filteredOptions = computed(() =>
  filterQuery.value.trim() === ''
    ? props.options
    : filterEnumOptions(props.options, filterQuery.value),
)

function handleFilter(query: string): void {
  filterQuery.value = query
}

/** 下拉关闭时复位过滤词（与 el-select 内部输入复位一致） */
function handleVisibleChange(visible: boolean): void {
  if (!visible) filterQuery.value = ''
}

/** el-select change：清空（value-on-clear 为 undefined/null）统一归一为 null */
function handleChange(value: unknown): void {
  const normalized = typeof value === 'string' ? (value as T) : null
  emit('update:modelValue', normalized)
  emit('change', normalized)
}
</script>

<template>
  <el-select
    :model-value="modelValue ?? undefined"
    filterable
    :filter-method="handleFilter"
    :disabled="disabled"
    :clearable="clearable"
    :placeholder="placeholder"
    popper-class="enum-select-dropdown"
    no-data-text="没有匹配项"
    @change="handleChange"
    @visible-change="handleVisibleChange"
  >
    <el-option v-for="opt in filteredOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
  </el-select>
</template>
