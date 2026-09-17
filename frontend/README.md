# CSM Frontend

CSM Web 前端。

技术栈（ADR-0001，`ACCEPTED`）：**Vue 3 + TypeScript + Vite + Element Plus**。除该技术栈外未引入其他状态管理 / UI / CSS 框架，也**未引入 `vue-router`**——页面切换由 `App.vue` 内的极简视图状态完成，多资源导航出现前再决策路由方案。

## 已交付范围

前端按 Feature 增量交付，每个 Feature 的范围以其产品 / 架构 Handoff 与 `docs/api/` 契约为准。**API 契约唯一权威来源是 `docs/api/`，代码中不得另立约定。**

| Feature | 交付内容 | 契约 |
| --- | --- | --- |
| **F012 / F001** | 三态基座（`ListStates` / `ErrorState` / `useAsyncQuery`）；Cluster 列表页与详情页骨架（`404` 独立于 Empty） | `docs/api/f001-cluster.md` |
| **F013** | 认证 API 客户端、登录页、`App.vue` 会话门控（`bootstrap → login → app`）、全局 401 处理 | `docs/api/f013-auth.md` |
| **F014** | 删除流程基座（`useResourceDelete`）与 Cluster 删除入口（列表 / 详情、二次确认、`409` 冲突提示） | `docs/api/f014-soft-delete.md` |
| **F002** | BareMetal API 客户端、列表 / 详情 / 登记 / 状态维护 / 删除；从 Cluster 详情进入「集群限定」列表 | `docs/api/f002-bare-metal.md` |
| **F009** | Cluster 视角成员视图（复用 F002 的集群限定列表，无新增前端实现）；按名称寻址的只读别名仅由后端提供 | `docs/api/f009-cluster-resource-view.md` |
| **F006** | VirtualMachine API 客户端、列表 / 详情 / 登记 / 可选字段维护 / 删除；从 BareMetal 详情进入「该宿主虚拟机」 | `docs/api/f006-virtual-machine.md` |
| **F004** | NetworkInterface API 客户端、列表 / 详情 / 登记 / 技术类型与用途维护 / 删除；从 BareMetal 详情进入「该宿主网络接口」 | `docs/api/f004-network-interface.md` |
| **F005** | IPAddress API 客户端、列表 / 详情 / 登记 / 修正 / 删除；从 NetworkInterface 详情进入「该网络接口 IP」 | `docs/api/f005-ip-address.md` |
| **F007** | Container API 客户端、列表（载体筛选：`carrier_type` + `carrier_id` 成对）/ 详情 / 登记（载体类型选择器 + 载体 ID 输入）/ 可选字段维护 / 删除；详情页登记成功后跳转新容器详情 | `docs/api/f007-container.md` |

**跨 Feature 的渲染约定**（全部页面一致）：

- **Loading / Empty / Error 三态互不相同**；Empty（`200` + `items` 为空）与 Not Found（`404`）必须渲染为**不同**状态（`api-conventions.md` §7 / R-QUERY-004）；
- 错误分支只依赖 `error.code`（必要时 `details[].code` / `details[].field`），`error.message` 仅作补充展示、**不参与任何分支判断**；
- 删除 / 维护失败：`409` 保留内容并渲染冲突提示，`404` 与成功同构（资源已不在活跃集合 → 刷新视图），`401` 交由全局会话失效处理；
- **领域校验全部在服务端**（§21）：唯一性、父资源存在性与活跃性、删除守卫、枚举合法性均由后端裁决，前端不预判、不禁用、不隐藏入口；
- **未定义约束不做任何变换**：`name` / `hostname` 等字段不做长度 / trim / 归一化 / 空串校验，也不基于 `undefined_constraints` 编写业务分支；
- 所有 HTTP 调用集中在 `src/api/`，页面组件不得直接 `fetch`。

**当前未交付**（属后续 Feature）：Service（F008）、资源详情与关联查询聚合视图（F010）、Excel 批量导入（F011）的 UI；恢复 / 回收站 / 已删资源查看 / 批量操作 / 审计展示 / 导出 / 高级筛选；账号管理页与口令修改。

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
│   │   ├── auth.ts               # 认证 API 客户端（f013-auth.md）
│   │   ├── bareMetals.ts         # BareMetal API 客户端（f002-bare-metal.md）
│   │   ├── clusters.ts           # Cluster API 客户端（f001-cluster.md / f014-soft-delete.md）
│   │   ├── containers.ts         # Container API 客户端（f007-container.md）
│   │   ├── http.ts               # 统一请求封装 + ApiError 归一化 + 全局 401 处理（基座）
│   │   ├── ipAddresses.ts        # IPAddress API 客户端（f005-ip-address.md）
│   │   ├── networkInterfaces.ts  # NetworkInterface API 客户端（f004-network-interface.md）
│   │   └── virtualMachines.ts    # VirtualMachine API 客户端（f006-virtual-machine.md）
│   ├── components/
│   │   ├── ErrorState.vue        # 按 error.code 分支渲染的错误态（基座）
│   │   ├── ListStates.vue        # 列表 Loading / Error / Empty / 内容容器（基座）
│   │   ├── BareMetalFormDialog.vue
│   │   ├── BareMetalStatusTag.vue
│   │   ├── ContainerFormDialog.vue
│   │   ├── IpAddressFormDialog.vue
│   │   ├── NetworkInterfaceFormDialog.vue
│   │   └── VirtualMachineFormDialog.vue
│   ├── composables/
│   │   ├── useAsyncQuery.ts      # 异步查询三态管理 + 竞态防护（基座）
│   │   ├── useResourceDelete.ts   # 删除流程共享基座（二次确认 / 防重复 / 404 同构 / 401 全局 / 错误按 code）
│   │   ├── useClusterDelete.ts
│   │   ├── useBareMetalDelete.ts
│   │   ├── useVirtualMachineDelete.ts
│   │   ├── useNetworkInterfaceDelete.ts
│   │   ├── useIpAddressDelete.ts
│   │   └── useContainerDelete.ts
│   ├── pages/
│   │   ├── LoginPage.vue
│   │   ├── ClusterListPage.vue / ClusterDetailPage.vue
│   │   ├── BareMetalListPage.vue / BareMetalDetailPage.vue
│   │   ├── VirtualMachineListPage.vue / VirtualMachineDetailPage.vue
│   │   ├── NetworkInterfaceListPage.vue / NetworkInterfaceDetailPage.vue
│   │   ├── IpAddressListPage.vue / IpAddressDetailPage.vue
│   │   └── ContainerListPage.vue / ContainerDetailPage.vue
│   ├── types/
│   │   └── api.ts                # 契约类型（错误信封 / 分页信封 / 错误码）
│   ├── App.vue                   # 会话门控 + 极简视图状态（bootstrap / login / app）
│   ├── main.ts
│   └── assets/main.css
├── tests/                        # vitest 单元测试（含 setup/）
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
- 领域校验（唯一性、父资源活跃性、删除守卫、枚举合法性）全部在服务端，前端不重复实现业务规则，
  也不对 `name` 等字段做长度 / trim / 归一化等任何变换（`undefined_constraints`）。

## 测试环境备注

以下 `vite.config.ts` 配置都是**测试基础设施**，不影响浏览器构建，且均已附带原因注释：

- **`element-plus` 内联**（`test.server.deps.inline`）：其 CJS 依赖 `async-validator`
  在 vitest 外部化加载时默认导入解析错误，会导致 `el-form` 校验在测试中静默失效。
- **`maxWorkers: 4` / `fsModuleCache: true`**：限制并发 worker 数并持久化模块转换缓存，
  降低多 worker 同时内联转换 `element-plus` 时的时序抖动。
- **`testTimeout: 20000`** 与 spec 内的 `waitForUi`（10s）：仅放宽**时序上限**，
  **不改变任何断言语义**。
- **`tests/setup/monotonic-date-now.ts`**：在测试进程内把 `Date.now()` 单调化（时钟正常时为恒等操作）。
  宿主机 NTP 校时会让系统时钟周期性**向后跳变**，而 Vue 的事件调用器会丢弃时间戳早于自身的
  事件（`e._vts <= invoker.attached`），导致 `trigger()` 的点击被静默吞掉、测试随机超时。
  单调化后这一比较恢复「健康机器」语义；**它不改变产品代码，也不会让错误实现通过**——
  被丢弃的点击发生在业务 handler 之前。若在未来环境或 vitest 版本下不再需要，可移除本文件与注册项，并
  预期测试仍稳定。
