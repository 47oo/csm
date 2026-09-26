import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createAppRouter } from './index'
import { useAuthStore } from '../stores/auth'
import type { CurrentUser } from '../api/types'

// 路由守卫单测：直接设置 auth store 状态（initialized=true），
// 不触发 /auth/me 网络请求；守卫分支逻辑不依赖 API。
vi.mock('../api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
  changePassword: vi.fn(),
}))

function setUser(user: CurrentUser | null): void {
  const auth = useAuthStore()
  auth.$patch({ user, initialized: true, initError: null })
}

const admin: CurrentUser = {
  id: 1,
  username: 'admin',
  role: 'admin',
  status: 'enabled',
  must_change_password: false,
}
const maintainer: CurrentUser = {
  id: 2,
  username: 'ops01',
  role: 'maintainer',
  status: 'enabled',
  must_change_password: false,
}
const adminForced: CurrentUser = {
  id: 1,
  username: 'admin',
  role: 'admin',
  status: 'enabled',
  must_change_password: true,
}

let router: ReturnType<typeof createAppRouter>

beforeEach(() => {
  setActivePinia(createPinia())
  router = createAppRouter()
})

async function navigateTo(path: string) {
  try {
    await router.push(path)
  } catch {
    // 路由重定向本身不抛错；吞掉意外错误以便断言最终位置
  }
  await router.isReady()
}

describe('路由守卫：未登录', () => {
  it('访问受保护页面跳转 /login 并携带回跳地址', async () => {
    setUser(null)
    await navigateTo('/admin/users')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/admin/users')
  })

  it('访问首页同样跳转 /login', async () => {
    setUser(null)
    await navigateTo('/')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('访问 /change-password 跳转 /login', async () => {
    setUser(null)
    await navigateTo('/change-password')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('未登录可直接访问 /login', async () => {
    setUser(null)
    await navigateTo('/login')
    expect(router.currentRoute.value.name).toBe('login')
  })
})

describe('路由守卫：已登录', () => {
  it('访问 /login 跳转首页', async () => {
    setUser(admin)
    await navigateTo('/login')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('admin 可进入 /admin/users', async () => {
    setUser(admin)
    await navigateTo('/admin/users')
    expect(router.currentRoute.value.name).toBe('admin-users')
  })

  it('非 admin（maintainer）进入 /admin/users 被拒绝并重定向首页', async () => {
    setUser(maintainer)
    await navigateTo('/admin/users')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('viewer 进入 /admin/users 同样被拒绝', async () => {
    setUser({ ...maintainer, role: 'viewer' })
    await navigateTo('/admin/users')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('普通用户可进入首页与改密页', async () => {
    setUser(maintainer)
    await navigateTo('/')
    expect(router.currentRoute.value.name).toBe('home')
    await navigateTo('/change-password')
    expect(router.currentRoute.value.name).toBe('change-password')
  })
})

describe('路由守卫：首登强制改密（must_change_password 不可绕过）', () => {
  it('强制改密用户访问首页被重定向到 /change-password', async () => {
    setUser(adminForced)
    await navigateTo('/')
    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('强制改密用户访问 /admin/users 被重定向到 /change-password', async () => {
    setUser(adminForced)
    await navigateTo('/admin/users')
    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('强制改密用户访问 /login 也被重定向到 /change-password', async () => {
    setUser(adminForced)
    await navigateTo('/login')
    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('强制改密用户可停留在 /change-password', async () => {
    setUser(adminForced)
    await navigateTo('/change-password')
    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('改密完成后（标记清除）可恢复访问其它页面', async () => {
    setUser(adminForced)
    await navigateTo('/')
    expect(router.currentRoute.value.name).toBe('change-password')
    // 模拟改密成功后 store 状态更新
    const auth = useAuthStore()
    auth.$patch({ user: { ...adminForced, must_change_password: false } })
    await navigateTo('/admin/users')
    expect(router.currentRoute.value.name).toBe('admin-users')
  })
})

describe('路由守卫：初始化探测', () => {
  it('未初始化时守卫触发一次 init（探测 /auth/me）', async () => {
    const auth = useAuthStore()
    auth.$patch({ user: null, initialized: false })
    // init → fetchMe → me()（mock 模块），默认 resolve undefined 会被视为失败？
    // mock me 返回 admin 会话
    const { me } = await import('../api/auth')
    vi.mocked(me).mockResolvedValue(admin)
    await navigateTo('/')
    expect(router.currentRoute.value.name).toBe('home')
    expect(me).toHaveBeenCalledTimes(1)
  })
})
