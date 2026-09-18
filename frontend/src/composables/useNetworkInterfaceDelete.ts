import { deleteNetworkInterface } from '../api/networkInterfaces'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * NetworkInterface 删除流程基座（F004，契约 docs/api/f004-network-interface.md §3.5）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 按 details[].code ===
 * 'ACTIVE_CHILDREN_EXIST' 渲染、401 全局处理、防重复提交）由 useResourceDelete
 * 提供；本函数仅绑定 NetworkInterface 的删除端点与文案。
 *
 * 注意：409 CONFLICT（ACTIVE_CHILDREN_EXIST，契约 §4.1）在 F004 内不可达
 * （ip_addresses 表尚不存在，检查点显式空元组），该分支由 F005 落地
 * IPAddress 后触发；本层**不假定「NetworkInterface 永远无子资源」**，
 * 按 error.code 正常分支（§21）。
 */
export function useNetworkInterfaceDelete(
  options: UseResourceDeleteCallerOptions,
): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteNetworkInterface,
    onRemoved: options.onRemoved,
    resourceName: '网络接口',
  })
}
