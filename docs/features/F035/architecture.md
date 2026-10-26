# F035 向既有 Resource 追加 Interface/IP 导入 — ARCHITECTURE 阶段报告

- **状态**：READY FOR DESIGN
- **版本**：v1（2026-10-26）
- **上游依据**：
  - `docs/product/requirements-v3.md` **revision 14**：§24.6（CONFIRMED 全节）、§24 / §24.1 / §24.5（经 §24.6 修订的措辞）、§11.1、§13.2、§14、§21、§22、§23、§23.2、§27、§31 **T117–T126** 及修订后的 T67 / T71、§32。
  - 用户裁定（CONFIRMED）：CHG013-BQ01=B / BQ02=B / BQ03=A / BQ04=A / BQ05=A / BQ06=C1 / BQ07=A / BQ08=A；plan_revision 21；`execution.authorization.feature_ids=[F035]`。
  - `docs/features/F035/product.md` v1；`docs/project/proposals/CHG-013-append-interface-ip.md` §10/§11；Architect 轻量全局评估（2026-10-26）。
  - 既有基线：`docs/api/F023.md` **v2**（本 Gate 定稿，见 §6）、`docs/features/F023/*`（DONE，证据不改写）。
- **契约**：`docs/api/F023.md` **v1 → v2 正文升版**（替代 §4 计数 bullet、§8.1、§11、§12.3 第 1–2 项、§13 第 1/3 项；端点/字段/错误码/`reason` 集合/模板/上限/权限/原子性零变更）。

## 1. 范围

「资源 + 网卡 + IP」导入（26 列宽模板、文件与文本两种载体）中，组键 `(cluster, hostname)` **已存在且未软删**时改为在该既有 Resource 下新建 Interface 与 IPAddress 并绑定，**不新建 Resource、不修改既有 Resource 任何字段、不覆盖既有子对象**（§24.6）。

明确不做：新端点 / 查询参数 / 错误码 / `reason` 注册项 / 响应字段 / 模板列 / 上限 / 权限 / Schema / Migration；不做 upsert、幂等跳过、部分成功、向既有 Interface 追加 IP、复活软删 Resource、创建 Network / Pool / Cluster / Host / Service / Endpoint、触发自动分配；F014 入口零改动。

## 2. 现状核对（代码事实，HEAD `5a4f4c1`）

| 事实 | 位置 | 意义 |
| --- | --- | --- |
| `_parse_row` 末尾既有冲突块同时报 `hostname` 与 `ip` | `backend/app/services/resource_interface_ip_import.py:723-745` | 唯一实质冲突点：`hostname` 分支改为查得宿主 id，`ip` 分支原样保留（BQ03=A） |
| 组内一致性由纯函数 `_merge_and_check` 完成（无 DB 访问） | 同文件 `:788-863` | 既有值比较需 DB 快照 → 新增独立组级比较步骤 |
| `_build_groups` 无条件调用 `validate_hardware` / `validate_virtual_machine_values` 并构造 `PreparedResource` | `:865-941` | 追加组复用只读校验，只是**不 stage** |
| `_acquire_locks` 只收 VM Host + `network_id`，表序 `resources → networks`、id 升序、SAVEPOINT 外 | `:1017-1048` | 追加宿主必须并入**同一** `resources` 预锁集合（单语句、同序） |
| `prepare_interface` 自持 `_lock_resource(FOR UPDATE)` 且校验同资源未软删唯一 `name` | `backend/app/services/interface.py:135-160,467-530` | 追加组直接复用即得加锁 + 唯一性；并发败方归因 `field="name"` |
| `prepare_ip_address` 校验 Network ACTIVE / §11.1 边界 / 同 Cluster 唯一 / 同 Cluster 绑定；不触发自动分配 | `backend/app/services/ip_address.py:588-640` | 与新建组同口径，零改动 |
| `stage_*` 各写一条 CREATE Audit | `resource.py:863-903`、`interface.py:531-566`、`ip_address.py:641-666` | 追加组跳过 `stage_resource` ⇒ 无 UPDATE Audit、`version`/`updated_at` 不变（T118） |
| 既有值投影 `_hardware_snapshot` / `_virtual_machine_snapshot` | `backend/app/services/resource.py:297-329` | 比较复用唯一归一化来源 |
| 三个部分唯一索引（`uq_resources_cluster_id_hostname_key`、`uq_interfaces_resource_id_name`、`uq_ip_addresses_cluster_id_address`，均 `deleted_at IS NULL`） | `alembic/versions/0004/0007/0010` | 追加能力无需 Schema 变更即有并发兜底 |

## 3. 方案

### 3.1 组级二态

`PreparedGroup` 增 `existing_resource_id: uuid.UUID | None`：

| 组键判定（仅计 `deleted_at IS NULL`） | 语义 | 写入 | `created` |
| --- | --- | --- | --- |
| 不存在（含仅软删） | 新建 | `stage_resource` → 子对象（现有路径不变） | +1 |
| 存在且未软删 | **追加** | 不 stage Resource；Interface/IP 指向该 id | +0 |

- 二态按**组**判定，不存在同组内部分新建/部分追加。
- `_parse_row` 只负责查得宿主 id（带 `(cluster_id, hostname_key)` 缓存，同组多行只发一次点查），不再产生 `hostname` 错误；组一致性阶段断言同组该值一致（防御）。
- 实现形态：改造现有写入路径，零新端点。

### 3.2 BQ02 比较列集与位置

- **列集** = 组内 canonical `resource_cells` 的键集合；`_parse_row` 仅在单元格非空时写键 → 「留空=省略不比较」由既有结构保证（BQ07=A）。
- **位置**：`_merge_and_check` 之后新增 `_check_existing_consistency(rows, snapshots)`；比较对象是**服务端归一化后的标量**（`validate_hardware` / `validate_virtual_machine_values` / `_validate_role` / `_validate_status` 输出）与既有快照值，逐一相等；字符串精确比较（不折叠大小写）、整数按数值；不做 SQL 侧归一化比较。
- **取数**：一条 `select(Resource).where(Resource.id.in_(append_ids)).options(selectinload(bare_metal_detail), selectinload(virtual_machine_detail))` + 复用 `_hardware_snapshot` / `_virtual_machine_snapshot`；`host` 比较前两侧统一为 `str`。
- **列 → 既有值**：`resource_type|role|status` → `Resource`；硬件 8 列 → `BareMetalDetail`；`memory_mb` → BM/VM 对应明细；`vcpu|disk_gb|hypervisor|host` → `VirtualMachineDetail`（`host` → `host_resource_id`）。
- 明细缺失（不变量修复态）按既有快照口径视为 `None` ⇒ 提供值即行错误。既有 `null` 不能经导入补填（BQ02=B 预期副作用，界面须说明）。
- 归因：`field` = 模板列名（`resource_type` → `"resource_type"`），`related_row=null`，`(row, field)` 去重。

### 3.3 预校验新增只读检查（T120）

- **宿主内未软删同名 Interface**：单条 `SELECT resource_id, name FROM interfaces WHERE resource_id IN (…) AND name IN (…) AND deleted_at IS NULL`，命中 → `field="name"`（区分大小写）。现状该冲突只可能出现在本批新建 Resource 上，故必须新增。
- **同 Cluster 既有 IP**：沿用 `_parse_row:733-745`（`field="ip"`，不跳过）。
- 两检查经 `parse_and_validate` 在预校验与写入再校验同函数重跑，口径天然一致；全部只读、不加锁、不写 Audit。

### 3.4 软删 Resource

宿主查询固定 `deleted_at IS NULL` ⇒ 软删行按「不存在」新建（部分唯一索引不覆盖已删行），不复活、不追加（T125）。

### 3.5 错误归因

- 删除 `_parse_row` 的 `hostname already exists` 业务分支。
- **保留** `_attribute_integrity` 的 `uq_resources_cluster_id_hostname_key → field="hostname"`（并发新建唯一性兜底，语义不同）、`uq_interfaces_resource_id_name → name`、`uq_ip_addresses_cluster_id_address → ip`、触发器归因。
- 不新增错误码、不新增 `IMPORT_INVALID_FILE.details.reason` 取值、不新增响应字段。

## 4. 事务与锁序

- 保持「解析 → 再校验 → 按组 SAVEPOINT 写入 → 全成功 commit / 任一错误 rollback」。
- `resources` 预锁集合 = VM Host id ∪ 追加宿主 id，**单语句 + `ORDER BY id` + SAVEPOINT 外**；随后 `networks` 同序（Contract §12.3）。
- 追加组不发出任何 `UPDATE`：只读加载既有 `Resource` / 明细实例、不赋值（避免 autoflush UPDATE）。
- `40P01` 仍整批回滚 + 500 `INTERNAL_ERROR`、不重试（§12.4）。

## 5. 数据完整性（data-integrity 对应表）

| 规则 | 入口 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §14 同 Cluster hostname 未删唯一 | 新建组 | `uq_resources_cluster_id_hostname_key` | 二态判定 + `_attribute_integrity` 归因 | 预校验后并发插入 → 败方 `field="hostname"`、整批回滚 | V7/V11 |
| §24.6/T120 宿主内未删同名 Interface | 追加+新建 | `uq_interfaces_resource_id_name` | **新增**只读批量检查 + `prepare_interface` | 并发同名 → 恰一成功、败方 `field="name"` | V4/V11 |
| §14 同 Cluster IP 未删唯一 | 两者 | `uq_ip_addresses_cluster_id_address` | 既有 IP 检查（保留）+ `prepare_ip_address` | 并发同 IP → 恰一成功、败方 `field="ip"` | V4/V11 |
| §11.1 / §9 CIDR 归属 | 两者 | `ck_ip_addresses_*`、`trg_ip_addresses_cidr_contains` | `ip_capacity` | `_lock_network` 串行化 | V6 |
| §24.6/T118 既有 Resource 零改动 | 追加组 | 无（不写即无变更） | 不 stage Resource、不赋值 | `FOR UPDATE` 串行化 | V2 |
| §22 每新建对象 CREATE Audit | 两者 | — | `stage_interface` / `stage_ip_address` | 回滚无残留 | V2/V7 |
| BQ02/BQ07 一致性比较 | 追加组 | 无 DB 约束（只读） | `_check_existing_consistency` | 预校验→写入二次比较 | V3 |
| §23.2 集群范围 | 两者 | — | 行级 `scope_filters`（沿用） | 未授权整批失败 | V8 |

**Database：`NOT_REQUIRED`**（无表/列/索引/约束/触发器/Migration 变更；追加依赖的三个部分唯一索引已存在）。

## 6. 契约状态

- `docs/api/F023.md` **v2 READY**（Architect 签核 2026-10-26；替代条款与衔接说明见该文件头部与 §17 修订表）；`docs/api/F014.md` 仅加「追加能力不适用于本文件」事实补注（正文版本仍 v1，行为零变更）。
- `layers = {database: false, backend: true, frontend: true}`；`api_required = true`（仅 F023 正文升版，无新端点）。

## 7. 逐文件工作项

### 7.1 Backend（`backend/app/services/resource_interface_ip_import.py` 主改）

1. `ParsedRow` 增 `existing_resource_id: uuid.UUID | None = None`。
2. `_parse_row`：新增 `existing_cache`；删除 `hostname already exists` 分支，改为查得宿主 id；保留 IP 现存检查与其余校验顺序/错误文本/行号。
3. 新增 `ExistingSnapshot` + `_load_existing_snapshots(db, rows)`（`selectinload`）。
4. 新增 `_check_existing_consistency(rows, snapshots)`（§3.2）。
5. 新增 `_check_existing_interface_names(db, rows)`（§3.3）。
6. `parse_and_validate`：在 `_merge_and_check` 之后追加两处新检查。
7. `PreparedGroup` 增 `existing_resource_id`；`_build_groups` 从组首行赋值并断言组内一致。
8. `_acquire_locks`：`resource_ids = sorted(VM Host ∪ 追加宿主)`，单语句、`ORDER BY id`、SAVEPOINT 外。
9. `write_import`：组内二态——存在宿主则跳过 `stage_resource` 且不计数；Interface/IP 写入与计数不变；失败归因与整批回滚不变。
10. 模块 docstring 补「组级二态 + F023 v2」说明。
11. **零 diff 守卫**：`backend/app/services/{resource_import,resource,interface,ip_address,network,ip_capacity}.py`、`backend/app/api/v1/imports.py`、`backend/app/models/**`、`backend/alembic/**`。`resource_import.py` 的 F014 hostname 冲突块必须保留（BQ04=A）。

### 7.2 Backend 测试

- 新增 `backend/tests/integration/test_f035_append_interface_ip_import.py`（V1–V12）。
- 更新 `backend/tests/integration/test_f023_resource_interface_ip_import.py` 中因 BQ01=B 失效的「existing hostname conflict」期望（迁入 F035 用例）；**保留**两批并发新建同 hostname 的 `field="hostname"` 断言（数据库兜底）。

### 7.3 Frontend

- `ResourceInterfaceIpImportPanel.tsx`：说明追加语义（只新增、不改既有资源字段）、Resource 级列「可填须一致 / 留空=省略 / 既有 null 不能补填」、既有同名网卡与同集群既有 IP 仍报错、不支持向既有网卡再加 IP、**补录既有机器时只提交新增行**；`created===0` 时给定性说明「本批未新建资源（全部追加到既有资源）」，**不展示**追加数 M。
- `ResourceImportPanel.tsx`：加一行「资源导入不支持追加，需追加请用『资源+网卡+IP』导入」（BQ04=A）。
- `frontend/scripts/smoke-client.mjs`：更新 F023/F034 段的契约引用（v1→v2）与因文案变化的断言；wire 断言零改动。

## 8. 验证策略（交 Tester 出 TEST_DESIGN）

| ID | 覆盖 | 验收 |
| --- | --- | --- |
| V1 | 纯追加成功（BM 与 VM 各一） | T117 |
| V2 | 既有 Resource 全列 + `version` + `updated_at` + 既有子对象快照不变；无 `resource` UPDATE Audit；新子对象各一条 CREATE | T118 |
| V3 | Resource 级列不一致逐列 → 对应 `field`；`resource_type` → `resource_type`；留空不比较、不置空、null 不补填 | T119 |
| V4 | 既有同名 Interface → `name`（大小写敏感）；同 Cluster 既有 IP → `ip`；不跳过 | T120 |
| V5 | Interface 追加规则沿用（type/enabled/mac/speed/mtu/唯一/无 parent） | T121 |
| V6 | IP 追加规则沿用（CIDR/§11.1/唯一/绑定同 Cluster/不触发自动分配） | T122 |
| V7 | 混合批原子性 + 预校验后状态变化 422 整批回滚 | T123 |
| V8 | 纯追加 `created=0`；权限 403/401；未授权集群行整批失败 | T124 |
| V9 | 软删 Resource 视为不存在；不创建其它对象；同名网卡报错而非追加 IP | T125 |
| V10 | 零回归（F014 冲突仍报错、F023 新建路径、T64–T72、T107–T116、T73–T84/T100–T106、模板/端点/错误码/上限） | T126 |
| V11 | 真实 PG 双会话并发：不同网卡名均成功 / 同网卡名恰一成功 / 同 IP 恰一成功 / 两批新建同 hostname 恰一成功 / 无 `40P01` 锁环 | §12.3、T123 |
| V12 | 观察项：预校验为追加后写入前宿主被软删 → 按新建处理（不断言为错误） | T125 |

## 9. 技术决策

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-F035-01 | 改造现有写入路径，`PreparedGroup.existing_resource_id` 组级二态，零新端点 | CONFIRMED |
| DR-F035-02 | 追加组复用 `prepare/stage_interface`、`prepare/stage_ip_address`，跳过 `stage_resource` | CONFIRMED |
| DR-F035-03 | 追加宿主并入 `resources` 预锁集合（同表同序、单语句、SAVEPOINT 外） | REQUIRED |
| DR-F035-04 | 计数 C1：`created` = 新建 Resource 组数；纯追加批为 0；无新响应字段 | CONFIRMED |
| DR-F035-05 | 预校验新增只读「宿主内未软删同名 Interface」批量检查 | REQUIRED |
| DR-F035-06 | BQ02 比较列集 = canonical `resource_cells` 键集合；组级比较；归一化标量；批量取数 | CONFIRMED + 实现形态 |
| DR-F035-07 | 既有值投影复用 `_hardware_snapshot` / `_virtual_machine_snapshot` | PROPOSED → CONFIRMED（定稿） |
| DR-F035-08 | 归因：`field` = 模板列名（含 `resource_type`），`related_row=null`，去重 | CONFIRMED（定稿） |
| DR-F035-09 | 删除 hostname 业务冲突检查，保留 DB 唯一归因（并发新建兜底） | REQUIRED |
| DR-F035-10 | 软删 Resource 不参与判定、按不存在处理、不复活 | CONFIRMED |
| DR-F035-11 | 前端不展示追加数 M，仅 `created=0` 定性说明 | CONFIRMED（定稿） |
| DR-F035-12 | 新检查经 `parse_and_validate`，预校验与写入同口径 | REQUIRED |
| DR-F035-13 | F014 零 diff（含其 hostname 冲突块），差异仅由界面文案说明 | CONFIRMED |
| DR-F035-14 | F023 正文升版 v2（显式替代关系 + 增补节衔接），不用增补节 | REQUIRED |

## 10. 风险与待核对

| ID | 内容 | 处理 |
| --- | --- | --- |
| R1 | 既有 `null` 字段不能经导入补填（BQ02=B 预期副作用） | 界面文案必须写明 |
| R2 | 用户原始样本（含已导入行）仍整批失败（BQ03=A / BQ08=A） | 界面写明「只提交新增行」 |
| R3 | 预校验→写入间宿主被软删 ⇒ 按新建处理（可能「本意追加却新建」） | V12 观察项；改为报错需新提案 |
| R4 | `resource_type` 同时是业务不一致归因与 DB 兜底归因，`reason` 文本不同 | 接受，测试区分 |
| R5 | VM 追加行仍须填 `host`（模板必填，不在省略范围）且须与既有宿主机一致 | 界面写明 |
| R6 | 追加组仍执行 `_build_groups` 只读校验但不使用其结果 | 接受（同源、只读） |
| R7 | 前端不展示追加数 M（DR-F035-11） | 如需展示须用户确认（前端推导、不改响应） |

## 11. 待核对（交其它角色）

| 对象 | 结论 |
| --- | --- |
| Database | `NOT_REQUIRED`：无 Schema 变更；三个部分唯一索引足以兜底追加并发；追加路径不产生 `UPDATE`/`version` 变化 |
| Tester | Test Design 覆盖 V1–V12（尤其 V2 零变化、V3 比较、V10 零回归、V11 真实 PG 并发） |
| Backend | §3/§4/§7.1 实现约束，零 diff 守卫 |
| Frontend | §7.3 文案，无 wire 变更、不自推计数 |

## 12. 定稿签核

- **状态**：待 CONTRACT 阶段填写（取得 Database `NOT_REQUIRED` 结论与 Test Design 后，由 Architect 核对一致性并签署 `READY FOR IMPLEMENTATION`）。
- **变更边界**：本设计绑定 requirements revision 14 §24.6 与 T117–T126、CHG013-BQ01–BQ08、F023 v2；任一变化须重新核对并重新签核。
