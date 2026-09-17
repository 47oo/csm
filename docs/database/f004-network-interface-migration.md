# F004 Database Design — `network_interfaces`

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Feature: F004（E02，P1）
> Author Role: database design（依据已批准 `docs/architecture/f004-network-interface-handoff.md` 的 Database Work / 决策 1 规格，未新增任何决策）
> 权威来源：`docs/architecture/f004-network-interface-handoff.md`、`docs/api/f004-network-interface.md`、`docs/product/handoffs/f004-network-interface.md`、ADR-0002 / ADR-0004

---

## 1. 范围

覆盖 **新增一张表** `network_interfaces` 与**一次增量 migration** `0005_f004_network_interfaces`。

- **不改** `0001` / `0002` / `0003` / `0004`。
- **无**数据迁移（表为首次创建，系统内不存在 NIC 数据）。
- 无新 extension / database / role；无触发器；无 `COLLATE`；无 CASCADE。

---

## 2. Migration

| 项 | 值 |
|---|---|
| revision | `0005_f004_network_interfaces` |
| down_revision | `0004_f006_virtual_machines`（当前 head；维持单一线性 head） |
| upgrade | 一条 `CREATE TABLE`（8 列 + PK + FK RESTRICT + 两个 CHECK）→ `CREATE INDEX ix_network_interfaces_bare_metal_id` |
| downgrade（逆序） | `DROP INDEX ix_network_interfaces_bare_metal_id` → `DROP TABLE network_interfaces` |

`downgrade` 为破坏性操作（会丢失全部 NIC 登记历史），生产环境禁止。

---

## 3. DDL

```sql
CREATE TABLE network_interfaces (
  id              BIGINT GENERATED ALWAYS AS IDENTITY,
  bare_metal_id   BIGINT      NOT NULL,   -- R-NIC-003 父（必选，恰好一个）
  name            TEXT        NOT NULL,   -- 接口名（eth0 / ib0 …）；无长度 / trim / 字符约束
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

列集合**恰为 8 列**。**唯一索引集合为空**。

---

## 4. 约束与设计依据

| 约束 / 索引 | 定义 | 依据 |
|---|---|---|
| `pk_network_interfaces` | `PRIMARY KEY (id)` | ADR-0003：`id` 为规范路径与写操作标识 |
| `fk_network_interfaces_bare_metal` | `FOREIGN KEY (bare_metal_id) REFERENCES bare_metals (id) ON DELETE RESTRICT ON UPDATE RESTRICT` | R-NIC-003 绑定必选；R-DELETE-005 不级联；ADR-0004 |
| `ck_network_interfaces_technology_type` | `CHECK (technology_type IN ('Ethernet','InfiniBand','RoCE','Other'))` | R-NIC-001 封闭枚举；§21 数据库为最终权威 |
| `ck_network_interfaces_purpose` | `CHECK (purpose IN ('BMC','Management','Business','Compute','Storage','DataTransfer','Other'))` | R-NIC-002 封闭枚举；§21 |
| `ix_network_interfaces_bare_metal_id` | `INDEX (bare_metal_id)` | FK 引用检查与按宿主读取（F004 `?bare_metal_id=`、F010 复用） |

**明确不添加**（未确认或已排除）：

- **任何唯一性约束**（含 `UNIQUE (bare_metal_id, name)` 与 partial unique 形式）→ NIC 名称唯一性**未确认**（NQ-2）；未确认时默认行为是「不实现」。
- `status` 列 / 状态枚举 → Q-002=B。
- `cluster_id` 列 → Cluster 归属由宿主推导。
- IP / `ip_address` / `prefix_len` 列 → 归 F005。
- `mac` / `mac_address` / `speed` / `rate` / `mtu` / `port` / `module` / `transceiver` 列 → §23 未确认字段。
- `vm_id` / `virtual_machine_id` / `container_id` / `service_id` / `carrier_type` 列 → NQ-1 未确认，不得预留。
- `name` 的长度 / 首尾空白 / 空串 / 字符 / `/` 约束 → 未定义约束。
- `ON DELETE CASCADE` / 触发器 → R-DELETE-005 / ADR-0004。

**类型选择**：三个文本列使用 `TEXT`，与既有资源表一致；枚举用 `TEXT + CHECK` 而非 PostgreSQL `ENUM`（ADR-0002 已裁定，变更成本可控）。

---

## 5. 并发协议（由 Backend 实现，DDL 提供基础）

1. 创建 NetworkInterface：对父 BareMetal 行取 `FOR SHARE`，并在同一事务内确认 `bare_metals.deleted_at IS NULL`；未命中 → `404`。
2. 删除父 BareMetal：对自身行取 `FOR UPDATE`，再检查活跃子资源（`BARE_METAL_ACTIVE_CHILD_CHECKS`，F004 后**同时**包含活跃 VirtualMachine 与活跃 NetworkInterface 检查）。
3. 不变式：并发结束后不存在「父已删 + NIC 活跃」的记录。

`fk_network_interfaces_bare_metal` 的 `RESTRICT` 是第二道防线（宿主无物理删除路径，故应用路径不触发）。

---

## 6. 验证（Verification）

| # | 验证 | 方法 |
|---|---|---|
| V-1 | 列集合恰为 8 列，且不含 `status` / IP / MAC / 速率 / MTU / 载体列 | `information_schema.columns` |
| V-2 | 主键恰为 `pk_network_interfaces` | `pg_constraint` |
| V-3 | FK 恰为 `fk_network_interfaces_bare_metal`，`confdeltype='r'`、`confupdtype='r'` | `pg_constraint` |
| V-4 | 全库无 `confdeltype='c'`（无 CASCADE） | `pg_constraint` |
| V-5 | CHECK 集合恰为 `{ck_network_interfaces_technology_type, ck_network_interfaces_purpose}`，且取值逐字匹配 R-NIC-001/002 | `pg_constraint` |
| V-6 | `ix_network_interfaces_bare_metal_id` 存在 | `pg_indexes` |
| V-7 | **唯一索引集合为空**（`pg_indexes` 无 `ux_`、无 `unique` 索引） | `pg_indexes` |
| V-8 | `network_interfaces` 所有列 `collation_name IS NULL` | `information_schema.columns` |
| V-9 | 无触发器 | `information_schema.triggers` |
| V-10 | 直连插入非法 `technology_type` / `purpose` → `23514`；插入指向不存在宿主的行 → `23503` | psycopg 异常 |
| V-11 | 直连插入同宿主同名两行 → **成功**（无唯一性约束） | 行为断言 |
| V-12 | `alembic upgrade head` ×2 幂等；`downgrade base` → `upgrade head` 可重建 | alembic |
| V-13 | `alembic downgrade 0004_f006_virtual_machines` 后本表被删、既有表完好 | alembic + 结构断言 |
| V-14 | `alembic check` 无 schema 漂移 | alembic |
| V-15 | 既有表 `clusters` / `users` / `sessions` / `bare_metals` / `virtual_machines` 结构与本 migration 之前一致 | 结构断言 |

---

## 7. 与既有表的关系

- `network_interfaces.bare_metal_id → bare_metals.id`：N:1，必选，`RESTRICT`。
- 无其它外键；不引用 `clusters`（Cluster 归属由宿主推导）。
- 新增表不改变任何既有表的列 / 约束 / 索引。
- 本表是 **F005 `ip_addresses` 的父**（`ip_addresses.network_interface_id` 必选），因此 Backend 需声明 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`（当前显式空元组）供 F005 追加。

---

## 8. 文档同步状态

- `docs/database/csm-v1-schema-design.md`：`network_interfaces` 段已补 migration 版本 `0005_f004_network_interfaces` 与「无唯一性约束」说明。
- `docs/database/f012-baseline-migration.md`：§3 revision 序列已更新为 `0003 → 0004_f006_virtual_machines → 0005_f004_network_interfaces → 0006_f005_ip_addresses`；§4 DDL 小节名已改号为 `0005_f004_network_interfaces`。

GIT: NONE
