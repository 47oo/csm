# F012 基线 Migration 方案

> **Database Handoff**
> Status: `READY FOR DATABASE IMPLEMENTATION`
> Author Role: database
> Date: 2026-09-15
> 配套文档：`docs/database/csm-v1-schema-design.md`（权威 Schema）
>
> 本文档是 F012「项目基础框架与运行环境」的数据库交付规格。**不包含实际 Python 代码文件**，只给出结构、顺序、DDL 规格、回滚风险与 Backend 在 Alembic 中必须完成的事项。

---

## 1. 目的与范围

F012 的验收内容包含「可运行验证骨架」（架构文档「技术栈验证骨架」），其数据库侧判据为：

1. 数据库连接可用，**基线 migration 可应用、可重复应用、可从空库重建**；
2. 建立**一张显式资源表**（架构建议直接用 `cluster`），并可验证：大小写敏感 collation 生效、partial unique index 生效、**绕过应用层直接插入重复数据被拒绝**。

因此 F012 基线 migration 的职责是：

- 建立 Alembic 框架（配置 + `env.py` + `versions/`）；
- 创建**最小可跑通集合**：`clusters` 一张资源表及其约束/索引；
- 固定命名约定、迁移执行方式与验证手段，供 F001~F014 复用。

**不在 F012 范围**：其余资源表、认证表、领域服务、API、前端。

---

## 2. 最小可跑通集合（明确结论）

| 组成 | 是否必须 | 说明 |
|---|---|---|
| Alembic 配置（`alembic.ini` + `env.py` + `script.py.mako`） | ✅ 必须 | 版本化 migration 的基础 |
| `alembic_version` 表 | ✅ 自动 | Alembic 自动创建，无需手写 |
| PostgreSQL 扩展（extension） | ❌ 不需要 | 无 `uuid-ossp` / `pgcrypto` / `citext` 需求；identity 用原生 `GENERATED ... AS IDENTITY`，会话令牌哈希在应用层用 Argon2 / SHA 处理 |
| `clusters` 表（含 `id` / `name` / `created_at` / `updated_at` / `deleted_at`） | ✅ 必须 | 骨架验证所需的「一张显式资源表」 |
| `ck_clusters_name_no_slash` | ✅ 必须 | 顺带固化 R-CLUSTER-005 的数据库层校验，成本为零 |
| `ux_clusters_name_active`（partial unique index） | ✅ 必须 | 骨架判据 #3 直接验证的两个最易「选错难回退」的点之一 |
| `bare_metals` / `network_interfaces` / `ip_addresses` / `users` / `sessions` | ❌ 不在基线 | 归 F002 / F004 / F005 / F013 各自的 migration |

**结论：F012 基线 migration 的最小可跑通集合 = 1 个 revision `0001_f012_baseline`，创建 `clusters` 表 + 1 个 CHECK + 1 个 partial unique index。** 这已足以完成架构「技术栈验证骨架」的第 2、3 条判据。

> F012 基线**只创建 `clusters`**，因此 **F001 不创建新表**：F001 交付的是 Cluster 的领域校验 / CRUD / `by-name` 别名等 API 能力（AC 见 `project-plan.yaml` F001），其表结构由本设计规定并在基线建立。若 F001 后续确需新增 Cluster 列（例如产品补充字段），走**增量** revision（可空列或带默认值），不改基线。

---

## 3. Revision 序列与顺序

```text
alembic_version
  0001_f012_baseline                 (F012)  clusters
  └─ 0002_f013_auth                  (F013)  users, sessions
     └─ 0003_f002_bare_metals        (F002)  bare_metals
        └─ 0004_f004_network_interfaces (F004) network_interfaces
           └─ 0005_f005_ip_addresses    (F005) ip_addresses
              └─ 0006_f006_...          (延后, Product 未确认)
              └─ 0007_f007_...          (延后)
              └─ 0008_f008_...          (延后)
```

- **Alembic 配置为单一线性 head**（`down_revision` 串成一条链），不使用多 head / merge，避免 4 个实现分支并行时产生分支与 merge revision。
- 依赖顺序即产品/架构依赖顺序：`bare_metals` 需要 `clusters`；`network_interfaces` 需要 `bare_metals`；`ip_addresses` 需要 `network_interfaces` 与 `clusters`。
- `0002_f013_auth` 与 `0003_f002_bare_metals` 相互独立，但为保持线性 head，`0003` 的 `down_revision` 指向 `0002`。

---

## 4. 各 revision 的 DDL 规格

### `0001_f012_baseline`（F012）

```sql
CREATE TABLE clusters (
  id          BIGINT GENERATED ALWAYS AS IDENTITY,
  name        TEXT        NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ NULL,
  CONSTRAINT pk_clusters PRIMARY KEY (id),
  CONSTRAINT ck_clusters_name_no_slash CHECK (strpos(name, '/') = 0)
);

CREATE UNIQUE INDEX ux_clusters_name_active
  ON clusters (name)
  WHERE deleted_at IS NULL;
```

- 无 FK、无状态列、无长度/空白约束（未确认，见 Schema 设计 Open Questions）。
- 无显式 `COLLATE` 子句（ADR-0002 选项 1）。
- `downgrade`：`DROP INDEX ux_clusters_name_active; DROP TABLE clusters;`

### `0002_f013_auth`（F013）

```sql
CREATE TABLE users (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  username      TEXT        NOT NULL,
  password_hash TEXT        NOT NULL,
  active        BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT pk_users PRIMARY KEY (id),
  CONSTRAINT ux_users_username UNIQUE (username)
);

CREATE TABLE sessions (
  id           BIGINT GENERATED ALWAYS AS IDENTITY,
  user_id      BIGINT      NOT NULL,
  token_hash   TEXT        NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NULL,               -- OPTIONAL / PROPOSED
  CONSTRAINT pk_sessions PRIMARY KEY (id),
  CONSTRAINT ux_sessions_token_hash UNIQUE (token_hash),
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX ix_sessions_user_id   ON sessions (user_id);
CREATE INDEX ix_sessions_expires_at ON sessions (expires_at);
```

- `downgrade` 顺序：先 `sessions` 后 `users`（先删子表，避免 FK 依赖）。

### `0003_f002_bare_metals`（F002）

```sql
CREATE TABLE bare_metals (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  cluster_id    BIGINT      NOT NULL,
  hostname      TEXT        NOT NULL,
  status        TEXT        NOT NULL DEFAULT 'IDLE',
  vendor        TEXT        NULL,          -- R-BM-007
  model         TEXT        NULL,          -- R-BM-007
  serial_number TEXT        NULL,          -- R-BM-007（不参与唯一性）
  cpu           TEXT        NULL,          -- R-BM-007
  memory        TEXT        NULL,          -- R-BM-007
  gpu           TEXT        NULL,          -- R-BM-007
  storage       TEXT        NULL,          -- R-BM-007
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ NULL,
  CONSTRAINT pk_bare_metals PRIMARY KEY (id),
  CONSTRAINT fk_bare_metals_cluster FOREIGN KEY (cluster_id)
    REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_bare_metals_status
    CHECK (status IN ('IDLE', 'ALLOC', 'DOWN', 'UNKNOWN'))
);

CREATE UNIQUE INDEX ux_bare_metals_cluster_hostname_active
  ON bare_metals (cluster_id, hostname)
  WHERE deleted_at IS NULL;

CREATE INDEX ix_bare_metals_cluster_id ON bare_metals (cluster_id);
```

### `0004_f004_network_interfaces`（F004）

```sql
CREATE TABLE network_interfaces (
  id              BIGINT GENERATED ALWAYS AS IDENTITY,
  bare_metal_id   BIGINT      NOT NULL,
  name            TEXT        NOT NULL,
  technology_type TEXT        NOT NULL,
  purpose         TEXT        NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ NULL,
  CONSTRAINT pk_network_interfaces PRIMARY KEY (id),
  CONSTRAINT fk_network_interfaces_bare_metal FOREIGN KEY (bare_metal_id)
    REFERENCES bare_metals (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_network_interfaces_technology_type
    CHECK (technology_type IN ('Ethernet', 'InfiniBand', 'RoCE', 'Other')),
  CONSTRAINT ck_network_interfaces_purpose
    CHECK (purpose IN ('BMC', 'Management', 'Business', 'Compute', 'Storage', 'DataTransfer', 'Other'))
);

CREATE INDEX ix_network_interfaces_bare_metal_id
  ON network_interfaces (bare_metal_id);
```

### `0005_f005_ip_addresses`（F005）

```sql
CREATE TABLE ip_addresses (
  id                   BIGINT GENERATED ALWAYS AS IDENTITY,
  network_interface_id BIGINT      NOT NULL,
  cluster_id           BIGINT      NOT NULL,
  ip_address           TEXT        NOT NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at           TIMESTAMPTZ NULL,
  CONSTRAINT pk_ip_addresses PRIMARY KEY (id),
  CONSTRAINT fk_ip_addresses_network_interface FOREIGN KEY (network_interface_id)
    REFERENCES network_interfaces (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_ip_addresses_cluster FOREIGN KEY (cluster_id)
    REFERENCES clusters (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE UNIQUE INDEX ux_ip_addresses_cluster_ip_active
  ON ip_addresses (cluster_id, ip_address)
  WHERE deleted_at IS NULL;

CREATE INDEX ix_ip_addresses_cluster_id
  ON ip_addresses (cluster_id);

CREATE INDEX ix_ip_addresses_network_interface_id
  ON ip_addresses (network_interface_id);
```

> 每个 revision 的 `downgrade` 为对应 `DROP TABLE`（自动级联删除其约束与索引）；顺序必须与 `upgrade` 相反。

---

## 5. Alembic 配置与命名约定（Backend 必做）

1. **`env.py`**
   - 从应用配置读取数据库 URL（环境变量 / `.env`），不在 `alembic.ini` 硬编码生产密码；
   - `target_metadata = Base.metadata`；
   - 使用 `sqlalchemy.url` 与 `pool` 选项，`compare_type=True`；
   - **不需要** `render_as_batch`（PostgreSQL 原生支持 `ALTER`）。
2. **命名约定**（必须配置，否则 autogenerate 与 downgrade 的约束名不稳定）：

   ```python
   NAMING_CONVENTION = {
       "ix": "ix_%(table_name)s_%(column_0_N_name)s",
       "uq": "ux_%(table_name)s_%(column_0_N_name)s",
       "ck": "ck_%(table_name)s_%(constraint_name)s",
       "fk": "fk_%(table_name)s_%(column_0_N_name)s",
       "pk": "pk_%(table_name)s",
   }
   ```
   与本设计中的 `pk_` / `fk_` / `ux_` / `ix_` / `ck_` 命名一致，保证 migration 与 Schema 设计文档可逐条对照。
3. **partial unique index 必须在 migration 中显式书写 `postgresql_where`**（SQLAlchemy `Index(..., postgresql_where=sa.text("deleted_at IS NULL"))`）。不得依赖 autogenerate 推断 predicate，且 `DROP INDEX` 必须写全名。
4. **identity 列**使用 `sa.Identity(always=True)`（对应 `GENERATED ALWAYS AS IDENTITY`），应用层不得显式写入 `id`。
5. **时间列**使用 `server_default=sa.text("now()")`，`TIMESTAMPTZ`。
6. **不写 `COLLATE`**：任何列 / 索引不得带 collation 参数。
7. **不使用触发器**：`updated_at` 由应用层维护（见 Schema 设计 决策 8）。
8. **不在 migration 中创建 database / role / extension**：数据库与账号由部署（docker-compose / 初始化脚本）负责，且必须固定 locale（见下）。

---

## 6. 幂等 / 可重复应用 / 空库重建

- **可应用**：`alembic upgrade head` 对空库一次成功。
- **可重复应用**：再次 `alembic upgrade head` 为 no-op（`alembic_version` 已记录 head，不做任何 DDL）。
- **可从空库重建**：`alembic downgrade base` 后再 `alembic upgrade head` 成功；或在 CI 中 drop schema 后重跑。
- PostgreSQL 事务性 DDL + Alembic 默认事务：任一 revision 失败整体回滚，不残留半成品对象。

验收命令：

```bash
alembic upgrade head
alembic upgrade head                       # 重复应用 → 成功且无变化
alembic current                            # 显示 head
alembic downgrade base && alembic upgrade head
```

---

## 7. 数据迁移需求

**无。** 绿色字段启动，库中无既有数据；基线为首次建表，不存在数据回填、类型转换、唯一性冲突清理。

（F002 的 R-BM-007 硬件字段已随 `0003_f002_bare_metals` 首次建表一并创建，**不涉及新增列或数据回填**；F006/F007/F008 的新表为**新增表**，无需数据迁移；破坏性变更须单独说明并经用户确认。）

---

## 8. 回滚风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| `downgrade` 破坏性 | 每个 downgrade 为 `DROP TABLE` / `DROP INDEX`，**会永久丢失资源历史**（违反 §25 History Preservation 的意图） | 生产环境**禁止** downgrade；仅限开发 / CI 空库。破坏性变更须单独说明回滚策略并经用户确认（AGENTS.md §6 / ADR-0002 §6） |
| 顺序错误 | 违反 FK 依赖的 downgrade（先删 `clusters` 再删 `bare_metals`）会因 FK 失败 | 每个 `downgrade` 严格按 `upgrade` 逆序；由 revision 链 `down_revision` 保证执行顺序 |
| 约束名漂移 | 未配置命名约定时，autogenerate 生成的名字不稳定，导致 downgrade 找不到对象 | 配置 `NAMING_CONVENTION`（见 §5）；migration 中所有 DDL 显式书写名 |
| locale 漂移 | 部署环境 locale 变化会改变排序（不影响等值比较），并可能使「大小写敏感」断言失效 | 部署文档固定 locale（§9）；CI 中对既有库执行 `SELECT ('cluster-a' = 'Cluster-A')` 与约束回归断言 |
| partial index predicate 与查询过滤错位 | 若查询未附加 `deleted_at IS NULL`，会出现「查得到却写不进」 | 由 F014 统一软删除过滤基座强制；测试覆盖 |
| 基线只建 `clusters` | 若后置 Feature 误以为基线已建全表，可能产生重复建表 | 本文档与 `csm-v1-schema-design.md` 的 revision 表为唯一权威；各 Feature migration 只创建自己负责的表 |

---

## 9. Backend 必须在 Alembic 中完成的事项（Checklist）

- [ ] 建立 Alembic 目录结构（`alembic.ini`、`env.py`、`script.py.mako`、`versions/`），支持从应用配置 / 环境变量读取数据库 URL。
- [ ] 配置 `NAMING_CONVENTION`（§5.2），并确保 `Base.metadata` 使用同一约定。
- [ ] 创建 revision `0001_f012_baseline`：`clusters` 表 + `ck_clusters_name_no_slash` + `ux_clusters_name_active`（§4）。
- [ ] 编写并执行 §6 的四条验收命令，确认可应用 / 可重复应用 / 可重建。
- [ ] 编写数据库级自动化测试（绕过应用层，直接连接数据库），覆盖：
  - `cluster-a` 与 `Cluster-A` 可共存；
  - 活跃同名重复被拒绝（`23505`）；
  - 软删后可重建同名（R-DELETE-006）；
  - `name` 含 `/` 被拒绝（`23514`）；
  - `SELECT ('cluster-a' = 'Cluster-A')` 为 `false`。
- [ ] 部署文档（F015 交付）记录数据库 locale / encoding 要求、`datcollate` / `datctype` 期望值、PostgreSQL 大版本，以及「该环境中大小写敏感回归测试必须通过」的要求（架构 Risk #1）。
- [ ] 后续 revision（`0002`~`0005`）按 §3 / §4 顺序提交，每个 revision 只创建自己负责的表，不改动基线（`0001` 一经合入即冻结）。
- [ ] 数据访问层统一提供 `deleted_at IS NULL` 过滤基座（F014），并与 partial index 的 predicate 保持一致。
- [ ] 不引入触发器；`updated_at` 由应用层维护。
- [ ] 不创建任何 extension；数据库 / role / locale 由部署层负责。

---

## 10. 不做什么（本次明确排除）

- 不编写实际 Python migration 代码文件；
- 不执行任何 migration、不修改数据库；
- 不为 VM / Container / Service 建表或定义字段（OPEN-001~003 / DEC-004 / DEC-005 未确认）；
- 不引入 EAV / 通用 `resources` 表 / STI / JSONB 万能模型；
- 不使用 `ON DELETE CASCADE`、不使用触发器、不声明 `COLLATE`；
- 不为未确认字段（硬件字段、长度、格式、大小写不敏感）建立约束。