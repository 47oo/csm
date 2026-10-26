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

## 5. F035 复核（2026-10-26）

- **作者**：Database。**对象**：F035「向既有 Resource 追加 Interface/IP」（`docs/features/F035/architecture.md` v1 §5 完整性表、§12.6 第 1 项 / TD-I-3）。
- **结论**：`NOT_REQUIRED` 继续成立（`layers.database=false`）。**不新增/修改**任何表、列、索引、约束、触发器/函数或 Migration；**无回填**、无既有数据升级动作、无回滚风险（纯 INSERT 新子对象行）。
- **上游依据**：requirements **revision 14** §24.6、T117–T126（并回归 T64–T72、T89、T115）；`docs/api/F023.md` **v2** §8.1 / §11 / §12.3 / §12.5 / §13；CHG013-BQ01…BQ08；迁移 `0004_resources` / `0007_interfaces` / `0010_ip_addresses`；写入路径只读核对 `app/services/{resource_interface_ip_import,interface,ip_address,resource}.py`。

### 5.1 四项判定

| # | 待判定 | 结论 | 依据 |
| --- | --- | --- | --- |
| ① | 不新增/修改表、列、索引、约束、触发器、Migration | 成立 | 追加路径只 INSERT `interfaces` / `ip_addresses` 及各一条 CREATE Audit；无 DDL；`alembic` head 仍为 `0015` |
| ② | 追加只需应用层，不需额外 DB 约束 | 成立 | 见 §5.5：T118 是**入口级行为规则**，非数据库不变式 |
| ③ | 三个部分唯一索引足以兜底追加并发 | 成立 | 见 §5.3 |
| ④ | 锁集合扩展仅属应用层 | 成立 | 见 §5.4 |

### 5.2 零 Schema 漂移断言（替代约束验证）

| ID | 断言 | 承载 |
| --- | --- | --- |
| A1 | `backend/alembic/versions/` 文件集合与 F023 基线一致（唯一 head `0015_user_cluster_authorizations`），F035 **零新迁移** | Tester 静态守卫（T126 / V10） |
| A2 | `pg_indexes.indexdef` 三条部分唯一索引仍含 `UNIQUE` 且含 `deleted_at IS NULL` | `test_import_constraints.py`、`test_interface_constraints.py`、`test_ip_address_constraints.py` 口径复用 |
| A3 | `Base.metadata` 对象集与迁移对象集 diff 为空（ORM 未越权引入对象） | 可选静态比对 |
| A4 | 追加用例后 `resources` 行快照（全列 + `version` + `updated_at` + `xmin`）与既有子对象快照不变；无 `object_type=resource` 的 UPDATE Audit；新子对象各一条 CREATE | T118 / V2 |
| A5 | `trg_resources_immutable_fields` 为 BEFORE **UPDATE**，追加不产生 UPDATE ⇒ 不触发，`version`/`updated_at` 保持 | 0004:165-180 |

### 5.3 三个部分唯一索引的兜底范围（追加场景）

| 索引（定义） | 覆盖的追加场景 | 并发结果 / 归因 |
| --- | --- | --- |
| `uq_resources_cluster_id_hostname_key` `UNIQUE(cluster_id, hostname_key) WHERE deleted_at IS NULL` | 宿主定位点查；两批「均判定为新建」同 hostname；预校验判为追加但宿主已被软删 ⇒ 按新建（V12/R3） | 23505 → `_attribute_integrity` → `field="hostname"`，整批回滚 |
| `uq_interfaces_resource_id_name` `UNIQUE(resource_id, name) WHERE deleted_at IS NULL` | 两批并发向**同一既有 Resource** 追加同名 Interface | 23505 → `field="name"`；恰一成功 |
| `uq_ip_addresses_cluster_id_address` `UNIQUE(cluster_id, address) WHERE deleted_at IS NULL` | 追加组与任意入口并发抢占同 Cluster 同一地址 | 23505 → `field="ip"`；恰一成功 |

生命周期口径（已确认，不改）：三条索引均排除已软删行 ⇒ 软删同名 Interface 不阻断新同名 Interface；软删 IP 释放地址；软删 Resource 按「不存在」新建且受 hostname 部分唯一约束（T125）；恢复时重入索引冲突由既有恢复路径拒绝。

大小写口径：`interfaces.name` 为 trim + 保留大小写的 `varchar(64)`，无归一化键列，唯一性在确定性排序规则下按字节精确比较 ⇒「同资源 name 唯一（区分大小写）」成立。**环境假设**：库不可改为非确定性（ICU `DETERMINISTIC = FALSE`）排序规则，否则该口径不再成立（见 §5.7 第 7 项）。

### 5.4 F023-DB-01 锁序扩展（应用层，非 Schema）

- `resources` 预锁集合 = ①本批 VM Host `resource_id` ∪ ②本批**全部追加宿主**的既有 `resource_id`；仍为**单语句** `SELECT … WHERE id IN (…) ORDER BY id FOR UPDATE`，位于任何 SAVEPOINT 之外；随后 `networks` 同序加锁（Contract §12.3）。
- 追加宿主在 `prepare_interface` 内由 `_lock_resource` 再次 `FOR UPDATE`：同事务、同行、表序不变 ⇒ 不形成新锁序、无锁环。
- 未引入 advisory lock、`SERIALIZABLE`、新索引或新触发器。`40P01` 行为不变：整批回滚、500 `INTERNAL_ERROR`、不静默重试。
- 影响：锁集合扩大只增加同批内 `resources` 行锁数量（升序、一次取齐），跨批仍与 F023 同序 ⇒ F023-DB-01 结论不变。5000 行纯追加批性能默认 `NOT TESTED`；若回归走变更控制，不得放松 V11.5 锁环判据。

### 5.5 为什么 T118 无法由数据库约束表达

「追加不得修改既有 Resource 任何字段」是**本入口**的行为约束，而非数据模型不变式：同一 `resources` 行经 Resource 编辑入口可合法 UPDATE（并 bump `version`/`updated_at`）。任何「禁止 UPDATE」的 DB 机制都会破坏既有合法业务。数据库在本特性中保证的是**新子对象插入的完整性与引用语义**（FK RESTRICT、部分唯一、CHECK、`trg_ip_addresses_*`、宿主类型触发器），而非「不写既有行」。故不新增约束，改由 A4 + A5 机械验证。

### 5.6 新增只读检查的索引覆盖（不新增索引）

| 检查 | 查询 | 承载 |
| --- | --- | --- |
| 宿主二态点查（批内缓存） | `WHERE cluster_id=? AND hostname_key=? AND deleted_at IS NULL` | `uq_resources_cluster_id_hostname_key`（谓词完全匹配） |
| 批量既有快照 | `WHERE id IN (…)` + `selectinload(bare_metal_detail/virtual_machine_detail)` | `pk_resources`；明细 PK 即 `resource_id`（1:1） |
| 宿主内未软删同名 Interface 批量检查 | `WHERE resource_id IN (…) AND name IN (…) AND deleted_at IS NULL` | `uq_interfaces_resource_id_name`（前导 `resource_id`）+ `ix_interfaces_resource_id` |
| 同 Cluster 既有 IP 检查（保留） | `WHERE cluster_id=? AND address=? AND deleted_at IS NULL` | `uq_ip_addresses_cluster_id_address` |
| 既有值一致性比较 | 无 SQL 侧比较（取数后应用层归一化比较） | 无 DB 参与 |

### 5.7 未来触发 Schema 变更的条件（任一出现 ⇒ `layers.database` 变 true，本复核失效）

1. 引入幂等跳过 / upsert / 覆盖既有字段 / 复活软删 Resource；
2. 支持向既有 Interface 追加 IP；
3. 要求 DB 层保证「既有 Resource 零 UPDATE」（审计触发器、只读视图、时态表）；
4. 追加批 5000 行经 `EXPLAIN` 证明需要新复合/覆盖索引；
5. 需要导入批次标识 / 幂等键（batch id）；
6. R3 改为「预校验→写入间宿主被软删 ⇒ 报错」需要 DB 侧支持（需重新设计）；
7. 排序规则改为非确定性或改用 `citext`（破坏 name 区分大小写）；
8. 模板新增需落库的列（如 `parent_interface`）或新表关系。

### 5.8 Backend 可依赖的保证（仅应用层，无新 DB 对象）

- 追加宿主定位只命中未软删 Resource；宿主在写入时已软删/不可选 ⇒ `prepare_interface._lock_resource` 抛 422 行错误（沿用既有 `field` 映射）。
- 同名 Interface、同 Cluster 同 IP、并发新建同 hostname 的最终仲裁均落在既有三条部分唯一索引，败方 23505 经 `_attribute_integrity` 归因 `name` / `ip` / `hostname`，整批回滚零残留。
- 触发器归因口径不变（F023-DB-02 继续有效）。
- 追加不产生 `resources` UPDATE ⇒ `version`、`updated_at` 不变，无 `resource` UPDATE Audit（A4/A5）。

### 5.9 Issues 状态更新

| ID | 状态 |
| --- | --- |
| F023-DB-01 | CLOSED（F035 仅扩展 `resources` 预锁集合，仍同表同序、SAVEPOINT 外） |
| F023-DB-02 | 继续有效（未变） |
| F023-DB-03 | 继续有效（未变；追加场景见 §5.6 触发条件） |
| F035-DB-NOTE-01 | NOTE：`name` 区分大小写依赖库排序规则为确定性（环境事实，非阻塞） |
| F036-DB-NOTE-01 | NOTE（F036）：`RowError.field` 的并发软删归因标签 `resource` → `hostname` 属应用层/契约层措辞修正（F023 v2 §11 澄清），不改 DB 对象、不改约束归因口径、不引入新不变量 |

### 5.10 结论

`NOT_REQUIRED` 复核通过：无 Schema 交付；追加能力的数据库兜底仍是三个部分唯一索引；F023-DB-01 锁序扩展为「追加宿主并入 `resources` 预锁集合」；验证以**零 Schema 漂移断言**（A1–A5）替代约束验证，并发以真实 PG 双会话用例（V11.1–V11.5）承载。
