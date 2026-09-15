# CSM Frontend

CSM Web 前端。当前为 **F012 前端基座**。

技术栈（ADR-0001，`ACCEPTED`）：**Vue 3 + TypeScript + Vite + Element Plus**。除该技术栈外未引入其他状态管理 / UI / CSS 框架。

## 当前范围（F012）

F012 只交付**前端基座**，不含任何产品页面：

- **前端骨架**：Vue 3 + TS + Vite + Element Plus；
- **API client 基座**：统一请求封装（`src/api/http.ts`）+ 统一错误解析，消费方按
  `error.code` 分支渲染，**不解析 `error.message` 文案**（`message` 仅用于展示）；
- **列表三态基座**：Loading / Empty / Error（`ListStates` + `ErrorState` +
  `useAsyncQuery`）。Empty（200 + `items` 为空）与 Not Found（404 `NOT_FOUND`）
  是**不同**状态；另预留 `UNAUTHENTICATED` / `FORBIDDEN` 渲染分支（F013 起才会触发）；
- **开发自检页**（`/`，仅 dev 构建渲染，生产构建渲染占位说明）：调用非产品端点
  `GET /_foundation/clusters`（列表，含 Loading / Empty）与
  `GET /_foundation/error`（确定性 500 `INTERNAL_ERROR`，驱动 Error 态），
  仅用于验证基座。

> ⚠️ **`/_foundation/*` 是非产品自检面**（`docs/api/f012-project-foundation.md` §4）：
> 仅在 dev/test 配置下由后端挂载，生产环境不可达；`clusters` 仅作基座验证载体，
> 不含任何领域规则。自检页已明确标注为 dev 用途，**不构成产品功能**。
> F001 交付产品 Cluster API（`/api/clusters`）后，该自检面将移除或降级为测试夹具。
> 产品页面自 F001 起交付。

## 环境要求

- Node.js `^20.19.0 || >=22.12.0`（Vite 7 的要求）
- npm（随 Node 附带）

## 快速开始

```bash
cd frontend
npm install
npm run dev
```

dev server 默认把 `/api` 与 `/_foundation` 反向代理到 `http://127.0.0.1:8000`。
后端地址不同时，用环境变量覆盖即可（**无需任何 `.env` 文件**）：

```bash
CSM_DEV_API_TARGET=http://127.0.0.1:9000 npm run dev
```

后端未启动时，自检页的列表区会渲染 Error 态（无法连接服务器 / 未知错误），
属预期行为——本前端不使用任何 Mock 数据伪装成功。

## 常用脚本

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 启动 dev server（含 API 反向代理） |
| `npm run build` | 类型检查（`vue-tsc`）+ 生产构建，产物输出到 `dist/` |
| `npm run typecheck` | 仅类型检查 |
| `npm run test` | 运行单元测试（vitest，一次性） |
| `npm run test:watch` | 以 watch 模式运行测试 |

## 目录结构

```text
frontend/
├── src/
│   ├── api/
│   │   ├── http.ts              # 统一请求封装 + ApiError 归一化（基座）
│   │   └── foundation.ts        # /_foundation/* 非产品自检面客户端（契约 §4）
│   ├── components/
│   │   ├── ErrorState.vue       # 按 error.code 分支渲染的错误态（基座）
│   │   └── ListStates.vue       # 列表 Loading / Error / Empty / 内容容器（基座）
│   ├── composables/
│   │   └── useAsyncQuery.ts     # 异步查询三态管理 + 竞态防护（基座）
│   ├── pages/
│   │   └── DevSelfCheckPage.vue # dev 自检页（非产品；仅 dev 构建渲染）
│   ├── types/
│   │   └── api.ts               # 契约类型（错误信封 / 分页信封 / 错误码）
│   ├── App.vue
│   ├── main.ts
│   └── assets/main.css
├── tests/                       # vitest 单元测试
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 实现约定

- API 契约唯一权威来源是 `docs/api/`，代码中不得另立约定；
- 所有 HTTP 调用集中在 `src/api/`，页面组件不得直接 `fetch`；
- 状态渲染只依赖 `error.code`（及 `error.details` 的字段级信息），
  `error.message` 仅作为补充文案展示，不参与任何分支判断；
- Empty（请求成功但无数据）与 Not Found（404）必须渲染为不同状态
  （`api-conventions.md` §7 / R-QUERY-004）。
