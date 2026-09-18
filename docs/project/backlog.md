# CSM Backlog

> Status: DRAFT（待用户确认）
> Source of Truth: `docs/project/project-plan.yaml`
> 本文件是人类可读视图，不构成机器状态的唯一来源。
> Last updated: 2026-09-16（OPEN-004 已裁定并固化为 R-BM-007；F002 解除 DRAFT → READY；M1 完成）

需求基线：`docs/product/requirements.md`（CONFIRMED BASELINE；2026-09-15 架构阶段产品裁定：OPEN-005 关闭，固化为 R-IMPORT-004 All-or-Nothing）。
产品领域模型：`docs/product/domain-model.md` / `domain-model.yaml`（已于 2026-09-15 同步，OPEN-005 已关闭）。
架构：`docs/architecture/csm-v1-foundation-architecture.md`（READY FOR IMPLEMENTATION），
ADR-0001 ~ ADR-0005（全部 ACCEPTED），`docs/api/api-conventions.md`（READY）。
已完成 **F012（项目基础框架与运行环境）**、**F001（Cluster 登记与管理）**、**F013（本地账号认证与会话）**、**F014（逻辑删除与数据一致性治理）** 与 **F015（内网部署与运行环境）**，均已合入 `develop`；M1「平台基础可运行」完成。
不再是无实现项目：`backend/` 与 `frontend/` 已存在，`clusters` 表已由 F012 基线建立并冻结，
认证基座已由 F013 建立，统一软删服务与 `DELETE /api/clusters/{id}` 已由 F014 建立，
生产内网部署产物（`docker-compose.prod.yml` / nginx / 部署文档）已由 F015 建立。
**当前无 READY Feature**：F002 受 OPEN-004 阻塞，其余均直接 / 间接依赖 F002。

状态取值：`DRAFT` / `BLOCKED` / `READY` / `IN_PROGRESS` / `IN_REVIEW` / `DONE`。

DRAFT / BLOCKED 判定规则（权威定义见 `project-plan.yaml` 顶部与 `planning_status.status_decision_rules`）：

- `DRAFT`：存在未解决的产品问题，且该问题直接影响该 Feature 自身 scope 或 acceptance_criteria 的定稿（自身数据模型 / 字段 / 唯一性 / 生命周期 / 校验策略等产品语义尚未确认）。
- `BLOCKED`：Feature 的 scope 与 acceptance_criteria 已可定稿，仅被 architecture / database decision、未 DONE 的 `depends_on` 或环境阻塞。
- 两类原因同时存在时取 `DRAFT`，并在 `blocking` 中同时列出两类原因；仅被其他 Feature 的产品决策间接影响、不改变本 Feature 交付边界时仍按 `BLOCKED`。

`READY` 需同时满足：产品范围明确、AC 可定义、无阻塞产品问题、无阻塞架构决策、所有 `depends_on` 已 DONE、项目基础能力支持进入 Feature Workflow。

架构已批准、DEC-008 ~ DEC-016 全部裁定后，**F012 为项目第一个 READY Feature**。

---

## 汇总

| 维度 | 值 |
|---|---|
| Feature 总数 | 14 |
| P0 | 7（F001, F002, F009, F012, F013, F014, F015） |
| P1 | 7（F004, F005, F006, F007, F008, F010, F011） |
| P2 | 0 |
| READY | 1（F007） |
| BLOCKED | 3（F008, F010, F011） |
| DRAFT | 0 |
| DONE | 10（F012, F001, F013, F014, F015, F002, F009, F006, F004, F005） |
| Blocking Decisions (OPEN) | **0**（DEC-008 ~ DEC-016 全部裁定；DEC-001 ~ DEC-014 无 OPEN 项） |

产品冲突 DEC-001 ~ DEC-014 已全部裁定，DEC-015 / DEC-016 为新裁定的规模与部署决策，均不作为项目级阻塞（见下方状态表）。

---

## E01 基础资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F001 | Cluster 登记与管理 | P0 | **DONE** | F012 | — | requirements.md §7, §22 |
| F002 | BareMetal 登记与管理 | P0 | **DONE** | F001 | — | requirements.md §8, §22 |

## E02 网络资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F004 | NetworkInterface 管理 | P1 | **DONE** | F002 | — | requirements.md §11 |
| F005 | IPAddress 管理 | P1 | **DONE** | F004 | — | requirements.md §12 |

## E03 虚拟资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F006 | VirtualMachine 登记与管理 | P1 | **DONE** | F002 | — | requirements.md §9 |
| F007 | Container 资源模型与登记 | P1 | READY | F006, F002 | — | requirements.md §10 |

## E04 服务资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F008 | Service 资源管理与 Cluster 共享关联 | P1 | BLOCKED | F001, F002, F006, F007 | 依赖 F002/F006/F007 未 DONE | requirements.md §14, §15 |

## E05 资源查询与视图

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F009 | Cluster 视角资源查询 | P0 | **DONE** | F001, F002 | — | requirements.md §16 |
| F010 | 资源详情与关联查询 | P1 | BLOCKED | F001, F002, F004, F005, F006, F007, F008 | 依赖多个资源 Feature 未 DONE | requirements.md §15, §16 |

## E06 数据导入

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F011 | Excel 模板与批量导入 | P1 | BLOCKED | F001, F002, F004, F005, F006, F007, F008 | 依赖多个资源 Feature 未 DONE | requirements.md §18 |

## E07 平台基础能力（ENABLER）

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F012 | 项目基础框架与运行环境 | P0 | **DONE** | — | — | requirements.md §4, §5, §21, §24, §25 |
| F013 | 本地账号认证与会话 | P0 | **DONE** | F012 | — | requirements.md §19 |
| F014 | 逻辑删除与数据一致性治理 | P0 | **DONE** | F012 | — | requirements.md §17, §21 |
| F015 | 内网部署与运行环境 | P0 | **DONE** | F012, F013 | — | requirements.md §20 |

**F003（Rack 与 U 位位置管理）已于 2026-09-15 依用户决策删除，不再属于 V1 范围。**

**F012 为什么是 READY**：无 `depends_on`；产品范围明确（显式资源类型建模、通用校验与错误处理基座）；AC 可定义；
无阻塞产品问题；架构/数据库/标识/API 契约决策 DEC-009 / DEC-010 / DEC-011 / DEC-014 均已 RESOLVED
（ADR-0001 ~ ADR-0003 `ACCEPTED`），Blocking Architecture Decision = 0；
架构 Handoff = `READY FOR IMPLEMENTATION`，API 契约 = `READY`。

---

## Blocking Decisions（摘要）

| ID | Type | 影响 Feature | 状态 | 说明 |
|---|---|---|---|---|
| DEC-001 | product | F001, F002, F009, F010, F011 | RESOLVED | V1 不含 DataCenter（requirements.md §6） |
| DEC-002 | product | F011 | RESOLVED | Rack / U 位已从 V1 删除，F003 一并删除 |
| DEC-003 | product | F008, F010, F011 | RESOLVED | 方案 C：Service 必选绑定运行载体（R-SVC-005/006） |
| DEC-004 | product | F006, F007, F010, F011 | RESOLVED | VM→BareMetal 绑定必选；R-VM-005（2026-09-16 用户裁定） |
| DEC-005 | product | F007, F010, F011 | RESOLVED | Container 粒度与绑定（R-CONTAINER-001~005，2026-09-16 用户裁定） |
| DEC-006 | product | F004, F005, F006, F007, F008 | RESOLVED | 方案 B：仅 BareMetal 有状态 |
| DEC-007 | product | F001 | RESOLVED | 已确认为 R-CLUSTER-005 |
| DEC-008 | architecture | F006, F007, F008 | RESOLVED | ADR-0002：`bare_metal.status` 显式列 + CHECK，不设通用 status 表 |
| DEC-009 | architecture | 全部 Feature | RESOLVED | ADR-0001 ACCEPTED：Python/FastAPI/SQLAlchemy + Vue 3 技术栈 |
| DEC-010 | database | F004, F005, F006, F007, F008, F012, F015 | RESOLVED | ADR-0002 ACCEPTED：PostgreSQL + Alembic |
| DEC-011 | architecture | 全部资源 Feature | RESOLVED | ADR-0003 ACCEPTED：BIGINT `id` + Cluster `by-name` 只读别名 |
| DEC-012 | database | F014 及资源 Feature | RESOLVED | ADR-0004 ACCEPTED：`deleted_at` + partial unique index |
| DEC-013 | architecture | F013, F015 | RESOLVED | ADR-0005 ACCEPTED：服务端会话 + HttpOnly Cookie + Argon2id |
| DEC-014 | architecture | 全部 API 相关 Feature | RESOLVED | ADR-0003 ACCEPTED：Problem 风格错误信封 + 稳定 `code` |
| DEC-015 | process | F012, F015 | RESOLVED | 规模：资源总量约 10⁵、并发约 50（用户裁定） |
| DEC-016 | architecture | F015 | RESOLVED | 部署打包：docker-compose（用户裁定，ADR-0001） |

**无 OPEN 项。** DEC-004 / DEC-005 已于 2026-09-16 由用户裁定并固化为 R-VM-005 / R-CONTAINER-001~005，不再是 Feature 级 `open_questions`；
F001 / F002 / F006 / F007 的关键产品问题已全部关闭。

完整 question 文本与 resolution 见 `docs/project/project-plan.yaml` 的 `decisions_required`。

---

## Open Questions（未确认需求，不升级为 Feature / 验收条件）

| OPEN | 关联 Feature | 内容 | 状态 |
|---|---|---|---|
| OPEN-001 | F006 | VirtualMachine 字段范围及其标识与唯一性规则 | **已关闭（R-VM-004/005/006）** |
| OPEN-002 | F007 | Container 管理粒度 | **已关闭（R-CONTAINER-001 ~ 005）** |
| OPEN-003 | F008 | Service 字段 | **已关闭（R-SVC-007/008/009）** |
| OPEN-004 | F002 | BareMetal 硬件字段 | **已关闭（R-BM-007）** |
| OPEN-005 | F011 | Excel 部分成功导入策略 | **已关闭（All-or-Nothing，固化为 R-IMPORT-004）** |
| OPEN-006 | — | 虚拟资源运行时集成 | **已关闭（已确认排除）** |

另有 2 项原项目级产品决策已转为 Feature 级 `open_questions`（不再计入项目级阻塞）：

（DEC-004 / DEC-005 已关闭，见上。）

---

最后更新依据：用户对 DEC-009 ~ DEC-014（ADR-0001 ~ ADR-0005 ACCEPTED）、DEC-008（ADR-0002）、
BQ-1 规模、BQ-3 导入语义（OPEN-005 → R-IMPORT-004）、BQ-4 部署打包的裁定，
以及已批准的架构 Handoff（`READY FOR IMPLEMENTATION`）与 API 契约（`READY`）。

---

# 2026-09-18 增补：F017（应用外壳侧边栏导航）

> **更新（2026-09-18）：DEC-020 已裁定「做」，F017 由 DRAFT 转 READY，M7 开始执行。**
>
> ⚠️ **本文件正文仍严重陈旧，请先阅读下面的「漂移声明」。**

## 漂移声明（重要，不掩盖）

本文件的既有正文（上方「汇总」「E01–E07」各表、`Last updated: 2026-09-16` 等）**停留在 M1 完成时期**，
与 `docs/project/project-plan.yaml` 已严重不一致，例如它仍写着：

| 本文件的陈旧陈述 | 计划 YAML 的实际情况 |
|---|---|
| `Feature 总数 14` | **16**（含 F016、F017） |
| `DONE 10` | **14 DONE + 1 CANCELLED** |
| `READY 1（F007）` / `BLOCKED 3（F008, F010, F011）` | `READY 0 / BLOCKED 0`；F008 / F010 已 DONE，F011 已 CANCELLED |
| `M1 完成` | **M1–M6 全部 DONE**，M7 待用户确认 |
| 正文未提及 F014 / F015 / F016 / F017 的实际结局 | 见计划 YAML 的 `planning_status.done_rationale` |

**该漂移是既有的、与本次规划无关**（M2–M6 期间这三份人类视图均未被同步刷新）。
本次**只追加本节并纠正上表所述的误导性结论**，**未**静默重建全文——按 `AGENTS.md` §5
「不得顺便进行无关的大范围重构」，且静默重写会掩盖漂移本身。
**是否全文重建本文件待用户决定**（见计划 `planning_status` 与本次规划摘要）。

## 新增 Feature

| ID | Feature | Epic | Priority | 状态 | depends_on | 阻塞原因 |
|---|---|---|---|---|---|---|
| F017 | 应用外壳侧边栏导航 | E07 | P2 | **READY**（DEC-020 已裁定「做」） | F012, F013, F001, F002, F004, F005, F006, F007, F008, F010（均 DONE） | 无阻塞（唯一阻塞 NQ-1 已随 DEC-020 裁定解除，2026-09-18） |

**汇总增量**：`Feature 总数 16`、`DONE 14`、`CANCELLED 1`、`DRAFT 1`、`READY 0`、`BLOCKED 0`。

## Blocking Decisions（增量）

| ID | type | 关联 | 状态 | 问题 |
|---|---|---|---|---|
| DEC-020 | product | F017 | **RESOLVED（2026-09-18 用户裁定「做」）** | 用户是否需要把应用外壳导航由顶部横向按钮改为侧边栏？若实施，范围是否限于呈现层（不引入 vue-router / 不新增依赖 / 不改路由 URL / 不改资源页面内容 / 不做响应式主题）？ |

**供决策的已核实事实**（非推测）：
1. **无任何已确认产品规则规定导航形态**——`requirements.md` §5 的「页面导航」仅述资源分类的作用之一；
   `docs/architecture/f002-bare-metal-handoff.md:230` 与 `frontend/src/App.vue:23/31/93` 均明确写明
   「导航形式不构成产品规则」。故改为侧边栏**不违反任何已确认规则**、**不新增产品规则**。
2. **不需要 vue-router**：侧边栏只是把同一套视图状态切换器的呈现从顶栏改为侧栏。「不引入 vue-router」
   仍是 OPEN 非阻塞项，与本项**相互独立**，本项**不触发**该决策。
3. **不需要新增依赖**：Element Plus 已是既有依赖（`element-plus ^2.14.5`），其 `el-menu` / `el-aside`
   当前未被使用。与 `AGENTS.md` §2.6 不冲突。
4. **影响面为纯呈现层，但共享外壳 `frontend/src/App.vue` 被改动**；5 个既有导航测试共 **15 处**
   把活跃态断言为 `el-button--primary`，改版后必须**改写而非删除**（已写成 F017 的 AC-06 必需工作）。
5. 无权限 / 删除 / 全局标识影响；**不存在真正阻塞的长期架构决策**。

## Milestones（增量）

| ID | 名称 | Features | 状态 |
|---|---|---|---|
| M7 | 应用外壳侧边栏导航（post-V1，呈现层） | F017 | READY — 已获用户批准，执行中 |

## Open Questions（增量）

| ID | Feature | 问题 | 阻塞 |
|---|---|---|---|
| NQ-1 | F017 | 用户是否确实要求实施 | **否（已裁定「做」，2026-09-18）** |
| NQ-2 | F017 | 侧边栏视觉细节（折叠 / 图标 / 记忆折叠状态 / 宽度） | 否（UI 设计，最小改动） |
| NQ-3 | F017 | 是否采用 Element Plus `el-menu`（实现选择，不写入 AC） | 否 |
