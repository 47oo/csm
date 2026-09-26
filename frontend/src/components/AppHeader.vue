<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiErrorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { roleLabel } from '../utils/validation'

const router = useRouter()
const auth = useAuthStore()

async function handleLogout(): Promise<void> {
  try {
    await auth.logout()
    ElMessage.success('已退出登录')
  } catch (error) {
    // 登出接口异常时本地会话已在 store 中清除，仍返回登录页
    ElMessage.warning(`已返回登录页（${apiErrorMessage(error)}）`)
  }
  void router.push({ name: 'login' })
}
</script>

<template>
  <header class="app-header">
    <div class="app-header-inner">
      <span class="app-title">CSM 资源管理平台</span>
      <div v-if="auth.user" class="app-user">
        <span class="app-user-name">
          {{ auth.user.username }}（{{ roleLabel(auth.user.role) }}）
        </span>
        <el-button link type="primary" @click="router.push({ name: 'change-password' })">
          修改密码
        </el-button>
        <el-button v-if="auth.isAdmin" link type="primary" @click="router.push({ name: 'admin-users' })">
          用户管理
        </el-button>
        <el-button link @click="handleLogout">退出登录</el-button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  background-color: #1f2d3d;
  color: #fff;
}
.app-header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.app-title {
  font-size: 16px;
  font-weight: 600;
}
.app-user {
  display: flex;
  align-items: center;
  gap: 4px;
}
.app-user-name {
  margin-right: 8px;
  color: #cfd8e3;
}
</style>
