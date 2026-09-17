import { deleteService } from '../api/services'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * Service 删除流程基座（F008，契约 docs/api/f008-service.md §4.5）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 按 error.code 渲染、401 全局
 * 处理、防重复提交）由 useResourceDelete 提供；本函数仅绑定 Service 的
 * 删除端点与文案。
 *
 * 注意：契约 §4.5 在 F008 内 Service 删除不产生 409（SERVICE_ACTIVE_CHILD_
 * CHECKS 为显式空元组，Service 无子资源），但本层**不假定**未来不存在
 * 其他冲突形态：任何失败仍按 error.code 分支渲染（§21），无需修改。
 */
export function useServiceDelete(
  options: UseResourceDeleteCallerOptions,
): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteService,
    onRemoved: options.onRemoved,
    resourceName: '服务',
  })
}
