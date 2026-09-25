// 全局 401/403 处理器装配：连接 axios 客户端、Pinia auth store 与 router。
// 在 main.ts 中 pinia 激活后调用一次；client.test.ts 注入替身验证分支逻辑。
import { ElMessage } from 'element-plus'
import type { Router } from 'vue-router'
import { setApiHandlers, type ApiError } from './client'
import { useAuthStore } from '../stores/auth'

export function installApiHandlers(router: Router): void {
  setApiHandlers({
    // 401：会话失效（UNAUTHENTICATED）→ 清除本地会话并跳登录页（保留回跳地址）。
    onUnauthorized(_error: ApiError) {
      const auth = useAuthStore()
      auth.clearSession()
      const current = router.currentRoute.value
      if (current.name !== 'login') {
        void router.push({ name: 'login', query: { redirect: current.fullPath } })
      }
    },
    // 403（FORBIDDEN / ACCOUNT_DISABLED 等）：服务端已拒绝，提示即可，数据不变。
    onForbidden(error: ApiError) {
      ElMessage.error(error.message || '没有权限执行此操作')
    },
    // 403 PASSWORD_CHANGE_REQUIRED：强制进入改密页（服务端拦截，前端不可绕过）。
    onPasswordChangeRequired(_error: ApiError) {
      const auth = useAuthStore()
      auth.markMustChangePassword()
      if (router.currentRoute.value.name !== 'change-password') {
        void router.push({ name: 'change-password' })
      }
    },
  })
}
