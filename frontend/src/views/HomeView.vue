<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { roleLabel } from '../utils/validation'

const router = useRouter()
const auth = useAuthStore()
</script>

<template>
  <div class="home-page">
    <el-card class="home-card">
      <h2>欢迎使用 CSM 资源管理平台</h2>
      <p v-if="auth.user">
        当前登录：<strong>{{ auth.user.username }}</strong>（{{ roleLabel(auth.user.role) }}）
      </p>
      <p class="home-hint">资源登记、查询与维护功能将随后续版本提供。</p>
      <div class="home-actions">
        <el-button type="primary" @click="router.push({ name: 'change-password' })">
          修改密码
        </el-button>
        <el-button
          v-if="auth.isAdmin"
          type="primary"
          plain
          @click="router.push({ name: 'admin-users' })"
        >
          用户管理
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 24px;
}
.home-card {
  padding: 8px 16px;
}
.home-hint {
  color: #909399;
}
.home-actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}
</style>
