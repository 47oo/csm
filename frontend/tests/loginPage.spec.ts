import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import LoginPage from '../src/pages/LoginPage.vue'

/**
 * 登录页三态测试（T-17 / AC-06）：默认 / 提交 Loading / 401 失败提示互不相同；
 * 仅必填校验（R-AUTH-004 不属登录路径）；成功 → emit success。
 * 响应体严格按 docs/api/f013-auth.md §5.1 构造；fetch 全部桩替换。
 */

const SESSION_USER = { id: 1, username: 'admin' }
const UNAUTHENTICATED_BODY = {
  error: { code: 'UNAUTHENTICATED', message: '与展示无关的后端文案', details: [] },
}
const INTERNAL_ERROR_BODY = { error: { code: 'INTERNAL_ERROR', message: '内部错误' } }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 可控的挂起响应：让提交 Loading 态可确定性观察。 */
function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function mountPage() {
  return mount(LoginPage, { global: { plugins: [ElementPlus] } })
}

function viewState(wrapper: VueWrapper): string {
  const state = wrapper.find('[data-state]').attributes('data-state')
  expect(state).toBeDefined()
  return state!
}

function findSubmit(wrapper: VueWrapper) {
  const button = wrapper.findAll('button').find((b) => b.text().includes('登录'))
  expect(button).toBeDefined()
  return button!
}

async function fillCredentials(wrapper: VueWrapper, username: string, password: string) {
  await wrapper.find('input[autocomplete="username"]').setValue(username)
  await wrapper.find('input[autocomplete="current-password"]').setValue(password)
}

async function submitForm(wrapper: VueWrapper) {
  await wrapper.find('form').trigger('submit')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LoginPage 三态互不相同（T-17 / AC-06）', () => {
  it('默认态：username / password 表单可提交，无失败提示；password 为 type=password + autocomplete=current-password', () => {
    vi.stubGlobal('fetch', vi.fn())

    const wrapper = mountPage()

    expect(viewState(wrapper)).toBe('default')
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    const passwordInput = wrapper.find('input[autocomplete="current-password"]')
    expect(passwordInput.exists()).toBe(true)
    expect(passwordInput.attributes('type')).toBe('password')
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)
    expect(findSubmit(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('提交 Loading 态：请求进行中按钮 loading / 禁止重复提交，无失败提示', async () => {
    const { promise, resolve } = deferredResponse()
    const fetchMock = vi.fn(async () => promise)
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await fillCredentials(wrapper, 'admin', 'correct horse battery staple')
    await submitForm(wrapper)

    await vi.waitFor(() => {
      expect(viewState(wrapper)).toBe('loading')
    })
    // 提交中：按钮禁用，失败提示不出现。
    expect(findSubmit(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-error-code]').exists()).toBe(false)

    // 等待第一个请求真正发出（el-form 校验异步完成后），再验证重复提交被拦截。
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    // 连续触发提交（连点 / 连按回车）不得发出第二个请求。
    await submitForm(wrapper)
    await submitForm(wrapper)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    resolve(jsonResponse(200, SESSION_USER))
    await vi.waitFor(() => {
      expect(wrapper.emitted('success')).toEqual([[SESSION_USER]])
    })
  })

  it('401 失败态：停留登录页 + 固定失败提示（按 error.code 分支，不解析 message）', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, UNAUTHENTICATED_BODY)))

    const wrapper = mountPage()
    await fillCredentials(wrapper, 'admin', 'wrong-password')
    await submitForm(wrapper)

    await vi.waitFor(() => {
      expect(viewState(wrapper)).toBe('error')
    })

    const alert = wrapper.find('[data-error-code]')
    expect(alert.attributes('data-error-code')).toBe('UNAUTHENTICATED')
    // 固定失败提示；后端 message 不参与展示（R-AUTH-006：前端不区分失败原因）。
    expect(alert.text()).toContain('用户名或口令不正确')
    expect(alert.text()).not.toContain('与展示无关的后端文案')

    // 停留登录页：表单仍在，可再次提交（按钮未禁用）。
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(findSubmit(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('非 401 失败（500 INTERNAL_ERROR）→ 通用失败提示，按 error.code 分支', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(500, INTERNAL_ERROR_BODY)))

    const wrapper = mountPage()
    await fillCredentials(wrapper, 'admin', 'whatever')
    await submitForm(wrapper)

    await vi.waitFor(() => {
      expect(viewState(wrapper)).toBe('error')
    })

    const alert = wrapper.find('[data-error-code]')
    expect(alert.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(alert.text()).toContain('登录失败，请稍后重试')
  })

  it('网络错误 → NETWORK_ERROR 分支提示', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )

    const wrapper = mountPage()
    await fillCredentials(wrapper, 'admin', 'whatever')
    await submitForm(wrapper)

    await vi.waitFor(() => {
      expect(viewState(wrapper)).toBe('error')
    })

    const alert = wrapper.find('[data-error-code]')
    expect(alert.attributes('data-error-code')).toBe('NETWORK_ERROR')
    expect(alert.text()).toContain('无法连接服务器')
  })
})

describe('LoginPage 校验与成功路径', () => {
  it('仅必填校验：空字段提交 → 不发请求，字段级提示；短口令照常提交（R-AUTH-004 不属登录路径）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(401, UNAUTHENTICATED_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()

    // 两个字段均为空 → 必填校验失败，不发出登录请求。
    await submitForm(wrapper)
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('请输入用户名')
    })
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('请输入口令')
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(viewState(wrapper)).toBe('default')

    // 1 位口令：前端不做长度 / 复杂度校验，原样提交，由服务端统一返回 401。
    await fillCredentials(wrapper, 'admin', 'x')
    await submitForm(wrapper)
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
        '/api/auth/login',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ username: 'admin', password: 'x' }),
        }),
      )
    })
    await vi.waitFor(() => {
      expect(viewState(wrapper)).toBe('error')
    })
  })

  it('成功 → emit success(AuthenticatedUser)，进入系统（由 App 切换视图）', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SESSION_USER))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountPage()
    await fillCredentials(wrapper, 'admin', 'correct horse battery staple')
    await submitForm(wrapper)

    await vi.waitFor(() => {
      expect(wrapper.emitted('success')).toEqual([[{ id: 1, username: 'admin' }]])
    })
    expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ username: 'admin', password: 'correct horse battery staple' }),
      }),
    )
  })
})
