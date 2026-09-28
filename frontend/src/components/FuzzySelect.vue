<script setup lang="ts">
// 统一模糊搜索下拉（架构 F008 §4.2/§5，需求 §8.1–§8.3、场景 41）：
// 基于 el-select filterable + remote，数据层为 composables/useRemoteOptions——
// - 输入防抖（默认 300ms，连续输入重置计时）、回车立即、加载态、竞态丢弃；
// - 清空（clearable / 清除键）清除选择并回到初始候选；
// - 无结果显示统一文案「没有匹配项」；错误显式呈现（可重试），不伪装成空列表；
// - 上下/回车/Esc 键盘交互交由 el-select；本组件补充：展开且无高亮项时回车 = 立即查询；
// - 提交值恒为稳定 ID（SearchOption.value），不提交展示文本；
// - 未匹配自由文本不提交、不创建对象，失焦/关闭后由 el-select 回退到上次有效选择或清空。
// 本组件不承载对象业务规则；对象适配（集群/资源/网段 → SearchOption）见 utils/searchOptions。
import { computed, ref, watch } from 'vue'
import { useRemoteOptions } from '../composables/useRemoteOptions'
import type { SearchOption, SearchOptionsPage } from '../utils/searchOptions'

/** el-select 模板实例上可用的内部状态（Element Plus select 经 setup 返回暴露；
 * 版本升级如缺失则相关行为退化为 el-select 原生，不影响选择功能） */
interface SelectInternal {
  focus: () => void
  blur: () => void
  toggleMenu: () => void
  expanded?: boolean
  states?: { hoveringIndex?: number }
}

const props = withDefaults(
  defineProps<{
    /** 当前值：稳定 ID（单选 number|string|null；多选为 ID 数组） */
    modelValue: number | string | null | Array<number | string>
    /** 数据源：按关键词取一页候选（关键词已去首尾空格；空 = 初始候选） */
    fetcher: (query: string, page: number, pageSize: number) => Promise<SearchOptionsPage>
    /** 初始候选：提供则免首次请求；亦用于回显当前值对应的 label */
    initialOptions?: SearchOption[]
    /** 防抖毫秒数（§8.3）；默认 300 */
    debounceMs?: number
    /** 每页数量（建议小值 ≤100）；默认 20 */
    pageSize?: number
    placeholder?: string
    clearable?: boolean
    disabled?: boolean
    multiple?: boolean
    /** 无结果 / 无数据统一文案（§8.3） */
    emptyText?: string
    loadingText?: string
  }>(),
  {
    initialOptions: () => [],
    debounceMs: 300,
    pageSize: 20,
    placeholder: '输入关键词搜索',
    clearable: true,
    disabled: false,
    multiple: false,
    emptyText: '没有匹配项',
    loadingText: '加载中…',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: number | string | null | Array<number | string>): void
  (e: 'change', value: number | string | null | Array<number | string>): void
  (e: 'select', option: SearchOption | SearchOption[] | null): void
  (e: 'clear'): void
  (e: 'no-match', query: string): void
  (e: 'error', message: string): void
}>()

const selectRef = ref<SelectInternal | null>(null)

// pageSize / debounceMs / initialOptions 在建立时生效（静态配置，不动态响应）
const remote = useRemoteOptions<SearchOption>({
  fetcher: (query, page, pageSize) => props.fetcher(query, page, pageSize),
  initialItems: props.initialOptions,
  pageSize: props.pageSize,
  debounceMs: props.debounceMs,
  immediateInitial: props.initialOptions.length === 0,
})

const {
  options: remoteOptions,
  loading: remoteLoading,
  error: remoteError,
  hasNoMatch,
} = remote

/** 已确认过的选项（initialOptions + 历史选中）：当前值不在当前候选页时用于回显 label */
const knownOptions = ref<SearchOption[]>([...props.initialOptions])

function isSelected(value: number | string): boolean {
  return props.multiple
    ? Array.isArray(props.modelValue) && props.modelValue.includes(value)
    : props.modelValue === value
}

/** 展示候选：当前页结果 + 当前值对应但不在当前页的已知选项（置顶回显） */
const displayOptions = computed(() => {
  const inPage = new Set(remoteOptions.value.map((o) => o.value))
  const echo = knownOptions.value.filter((o) => !inPage.has(o.value) && isSelected(o.value))
  return [...echo, ...remoteOptions.value]
})

function findOption(value: number | string): SearchOption {
  return (
    displayOptions.value.find((o) => o.value === value) ??
    knownOptions.value.find((o) => o.value === value) ?? { value, label: String(value) }
  )
}

function remember(option: SearchOption): void {
  if (!knownOptions.value.some((o) => o.value === option.value)) {
    knownOptions.value = [...knownOptions.value, option]
  }
}

/** el-select change：单选收到稳定 ID（清空为 undefined → 归一 null）；多选收到 ID 数组 */
function handleChange(raw: unknown): void {
  if (props.multiple && Array.isArray(raw)) {
    const value = raw as Array<number | string>
    const selected = value.map((v) => {
      const option = findOption(v)
      remember(option)
      return option
    })
    emit('update:modelValue', value)
    emit('change', value)
    emit('select', selected)
    return
  }
  const value = typeof raw === 'number' || typeof raw === 'string' ? raw : null
  if (value === null) {
    emit('update:modelValue', null)
    emit('change', null)
    emit('select', null)
    return
  }
  const option = findOption(value)
  remember(option)
  emit('update:modelValue', value)
  emit('change', value)
  emit('select', option)
}

/** 清除选择（el-select clear 事件；change(undefined) 已先经 handleChange 归一） */
function handleClear(): void {
  emit('clear')
  remote.loadInitial()
}

/** el-select remote-method：输入即防抖查询（el-select debounce=0，防抖统一由 useRemoteOptions 承接） */
function handleRemoteSearch(query: string): void {
  remote.search(query)
}

/** 键盘（捕获阶段，先于 el-select 输入框处理器）：展开且无高亮项时回车 = 立即查询 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.isComposing || props.disabled) return
  const internal = selectRef.value
  // 未确认展开状态（或未展开）：交由 el-select 原生（打开下拉 / 确认高亮项）
  if (!internal || internal.expanded !== true) return
  const hoveringIndex = internal.states?.hoveringIndex
  if (typeof hoveringIndex === 'number' && hoveringIndex >= 0) return
  // 无高亮项：回车跳过防抖立即查询，并阻止 el-select 的空确认行为
  event.preventDefault()
  event.stopPropagation()
  remote.searchNow()
}

/** 错误显式上报（不伪装成空列表） */
watch(
  () => remoteError.value,
  (message) => {
    if (message !== '') emit('error', message)
  },
)

/** 无结果上报（§8.3「没有匹配项」） */
watch(
  () => hasNoMatch.value,
  (noMatch) => {
    if (noMatch) emit('no-match', remote.appliedQuery.value)
  },
)

// ---------- Exposed：focus / blur / clear / reload / open ----------

function focus(): void {
  selectRef.value?.focus()
}

function blur(): void {
  selectRef.value?.blur()
}

/** 程序化清空：按清除按钮同语义发出事件并回到初始候选 */
function clear(): void {
  if (props.disabled) return
  emit('update:modelValue', props.multiple ? [] : null)
  emit('change', props.multiple ? [] : null)
  emit('select', null)
  emit('clear')
  remote.loadInitial()
}

/** 重新加载初始候选（无 q 第 1 页） */
function reload(): void {
  remote.loadInitial()
}

/** 打开下拉（已打开则不重复切换） */
function open(): void {
  const internal = selectRef.value
  if (!internal) return
  if (internal.expanded === true) return
  internal.toggleMenu()
}

defineExpose({ focus, blur, clear, reload, open })
</script>

<template>
  <el-select
    ref="selectRef"
    :model-value="modelValue"
    filterable
    remote
    :remote-method="handleRemoteSearch"
    :debounce="0"
    :loading="remoteLoading"
    :clearable="clearable"
    :disabled="disabled"
    :multiple="multiple"
    :placeholder="placeholder"
    @change="handleChange"
    @clear="handleClear"
    @keydown.capture="handleKeydown"
  >
    <el-option
      v-for="opt in displayOptions"
      :key="opt.value"
      :value="opt.value"
      :label="opt.label"
      :disabled="opt.disabled"
    />
    <!-- 下拉空态：加载 / 错误（可重试）/ 无匹配 统一呈现（§8.3；错误不伪装成空列表） -->
    <template #empty>
      <span v-if="remoteLoading">{{ loadingText }}</span>
      <div v-else-if="remoteError !== ''" class="fuzzy-select-error">
        <span>{{ remoteError }}</span>
        <el-button link type="primary" size="small" @click="remote.retry()">重试</el-button>
      </div>
      <span v-else>{{ emptyText }}</span>
    </template>
  </el-select>
</template>

<style scoped>
.fuzzy-select-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 12px;
  color: #f56c6c;
}
</style>
