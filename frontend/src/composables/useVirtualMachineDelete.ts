import { deleteVirtualMachine } from '../api/virtualMachines'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * VirtualMachine 删除流程基座（F006，契约 docs/api/f006-virtual-machine.md §3.5）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 渲染、401 全局处理、防重复提交）
 * 由 useResourceDelete 提供；本函数仅绑定 VirtualMachine 的删除端点与文案。
 *
 * 注意：409 CONFLICT（ACTIVE_CHILDREN_EXIST）在 F006 内不可达（VM 当前无
 * 子资源表），该分支由 F007 落地 Container 后触发；本层不假定
 * 「VirtualMachine 永远无子资源」，按 error.code 正常分支（§21）。
 */
export function useVirtualMachineDelete(
  options: UseResourceDeleteCallerOptions,
): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteVirtualMachine,
    onRemoved: options.onRemoved,
    resourceName: '虚拟机',
  })
}
