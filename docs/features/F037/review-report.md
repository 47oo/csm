# F037 导入解析异常统一收敛为 422 IMPORT_INVALID_FILE — Review Report

- **状态**：**APPROVED WITH FOLLOW-UP**（无 BLOCKER / HIGH / 必须修复 MEDIUM；可进入 Merge Gate）
- **版本**：v1（2026-10-29，正式 Review，独立复核，reviewer 只读产出，协调器持久化）
- **候选 HEAD**：`36405bdcdeb53c5c37780742e9e00fdc4d115ebd`（short `36405bd`）
- **Base**：`refs/heads/v3.4` = `1c0eeafcd36fc6c4c791f89197243a074c6d5f01`（= `start_commit` = merge-base，无分叉历史遗漏）
- **完整范围**：`refs/heads/v3.4...HEAD`，5 提交 / 12 文件 / +3152 −45；工作区 clean
- **测试输入状态**：TE-F037-1 = `READY FOR REVIEW`

## 0. 审查范围与变更文件

| 类别 | 文件 |
| --- | --- |
| 实现 | `backend/app/services/resource_import.py`（M） |
| 测试 | `backend/tests/integration/test_f037_import_parse_errors.py`（A） |
| 契约 | `docs/api/F014.md`（M，+2 行：§1.2 bullet + §13 修订行）、`docs/api/F023.md`（M，+2 行：§1.2 bullet + §17 修订行） |
| Feature 报告 | `docs/features/F037/{product,architecture,implementation,test-report}.md`（A） |
| 计划 | `docs/project/project-plan.yaml` + 脚本派生视图 `backlog.md` / `dependency-map.md` / `milestones.md` |

`core/errors.py`、`backend/app/api/`、`models/`、`alembic/`、`frontend/`、`pyproject.toml`、`Dockerfile`：**零 diff**。

基线一致性（git-workflow §4）：`DELIVERY_BRANCH=v3.4`（git-workflow.md:35）＝ plan `git.base_branch` ＝ `refs/heads/v3.4`，且与 start_commit 指向同一提交；`v3.4` 同名 tag 存在，故所有比较命令使用 `refs/heads/v3.4`。`validate_project_state.py --feature F037` → VALID；`render_project_views.py`（只读）→ VIEWS VALID。

## 1. 独立验证（实际执行）

真实 PostgreSQL（容器 `csm-f037-pg`，postgres 16.15，`127.0.0.1:55432`，库名含 `test`）；Python 3.12.7 / pytest 7.4.4 / openpyxl 3.1.5 / `openpyxl.LXML=True` / lxml 5.2.1。

| 命令 | 结果 |
| --- | --- |
| `pytest tests/integration/test_f037_import_parse_errors.py -q` | **52 passed in 13.79s** |
| `pytest tests/integration/test_imports.py tests/integration/test_f030_test_harness.py -q` | **32 passed** |
| `pytest tests/integration/test_f023_resource_interface_ip_import.py -q -k "not perf03"` / perf03 单跑 | **27 passed** / **1 passed in 229.51s（write=200.14s）** |
| `pytest test_f034_*`(2) + `test_f036_*`(2) + `test_import_tester_acceptance` + `test_import_constraints` | **54 passed** |
| `pytest test_f035_*`(3) + `test_import_performance` | **42 passed** |
| 合计独立复跑 | **208 项全绿，0 skip / 0 xfail** |
| `ruff check app/services/resource_import.py` | All checks passed |

负向对照（内存内 passthrough，未改文件）：四个样本分别以 `_csv.Error` / `ElementTree.ParseError` / `lxml.etree.XMLSyntaxError` / `OSError` 逃逸 ⇒ 新增断言对「退回 500」敏感，非空跑。

日志实证：拒收路径实际产出 3 条 `csm.imports | import parse rejected: format=… bytes=… error=…`，无内容 marker。

## 2. 逐项结论

### 2.1 范围与基线 — PASS

工作区 clean、无未跟踪交付物；HEAD/Base/merge-base 正确；diff 仅授权文件；计划批准 cover F037（`api_required=true`、`layers={db:false,backend:true,frontend:false}`、`blocking_decisions: []`）；`pending_changes: []`（无暂停命中）；执行授权 `plan_revision 25` 由用户 2026-10-29 授予。

### 2.2 需求与契约符合性 — PASS

- product S1–S7 / N1–N8 / B1–B12 与 requirements revision 16（§24、§24.5、§31 T27/T28/T72/T107–T116 含 T114 追认/T124/T126）逐条一致，未自造规则。
- 契约仅新增不升版澄清附注：F014 仍 **v1**、F023 仍 **v2**；`docs/api/F002.md` 零 diff（无新 `reason` / 码 / `details` 键 / 上限 / 权限）。
- 附注措辞全文核对：仅排除式否定，无「新增拒绝 / 新增 reason / 新增上限」；T114 等价性口径未改写；`empty_file` / `unsupported_format` / 表头类 reason 与 §2 顺序明示不变。
- 附注描述输入形态而非异常类名 ⇒ 与 BE-01 的 `OSError` 局部入表不冲突；`message` 为默认文案、`details` 仅 `{"reason":"unreadable"}`。

### 2.3 实现正确性 — PASS

| 核对点 | 结论 | 证据 |
| --- | --- | --- |
| 白名单最小性 | PASS | `len(_PARSE_FAILURES)==8`；`InvalidFileException` + `OSError` 仅 `_parse_xlsx` 局部；`LxmlError` 条件追加（`try/except ImportError/else`），无模块顶层导入 |
| 分类边界 | PASS | 仅 `except AppError: raise` + `except failures`（AST 断言 handler 序列）；无 `except SyntaxError` |
| `except Exception` | PASS | 全文件 2 处：`_close_workbook`（新增清理边界，`noqa: BLE001`）与 `write_import`（既有回滚边界，零 diff） |
| 判定顺序 | PASS | `not data → empty_file` 先于 dispatch；PK 魔数闸门先于解析器调用；`worksheets` 空判定先于 `iter_rows` |
| `parse_records` 语义 | PASS | 签名与「全量物化 `list[list[str]]`」不变；CSV 仍全量物化后归一化 |
| `close()` 生命周期 | PASS | `workbook=None` + `finally` 守卫；实测成功 1 次 / 解析失败+close 抛错仍 422 且 close 恰 1 次 / `load_workbook` 抛错 0 次 |
| 日志字段 | PASS | 仅 `format` / `bytes` / 异常类名；无 `exc_info` / `filename` / `logger.exception|error` |
| L7′ | PASS | `grep` 无 `open(` / `Path(` / `NamedTemporaryFile` / `requests.` / `session.`；静态用例断言 `_parse_xlsx` 的 `with` 块只调用第三方解析 API |
| 依赖/镜像 | PASS | `pyproject.toml` / `Dockerfile` 零 diff；`backend/app` 中仅 `resource_import.py` 提及 lxml（函数内条件导入） |

观察（非缺陷）：`_parse_csv` 复用完整 `_PARSE_FAILURES`，CSV 作用域内实际仅 `csv.Error` 可达；`OSError` / `_cell_text` 类错误已证明不被吞（REV-F037-01，见 §3）。

### 2.4 测试充分性 — PASS

- 52 项覆盖 A1–A22（A1–A8→`i1_i8`、A9→`i9`、A10→`i10`、A11→`i11`、A12→`i12`、A13→`i13`、A14→`i14`、A15→`i15`、A16→`i16`、A17→`i17`、A18→`u12`+`i18`、A19→`u3–u8,u13–u16`+`i19`、A20→`i20`+`s6`、A21→`s2,s3,s5,s7,s8`、A22→R1–R6）。
- 三类输入均有**有效性前置断言**：输入①（131,229 / 131,336 B，裸 `csv.reader` 必抛含 `field larger than field limit` 的 `csv.Error`）；输入②（5,029 B、`PK\x03\x04`、`load_workbook` 成功而 `iter_rows` 抛 `ElementTree.ParseError`）；输入③（manifest 损坏，裸类型按 `openpyxl.LXML` 分支断言，不硬编码后端）。
- 零写入 / 零 Audit：7 表计数逐一相等，措辞为「`audit_logs` 不变即同时覆盖 Activity（无独立 activity 表）」，未出现误述。
- 401/403 先行、413 两码、表头类 role reason 与顺序、行级 `RowError`（`row==3`）、双载体 deep-equal、`MemoryError`→500、fd 20 次不增长：各有独立断言。
- `test_perf03` 结论成立且未被用于掩盖回归：同一代码三点测量 200.14 / 308.70 / 685.48 s；`write_import` / `parse_and_validate` / 逐行校验零 diff；微基准 `_PARSE_FAILURES + (InvalidFileException, OSError)` 元组构造 0.198 µs/次、5000 行解析 8.6–9.2 ms。

### 2.5 可维护性与风险 — PASS

`OPEN-T1`（`InvalidFileException` 本机不可达）、`OPEN-T2`（两条 content-free INFO 日志）、`OPEN-T4`（真实内存耗尽不可测，标 `NOT TESTED`）、`OPEN-T5`/`R-11`（无 lxml 环境未测，结论不外推）、`R-12`（`OSError` 宽基类，L7′ + 静态用例双重约束）、`TD-I-8`（空 zip 期望更正并实测）、`EOFError`（仅登记、未主张可达性）均如实登记；未发现「以未验证冒充通过」的表述。

## 3. 缺陷与跟进

**无必须修复项。** 观察项（全部非阻塞）：

| ID | 级别 | 是否必须修复 | 内容 | Owner |
| --- | --- | --- | --- | --- |
| REV-F037-01 | NOTE | 否 | `_parse_csv` 复用完整白名单（CSV 作用域内实际仅 `csv.Error` 可达，已登记 R-9 / TD-I-4） | Backend / Architect |
| REV-F037-02 | NOTE | 否 | `OSError` 宽基类由 L7′ 前提封住（R-12 LOW） | Backend（F038 重评） |
| REV-F037-03 | NOTE | 否 | `ValueError` / `KeyError` 偏宽（未来 openpyxl 内部错误可能表现为 422），已登记 R-1 / R-9 | Architect |
| REV-F037-04 | NOTE | 否 | `EOFError`（截断成员读取）未入白名单 → 500，未裁定可达性 | Backend（探测后另裁） |
| REV-F037-05 | NOTE | 否 | 契约附注「仍为 500」为契约意图表述；实际收窄已在 implementation §5 / architecture §3.2 / R-6 披露 | Architect（措辞，可选） |
| REV-F037-06 | NOTE | 否 | 测试 `assert_unreadable()` 以 `status_code == 422` 断言（严格强于反例排除），TE-3 措辞略强于代码字面，无覆盖缺口 | Tester |
| REV-F037-07 | LOW | 否 | 新测试依赖私有符号（`_PARSE_FAILURES` 等），内部改名会 FAIL，属白盒守卫必要代价 | Tester |
| REV-F037-08 | NOTE | 否 | `architecture.md` §5.2 日志字段列 `stage`，与 §2.2 定稿实现不一致（纯文档） | Architect |
| REV-F037-09 | NOTE | 否 | `test_perf03` 阈值对负载敏感（三分测量 3.4× 波动），未改阈值 / 语义 | 协调器（CI） |

旧缺陷复核：`F037-BE-01`（OSError 退化 500）**已闭环**（DR-F037-08，`u13`/`i22` 独立验证，`OSError not in _PARSE_FAILURES`）；`TD-I-1`（lxml XMLSyntaxError）**已闭环**（条件入表，`u15`/`u3`/`u4`/`i23`）；`TD-I-8` **已更正并实测**；`TE-N1`–`TE-N4` 事实成立、非缺陷。

## 4. FOLLOW-UP（均不阻塞合并）

| ID | 内容 | Owner | 阻塞 |
| --- | --- | --- | --- |
| FU-01 | Merge 以候选 HEAD `36405bd` + Base `1c0eeaf` 为准；合并后写入 `git.head_commit` / `git.merge_commit`；任何新提交须重新 Review | 协调器 | 否 |
| FU-02 | 修正 `architecture.md` §5.2 清理日志的 `stage` 字段表述（纯文档） | Architect | 否 |
| FU-03 | `perf03` 阈值敏感：仅在 CI 稳定复现时另立提案，不在 F037 内改阈值 | 协调器 / CI | 否 |
| FU-04 | F038 必须复用 `_invalid_file_on_parse_failure` / `_PARSE_FAILURES`（含 lxml 与 `OSError` 条目）并重评 L7′；顺带探测 `EOFError` | Architect（F038） | 否 |
| FU-05 | 若收窄 CSV 路径白名单为 `(csv.Error,)`，走普通设计签核（可观察行为不变） | Backend / Architect | 否 |
| FU-06 | 补一次无 lxml（`openpyxl.LXML=False`）环境验证，把 `u15`/`u4` 的 False 分支从 `NOT TESTED` 转实测 | 协调器 | 否 |
| FU-07 | 测试层措辞/清理：冗余断言行与私有符号耦合在 TD-2 中明确 | Tester | 否 |

## 5. 明确声明

- 结论 **APPROVED WITH FOLLOW-UP**：核心验收（A1–A22）满足、必要验证可信（208 项独立复跑全绿、负向对照成立）、无 BLOCKER / HIGH / 必须修复 MEDIUM、无未决产品问题。
- 批准仅对候选 HEAD `36405bd` 与 Base `refs/heads/v3.4` = `1c0eeaf` 有效；基线或候选变化必须重新 Review。
- 可进入 Merge Gate（由协调器按 git-workflow §5 判定 DONE）；NOTE / LOW 与 FU-01–FU-07 均非阻塞，不得据此修改实现或放宽产品规则。
- 未审查：前端（`layers.frontend=false`）、Schema/Migration（`layers.database=false`，零 DDL）、无 lxml 环境、真实内存耗尽、`LargeZipFile`/`NotImplementedError`/`InvalidFileException` 真实可达性、`pg_locks` 直接观测、F038 及后续 Feature、F045 整体验收。
