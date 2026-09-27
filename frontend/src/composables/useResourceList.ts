// 资源列表状态机（架构 F003 §2.4/§7 / Contract docs/api/F003.md §2.1）：
// - GET /resources（cluster_id 必填为唯一作用域）：类型（全部/裸金属/虚拟机）与状态筛选、
//   q 搜索（300ms 防抖 + 回车立即，§8.3；q 去首尾空格，匹配名称/资源 ID/本集群已登记 IPv4）、
//   服务端分页（page/page_size）、排序（默认 name）；
// - Loading / Error / Empty / Success 状态显式区分：错误不伪装成空列表（保留重试）；
// - 旧请求不覆盖较新请求（§8.3 快速连续输入 / 筛选翻页切换）；
// - 作用域变化（切换/清除集群）刷新列表：页码重置、搜索词保留（仍限新集群）；
//   未选择集群不发起查询（页面提示选择集群）；
// - 响应回显 scope（ClusterScope）供页面显式展示「当前集群作用域」（§6.2）。
// 权限：列表任意已登录（viewer 只读）；服务端为最终校验。
import { ref, watch, type Ref } from 'vue'
import {
  listResources,
  type ClusterScope,
  type ResourceListItem,
  type ResourceSort,
  type ResourceStatus,
  type ResourceType,
} from '../api/resources'
import { apiErrorMessage } from '../api/client'

/** 搜索防抖（§8.3：输入后约 300ms 自动更新） */
const SEARCH_DEBOUNCE_MS = 300

export function useResourceList(scopeClusterId: Ref<number | null>) {
  const items = ref<ResourceListItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  /** 搜索框输入值（防抖前的展示值） */
  const q = ref('')
  /** 类型筛选：'' = 全部（对应「全部/裸金属/虚拟机」切换） */
  const resourceType = ref<ResourceType | ''>('')
  /** 状态筛选：'' = 全部 */
  const status = ref<ResourceStatus | ''>('')
  const sort = ref<ResourceSort>('name')
  /** 最近一次成功响应回显的作用域（Contract §1 ClusterScope）；未加载为 null */
  const scope = ref<ClusterScope | null>(null)
  const loading = ref(false)
  const loadError = ref('')

  /** 已应用到请求的关键词（去首尾空格；空 = 不搜索） */
  let appliedQ = ''
  /** 请求序号：丢弃切换集群/筛选/翻页过程中的过期响应 */
  let token = 0
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  async function load(): Promise<void> {
    const clusterId = scopeClusterId.value
    if (clusterId === null) {
      // 无选中集群：不发起查询（页面提示选择集群），不伪装成空列表
      token += 1
      items.value = []
      total.value = 0
      scope.value = null
      loadError.value = ''
      loading.value = false
      return
    }
    const current = ++token
    loading.value = true
    loadError.value = ''
    try {
      const data = await listResources({
        cluster_id: clusterId,
        ...(resourceType.value !== '' ? { resource_type: resourceType.value } : {}),
        ...(status.value !== '' ? { status: status.value } : {}),
        ...(appliedQ !== '' ? { q: appliedQ } : {}),
        page: page.value,
        page_size: pageSize.value,
        sort: sort.value,
      })
      if (current !== token) return // 旧请求不覆盖较新请求
      items.value = data.items
      total.value = data.total
      scope.value = data.scope
    } catch (error) {
      if (current !== token) return
      // 错误显式呈现，不伪装成空结果
      items.value = []
      total.value = 0
      scope.value = null
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

  /** 类型切换（全部/裸金属/虚拟机）：回到第 1 页 */
  function setType(value: ResourceType | ''): void {
    resourceType.value = value
    page.value = 1
    void load()
  }

  /** 状态筛选：回到第 1 页 */
  function setStatus(value: ResourceStatus | ''): void {
    status.value = value
    page.value = 1
    void load()
  }

  function setSort(value: ResourceSort): void {
    sort.value = value
    page.value = 1
    void load()
  }

  /** 翻页（服务端分页） */
  function setPage(next: number): void {
    page.value = next
    void load()
  }

  function setPageSize(next: number): void {
    pageSize.value = next
    page.value = 1
    void load()
  }

  /** 重置筛选/搜索/排序（回到默认 name 升序第 1 页） */
  function resetFilters(): void {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    q.value = ''
    appliedQ = ''
    resourceType.value = ''
    status.value = ''
    sort.value = 'name'
    page.value = 1
    void load()
  }

  function retry(): void {
    void load()
  }

  // 作用域（集群）变化：页码重置并刷新；搜索词保留（仍限新集群作用域，不隐式跨集群）
  watch(
    scopeClusterId,
    () => {
      page.value = 1
      void load()
    },
    { immediate: true },
  )

  return {
    items,
    total,
    page,
    pageSize,
    q,
    resourceType,
    status,
    sort,
    scope,
    loading,
    loadError,
    setQ,
    searchNow,
    setType,
    setStatus,
    setSort,
    setPage,
    setPageSize,
    resetFilters,
    retry,
  }
}
