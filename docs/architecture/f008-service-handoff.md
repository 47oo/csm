# Architecture Handoff — F008 Service 资源管理与 Cluster 共享关联

> Feature: F008（E04，P1，`depends_on: [F001, F002, F006, F007]` 均 DONE）
> Author Role: architect ｜ Status: `READY FOR IMPLEMENTATION`
> Product Source: `docs/product/handoffs/f008-service.md`（AC-01~AC-54；NQ-01 已由用户确认）；`requirements.md` §14（R-SVC-001~009，含「V1 不提供解除绑定能力」）/§21/§22；ADR-0002/0003/0004/0005
> 契约: `docs/api/f008-service.md`（本 Feature 单一权威，Status `READY`）
> 先例: `docs/architecture/f007-container-handoff.md` §1/§2/§3/§7/§9/§10（直接先例）

---

## Architecture Summary

在既有 F002/F006/F007 之上新增显式资源表 `services` 与 **N:M 多态绑定表 `service_carriers`**，落地 Service 的登记 / 查询 / 可选字段维护 / 逻辑删除，以及 `Service ↔ {BareMetal | VirtualMachine | Container}` 的 **N:M、必选、集合语义**绑定，并把 F007 预留的 `CONTAINER_ACTIVE_CHILD_CHECKS` 追加点与 F002/F006 的检查点一起演进为三载体父删子拦端到端。

**不新建技术栈、不新建分层、不修改任何既有领域规则。** 要点：

1. **N:M 绑定 = 单张绑定表 + 三个可空 FK 列 + `CHECK (num_nonnulls(...) = 1)` + 3 条 partial unique（集合语义）**（§1；F007 多态载体方案的直接推广）。
2. **释放机制 = 无释放写入**：绑定行**不可变、不物理删除、无 `deleted_at`**；活跃性由 `services.deleted_at IS NULL` 派生，子检查写成「存在绑定到本载体的**活跃** Service」（§2）。
3. 登记对**每一个**载体行取 `FOR SHARE` 并同事务确认活跃，锁获取顺序由 **(载体类型 rank, carrier_id)** 确定（§3）。
4. `BARE_METAL_` / `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` **追加**活跃 Service 检查；`CONTAINER_ACTIVE_CHILD_CHECKS` 由 `()` 变非空；`CLUSTER_ACTIVE_CHILD_CHECKS` **不变**（§5）。
5. 全局 `name` 唯一由 `ux_services_name_active`（partial，大小写敏感）+ 应用层 `409`（§6）。

## Domain Impact

- **新增领域对象**：`Service`（V1 无状态、无 `cluster_id`、无凭据/健康字段）。
- **新增关系**：`Service ↔ 运行载体`，**N:M、mandatory（登记时 ≥1 载体）**；`Service ↔ Cluster` 为**推导关系，不落列**。
- **不新增/修改任何既有领域规则**；`Service.name` 唯一性 = **全局**（与 `Container.name` 载体内唯一对照，**不得混用**）。
- **结构性演进**：三个 `*_ACTIVE_CHILD_CHECKS` 常量；`CLUSTER_ACTIVE_CHILD_CHECKS` 不变。

## Data Layer Impact

Database Agent 在 `docs/database/f008-service-migration.md` 定义并交付 **`0008_f008_services`**（§8）。

| 问题 | 落点 |
|---|---|
| Service 事实 + 全局活跃 `name` 唯一、软删释放、大小写敏感 | `services` 表 + `ux_services_name_active`（partial `WHERE deleted_at IS NULL`，**不 COLLATE、不 lower()**） |
| N:M 多态绑定、载体类型封闭三值、类型与标识一致 | `service_carriers`：三列可空 FK + `CHECK (num_nonnulls(...) = 1)`；4 条 FK 全 `RESTRICT`/`RESTRICT` |
| **集合语义**（同一 Service 内不重复同一载体） | 3 条 partial unique：`(service_id, <carrier_col>) WHERE <carrier_col> IS NOT NULL` |
| 按载体反查 Service（AC-17/19/31） | 3 条载体列索引 + 1 条 `service_id` 索引 |
| 无 CASCADE / 触发器 / 生成列 / EAV / JSONB / 多态 / 通用资源表 | 由结构 guard 固定 |

**建议 DDL**（Database Agent 细化，非最终实现）：

```sql
CREATE TABLE services (
  id BIGINT GENERATED ALWAYS AS IDENTITY, name TEXT NOT NULL,
  service_type TEXT NULL, url TEXT NULL, port TEXT NULL, protocol TEXT NULL,
  owner TEXT NULL, description TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ NULL,
  CONSTRAINT pk_services PRIMARY KEY (id)                 -- 无 CHECK（AC-15）
);
CREATE UNIQUE INDEX ux_services_name_active ON services (name) WHERE deleted_at IS NULL;

CREATE TABLE service_carriers (                            -- 绑定行：无 deleted_at、无时间戳
  id BIGINT GENERATED ALWAYS AS IDENTITY, service_id BIGINT NOT NULL,
  bare_metal_id BIGINT NULL, virtual_machine_id BIGINT NULL, container_id BIGINT NULL,
  CONSTRAINT pk_service_carriers PRIMARY KEY (id),
  CONSTRAINT ck_service_carriers_exactly_one_carrier
    CHECK (num_nonnulls(bare_metal_id, virtual_machine_id, container_id) = 1),
  CONSTRAINT fk_service_carriers_service FOREIGN KEY (service_id) REFERENCES services (id)
    ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_service_carriers_bare_metal FOREIGN KEY (bare_metal_id) REFERENCES bare_metals (id)
    ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_service_carriers_virtual_machine FOREIGN KEY (virtual_machine_id)
    REFERENCES virtual_machines (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_service_carriers_container FOREIGN KEY (container_id) REFERENCES containers (id)
    ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE UNIQUE INDEX ux_service_carriers_service_bare_metal      ON service_carriers (service_id, bare_metal_id)      WHERE bare_metal_id      IS NOT NULL;
CREATE UNIQUE INDEX ux_service_carriers_service_virtual_machine ON service_carriers (service_id, virtual_machine_id) WHERE virtual_machine_id IS NOT NULL;
CREATE UNIQUE INDEX ux_service_carriers_service_container       ON service_carriers (service_id, container_id)       WHERE container_id       IS NOT NULL;
CREATE INDEX ix_service_carriers_bare_metal_id      ON service_carriers (bare_metal_id);
CREATE INDEX ix_service_carriers_virtual_machine_id ON service_carriers (virtual_machine_id);
CREATE INDEX ix_service_carriers_container_id       ON service_carriers (container_id);
CREATE INDEX ix_service_carriers_service_id         ON service_carriers (service_id);
```

## Backend Work

新增 `backend/app/services/**`（对齐 `containers/**`）并接线：

1. `models/service.py`：`Service(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`，`__tablename__="services"`，11 列；**无** `status`/`cluster_id`/凭据/健康/位置列；无 ORM relationship。
2. `models/service_carrier.py`：`ServiceCarrier(IdMixin, Base)`，`__tablename__="service_carriers"`，5 列；**无** `deleted_at`/时间戳；`CHECK` + 4 FK + 7 索引；无 ORM relationship（防 mapper 环）。
3. `services/schemas.py`：`ServiceCarrierType`（`StrEnum`，三值，字面量与 F007 一致并扩展）、`CarrierRef`（`carrier_type`+`carrier_id`，`extra="forbid"`）、`ServiceCreate`（`name` 必填；`carriers: list[CarrierRef]` 必填 `min_length=1`；6 可选字段）、`ServiceUpdate`（恰 6 可选字段）、`ServiceRead`（恰 11 字段，含 `carriers`）。7 个字段**无任何字段级约束 / validator**（AC-15）。**不修改** F007 的 `ContainerCarrierType`。
4. `services/repository.py`：`get_active` / `list_active`（含**canonical** `list_active_services_by_carrier`，供 F010 复用）/ `active_name_exists` / `create_with_carriers` / `insert_carriers` / `update`。读取经 `app/db/active.py`；**绑定写入仅 INSERT**，无 UPDATE/DELETE。
5. `services/service.py`：`create_service`（按 §3 锁全部载体 → 查重 `409` → 插 Service + 绑定行）、`list_services` / `get_service_by_id` / `update_service`（PATCH 不含 `name`/`carriers`）/ `delete_service`（委托 `app.deletion.soft_delete`，显式传 `SERVICE_ACTIVE_CHILD_CHECKS`）。
6. `services/deletion.py`：`SERVICE_ACTIVE_CHILD_CHECKS = ()`（显式）；`has_active_services_on_bare_metal` / `_on_virtual_machine` / `_on_container`（`EXISTS` 语义：`service_carriers ⋈ services` 且 `active_filter(Service)`）。
7. **演进** `bare_metals/deletion.py` / `virtual_machines/deletion.py` / `containers/deletion.py`（§5）。
8. `services/router.py`：5 端点，`main.py` `include_router(..., prefix="/api")`。
9. 载体锁：`select_active(Model).where(Model.id == carrier_id).with_for_update(read=True)`（单表 `FOR SHARE`，无 `OF`）。
10. **`app/deletion/service.py` 零改动**（§2）；allow-list 仍恰为 `{backend/app/deletion/service.py}`。

## Frontend Work

对齐 `ContainerListPage.vue` / `ContainerDetailPage.vue` / `api/containers.ts`：

- `src/api/services.ts`（`ServiceRead`、`ServiceCarrier`、`SERVICE_CARRIER_TYPES`、list/get/create/update/delete）；`src/types/api.ts` 增类型。
- `ServiceListPage.vue`：列表 + 分页 + **载体筛选**（`carrier_type`+`carrier_id`，三值）+ 删除入口。
- `ServiceDetailPage.vue`：详情 + 登记入口 + 6 字段 PATCH 表单 + 删除。
- `ServiceFormDialog.vue`：**三种载体类型**可多选、**至少选一项**才能提交；载体 id 输入。
- 路由 / `App.vue` 导航注册。
- **三态**互不相同；**Empty** 与 **Not Found** 渲染不同状态；错误按 `error.code`（必要时 `details[].code`）分支，**不解析 `message`**；`409`/`404`/`401` 分别处理；**前端不实现业务守卫**。

## API Contract

Status `READY`；权威正文 **`docs/api/f008-service.md`**。要点：5 端点；载体统一 `carrier_type`+`carrier_id`（三值闭集）；创建请求 `carriers` 数组（≥1）；响应 `carriers` **稳定按（类型 rank, id）升序**；`409 details[].code="DUPLICATE"`、`404 details==[]`。

## Test Work

1. **API 行为**：AC-01~AC-43（除并发/静态 guard 外）经 API；逐字段信封断言。
2. **DB 绕应用层**：`23505`（重复活跃 `name`；重复 `(service, 载体)`）、`23514`（0/2/3 个载体列非空的组合）、`23503`（FK / RESTRICT，禁 CASCADE）、大小写敏感、软删释放、**空串/空白 `name` 不被拒绝**、`services` 恰 1 CHECK、`service_carriers` 无 `deleted_at`。
3. **并发**：AC-46 三条孤立记录查询 = 0 行（三载体类型，真实并发）；AC-47 共享锁与「恰一个成功」。
4. **高危否定性测试**：登记失败后 Service 行与绑定行均为 0；无任何解绑端点/参数（AC-48）；AC-49 零载体查询 = 0 行。
5. **Guard（静态/结构）**：AC-15/20/21/28/48/51/52 + 既有 guard 演进（§9）。
6. **Alembic**：`upgrade head` 幂等、`downgrade 0007` 可逆、`alembic check` 无漂移、`0001`–`0007` 未改。
7. **前端**：三态与 Empty/Not Found 可区分；错误按 `code` 分支；载体选择 ≥1。

---

## 核心裁定

### §1 N:M 多态绑定 → **单张 `service_carriers` + 三个可空 FK 列 + `CHECK (num_nonnulls(...) = 1)`**

4 条真实 FK 全 `RESTRICT`；集合语义由 3 条 partial unique（`(service_id, <carrier_col>) WHERE <carrier_col> IS NOT NULL`）表达；反查由 3 条载体列索引 + `service_id` 索引支撑。

| 维度 | (a) 单表多列 FK（**选定**） | (b) 三张绑定表 | (c) 判别列 + 无 FK |
|---|---|---|---|
| 参照完整性 | **保留**（4 条真实 FK） | 保留 | **丢失** |
| 集合语义 | 3 条 partial unique | 3 条 `UNIQUE(service_id, carrier_id)` | 需应用层 |
| 反查形状（AC-31） | 1 表按类型选列分派 | 3 表分派 | 1 表但无 RI |
| Service 载体集合装配（AC-16） | **单查询** | 需 3 表 UNION | 单查询 |
| 多载体登记写入（AC-04） | 1 表批量 INSERT | 3 表 INSERT | 1 表 |
| 表数 / guard / migration 成本 | **2 表** | 4 表 | 2 表 |
| 与 F007 先例一致性 | **直接推广**（`num_nonnulls` 2 列→3 列） | 关系被拆散 | 已被 F007 §1 否决 |

**否决 (b) 三张绑定表**：语义无任何增益，却把一个关系拆成三张表——AC-16 变成 3 路 UNION，AC-04 变成 3 表写入，表/索引 guard 与 migration 对象数×3，并把「载体类型封闭三值」从「一行的 CHECK」变成「存在哪三张表」这一**隐式**结构事实。为不存在的收益付出三倍 schema 与 guard 成本。

**否决 (c) 判别列 + 无 FK**：与 F007 §1 同——**放弃数据库级参照完整性**，把「载体必须物理存在」交给应用层，违反 `AGENTS.md` §6 与 ADR-0002；AC-46 的孤立记录不变式失去数据库第二道防线。

**否决**生成列 / 复合约束 / 闭包表 / ORM 多态 / STI / 触发器 / EAV / JSONB：见 F007 §1。

**绑定表的 `id` 主键**：三列均可空、无法作 PK，沿用项目「每表一个不可变 BIGINT identity `id`」约定。绑定表**无** `created_at`/`updated_at`/`deleted_at`——它不是资源表，且无任何需求要求绑定时间。

### §2 「释放绑定」→ **(iii) 不需要释放动作**：绑定行不可变、不删除；活跃性由 `services.deleted_at` 派生

```python
select(ServiceCarrier.id).join(Service, Service.id == ServiceCarrier.service_id)
    .where(active_filter(Service), ServiceCarrier.bare_metal_id == bare_metal_id).limit(1)
```

Service 软删后该 EXISTS 立即为假 → AC-39 **自动成立**；绑定事实作为历史**完整保留**。

| 问题 | 结论 |
|---|---|
| (a) 是否引入第二条写 `deleted_at` 的路径？ | **否**。绑定表无 `deleted_at` 列（静态 guard 可判）；Service 软删仍只经 `app/deletion/service.py`。allow-list **不变**。 |
| (b) 是否物理删除资源历史？ | **否**。绑定行从不删除；`services` / 三个载体表都只软删。 |
| (c) AC-46 / AC-49 是否成立且简单？ | **是**。形状一致，各只需一次 JOIN。 |
| (d) `app/deletion/service.py` 需改动？ | **不需要**；F007 的「核心零改动」继续保持。 |

**否决 (i) 绑定行物理删除**：① **物理删除**绑定事实，破坏 §17 History Preservation 与 R-DELETE-001 精神（`AGENTS.md` §6 禁止未经确认删除重要资源历史）；② 引入新的 `DELETE` 写入路径，与「删除只改目标行、不级联」（ADR-0004 §6）冲突；③ 需把 `soft_delete` 的契约扩为「删父时顺带删子」，改动系统内唯一软删服务的核心语义。

**否决 (ii) 绑定表带 `deleted_at` 经统一软删路径释放**：`app/deletion/service.py` 的契约是「**只对已锁定的目标行**赋值 `deleted_at`，不触碰任何其他行」。在 Service 软删时写第二张表，要么修改该服务（破坏单一职责与「零改动」），要么在 `services` 模块再写一次 `deleted_at`（**直接违反 ADR-0004 allow-list**）；且与 ADR-0004 §6「删除不级联」正面冲突。收益不被任何确认规则要求。

### §3 多载体登记的加锁协议与死锁避免（AC-47）

**确定性全序**：按 **`(carrier_type_rank, carrier_id)` 升序**排序，`rank = {"BARE_METAL":0, "VIRTUAL_MACHINE":1, "CONTAINER":2}`；严格按该顺序逐个执行 `select_active(Model).where(Model.id == carrier_id).with_for_update(read=True)`。

- **同一事务内**对每个载体取共享锁并确认 `deleted_at IS NULL`；任一未命中 → `404`，**在任何 INSERT 之前**抛出 → 无 Service 行、无绑定行（AC-08/47）。
- 与 F002/F004/F006/F007 的单载体 `FOR SHARE` **完全同形**（单表、无 JOIN、不加 `OF`）；本 Feature 只把「1 次」变成「按固定序 N 次」。
- **死锁避免**：全项目多载体持锁路径**只有登记这一条**，且使用同一全序；两笔并发登记按同一全序取锁，不存在环。父资源删除只对**自身行** `FOR UPDATE` 后再读子表（不持第二把行锁）。
- **并发结果**：登记 `FOR SHARE` vs 载体删除 `FOR UPDATE` → **恰一个成功**；失败者 `404` → AC-46 成立。

### §4 按载体限定读取（NQ-09）→ **沿用 F007 成对 query，扩展三值**

- `GET /api/services?carrier_type=&carrier_id=`；`carrier_type ∈ {"BARE_METAL","VIRTUAL_MACHINE","CONTAINER"}`（封闭）。
- 仅给其一 → `400 VALIDATION_ERROR`，`details[].field` = 缺失项（AC-32）。
- **Empty / Not Found 判定在 service 层**（与 F007 一致）：按类型分派查活跃载体行，未命中 → `404 NOT_FOUND`（`details == []`）；命中但无活跃 Service → `200` + `items == []`。三种类型均成立（AC-31）。
- **F010 复用**：canonical 落在 `app/services/repository.list_active_services_by_carrier(...)` 与对应端点。**F010 必须调用该能力，不得另写过滤**；F010 自行完成「Service → 载体 → Cluster」推导，**不得**要求 F008 落 `cluster_id` 或提供 Cluster 维度过滤。

### §5 F014 三载体检查点接线（AC-41~AC-45）

| 常量 | 演进 | 检查函数所在模块 |
|---|---|---|
| `BARE_METAL_ACTIVE_CHILD_CHECKS` | **追加** `has_active_services_on_bare_metal`（保留活跃 VM / NIC / Container） | `app/services/deletion.py` |
| `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` | **追加** `has_active_services_on_virtual_machine`（保留活跃 Container） | 同上 |
| `CONTAINER_ACTIVE_CHILD_CHECKS` | `()` → `(has_active_services_on_container,)`（**非空**，落实 F007 AC-41） | 同上 |
| `CLUSTER_ACTIVE_CHILD_CHECKS` | **不变**（仍只 `has_active_bare_metals`，AC-45） | `app/clusters/deletion.py` 不动 |

- `soft_delete(..., active_children=<声明常量>)` 的接线在三个载体模块的删除函数中**真实传入**（AST guard 可判）。
- **导入方向无循环**：`app.bare_metals.deletion → app.containers.deletion → app.services.deletion → app.models.service_carrier`；`app.services.deletion` 只依赖 `app.db.active` 与模型，**不导入** `app.containers` / `app.bare_metals`。
- **不做传递性拦截**（AC-45）。

### §6 唯一性落地（AC-22~AC-27）

- DB 为最终权威：`ux_services_name_active = UNIQUE (name) WHERE deleted_at IS NULL`；**不 COLLATE、不 lower()**。
- 应用层预检：`active_name_exists` 命中 → `409 CONFLICT` + `details=[{"field":"name","code":"DUPLICATE",...}]`。
- **相互独立**（AC-23/24）：独立表、独立索引，不与其它资源的唯一索引合并；**不得**施加「载体内唯一」「按 Cluster 唯一」。

### §7 未定义约束的「不实现」保障（AC-15）

- schema 层：7 个字段**无** `min_length`/`max_length`/`pattern`/`strip_whitespace`/`lower`/`upper`，无 `field_validator`/`model_validator`。
- ORM / migration 层：`services` **恰有 1 个约束（PK）**，**无任何 CHECK**；列类型全 `TEXT`、无长度。
- **可失败 guard 固定**：字段约束标志为空、CHECK 集合为空、`character_maximum_length` 全 NULL、空串与含首尾空白 `name` 被原样接受（同时反向断言不存在隐性约束）。
- **明确后果（事实非规则）**：空串、含首尾空白、任意 `url`/`port`（含非数字）、任意 `protocol` 均**不被拒绝**；`/` 禁令**仅**适用于 Cluster 名称。

### §8 Migration

| 项 | 值 |
|---|---|
| revision | `0008_f008_services` |
| down_revision | `0007_f007_containers`（当前 head；单一线性 head） |
| 表 | **2**（`services`、`service_carriers`） |
| 列 | `services` **11**；`service_carriers` **5** |
| PK | 2 |
| CHECK | 1（`ck_service_carriers_exactly_one_carrier`） |
| FK | 4（全 `RESTRICT`/`RESTRICT`） |
| 索引 | 8（`ux_services_name_active` + 3 partial unique + 3 载体列 + 1 `service_id`） |
| 修改既有 migration | **无**（`0001`–`0007` 原样逐字节不变） |
| 数据迁移 / extension / 触发器 / 生成列 / COLLATE / CASCADE | 无 |

### §9 Guard / 测试演进清单（**增演，不得删减**）

| 位置 | 演进 |
|---|---|
| `tests/test_structure_guard.py::test_only_expected_tables_registered` | `EXPECTED_TABLES` **增表** `services`、`service_carriers` |
| `tests/test_structure_guard.py::APPROVED_API_PREFIXES` | 追加 `services` |
| `tests/test_auth_guards.py::EXPECTED_GET_ROUTES` | 追加 `/api/services`、`/api/services/{service_id}` |
| `tests/test_cluster_views_guards.py::BOUNDARY_TOKENS` | **仅移除** `service` → `()`；`test_g009_2` 保留、仍对**全部** OpenAPI path 扫描（不得收窄到单模块）；注释示例 `POST /api/services` 换成未批准资源 |
| `tests/test_containers_guards.py` G-7 | `assert "service" in tokens` → `not in` |
| `tests/test_network_interfaces_guards.py` G-7 | 同上 |
| `tests/test_ip_addresses_guards.py` G-7 | 同上 |
| `tests/test_bare_metals_api.py::test_t29_...` | `forbidden_prefixes = ("nic","service")` → `("nic",)`；`bare_metals` **列** token 断言（含 `"service"`）**保留不变** |
| `tests/test_virtual_machines_api.py`（`forbidden_prefixes` 含 `"service"`） | 移除 `"service"`；其余断言保留 |
| `tests/test_containers_guards.py` G-10 | `CONTAINER_ACTIVE_CHILD_CHECKS == ()` / `"= ()"` → **非空**且含 `has_active_services_on_container` |
| `tests/test_virtual_machines_guards.py` G-5/T-26 | 追加断言 BM / VM 检查分别含 `has_active_services_on_bare_metal` / `_on_virtual_machine` |
| head 断言（vm G-11、containers G-12、ip_addresses G-5/G-16、network_interfaces G-5）、`tests/database/helpers.py::MIGRATION_HEAD` | → `0008_f008_services` |
| `tests/database/test_migrations.py`（多处 head 与表集合） | head → `0008`；表集合增两表 |
| `tests/database/test_schema.py::EXPECTED_TABLES` | 增 `services` / `service_carriers` |
| `tests/database/*_schema_guard.py` | 列 / 索引 / 约束集合增演；无 CASCADE guard 随新 FK 继续生效 |
| 新增 | `tests/test_services_api.py`、`_concurrency.py`、`_guards.py`、`tests/database/test_services_constraints.py`、`test_services_schema_guard.py` |

> **必须特别说明**：移除 `service` token 后 `BOUNDARY_TOKENS = ()`，`test_g009_2` 变为「恒真但保留结构」的扫描。**不得删除该测试**；同时必须保留 `test_product_api_surface_is_closed`（`APPROVED_API_PREFIXES` allow-list），它才是 F008 之后真正的越界端点防线。历史上 F006-T-01 / F004-T-02 两次 MEDIUM 缺陷均因**收窄扫描范围**；本次只允许「从 token 集合中移除已成为合法资源的 `service`」，**不允许**把扫描范围从「全部 OpenAPI path」改为单模块或单前缀。

### §10 无 `cluster_id` / 无状态 / 无凭据健康的可失败 guard

| Guard | 断言 |
|---|---|
| AC-20 / AC-51 | 两表列集合不含 `cluster_id`/`cluster`/`cluster_name`；四个 schema 字段不含；全部 OpenAPI 中 `/api/services*` 参数不含 `cluster*`；`app/services/**` 源码不含 `cluster_id`/`cluster_name`；**不存在任何推导 / 持久化 Cluster 归属的写入路径** |
| AC-21 / NQ-05 | 响应只含 `carriers`；源码 / schema 无 Cluster 归属字段或返回 |
| AC-28 | 两表列集合不含 `status`/`state`；`/api/services*` 无 `status*` 参数；schema 无状态字段 / 默认值 / 过滤参数 |
| AC-52 | 全部 OpenAPI path 与 `app/services/**` 源码扫描 forbidden token（`credential`/`secret`/`password`/`token`/`health`/`monitor`/`alert`/`discover`/`sync`/`external_id`/`data_center`/`datacenter`/`location`/`room`/`rack`/`u_position`/`site`/`campus`）→ 为空 |
| AC-48（**新增，关键**） | `/api/services*` 路径集合**恰为 5 个**；不存在 `…/carriers` 子资源、`PUT`、`restore/undelete/purge/batch/by-name` 路径或参数；`ServiceUpdate.model_fields` **不含** `carriers`；`app/services/**` 中**不存在**对 `service_carriers` 的 `UPDATE`/`DELETE`/`session.delete`/`delete(` 调用——绑定写入路径**恰为一次 INSERT**；`service_carriers` 无 `deleted_at` 列 |
| AC-41 | Allow-list guard 保持 `{backend/app/deletion/service.py}`；`app/services/**` 无 `deleted_at` 写入、无 `deleted_at = None` |

## Technical Decisions

### CONFIRMED

1. 字段集合（`name` + 6 可选纯文本）、无状态、无 `cluster_id`、无凭据/健康。
2. 必选绑定、可绑多载体、可被多 Cluster 共享且只登记一次、Cluster 归属推导。
3. `name` 全局唯一、大小写敏感、软删释放。
4. 绑定了活跃 Service 的载体不得删除；**V1 不提供解除绑定能力**（2026-09-16 用户确认）；软删不级联。
5. `id` 规范路径 + 分页信封 + `deleted_at` 不暴露 + 错误信封 / 状态码。
6. 单一软删写入路径、父删子拦同事务加锁、子检查由资源模块显式声明。
7. `/api/*` 认证；PostgreSQL + 默认 collation + partial unique index。

### REQUIRED

1. **N:M 多态绑定必须由 DB 保证「每绑定行恰一个载体」且保留参照完整性**：`CHECK (num_nonnulls(三列) = 1)` + 4 条 `RESTRICT` FK。
2. **集合语义必须由 DB 保证**：3 条 partial unique；应用层 `400` 去重仅体验优化。
3. **`name` 全局唯一必须由 DB 保证**：`ux_services_name_active`。
4. **登记须对每一个载体行 `FOR SHARE` 并同事务确认活跃，且按 §3 全序取锁**。
5. **三载体检查点必须被删除路径真实消费**；`CLUSTER_ACTIVE_CHILD_CHECKS` 不变。
6. **AC-49 回归查询必须存在**。
7. **绑定写入路径唯一**：仅登记 INSERT；无 UPDATE/DELETE；绑定行无 `deleted_at`。
8. **`app/deletion/service.py` 不得改动**；allow-list 恰为 `{backend/app/deletion/service.py}`。

### PROPOSED

1. 绑定表形态 = 单表三可空 FK + `num_nonnulls` CHECK + 3 partial unique（§1）。
2. 释放机制 = 方案 (iii)「无释放写入，活跃性由 `services.deleted_at` 派生」（§2）。
3. API 载体表示 = `carriers: [{carrier_type, carrier_id}]`；按载体读取 = 成对 query（三值）。
4. 同一请求内重复载体 → **拒绝**（`400`，`details[].field="carriers"`、`code="DUPLICATE"`），而非静默去重（NQ-04）。
5. 响应 `carriers` **稳定顺序**：按 `(carrier_type rank, carrier_id)` 升序（与 §3 锁序同一全序）。
6. 载体无效 / 已删 / 类型不一致 → `404 NOT_FOUND`，`details == []`（NQ-07）。
7. PATCH 可变字段恰 6 个；`name` 与载体绑定不可变；空 body → `400`。
8. **不引入**「零载体活跃 Service」的 DB 层硬约束；以「无可移除绑定的路径」+ AC-49 回归查询兑现 AC-50（NQ-06；ADR-0002 明确避免触发器）。
9. 不提供 `by-name`（NQ-03）；不返回推导出的 Cluster 归属（NQ-05）。

### OPEN

1. NQ-02（`name` 可变性）：维持**不可变**；属未来加性扩展。
2. 「零载体活跃 Service 是否合法」：无产品路径可达；本 Feature 不裁定、不据此引入约束。
3. F011（Excel 导入含 Service 行）：必须复用同一套领域校验；行式模板的 N:M 表达属 F011 待确认项。
4. 未来「绑定变更 / 解绑」：属新产品规则，须独立 Feature 并在其 Product 阶段重新确认 R-SVC-005 的零载体语义。

## Risks

| 风险 | 级别 |
|---|---|
| 绑定表结构性 NULL 可能被误读为缺陷 —— 由 CHECK + guard 固定 | 低 |
| 方案 (iii) 下「释放」不是显式写入，评审者可能误判 AC-48 未落地 —— 契约与 guard 明确「写入路径恰一次 INSERT + 派生失效」 | 中（可测） |
| `BOUNDARY_TOKENS` 清空后 deny-list guard 变为恒真；若同时丢失 `APPROVED_API_PREFIXES` allow-list，边界防线会实质消失 | 中（必须在 §9 明确保留） |
| 多载体锁序若被写成请求顺序会产生死锁 —— 由 §3 全序 + 排序断言固定 | 中（可测） |
| AC-12 两处措辞（`services` 表「不存在 `deleted_at`」/「含载体绑定」）若被字面执行会与 ADR-0004 / AC-33 / AC-37 冲突 | 中（已解释，见 Open #6） |
| 文档漂移（NQ-10）：`domain-model.md` §8、`csm-v1-schema-design.md` 439/440/697/894、`f012-baseline-migration.md`、`project-plan.yaml`、README 迁移清单 | 中（协调流程同步） |

## Constraints

1. **不得**修改任何既有领域规则、字段、状态、唯一性规则。
2. **不得**引入 `service.cluster_id` / `status` / 凭据 / 健康 / 监控 / 发现 / 位置字段或端点。
3. **不得**引入 CASCADE、触发器、生成列、EAV、JSON(B)、ORM 多态 / STI / 通用资源表。
4. **不得**新增第二条写 `deleted_at` 的路径；**不得修改** `app/deletion/service.py`。
5. **不得**物理删除绑定行；**不得**提供解绑 / 替换载体 / 批量改绑的端点或参数。
6. **不得**为 `name` 或 6 个可选字段引入长度 / trim / 空串 / 字符 / `/` / URL 格式 / 端口数字校验。
7. **不得**修改 `0001`–`0007` migration。
8. **不得**删减既有 guard 测试；只能增演；**不得**收窄全局扫描范围（仅移除 `service`），且必须保留 `APPROVED_API_PREFIXES` allow-list。
9. **不得**在数据库层表达大小写折叠。
10. **不得**为 F010 提前实现 Cluster → Service 视图。
11. **不得**修改 `CLUSTER_ACTIVE_CHILD_CHECKS`。
12. **不得**修改 F007 的 `CarrierType`（Container 不能成为自己的载体）。

## Open Technical Questions

### Blocking

**None.**

### Non-blocking

1. NQ-02（`name` 可变性）：保持不可变。
2. NQ-04（重复载体）：裁定 `400`；若产品改为「去重并 201」属加性变更，不影响 schema。
3. NQ-06（DB 层零载体硬约束）：裁定不引入。
4. NQ-08 / NQ-10（F011 义务 / 文档漂移）：协调流程同步。
5. F010 复用义务（R-QUERY-003）。
6. **AC-12 解释（不改需求，仅消除措辞歧义）**：AC-12 中「`services` 表恰包含 …；不存在 `deleted_at`（不暴露）」按下述一致方式落地——① `deleted_at` 的限定语是「**不暴露**」，物理列**必须存在**（ADR-0004；AC-33 需预置、AC-37 需非空）；② 物理 `services` 表**不含**载体列，载体绑定由独立表 `service_carriers` 承载；字段封闭性对「请求体 / 响应体」与「两表的列集合」分别成立。此为措辞消歧，**不构成需求变更**。
7. **AC-10 的第二种可测形式**（「两个互斥字段同时给出 → 拒绝」）在本契约选定的「`carrier_type` + `carrier_id` 二元组」下**不适用**；第一种形式（类型与标识不一致 → 拒绝）成立且为 `404`。

## Implementation Layers

```text
database: true   （services + service_carriers + migration 0008_f008_services；实现由 Backend 负责）
backend:  true   （app/services/** + models + 三个 *_ACTIVE_CHILD_CHECKS 演进 + main.py 接线）
frontend: true   （api/services.ts + List/Detail 页 + FormDialog + 三态 + 多载体选择）
```

## Implementation Order

```text
Architecture + API Contract
  ├─ Frontend（依契约并行）
  └─ Database Design（docs/database/f008-service-migration.md）→ Backend
                        ↓ 所有必需实现分支完成
                     Tester → Reviewer
```

## Verification Strategy

1. **契约符合性**：5 端点字段集合（`ServiceRead` 恰 11 字段含 `carriers`）、状态码、错误信封、Empty/Not Found 对照契约。
2. **数据库权威性（绕应用层）**：`23505`（重复活跃 `name`；重复 `(service, 载体)`）、`23514`（0/2/3 个载体列）、`23503`（不存在载体 / 物理删载体被 RESTRICT 拒绝）、大小写敏感、软删释放、空串/空白 `name` 接受、`services` 恰 1 CHECK、`service_carriers` 无 `deleted_at`。
3. **并发**：AC-46 三条查询 = 0 行（真实并发）；AC-47 多载体共享锁与「恰一个成功」；登记失败后无 Service / 无绑定行。
4. **F014 三载体端到端**：三载体有活跃 Service → `409` 且 `deleted_at` 仍 NULL；软删 Service 后载体可删；`CLUSTER_ACTIVE_CHILD_CHECKS` 仍只含活跃 BareMetal。
5. **反查能力**：三种载体类型逐一验证 Empty / Not Found；同一载体被多 Service 绑定时全部返回；canonical 函数存在。
6. **边界 guard**：AC-15/20/21/28/48/51/52 全部为可失败测试；验证「移除 `service` token 后 deny-list 与 allow-list 双防线仍在」。
7. **Migration**：`upgrade head` 幂等、`downgrade 0007` 可逆、`alembic check` 无漂移、`0001`–`0007` 未改。
8. **前端**：三态与 Empty / Not Found 可区分；错误按 `error.code`；载体至少选一项。

## AC 可实现性结论（AC-01~AC-54）

**全部 54 条均可实现，无一条需要修改产品需求。** 无 Blocking。逐条映射见 `docs/api/f008-service.md` §9。

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

`database: true`、`backend: true`、`frontend: true`；API Contract Status = `READY`。

GIT: NONE
