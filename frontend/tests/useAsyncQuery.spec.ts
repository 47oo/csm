import { describe, expect, it, vi } from 'vitest'
import { useAsyncQuery } from '../src/composables/useAsyncQuery'
import { ApiError } from '../src/api/http'

/** 三态基座测试：useAsyncQuery 的 Loading / 数据 / Error 状态与竞态防护。 */

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useAsyncQuery', () => {
  it('成功：请求期间 loading 为 true，完成后写入 data、error 为 null', async () => {
    const { promise, resolve } = deferred<number>()
    const query = useAsyncQuery(() => promise)

    const running = query.run()
    expect(query.loading.value).toBe(true)

    resolve(42)
    await running

    expect(query.loading.value).toBe(false)
    expect(query.data.value).toBe(42)
    expect(query.error.value).toBeNull()
  })

  it('失败（ApiError）：error 被记录，data 置空', async () => {
    const { promise, reject } = deferred<never>()
    const query = useAsyncQuery(() => promise)
    const apiError = new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '内部错误' })

    const running = query.run()
    reject(apiError)
    await running

    expect(query.loading.value).toBe(false)
    expect(query.data.value).toBeNull()
    expect(query.error.value).toBe(apiError)
  })

  it('失败（非 ApiError 的意外异常）：归一为 UNKNOWN_ERROR', async () => {
    const { promise, reject } = deferred<never>()
    const query = useAsyncQuery(() => promise)

    const running = query.run()
    reject(new Error('意外错误'))
    await running

    expect(query.error.value).toBeInstanceOf(ApiError)
    expect(query.error.value?.code).toBe('UNKNOWN_ERROR')
  })

  it('重新 run 会清除上一次的 error', async () => {
    const fetcher = vi
      .fn<() => Promise<number>>()
      .mockRejectedValueOnce(
        new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '内部错误' }),
      )
      .mockResolvedValueOnce(7)
    const query = useAsyncQuery(fetcher)

    await query.run()
    expect(query.error.value).not.toBeNull()

    await query.run()
    expect(query.error.value).toBeNull()
    expect(query.data.value).toBe(7)
  })

  it('竞态防护：仅采纳最近一次请求的结果，过期响应被丢弃', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const fetcher = vi
      .fn<() => Promise<string>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const query = useAsyncQuery(fetcher)

    const runningFirst = query.run()
    const runningSecond = query.run()

    second.resolve('latest')
    await runningSecond
    expect(query.data.value).toBe('latest')
    expect(query.loading.value).toBe(false)

    // 过期的第一次请求随后完成：其结果不得覆盖最新状态。
    first.resolve('stale')
    await runningFirst
    expect(query.data.value).toBe('latest')
    expect(query.loading.value).toBe(false)
  })
})
