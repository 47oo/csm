// 认证状态（架构 §2.4）：当前用户/角色/must_change_password；登录、登出、刷新 me。
import { defineStore } from 'pinia'
import * as authApi from '../api/auth'
import { isApiError } from '../api/client'
import type { CurrentUser } from '../api/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    /** 当前登录用户；null = 未登录 */
    user: null as CurrentUser | null,
    /** 是否已完成启动期会话探测（GET /auth/me） */
    initialized: false,
    /** 启动期探测失败（非 401，如网络错误）的错误信息；null = 无 */
    initError: null as string | null,
  }),
  getters: {
    isAuthenticated: (state): boolean => state.user !== null,
    isAdmin: (state): boolean => state.user?.role === 'admin',
    mustChangePassword: (state): boolean => state.user?.must_change_password === true,
  },
  actions: {
    /** 启动期初始化：只探测一次；路由守卫依赖 initialized 避免重复请求 */
    async init(): Promise<void> {
      if (this.initialized) return
      await this.fetchMe()
    },

    /** 刷新当前用户（GET /auth/me）：401 属正常未登录；其它错误记入 initError，不伪装成未登录 */
    async fetchMe(): Promise<void> {
      try {
        this.user = await authApi.me()
        this.initError = null
      } catch (error) {
        this.user = null
        if (isApiError(error) && error.status === 401) {
          this.initError = null
        } else if (isApiError(error)) {
          this.initError = error.message
        } else {
          this.initError = '无法连接服务器'
        }
      } finally {
        this.initialized = true
      }
    },

    /** 登录：成功写入当前用户；失败原样抛出（由登录页呈现错误） */
    async login(username: string, password: string): Promise<void> {
      this.user = await authApi.login({ username, password })
      this.initialized = true
      this.initError = null
    },

    /** 登出：无论接口成败都清除本地会话（finally）；接口异常向上抛出由调用方处理 */
    async logout(): Promise<void> {
      try {
        await authApi.logout()
      } finally {
        this.user = null
      }
    },

    /** 自助改密：成功后本地清除 must_change_password（服务端已清除并失效其它会话） */
    async changePassword(currentPassword: string, newPassword: string): Promise<void> {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      if (this.user) {
        this.user = { ...this.user, must_change_password: false }
      }
    },

    /** 会话失效（401 拦截）时清除本地状态 */
    clearSession(): void {
      this.user = null
    },

    /** 服务端 403 PASSWORD_CHANGE_REQUIRED 拦截时同步本地标记 */
    markMustChangePassword(): void {
      if (this.user && !this.user.must_change_password) {
        this.user = { ...this.user, must_change_password: true }
      }
    },
  },
})
