// 网段详情「已分配 IP 及归属」状态机（架构 F006 §2.4 / Contract F006 §3.1）：
// - GET /network-segments/{id}/allocated-ips：分页（服务端）+ q 搜索（300ms 防抖 + 回车立即，
//   §8.3；q 去首尾空格，匹配地址/资源名/接口名）；
// - Loading / Error / Empty / Success 状态显式区分：错误不伪装成空列表（保留重试）；
// - 旧请求不覆盖较新请求（§8.3 快速连续输入）；
// - 抽屉打开/切换网段时重置并加载；关闭时清空。
// 权限：任意已登录（viewer 只读可见）；服务端为最终校验。
import { ref, watch, type Ref } from 'vue'
import { listAllocatedIps, type AllocatedIpItem } from '../api/segments'
import { apiErrorMessage } from '../api/client'

/** 搜索防抖（§8.3：输入后约 300ms 自动更新） */
const SEARCH_DEBOUNCE_MS = 300

export function useSegmentAllocatedIps(segmentId: Ref<number | null>, active: Ref<boolean>) {
  const items = ref<AllocatedIpItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  /** 搜索框输入值（防抖前的展示值） */
  const q = ref('')
  const loading = ref(false)
  const loadError = ref('')

  /** 已应用到请求的关键词（去首尾空格；空 = 不过滤） */
  let appliedQ = ''
  let token = 0
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  async function load(): Promise<void> {
    const id = segmentId.value
    if (id === null) return
    const current = ++token
    loading.value = true
    loadError.value = ''
    try {
      const data = await listAllocatedIps(id, {
        page: page.value,
        page_size: pageSize.value,
        ...(appliedQ !== '' ? { q: appliedQ } : {}),
      })
      if (current !== token) return // 旧请求不覆盖较新请求
      items.value = data.items
      total.value = data.total
    } catch (error) {
      if (current !== token) return
      // 错误显式呈现，不伪装成空结果
      items.value = []
      total.value = 0
      loadError.value = apiErrorMessage(error)
    } finally {
      if (current === token) loading.value = false
    }
  }

  /** 搜索输入：300ms 防抖后回到第 1 页加载（§8.3） */
  function setQ(value: string): void {
    q.value = value
    if (debounceTimer !== null) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      appliedQ = value.trim()
      page.value = 1
      void load()
    }, SEARCH_DEBOUNCE_MS)
  }

  /** 回车立即搜索（§8.3），取消未触发的防抖 */
  function searchNow(): void {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    appliedQ = q.value.trim()
    page.value = 1
    void load()
  }

  /** 翻页（服务端分页） */
  function setPage(next: number): void {
    page.value = next
    void load()
  }

  function retry(): void {
    void load()
  }

  /** 重置（抽屉关闭或切换网段）：清空结果与关键词，作废进行中的请求 */
  function reset(): void {
    token += 1
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    items.value = []
    total.value = 0
    page.value = 1
    q.value = ''
    appliedQ = ''
    loading.value = false
    loadError.value = ''
  }

  watch(
    () => [active.value, segmentId.value] as const,
    ([open, id]) => {
      if (open && id !== null) {
        reset()
        void load()
      } else if (!open) {
        reset()
      }
    },
    { immediate: true },
  )

  return {
    items,
    total,
    page,
    pageSize,
    q,
    loading,
    loadError,
    setQ,
    searchNow,
    setPage,
    retry,
    reset,
  }
}
