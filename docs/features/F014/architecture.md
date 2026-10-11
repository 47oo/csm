# F014 CSV / Excel 批量导入 — ARCHITECTURE 阶段报告

- **Task**：F014（FEATURE，P1，M6 检索、导入与系统功能，deps [F003, F004, F005, F006]）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-09）
- **Basis**：requirements-v3.md revision 3（§4/§4.1、§5、§6、§7、§8、§9、§21、§22、§23、§24、§25、§27、§29、§31 T11/T25/T27/T28/T37/T38、§32、§35.2 Q02-A/Q10-A/Q10-B、§35.3 D01/D03）；`docs/features/F014/product.md`（A1–A26、I-1–I-17、OPEN I-1–I-9）；`docs/architecture/d01-conventions.md` v11（§3、§4、§5.3、§5.4、§5.5）；`docs/api/F004.md` v3（§1.2/§2.1/§2.4/§2.5/§6.2/§7/§8）；`docs/api/F003.md` v2；`docs/api/F002.md` v1（§1.1–§1.3、§2.1、§3）；实现 `backend/app/services/resource.py`、`app/schemas/resource.py`、`app/api/v1/resources.py`、`app/services/audit.py`、`app/services/normalization.py`、`app/services/cluster.py`、`app/core/errors.py`、`app/core/permissions.py`、`app/core/config.py`、`app/api/v1/router.py`；`.pi/skills/data-integrity/SKILL.md`；`docs/project/implementation-rules.md`；`docs/project/handoff.md`；plan_revision 4 F014（用户 2026-10-06 批准）。

## 1. 方案摘要

F014 在已交付 Resource 域（F003–F006）之上新增 CSV 与 `.xlsx` 的**资源新增批量导入**（§24），不新增资源实体、字段、状态或写入路径语义。导入是普通创建路径的批量入口：**两阶段**（预校验只读 → 用户确认 → 正式写入再次校验），**整批单事务原子**（全成或全回滚，回滚不留 Resource / 明细 / Audit / Activity），逐行**复用 F004 Service Layer**（禁止旁路直写）。仅新增两个写/读端点（外加模板规范端点，满足 A25），挂同一 `api_v1_router`。

### 1.1 两阶段流程（§24-1、§24-2、T27）
1. **预校验**（`POST /api/v1/imports/resources/validate`）：权限 `IMPORT`；解析 CSV/`.xlsx`，逐行依 §4.1/§5/§6/§7/§8/§9 与 F004 契约校验（同一 Service Layer 只读路径）；**聚合返回全部行错误**（`row`/`field`/`reason`，不 fail-fast）；**不写任何业务数据、不写 Audit、不改状态**，可重复调用结果一致（I-3）。
2. **确认**：用户查看错误行后决定是否写入；预校验存在错误行时整批不可能成功，前端不应进入写入。
3. **正式写入**（`POST /api/v1/imports/resources`）：权限同 `IMPORT`；在**同一事务内**重新解析并**再次校验全部行**（覆盖预校验后状态变化，I-4）；整批成功或整批回滚；成功每行产生一条 CREATE Audit（§22），失败整批无残留（I-8）。

### 1.2 边界
仅 `BARE_METAL` / `VIRTUAL_MACHINE` 新增；**不更新/覆盖**现存资源（I-6）；VM Host 必须**批外已存在**且满足 §9（I-9）；不导入 Cluster/Interface/IPAddress/Network/Service 等（A26/I-17）；一期同步处理、有文件/行数上限（I-10/I-15）；不引入异步任务（§29）；不新增字段（metadata/description 不导入，I-7）。

## 2. Design Requirements（DR-190–DR-212，接续 F013 DR-189）

> 状态语义：`CONFIRMED`+`DESIGN` = 由已确认规则必然产生的技术要求；`PROPOSED→CONTRACT` = 对 product I-1–I-9 或 D03 的已给可实施默认，由 Architect（D03 含 Backend/Tester）在 CONTRACT Gate 定稿，在此之前不视为永久规则。

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-190 | 两阶段端点：`POST /api/v1/imports/resources/validate`（只读）与 `POST /api/v1/imports/resources`（写入），挂同一 `api_v1_router`（新增 `app/api/v1/imports.py`）；独立 Contract `docs/api/F014.md`；不新增实体/字段 | CONFIRMED（§24/§25）+DESIGN（I-3） |
| DR-191 | 请求为 `multipart/form-data`：`file`（必填二进制）+ `format`（必填，∈{`csv`,`xlsx`}，大小写不敏感）；服务端不保存临时文件，写入端点接收同一文件并完整重校验；CSRF 沿用 F002 §2.1 | PROPOSED→CONTRACT（I-3） |
| DR-192 | 预校验响应 200：`{format,total_rows,importable_rows,error_count,errors:[{row,field,reason,related_row?}],errors_truncated}`；行错误聚合、不 fail-fast | CONFIRMED（§24-1/T27）+DESIGN（I-6） |
| DR-193 | 写入成功 201 `{created,total_rows}`；存在行错误时 422 `IMPORT_VALIDATION_FAILED`，`details` 携带同一聚合错误列表；文件级致命错误用 4xx（见 DR-195/DR-196） | PROPOSED→CONTRACT（I-6） |
| DR-194 | 行号约定：1-based 文件行号，**表头为第 1 行**，数据自第 2 行；CSV 用**逻辑记录号**（正确处理引号内换行，非物理行号），`.xlsx` 用工作表行号；`field` 取**模板列名** | PROPOSED→CONTRACT（I-6） |
| DR-195 | 文件级致命错误码 `IMPORT_INVALID_FILE`（422），`details.reason ∈ {unreadable, unsupported_format, header_missing, missing_columns, unknown_columns, column_order, empty_file}`，附 `missing_columns`/`unknown_columns` 等；与 F004 §2.4/§2.5 互斥/类型错配的行级报错保持同口径 | PROPOSED→CONTRACT（I-4/I-6/A21） |
| DR-196 | 上限：`MAX_IMPORT_FILE_BYTES`（默认 **5 MiB = 5,242,880**）在解析前拦截 → 413 `IMPORT_FILE_TOO_LARGE{limit_bytes}`；`MAX_IMPORT_ROWS`（默认 **5000**）在解析后、校验前拦截 → 413 `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows}`；超限**无部分导入** | PROPOSED→CONTRACT / D03（I-4/A20） |
| DR-197 | 新增错误码（`IMPORT_FILE_TOO_LARGE` 413、`IMPORT_ROW_LIMIT_EXCEEDED` 413、`IMPORT_INVALID_FILE` 422、`IMPORT_VALIDATION_FAILED` 422）须登记到 `docs/api/F002.md` §1.2 共享注册表；本 Feature 不改其它既有码 | CONFIRMED+DESIGN（跨 Contract 一致性） |
| DR-198 | **两套固定模板**（§2.1/§2.2）：BM 模板 14 列、VM 模板 10 列，列名/顺序/必填/类型/单位/枚举冻结；`resource_type` 作为固定值列保留（BM=`BARE_METAL`，VM=`VIRTUAL_MACHINE`） | PROPOSED→CONTRACT / D03（I-1） |
| DR-199 | 空单元格语义：可选列空/纯空白 = **省略**（默认值生效；非必填→null）；必填列空 = 行错误；枚举取**大写规范值**，非规范值报错；表格导入**无「显式 null」概念** | PROPOSED→CONTRACT / D03（I-5） |
| DR-200 | `metadata` / `description` **不导入**：导入对象取契约默认（`metadata={}`、`description=null`）；模板不含该列 | PROPOSED→CONTRACT / D03（I-7） |
| DR-201 | VM Host 引用列 `host` 取**同 cluster 内 Host 的 hostname**（可解析）或 UUID，服务端解析为 `host_resource_id`；不接受 cluster code/name 或任意字符串；须满足 §9 四条件且同 Cluster | PROPOSED→CONTRACT / D03（I-2） |
| DR-202 | **同一 Service Layer**：抽取 `app/services/resource.py` 的**非提交核心**（校验 + persist + Audit staging），导入逐行调用；`create_resource` 退化为「核心 + `db.commit()`」薄包装以保持既有 API 行为；**禁止直写 SQL/ORM 旁路** | CONFIRMED（§24）+DESIGN（I-7/A14） |
| DR-203 | 原子性：整批**单事务**；逐行 `SAVEPOINT`（`db.begin_nested()`）用于行级归因；任一错误最终 `db.rollback()` 全批回滚，成功一次 `db.commit()`；失败**零残留**（无 Resource/明细/Audit/Activity） | CONFIRMED（§24-2/§22）+DESIGN（I-1/I-8） |
| DR-204 | 写入在同一事务**再次解析 + 全部重校验**；文件内 `(cluster_id,hostname_key)` 重复报错并给出**两行行号**（`related_row`）；现存未删冲突报错、**不更新/不覆盖**、不产生 UPDATE Audit | CONFIRMED（§24-2/T11/T28）+DESIGN（A8/A9/I-4） |
| DR-205 | **Host 批外已存在**：VM Host 仅从进入写入事务前的库快照解析；本批（含更早行）新建的 BM **不可被本批 VM 引用**（行错误） | CONFIRMED（§24-3/§9）+DESIGN（I-9/A18/A19） |
| DR-206 | 并发兜底：hostname 唯一由 DB 部分唯一约束 `uq_resources_cluster_id_hostname_key` 兜底；VM Host 行写入路径 `SELECT … FOR UPDATE` 串行化（复用 F004 DR-71）；DB `IntegrityError` 在 SAVEPOINT 内归因后整批回滚；**预校验只读不加锁**（`lock=False`） | CONFIRMED（§27）+DESIGN |
| DR-207 | 解析库：CSV 用 Python 标准库 `csv`（UTF-8，兼容 BOM `utf-8-sig`，逗号分隔）；`.xlsx` 用 `openpyxl`（**新增依赖**，MIT，`>=3.1,<3.2`，`read_only`、不执行公式/宏，仅 `.xlsx`、不支持 `.xls`）；multipart 需 **`python-multipart`**（**新增依赖**，Apache-2.0，FastAPI File/Form 要求）。遵守 §29（未引入禁项）；两个新依赖为 **CONTRACT 签核项**，写入 `backend/pyproject.toml` 运行依赖 | PROPOSED→CONTRACT（§29） |
| DR-208 | 模板获取端点（A25）：`GET /api/v1/imports/resources/templates`（`READ` 全角色）返回两套模板列规范 JSON（列名/必填/类型/单位/枚举/说明/示例），供前端查看与生成下载；只读、不写 Audit | PROPOSED→CONTRACT（A25/§24） |
| DR-209 | 权限：预校验与写入均 `require_permission(Permission.IMPORT)`（EDITOR/ADMIN）；VIEWER→403 `FORBIDDEN{reason:"permission"}`；未认证→401；模板端点 `READ`。前端隐藏不替代服务端校验 | CONFIRMED（§23/§24-4/T25）+DESIGN（I-11） |
| DR-210 | 计划字段：`layers.database=false`、`layers.backend=true`、`layers.frontend=true`、`api_required=true`（I-8；database 理由见 §9） | PROPOSED→CONTRACT（I-8） |
| DR-211 | **D01 最终关闭核对**（I-9）：导入字段口径与 D01 v11 §5.3（hostname）/§5.4（hardware）/§5.5（VM）逐项一致，无新增口径；`docs/api/F014.md` READY 时记录 D01 关闭 | CONFIRMED+DESIGN（I-9） |
| DR-212 | 上限/预览经 Settings 配置：`import_max_file_bytes`（默认 5 MiB）、`import_max_rows`（默认 5000）、`import_error_preview_limit`（默认 1000，`errors_truncated`）；默认值文档化，最终数值待真实 PG 性能验证定稿（D03） | PROPOSED→CONTRACT（I-4） |

## 3. Domain / Data Impact

| 对象/视图 | 关系 | 作用域 | 生命周期 | 依据及状态 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| 导入文件（派生输入，非实体） | 1..N 新增行 → Resource | 按行 cluster（可多 Cluster） | 请求内一次性处理；**不落库** | §24 CONFIRMED | DR-190–196/198–207 |
| Resource（新增） | 每行 1:1 创建 | 行内 cluster | CREATE；无 UPDATE/DELETE/RESTORE | §4/§4.1/§6/§7 | DR-202–206 |
| BareMetalDetail | 随 BM Resource 同事务创建 | Resource 的 Cluster | 随 Resource | §8/§21 | DR-198 |
| VirtualMachineDetail | 随 VM Resource 同事务创建；host 引用现存 BARE_METAL | 同 Cluster | 随 Resource | §9/§21 | DR-201/205 |
| Cluster（被引用） | 1:N | code 全局唯一 | 不被导入创建/修改/删除 | §5 | INACTIVE 允许；软删视为不存在 |
| Host Resource（被引用） | VM 行 N:1 → 现存 BARE_METAL | 同 Cluster | 不被导入创建/修改 | §9 | **批外已存在**（DR-205） |
| Audit / Activity | 成功后每行 1 条 CREATE；失败整批无 | Resource | 与创建同事务 | §22 | DR-203；回滚无残留 |
| 模板规范（派生视图，非实体） | 只读列字典 | 全局 | 无 | §24/A25 | DR-208 |
| 新增错误码 | 登记 F002 注册表 | API 级 | 无 | F002 §1.2 | DR-197 |

**数据完整性对应表**（引用 `.pi/skills/data-integrity/SKILL.md`）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §7 / D01 §5.3（v11） | 同 cluster hostname 唯一；导入 + API | `uq_resources_cluster_id_hostname_key` 部分唯一 `WHERE deleted_at IS NULL` | 归一化 `hostname_key` + 现存/批内重复检查（DR-204） | 并发由唯一约束兜底 → SAVEPOINT 归因后整批回滚 | 真 PG 文件内重复/现存冲突/软删复用 |
| §4.1/§6（revision 3） | cluster 引用必填有效 | FK `cluster_id` | `resolve_cluster`（存在且未软删；INACTIVE 允许） | 软删 Cluster（行仍在，FK 不破坏）该行报错 | 不存在/软删 → 行错误；INACTIVE → 通过 |
| §8/§9、D01 §3/§5.4/§5.5 | 单位与未知值 | 列 CHECK（`memory_mb`/`disk_gb` 等） | `validate_hardware` / `validate_virtual_machine_values` | 未知 null ≠ 0；`gpu_count`/`disk_gb`=0 表示明确无 | T38 边界、MiB/GiB、null vs 0 |
| §9（revision 3） | VM Host 正确性 | FK `host_resource_id`；Host 反向引用检查器 | `validate_virtual_machine`（存在/未软删/BARE_METAL/同 cluster） | Host 行 `FOR UPDATE` 串行化（DR-206） | 批外不存在/软删/非 BM/跨 cluster → 行错误；同批 BM 不可引用 |
| §24（revision 3） | 整批原子 | 单事务 + SAVEPOINT | 任一错误整批 `rollback()` | 失败无 Resource/明细/Audit 残留 | T27 真 PG 回滚断言 |
| §23/§24-4（revision 3） | 权限 | 无 | 两写端点均 `IMPORT` | 401 先于 403 | T25 权限矩阵 |
| §22（revision 3） | Audit 同事务 | `audit_logs` 同 Session | `audit.record` 逐行 staging | 回滚无 Audit | 回滚后 Activity 为空 |

## 4. 请求/响应与错误形态

### 4.1 预校验（`POST /api/v1/imports/resources/validate`）
- `multipart/form-data`：`file`（必填）、`format`（必填 `csv`/`xlsx`）。
- 权限 `IMPORT`；只读、幂等、无 Audit。
- 成功 200：

```json
{
  "format": "csv",
  "total_rows": 12,
  "importable_rows": 10,
  "error_count": 3,
  "errors": [
    {"row": 4, "field": "cluster",  "reason": "cluster does not exist or is not selectable", "related_row": null},
    {"row": 7, "field": "hostname", "reason": "duplicate hostname within file (also at row 2)", "related_row": 2},
    {"row": 7, "field": "host",     "reason": "host must be an existing, undeleted BARE_METAL resource in the same cluster", "related_row": null}
  ],
  "errors_truncated": false
}
```
- 文件级致命 → 4xx（§4.3），无 `errors` 列表。

### 4.2 写入（`POST /api/v1/imports/resources`）
- 请求同 §4.1；权限 `IMPORT`。
- 成功 201：`{"created": 10, "total_rows": 10}`（每行 CREATE Audit 同事务）。
- 存在行错误（校验或并发归因）→ 422 `IMPORT_VALIDATION_FAILED`：

```json
{"error": {"code": "IMPORT_VALIDATION_FAILED", "message": "Import validation failed",
  "details": {"total_rows": 12, "importable_rows": 10, "error_count": 3,
              "errors": [{"row": 4, "field": "cluster", "reason": "…", "related_row": null}],
              "errors_truncated": false}}}
```
- **整批回滚**，无部分成功（I-1/I-8）。

### 4.3 文件级错误

| 场景 | HTTP | code | details |
| --- | --- | --- | --- |
| 文件字节数 > `import_max_file_bytes`（解析前） | 413 | `IMPORT_FILE_TOO_LARGE` | `{"limit_bytes": 5242880}` |
| 数据行数 > `import_max_rows`（解析后、校验前） | 413 | `IMPORT_ROW_LIMIT_EXCEEDED` | `{"limit_rows": 5000}` |
| 不可解码/损坏/非 `.xlsx`/`.xls`/空数据行 | 422 | `IMPORT_INVALID_FILE` | `{"reason": "unreadable\|unsupported_format\|empty_file"}` |
| 表头缺失/缺列/多列/列序不符 | 422 | `IMPORT_INVALID_FILE` | `{"reason": "header_missing\|missing_columns\|unknown_columns\|column_order", "missing_columns": [...], "unknown_columns": [...]}` |
| `format` 缺失/非法 | 422 | `VALIDATION_ERROR` | `{"fields":[{"field":"format","message":"…"}]}` |
| 未认证 / 权限不足 / CSRF | 401 / 403 / 403 | `AUTH_REQUIRED` / `FORBIDDEN{reason:"permission"}` / `FORBIDDEN{reason:"csrf"}` | — |

> 列序裁定（PROPOSED→CONTRACT）：表头须与冻结模板**列名、顺序完全一致**；不一致 → `column_order`/`unknown_columns`/`missing_columns`，不静默忽略、不按名重排。

## 5. 固定模板（D03 签核）

两套模板；列名/顺序/必填/单位/枚举冻结。表头第 1 行，数据自第 2 行。

### 5.1 BM 模板（`resource_type=BARE_METAL`，14 列）

| # | 列名 | 必填 | 目标字段 | 类型/单位 | 允许值/说明 |
| --- | --- | --- | --- | --- | --- |
| 1 | `cluster` | 是 | resource.cluster | string | Cluster `code`（ASCII 大小写不敏感，§5.1）或 UUID；须存在且未软删；INACTIVE 允许 |
| 2 | `hostname` | 是 | resource.hostname | string ≤253 | §7/D01 §5.3：trim→非空→禁内部空白/控制字符→**仅 ASCII A-Z→a-z**；同 cluster 未删唯一 |
| 3 | `resource_type` | 是 | resource.resource_type | enum | 固定 `BARE_METAL`；其它值行错误 |
| 4 | `role` | 否 | resource.role | enum | `COMPUTE,LOGIN,MANAGEMENT,STORAGE,SERVICE,GPU,OTHER`；空→`OTHER` |
| 5 | `status` | 否 | resource.status | enum | `IDLE,ALLOC,DOWN,UNKNOWN`；空→`UNKNOWN` |
| 6 | `manufacturer` | 否 | hardware.manufacturer | string ≤255 | trim 后非空或空(=null) |
| 7 | `model` | 否 | hardware.model | string ≤255 | 同上 |
| 8 | `serial_number` | 否 | hardware.serial_number | string ≤255 | 同上；一期无全局唯一 |
| 9 | `cpu_model` | 否 | hardware.cpu_model | string ≤255 | 同上 |
| 10 | `cpu_sockets` | 否 | hardware.cpu_sockets | int | 正整数 1..2147483647 或空(=null) |
| 11 | `cpu_cores` | 否 | hardware.cpu_cores | int | 正整数 1..2147483647 或空(=null)；整机物理核心不含超线程 |
| 12 | `memory_mb` | 否 | hardware.memory_mb | int **MiB** | 正整数 1..2147483647 或空(=null) |
| 13 | `gpu_model` | 否 | hardware.gpu_model | string ≤255 | trim 后非空或空(=null) |
| 14 | `gpu_count` | 否 | hardware.gpu_count | int | 非负整数 0..2147483647 或空(=null)；**0=明确无 GPU** |

### 5.2 VM 模板（`resource_type=VIRTUAL_MACHINE`，10 列）

| # | 列名 | 必填 | 目标字段 | 类型/单位 | 允许值/说明 |
| --- | --- | --- | --- | --- | --- |
| 1 | `cluster` | 是 | resource.cluster | string | 同 §5.1 |
| 2 | `hostname` | 是 | resource.hostname | string ≤253 | 同 §5.1 |
| 3 | `resource_type` | 是 | resource.resource_type | enum | 固定 `VIRTUAL_MACHINE`；其它值行错误 |
| 4 | `role` | 否 | resource.role | enum | 同 §5.1；空→`OTHER` |
| 5 | `status` | 否 | resource.status | enum | 同 §5.1；空→`UNKNOWN` |
| 6 | `host` | 是 | virtual_machine.host_resource_id | string | 同 cluster 内**已存在、未软删、BARE_METAL** 的 Host 的 `hostname`（或 UUID）；**批外已存在** |
| 7 | `vcpu` | 否 | virtual_machine.vcpu | int | 正整数 1..2147483647 或空(=null) |
| 8 | `memory_mb` | 否 | virtual_machine.memory_mb | int **MiB** | 正整数 1..2147483647 或空(=null) |
| 9 | `disk_gb` | 否 | virtual_machine.disk_gb | int **GiB** | 非负整数 0..2147483647 或空(=null)；**0=明确无磁盘** |
| 10 | `hypervisor` | 否 | virtual_machine.hypervisor | string ≤255 | trim 后非空或空(=null)；一期无枚举 |

**模板级约束**：同一文件同一模板；BM 行出现 VM 专属列、VM 行出现 hardware 列 → 行/模板错误（与 F004 §2.4/§2.5 互斥 422 同口径）；缺列/多列/列序不符 → `IMPORT_INVALID_FILE`（DR-195）；不新增 `serial_number`/`cpu_sockets` 之外的字段；`metadata`/`description` 不出现（DR-200）。

## 6. 解析与逐行校验

- **CSV**：`csv.reader`，UTF-8（`utf-8-sig` 兼容 BOM），逗号分隔；多行引号字段按**逻辑记录号**计行号（DR-194）。
- **`.xlsx`**：`openpyxl.load_workbook(read_only=True, data_only=True)`；取**首个工作表**；不执行公式/宏；`.xls`/非 xlsx → `IMPORT_INVALID_FILE{unsupported_format}`（DR-207）。
- **逐行校验（复用同一 Service Layer）**：cluster 解析（`cluster_service.resolve_cluster`，批内缓存）、hostname 归一化与唯一（`normalization.normalize_hostname`/`hostname_key`）、type/enum/缺省（`validate_hardware`/`validate_virtual_machine_values`）、VM Host 四条件（`validate_virtual_machine`）——与 F004 `create_resource` **完全同源**；空单元格按 DR-199 先归一为「省略」再进入服务层（与 F004 API 的空串→422 差异仅在导入层预处理，见 §11 OPEN）。
- **缺省**：`role`→`OTHER`、`status`→`UNKNOWN`；可空列空→null；未知存 null，不以 0 代替（I-12）。
- **引用解析**：`cluster`→`cluster_id`、`host`→`host_resource_id`（UUID 落库，不拼接字符串，I-14）。

## 7. 原子性、再次校验与并发

- **单事务**：写入端点在同一 DB 事务内完成「解析 → 再次校验 → 逐行创建 → Audit → commit」。
- **行级归因 + 全批回滚**：逐行 `SAVEPOINT`；某行 DB 失败（并发唯一/FK）→ 回滚该 SAVEPOINT、记录行错误；迭代结束若有错误 → `db.rollback()` 整批回滚；否则一次 `db.commit()`（DR-203/206）。成功后每行 CREATE Audit 在**同一 Session/事务**（`audit.record` 仅 staging，`resource_snapshot` 快照白名单不变）。
- **写入前再次校验**：写入请求**重新上传同一文件**、服务端不留临时文件；校验使用事务内最新状态，覆盖「预校验后状态变化」窗口（DR-191/204）。**文件内重复**在插入前校验期检测并报两行行号，存在错误则不进入插入阶段。
- **Host 批外已存在**：VM Host 仅从写入事务开始前的库快照解析；本批新建 BM 不在解析集合内（DR-205）。
- **并发**：hostname 唯一由 DB 部分唯一约束兜底；VM Host 行 `FOR UPDATE` 与 Host 软删串行化（复用 F004 DR-71）；预校验 `lock=False` 只读。**说明**：Cluster 软删窗口与 F004 `POST /resources` 行为一致（`resolve_cluster` 不加锁），导入不额外收紧；DB FK 保证引用行存在（见 §12 风险 NOTE）。

## 8. 权限与配置

- 预校验、写入：`require_permission(Permission.IMPORT)`（EDITOR/ADMIN）；模板端点：`Permission.READ`。
- 401 先于 403；VIEWER→403 `FORBIDDEN{reason:"permission"}`；CSRF 沿用 F002 §2.1。
- Settings 新增：`import_max_file_bytes`（默认 5,242,880）、`import_max_rows`（默认 5000）、`import_error_preview_limit`（默认 1000）。

## 9. Frontend / Backend Work 与 Layers

**Backend（`backend=true`）**
- `app/services/resource.py`：抽取非提交核心（校验 + persist + Audit staging）；`create_resource` 薄包装；`validate_virtual_machine(..., lock: bool)`（默认 True）。
- `app/services/resource_import.py`：模板定义（两套 + 逐列说明）、CSV/xlsx 解析、行校验编排、批内重复/批外 Host 解析、SAVEPOINT 写入。
- `app/schemas/imports.py`；`app/api/v1/imports.py` + 在 `app/api/v1/router.py` 挂载 `imports.router`。
- `app/core/errors.py`：新增 413/422 错误子类；`docs/api/F002.md` §1.2 注册表登记（DR-197）。
- `app/core/config.py`：上限/预览设置。
- `backend/pyproject.toml`：`python-multipart`、`openpyxl`（DR-207，CONTRACT 签核）。
- 复用 `normalization`、`cluster_service.resolve_cluster`、`audit.record`、`resource_snapshot`；**不新增直写路径**。

**Frontend（`frontend=true`）**
- 导入入口：格式选择（CSV/xlsx）、模板查看/下载（消费 `GET /imports/resources/templates`）、逐列说明（含单位/枚举/必填）。
- 预校验结果表：行号/字段/原因（含 `related_row`），可滚动、Loading/Empty/Error（未知）状态；**无部分成功 UI 语义**。
- 确认导入 → 写入结果（创建数量）或整批失败提示（422 聚合错误）；错误不得伪装为空列表。

**Layers / api_required（DR-210）**

```yaml
layers:
  database: false    # 无新表/新列/新索引/迁移；见下
  backend: true
  frontend: true
api_required: true   # /imports/resources/validate · /imports/resources · /imports/resources/templates
```

`database=false` 理由：导入只写 `resources` + `bare_metal_details`/`virtual_machine_details`（既有表、既有约束）；重复/并发检查复用 `uq_resources_cluster_id_hostname_key`、FK 与既有 CHECK；cluster 解析复用 `clusters.code_key` 唯一；VM Host 解析复用 `(cluster_id, hostname_key)` 部分唯一；**无需新表、新列、新索引或 Migration**。由 Database 在 DATABASE Gate 以 `NOT_REQUIRED` 复核确认（无 Schema 交付）。

## 10. 验证策略（真实 PostgreSQL）

- **原子回滚**：构造含 1 个非法行的批次 → 422；断言 `resources`/`bare_metal_details`/`virtual_machine_details`/`audit_logs` 行数与调用前一致（A5/A6/I-1/I-8）。
- **文件内重复**：同批同 `(cluster, hostname)` 两行 → 两行行号报错，整批不写（A8/T27）。
- **现存冲突**：目标 hostname 已存在未删 → 行错误，现存行不变、无 UPDATE Audit（A9/I-6/T28）。
- **软删复用**：软删 hostname 可重用（A13/T03）。
- **VM Host**：不存在/软删/非 BARE_METAL/跨 Cluster → 行错误（A11/I-9/T08/T09/T28）；**同批 BM 不可被本批 VM 引用**（A19）。
- **cluster 列**：不存在/软删 → 行错误；INACTIVE → 通过（A12/T29）。
- **上限**：字节数超限（解析前）与行数超限（校验前）→ 413，无部分导入（A20/T28）。
- **权限矩阵**：401/403/允许；EDITOR/ADMIN 可，VIEWER 403，未认证 401（A22/T25）。
- **CSV/xlsx 一致**：同一数据两种格式行为一致（A1）。
- **单位/未知值/缺省**：MiB/GiB、null vs 0、`role`/`status` 缺省（A15/A16/A17/T37/T38）。
- **写入前再次校验**：预校验后、写入前改变库状态（如占用 hostname）→ 写入 422 回滚。
- **并发**：两个并发写入重叠 hostname → 仅一个成功；另一个整批回滚、无残留、无重复（DR-206/§27）。
- **契约收敛**：模板列序/表头/未知列/类型错配（A21）；文件级错误码。
- **限制**：唯一性/回滚/并发须真 PG；SQLite/Mock 不构成证据。

## 11. Blocking / OPEN

- **Blocking**：无。
- **PROPOSED→CONTRACT（非阻塞）**：I-1 模板列集、I-2 Host 引用形式、I-3 接口形态、I-4 上限数值（须真实 PG 性能证据，D03）、I-5 空值/枚举、I-6 错误形态与行号、I-7 metadata/description、I-8 计划字段。
- **新依赖（CONTRACT 签核）**：`openpyxl`（MIT，≥3.1,<3.2）、`python-multipart`（Apache-2.0）；遵守 §29，无禁项。
- **OPEN（product，非阻塞）**：I-7 `metadata`/`description` 是否纳入可选列 — 本设计默认不导入。
- **OPEN（CONTRACT）**：`resource_type` 列是否在专用模板中保留（本设计保留）；表头是否要求严格列序（本设计严格）。
- **跨 Contract**：新增 4 个错误码须登记 `docs/api/F002.md` §1.2；Architect 在 CONTRACT 落地（DR-197）。
- **NOTE（风险，与 F004 一致）**：Cluster 软删窗口在 F004 与 F014 均不额外加锁；DB FK 保证引用行存在，语义窗口由既有行为承担，不在本 Feature 收紧。

## 12. D01 最终关闭核对（I-9）

D01 v11 §5.3（hostname 归一化/长度/ASCII-only 折叠）、§5.4（hardware 9 字段：类型/范围/单位/未知 null vs 0）、§5.5（VM：host 必填四条件、vcpu/memory_mb 正整数、disk_gb 非负 0=明确无、hypervisor trim/≤255/无枚举、metadata 归 Resource）与 F014 导入字段口径**逐项一致，无新增/偏离口径**。F014 CONTRACT READY 时记录 **D01 最终关闭**。

## 13. 结论与下一步

无 Blocking Questions。DR-190–DR-212 覆盖两阶段 API、模板/上限（D03）、逐行校验与 Service Layer 复用、原子与并发、权限、解析依赖、验证与计划字段。**Status：`READY FOR DESIGN`。**

下一步：TEST_DESIGN 给 A1–A26/I-1–I-17 判据与真 PG 用例；Database 在 DATABASE Gate 复核 `layers.database=false`（`NOT_REQUIRED`）；CONTRACT 定稿 `docs/api/F014.md` + 签核 D03（模板/上限/依赖/错误码登记）→ `READY FOR IMPLEMENTATION`。