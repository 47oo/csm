<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import AppHeader from './components/AppHeader.vue'

const route = useRoute()
const auth = useAuthStore()

// 登录页无页头；must_change_password 强制改密时也隐藏页头，避免引导出不可达入口
const showHeader = computed(
  () => route.meta.layout !== 'bare' && !auth.mustChangePassword,
)
</script>

<template>
  <div class="app-shell">
    <AppHeader v-if="showHeader" />
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
}
body {
  font-family:
    'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
  background-color: #f5f7fa;
}
.app-shell {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.app-main {
  flex: 1;
}
</style>
