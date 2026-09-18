# Architecture Handoff — F006 VirtualMachine 登记与管理

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Feature: F006（E03，P1，`depends_on: [F002]` = DONE）
> 配套契约：`docs/api/f006-virtual-machine.md`（`READY`）
> Product Source: `docs/product/handoffs/f006-virtual-machine.md`（`READY FOR ARCHITECT`，无 Blocking）

---

## Feature

VirtualMachine 登记与管理（F006）— CSM V1 虚拟资源的第一个资源：虚拟机的人工登记、查询、可选配置维护与逻辑删除，以及 **VirtualMachine → BareMetal 必选绑定**的真实业务落地，并作为 F014「宿主有活跃子 VM → 不得删宿主」的第二个真实端到端。

## Status

`READY FOR IMPLEMENTATION`（无 Blocking；API Contract = `READY`）。

## Context — 现状核实（只读检查结论）

| 项 | 现状（已核实） |
|---|---|
| Backend | **已存在**：应用工厂（`app/main.py` 挂载 `/api` → health + clusters + cluster_views + bare_metals + auth）、F013 认证中间件（`/api/*` 自动覆盖，仅登录豁免）、统一错误信封与全局 handler（`common/errors.py` / `error_handlers.py`）、通用 SQLSTATE→HTTP 映射（`common/sqlstate.py`：23502/23514→400、23505/23503→409）、分页（`common/pagination.py`，默认 50 / 上限 200）、请求级事务边界（`api/deps.py`）、活跃过滤原语（`db/active.py`） |
| 统一软删服务 | **已存在** `backend/app/deletion/`：`service.soft_delete()`（系统内唯一写 `deleted_at` 的路径）、`checks.ActiveChildCheck`。`app/bare_metals/deletion.py` 声明 `BARE_METAL_ACTIVE_CHILD_CHECKS: tuple = ()` + `has_active_bare_metals`；`app/clusters/deletion.py` 声明 `CLUSTER_ACTIVE_CHILD_CHECKS = (has_active_bare_metals,)` |
| BareMetal 模块 | **已存在** `app/bare_metals/**`（模型 / schema / validation / repository / service / router / deletion），5 个端点，创建对父 Cluster 行取 `FOR SHARE` 并同事务确认活跃 |
| Database | `clusters`（`0001`，冻结）+ `users` / `sessions`（`0002`）+ `bare_metals`（`0003`）。**`virtual_machines` 表不存在**。`tests/database/helpers.MIGRATION_HEAD = "0003_f002_bare_metals"`；`EXPECTED_TABLES = {alembic_version, clusters, users, sessions, bare_metals}` |
| Frontend | **已存在** `frontend/src/**`：`api/http.ts`（错误归一 + 全局 401）、`api/bareMetals.ts`、`components/ListStates.vue` / `ErrorState.vue` / `BareMetalFormDialog.vue`、`composables/useAsyncQuery.ts` / `useResourceDelete.ts` / `useBareMetalDelete.ts`、`pages/BareMetalListPage.vue` / `BareMetalDetailPage.vue`、`App.vue` 极简视图切换（**无 vue-router**）。**无 VM 相关 UI** |
| 相关 guard（须演进） | `tests/test_bare_metals_guards.py::test_t22_bare_metal_active_child_checks_explicitly_declared`（断言 `== ()`）；`test_structure_guard.test_only_expected_tables_registered`；`tests/test_auth_guards.py::EXPECTED_GET_ROUTES`；`tests/database/{helpers,test_schema,test_migrations}` |

**结论**：F006 是在非空、已具 F012/F013/F014/F002 基座的项目上的增量交付。需**新增一张表 + 一次增量 migration**；删除、错误信封、分页、事务、活跃过滤、父删子拦机制与 `FOR SHARE` 并发协议**全部复用既有基座**，不另立一套。

---

## Architecture Summary

**对现有系统的影响**：
- 新增模块 `backend/app/virtual_machines/`（模型 + schema + repository + service + router + deletion 声明）。
- 新增 ORM 模型 `app/models/virtual_machine.py`，注册到 `app/models/__init__.py`，并在 `app/main.py` 挂载路由。
- **改** `app/bare_metals/deletion.py`：把 `BARE_METAL_ACTIVE_CHILD_CHECKS` 从显式空元组演进为包含「活跃 VirtualMachine」检查（F014 端到端义务）。
- 新增 migration `0004_f006_virtual_machines`（**不改 `0001` / `0002` / `0003`**）。
- 新增前端 VM API 客户端与页面。
- 演进既有表集合 / 路由集合 / BareMetal 检查点 guard（**增表 / 增路由 / 增检查，不删测试**）。

**方案要点**：
1. **数据层**：`virtual_machines` 一次 `CREATE TABLE` 建齐 `bare_metal_id NOT NULL + FK RESTRICT`、`name NOT NULL`、六个可空 `TEXT` 列、`deleted_at`；**无 `status` 列**、**无 `cluster_id` 列**；partial unique `ux_virtual_machines_name_active`（全局、predicate `deleted_at IS NULL`、大小写敏感、不声明 `COLLATE`）；`ix_virtual_machines_bare_metal_id`。
2. **唯一性**：全局活跃 `name` 唯一、跨宿主跨 Cluster、软删释放——partial unique index 为最终权威，应用层仅做友好 `409` 预检。
3. **创建关系写入**：创建对宿主 BareMetal 行取 `FOR SHARE` 并在同一事务内确认活跃；未命中 → `404 NOT_FOUND`。与 F014 的 `FOR UPDATE` 删除协议共同保证「不存在宿主已删 + VM 活跃」。
4. **删除**：`DELETE /api/virtual-machines/{id}` 委托**唯一**软删服务；VM 以 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS`（显式空元组）声明自身子资源检查点（F007 追加位置）；BareMetal 删除路径追加「活跃 VM」检查。
5. **可复用宿主限定读取**：`GET /api/virtual-machines?bare_metal_id={id}` 由 F006 提供 canonical 过滤能力（与 F002 `?cluster_id=` 对称），F010 必须复用（决策 3）。
6. **未定义约束不实现**：`name` 与六个可选字段无长度 / trim / 空串 / 字符 / `/` 约束，不做归一化；以可失败 guard 固定。
7. **无状态 / 无越界 / 无平台接入**：VM 无 `status`、无 `cluster_id`、无 NIC / IP / Container / Service / DataCenter 结构、无虚拟化平台客户端 / 凭据 / 同步字段。
8. **无新框架 / 无新依赖 / 无 EAV / 无通用表 / 无多态 / 无 CASCADE / 无触发器 / 无 COLLATE / 无 vue-router**；契约落点新增 `docs/api/f006-virtual-machine.md`。

---

## Domain Impact

**使用**已有领域对象 `BareMetal`（R-VM-005 的 N:1 宿主）。

**新增领域对象**：**无**。VirtualMachine 作为资源实体**已由 CONFIRMED 产品文档确定**（R-VM-001~006）。本 Feature 只将其**落地**为表、模型与 API，不新增 / 不修改任何领域对象、字段、关系、状态或唯一性规则。

- 关系：`VirtualMachine → BareMetal` N:1 mandatory（R-VM-005）——**CONFIRMED**。
- Cluster 归属**由宿主推导，不落列**（R-VM-005）；**无 `cluster_id`**。
- 状态：**无**（Q-002=B）。
- 唯一性：**全局活跃 `name` 唯一**（跨宿主跨 Cluster），区分大小写，已软删释放（R-VM-004 + R-DELETE-006）。与 Container 的「同一载体内唯一」是**不同边界**。
- 生命周期：`soft_delete: true` / `cascade: false` / 宿主有活跃 VM 不得删（ADR-0004；R-DELETE-004/005）。

---

## Data Layer Impact

1. **建表**：`virtual_machines`（首张以 BareMetal 为宿主的资源表）。
2. **唯一性**：全局活跃 `name` 唯一（partial unique index，predicate `deleted_at IS NULL`），大小写敏感（默认 collation）。
3. **关系完整性**：`bare_metal_id NOT NULL` + FK `ON DELETE RESTRICT ON UPDATE RESTRICT`（禁止 CASCADE）。
4. **宿主检索索引**：`ix_virtual_machines_bare_metal_id`。
5. **软删**：`deleted_at TIMESTAMPTZ NULL`，仅由统一软删服务写入。
6. **不做**：不改既有表与 `0001` / `0002` / `0003`；无数据迁移；无 `status` 列；无 `cluster_id` 列；无触发器；无 `COLLATE`；无 `name` 长度 / trim / 字符 / `/` CHECK；无 NIC / IP / Container / Service / DataCenter 结构。

---

## Decisions（问题 1 ~ 13）

### 问题 1 — `virtual_machines` Schema 与增量 migration

**结论**：新建 migration `0004_f006_virtual_machines`，`down_revision = "0003_f002_bare_metals"`（当前 head，维持单一线性 head）。**一条 `CREATE TABLE`** 建齐 12 列 + PK + FK + partial unique index + 宿主检索索引。

```sql
CREATE TABLE virtual_machines (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  bare_metal_id BIGINT      NOT NULL,      -- R-VM-005 宿主（必选，恰好一个）
  name          TEXT        NOT NULL,      -- R-VM-004 身份标识
  cpu           TEXT        NULL,           -- R-VM-006
  memory        TEXT        NULL,
  disk          TEXT        NULL,
  os            TEXT        NULL,
  hypervisor    TEXT        NULL,           -- 仅文本登记字段
  owner         TEXT        NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ NULL,
  CONSTRAINT pk_virtual_machines PRIMARY KEY (id),
  CONSTRAINT fk_virtual_machines_bare_metal FOREIGN KEY (bare_metal_id)
    REFERENCES bare_metals (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE UNIQUE INDEX ux_virtual_machines_name_active
  ON virtual_machines (name) WHERE deleted_at IS NULL;      -- R-VM-004 + R-DELETE-006

CREATE INDEX ix_virtual_machines_bare_metal_id
  ON virtual_machines (bare_metal_id);
```

`downgrade`（逆序）：`drop ix_virtual_machines_bare_metal_id` → `drop ux_virtual_machines_name_active` → `drop table virtual_machines`。破坏性，生产禁止。

**规格约束（REQUIRED）**：
- 宿主列名 **`bare_metal_id`**；FK `fk_virtual_machines_bare_metal`，`ON DELETE RESTRICT ON UPDATE RESTRICT`，**禁止 CASCADE**。
- `name NOT NULL`（**不得**加长度 / trim / 空串 / 字符 / `/` 约束）。
- 六个可选列恰为 `cpu / memory / disk / os / hypervisor / owner`，均为可空 `TEXT`。
- **无 `status` 列**、**无 `cluster_id` 列**。
- 唯一性为 **`name` 上的全局 partial unique index**（predicate `deleted_at IS NULL`，大小写敏感，**不声明 `COLLATE`**，不使用 `lower()`）。
- identity 用 `sa.Identity(always=True)`；时间列 `server_default=sa.text("now()")`；遵循既有 `NAMING_CONVENTION`。
- **不改 `0001` / `0002` / `0003`**；无数据迁移。

**文档同步（漂移 4）**：`docs/database/csm-v1-schema-design.md` 需新增 `virtual_machines` 段、把「VM → BareMetal 未确认 / 不得固化为 NOT NULL」改为 **N:1 mandatory**、修正「VM 可反规范化 `cluster_id`」注记（已被取代，VM 名称**全局**唯一、**不需要** `cluster_id`）、增补 Required Constraints / Indexes。`docs/database/f012-baseline-migration.md` revision 表加 `0004`（建议）。由协调器落盘。

**被拒绝的替代方案**：加 `status` 列（违反 Q-002=B）；加 `cluster_id`（R-VM-005 明确不记录）；宿主列可空再补 NOT NULL（表为首次创建，无收益）；`name` 加 CHECK（未定义约束）；`lower(name)` 唯一索引（改规则为大小写不敏感）；`ON DELETE CASCADE` / 触发器（R-DELETE-005 / ADR-0004）。

### 问题 2 — 端点集合与资源表示封闭性

**结论**：确认 **5 个端点**，路径 `/api/virtual-machines`：`POST`（`201`）、`GET`（`200` + 分页，可选 `bare_metal_id`）、`GET /{virtual_machine_id}`（`200`）、`PATCH /{virtual_machine_id}`（`200`）、`DELETE /{virtual_machine_id}`（`204`）。

资源表示字段集合**封闭**为 `{id, bare_metal_id, name, cpu, memory, disk, os, hypervisor, owner, created_at, updated_at}`。**不含** `deleted_at` / `status` / `cluster_id` / NIC / 位置 / 平台同步字段。请求 schema 同样封闭（`extra="forbid"`）。契约唯一权威：`docs/api/f006-virtual-machine.md`。

### 问题 3 — NQ-4 归属裁定：「按宿主查看 VM」读取方向

**结论（Architect 裁定）**：**F006 提供 `GET /api/virtual-machines?bare_metal_id={id}`** 作为 canonical 宿主限定读取能力；**R-QUERY-003 的关联查询视图仍归 F010**，F010 必须复用本能力。

语义（满足 R-QUERY-004）：`bare_metal_id` 非整数 → `400`；宿主不存在或已逻辑删除 → **`404 NOT_FOUND`**；宿主存在但无活跃 VM → **`200` + `items == []`**；未提供 `bare_metal_id` → 全部活跃 VM（`200`）。

**理由**：与 F002 `?cluster_id=` 完全对称（F009 复用该模式）；避免 F010 侵入 VM 模块；仅一个可选 query parameter，**不新增端点 / 领域字段**，不是范围扩张；否则 F010 需重复实现过滤与 R-QUERY-004 语义。

**被拒绝**：完全归 F010（与先例不对称、重复实现）；嵌套路由 `GET /api/bare-metals/{id}/virtual-machines`（跨模块、ADR-0003 未确立）；全局 `by-name` 别名（需求未授予）。

### 问题 4 — NQ-2 裁定：引用不存在 / 已软删宿主的响应码

**结论**：`POST` 与 `?bare_metal_id=` 在宿主**不存在或已逻辑删除**时返回 **`404 NOT_FOUND`**（`details == []`），**不产生任何写入、永不为 5xx**。

**理由**：与 F002 NQ-2 裁定一致；字段格式错误保留 `400`，存在性 / 活跃性失败归 `404`；「不存在」与「已软删除」不区分。

### 问题 5 — 创建路径并发协议；FK 违规与预检的响应映射

**结论**：
- **创建**在**同一请求事务内**执行 `SELECT id FROM bare_metals WHERE id = :bare_metal_id AND deleted_at IS NULL FOR SHARE`；未命中 → `404 NOT_FOUND`。**锁序与 F002 / F014 完全对齐**。
- **交错分析**：宿主删先持 `FOR UPDATE` ⇒ VM 建阻塞、宿主删提交后 VM 建在 `READ COMMITTED` 下重新求值未命中 → 拒绝；VM 建先持 `FOR SHARE` ⇒ 宿主删阻塞、VM 建提交后宿主删的活跃子检查命中 → `409`。两种交错都**不产生**「宿主已删 + VM 活跃」。
- **FK 违规映射**：正常路径由 `FOR SHARE` 预检给出 `404`，应用路径**不会**触发 `23503`；若绕过预检，经**既有通用** `sqlstate.py` 返回 `409 CONFLICT` + `details[].code = "REFERENCE"`，仍非 5xx；**不为 VM 另立映射**。该路径在本 Feature 内**不可达**（宿主无物理删除）。

**被拒绝**：纯 `SELECT` 不加锁（并发下产生孤立记录）；用 FK 替代加锁（FK 无法表达 `deleted_at IS NULL`）；`SERIALIZABLE` 隔离（过度）。

### 问题 6 — R-VM-004 全局唯一性落地

**结论**：应用层预检活跃范围内 `name` 已存在 → `409 CONFLICT`，`details[].field == "name"`、`details[].code == "DUPLICATE"`（大小写敏感，字面值等值）。数据库 `ux_virtual_machines_name_active` 为**最终权威**；绕过应用层直插重复活跃 `name` 被 `23505` 拒绝 → 既有映射返回 `409`。**不引入任何大小写折叠**。已软删 VM **释放**唯一性。唯一性边界是**全局**。

### 问题 7 — F014 端到端义务落点

**结论**：
- 新增 `app/virtual_machines/deletion.py`：`has_active_virtual_machines(session, bare_metal_id) -> bool`（`EXISTS` 活跃 VM，复用活跃过滤原语）。
- **改** `app/bare_metals/deletion.py`：`BARE_METAL_ACTIVE_CHILD_CHECKS` 从**显式空元组演进**为 `(has_active_virtual_machines,)`（无循环导入）。
- `app/bare_metals/service.delete_bare_metal` 已传入 `active_children=BARE_METAL_ACTIVE_CHILD_CHECKS`，**无需改删除路径逻辑**。
- 端到端：宿主有活跃 VM → `DELETE /api/bare-metals/{id}` → `409` + `details[].code == "ACTIVE_CHILDREN_EXIST"`、宿主 `deleted_at` 仍 NULL；软删全部活跃 VM 后 → `204`。
- 并发：创建 VM（`FOR SHARE`）与删除宿主（`FOR UPDATE` + 检查）并发，孤立记录不变式 **0 行**。
- **既有 guard 演进**：`test_t22_bare_metal_active_child_checks_explicitly_declared` 现断言 `== ()` 与源码 `"= ()"`，**必然失效** → 演变为「为 tuple 且包含活跃 VM 检查」的正向断言；`test_t22_delete_path_passes_active_child_checks` 保持。

**被拒绝**：把检查硬编码进 `soft_delete`；保持 `BARE_METAL_ACTIVE_CHILD_CHECKS` 为空（fail-open，违反 AC-28）。

### 问题 8 — VM 自身活跃子检查点

**结论**：新增 `app/virtual_machines/deletion.py` 的 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()`（**显式空元组**，承载 F007「活跃 Container」追加位置），并由 `delete_virtual_machine(...)` **显式传入** `soft_delete(..., active_children=VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS)`。

以可失败 guard 固定：`isinstance(..., tuple)`、源码含显式 `= ()`、VM 删除路径源码引用 `soft_delete(` 且传入该常量。

### 问题 9 — 无状态 / 边界的结构性 guard

以**可失败 guard**固定：

| Guard | 断言 |
|---|---|
| VM 无状态 | `virtual_machines` 列不含 `status`；OpenAPI 中 VM 端点无状态过滤参数；VM schema 无 `status` 字段；不存在读写 VM 状态的路径 |
| 无越界资源 | 列不含 `network_interface_id` / `ip_address_id` / `container_id` / `service_id`；F006 未注册这些端点；VM 无独立 NetworkInterface |
| 无 DataCenter / 位置 | 列与 schema 不含 DataCenter / 园区 / 机房 / 机柜 / U 位字段 |
| 无平台接入 | 不存在平台 API 客户端、凭据列（`credential` / `password` / `token` / `api_key`）、外部平台 id（`external_id` / `platform_id`）、同步 / 发现列或端点 |
| 未定义约束不实现 | 无 `<> ''` / 长度 / `trim` / `/` CHECK；schema `name` 与六字段无 `min_length` / `max_length` / `pattern` / `strip_whitespace` / `to_lower` / `to_upper`；空串与首尾空白原样存取 |
| 无 CASCADE / COLLATE / 触发器 | 全库 `confdeltype='c'` 计数 0；列 `collation_name IS NULL`；无触发器 |
| 无 EAV / 通用表 / JSONB / 多态 | 既有 guard 对 `virtual_machines` 继续成立 |

### 问题 10 — 交付层判定

```text
database: true
backend:  true
frontend: true
```

- **database = true**：新增 `virtual_machines` 表 + migration `0004` + schema 文档同步。实现由 Backend 负责。
- **backend = true**：模型 / schema / repository / service / router / F014 接线 / guard 演进 / 全测试集。
- **frontend = true**：VM API 客户端与页面、三态与错误分支。

### 问题 11 — 契约

新建 `docs/api/f006-virtual-machine.md`（`READY`）。要点：5 端点、封闭字段集合、`bare_metal_id` 宿主表示、六个可空字段返回 `null` 不省略、`404 NOT_FOUND`（宿主缺失 / VM 不存在或已删）、`409 CONFLICT`（`DUPLICATE` / `ACTIVE_CHILDREN_EXIST`）、Empty 与 Not Found 可区分、认证自动覆盖。

### 问题 12 — AC 与计划落盘

```yaml
layers: { database: true, backend: true, frontend: true }
contract: { status: READY, doc: docs/api/f006-virtual-machine.md }
implementation: { database_design: PENDING, backend: PENDING, frontend: PENDING, test: PENDING, review: PENDING }
# open_questions: NQ-2 / NQ-4 已由 Architecture 裁定；NQ-1 / NQ-3 / NQ-5 / NQ-7 保持 Non-blocking；NQ-6 由协调器落盘
```

### 问题 13 — 前端接线

见 Frontend Work。三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`（必要时 `details[].code`）分支，不解析 `message`；`409` / `404` / `401` 分别处理；不重复实现业务守卫；不引入新依赖 / vue-router。

---

## Database Work

**Revision**：`0004_f006_virtual_machines`，`down_revision = "0003_f002_bare_metals"`。**不改 `0001` / `0002` / `0003`。**

- `upgrade`：`CREATE TABLE virtual_machines`（12 列 + PK + FK RESTRICT）→ `create_index ux_virtual_machines_name_active`（`unique=True`、`postgresql_where=sa.text("deleted_at IS NULL")`）→ `create_index ix_virtual_machines_bare_metal_id`。
- `downgrade`（逆序）。
- `sa.Identity(always=True)`；时间列 `server_default=sa.text("now()")`；FK `ondelete="RESTRICT" onupdate="RESTRICT"`；无 CASCADE / 触发器 / `COLLATE`。
- 列集合**恰为** 12 列；CHECK 集合为空；FK 恰为 `{fk_virtual_machines_bare_metal}`；索引恰为 `{ux_virtual_machines_name_active, ix_virtual_machines_bare_metal_id}`。

**文档同步**：`docs/database/csm-v1-schema-design.md`（问题 1 的 4 项）；`docs/database/f012-baseline-migration.md` revision 表加 `0004`（建议）。

---

## Backend Work

### 1. ORM 模型（新 `app/models/virtual_machine.py`）
`VirtualMachine(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`，`__tablename__ = "virtual_machines"`。列：`bare_metal_id`（`BigInteger NOT NULL`）、`name`（`Text NOT NULL`）、六个 `Text NULL`。**无 `status`**、**无 `cluster_id`**。`__table_args__` 含 FK RESTRICT、partial unique、宿主索引。注册到 `app/models/__init__.py`。

### 2. schema（`app/virtual_machines/schemas.py`）
- `VirtualMachineRead`：恰 11 字段。
- `VirtualMachineCreate`：`bare_metal_id: int`、`name: str`、六个可选 `str | None`；`extra="forbid"`；**不**给 `name` 添加任何约束。
- `VirtualMachineUpdate`：仅六个可选字段；不含 `name` / `bare_metal_id` / `id` / `deleted_at`；`extra="forbid"`。
- `OPTIONAL_FIELDS = ("cpu", "memory", "disk", "os", "hypervisor", "owner")`。

### 3. repository（`app/virtual_machines/repository.py`）
读取路径**必须**经 `active_filter` / `select_active`。`get_active(id)`、`list_active(params, bare_metal_id=None)`、`active_name_exists(name)`（**全局**、大小写敏感）。`create` / `update` 后 `flush()` + `refresh()`。**不存在**写 `deleted_at` 的方法。

### 4. service（`app/virtual_machines/service.py`）
- `create_virtual_machine`：`_lock_active_host`（`FOR SHARE` + `deleted_at IS NULL`；未命中 → `404`）→ 全局活跃重复预检（`409`）→ 插入。
- `list_virtual_machines`：`bare_metal_id` 给出时先 `select_active(BareMetal)` 确认宿主活跃（未命中 `404`），再返回该宿主活跃子集；未给出时返回全部活跃。
- `get_virtual_machine_by_id`：未命中 → `404`。
- `update_virtual_machine`：加载活跃目标（`404`）；按 `model_fields_set` 应用六个可变字段；空 body → `400`。
- `delete_virtual_machine`：`soft_delete(session, VirtualMachine, id, active_children=VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS)`。

### 5. router（`app/virtual_machines/router.py`，`prefix="/virtual-machines"`）
5 端点（`POST ""`、`GET ""`、`GET "/{virtual_machine_id}"`、`PATCH "/{virtual_machine_id}"`、`DELETE "/{virtual_machine_id}"`）；`GET ""` 可选 `bare_metal_id`。在 `app/main.py` 以 `prefix="/api"` 挂载；无 `by-name`；无 restore / 批量 / `include_deleted`。

### 6. F014 / F007 接线（**必须**）
新 `app/virtual_machines/deletion.py`：`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS = ()`（显式空元组；F007 追加位置）；`has_active_virtual_machines(session, bare_metal_id) -> bool`。**改** `app/bare_metals/deletion.py`：`BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines,)`（**显式声明**，不 fail-open）。

### 7. Guard 演进（**必须，不得删除后不补**）
- `tests/database/helpers.py::MIGRATION_HEAD` → `"0004_f006_virtual_machines"`。
- `tests/database/test_schema.py::EXPECTED_TABLES` → 加 `virtual_machines`。
- `tests/database/test_migrations.py` 表集合与 head 断言 → 加 `virtual_machines` / `0004`。
- `tests/test_structure_guard.py::test_only_expected_tables_registered` → 加 `virtual_machines`。
- `tests/test_auth_guards.py::EXPECTED_GET_ROUTES` → 追加 `/api/virtual-machines`、`/api/virtual-machines/{virtual_machine_id}`。
- `tests/test_bare_metals_guards.py::test_t22_bare_metal_active_child_checks_explicitly_declared` → 由 `== ()` 演进为「tuple 且含活跃 VM 检查」。
- 新增 VM 结构 guard（问题 9 的表）。
- `test_deletion_guards` allow-list、无 CASCADE、`clusters` 结构 guard → **原样保留**。

---

## Frontend Work

（复用 `api/http.ts`；**不引入新依赖 / 不引入 vue-router**。）

1. **`src/api/virtualMachines.ts`**：`VirtualMachineRead`（字段封闭，六字段 `string | null`；**无 `status` / `cluster_id`**）；`listVirtualMachines({page?, page_size?, bareMetalId?})`、`getVirtualMachine`、`createVirtualMachine`、`updateVirtualMachine`、`deleteVirtualMachine`。
2. **`pages/VirtualMachineListPage.vue`**：列表 + 可选 `bare_metal_id` 过滤；三态互不相同；Empty（`200` 空集）与 Not Found（宿主 404）可区分；错误按 `error.code`；每行详情 / 删除入口 + 二次确认；登记表单入口；提交中 Loading 防重复。
3. **`pages/VirtualMachineDetailPage.vue`**：详情；`404` → 独立 Not Found 态；六字段 `null` 渲染「—」；可选字段修改（`PATCH`）与删除入口；`name` / `bare_metal_id` 不可编辑；**无状态展示 / 编辑**。
4. **`components/VirtualMachineFormDialog.vue`**：create = 宿主裸金属选择（既有 `GET /api/bare-metals`）+ `name` + 六字段；edit = 仅六字段；**不对 `name` 做长度 / 空串 / 字符校验**；失败按 `error.code` 分支。
5. **`composables/useVirtualMachineDelete.ts`**：复用 `useResourceDelete`；不假定「VM 永远无子资源」。
6. **`App.vue`**：增加 VM 列表 / 详情视图与切换；提供从 BareMetal 详情进入「该宿主 VM」的入口（携带 `bare_metal_id`）。
7. **禁止重复实现业务守卫**（§21）：全局 `name` 唯一、宿主存在性 / 活跃性、删除守卫一律由后端裁决。
8. **不做**：NIC / IP / Container / Service UI、平台同步 UI、审计 / 恢复 / 回收站 / 批量 / 筛选 / 导出、VM 状态 UI。

---

## Contract

**Status**：`READY`。唯一权威正文：`docs/api/f006-virtual-machine.md`。

---

## Test Work

### API + DB 行为

| # | 测试 | 层次 | AC |
|---|---|---|---|
| **T-01** | `POST`（活跃宿主 + 唯一 name）→ `201`，字段集合恰为 11 字段；无 `deleted_at` / `status` / `cluster_id` / NIC / 位置 / 平台字段 | API | AC-01 |
| **T-02** | `POST` 缺 `name` / 非字符串 → `400` `field=="name"`，无写入 | API + DB | AC-02 |
| **T-03** | `POST` 缺 / 非整数 `bare_metal_id` → `400` `field=="bare_metal_id"`；引用不存在 / 已软删宿主 → `404 NOT_FOUND`，无写入、非 5xx | API + DB | AC-03 / AC-04 |
| **T-04** | `POST` 多宿主 / 以 VM / Container 作宿主 / 载体类型选择器 → `400`（schema 封闭） | API | AC-05 |
| **T-05** | 不提供任何可选字段 → `201`，六字段响应为 `null`（返回 `null` 而非省略） | API | AC-06 |
| **T-06** | 中文 `name` 与 `"8 vCPU"` 等原样往返 | API + DB | AC-07 |
| **T-07** | 空串 / 含首尾空白 `name` **不被拒绝**（不实现未定义约束） | API | AC-08 |
| **T-08** | 宿主 A 已有活跃 `vm1`，宿主 B / 另一 Cluster 登记 `vm1` → `409` `field=="name"` `code=="DUPLICATE"` | API + DB | AC-09 / AC-10 |
| **T-09** | `vm1` 与 `VM1` 并存为两条；无 `lower(name)` 唯一索引 | API + DB | AC-11 |
| **T-10** | 直连库插入重复活跃 `name` → `23505`；经应用调用 → `409` | DB + API | AC-12 |
| **T-11** | 软删 `vm1` 后可在**任意**宿主重新登记 → `201`；旧行 `deleted_at` 未被改写 | API + DB | AC-13 |
| **T-12** | `GET` 无活跃 → `200` + 空信封，非 404；分页正确 | API | AC-14 |
| **T-13** | `GET /{id}` 不存在 / 已软删 → `404`（不区分） | API | AC-15 |
| **T-14** | 绕过应用层预置 `deleted_at` → 不出现在 items / total；按 id → `404` | API + DB | AC-16 |
| **T-15** | 读回以 `bare_metal_id` 观察宿主；无 `cluster_id` / `cluster_name` | API + Schema | AC-17 |
| **T-16** | 请求体 / 响应体 / 表 / 端点 / 参数**无** `status` | API + Schema | AC-18 |
| **T-17** | `PATCH` 合法字段 → `200` 新值；`null` 清空；缺省不变 | API + DB | AC-19 |
| **T-18** | `PATCH` 含未识别 / 不可变字段 → `400`；空 body → `400` | API | AC-20 |
| **T-19** | `DELETE`（活跃）→ `204` 无响应体；行仍物理存在、`deleted_at` 非空 | API + DB | AC-21 |
| **T-20** | 删除 VM 后宿主 `deleted_at` / `updated_at` / 字段不变 | API + DB | AC-22 |
| **T-21** | 无 restore / undelete / purge / 批量 / `include_deleted` | API | AC-23 |
| **T-22** | 宿主有活跃 VM → `DELETE /api/bare-metals/{id}` → `409` + `code=="ACTIVE_CHILDREN_EXIST"`；宿主 `deleted_at` 仍 NULL | API + DB | AC-24 |
| **T-23** | 软删全部活跃 VM 后 → `DELETE` 宿主 `204` | API + DB | AC-25 |
| **T-24** | 并发「创建 VM vs 删除宿主」后孤立记录 = **0 行** | 并发（DB） | AC-26 |
| **T-25** | 创建 VM 对宿主取 `FOR SHARE`；未命中 → 拒绝创建 | 并发（DB） | AC-27 |
| **T-26** | `BARE_METAL_ACTIVE_CHILD_CHECKS` 非空且含活跃 VM 检查，并被宿主删除路径真实消费 | 静态 + API | AC-28 |
| **T-27** | `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 显式声明（当前空），且 VM 删除路径真实传入 | 静态 + API | AC-29 |
| **T-28** | 无平台 API 客户端 / 凭据 / 外部平台 id / 同步字段或端点 | API + Schema | AC-30 |
| **T-29** | 不注册 NIC / IP / Container / Service 端点；表无这些结构，也无位置字段 | API + Schema | AC-31 |
| **T-30** | 按宿主读取：宿主不存在 / 已删 → `404`；存在但无活跃 VM → `200` + `items==[]`；只返回该宿主子集 | API + DB | 决策 3 |
| **T-FE-01** | 三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`；`409`/`404`/`401` 分别处理；不重复实现守卫 | 前端组件 | AC-32 |

### 结构 / 静态 guard

| # | guard | 关联 |
|---|---|---|
| **G-1** | 列集合恰为 12 列；无 `status` / `cluster_id`；CHECK 集合为空；FK 恰为 `fk_virtual_machines_bare_metal` 且 `confdeltype='r'` / `confupdtype='r'` | AC-01/05/18 |
| **G-2** | `ux_virtual_machines_name_active` 存在、`UNIQUE`、`indexdef` 含 `WHERE (deleted_at IS NULL)`；`ix_virtual_machines_bare_metal_id` 存在 | R-VM-004 |
| **G-3** | 表集合 guard 演进（`virtual_machines` / `0004`），**增表演进不得删测试** | 约束 |
| **G-4** | `EXPECTED_GET_ROUTES` 追加 VM 两条 GET 路由（只增不删） | 约束 |
| **G-5** | `BARE_METAL_ACTIVE_CHILD_CHECKS` guard 由 `== ()` 演进为「含 `has_active_virtual_machines`」 | AC-28 |
| **G-6** | `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 显式声明且 VM 删除路径引用 `soft_delete(` + 传入 | AC-29 |
| **G-7** | 未定义约束「不实现」：无 `<> ''` / 长度 / `trim` / `/` CHECK；schema 无 `min_length` / `pattern` / `strip`；空串 / 首尾空白原样存取 | AC-08 |
| **G-8** | 无 CASCADE；列 `collation_name IS NULL`；无触发器 | R-DELETE-005 |
| **G-9** | 唯一软删写入路径 allow-list 保持 `{backend/app/deletion/service.py}` | AC-21/23 |
| **G-10** | 无通用 `resources` 表 / EAV / STI / 多态 / JSON(B) | §24 |
| **G-11** | `MIGRATION_HEAD` 与 `alembic current` = `0004_f006_virtual_machines`；可应用 / 可重复 / 可从空库重建 | 约束 |

### 必须同步演进的既有测试

`tests/database/{helpers,test_schema,test_migrations}`、`tests/test_structure_guard.py`、`tests/test_auth_guards.py`、`tests/test_bare_metals_guards.py`（T-22 相关）。`tests/test_deletion_guards.py`、`tests/database/test_deletion_schema_guard.py`、`clusters` 结构 guard → **原样保留**。

---

## REQUIRED

1. `virtual_machines` 唯一性由 **partial unique index** 强制（predicate `deleted_at IS NULL`）；大小写敏感，**禁止 `lower()` / `COLLATE`**。
2. `bare_metal_id NOT NULL` + FK `ON DELETE RESTRICT ON UPDATE RESTRICT`；**禁止 CASCADE**。
3. 创建**必须在同一事务内**对宿主 BareMetal 取 `FOR SHARE` 并确认活跃；未命中即 `404`。
4. `deleted_at` 写入路径**恰好 1 条**；VM 删除必须委托 `soft_delete()`。
5. 宿主删除路径的活跃子资源检查**必须包含**活跃 VM 检查；`BARE_METAL_ACTIVE_CHILD_CHECKS` **非空**。
6. `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` **显式声明**且被 VM 删除路径**真实传入**。
7. `name` 与六个可选字段**不得**有隐式长度 / trim / 字符 / `/` 约束。
8. 请求 / 响应 schema **封闭**（`extra="forbid"`）；`PATCH` 不含 `name` / `bare_metal_id` / `id` / `deleted_at`。
9. 不新增任何 CASCADE / 触发器 / `COLLATE`；不改 `0001` / `0002` / `0003`。
10. 既有 guard **必须演进而非删除**。
11. 失败不得依赖前端；守卫由后端裁决（§21）。
12. 所有端点位于 `/api` 前缀下，由 F013 自动覆盖，**不新增白名单**。
13. 错误信封 / 状态码 / SQLSTATE 映射**复用**既有机制。

---

## Constraints

1. 不得修改或新增 `clusters` / `users` / `sessions` / `bare_metals` 的列与约束；不得改 `0001` / `0002` / `0003`；只新增 `0004`。
2. 不得新增 `status` 列 / 状态枚举 / 状态端点 / 状态过滤；不得新增 `cluster_id` 列或任何 Cluster 维度字段。
3. 不得实现第二条 `deleted_at` 写入路径；不得实现 restore / undelete / purge / 批量删除。
4. 不得偏离 `api-conventions.md` 的信封、状态码与 Empty / Not Found 语义。
5. 不得在前端重复实现业务守卫（§21）。
6. 不得引入新框架 / 新中间件 / 新依赖 / vue-router；不得引入 EAV / 通用表 / STI / 多态 / JSONB。
7. 不得新增 CASCADE / 触发器 / `COLLATE`。
8. 不得注册 NIC / IP / Container / Service 端点；表不得含这些实体结构或位置字段。
9. 不得引入虚拟化平台 API 客户端 / 凭据 / 外部平台 id / 同步字段或端点。
10. 不得修改既有契约正文；F006 契约唯一正文在 `docs/api/f006-virtual-machine.md`。
11. 不得为 VM 提供全局 `by-name` 别名；不得实现 `name` / 宿主绑定可变。

---

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 既有 `test_t22_..._explicitly_declared`（断言空元组）在 F006 后失效，若处理不当会「删测试」 | REQUIRED #10；G-5 |
| R2 | 新增表后表集合 / 路由 guard 被删除而非演进 | REQUIRED #10；G-3 / G-4 |
| R3 | 未定义约束被「顺手」加上（`name <> ''` / 长度 / `/` 禁令 / `lower()`） | G-2 / G-7 |
| R4 | 唯一性 / FK / 约束冲突返回 500 | 应用层预检 + 既有 SQLSTATE 映射 |
| R5 | F014 / F007 交接的并发端到端被简化或 fail-open | AC-24~29 与 T-22~27；G-5 / G-6 |
| R6 | NQ-4 裁定与 F010 预期不一致，产生重复实现 | 契约固定并标注 F010 必须复用；T-30 |
| R7 | partial index predicate 与查询过滤错位 | 读取统一经 `active_filter` / `select_active`；G-2 |
| R8 | 文档漂移（schema-design）导致 Database 与 Handoff 不一致 | Database Work 明确同步 4 项；协调器落盘 |
| R9 | 前端误把组织守卫做成前端校验 | REQUIRED #11；T-FE-01 |

---

## Open Questions

### Blocking

**无。** NQ-2 / NQ-4 已在决策 4 / 决策 3 裁定。

### Non-blocking

1. **NQ-1**（`name` / 宿主绑定可变性）：F006 **不实现、不承诺**。
2. **NQ-3**（VM 全局 `by-name` 别名）：F006 **不实现**。
3. **NQ-5**（`name` 与可选字段最小字符约束）：F006 **不实现、不承诺**。
4. **NQ-7**（读路径是否附加推导出的 Cluster）：F006 **不返回** Cluster 字段。
5. **NQ-6**（文档与计划元数据同步）：由协调器落盘。
6. `23503` 经通用映射返回 `409 CONFLICT`（`REFERENCE`）而非 `404`；该路径在产品路径下不可达。
7. F014 Review 遗留：G-3 静态扫描器 AST 化——非本 Feature AC 要求。

---

## Implementation Layers

```text
database: true
backend:  true
frontend: true
```

**文件所有权**：Backend = `backend/**` + `tests/**`；Frontend = `frontend/**`；共享 `docs/**` 由协调器统一落盘。

---

## Verification Strategy

1. **契约层**：字段集合封闭、必填校验、宿主存在性 / 活跃性、列表 Empty 与详情 Not Found、按宿主 Empty vs Not Found、负向路由。
2. **唯一性**：跨宿主 / 跨 Cluster 重复 `409`、大小写敏感、软删释放、DB 直插断言。
3. **关系写入与并发**：schema 封闭、`FOR SHARE` 锁序、孤立记录不变式 0 行。
4. **无状态与边界**：无 `status`、无平台接入、无越界实体 / 位置结构。
5. **维护与删除**：PATCH 部分更新与封闭性、软删、不级联、无恢复 / 批量。
6. **F014 / F007 端到端**：宿主有活跃 VM → `409` 无部分写入；软删后可删；检查点声明与消费。
7. **未定义约束「不实现」**。
8. **数据层结构（G-1~G-11）**。
9. **前端（AC-32）**。
10. **工程门禁**：lint 通过；既有测试全绿；所有 guard 完成演进而非删除。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：Product Handoff 为 `READY FOR ARCHITECT` 且无 Blocking；`database: true`；API Contract = `READY`；Backend / Frontend 两分支均有可直接开工的依据。全部 13 个待决技术问题已逐条裁定。**需用户确认的长期技术决策：无。**

GIT: NONE
