# CSM Frontend

CSM Web 前端。

技术栈（ADR-0001，`ACCEPTED`）：**Vue 3 + TypeScript + Vite + Element Plus**。除该技术栈外未引入其他状态管理 / UI / CSS 框架。

## 当前范围（F001）

F001 交付 **Cluster 登记与管理** 的前端部分（契约：`docs/api/f001-cluster.md`，`READY`）：

- **Cluster API 客户端**（`src/api/clusters.ts`）：5 个端点（`POST /api/clusters`、
  `GET /api/clusters`、`GET /api/clusters/{id}`、`GET /api/clusters/by-name/{name}`、
  `PATCH /api/clusters/{id}`），复用统一请求封装 `src/api/http.ts`，不新建请求层；
  类型 `ClusterRead` 字段集合封闭（`id` / `name` / `created_at` / `updated_at`），
  时间字段按不透明字符串展示 / 传递；
- **集群列表页**（`ClusterListPage`）：展示 4 个字段与分页（`page` / `page_size`）；
  **Loading / Empty / Error 三态互不相同**（Empty = `200` + `items` 为空；
  Error 按 `error.code` 分支渲染，**不解析 `message`**）；
- **集群详情页骨架**（`ClusterDetailPage`）：仅呈现 Cluster 自身字段；
  `404 NOT_FOUND` 渲染为独立的「资源不存在或已被删除」态，与列表 Empty 是
  **不同**状态（R-QUERY-004 / `api-conventions.md` §7）；
- **三态基座**（`ListStates` / `ErrorState` / `useAsyncQuery`）：自 F012 保留为
  可复用基座，由产品页面与其测试使用；F012 判据 6 的验证力由 Cluster 列表页
  三态测试承载；
- 页面切换由 `App.vue` 内的极简视图状态完成（**不引入 `vue-router`**，
  多资源导航出现前再决策路由方案）。

> F012 的非产品自检面 `/_foundation/*` 已于 F001 彻底移除：dev 自检页与
> `src/api/foundation.ts` 已删除，Vite dev proxy 仅保留 `/api`。

F001 前端**不包含**：登记 / 改名表单（PROPOSED，不构成 AC；API 客户端已就绪）、
Cluster 删除入口（F014）、BareMetal 相关内容（F002+）。

## 当前范围（F013）

F013 交付**本地账号认证与会话**的前端部分（契约：`docs/api/f013-auth.md`，
`READY`）：

- **认证 API 客户端**（`src/api/auth.ts`）：`login` / `logout` /
  `getCurrentSession`，类型 `AuthenticatedUser`（`id` / `username`，字段集合
  封闭），复用 `src/api/http.ts`，不新建请求层；会话 Cookie（`csm_session`，
  `HttpOnly`）由浏览器管理，前端不读不写任何令牌；`login` 与启动期
  `getCurrentSession` 抑制全局 401 跳转，由请求方自行处理 401 语义；
- **全局 401 处理**（`src/api/http.ts`）：`setUnauthenticatedHandler(handler)`，
  未抑制的请求收到 `error.code === 'UNAUTHENTICATED'` 时调用（典型：会话过期
  后的资源请求 → 切回登录页）；仍不解析 `message`；
- **登录页**（`LoginPage`）：`username` + `password` 仅必填校验（R-AUTH-004
  不属登录路径）；默认 / 提交 Loading（禁重复提交）/ 失败提示（401 → 停留
  + 固定提示，按 `error.code` 分支，不区分失败原因，R-AUTH-006）三态互不相同；
- **App 会话门控**（`App.vue`）：视图状态 `bootstrap → login → app`（仍不引入
  `vue-router`）；挂载时 `getCurrentSession()`；全局 401 → 切回登录页并清除当前
  视图状态；登出按钮把 `204` 与 `401` 归一为同一处理（契约 §5.2）。

F013 前端**不包含**：注册页 / 注册表单、账号管理页、口令修改 / 找回、路由库。

## 环境要求

- Node.js `^20.19.0 || >=22.12.0`（Vite 7 的要求）
- npm（随 Node 附带）

## 快速开始

```bash
cd frontend
npm install
npm run dev
```

dev server 默认把 `/api` 反向代理到 `http://127.0.0.1:8000`。后端地址不同时，
用环境变量覆盖即可（**无需任何 `.env` 文件**）：

```bash
CSM_DEV_API_TARGET=http://127.0.0.1:9000 npm run dev
```

后端未启动时，列表页会渲染 Error 态（无法连接服务器），属预期行为——
本前端不使用任何 Mock 数据伪装成功。

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
│   │   ├── auth.ts               # 认证 API 客户端（契约 f013-auth.md）
│   │   ├── clusters.ts           # Cluster 产品 API 客户端（契约 f001-cluster.md）
│   │   └── http.ts               # 统一请求封装 + ApiError 归一化 + 全局 401 处理（基座）
│   ├── components/
│   │   ├── ErrorState.vue        # 按 error.code 分支渲染的错误态（基座）
│   │   └── ListStates.vue        # 列表 Loading / Error / Empty / 内容容器（基座）
│   ├── composables/
│   │   └── useAsyncQuery.ts      # 异步查询三态管理 + 竞态防护（基座）
│   ├── pages/
│   │   ├── ClusterDetailPage.vue # 集群详情页（骨架，404 态独立于 Empty）
│   │   ├── ClusterListPage.vue   # 集群列表页（产品页，三态 + 分页）
│   │   └── LoginPage.vue         # 登录页（三态 + 仅必填校验）
│   ├── types/
│   │   └── api.ts                # 契约类型（错误信封 / 分页信封 / 错误码）
│   ├── App.vue                   # 会话门控 + 极简视图状态：bootstrap / login / app
│   ├── main.ts
│   └── assets/main.css
├── tests/                        # vitest 单元测试
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
  （`api-conventions.md` §7 / R-QUERY-004）；
- 领域校验（`/` 禁令、活跃唯一性）全部在服务端，前端不重复实现业务规则，
  也不对 `name` 做长度 / trim / 归一化等任何变换（`undefined_constraints`）；
- 测试环境备注：`vite.config.ts` 中将 `element-plus` 内联（
  `test.server.deps.inline`），因其 CJS 依赖 `async-validator` 在 vitest
  外部化加载时默认导入解析错误，会导致 `el-form` 校验在测试中静默失效；
  浏览器构建不受影响。
