# F037 导入解析异常统一收敛为 422 IMPORT_INVALID_FILE — Test Report

> 同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本与证据。
> **当前状态**：§1 TEST DESIGN = **TD-F037-1（v1，2026-10-29，`TEST DESIGN READY`）**；§2 TEST EXECUTION = **TE-F037-1（v1，2026-10-29，`READY FOR REVIEW`）** —— 52/52 新增用例与全部必要回归**实际执行通过**。
> `TEST DESIGN READY` 仅表示方案可验证；§2 才是执行结论。§1 中「期望」为设计期断言，TEST 阶段对两处口径做了修订（`TD-F037-U9` 的空 zip 期望按 `TD-I-8` 更正；`TD-F037-U2` 的 `parse_records` 期望按修复后语义更正），逐条差异见 §2 TE-7。

**版本记录**

| 阶段 | 版本 | 日期 | 结论 | 依据 HEAD |
| --- | --- | --- | --- | --- |
| TEST DESIGN | TD-F037-1 | 2026-10-29 | `TEST DESIGN READY`（**不是测试通过**；实现未开始，全部用例待执行） | `a6932c5`（工作区仅新增未跟踪 `docs/features/F037/architecture.md`；`backend/**`、`frontend/**`、`docs/api/**` 零 diff） |
| TEST | TE-F037-1 | 2026-10-29 | **`READY FOR REVIEW`**：新增模块 52/52 PASS（U 23 / I 23 / S 6，含 BE-01 与输入 ③）；回归 R1–R6 全部实跑通过（42 / 28 / 31 / 48 / 4 / 3）；真实 PostgreSQL 16.15，`openpyxl 3.1.5 / LXML=True / lxml 5.2.1` | `dec9445` + 工作区 BE-01 修复（`backend/app/services/resource_import.py` 未提交 10+/1−；新增未跟踪测试模块 `backend/tests/integration/test_f037_import_parse_errors.py`） |

---

## 1. Test Design（TD-F037-1，v1，2026-10-29）

### TD-1 Task / Status / Basis

- **Task**：F037「导入解析异常统一收敛为 422 `IMPORT_INVALID_FILE`」（FEATURE / P0 / M28）；分支 `feature/F037-import-parse-error-contract`（交付线 `v3.4`，`start_commit` `1c0eeaf`，本 TD 编写时 HEAD `a6932c5`）；`plan revision` 25；需求 **revision 16**；阶段 **TEST_DESIGN**，Tester 只读核对 + 只写本文件。
- **Status**：**`TEST DESIGN READY`** —— A1–A22 全部有可执行映射；两类输入的有效性已在当前环境**实测证明可构造**（见 TD-4）；`TD-I-1…TD-I-7` 为登记/待裁定项，**不构成不可验证项**；当前无真实 PG（TD-6），I 层用例在 TEST 阶段若无库一律 `NOT TESTED`，不影响本阶段结论。
- **范围**：只做设计检查（验收映射、边界与反向场景、夹具/环境、可观察结果、可验证性）。**未写任何生产代码或测试代码**，未执行测试、构建或任何改变 Git 状态的命令；仅运行 TD-6 列出的只读探测命令，输出如实抄录。

| Basis | 版本 / 状态 | 本 TD 用途 |
| --- | --- | --- |
| `docs/features/F037/product.md` | v1（READY FOR ARCHITECT） | §2.1 S1–S7、§2.2 N1–N8、§3.1–3.3 期望契约、§4 B1–B12、**§7 A1–A22**（验收唯一来源） |
| `docs/features/F037/architecture.md` | v1（READY FOR DESIGN，§6.2 附注待 CONTRACT 签核） | **§10.1–§10.12 测试输入（主依据）**、§3 白名单/排除项、§4 L1–L7 生命周期与顺序、§5.1 错误文案/§5.2 日志字段、§11 R-1…R-10 |
| `docs/api/F014.md` | v1 §1.2 / §2 / §7 | `IMPORT_INVALID_FILE` 与 7 个 `reason`、校验顺序、解析口径 |
| `docs/api/F023.md` | v2 §1.2 / §2 / §12 | 错误码与 `reason` 全复用、同源顺序、锁序/原子性 |
| `docs/product/requirements-v3.md` | revision 16 | §22、§24、§24.1、§24.5、§24.6、§31 **T27 / T28 / T72 / T107–T116 / T124 / T126** |
| `docs/project/project-plan.yaml` | revision 25 F037 条目 | `layers={database:false,backend:true,frontend:false}`、`api_required=true`、`blocking_decisions: []`、acceptance 文本 |
| 既有已签核口径 | `docs/features/F034/architecture.md` §12 TD-I-1、`docs/features/F036/architecture.md` §3/§12 | T114 等价性口径、不升版附注先例（F035-RV-05） |
| 规则与方法 | `AGENTS.md`、`docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`.pi/agents/tester.md` | 交接/缺陷格式、验证纪律、完整性对照方法 |
| 只读代码核对（`a6932c5`） | `app/services/resource_import.py:419-459`（`_parse_csv`/`_parse_xlsx`/`parse_records`）、`:790-836`（`parse_and_validate`）、`app/services/resource_interface_ip_import.py:1187-1240`（复用 `parse_records`）、`:1307/:1314`（`with_for_update` 仅写入路径）、`app/api/v1/imports.py:1-10,52-140`（四端点与顺序）、`app/core/errors.py:204-232`（`ImportInvalidFile`）、`:293-296` / `:324-328`（422/500 handler）、`app/core/logging.py:62-70`（`configure_logging`，无 `propagate=False`） | 判定可观察面与断言可实现性 |
| 只读测试基线 | `backend/tests/conftest.py`（DB-D10 双守卫、`auth_app`/`auth_session_factory`/`committed_engine`）、`tests/integration/f015_helpers.py`（`role_client_factory` 与对象 helper）、`test_imports.py`、`test_f023_resource_interface_ip_import.py`、`test_f034_csv_text_carrier.py`（双载体 `post()` / `assert_equivalent()`）、`test_import_performance.py` | 复用夹具、计数断言与命名风格；不改写既有用例 |

### TD-2 层级记号与可验证性前提

| 记号 | 载体 | 说明 |
| --- | --- | --- |
| **U** | pytest 直调 `app.services.resource_import.parse_records` / 私有解析函数 | 纯函数，**不需要数据库**；输入构造有效性、白名单语义、`close` 生命周期、`caplog` 日志字段 |
| **I** | pytest + `auth_app`（真实 `create_app`）+ **真实 PostgreSQL**（`TEST_DATABASE_URL`，DB-D10 双守卫） | 8 例端到端、零写入/零 Audit、401/403 先行、413/表头/行级回归、双载体等价、fd 计数 |
| **S** | `git diff` / `grep` / 既有静态用例 | 契约与常量零 diff、日志调用形态、`validate` 路径无锁语句、端点清单 |
| **R** | 既有回归套件（pytest） | T27 / T28 / T72 / T107–T116 / T124 / T126 零回归 |

**可验证性前提**

1. **实现未开始**：`a6932c5` 工作区 `backend/**` 零 diff ⇒ 本阶段所有用例状态为「待执行」，不得读作 PASS。
2. **符号名以架构为准**（`_PARSE_FAILURES`、`_invalid_file_on_parse_failure`、`_close_workbook`、logger `csm.imports`、事件串 `import parse rejected`）：TEST 按**语义**断言（状态码/`code`/`reason`/异常类型/调用次数/日志字段集合），等价改名不判 FAIL，但须在 TEST 报告登记实际名称。
3. **测试模块落点**：新建 `backend/tests/integration/test_f037_import_parse_errors.py`（U + I 同模块，沿用 `test_f023_*` 先例）。该模块**不**导入 `app.core.access_scope` 符号 ⇒ 不需要 `pytest.mark.real_scope`（F030 §9.1 约定），并由 `test_f030_test_harness.py` 的 AST 门禁复核。
4. **不发明规则**：预期只引用 A1–A22 / B1–B12 / L1–L7 / F014 §1.2 / F023 v2 §1.2；架构未固定处按 TD-7 `TD-I-*` 登记，不转成断言。
5. **不新增业务断言**：本 Feature 只改变「同一批已被拒绝的输入」的可观察表达，用例断言**拒绝面不变、表达面收敛**，不为任何输入新增接受路径。

### TD-3 验收映射（A1–A22 → 34 条 `TD-F037-*`）

记法：`ID | 层 | 目标 / 前置 | 步骤 | 期望（判据） | 映射`。TEST 阶段逐条标 `PASS / FAIL / BLOCKED / NOT TESTED`，附命令与证据路径。公共断言包（下文称 **EB**，8 例共用）：

> **EB（8 例断言包，A1–A8）**：`resp.status_code == 422`；`resp.json()["error"]["code"] == "IMPORT_INVALID_FILE"`；`resp.json()["error"]["details"] == {"reason": "unreadable"}`（**逐键相等**，不得出现 `missing_columns`/`unknown_columns`）；`message == "Invalid import file"`；`set(resp.json()) == {"error"}`；`set(resp.json()["error"]) == {"code","message","details"}`；并显式反例排除 `status_code not in (200, 201)`、`!= 413`、`!= 500`；同字节再发一次 → `resp.json()` 完全相同（A20 前置）。

| ID | 层 | 目标 / 前置 | 步骤 | 期望（判据） | 映射 |
| --- | --- | --- | --- | --- | --- |
| `TD-F037-U1` | U | **输入 ① 有效性证明**（architecture §10.2；SSOT，8 例前置） | 按 TD-4 构造 BM 14 列与 26 列两份超长字段 CSV；先 `list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))`，再 `resource_import.parse_records(raw, "csv")` | 两次均抛 `csv.Error`（消息含 `field larger than field limit`）；`len(raw) > 131_072` 且 `<= 5_242_880`；列数 == 14 / 26；实测字节数记入报告（本机 131,229 / 131,336） | A1–A8 前置；T27 |
| `TD-F037-U2` | U | **输入 ② 有效性证明**（SSOT，8 例前置） | 按 TD-4 构造结束标签损坏 xlsx；先 `load_workbook(io.BytesIO(raw), read_only=True, data_only=True)`，再 `list(ws.iter_rows(values_only=True))`，再 `parse_records(raw, "xlsx")` | `load_workbook` **不抛**；`iter_rows` 抛 `ElementTree.ParseError`；`parse_records` 抛同一类型；`raw.startswith(b"PK\x03\x04")`；`0 < len(raw) < 5_242_880`（本机 5,029 B） | A1–A8 前置；T27 |
| `TD-F037-I1` | I | 资源导入 `/resources/validate` × 输入 ①（BM 14 表头） | EDITOR 客户端 `files={"file":("import.csv",raw,"text/csv")}, data={"format":"csv"}` | **EB** | A1；S1、S2 |
| `TD-F037-I2` | I | 资源导入 `/resources/validate` × 输入 ② | `format="xlsx"`，`content_type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | **EB** | A2；S1、S2 |
| `TD-F037-I3` | I | 资源导入 `/resources` × 输入 ① | 同 I1 换写入端点 | **EB**；响应体无 `created`/`errors` | A3；S1、S2 |
| `TD-F037-I4` | I | 资源导入 `/resources` × 输入 ② | 同 I2 换写入端点 | **EB** | A4；S1、S2 |
| `TD-F037-I5` | I | F023 `/resource-interfaces-ips/validate` × 输入 ①（26 列表头） | 同 I1 换端点 | **EB** | A5；S1、S2 |
| `TD-F037-I6` | I | F023 `/resource-interfaces-ips/validate` × 输入 ② | 同 I2 换端点 | **EB** | A6；S1、S2 |
| `TD-F037-I7` | I | F023 `/resource-interfaces-ips` × 输入 ① | 同 I3 换端点 | **EB**；无 `created`/`interfaces_created`/`ip_addresses_created` | A7；S1、S2 |
| `TD-F037-I8` | I | F023 `/resource-interfaces-ips` × 输入 ② | 同 I4 换端点 | **EB** | A8；S1、S2 |
| `TD-F037-I9` | I | **拒绝零残留**（A9；前置：I3/I4/I7/I8 的 4 条写入路径） | 前置基线用 `committed_engine` + `auth_session_factory` 采 `clusters, resources, bare_metal_details, virtual_machine_details, interfaces, ip_addresses, audit_logs` 计数（沿用 `test_imports._counts` / F023 `COUNT_TABLES` 并集），逐条提交 4 个写入请求后再采 | 7 表计数**逐表不变**；无 `201`；**Activity 无独立表**（由 `audit_logs` 派生）⇒ `audit_logs` 不变即同时覆盖 Activity，报告须按此措辞，**不得**写「已检查 activity 表」 | A9；S3；T27、T68、T123 |
| `TD-F037-I10` | I | **401 / 403 先行**（A10；前置：输入 ①，4 端点） | (a) `TestClient(auth_app)` 未登录各提交 1 次；(b) `role_client_factory("VIEWER")` 各提交 1 次 | (a) 8 例全 `401`，`code=="AUTH_REQUIRED"`；(b) 8 例全 `403`，`code=="FORBIDDEN"`、`details.reason=="permission"`；两者**均不得**出现 422/500（证明认证/权限依赖先于 body 与解析） | A10；B10；T72、T115、T124 |
| `TD-F037-I11` | I | **413 不得被 422 取代**（A11） | `monkeypatch.setattr(imports_api, "get_settings", lambda: Settings(_env_file=None, import_max_file_bytes=10))` + 输入 ① → 4 端点；再以默认设置 + 输入 ①（不 monkeypatch） | monkeypatched：4 例全 `413`、`code=="IMPORT_FILE_TOO_LARGE"`、`details=={"limit_bytes":10}`；默认：全 `422`（`len(raw) < 5 MiB` 必须越过 413 后才在解析阶段被拒）。**禁止**实现以此改成「按字节提前拒绝」 | A11；B4 |
| `TD-F037-I12` | I | **`empty_file` 不被收敛**（A12；B1） | 4 端点各提交 `b""` 与「仅表头无数据行」（BM14 / 26 列） | 8 例全 `422`、`reason=="empty_file"`（**不得**为 `unreadable`），`details` 恰 `{"reason":"empty_file"}` | A12；B1；T110 |
| `TD-F037-I13` | I | **`unsupported_format` 不被收敛**（A13；B2） | `b"\xd0\xcf\x11\xe0" + b"notxlsx"`（OLE2 `.xls` 魔数）`format="xlsx"` → 4 端点；对照 `b"PK\x03\x04not-a-zip"` → 4 端点 | OLE2：`reason=="unsupported_format"`；`PK` 非 zip：`reason=="unreadable"`（既有行为，改前后一致） | A13；B2 |
| `TD-F037-I14` | I | **表头/列类 reason 与顺序不变**（A14；B3） | 复用 `test_imports.py::test_header_errors`（缺列/未知列/列序/`header_missing`）与 F023 对应表头用例；另加一次自有断言：`BM_HEADERS + ["interface_name"]` → `unknown_columns`，同时 `import_max_rows=1` + 2 行 → `413 IMPORT_ROW_LIMIT_EXCEEDED`（行数先于表头） | `reason` ∈ `header_missing`/`missing_columns`/`unknown_columns`/`column_order` 各就位；`details` 携带 `missing_columns`/`unknown_columns` 时不出现 `reason=="unreadable"`；顺序 `413 行数 → 表头 422` 不变（沿用 `test_validation_order_row_limit_before_header` 口径） | A14；B3；T72、T112 |
| `TD-F037-I15` | I | **5001 行 → 413，无部分导入**（A15） | 5001 行合法短行 CSV → 4 端点（写入端点另采计数） | 4 例全 `413`、`code=="IMPORT_ROW_LIMIT_EXCEEDED"`、`details=={"limit_rows":5000}`；7 表计数不变 | A15；B4；T111、T28 |
| `TD-F037-I16` | I | **行级 `RowError` 形状与行号不变**（A16；B5） | 复用 `test_imports.py::{test_field_validation_errors,test_validate_aggregates_all_errors_not_fail_fast,test_file_internal_duplicate_reports_related_row}` 与 F023 `T109` 等价用例；写入端点再验 `IMPORT_VALIDATION_FAILED` | 预校验 `200` + `errors[]` 非空且不 fail-fast；写入 `422`、`code=="IMPORT_VALIDATION_FAILED"`、`details` 4 键齐备；每条 `RowError` 键集 == `{"row","field","reason","related_row"}`，`row` 为 1-based（表头为第 1 行，数据自第 2 行） | A16；B5；T27、T67、T109、T124 |
| `TD-F037-I17` | I | **双载体等价**（A17；B9；T114 口径不变） | 复用 F034 的载体形状常量（`PASTED_FILE_NAME="csm-pasted-import.csv"`、`PASTED_MIME="text/csv;charset=utf-8"`、`FILE_NAME`/`FILE_MIME`）：同一份输入 ① 字节分别以文件载体与文本载体提交 4 端点 | `status_code` 相同（全 422）且 `resp.json()` **deep-equal**（逐字段：`code`/`message`/`details.reason`）；另在 U 层断言 `parse_records` 抛出的 `ImportInvalidFile.details` 与 HTTP `details` 一致（单一定义来源，无载体分支） | A17；S5；T107、T108、T114、T115 |
| `TD-F037-U12` | U | **日志 content-free**（A18 前半；前置：`caplog.set_level(logging.INFO, logger="csm.imports")`） | 对输入 ①② 各调 `parse_records` 一次；把上传内容类 marker（`F034-MARKER-*` 形式随机串、字段值前缀、`<worksheet`、`mismatched tag`、`filename`）写入构造的输入；采集 `caplog.records` | 若存在 `csm.imports` 记录：`record.args` 只含 `format`(csv/xlsx)、`bytes`(int)、`error`(白名单异常**类名**，如 `Error`/`ParseError`/`BadZipFile`)；`record.msg` 为固定事件串；`caplog.text` **不含** marker、字段值、XML 片段、`filename`、`Traceback`、`str(exc)` 文本；无 `exc_info`（`record.exc_info is None`）。**若实现未保留日志（OPEN-T2）**：断言改为「`csm.imports` 无任何记录」同样 PASS（判据非「必须有日志」） | A18；§24.5、§22 |
| `TD-F037-I18` | I | **响应体 content-free**（A18 后半） | 用带 marker 的输入 ①② 提交 4 端点（此时解析已失败，marker 位于首个超长字段/工作表名附近） | 响应 `resp.text` 不含 marker、`<worksheet`、`mismatched tag`、`field larger than field limit`、`Traceback`、`.py` 路径；`message` 恒为 `Invalid import file` | A18；§3.3 |
| `TD-F037-U3` | U | 白名单异常 → `ImportInvalidFile{unreadable}` 且保留原因链（A19 前半） | 对 TD-5 矩阵每类触发一次（真实 payload 优先，注入兜底） | 抛 `ImportInvalidFile`，`.details=={"reason":"unreadable"}`，`exc.__cause__` 为原解析器异常类型；**不**抛裸异常 | A19；B7 |
| `TD-F037-U4` | U | 白名单 9 类参数化（R-1 检测） | 按 TD-5 表逐行构造：真实 payload 可达者用 payload，其余用 `monkeypatch` 注入（`openpyxl.load_workbook` 于 `_parse_xlsx` 内**惰性导入**，patch 模块属性可生效） | 9 类全部收敛为 `unreadable`；真实 payload 未可达的类别在报告中标「注入等价验证 / 真实可达性 `NOT TESTED`」，不得写成「真实输入已验证」 | A19；R-1 |
| `TD-F037-U5` | U | **`AppError` 原因保真**（U-c） | 注入/构造：`ImportInvalidFile("empty_file")`、`ImportInvalidFile("unsupported_format")`、`ImportInvalidFile("column_order", ...)`、`ImportFileTooLarge(10)`、`ImportRowLimitExceeded(1)`、`ImportValidationFailed(...)`、`ValidationError(details=...)`（在 `with` 作用域内抛） | 全部**原样**抛出：同类型、同 `status_code`、同 `details`（不得改写为 `unreadable`，不得二次包装）；`resource_import.parse_records(b"", "csv")` → `empty_file`；`parse_records(b"\xd0\xcf\x11\xe0", "xlsx")` → `unsupported_format` | A19；B1、B2、B6 |
| `TD-F037-U6` | U | **`MemoryError` / `RecursionError` 不吞**（U-d；R-6） | 注入 `MemoryError()`、`RecursionError()` 于 `csv.reader` 迭代与 `load_workbook` 两处 | 原样传播（`pytest.raises(MemoryError)` / `pytest.raises(RecursionError)`），**不得**为 `ImportInvalidFile` | A19；B7（事实披露：改前会转 `unreadable`，改后回 500） |
| `TD-F037-U7` | U | **`KeyboardInterrupt` / `SystemExit` 语义不变** | 注入 `KeyboardInterrupt()`、`SystemExit(3)` | 原样传播（`BaseException` 子类天然不被捕获），`SystemExit.code == 3` | A19；B7 |
| `TD-F037-U8` | U | **未白名单异常不转换**（U-f；B8） | 注入 `AttributeError`/`TypeError`/`IndexError`/`AssertionError`/`OverflowError` | 原样传播，**不得**为 `ImportInvalidFile`（`OverflowError` 现状即未白名单，R-1 登记） | A19；B8 |
| `TD-F037-U9` | U | **判定顺序与生命周期不变**（L4/L5） | `parse_records(b"", "csv")` / `b"" xlsx`；非 PK 的 `.xls` 魔数；`PK\x03\x04` 非 zip；**零成员 zip**（magic `PK\x05\x06`）；**合法容器缺 worksheet 部件**；正常 xlsx | `empty_file`（空字节，先于 dispatch）→ `unsupported_format`（PK 闸门先于任何解析器调用）→ `unreadable`（坏 zip）→ **`unsupported_format`（零成员 zip 被 PK 闸门拒绝，见 `TD-I-8` 修订）**→ `empty_file`（合法容器但 `workbook.worksheets` 空，先于 `iter_rows`）→ 正常解析返回 `list[list[str]]` 且 `parse_records` 返回类型仍为物化列表 | A19；B1、B2、L4、L5；`TD-I-8` |
| `TD-F037-U10` | U | **`close` 生命周期与「close 覆盖 422」**（R-2） | (a) 正常 xlsx：spy `resource_import._close_workbook` 计数；(b) 假 workbook：`iter_rows` 抛 `ElementTree.ParseError` 且 `close()` 抛 `RuntimeError`；(c) `load_workbook` 自身抛 `BadZipFile` | (a) 恰 1 次；(b) 最终仍为 `ImportInvalidFile{unreadable}`（`RuntimeError` 不得覆盖已判定 422），`close` 恰 1 次且 `finally` 内无 `raise`/`return`；(c) `close` **0** 次（`workbook is None` 守卫） | A19；L2、L3；R-2 |
| `TD-F037-U11` | U | **转换作用域最小性**（R-9） | `monkeypatch.setattr(resource_import, "_cell_text", raising TypeError)` 后解析正常 CSV；再 monkeypatch `parse_and_validate` 之前的 `_resolve_template` 抛 `ValueError` 类别的表头错误 | `_cell_text` 的 `TypeError` **原样传播**（证明归一位不在 `with` 内）；表头/列校验仍由 `_resolve_template` 产生既有 `reason`（不落入 `unreadable`）。S 层配 `S3` 复核两处 `with` 内只有第三方调用 | A19；R-9 |
| `TD-F037-I19` | I | **分类边界到 HTTP 的落点**（A19 补充；可选） | `monkeypatch.setattr(resource_import, "parse_records", raising MemoryError)`；`TestClient(auth_app, raise_server_exceptions=False)`（沿用 `test_auth.py:344` 先例）→ 4 端点 | `500`、`code=="INTERNAL_ERROR"`、`message=="Internal server error"`、`details=={}`；**不得**为 422 `IMPORT_INVALID_FILE`（B7/B8 的可观察面） | A19；B7、B8 |
| `TD-F037-I20` | I | **重复 `validate` 一致且无副作用**（A20） | 输入 ① 对 4 端点各提交 2 次；计数表前后对比 | 两次 `resp.json()` 完全相同；7 表计数不变；`audit_logs` 不变（`validate` 只读）。**锁语义**：不以 `pg_locks` 断言（无可稳定观察面，见 TD-7 `TD-I-6`），改由 `S6` 静态核对 `validate` 路径无 `with_for_update`/`begin_nested` | A20；T116 |
| `TD-F037-S1` | S | **改动面收口**（A21 前半） | `git diff --stat -- backend/app/services/resource_import.py`；`git diff --stat -- backend/app/services/resource_interface_ip_import.py backend/app/api backend/app/core backend/app/models backend/alembic frontend` | 前者有 diff；后者**零 diff**（`core/errors.py` 必须零 diff）；新增文件仅 `backend/tests/integration/test_f037_import_parse_errors.py` + 测试产物 | A21；S6；CHG-015 §2 |
| `TD-F037-S2` | S | **上限与解析严格性零变更** | `git diff -U0 -- backend/app/services/resource_import.py \| grep -nE 'field_size_limit\|strict=True\|import_max_'` ；`grep -rn "field_size_limit\|csv.QUOTE" backend/app` | 无命中（或仅出现在注释/`_PARSE_FAILURES` 说明中，逐条核对）；5,242,880 / 5000 / 1000 三常量零 diff | A21；T126 |
| `TD-F037-S3` | S | **日志调用形态与脱敏** | `grep -nE 'logger\.(exception\|error)\(' backend/app/services/resource_import.py`；`grep -n 'filename\|exc_info' backend/app/services/resource_import.py`；`grep -n "except Exception" backend/app/services/resource_import.py` | 无 `logger.exception`/`logger.error`；无 `filename`/`exc_info`；`except Exception` 仅出现在 `_close_workbook` 清理边界（1 处），解析分类处只有 `except AppError: raise` + `except failures` 两个子句 | A18、A21；§3.2、§5.2 |
| `TD-F037-S4` | S | **契约附注不升版**（A21 后半；S7） | `git diff -- docs/api/F014.md docs/api/F023.md`；读两文件版本行与修订表 | 只允许四条落稿（F014 §1.2 一条 bullet + §13 一行；F023 v2 §1.2 一条 bullet + §17 一行），文本与 architecture §6.2 A–D 一致；**F014 仍 v1、F023 仍 v2**；不得出现新 `reason`/错误码/`details` 键/上限；`docs/api/F002.md` 零 diff | A21；S7；T126 |
| `TD-F037-S5` | S | **模板/端点/权限零变更** | 运行 `test_reg02_route_inventory`（`test_f023_*:1144`）与 `test_templates_spec_and_read_permission`（`test_imports.py:173`）；`grep -n "IMPORT_INVALID_FILE\|unreadable" backend/app/services/resource_import.py` | 路由清单不变；BM 14 / VM 10 / 26 列列集与列序不变；`_PARSE_FAILURES` 不引入新 `reason` 取值，`ImportInvalidFile` 调用点新增的 `reason` 仅 `"unreadable"` | A21；T126 |
| `TD-F037-S6` | S | **`validate` 只读静态证据**（A20 补充） | `grep -n "for_update\|begin_nested\|db.commit" backend/app/services/resource_import.py backend/app/services/resource_interface_ip_import.py` 并逐条核对行号归属 | `with_for_update`/`begin_nested`/`commit` **仅**出现在写入函数（`resource_import.py:870+`、`resource_interface_ip_import.py:1307/1314/1488/1556`），`parse_and_validate` / `validate_import` 区间内无命中 | A20；§10.4 |
| `TD-F037-I21` | I | **fd / 资源泄漏**（R-5；前置 `/proc/self/fd` 可读，本机实测可用） | 同一进程连续提交损坏 xlsx 20 次，前后 `len(os.listdir("/proc/self/fd"))`；`/proc` 不可用时 `pytest.skip` 并登记 | 20 次后 fd 数**不增长**（允许 ±0；如出现波动，须在同一进程内做前后各 3 次采样并附数值）；跳过后以 `TD-F037-U10` 的 close 计数作为确定性替代证据 | A21 关联；R-5 |

**回归执行项（A22 → R1–R6，T27 / T28 / T72 / T107–T116 / T124 / T126）**

| ID | 套件 | 本机 `--collect-only` 计数（`a6932c5`） | 判据 |
| --- | --- | --- | --- |
| `TD-F037-R1` | `tests/integration/test_imports.py` + `test_import_tester_acceptance.py` + `test_import_constraints.py` | 29 + 9 + 4 = **42** | 全绿；`test_header_errors`、`test_format_and_file_level_errors`、`test_file_size_and_row_limits`、`test_validation_order_row_limit_before_header`、`test_permission_matrix` 必须逐条通过（T27/T28/T72 核心） |
| `TD-F037-R2` | `tests/integration/test_f023_resource_interface_ip_import.py`（含 `test_reg02_route_inventory`） | **28** | 全绿，计数不下降（F023 既定基线 28） |
| `TD-F037-R3` | `tests/integration/test_f034_csv_text_carrier.py` + `test_f034_csv_text_carrier_scope.py` | 29 + 2 = **31** | 全绿（T107–T116，重点 T114 / `test_td3_t114_field_boundaries`）；**不得**改写 F034 corpus 或等价性用例 |
| `TD-F037-R4` | `tests/integration/test_f035_append_interface_ip_import.py` + `test_f035_append_scope.py` + `test_f035_tester_acceptance.py` + `test_f036_attribution.py` + `test_f036_tester_independent.py` | 20 + 2 + 16 + 5 + 5 = **48** | 全绿（T124 / 追加路径 / 归因口径不变） |
| `TD-F037-R5` | `tests/integration/test_import_performance.py` | **4** | 全绿（上限拒绝与预览截断口径不变；数值仅打印，不新增阈值） |
| `TD-F037-R6` | `tests/integration/test_f030_test_harness.py`（补充：新模块 real_scope 门禁） | **3** | 全绿（新模块未触碰 `access_scope` 符号，不需要该 mark；若将来新增行级范围用例须声明 mark） |

> 计数为**本次只读采集**结果，TEST 阶段开跑前须重测并以此轮实测为基线（`≥` 比较）；若低于上表则先核环境（不得直接判 FAIL 实现）。

### TD-4 两类输入的构造与有效性前置断言（architecture §10.2）

**输入 ① — CSV 单字段超 `csv.field_size_limit`**

```python
def oversized_field_csv(headers: list[str], pad: int = 131_073) -> bytes:
    row = [""] * len(headers)
    row[0] = "F37A"          # cluster（内容无关，解析期即失败）
    row[-1] = "x" * pad       # 单字段 > csv.field_size_limit()（本机 131072）
    return (",".join(headers) + "\n" + ",".join(row) + "\n").encode("utf-8")
```

- **不变量**：`131_072 < len(raw) <= 5_242_880`；表头列数 **14**（F014 BM）/ **26**（F023）；单字段长度 131,073 > `csv.field_size_limit()`（本机实测 `131072`）。
- **实测（本机，`python3` 直接执行）**：BM 14 列 → **131,229 B**；26 列 → **131,336 B**；两者 `list(csv.reader(...))` 均抛 `_csv.Error: field larger than field limit (131072)`。
- **有效性前置断言**（`TD-F037-U1`，8 例的硬前置）：`pytest.raises(csv.Error)` 成功后，本用例才有资格继续；若构造不再抛错，判 **BLOCKED**（构造失效），不得改判 PASS。
- **口径登记**：`product.md` §2.1 / plan acceptance 中的「131,082 B」为示例值（字节数随表头与行内容变化）；断言**只**使用不变量与实测字节数，不硬编码 131,082（TD-7 `TD-I-2`）。

**输入 ② — `.xlsx` 结束标签损坏（`load_workbook` 成功、`iter_rows` 抛错）**

```python
good = _xlsx_bytes(BM_HEADERS, [{"cluster": "F37A", "hostname": "f37-x", "resource_type": "BARE_METAL"}])
src = zipfile.ZipFile(io.BytesIO(good)); out = io.BytesIO()
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
    for item in src.infolist():
        payload = src.read(item.filename)
        if item.filename == "xl/worksheets/sheet1.xml":
            assert b"</worksheet>" in payload
            payload = payload.replace(b"</worksheet>", b"</workshet>")   # 只坏结束标签
        dst.writestr(item, payload)
raw = out.getvalue()
```

- **不变量**：`raw.startswith(b"PK\x03\x04")`（不得被 `unsupported_format` 的 PK 闸门抢先拦截）；`0 < len(raw) < 5_242_880`；zip 成员名固定 `xl/worksheets/sheet1.xml`。
- **实测（本机）**：正常 xlsx 5,029 B / sheet 部件 1,693 B / 损坏后 **5,029 B**；`load_workbook(..., read_only=True, data_only=True)` **成功**（worksheets `['Sheet']`）；`list(iter_rows(values_only=True))` 抛 `xml.etree.ElementTree.ParseError: mismatched tag: line 1, column 1683`；`close()` 正常。
- **有效性前置断言**（`TD-F037-U2`）：三步顺序断言（`load_workbook` 不抛 → `iter_rows` 抛 `ElementTree.ParseError` → `parse_records` 抛同一类型）；任一步不符即 **BLOCKED**。
- **改前缺陷基线（只读探测，供 TEST 对照）**：当前 `parse_records` 对输入 ① 抛 `_csv.Error`、对输入 ② 抛 `ElementTree.ParseError`（未收敛 ⇒ 现网表现为 500）；修复后两者必须变为 `ImportInvalidFile{unreadable}`。此基线仅作「缺陷可复现」证据，不作为 PASS 依据。

### TD-5 白名单样本矩阵（R-1 检测，`TD-F037-U4`；本机真实 payload 探测结果）

| # | 白名单类型 | 构造 | 本机实测抛出点与类型 | 判定层 |
| --- | --- | --- | --- | --- |
| 1 | `csv.Error` | 输入 ① | `_parse_csv` 迭代期 `_csv.Error` | 真实 payload（U1） |
| 2 | `zipfile.BadZipFile` | `b"PK\x03\x04not-a-zip"` | `load_workbook` → `BadZipFile` | 真实 payload |
| 3 | `zipfile.LargeZipFile` | 需伪造 ZIP64 声明 | 本机未构造成功 | **注入等价验证；真实可达性 `NOT TESTED`** |
| 4 | `zlib.error` | 翻转 `xl/worksheets/sheet1.xml` 首个压缩字节（CRC/deflate 损坏） | `load_workbook` → `zlib.error` | 真实 payload |
| 5 | `ElementTree.ParseError` | 输入 ②；另「截断 sheet 部件」同样落在 `iter_rows` | `iter` → `ElementTree.ParseError` | 真实 payload（U2） |
| 6 | `NotImplementedError` | 需声明不支持的压缩方法 | 本机未构造成功 | **注入等价验证；真实可达性 `NOT TESTED`** |
| 7 | `KeyError` | zip 缺少 `[Content_Types].xml`；缺少 `xl/workbook.xml`；空 zip | `load_workbook` → `KeyError`（三者一致） | 真实 payload |
| 8 | `ValueError` | 需非法坐标/值域 | 本机未构造成功 | **注入等价验证；真实可达性 `NOT TESTED`** |
| 9 | `openpyxl.InvalidFileException` | `load_workbook(fileobj)` 路径 | 本机未命中（`PK` 非 zip → `BadZipFile`） | **注入等价验证；真实可达性 `NOT TESTED`（OPEN-T1）** |
| ✗ | `lxml.etree.XMLSyntaxError` | 把 `[Content_Types].xml` 的 `</Types>` 改坏 | `load_workbook` → **`lxml.etree.XMLSyntaxError`**（MRO：`SyntaxError` 子类，**不是** `ElementTree.ParseError`，也不是 `ValueError`） | **白名单未覆盖 → 预期逃逸为 500**，见 `TD-I-1` |

### TD-6 环境与可验证性检查（只读探测，输出如实抄录，2026-10-29）

| 探测项 | 命令 | 实际输出 | 结论 |
| --- | --- | --- | --- |
| 基线 HEAD / 工作区 | `git rev-parse --short HEAD`；`git status --porcelain` | `a6932c5`；`?? docs/features/F037/architecture.md` | 实现未开始；本 TD 依据 `a6932c5` |
| **真实 PostgreSQL** | `echo ${TEST_DATABASE_URL:-unset}`；`echo ${DATABASE_URL:-unset}` | `unset` / `unset` | **当前不可用** |
| PG 实例 | `docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'`；`docker info --format '{{.ServerVersion}}'`；`ss -ltnp \| grep -E '5432\|55432'` | 无容器输出；docker server `29.8.2`；无监听行 | 本机 docker 可用但**无运行中的 PG**；`compose.yaml` 的 `db` 服务无宿主端口且库名默认 `csm`（不含 `test`）⇒ **不能直接作测试库**（DB-D10 守卫 `assert "test" in database.lower()`） |
| 判定方式（TEST 阶段） | ① `echo ${TEST_DATABASE_URL:-unset}`；② 库名含 `test` 且 `!= DATABASE_URL`（conftest 双守卫，缺失即 `pytest.skip`）；③ `python3 -c "from sqlalchemy import create_engine; c=create_engine(URL).connect(); print(c.exec_driver_sql('select 1').scalar())"`；④ 设好后跑 architecture §10.9 命令。**不可用时 I 层全标 `NOT TESTED`，禁止以 SQLite/Mock 代替**（`implementation-rules.md` 验证与交付） | — | 本 TD 结论不受影响（设计可验证） |
| Python / 依赖 | `python3 -c "import openpyxl, sys; print(openpyxl.__version__)"`；`python3 -c "import pytest, sqlalchemy, fastapi; ..."`；`python3 -c "import psycopg; ..."` | `openpyxl 3.1.5`；`python 3.12.7`；`pytest 7.4.4 / sqlalchemy 2.0.34 / fastapi 0.115.14`；`psycopg 3.2.13` | U 层可执行；`lxml 5.2.1` 亦已安装（影响 `TD-I-1`） |
| CSV 上限 | `python3 -c "import csv; print(csv.field_size_limit())"` | `131072` | 输入 ① 以 131,073 字符单字段构造 |
| `/proc/self/fd` | `ls -d /proc/self/fd`；`python3 -c "import os; print(len(os.listdir('/proc/self/fd')))"` | 存在；`4` | `TD-F037-I21` 可执行；不可用则 `skip` 并登记 |
| `caplog` 可行性 | 既有用例 `tests/integration/test_auth.py:313`、`test_f017_tester_acceptance.py:478` 已用 `caplog.at_level`；`app/core/logging.py:62-70` 将 `SensitiveDataFilter` 挂 root，**无** `propagate=False`；全仓 `grep propagate` 无 logger 级关闭 | 命中如左 | `TD-F037-U12` 可执行（需 `caplog.set_level(logging.INFO, logger="csm.imports")`；若实现改 logger 名不判 FAIL，登记实际名） |
| 既有模块采集 | `python3 -m pytest --collect-only -q <module>` | `test_imports.py` 29；`test_f023_*` 28；`test_f034_csv_text_carrier.py` 29；`test_f034_*_scope` 2；`test_f035_append_*` 20；`test_f035_append_scope` 2；`test_f035_tester_acceptance` 16；`test_f036_attribution` 5；`test_f036_tester_independent` 5；`test_import_tester_acceptance` 9；`test_import_constraints` 4；`test_import_performance` 4；`test_f030_test_harness` 3；三模块合并 = `86 tests collected in 2.73s` | 回归基线可复现（R1–R6） |
| 500 可观察方式 | `grep -rn "raise_server_exceptions" tests/` | `test_auth.py:344`、`test_cluster_authorizations.py:957` | `TD-F037-I19` 用 `TestClient(auth_app, raise_server_exceptions=False)` 观察 500 信封，不用「异常外泄」冒充 |
| 既有 500 契约 | `app/core/errors.py:324-328` | `logger.exception("unhandled error: %s", type(exc).__name__)` + 固定 `Internal server error` 信封 | `TD-F037-I19` 期望体 = `{"error":{"code":"INTERNAL_ERROR","message":"Internal server error","details":{}}}` |

**TEST 阶段命令（从 `backend/`，architecture §10.9）**

```bash
export TEST_DATABASE_URL='postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/<db_with_test_in_name>'
python3 -m pytest tests/integration/test_f037_import_parse_errors.py -q
python3 -m pytest tests/integration/test_imports.py tests/integration/test_import_tester_acceptance.py \
                 tests/integration/test_import_constraints.py \
                 tests/integration/test_f023_resource_interface_ip_import.py -q            # R1+R2
python3 -m pytest tests/integration/test_f034_csv_text_carrier.py \
                 tests/integration/test_f034_csv_text_carrier_scope.py -q                # R3
python3 -m pytest tests/integration/test_f035_append_interface_ip_import.py \
                 tests/integration/test_f035_append_scope.py \
                 tests/integration/test_f035_tester_acceptance.py \
                 tests/integration/test_f036_attribution.py \
                 tests/integration/test_f036_tester_independent.py -q                     # R4
python3 -m pytest tests/integration/test_import_performance.py -q                           # R5
python3 -m pytest tests/integration/test_f030_test_harness.py -q                            # R6
# U 层无需数据库，可单独先跑（排除 I 层 marker 或用 -k 选择 TD-F037-U* 命名）
```

### TD-7 不可验证项、降级口径与登记项

**7.1 明确不可验证 / 不属本 Feature（TEST 阶段须如实标注，不得折算 PASS）**

| 项 | 标注 | 理由 |
| --- | --- | --- |
| 真实内存耗尽触发 `MemoryError` | **`NOT TESTED`** | 无法在不破坏宿主的前提下稳定制造；仅以注入证明分类边界（`TD-F037-U6`/`I19`）（architecture OPEN-T4） |
| 真实 `RecursionError` 由上传字节触发 | **`NOT TESTED`** | 无已知可构造输入；仅注入等价验证 |
| `zipfile.LargeZipFile` / `NotImplementedError` / `ValueError` / `InvalidFileException` 的**真实 payload 可达性** | **`NOT TESTED`** | 本机未构造成功（TD-5）；分类正确性以注入等价验证，真实可达性不宣称 |
| `validate` 的「不加锁」直接观测 | **`NOT TESTED`**（以 `S6` 静态替代） | `pg_locks` 采样不稳定（他连接干扰），易得假阳性；`test_validate_read_only_and_idempotent` 既有口径 + 计数 + 静态核查已覆盖 |
| 解析内存峰值 / 解压工作量边界（R05） | **`NOT_REQUIRED`** | 归 F038（product N7、plan revision 25 F038） |
| 前端 / 界面验证 | **`NOT_REQUIRED`** | `layers.frontend=false`；无任何前端文件改动（`S1` 守卫 `frontend` 零 diff）；载体行为由 F034 服务端等价性用例（R3）覆盖 |
| 数据库约束 / Migration | **`NOT_REQUIRED`** | `layers.database=false`；解析失败发生在任何 `begin_nested()` 之前；`docs/database/f014-import.md` v1 与 `f023-import.md` 的 `NOT_REQUIRED` 继续成立（本 TD 复核无新增写入路径） |
| 整体验收（需求 §31–33 跨功能） | **`NOT_REQUIRED`（本 Feature）** | 归后续整体验收（plan `acceptance.status=PENDING`，由 F045 变更集整体回归补充）；不得用本 Feature 局部 PASS 拼成整体 PASS |

**7.2 降级口径**

| 缺失项 | 受影响用例 | 标注 | 禁止做法 |
| --- | --- | --- | --- |
| 真实 PG 不可用（当前即此状态） | 全部 I 层（`I1–I21`）、R1–R6 | **`NOT TESTED`**（前置未满足），单列原因与已尝试命令 | 不得改用 SQLite / Mock / `db_session` 伪证；不得以 U、S 结果替代 |
| `/proc/self/fd` 不可读 | `I21` | `pytest.skip` + **`NOT TESTED`**，以 `U10` close 计数为替代证据 | 不得据「无报错」判无泄漏 |
| 实现未保留 `csm.imports` 日志（OPEN-T2） | `U12` | 断言切换为「无 `csm.imports` 记录即 PASS」 | 不得因日志缺失判 FAIL（日志非契约） |
| CONTRACT §6.2 附注未落稿 | `S4` | `BLOCKED`（契约输入缺失），其余用例可执行 | 不得跳过契约检查直接判 A21 PASS |

**7.3 登记 / 待裁定项（`TD-I-*`，不阻塞「可验证」结论）**

| ID | 内容 | Owner | 是否必须修复 |
| --- | --- | --- | --- |
| `TD-I-1` | **白名单覆盖缺口（本机实测）**：`openpyxl 3.1.5` + `lxml 5.2.1` 下，`[Content_Types].xml` 等部件由 **lxml** 解析，XML 结构损坏抛 `lxml.etree.XMLSyntaxError`（MRO 仅到 `SyntaxError`，**不是** `ElementTree.ParseError`，也不是 `ValueError`）⇒ architecture §3.1 白名单**不覆盖**，该类输入修复后仍为 500。属于 R-1「白名单过窄」的具体实例。请 Architect 裁定：① 扩展白名单（如 `lxml.etree.LxmlError` 或 `SyntaxError`，需评估后者的可观察副作用）；② 或在 §3.1 明确将「lxml 解析路径的 XML 损坏」排除并登记为既有残余（则 R-1 矩阵中该行用例标 `NOT TESTED` 并写明理由）。**A1–A8 不受影响**（输入 ①② 实测分别落在 `csv.Error` 与 `ElementTree.ParseError`）。**状态（2026-10-29 更新）**：Architect 已在 CONTRACT Gate 裁定 `lxml.etree.LxmlError` 条件入表（architecture §15.1/§15.2、DR-F037-07）⇒ 本项**关闭**；TEST 以新增 `TD-F037-U15`（输入 ③ 裸类型随 `openpyxl.LXML`、收敛结果不变）+ `I23`（4 端点 × 输入 ③）+ `U4` 第 10 类实测 | Architect | 已裁定并关闭（本轮实测 PASS） |
| `TD-I-2` | 输入 ① 字节数口径：product/plan 写「131,082 B」，本机按 architecture §10.2 构造得 131,229 B（BM 14 列）/ 131,336 B（26 列）。本 TD 只用不变量（`>131_072` 且 `≤5_242_880`）+ 实测值，**不**硬编码 131,082 | Product（确认即可） | 否（登记口径） |
| `TD-I-3` | `csm.imports` 两条 content-free INFO 日志是否保留（architecture OPEN-T2）。本 TD 的 `U12` 判据与日志存在性解耦：存在则校验字段受限，不存在则断言无记录 | 协调器 / 运维 | 否 |
| `TD-I-4` | `ValueError` / `KeyError` 入白名单偏宽（所有 `ValueError` 在 `with` 内都被转为 `unreadable`）：以 `U11`（作用域最小性）+ `S3`（`except` 子句形态）共同约束，不放宽到 `except Exception` | Backend（实现登记） | 否 |
| `TD-I-5` | `InvalidFileException` 在 `load_workbook(fileobj)` 路径本机未命中（`PK` 非 zip → `BadZipFile`，与 architecture OPEN-T1 一致）。删除或保留该 `failures=` 项**不改变**任何已设计断言；TEST 只做注入等价验证 | Backend | 否 |
| `TD-I-6` | **A18 判据纪律**：`core/errors.py` 的 500 handler 使用 `logger.exception`（含 traceback），`TD-F037-I19` 注入的自定义异常消息会进入日志。故 A18 的 `caplog` 守卫**只**覆盖 422 拒绝路径（`U12`），不把 500 注入用例的 traceback 计入判据；`I19` 亦不使用含上传内容的 marker | Tester（本 TD 已固定） | 否（判据已固定） |
| `TD-I-8` | **测试设计更正（architecture §15.7 登记，本轮已按修订执行）**：原「空 zip（无 worksheet）→ `empty_file`」期望不成立——零成员 zip 的 magic 是 `PK\x05\x06`，先被 PK 闸门拒绝 ⇒ `unsupported_format`；`empty_file` 须用**合法 xlsx 容器但 `workbook.worksheets` 为空**（删除 `xl/worksheets/sheet1.xml` 成员）构造。`TD-F037-U9` 的期望已按此修订并在 TEST 中实测（零成员 zip 22 B → `unsupported_format`；缺 sheet 部件 → `empty_file`） | Tester（本轮闭环） | 否（已修订并实测） |
| `TD-I-7` | TEST 环境需一个**独立、库名含 `test`** 的 PostgreSQL（`compose.yaml` 的 `db` 无宿主端口且库名 `csm`，会被 DB-D10 守卫拒绝）。当前无运行实例（TD-6）。建议协调器在 TEST 前提供，例如 `docker run --rm -d --name csm-f037-pg -e POSTGRES_PASSWORD=... -e POSTGRES_DB=csm_test -p 127.0.0.1:55433:5432 postgres:16`（仅为环境建议，不属设计裁定） | 协调器 | 是（否则 I 层与 R1–R6 全部 `NOT TESTED`） |

### TD-8 数据完整性映射（data-integrity 口径）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据（设计） |
| --- | --- | --- | --- | --- | --- |
| §24-2 / T27 / T123 整批原子、拒绝零残留 | 4 端点写入 | 单事务 + 逐行 SAVEPOINT（**不变**） | 解析失败发生在任何 `begin_nested()` 之前 ⇒ 提前失败，无部分写入 | 无需并发场景（失败点在取锁前） | `I9`（7 表零变化）、`I15`、`U9` |
| §22 Audit 同事务、每对象 CREATE | 4 端点写入 | `audit_logs` append-only | 拒绝路径不写 Audit | — | `I9`（`audit_logs` 不变 = Activity 不变）、`I20` |
| §24.5 / T107–T116 双载体等价 | CSV 文件/文本载体 | — | 载体只决定 multipart 形状，转换发生在字节入口之后 | — | `I17`、`R3`（31 项） |
| §7 同 cluster hostname 未删唯一 等 | 4 端点 | 三条部分唯一索引（**不变**） | 逐行校验（**不变**） | 不触碰 | `R1`/`R2`/`R4`（既有约束用例） |
| 1-based 行号 / `RowError` 形状 | 4 端点 | — | 物化解析列表索引（**不变**，L1「不引入流式」） | — | `I16`、`R3`（`T113` 行号/尾部空行） |
| F014/F023 拒绝原因保真（B6） | 4 端点 | — | `except AppError: raise` 先于白名单 | — | `U5`、`I12`、`I13` |

**Database：`NOT_REQUIRED`** —— 本 Feature 零 DDL、零事务边界变化；上表各项均为「不变量复核」，不主张「新增约束已验证」。

### TD-9 结论

**`TEST DESIGN READY`**

- A1–A22 全部映射到 **34 条** `TD-F037-*` 用例（U 12 / I 21 / S 6，其中 `I21` 为 fd 检测）与 **6 条**回归执行项（R1–R6，基线计数 `42 / 28 / 31 / 48 / 4 / 3`），每条给出环境层、前置夹具、断言要点与 T 条目映射。
- 两类输入的可构造性已在本机**实测证明**（输入 ① 131,229 B / 131,336 B 且必抛 `csv.Error`；输入 ② 5,029 B、`load_workbook` 成功且 `iter_rows` 抛 `ElementTree.ParseError`），并固化了不变量（字节区间、PK 魔数、表头列数、zip 成员名）与「构造失效即 BLOCKED、不得改判 PASS」的硬前置。
- 边界与反向场景齐备：`empty_file`、`unsupported_format`（含 `.xls` OLE2 与 `PK` 非 zip 对照）、表头/列类 `reason` 与 413/表头顺序、413 字节与 413 行数、行级 `RowError` 形状着色、401/403 先行、双载体逐字段等价、`close` 异常不覆盖已判定 422、未白名单异常不转换。
- 环境如实记录：**当前无真实 PostgreSQL**（`TEST_DATABASE_URL` 未设、无运行实例、compose `db` 不满足 DB-D10）⇒ I 层与 R1–R6 在 TEST 阶段无库即 `NOT TESTED`，不得以 SQLite/Mock 代替；`/proc/self/fd` 可用（fd=4）；`caplog` 有既有先例可用。
- 探测发现 **1 项架构白名单缺口**（`TD-I-1`：`lxml.etree.XMLSyntaxError` 未覆盖，本机实测可达）与 6 条口径/环境登记项，均**不构成不可验证项**，故不返回 `TEST DESIGN BLOCKED`；请 Architect 在 CONTRACT Gate 一并裁定 `TD-I-1`。
- 本阶段**未执行**任何测试、构建或 Git 变更命令；`TEST DESIGN READY` 不批准实现、Contract 定稿或合并，也不代表任何验收项已通过。

GIT（TEST DESIGN 阶段，2026-10-29，均为只读）：`git rev-parse --short HEAD`、`git status --porcelain`、`git diff --stat`、`git diff -U0`、`grep`/`ls`/`docker ps`/`python3 -c` 探测；无 Git 写操作。

---

## 2. Test Execution（TE-F037-1，v1，2026-10-29）

### TE-1 Task / Status / Basis

- **Task**：F037「导入解析异常统一收敛为 422 `IMPORT_INVALID_FILE`」TEST 阶段（独立执行）。写面仅 `backend/tests/integration/test_f037_import_parse_errors.py`（新建）与本文件；零生产代码 / 契约 / 计划改动，零 Git 写操作。
- **Status**：**`READY FOR REVIEW`** —— 新增模块 **52/52 PASS**（U 23 / I 23 / S 6，含 BE-01 与输入 ③ 补充）；回归 **R1–R6 全部实跑通过**（42 / 28 / 31 / 48 / 4 / 3），无必须修复缺陷。
- **Basis**：`docs/features/F037/product.md` v1（A1–A22、B1–B12）；`docs/features/F037/architecture.md` v1 §10（测试输入）+ §15.1–§15.9（CONTRACT：`TD-I-1` 裁定、输入 ③、11 类）+ **§15.10（BE-01 / DR-F037-08 / L7′）**；§1 TEST DESIGN `TD-F037-1`；`docs/features/F037/implementation.md` v1 + §9（Repair round 1）；`docs/api/F014.md` v1 §1.2、`docs/api/F023.md` v2 §1.2；`requirements-v3.md` revision 16 §24 / §24.1 / §24.5 / §24.6 / §22 / §31（T27、T28、T72、T107–T116、T124、T126）；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`。
- **测试基线**：HEAD `dec9445`（`feat(F037): converge parse-stage errors to 422 IMPORT_INVALID_FILE`）+ 工作区未提交的 BE-01 修复（`resource_import.py` `failures` 元组新增 `OSError`，10 insertions / 1 deletion）+ 本模块（未跟踪新文件）。真实验证对象为**工作区当前代码**，即 Backend 声明的 BE-01 完成态。

### TE-2 Environment（实测，逐项抄录）

| 项 | 实际值 | 取得方式 |
| --- | --- | --- |
| Python | `3.12.7` | `pytest` 会话头 / `sys.version` |
| pytest | `7.4.4`（pluggy 1.0.0） | 会话头 |
| `openpyxl.__version__` | **`3.1.5`** | `python3 -c "import openpyxl; print(openpyxl.__version__)"` |
| `openpyxl.LXML` | **`True`**（`fromstring` 走 lxml，`iterparse` 恒为 ET） | 同上（报告结论仅适用于本后端形态，不外推到无 lxml 镜像） |
| `lxml.__version__` | **`5.2.1`** | `python3 -c "import lxml; print(lxml.__version__)"` |
| `csv.field_size_limit()` | `131072` | `python3 -c "import csv; print(csv.field_size_limit())"` |
| `TEST_DATABASE_URL` | `postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test`（driver `postgresql+psycopg`，host `127.0.0.1`，port **55432**，db `csm_f037_test`） | `echo $TEST_DATABASE_URL` + `make_url(...)` 解析打印 |
| 数据库 | 容器 `csm-f037-pg`，镜像 **`postgres:16-alpine`**，`Up 30 minutes`，`0.0.0.0:55432->5432/tcp`；`show server_version` = **`16.15`** | `docker ps --filter name=csm-f037-pg`；`show server_version` |
| DB-D10 守卫 | 库名含 `test` = `True`；`DATABASE_URL` 未设（`False`）⇒ 双守卫均满足；**未接触生产/未知库** | conftest 断言 + 显式打印 |
| Schema 状态 | 会话级 fixture 每轮 `DROP SCHEMA public CASCADE` → `alembic upgrade head`（15 个修订：`0001_baseline` … `0015_user_cluster_authorizations`），结束后重建空 schema | 会话日志（`alembic.runtime.migration ... 0015`），跑后 `pg_tables` 计数 0 |
| `/proc/self/fd` | 可用（`TD-F037-I21` 实跑，未 skip） | 用例内 `Path('/proc/self/fd').is_dir()` |

### TE-3 执行命令与结果计数（全部为本轮真实输出）

| 编号 | 命令（cwd `backend/`，均带 `TEST_DATABASE_URL`，除 E3） | 实际结果 |
| --- | --- | --- |
| **E1** | `python3 -m pytest tests/integration/test_f037_import_parse_errors.py -q` | **`52 passed in 20.32s`** |
| **E2** | 同 E1 再跑一次（`-v --tb=short`，验证可独立重复执行与无残留） | **`52 passed in 14.68s`**，无 skip、无 xfail |
| E3 | `env -u TEST_DATABASE_URL python3 -m pytest tests/integration/test_f037_import_parse_errors.py -q` | `29 passed, 23 skipped in 1.08s`（U+S 无库可跑；23 项 I 层按 DB-D10 守卫 `skip`，证明用例未以 SQLite/Mock 伪证） |
| R1a | `python3 -m pytest tests/integration/test_imports.py -q` | `29 passed in 25.24s` |
| R1b | `python3 -m pytest tests/integration/test_import_tester_acceptance.py tests/integration/test_import_constraints.py -q` | `13 passed in 10.92s` |
| R2a | `python3 -m pytest tests/integration/test_f023_resource_interface_ip_import.py -q --deselect tests/integration/test_f023_resource_interface_ip_import.py::test_perf03_near_max_rows_baseline` | `27 passed, 1 deselected in 30.55s` |
| R2b | `python3 -m pytest tests/integration/test_f023_resource_interface_ip_import.py::test_perf03_near_max_rows_baseline -q -s`（单独重跑，见 TE-6.6） | **`1 passed in 342.25s`**；`[PERF-03] file=320476B rows=5000 validate=42.15s validate_peak=8.1MB write=308.70s write_peak=13.9MB` |
| R3 | `python3 -m pytest tests/integration/test_f034_csv_text_carrier.py tests/integration/test_f034_csv_text_carrier_scope.py -q` | `31 passed in 53.62s`（含 `test_td3_t114_field_boundaries` 等重点项） |
| R4a | `python3 -m pytest tests/integration/test_f035_append_interface_ip_import.py tests/integration/test_f035_append_scope.py tests/integration/test_f035_tester_acceptance.py -q` | `38 passed in 46.96s` |
| R4b | `python3 -m pytest tests/integration/test_f036_attribution.py tests/integration/test_f036_tester_independent.py -q` | `10 passed in 11.71s` |
| R5+R6 | `python3 -m pytest tests/integration/test_f030_test_harness.py tests/integration/test_import_performance.py -q` | `7 passed in 76.72s`（F030 门禁 3 + 性能 4） |

> 计数与 §1 基线一致：R1 = 29+13 = **42**；R2 = 27+1 = **28**；R3 = **31**；R4 = 38+10 = **48**；R5 = **4**；R6 = **3**。**无一项低于 §1 采集的基线**。

### TE-4 逐用例结果（52 项，全部 PASS）

模块：`backend/tests/integration/test_f037_import_parse_errors.py`（U + I + S 同模块，沿用 `test_f023_*` 先例；不导入 `app.core.access_scope` 符号 ⇒ 按 F030 §9.1 不需 `pytest.mark.real_scope`，`test_f030_test_harness.py` AST 门禁实跑通过）。

| 用例（测试函数 / 参数） | 层 | 对应 TD / 依据 | 结果 |
| --- | --- | --- | --- |
| `u1_oversized_csv_really_fails_during_parse[bm14]` / `[w26]` | U | `TD-F037-U1`、architecture §10.2 | **PASS** ×2 |
| `u2_corrupt_sheet_tail_really_fails_during_parse` | U | `TD-F037-U2`（口径见 TE-7） | **PASS** |
| `u15_manifest_corruption_converges_on_both_backends` | U | §15.8.1（输入 ③，`TD-I-1`） | **PASS** |
| `u3_whitelisted_real_payloads_keep_reason_and_cause` | U | `TD-F037-U3`（8 类真实 payload） | **PASS** |
| `u4_whitelist_covers_eleven_classes` | U | `TD-F037-U4` + §15.10.7-2（11 类） | **PASS** |
| `u5_app_error_reason_fidelity` | U | `TD-F037-U5`（B6） | **PASS** |
| `u6_memory_and_recursion_errors_propagate[MemoryError]` / `[RecursionError]` | U | `TD-F037-U6`（B7） | **PASS** ×2 |
| `u7_interrupt_semantics_unchanged[KeyboardInterrupt]` / `[SystemExit]` | U | `TD-F037-U7`（`SystemExit.code == 3` 已断言） | **PASS** ×2 |
| `u8_u16_non_whitelisted_errors_propagate[AttributeError/TypeError/IndexError/AssertionError/OverflowError/SyntaxError]` | U | `TD-F037-U8` + §15.8.4 负向守卫 | **PASS** ×6 |
| `u9_decision_order_and_materialised_result` | U | `TD-F037-U9`（含 `TD-I-8` 修订） | **PASS** |
| `u10_close_lifecycle_and_no_override` | U | `TD-F037-U10`（R-2；close 1/1/0 次） | **PASS** |
| `u11_cell_text_errors_stay_outside_the_conversion_scope` | U | `TD-F037-U11`（R-9） | **PASS** |
| `u12_parse_logging_is_content_free` | U | `TD-F037-U12`（A18 前半） | **PASS**（非空跑：实测捕获 3 条 `csm.imports` 记录） |
| `u13_missing_workbook_part_converges` | U | `TD-F037-U13`（§15.10.7-1 / BE-01） | **PASS** |
| `u14_oserror_scope_is_minimal` | U | `TD-F037-U14`（§15.10.7-3 / R-12） | **PASS** |
| `i1_i8_parse_failure_is_422_at_every_endpoint[I1…I8]` | I | `TD-F037-I1…I8`（A1–A8 + A20 前置，同字节重发同体） | **PASS** ×8 |
| `i9_rejected_write_leaves_no_residue` | I | `TD-F037-I9`（A9；7 表计数逐表不变） | **PASS** |
| `i10_auth_and_permission_precede_parsing` | I | `TD-F037-I10`（A10 / B10；8×401 + 8×403） | **PASS** |
| `i11_byte_limit_still_wins` | I | `TD-F037-I11`（A11 / B4） | **PASS** |
| `i12_empty_file_reason_not_converged` | I | `TD-F037-I12`（A12 / B1；8 请求） | **PASS** |
| `i13_unsupported_format_not_converged` | I | `TD-F037-I13`（A13 / B2） | **PASS** |
| `i14_header_and_column_reasons_unchanged` | I | `TD-F037-I14`（A14 / B3；含「行数 413 先于表头 422」） | **PASS** |
| `i15_row_limit_413_without_partial_import` | I | `TD-F037-I15`（A15；5001 行 → 413 + 零写入） | **PASS** |
| `i16_row_errors_shape_and_one_based_rows` | I | `TD-F037-I16`（A16 / B5；`RowError` 4 键、`row=3`、批量零残留） | **PASS** |
| `i17_dual_carrier_equivalence` | I | `TD-F037-I17`（A17 / B9 / T114） | **PASS** |
| `i18_response_body_is_content_free` | I | `TD-F037-I18`（A18 后半；4 端点 × 2 输入） | **PASS** |
| `i19_internal_errors_stay_500` | I | `TD-F037-I19`（B7/B8；`MemoryError` 注入 → 500 信封） | **PASS** |
| `i20_repeated_validate_is_idempotent_and_read_only` | I | `TD-F037-I20`（A20 / T116） | **PASS** |
| `i21_no_file_descriptor_leak` | I | `TD-F037-I21`（R-5；未 skip） | **PASS** |
| `i22_missing_workbook_part_is_422_at_every_endpoint` | I | `TD-F037-I22`（§15.10.7-4 / BE-01） | **PASS** |
| `i23_corrupt_manifest_is_422_at_every_endpoint` | I | §15.8.2（输入 ③ × 4 端点，TD 新增） | **PASS** |
| `s2_caps_and_csv_strictness_unchanged` | S | `TD-F037-S2` | **PASS** |
| `s3_logging_shape_and_classification_boundary` | S | `TD-F037-S3` | **PASS** |
| `s5_only_signed_reasons_and_frozen_templates` | S | `TD-F037-S5` | **PASS** |
| `s6_validate_path_has_no_locks_or_commits` | S | `TD-F037-S6` | **PASS** |
| `s7_oserror_is_local_to_parse_xlsx` | S | `TD-F037-S7`（§15.10.7-5 / L7′） | **PASS** |
| `s8_lxml_stays_an_optional_dependency` | S | §15.8.5（lxml 不落依赖、仅 `resource_import.py` 条件导入） | **PASS** |

合计：**52 passed / 0 failed / 0 skipped / 0 xfail**（E1、E2 两次独立运行一致）。

### TE-5 验收映射（A1–A22，逐项裁决）

| 验收 | 判定 | 证据（用例 / 命令） |
| --- | --- | --- |
| A1 / A2（资源导入 `validate` × 输入 ①②） | **PASS** | `I1`、`I2` |
| A3 / A4（资源导入写入 × 输入 ①②） | **PASS** | `I3`、`I4` |
| A5 / A6（F023 `validate` × 输入 ①②） | **PASS** | `I5`、`I6` |
| A7 / A8（F023 写入 × 输入 ①②） | **PASS** | `I7`、`I8` |
| A9（写入路径零残留，含 Audit / Activity） | **PASS** | `I9`（`clusters/resources/bare_metal_details/virtual_machine_details/interfaces/ip_addresses/audit_logs` 7 表计数逐表不变；Activity 无独立表、由 `audit_logs` 派生 ⇒ `audit_logs` 不变即同时覆盖 Activity，**未**检查任何「activity 表」） |
| A10（401 / 403 先行） | **PASS** | `I10`（未登录 4 端点全 401 `AUTH_REQUIRED`；VIEWER 全 403 `FORBIDDEN{reason:"permission"}`；无 422/500） |
| A11（413 不被 422 取代；输入 ① 必须越过 413） | **PASS** | `I11`（`import_max_file_bytes=10` → 4×413 `{limit_bytes:10}`；默认 → 4×422） |
| A12（`empty_file` 不被收敛） | **PASS** | `I12`（空字节与仅表头 × 4 端点，`details` 恰 `{"reason":"empty_file"}`） |
| A13（`.xls`/非 OOXML → `unsupported_format`；PK 非 zip → `unreadable`） | **PASS** | `I13` |
| A14（表头/列类 reason 与顺序不变） | **PASS** | `I14`（`header_missing`/`missing_columns`/`unknown_columns`/`column_order` + 行数 413 先于表头 422）；R1a 的 `test_header_errors`、`test_validation_order_row_limit_before_header` 同时通过 |
| A15（5001 行 → 413，无部分导入） | **PASS** | `I15`（4 端点 + 计数不变） |
| A16（行级 `RowError` 形状与 1-based 行号） | **PASS** | `I16`（`{"row","field","reason","related_row"}` 且 `row==3`；写入 422 `IMPORT_VALIDATION_FAILED` 5 键 details；批量零残留） |
| A17（双载体等价） | **PASS** | `I17`（4 端点 × 文件/文本载体，状态码相同 + `json()` 深等）；R3 的 F034 31 项全绿（含 `test_td3_t114_field_boundaries`） |
| A18（响应体 / 日志不含上传内容） | **PASS** | `I18`（marker、`<worksheet`、`mismatched tag`、`field larger than field limit`、`Traceback`、`.py` 0 命中）+ `U12`（实捕获 3 条记录，`args` 仅 `format`/`bytes`/异常类名，`exc_info is None`） |
| A19（不吞异常守卫） | **PASS** | `U3`/`U4`/`U5`/`U6`/`U7`/`U8`/`U13`/`U14`/`U15`/`U16` + `I19`（注入 `MemoryError` → 4 端点 500 `INTERNAL_ERROR`，非 422） |
| A20（重复 `validate` 一致、无副作用、不加锁） | **PASS** | `I20`（两次响应逐字段相同、7 表计数不变）+ `S6`（解析/预校验区间无 `for_update`/`begin_nested`/`commit`）；锁语义仍不以 `pg_locks` 断言（`TD-I-6` 口径） |
| A21（契约与常量守卫） | **PASS** | `S2`（无 `field_size_limit`/`strict=True`/`csv.QUOTE`；5 242 880 / 5000 / 1000 不变）+ `S3`（无 `logger.exception|error`、无 `filename`/`exc_info`；分类边界恰 `AppError` + `failures`）+ `S5`（`ImportInvalidFile` 字面 `reason` ⊂ 已签核集合；BM 14 / VM 10 列序冻结）+ `S7`/`S8`；命令侧见 TE-6.5（`git diff` 收口、F014 仍 v1 / F023 仍 v2） |
| A22（回归 T27/T28/T72、T107–T116 含 T114、T124/T126） | **PASS** | R1–R6（TE-3），全部实跑通过 |

**无 FAIL / BLOCKED。** 未执行项见 TE-9。

### TE-6 关键证据（真实输出）

**6.1 输入构造的有效性与不变量（`TD-F037-U1`/`U2`/§15.8.1）**

```text
input1 bm14 bytes 131229     input1 w26 bytes 131336     (131_072 < len <= 5_242_880)
  raw csv.reader  -> _csv.Error: field larger than field limit (131072)
input2 bytes 5029 / 5030(含 marker)   startswith PK\x03\x04
  load_workbook(read_only=True,data_only=True) OK, sheetnames ['Sheet']
  iter_rows -> xml.etree.ElementTree.ParseError: mismatched tag: line 1, column 1683
input3(manifest corrupt '</Types>'->'</Typse>') bytes 5029
  load_workbook -> lxml.etree.XMLSyntaxError   (openpyxl.LXML=True ⇒ 走 lxml)
BE-01 缺 workbook 部件 zip bytes 535;  bare load_workbook -> OSError('File contains no valid workbook part')
零成员 zip bytes 22, magic PK\x05\x06 (⇒ PK 闸门 unsupported_format)
```

`__cause__` 逐类实测（`U3`/`U4`/`U9`/`U13`/`U15`）：

| 输入形态 | 收敛结果 | `type(__cause__)` | 真实 payload? |
| --- | --- | --- | --- |
| CSV 单字段超限 | 422 `unreadable` | `_csv.Error` | 是 |
| `PK\x03\x04` 非 zip / zip 截断 | 422 `unreadable` | `zipfile.BadZipFile` | 是 |
| sheet 部件 deflate 首字节损坏 | 422 `unreadable` | `zlib.error` | 是 |
| sheet XML 结束标签损坏 | 422 `unreadable` | `ElementTree.ParseError` | 是 |
| 缺 `[Content_Types].xml` | 422 `unreadable` | `KeyError` | 是 |
| 非法单元格坐标 `r="??"` | 422 `unreadable` | `ValueError` | 是 |
| `[Content_Types].xml` 结构损坏 | 422 `unreadable` | `lxml.etree.XMLSyntaxError` | 是（输入 ③） |
| 缺 workbook 部件（BE-01） | 422 `unreadable` | `OSError` | 是 |
| `InvalidFileException` / `LargeZipFile` / `NotImplementedError` | 422 `unreadable` | 同名类 | **否（注入等价验证）** |

`_PARSE_FAILURES` 实测 8 项（`Error`/`BadZipFile`/`LargeZipFile`/`error`(zlib)/`ParseError`/`NotImplementedError`/`KeyError`/`ValueError`），`OSError` **不在**其中（仅 `_parse_xlsx` 局部）；`.xlsx` 有效白名单 11 类（8 + `InvalidFileException` + 条件 `LxmlError` + `OSError`）。

**6.2 日志 content-free 实测（`U12` 非空跑）**

```text
csm.imports | import parse rejected: format=csv  bytes=131229 error=Error
csm.imports | import parse rejected: format=xlsx bytes=5055   error=ParseError
csm.imports | import parse rejected: format=xlsx bytes=5029   error=XMLSyntaxError
args=('csv', 131229, 'Error') / ('xlsx', 5055, 'ParseError') / ('xlsx', 5029, 'XMLSyntaxError') | exc_info=None
```
marker（`F037-MARKER-…`）、`<worksheet`、`mismatched tag`、`field larger than field limit`、`Traceback`、客户端文件名均 0 命中。

**6.3 fd 泄漏（`I21`）**：同一进程连续 20 次提交损坏 xlsx，`len(os.listdir('/proc/self/fd'))` 前后不增长（断言 `after <= before`，用例 PASS，未 skip）。

**6.4 缺陷可检测性（负向对照，不改生产文件）**：把 `_invalid_file_on_parse_failure` 临时替换为「不转换」的 passthrough 后，四个样本全部以原始解析器异常逃逸（即修复前的 500 路径）：

```text
input1-csv     -> escapes as _csv.Error
input2-xlsx    -> escapes as xml.etree.ElementTree.ParseError
input3-manifest-> escapes as lxml.etree.XMLSyntaxError
be01-no-workbook-> escapes as builtins.OSError
```
⇒ 新增用例对「回归到 500」的缺陷是敏感的（不是空跑断言）。

**6.5 静态 / 契约守卫（命令侧，cwd 仓库根）**

```text
$ git diff --stat -- backend/app/services/resource_import.py
 backend/app/services/resource_import.py | 11 ++++++++++-      (1 file changed, 10 insertions(+), 1 deletion(-) 工作区 BE-01)
$ git diff --stat -- backend/app/services/resource_interface_ip_import.py backend/app/api backend/app/core backend/app/models backend/alembic frontend
(空)                                        # core/errors.py、F023 service、路由、models、alembic、frontend 零 diff
$ git status --porcelain --untracked-files=all   (非 M 行)
?? backend/tests/integration/test_f037_import_parse_errors.py   # 唯一新增文件
$ git diff -U0 1c0eeaf -- backend/app/services/resource_import.py | grep -nE 'field_size_limit|strict=True|import_max_'
no cap/strict change
$ grep -rn "field_size_limit\|csv.QUOTE" backend/app
(无命中)
$ grep -nE 'logger\.(exception|error)\(' backend/app/services/resource_import.py
no exception logging
$ grep -n 'filename\|exc_info' backend/app/services/resource_import.py
no filename/exc_info
$ grep -nE 'except SyntaxError|except Exception' backend/app/services/resource_import.py
476:  except Exception as exc:   # _close_workbook 清理边界（既有）
509:  # 注释文本命中（OSError 说明，非代码）
1019: except Exception:          # write_import 回滚边界（既有）
$ git diff 1c0eeaf -- docs/api/F014.md docs/api/F023.md
共 4 行落稿：F014 §1.2 一条 bullet + 修订表一行；F023 v2 §1.2 一条 bullet + 修订表一行
$ head -4 docs/api/F014.md   -> - **版本**：v1          (未升版)
$ head -4 docs/api/F023.md   -> - **版本**：v2（2026-10-26…）(未升版)
$ git diff --stat 1c0eeaf -- docs/api/F002.md
(空)                          # 无新 reason / 错误码 / details 键 / 上限
```
注：`S1`/`S4` 依赖 Git 状态，不在 pytest 内断言（以本表命令为证据）；`S2`/`S3`/`S5`/`S6`/`S7`/`S8` 另有 pytest 守卫（`TE-4`），两者结论一致。

**6.6 `test_perf03_near_max_rows_baseline` 的独立归因（本 Tester 自己的结论）**

- **事实**：Backend §9.5 记录该用例失败（`write=685.48s > 600`）；我在同一容器、同一 commit + 同一工作区代码上**单独重跑，结果为 `1 passed in 342.25s`**（`write=308.70s < 600`，`validate=42.15s`）。两次相差 **2.22×**（write）/ **2.83×**（validate），代码完全相同 ⇒ 测点读数随宿主负载/容器 I/O 大幅波动。
- **代码侧证据**：`git diff 1c0eeaf -- backend/app/services/resource_import.py` 的功能改动只在 `_parse_xlsx` 的 `failures` 元组（新增 `OSError`）与注释；`write_import`、`parse_and_validate`、逐行校验、DB 访问与锁序**零 diff**（`S6` 与上表 diff 双证）。该用例 685 s 的耗时发生在 `unified.write_import`（5000 行 × resource/interface/ip + 3 条 Audit 的单事务），与解析异常白名单无调用关系。
- **量化**：同一 320,476 B / 5000 行 payload 上，`parse_records`（含转换上下文与新增元组）耗时 `17.3 / 17.8 / 14.5 ms`（三次），裸 `csv.reader` 遍历 `18.6 ms`；新增的 `_PARSE_FAILURES + (InvalidFileException, OSError)` 元组构造 **0.27 µs/次**。即改动对整条路径的贡献约 **10⁻⁷ 量级**，不可能解释 600 s 级阈值跨越。
- **结论（我的独立判断）**：该失败**与本改动无因果关系**，是**宿主/容器负载导致的测点波动**（Backend 归因方向成立，但「本机性能」应更准确地表述为「随负载波动、非稳定复现」——本轮已实测通过）。
- **后续处置**：登记为**已知限制**（该阈值对宿主负载敏感；600 s 为「宽松 sanity ceiling」）；**不修改**测试阈值或测试语义，不改生产代码；若后续在 CI 稳定复现再评估是否另立提案（Owner：协调器；非 F037 缺陷）。

### TE-7 与 §1 TEST DESIGN 的差异（本轮口径修订，均已在代码与结果中体现）

| 条目 | §1 设计期表述 | TEST 实施口径 | 依据 / 影响 |
| --- | --- | --- | --- |
| `TD-F037-U9`（空 zip） | 「空 zip（无 worksheet）→ `empty_file`」 | **零成员 zip**（magic `PK\x05\x06`）→ `unsupported_format`；`empty_file` 用**合法容器缺 worksheet 部件**构造 | architecture §15.7 `TD-I-8` 更正；不改变设计或契约（`§1` 该行已同步修订） |
| `TD-F037-U2`（`parse_records` 期望） | 「`parse_records` 抛同一类型（`ElementTree.ParseError`）」（修复前基线） | 有效性仍由**裸 `load_workbook` / `iter_rows`** 三步证明；收敛后 `parse_records` 断言 `ImportInvalidFile{unreadable}` + `__cause__ is ElementTree.ParseError` | 修复已落地，§1 原文为「改前缺陷基线」；按修复后语义断言，前置证明未削弱 |
| `TD-F037-U4`（白名单参数化） | 9 类 | **11 类**（+ 条件 `LxmlError`、+ `OSError`），真实 payload 优先、注入兜底 | architecture §15.8.3 / §15.10.7-2 / §15.10.2 |
| 新增 `TD-F037-U15` / `I23` / `S8` | 无 | 输入 ③（`[Content_Types].xml` 损坏）的有效性 + 4 端点 + lxml 可选依赖守卫 | architecture §15.8.1 / §15.8.2 / §15.8.5 |
| 新增 `TD-F037-U16` | `U8` 未含 `SyntaxError` | 参数化并入 `U8`（`SyntaxError` 行），验证「未用 `except SyntaxError`」 | architecture §15.8.4 |
| 新增 `TD-F037-U13` / `U14` / `I22` / `S7` | 无 | BE-01 真实 payload 收敛、`OSError` 作用域最小性、4 端点、静态守卫（L7′） | architecture §15.10.7 |
| 载体常量 | 「复用 F034 常量」 | 本模块内以同值常量定义（`csm-pasted-import.csv` / `text/csv;charset=utf-8` / `f037-file-carrier.csv` / `text/csv`），不跨测试模块导入 | 保持模块独立、避免耦合；值来源 F034 `importCarrier.ts` |

### TE-8 回归结果（TE-3 明细的裁决）

| 项 | 套件 | 结果 | 重点项 |
| --- | --- | --- | --- |
| R1 | `test_imports.py`(29) + `test_import_tester_acceptance.py`(9) + `test_import_constraints.py`(4) | **42 PASS** | `test_header_errors`、`test_format_and_file_level_errors`、`test_file_size_and_row_limits`、`test_validation_order_row_limit_before_header`、`test_permission_matrix`、`test_templates_spec_and_read_permission` |
| R2 | `test_f023_resource_interface_ip_import.py`(28) | **28 PASS**（27 + perf03 单独重跑通过） | `test_reg02_route_inventory` 通过 ⇒ 路由清单不变 |
| R3 | `test_f034_csv_text_carrier.py`(29) + `_scope.py`(2) | **31 PASS** | `test_td3_t114_field_boundaries`（T114 字段边界等价）通过；未改写 F034 corpus |
| R4 | `test_f035_append_interface_ip_import.py`(20) + `test_f035_append_scope.py`(2) + `test_f035_tester_acceptance.py`(16) + `test_f036_attribution.py`(5) + `test_f036_tester_independent.py`(5) | **48 PASS** | 追加路径、归因口径不变（T124） |
| R5 | `test_import_performance.py`(4) | **4 PASS** | 上限拒绝与预览截断口径不变（未新增阈值） |
| R6 | `test_f030_test_harness.py`(3) | **3 PASS** | 新模块未触碰 `access_scope` 符号，AST 门禁通过 |

### TE-9 未执行 / 不可验证项（明示，不计入 PASS）

| 项 | 标注 | 原因 |
| --- | --- | --- |
| 无 lxml 环境（`openpyxl.LXML=False`，生产镜像形态） | **NOT TESTED** | 本机 `LXML=True`；`U15` 已按分支断言实现（`expected_manifest_error_type()`），但仅 True 分支实测。结论**不外推**（R-11 / OPEN-T5） |
| 真实内存耗尽触发 `MemoryError` / 真实 `RecursionError`（由上传字节触发） | **NOT TESTED** | 无法在宿主上稳定制造；仅注入证明分类边界（OPEN-T4） |
| `zipfile.LargeZipFile` / `NotImplementedError` / `InvalidFileException` 的**真实 payload 可达性** | **NOT TESTED** | 本机未构造成功（`TD-I-5`）；仅注入等价验证 |
| `EOFError`（截断成员读取路径） | **NOT TESTED**（仅登记） | architecture §15.10.6 只要求登记，不主张可达与否 |
| `validate` 路径「不加锁」的直接观测（`pg_locks`） | **NOT TESTED**（以 `S6` 静态替代） | 采样不稳定（`TD-I-6`）；`I20` 计数 + `S6` 静态核查已覆盖 |
| 前端 / 界面 | **NOT_REQUIRED** | `layers.frontend=false`；`git diff` 证明 `frontend` 零改动；载体行为由 R3 覆盖 |
| 数据库约束 / Migration | **NOT_REQUIRED** | `layers.database=false`；零 DDL、零事务边界变化；解析失败发生在任何 `begin_nested()` 之前（`I9`/`I15`/`I16` 计数实测支撑「拒绝零残留」） |
| 整体验收（需求 §31–33 跨功能） | **NOT_REQUIRED（本 Feature）** | 归 plan `acceptance` 整体回归（F045 变更集）；不得用本 Feature 局部 PASS 拼成整体 PASS |
| `S1` / `S4` 的 pytest 化 | **NOT_REQUIRED** | 依赖 Git 状态，以 TE-6.5 只读命令为证据（其余 S 项均有 pytest 守卫） |

### TE-10 Defects

**无 BLOCKER / HIGH / MEDIUM 缺陷；无必须修复项（`READY FOR REVIEW`）。**

观察项（NOTE，不阻塞）：

| ID | Severity | Layer | 内容 | Owner |
| --- | --- | --- | --- | --- |
| TE-N1 | NOTE | 测试环境 | `test_perf03_near_max_rows_baseline` 的 600 s 阈值对宿主负载敏感（同一代码两次读数 685.48 s 失败 / 308.70 s 通过）。归因为环境波动，**不改阈值**、不改测试语义；登记为已知限制 | 协调器（环境 / CI） |
| TE-N2 | NOTE | Backend | `_parse_csv` 仍保留一份独立的 `UnicodeDecodeError → unreadable` 分支（共享转换器之外）；既有代码、零 diff、结论不变，仅记录形态差异供 Review 核对（不构成缺陷） | Backend（信息登记） |
| TE-N3 | NOTE | Backend | 拒绝路径保留一条 INFO 级 content-free 日志（`import parse rejected: format/bytes/error`），实测不含内容；与 `OPEN-T2` 默认保留一致（删除不影响任何断言） | 协调器 / 运维 |
| TE-N4 | NOTE | Architect | 无 lxml 环境（生产镜像）未实测，结论不外推（R-11 / OPEN-T5）；如需覆盖须另行提供该形态环境 | Architect / 协调器 |

### TE-11 结论

**`READY FOR REVIEW`**

- 新增测试模块 **52/52 PASS**（U 23 / I 23 / S 6），两次独立运行结果一致；含 architecture §10.2 两类输入的**有效性硬前置**、§15.8 输入 ③（含两种 XML 后端分支）、§15.10.7 的 `U13`/`U4` 11 类/`U14`/`I22`/`S7`，以及 `SyntaxError` 负向守卫。
- 验收 A1–A22 **全部 PASS**，无 FAIL / BLOCKED；回归 R1–R6 全部实跑通过（42 / 28 / 31 / 48 / 4 / 3），重点项 `test_td3_t114_field_boundaries`、`test_reg02_route_inventory`、`test_permission_matrix`、`test_validation_order_row_limit_before_header` 均通过。
- 契约与常量收口：仅 `resource_import.py` 的解析区有 diff；`core/errors.py`、F023 service、路由、models、alembic、frontend **零 diff**；F014 仍 **v1**、F023 仍 **v2**（各仅一条 §1.2 bullet + 一行修订记录）。
- 唯一环境相关失败项（`test_perf03`）经独立重跑**通过**，归因为宿主负载波动而非本改动（TE-6.6），登记为已知限制且未改任何阈值。
- 未执行项已在 TE-9 明示（无 lxml 环境、真实内存耗尽、三类异常真实可达性、`EOFError`、锁的直接观测、前端 / DB / 整体验收）。
- 本阶段只写 `backend/tests/integration/test_f037_import_parse_errors.py` 与本文件；未改生产代码、契约、其它测试或计划。

**GIT（本轮实际执行的只读命令，逐条列出）**：

```text
GIT: git status --porcelain
GIT: git log --oneline -5
GIT: git rev-parse --short HEAD
GIT: git diff -- backend/app/services/resource_import.py
GIT: git diff --stat
GIT: git diff --stat 1c0eeaf -- backend/ docs/api docs/database frontend
GIT: git diff --stat -- backend/app/services/resource_import.py
GIT: git diff --stat -- backend/app/services/resource_interface_ip_import.py backend/app/api backend/app/core backend/app/models backend/alembic frontend
GIT: git status --porcelain --untracked-files=all
GIT: git diff -U0 1c0eeaf -- backend/app/services/resource_import.py | grep -nE 'field_size_limit|strict=True|import_max_'
GIT: git diff 1c0eeaf -- docs/api/F014.md docs/api/F023.md
GIT: git diff --stat 1c0eeaf -- docs/api/F002.md
```

未执行任何 `git add` / commit / branch / merge / stash / reset / clean。
