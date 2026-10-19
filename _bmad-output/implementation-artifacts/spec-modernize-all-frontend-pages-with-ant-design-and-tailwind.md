---
title: '全站前端迁移至 Ant Design 与 Tailwind CSS'
type: 'refactor'
created: '2026-10-12'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'd6505516a2d0a9bfea3e6000d5bf2034d6cb2e2d'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/docs/product/requirements-v3.md'
  - '{project-root}/docs/project/implementation-rules.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前 14 个页面和 20 个可视组件仍使用原生控件与集中式手写 CSS，重复的表格、表单和反馈交互缺乏一致性，窄屏适配有限。

**Approach:** 全站改用 Ant Design 6 组件呈现交互与数据，使用 Tailwind CSS 4 管理布局、间距和响应式，形成浅色、紧凑、信息密度适中的运维控制台；保留现有顶部导航、业务流程、权限和 API 行为。

## Boundaries & Constraints

**Always:** 覆盖启动/登录、概览、搜索、Dashboard、Clusters、Resources、Networks/IPAM、Services、Audit、System 及其表单和嵌套面板；交互与数据展示使用 Ant Design，Tailwind 负责应用布局和响应式；保持中文、键盘焦点和语义属性；记录新增技术选型。

**Never:** 不修改后端、数据库、API、领域规则、权限、生命周期、版本冲突或审计语义；不引入路由/状态库或新业务行为；错误不能伪装为空，不静默重试，不把未知值转成 0；不以 Tailwind 深层覆盖 Ant Design DOM。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 认证 | 恢复、登录、登出 | 401 回登录且凭据不回显 | 其他失败显示 Alert 并可重试 |
| 列表/搜索 | 筛选、排序、分页、软删 | 保持服务端参数、总数和稳定跳转 | Loading/Empty/Error 分离 |
| 写操作 | 校验、PATCH、删除/恢复 | 保持 null/默认/单位/只读和二次确认语义 | 字段错误与冲突明细完整；不自动覆盖 |
| 导入/响应式 | 两阶段导入；桌面/窄屏 | 整批成功/回滚；导航可达、表格可滚动 | 无部分成功语义；内容不截断 |

</frozen-after-approval>

## Code Map

- `frontend/src/{main.tsx,index.css}`、`frontend/vite.config.ts` -- 全局主题、中文 locale、Tailwind Vite 接线。
- `frontend/src/App.tsx`、`frontend/src/pages/{Login,Home}Page.tsx` -- 认证状态机和无路由导航；保留状态流及权限门控。
- `frontend/src/pages/*.tsx` -- 14 个页面的列表、详情、表单、Activity 与管理流程。
- `frontend/src/components/*.tsx` -- 20 个可视组件；复用新的 `components/ui/` 展示原语。
- `frontend/src/api/*.ts`、`frontend/src/components/*.ts` -- 已验证的请求、校验和载荷逻辑，原则上不改；`scripts/smoke-client.mjs` 是 264 项回归基线。

## Tasks & Acceptance

**Execution:**
- [x] `frontend/package*.json`、`vite.config.ts`、`src/{main.tsx,index.css}` -- 接入 Ant Design/图标/Tailwind，定义中文浅色紧凑主题和响应式基础层。
- [x] `frontend/src/components/ui/*.tsx` -- 提取卡片、反馈、标签、分页和危险操作确认等共享展示原语。
- [x] `frontend/src/{App.tsx,pages/*.tsx,components/*.tsx}` -- 分域迁移全部壳层、页面、表单和嵌套面板，保留现有 state/effect/权限/请求逻辑。
- [x] `docs/architecture/frontend-ui-stack.md` -- 记录用户确认的 UI/CSS 选型、职责边界、版本与兼容策略。

**Acceptance Criteria:**
- Given 任一角色访问任一页面, when 页面处于加载、成功、空或失败, then 使用统一 Ant Design 反馈且权限和数据行为不变。
- Given 用户在桌面或窄屏操作, when 内容超宽, then 布局自适应、表格可滚动且操作可键盘访问。
- Given 服务端返回 401/403/409/422 或生命周期冲突, when 前端处理, then 原跳转、字段提示、冲突明细和禁止静默重试规则保留。
- Given VIEWER/EDITOR/ADMIN 登录, when 浏览和操作, then 控件继续严格按服务端 permissions 显示。
- Given 改造完成, when 构建、264 项 smoke 和全页浏览器巡检结束, then 全部通过且无原生风格残留或控制台错误。

## Implementation Notes

- Ant Design 6 统一承载 Button、Input、Select、Checkbox、Table、Card、Alert、Empty、Spin、Tag、Pagination、Descriptions 等交互与反馈；共享适配层保留既有表单事件、服务端分页和表格声明式调用方式。
- Tailwind CSS 4 通过 Vite 插件接入，仅管理应用自有布局、间距、断点与横向滚动；未使用选择器深层覆盖 Ant Design 内部 DOM。
- 14 个页面及 20 个可视组件已迁移；认证状态机、无路由顶部导航、permissions 门控、API 调用、字段校验、PATCH/null 语义和冲突处理均保持原实现。
- 旧 `status-*`、`badge-*`、原生按钮/输入/选择器/textarea/table 以及裸 `panel` section 已从 TSX 清除；状态、空态、错误、成功及危险确认均通过共享 Ant Design 原语呈现。

## Spec Change Log

## Review Triage Log

| ID | Verdict | Evidence / Route |
|---|---|---|
| V1 | low | Select/checkbox 适配缺少持久化交互测试的风险属实；最终 Chromium 已实际选择 `INACTIVE`、提交并从 201 响应及详情确认值未丢失。仓库没有既有浏览器测试基础设施，新增整套框架相对该已验证风险过重，拒绝额外复杂度。 |
| V2 | medium | DataTable/ServerPagination 原先只做页面可达检查，证据不足；已补跑真实数据检查，验证 20/20/50 行渲染、排序请求、翻页、页大小变化及行操作，问题按 verification patch 关闭。 |
| V3 | medium | 原巡检正则确实可能漏掉“加载…失败”，且 `requestfailed` 不覆盖 HTTP 500；临时巡检已增加所有 `>=400` 响应检查及宽松失败文案匹配，并通过路由注入 500 验证 Alert 与重试恢复。 |
| B1 | false | 当前 Select 调用均为受控 state，未使用 `required` 或浏览器 FormData；提交处理显式读取 state，`name` 仅用于合成事件，审查所述原生约束丢失在现有调用点不可达。 |
| B2 | false | 现有五个 checkbox 调用只使用 id/name/checked/disabled/onChange；这些属性均保留，Ant CheckboxChangeEvent 的 target 提供实际读取的 checked，未发现被丢弃调用属性。 |
| B3 | false | 当前 19 个 DataTable 的 th/td 未使用 scope/aria-sort/headers/span/style/事件属性；排序 Button 和单元格 class/children 均被适配器保留，所述坏结果在现有调用点不发生。 |
| B4 | medium | `.table-wrap` 与 Ant Table 双重持有 overflow 会产生嵌套滚动；已移除外层 overflow，由 Ant Table 单独负责横向滚动。 |
| B5 | medium | 三个 Card 字符串标题确实丢失 h2；SurfaceCard 现将字符串 title 包装为语义化 h2，并保持 Card 标题样式。 |
| B6 | medium | Ant Alert 默认 `role=alert` 会让静态说明过度播报；Info 改为 `note`、Success 改为 `status`，Error/Warning 保留 `alert`。 |
| B7 | medium | 删除/释放/停用入口及确认按钮原先视觉中性；Button 新增显式 danger API，所有破坏性调用点已标记，恢复操作保持普通样式。 |
| B8 | medium | 全局 `popupMatchSelectWidth=false` 可能让长选项逃出窄屏；已恢复匹配触发器宽度，390px 全页巡检无页面级横向溢出。 |
| B9 | low | 缺少提交到仓库的 UI 测试是开发者回归风险，但仓库无现成 JSX/浏览器测试基础；本次以真实 Chromium 的角色、全页、表单、表格、分页、错误重试检查补足，新增框架成本不成比例，拒绝。 |
| B10 | low | 生产构建确有 1.17 MB chunk 警告，但 gzip 为约 358 KB，未测得启动故障；按页面懒加载会改变当前无路由壳层并显著扩展变更，作为后续性能优化而非本次缺陷，拒绝。 |
| B11 | low | Tailwind 与 Vite 插件属于构建工具，已移至 devDependencies；`@ant-design/icons` 同时是 antd 的同版本传递依赖且执行任务明确要求图标接入，移除直接声明不会减少安装内容，故该部分不采纳。 |
| B12 | low | 生成 manifest 含本机绝对路径属实；整个未跟踪 `_bmad` 渲染目录不是产品交付物，已删除，最终 diff 不再包含该路径。 |
| B13 | medium | `_bmad` 渲染脚本/提示与前端改造无关并显著污染审查；已删除完整临时目录。 |
| E1 | false | `memlog.py` 并发更新主张仅针对已删除的临时 `_bmad` 工具；最终改动不存在该文件或运行入口，因此本交付无法触发所述结果。 |
| E2 | false | `memlog.py` 可预测临时文件主张仅针对已删除的临时 `_bmad` 工具；最终改动不存在该文件或运行入口。 |
| E3 | false | `memlog.py` 字段校验主张仅针对已删除的临时 `_bmad` 工具；最终改动不存在该文件或运行入口。 |
| E4 | false | `memlog.py` 日志换行主张仅针对已删除的临时 `_bmad` 工具；最终改动不存在该文件或运行入口。 |
| E5 | false | `setup.py` 输出目录穿越主张仅针对已删除的临时 `_bmad` 工具；最终改动不存在该文件或运行入口。 |
| E6 | false | `setup.py` 非字符串配置主张仅针对已删除的临时 `_bmad` 工具；最终改动不存在该文件或运行入口。 |
| E7 | false | `setup.py` 文件/符号链接目标主张仅针对已删除的临时 `_bmad` 工具；最终改动不存在该文件或运行入口。 |
| E8 | medium | 与 B5 相同的标题语义缺失独立记录；已由 SurfaceCard 的字符串 h2 修复。 |
| E9 | medium | 新增 page size 10 改变既有 20/50/100 行为；ServerPagination 已恢复原三档并通过真实翻页/页大小检查。 |

## Design Notes

采用 Ant Design 6.6.x 与 Tailwind CSS 4.3.x。Ant Design 负责有状态交互，Tailwind 仅作用于应用自有布局；保留 React state 驱动的顶部导航。

## Verification

**Commands:**
- `cd frontend && npm run typecheck` -- strict TypeScript 无错误。
- `cd frontend && npm run build` -- Vite/Tailwind/Ant Design 生产构建成功。
- `cd frontend && npm run smoke:client` -- 264 passed, 0 failed。
- `docker build -t csm-frontend-ui ./frontend` -- `npm ci` 与镜像构建成功。
- `docker compose --env-file .env.ui-verify -p csm-ui-verify up -d --build` -- 隔离环境 migration/bootstrap/backend/frontend/nginx 全部启动，backend healthy，入口 HTTP 200。
- `node /tmp/csm-ui-browser-check.js` -- ADMIN 登录后巡检概览、Clusters、Resources、Networks、IP Pools、IP Addresses、Services、Audit、System；1440×1000 与 390×844 均无控制台错误、请求失败、加载失败或页面级横向溢出。
- `node /tmp/csm-ui-role-check.js` -- VIEWER/EDITOR 权限导航与 Clusters 写入/软删控件门控通过；EDITOR 创建页可达。
- `node /tmp/csm-ui-interaction-check.js` -- Ant Select 选择 `INACTIVE` 后创建响应与详情一致；50 条真实数据下验证表格行、排序、20 行翻页、50 行页大小、查看操作，以及注入 HTTP 500 后 Alert/重试恢复。
- `rg ... frontend/src --glob '*.tsx'` 与 `git diff --check` -- 无原生交互/旧状态样式残留，无空白错误。
- `npm audit --omit=dev` -- 未得到审计结论：配置镜像不实现 npm audit API；切换 npm 官方 registry 后 TLS 在握手前断开。未据此声称依赖无漏洞。

**Manual checks (if no CLI):**
- 已用真实 Chromium 自动覆盖三种角色导航与权限门控、ADMIN 全导航、EDITOR 创建入口，以及桌面/窄屏布局；关键 CRUD、导入、删除/恢复和错误信封语义由 264 项 client smoke 覆盖。
