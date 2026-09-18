# Architecture Handoff — F002 BareMetal 登记与管理

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-16
> Feature: F002（E01，P0，`depends_on: [F001]`）
> Git: `feature/F002-bare-metal`，base `develop` = `c8e5d910b057f96cc4864959ac802d15b75abc67`
> 配套契约：`docs/api/f002-bare-metal.md`（`READY`）

---

## Feature

BareMetal 登记与管理（F002）— CSM V1 唯一有状态资源的登记、查询、状态人工维护、R-BM-007 硬件字段维护与逻辑删除，并承接 R-CLUSTER-004 的 N:1 方向、F014「父删子拦」真实端到端与 `FOR SHARE` 并发协议。

## Product Source

- `docs/product/handoffs/f002-bare-metal.md`（`READY FOR ARCHITECT`，无 Blocking，AC-01 ~ AC-30，主要输入）
- `docs/product/requirements.md` §8 / §17 / §21 / §22 / §23 / §24 / §25
- `docs/product/domain-model.md` / `domain-model.yaml`（BareMetal / Cluster / lifecycle / data_consistency）
- `.pi/skills/resource-domain/SKILL.md`
- ADR-0001 / ADR-0002 / ADR-0003 / **ADR-0004** / ADR-0005（全部 `ACCEPTED`）
- `docs/architecture/f014-soft-delete-handoff.md`、`f013-auth-handoff.md`、`f001-cluster-handoff.md`、`f012-project-foundation-handoff.md`
- `docs/database/csm-v1-schema-design.md`、`docs/database/f012-baseline-migration.md`
- `docs/api/api-conventions.md`、`docs/api/f001-cluster.md`、`docs/api/f014-soft-delete.md`
- 现有实现（只读）：`backend/app/**`、`tests/**`、`frontend/src/**`

---

## 现状核实（只读检查结论）

| 项 | 现状（已核实） |
|---|---|
| Backend | **已存在**：应用工厂（`main.py` 挂载 `/api` → health + auth + clusters）、F013 认证中间件（`/api/*` 自动覆盖，仅登录豁免）、F012 统一错误信封 + 全局 handler（`common/errors.py` / `error_handlers.py`，`RequestValidationError → 400 VALIDATION_ERROR`）、通用 SQLSTATE→HTTP 映射（`common/sqlstate.py`：23502/23514→400、23505/23503→409）、分页（`common/pagination.py`，默认 50 / 上限 200）、请求级事务边界（`api/deps.py`）、活跃过滤原语（`db/active.py`：`active_filter` / `select_active`） |
| 统一软删服务 | **已存在** `backend/app/deletion/`：`service.soft_delete()`（系统内唯一写 `deleted_at` 的路径）、`checks.ActiveChildCheck` 声明类型。`app/clusters/deletion.py` 声明 `CLUSTER_ACTIVE_CHILD_CHECKS = ()`（**显式空元组**，待 F002 追加） |
| `clusters` 删除路径 | **已注册** `DELETE /api/clusters/{cluster_id}` → `204`，委托 `soft_delete()`（F014） |
| `deleted_at` 写入路径数 | **恰好 1**（`app/deletion/service.py`）；`tests/deletion_guard_helpers.py` 的 allow-list 扫描器已固定之 |
| Database | `clusters`（`0001`，冻结）+ `users` / `sessions`（`0002`）。**`bare_metals` 表不存在**。`tests/database/helpers.MIGRATION_HEAD = "0002_f013_auth"`；`tests/database/test_schema.EXPECTED_TABLES = {alembic_version, clusters, users, sessions}`；`tests/database/test_migrations` 与 `tests/test_structure_guard.test_only_expected_tables_registered` 同集合。无 CASCADE guard 已存在且当前空真生效 |
| Frontend | **已存在** `frontend/src/**`：`api/http.ts`（错误归一 + 全局 401）、`api/clusters.ts`、`components/ListStates.vue` / `ErrorState.vue`、`composables/useAsyncQuery.ts` / `useClusterDelete.ts`、`pages/ClusterListPage.vue` / `ClusterDetailPage.vue` / `LoginPage.vue`、`App.vue` 极简视图切换（**无 vue-router**）。**无 BareMetal 相关 UI** |
| 领域对象 | 仅 `Cluster`（`app/models/cluster.py`）。**无 BareMetal 实体** |
| 现有 guard | A15 / G-E 已演进为 G-3 allow-list；`test_a15_delete_endpoint_does_not_soft_delete` 已由 T-01 取代；`test_g2_schema_guard` 固定 `clusters` 列/CHECK 集合；`test_deletion_schema_guard` 固定「无 CASCADE」「认证表无 `deleted_at`」 |

**产品 Handoff 记录的文档漂移复核（Architect 只读核实）**：

1. **仍存在**：`docs/database/csm-v1-schema-design.md` 的 `bare_metals` Columns 表**尚未列出** R-BM-007 七列（仅有「待 F002 Database 阶段同步补齐」的注记）；`docs/database/f012-baseline-migration.md §4 0003_f002_bare_metals` DDL 亦未含七列。→ **F002 需同步**（见 Data Layer Impact / Database Work）。
2. **已消解**：`domain-model.yaml > open_questions > OPEN-004` 现为 `status: CLOSED_RESOLVED`（resolution 已记录用户 2026-09-16 裁定），与 Product Handoff 所述「仍为 OPEN」不符——该漂移已在协调器侧修正。
3. **已消解**：`project-plan.yaml > F002.requirements` 现已包含 `§21 Data Consistency`、`R-DELETE-004`、`R-DELETE-006`、`§22 Case Sensitivity`；NQ-8 的元数据同步项已完成。

**结论**：F002 是在非空、已具 F012/F013/F014 基座的项目上的增量交付；本 Feature 需要**新增一张表 + 一次增量 migration**，而删除、错误信封、分页、事务、活跃过滤、父删子拦机制与并发协议**全部复用既有基座**，不另立一套。

---

## Architecture Summary

**目标**：让「一台机器属于哪个集群、叫什么、当前什么状态、硬件规格如何」成为可信、唯一、可维护、可删除的事实，并让 F014 的父删子拦与并发不变式获得**首个真实业务端到端**。

**对现有系统的影响**：
- 新增模块 `backend/app/bare_metals/`（模型 + 领域校验 + repository + service + router + deletion 声明）。
- 新增 ORM 模型 `app/models/bare_metal.py` 并注册到 `app/models/__init__.py`、`main.py` 挂载路由。
- **改** `app/clusters/deletion.py`：把 `CLUSTER_ACTIVE_CHILD_CHECKS` 从空元组演进为 `(has_active_bare_metals,)`（F014 端到端义务）。
- 新增 migration `0003_f002_bare_metals`（**不改 `0001` / `0002` 基线**）。
- 新增前端 BareMetal 页面与 API 客户端。
- 演进既有 schema guard 的「表集合」断言（增表），并新增 `bare_metals` 结构 guard。

**方案要点**：
1. **数据层**：`bare_metals` 一次 `CREATE TABLE` 建齐 `cluster_id NOT NULL + FK RESTRICT`、`hostname NOT NULL`、`status NOT NULL DEFAULT 'IDLE' + CHECK`、R-BM-007 七个可空 `TEXT` 列、`deleted_at`；partial unique `ux_bare_metals_cluster_hostname_active`（predicate `deleted_at IS NULL`）；`ix_bare_metals_cluster_id`。
2. **唯一性**：同 Cluster 活跃 `hostname` 唯一、大小写敏感、跨 Cluster 可重、软删释放——由 partial unique index 强制，应用层仅做友好 `409` 预检。
3. **创建关系写入**：创建对父 Cluster 行取 `FOR SHARE` 并在同一事务内确认活跃；未命中 → `404 NOT_FOUND`（NQ-2 裁定，见设计问题 3）。与 F014 的 `FOR UPDATE` 删除协议共同保证「不存在父已删 + 子活跃」。
4. **删除**：`DELETE /api/bare-metals/{id}` 委托**唯一**软删服务；BareMetal 以 `BARE_METAL_ACTIVE_CHILD_CHECKS`（显式空元组）声明自身子资源检查点；Cluster 删除路径追加「活跃 BareMetal」检查。
5. **领域校验单一实现**：状态封闭集合校验只有一份，创建 / 更新 / （未来导入）共用；`23514` 经既有映射 → `400`。
6. **未定义约束不实现**：`hostname` 无长度 / trim / 空串 / 字符约束，无 `/` 禁令；以结构 guard 固定。
7. **无新框架 / 无新依赖 / 无 EAV / 无通用表 / 无多态**；契约落点新增 `docs/api/f002-bare-metal.md`。

---

## Domain Impact

**使用**已有领域对象 `Cluster`（R-BM-001 的 N:1 父）。

**新增**领域对象：**无**。BareMetal 作为资源实体其建模（`hostname`、`status`、R-BM-007 七字段）**均已由 CONFIRMED 产品文档确定**（`requirements.md` §8 R-BM-001~007、`domain-model.yaml`），本 Feature 不新增 / 不修改任何领域对象、字段、关系、状态或唯一性规则，仅将其**落地**为表、模型与 API。

- 关系：`BareMetal → Cluster` N:1 mandatory（R-BM-001）——**已确认**，F002 只负责 N:1 写入方向（R-CLUSTER-004 的 F002 侧）；Cluster 视角读取归 F009。
- 状态：`BareMetal` 是 V1 唯一有状态资源；集合 `{IDLE, ALLOC, DOWN, UNKNOWN}` 为**封闭集合**，不得新增 / 合并 / 重命名。
- 生命周期：`soft_delete: true` / `cascade: false` / `parent_deletion.blocked_when_active_children_exist: true`（ADR-0004）。
- 明确**不**引入：Rack / U 位 / DataCenter（§6、§13）、自动发现 / 外部同步（§23、R-BM-006/007）、硬件字段结构化拆分、NIC/IP/VM/Container/Service 实体。

---

## Data Layer Impact

数据层需要解决：

1. **建表**：`bare_metals`（首张非 Cluster 资源表、首个真实 FK 引用 `clusters`）。
2. **唯一性**：同 Cluster 活跃 `hostname` 唯一（partial unique index，predicate `deleted_at IS NULL`），比较大小写敏感（默认 collation，不声明 `COLLATE`）。
3. **关系完整性**：`cluster_id` `NOT NULL` + FK `ON DELETE RESTRICT ON UPDATE RESTRICT`（禁止 CASCADE）。
4. **状态完整性**：`status` `NOT NULL DEFAULT 'IDLE'` + `CHECK IN (...)`。
5. **索引**：partial unique（服务 R-BM-002 与按 Cluster 活跃读取）+ 完整 `cluster_id` bt（服务 FK 引用检查与含已删行的按 Cluster 查询）。
6. **软删**：`deleted_at TIMESTAMPTZ NULL`，仅由统一软删服务写入。
7. **不做**：不改 `clusters` / `users` / `sessions`；不改 `0001` / `0002`；无数据迁移（表不存在）；无触发器；无 `COLLATE`；无硬件字段长度 / 格式 / 唯一约束。

数据层交付**同时包含测试断言**（结构 guard、约束行为断言，见 Test Work）。

---

## Database Work（migration `0003` 规格）

> Database Agent 给出最终 migration 实现；以下为 Architect 规格。表为**首次创建**，七列与其余列在**同一条 `CREATE TABLE`** 内建齐（不存在既有数据，无需 `ALTER`/回填）。

**Revision**：`0003_f002_bare_metals`，`down_revision = 0002_f013_auth`（维持单一线性 head）。

```sql
CREATE TABLE bare_metals (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  cluster_id    BIGINT      NOT NULL,
  hostname      TEXT        NOT NULL,
  status        TEXT        NOT NULL DEFAULT 'IDLE',
  vendor        TEXT        NULL,          -- R-BM-007
  model         TEXT        NULL,          -- R-BM-007
  serial_number TEXT        NULL,          -- R-BM-007（不参与唯一性）
  cpu           TEXT        NULL,          -- R-BM-007
  memory        TEXT        NULL,          -- R-BM-007
  gpu           TEXT        NULL,          -- R-BM-007
  storage       TEXT        NULL,          -- R-BM-007
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ NULL,
  CONSTRAINT pk_bare_metals PRIMARY KEY (id),
  CONSTRAINT fk_bare_metals_cluster FOREIGN KEY (cluster_id)
    REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_bare_metals_status
    CHECK (status IN ('IDLE', 'ALLOC', 'DOWN', 'UNKNOWN'))
);

CREATE UNIQUE INDEX ux_bare_metals_cluster_hostname_active
  ON bare_metals (cluster_id, hostname)
  WHERE deleted_at IS NULL;

CREATE INDEX ix_bare_metals_cluster_id ON bare_metals (cluster_id);
```

`downgrade`：`DROP INDEX ux_bare_metals_cluster_hostname_active; DROP INDEX ix_bare_metals_cluster_id; DROP TABLE bare_metals;`（顺序与 upgrade 逆序；破坏性，生产禁止）。

**规格约束（REQUIRED）**：
- identity 用 `sa.Identity(always=True)`；时间列 `server_default=sa.text("now()")`。
- partial unique index 显式 `postgresql_where=sa.text("deleted_at IS NULL")`，不得依赖 autogenerate。
- **不声明任何 `COLLATE`**；**不使用触发器**；**不使用 `ON DELETE CASCADE`**。
- **不添加** `hostname` 的 `<> ''` / 长度 / `trim` / 字符 CHECK；**不添加** `serial_number` 唯一约束。
- 遵循既有 `NAMING_CONVENTION`（`db/base.py`）。

**文档同步（NQ-6）**：
- 同步 `docs/database/csm-v1-schema-design.md` 的 `bare_metals` Columns 表，补入 R-BM-007 七列（`TEXT NULL`）。
- 同步 `docs/database/f012-baseline-migration.md §4 0003_f002_bare_metals` DDL，加入七列。
- 由协调器统一落盘；Architect 不直接修改。

---

## Backend Work

Backend Agent 需交付以下能力（实现细节由 Backend 决定）：

### 1. ORM 模型（新 `app/models/bare_metal.py`）
- `BareMetal(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`，`__tablename__ = "bare_metals"`。
- 列：`cluster_id`（`BigInteger NOT NULL`）、`hostname`（`Text NOT NULL`）、`status`（`Text NOT NULL server_default='IDLE'`）、七个 `Text NULL` 硬件列。
- `__table_args__`：`ForeignKeyConstraint(["cluster_id"], ["clusters.id"], ondelete="RESTRICT", onupdate="RESTRICT", name="fk_bare_metals_cluster")`、`CheckConstraint("status IN ('IDLE','ALLOC','DOWN','UNKNOWN')", name="status")`、partial unique `Index("ux_bare_metals_cluster_hostname_active", "cluster_id", "hostname", unique=True, postgresql_where=text("deleted_at IS NULL"))`、`Index("ix_bare_metals_cluster_id", "cluster_id")`。
- 注册到 `app/models/__init__.py`。

### 2. 请求 / 响应 schema（`app/bare_metals/schemas.py`）
- `BareMetalRead`：**恰好** `{id, cluster_id, hostname, status, vendor, model, serial_number, cpu, memory, gpu, storage, created_at, updated_at}`（无 `deleted_at`、无位置 / 上级字段）。
- `BareMetalCreate`：`cluster_id: int`、`hostname: str`（**无** min_length / pattern / strip）、可选 `status: str`、可选七个硬件字段 `str | None`。**不**给 `hostname` 添加任何约束。
- `BareMetalUpdate`：仅 `status: str | None` + 七个硬件字段 `str | None`；**不含** `hostname` / `cluster_id` / `id` / `deleted_at`；`model_config = ConfigDict(extra="forbid")`（未识别字段 → 400）。
- 不添加 `str_strip_whitespace` / NFC 归一化 / 长度 / 字符校验。

### 3. 领域校验（`app/bare_metals/validation.py`，唯一一份实现入口）
- `validate_status(status)`：仅接受 `{IDLE, ALLOC, DOWN, UNKNOWN}`，否则 `ValidationError(400)` + `details[].field="status"`。创建 / 更新共用，未来导入复用。
- **不实现**任何 `hostname` 字符 / 长度 / trim 校验（未定义约束）。

### 4. Repository（`app/bare_metals/repository.py`）
- 读取路径**必须**经 `app/db/active.py` 的 `active_filter` / `select_active`，不重写 `deleted_at.is_(None)` 谓词。
- `get_active(id)`、`list_active(params, cluster_id=None)`（返回 `(items, total)`，按 `id` 升序）、`active_hostname_exists(cluster_id, hostname)`（大小写敏感字面值等值）。
- `create(...)` / `update(...)`：`add` / 赋值后 `flush()` + `refresh()`，让数据库约束在请求内抛出（经既有 SQLSTATE 映射）。
- **不存在**写 `deleted_at` 的方法。

### 5. Service（`app/bare_metals/service.py`）
- `create_bare_metal(session, payload)`：
  1. `parent_gate`：`SELECT id FROM clusters WHERE id=:cluster_id AND deleted_at IS NULL FOR SHARE`；未命中 → `NotFoundError`（404）。
  2. 活跃重复预检 → `ConflictError(409, field="hostname", code="DUPLICATE")`。
  3. `validate_status`（若提供）。
  4. 插入（`status` 未提供时由 DB default 生效）、`flush`、`refresh`。
- `list_bare_metals(session, params, cluster_id=None)`：当 `cluster_id` 给出时，先以 `select_active(Cluster)` 确认父活跃 → 未命中 `404`；再返回该 Cluster 活跃子集。未给出时返回全部活跃。
- `get_bare_metal_by_id(session, id)`：未命中 → `404`。
- `update_bare_metal(session, id, payload)`：加载活跃目标（`404`），按 `model_fields_set` 应用可变字段、`validate_status`、`flush`、`refresh`；不处理 `hostname` 唯一性（不可变）。
- `delete_bare_metal(session, id)`：委托 `soft_delete(session, BareMetal, id, active_children=BARE_METAL_ACTIVE_CHILD_CHECKS)`。

### 6. 路由（`app/bare_metals/router.py`，`prefix="/bare-metals"`）
- `POST ""` → `201 BareMetalRead`
- `GET ""` → `Page[BareMetalRead]`，可选 query `cluster_id: int | None`
- `GET "/{bare_metal_id}"` → `BareMetalRead`
- `PATCH "/{bare_metal_id}"` → `BareMetalRead`
- `DELETE "/{bare_metal_id}"` → `204`（无 `response_model`）
- 在 `app/main.py` 以 `prefix="/api"` 挂载（自动进入 F013 认证边界，**无白名单**）。
- 路径参数名 `bare_metal_id`（对齐 `{resource_id}` 约定）；无 `by-name` 路由。

### 7. F014 端到端接线（**必须**）
- 新 `app/bare_metals/deletion.py`：`BARE_METAL_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()`（**显式**声明「当前无子资源」，不得由服务假定）；并提供 `has_active_bare_metals(session, cluster_id) -> bool`（`EXISTS` 活跃 BareMetal，复用活跃过滤原语）。
- 改 `app/clusters/deletion.py`：`CLUSTER_ACTIVE_CHILD_CHECKS = (has_active_bare_metals,)`（子资源模块提供检查函数，父资源模块声明；无循环导入：`app.clusters.deletion → app.bare_metals.deletion → app.models.*`）。
- 该声明被 `app/clusters/service.delete_cluster` 真实传入 `soft_delete()`。

### 8. 明确不做
第二处 `deleted_at` 写入；restore / undelete / purge / 批量删除；`include_deleted`；`by-name` 别名；跨 Cluster 迁移 / 改名；自动发现 / 外部同步；硬件字段结构化拆分；其它资源端点；新框架 / 新依赖；触发器 / CASCADE / `COLLATE`。

---

## Frontend Work

Frontend Agent 完成（`frontend/**` 归 Frontend）：

1. **`src/api/bareMetals.ts`**（不新建请求层，复用 `api/http.ts`）：
   - `BareMetalRead` 接口（字段集合封闭，`vendor`/`model`/`serial_number`/`cpu`/`memory`/`gpu`/`storage` 为 `string | null`，`status` 为字符串枚举，时间字段为不透明字符串）。
   - `listBareMetals(params: { page?; page_size?; clusterId? })`、`getBareMetal(id)`、`createBareMetal(body)`、`updateBareMetal(id, body)`、`deleteBareMetal(id)`。
2. **`pages/BareMetalListPage.vue`**：
   - 调用 `GET /api/bare-metals`（可选 `cluster_id` 过滤，供 Cluster 视角入口复用）。
   - **三态互不相同**（Loading / Empty / Error）；Empty（200 + `items==[]`）与 Not Found（父 Cluster 不存在 / 已删 → `404`）**可区分**渲染（R-QUERY-004）。
   - 错误按 `error.code` 分支（不解析 `message`）；`UNAUTHENTICATED` 交由既有全局会话失效处理。
   - 每行提供详情 / 删除入口；删除二次确认（`ElPopconfirm`），失败按 `error.code` 渲染（`409` / `404` / `401` 分别处理），提交中 Loading 且禁重复提交。
   - 提供登记表单入口（对话框或独立表单，交互形式自定）。
3. **`pages/BareMetalDetailPage.vue`**：
   - 调用 `GET /api/bare-metals/{id}`；`404` → 独立 Not Found 态。
   - 展示 `cluster_id` / `hostname` / `status` / R-BM-007 七字段（`null` 渲染为「—」或等价空值，与契约「返回 `null` 不省略」一致）。
   - 提供状态修改入口（`PATCH`）与删除入口；`hostname` / `cluster_id` **不可编辑**（不在 PATCH 契约内）。
4. **`App.vue` 视图状态扩展**（沿用无 vue-router 现状，导航形式不构成产品规则）：在 `ClusterListPage` / `ClusterDetailPage` 之外增加 BareMetal 列表 / 详情视图状态与切换；提供从 Cluster 详情进入「该集群 BareMetal」的入口（携带 `cluster_id`）。
5. **禁止在前端重复实现业务守关**（§21）：同 Cluster `hostname` 唯一、状态封闭集合、父存在性 / 活跃性、删除守卫一律由后端裁决；前端**不得**自行预判或隐藏入口替代后端校验。
6. **不做**：NIC/IP/VM/Container/Service UI、导入、审计 / 历史、恢复 / 回收站、批量操作、筛选 / 导出。

---

## API Contract

### Status

```text
READY
```

### Contract

完整正文见 **`docs/api/f002-bare-metal.md`**（本 Feature 唯一权威契约）。要点：

- **5 个端点**：`POST /api/bare-metals`（`201`）、`GET /api/bare-metals`（`200` + 分页，可选 `cluster_id`）、`GET /api/bare-metals/{bare_metal_id}`（`200`）、`PATCH /api/bare-metals/{bare_metal_id}`（`200`）、`DELETE /api/bare-metals/{bare_metal_id}`（`204`）。
- 资源表示字段集合**封闭**为 `{id, cluster_id, hostname, status, vendor, model, serial_number, cpu, memory, gpu, storage, created_at, updated_at}`；`deleted_at` 不暴露；无位置 / 上级字段。
- `GET /api/bare-metals?cluster_id={id}`：Cluster 存在但无活跃 BareMetal → `200` + `items==[]`；Cluster 不存在或已逻辑删除 → `404 NOT_FOUND`。
- 创建引用不存在 / 已删 Cluster → `404 NOT_FOUND`（NQ-2 裁定），**不产生写入、非 5xx**。
- 同 Cluster 活跃 `hostname` 重复 → `409 CONFLICT` + `details[].field="hostname"`、`details[].code="DUPLICATE"`；大小写敏感、跨 Cluster 可重、软删释放。
- `DELETE` 委托统一软删服务；BareMetal 自身无活跃子资源（当前），存在活跃子资源 → `409 CONFLICT` + `details[].code="ACTIVE_CHILDREN_EXIST"`（未来 F004/F006/F007/F008 触发）。
- 通用规范（`/api` 前缀、分页信封、字段类型、错误信封、状态码、Empty/Not Found、`deleted_at` 不暴露）遵循 `docs/api/api-conventions.md`，不重复定义。
- **不提供**：`by-name` 别名、restore / undelete / purge / 批量 / `include_deleted`。
- 认证：所有 `/api/*` 由 F013 中间件自动覆盖（无白名单）；未认证 → `401 UNAUTHENTICATED`，不改数据。

---

## Test Work

Testing Agent 应验证以下最小集合，逐条映射 AC-01 ~ AC-30。测试可用数据层直接预置（不依赖其它 Feature）。

### API + DB 行为

| # | 测试 | 层次 | AC |
|---|---|---|---|
| **T-01** | `POST`（活跃 Cluster + 唯一 hostname）→ `201`，响应字段集合**恰为** 13 字段；**无** `deleted_at`、无位置 / 上级字段 | API | AC-01 |
| **T-02** | `POST` 缺 `hostname` / 非字符串 → `400 VALIDATION_ERROR`，`details[].field=="hostname"`，**无写入** | API | AC-02 |
| **T-03** | `POST` 缺 / 非整数 `cluster_id` → `400` `field=="cluster_id"`；引用不存在 / 已软删 Cluster → `404 NOT_FOUND`，**无写入、非 5xx**（NQ-2） | API + DB | AC-03 |
| **T-04** | 同 Cluster 活跃 `n1` 已存在再登记 `n1` → `409` `field=="hostname"` `code=="DUPLICATE"`，无第二条活跃行 | API + DB | AC-04 |
| **T-05** | Cluster A / B 各登记 `n1` → 均 `201`，两条不同记录 | API | AC-05 |
| **T-06** | 同 Cluster `n1` 与 `N1` 共存为两条；精确等值查询不混同 | API + DB | AC-06 |
| **T-07** | 未提供 `status` → `status=="IDLE"`；显式合法状态（若裁定允许，见 PROPOSED）→ 该值 | API + DB | AC-07 |
| **T-08** | 不提供任何 R-BM-007 字段 → `201`，七字段在响应中为 `null`（**返回 `null` 而非省略**） | API | AC-08 |
| **T-09** | 中文 `hostname` 登记并在列表 / 详情按字面值读回（UTF-8 往返） | API + DB | AC-09 |
| **T-10** | `status` 取 `RUNNING` / `idle` / 空串 / `null` → `400` `field=="status"`，不写入（创建与 PATCH 两路径） | API | AC-10 |
| **T-11** | 直连库：`status` 列 `NOT NULL`；`UNKNOWN` 可显式写入；裸插入 `NULL` → `23502`；不存在把 `status` 写 `NULL` 的应用路径 | DB | AC-11 |
| **T-12** | `PATCH` 合法 `status` → `200` 返回新值，再次读取（列表 / 详情）一致 | API + DB | AC-12 |
| **T-13** | `GET /api/bare-metals` 无活跃 → `200` + `{items:[],total:0,page,page_size}`，**非 404**；分页正确 | API | AC-13 |
| **T-14** | `GET /{id}` 不存在 / 已软删 → `404 NOT_FOUND`（不区分） | API | AC-14 |
| **T-15** | 按 Cluster 读取：Cluster 不存在 / 已删 → `404`；Cluster 存在但无活跃 BareMetal → `200` + `items==[]`；只返回该 Cluster 活跃子集 | API + DB | AC-15 |
| **T-16** | 同 Cluster 连续登记 2 台 → 均 `201`；按该 Cluster 读回 2 条，`cluster_id` 相同、`id` 不同 | API + DB | AC-16 |
| **T-17** | 绕过应用层预置 `deleted_at` 非空行 → 不出现在列表 `items` / `total`；按 `id` → `404` | API + DB | AC-17 |
| **T-18** | `DELETE /{id}`（活跃）→ `204` 无响应体；行**仍物理存在**、`deleted_at` 非空；不出现在列表 / 详情 | API + DB | AC-18 |
| **T-19** | 软删 `n1` 后可在**同一 Cluster** 重新登记 `n1` → `201`；旧已删行保留且 `deleted_at` 未被改写 | API + DB | AC-19 |
| **T-20** | 删除 BareMetal 后，所属 Cluster 的 `deleted_at`/`name`/`updated_at` 不变；无其它行被改 / 物理删除 | API + DB | AC-20 |
| **T-21** | 不存在 restore / undelete / purge / 批量删除 / `include_deleted`（负向路由 / 参数断言） | API | AC-21 |
| **T-22** | `BARE_METAL_ACTIVE_CHILD_CHECKS` 为**显式声明**的元组（当前空）；BareMetal 删除路径真实传入它，不假定「无子资源」 | 静态 + API | AC-22 |
| **T-23** | Cluster 下存在活跃 BareMetal → `DELETE /api/clusters/{id}` → `409 CONFLICT` + `details[].code=="ACTIVE_CHILDREN_EXIST"`；该 Cluster `deleted_at` **仍为 NULL** | API + DB | AC-23 |
| **T-24** | 先软删该 Cluster 下全部 BareMetal，再 `DELETE /api/clusters/{id}` → `204` | API + DB | AC-24 |
| **T-25** | 并发「创建 BareMetal vs 删除 Cluster」结束后，孤立记录不变式查询 = **0 行** | 并发（DB） | AC-25 |
| **T-26** | 创建时对父 Cluster 行取 `FOR SHARE` 并确认活跃；未命中活跃父 → 拒绝创建（锁序 / 阻塞断言：父删持 `FOR UPDATE` 时创建阻塞并在父删提交后拒绝） | 并发（DB） | AC-26 |
| **T-27** | `CLUSTER_ACTIVE_CHILD_CHECKS` **非空**且包含「活跃 BareMetal」检查，并断言被 Cluster 删除路径真实消费（F014 NOTE-01） | 静态 + API | AC-27 |
| **T-28** | 请求 / 响应 / 表 / 端点不存在 DataCenter / 园区 / 机房 / 机柜 / U 位 / 自动发现 / 外部同步字段或端点 | API + Schema | AC-28 |
| **T-29** | F002 不注册 NIC / IP / VM / Container / Service 端点；`bare_metals` 无指向这些实体的结构；无 `by-name/{name}/bare-metals` | API + Schema | AC-29 |
| **T-FE-01** | 列表页三种情形渲染互不相同；Empty 与 Not Found 可区分；错误按 `error.code` 分支；删除 / 修改失败按 `409`/`404`/`401` 分别处理；前端不重复实现业务守卫 | 前端组件 | AC-30 |

### 结构 / 静态 guard

| # | guard | 说明 | 关联 |
|---|---|---|---|
| **G-1** | 无 CASCADE（演进既有 `test_g1_no_cascade_foreign_keys`）：`bare_metals` FK 为 `RESTRICT`，`confdeltype='c'` 计数仍为 0 | Schema | AC-20、R-DELETE-005 |
| **G-2** | `bare_metals` 列集合**恰为** 14 列；CHECK 集合**恰为** `{ck_bare_metals_status}`；partial unique predicate 含 `deleted_at IS NULL`；`ix_bare_metals_cluster_id` 存在 | Schema | AC-01/11、未定义约束「不实现」 |
| **G-3** | 表集合 guard **演进**：`tests/database/test_schema.EXPECTED_TABLES`、`tests/database/test_migrations`、`tests/database/helpers.MIGRATION_HEAD`、`tests/test_structure_guard.test_only_expected_tables_registered` 加入 `bare_metals`（**增表演进，不得删测试**） | Schema / 元数据 | 约束 |
| **G-4** | 唯一软删写入路径 allow-list **保持** `{backend/app/deletion/service.py}`；`bare_metals` 无第二处 `deleted_at` 写入、无 `deleted_at = None` | 静态 | AC-18/21、ADR-0004 |
| **G-5** | 未定义约束「不实现」：`bare_metals` 无 `<> ''` / 长度 / `trim` / `/` 禁令 CHECK；ORM / schema 无 `min_length` / `pattern` / `strip`；空串与首尾空白 `hostname` 原样存取 | Schema + 行为 | 假设 5 / NQ-4 |
| **G-6** | `MIGRATION_HEAD` 与 `alembic current` = `0003_f002_bare_metals`；migration 可应用 / 可重复应用 / 可从空库重建 | Schema | 约束 |
| **G-7** | 无通用 `resources` 表 / EAV / STI / 多态 / JSON(B) 列（F012 Q3 元数据 guard 对 `bare_metals` 继续成立） | 静态 | §24 |

### 既有测试的演进（**必须演进，不得删除后不补**）

- `tests/database/test_schema.py::EXPECTED_TABLES`、`tests/database/test_migrations.py`、`tests/database/helpers.py::MIGRATION_HEAD` → 加 `bare_metals` / 改 `0003`（G-3 / G-6）。
- `tests/test_structure_guard.py::test_only_expected_tables_registered` → 集合加 `bare_metals`（G-3 / G-7）。
- `tests/database/test_deletion_schema_guard.py` 无 CASCADE / 认证表无 `deleted_at` → **原样保留**（G-1 持续生效）。
- `tests/test_deletion_guards.py` G-3 allow-list → **原样保留**；补充「BareMetal 删除路径委托 `soft_delete()`」正向前向断言（T-22）。

### 附：NQ-9（FK 字段回退解析）

`FOR SHARE` 父预检使应用路径**不会**触发 `23503`；仍建议补一个「直连库写入无效 `cluster_id` → `23503`」的 DB 层测试，并验证若经应用映射，`details[].field` 不因 F012 F-02 截断为 `cluster`（不改变产品行为）。

---

## 设计问题逐条回应（Product Handoff「Architecture Handoff」12 项）

### 问题 1 — `bare_metals` Schema 与增量 migration

**结论**：新建 migration `0003_f002_bare_metals`（`down_revision=0002_f013_auth`），**一条 `CREATE TABLE`** 建齐 14 列（含 R-BM-007 七列）+ `fk_bare_metals_cluster`（`RESTRICT`）+ `ck_bare_metals_status` + `ux_bare_metals_cluster_hostname_active`（predicate `deleted_at IS NULL`）+ `ix_bare_metals_cluster_id`。**不改 `0001`/`0002`**；表不存在故无数据迁移。同步 `csm-v1-schema-design.md` 与 `f012-baseline-migration.md`（NQ-6）。

**被拒绝的替代方案**：
- 先建无硬件列、再用 `0004` 补七列 → 无收益的两次 migration，且表为首次创建，属过早拆分。
- 七列非空 + 默认 `''` → 违反 R-BM-007「允许 NULL / 纯文本可选」。
- `serial_number` 加唯一约束 → 违反 R-BM-007。
- `status` 用 PostgreSQL `ENUM` → 变更成本高；ADR-0002 已裁定 `TEXT + CHECK`。
- 硬件字段拆成结构化列 / JSONB → 违反 R-BM-007「纯文本」与 §24。
- 加 `COLLATE "C"` / 触发器 / CASCADE → ADR-0002 / ADR-0004 / AGENTS §2.4 明确排除。

### 问题 2 — 端点集合与契约落点

**结论**：确认 **5 端点**（`POST` / `GET` / `GET {id}` / `PATCH {id}` / `DELETE {id}`），资源表示字段集合封闭（AC-01）。**新建 `docs/api/f002-bare-metal.md`** 作为唯一权威契约（`READY`）；通用规范引用 `api-conventions.md`，不重复；`f001-cluster.md` / `f014-soft-delete.md` **不修改**。

**被拒绝的替代方案**：把 F002 端点并入 `f001-cluster.md`（跨资源混契约）；每个端点单独文件（碎片化，无收益）。

### 问题 3 — 创建路径父存在性 / 活跃性 + `FOR SHARE` 协议；NQ-2 响应码

**结论**：
- 创建在**同一请求事务内**执行 `SELECT id FROM clusters WHERE id=:cluster_id AND deleted_at IS NULL FOR SHARE`；未命中 → **`404 NOT_FOUND`**（NQ-2 裁定）。
- 锁序（与 ADR-0004 §5 / DB 设计决策 6 一致）：父删持 `FOR UPDATE` ⇒ 子建 `FOR SHARE` 阻塞、父删提交后重新求值 `deleted_at IS NULL` 未命中 → 拒绝；子建先持 `FOR SHARE` ⇒ 父删 `FOR UPDATE` 阻塞、子建提交后父删活跃子检查命中 → `409`。两种交错都**不产生**「父已删 + 子活跃」。
- 数据库 FK（`RESTRICT`）为第二道防线，应用路径不触发 `23503`。

**为何选 `404` 而非 `400`（NQ-2）**：
1. `api-conventions.md §7` 已立「父资源不存在或已逻辑删除 → 404」的项目级原则；R-BM-001 违规的实质是「被引用父资源不存在」而非「字段格式错误」。
2. 字段格式错误（缺失 / 非整数）保留 `400`；存在性 / 活跃性失败归 `404`，错误性质清晰分层。
3. 与项目「不存在」与「已逻辑删除」一律不区分（统一 `404`）的既有立场一致。
4. 保证「不产生写入、非 5xx」。

**被拒绝的替代方案**：
- `400 VALIDATION_ERROR + details[].field="cluster_id"`：把父资源缺失降级为字段格式问题，且与 `api-conventions §7` 语义张力更大；前端需为「父已消失」与「字段格式」写不同处理，反而不清晰。
- `409 CONFLICT`（跟随 `23503` DB 映射）：依赖 DB 才能判定，无法在 `FOR SHARE` 预检阶段给出，且语义上「引用缺失」不是业务冲突。
- 纯 `SELECT`（不加锁）确认父活跃：并发下可产生孤立记录，违反 AC-25/26。
- 用 FK 替代加锁：FK 无法表达 `deleted_at IS NULL`（DB 设计决策 5）。

### 问题 4 — 按 Cluster 限定读取的路由形态；Empty / Not Found；F002 vs F009

**结论**：F002 提供 **`GET /api/bare-metals?cluster_id={id}`**（集合端点的可选过滤）作为可复用的「按 Cluster 限定读取」能力。语义：
- `cluster_id` 非整数 → `400` `field=="cluster_id"`；
- Cluster 不存在 / 已逻辑删除 → `404 NOT_FOUND`；
- Cluster 存在但无活跃 BareMetal → `200` + `items==[]` / `total==0`；
- 未给 `cluster_id` → 全部活跃 BareMetal（无父语义，`200`）。

F009 后续实现 Cluster 视角别名 `GET /api/clusters/by-name/{name}/bare-metals`（`f001-cluster-handoff.md` PROPOSED #5），其可复用 F002 的查询能力（解析 name→id 后委托同一 service），F009 负责 404 / Empty 的别名语义。

**被拒绝的替代方案**：
- 嵌套 `GET /api/clusters/{cluster_id}/bare-metals`：会把 BareMetal 路由注册进 clusters 模块，跨越 F002/F009 归属，且 ADR-0003 未确立嵌套子集合路径。
- 仅提供无过滤列表、由 F009 自行实现过滤：F002 将缺少 AC-15 所需能力。
- 提供全局 `by-name` 别名：`hostname` 仅按 Cluster 唯一，全局不可判定（PROPOSED-1；ADR-0003 §2 未授予）。

### 问题 5 — `BARE_METAL_ACTIVE_CHILD_CHECKS` 声明位置与追加机制

**结论**：在 **`app/bare_metals/deletion.py`** 声明 `BARE_METAL_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()`（**显式空元组**，不假定无子资源），并由 `delete_bare_metal` **显式传入** `soft_delete(..., active_children=...)`。F004/F006/F007/F008 落地时在**该元组**追加各自的活跃子资源检查（子资源模块提供函数），统一服务核心零改动（F014 问题 2）。

**被拒绝的替代方案**：由统一服务按模型自省外键推导子资源（谓词无法推导、把规则藏进实现）；全局注册表 / import 期自动注册（全局可变状态、fail-open 风险）；每资源一个软删服务子类（无收益继承）。

### 问题 6 — F014 端到端义务的落点

**结论**：
- `app/bare_metals/deletion.py` 提供 `has_active_bare_metals(session, cluster_id)`（`EXISTS` 活跃子行）；`app/clusters/deletion.py` 把 `CLUSTER_ACTIVE_CHILD_CHECKS` 演进为 `(has_active_bare_metals,)`。
- 端到端：Cluster 有活跃 BareMetal → `DELETE /api/clusters/{id}` → `409 CONFLICT` + `details[].code="ACTIVE_CHILDREN_EXIST"`、目标行 `deleted_at` 仍 NULL（T-23）；软删全部 BareMetal 后 → `204`（T-24）。
- 并发端到端：创建 BareMetal（`FOR SHARE`）与删除 Cluster（`FOR UPDATE` + 检查）并发，孤立记录不变式查询 **0 行**（T-25）；`FOR SHARE` 锁序 / 阻塞断言（T-26）。
- F014 `NOTE-01`：断言 `CLUSTER_ACTIVE_CHILD_CHECKS` **非空**且被 Cluster 删除路径真实消费（T-27），消除「空元组 fail-open」默认。

**被拒绝的替代方案**：把检查逻辑硬编码进 `soft_delete`（违反 F014 声明机制）；在 `soft_delete` 内对 `clusters` 特判（把资源知识藏进通用服务）。

### 问题 7 — PATCH 可变字段与状态校验

**结论**：`PATCH` 仅接受 `status` + R-BM-007 七字段（假设 3）；`hostname` / `cluster_id` / `id` / `deleted_at` 不在契约内（NQ-1 未确认，F002 不提供）。未识别字段 → `400`（`extra="forbid"`）；空 body（无任一可变字段）→ `400`；`status` 为 `null` / 非枚举 → `400` `field=="status"`；硬件字段显式 `null` 表示清空。状态校验**唯一一份实现**，`23514` 经既有映射 → `400`（而非 500）。修改路径不处理 `hostname` 唯一性（不可变假设下无需）。

**被拒绝的替代方案**：允许 `hostname` / `cluster_id` 修改（NQ-1 未确认，且迁移需重校验目标 Cluster 唯一性 + 受父删子拦约束）；静默忽略未识别字段（会造成「请求看似成功、实际未改」的误导）。

### 问题 8 — 未定义约束「不实现」保障

**结论**：`hostname` 在 schema / ORM / 校验层**无**任何长度 / trim / 空串 / 字符约束，**无**类似 R-CLUSTER-005 的 `/` 禁令（假设 5 / NQ-4）。以 **G-2**（`bare_metals` CHECK 集合恰为 `{ck_bare_metals_status}`、列集合恰为 14 列）与 **G-5**（空串 / 首尾空白 `hostname` 原样存取的行为断言）固定。`serial_number` 无唯一约束。

**被拒绝的替代方案**：加 `hostname <> ''` 或长度 CHECK（未确认，属新增产品规则）；对 `hostname` 做 trim / 归一化（把建议变成约束）。

### 问题 9 — 删除端点注册与唯一软删写入路径

**结论**：`DELETE /api/bare-metals/{bare_metal_id}` 由 `app/bare_metals/router.py` 注册，`delete_bare_metal` 委托 `soft_delete()`；**不引入**第二条 `deleted_at` 写入路径；不提供 restore / undelete / purge / 批量。G-3 allow-list 保持 `{app/deletion/service.py}`；补「BareMetal 删除委托 `soft_delete()`」正向断言。

**被拒绝的替代方案**：BareMetal 自写 `UPDATE ... SET deleted_at`；在 `app/deletion` 增加资源分支；直接物理删除。

### 问题 10 — 前端接线

见 Frontend Work。三态 + Empty/Not Found 区分；错误按 `error.code`（`VALIDATION_ERROR` / `NOT_FOUND` / `CONFLICT` / `UNAUTHENTICATED`）；删除 / 修改失败按 `409` / `404` / `401` 分别处理；**前端不重复实现业务守卫**（§21）；Loading 与防重复提交。

### 问题 11 — 交付层判定

```text
database: true
backend:  true
frontend: true
```

- **database = true**：新增 `bare_metals` 表 + migration `0003` + schema 文档同步；判定依据是「需要 schema 变更」。
- **backend = true**：模型 / 校验 / repository / service / router / F014 接线 / guard 演进 / 测试。
- **frontend = true**：BareMetal API 客户端与页面、三态与错误分支、删除 / 状态维护入口。
- 协调器需同步 `project-plan.yaml` F002 的 `layers` / `contract` / `implementation`，并落 NQ-7（后续 Feature 追加 BareMetal 子资源检查 + `409` 端到端）与 NQ-8（元数据，已部分完成）。

### 问题 12 — 既有测试的演进

**结论**：`bare_metals` 是首张非 Cluster 资源表与首个真实 FK。既有 guard **随增表演进而非删除**：
- **表集合 guard**（`test_schema.EXPECTED_TABLES` / `test_migrations` / `helpers.MIGRATION_HEAD` / `test_only_expected_tables_registered`）→ 加 `bare_metals`、改 `0003`（G-3 / G-6）。
- **无 CASCADE guard**（`test_deletion_schema_guard`）→ 原样保留，随新 FK 持续生效（G-1）。
- **唯一软删写入路径 guard**（`test_deletion_guards` G-3 allow-list）→ 原样保留，补 BareMetal 删除委托正向断言（G-4 / T-22）。
- `clusters` 结构 guard（`test_g2_schema_guard`）→ 原样保留（`clusters` 不变）。

---

## Technical Decisions

### CONFIRMED（用户 / 产品 / 已批准架构文档）

- 技术栈、PostgreSQL、Alembic、BIGINT identity、错误信封与状态码语义、`by-name` 只读别名（ADR-0001~0005 全部 `ACCEPTED`）。
- `bare_metals` 关键列与约束语义：`cluster_id NOT NULL` + FK `RESTRICT`、`hostname NOT NULL`、`status NOT NULL DEFAULT 'IDLE' + CHECK` 四值、R-BM-007 七列可选 `TEXT NULL`、`deleted_at`（ADR-0002/0004；R-BM-001~007）。
- 同 Cluster 活跃 `hostname` 唯一、大小写敏感、跨 Cluster 可重、软删释放（R-BM-002、§22、R-DELETE-006、ADR-0004）。
- 父删子拦同事务加锁、不级联、无 undelete；创建对父行取 `FOR SHARE`（ADR-0004、DB 设计决策 6）。
- 写走 `id`；`deleted_at` 不暴露；可选字段空值返回 `null`；不存在 / 已删一律 `404` 不区分；Empty（200 空集）与 Not Found（404）可区分（ADR-0003、`api-conventions.md`）。
- 认证：所有 `/api/*` 由 F013 中间件自动覆盖，无白名单（ADR-0005）。
- 禁止 EAV / 通用 `resources` 表 / STI / ORM 多态 / JSONB 万能模型（§4、§24）。

### REQUIRED（由需求自然产生，为正确性必须满足）

1. `bare_metals` 唯一性由 **partial unique index** 强制，predicate 与查询过滤一致（`deleted_at IS NULL`）。
2. 创建**必须在同一事务内**对父 Cluster 取 `FOR SHARE` 并确认活跃；未命中即拒绝（AC-26）。
3. `deleted_at` 写入路径**恰好 1 条**；BareMetal 删除必须委托 `soft_delete()`（ADR-0004 §3）。
4. Cluster 删除路径的活跃子资源检查**必须包含** BareMetal 活跃检查；`CLUSTER_ACTIVE_CHILD_CHECKS` **非空**（AC-23/27；F014 NOTE-01）。
5. `status` 校验为**唯一一份**领域实现，`23514 → 400`（不返回 500）。
6. `hostname` / `serial_number` **不得**有隐式长度 / trim / 字符 / 唯一约束（假设 5；R-BM-007）。
7. 不新增任何 CASCADE / 触发器 / `COLLATE`；不改 `0001`/`0002` 基线。
8. 既有 schema 表集合 guard、无 CASCADE guard、唯一软删写入路径 guard **必须演进 / 保留**，不得删除后不补。
9. 生成接口的失败**不得**依赖前端；守卫由后端裁决（§21）。

### PROPOSED（Architect 建议）

1. **契约落点**：新增 `docs/api/f002-bare-metal.md`（不修改既有契约）。
2. **NQ-2 响应码**：引用不存在 / 已删 Cluster → `404 NOT_FOUND`（设计问题 3）。
3. **按 Cluster 读取路由形态**：`GET /api/bare-metals?cluster_id=`（设计问题 4）。
4. **模块布局**：`app/bare_metals/`（`schemas` / `validation` / `repository` / `service` / `router` / `deletion`）；`app/models/bare_metal.py`。
5. **F014 接线位置**：`has_active_bare_metals` 在 `app/bare_metals/deletion.py`，由 `app/clusters/deletion.py` 追加。
6. **PATCH 契约细节**：`extra="forbid"`；至少一个可变字段；`status` 不可为 `null`；硬件字段显式 `null` 清空。
7. **POST 可选 `status`**：缺省 `IDLE`，提供时校验封闭集合（与 AC-07 表述一致；见 Non-blocking Open NQ-3）。
8. **页面 / 导航形式**：沿用无 `vue-router` 的 `App.vue` 视图切换；列表 / 详情 / 登记 / 状态 / 删除入口；交互形式不构成产品规则。
9. 分页沿用 `page_size` 默认 50 / 上限 200。

### OPEN（非阻塞）

1. **NQ-3**：`POST` 是否允许显式非 `IDLE` 状态（产品 PROPOSED-2，需用户裁定）。当前按 PROPOSED 7 支持可选 `status`；若用户确认「登记只能 `IDLE`」，仅需从 POST 契约移除 `status`（加性回退，不改数据）。
2. **NQ-1**：`hostname` / `cluster_id` 登记后可变性（产品 PROPOSED-3，需用户裁定）；F002 不实现。
3. **NQ-4**：`hostname` 未定义字符约束（产品 PROPOSED-4）；F002 不实现、不承诺。
4. **NQ-7**：F004/F006/F007/F008 追加 BareMetal 子资源检查与 `409` 端到端；本 Feature 建立声明点。
5. **NQ-9**：`sqlstate.field_for` 对 `cluster_id` 的回退截断（F012 F-02）；本 Feature 应用路径不可达，建议补 DB 层测试。
6. 运行时 `deleted_at` 写入拦截（事件监听）——当前以静态 guard 满足，不引入（承 F014 OPEN#1）。
7. F014 Review「G-3 扫描器扩展到 `values({...})` / `values(**{...})` 的 AST 扫描」——建议在 F002 批次内评估，非 AC 要求（承 project-plan follow-up）。

---

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | `POST` 引用已删 / 不存在 Cluster 的响应码（NQ-2）若与前端预期不一致，造成状态处理错位 | 契约固定 `404 NOT_FOUND` 并写入 `docs/api/f002-bare-metal.md`；T-03 直接断言；标记 PROPOSED 可回退 |
| R2 | F014 交接的并发端到端（AC-25/26）可能在实现中被简化 | 显式列入 AC-23~27 与 T-23~27；`CLUSTER_ACTIVE_CHILD_CHECKS` 非空断言（NOTE-01）防 fail-open |
| R3 | 未定义约束被「顺手」加上（`hostname <> ''` / 长度 / `/` 禁令） | G-2 / G-5 可失败 guard + 行为断言 |
| R4 | 新增表后既有表集合 guard 被「删掉」而非演进，验证力降低 | REQUIRED #8；G-3 / G-6；代码评审检查项 |
| R5 | 唯一性 / FK / CHECK 冲突返回 500 | 应用层预检 + 既有 SQLSTATE 映射（23505→409、23514/23502→400、23503→409）；T-03/04/10/11 断言非 5xx |
| R6 | `POST` 可选 `status`（NQ-3）未经用户确认 | PROPOSED 7 + OPEN NQ-3；回退仅需移除该字段 |
| R7 | partial index predicate 与查询过滤错位（「查得到却写不进」） | 读取统一经 `active_filter` / `select_active`；G-2 断言 predicate |
| R8 | 文档漂移（schema-design / baseline-migration 未含七列）导致 Database 与 Handoff 不一致 | Database Work 明确同步项（NQ-6）；协调器落盘 |

---

## Constraints

1. 不得修改或新增 `clusters` / `users` / `sessions`；不得改 `0001` / `0002` 基线；只新增 `0003`。
2. 不得新建与 R-BM-007 冲突的约束；`serial_number` 不得唯一；`hostname` 不得加未确认的长度 / trim / 字符 / `/` 约束。
3. 不得实现第二条 `deleted_at` 写入路径；不得实现 restore / undelete / purge / 批量删除；不得出现 `deleted_at = None`。
4. 不得偏离 `api-conventions.md` 的信封、状态码与 Empty / Not Found 语义；不得另立第二套 SQLSTATE 映射。
5. 不得在前端重复实现业务守卫（§21）；唯一性 / 状态 / 父活跃 / 删除守卫由后端裁决。
6. 不得引入新框架 / 新中间件 / 新依赖；不得引入 EAV / 通用表 / STI / ORM 多态 / JSONB 万能模型。
7. 不得新增 CASCADE / 触发器 / `COLLATE`；`updated_at` 由应用层维护，不得作为审计或并发控制依据。
8. 所有端点必须在 `/api` 前缀下，使 F013 认证自动覆盖，不新增白名单。
9. 不得修改 `docs/api/f001-cluster.md` / `f014-soft-delete.md` / `api-conventions.md` 正文；F002 契约唯一正文在 `docs/api/f002-bare-metal.md`。
10. F002 不注册 NIC / IP / VM / Container / Service 端点，不提供 `by-name` 别名。

---

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

1. **NQ-3**（`POST` 显式指定状态）：产品 PROPOSED-2；当前实现假设（PROPOSED 7）。需用户裁定；不阻塞实现。
2. **NQ-1**（`hostname` / `cluster_id` 可变性 / 跨 Cluster 迁移）：产品 PROPOSED-3；F002 不实现。
3. **NQ-4**（`hostname` 字符约束）：产品 PROPOSED-4；F002 不实现、不承诺。
4. **NQ-7**（后续 Feature 的 BareMetal 子资源删除守卫）：F002 建立声明点并记入 `project-plan.yaml` 的 F004/F006/F007/F008 义务。
5. **NQ-9**（`cluster_id` FK 字段回退解析）：F012 F-02；本 Feature 应用路径不可达，建议补测试。
6. F014 Review：G-3 扫描器 AST 化（`values({...})` / `values(**{...})`）——建议在 F002 批次评估。
7. 运行时 `deleted_at` 写入拦截（承 F014）——当前不引入。

---

## Implementation Layers

```text
database: true
backend:  true
frontend: true
```

- **database**：`bare_metals` 表 + migration `0003_f002_bare_metals`；schema 文档同步；结构 / 约束 guard。实现由 Backend 负责。
- **backend**：`app/models/bare_metal.py`、`app/bare_metals/**`、`app/clusters/deletion.py` 演进、`app/main.py` 挂载、`app/models/__init__.py` 注册、guard 演进与全测试集。
- **frontend**：`src/api/bareMetals.ts`、`pages/BareMetalListPage.vue`、`pages/BareMetalDetailPage.vue`、`App.vue` 视图状态扩展、登记 / 状态 / 删除入口与三态 / 错误分支。

**文件所有权**：Backend = `backend/**` + `tests/**`；Frontend = `frontend/**`；共享 `docs/**` 由协调器统一落盘。

---

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f002-bare-metal.md，均 READY）
  ├─ Frontend（契约稳定即可开工：api/bareMetals.ts → 列表 / 详情 / 登记 / 状态 / 删除 → 三态与错误分支）
  └─ Database Design（同步 csm-v1-schema-design.md / f012-baseline-migration.md 的 bare_metals 七列）
        → Backend（migration 0003 → 模型 → 校验 / repository / service / router
                   → F014 接线：clusters/deletion 追加 BareMetal 检查
                   → guard 演进 + 全测试集）
                 ↓ 所有必需实现分支完成
              Tester → Reviewer
```

- Backend 与 Frontend 在契约 `READY` 后可直接并行；Database Design 分支为 Backend 的前置（`database: true`）。
- 协调器需落盘：本 Handoff、`docs/api/f002-bare-metal.md`、schema 文档同步，并同步 `project-plan.yaml` F002 的 `layers` / `contract` / `implementation` 与 NQ-7 义务。

---

## Verification Strategy

1. **契约层（AC-01/02/03/13/14/15/21）**：字段集合封闭、必填校验、父存在性 / 活跃性、列表 Empty 与详情 Not Found、按 Cluster Empty vs Not Found、负向路由 / 参数（T-01/02/03/13/14/15/21）。
2. **唯一性（AC-04/05/06/19）**：同 Cluster 重复 `409`、跨 Cluster 可重、大小写敏感、软删释放（T-04/05/06/19）+ DB 直插断言（绕过应用层）。
3. **状态与硬件字段（AC-07/08/10/11/12）**：默认 `IDLE`、可选字段 `null` 返回、封闭集合 `400`、`NOT NULL`、PATCH 维护（T-07/08/10/11/12）。
4. **查询软删过滤（AC-17/18/14）**：数据层预置已删行不出现在列表 / 详情、`DELETE` 后行仍物理存在（T-17/18/14）。
5. **删除生命周期（AC-18/19/20/21/22）**：唯一软删路径、释放唯一性、不级联、无恢复 / 批量、显式空检查点（T-18/19/20/21/22 + G-4）。
6. **F014 端到端（AC-23/24/25/26/27）**：Cluster 有活跃 BareMetal → `409` 无部分写入；软删后可删；并发孤立记录不变式 0 行；`FOR SHARE` 锁序；`CLUSTER_ACTIVE_CHILD_CHECKS` 非空且被消费（T-23~27）。
7. **边界（AC-28/29）**：无位置 / 上级 / 自动发现结构；不越界其它资源端点（T-28/29）。
8. **前端（AC-30）**：三态区分、Empty / Not Found 区分、`error.code` 分支、不重复实现守卫（T-FE-01）。
9. **数据层结构（G-1~G-7）**：无 CASCADE、`bare_metals` 列 / CHECK / index 精确、表集合 guard 演进、allow-list 不退化、未定义约束不实现、迁移可重建、无 EAV / 多态。
10. **工程门禁**：lint 通过；既有 F012/F013/F014/F015 测试全绿；schema 集合 guard 完成演进而非删除。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：Product Handoff 为 `READY FOR ARCHITECT` 且无 Blocking；所有输入为 `READY` / `ACCEPTED` / `CONFIRMED`；API Contract Status = `READY`；三个实现分支（database / backend / frontend）均有可直接开工的依据；12 项待决技术问题已逐条裁定（含被拒绝替代方案）与迁移规格。

**需用户确认的长期技术决策：无。** NQ-1 / NQ-3 / NQ-4 为产品侧 PROPOSED（不阻塞范围，F002 采用的产品假设已在契约中显式标注）；NQ-2（引用不存在父的响应码）为 Architect 在既有约定内填补契约空白的内部裁定，不属需用户批准的长期架构决策。