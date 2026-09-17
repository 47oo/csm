import { deleteContainer } from '../api/containers'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * Container 删除流程基座（F007，契约 docs/api/f007-container.md §4.5）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 按 error.code 渲染、401 全局
 * 处理、防重复提交）由 useResourceDelete 提供；本函数仅绑定 Container 的
 * 删除端点与文案。
 *
 * 注意：契约 §4.5 在 F007 内不存在 409 触发路径（CONTAINER_ACTIVE_CHILD_CHECKS
 * 当前为显式空元组，代表「Service 表尚不存在」而非「Container 无子资源」），
 * 但本层**不假定「Container 永远无子资源」**：F008 落地 Service 后，删除守卫
 * （409 CONFLICT + details[].code === 'ACTIVE_CHILDREN_EXIST'）仍由后端裁决
 * （§21），本层按 error.code 正常分支，无需修改。
 */
export function useContainerDelete(
  options: UseResourceDeleteCallerOptions,
): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteContainer,
    onRemoved: options.onRemoved,
    resourceName: '容器',
  })
}
