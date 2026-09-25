import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ApiError } from '../api/client'
import type { CurrentUser } from '../api/types'
import { useAuthStore } from './auth'

// 替换 API 模块：store 单测只验证状态逻辑，不发真实请求
vi.mock('../api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
  changePassword: vi.fn(),
}))

import * as authApi from '../api/auth'

const adminUser: CurrentUser = {
  id: 1,
  username: 'admin',
  role: 'admin',
  status: 'enabled',
  must_change_password: false,
}

const viewerForced: CurrentUser = {
  id: 2,
  username: 'viewer01',
  role: 'viewer',
  status: 'enabled',
  must_change_password: true,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useAuthStore：登录', () => {
  it('登录成功写入当前用户并标记 initialized', async () => {
    vi.mocked(authApi.login).mockResolvedValue(adminUser)
    const auth = useAuthStore()
    await auth.login('admin', 'Passw0rd')
    expect(auth.user).toEqual(adminUser)
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.isAdmin).toBe(true)
    expect(auth.initialized).toBe(true)
  })

  it('登录失败（401 INVALID_CREDENTIALS）错误上抛，不写入用户', async () => {
    vi.mocked(authApi.login).mockRejectedValue(
      new ApiError(401, 'INVALID_CREDENTIALS', '用户名或口令错误'),
    )
    const auth = useAuthStore()
    await expect(auth.login('admin', 'wrong')).rejects.toMatchObject({
      code: 'INVALID_CREDENTIALS',
    })
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('首登强制改密用户登录后 mustChangePassword 为 true', async () => {
    vi.mocked(authApi.login).mockResolvedValue(viewerForced)
    const auth = useAuthStore()
    await auth.login('viewer01', 'Passw0rd')
    expect(auth.mustChangePassword).toBe(true)
    expect(auth.isAdmin).toBe(false)
  })
})

describe('useAuthStore：登出', () => {
  it('登出成功清除用户', async () => {
    vi.mocked(authApi.login).mockResolvedValue(adminUser)
    vi.mocked(authApi.logout).mockResolvedValue(undefined)
    const auth = useAuthStore()
    await auth.login('admin', 'Passw0rd')
    await auth.logout()
    expect(auth.user).toBeNull()
    expect(auth.initialized).toBe(true)
  })

  it('登出接口异常时仍清除本地会话（不保留假会话），错误上抛由调用方处理', async () => {
    vi.mocked(authApi.login).mockResolvedValue(adminUser)
    vi.mocked(authApi.logout).mockRejectedValue(new ApiError(0, 'NETWORK_ERROR', '网络错误'))
    const auth = useAuthStore()
    await auth.login('admin', 'Passw0rd')
    await expect(auth.logout()).rejects.toBeInstanceOf(ApiError)
    expect(auth.user).toBeNull()
  })
})

describe('useAuthStore：fetchMe / init', () => {
  it('fetchMe 成功写入用户', async () => {
    vi.mocked(authApi.me).mockResolvedValue(adminUser)
    const auth = useAuthStore()
    await auth.fetchMe()
    expect(auth.user).toEqual(adminUser)
    expect(auth.initialized).toBe(true)
    expect(auth.initError).toBeNull()
  })

  it('fetchMe 401 属正常未登录：user=null 且不记 initError', async () => {
    vi.mocked(authApi.me).mockRejectedValue(new ApiError(401, 'UNAUTHENTICATED', '未登录'))
    const auth = useAuthStore()
    await auth.fetchMe()
    expect(auth.user).toBeNull()
    expect(auth.initialized).toBe(true)
    expect(auth.initError).toBeNull()
  })

  it('fetchMe 网络错误记入 initError，不伪装成正常未登录', async () => {
    vi.mocked(authApi.me).mockRejectedValue(new ApiError(0, 'NETWORK_ERROR', '网络错误，请检查与服务器的连接后重试'))
    const auth = useAuthStore()
    await auth.fetchMe()
    expect(auth.user).toBeNull()
    expect(auth.initError).toBe('网络错误，请检查与服务器的连接后重试')
  })

  it('init 只探测一次（initialized 后不再请求）', async () => {
    vi.mocked(authApi.me).mockResolvedValue(adminUser)
    const auth = useAuthStore()
    await auth.init()
    await auth.init()
    expect(authApi.me).toHaveBeenCalledTimes(1)
  })
})

describe('useAuthStore：改密与会话状态', () => {
  it('changePassword 成功后本地清除 must_change_password', async () => {
    vi.mocked(authApi.login).mockResolvedValue(viewerForced)
    vi.mocked(authApi.changePassword).mockResolvedValue(undefined)
    const auth = useAuthStore()
    await auth.login('viewer01', 'Passw0rd')
    expect(auth.mustChangePassword).toBe(true)
    await auth.changePassword('Passw0rd', 'NewPass1')
    expect(auth.mustChangePassword).toBe(false)
    expect(authApi.changePassword).toHaveBeenCalledWith({
      current_password: 'Passw0rd',
      new_password: 'NewPass1',
    })
  })

  it('changePassword 失败时错误上抛且保留 must_change_password', async () => {
    vi.mocked(authApi.login).mockResolvedValue(viewerForced)
    vi.mocked(authApi.changePassword).mockRejectedValue(
      new ApiError(400, 'INVALID_CURRENT_PASSWORD', '当前口令错误'),
    )
    const auth = useAuthStore()
    await auth.login('viewer01', 'Passw0rd')
    await expect(auth.changePassword('bad', 'NewPass1')).rejects.toMatchObject({
      code: 'INVALID_CURRENT_PASSWORD',
    })
    expect(auth.mustChangePassword).toBe(true)
  })

  it('clearSession：401 拦截时清除本地会话', async () => {
    vi.mocked(authApi.login).mockResolvedValue(adminUser)
    const auth = useAuthStore()
    await auth.login('admin', 'Passw0rd')
    auth.clearSession()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('markMustChangePassword：服务端 403 PASSWORD_CHANGE_REQUIRED 时同步标记', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ ...viewerForced, must_change_password: false })
    const auth = useAuthStore()
    await auth.login('viewer01', 'Passw0rd')
    expect(auth.mustChangePassword).toBe(false)
    auth.markMustChangePassword()
    expect(auth.mustChangePassword).toBe(true)
  })
})
