<script setup lang="ts">
import DevSelfCheckPage from './pages/DevSelfCheckPage.vue'

// Vite 静态替换：生产构建中 import.meta.env.DEV 恒为 false，
// 自检页（依赖仅 dev 挂载的 /_foundation/*）不会在生产构建中渲染。
const isDev = import.meta.env.DEV
</script>

<template>
  <DevSelfCheckPage v-if="isDev" />
  <main v-else class="app-placeholder">
    <h1>CSM</h1>
    <p>前端基座已构建完成。产品界面自 F001 起交付，当前构建不包含产品页面。</p>
  </main>
</template>

<style scoped>
.app-placeholder {
  max-width: 720px;
  margin: 16vh auto 0;
  padding: 0 16px;
  text-align: center;
  color: #606266;
}

.app-placeholder h1 {
  color: #303133;
  font-weight: 600;
}
</style>
