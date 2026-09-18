# Architecture Handoff — F004 NetworkInterface 管理

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Feature: F004（E02，P1，`depends_on: [F002]` = DONE）
> 配套契约：`docs/api/f004-network-interface.md`（`READY`）
> Product Source: `docs/product/handoffs/f004-network-interface.md`（`READY FOR ARCHITECT`，无 Blocking，AC-01 ~ AC-34，NQ-1 ~ NQ-12）

---

## Feature

NetworkInterface 管理（F004）— CSM V1 网络资源的第一个资源：网络接口的登记、查询、技术类型与用途维护、逻辑删除，以及 **NetworkInterface → BareMetal 必选绑定** 的真实落地与 F014 父删子拦端到端。

## Status

`READY FOR IMPLEMENTATION`（无 Blocking；API Contract = `READY`）。

## Context — 现状核实（只读检查结论）

| 项 | 现状 |
|---|---|
| Backend | 应用工厂 `app/main.py`（`/api` → health + clusters + cluster_views + bare_metals + virtual_machines + auth）；F013 认证中间件自动覆盖；统一错误信封；SQLSTATE 映射（23502/23514→400、23505/23503→409）；分页默认 50 / 上限 200；请求级事务边界；活跃过滤原语 `db/active.py` |
| 统一软删服务 | `backend/app/deletion/service.py`（系统内唯一写 `deleted_at` 的路径）+ `deletion/checks.ActiveChildCheck` |
| F014 接线现状 | `BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines,)`；`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS = ()`。**NetworkInterface 模块不存在** |
| Database | head = `0004_f006_virtual_machines`；`EXPECTED_TABLES` 含 `bare_metals` / `virtual_machines`。**`network_interfaces` 不存在** |
| Frontend | `api/http.ts`、`api/virtualMachines.ts`、`ListStates.vue` / `ErrorState.vue`、`useResourceDelete.ts`、VM 页面、`App.vue` 视图切换（无 vue-router）。**无 NIC UI** |
| 须演进 guard | `tests/database/{helpers,test_schema,test_migrations}`；`test_structure_guard`；`test_auth_guards.EXPECTED_GET_ROUTES`；`test_bare_metals_guards`（检查点断言）；**`test_cluster_views_guards.BOUNDARY_TOKENS`（当前把 `network-interface` 列为越界 token，必然失效）** |

**结论**：增量交付，需新增一张表 + 一次增量 migration；其余机制全部复用既有基座。

---

## Architecture Summary

- 新增模块 `backend/app/network_interfaces/`（model + schema + validation + repository + service + router + deletion）。
- 新增 `app/models/network_interface.py`，注册到 `app/models/__init__.py`，在 `app/main.py` 挂载。
- **改** `app/bare_metals/deletion.py`：`BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines, has_active_network_interfaces)`（**追加，保留 VM 检查**）。
- 新增 migration `0005_f004_network_interfaces`（`down_revision = "0004_f006_virtual_machines"`；**不改 `0001`–`0004`**）。
- 新增前端 NIC API 客户端与页面。
- 演进既有 guard（表集合 / GET 路由 / BOUNDARY_TOKENS / BareMetal 检查点），新增 NIC guard；**不删测试**。

**要点**：一次 `CREATE TABLE` 建齐 8 列 + 两个封闭枚举 CHECK + 父 FK；父限定读取 `?bare_metal_id=`；应用层枚举 `400` + DB CHECK 最终权威；NIC 自身检查点显式空元组；无状态 / 无 IP / 无未确认硬件字段 / 无载体多态 / **无名称唯一性**。

---

## Domain Impact

**使用**已有领域对象 `BareMetal`（N:1 父）。**新增领域对象：无**。NetworkInterface 实体、其字段、封闭枚举与 NIC→BareMetal 关系均已由 CONFIRMED 产品文档确定，本 Feature 只落表 / 模型 / API。

- 状态：**无**（Q-002=B）。唯一性：**无**（NQ-2 未确认，不得建唯一约束与应用层预检）。生命周期：软删 / 不级联 / 父有活跃 NIC 不得删。
- **不裁定** NQ-1（VM 是否拥有独立 NIC），不为多态载体预留任何字段 / 参数 / 分支。

---

## Decisions

### 决策 1 — Schema 与增量 migration

新建 `0005_f004_network_interfaces`，`down_revision = "0004_f006_virtual_machines"`。一条 `CREATE TABLE`：

```sql
CREATE TABLE network_interfaces (
  id              BIGINT GENERATED ALWAYS AS IDENTITY,
  bare_metal_id   BIGINT      NOT NULL,   -- R-NIC-003 父（必选，恰好一个）
  name            TEXT        NOT NULL,   -- 无长度 / trim / 字符约束
  technology_type TEXT        NOT NULL,   -- R-NIC-001 封闭四值
  purpose         TEXT        NOT NULL,   -- R-NIC-002 封闭七值
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ NULL,
  CONSTRAINT pk_network_interfaces PRIMARY KEY (id),
  CONSTRAINT fk_network_interfaces_bare_metal FOREIGN KEY (bare_metal_id)
    REFERENCES bare_metals (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_network_interfaces_technology_type
    CHECK (technology_type IN ('Ethernet', 'InfiniBand', 'RoCE', 'Other')),
  CONSTRAINT ck_network_interfaces_purpose
    CHECK (purpose IN ('BMC', 'Management', 'Business', 'Compute',
                       'Storage', 'DataTransfer', 'Other'))
);

CREATE INDEX ix_network_interfaces_bare_metal_id
  ON network_interfaces (bare_metal_id);
```

`downgrade`（逆序）：`drop_index` → `drop_table`。破坏性，生产禁止。

**REQUIRED 规格**：父列 `bare_metal_id`；FK RESTRICT/RESTRICT（禁止 CASCADE）；`name NOT NULL`（**不得**加长度 / trim / 字符 / `/` 约束）；两个枚举列 `NOT NULL` + CHECK 且取值**恰为** R-NIC-001/002 集合；**无 `status` 列**；**无** IP / MAC / 速率 / MTU / 光模块 / 端口 / `vm_id` / `container_id` / `cluster_id` / 载体选择器列；**明确不添加** `UNIQUE (bare_metal_id, name)`（不得以任何形式表达 NIC 名称唯一性）；唯一索引集合为**空**；索引恰为 `{ix_network_interfaces_bare_metal_id}`；`sa.Identity(always=True)`；时间列 `server_default=now()`；不改 `0001`–`0004`；无数据迁移。

**文档同步**：`docs/database/csm-v1-schema-design.md` NIC 段补 migration 版本 `0005_f004_network_interfaces`；`docs/database/f012-baseline-migration.md` §3/§4 的 NIC 条目由 `0004_f004_network_interfaces` 改号为 `0005_f004_network_interfaces` 并置于 `0004_f006_virtual_machines` 之后（文档因 F006 占用 `0004` 而漂移），F005 顺延；新建 `docs/database/f004-network-interface-migration.md`（镜像 F006 格式）。

**被拒绝**：加 `status`；加 IP / MAC / 速率 / MTU；加载体列；建名称唯一约束；`name` 加 CHECK；CASCADE / 触发器 / `COLLATE`。

### 决策 2 — 端点集合与资源表示封闭性

5 个端点，路径 `/api/network-interfaces`：`POST`（201）、`GET`（200，可选 `bare_metal_id`）、`GET /{network_interface_id}`（200）、`PATCH /{network_interface_id}`（200）、`DELETE /{network_interface_id}`（204）。

资源表示字段集合**封闭**为恰 7 字段 `{id, bare_metal_id, name, technology_type, purpose, created_at, updated_at}`。请求 schema 封闭（`extra="forbid"`）。不提供 `by-name` / restore / 批量 / `include_deleted`。契约唯一权威：`docs/api/f004-network-interface.md`。

### 决策 3 — NQ-6：按父限定读取的路由形态与归属

**结论**：F004 提供 `GET /api/network-interfaces?bare_metal_id={id}` 作为 canonical 父限定读取能力（集合端点的可选 query parameter，**不新增端点**）；R-QUERY-003 的关联查询视图仍归 F010，F010 必须复用。

语义：`bare_metal_id` 非整数 → `400`；宿主不存在或已逻辑删除 → **`404 NOT_FOUND`**；宿主存在但无活跃 NIC → **`200` + `items == []`**；未提供 → 全部活跃 NIC（`200`）。

**理由**：与 F002 `?cluster_id=`、F006 `?bare_metal_id=` 完全对称（项目内已两次确立该模式）；不新增端点 / 领域字段；使 Empty-vs-NotFound 判定落在唯一一处，避免 F010 重复实现而漂移。

**被拒绝**：嵌套路径（跨模块注册、与先例不对称）；完全归 F010（重复实现过滤与 R-QUERY-004）；仅无过滤列表（违反 AC-16）。

### 决策 4 — NQ-5：引用不存在 / 已软删父的响应码

**结论**：`POST` 与 `?bare_metal_id=` 在父 BareMetal 不存在 / 已逻辑删除时返回 **`404 NOT_FOUND`**（`details == []`），**不产生写入、永不为 5xx**。与 F002 / F006 裁定一致；字段格式错误保留 `400`，存在性 / 活跃性失败归 `404`。

### 决策 5 — 创建路径并发协议与 FK 映射

- 创建在同一请求事务内 `SELECT … WHERE id = :bare_metal_id AND deleted_at IS NULL FOR SHARE`（实现经 `select_active(BareMetal).with_for_update(read=True)`）；未命中 → `404`。**锁序与 F002 / F006 / F014 对齐**。
- 交错：宿主删先持 `FOR UPDATE` ⇒ NIC 建阻塞、提交后未命中 → 拒绝；NIC 建先持 `FOR SHARE` ⇒ 宿主删阻塞、提交后活跃子检查命中 → `409`。两种交错都不产生「宿主已删 + NIC 活跃」。
- FK 违规：正常路径由预检给出 `404`，应用路径不触发 `23503`；若绕过预检，经既有通用映射返回 `409 CONFLICT` + `details[].code = "REFERENCE"`，非 5xx，**不为 NIC 另立映射**；该路径不可达。

### 决策 6 — 封闭枚举落地与最终权威

- 应用层**唯一一份**领域校验（`app/network_interfaces/validation.py`）：`TECHNOLOGY_TYPE_VALUES` / `PURPOSE_VALUES`（`frozenset`）；非法值 → `400 VALIDATION_ERROR` + `details[].field` + `details[].code = "INVALID"`。创建与更新**共用同一实现**（F011 导入复用）。
- 字面精确匹配：**不做**大小写折叠、`trim`、NFC 归一、中文映射。
- **DB `CHECK` 为最终权威**；绕过应用层直写非法值 `23514` → 既有通用映射返回 `400`（**永不 500**）。
- 以可失败 guard 固定两个枚举集合恰为上述值，且所有 schema 与表**不存在**伴随自由文本字段（`other_text` / `description` / `note` / `remark`）。

**被拒绝**：PostgreSQL `ENUM` 类型（ADR-0002 已裁定 `TEXT + CHECK`）；中文文案进后端枚举；`Other` 伴随自由文本。

### 决策 7 — F014 端到端义务落点

- 新增 `app/network_interfaces/deletion.py`：`has_active_network_interfaces(session, bare_metal_id) -> bool`（`EXISTS` 活跃 NIC，复用 `active_filter`）。
- **改** `app/bare_metals/deletion.py`：追加 `has_active_network_interfaces`，**保留** `has_active_virtual_machines`。
- `delete_bare_metal` 已传入 `active_children=BARE_METAL_ACTIVE_CHILD_CHECKS`，**无需改删除路径逻辑**。
- 端到端：宿主有活跃 NIC → `409` + `details[].code == "ACTIVE_CHILDREN_EXIST"`、宿主 `deleted_at` 仍 NULL；软删全部活跃子资源后 → `204`；并发孤立记录不变式 **0 行**。
- 无循环导入：`app.bare_metals.deletion → app.network_interfaces.deletion → app.models.network_interface`。

**既有 guard 演进**：`test_t22_bare_metal_active_child_checks_explicitly_declared` 保持 VM 断言并**追加** NIC 断言。

**被拒绝**：把检查硬编码进 `soft_delete`；以新元组**替换**（丢弃 VM 检查，违反 AC-29）。

### 决策 8 — NIC 自身活跃子检查声明位置

新增 `app/network_interfaces/deletion.py`：

```python
NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()
```

（**显式空元组**，代表「`ip_addresses` 表尚不存在」而非「NIC 无子资源」），并由 `delete_network_interface(...)` **显式传入** `soft_delete(..., active_children=NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS)`。F005 在该元组追加「活跃 IPAddress」检查并补端到端。

以可失败 guard 固定：`isinstance(..., tuple)`、源码含显式 `= ()`、NIC 删除路径经 **AST 扫描**确认真实传入 `active_children=<该常量>`。

### 决策 9 — 无状态 / 边界 / 未确认项「不预留」的结构性 guard

以可失败 guard（`tests/test_network_interfaces_guards.py`）固定：

| Guard | 断言 |
|---|---|
| NIC 无状态 | 列不含 `status`；OpenAPI 中 NIC 端点无状态过滤参数；NIC schema 无 `status`；不存在读写 NIC 状态的路径 |
| 无 IP 语义 | 表 / schema / 请求 / 响应无 `ip` / `ip_address` / `ipv4` / `ipv6` / `prefix_len`；未注册 IP 端点；无 `ip_addresses` 表；表无 `cluster_id` 列 |
| 无未确认硬件字段 | 无 `mac` / `mac_address` / `speed` / `rate` / `mtu` / `port` / `module` / `transceiver` / `discovered` / `external_id` / `last_seen` |
| 无载体多态 | 无 `vm_id` / `virtual_machine_id` / `container_id` / `service_id` / `cluster_id` / `carrier_type` / `owner_type`；`NetworkInterfaceCreate` 字段集合**恰为** `{bare_metal_id, name, technology_type, purpose}` |
| 无 NIC 名称唯一性 | 无任何 `UNIQUE` 索引、无 `ux_` 前缀索引；repository / service 源码不含 `active_name_exists` / `name_exists` 类唯一性预检 |
| 未定义约束不实现 | 无 `<> ''` / 长度 / `trim` / `like` / `strpos` / `/` CHECK；schema `name` 无 `min_length` / `max_length` / `pattern` / `strip_whitespace` / `to_lower` / `to_upper`；空串与首尾空白原样存取 |
| 无 CASCADE / COLLATE / 触发器 | 全库 `confdeltype='c'` 计数 0；列 `collation_name IS NULL`；无触发器 |
| 无 EAV / 通用表 / JSONB / 多态 | 既有 guard 对 `network_interfaces` 继续成立 |
| 交付面封闭 | NIC 路由恰为 5 个端点；无 `by-name`；无 restore / 批量 |

### 决策 10 — 交付层

```text
database: true
backend:  true
frontend: true
```

### 决策 11 — 契约

新建 `docs/api/f004-network-interface.md`（`READY`）。不修改任何既有契约正文。

### 决策 12 — 计划落盘

```yaml
layers: { database: true, backend: true, frontend: true }
contract: { status: READY, doc: docs/api/f004-network-interface.md }
implementation: { database_design: PENDING, backend: PENDING, frontend: PENDING, test: PENDING, review: PENDING }
# NQ-5 / NQ-6 已由 Architecture 裁定；NQ-1 / NQ-2 / NQ-3 / NQ-4 / NQ-7 / NQ-8 保持 Non-blocking（不实现 / 不预留）；NQ-9 为 F005 义务
```

### 决策 13 — 前端接线

见 Frontend Work。三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`；`409` / `404` / `401` 分别处理；不重复实现业务守卫；不引入新依赖 / vue-router。

---

## Database Work

**Revision**：`0005_f004_network_interfaces`，`down_revision = "0004_f006_virtual_machines"`。**不改 `0001`–`0004`。**

- `upgrade`：`CREATE TABLE`（8 列 + PK + FK RESTRICT + 两个 CHECK）→ `create_index ix_network_interfaces_bare_metal_id`。
- `downgrade`（逆序）。
- 列集合**恰为 8 列**；CHECK 集合**恰为** `{ck_network_interfaces_technology_type, ck_network_interfaces_purpose}`；FK 恰为 `{fk_network_interfaces_bare_metal}`；索引恰为 `{ix_network_interfaces_bare_metal_id}`；**唯一索引集合为空**。
- **不做**：唯一性约束；状态列；IP / MAC / 速率 / MTU 列；载体多态列；触发器；`COLLATE`；数据迁移。

**文档同步**：`docs/database/csm-v1-schema-design.md`（NIC 段补版本号）；`docs/database/f012-baseline-migration.md`（§3/§4 改号与排序）；新建 `docs/database/f004-network-interface-migration.md`。

---

## Backend Work

1. **ORM 模型** `app/models/network_interface.py`：`NetworkInterface(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`，`__tablename__ = "network_interfaces"`；列 `bare_metal_id` / `name` / `technology_type` / `purpose`；**无 `status`**、**无 IP / MAC / 速率 / MTU**、**无载体列**；`__table_args__` 含 FK RESTRICT、两个 `CheckConstraint`、`Index("ix_network_interfaces_bare_metal_id", ...)`；**无任何 `unique=True` 索引**。注册到 `app/models/__init__.py`。
2. **schema** `app/network_interfaces/schemas.py`：`NetworkInterfaceRead` 恰 7 字段；`NetworkInterfaceCreate` 恰 4 字段（`extra="forbid"`，**不给任何字段加约束**）；`NetworkInterfaceUpdate` 仅 `technology_type` / `purpose`（`extra="forbid"`）；`MUTABLE_FIELDS = ("technology_type", "purpose")`。
3. **校验** `app/network_interfaces/validation.py`：`TECHNOLOGY_TYPE_VALUES` / `PURPOSE_VALUES`（`frozenset`）；`validate_technology_type` / `validate_purpose` → 非法值 `ValidationError`（400）+ `details[].field` + `code="INVALID"`；创建 / 更新共用；**不实现任何 `name` 校验**。
4. **repository**：读取必经 `active_filter` / `select_active`；`get_active` / `list_active(params, bare_metal_id=None)`；`create` / `update` 后 `flush` + `refresh`；**不写 `deleted_at`**；**无任何名称唯一性查询方法**。
5. **service**：`create_network_interface`（父 `FOR SHARE` 活跃确认 → 未命中 `404` → 校验两个枚举 → 插入；**无唯一性预检**）；`list_network_interfaces`（带 `bare_metal_id` 先确认父活跃，未命中 `404`）；`get_*_by_id`；`update_*`（按 `model_fields_set` 应用并逐个校验枚举；空 body → `400`）；`delete_*`（委托 `soft_delete(..., active_children=NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS)`）。
6. **router** `prefix="/network-interfaces"`：5 端点；`GET ""` 可选 `bare_metal_id`；在 `app/main.py` 以 `prefix="/api"` 挂载；无 `by-name` / restore / 批量 / `include_deleted`。
7. **接线**：新 `app/network_interfaces/deletion.py`（`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS = ()` + `has_active_network_interfaces`）；**改** `app/bare_metals/deletion.py`（追加，保留 VM 检查）。
8. **Guard 演进（不得删除后不补）**：
   - `tests/database/helpers.py::MIGRATION_HEAD` → `"0005_f004_network_interfaces"`。
   - `tests/database/test_schema.py::EXPECTED_TABLES` → 加 `network_interfaces`。
   - `tests/database/test_migrations.py` → head / 表集合 / 可重建加 `network_interfaces` / `0005`；新增 downgrade 到 `0004_f006_virtual_machines` 的断言。
   - `tests/test_structure_guard.py::test_only_expected_tables_registered` → 加 `network_interfaces`。
   - `tests/test_auth_guards.py::EXPECTED_GET_ROUTES` → 追加 NIC 两条 GET（只增不删）。
   - **`tests/test_cluster_views_guards.py::BOUNDARY_TOKENS`** → 移除 `network-interface` / `network_interface`（F004 已成为合法资源，与 F006 移除 `virtual-machine` 同一处置）；**保留** `ip-address` / `ip_address` / `container` / `service`；**保持全局扫描**。
   - `tests/test_bare_metals_guards.py::test_t22_...` → 追加「含 `has_active_network_interfaces`」断言。
   - 新增 `tests/test_network_interfaces_guards.py`（决策 9 + G-1 ~ G-14）。
   - `tests/test_deletion_guards.py` allow-list、无 CASCADE、`clusters` / `virtual_machines` 结构 guard → **原样保留**。

---

## Frontend Work

1. **`src/api/networkInterfaces.ts`**：`NetworkInterfaceRead`（恰 7 字段）；`TECHNOLOGY_TYPE_OPTIONS` / `PURPOSE_OPTIONS`（**仅用于下拉渲染**，不作为业务校验依据）；`listNetworkInterfaces({page?, page_size?, bareMetalId?})`、`getNetworkInterface`、`createNetworkInterface`、`updateNetworkInterface`、`deleteNetworkInterface`。
2. **`pages/NetworkInterfaceListPage.vue`**：列表 + 可选 `bare_metal_id` 过滤；三态互不相同；Empty 与 Not Found（宿主 `404`）可区分；错误按 `error.code`；行级详情 / 删除（二次确认）；登记入口；提交中 Loading 防重复；**无状态列 / 状态筛选**。
3. **`pages/NetworkInterfaceDetailPage.vue`**：详情（7 字段，时间不透明字符串）；`404` → 独立 Not Found 态；枚举修改（`PATCH`）；`name` / `bare_metal_id` **不可编辑**；删除入口。
4. **`components/NetworkInterfaceFormDialog.vue`**：create = 宿主选择（复用 `GET /api/bare-metals`）+ `name` + 两个枚举下拉；edit = 仅两个枚举；**不对 `name` 做长度 / 空串 / 字符校验**；失败按 `error.code`（`VALIDATION_ERROR` 展示 `details[].field`）。
5. **`composables/useNetworkInterfaceDelete.ts`**：复用 `useResourceDelete`；`409` 按 `details[].code === 'ACTIVE_CHILDREN_EXIST'` 渲染；**不假定「NIC 永远无子资源」**。
6. **`App.vue`**：NIC 列表 / 详情视图与切换；从 BareMetal 详情进入「该宿主网络接口」（携带 `bare_metal_id`）并保留返回上下文。
7. **禁止重复实现业务守卫**（§21）。
8. **不做**：IP / VM / Container / Service UI、平台同步 UI、审计 / 恢复 / 回收站 / 批量 / 导出 / 高级筛选。

---

## Contract

```text
READY
```

唯一权威正文：`docs/api/f004-network-interface.md`。

---

## Test Work

### API + DB 行为

| # | 测试 | 层次 | AC |
|---|---|---|---|
| T-01 | `POST`（活跃宿主 + 合法枚举）→ `201`，字段集合恰 7 字段；无 `deleted_at` / `status` / IP / MAC / 速率 / MTU / 载体字段 | API | AC-01 |
| T-02 | `POST` 缺 `name` / 非字符串（含 `{}`）→ `400` `field=="name"`，无写入 | API + DB | AC-02 |
| T-03 | 四个合法 `technology_type` 均 `201`；`FibreChannel` / `ethernet` / `"Other "` / 空串 / `null` / 缺失 → `400` `field=="technology_type"` | API + DB | AC-03 |
| T-04 | 同 T-03 对七个合法 `purpose` 与非法值成立 | API + DB | AC-04 |
| T-05 | `"Other"` → `201` 读回 `"Other"`；schema 无 `other_text` / `description`；任意非枚举字符串 → `400` | API + Schema | AC-05 |
| T-06 | `POST` 缺 / 非整数 `bare_metal_id` → `400` `field=="bare_metal_id"` | API | AC-06 |
| T-07 | 引用不存在 / 已软删宿主 → `404 NOT_FOUND`，无写入、非 5xx；`?bare_metal_id=` 同语义 | API + DB | AC-07 |
| T-08 | 多父 / `vm_id` / `container_id` / `cluster_id` / `carrier_type` 等未识别字段 → `400` | API | AC-08 |
| T-09 | 同宿主连续登记 2 张同名 `eth0` → 均 `201`；`bare_metal_id` 同、`id` 不同 | API + DB | AC-09 / AC-12 |
| T-10 | 含中文 / 点号 / 连字符的 `name` 与枚举字面值原样往返 | API + DB | AC-10 |
| T-11 | 空串 / 含首尾空白 `name` **不被拒绝** | API | AC-11 |
| T-12 | 请求 / 响应 / 表 / 端点 / 参数**无** `status` | API + Schema | AC-13 |
| T-13 | `GET` 无活跃 NIC → `200` + 空信封，非 404；分页正确 | API | AC-14 |
| T-14 | `GET /{id}` 不存在 / 已软删 → `404`（不区分） | API | AC-15 |
| T-15 | `?bare_metal_id=`：宿主不存在 / 已删 → `404`；存在但无活跃 NIC → `200` + `items==[]`；只返回该宿主子集 | API + DB | AC-16 |
| T-16 | 绕过应用层预置 `deleted_at` → 不出现在 items / total；按 id → `404` | API + DB | AC-17 |
| T-17 | `PATCH` 合法枚举 → `200` 新值；再次读取一致；缺省不变；两者同时可改 | API + DB | AC-18 |
| T-18 | `PATCH` 非法枚举 → `400` + `details[].field` 无写入；直连库写非法值 → `23514`，经应用 → `400`（非 500） | API + DB | AC-19 |
| T-19 | `PATCH` 含未识别 / 不可变字段 → `400`；空 body → `400` | API | AC-20 |
| T-20 | `DELETE`（活跃）→ `204` 无响应体；行仍物理存在、`deleted_at` 非空 | API + DB | AC-21 |
| T-21 | 删除 NIC 后宿主字段**逐字段不变**；无其它行被改 / 物理删除 | API + DB | AC-22 |
| T-22 | 无 restore / undelete / purge / 批量 / `include_deleted` | API | AC-23 |
| T-23 | 两行同名 NIC 各自软删可成功；已删行 `deleted_at` 不被改写；不存在 `409 DUPLICATE` 路径 | API + DB | AC-24 |
| T-24 | 宿主有活跃 NIC → `DELETE /api/bare-metals/{id}` → `409` + `code=="ACTIVE_CHILDREN_EXIST"`；宿主 `deleted_at` 仍 NULL | API + DB | AC-25 |
| T-25 | 软删该宿主全部活跃 NIC（及其它活跃子资源）后 → `DELETE` 宿主 `204` | API + DB | AC-26 |
| T-26 | 并发「创建 NIC vs 删除宿主」后孤立记录 = **0 行** | 并发（DB） | AC-27 |
| T-27 | 创建 NIC 对宿主取 `FOR SHARE`；未命中 → 拒绝创建 | 并发（DB） | AC-28 |
| T-28 | `BARE_METAL_ACTIVE_CHILD_CHECKS` 非空且**同时**含 VM 与 NIC 检查，并被宿主删除路径真实消费 | 静态 + API | AC-29 |
| T-29 | `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 显式声明（当前空），NIC 删除路径经 AST 确认真实传入 | 静态 + API | AC-30 |
| T-30 | 不注册 IP 端点、无 `ip_addresses` 表、NIC 表 / schema 无 IP 字段或 `cluster_id` 列 | API + Schema | AC-31 |
| T-31 | 不注册 VM / Container / Service / Cluster 视角端点；NIC 表无这些实体结构与 VM 归属列 | API + Schema | AC-32 |
| T-32 | 无 MAC / 速率 / MTU / 光模块 / 端口 / 自动发现 / 外部同步字段或端点 | API + Schema | AC-33 |
| T-FE-01 | 三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`；`409`/`404`/`401` 分别处理；不重复实现守卫 | 前端组件 | AC-34 |

### 结构 / 静态 guard

| # | guard | 关联 |
|---|---|---|
| G-1 | ORM / 表列集合**恰为** 8 列；无 `status` / IP / MAC / 速率 / MTU / 载体列 | AC-01/08/13/31/32/33 |
| G-2 | CHECK 集合恰为两个；取值集合逐字匹配 R-NIC-001/002 | AC-03/04/19 |
| G-3 | FK 恰为 `fk_network_interfaces_bare_metal` 且 `confdeltype='r'` / `confupdtype='r'`；`ix_network_interfaces_bare_metal_id` 存在 | AC-07/08 |
| G-4 | **唯一索引集合为空**；`pg_indexes` 无 `ux_`；repository / service 无唯一性预检函数 | AC-09/12/24 |
| G-5 | 表集合 guard 演进（`network_interfaces` / `0005`），增表演进不得删测试 | 约束 |
| G-6 | `EXPECTED_GET_ROUTES` 追加 NIC 两条 GET（只增不删） | 约束 |
| G-7 | `BOUNDARY_TOKENS` 移除 NIC 两个 token，保留 `ip-address` / `container` / `service`，且**保持全局扫描** | AC-31/32 |
| G-8 | `BARE_METAL_ACTIVE_CHILD_CHECKS` guard 演进为「同时含 VM 与 NIC 检查」 | AC-29 |
| G-9 | `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 显式声明 `= ()` 且删除路径 AST 传入该常量 | AC-30 |
| G-10 | 未定义约束「不实现」：无 `<> ''` / 长度 / `trim` / `/` CHECK；schema 无 `min_length` / `pattern` / `strip`；空串 / 首尾空白原样存取 | AC-11 |
| G-11 | 无 CASCADE；列 `collation_name IS NULL`；无触发器 | R-DELETE-005 |
| G-12 | 唯一软删写入路径 allow-list 保持 `{backend/app/deletion/service.py}`；NIC 模块不写 `deleted_at` | AC-21/23 |
| G-13 | 无通用 `resources` 表 / EAV / STI / 多态 / JSON(B) | §24 |
| G-14 | `MIGRATION_HEAD` 与 `alembic current` = `0005_f004_network_interfaces`；可应用 / 可重复 / 可从空库重建；downgrade 到 `0004` 后 NIC 表被删、既有表完好 | 约束 |

### 必须同步演进的既有测试

`tests/database/{helpers,test_schema,test_migrations}`、`tests/test_structure_guard.py`、`tests/test_auth_guards.py`、`tests/test_cluster_views_guards.py`、`tests/test_bare_metals_guards.py`。`tests/test_deletion_guards.py`、`tests/database/test_deletion_schema_guard.py`、`clusters` / `virtual_machines` 结构 guard → **原样保留**。

---

## REQUIRED

1. `network_interfaces` **不得**有任何唯一性约束（NQ-2），**不得**实现应用层 NIC 名称唯一性预检。
2. `bare_metal_id NOT NULL` + FK `ON DELETE RESTRICT ON UPDATE RESTRICT`；**禁止 CASCADE**。
3. 创建**必须在同一事务内**对父 BareMetal 取 `FOR SHARE` 并确认活跃；未命中即 `404`。
4. `deleted_at` 写入路径**恰好 1 条**；NIC 删除必须委托 `soft_delete()`。
5. 宿主删除路径的活跃子资源检查**必须同时包含**活跃 VM 与活跃 NIC 检查；**不得**丢弃 F006 的 VM 检查。
6. `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` **显式声明**（空元组）且被 NIC 删除路径**真实传入**（AST 可验证）。
7. 两个枚举的校验实现**唯一一份**，创建 / 更新共用；`23514 → 400`（永不 500）。
8. `name` **不得**有隐式长度 / trim / 字符 / `/` 约束；schema **不得**给任何字段添加 `min_length` / `pattern` / `strip_whitespace`。
9. 请求 / 响应 schema **封闭**（`extra="forbid"`）；`PATCH` 不含 `name` / `bare_metal_id` / `id` / `deleted_at`；空 body → `400`。
10. 不新增任何 CASCADE / 触发器 / `COLLATE`；不改 `0001`–`0004`。
11. 既有 guard **必须演进而非删除**；`BOUNDARY_TOKENS` 必须同步收窄（仅移除 NIC token、保持全局扫描），否则 F004 会因 F009 guard 失败。
12. 失败不得依赖前端；守卫由后端裁决（§21）。
13. 所有端点位于 `/api` 前缀下，由 F013 自动覆盖，**不新增白名单**。
14. 错误信封 / 状态码 / SQLSTATE 映射**复用**既有机制。
15. **不得**为 NQ-1（VM 拥有独立 NIC）或 NQ-2（NIC 名称唯一）预留任何字段、参数、分支、常量或占位。

---

## Constraints

1. 不得修改或新增 `clusters` / `users` / `sessions` / `bare_metals` / `virtual_machines` 的列与约束；只新增 `0005`。
2. 不得新增 `status` 列 / 状态枚举 / 状态端点 / 状态过滤。
3. 不得新增 IP / MAC / 速率 / MTU / 光模块 / 端口 / 自动发现 / 外部平台同步字段或端点。
4. 不得新增指向 VM / Container / Service / Cluster 的结构或载体类型选择器；不得新增 `cluster_id` 列。
5. 不得实现 NIC 名称唯一性（含 DB 唯一索引与应用层预检）。
6. 不得实现第二条 `deleted_at` 写入路径；不得实现 restore / undelete / purge / 批量删除。
7. 不得偏离 `api-conventions.md` 的信封、状态码与 Empty / Not Found 语义。
8. 不得在前端重复实现业务守卫（§21）。
9. 不得引入新框架 / 新中间件 / 新依赖 / vue-router；不得引入 EAV / 通用表 / STI / 多态 / JSONB。
10. 不得修改既有契约正文；F004 契约唯一正文在 `docs/api/f004-network-interface.md`。
11. 不得为 NIC 提供 `by-name` 别名；不得实现 `name` / 父绑定可变。

---

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | F004 注册 `/api/network-interfaces` 会使 F009 的 `BOUNDARY_TOKENS` guard 失败；若处理不当会删测试或全局禁用 | REQUIRED #11；G-7；仅移除 NIC 两 token、保持全局扫描 |
| R2 | 既有表集合 / 路由 / 检查点 guard 被删除而非演进 | REQUIRED #11；G-5 / G-6 / G-8 |
| R3 | 「顺手」加上 NIC 名称唯一约束或应用层预检（NQ-2 未确认，属静默修改产品规则） | REQUIRED #1；G-4；T-09 / T-23 |
| R4 | 「顺手」加上 IP / MAC / 速率 / MTU / VM 载体字段或选择器 | G-1；T-08 / T-30 / T-31 / T-32 |
| R5 | `name` 被加上 `<> ''` / 长度 / trim / `/` CHECK | G-10；T-11 |
| R6 | F014 端到端被简化或 fail-open（检查点被替换为空或丢 VM 检查） | G-8；T-24~T-28 |
| R7 | 枚举 CHECK / FK 冲突返回 500 | 应用层预检 + 既有 SQLSTATE 映射；T-18 |
| R8 | 数据库文档漂移（`f012-baseline-migration.md` revision 号因 F006 占用 `0004` 而失真） | Database Work 3 项同步；协调器落盘 |
| R9 | NQ-6 裁定与 F010 预期不一致，导致重复实现过滤 | 契约固定并标注 F010 必须复用；T-15 |
| R10 | 前端把枚举下拉或宿主选择做成前端业务校验入口 | REQUIRED #12；T-FE-01 |

---

## Open Questions

### Blocking

**无。** NQ-5 / NQ-6 已裁定。

### Non-blocking

1. **NQ-1**（VM 等是否拥有独立 NIC）：**不裁定、不实现、不预留**（AC-08 明确拒绝以 VM 为父）。
2. **NQ-2**（NIC `name` 同宿主唯一性）：**不实现、不承诺**（AC-12）。
3. **NQ-3**（可变性）：**不实现**；`PATCH` 不含 `name` / `bare_metal_id`。
4. **NQ-4**（`Other` 伴随自由文本 / 中文映射）：**不实现**；中文展示仅属 UI。
5. **NQ-7**（`PATCH` 可变字段）：固定为 `{technology_type, purpose}`。
6. **NQ-8**（`name` 未定义约束）：**不实现、不承诺**。
7. **NQ-9**（F005 义务）：F005 须向 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 追加「活跃 IPAddress」检查并补端到端。
8. **NQ-10**（F011 复用）：导入 NIC 行须复用 `app/network_interfaces/validation.py` 的同一套校验。
9. **NQ-11 / NQ-12**（文档 / 计划元数据、工程约定）：由协调器 / Backend / Frontend 落盘。
10. 若绕过 `FOR SHARE` 预检，`23503` 经通用映射返回 `409 CONFLICT`（`REFERENCE`）而非 `404`；该路径在产品路径下**不可达**。

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

1. **契约层**：字段集合封闭、必填与枚举 `400`、宿主存在性 / 活跃性 `404`、列表 Empty 与详情 Not Found、负向路由 / 参数。
2. **无唯一性**：同宿主同名两行均 `201`；无 `ux_` 索引；无唯一性预检；不存在 `409 DUPLICATE`。
3. **枚举与最终权威**：两路径非法值 `400` + `details[].field`；DB 直写非法值 `23514` → `400`。
4. **关系写入与并发**：schema 封闭、`FOR SHARE` 锁序、孤立记录不变式 0 行。
5. **维护与删除**：PATCH 部分更新与封闭性、软删、不级联、无恢复 / 批量。
6. **F014 / F005 端到端**：宿主有活跃 NIC → `409` 无部分写入；软删后可删；检查点声明与消费。
7. **无状态与边界**：无 `status`、无 IP 语义、无越界实体 / 载体结构、无未确认硬件字段与自动发现。
8. **未定义约束「不实现」**：无 CHECK、无 schema 约束、空串 / 首尾空白原样存取。
9. **数据层结构（G-1~G-14）**。
10. **前端（AC-34）**。
11. **工程门禁**：lint 通过；既有 F012/F013/F014/F015/F002/F006/F009 测试全绿；所有 guard 完成演进而非删除。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：Product Handoff 为 `READY FOR ARCHITECT` 且无 Blocking；`database: true`；API Contract = `READY`；Backend / Frontend 两分支均有可直接开工的依据。全部 13 个待决技术问题已逐条裁定。**需用户确认的长期技术决策：无。**

GIT: NONE
