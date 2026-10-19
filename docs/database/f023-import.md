# F023 资源+网卡+IP 批量导入 — DATABASE Gate 复核

- **状态**：`NOT_REQUIRED`（`layers.database=false` 复核通过）
- **角色**：Database；日期：2026-10-15
- **依据**：requirements revision 8 §24.1/§10/§11/§11.1/§12/§13.2/§14/§21/§27；`docs/features/F023/architecture.md`（DR-401–DR-431、§3/§8）；`docs/database/f004..f010`、`f014-import.md`（NOT_REQUIRED 先例）；后端 `app/models/*`、`app/services/{network,ip_address,interface,resource_import}.py`、`alembic/versions/0008/0009/0010`。

## 1. §8 四项裁决

### 1.1 Network 解析索引 — 既有索引充分，NOT_REQUIRED
| 解析路径 | 查询 | 承载 |
| --- | --- | --- |
| `name`（同 Cluster，不区分大小写） | `WHERE cluster_id=? AND name_key=? AND deleted_at IS NULL` | `uq_networks_cluster_id_name_key`（f008 DB-D82） |
| CIDR 精确相等 | `WHERE cluster_id=? AND deleted_at IS NULL AND cidr=?` | `ix_networks_cluster_id`（DB-D89）+ `excl_networks_cluster_id_cidr` GiST |
| `/mask` → `network_of(ip,m)` 精确 CIDR 相等 | 同上 | 同 Cluster CIDR 不重叠（`excl_networks_cluster_id_cidr`）故至多命中 1 行；按 Network 去重缓存 |

结论：不新增索引。触发复核条件：D03 真 PG EXPLAIN 证明热点（当前无证据）。

### 1.2 IP 创建并发锁序 — 非 Schema；应用层需确定性锁序（F023-DB-01）
- `_lock_network` = `SELECT networks.id ... FOR UPDATE`；行锁为事务级，SAVEPOINT 回滚不保证释放。
- 一个批次可跨多 Network/Host，两并发导入按不同行序可形成 `40P01` 死锁（原子性不破坏，整批失败）。
- 建议：写入前收集全部组的 `network_id`（及 VM Host `resource_id`），按稳定键升序**在 SAVEPOINT 之外一次性取全部行锁**；或至少组内固定 Host→network 顺序且批次按 `(cluster_id,hostname_key)` 确定性排序。捕获 `40P01` 时整批回滚、返回可重试语义，不静默重试。

### 1.3 SAVEPOINT 内触发器归因 — 可回滚成立；归因来源需订正（F023-DB-02）
- `begin_nested()` + `ROLLBACK TO SAVEPOINT` 隔离成立（既有 F014 先例 `resource_import.py`）；`trg_ip_addresses_*` BEFORE 触发器可在 SAVEPOINT 内触发并捕获。
- `diag.constraint_name` 仅对真正约束违反（UNIQUE/CHECK/FK/NOT NULL）填充。`fn_ip_addresses_*` 用 `RAISE EXCEPTION ... USING ERRCODE='restrict_violation'`，**不设 `constraint_name`**。
- 因此 DR-422 需订正：`uq_*`/`ck_*`/FK 用 `constraint_name`；`fn/trg_ip_addresses_cidr_contains`/`_cluster_consistent`/`_interface_cluster` 须按 RAISE 消息或 SQLSTATE `restrict_violation` 归因（复用 `ip_address.py::_translate_integrity_error` 既有文本分支）。

### 1.4 `layers.database=false` / NOT_REQUIRED — 成立
仅通过导入入口 CREATE 既有表（`resources`/`bare_metal_details`/`virtual_machine_details`/`interfaces`/`ip_addresses`/`audit_logs`）；无 UPDATE/DELETE/RESTORE；无新表/列/约束/触发器/索引/迁移；无既有数据结构改动/回填。与 f014-import 同型。

## 2. 完整性复用清单
`uq_resources_cluster_id_hostname_key`、`uq_interfaces_resource_id_name`、`uq_ip_addresses_cluster_id_address`、`ck_ip_addresses_address_host`/`_not_disabled`、`trg_ip_addresses_cidr_contains`/`_cluster_consistent`/`_interface_cluster`、FK `host_resource_id`、`uq_networks_cluster_id_name_key`、`excl_networks_cluster_id_cidr`、`ix_networks_cluster_id`、`excl_ip_pools_network_id_address_range`、`trg_virtual_machine_details_host_valid`。

## 3. Issues
| ID | Severity | 内容 | Owner | 阻塞 |
| --- | --- | --- | --- | --- |
| F023-DB-01 | MEDIUM | 跨批次死锁窗口，需确定性锁序（SAVEPOINT 外一次性锁定） | Architect（CONTRACT）/Backend | 否 |
| F023-DB-02 | LOW | `fn/trg_ip_addresses_*` 无 `constraint_name`，DR-422 归因须用消息/SQLSTATE | Architect/Backend | 否 |
| F023-DB-03 | NOTE | `/mask`/CIDR 解析依赖既有索引；若 EXPLAIN 证明热点走变更控制 | Tester/Architect | 否 |

## 4. 结论
`NOT_REQUIRED`：无新表/列/约束/触发器/索引/迁移，无需 Migration 交付。F023-DB-01/02 交 Architect/Backend 在已批准边界内处理，不改变本 Gate 结论。验证计划见 `docs/features/F023/test-report.md`（真 PG）。

GIT: NONE