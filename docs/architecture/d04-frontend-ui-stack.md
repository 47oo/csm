# D04 前端 UI 技术栈 — Ant Design + Tailwind CSS 专业设计输入

- **状态**：CONFIRMED（Architect 专业设计签核；F017 CONTRACT 载体）
- **版本**：v2 FINAL（v1 PROPOSED 2026-10-12）
- **签核**：Architect，2026-10-15
- **依据**：`docs/product/requirements-v3.md` revision 4 §28 / §29（用户明确要求引入 Ant Design 与 Tailwind CSS，并记录为 CONFIRMED）；`AGENTS.md` §2.9（软件版本与普通设计由专业角色签核）；`docs/project/change-control.md` §1、§4；`docs/project/project-plan.yaml` plan_revision 5（用户 2026-10-12 批准）；`docs/architecture/d01-conventions.md` v11。
- **覆盖**：F017 前端 UI 体系改造及其 F018 验收复验。D04 各项由 F017 设计与 CONTRACT 定稿记录；无新增业务规则或重大架构变化，无需用户重复批准。

## 1. 背景与范围

V3 一期 F001–F016 前端为 React 18.3 + TypeScript 5.6 + Vite 5.4，使用约 758 行手写全局 `frontend/src/index.css`，无 UI 组件库。用户明确要求改用 Ant Design 组件库与 Tailwind CSS 样式方案（§29 revision 4）。本变更属展示层技术选型，不改变业务对象、关系、状态、唯一性、生命周期与 API 约定。详细设计见 `docs/features/F017/architecture.md` §1。

## 2. 决策（CONFIRMED）

| ID | 决策 | 说明 / 拒绝项 |
| --- | --- | --- |
| D04-1 | UI 库采用 **Ant Design 5.x**（`antd`，补丁版本由 `package-lock.json` 固定） | React 18.3 兼容；v5 运行时 CSS-in-JS，选择器以 `:where()` 降低特异性，便于与 Tailwind 协作。拒绝 antd 6：偏离保守基线，升级走后续变更控制。 |
| D04-2 | 样式库采用 **Tailwind CSS 4.x**（`tailwindcss` + `@tailwindcss/vite`，CSS-first） | 原生 cascade layer，层序确定；无需 PostCSS/autoprefixer；`@tailwindcss/vite` 支持 Vite ^5.2（现 5.4.9）。拒绝 v3：须关闭 preflight 规避与 AntD reset 的冲突，会破坏依赖 preflight 的边框等样式。 |
| D04-3 | 维持 **React 18.3.x / TS 5.6.x / Vite 5.4.x**，不升级 React 19 / Vite 6 / antd 6 / Tailwind 5 | §29 已确认选型；本次不夹带框架升级。 |
| D04-4 | Vite 插件路线：`vite.config.ts` 增加 `@tailwindcss/vite`，不引入 PostCSS 配置 | 与既有 `@vitejs/plugin-react` 并列；AntD 无需构建期插件。 |
| D04-5 | 入口 CSS 保留 `src/index.css`，显式声明 layer 顺序并分片导入 Tailwind；AntD 根装配 `StyleProvider layer="antd"`（`@ant-design/cssinjs` 直接依赖）+ `ConfigProvider` + `App` | 不额外 `import "antd/dist/reset.css"`，以 Tailwind preflight 作为唯一 base reset，避免双重 reset。`@ant-design/cssinjs` 提为直接依赖，避免隐式传递版本漂移。 |
| D04-6 | 主题分工：AntD 组件主题唯一权威为 `ConfigProvider theme`（seed token：`colorPrimary`/`borderRadius`/`fontFamily`）；Tailwind 设计令牌为 `@theme {}`；仅维护最小共享集（品牌色 / 圆角 / 字体栈），不做运行时同步 | 避免无收益耦合。 |
| D04-7 | `index.css` 分两态收敛：迁移期在最小全局层外将全部旧规则包进 `@layer legacy` 过渡层；全部迁移完成后删除 `@layer legacy`，仅保留最小全局层 | 未分层旧规则会反向覆盖 AntD / Tailwind utilities（R8），故必须包进 `@layer legacy`（位于 `base` 之后、`antd` 之前）。 |
| D04-8 | 不新增 DOM 测试框架；保留 `smoke:client` 并须原样通过；UI 正确性由 F018 在真实 Compose 手动复验 | AntD v5 运行时注入样式，构建产物不含组件 CSS；不得以构建通过声称 UI 正确。 |
| D04-9 | locale 采用 `antd/locale/zh_CN`，仅影响 AntD 内置文案 | 不改业务语义与自定义中文文案。 |
| D04-10 | 无 API / 无 Schema / 无部署变更；`layers={database:false,backend:false,frontend:true}`、`api_required=false` | 见 `docs/features/F017/architecture.md` §4。 |

### 2.1 layer 顺序（D04-5 / D04-7）

定稿（迁移完成）入口 CSS：

```css
@layer theme, base, legacy, antd, components, utilities;

@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/preflight.css" layer(base);
@import "tailwindcss/utilities.css" layer(utilities);
```

迁移期旧规则整体包进 `@layer legacy { ... }`（置于 `base` 之后、`antd` 之前），使未迁移页面仍有样式、且已迁移页面的 AntD/utilities 能覆盖旧规则。最终优先序：preflight(base) → legacy(迁移期旧样式) → antd(AntD CSS-in-JS) → utilities(Tailwind 原子类)。配合 `StyleProvider layer="antd"` 保证确定性。

## 3. 影响评估

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 模块边界 | 局部，受约束 | 仅改 `frontend/src/pages/`、`frontend/src/components/*.tsx`、根装配与样式入口。硬边界：`frontend/src/api/` 与纯逻辑 `*.ts` 不得引入 React/CSS/AntD，否则破坏 `smoke:client`。 |
| 后端 / 数据库 / 事务 | 无影响 | 无后端文件、无 Schema / Migration / 约束变更。 |
| API 约定 | 无影响 | 无 Contract 字段 / 端点 / 错误语义变化。 |
| 部署（§30） | 无影响 | 仍为多阶段构建 → `nginx:alpine` 静态服务；`Dockerfile`、`nginx.conf`、入口代理不变；仅 `dist` 体积增大（R3）。 |
| 验收（§31/§32） | 行为不变、需复验 | 业务能力与验收项不变；F018 复验界面回归并更新 `project.acceptance`。 |

## 4. 验证策略

详细 V1–V7 与 F-UI-1..7 映射见 `docs/features/F017/architecture.md` §5。要点：V1–V3 自动（依赖/构建/smoke）；V4 半自动（迁移完整性与样式收敛静态检查）；V5–V7 必须手动（真实渲染与部署可达性），未实际执行不得写 PASS。

## 5. 风险

| ID | 风险 | 等级 | 缓解 |
| --- | --- | --- | --- |
| R1 | 依赖源不可达 / CI 无 npm 镜像 | MEDIUM | 提交 `package-lock.json`；配置镜像；离线不可执行时明确标注未验证 |
| R2 | preflight 与 AntD CSS-in-JS / reset 冲突 | MEDIUM | §2.1 layer 顺序 + `StyleProvider layer="antd"`；不引 AntD reset；V6 抽查 |
| R3 | 包体积 / 首屏增长 | LOW–MEDIUM | AntD v5 ESM tree-shake；§32 无性能验收项，仅记录不阻塞 |
| R4 | 版本漂移 | LOW | 锁文件固定；升级走变更控制 |
| R5 | `index.css` 收缩与页面迁移不同步 | MEDIUM | 分两态收敛；未迁移前保留 `@layer legacy`；F018 复验 |
| R6 | 纯逻辑模块误引入 React/CSS | MEDIUM | 明确模块边界；V3 守门回归 |
| R7 | 夹带框架升级 | LOW | D04-3 明确本次不升级；越界返回变更控制 |
| R8 | 旧 `index.css` 保持未分层，覆盖 AntD/utilities | MEDIUM | 必须包进 `@layer legacy`（D04-7）；V4/V6 检查未分层旧规则 |
| R9 | `@ant-design/cssinjs` 与 `antd` 内部版本不匹配 | LOW–MEDIUM | 作为直接依赖并随 antd 同批锁定；`npm ci` + V6 渲染抽查 |
| R10 | 以构建通过声称 UI 正确 | MEDIUM | D04-8；运行时样式须真实渲染验证，未执行不写 PASS |
| R11 | preflight 使未迁移页面出现样式缺口 | LOW–MEDIUM | `@layer legacy` 兜底；V6 抽查发现即补 legacy，不回退层结构 |

**Rollback**：无 DB Migration、无数据与 API 变化。回滚只需撤销 F017 提交（或还原分支 / 镜像）并重部署上一 `dist`，不涉及数据恢复。F018 复验在回滚前不置 PASS。

## 6. Implementation Layers 与 Contract

- `layers.database = false`、`layers.backend = false`、`layers.frontend = true`
- `api_required = false` → Contract 状态 `NOT_REQUIRED`（无业务 API / 字段 / 错误语义变更；前端仅消费既有 READY Contract）。无 API 仍须在 F017 CONTRACT 记录最终设计签核（见 `docs/features/F017/architecture.md` §7.1）。

## 7. 签核与定稿

- 本文件 v2 FINAL 由 Architect 于 F017 设计 Gate 签核（2026-10-15），接收于 F017 CONTRACT。
- F018 承接 V5–V7 复验并更新 `project.acceptance`。
- 软件次版本升级、React/Vite 升级、antd 6 / Tailwind 5 迁移均须重新走变更控制。