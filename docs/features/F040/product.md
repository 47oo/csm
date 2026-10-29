# F040 前端依赖版本范围与架构升级策略对齐（R07）— PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-29）；ENABLER / P1 / M30 非功能改进；分支 `feature/F040-dependency-ranges`，交付线 `v3.4`，start_commit `adef87a43d9c73465c815fe85b2577d5dd17a1f2`；plan revision 25；requirements revision 16
- **角色产物**：product-manager 只读产出，协调器持久化
- **Basis**：用户 2026-10-29「批准并执行」并裁定 **AQ-6 = (i) 收敛依赖声明**（CONFIRMED；同批 AQ-5=A 使 R07 纳入本期、承载于 F040）；plan revision 25 F040（`kind: ENABLER`、`layers={database:false,backend:false,frontend:true}`、`api_required=false`、`depends_on: []`、`blocking_decisions: []`）；`docs/architecture/frontend-ui-stack.md` §1 选型 / §2 职责边界 / §4 升级策略（「Ant Design 仅在 6.6.x 兼容范围内升级，Tailwind CSS 仅在 4.3.x 兼容范围内升级」）；requirements revision 16 §28 / §29 / §3；CHG-015 §0/§1/§2/§3 R07/§4 AQ-6/§5/§8；来源 `/tmp/csm-review-2026-10-29.md` §R07；`frontend/package.json`；`frontend/package-lock.json`（解析结果 `antd 6.6.6`、`tailwindcss 4.3.3`、`@tailwindcss/vite 4.3.3`）

## 1. 性质：无产品规则变更（ENABLER）

| 维度 | 判定 |
| --- | --- |
| 问题事实 | `package.json` 的 `antd: ^6.6.6`、`tailwindcss: ^4.3.3`、`@tailwindcss/vite: ^4.3.3` 使用插入符范围（允许 6.7.x / 4.4.x），与 `frontend-ui-stack.md` §4「仅 6.6.x / 4.3.x 内常规升级」不一致；lockfile 已固定安装结果，故非运行故障 |
| 产品规则 | **零变更**（需求正文零 diff） |
| 业务行为 | **零变更**（页面/组件/交互/请求/权限/错误呈现/文案/视觉均不变） |
| 变更类型 | `ENABLER`：把实现对齐到**已批准的架构策略**，不是新需求 |
| 方向 | **收紧声明**，不是放宽策略（放宽为 `^` 属重大架构变更、须用户批准，本次不做） |
| 层级 | 依赖版本与范围属架构/实现层（需求 §29 已把「具体软件版本」授权 Architect 在确认边界内签核） |

## 2. 范围精确清单

允许变更（唯一 3 项）＋ lockfile 同步：

| 依赖 | 现状 | 目标（基线） |
| --- | --- | --- |
| `antd` | `^6.6.6` | `~6.6.6`（或精确 `6.6.6`，见 ON-1） |
| `tailwindcss` | `^4.3.3` | `~4.3.3`（或精确） |
| `@tailwindcss/vite` | `^4.3.3` | `~4.3.3`（或精确） |

明确不得变更：`react` / `react-dom` / `vite` / `typescript` / `@ant-design/icons` / `@vitejs/plugin-react` / `@types/react` / `@types/react-dom` 的范围与版本，以及 `scripts` / `name` / `version` / `private` / `type`。理由：无对应已批准策略依据，且会无故扩大回归面（plan revision 25 F040 `scope` 同此口径）。

## 3. 覆盖与不覆盖

覆盖：S1 三项声明范围收敛；S2 lockfile 同步（`npm ci` 可复现）；S3 与 `frontend-ui-stack.md` §1/§4 的逐项一致性核对记录（含 `npm ls` 输出，落 F040 `architecture.md`）。

不覆盖：N1 任何跨次/跨主版本升级；N2 新增/删除/替换依赖或 `overrides`/`resolutions`；N3 组件行为/页面/样式/文案/可访问性改动；N4 其它库范围；N5 修改 `frontend-ui-stack.md`；N6 后端与镜像依赖策略；N7 需求/领域/契约/Schema；N8 浏览器全页巡检（无交互改动；可重复交互入口归 F043）；N9 回填 F001–F039 历史证据。

## 4. 需求与领域影响

需求 revision 16 零变更；领域模型零变更；`frontend-ui-stack.md` 零 diff；`layers.database=false` / `backend=false` / `api_required=false` / `not_required.contract` 成立。F045 在 AQ-6=(i) 下把 F040 列入 `depends_on`；F040 的 typecheck/build/smoke 证据供 F045 引用。

## 5. 可观察验收标准（供 ARCHITECTURE / TEST DESIGN 承接）

| ID | 断言 |
| --- | --- |
| A1 | 三项范围已收敛（`~6.6.6` / `~4.3.3` / `~4.3.3` 或精确版本），三项形式一致且无 `^` 残留 |
| A2 | 三项与 `frontend-ui-stack.md` §1（6.6.x / 4.3.x）与 §4（仅次版本内升级）逐项一致；核对记录与 `npm ls antd tailwindcss @tailwindcss/vite` 原始输出入 `docs/features/F040/architecture.md` |
| A3 | `npm ci` 从干净 `node_modules` 成功（无 `ERESOLVE`、无 lockfile 不同步） |
| A4 | `npm ls` 显示实际安装仍为 `antd 6.6.6` / `tailwindcss 4.3.3` / `@tailwindcss/vite 4.3.3`；无跨次版本、无 `UNMET` / `invalid` / `extraneous` |
| A5 | `npm run typecheck`、`npm run build`、`npm run smoke:client` 全通过（smoke `0 failed`，通过项不少于基线 340；chunk 体积警告不属本 Feature 缺陷） |
| A6 | `package.json` 除 A1 三项外零 diff（依赖名集合与数量不变：`dependencies` 4 项、`devDependencies` 8 项；`scripts` 与元数据逐字不变） |
| A7 | 无新增/删除依赖；`package-lock.json` 中其它包的 `version` / `resolved` / `integrity` 不变 |
| A8 | 前端源码零 diff（`frontend/src/**`、`vite.config.ts`、`index.css`、`scripts/**`） |
| A9 | `frontend-ui-stack.md`、`docs/product/**`、`docs/api/**`、`docs/database/**`、`backend/**` 零 diff |
| A10 | 变更文件范围受控（`package.json`、`package-lock.json`、F040 报告、`docs/project/**`） |

不在验收范围：任何版本升级、浏览器交互/视觉验收、性能指标、F001–F039 历史证据回溯、变更集整体验收（归 F045）。

## 6. Blocking Questions

**无。** 目标由已批准架构策略 + 已裁定 AQ-6=(i) 完全确定；需求 §29 已授权 Architect 在确认边界内签核具体版本；不涉及业务规则/对象/状态/权限/可观察业务行为；范围分岔已由 AQ-6 裁定（(ii) 放宽、(iii) 记例外均不采纳）。

## 7. Non-blocking 观察

| ID | 观察 | 归属 |
| --- | --- | --- |
| ON-1 | `~` vs 精确版本的取舍：建议 `~`（阻止次版本越界并保留补丁升级），与 plan `acceptance` 措辞一致；若选精确版本须在 architecture 记录理由并同步 plan 措辞 | Architect |
| ON-2 | `npm ci` 与 lockfile 一致性验证形态（干净目录、npm 版本、是否允许 lockfile 元数据重写） | Tester |
| ON-3 | `@tailwindcss/vite` 与 `tailwindcss` 是否须等号绑定：架构文档只按 4.3.x 表述，未要求等号；建议维持 4.3.3 同步，但不新增同步义务 | Architect |
| ON-4 | `@ant-design/icons` 仍 `^6.3.4`：§4 未覆盖图标包，本次不收紧；若需覆盖须先扩写 §4（架构变更） | 用户 / Architect |
| ON-5 | `build` 的 chunk 体积警告与 R06 懒加载分属 F042（backlog，未启动）；本 Feature 不改变包体，不计为缺陷 | Architect / 协调器 |
| ON-6 | 浏览器专项依赖环境侧 Playwright、未入库；F040 无交互改动，不做浏览器验收（可重复入口归 F043），不得写成仓库保证 | Tester / 协调器 |

## 8. 后续文档更新

需求 / 领域模型 / `frontend-ui-stack.md` / `docs/api/**` / `docs/database/**` 均零变更；`docs/features/F040/architecture.md` 由 Architect 写入符合性核对记录与 `npm ls` 输出；plan 由协调器维护阶段结果与证据锚点。
