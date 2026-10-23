# F033 前端布局与 CSS 质量优化 — ARCHITECTURE 阶段报告

- **状态**：READY FOR DESIGN
- **版本**：v1
- **上游依据**：`docs/features/F033/product.md` v1（READY FOR ARCHITECT，A1–A11）；`docs/product/requirements-v3.md` revision 12 §28；`docs/architecture/frontend-ui-stack.md` §2/§3/§5；用户 2026-10-23 要求；plan revision 19。
- **layers**：`database=false`、`backend=false`、`frontend=true`；`api_required=false`；Contract `NOT_REQUIRED`。

## 1. 方案摘要

只调整呈现层：应用壳结构、语义 CSS token、容器宽度、页面标题层级、三处局部布局（搜索字段组 / 授权面板 / Dashboard 计数卡）。交互语义、请求参数、权限、错误与确认流程、服务端分页排序过滤保持不变。

| # | 现状根因 | 方案 |
| --- | --- | --- |
| R1 | `main` 全局 `max-width:720` 与 `.workspace-content:1600` 冲突 | 删除全局 main 宽度，显式 `.boot-main` / `.login-main` / `.workspace-content` |
| R2 | header 的「工作空间/当前页」与 h1 重复 | 删除 `.workspace-location`，当前页由 h1 + `main[aria-label]` + `aria-current` 表达 |
| R3 | 桌面 header 不粘性 | ≥1024 sticky + `scroll-padding-top`，≤1023 保持静态 |
| R4 | ≤767 3×3 导航 + 242px sidebar + 65px header | ≤1023 单行横向滚动导航、44px 触达、brand 紧凑 |
| R5 | CSS 散落硬编码颜色/圆角/阴影 | `:root` 语义 token + 应用自有类替换 |
| R6 | Search 字段组 9 项常驻展开 | `<details>` 默认折叠，逻辑/偏好不变 |
| R7 | 授权面板 inline 固定双栏 | CSS 双栏；≤1023 单列 |
| R8 | Dashboard 5 卡 2 列时末卡半列 | ≤767 末奇数卡跨列 |
| R9 | 宽表需自身滚动 | 保持 `DataTable` `scroll.x`；补齐 `min-width:0`，禁止页面 `overflow-x:hidden` |

## 2. 模块边界

| 边界 | 文件 | 动作 |
| --- | --- | --- |
| 布局/样式/token/断点 | `frontend/src/index.css` | 主要改动；token 唯一定义处 |
| 壳层 JSX | `frontend/src/pages/HomePage.tsx` | 删除重复块；eyebrow aria-hidden；激活导航项 scrollIntoView |
| boot 容器 | `frontend/src/App.tsx` | 两处 `<main>` 加 `boot-main` |
| 搜索字段组 | `frontend/src/components/GlobalSearch.tsx` | fieldset → details/summary |
| 授权面板 | `frontend/src/components/ClusterAuthorizationPanel.tsx` | 移除 inline style，改 class |
| 文档 | `docs/architecture/frontend-ui-stack.md` §5 | 定稿后同步布局基线 |
| Ant 主题/依赖/API/后端/共享原语 | `frontend/src/main.tsx`、`package.json`、`docs/api/*`、`backend/*`、`components/ui/*` | 不改 |

## 3. 设计决策

### DR-F033-01 页头去重

删除 header 内 `.workspace-location`。当前页仍由内容区 `h1`、`main[aria-label]`、导航 `aria-current="page"` 表达；`currentPage` 推导和权限门控不变。

### DR-F033-02 桌面 sticky header

≥1024：`html { scroll-padding-top: var(--csm-header-offset); }`、`.app-header { position:sticky; top:0; z-index:30; }`、`.workspace-content { scroll-margin-top: var(--csm-header-offset); }`。`--csm-header-offset:72px`（以实测校正）。≤1023 不 sticky。z-index 30 低于 Ant Modal 与 skip-link 1000。

### DR-F033-03 非桌面壳层

≤1023：sidebar padding 10/16；brand 32px、mb 8；`.app-nav` 单行 `flex-wrap:nowrap; overflow-x:auto; scroll-snap-type:x proximity;`；nav-link `flex:0 0 auto; min-height:44px; white-space:nowrap`；隐藏 group label/sidebar note；右侧渐隐提示。当前激活项在 section 变化后 `scrollIntoView({inline:"nearest"})`。header 8/16、user gap 8、按钮 min-height 44。375 壳层预算约 164px（≤200）。

### DR-F033-04 标题层级

每页唯一 h1 = currentPage.description；卡片 h2/h3 不变；`.page-eyebrow` 加 `aria-hidden="true"`，≤480 隐藏；≤767 subtitle 不强制整行；h1 使用 `--csm-font-h1:24px`。

### DR-F033-05 语义 token

在 `:root` 定义：
- 主色 `--csm-primary #2563eb`、`--csm-primary-strong #1d4ed8`、`--csm-primary-soft #eaf1ff`、`--csm-primary-soft-border #b5cafa`
- 文本 `--csm-text #172b4d`、`--csm-text-muted #52637a`、`--csm-text-subtle #6b7280`、`--csm-text-label #374151`
- 表面 `--csm-surface #fff`、`--csm-surface-subtle #f9fafb`、`--csm-surface-raised #f7f9fc`、`--csm-background #f4f6fa`、`--csm-hover-bg #f1f5fb`、`--csm-selected-bg #eff6ff`
- 边框 `--csm-border #e5eaf1`、`--csm-border-subtle #e5e7eb`、`--csm-border-dashed #d1d5db`、`--csm-divider #f3f4f6`
- 语义态 `--csm-danger-text #b91c1c`、`--csm-warning-text #92400e`、`--csm-highlight-bg #fef08a`
- 阴影/焦点 `--csm-shadow-panel`、`--csm-focus-ring`
- 圆角 `--csm-radius-sm/md/lg`
- 间距 `--csm-space-1..6`
- 字阶 `--csm-font-h1/h2/body/note`
- 布局 `--csm-content-max:1600px`、`--csm-content-gutter`、`--csm-header-offset:72px`、`--csm-nav-item-height`

替换原则：只替换应用自有类；不新增 `.ant-*` 选择器；Ant token 仍由 `main.tsx` 承载；`index.css` 中 hex 只允许出现在 `:root`；`rgb()` 只允许阴影 token；无对应 token 先补再替换。

### DR-F033-06 main 宽度收口

删除 `main { max-width:720px; ... }`。改为：
- `.boot-main { max-width:720px; margin-inline:auto; padding:48px 24px; }`
- `.login-main { max-width:460px; ... }`
- `.workspace-content { width:100%; max-width:var(--csm-content-max); margin-inline:auto; padding:20px var(--csm-content-gutter) 40px; min-width:0; }`

`App.tsx` boot-loading/boot-error 加 `className="boot-main"`。`.main-wide` 保留兼容别名。

### DR-F033-07 GlobalSearch 字段组默认折叠

`fieldset` → `<details className="search-fields-toggle">`，`<summary>` 使用原 legend 文案；内部 `div role="group"` 保留 9 个复选框与原说明。不写 `open`，不持久化展开态。`selectedFields`、localStorage 键/值、`changeField`、`buildSearchQuery`、`applied` 零改动。summary 原生键盘可操作，focus-visible 使用统一焦点环。

### DR-F033-08 授权面板响应式

移除 inline `display:grid/gridTemplateColumns/gap` 与 `<ul>` inline 样式；CSS：
```
.authorization-layout { display:grid; gap:16px; align-items:start; grid-template-columns:minmax(240px,1fr) minmax(0,2fr); }
.authorization-user-list { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:4px; }
.authorization-user-list .csm-button { width:100%; justify-content:flex-start; }
@media (max-width:1023px){ .authorization-layout{grid-template-columns:minmax(0,1fr);} .authorization-user-list .csm-button{min-height:44px;} }
```
授权表格继续在自身区域横向滚动；权限/409/确认行为不变。

### DR-F033-09 Dashboard 计数卡

≤767 保持两列；`.dashboard-counts > .count-card:last-child:nth-child(odd) { grid-column:1/-1; }`。其他断点不变。

### DR-F033-10 表格

不改 `DataTable`（`scroll={{x:"max-content"}}`、`size="small"`、无分页）。补齐 `.app-workspace`/`.workspace-content`/`.panel`/`.table-wrap` 的 `min-width:0`。禁止在 html/body 加 `overflow-x:hidden`。

### DR-F033-11 Ant 主题/依赖

不改 `main.tsx` 的算法/token、`package.json` 依赖、组件库版本、路由/状态库。只有 `index.css` 应用自有类与 4 个 JSX 文件改动。

## 4. 断点

| 断点 | 行为 |
| --- | --- |
| ≥1024 | 224px 侧栏、sticky header、导航 42px 竖排、授权双栏、gutter 32px |
| ≤1023 | 单列壳层、单行横向滚动导航 44px、header 非 sticky、授权单列、gutter 20px |
| ≤767 | Dashboard 2 列+末奇数卡跨列、标题单列、筛选/表单整行、detail 单列、按钮 44px、gutter 16px |
| ≤480 | gutter 12px、eyebrow 隐藏、nav 12px、角色标签紧凑 |
| ≥1280 | Dashboard 5 列（既有） |

巡检：1440×900、1024×768、768×1024、375×667。

## 5. 验证策略

1. `cd frontend && npm run typecheck`、`npm run build`、`npm run smoke:client`。
2. 浏览器四视口（外部 Playwright，不新增仓库依赖）检查：
   - 页面 `scrollWidth <= clientWidth`；宽表在 `.ant-table-content` 内滚动。
   - 375 壳层高度 ≤200；导航项 ≥44；激活项可见。
   - 768/375 授权面板单列；1024/1440 双栏。
   - Search details 默认无 `open`，展开后 9 个 checkbox 可聚焦；偏好/请求参数不变。
   - 375 Dashboard 5 卡无孤立半列。
   - 桌面 sticky header 滚到底仍 top=0；焦点不被遮挡。
3. 静态核对：`index.css` hex 仅在 `:root`；授权面板无 inline style；`workspace-location` 无残留；`main.tsx`/`package.json`/API/DB/shared ui 零 diff。
4. 截图存 `docs/features/F033/artifacts/`，覆盖四视口与代表页面。

## 6. 风险与兼容

- sticky header 可能遮挡焦点：scroll-padding + scroll-margin + 实测；z-index 30。
- 横向导航可发现性：保留文字标签、渐隐边缘、scroll-snap、激活项滚入。
- CSS token 替换范围：只改应用自有类，分步提交，grep 白名单。
- 单列授权表横向滚动：保留 Ant scroll.x。
- 无浏览器自动化时布局项必须标 NOT TESTED，不以 build 冒充。
- 不改变删除/释放/恢复确认、两阶段导入、401/403/409/422、分页排序过滤、权限门控、skip-link/焦点转移。
- 不改 `components/ui/` 契约，不删除旧 class，不新增第二套组件。

## 7. Contract

`NOT_REQUIRED`：无 Endpoint/参数/Schema/错误码/权限/上限变化；不新建 `docs/api/F033.md`。

## 8. 结论

**READY FOR DESIGN**。数据库/API/权限/业务语义零影响；11 项 DR 均落在 `index.css` 与 4 个呈现层文件；A1–A11 可验证。待 Test Design 后定稿 `READY FOR IMPLEMENTATION`。

## 9. 设计定稿与签核（v1 / 2026-10-23）

- **状态**：READY FOR IMPLEMENTATION
- **设计版本**：architecture v1（定稿，含本节修订）
- **签核者**：Architect
- **覆盖 Feature**：F033
- **上游批准依据**：requirements revision 12 §28；用户 2026-10-23 布局/CSS 要求；plan revision 19；F028 前端验收基线。
- **同级设计核对**：Test Design TD-1 / v1 / 2026-10-23（`docs/features/F033/test-report.md`，TEST DESIGN READY）；Database `NOT_REQUIRED`；Contract `NOT_REQUIRED`。

### 9.1 核对结论

1. A1–A11 已被 TD-1 全覆盖（11/11）；DR-F033-01..11 与验证项一一可映射。
2. DR 与 Test Design 无冲突。A10 由 Product 可选、DR-02 选定实现，TD-1 据此列为必测。
3. layers/API/Contract 成立：`frontend=true`、`backend=false`、`database=false`、`api_required=false`、Contract NOT_REQUIRED；写入面限 `index.css` + 4 个呈现层文件 + 文档 §5。
4. TD-1 N1–N4 接受为 NOTE 级实现提醒，不改变 A 项判定。

### 9.2 定稿修订

- **R1 前提修正**：`main{max-width:720px}` 当前受类选择器优先级影响并未实际收窄 `.workspace-content`；真实影响是裸 `<main>`（App boot 两态）与全局 padding。删除仍必要，但不得把“宽表页变宽”作为改善证据；A8 宽度项按回归守护。
- **375 预算修正**：由约 164px 修正为约 180px（sidebar ≈120 + header 单行 ≈60）。≤480 必须保持 header 单行（必要时隐藏 brand 副标题、收紧角色标签/登出按钮但保留可访问名与登出可用性）；375 实测 >200px 判 A2 FAIL 并回设计。
- **激活导航项滚入**：使用 `<nav>` 原生 ref + `querySelector(".app-nav .nav-link-active")`；共享 `Button` 不转发 ref，不得修改 `components/ui`。
- **token 补充**：保留 `--csm-muted`（或作为 `--csm-text-muted` 别名）；新增 token 与 `main.tsx` Ant token 对齐（primary `#2563eb`、text `#172b4d`、secondary `#52637a`、layout `#f4f6fa`、border `#e5eaf1`、radius 10px）；不新增 `.ant-*` 选择器。
- **窄屏 padding**：保留 `@media (max-width:767px){ main { … } }` 或等价下沉到 `.boot-main`/`.login-main`。
- **文档同步**：`frontend-ui-stack.md` §5 的“较窄屏幕导航换行”改写为“≤1023 单行横向滚动导航、≥1024 sticky header、token 单一来源、容器宽度收敛、details 折叠”；不改 §1/§2/§4 或 §3 行为兼容。
- **测试执行**：TD-1 §8 临时 Vite 代理与 Playwright 脚本置于仓库外，避免 S-V4/S-V6 误判。

### 9.3 移交实现的前置条件

无阻塞。TEST-1 前按 TD-1 amendment 收敛判定式（`.app-nav .nav-link-active` 作用域、A8.4 宽度判定、A7.1/A6.2/A6.6 时序、smoke 基线计数以实测 log 为准），不改变 A 项与 DR 意图。

### 9.4 签核

| 角色 | 对象 | 结论 |
| --- | --- | --- |
| Architect | F033 架构设计 v1；Contract NOT_REQUIRED | CONFIRMED / READY FOR IMPLEMENTATION（2026-10-23） |
| Database | Schema/Migration | NOT_REQUIRED |
| Tester | Test Design TD-1 v1 | TEST DESIGN READY |
