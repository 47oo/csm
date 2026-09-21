import { deleteIpAddressRange } from '../api/ipAddressRanges'
import { useResourceDelete } from './useResourceDelete'
import type {
  DeleteErrorView,
  UseResourceDeleteCallerOptions,
  UseResourceDeleteReturn,
} from './useResourceDelete'

export type { DeleteErrorView, UseResourceDeleteCallerOptions, UseResourceDeleteReturn }

/**
 * IPAddressRange 删除流程基座（F020，契约 docs/api/f020-ip-address-range.md
 * §3.5）。
 *
 * 通用流程（204 / 404 同构刷新、409 CONFLICT 按 error.code 渲染、401 全局
 * 处理、防重复提交）由 useResourceDelete 提供；本函数仅绑定范围段的删除
 * 端点与文案。
 *
 * 删除守卫（契约 §3.5 / §4.2）：范围内仍有同 Cluster 活跃 IPAddress（字面
 * 落在 [start_ip, end_ip] 内）时禁止删除 → 409 CONFLICT +
 * details[].code === 'ACTIVE_CHILDREN_EXIST'。守卫由后端裁决（§21），本层
 * 不预判、不禁用、不隐藏入口；文案按契约语义表达为「该范围内仍有活跃 IP」
 * （须先软删这些 IP 后方可删除，无需物理删除）。
 */
export function useIpAddressRangeDelete(
  options: UseResourceDeleteCallerOptions,
): UseResourceDeleteReturn {
  return useResourceDelete({
    remove: deleteIpAddressRange,
    onRemoved: options.onRemoved,
    resourceName: 'IP 地址范围段',
    activeChildrenDescription:
      '该范围内仍有活跃 IP，无法删除。请先软删范围内的活跃 IP 后重试。',
  })
}
