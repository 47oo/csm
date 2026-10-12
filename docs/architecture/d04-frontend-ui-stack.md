# D04 前端 UI 技术栈 — Ant Design + Tailwind CSS 专业设计输入

- **状态**：PROPOSED（专业设计输入；最终签核在 F017 CONTRACT Gate）
- **版本**：v1
- **起草**：Architect，2026-10-12（轻量全局评估结论落稿）
- **依据**：`docs/product/requirements-v3.md` revision 4 §28 / §29（用户明确要求引入 Ant Design 与 Tailwind CSS）；`AGENTS.md` §2.9（软件版本与普通设计由专业角色签核）；`docs/project/change-control.md` §1、§4；`docs/architecture/d01-conventions.md` v11。
- **覆盖**：F017 前端 UI 体系改造及其 F018 验收复验。**本文件在产品正文被批准且 F017 CONTRACT 定稿前为 PROPOSED，不构成实现依据。**

## 1. 背景与范围

V3 一期 F001–F016 前端为 React 18.3 + TypeScript 5.6 + Vite 5.4，使用约 758 行手写全局 `frontend/src/index.css`，无 UI 组件库。用户明确要求改用 Ant Design 组件库与 Tailwind CSS 样式方案（§29 revision 4）。本变更属展示层技术选型，不改变业务对象、关系、状态、唯一性、生命周期与 API 约定。

## 2. 决策（PROPOSED，单一推荐）

| ID | 决策 | 说明 / 拒绝项 |
| --- | --- | --- |
| D04-1 | UI 库采用 **Ant Design 5.x**（`antd`，锁文件固定补丁） | React 18.3 兼容；v5 运行时 CSS-in-JS，选择器以 `:where()` 降低特异性，便于与 Tailwind 协作。拒绝 antd 6：偏离保守基线，升级走后续变更控制。 |
| D04-2 | 样式库采用 **Tailwind CSS 4.x**（`tailwindcss` + `@tailwindcss/vite`，CSS-first） | 原生 cascade layer，层序确定；无需 PostCSS/autoprefixer；`@tailwindcss/vite` 支持 Vite ^5.2（现 5.4.9）。拒绝 v3：须关闭 preflight 规避与 AntD reset 的冲突，会破坏依赖 preflight 的边框等样式。 |
| D04-3 | 维持 **React 18.3.x / TS 5.x / Vite 5.x**，不升级 React 19 / Vite 6 / antd 6 | §29 已确认选型；本次不夹带框架升级。 |
| D04-4 | Vite 插件路线：`vite.config.ts` 增加 `@tailwindcss/vite`，不引入 PostCSS 配置 | 与既有 `@vitejs/plugin-react` 并列；AntD 无需构建期插件。 |
| D04-5 | 入口 CSS 保留 `src/index.css`，显式声明 layer 顺序并导入 Tailwind；AntD 根装配 `ConfigProvider` + `App`，外层 `StyleProvider layer="antd"` | 不额外 `import "antd/dist/reset.css"`，以 Tailwind preflight 作为唯一 base reset，避免双重 reset。 |
| D04-6 | 主题分工：AntD 组件主题唯一权威为 `ConfigProvider theme`（seed token）；Tailwind 设计令牌为 `@theme {}`；仅维护最小共享集（品牌色 / 圆角 / 字体栈），不做运行时同步 | 避免无收益耦合。 |
| D04-7 | `index.css` 收敛为最小全局层（不整体移除）：字体栈、`html/body/#root` 高度与背景及极少数真正跨页规则 | 旧组件样式随页面迁移删除；迁移未完成前保留旧层避免样式缺口（风险 R5）。 |
| D04-8 | 不新增 DOM 测试框架；保留 `smoke:client` 并须原样通过；UI 正确性由 F018 在真实 Compose 手动复验 | AntD v5 运行时注入样式，构建产物不含组件 CSS；不得以构建通过声称 UI 正确。 |

### 2.1 layer 顺序（D04-5）

```css
@layer theme, base, antd, components, utilities;
@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/preflight.css" layer(base);
@import "tailwindcss/utilities.css" layer(utilities);
```

配合 `StyleProvider layer="antd"`，得到确定性优先序：Tailwind reset(base) → AntD 组件样式(antd) → Tailwind utilities(utilities)。

## 3. 影响评估

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 模块边界 | 局部，受约束 | 仅改 `frontend/src/pages/`、`frontend/src/components/*.tsx`、根装配与样式入口。硬边界：`frontend/src/api/` 与纯逻辑 `*.ts` 不得引入 React/CSS/AntD，否则破坏 `smoke:client`。 |
| 后端 / 数据库 / 事务 | 无影响 | 无后端文件、无 Schema / Migration / 约束变更。 |
| API 约定 | 无影响 | 无 Contract 字段 / 端点 / 错误语义变化。 |
| 部署（§30） | 无影响 | 仍为多阶段构建 → `nginx:alpine` 静态服务；`Dockerfile`、`nginx.conf`、入口代理不变；仅 `dist` 体积增大（R3）。 |
| 验收（§31/§32） | 行为不变、需复验 | 业务能力与验收项不变；F018 复验界面回归并更新 `project.acceptance`。 |

## 4. 验证策略

| # | 验证项 | 方法 | 判据 |
| --- | --- | --- | --- |
| V1 | 类型与构建 | `npm run typecheck`、`npm run build` | 通过；`dist` 含非空 CSS |
| V2 | 纯逻辑回归 | `npm run smoke:client` | 全部原有用例 PASS，脚本零改动 |
| V3 | 依赖解析 | 干净 `npm ci`（依赖源可达） | 锁文件与依赖一致，构建可复现 |
| V4 | layer 优先序 | 手工抽查 Tailwind utility 覆盖 AntD、preflight 未破坏布局 | 符合 §2.1 |
| V5 | 真实部署回归 | 干净环境 `docker compose up -d` 经 Nginx 入口 | 前端可达、SPA fallback 正常 |
| V6 | 业务验收复验（F018） | 真实 Compose 按 §31 适用用例 / §32 C1–C15 复验界面 | 无回归；未执行项显式标注 |

## 5. 风险

| ID | 风险 | 等级 | 缓解 |
| --- | --- | --- | --- |
| R1 | 依赖源不可达 / CI 无 npm 镜像 | MEDIUM | 提交 `package-lock.json`；配置镜像；离线不可执行时明确标注未验证 |
| R2 | preflight 与 AntD CSS-in-JS / reset 冲突 | MEDIUM | §2.1 layer 顺序 + `StyleProvider layer="antd"`；不引 AntD reset；V4 抽查 |
| R3 | 包体积 / 首屏增长 | LOW–MEDIUM | AntD v5 ESM tree-shake；§32 无性能验收项，仅记录不阻塞 |
| R4 | 版本漂移 | LOW | 锁文件固定；升级走变更控制 |
| R5 | `index.css` 收缩与页面迁移不同步 | MEDIUM | 同 Feature 内完成全量迁移；未完成前保留旧层；F018 复验 |
| R6 | 纯逻辑模块误引入 React/CSS | MEDIUM | 明确模块边界；V2 守门回归 |
| R7 | 夹带框架升级 | LOW | 明确本次不升级；越界返回变更控制 |

**Rollback**：无 DB Migration、无数据与 API 变化。回滚只需撤销 F017 提交（或还原分支 / 镜像）并重部署上一 `dist`，不涉及数据恢复。F018 复验在回滚前不置 PASS。

## 6. Implementation Layers 与 Contract

- `layers.database = false`、`layers.backend = false`、`layers.frontend = true`
- `api_required = false` → Contract 状态 `NOT_REQUIRED`（无业务 API / 字段 / 错误语义变更；前端仅消费既有 READY Contract）。无 API 仍须在 F017 CONTRACT 记录最终设计签核。

## 7. 待办与定稿

- 本文件由 F017 ARCHITECTURE 阶段定稿（可修订 D04-1–D04-8），F017 CONTRACT 记录最终设计签核。
- F018 承接 V5–V6 复验并更新 `project.acceptance`。
- 软件次版本升级、React/Vite 升级、antd 6 / Tailwind 5 迁移均须重新走变更控制。