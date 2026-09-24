# Architecture Handoff — F014 逻辑删除与数据一致性治理

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-16
> Feature: F014（ENABLER，E07，P0，`depends_on: [F012]`）
> Git: `feature/F014-soft-delete`，base `develop` = `897b32539927c137b933aa0ebed700d3bc26be5b`
> 配套契约：`docs/api/f014-soft-delete.md`（`READY`）

---

## Feature

逻辑删除与数据一致性治理（F014）— CSM V1 的逻辑删除领域基座：**唯一软删写入路径**、**删除守卫（父删子拦 / 不级联 / 单事务加锁）**，以及 `clusters` 资源上的**产品删除路径** `DELETE /api/clusters/{cluster_id}`。

## Product Source

- `docs/product/handoffs/f014-soft-delete.md`（`READY FOR ARCHITECT`，主要输入，无 Blocking）
- `docs/product/requirements.md`（§17 R-DELETE-001~006、§21、§22、§23、§24、§25、§26）
- `docs/product/domain-model.md` / `domain-model.yaml`（`lifecycle` / `data_consistency` / `uniqueness_rules`）
- `.pi/skills/resource-domain/SKILL.md`
- ADR-0001（技术栈）、ADR-0002（PostgreSQL / 唯一性）、ADR-0003（BIGINT id / 错误信封）、**ADR-0004（deleted_at + partial unique index + 统一软删 + 加锁）**、ADR-0005（认证两态）
- `docs/architecture/csm-v1-foundation-architecture.md`、`docs/architecture/f012-project-foundation-handoff.md`（Q1 / Q2 / Q3 / Q5）、`docs/architecture/f001-cluster-handoff.md`（问题 1 / 问题 2 / 问题 8 / Open #4）
- `docs/database/csm-v1-schema-design.md`（决策 5 / 6 / 8；`clusters` 冻结）、`docs/database/f012-baseline-migration.md`
- `docs/api/api-conventions.md`（§2 / §5 / §6 / §7）、`docs/api/f001-cluster.md`（§2 / §10）
- `docs/project/v1/project-plan.yaml`（F014 条目）

---

## 现状核实（只读检查结论）

| 项 | 现状（已核实） |
|---|---|
| Backend | **已存在** `backend/app/**`：应用工厂（`main.py`）、`/api/health`、认证中间件与 auth 模块（F013）、`clusters` 模块 5 个端点、统一错误信封 + 全局 handler（`common/errors.py` / `error_handlers.py`）、通用 SQLSTATE→HTTP 映射（`common/sqlstate.py`）、分页、请求级事务边界（`api/deps.py`）、活跃行过滤原语（`db/active.py`） |
| `deleted_at` 写入路径数 | **0**（`backend/app/**` 中无任何 `.deleted_at` 赋值；`SELECT`/过滤除外） |
| `DELETE /api/clusters/{id}` | **未注册**（`app/clusters/router.py` 仅 POST/GET/GET/GET/PATCH 五个端点） |
| Frontend | **已存在** `frontend/src/**`：`api/http.ts`（错误归一）、`components/ListStates.vue` / `ErrorState.vue`、`composables/useAsyncQuery.ts`、`pages/ClusterListPage.vue`（三态 + 分页）、`pages/ClusterDetailPage.vue`（独立 Not Found 态）、`pages/LoginPage.vue`、`App.vue` 极简视图切换（**无 vue-router**）。**无删除入口** |
| Database | **已存在** `clusters` 表（`id / name / created_at / updated_at / deleted_at`）+ `ck_clusters_name_no_slash` + `ux_clusters_name_active`（partial unique，`WHERE deleted_at IS NULL`），由 `0001_f012_baseline` 建立并冻结；`users` / `sessions`（`0002_f013_auth`）。**`bare_metals` 及后续资源表均不存在** |
| 相关领域对象 | `Cluster`（`app/models/cluster.py`）。**无**子资源实体 |
| 相关架构决策 | ADR-0001~0005 全部 `ACCEPTED`；F012 已裁定「过滤原语归 F012、软删领域服务归 F014」 |
| 现有 guard | `tests/test_clusters_guards.py::test_a15_no_deleted_at_assignment_in_app_source`（断言写入数 = 0）、`tests/test_auth_guards.py::test_g_e_no_deleted_at_assignment_in_app_source`（扫描**全部** app 源码，断言写入数 = 0）、`test_clusters_api.py::test_a15_delete_endpoint_does_not_soft_delete`（DELETE 不软删）。**F014 落地后这三条必然失效，必须演进，见「问题 11」。** |

**结论**：F014 是在非空、已具基座的项目上的增量交付；删除语义所需结构（`deleted_at` + partial unique index）**已齐备**，无需 schema / migration。

---

## Architecture Summary

**目标**：让「删除」成为唯一、可审计、并发正确的产品动作，并把这条语义做成 F002~F011 必须复用的唯一基座。

**方案要点**：

1. **统一软删领域服务**：新增 `backend/app/deletion/`，其中 `service.py` 的 `soft_delete()` 是**系统内唯一允许写 `deleted_at` 的代码路径**。所有资源删除端点一律委托它，各资源模块不得自建第二条路径（ADR-0004 §1/§3）。
2. **单事务加锁协议**：`soft_delete()` 在**当前请求事务内**（F012 事务边界基座）先 `SELECT … FOR UPDATE` 锁目标活跃行（未命中 → `404`），再执行**资源模块声明的活跃子资源检查**（命中 → `409` 且不写 `deleted_at`），最后**只改目标行**的 `deleted_at`（不再触碰任何其他行）。
3. **活跃子资源检查声明机制**：由**资源模块**以模块级常量显式声明 `ActiveChildCheck` 元组，并在该资源的删除路径显式传给 `soft_delete()`。统一服务不硬编码「某资源有无子资源」；新增子资源只需在父资源的声明处追加一个检查，**不需要改动统一服务核心逻辑**。
4. **`clusters` 产品删除路径**：在 `app/clusters/router.py` 注册 `DELETE /api/clusters/{cluster_id}` → `204`（无响应体）；委托 `soft_delete()`；**不提供** `by-name` 写别名。
5. **读取侧后果复用既有实现**：删除后的「不出现在列表 / 按 id 与 by-name 均 404」完全复用 F001 已有读取路径与 `app/db/active.py` 原语，F014 **不重写过滤谓词**。
6. **错误信封复用 F012**：`404 NOT_FOUND`、`409 CONFLICT`（`details[].code = "ACTIVE_CHILDREN_EXIST"`）、`401 UNAUTHENTICATED` 均由既有 `common/errors.py` / `error_handlers.py` / `sqlstate.py` 产生，**不另立一套**。
7. **无 schema / migration 变更**（预期 `database: false`）。
8. **不引入任何新框架 / 中间件 / 依赖**；不引入 EAV / 通用 `resources` 表 / STI / ORM 多态基类（§24；F012 Q3 的元数据 guard 继续生效）。
9. **验证力不静默丢失**：F001 的 A15 guard 与 F013 的 G-E guard 必须**演进为「写入点收敛于唯一服务文件」的 allow-list 断言**，不得删除后不补。

---

## Domain Impact

**无。** 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。

- 使用已有领域对象 `Cluster`（R-DELETE-001/002/003/006 的产品承载）。
- `R-DELETE-004`（父有活跃子资源不得删）与 `R-DELETE-005`（不级联）在 F014 内**不产生新的实体**：不建 `bare_metals` 表、不加 `cluster_id` 列、不加任何子资源结构 —— 子实体归 F002。
- 认证表 `users` / `sessions` **不是** Resource，不适用软删语义（§17；`domain-model.yaml > authentication.note`）。F014 不得把 `deleted_at` 扩大到认证表。
- 不引入角色 / 权限 / RBAC（R-AUTH-003；ADR-0005）；`403 FORBIDDEN` 仍**无触发路径**。

---

## Data Layer Impact

**不需要任何 Schema 变更、索引变更或 migration。`database: false`。**

F014 依赖以下**已由 F012/F013 基线保证**的事实（Backend 可直接假设）：

- `clusters` 列集合恰为 `{id, name, created_at, updated_at, deleted_at}`；`deleted_at TIMESTAMPTZ NULL`；`deleted_at IS NULL` 是「活跃」的唯一判定条件。
- `ux_clusters_name_active`（partial unique，predicate `deleted_at IS NULL`）保证「活跃同名至多一条、大小写敏感、已删释放唯一性」（R-DELETE-006）。
- 全部 FK（现有仅 `sessions.user_id`）为 `ON DELETE RESTRICT`；无 `ON DELETE CASCADE`。

数据层**唯一**新增内容是**测试断言**（不是 Schema）：

1. **全局「无 CASCADE」guard**：扫描 `information_schema` / `pg_constraint`，断言不存在任何 `confdeltype = 'c'`（CASCADE）的外键。该断言在 F014 时点为「真空成立」（`clusters` 无 FK），但其价值随 F002+ 建表而生效。
2. **`clusters` 结构不变 guard**：列集合、CHECK 集合、`ux_clusters_name_active` predicate 的既有断言**原样保留**（F012 T2/T5 与 F001 G2）。
3. **「删除只改目标行」的行为断言**：删除前后对 `clusters` 全表快照比对（见 Test Work T-07）。

**明确不做**：新表、新列、新索引、新约束、`COLLATE`、触发器、`audit_log` / `created_by` / `version` 列、任何 migration。

---

## Backend Work

Backend Agent 需交付以下**能力**：

### 1. 统一软删领域服务（新模块 `backend/app/deletion/`）

| 文件 | 职责 |
|---|---|
| `checks.py` | 定义 `ActiveChildCheck` 协议 / 类型（`(Session, parent_id) -> bool`，True = 存在活跃子资源），以及资源模块声明检查点所需的类型与文档 |
| `service.py` | **唯一**写 `deleted_at` 的函数 `soft_delete(session, resource_model, resource_id, *, active_children)` |
| `__init__.py` | 导出 `soft_delete` 与 `ActiveChildCheck` |

`soft_delete()` 的**行为契约**（实现细节由 Backend 决定）：

1. 在**调用方事务内**执行 `SELECT <model> WHERE id = :id AND deleted_at IS NULL FOR UPDATE`；未命中 → `NotFoundError`（404）。
2. 依次执行传入的每个 `ActiveChildCheck`；任一返回 True → `ConflictError`（409，`details=[{"field": None, "code": "ACTIVE_CHILDREN_EXIST", ...}]`），**且不写 `deleted_at`**。
3. 仅对**已锁定的目标行**赋值 `deleted_at = now()`（`updated_at` 由既有 `onupdate` 维护），`flush()`。
4. **不得**触碰任何其他行；**不得**物理删除；**不得**回写 `deleted_at` 为空（无 undelete）。
5. 不在服务内部 `commit` / `rollback`（事务边界由 F012 的 `api/deps.py` 统一负责）。

### 2. `clusters` 删除路径（改 `app/clusters/`）

| 文件 | 变更 |
|---|---|
| `deletion.py`（新） | 声明 `CLUSTER_ACTIVE_CHILD_CHECKS: ActiveChildCheck 元组 = ()`（由 Cluster 资源模块显式声明；F002 落地时在此追加 `bare_metals` 的活跃检查） |
| `service.py` | 新增 `delete_cluster(session, cluster_id)`：委托 `soft_delete(session, Cluster, cluster_id, active_children=CLUSTER_ACTIVE_CHILD_CHECKS)` |
| `router.py` | 新增 `DELETE /clusters/{cluster_id}` → `status_code=204`，无 `response_model`；委托 service；**声明顺序仍保持 `by-name` 早于 `/{cluster_id}`**（不提供 by-name 删除） |
| `schemas.py` / `validation.py` / `repository.py` | **不改**（删除不需要请求体与领域校验；读取过滤原语不变） |

### 3. 明确不做

其他资源端点、`bare_metals` 等实体、物理删除 / purge、restore / undelete、批量删除、审计字段、`ip_addresses.cluster_id` 推导（表不存在）、任何 schema 变更、任何新依赖。

---

## Frontend Work

Frontend Agent 完成：

1. **`frontend/src/api/clusters.ts`**：新增 `deleteCluster(clusterId: number): Promise<void>`（`DELETE /api/clusters/{id}`；`204` 视为成功；错误经 `api/http.ts` 归一为 `ApiError`）。**不新建**请求层。
2. **`ClusterListPage.vue`**：为每行增加用户可触发的**删除入口**（按钮 + 二次确认，交互形式自定）。
   - 成功（`204`）→ 刷新列表；被删行消失；若当前页因此变空，按 Empty 态渲染。
   - `409 CONFLICT` → 保留行，按 `error.code === 'CONFLICT'` 渲染冲突提示；**不得**解析 `error.message` 做业务判断。
   - `404 NOT_FOUND` → 视为「已不存在」，刷新列表即可（不报未知错误）。
   - `401 UNAUTHENTICATED` → 交由既有全局会话失效处理（F013 行为：回登录页）。
   - 提交中按钮进入 Loading 且禁止重复提交。
3. **`ClusterDetailPage.vue`**：增加删除入口；成功后进入既有**独立 Not Found 态**（`404` 分支，`state === 'not-found'`），或返回列表；失败按 `error.code` 渲染（`409` 冲突 / 其他错误）。
4. **禁止在前端重复实现删除守卫**（§21）：「父有活跃子资源」由后端 `409` 裁决，前端**不得**自行判断或隐藏入口来替代后端校验。是否禁用按钮纯属体验，不影响正确性。
5. **不做**：恢复 / 回收站 / 已删资源查看 / 批量删除 / 审计展示 / BareMetal 相关 UI。

**文件所有权（并行安全）**：Frontend 拥有 `frontend/**`；Backend 拥有 `backend/**`、`tests/**`；共享 `docs/**` 由协调器统一落盘。

---

## API Contract

### Status

```text
READY
```

### Contract

完整正文见 **`docs/api/f014-soft-delete.md`**（本 Feature 的唯一权威契约）。要点：

- 端点：`DELETE /api/clusters/{cluster_id}`，成功 **`204`**（无响应体）。
- `404 NOT_FOUND`：id 不存在**或**已被逻辑删除（不区分）。
- `409 CONFLICT`：存在活跃子资源；信封 `details[].code = "ACTIVE_CHILDREN_EXIST"`。
- `401 UNAUTHENTICATED`：未认证；不改变任何数据。
- **不提供** `DELETE /api/clusters/by-name/{name}`。
- `docs/api/f001-cluster.md` **不修改**：其 §10 已显式声明 DELETE 属 F014，两文件通过引用保持一致，无正文重复。

---

## Test Work

Testing Agent 应验证以下**最小集合**，逐条映射 AC-01 ~ AC-13。

| # | 测试 | 层次 | AC |
|---|---|---|---|
| **T-01** | 已认证 `DELETE /api/clusters/{id}`（活跃 Cluster）→ `204` 且**无响应体**；原始连接断言：该行**仍物理存在**、`deleted_at IS NOT NULL`、`clusters` 行数不变（无物理删除） | API + DB | AC-01 |
| **T-02** | 删除后：不出现在 `GET /api/clusters.items` 与 `total`；`GET /{id}` → `404 NOT_FOUND`；`GET /by-name/{name}` → `404 NOT_FOUND`；无活跃行时列表仍 `200` + `items==[]`（Empty 与 Not Found 仍可区分） | API + DB | AC-02 |
| **T-03** | 对已删 id 再次 `DELETE` → `404 NOT_FOUND`，`deleted_at` 不被改写；不存在任何恢复 / undelete 端点（负向路由断言） | API | AC-03 |
| **T-04** | **§21 服务端强制**：直接调用 `DELETE`（无 UI）即触发后端守卫；构造「有活跃子资源」的注入检查 → `409`（T-05）。前端是否禁用按钮不影响结果 | API | AC-07 |
| **T-05** | **父删子拦机制**：Cluster 删除路径注入一个返回 True 的 `ActiveChildCheck` → `DELETE` → `409 CONFLICT`，`details[].code == "ACTIVE_CHILDREN_EXIST"`，且目标行 `deleted_at` **仍为 NULL**（无部分写入）、行仍物理存在 | API + DB | AC-04 |
| **T-06** | **守卫真实被调用 + 锁序**：注入 spy 检查点，断言删除路径确实调用它；并断言检查点执行时目标父行已被**本事务**加锁（另一连接对同一行 `FOR UPDATE NOWAIT` 在检查点执行期间失败 / 阻塞） | 并发（DB） | AC-04、AC-09 支撑 |
| **T-07** | **不级联、只改目标行**：建活跃 A、B；删 A 后：B 的 `deleted_at`/`name`/`updated_at` 不变；`clusters` 全表除 A 的 `deleted_at` 外无差异；无任何行被物理删除 | API + DB | AC-05 |
| **T-08** | **释放唯一性**：删 `name=X` 后 `POST /api/clusters {"name":X}` → `201`；列表只见新行；旧已删行仍保留且 `deleted_at` 未被改写 | API + DB | AC-06 |
| **T-09** | 删除后 `GET /api/clusters` 的 Empty 与 `GET /{id}` 的 Not Found 渲染 / 语义不同（契约层断言，前端由 FE 测试承接） | API | AC-02、AC-10 |
| **T-10** | 未认证 `DELETE /api/clusters/{id}` → `401 UNAUTHENTICATED` 且**数据不变**（`deleted_at` 仍 NULL）；已认证普通用户即可删除；不存在角色 / 权限依赖 | API + DB | AC-12 |
| **T-11** | **非资源表不受影响**：`users` / `sessions` 无 `deleted_at` 列、无软删代码路径；登出 / 会话过期既有行为不变（保留 F013 测试） | DB + API | AC-13 |
| **T-12** | **无越界能力**：不存在查看已删 / restore / 批量删除端点与查询参数（负向路由 / 参数断言） | API | AC-11 |
| **T-13** | **并发正确性（F014 可验证形态）**：另一连接持有目标行 `FOR UPDATE` 时，`DELETE` **阻塞等待**而非基于快照直接更新；释放后按预期完成（成功或 `409`）。证明删除使用阻塞行锁 | 并发（DB） | AC-09 |
| **G-1** | **无 CASCADE**：数据库中不存在任何 `ON DELETE CASCADE` 外键（`confdeltype='c'`） | DB Schema | AC-05 |
| **G-2** | **clusters 结构不变**：列集合、CHECK 集合、`ux_clusters_name_active` predicate 断言原样通过（F012/F001 既有测试保留） | DB Schema | 约束 |
| **G-3** | **唯一软删写入路径（静态 allow-list）**：`backend/app/**` 中写 `deleted_at` 的文件集合**恰好为** `{backend/app/deletion/service.py}`；且**不存在**任何写 `deleted_at = None` 的路径（R-DELETE-003） | 静态 guard | AC-03、AC-08 |
| **G-4** | **认证表无软删**：`users` / `sessions` 无 `deleted_at` 列（保留 F013 既有断言） | DB Schema | AC-13 |
| **T-FE-01** | 列表 / 详情存在删除入口；成功后被删资源从列表 / 详情消失，详情进入独立 Not Found 态；`409` 与 `404` 分别按 `error.code` 渲染；提交中 Loading；前端不重复实现业务规则 | 前端组件 | AC-10 |

**必须同步演进的既有测试（不可删除后不补）**：

- `tests/test_clusters_guards.py::test_a15_no_deleted_at_assignment_in_app_source` → 改为 G-3 的 allow-list 形式。
- `tests/test_auth_guards.py::test_g_e_no_deleted_at_assignment_in_app_source` → 收窄到 `app/auth/**`（其意图本就是「认证代码不写 `deleted_at`」，已由 `test_g_e_auth_module_declares_no_deleted_at` 覆盖），或直接复用 G-3。
- `tests/test_clusters_api.py::test_a15_delete_endpoint_does_not_soft_delete` → 由 T-01（DELETE **确实**软删、行仍存在）取代。

**明确不在 F014 测试范围（交接给 F002）**：真实「Cluster + 活跃 BareMetal → `409`」端到端；并发「创建 BareMetal vs 删除 Cluster」的孤立记录不变式；`ip_addresses.cluster_id` 漂移。见「问题 7」「问题 10」。

---

## Architecture Handoff — 11 问逐条回应

### 问题 1 — 统一软删领域服务的接口与边界；结构性阻止第二条写入路径；禁止 EAV / 多态基类 / 通用 resources 表

**结论**：

- **接口**：`soft_delete(session, resource_model, resource_id, *, active_children: Sequence[ActiveChildCheck]) -> Model`，位于 `backend/app/deletion/service.py`。它是系统内唯一写 `deleted_at` 的函数。行为见 Backend Work §1。
- **边界**：服务只负责「锁父行 → 跑声明的子资源检查 → 只改目标行 `deleted_at`」。它**不**知道任何资源的具体字段、不提供通用 CRUD、不抽象资源实体。它参数化于 `SoftDeleteMixin` 模型类（与既有 `active_filter[ModelT: SoftDeleteMixin]` 同一模式），**不是**多态基类。
- **调用方边界**：各资源模块提供自己的 `delete_<resource>()` 领域函数委托 `soft_delete()`；HTTP 路由只做编排。资源模块**不得**自写 `UPDATE … deleted_at`。
- **结构性阻止第二条路径**：以**静态 allow-list guard**（G-3）强制：扫描 `backend/app/**` 中所有 `deleted_at` 写入形态（`.deleted_at =`、`values(deleted_at=`、`setattr(..., "deleted_at", ...)`、`mappings` 中的 `deleted_at`），断言出现写入的文件集合**恰好为** `{app/deletion/service.py}`，并断言无 `deleted_at = None`。写入点从「0 处」（F001 A15）演进为「恰好 1 处文件」，验证力不降低。

**被拒绝的替代方案**：

| 方案 | 拒绝理由 |
|---|---|
| 通用 `Resource` ORM 基类 / 带 `type` 判别列的 STI / `polymorphic_on` | 违反 §24；F012 Q3 的元数据 guard（`test_no_polymorphic_mappers_or_discriminator` / `test_no_orm_inheritance_at_all`）会直接失败 |
| EAV（通用 `attribute/value` 表）或 JSONB 万能属性列 | 违反 §24；`test_no_json_or_jsonb_columns` / `test_no_eav_shape` 会失败 |
| 通用 `resources` 表 | 违反 §24；`test_no_generic_resources_table` / `test_only_expected_tables_registered` 会失败 |
| 各资源模块各自实现软删 | 违反 ADR-0004 §1/§3；会产生多条写入路径与谓词漂移风险 |
| 每资源一个 `SoftDeleteService` 子类 | 无实际收益的继承层次（AGENTS §2.3/§2.6）；「无明确收益不引入」 |
| 以数据库**触发器**自动置 `deleted_at` | 把业务规则藏进 Schema（AGENTS §2.4）；ADR-0002 已排除触发器 |
| 服务接收 `(table_name, id)` 字符串并执行裸 SQL | 丢失 ORM 类型约束，且不利于行锁与检查点组合；无收益 |
| 运行时拦截「未授权 `deleted_at` 写入」的 SQLAlchemy 事件监听 | 增加全局状态与复杂度；AC-08 明确允许静态 guard 断言。列为 **OPEN（非阻塞）**，不作为本次要求 |

### 问题 2 — 活跃子资源检查的声明机制

**结论（采用）**：**资源模块声明 + 显式传递**。

- 每个可删除资源模块提供模块级常量：`<RESOURCE>_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...]`（F014 的 `app/clusters/deletion.py` 为 `CLUSTER_ACTIVE_CHILD_CHECKS = ()`，**显式**声明「当前无子资源」，而非由服务假定）。
- 该资源的 `delete_<resource>()` 领域函数把它显式传给 `soft_delete(..., active_children=...)`。
- `ActiveChildCheck` 为 `Callable[[Session, int], bool]`；实现方负责「该父行下是否存在 `deleted_at IS NULL` 的子行」这一查询（通常是 `EXISTS(... LIMIT 1)`）。
- **新增子资源时**：在**父资源**的声明元组中追加由子资源模块提供的检查函数（如 F002 的 `bare_metals` 活跃检查）；**统一服务核心逻辑零改动**。
- **不得硬编码**：服务内不出现「Cluster 无子资源」「某资源无子资源」等分支；是否检查、检查什么完全由声明决定。

**被拒绝的替代方案**：

| 方案 | 拒绝理由 |
|---|---|
| 统一服务硬编码「某资源没有子资源」 | Product Handoff 明确禁止；新增子资源必须改服务，违反可扩展性 |
| 全局注册表 + import 期自动注册（registry/回调） | 引入全局可变状态与 import 顺序依赖；未注册时存在 fail-open 风险。以显式常量替代，副作用更小、更易审查（`Simple First`） |
| 由统一服务按模型自省外键自动推导子资源 | 依赖 ORM 关系元数据；F014 无子资源表可推导；且「活跃」谓词无法从 FK 推导（DB 设计决策 5）；会把规则藏进实现 |
| 由数据库部分外键 / 约束触发器表达 | PostgreSQL 无 partial FK；触发器被 ADR-0002 / AGENTS §2.4 排除 |

### 问题 3 — 父删子拦的事务与加锁协议；并发测试如何构造窗口

**结论（落实 ADR-0004 §5 / DB 设计决策 6）**：

- **删除事务（F014 实现）**：
  ```
  BEGIN                                   -- F012 请求级事务（api/deps.py）
  SELECT … FROM clusters
   WHERE id = :id AND deleted_at IS NULL
   FOR UPDATE;                            -- 未命中 → 404；命中则锁住父行
  -- 在同一事务内执行声明的活跃子资源检查（EXISTS 活跃子行）
  --   命中 → ConflictError(409)，ROLLBACK（deleted_at 不写）
  UPDATE clusters SET deleted_at = now(), updated_at = now() WHERE id = :id;
  COMMIT
  ```
  `READ COMMITTED` 下 `FOR UPDATE` 会在获得锁后**重新求值** `deleted_at IS NULL`，因此并发软删竞争也安全（后到者命中不到活跃行 → `404`）。
- **子资源创建侧（F002+ 义务，F014 只交付删除侧并对齐协议）**：创建子资源时必须对父行取**共享锁**并确认父行活跃：
  ```
  SELECT id FROM clusters WHERE id = :cid AND deleted_at IS NULL FOR SHARE;
  -- 未命中 → 拒绝创建
  INSERT INTO bare_metals (...);
  ```
  两种交错都不可能产生「父已删 + 子活跃」：父删先持 `FOR UPDATE` 则子建阻塞并在父删提交后命中不到活跃父；子建先持 `FOR SHARE` 则父删阻塞并在子建提交后看到新子行 → `409`。
- **F014 内的并发测试窗口构造**（无真实子表，见问题 7）：
  1. **锁序断言（T-06）**：注入一个 `ActiveChildCheck`，在其执行瞬间由测试的**第二连接**对同一父行执行 `SELECT … FOR UPDATE NOWAIT`，断言失败（`55P03` / lock not available），从而证明「父行锁已在检查之前取得，且检查与删除同事务」。
  2. **阻塞锁断言（T-13）**：第二连接先持有父行 `FOR UPDATE`；后台线程发起 `DELETE`；断言 `DELETE` **阻塞**（在阈值时间内未完成），释放后按下述逻辑完成。证明删除使用**阻塞行锁**而非 MVCC 快照直接更新。
  3. **检查失败即拒绝 + 无部分写入（T-05）**。
- **AC-09 的完整端到端形式（Cluster + BareMetal）不可在 F014 复验**，作为 F002 的显式义务交接（问题 7）。

**被拒绝的替代方案**：`SERIALIZABLE` 隔离级别（引入序列化失败与重试，对 50 并发低频 CRUD 过度）；仅靠 FK（无法表达 `deleted_at IS NULL`）；`EXCLUDE` 约束 / 约束触发器（ADR-0002 排除）。

### 问题 4 — API 契约落点

**结论**：**新增 `docs/api/f014-soft-delete.md` 作为 F014 的唯一权威契约**；`docs/api/f001-cluster.md` **不修改**。

理由：

- f001 契约 §1.3 / §10 已显式把整个 DELETE 语义排除并归属 F014；新增文件不制造矛盾，且避免「同一端点跨两文件」的正文重复。
- 删除端点响应为 `204`（无响应体），不依赖 f001 §2 的 `ClusterRead` 资源表示；共享部分（错误信封、状态码、Empty/Not Found）通过引用 `api-conventions.md` 获得，**不重复定义**。
- **不提供** `DELETE /api/clusters/by-name/{name}`（写操作一律走 `id`，ADR-0003 §2）；重复删除 → `404 NOT_FOUND`。
- 契约 Status 在实现前为 `READY`。

### 问题 5 — `409 CONFLICT` 的错误信封稳定形态

**结论（复用 F012 机制，仅新增一个稳定 `details[].code`）**：

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "父资源存在活跃子资源，无法删除",
    "details": [
      {
        "row": null,
        "field": null,
        "code": "ACTIVE_CHILDREN_EXIST",
        "message": "资源仍存在活跃子资源，无法删除"
      }
    ]
  }
}
```

- `error.code = "CONFLICT"`（由 `api-conventions.md` §6 固定，与唯一性冲突共用同一顶层 code）。
- `details[].code = "ACTIVE_CHILDREN_EXIST"` 是**唯一稳定判别值**（与唯一性冲突的 `"DUPLICATE"`、非法字符的 `"INVALID_CHARACTER"` 并列，均为 `details[].code` 值域成员，**不修改** `api-conventions.md`）。
- `details[].field = null`、`details[].row = null`（资源级冲突，无单一字段；`row` 仅导入使用）。
- `message` 为人类可读描述，**不构成契约**；前端必须按 `error.code`（必要时 `details[].code`）分支。
- 实现经既有 `app/common/errors.py::ConflictError` + `error_handlers.py` 产生，**不另立信封**。

### 问题 6 — R-DELETE-005「不级联、只改目标行」的验证方式

**结论**：三重断言，全部可失败：

1. **Schema guard（G-1）**：断言数据库中**不存在**任何 `ON DELETE CASCADE` 外键（`pg_constraint.confdeltype='c'` 计数为 0）。F014 时点为空真；随 F002+ 建表持续生效，防止「顺手加 CASCADE」。
2. **行为 guard（T-07）**：创建活跃 A、B，但**删除 A 后**断言 B 的 `deleted_at` / `name` / `updated_at` **逐字段不变**；`clusters` 行数不变（无物理删除）；对全表 `(id, deleted_at)` 快照比对，差异仅为 A 的 `deleted_at`。
3. **结构性**：软删服务是 `UPDATE` 单行而非 `DELETE`，且不遍历任何关系；由 G-3（唯一写入路径）与代码评审共同保证。

**Schema 层「无 CASCADE」guard 的归属**：归 **F014**（本 Feature 是逻辑删除一致性治理的基座），放在 `tests/database/`，后续 Feature 建表时必须保持其为真。

### 问题 7 — R-DELETE-004 在 F014 内的可验证形态；F002 必须补的端到端场景

**F014 可验证形态（不削弱 AC-04）**：

- **守卫存在且被调用**：T-06 注入 spy 检查点，断言删除路径**真实调用**声明的检查。
- **失败即拒绝且无部分写入**：T-05 注入返回 True 的检查点 → `409` + `details[].code` + 目标行 `deleted_at` 仍 NULL。
- **同事务、锁后检查**：T-06 的锁序断言。
- 单元层面亦可断言 `CLUSTER_ACTIVE_CHILD_CHECKS` 作为声明点被删除路径消费。

**F002 落地后必须补的端到端场景（显式交接，避免静默丢失）**：

1. `bare_metals` 模块向 `CLUSTER_ACTIVE_CHILD_CHECKS`（或等价声明）注册「Cluster 下是否存在活跃 BareMetal」检查。
2. 端到端：Cluster 有活跃 BareMetal → `DELETE /api/clusters/{id}` → `409 CONFLICT`；软删该 BareMetal 后 → 删除成功。
3. 并发端到端：创建 BareMetal 与删除 Cluster 并发，结果只可能二者之一；结束后断言孤立记录不变式为 **0 行**：
   ```sql
   SELECT count(*) FROM bare_metals bm
   JOIN clusters c ON c.id = bm.cluster_id
   WHERE bm.deleted_at IS NULL AND c.deleted_at IS NOT NULL;   -- 必须为 0
   ```
4. 创建 BareMetal 必须对父 Cluster 行取 `FOR SHARE` 并确认活跃（问题 3 协议）。

### 问题 8 — 交付层判定

```text
database: false
backend:  true
frontend: true
```

- **database = false**：无 Schema / 索引 / 约束 / migration 变更；`clusters.deleted_at` 与 `ux_clusters_name_active` 已由 F012 基线冻结。数据库侧交付**仅为测试断言**（G-1 / G-2 / G-4 / T-13），由 Backend 承担。**判定依据是「是否需要 schema 变更」，不是「是否存在数据库断言」**（与 F001 `database: false` 同一标准）。
- **backend = true**：统一软删服务 + 声明机制 + `DELETE /api/clusters/{id}` + guard 演进 + 测试。
- **frontend = true**：删除入口 + 成功 / 失败 / Not Found 状态接线。

### 问题 9 — 前端接线

见 Frontend Work。要点：删除入口（列表 + 详情，二次确认）；成功后刷新并进入删除后状态（列表消失 / 详情 Not Found）；失败按 `error.code`（`CONFLICT` / `NOT_FOUND` / `UNAUTHENTICATED`）渲染；**不得**在前端重复实现守卫（§21）；Loading 与防重复提交。

### 问题 10 — `ip_address.cluster_id` 机制交接

- `ip_addresses` 表**尚不存在**（F005 BLOCKED，`depends_on: [F004]`），F014 **无法交付**该一致性逻辑。
- F014 的交付面是**「一个可复用的统一领域服务机制」**（当前用于软删）。`ip_address.cluster_id` 的**受控写入（从 `network_interface_id` 沿 NIC→BareMetal→Cluster 推导）属 F005**，必须在其领域服务中实现，而非由调用方直接赋值。
- **不建议**在 F014 预先建立通用「资源写入服务」抽象（无实际消费者，违反 `Simple First`）。
- **交接要求（Non-blocking，请 PM 更新归属）**：`docs/database/csm-v1-schema-design.md` §3 决策 3 现把该条归给「F014 领域服务」；建议在 `project-plan.yaml` 中把该 requirement 归属迁移到 **F005**，并要求 F005 建表时实现推导 + 漂移检测测试（漂移查询 0 行）。F014 仅保证统一领域服务机制存在且可复用。

### 问题 11 — F001 遗留 A15 guard 的演进

**问题**：F001 的 A15 断言「`backend/app/**` 中 `deleted_at` 写入数 = 0」，F014 落地后必然失效；若不演进就会「删掉旧 guard、失去验证力」。

**结论**：演进而非删除：

| 旧断言 | 新断言（F014） |
|---|---|
| `test_a15_no_deleted_at_assignment_in_app_source`：写入数 = 0 | **G-3**：写入 `deleted_at` 的文件集合**恰好为** `{app/deletion/service.py}`；并断言不存在 `deleted_at = None`（R-DELETE-003） |
| `test_a15_delete_endpoint_does_not_soft_delete`：DELETE 不软删、行仍活跃 | **T-01**：`DELETE` **确实**软删（`204`），行**仍物理存在**且 `deleted_at` 非空 |
| `test_g_e_no_deleted_at_assignment_in_app_source`（扫描全部 app 源码 = 0） | 收窄为 `app/auth/**`（原意即「认证代码不写 `deleted_at`」），或统一并入 G-3 |

**新增正向断言**：唯一写入路径**存在且被使用**（`DELETE` 走 `soft_delete()`）。避免出现「允许列表为空 / 服务未被删除路径调用」的静默退化。

---

## Technical Decisions

### CONFIRMED

- 技术栈、PostgreSQL、Alembic、BIGINT identity 主键、错误信封与状态码语义（ADR-0001~0005 全部 `ACCEPTED`）。
- 单一 `deleted_at` 删除标记 + partial unique index（predicate `deleted_at IS NULL`）+ 查询统一过滤（ADR-0004 §1~§3）。
- 父删子拦必须同事务检查并对父行加锁；不级联；无 undelete（ADR-0004 §4~§6）。
- `204` 删除成功、`404 NOT_FOUND`（不存在或已删）、`409 CONFLICT`（父有活跃子）、写操作走 `id`（`api-conventions.md` §2/§6；ADR-0003 §2）。
- `clusters` 表、`ck_clusters_name_no_slash`、`ux_clusters_name_active` 由 F012 基线建立并**冻结**；F014 不改基线、不新建表。
- 认证：所有 `/api/*`（登录除外）要求认证，V1 仅两态、无 RBAC（ADR-0005；R-AUTH-003）。
- 禁止 EAV / 通用 `resources` 表 / STI / ORM 多态 / JSONB 万能模型（§4、§24）。
- `updated_at` 由应用层维护，**不得**作为审计或并发控制依据（DB 设计决策 8）。

### REQUIRED

1. `deleted_at` 的写入路径**恰好 1 条**（统一服务）；各资源删除端点必须委托它（ADR-0004 §3；AC-08）。
2. `soft_delete()` 必须在**同一事务内**先锁父行、再执行活跃子资源检查、命中即 `409` 且**不写 `deleted_at`**（ADR-0004 §5；AC-04）。
3. 删除**只改目标行**，不级联、不物理删除其他行（R-DELETE-005；AC-05）。
4. 删除端点必须位于 `/api` 前缀下（由 F013 认证中间件自动覆盖，无白名单）；未认证 → `401` 且不改数据（AC-12）。
5. 不存在任何恢复 / undelete 路径，不得出现 `deleted_at = None`（R-DELETE-003；AC-03）。
6. **无 schema / migration 变更**；不改 `0001_f012_baseline`；不改 `ux_clusters_name_active` 的 predicate / collation / 大小写语义（§22）。
7. 删除守卫必须在**后端**判定义务，前端不得替代（§21；AC-07）。
8. F001 A15 与 F013 G-E 的 `deleted_at` guard **必须演进为 allow-list 形式**，不得删除后不补（问题 11）。
9. 错误信封 / 状态码 / SQLSTATE 映射**复用** F012 机制，不另立一套。
10. 认证表（`users` / `sessions`）不得获得软删语义（AC-13）。
11. 不引入新框架 / 中间件 / 依赖；不引入 EAV / 通用表 / 多态基类。

### PROPOSED

1. **契约落点**：新增 `docs/api/f014-soft-delete.md`（不修改 `f001-cluster.md`）。
2. **模块布局**：`backend/app/deletion/`（`service.py` + `checks.py`）；Cluster 删除声明在 `app/clusters/deletion.py`。
3. **声明机制**：资源模块模块级 `ActiveChildCheck` 元组 + 显式传参（问题 2）。
4. **409 判别值**：`details[].code = "ACTIVE_CHILDREN_EXIST"`（问题 5）。
5. **端点注册位置**：注册在 `app/clusters/router.py`（资源内聚；回应 F001 Open #4）。统一服务是被委托方，不放路由。
6. **`by-name` 无 DELETE**；重复删除 → `404`。
7. **前端交互**：删除入口置于列表与详情页，采用 Element Plus 二次确认（交互形式不构成产品规则）。
8. 分页与错误渲染沿用既有基座（`page_size` 默认 50 / 上限 200）。

### OPEN（非阻塞）

1. 运行时拦截「未授权 `deleted_at` 写入」的 SQLAlchemy 事件监听（当前以静态 guard 满足 AC-08，不引入）。
2. `DELETE /api/clusters/by-name/...` 等非契约路径的 405/404 精确 code（F001 Review F-01 遗留：未映射 4xx 统一为 `INTERNAL_ERROR`；F014 不修通用映射表）。
3. F005 的 `ip_address.cluster_id` 受控写入（问题 10）。
4. 审计 / 保留期限 / 已删资源查看出口（产品 PROPOSED-2/3、NQ-5；本次不实现、不承诺）。
5. NQ-3（其他资源删除端点是否成为统一约定）。

---

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | **AC-09 无法在 F014 端到端复验**（无子资源表），可能在交接中静默丢失 | 显式交接 F002 的 4 项义务（问题 7），并把孤立记录不变式查询写入本 Handoff 与 F002 的 AC；F014 以锁序 + 阻塞锁 + 注入检查点测试固定机制 |
| R2 | 静态 guard 可被动态 SQL（`text("UPDATE … deleted_at …")`）绕过 | G-3 覆盖常见写入形态；补充代码评审检查项；行为测试 T-01/T-07 作为运行时不变量 |
| R3 | 现有 A15 / G-E guard 在 F014 后失败，若处理不当会「删测试」而非「演进」 | REQUIRED #8 明确演进方式与新旧对应表（问题 11） |
| R4 | `409` 判别值不稳定导致前后端漂移 | 契约固定 `error.code="CONFLICT"` + `details[].code="ACTIVE_CHILDREN_EXIST"`；T-05 直接断言 |
| R5 | 前端误把「父有活跃子」做成前端校验，违反 §21 | REQUIRED #7；前端禁止重复实现；T-04 证明后端强制 |
| R6 | 误把删除端点注册位置 / 模块名当产品规则 | 全部标注为工程约定（PROPOSED），不改领域语义 |
| R7 | 删除入口无二次确认导致误操作 | 前端二次确认（PROPOSED #7）；不影响后端正确性 |

---

## Constraints

1. 不得修改或新增任何 Schema / migration；不得改 `0001_f012_baseline`；不得新增同类数据库约束或列。
2. 不得改变 `ux_clusters_name_active` 的 predicate / collation / 大小写敏感语义；不得用 `lower()` 折叠。
3. 不得实现第二条 `deleted_at` 写入路径；不得实现 restore / undelete / purge / 批量删除。
4. 不得把软删语义扩展到 `users` / `sessions`；不得引入角色 / 权限 / RBAC。
5. 不得在前端重复实现删除守卫；守卫必须由后端裁决（§21）。
6. 不得引入新框架 / 中间件 / 新依赖；不得引入 EAV / 通用 `resources` 表 / STI / ORM 多态 / JSONB 万能模型。
7. 不得偏离 `api-conventions.md` 的信封、状态码与 Empty / Not Found 语义；不得另立第二套 SQLSTATE 映射。
8. 所有删除端点必须在 `/api` 前缀下，使 F013 认证自动覆盖，不新增白名单。
9. DB / API 契约单一权威；代码中不得另立约定。F014 删除契约唯一正文在 `docs/api/f014-soft-delete.md`。
10. `updated_at` 由应用层维护，不得作为审计或并发控制依据。
11. 不得修改 `docs/api/f001-cluster.md` 正文（其 §10 已正确排除 DELETE）。

---

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

1. 运行时 `deleted_at` 写入拦截（事件监听）——当前不引入。
2. 非契约路径（`DELETE …/by-name/...`）的 405/404 精确 `code`——F001 Review F-01 遗留，F014 不改通用映射。
3. F005 的 `ip_address.cluster_id` 受控写入与漂移测试归属（问题 10；请 PM 更新 `project-plan.yaml`）。
4. 审计 / 保留期限 / 已删可见性出口（产品 PROPOSED-2/3、NQ-5）。
5. NQ-3：其他资源删除端点是否作为统一约定（本 Feature 的约束是「若提供必须委托统一服务」）。
6. NQ-1：F002 端到端 AC 的落点（问题 7，已给出交接清单）。

---

## Implementation Layers

```text
database: false
backend:  true
frontend: true
```

- **database**：无 Schema / 索引 / migration 变更。交付仅为测试断言（G-1 / G-2 / G-4 / T-13），由 Backend 承担。
- **backend**：`app/deletion/`（统一服务 + 检查声明类型）、`app/clusters/deletion.py` + service + router 的删除路径、guard 演进（G-3 / T-01 取代 A15 / G-E）、全测试集。
- **frontend**：`api/clusters.ts` 的 `deleteCluster`、列表 / 详情的删除入口与状态刷新、错误按 `error.code` 渲染。

---

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f014-soft-delete.md，均 READY）
  ├─ Frontend（只需契约稳定：api/clusters.ts 删除函数 → 列表 / 详情删除入口与状态 → 错误渲染）
  └─ Backend（统一软删服务 + 声明机制 → clusters 删除路径 → guard 演进与测试）
                 ↓ 两个必需分支完成
              Tester → Reviewer
```

- **无 Database Design 分支**（`database: false`），无需等待数据库 Agent；无 migration。
- Backend 与 Frontend 可**直接并行**（契约已 `READY`）。
- 文件所有权：Backend = `backend/**` + `tests/**`；Frontend = `frontend/**`；共享 `docs/**` 由协调器落盘。
- 协调器需落盘：本 Handoff、`docs/api/f014-soft-delete.md`，并同步 `project-plan.yaml` F014 的 `layers` / `contract` / `implementation`。

---

## Verification Strategy

1. **契约层（AC-01 / AC-02 / AC-03 / AC-12）**：`204`/`404`/`401` 状态码与错误信封、无响应体、重复删除、未认证不改数据（T-01 / T-02 / T-03 / T-10）。
2. **删除守卫（AC-04 / AC-07）**：注入检查点 → `409` 稳定 code + 无部分写入（T-05）；守卫真实被调用且同事务锁后执行（T-06）；后端强制、与 UI 无关（T-04）。
3. **不级联（AC-05）**：Schema 无 CASCADE（G-1）+ 行为「只改目标行」（T-07）。
4. **唯一性释放（AC-06）**：删除后同名可重建（T-08），并保留 F012 直写库的权威断言。
5. **单一路径（AC-08）与无恢复（AC-03）**：静态 allow-list guard（G-3）+ 无 `deleted_at = None`。
6. **并发（AC-09）**：锁序 + 阻塞锁（T-06 / T-13）；端到端与孤立记录不变式交接 F002。
7. **认证与非资源表（AC-12 / AC-13）**：`401` 不改数据（T-10）；`users` / `sessions` 无软删（T-11 / G-4）。
8. **无越界能力（AC-11）**：负向路由 / 参数断言（T-12）。
9. **前端（AC-10）**：删除入口、成功后列表 / 详情状态、`error.code` 渲染（T-FE-01）。
10. **结构不变（约束）**：`clusters` 列 / CHECK / 索引断言与 F012 数据库测试全绿（G-2）。
11. **工程门禁**：lint 通过；既有测试（含 F013 认证、F012 数据库测试）全绿，A15 / G-E guard 已完成演进。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：Product Handoff 为 `READY FOR ARCHITECT` 且无 Blocking；所有输入为 `READY` / `ACCEPTED` / `CONFIRMED`；`database: false`（无 Schema 不确定性）；API Contract = `READY`；Backend / Frontend 两分支均有可直接开工的依据。11 个待决技术问题已逐条裁定（含被拒绝替代方案）。**需用户确认的长期技术决策：无**（NQ-2 的归属修正属 `project-plan.yaml` 的计划归属调整，需 PM 同步，不阻塞实现）。