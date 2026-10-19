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