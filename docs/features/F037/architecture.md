# F037 导入解析异常统一收敛为 422 IMPORT_INVALID_FILE — ARCHITECTURE 阶段报告

- **状态**：**READY FOR DESIGN** → **CONTRACT Gate 已签核（READY FOR IMPLEMENTATION，2026-10-29，见 §15.9）**
- **版本**：v1（2026-10-29）；FEATURE / P0 / M28；分支 `feature/F037-import-parse-error-contract`（交付线 `v3.4`，start_commit `1c0eeaf`）；**plan revision 25**；**requirements revision 16**
- **角色产物**：architect 只读产出，协调器持久化。
- **上游依据**：用户 2026-10-29 AQ-3 = A（CONFIRMED）；`docs/features/F037/product.md` v1（S1–S7、B1–B12、A1–A22）；`docs/api/F014.md` v1 §1.2/§2/§7/§9/§10；`docs/api/F023.md` v2 §1.2/§2/§7/§12；requirements revision 16 §24 / §24.1 / §24.5 / §22 / §23 / §23.2 / §31 T27、T28、T72、T107–T116（含 T114 追认）、T124、T126 / §32；CHG-015（APPROVED）§2 不变项、§3 R02 处置、§5 历史保护；plan revision 25 F037 条目；既有设计消费：`docs/features/F034/architecture.md` §12 TD-I-1/TD-I-2、`docs/features/F036/architecture.md` §3/§12、`docs/database/f014-import.md` v1（NOT_REQUIRED）、`docs/database/f023-import.md`（NOT_REQUIRED）。
- **代码与测试基线（只读核对）**：`backend/app/services/resource_import.py`（`parse_records` / `_parse_csv` / `_parse_xlsx` / `parse_and_validate` / `write_import`，:419–459、:790–836）、`backend/app/services/resource_interface_ip_import.py`（`parse_and_validate` :1194–1240 复用 `resource_import.parse_records`）、`backend/app/api/v1/imports.py`（四端点，校验顺序注释 :1–10）、`backend/app/core/errors.py`（`ImportInvalidFile` :204–232、`_app_error` handler :293–296、500 handler :324–328）、`backend/app/core/logging.py`（`SensitiveDataFilter`）、`backend/tests/conftest.py`、`backend/tests/integration/{test_imports.py,test_f023_resource_interface_ip_import.py,test_f034_csv_text_carrier.py,f015_helpers.py}`。

## 1. 方案摘要

**性质**：既有契约内的实现缺陷修正。解析阶段失败按 F014 §1.2/§2 与 F023 v2 §1.2/§2 本应落在「解析 422」档位，但两条解析路径各有一处未覆盖的迭代期异常，逃逸为 500 `INTERNAL_ERROR`。

| 载体 | 失败点（代码事实） | 现状 | 目标 |
| --- | --- | --- | --- |
| CSV | `csv.reader(io.StringIO(...))` **迭代期** `_csv.Error`（单字段 > `csv.field_size_limit` 131072），`_parse_csv` :424–425 无捕获 | 500 `INTERNAL_ERROR` | 422 `IMPORT_INVALID_FILE{reason:"unreadable"}` |
| `.xlsx` | `load_workbook` :437–442 已用 `except Exception` 兜住；`worksheet.iter_rows(...)`（:447–451）为**延迟解析**，XML 结构错误在此抛出 | 500 `INTERNAL_ERROR` | 同上 |

**唯一改动点**：`backend/app/services/resource_import.py` 单文件（新增 1 个模块级白名单常量、1 个私有 context manager、1 个 best-effort close 助手，重写 `_parse_csv` / `_parse_xlsx` 的异常边界）。`parse_records` 签名、返回类型与语义不变；路由、错误层、F023 service、Schema、模板、上限、权限、Audit、原子性零改动。

四个端点全覆盖的传递链：

```
POST /imports/resources{,/validate}               -> resource_import.parse_and_validate -> parse_records
POST /imports/resource-interfaces-ips{,/validate} -> unified.parse_and_validate(:1200)     -> parse_records
```

全仓 `parse_records` 仅两个调用点（`resource_import.py:800`、`resource_interface_ip_import.py:1200`），均位于各自 `parse_and_validate` 首部，故在 `parse_records` 内部收敛即覆盖 4 端点的预校验与写入两条路径。不新增第二处转换（避免双载体 / 双模板口径漂移）。

## 2. DR-F037-01 共享落点与具体设计

### 2.1 设计约束

1. `parse_records` 是 F014 / F023 共享的唯一解析入口（`resource_import.py:455`）。
2. 不上移到 `parse_and_validate` 或路由（路由无「解析阶段」语义；F023 会重复定义）。
3. **不引入流式包装**：`parse_records` 必须继续返回完全物化的 `list[list[str]]`，两个 `parse_and_validate` 依赖物化结果做「尾部空行裁剪 → 行数上限 → 表头 → 逐行」，行号口径建立在物化索引上。改为惰性/逐行消费会同时改变 T111 行数语义、T113 尾部空行语义与 §2 顺序（属 F038）。
4. 不引入通用解析异常框架：仅一个私有 context manager + 一个白名单常量。
5. 归一位（`_cell_text`）移出转换作用域：白名单只包第三方解析代码，编程错误不被静默转成 422。

### 2.2 目标代码（`backend/app/services/resource_import.py`）

```python
import logging
import zipfile
import zlib
from contextlib import contextmanager
from xml.etree import ElementTree
from collections.abc import Iterator

logger = logging.getLogger("csm.imports")

#: 白名单：唯一被收敛为 IMPORT_INVALID_FILE{unreadable} 的解析器异常。
_PARSE_FAILURES: tuple[type[BaseException], ...] = (
    csv.Error,               # CSV 迭代期，如单字段超过 csv.field_size_limit
    zipfile.BadZipFile,      # 非 zip / 中央目录损坏 / CRC 不符
    zipfile.LargeZipFile,    # ZIP64 声明超限
    zlib.error,              # deflate 流损坏或截断
    ElementTree.ParseError,  # workbook / sheet XML 结构损坏（含 read_only 延迟解析）
    NotImplementedError,     # 容器声明了不支持的压缩方法
    KeyError,                # zip 缺少必需部件（[Content_Types].xml / xl/workbook.xml）
    ValueError,              # openpyxl 坐标 / 值域 / 日期解析失败
)


@contextmanager
def _invalid_file_on_parse_failure(
    fmt: str,
    size: int,
    failures: tuple[type[BaseException], ...] = _PARSE_FAILURES,
) -> Iterator[None]:
    """把白名单内的解析器异常收敛为 422 IMPORT_INVALID_FILE{unreadable}。"""
    try:
        yield
    except AppError:
        # 原因保真：已带明确 reason 的业务拒绝永不被改写为 unreadable。
        raise
    except failures as exc:
        # 只记录白名单字段：不含上传内容、异常消息文本、文件名或堆栈。
        logger.info(
            "import parse rejected: format=%s bytes=%d error=%s",
            fmt, size, type(exc).__name__,
        )
        raise ImportInvalidFile("unreadable") from exc


def _close_workbook(workbook: Any) -> None:
    """Best-effort 释放 read_only workbook 的归档句柄。

    close() 自身失败既不能归因用户输入，也不得覆盖已判定的解析结论
    （否则 422 会被第二次异常改写回 500）；故此处刻意吞掉清理异常，
    只按类别留一条 content-free 日志。
    """
    try:
        workbook.close()
    except Exception as exc:  # noqa: BLE001 - 清理边界，不参与 4xx/5xx 判定
        logger.info("import workbook close failed: error=%s", type(exc).__name__)
```

```python
def _parse_csv(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportInvalidFile("unreadable") from exc
    with _invalid_file_on_parse_failure("csv", len(data)):
        raw_rows = list(csv.reader(io.StringIO(text, newline="")))
    return [[_cell_text(cell) for cell in row] for row in raw_rows]


def _parse_xlsx(data: bytes) -> list[list[str]]:
    if not data.startswith(b"PK\x03\x04"):
        # Non-OOXML payload (.xls OLE2, plain text, ...)。
        raise ImportInvalidFile("unsupported_format")
    try:
        from openpyxl import load_workbook
        from openpyxl.utils.exceptions import InvalidFileException
    except ImportError as exc:  # pragma: no cover - dependency guaranteed
        raise ImportInvalidFile("unsupported_format") from exc

    workbook = None
    try:
        with _invalid_file_on_parse_failure(
            "xlsx", len(data), _PARSE_FAILURES + (InvalidFileException,)
        ):
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            if not workbook.worksheets:
                raise ImportInvalidFile("empty_file")
            worksheet = workbook.worksheets[0]
            raw_rows = list(worksheet.iter_rows(values_only=True))
    finally:
        if workbook is not None:
            _close_workbook(workbook)
    return [[_cell_text(cell) for cell in row] for row in raw_rows]


def parse_records(data: bytes, fmt: str) -> list[list[str]]:
    """Parse CSV/xlsx bytes into logical rows (header is record 1)."""
    if not data:
        raise ImportInvalidFile("empty_file")
    return _parse_csv(data) if fmt == "csv" else _parse_xlsx(data)
```

**兼容性声明**：`parse_records(data: bytes, fmt: str) -> list[list[str]]` 不变；`_parse_csv` / `_parse_xlsx` 仍为私有；`_cell_text` 不变；`openpyxl` 仍惰性导入（保留「依赖缺失 → `unsupported_format`」路径）；`InvalidFileException` 仅在 `_parse_xlsx` 内以 `failures=` 并入，不改变白名单单一来源。

## 3. DR-F037-02 异常白名单与必须排除项

### 3.1 捕获（白名单）

| 异常类型 | 触发位置 | 输入形态 | 依据 |
| --- | --- | --- | --- |
| `csv.Error` | `_parse_csv` 迭代期 | 单字段 > `csv.field_size_limit`（默认 131072）等 CSV 结构性拒绝 | R02 复现 A；F014 §1.2「不可解码 / 损坏」 |
| `zipfile.BadZipFile` | `load_workbook` 或迭代期 | 非 zip / 中央目录损坏 / 截断 / CRC 不符 | 「损坏」 |
| `zipfile.LargeZipFile` | `load_workbook` | ZIP64 声明超过解释器上限 | 「损坏」 |
| `zlib.error` | 迭代期（`ZipExtFile` 解压成员） | deflate 流损坏 / 截断 | 「损坏」 |
| `ElementTree.ParseError` | 迭代期（`read_only` 延迟解析），亦可能在 `load_workbook` | XML 结构损坏、结束标签不匹配、空文档 | R02 复现 B；F014 §7 |
| `NotImplementedError` | `load_workbook` / 迭代期 | 容器声明不支持的压缩方法 | 「损坏」 |
| `KeyError` | `load_workbook` | zip 缺少必需部件 | 「损坏」 |
| `ValueError` | `load_workbook` / 迭代期 | openpyxl 坐标 / 值域 / 日期解析失败 | 「损坏」 |
| `InvalidFileException`（openpyxl） | `load_workbook` | openpyxl 判定容器不可读 | 「不可解码」 |

全部映射为同一结果：422 `IMPORT_INVALID_FILE`，`details == {"reason": "unreadable"}`（无 `missing_columns` / `unknown_columns`）。不区分异常类型到 `reason`（`reason` 集合零新增）。白名单只作用于第三方解析调用区；`data.decode` 的既有 `UnicodeDecodeError → unreadable` 独立保留。

### 3.2 必须排除（不得捕获）

| 异常 | 为何排除 | 最终表现 |
| --- | --- | --- |
| `AppError`（含 `ImportInvalidFile` 各 reason、`ImportFileTooLarge`、`ImportRowLimitExceeded`、`ImportValidationFailed`、`ValidationError`） | 原因保真优先：`empty_file` / `unsupported_format` / 表头类 reason 是已签核精确原因，改写会破坏 T110/T112（B1/B2/B6） | 原状态码与原 `details` 原样透传 |
| `MemoryError` | 内存耗尽不是「文件不可解码」的证据；product N7/B7 明确不归入 `unreadable` | 500 `INTERNAL_ERROR`（`message` 固定 `Internal server error`，`details {}`）+ 既有脱敏 `logger.exception`；真耗尽时进程行为不可保证（`NOT TESTED`） |
| `RecursionError` | 解析器对上传字节的递归深度异常几乎总是实现/库缺陷信号；且为 `RuntimeError` 子类，捕获会吞掉整个 `RuntimeError` 族 | 500 `INTERNAL_ERROR`；记录为接受的残余（§11 R-1） |
| `KeyboardInterrupt` / `SystemExit` | 用户/运维中断与进程退出语义 | `BaseException` 子类，天然不捕获，语义不变 |
| 未白名单的其它 `Exception`（`AttributeError`/`TypeError`/`IndexError`/`AssertionError`/`OverflowError`） | 多为编程错误或库版本漂移；转 422 会永久隐藏缺陷 | 500 `INTERNAL_ERROR`（B8「只缩小 500 适用范围」） |

**禁止 `except Exception` 泛捕**：解析分类边界只有 `except AppError: raise` + `except failures` 两个子句。唯一保留的 `except Exception` 位于 `_close_workbook` 清理边界（不参与 4xx/5xx 判定、不读取上传内容、只记录异常类别）。

**事实披露（行为收窄，非纯加法）**：改前 `load_workbook` 处的 `except Exception` 会把 `MemoryError` / `RecursionError` / 未识别类型也转成 `unreadable`；改后这些类型回到 500。这是 product B7 的强制要求，必须在 CONTRACT / 实现报告中登记为可观察变化。

## 4. DR-F037-03 生命周期与判定顺序

| # | 约束 | 落法 | 禁止 |
| --- | --- | --- | --- |
| L1 | `read_only=True, data_only=True` 保持 | 原样保留 | 改大文件模式 / `data_only=False` / `keep_vba` |
| L2 | `close()` 在 `finally` | `workbook = None` + `finally: if workbook is not None: _close_workbook(workbook)` | close 放在 try 主体末尾（抛错时泄漏）；放在转换作用域内（close 异常被转成 unreadable） |
| L3 | close 异常不得覆盖已判定 422 | `_close_workbook` 吞异常 + content-free 日志；`finally` 不 `raise`/`return` | 裸 `finally: workbook.close()`（R02 复发路径） |
| L4 | `empty_file` 顺序不变 | `parse_records`：`if not data` 在 dispatch 前；`_parse_xlsx` 内 `if not workbook.worksheets` 在 PK 闸门之后、`iter_rows` 之前；`parse_and_validate` 的空判定与尾部空行裁剪不变 | 空判定挪动导致 `empty_file` 被 `KeyError`/`ValueError` 抢先或走 `iter_rows` 抛 `IndexError` |
| L5 | `unsupported_format` 顺序不变 | PK 魔数检查在任何解析器调用前；`ImportError` 分支保留 `unsupported_format` | 让 `InvalidFileException` 覆盖 `.xls` 分类 |
| L6 | 大小 / 行数 / 表头 / 逐行顺序 | 完全不动 `parse_and_validate` | 借改动重排或改上限 |
| L7 | 无副作用 | 全在纯函数内，不触 DB、不加锁、不写 Audit、不落盘 | 在解析层加审计/日志内容 |

## 5. DR-F037-04 错误文案与信息保护

### 5.1 `message` 定稿

不新增自定义消息，走既有 `ImportInvalidFile` 默认文案：

```json
{"error": {"code": "IMPORT_INVALID_FILE", "message": "Invalid import file", "details": {"reason": "unreadable"}}}
```

不含上传内容、内部异常类名、路径、堆栈、行号/列名；`details` 仅 `{"reason":"unreadable"}`；`core/errors.py` 零 diff。

### 5.2 日志策略

| 项 | 定稿 |
| --- | --- |
| 是否记录 | 记录一条 `INFO`，事件串固定 `import parse rejected`（清理失败为 `import workbook close failed`），logger 名 `csm.imports` |
| 白名单字段 | `format`（csv/xlsx）、`bytes`（整数）、`error`（异常**类名**，有限集合）、`stage`（仅清理行，值 `close`） |
| 明确不记录 | 上传内容片段、单元格/字段值、XML 片段、文件字节、客户端 `filename`、`Content-Type`、`str(exc)` 消息文本、`args`/`repr`、`exc_info`/堆栈（禁止 `logger.exception`）、`details`、行号 |
| 端点 | 不记录（服务层无请求上下文；为拿端点而透传 `Request` 属新增职责） |
| 与既有 filter 的关系 | `SensitiveDataFilter` 继续作为纵深防御；本设计不依赖它脱敏（内容不进入日志参数） |

## 6. DR-F037-05 契约处置（不升版编辑性澄清附注）

### 6.1 处置结论

需要改契约，但仅不升版编辑性澄清附注（先例 F035-RV-05 / F036-RV-05），在 CONTRACT 阶段签核。`docs/api/F014.md` 仍 v1、`docs/api/F023.md` 仍 v2；不新增增补节、不改正文条款、不动修订表既有行（仅追加一行）。单一定义来源为 F014 §1.2，F023 只引用。不新增拒绝条件、不扩大可拒绝输入集合、不新增 `reason`/码/字段/上限。

### 6.2 附注定稿文本（逐字可落稿）

**A. `docs/api/F014.md` §1.2 末尾追加**（插入位置：`- 4 个新码为独立 error code，非 \`CONFLICT\`，**不进入 F002 §1.2.1 reason 注册表**。` 之后，作为该节最后一条 bullet）：

```markdown
- **解析阶段异常归类澄清（F037，2026-10-29，不升版）**：§2 校验顺序中「解析(422 `IMPORT_INVALID_FILE`)」一档覆盖**解析器在解析/迭代阶段本身抛出异常**的输入，归入本表既有 `details.reason = "unreadable"`（「不可解码 / 损坏」）；不新增 `reason` 、错误码、`details` 键或上限。覆盖范围：CSV 迭代期 `csv.Error`（如单字段超过 `csv` 默认字段上限）、`.xlsx` 的 zip 容器与 XML 结构错误（含 `load_workbook` 成功后的延迟解析失败）。本澄清**不新增拒绝条件、不扩大可拒绝输入集合**：此类输入按本表口径本就属 `unreadable`。同时明确：不调整 `csv.field_size_limit`、不启用严格 CSV 引号规则（§「CSV 文本载体（加法引用）」解释性附注 1 的等价性口径不变），§6 模板列集与列序、§7 解析与行号、§8 原子性与再校验、§10 上限数值，以及 §2 的 401 → 403 → `format` 422 → 413 → 解析 422 → 413 → 表头/列 422 → 逐行的顺序均不变。响应面：`message` 为 `ImportInvalidFile` 既有默认文案，`details` 仅含 `{"reason":"unreadable"}`，不回显上传内容、内部异常类名、路径或堆栈。`empty_file` / `unsupported_format` / `header_missing` / `missing_columns` / `unknown_columns` / `column_order` 的触发条件与先后顺序不变；`MemoryError` / `RecursionError` 及未识别异常仍为 500 `INTERNAL_ERROR`，`KeyboardInterrupt` / `SystemExit` 维持进程与中断语义。
```

**B. `docs/api/F014.md` §13 修订表追加一行**：

```markdown
| 解析阶段异常归类澄清（不升版，正文仍 v1） | 2026-10-29 | §1.2 增补一条归类澄清：解析器在解析/迭代阶段抛出的已知异常归入既有 `unreadable`（CSV 迭代期 `csv.Error`、`.xlsx` zip / XML 结构错误含 `load_workbook` 后的延迟解析）；不新增拒绝条件、不扩大可拒绝输入集合、不调整 `csv.field_size_limit`、不启用严格引号规则、不新增码 / `reason` / `details` 键 / 字段 / 上限；`empty_file` / `unsupported_format` / 表头类 `reason` 与 §2 校验顺序不变；`MemoryError` / `RecursionError` 与未识别异常仍 500 | F037 CONTRACT Gate（plan revision 25；requirements revision 16 §24 / §24.5 / §31 T27 / T28 / T72 / T107–T116 / T126；用户 2026-10-29 AQ-3 = A；附注定稿文本见 `docs/features/F037/architecture.md` §6.2） |
```

**C. `docs/api/F023.md` §1.2 末尾追加**（插入位置：`- 所有行级业务拒绝统一进入 \`RowError\`…**导入端点不产生 409**。` 之后）：

```markdown
- **解析阶段异常归类澄清（F037，2026-10-29，不升版）**：§2 校验顺序中「解析(422 `IMPORT_INVALID_FILE`)」一档覆盖解析器在解析/迭代阶段本身抛出异常的输入，归入本表既有 `IMPORT_INVALID_FILE` 的 `details.reason = "unreadable"`；口径与 `docs/api/F014.md` §1.2 同名澄清**完全一致**（该处为唯一定义来源，本节不重复定义）。覆盖：CSV 迭代期 `csv.Error`、`.xlsx` 的 zip / XML 结构错误（含 `load_workbook` 成功后的延迟解析失败）。本澄清不新增错误码、`reason` 取值、`details` 键、响应字段、上限或权限项，不新增拒绝条件、不扩大可拒绝输入集合，不调整 `csv.field_size_limit`、不启用严格 CSV 引号规则（§「CSV 文本载体（加法引用）」解释性附注 1 不变）；§6 的 26 列模板与列序、§7 行号口径、§8–§12 的分组/合并、Network 解析、原子性、再校验与确定性锁序、§14 上限、四个端点与 `created` 计数口径均不变。四个端点（`/imports/resources{,/validate}`、`/imports/resource-interfaces-ips{,/validate}`）同口径；响应 `message` 为默认文案、`details` 仅含 `{"reason":"unreadable"}`，不回显上传内容或内部异常信息；`MemoryError` / `RecursionError` 及未识别异常仍为 500 `INTERNAL_ERROR`，`KeyboardInterrupt` / `SystemExit` 维持进程与中断语义。
```

**D. `docs/api/F023.md` §17 修订表追加一行**：

```markdown
| 澄清（不升版，正文仍 v2） | 2026-10-29 | §1.2 增补一条解析阶段异常归类澄清：与 `docs/api/F014.md` §1.2 同名澄清同口径（单一定义来源），归入既有 `IMPORT_INVALID_FILE{reason:"unreadable"}`；四个端点同口径；不新增码 / `reason` / `details` 键 / 字段 / 上限 / 权限，不改 26 列模板与列序、行号、分组/Network/原子性/锁序、`created` 计数 | F037 CONTRACT Gate（plan revision 25；requirements revision 16 §24 / §24.1 / §24.5 / §31 T64–T72 / T107–T116 / T124 / T126；用户 2026-10-29 AQ-3 = A；附注定稿文本见 `docs/features/F037/architecture.md` §6.2） |
```

### 6.3 措辞自检（Review 可机械核对）

1. 附注未出现「新增拒绝」「新增 `reason`」「新增上限」「启用严格解析」（只有排除式否定）。
2. 未把 T114 等价性口径改成严格拒绝。
3. 未改变 `empty_file` 优先级（B1/T110）。
4. `MemoryError` / `RecursionError` 明确留在 500（B7）。
5. 正文版本号（F014 v1 / F023 v2）与既有修订表行保持不变。

## 7. 变更边界（本 Feature 不做）

| 类型 | 禁止事项 |
| --- | --- |
| 拒绝口径 | 新增拒绝条件 / `reason` / 错误码 / `details` 键；改 `empty_file`、`unsupported_format`、表头类 reason 的触发与顺序；行级字段长度错误（AQ-3=B） |
| 配置与上限 | 改 `csv.field_size_limit`；启用严格引号或其它严格解析开关；改 5 MiB / 5000 行 / 预览 1000；新增配置项 |
| 契约面 | 改端点、方法、请求字段、响应 Schema、`format` 取值、模板列集与列序、权限矩阵、§23.2 范围；改 `core/errors.py` |
| 数据面 | Schema / Migration / 索引 / 约束 / 触发器；事务边界、SAVEPOINT 结构、写入顺序、锁序；Audit 口径 |
| 结构 | 引入流式解析（F038）；改 `parse_records` 返回类型；新增通用解析框架；新增运行时依赖（含 `lxml`）；前端改动 |
| 其它 | 顺手重构 `parse_and_validate` / `_resolve_template` / 逐行校验；改 F001–F036 历史证据 |

**升级到用户 / 变更控制的条件**：① 需新增或收窄业务规则；② 契约面变化超出 §6.2 附注；③ 出现 Schema 需求；④ 需改变 `parse_records` 返回形态或引入流式解析（与 F038 合并）；⑤ plan 的 `layers` / `api_required` 变化。

## 8. Domain / Data Impact

无新对象 / 关系 / 状态 / 唯一性 / 生命周期 / 权限项 / 范围语义变化。`layers.database=false` → `NOT_REQUIRED`（本改动不触任何 SQL、表、列、索引、约束、触发器、Migration、事务边界与写入顺序；解析阶段抛异常时尚未开始任何写入）。`docs/database/f014-import.md` v1 与 `f023-import.md` 的 `NOT_REQUIRED` 继续成立。

data-integrity 对照：

| 规则 | 入口 | DB 保证 | 业务层保证 | 本次影响 |
| --- | --- | --- | --- | --- |
| §24-2 / T27 / T123 整批原子、拒绝零残留 | 4 端点写入 | 单事务 + SAVEPOINT（不变） | 解析失败发生在任何 `begin_nested()` 之前 | 不变（提前失败只减少写入机会） |
| §22 Audit 同事务 | 4 端点写入 | `audit_logs` append-only | 每对象 CREATE Audit（不变） | 不变（拒绝请求零 Audit） |
| §24.5 / T107–T116 双载体等价 | CSV 文件/文本载体 | — | 载体只决定 multipart 产生方式 | 不变（转换在字节入口之后） |
| §7 同 cluster hostname 唯一等 | 4 端点 | 三条部分唯一索引（不变） | 逐行校验（不变） | 不变 |
| 1-based 行号 / `RowError` 形状 | 4 端点 | — | 物化解析列表索引（不变） | 不变 |

## 9. 实施层分工

| Layer | 内容 | 负责 |
| --- | --- | --- |
| L0 | §6.2 附注四处落稿 + CONTRACT 签核 | Architect / 协调器 |
| L1 | `backend/app/services/resource_import.py`：白名单常量 + context manager + `_close_workbook` + 两个解析函数重写 | Backend |
| L2 | 新增 `backend/tests/integration/test_f037_import_parse_errors.py`（U + I） | Tester（先 TEST_DESIGN，TEST 在 L1 后） |
| L3 | 回归套件 + 静态守卫 | Tester |
| L4 | Review（契约—实现—测试一致性、白名单最小性、日志字段、零 diff 守卫） | Reviewer |

`layers.database=false` / `layers.backend=true` / `layers.frontend=false` / `api_required=true`（唯一原因：§6.2 附注，无新端点/字段/码）。

## 10. Test Work — 给 Tester 的 TEST DESIGN 输入

### 10.1 分层与环境分工

| 层 | 用途 | 环境 |
| --- | --- | --- |
| U（服务/纯函数级） | 白名单语义、不吞异常守卫、生命周期（close 次数/异常覆盖）、输入构造有效性证明 | 不需要数据库（`parse_records` 为纯函数） |
| I（API + 真实 PostgreSQL） | 8 例端到端、零写入/零 Audit、401/403 先行、413/表头/行级回归、双载体等价、fd 泄漏 | 必须真实 PG（`TEST_DATABASE_URL`）；不可用时标 `NOT TESTED`，不得用 SQLite/Mock 代替 |
| S（静态守卫） | 契约与常量零 diff、日志无内容、路由清单不变 | 仓库 + `git diff`/grep |

建议新建单一模块 `backend/tests/integration/test_f037_import_parse_errors.py`（U + I 同模块，沿用 `test_f023_*` 先例）。不需要 `pytest.mark.real_scope`（不触 `app.core.access_scope` 符号）；若后续追加行级范围用例则模块须声明该 mark。

### 10.2 两类输入的构造（必须证明「输入确实在解析期失败」）

输入 ①（CSV 单字段超限）：

```python
def oversized_field_csv(headers: list[str], pad: int = 131_073) -> bytes:
    row = [""] * len(headers)
    row[0] = "F37A"
    row[-1] = "x" * pad              # 单字段 > csv.field_size_limit(131072)
    return (",".join(headers) + "\n" + ",".join(row) + "\n").encode("utf-8")
```

- 有效性证明（U）：`with pytest.raises(csv.Error): list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))`。
- 不变量：`131_072 < len(raw) <= 5_242_880`；把实测字节数记入报告；4 端点各用自己模板表头（BM 14 / 26 列），断言 `details` 恰为 `{"reason":"unreadable"}`。

输入 ②（`.xlsx` 结束标签损坏 → 延迟解析失败）：构造正常 xlsx 后重写 zip，把 `xl/worksheets/sheet1.xml` 的 `</worksheet>` 改为 `</workshet>`。

- 有效性证明（U）：`load_workbook(..., read_only=True, data_only=True)` 不抛；`list(ws.iter_rows(values_only=True))` 抛 `ElementTree.ParseError`。
- 不变量：`0 < len(data) < 5_242_880`；`data.startswith(b"PK\x03\x04")`（不被 `unsupported_format` 抢先）。

### 10.3 8 例与断言映射（A1–A8）

4 端点 × 2 输入：422、`error.code=="IMPORT_INVALID_FILE"`、`details=={"reason":"unreadable"}`、`message=="Invalid import file"`、`set(body)=={"error"}`；反例排除：`!=500`、`!=413`、`!=2xx`；同字节重复提交 `resp.json()` 完全相同（A20）。

### 10.4 零写入 / 零 Audit（A9）

计数表：`clusters, resources, bare_metal_details, virtual_machine_details, interfaces, ip_addresses, audit_logs`。Activity 无独立表（由 `audit_logs` 派生），报告须写明「`audit_logs` 计数不变即同时覆盖 Activity」，不得写成「已检查 activity 表」。

### 10.5 401 / 403 先行（A10）

未认证 → 4 端点 × 输入 ① 全部 401 `AUTH_REQUIRED`；VIEWER（`role_client_factory("VIEWER")`）→ 全部 403 `FORBIDDEN{reason:"permission"}`。依赖解析先于 body/服务调用，用例对该顺序断言，不依赖时序假设。

### 10.6 上限与既有原因不回归（A11–A16）

| 用例 | 断言 |
| --- | --- |
| 413 字节 | `monkeypatch` `imports_api.get_settings` → `import_max_file_bytes=10` + 输入 ① → 413 `IMPORT_FILE_TOO_LARGE{limit_bytes:10}` |
| 输入 ① 非 413 | 输入 ① → 422（`len(data) < 5 MiB`） |
| 413 行数 | 5001 行 CSV → 413 `IMPORT_ROW_LIMIT_EXCEEDED` |
| `empty_file` | 空字节与仅表头 → `empty_file`（4 端点各一） |
| `unsupported_format` | `.xls` OLE2 魔数 → `unsupported_format`；`PK\x03\x04` 非 zip → `unreadable` |
| 表头/列类 | 缺列 / 未知列 / 列序不符 → 对应既有 reason（复用既有用例） |
| 行级 | 预校验 200 + `errors[]`；写入 422 `IMPORT_VALIDATION_FAILED`，`RowError` 形状与 1-based 行号不变 |

### 10.7 双载体等价（A17）

同一份字节分别以文件载体 multipart（`filename="f037-file-carrier.csv"`、`text/csv`）与文本载体 multipart（`filename="csm-pasted-import.csv"`、`text/csv;charset=utf-8`）提交 → `status_code` 相同且 `json()` deep-equal；覆盖输入 ① × 4 端点；另加服务级断言 `parse_records` 异常 `details` 与 HTTP 响应逐字段一致。T114 口径不变，F034 等价性套件必须全绿。

### 10.8 「不吞异常」守卫（A19）

U-a 白名单内异常 → `ImportInvalidFile{unreadable}` 且 `__cause__` 为原异常；U-b 参数化 9 类白名单；U-c `AppError` 保真（各 reason + 两 413 + `ImportValidationFailed`）原样抛出；U-d `MemoryError` / `RecursionError` 原样传播；U-e `KeyboardInterrupt` / `SystemExit` 原样传播；U-f `AttributeError`/`TypeError`/`IndexError` 原样传播；U-g `parse_records` 空/`.xls`/坏 zip 顺序与保真；U-h close 抛错时最终仍为 `ImportInvalidFile{unreadable}` 且 close 调用恰好 1 次；U-i close 正常路径调用 1 次、`load_workbook` 失败时不调用；I-a（可选）`MemoryError` 注入 → 500 `INTERNAL_ERROR`（环境不便则标 `NOT TESTED`）。

### 10.9 回归套件与命令（从 `backend/`）

```bash
export TEST_DATABASE_URL='postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/<db_with_test_in_name>'
python3 -m pytest tests/integration/test_f037_import_parse_errors.py -q
python3 -m pytest tests/integration/test_imports.py tests/integration/test_import_tester_acceptance.py \
                 tests/integration/test_import_constraints.py \
                 tests/integration/test_f023_resource_interface_ip_import.py -q
python3 -m pytest tests/integration/test_f034_csv_text_carrier.py \
                 tests/integration/test_f034_csv_text_carrier_scope.py -q
python3 -m pytest tests/integration/test_f035_append_interface_ip_import.py \
                 tests/integration/test_f035_append_scope.py \
                 tests/integration/test_f035_tester_acceptance.py \
                 tests/integration/test_f036_attribution.py \
                 tests/integration/test_f036_tester_independent.py -q
python3 -m pytest tests/integration/test_import_performance.py -q
```

基线计数以 TEST 阶段实跑为准，不得预填；下限参考 F023 28、F034 31、F036 归因 5。

### 10.10 静态守卫（A18 / A21）

```bash
git diff --stat -- backend/app/services/resource_import.py
git diff --stat -- backend/app/services/resource_interface_ip_import.py backend/app/api backend/app/core \
                    backend/app/models backend/alembic frontend
git diff -U0 -- backend/app/services/resource_import.py | grep -nE 'field_size_limit|strict=True|import_max_' || echo 'no cap/strict change'
grep -nE 'logger\.(exception|error)\(' backend/app/services/resource_import.py || echo 'no exception logging'
grep -n 'filename\|exc_info' backend/app/services/resource_import.py || echo 'no filename/exc_info'
```

契约侧：`git diff -- docs/api/F014.md docs/api/F023.md` 只允许 §6.2 两条 bullet + 两行修订记录；版本行仍 v1 / v2。端点清单守卫：`test_reg02_route_inventory`、`test_templates_spec_and_read_permission` 继续通过。日志内容守卫（A18）：`caplog` 后提交输入 ①②，断言 marker 子串、`field larger than field limit`、`filename`、`Traceback` 0 命中（异常类名允许以 `error=<Class>` 形式出现）。

### 10.11 fd / 资源泄漏（R-5 检测）

I 层：同一进程连续提交同一损坏 xlsx 20 次，前后采 `len(os.listdir("/proc/self/fd"))`（不可用则 `skip`），断言不增长；U 层 close 调用次数 spy 作为确定性替代。

### 10.12 明确不在验收范围

行级字段长度错误归因（AQ-3=B）、严格引号拒绝、`csv.field_size_limit` 调整、解析内存峰值与解压工作量边界（F038/R05）、前端改动、真实内存耗尽（`NOT TESTED`）、F001–F036 历史证据回溯。

## 11. 风险与回滚

| ID | 风险 | 级别 | 检测 | 处置 |
| --- | --- | --- | --- | --- |
| R-1 | 白名单过窄（`OverflowError` 或新版本 openpyxl 异常仍逃逸 500） | MEDIUM | 损坏样本矩阵 U 用例：缺 `[Content_Types].xml`、缺 `xl/workbook.xml`（`KeyError`）、deflate 截断（`zlib.error`）、CRC 损坏、不支持压缩方法、sheet XML 损坏、非法坐标（`ValueError`）逐例断言 422 | 新类型按普通设计扩展白名单（Architect 签核，不改契约）；改变 `reason` 分类须走变更控制 |
| R-2 | `close()` 二次抛错覆盖已判定 422（R02 复发） | HIGH | U-h / U-i | 吞清理异常 + `finally` 不 raise/return；Review 检查 `finally` 内无裸 `close()` |
| R-3 | 误吞 `empty_file` / `unsupported_format` | HIGH | U-c、U-g + I 层用例 + 既有 `test_format_and_file_level_errors` | `except AppError: raise`；判定位置不变（L4/L5） |
| R-4 | 影响 F034 双载体等价（T114） | MEDIUM | A17 + F034 两模块 31 项全绿 + grep「服务端不读 filename/Content-Type」 | 转换在字节入口之后；不新增字段边界判定 |
| R-5 | `read_only` 句柄跨请求泄漏 | MEDIUM | fd 计数（20 次不增长）+ close spy | `finally` + `None` 守卫；不缓存 workbook |
| R-6 | 行为收窄被误读为纯加法（`MemoryError`/`RecursionError`/未白名单类型回到 500） | MEDIUM | U-d / U-f；报告登记；附注已写「仍为 500」 | 属 B7 强制要求，事实披露，不静默 |
| R-7 | 新增日志行被判定违反 §24.5「不写日志内容」 | LOW | A18 `caplog` 守卫 + grep + Review 逐字段核对 | 若被判越界则删除该 `logger.info`（不影响任何断言） |
| R-8 | F038 改流式解析后白名单作用域漂移 | MEDIUM | F038 须复用 `_invalid_file_on_parse_failure`；本 Feature 8 例与等价用例在 F038 分支继续成立 | 本设计将转换抽为可复用 context manager |
| R-9 | `ValueError`/`KeyError` 白名单偏宽 | LOW | 作用域限制 + U-f | Review 核对两处 `with` 内只有第三方调用；不放宽到 `except Exception` |
| R-10 | `InvalidFileException` 在 file-object 路径可达性（OPEN-T1） | NOTE | 实现时以 2–3 个畸形容器验证 | 不可达则从 `failures=` 移除（可观察行为不变） |

**回滚**：改动限于单文件、无 Schema、无迁移、无配置；回滚 = 还原 `resource_import.py` 到 `1c0eeaf` + 撤销 §6.2 附注（附注不改变行为）。回滚后新增用例会失败（即缺陷回归的可检测信号），不得删用例修绿。

## 12. OPEN 技术问题

| ID | 问题 | Owner | 阻塞 |
| --- | --- | --- | --- |
| OPEN-T1 | `InvalidFileException` 在 `load_workbook(fileobj)` 路径可达性；不可达时去掉 `failures=` 参数 | Backend | 否 |
| OPEN-T2 | 是否保留 `csm.imports` 两条 content-free INFO 日志（建议保留；删除不影响断言） | 协调器 / 运维 | 否 |
| OPEN-T3 | F038 若流式化须复用该 context manager 并保持 `parse_records` 语义或走变更控制 | Architect（F038） | 否 |
| OPEN-T4 | 真实内存耗尽进程行为不可测（仅以注入证明分类边界） | Tester（标 `NOT TESTED`） | 否 |

## 13. 技术决策记录（本角色签核）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-F037-01 | 转换落点在 `parse_records` 之下的两个解析函数，单一私有 context manager 承载；签名与「全量物化」语义不变；不引入流式包装 | 已定 |
| DR-F037-02 | 白名单 9 类结构性异常；显式排除 `AppError`、`MemoryError`、`RecursionError`、`KeyboardInterrupt`、`SystemExit` 与未识别异常；禁 `except Exception` 泛捕（清理边界除外） | 已定 |
| DR-F037-03 | `read_only/data_only` 与 `empty_file` → `unsupported_format` → 解析顺序不变；`close()` 在 `finally`，异常吞掉且不覆盖已判定结果 | 已定 |
| DR-F037-04 | `message` 复用默认 `Invalid import file`，`details` 仅 `{"reason":"unreadable"}`；`core/errors.py` 零 diff；日志只含 format/bytes/异常类名 | 已定 |
| DR-F037-05 | 契约仅加不升版编辑性澄清附注（F014 §1.2 + F023 v2 §1.2 + 两行修订记录），版本不变；附注见 §6.2，待 CONTRACT Gate 签核 | 已定（文本定稿） |
| DR-F037-06 | `layers={database:false,backend:true,frontend:false}`；`api_required=true`（唯一原因：§6.2 附注）；Database `NOT_REQUIRED` | 已定 |

## 14. 结论

把两条解析路径上逃逸为 500 的已知解析器异常收敛到 F014 §1.2 / F023 v2 §1.2 本已覆盖的 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`，实现面为单文件、单落点、零 Schema、零端点/字段/错误码/上限/权限变化；同时对既有 `except Exception` 做必要收窄以满足「不得吞 `MemoryError` / `RecursionError`」（product B7），并逐项保留 `empty_file` / `unsupported_format` / 表头类 reason、校验顺序、原子性与 Audit 口径。契约面仅需 §6.2 四条不升版附注。

**READY FOR DESIGN** —— 可交 Database（复核 `NOT_REQUIRED`）与 Tester 检查；本阶段不放行编码，实现须待 CONTRACT Gate 签核 §6.2 附注并给出 `READY FOR IMPLEMENTATION`。

## 15. CONTRACT 阶段增补（TD-I-1 裁定与最终签核，2026-10-29）

> 本节由 Architect 在 CONTRACT Gate 出具，与 §1–§14 具有同等效力；与正文冲突时以本节为准。

### 15.1 设计约束增补（对应 §2.1）

6. **lxml 兼容（TD-I-1 裁定，2026-10-29）**：openpyxl 的 `fromstring` 后端随 lxml 是否存在切换（`openpyxl/xml/functions.py`：`LXML` 为真 → `lxml.etree.fromstring`，否则 `xml.etree.ElementTree`；`iterparse` 恒为 ET）。`lxml.etree.XMLSyntaxError` 只继承 `SyntaxError`，不是 `ElementTree.ParseError` 也不是 `ValueError`，故 `.xlsx` 白名单须同时含两类 XML 解析错误。该扩展为**条件构造**（`try: from lxml.etree import LxmlError / except ImportError`），lxml 保持 openpyxl 的可选加速依赖：**不写入 `pyproject.toml`、不改镜像、不得在模块顶层导入**。

### 15.2 白名单增补（对应 §3.1）

| 异常类型 | 触发位置 | 输入形态 | 依据 |
| --- | --- | --- | --- |
| `lxml.etree.LxmlError`（实际可达成员 `XMLSyntaxError`） | `load_workbook`（`fromstring` 路径：`[Content_Types].xml` / `xl/workbook.xml` / `docProps/*` / table / pivot） | 包内部件 XML 结构损坏，且 openpyxl 以 lxml 解析（lxml 可导入时） | 「损坏」；TD-I-1 实测；**条件入表** |

### 15.3 必须排除项增补（对应 §3.2）

| 异常 | 为何排除 | 最终表现 |
| --- | --- | --- |
| `SyntaxError`（含 `lxml.etree.XMLSyntaxError` 所在的 `SyntaxError` 族） | 「代码语法 / 编译」信号，泛捕会吞掉实现错误；`SyntaxError` 携带 `filename`/`text`/`offset`，是内容泄露通道。`XMLSyntaxError` 已按 `LxmlError` **精确**入表，无需父类 | 非白名单异常 → 500 `INTERNAL_ERROR` |
| `lxml.etree.Error`（`LxmlError` 父类）及以上 | 过宽：含注册表 / XSLT / XPath 等非解析族 | 不捕获，保持 500 |

同样禁止 `except SyntaxError`；解析分类边界只有 `except AppError: raise` + `except failures` 两个子句。

### 15.4 `_parse_xlsx` 定稿（替换 §2.2 的 `_parse_xlsx`）

```python
def _parse_xlsx(data: bytes) -> list[list[str]]:
    if not data.startswith(b"PK\x03\x04"):
        raise ImportInvalidFile("unsupported_format")
    try:
        from openpyxl import load_workbook
        from openpyxl.utils.exceptions import InvalidFileException
    except ImportError as exc:  # pragma: no cover - dependency guaranteed
        raise ImportInvalidFile("unsupported_format") from exc

    # openpyxl 的 XML 后端二选一：fromstring 走 lxml（可导入时）；iterparse 恒为 ET。
    # lxml.etree.XMLSyntaxError 只继承 SyntaxError，故两种后端的解析错误类都须入白名单。
    failures: tuple[type[BaseException], ...] = _PARSE_FAILURES + (InvalidFileException,)
    try:
        from lxml.etree import LxmlError  # 可选依赖：openpyxl 在 lxml 存在时启用
    except ImportError:  # pragma: no cover - 镜像未安装 lxml 时回退 ElementTree
        pass
    else:
        failures += (LxmlError,)

    workbook = None
    try:
        with _invalid_file_on_parse_failure("xlsx", len(data), failures):
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            if not workbook.worksheets:
                raise ImportInvalidFile("empty_file")
            worksheet = workbook.worksheets[0]
            raw_rows = list(worksheet.iter_rows(values_only=True))
    finally:
        if workbook is not None:
            _close_workbook(workbook)
    return [[_cell_text(cell) for cell in row] for row in raw_rows]
```

`_parse_csv` / `parse_records` / `_PARSE_FAILURES`（9 类）/ `_invalid_file_on_parse_failure` / `_close_workbook` 不变（`failures=` 参数已存在）。

### 15.5 决策记录增补（对应 §13）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-F037-02（修订） | 白名单 = 9 类结构性异常（`csv.Error`/`BadZipFile`/`LargeZipFile`/`zlib.error`/`ElementTree.ParseError`/`NotImplementedError`/`KeyError`/`ValueError`/`InvalidFileException`）**+ 条件并入 `lxml.etree.LxmlError`**（TD-I-1 裁定 2026-10-29）；显式排除 `AppError`、`MemoryError`、`RecursionError`、`KeyboardInterrupt`、`SystemExit` 与未识别异常；禁 `except Exception` 与 `except SyntaxError` 泛捕（仅 `_close_workbook` 清理边界例外） | 已定 |
| DR-F037-07 | TD-I-1 裁定：lxml 后端 XML 结构错误经 `lxml.etree.LxmlError` 条件入白名单；不改契约附注、不新增 `reason`、不新增依赖 | 已定（2026-10-29，CONTRACT Gate） |

### 15.6 契约附注落稿状态

`docs/api/F014.md` §1.2 末条 bullet + §13 修订表一行、`docs/api/F023.md` v2 §1.2 末条 bullet + §17 修订表一行已按 §6.2 A/B/C/D 逐字落稿；正文版本保持 F014 v1 / F023 v2，无新增 `reason` / 码 / `details` 键 / 字段 / 上限 / 权限。**TD-I-1 裁定不改动附注文本**（附注描述输入形态「XML 结构错误」而非异常类名）。

### 15.7 风险与 OPEN 变化

| ID | 变化 | 结论 |
| --- | --- | --- |
| R-1 | 唯一已实测可达缺口（`lxml.etree.XMLSyntaxError`）已裁定入表 | **MEDIUM → LOW**；残余为未来版本新增异常类（由样本矩阵 + 参数化用例检测）与 `OverflowError`（B8 刻意不捕，非缺陷） |
| R-6 | 新增可观察事实：有 lxml 环境下 `read_manifest` XML 损坏改前 500 → 改后 422；环境差异已消除 | 级别不变（MEDIUM），须在 implementation / test 报告登记 |
| R-11（新增，NOTE） | 环境相关分类差异：生产镜像无 lxml（ET 后端）、开发/测试机有 lxml（fromstring 走 lxml） | 报告须记录 `openpyxl.LXML`；用例面向可观察结果断言，不硬编码异常类 |
| OPEN-T5（新增，非阻塞） | `OPENPYXL_LXML` / `OPENPYXL_DEFUSEDXML` 会改变异常类与解析后端，属可审计性事项 | Owner 协调器 / Tester（TEST 报告记录）；不改契约、不改代码 |
| TD-I-1 | 本轮闭环 | 关闭 |
| TD-I-8（新增，测试设计更正） | 「空 zip → `empty_file`」期望不成立（应先 `KeyError`/`BadZipFile` → `unreadable`）；`empty_file` 须用合法 xlsx 但 `<sheets/>` 为空构造 | Owner Tester，TEST 前修订，不影响设计或契约 |

### 15.8 Test 阶段需补跑（对应 §10）

1. 新增输入 ③（损坏 `[Content_Types].xml`）有效性证明：断言 `load_workbook` 抛出类型**随 `openpyxl.LXML` 分支**（`True` → `XMLSyntaxError`；`False` → `ElementTree.ParseError`），`parse_records` 两种环境均抛 `ImportInvalidFile{unreadable}` 且 `__cause__` 为对应类型；期望不得硬编码成单一后端。
2. 输入 ③ × 4 端点 → 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`，无 500 / 2xx / 413。
3. 白名单参数化 9 → 10 类（新增 `LxmlError` 行；真实 payload 优先，注入兜底用 `monkeypatch.setattr("openpyxl.reader.excel.fromstring", ...)`）；lxml 未安装环境标 `NOT TESTED`。
4. 负向守卫：普通 `SyntaxError("x")` 在作用域内原样传播（证明未用 `except SyntaxError`）。
5. 静态守卫：`git diff -- backend/pyproject.toml backend/Dockerfile` 为空；`grep -n "except SyntaxError"` 无命中；`grep -rn "lxml" backend/app` 仅 `resource_import.py`。
6. 报告必填环境记录：`openpyxl.__version__`、`openpyxl.LXML`、`lxml.__version__`（若装），并声明结论不外推到另一后端环境。
7. 修订 TD-I-8 的空 zip 断言（见 15.7）。

### 15.9 最终设计签核（CONTRACT Gate）

```text
签核：Architect；日期 2026-10-29。
对象：`docs/api/F014.md` v1 §1.2「解析阶段异常归类澄清（不升版）」+ §13 修订表一行；`docs/api/F023.md` v2 §1.2 同名澄清（引用单一定义来源）+ §17 修订表一行。正文版本保持 F014 v1 / F023 v2，不新增 Endpoint / 字段 / 错误码 / `reason` / `details` 键 / 上限 / 权限。
设计版本：`docs/features/F037/architecture.md` v1（2026-10-29，READY FOR DESIGN）+ 本轮 CONTRACT 增补（§15：TD-I-1 裁定）。
上游依据：requirements revision 16 §24 / §24.5 / §31（T27、T28、T72、T107–T116 含 revision 15 T114 追认、T124、T126）；用户 2026-10-29 AQ-3 = A（CONFIRMED，DERIVED_FROM_CONFIRMED）；CHG-015（APPROVED，plan revision 25）§2 不变项 / §3 R02 处置 / §5 历史保护；plan revision 25 F037 条目（layers={database:false,backend:true,frontend:false}、api_required=true）；`docs/features/F037/product.md` v1。
定稿核对：TEST DESIGN TD-F037-1（TEST DESIGN READY，A1–A22 → 34 条用例 + R1–R6，`docs/features/F037/test-report.md`）；Database NOT_REQUIRED（`docs/database/f014-import.md` v1、`docs/database/f023-import.md`，F035 增补「继续成立」）；TD-I-1 已裁定并纳入设计增补；TD-I-2/I-4/I-5/I-6 为登记项不阻塞；TD-I-7（真实 PG）属 TEST 环境事项、不阻塞实现。
覆盖 Feature：F037 仅此一项。
结论：READY FOR IMPLEMENTATION。
```

**放行范围**：只放行 F037 实现（`backend/app/services/resource_import.py` + 新增测试模块）；**不包含 F038 的流式解析改造**。F038 若流式化，须复用 `_invalid_file_on_parse_failure` 与 `_PARSE_FAILURES`（含本轮 lxml 条件条目）并另走自身 Gate。
