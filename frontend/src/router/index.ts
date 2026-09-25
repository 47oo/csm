// 路由与守卫（架构 §2.4）：
// - 未登录访问受保护页面 → /login（携带回跳地址）
// - 已登录访问 /login → 首页（must_change_password 时 → /change-password）
// - must_change_password 只能进入 /change-password（首登强制改密不可绕过）
// - /admin/* 仅 admin 可进；非 admin 重定向首页（服务端仍做最终校验）
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true, layout: 'bare' },
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('../views/ChangePasswordView.vue'),
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('../views/AdminUsersView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    redirect: '/',
  },
]

/** 工厂函数：测试可创建独立 router 实例 */
export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes,
  })

  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    if (!auth.initialized) {
      await auth.init()
    }

    // 未登录 → 登录页（公开页除外）
    if (!auth.isAuthenticated && !to.meta.public) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    if (auth.isAuthenticated) {
      // 已登录访问 /login → 首页/改密页
      if (to.name === 'login') {
        return auth.mustChangePassword ? { name: 'change-password' } : { name: 'home' }
      }
      // 首登强制改密：除 /change-password 外一律拦截
      if (auth.mustChangePassword && to.name !== 'change-password') {
        return { name: 'change-password' }
      }
      // /admin/* 仅平台管理员
      if (to.meta.requiresAdmin && !auth.isAdmin) {
        return { name: 'home' }
      }
    }

    return true
  })

  return router
}
