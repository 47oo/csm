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
    // F004-T-01 根因修复：宿主机系统时钟会周期性向后跳变，导致 Vue 事件
    // invoker 去重（e._vts <= invoker.attached）静默吞掉 VTU trigger 的点击，
    // 登记用例非确定性超时。setup 将测试进程内 Date.now() 单调化（时钟正常时
    // 为恒等操作），详见 tests/setup/monotonic-date-now.ts 头注。
    setupFiles: ['tests/setup/monotonic-date-now.ts'],
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
    // 同一原因下，单条用例内的多段 waitForUi（各 5s 轮询）叠加后可能
    // 超过 vitest 默认单用例 5s 超时（与时序敏感断言本身无关），
    // 放宽单用例超时上限，不改变断言语义。
    testTimeout: 20000,
  },
})
