# F022 Database Design — `ip_address_ranges` 元数据字段（name / subnet_mask / vlan）

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Feature: F022（E02，P1，`depends_on: [F020]` = DONE）
> Author Role: database design（复核并定稿 `docs/architecture/f022-network-segment-metadata-handoff.md` 的 Data Layer Impact；**未新增任何产品规则**）
> 权威来源：`docs/architecture/f022-network-segment-metadata-handoff.md`（`READY FOR IMPLEMENTATION`）、`requirements.md` §12 **R-IP-004**（2026-09-21 DEC-024 修订）、`docs/product/domain-model.md` §5.7 / §8 / §9、`docs/product/handoffs/f022-network-segment-metadata.md`、`docs/api/f020-ip-address-range.md`（纯增量修订，Status 维持 `READY`）、ADR-0002 / ADR-0003 / ADR-0004、`docs/database/f020-ip-address-range-migration.md`、`backend/migrations/versions/0009_f020_ip_address_ranges.py`

---

## 1. 范围

覆盖**一次纯增量 migration** `0010_f022_ip_range_metadata`：

- `ALTER TABLE ip_address_ranges ADD COLUMN` 3 个可空列：`name TEXT NULL` / `subnet_mask TEXT NULL` / `vlan INTEGER NULL`；既有行取 `NULL`，**无回填、无数据迁移**。
- 新增 `name` 的**部分唯一索引**（partial unique index）`ux_ip_address_ranges_cluster_name_active`。
- 新增 `vlan` 的 `CHECK` 约束 `ck_ip_address_ranges_vlan_range`。
- **不改** `0001`–`0009`；不改任何既有列 / 约束 / 索引；不改其它表。
- **不新增** 表、extension、触发器、生成列、`CASCADE`、复合外键、第二条写 `deleted_at` 的路径。
- 无 IPv4 / 掩码 / VLAN 校验函数（属 Backend），无数据回填。

本表未新增；本 Feature 为**扩展既有表**，非首次建模。

---

## 2. 设计复核（对 Architecture Data Layer Impact 草案）

逐项复核，结论：**草案方向正确、语义完整，无需 `RETURN TO ARCHITECT`**。

### 2.1 确认无误的点

| 草案项 | 复核结论 |
|---|---|
| 扩展既有表、3 个可空列、无回填 | 与 R-IP-004 修订（三字段均可选）及「不引入第二套事实」一致。**确认**。 |
| `name` / `subnet_mask` 用 `TEXT NULL` | `subnet_mask` 为 dotted-quad 描述性元数据、`name` 为原样存取的业务可读标识；`TEXT` 允许任意字节串，不引入长度 / 字符集约束（未确认即不实现）。**确认**。 |
| `vlan` 用 `INTEGER NULL` + CHECK `1..4094` | `1..4094` 完全落在 `int4` 范围内，无需 `BIGINT`；CHECK 为数据库层最终兜底，应用层另有 `400`。**确认**。 |
| partial unique index `ux_ip_address_ranges_cluster_name_active (cluster_id, name) WHERE deleted_at IS NULL AND name IS NOT NULL` | 「同 Cluster 活跃 `name` 唯一、跨 Cluster 可重复、软删释放」的**最终权威**（ADR-0002 / ADR-0004）。谓词同时排除已删行与未命名行。**确认**。 |
| **不声明 `COLLATE`、不用 `lower()`** | 与 §22 大小写敏感立场、ADR-0002 一致。**确认**，落地时不得添加 `text_pattern` / `citext` / 表达式索引。 |
| CHECK 名为 `ck_ip_address_ranges_vlan_range` | 需经命名约定 `ck_%(table_name)s_%(constraint_name)s` 生成；Alembic 传**裸名 `"vlan_range"`**（见 F-1）。**语义确认**。 |
| `down_revision = "0009_f020_ip_address_ranges"` | 与当前 head 一致，维持单一线性 head。**确认**。 |
| 不加 `name` / `subnet_mask` 格式 CHECK，不建 VLAN 唯一 | 与「未确认即不实现」「仅新增 name 一条唯一性」一致。**确认**。 |
| 无触发器 / `CASCADE` / extension / 第二条 `deleted_at` 路径 | 与 ADR-0002 / ADR-0004 一致。**确认**。 |

### 2.2 落地修正 / 澄清（不改变 Schema 语义）

- **F-1（CHECK 约束名传递方式）**：命名约定为 `ck_%(table_name)s_%(constraint_name)s`。Alembic 与 ORM 中必须传**裸名 `"vlan_range"`**，由约定生成 `ck_ip_address_ranges_vlan_range`；若直接传全名会产生 `ck_ip_address_ranges_ck_ip_address_ranges_vlan_range`（双重前缀）。与 `0003`–`0009` 一致。
- **F-2（`ALTER TABLE … ADD COLUMN` 的默认）**：三列**不设 `server_default`**（既有行取 `NULL` 即目标行为）；`ADD COLUMN … NULL` 在 PostgreSQL 11+ 为**元数据级操作**，不重写表，无停写。
- **F-3（partial unique index 的 DDL 写法）**：`CREATE UNIQUE INDEX … WHERE …` 无法用唯一约束表达（唯一约束不接受谓词）。经 `op.create_index(..., unique=True, postgresql_where=...)` 或原生 DDL 落地；`ux_` 前缀**按字面**使用，不经过 `uq` 命名约定（约定仅作用于 `UniqueConstraint`）。
- **F-4（保留既有 `ix_ip_address_ranges_cluster_id`）**：新 unique index 是 **partial** 且首列为 `cluster_id`，**不覆盖已删行与未命名行**，**不能**替代既有完整 btree 索引 `ix_ip_address_ranges_cluster_id`（该索引服务 FK 引用完整性检查 + 含已删行的按 Cluster 读取）。**保留不动。**
- **F-5（`23505` 映射已有，不新增键）**：`app/common/sqlstate.py` 既有 `23505 → 409 CONFLICT / DUPLICATE` 通用映射覆盖本索引；**不新增 SQLSTATE 键**（R-04）。DB 兜底路径的 `details[].field` 为 best-effort，不构成契约。
- **F-6（ORM 元数据一致性提示）**：Backend 的 `IpAddressRange` 模型须以等价声明补齐三列、`CheckConstraint(name="vlan_range")`、`Index("ux_ip_address_ranges_cluster_name_active", "cluster_id", "name", unique=True, postgresql_where=text("deleted_at IS NULL AND name IS NOT NULL"))`，确保 `alembic check` 无漂移。SQLAlchemy autogenerate 对 partial index 谓词比较支持有限，**不得**让 autogenerate 误删 / 重建该索引；以 §11 V-6 显式断言为准。
- **F-7（downgrade 严格逆序）**：`drop index` → `drop constraint` → `drop column vlan` / `subnet_mask` / `name`；**不** `DROP EXTENSION`（本 Feature 不引入 extension，若 `btree_gist` 已因 F020 存在，保持不动）。
- **F-8（`name` 唯一性只在 `(cluster_id, name)` 二维）**：不是全局唯一；跨 Cluster 同名合法。不得将索引降为 `(name)`。

结论：Architecture 草案可直接实现；本文件按上述定稿给出完整规格。**无阻塞项。**

---

## 3. Migration

| 项 | 值 |
|---|---|
| revision | `0010_f022_ip_range_metadata` |
| down_revision | `0009_f020_ip_address_ranges`（当前 head；维持单一线性 head） |
| upgrade | `ALTER TABLE ip_address_ranges ADD COLUMN name TEXT NULL` → `ADD COLUMN subnet_mask TEXT NULL` → `ADD COLUMN vlan INTEGER NULL` → `CREATE UNIQUE INDEX ux_ip_address_ranges_cluster_name_active ON ip_address_ranges (cluster_id, name) WHERE deleted_at IS NULL AND name IS NOT NULL` → `ALTER TABLE ip_address_ranges ADD CONSTRAINT ck_ip_address_ranges_vlan_range CHECK (vlan IS NULL OR (vlan BETWEEN 1 AND 4094))` |
| downgrade（严格逆序） | `DROP INDEX ux_ip_address_ranges_cluster_name_active` → `ALTER TABLE ip_address_ranges DROP CONSTRAINT ck_ip_address_ranges_vlan_range` → `DROP COLUMN vlan` → `DROP COLUMN subnet_mask` → `DROP COLUMN name` |
| 数据迁移 | **无**（既有行三列取 `NULL`） |
| 是否首次建表 | 否（扩展既有表 `ip_address_ranges`） |
| 破坏性 | upgrade 为纯增量、向后兼容；downgrade 丢弃 3 个元数据列的值（核心范围段行保留），生产环境禁止，仅供开发 / CI 空库验证与重建 |
| 风险 | 见 §16 |

**顺序依据**：先加列（唯一索引与 CHECK 都依赖列存在）；索引与 CHECK 相互独立，顺序不敏感；downgrade 逆序。

---

## 4. DDL（完整）

```sql
-- 1) 3 个可空列（元数据级 ALTER，不重写表；既有行取 NULL，无回填）。
ALTER TABLE ip_address_ranges ADD COLUMN name        TEXT    NULL;  -- 网段自定义名称（原样存取）
ALTER TABLE ip_address_ranges ADD COLUMN subnet_mask  TEXT    NULL;  -- dotted-quad IPv4 掩码（原样存取）
ALTER TABLE ip_address_ranges ADD COLUMN vlan         INTEGER NULL;  -- VLAN 标注 1..4094

-- 2) 同 Cluster 活跃范围段 name 唯一（大小写敏感；软删 / 未命名释放）。
--    「同 Cluster 活跃 name 唯一」的最终权威（ADR-0002 / ADR-0004）。
CREATE UNIQUE INDEX ux_ip_address_ranges_cluster_name_active
  ON ip_address_ranges (cluster_id, name)
  WHERE deleted_at IS NULL AND name IS NOT NULL;

-- 3) vlan 限域兜底（应用层另有 400）。
ALTER TABLE ip_address_ranges
  ADD CONSTRAINT ck_ip_address_ranges_vlan_range
  CHECK (vlan IS NULL OR (vlan BETWEEN 1 AND 4094));
```

**downgrade DDL（语义，严格逆序）**：

```sql
DROP INDEX ux_ip_address_ranges_cluster_name_active;
ALTER TABLE ip_address_ranges DROP CONSTRAINT ck_ip_address_ranges_vlan_range;
ALTER TABLE ip_address_ranges DROP COLUMN vlan;
ALTER TABLE ip_address_ranges DROP COLUMN subnet_mask;
ALTER TABLE ip_address_ranges DROP COLUMN name;
```

> 说明：`name` / `subnet_mask` **不**加格式 / 长度 / 字符集 CHECK；**不**声明 `COLLATE`、**不**用 `lower()`；**不**新增触发器、extension、`CASCADE`。

---

## 5. 列清单与约束设计依据

### 5.1 列清单（扩展后恰 10 列）

| 列 | 类型 | NULL | 默认 | 业务含义 / 依据 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | 否 | identity | 内部代理主键（ADR-0003，既存） |
| `cluster_id` | `BIGINT` | 否 | — | 归属 Cluster（R-IP-004；FK，既存） |
| `start_ip` | `BIGINT` | 否 | — | 范围下界，IPv4 canonical 数值（既存） |
| `end_ip` | `BIGINT` | 否 | — | 范围上界，IPv4 canonical 数值（既存） |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | 登记时间（既存） |
| `updated_at` | `TIMESTAMPTZ` | 否 | `now()` | 最近更新时间（应用层维护，既存） |
| `deleted_at` | `TIMESTAMPTZ` | 是 | — | 逻辑删除标记（NULL = 活跃；**唯一写入路径** `app/deletion/service.py`，既存） |
| `name` | `TEXT` | **是** | — | **新增**：网段自定义名称；同 Cluster 活跃唯一、区分大小写、软删释放、跨 Cluster 可重复；原样存取（长度 / trim / 空串 / 字符集未定义，不实现） |
| `subnet_mask` | `TEXT` | **是** | — | **新增**：dotted-quad IPv4 合法掩码（连续 1 后连续 0）；描述性元数据、原样存取；不强制与 start–end 自洽；合法性与规范化由应用层 `ipv4.py` 单实现裁决 |
| `vlan` | `INTEGER` | **是** | — | **新增**：VLAN 标注 `1`–`4094`；不唯一 |

**明确不存在**：`status` / 枚举（Q-002=B 无状态）、`description` / 用途 / `owner`、CIDR / 前缀长度 / `network_address` / `broadcast_address` / `gateway` / `dhcp` / `dns` / IPv6、使用率 / 剩余地址 / 容量、分配对象 / 分配时间 / 回收状态（F021 范围），以及 `created_by` / `updated_by` / `version` / `audit`（无需求）。

**类型选择**：`name` / `subnet_mask` 用 `TEXT`（不做 trim / 归一化）；`vlan` 用 `INTEGER`（`1..4094` 落在 `int4`）。

### 5.2 约束 / 索引清单

| 对象 | 定义 | 依据 |
|---|---|---|
| `ux_ip_address_ranges_cluster_name_active`（**unique 索引**） | `UNIQUE INDEX (cluster_id, name) WHERE deleted_at IS NULL AND name IS NOT NULL` | R-IP-004 修订：同 Cluster 活跃 `name` 唯一、区分大小写、软删释放、跨 Cluster 可重复；ADR-0002 数据库最终权威 |
| `ck_ip_address_ranges_vlan_range` | `CHECK (vlan IS NULL OR (vlan BETWEEN 1 AND 4094))` | R-IP-004 修订：`vlan` 整数 `1`–`4094` 的 DB 兜底（§21） |

**保留不动**：`pk_ip_address_ranges`、`fk_ip_address_ranges_cluster`（`RESTRICT`/`RESTRICT`）、`ck_ip_address_ranges_bounds`、`ex_ip_address_ranges_active_no_overlap`、`ix_ip_address_ranges_cluster_id`。

**不建立的约束**（必须如实记录，不得自行发明）：

- **不建** `UNIQUE(name)` 或 `UNIQUE(cluster_id, name)` 全局：`name` 唯一性边界是「同 Cluster 且活跃」，必须用 partial index，且跨 Cluster 可重复。
- **不建** `UNIQUE(vlan)` / 复合唯一：`vlan` **不唯一**（同 Cluster 多网段可共用）。
- **不建** `name` / `subnet_mask` 的长度 / 字符集 / 格式 CHECK：未确认规则不实现；掩码合法性属应用层。
- **不建** `name` 的 `COLLATE` / `lower()` 表达式索引：大小写敏感为已确认语义。
- **不建** 任何触发器 / 生成列 / 跨表一致性 CHECK（ADR-0002 排除「把业务规则藏进 Schema」）。

---

## 6. 关系

| 关系 | 基数 | 必选 | 数据库实现 | 删除行为 | 允许孤立记录 |
|---|---|---|---|---|---|
| IPAddressRange → Cluster | N:1 | **是**（R-IP-004） | 既存 `ip_address_ranges.cluster_id NOT NULL` + FK | `ON DELETE RESTRICT`（不级联，既存） | 否（`NOT NULL`） |

本 Feature **不新增**任何关系 / FK / 复合外键；`name` / `subnet_mask` / `vlan` 为同表属性列，不引入关联。范围段删除守卫仍为应用层派生条件（字面落在范围内的活跃 IP），非参照完整性。

---

## 7. 数据库保证 vs 不保证的 invariant

### 7.1 数据库**真实保证**的 invariant（本 Feature 新增部分）

```text
ip_address_ranges.vlan 为 NULL，或落在 [1, 4094] 内（CHECK）
同一 Cluster 内任意两条 deleted_at IS NULL AND name IS NOT NULL 的行，name 字面互不相同（partial unique）
不同 Cluster 的相同 name 一定被允许（索引含 cluster_id）
deleted_at IS NOT NULL 或 name IS NULL 的行不参与 name 唯一性（谓词）
name 比较区分大小写（无 COLLATE / 无 lower()）
```

既有保证（F020）逐条不变（FK、bounds CHECK、EXCLUDE 不重叠、`deleted_at IS NULL` 活跃判定）。

### 7.2 数据库**不保证**的 invariant（须应用层）

```text
name / subnet_mask 的格式、长度、trim、空串、字符集（未确认即不实现）
subnet_mask 与 start–end 自洽（不强制，描述性元数据）
vlan 唯一性（不唯一）
活跃范围段的 cluster_id 指向「活跃」Cluster（应用层 FOR SHARE + Cluster 删除守卫）
```

### 7.3 必须纳入回归的查询（仍恒 0）

```sql
-- R-1 同 Cluster 活跃范围两两不重叠——期望 0 行（F020 既有）
SELECT a.id AS a_id, b.id AS b_id
FROM ip_address_ranges a
JOIN ip_address_ranges b
  ON a.cluster_id = b.cluster_id AND a.id < b.id
 AND a.deleted_at IS NULL AND b.deleted_at IS NULL
 AND a.start_ip <= b.end_ip AND a.end_ip >= b.start_ip;

-- R-2 活跃范围挂已软删 Cluster——期望 0 行（F020 既有）
SELECT count(*) FROM ip_address_ranges r
JOIN clusters c ON c.id = r.cluster_id
WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL;

-- R-3 F005 漂移查询——期望 0 行（F020 既有）
SELECT ip.id FROM ip_addresses ip
JOIN network_interfaces nic ON nic.id = ip.network_interface_id
JOIN bare_metals bm ON bm.id = nic.bare_metal_id
WHERE ip.cluster_id <> bm.cluster_id;

-- R-4（本 Feature 新增）同 Cluster 活跃同名重复——期望 0 行（由 partial unique 保证）
SELECT a.id AS a_id, b.id AS b_id, a.name
FROM ip_address_ranges a
JOIN ip_address_ranges b
  ON a.cluster_id = b.cluster_id AND a.id < b.id
 AND a.deleted_at IS NULL AND b.deleted_at IS NULL
 AND a.name IS NOT NULL AND b.name IS NOT NULL
 AND a.name = b.name;

-- R-5（本 Feature 新增）vlan 越界——期望 0 行（由 CHECK 保证）
SELECT id FROM ip_address_ranges
WHERE vlan IS NOT NULL AND (vlan < 1 OR vlan > 4094);
```

---

## 8. 并发协议（由 Backend 实现；本 DDL 提供最终权威）

既有 F020 并发协议不变（父 Cluster `FOR SHARE` → 插入 / 修改；删除委托唯一软删路径）。本 Feature 追加：

1. **创建 / 修正带 `name` 的范围段**：应用层预检 `active_name_exists(cluster_id, name, exclude_id=None)`（友好 `409 DUPLICATE`）→ 写入；`ux_ip_address_ranges_cluster_name_active` 为**最终权威**。并发同 Cluster 同名登记至多一条成功，后到者以 `23505` 被拒，经既有 `sqlstate.py` → `409 CONFLICT / DUPLICATE`，**永不 500**。
2. **锁序不变**：仍为 父 → 子；name 唯一性由 partial unique 索引内部并发控制，**不新增应用层锁、不引入新死锁序**。
3. **`name` 置 `null` / 软删**：退出唯一性判定，不产生冲突。

---

## 9. Alembic 落地要点与可重复性

**迁移文件**：`backend/migrations/versions/0010_f022_ip_range_metadata.py`，`revision = "0010_f022_ip_range_metadata"`，`down_revision = "0009_f020_ip_address_ranges"`。

落地要点：

1. 三列 `op.add_column("ip_address_ranges", sa.Column("name", sa.Text(), nullable=True))` 等；**不设** `server_default`（F-2）。
2. `op.create_index("ux_ip_address_ranges_cluster_name_active", "ip_address_ranges", ["cluster_id", "name"], unique=True, postgresql_where=sa.text("deleted_at IS NULL AND name IS NOT NULL"))`（F-3）。若用原生 `op.execute` 亦可；索引名**按字面**使用。
3. `op.create_check_constraint("vlan_range", "ip_address_ranges", "vlan IS NULL OR (vlan BETWEEN 1 AND 4094)")` —— 传**裸名 `"vlan_range"`**（F-1），生成 `ck_ip_address_ranges_vlan_range`。
4. `downgrade()` 严格逆序：`op.drop_index(...)` → `op.drop_constraint("ck_ip_address_ranges_vlan_range", "ip_address_ranges", type_="check")` → `op.drop_column("vlan")` / `"subnet_mask"` / `"name"`。
5. ORM 模型等价声明三列 + `CheckConstraint(name="vlan_range")` + `Index(..., unique=True, postgresql_where=...)`；确认 `alembic check` 无漂移（F-6）。**不得**让 autogenerate 误删 / 重建 partial unique index。

**可重复性**：

- `alembic upgrade head` 对空库一次成功；再次执行 no-op。
- `alembic downgrade 0009_f020_ip_address_ranges` 后三列 / 索引 / CHECK 被删除、其它对象完好；再 `upgrade head` 一致重建。
- `0001`–`0009` **逐字节未改**；既有表结构不变。
- `alembic check` 无 schema 漂移。

---

## 10. 对象清单（本 Feature 增量）

| 类别 | 数量 | 名称 |
|---|---|---|
| 表 | 0（扩展既有） | `ip_address_ranges` |
| 列 | 3 | `name` / `subnet_mask` / `vlan` |
| PK | 0（既有不变） | — |
| FK | 0（既有不变） | — |
| CHECK | **+1** | `ck_ip_address_ranges_vlan_range` |
| UNIQUE 索引 | **+1** | `ux_ip_address_ranges_cluster_name_active` |
| 普通索引 | 0（既有 `ix_ip_address_ranges_cluster_id` 不变） | — |
| Extension | 0 | — |
| CASCADE / 触发器 / 生成列 / `COLLATE` / 第二条 `deleted_at` 写入路径 | **0** | — |

**扩展后结构快照**：

```text
列集合       恰 10：id, cluster_id, start_ip, end_ip, created_at, updated_at, deleted_at, name, subnet_mask, vlan
CHECK 集合   恰 2：ck_ip_address_ranges_bounds, ck_ip_address_ranges_vlan_range
unique 索引  恰 1：ux_ip_address_ranges_cluster_name_active
排它约束     恰 1（不变）：ex_ip_address_ranges_active_no_overlap
普通索引     恰 1（不变）：ix_ip_address_ranges_cluster_id
触发器       恰 0
```

---

## 11. Verification（实现后必须覆盖）

**结构断言（直连 DB）**

| # | 验证 | 方法 |
|---|---|---|
| V-1 | 列集合**恰为 10 列**：`{id, cluster_id, start_ip, end_ip, created_at, updated_at, deleted_at, name, subnet_mask, vlan}`；不含 `status` / `description` / `cidr` / `prefix_length` / `gateway` / `dhcp` / `dns` / 容量类 | `information_schema.columns` |
| V-2 | 三列 `data_type` 分别为 `text` / `text` / `integer`；均 `is_nullable = YES`；均**无** `column_default` | `information_schema.columns` |
| V-3 | PK 恰为 `pk_ip_address_ranges` | `pg_constraint`（`contype='p'`） |
| V-4 | CHECK 集合**恰为** `{ck_ip_address_ranges_bounds, ck_ip_address_ranges_vlan_range}`；后者定义含 `vlan`、`1`、`4094`、`IS NULL` | `pg_constraint`（`contype='c'`） |
| V-5 | FK 恰为 `fk_ip_address_ranges_cluster`（`confdeltype='r'`、`confupdtype='r'`） | `pg_constraint` |
| V-6 | unique 索引集合**恰为** `{ux_ip_address_ranges_cluster_name_active}`；`indexdef` 含 `UNIQUE`、`(cluster_id, name)`、`deleted_at IS NULL`、`name IS NOT NULL`，且**不含** `COLLATE` / `lower(` | `pg_indexes` + `pg_get_indexdef` |
| V-7 | 排它约束 `ex_ip_address_ranges_active_no_overlap` 仍存在（`contype='x'`），定义不变 | `pg_constraint` |
| V-8 | 普通索引 `ix_ip_address_ranges_cluster_id` 仍存在 | `pg_indexes` |
| V-9 | 全库无 `confdeltype='c'`（无 CASCADE） | `pg_constraint` |
| V-10 | `ip_address_ranges` 无触发器；所有列 `collation_name IS NULL` | `information_schema.triggers`（0 行）/ `information_schema.columns` |

**约束证伪（绕过应用层直连 DB）**

| # | 验证 | 期望 |
|---|---|---|
| V-11 | 同 Cluster 直插两条**活跃同名** `name`（非 NULL） | 第二条 `23505`（`UniqueViolation`） |
| V-12 | 同 Cluster 直插 `web` 与 `Web` | **均成功**（大小写敏感，无 `COLLATE` / `lower()`） |
| V-13 | 软删一条后直插同名；或直插两条 `name IS NULL` | **均成功**（谓词 `deleted_at IS NULL AND name IS NOT NULL` 生效） |
| V-14 | 跨 Cluster 直插相同 `name` | **均成功**（含 `cluster_id`） |
| V-15 | 直插 `vlan = 0` / `4095` / `5000` / `-1` | 均 `23514`（CHECK） |
| V-16 | 直插 `vlan = 1` / `4094` / `NULL` | **均成功** |
| V-17 | 直插 `name` 为空串 / 含首尾空白 / 超长 | **均成功**（无长度 / trim / 空串 CHECK；不解读为空 name 合法） |
| V-18 | 直插 `subnet_mask` 为 `255.0.255.0` / 任意字符串 | **均成功**（DB 无掩码格式 CHECK，合法性仅应用层） |
| V-19 | 直插 `cluster_id` 不存在 | `23503`（既有 FK 不变） |
| V-20 | 软删一条后，同 Cluster 直插同名 + 重叠范围 | **均成功**（软删释放 name 与重叠） |

**不变式回归（恒 0）**

| # | 验证 | 期望 |
|---|---|---|
| V-21 | §7.3 R-1 活跃重叠 | 0 行 |
| V-22 | §7.3 R-2 活跃范围挂已软删 Cluster | 0 行 |
| V-23 | §7.3 R-3 F005 漂移 | 0 行 |
| V-24 | §7.3 R-4 同 Cluster 活跃同名重复 | 0 行 |
| V-25 | §7.3 R-5 vlan 越界 | 0 行 |

**无回填**

| # | 验证 | 期望 |
|---|---|---|
| V-26 | 对既有（pre-0010）数据行，升到 0010 后三列均为 `NULL` | `SELECT count(*) FROM ip_address_ranges WHERE name IS NOT NULL OR subnet_mask IS NOT NULL OR vlan IS NOT NULL` = 0（在未写入新值的库上） |

**Migration**

| # | 验证 |
|---|---|
| V-27 | `alembic upgrade head` 幂等（二次 no-op）；`alembic current` = `0010_f022_ip_range_metadata` |
| V-28 | `alembic downgrade 0009_f020_ip_address_ranges` 后三列 / 索引 / CHECK 被删、既有对象与其它表完好；再 `upgrade head` 一致重建 |
| V-29 | `alembic check` 无漂移 |
| V-30 | `0001`–`0009` 内容逐字节未改；既有表结构不变 |

**静态 guard（可失败，不弱化既有断言）**

| # | 验证 |
|---|---|
| V-31 | `deleted_at` 写入路径仍唯一（`app/deletion/service.py`）；`ip_address_ranges` 模块内零 `deleted_at` 赋值 |
| V-32 | 新增 `tests/test_ip_address_range_metadata_guards.py` 断言：不存在 `name` 长度 / trim / 空串 / 字符集校验、掩码自洽校验、VLAN 唯一性、CIDR / IPv6 / 网关 / DHCP / DNS / 使用率字段或端点 |
| V-33 | 唯一 IPv4 / 掩码解析实现仍在 `app/ip_address_ranges/ipv4.py`（不复制第二份） |
| V-34 | `SQLSTATE_MAP` 键集合不变（未新增键）；`23505 → 409 / DUPLICATE` 存在 |

---

## 12. Backend Contract

Backend 可以依赖以下**由数据库真实保证**的事实（本 Feature 新增）：

```text
ip_address_ranges.vlan 为 NULL 或落在 [1, 4094] 内
同一 Cluster 内任意两条 deleted_at IS NULL AND name IS NOT NULL 的行，name 一定互不相同（比较区分大小写）
不同 Cluster 的相同 name 一定被允许
deleted_at IS NOT NULL 或 name IS NULL 的行不占用 name 唯一性
```

Backend **必须自行保证、不得从数据库假设**：

```text
name / subnet_mask 的格式、长度、trim、空串、字符集（数据库无承诺）
subnet_mask 的合法性（连续 1 后连续 0）与是否与 start–end 自洽（应用层裁决）
vlan 唯一性（不存在）
活跃范围段的 cluster_id 指向「活跃」Cluster（应用层 FOR SHARE + Cluster 删除守卫）
updated_at 准确性（应用层维护；不得作为审计依据）
```

---

## 13. Open Questions

### Blocking

**无。** 列、类型、可空性、索引、约束、删除行为、migration 编号均已由 `READY FOR IMPLEMENTATION` 的 Architecture Handoff 与已 Approved ADR 确定。Handoff Status = `READY FOR DATABASE IMPLEMENTATION`。

### Non-blocking

- **OQ-1（`name` 未定义约束）**：长度 / trim / 空串 / 字符集当前不实现、不承诺；空串被接受但**不得**解读为已确认合法。
- **OQ-2（掩码归一化 / 存储表示）**：本 Feature `TEXT` 原样存取；若未来确认 canonical 化或改数值表示，属新 Feature。
- **OQ-3（按名称 / 掩码 / VLAN 查询）**：本 Feature 不新增筛选 / 排序 / `by-name`；未因此新增索引。
- **OQ-4（`alembic check` 对 partial index 的支持）**：autogenerate 对谓词比较支持有限；以 V-6 显式断言为准。
- **OQ-5（列注释）**：建议 ORM / migration 为三列加注释；属实现细节。

---

## 14. 不做什么（本次明确排除）

- 不执行任何 migration、不修改数据库（本文件仅为设计）。
- 不修改 `0001`–`0009`；不修改 `ip_address_ranges` 既有列 / 约束 / 索引；不修改任何其它表。
- 不新增 `description` / 用途 / `status` / CIDR / IPv6 / 网关 / DHCP / DNS / 使用率 / 容量 / 分配对象等字段。
- 不实现 `name` 的长度 / trim / 空串 / 字符集约束；不实现掩码格式 CHECK；不实现掩码自洽校验；不实现 VLAN 唯一性。
- 不引入触发器、`CASCADE`、extension、复合外键、生成列、EAV / 通用资源表 / JSONB。
- 不声明 `COLLATE`、不建 `lower()` 表达式索引。
- 不新增第二条写 `deleted_at` 的路径；不物理删除资源历史。
- 不新增端点 / 查询参数 / 筛选 / 排序 / 分配语义（F021 不变）；不改 F005 `ip_address` 自由文本立场。

---

## 15. 对既有 Guard 的影响（受控演进，只增不弱）

Backend / Tester 必须同步（**不得删除既有断言**）：

1. `tests/database/helpers.py`：`MIGRATION_HEAD` 由 `"0009_f020_ip_address_ranges"` 演进为 `"0010_f022_ip_range_metadata"`。
2. 其它 head 断言同步为 `0010…`（`tests/database/test_migrations.py`、`tests/database/test_schema.py`、各 `tests/test_*_guards.py` 中的 head 断言）。
3. `tests/database/test_ip_address_ranges_schema_guard.py`：`EXPECTED_COLUMNS` +3；`FORBIDDEN_TOKENS` 仅移除本 Feature 已确认合法的 `name` / `vlan`（保留 `status` / `description` / `cidr` / `gateway` / `dhcp` / `dns` / 容量等）；CHECK 集合断言扩为 2；unique 索引断言改为恰为 `{ux_ip_address_ranges_cluster_name_active}`。
4. `tests/test_ip_address_ranges_guards.py`：`READ_FIELDS` / `TABLE_COLUMNS` +3；`FORBIDDEN_FIELD_TOKENS` 仅移除 `name` / `vlan`；`MUTABLE_FIELDS` 扩为 5 元组；约束 / 索引集合断言更新。
5. **新增** `tests/test_ip_address_range_metadata_guards.py`（可失败 guard，覆盖 V-31 ~ V-34）。

> `docs/test-reports/**` 属冻结历史，**不得修改**。

---

## 16. 风险

- **风险 1**：空串 / 含首尾空白 `name` 当前被接受，可能与运维直觉不符；不违反已确认规则（契约明确「不承诺」）。
- **风险 2**：DB 兜底 `23505` 路径的 `details[].field` 为 best-effort；应用层预检先行。
- **风险 3**：多个既有 head guard 硬编码 `0009`，遗漏一处会红；§15 列出完整清单。
- **风险 4**：`alembic check` 与 partial unique index 漂移；ORM 显式 `Index(..., postgresql_where=...)` 并以 V-6 断言。
- **风险 5**：掩码无 DB 格式保证（仅应用层）；属描述性元数据，写入路径唯一。
- **风险 6**：downgrade 丢弃三列元数据值（核心范围段行保留）；生产禁止 downgrade。

---

## Database Gate 结论

```text
READY FOR DATABASE IMPLEMENTATION
```

无 Blocking Open Question；Schema、约束、索引、删除行为与 migration 编号均已定稿，可交 Backend 落地 `0010_f022_ip_range_metadata`。