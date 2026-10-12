# F016 一期集成验收 — DATABASE 复核

- **签核**：Database；设计版本 v1（2026-10-14）
- **结论**：`NOT_REQUIRED`（`layers.database=false` 复核通过；无 Schema 交付、无 Migration）
- **上游依据**：`docs/features/F016/architecture.md`（DR-228、DR-232、DR-236、DR-240、DR-241、DR-243、O-4、§4/§8/§11）、`docs/features/F016/product.md`（§2.2、§6、A7/A14、I-1/I-3/I-6）、`docs/database/f003-cluster.md` v1（DB-D20–D32，尤其 DB-D28）、`docs/database/f015-audit-admin.md` v1（DB-D167–D172）、`docs/database/f013-search-index.md` v1；`backend/alembic/versions/`（head `0013_search_indexes`）、`0003_clusters_audit.py`；`deploy/backup/{pg_dump.sh,restore.sh,README.md}`。

F016 为验收型 Feature，经复核**无新表/新列/新约束/新触发器/新索引/新迁移**。

## 1. 复核裁定（DB-D173–DB-D176）

| ID | 裁定 | 结论 | 依据 |
| --- | --- | --- | --- |
| DB-D173 | 迁移链单 head 保持 `0013_search_indexes`，线性无分叉；无新增版本文件 | NOT_REQUIRED | §2 |
| DB-D174 | T36 备份覆盖 Audit：全库 `pg_dump -Fc` 默认包含 `audit_logs`；恢复随库重建表/数据/索引/约束/触发器/函数 | NOT_REQUIRED | §3；0003；DR-240 |
| DB-D175 | 验收数据集构造仅使用既有表，无 Schema 需求 | NOT_REQUIRED | §4；DR-236 |
| DB-D176 | 备份/恢复的 DB 侧无需新增 Schema 支持（备份脚本属部署脚本） | NOT_REQUIRED | §3 |

## 2. 迁移链复核（DB-D173）
13 个版本构成单一线性链：`0001_baseline → 0002_users_sessions → 0003_clusters_audit → 0004_resources → 0005_bare_metal_details → 0006_virtual_machine_details → 0007_interfaces → 0008_networks → 0009_ip_pools → 0010_ip_addresses → 0011_services → 0012_service_endpoints → 0013_search_indexes`。仅 `0013_search_indexes` 无子节点（单 head）；F016 无新增迁移。

## 3. T36 备份覆盖 Audit 的数据库侧复核（DB-D174/DB-D176）
- `pg_dump -Fc` 为整库导出，默认包含 `audit_logs` 表及其数据、PK/FK/CHECK、`ix_audit_logs_*` 索引、`trg_audit_logs_append_only` 触发器与 `fn_audit_logs_append_only()` 函数（定义于 0003）；脚本无 `--exclude-table/--schema` 过滤。
- `restore.sh` 默认恢复到新库，标准 `pg_restore --no-owner --no-privileges`（`--force` 才 `--clean --if-exists`），随归档重建表/数据/约束/索引/触发器/函数；append-only 触发器随库恢复，UPDATE/DELETE 仍被拒。
- 已知边界（非缺陷）：触发器只拦 UPDATE/DELETE，TRUNCATE/DROP 有意保留给测试清场与 downgrade（0003 注释）；「无清空路径」由 UI/API 无入口保证（F015 DB-D167）。
- 结论：DB 侧无需新增备份/恢复支持；B1–B4 均基于既有 Schema 可断言。

## 4. 验收数据集 Schema 依赖（DB-D175）
DR-236 数据集全部落在 F003–F013 既有表与约束内，经真实 HTTP API 构造、用后清理，不新增业务规则或列。

## 5. 数据完整性对应表（F016 范围）

| 规则依据及版本 | 作用域 | 数据库保证 | 业务层保证 | 验证 |
| --- | --- | --- | --- | --- |
| §22 / f003 DB-D28 | audit_logs append-only | trg_audit_logs_append_only（UPDATE/DELETE 拒） | 无修改/删除/清空入口/UI | B3/B4 |
| §22 / §30 | Audit 纳入备份 | 全库 pg_dump -Fc 含 audit_logs | 恢复默认新库 | B1/B2/B5/B7 |
| §22 | 恢复后审计完整 | 触发器/约束/函数随库重建 | 无截断 | B1/B2/B6 |
| §27 / T07/T35 | 约束/并发证据 | 真实 PostgreSQL | — | REUSE F010/F009 |
| §27 | 迁移链 | 单 head 0013_search_indexes | — | alembic current=head |

## 6. 验证计划（真实 PG，本设计无 PASS）
- V-DB-F016-1：`alembic heads` 单 head=`0013_search_indexes`；无新增版本文件。
- V-DB-F016-2：备份后 `pg_restore -l` 归档清单含 TABLE audit_logs、TRIGGER trg_audit_logs_append_only、FUNCTION fn_audit_logs_append_only。
- V-DB-F016-3：恢复库 audit_logs 行数/关键字段聚合与源库一致且 >0。
- V-DB-F016-4：恢复库 audit_logs UPDATE/DELETE 被拒；alembic current=head；ready 200。
- V-DB-F016-5：Schema 不变断言（无新增对象）。

## 7. 未决 / 交核（无 Blocking）
- layers.database=false 维持；F016 DATABASE=NOT_REQUIRED，无 Migration/回填/破坏性 DDL。
- 性能延期项沿用 F015 §9，F016 不触发。
- 只读签核，全部为计划验证无 PASS；执行证据由 F016 TEST 阶段产出。

## 8. 设计版本历史
| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-14 | 初次复核：裁定 NOT_REQUIRED；DB-D173–DB-D176。 |
