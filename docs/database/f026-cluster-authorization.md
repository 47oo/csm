# F026 集群范围授权 — Database 设计

- 阶段：DATABASE；设计版本 v1（2026-10-21）
- Feature：F026；变更单 CHG010-BQ18
- 结论：READY FOR DATABASE IMPLEMENTATION
- 依据：requirements revision 11 §21/§22/§23.2/§26/§27/§31（T85–T99）；CHG-010 批准；F026 product / architecture；D01 v11；F001/F002/F003/F015/F017 Database 设计
- 迁移链：当前 head `0014_api_keys`；单事务执行

## 1. 表 `user_cluster_authorizations`

**不属 §21 业务对象；无 `deleted_at`；不继承 `SoftDeleteMixin`**（避免 `db.py` 全局软删谓词注入）。

| 列 | 类型 | 空 | 默认/约束 |
| --- | --- | --- | --- |
| `id` | UUID | NOT NULL | PK `pk_user_cluster_authorizations`，`gen_random_uuid()` |
| `user_id` | UUID | NOT NULL | FK → users RESTRICT |
| `cluster_id` | UUID | NOT NULL | FK → clusters RESTRICT |
| `granted_at` | timestamptz | NOT NULL | `now()` |
| `granted_by` | UUID | NULL | FK → users RESTRICT；NULL = 系统回填 |
| `revoked_at` | timestamptz | NULL | — |
| `revoked_by` | UUID | NULL | FK → users RESTRICT |

CHECK：

- `ck_..._revoked_pair`：`(revoked_at IS NULL) = (revoked_by IS NULL)`
- `ck_..._revoked_after_granted`：`revoked_at IS NULL OR revoked_at >= granted_at`

不采用 `deleted_at`、`version`、`created_at`/`updated_at`；`granted_by` 可空用于回填，不伪造操作者。username 不可修改且账号只停用不删除，因此不需要展示快照列。

## 2. 索引与有效行唯一

| 索引 | 列 | 唯一 | 谓词 | 用途 |
| --- | --- | --- | --- | --- |
| `uq_..._user_id_cluster_id` | `(user_id, cluster_id)` | 是 | `WHERE revoked_at IS NULL` | 有效行唯一；并发重复授予权威兜底 |
| `ix_..._user_id` | `(user_id)` | 否 | — | E1 列表（含已撤销历史）与 scope 解析 |
| `ix_..._cluster_id` | `(cluster_id)` | 否 | — | FK 支撑 / 反查 |

DB 修订：不建 `(user_id) WHERE revoked_at IS NULL`；部分唯一索引前导列已服务活动集，且 E1 `status=REVOKED`/省略时需全量 `(user_id)` 索引。无接口影响。

DDL：

```sql
CREATE UNIQUE INDEX uq_user_cluster_authorizations_user_id_cluster_id
ON user_cluster_authorizations (user_id, cluster_id)
WHERE revoked_at IS NULL;
```

Alembic：`op.create_index(..., unique=True, postgresql_where=sa.text("revoked_at IS NULL"))`。

`ON CONFLICT (user_id, cluster_id) WHERE revoked_at IS NULL DO NOTHING` 与索引谓词逐字匹配；禁止 `DO UPDATE`（不得复活已撤销行）。Backend 若用 `ON CONFLICT DO NOTHING`，受影响行数 0 必须映射 409 `already_granted`，不得静默成功。

EXPLAIN 验证：scope 解析、E1 ACTIVE、E1 REVOKED、反查、仲裁索引存在性；记录 `EXPLAIN (ANALYZE, BUFFERS)` 基线。

## 3. 不可变与撤销单向（触发器）

`BEFORE UPDATE` 触发器 `trg_..._immutable`：

- 拒绝修改 `id/user_id/cluster_id/granted_at/granted_by`（`IS DISTINCT FROM`，SQLSTATE 23514）；
- 已撤销行任何 UPDATE → 23514；
- `NEW.revoked_at IS NULL` → 23514（只允许 NULL → NOT NULL）；
- 唯一合法 UPDATE：置 `revoked_at` + `revoked_by`。

`BEFORE DELETE` 触发器 `trg_..._no_delete`：拒绝物理删除（SQLSTATE 23001）。`TRUNCATE`/`DROP TABLE` 有意保留给测试清场与 downgrade。

ADMIN 无行、授予目标未软删由应用层保证（瞬态条件，不能建跨表 DB 约束）；回填 SQL 排除 ADMIN，迁移断言兜底。

## 4. 迁移 `0015_user_cluster_authorizations`

- `revision="0015_user_cluster_authorizations"`，`down_revision="0014_api_keys"`，单 head。
- 手写 DDL（部分索引/触发器/`gen_random_uuid()` autogenerate 不识别），显式全名 + `op.f()`。
- upgrade：建表 + PK + 4 FK + 2 CHECK → 部分唯一索引 + 2 索引 → 2 函数 + 2 触发器 → 回填 → 计数断言。
- downgrade：逆序 drop 触发器/函数/索引/表。

### 回填

```sql
INSERT INTO user_cluster_authorizations
    (user_id, cluster_id, granted_at, granted_by, revoked_at, revoked_by)
SELECT u.id, c.id, now(), NULL, NULL, NULL
FROM users u
CROSS JOIN clusters c
WHERE u.role <> 'ADMIN'
  AND NOT EXISTS (
      SELECT 1 FROM user_cluster_authorizations a
      WHERE a.user_id = u.id AND a.cluster_id = c.id
  )
ON CONFLICT (user_id, cluster_id) WHERE revoked_at IS NULL DO NOTHING;
```

- 含软删 Cluster 与 DISABLED 账号；ADMIN 零行；不写业务 Audit；`granted_by=NULL`。
- `NOT EXISTS` 以任意状态行为存在条件，重复执行不复活已撤销授权。
- 迁移内断言：ADMIN=0、missing=0、duplicate_active=0；表新建无撤销时 total=active=非 ADMIN 用户数 × Cluster 数；失败 `RuntimeError` 整体回滚。

### 部署与回滚

1. 全库备份；记录 `0014_api_keys`。
2. `upgrade head`（纯追加，旧代码安全）。
3. 部署 F026 代码；`AccessScope` 交付但不解引用。
4. 生产回滚用备份；`downgrade` 仅开发/测试 up/down/up，且丢本表全部历史；若 F027 已部署须先回退其代码。

## 5. 对既有 Schema 的影响

- `users`：无 Schema 变更；新增 3 条入向 FK RESTRICT。
- `clusters`：无 Schema 变更；新增 1 条入向 FK RESTRICT；软删是 UPDATE，不触发 RESTRICT。
- `audit_logs`：**无需 Schema 变更**（`object_type varchar(64)` 无枚举 CHECK；`action` 仅用 CREATE/UPDATE）；append-only 与索引不变。
- 既有业务对象：无 DDL/DML 影响。

## 6. 数据完整性对应

| 规则 | DB 保证 | 应用保证 | 验证 |
| --- | --- | --- | --- |
| 有效授权唯一（§23.2/A2） | 部分唯一索引 | 409 `already_granted` | 真 PG 重复/并发 |
| 撤销历史不删除（§23.2/A4/A5/A33） | 成对 CHECK、UPDATE 单向、DELETE 触发器 | 仅 revoke；重授新行 | 撤销/重授/DELETE 拒绝 |
| 归属不可变（§23.2） | BEFORE UPDATE 触发器 | 无 PATCH | 逐列 UPDATE 拒绝 |
| 账号/Cluster 引用（§21/§23.2） | FK RESTRICT | 422 非法目标 | FK/软删/停用 |
| 回填完整幂等（T99/A26–A29） | INSERT…SELECT + 断言 | — | 预置数据 up/down/up、重跑 |
| 解析口径（A19–A23） | 索引 + 显式 join | 空集默认拒绝、ADMIN 不受限 | scope 用例 |
| Audit 同事务（§22/A30–A32） | 无 Schema 变更 | audit.record 同事务 | 审计行/回滚 |

## 7. 真实 PostgreSQL 验证清单

- V1 up/down/up、单 head、对象清单对称。
- V2 CHECK：撤销时间/操作者成对、`revoked_at >= granted_at`。
- V3 部分唯一：第二条有效行 23505；撤销后可重授；同对多已撤销合法；`pg_index` 谓词正确。
- V4 并发重复授予：两连接，最终有效行 ≤1，失败方 409。
- V5 回填：每个非 ADMIN × 每个 Cluster（含软删）恰一条有效；ADMIN 0；DISABLED 有行；重跑不复活撤销；空数据边界。
- V6 归属不可变/撤销单向/DELETE 拒绝。
- V7 默认值/UTC。
- V8/V9 FK RESTRICT（users/clusters）与软删。
- V10 ADMIN 0 行。
- V11 回填不改变 users/clusters/audit_logs。
- V12 迁移断言失败整体回滚。
- V13 EXPLAIN 基线。
- V14 Audit 兼容（新 object_type 可插入，旧约束/触发器不变）。
- V15 无副作用 Schema 断言。

## 8. Backend 可依赖保证

1. `id`/`granted_at` 默认值；timestamptz UTC。
2. 有效行唯一由部分唯一索引兜底；23505 + 约束名映射 409。
3. 同对可保留多条已撤销；重授必须 INSERT。
4. 归属不可变；撤销只能 NULL→NOT NULL；不以异常做业务分支（先查/条件更新判 404/409）。
5. DELETE 被拒；无物理删除路径。
6. 被引用 users/clusters 不可物理删除；软删/停用不影响授权行。
7. 表无 `deleted_at`；ORM 不继承 `SoftDeleteMixin`；全局软删过滤不作用于本表。
8. 迁移单 head、有 downgrade、回填幂等不复活。
9. `audit_logs` 无 Schema 变更。
10. 解析查询由 `uq_...`/`ix_..._user_id` + clusters PK 支撑；软删过滤显式写在应用查询。

ORM：`backend/app/models/user_cluster_authorization.py` 与迁移一致；部分索引 `Index(..., unique=True, postgresql_where=text("revoked_at IS NULL"))`；`models/__init__.py` 注册。

## 9. 决策与待核

- DB-D401 表与列；DB-D402 UUID PK；DB-D403 双 FK RESTRICT；DB-D404 可空操作者 FK；DB-D405 CHECK；DB-D406 部分唯一；DB-D407 全量 `(user_id)` 索引取代部分索引；DB-D408 cluster 索引；DB-D409 不建操作者索引；DB-D410 UPDATE 触发器；DB-D411 DELETE 触发器；DB-D412 ADMIN/软删由应用保证；DB-D413 迁移 0015；DB-D414 手写 DDL；DB-D415 回填；DB-D416 计数断言；DB-D417 downgrade 破坏性；DB-D418 audit 无变更；DB-D419 部署顺序；DB-D420 查询计划。
- 非阻塞待核：A-3 回填不写 Audit（Product/用户）；A-1 停用账号保留授权/回填含 DISABLED；A-2 ADMIN 升降级行保留；索引 errata 知会 Architect。

**Status：READY FOR DATABASE IMPLEMENTATION**