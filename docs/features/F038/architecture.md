# F038 导入解压 / 解析内存边界加固 — ARCHITECTURE 阶段报告

- **状态**：**READY FOR DESIGN**
- **版本**：v1（2026-10-29）；FEATURE / P1 / M29；分支 `feature/F038-import-parse-bounds`（交付线 `v3.4`，start_commit `8e609ca2e5b88c30804b6f6ad54a8a57d7906556`）；plan revision 25；requirements revision 16
- **角色产物**：architect 只读产出，协调器持久化。
- **上游依据**：AQ-2 = A（仅实现侧有界解析、零可观察差异）；`docs/features/F038/product.md` v1（S1–S8、B1–B13、A1–A14、ON-1..ON-7）；`docs/features/F037/architecture.md` §2/§3/§15.4/§15.10（DR-F037-08、L7′）、§12 OPEN-T3；`docs/api/F014.md` v1 §1.2/§2/§7/§10/§13；`docs/api/F023.md` v2 §1.2/§2/§4/§7/§14/§17；plan 25 F038（`layers={database:false,backend:true,frontend:false}`、`api_required=false`）。
- **代码基线（逐行只读核对，行号为 start_commit）**：`resource_import.py`：`_invalid_file_on_parse_failure` :441–464、`_close_workbook` :466–477、`_parse_csv` :480–487（`list(csv.reader(...))` :486）、`_parse_xlsx` :490–532（`list(worksheet.iter_rows(...))` :528）、`parse_records` :535–538、`_validate_record` :656–（`padded` :675–676）、`parse_and_validate` :867–918（`records[1:]` :884、尾部空行裁剪 :887–888、413 :891、表头 :894、逐行 :903–918）、`write_import` :950；`resource_interface_ip_import.py`：`_resolve_header` :369–386、`_cells_for` :389–393、`parse_and_validate` :1187–1239（`parse_records` :1200、裁剪 :1205–1206、413 :1207–1208、表头 :1210、`total_rows` :1238）；`backend/tests/integration/test_f037_import_parse_errors.py`（U9 :661–666、S6 :1282–1288、S7 :1290–1313，40 处两参数 `parse_records` 调用）；`test_import_performance.py`（`tracemalloc` + `perf_counter` 先例）；openpyxl 3.1.5 `_read_only.py::_cells_by_row` / `reader/excel.py::read_manifest` / `read_strings`。

## 1. 结论摘要

`parse_records` 现全量物化（CSV :486、xlsx :528），行数上限（5000）在物化后才判（:891/:1207），故峰值 ∝ 展开工作量（行数 × 宽度），5 MiB 只约束压缩后字节。

**结论**：可在零可观察差异下实现。唯一需要「整行」的消费是尾部空行判定（:887–888/:1205–1206）；把它与行数上限上移进 `parse_records`，即可在保持返回形态 `list[list[str]]`、四端点响应逐字段相同的前提下，把保留量压到 `max_rows+1` 行 × `keep_cells` 单元格 + 1 个完整表头行，其余边迭代边丢弃。

**方案**：流式来源 + 有界保留（product 方案 C 的强化形态，§4）。否决 A（§3.1）与纯 B（§3.2）。

## 2. `records` 的消费契约（代码事实）

| # | 消费点 | 位置 | 读取内容 | 读超模板列数 | 依赖尾部空行裁剪 |
| --- | --- | --- | --- | --- | --- |
| C1 | F014 `parse_and_validate` | :884–918 | `records[0]` 整行做表头判定、`records[1:]` 逐行 | 否 | **是**（:887–888） |
| C2 | `_validate_record` | :675–676 | `padded[index]`，`index ∈ [0, len(template.columns))`；多余格不入 dict | 否 | 否 |
| C3 | `_resolve_template` | :542–583 | 表头**整行**（`unknown_columns` 逐格比对） | **是（表头行）** | 否 |
| C4 | F023 `parse_and_validate` | :1200–1238 | `records[0]`→`_resolve_header`；`records[1:]`→`_parse_row`；`total_rows` | 否 | **是**（:1205–1206） |
| C5 | `_cells_for` | :389–393 | `padded[index]`，`index ∈ [0, 26)`；多余格不入 dict | 否 | 否 |
| C6 | `_resolve_header` | :369–386 | 表头**整行** | **是（表头行）** | 否 |
| C7 | 行号 | :905 `index+2`；:1222 `index+2` | 依赖 `data_records` 索引 | n/a | **是** |
| C8 | `total_rows` | :903 / :1238 | `len(data_records)` | n/a | **是** |

判定：①数据行只有「整行是否全空」判定依赖模板列数以外的单元格；②表头行必须整行保留（否则 `unknown_columns` 明细变化）；③行号建立在裁剪后列表索引上，任何改变「哪些行在列表里」的实现都会引起行号位移；④基线先完整解析（异常即 422）再裁剪、再 413、再表头 422，任何提前退出都会把「尾部解析错误 → 422」改写成 413。

→ 有界累积可行的前提：表头整行保留；数据行可裁剪但「整行是否为空」由解析层用整行判定；必须整段排空迭代器；行数上限在排空后判定。

## 3. 候选方案评估

### 3.1 方案 A（全量物化 + 按表头列数裁剪）— 否决

1. 不解决主因：行数上限仍在物化后判定，5001+ 行仍随行数无界。
2. 改变可观察结果：裁剪后 `all(cell == "" for cell in data_records[-1])` 在「前 N 列全空、第 N+1 列非空」的尾部行上与基线相反 → 误裁 → `total_rows`、行号、错误集变化。
3. 不设界：表头可被构造成极宽。

### 3.2 方案 B（纯迭代器 + consumer 改流式）— 否决

流式无法在见表头前判行数（B2/B6），也无法在见文件尾前判尾部空行（B3）；要保持顺序只能两遍扫描（时间 ×2，CSV 需保留 str、xlsx 需重开 workbook）或改成「先到先错」（违反 B6/A6）。且 F023 的 `_merge_and_check` 分组需要全量 `rows`。

### 3.3 方案 C（有界累积 + 继续迭代）— 采纳

补两项不可观察的必要修正：①表头整行保留；②「整行是否为空」由解析层用整行判定（裁剪只作用于保留副本）。

## 4. 定稿设计

### 4.1 设计要点

| # | 要点 | 不可观察性依据 |
| --- | --- | --- |
| D1 | 边迭代边保留，最多 `max_rows+1` 条数据记录；判定超额后释放已保留记录并只继续迭代 | 超额路径必在读取内容前抛 413（B2），内容不可观察 |
| D2 | 保留的数据记录裁剪到 `keep_cells`；**表头整行保留** | C2/C5 证明逐行校验只读前 `len(template.columns) ≤ keep_cells` 列；C3/C6 要求表头整行 |
| D3 | 一段全空记录用计数器处理（不保留），后续出现非空记录时按计数补回占位；文件结束时残留计数即尾部空行，直接丢弃 | 基线 :887–888 语义即「只丢尾部空行」；空记录长度不可观察 |
| D4 | 整段排空后才做行数上限与归一化；`parse_records` 保持返回 `list[list[str]]`，新增可选 `max_rows` / `keep_cells`；行数上限与尾部空行裁剪上移进 `parse_records`（单一来源），两个 consumer 删除重复逻辑 | 顺序仍为 解析 422 → 行数 413 → 表头/列 422 → 逐行；`ImportRowLimitExceeded` 在 `with` 作用域外抛出 |

### 4.2 定稿代码（`backend/app/services/resource_import.py`）

```python
from collections.abc import Iterable, Iterator, Sequence

#: 最宽冻结模板（BM 14 / VM 10）。逐行校验只读前 len(template.columns) 个单元格，
#: 故数据记录的保留宽度取此值。F038 内部界限，永不可观察。
_MAX_TEMPLATE_COLUMNS = max(len(template.columns) for template in TEMPLATES)


def _is_blank_record(values: Sequence[Any]) -> bool:
    """整行归一化后是否全空（B3 尾部空行口径）。

    与 ``all(_cell_text(cell) == "" for cell in values)`` 对两条解析路径可产出的
    取值类型精确等价（CSV 只有 str；openpyxl values_only 只有 str/bool/int/float/
    日期时间/None）。刻意不构造文本：本判定运行在 F037 的 422 作用域**内**，
    不得把归一化异常带进白名单。
    """
    return all(value is None or value == "" for value in values)


@dataclass
class _Collected:
    header: Sequence[Any] | None = None
    rows: list[Sequence[Any]] = field(default_factory=list)
    overflow: bool = False


def _collect_records(records, *, max_rows, keep_cells) -> "_Collected":
    """消费解析行迭代器，保留量有界（F038 / R05）。

    **迭代器一定被排空**：解析器异常照旧在原位置抛出（解析 422 先于行数 413），
    尾部空行/行数结论与基线一致。内存上界 = (max_rows+1) × keep_cells 单元格
    + 1 个完整表头 + 输入字节；时间仍随展开工作量线性增长（不宣称空间与时间
    同时有界）。保留规则见 product B3 / 本文件 D1–D3。
    """
    collected = _Collected()
    cap = None if max_rows is None else max_rows + 1
    pending_blanks = 0
    for record in records:
        if collected.header is None:
            collected.header = record          # 表头整行保留
            continue
        if collected.overflow:
            continue                            # 只为排空：保持解析错误时序
        if _is_blank_record(record):
            pending_blanks += 1                 # 可能是尾部空行：只计数
            continue
        if cap is not None and len(collected.rows) + pending_blanks >= cap:
            collected.overflow = True           # 行数已超额，内容不再可观察
            collected.rows.clear()
            pending_blanks = 0
            continue
        if pending_blanks:                      # 空行落在中间：按位置补回
            collected.rows.extend([()] * pending_blanks)
            pending_blanks = 0
        collected.rows.append(record if keep_cells is None else record[:keep_cells])
    return collected


def _finalise(collected, *, max_rows) -> list[list[str]]:
    """归一化并执行行数上限（在 F037 白名单作用域**之外**）。"""
    if max_rows is not None and (collected.overflow or len(collected.rows) > max_rows):
        raise ImportRowLimitExceeded(max_rows)
    if collected.header is None:
        return []
    rows = [[_cell_text(cell) for cell in record] for record in collected.rows]
    return [[_cell_text(cell) for cell in collected.header], *rows]


def _parse_csv(data, *, max_rows, keep_cells) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportInvalidFile("unreadable") from exc
    with _invalid_file_on_parse_failure("csv", len(data)):
        collected = _collect_records(
            csv.reader(io.StringIO(text, newline="")),
            max_rows=max_rows, keep_cells=keep_cells,
        )
    return _finalise(collected, max_rows=max_rows)
```

`_parse_xlsx` 至 `worksheet = workbook.worksheets[0]` 前全部不变（`failures` 构造、PK 闸门、`empty_file`、lxml 条件条目、DR-F037-08 的 `OSError`）；`with` 块内改为：

```python
            collected = _collect_records(
                worksheet.iter_rows(values_only=True),
                max_rows=max_rows, keep_cells=keep_cells,
            )
```

`parse_records` 增加可选关键字参数：

```python
def parse_records(data: bytes, fmt: str, *, max_rows: int | None = None,
                  keep_cells: int | None = None) -> list[list[str]]:
    """Parse CSV/xlsx bytes into ``[header, *data_rows]``（表头为文件第 1 行）。

    数据行返回前已剔除尾部空行，且每行至多 ``keep_cells`` 个单元格。给出
    ``max_rows`` 时在此执行记录上限——在解析器**整段排空之后**，因此文件中任何
    位置的解析失败仍优先 422。``max_rows`` / ``keep_cells`` 只用于限制内存：
    生产调用点必须同时传入；省略即回到无界物化，仅供单独验证解析层的用例使用。
    """
    if not data:
        raise ImportInvalidFile("empty_file")
    if fmt == "csv":
        return _parse_csv(data, max_rows=max_rows, keep_cells=keep_cells)
    return _parse_xlsx(data, max_rows=max_rows, keep_cells=keep_cells)
```

`resource_import.parse_and_validate`（:867–918）：

```python
    if len(data) > max_file_bytes:
        raise ImportFileTooLarge(max_file_bytes)

    # 顺序不变（Contract §2）：解析 422 → 行数 413 → 表头/列 422 → 逐行。
    # 裁剪与行数判定已归 parse_records（F038，单一来源）。
    records = parse_records(data, fmt, max_rows=max_rows,
                            keep_cells=_MAX_TEMPLATE_COLUMNS)
    if not records:
        raise ImportInvalidFile("empty_file")
    data_records = list(records[1:])
    if not records[0] or all(cell == "" for cell in records[0]):
        raise ImportInvalidFile("header_missing")
    template = _resolve_template(records[0])
    if not data_records:
        raise ImportInvalidFile("empty_file")
    # :900 之后逐行校验与 ImportResult 构造完全不变
```

`resource_interface_ip_import.parse_and_validate`（:1187–1239）：

```python
    if len(data) > max_file_bytes:
        raise ImportFileTooLarge(max_file_bytes)
    records = resource_import.parse_records(
        data, fmt, max_rows=max_rows, keep_cells=len(COLUMN_NAMES)
    )
    if not records:
        raise ImportInvalidFile("empty_file")
    data_records: list[list[str]] = records[1:]
    _resolve_header(records[0])
    if not data_records:
        raise ImportInvalidFile("empty_file")
    # :1214 之后完全不变
```

随之删除：两处裁剪循环与行数判定（:884–891 / :1204–1208）；`resource_interface_ip_import.py` 的 `ImportRowLimitExceeded` 未使用导入（`ImportFileTooLarge` 仍使用，保留）。

### 4.3 零可观察差异论证

| 输入形态 | 基线 | 定稿 | 一致原因 |
| --- | --- | --- | --- |
| 合法 ≤5000 行 | 全量物化 → 裁剪 → `total_rows=N` | 有界保留 → 同样裁剪 | D1：N ≤ max_rows 时一条不丢 |
| 中间夹空行 | 空行是数据行、产生行错误 | `pending_blanks` 补回占位 → `()` → `[]` → 模板补空 | C2/C5：空记录长度不可观察；行号仍按索引 +2 |
| 尾部空行（含 xlsx 大使用区域） | 物化后裁掉 | 只计数，结束即丢弃 | D3 等同 :887–888 |
| 5001 行 | 413 | 保留 5001 → `_finalise` 413（排空后） | D4 |
| ≫5001 行 + 中间空行 | 413 | 超额即释放并继续迭代 → 排空后 413 | D1 |
| 尾部解析错误（任意行数） | **422** | **422**（排空时抛，早于 `_finalise`） | 整段排空保证时序 |
| 表头 100 列 | `unknown_columns` 列全部未知列 | 表头整行保留 → 相同明细 | D2 |
| 数据行 100 列（前 26 合法） | 逐行校验只看前 ≤26 列 | 裁剪到 26 → 校验逐字节相同 | C2/C5 |

### 4.4 B1–B13 映射

| # | 不变量 | 落点 | 影响 |
| --- | --- | --- | --- |
| B1 | 5 MiB / 413 大小 | `parse_and_validate` 首部 | 不变 |
| B2 | 5000 行 / 413 行数 | `_finalise`（唯一判定点） | 语义不变，位置移入 `parse_records`，仍在表头前 |
| B3 | 尾部空行 / 行号 | `pending_blanks` + `_is_blank_record` | 语义不变，实现改计数式 |
| B4 | `errors_truncated` / 1000 预览 | `result_payload` | 不变 |
| B5 | 1-based 行号 / `field` / `related_row` | consumer `enumerate` | 不变 |
| B6 | 校验顺序 | 路由 + `parse_records` 排空后判行数 + consumer 表头 | 顺序逐项不变 |
| B7 | 六类 reason | `_resolve_*` | 不变 |
| B8 | F037 收敛（`LxmlError`、局部 `OSError`） | `with` 边界未变，仅块内改为 `_collect_records` | 不变 |
| B9 | 双载体等价 | 两 carrier 在 `parse_records` 前汇合 | 不变 |
| B10 | 零写入 / 零 Audit | 解析早于任何 `begin_nested()` | 不变 |
| B11 | 权限/范围、401 先于 403 | 路由依赖顺序 | 不变 |
| B12 | 模板/端点/字段/码/reason 零变更 | 无契约改动 | 不变 |
| B13 | 内容保护 | 不新增日志、不新增含内容消息 | 不变 |

### 4.5 空间有界 / 时间线性（诚实表述）与残余无界面

- 空间：峰值 ≈ `len(data)`（≤5 MiB）+ 解码文本（≤5 MiB）+ 1 个完整表头 + `(max_rows+1) × keep_cells` 保留单元格 + 解析器常驻部件 + 1 行瞬时宽度；不随「超过 max_rows 的行数」与「超过 keep_cells 的列数」增长。
- 时间：仍线性于解析器展开工作量（必须整段排空）。**不得**表述为「空间与时间同时有界」。新实现比基线更省时（只做 `is None or == ""`，不再逐格构造文本），但不承诺时间上界。
- 残余无界项（本 Feature 不消解，登记 R-3）：①`read_manifest` / `read_workbook` 把 `[Content_Types].xml` / `xl/workbook.xml` 整读；②`read_strings` 把 sharedStrings 整表读入；③路由 `file.file.read()` 在 5 MiB 判定前整读请求体。三者受 deflate 最大压缩比约束，属 AQ-2=B 才能硬化的范畴。

## 5. 与 F037 转换层的关系

| 项 | 结论 |
| --- | --- |
| `_invalid_file_on_parse_failure` | 原样复用；`with` 边界不变，块内由 `list(...)` 改为 `_collect_records(...)`，迭代仍发生在块内 → 422 收敛不变（B8） |
| `_PARSE_FAILURES` 8 类 | 零 diff（F037 S7 的 `len(...) == 8` 断言继续成立） |
| `lxml` 条件条目 / `_parse_xlsx` 局部 `OSError` | 零 diff（DR-F037-08 不动） |
| L7′ | 仍成立：全程 `io.BytesIO`，无临时文件/路径/请求流；新增自有代码不做 I/O、不捕获异常、不构造文本 |
| R-12 | 不重评（L7′ 前提未变）→ 保持 LOW |
| 新增 **L7″** | 作用域内新增自有代码只允许「遍历 + 计数 + 切片 + `is None or == ""` 判定」；禁止新增 `try/except`、文本构造、I/O、日志 |
| F037 52 项 | `parse_records` 返回类型仍 `list[list[str]]`、两参数调用仍可（默认 `None` = 无界）→ 预期无需修改 |

## 6. 契约影响

**零 diff**（`api_required=false`）。F014 §2 顺序、§7 行号、§10 上限与「bounds 内存型 read_only xlsx 解析」的论证均不变（本 Feature 正是补强该论证）；F023 v2 §2/§14 同。守卫：`git diff -- docs/api/` 必须为空。若实现中发现必须改契约（如需新增解压后字节/列数上限）→ 立即停止并回退变更控制（与 AQ-2=A 冲突，属 product §1.3 Gate 条件）。

**Contract 状态：NOT_REQUIRED**（无 Endpoint / 字段 / 错误码 / reason / details 键 / 上限 / 权限变更）。

## 7. Database

**NOT_REQUIRED**：解析发生在任何 DB 访问之前（`write_import` :950 之后才 `begin_nested()`），拒绝路径零 SQL、零事务、零 Audit；无 Schema / 索引 / 约束 / 触发器 / Migration / 事务边界 / 锁序变化；`docs/database/f014-import.md` v1 与 `f023-import.md` 的 NOT_REQUIRED 继续成立。

## 8. 测量与验证方案

### 8.1 基线与工具（先测后改）

`tracemalloc` 峰值 + `time.perf_counter()`（沿用 `test_import_performance.py`），交叉参照 `resource.getrusage(RUSAGE_SELF).ru_maxrss`（仅报告，不作断言：单调且含 lxml C 层）。

基线代码获取（只读）：`git show 8e609ca2e5b88c30804b6f6ad54a8a57d7906556:backend/app/services/resource_import.py > /tmp/f038_baseline_resource_import.py`，用 `importlib` 载入仅供测量，**不得提交**。环境必录：`python -V`、`openpyxl.__version__`、`openpyxl.LXML`、`lxml.__version__`、`ru_maxrss` 观测值。

### 8.2 样例构造（复用 F037 的 zip 改写手法）

| ID | 构造 | 基线预期 |
| --- | --- | --- |
| S-W1 宽表 | xlsx + `dimension A1:ZZ10001` + 每行 `ZZ` 列 inlineStr | 10001 × 702 宽元组，数百 MB |
| S-W2 大使用区域 | `dimension A1:XFD10001` + 10001 个空 `<row/>` | ~1.3 GB（全空 → 尾部空行，基线仍须先物化） |
| S-W3 尾部空行 CSV | 表头 + 3 行 + 100k 个 `\n` | 100k 个 `[]` 后裁掉 |
| S-W4 5001 行 + 尾部行级错误/超宽行 | 5001 行 + 末行 200 列或非法 ip | **413** |
| S-W5 5001 行 + 尾部解析损坏 | 5001 行 + 单字段 >131072（或 sheet XML 损坏） | **422 `unreadable`**（基线即 422，见 §11 ON-1） |
| S-W6 宽表 CSV | 5 MiB 的 `,`（≈260 万单元格） | 全量物化 |
| S-W7 中间大段空行 | 表头 + 1 行 + 1000 空行 + 1 行（末行带错误） | `total_rows=1002`，错误行号 1002 |

### 8.3 阈值（相对倍数，禁绝对 MB 硬编码）

1. 规模不敏感：同一构造族 N 与 4N（均 > max_rows），断言 `fixed_peak(4N) ≤ 1.5 × fixed_peak(N) + 2 MiB`；报告基线倍率（基线分支已不存在，仅记录）。
2. 相对基线：S-W1/S-W2/S-W6 断言 `fixed_peak ≤ baseline_peak / 8`。
3. 无退化：合法 5000 行样例断言 `fixed_peak ≤ 1.2 × baseline_peak`。
4. 绝对哨兵：`fixed_peak ≤ 64 × len(data) + 64 MiB`。
5. 时间：S-W1/S-W2 断言 `fixed_time ≤ baseline_time`（记录秒数，不设绝对上限）。

### 8.4 同字节响应深比较（A1）

测试内提供 start_commit 语义的参考实现 `_baseline_records(data, fmt)`（仅测试使用），逐份断言：①参考实现 + 基线裁剪/行数逻辑的结果与 `parse_records(data, fmt, max_rows=5000, keep_cells=W)` 相等（`rows` 只比前 W 列，并用索引探针证明 consumer 从不读第 W 列之后，见 TD-F038-U4）；②四端点 × 固定输入矩阵（F037 的 8 例 + 输入③ + 缺 workbook 部件 + 413 字节 / 413 行数 / `empty_file` / `unsupported_format` / 表头四类 / 行级错误 / 正常成功批次 + S-W1..S-W7）状态码与 `resp.json()` 深比较相等。

### 8.5 必须复跑的既有套件（cwd `backend/`）

```bash
export TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test'
python3 -m pytest tests/integration/test_f037_import_parse_errors.py -q         # 52 项，零修改通过
python3 -m pytest tests/integration/test_imports.py tests/integration/test_import_tester_acceptance.py \
                 tests/integration/test_import_constraints.py \
                 tests/integration/test_f023_resource_interface_ip_import.py -q
python3 -m pytest tests/integration/test_f034_csv_text_carrier.py tests/integration/test_f034_csv_text_carrier_scope.py -q
python3 -m pytest tests/integration/test_f035_append_interface_ip_import.py tests/integration/test_f035_append_scope.py \
                 tests/integration/test_f035_tester_acceptance.py tests/integration/test_f036_attribution.py \
                 tests/integration/test_f036_tester_independent.py -q
python3 -m pytest tests/integration/test_import_performance.py -q
python3 -m pytest tests/integration/test_f038_parse_bounds.py -q                # 新增
```

## 9. 风险、分工与决策

### 9.1 风险

| ID | 风险 | 级别 | 检测 | 处置 |
| --- | --- | --- | --- | --- |
| R-1 | 行号位移 | HIGH | S-W7 / S-W3 + 差分参考比对 `row` / `total_rows` | `pending_blanks` 按位置补回 |
| R-2 | 尾部空行误判（`_is_blank_record` 与 `_cell_text` 不等价） | HIGH | 全类型矩阵参数化等价用例（`None`/`""`/`" "`/`0`/`0.0`/`-0.0`/`True`/`Decimal`/`datetime`/`date`/`time`/`timedelta`） | 若不等价则显式处理该类型并重跑 S-W3/S-W7 |
| R-3 | 残余无界面被误宣称已消解 | MEDIUM | 报告显式登记；Review 核对措辞 | 不新增拒绝（AQ-2=B） |
| R-4 | `errors_truncated` / `error_count` / `importable_rows` 变化 | HIGH | 1100 错误行样例（`error_count=1100`、`len(errors)=1000`、`truncated=true`、`total_rows=1100`） | 行集合须逐位等价 |
| R-5 | 时间退化（宽表 gap 行判定 O(width)） | MEDIUM | S-W1/S-W2 记录秒数，断言 `fixed_time ≤ baseline_time`；D03 全绿 | 必要时对 `_is_blank_record` 加「先看前 keep_cells 再扫尾部」短路 |
| R-6 | openpyxl used range / dimension 行为差异 | MEDIUM | 补「无 dimension 稀疏 sheet」「dimension 与实际不一致」两例 | 逻辑不依赖 width |
| R-7 | 413/422 顺序回归 | HIGH | S-W5（→422）+ S-W4（→413）+ F037 三类输入 × 4 端点 | 413 只在 `_finalise`（排空后）抛出；Review 核对循环无 break/return |
| R-8 | L7′ 失守 / `OSError` 外溢 | MEDIUM | F037 S7 的 AST 守卫 + 新增 L7″ 静态断言 | 违反即回退并重评 R-12 |
| R-9 | 生产调用点漏传参数 → 静默回到无界 | MEDIUM | AST 断言两处 `parse_records` 调用均带 `max_rows=` 与 `keep_cells=` | 同上 |
| R-10 | `MemoryError` / `RecursionError` 语义变化 | MEDIUM | F037 U-d/U-f 继续全绿 + 静态断言本次 diff 无新增 `except` | 违反即 BLOCKER |
| R-11 | 测量噪声 | MEDIUM | 每样例 `tracemalloc.start()` 前后 `gc.collect()`；同进程固定顺序；报告两次重复值 | 用相对倍数断言 |

**回滚**：改动局限 2 个 service 文件（无 Schema / 迁移 / 配置 / 依赖 / 契约）；回滚 = 还原两文件到 `8e609ca`，删除新增测试与完成态结论。回滚后新增用例必须失败，不得删用例修绿。

### 9.2 Backend 实现要点

1. 只改 `resource_import.py` 与 `resource_interface_ip_import.py`；契约 / 模板 / `pyproject.toml` / `Dockerfile` / `frontend/` / `alembic/` 零 diff。
2. `resource_import.py`：新增 `_MAX_TEMPLATE_COLUMNS`、`_is_blank_record`、`_Collected`、`_collect_records`、`_finalise`；两个解析函数改为 `_collect_records`；`parse_records` 加两个可选关键字参数并保留返回类型；删除 consumer 的裁剪与行数判定并注释指向 `parse_records`。
3. 不得改动：`_PARSE_FAILURES`、`failures` 构造、PK 闸门、`empty_file` / `unsupported_format` 位置、`_close_workbook`、`_cell_text`、`_resolve_*`、逐行校验、`write_import`、任何日志。
4. 不得新增 `except` / `try`（既有 `try/finally` 保留）/ 临时文件 / `open(` / `Path(` / 新依赖 / `field_size_limit` 变更 / 可观察上限。
5. L7″ 纪律：`_collect_records` 内只有遍历、计数、切片、`is None or == ""`。
6. `resource_interface_ip_import.py`：传 `max_rows=max_rows, keep_cells=len(COLUMN_NAMES)`；删除裁剪、行数判定与 `ImportRowLimitExceeded` 导入。
7. 自检：`git diff --stat` 仅两文件；`grep -nE 'list\(csv\.reader|list\(worksheet\.iter_rows'` 无命中；`ruff` 干净。

### 9.3 Tester 的 TEST DESIGN 输入（TD-F038-*）

| ID | 层 | 断言 |
| --- | --- | --- |
| U1 | U | `_is_blank_record` 与 `all(_cell_text(c)=="" ...)` 全类型等价（R-2） |
| U2 | U | `_collect_records` 语义表：<cap、=cap、>cap、中间空行、尾部空行、空表、仅表头、`max_rows=None` |
| U3 | U | 排空性：第 3 行抛 `csv.Error` 且总行数 > max_rows → 422 而非 413 |
| U4 | U | 裁剪安全性探针：100 列 `list` 子类记录最大访问下标 < 模板列数（含错误路径） |
| U5 | U | 保留上界：10 万条宽记录 → `len(rows) ≤ max_rows+1` 且 `overflow is True` |
| I1–I8 | I | S-W1..S-W7 + 合法 5000 行 × 4 端点：状态码与 `json()` 与参考实现逐字段相等 |
| I9 | I | F037 的 8 例 + 输入③ + 缺 workbook 部件继续 422 `unreadable`（F037 测试文件零修改） |
| I10 | I | 零写入/零 Audit：7 表计数在 S-W1/S-W4 后不变 |
| M1 | 测量 | §8.1–8.3 数值、阈值断言、环境记录写入 test-report |
| S1 | 静态 | `git diff -- docs/api/` 空；模板/端点/错误码/上限/`pyproject.toml`/`Dockerfile`/`frontend/` 空 diff |
| S2 | 静态 | 两处 `parse_records` 调用带 `max_rows=` / `keep_cells=`，且分别由 `_MAX_TEMPLATE_COLUMNS` 与 `len(COLUMN_NAMES)` 推导 |
| S3 | 静态 | 无新增 `except`；`_PARSE_FAILURES` 长度仍 8；无 `field_size_limit`；无 lxml 依赖声明 |
| S4 | 静态 | `grep 'list(csv.reader\|list(worksheet.iter_rows'` 无命中 |
| S5 | 静态 | L7″：`_collect_records` / `_is_blank_record` 源码无 `try`/`except`/`open(`/`Path(`/`logger.` |

### 9.4 技术决策（本角色签核）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-F038-01 | 流式来源 + 有界保留：边迭代边保留（≤ max_rows+1 行 × keep_cells），整段排空，超额即释放；表头整行保留；尾部空行计数式 | 已定 |
| DR-F038-02 | **OPEN-T3 显式裁定**：`parse_records` 保留名称/返回类型/两参数兼容，新增可选 `max_rows` / `keep_cells`（默认 `None` = 无界，仅供解析层单测）；尾部空行裁剪与行数上限上移进 `parse_records`，两个 consumer 删除重复实现。理由：唯一能在不伪造行内容、不改契约、不动 F037 52 项的前提下让长度通道不承载「超额」信息 | 已定（CONTRACT Gate 复核） |
| DR-F038-03 | 「整行是否为空」由解析层整行判定（无文本构造、无异常面），数据行裁剪只作用于保留副本 | 已定 |
| DR-F038-04 | 复用 F037 转换层零改动；新增 L7″；`OSError` / R-12 不重评 | 已定 |
| DR-F038-05 | `layers={database:false,backend:true,frontend:false}`；`api_required=false`；Contract / Database NOT_REQUIRED | 已定 |
| DR-F038-06 | 测量以 `tracemalloc` 峰值为主、`ru_maxrss` 交叉参照；阈值用相对倍数，禁绝对 MB | 已定 |

### 9.5 实施层

| Layer | 内容 | 负责 |
| --- | --- | --- |
| L0 | 本设计 + Database NOT_REQUIRED 复核 + TEST DESIGN 交接 | Architect / Database / 协调器 |
| L1 | `resource_import.py`（§4.2 落稿） | Backend |
| L2 | `resource_interface_ip_import.py`（consumer 改造 + 未使用导入清理） | Backend |
| L3 | 基线测量脚本 + 样例构造 + `tracemalloc` 证据（`/tmp` 基线模块不入库） | Tester |
| L4 | 新增 `backend/tests/integration/test_f038_parse_bounds.py` + TD 落稿 | Tester |
| L5 | 全量回归 + 静态守卫 | Tester |
| L6 | Review | Reviewer |

## 10. Domain / Data Impact 与前端

无领域 / 数据 / 权限 / 范围变化；data-integrity 对照不变（唯一性由三条部分唯一索引与逐行校验保证，整批原子性由单事务保证，拒绝路径仍在任何写入之前）。**Frontend：无改动**（`frontend/` 必须空 diff）。

## 11. OPEN 技术问题

| ID | 问题 | Owner | 阻塞 |
| --- | --- | --- | --- |
| **ON-1（口径裁定，已按基线执行）** | product S3 写「5001 行 + 尾部**解析损坏**仍 413」，但基线对尾部解析器异常返回 **422**（物化时抛出，早于 :891 行数判定；B6/S6 亦定「解析 422 先于行数 413」）。AQ-2=A 下必须按基线：尾部解析器异常 → 422；只有行级错误 / 超宽行 → 413。本设计据此执行，须在 test-report 登记该口径（product S3 措辞按此解释） | Tester / Product | 否 |
| ON-2 | `max_rows` / `keep_cells` 默认 `None`（兼容 F037 两参数调用）。若定稿 Gate 不接受「默认无界」，替代方案为改必填并机械适配 F037 的 40 处调用 | 协调器（CONTRACT Gate） | 否 |
| ON-3 | 残余无界面（sharedStrings / manifest 部件 / `file.file.read()`）不在本 Feature 范围 | 协调器 / Product | 否 |
| ON-4 | `tracemalloc` 不计 lxml C 层；有/无 lxml 环境峰值与异常类不同 → 报告须记 `openpyxl.LXML` 且结论不外推 | Tester | 否 |
| ON-5 | 超大 `dimension` 样例单次耗时可能达分钟级；报告须给实测秒数 | Tester | 否 |

## 12. 结论

在既有契约与 AQ-2=A 边界内，通过「整段排空 + 有界保留」使解析阶段内存相对输入规模有界、且不随展开工作量增长；四端点可观察结果预期逐字段不变，`docs/api/` 零 diff，无 Schema / 配置 / 依赖 / 前端改动。时间仍线性于展开工作量（§4.5），残余无界面三条登记为已知项。

**READY FOR DESIGN** —— 可交 Database（复核 NOT_REQUIRED）与 Tester 编写 TEST DESIGN；本阶段不放行编码。定稿须在取得 Database NOT_REQUIRED 复核与 Test Design 后，由本角色核对 §4.5/§9 一致性并签核，特别复核 DR-F038-02 与 ON-1 口径。

## 13. CONTRACT 阶段定稿签核（v1 + §13 增补，2026-10-29）

- **状态**：**READY FOR IMPLEMENTATION**
- 本节对 §8（阈值）、§9.3（TD 输入）、§9.4（DR-F038-02）、§11（ON-1/ON-2）作口径确认与收紧；冲突以本节为准，v1 正文 §1–§12 不修订。
- 核对输入：`docs/features/F038/{product,test-report}.md`（TD-F038-1）、`docs/api/F014.md` v1 §2/§7/§10/§13、`docs/api/F023.md` v2 §2/§7/§14/§17、`backend/app/services/{resource_import,resource_interface_ip_import}.py`、`backend/tests/integration/test_f037_import_parse_errors.py`。

### 13.1 TD-I-1 裁剪安全性取证（裁定：毒值探针 + 负向对照 + AST 三件套成立）

代码事实：`_validate_record` :675–676 与 `_cells_for` :389–393 均先 `list(cells)` / `list(record)`，`list.__iter__` 不回调子类 `__getitem__` ⇒ 原「下标探针」不可执行。裁定采纳毒值探针方案，附 4 条硬约束（缺一即证据不成立）：

| ID | 约束 |
| --- | --- |
| P-1 | 毒值必须覆盖 `__getattr__` / `__eq__` / `__ne__` / `__hash__` / `__bool__` / `__str__` / `__repr__` / `strip`；**不得**在 `__len__` 上抛（`len()` 合法） |
| P-2 | 双负向对照：① 同一记录第 **W-1** 列放毒值 → **必须触发**；② 毒值记录与「第 ≥W 列置空」的 `result_payload()` 完全相等 |
| P-3 | 毒值只加数据行；表头整行保留另由 `U2-⑩`（header 宽度 == 原始宽度）与 `I6a`（`unknown_columns` 逐元素等于基线）证明，三项须同时绿 |
| P-4 | 毒值探针须覆盖错误路径（未知 cluster / 非法整数 / 文件内重复 hostname / F023 组内一致性冲突），错误集与基线逐元素相等 |

OPTIONAL（不作判据）：表头第 ≥W 列放毒值须触发；宽表差分 fuzz。

### 13.2 阈值口径（定稿，唯一有效）

| # | 断言 | 适用 |
| --- | --- | --- |
| T-1 | `fixed_peak(4N) ≤ 1.5 × fixed_peak(N) + 2 MiB` | **仅 xlsx 族** S-W1 / S-W2；N=2501 / 4N=10001（统一取值，取代 20004） |
| **T-1b** | `Δpeak ≤ 1.5 × Δbytes + 2 MiB`（`Δpeak = fixed(4N) − fixed(N)`，`Δbytes` 同构造） | CSV 族 |
| T-2 | `excess(fixed) ≤ excess(baseline) / 8`，`excess(x) = max(peak − len(data), 0)` | S-W1 / S-W2（等规模 1001 行）、S-W6a |
| T-3 | `fixed_peak ≤ 1.2 × baseline_peak` | 合法 5000 行 CSV |
| T-4 | `fixed_peak ≤ 64 × len(data) + 64 MiB` | 全部样例 |
| T-5 | `fixed_time ≤ baseline_time`（记录秒数，无绝对上限） | S-W1 / S-W2 / S-W6a |
| T-6 | 报告项 `fixed_peak(S-W2, 4N) ≤ 8 MiB`（不判 FAIL） | S-W2 |

理由：CSV 峰值地板是不可避免的 `data.decode("utf-8-sig")` 整串（≤5 MiB），故 T-1 只对 xlsx 族成立；T-2 剥离输入地板后 `S-W6a` 余量 ≥ 2×（关闭 TD-I-3）。列数维度不新增判据（T-2 已含相对证据 + T-4 哨兵），允许作报告项。

**防放宽条款（R-13）**：本节为阈值唯一有效口径；TEST 阶段不得改倍数/加减项；实测 FAIL 须修实现。任何第三次口径修订须回本节重签核，且报告须同时公布公式与两侧实测数值。

### 13.3 ON-1 口径（413 / 422）与 product S3 errata

实证（start_commit 基线）：S-W4（5001 行 + 尾部**行级错误/超宽行**）→ **413** `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows:5000}`；S-W5（5001 行 + 尾部**解析器异常**，如单字段 >131072）→ **422** `IMPORT_INVALID_FILE{reason:"unreadable"}`。

定稿口径：

1. 尾部**解析器异常**（`csv.Error`、zip/XML 结构错误、`LxmlError`、`_parse_xlsx` 局部 `OSError`）→ **422 `unreadable`**，与行数无关（B6「解析 422 先于行数 413」）。
2. 尾部**行级错误**或**超宽行**（不触发解析器异常）→ **413**。
3. product §2.1 S3 的「5001 行 + 尾部解析损坏仍 413」只能读作「尾部行级错误或超宽行 → 413」；B6/B8/S6 与 F014 §2 优先。
4. 构造必须配对：「末行 200 列」= 413 的正确构造；「末行单字段 131,073 字符」= 422 的正确构造。把 S-W5 写成 413 或用例判 **FAIL**。

product 侧 errata：**需要**，归属 Product Manager，在 `docs/features/F038/product.md` §2.1 S3 行下增补解释（引用本 §13.3 与 TD 实测），不改 S1–S8 / B1–B13 实质；需求正文零变更；分类为澄清（`change-control.md` §2 编辑维护），不需用户裁定。

### 13.4 S-W2 规模降级与期望值勘误（TD-I-8）

1. **降级可接受**：原规模基线不是有界性证据，只是对照量；有界性由 T-1（N=2501/4N=10001）+ T-2（等规模 1001 行）+ T-4 承担。**2.7 GB 必须标 `ESTIMATE（外推，未实测）`**，不得表述为已实测（product N8）。
2. **期望值勘误**：`dimension A1:XFD{N+1}` 使 openpyxl 把**每一行（含表头行）**补齐到 16,384 格；数据行全为 `<row/>` ⇒ 全属尾部空行被裁掉 ⇒ `total_rows=0`，**不触发 413**；表头含 14 个真实列名 + 16,350 个 `None` ⇒ `unknown_columns` 为 16,350 个空串 ⇒ 基线为 **422 `unknown_columns`**（硬编码 413 会产生假 FAIL）。
3. 如需覆盖「超大宽度 + 413」，另立 S-W2b（XFD 宽 + 10001 行**非空**）→ 完成态 413，基线侧 `NOT TESTED（ESTIMATE）`，无差分兜底（R-14）。
4. **I 层判据顺序固定**：① `(status, json())` 两侧深等优先；② 其次声明期望值；冲突时以①为准并立即登记，不得静默改期望。

### 13.5 DR-F038-02 / ON-2 定稿（接受默认 `None`）

硬事实：`test_f037_import_parse_errors.py` 共 **35 处**两参数 `parse_records(...)` 调用；其 :661–666 断言 `records[0] == BM_HEADERS`、`isinstance(records, list)`；A11/B8/S7 要求该文件零修改。

裁定：**接受** `max_rows: int | None = None` / `keep_cells: int | None = None`。若改必填须机械适配 35 处并修改该文件 → 违反 B8/S7/A11 并使 F037 证据失效。补偿控制：

| ID | 要求 |
| --- | --- |
| E-1 | `S2` 扩展为**全模块 AST 扫描**：`backend/app/**` 中 `parse_records(` 调用**恰好 2 处**，每处 `keywords` 均含 `max_rows` 与 `keep_cells`；第 3 处或缺参 → FAIL |
| E-2 | `parse_records` docstring 保留「生产调用点必须同时传入；省略即回到无界物化，仅供单独验证解析层的用例使用」 |
| E-3 | `max_rows=None` 分支由 `U6` 覆盖（两参数调用与显式 `None` 结果逐字节相等） |

**须告知的语义变化**：F038 后两参数调用的语义变为「已剔除尾部空行 + 无行数上限」（v1 为「含尾部空行」）。已核对 F037 全文件无相应断言 ⇒ 零修改仍成立。

被否决替代：必填参数 + 适配 35 处（违反 B8/S7/A11）；双入口（`parse_records` / `parse_records_bounded`，新增公共面且更易误用）；哨兵默认值（等价必填）。

### 13.6 契约：`NOT_REQUIRED`，`docs/api/` 零 diff

F038 对 `docs/api/F014.md`（v1）与 `docs/api/F023.md`（v2）**零修改**：Endpoint（4）、`format`、请求字段、响应 schema、错误码集合、`reason` 集合、`details` 键、上限常量（5,242,880 / 5000 / 1000）、校验顺序、行号语义、`IMPORT` 权限与 §23.2 范围均无变更。本 Feature 仅改变解析阶段内存工作集与可能的时间特征。

| 面 | 状态 |
| --- | --- |
| Endpoint / `format` / 请求字段 | 零变更 |
| 响应字段与 JSON 形状 | 零变更（`result_payload` 未动） |
| 错误码 / `reason` / `details` 键 | 零变更（只复用既有异常） |
| 校验顺序 | 零变更（行数判定位置移入 `parse_records`，仍在表头前） |
| 上限数值 / 模板 / 权限 / 范围 / Audit / 原子性 | 零变更 |
| `docs/api/`、`docs/database/`、`frontend/`、`backend/alembic/`、`pyproject.toml`、`Dockerfile` | 零 diff（`git diff --stat 8e609ca -- …` 必须为空） |

四项 TD 发现（TD-I-1 / TD-I-2 / ON-1 / S-W2）均不触及契约 ⇒ 不存在与 AQ-2=A 的冲突。**若实现中出现「必须新增可观察拒绝/上限才能达成有界」的判断，立即停止实现，本签核与 §12 设计同时失效，回退 AQ-2=B 变更流程。**

### 13.7 Backend 实现要点增补（叠加 §9.2）

| ID | 要点 |
| --- | --- |
| IMP-1 | `_is_blank_record` **不加优化、不得收窄到前 keep_cells 列**（否则前 W 列全空、第 W+1 列有值的尾部行会被误判，破坏 B3/A4）。`all()` 的自然短路即为 §9.1 R-5 的处置，**不得实现为截断判定** |
| IMP-2 | `_collect_records` 内**禁止** `list(record)`；只能 `record[:keep_cells]`（整行 `list()` 会复制 16,384 指针，抵消收益） |
| IMP-3 | 新增 `from collections.abc import Sequence`；不新增第三方 import |
| IMP-4 | `_finalise` 调用位置：CSV 在 `with` 块之后；xlsx 在 `finally: _close_workbook` 之后 ⇒ `ImportRowLimitExceeded` 恒在白名单作用域外 |
| IMP-5 | consumer 用 `data_records = records[1:]`，**不得**再包 `list(...)`；返回类型仍 `list[list[str]]` |
| IMP-6 | 中间空行占位 `()` → `_finalise` 归一化为 `[]` → `_validate_record` 补 14 / `_cells_for` 补 26，与基线读取下标集相同 |
| IMP-7 | `_collect_records` 的 `for` 体内**不得**出现 `break` / `return`（超额后必须 `continue` 排空）；由 AST 断言 |
| IMP-8 | `_is_blank_record` / `_Collected` / `_collect_records` / `_finalise` 内不得出现 `logger.` / `open(` / `Path(` / `try` / `except`（L7″） |
| IMP-9 | `_MAX_TEMPLATE_COLUMNS` 由 `TEMPLATES` 推导（实测 14），不得硬编码；F023 侧用 `len(COLUMN_NAMES)`（26） |
| IMP-10 | 自检：`git diff --stat 8e609ca -- backend/tests/integration/test_f037_import_parse_errors.py` 必须为空，且该套件 52 项全绿 |

F037 守卫兼容性已逐条只读核对（`:1293–1320` 的 `OSError` 行区间、无独立 `except OSError`、`with` 块禁 I/O、`except Exception` 恰 2 处、`_invalid_file_on_parse_failure` 子句仍 `["AppError","failures"]`、`len(_PARSE_FAILURES)==8`）⇒ 无需改动。

### 13.8 Database / Frontend 复核

Database `NOT_REQUIRED` 继续成立（解析早于任何 DB 访问；`write_import` :950 之后才 `begin_nested()`）。**事实如实记录**：仓库内无 `docs/database/F038*` 产物，按 `layers.database=false` 不需要；本签核依据为 plan revision 25 的 `layers.database=false` + 代码事实 + test-report TD-10 复核；不宣称 Database 角色已出具独立报告（若需书面复核在 L0 补齐，不阻塞放行）。Frontend 零改动（`frontend/` 空 diff）。

### 13.9 风险变化

| ID | v1 | §13 | 依据 |
| --- | --- | --- | --- |
| R-1 行号位移 | HIGH | HIGH | 证据链成型但未实测 |
| R-2 `_is_blank_record` 不等价 | HIGH | **MEDIUM** | 逐类型复核 `_cell_text`：`str`/`None`/`bool`/`int`/`float`/`datetime`/`date`/`time`/`timedelta`/`Decimal("0")`/`b""`/`nan` 全等价；残由 U1 + S-W3/S-W7 兜底 |
| R-3 残余无界面 | MEDIUM | MEDIUM | §4.5 措辞不变 |
| R-4 预览/计数语义 | HIGH | HIGH | 由 I7/I12 承担，未实测 |
| R-5 时间退化 | MEDIUM | **LOW** | `all()` 短路 + 无文本构造（严快于基线） |
| R-6 openpyxl dimension 差异 | MEDIUM | MEDIUM | 另需「无 dimension」「dimension 不一致」两例 |
| R-7 413/422 顺序 | HIGH | HIGH | §13.3 配对构造 + IMP-4/7 |
| R-8 L7′ 失守 | MEDIUM | MEDIUM | F037 守卫兼容性已核对 |
| R-9 漏传参数 | MEDIUM | MEDIUM | 升级为 E-1 全模块 AST |
| R-10 MemoryError 语义 | MEDIUM | MEDIUM | `except Exception == 2` 守卫已核对 |
| R-11 测量噪声 | MEDIUM | MEDIUM | M6 协议不变 |
| **R-12（新）** | — | MEDIUM | TD 期望值与基线不一致（S-W2 写成 413）→ 假 FAIL；由 TD-I-8 勘误 + 差分优先判据处置 |
| **R-13（新）** | — | MEDIUM | 阈值口径被二次放宽 → §13.2 防放宽条款 |
| **R-14（新）** | — | LOW | 单侧断言无差分兜底（S-W2b、5000 行写入端点 `NOT TESTED`）；不得表述为等价性证据 |

关闭：**TD-I-3**（T-2 的 `excess` 口径使 S-W6a 余量 ≥ 2×）。

### 13.10 定稿签核

```text
签核：Architect；日期 2026-10-29。
设计版本：docs/features/F038/architecture.md v1 + §13 增补（自本行起为实施依据；冲突以 §13 为准）。
上游依据：用户 2026-10-29 AQ-2 = A；product.md v1（S1–S8/B1–B13/N1–N10/A1–A14）；requirements revision 16；plan revision 25（layers={database:false,backend:true,frontend:false}、api_required=false、blocking_decisions: []）；F014 v1 / F023 v2（零 diff）。
定稿核对：TD-F038-1 覆盖 A1–A14 与 B1–B13（U1–U6 / I1–I15 / M1–M6 / S1–S6 + R1–R6，逐条给出层级/夹具/构造/断言/T 条目，映射无缺口）；§13 裁定四项 TD 实测发现与 DR-F038-02/ON-2，并新增 TD-I-8 勘误；契约 NOT_REQUIRED 且零 diff；Database NOT_REQUIRED 复核；无残留冲突与失效设计。
覆盖：仅 F038。不含 AQ-2=B、不含 F045 整体验收、不回填 F001–F037 历史证据。
结论：READY FOR IMPLEMENTATION
放行写入：① backend/app/services/resource_import.py；② backend/app/services/resource_interface_ip_import.py；③ 新增 backend/tests/integration/test_f038_parse_bounds.py；④ docs/features/F038/architecture.md §13、test-report §2 与 TD-I-8 勘误。
零 diff 禁止写入：docs/api/、docs/database/、backend/alembic/、frontend/、pyproject.toml、Dockerfile、模板/上限/错误码、backend/tests/integration/test_f037_import_parse_errors.py。
前置义务（不阻塞放行，但 TEST 结论须满足）：① 按 §13.4 修正 S-W2 期望；② 阈值按 §13.2 并公布公式与数值；③ 2.7 GB 标 ESTIMATE；④ product errata 由 Product 落稿并由协调器核验一致。
失效条件：① 需新增可观察拒绝/上限；② 需改 F037 52 项或任何契约文件；③ S-W5 实现为 413 或 S-W4 实现为 422；④ 两 service 之外出现 diff；⑤ 需求/契约/product 修订触及 §1.2 与 B1–B13。
```
