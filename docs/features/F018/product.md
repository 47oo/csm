# F018 前端改造后一期整体验收复验 — PRODUCT 阶段报告

- **Task**：F018（FEATURE，P0，M8 前端 UI 改造，deps F017）— Product Manager，PRODUCT 阶段。
- **Status**：`READY FOR ARCHITECT`。
- **Basis**：
  - `docs/product/requirements-v3.md` **revision 4** CONFIRMED：§28 / §29 / §30 / §31 / §32 / §33 / §35 / §36。
  - `docs/features/F017/architecture.md`（CONTRACT 定稿）§5 V5–V7；`docs/features/F017/review-report.md` Follow-ups（R-1/R-5、D-4 视觉确认）。
  - `docs/features/F016/test-report.md`（整体验收、等价替代栈方法与差异声明）。
  - `docs/project/project-plan.yaml` F018 条目（plan_revision 5）；`docs/architecture/d04-frontend-ui-stack.md` v2 FINAL / CONFIRMED。
- **领域影响**：F018 为验收复验型 Feature，**不新增/变更任何对象、关系、状态、唯一性或生命周期规则**；仅复核既有已确认证据。

## 1. 目标

在**真实 / 等价部署拓扑**（§30：Nginx → Frontend / FastAPI → PostgreSQL）下，复核 F017 前端改造后 §31 / §32 / §33 中**与前端相关的证据**：重跑前端 `typecheck` / `build` / `smoke:client`，确认 Nginx 入口可达性与 SPA fallback，验证 AntD 运行时渲染、layer 优先序、preflight 影响、权限门控、四态、错误呈现、列表交互，并承接更新 `project.acceptance`。

## 2. 范围（复验项清单）

| # | 复验项 | 来源 |
| --- | --- | --- |
| R-1 | 前端 `npm run typecheck` / `npm run build` 退出码 0，`dist` 含非空 CSS；`npm run smoke:client` 全绿且用例数不少于 F017 的 264 | §31 / F-UI-5；F017 V2/V3 |
| R-2 | 经 Nginx 入口 `/` 200 且含应用入口标记；直接访问前端子路径（如 `/clusters`）返回应用入口而非 404；`/api/v1/health/ready` 经 Nginx 200 | §30 / F-UI-7；F017 V7 |
| R-3 | 真实浏览器：Tailwind utility 覆盖 AntD、preflight 未破坏布局、AntD 组件样式正确（`StyleProvider layer` 生效）；layer 优先序 `base → antd → utilities` | §29 / F-UI-2/6；F017 V6、D04-7 |
| R-4 | 权限门控：Audit 入口需 `AUDIT_READ`、System 入口需 `USER_ADMIN` 或 `VIEW_DELETED`，无权限时不显示入口且不可访问 | §23 / F-UI-4a；F017 V5 |
| R-5 | 页面 Loading / Success / Empty / Error 四态在各列表与详情可见且正确 | §28 / F-UI-4b；F017 V5 |
| R-6 | 401 / 403 / 409 / 422 前端呈现语义与迁移前一致 | §23 / F-UI-4c；F017 V5 |
| R-7 | Audit 页面无修改 / 删除 / 清空入口（含 ADMIN） | §22 / F-UI-4e；F017 V5 |
| R-8 | §28 列表分页 / 排序 / 过滤 / 模糊搜索可用；触发参数与迁移前一致（`type` 过滤名、`resource_type` 排序字段不可互换） | §28 / F-UI-3；F017 V5 |
| R-9 | §32 C1–C15 经真实 HTTP 数据层 + UI 呈现复核；§33 查询场景界面呈现复核；C15 为实际汇总（非局部拼接） | §32 / §33；F016 A5/A6 |
| R-10 | F017 R-1 / D-4 视觉确认：ClustersPage 列对齐修正后，抽查其余页面无同类列错位 | F017 review-report §3/§6 |

## 3. 明确排除

- **不改业务规则、不改产品/领域语义**；§31 T01–T41 与 §32 后端/数据库/API 语义由 F001–F016 已确认证据承载，本 Feature 不重定义。
- **不改代码**（前端 / 后端 / 数据库 / 部署），除验收所需的**测试脚本与夹具**外不产生实现改动。
- **不复验、不回写 F001–F016 后端 / 数据库 / API / 备份证据**（§31 T01–T41 后端侧、§32 C14 / T36 备份、并发与约束证据）。
- 不新增业务规则、不引入新对象/字段/状态/唯一性/生命周期规则；不得把未实际执行项写成 PASS。
- 不进行无关重构、框架升级或 UI 再设计。
- 浏览器 E2E harness 的引入需先返回 Architect 评估，不在本 Feature 自行决定。

## 4. 可观察验收标准

| ID | 可观察判据（PASS/FAIL） |
| --- | --- |
| AC-1 | `typecheck`/`build` 退出码 0 且 `dist` CSS 非空；`smoke:client` 输出 `N passed, 0 failed` 且 `N ≥ 264`（无断言删减）。 |
| AC-2 | 经 Nginx 入口：`/healthz`=200、`/api/v1/health/ready`=200、`/`=200 含入口标记；任意前端 SPA 子路径=200 且返回同一入口（fallback 生效）。 |
| AC-3 | 真实浏览器中 Tailwind utility 覆盖 AntD、preflight 未破版、AntD 组件样式正确；layer 顺序与 D04-7 一致，判据附截图或等价证据。 |
| AC-4 | 无 `AUDIT_READ` 时 Audit 入口不显示；无 `USER_ADMIN`/`VIEW_DELETED` 时 System 入口不显示；带权限时可见可访问。 |
| AC-5 | 每个被抽查列表/详情分别呈现 Loading、Success、Empty、Error 四态，与实际请求状态一致。 |
| AC-6 | 触发 401/403/409/422 时前端呈现与迁移前语义一致（如 409 `VERSION_CONFLICT` 提示、401 重登录）。 |
| AC-7 | Audit 界面无修改/删除/清空控件与入口；仅查询能力。 |
| AC-8 | 分页/排序/过滤/模糊搜索可用，请求参数（`type` 过滤名、`resource_type` 排序字段等）与迁移前逐一致。 |
| AC-9 | §32 C1–C15、§33 Q1–Q9 前端相关呈现复核有真实证据；C15 为实际执行汇总，缺证据项标 NOT TESTED。 |
| AC-10 | ClustersPage 列对齐修正无误；抽查其余页面无同类列错位。 |

## 5. 环境与限制

- 首选 `docker compose up -d`（§30）；若镜像源不可达（同 F016 环境限制），改用 F016 已记录的**等价替代栈**（Nginx → Frontend(dist) / FastAPI → PostgreSQL，独立端口/库），并**如实记录差异声明，不得以替代栈冒充 Compose**。
- 无浏览器 E2E harness 时：DOM 相关判据（AC-3/4/5/6/7/8/10）须以真实 HTTP 数据正确 + `build`/`smoke:client` 为机制证据，未在真实渲染中执行者标 **NOT TESTED**，不得冒充 PASS；R-3 的运行时样式须真实渲染验证（D04-8）。
- 验收数据与断言仅引用既有 READY Contract / 已确认需求，不新增规则。

## 6. Blocking Questions

None。无新增业务歧义；§35 已关闭问题不重列为 OPEN；现有技术设计由专业角色在已批准边界内执行。

## 7. 结论

无阻塞、无新增业务规则、无代码/契约/Schema 变更；F018 复验项均可映射到可观察判据。**Status：`READY FOR ARCHITECT`。**