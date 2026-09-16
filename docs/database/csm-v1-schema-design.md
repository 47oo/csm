# CSM V1 数据库 Schema 设计（PostgreSQL + Alembic）

> **Database Handoff**
> Status: `READY FOR DATABASE IMPLEMENTATION`
> Author Role: database
> Date: 2026-09-15
> Source: `docs/product/requirements.md`、`docs/product/domain-model.yaml`、`docs/architecture/csm-v1-foundation-architecture.md`、ADR-0001 ~ ADR-0005（全部 `ACCEPTED`）
> 配套文档：`docs/database/f012-baseline-migration.md`

---

## Feature

CSM V1 数据库 Schema 首次建模 + F012 基线 migration 设计。

本设计覆盖当前已确认、已进入实现范围的实体：**Cluster（F001）、BareMetal（F002）、NetworkInterface（F004）、IPAddress（F005）与本地认证（users / sessions，F013）**；并给出 F012 基线 migration 的最小集合（见配套文档）。

VirtualMachine（F006）、Container（F007）、Service（F008）对应的表 **不在本次范围**（见 `Open Questions > Non-blocking`）。

---

## Design Basis

**产品文档（CONFIRMED）**

- `docs/product/requirements.md`（Primary Requirements Source）：§5 唯一性、§7 状态模型、§10~§12、§16 查询、§17 逻辑删除、§18 R-IMPORT、§19 认证、§21 完整性、§22 大小写、§24~§25 原则、§29 未决项、§30 范围外。
- `docs/product/domain-model.yaml`（精确取值来源）：`resources` / `relationships` / `status_models` / `uniqueness_rules` / `lifecycle` / `data_consistency`。
- `docs/product/domain-model.md` §5~§9。

**Architecture Handoff**

- `docs/architecture/csm-v1-foundation-architecture.md`（Status `READY FOR IMPLEMENTATION`）：Data Layer Impact（8 张资源表 + 2 张认证表、代理主键、三条 partial unique、`ip_address.cluster_id` 反规范化、软删除、状态约束、枚举落点、索引、Migration 策略、UTF-8）、Risks #1/#4/#7。

**Accepted ADR（全部 `ACCEPTED`）**

- ADR-0001：技术栈 Python + FastAPI + Pydantic + SQLAlchemy 2.x + Alembic；PostgreSQL；横切列 `id / created_at / updated_at / deleted_at` 允许 mixin 复用。
- ADR-0002：PostgreSQL；**默认 collation**（不声明 `COLLATE "C"`）；三条 partial unique index；`ip_address.cluster_id` 走**受控写入路径 + 一致性测试**，不引入复合外键、不使用触发器；`bare_metal.status` NOT NULL DEFAULT `'IDLE'` + CHECK；Alembic 版本化向前 migration。
- ADR-0003：BIGINT identity 不可变代理主键；外键一律引用 `id`；`by-name` 只读别名（大小写敏感）。
- ADR-0004：`deleted_at TIMESTAMPTZ NULL` 单一删除标记；partial unique index predicate = `deleted_at IS NULL`；查询统一过滤；无 undelete；父删子拦在同一事务内加行锁；不级联。
- ADR-0005：本地账号 `users`（username 唯一、password_hash、active、时间戳）；服务端会话表 + 随机不可预测 session id + HttpOnly Cookie + Argon2id；仅「已认证 / 未认证」。

**Domain Rule**

- 唯一性：R-CLUSTER-002（全局、大小写敏感）、R-BM-002（同 Cluster 内、大小写敏感）、R-IP-001~003（同 Cluster 内）。
- 字符约束：R-CLUSTER-005（名称不得含 `/`）。
- 状态：R-BM-003~006（`IDLE/ALLOC/DOWN/UNKNOWN`、默认 `IDLE`、非空、人工维护）。
- 关系：R-BM-001（BareMetal→Cluster 必选）、R-NIC-003（NIC→BareMetal 必选）、§15（IP→NIC 必选）。
- 生命周期：R-DELETE-001~006。
- 一致性：§21（关键冲突必须在保存前阻止，不能只依赖 UI）。

**Skill**：`.pi/skills/resource-domain/SKILL.md`（CONFIRMED / PROPOSED / UNCONFIRMED 三分法）。

---

## Entities

`Cluster`、`BareMetal`、`NetworkInterface`、`IPAddress`、`User`、`Session`。

---

## Existing Schema

**当前不存在，属于首次建模。**

`docs/database/` 目录原不存在（已确认）；无 backend / tests；无任何既有 migration 或数据库对象需兼容。数据库为 greenfield 单机 PostgreSQL。

---

## Schema Design

### 命名与通用约定（技术决策，非产品规则）

| 项 | 约定 |
|---|---|
| 表名 | 复数 `snake_case`（`clusters` / `bare_metals` / `network_interfaces` / `ip_addresses` / `users` / `sessions`） |
| 约束/索引前缀 | `pk_` / `fk_` / `ux_`（唯一索引）/ `ix_`（普通索引）/ `ck_` |
| 主键 | `id BIGINT GENERATED ALWAYS AS IDENTITY`（不可变代理主键，ADR-0003） |
| 时间列 | `created_at` / `updated_at`：`TIMESTAMPTZ NOT NULL DEFAULT now()` |
| 删除列 | `deleted_at TIMESTAMPTZ NULL`（仅资源表；认证表不使用） |
| 字符集 | 数据库 / 表 / 连接统一 UTF-8 |
| collation | **不显式声明**，使用数据库默认 collation（ADR-0002 选项 1） |
| 时间语义 | `TIMESTAMPTZ`（UTC 存储、按会话时区呈现） |

> 表名/约束名属工程约定，不得被解释为产品规则；不改变任何领域语义。

---

### Table: `clusters`（F001，Cluster）

**用途**：Cluster 为 V1 基础设施顶层对象，无状态、无 DataCenter 上级。

#### Columns

| 列 | 类型 | 空 | 默认 | 业务含义 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | identity | 数据库内部身份（不可变） |
| `name` | `TEXT` | NOT NULL | — | 集群名称（R-CLUSTER-001 的识别名称） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 登记时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 最近更新时间（应用层维护） |
| `deleted_at` | `TIMESTAMPTZ` | NULL | — | 逻辑删除标记（`NULL` = 活跃） |

> **不设计**：状态列（R-CLUSTER-003）、DataCenter 上级（§6 / DEC-001）、`name` 的长度 / 首尾空白 / 其他字符规则（domain-model `undefined_constraints`，**不得自行假设**）、`owner` / `description` 等未确认字段。

#### Primary Key

`pk_clusters (id)` —— BIGINT identity 代理主键，绝不使用 `name` 作为主键。

#### Foreign Keys

无。

#### Constraints

```sql
ALTER TABLE clusters
  ADD CONSTRAINT ck_clusters_name_no_slash CHECK (strpos(name, '/') = 0);
```

- **R-CLUSTER-005 的数据库层落地**：`name` 不得包含 `/`。产品将该规则定义为「写入路径必须校验」；`CHECK` 是最强形式的写入路径校验（ADR-0002 / AGENTS.md §6）。
- `name` 全局唯一由 partial unique index 表达（见 Indexes），**不使用**表级 `UNIQUE` 约束 —— PostgreSQL 的 `UNIQUE` 约束无法带 `WHERE` predicate，无法满足 R-DELETE-006。
- **不添加**：`name <> ''`、长度上限、`trim(name) = name`（未确认，见 Open Questions）。

#### Indexes

```sql
CREATE UNIQUE INDEX ux_clusters_name_active
  ON clusters (name)
  WHERE deleted_at IS NULL;
```

- 服务于：**R-CLUSTER-002**（全局唯一）+ **R-DELETE-006**（已删不占唯一性）+ **ADR-0003 `GET /api/clusters/by-name/{cluster_name}`**（大小写敏感、已删不参与名称解析）。
- 不额外建 `deleted_at` 索引：活跃 Cluster 数量级为 10¹~10²，全表扫描成本可忽略；`ux_clusters_name_active` 已覆盖按名称的活跃查询。

---

### Table: `bare_metals`（F002，BareMetal）

**用途**：物理服务器 / 物理计算节点登记；V1 唯一有状态资源。

#### Columns

| 列 | 类型 | 空 | 默认 | 业务含义 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | identity | 内部身份 |
| `cluster_id` | `BIGINT` | NOT NULL | — | 所属 Cluster（R-BM-001 必选） |
| `hostname` | `TEXT` | NOT NULL | — | 主机名（R-BM-002） |
| `status` | `TEXT` | NOT NULL | `'IDLE'` | 状态（R-BM-003~006） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 登记时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 最近更新时间 |
| `deleted_at` | `TIMESTAMPTZ` | NULL | — | 逻辑删除标记 |

> **不设计**：Rack / U Position（§13 已从 V1 删除）、状态来源 / 监控字段（R-BM-006）。
> **硬件字段（R-BM-007，2026-09-16 用户裁定，OPEN-004 已关闭）**：`vendor` / `model` / `serial_number` / `cpu` / `memory` / `gpu` / `storage` 均为**可选 `TEXT` 且允许 NULL**（Serial 不参与唯一性），需在 F002 的增量 migration 中新增；本节列清单待 F002 Database 阶段同步补齐。

#### Primary Key

`pk_bare_metals (id)`。

#### Foreign Keys

```sql
ALTER TABLE bare_metals
  ADD CONSTRAINT fk_bare_metals_cluster
  FOREIGN KEY (cluster_id) REFERENCES clusters (id)
  ON DELETE RESTRICT ON UPDATE RESTRICT;
```

- 必选关系（R-BM-001）→ `NOT NULL` + FK。
- `ON DELETE RESTRICT`：**不使用 CASCADE**（R-DELETE-005 / ADR-0004）。物理删除父 Cluster 会被数据库拒绝；产品语义的「父删子拦」见「关键设计决策 > 5/6」（FK 无法表达 `deleted_at IS NULL`，该规则由应用层在同事务加锁实现）。

#### Constraints

```sql
ALTER TABLE bare_metals
  ADD CONSTRAINT ck_bare_metals_status
  CHECK (status IN ('IDLE', 'ALLOC', 'DOWN', 'UNKNOWN'));
```

- 取值集合来自 `domain-model.yaml > status_models.stateful_resources`；`NOT NULL` 表达 R-BM-005（不得用 `NULL` 代替 `UNKNOWN`）；默认值表达 R-BM-004。
- 主机名同 Cluster 内唯一由 partial unique index 表达（见下）；跨 Cluster 可重复（R-BM-002 `cross_scope_allowed`）。

#### Indexes

```sql
CREATE UNIQUE INDEX ux_bare_metals_cluster_hostname_active
  ON bare_metals (cluster_id, hostname)
  WHERE deleted_at IS NULL;

CREATE INDEX ix_bare_metals_cluster_id
  ON bare_metals (cluster_id);
```

- `ux_bare_metals_cluster_hostname_active`：服务于 **R-BM-002**（同 Cluster 内 hostname 唯一）+ **R-DELETE-006**；其首列同时服务「按 Cluster 列出活跃 BareMetal」（R-QUERY-002 / F009）。
- `ix_bare_metals_cluster_id`：`ux_..._active` 为 **partial**，不覆盖已删行，也无法服务 FK 引用完整性检查（物理删除父行时）；保留完整 `cluster_id` 索引以服务 FK 引用检查（架构 Data Layer Impact「外键列索引」）。两条索引职责不同，均保留。

---

### Table: `network_interfaces`（F004，NetworkInterface）

**用途**：网络接口登记，V1 无状态。

#### Columns

| 列 | 类型 | 空 | 默认 | 业务含义 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | identity | 内部身份 |
| `bare_metal_id` | `BIGINT` | NOT NULL | — | 所属 BareMetal（R-NIC-003 必选） |
| `name` | `TEXT` | NOT NULL | — | 接口名（`eth0` / `ib0` …） |
| `technology_type` | `TEXT` | NOT NULL | — | 技术类型（R-NIC-001） |
| `purpose` | `TEXT` | NOT NULL | — | 用途（R-NIC-002） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 登记时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 最近更新时间 |
| `deleted_at` | `TIMESTAMPTZ` | NULL | — | 逻辑删除标记 |

> **不设计**：状态列（Q-002=B 已确认无状态）、MAC / 速率 / MTU 等未确认字段、VM 归属列（R-NIC-003 开放项，见 Open Questions）。

#### Primary Key

`pk_network_interfaces (id)`。

#### Foreign Keys

```sql
ALTER TABLE network_interfaces
  ADD CONSTRAINT fk_network_interfaces_bare_metal
  FOREIGN KEY (bare_metal_id) REFERENCES bare_metals (id)
  ON DELETE RESTRICT ON UPDATE RESTRICT;
```

#### Constraints

```sql
ALTER TABLE network_interfaces
  ADD CONSTRAINT ck_network_interfaces_technology_type
    CHECK (technology_type IN ('Ethernet', 'InfiniBand', 'RoCE', 'Other')),
  ADD CONSTRAINT ck_network_interfaces_purpose
    CHECK (purpose IN ('BMC', 'Management', 'Business', 'Compute', 'Storage', 'DataTransfer', 'Other'));
```

- 枚举集来自 `domain-model.yaml > resources[NetworkInterface].fields`，与 R-NIC-001 / R-NIC-002 完全一致（内部枚举稳定，中文展示由 UI 决定）。
- **不添加** `UNIQUE (bare_metal_id, name)`：NIC 名称在同一 BareMetal 内是否唯一**未经产品确认**，不得设为唯一约束（见 Open Questions）。

#### Indexes

```sql
CREATE INDEX ix_network_interfaces_bare_metal_id
  ON network_interfaces (bare_metal_id);
```

- 服务于：FK 引用完整性检查 + 「按 BareMetal 列出其 NIC」（R-QUERY-003 / F010）。

---

### Table: `ip_addresses`（F005，IPAddress）

**用途**：IP 地址登记，V1 无状态；唯一性边界是 **Cluster**，而直接父是 NetworkInterface → 需反规范化 `cluster_id`。

#### Columns

| 列 | 类型 | 空 | 默认 | 业务含义 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | identity | 内部身份 |
| `network_interface_id` | `BIGINT` | NOT NULL | — | 直接父：NetworkInterface（§15 必选） |
| `cluster_id` | `BIGINT` | NOT NULL | — | **反规范化**：IP 所属 Cluster（唯一性边界，ADR-0002） |
| `ip_address` | `TEXT` | NOT NULL | — | IP 地址字面值（如 `10.0.1.1/16`） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 登记时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 最近更新时间 |
| `deleted_at` | `TIMESTAMPTZ` | NULL | — | 逻辑删除标记 |

**列类型选择 `TEXT`（明确结论）**：产品规则要求「完全相同 IP」（R-IP-001）且 `domain-model.yaml` 声明 `case_sensitive: true`，即以**字面值精确比较**为唯一性语义；示例 `10.0.1.1/16` 含前缀长度。使用 PostgreSQL `inet` / `cidr` 会引入产品未确认的**表示归一化**语义（例如 `10.0.1.1` 与 `10.0.1.1/16` 的等价性、IPv6 十六进制大小写折叠），属于「把建议变成约束」。因此 V1 采用 `TEXT`，格式校验 / 归一化列为 OPEN（见 Open Questions）。

> **不设计**：状态列、VRF / 网络命名空间列（R-IP-003 明确不考虑）、用途 / 备注等未确认字段。

#### Primary Key

`pk_ip_addresses (id)`。

#### Foreign Keys

```sql
ALTER TABLE ip_addresses
  ADD CONSTRAINT fk_ip_addresses_network_interface
  FOREIGN KEY (network_interface_id) REFERENCES network_interfaces (id)
  ON DELETE RESTRICT ON UPDATE RESTRICT,
  ADD CONSTRAINT fk_ip_addresses_cluster
  FOREIGN KEY (cluster_id) REFERENCES clusters (id)
  ON DELETE RESTRICT ON UPDATE RESTRICT;
```

- 两条 FK 都只保证「引用对象在物理上存在」。
- **`fk_ip_addresses_cluster` 不保证 `cluster_id` 与 NIC→BareMetal→Cluster 链路一致**（ADR-0002 已裁定：不引入逐级复合外键、不使用触发器）。一致性由受控写入路径 + 一致性测试保证；数据库层可执行的漂移检测查询见「关键设计决策 > 3」与 `Verification`。

> **关于 `network_interface_id NOT NULL` 的依据（已于 2026-09-15 由用户裁定，不再是开放问题）**
>
> **用户裁定：IP 地址必须绑定在 NetworkInterface 上，该关系为 Mandatory。** 因此 `ip_addresses.network_interface_id` 为 `NOT NULL` + FK，**本设计无需修改**。
>
> 该裁定同时消除了一项文档歧义：`domain-model.yaml` 本已记为 `binding_state: CONFIRMED` / `mandatory: true`，而 `requirements.md` §15 散文写的是「必选性必须以对应 Product Feature 的确认结果为准」。**现以用户裁定为准，§15 的该句不再适用于此关系。** 两处产品文档已同步更新，并记录于 `requirements.md` 顶部变更记录。

#### Constraints

`NOT NULL` 表达必选关系；唯一性由 partial unique index 表达；无其他 CHECK（格式校验未确认）。

#### Indexes

```sql
CREATE UNIQUE INDEX ux_ip_addresses_cluster_ip_active
  ON ip_addresses (cluster_id, ip_address)
  WHERE deleted_at IS NULL;

CREATE INDEX ix_ip_addresses_cluster_id
  ON ip_addresses (cluster_id);

CREATE INDEX ix_ip_addresses_network_interface_id
  ON ip_addresses (network_interface_id);
```

- `ux_ip_addresses_cluster_ip_active`：服务于 **R-IP-001 / R-IP-002 / R-IP-003**（同 Cluster 唯一、跨 Cluster 可重复）+ R-DELETE-006。
- `ix_ip_addresses_cluster_id`：`ux_..._active` 为 partial，不覆盖已删行与 FK 检查；保留完整索引。
- `ix_ip_addresses_network_interface_id`：FK 引用完整性 + 「列出某 NIC 的 IP」。

---

### Table: `users`（F013，本地账号，ADR-0005）

**用途**：本地认证账号。V1 无自助注册；账号由管理员初始化 / 种子创建。

#### Columns

| 列 | 类型 | 空 | 默认 | 业务含义 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | identity | 内部身份 |
| `username` | `TEXT` | NOT NULL | — | 登录名 |
| `password_hash` | `TEXT` | NOT NULL | — | Argon2id 哈希（明文不得落库） |
| `active` | `BOOLEAN` | NOT NULL | `TRUE` | 账号启用标志（禁用即失效） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 最近更新时间 |

> **不设计**：`deleted_at`（账号不使用资源逻辑删除语义，停用由 `active` 表达；V1 无删除账号功能）、角色 / 权限 / RBAC 相关列（R-AUTH-003 明确禁止扩大范围）、邮箱 / 显示名等未确认字段。

#### Primary Key

`pk_users (id)`。

#### Foreign Keys

无。

#### Constraints

```sql
ALTER TABLE users
  ADD CONSTRAINT ux_users_username UNIQUE (username);
```

- **说明**：`users` 无 `deleted_at`，故使用普通 `UNIQUE` 约束（非 partial index）。
- `username` 唯一性**区分大小写**——**已由 R-AUTH-005 确认（2026-09-15）**，不再是 OPEN。按数据库默认 collation（大小写敏感）+ 普通 `UNIQUE` 实现。**不添加** `lower(username)` 唯一索引，也**不得**使用 `ILIKE` 或任何大小写折叠。

#### Indexes

`ux_users_username` 已满足按 username 查找的唯一约束与访问需求。

---

### Table: `sessions`（F013，服务端会话，ADR-0005）

**用途**：服务端会话。Cookie 仅承载不透明随机会话令牌；登出 / 过期即失效。

#### Columns

| 列 | 类型 | 空 | 默认 | 业务含义 |
|---|---|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | NOT NULL | identity | 内部身份 |
| `user_id` | `BIGINT` | NOT NULL | — | 所属账号 |
| `token_hash` | `TEXT` | NOT NULL | — | 会话令牌的哈希（原文不落库） |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | 会话建立时间 |
| `expires_at` | `TIMESTAMPTZ` | NOT NULL | — | 绝对过期时间 |
| `last_seen_at` | `TIMESTAMPTZ` | NULL | — | **OPTIONAL / PROPOSED**：若采用滑动续期则记录；否则保持不用 |

> **不设计**：`deleted_at` / `revoked_at`（会话不是资源历史，登出 / 过期直接删除行）、角色列、IP / UA 记录（无产品需求）。
> `last_seen_at` 标记为 PROPOSED：ADR-0005 将「会话过期时间与是否滑动续期」留给实现阶段决定。
> **F013 已记录该决策（2026-09-15）**：绝对有效期 **8 小时**，**不采用滑动续期**，因此该列**保留但不写入**（保留列成本极低，避免后续加列迁移）。**它不是产品规则**；决策记录见 `docs/api/f013-auth.md` §7。

#### Primary Key

`pk_sessions (id)`。

#### Foreign Keys

```sql
ALTER TABLE sessions
  ADD CONSTRAINT fk_sessions_user
  FOREIGN KEY (user_id) REFERENCES users (id)
  ON DELETE RESTRICT ON UPDATE RESTRICT;
```

- V1 无删除账号功能；`RESTRICT` 明确「存在会话时不得物理删除账号」。

#### Constraints

```sql
ALTER TABLE sessions
  ADD CONSTRAINT ux_sessions_token_hash UNIQUE (token_hash);
```

#### Indexes

```sql
CREATE INDEX ix_sessions_user_id ON sessions (user_id);
CREATE INDEX ix_sessions_expires_at ON sessions (expires_at);
```

- `ix_sessions_user_id`：服务于 ADR-0005「管理员禁用账号 / 登出 → 使该用户全部会话即时失效」。
- `ix_sessions_expires_at`：服务于会话过期清理任务（删除 `expires_at <= now()` 的行）。

---

## Relationships

| 关系 | 基数 | 必选 | 数据库实现 | 删除行为 | 允许孤立记录 |
|---|---|---|---|---|---|
| BareMetal → Cluster | N:1 | **是**（R-BM-001） | `bare_metals.cluster_id NOT NULL` + FK | `ON DELETE RESTRICT`（不级联）；产品语义的父删子拦由应用层事务加锁实现 | 否（`NOT NULL`） |
| NetworkInterface → BareMetal | N:1 | **是**（R-NIC-003） | `network_interfaces.bare_metal_id NOT NULL` + FK | `ON DELETE RESTRICT` | 否 |
| IPAddress → NetworkInterface | N:1 | **是**（用户 2026-09-15 裁定：IP 必须绑定在 NIC 上；见上文依据说明） | `ip_addresses.network_interface_id NOT NULL` + FK | `ON DELETE RESTRICT` | 否 |
| IPAddress → Cluster（反规范化） | N:1 | **是**（ADR-0002） | `ip_addresses.cluster_id NOT NULL` + FK | `ON DELETE RESTRICT` | 否 |
| Session → User | N:1 | 是 | `sessions.user_id NOT NULL` + FK | `ON DELETE RESTRICT` | 否 |
| Service → BareMetal / VM / Container | N:M | 是（R-SVC-005） | **本次不设计**（F008 延后） | — | — |
| Service ↔ Cluster | 推导 | — | **不落列**（R-SVC-004 / R-SVC-006 禁止 `service.cluster_id`） | — | — |
| VirtualMachine → BareMetal / Container → 载体 | 未确认 | UNCONFIRMED | **本次不设计**，且**不得**固化为 `NOT NULL` | — | — |

**不级联结论**：全部 FK 使用 `ON DELETE RESTRICT`，无一处 `ON DELETE CASCADE`（R-DELETE-005 / ADR-0004）。逻辑删除是 `UPDATE ... SET deleted_at = now()`，不触发 FK。

---

## Required Constraints

已经确认、**必须由数据库实现**的约束：

1. `clusters.name` —— `NOT NULL`（R-CLUSTER-001 的识别名称）。
2. `clusters` —— `CHECK (strpos(name, '/') = 0)`（R-CLUSTER-005）。
3. `ux_clusters_name_active` —— 全局唯一、大小写敏感、仅活跃（R-CLUSTER-002 + R-DELETE-006 + §22）。
4. `bare_metals.cluster_id` —— `NOT NULL` + FK → `clusters(id)`（R-BM-001）。
5. `bare_metals.hostname` —— `NOT NULL`（R-BM-002）。
6. `ux_bare_metals_cluster_hostname_active` —— 同 Cluster 内唯一、大小写敏感、仅活跃（R-BM-002 + §22 + R-DELETE-006）。
7. `bare_metals.status` —— `NOT NULL DEFAULT 'IDLE'` + `CHECK IN ('IDLE','ALLOC','DOWN','UNKNOWN')`（R-BM-003~005）。
8. `network_interfaces.bare_metal_id` —— `NOT NULL` + FK（R-NIC-003）；`technology_type` / `purpose` —— `NOT NULL` + 枚举 `CHECK`（R-NIC-001 / R-NIC-002）。
9. `ip_addresses.network_interface_id` —— `NOT NULL` + FK（用户 2026-09-15 裁定为 Mandatory；见上文依据说明）。
10. `ip_addresses.cluster_id` —— `NOT NULL` + FK → `clusters(id)`（ADR-0002，承载唯一性边界）。
11. `ux_ip_addresses_cluster_ip_active` —— 同 Cluster 唯一、跨 Cluster 可重复、仅活跃（R-IP-001~003 + R-DELETE-006）。
12. `users.username` —— `NOT NULL` + `UNIQUE`；`password_hash` —— `NOT NULL`（ADR-0005）。
13. `sessions.user_id` —— `NOT NULL` + FK；`token_hash` —— `NOT NULL` + `UNIQUE`；`expires_at` —— `NOT NULL`（ADR-0005）。
14. 全部 FK —— `ON DELETE RESTRICT`，**禁止 CASCADE**（R-DELETE-005 / ADR-0004）。
15. 全部资源表 —— `deleted_at TIMESTAMPTZ NULL`（ADR-0004）。

**明确不作为数据库约束**（未确认或表达力不足）：

- `ip_addresses.cluster_id` 与链路一致性（**可执行检测查询，但非约束**，ADR-0002）。
- 「父资源存在活跃子资源时不得删除」的**软删除**分支（FK 看不到 `deleted_at`，须应用层事务加锁）。
- NIC 名称在同一 BareMetal 内唯一（未确认）。
- `name` / `hostname` / `ip_address` 的长度、空白、格式规则（未确认）。
- ~~`username` 大小写敏感性（未确认）~~ → **已确认**（R-AUTH-005）：区分大小写。

---

## Required Indexes

| 索引 | 类型 | 对应查询 / 约束 |
|---|---|---|
| `pk_clusters` / `pk_bare_metals` / `pk_network_interfaces` / `pk_ip_addresses` / `pk_users` / `pk_sessions` | 主键唯一 | 按 `id` 寻址（ADR-0003） |
| `ux_clusters_name_active` | partial unique | R-CLUSTER-002 + R-DELETE-006 + `by-name` 别名 |
| `ux_bare_metals_cluster_hostname_active` | partial unique | R-BM-002 + R-DELETE-006 + 按 Cluster 列 BareMetal（活跃） |
| `ix_bare_metals_cluster_id` | btree | FK 引用完整性检查 + 含已删行的按 Cluster 查询 |
| `ix_network_interfaces_bare_metal_id` | btree | FK 引用完整性 + 按 BareMetal 列 NIC |
| `ux_ip_addresses_cluster_ip_active` | partial unique | R-IP-001~003 + R-DELETE-006 |
| `ix_ip_addresses_cluster_id` | btree | FK 引用完整性 + 含已删行的按 Cluster 查询 |
| `ix_ip_addresses_network_interface_id` | btree | FK 引用完整性 + 按 NIC 列 IP |
| `ux_users_username` | unique | 登录名唯一 + 登录查找 |
| `ux_sessions_token_hash` | unique | 会话令牌查找 |
| `ix_sessions_user_id` | btree | 使某用户全部会话失效（登出 / 禁用账号） |
| `ix_sessions_expires_at` | btree | 过期会话清理 |

无一为「以后可能查询」而建；每条均对应上述具名查询或约束。

---

## 关键设计决策（技术点结论）

### 1. collation 的落地形式

**结论：使用数据库默认 collation；迁移中不出现任何 `COLLATE` 子句。**

- **DDL / Migration 要求**：`clusters.name`、`bare_metals.hostname`、`ip_addresses.ip_address` 等列**不声明**列级 collation；唯一索引**不写** `COLLATE`；不创建 `lower(...)` 表达式索引。Alembic migration 中对应 `sa.Column(..., sa.Text())`，不得带 `collation=`。
- **如何确认实际 collation**（部署与测试都可执行）：

  ```sql
  -- 数据库级
  SELECT datname, datcollate, datctype, pg_encoding_to_char(encoding) AS encoding
  FROM pg_database WHERE datname = current_database();

  -- 列级：预期 collation_name 为 NULL（表示使用数据库默认）
  SELECT table_name, column_name, collation_name
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name IN ('clusters','bare_metals','network_interfaces','ip_addresses')
    AND collation_name IS NOT NULL;   -- 应返回 0 行

  -- 语义固定（必须为 false）
  SELECT ('cluster-a' = 'Cluster-A') AS eq_ci;   -- 期望 false
  ```
- **部署文档须记录的内容**（架构 Risk #1 的具体落地）：
  1. 目标数据库实例的 `datcollate` / `datctype` / `encoding`（`encoding` 必须为 `UTF8`），以及记录时的 PostgreSQL 大版本；
  2. **数据库必须使用固定的、大小写敏感的文本比较 locale 初始化**（`C.UTF-8` 或 `en_US.UTF-8` 等），且**不得在已部署环境中静默变更 locale**；
  3. docker-compose 中 PostgreSQL 服务的 locale 配置项（例如 `POSTGRES_INITDB_ARGS` / `LANG` / `LC_ALL`）必须显式固定，避免镜像默认值漂移；
  4. 说明：PostgreSQL 的 `text` **等值比较在标准 locale 下本身即大小写敏感**，默认 collation 只影响排序（中文排序不要求拼音序）；
  5. 附上上一条 `SELECT ('cluster-a' = 'Cluster-A')` 的回归测试，作为「locale 未被静默改变」的持续断言（必须绕过应用层直接对数据库执行）。
- **不采用 `COLLATE "C"`**：用户已裁定（ADR-0002）。`COLLATE "C"` 会让中文排序按 UTF-8 码点而非拼音，改变列表排序语义，而等值比较本就正确。

### 2. partial unique index 的精确定义

三条规则的可执行形式：

```sql
-- R-CLUSTER-002（全局唯一）
CREATE UNIQUE INDEX ux_clusters_name_active
  ON clusters (name)
  WHERE deleted_at IS NULL;

-- R-BM-002（同一 Cluster 内唯一）
CREATE UNIQUE INDEX ux_bare_metals_cluster_hostname_active
  ON bare_metals (cluster_id, hostname)
  WHERE deleted_at IS NULL;

-- R-IP-001/002/003（同一 Cluster 内唯一，跨 Cluster 可重复）
CREATE UNIQUE INDEX ux_ip_addresses_cluster_ip_active
  ON ip_addresses (cluster_id, ip_address)
  WHERE deleted_at IS NULL;
```

- **`NULLS NOT DISTINCT` 不需要，也不得添加**：其语义仅在「被索引列的值为 NULL」时才起作用。本设计中被索引列 `name` / `cluster_id` / `hostname` / `ip_address` 全部为 `NOT NULL`，NULL 无法进入索引，加不加 `NULLS NOT DISTINCT` 行为完全相同。显式添加只会误导读者以为存在 NULL 语义。
- **predicate 必须与常规查询过滤一致**：全部活跃查询一律附加 `deleted_at IS NULL`（ADR-0004），否则会出现「查询看不到、写入却冲突」的错位。
- 使用 **partial unique index** 而非表级 `UNIQUE` 约束，因为 PostgreSQL 的 `UNIQUE` 约束不支持 `WHERE` predicate，无法满足 R-DELETE-006。

### 3. `ip_address.cluster_id` 的受控写入路径

**数据库层能看到什么保证：**

- `ip_addresses.cluster_id` 引用的 Cluster 在物理上存在（FK `fk_ip_addresses_cluster`）；
- `ip_addresses.network_interface_id` 引用的 NIC 在物理上存在（FK）；
- **不能**保证 `ip_addresses.cluster_id` 等于 `network_interfaces.bare_metal_id → bare_metals.cluster_id` 的推导结果。

**受控写入路径（必须由 F014 领域服务强制，不得由调用方直接赋值）：**

| 触发写入 | 必须执行的推导/联动 |
|---|---|
| 新建 / 更新 IPAddress | 从 `network_interface_id` 沿 NIC→BareMetal→Cluster 推导 `cluster_id` 后写入 |
| 变更 `network_interfaces.bare_metal_id` | 在同一事务内重新推导并更新该 NIC 全部 IP 的 `cluster_id`（或被领域服务拒绝） |
| 变更 `bare_metals.cluster_id` | 在同一事务内重新推导并更新该 BareMetal 全部 NIC 的全部 IP 的 `cluster_id`（若该操作被允许，见 Open Questions；否则拒绝） |

**一致性测试具体要测什么（可执行）：**

1. **漂移检测查询（应返回 0 行，作为回归断言）**：

   ```sql
   SELECT ip.id, ip.cluster_id AS stored_cluster, bm.cluster_id AS derived_cluster
   FROM ip_addresses ip
   JOIN network_interfaces nic ON nic.id = ip.network_interface_id
   JOIN bare_metals        bm  ON bm.id  = nic.bare_metal_id
   WHERE ip.cluster_id <> bm.cluster_id;
   ```

   期望：**0 行**。该查询在 `ip_addresses` / `network_interfaces` / `bare_metals` 上均为真实扫描，是唯一能从数据库侧发现漂移的手段。

2. **场景 A（创建）**：在 Cluster A 的 BareMetal 下建立 NIC，随后通过领域服务创建 IP → 断言新行 `cluster_id = A.id`。
3. **场景 B（反例 / 绕过路径）**：直接对数据库插入 `cluster_id` 指向 Cluster B 的 IP（其 NIC 属于 Cluster A）→ 数据库**不会拒绝**（这是 ADR-0002 的已知取舍）；断言：该行必须被步骤 1 的漂移查询发现，从而证明测试有效而非约束有效。此用例是「题面要求证明该机制必需」的证据。
4. **场景 C（NIC 迁移）**：将 NIC 从 Cluster A 的 BareMetal 改挂到 Cluster B 的 BareMetal → 断言该 NIC 全部 IP 的 `cluster_id` 同步变为 `B.id`，且漂移查询仍为 0 行。
5. **场景 D（唯一性边界被漂移破坏的证明）**：Cluster A 已有 IP `10.0.0.10`；构造一条漂移行（真实属于 A、但存储 `cluster_id = B`）为同一 `10.0.0.10` → 唯一索引**不会**阻止（因为索引看到的是 B+A 的组合），从而证明「漂移 = R-IP-001 的静默漏洞」，故一致性测试为必需项。
6. **跨 Cluster 变更不留漂移**：删除 / 软删中间节点（NIC / BareMetal）后，漂移查询仍为 0 行。

### 4. status 的约束形式

| 方案 | 优点 | 缺点 / 演进成本 |
|---|---|---|
| PostgreSQL `ENUM` 类型 | 类型级强约束、存储紧凑、`pg_type` 集中管理 | 增删值需 `ALTER TYPE`（有事务上下文限制、不能与使用同值在同一事务中）；改名 / 删除 / 重排值困难；SQLAlchemy/Alembic 映射与 autogenerate 支持较弱；跨环境迁移更易出错 |
| **`TEXT` + 具名 `CHECK`** ✅ | 与 ORM 映射最简；调整值集合只需 drop + recreate CHECK；约束名可被迁移与测试直接引用；对 10⁵ 规模无任何性能差异 | 约束定义在表上而非独立类型（对本项目是优点：规则显式可见，符合 AGENTS.md §2.4） |
| `VARCHAR` + 仅应用层校验 | 实现最省事 | **违反 §21 / AGENTS.md §6**：数据库无真实保护，明确排除 |

**选择：`TEXT` + 具名 `CHECK`**（`ck_bare_metals_status`）。理由：V1 只有**一个**状态列，ENUM 的类型安全收益极小，而 ENUM 的变更成本（需产品确认后才能改、且变更流程更重）在 V1 之后很可能被触发（状态集合由产品维护，R-BM-003 明确「若确需调整状态集合，必须经过需求确认」—— 约束形式应让这种受控变更尽量便宜）。`NOT NULL` + `DEFAULT 'IDLE'` 与 `CHECK` 一并表达 R-BM-003~005。

### 5. `ON DELETE` 行为选择及其与「父删子拦」的关系

- **全部 FK 使用 `ON DELETE RESTRICT`（不 CASCADE）**：物理删除父对象被数据库拒绝；无自动级联（R-DELETE-005 / ADR-0004）。
- **产品删除是逻辑删除**（`UPDATE ... SET deleted_at = now()`），它**不触发**任何 FK 的 `ON DELETE` 行为。因此 FK 只服务两个目的：(a) 防止任何越界的物理删除造成引用断裂；(b) 保证引用行物理存在。
- **「父删子拦」（R-DELETE-004）无法由 FK 表达**：FK 看到的是「子行是否存在」，而规则要求的是「**活跃**子行（`deleted_at IS NULL`）是否存在」。子行即使已逻辑删除，其物理行仍在表中，FK 仍会拦截父行的物理删除；反之，只要存在任何子行（含已软删），物理删除就被拦住 —— 这与 R-DELETE-004 的语义（按相对活跃状态判定）**不等价**。
- 因此：**父删子拦必须在应用层（F014 领域服务）实现**，与「不级联」一起在**同一事务**内完成（ADR-0004 §5）。PostgreSQL 没有可用于此的部分外键（partial FK 不存在），替代手段是约束触发器或 `EXCLUDE` 约束 —— 前者被 ADR-0002 / AGENTS.md §2.4 明确排除（把业务规则藏进 Schema）。

### 6. 并发下的父删子拦

架构 Risk #7（「先查后删」在并发下失效）的数据库层可行手段：

| 手段 | 评价 |
|---|---|
| `SERIALIZABLE` 隔离级别 | 能保证正确性，但会引入序列化失败与重试逻辑；对 50 并发的内部低频 CRUD 平台属于过度手段 |
| **`READ COMMITTED` + 显式行锁** ✅ | 针对性强、无重试风控、与本场景匹配 |
| 仅靠 FK | 不适用（见决策 5，FK 无法表达 `deleted_at IS NULL`） |

**选择：PostgreSQL 默认 `READ COMMITTED` + 显式行锁，且加锁必须与读写操作在同一事务内。** 具体协议：

```sql
-- 父软删（例如删除 Cluster），单事务内：
BEGIN;
-- 1) 锁父行，并确认其当前活跃
SELECT id FROM clusters
 WHERE id = :cluster_id AND deleted_at IS NULL
 FOR UPDATE;                       -- 未返回行 → 404 NOT_FOUND
-- 2) 检查活跃子资源
SELECT 1 FROM bare_metals
 WHERE cluster_id = :cluster_id AND deleted_at IS NULL
 LIMIT 1;                          -- 有结果 → 409 CONFLICT，ROLLBACK
-- 3) 无活跃子资源 → 软删
UPDATE clusters SET deleted_at = now(), updated_at = now()
 WHERE id = :cluster_id;
COMMIT;

-- 子资源创建（例如新建 BareMetal），单事务内：
BEGIN;
-- 1') 对父行取共享锁，并确认其活跃（必须加锁，纯 SELECT 不够）
SELECT id FROM clusters
 WHERE id = :cluster_id AND deleted_at IS NULL
 FOR SHARE;                        -- 未返回行 → 父不存在/已删，拒绝创建
-- 2') 插入子资源
INSERT INTO bare_metals (cluster_id, hostname) VALUES (:cluster_id, :hostname);
COMMIT;
```

- 语义：若父删事务先拿到 `FOR UPDATE`，子创建事务的 `FOR SHARE` 会阻塞；父删提交后，子创建事务在 `READ COMMITTED` 下重新求值 `WHERE`，发现父已不存在活跃行 → 拒绝创建。反之若子创建先拿到 `FOR SHARE`，父删的 `FOR UPDATE` 阻塞至子创建提交，随后父删的活跃子检查必然看到新子行 → 拒绝删除。两种交错都不会产生「孤立活跃子资源」。
- 该模式对每一层父子关系通用（Cluster→BareMetal、BareMetal→NetworkInterface、NetworkInterface→IPAddress），且是 F014「逻辑删除与数据一致性治理」的验收内容（架构 Test Work #4）。
- 物理 FK `ON DELETE RESTRICT` 作为第二道防线，独立于上述锁协议。

### 7. 时间字段

| 字段 | 是否采用 | 依据 |
|---|---|---|
| `created_at` / `updated_at` | **采用**（全部资源表 + `users`；`sessions` 用 `created_at` / `expires_at`） | ADR-0001 明确允许 `id / created_at / updated_at / deleted_at` 作为横切列 mixin 复用；API 契约（ADR-0003 §3）对外暴露 RFC 3339 时间字段；资源登记时间是可查询事实（§16） |
| `deleted_at` | **采用**（资源表） | ADR-0004 / R-DELETE-001~006 |
| `created_by` / `updated_by` | **不采用** | 无任何已确认需求要求记录操作者；V1 认证只有「已认证 / 未认证」两态（ADR-0005），无用户级归属语义；§23 排除范围蔓延 |
| `version`（乐观锁） | **不采用** | 无并发编辑冲突的产品需求；50 并发用户、低频 CRUD；`version` 属于「无明确收益不引入」（AGENTS.md §2.6） |
| `audit_log` 表 | **不采用** | 不在 V1 能力范围（§26）；不得因「CMDB 通常都有」而加入（§23） |

### 8. `updated_at` 的维护方式

**选择：应用层维护（SQLAlchemy 2.x `onupdate` / 领域服务显式赋值），不使用数据库触发器。**

理由：

- 触发器会把规则藏进 Schema（AGENTS.md §2.4「业务规则必须显式表达」），且 ADR-0002 已明确排除触发器方案；
- `updated_at` 是元数据，不是数据完整性规则，不需要数据库强制；
- 单写入路径（领域服务 + SQLAlchemy）即可一致维护。

**代价与必须记录的事实**：任何绕过应用层的写（手工 SQL、一次性脚本）不会更新 `updated_at`。因此 **`updated_at` 不得作为审计或并发控制依据**；这一点必须在 Backend Contract 中声明。

`created_at` 同时具有列 `DEFAULT now()`（防止裸 SQL 插入留下 NULL），`updated_at` 亦保留 `DEFAULT now()`；应用层负责后续更新。

---

## Migration Work

> 本次不执行任何 Migration。数据库无既有数据（greenfield），**无需数据迁移**。详细 F012 基线方案见 `docs/database/f012-baseline-migration.md`。

**总体 revision 序列**（Alembic，线性向前）：

| revision | 归属 Feature | 内容 |
|---|---|---|
| `0001_f012_baseline` | F012 | `clusters` 表 + `ck_clusters_name_no_slash` + `ux_clusters_name_active`（骨架验证用显式资源表） |
| `0002_f013_auth` | F013 | `users`、`sessions` |
| `0003_f002_bare_metals` | F002 | `bare_metals` + FK + status CHECK + partial unique + 索引 |
| `0004_f004_network_interfaces` | F004 | `network_interfaces` + FK + 两个 CHECK + 索引 |
| `0005_f005_ip_addresses` | F005 | `ip_addresses` + 两条 FK + partial unique + 索引 |
| `0006+`（延后） | F006 / F007 / F008 | `virtual_machines` / `containers` / `services` + 绑定表 —— **字段待 Product 阶段确认，本次不设计** |

- **是否首次建表**：是（全部）。
- **是否新增字段 / 约束 / 索引**：是（全部，属首次创建）。
- **是否修改已有数据**：否。
- **是否需要数据迁移**：否（空库）。
- **回滚风险**：`downgrade` 会 `DROP TABLE` / `DROP INDEX`，**在已有数据时是破坏性的、且会丢失资源历史**（违反 §25 History Preservation）。生产环境**不得**执行 downgrade；downgrade 仅供开发 / CI 在空库上验证与本地重建。破坏性变更须单独说明回滚策略并经用户确认（AGENTS.md §6 / ADR-0002 §6）。
- PostgreSQL 支持事务性 DDL，Alembic 默认在单事务内执行每个 revision：迁移失败会整体回滚，不留下半成品 Schema。

---

## Backend Contract

Backend 可以依赖以下**由数据库真实保证**的事实：

```text
clusters.name 一定非空，且一定不包含 '/'
同一时间最多存在一条 deleted_at IS NULL 的 clusters.name（大小写敏感）
不同 Cluster 的同名 hostname 合法；同一 Cluster 内活跃 hostname 互不相同（大小写敏感）
同一 Cluster 内活跃 ip_address 互不相同（大小写敏感）；不同 Cluster 可重复
bare_metals.cluster_id 一定指向物理存在的 clusters 行
bare_metals.status 一定属于 {IDLE, ALLOC, DOWN, UNKNOWN}，且永不为 NULL；未显式给值时为 'IDLE'
network_interfaces.bare_metal_id 一定指向物理存在的 bare_metals 行
network_interfaces.technology_type ∈ {Ethernet, InfiniBand, RoCE, Other}
network_interfaces.purpose ∈ {BMC, Management, Business, Compute, Storage, DataTransfer, Other}
ip_addresses.network_interface_id / cluster_id 一定指向物理存在的行
deleted_at IS NULL 是「活跃记录」的唯一判定条件
sessions.token_hash 全局唯一
```

Backend **必须自行保证、不得从数据库假设**的事实：

```text
ip_addresses.cluster_id == （NIC→BareMetal→Cluster 推导结果）
    —— 数据库仅保证 FK 存在性；漂移由受控写入路径 + 一致性测试防止（ADR-0002 / Risk #4）
「父资源存在活跃子资源时不得删除」的软删除拦截（必须在同一事务内对父行加锁）
任何物理删除都不会被产品路径触发（R-DELETE-001）
updated_at 是否准确（应用层维护；不得作为审计依据）
UNCONFIRMED 关系（VM→BareMetal、Container→载体）不得在 API 层被当作必选
```

---

## Verification

以下验证**必须绕过应用层直接对数据库操作**（§21 / 架构 Test Work）。SQLSTATE：唯一性违反 `23505`、FK 违反 `23503`、CHECK 违反 `23514`、NOT NULL 违反 `23502`。

1. **大小写敏感唯一性（R-CLUSTER-002 / §22）**

   ```sql
   INSERT INTO clusters (name) VALUES ('cluster-a');       -- 成功
   INSERT INTO clusters (name) VALUES ('Cluster-A');       -- 必须成功（大小写不同）
   INSERT INTO clusters (name) VALUES ('cluster-a');       -- 必须失败 23505
   SELECT ('cluster-a' = 'Cluster-A');                     -- 必须为 false
   ```

2. **同 Cluster 内 hostname 唯一（R-BM-002）**

   ```sql
   -- 同一 Cluster 内
   INSERT INTO bare_metals (cluster_id, hostname) VALUES (:c1, 'cn001');  -- 成功
   INSERT INTO bare_metals (cluster_id, hostname) VALUES (:c1, 'CN001');  -- 成功（大小写不同）
   INSERT INTO bare_metals (cluster_id, hostname) VALUES (:c1, 'cn001');  -- 必须失败 23505
   -- 不同 Cluster
   INSERT INTO bare_metals (cluster_id, hostname) VALUES (:c2, 'cn001');  -- 必须成功
   ```

3. **软删除释放唯一性（R-DELETE-006）**

   ```sql
   UPDATE clusters SET deleted_at = now() WHERE name = 'cluster-a';
   INSERT INTO clusters (name) VALUES ('cluster-a');       -- 必须成功
   SELECT count(*) FROM clusters
     WHERE name = 'cluster-a' AND deleted_at IS NULL;      -- 必须为 1
   ```

4. **同 Cluster 内 IP 唯一 / 跨 Cluster 可重复（R-IP-001~003）**

   ```sql
   -- 同一 Cluster 的两个不同 NIC 上写同一 IP
   INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address)
     VALUES (:nic_of_c1, :c1, '10.0.0.10');                -- 成功
   INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address)
     VALUES (:other_nic_of_c1, :c1, '10.0.0.10');          -- 必须失败 23505
   -- 不同 Cluster
   INSERT INTO ip_addresses (network_interface_id, cluster_id, ip_address)
     VALUES (:nic_of_c2, :c2, '10.0.0.10');                -- 必须成功
   ```

5. **状态约束（R-BM-003~005）**

   ```sql
   INSERT INTO bare_metals (cluster_id, hostname) VALUES (:c1, 'n1')
     RETURNING status;                                            -- 必须为 'IDLE'
   INSERT INTO bare_metals (cluster_id, hostname, status)
     VALUES (:c1, 'n2', NULL);                                    -- 必须失败 23502
   INSERT INTO bare_metals (cluster_id, hostname, status)
     VALUES (:c1, 'n3', 'BOGUS');                                 -- 必须失败 23514
   UPDATE bare_metals SET status = 'ALLOC' WHERE hostname = 'n1'; -- 成功
   ```

6. **Cluster 名称 `/` 禁令（R-CLUSTER-005）**

   ```sql
   INSERT INTO clusters (name) VALUES ('a/b');             -- 必须失败 23514
   ```

7. **不能创建不存在 Cluster 的 BareMetal（R-BM-001 / FK）**

   ```sql
   INSERT INTO bare_metals (cluster_id, hostname) VALUES (999999999, 'x');  -- 必须失败 23503
   ```

8. **无级联物理删除（R-DELETE-005 / ADR-0004）**

   ```sql
   -- c1 下存在 bare_metals（即使已软删）
   DELETE FROM clusters WHERE id = :c1;                    -- 必须失败 23503（RESTRICT）
   -- 断言 bare_metals 中 c1 的行仍存在
   ```

9. **`ip_addresses.cluster_id` 漂移检测（ADR-0002 / Risk #4）**

   ```sql
   SELECT ip.id
   FROM ip_addresses ip
   JOIN network_interfaces nic ON nic.id = ip.network_interface_id
   JOIN bare_metals bm ON bm.id = nic.bare_metal_id
   WHERE ip.cluster_id <> bm.cluster_id;                   -- 必须为 0 行
   ```

   另需在应用层用例中验证：IP 创建 / NIC 改挂 / BareMetal 改 Cluster 后该查询仍为 0 行（见决策 3 的场景 A~D）。

10. **并发父删子建（Risk #7 / R-DELETE-004）**

    两个并发事务交错执行：T1 软删 Cluster，T2 在该 Cluster 下创建 BareMetal。断言：T1 与 T2 **恰有一个**成功；结束后不存在「活跃 BareMetal 挂在一个已软删 Cluster 下」的行：

    ```sql
    SELECT count(*) FROM bare_metals bm
    JOIN clusters c ON c.id = bm.cluster_id
    WHERE bm.deleted_at IS NULL AND c.deleted_at IS NOT NULL;   -- 必须为 0
    ```

11. **中文往返（§21 / 架构 Verification #6）**

    ```sql
    INSERT INTO clusters (name) VALUES ('高性能计算集群-A');   -- 成功
    SELECT name FROM clusters WHERE name = '高性能计算集群-A';  -- 命中
    ```

12. **约束/索引实际存在（Schema 断言）**

    ```sql
    SELECT indexname FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname IN ('ux_clusters_name_active',
                        'ux_bare_metals_cluster_hostname_active',
                        'ux_ip_addresses_cluster_ip_active');   -- 必须 3 行
    ```

13. **Migration 可重复应用 / 可从空库重建（F012 AC）**

    ```bash
    alembic upgrade head        # 空库 → 成功
    alembic upgrade head        # 重复应用 → no-op，无错误
    alembic downgrade base && alembic upgrade head   # 空库重建 → 成功
    ```

14. **认证相关（ADR-0005）**

    ```sql
    INSERT INTO users (username, password_hash) VALUES ('admin', '$argon2id$...');  -- 成功
    INSERT INTO users (username, password_hash) VALUES ('admin', '$argon2id$...');  -- 必须失败 23505
    INSERT INTO sessions (user_id, token_hash, expires_at)
      VALUES (:uid, 'h1', now() + interval '8 hours');                              -- 成功
    INSERT INTO sessions (user_id, token_hash, expires_at)
      VALUES (:uid, 'h1', now() + interval '8 hours');                              -- 必须失败 23505
    -- 断言：password_hash 列中不存在明文口令（应用层测试）
    ```

---

## Open Questions

### Blocking

**无。**

本设计覆盖的实体（Cluster / BareMetal / NetworkInterface / IPAddress / users / sessions）的核心业务关系、唯一性边界、状态模型、删除语义与认证范围**均已由 CONFIRMED 产品文档、`READY FOR IMPLEMENTATION` 的 Architecture Handoff 与 5 条 ACCEPTED ADR 确定**，不存在会使 Schema 不确定的阻塞项。

- BareMetal 仅设计生产核心字段（hostname / cluster 归属 / status）；硬件字段属 OPEN-004，**本次不设计的列不会使已设计的列不确定**，且 OPEN-004 归属 F002 Product 阶段（`project-plan.yaml`）。
- VirtualMachine / Container / Service 表延期设计，不影响本批 4 张资源表与 2 张认证表的确定性。

### Non-blocking

1. **OPEN-004（BareMetal 硬件字段）延后到 F002 的 Product 阶段** —— 归属 `project-plan.yaml` F002；本设计**故意不包含**任何 CPU / Memory / GPU / Storage / Vendor / Model / Serial Number 列。字段确认后以**新增列**的增量 migration 落地（可空列或带默认值的非空列），对本设计无破坏。
2. **OPEN-001 / OPEN-002 / OPEN-003（VM / Container / Service 字段与粒度）延后到对应 Feature 的 Product 阶段** —— `virtual_machines` / `containers` / `services` 表本次**不设计、不给出字段清单**。未来接入时的模式（仅说明模式，不涉字段）：
   - Service 与 Cluster 的关联由运行载体推导，**不得**落 `service.cluster_id`（R-SVC-004 / R-SVC-006）；Service↔Host 需一张绑定表（N:M）；
   - 若未来某一资源（如 VirtualMachine）也需要「同 Cluster 内唯一」的名称 / 地址，可复用与 `ip_addresses.cluster_id` 相同的**反规范化 `cluster_id` + 受控写入路径 + 一致性测试**模式；是否反规范化须在其 Product 阶段依唯一性边界决定，**不得预先落地**；
   - VM→BareMetal、Container→载体在 DDL 中**不得**默认 `NOT NULL`（DEC-004 / DEC-005 归属 F006 / F007）。
3. **NIC 名称在同一 BareMetal 内是否唯一**未确认 → 当前**无唯一约束**；如需，属 F004 产品确认后新增 partial unique index。
4. **`ip_address` 的格式校验与归一化**未确认 → 当前为 `TEXT`，无格式 CHECK；未来若确认应校验为合法 IP（含 / 不此前缀），需产品确认后再引入（`inet` 类型切换属语义变更，不可静默进行）。
5. **Cluster 名称 / hostname 的长度、首尾空白、空字符串、Unicode NFC 规范化**未确认（domain-model `undefined_constraints`）→ 当前无 CHECK；NFC 归一化架构已记为 Non-blocking「当前不做」。
6. ~~**`username` 唯一性是否大小写敏感**未确认~~ → **✅ 已关闭（2026-09-15，R-AUTH-005）**：确认**区分大小写**。当前按数据库默认 collation（大小写敏感）的普通 `UNIQUE` 实现即正确，**无需变更**；不得用 `lower()` 静默替换。
7. **BareMetal 是否允许改属 Cluster**未确认 → 若允许，领域服务必须同步重算其下全部 IP 的 `cluster_id`；若不允许，后端必须拒绝。两种选择都不改变本 Schema（列为行为契约，不改变 DDL）。
8. **会话过期时间与是否滑动续期**未由 ADR-0005 确定（留给实现阶段并需记录）→ 影响是否使用 `sessions.last_seen_at`（已按 PROPOSED 保留为可空列）。
9. **`created_by` / `updated_by` / `version` / `audit_log`** 当前无需求依据 → 不引入；若未来需要审计，属新产品需求。
10. **`NULLS NOT DISTINCT`** 在本设计下为 no-op（被索引列全为 NOT NULL），已明确不添加；若未来引入可空唯一列需重新评估。
11. ~~**【需产品方裁定】`IPAddress → NetworkInterface` 必选性的文档冲突**~~ → **✅ 已裁定（2026-09-15）**：用户确认 IP 必须绑定在 NetworkInterface 上，关系为 **Mandatory**。`NOT NULL` 保留，**DDL 不变**。`requirements.md` §15 与 `domain-model.yaml` 已同步，冲突消除。
12. ~~**NIC 枚举是封闭集合，但 R-NIC-001 / R-NIC-002 的措辞是「至少能够表达」**~~ → **✅ 已裁定（2026-09-15）**：用户明确 `technology_type` 即为 **Ethernet / InfiniBand / RoCE / Other 四种**，`purpose` 同属封闭集合。原文「至少能够表达」现解释为「内部枚举固定」。**`CHECK` 约束保留，DDL 不变。** 新增取值须重新走需求确认流程（同 R-BM-003）。