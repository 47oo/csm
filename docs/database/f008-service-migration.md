# F008 Database Design — `services` 与 `service_carriers`

> Status: `READY FOR DATABASE IMPLEMENTATION`
> Feature: F008（E04，P1）
> Author Role: database design（依据已批准 `docs/architecture/f008-service-handoff.md` 的 Data Layer Impact / §1 / §2 / §8 规格，**未新增任何决策**）
> 权威来源：`docs/architecture/f008-service-handoff.md`、`docs/api/f008-service.md`、`docs/product/handoffs/f008-service.md`、`requirements.md` §14（R-SVC-001~009，含「V1 不提供解除绑定能力」）、ADR-0002 / ADR-0004、`docs/database/csm-v1-schema-design.md`

---

## 1. 范围

覆盖 **新增两张表**（`services`、`service_carriers`）与**一次增量 migration** `0008_f008_services`。

- **不改** `0001`–`0007`。
- **无**数据迁移（两表均为首次创建，系统内不存在 Service 与绑定数据）。
- 无新 extension / database / role；无触发器；无生成列；无 `COLLATE`；无 CASCADE；无复合外键。
- **本表是本次仅有的两张新增表**；不改变任何既有表的列 / 约束 / 索引。

---

## 2. Migration

| 项 | 值 |
|---|---|
| revision | `0008_f008_services` |
| down_revision | `0007_f007_containers`（当前 head；维持单一线性 head） |
| upgrade | `CREATE TABLE services`（11 列 + PK，**0 个 CHECK**）→ `CREATE UNIQUE INDEX ux_services_name_active` → `CREATE TABLE service_carriers`（5 列 + PK + **1 CHECK** + 4 FK `RESTRICT`/`RESTRICT`）→ 3 条 partial unique → 3 条载体列索引 → 1 条 `service_id` 索引 |
| downgrade（严格逆序） | `DROP INDEX ix_service_carriers_service_id` → 3 条 `ix_service_carriers_<carrier>_id` → 3 条 `ux_service_carriers_service_<carrier>` → `DROP TABLE service_carriers` → `DROP INDEX ux_services_name_active` → `DROP TABLE services` |

`downgrade` 为破坏性操作（丢失全部 Service 登记与绑定历史），生产环境禁止。

---

## 3. DDL

```sql
CREATE TABLE services (
  id           BIGINT GENERATED ALWAYS AS IDENTITY,
  name         TEXT        NOT NULL,
  service_type TEXT        NULL,
  url          TEXT        NULL,
  port         TEXT        NULL,
  protocol     TEXT        NULL,
  owner        TEXT        NULL,
  description  TEXT        NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ NULL,
  CONSTRAINT pk_services PRIMARY KEY (id)          -- 无 CHECK、无其它约束
);

CREATE UNIQUE INDEX ux_services_name_active
  ON services (name)
  WHERE deleted_at IS NULL;

CREATE TABLE service_carriers (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY,
  service_id         BIGINT NOT NULL,
  bare_metal_id      BIGINT NULL,   -- 载体三选一（其一）
  virtual_machine_id BIGINT NULL,   -- 载体三选一（其一）
  container_id       BIGINT NULL,   -- 载体三选一（其一）
  CONSTRAINT pk_service_carriers PRIMARY KEY (id),
  CONSTRAINT ck_service_carriers_exactly_one_carrier
    CHECK (num_nonnulls(bare_metal_id, virtual_machine_id, container_id) = 1),
  CONSTRAINT fk_service_carriers_service FOREIGN KEY (service_id)
    REFERENCES services (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_service_carriers_bare_metal FOREIGN KEY (bare_metal_id)
    REFERENCES bare_metals (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_service_carriers_virtual_machine FOREIGN KEY (virtual_machine_id)
    REFERENCES virtual_machines (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_service_carriers_container FOREIGN KEY (container_id)
    REFERENCES containers (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

-- 集合语义：同一 Service 内不得重复绑定同一载体（每载体列一条 partial unique）
CREATE UNIQUE INDEX ux_service_carriers_service_bare_metal
  ON service_carriers (service_id, bare_metal_id)
  WHERE bare_metal_id IS NOT NULL;

CREATE UNIQUE INDEX ux_service_carriers_service_virtual_machine
  ON service_carriers (service_id, virtual_machine_id)
  WHERE virtual_machine_id IS NOT NULL;

CREATE UNIQUE INDEX ux_service_carriers_service_container
  ON service_carriers (service_id, container_id)
  WHERE container_id IS NOT NULL;

-- 按载体反查 Service（AC-17 / AC-19 / AC-31）
CREATE INDEX ix_service_carriers_bare_metal_id      ON service_carriers (bare_metal_id);
CREATE INDEX ix_service_carriers_virtual_machine_id ON service_carriers (virtual_machine_id);
CREATE INDEX ix_service_carriers_container_id       ON service_carriers (container_id);

-- Service 的载体集合装配（AC-16）
CREATE INDEX ix_service_carriers_service_id         ON service_carriers (service_id);
```

---

## 4. 列清单

### 4.1 `services`（11 列）

| 列 | 类型 | NULL | 说明 |
|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | 否 | 代理主键 |
| `name` | `TEXT` | 否 | 身份标识；**全局**活跃唯一、大小写敏感；**无长度 / trim / 字符 CHECK** |
| `service_type` | `TEXT` | 是 | 可选纯文本；**不是**封闭枚举 |
| `url` | `TEXT` | 是 | 可选纯文本；**无 URL 格式校验** |
| `port` | `TEXT` | 是 | 可选纯文本；**无数字 / 范围校验** |
| `protocol` | `TEXT` | 是 | 可选纯文本 |
| `owner` | `TEXT` | 是 | 可选纯文本 |
| `description` | `TEXT` | 是 | 可选纯文本（含换行不处理） |
| `created_at` | `TIMESTAMPTZ` | 否 | `DEFAULT now()` |
| `updated_at` | `TIMESTAMPTZ` | 否 | 应用层维护 |
| `deleted_at` | `TIMESTAMPTZ` | 是 | 软删标记；**唯一写入路径为 `app/deletion/service.py`** |

**明确不存在**：`status` / `state`（Q-002=B 无状态）、`cluster_id` / `cluster` / `cluster_name`（R-SVC-004/006 归属由载体推导）、凭据 / 密钥 / 外部平台 id、健康 / 监控 / 最后上报、DataCenter / 位置、任何载体列。

### 4.2 `service_carriers`（5 列）

| 列 | 类型 | NULL | 说明 |
|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | 否 | 代理主键（三列载体均可空，无法作 PK 列） |
| `service_id` | `BIGINT` | 否 | 所属 Service；FK `RESTRICT` |
| `bare_metal_id` | `BIGINT` | **是** | 载体三选一；FK `RESTRICT` |
| `virtual_machine_id` | `BIGINT` | **是** | 载体三选一；FK `RESTRICT` |
| `container_id` | `BIGINT` | **是** | 载体三选一；FK `RESTRICT` |

**明确不存在**：`deleted_at`、`created_at`、`updated_at`、任何判别列（`carrier_type`）。

**这不是资源表，而是关系表**：它不承载独立的资源事实，而只承载「某个 Service 绑定某个运行载体」这一关系；因此**没有软删列、也没有时间戳**。绑定行**只在登记时 INSERT**，**永不 UPDATE / DELETE**。

---

## 5. 关键设计说明

### 5.1 N:M 多态绑定：单表 + 三列可空 FK + `num_nonnulls` CHECK（架构 §1 裁定）

不引入 `carrier_type` 判别列，而用三列可空 FK：

- **恰好一个载体**由 `ck_service_carriers_exactly_one_carrier` 在数据库层保证：`num_nonnulls(bare_metal_id, virtual_machine_id, container_id) = 1`。0 个（无载体）与 ≥2 个（多载体于同一行）均被拒绝。
- **四条 FK 均为真实外键**（`RESTRICT`/`RESTRICT`）：载体是否物理存在由数据库保证，且无 `ON DELETE CASCADE`。这是否决「判别列 + 无 FK」方案的决定性理由——该方案会放弃数据库级参照完整性，违反 `AGENTS.md` §6 与 ADR-0002。
- **不引入生成列 / ORM 多态 / STI / 触发器等**：三列都是普通标量列。

**结构性 NULL 是设计的一部分，不是缺陷**：任一行恰有两列为 NULL，由 CHECK 保证。

**多载体是一个 Service 的多行**，不是一行多列非空——这与 F007 的单载体情形不同，是本表的关键点：N:M 的「N」体现在 `service_carriers` 的**行数**（每个 Service 至少 1 行），「多载体」由**多个绑定行**表达。

### 5.2 集合语义：每载体列一条 partial unique

产品要求绑定集合是**集合**（同一 Service 内不得出现重复的同一载体，AC-48 / PROPOSED-1）。

因本设计没有单一载体判别列，集合语义由**三条**部分唯一索引表达：

- `ux_service_carriers_service_bare_metal`：`(service_id, bare_metal_id) WHERE bare_metal_id IS NOT NULL`
- `ux_service_carriers_service_virtual_machine`：`(service_id, virtual_machine_id) WHERE virtual_machine_id IS NOT NULL`
- `ux_service_carriers_service_container`：`(service_id, container_id) WHERE container_id IS NOT NULL`

**为什么三条索引不会互相干扰**：CHECK 保证每行恰有一列非空、另两列为 NULL，而 PostgreSQL 唯一索引中 **NULL 互不相等**。因此载体为 BareMetal 的行在另两条索引中的 key 含 NULL，恒不参与冲突；反之亦然。

**由此自动成立的关键语义**：

- **不同载体类型的绑定互不干扰**：同一 Service 可同时绑定 BareMetal `id=5`、VirtualMachine `id=5`、Container `id=5`——载体身份是 `(类型, 标识)` 二元组。
- **不同 Service 可绑定同一载体**（N:M 的另一方向，AC-17）：`service_id` 是索引首列，不同 Service 的行彼此独立。
- **同一 Service 内不得重复绑定同一载体**：由对应 partial unique 拒绝（`23505`）。
- **AC-06/07 的落地**：绑定表结构上不阻止「某个 Service 有 0 行」，故「登记时 ≥1 载体」由**应用层 + AC-49 回归查询**保证（见 §5.4）。

### 5.3 「释放绑定」不需要任何写入（架构 §2 裁定）

**绑定行不可变、不物理删除、无 `deleted_at`**。判断「某载体是否被活跃 Service 绑定」时，**不是**去查绑定行是否有效，而是把绑定行 JOIN 到 `services` 上并按 `services.deleted_at IS NULL` 过滤：

```sql
SELECT count(*) FROM service_carriers sc
JOIN services s ON s.id = sc.service_id
WHERE s.deleted_at IS NULL AND sc.bare_metal_id = :carrier_id;   -- 用于活跃子检查
```

Service 软删后，该查询立即返回 0 → 载体不再被该 Service 拦截（AC-39）**自动成立**。

**为什么这是正确取舍**：

- **不引入第二条写 `deleted_at` 的路径**：绑定表没有 `deleted_at` 列，静态 guard 可直接判定；`deleted_at` 的写入路径仍**恰为** `{backend/app/deletion/service.py}`（ADR-0004 allow-list 不变）。
- **不物理删除任何历史**：绑定行永不删除，绑定事实完整保留（R-DELETE-001 与历史保全精神）。
- **`app/deletion/service.py` 零改动**：统一软删服务仍只对「已锁定的目标行」赋值 `deleted_at`，不需要理解绑定表的存在。
- **AC-46 孤立记录不变式**：三条查询都以 `s.deleted_at IS NULL` 为条件，形状一致且只需一次 JOIN。
- **AC-49 零载体不变式**：`services` 中活跃行必有其绑定行，由「登记路径强制 ≥1」+「无任何路径移除绑定」共同保证（见 §5.4）。

> **对比 F007**：F007 没有「绑定」概念，其子资源 `containers` 是独立资源、有 `deleted_at`。F008 的 `service_carriers` 是**关系表**而非资源表，故不需要软删列，也不需要释放写入。**不得**照搬「子资源软删」模式到绑定表。

### 5.4 「≥1 载体」不变式与零载体

`service_carriers` 是普通 N:M 关系表，**结构上可以**表达「活跃 Service 且绑定行数为 0」。产品要求：

1. **产品写入路径必须兑现 AC-49**：登记路径强制 ≥1（应用层 `min_length=1` + 载体逐一校验）；且**不存在**任何移除绑定的路径（AC-48），故无路径可把活跃 Service 变为零载体。
2. **保留可重复执行的一致性查询作为回归断言**（AC-49）：

   ```sql
   SELECT count(*) FROM services s
   WHERE s.deleted_at IS NULL
     AND NOT EXISTS (SELECT 1 FROM service_carriers sc WHERE sc.service_id = s.id);
   -- 必须为 0 行
   ```

3. **不引入触发器 / 跨行约束**来实现该不变式（NQ-06 裁定；ADR-0002 明确避免触发器与复合外键）。数据库层**不**保证「活跃 Service 必有绑定行」——这是**应用层协议 + 回归断言**，与 F005 的漂移检测同性质。

**明确的后果声明（是事实，不是规则）**：在数据库层，一个活跃 Service 可以存在零绑定行。产品要求所有产品路径不产生该状态，并以回归查询持续验证。这**不得**被解读为「零载体活跃 Service 是合法状态」——该问题随 NQ-01 的确认（不做解绑）已无路径可达。

### 5.5 无 Cluster 维度

**不加 `cluster_id`**。Service 的 Cluster 归属由其**全部绑定载体**推导（BareMetal → 其 Cluster；VM → 其宿主 BareMetal → 其 Cluster；Container → 其载体的载体）。R-SVC-004 / R-SVC-006 明确**不设 `service.cluster_id`**。

> 与 F005 `ip_addresses` 形成对照：F005 落 `cluster_id` 是因为其**唯一性边界是 Cluster**，必须有该列才能建索引。F008 的唯一性边界是**全局**（`services.name` 单列索引），且 Cluster 归属是**纯推导**、不参与任何约束 → **不需要**任何 Cluster 列。**不得**照搬 F005 模式。

### 5.6 未定义约束不落 CHECK

**`services` 恰有 1 个约束（PK）、0 个 CHECK**；**`service_carriers` 恰有 1 个 CHECK**（载体 `num_nonnulls`）：

- `name` 与 6 个可选字段的长度 / trim / 空串 / 字符 / `/` / URL 格式 / 端口数字规则**均未确认**（AC-15）→ **不建任何 CHECK**，不 agent 自创。
- 大小写敏感**不**需要 CHECK（那是 collation 行为，ADR-0002 保证）。

> **明确的后果（事实，非规则）**：在当前已确认规则下，空串 `name`、含首尾空白的 `name`、`url = '这不是一个 URL'`、`port = 'abc'` **都不会被数据库拒绝**。这**不得**被解读为「已确认空 `name` 合法」或「任意 URL / 端口合法」。

### 5.7 与 F014 的关系

- `deleted_at` 的**唯一**写入路径是 `app/deletion/service.py`；本表不新增第二条路径。
- **父删子拦（三载体）**：活跃 Service 会阻止删除其**直接绑定**的 BareMetal / VirtualMachine / Container。这**不需要绑定表上的任何额外约束**——由应用层声明的活跃子检查实现（三个 `*_ACTIVE_CHILD_CHECKS` 均含活跃 Service 检查）。
- 四条 FK 的 `RESTRICT` 是绕过应用层时的第二道防线。
- **`CLUSTER_ACTIVE_CHILD_CHECKS` 不变**：Service↔Cluster 是推导关系而非子资源关系，删除 Cluster 仍只被活跃 BareMetal 拦截。
- **并发孤立记录不变式**（AC-46）：并发「登记 Service（绑定载体 X）」与「删除载体 X」结束后，下列三条查询必须为 **0 行**（见 `docs/api/f008-service.md` §7.3）。由「登记侧对每个载体行取 `FOR SHARE`（固定全序）并同事务确认活跃」+「删除侧对自身行 `FOR UPDATE` 后再检查活跃子」共同保证（ADR-0004 §5）。这是**应用层协议**，数据库不能单独保证；测试必须真实并发验证。

---

## 6. 对象清单（交付验收）

| 类别 | 数量 | 名称 |
|---|---|---|
| 表 | 2 | `services`、`service_carriers` |
| 列 | 16 | `services` 11 列 + `service_carriers` 5 列 |
| 约束 | 6 | 2 PK（`pk_services`、`pk_service_carriers`）+ 1 CHECK（`ck_service_carriers_exactly_one_carrier`）+ **4 FK**（均 `RESTRICT`/`RESTRICT`） |
| 索引 | 8 | `ux_services_name_active` + 3 条 `ux_service_carriers_service_*` + 3 条 `ix_service_carriers_<carrier>_id` + `ix_service_carriers_service_id` |
| CHECK | 1 | 仅 `ck_service_carriers_exactly_one_carrier` |
| CASCADE | **0** | 全部 FK 为 `RESTRICT`/`RESTRICT` |
| 触发器 / 生成列 / extension | **0** | — |
| `COLLATE` 声明 | **0** | — |

---

## 7. 验证方法（Tester 必须覆盖）

**绕开应用层直连数据库**（数据库为最终权威，ADR-0002）：

- [ ] 同一 Service 内重复绑定同一载体（三类型各一）→ `23505`（对应 partial unique）。
- [ ] **不同载体类型的绑定互不干扰**：同一 Service 同时绑定 BareMetal / VirtualMachine / Container 的 **同数值 id** → **成功**（三条 partial unique 互不干扰，本设计核心不变式之一）。
- [ ] **不同 Service 绑定同一载体** → **成功**（N:M 另一方向）。
- [ ] **0 个载体**（三列全 NULL）→ `23514`；**2 个载体**（任两列非空）→ `23514`；**3 个载体**（三列全非空）→ `23514`。
- [ ] 重复活跃 `services.name` → `23505`（`ux_services_name_active`）；非同活跃（一条已软删）→ **成功**。
- [ ] 同 `name` 的 `Service` 与 `Container` / `VirtualMachine` / `Cluster` / `BareMetal` 并存 → **成功**（各资源唯一性独立）。
- [ ] `name` 大小写敏感：`mon` 与 `MON` 共存。
- [ ] 软删释放唯一性：软删后可重建同名；旧行 `deleted_at` 未被改写。
- [ ] `name` 为空串、含首尾空白 → **不被拒绝**；`url = '这不是一个 URL'`、`port = 'abc'` → **不被拒绝**；并断言 `services` 表**恰 1 个约束**（PK，无隐性 CHECK）。
- [ ] 引用不存在的载体 id → `23503`；**尝试物理删除被绑定的载体行 → `23503`**（证明 `RESTRICT` 而非 CASCADE，三类型各一）。
- [ ] **软删 Service 后其绑定行仍存在且未被修改**（`service_carriers` 行数与各列不变）——证明「释放不是写入」。
- [ ] 断言两表**不存在** `status` / `cluster_id` 列；`service_carriers` **不存在** `deleted_at` 列。
- [ ] **AC-49 回归查询 = 0 行**；**AC-46 三条孤立记录查询 = 0 行**（真实并发，不得 mock）。

**Migration 层面**：

- [ ] `alembic upgrade head` 幂等；head 为 `0008_f008_services`。
- [ ] `alembic downgrade 0007` 可逆，再 `upgrade head` 回到一致状态。
- [ ] `alembic check` 无漂移（ORM 元数据与 migration 一致）。
- [ ] `0001`–`0007` 内容**逐字节未改**；既有表结构（列 / 约束 / 索引）不变。
- [ ] 无 `COLLATE` / 无 `lower()` / 无 CASCADE / 无触发器 / 无生成列（可失败静态断言）。

---

## 8. 文档同步（本 Feature 已执行）

以 CONFIRMED 规则为准，更正陈旧记载：

- `docs/database/csm-v1-schema-design.md`：`Service → BareMetal / VM / Container` 由「**本次不设计**（F008 延后）」更正为 F008 交付的两表设计；`0008+`「字段待 Product 阶段确认」更正为 `0008_f008_services` 已交付。
- `docs/database/f012-baseline-migration.md`：revision 树与 `0008_f008_services` 小节。

---

## 9. 不做什么（本次明确排除）

- 不执行任何 migration、不修改数据库（本文件仅为设计）。
- 不修改 `0001`–`0007`。
- 不引入 `status` / `cluster_id` / 凭据 / 健康 / 监控 / 发现 / 位置列。
- 不引入 CASCADE、触发器、生成列、EAV、JSONB、ORM 多态 / STI / 通用资源表。
- 不为 `name` 或 6 个可选字段建任何长度 / trim / 空串 / 字符 / URL / 端口 CHECK。
- **不为绑定表加 `deleted_at`**；**不物理删除绑定行**。
- 不声明 `COLLATE`、不使用 `lower()`。
- 不新增第二条写 `deleted_at` 的路径；**不修改** `app/deletion/service.py`。
- 不新增 extension / database / role / locale 变更。
