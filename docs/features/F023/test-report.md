# F023 资源+网卡+IP 批量导入 — TEST REPORT

- **版本**：TD-1（TEST DESIGN）；执行结果见后续 `# Test Execution` 小节
- **日期**：2026-10-15

## TEST DESIGN

- **结论**：`TEST DESIGN READY`
- **依据**：requirements revision 8 §10/§11/§11.1/§12/§13.2/§14/§21/§23/§24/§24.1/§27/§31（T64–T72）；`docs/features/F023/product.md`（A1–A10）；`docs/features/F023/architecture.md`（DR-401–DR-431；layers{database:false,backend:true,frontend:true}；api_required=true；Contract 待定稿）；`docs/api/F014.md`（复用错误码/上限/行号/解析）；`docs/database/f023-import.md`（NOT_REQUIRED）。
- READY 仅表示方案可验证，不代表测试通过、不批准实现或合并。Contract `docs/api/F023.md` 待 CONTRACT 定稿；PROPOSED 项按可观察行为判定。

### 0. 数据完整性（无 Schema 变更）
复用既有约束：`uq_resources_cluster_id_hostname_key`、`uq_interfaces_resource_id_name`、`uq_ip_addresses_cluster_id_address`、`ck_ip_addresses_address_host`/`_not_disabled`、`trg_ip_addresses_cidr_contains`/`_cluster_consistent`/`_interface_cluster`、`uq_networks_cluster_id_name_key`、`excl_networks_cluster_id_cidr`、`trg_virtual_machine_details_host_valid`。Database Gate `NOT_REQUIRED`。

### 1. 验收映射（A1–A10 / T64–T72）
层次：PURE（纯逻辑单测）/ PG（真 PostgreSQL 集成）/ API / REG（回归）/ FE-MECH / BROWSER / STATIC。
| 测试项 | 验收 | 层次 | 预期 |
| --- | --- | --- | --- |
| F023-T01 | A1/T64 | PG | 多节点多行→对应 Resource、eth0 Interface、IP 且正确绑定；Audit 每对象 1 条 |
| F023-T02/T08 | A1/A3 | PURE | 合并编排/去重（Resource/Interface）结构正确 |
| F023-T03/T04 | A2/T65 | PG | IP 越界/跨 Cluster→行错误整批回滚 |
| F023-T05 | A1/A2 | PG | Network 解析矩阵（名称/CIDR/`/mask` 优先）；`/mask` 落库剥离 |
| F023-T06 | A2 | PG | Network INACTIVE/软删→行错误 |
| F023-T07 | A3/T66 | PG | 同 hostname 合并、同接口多 IP 去重 |
| F023-T09/T10 | A4/T67 | PG | 重复/非法行含行号/字段/原因（文件内重复带 related_row） |
| F023-T11/T12 | A5/T68 | PG | 任一错误整批回滚，各表+audit 行数不变 |
| F023-T13 | A6/T69 | PG | 预校验后状态变化→写入失败不覆盖 |
| F023-T14/T15 | A7/T70 | PG | VM Host 四条件/批外快照；不隐式创建 |
| F023-T16/T17 | A8/T71 | PG+PURE+STATIC | 导入与 API 唯一性一致；无独立直写 SQL |
| F023-T18/T19/T20 | A9/T72 | API/PG | 权限 401/403；列序 422；超限 413 |
| F023-T21/T22 | A10 | REG/STATIC | F014 无回归；路由清单一致 |

### 2. 真 PG 集成用例（PG-01…14）
- PG-01 多行 happy path；PG-02 csv/xlsx 一致；PG-03 IP 归属/同 Cluster；PG-04 Network 解析矩阵（名称/CIDR/`/mask`/优先级/INACTIVE/软删）；PG-05 并发重叠 hostname/IP（恰一成功、无残留）；PG-06 唯一性与 §11.1 边界（文件内重复/现存冲突/大小写/`/30` `/31` `/32`/gateway/RESERVED/禁用段）；PG-07 VM Host 四条件+批外；PG-08 文件内重复与现存冲突（两阶段一致）；PG-09 禁用段真实边界；PG-10 整批回滚零残留（各表计数不变）；PG-11 写入再校验；PG-12 归一化与 Service Layer 一致性；PG-13 组内合并一致性（不同值→related_row）；PG-14 权限/模板/请求形状。

### 3. 后端纯逻辑单测（U-01…07）
解析/表头匹配、分组合并、Network 解析器、文件内重复、组内一致性、约束归因（DR-422，含 trigger 消息/SQLSTATE 归因）、整数/枚举/bool 解析。

### 4. 前端机制级 smoke（M-01…06）与人工浏览器（B-01…07）
M：API 函数/类型/multipart、指纹失效、预校验四态、确认门控、错误呈现、无部分成功 UI。
B：模板查看/下载、预校验错误表、确认导入成功、写入期冲突整批失败、VM Host 缺失、VIEWER 无入口、超限提示（无 DOM 工具时标 NOT TESTED）。

### 5. 回归（REG-01…05 / S-01…02）
F014 模板/端点/行为无回归；F007 `create_interface` 与 F010 `create_ip_address` 薄包装重构无回归（既有测试全绿）；无独立直写 SQL；路由/权限正确。

### 6. 上限/性能（PERF-01…04）
复用 F014 签核值（5 MiB/5000/1000 与 413）；接近 5000 行耗时/内存基线（每行 3 表 INSERT，成本高于 F014）；拒绝时延与「无部分导入」；`errors_truncated`。

### 7. 夹具/环境
复用 `backend/tests/conftest.py`（`pg_engine`/`committed_engine`/`role_client_factory` 等）与 F014/F010/F007 helper；新增 `F023_HEADERS`（26 列，按 Contract 定稿）、`f023_csv/xlsx`、`post_import`、`table_counts`（零残留）、`assert_row_error`、`concurrent_import_pair`。真 PG（`compose.test.yaml -p csmtest`）。

### 8. OPEN / 不可验证项
- OPEN-C-1 `created` 语义（行数 vs Resource 数）；OPEN-C-2 26 列定稿；OPEN-C-3 Network 解析优先级/`/mask`；OPEN-C-4 组内合并；OPEN-C-5 约束归因；OPEN-C-6 上限/性能；OPEN-C-7 templates 形状；OPEN-D-1 Database 裁决（已回：NOT_REQUIRED + F023-DB-01/02）。
- F023-UNV-1/2 浏览器 DOM/端到端无工具→NOT TESTED；UNV-3 PROPOSED 项按可观察行为；UNV-4 5000 行精确性能待 TEST；UNV-6 整体上线验收归 F016。

### 9. 结论
`TEST DESIGN READY`（TD-1）。Contract 待 CONTRACT 定稿；Database `NOT_REQUIRED`；无 Blocking。
---

# Test Execution

- **版本**：TR-1（TEST 执行）；日期 2026-10-15
- **结论**：`RETURN TO IMPLEMENTATION`
- **核对输入**：Contract `docs/api/F023.md` v1（READY）；`docs/features/F023/implementation.md` v1；TD-1（本文档 Test Design）；`docs/database/f023-import.md`（NOT_REQUIRED，F023-DB-01/02）。
- 本轮新增测试文件：`backend/tests/integration/test_f023_resource_interface_ip_import.py`（PG-01…14、U-01…07、PERF、REG/STATIC）。未修改任何生产实现、Schema 或产品规则。

## Environment

| 项 | 值 |
| --- | --- |
| 数据库 | 真 PostgreSQL `csmtest-db-1`，库 `csm_test`，网络 `csmtest_default` |
| 后端镜像 | `docker build --target test -t csm-backend-f019test ./backend`（含 `main` 实现 `524a729`） |
| 集成命令 | `docker run --rm --network csmtest_default -e TEST_DATABASE_URL='postgresql+psycopg://csm:csmtestpw@db:5432/csm_test' -e DATABASE_URL='postgresql+psycopg://csm:csmtestpw@db:5432/csm' -e PYTHONDONTWRITEBYTECODE=1 csm-backend-f019test pytest <file> -q -p no:cacheprovider` |
| 前端 | `cd frontend && npm run typecheck && npm run build && npm run smoke:client` |
| 说明 | 新增测试文件以只读卷挂载 `/app/tests`；镜像内为已合入的 `v3`/`main` 实现。未对生产库执行任何测试（DB-D10 guard 生效）。 |

## 1. 验收映射（A1–A10 / T64–T72）

| 测试项 | 验收 | 结果 | 证据 |
| --- | --- | --- | --- |
| F023-T01/T64 多节点多行 → Resource/eth0/IP 绑定 + Audit | A1 | PASS | `test_pg01_multi_node_multi_row_happy_path`（2 Resource/3 Interface/3 IP，每对象 1 CREATE Audit，掩码剥离、Network 正确） |
| F023-T03/T04 IP 归属/跨 Cluster/越界 | A2 | PASS | `test_pg03_*`、`test_pg04_*`、`test_pg04b_*` |
| F023-T07 同 hostname 合并/同接口多 IP | A3 | PASS | `test_pg01_*`、`test_pg13_*` |
| F023-T09/T10 重复/非法行含行号/字段/原因 | A4/T67 | PASS（常规路径） | `test_pg06_*`、`test_pg08_*`、`test_pg13_*`；**并发 IP 竞争下字段归因缺陷见 Defect F023-TEST-01** |
| F023-T11/T12 整批回滚零残留 | A5/T68 | PASS | `test_pg10_whole_batch_rollback_zero_residue`（各表 + audit 计数不变） |
| F023-T13 写入再校验 | A6/T69 | PASS | `test_pg11_*`、`test_pg11b_*` |
| F023-T14/T15 VM Host 四条件 + 批外快照 | A7/T70 | PASS | `test_pg07_vm_host_conditions_and_batch_external` |
| F023-T16/T17 唯一性与 API 一致 / 无直写 SQL | A8/T71 | PASS | `test_pg12_*`、`test_reg01_no_direct_write_sql` |
| F023-T18/T19/T20 权限 401/403 / 列序 422 / 413 | A9/T72 | PASS | `test_pg14_permissions_templates_shape` |
| F023-T21/T22 F014 无回归 / 路由清单 | A10 | PASS | `test_reg02_route_inventory`、回归套件（见 §5） |

## 2. 真 PG 集成用例（PG-01…14）

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| PG-01 多行 happy path | PASS | 响应 `(created,interfaces,ip,total)=(2,3,3,3)`；绑定/Network/Audit 逐项核对 |
| PG-02 csv/xlsx 一致 | PASS | 成功与错误两条路径逐字段一致（除 `format`） |
| PG-03 IP 归属/跨 Cluster | PASS | 越界 `field=ip`；外 Cluster 名称 `field=network`；外 Cluster `/mask` `field=ip` |
| PG-04 Network 解析矩阵 | PASS | 名称（大小写不敏感）/CIDR/`/mask`；INACTIVE/软删/缺失均行错误 |
| PG-04b Network 列优先级 | PASS | `network` 非空为权威；未命中不回退 `/mask` |
| PG-05a 并发重叠 hostname | PASS | 恰一成功；失败方 `field=hostname`；无残留 |
| PG-05b 并发重叠 IP（不变量） | PASS | 恰一成功；无残留（resource/interface/ip/audit 各 +1） |
| PG-05c 并发 IP 失败方归因 | **FAIL** | 失败方 `field=resource_type`、`reason=Conflict`，应为 `field=ip`（Defect F023-TEST-01） |
| PG-06 唯一性与 §11.1 边界 | PASS | 文件内重复（含 `related_row`）、现存 hostname/IP 冲突、大小写折叠、`/30` `/31` `/32`、gateway、RESERVED 边界 |
| PG-07 VM Host 四条件 + 批外 | PASS | 缺失/非 BM/跨 Cluster/软删均 `field=host`；批内新建 BM 不可作 Host；有效 BM 通过 |
| PG-08 两阶段一致 | PASS | 预校验与写入再校验错误一致；现存冲突不覆盖、无 UPDATE Audit |
| PG-09 禁用段真实边界 | PASS | `127/8`、`169.254/16`、`224/4` 段内地址 `field=ip`，整批 422 |
| PG-10 整批回滚零残留 | PASS | breakdown: total=3/importable=2/error=1；各表 + audit 不变 |
| PG-11 写入再校验 | PASS | 预校验后 hostname / IP 被外部占用 → 422，不覆盖 |
| PG-12 归一化/Service Layer 一致 | PASS | 导入 hostname 折小写；API 同名/同接口/同 IP 均 409，唯一性范围一致 |
| PG-13 组内合并一致性 | PASS | resource 级 `role`、interface 级 `mtu`、`resource_type` 冲突均带 `related_row=首行` |
| PG-14 权限/模板/请求形状 | PASS | 401 先于 403；VIEWER 403、模板 200 且 26 列/`applies_to`/必填正确；`format` 422；表头 422；413；404/405 |

## 3. 后端纯逻辑直调（U-01…07）

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| U-01 解析/表头匹配 | PASS | `test_u01_header_matching`（exact / header_missing / column_order / unknown / missing） |
| U-02 分组/合并 | PASS | `test_u02_u04_u05_*`（`_group_by_resource`/`_group_by_interface`/`_canonicalize`） |
| U-03 Network/IP 解析器 | PASS | `test_u03_*`（`/mask` 仅解析、落库剥离；IPv6/非法/`/33` 报错） |
| U-04 文件内重复 | PASS | `_merge_and_check` 同 `(cluster,ip)` → `field=ip`、`related_row` |
| U-05 组内一致性 | PASS | `_canonicalize` 冲突 `(row,field,related_row)` |
| U-06 约束归因（DR-422） | PASS | `test_u06_constraint_attribution`（UNIQUE/CHECK 约束名 + 触发器消息/SQLSTATE 文本分支 + 未知→`resource_type`） |
| U-07 整数/枚举/bool 解析 | PASS | `test_u07_*`（`_parse_int`/`_parse_bool`/`_validate_resource_type`） |

> 说明：TD-1 将 U-01…07 列为 PURE；本轮以服务层纯函数/非提交核心直调补齐，未改动实现。U-06 的 `_app_error_field` 分支未覆盖 `AppError.details["field"]`（见 Defect F023-TEST-01）。

## 4. 前端机制级 smoke（M-01…06）与人工浏览器（B-01…07）

- **M-01…06**：`npm run typecheck` 通过；`npm run build` 通过；`npm run smoke:client` **319 passed, 0 failed**（含 13 个 F023 机制级用例：模板列/`applies_to`、multipart 形状、401/403/413/422 文案、`VALIDATION_ERROR` 字段映射、本地解析/大小拦截、file+format 指纹失效、确认门控、26 列表头文本、渲染标签）。独立复跑，未复用开发者结果。**PASS**
- **B-01…07**（模板查看/下载、预校验错误表、确认导入成功、写入期冲突整批失败、VM Host 缺失、VIEWER 无入口、超限提示）：当前环境**无浏览器 DOM/E2E 工具**，**NOT TESTED**；前端机制级已覆盖 API 契约与门控，但真实浏览器交互未验证。

## 5. 回归（REG）

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| REG-01 无独立直写 SQL / 经 Service Layer | PASS | `test_reg01_no_direct_write_sql`（`stage_*`/`prepare_*`，无 `insert into`/`update resources`/`delete from`） |
| REG-02 路由清单 | PASS | `test_reg02_route_inventory`（F023 三路由存在；F014 三路由不变） |
| REG-03 F014 全套无回归 | PASS | `test_imports.py`、`test_import_tester_acceptance.py`、`test_import_constraints.py`、`test_import_performance.py` |
| REG-04 F007 `create_interface` 薄包装无回归 | PASS | `test_interfaces.py`、`test_interface_constraints.py` |
| REG-05 F010 `create_ip_address` 薄包装无回归 | PASS | `test_ip_addresses.py`、`test_ip_address_constraints.py`、`test_f019_interface_ip_binding.py` |
| 回归合计 | PASS | **148 passed**（F014 + F007 + F010 + F019，真 PG，0 failed） |

## 6. 上限/性能（PERF-01…04）

| 用例 | 结果 | 观测 |
| --- | --- | --- |
| PERF-01 上限拒绝（413，无部分导入） | PASS | 5001 行 → 413 `IMPORT_ROW_LIMIT_EXCEEDED`，拒绝后各表计数不变；超字节 → 413 `IMPORT_FILE_TOO_LARGE` |
| PERF-02 预览截断 | PASS | `error_count` 全量、`errors` 受 `import_error_preview_limit` 限制、`errors_truncated=true` |
| PERF-03 接近 5000 行基线（真 PG） | PASS | 5000 行：`validate=36.98s / peak 7.7MB`；`write=218.92s / peak 12.5MB`；`(created,interfaces,ip,total)=(5000,5000,5000,5000)`，各表 +5000、audit +15000，写入 `< 600s` 兜底。**无正式阈值**（Contract §14 未给数值；每行 3 表 INSERT，成本高于 F014 的 ~43s） |
| PERF-04 并发重叠恰一成功无残留 | PASS | PG-05a（hostname）、PG-05b（IP）恰一成功、无残留；失败方字段归因缺陷见下 |

## 7. Defects

| ID | 级别 | 描述 | 证据 | Owner |
| --- | --- | --- | --- | --- |
| F023-TEST-01 | **MEDIUM** | **并发重叠 IP 失败批的行错误字段归因错误。** 两个批次并发写入同一 `(cluster, ip)` 时，失败批在 SAVEPOINT 内由 `prepare_ip_address` 抛 `Conflict.unique_conflict("address")`（共享网络行锁串行后重校验）。`write_import` 的 `_app_error_field` 仅解析 `details["fields"]`，未映射 `Conflict.details["field"]`，因此发出 `RowError{field:"resource_type", reason:"Conflict"}`；Contract §11 要求现存 IP 冲突 `field="ip"`，DR-422 要求 `uq_ip_addresses_cluster_id_address → ip`。批次仍正确整批回滚、无残留（原子性不变量成立）。建议在 `_app_error_field`/`_error_message` 中按 `AppError.details["field"]`（`address→ip`、`name→name`、`network→network` 等）与具体 reason 归因。 | `test_pg05c_concurrent_ip_loser_attribution`（FAIL）；`test_pg05b_*` 证明不变量 PASS | Backend |
| F023-TEST-02 | LOW（观察，非阻塞） | **Network 解析未按批缓存。** Contract §9 注明「解析按 Network 批内缓存」，但 `_parse_row` 每行都调用 `_resolve_network` 查询数据库（`cluster_cache` 仅缓存 Cluster）。行为正确但 5000 行预校验产生 ~5000 次网络点查（观测 `validate=36.98s`）。 | PERF-03 观测；源码核对 | Backend |

**Defect 汇总**：F023-TEST-01 MEDIUM（需修复）、F023-TEST-02 LOW（观察）。无数据损坏、无部分成功、无越权。

## 8. 未验证项（NOT TESTED）

- B-01…07：真实浏览器 DOM/E2E（无工具）。
- 精确 5000 行生产硬件性能 SLA（Contract 未给数值；仅给出真 PG 基线与兜底上限）。
- F016 整体上线端到端验收（归 F016）。

## 9. 结论

`RETURN TO IMPLEMENTATION`

- 26 个 F023 用例通过（含 PG-01…14 中 15 项、U-01…07、REG/STATIC），PERF-03 单独通过；前端 319 passed；回归 148 passed。
- 发现 1 个 MEDIUM 实现缺陷（F023-TEST-01，并发 IP 失败批字段归因），Owner：Backend；修复后按影响重测 `test_pg05c_concurrent_ip_loser_attribution` 即闭环。
- 核心验收（A1–A10 / T64–T72）其余项通过；原子性、零残留、唯一性、Network 解析、VM Host、再校验、权限/上限/模板均满足已批准设计。

## 10. Git

本轮仅新增未跟踪测试文件，未修改任何生产实现；`.agents/` 为本会话工具产物，非交付物、未纳入交付。

GIT: git rev-parse --short HEAD
GIT: git status --short
GIT: git diff --stat
GIT: git ls-files --others --exclude-standard backend/tests

---

# Test Execution — Repair Round 1（F023-TEST-01 复测）

- **版本**：TR-1-R1（修复后重测）；日期 2026-10-19
- **结论**：`READY FOR REVIEW`
- **修复提交**：`37284b6`（fix(F023): attribute Conflict field to row column (F023-TEST-01)）；**Base** `codex/v3.1` = `db6b659`；**候选 HEAD** = `37284b6`（工作区干净，仅 `.agents/` 未跟踪）。
- **核对输入**：Contract `docs/api/F023.md` v1；`docs/features/F023/implementation.md`；TD-1；缺陷 F023-TEST-01。修复仅改 `backend/app/services/resource_interface_ip_import.py::_app_error_field`（回退读取 `AppError.details["field"]`），未改 Schema / 产品规则 / 测试。
- 上文 TD-1（Test Design）与 TR-1（首轮执行记录，含 F023-TEST-01 FAIL、F023-TEST-02 LOW）完整保留；TR-1 的 `RETURN TO IMPLEMENTATION` 结论已被本节取代，其 F023-TEST-01 判定失效范围仅限该缺陷行。

## Environment（Repair Round 1）

| 项 | 值 |
| --- | --- |
| 数据库 | 真 PostgreSQL `csmtest-db-1`，库 `csm_test`，网络 `csmtest_default` |
| 后端镜像 | 重建 `docker build --target test -t csm-backend-f023r1 ./backend`（构建上下文 = HEAD `37284b6`）；镜像内 `_app_error_field` 已含 `details["field"]` 回退（`docker run … inspect.getsource` 核对 `HAS_FALLBACK`） |
| 集成命令 | `docker run --rm --network csmtest_default -e TEST_DATABASE_URL='postgresql+psycopg://csm:csmtestpw@db:5432/csm_test' -e DATABASE_URL='postgresql+psycopg://csm:csmtestpw@db:5432/csm' -e PYTHONDONTWRITEBYTECODE=1 csm-backend-f023r1 pytest <target> -q -p no:cacheprovider` |
| 前端 | `cd frontend && npm run typecheck && npm run build && npm run smoke:client` |
| 说明 | 未对生产库执行任何测试（DB-D10 guard 生效）。测试文件 `backend/tests/integration/test_f023_resource_interface_ip_import.py` 为已提交内容，本轮未新增/修改测试代码（`git diff --stat` 为空）。 |

## 1. 缺陷复测（F023-TEST-01）

| 验证项 | 方法 | 结果 | 证据 |
| --- | --- | --- | --- |
| 并发重叠 IP 失败批 `field="ip"` | `test_pg05c_concurrent_ip_loser_attribution` 独立执行 | **PASS（缺陷关闭）** | 失败批行错误 `field="ip"`（`_find_error(details, "ip")` 命中）；修复前为 `field="resource_type"` |
| 并发重叠 IP 恰一成功、无残留 | `test_pg05b_concurrent_overlapping_ip` | PASS | 恰一成功；resource/interface/ip 各 +1、audit +3 |
| 并发重叠 hostname 归因不回归 | `test_pg05a_concurrent_overlapping_hostname` | PASS | 失败方 `field="hostname"`；恰一成功无残留 |
| 同 Cluster 唯一 `(cluster, ip)` 仍成立 | PG-05b + PG-12 | PASS | 并发/API 两路径唯一性范围一致 |
| 整批回滚零残留仍成立 | `test_pg10_whole_batch_rollback_zero_residue` | PASS | 各表 + audit 计数不变 |
| `-k pg05` 三项 | `pytest … -k pg05 -v` | **3 passed, 25 deselected** | 5.24s |

**结论**：F023-TEST-01（MEDIUM）已在 `37284b6` 修复并经独立复测确认，字段归因符合 Contract §11 / DR-422；原子性与唯一性不变量保持。

## 2. 验收映射（A1–A10 / T64–T72）复测状态

| 验收 | 对应用例 | TR-1 | Repair Round 1 |
| --- | --- | --- | --- |
| A1/T64（多节点多行 Resource/Interface/IP + Audit） | `test_pg01_*`、`test_u02_*` | PASS | **PASS** |
| A2/T65（IP 归属/跨 Cluster/越界/Network 解析） | `test_pg03_*`、`test_pg04_*`、`test_pg04b_*` | PASS | **PASS** |
| A3/T66（同 hostname 合并、同接口多 IP 去重） | `test_pg01_*`、`test_pg07_*`、`test_pg13_*` | PASS | **PASS** |
| A4/T67（重复/非法行含行号/字段/原因） | `test_pg06_*`、`test_pg08_*`、`test_pg13_*`、`test_pg05c_*` | PASS（常规）/ FAIL（并发 IP） | **PASS**（并发 IP 归因已修复） |
| A5/T68（任一错误整批回滚零残留） | `test_pg10_*` | PASS | **PASS** |
| A6/T69（写入再校验） | `test_pg11_*`、`test_pg11b_*` | PASS | **PASS** |
| A7/T70（VM Host 四条件 + 批外快照） | `test_pg07_vm_host_conditions_and_batch_external` | PASS | **PASS** |
| A8/T71（与 API 唯一性一致/无独立直写 SQL） | `test_pg12_*`、`test_reg01_no_direct_write_sql` | PASS | **PASS** |
| A9/T72（权限 401/403、列序 422、413） | `test_pg14_permissions_templates_shape` | PASS | **PASS** |
| A10（F014 无回归/路由清单） | `test_reg02_route_inventory` + 回归套件 | PASS | **PASS** |

A1–A10 / T64–T72 全部 PASS，无 BLOCKED / NOT TESTED（BROWSER 例外见 §4）。

## 3. 执行结果（独立复现）

| 目标 | 实际数字 | 结果 |
| --- | --- | --- |
| F023 集成文件 `tests/integration/test_f023_resource_interface_ip_import.py` | **28 passed**, 1 warning in 279.89s | PASS |
| 全量 `tests/` | **700 passed, 2 skipped**, 1 warning in 850.99s | PASS |
| `-k pg05` | 3 passed, 25 deselected | PASS |
| 前端三命令 | `typecheck` 通过；`build` 通过（`✓ built in 12.73s`）；`smoke:client` **319 passed, 0 failed** | PASS |

跳过项（与 TR-1 一致，非阻塞）：`test_f016_acceptance.py`（需 `F016_ACCEPTANCE=1`）、`test_migrations.py`（需非超级用户 DB owner 行使 V3b / DB-D11）。

## 4. 前端浏览器（B-01…07）

当前环境无浏览器 DOM/E2E 工具，B-01…07 **NOT TESTED**（模板查看/下载、预校验错误表、确认导入成功、写入期冲突整批失败、VM Host 缺失、VIEWER 无入口、超限提示）。前端机制级 smoke 已覆盖 API 契约、字段映射与确认门控；真实浏览器交互待具备工具后验证。

## 5. Defects（Repair Round 1）

| ID | 级别 | 状态 | 说明 |
| --- | --- | --- | --- |
| F023-TEST-01 | MEDIUM | **CLOSED / VERIFIED** | `37284b6` 使并发重叠 IP 失败批归因 `field="ip"`；`test_pg05c_*` 复测 PASS；原子性与唯一性不变量保持。 |
| F023-TEST-02 | LOW（观察） | **OPEN（不阻塞）** | Network 解析未按批缓存（`_parse_row` 每行点查）；行为正确，`validate=36.98s`（5000 行）观测；Contract §9 缓存为优化项，按既定处理不阻塞。 |

## 6. 未验证项（NOT TESTED）

- B-01…07：真实浏览器 DOM/E2E（无工具）。
- 精确 5000 行生产硬件性能 SLA（Contract 未给数值；仅真 PG 基线与兜底上限）。
- F016 整体上线端到端验收（归 F016）。

## 7. 结论

`READY FOR REVIEW`

- F023-TEST-01 MEDIUM 已修复并独立复测确认（`test_pg05c_*` PASS），无必须修复问题。
- F023 集成 28 passed；全量 700 passed, 2 skipped；前端 319 passed；A1–A10 / T64–T72 全部 PASS。
- F023-TEST-02 LOW 按既定处理，不阻塞；B-01…07 因缺工具标 NOT TESTED。
- Tester 未修改任何生产实现、Schema 或产品规则。

## 8. Git（Repair Round 1）

本轮仅重建测试镜像并按只读方式读取源码，未修改生产实现、Schema、测试或配置；`.agents/` 为非交付工具产物，未触碰。

GIT: git log --oneline -5
GIT: git show 37284b6 --stat
GIT: git show 37284b6
GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git rev-parse --short db6b659
GIT: git diff --stat
GIT: git ls-files --others --exclude-standard backend/tests docs/features/F023
