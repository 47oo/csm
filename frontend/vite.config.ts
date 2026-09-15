import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// dev 反向代理目标：后端地址。
// 后端 dev server 默认监听 http://127.0.0.1:8000；如不同，用环境变量覆盖（无需 .env 文件）：
//   CSM_DEV_API_TARGET=http://127.0.0.1:9000 npm run dev
const devApiTarget = process.env.CSM_DEV_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      // 产品 API 前缀（契约见 docs/api/；F001 起含 /api/clusters）。
      // F012 的非产品自检面 /_foundation/* 已于 F001 彻底移除，不再代理。
      '/api': { target: devApiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.spec.ts'],
  },
})
