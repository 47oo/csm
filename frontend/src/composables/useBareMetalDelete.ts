import { deleteBareMetal } from '../api/bareMetals'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * BareMetal 删除流程基座（F002，契约 docs/api/f002-bare-metal.md §3.5）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 渲染、401 全局处理、防重复提交）
 * 由 useResourceDelete 提供；本函数仅绑定 BareMetal 的删除端点与文案。
 *
 * 注意：409 CONFLICT（ACTIVE_CHILDREN_EXIST）在 F002 内不可达（BareMetal 当前
 * 无子资源表），该分支由 F004 / F006 / F007 / F008 落地子资源后触发；
 * 本层不假定「BareMetal 永远无子资源」，按 error.code 正常分支（§21）。
 */
export function useBareMetalDelete(options: UseResourceDeleteCallerOptions): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteBareMetal,
    onRemoved: options.onRemoved,
    resourceName: '裸金属',
  })
}
