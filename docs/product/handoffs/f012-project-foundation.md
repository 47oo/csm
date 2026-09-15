# Product Handoff — F012 项目基础框架与运行环境

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-15
> Feature: F012（ENABLER，E07，P0，无 `depends_on`）
> Git: `feature/F012-project-foundation`，base `develop`

---

## Feature

项目基础框架与运行环境（F012）— 所有资源 Feature 的共享基座（ENABLER，E07，P0）。

## Problem

CSM 的产品承诺是「建立一个统一、清晰、可查询、可维护的资源事实库」，替代分散维护的 Excel（`requirements.md` §1、§2）。事实库要成立，前提是**数据可信**：同名资源不重复、非法数据写不进去、错误能被人看见（§21、§25）。

当前项目是 greenfield：不存在任何应用代码、数据库、API（`project-plan.yaml > existing_work`）。如果直接进入 F001 ~ F011，十二个资源 Feature 会各自发明自己的校验、错误结构、删除语义与运行方式，结果是 Excel 场景中「同一资源跨多表」「重复登记」「事实互不一致」的问题以新形式重现；更严重的是，本架构中**最难回退的两处基座语义**（大小写敏感的唯一性比较、软删与唯一索引的交互、数据库选型）一旦在资源建模开始后才发现选错，返工代价极高（`adr-0002` / `adr-0004` Reversibility 均记为「高代价」）。

因此 F012 的产品价值不是「搭一个框架」，而是：**在为资源建模投入之前，用最小骨架把「数据可信」的基座语义固定下来并证明其成立**，使所有资源 Feature 复用的是一套已验证、不可静默改变的事实保护机制。

使用者：
- 直接使用者是开发 / 运维（需要可运行、可按文档启动的环境）；
- 最终受益者是 HPC / AI 运维人员与平台管理员（依赖其后登记的数据可信，§3）。

## Confirmed Requirements

仅列已确认内容，来源见括号。

1. **项目骨架可运行，并具备本地开发 / 运行环境**；资源类型采用显式建模（F012 AC，`project-plan.yaml`）。
2. **资源仅有统一产品分类概念，不得因该概念产生通用数据库模型**：不得采用 EAV、通用 `resources` 表、Single Table Inheritance、ORM 多态继承或 JSONB 万能资源模型（§4、§24；`domain-model.yaml > implementation_constraints`）。
3. **提供通用数据校验与冲突错误处理基座，供各资源 Feature 复用**（§21；F012 AC）。
4. **关键冲突必须在保存前阻止，不能只依赖 UI 校验**；Backend / Database 必须具备真实的数据一致性保护（§21）。
5. **名称唯一性比较区分大小写**：`cluster-a` 与 `Cluster-A` 从业务上视为不同值（§22）。
6. **产品核心原则**：Explicit Resource Types / Explicit Relationships / Explicit Constraints / History Preservation / Simple First；不得为「未来可能需要」做大规模抽象（§25）。
7. **数据与界面含中文**，数据库与连接字符集必须支持中文（UTF-8）（`adr-0001` Context「界面与数据含中文」；架构 Data Layer Impact #10、Verification #6）。
8. **部署形态为独立内网虚拟机、Internal IP + HTTP**，不引入公网入口 / 域名 / HTTPS——此为已确认的产品取舍（§20、R-DEPLOY-001~003；`adr-0005`）。
9. **统一错误响应必须能承载「字段 + 原因」级信息**（§21；`docs/api/api-conventions.md` §5，`READY`）。
10. **技术栈、数据库、标识、软删持久化、认证、API 契约均已由用户批准**（`adr-0001` ~ `adr-0005` 全部 `ACCEPTED`；`api-conventions.md` = `READY`；`docs/database/` = `READY FOR DATABASE IMPLEMENTATION`）。F012 在这些已批准决策内落地，不重新论证。

## Confirmed Domain Rules

本 Feature **不新增、不修改任何领域对象、关系、状态或唯一性规则**（架构 Domain Impact）。它只依赖以下已确认规则：

| 规则 / 原则 | 内容 | 来源 |
|---|---|---|
| Resource 概念 | `Resource` 仅表示分类体系，不意味着通用表 / ORM 基类 / 数据库继承 / 统一状态模型 | `requirements.md` §4 |
| Resource Taxonomy | Infrastructure / Virtual / Network / Service 四类，仅用于产品组织，不自动产生数据库关系 | `requirements.md` §5；`domain-model.md` §3 |
| 禁止 EAV / 通用 `resources` 表 / STI / JSONB 万能模型 | Architecture / Database 不得因存在统一 Resource 概念而默认采用 | `requirements.md` §24；`domain-model.yaml > implementation_constraints` |
| §21 Data Consistency | 关键冲突（同 Cluster IP、同 Cluster hostname、全局 Cluster Name、非法关系、非法状态值）必须在保存前阻止；不能只依赖 UI | `requirements.md` §21；`domain-model.yaml > data_consistency` |
| §22 Case Sensitivity | Cluster Name 与 BareMetal hostname 唯一性比较区分大小写 | `requirements.md` §22；`domain-model.md` §8 |
| §25 产品核心原则 | 显式类型 / 显式关系 / 显式约束 / 历史保留 / 简单优先 | `requirements.md` §25 |
| R-CLUSTER-005（仅数据库层落地） | Cluster 名称不得包含 `/`；基线 migration 按已 READY 数据库设计固化为 `ck_clusters_name_no_slash` | `requirements.md` R-CLUSTER-005；`docs/database/f012-baseline-migration.md` §2、§4 |
| 逻辑删除语义（仅作为基座依赖，不实现） | F012 的基线 partial unique index 需与 R-DELETE-006 的语义相容；软删行为本身属 F014 | `requirements.md` §17；`adr-0004` |

**明确依赖但不在 F012 实现的领域规则**：Cluster / BareMetal / NetworkInterface / IPAddress / VirtualMachine / Container / Service 的字段、唯一性、状态与生命周期（R-CLUSTER-*、R-BM-*、R-NIC-*、R-IP-*、R-VM-*、R-SVC-*），以及逻辑删除六条规则（R-DELETE-001~006），分别属于 F001 ~ F008、F014。

## Scope

### 本次包含

1. 应用骨架、配置、数据库连接池、健康检查；可运行的本地开发 / 运行环境。
2. 分层与模块边界基座（HTTP → 校验 → 领域服务 → 数据访问），**每类资源为独立模块 + 独立表**，仅允许 `id` / `created_at` / `updated_at` / `deleted_at` 这类横切列的 mixin 复用（`adr-0001`）。
3. 统一请求校验基座 + 统一错误信封（按 `api-conventions.md`，含 `error.code` 与 `details[].field`）。
4. 分页约定、事务边界约定。
5. 基线 migration 框架（Alembic）+ 最小可跑通集合：`clusters` 表 + `ck_clusters_name_no_slash` + `ux_clusters_name_active`（partial unique index），**作为验证载体**（`docs/database/f012-baseline-migration.md` §2）。
6. 前端骨架，列表 Loading / Empty / Error 三态基座。
7. 代码规范与最小测试可执行（lint + 至少一个**真实断言数据库约束**、绕过应用层直接对数据库操作的测试）。

### 本次明确不包含

（依据：F012 定位、架构 Backend Work、`project-plan.yaml`、数据库设计 §10）

1. 任何具体资源的业务规则与 CRUD API——Cluster / BareMetal / NetworkInterface / IPAddress / VirtualMachine / Container / Service 的字段、唯一性、状态、生命周期校验一律不属于 F012。
2. **Cluster 的领域校验、CRUD API、`GET /api/clusters/by-name/{cluster_name}` 别名**——属 F001。`clusters` 表由 F012 基线建立，F001 **不新建表**（`f012-baseline-migration.md` §2）。
3. 其余资源表与认证表及其 migration（`bare_metals` / `network_interfaces` / `ip_addresses` / `users` / `sessions`），分别属 F002 / F004 / F005 / F013。
4. 逻辑删除领域服务、父删子拦、不级联、并发父子完整性、`ip_address.cluster_id` 一致性治理、唯一冲突到 HTTP 语义的映射——属 F014。
5. 本地账号认证、口令哈希、会话与 Cookie、认证中间件——属 F013。
6. 内网部署打包（docker-compose / nginx / 生产运行）——属 F015。
7. Excel 模板与批量导入——属 F011。
8. 复杂 RBAC、审批流 / 工作流、通用资源抽象、微服务化、消息队列、Redis、Event Bus、CQRS、Kubernetes、Elasticsearch——无已确认需求支撑（§23；架构 Constraints #1）。

### 本次未涉及

当前需求没有要求，但不能推断为永远不需要：

- 资源导出；
- 高级筛选 / 复合检索；
- 历史审计（audit log）；
- 可观测性（结构化访问日志、指标）；
- 数据库备份 / 恢复策略与连接池尺寸调优；
- API versioning、游标分页；
- 前端组件库最终选型（若组织有标准可替换 Element Plus）。

## Acceptance Criteria

每条均为**可判定（是 / 否）**，描述可观察到的行为。

- **AC-01（可运行骨架与文档）**：存在可运行的项目骨架与本地开发 / 运行环境；一个未接触过本仓库的开发者**仅依照仓库内文档**即可在 30 分钟内启动系统（架构判据 7）。
- **AC-02（可运行证明）**：启动后健康检查端点 `GET /api/health` 返回 200（架构判据 1 的可观察部分）。
- **AC-03（显式资源建模）**：系统中不存在通用 `resources` 表、EAV 结构、Single Table Inheritance、ORM 多态继承或 JSONB 万能资源模型；占位资源以显式类型化表建模（§4、§24、§25）。
- **AC-04（冲突在保存前被阻止，且不依赖 UI）**：重复 / 非法的关键值即使**绕过界面、直接写入数据层**也会被拒绝；界面并非唯一防线（§21）。
- **AC-05（大小写敏感在数据层成立）**：`cluster-a` 与 `Cluster-A` 被系统接受为两个不同的值；而写入两个真正相同的活跃值时，**绕过应用层直接操作数据库**仍被拒绝（§22 + §21；架构判据 3 的产品部分）。
- **AC-06（错误可被用户看到具体字段与原因）**：字段校验失败时返回 `400`，响应包含稳定 `error.code` 与 `details[].field`，使调用方无需靠猜定位问题（`api-conventions.md` §5、§6；§21）。
- **AC-07（中文往返正确）**：含中文的数据写入后能被正确读出，且按字面值等值比较正确（无乱码、无错误匹配）（架构 Verification #6）。
- **AC-08（基座可复用、契约单一权威）**：各资源 Feature 复用同一套校验 / 错误信封 / 分页 / 事务边界基座，不各自实现；数据库与 API 契约是单一权威来源，代码中不另立一套约定（架构 Constraints #9；R-IMPORT-002 的复用前提）。
- **AC-09（不承载资源业务规则）**：F012 交付物中不包含任何具体资源的字段定义、唯一性规则实现、状态流转或生命周期逻辑；`clusters` 表仅作为基座验证载体存在（F012 定位边界）。

### 架构 8 条「技术栈验证骨架」判据的归属判断

架构文档「技术栈验证骨架」是 **F012 的验收内容**；但并非每条都构成产品可验收标准。逐条判断如下（**不照抄为产品 AC**）：

| # | 架构判据 | 归属 | 依据 |
|---|---|---|---|
| 1 | 目标内网虚拟机以 Internal IP + HTTP 启动，`GET /api/health` 返回 200 | **分裂**：部署形态偏产品约束，健康检查属架构验证 | 「内网 + HTTP、不引入公网/域名/HTTPS」是产品规则（§20、R-DEPLOY-002/003），但**实际内网部署属 F015**；F012 只要求本地 / 开发可运行（AC-01、AC-02）。健康检查本身是技术验证。 |
| 2 | 基线 migration 可应用 / 可重复应用 / 可从空库重建 | **架构验证（数据库）** | 属数据库工程机制，无对应产品 R-xxx；产品不关心迁移的执行次数与重建路径。 |
| 3 | 显式资源表验证：大小写敏感 collation 生效；partial unique index 生效；**绕过应用直接插入重复被拒** | **产品可验收（部分）+ 架构验证（部分）** | 「大小写敏感」= §22 产品规则；「不能只依赖 UI」= §21 产品规则 → 对应 AC-05，可判定。partial unique index 与「软删后可重建同名」属基座机制验证，支撑 R-DELETE-006（F014），**不是 F012 的产品 AC**。 |
| 4 | 统一错误信封：一次字段校验失败返回 400 + `details[].field` | **产品可验收** | §21 要求关键冲突被阻止且错误可见；R-IMPORT-003 需要字段级错误；契约已 `READY` → 对应 AC-06。 |
| 5 | 一个资源 create → list → get → update → soft delete 端到端往返 | **架构验证（骨架贯通）** | 端到端往返本身是技术验证；其中「删除后不出现在 list」= R-DELETE-002，属 F014 的 AC，不属于 F012 产品验收。 |
| 6 | 前端可构建，并渲染 Loading / Empty / Error 三态 | **架构验证（前端基座）**，含一条弱产品相关约束 | 三态是前端工程基座；其中「Error 态由后端 `error.code` 渲染、错误对用户可见」关联 §21，已由 AC-06 覆盖。 |
| 7 | 本地开发 / 运行方式有文档，可依文档在 30 分钟内启动 | **产品可验收** | F012 的 AC 明确要求「存在可运行的项目骨架与本地开发/运行环境」，可计时、可观察 → 对应 AC-01。 |
| 8 | 代码规范与最小测试可执行（lint + 一个真实断言数据库约束的测试） | **架构验证（质量门禁）** | 属工程质量保证，非产品可观察行为；但其「绕过应用层断言数据库约束」的取向来自 §21，须保留。 |

**特别说明（判据 3 的产品含义）**：§21 要求关键冲突「不能只依赖 UI 校验」。在产品层，这意味着：**数据一致性不能建立在「用户会通过我们的界面操作」这一假设上**。即使有人通过脚本、手工 SQL 或其他非界面路径写入，关键冲突（如两个活跃的同名资源）也必须被数据层拒绝。因此判据 3 的产品意义是「事实库的可信性不取决于入口是否规范」，这是 AC-04 / AC-05 的直接来源。

## Assumptions

（不阻塞当前工作、且可安全暂时采用；不得当作 CONFIRMED）

1. 架构文档与 ADR-0001 ~ ADR-0005 全部 `ACCEPTED`、API 契约 `READY`、数据库设计 `READY FOR DATABASE IMPLEMENTATION`，作为 F012 的实现依据，不再重新论证。
2. AC-01 的「30 分钟」度量环境为具备项目所需本地/容器工具链（Python、Node、PostgreSQL 或等价 docker 环境）的开发机；计时口径（是否含前端构建与数据库初始化）由架构 / 部署文档确定（见 NQ-4）。
3. 架构 Backend Work 列出的 F012 基座项与 F014 的「统一逻辑删除领域服务」存在边界重叠（软删过滤基座、冲突→HTTP 映射）；假设该重叠由 Architecture 阶段明确划分，且**不改变任何产品行为**（见 NQ-1）。

## Proposed Rules

无。本 Feature 不引入任何新的产品规则，也不修改任何已有规则。

## Open Questions

### Blocking

**无。**

理由：F012 的产品范围（显式资源建模 + 通用校验 / 错误基座 + 可运行环境）、边界（不实现任何资源业务规则）与验收标准（AC-01 ~ AC-09）均可由现有 CONFIRMED 文档（`requirements.md` §4/§5/§20/§21/§22/§23/§24/§25、`domain-model.md`、5 条 `ACCEPTED` ADR、`READY` 的 API 契约与数据库设计）完整确定。

以下候选问题经判断**均不改变业务行为**，故不构成 Blocking：
- F012 / F014 的基座职责切分（NQ-1）——无论由哪个 Feature 实现，产品行为相同；
- `ck_clusters_name_no_slash` 的交付归属（NQ-2）——R-CLUSTER-005 已是确认规则，差异仅在由哪个 Feature 落地；
- 「可运行」与「内网部署」的边界（NQ-3）——AC 已分别归属 F012 / F015；
- 30 分钟计时口径（NQ-4）——度量细节，不改变功能语义。

### Non-blocking

- **NQ-1（F012 ↔ F014 基座边界）**：架构 Backend Work 把「软删除过滤基座」与「事务边界约定」放在 F012，把「统一逻辑删除领域服务（含软删过滤）」与「唯一冲突到 HTTP 语义的映射」放在 F014；`adr-0004` 要求软删过滤由数据访问层**统一提供**、禁止各模块各写一套。需在 Architecture 阶段明确谁提供、谁复用，避免重复实现或遗漏（不改变产品行为）。
- **NQ-2（R-CLUSTER-005 的交付归属）**：基线 migration 按已 READY 的数据库设计包含 `ck_clusters_name_no_slash`。该规则的**产品定义**属 F001，数据库约束**落地**在 F012 基线。需在 Architecture / Backend 交接中明确责任划分：F001 负责 API 写入路径校验，使含 `/` 的名称以 `400 VALIDATION_ERROR`（而非 `500`）被拒绝；F012 仅承载数据库约束。二者应形成双保险而非重复逻辑。
- **NQ-3（F012 ↔ F015 边界）**：「可运行」在 F012 指本地 / 开发环境；「独立内网虚拟机 + Internal IP + HTTP + docker-compose」属 F015。需确认 F012 不在本 Feature 内交付生产部署包。
- **NQ-4（30 分钟计时口径）**：是否需要容器化启动、是否含前端构建与数据库初始化，口径未定。不影响功能正确性。
- **NQ-5（前端错误态与契约）**：`api-conventions.md` 要求前端按 `error.code` 分支且不解析 `message`。前端基座应遵循该契约；属实现一致性问题，非产品问题。

## Architecture Handoff

Architect 接下来需要解决的技术设计问题（此处不替 Architect 选择框架、设计表、定义 API 或编写代码）：

1. **F012 与 F013 / F014 / F015 的基座责任边界**：明确软删过滤基座、统一错误信封、事务边界约定、冲突→HTTP 语义映射四者分别由哪个 Feature 交付、其余 Feature 如何复用（回应 NQ-1）。
2. **基线 migration 的范围与 F001 的衔接**：明确 F012 建立 `clusters` 表及其约束 / 索引时，F001 **不新建表**、只交付领域校验 / CRUD / `by-name` 别名；并明确数据库约束违反（`23514` / `23505`）如何映射为产品语义状态码（`400` vs `409`），以及 R-CLUSTER-005 在 API 层与数据库层的双保险分工（回应 NQ-2）。
3. **显式资源类型的基座约束**：明确骨架如何在结构与约定上防止后续引入通用 `resources` 表 / EAV / STI / JSONB 万能模型（§4、§24）。
4. **可运行环境的验收口径**：明确 AC-01 的「本地 / 开发可运行」与 AC-02 的健康检查在 F012 内的具体边界，及其与 F015 内网部署的切分（回应 NQ-3、NQ-4）。
5. **大小写敏感与中文 UTF-8 的基座落地**：明确 collation 语义（使用数据库默认，见 `adr-0002`）与 UTF-8 连接字符集在骨架层的具体承载方式，以及「绕过应用层直接断言」的测试位置；与 `adr-0002` Risk #1「locale 依赖须在部署文档固定」的要求衔接。
6. **认证边界**：明确 F012 骨架**不实现** F013 的认证与会话，并说明在认证尚未落地前 `/api/*` 的临时行为，避免 F012 事实上扩大为 F013。
7. **UNCONFIRMED 关系不被固化**：确认 F012 骨架的约定不预先假定 VM→BareMetal、Container→载体为必选（这些关系 UNCONFIRMED，属 F006 / F007）；F012 不建这些表，但基座约定不得隐含其强制性。

## Handoff Status

`READY FOR ARCHITECT`