# F014 CSV / Excel 批量导入 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据；TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-13
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`（TD-1）
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§5、§6、§7、§8、§9、§21、§22、§23、§24、§25、§27、§29、§31 T11/T25/T27/T28/T37/T38、§32、§34、§35.2 Q02-A/Q10-A/Q10-B、§35.3 D01/D03）
  - `docs/features/F014/product.md`（PRODUCT `READY FOR ARCHITECT`；A1–A26、I-1–I-17、OPEN I-1–I-9、明确排除项）
  - `docs/features/F014/architecture.md`（ARCHITECTURE `READY FOR DESIGN` 2026-10-09；DR-190–DR-212、§4 请求/响应/错误形态、§5 两套固定模板、§6 解析与逐行校验、§7 原子/再次校验/并发、§8 权限与配置、§9 layers.database=false、§10 验证策略、§12 D01 关闭核对）
  - `docs/api/F014.md`（**草案 v0，状态 BLOCKED 未签核**）：`POST /api/v1/imports/resources/validate`、`POST /api/v1/imports/resources`、`GET /api/v1/imports/resources/templates`
  - `docs/api/F004.md` v3（Resource/BM/VM 创建、互斥 422、hostname 归一化、权限、错误语义）、`docs/api/F003.md` v2（Cluster resolve/INACTIVE/软删）、`docs/api/F002.md` v1（§1.1 信封、§1.2 错误码与注册表、§2.1 CSRF、§3 权限矩阵）
  - `docs/architecture/d01-conventions.md` v11（§3、§4、§5.3、§5.4、§5.5）
  - `backend/tests/conftest.py` 与既有 `backend/tests/integration/` 夹具（`test_database_url` / `pg_engine` / `db_session` / `committed_engine` / `alembic_runner` / `auth_app` / `api_client` / `bootstrap_admin` / `make_user` / `role_client_factory`）
  - `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`AGENTS.md`
- **状态属性**：TD-1 `READY` 仅表示 A1–A26 已映射到可观察判据、边界/并发场景可执行、夹具与可验证性检查已建立；**不代表测试已运行、不填充执行 PASS、不批准实现或合并**。`docs/api/F014.md` 仍为草案 v0（BLOCKED），4 个新增错误码尚未登记 `docs/api/F002.md` §1.2，上限数值（I-4）待 D03 真实 PG 性能证据，模板列集/列序/行号约定/`resource_type` 保留等 OPEN 仅由 architecture 给出 PROPOSED→CONTRACT 默认。**不因 Contract 未定稿或实现未落地而直接 BLOCKED**（architecture §4–§8、§10 已给出可执行的端点、模板、错误码、上限默认、原子/并发语义与验证策略）。相关 OPEN 逐项见 §7，待 CONTRACT/D03 定稿后由 TD-2 关闭并固定执行判据。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-13 | 初版：A1–A26 映射 V1–V26（补充 V27–V32、V-FE-1…V-FE-3、V-DB-1…V-DB-3）；边界/并发/夹具 B1–B33；真 PG 可执行性评估；新依赖 `openpyxl`/`python-multipart` 可测性；错误码登记与 D03 上限性能 OPEN 清单；§7 OPEN-1…OPEN-10。 |

> **复核基线（待 TD-2）**：`docs/api/F014.md` v1 READY、`docs/api/F002.md` §1.2 登记 4 个新错误码、D03 上限/性能数值定稿、architecture 的模板列集/列序/`resource_type` 保留裁定。TD-1 的端点路径、模板列名/顺序、错误码/details 形态、上限默认值、行号约定均按 architecture §4–§8 与 Contract v0 假设；TD-2 逐项核对后方可作执行依据。

---

### 0. 数据完整性对应表（F014 范围）

方法依据 `.pi/skills/data-integrity/SKILL.md`。F014 为**新增写入入口**（无新实体/字段/状态、无 Migration）；下表聚焦「导入写入路径」与既有约束的复用。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（既有，architecture §9 database=false） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §7 / D01 §5.3（v11） | 同 cluster hostname 唯一；导入 + 普通 API | `uq_resources_cluster_id_hostname_key` 部分唯一 `WHERE deleted_at IS NULL`；`clusters.code_key` 唯一 | `normalization.normalize_hostname` + 现存/批内重复检查（DR-204）；文件内重复报两行行号 | 并发重叠 hostname 由唯一约束兜底 → SAVEPOINT 归因后整批回滚（DR-206） | V8/V9/V24、V-DB-1、B6/B7/B8/B9/B33 |
| §4.1/§6 | cluster 引用必填有效 | FK `resources.cluster_id → clusters.id` | `cluster_service.resolve_cluster`（存在且未软删；INACTIVE 允许） | 软删 Cluster 该行报错；INACTIVE 通过 | V12、B15/B16 |
| §8/§9、D01 §3/§5.4/§5.5 | 单位与未知值 | 列 CHECK（`memory_mb`/`cpu_*`/`gpu_count`/`disk_gb` 范围） | 逐行复用 `validate_hardware` / `validate_virtual_machine_values` | 未知 null ≠ 0；`gpu_count`/`disk_gb`=0 明确无 | V16/V17、B25/B26/B27 |
| §9 | VM Host 正确性 | FK `host_resource_id`；Host 反向引用检查 | `validate_virtual_machine`（存在/未软删/BARE_METAL/同 cluster），`lock` 由调用方控制（预校验 `lock=False`） | Host 行 `FOR UPDATE` 串行化；批外快照；同批 BM 不被引用（DR-205/206） | V11/V18/V19、B17/B18/B19/B20/B33 |
| §24 | 整批原子 | 单事务 + 逐行 `SAVEPOINT` | 任一错误整批 `db.rollback()`；成功一次 `commit()`（DR-203） | 失败零残留（无 Resource/明细/Audit/Activity） | V5/V6、B10/B11 |
| §22 | Audit 同事务 | `audit_logs` 同 Session | 成功每行 `audit.record` staging；失败回滚无 Audit | 回滚后 Activity 为空 | V6/V7、B11/B12 |
| §23/§24-4 | 权限 | 无 | 两写端点 `require_permission(Permission.IMPORT)`；模板 `READ`；401 先于 403 | 前端隐藏不替代服务端（DR-209） | V22、B28/B29 |
| §4 | 稳定 ID 引用 | PK UUID / FK | cluster→`cluster_id`、host→`host_resource_id`（UUID 落库，不拼接字符串） | 名称改名不影响关联 | V1/V12/V19、BISC |

---

## 1. 验收映射（product.md A1–A26 → 验证项）

执行环境代号：`真PG集成` = ASGI 应用 + 真实 PostgreSQL（非 SQLite）；`真PG约束` = 真实 PG raw SQL / `pg_indexes` / 目录断言；`真PG并发` = `committed_engine` 真实两连接并发 + 最终持久化断言；`前端` = 构建 + 真实 API 集成（非 Mock）；`静态` = 路由清单 / 源码检查。

> **分界声明（关键）**：
> - **F014 独立可验证**：A1–A26 全部（两阶段流程、聚合错误、原子回滚、Service Layer 复用、权限、模板、上限、单位/未知值、排除项）；§31 **T11**（归一化唯一）、**T25**（权限）、**T27**（预校验/再次校验/整批回滚/行号字段原因）、**T28**（Host 已存在/不覆盖/上限）、**T37/T38**（默认值/未知值/单位）在本 Feature 闭合。
> - **F014 消费 F003–F006 已 DONE 口径**：cluster 解析、hostname 归一化与唯一、BM/VM 字段校验、Audit/Activity 均为既有实现；F014 只验证「导入逐行复用同一结果 + 新增原子/聚合/回滚语义」，不重验 F003–F006 单独创建用例（归各 Feature TE）。
> - **完整跨功能 §31/§32 集成验收（F016）**：F014 只承载导入入口；**不得以 F014 局部 PASS 拼接整体通过**。
> - **database=false**：无 Migration / 新表 / 新列 / 新索引（architecture §9），Database Gate 以 `NOT_REQUIRED` 复核；F014 的 `V-DB-*` 仅验证「复用既有约束/索引」而非新增。

| 验收（product.md） | 验证项 | 测试类型 | 前置数据 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- | --- |
| A1 提供 CSV 与 `.xlsx` 两种格式新增导入，两者行为一致 | **V1** | 真PG集成 | 同一逻辑数据分别构造 CSV 与 `.xlsx` 文件；Cluster 存在 | PASS：两格式对同一数据返回一致的 `total_rows`/`importable_rows`/`errors`（行号/字段/原因）；写入均 201 且创建集合一致。FAIL：格式间结果不同、仅支持一种 |
| A2 预校验一次性展示全部错误行的行号、字段、原因（聚合不 fail-fast） | **V2** | 真PG集成 | 单文件含 ≥3 个不同错误行（cluster 不存在、hostname 非法、枚举非法） | PASS：`POST …/validate` 200，`errors` 同时含全部错误行，每项含 `row`/`field`/`reason`；非仅首个错误。FAIL：fail-fast、字段缺失 |
| A3 预校验不写业务数据/不写 Audit；重复同一文件结果一致且无副作用 | **V3**；**V-DB-2** | 真PG集成 + 真PG约束 | 调用前后统计 `resources`/`bare_metal_details`/`virtual_machine_details`/`audit_logs` 行数 | PASS：行数全部不变；无新增 `audit_logs`；两次 validate 响应深比较一致（键/顺序/计数）。FAIL：落库、写 Audit、两次结果漂移 |
| A4 预校验通过后确认→写入；写入时再次校验当前状态 | **V4**；**B12** | 真PG集成 | validate 通过与写入之间由外部并发/他端改变库状态（占用目标 hostname / 软删 Host） | PASS：写入端点重新校验最新状态并 422 `IMPORT_VALIDATION_FAILED`（未使用旧预校验结果），整批回滚。FAIL：写入使用陈旧结果、静默成功 |
| A5 正式写入任一行失败 → 整批回滚，无部分成功 | **V5** | 真PG集成 + 真PG约束 | 有效行与 1 个非法行混合；统计调用前后各表行数 | PASS：响应 422，`resources`/明细/`audit_logs` 行数与调用前一致；无任一有效行被提交。FAIL：部分行落库 |
| A6 回滚后无 Resource/明细残留，且无 Audit/Activity 残留 | **V6** | 真PG集成 + 真PG约束 | 同上；另查 Activity 视图/端点对应资源 | PASS：所有相关表零新增；失败资源在列表/详情/Activity 不可见。FAIL：残留任一对象或 Audit |
| A7 整批成功后每行创建 Resource(+BM/VM 明细) 各一条 CREATE Audit，可查 | **V7** | 真PG集成 | 有效 BM+VM 行；写入成功 | PASS：`created == total_rows`；每行 Resource 与其明细各 1 行；`audit_logs` 对应每资源 1 条 `CREATE`、operator 为请求会话用户；Activity 可见。FAIL：缺明细、Audit 条数/action/operator 错 |
| A8 文件内重复（归一化 cluster+hostname）→ 报错（涉及两行行号），该批不写入 | **V8** | 真PG集成 | 同批两行同 cluster、hostname 仅大小写/首尾空白差异 | PASS：validate/write 均报错；错误项含 `related_row` 指向另一行；整批不写入。FAIL：只报一行、无 related_row、部分写入 |
| A9 现存冲突（同 cluster+hostname 未删）→ 报错，不更新/不覆盖，无 UPDATE Audit | **V9** | 真PG集成 + 真PG约束 | 库中已存在未删 `cn001`；导入同 hostname 行 | PASS：报行错误；现存行字段/`updated_at`/`version` 不变；无 `UPDATE` Audit。FAIL：upsert、更新现存行 |
| A10 非法字段（枚举/整数/单位/长度/空白）→ 行错误含字段与原因 | **V10**；**B21–B27** | 真PG集成 | 覆盖 role/status 非法值、`cpu_cores=0`/负、超长字符串、hostname 内部空白、NaN 文本 | PASS：逐行 `field`/`reason` 与普通 API 校验一致；无绕过。FAIL：接受非法值、字段定位错 |
| A11 非法关系（VM Host 不存在/软删/非 BM/跨 Cluster）→ 行错误 | **V11**；**B17/B18** | 真PG集成 | 构造四类非法 Host 引用 | PASS：各返回 `field="host"` 行错误；整批不写。FAIL：任一非法关系通过 |
| A12 cluster 列不存在/软删 → 行错误；`INACTIVE` Cluster 允许导入 | **V12**；**B15/B16** | 真PG集成 | 不存在 code、软删 Cluster、INACTIVE Cluster、大小写不同 code | PASS：不存在/软删→`field="cluster"` 行错误；INACTIVE→可导入；code 大小写不敏感且 name 不作引用。FAIL：软删被视为存在、INACTIVE 被拒 |
| A13 软删 hostname 可在导入中重用（不视为冲突）；恢复冲突按 §21 | **V13** | 真PG集成 | 库含软删 `cn001`；导入同 hostname | PASS：导入成功新建一行；软删行仍软删；恢复该软删行按 §21 报冲突（`CONFLICT`）。FAIL：误判冲突拒绝、或恢复重复唯一 |
| A14 导入与普通 API 使用同一 Service Layer；不创建 API 会拒绝的对象、不得直写 | **V14**；**V-SL-1** | 真PG集成 + 静态 | 取普通 API 拒绝的组合集作为导入输入；源码检查导入模块无独立直写 SQL | PASS：导入对这些组合同样报错；`resource_import` 调用抽取的 Service Layer 核心（校验+persist+Audit staging），无直写 SQL/ORM 旁路。FAIL：导入接受 API 拒绝组合、存在旁路写路径 |
| A15 缺省：role 省略→OTHER、status 省略→UNKNOWN；可空省略→null；未知不存 0 | **V15**；**B25** | 真PG集成 | 省略 role/status/容量的行 | PASS：落库 `role=OTHER`、`status=UNKNOWN`、可空列 NULL（非 0、非空串）。FAIL：默认错、以 0 代替 null |
| A16 单位一致：`memory_mb`=MiB、`disk_gb`=GiB；模板显式标注 | **V16**；**V-FE-2** | 真PG集成 + 前端 | memory_mb=262144、disk_gb=100 的行 | PASS：逐字存储不换算；模板规范/逐列说明单位字段为 `MiB`/`GiB`。FAIL：按 MB/GB 转换、模板单位缺失 |
| A17 `gpu_count=0`/`disk_gb=0` 接受并存 0（明确无），与 null 区分；负值/零值按 §8/§9 拒绝 | **V17**；**B26** | 真PG集成 | `gpu_count=0`、`disk_gb=0`、`cpu_cores=0`、负值、空 | PASS：`gpu_count`/`disk_gb`=0 存 0 且 ≠NULL；`cpu_cores=0`/负值/`gpu_count` 负值被拒。FAIL：0 与 null 混淆、非法零值通过 |
| A18 VM Host 必须已存在且满足 §9；先导 BM 再导 VM；不在同批隐式创建 Host | **V18**；**B19** | 真PG集成 | 已存在 Host 的 VM 导入成功；缺失 Host 的 VM 导入失败；先导 BM 批、后导 VM 批 | PASS：已存在 Host→成功；无 Host/仅同批 BM→报错；确认后独立 BM 批再 VM 批成功。FAIL：同批隐式创建 Host、引用不存在 Host 成功 |
| A19 同批 BARE_METAL 行新建的 Host 不能被本批 VM 行引用 → 行错误 | **V19**；**B20** | 真PG集成 | 同文件先 BM 行 `cn100`、后 VM 行 `host=cn100` | PASS：VM 行 `field="host"` 报错（Host 仅批内新建）；整批回滚。FAIL：VM 引用到同批新建 Host 并成功 |
| A20 文件大小/行数超限 → 解析前拒绝并明确报错，无部分导入 | **V20**；**B13/B14** | 真PG集成 | 超过 `import_max_file_bytes`（默认 5,242,880）的字节数；超过 `import_max_rows`（默认 5000）的数据行 | PASS：均 413（`IMPORT_FILE_TOO_LARGE{limit_bytes}` / `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows}`）；无任何行落库。FAIL：超限被处理、部分导入 |
| A21 模板固定列：缺失必填列/未定义列报错；VM 含 Host 列；BM/VM 专属列错配报错 | **V21**；**B1–B5** | 真PG集成 | 缺列、多列、列序不符、BM 行填 VM 列、VM 行填 hardware 列、非 `.xlsx`/`.xls` | PASS：文件级 `IMPORT_INVALID_FILE{reason}`（`missing_columns`/`unknown_columns`/`column_order`/`unsupported_format`）或行级互斥错误，与 F004 §2.4/§2.5 口径一致。FAIL：静默忽略列、接受错配 |
| A22 预校验与写入均执行 §23 权限检查：VIEWER→403；EDITOR/ADMIN→允许；未认证→401 | **V22**；**B28/B29** | 真PG集成 + 前端 | 无 Cookie、VIEWER、EDITOR、ADMIN 分别调用 validate/write/templates | PASS：未认证 401；VIEWER 写端点 403 `FORBIDDEN{reason:"permission"}`；EDITOR/ADMIN 允许；templates 对 VIEWER 允许（READ）；前端隐藏不替代（直连仍拦）。FAIL：任一角色越权、401/403 顺序错 |
| A23 一期同步处理；同一文件重复确认在成功后再导入因冲突报错、不产生新行 | **V23**；**V-SYNC-1** | 真PG集成 + 静态 | 成功导入后再次对同一文件写入；源码/路由检查无异步任务 | PASS：二次写入 422（现存冲突），不产生新行、不产生重复 Audit；无 Celery/队列/任务表引入。FAIL：异步化、二次导入新增行 |
| A24 导入不创建/修改 Cluster；cluster 仅作引用且须已存在 | **V24** | 真PG集成 + 真PG约束 | 导入前后统计 `clusters`；导入引用不存在 cluster | PASS：`clusters` 行数/内容不变；不存在 cluster 行报错。FAIL：隐式创建/修改 Cluster |
| A25 固定模板提供逐列说明（单位/枚举/必填性）供下载/查看 | **V25**；**V-FE-2/V-FE-3** | 真PG集成 + 前端 | `GET /imports/resources/templates` | PASS：返回两套模板列规范（name/required/type/unit/enum/description/example）；列集合与顺序与 architecture §5 一致；前端可查看/下载。FAIL：缺说明/单位/枚举、列集不一致 |
| A26 未支持对象（Interface/IPAddress/Network/Cluster/Service 等）不在本 Feature 导入；上传其数据不产生对象 | **V26** | 真PG集成 + 静态 | 上传含 `interface`/`ip_address`/`network` 列的文件；路由清单检查 | PASS：`unknown_columns` 报错或不被识别，无对应对象类型创建；无导入这些对象的端点。FAIL：创建非 Resource 对象 |

**补充验证项（不直接对应单一 A，用于覆盖契约与一致性）**

| 编号 | 项目 | 测试类型 | 判据 |
| --- | --- | --- | --- |
| **V27** | 行号约定（1-based 文件行号、表头第 1 行、数据自第 2 行；CSV 逻辑记录号正确处理引号内换行；xlsx 工作表行号） | 真PG集成 | 含引号内换行的 CSV 错误行号 = 逻辑记录号；`field` 取模板列名（OPEN-6 定稿后固定） |
| **V28** | 预校验/写入响应结构完整性（`format`/`total_rows`/`importable_rows`/`error_count`/`errors[]`/`errors_truncated`；201 `{created,total_rows}`） | 真PG集成 | 字段齐全、类型正确；`errors_truncated` 在上限内为 false，超预览上限为 true 且 `errors` 有界 |
| **V29** | `format` 缺失/非法 → 422 `VALIDATION_ERROR{fields:[{field:"format"}]}`；未知路径/方法 404/405 | 真PG集成 | 缺 `format`/传 `xls`/非法值均 422 field=format（注意与 `unsupported_format` 的区分，OPEN-4） |
| **V30** | 空文件/仅表头 → `IMPORT_INVALID_FILE{reason:"empty_file"}`；损坏 xlsx → `unreadable` | 真PG集成 | 各返回对应 reason，无 500 |
| **V31** | 请求不落盘、服务端不保存临时文件；写入端点接收同一文件完整重校验 | 真PG集成 + 静态 | 无临时文件残留；写入不需先上传缓存（无 token 依赖，OPEN-3 定稿后固定） |
| **V32** | 错误列表截断：> `import_error_preview_limit`（默认 1000）行错误时 `errors_truncated=true` 且 `errors` 有界 | 真PG集成 | 截断标志与条数符合配置；`error_count` 为全量计数（OPEN-4/OPEN-7） |
| **V-SL-1** | 无直写旁路：`app/services/resource_import.py` 调用抽取核心，不出现导入专属 `INSERT/UPDATE` SQL 绕过 Service Layer | 静态 | 源码检查：导入路径复用 `resource.py` 核心；无直写路径 |
| **V-SYNC-1** | 同步处理：无异步任务/队列/后台作业；请求内完成 | 静态 | 无 Celery/队列/任务表；路由为同步处理 |
| **V-DB-1** | `uq_resources_cluster_id_hostname_key` 部分唯一仍存在且 `WHERE deleted_at IS NULL`；软删行不占唯一 | 真PG约束 | `pg_indexes`/`pg_indexdef` 断言；raw 插入软删同行成功 |
| **V-DB-2** | 预校验零写入（无 `resources`/明细/`audit_logs` 新行） | 真PG约束 | 调用 validate 前后行数一致 |
| **V-DB-3** | 并发兜底：重叠 hostname 并发写入由 DB 唯一约束拦截，失败方整批回滚 | 真PG并发 | 见 B33 |
| **V-FE-1** | 前端上传入口：格式选择（CSV/xlsx）、模板查看/下载、预校验结果表（行号/字段/原因/related_row）、确认写入、结果/整批失败提示；Loading/Empty/Error/未知态；错误不伪装为空列表 | 前端（真实 API 集成） | 消费真实 `/imports/resources/templates`、`…/validate`、`…/resources`；无 Mock 结果替代；无「部分成功」UI |
| **V-FE-2** | 逐列说明含单位（MiB/GiB）、枚举、必填性 | 前端 | 展示与模板规范一致 |
| **V-FE-3** | 模板下载文件列名/顺序与 architecture §5 冻结集合一致 | 前端 | 下载内容与 `GET …/templates` 一致 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| # | 场景 | 输入/前置 | 预期 |
| --- | --- | --- | --- |
| B1 | CSV 与 xlsx 一致 | 同逻辑数据两格式 | 预校验与写入结果逐项一致（A1/V1） |
| B2 | 表头缺失 | 首行非表头/空 | `IMPORT_INVALID_FILE{reason:"header_missing"}` |
| B3 | 缺列 | 缺 `hostname` 等必填列 | `missing_columns` 列出缺失列，不静默 |
| B4 | 未知列 | 多出模板未定义列 | `unknown_columns` 列出多余列 |
| B5 | 列序不符 | 列名齐全但顺序变化 | `column_order`（PROPOSED 严格；OPEN-5 定稿后固定） |
| B6 | 文件内重复两行 | 同 cluster 两行 hostname 仅大小写/空白差异 | 两行行号，`related_row` 指向对方（A8/V8） |
| B7 | 现存冲突不覆盖 | 库中未删 `cn001` 为目标 | 行错误；现存行 `updated_at`/`version` 不变、无 UPDATE Audit（A9/V9） |
| B8 | 归一化一致性 | `CN001`、` cn001 `、`cn001` 同批/跨批 | 视为同一 key；重复报错；用 `str.lower()` 反例不改变 ASCII 折叠语义（I-13） |
| B9 | 软删 hostname 重用 | 库含软删 `cn001` | 导入成功，软删行不受影响（A13/V13） |
| B10 | 整批回滚零残留 | 有效行 + 1 非法行 | Resource/BM/VM 明细/Audit/Activity 零新增（A5/A6） |
| B11 | 失败无 Activity | 同上，查 Activity 端点 | 无相应变更记录（A6） |
| B12 | 预校验后状态变化 | validate 通过 → 他端占用 hostname → write | write 再次校验报冲突并回滚（A4/V4/I-4） |
| B13 | 文件字节超上限 | > `import_max_file_bytes` | 413 `IMPORT_FILE_TOO_LARGE`，解析前拒绝，无落库（A20） |
| B14 | 行数超上限 | > `import_max_rows` 数据行 | 413 `IMPORT_ROW_LIMIT_EXCEEDED`，校验前拒绝（A20） |
| B15 | cluster 不存在 | code 未登记 | 行错误 `field="cluster"`（A12） |
| B16 | cluster 软删 / INACTIVE | 软删 cluster；INACTIVE cluster | 软删→行错误；INACTIVE→通过（A12/T29） |
| B17 | VM Host 不存在/软删 | host 指向不存在或软删 BM | 行错误 `field="host"`（A11） |
| B18 | VM Host 非 BM / 跨 Cluster | host 指向 VM 或他 cluster BM | 行错误（A11） |
| B19 | VM Host 批外已存在 | 无 Host 的同批；独立 BM 批后 VM 批 | 同批报错；独立批成功（A18） |
| B20 | 同批 BM 不可被本批 VM 引用 | 同文件 BM `cn100` + VM `host=cn100` | VM 行报错，整批回滚（A19/I-9） |
| B21 | 枚举错配 | `role=compute`、`status=idle` 小写；非法枚举 | 非规范值报错（DR-199）；`role`/`status` 缺省→OTHER/UNKNOWN（A10/A15） |
| B22 | 类型错配整数 | `cpu_cores=abc`/小数/负数/0 | 行错误含字段与原因；与 F004 一致（A10） |
| B23 | 字符串边界 | 超长（>255）、hostname 内部空白/控制字符、超 253 | 行错误；`manufacturer` 等 trim 后空→null（A10/A15） |
| B24 | BM/VM 专属列错配 | BM 行填 `host`/`vcpu`；VM 行填 `gpu_model` | 行/模板级方斥错误，与 F004 §2.4/§2.5 同口径（A21） |
| B25 | 单位与未知值 | `memory_mb`/`disk_gb` 值；空 vs 0 | MiB/GiB 不换算；空→NULL，0→0（A15/A16/A17） |
| B26 | 零值/负值 | `gpu_count=0`、`disk_gb=0`、负值、`cpu_cores=0` | 0 接受并存 0；负值/`cpu_cores=0` 拒绝（A17） |
| B27 | 空单元格语义 | 可选列空/纯空白；必填列空 | 可选空=省略/默认；必填空=行错误（DR-199/I-5） |
| B28 | 权限矩阵 | 无 Cookie/VIEWER/EDITOR/ADMIN × validate/write/templates | 401/403/允许 符合 §1.1（A22/T25） |
| B29 | 403 与 CSRF 区分 | 缺权限 vs 跨源 | `FORBIDDEN{reason:"permission"}` vs `{reason:"csrf"}`（F002 §2.1） |
| B30 | 未认证先于权限 | 无 Cookie + 无权限路径 | 401 先于 403（I-11） |
| B31 | `format` 非法 | 缺 `format`、`xls`、`pdf` | 422 `VALIDATION_ERROR` field=format / `unsupported_format`（OPEN-4） |
| B32 | 仅表头/空文件/损坏 xlsx | 空数据行、截断 xlsx | `IMPORT_INVALID_FILE{empty_file|unreadable}`（A20 之外） |
| B33 | 并发重叠 hostname | 两真实连接同时写入含同 `(cluster,hostname)` 的文件 | 仅一个成功；另一个整批回滚、无残留、无重复行（§27/DR-206） |

并发说明：F014 为**写入口**，并发证据必须经真实 PostgreSQL（`committed_engine` + 两独立连接 + 最终持久化断言），SQLite/Mock 不构成证据。预校验为只读不加锁（`lock=False`），并发正确性由唯一约束/FK 兜底（DR-206）。

---

## 3. 夹具 / 环境设计

**复用 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip。
- `pg_engine`：会话级重建 `public` schema + `alembic upgrade head`（F001–F013 全部迁移，F014 无新迁移）；会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染。
- `committed_engine`：真实提交用例（写入/回滚/并发证据），teardown TRUNCATE；**新开连接断言最终持久化**。
- `auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login` 与既有 `role_client_factory`（`test_bare_metal.py`）：提供 ADMIN/EDITOR/VIEWER 与未认证客户端。
- 既有 helper（`_cluster`/`_create`/`_resource`/`_hardware_row`/软删）直接复用构造 Cluster/BM/VM。

**F014 新增测试侧夹具/断言（Tester 落地于测试侧）**：
- `import_file_factory(format, headers, rows, *, bom=False, quoted_newlines=False)`：将行数据构造成 CSV（含 BOM/引号换行变体）或 `.xlsx`（`openpyxl` 写入内存 BytesIO），供两格式一致性（A1/B1）。
- `multipart(file_bytes, filename, fmt)`：构造 `multipart/form-data` 请求体，`file`+`format`。
- `bm_template_headers()` / `vm_template_headers()`：与 architecture §5 冻结列名/顺序一致（TD-2 按 CONTRACT 固定）。
- `validate(client, file_bytes, fmt)` / `write(client, file_bytes, fmt)`：调用两写端点。
- `table_counts(session)`：一次性统计 `resources`/`bare_metal_details`/`virtual_machine_details`/`audit_logs`/`clusters`，用于 A3/A5/A6/A24 的零残留断言。
- `assert_row_error(resp, row, field, related_row=None)`：断言 `errors` 中该行/字段/原因命中。
- `assert_template_columns(payload, resource_type, expected)`：列集合/顺序/必填/单位断言（A21/A25）。
- `concurrent_write_pair(committed_engine, ...)`：两连接并发写入重叠 hostname（B33）。

**环境**：Docker / Compose 可用（F001–F013 TE 已证）；真实 PG 经 Compose `db`（`postgres:16`）。F014 无 Migration（database=false），既有约束/索引由既有迁移提供。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V28、V31、B1–B32、V-FE-* | 真实 PG + 后端/前端；**依赖 `/imports/resources/validate|resources|templates` 实现落地** | Compose `db` 可满足；实现未落地→BLOCKED | **不得**用 SQLite/Mock 替代约束/回滚证据 |
| V-DB-1（既有唯一约束）、V-DB-2（零写入）、V-DB-3/B33（并发） | 真实 PG（`committed_engine` + 两连接） | 环境可执行；依赖实现落地 | 无 PG→BLOCKED |
| V20（上限 413） | 真实 PG + 可配置 `import_max_file_bytes`/`import_max_rows` | 可执行；**数值待 D03 定稿** | 数值未定→判据按默认；定稿后 TD-2 固定 |
| V-FE-1…V-FE-3 | Node + 构建 + 真实 API | 可执行 | 真实浏览器 DOM 非必要；镜像/端口问题记 BLOCKED |
| 新依赖 `openpyxl`/`python-multipart` | 运行时依赖已加入 `pyproject.toml` | 见 §5 | 未加入→BLOCKED |
| §31/§32 完整跨功能回归 | F016 交付 | **不可执行** | 标 `NOT TESTED / 归 F016` |
| Migration/备份 | database=false（architecture §9） | **NOT_REQUIRED** | Database Gate 以 `NOT_REQUIRED` 复核 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1 两格式一致 | **可验证（API）** | V1/B1；CSV 内存 vs xlsx 内存 |
| A2 错误聚合 | **可验证（API）** | V2/V28；多错误行 |
| A3 预校验只读幂等 | **可验证（API + DB）** | V3/V-DB-2；行数快照 + 两次响应对比 |
| A4 写入再次校验 | **可验证（API + DB）** | V4/B12；外部状态变更窗口 |
| A5/A6 原子回滚零残留 | **可验证（真 PG + 真实提交）** | V5/V6/B10/B11；`committed_engine` + 新连接断言 |
| A7 Audit/Activity | **可验证（API + DB）** | V7；`audit_logs` + Activity |
| A8 文件内重复 | **可验证（API）** | V8/B6；`related_row` |
| A9/A13/A14 冲突/软删/同 Service Layer | **可验证（API + DB + 静态）** | V9/V13/V14/V-SL-1；现存行不变 + 源码检查 |
| A10/A15/A16/A17 字段/默认/单位/零值 | **可验证（API + DB）** | V10/V15/V16/V17；raw 查询落库值 |
| A11/A18/A19 VM Host 四条件与批外 | **可验证（API + DB）** | V11/V18/V19；四类非法 + 同批 BM |
| A12/A24 cluster 引用 | **可验证（API + DB）** | V12/V24；`clusters` 行数不变 |
| A20 上限 | **可验证（API）** | V20/B13/B14；413 与 details；**数值待 D03** |
| A21/A25/A26 模板/说明/排除 | **可验证（API + 前端 + 静态）** | V21/V25/V26/V-FE-2/3；列集合断言 |
| A22 权限 | **可验证（API + 前端 + 静态）** | V22/B28–B30 |
| A23 同步/重复确认 | **可验证（API + 静态）** | V23/V-SYNC-1 |
| V27 行号约定 | **可验证（API）** | 依赖 OPEN-6 定稿 |
| V29 `format` 与文件级错误 | **可验证（API）** | 依赖 OPEN-4 定稿 |
| V-FE-* 前端 | **可验证（前端 + 真实 API）** | 构建 + 真实端点；**不得用 Mock 替代真实 API** |

口径明确记录：**A20 的上限数值在 D03 签核前不得以具体数字判 PASS**（先用默认值建立判据，TD-2 固定）；**A14/V14 只验证「导入复用同一 Service Layer 结果」，不重验 F003–F006 单条创建实现**；**§31 T11/T25/T27/T28/T37/T38 的 F014 部分在本 Feature 闭合，完整 §31/§32 归 F016**。

---

## 5. 新依赖的可测性核对

| 依赖 | 用途 | 版本/许可（architecture DR-207） | 可测性核对 | 结论 |
| --- | --- | --- | --- | --- |
| `openpyxl` | 读取 `.xlsx`（`read_only`、`data_only`，不执行公式/宏） | `>=3.1,<3.2`；MIT | 纯 Python、无外部服务；测试侧可用同一库构造 `.xlsx` 字节（内存 BytesIO）以生成夹具，无需真实 Office 文件；可用损坏/`.xls` 夹具验证 `unsupported_format`/`unreadable` | **可测**；列入 `backend/pyproject.toml` 运行依赖（CONTRACT 签核项） |
| `python-multipart` | FastAPI `File`/`Form` multipart 解析 | `>=0.0.9,<0.1`；Apache-2.0 | 测试经 `TestClient` 直接发送 multipart（httpx 支撑），依赖存在即可解析；缺失时端点不可用→导入测试 BLOCKED | **可测**；CONTRACT 签核项 |

两者均遵守 §29（未引入禁项）。若 CONTRACT 否决其一，须改用等价方案并复核本文件对应用例；**未加入依赖前 V1/V27/V30 等 xlsx 用例 BLOCKED**。

---

## 6. 错误码登记与 D03 上限性能证据（OPEN 清单输入）

**错误码登记核对（DR-197）**：F014 新增 4 码，**当前 `docs/api/F002.md` §1.2 共享注册表未登记**，须由 Architect 在 CONTRACT 落地后方可 READY。

| HTTP | code | 触发 | details | F002 §1.2 登记 |
| --- | --- | --- | --- | --- |
| 413 | `IMPORT_FILE_TOO_LARGE` | 文件字节数 > 上限（解析前） | `{"limit_bytes": int}` | **待登记** |
| 413 | `IMPORT_ROW_LIMIT_EXCEEDED` | 数据行数 > 上限（解析后、校验前） | `{"limit_rows": int}` | **待登记** |
| 422 | `IMPORT_INVALID_FILE` | 不可解码/损坏/非 xlsx/空/表头或列不符 | `{"reason":str,"missing_columns"?,"unknown_columns"?}` | **待登记** |
| 422 | `IMPORT_VALIDATION_FAILED` | 写入存在行错误（整批回滚） | `{total_rows,importable_rows,error_count,errors,errors_truncated}` | **待登记** |

**D03 上限/性能证据待办（I-4）**：`import_max_file_bytes`（默认 5,242,880）、`import_max_rows`（默认 5000）、`import_error_preview_limit`（默认 1000）为 PROPOSED 默认值，须以**真实 PostgreSQL 性能验证**为依据在 D03 定稿。TEST 阶段需产出证据（Owner：Architect/Backend/Tester）：①在真实 PG 下导入接近上限行数的耗时/内存基线；②上限处拒绝的响应时延与无部分导入；③预览截断行为。**未取得性能证据前，A20 的数值断言仅按默认值建立，不判 D03 PASS。**

---

## 7. OPEN 复核项（TD-1 提出，待 CONTRACT / D03 定稿后由 TD-2 关闭）

| OPEN | 待复核假设 | 影响验证项 | Owner |
| --- | --- | --- | --- |
| OPEN-1 | `docs/api/F014.md` 草案 v0 未签核（状态 BLOCKED）；端点路径/方法、响应 details 形态可能调整 | 全部 | 协调器 / Architect |
| OPEN-2 | I-1 模板最终列集：BM 14 列 / VM 10 列、是否两套、`resource_type` 是否保留、是否含 `serial_number`/`cpu_sockets`/VM 容量列；`metadata`/`description` 不导入（DR-200） | V21/V25、V-FE-2/3、B3/B5/B24 | Architect / Product 核对 |
| OPEN-3 | I-3 两步交互接口形态：是否用确认令牌 / 客户端再次上传；架构默认「两端点、服务端不留临时文件、写入整重校验」 | V4/V31、B12 | Architect |
| OPEN-4 | I-4 上限数值与超限错误码（413）、文件级错误码 `reason` 枚举、`format` 非法归 `VALIDATION_ERROR` vs `unsupported_format`；`errors_truncated` 语义 | V20/V29/V30/V32、B13/B14/B31/B32 | Architect / Backend / Tester（D03） |
| OPEN-5 | I-5 空单元格语义（空=省略/默认；无显式 null）、枚举大写规范值 | V15/V17、B21/B27 | Architect / Product 核对 |
| OPEN-6 | I-6 错误响应形态与行号约定（1-based 文件行号、表头第 1 行、CSV 逻辑记录号、`field` 取模板列名）；表头是否严格要求列序 | V2/V21/V27/V28、B5 | Architect |
| OPEN-7 | 请求/表单字段细节（`format` 大小写不敏感；`file`/`format` 校验顺序）与预览截断阈值 | V28/V29/V32 | Architect |
| OPEN-8 | I-2 Host 引用列取值形式（hostname 或 UUID；不接受 cluster code/name） | V11/V18/V19、B17/B18 | Architect / Backend |
| OPEN-9 | 新依赖 `openpyxl`/`python-multipart` CONTRACT 签核；4 个错误码登记 `docs/api/F002.md` §1.2 | 全部 xlsx/错误码用例 | Architect（CONTRACT） |
| OPEN-10 | layers 字段（`database=false`、`backend/frontend=true`、`api_required=true`）由 Database Gate `NOT_REQUIRED` 复核 | V-DB-*、B33 | Database / 协调器 |

TD-1 结论：**`TEST DESIGN READY`** —— A1–A26 已映射到可观察判据（V1–V32、V-SL-1/V-SYNC-1/V-DB-1…3、V-FE-1…3），边界/并发/环境场景（CSV/xlsx 一致、错误聚合含 related_row、预校验只读幂等无 Audit、写入再次校验、整批回滚零残留含 Resource/BM/VM 明细/Audit/Activity、文件内重复两行行号、现存冲突不覆盖不 UPDATE、软删 hostname 重用、VM Host 四条件与批外已存在/同批 BM 不可引用、cluster 不存在/软删/INACTIVE、409/413 上限、权限矩阵 401/403/EDITOR/ADMIN、模板列集/列序/未知列/类型错配、单位/未知值/缺省、并发重叠 hostname）可执行；夹具与可验证性已与 architecture §4–§10 及 Contract v0 建立对应；真实 PostgreSQL + `committed_engine` + 并发双连接口径固定；新依赖可测性已核对。**Contract 为草案 BLOCKED、4 错误码未登记、D03 上限性能未定稿，§7 OPEN-1–10 未经逐项核对；READY 不等于测试通过，不批准实现或合并。** 定稿后由 TD-2 关闭 §7 并固定执行判据。

> **TD-1 Git 记录**（只读，未改变 Git 状态）：
> ```text
> GIT: git rev-parse --short HEAD
> GIT: git branch --show-current
> GIT: git status --short
> ```

---

## Test Design（TD-2，定稿复核）

- **版本**：TD-2
- **日期**：2026-10-14
- **角色**：Tester（TEST_DESIGN 定稿复核）
- **结论**：`TEST DESIGN READY (TD-2)` —— TD-1 §7 OPEN-1…OPEN-10 已按最终 Contract / DB / D01 逐项关闭并固定执行判据；TD-1 的端点、模板列、错误码/details、上限、行号假设全部与定稿一致，无判据返工。
- **复核基线**：`docs/api/F014.md` v1（READY，2026-10-13，D03 §10 签核、D01 §12 关闭）；`docs/database/f014-import.md` v1（NOT_REQUIRED）；`docs/api/F002.md` §1.2 已登记 4 码、§3 `IMPORT` 权限；`docs/architecture/d01-conventions.md` v11；实现报告 `docs/features/F014/implementation.md`；HEAD `51a4645`。

### TD-2 §7 OPEN 关闭表

| OPEN | TD-1 待复核假设 | 定稿裁定（TD-2 核对） | 判据固定 | 状态 |
| --- | --- | --- | --- | --- |
| OPEN-1 | `F014.md` 草案 v0 BLOCKED；端点/details 可能调整 | `docs/api/F014.md` v1 READY；三端点路径/方法不变；details 形态与 TD-1 假设一致 | V1–V32 按 v1 执行 | **CLOSED** |
| OPEN-2 | 模板列集 BM/VM、`resource_type` 是否保留、`metadata`/`description` | 冻结 BM 14 列 / VM 10 列（`resource_type` 保留为固定值列，含 `serial_number`/`cpu_sockets`/VM 容量列）；`metadata`/`description` 不导入（默认 `{}`/null） | A21/A25、V-FE-2/3、B3/B5/B24 | **CLOSED** |
| OPEN-3 | 两步交互是否用令牌 | 无令牌：validate + 写入两端点，写入接收同一文件完整重校验，服务端不落盘 | V4/V31、B12 | **CLOSED** |
| OPEN-4 | 上限数值、超限码、`reason` 枚举、`format` 归属、截断语义 | 5,242,880 B / 5000 行 / 预览 1000；超限 413 `IMPORT_FILE_TOO_LARGE`/`IMPORT_ROW_LIMIT_EXCEEDED`；`reason` 7 值；`format` 非法→422 `VALIDATION_ERROR{field:"format"}`；`errors_truncated` 与全量 `error_count` | V20/V29/V30/V32、B13/B14/B31/B32 | **CLOSED** |
| OPEN-5 | 空单元格语义、枚举大小写 | 空=省略（默认生效；非必填→null），必填空=行错误；枚举取大写规范值，非规范报错 | V15/V17、B21/B27 | **CLOSED** |
| OPEN-6 | 错误形态与行号约定、`field` 取值 | 合法解析即使有行错误也 200 + `errors`；文件级致命 4xx 无 `errors`；行号 1-based 文件行号（表头第 1 行、数据自第 2 行），CSV 逻辑记录号，`.xlsx` 工作表行号；`field`=模板列名；`related_row` 可空 | V2/V21/V27/V28、B5 | **CLOSED** |
| OPEN-7 | 请求/表单细节与截断阈值 | `format` 大小写不敏感；校验顺序 401→403→format(422)→size(413)→parse(422)→rows(413)→header(422)→逐行；预览阈值 1000 | V28/V29/V32 | **CLOSED** |
| OPEN-8 | VM Host 引用列取值 | `host`=同 cluster 内已存在、未软删 BARE_METAL 的 hostname **或** UUID；不接受 cluster code/name；批外已存在 | V11/V18/V19、B17/B18 | **CLOSED** |
| OPEN-9 | 新依赖签核、4 码登记 | `python-multipart>=0.0.9,<0.1`、`openpyxl>=3.1,<3.2` 已入 `backend/pyproject.toml`；4 码已登记 `docs/api/F002.md` §1.2；`IMPORT` 复用 §3（未新增 capability） | 全部 xlsx/错误码用例 | **CLOSED** |
| OPEN-10 | layers/database=false 复核 | `docs/database/f014-import.md` v1 `NOT_REQUIRED`（无新表/列/索引/触发器/迁移）；导入复用既有部分唯一/FK/CHECK/触发器 | V-DB-F014-*、B33 | **CLOSED** |

### TD-2 定稿判据（并入执行）

1. **模板与列序**：BM `[cluster,hostname,resource_type,role,status,manufacturer,model,serial_number,cpu_model,cpu_sockets,cpu_cores,memory_mb,gpu_model,gpu_count]`（14）；VM `[cluster,hostname,resource_type,role,status,host,vcpu,memory_mb,disk_gb,hypervisor]`（10）；表头列名+顺序严格一致，缺列/多列/列序不符→422 `IMPORT_INVALID_FILE`。
2. **Host 引用**：hostname 或 UUID，解析为 `host_resource_id`；四条件（存在、未软删、BARE_METAL、同 cluster）+ 批外已存在。
3. **两端点无令牌**：`POST …/validate`（只读）与 `POST …/resources`（单事务）；写入重传同一文件、无服务端临时文件。
4. **上限**：5,242,880 B（解析前 413）/ 5000 行（解析后校验前 413）/ 预览 1000；超限无部分导入。
5. **空/枚举**：空=省略，非必填→null；`resource_type`/`role`/`status` 大写规范值；`gpu_count`/`disk_gb`=0 表「明确无」。
6. **行号**：1-based 文件行号，表头第 1 行；CSV 逻辑记录号；`related_row` 指向另一重复行。
7. **`metadata`/`description` 不导入**。
8. **`IMPORT` 复用 F002 §3**：EDITOR/ADMIN 允许，VIEWER 403，未认证 401。

**TD-2 结论**：`TEST DESIGN READY`。TD-1 全部判据经最终 Contract 校对一致，无 OPEN 遗留，进入 TE-1 独立执行。

---

## Test Execution（TE-1）

- **版本**：TE-1
- **日期**：2026-10-14
- **角色**：Tester（TEST 模式，独立执行）
- **被测版本**：HEAD `51a4645`（`feature/F014-import`）；工作区仅新增 Tester 测试文件（`backend/tests/integration/test_import_performance.py`、`test_import_tester_acceptance.py`），无业务/产品/设计改动。
- **执行基线**：
  - Contract `docs/api/F014.md` v1（READY）；DB `docs/database/f014-import.md` v1（NOT_REQUIRED）；D01 v11（已关闭）；实现报告 `docs/features/F014/implementation.md`。
  - 后端全量：**528 passed, 1 skipped**（skip=连接角色 superuser，环境性 DB-D11）。F014 开发者用例 32/32；Tester 追加 13（性能 4 + 独立验收 9）；回归 `resource/bare_metal/virtual_machine` 等全绿。
  - 前端：`typecheck` 0、`build` 成功（82 modules）、`smoke:client` **241 passed / 0 failed**。
  - 真实 HTTP（uvicorn 经 socket + 真实 PG）：**13/13** 通过。
- **独立性声明**：本报告结果由 Tester 在独立数据库（`csm_f014_test`，运行后 DROP）与独立命令下重新执行得到，未复制开发者输出。对开发者既有用例做独立复跑，并新增独立验收/性能/约束用例补足缺口；对未实际执行项明确标注，未把设计推演当作 PASS。

### 环境

| 项 | 值 |
| --- | --- |
| 分支 / HEAD | `feature/F014-import` / `51a4645` |
| 数据库 | PostgreSQL 16，容器 `f002test-db`，网络 `f002test-net` |
| 独立验证库 | `csm_f014_test`（主）、`csm_f014_http`（真实 HTTP）；用后已 DROP |
| 后端镜像 | `csm-f007-test`（容器内安装 `python-multipart`、`openpyxl`，未 `docker build`） |
| 前端 | Node v22.23.2 / npm 12.0.2 |
| 生产/未知库 | 未使用；DB-D10 护栏（库名含 `test` 且 ≠ `DATABASE_URL`）生效 |
| Compose / Nginx | 未使用（单容器 + 网络）；浏览器 E2E 无 harness（见未验证项） |

### 命令与输出（摘要）

```text
# 后端全量（真实 PG，独立库）
docker run --rm --network f002test-net -v "$PWD/backend:/app" \
  -e TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f002test-db:5432/csm_f014_test \
  -w /app csm-f007-test bash -c "pip install -q 'python-multipart>=0.0.9,<0.1' 'openpyxl>=3.1,<3.2' && python -m pytest tests -q"
=> 528 passed, 1 skipped in 332.27s

# F014 开发者用例
tests/integration/test_imports.py + test_import_constraints.py -v  => 32 passed

# Tester 独立用例
tests/integration/test_import_tester_acceptance.py -q              =>  9 passed
tests/integration/test_import_performance.py -v -s                =>  4 passed

# 真实 HTTP（uvicorn app.main:app + 真实 PG csm_f014_http）
=> HTTP integration: 13/13 passed

# 前端
cd frontend && npm run typecheck   => exit 0
npm run build                      => built in 5.95s (82 modules)
npm run smoke:client               => 241 passed, 0 failed

# 项目状态一致性（只读）
python3 scripts/validate_project_state.py --feature F014
=> PROJECT STATE VALID
```

### A1–A26 验收映射结果

| 验收 | 结果 | 主要证据（独立复跑） |
| --- | --- | --- |
| A1 CSV/xlsx 行为一致 | **PASS** | `test_csv_and_xlsx_behaviour_identical`（BM 预校验深比较）、Tester `test_csv_xlsx_vm_validate_identical`（VM）、真实 HTTP BM+VM |
| A2 错误聚合（行/字段/原因） | **PASS** | `test_validate_aggregates_all_errors_not_fail_fast`（3 错行全部返回） |
| A3 预校验只读幂等无 Audit | **PASS** | `test_validate_read_only_and_idempotent`（行数快照 + 两次响应相等）、`test_prevalidate_writes_nothing` |
| A4 写入再次校验 | **PASS** | `test_write_revalidates_after_external_change`（预校验后占用 hostname → 422 回滚） |
| A5 整批回滚无部分成功 | **PASS** | `test_rollback_zero_residue_including_audit`（1 非法行 → 422，全表零新增） |
| A6 回滚无 Resource/明细/Audit/Activity | **PASS** | 同上 + Tester `test_activity_after_success_and_absent_after_rollback`（失败批资源列表不可见） |
| A7 每行 Resource+明细+CREATE Audit | **PASS** | `test_bm_create_defaults_units_and_audit`、`test_vm_create_with_host_detail_and_audit`、Tester Activity 查询 |
| A8 文件内重复两行号 | **PASS** | `test_file_internal_duplicate_reports_related_row`（`related_row=2`） |
| A9 现存冲突不覆盖不 UPDATE | **PASS** | `test_existing_conflict_not_overwritten`（role/description/version 不变，无 UPDATE Audit） |
| A10 非法字段字段级报错 | **PASS** | `test_field_validation_errors`、Tester `test_numeric_boundaries_map_to_template_columns` |
| A11 非法 VM Host 关系 | **PASS** | `test_vm_host_four_conditions`（不存在/跨 cluster/VM/软删 4 类） |
| A12 cluster 不存在/软删/INACTIVE | **PASS** | `test_cluster_not_found_soft_deleted_inactive` |
| A13 软删 hostname 重用 | **PASS** | `test_soft_deleted_hostname_reusable`、`test_hostname_unique_backstop_and_soft_delete_reuse` |
| A14 同一 Service Layer / 无旁路 | **PASS** | `test_no_direct_write_bypass_static`、Tester `test_import_service_has_no_direct_write_sql` |
| A15 缺省 role/status/可空 null | **PASS** | `test_bm_create_defaults_units_and_audit`（`OTHER`/`UNKNOWN`/`{}`） |
| A16 单位 MiB/GiB | **PASS** | memory_mb 逐字存 262144；模板 `unit` 断言；Tester VM disk_gb |
| A17 0 与 null 区分、负/零拒绝 | **PASS** | gpu_count=0/disk_gb=0 存 0；cpu_cores=0/负值被拒；Tester 负数/小数 |
| A18 Host 须已存在、批外 | **PASS** | `test_vm_host_must_be_out_of_batch`（先 BM 批后 VM 批成功）、`test_same_batch_bm_not_referencable`（缺 Host 行错误） |
| A19 同批 BM 不被本批 VM 引用 | **NOT TESTED（不可达）** | 冻结 Contract §6.3 要求单文件单一模板，一个批次（=一个文件）不可能同时含 BM 行与 VM 行，该场景在批准契约下结构性不可发生；DR-205「批外快照」由 `write_import` 先全行校验、后插入的次序保证。Tester 增加 `test_mixed_role_template_header_rejected` 证明混合表头被拒。**不构成覆盖失败**（详见未验证项/说明） |
| A20 上限拒绝无部分导入 | **PASS** | `test_file_size_and_row_limits`、Tester D03-2a/2b（413 + 零残留） |
| A21 固定模板/缺列/多列/列序/类型错配 | **PASS** | `test_header_errors`（missing/unknown/order/header_missing/BM 含 host/VM 含 gpu_model）、Tester 混合表头 |
| A22 权限 401/403/EDITOR/ADMIN | **PASS** | `test_permission_matrix`、`test_templates_spec_and_read_permission`、`test_csrf_reason_distinct` |
| A23 同步 + 重复确认冲突 | **PASS** | `test_reimport_after_success_conflicts`；路由为同步函数、无 Celery/队列（源码/路由核对） |
| A24 不改 Cluster | **PASS** | `test_import_does_not_touch_clusters` |
| A25 模板逐列说明可下载/查看 | **PASS** | `test_templates_spec_and_read_permission`、真实 HTTP `/templates`（BM14/VM10 + required/unit/enum） |
| A26 未支持对象不导入 | **PASS** | `test_unsupported_columns_rejected`、Tester 混合表头 → `IMPORT_INVALID_FILE` |

**补充验证项**：V1–V32 除 V-FE-* 外均由上表开发者 + Tester 用例覆盖；V14/V-SL-1、V-SYNC-1 由静态检查独立复跑；V27/V29/V30/V31/V32 由 BOM/引号换行行号、`format` 形状、空/损坏文件、无临时文件、截断用例覆盖。

### V-DB-F014-1…8（真实 PG）

| 项 | 结果 | 证据 |
| --- | --- | --- |
| V-DB-F014-1 文件内重复两行号、零写入 | **PASS** | `test_file_internal_duplicate_reports_related_row` |
| V-DB-F014-2 并发重叠仅一成功、整批回滚 | **PASS** | `test_concurrent_overlapping_import_one_succeeds`（committed_engine 双连接；失败方 `ImportValidationFailed`；最终 1 行/1 Audit） |
| V-DB-F014-3 软删 hostname 可重用（部分唯一谓词） | **PASS** | `test_hostname_unique_backstop_and_soft_delete_reuse`（raw SQL） |
| V-DB-F014-4 cluster 不存在/软删行错误、INACTIVE 通过、跨 cluster 同名允许 | **PASS** | `test_cluster_not_found_soft_deleted_inactive`、Tester `test_same_hostname_allowed_across_clusters` |
| V-DB-F014-5 0 与 null 可区分、0/负被 CHECK 拒 | **PASS** | `test_bm_create_defaults_units_and_audit`、Tester 负数/小数 |
| V-DB-F014-6 VM Host 触发器违约归因；批外快照应用保证 | **PASS**（批外属性见下 NOTE） | `test_vm_host_four_conditions`、Tester `test_import_adds_no_catalog_objects`（断言 `trg_*_host_valid` 存在）；DB 不表达「批次前已存在」时间语义（DB 设计 §3.1） |
| V-DB-F014-7 回滚零残留 + 成功每行 1 CREATE Audit | **PASS** | `test_rollback_zero_residue_including_audit`、性能 D03-1（5000 CREATE Audit） |
| V-DB-F014-8 运行期不增删 DB 对象 | **PASS** | Tester `test_import_adds_no_catalog_objects`（`pg_class`/`pg_trigger` 前后一致；依赖索引/触发器存在） |

### B1–B33 边界/并发结果

| # | 结果 | 证据 |
| --- | --- | --- |
| B1 CSV/xlsx 一致 | PASS | A1 证据 |
| B2 表头缺失 | PASS | `test_header_errors`（`b"\n"` → `header_missing`） |
| B3 缺列 | PASS | `missing_columns` |
| B4 未知列 | PASS | `unknown_columns` |
| B5 列序不符 | PASS | `column_order` |
| B6 文件内重复两行 | PASS | A8 证据 |
| B7 现存冲突不覆盖 | PASS | A9 证据 |
| B8 归一化一致性 | PASS | 重复用例 `cn001` vs ` CN001 `；软删用例 `CN001` |
| B9 软删重用 | PASS | A13 证据 |
| B10 整批回滚零残留 | PASS | A5 证据 |
| B11 失败无 Activity | PASS | Tester Activity 用例 |
| B12 预校验后状态变化 | PASS | A4 证据 |
| B13 文件字节超限 | PASS | `test_file_size_and_row_limits`、D03-2b |
| B14 行数超限 | PASS | 同上、D03-2a |
| B15 cluster 不存在 | PASS | A12 证据 |
| B16 cluster 软删/INACTIVE | PASS | A12 证据 |
| B17 Host 不存在/软删 | PASS | A11 证据 |
| B18 Host 非 BM/跨 cluster | PASS | A11 证据 |
| B19 Host 批外已存在 | PASS | A18 证据 |
| B20 同批 BM 不可被本批 VM 引用 | **NOT TESTED（不可达）** | 同 A19；单一模板/文件下不可构造 |
| B21 枚举错配 | PASS | `test_field_validation_errors`（`role=compute`/`status=idle`） |
| B22 类型错配整数 | PASS | `abc`/`0`/负/小数 |
| B23 字符串边界 | PASS | `manufacturer` 256 → 行错误；纯空白 → null |
| B24 BM/VM 专属列错配 | PASS | `test_header_errors`（BM+`host`、VM+`gpu_model` → `unknown_columns`） |
| B25 单位与未知值 | PASS | MiB/GiB、空→null、0→0 |
| B26 零值/负值 | PASS | gpu_count=0/disk_gb=0 接受；负值/`cpu_cores=0` 拒绝 |
| B27 空单元格语义 | PASS | `test_required_and_optional_empty_cells` |
| B28 权限矩阵 | PASS | A22 证据 |
| B29 403 与 CSRF 区分 | PASS | `test_csrf_reason_distinct`（`permission` vs `csrf`） |
| B30 未认证先于权限 | PASS | `test_permission_matrix`（无 Cookie → 401） |
| B31 `format` 非法 | PASS | 缺/`xls`/`pdf` → `VALIDATION_ERROR`；Tester 大小写不敏感 |
| B32 仅表头/空/损坏 xlsx | PASS | `test_format_and_file_level_errors`（`empty_file`/`unsupported_format`/`unreadable`） |
| B33 并发重叠 hostname | PASS | V-DB-F014-2 证据 |

### D03 真实 PG 性能证据（Contract §10 义务）

执行：`tests/integration/test_import_performance.py`（真实 PG，默认签核上限），输出如下（同一测试主机，耗时随负载有波动，取两次观测区间）：

| 项 | 观测 |
| --- | --- |
| **① 接近上限导入基线** | 5000 行 BM CSV，文件 495,138 B；预校验 **5.64 s**（Python 峰值内存 ≈8.0 MB）；整批写入 **43.3–47.8 s**（峰值内存 ≈7.8 MB）；成功创建 5000 Resource + 5000 bare_metal_details + 5000 条 CREATE Audit；`created=total_rows=5000` |
| **② 上限处拒绝时延 + 无部分导入** | 5001 行 → 413 `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows:5000}`，**≈0.008 s**，`resources`/明细/`audit_logs` 与调用前一致；5,242,881 B → 413 `IMPORT_FILE_TOO_LARGE{limit_bytes:5242880}`，**≈0.0001 s**，零残留 |
| **③ 预览截断行为** | 1100 个错误行 → `errors_truncated=true`、`error_count=1100`、`errors` 恰为 1000 条，**≈0.03 s**；只读路径零写入 |

**判读**：上限拒绝与截断均在毫秒级、无部分导入，符合 §10；内存有界（≈8 MB Python 侧，`read_only` xlsx/流式 CSV）。**NOTE（风险，非阻塞）**：5000 行同步写入约 43–48 s，属单次迁移量级但接近常见网关默认 60 s 请求超时。D03 未定义时延阈值，本项不判 FAIL；建议协调器/Architect 按 `change-control.md` 评估部署超时或是否需要调低 `import_max_rows`（若判定「不安全」）。

### 前端（V-FE-1…3）与真实 API 集成

| 项 | 结果 | 证据 |
| --- | --- | --- |
| V-FE-1 上传入口/预校验结果/确认写入/四态/无部分成功 | **PASS（机制级 + 真实 API）；浏览器 DOM E2E NOT TESTED** | `smoke:client` 241 passed（`describeImportError` 401/403/413/422/500、无重试、不伪装空结果）；真实 HTTP 13/13（真实 multipart + 真实 PG 经 socket，非 Mock）；未在真实浏览器渲染（无 harness） |
| V-FE-2 逐列说明含单位/枚举/必填 | **PASS** | smoke 模板渲染辅助 + `GET /templates`；真实 HTTP 列集断言 |
| V-FE-3 模板下载列名/顺序与冻结集合一致 | **PASS** | smoke 表头 CSV 生成 + 真实 HTTP BM14/VM10 顺序 |

### 既有 no-GIN 抖动 NOTE（非 F014）

`test_search_constraints.py::test_explain_uses_gin_for_long_enough_query` 依赖查询计划器选择 `Bitmap Index Scan`（50000 填充行 + `ILIKE '%needle-xyz%'`），属计划器依赖、易随统计/负载抖动，**与 F014 无关**。本次独立复跑：单测 1 次 PASS、两次全量回归各 1 次 PASS，**未观测到抖动**；保留 NOTE 供后续，不阻塞 F014。

### Defects

- **无阻塞缺陷**。未发现需求违反、整批原子性破坏、回滚残留、权限越权、模板/错误码偏离 Contract 或 DB 设计偏差。
- **风险 NOTE（Owner：协调器/Architect）**：5000 行同步写入 ≈43–48 s（见 D03 判读），需确认部署超时或评估上限调整，走变更控制（非实现缺陷）。
- **说明（非缺陷，Owner：Architect/Product）**：A19/B20「同批 BM 被本批 VM 引用」在单模板/文件契约下不可达（见上）；DR-205 的「批外快照」由 `write_import` 校验先于插入的次序保证，DB 不兜底（DB 设计 §3.1 已记录）。

### 未验证项

| 项 | 原因 |
| --- | --- |
| 真实浏览器 DOM E2E（上传/表格渲染） | 无浏览器/E2E harness；已用机制级 smoke + 真实 HTTP 覆盖 API 契约，浏览器渲染未执行 |
| Compose / Nginx 端到端 | 未使用 Compose/Nginx；不影响契约限定的验证 |
| §31/§32 完整跨功能回归（T01–T41） | 归 F016 整体验收，不得以 F014 局部 PASS 拼接；本报告只闭合 F014 承载部分 |
| superuser 专用迁移用例 | DB-D11：连接角色为 superuser，`test_migrations.py::105` skip（环境性，非 F014） |
| A19/B20 同批 BM 引用 | 批准契约下不可达（见说明） |

### TE-1 结论

F014 全部可执行验收项（A1–A18、A20–A26；V-DB-F014-1…8；B1–B19、B21–B33）**PASS**；D03 性能证据已产出且判据满足；前端机制级与真实 API 集成 **PASS**（浏览器 DOM E2E 未执行）；唯一 NOT TESTED 项（A19/B20）在定稿契约下结构性不可达，不构成覆盖或实现缺口；无必须修复问题。

**结论：`READY FOR REVIEW`** —— 附两项交协调器的 NOTE（性能时延、A19 不可达说明），非阻塞。测试代码（`test_import_performance.py`、`test_import_tester_acceptance.py`）属 Review 范围。

> **TE-1 Git 记录**（全程只读，未执行 `git add`/commit/branch/merge/stash/reset，工作区未产生业务改动；仅新增上述两个 Tester 测试文件）：
> ```text
> GIT: git status
> GIT: git status --short
> GIT: git branch --show-current
> GIT: git rev-parse --short HEAD
> GIT: git log --oneline -5
> GIT: git log --oneline -1
> ```