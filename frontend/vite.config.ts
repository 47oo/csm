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
    // element-plus（ESM 包）默认被外部化、由 Node 原生 import，
    // 其内部对 CJS 依赖 async-validator（无 exports 字段，main 指向 dist-node）
    // 的默认导入会解析成整个 module.exports 而非构造函数，导致 el-form
    // 校验在测试环境静默失效（validate 恒为 true）。
    // 浏览器构建走 module 字段（dist-web ESM）无此问题。
    // 内联 element-plus 后其依赖经 Vite 解析，回归正常。
    server: {
      deps: {
        inline: ['element-plus'],
      },
    },
    // 全量并行时多个 worker 同时内联转换 element-plus 会争抢 CPU，
    // 使既有 vi.waitFor（默认 1000ms）偶发超时；限制并发 worker 数
    // 并持久化模块转换缓存，保证时序敏感用例的确定性。
    maxWorkers: 4,
    fsModuleCache: true,
  },
})
