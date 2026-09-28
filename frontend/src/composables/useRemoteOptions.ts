// 远程下拉选项状态机（架构 F008 §4.2，需求 §8.3）：FuzzySelect 的数据层——
// - 持有 query / options / total / loading / error / hasMore / page；泛型 fetcher，
//   不承载对象业务规则；
// - 输入后约 300ms 防抖（连续输入重置计时）、回车立即（searchNow）、清空回初始候选；
// - 请求序号竞态：旧请求响应不得覆盖较新请求；
// - Loading / Error / Empty / Success 状态显式区分：错误不伪装成空列表（可 retry）；
// - hasNoMatch：非加载、无错误、有效关键词非空且无结果（区别于「暂无数据」）。
import { computed, ref, type Ref } from 'vue'
import { apiErrorMessage } from '../api/client'

/** 下拉数据源分页结果 */
export interface RemoteOptionsPage<T> {
  items: T[]
  total: number
}

export interface UseRemoteOptionsInput<T> {
  /** 数据源：按关键词与页码取一页候选（关键词已去首尾空格；空 = 初始候选） */
  fetcher: (query: string, page: number, pageSize: number) => Promise<RemoteOptionsPage<T>>
  /** 初始候选：作为首个展示结果（可配 immediateInitial=false 免首次请求） */
  initialItems?: T[]
  /** 每页数量（架构 §5.1 建议小值 ≤100）；默认 20 */
  pageSize?: number
  /** 防抖毫秒数；默认 300（§8.3） */
  debounceMs?: number
  /** 建立时是否立即加载初始候选；默认 true */
  immediateInitial?: boolean
}

export function useRemoteOptions<T>(input: UseRemoteOptionsInput<T>) {
  const pageSize = input.pageSize ?? 20
  const debounceMs = input.debounceMs ?? 300

  /** 输入框展示值（防抖前） */
  const query = ref('')
  /** 当前展示的候选（第 page 页；初始为 initialItems） */
  const options = ref([...(input.initialItems ?? [])]) as Ref<T[]>
  const total = ref(input.initialItems?.length ?? 0)
  const loading = ref(false)
  /** 显式错误文案；空 = 无错误（错误不伪装成空列表） */
  const error = ref('')
  const page = ref(1)
  /** 是否还有更多页（服务端分页 total） */
  const hasMore = computed(() => options.value.length < total.value)

  /** 已应用到请求的关键词（去首尾空格；空 = 初始候选） */
  const appliedQuery = ref('')
  /** 请求序号：丢弃快速连续输入 / 翻页过程中的过期响应 */
  let token = 0
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  /** 最近一次尝试（retry 重放同参数） */
  let lastAttempt = { page: 1, append: false }

  function cancelPending(): void {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  }

  async function fetchPage(targetPage: number, append: boolean): Promise<void> {
    lastAttempt = { page: targetPage, append }
    const current = ++token
    loading.value = true
    error.value = ''
    try {
      const data = await input.fetcher(appliedQuery.value, targetPage, pageSize)
      if (current !== token) return // 旧请求不覆盖较新请求
      // append=分页加载更多；否则替换为该页结果（搜索/清空回第 1 页）
      options.value = append ? [...options.value, ...data.items] : data.items
      total.value = data.total
      page.value = targetPage
    } catch (e) {
      if (current !== token) return
      // 错误显式呈现，不伪装成空结果
      options.value = []
      total.value = 0
      error.value = apiErrorMessage(e)
    } finally {
      if (current === token) loading.value = false
    }
  }

  /** 输入 → 防抖查询（连续输入重置计时；关键词去首尾空格；回到第 1 页） */
  function search(q: string): void {
    query.value = q
    cancelPending()
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      appliedQuery.value = q.trim()
      void fetchPage(1, false)
    }, debounceMs)
  }

  /** 回车立即查询（取消防抖，回到第 1 页） */
  function searchNow(): void {
    cancelPending()
    appliedQuery.value = query.value.trim()
    void fetchPage(1, false)
  }

  /** 清空回初始：关键词清空并回到初始候选（无 q 第 1 页） */
  function clear(): void {
    cancelPending()
    query.value = ''
    appliedQuery.value = ''
    void fetchPage(1, false)
  }

  /** （重新）加载初始候选：无 q 第 1 页（下拉打开 / 清除选择后回到初始候选） */
  function loadInitial(): void {
    cancelPending()
    query.value = ''
    appliedQuery.value = ''
    void fetchPage(1, false)
  }

  /** 重试最近一次失败的请求（同关键词同页） */
  function retry(): void {
    void fetchPage(lastAttempt.page, lastAttempt.append)
  }

  /** 加载更多 / 翻页：n>1 追加第 n 页（服务端分页）；n≤1 替换回第 1 页 */
  function setPage(n: number): void {
    void fetchPage(Math.max(n, 1), n > 1)
  }

  /** 无结果：非加载、无错误、有效关键词非空且候选为空（区别于「暂无数据」） */
  const hasNoMatch = computed(
    () => !loading.value && error.value === '' && appliedQuery.value !== '' && options.value.length === 0,
  )

  if (input.immediateInitial !== false) {
    void fetchPage(1, false)
  }

  return {
    query,
    appliedQuery,
    options,
    total,
    loading,
    error,
    page,
    hasMore,
    hasNoMatch,
    search,
    searchNow,
    clear,
    loadInitial,
    retry,
    setPage,
  }
}

export type UseRemoteOptions<T> = ReturnType<typeof useRemoteOptions<T>>
