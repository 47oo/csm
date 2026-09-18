# F007 Database Design — `containers`

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Feature: F007（E03，P1）
> Author Role: database design（依据已批准 `docs/architecture/f007-container-handoff.md` 的 Data Layer Impact / §1 裁定，**未新增任何决策**）
> 权威来源：`docs/architecture/f007-container-handoff.md`、`docs/api/f007-container.md`、`docs/product/handoffs/f007-container.md`、ADR-0002 / ADR-0004、`docs/database/csm-v1-schema-design.md`

---

## 1. 范围

覆盖 **新增一张表** `containers` 与**一次增量 migration** `0007_f007_containers`。

- **不改** `0001`–`0006`。
- **无**数据迁移（表为首次创建，系统内不存在 Container 数据）。
- 无新 extension / database / role；无触发器；无生成列；无 `COLLATE`；无 CASCADE；无复合外键。
- **本表是本次唯一新增的表**；不改变任何既有表的列 / 约束 / 索引。

---

## 2. Migration

| 项 | 值 |
|---|---|
| revision | `0007_f007_containers` |
| down_revision | `0006_f005_ip_addresses`（当前 head；维持单一线性 head） |
| upgrade | `CREATE TABLE containers`（11 列 + PK + **1 CHECK** + 2 FK `RESTRICT`/`RESTRICT`）→ `CREATE UNIQUE INDEX ux_containers_bare_metal_name_active` → `CREATE UNIQUE INDEX ux_containers_virtual_machine_name_active` → `CREATE INDEX ix_containers_bare_metal_id` → `CREATE INDEX ix_containers_virtual_machine_id` |
| downgrade（严格逆序） | `DROP INDEX ix_containers_virtual_machine_id` → `DROP INDEX ix_containers_bare_metal_id` → `DROP INDEX ux_containers_virtual_machine_name_active` → `DROP INDEX ux_containers_bare_metal_name_active` → `DROP TABLE containers` |

`downgrade` 为破坏性操作（丢失全部 Container 登记历史），生产环境禁止。

---

## 3. DDL

```sql
CREATE TABLE containers (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY,
  bare_metal_id      BIGINT      NULL,   -- 载体二选一（其一）
  virtual_machine_id BIGINT      NULL,   -- 载体二选一（其一）
  name               TEXT        NOT NULL,
  image              TEXT        NULL,
  cpu                TEXT        NULL,
  memory             TEXT        NULL,
  owner              TEXT        NULL,
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
  ON containers (bare_metal_id, name)
  WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX ux_containers_virtual_machine_name_active
  ON containers (virtual_machine_id, name)
  WHERE deleted_at IS NULL;

CREATE INDEX ix_containers_bare_metal_id
  ON containers (bare_metal_id);

CREATE INDEX ix_containers_virtual_machine_id
  ON containers (virtual_machine_id);
```

---

## 4. 列清单（11 列）

| 列 | 类型 | NULL | 说明 |
|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | 否 | 代理主键 |
| `bare_metal_id` | `BIGINT` | **是** | 载体之一；与 `virtual_machine_id` **恰好一个非空** |
| `virtual_machine_id` | `BIGINT` | **是** | 载体之一 |
| `name` | `TEXT` | 否 | 身份标识；**无长度 / trim / 字符 CHECK** |
| `image` | `TEXT` | 是 | R-CONTAINER-004；**未登记为 NULL** |
| `cpu` | `TEXT` | 是 | 纯文本，不拆数量与单位 |
| `memory` | `TEXT` | 是 | 纯文本 |
| `owner` | `TEXT` | 是 | 纯文本 |
| `created_at` | `TIMESTAMPTZ` | 否 | `DEFAULT now()` |
| `updated_at` | `TIMESTAMPTZ` | 否 | 应用层维护 |
| `deleted_at` | `TIMESTAMPTZ` | 是 | 软删标记；**唯一写入路径为 `app/deletion/service.py`** |

**明确不存在**：`status`（Q-002=B 无状态）、`cluster_id` / 任何 Cluster 维度列（R-CONTAINER-002 归属由载体推导）、K8s / Docker / Runtime / 外部平台 id / 凭据列、DataCenter / 位置列、`carrier_type` 判别列（见 §5）。

---

## 5. 关键设计说明

### 5.1 多态载体：两列可空 FK + `num_nonnulls` CHECK（架构 §1 裁定）

不引入 `carrier_type` 判别列，而用两列可空 FK：

- **恰好一个**由 `ck_containers_carrier_exactly_one` 在数据库层保证：`num_nonnulls(bare_metal_id, virtual_machine_id) = 1`。0 个（无载体）与 2 个（多载体）均被拒绝。
- **两条 FK 均保留**（`RESTRICT`/`RESTRICT`）：载体是否物理存在由数据库保证，且无 `ON DELETE CASCADE`（R-DELETE-005）。这是否决「判别列 + 无 FK」方案的决定性理由——该方案会放弃数据库级参照完整性，违反 `AGENTS.md` §6 与 ADR-0002。
- **不引入生成列 / ORM 多态 / STI / 触发器等**：两列都是普通标量列。

**结构性 NULL 是设计的一部分，不是缺陷**：任一时刻恰有一列为 NULL，由 CHECK 保证。该形态不进任何部分索引的 key 误判（见 §5.2）。

### 5.2 载体内 `name` 唯一：每载体列一条 partial unique index

`name` 的唯一性边界是**运行载体**，不是全局、也不是 Cluster（R-CONTAINER-003）。

因本设计没有单一载体判别列，唯一性由**两条**部分唯一索引表达：

- `ux_containers_bare_metal_name_active`：`(bare_metal_id, name) WHERE deleted_at IS NULL`
- `ux_containers_virtual_machine_name_active`：`(virtual_machine_id, name) WHERE deleted_at IS NULL`

两者合起来语义等价于架构要求的 `(载体类型, 载体标识, name) WHERE deleted_at IS NULL`。

**为什么两条索引不会互相干扰**：CHECK 保证每行恰有一列非空、另一列为 NULL，而 PostgreSQL 唯一索引中 **NULL 互不相等**。因此：

- 载体为 BareMetal 的行，在 VM 索引中的 key 为 `(NULL, name)`，恒不参与冲突；
- 反之亦然。

**由此自动成立的关键语义**：

- **AC-15（跨载体类型同数值 id 不冲突）**：BareMetal `id=5` 与 VM `id=5` 上同名 `web` 分属两条不同索引，均合法。载体身份 =（类型, 标识）二元组，**无需额外机制**。
- **AC-13 / AC-14（不同载体可重名）**：同类型不同 id 亦不冲突。
- **AC-17（大小写敏感）**：**不声明 `COLLATE`、不使用 `lower()`**；依赖数据库默认（大小写敏感）collation，与 Cluster / BareMetal / VM 一致（§22、ADR-0002）。
- **AC-19（软删释放唯一性）**：predicate `deleted_at IS NULL` 使已软删行退出索引。

### 5.3 无 Cluster 维度

**不加 `cluster_id`**。Container 的 Cluster 归属由载体推导（BareMetal → 其 Cluster；VM → 其宿主 BareMetal → 其 Cluster），R-CONTAINER-002 明确**不单独记录**。

> 与 F005 `ip_addresses` 的反规范化 `cluster_id` 形成对照：F005 之所以落 `cluster_id`，是因为其唯一性边界**是 Cluster**（同 Cluster 内 IP 唯一），必须有该列才能建索引。F007 的唯一性边界是**载体**，载体两列已在表内，**不需要**任何 Cluster 列。**不得**照搬 F005 模式。

### 5.4 未定义约束不落 CHECK

**本表恰有 1 个 CHECK**（载体的 `num_nonnulls`），**无需任何其它 CHECK**：

- `name` 与 `image` / `cpu` / `memory` / `owner` 的长度 / trim / 空串 / 字符 / `/` / 格式规则**均未确认**（NQ-4）→ **不建任何 CHECK**，不 agent 自创。
- 「长期服务型 vs 短生命周期」**无可判别字段**（NQ-5）→ **不引入**任何判别列或 CHECK。
- 已确认的大小写敏感**不**需要 CHECK（那是 collation 行为，已由 ADR-0002 保证）。

> 明确的后果（是事实，不是规则）：在当前已确认规则下，空串 `name` 与含首尾空白的 `name` **不会被数据库拒绝**。这**不得**被解读为「已确认空 `name` 合法」。

### 5.5 与 F014 的关系

- `deleted_at` 的**唯一**写入路径是 `app/deletion/service.py`（ADR-0004 allow-list guard 固定）；本表不新增第二条路径。
- **父删子拦**：活跃 Container 会阻止删除其载体。这**不需要本表上的任何额外约束**——由应用层声明的活跃子检查实现（`BARE_METAL_ACTIVE_CHILD_CHECKS` / `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 含活跃 Container 检查）。
- 两条 FK 的 `RESTRICT` 是绕过应用层时的第二道防线。
- **并发孤立记录不变式**（AC-36 / AC-37）：并发「创建 Container」与「删除其载体」结束后，下列查询必须为 **0 行**：

  ```sql
  SELECT count(*) FROM containers c
  JOIN bare_metals bm ON bm.id = c.bare_metal_id
  WHERE c.deleted_at IS NULL AND bm.deleted_at IS NOT NULL;

  SELECT count(*) FROM containers c
  JOIN virtual_machines vm ON vm.id = c.virtual_machine_id
  WHERE c.deleted_at IS NULL AND vm.deleted_at IS NOT NULL;
  ```

  由「创建侧对载体行取 `FOR SHARE` 并同事务确认活跃」+「删除侧对自身行 `FOR UPDATE` 后再检查活跃子」共同保证（ADR-0004 §5）。这是**应用层协议**，数据库不能单独保证；测试必须真实并发验证。

---

## 6. 对象清单（交付验收）

| 类别 | 数量 | 名称 |
|---|---|---|
| 表 | 1 | `containers` |
| 列 | 11 | 见 §4 |
| 约束 | 4 | `pk_containers`、`ck_containers_carrier_exactly_one`、`fk_containers_bare_metal`、`fk_containers_virtual_machine` |
| 索引 | 4 | `ux_containers_bare_metal_name_active`、`ux_containers_virtual_machine_name_active`、`ix_containers_bare_metal_id`、`ix_containers_virtual_machine_id` |
| CHECK | 1 | 仅 `ck_containers_carrier_exactly_one` |
| CASCADE | **0** | 全部 FK 为 `RESTRICT`/`RESTRICT` |
| 触发器 / 生成列 / extension | **0** | — |
| `COLLATE` 声明 | **0** | — |

---

## 7. 验证方法（Tester 必须覆盖）

**绕开应用层直连数据库**（数据库为最终权威，ADR-0002）：

- [ ] 同载体插入重复活跃 `(载体, name)` → `23505`（两条索引分别验证 BareMetal 与 VM 载体）。
- [ ] 跨载体类型同名（含两类型 id 数值相同）→ **成功**（AC-15；证明两索引互不干扰，是本次设计的核心不变式）。
- [ ] 同类型不同载体 id 同名 → **成功**（AC-14）。
- [ ] 同载体 `web` 与 `WEB` → **共存**（AC-17；证明无大小写折叠）。
- [ ] `name` 为空串、含首尾空白 → **不被拒绝**（AC-11；同时断言**不存在**其它 CHECK，防止隐性约束）。
- [ ] 软删后同载体重建同名 → **成功**，且旧行 `deleted_at` 未被改写（AC-19）。
- [ ] **0 个载体**（两列均 NULL）→ `23514`。
- [ ] **2 个载体**（两列均非空）→ `23514`。
- [ ] 引用不存在载体的 id → `23503`；**尝试物理删除有 Container 的载体行 → `23503`**（证明 `RESTRICT` 而非 CASCADE）。
- [ ] 断言 `containers` 表**不存在** `status` / `cluster_id` 列（AC-21 / AC-23）。
- [ ] 并发孤立记录不变式 = 0 行（AC-36 / AC-37，真实并发，不得 mock）。

**Migration 层面**：

- [ ] `alembic upgrade head` 幂等（重复执行无副作用）；head 为 `0007_f007_containers`。
- [ ] `alembic downgrade 0006` 可逆，再 `upgrade head` 回到一致状态。
- [ ] `alembic check` 无漂移（ORM 元数据与 migration 一致）。
- [ ] `0001`–`0006` 内容**逐字节未改**；既有表结构（列 / 约束 / 索引）不变。
- [ ] 无 `COLLATE` / 无 `lower()` / 无 CASCADE / 无触发器 / 无生成列（可失败静态断言）。

---

## 8. 文档同步（本 Feature 已执行）

以 CONFIRMED 规则为准，更正陈旧记载：

- `docs/database/csm-v1-schema-design.md`：`Container → 载体` 由 `UNCONFIRMED` / 「不得固化为 `NOT NULL`」更正为**已确认必选且恰好一个**，并记录本表设计；`containers` 由「本次不设计」更正为 F007 交付。
- `docs/database/f012-baseline-migration.md`：revision 树与 `0007_f007_containers` 小节。

---

## 9. 不做什么（本次明确排除）

- 不执行任何 migration、不修改数据库（本文件仅为设计）。
- 不修改 `0001`–`0006`。
- 不引入 `status` / `cluster_id` / K8s / Docker / Runtime / 位置列。
- 不引入 CASCADE、触发器、生成列、EAV、JSONB、ORM 多态 / STI / 通用资源表。
- 不为 `name` 或四个可选字段建任何长度 / trim / 空串 / 字符 / 格式 CHECK，也不引入「长期服务型」判别列。
- 不声明 `COLLATE`、不使用 `lower()`。
- 不新增第二条写 `deleted_at` 的路径。
- 不新增 extension / database / role / locale 变更。
