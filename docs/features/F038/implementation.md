# F038 导入解析内存边界加固 — IMPLEMENTATION 阶段报告（后端）

- **状态**：**BACKEND COMPLETE**
- **版本**：v1（2026-10-29）；FEATURE F038 / P1 / M29；分支 `feature/F038-import-parse-bounds`（交付线 `v3.4`），实现基线 `e954537`（start_commit `8e609ca` 语义未变，中间提交仅文档）
- **角色产物**：backend 只读产出 + 写入 `backend/app/services/resource_import.py`、`backend/app/services/resource_interface_ip_import.py`、本文件。
- **上游依据**：`docs/features/F038/architecture.md` v1 §4.2（定稿代码）/ §4.3（零可观察差异）/ §9.2 与 §13.7 IMP-1..IMP-10；§13.5（DR-F038-02 / ON-2 定稿 + E-1..E-3）；§13.3（ON-1：422 / 413 口径）；`docs/features/F038/product.md`（S1–S8、B1–B13）；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`。
- **实现范围**：仅解析层（`_parse_csv` / `_parse_xlsx` / `parse_records`）与两个 consumer 的裁剪、行数判定归并。**零** Schema / Migration / 契约 / 前端 / 依赖 / 配置改动；拒绝路径仍早于任何 DB 访问（`write_import` 内 `begin_nested()` 之前）。

---

## 1. 变更清单（函数级）

### 1.1 `backend/app/services/resource_import.py`（+120 / −27）

| 位置 | 变更 |
| --- | --- |
| 导入区 | `from collections.abc import Iterator` → `Iterator, Iterable, Sequence`（仅标准库；无新第三方 import） |
| 新增 `_MAX_TEMPLATE_COLUMNS`（`# --- parsing ---` 段首） | `max(len(template.columns) for template in TEMPLATES)`，实测 **14**；不硬编码 |
| 新增 `_is_blank_record(values) -> bool` | `all(value is None or value == "" for value in values)`；整行判定，不构造文本，不收窄到前 `keep_cells` 列 |
| 新增 `@dataclass _Collected` | 字段 `header`（`Sequence[Any]` 或 `None`，默认 `None`）/ `rows`（`list[Sequence[Any]]`，`default_factory=list`）/ `overflow`（`bool`，默认 `False`） |
| 新增 `_collect_records(records, *, max_rows, keep_cells) -> _Collected` | 边迭代边保留；表头整行保留；尾部空行计数（`pending_blanks`）；中间空行按位置补回 `()` 占位；超额后 `rows.clear()` 并 `continue` 排空；保留宽 `record[:keep_cells]`（无 `list(record)`） |
| 新增 `_finalise(collected, *, max_rows) -> list[list[str]]` | 行数上限（`overflow or len(rows) > max_rows` → `ImportRowLimitExceeded`）+ 逐格 `_cell_text` 归一化；返回 `[header, *rows]`，保持 `list[list[str]]` |
| `_parse_csv` | 签名加 `*, max_rows, keep_cells`；`with _invalid_file_on_parse_failure(...)` 边界**不变**，块内 `list(csv.reader(...))` → `_collect_records(csv.reader(...), ...)`；`_finalise` 在 `with` 之后 |
| `_parse_xlsx` | 签名加 `*, max_rows, keep_cells`；PK 闸门 / `failures` 构造（`InvalidFileException` + `OSError` + 条件 `LxmlError`）/ 局部 `ImportError` / `empty_file` / `_close_workbook` **逐字不变**，仅块内 `list(worksheet.iter_rows(...))` → `_collect_records(...)`；`_finalise` 在 `finally: _close_workbook` **之后** |
| `parse_records` | 新增关键字参数 `max_rows: int 或 None = None`、`keep_cells: int 或 None = None`；返回类型仍 `list[list[str]]`；docstring 含 E-2 原文（「生产调用点必须同时传入；省略即回到无界物化，仅供单独验证解析层的用例使用」） |
| `parse_and_validate` | 传 `max_rows=max_rows, keep_cells=_MAX_TEMPLATE_COLUMNS`；删除 3 行裁剪 `while` 与 2 行行数判定；`data_records = records[1:]`（无 `list(...)`）；表头判定 / `_resolve_template` / 逐行校验 / `ImportResult` 构造零改动 |

### 1.2 `backend/app/services/resource_interface_ip_import.py`（+9 / −4）

| 位置 | 变更 |
| --- | --- |
| 导入区 | 删除未使用的 `ImportRowLimitExceeded`（`ImportFileTooLarge` 保留，`:1197` 仍使用） |
| `parse_and_validate` | 传 `max_rows=max_rows, keep_cells=len(COLUMN_NAMES)`（=26）；删除裁剪 `while` 与行数判定；`data_records: list[list[str]] = records[1:]`；`_resolve_header`、`_parse_row`、`_merge_and_check`、F035 append 检查、`UnifiedImportResult` 零改动 |

未改动：`_PARSE_FAILURES`（仍 8 类）、`_cell_text`、`_invalid_file_on_parse_failure`、`_close_workbook`、`_resolve_template` / `_resolve_header` / `_cells_for`、`_validate_record`、`_parse_row`、`write_import`、`result_payload`、任何日志语句、模板/上限常量。

### 1.3 新增代码的静态形状（L7″）

`_is_blank_record` / `_Collected` / `_collect_records` / `_finalise` / `parse_records` 内**无** `logger.` / `open(` / `Path(` / `try` / `except`；`_collect_records` 的 `for` 体内**无** `break` / `return`；**无** `list(record)`。既有 `_parse_csv` / `_parse_xlsx` 的 `try/except` 为基线原样保留（未新增子句）。

---

## 2. IMP-1..IMP-10 逐条落实

| ID | 要求 | 落实 | 证据 |
| --- | --- | --- | --- |
| IMP-1 | `_is_blank_record` 不加优化、不收窄到前 `keep_cells` 列 | 实现为整行 `all(value is None or value == "")`，无宽度参数、无前缀短路 | AST 检查 `_is_blank_record` 无额外调用；样例 1/自检「中间空行」逐元素相等 |
| IMP-2 | `_collect_records` 禁 `list(record)`，只用 `record[:keep_cells]` | `collected.rows.append(record if keep_cells is None else record[:keep_cells])` | AST：`_collect_records` 内 `list() calls: []` |
| IMP-3 | 新增 `from collections.abc import Sequence`；无新第三方 import | 导入行合并为 `from collections.abc import Iterable, Iterator, Sequence` | `git diff` 导入区仅此 1 行 |
| IMP-4 | `_finalise` 在 CSV `with` 之后、xlsx `finally: _close_workbook` 之后 | `_parse_csv` 中 `with` 块结束后调用；`_parse_xlsx` 中 `return _finalise(...)` 在 `finally` 之后，并附注释 | `git diff` 对应 hunk；样例 4（422）/样例 5（413）配对成立 |
| IMP-5 | consumer 用 `data_records = records[1:]`，不再包 `list(...)` | 两处均改为切片；F023 侧带类型标注 `list[list[str]]` | `git diff` 两个 consumer hunk |
| IMP-6 | 中间空行占位 `()` → `_finalise` 归一化 `[]` → 校验补 14/26 | `collected.rows.extend([()] * pending_blanks)`；`_finalise` 逐格 `_cell_text` 得 `[]` | 自检「1000 中间空行 + 1 行错误」→ `rows=1002`（两侧相等）；样例 1 `rows=4`（含 1 个空数据行） |
| IMP-7 | `_collect_records` for 体内无 `break` / `return`，超额后 `continue` | 超额分支 `overflow=True; rows.clear(); pending_blanks=0; continue` | AST：`_collect_records loop-exit nodes: []`（仅循环后 `return collected`） |
| IMP-8 | 新函数内无 `logger.` / `open(` / `Path(` / `try` / `except`（L7″） | 见 §1.3 | AST 逐函数 `banned=[]`（`_parse_csv`/`_parse_xlsx` 的既有 `try` 为基线原样，未新增） |
| IMP-9 | `_MAX_TEMPLATE_COLUMNS` 由 `TEMPLATES` 推导（实测 14），F023 用 `len(COLUMN_NAMES)`（26） | `_MAX_TEMPLATE_COLUMNS = max(len(template.columns) for template in TEMPLATES)`；F023 `keep_cells=len(COLUMN_NAMES)` | 自检输出 `_MAX_TEMPLATE_COLUMNS=14`；`grep` 两处调用见 §3.6 |
| IMP-10 | F037 测试文件零 diff 且 52 项全绿 | 未触碰任何测试文件 | `git diff --stat -- backend/tests/integration/test_f037_import_parse_errors.py` 空；`52 passed` |

E-1（全模块 AST：`parse_records(` 调用恰好 2 处且均带两关键字）与 E-3（`max_rows=None` 两参数兼容）见 §3.6 / §3.4；E-2 见 §1.1 `parse_records` docstring。

---

## 3. 验证（真实输出）

环境：`python 3.12.7`；`openpyxl 3.1.5`，`openpyxl.LXML=True`；`lxml 5.2.1`；`ruff 0.15.17`（仓库无 ruff 配置，默认规则集）。

### 3.1 编译 + lint

```console
$ cd backend
$ python3 -m compileall -q app/services/resource_import.py app/services/resource_interface_ip_import.py && echo compile-ok
compile-ok
$ ruff check app/services/resource_import.py app/services/resource_interface_ip_import.py
All checks passed!
```

### 3.2 diff 范围（仅 2 文件）

```console
$ git diff --stat -- backend/app/services/
 backend/app/services/resource_import.py            | 134 ++++++++++++++++++---
 .../app/services/resource_interface_ip_import.py   |  13 +-
 2 files changed, 120 insertions(+), 27 deletions(-)
```

### 3.3 零 diff 守卫（契约 / 数据库 / 前端 / alembic / pyproject / Dockerfile / 测试）

```console
$ git diff --stat -- docs/api docs/database frontend backend/alembic backend/pyproject.toml backend/Dockerfile
$ git diff --stat -- backend/tests/
$ git diff --stat -- backend/tests/integration/test_f037_import_parse_errors.py
```

三条命令均**无输出**（空 diff）。另：`git status --porcelain` 仅为两 service 文件的 ` M` 与新增的 `docs/features/F038/implementation.md`。

### 3.4 全量物化已消除 / 既有 except 清单

```console
$ grep -nE 'list\(csv\.reader|list\(worksheet\.iter_rows' app/services/resource_import.py || echo 'no full materialisation'
no full materialisation

$ grep -nE 'except ' app/services/resource_import.py
454:    except AppError:
458:    except failures as exc:
480:    except Exception as exc:  # noqa: BLE001 - cleanup boundary, not a 4xx/5xx signal
556:    except UnicodeDecodeError as exc:
576:    except ImportError as exc:  # pragma: no cover - dependency guaranteed
588:    # 不会被掩盖；不得在此块内新增真实 I/O（L7'），不得放宽为 except Exception。
595:    except ImportError:  # pragma: no cover - falls back to ElementTree
732:    except (ValueError, AttributeError, TypeError):
739:        except AppError:
799:        except AppError as exc:
829:        except AppError as exc:
836:        except AppError as exc:
843:        except AppError as exc:
861:                except ValueError as exc:
869:        except AppError as exc:
894:                except ValueError as exc:
907:            except AppError as exc:
918:            except AppError as exc:
1088:            except IntegrityError as exc:
1090:            except AppError as exc:
1110:    except AppError:
1113:    except Exception:
```

与基线同集合，**本次 diff 无新增 `except`**：

```console
$ git diff -U0 -- backend/app/services/ | grep -E '^\+' | grep -nE 'except |try:|logger\.|open\(|Path\(' ; echo "exit=$?"
exit=1 (1 = none found)
```

### 3.5 回归套件（真实 PostgreSQL，`TEST_DATABASE_URL` 见下）

```console
$ export TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test'
$ python3 -m pytest tests/integration/test_f037_import_parse_errors.py -q
52 passed in 13.24s

$ python3 -m pytest tests/integration/test_imports.py -q
29 passed in 15.20s
```

补充（架构 §8.5 的其余导入套件，一并复跑）：

```console
$ python3 -m pytest tests/integration/test_import_tester_acceptance.py tests/integration/test_import_constraints.py \
    tests/integration/test_f023_resource_interface_ip_import.py tests/integration/test_f034_csv_text_carrier.py \
    tests/integration/test_f034_csv_text_carrier_scope.py tests/integration/test_f035_append_interface_ip_import.py \
    tests/integration/test_f035_append_scope.py tests/integration/test_f035_tester_acceptance.py \
    tests/integration/test_f036_attribution.py tests/integration/test_f036_tester_independent.py \
    tests/integration/test_import_performance.py -q
124 passed in 378.96s (0:06:18)
```

### 3.6 静态断言（E-1 / IMP-9 / L7″ / IMP-7 / IMP-2）

```console
$ python3 - <<'PY'   # AST 扫描（app/**），完整脚本见 §4 说明
parse_records calls: [('app/services/resource_import.py', 980, ['keep_cells', 'max_rows']),
                      ('app/services/resource_interface_ip_import.py', 1199, ['keep_cells', 'max_rows'])]
count: 2
_is_blank_record: banned=[]
_collect_records: banned=[]
  _collect_records loop-exit nodes: []
  list() calls: []
_finalise: banned=[]
_parse_csv: banned=['Try', 'ExceptHandler']        # 基线原样（未新增）
_parse_xlsx: banned=['Try', 'Try', 'Try', 'ExceptHandler', 'ExceptHandler']  # 基线原样（未新增）
parse_records: banned=[]
```

E-1 成立：`backend/app/**` 内 `parse_records(` 调用**恰好 2 处**，两处 `keywords` 均含 `max_rows` 与 `keep_cells`，分别由 `_MAX_TEMPLATE_COLUMNS`（14）与 `len(COLUMN_NAMES)`（26）推导。

---

## 4. 等价性自检（无 DB）— 真实输出

脚本位于 `/tmp/f038_selfcheck.py`（**不入库**）：内含 start_commit 语义的参考实现（`csv.reader` / `openpyxl.iter_rows` 全量物化 + `_cell_text` + 基线尾部空行裁剪 + 基线行数判定 + 基线异常白名单），与生产路径（`parse_records(data, fmt, max_rows=5000, keep_cells=14)` + 顺序相同的 consumer 判定）逐样例比对 `(verdict, header, rows)`。

`header` 逐元素比较；`rows` 按 consumer 可见投影比较（`(row[:14] + [""]*14)[:14]`，即 C2/C5 实际读取的 `padded[index], index < 14`）——该投影正是 §4.2 IMP-6 所依赖的等价口径（`()`/`[]` 与 `[""]*702` 在 consumer 眼里完全相同）。

```console
$ cd backend && PYTHONPATH=. python3 /tmp/f038_selfcheck.py
=== 环境 ===
python 3.12.7
openpyxl 3.1.5 openpyxl.LXML True
lxml 5.2.1
_MAX_TEMPLATE_COLUMNS=14 keep_cells(F014)=14

=== 等价性自检（verdict / header / rows 投影到前 keep 列） ===

[1 合法 3 行 CSV（1 中间空行 + 2 尾部空行）] bytes=268
  参考 verdict: ok
  生产 verdict: ok
  header: len=14 前3=['cluster', 'hostname', 'resource_type']
  rows: 4 行 × 14 列
  header/rows 逐元素相等: True
  EQUAL=True

[2 5000 行 CSV → 正常] bytes=190138
  参考 verdict: ok
  生产 verdict: ok
  header: len=14 前3=['cluster', 'hostname', 'resource_type']
  rows: 5000 行 × 14 列
  header/rows 逐元素相等: True
  EQUAL=True

[3 5001 行 CSV → 413] bytes=190176
  参考 verdict: ImportRowLimitExceeded({'limit_rows': 5000})
  生产 verdict: ImportRowLimitExceeded({'limit_rows': 5000})
  header/rows 逐元素相等: True
  EQUAL=True

[4 5001 行 + 末行 131,073 字符 → 422] bytes=321212
  参考 verdict: ImportInvalidFile(unreadable, )
  生产 verdict: ImportInvalidFile(unreadable, )
  header/rows 逐元素相等: True
  EQUAL=True

[5 5001 行 + 末行 200 列 → 413] bytes=191028
  参考 verdict: ImportRowLimitExceeded({'limit_rows': 5000})
  生产 verdict: ImportRowLimitExceeded({'limit_rows': 5000})
  header/rows 逐元素相等: True
  EQUAL=True

[6a 宽表 xlsx dimension A1:ZZ6000 → 413] bytes=50135
  参考 verdict: ImportRowLimitExceeded({'limit_rows': 5000})
  生产 verdict: ImportRowLimitExceeded({'limit_rows': 5000})
  header/rows 逐元素相等: True
  EQUAL=True

[6b 宽表 xlsx dimension A1:ZZ5000 → 表头 422] bytes=42826
  参考 verdict: ImportInvalidFile(unknown_columns, {'unknown_columns': '<688 items>'})
  生产 verdict: ImportInvalidFile(unknown_columns, {'unknown_columns': '<688 items>'})
  header: len=702 前3=['cluster', 'hostname', 'resource_type']
  header/rows 逐元素相等: True
  EQUAL=True

全部样例等价: True
```

样例构造要点：6a/6b 为 `dimension A1:ZZ{N}` + 每行 `<c r="A{r}"><v>{r}</v></c>`（全部行非空，故计入行数）；6b 因 `unknown_columns` 明细含 688 个空串而落到表头 422（与架构 §13.4 TD-I-8 勘误一致：宽 dimension 下 openpyxl 把表头行补齐到 702 格）。样例 4 走 `csv.Error`（字段 > 131072）→ **422 `unreadable`**；样例 5 走行级超宽 → **413**；ON-1 配对构造成立。

补充边界（同脚本函数复用，临时命令）：

```console
5000 data + 2 trailing blanks: ref=ok prod=ok eq=True rows=5000
5001 data + 2 trailing blanks: ref=ImportRowLimitExceeded({'limit_rows': 5000}) prod=ImportRowLimitExceeded({'limit_rows': 5000}) eq=True
4999 data + 2 trailing blanks: ref=ok prod=ok eq=True rows=4999
header only + 5 trailing blanks: ref=ok prod=ok eq=True rows=0
1000 middle blanks + 1 bad row: ref=ok prod=ok eq=True rows=1002
1100 error rows (preview/truncation shape): ref=ok prod=ok eq=True rows=1100
4999+3 blanks+1 data (5003 -> 413): ref=ImportRowLimitExceeded({'limit_rows': 5000}) prod=ImportRowLimitExceeded({'limit_rows': 5000}) eq=True
4996+3 blanks+1 data (5000 -> ok): ref=ok prod=ok eq=True rows=5000
```

「1000 中间空行 + 1 行错误」得 `rows=1002`，与架构 §8.2 S-W7 期望（`total_rows=1002`，错误行号 1002）一致；「5000 + 尾部空行」与「5001 + 尾部空行」证明 `pending_blanks` 不改变行数判定。

### 4.1 等价性自检结果表

| # | 输入 | 参考 verdict | 生产 verdict | verdict/header/rows 全等 |
| --- | --- | --- | --- | --- |
| 1 | 合法 3 行 CSV（1 中间空行 + 2 尾部空行） | `ok`（header 14，rows 4） | `ok`（header 14，rows 4） | ✅ |
| 2 | 5000 行 CSV | `ok`（rows 5000） | `ok`（rows 5000） | ✅ |
| 3 | 5001 行 CSV | `ImportRowLimitExceeded{limit_rows:5000}` | 同左 | ✅ |
| 4 | 5001 行 + 末行单字段 131,073 字符 | `ImportInvalidFile{unreadable}` | 同左 | ✅（非 413） |
| 5 | 5001 行 + 末行 200 列 | `ImportRowLimitExceeded{limit_rows:5000}` | 同左 | ✅（非 422/500） |
| 6a | 宽表 xlsx `A1:ZZ6000`（6000 行） | `ImportRowLimitExceeded{limit_rows:5000}` | 同左 | ✅ |
| 6b | 宽表 xlsx `A1:ZZ5000`（5000 行） | `ImportInvalidFile{unknown_columns}`，688 项 | 同左（688 项，逐元素相等） | ✅ |

### 4.2 `tracemalloc` 峰值对比（记录数值，不做阈值断言）

```console
=== tracemalloc 峰值对比（多次重复，单位 MiB） ===
[5 5001 行 + 末行 200 列] run1: 生产=2.482 MiB 参考=2.731 MiB 倍率=0.909 bytes=191028
[5 5001 行 + 末行 200 列] run2: 生产=2.482 MiB 参考=2.731 MiB 倍率=0.909 bytes=191028
[6a 宽表 A1:ZZ6000 (6000 行)] run1: 生产=1.818 MiB 参考=68.148 MiB 倍率=0.027 bytes=50136
[6a 宽表 A1:ZZ6000 (6000 行)] run2: 生产=1.817 MiB 参考=68.148 MiB 倍率=0.027 bytes=50136
```

| 样例 | 生产峰值 | 参考（基线）峰值 | 生产/参考 | 说明 |
| --- | --- | --- | --- | --- |
| 5（5001 行 + 末行 200 列，CSV） | 2.482 MiB | 2.731 MiB | 0.909 | 两侧均被 `data.decode("utf-8-sig")` 地板（0.19 MB 输入）主导；无可测退化 |
| 6a（`A1:ZZ6000` 宽表 xlsx） | 1.818 MiB | 68.148 MiB | 0.027 | 基线物化 5999 行 × 702 格；生产保留 `(max_rows+1) × 14` |

结论（仅限本自检样本，**不替代 TEST 的 M1–M6 正式测量**）：生产峰值不再随「超过 max_rows 的行数」与「超过 `keep_cells` 的列数」增长；CSV 路径峰值地板为 UTF-8 解码整串（架构 §4.5 已如实登记）。

---

## 5. 未验证项（留待 TEST）

| # | 未验证项 | 归属 |
| --- | --- | --- |
| U-1 | I 层真实 PostgreSQL 全矩阵：4 端点 ×（F037 的 8 例 + 输入③ + S-W1..S-W7 + 413/422/`empty_file`/`unsupported_format`/表头四类/行级错误/正常批次）状态码与 `resp.json()` 深比较（TD-I1..I10）。本次仅复跑既有套件，未新增差分端点矩阵 | TEST |
| U-2 | 架构 §13.2 阈值 T-1 / T-1b / T-2 / T-3 / T-4 / T-6 的正式测量与断言（含 N=2501 / 4N=10001 的 xlsx 族与 `excess()` 口径）、T-5 时间记录 | TEST |
| U-3 | 毒值探针（§13.1 P-1..P-4）与 `U4` 裁剪安全性取证、`U1` 全类型等价参数化（本报告仅用 `None`/`str`/数字等真实解析产出类型做了整行等价抽查，未构造毒值） | TEST |
| U-4 | `errors_truncated` / `error_count` / `importable_rows` 端点级逐字段相等（R-4） | TEST |
| U-5 | `ru_maxrss` 交叉参照、`S-W2`（`A1:XFD10001`）与 `S-W2b`、`MemoryError`/`RecursionError` 语义（F037 U-d/U-f 已随 52 项全绿间接覆盖，但未单列断言） | TEST |
| U-6 | 无 `dimension` 稀疏 sheet / `dimension` 与实际不一致两例（R-6） | TEST |

---

## 6. 风险与遗留

| ID | 项 | 级别 | 现状 |
| --- | --- | --- | --- |
| R-1 | 行号位移 | HIGH（架构维持） | 实现按 D3/IMP-6 补回占位；自检「1000 中间空行」得 `rows=1002` 与 S-W7 期望一致；端点级行号断言留 TEST（U-1） |
| R-2 | `_is_blank_record` 与 `_cell_text` 不等价 | MEDIUM | 未新增分支；`Decimal` / `datetime` / `timedelta` / `nan` 的逐类型等价由 U1 覆盖（U-3） |
| R-3 | 残余无界面（`read_manifest`/`read_strings`/`file.file.read()`） | MEDIUM | **未消解**（AQ-2=A）；本报告不宣称已消除 |
| R-4 | 预览/计数语义 | HIGH（架构维持） | 行集合按投影逐元素相等（自检）；端点级留 TEST（U-4） |
| R-5 | 时间退化 | LOW | 新判定只做 `is None or == ""`（无文本构造），自检无退化迹象；T-5 由 TEST 记录秒数 |
| R-6 | openpyxl dimension 行为差异 | MEDIUM | 自检 6a/6b 覆盖「dimension 决定 max_row/max_col」的实际行为；无 dimension / dimension 不一致两例留 TEST（U-6） |
| R-7 | 413/422 顺序回归 | HIGH（架构维持） | 样例 4→422、样例 5→413、6a→413 全等；`_finalise` 在 `with` / `finally` 之外（IMP-4），for 体无 `break`/`return`（IMP-7） |
| R-8 | L7′ / L7″ | MEDIUM | §1.3 / §3.6 AST 与 grep 证据 |
| R-9 | 生产调用点漏传参数 | MEDIUM | E-1 全模块 AST：恰 2 处、均带两关键字 |
| R-10 | 新增 `except` / `MemoryError` 语义 | MEDIUM | 本次 diff 无新增 `except`；`except Exception` 仍 2 处 |
| R-12/R-13/R-14 | TD 期望值/阈值/单侧断言 | — | 本阶段不涉及；TEST 按 §13.2/§13.4 执行 |
| 遗留-1 | 语义变化告知（§13.5）：两参数 `parse_records` 语义变为「已剔除尾部空行 + 无行数上限」 | — | F037 文件零 diff、52 项全绿，未出现相关断言失败 |
| 遗留-2 | product §2.1 S3 errata（ON-1 措辞澄清） | — | 归属 Product Manager，本角色未改动 `docs/features/F038/product.md` |

---

## 7. 公共交接字段

- **已确认需求**：F038 product S1–S8 / B1–B13 / A1–A14；architecture §13 定稿（IMP-1..IMP-10、DR-F038-02、ON-1 口径）。
- **已做决策**：按 §4.2 定稿代码落稿；`_MAX_TEMPLATE_COLUMNS` 取 14；F023 `keep_cells=len(COLUMN_NAMES)`=26；`data_records = records[1:]`（IMP-5 优先于 §4.2 代码块中的 `list(records[1:])` 写法，理由为该代码块与 IMP-5 冲突时以 §13.7 IMP 条目为准）。
- **关键约束**：契约零 diff、测试零 diff、无新依赖/新 `except`/新 I/O/新日志、行数上限为唯一可观察拒绝点。
- **当前假设**：`_is_blank_record` 对两条解析路径可产出类型与 `_cell_text` 等价（架构 §13.9 已降级为 MEDIUM，最终由 U1 兜底）。
- **未解决问题**：无阻塞项；§5 的 U-1..U-6 属 TEST 阶段范围。
- **后续关注**：TEST 的 M 系列阈值须按 §13.2 且公布公式与两侧数值；S-W4/S-W5 配对构造不得互换（ON-1）。

---

**BACKEND COMPLETE** —— 实现与本次要求的必要验证（编译、lint、零 diff 守卫、F037 52 项与导入回归套件、无 DB 等价性自检 + 峰值记录）均已完成；I 层端点级全矩阵与测量阈值按分层留待 TEST。

GIT: git rev-parse --short HEAD
GIT: git log --oneline -3
GIT: git status --porcelain
GIT: git diff --stat -- backend/app/services/
GIT: git diff --stat -- docs/api docs/database frontend backend/alembic backend/pyproject.toml backend/Dockerfile
GIT: git diff --stat -- backend/tests/
GIT: git diff --stat -- backend/tests/integration/test_f037_import_parse_errors.py
GIT: git diff -- backend/app/services/
GIT: git diff -U0 -- backend/app/services/
