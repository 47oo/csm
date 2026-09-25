# CSM 前端（F013 用户与角色管理）

Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router（ADR-001）。

## 命令

```bash
pnpm install   # 安装依赖
pnpm dev       # 开发服务器（:5173，/api 代理到 http://localhost:8000）
pnpm test      # Vitest 单测（守卫 / store / 校验 / 错误映射 / API 参数）
pnpm build     # vue-tsc 类型检查 + vite 构建（dist/）
```

## 与后端的集成方式

- 全部请求走真实 API：axios 客户端 `baseURL=/api/v1`、`withCredentials=true`，
  会话由后端下发的 HttpOnly Cookie `csm_session` 承载（ADR-004）。
- 开发期通过 Vite 代理保持与后端同源（`vite.config.ts` → `/api` → `http://localhost:8000`），
  避免 CORS 与跨站 Cookie 问题；生产部署由反向代理统一入口。
- 本工程**没有使用任何 Mock / Fixture**，契约依据 `docs/api/F013.md`（唯一字段清单）。

## 范围（F013）

- `/login` 登录页；`/change-password` 首登强制改密 / 自助改密；`/admin/users` 用户管理（admin）
- 路由守卫：未登录 → `/login`；非 admin 不可进 `/admin/*`；`must_change_password` 强制改密
- 统一错误处理：problem+json 字段级错误、401 跳登录、403 提示、
  403 PASSWORD_CHANGE_REQUIRED 强制改密、409（USERNAME_TAKEN / VERSION_CONFLICT / LAST_ADMIN）
  保留输入并提示（`src/api/client.ts` + `src/api/handlers.ts`）
