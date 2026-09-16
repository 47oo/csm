import { computed, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { ApiError } from '../api/http'

/** 删除失败提示视图：由稳定错误码驱动，不解析 message（api-conventions.md §5）。 */
export interface DeleteErrorView {
  /** 原始 error.code（排障 / 测试锚点，不改写、不丢失）。 */
  code: string
  title: string
  description: string
}

export interface UseResourceDeleteOptions {
  /** 资源删除函数（DELETE /api/<resource>/{id}，写操作一律走 id）。 */
  remove: (id: number) => Promise<void>
  /**
   * 资源已不在活跃集合时调用：删除成功（204），或 404 NOT_FOUND
   * （不存在 / 已被逻辑删除，两者不区分）。两种结果对前端同构：
   * 调用方刷新视图即可 —— 列表页重新拉取（被删行消失，当前页变空 → Empty 态），
   * 详情页重新读取 → 服务端返回 404 → 既有独立 Not Found 态。
   */
  onRemoved: () => void | Promise<void>
  /** 错误文案中的资源名（如「集群」「裸金属」），仅用于展示。 */
  resourceName: string
}

export interface UseResourceDeleteReturn {
  /** 正在删除的资源 id；null = 无进行中的删除（重复提交被拦截）。 */
  deletingId: Ref<number | null>
  /** 删除失败提示视图；无失败（或交由全局处理的 401）时为 null。 */
  deleteErrorView: ComputedRef<DeleteErrorView | null>
  /** 二次确认通过后发起删除；提交中的重复调用被直接忽略。 */
  requestDelete: (id: number) => Promise<void>
  /** 清除删除失败提示（用户关闭提示时调用；重新发起删除时自动清除）。 */
  clearDeleteError: () => void
}

/** 资源专属包装（useClusterDelete / useBareMetalDelete）的调用方选项。 */
export type UseResourceDeleteCallerOptions = Pick<UseResourceDeleteOptions, 'onRemoved'>

/**
 * 资源逻辑删除流程基座（F014 统一软删服务的前端侧；Cluster 与 BareMetal 共用）。
 *
 * - 「是否存在活跃子资源」等删除守卫由**后端**裁决（§21）；本层不做任何
 *   业务预判（不禁用、不隐藏入口），只依据响应的稳定 error.code 分支；
 * - 404（不存在或已被逻辑删除）与 204 成功对前端同构：资源已不在活跃集合，
 *   通知调用方刷新视图，不作为错误渲染；
 * - 401 交由既有全局会话失效处理（api/http.ts → App 切回登录页），
 *   本层不渲染删除失败提示；
 * - 其余失败（409 CONFLICT、网络错误等）保留 ApiError，由 deleteErrorView
 *   按 error.code（必要时 details[].code）生成固定文案，不解析 message。
 */
export function useResourceDelete(options: UseResourceDeleteOptions): UseResourceDeleteReturn {
  const deletingId = ref<number | null>(null)
  const deleteError = ref<ApiError | null>(null)

  const deleteErrorView = computed<DeleteErrorView | null>(() => {
    const error = deleteError.value
    if (error === null) return null
    if (error.code === 'CONFLICT') {
      // 契约错误信封：409 的稳定判别值为 error.code === 'CONFLICT' +
      // details[].code === 'ACTIVE_CHILDREN_EXIST'；message 不构成契约，
      // 仅用于展示且不参与分支。
      const hasActiveChildren = error.details.some(
        (detail) => detail.code === 'ACTIVE_CHILDREN_EXIST',
      )
      return {
        code: error.code,
        title: `无法删除${options.resourceName}`,
        description: hasActiveChildren
          ? `该${options.resourceName}仍存在活跃子资源，无法删除。`
          : '删除操作与现有数据冲突，请稍后重试。',
      }
    }
    return {
      code: error.code,
      title: '删除失败',
      description: `删除请求未成功（${error.code}），请稍后重试。`,
    }
  })

  async function requestDelete(id: number): Promise<void> {
    // 提交中禁止重复提交（同一行连点或跨行并发均被拦截）。
    if (deletingId.value !== null) return
    deletingId.value = id
    deleteError.value = null
    let removed = false
    try {
      try {
        await options.remove(id)
        removed = true
      } catch (err) {
        const apiError =
          err instanceof ApiError
            ? err
            : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
        if (apiError.code === 'NOT_FOUND') {
          // 不存在或已被逻辑删除（两者不区分）→ 与成功同构，刷新视图即可。
          removed = true
        } else if (apiError.code !== 'UNAUTHENTICATED') {
          // 401 由全局会话失效处理；其余失败按 error.code 渲染。
          deleteError.value = apiError
        }
      }
      if (removed) {
        await options.onRemoved()
      }
    } finally {
      deletingId.value = null
    }
  }

  function clearDeleteError(): void {
    deleteError.value = null
  }

  return { deletingId, deleteErrorView, requestDelete, clearDeleteError }
}
