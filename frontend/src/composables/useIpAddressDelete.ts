import { deleteIpAddress } from '../api/ipAddresses'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * IPAddress 删除流程基座（F005，契约 docs/api/f005-ip-address.md §3.5）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 按 error.code 渲染、401 全局
 * 处理、防重复提交）由 useResourceDelete 提供；本函数仅绑定 IPAddress 的
 * 删除端点与文案。
 *
 * 注意：契约 §3.5 在 V1 不存在 409 触发路径（IPAddress 是叶子资源，活跃子
 * 检查显式为空元组），但本层**不假定「IP 永远无子资源」**：未来若 IP 获得
 * 子资源，删除守卫（409 CONFLICT + details[].code === 'ACTIVE_CHILDREN_EXIST'）
 * 仍由后端裁决（§21），本层按 error.code 正常分支，无需修改。
 */
export function useIpAddressDelete(
  options: UseResourceDeleteCallerOptions,
): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteIpAddress,
    onRemoved: options.onRemoved,
    resourceName: 'IP 地址',
  })
}
