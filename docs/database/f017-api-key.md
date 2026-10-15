# F017 API Key 机器凭据 — DATABASE 设计

- **签核**：Database；阶段 DATABASE；设计版本 v1（2026-10-14）
- **结论**：`READY FOR DATABASE IMPLEMENTATION`（无 DB 侧阻塞；F017-OPEN-1/OPEN-3 为 Product 未决、非本 Gate 阻塞，见 §9）
- **覆盖**：`api_keys` 新表、`audit_logs.api_key_label` 增列、迁移 `0014_api_keys`、约束/索引裁定、数据完整性对应表、真实 PostgreSQL 验证清单、Backend 可依赖保证与 Tester 测试项、DB-D301–DB-D316 决策。
- **不覆盖**：认证 seam / CSRF / 端点 / 前端实现（Architect / Backend / Frontend）；`docs/api/F017.md` 定稿；TEST 执行；F002/F015 契约修订文本（协调器按变更控制同步）。

## 1. 元信息与依据（Basis）

| 类别 | 依据（版本） |
| --- | --- |
| 需求（CONFIRMED） | `docs/product/requirements-v3.md` **revision 4**：§23.1 API Key 机器凭据、§22 Audit Log、§23 用户与权限、§21 逻辑删除、§26 数据库、§27 数据完整性、§31 T42–T49、§32 上线验收、§35.1 确认记录 |
| Product | `docs/features/F017/product.md`（PRODUCT `READY FOR ARCHITECT`，A1–A8 ↔ T42–T49，无 Blocking Questions） |
| Architecture | `docs/features/F017/architecture.md`（ARCHITECTURE `READY FOR DESIGN` 2026-10-14；DR-301–DR-318，尤其 DR-305/306/307/308/314/315/316；§5.1–§5.5 Database 影响与签核清单） |
| 共享约定 | `docs/architecture/d01-conventions.md` **v11**（§1 稳定 ID / §2 时间；`label` 非业务对象名，不并入 §5 名称表） |
| 既有 DB 设计 | `docs/database/f002-auth.md` **v1**（DB-D13–DB-D19：UUID `gen_random_uuid()`、timestamptz/UTC、FK RESTRICT、SHA-256 hex 范式、迁移对称可逆）；`docs/database/f003-cluster.md` v2（DB-D27/DB-D28：audit 多态无 FK、append-only 触发器）；`docs/database/f015-audit-admin.md` v1（DB-D167–DB-D172：`object_type` 无 CHECK 注册表、append-only、FK RESTRICT）；`docs/database/f016-acceptance.md` v1（DB-D173–DB-D176） |
| 迁移链 | `backend/alembic/versions/`；当前 **head = `0013_search_indexes`**，线性无分叉 |
| 实现现状 | `backend/app/models/{user,session,audit_log,base}.py`（命名约定 DB-D6、`SoftDeleteMixin` 仅业务对象、audit append-only 模型） |
| 方法 | `.pi/skills/data-integrity/SKILL.md`；`docs/project/{handoff,change-control,project-state,implementation-rules}.md`；F001 DB-D7（迁移规范/破坏性记录） |
| Git | 本次为只读设计签核，未修改文件、未执行 Git 状态变更 |

**DB-D 编号说明**：物理上 F015 段止于 DB-D172、F016 段为 DB-D173–DB-D176。本 Feature 按任务约定开启 **DB-D301–DB-D316**（与 F017 architecture DR-301 段对齐，避免与相邻 Feature 段混淆）。若协调器要求保持全局连续编号，可将下表整体平移为 DB-D177–DB-D192，内容与结论不变。

---

## 2. `api_keys` 表设计

新持久对象，**不属 §21 业务对象集合**，采用吊销语义，不继承 `SoftDeleteMixin`（依据 §23.1、§21、DR-305）。

### 2.1 列、类型、可空、默认

| 列 | 类型 | 空 | 默认 | 约束（全名） |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | NOT NULL | `gen_random_uuid()` | PK `pk_api_keys` |
| `user_id` | `UUID` | NOT NULL | — | FK `fk_api_keys_user_id_users` → `users.id` `ON DELETE RESTRICT` |
| `label` | `varchar(255)` | NOT NULL | — | CHECK `ck_api_keys_label_not_blank`：`btrim(label) <> ''` |
| `key_hash` | `varchar(64)` | NOT NULL | — | UNIQUE `uq_api_keys_key_hash`；CHECK `ck_api_keys_key_hash_format`：`key_hash ~ '^[0-9a-f]{64}$'` |
| `created_by` | `UUID` | NOT NULL | — | FK `fk_api_keys_created_by_users` → `users.id` `ON DELETE RESTRICT` |
| `created_at` | `timestamptz` | NOT NULL | `now()` | UTC（D01 §2） |
| `expires_at` | `timestamptz` | NOT NULL | — | CHECK `ck_api_keys_expires_after_created`：`expires_at > created_at`；CHECK `ck_api_keys_expires_within_max`（见 §2.3） |
| `revoked_at` | `timestamptz` | NULL | — | CHECK `ck_api_keys_revoked_after_created`：`revoked_at IS NULL OR revoked_at >= created_at` |

### 2.2 索引

| 索引名 | 表 | 列 | 类型 | 服务查询/约束 |
| --- | --- | --- | --- | --- |
| `pk_api_keys` | `api_keys` | `id` | PK btree | 主键 |
| `uq_api_keys_key_hash` | `api_keys` | `key_hash` | UNIQUE btree | **认证等值查找 O(1)**（DR-307）、并发创建不重复 |
| `ix_api_keys_user_id` | `api_keys` | `user_id` | btree | 列表按账号过滤（`user_id`）；PG 不自动为 FK 建索引；RESTRICT 校验路径 |
| `ix_api_keys_created_by` | `api_keys` | `created_by` | btree | FK 支撑（RESTRICT 检查、未来按创建人查询）；沿用 F002 显式索引 FK 范式（DB-D16） |

**不建**：`expires_at` 索引（无惰性清理/批量扫描，认证按 `key_hash` 命中，DR-307）；`label` 索引（无唯一/过滤要求）；`(user_id, label)` 唯一（见 §9 F017-OPEN-3）。

### 2.3 有效期上限 backstop 与时钟偏差口径（DR-308 定稿）

- 权威业务校验在应用层：`validity_days` 整数 **1..365**（含端点），显式 `null`/`0`/负/`>365`/非整数 → 422（A7/T48）。
- DB backstop：`ck_api_keys_expires_within_max` = `expires_at <= created_at + interval '365 days' + interval '5 minutes'`。
  - `created_at` 为 `server_default now()`，在事务内等于 `transaction_timestamp()`，事务内稳定。
  - **要求**：服务端须以**同一事务内的数据库 `now()`**派生 `expires_at`（`expires_at = transaction_timestamp() + make_interval(days => :validity_days)`，或先 `SELECT now()` 再计算）。此时时钟同源，365 天边界精确成立。
  - `+ interval '5 minutes'` 为**时钟偏差容差**，仅在实现误用应用进程时钟（可能走快）时避免把合法的 365 天请求误判为 CheckViolation（表现为 500）。容差只放宽 DB 兜底，不放宽应用侧 `>365 → 422` 的权威上限；365 天+5 分钟是最坏 5 分钟的安全裕度，不构成对 §23.1「上限 365 天」的产品偏离。
- 不提供「永不过期」；`expires_at` NOT NULL。

### 2.4 为何无 `deleted_at` / `version` / `last_used_at`（DR-305 定稿）

| 未采用列 | 理由 | 依据 |
| --- | --- | --- |
| `deleted_at` | API Key **不纳入 §21 业务对象软删除/恢复**，采用吊销语义（`revoked_at`）。`SoftDeleteMixin` 仅用于业务对象（`base.py`），`api_keys` 不得继承。 | §23.1、§21、DB-D26 |
| `version` | 无 PATCH/更新端点（label/有效期不可改），无乐观锁比较-写入路径；预建 `version` 属无需求支撑的过度设计（AGENTS §2.6）。 | DR-301/DR-313（不可更新）、AGENTS §2.6 |
| `last_used_at` | §23.1 未要求；每次认证命中都会写该列，将在**最热的认证读路径**上产生行写放大与锁竞争，且与 append-only 审计职责重叠（使用痕迹由 `audit_logs` 承载）。不预建。 | §23.1、§22、DR-307 |

---

## 3. `audit_logs.api_key_label` 增列设计（DR-306 定稿）

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| `api_key_label` | `varchar(255)` | NULL | — | CHECK `ck_audit_logs_api_key_label_not_blank`：`api_key_label IS NULL OR btrim(api_key_label) <> ''` |

- **nullable、无默认**：Cookie / system 操作为 NULL；写入由 `audit.record` 取 `operator.api_key_label`（DR-315）。
- **无 FK**：存的是 operator 的 Key **标签快照**（与 `operator_username` 快照范式一致，DB-D27/DB-D167），不是 `api_keys.id`。审计须在 Key 吊销、甚至账号停用后继续可解析；FK 会引入错误的引用语义。
- **append-only 兼容**：`ALTER TABLE audit_logs ADD COLUMN api_key_label varchar(255) NULL`（PG 11+）为**元数据级变更**、无表重写、无默认回填；`trg_audit_logs_append_only` 为 `BEFORE UPDATE OR DELETE FOR EACH ROW`，`ALTER TABLE` 不触发行级触发器。既有索引与触发器/函数**不变**。
- **既有行回填 NULL**：ADD COLUMN nullable 无 DEFAULT，既有行自动为 NULL，**无需显式回填**。
- **长度一致性**：255 与 `api_keys.label varchar(255)` 一致（PG `varchar(255)` 按字符计，与应用 Unicode code point 口径一致，D01 §5.2）。
- **是否加索引**：**不建**。审计查询不以 `api_key_label` 为过滤键；对 append-only 最热写路径加二级索引永久累积写放大，收益无需求支撑（沿用 F015 DB-D168 口径）。
- **not-blank CHECK**：**加**（nullable-safe）。成本极低、与 `ck_audit_logs_operator_username_not_blank` 一致，作为标签非空的 DB backstop。

---

## 4. Migration `0014_api_keys`

### 4.1 revision 链

```text
revision      = "0014_api_keys"
down_revision = "0013_search_indexes"
branch_labels = None
depends_on    = None
```
- 单一 head；不改已发布 revision（DB-D7）。迁移后 `alembic heads` 唯一 = `0014_api_keys`。

### 4.2 upgrade 顺序

1. `op.create_table("api_keys", ...)` —— 建表 + PK + 两 FK + UNIQUE/CHECK 集（`users` 已由 0002 建立，FK 前置满足）。
2. `op.create_index("ix_api_keys_user_id", ...)`、`op.create_index("ix_api_keys_created_by", ...)`。
3. `op.add_column("audit_logs", Column("api_key_label", String(255), nullable=True))`。
4. `op.create_check_constraint("ck_audit_logs_api_key_label_not_blank", "audit_logs", "api_key_label IS NULL OR btrim(api_key_label) <> ''")`。

### 4.3 downgrade 逆序

1. `op.drop_constraint("ck_audit_logs_api_key_label_not_blank", "audit_logs", type_="check")`
2. `op.drop_column("audit_logs", "api_key_label")`
3. `op.drop_index("ix_api_keys_created_by", table_name="api_keys")`、`op.drop_index("ix_api_keys_user_id", table_name="api_keys")`
4. `op.drop_table("api_keys")`（索引随表；显式先 drop 保证对称）

### 4.4 可逆性与破坏性边界（DB-D7 / DR-314）

- **结构可逆**：`up/down/up` 对称，真 PG 执行验证（§6）。`down` 后 Schema 回到 `0013` head 的等价状态。
- **数据破坏性边界**：`downgrade` 丢弃 `api_keys` 全表（F017 自有数据）与 `audit_logs.api_key_label` 列（**仅 F017 写入的值**；既有审计行的其余列不变）。属破坏性操作，按 **DB-D7** 显式记录：
  - **生产回滚不得使用 `downgrade`**，须以 F001 全库备份恢复；
  - `downgrade` 仅用于开发/测试 `up/down/up`。
- **回填风险**：无。新表无既有数据；`api_key_label` nullable 无默认，既有行自动 NULL。
- **升级风险**：`api_keys` 为空表建约束/索引无锁表风险；`audit_logs` ADD COLUMN 为元数据操作，不重写大表。

### 4.5 手写 DDL 理由（DB-D6/DB-D7）

- autogenerate **不识别 CHECK 约束**（`~`、`interval`、`IS NULL OR` 表达式），也不识别 `gen_random_uuid()` server_default 与约束全名的命名约定语义；F001 DB-D7 要求扩展/表达式项手写。
- 约束/索引**显式给全名**，并以 `op.f()` 包裹，避免迁移 metadata 再次套用 `Base.metadata` 命名约定导致重复前缀。
- 命名遵循 DB-D6：`pk_api_keys`、`fk_api_keys_<col>_users`、`uq_api_keys_key_hash`、`ck_api_keys_<name>`、`ck_audit_logs_api_key_label_not_blank`、`ix_api_keys_<col>`。

---

## 5. 数据完整性对应表（F017 适用项）

| 规则依据及版本 | 作用域 / 写入入口 | 数据库保证 | 业务层保证 | 并发 / 生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §23.1 / §21（rev4）；DR-305 | `api_keys` 生命周期 | 无 `deleted_at`/`version`；`revoked_at` + CHECK；吊销=置 `revoked_at`，无 DELETE 路径 | 端点仅 create/list/detail/revoke；无 PATCH/DELETE；停用即时失效（认证查 `join users.status='ACTIVE'`） | 不纳入软删/恢复；不可重新启用 | V-DB-F017-1/6/9 |
| §23.1 / §27；DR-309 | Key 凭据存储 | `key_hash` UNIQUE + `^[0-9a-f]{64}$` CHECK；无明文列 | token=`csm_ak_`+`token_urlsafe(32)`；仅存 SHA-256 hex；明文仅 201 一次 | 并发创建不同 hash；UNIQUE 兜底 | V-DB-F017-2/3；T46 |
| §23.1；DR-305 | `label` | `varchar(255)` NOT NULL + not-blank CHECK | trim 后非空、禁 Cc/Cf、1..255；不要求唯一 | 无生命周期变更 | V-DB-F017-2 |
| §23.1 / §26；DR-308 | 有效期 | `expires_at` CHECK `> created_at` 且 `<= created_at + 365d + 5min` | 整数 1..365（缺省 90）；>365/0/负/null/非整数→422；无永不过期 | `expires_at <= now()` 视为失效 | V-DB-F017-2/9；T48 |
| §23.1 / T47；DR-307 | 即时失效 | 认证等值命中 `uq_api_keys_key_hash`；状态列可读 | 逐请求读已提交状态，无缓存/惰性清理 | 吊销提交后新请求即 401；并发以提交后可观察状态为准 | V-DB-F017-6/9；T47 |
| §21 / §22；DR-305/DB-D16 | 账号引用 | 两 FK `ON DELETE RESTRICT`；`ix_api_keys_user_id`/`ix_api_keys_created_by` | 无用户物理删除路径；停用仅改 `status` | 有 Key 的用户物理删除被 RESTRICT 拒绝（无路径，仅兜底） | V-DB-F017-4 |
| §22 / §23.1；DR-306/315 | Audit 增列 | `api_key_label varchar(255) NULL`，无 FK，nullable-safe not-blank CHECK；既有行 NULL | `audit.record` 写 `operator.api_key_label`；Cookie 路径 NULL | 快照不随 Key 吊销/账号停用变化 | V-DB-F017-5/8 |
| §22 / f003 DB-D28 | Audit append-only | `trg_audit_logs_append_only` 拒 UPDATE/DELETE；ADD COLUMN 不触发 | 无修改/删除/清空入口 | 增列后既有索引/触发器不变 | V-DB-F017-5 |
| §22 / §23.1；DR-316 | `object_type="api_key"` | 无需 Schema 变更（`varchar(64)` 无 CHECK） | 契约层登记 + `AUDITABLE_FIELDS`；action=CREATE/UPDATE | 枚举扩展为契约变更，不触发迁移 | V-DB-F017-8 |
| §23.1 / §27；D01 §1 | 稳定 ID | `gen_random_uuid()` PK 默认 | 响应/审计携带 UUID | 不改 id | V-DB-F017-7 |
| §27 / DB-D7 | 迁移链 | 单 head `0014_api_keys`；up/down 对称 | — | 结构可逆；数据破坏性按 DB-D7 | V-DB-F017-1 |

---

## 6. 真实 PostgreSQL 验证清单（本设计**无 PASS**，交 Tester 执行）

> Constraint / UNIQUE / FK / 迁移 / append-only 仅**真 PostgreSQL** 为证据，Mock/SQLite 不作数（§27、data-integrity SKILL §6）。

**V-DB-F017-1 迁移 up/down/up**
- `alembic upgrade head` → `alembic heads` 唯一 = `0014_api_keys`；`down_revision = 0013_search_indexes`。
- `alembic downgrade 0013_search_indexes`：`api_keys` 表、两条索引、`audit_logs.api_key_label` 列与 `ck_audit_logs_api_key_label_not_blank` 全部消失；既有对象/数据保留。
- re-upgrade 恢复；无残留、无半成品。断言 `alembic current` 与对象清单。

**V-DB-F017-2 约束拒绝（写非法行失败，错误类型为 `CheckViolation`）**
- `key_hash` 非 64 位 hex、`label` 空串/纯空白、`expires_at <= created_at`、`expires_at > created_at + 365d + 5min`、`revoked_at < created_at` 均被拒。
- 合法边界通过：`expires_at = created_at + 365 days`、`revoked_at = created_at`、label 恰 255 code point。

**V-DB-F017-3 唯一**
- 插入重复 `key_hash` 失败（`uq_api_keys_key_hash`）；不同 `key_hash` 并发插入均成功且唯一约束兜底。

**V-DB-F017-4 FK RESTRICT**
- `DELETE FROM users WHERE id = <持 Key 用户>` 被 `fk_api_keys_user_id_users`/`fk_api_keys_created_by_users` 拒绝（`ForeignKeyViolation`）。

**V-DB-F017-5 append-only 兼容**
- 增列后 `UPDATE audit_logs` / `DELETE FROM audit_logs` 仍抛 `restrict_violation`（`trg_audit_logs_append_only`）。
- 既有审计行 `api_key_label IS NULL`；`INSERT` 带 `api_key_label` 成功，带空串/纯空白被 CHECK 拒绝。
- `pg_indexes` 断言既有 `ix_audit_logs_*` 与触发器/函数存在且未变。

**V-DB-F017-6 即时失效（DB 侧可观察状态）**
- 置 `revoked_at=now()` / `users.status='DISABLED'` 提交后，按 `key_hash` 联接查询不再返回“可用”状态（以新连接/新事务读取已提交状态）。
- 认证查询计划：`EXPLAIN` 命中 `uq_api_keys_key_hash` 等值（`Index Scan`/`Index Only Scan`）。

**V-DB-F017-7 `gen_random_uuid()` 默认**
- 不带 `id` 插入 → `id` 非空且为 UUID v4（PG 核心函数，无扩展依赖）。

**V-DB-F017-8 `object_type="api_key"` 插入**
- `INSERT INTO audit_logs(object_type='api_key', action IN ('CREATE','UPDATE'), ...)` 成功（`varchar(64)` 无 CHECK）；越界 action 仍被 `ck_audit_logs_action` 拒。

**V-DB-F017-9 授权/查询计划基线**
- `ix_api_keys_user_id`/`ix_api_keys_created_by` 存在（`pg_indexes`）；无 `expires_at`/`label` 索引（断言不存在）。
- `key_hash` 认证查询在代表性数据量下走唯一索引（记录 `EXPLAIN (ANALYZE)` 基线）。

**V-DB-F017-10 Schema 不变断言（F002/F015 回归）**
- `users`/`user_sessions`/既有 `audit_logs` 列与约束未变（新增仅 `api_key_label`）；无 `pg_trgm`/扩展 DDL 出现在 `0014`。

---

## 7. 交 Backend 的依赖保证与交 Tester 的测试项

### 7.1 Backend 可依赖的 DB 保证

1. `api_keys.id` 默认 `gen_random_uuid()`（UUID）；`created_at` 默认 `now()`（timestamptz/UTC）。
2. `key_hash` 全表唯一且格式受 CHECK（`^[0-9a-f]{64}$`）；无任何明文列。
3. `api_keys` 无 `deleted_at`/`version`/`last_used_at`，**ORM 模型不得继承 `SoftDeleteMixin`**，也不得在全局软删过滤中生效。
4. `user_id`、`created_by` 均 `ON DELETE RESTRICT`；有 Key 的用户无法物理删除（无删除路径，仅兜底）。
5. 有效期受两条 CHECK 约束（`> created_at`、上限 backstop）；`expires_at` 须由 **DB 事务 `now()`** 派生以避免时钟漂移触发 500（§2.3）。
6. `audit_logs.api_key_label` 可空、无 FK；可写入或留 NULL；空串/纯空白被 CHECK 拒绝。
7. 迁移 `0014_api_keys` 有真实 `downgrade`；`up` 后为唯一 head。
8. `object_type="api_key"` 无 Schema 限制（`varchar(64)`）；`action` 仅限既有四值（CREATE/UPDATE 用于本 Feature）。

**ORM 同步要求（Backend）**：新增 `backend/app/models/api_key.py`（列/约束/索引与迁移一致，短名交给 `Base` 命名约定；无 `SoftDeleteMixin`）；`backend/app/models/audit_log.py` 增 `api_key_label` nullable 列及 nullable-safe CHECK；`models/__init__.py` 注册。避免 `Base.metadata` 与迁移漂移。

### 7.2 Tester 测试项（真实 PG / 真 HTTP，逐条映射）

| 测试项 | 内容 | 映射 |
| --- | --- | --- |
| V-DB-F017-1..10 | §6 全部 DB 约束/唯一/FK/append-only/迁移/默认/计划 | §27、T44/T46/T47 |
| T-DB-1 | DB 仅存 `key_hash`：`SELECT` 断言无明文/无 `plaintext` 列 | T46 |
| T-DB-2 | 创建成功 201 返回明文一次；随后 list/detail/audit/error 响应无明文/哈希 | T46 / A5 |
| T-DB-3 | 吊销后并发/后续认证 401；账号 DISABLED 后全部 Key 401 | T47 / A6 |
| T-DB-4 | 用 Key 的写操作审计 `operator_username`=绑定账号、`api_key_label`=标签；创建/吊销各一条 | T45 / A4 |
| T-DB-5 | `expires_at` 缺省 90 天；`365` 成功、`366`/`0`/负/`null` 失败 | T48 / A7 |
| T-DB-6 | 凭证边界：缺失/格式非法/哈希不匹配/已吊销/已过期 → 401 且等价；401 先于 403 | T44 / A3 |
| T-DB-7 | F002 回归：登录/登出/me、CSRF 同源、401/403 语义不变 | T49 / A8 |

---

## 8. DB-D301–DB-D316 决策编号表

| ID | 决定 | 状态 | 依据 |
| --- | --- | --- | --- |
| DB-D301 | 新建 `api_keys` 表（列集合见 §2.1）；**无 `deleted_at`/`version`/`last_used_at`**；不继承 `SoftDeleteMixin` | DESIGN | §23.1、§21；DR-305；AGENTS §2.6 |
| DB-D302 | `api_keys.id` UUID + `gen_random_uuid()` PK `pk_api_keys` | DESIGN | D01 §1、DB-D13 |
| DB-D303 | `user_id`/`created_by` 双 FK → `users.id` `ON DELETE RESTRICT`；建 `ix_api_keys_user_id`、`ix_api_keys_created_by` | DESIGN | §21、§22；DB-D16 范式；DR-305 |
| DB-D304 | `key_hash varchar(64) NOT NULL` + `uq_api_keys_key_hash` + `ck_api_keys_key_hash_format`（`^[0-9a-f]{64}$`）；唯一索引承载认证 O(1) | DESIGN | §27；DR-305/309 |
| DB-D305 | `label varchar(255) NOT NULL` + `ck_api_keys_label_not_blank`（`btrim<>''`）；trim/禁控制字符为应用层 | DESIGN | §23.1；DR-305 |
| DB-D306 | 时间 CHECK：`ck_api_keys_expires_after_created`、`ck_api_keys_revoked_after_created` | DESIGN | §23.1；DR-305/307 |
| DB-D307 | 365 天 backstop `ck_api_keys_expires_within_max` = `<= created_at + interval '365 days' + interval '5 minutes'`；权威 1..365 在应用；`expires_at` 由 DB 事务 `now()` 派生 | DESIGN | §23.1、§26；DR-308；§2.3 |
| DB-D308 | **不建** `expires_at`/`label` 索引；认证按 `key_hash` 唯一索引，无惰性清理 | DESIGN | DR-307；AGENTS §2.6 |
| DB-D309 | `audit_logs.api_key_label varchar(255) NULL` 无默认、**无 FK**（快照）；既有行自动 NULL、无需回填 | DESIGN | §22、§23.1；DR-306/315 |
| DB-D310 | 加 nullable-safe `ck_audit_logs_api_key_label_not_blank`；**不建** `api_key_label` 索引 | DESIGN | §22；DR-306；F015 DB-D168 口径 |
| DB-D311 | append-only 触发器/既有索引不变；ADD COLUMN 为元数据级、不触发、无表重写 | DESIGN | §22；f003 DB-D28 |
| DB-D312 | 迁移 `0014_api_keys`，`down_revision=0013_search_indexes`，单 head；upgrade 建表→索引→增列→增 CHECK，downgrade 逆序 | DESIGN | DB-D7；DR-314 |
| DB-D313 | 手写 DDL（autogenerate 不识别 CHECK）；`op.f()` 全名避免命名约定二次套用；约束全名遵循 DB-D6 | DESIGN | DB-D6/DB-D7 |
| DB-D314 | downgrade 破坏性边界按 DB-D7：丢 `api_keys` 全表与仅 F017 写入的 `api_key_label` 值；生产回滚用 F001 备份，`downgrade` 仅用于开发/测试 | DESIGN | DB-D7；DR-314 |
| DB-D315 | `object_type="api_key"` **无需 Schema 变更**（`varchar(64)` 无 CHECK）；`AUDITABLE_FIELDS`/action 取值为契约层 | DESIGN | §22；F015 DB-D167 范式；DR-316 |
| DB-D316 | 认证查询计划以 `uq_api_keys_key_hash` 等值命中；**无额外部分/复合索引需求** | DESIGN | §27；DR-307；§6 V-DB-F017-6/9 |

> 状态语义：`DESIGN` = 由已确认规则（§21/§22/§23.1/§26/§27 + DR-305/306/307/308/314/315/316）必然产生的技术要求，本 DATABASE Gate 签核；不新增业务规则。

---

## 9. 结论

### `READY FOR DATABASE IMPLEMENTATION`

- F017 的 Schema 交付面收敛为**一表一列一迁移**：`api_keys` + `audit_logs.api_key_label` + `0014_api_keys`；约束/索引/迁移/downgrade/append-only 交互全部在已确认边界内定稿，无 DB 侧阻塞。
- §5.4 交 Database 签核清单逐项关闭。
- **无 Schema 阻塞项**。以下为**非阻塞**交核：

| 项 | 类型 | 说明 | 责任 |
| --- | --- | --- | --- |
| F017-OPEN-3 / DR-308 附属 | Product（OPEN，非阻塞） | `label` 是否需账号内唯一。当前 PROPOSED=不唯一，DB 不建 `(user_id,label)` 唯一索引。若后续要求唯一，以新增迁移加部分唯一索引，不改本表其余结构。 | Product → Architect |
| F017-OPEN-1 / DR-317 | Product（OPEN，非阻塞） | 账号停用后再启用，未吊销 Key 是否恢复可用。DB 两条路径均支持（默认暂停用即 401；若要求永久失效，停用同事务批量置 `revoked_at`）。**不影响本 Schema**。 | Product |
| F002/F015 契约同步 | 协调器 | `docs/api/F002.md`→v2、`docs/api/F015.md`→v2。DB 侧无变更。 | 协调器按 change-control |

- **未验证声明**：本 Gate 为只读设计签核，§6/§7 全部为**计划验证**，无 PASS；执行证据由 F017 TEST 阶段产出。

## 10. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-14 | 初次签核：`api_keys` 表、`audit_logs.api_key_label`、迁移 `0014_api_keys`、DB-D301–DB-D316、数据完整性对应表、真实 PG 验证清单、Backend/Tester 交接；结论 `READY FOR DATABASE IMPLEMENTATION`。 |