# F017 前端 UI 体系改造（Ant Design + Tailwind CSS）— PRODUCT 阶段报告

- **Feature**：F017 前端 UI 体系改造（Ant Design + Tailwind CSS），FEATURE，P0，M8 前端 UI 改造；deps F016。
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`。
- **依据**：`docs/product/requirements-v3.md` revision 4 CONFIRMED（§28、§29、§31、§32、§35.1/§35.3）；`docs/project/project-plan.yaml` plan_revision 5（用户 2026-10-12 批准并同次授权实施）；`docs/project/change-control.md` §4；`docs/architecture/d04-frontend-ui-stack.md`（PROPOSED，Architect 输入）；`docs/project/handoff.md`。

## 1. 目标、使用者、范围、明确排除

### 1.1 目标（用户可观察结果）
在保持既有业务行为与接口契约不变的前提下，将已交付前端（React 18.3 / TypeScript 5.6 / Vite 5.4）的展示层迁移到 **Ant Design 组件库 + Tailwind CSS 样式方案**（§29 revision 4 已 CONFIRMED），并收敛手写全局样式，使运维资源查询与维护控制台在视觉与控件层面的实现与技术选型一致（§28：快速、清晰、高效查询、低操作成本）。

### 1.2 使用者
- **VIEWER**：查询资源、Dashboard / 搜索、Resource Activity（受权限限制）。
- **EDITOR**：在 VIEWER 基础上新增 / 修改 / 导入 / 解绑等维护操作（受权限限制）。
- **ADMIN**：在 EDITOR 基础上删除 / 恢复、账号管理、完整 Audit 查询（受权限限制）。
界面迁移不得改变上述角色的可见能力与操作边界（§23/§25）。

### 1.3 本次范围（实现层）
- 接入 Ant Design 与 Tailwind CSS，按 Architect 在 D04 签核的版本与集成方式（组件库 5.x、Tailwind CSS 4.x 及 Vite 插件、layer 顺序、`ConfigProvider` / `StyleProvider` 装配）。
- 迁移 `frontend/src/pages/` 的 14 个页面与 `frontend/src/components/` 的约 25 个组件（含 `.tsx` 与纯逻辑 `*.ts` 中的 UI 映射部分）到 Ant Design 组件与 Tailwind 原子类。
- 收敛 `frontend/src/index.css` 为最小全局层（按 D04-7）；删除随页面迁移而失效的旧组件样式。
- 保持 `frontend/src/pages/` 与 `components/*.tsx` 之外的边界：`frontend/src/api/`、纯逻辑 `*.ts` 不改行为语义。
- 满足 plan revision 5 F017 acceptance `F-UI-1..7`。

### 1.4 明确排除（本次不做）
- **不新增/修改业务规则**：不改任何领域对象、关系、状态、唯一性、生命周期（§4–§24）。
- **不改后端与数据契约**：无后端路由 / 服务 / 模型 / Schema / Migration / 连接池 / 锁策略变更；`frontend/src/api/` 维持既有 READY Contract（`api_required=false`）。
- **不改部署拓扑**：`Dockerfile`、`nginx.conf`、`compose.yaml`、入口代理与 SPA fallback 语义不变（§30）；仅允许 `dist` 体积变化。
- **不夹带框架升级**：不升级 React 19 / Vite 6 / Ant Design 6 / Tailwind 5（依 D04-3；越界走变更控制）。
- **不新增页面或路由**，不新增设计与交互需求。
- **不以构建通过宣称 UI 正确**：Ant Design v5 运行时样式不在构建产物中，真实渲染正确性由 F018 在真实/等价 Compose 手动复验（D04-8）。
- **不做 §33 跨功能验收与 `project.acceptance` 更新**（归 F018）。

## 2. 需求引用与不改变的业务规则声明

### 2.1 需求引用
| 条款 | 状态 | 与本 Feature 关系 |
| --- | --- | --- |
| §28 前端 | CONFIRMED | 交互基线：Dashboard / Search / Clusters / Cluster Detail / Resources / Resource Detail / Networks / IPAM / Services / Audit / System；列表至少分页、排序、过滤、模糊搜索；「不追求复杂视觉效果」。F017 只更换 UI 技术实现，不降低该基线。 |
| §29 技术栈 | CONFIRMED（revision 4） | 已确认采用 Ant Design + Tailwind CSS，与 React/TS/Vite 组合；明确「不改变 §28 的交互基线与业务规则」；主版本/集成/主题/样式优先级交 Architect 设计签核（§35.3 D04）。 |
| §31 测试 | CONFIRMED | T01–T41 为业务用例，F017 不改其判据；前端类型/构建/smoke 机制级回归须保持通过；真实 Compose 手动复验归 F018。 |
| §32 上线验收 | CONFIRMED | C1–C15 能力不得因 UI 改造降低或删除；F017 不写 PASS，F018 承接复验并更新 `project.acceptance`。 |
| §23 / §25 权限 | CONFIRMED | 权限矩阵在服务端执行；前端门控仅影响呈现，不改服务端语义；401 先于 403。 |
| §22 / T36 Audit | CONFIRMED | Audit 持续保留、无修改/删除/清空入口。迁移不得新增任何 Audit 变更入口。 |
| §35.3 D04 | OPEN（设计输入） | 由 Architect 在 F017 设计 Gate 定稿并签核；不要求用户重复批准，除非产生新业务限制或重大架构变化。 |

### 2.2 不改变的业务规则声明
- 本 Feature 为**展示层技术选型改造**，不触碰任何业务对象、关系、状态、唯一性与生命周期规则。
- API 请求/响应形状、错误码与错误语义、权限判定、乐观锁与版本冲突、软删除/恢复、导入流程等**全部不变**；前端迁移不得绕过或改写这些规则。
- 若迁移过程中发现需要变更任何业务行为，停止并返回需求变更控制，不在本 Feature 内静默决定。

### 2.3 领域分析（resource-domain，结论：无领域影响）
| 对象 | 关系 | 作用域 | 生命周期 | 约束依据及版本 | 未决问题/影响 |
| --- | --- | --- | --- | --- | --- |
| （无新增对象；仅现有展示视图） | 不新增/不改变 | 不适用 | 不适用 | §28/§29 revision 4 | None |

名词「Ant Design 组件」「Tailwind 原子类」为技术实现概念，不升级为业务实体。

## 3. 用户可观察验收标准（可直接作为 test design / 实现依据）

> 所有验收均为**展示层**判据；业务正确性判据沿用 §31/§32 与各 Feature，不在 F017 重定义。

| # | 验收标准（可观察/可执行） | 边界与不适用说明 | 映射 |
| --- | --- | --- | --- |
| F-UI-1 | `frontend/package.json` 声明 Ant Design 与 Tailwind CSS 及其 Vite 插件，版本与 Architect 签核的 D04 版本一致；`package-lock.json` 已提交且与声明一致；在依赖源可达的干净环境执行 `npm ci` 成功（对应本文档 §6 V1/V3）。 | 依赖源不可达时按环境限制如实记录（D04 R1），不得伪造 PASS；版本漂移走变更控制。 | plan F-UI-1 |
| F-UI-2 | 迁移覆盖 `frontend/src/pages/` 全部 14 个页面与 `frontend/src/components/` 全部 `.tsx` 组件；主要交互（登录表单、列表、表单、弹窗、按钮、导航）由 Ant Design 组件与/或 Tailwind 原子类承担，无遗留原生控件承担主要交互；经代码审查 + 真实渲染抽查确认。 | 语义化原生元素（如 `main`/标题/`role="alert"` 无障碍语义）与非交互容器为合理保留项，不判为「遗留控件」；纯逻辑 `*.ts`（无 JSX）不进行 UI 迁移。 | plan F-UI-2 |
| F-UI-3 | §28 列表交互不降低：每个列表页仍可**分页、排序、过滤、模糊搜索**，且触发与迁移前相同的请求参数；API 层行为由 `smoke:client` 原样断言，UI 触发经真实渲染验证。 | 不新增交互能力；不改变查询参数名（如过滤名 `type` 与排序字段名 `resource_type` 不可互换）。 | plan F-UI-3；§28 |
| F-UI-4 | 无业务回归，至少覆盖：(a) 导航与操作按 `permissions` 门控（Audit 需 `AUDIT_READ`；System 需 `USER_ADMIN` 或 `VIEW_DELETED`）与迁移前一致；(b) 各页面 Loading / Success / Empty / Error 四态仍可观察；(c) 401 / 403 / 409（`CONFLICT` / `VERSION_CONFLICT`）/ 422（字段级错误）呈现语义与迁移前一致；(d) `frontend/src/api/` 与后端契约零改动；(e) 无任何 Audit 修改/删除/清空入口新增。 | 判定以可见行为与 `smoke:client` 为准；不要求视觉像素一致。前端门控不替代服务端权限（§23/§25）。 | plan F-UI-4；§23/§25/§31/§32/T36 |
| F-UI-5 | `npm run typecheck`、`npm run build`、`npm run smoke:client` 在新栈下全部通过；`smoke:client` 用例不得删减覆盖（原有断言仍全绿）；`build` 产物 `dist` 含非空 CSS。 | 构建通过不等于 UI 正确（D04-8）；Node 版本与运行方式沿用既有 `scripts/smoke-client.mjs`。 | plan F-UI-5 |
| F-UI-6 | `frontend/src/index.css` 收敛为最小全局层：字体栈、`html/body/#root` 高度与背景、极少数真正跨页规则；无重复或冲突样式；旧页面/组件专用样式随迁移删除。 | 「最小」以 D04-7 定义为准；不整体移除该文件；未完成迁移前不得提前删除仍在使用的旧层（D04 R5）。 | plan F-UI-6 |
| F-UI-7 | 前端构建产物与部署配置未被破坏：经 Nginx 入口前端可达、SPA fallback 正常（直接访问子路径返回应用入口而非 404）。 | 真实部署可达性由 F018 在真实/等价 Compose 复验；F017 仅保证 `Dockerfile`/`nginx.conf`/构建产物不被破坏，不写部署 PASS。 | plan F-UI-7；§30 |

### 3.1 验收边界汇总
- **不适用**：业务对象 CRUD 语义、约束/并发、导入正确性、备份/恢复——判据不变且归各权威 Feature 与 F018；F017 不重定义、不写业务 PASS。
- **不可由构建断言**：Ant Design 运行时 CSS-in-JS 的实际渲染样式与 layer 优先序，须真实渲染手动抽查；未实际执行项不得写 PASS（D04-8）。
- **不设性能验收项**：包体积/首屏增长仅记录（D04 R3），不作为 F017 阻塞或验收判据（§32 无对应项）。
- **回滚**：无 DB/数据/API 变化，回滚只需撤销 F017 提交并重部署上一 `dist`。

## 4. Questions

### 4.1 Blocking Questions
**None。** §28/§29/§31/§32 已 CONFIRMED，无新增业务规则，无需求侧阻塞。

### 4.2 Non-blocking 注意事项（交 Architect / 后续角色）
- **N-1（Architect）**：`docs/architecture/d04-frontend-ui-stack.md` 现为 PROPOSED，须在 F017 设计 Gate 定稿并记录设计签核（版本、集成方式、layer 顺序、主题分工）。产品侧不预设技术方案。
- **N-2（Architect / Tester）**：D04 R1 依赖源不可达时 `npm ci` 可能无法复现；执行者须配置镜像或如实标注未验证，不得以局部结果声称 F-UI-1 通过。
- **N-3（Frontend）**：F-UI-2「无遗留原生控件承担主要交互」的判定以主要交互为准，非交互语义元素为合理保留；具体清单由实现与 Review 按此边界核对。
- **N-4（Tester / F018）**：Ant Design 运行时样式的真实渲染验证、layer 优先序抽查、Nginx 可达性/SPA fallback 复验均在 F018 真实/等价拓扑执行；F017 只保证构建与配置不破坏。
- **N-5（协调器）**：本变更使 F016 的前端构建 / 可达性 / smoke 相关验收证据失效，须由 F017 / F018 重建后再更新 `project.acceptance`（§36 revision 4 记录）；F018 依赖 F017。

## 5. 交 Architect 的输入
- 产品边界：仅展示层技术实现，不改业务规则、API 契约、后端/数据/部署拓扑。
- 验收输入：F-UI-1..7 与本文档 §3 边界，作为 CONTRACT / Test Design 的验收映射基础；API Contract `NOT_REQUIRED`（`api_required=false`）。
- 待定稿：D04（版本/集成/layer/样式优先级/主题分工）由 Architect 签核（N-1）。
- 不新增业务限制；若设计引入新的业务限制或重大架构变化，返回相应裁定。

## 6. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT。**
下一步：ARCHITECTURE 定稿 D04 并记录 F017 设计签核；CONTRACT 记录 `api_required=false` 的最终设计签核；TEST_DESIGN 依 §3 与 D04 验证策略细化可执行步骤与断言，禁止将未执行预期写成 PASS。