import { deleteCluster } from '../api/clusters'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * Cluster 删除流程基座（F014，契约 docs/api/f014-soft-delete.md）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 渲染、401 全局处理、防重复提交）
 * 由 useResourceDelete 提供；本函数仅绑定 Cluster 的删除端点与文案。
 */
export function useClusterDelete(options: UseResourceDeleteCallerOptions): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteCluster,
    onRemoved: options.onRemoved,
    resourceName: '集群',
  })
}
