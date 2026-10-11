# F014 CSV / Excel 批量导入 — DATABASE 复核（NOT_REQUIRED）

- **签核**：Database；设计版本 v1（2026-10-09）
- **结论**：`NOT_REQUIRED`（`layers.database=false` 复核通过；无 Schema 交付、无 Migration）
- **上游依据**：`docs/features/F014/architecture.md`（DR-190–DR-212、§3 数据影响、§9 layers database=false、§10 验证策略）、`docs/features/F014/product.md`（A1–A26、I-1–I-17）、`docs/api/F014.md` v0 草案；`docs/database/f004-resource.md` v1（DB-D33–D44）、`f003-cluster.md` v2（DB-D20–D32）、`f005-bare-metal.md` v1（DB-D45–D52）、`f006-virtual-machine.md` v1（DB-D53–DB-D63）、`f013-search-index.md`（DB-D157–D166）；`.pi/skills/data-integrity/SKILL.md`
- **覆盖**：F014 导入写入路径的库级完整性复核、索引需求裁定、SAVEPOINT 与既有约束/触发器兼容性；**不覆盖** API 契约定稿、TEST 执行。

> 说明：本 Feature 无新表/新列/新约束/新触发器/新索引/迁移，故本文只做复核与裁定，不引入 DB-D 设计决策；编号留空给后续有 Schema 变更的 Feature。

## 1. 复核结论：无需 Schema 变更

F014 导入是既有创建路径的批量入口，**只写** `resources` + `bare_metal_details` / `virtual_machine_details`（均既有表），复用既有约束：

| 导入行为 | 既有 DB 对象 | 依据 |
| --- | --- | --- |
| 同 cluster hostname 唯一（文件内 + 现存 + 并发） | `uq_resources_cluster_id_hostname_key UNIQUE(cluster_id, hostname_key) WHERE deleted_at IS NULL` | f004 DB-D38 |
| hostname 归一化口径（trim + ASCII 小写、key 一致） | `ck_resources_hostname_ascii_lower` / `ck_resources_hostname_key_matches` | f004 DB-D36/DB-D37 |
| cluster 引用 | `fk_resources_cluster_id_clusters`（RESTRICT） | f004 DB-D39 |
| cluster 按 code 解析 | `uq_clusters_code_key`（全量唯一）+ PK | f003 DB-D22 |
| 枚举 / 默认 | `ck_resources_resource_type/role/status`、DEFAULT | f004 DB-D34 |
| hardware 数值/字符串 | `ck_bare_metal_details_*_range/format`、类型匹配触发器 | f005 DB-D46/DB-D49 |
| VM 数值/字符串 + Host 正确性 | `ck_virtual_machine_details_*`、`trg_..._type_match`、`trg_..._host_valid`、`fk_..._host_resource_id_resources`（RESTRICT） | f006 DB-D54/DB-D55/DB-D56/DB-D58 |
| VM Host 解析（按 cluster + hostname） | `(cluster_id, hostname_key)` 部分唯一可作索引；`ix_resources_cluster_id` | f004 DB-D38/DB-D41 |
| Audit 同事务 | `audit_logs` append-only 触发器（0003） | f003 DB-D27/DB-D28 |

无既有约束被绕过，无新约束需求，**无 Migration、无回填、无回滚风险**。`layers.database=false` 成立，交 `NOT_REQUIRED`。

## 2. 索引需求裁定（正式）

**裁定：`NOT_REQUIRED`——不新增任何索引。** 依据：

1. **文件内重复检查**在应用内存中完成（`(cluster_id, hostname_key)` 字典 + 两行行号），**不产生 DB 查询**，与索引无关（DR-204）。
2. **现存冲突 / hostname 唯一查询**：`SELECT 1 FROM resources WHERE cluster_id=? AND hostname_key=? AND deleted_at IS NULL` 命中 `uq_resources_cluster_id_hostname_key`（部分唯一 btree；查询谓词 `deleted_at IS NULL` 与该索引谓词一致，可直接 Index Scan）。hostname 选择性高，无额外索引收益。
3. **VM Host 解析**：`WHERE cluster_id=? AND hostname_key=? AND deleted_at IS NULL`（再按 `resource_type='BARE_METAL'` 过滤）复用同一 `(cluster_id, hostname_key)` 部分唯一索引前缀，hostname 选择性高，`resource_type` 后过滤成本可忽略；UUID 形式走 PK。
4. **cluster 解析**：code 走 `uq_clusters_code_key`，UUID 走 PK；批内缓存（architecture §6），多为一次查询。
5. 导入上限 `MAX_IMPORT_ROWS` 默认 5000（DR-196/DR-212），单请求索引点查规模为 O(行数)，均在既有 btree 上；`ix_virtual_machine_details_host_resource_id`（f006 DB-D54）已覆盖 Host 反向引用，导入不引入新查询形态。
6. 拒绝过度建索引（AGENTS §2.6）：无未定增益不新增对象。

> 触发复核的条件（非阻塞）：若 D03 真实 PG 性能证据显示某查询为热点且缺索引，再由 Architect 走变更控制追加迁移；当前无证据。

## 3. SAVEPOINT + 既有约束/触发器兼容性

**结论：不冲突。** 逐行 `db.begin_nested()`（DR-203）与既有触发器/约束语义正交：

- `trg_resources_immutable_fields` 为 **BEFORE UPDATE**（f004 DB-D40）；导入路径仅 INSERT（I-6 不更新/覆盖），该触发器在导入中不触发，无 restrict_violation 风险。
- `trg_bare_metal_details_type_match` / `trg_virtual_machine_details_type_match` / `trg_..._host_valid` 为 **BEFORE INSERT OR UPDATE**，在 SAVEPOINT 作用域内正常执行；合法行通过，违约抛 `restrict_violation`，可被子事务捕获并回滚到 SAVEPOINT，与普通 INSERT 行为一致。
- `trg_audit_logs_append_only` 仅拦 UPDATE/DELETE；导入只 INSERT 审计，无冲突。
- 同事务内 FK 校验可见未提交行：Resource 先于其 detail 插入，同一事务内 FK 满足；`ON DELETE CASCADE/RESTRICT` 在导入（仅 INSERT）路径不触发。
- 唯一约束违反（并发同名）在 SAVEPOINT 内抛出 → 归因行错误 → 最终 `db.rollback()` 整批回滚，零残留（DR-203/DR-206）。

**完整性风险 / 已知差异（记录，不阻塞）：**

1. **批外 Host 为应用层保证**（DR-205/I-9）：`trg_host_valid` 只校验「未软删 + BARE_METAL + 同 cluster」，**无法表达「批次开始前已存在」的时间语义**；同批新建 BM 被本批 VM 引用的拦截完全由应用的事务开始快照负责，DB 不兜底。属已确认设计，交 Backend/Reviewer 核对实现（非 Schema 问题）。
2. **Cluster 软删窗口**：FK 只保证引用行物理存在，不保证未软删；与 F004 `POST /resources` 同口径，导入不额外收紧（architecture §7 NOTE、§11）。应用校验器负责；残余窗口与既有行为一致。
3. **SAVEPOINT 回滚纪律**（实现风险）：PG 在语句报错后事务进入 aborted 状态，**必须先 `ROLLBACK TO SAVEPOINT` 才能继续**；若实现未捕获即继续发语句将全部失败。须由 SQLAlchemy `begin_nested()` 上下文管理器承载，交 Backend（非 DB 约束）。
4. 部分唯一索引仅覆盖 `deleted_at IS NULL`：导入只插入未删行，全覆盖；软删 hostname 可重用符合 §21（A13）。

## 4. 数据完整性对应表（引用 data-integrity SKILL）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §7 / D01 §5.3（f004 v1） | 同 cluster hostname 唯一；导入 + API | 部分唯一 `uq_resources_cluster_id_hostname_key` + key CHECK | 归一化 key + 文件内/现存重复检查 | 并发由唯一约束兜底 → SAVEPOINT 归因 → 整批回滚 | V-DB-F014-1/2/3 |
| §4.1/§6 | cluster 引用必填有效 | FK RESTRICT + `uq_clusters_code_key` | `resolve_cluster`（存在且未软删；INACTIVE 允许） | 软删 Cluster 行仍在，FK 不破坏 | V-DB-F014-4 |
| §8/§9、D01 §3 | 单位与未知值 | 列 CHECK（memory_mb/disk_gb 等） | 校验函数 | 未知 null ≠ 0；0 表明确无 | V-DB-F014-5 |
| §9 | VM Host 正确性 | FK + `trg_host_valid`（未软删/BARE_METAL/同 cluster） | `validate_virtual_machine` + 批外快照（I-9） | Host 行 `FOR UPDATE` 串行化；**批外语义仅应用保证** | V-DB-F014-6 |
| §24 | 整批原子 | 单事务 + SAVEPOINT | 任一错误 `rollback()` | 失败无 Resource/明细/Audit 残留 | V-DB-F014-7 |
| §22 | Audit 同事务 | `audit_logs` append-only | `audit.record` staging | 回滚无 Audit | V-DB-F014-7 |
| §27 | 真实 PG | 上列全部 | — | — | 全部须真 PG；Mock 不构成证据 |

## 5. Backend / Tester 可依赖保证与计划验证项

**保证**：导入只写三张既有表；hostname 唯一由 DB 部分唯一兜底；不存在需要新增的表/列/索引/迁移；SAVEPOINT 与既有触发器兼容，导入 INSERT 路径不触发 immutable-fields 触发器；回滚不残留。

**计划测试项（真实 PG，本设计无 PASS）**：
- V-DB-F014-1 文件内重复两行 → 422 两行行号，零写入（部分唯一未被触发前即拦截）。
- V-DB-F014-2 并发重叠 hostname → 仅一成功，另一在 SAVEPOINT 内命中 `uq_resources_cluster_id_hostname_key` 后整批回滚，无重复行。
- V-DB-F014-3 软删 hostname 可重用插入成功（部分唯一谓词生效）。
- V-DB-F014-4 cluster 不存在/软删 → 行错误；INACTIVE 通过；跨 cluster hostname 允许（部分唯一按 cluster_id）。
- V-DB-F014-5 `gpu_count=0`/`disk_gb=0` 存 0 且与 NULL 可区分；正整数列 0/负被 CHECK 拒。
- V-DB-F014-6 VM Host 非 BM/跨 cluster/软删 → `trg_host_valid` 违约归因；同批新建 BM 被引用 → 应用层成功拦截（**说明 DB 不兜底**）。
- V-DB-F014-7 含 1 非法行批次 → 422 后 `resources`/`bare_metal_details`/`virtual_machine_details`/`audit_logs` 行数与调用前一致；成功批每行 1 条 CREATE Audit。
- V-DB-F014-8 对象存在断言：运行期**不新增**任何表/列/索引/触发器（对比 0013 head 的 catalog）。

## 6. 未决 / 交核

- **无 Blocking**。I-1/I-8 交验项：
  - I-1（NOTE，交 Backend/Reviewer）：SAVEPOINT 回滚纪律（§3.3）须在实现与 Review 核对。
  - I-2（NOTE，交 Backend/Tester）：批外 Host 语义无 DB 兜底（§3.1），依赖批快照；列入集成测试。
  - I-3（NOTE）：导入不改变任何既有 Schema；若 D03 性能证据要求新索引，走变更控制，不在本 Gate 预设。

## 7. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次复核：`layers.database=false` 成立，裁定 `NOT_REQUIRED`；索引无新增理由；SAVEPOINT 与既有触发器兼容性确认；记录三项 NOTE 风险。 |