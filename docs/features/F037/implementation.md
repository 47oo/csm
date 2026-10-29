# F037 导入解析异常统一收敛为 422 IMPORT_INVALID_FILE — IMPLEMENTATION 阶段报告（Backend）

- **状态**：**BACKEND COMPLETE**（Backend 范围完成；真实 PG 集成与全量回归留待 TEST 阶段，见 §6）
- **版本**：v1（2026-10-29）；FEATURE / P0 / M28；分支 `feature/F037-import-parse-error-contract`（交付线 `v3.4`，实现基于 `50bb9cf`）；**plan revision 25**；**requirements revision 16**
- **角色产物**：backend 只读产出，协调器持久化。
- **上游依据（逐字遵守）**：`docs/features/F037/architecture.md` v1 §2.2（`_PARSE_FAILURES` / `_invalid_file_on_parse_failure` / `_close_workbook` / `_parse_csv`）、**§15.1（lxml 条件条目）、§15.4（`_parse_xlsx` 定稿）**、§3 / §15.2–15.3（白名单与排除项）、§4（L1–L7）、§5（文案与日志）、§9（实施层）、§15.9（放行范围）；`docs/features/F037/product.md` v1（B1–B12、A1–A22）；`docs/api/F014.md` v1 §1.2 澄清附注、`docs/api/F023.md` v2 §1.2 澄清附注；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`。
- **写入面（仅此两处）**：`backend/app/services/resource_import.py`（改动）、`docs/features/F037/implementation.md`（本文件，新建）。零 Git 写操作。

## 1. 实现范围

### 1.1 文件与函数清单（单文件，+86 / −15）

| 位置 | 内容 | 对应设计 |
| --- | --- | --- |
| `resource_import.py:22-39` | 新增 stdlib 导入：`logging`、`zipfile`、`zlib`、`collections.abc.Iterator`、`contextlib.contextmanager`、`xml.etree.ElementTree` | §2.2 |
| `resource_import.py:62` | `logger = logging.getLogger("csm.imports")` | §2.2 / §5.2 |
| `resource_import.py:67-76` | `_PARSE_FAILURES`：9 类结构性异常的模块级白名单元组（`csv.Error`、`BadZipFile`、`LargeZipFile`、`zlib.error`、`ElementTree.ParseError`、`NotImplementedError`、`KeyError`、`ValueError`；第 9 类 `InvalidFileException` 按 §15.4 仅在 `_parse_xlsx` 内并入） | §2.2 / §3.1 / §15.2 |
| `resource_import.py:441-462` | `_invalid_file_on_parse_failure(fmt, size, failures=_PARSE_FAILURES)`：`except AppError: raise` + `except failures as exc:` 两个子句；记录 `format` / `bytes` / 异常**类名**后 `raise ImportInvalidFile("unreadable") from exc` | §2.2 / §3.2 / §5.2 |
| `resource_import.py:465-477` | `_close_workbook(workbook)`：best-effort `close()`，清理异常吞掉（唯一保留的 `except Exception`，标注 `# noqa: BLE001 - cleanup boundary`）并只记异常类名 | §2.2 / §4 L2–L3 |
| `resource_import.py:480-487` | `_parse_csv`：`data.decode("utf-8-sig")` 既有 `UnicodeDecodeError → unreadable` 独立保留，其后仅在 `with _invalid_file_on_parse_failure("csv", len(data))` 内物化 `list(csv.reader(...))`；归一化在作用域外 | §2.2 / §2.1-5 |
| `resource_import.py:490-523` | `_parse_xlsx`：PK 魔数闸门 → 惰性 `from openpyxl import load_workbook` + `InvalidFileException` → `failures = _PARSE_FAILURES + (InvalidFileException,)` → `try: from lxml.etree import LxmlError / except ImportError: pass / else: failures += (LxmlError,)` → `workbook = None` → `with` 内 `load_workbook(read_only=True, data_only=True)` + `worksheets` 空判定（`empty_file`）+ `iter_rows` → `finally: if workbook is not None: _close_workbook(workbook)` → 归一化 | **§15.4（定稿，逐句一致）** |
| `resource_import.py:526-529` | `parse_records(data, fmt)`：签名与「全量物化 `list[list[str]]`」语义不变，`if not data: empty_file` 在 dispatch 前 | §2.1-3 / §4 L4 |

### 1.2 明确未改动

- `_cell_text` 零 diff；`parse_records` 签名/返回类型/物化语义零变化；`openpyxl` 仍惰性导入（`ImportError → unsupported_format` 路径保留）。
- `parse_and_validate` / `_resolve_template` / 逐行校验 / `write_import` 零 diff（校验顺序、5 MiB、5000 行、预览 1000 全部不动）。
- `backend/app/core/errors.py`、`backend/app/services/resource_interface_ip_import.py`、`backend/app/api`、`backend/app/models`、`backend/alembic`、`frontend/` 零 diff；`backend/pyproject.toml`、`backend/Dockerfile` 零 diff（**无新依赖，lxml 不落依赖清单、不改镜像、不在模块顶层导入**，仅函数内条件导入）。

## 2. 逐条自检结论

### 2.1 环境事实（实测，`openpyxl.LXML` 决定 `.xlsx` 走哪条 XML 后端）

```text
Python 3.12.7
openpyxl 3.1.5 LXML True
lxml 5.2.1
```

结论仅适用于 `openpyxl.LXML is True` 的本机环境（开发/测试机形态）；生产镜像（无 lxml → ElementTree 后端）未在本阶段验证，不外推（R-11 / OPEN-T5，见 §7）。

### 2.2 §15.4 定稿逐项核对

| # | §15.4 要求 | 实现 | 证据 |
| --- | --- | --- | --- |
| 1 | PK 魔数闸门先于任何解析器调用，非 OOXML → `unsupported_format` | `:491-493` | `.xls` OLE2 魔数（`\xd0\xcf\x11\xe0…`）→ `IMPORT_INVALID_FILE {'reason': 'unsupported_format'}`；空 zip（含 `PK` 头但无成员）→ `unsupported_format` |
| 2 | `load_workbook` / `InvalidFileException` 惰性导入，`ImportError → unsupported_format` | `:494-498` | 三处 `parse_records` 调用签名不变，模块导入不触发 openpyxl（`python3 -c "from app.services…"` → `import ok`） |
| 3 | `failures = _PARSE_FAILURES + (InvalidFileException,)` | `:504` | 注入 `InvalidFileException` → `{'reason': 'unreadable'}`、`__cause__` 为 `InvalidFileException` |
| 4 | `from lxml.etree import LxmlError` **条件**并入（`try/except ImportError/else`），不在模块顶层 | `:505-510` | `grep -rn lxml backend/app` 仅命中 `resource_import.py:500-506`（另有无害 `.pyc` 命中）；`git diff -- backend/pyproject.toml backend/Dockerfile` 为空 |
| 5 | `workbook=None` + `finally: if workbook is not None: _close_workbook(workbook)` | `:512-522` | close 调用次数：成功路径 1、解析失败路径 1、`load_workbook` 抛错路径 0 |
| 6 | `worksheets` 空判定（`empty_file`）在 PK 闸门之后、`iter_rows` 之前 | `:516-519` | 缺 `xl/worksheets/sheet1.xml` 的容器 → `422 {'reason': 'empty_file'}` |
| 7 | 归一化（`_cell_text`）在转换作用域之外 | `:487` / `:523` | 编程错误不被转成 422（见 2.4） |

### 2.3 §4 不变量 L1–L7

| # | 不变量 | 结论 | 证据 |
| --- | --- | --- | --- |
| L1 | `read_only=True, data_only=True` 保持 | **PASS** | `:515` 原样保留；未改大文件模式 / `data_only=False` / `keep_vba` |
| L2 | `close()` 在 `finally`，用 `None` 守卫 | **PASS** | `:512-522`；`_close_workbook` spy：成功 1 次、损坏 sheet 1 次、`load_workbook` 抛错 0 次 |
| L3 | close 异常不得覆盖已判定 422 | **PASS** | 注入「解析失败 + `close()` 抛 `RuntimeError`」→ 仍 `IMPORT_INVALID_FILE {'reason': 'unreadable'}`（未逃逸 `RuntimeError`）；日志出现 `import workbook close failed: error=RuntimeError`，无堆栈 |
| L4 | `empty_file` 顺序不变 | **PASS** | 空字节 → `empty_file`；仅表头 CSV 正常解析（`empty_file` 仍由 `parse_and_validate` 既有位置判定，零 diff） |
| L5 | `unsupported_format` 顺序不变 | **PASS** | 非 OOXML 在 PK 闸门先返回 `unsupported_format`，未被 `InvalidFileException` 覆盖 |
| L6 | 大小 / 行数 / 表头 / 逐行顺序 | **PASS（零 diff）** | `git diff` 仅含导入区与 `_cell_text` 之后的解析区；`parse_and_validate` / `_resolve_template` / `_ROW`/上限常量无改动；`git diff -U0 … \| grep -E 'field_size_limit\|strict=True\|import_max_'` → `no cap/strict change` |
| L7 | 无副作用 | **PASS** | 全部改动位于纯函数内；无 DB 访问、无锁、无 Audit、无落盘、无配置读取（解析层不新增任何 I/O 出口） |

### 2.4 分类边界与「不吞异常」守卫（§3.2 / §15.3，实测）

```text
AppError fidelity -> {'reason': 'empty_file'}        # ImportInvalidFile 原样透传
propagates -> MemoryError
propagates -> RecursionError
propagates -> SyntaxError                            # 证明未用 except SyntaxError（ParseError 仅按精确类入表）
propagates -> AttributeError
propagates -> TypeError
propagates -> IndexError
propagates -> KeyboardInterrupt
propagates -> SystemExit
```

- 分类边界仅 `except AppError: raise` + `except failures as exc:`（`_invalid_file_on_parse_failure`），全文件 `except Exception` 只剩 2 处：`:476` `_close_workbook` 清理边界（设计允许的唯一例外）、`:1010` `write_import` 事务回滚后 `raise`（**既有代码，零 diff，不参与 4xx/5xx 分类**）。

### 2.5 真实字节端到端自检（服务层，无需数据库）

```text
csv bytes: 131152
csv -> IMPORT_INVALID_FILE {'reason': 'unreadable'}
xlsx-sheet (4964 B) -> IMPORT_INVALID_FILE {'reason': 'unreadable'}
xlsx-manifest (4962 B) -> IMPORT_INVALID_FILE {'reason': 'unreadable'}
```

输入①（14 列表头 + 单字段 131,073 字符，总 131,152 B；未超 5 MiB 上限，故不会先命中 413）；输入②（`xl/worksheets/sheet1.xml` 的 `</worksheet>` → `</weshet>`）；输入③（`[Content_Types].xml` 的 `</Types>` → `</Typse>`，TD-I-1 环境相关路径）。三者均落 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`，`details` 恰为 `{"reason": "unreadable"}`。

根因与后端分支实测（`__cause__` 类型证明输入确实在解析期失败）：

| 输入 | `__cause__` | 说明 |
| --- | --- | --- |
| CSV 单字段超限 | `csv.Error` | CSV 迭代期（`csv` 默认字段上限 131072） |
| sheet XML 结束标签损坏 | `ElementTree.ParseError` | `read_only` 惰性解析（`iterparse` 恒为 ET，与 lxml 无关） |
| `[Content_Types].xml` 损坏 | `lxml.etree.XMLSyntaxError` | `openpyxl.LXML=True` → `fromstring` 走 lxml；仅由条件条目 `LxmlError` 覆盖 |

### 2.6 白名单样本矩阵（R-1 检测，实测）

| 输入形态 | 结果 | `__cause__` |
| --- | --- | --- |
| 最小合法 xlsx | OK（2 行） | — |
| 缺 `xl/worksheets/sheet1.xml` | 422 `empty_file` | — |
| 缺 `[Content_Types].xml` | 422 `unreadable` | `KeyError` |
| 缺 `xl/_rels/workbook.xml.rels` / 缺 `xl/workbook.xml` / 仅 CT | 422 `unreadable` | `KeyError` |
| 非法单元格坐标（`r="??"`） | 422 `unreadable` | `ValueError` |
| `xl/workbook.xml` XML 损坏 | 422 `unreadable` | `XMLSyntaxError`（lxml） |
| zip 截断（字节砍半） | 422 `unreadable` | `BadZipFile` |
| CRC / 中央目录损坏 | 422 `unreadable` | `BadZipFile` |
| `PK` 头 + 非 zip 内容 | 422 `unreadable` | 白名单内异常 |
| 空 zip（零成员） | 422 `unsupported_format` | — |
| **`[Content_Types].xml` 可读但未声明 workbook 部件** | **500 逃逸**（`OSError: File contains no valid workbook part`） | `OSError`（openpyxl `_find_workbook_part`）→ 见 §7.2 |

### 2.7 日志与信息保护（§5 / A18 级守卫，实测）

捕获的输出样本（`csm.imports`，content-free）：

```text
import parse rejected: format=xlsx bytes=4838 error=ParseError
import workbook close failed: error=RuntimeError
```

marker 守卫（同一批日志文本内检索）：`field larger than field limit` → 未命中；`filename` → 未命中；`Traceback` → 未命中；`weshet` → 未命中；`<worksheet` → 未命中；`"a"*40`（字段内容）→ 未命中。

- `grep -nE 'logger\.(exception|error)\(' backend/app/services/resource_import.py` → `no exception logging`。
- `grep -n 'filename\|exc_info' backend/app/services/resource_import.py` → `no filename/exc_info`（无 `exc_info`、无客户端文件名入日志；异常仅以 `error=<类名>` 形式出现）。
- `message` 走 `ImportInvalidFile` 既有默认文案 `Invalid import file`（`core/errors.py` 零 diff），`details` 仅 `{"reason":"unreadable"}`；响应与日志均不含上传内容、`str(exc)`、lxml `error_log`（含源行上下文）。

### 2.8 fd 泄漏（R-5，实测）

```text
R-5 fd before/after 20 corrupt submissions: 4 4
```

同一进程连续 20 次提交同一损坏 xlsx，`/proc/self/fd` 条目数不增长（与 U 层 close 计数 1 次互为佐证）。

### 2.9 静态守卫（实测输出）

```text
$ git diff --stat -- backend/app/services/resource_import.py
 backend/app/services/resource_import.py | 101 +++++++++++++++++++++++++++-----
 1 file changed, 86 insertions(+), 15 deletions(-)

$ git diff -- backend/pyproject.toml backend/Dockerfile
(空)

$ git diff --stat -- backend/app/services/resource_interface_ip_import.py backend/app/api backend/app/core backend/app/models backend/alembic frontend
(空)

$ grep -nE 'except SyntaxError|except Exception' backend/app/services/resource_import.py
476:    except Exception as exc:  # noqa: BLE001 - cleanup boundary, not a 4xx/5xx signal
1010:    except Exception:
```

注：`:1010` 为 `write_import` 事务回滚后 `raise` 的既有代码（`except AppError: db.rollback(); raise` / `except Exception: db.rollback(); raise`），零 diff、不参与 4xx/5xx 分类；`grep 'except SyntaxError'` 无命中。

```text
$ grep -nE 'logger\.(exception|error)\(' backend/app/services/resource_import.py || echo 'no exception logging'
no exception logging

$ grep -n 'filename\|exc_info' backend/app/services/resource_import.py || echo 'no filename/exc_info'
no filename/exc_info

$ git diff -U0 -- backend/app/services/resource_import.py | grep -nE 'field_size_limit|strict=True|import_max_' || echo 'no cap/strict change'
no cap/strict change

$ grep -rn "lxml" backend/app
backend/app/services/resource_import.py:500/501/506 (+ 无害 __pycache__ .pyc 命中)

$ python3 -m compileall -q app/services/resource_import.py && echo compile-ok
compile-ok
```

### 2.10 既有测试（真实输出，无库）

```text
$ TEST_DATABASE_URL= python3 -m pytest tests/integration/test_imports.py -q
1 passed, 28 skipped in 1.58s
（28 skipped 原因均为 `TEST_DATABASE_URL is not set; integration tests require a real PostgreSQL database`）
```

**不得声称集成通过**：28 项因缺 PG 全部 skip，仅 1 项纯逻辑用例实际执行并通过。

## 3. Contract 符合情况

| 契约点 | 结论 |
| --- | --- |
| 4 端点（`/imports/resources{,/validate}`、`/imports/resource-interfaces-ips{,/validate}`）解析期失败 → 422 `IMPORT_INVALID_FILE` | 服务层单一落点覆盖：`parse_records` 仅 2 个调用点（`resource_import.py` 的 `parse_and_validate`、`resource_interface_ip_import.py:1200`），均在 `parse_and_validate` 首部，故四端点两条路径同口径；本阶段未做 HTTP 层验证（留待 TEST） |
| `details` 恰 `{"reason":"unreadable"}`，`message` 默认文案 | 实测三输入一致；未新增 `reason` / 码 / `details` 键 |
| F014 §1.2 / F023 v2 §1.2 澄清附注（不升版）已落稿 | 无需本角色改动；实现与该附注一致（归入既有 `unreadable`，未新增拒绝条件、未改 `csv` 字段上限、未启用严格引号） |
| 校验顺序 401 → 403 → `format` 422 → 413 → 解析 422 → 413 → 表头/列 422 → 逐行 | 服务层零改序（L6 零 diff）；HTTP 前两档与端点装配属既有代码，零 diff |
| `core/errors.py` 零 diff | 是 |
| 双载体等价（T114） | 转换发生在字节入口之后，服务层不读取客户端文件名 / `Content-Type`（`grep filename` 无命中）；等价性用例留待 TEST |

## 4. Database / Migration 影响

**NOT_REQUIRED 继续成立**：零 SQL、零表/列/索引/约束/触发器/Migration、零事务边界改动；解析期失败发生在任何 `begin_nested()` / 写入之前，`audit_logs` / 目标表零残留（结构性保证，实测计数留待 TEST 的 PG 用例）。

data-integrity 对照（引用 `docs/project/implementation-rules.md` 与 `.pi/skills/data-integrity/SKILL.md`，不另建规则）：

| 规则 | 本次影响 |
| --- | --- |
| §24-2 / T27 / T123 整批原子、拒绝零残留 | 不变（提前失败只减少写入机会） |
| §22 Audit 同事务 | 不变（拒绝请求零 Audit） |
| §24.5 / T107–T116 双载体等价 | 不变（转换在字节入口之后） |
| 1-based 行号 / `RowError` 形状 | 不变（物化列表索引语义保持） |

## 5. 事实披露（可观察行为变化，非纯加法）

以下均为 product B7 / architecture §3.2 的强制结果，在此登记，TEST 与 Review 需据此判定，不得当作回归：

1. **收窄（500 ← 曾 422）**：改前 `_parse_xlsx` 的 `load_workbook` 处为 `except Exception`（`resource_import.py:437-442@50bb9cf`），因此 `MemoryError`、`RecursionError`、`SyntaxError`、`AttributeError`、`TypeError`、`IndexError` 等**未入白名单类型**在 `.xlsx` 路径上曾被转成 422 `unreadable`；改后回到 500 `INTERNAL_ERROR`（既有固定 `message`，`details {}`），并保留既有脱敏 `logger.exception`。已实测传播（§2.4）。CSV 路径改前仅有 `UnicodeDecodeError` 转换，故此收窄只影响 `.xlsx` 路径。
2. **收窄（具体样本）**：`[Content_Types].xml` 可读但未声明 workbook 部件的 zip（`PK` 头、结构可读、缺有效 workbook 部件）由 openpyxl `_find_workbook_part` 抛 `OSError: File contains no valid workbook part`。该类型未入 §15.2 白名单，改前为 422，改后为 **500**。**这是白名单最小性（R-1）在本环境下的唯一实测缺口**，需 Architect 裁定是否扩展（见 §7.2；本角色不擅自扩表）。
3. **放宽（422 ← 曾 500），仅 `openpyxl.LXML=True` 环境**：`[Content_Types].xml` / `xl/workbook.xml` / `docProps/*` 等经 `fromstring` 解析的部件 XML 损坏时抛 `lxml.etree.XMLSyntaxError`，改前逃逸为 500，改后按 TD-I-1 条件条目收敛为 422 `unreadable`。在无 lxml 环境（ElementTree 后端）该路径抛 `ElementTree.ParseError`，改前即 422，行为不变。实测 `openpyxl.LXML=True`，故本机可见此放宽。
4. **无变化**：`empty_file`、`unsupported_format`、表头/列类 reason、两 413、行级 `IMPORT_VALIDATION_FAILED`、`RowError` 形状与行号、双载体等价、原子性与 Audit 口径全部不变。

## 6. 未执行项（明示）

1. **真实 PostgreSQL 集成**（A1–A22 中的 I 层 8 例、零写入/零 Audit、401/403 先行、413/表头/行级回归、双载体等价、fd 契约化用例）：本阶段无 `TEST_DATABASE_URL`，`tests/integration/test_imports.py` 28 项全部 skip。**未验证，不得视为通过**；由 TEST 阶段执行。
2. **全量回归套件**（`test_import_tester_acceptance` / `test_import_constraints` / `test_f023_resource_interface_ip_import` / F034 两模块 / F035 / F036 归因 / `test_import_performance`）：未运行，留待 TEST 阶段。
3. **新增测试模块** `backend/tests/integration/test_f037_import_parse_errors.py`：属 Tester 的 L2 范围，本角色未创建（写入面不含测试文件）。
4. **生产镜像形态验证**（无 lxml / ElementTree 后端，R-11 / OPEN-T5）：未执行；结论不外推。
5. **真实内存耗尽**（`MemoryError` 进程行为）：未测试，仅以注入证明分类边界（OPEN-T4）。
6. **HTTP 层端点装配与响应体逐字段断言**：未执行（服务层已验证 `details` 形状；端点行为留待 TEST）。

## 7. 风险与遗留

### 7.1 OPEN-T1（`InvalidFileException` 可达性）— 结论：本环境样本中不可达，按 §15.4 定稿保留

- 采样（openpyxl 3.1.5，file-object 路径）：空 zip → PK 闸门后 `unsupported_format`；缺 `[Content_Types].xml` / 缺 `xl/workbook.xml` / 仅 CT → `KeyError`；CT 可读但无 workbook 部件 → `OSError`。**未观察到 openpyxl 在 `load_workbook(fileobj)` 路径抛 `InvalidFileException`**（其判定面向文件名后缀/文件类型提示）。
- 处置：按 §15.4 定稿**保留** `+ (InvalidFileException,)`（可观察行为不变：仅当该异常出现时结果同样是 422 `unreadable`，与既有 `unreadable` 口径一致）。已实测注入 `InvalidFileException` → 422 `unreadable` 且 `__cause__` 保留。若后续架构角色裁定移除，属零可观察差异的收窄。

### 7.2 遗留风险（本报告新增登记，需 Architect 裁定；本角色未擅自扩表）

| ID | 风险 | 级别 | 实测事实 | 建议处置（Architect） |
| --- | --- | --- | --- | --- |
| **F037-BE-01**（建议并入 R-1 / 记为 OPEN-T6） | `OSError('File contains no valid workbook part')`（openpyxl `_find_workbook_part`）未入白名单 → 该类损坏容器 500（改前 422） | **MEDIUM** | §2.6 行「CT 可读但未声明 workbook 部件」 | 若要覆盖，须由 Architect 裁定扩展方式；注意 `OSError` 为宽基类（含 `FileNotFoundError` / 磁盘错误族），建议仅在 `load_workbook` 调用点窄化（或引入 openpyxl 精确异常），**不宜**直接整体加入 `_PARSE_FAILURES`；改变判定须走设计签核，不改契约 |
| R-1（残余） | 未来 openpyxl 版本新增异常类或 `OverflowError` 仍逃逸 500 | LOW | 本阶段样本矩阵 11 例中 10 例 422 / OK | 由 TEST 的样本矩阵 + 参数化用例持续检测；`OverflowError` 属 B8 刻意不捕 |
| R-6 | 行为收窄/放宽被误读为回归 | MEDIUM | §5 第 1–3 条 | TEST / Review 以 §5 为准；不得据此改实现 |
| R-7 | 新增 INFO 日志被判越界 | LOW | §2.7 内容守卫全绿（仅 format/bytes/类名） | 若 Review 判越界，删除该 `logger.info` 不影响任何解析断言（OPEN-T2） |
| R-8 | F038 流式化后作用域漂移 | MEDIUM | 转换已抽为可复用 `_invalid_file_on_parse_failure` + `_PARSE_FAILURES`（含 lxml 条件条目） | F038 须复用，另走自身 Gate |

### 7.3 回滚

还原 `backend/app/services/resource_import.py` 至 `50bb9cf` 即回到改前行为（无 Schema / 迁移 / 配置 / 依赖耦合）；回滚后 F037 新增用例应失败，不得删用例修绿。

## 8. 与设计的一致性声明

实现与 `docs/features/F037/architecture.md` §2.2 / §15.4 定稿**逐句一致**，未新增设计外行为：无 `except Exception` 泛捕（清理边界除外）、无 `except SyntaxError`、无 `str(exc)`、无 `exc_info`、无 `logger.exception|error`、无 `filename`、未改校验顺序 / 上限 / `core/errors.py` / F023 service / 路由 / 前端 / 依赖。发现的唯一实测缺口（§7.2 `OSError`）**按角色边界返回 Architect 裁定**，未在本 Feature 内擅自扩展白名单。

GIT: NONE

## 9. Repair round 1（BE-01，2026-10-29）

- **上游依据**：`docs/features/F037/architecture.md` §15.10（BE-01 裁定 / DR-F037-08）+ §15.10.3（`_parse_xlsx` `failures` 定稿修订）+ §15.10.4（L7′）；本轮放行写面仅 `backend/app/services/resource_import.py` 与本文件。
- **基线**：`dec9445`（本轮未做任何 Git 写操作）。

### 9.1 改动（唯一一处，`resource_import.py:501-514`）

`_parse_xlsx` 内 `failures` 构造由 `_PARSE_FAILURES + (InvalidFileException,)` 改为 `_PARSE_FAILURES + (InvalidFileException, OSError)`（多行元组写法），并按 §15.10.3 加入 OSError 语义注释（openpyxl「包不是 workbook」信号 / 非 I/O 故障 / 全程 `io.BytesIO` 故真实 I/O 故障不可达 / 不得在块内新增真实 I/O（L7′）/ 不得放宽为 `except Exception`）。注释以 §15.10.3 定稿的中文原文落码（该段为本轮新增注释；模块其余既有注释保持原英文字样不动，零 diff）。

**零 diff 核对**：`_PARSE_FAILURES`（8 项）、`_invalid_file_on_parse_failure`、`_close_workbook`、`_parse_csv`、`parse_records`、`with _invalid_file_on_parse_failure("xlsx", …)` 块体、`lxml` 条件追加逻辑（位置仍在元组之后）全部未改；未新增 `try:`/`except`，无独立 `except OSError` 分支，`OSError` 未进入 `_PARSE_FAILURES`。`git diff --stat` = `1 file changed, 10 insertions(+), 1 deletion(-)`。

### 9.2 白名单类别数

| 路径 | 改前 | 改后 |
| --- | --- | --- |
| `.xlsx` 有效白名单 | 10 类（`_PARSE_FAILURES` 8 + 局部 `InvalidFileException` + 条件 `lxml.etree.LxmlError`） | **11 类**（+ `OSError`） |
| CSV | 8 类 | 8 类（不变） |

本机 `openpyxl.LXML=True` / `lxml 5.2.1`，故 11 类全量在位；无 lxml 环境为 10 类（`LxmlError` 缺席），`OSError` 条目与环境后端无关。

### 9.3 事实披露更新（撤回 §5 第 2 条）

- **撤回**：§5 第 2 条「`[Content_Types].xml` 可读但未声明 workbook 部件 → **500**（改前 422）」不再成立。改后该输入为 **422 `IMPORT_INVALID_FILE{reason:"unreadable"}`**，`type(__cause__) is OSError`（`File contains no valid workbook part`）。即改前/改后均为 422，**不再存在「拒绝由 422 退化为 500」的收窄**（architecture §15.10.6 R-6 同步登记）。
- **仍然成立**：§5 第 1 条（`MemoryError`/`RecursionError`/`SyntaxError`/`AttributeError`/`TypeError`/`IndexError` 等未入白名单类型在 `.xlsx` 路径 500，改前曾 422）不变——`OSError` 是本路径唯一实测可达缺口，未连带放宽其它类型。
- **§7.2 F037-BE-01**：状态由「MEDIUM，待裁定」改为**已裁定并闭环**（DR-F037-08：仅在 `_parse_xlsx` 局部入表，未整体加入 `_PARSE_FAILURES`）。
- **§2.6 样本矩阵**：行「`[Content_Types].xml` 可读但未声明 workbook 部件」的结果由「500 逃逸」更正为「422 `unreadable` / `__cause__=OSError`」（见 §9.4 实测）。§2.6 标题所述「10 例 422」随之变为 11 例 422（矩阵行数不变，仅该行结论更新）。

### 9.4 自检（真实输出）

```text
$ cd backend && python3 -m compileall -q app/services/resource_import.py && echo compile-ok
compile-ok

$ grep -n "OSError" app/services/resource_import.py
505:    # OSError 是 openpyxl 的「包不是 workbook」信号（DR-F037-08）：zip 可读但
512:        OSError,
（仅 `_parse_xlsx` 局部构造 + 其注释，无其它命中）

$ grep -nE 'except SyntaxError|except Exception' app/services/resource_import.py
476:    except Exception as exc:  # noqa: BLE001 - cleanup boundary, not a 4xx/5xx signal   （既有 _close_workbook 清理边界，零 diff）
509:    # 不会被掩盖；不得在此块内新增真实 I/O（L7'），不得放宽为 except Exception。      （本轮注释文本命中）
1019:    except Exception:                                                                （既有 write_import 回滚边界，零 diff）
（无 `except SyntaxError`；两处 `except Exception` 均为改前既有且不在解析分类作用域）

$ grep -nE 'open\(|Path\(|NamedTemporaryFile|requests\.|session\.' app/services/resource_import.py || echo 'no real-io in module'
no real-io in module     （L7′ 成立：with 块内无真实 I/O，且块体零 diff）

$ git diff -U0 -- backend/app/services/resource_import.py | grep -nE 'field_size_limit|strict=True' || echo 'no cap/strict change'
no cap/strict change     （CSV 字段上限 / 严格引号零改动）
```

BE-01 行为自检（缺 workbook 部件的 zip，真实 payload，非注入）：

```text
precondition ok: OSError File contains no valid workbook part
manifest-no-workbook -> IMPORT_INVALID_FILE {'reason': 'unreadable'} cause: OSError
```

环境：Python 3.12.7 / openpyxl 3.1.5 / `openpyxl.LXML=True` / lxml 5.2.1；`_PARSE_FAILURES` 实测 8 项（`csv.Error`、`BadZipFile`、`LargeZipFile`、`zlib.error`、`ElementTree.ParseError`、`NotImplementedError`、`KeyError`、`ValueError`）——零 diff。

### 9.5 回归（本轮实际执行，真实 PostgreSQL 可用）

`TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test'`（容器 `csm-f037-pg`，postgres:16-alpine，库名含 `test`）：

```text
$ python3 -m pytest tests/integration/test_imports.py -q
29 passed in 56.26s
（含四端点解析期 422 用例；本轮之前该模块在无 PG 环境下为 1 passed / 28 skipped）

$ python3 -m pytest tests/integration/test_f023_resource_interface_ip_import.py tests/integration/test_import_tester_acceptance.py -q
1 failed, 36 passed in 838.22s
FAILED tests/integration/test_f023_resource_interface_ip_import.py::test_perf03_near_max_rows_baseline
  AssertionError: 685.4837610899995
  assert 685.4837610899995 < 600
  [PERF-03] file=320476B rows=5000 validate=119.61s validate_peak=7.9MB write=685.48s write_peak=12.8MB
```

**该失败不归因于本轮改动**：`test_perf03` 是 5000 行批量写入的**耗时上限**断言（`write_seconds < 600`），本轮改动仅在解析异常白名单元组上追加一个类型，仅在抛异常时被解释器查找，不影响任何成功路径的解析/写入耗时；同批 36 项（含四端点 422 与 F023 复用路径）全部通过。该阈值属 TEST 阶段环境/性能事项（宿主机负载相关），本轮未改测试文件（不在写面内），如实登记不修绿。

### 9.6 本轮未验证项（明示）

1. **TD-F037-U13 / U4（11 类参数化）/ U14 / I22 / S7**：属 Tester 范围（测试文件不在本轮写面），本轮仅以真实 payload 证明 `parse_records` 层 422 + `__cause__=OSError`；4 端点 × 该字节的 HTTP 断言由 TEST 执行（`test_imports.py` 29 项通过只覆盖其现有用例集，未含 BE-01 样本）。
2. **无 lxml 环境（生产镜像形态，`openpyxl.LXML=False`）**：未执行，结论不外推（R-11 / OPEN-T5）。`OSError` 条目与环境无关，故该环境同样应得 422，但未实测。
3. **`EOFError`（截断成员读取路径）**：按 §15.10.6 仅登记为待探测项，未主张可达或不可达。

**本轮结论**：BE-01 按 §15.10.3 落码完成，§15.10 授权行为（缺 workbook 部件 → 422）已实测；未新增设计外行为，契约（F014 v1 / F023 v2 附注）零 diff。

**GIT（repair round 1，逐条列出实际执行的只读命令）**：

```text
GIT: git rev-parse --short HEAD
GIT: git status --short
GIT: git -C .. diff --stat
GIT: git diff --stat
GIT: git diff -U0 -- backend/app/services/resource_import.py | grep -nE 'field_size_limit|strict=True'
GIT: git diff -- backend/app/services/resource_import.py
```

（以上均为只读；未执行 `git add` / commit / branch / merge / stash / reset / clean。其中两条 `git diff` 首次在 `backend/` 下以仓库根相对 pathspec 执行未匹配到文件、输出为空，随后在仓库根重跑取得真实 diff，故两次命令均如实列出。）
