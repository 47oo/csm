# Product Handoff — F014 逻辑删除与数据一致性治理

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-16
> Feature: F014（ENABLER，E07，P0，`depends_on: [F012]`）
> Git: `feature/F014-soft-delete`，base `develop` = `897b32539927c137b933aa0ebed700d3bc26be5b`
> 已核实实现事实（只读）：F012 DONE、F013 DONE、F001 DONE；`backend/app/**` 中 `deleted_at` 写入路径数 = **0**；唯一已存在资源表为 `clusters`；F001 刻意未注册 `DELETE /api/clusters/{id}`（`docs/architecture/f001-cluster-handoff.md` 方案要点 #2/#3、测试 A15）。

---

## Feature

逻辑删除与数据一致性治理（F014）— CSM V1 的**逻辑删除领域基座**：唯一软删写入路径、删除守卫（父删子拦 / 不级联）、以及 `clusters` 资源上的**产品删除路径**。

## Problem

CSM 的核心承诺是「替代分散维护的 Excel，形成可信、可查、可维护的资源事实库」（`requirements.md` §1、§2）。Excel 的现实问题之一是**误登记无处撤销**：写错一行只能删掉覆盖，历史随之丢失；而直接删掉又会连带丢掉「这台机器曾经登记过」的事实（§25 History Preservation）。

当前系统在这条能力上是**空白**：`clusters` 可登记、可改名、可查询（F001），但**无法删除任何资源**。原因是 F001 已把整个删除语义显式推迟给 F014 —— F001 既不注册删除端点，也不存在任何写入 `deleted_at` 的代码路径（`f001-cluster-handoff.md` REQUIRED #1 / A15；`ADR-0004` §1/§3 要求软删由**统一领域服务**提供，禁止各模块各写一套）。

因此现在面临的具体运维问题：

- 运维人员登记了一个错误的集群，**没有任何产品路径可以撤销**；
- 若不建立统一服务就各自开删除端点，就会产生多条软删写入路径，违反 ADR-0004，并使「已删不占唯一性」与「查询过滤」的谓词出现漂移（查得到却写不进 / 写进了却查得到）；
- `R-DELETE-004`（父资源有活跃子资源时不得删除）若只在界面上禁用按钮，违反 §21「关键冲突必须在保存前阻止，不能只依赖 UI 校验」。

使用者：HPC / AI 集群运维人员、基础设施管理员（§3）。场景是「登记写错了 → 删除这个集群 → 后续可以用同名重新登记」。

F014 的产品价值是：**让「删除」成为一个可信、唯一、可审计语义清晰的产品动作**——记录仍在（历史保留）、查询看不到、同名可重建、有活跃子资源时删不掉；并把这条语义做成 F002 ~ F011 必须复用的唯一基座。

## Confirmed Requirements

仅列已确认内容，来源见括号。

1. **核心资源记录不得被正常产品操作物理删除**；删除采用逻辑删除语义（R-DELETE-001；`domain-model.yaml > lifecycle.deletion = soft`、`physical_delete.allowed = false`）。
2. **已逻辑删除的资源默认不出现在正常查询结果中**（R-DELETE-002；`lifecycle.deleted_visibility.excluded_from_normal_queries = true`）。
3. **V1 不提供 Undelete / Restore**；`deleted_at` 一旦写入不再回退，资源记录仅支持更新（R-DELETE-003；ADR-0004 §4）。
4. **父资源存在有效子资源时不得删除父资源**；示例为「Cluster 仍存在有效 BareMetal 时不能删除 Cluster」（R-DELETE-004；`lifecycle.parent_deletion.blocked_when_active_children_exist = true`）。该冲突属 §21 的「保存前必须阻止」项，**不得只依赖 UI**。
5. **逻辑删除不得自动级联删除所有子资源**；必须显式处理依赖关系（R-DELETE-005；`lifecycle.cascade.automatic_cascade_delete = false`；`docs/database/csm-v1-schema-design.md`「不级联结论」：全部 FK `ON DELETE RESTRICT`，无一处 CASCADE）。
6. **已逻辑删除的记录不继续占用正常业务唯一性**，因此可以重新创建同名资源（R-DELETE-006；ADR-0004 §2 由 partial unique index `WHERE deleted_at IS NULL` 保证）。**F014 不改变该语义**：它已由 F012 基线（`ux_clusters_name_active`）与 ADR-0002/0004 固定，F014 只负责让它通过产品路径可被观察。
7. **删除时必须保证已删除记录的历史信息保留**；删除标记的具体持久化方式由数据库设计决定（`domain-model.md` §9；`lifecycle.persistence_note`）。
8. **§21 Data Consistency**：关键冲突必须在保存前阻止，不能只依赖 UI；Backend / Database 必须具备必要的数据一致性保护（§21；`data_consistency.not_ui_only = true`）。§21 列举的具体冲突（同 Cluster IP / 同 Cluster hostname / 全局 Cluster Name / 非法资源关系 / 非法状态值）**逐条归属各资源 Feature**（F005 / F002 / F001 / F002·F004·F005·F008 / F002），**不属 F014**（见「交付边界裁定」）。
9. 资源标识与 API 契约按已批准约定：规范路径使用 `id`，**写操作（POST / PATCH / DELETE）一律走 `id` 路径**；删除成功语义为 **`204`**；「资源不存在或已被逻辑删除」→ **`404 NOT_FOUND`**；「父资源存在活跃子资源」→ **`409 CONFLICT`**（ADR-0003 §2；`api-conventions.md` §2、§6）。
10. **AD：所有资源表的删除标记为单一 `deleted_at`，所有常规查询统一附加 `deleted_at IS NULL`，且由数据访问层统一提供，禁止各模块各写一套**（ADR-0004 §1/§3）。
11. **父资源删除前必须在同一事务内检查活跃子资源并对父行加锁**，以避免并发下「子资源刚创建、父资源同时被删」产生孤立记录（ADR-0004 §5）。
12. **唯一性冲突在应用层先行检查仅为体验优化；数据库 partial unique index 是最终权威**（ADR-0004 §7；§21）。该分工已由 F001 落地并测试（`f001-cluster-handoff.md` A04），F014 不得改动。
13. **认证边界**：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两种边界，**不引入角色 / 权限 / RBAC**（ADR-0005；R-AUTH-003）。因此**任何已认证用户都可以执行删除**，删除不引入额外审批流或角色限制。
14. **F001 的交付面已划定**：Cluster 的删除语义整体属 F014；F001 结束时 `backend/app/**` 中 `deleted_at` 写入路径数恰好为 0，`DELETE /api/clusters/{id}` 未注册（`f001-cluster-handoff.md` 方案要点 #2/#3、REQUIRED #1、A15；`f001-cluster.md` AC-13）。F014 是 `clusters` 删除端点的所属 Feature。
15. **逻辑删除不适用于非资源表**：`users` / `sessions` 不是 Resource，不用 `deleted_at`、不适用本 Feature 语义（`domain-model.yaml > authentication.note`；`app/auth/repository.py` 注释）。F014 不得把软删语义扩大到认证表。

## Confirmed Domain Rules

| 规则 / 原则 | 内容 | 来源 |
|---|---|---|
| R-DELETE-001 | 正常产品操作不得物理删除核心资源记录 | `requirements.md` §17；`domain-model.yaml > lifecycle.physical_delete` |
| R-DELETE-002 | 已逻辑删除资源默认不出现在正常查询结果中 | `requirements.md` §17；`domain-model.yaml > lifecycle.deleted_visibility` |
| R-DELETE-003 | V1 不提供 Undelete / Restore；`deleted_at` 不回退 | `requirements.md` §17；`domain-model.yaml > lifecycle.undelete`；ADR-0004 §4 |
| R-DELETE-004 | 父资源存在有效子资源时不得删除父资源 | `requirements.md` §17；`domain-model.yaml > lifecycle.parent_deletion`；ADR-0004 §5 |
| R-DELETE-005 | 逻辑删除不得自动级联删除子资源 | `requirements.md` §17；`domain-model.yaml > lifecycle.cascade`；ADR-0004 §6 |
| R-DELETE-006 | 已逻辑删除资源不占用正常业务唯一性，可重建同名 | `requirements.md` §17；`domain-model.yaml > lifecycle.uniqueness_release`；ADR-0004 §2 |
| §21 Data Consistency | 关键冲突在保存前阻止，不能只依赖 UI | `requirements.md` §21；`domain-model.yaml > data_consistency` |
| §25 History Preservation / Simple First | 删除不破坏历史事实；简单优先 | `requirements.md` §25；`domain-model.yaml > implementation_constraints` |
| 唯一性边界与大小写 | Cluster Name 全局唯一、大小写敏感；已删释放唯一性 | `requirements.md` §22；`domain-model.yaml > uniqueness_rules`；ADR-0002 |
| 寻址与状态码 | 写操作走 `id`；`204` 删除成功；`404` 不存在或已删；`409` 父有活跃子 | `adr-0003` §2；`api-conventions.md` §2/§6 |
| 删除标记与过滤 | 单一 `deleted_at`；`deleted_at IS NULL` 由数据访问层统一提供 | `adr-0004` §1/§3 |

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。**

## Scope

### 本次包含

1. **统一逻辑删除领域服务**：系统内唯一允许写入 `deleted_at` 的领域服务；所有资源模块的删除必须委托它（ADR-0004 §1/§3；`f012-project-foundation-handoff.md` Q1「软删除领域服务、并发父子完整性」归 F014）。F014 交付后，`deleted_at` 写入路径由 0 变为「恰好 1 条服务路径 + 各资源显式委托」。
2. **删除守卫（服务级规则，非资源级）**：
   - 删除前在**同一事务内**执行活跃子资源检查，并对目标行加锁（ADR-0004 §5）；
   - 存在活跃子资源 → 删除被拒，返回 `409 CONFLICT`，且**目标行 `deleted_at` 仍为 NULL**（无部分写入）；
   - 只修改目标行，**不修改任何其他行**（R-DELETE-005）；
   - 子资源关系集合由各资源模块声明，服务不得硬编码「某个资源没有子资源」。
3. **`clusters` 的产品删除路径**：新增 `DELETE /api/clusters/{cluster_id}` → `204`（无响应体）。这是当前唯一存在资源的删除路径；`DELETE` 不提供 `by-name` 别名（写入一律走 `id`，ADR-0003 §2）。
4. **删除与唯一性的产品可观察结果**（R-DELETE-006）：删除 `name = X` 的 Cluster 后，可重新创建 `name = X` 的 Cluster 并成功；旧的已删行保留且 `deleted_at` 不变。
5. **读取侧后果端到端贯通**（R-DELETE-002）：删除后，该资源不再出现在列表 `items`、按 `id` 读取与 `by-name` 解析均返回 `404 NOT_FOUND`（读取路径本身由 F001 提供并复用 `app/db/active.py` 原语，F014 不重写）。
6. **不存在恢复能力**（R-DELETE-003）：不提供 restore / undelete 端点与页面；不存在把 `deleted_at` 置回 NULL 的任何路径。
7. **前端用户可见的删除动作**：在既有 Cluster 列表 / 详情页提供**可触发的删除入口**（仅对活跃资源），删除成功后被删资源从列表与详情中消失、进入 Not Found 态；失败时按 `error.code` 渲染（不解析 `message`）。具体交互形式（按钮位置、确认方式）由前端实现决定。
8. **一致性保障落成可失败测试**：单一写入路径的静态 guard；父删子拦的并发正确性测试；「删除只影响目标行」的断言；§21 的「绕过 UI 直接调用 API / 直接写库仍被拒」断言。

### 本次明确不包含

（用户 / 已确认规则明确排除，或已由 CONFIRMED 归属划定）

1. **任何资源级字段、校验、唯一性、状态与关系逻辑**：Cluster 校验（F001）、BareMetal 与 hostname 唯一、状态 `IDLE/ALLOC/DOWN/UNKNOWN`（F002）、NIC / IP（F004 / F005）、VM / Container（F006 / F007）、Service（F008）、查询视图（F009 / F010）、Excel 导入（F011）。
2. **新建任何资源表、迁移或 Schema 变更**（F002 / F004 / F005 各自建表）；F014 预期**不需要 migration**。
3. **对认证表的逻辑删除**：`users` / `sessions` 不适用本语义（`domain-model.yaml > authentication.note`）。
4. **物理删除 / 数据清理 / purge**：V1 无此类产品路径（R-DELETE-001；§23）。
5. **Undelete / Restore**（R-DELETE-003；`project-plan.yaml > out_of_scope`）。
6. **级联删除子资源**（R-DELETE-005）。
7. **审批流 / 工单 / 复杂 RBAC / 角色化的删除权限**（R-AUTH-003；§23）。
8. **`ip_address.cluster_id` 一致性治理**：数据库设计将该受控写入路径指定给「F014 领域服务」（`docs/database/csm-v1-schema-design.md` §3「关键设计决策 > 3」），但 **`ip_addresses` 表尚不存在**（F005 状态 BLOCKED，`depends_on: [F004]`）。F014 **无法交付**该能力的实现；F014 只交付「资源写入必须经统一领域服务」的机制，具体推导与一致性测试**在 F005 落地时必须实现**（见 NQ-2）。

### 本次未涉及

当前需求没有要求，但不能推断为永远不需要：

- 已删除资源的查询 / 审计视图（回收站、历史记录页、`include_deleted` 参数）；
- 删除操作的操作人 / 时间 / 原因记录（审计日志）；
- 批量删除、按条件批量清理；
- 已删数据保留期限、归档与最终物理清理策略；
- 删除通知 / 二次审批 / 影响面预览（「该集群下有 N 台裸金属」）；
- 删除对其他资源读取语义的影响（如 Service 归属推导在父资源已删时的呈现）。

## 交付边界裁定（对 5 个重点澄清的正面回答）

### 澄清 1：F014 是「基座」还是「某资源的删除端点」——**两者都是，且端点只落在 `clusters`**

**结论**：F014 交付「统一逻辑删除领域服务 + 删除守卫 + 一致性保障」这套基座，**同时**交付 `clusters`（当前唯一存在的资源）上的产品删除路径 `DELETE /api/clusters/{cluster_id}`。

依据（均为已确认文档，不是新规则）：

1. R-DELETE-001 的表述是「**正常产品操作**不得直接物理删除核心资源记录」——它预设存在一个正常的**产品删除操作**；`api-conventions.md` §6 已定义 `204 删除成功` 语义；ADR-0003 §2 明确「写操作（POST / PATCH / DELETE）一律走 `id` 路径」。删除是 V1 已确认的产品能力，不是纯内部机制。
2. R-DELETE-004 用「Cluster 仍存在有效 BareMetal 时不能删除 Cluster」作示例——**该示例本身预设 Cluster 是可删除的**。
3. `project-plan.yaml > F014` 的 AC 第 1 条是「正常产品操作不物理删除核心资源记录」；若 F014 不提供任何产品删除路径，该条在产品面上为空谈，且 R-DELETE-001 ~ 006 在 F014 中全部只能靠「直接写库」验证。
4. F001 已把删除**整体**推迟给 F014，并留下 Open #4「F014 是否把 `DELETE /api/clusters/{id}` 注册在 `app/clusters/router.py` 还是独立模块」——即端点归属 F014 是既定前提；F014 不做，则无人做（F001 已交付，F002 尚为 DRAFT，且 `project-plan` 未把 Cluster 删除归给任何其他 Feature）。
5. ADR-0004 §3 要求软删过滤与删除语义**统一提供、禁止各模块各写一套**——所以 F014 必须是唯一写入 `deleted_at` 的领域服务，各资源 Feature 只能委托。

**交付形态（产品层结论）**：F014 结束时——(a) 系统存在唯一的软删写入路径（统一服务）；(b) `DELETE /api/clusters/{cluster_id}` 可用，语义为 `204`；(c) 其他资源一旦落地，其删除端点**只能**委托同一服务，不得自建。

**明确不属于 F014（R-DELETE-004 的完整验收）**：**BareMetal 实体与 `bare_metals` 表属 F002**。因此在 F014 时点，「Cluster 存在活跃 BareMetal → 删除被拒」这一**具体业务场景不可端到端复验**（与 F001 的 R-CLUSTER-004 同类情形，见 `f001-cluster.md` NQ-4 与 `acceptance_criteria_note`）。

F014 对该条的承诺是**可判定的中间形态**（不削弱 AC）：

- 统一软删服务**必须**在删除路径上执行活跃子资源检查，检查失败即拒绝（`409 CONFLICT`）且不写入 `deleted_at`；
- 该检查在 F014 必须由测试证明「在删除路径上被真实调用且失败即拒绝」（允许使用声明的子资源检查点 / 测试夹具）；
- **真实业务场景**（Cluster + 活跃 BareMetal）的端到端验收，在 F002 落地 `bare_metals` 后由 F002 / 端到端测试完成（见 NQ-1）。

### 澄清 2：谁可以触发软删、通过什么产品路径——**存在 `DELETE /api/<resource>/{id}`，已认证用户即可**

- **产品路径**：`DELETE /api/clusters/{cluster_id}` → `204`；写操作走 `id`，**不提供** `DELETE .../by-name/{name}`（ADR-0003 §2）。
- **谁可以触发**：任何**已认证**用户。V1 只有「已认证 / 未认证」两态，**不存在**角色、权限、RBAC，也不允许为删除引入额外权限模型（R-AUTH-003；ADR-0005）。未认证访问 `/api/clusters*` → `401 UNAUTHENTICATED`（F013 已落地的 `/api/*` 认证边界）。
- **前端**：必须有用户可触发的删除入口（见 Scope #7）；F001 明确在 F014 落地前不显示删除入口（`f001-cluster.md` NQ-2），因此入口的出现属于 F014。
- **软删服务如何被产品路径使用**：`DELETE` 端点是"产品路径"，统一软删领域服务是"领域实现"；端点必须委托服务，不得自行 `UPDATE deleted_at`。不存在「服务无法被产品路径使用」的情形。

### 澄清 3：R-DELETE-006 与现实唯一性的关系——**F014 只做统一服务与守卫，不改变该语义**

- 语义已固定：**已逻辑删除的行不占用正常业务唯一性**，由 partial unique index（`ux_clusters_name_active`，predicate `deleted_at IS NULL`）保证（ADR-0002 §3、ADR-0004 §2；F012 基线已落地并由 `tests/database/*` 断言）。
- F014 **不改变**谓词、索引、collation 或大小写敏感语义，也**不得**新增 `UNIQUE` 表约束或 `lower()` 折叠（§22；ADR-0002 Alternatives）。
- F014 的增量价值是：把「删除 → 同名重建」从**直接写库可验证**升级为**产品路径可验证**（F001 的 A08 用直接置 `deleted_at` 验证；F014 后由 `DELETE` + `POST` 完成同一断言的端到端版本）。
- 一致性要求（ADR-0004 Consequences）：唯一索引 predicate 必须与查询过滤一致，否则会出现「查得到却写不进」。F014 不得引入任何与 `deleted_at IS NULL` 不一致的过滤或写入。

### 澄清 4：§21「关键冲突在保存前阻止」的 F014 落点——**只承担与删除相关的部分**

| §21 冲突项 | 归属 | F014 的角色 |
|---|---|---|
| 同 Cluster IP 重复 | F005 | 不实现 |
| 同 Cluster hostname 重复 | F002 | 不实现 |
| 全局 Cluster Name 重复 | F001（已交付，`ux_clusters_name_active` + 应用层预检） | 不重做、不改变语义 |
| 非法资源关系 | F002 / F004 / F005 / F008 | 不实现 |
| 非法状态值 | F002 | 不实现 |
| **删除导致的一致性风险**（父已删 + 子活跃、孤立记录、第二条软删路径、谓词漂移） | **F014** | 统一服务 + 单事务加锁守卫 + 静态 guard + 并发测试 |
| **通用错误信封与 SQLSTATE 映射机制** | F012（已交付） | 复用，不另立 |

F014 的 §21 承诺可归结为一条可验证命题：**删除相关的一致性不建立在「用户会通过界面操作」这一假设上**——绕过 UI 直接调用 API、绕过 API 直接写库、并发提交，都不会产生「父已删而子仍活跃」「已删却仍占用唯一性」「出现第二条软删写入路径」等结果。

### 澄清 5：无法从既有文档推出的问题

经逐条筛查，**未发现阻塞当前需求定义的产品问题**（判定过程见 Open Questions > Blocking）。凡属技术设计（端点注册位置、加锁协议、服务接口、测试夹具）一律交 Architect。

## Acceptance Criteria

每条均为可判定（是 / 否），描述用户可观察到的行为。与 `project-plan.yaml > F014.acceptance_criteria` 逐条对齐（见末尾映射表），可细化但未削弱。

- **AC-01（逻辑删除而非物理删除，R-DELETE-001）**：对一个活跃 Cluster 执行 `DELETE /api/clusters/{id}` → `204`；该记录**仍存在于数据库中**，且删除标记非空；系统不存在任何可物理删除核心资源记录的产品端点。
- **AC-02（已删不出现在常规查询，R-DELETE-002）**：删除后，该 Cluster 不出现在 `GET /api/clusters` 的 `items` 与 `total` 中；`GET /api/clusters/{id}` 与 `GET /api/clusters/by-name/{name}` 均返回 `404 NOT_FOUND`（Empty 与 Not Found 仍可区分，R-QUERY-004）。
- **AC-03（无恢复能力，R-DELETE-003）**：产品中不存在 Undelete / Restore 端点与页面；不存在任何将删除标记置回空值的代码路径（可由静态 guard 断言）；已删资源重复删除 → `404 NOT_FOUND`。
- **AC-04（父有活跃子资源时不得删除，R-DELETE-004）**：删除前在同一事务内执行活跃子资源检查；存在活跃子资源时 → `409 CONFLICT`，**目标行删除标记仍为空**（无部分写入），响应经统一错误信封返回稳定 `code`。F014 必须由测试证明该检查在删除路径上被真实调用且失败即拒绝；「Cluster + 活跃 BareMetal」的完整业务场景在 F002 落地后复验（见 NQ-1）。
- **AC-05（不级联，R-DELETE-005）**：删除操作只修改目标行；删除父资源不会修改任何子资源行的删除标记，也不会删除任何其他记录。数据库 Schema 中不存在 `ON DELETE CASCADE`。
- **AC-06（已删释放唯一性，R-DELETE-006）**：删除 `name = X` 的 Cluster 后，可重新 `POST /api/clusters` 创建 `name = X` → `201`；此时查询只看到新的活跃记录；旧的已删行仍保留且删除标记未被改写。
- **AC-07（关键冲突在保存前阻止，不只依赖 UI，§21）**：绕过界面（直接调用 API）或绕过 API（直接向数据层写入）都不能产生违反上面规则的状态；「父有活跃子」这一冲突在后端被判定义务，前端按钮是否禁用不影响结果。
- **AC-08（唯一软删写入路径）**：系统内不存在第二条写入删除标记的产品路径；所有资源删除一律委托统一软删领域服务（可由静态 guard 断言；该 guard 由 F001 的「`deleted_at` 写入路径数 = 0」断言演进而来）。
- **AC-09（并发正确性，ADR-0004 §5）**：并发执行「创建子资源」与「删除父资源」时，结果只可能是二者之一——子资源创建成功且父删除被拒（`409`），或父删除成功且子创建被拒；**不存在**「父资源已删 + 子资源活跃」的状态。
- **AC-10（前端删除动作与状态）**：Cluster 列表 / 详情页存在用户可触发的删除入口；删除成功后该资源从列表与详情中消失，详情进入独立的 Not Found 态（不显示为普通错误或空白）；删除失败时按 `error.code` 渲染（不解析 `message`）。
- **AC-11（无越界能力）**：产品中不存在查看已删资源、恢复、批量删除、清空历史的入口（R-DELETE-003；§23；`project-plan.yaml > out_of_scope`）。
- **AC-12（认证边界）**：未认证调用 `DELETE /api/clusters/{id}` → `401 UNAUTHENTICATED`，且不改变任何数据；已认证用户即可删除，不需要任何角色 / 权限（R-AUTH-003；ADR-0005）。
- **AC-13（非资源表不受影响）**：`users` / `sessions` 不因本 Feature 获得删除标记列或软删语义；登出 / 过期会话的既有行为不变（`domain-model.yaml > authentication.note`）。

**与 `project-plan.yaml > F014.acceptance_criteria` 的映射（不削弱）**：

| plan AC | 本 Handoff |
|---|---|
| 正常产品操作不物理删除核心资源记录（R-DELETE-001） | AC-01 |
| 已逻辑删除资源默认不出现在常规查询（R-DELETE-002） | AC-02 |
| V1 不提供 Undelete / Restore（R-DELETE-003） | AC-03 |
| 父资源存在活跃子资源时不允许删除父资源（R-DELETE-004） | AC-04（+ NQ-1 的归属说明） |
| 逻辑删除不自动级联删除子资源（R-DELETE-005） | AC-05 |
| 已逻辑删除资源不再占用正常业务唯一性，可重新创建同名资源（R-DELETE-006） | AC-06 |
| 关键冲突在保存前阻止，不仅依赖 UI 校验（§21） | AC-07、AC-08、AC-09 |

## Assumptions

（不阻塞当前工作、可安全暂时采用；**不得当作 CONFIRMED**）

1. F012 / F013 / F001 已 DONE，系统当前产品面为 `/api/health`、认证端点与 5 个 `/api/clusters*` 端点；`clusters` 是唯一资源表。F014 在其上增量交付，不重做基座。
2. F014 **不需要 schema / migration 变更**：`clusters` 已有 `deleted_at` 与 `ux_clusters_name_active`（`0001_f012_baseline`，已冻结），删除语义所需结构齐备。
3. 统一软删领域服务可被后续资源模块复用而无需结构性改动（F002 ~ F008 建表后在各自模块内委托）。
4. R-DELETE-004 的真实业务场景验收按澄清 1 的结论在 F002 落地后复验；F014 内以守卫机制 + 测试夹具验证。
5. 删除的默认成功语义为 `204`（`api-conventions.md` §6 已确认）；前端删除入口的具体交互形式不构成产品规则。
6. `project-plan.yaml > F014.layers` 目前为空；本 Handoff 的产品范围同时涉及 backend 与 frontend（见 Architecture Handoff #8）。

## Proposed Rules

**PROPOSED-1（需用户裁定，非 CONFIRMED）**：是否需要「删除前展示影响面」（例如「该集群下有 3 台裸金属，无法删除」的具体提示）。V1 已确认的仅是 `409 CONFLICT` 语义；更丰富的提示文案属实现细节，但「影响面预览」是新增产品能力，本 Feature **不实现**。

**PROPOSED-2（需用户裁定，非 CONFIRMED）**：删除是否需要记录操作人 / 时间 / 原因（审计）。当前 `deleted_at` 仅表达「何时被删」；R-DELETE-002 只要求不出现在常规查询，未要求审计追溯。本 Feature **不实现**任何审计字段、操作日志或原因输入。

**PROPOSED-3（需用户裁定，非 CONFIRMED）**：已删数据的保留期限与最终清理策略。当前无任何已确认规则（`lifecycle.persistence_note` 只规定「删除标记由数据库设计决定」）。在无明确规则前，**一律保留、不清理**——这是「未定义即不做」的直接后果，不得被解读为 CSM 已确认「永久保留」。

**PROPOSED-4（属 F002 的产品问题，非本 Feature）**：是否允许删除处于 `ALLOC`（已分配 / 使用中）状态的 BareMetal。R-DELETE-* 未对状态作任何限制，F014 **不得**为此预设规则；该问题必须在 F002 的 Product 阶段确认。

## Open Questions

### Blocking

**无。**

逐条对照阻塞判定标准（`不确认就无法确定本次功能范围` / `导致两种明显不同的用户行为` / `改变核心领域关系` / `导致验收标准无法定义`）：

| 候选问题 | 判定 | 依据 |
|---|---|---|
| F014 是否引入产品删除端点 | **非阻塞**：唯一自洽的读法只有一种 | R-DELETE-001 的「正常产品操作」+ `api-conventions.md` §6 的 `204` + ADR-0003 §2 的「写操作走 id」+ R-DELETE-004 的 Cluster 示例 + F001 的显式推迟与 Open #4 → F014 必须提供 `DELETE /api/clusters/{id}`（澄清 1） |
| 谁可以删除 | **非阻塞**：已确认规则直接给出 | 认证边界 ADR-0005 + R-AUTH-003 禁止 RBAC → 任何已认证用户 |
| R-DELETE-004 在无子资源时是否可验收 | **非阻塞**：F001 已有同类先例与处理方式 | `f001-cluster.md` NQ-4 / `acceptance_criteria_note`：Feature 内不可判定的关系规则由「机制可判定 + 场景归后续 Feature」处理，不改产品规则 |
| R-DELETE-006 是否改变 | **非阻塞**：语义已由 ADR-0002/0004 固定 | partial unique index；F014 只做统一服务与守卫（澄清 3） |
| §21 哪些属 F014 | **非阻塞**：归属清晰 | `domain-model.yaml > data_consistency` 的具体冲突项逐条归属各资源 Feature；F014 承担删除相关一致性（澄清 4） |
| `ip_address.cluster_id` 一致性治理归属 | **非阻塞（但需计划修正）** | 表不存在（F005 BLOCKED），F014 无法实现；不影响 F014 自身范围与 AC 判定（NQ-2） |
| 已删数据的保留期限 / 审计 | **非阻塞**：当前无需求 | 属「本次未涉及」，不实现、不承诺（PROPOSED-2/3） |

### Non-blocking

- **NQ-1（R-DELETE-004 真实场景的验收归属）**：`bare_metals` 表属 F002（当前 DRAFT）。建议：F014 交付并测试「统一服务的活跃子资源守卫在删除路径上被调用且失败即拒绝」；「Cluster + 活跃 BareMetal → 删除返回 `409`」的端到端验收在 F002 的 AC 中显式列出。属**计划归属细化**（与 F001 把 R-CLUSTER-004 归入 F002/F009 同类），**不修改产品规则、不削弱 F014 的 AC**。请 Project Manager / Architect 确认。
- **NQ-2（`ip_address.cluster_id` 一致性治理的归属迁移）**：`docs/database/csm-v1-schema-design.md` §3 把该受控写入路径指定给「F014 领域服务」，但 `ip_addresses` 表属 F005（BLOCKED，`depends_on: [F004]`）。建议：该条归属改为 **F005**（在其建表时实现推导与一致性测试），并要求其写入经 F014 的统一服务机制。请 Project Manager 更新归属。
- **NQ-3（其他资源的删除端点归属与出现时机）**：BareMetal / NIC / IP / VM / Container / Service 的 `DELETE` 端点属各自 Feature（F002 / F004 / F005 / F006 / F007 / F008），但需 Architect 确认这是否作为「每个资源 Feature 必须提供删除端点」的统一约定——`project-plan.yaml` 目前未在任何资源 Feature 的 AC 中列出删除。**F014 的约束是**：若提供，必须委托统一服务，不得自建第二条路径。
- **NQ-4（前端删除入口的落点）**：入口出现在 Cluster 列表页还是详情页、是否需要二次确认，属实现细节；F014 只要求「存在用户可触发的产品路径 + 结果状态正确」。
- **NQ-5（已删资源的可见性出口）**：是否需要「查看已删记录」的出口（管理 / 排障）当前无需求；本 Feature 拒绝在常规查询中暴露（R-DELETE-002）。
- **NQ-6（审计与保留期限）**：见 PROPOSED-2 / PROPOSED-3。
- **NQ-7（删除端点注册位置）**：`app/clusters/router.py` 还是独立模块——架构决策，不影响产品行为（`f001-cluster-handoff.md` Open #4）。
- **NQ-8（并发拒绝的表现形式）**：并发下被拒一侧返回 `409 CONFLICT` 还是其它稳定 code，属架构 / 契约细节；产品只要求「不得出现父已删子活跃」。

## Architecture Handoff

以下为 Architect 需要解决的技术设计问题（本 Handoff 不选择框架、不设计表、不定义 API 细节）：

1. **统一软删领域服务的接口与边界**：定义「唯一软删写入路径」的接口形态；各资源模块如何显式委托；如何在结构上（而非仅靠约定）阻止第二条写入 `deleted_at` 的路径（回应 AC-08；ADR-0004 §3）。**不得**扩大为通用资源抽象、EAV 或多态基类（§4、§24）。
2. **活跃子资源检查的声明机制**：统一服务如何获得「某资源的活跃子资源集合」——由资源模块声明检查点、注册回调，还是其它方式。设计要求：不得硬编码「某资源没有子资源」；新增子资源时不需要修改统一服务的核心逻辑。
3. **父删子拦的事务与加锁协议**：落实 ADR-0004 §5（同一事务内检查活跃子资源 + 对父行加锁），使 AC-09 的并发断言可被测试复现（含测试如何构造并发窗口）。
4. **API 契约落点**：`DELETE /api/clusters/{cluster_id}` 与 `204` / `404` / `409` 语义应写入哪份契约（新增 F014 契约文件，或扩展 `docs/api/f001-cluster.md`）；并确认 `by-name` 不提供 DELETE、重复删除返回 `404 NOT_FOUND`。契约 Status 需在实现前达到 `READY`。
5. **删除时的错误信封细节**：`409 CONFLICT` 的稳定 `code` 与 `details[]` 形态（是否含字段 / 冲突类型），复用 F012 既有机制，不得另立一套（`f012-project-foundation-handoff.md` Q1）。
6. **R-DELETE-005 的验证方式**：在无子资源的当下，「删除不级联、只改目标行」如何被真实断言（结构 guard + 行为断言）；以及 Schema 层「无 CASCADE」的 guard 归属。
7. **R-DELETE-004 在 F014 内的可验证形态**：在不存在子资源表的前提下，如何验证「守卫存在且被调用」（测试夹具 / 声明的检查点）；并明确 F002 落地后必须补的端到端场景，避免该 AC 在 Feature 交接中静默丢失（回应 NQ-1）。
8. **交付层判定**：`project-plan.yaml > F014.layers` 目前为空；请依本 Handoff 判定 database / backend / frontend 三项（本 Feature 预期 `database: false`）。
9. **前端接线**：删除入口落点、删除成功后的列表 / 详情状态刷新与 Not Found 态、失败按 `error.code` 渲染；不得在**前端**重复实现业务规则（删除守卫必须在后端，§21）。
10. **`ip_address.cluster_id` 机制的交接**：F014 只需保证「统一领域服务」的存在与可复用性；F005 实现推导与一致性测试时如何接入该服务（回应 NQ-2）。
11. **F001 遗留 guard 的演进**：F001 的 A15 断言「`backend/app/**` 中不存在任何 `deleted_at` 赋值语句（当前为 0 处）」在 F014 后必然失效；需定义新的等价断言（写入点恰好收敛于统一服务 + 各资源委托），避免验证力静默丢失。

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。题目列出的 5 个重点澄清均已在「交付边界裁定」中给出明确产品结论，全部可由 CONFIRMED 文档（R-DELETE-001~006、§17、§21、§22、§23、§25、`domain-model.yaml > lifecycle / data_consistency`、ADR-0002/0003/0004/0005、`api-conventions.md`、`f001-cluster-handoff.md`、`f012-project-foundation-handoff.md`）推导，无需新增或变更任何产品规则。NQ-1 / NQ-2 为计划归属细化，不阻塞架构设计，但请求 Project Manager 在 F014 阶段同步更新 `project-plan.yaml` 的 AC / requirement 归属。