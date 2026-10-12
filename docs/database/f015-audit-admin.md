# F015 Audit 查询、已删除对象管理与系统功能 — DATABASE 复核

- **签核**：Database；设计版本 v1（2026-10-14）
- **结论**：`NOT_REQUIRED`（`layers.database=false` 复核通过；无 Schema 交付、无 Migration）
- **上游依据**：`docs/features/F015/architecture.md`（DR-213–DR-227，尤其 DR-222/DR-226/DR-227、§4.2/§4.3、§6）、`docs/features/F015/product.md`（A1–A31、I-1–I-15、O-1–O-8）、`docs/api/F015.md` v0 草案；`docs/database/f002-auth.md` v1（DB-D13–D19）、`docs/database/f003-cluster.md` v2（DB-D20–D32）、`docs/database/f007-interface.md` v1（DB-D77）、`docs/database/f013-search-index.md` v1（head `0013_search_indexes`）、`docs/database/f014-import.md` v1；`backend/alembic/versions/`（head `0013_search_indexes`）、`0003_clusters_audit.py`、`0007_interfaces.py`；`backend/app/models/{audit_log,user,session,interface}.py`；`.pi/skills/data-integrity/SKILL.md`。

本 Feature 经复核**无新表/新列/新约束/新触发器/新索引/迁移**。DB-D167–DB-D172 均为复核裁定，编号段保留给后续真正有 Schema 变更的 Feature。

## 1. 复核裁定汇总（DB-D167–DB-D172）

| ID | 裁定 | 结论 | 依据 |
| --- | --- | --- | --- |
| DB-D167 | `audit_logs.object_type` 登记值 `"user"` **无需 Schema 变更**：列 `varchar(64) NOT NULL`，无枚举 CHECK；`"user"` 长度 4 | NOT_REQUIRED | DR-222；0003 表定义；O-6 |
| DB-D168 | **不新增** `ix_audit_logs_operator_username`（DR-227） | NOT_REQUIRED | §2 |
| DB-D169 | 已删 8 类聚合**无需新增索引**：7 类既有 `ix_*_deleted_at` 覆盖；`interfaces` 依 DB-D77 未建，F015 不改 | NOT_REQUIRED | §3 |
| DB-D170 | `users`/`user_sessions`/`audit_logs` 生命周期与 FK RESTRICT **无需 Schema 变更** | NOT_REQUIRED | §4；DB-D16/DB-D27 |
| DB-D171 | **无新迁移**；迁移链单 head 保持 `0013_search_indexes`；`layers.database` 应为 `false` | NOT_REQUIRED | §5 |
| DB-D172 | `GET /api/v1/users` 的 `role`/`status`/`q` 过滤与排序**不建索引**（小表） | NOT_REQUIRED | §4.3 |

## 2. DR-222 复核：`object_type="user"` 登记

**裁定：无需 Schema 变更。** `audit_logs.object_type` 为 `varchar(64) NOT NULL`，无枚举 CHECK/ENUM；已登记 8 值与新增 `user` 同为普通字符串；`action` CHECK 已含 CREATE/UPDATE；快照白名单 `{username,role,status}` 为 JSON object，满足既有约束；`object_id` 多态 UUID（无对象级 FK）。`object_type` 取值集合属 API 契约枚举（docs/api/F015.md §2.1），非数据库对象。

## 3. DR-227 裁定：`audit_logs(operator_username)` 索引

**裁定：`NOT_REQUIRED` —— 不新增索引，不产生迁移。**

现有索引：`ix_audit_logs_object_type_object_id(object_type,object_id,created_at)`、`ix_audit_logs_operator_user_id`、`ix_audit_logs_created_at`、PK。`operator_username` 精确过滤未命中现有索引列首列，但：
1. 选择性低（本地账号少，单值常命中大比例历史行）；
2. 正确性不依赖索引（缺索引仅性能退化）；
3. 契约未将 operator 定为唯一/必选过滤。

append-only 评估：audit_logs 持续保留无 TTL，所有二级索引只增不减；新增单列 btree 在最热写入路径永久累积写放大，收益低于成本（AGENTS §2.6）。延期触发：真实 PG `EXPLAIN (ANALYZE)` 确认顺序扫描为瓶颈后走变更控制，未来优先复合/partial 形态。

**架构 errata**：`docs/features/F015/architecture.md` DR-227（PROPOSED）与 §5 `layers.database` 应同步为 `NOT_REQUIRED`/`database=false`（协调器按变更控制同步）。

## 4. 已删 8 类聚合索引复核

7 类既有 `ix_*_deleted_at`；`interfaces` 无（F007 DB-D77 显式裁定）。F015 `GET /api/v1/deleted` 的 interface 分支顺序扫描，正确性不受影响，量级小。裁定 `NOT_REQUIRED`；延期触发为 partial 索引 `ix_interfaces_deleted_at ON interfaces(deleted_at) WHERE deleted_at IS NOT NULL`。`label`/`cluster` 为展示派生列，不落库不建索引。

## 5. 用户表生命周期与 FK RESTRICT 复核

- `users` 无 `deleted_at`；F015 无 `DELETE /api/v1/users`、无改密/重置/注册。停用/启用仅改 `status` 与 `version`。
- DR-220 停用同事务删 `user_sessions`（无 append-only 触发器，允许 DELETE），不触碰审计。
- FK RESTRICT：`fk_audit_logs_operator_user_id_users`、`fk_user_sessions_user_id_users` —— 持有审计/会话的用户不可物理删除；`operator_username` 快照 + 可空 `operator_user_id` 保证停用后历史身份可解析。
- `GET /api/v1/users` 小表，不建 role/status/q 索引。

## 6. 迁移影响与 head

无迁移；单 head 保持 `0013_search_indexes`。`layers.database` 由 PROPOSED true 覆写为 **false**。无回填、无破坏性 DDL。

## 7. 数据完整性对应表

| 规则依据及版本 | 作用域/读写入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §22 / f003 DB-D28 | audit_logs（含 user） | trg_audit_logs_append_only；无 deleted_at/version | 无修改/删除/清空端点或 UI | 持续保留无 TTL | V-DB-F015-1 |
| §22 / f003 DB-D27 | 账号事件 object_type=user | 无对象 FK；action CHECK；快照 object | 白名单无密码；同事务 | 停用不改审计 | V-DB-F015-2/4 |
| §22/§23 / f002 DB-D16/D27 | users/user_sessions/audit_logs FK | 均 RESTRICT | 无物理删除；停用代替删除 | 身份快照保留 | V-DB-F015-3/4 |
| §23 / f002 DB-D14 | username 唯一 | uq_users_username + ck_users_username_format | 归一化；冲突 409 | 并发 UNIQUE 兜底 | V-DB-F015-5 |
| §21 / DB-D169 | 已删聚合 8 类 | 7 类 ix_*_deleted_at；interfaces 无 | 谓词 deleted_at IS NOT NULL | 正确性不依赖索引 | V-DB-F015-6 |
| §22 / DB-D168 | Audit 查询 | 既有 object_type/object_id/created_at 等 | 过滤/分页/排序；只读 | 缺 operator 索引仅退化 | V-DB-F015-7 |
| §27 | 迁移链 | 单 head 0013_search_indexes | — | 结构不变 | V-DB-F015-8 |

## 8. 验证计划（真实 PG，本设计无 PASS）

- V-DB-F015-1 append-only：UPDATE/DELETE 被触发器拒。
- V-DB-F015-2 插入 object_type='user' + action CREATE/UPDATE + 白名单快照成功；双空/非 object 被拒。
- V-DB-F015-3 删持有审计/会话用户被 RESTRICT 拒。
- V-DB-F015-4 停用+删会话同事务成功；既有审计行不变、operator_username 可读。
- V-DB-F015-5 username 唯一/格式约束回归。
- V-DB-F015-6 已删聚合索引存在断言（interfaces 记录无索引）。
- V-DB-F015-7 Audit 查询 EXPLAIN 计划基线（默认走 created_at/object_type 索引；operator 过滤未走专用索引，预期）。
- V-DB-F015-8 Schema 不变断言：head=0013_search_indexes；无新增对象；不存在 ix_audit_logs_operator_username。

## 9. 未决 / 交核（无 Blocking）

- 交协调器：DR-227 标 `PROPOSED → NOT_REQUIRED`；architecture DR-226/§5 `layers.database=false`。
- 性能延期项（非阻塞）：`ix_audit_logs_operator_username`、`ix_interfaces_deleted_at`（触发条件与形态已记录）。
- 只读签核，全部为计划验证无 PASS。

## 10. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-14 | 初次复核：裁定 NOT_REQUIRED；DB-D167–D172。 |
