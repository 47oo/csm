// 页面搜索输入状态机（架构 F008 §4.2，需求 §8.3）：从 useResourceList 抽取的通用能力——
// - q（输入框展示值）与 appliedQ（已应用到请求的关键词；去首尾空格，空 = 不搜索）；
// - 输入后约 300ms 防抖（连续输入重置计时）、回车立即（取消未触发的防抖）；
// - 请求序号竞态：旧请求响应不得覆盖较新请求（beginLoad / isCurrent / invalidate）；
// - 清空回初始：关键词清空后回到当前其它筛选条件下的初始候选（无 q，页面回调回第 1 页）。
// 不承载任何对象业务规则；供集群页、网段页、资源页等页面搜索统一接入。
import { ref } from 'vue'

/** 搜索防抖（§8.3：输入后约 300ms 自动更新） */
export const SEARCH_DEBOUNCE_MS = 300

export interface UseSearchInputOptions {
  /** 搜索触发（防抖到期 / 回车立即 / 清空回初始）：收到去首尾空格后的关键词；空串 = 初始候选 */
  onSearch: (appliedQ: string) => void
  /** 防抖毫秒数，默认 300（§8.3） */
  debounceMs?: number
}

export function useSearchInput(options: UseSearchInputOptions) {
  const debounceMs = options.debounceMs ?? SEARCH_DEBOUNCE_MS

  /** 输入框展示值（防抖前） */
  const q = ref('')
  /** 已应用到请求的关键词（去首尾空格；空 = 不搜索 / 初始候选） */
  const appliedQ = ref('')

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  /** 请求序号：丢弃快速连续输入 / 筛选切换 / 翻页过程中的过期响应 */
  let token = 0

  function cancelPending(): void {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  }

  function fire(): void {
    appliedQ.value = q.value.trim()
    token += 1
    options.onSearch(appliedQ.value)
  }

  /** 搜索输入：约 300ms 防抖后触发（连续输入重置计时）；关键词去首尾空格 */
  function setQ(value: string): void {
    q.value = value
    cancelPending()
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      fire()
    }, debounceMs)
  }

  /** 回车立即搜索（§8.3），取消未触发的防抖 */
  function searchNow(): void {
    cancelPending()
    fire()
  }

  /** 清空回初始：关键词清空并立即触发（onSearch 收到空串 = 无 q 初始候选） */
  function clear(): void {
    cancelPending()
    q.value = ''
    fire()
  }

  /** 重置输入状态而不触发搜索（供整表重置：由调用方自行重新加载） */
  function resetQuiet(): void {
    cancelPending()
    q.value = ''
    appliedQ.value = ''
  }

  /** 开始一次列表加载：返回请求序号（响应返回后用 isCurrent 判定是否丢弃） */
  function beginLoad(): number {
    token += 1
    return token
  }

  /** 该序号是否仍为最新请求（旧请求响应不得覆盖较新请求，§8.3） */
  function isCurrent(t: number): boolean {
    return t === token
  }

  /** 作废进行中的请求（如作用域清除 / 整表重置）：过期响应将被丢弃 */
  function invalidate(): void {
    token += 1
  }

  return { q, appliedQ, setQ, searchNow, clear, resetQuiet, beginLoad, isCurrent, invalidate }
}

export type UseSearchInput = ReturnType<typeof useSearchInput>
