# CSM Backlog

> Status: DRAFT（待用户确认）
> Source of Truth: `docs/project/project-plan.yaml`
> 本文件是人类可读视图，不构成机器状态的唯一来源。
> Last updated: 2026-09-15（依用户对 8 项产品冲突的裁定与产品文档同步更新）

需求基线：`docs/product/requirements.md`（CONFIRMED BASELINE）。
产品领域模型：`docs/product/domain-model.md`（已于 2026-09-15 同步）。
项目为 Greenfield：无任何已实现能力，**无 DONE Feature**。

状态取值：`DRAFT` / `BLOCKED` / `READY` / `IN_PROGRESS` / `IN_REVIEW` / `DONE`。

DRAFT / BLOCKED 判定规则（权威定义见 `project-plan.yaml` 顶部与 `planning_status.status_decision_rules`）：

- `DRAFT`：存在未解决的产品问题，且该问题直接影响该 Feature 自身 scope 或 acceptance_criteria 的定稿（自身数据模型 / 字段 / 唯一性 / 生命周期 / 校验策略等产品语义尚未确认）。
- `BLOCKED`：Feature 的 scope 与 acceptance_criteria 已可定稿，仅被 architecture / database decision、未 DONE 的 `depends_on` 或环境阻塞。
- 两类原因同时存在时取 `DRAFT`，并在 `blocking` 中同时列出两类原因；仅被其他 Feature 的产品决策间接影响、不改变本 Feature 交付边界时仍按 `BLOCKED`。

由于项目无技术栈 ADR、无架构/数据库/API 设计、无基础实现，**当前没有任何 READY Feature**。

---

## 汇总

| 维度 | 值 |
|---|---|
| Feature 总数 | 14 |
| P0 | 7（F001, F002, F009, F012, F013, F014, F015） |
| P1 | 7（F004, F005, F006, F007, F008, F010, F011） |
| P2 | 0 |
| READY | 0 |
| BLOCKED | 9（F001, F004, F005, F009, F010, F012, F013, F014, F015） |
| DRAFT | 5（F002, F006, F007, F008, F011） |
| DONE | 0 |
| Blocking Decisions (OPEN) | 6（DEC-009 ~ DEC-014） |

产品冲突 DEC-001 ~ DEC-008 已由用户裁定，不再计为项目级阻塞（见下方状态表）。

---

## E01 基础资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F001 | Cluster 登记与管理 | P0 | BLOCKED | F012 | DEC-009, DEC-011 | requirements.md §7, §22 |
| F002 | BareMetal 登记与管理 | P0 | DRAFT | F001 | DEC-009, DEC-012, OPEN-004 | requirements.md §8, §22 |

## E02 网络资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F004 | NetworkInterface 管理 | P1 | BLOCKED | F002 | DEC-009 | requirements.md §11 |
| F005 | IPAddress 管理 | P1 | BLOCKED | F004 | DEC-009 | requirements.md §12 |

## E03 虚拟资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F006 | VirtualMachine 登记与管理 | P1 | DRAFT | F002 | DEC-009, OPEN-001, DEC-004(Feature 级) | requirements.md §9 |
| F007 | Container 资源模型与登记 | P1 | DRAFT | F006, F002 | DEC-009, OPEN-002, DEC-005(Feature 级) | requirements.md §10 |

## E04 服务资源管理

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F008 | Service 资源管理与 Cluster 共享关联 | P1 | DRAFT | F001, F002, F006, F007 | DEC-009, OPEN-003 | requirements.md §14, §15 |

## E05 资源查询与视图

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F009 | Cluster 视角资源查询 | P0 | BLOCKED | F001, F002 | DEC-009, F001/F002 未 DONE | requirements.md §16 |
| F010 | 资源详情与关联查询 | P1 | BLOCKED | F001, F002, F004, F005, F006, F007, F008 | DEC-009, 依赖未 DONE | requirements.md §15, §16 |

## E06 数据导入

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F011 | Excel 模板与批量导入 | P1 | DRAFT | F001, F002, F004, F005, F006, F007, F008 | DEC-009, OPEN-005, 依赖未 DONE | requirements.md §18 |

## E07 平台基础能力（ENABLER）

| ID | Feature | Priority | Status | Dependencies | Blocking | Product Document |
|---|---|---|---|---|---|---|
| F012 | 项目基础框架与运行环境 | P0 | BLOCKED | — | DEC-009, DEC-010, DEC-011 | requirements.md §4, §5, §21, §24, §25 |
| F013 | 本地账号认证与会话 | P0 | BLOCKED | F012 | DEC-009, DEC-013 | requirements.md §19 |
| F014 | 逻辑删除与数据一致性治理 | P0 | BLOCKED | F012 | DEC-012, DEC-009 | requirements.md §17, §21 |
| F015 | 内网部署与运行环境 | P0 | BLOCKED | F012, F013 | DEC-009, DEC-010 | requirements.md §20 |

**F003（Rack 与 U 位位置管理）已于 2026-09-15 依用户决策删除，不再属于 V1 范围。**

---

## Blocking Decisions（摘要）

| ID | Type | 影响 Feature | 状态 | 说明 |
|---|---|---|---|---|
| DEC-001 | product | F001, F002, F009, F010, F011 | RESOLVED | V1 不含 DataCenter（requirements.md §6） |
| DEC-002 | product | F011 | RESOLVED | Rack / U 位已从 V1 删除，F003 一并删除 |
| DEC-003 | product | F008, F010, F011 | RESOLVED | 方案 C：Service 必选绑定运行载体（R-SVC-005/006） |
| DEC-004 | product | F006, F007, F010, F011 | DEFERRED_TO_FEATURE | 归属 F006 Product 阶段 |
| DEC-005 | product | F007, F010, F011 | DEFERRED_TO_FEATURE | 归属 F007 Product 阶段 |
| DEC-006 | product | F004, F005, F006, F007, F008 | RESOLVED | 方案 B：仅 BareMetal 有状态 |
| DEC-007 | product | F001 | RESOLVED | 已确认为 R-CLUSTER-005 |
| DEC-008 | architecture | F006, F007, F008 | TRANSFERRED_TO_ARCHITECT | 统一 status 建模转由 Architect 处理 |
| DEC-009 | architecture | 全部 Feature（技术栈与整体架构） | OPEN | — |
| DEC-010 | database | F004, F005, F006, F007, F008, F012, F015（数据库与 Schema） | OPEN | — |
| DEC-011 | architecture | 全部资源 Feature（全局标识与寻址） | OPEN | — |
| DEC-012 | database | F014 及资源 Feature（逻辑删除实现与唯一性释放） | OPEN | — |
| DEC-013 | architecture | F013, F015（认证实现范围） | OPEN | — |
| DEC-014 | architecture | 全部 API 相关 Feature（API 契约与错误响应） | OPEN | — |

完整 question 文本与 resolution 见 `docs/project/project-plan.yaml` 的 `decisions_required`。

---

## Open Questions（未确认需求，不升级为 Feature / 验收条件）

| OPEN | 关联 Feature | 内容 | 状态 |
|---|---|---|---|
| OPEN-001 | F006 | VirtualMachine 字段范围及其标识与唯一性规则 | OPEN |
| OPEN-002 | F007 | Container 管理粒度 | OPEN |
| OPEN-003 | F008 | Service 字段 | OPEN |
| OPEN-004 | F002 | BareMetal 硬件字段 | OPEN |
| OPEN-005 | F011 | Excel 部分成功导入策略 | OPEN |
| OPEN-006 | — | 虚拟资源运行时集成 | **已关闭（已确认排除）** |

另有 2 项原项目级产品决策已转为 Feature 级 `open_questions`（不再计入项目级阻塞）：

- **DEC-004** → F006 Product 阶段（VM→BareMetal 绑定强制性与生命周期）；
- **DEC-005** → F007 Product 阶段（Container 粒度与绑定）。

---

最后更新依据：用户对 8 项产品冲突的裁定结果 + `docs/product/domain-conflict-handoff.md`（注意：该 Handoff 的 Handoff Status 已过时）+ 已定稿的 `docs/product/requirements.md` / `domain-model.md`。