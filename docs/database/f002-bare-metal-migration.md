# Database Handoff — F002 BareMetal 登记与管理

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Author Role: database
> Date: 2026-09-16
> Feature: F002（E01，P0，`database: true`）
> 交付：新建 `bare_metals` 表 + 增量 migration `0003_f002_bare_metals` + `docs/database/` 两处同步（NQ-6）。**不修改** `clusters` / `users` / `sessions`；**不修改** `0001` / `0002`。

---

## Design Basis

- Product：`docs/product/handoffs/f002-bare-metal.md`（`READY FOR ARCHITECT`，R-BM-001 ~ 007）。
- Architecture：`docs/architecture/f002-bare-metal-handoff.md`（`READY FOR IMPLEMENTATION`，Database Work / migration `0003` 规格）。
- ADR-0001 / 0002 / 0003 / 0004（ACCEPTED）。
- Contract：`docs/api/f002-bare-metal.md`（`READY`）。

## Existing Schema

Revision head = `0002_f013_auth`；`clusters`（`0001`，冻结）、`users` / `sessions`（`0002`）已存在。`bare_metals` 属**首次建模**，库中无该表数据。

已核实：`tests/database/helpers.py::MIGRATION_HEAD = "0002_f013_auth"`；`test_schema.EXPECTED_TABLES = {alembic_version, clusters, users, sessions}`；`test_migrations` 断言 head 与表集合；`test_g2_schema_guard` 固定 `clusters` 列 / CHECK；`test_deletion_schema_guard` 固定「无 CASCADE」「认证表无 `deleted_at`」。

---

## Schema Design — `bare_metals`（14 列）

| 列 | 类型 | 空 | 默认 | 业务含义 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | identity | 内部身份（ADR-0003，不可变） |
| `cluster_id` | `BIGINT` | NOT NULL | — | 所属 Cluster（R-BM-001 必选） |
| `hostname` | `TEXT` | NOT NULL | — | 主机名（R-BM-002 身份标识） |
| `status` | `TEXT` | NOT NULL | `'IDLE'` | 状态（R-BM-003~005） |
| `vendor` | `TEXT` | NULL | — | 厂商（R-BM-007，可选） |
| `model` | `TEXT` | NULL | — | 型号（R-BM-007，可选） |
| `serial_number` | `TEXT` | NULL | — | 序列号（R-BM-007，可选；**不参与唯一性**） |
| `cpu` | `TEXT` | NULL | — | CPU（R-BM-007，可选，纯文本） |
| `memory` | `TEXT` | NULL | — | 内存（R-BM-007，可选，纯文本） |
| `gpu` | `TEXT` | NULL | — | GPU（R-BM-007，可选，纯文本） |
| `storage` | `TEXT` | NULL | — | 存储（R-BM-007，可选，纯文本） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 登记时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 最近更新时间（应用层维护） |
| `deleted_at` | `TIMESTAMPTZ` | NULL | — | 逻辑删除标记（`NULL` = 活跃） |

**约束**

```sql
CONSTRAINT pk_bare_metals PRIMARY KEY (id)
CONSTRAINT fk_bare_metals_cluster FOREIGN KEY (cluster_id)
  REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT
CONSTRAINT ck_bare_metals_status
  CHECK (status IN ('IDLE', 'ALLOC', 'DOWN', 'UNKNOWN'))
```

**索引**

```sql
CREATE UNIQUE INDEX ux_bare_metals_cluster_hostname_active
  ON bare_metals (cluster_id, hostname) WHERE deleted_at IS NULL;   -- R-BM-002 + R-DELETE-006
CREATE INDEX ix_bare_metals_cluster_id ON bare_metals (cluster_id); -- FK 检查 + 含已删行查询
```

**明确不设计 / 不约束**：Rack / U 位 / DataCenter；状态来源 / 监控 / 自动发现；NIC/IP/VM/Container/Service 引用列；`hostname` 的长度 / trim / 空串 / 字符 / `/` 约束；`serial_number` 唯一性；七个硬件字段的长度 / 格式 / 结构化拆分；无 CASCADE / 触发器 / `COLLATE`。

## Relationships

| 关系 | 基数 | 必选 | 实现 | 删除行为 | 允许孤立 |
|---|---|---|---|---|---|
| BareMetal → Cluster | N:1 | 是（R-BM-001） | `cluster_id NOT NULL` + FK | `RESTRICT / RESTRICT`；父删子拦由应用层同事务加锁实现 | 否 |

## Required Constraints / Indexes

数据库**必须**保证：`pk_bare_metals`、`cluster_id NOT NULL + FK RESTRICT`、`hostname NOT NULL`、同 Cluster 活跃 `hostname` 唯一（partial unique，大小写敏感，软删释放）、`status NOT NULL DEFAULT 'IDLE' + CHECK` 四值、`deleted_at`。

数据库**不**保证（须应用层）：父资源活跃性（`FOR SHARE` + `deleted_at IS NULL` 预检）、「父有活跃子不得逻辑删除」、`updated_at` 准确性、七列 / `hostname` 格式。

## Backend Contract（可由数据库依赖的事实）

```text
cluster_id 一定指向物理存在的 clusters 行（FK）
status ∈ {IDLE, ALLOC, DOWN, UNKNOWN} 且永不为 NULL；未显式给值时 'IDLE'
hostname 一定非空
同 Cluster 活跃 hostname 互不相同，大小写敏感；软删后释放
跨 Cluster 允许相同 hostname
deleted_at IS NULL 是「活跃 BareMetal」的唯一判定条件
```

ORM 边界：`BareMetal(IdMixin, TimestampMixin, SoftDeleteMixin, Base)`；`__table_args__` 含 FK（RESTRICT）、CHECK、partial unique Index、`ix_bare_metals_cluster_id`；注册到 `app/models/__init__.py`。**ORM 不得牺牲数据库完整性**。

## Migration `0003_f002_bare_metals`

- `revision = "0003_f002_bare_metals"`，`down_revision = "0002_f013_auth"`（单一线性 head）。
- **upgrade**：一条 `CREATE TABLE bare_metals`（14 列 + PK + FK + CHECK）→ `create_index ux_..._active`（`postgresql_where=sa.text("deleted_at IS NULL")`）→ `create_index ix_bare_metals_cluster_id`。
- **downgrade**（逆序）：`drop_index ix_...` → `drop_index ux_...` → `drop_table bare_metals`。破坏性，生产禁止。
- 不改 `0001` / `0002`；无数据迁移；无 CASCADE / 触发器 / `COLLATE`；无 extension / database / role。
- `sa.Identity(always=True)`；时间列 `server_default=sa.text("now()")`；`CheckConstraint` 传裸名 `"status"`（命名约定生成 `ck_bare_metals_status`）。

## Verification（必须绕过应用层直连数据库）

SQLSTATE：`23505` 唯一性、`23503` FK、`23514` CHECK、`23502` NOT NULL。

- **V-1**：列集合**恰为** 14 列。
- **V-2**：CHECK 集合恰为 `{ck_bare_metals_status}`；FK 恰为 `{fk_bare_metals_cluster}` 且 `confdeltype='r'`、`confupdtype='r'`；PK 为 `pk_bare_metals`。
- **V-3**：`ux_bare_metals_cluster_hostname_active` 存在、`UNIQUE`、`indexdef` 含 `WHERE (deleted_at IS NULL)`；`ix_bare_metals_cluster_id` 存在。
- **V-4**：所有列 `collation_name IS NULL`；全库 `confdeltype='c'` 计数 = 0；无触发器。
- **V-5**：无 `<> ''` / 长度 / trim / `/` CHECK；`serial_number` 无唯一约束。
- **V-6**：同 Cluster 插 `cn001` 成功、`CN001` 成功（大小写不同）、再插 `cn001` 失败 `23505`；不同 Cluster 插 `cn001` 成功。
- **V-7**：软删后同 Cluster 可再插同名成功。
- **V-8**：不提供 `status` → `RETURNING 'IDLE'`；`UNKNOWN` 成功；`NULL` 失败 `23502`；`BOGUS`/`RUNNING`/`idle`/`''` 失败 `23514`。
- **V-9**：无效 `cluster_id` → `23503`。
- **V-10**：父 Cluster 下有 `bare_metals`（含已软删）时 `DELETE FROM clusters` → `23503`，子行仍在。
- **V-11**：不提供七列 → 插入成功、读到 `NULL`；中文 `hostname` 往返；空串 / 首尾空白原样存取。
- **V-12**：`alembic upgrade head` 一次成功且 `current = 0003_f002_bare_metals`；重复应用 no-op；`downgrade base && upgrade head` 成功。
- **V-13**：迁移后表集合含 `bare_metals`。
- **V-14**：既有 guard **演进而非删除**：`MIGRATION_HEAD` 改 `0003`；`EXPECTED_TABLES` 加 `bare_metals`；`test_migrations` / `test_structure_guard.test_only_expected_tables_registered` 同步；`test_deletion_schema_guard` 保持；新增 `bare_metals` 结构 guard（V-1~V-5）。

## 文档同步（NQ-6）— 已由协调器落盘

1. `docs/database/csm-v1-schema-design.md`：`bare_metals` Columns 表补入 R-BM-007 七列。
2. 同表注记改为「已并入列清单，`0003` 首次建表一并创建」。
3. 同文档 Open Questions 第 1 项 OPEN-004 标记关闭。
4. `docs/database/f012-baseline-migration.md` §4 `0003` DDL 补入七列。
5. 同文档 §7 改为「R-BM-007 随 `0003` 首次建表，不涉及新增列 / 数据回填」。

## Open Questions

### Blocking

**无。** `bare_metals` 结构完全由 CONFIRMED 产品文档、`READY FOR IMPLEMENTATION` 的 Architecture Handoff 与 ACCEPTED ADR 确定。

### Non-blocking

1. **NQ-3**（`POST` 显式非 `IDLE`）：不改变 DDL。
2. **NQ-1**（`hostname` / `cluster_id` 可变性 / 迁移）：F002 不实现，不改变 DDL。
3. **NQ-4**（`hostname` 字符约束）：不实现、不承诺；V-2 / V-11 固定。
4. **NQ-7**（后续 Feature 追加 BareMetal 子资源检查 / 子表 FK）：F002 建立声明点；届时新增子表 / FK，不回改 `bare_metals`。
5. **NQ-9**（`cluster_id` FK 字段回退截断，F012 F-02）：数据库层无影响；Backend 在 V-9 上补应用映射测试。

## Handoff Status

```text
READY FOR DATABASE IMPLEMENTATION
```