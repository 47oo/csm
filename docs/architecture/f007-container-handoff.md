# Architecture Handoff — F007 Container 资源模型与登记

> Feature: F007「Container 资源模型与登记」（E03，P1，`depends_on: [F006, F002]` 均 DONE）
> Author Role: architect
> Status: `READY FOR IMPLEMENTATION`
> Product Source: `docs/product/handoffs/f007-container.md`（`READY FOR ARCHITECT`；权威需求，AC-01~AC-44）
> 已批准架构：ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005（均 `ACCEPTED`）
> 契约：`docs/api/f007-container.md`（Status `READY`，本 Feature 单一权威）
> 既有实现先例：`backend/app/virtual_machines/**`（最相近）、`bare_metals/**`、`network_interfaces/**`、`ip_addresses/**`、`deletion/**`、`db/active.py`、`models/**`、`tests/**`

---

## Architecture Summary

在既有 F002/F006 之上新增显式资源表 `containers`，落地「长期服务型 Container 实例」的人工登记 / 查询 / 可选字段维护 / 逻辑删除，以及 `Container → 运行载体` 这一 **多态、必选、恰好一个** 关系，并向 F014 双载体父删子拦交付端到端。

**不新建技术栈、不新建分层**，完全复用既有模式。

**方案要点**：

1. 多态载体采用 **两列可空 FK + `CHECK (num_nonnulls(...) = 1)` + 两列 partial unique index**（§1 裁定）。
2. 写入对**被选中载体行**取 `FOR SHARE` 并同事务确认活跃。
3. `BARE_METAL_ACTIVE_CHILD_CHECKS` 追加容器检查；`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 由空元组变非空；新增 `CONTAINER_ACTIVE_CHILD_CHECKS = ()`。
4. 载体内 `name` 唯一由应用层 `409`（体验）+ 数据库 partial unique index（最终权威）双层保证。

## Domain Impact

- **新增领域对象**：`Container`（V1 登记粒度=长期服务型实例；无状态；无 `cluster_id`）。
- **新增关系**：`Container → 运行载体`（BareMetal **或** VirtualMachine **二选一，恰好一个**；mandatory；关系本身不进数据库，落为两张表的 FK 择一）。Cluster 归属由载体推导，**不持久化**。
- **使用既有对象**：BareMetal / VirtualMachine（存在且活跃判定 + 删除守卫）。
- **不新增领域对象 / 字段 / 状态 / 唯一性规则**；不修改任何既有领域规则。
- 结构性演进：`BARE_METAL_ACTIVE_CHILD_CHECKS` 增加成员；`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 由显式空元组变非空；新增 `CONTAINER_ACTIVE_CHILD_CHECKS`（显式空元组，F008 追加位置）。

## Data Layer Impact

Database Agent 需在 `docs/database/f007-container-migration.md` 定义并交付 **`0007_f007_containers`**（`down_revision = "0006_f005_ip_addresses"`，当前 head）：

1. **数据层要解决的问题**：新增一张显式资源表，承载「恰好一个多态载体」与「载体内活跃 `name` 唯一（大小写敏感、软删释放）」，且不引入 CASCADE、触发器、EAV、JSON、生成列或 ORM 多态。
2. **新增表**：`containers`，11 列（见下）。**无** `status` 列、**无** `cluster_id` 列、**无** K8s/Docker/运行时/位置列。
3. **约束**（4 个）：`pk_containers`；`fk_containers_bare_metal`（`ON DELETE RESTRICT ON UPDATE RESTRICT`）；`fk_containers_virtual_machine`（`RESTRICT/RESTRICT`）；`ck_containers_carrier_exactly_one`（`CHECK (num_nonnulls(bare_metal_id, virtual_machine_id) = 1)`）。
4. **索引**（4 个）：`ux_containers_bare_metal_name_active`（`UNIQUE (bare_metal_id, name) WHERE deleted_at IS NULL`）、`ux_containers_virtual_machine_name_active`（`UNIQUE (virtual_machine_id, name) WHERE deleted_at IS NULL`）、`ix_containers_bare_metal_id`、`ix_containers_virtual_machine_id`。**不声明 `COLLATE`、不使用 `lower()`**。
5. **Migration**：一条 `CREATE TABLE` + 4 个索引；`downgrade` 严格逆序。**不修改** `0001`~`0006`。无数据迁移（表首次创建）。无 extension / 触发器 / 生成列。
6. **文档同步（NQ-8）**：更新 `docs/database/csm-v1-schema-design.md` 第 442 / 731 / 892 行（Container→载体由 UNCONFIRMED 更新为 mandatory/exactly_one；「不得固化 NOT NULL」注记作废并替换为本表设计）；`docs/database/f012-baseline-migration.md` revision 序列加入 `0007`。

**建议 DDL**（Database Agent 据此细化，非最终实现）：

```sql
CREATE TABLE containers (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY,
  bare_metal_id      BIGINT NULL,   -- 载体二选一（其一）
  virtual_machine_id BIGINT NULL,   -- 载体二选一（其一）
  name               TEXT   NOT NULL,
  image              TEXT   NULL,
  cpu                TEXT   NULL,
  memory             TEXT   NULL,
  owner              TEXT   NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at         TIMESTAMPTZ NULL,
  CONSTRAINT pk_containers PRIMARY KEY (id),
  CONSTRAINT ck_containers_carrier_exactly_one
    CHECK (num_nonnulls(bare_metal_id, virtual_machine_id) = 1),
  CONSTRAINT fk_containers_bare_metal FOREIGN KEY (bare_metal_id)
    REFERENCES bare_metals (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_containers_virtual_machine FOREIGN KEY (virtual_machine_id)
    REFERENCES virtual_machines (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE UNIQUE INDEX ux_containers_bare_metal_name_active
  ON containers (bare_metal_id, name) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX ux_containers_virtual_machine_name_active
  ON containers (virtual_machine_id, name) WHERE deleted_at IS NULL;
CREATE INDEX ix_containers_bare_metal_id      ON containers (bare_metal_id);
CREATE INDEX ix_containers_virtual_machine_id ON containers (virtual_machine_id);
```

## Backend Work

新增 `backend/app/containers/**`（对齐 `virtual_machines/**` 结构）并接线：

1. `models/container.py`：`Container(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`，`__tablename__="containers"`，列与约束 / 索引严格对应上表；`image/cpu/memory/owner` 为 `Text | None`；**无** `status` / `cluster_id` / K8s / 位置列。
2. `containers/schemas.py`：`ContainerCreate` / `ContainerUpdate` / `ContainerRead`（`extra="forbid"`，无字段级约束、无 validator）。
3. `containers/repository.py`：`get_active` / `list_active`（按载体列过滤）/ `active_name_exists(carrier…)` / `create` / `update`；读取一律经 `app/db/active.py` 的 `active_filter` / `select_active`；写入不触碰 `deleted_at`。
4. `containers/service.py`：`create`（**先锁活跃载体**，再 `409` 预检，再插入 flush）；`list` / `get` / `update`（PATCH 不含 `name` 与载体绑定）；`delete`（委托 `app.deletion.soft_delete`，显式传入 `CONTAINER_ACTIVE_CHILD_CHECKS`）。
5. `containers/deletion.py`：`CONTAINER_ACTIVE_CHILD_CHECKS = ()`；`has_active_containers_on_bare_metal(session, bare_metal_id)`、`has_active_containers_on_virtual_machine(session, virtual_machine_id)`（`EXISTS` 语义，复用 `active_filter`）。
6. **演进** `bare_metals/deletion.py`：`BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines, has_active_network_interfaces, has_active_containers_on_bare_metal)`（**保留** VM/NIC）。
7. **演进** `virtual_machines/deletion.py`：`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS = (has_active_containers_on_virtual_machine,)`（由显式空元组变非空）。
8. `containers/router.py`：5 个端点，挂载于 `app/main.py`（`include_router(containers_router, prefix="/api")`），自动受 `/api/*` 认证中间件覆盖，无需白名单。
9. 载体锁：`select_active(Model).where(Model.id == carrier_id).with_for_update(read=True)`（单表 `FOR SHARE`；**无 `OF`**，因为无 JOIN）。

## Frontend Work

新增（对齐 `VirtualMachineListPage.vue` / `VirtualMachineDetailPage.vue` / `api/virtualMachines.ts` / `types/api.ts`）：

- `src/api/containers.ts`：`ContainerRead` 类型 + `listContainers` / `getContainer` / `createContainer` / `updateContainer` / `deleteContainer`。
- `src/pages/ContainerListPage.vue`：列表 + 分页 + 载体类型筛选（`carrier_type`/`carrier_id`）+ 删除入口。
- `src/pages/ContainerDetailPage.vue`：详情 + 登记表单（含**载体类型选择器** `BARE_METAL`/`VIRTUAL_MACHINE` 与载体 id）+ 四个可选字段 PATCH 表单 + 删除。
- 路由注册。
- **三态**（Loading / Empty / Error）互不相同；**Empty**（200 + `items==[]`）与 **Not Found**（404）渲染不同状态；错误按 `error.code`（必要时结合 `details[].code`）分支，**不解析 `message`**；`409`/`404`/`401` 分别处理；**前端不得自行实现业务守卫**。

## API Contract

### Status

```text
READY
```

### Contract

权威正文：**`docs/api/f007-container.md`**。要点：

- 5 个端点：`POST /api/containers`、`GET /api/containers`、`GET /api/containers/{container_id}`、`PATCH /api/containers/{container_id}`、`DELETE /api/containers/{container_id}`。
- 请求 / 响应使用 **`carrier_type` + `carrier_id`** 表达多态载体；按载体读取使用成对 query `?carrier_type=&carrier_id=`。
- 响应字段集合恰为 `{id, carrier_type, carrier_id, name, image, cpu, memory, owner, created_at, updated_at}`（10 字段）。
- 错误码：`400 VALIDATION_ERROR` / `401 UNAUTHENTICATED` / `404 NOT_FOUND` / `409 CONFLICT`（`details[].code = "DUPLICATE"` 或 `"ACTIVE_CHILDREN_EXIST"`）。

## Test Work

在 `backend/tests/**` 复用既有模式，交付：

1. **API 行为**：AC-01~AC-03、AC-09~AC-17、AC-19、AC-21~AC-35、AC-38、AC-44（经 API）；`409`/`404`/`400`/`401` 信封逐字段断言。
2. **数据库约束（绕过应用层直连）**：AC-18（同载体重复活跃 → `23505`）、AC-15（跨类型同 id → 成功）、AC-17（大小写共存）、AC-19（软删释放）、`num_nonnulls` CHECK（0 举 2 载体 / 2 举 2 载体 → `23514`）、FK `RESTRICT`、无 CASCADE。
3. **并发**：AC-36 / AC-37 孤立记录不变式 = 0 行；AC-38 载体共享锁（对齐 `test_virtual_machines_concurrency.py`）。
4. **Guard（静态 / 结构）**：AC-11、AC-21、AC-23、AC-32、AC-39~AC-41、AC-42、AC-43，以及既有 guard 的演进（§10）。
5. **Alembic**：`upgrade` 幂等、`downgrade 0006` 可逆、`alembic check` 无漂移、既有表结构不变。

## Technical Decisions

### CONFIRMED

1. Container 登记粒度、绑定必选且恰好一个、载体为 BareMetal/VM、Cluster 归属推导、无状态、载体内 `name` 唯一且大小写敏感、软删释放唯一性、父有活跃子不得删、不级联（R-CONTAINER-001~005；Q-002=B）。
2. `id` 为规范路径 + 列表信封 + `deleted_at` 不暴露；错误信封与状态码（ADR-0003）。
3. 单一软删写入路径 + 父删子拦同事务加锁 + 活跃子检查由资源模块显式声明（ADR-0004 / F014）。
4. `/api/*` 认证（ADR-0005）。
5. PostgreSQL；默认大小写敏感 collation；partial unique index 为唯一性最终权威（ADR-0002）。

### REQUIRED

1. **多态载体必须由数据库保证「恰好一个」且保参照完整性**。`CHECK (num_nonnulls(bare_metal_id, virtual_machine_id) = 1)` + 两条 `RESTRICT` FK 为最低要求（§21 与 `AGENTS.md` §6：能被数据库可靠保证的完整性约束不得只靠应用代码）。
2. **载体内唯一性必须由数据库保证**：两条 partial unique index（predicate `deleted_at IS NULL`，大小写敏感、无 `COLLATE`、无 `lower()`）。应用层 `409` 仅为体验优化。
3. **创建须对载体行取共享锁并同事务确认活跃**，保证 AC-36/37 孤立记录不变式。
4. **F014 双载体接线**：`BARE_METAL_ACTIVE_CHILD_CHECKS` 与 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 均须包含活跃 Container 检查，且删除路径真实消费。
5. **无 `status` / 无 `cluster_id` / 无 K8s / 无位置字段**，且以可失败 guard 固定。

### PROPOSED

1. **多态载体存储 = 选项 (b)**：两列可空 FK + `CHECK num_nonnulls(...) = 1` + 两列 partial unique index。
2. **API 表示 = `carrier_type` + `carrier_id`**，请求、响应、按载体读取 query 统一使用该对。
3. **NQ-2 裁定 = `404 NOT_FOUND`**（引用不存在 / 已软删 / 类型与标识不一致的载体），`details == []`，与 F002/F004/F006 一致。
4. PATCH 可变字段恰为 `{image, cpu, memory, owner}`；`name` 与载体绑定不可变；空 body → `400`。
5. `has_active_containers_on_bare_metal` / `has_active_containers_on_virtual_machine` 两个检查函数置于 `app/containers/deletion.py`。

### OPEN

1. NQ-1（`name` / 载体绑定的登记后可变性）：维持「不可变」，变更由「软删 + 重新登记」替代；属未来范围加性扩展。
2. NQ-3（宿主 BareMetal 改属 Cluster）：Container 不持久化归属，F007 无需维护；待相关能力确认时另行裁定。
3. NQ-4/NQ-5（未定义约束 / 长期服务型判别字段）：**不实现**，且以 guard 固定（AC-11）。
4. NQ-6：本 Handoff §5 已裁定，不再是 OPEN。
5. NQ-9/NQ-10：F008 / F011 的复用义务（本 Feature 只提供声明点）。

---

## 核心裁定

### §1 多态载体的技术表示 → **选项 (b)：两列可空 FK + `num_nonnulls` CHECK + 两列 partial unique index**

**采用**：

- `bare_metal_id BIGINT NULL` + `virtual_machine_id BIGINT NULL`，两条 FK 均 `ON DELETE RESTRICT ON UPDATE RESTRICT`（**保留数据库级参照完整性**）。
- `CHECK (num_nonnulls(bare_metal_id, virtual_machine_id) = 1)`（**恰好一个**由数据库保证；0 个或 2 个均被拒绝）。
- 载体内唯一性由两条 partial unique index 表达：`(bare_metal_id, name) WHERE deleted_at IS NULL` 与 `(virtual_machine_id, name) WHERE deleted_at IS NULL`。二者合起来语义等价于 `(载体类型, 载体标识, name) WHERE deleted_at IS NULL`。

**唯一性索引如何表达**：双 FK 方案下唯一性由「每载体列一条 partial unique index」表达。因 CHECK 保证恰好一列非空、另一列必为 NULL，而 PostgreSQL 唯一索引中 NULL 互不相等，故两索引不会互相干扰，也不会误判跨类型同数值 id（AC-15 天然成立）。

**参照完整性**：**保留**。两条真实 FK 使「载体必须物理存在」由数据库保证，RESTRICT 满足「无 CASCADE」。

**「恰好一个」能否由 DB 保证**：能。`num_nonnulls` 是 PostgreSQL 内建函数；CHECK 为既有 migration 已采用的机制（`bare_metals` / `network_interfaces` 已用 CHECK 做闭集枚举）。

**不引入 ORM 多态**：两列都是普通标量列；无 STI、无 `polymorphic_on`、无 relationship 多态、无触发器、无 EAV、无生成列。既有 `test_structure_guard.py` 的 `no_polymorphic_mappers` / `no_orm_inheritance` / `no_eav_shape` 保持通过。

**否决方案及理由**：

- **(a) 判别列 `carrier_type` + `carrier_id`（无 FK）→ 否决**。唯一性索引可直接表达（优点），但**放弃数据库级参照完整性**：载体是否物理存在只能靠应用层，直接违反 `AGENTS.md` §6（「对能够由数据库可靠保证的重要完整性约束，仅依赖应用代码实现」被禁止）与 ADR-0002「DB 为最终权威」的强度。AC-36/37 的孤立记录不变式与「载体必须存在」将失去数据库第二道防线。收益（单索引）远小于代价（丢失 FK）。
- **(c) 两列 + 生成列承载判别值 → 否决**。功能上与 (b) 完全等价（单索引 vs 两索引无行为差异），却引入本项目此前从未使用的**生成列**这一新 schema 机制，并把 `carrier_type` 固化为存储工件，易被误读为判别列方案的变体。为「一条而非两条索引」付出新机制的维护与审计成本，违反「优先简单方案、不过早泛化」。且生成列不能进入 FK，对参照完整性无增益。
- **单 `carrier_type`+`carrier_id` 存储列 → 属 (a)，已否决。**
- **ORM polymorphic / STI / 触发器 / EAV / JSONB → 项目明确禁止，直接排除。**

### §5 API 表示与按载体读取路由形态（NQ-6）→ **统一使用 `carrier_type` + `carrier_id`**

**裁定**：

- 请求体与响应体使用 `carrier_type`（`"BARE_METAL"` | `"VIRTUAL_MACHINE"`，封闭枚举）+ `carrier_id`（integer）。
- 按载体限定读取使用成对 query：`GET /api/containers?carrier_type=BARE_METAL&carrier_id=3`。两者必须**同时提供**：仅给其一 → `400 VALIDATION_ERROR`；都不给 → 返回全部活跃 Container。

**理由**：

1. **AC-01 字面形态**：`{id, <载体类型标识>, <载体标识>, name, ...}` 恰是「一个类型字段 + 一个标识字段」。
2. **「恰好一个」结构化不可违反**：请求中只有一对标量字段，多载体（列表、或同时给两个载体）在 schema 层即不可表达，AC-04/AC-05/AC-06 由结构而非运行期校验保证。
3. **AC-07「载体类型 + 载体标识」可测形式**直接成立。
4. **F010 复用**：一个统一的 `carrier_type`+`carrier_id` 过滤即覆盖两种载体。

**Empty / Not Found 判定位置**（与 F004/F006 语义一致，R-QUERY-004）：

- 判定在 service 层：先按 `carrier_type` 分派，在同一事务内以「载体表按 id 查活跃行」判定载体存在性。
- 载体**不存在 / 已逻辑删除** → `404 NOT_FOUND`（`details == []`）。
- 载体**存在但无活跃 Container** → `200` + `items == []` + `total == 0`（**Empty**，非 404）。
- 只返回该载体的活跃 Container；两载体类型均成立。

**被否决形态及理由**：`?bare_metal_id=` / `?virtual_machine_id=` 互斥（F004/F006 先例）——否决：它把「载体类型」隐含进参数名，需要额外的 XOR 校验，且与请求 / 响应体出现第二套载体词汇；对多态关系而言，统一的类型 + 标识对更简单、更少校验分支。F004/F006 先例的**语义**（父存在→404、父存在但空→200 empty、供 F010 复用）被完整保留，仅参数形状在多态场景下泛化。

### §6 NQ-2 裁定 → **`404 NOT_FOUND`**

引用不存在 / 已软删 / 类型与标识不一致的载体 → `404 NOT_FOUND`，`details == []`，`error.message` 人类可读，**不得 5xx、不得写入**。与 F002 / F004 / F005 / F006 的「父资源不存在或已删 → 404」先例完全一致。

- 「类型与标识不一致」（如 `carrier_type=VIRTUAL_MACHINE` 但 `carrier_id` 实为 BareMetal）：按 `carrier_type` 分派到 `virtual_machines` 表查询，未命中 → `404`（与「不存在」不可区分，符合 §21 语义与先例）。
- 通用 SQLSTATE `23503`/`23514` 映射不用于本产品路径：`FOR SHARE` 预检先给出 `404`；CHECK / FK 为绕过应用层时的最终权威（测试断言，非产品路径）。

### §2 加锁协议（对齐 F002/F004/F005/F006）

创建 Container 时，按 `carrier_type` **分派**到被选中载体表，在**同一请求事务内**执行：

```python
model = BareMetal if carrier_type == "BARE_METAL" else VirtualMachine
stmt = select_active(model).where(model.id == carrier_id).with_for_update(read=True)  # FOR SHARE
if session.scalars(stmt).one_or_none() is None:
    raise NotFoundError()   # 不存在 / 已软删 → 404
```

- 与 F006 `_lock_active_host` 同形（单表 `with_for_update(read=True)` 即 `FOR SHARE`）。
- **不使用 `FOR SHARE OF`**：`FOR SHARE OF` 仅用于 F005 那种「一条语句 JOIN 多表、需限定锁哪张表」的场景（`derive_cluster_id`）；此处单表查询，无 JOIN，无歧义，用普通 `FOR SHARE`。
- 父资源删除侧不变：`DELETE` 对自己行 `FOR UPDATE`，再跑活跃子检查。

### §3 活跃子检查点演进

- `app/bare_metals/deletion.py`：`BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines, has_active_network_interfaces, has_active_containers_on_bare_metal)` —— **保留** F006 的 VM 检查与 F004 的 NIC 检查，仅**追加** Container 检查。
- `app/virtual_machines/deletion.py`：`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS = (has_active_containers_on_virtual_machine,)` —— 由**显式空元组**变为**非空**（F006 AC-29 / REV-3 的预留追加位置落地）。
- `app/containers/deletion.py`（新增）：`CONTAINER_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = ()`（显式空元组，代表「Service 表尚不存在」而非「Container 无子资源」；F008 追加「活跃 Service」）。

**检查函数所在模块与 F014 接线**：检查函数由**子资源模块**（`app/containers/deletion.py`）提供，父资源模块（bare_metals / virtual_machines）声明，`soft_delete(session, Model, id, active_children=<声明常量>)` 显式传入。**统一软删服务核心零改动**。导入方向 `bare_metals.deletion → containers.deletion → models.container`、`virtual_machines.deletion → containers.deletion → models.container`，无循环。

### §4 唯一性落地

- 应用层预检：`active_name_exists(carrier_type, carrier_id, name)` 命中 → `409 CONFLICT`，`details = [{"field": "name", "code": "DUPLICATE", "message": "…"}]`（与 F005/F006 先例完全一致）。
- 数据库：两条 partial unique index（§1）。**大小写敏感、不 `COLLATE`、不 `lower()`**。
- 绕过应用层直插重复活跃 `(载体, name)` → `23505`（数据库为最终权威）。

### §7 无状态 / 无 cluster_id / 无 K8s 的 guard 设计

新增 `tests/test_containers_guards.py`（对齐 `test_virtual_machines_guards.py`），全部为**可失败**断言：

1. **字段封闭**：`ContainerRead.model_fields` 恰为 10 字段；断言 `deleted_at` / `status` / `cluster_id` 不在其中。`ContainerCreate` / `ContainerUpdate` `extra == "forbid"`；`ContainerUpdate` 不含 `name` / `carrier_type` / `carrier_id` / `id` / `deleted_at` / `status` / `cluster_id`。
2. **无状态**：ORM 元数据 `containers` 列集合不含 `status`（亦不含 `state`）；OpenAPI 中容器路径无 `status` query 参数。
3. **无 cluster_id**：列集合不含 `cluster_id` / `cluster`；OpenAPI 容器端点无 `cluster*` 参数；容器模块源码无 `cluster_id` / `cluster_name`。
4. **无 K8s / Docker / Runtime / 位置字段**：对**全部 OpenAPI path** 与容器模块源码扫描 forbidden token 集合（`kubernetes`、`k8s`、`docker`、`pod`、`deployment`、`daemonset`、`replicaset`、`statefulset`、`container_runtime`、`runtime_api`、`data_center`、`datacenter`、`location`、`room`、`rack`、`u_position`、`site`、`campus`）→ 必须为空。（注意：容器模块自身文件名 / 表名含 `container`，**不得**把 `container` 作为本模块内的 forbidden token；`container` 只从**全局** `BOUNDARY_TOKENS` 中移除。）
5. **可选字段不被结构化**：`image` / `cpu` / `memory` / `owner` 无 `min_length` / `max_length` / `pattern` / `strip_whitespace` / `lower` / `upper`；模型无 validator / field_validator；`name` 同样无约束。
6. **活跃子检查点**：`BARE_METAL_ACTIVE_CHILD_CHECKS` 非空且同时包含 VM / NIC / Container 检查；`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 非空且包含 Container 检查；`CONTAINER_ACTIVE_CHILD_CHECKS == ()` 且**显式**（源码含 `= ()`）；三者均经 `_soft_delete_active_children_args`（AST）确认在各自删除路径以 `active_children=` 真实传入。
7. **唯一软删写入路径**：`scan_deleted_at_writes(APP_DIR / "containers") == {}`；全局 allow-list 不变。
8. **无 EAV / JSON / 多态 / ORM 继承**：复用 `test_structure_guard.py` 机制，对 `containers` 表成立。
9. **交付面封闭**：容器 router 恰为 5 端点；`APPROVED_API_PREFIXES` 加入 `containers`。

**既有 guard 演进规则**：`tests/test_cluster_views_guards.py::BOUNDARY_TOKENS` **仅移除** `container`，**保留** `service`，且**保持对全部 OpenAPI path 的全局扫描**（历史上两次因收窄扫描范围被判 MEDIUM 缺陷；本次不得收窄到单模块）。同时保留「非 GET 越界路由仍被检出」的能力（新增容器路由为已批准资源，故从 token 移除；其它未批准资源如 `service` 仍被全局检出）。

### §8 前端接线

见 Frontend Work。关键：三态与 Empty / Not Found 区分；错误按 `error.code`（必要时 `details[].code`）；不重复实现业务守卫。

### §9 Migration

- 当前 head = `0006_f005_ip_addresses` → 本 Feature 为 **`0007_f007_containers`**，`down_revision = "0006_f005_ip_addresses"`。
- 可达列集合：11 列。约束 4 个（1 PK + 1 CHECK + 2 FK）。索引 4 个（2 partial unique + 2 普通）。
- **不修改任何既有 migration**（`0001`~`0006` 原样）。
- 同步更新 `tests/database/helpers.py::MIGRATION_HEAD` 及各 guard 中硬编码的 head 断言。

### §10 Guard / 测试演进清单

| 位置 | 演进 |
|---|---|
| `tests/test_structure_guard.py::test_only_expected_tables_registered` | `EXPECTED_TABLES` **增表** `containers` |
| `tests/test_structure_guard.py::APPROVED_API_PREFIXES` | 追加 `containers` |
| `tests/test_auth_guards.py::EXPECTED_GET_ROUTES` | 追加 `/api/containers`、`/api/containers/{container_id}` |
| `tests/test_cluster_views_guards.py::BOUNDARY_TOKENS` | 移除 `container`，保留 `service`，保持全局扫描 |
| `tests/test_virtual_machines_guards.py::test_g6_t27_vm_active_child_checks_explicitly_declared` | 由 `== ()` / `"= ()"` 改为**非空**且包含 `has_active_containers_on_virtual_machine`（F006 REV-3 演进点） |
| `tests/test_virtual_machines_guards.py::test_g5_t26_...` | 追加断言 BM 检查含 Container |
| `tests/test_virtual_machines_guards.py::test_g11_migration_head_is_current_head` 及 `tests/database/helpers.py::MIGRATION_HEAD` | head 演进为 `0007_f007_containers` |
| `tests/database/*_schema_guard.py` | 表集合 / 索引集合 / 约束集合断言增演；**不得删测试** |
| 新增 `tests/test_containers_api.py` / `_concurrency.py` / `_guards.py`；`tests/database/test_containers_constraints.py` / `_schema_guard.py` | 交付 |

## Risks

1. **多态载体失去单列判别带来的查询可读性**：DB 层无单一 `carrier_type` 列，按载体查询需分派（应用层按 `carrier_type` 选列）。属已知取舍，由 API 统一 `carrier_type`+`carrier_id` 掩盖。（低）
2. **两列 FK 使 `containers` 表存在「结构性 NULL」**：任一时刻恰有一列为 NULL。这是 CHECK 保证的必然形态，非缺陷；由 `ck_containers_carrier_exactly_one` 与 guard 固定。（低）
3. **`FOR SHARE` 锁序**：新增「读载体行 `FOR SHARE` → 插入」；父删为「父行 `FOR UPDATE` → 读子行（无锁）」。新路径**不引入反向持锁**，不新增死锁序。（低）
4. **F006 空元组断言必须演进**：若遗漏，F007 落地后 F006 guard 会失败；已在 §10 明确列为演进点。（中，可测）
5. **文档漂移（NQ-8）**：`domain-model.yaml` / `domain-model.md` / `csm-v1-schema-design.md` / `project-plan.yaml` 的 Container→载体条目仍为 UNCONFIRMED，必须由 Database / 协调流程同步；否则后续 Agent 可能读到过时事实。（中）

## Constraints

1. **不得**修改任何既有领域规则、字段、状态、唯一性规则。
2. **不得**引入 `cluster_id` / `status` / K8s / Docker / Runtime / 位置字段或端点。
3. **不得**引入 CASCADE、触发器、生成列、EAV、JSON(B)、ORM 多态 / STI / 通用资源表。
4. **不得**为 `name` 或四个可选字段引入长度 / trim / 空串 / 字符 / 格式 / `/` 校验，也不引入「长期服务型」判别字段（NQ-4/NQ-5）。
5. **不得**新增第二条写入 `deleted_at` 的代码路径；删除必须委托 `app.deletion.soft_delete`。
6. **不得**修改 `0001`~`0006` migration；**不得**执行破坏性 schema 变更。
7. **不得**删减既有 guard 测试；只能增演（增表、增路由、增字段、演进空元组断言）。
8. **不得**收窄 `BOUNDARY_TOKENS` 的全局扫描范围（仅移除 `container`）。
9. **不得**在数据库层表达大小写折叠（`lower()` / `COLLATE`）。
10. PATCH **不得**允许 `name` 与载体绑定变更。

## Open Technical Questions

### Blocking

**None.**

### Non-blocking

1. NQ-1（`name` / 载体绑定登记后可变性）：保持不可变；未来变更属加性扩展。
2. NQ-3（载体 Cluster 归属变化的连带影响）：F007 无持久化字段需维护；待相关能力确认。
3. NQ-9 / NQ-10：F008 向 `CONTAINER_ACTIVE_CHILD_CHECKS` 追加活跃 Service；F011 复用同一套领域校验。
4. NQ-8 文档漂移：由 Database / 协调流程同步（非本 Handoff 阻塞项）。

## Implementation Layers

```text
database: true   （新增 containers 表 + 0007_f007_containers；实现由 Backend 负责）
backend:  true   （app/containers/** + 既有 deletion 常量演进 + main.py 接线）
frontend: true   （api/containers.ts + List/Detail 页 + 载体选择 + 三态）
```

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f007-container.md）
  ├─ Frontend（依契约并行）
  └─ Database Design（docs/database/f007-container-migration.md）→ Backend
                        ↓ 所有必需实现分支完成
                     Tester → Reviewer
```

无数据库变更分支与 Frontend 可并行；Backend 依赖 Database Design（新表）与已 READY 的 API Contract。

## Verification Strategy

1. **契约符合性**：5 个端点的字段集合、状态码、错误信封、Empty/Not Found 逐条对照 `docs/api/f007-container.md`。
2. **数据库权威性**：绕过应用层直连插入 / 更新，验证 `23505`（重复活跃 `(载体,name)`）、`23514`（0 或 2 个载体）、`23503`（FK）、大小写敏感、软删释放、无 CASCADE。
3. **并发正确性**：AC-36/37 孤立记录 = 0 行；AC-38 共享锁；与父删并发者恰一个成功。
4. **F014 双载体端到端**：BM / VM 有活跃 Container → `409 ACTIVE_CHILDREN_EXIST`；软删后载体可删（AC-33~AC-35、AC-39~AC-41）。
5. **边界 guard**：AC-11、AC-21、AC-23、AC-32、AC-42、AC-43 全部为可失败测试。
6. **Migration**：`upgrade head` 幂等、`downgrade 0006` 可逆、`alembic check` 无漂移、既有表结构不变。
7. **前端**：三态与 Empty/Not Found 可区分；错误按 `error.code`；不重复实现业务守卫。
8. **44 条 AC 逐条通过性**：见 API Contract 的 AC 映射表。

## AC 可实现性结论（AC-01~AC-44）

**全部 44 条均可实现，无一条需要修改产品需求。** 无 Blocking。逐条映射见 `docs/api/f007-container.md` §9。

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

`database: true`、`backend: true`、`frontend: true`；API Contract Status = `READY`。

GIT: NONE
