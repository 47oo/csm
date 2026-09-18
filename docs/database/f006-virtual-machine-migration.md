# F006 Database Design — `virtual_machines`

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Feature: F006（E03，P1）
> Author Role: database design（依据已批准 `docs/architecture/f006-virtual-machine-handoff.md` 的 Database Work / 问题 1 规格，未新增任何决策）
> 权威来源：`docs/architecture/f006-virtual-machine-handoff.md`、`docs/api/f006-virtual-machine.md`、`docs/product/handoffs/f006-virtual-machine.md`、ADR-0002 / ADR-0004

---

## 1. 范围

本设计覆盖 **新增一张表** `virtual_machines` 与**一次增量 migration** `0004_f006_virtual_machines`。

- **不改** `0001` / `0002` / `0003` 基线。
- **无**数据迁移（表为首次创建，系统内不存在 VirtualMachine 数据）。
- 无新 extension / database / role；无触发器；无 `COLLATE`；无 CASCADE。

---

## 2. Migration

| 项 | 值 |
|---|---|
| revision | `0004_f006_virtual_machines` |
| down_revision | `0003_f002_bare_metals`（当前 head；维持单一线性 head） |
| upgrade | 一条 `CREATE TABLE` → `CREATE UNIQUE INDEX ux_virtual_machines_name_active` → `CREATE INDEX ix_virtual_machines_bare_metal_id` |
| downgrade（逆序） | `DROP INDEX ix_virtual_machines_bare_metal_id` → `DROP INDEX ux_virtual_machines_name_active` → `DROP TABLE virtual_machines` |

`downgrade` 为破坏性操作（会丢失全部 VirtualMachine 历史），生产环境禁止。

---

## 3. DDL

```sql
CREATE TABLE virtual_machines (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  bare_metal_id BIGINT      NOT NULL,      -- R-VM-005 宿主（必选，恰好一个）
  name          TEXT        NOT NULL,      -- R-VM-004 身份标识
  cpu           TEXT        NULL,           -- R-VM-006 可选，纯文本
  memory        TEXT        NULL,
  disk          TEXT        NULL,
  os            TEXT        NULL,
  hypervisor    TEXT        NULL,           -- 仅文本登记字段，不代表平台接入
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
  ON virtual_machines (bare_metal_id);                       -- FK 检查 + 按宿主读取
```

列集合**恰为 12 列**；`CHECK` 集合**为空**。

---

## 4. 约束与设计依据

| 约束 / 索引 | 定义 | 依据 |
|---|---|---|
| `pk_virtual_machines` | `PRIMARY KEY (id)` | ADR-0003：`id` 为规范路径与写操作标识 |
| `fk_virtual_machines_bare_metal` | `FOREIGN KEY (bare_metal_id) REFERENCES bare_metals (id) ON DELETE RESTRICT ON UPDATE RESTRICT` | R-VM-005 绑定必选；R-DELETE-005 不级联；ADR-0004 |
| `ux_virtual_machines_name_active` | `UNIQUE (name) WHERE deleted_at IS NULL` | R-VM-004 全局活跃唯一；R-DELETE-006 软删释放 |
| `ix_virtual_machines_bare_metal_id` | `INDEX (bare_metal_id)` | FK 引用检查与按宿主读取（F006 `?bare_metal_id=`、F010 复用） |

**明确不添加**（未确认或已排除）：

- `status` 列 / 状态枚举 / 默认值 → Q-002=B（VirtualMachine 在 V1 不设状态）。
- `cluster_id` 列 → R-VM-005（Cluster 归属由宿主推导，不单独记录）。
- `name` 的长度 / 首尾空白 / 空串 / 字符 / `/` 约束 → 未定义（Product Handoff 假设 6 / NQ-5）。
- `lower(name)` 唯一索引 / `COLLATE` → 会改变大小写敏感语义（R-VM-004、§22、ADR-0002）。
- `ON DELETE CASCADE` / 触发器 → R-DELETE-005 / ADR-0004。
- NIC / IP / Container / Service 结构、DataCenter / 位置字段、平台凭据 / 外部 id / 同步字段 → R-VM-002、§6、§13、§23。

**类型选择**：六个可选字段使用 `TEXT`（R-VM-006 明确「纯文本、不结构化」，不得引入单位 / 容量归一或结构化拆分）。`name` 使用 `TEXT` 且无 CHECK（未定义约束）。

**大小写敏感**：依赖数据库默认（大小写敏感）collation 的普通等值比较与 partial unique index；**不声明 `COLLATE`**、**不使用 `lower()`**（ADR-0002 §2）。

---

## 5. 并发协议（由 Backend 实现，DDL 提供基础）

1. 创建 VirtualMachine：对宿主 BareMetal 行取 `FOR SHARE`，并在同一事务内确认 `bare_metals.deleted_at IS NULL`；未命中 → `404`。
2. 删除宿主 BareMetal：对自身行取 `FOR UPDATE`，再检查活跃子资源（`BARE_METAL_ACTIVE_CHILD_CHECKS`，F006 后包含活跃 VirtualMachine 检查）。
3. 不变式：并发结束后不存在「宿主已删 + VM 活跃」的记录。

`fk_virtual_machines_bare_metal` 的 `RESTRICT` 是第二道防线（宿主无物理删除路径，故应用路径不触发）。

---

## 6. 验证（Verification）

| # | 验证 | 方法 |
|---|---|---|
| V-1 | 列集合恰为 12 列，且不含 `status` / `cluster_id` | 查询 `information_schema.columns` |
| V-2 | 主键恰为 `pk_virtual_machines` | `pg_constraint` |
| V-3 | FK 恰为 `fk_virtual_machines_bare_metal`，`confdeltype='r'`、`confupdtype='r'` | `pg_constraint` |
| V-4 | 全库无 `confdeltype='c'`（无 CASCADE） | `pg_constraint` |
| V-5 | `ux_virtual_machines_name_active` 为 `UNIQUE` 且 `indexdef` 含 `WHERE (deleted_at IS NULL)` | `pg_indexes` |
| V-6 | `ix_virtual_machines_bare_metal_id` 存在 | `pg_indexes` |
| V-7 | `virtual_machines` 所有列 `collation_name IS NULL` | `information_schema.columns` |
| V-8 | 无触发器 | `information_schema.triggers` |
| V-9 | 直连插入重复活跃 `name` → `23505`；插入指向不存在宿主的行 → `23503` | psycopg 异常 |
| V-10 | soft delete 后同一 `name` 可再次插入活跃行 | 行为断言 |
| V-11 | `alembic upgrade head` ×2 幂等；`downgrade base` → `upgrade head` 可重建 | alembic |
| V-12 | `alembic downgrade 0003_f002_bare_metals` 后表被删、既有表完好 | alembic + 结构断言 |
| V-13 | `alembic check` 无 schema 漂移 | alembic |
| V-14 | 既有表 `clusters` / `users` / `sessions` / `bare_metals` 结构与本 migration 之前一致 | 结构断言 |

---

## 7. 与既有表的关系

- `virtual_machines.bare_metal_id → bare_metals.id`：N:1，必选，`RESTRICT`。
- 无其它外键；不引用 `clusters`（Cluster 归属由宿主推导）。
- 新增表不改变任何既有表的列 / 约束 / 索引。

---

## 8. 文档同步状态

- `docs/database/csm-v1-schema-design.md`：VirtualMachine→BareMetal 关系行已由「未确认」更新为 N:1 mandatory；「反规范化 `cluster_id`」注记已标注为已关闭。
- `docs/database/f012-baseline-migration.md`：revision 表加入 `0004`（建议，非阻塞）。

GIT: NONE
