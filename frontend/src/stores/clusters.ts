// 集群选择状态（架构 F001 §2.3）：列表缓存 + “本次选择”。
// 选择仅改变查询作用域，不改变角色权限（需求 §6.1、场景 40/57：权限始终由服务端校验）。
// currentClusterId 持久化到 localStorage，刷新后恢复；记忆的集群已不存在时回退为空并标记提示。
import { defineStore } from 'pinia'
import { apiErrorMessage } from '../api/client'
import * as clustersApi from '../api/clusters'
import type { ClusterListItem } from '../api/clusters'

/** localStorage 键：本次选择的集群 ID */
const STORAGE_KEY = 'csm.cluster.currentClusterId'

/** 全量拉取保护上限（page_size=100 × 50 页 = 5000 条，足够 P0 规模并防异常 total 死循环） */
const MAX_PAGES = 50

/** 读取记忆的集群 ID；缺失/非法返回 null */
function readRememberedClusterId(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw === null) return null
    const id = Number(raw)
    return Number.isInteger(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

function persistClusterId(id: number | null): void {
  try {
    if (id === null) window.localStorage.removeItem(STORAGE_KEY)
    else window.localStorage.setItem(STORAGE_KEY, String(id))
  } catch {
    // localStorage 不可用（如被禁用）时仅影响跨刷新记忆，不影响本次会话
  }
}

export const useClusterStore = defineStore('clusters', {
  state: () => ({
    /** 集群列表缓存（选择器数据源；全量拉取，兼作选择存在性校验依据） */
    clusters: [] as ClusterListItem[],
    /** 本次选择的集群 ID；null = 未选择（不限作用域）。只改查询作用域，不是权限 */
    currentClusterId: null as number | null,
    /** 是否已完成至少一次成功加载 */
    loaded: false,
    /** 最近一次加载失败信息；null = 无。错误不伪装成空列表 */
    loadError: null as string | null,
    /** 记忆/当前的选择已失效（集群不存在），待 UI 提示后确认 */
    selectionDropped: false,
  }),
  getters: {
    /** 当前选择的集群（缓存中查找；未选择或未加载返回 null） */
    currentCluster(state): ClusterListItem | null {
      return state.clusters.find((c) => c.id === state.currentClusterId) ?? null
    },
  },
  actions: {
    /** 选择集群（null = 清除选择），持久化到 localStorage（本次选择，刷新恢复） */
    selectCluster(id: number | null): void {
      this.currentClusterId = id
      persistClusterId(id)
    },

    /**
     * 全量加载集群列表（选择器数据源）。分页上限 100/页（Contract §2.1），
     * 逐页拉取直到 total；加载后校验当前选择仍存在。
     */
    async loadClusters(force = false): Promise<void> {
      if (this.loaded && !force) return
      try {
        const items: ClusterListItem[] = []
        let page = 1
        while (page <= MAX_PAGES) {
          const data = await clustersApi.listClusters({ page, page_size: 100, sort: 'code' })
          items.push(...data.items)
          if (items.length >= data.total || data.items.length === 0) break
          page += 1
        }
        this.clusters = items
        this.loaded = true
        this.loadError = null
        this.validateSelection()
      } catch (error) {
        // 加载失败：保留原缓存与 loaded 状态，记录错误，不伪装成空列表
        this.loadError = apiErrorMessage(error)
      }
    },

    /** 首屏恢复：先恢复记忆的选择，再加载列表校验其仍存在（架构 §2.3） */
    async restoreSelection(): Promise<void> {
      const remembered = readRememberedClusterId()
      if (remembered !== null && this.currentClusterId === null) {
        this.currentClusterId = remembered
      }
      await this.loadClusters()
    },

    /** 校验当前选择仍存在；失效则回退为空、清除持久化并标记待提示 */
    validateSelection(): void {
      if (this.currentClusterId === null) return
      if (!this.clusters.some((c) => c.id === this.currentClusterId)) {
        this.currentClusterId = null
        this.selectionDropped = true
        persistClusterId(null)
      }
    },

    /** UI 已提示“选择失效”，清除标记 */
    acknowledgeSelectionDrop(): void {
      this.selectionDropped = false
    },
  },
})
