# F017 前端 UI 体系改造（Ant Design + Tailwind CSS）— IMPLEMENTATION 阶段报告

- **Task**：F017（FEATURE，P0，M8）— Frontend 实现（P0 骨架由协调器执行，页面/组件逐文件由 frontend 角色执行，见 §5 执行说明）。
- **Status**：`FRONTEND COMPLETE`
- **Basis**：
  - `docs/features/F017/product.md`（PRODUCT COMPLETE，F-UI-1..7）。
  - `docs/features/F017/architecture.md`（CONTRACT `READY FOR IMPLEMENTATION`；D04 定稿、§2 文件清单与硬边界、§3 迁移策略）。
  - `docs/architecture/d04-frontend-ui-stack.md` v2 FINAL / CONFIRMED。
  - `docs/database/f017-frontend-ui.md`（Database NOT_REQUIRED）。
  - `docs/features/F017/test-report.md#test-design`（TD-1）。
  - `docs/project/project-plan.yaml` plan_revision 5；`docs/project/implementation-rules.md`。
- **分支**：`feature/F017-frontend-ui-antd-tailwind`，base `v3`，`start_commit` `67770639067bd7fe11bf633de4ff7b9c31e42c5e`。

## 1. 交付范围

在保持业务行为、API 契约、后端/数据库/部署不变的前提下，将前端展示层迁移到 **Ant Design 5.29.3 + Tailwind CSS 4.3.3（`@tailwindcss/vite`）**：

| 类别 | 文件 |
| --- | --- |
| 依赖/配置 | `frontend/package.json`、`frontend/package-lock.json`、`frontend/vite.config.ts` |
| 入口/样式 | `frontend/src/main.tsx`、`frontend/src/index.css` |
| 应用壳 | `frontend/src/App.tsx`、`frontend/src/pages/HomePage.tsx`、`frontend/src/pages/LoginPage.tsx` |
| 页面（14） | `LoginPage`、`HomePage`、`ClustersPage`、`ClusterCreatePage`、`ClusterDetailPage`、`ResourcesPage`、`ResourceCreatePage`、`ResourceDetailPage`、`NetworksPage`、`IpPoolsPage`、`IpAddressesPage`、`ServicesPage`、`AuditPage`、`SystemPage` |
| 组件 .tsx（19） | `AccountManagementPanel`、`AuditQueryPanel`、`ClusterForm`、`DashboardPanel`、`DeletedObjectsPanel`、`GlobalSearch`、`HealthPanel`、`InterfaceForm`、`InterfacesPanel`、`IpAddressForm`、`IpPoolForm`、`NetworkForm`、`ResourceForm`、`ResourceImportPanel`、`ServiceEndpointForm`、`ServiceEndpointsPanel`、`ServiceForm`、`ServicesPanel`、`VirtualMachineFields` |

## 2. 关键实现

- **入口装配**（`main.tsx`）：`StyleProvider`（`@ant-design/cssinjs`）→ `ConfigProvider`（`locale=zh_CN`，seed token `colorPrimary #2563eb` / `borderRadius 6` / 系统字体栈）→ antd `App` → 应用 `App`。不引入 `antd/dist/reset.css`。
- **层序**（`index.css` 定稿）：`@layer theme, base, antd, components, utilities;` + `tailwindcss/theme.css`、`preflight.css`、`utilities.css` 分片导入 + `@theme` 共享令牌 + 最小全局层（`:root` 字体/背景、`html/body/#root` 高度、`body margin`）。迁移期使用的 `@layer legacy` 已删除。
- **迁移模式**：`section.panel`→`Card`；`table.data-table`→`Table`；原生表单控件→`Form`/`Input`/`Input.TextArea`/`Select`/`InputNumber`/`Checkbox`；按钮→`Button`；徽标→`Tag`；四态→`Spin`/`Alert`/`Empty`/`Table`；行内二次确认→`Modal`（保留失败不自动关闭、错误与引用/冲突明细、版本冲突刷新）；列表分页/排序/过滤与查询参数名逐一致。

## 3. 硬边界核对（F-UI-4d / F-UI-7）

相对 `start_commit`：

| 边界 | 结论 |
| --- | --- |
| `frontend/src/api/*.ts`（16） | 零改动 |
| 纯逻辑 `frontend/src/components/*.ts`（11） | 零改动；无 `antd`/`react`/CSS import |
| `frontend/scripts/smoke-client.mjs` | 零改动 |
| `frontend/Dockerfile`、`frontend/nginx.conf`、`compose.yaml`、`compose.test.yaml`、`deploy/**` | 零改动 |
| `backend/**`、`docs/database/**`、`docs/api/**` | 零改动 |

## 4. 本地验证（实际执行）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 类型 | `npm run typecheck` | PASS（0 错误） |
| 构建 | `npm run build` | PASS；`dist/assets/index-*.css` 非空（约 15.75 kB，含 `@layer theme/base/antd,components/utilities`） |
| 纯逻辑回归 | `npm run smoke:client` | PASS：**264 passed, 0 failed** |
| 依赖 | `npm ls @ant-design/cssinjs` | 单一 `1.24.0`（与 antd 5.29.3 内部一致，R9 已消除） |
| dist 产物 | `find dist -name '*.css' -size +0c` | 命中 |

> **smoke 基线更正**：TD-1 记录基线为 265，实测脚本 `await test(` 计数与实际运行均为 **264**。以 264 为准；用例数未减少（脚本零改动）。

## 5. 执行说明（环境偏差，如实记录）

- frontend 角色（`local/GLM-5.3:high`）在较长任务上反复超时；P0 依赖安装与骨架（`package.json`、`vite.config.ts`、`main.tsx`、`index.css`）由协调器执行，`HomePage.tsx` 由协调器迁移，其余页面/组件由 frontend 角色逐文件迁移。
- 该偏差不改变设计或业务规则；实现与后续 Review 仍由独立角色复核。

## 6. 与设计的偏差（记录，不改变业务规则）

1. **`StyleProvider` 的 `layer` 为 boolean**：`@ant-design/cssinjs` 1.24 的 `layer` 是 boolean，默认层名 `antd`；代码使用 `<StyleProvider layer>`。architecture.md / D04 中的 `layer="antd"` 为意图描述，实际 API 以 boolean 呈现，效果一致（AntD 样式进入 `@layer antd`）。
2. **Tailwind v4 令牌 tree-shake**：未被 utility 引用的 `@theme` 令牌（`--color-brand`、`--radius-card`）不进入构建产物，`--font-sans` 因被 `:root` 引用而保留。共享令牌仍由 `main.tsx` seed token 承载；不影响 F-UI-1..7。
3. **ClustersPage 列序修正**：迁移中按 `dataIndex` 对齐了原本错位的表体单元格与表头（`version`/`created_at`/`updated_at`）；属展示正确性修正，不改变数据或请求语义，Review 需关注。
4. 个别组件的旧语义色（如 `.unset` 灰）在迁移中采用近似 Tailwind 色（如 amber）；视觉细节由 F018 复核。

## 7. 未验证 / 交 F018

- AntD 运行时 CSS-in-JS 的真实渲染、layer 优先序、preflight 实际布局影响（V6）。
- 权限门控、四态、401/403/409/422 界面呈现、Audit 无变更入口、列表交互真实触发（V5）。
- Nginx 入口可达性与 SPA fallback（V7）。
- `npm ci` 干净安装可复现性（依赖源可达性）。

## 8. Git 声明

实现期间对 `feature/F017-frontend-ui-antd-tailwind` 的提交见协调器记录；本报告未执行 Git 命令。

```text
GIT: NONE
```