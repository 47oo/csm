# F020 Database Design — `ip_address_ranges`

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Feature: F020（E02，P1，`depends_on: [F001, F005]` = DONE）
> Author Role: database design（复核并定稿 `docs/architecture/f020-ip-address-range-handoff.md` 的 Data Layer Impact 草案；**未新增任何产品规则**）
> 权威来源：`docs/architecture/f020-ip-address-range-handoff.md`（`READY FOR IMPLEMENTATION`）、`docs/api/f020-ip-address-range.md`（`READY`）、`docs/product/handoffs/f020-ip-address-range.md`、`requirements.md` §12 **R-IP-004**、`decisions_required[DEC-023].resolution`、`docs/product/domain-model.md` §5.7 / §8 / §9、ADR-0002 / ADR-0003 / ADR-0004、`docs/database/csm-v1-schema-design.md`、`docs/database/f005-ip-address-migration.md`、`docs/database/f008-service-migration.md`

---

## 1. 范围

覆盖**新增一张表** `ip_address_ranges` + **一个新 extension** `btree_gist` + **一次增量 migration** `0009_f020_ip_address_ranges`。

- **不改** `0001`–`0008` 的任何内容；不修改任何既有表的列 / 约束 / 索引。
- **无**数据迁移（表为首次创建，系统内不存在 IP 地址范围段数据）。
- 无触发器；无生成列；无 `COLLATE`；无 `CASCADE`；无复合外键；无第二条写 `deleted_at` 的路径。
- 本表是本次**唯一**新增表。

---

## 2. 设计复核（对 Architecture Data Layer Impact 草案）

对 Handoff 草案逐项复核，结论如下。**无阻塞项；草案方向正确，仅需 3 处落地修正 / 澄清。**

### 2.1 确认无误的点

| 草案项 | 复核结论 |
|---|---|
| 7 列 `id / cluster_id / start_ip / end_ip / created_at / updated_at / deleted_at`，无 status | 与 R-IP-004「至少字段」+「无状态（Q-002=B）」一致；`deleted_at` 为 ADR-0004 唯一删除标记。**确认**。 |
| `start_ip` / `end_ip` 用 `BIGINT` 存 IPv4 canonical 数值 | IPv4 上界 `4294967295 > int4` 上界 `2147483647`，**必须 `BIGINT`**（`int4` 会溢出）。**确认**，不可用 `INTEGER`。 |
| `cluster_id → clusters(id)` FK，`RESTRICT`/`RESTRICT` | 与 ADR-0004 / 既有全部 FK 约定一致，禁止 CASCADE。**确认**。 |
| `start_ip <= end_ip` 用 DB `CHECK` 兜底 + 应用层 `400`（R-02） | §21「保存前阻止」的数据库层最终权威。**确认**。 |
| 排它约束 `EXCLUDE USING gist (cluster_id WITH =, int8range(start_ip,end_ip,'[]') WITH &&) WHERE (deleted_at IS NULL)` | 语义正确：同 Cluster（`=`）、活跃行（predicate）、闭区间交集非空（`&&`）。相接区间（`[1,10]`/`[11,20]`）为离散 `int8range`，**不重叠**，与 Product NQ-A 一致。**确认**。 |
| 需 `btree_gist` | GiST 上 `bigint` 的 `=` operator class 由 `btree_gist` 提供；`int8range &&` 为内建 GiST 支持。**确认**。 |
| 无触发器、无 CASCADE、删除守卫为应用层派生条件（非 FK） | 与 ADR-0002 / ADR-0004 一致。**确认**。 |
| migration `0009_f020_ip_address_ranges`，`down_revision = "0008_f008_services"` | 与当前实际 head（`backend/migrations/versions/0008_f008_services.py`）一致，维持单一线性 head。**确认**。 |

### 2.2 修正 / 澄清（不改变 Schema 语义）

- **F-1（CHECK 约束名传递方式）**：命名约定为 `ck_%(table_name)s_%(constraint_name)s`。Alembic 中必须传**裸名 `"bounds"`**，由约定生成 `ck_ip_address_ranges_bounds`；若直接传全名会产生 `ck_ip_address_ranges_ck_ip_address_ranges_bounds`（双重前缀）。**修正落地写法**（与 `0003`/`0008` 一致）。
- **F-2（排它约束的 DDL 写法）**：`EXCLUDE` 约束无法用 `sa.CheckConstraint` 表达，`sa.Index` 也不等价（`contype='x'` ≠ 普通索引）。且表达式元素应显式加括号。**定稿写法**：

  ```sql
  ALTER TABLE ip_address_ranges
    ADD CONSTRAINT ex_ip_address_ranges_active_no_overlap
    EXCLUDE USING gist (
      cluster_id WITH =,
      (int8range(start_ip, end_ip, '[]')) WITH &&
    )
    WHERE (deleted_at IS NULL);
  ```

  在 Alembic 中经 `op.execute(...)` 落地；`ex_` 不在 `NAMING_CONVENTION` 中，约束名**按字面**使用，不会双重前缀。
- **F-3（保留 `ix_ip_address_ranges_cluster_id`）**：排它约束的 GiST 索引是 **partial**（`WHERE deleted_at IS NULL`）且为多列表达式索引，**不覆盖已删行、不服务 FK 引用完整性检查**。因此仍需保留完整 btree 索引 `ix_ip_address_ranges_cluster_id`（与既有 `ix_ip_addresses_cluster_id` / `ix_bare_metals_cluster_id` 同一模式）。**确认草案已列出，予以保留。**
- **F-4（extension 的 downgrade 行为）**：`btree_gist` 是**首次**引入的 extension（F012 基线约定「不创建 extension」被本 Feature 的已批准 P-02 覆盖）。`CREATE EXTENSION IF NOT EXISTS btree_gist` 在 upgrade 中执行以保证幂等；**downgrade 不得 `DROP EXTENSION`**（extension 是数据库级共享对象，可能被将来其它对象依赖；drop 表即释放本 Feature 的依赖）。`downgrade → upgrade` 因此可重复重建。
- **F-5（部署权限，记录为实施门）**：`CREATE EXTENSION` 需要相应权限。若目标库应用用户无 `CREATE` on database 且未预装扩展，`alembic upgrade` 会失败。Architecture Risk 1 / TQ-1 已给出 **Degraded Design B**（去 `EXCLUDE`，改为对父 Cluster 行串行化 + 应用层重叠校验 + SQL 漂移查询），并声明「Database 阶段如遇扩展不可用，可启用退化路径而无需重新定契约」。**本设计默认按 P-02（EXCLUDE）定稿**；退化路径仅作为部署门记录，见 §13 **Non-blocking OQ-1**，**不构成阻塞**。
- **F-6（ORM 元数据一致性提示）**：Backend 的 ORM 模型须以等价的 `ExcludeConstraint` / `CheckConstraint(name="bounds")` / `Index` 声明，确保 `alembic check` 无漂移。注意 SQLAlchemy 对 exclusion constraint 的 autogenerate 支持有限——**不得**让 autogenerate 误删/重建该约束；以 `pg_constraint` 显式断言为准（V-5）。

结论：**Architecture 草案可直接实现**；本文件按上述定稿给出完整规格。无 `RETURN TO ARCHITECT`。

---

## 3. Migration

| 项 | 值 |
|---|---|
| revision | `0009_f020_ip_address_ranges` |
| down_revision | `0008_f008_services`（当前 head；维持单一线性 head） |
| upgrade | `CREATE EXTENSION IF NOT EXISTS btree_gist` → `CREATE TABLE ip_address_ranges`（7 列 + PK + 1 FK `RESTRICT`/`RESTRICT` + 1 CHECK）→ `ALTER TABLE ... ADD CONSTRAINT ex_ip_address_ranges_active_no_overlap EXCLUDE ...` → `CREATE INDEX ix_ip_address_ranges_cluster_id` |
| downgrade（严格逆序） | `DROP INDEX ix_ip_address_ranges_cluster_id` → `DROP TABLE ip_address_ranges`（连带删除 PK / FK / CHECK / EXCLUDE 及其 backing GiST 索引）。**不 `DROP EXTENSION btree_gist`**（F-4）。 |

`downgrade` 为破坏性操作（丢失全部范围段登记历史），生产环境禁止；仅供开发 / CI 空库验证与重建。

**顺序依据**：`CREATE EXTENSION` 必须先于 `ADD CONSTRAINT ... EXCLUDE`（后者需要 `btree_gist` 提供 `bigint` 的 GiST `=` operator class）；建表本身不依赖扩展。

---

## 4. DDL（完整）

```sql
-- 0) 扩展：GiST 上支持 bigint 等值（本 Feature 首次引入；幂等）
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- 1) 表（7 列）
CREATE TABLE ip_address_ranges (
  id         BIGINT GENERATED ALWAYS AS IDENTITY,
  cluster_id BIGINT      NOT NULL,   -- 归属 Cluster（R-IP-004：恰属一个活跃 Cluster）
  start_ip   BIGINT      NOT NULL,   -- IPv4 canonical 数值（0..4294967295），含端点
  end_ip     BIGINT      NOT NULL,   -- IPv4 canonical 数值（0..4294967295），含端点
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ NULL,       -- 逻辑删除标记（NULL = 活跃）
  CONSTRAINT pk_ip_address_ranges PRIMARY KEY (id),
  CONSTRAINT fk_ip_address_ranges_cluster FOREIGN KEY (cluster_id)
    REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_ip_address_ranges_bounds CHECK (
    start_ip BETWEEN 0 AND 4294967295
    AND end_ip BETWEEN 0 AND 4294967295
    AND start_ip <= end_ip
  )
);

-- 2) 同 Cluster 活跃范围段不得重叠（数据库为最终权威；§21 / R-IP-004）
ALTER TABLE ip_address_ranges
  ADD CONSTRAINT ex_ip_address_ranges_active_no_overlap
  EXCLUDE USING gist (
    cluster_id WITH =,
    (int8range(start_ip, end_ip, '[]')) WITH &&
  )
  WHERE (deleted_at IS NULL);

-- 3) FK 引用完整性检查 + 含已删行的按 Cluster 查询（partial GiST 不能替代）
CREATE INDEX ix_ip_address_ranges_cluster_id
  ON ip_address_ranges (cluster_id);
```

**downgrade DDL（语义）**：

```sql
DROP INDEX ix_ip_address_ranges_cluster_id;
DROP TABLE ip_address_ranges;   -- 连带 PK / FK / CHECK / EXCLUDE 及 backing GiST 索引
-- 不 DROP EXTENSION btree_gist
```

---

## 5. 列清单与约束设计依据

### 5.1 列清单（恰 7 列）

| 列 | 类型 | NULL | 默认 | 业务含义 / 依据 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | 否 | identity | 内部代理主键（ADR-0003）；写操作与寻址用） |
| `cluster_id` | `BIGINT` | 否 | — | 归属 Cluster（R-IP-004「恰属一个 Cluster」；FK） |
| `start_ip` | `BIGINT` | 否 | — | 范围下界，IPv4 canonical 数值（P-01） |
| `end_ip` | `BIGINT` | 否 | — | 范围上界，IPv4 canonical 数值（P-01） |
| `created_at` | `TIMESTAMPTZ` | 否 | `now()` | 登记时间 |
| `updated_at` | `TIMESTAMPTZ` | 否 | `now()` | 最近更新时间（应用层维护，非并发控制依据） |
| `deleted_at` | `TIMESTAMPTZ` | 是 | — | 逻辑删除标记（NULL = 活跃）；**唯一写入路径** `app/deletion/service.py` |

**明确不存在**：`status` / 枚举（Q-002=B 无状态）、`name` / `description` / 用途（R-IP-004 字段封闭）、CIDR / 前缀长度 / IPv6 / 网络地址 / 广播地址 / 网关 / VLAN / DHCP / DNS / 使用率 / 容量 / 分配对象等（非目标），以及 `created_by` / `updated_by` / `version` / `audit`（无需求）。

**类型选择（P-01）**：`start_ip` / `end_ip` 以 `BIGINT` 存 canonical 数值而非 `TEXT` dotted-quad。理由：使排它约束可直接用内建 `int8range` 表达区间交集，且**只保留一份事实**（规范化由应用层 `app/ip_address_ranges/ipv4.py` 的单实现保证，API 层渲染为 dotted-quad）。**代价（事实记录）**：DB 内不能直读 dotted-quad；以本文件与列注释补偿。**不采用**「`TEXT` + `BIGINT` 双列」（需额外一致性 CHECK，引入第二份事实），与 Architecture P-01 定稿一致。

### 5.2 约束清单

| 约束 | 定义 | 依据 |
|---|---|---|
| `pk_ip_address_ranges` | `PRIMARY KEY (id)` | ADR-0003（不可变代理主键，非 `start_ip`/`end_ip`） |
| `fk_ip_address_ranges_cluster` | `FOREIGN KEY (cluster_id) REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT` | R-IP-004 归属必选；R-DELETE-005 不级联；ADR-0004 |
| `ck_ip_address_ranges_bounds` | `CHECK (start_ip BETWEEN 0 AND 4294967295 AND end_ip BETWEEN 0 AND 4294967295 AND start_ip <= end_ip)` | R-IP-004「合法 IPv4」「`start_ip <= end_ip`」的 DB 兜底（§21；R-02） |
| `ex_ip_address_ranges_active_no_overlap` | `EXCLUDE USING gist (cluster_id WITH =, (int8range(start_ip, end_ip, '[]')) WITH &&) WHERE (deleted_at IS NULL)` | R-IP-004「同 Cluster 活跃范围段不重叠、跨 Cluster 可重复」的**最终权威**（R-03；ADR-0002「数据库为最终权威」） |
| `ix_ip_address_ranges_cluster_id` | `INDEX (cluster_id)`（btree） | FK 引用完整性检查 + 按 Cluster 读取（含已删行；partial GiST 不能替代） |

**不建立的约束**（必须如实记录，不得自行发明）：

- **不建** `UNIQUE`（`cluster_id` / `start_ip` / `end_ip` 或组合）：R-IP-004 唯一性语义是「同 Cluster 活跃**不重叠**」，不是「值唯一」；跨 Cluster 允许相同范围。用 `UNIQUE` 会把「不重叠」错误地退化为「端点不得重复」。
- **不建**「范围必须覆盖 / 不覆盖已登记 IP」的 DB 硬约束：DEC-023 第 6 项明确不要求；且无法用当前无触发器 / 无复合外键的 Schema 表达。
- **不建** `start_ip`/`end_ip` 的 dotted-quad 文本格式 CHECK：格式合法性与规范化属应用层（P-03），DB 只保证数值域。
- **不建**任何跨表一致性 CHECK / 生成列（ADR-0002 明确排除「把业务规则藏进 Schema」）。

### 5.3 `int8range` 与排它约束的语义细则

- `int8range(start_ip, end_ip, '[]')` = 闭区间 `[start_ip, end_ip]`（含两端），与 R-IP-004「含两端」一致。
- `&&` 为「区间交集非空」。因 `int8range` 是**离散** range，`[1,10]` 与 `[11,20]` **不相交** → 相接不算重叠（Product NQ-A）。
- `cluster_id WITH =` 保证只比较**同 Cluster** 的行；跨 Cluster 的行 `cluster_id` 不等 → 不冲突。
- `WHERE (deleted_at IS NULL)` 保证**仅活跃行**参与；软删行退出约束判定（R-DELETE-006 类比：软删释放重叠）。
- 并发插入 / 更新重叠的活跃范围：PostgreSQL 排它约束会阻塞并在提交时以 SQLSTATE `23P01` 拒绝后到者（数据库层保证，非应用层）。

---

## 6. 关系

| 关系 | 基数 | 必选 | 数据库实现 | 删除行为 | 允许孤立记录 |
|---|---|---|---|---|---|
| IPAddressRange → Cluster | N:1 | **是**（R-IP-004） | `ip_address_ranges.cluster_id NOT NULL` + FK | `ON DELETE RESTRICT`（不级联）；产品语义的「父删子拦」由应用层事务加锁实现 | 否（`NOT NULL`） |

- **不建立** IPAddressRange → IPAddress 的任何 FK / 载体关系：删除守卫是**派生条件**（字面落在范围内），非参照完整性。
- **不建立** `cluster_id` 到 NIC / BareMetal 的链路外键：Cluster 归属是**直接事实**，无需推导。
- 无其它表以 `ip_address_ranges` 为父（本表是 Cluster 的子资源 / V1 叶子）。

---

## 7. 数据库保证 vs 不保证的 invariant 与回归查询

### 7.1 数据库**真实保证**的 invariant

```text
ip_address_ranges.cluster_id 一定指向物理存在的 clusters 行（FK）
start_ip / end_ip 一定非空，且均在 [0, 4294967295] 内，且 start_ip <= end_ip（NOT NULL + CHECK）
同一 Cluster 内任意两条 deleted_at IS NULL 的范围段区间交集恒为空（EXCLUDE）
跨 Cluster 的相同 / 重叠范围一定被允许（EXCLUDE 含 cluster_id 等值）
deleted_at IS NULL 是「活跃」的唯一判定；软删行不占用「不重叠」约束、不再参与任何排斥
```

### 7.2 数据库**不保证**的 invariant（须应用层 + 回归查询）

1. **「活跃范围段必挂在活跃 Cluster 下」** —— FK 只看物理存在性，看不到 `deleted_at`。
   - 应用层协议：创建/修改对父 Cluster 行取 `FOR SHARE` 并确认活跃（§8）；Cluster 删除守卫包含「存在活跃范围段」（`CLUSTER_ACTIVE_CHILD_CHECKS` 追加 `has_active_ip_address_ranges`）。
   - 回归（必须恒 **0 行**）：

     ```sql
     SELECT count(*) FROM ip_address_ranges r
     JOIN clusters c ON c.id = r.cluster_id
     WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL;
     ```

2. **「每个活跃 IP 必被某个活跃范围覆盖」** —— DEC-023 第 6 项明确**不要求** DB 硬约束；删除守卫与「并发登记新 IP」不互相串行，存在已知并发窗口（Architecture Risk 2）。不引入触发器 / 不修改 F005 写入路径。
   - 漂移检测（应用层 / 测试侧，**不提供端点**）：取某 Cluster 全部活跃 `ip_address`，按 API §7.2 规则解析为 IPv4，数值若不在该 Cluster 任一活跃范围段内即计为漂移；无漂移时期望 **0**。
3. **`ip_address` 的解析语义** —— DB 完全不参与；`ip_addresses.ip_address` 无格式约束（R-IP-004 / AC-23 不变）。不可解析字面值（`abc` / 空串 / 前导空白）在守卫中**跳过**，不得因此 500。

### 7.3 必须纳入回归的查询

```sql
-- R-1 同 Cluster 活跃范围两两不重叠（EXCLUDE 的必然结果）——期望 0 行
SELECT a.id AS a_id, b.id AS b_id
FROM ip_address_ranges a
JOIN ip_address_ranges b
  ON a.cluster_id = b.cluster_id AND a.id < b.id
 AND a.deleted_at IS NULL AND b.deleted_at IS NULL
 AND a.start_ip <= b.end_ip AND a.end_ip >= b.start_ip;

-- R-2 活跃范围挂已软删 Cluster——期望 0 行（§7.2-1）
SELECT count(*) FROM ip_address_ranges r
JOIN clusters c ON c.id = r.cluster_id
WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL;

-- R-3 F005 既有漂移查询——仍期望 0 行（本 Feature 不得使 ip_addresses 漂移）
SELECT ip.id FROM ip_addresses ip
JOIN network_interfaces nic ON nic.id = ip.network_interface_id
JOIN bare_metals bm ON bm.id = nic.bare_metal_id
WHERE ip.cluster_id <> bm.cluster_id;
```

---

## 8. 并发协议（由 Backend 实现；DDL 提供基础）

采用 PostgreSQL 默认 `READ COMMITTED` + 显式行锁（承 `csm-v1-schema-design.md` 关键设计决策 #6），**不引入新死锁序**。

1. **创建（POST）**：同一事务内
   1. `SELECT id FROM clusters WHERE id = :cluster_id AND deleted_at IS NULL FOR SHARE;` 未命中 → `404 NOT_FOUND`（R-01）；
   2. 应用层解析 `start_ip`/`end_ip` 为数值并校验 `start <= end`（否则 `400`）；重叠预检（友好 `409 OVERLAP`）；
   3. `INSERT`；`ex_ip_address_ranges_active_no_overlap` 为最终权威（并发重叠 → `23P01` → `409`）。
2. **修改（PATCH）**：同一事务内
   1. `SELECT ... FROM ip_address_ranges WHERE id = :id AND deleted_at IS NULL FOR UPDATE;` 未命中 → `404`；
   2. 重跑解析 / `start <= end` / 重叠预检；即使预检用 `EXCLUDE` 兜底，**无部分写入**（失败即整事务回滚）；
   3. `UPDATE`；约束重评估。
3. **删除（DELETE）**：委托系统内**唯一**软删路径 `app/deletion/service.py::soft_delete`：
   1. 对目标行 `SELECT ... FOR UPDATE`（`deleted_at IS NULL`；READ COMMITTED 下锁后重评估，竞态软删后到者 `404`）；
   2. 执行 `IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS = (has_active_ip_addresses_in_range,)`：命中活跃 IP → `409 ACTIVE_CHILDREN_EXIST`，**不写 `deleted_at`**；
   3. 仅对已锁定目标行赋 `deleted_at = now()`。

**锁序与死锁分析**：

- 创建：父 Cluster 行 `FOR SHARE` → 新范围段行插入（EXCLUDE 索引内部并发控制）。
- 修改：自身范围段行 `FOR UPDATE` → 读同 Cluster 其它范围行（只读，无锁）。
- 删除范围段：自身范围段行 `FOR UPDATE` → 读 IP 行（只读，无锁）。
- 删除 Cluster：Cluster 行 `FOR UPDATE` → 读活跃子行（BareMetal / 范围段，只读，无锁）。
- 全序恒为 **父 → 子**，无反向持锁，**不新增死锁序**（与 F005 §6 一致）。

**并发结果不变式**：并发「登记范围段」×「删除其 Cluster」恰有一个成功，结束后 R-2 = 0；并发同 Cluster 两条重叠范围至多一条成功（另一条 `409`），无 5xx。

**已知并发窗口（记录，不消除）**：范围段删除与「并发登记落在其范围内的新 IP」不互相串行，极端并发下可能出现「活跃 IP 存在、其范围已被软删」。这不违反任何已确认产品规则（DEC-023 第 6 项），由 §7.2-2 漂移检测发现；**不得**为此修改 F005 写入路径或引入触发器。

---

## 9. Alembic 落地要点与可重复性

**迁移文件**：`backend/migrations/versions/0009_f020_ip_address_ranges.py`，`revision = "0009_f020_ip_address_ranges"`，`down_revision = "0008_f008_services"`。

落地要点（与既有 `0003`–`0008` 风格一致）：

1. `op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")`（幂等）。这是项目**首个** extension；在此显式声明，并记录为部署前置要求。
2. `op.create_table("ip_address_ranges", ...)`：
   - 列用 `sa.BigInteger`（`id` 用 `sa.Identity(always=True)`），时间列 `sa.DateTime(timezone=True)` + `server_default=sa.text("now()")`；
   - `sa.PrimaryKeyConstraint("id", name="pk_ip_address_ranges")`；
   - `sa.ForeignKeyConstraint([...], ["clusters.id"], name="fk_ip_address_ranges_cluster", ondelete="RESTRICT", onupdate="RESTRICT")`；
   - `sa.CheckConstraint("start_ip BETWEEN 0 AND 4294967295 AND end_ip BETWEEN 0 AND 4294967295 AND start_ip <= end_ip", name="bounds")` —— **传裸名 `"bounds"`**，命名约定生成 `ck_ip_address_ranges_bounds`（F-1）。
3. `op.execute("ALTER TABLE ip_address_ranges ADD CONSTRAINT ex_ip_address_ranges_active_no_overlap EXCLUDE USING gist (cluster_id WITH =, (int8range(start_ip, end_ip, '[]')) WITH &&) WHERE (deleted_at IS NULL)")` —— `ex_` 无约定前缀，按字面使用（F-2）。
4. `op.create_index("ix_ip_address_ranges_cluster_id", "ip_address_ranges", ["cluster_id"])`。
5. ORM 模型等价声明 `ExcludeConstraint` / `CheckConstraint(name="bounds")` / `Index`；确认 `alembic check` 无漂移（F-6）。**不得**让 autogenerate 误改该约束。
6. `downgrade()`：`op.drop_index("ix_ip_address_ranges_cluster_id", table_name="ip_address_ranges")` → `op.drop_table("ip_address_ranges")`；**不 `DROP EXTENSION`**（F-4）。

**可重复性**：

- `alembic upgrade head` 对空库一次成功；再次执行 no-op（`alembic_version` 已在 head）。
- `CREATE EXTENSION IF NOT EXISTS` 幂等；extension 已存在时不报错。
- `alembic downgrade 0008_f008_services` 后本表及本 Feature 的约束 / 索引被删除、extension 保留；再 `upgrade head` 一致重建。
- `0001`–`0008` **逐字节未改**；既有表结构（列 / 约束 / 索引）不变。
- `alembic check` 无 schema 漂移。

---

## 10. 对象清单

| 类别 | 数量 | 名称 |
|---|---|---|
| 表 | 1 | `ip_address_ranges` |
| 列 | 7 | `id` / `cluster_id` / `start_ip` / `end_ip` / `created_at` / `updated_at` / `deleted_at` |
| PK | 1 | `pk_ip_address_ranges` |
| FK | 1 | `fk_ip_address_ranges_cluster`（`RESTRICT`/`RESTRICT`） |
| CHECK | 1 | `ck_ip_address_ranges_bounds` |
| EXCLUDE（`contype='x'`） | 1 | `ex_ip_address_ranges_active_no_overlap`（backing GiST 索引同名） |
| 普通索引 | 1 | `ix_ip_address_ranges_cluster_id` |
| Extension | 1 | `btree_gist` |
| CASCADE | **0** | 全部 FK 为 `RESTRICT`/`RESTRICT` |
| 触发器 / 生成列 / `COLLATE` 声明 / 第二条 `deleted_at` 写入路径 | **0** | — |

> `pg_indexes` 中会同时出现 `ex_ip_address_ranges_active_no_overlap`（约束的 backing GiST 索引）与 `ix_ip_address_ranges_cluster_id`；PK 亦产生 backing 索引。结构断言须据此列举，而非只列普通索引。

---

## 11. Verification（实现后必须覆盖）

**结构断言（直连 DB）**

| # | 验证 | 方法 |
|---|---|---|
| V-1 | 列集合**恰为** 7 列；不含 `status` / `name` / `description` / CIDR / 前缀 / IPv6 / 分配类列 | `information_schema.columns` |
| V-2 | PK 恰为 `pk_ip_address_ranges` | `pg_constraint`（`contype='p'`） |
| V-3 | FK 恰为 `fk_ip_address_ranges_cluster`，`confdeltype='r'`、`confupdtype='r'` | `pg_constraint` |
| V-4 | CHECK 恰为 `{ck_ip_address_ranges_bounds}`，定义含两列数值域与 `start_ip <= end_ip` | `pg_constraint`（`contype='c'`） |
| V-5 | 排它约束 `ex_ip_address_ranges_active_no_overlap` 存在（`contype='x'`），`pg_get_constraintdef` 含 `int8range`、`&&`、`cluster_id` 与 `deleted_at IS NULL` | `pg_constraint` |
| V-6 | extension `btree_gist` 存在于当前库 | `pg_extension` |
| V-7 | `ix_ip_address_ranges_cluster_id` 存在；**无** `ux_` 唯一索引 | `pg_indexes` |
| V-8 | 全库无 `confdeltype='c'`（无 CASCADE） | `pg_constraint` |
| V-9 | 无触发器 | `information_schema.triggers`（0 行） |
| V-10 | `ip_address_ranges` 所有列 `collation_name IS NULL` | `information_schema.columns` |

**约束证伪（绕过应用层直连 DB）**

| # | 验证 | 期望 |
|---|---|---|
| V-11 | 同 Cluster 直插两条**活跃**重叠范围（含共享端点） | `23P01` |
| V-12 | 跨 Cluster 直插**完全相同**范围 | **成功**（唯一性边界是 Cluster） |
| V-13 | 直插 `start_ip > end_ip`；`start_ip < 0`；`end_ip > 4294967295` | 均 `23514` |
| V-14 | 软删一条范围后，直插与之重叠的活跃范围 | **成功**（predicate 生效） |
| V-15 | 直插 `cluster_id` 不存在的范围 | `23503`；物理 `DELETE FROM clusters`（其下存在范围段，即使已软删）→ `23503`（`RESTRICT` 非 CASCADE） |
| V-16 | 软删某范围段后，其行仍物理存在、`deleted_at` 非空、`updated_at` 更新；同 Cluster 可重建重叠范围 | 行为断言 |

**不变式回归（恒 0）**

| # | 验证 | 期望 |
|---|---|---|
| V-17 | §7.3 R-1「同 Cluster 活跃范围重叠」 | 0 行 |
| V-18 | §7.3 R-2「活跃范围挂已软删 Cluster」 | 0 行 |
| V-19 | §7.3 R-3 F005 漂移查询 | 0 行 |
| V-20 | §7.2-2 范围覆盖漂移（应用层解析，无漂移时） | 0（检测查询，非端点） |

**并发**

| # | 验证 |
|---|---|
| V-21 | 并发「登记范围段」×「删除其 Cluster」：恰一个成功；结束后 V-18 = 0 |
| V-22 | 并发同 Cluster 两条重叠范围：至多一条成功（另一条 `409 OVERLAP`），无 5xx；结束后 V-17 = 0 |

**Migration**

| # | 验证 |
|---|---|
| V-23 | `alembic upgrade head` 幂等（二次 no-op）；`alembic current` = head |
| V-24 | `alembic downgrade 0008_f008_services` 后本表被删、既有表完好、`btree_gist` 仍在；再 `upgrade head` 一致重建 |
| V-25 | `alembic check` 无漂移 |
| V-26 | `0001`–`0008` 内容逐字节未改；既有表结构不变 |

---

## 12. Backend Contract

Backend 可以依赖以下**由数据库真实保证**的事实：

```text
ip_address_ranges.cluster_id 一定指向物理存在的 clusters 行
start_ip / end_ip 一定非空，且均在 [0, 4294967295] 内，且 start_ip <= end_ip
同一 Cluster 内任意两条 deleted_at IS NULL 的范围段一定不重叠（区间交集为空）
跨 Cluster 的相同 / 重叠范围一定被允许
deleted_at IS NULL 是「活跃」的唯一判定；软删范围段退出不重叠约束
```

Backend **必须自行保证、不得从数据库假设**的事实：

```text
活跃范围段的 cluster_id 一定指向「活跃」Cluster（应用层 FOR SHARE + Cluster 删除守卫保证）
每个活跃 IP 一定被某个活跃范围覆盖（非产品要求；仅由漂移检测观测）
ip_addresses.ip_address 的格式 / 解析（数据库与 F005 均无承诺）
updated_at 是否准确（应用层维护；不得作为审计依据）
```

---

## 13. Open Questions

### Blocking

**无。** 表结构、列、约束、索引、删除行为与 migration 编号均已由 `READY FOR IMPLEMENTATION` 的 Architecture Handoff 与已 Approved ADR 确定，不存在使 Schema 不确定的阻塞项。Handoff Status = `READY FOR DATABASE IMPLEMENTATION`。

### Non-blocking

- **OQ-1（`btree_gist` 部署权限）**：若目标库应用用户无法 `CREATE EXTENSION` 且未预装扩展，`alembic upgrade` 失败。Architecture Risk 1 / TQ-1 已定义 **Degraded Design B**（去 `EXCLUDE`，改为对父 Cluster 行 `FOR UPDATE` / `pg_advisory_xact_lock` 串行化同 Cluster 范围段写入 + 应用层重叠校验 + R-1 漂移查询；API 契约与错误语义不变）。默认按 P-02 实施；如遇扩展不可用，可启用退化路径而**无需重新定契约**（已在 Architecture 定稿）。**记录为部署门，不阻塞本设计。**
- **OQ-2（`int4range` 优化，不采用）**：若将来改用 `CASE`/偏移把数值压入 `int4`，可略减索引体积；当前规模（10⁵、50 并发）无收益，且会让「数值域」与「存储表示」分裂，**不采用**。
- **OQ-3（列注释）**：建议在 ORM / migration 中为 `start_ip` / `end_ip` 加注释「IPv4 canonical 数值 0..4294967295」以补偿 DB 不可直读 dotted-quad（P-01 代价）；属实现细节，不影响 DDL 语义。
- **OQ-4（`alembic check` 对 exclusion constraint 的支持）**：SQLAlchemy autogenerate 对 exclusion constraint 比较支持有限；须以 V-5 显式断言为准，避免 autogenerate 误删重建（F-6）。

---

## 14. 不做什么（本次明确排除）

- 不执行任何 migration、不修改数据库（本文件仅为设计）。
- 不修改 `0001`–`0008`；不修改任何既有表。
- 不引入 `status` / `name` / `description` / CIDR / IPv6 / 使用率 / 容量 / 分配对象等未确认字段。
- 不引入触发器、CASCADE、复合外键、生成列、EAV / 通用资源表 / JSONB。
- 不声明 `COLLATE`、不建 `lower()` 表达式索引。
- 不新增第二条写 `deleted_at` 的路径；不物理删除资源历史。
- 不新增「范围必须覆盖已分配 IP」的 DB 硬约束（DEC-023 第 6 项）。
- 不实现任何 IP 分配 / 占用 / 耗尽 / 冲突扫描 / CIDR / IPv6 语义（F021 范围）。
- 不修改 `ip_addresses` 表结构、R-IP-001~003、§22 大小写语义、F005 `ip_address` 自由文本立场。
