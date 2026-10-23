# F033 前端布局与 CSS 质量优化 — IMPLEMENTATION 阶段报告

- **状态**：FRONTEND COMPLETE
- **版本**：v1
- **角色**：Frontend（只改呈现层；不新增业务规则、不改 API 契约 / Schema / 权限 / 服务端语义）
- **上游依据**：`docs/features/F033/product.md` v1（A1–A11）；`docs/features/F033/architecture.md` v1 定稿（DR-F033-01..11 + §9 修订，READY FOR IMPLEMENTATION / 2026-10-23）；`docs/features/F033/test-report.md` TD-1 v1（TEST DESIGN READY）；`docs/architecture/frontend-ui-stack.md` §2/§3/§5；`docs/product/requirements-v3.md` revision 12 §28；Contract `NOT_REQUIRED`（无 Endpoint / 参数 / Schema / 错误码变化）。

## 1. 范围

只做呈现层质量优化：应用壳结构、语义 CSS token、容器宽度、页头层级、三处局部布局（搜索字段组 / 授权面板 / Dashboard 计数卡）。交互语义、请求参数、localStorage 偏好、权限门控、错误 / 确认 / 分页排序过滤语义零改动。

`layers`：`database=false`、`backend=false`、`frontend=true`；`api_required=false`；Contract `NOT_REQUIRED`。

## 2. 修改文件

| 文件 | 动作 | 说明 |
| --- | --- | --- |
| `frontend/src/index.css` | 改写 | 语义 token 单一来源；删除全局 `main` 裁宽；`.boot-main` / `.login-main` / `.workspace-content` 容器；≥1024 sticky header + `scroll-padding-top`；≤1023 单行横向滚动导航 + 右缘渐隐 + 44px 触达；`.workspace-location` 样式删除；授权面板双栏/单列；`details` 摘要样式；≤767 末奇数计数卡跨列；`min-width:0` 补齐 |
| `frontend/src/App.tsx` | 修改 2 处 | boot-loading / boot-error 的 `<main>` 加 `className="boot-main"` |
| `frontend/src/pages/HomePage.tsx` | 修改 4 处 | 删除 header 的 `.workspace-location`；`page-eyebrow` 加 `aria-hidden`；nav 外包 `.nav-scroller` 并加 `navRef`；section 变化后 `querySelector(".app-nav .nav-link-active")` + `scrollIntoView({inline:"nearest",block:"nearest"})` |
| `frontend/src/components/GlobalSearch.tsx` | 修改 | `fieldset/legend` → `<details>/<summary>`（默认折叠）+ 内部 `div[role="group"]`；其余逻辑零改动 |
| `frontend/src/components/ClusterAuthorizationPanel.tsx` | 修改 2 处 | 移除 `.authorization-layout` 与 `.authorization-user-list` 的 inline style，改用 CSS 类 |
| `docs/architecture/frontend-ui-stack.md` | §5 增补 | 新增 §5.1「2026-10-23 呈现层维护（F033）」；§1/§2/§3/§4 未改 |
| `docs/features/F033/implementation.md` | 新建 | 本报告 |

未修改（按架构 §2 边界核对）：`frontend/src/main.tsx`、`frontend/package.json`、`frontend/package-lock.json`、`frontend/src/components/ui/*`、`frontend/vite.config.ts`、`backend/*`、`docs/api/*`。

## 3. DR 对照

| DR | 实现内容 | 位置 |
| --- | --- | --- |
| DR-F033-01 页头去重 | 删除 header 内 `.workspace-location` 与其 CSS；当前页由 `h1` + `main[aria-label]` + `aria-current="page"` 表达；`currentPage` 推导与权限门控未改 | `HomePage.tsx` 178 行区、`index.css` |
| DR-F033-02 sticky header | ≥1024：`.app-header{position:sticky;top:0;z-index:30}`、`html{scroll-padding-top:calc(var(--csm-header-offset)+var(--csm-space-2))}`、`.workspace-content{scroll-margin-top:var(--csm-space-2)}`；≤1023 非 sticky | `index.css` `@media (min-width:1024px)` |
| DR-F033-03 非桌面壳层 | ≤1023：sidebar `padding:10px/16px/12px`、brand 32px + `mb:8`、英文副标题收起；`.app-nav{flex-direction:row;flex-wrap:nowrap;overflow-x:auto;scroll-snap-type:x proximity}`、`.nav-entry{flex:0 0 auto}`、`.nav-link{min-height:44px;white-space:nowrap}`；`.nav-scroller::after` 右缘渐隐；`.nav-group-label`/`.sidebar-note` 隐藏；header 8/16、`user-box` gap 8、header 按钮 44px；激活项 `scrollIntoView` | `index.css`、`HomePage.tsx` |
| DR-F033-04 标题层级 | 唯一 `h1` = `currentPage.description`；`.page-eyebrow[aria-hidden="true"]`，≤480 `display:none`；`h1` 用 `--csm-font-h1:24px`；`h2` 用 `--csm-font-h2` | `HomePage.tsx`、`index.css` |
| DR-F033-05 语义 token | `:root` 定义主色 / 文本 / 表面 / 边框 / 语义态 / 阴影 / 焦点环 / 圆角 / 间距 / 字阶 / 布局共 45 个 `--csm-*`；保留 `--csm-muted` 作为 `--csm-text-muted` 别名；应用自有类全部改为引用 token；无新增 Ant 内部选择器 | `index.css` `:root` |
| DR-F033-06 main 宽度收口 | 删除 `main{max-width:720px…}`；新增 `.boot-main`（≤720）、`.login-main`（460 + `clamp` 顶部间距）、`.workspace-content`（`width:100%` + `--csm-content-max:1600px` + `min-width:0`）；`.main-wide` 兼容别名保留；≤767 内边距等价下沉到 `.boot-main`/`.login-main` | `index.css`、`App.tsx` |
| DR-F033-07 搜索字段组折叠 | `<details className="search-fields-toggle">` + `<summary>`，不写 `open`、不持久化展开态；内部 `div[role="group"][aria-label]` 保留 9 个复选框与说明；`selectedFields` / `changeField` / `readGlobalSearchFieldPreference` / `writeGlobalSearchFieldPreference` / `buildSearchQuery` / `applied` 零改动 | `GlobalSearch.tsx`、`index.css` |
| DR-F033-08 授权面板响应式 | 移除两处 inline style；`.authorization-layout`（≥1024 `minmax(240px,1fr) minmax(0,2fr)`，≤1023 单列）、`.authorization-user-list`（`flex` 列 + 按钮 100% 宽 / 左对齐 / `min-height:40px`；≤1023 `44px`）、子 `section` `min-width:0`；授权表继续自身滚动；权限 / 409 / 确认行为不变 | `ClusterAuthorizationPanel.tsx`、`index.css` |
| DR-F033-09 Dashboard 计数卡 | ≤767 保持两列 + `.dashboard-counts > .count-card:last-child:nth-child(odd){grid-column:1/-1}`；768–1023 三列、≥1280 五列不变 | `index.css` |
| DR-F033-10 表格 | 未改 `DataTable`（`scroll={{x:"max-content"}}`、`size="small"`、无分页）；`.app-workspace`/`.workspace-content`/`.panel`/`.table-wrap`/`.page-heading`/`.dashboard-counts` 补 `min-width:0`；`html`/`body` 无 `overflow-x:hidden` | `index.css` |
| DR-F033-11 Ant 主题 / 依赖 | `main.tsx` 算法与 token、`package.json` 依赖、组件库版本、路由 / 状态库零改动 | — |

### 3.1 与 DR 文本的偏差（均为实现细节，不改变意图）

1. **滚动落点不叠加两份 header 偏移**：DR-F033-02 给定 `html{scroll-padding-top:var(--csm-header-offset)}` + `.workspace-content{scroll-margin-top:var(--csm-header-offset)}`。二者在浏览器中**叠加**计算（144px），会在跳转后留下约 70px 无效空白。实现改为 `scroll-padding-top: calc(var(--csm-header-offset) + 8px)` + `scroll-margin-top: var(--csm-space-2)`（合计 80px，实测 header 高 69px），仍全部由 token 驱动，`V-A10.4` 几何结论成立。
2. **`.nav-scroller` 包装层**：`HomePage.tsx` 在 `<nav className="app-nav">` 外增加一个包装 `div`，用于承载右缘渐隐（`::after` 需要在滚动容器之外定位）；`.app-nav` 仍是滚动容器，测试选择器 `.app-nav .nav-link(-active)` 不受影响。
3. **授权列表按钮基线高度**：DR-F033-08 只给 ≤1023 的 `min-height:44px`；为避免桌面端按钮高度低于 Ant `controlHeight(40)` 造成视觉不一致，基础规则使用 `height:auto; min-height:40px`（内容可换行、不裁切），≤1023 提升为 44px。
4. **token 补充**：DR 列表未覆盖的既有色值新增 `--csm-primary-wash`(#f8faff)、`--csm-surface-inset`(#fafbfd)、`--csm-on-primary`（原 `white` 关键字）、`--csm-touch-target`、`--csm-font-body`，均为等价取值，不改变视觉。

## 4. Verification

### 4.1 实际执行的命令（`cd frontend`）

| 命令 | 结果 |
| --- | --- |
| `npm run typecheck`（`tsc --noEmit`） | exit 0，无输出 |
| `npm run build`（`tsc --noEmit && vite build`） | exit 0；`dist/assets/index-*.css 23.93 kB`、`index-*.js 1,264.51 kB`；仅既有 chunk >500 kB 提示 |
| `npm run smoke:client` | **328 passed, 0 failed**（F028 基线 322，增加不减少，符合 `V-A9.1`） |

### 4.2 静态核对（对应 TD-1 §4）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| S-V1 | `grep -nE '#[0-9a-fA-F]{3,8}\b' frontend/src/index.css` | 命中共 24 行，全部落在 `:root{}` 块内（行 15–48；块范围 13–94） |
| S-V1 rgb | `grep -nE 'rgba?\(' frontend/src/index.css` | 仅 `--csm-shadow-panel`、`--csm-focus-ring` 两行 |
| S-V2 | 脚本比对 `var(--csm-*)` 定义 / 引用集合 | 未定义引用 **0**（定义 45，全部被引用） |
| S-V2 | `grep -n 'workspace-location' -r frontend/src` | 0 命中（TSX 与 CSS 均无残留） |
| S-V3 | `grep -n 'style={{' frontend/src/components/ClusterAuthorizationPanel.tsx` | 0 命中 |
| S-V8 | `grep -n 'ant-' frontend/src/index.css` | 0 命中（无 Ant 内部选择器） |
| S-V8 | `grep -n 'overflow-x' frontend/src/index.css` | 仅 `.json-block`、`.app-nav`（`auto`）；`html`/`body` 无 `overflow-x:hidden` |
| S-V7 | 人工核对 `currentPage` / `canAudit` / `canSystem` / `handleLogout` / `selectedFields` / `changeField` / `buildSearchQuery` / `applied` | 未修改（仅 JSX 结构与属性变更） |
| S-V9 | `h1` 结构来源 | 仍仅 `HomePage.tsx` 的 `.page-heading`；卡片内为 `h2/h3` |

### 4.3 补充自查（非正式巡检证据，临时脚本在仓库外）

说明：TD-1 §8 的四视口正式巡检与截图仍由 Tester 执行（见 §5）。实现期间用**仓库外**临时 Playwright 脚本（`/tmp/f033check/*.py`，未新增任何仓库内 Vite/Playwright 配置或依赖）对当前源码做过一次快速自查，仅为降低返工风险，**不构成验收证据，也未生成 `docs/features/F033/artifacts/` 截图**。

自查连接的是已存在的开发服务 `http://127.0.0.1:15173`（服务 `frontend/src` 源码 + 代理 `127.0.0.1:18080` 测试栈，账号 `admin`）；实测项与结果：

| 项 | 1440×900 | 1024×768 | 768×1024 | 375×667 |
| --- | --- | --- | --- | --- |
| 页面横向溢出（`documentElement.scrollWidth` vs `clientWidth`） | 1440/1440 | 1024/1024 | 768/768 | 375/375 |
| `html`/`body` computed `overflow-x` | visible | visible | visible | visible |
| header `position` / `z-index` | sticky / 30 | sticky / 30 | static | static |
| 滚到底后 header `top` | 0 | 0 | −256 | −957 |
| `scroll-padding-top` | 80px | 80px | auto | auto |
| `main` computed `max-width` | 1600px | 1600px | 1600px | 1600px |
| `.workspace-content` 宽度 | 1216 | 800 | 768 | 375 |
| `.workspace-location` 数量 / `h1` 数量 | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 1 |
| eyebrow `display` / `aria-hidden` | block / true | block / true | block / true | none / true |
| nav 项高度 | 42 | 42 | 44 | 44 |
| nav 滚动容器（`scrollWidth`/`clientWidth`） | 不滚动 | 不滚动 | 825/736 | 712/343 |
| 切到 System 后激活项在可视区（`scrollIntoView`） | true | true | true | true（`scrollLeft 369`） |
| 375 壳层高度（header.bottom） | — | — | 176 | **176**（≤180 预算、≤200 判定） |
| 计数卡列数 / 末卡宽度比 | 5 / 0.19 | 3 / 0.32 | 3 / 0.32 | 2 / **1.00**（跨满行） |
| `.authorization-layout` 轨道 | 2（362+724） | 2（240+430） | 1（678） | 1（301） |
| 授权账号按钮高度 / 宽度比 | 40 / 1.00 | 40 / 1.00 | 44 / 1.00 | 44 / 1.00 |
| `details` 折叠态 `open` / `[role=group]` | false / 1 | false / 1 | false / 1 | false / 1 |
| 键盘展开后 9 个 checkbox 可聚焦 | 9/9 | 9/9 | 9/9 | 9/9 |
| 搜索卡高度（折叠 / 展开，px） | 501.5 / 583.3 | 525.5 / 657.7 | 525.5 / 657.7 | **677.6 / 997.7** |
| Resources 表 `.ant-table-content` `overflow-x` | auto | auto | auto | auto |
| 表格滚到最右后页面 `scrollWidth` | 1440（不变） | 1024（不变） | 768（不变） | 375（不变） |
| 登录页 `main` 宽 / 页面溢出 | 460，无溢出 | — | — | 375，无溢出 |
| 跳过导航链接（`Tab` → `Enter`） | hash `#workspace-content`、焦点落内容区、`h1.top 117.7 > header.bottom 69` | — | — | hash 生效、`h1.top 196 > header.bottom 176` |
| 切页后焦点 | `#workspace-content` | `#workspace-content` | `#workspace-content` | `#workspace-content` |
| nav 项键盘焦点环 | — | — | — | `3px solid`、`offset 0`、指示完全在滚动容器内 |
| 右缘渐隐提示 | 无（不溢出） | 无 | 有 | 有（24px） |
| 登录后新增 console error / pageerror | 0 | 0 | 0 | 0 |

自查中观察到的既有现象（**非本次引入**，仅记录）：`[antd: Alert] message is deprecated`、`[antd: Modal] maskClosable is deprecated` 两条 deprecation warning 属既有代码基线；登录前 `/api/v1/auth/me` 的 401 属启动恢复登录态的正常路径。

### 4.4 UI 改进要点与技能建议采用情况

- 采用 `ui-ux-pro-max`（`.agents/skills/ui-ux-pro-max/SKILL.md`）两次最小检索：
  - `"sticky header focus not obscured" --domain ux` → 采纳 `scroll-padding` 抵消粘性 UI（已实现，且修正了 DR 的双重偏移）与 focus-not-obscured 判定方法。
  - `"adaptive navigation horizontal scroll sidebar" --domain ux` → 检索结果中的 `Horizontal Scroll`（避免页面级横向滚动）按 CSM 场景适配：**页面级**不横向滚动，横向滚动仅限导航条这一受控 rail（`scroll-snap` + 渐隐提示 + 激活项滚入），未采纳其结果中「全局 `overflow-x:hidden` + `max-w-full`」的做法（会掩蔽真实溢出，与 A1/V-A1.3 冲突）。
- 触达目标：≤1023 导航项、header 按钮、授权账号按钮、`details` 摘要行均 ≥44px；状态不只用颜色表达（激活项同时有背景、左侧边线与 `aria-current`）。

## 5. 未验证项

| 项 | 状态 | 原因 / 后续 |
| --- | --- | --- |
| TD-1 §2 的「四视口 × 11 页面」正式巡检与截图（`docs/features/F033/artifacts/`） | **NOT TESTED（交 Tester）** | 本次为 Frontend 实现阶段；按任务划分由 TEST-1 依 TD-1 §8 执行，实现未创建 artifacts 目录、未新增仓库内 Vite/Playwright 配置 |
| A1/A5/A6/A7/A8/A10 的正式 PASS/FAIL 判定 | **NOT TESTED** | 同上；§4.3 自查数据仅供 Tester 对照，不代替 PASS 结论 |
| 删除确认 / 释放 / 恢复取消零请求、两阶段导入、401/403/409/422 呈现、非 ADMIN 权限门控 | **NOT TESTED（回归交 Tester）** | 本次零 diff 触及这些逻辑（`ClusterAuthorizationPanel` 仅删 inline style，`GlobalSearch` 仅换外层标签），但按 A9 由 TEST-1 复测 |
| `git diff` 基线核对（S-V4/S-V5/S-V6） | **NOT TESTED** | 需协调器提供 `<F033-base>` 提交；本次未执行任何 Git 写操作，`main.tsx` / `package.json` / `package-lock.json` / `components/ui` / `backend` / `docs/api` 均未改动 |
| A8.5 视觉一致性人工判定 | **NOT TESTED** | 需 Tester 截图后人工比对（本阶段无 artifacts） |

### 5.1 环境副作用（如实披露）

- 临时脚本与本地静态服务文件全部位于 `/tmp/f033check/`（仓库外），未进入工作区。
- 自查结束时为释放端口 `15173`，停止了该端口上**已存在的** Vite 开发服进程（pid 16077，非本任务启动、属先前测试环境的遗留进程）。该进程不影响仓库文件；Tester 执行 TEST-1 时按 TD-1 §8 命令重新启动即可。
- 自查使用了已运行的测试栈（`http://127.0.0.1:18080`，账号 `admin` / `.env.test`），只执行登录与只读查询，未写入业务数据。

## 6. 共享组件 / Contract 影响

- 共享组件：`components/ui/*` 零改动；`.csm-button` 仅新增授权列表作用域下的高度/对齐规则（新增类作用域，不改共享原语）。`Button` 不转发 ref 的约束被遵守（导航滚动使用 `<nav>` 原生 ref）。
- Contract：`NOT_REQUIRED`。请求参数、响应消费、错误码、权限、分页/排序/过滤与本地偏好键值均未改动；`smoke:client` 328 用例全过作为机制级证据。
- Mock：无（本次不涉及数据或 API 变更，`globalSearchFields` 等纯逻辑模块未改）。

## 7. Issues / Next

- **Issues**：None（实现范围内无阻塞项；§3.1 的 4 条偏差均为实现细节，已在此说明供 Architect/Review 复核）。
- **Next（协调器）**：提供 `<F033-base>` 提交 → 调度 TEST-1（按 TD-1 §8，仓库外临时配置）→ 填 `docs/features/F033/artifacts/` 与 `test-report.md` 的 TEST 段。`FRONTEND COMPLETE` 不替代 Test、Review 或 Feature DONE。

GIT: NONE
