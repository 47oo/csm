import { ref, shallowRef } from 'vue'
import type { Ref, ShallowRef } from 'vue'
import { ApiError } from '../api/http'

export interface UseAsyncQueryReturn<T> {
  data: ShallowRef<T | null>
  loading: Ref<boolean>
  error: Ref<ApiError | null>
  run: () => Promise<void>
}

/**
 * 极简异步查询基座：管理一次请求的 Loading / 数据 / Error 状态。
 *
 * - 竞态防护：只采纳最近一次 run() 的结果，过期响应被丢弃；
 * - 非 ApiError 的意外异常归一为 UNKNOWN_ERROR，组件层无需再判断异常类型。
 *
 * 该基座不引入任何额外依赖（无状态管理库）；列表的 Empty 判定
 * （data.items.length === 0）由调用方计算后交给 ListStates 渲染。
 */
export function useAsyncQuery<T>(fetcher: () => Promise<T>): UseAsyncQueryReturn<T> {
  const data = shallowRef<T | null>(null)
  const loading = ref(false)
  const error = ref<ApiError | null>(null)
  let sequence = 0

  async function run(): Promise<void> {
    const current = ++sequence
    loading.value = true
    error.value = null
    try {
      const result = await fetcher()
      if (current !== sequence) return
      data.value = result
    } catch (err) {
      if (current !== sequence) return
      data.value = null
      error.value =
        err instanceof ApiError
          ? err
          : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
    } finally {
      if (current === sequence) {
        loading.value = false
      }
    }
  }

  return { data, loading, error, run }
}
