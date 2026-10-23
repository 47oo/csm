# F033 前端布局与 CSS 质量优化 — Test Report

## Task

- Feature：F033（前端布局与 CSS 质量优化）
- 角色：Tester（Tester 专属工作范围：测试设计；不改业务实现、Schema 或产品规则）
- 本次工作范围：`TEST_DESIGN`（TD-1），只写本文件

## Status

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
| 测试账号 admin / testadmin | 可用 | `POST /api/v1/auth/login` → 200；角色 `ADMIN`；permissions 含 `AUDIT_READ, USER_ADMIN, VIEW_DELETED, WRITE, DELETE_OBJECT, RESTORE, IMPORT, RELEASE_IP, VIEW_ACTIVITY, READ`；`GET /auth/me` → 200 |
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
