# F033 前端布局与 CSS 质量优化 — Test Report

## Task

- Feature：F033（前端布局与 CSS 质量优化）
- 角色：Tester（Tester 专属工作范围：测试设计与独立执行；不改业务实现、Schema 或产品规则）
- 本次工作范围：`TEST`（TEST-1，2026-10-23 / v1），只写本文件与 `docs/features/F033/artifacts/`；上游 TD-1（`TEST_DESIGN`）内容保留在下方各节

## Status

| 阶段 | 版本 / 日期 | 结论 |
| --- | --- | --- |
| TEST_DESIGN（TD-1） | v1 / 2026-10-23 | TEST DESIGN READY（见下文 TD-1 各节） |
| TEST（TEST-1） | v1 / 2026-10-23 | **READY FOR REVIEW**（见 §TE-1；A1–A11 全部 PASS，无必须修复缺陷，1 项 LOW + 3 项 NOTE） |

**TEST DESIGN READY**（TD-1 / v1 / 2026-10-23）

> READY 仅表示 A1–A11 在当前已签核设计（DR-F033-01..11）下**可被客观验证**，即验收映射、判定方法、夹具与证据路径已确定。READY **不是测试通过**，不批准实现完成，也不批准合并。TEST 阶段（TEST-1）才是执行报告，届时另行记录版本、HEAD、命令输出与 PASS/FAIL。

## Basis

| 类型 | 路径 | 版本 / 依据 |
| --- | --- | --- |
| 产品需求 | `docs/product/requirements-v3.md` | revision 12 §28（CONFIRMED：运维控制台，快速/清晰/高效查询与低操作成本，不追求复杂视觉效果；revision 7 二次确认弹窗条款） |
| Feature 产品 | `docs/features/F033/product.md` | v1（READY FOR ARCHITECT，A1–A11，S1–S7，§2 明确不做） |
| Feature 架构 | `docs/features/F033/architecture.md` | v1（READY FOR DESIGN，DR-F033-01..11，Contract `NOT_REQUIRED`） |
| 架构基线 | `docs/architecture/frontend-ui-stack.md` | §2/§3/§5（Ant Design + Tailwind 边界、布局基线；§5 需在实现后同步） |
| 公共规则 | `AGENTS.md` §7/§9、`docs/project/handoff.md`、`docs/project/implementation-rules.md`「验证与交付」 | 当前 |
| 前端实现（被检对象基线） | `frontend/src/index.css`（780 行）、`frontend/src/App.tsx`、`frontend/src/pages/HomePage.tsx`、`frontend/src/components/GlobalSearch.tsx`、`frontend/src/components/ClusterAuthorizationPanel.tsx`、`frontend/src/main.tsx`、`frontend/package.json` | 工作区 HEAD（F033 实施前状态） |
| Plan | `docs/project/project-plan.yaml` | revision 19（F033，depends_on F028 DONE） |

### 设计与需求的一致性核对（Tester 侧，只核对可验证性）

- 层影响：`database=false`、`backend=false`、`frontend=true`、`api_required=false`。与 product §3「无实体/关系/状态/唯一性/字段/生命周期变更」一致；数据完整性方法（`.pi/skills/data-integrity/SKILL.md`）**不适用**，判定为 `NOT_REQUIRED`（见 §9）。
- 架构 §2 划定的写入面：`frontend/src/index.css` + 4 个呈现层文件（`HomePage.tsx`、`App.tsx`、`GlobalSearch.tsx`、`ClusterAuthorizationPanel.tsx`）+ 文档 §5。该边界使「零业务语义变更」可由 diff 静态判定（S-V4、S-V6）。
- 断点口径统一（≥1024 / ≤1023 / ≤767 / ≤480 / ≥1280），A2/A5/A7 的期望值由断点表唯一确定，不存在需 Tester 自行发明的领域状态或默认值。
- A10 在 product 中标为「可选（S7）」，架构 DR-F033-02 已明确选择**实现** sticky header（≥1024）。因此 A10 在本 Feature 内为**必测项**，不适用「否则报告维持现状」分支。
- 契约：`NOT_REQUIRED`，不新建 `docs/api/F033.md`；接口层验证范围仅「请求参数与响应消费零变化」（V-A6.6、V-A9.7）。

## 1. 验收映射 A1–A11 → 验证项

判定单位：PASS / FAIL / BLOCKED / NOT TESTED。TD-1 阶段全部 `NOT TESTED`（原因：实现尚未开始，且本轮仅做设计检查）。

| AC | 验证项 | 判定方式（客观量） | Owner（若 FAIL） |
| --- | --- | --- | --- |
| A1 | V-A1.1 | 4 视口 × 全页面矩阵（§2）逐项断言 `document.documentElement.scrollWidth <= clientWidth` 且 `body.scrollWidth <= clientWidth`（容差 1px） | Frontend |
| A1 | V-A1.2 | 宽表页（Resources / Audit / IP Addresses）：`.ant-table-content` computed `overflow-x ∈ {auto, scroll}`；在其中 `scrollLeft = scrollWidth` 后页面 `scrollWidth` 不变 | Frontend |
| A1 | V-A1.3 | 禁止掩蔽：`html`/`body` computed `overflow-x` ≠ `hidden`（样式与计算值双查） | Frontend |
| A2 | V-A2.1 | 375×667：壳层高度 = `.app-header` `getBoundingClientRect().bottom`（sidebar 在其上方，等价「导航+顶部区合计」）≤ 200（严格）；同时记录实测值 | Frontend / Architect（预算） |
| A2 | V-A2.2 | 375×667：`h1` 可见（`is_visible`）且 `rect.top < 567`；标题后首个内容块 top < 667 | Frontend |
| A2 | V-A2.3 | 375 与 768：每个 `.app-nav .nav-link` `height >= 43.5`（44 触达，含亚像素）且含非空文本标签；数量 = 当前角色应有导航数（admin：9） | Frontend |
| A2 | V-A2.4 | 375 与 768：`.nav-link-active` 元素矩形被横向导航滚动容器可视区完全包含（`offsetLeft >= scrollLeft && offsetLeft + width <= scrollLeft + clientWidth`） | Frontend |
| A2 | V-A2.5 | 切换到最后一个导航项（System）后 `.nav-link-active` 仍满足 V-A2.4（`scrollIntoView({inline:"nearest"})` 生效） | Frontend |
| A3 | V-A3.1 | 768/1024/1440：逐个点击/键盘激活全部导航项，`main[aria-label]` 与 `h1` 随之更新且未抛错 | Frontend |
| A3 | V-A3.2 | 每次切页后 `document.activeElement === #workspace-content`（既有 `contentRef.focus({preventScroll:true})` 保持） | Frontend |
| A3 | V-A3.3 | `Tab` 首按焦点落到 `.skip-link`；`Enter` 后 `location.hash === "#workspace-content"` 且 `h1` 未被 header 遮挡（见 V-A10.4） | Frontend |
| A3 | V-A3.4 | 三视口下连续 `Tab` 40 次：`activeElement` 从不出现在 `display:none` 元素上、无焦点陷阱（不回到 body 死循环中断前项） | Frontend |
| A4 | V-A4.1 | 全页面矩阵：`.workspace-location` 匹配数 == 0（DOM 与 `getComputedStyle` 双查） | Frontend |
| A4 | V-A4.2 | 每页 `h1` 数量 == 1，文本 == 期望页面名（概览=资源概览、Resources=资源台账、…、System=系统管理） | Frontend |
| A4 | V-A4.3 | `main[aria-label]` 文本 == `h1` 文本；`[aria-current="page"]` 数量 == 1 且指向对应导航项 | Frontend |
| A4 | V-A4.4 | `.page-eyebrow` 有 `aria-hidden="true"`；375/480 以下 computed `display: none` | Frontend |
| A4 | V-A4.5 | header 文本内容不包含当前页名（header 仅 username / role / 登出），即删除后无重复表达 | Frontend |
| A5 | V-A5.1 | 768 与 375：`getComputedStyle('.authorization-layout').gridTemplateColumns` 解析为 **1 个 track**；两子 section 垂直堆叠（`child2.top >= child1.bottom - 1`） | Frontend |
| A5 | V-A5.2 | 1024 与 1440：解析为 **2 个 track**；两子 section 并排（`left2 >= right1 - 1` 且 `top` 差 ≤ 2） | Frontend |
| A5 | V-A5.3 | 无重叠/裁切：每个子 section rect 落在 `.authorization-layout` rect 内（±1px）；子 section 内首末元素不被父容器裁切 | Frontend |
| A5 | V-A5.4 | ≤1023：`.authorization-user-list .csm-button` `height >= 43.5`；列表项 `width` 占满左列（≥95%） | Frontend |
| A5 | V-A5.5 | 授权表格（选中账号后）在自身容器内横向滚动（computed `overflow-x` 且 `scrollWidth > clientWidth` 时页面不溢出） | Frontend |
| A5 | V-A5.6 | 静态：`ClusterAuthorizationPanel.tsx` 内 `style={{` 匹配数 == 0；`.authorization-layout` 与 `.authorization-user-list` 的样式仅来自 `index.css` | Frontend |
| A5 | A5.7 | 功能不变：选择账号 → 授权列表加载；新增/撤销授权的提示文案与 409 语义与 F028 基线一致（文本级断言，不改业务） | Frontend |
| A6 | V-A6.1 | `details.search-fields-toggle` 存在、`open === false`、无 `open` 属性；折叠态可见 checkbox 数 == 0 | Frontend |
| A6 | V-A6.2 | 375×667：搜索卡高度实测并记录；判定「折叠态高度 < 展开态高度（同页对比）」，并与 F028 基线约 945px 对比记录降幅（不新设绝对阈值） | Frontend |
| A6 | V-A6.3 | 键盘展开：焦点置 summary（`Enter`）→ `details.open === true`，9 个 checkbox 均可见；逐一 `Tab` 命中 9 个 `#global-search-field-*`（默认 5 项选中 → 无 disabled） | Frontend |
| A6 | V-A6.4 | 既有规则不变：选中数降到 1 时最后一项仍 `disabled`（此时 8 可聚焦 + 1 disabled，属预期，不记缺陷） | — （预期） |
| A6 | V-A6.5 | localStorage 键 `csm.globalSearch.fields.v1` 与值语义不变：写入自定义集 → 刷新后选中集恢复；损坏值仍静默回退默认 | Frontend |
| A6 | V-A6.6 | 请求参数不变：`page.on("request")` 捕获 `/api/v1/search` URL，折叠态 / 展开态 / 改变展开前完全一致（query 字符串逐字相等） | Frontend |
| A6 | V-A6.7 | 默认选中集仍为 hostname / resource_type / role / status / cluster（5 项）；resource 结果行展示字段与折叠前一致 | Frontend |
| A6 | V-A6.8 | summary 文本 == 原 legend 文案「Resource 行展示字段（仅作用 resource 结果行）」；内部 `[role="group"]` 与说明文案仍在 | Frontend |
| A7 | V-A7.1 | 375：`.dashboard-counts` 计算列数 == 2；`.count-card` 共 5 张；末卡 `width >= 0.95 × 容器 width`（无孤立半列） | Frontend |
| A7 | V-A7.2 | 断点列数符合既有基线：375→2、768→3、1024→3、1440→5（`gridTemplateColumns` track 计数） | Frontend |
| A7 | V-A7.3 | 计数数值与 `GET /api/v1/dashboard` 一致（不退化为 0/占位） | Frontend |
| A8 | V-A8.1 | 静态：`index.css` 中 `#rgb/#rrggbb/#rrggbbaa` 命中只出现在 `:root { ... }` 块内；`rgb(` 只出现在阴影 token（S-V1） | Frontend |
| A8 | V-A8.2 | 所有 `var(--csm-*)` 引用均在 `:root` 有定义（脚本比对集合差为空） | Frontend |
| A8 | V-A8.3 | `index.css` 未新增 `.ant-*` 选择器（`main.tsx` 仍是 Ant token 唯一承载处） | Frontend |
| A8 | V-A8.4 | 1440：`.workspace-content` 宽度 > 1200 且 `main` computed `max-width` 不再是 `720px`；宽表页表格可用宽度接近内容区（不被 720 收窄） | Frontend |
| A8 | V-A8.5 | 抽查 3 类计算值符合 token：主按钮背景 = `--csm-primary` 系蓝色、panel `.count-card` 圆角 = `--csm-radius-*`、页面背景 = `--csm-background`；并留截图供人工比对（浅色表面 + 蓝色主操作 + 统一圆角间距） | Frontend（视觉判定人工） |
| A9 | V-A9.1 | `npm run typecheck`、`npm run build`、`npm run smoke:client` 全量：0 failed（smoke 计数与 F028 基线 322 对比，允许增加，禁止减少/失败） | Frontend |
| A9 | V-A9.2 | 列表：Resources 分页/排序/过滤/模糊搜索各执行一次，结果与查询串符合既有语义 | Frontend |
| A9 | V-A9.3 | 详情：Resource Detail / Cluster Detail 渲染、关系跳转按钮、Activity 区可用 | Frontend |
| A9 | V-A9.4 | 表单：新建 Resource 触发 422 字段级错误呈现；取消返回列表不写入 | Frontend |
| A9 | V-A9.5 | 弹窗：删除二次确认 Modal 含对象标识 + 后果（含软删说明/引用检查提示）、危险样式确认按钮、取消；打开后取消**零**请求（network 断言）；提交中禁用重复点击 | Frontend |
| A9 | V-A9.6 | 权限：非 ADMIN 账号不显示 Audit/System 导航；越权请求 403 明确呈现（账号可用性见 §5，缺账号则 NOT TESTED） | Frontend |
| A9 | V-A9.7 | 错误语义：401 回登录页；403/409/422 文案与 details 呈现；空态与错误互不伪装 | Frontend |
| A9 | V-A9.8 | 登出可用（→ 登录页）；登录页 `.login-main` 宽 460、无横向溢出；启动 loading/错误页 `.boot-main` 宽 ≤720 | Frontend |
| A9 | V-A9.9 | 全流程 `console` 监听：无 `error` 级日志、无 React key/act 警告新增 | Frontend |
| A10 | V-A10.1 | 1440 与 1024：滚动至页面底部后 `.app-header` rect `top == 0`（±1）；computed `position == sticky`、`z-index == 30` | Frontend |
| A10 | V-A10.2 | 滚动后 user-box 与登出按钮在视口内且可点击（登出真实执行到登录页） | Frontend |
| A10 | V-A10.3 | 焦点不被遮挡：滚动到底后聚焦内容区首个按钮，`elementFromPoint(rect.center)` 命中该元素或其子元素，且 `rect.top >= header.bottom - 1` | Frontend |
| A10 | V-A10.4 | `scroll-padding-top` / `scroll-margin-top` 生效：skip-link 跳转与切页后 `h1` `rect.top >= header.bottom` | Frontend |
| A10 | V-A10.5 | 768 与 375：滚动后 `.app-header` `top < 0`（非 sticky，维持静态流） | Frontend |
| A10 | V-A10.6 | Modal / Select 下拉不与 sticky header 争夺层级：打开删除 Modal，header 不覆盖 Modal 内容 | Frontend |
| A11 | V-A11.1 | V-A9.1 的命令结果单列记录（typecheck / build 各自退出码 0） | Frontend |
| A11 | V-A11.2 | 无新增控制台错误（与 V-A9.9 同源，分开记录） | Frontend |
| A11 | V-A11.3 | 文档：`docs/architecture/frontend-ui-stack.md` §5 已同步布局基线（断点、token、容器宽度、details 模式），共享组件说明同步 | Frontend |

## 2. 视口 × 页面矩阵（40 格 + 交互补充）

视口：`1440×900`、`1024×768`、`768×1024`、`375×667`（`deviceScaleFactor=1`、`is_mobile=False`、`emulate_media(reduced_motion="reduce")` 以保证测量确定性）。
访问方式：**同一 SPA 会话**，通过导航切换 section，避免重复登录造成的时序差异。

| ID | 页面 / 状态 | 进入方式 | 每视口断言 |
| --- | --- | --- | --- |
| P1 | 登录页 | 未登录访问 `/`（清 Cookie） | A1、A9.8；截图 |
| P2 | Dashboard（概览） | 登录后默认 section | A1、A2、A3、A4、A7、A8、A10；截图 |
| P3 | Search（搜索态） | P2 内输入关键字 → 搜索（含 resource 结果行） | A6 全部 + A1；折叠/展开两态截图 |
| P4 | Resources 列表 | 导航 Resources | A1、A2、A3、A4、A8.4、A9.2；截图 |
| P5 | Resource Detail | P4 首行打开 | A1、A4、A9.3；截图 |
| P6 | Clusters 列表 | 导航 Clusters | A1、A4、A9.2；截图 |
| P7 | Cluster Detail | P6 首行打开 | A1、A4、A9.3；截图 |
| P8 | Networks | 导航 Networks | A1、A4；截图 |
| P9 | Services | 导航 Services | A1、A4；截图（当前栈为空态，见 §5） |
| P10 | Audit | 导航 Audit | A1、A1.2、A4、A9.2；截图 |
| P11 | System（账号 tab + 授权面板 tab） | 导航 System → 切到「集群授权」 | A1、A4、A5 全部、A10.6；截图 |

补充交互（不入 40 格，但有独立判定）：删除确认 Modal（V-A9.5）、新建表单 422（V-A9.4）、localStorage 重载（V-A6.5）、键盘 Tab 巡检（V-A3.3/3.4）、skip-link（V-A10.4）。

## 3. DOM 指标定义（实现无关、可复现）

统一测量约定：
- 每步操作后 `wait_for_load_state("networkidle")` + 一帧 `requestAnimationFrame` 再测；
- 数值 `round(1)`，等值判定容差 ±1px，阈值判定用严格比较（`>=44` 用 `>=43.5` 吸收亚像素）；
- 元素缺失、`display:none`、rect 全 0 时该子项直接 FAIL（不以「读不到」代替通过）。

| 指标 | 选择器 / 表达式 | 判定 |
| --- | --- | --- |
| 页面横向溢出 | `document.documentElement.scrollWidth` vs `clientWidth`；同查 `body` | `<=`（±1） |
| 壳层高度(375) | `document.querySelector(".app-header").getBoundingClientRect().bottom + window.scrollY` | `<= 200` |
| nav 触达 | 逐个 `.app-nav .nav-link` 的 `getBoundingClientRect().height` | `>= 43.5`（≤1023） |
| nav 激活可见 | `const a = active; a.offsetLeft - nav.scrollLeft >= -1 && a.offsetLeft + a.offsetWidth <= nav.scrollLeft + nav.clientWidth + 1` | `true` |
| 授权面板列数 | `getComputedStyle(el).gridTemplateColumns` → 按顶层空格切分 track 数（`minmax(...)` 内部空格需括号配对解析） | 768/375→1；1024/1440→2 |
| 面板堆叠 | 两子 section rect：单列 `b.top >= a.bottom - 1`；双栏 `b.left >= a.right - 1` | 如上 |
| details 折叠 | `d.open === false && !d.hasAttribute("open")`；可见 `input[type=checkbox]` 计数 == 0 | `true` / `0` |
| 9 checkbox 可聚焦 | 展开后循环 `focus()` 并逐个断言 `document.activeElement.id === 期望 id` | 9/9 |
| Dashboard 末卡跨列 | `lastCard.width / grid.clientWidth` | `>= 0.95`（375） |
| 列数(计数卡) | `gridTemplateColumns` track 数 | 375→2、768→3、1024→3、1440→5 |
| sticky 顶对齐 | 滚到底后 `header.getBoundingClientRect().top` | `0`（±1） |
| 焦点不被遮挡 | `document.elementFromPoint(r.x + r.w/2, r.y + r.h/2)` 是否等于或包含于 `activeElement`；且 `activeRect.top >= headerRect.bottom - 1` | `true` |
| 宽表自身滚动 | `.ant-table-content` computed `overflow-x` ∈ {auto,scroll}；`scrollWidth > clientWidth` 时页面 `scrollWidth` 不变 | 如上 |
| 控制台 | `page.on("console")` 收集 `type == "error"`；`page.on("pageerror")` | 0 条新增 |

预置关注点（**验证要求，不是已发现缺陷**，均以 NOTE 记录，交 Implementer 注意）：
- N1 `.csm-button:focus-visible { outline: 3px solid; outline-offset: 3px }` 在 `overflow-x:auto` 的 `.app-nav` 中可能被裁切 → V-A3.4 需一并断言「键盘聚焦 nav 项时焦点指示可见」（若被裁切，记 LOW）。
- N2 `.search-fields-toggle legend` 选择器在改为 `<summary>` 后需同步（否则字号/颜色丢失）→ V-A6.8 同时断言 summary 的 `font-size` ≈ 0.9rem 与 `color` 取自 token。
- N3 删除全局 `main { max-width:720px }` 后，登录页与 boot 页依赖 `login-main` / `boot-main` → V-A9.8 明确覆盖这两个容器（漏改属 HIGH，因为会使未登录与启动态布局错乱）。
- N4 `--csm-header-offset:72px` 若与实测 header 高度不一致，只影响 scroll offset 精度；判定不依赖该 token 数值，只依赖 V-A10.3/10.4 的几何结论。

## 4. 静态核对（不依赖浏览器）

| ID | 检查 | 期望 | Owner |
| --- | --- | --- | --- |
| S-V1 | `grep -nE '#[0-9a-fA-F]{3,8}\b' frontend/src/index.css` | 命中行全部落在 `:root {` 块内（逐行判定，输出命中行号与所在块）；`rgba?\(` 仅阴影 token 内 | Frontend |
| S-V2 | `grep -rn 'workspace-location' frontend/src` | 0 命中（TSX 与 CSS 均无残留） | Frontend |
| S-V3 | `grep -n 'style={{' frontend/src/components/ClusterAuthorizationPanel.tsx` | 0 命中（DR-F033-08 移除 inline grid 与 `<ul>` inline 样式） | Frontend |
| S-V4 | `git diff --stat <F033-base>..HEAD -- frontend/src/main.tsx frontend/package.json frontend/package-lock.json backend docs/api frontend/src/components/ui` | 空输出（零 diff）。`<F033-base>` 取 F033 起始提交，由协调器在 TEST-1 前提供并写入报告 | Frontend |
| S-V5 | `git diff <F033-base>..HEAD -- frontend/src/main.tsx` | 空（Ant 算法/token 唯一承载处未动，DR-F033-11） | Frontend |
| S-V6 | `git diff --stat <F033-base>..HEAD -- frontend/src` | 改动文件集合 ⊆ {`index.css`, `pages/HomePage.tsx`, `App.tsx`, `components/GlobalSearch.tsx`, `components/ClusterAuthorizationPanel.tsx`} | Frontend |
| S-V7 | 语义零改动人工核对：`currentPage` 推导、`canAudit` / `canSystem` 权限门控、`handleLogout`、`selectedFields` / `changeField` / `buildSearchQuery` / `applied` 逻辑 | 未修改（仅 JSX 结构与属性变更） | Frontend |
| S-V8 | `frontend/src/index.css` 无新增 `.ant-*` 选择器；无 `overflow-x: hidden` 施加在 `html`/`body` | 满足 | Frontend |
| S-V9 | 每页唯一 `h1` 的结构来源 | `HomePage.tsx` 的 `.page-heading` 仍为唯一 `h1` 来源，卡片内仅 `h2/h3` | Frontend |

## 5. 环境与可验证性（TD-1 已实测可达性，未执行验收）

| 项 | 状态 | 证据（TD-1 只读探针） |
| --- | --- | --- |
| 测试栈 `csmtest` | 可用 | `http://127.0.0.1:18080/healthz` → 200；`/` → 200 |
| 前端开发服（Vite 临时配置，代理 18080） | 可用 | `http://127.0.0.1:15173/` → 200 |
| 测试账号 `admin`（口令见 `.env.test`，不入库） | 可用 | `POST /api/v1/auth/login` → 200；角色 `ADMIN`；permissions 含 `AUDIT_READ, USER_ADMIN, VIEW_DELETED, WRITE, DELETE_OBJECT, RESTORE, IMPORT, RELEASE_IP, VIEW_ACTIVITY, READ`；`GET /auth/me` → 200 |
| 既有数据（免造数） | 可用 | `clusters=9`、`resources=7`、`networks=6`、`ip-addresses>0`、`audit>0`；`dashboard.counts = {clusters:9, resources:7, bare_metal:6, virtual_machines:1, networks:6}` |
| Services 数据 | **空**（`total=0`） | P9 走空态；宽表滚动改由 Resources/Audit/IP Addresses 覆盖。**不为此造数**（写入会产生 Audit 行，污染 F028/F032 证据口径） |
| 非 ADMIN 账号（V-A9.6） | 未确认 | TEST-1 先在 System → 账号列表（admin 有 `USER_ADMIN`）**只读**查找 viewer/editor 账号；存在则用，不存在则 V-A9.6 记 `NOT TESTED`（理由：本 Feature 零权限改动 + 需新增账号会写 Audit，收益不足） |
| Python Playwright | 可用 | `playwright 1.58.0`（全局 pip，**不在仓库依赖**）；Chromium 构建已缓存（`~/.cache/ms-playwright/chromium-*`） |
| Node / npm | 可用 | `node v22.23.3`、`npm 10.9.9`（`smoke:client` 依赖原生 type stripping，无需额外 flag） |
| 构建脚本 | 存在 | `frontend/package.json`：`typecheck`、`build`（tsc --noEmit && vite build）、`smoke:client`（`node scripts/smoke-client.mjs`） |
| 数据库变更验证 | `NOT_REQUIRED` | `database=false`、零 schema/migration 变更、产品零实体变更；`.pi/skills/data-integrity/SKILL.md` 不适用 |
| 后端全量 pytest | `NOT_REQUIRED`（F033 范围） | `backend/` 零 diff（S-V4）；A9「语义一致」由前端机制级 smoke + 代表性 UI 交互 + 零后端 diff 共同支撑。整体验收不由此拼装 |

可验证性结论：A1–A8、A10 全部为**几何/计算样式可测量**；A9 为**命令 + 交互 + 网络断言**；A8.5 与 A11.3 属**人工视觉/文档判定**，已明确标注，不以自动化结果冒充。**无阻塞项。**

## 6. 回归范围

1. **全量构建与机制级回归**：`typecheck` → `build` → `smoke:client`（当前 322 用例基线，新增用例允许，失败零容忍）。`smoke:client` 覆盖 `api/*` 的 URL/method/body 构造、409/422/403 错误语义与纯逻辑模块，是「请求参数与错误语义不变」的主要机器证据。
2. **UI 交互回归**（人工脚本化）：列表分页/排序/过滤/模糊搜索、详情与关系跳转、Activity、表单 422、删除二次确认 Modal（取消零请求、加载态禁重复）、权限门控、401/403/409/422 呈现、空态与错误区分、登出入口。
3. **布局回归**：四视口 × 11 页面矩阵（§2）。
4. **不变项声明**：删除/释放/恢复语义、两阶段导入、分页/排序/过滤服务端语义、权限矩阵、错误码集合、`components/ui/` 契约、`main.tsx` Ant token —— 均以「零 diff + smoke 通过」证明，不重复执行业务级验收。

## 7. 证据归档

目录：`docs/features/F033/artifacts/`（TEST-1 创建；TD-1 不创建文件）

| 文件 | 内容 |
| --- | --- |
| `run.log` | 执行清单、HEAD、`<F033-base>`、Vite 临时配置说明、时间戳、viewport 参数 |
| `typecheck.log` / `build.log` / `smoke-client.log` | 三条命令完整输出与退出码 |
| `static-checks.log` | S-V1..S-V8 全部命令原文与输出（含 hex 命中行号与所属块判定） |
| `ui-metrics.json` | 40 格矩阵 + 交互项的全部实测数值（视口、页面、指标、实测值、阈值、结论） |
| `console.log` | 各视口 `console` / `pageerror` 收集结果 |
| `{vw}x{vh}-{page}.png` | 每视口代表页面截图，如 `375x667-system-authorizations.png`；A6 另存 `-collapsed` / `-expanded` 两态；A5 另存 `{768,1024}-system-authorizations.png` 对照 |
| Playwright 脚本 | 存放于仓库外临时目录（如 `/tmp/f033_ui_check.py`），运行命令与完整脚本摘要写入 `run.log`，**不新增仓库依赖** |

## 8. 测试命令建议与执行清单

```bash
# 0) 记录基线（协调器提供 F033 起始提交）
cd /home/hanhao/github/47oo/csm && git rev-parse --short HEAD

# 1) 前端全量（cd frontend）
npm run typecheck            2>&1 | tee ../docs/features/F033/artifacts/typecheck.log; echo "exit=$?"
npm run build                2>&1 | tee ../docs/features/F033/artifacts/build.log;     echo "exit=$?"
npm run smoke:client         2>&1 | tee ../docs/features/F033/artifacts/smoke-client.log; echo "exit=$?"   # 断言 "N passed, 0 failed"

# 2) 静态核对（全部输出进 static-checks.log）
grep -nE '#[0-9a-fA-F]{3,8}\b' frontend/src/index.css
grep -nE 'rgba?\(' frontend/src/index.css
grep -rn 'workspace-location' frontend/src
grep -n 'style={{' frontend/src/components/ClusterAuthorizationPanel.tsx
grep -n '\.ant-' frontend/src/index.css
grep -n 'overflow-x' frontend/src/index.css
git -C . diff --stat <F033-base>..HEAD -- frontend/src/main.tsx frontend/package.json frontend/package-lock.json backend docs/api frontend/src/components/ui
git -C . diff --stat <F033-base>..HEAD -- frontend/src

# 3) 浏览器巡检（Playwright Python，仓库外）
#    前端：cd frontend && npx vite --port 15173 --host 127.0.0.1（临时配置 proxy /api/v1 -> 127.0.0.1:18080）
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:15173/
python3 /tmp/f033_ui_check.py 2>&1 | tee docs/features/F033/artifacts/run.log
```

`/tmp/f033_ui_check.py` 执行清单（顺序敏感，一次会话内完成）：

1. 启动 chromium（headless），注册 `console` / `pageerror` / `request` 监听。
2. P1：清 Cookie → `/` → 断言登录页（V-A9.8）→ 截图 → 填写 `#login-username`/`#login-password` → 提交 → 等 `.app-shell`。
3. 对每个视口（1440×900 → 1024×768 → 768×1024 → 375×667）：
   a. P2 概览：V-A2.*、V-A4.*、V-A7.*、V-A10.1/10.2（滚到底实测）、V-A1.1 → 截图。
   b. P3 搜索：输入关键字 → 搜索；V-A6.1/6.2（折叠态高度）→ 截图 `-collapsed`；键盘展开 → V-A6.3/6.6 → 截图 `-expanded`。
   c. P4→P5：V-A1.1/1.2、V-A9.2、V-A9.3、V-A8.4（1440）→ 截图。
   d. P6→P7：同上。
   e. P8、P9（空态）、P10（宽表滚动 V-A1.2）→ 截图。
   f. P11 System → 授权 tab → V-A5.1..A5.5、V-A10.6 → 截图；选中账号后重测 V-A5.5。
   g. 每页复测 V-A1.1 与 V-A4.1/4.2/4.3。
4. 交互补充：V-A3.2/3.3/3.4（Tab 巡检 + skip-link）、V-A9.4（表单 422）、V-A9.5（删除 Modal 取消零请求）、V-A6.5（localStorage 重载）、V-A6.4（降到 1 项仍 disabled）、V-A9.6（若存在非 ADMIN 账号）、V-A9.8（登出）。
5. 输出 `ui-metrics.json` 与 `console.log`，逐项标注 PASS / FAIL / NOT TESTED，并在报告中给出计数汇总。

## 9. 未验证项（TD-1 现状声明）

| 项 | 状态 | 原因 |
| --- | --- | --- |
| A1–A11 全部验证项 | `NOT TESTED` | 本轮为 TEST_DESIGN；实现尚未开始（工作区无 F033 改动），布局类判定不以 build 通过冒充 |
| V-A9.6 非 ADMIN 权限门控 | `NOT TESTED`（条件性） | 测试栈非 ADMIN 账号待确认；零权限改动前提下若无法低成本验证，按 §5 规则降级为 NOT TESTED 并说明 |
| 数据库约束 / Migration | `NOT_REQUIRED` | `database=false`；零 schema 变更；无实体/关系/生命周期改动 |
| 接口契约层验证 | `NOT_REQUIRED`（契约层）/ 已覆盖（消费层） | Contract `NOT_REQUIRED`；仅断言请求参数与响应消费零变化（V-A6.6、V-A9.1 的机制级 smoke） |
| 后端 pytest 全量 | `NOT_REQUIRED` | `backend/` 零 diff；不在 F033 变更面 |
| 需求 §31–33 跨功能整体验收 | `NOT_REQUIRED`（本 Feature） | F033 不新增/修改功能行为；整体验收由项目级任务实际执行，不由本报告的局部结论拼装 |
| A8.5 视觉一致性、A11.3 文档同步 | 人工判定 | 以截图 + 文档 diff 留证，人工确认，不宣称自动化 |

## 10. 缺陷

TD-1 未发现缺陷（无实现可检）。预置关注点 N1–N4 见 §3，属 NOTE 级提醒，不构成阻塞，也不算缺陷。

## Issues / Next

- **Issues**：None。无阻塞项；本设计检查未发现需要 Architect 修订的不可验证条款。
- 已核对差异：架构把 product 的 S7/A10 由「可选」确定为「实现 sticky header（≥1024）」，本设计据此把 A10 设为必测项；其余 DR-F033-01..11 与 A1–A11 一一可映射。
- **Next（协调器）**：架构定稿（核对本 Test Design v1）→ `READY FOR IMPLEMENTATION` → Frontend 实现（写入面限 `index.css` + 4 个呈现层文件）→ 实现报告后调度 TEST-1。TEST-1 需先确认 `<F033-base>` 提交与 Vite 临时代理配置，再按 §8 执行；修复后按影响重测并保留本 TD-1 版本。

GIT: NONE

---

## Test Execution（TEST-1，2026-10-23，v1）

### TE-1 Task / Status / Basis

- **Task**：F033（前端布局与 CSS 质量优化）；分支 `feature/F033-layout-css-refresh`；plan_revision 19；阶段 TEST（独立执行；仅写本报告 TEST 段与 `docs/features/F033/artifacts/`，未修改实现、Schema 或产品规则，未执行 Git 写操作）。
- **Status**：**READY FOR REVIEW**（A1–A11 全部通过；无必须修复缺陷；1 项 LOW（焦点环边缘 3px 被 rail 裁切，TD-1 N1 预判）与 3 项 NOTE 记录；A9 的 2 个条件性子项按 TD-1 §5 预授权降级为 NOT TESTED，理由见 TE-8）。
- **Basis（版本绑定）**：
  - 需求 `docs/product/requirements-v3.md` revision 12 §28（CONFIRMED，运维控制台；不追求复杂视觉效果）；plan revision 19（F033，depends_on F028 DONE，`approved_by=用户 / 2026-10-23`）。
  - `docs/features/F033/product.md` v1（READY FOR ARCHITECT，A1–A11 / S1–S7）。
  - `docs/features/F033/architecture.md` v1 **§9 READY FOR IMPLEMENTATION**（Architect 签核 2026-10-23；DR-F033-01..11；Contract `NOT_REQUIRED`；§9.2 的 R1/375 预算/激活项滚入/token/文档同步修订；§9.3 授权按影响收敛 TD-1 判定式）。
  - `docs/features/F033/test-report.md` TD-1 v1（TEST DESIGN READY；本段核对的 Test Design 版本即该版，口径收敛项见 `artifacts/run.log` §4）。
  - `docs/features/F033/implementation.md` v1（FRONTEND COMPLETE；`main.tsx`/`package.json`/`components/ui`/`backend`/`docs/api` 零 diff）。
  - `docs/architecture/frontend-ui-stack.md` §5 / §5.1（文档同步对象）。
- **未复用声明**：本段 PASS 均由本次实际执行产生；实现报告 §4.3 的自查数据仅用于对照，未作为判定依据。

### TE-2 输入基线与代码版本

| 项 | 值 |
| --- | --- |
| 分支 | `feature/F033-layout-css-refresh` |
| `<F033-base>` | `b741240`（`docs(plan): approve revision 19 for F033 frontend layout`） |
| TEST-1 输入 HEAD | **`3a3f7bd`**（实测 `git rev-parse --short HEAD`，与协调器给定一致）；开始测试前 `git status --porcelain` 为空，结束时工作区仅含本角色产物（`test-report.md` 修改 + `artifacts/` 新增） |
| 工作区变更面（base..HEAD） | 实现 5 文件（`index.css`、`App.tsx`、`pages/HomePage.tsx`、`components/GlobalSearch.tsx`、`components/ClusterAuthorizationPanel.tsx`）+ 文档；`frontend/src` 之外无代码改动 |
| layers / api_required | `frontend=true`、`backend=false`、`database=false`、`api_required=false`；Contract `NOT_REQUIRED` |
| 本段新增产物 | `docs/features/F033/artifacts/**`（79 文件：7 份日志 + 1 份 `ui-metrics.json` + 71 张截图）与本节 |

### TE-3 Environment

详见 `artifacts/run.log` §2。要点：`csmtest` 栈 `127.0.0.1:18080`（`/healthz` 200）+ Vite 5.4.21 开发服 `127.0.0.1:15173`（**仓库外**配置 `/tmp/f033dev/vite.config.mts`，`/api/v1` 代理到 18080）；Node v22.23.3 / npm 10.9.9 / Python 3.12.7 + 全局 Playwright 1.58.0 / Chromium 145.0.7632.6；视口 1440×900、1024×768、768×1024、375×667（`deviceScaleFactor=1`、`isMobile=false`、`reduced_motion=reduce`）。`frontend/` 内未新增任何配置文件或依赖；未使用 SQLite / Mock 替代真实后端。

### TE-4 命令与实际结果

| # | 命令 | 预期 | 实际 | 证据 |
| --- | --- | --- | --- | --- |
| 1 | `git rev-parse --short HEAD` / `git status --porcelain` | `3a3f7bd` / clean | `3a3f7bd` / 空 | run.log §1、TE-2 |
| 2 | `cd frontend && npm run typecheck` | exit 0 | **exit 0**（无输出） | `artifacts/typecheck.log` |
| 3 | `cd frontend && npm run build` | exit 0 | **exit 0**；`index-CLFB8N_k.css 24.01 kB`、`index-BVS4PLL2.js 1,264.51 kB`；仅既有 chunk 体积提示 | `artifacts/build.log` |
| 4 | `cd frontend && npm run smoke:client` | ≥322 passed / 0 failed | **328 passed, 0 failed**（exit 0） | `artifacts/smoke-client.log` |
| 5 | 静态核对（S-V1…S-V8 + 目录范围） | 全部符合 | 全部符合（见 TE-5 A8 与 TE-6） | `artifacts/static-checks.log` |
| 6 | Vite 开发服启动（仓库外 config） | 200 | `/` `/src/main.tsx` `/src/index.css` 均 200 | run.log §2.1 |
| 7 | `python3 /tmp/f033_ui_check.py`（四视口 × 11 页面 + 交互） | 无 FAIL | **records=438：PASS 434 / FAIL 1 / NOT_TESTED 3** | `artifacts/ui-metrics.json`、`console.log`、71 张截图 |
| 8 | `python3 /tmp/f033_a85.py`（V-A8.5 计算值抽查） | 与 token 一致 | 4/4 一致 | `artifacts/a8-5-token-values.log` |

**执行披露**：首轮运行因**脚本自身度量口径**（折叠态可见性用 `getClientRects()`、行数含 Ant 测量行、搜索关键字取空结果、Ant 按钮文案含插入空格）产生 31 个伪失败，已按 TD-1 允许的口径收敛修正（`run.log` §4，逐条列明），第 2、3 轮结果一致；伪失败不进入本报告结论。

### TE-5 验收映射 A1–A11（逐项判定）

图例：**PASS** / FAIL / BLOCKED / NOT TESTED。判定值均来自 `artifacts/ui-metrics.json`。

#### A1 无页面级横向溢出；宽表只在自身容器滚动 → **PASS**

| 验证项 | 判定 | 证据（实测） |
| --- | --- | --- |
| V-A1.1 4 视口 × 10 区段 | **PASS**（40/40） | 全部 `docScrollWidth==clientWidth`、`body` 同；如 1440 全页 `1440/1440`、375 全页 `375/375` |
| V-A1.2 宽表自身滚动（Resources / Audit / IP Addresses） | **PASS**（12/12） | `.ant-table-content` computed `overflow-x=auto`；滚到最右后页面宽度不变：1440 `1102→1177 / docSW 1440→1440`；1024 `686→1568 / 1024→1024`；768 `678→1568 / 768→768`；375 `301→1386 / 375→375` |
| V-A1.3 禁止掩蔽 | **PASS**（40/40） | `html`/`body` computed `overflow-x = visible`（非 hidden） |

#### A2 375 导航+顶部区 ≤200；首屏可见标题与内容；导航入口可达且有当前态 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A2.1 375 壳层高度 | **PASS** | `.app-header` bottom = **176px**（≤200 判定阈值；≤180 的 arch §9.2 预算内） |
| V-A2.2 h1 可见 + 后续内容 | **PASS** | h1 visible、`top=196`（<567）；标题后首个内容块 `top=280`（<667） |
| V-A2.3 nav 触达（≤1023） | **PASS** | 375/768 各 9 项，高度 `[44×9]`（≥43.5），文本非空 |
| V-A2.4 激活项在 rail 可视区 | **PASS** | 375 rail `16..359` / active `16..72`；768 rail `16..752` / active `16..83` |
| V-A2.5 切到最后一项后仍可见 | **PASS** | 375 active `287.8..358.7`（`scrollLeft=369`）；768 active `669.3..752.4`（`scrollLeft=89`），均完全包含 |

#### A3 导航可达；切页后内容区获得焦点；跳转主要内容链接可用 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A3.1 9 项导航逐项切换 | **PASS**（1440/1024/768 各 9/9） | `h1` 与 `main[aria-label]` 同步更新，无错误 |
| V-A3.2 切页后焦点 | **PASS** | 每次切换后 `document.activeElement.id == "workspace-content"` |
| V-A3.3 skip-link | **PASS** | 顺序焦点起点复位后首按 Tab 命中 `A.skip-link`；Enter 后 `hash=#workspace-content`、`activeElement=#workspace-content`、`h1.top 117.7 ≥ header.bottom 69`（未被遮挡） |
| V-A3.4 Tab 40 次 | **PASS** | 被聚焦元素 0 个不可见/`display:none`；序列 `跳转到主要内容 → 概览 → Clusters → …`（第 20 次走出文档末尾到 BODY，属正常回卷，无焦点陷阱） |
| N1 焦点指示 | **PASS（可见）/ LOW（边缘裁切）** | 焦点指示为 `box-shadow: rgba(37,99,235,.35) 0 0 0 3px`（`--csm-focus-ring`）+ `:focus-visible=true`；最左项位于 rail 左边界时左侧 3px 被 `overflow-x:auto` 裁切 → `D-F033-01` |

#### A4 页面标题不与 header 重复表达同一信息 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A4.1 `.workspace-location` | **PASS**（40/40） | DOM 命中 0（另见 `static-checks.log`：`frontend/src` grep 0 命中） |
| V-A4.2 唯一 h1 与期望页名 | **PASS**（40/40） | 每页 `h1` 数量 1，文本 = 资源概览/集群管理/资源台账/网络管理/地址池管理/IP 地址管理/服务登记/审计查询/系统管理 |
| V-A4.3 `main[aria-label]` / `aria-current` | **PASS**（40/40） | aria-label = h1 文本；`[aria-current="page"]` 恰好 1 个且指向对应导航项 |
| V-A4.4 eyebrow | **PASS**（40/40） | `aria-hidden="true"`；1440/1024/768 `display:block`，375 `display:none` |
| V-A4.5 header 文本 | **PASS**（40/40） | header 仅 `admin ADMIN 登出`，不含当前页名 |

#### A5 授权面板 768/375 单列、1024/1440 双栏，无重叠/裁切 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A5.1 单列 | **PASS** | 768 `grid-template-columns=678px`（1 track）、子区垂直堆叠 `543.5–739.5 / 755.5–908.5`；375 `301px`、`604.3–800.3 / 816.3–969.3` |
| V-A5.2 双栏 | **PASS** | 1440 `362px 724px`，c1 `281..643` / c2 `659..1383`，top 同 366；1024 `240px 430px`，c1 `281..521` / c2 `537..967`，top 同 386 |
| V-A5.3 不越界 | **PASS**（4/4） | 两个子 section rect 均在 `.authorization-layout` 内（±1px） |
| V-A5.4 ≤1023 触达 | **PASS** | 账号按钮高度 `[44,44,44]`、宽度占比 `1.0` |
| V-A5.5 授权表自身滚动 | **PASS** | 选中 `shixin`(EDITOR) 后：375 `client 301 / scroll 681 / scrolledTo 380`，页面 `docSW 375→375`；1024 `430/681`；768 `678/681`；1440 `724/724`（无溢出） |
| V-A5.6 无 inline style | **PASS** | `.authorization-layout` 与 `.authorization-user-list` 的 `style` 属性均为 `null`（残留的 `INPUT.ant-input` inline 为 Ant 组件内部实现，不计）；源码 `style={{` 命中 **0**（`static-checks.log`） |
| V-A5.7 功能不变 | **PASS** | 选中账号后呈现「目标账号：shixin（EDITOR / ACTIVE）」与授权区；`.smoke:client` 328 例覆盖 F026/F030 授权语义（409 `already_granted`/`already_revoked`、422、403 文案） |

#### A6 Search 字段组默认折叠、展开后 9 项可用、偏好/默认集/请求参数不变 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A6.1 默认折叠 | **PASS**（4/4） | `open=false`、无 `open` 属性、`checkVisibility` 可见 checkbox = **0** |
| V-A6.2 折叠 < 展开 | **PASS**（4/4） | 1440 `501.5 < 583.3`；1024/768 `525.5 < 657.7`；**375 `677.6 < 997.7`**（较 F028 基线约 945px 展开态下降约 267px） |
| V-A6.3 键盘展开 + 9 项可聚焦 | **PASS**（4/4） | summary 聚焦 + Enter → `open=true`、可见 9；逐个 `focus()` 命中 **9/9** |
| V-A6.4 仅剩 1 项时该项 disabled | **PASS**（375） | `checked=[hostname]`、`disabled=[hostname]`（既有规则保持） |
| V-A6.5 localStorage | **PASS**（375） | 写入 `["role","status"]` 刷新后恢复且仍折叠；写入 `not-json` 后静默回退 5 项默认集 |
| V-A6.6 请求参数不变 | **PASS**（4/4） | 折叠态 `/api/v1/search?q=gpu&deleted=exclude&page=1&page_size=20` 与展开前后**逐字相同**（展开不触发请求） |
| V-A6.7 默认选中集 / 结果行 | **PASS**（4/4） | hostname / resource_type / role / status / cluster 5 项 |
| V-A6.8 summary 文案与结构 | **PASS**（4/4） | 文本 = 原 legend「Resource 行展示字段（仅作用 resource 结果行）」；`font-size 14.4px`；内部 `role="group"` 与说明文案保留 |

#### A7 Dashboard 375 无孤立半列；各断点列数符合基线 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A7.1 375 末卡跨列 | **PASS** | 5 卡 / 2 列，末卡 `301/301 = 1.00`（无半列） |
| V-A7.2 断点列数 | **PASS** | 375→2、768→3、1024→3、1440→5（`grid-template-columns` track 计数） |
| V-A7.3 数值与 API 一致 | **PASS**（4/4） | UI `[9,7,6,1,6]` == `GET /api/v1/dashboard.counts` `{clusters:9, resources:7, bare_metal:6, virtual_machines:1, networks:6}` |

#### A8 语义 token 单一来源；宽表页不被 720px 收窄；浅色表面+蓝色主操作+统一圆角间距 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A8.1 hex 仅在 `:root` | **PASS** | 24 处 hex 命中全部位于行 15–48，`:root {}` 块为行 13–94；`rgb(` 仅 2 处（`--csm-shadow-panel` 51 行、`--csm-focus-ring` 52 行） |
| V-A8.2 token 定义/引用一致 | **PASS** | `--csm-*` 定义 45 / 引用 45；未定义引用 0、定义未用 0 |
| V-A8.3 无 `.ant-*` 选择器 | **PASS** | `grep -c 'ant-' frontend/src/index.css` = **0** |
| V-A8.4 大屏不被 720 收窄 | **PASS** | `.workspace-content` 宽 **1216**（>1200）、`main` computed `max-width=1600px`（非 720px）；Resources 表格可用宽/内容区 = **0.906** |
| V-A8.5 token 计算值抽查 | **PASS**（计算值 4/4） | 页面底色 `rgb(244,246,250)`==`--csm-background`；主操作按钮 `rgb(37,99,235)`==`--csm-primary`；计数卡圆角 `10px`==`--csm-radius-lg`；激活导航底色 `rgb(234,241,255)`==`--csm-primary-soft`。**视觉观感子判定**由 Reviewer 依 71 张截图人工比对（Tester 本轮仅以计算值 + DOM 判定，不宣称审美结论） |

#### A9 既有列表/详情/表单/弹窗/权限/错误行为与 F028 基线一致；smoke 全量通过 → **PASS**（A9.6 与 403 子项按 TD-1 §5 预授权 NOT TESTED，见 TE-8）

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A9.1 typecheck/build/smoke | **PASS** | exit 0 / exit 0 / **328 passed, 0 failed**（基线 322，只增不减） |
| V-A9.2 列表分页/排序/过滤/模糊搜索 | **PASS** | Resources：`q=lu` → URL 含 `q=lu` 且 2 行均命中；`sort=hostname&order=asc`；筛选表单与重置生效；分页渲染「共 7 项 1 20 条/页」。Audit（136 行）：点击第 2 页 → `page=2` 且首行内容变化 |
| V-A9.3 详情/关系/Activity | **PASS** | 资源详情 `资源详情 + Overview + Hardware + Virtual Machines + Interfaces + Services + IP Addresses + 系统信息`；集群详情渲染；IP Addresses 的 Activity 打开后加载 3 行只读流水 |
| V-A9.4 表单校验 | **PASS** | 空表单提交 → 2 条字段级错误（cluster / hostname）且 **POST 0 次**；取消返回列表行数仍 7（零写入） |
| V-A9.5 删除二次确认 | **PASS** | Modal：`删除资源` + 对象 `cn001` + 不级联/软删说明 + 危险样式 `确认删除`（`ant-btn-dangerous`）+ `取消`；取消后写请求 **0**（1440/375 各测一次）；`A10.6` Modal 未被 header 覆盖（命中 `.ant-modal-title`，wrap `z-index:1000`） |
| V-A9.6 非 ADMIN 权限门控 | **NOT TESTED** | 测试栈有 `shixin`(EDITOR)/`viewer27168`(VIEWER) 但**无口令**，且本 Feature 零权限代码改动（S-V7）；见 TE-8 |
| V-A9.7 错误语义 | **PASS（401/409/422）** | 清 Cookie 后切页 → 401 → 回登录页（`.app-shell` 消失、呈现 `.login-main`）；重复 hostname → 1 次 POST 被拒、字段级文案「hostname 与该集群内现存（未删除）资源冲突…」、`resources.total` 7→7；导入「预校验（只读）」坏模板 → 服务端 **422** `IMPORT_INVALID_FILE`（缺失列/未定义列逐项）且「确认导入」不可用。**403 子项 NOT TESTED**（同上，需非 ADMIN 账号） |
| V-A9.8 登出/登录页/boot 态 | **PASS** | 滚到底点「登出」→ 登录页，`.login-main` 宽 **460** 且无横向溢出（375 下 375/375 无溢出）；`.boot-main` 宽 **720（max-width 720px）**、无溢出，boot-loading 与 boot-error（abort `/auth/me` → 「恢复登录态失败：无法连接服务器，请稍后重试」+ 重试）两态四视口均通过 |
| V-A9.9 控制台 | **PASS** | `pageerror` = **0**；`console error` 仅两类且均非新增缺陷：① 有意的错误路径 HTTP 状态（401 启动探测、409、422 用例）② 既有 Ant deprecation warning（`Alert.message`、`Modal.maskClosable`，来源 `components/ui/*` **零 diff**） |

#### A10 桌面粘性 header 滚动后可用且不遮挡内容 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A10.1 sticky | **PASS** | 1440 滚到底 `top=0`、`position=sticky`、`z-index=30`（scrollY 777）；1024 同（scrollY 1179） |
| V-A10.2 用户区/登出可见可点 | **PASS** | 滚到底后 user-box 与登出按钮 rect 均在视口内（top 16 / bottom 52）；真实登出成功回登录页 |
| V-A10.3 焦点不被遮挡 | **PASS** | 滚到底后聚焦内容区首个按钮（「搜索」）：`elementFromPoint` 命中该按钮子元素、`btnTop 308 ≥ header.bottom 69`（1024：332 ≥ 69） |
| V-A10.4 `scroll-padding` 生效 | **PASS** | skip-link 跳转后 `h1.top 117.7 ≥ header.bottom 69`；`html.scroll-padding-top = 80px`（token 驱动，未叠加 144px） |
| V-A10.5 ≤1023 非 sticky | **PASS** | 768 滚到底 `header.top=-899 / position=static`；375 `-1754 / static` |
| V-A10.6 Modal 层级 | **PASS** | 1440/375 打开删除 Modal，标题中心命中 Modal 内部元素；Modal wrap `z-index:1000 > header 30` |

#### A11 typecheck/build 通过；无新增控制台错误；文档同步 → **PASS**

| 验证项 | 判定 | 证据 |
| --- | --- | --- |
| V-A11.1 命令 | **PASS** | `typecheck` exit 0、`build` exit 0（`artifacts/typecheck.log` / `build.log`） |
| V-A11.2 控制台 | **PASS** | 见 V-A9.9（0 pageerror；无 React key/act 警告；既有 deprecation warning 已在实现报告披露） |
| V-A11.3 文档同步 | **PASS** | `docs/architecture/frontend-ui-stack.md` 新增 §5.1：断点表（≥1024/≤1023/≤767/≤480/≥1280）、容器宽度收口、页头层级、语义 token 单一来源、`details` 渐进披露、局部布局；§1/§2/§3/§4 未改。共享组件说明无需改动（`components/ui/*` 零 diff，唯一新增规则为 `.authorization-user-list .csm-button` 作用域尺寸，不改共享原语契约；见 NOTE-03） |

**A1–A11 汇总：11/11 PASS**（不含 TE-8 列出的 2 个条件性子项）。

### TE-6 数据库 / 接口 / 前端 / 集成结果

| 层 | 结果 |
| --- | --- |
| 数据库 | **NOT_REQUIRED**：`database=false`，零 schema/migration 变更（`git diff base..HEAD -- backend docs/database` 无输出且 `backend/` 零 diff）；无实体/关系/状态/唯一性/生命周期变更，`.pi/skills/data-integrity/SKILL.md` 的约束→实现对应表不适用；本轮未连接数据库执行任何断言，也未写入业务数据 |
| 接口（消费层） | **PASS**：Contract `NOT_REQUIRED`（无 Endpoint/参数/Schema/错误码/权限变化）。真实 API 消费验证：搜索 URL 折叠/展开逐字一致（V-A6.6）；列表 `q/sort/order/page/page_size`、审计 `page=2` 查询串符合既有语义；错误语义实测 401 / 409 / 422 真实响应（未用 Mock）；`backend/`、`docs/api/` 零 diff |
| 前端 | **PASS**：4 视口 × 11 页面（Dashboard/Search/Resources/Resource Detail/Clusters/Cluster Detail/Networks/Services/Audit/IP Addresses/System 授权面板 + 登录页 + boot 两态），438 条判定记录，40 格页面矩阵每格 `scrollWidth<=clientWidth` |
| 集成 | **真实前后端集成**（Vite 代理 → csmtest 18080），未以 Mock 代替；只读 + 只读型校验（导入预校验/被拒 409），实测前后 `resources.total` 恒为 7 |

### TE-7 Defects

| ID | Severity | Layer | Location | 证据 / 复现 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D-F033-01 | **LOW** | Frontend（CSS） | `frontend/src/index.css:914-919`：`.app-nav .nav-link:focus-visible { outline-offset:0; box-shadow: var(--csm-focus-ring) }`（注释自称「聚焦环在滚动容器内完整可见（TD-1 N1）」），而 `.app-nav`（≤1023）为 `overflow-x:auto` 且无 inline padding | 768×1024：`Tab` 聚焦 rail 最左导航项，`getComputedStyle(activeElement).boxShadow = rgba(37,99,235,.35) 0 0 0 3px`，元素 `left=16` 与 rail `left=16` 重合 → 左侧 3px 环被裁切（`clipLeft=3`）。TD-1 §3 N1 已预判 | 期望：焦点指示完整可见；实际：最左/最右项在 rail 边界时环外侧 3px 被裁切 | 仅影响最边缘项焦点环的视觉完整度；焦点仍清晰可辨（三边环 + `aria-current` + 背景），A3 可访问性目标不受影响 | Frontend | **否**（建议：`.app-nav` 加 `padding-inline: 4px` 或环形改 `outline-offset:-1px`） |
| NOTE-01 | NOTE | Frontend（CSS） | `frontend/src/index.css:493` `mark { border-radius: 3px; }` | `static-checks.log` / `a8-5-token-values.log`：14 处 radius 中 13 处引用 `--csm-radius-*`，此 1 处为裸元素选择器硬编码 3px（不在 sm/md/lg 阶梯） | 期望：应用自有样式引用 token 阶梯；实际：`mark` 保留 3px | 视觉/可维护性提示；不影响 A8 的 hex/rgb 单一来源判定（V-A8.1 已通过） | Frontend | 否 |
| NOTE-02 | NOTE | 测试环境 | headless Chromium 顺序焦点起点 | 冷启动首按 `Tab` 落在内容区输入/导航项（默认起点落在文档中部）；把起点复位到文档起点后首按命中 `.skip-link` | 期望的「首按 = skip-link」需显式复位起点才可稳定观测 | `skip-link` 的 DOM 位置与 CSS 与基线 `b741240` 逐字相同（`git show` 对照），非 F033 引入；A3 以「DOM 首个可聚焦元素 + 复位后首按命中 + Enter 行为」判定 PASS | 协调器（记录即可） | 否 |
| NOTE-03 | NOTE | 文档 | `docs/architecture/frontend-ui-stack.md` §5.1 | 新增作用域规则 `.authorization-user-list .csm-button`（宽 100% / 左对齐 / `min-height 40→44`）未在 §5.1 文字中点名 | 期望：共享组件相关变更有一句话说明；实际：§5.1 只写「移除组件内 inline 样式」 | 文档完备性提示；共享原语契约未变（`components/ui/*` 零 diff） | Frontend / Architect | 否 |

**无 BLOCKER / HIGH / MEDIUM 缺陷；无用例 FAIL 归因于实现。**

### TE-8 未验证项（NOT TESTED / NOT_REQUIRED）

| 项 | 状态 | 原因与影响 |
| --- | --- | --- |
| V-A9.6 非 ADMIN 角色导航门控（Audit/System 隐藏） | **NOT TESTED** | 测试栈仅有 ADMIN 可用口令（`shixin`/`viewer27168` 口令未知）；新建账号会写 Audit 并污染既有证据口径。TD-1 §5 已预授权该条件性降级。补偿证据：`canAudit`/`canSystem` 门控逻辑零改动（S-V7 人工核对 + `git diff` 仅结构/属性变更） |
| V-A9.7 的 **403** 分支呈现 | **NOT TESTED** | 同上（需非 ADMIN 账号触发越权）；403 文案与 `describeClusterAuthorizationError` 语义由 `smoke:client` 328 例覆盖（机制级） |
| V-A8.5 的「审美观感」子判定 | 部分（计算值 PASS） | 计算值 4/4 与 token 一致；主观视觉比对交 Reviewer（71 张截图已入库），Tester 不宣称审美结论 |
| 数据库约束 / Migration | **NOT_REQUIRED** | `database=false`；零 schema 变更 |
| 接口契约层（Endpoint/参数/Schema/错误码/权限） | **NOT_REQUIRED** | Contract `NOT_REQUIRED`；仅验证消费层零变化 |
| 后端 pytest 全量 | **NOT_REQUIRED** | `backend/` 零 diff（S-V4 实测 0 行） |
| 需求 §31–33 跨功能整体验收 | **NOT_REQUIRED**（本 Feature） | F033 不新增/修改功能行为；整体验收由项目级任务实际执行，本报告不做拼装 |
| 深色模式 / 主题切换 / 动效 | **NOT_REQUIRED** | product §2 明确不做 |

### TE-9 Issues / Next

- **Issues**：D-F033-01（LOW，非必须修复）、NOTE-01…03。无阻塞项、无需求歧义、无设计偏离需要回退。
- **与 TD-1 的差异**：TD-1 §3 的 N1 被实测证实为「边缘 3px 裁切」→ 按 TD-1 规则记 LOW；N2（summary 字号/颜色）实测 `14.4px` 且无丢样式；N3（登录/boot 容器）四视口实测 460 / 720 且无溢出；N4（header offset 精度）实测 `scroll-padding-top=80px`、header 高 69px，V-A10.3/10.4 几何结论成立。
- **凭据卫生**：TD-1 §5 环境表原将测试账号与明文口令并列书写，本轮改为「口令见 `.env.test`，不入库」（仅脱敏，不改变任何 Test Design 结论）；`artifacts/` 全目录按测试口令检索 = **0 命中**。
- **实现报告 §3.1 的 4 条偏差**：本次实测确认后果均符合意图（滚动落点不叠加、`.nav-scroller` 不影响 `.app-nav` 选择器与几何、授权按钮 40/44px、token 补充未造成视觉差异）。
- **Next（协调器）**：`READY FOR REVIEW` → 交 Review（建议同时确认 D-F033-01 是否随本 Feature 修或留待后续；`artifacts/*.log` 被 `.gitignore` 覆盖，需 `git add -f`）。Feature DONE 与合并仍需 Review 批准与真实提交证据，本报告不授予合并权限。

### TE-10 结论

**READY FOR REVIEW**。A1–A11 全部通过（438 条判定记录：PASS 434 / FAIL 1（即 D-F033-01 的裁切子项）/ NOT TESTED 3），无必须修复缺陷；`typecheck`/`build`/`smoke:client` 328 例全通过；真实前后端集成下未发现回归、未写入任何业务数据。

### TE-11 Evidence Index

| 文件 | 内容 |
| --- | --- |
| `artifacts/run.log` | 基线/HEAD、Environment、命令与退出码、TD-1 口径收敛说明、产物清单、副作用声明 |
| `artifacts/typecheck.log` / `build.log` / `smoke-client.log` | 三条命令完整输出与 `exit=`（328 passed） |
| `artifacts/static-checks.log` | S-V1 hex 命中行号与 `:root` 块范围、rgb 白名单、`workspace-location` 0 命中、`style={{` 0 命中、`.ant-` 0 命中、token 定义/引用集合差、`git diff` 零 diff 与改动面 |
| `artifacts/ui-metrics.json` | 438 条判定记录（视口/页面/指标/实测值/阈值/结论） |
| `artifacts/console.log` | console `error`/`warning` 与 `pageerror`（0）分类 |
| `artifacts/a8-5-token-values.log` | V-A8.5 计算值抽查 + 2 项静态观察 |
| `artifacts/{1440x900,1024x768,768x1024,375x667}-*.png` | 71 张截图：11 页面 × 4 视口（含 `search-collapsed`/`search-expanded`、`system-authorizations`/`-selected`、`login`、`boot-loading`、`boot-error`），1440 另含 `resource-create`、`resource-create-409`、`resource-import-422`、`resource-detail-delete-modal`、`ip-addresses-activity`、`logout-login` |

#### 实际执行的命令清单（本段）

```bash
cd /home/hanhao/github/47oo/csm && git rev-parse --short HEAD && git status --porcelain
cd frontend && npm run typecheck        # exit 0
cd frontend && npm run build            # exit 0
cd frontend && npm run smoke:client     # 328 passed, 0 failed, exit 0
grep -nE '#[0-9a-fA-F]{3,8}\b' frontend/src/index.css
grep -nE 'rgba?\(' frontend/src/index.css
grep -rn 'workspace-location' frontend/src
grep -n 'style={{' frontend/src/components/ClusterAuthorizationPanel.tsx
grep -n 'ant-' frontend/src/index.css
grep -n 'overflow-x' frontend/src/index.css
git diff --stat b741240..HEAD -- frontend/src/main.tsx frontend/package.json frontend/package-lock.json backend docs/api frontend/src/components/ui
git diff --stat b741240..HEAD -- frontend/src
git diff --stat b741240..HEAD
cd /tmp/f033dev && ./node_modules/.bin/vite --config /tmp/f033dev/vite.config.mts   # 127.0.0.1:15173
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:15173/             # 200
python3 /tmp/f033_ui_check.py        # records=438 pass=434 fail=1 not_tested=3
python3 /tmp/f033_a85.py             # 4/4 token 计算值一致
```

GIT: NONE
