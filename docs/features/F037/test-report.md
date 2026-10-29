# F037 导入解析异常统一收敛为 422 IMPORT_INVALID_FILE — Test Report

> 同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本与证据。
> **当前状态**：§1 TEST DESIGN = **TD-F037-1（v1，2026-10-29，`TEST DESIGN READY`）**；§2 TEST EXECUTION 尚未开始（实现未启动）。
> `TEST DESIGN READY` 仅表示方案可验证，**不是测试通过**，不批准实现、Contract 定稿或合并。下文所有「期望」均为**待执行断言**，本阶段未运行任何测试或构建。

**版本记录**

| 阶段 | 版本 | 日期 | 结论 | 依据 HEAD |
| --- | --- | --- | --- | --- |
| TEST DESIGN | TD-F037-1 | 2026-10-29 | `TEST DESIGN READY`（**不是测试通过**；实现未开始，全部用例待执行） | `a6932c5`（工作区仅新增未跟踪 `docs/features/F037/architecture.md`；`backend/**`、`frontend/**`、`docs/api/**` 零 diff） |
| TEST | — | — | 尚未开始（待 CONTRACT Gate 签核 §6.2 附注 + Backend `implementation.md`） | — |

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
| `TD-F037-U9` | U | **判定顺序与生命周期不变**（L4/L5） | `parse_records(b"", "csv")` / `b"" xlsx`；非 PK 的 `.xls` 魔数；`PK\x03\x04` 非 zip；空 zip（无 worksheet）；正常 xlsx | `empty_file`（空字节，先于 dispatch）→ `unsupported_format`（PK 闸门先于任何解析器调用）→ `unreadable`（坏 zip）→ `empty_file`（`workbook.worksheets` 空，先于 `iter_rows`）→ 正常解析返回 `list[list[str]]` 且 `parse_records` 返回类型仍为物化列表 | A19；B1、B2、L4、L5 |
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
| `TD-I-1` | **白名单覆盖缺口（本机实测）**：`openpyxl 3.1.5` + `lxml 5.2.1` 下，`[Content_Types].xml` 等部件由 **lxml** 解析，XML 结构损坏抛 `lxml.etree.XMLSyntaxError`（MRO 仅到 `SyntaxError`，**不是** `ElementTree.ParseError`，也不是 `ValueError`）⇒ architecture §3.1 白名单**不覆盖**，该类输入修复后仍为 500。属于 R-1「白名单过窄」的具体实例。请 Architect 裁定：① 扩展白名单（如 `lxml.etree.LxmlError` 或 `SyntaxError`，需评估后者的可观察副作用）；② 或在 §3.1 明确将「lxml 解析路径的 XML 损坏」排除并登记为既有残余（则 R-1 矩阵中该行用例标 `NOT TESTED` 并写明理由）。**A1–A8 不受影响**（输入 ①② 实测分别落在 `csv.Error` 与 `ElementTree.ParseError`） | Architect | 需裁定（MEDIUM；不阻塞本 TD 结论，但决定 R-1 矩阵用例是否判 FAIL） |
| `TD-I-2` | 输入 ① 字节数口径：product/plan 写「131,082 B」，本机按 architecture §10.2 构造得 131,229 B（BM 14 列）/ 131,336 B（26 列）。本 TD 只用不变量（`>131_072` 且 `≤5_242_880`）+ 实测值，**不**硬编码 131,082 | Product（确认即可） | 否（登记口径） |
| `TD-I-3` | `csm.imports` 两条 content-free INFO 日志是否保留（architecture OPEN-T2）。本 TD 的 `U12` 判据与日志存在性解耦：存在则校验字段受限，不存在则断言无记录 | 协调器 / 运维 | 否 |
| `TD-I-4` | `ValueError` / `KeyError` 入白名单偏宽（所有 `ValueError` 在 `with` 内都被转为 `unreadable`）：以 `U11`（作用域最小性）+ `S3`（`except` 子句形态）共同约束，不放宽到 `except Exception` | Backend（实现登记） | 否 |
| `TD-I-5` | `InvalidFileException` 在 `load_workbook(fileobj)` 路径本机未命中（`PK` 非 zip → `BadZipFile`，与 architecture OPEN-T1 一致）。删除或保留该 `failures=` 项**不改变**任何已设计断言；TEST 只做注入等价验证 | Backend | 否 |
| `TD-I-6` | **A18 判据纪律**：`core/errors.py` 的 500 handler 使用 `logger.exception`（含 traceback），`TD-F037-I19` 注入的自定义异常消息会进入日志。故 A18 的 `caplog` 守卫**只**覆盖 422 拒绝路径（`U12`），不把 500 注入用例的 traceback 计入判据；`I19` 亦不使用含上传内容的 marker | Tester（本 TD 已固定） | 否（判据已固定） |
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

GIT: NONE
