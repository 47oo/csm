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
      // 产品 API 前缀（F012 仅有 /api/health；资源 API 自 F001 起交付）。
      '/api': { target: devApiTarget, changeOrigin: true },
      // F012 非产品自检面（仅 dev/test 挂载，生产不可达；见 docs/api/f012-project-foundation.md §4）。
      '/_foundation': { target: devApiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.spec.ts'],
  },
})
