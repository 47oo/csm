# F038 导入解压 / 解析内存边界加固（R05）— Test Report

> 同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本、结论与证据。
> **当前状态**：§1 TEST DESIGN = **TD-F038-1（v1，2026-10-29，`TEST DESIGN READY`）**；§2 TEST EXECUTION = **TE-F038-2（v2，2026-10-29，repair round 1 修复复测，`READY FOR REVIEW`）** —— 定点复测 8 项 PASS、整模块 **76 passed**、F037 52 项与 R1–R6 全绿；`DEF-01`/`DEF-02` 已按 architecture **§14** 判定为**阈值口径缺陷且已修正（实现零变更）**并关闭，见 §2.10。
> §2 的 M 层 CSV 族公式为 **architecture §14.2 的 T-1b′ / T-1c / T-2′（`work` 口径 + 实测地板 `F(x)`）**；§13.2 的 T-1b 全文、T-2 的 `excess` 定义与「S-W6a 余量 ≥2×」测算、旧 `DEF-01`/`DEF-02` 判定**已作废**（§14.7），作废范围见 §2.12。
> §1 中关于 **S-W2 期望 413** 的表述已按 architecture §13.4 勘误为 **422 `unknown_columns`**，勘误落稿见 §2.3。
> `TEST DESIGN READY` 仅表示「方案可执行、可验证」，**不是测试通过**，**不批准实现**，也不放行合并。

**版本记录**

| 阶段 | 版本 | 日期 | 结论 | 依据 HEAD / 工作区 |
| --- | --- | --- | --- | --- |
| TEST DESIGN | TD-F038-1 | 2026-10-29 | **`TEST DESIGN READY`** —— U1–U6 / I1–I15 / M1–M6 / S1–S6 + R1–R6 全部可执行映射；样例规模经小规模实测校准；ON-1 口径已独立实证 | `9ec4644`（分支 `feature/F038-import-parse-bounds`，start_commit `8e609ca`）；`git status --porcelain --untracked-files=all` 为空，`git diff --stat 8e609ca -- backend docs/api docs/database frontend` 为空 ⇒ 实现未开始 |
| TEST | TE-F038-1 | 2026-10-29 | `BLOCKED` —— 72 passed / 3 failed；3 项 FAIL 全为 §13.2 CSV 族阈值（`T-1b`、`T-2`@S-W6a），判为 **Architect 阈值口径缺陷**（`DEF-01`/`DEF-02`），实现侧无缺陷 | `e954537`（实现提交 `3289d39`）；实现/测试/报告三处写入 |
| TEST（修复复测） | **TE-F038-2** | **2026-10-29** | **`READY FOR REVIEW`** —— 按 architecture **§14.5 白名单**复测：定点 `m3a or m4b or m4d or m4e or m6` = **8 passed**，整模块 = **76 passed**，`test_f037_import_parse_errors.py` = **52 passed（零修改）**，R2–R6 = 70/31/48/4/3 全绿；`T-1b′` / `T-1c` / `T-2′`（含 S-W6b/S-W6c）全 PASS，G-A1/G-A2/G-A3/G-B 全 PASS；`DEF-01`/`DEF-02` 关闭（口径缺陷已由 §14 修正，**实现未变**） | `a3a2b9c`（`docs(F038): repair round 1 - CSV threshold re-ruling`）；工作区仅 `backend/tests/integration/test_f038_parse_bounds.py` 修改 + 本文件；`git diff --stat -- backend/app/services/` **空** |

---

## 1. Test Design（TD-F038-1，v1，2026-10-29）

### TD-1 Task / Status / Basis

- **Task**：F038「导入解压 / 解析内存边界加固（R05）」——FEATURE / P1 / M29；plan revision 25；requirements revision 16；阶段 **TEST_DESIGN**。Tester 只读核对 + **只写本文件**，未改生产代码、测试代码、契约或计划，未执行 Git 写操作。
- **Status**：**`TEST DESIGN READY`**。判定依据：① product A1–A14 与 B1–B13 全部有可执行映射；② architecture §9.3 的 U1–U5 / I1–I10 / M1 / S1–S5 **全部展开**为具体用例（并补 U6、I11–I15、M2–M6、S6）；③ 基线测量方案在**不修改工作区**的前提下可执行（`git show` + `importlib`，已实测载入成功）；④ 样例构造的**可行性**已用小规模探针实测（含 dimension 伪造 → 宽表展开、空 `<row/>` → 大使用区域、ON-1 两类尾部输入的真实异常类）。
- **本阶段未执行**任何测试套件、构建或应用启动；**未**运行任何可能 OOM 的大样例（只做规模校准用的小规模量测与外推估算，见 TD-7.3）。

| Basis | 版本 / 状态 | 本 TD 用途 |
| --- | --- | --- |
| `docs/features/F038/product.md` | v1（READY FOR ARCHITECT） | §1.2 AQ-2=A 边界、§2.1 S1–S8、§2.2 **B1–B13**（不变量，验收唯一来源）、§2.3 N1–N10、§5 ON-1–ON-7、§6 **A1–A14** |
| `docs/features/F038/architecture.md` | v1（READY FOR DESIGN） | §2 C1–C8 消费契约、§4.1 D1–D4、§4.2 定稿代码（`_is_blank_record` / `_Collected` / `_collect_records` / `_finalise`）、§4.5 空间有界/时间线性、§8 测量与验证、**§9.3 TD 输入（U1–U5 / I1–I10 / M1 / S1–S5）**、§9.4 DR-F038-01..06、§11 ON-1 口径 |
| `docs/features/F037/architecture.md` | v1 + §15 CONTRACT 增补 | §15.4/§15.10 DR-F037-08、**§15.10.4 L7′**、§15.10.7 测试边界（不得用磁盘文件喂 `load_workbook`）、§12 OPEN-T3（DR-F038-02 已裁定） |
| `docs/features/F037/test-report.md` | TD-F037-1 / TE-F037-1 | 52 项用例与 **L7′/AST 守卫先例**（`test_td_f037_s7_oserror_is_local_to_parse_xlsx`）、输入 ①②③ 构造手法、`_rewrite_zip` / `PATH` 常量、回归计数 42/28/31/48/4/3 |
| `docs/api/F014.md` v1 §1.2/§2/§7/§10/§13；`docs/api/F023.md` v2 §1.2/§2/§7/§14/§17 | 不变 | `reason` 集合、校验顺序、行号、上限常量、双载体等价 |
| `docs/product/requirements-v3.md` | revision 16 | §22、§24、§24.1、§24.5、§24.6、§31 **T28 / T72 / T107–T116 / T124 / T126**、§32 |
| `backend/app/services/resource_import.py`（`9ec4644`，1061 行） | 只读核对 | `_cell_text` :423、`_invalid_file_on_parse_failure` :441、`_close_workbook` :466、`_parse_csv` :480（`list(csv.reader(` :486）、`_parse_xlsx` :490（`list(worksheet.iter_rows(` :528）、`parse_records` :535、`_resolve_template` :542、`_validate_record` :656（`padded` :675–676）、`parse_and_validate` :867（`records[1:]` :884、裁剪 :887–888、413 :891、表头 :894）、`write_import` :950 |
| `backend/app/services/resource_interface_ip_import.py`（1566 行） | 只读核对 | `_resolve_header` :369（表头**整行**）、`_cells_for` :389（`padded` 只读前 26）、`_parse_row` :503、`parse_and_validate` :1187（:1205–1208 裁剪+413、:1210 表头、:1238 `total_rows`）、`COLUMN_NAMES`（26 列） |
| 回归基线测试 | 只读 | `tests/integration/test_f037_import_parse_errors.py`（52 项，U+I+S 同模块）、`test_import_performance.py`（4 项，`tracemalloc` + `perf_counter` 先例）、`tests/conftest.py`（DB-D10 双守卫、`auth_app` / `auth_session_factory` / `committed_engine`）、`f015_helpers.py`（`role_client_factory` + 对象 helper）、`test_f023_resource_interface_ip_import.py`（26 列 fixture 与 `COUNT_TABLES`） |
| 规则与方法 | — | `AGENTS.md`、`docs/project/handoff.md`、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`.pi/agents/tester.md` |

### TD-2 层记号、可验证性前提与本轮设计修正

| 记号 | 载体 | 说明 |
| --- | --- | --- |
| **U** | pytest 直调 `app.services.resource_import` / `resource_interface_ip_import` 的纯函数与私有函数 | **不需要数据库、不需要 HTTP** |
| **I** | pytest + `auth_app`（真实 `create_app`）+ **真实 PostgreSQL**（`TEST_DATABASE_URL`，DB-D10 双守卫） | 4 端点 × 输入矩阵、差分等价、零写入/Audit、401/403、消费者宽度探针 |
| **M** | pytest 内 `tracemalloc` / `perf_counter` + `/tmp` 基线模块（不入库） | 内存峰值与时间证据；数值写入 §2 TEST 报告 |
| **S** | 源码 AST / `grep` / `git diff`（写入 §2 报告的命令证据） | L7″、调用点参数、零 diff 守卫 |
| **R** | 既有回归套件 | T28 / T72 / T107–T116 / T124 / T126 零回归 |

**可验证性前提**

1. **实现未开始**：工作区 `backend/**` 相对 `8e609ca` 零 diff（TD-3 实测），`inspect.signature(resource_import.parse_records)` 仍为 `(data, fmt)`，无 `max_rows` / `keep_cells`。⇒ 本阶段所有 U/I/M/S 用例状态为「待执行」，不得读作 PASS。
2. **符号名以 architecture §4.2 为准**，但**按语义断言**：`_is_blank_record`、`_Collected`、`_collect_records`、`_finalise`、`_MAX_TEMPLATE_COLUMNS`、`parse_records(max_rows=, keep_cells=)`。等价改名不判 FAIL，但须在 §2 报告登记实际名称（F037 TD-2 同口径）。
3. **不发明规则**：预期只引用 A1–A14 / B1–B13 / F014 §1.2 / F023 v2 §1.2 / ON-1 口径。架构未固定处以 `TD-I-*` 登记（TD-12），不转成断言。
4. **ON-1 口径（架构 §11 已裁定，本轮独立实证）**：**尾部解析器异常 → 422，不是 413**；只有行级错误 / 超宽行 → 413。product §2.1 S3「5001 行 + 尾部解析损坏仍 413」按此解释。本 TD 的 S-W5 期望值固定为 **422 `IMPORT_INVALID_FILE{reason:"unreadable"}`**，并已用 start_commit 语义实测确认（TD-3.3）⇒ 任何把 S-W5 写成 413 的实现或用例都判 **FAIL**。
5. **测试模块落点**：新建 `backend/tests/integration/test_f038_parse_bounds.py`（U + I + M + S 同模块，沿用 `test_f037_import_parse_errors.py` 先例）。该模块**不导入** `app.core.access_scope` 符号 ⇒ 无需 `pytest.mark.real_scope`（由 `test_f030_test_harness.py` AST 门禁复核）。
6. **不改既有用例**：`test_f037_import_parse_errors.py` 的 52 项**零修改**（B8 / S7 的硬要求）；F034 / F035 / F036 套件与 corpus 零修改。

**本轮设计修正（相对 architecture §8.3 / §9.3，均为「可执行性」修正，不改业务口径，登记为 TD-12 `TD-I-1`…`TD-I-4`）**

| # | 架构原表述 | 实测/推导 | 本 TD 处置 |
| --- | --- | --- | --- |
| C-1 | §8.4/§9.3 U4：「`list` 子类记录 `__getitem__` 最大下标」证明 citizen 不读第 W 列之后 | **探针会被 `list()` 拷贝绕过**：`_validate_record` :675 与 `_cells_for` :390 都先 `list(cells)`（走 `__iter__`），随后下标读取发生在**普通 list 副本**上 ⇒ 子类 `__getitem__` 只看到一次 `len()`/拷贝，看不到真实读取宽度 | 改为 **毒值探针（动态）+ AST 守卫（静态）** 双证（TD-5 `U4` / `I14`） |
| C-2 | §8.3-1「同一构造族 N 与 4N 断言 `peak(4N) ≤ 1.5×peak(N) + 2 MiB`」 | CSV 峰值地板是**不可避免的解码文本**（`data.decode("utf-8-sig")` 后整串驻留，≤5 MiB）；4N 时该项线性增长，2 MiB 松量会被文本项吃掉，导致阈值在 CSV 族上恒假 | 「规模不敏感」**只对 xlsx 族**生效（S-W1/S-W2，输入仅 KB 级、展开达 MB~GB 级）；CSV 族改用「相对基线倍数 + 绝对哨兵」（`TD-I-2`） |
| C-3 | §8.4 参考实现「`_baseline_records` + 基线裁剪/行数逻辑」 | 单纯比对 records 无法覆盖 consumer 侧改动（F038 把裁剪/行数上移，consumer 也被改） | 参考实现上提为 **`_baseline_records` 返回「基线语义的 records（已裁剪+已判行数）」**，再用 **单点 monkeypatch 差分**同时覆盖 consumer（TD-8） |
| C-4 | §8.2「S-W1 10001×702 数百 MB / S-W2 10001×16384 ~1.3 GB」 | 小规模实测：702 宽 **16.4 KB/行**、16384 宽 **262.5 KB/行**（基线，含文本转换）⇒ 10001 行分别约 **164 MB / 2.7 GB**（后者本机 9.1 GB 可用内存下不可安全执行） | S-W1 按原规模测；**S-W2 基线侧降级到 1001 行**（等规模对比）并把原规模值标为 **ESTIMATE（外推，未实测）**（TD-7） |

### TD-3 环境探测（本轮实际执行，输出如实抄录）

#### TD-3.1 环境与工具链

| 探测项 | 命令 | 实际输出 | 结论 |
| --- | --- | --- | --- |
| Python | `python3 -V` | `Python 3.12.7` | 与 F037 TE 一致 |
| `openpyxl.__version__` | `python3 -c "import openpyxl; print(openpyxl.__version__)"` | **`3.1.5`** | 与 `pyproject.toml` 锁一致 |
| `openpyxl.LXML` | 同上 | **`True`** | `fromstring` 走 lxml；结论**不外推**到无 lxml 镜像（`TD-I-6`） |
| `lxml.__version__` | `python3 -c "import lxml; print(lxml.__version__)"` | **`5.2.1`** | 可选加速依赖在位 |
| `csv.field_size_limit()` | 同上 | **`131072`** | S-W5 尾字段以 131,073 字符构造 |
| `ulimit -v` | `ulimit -v` | **`unlimited`** | 无地址空间硬限；内存风险来自物理内存 |
| 物理内存 | `free -m` | `total 15634 MB`、`available 9191 MB`、`used 5674 MB`、`swap 4096 MB (used 2883)` | S-W2 原规模（估算 2.7 GB）**不可安全执行**；降级方案见 TD-7 |
| CPU | `nproc` | `16` | — |
| platform | `sys.platform` | `linux` | `/proc/self/fd` 可用（F037 I21 未 skip） |
| 被测文件规模 | `wc -l backend/app/services/resource_import.py` | **`1061`** | 与 `8e609ca` 版本行数相同 |
| 既有性能用例可采集 | `python3 -m pytest --collect-only -q tests/integration/test_import_performance.py \| tail -3` | **`4 tests collected in 0.43s`** | R5 基线 4 项 |

#### TD-3.2 基线 / 工作区状态（只读）

| 探测项 | 命令 | 实际输出 |
| --- | --- | --- |
| HEAD | `git rev-parse --short HEAD` | **`9ec4644`** |
| 分支 | `git rev-parse --abbrev-ref HEAD` | `feature/F038-import-parse-bounds` |
| 工作区 | `git status --porcelain --untracked-files=all` | **空**（无修改、无未跟踪） |
| 相对 start_commit 的实现/契约 diff | `git diff --stat 8e609ca -- backend docs/api docs/database frontend` | **空** ⇒ 实现未开始、契约零 diff |
| 基线文件获取（不入库） | `git show 8e609ca:backend/app/services/resource_import.py > /tmp/f038_probe/baseline_resource_import.py` + `wc -l` | 载入 **1061 行**（与 HEAD 一致 ⇒ 该文件自 start_commit 未变） |
| `parse_records` 现状签名 | `inspect.signature(resource_import.parse_records)` | `(data: 'bytes', fmt: 'str') -> 'list[list[str]]'` ⇒ **F038 的 `max_rows` / `keep_cells` 尚未实现** |
| 模板宽度 | `max(len(t.columns) for t in TEMPLATES)`；`len(COLUMN_NAMES)` | **14**（BM 14 / VM 10）；**26** |

#### TD-3.3 真实 PostgreSQL 与 ON-1 实证

| 探测项 | 命令 | 实际输出 |
| --- | --- | --- |
| `TEST_DATABASE_URL` 解析 | `make_url(os.environ["TEST_DATABASE_URL"])` | `driver postgresql+psycopg / host 127.0.0.1 / port 55432 / db csm_f037_test`；库名含 `test` = **True** |
| DB-D10 双守卫 | conftest `_require_test_database_url` | 库名含 `test` ✓、`DATABASE_URL` 未设 ✓ ⇒ 不接触生产/未知库 |
| 连通性 | `select 1` / `show server_version` | **`1`** / **`16.15`** |
| Schema 状态 | `select count(*) from pg_tables where schemaname='public'` | **`0`**（会话 fixture 将 `DROP SCHEMA public CASCADE` + `alembic upgrade head`） |
| 容器 | `docker ps --filter name=csm-f037-pg` | `csm-f037-pg\tpostgres:16-alpine\tUp 54 minutes\t0.0.0.0:55432->5432/tcp` |
| **ON-1 实证（start_commit 语义，`db=None` 因拒绝发生在任何 DB 访问前）** | `baseline.parse_and_validate(None, S-W4/S-W5, "csv", max_file_bytes=5_242_880, max_rows=5000)` | **S-W4（5001 行 + 尾部行级错误，167,988 B）→ `ImportRowLimitExceeded{'limit_rows': 5000}`（413）**；**S-W5（5001 行 + 尾部超长字段，299,051 B）→ `ImportInvalidFile{'reason': 'unreadable'}`（422）** |

> ON-1 由此从「架构推论」变为「已实证基线行为」：**413 只来自行级/超宽行，尾部解析损坏必为 422**。S-W5 断言 413 即为错误预期。

#### TD-3.4 基线模块加载可行性（M 层前置）

```text
spec = importlib.util.spec_from_file_location("f038_baseline_ri", "/tmp/f038_probe/baseline_resource_import.py")
baseline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = baseline     # ← 必须：dataclass() 需要 sys.modules 能查到本模块
spec.loader.exec_module(baseline)
→ baseline module loaded: f038_baseline_ri  has parse_records: True
→ baseline max template width: 14
```

**实测坑（必须写入用例注释）**：省略 `sys.modules[spec.name] = baseline` 时 `exec_module` 立即抛
`AttributeError: 'NoneType' object has no attribute '__dict__'`（`dataclasses._is_type` 通过 `sys.modules.get(cls.__module__)` 取模块）。基线模块依赖 `app.*`（`app.core.errors`、`app.models.resource` 等），因此**必须在 `backend/` 下、并已把 `backend/` 放入 `sys.path`** 后加载；该模块只在测试进程内存在，**不写入仓库**。

### TD-4 验收映射（A1–A14 / B1–B13 / S1–S8 → TD 用例 → T 条目）

| 验收 | 不变量映射 | TD 用例 | T 条目 |
| --- | --- | --- | --- |
| A1 同字节输入逐字一致 | B1–B9 | `U1`–`U6`（参考实现/等价）· `I1`–`I8`（S-W1..S-W7 + 合法 5000 行）· `I15`（F037 三输入 × 4 端点）· `M2`（参考实现对照真实基线） | T27、T28、T72、T107–T116、T126 |
| A2 内存峰值有界（相对倍数） | S1·B2·B3 | `M3`（相对基线 + 绝对哨兵）· `M4`（规模不敏感） | T28 |
| A3 超行数后继续迭代但不累积 | B2·B6 | `I1`（S-W1 413）· `I2`（S-W2 413）· `I6`（S-W6 413 变体）· `U3`（排空性）· `U5`（保留上界） | T28、T72 |
| A4 尾部空行 / BOM / CRLF / 混用 | B3·B5 | `U1`、`U2`（计数式裁剪语义）· `I3`（S-W3 CSV）· `I7`（S-W7 中间空行）· `I1`/`I2`（xlsx 尾部空使用区域） | T113、T27 |
| A5 上限与 1000 条预览 | B1·B4 | `I8`（合法 5000 行 200 + 计数）· `I11`（413 字节 / 413 行数）· `I12`（1100 行错误 → `errors` 恰 1000、`errors_truncated=true`） | T28、T111 |
| A6 校验顺序对角用例 | B6 | `I11`（413 先于表头）· `I12`· `I15` · `U3`（解析 422 先于行数 413） | T72 |
| A7 六类 reason 逐项不变；宽表走列类原因 | B7 | `I6`（S-W6 宽表 CSV → `unknown_columns`，不是新拒绝）· `I15`（`header_missing` / `missing_columns` / `unknown_columns` / `column_order` / `empty_file` / `unsupported_format`） | T72、T112 |
| A8 双载体等价；粘贴内容不留痕 | B9·B13 | `I13`（S-W3 / S-W6 文件 vs 文本载体，`json()` 深等）· `I9`（拒绝路径 7 表零变化）· `I15` | T107、T108、T114、T115 |
| A9 零写入 / 零 Audit；整批回滚 | B10 | `I9`（S-W1/S-W2/S-W4/S-W6 × 4 端点后 7 表计数逐表不变） | T27、T68、T123 |
| A10 401 / 403 先行 | B11 | `I10`（S-W1/S-W2 大样例 × 未登录/VIEWER × 4 端点） | T72、T115、T124 |
| A11 F037 52 项全绿；F034–F036 无回归 | S7·B8 | `R1`–`R6` | T27、T72、T107–T116、T124、T126 |
| A12 基准证据入库 | ON-4、ON-6 | `M1`–`M6`（脚本、样例构造、基线值、完成态值、两次重复、环境必录项、命令） | T28 |
| A13 零变更守卫 | B12·N2–N5 | `S1`–`S3`（`docs/api/` / 模板 / 端点 / 上限常量 / `pyproject.toml` / `Dockerfile` / `frontend/` 零 diff；无新增 `except`；无 `field_size_limit`；无 lxml 依赖） | T126、T106 |
| A14 内容保护 grep 级守卫 | B13 | `S5`（L7″：新增函数内无 `try`/`except`/`open(`/`Path(`/`logger.`)· `I9`（响应体不含 marker） | T115 |
| S2（product §2.1）同字节一致 | 同 A1 | 同 A1 | 同上 |
| S3 超行数不累积 | 同 A3 | 同 A3 + `I11` | T28 |
| S4/S5/S6 双载体 / 限额 / 顺序 | B9/B1–B5/B6 | 同 A8/A5/A6 | 同上 |
| S8 拒绝路径零副作用 | B10 | `I9` | T68、T123 |
| （DB）| layer.database=false | `TD-11`：**NOT_REQUIRED**（复核，不主张新增约束已验证） | — |
| （前端）| layers.frontend=false | **NOT_REQUIRED**（`S1` 守 `frontend/` 零 diff；T116 前端陈旧结果归 F034 R3） | T116 |

### TD-5 用例明细

记法：`ID | 层 | 目标 / 前置 | 构造 | 断言要点 | 映射`。全部用例写入新模块 `backend/tests/integration/test_f038_parse_bounds.py`。

#### TD-5.1 U 层（无数据库、无 HTTP）

| ID | 目标 / 前置 | 构造 | 断言要点 | 映射 |
| --- | --- | --- | --- | --- |
| `TD-F038-U1` | `_is_blank_record` 与 `all(_cell_text(c)=="" for c in values)` **全类型等价**（R-2） | 参数化矩阵：`[None, (), [], ("",), (None,), (" ",), (0,), (0.0,), (-0.0,), (True,), (False,), (Decimal("0"),), (datetime(2024,1,1),), (date(2024,1,1),), (time(12,0),), (timedelta(0),), (float("nan"),), ("", None, ""), ("0",), (b"",)]`，并追加 **真实解析器产物**：CSV `[]`（空行）、xlsx `(None,)*16384`（大使用区域整行空） | 对每行：`_is_blank_record(row) == all(_cell_text(c) == "" for c in row)`；`""`/`None`/空序列判真，`" "`/`0`/`"0"`/`True`/日期/`nan` 判假；**该函数不得抛异常**（含 `Decimal`/`date` 等非 CSV 类型） | B3、R-2 |
| `TD-F038-U2` | `_collect_records` + `_finalise` **语义表**（D1–D4） | 直接喂 list/generator：①行数 < cap；②= cap（`max_rows+1`）；③> cap；④中间 1 行空；⑤尾部 3 行空；⑥仅表头；⑦`header=None`（输入空记录序列）；⑧`max_rows=None`；⑨`keep_cells=None`；⑩100 列宽行 + `keep_cells=14` | ①②：`overflow is False`、`len(rows)` = 输入数据行数、返回值 `== [header, *rows]`（①）与 413（② 经 `_finalise`）；③：`overflow is True` 且 `rows == []`（已释放）、`_finalise` 抛 `ImportRowLimitExceeded(max_rows)`；④：占位以 **`()`** 补回且**保持位置**，`_finalise` 后该行为 `[""]*14`（长度与模板补齐一致）；⑤：`rows` 不含尾部空行、**长度不位移**；⑥：`_finalise` 返回 `[header]`；⑦：`_finalise` 返回 `[]`；⑧：无上限（`overflow` 恒 False）；⑨：数据行宽度 == 输入宽度；⑩：数据行 `len == 14` 而 `header` 宽度 == 100（表头整行，D2） | B2、B3、C1–C8 |
| `TD-F038-U3` | **排空性**：解析器异常不得被行数上限改写（B6 / R-7） | 自定义生成器：第 3 条 `raise csv.Error("boom")`，其后仍有 > `max_rows` 条；`_collect_records(gen, max_rows=5000, keep_cells=14)` | 抛 `csv.Error`（**不是** `ImportRowLimitExceeded`）；`_finalise` 从未被调用（用 spy/monkeypatch 计数=0）；另一变体：生成器共 5002 条合法记录 → 全量消费（`count == 5002`，用计数器生成器证明**迭代器被排空**） | B6、D4、R-7 |
| `TD-F038-U4` | **消费者宽度需求（静态侧）**：证明 `keep_cells=14/26` 安全（C-1 修正） | AST 解析两 service 源文件 | ① `_validate_record` 内对 `padded` 的下标读取**只**出现在 `for index, column in enumerate(template.columns)` 的推导式（下标来源必须是 `template.columns` 的枚举）；② `_cells_for` 同理（`enumerate(COLUMNS)`）；③ 两函数内**无** `padded[-1]` / `cells[-1]` / `max(` / 负索引 / 切片读取；④ 全模块 `_is_blank_record` 的调用点只在 `_collect_records` 循环内、且在裁剪之前 | C2、C5、D2、R-2 |
| `TD-F038-U5` | **保留上界**：`len(rows) ≤ max_rows+1`（超高行数不累积） | 纯生成器 100,000 条宽记录（`["x"]*200`），`max_rows=5000`、`keep_cells=14`；用 `tracemalloc` 记录该调用峰值 | 消费条数 == 100,000（排空）；`collected.overflow is True`；`len(collected.rows) == 0`（超额即释放）；调用峰值 ≤ 8 MiB（该用例**无输入字节、无解码文本**，可设窄哨兵）；`_finalise` 抛 `ImportRowLimitExceeded` | D1、A3 |
| `TD-F038-U6` | **DR-F038-02 兼容**：`parse_records` 两参数调用仍等价于无界物化；kwargs 存在性 | `inspect.signature` + 对 5 个小样例（合法 CSV / xlsx / 尾空行 / 中间空行 / 表头 100 列）分别调用 `parse_records(data, fmt)` 与 `parse_records(data, fmt, max_rows=None, keep_cells=None)` | 签名含 `max_rows` 与 `keep_cells`（均可选、默认 `None`）；两参数调用**不抛** `TypeError`；两次结果**逐字节相等**；返回类型 `list[list[str]]`、`records[0]` 为完整表头 | DR-F038-02、ON-2、B12 |

#### TD-5.2 I 层（真实 PostgreSQL + 真实 `create_app`）

**统一前置夹具**：`auth_app`、`role_client_factory`（EDITOR）、`auth_session_factory`、`committed_engine`；4 端点常量与 `headers_for(path)` 复用 F037 模块同值写法（模块内自持常量，不跨测试模块 import）。成功路径需先建 Cluster（BM 14 列）或 Cluster + Network（26 列），用 `create_cluster` / `create_network` helper 走真实 API 创建。

**差分断言模板（DB 层，全 I 用例共用）**：对同一 `(path, data, fmt)` 执行两遍 —— (a) 真实路径；(b) `monkeypatch.setattr(resource_import, "parse_records", lambda data, fmt, **kw: _baseline_records(data, fmt, max_rows=5000))` 的**基线语义路径**；比较 `(status_code, resp.json())` 深等，或（服务层用例）`(异常类型, details)` / `result_payload()` 深等。详见 TD-8。

| ID | 目标 / 前置 | 构造 | 断言要点 | 映射 |
| --- | --- | --- | --- | --- |
| `TD-F038-I1` | **S-W1 宽表 xlsx**（702 列 × 10,001 数据行） | `dimension` 改写为 `A1:ZZ10002`，仅 A 列有值（文件 ~0.4 MB） | 4 端点：真实路径 == 基线语义路径（状态码 + JSON 深等）；期望 **413 `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows:5000}`**；`write` 端点零写入；M3 记录该样例峰值（见 TD-6） | A1、A2、A3、B2 |
| `TD-F038-I2` | **S-W2 大使用区域 xlsx**（16,384 列 × 10,001 行空 `<row/>`） | 合成 `sheetData`（表头 + 1 行 + 9,999 个 `<row/>`）+ `dimension A1:XFD10002`（文件 ~6 KB） | 同 I1：4 端点差分相等 + **413**；`total_rows` 不出现（413 无计数）；零写入；M3 记录峰值（此样例是「小字节 → 大展开」的主证据） | A1、A2、A3、B2 |
| `TD-F038-I3` | **S-W3 尾部空行 CSV**（表头 + 3 行 + 100,000 个 `\n`） | BM14 / 26 列两版；成功批次（Cluster / Network 预备） | 4 端点差分相等；两 `validate` 端点 **200** 且 `total_rows == 3`、`error_count == 0`、`importable_rows == 3`；`write` 端点 **201** 且 `created == 3`；行号自 2 起；尾部空行**不计入** `total_rows`（B3） | A1、A4、A5、T113 |
| `TD-F038-I4` | **S-W4 5001 行 + 尾部行级错误 / 超宽行** | 5001 合法行 + 末行 `role="NOT_A_ROLE"`（变体：末行 200 列） | 4 端点差分相等；**413 `IMPORT_ROW_LIMIT_EXCEEDED`**（行级错误**不得**抢先变 422；顺序 413 先于逐行）；零写入 | A1、A3、A6、B2、B6 |
| `TD-F038-I5` | **S-W5 5001 行 + 尾部解析损坏（ON-1）** | CSV：末行单字段 131,073 字符（总 299,051 B）；xlsx 变体：sheet 结束标签损坏 + 5001 行 | 4 端点差分相等；期望 **422 `IMPORT_INVALID_FILE{details == {"reason":"unreadable"}}`**；**显式反例排除** `413`、`500`、2xx（`assert resp.status_code == 422` + `assert code != IMPORT_ROW_LIMIT_EXCEEDED`）；零写入 | A1、A6、B6、B8、ON-1 |
| `TD-F038-I6` | **S-W6 宽表 CSV** | 变体 a：4000 行 × 651 空列（≈2.6 MB）→ 行数**不**超限，走表头列类；变体 b：5001 行 × 520 空列 → 行数超限 | a：4 端点差分相等，BM 端点 **422 `unknown_columns`**（26 列端点同族 reason）、`details.unknown_columns` 逐项与基线相同；b：**413**；两者均**不出现**新的「工作量/宽度类」拒绝（B7/N1）；M3 记录 a 的峰值 | A1、A2、A7、B7、N1 |
| `TD-F038-I7` | **S-W7 中间大段空行** | 表头 + 1 合法行 + 1000 空行 + 1 行带错误（`role` 非法） | 4 端点差分相等；`validate` 端点 `total_rows == 1002`；首个空行的行号 == **3**、末错误行行号 == **1003**（行号不位移，R-1）；`error_count == 1000*3 + 1 == 3001`、`errors_truncated is True`、`len(errors) == 1000`；`write` 端点 **422 `IMPORT_VALIDATION_FAILED`** + 零写入 | A1、A4、R-1、R-4、B5 |
| `TD-F038-I8` | **合法 5000 行**（上限边界）+ 计数口径 | BM14 5000 行合法 CSV（167,918 B）与 xlsx 版 | 两 `validate` 端点 **200**：`total_rows == 5000`、`error_count == 0`、`importable_rows == 5000`、`errors == []`、`errors_truncated is False`；真实 == 基线语义；M3 阈値 3（无退化）记录峰值/时间；**5000 行 `write` 端点等价性 → `NOT TESTED`**（F037 实测该路径 300 s+，见 TD-10） | A5、B1、B4 |
| `TD-F038-I9` | **零写入 / 零 Audit**（B10） | `committed_engine` + 7 表计数（`clusters / resources / bare_metal_details / virtual_machine_details / interfaces / ip_addresses / audit_logs`）；对 S-W1、S-W2、S-W4、S-W6a 各提交 4 端点后重采 | 7 表计数**逐表不变**；无 2xx；响应体不含 marker（`F038-MARKER-…`）、`filename`、`Traceback`、`.py`、`<worksheet`；`audit_logs` 不变即同时覆盖 Activity（Activity 无独立表，**不得**写「已检查 activity 表」） | A8、A9、A14、B10、B13 |
| `TD-F038-I10` | **401 / 403 先行**（有界解析不得提前消费请求体改变顺序） | S-W1、S-W2 字节 × (a) 未登录 `TestClient(auth_app)` (b) `role_client_factory("VIEWER")` × 4 端点 | (a) 全 **401** `AUTH_REQUIRED`；(b) 全 **403** `FORBIDDEN`、`details.reason == "permission"`；**均不得**出现 413/422/500 | A10、B11、T72、T124 |
| `TD-F038-I11` | **上限对角：413 字节 vs 413 行数 vs 表头 422**（顺序不变） | (a) `> 5,242,880 B` 的 CSV（前置：仍为解析前拒绝）；(b) 5001 合法行；(c) 5001 行 + **错误表头**；(d) `import_max_rows=1` + 2 行 + 错误表头 | (a) 4 端点 **413 `IMPORT_FILE_TOO_LARGE{limit_bytes:5242880}`**（不得被挪到解析后、不得新增第二道字节拦截）；(b) 413 行数；(c) **413 行数**（行数先于表头）；(d) 413 行数（既有 `test_validation_order_row_limit_before_header` 同口径）；全部真实 == 基线语义 | A5、A6、B1、B2、B6、T28、T111 |
| `TD-F038-I12` | **`errors_truncated` / 预览 1000 / `importable_rows`**（R-4） | 1100 行（每行 `cluster="MISSING"` → 每行 1 错误）；另加 S-W7（3001 错误） | `total_rows == 1100`、`error_count == 1100`、`len(errors) == 1000`、`errors_truncated is True`、`importable_rows == 0`；错误列表**逐元素**与基线语义相等（含 `row`/`field`/`reason`/`related_row` 四键集）；零写入 | A5、B4、R-4、T109 |
| `TD-F038-I13` | **双载体逐字段等价**（T114 追认口径） | S-W3 与 S-W6a 字节，分别以文件载体（`f038-file-carrier.csv` / `text/csv`）与文本载体（`csm-pasted-import.csv` / `text/csv;charset=utf-8`）提交 4 端点 | `status_code` 相同且 `resp.json()` **深等**；2 次重复一致；粘贴内容不入库/不入审计/不回显（`I9` 覆盖计数与内容） | A8、B9、T107、T108、T114、T115 |
| `TD-F038-I14` | **消费者毒值探针（C-1 修正的动态版）** | 用参考实现生成 100 列宽 records，把第 ≥ W 列（F014 `W=14`、F023 `W=26`）的单元格替换为 `_Poison`（任何属性访问/比较/`strip`/`str` 都 `raise AssertionError`），`monkeypatch` 让 `parse_records` 返回这组 records，再调两 service 的 `parse_and_validate`（真实 session）：成功行 + 3 类错误行（未知 cluster / 非法整数 / 文件内重复 hostname） | 全部调用**不触发** `_Poison`；所得 `result_payload()` 与「第 ≥ W 列置空」的同构输入**完全相等**；对照负向：把 `_Poison` 放到第 13 列（W 内）→ **必须**触发（证明探针有效、非空跑） | C2、C5、D2、R-2 |
| `TD-F038-I15` | **F037 三输入 × 4 端点仍为 422 `unreadable`** | F037 输入 ①（BM14 / 26 列超长字段）、输入 ②（sheet 尾损坏）、输入 ③（`[Content_Types].xml` 损坏）、缺 workbook 部件（`BE-01`）、`b""`、仅表头、OLE2 魔数、四类表头错误 | 逐例：状态码/`code`/`message`/`details` **逐字段**与基线语义相等；`unreadable` 类 4 端点全 422 且 `details == {"reason":"unreadable"}`；`empty_file` / `unsupported_format` / 表头类 reason **不被改写**；无 500 | A1、A7、B6、B7、B8、B9、T72、T112 |

#### TD-5.3 M 层（测量，详案见 TD-6）

| ID | 断言 |
| --- | --- |
| `TD-F038-M1` | **环境必录项**全部采集并写入 §2：`python -V`、`openpyxl.__version__`、`openpyxl.LXML`、`lxml.__version__`、`csv.field_size_limit()`、`resource.getrusage(RUSAGE_SELF).ru_maxrss`（仅报告）、`free -m` 可用内存、`nproc`、`ulimit -v`、HEAD/start_commit、DB 版本 |
| `TD-F038-M2` | **参考实现对照真实基线**：对 6 个小样例，`_baseline_records(data, fmt, max_rows=5000)` 与「`/tmp` 基线模块 `parse_records` + 基线裁剪/行数逻辑」结果**逐字段相等**（含异常类型与 `details`）；若 `/tmp` 基线缺失 → 该子断言 `NOT TESTED`（参考实现的独立性另由 `_baseline_records` 内含 `list(csv.reader(` / `list(worksheet.iter_rows(` 的**自证 grep** 兜底） |
| `TD-F038-M3` | **相对阈值**：S-W1 / S-W2 / S-W6a `fixed_peak ≤ baseline_peak / 8`；合法 5000 行 `fixed_peak ≤ 1.2 × baseline_peak`；全样例 `fixed_peak ≤ 64 × len(data) + 64 MiB`（绝对哨兵） |
| `TD-F038-M4` | **规模不敏感（xlsx 族）**：S-W1 与 S-W2 各取 N=5001 / 4N=20004（均 > max_rows），`fixed_peak(4N) ≤ 1.5 × fixed_peak(N) + 2 MiB`；CSV 族按 C-2 改由 M3 覆盖（登记 `TD-I-2`） |
| `TD-F038-M5` | **时间记录**：S-W1 / S-W2 / S-W6a 的 `perf_counter` 秒数（基线与完成态），断言 `fixed_time ≤ baseline_time`；**不设绝对上限**；并记录 `parse_records` 单次耗时便于回归比较 |
| `TD-F038-M6` | **可重复性**：每样例两次重复（同进程、固定顺序），报告两次值；阈值断言取**两次的较大值**（保守）；`gc.collect()` 在 `tracemalloc.start()` 之前与取峰值之后各一次 |

#### TD-5.4 S 层（静态守卫）

| ID | 断言 | 实现 |
| --- | --- | --- |
| `TD-F038-S1` | **零 diff**：`docs/api/`、`docs/database/`、`backend/alembic/`、`frontend/`、`pyproject.toml`、`Dockerfile`、模板与端点常量 | `git diff --stat 8e609ca -- <path>` 全为空；模板断言 `[c["name"] for c in templates_payload()["BARE_METAL"]["columns"]] == BM_HEADERS`、VM 10 列、`COLUMN_NAMES` 26；`Settings(_env_file=None)` 三常量 `5_242_880 / 5000 / 1000` |
| `TD-F038-S2` | **生产调用点必须带参**（R-9）：两处 `parse_records` 调用均带 `max_rows=` 与 `keep_cells=`，且 `keep_cells` 分别由 `_MAX_TEMPLATE_COLUMNS` 与 `len(COLUMN_NAMES)` 推导 | AST：`resource_import.parse_and_validate` 与 `resource_interface_ip_import.parse_and_validate` 各恰 1 处 `parse_records` 调用，`keywords` 集合含 `max_rows` / `keep_cells`，`ast.unparse` 文本含 `_MAX_TEMPLATE_COLUMNS` / `len(COLUMN_NAMES)`；`_MAX_TEMPLATE_COLUMNS == max(len(t.columns) for t in TEMPLATES) == 14` |
| `TD-F038-S3` | **异常面零扩散**（R-8、R-10）：无新增 `except`；`_PARSE_FAILURES` 长度仍 8；`OSError` 仍只在 `_parse_xlsx` 局部；无 `field_size_limit` / `strict=True` / `csv.QUOTE`；lxml 仍在 `pyproject.toml` 之外 | `len(resource_import._PARSE_FAILURES) == 8`；AST 统计 `except Exception` 仍为 2 处（`_close_workbook` / `write_import`）且无新增 `ExceptHandler`；`_invalid_file_on_parse_failure` 子句仍 `["AppError", "failures"]`；`grep -n "OSError"` 命中行号 ⊂ `_parse_xlsx` 行区间；`"lxml" not in pyproject.toml` 且 `app/**` 中仅 `resource_import.py` 命中 |
| `TD-F038-S4` | **无全量物化残留**（R-7）：`list(csv.reader` / `list(worksheet.iter_rows(` 零命中；`_collect_records` 循环内无 `break` / `return`（不得提前退出） | `grep -nE "list\(csv\.reader\|list\(worksheet\.iter_rows"` 无命中；AST：`_collect_records` 的 `For` 体内无 `Break`/`Return`；`parse_records` 的两参数调用兼容由 `U6` 覆盖 |
| `TD-F038-S5` | **L7″**：新增自有代码（`_is_blank_record` / `_Collected` / `_collect_records` / `_finalise`）内无 `try` / `except` / `open(` / `Path(` / `NamedTemporaryFile` / `logger.` / 文本构造（`_cell_text` 调用只允许在 `_finalise`） | AST 逐函数扫描；`_parse_xlsx` 的 `with` 块内仍只有对内存字节的第三方调用（沿用 F037 `S7` 手法，禁 `open`/`Path`/`TemporaryFile`） |
| `TD-F038-S6` | **改动面收口**：仅 `resource_import.py` 与 `resource_interface_ip_import.py` 有 diff | `git diff --stat 8e609ca -- backend/app` 恰 2 文件；`git status --porcelain --untracked-files=all` 仅新增测试模块与 `docs/features/F038/`；命令证据写入 §2 |

#### TD-5.5 R 层（回归执行项）

| ID | 套件 | 基线计数（本轮 `--collect-only`/F037 实测） | 判据 |
| --- | --- | --- | --- |
| `R1` | `tests/integration/test_f037_import_parse_errors.py` | **52** | **零修改**全绿（B8/S7）；若需改该文件才通过 ⇒ 判 **FAIL**（B8 失守） |
| `R2` | `test_imports.py` + `test_import_tester_acceptance.py` + `test_import_constraints.py` + `test_f023_resource_interface_ip_import.py` | 29 + 9 + 4 + 28 = **70** | 全绿；`test_validation_order_row_limit_before_header`、`test_permission_matrix`、`test_header_errors`、`test_reg02_route_inventory` 必须逐条通过（T28/T72 核心）；`test_perf03_near_max_rows_baseline` 允许按 F037 TE-N1 单独重跑（负载敏感） |
| `R3` | `test_f034_csv_text_carrier.py` + `test_f034_csv_text_carrier_scope.py` | 29 + 2 = **31** | 全绿（T107–T116，含 `test_td3_t114_field_boundaries`）；不改 corpus |
| `R4` | `test_f035_append_interface_ip_import.py` + `test_f035_append_scope.py` + `test_f035_tester_acceptance.py` + `test_f036_attribution.py` + `test_f036_tester_independent.py` | 20 + 2 + 16 + 5 + 5 = **48** | 全绿（T124） |
| `R5` | `test_import_performance.py` | **4**（本轮实测 `4 tests collected`） | 全绿；数值仅打印，**不新增/不修改阈值** |
| `R6` | `test_f030_test_harness.py` | **3** | 全绿（新模块不触 `access_scope` 符号 ⇒ 无需 `real_scope` mark） |

> 开跑前须**重测**采集数并以此轮为基线（`≥` 比较）；低于基线先核环境，不直接判实现 FAIL。

### TD-6 基线测量设计（M 层详案）

#### TD-6.1 基线获取（不修改工作区、不入库）

```bash
# 只读：从 start_commit 取出语义基线（写入 /tmp，不进入仓库）
mkdir -p /tmp/f038_baseline
git show 8e609ca:backend/app/services/resource_import.py > /tmp/f038_baseline/resource_import_8e609ca.py
git show 8e609ca:backend/app/services/resource_interface_ip_import.py > /tmp/f038_baseline/resource_interface_ip_import_8e609ca.py   # 仅用于 consumer 语义复核，不参与测量
```

测试内载入（**注意 `sys.modules` 注册，见 TD-3.4**）：

```python
BASELINE_PATH = os.environ.get("F038_BASELINE_MODULE", "/tmp/f038_baseline/resource_import_8e609ca.py")

def _load_baseline_module():
    spec = importlib.util.spec_from_file_location("f038_baseline_ri", BASELINE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # dataclass() 需要 sys.modules 命中
    spec.loader.exec_module(module)
    return module
```

约束（写入用例 docstring）：

1. 基线模块**只用于测量与参考实现对照**，不作为任何生产路径；`/tmp` 缺失时相关子断言标 `NOT TESTED`，**不得**改用「猜测值」。
2. 基线模块与 HEAD 同一模块名会互相污染 ⇒ 固定用 `f038_baseline_ri` 这个名字，且**只加载一次**（module 级 fixture）。
3. 该文件**永不提交**；`git status --porcelain` 必须保持只有测试模块与 `docs/features/F038/`（`S6` 校验）。

#### TD-6.2 `tracemalloc` 协议（固定顺序、可重复）

```python
def measure(fn):
    """返回 (result_or_exception, peak_bytes, seconds)。

    约定：
    * 被测 input bytes / records 在 start() **之前**构造 ⇒ 峰值只反映「解析与保留」新增分配；
    * gc.collect() 在 start() 之前做，避免上一次用例的循环垃圾计入；
    * 同进程固定顺序（S-W1 → S-W2 → S-W6a → 合法 5000 行），两次重复；
    * 报告两个值，阈值断言用两者**较大值**。
    """
    gc.collect()
    tracemalloc.start()
    start_current, _ = tracemalloc.get_traced_memory()   # 记录起点（≈0，用于报告）
    started = time.perf_counter()
    try:
        value, error = fn(), None
    except BaseException as exc:                          # 仅测试内捕获，用于比较异常等价
        value, error = None, exc
    seconds = time.perf_counter() - started
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()
    fixed_peak = peak - start_current
    return value, error, fixed_peak, seconds
```

**被测对象（同族可比）**

| 侧 | 调用 |
| --- | --- |
| 基线（BASELINE） | `baseline_module.parse_records(data, fmt)`（start_commit 语义：全量物化 + 全格 `_cell_text`） |
| 完成态（FIXED） | `resource_import.parse_records(data, fmt, max_rows=5000, keep_cells=14)`（**生产调用形态**） |
| 交叉参照（仅报告） | `resource.getrusage(RUSAGE_SELF).ru_maxrss`（KiB）——单调、含 lxml C 层分配，**不作断言** |

**已知偏置（必须在报告写明）**：`tracemalloc` 只统计 Python 层分配，**不计 lxml C 层**（ON-4）；因此 `LXML=True` 的结论**不外推**到无 lxml 镜像（`TD-I-6`）。

#### TD-6.3 阈值断言（相对倍数、规模不敏感、绝对哨兵）

> **repair round 1 勘误指针**：architecture **§14.2** 已重裁 CSV 族判据——本表 T-1b 与 T-2 的 `excess` 定义**作废**，改由 `T-1b′`（`work(4N) ≤ 1.5·work(N) + 2 MiB`）、`T-1c`（宽度不敏感，新增）、`T-2′`（`work(fixed) ≤ work(baseline)/8`，`work = max(peak − F(x), 0)`，`F` 为实测地板探针）取代；T-1（xlsx）/ T-3 / T-4 / T-5 / T-6 不变。下表保留为 TD-F038-1 原始设计记录，**执行口径以 §14.2 与 §2.7.2 为准**。

| # | 断言（全部以 `fixed_peak` 表示） | 适用样例 | 依据 / 备注 |
| --- | --- | --- | --- |
| T-1 | `fixed_peak(4N) ≤ 1.5 × fixed_peak(N) + 2 MiB` | **仅 xlsx 族** S-W1 / S-W2，N=5001、4N=20004 | C-2：CSV 族峰值地板是解码文本，此式在 CSV 上恒假，故限定 xlsx 族 |
| T-2 | `fixed_peak ≤ baseline_peak / 8` | S-W1、S-W2、S-W6a | 与基线相对，不硬编码 MB；S-W2 的基线取**降级规模**（见 TD-7），断言用等规模 N |
| T-3 | `fixed_peak ≤ 1.2 × baseline_peak` | 合法 5000 行（CSV） | 「无退化」上界；本设计小规模实测基线 2.8 MB ⇒ 预算 ≈ 3.4 MB，按 F038 保留量（5001×14 单元 + 归一化副本）估算约 1.5–2 MB，**有余量** |
| T-4 | `fixed_peak ≤ 64 × len(data) + 64 MiB` | 全部样例 | 绝对哨兵，只用于捕获灾难性回归；对 S-W2（6 KB 输入）等价于 `≤ 64 MiB` |
| T-5 | `fixed_time ≤ baseline_time`（记录秒数，不设绝对上限） | S-W1、S-W2、S-W6a | 时间是**线性于展开工作量**的残余特征（ON-5），只要求不退化 |
| T-6 | 报告性断言：`fixed_peak(S-W2, 20004) ≤ 8 MiB`（本例无解码文本、保留量截断） | S-W2 | 兜住「排空但不累积」的直接证据 |

**阈值失败处置（防「改阈值修绿」）**：T-1..T-5 任一失败 ⇒ 判 **FAIL / `RETURN TO IMPLEMENTATION`**（Owner: Backend），并把实测数值写入 §2；**不得**由 Tester 自行放宽倍数。若判定为**阈值本身设计不当**（如 C-2 类构造性缺陷），须以 `TD-I-*` 登记并交 Architect 裁定后按新口径重测，且旧结论作废。

#### TD-6.4 环境必录项（写入 §2 Environment 表）

`python -V`、`openpyxl.__version__`、`openpyxl.LXML`、`lxml.__version__`、`csv.field_size_limit()`、`free -m`（total / available）、`nproc`、`ulimit -v`、`ru_maxrss`（采值）、HEAD 与 start_commit 短哈希、`TEST_DATABASE_URL` 的 host/port/db（库名含 `test`）与 `show server_version`、pytest 版本、`F038_PROBE_SCALE` 取值（若使用降级规模）、每样例的 `len(data)` / 行数 / 列数 / 峰值 / 秒数（基线 vs 完成态，各两次）。

#### TD-6.5 规模控制与可外推理由（不得宣称实测原规模）

| 样例 | 本 TD 默认规模 | 基线侧规模 | 理由 |
| --- | --- | --- | --- |
| S-W1（702 列） | 10,001 数据行（dim `A1:ZZ10002`） | **同规模** | 小规模实测 16.4 KB/行 ⇒ 10001 行 ≈ **164 MB**，本机可安全执行（available 9,191 MB） |
| S-W2（16,384 列） | 10,001 数据行（dim `A1:XFD10002`） | **降级到 1,001 行**（≈263 MB） | 小规模实测 262.5 KB/行 ⇒ 原规模 **≈2.7 GB（ESTIMATE，未实测）**；基线侧降级后 T-2 用等规模（1,001 行）比较，完成态另跑 10,001 行证明规模不敏感（T-1） |
| S-W6a（CSV 宽表） | 4,000 行 × 651 列（2.6 MB） | **同规模** | 小规模实测 37.8 MB，安全 |
| 合法 5000 行 | 5,000 行（167,918 B） | **同规模** | 实测基线 2.8 MB / 26 ms |

若整轮测量耗时超出预算（建议 ≤ 5 分钟），允许把 `F038_PROBE_SCALE` 降到 `0.25`（行数 ×0.25，仍须 > 5000 后才触发超额语义的样例按 `max(5001, N)` 取下限），并**在报告中注明降级后规模**；此时结论只在「相对倍数/规模不敏感」意义上成立，**不得**写成「已在原规模实测」。

### TD-7 样例构造设计（S-W1 … S-W7）

所有样例**在内存中构造**（`io.BytesIO` + `zipfile` 重写 / `csv.writer`），**不落盘**（L7′ / F037 §15.10.7-6 边界）。

| ID | 构造要点 | 规模（默认） | 关键不变量（构造失效即 `BLOCKED`） | 期望响应 | 映射 |
| --- | --- | --- | --- | --- | --- |
| **S-W1 宽表** | `Workbook` 写 BM14 表头 + N 行（仅 A 列有值）→ `zipfile` 重写 `xl/worksheets/sheet1.xml` 的 `<dimension ref="…"/>` 为 `A1:ZZ{N+1}` | 10,001 数据行，702 宽 | `raw.startswith(b"PK\x03\x04")`；`0 < len(raw) < 5_242_880`（实测 100 行时 8,649 B）；裸 `load_workbook(read_only=True).worksheets[0].max_column == 702`（**已实测成立**） | 413 `IMPORT_ROW_LIMIT_EXCEEDED` | A2、A3、B2 |
| **S-W2 大使用区域** | 正常 workbook 基础上把 `sheetData` 补 9,999 个空 `<row r="k"/>` + `dimension` 改 `A1:XFD{N+1}` | 10,001 数据行，16,384 宽（文件 ~5.5 KB） | 同 S-W1；`max_column == 16384`；`iter_rows` 行数 == N+1 且空行为 `(None,)*16384`（**已实测**：200 行 / 5,518 B / 18 ms） | 413 | A2、A3、B3、B2 |
| **S-W3 尾部空行 CSV** | 表头 + R 行合法 + `"\n" * 100_000` | R=3，100,222 B | 裸 `csv.reader` 末尾产出 `[]` 记录（**已实测** `[..., [], [], [], [], []]`）；总字节 < 5 MiB | 200 / 201，`total_rows == 3` | A4、B3、T113 |
| **S-W4 5001 行 + 尾部行级错误** | 5001 合法行 + 末行 `role="NOT_A_ROLE"`（变体：末行 200 列） | 167,988 B | 行级错误行**必须是数据行**（非空） | **413**（不是 422） | A3、B6 |
| **S-W5 5001 行 + 尾部解析损坏** | CSV：末行单字段 131,073 字符（`csv.field_size_limit()=131072`）；xlsx 变体：`</worksheet>` → `</workshet>` + 5001 行 | 299,051 B | `131_072 < 字段长度`；总字节 < 5 MiB；**基线实测** → `ImportInvalidFile{unreadable}` | **422 `unreadable`（ON-1，不得写 413）** | A6、B6、B8、ON-1 |
| **S-W6 宽表 CSV** | a：表头 651 列 + 4,000 行 651 个空字段；b：表头 520 列 + 5,001 行 | a ≈2.6 MB；b ≈2.6 MB | `len(raw) < 5_242_880`；a 行数 ≤ 5000（走表头/列类 422）、b 行数 > 5000（走 413） | a：422 `unknown_columns`；b：413 | A7、B7、N1 |
| **S-W7 中间大段空行** | 表头 + 1 合法行 + 1,000 空行 + 1 行 `role` 非法 | ≈100 KB | 空行为空行（`[]`）而非含空格行 | 200（`total_rows=1002`、错误行号 1003）/ 写入 422 | A4、R-1、R-4 |

#### TD-7.3 规模校准实测（小规模，仅用于校准与可行性，**不是原规模实测**）

| 探针 | 构造 | 实测输出 |
| --- | --- | --- |
| 宽表展开（702 宽） | `dimension A1:ZZ101`，100 数据行，8,649 B | `max_row=101`、`max_column=702`；基线 `parse_records` 峰值 **1.68 MB**（16.4 KB/行）、32 ms ⇒ 10,001 行外推 ≈ **164 MB** |
| 大使用区域（16,384 宽） | `dimension A1:XFD401`，400 数据行，18,884 B | 基线峰值 **107.52 MB**（262.5 KB/行）、465 ms ⇒ 10,001 行外推 ≈ **2.7 GB（ESTIMATE）** |
| 大使用区域（空 `<row/>`，合成） | 200 行 / 16,384 宽 / 5,518 B | `max_row=201`、`max_column=16384`；裸 `iter_rows` 200 行耗时 **18 ms**；行内容 `('NoneType',)` |
| 合法 5000 行 CSV | 167,918 B | 基线峰值 **2.8 MB**、26 ms；`rows=5001`（含表头） |
| S-W3 | 100,222 B | 基线峰值 **12.9 MB**、171 ms；`rows=100,004`（含表头，尾部空行仍被物化） |
| S-W6（4000×500，1 字符单元） | 4,002,390 B | 基线峰值 **37.8 MB**、222 ms（1 字符 str 被 CPython 驻留 ⇒ 每单元约 8 B 槽位；T-2 的 8× 余量约为 1.2–1.5×，**测试时须实测确认**，见 `TD-I-3`） |

> 上述数值来自 `/tmp/f038_probe/*.py` 的一次性探测，**只用于规模校准与阈值合理性预检**；正式证据必须由 `TD-F038-M*` 在 TEST 阶段重新产生。

### TD-8 等价性设计（A1 的实现方式）

#### TD-8.1 参考实现 `_baseline_records`（测试内、start_commit 语义）

```python
def _baseline_records(data: bytes, fmt: str, *, max_rows: int | None) -> list[list[str]]:
    """start_commit（8e609ca）语义的 records：全量物化 → 裁剪尾部空行 → 行数上限。

    与生产实现的差异**必须**保留（否则失去独立证据意义）：
    * 全量物化：`list(csv.reader(...))` / `list(worksheet.iter_rows(...))`（测试代码内允许出现这两个字符串）；
    * 对**每个**单元格调用 `_cell_text`（生产实现改为只归一化保留记录）；
    * 不做 keep_cells 裁剪；表头与数据行都保持原宽度。
    复用的未改动共享件（由 S3 证明零 diff）：`resource_import._cell_text`、
    `resource_import._invalid_file_on_parse_failure`、PK 闸门与 `empty_file` 判定顺序。
    """
    if not data:
        raise ImportInvalidFile("empty_file")
    if fmt == "csv":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportInvalidFile("unreadable") from exc
        with resource_import._invalid_file_on_parse_failure("csv", len(data)):
            raw = list(csv.reader(io.StringIO(text, newline="")))
    else:
        raw = _baseline_xlsx_rows(data)          # PK 闸门 + load_workbook(read_only,data_only) + worksheets 检查 + iter_rows
    records = [[resource_import._cell_text(cell) for cell in row] for row in raw]
    if not records:
        raise ImportInvalidFile("empty_file")
    data_records = list(records[1:])
    while data_records and all(cell == "" for cell in data_records[-1]):   # 基线 :887–888
        data_records.pop()
    if max_rows is not None and len(data_records) > max_rows:              # 基线 :891
        raise ImportRowLimitExceeded(max_rows)
    return [records[0], *data_records]
```

**独立性自证（防「参考实现照抄被测实现」）**：`TD-F038-U4`/`M2` 断言参考实现源码内含 `list(csv.reader(` 与 `list(worksheet.iter_rows(`、**不含**`_collect_records` / `_finalise` / `keep_cells`；并在 `M2` 用 `/tmp` 真实基线模块做一次黄金对照。

#### TD-8.2 差分机制（单点 monkeypatch 覆盖 consumer 改动）

F038 把「尾部空行裁剪 + 行数上限」从 consumer 上移进 `parse_records`，因此只比 records 不够。做法：让**被测 consumer 保持不变**，只替换它的输入来源：

```python
# 基线语义路径：patched parse 已内含基线裁剪 + 基线行数上限（同一相对顺序）
monkeypatch.setattr(
    resource_import, "parse_records",
    lambda data, fmt, **kwargs: _baseline_records(data, fmt, max_rows=5000),
)
resp_baseline = client.post(path, files=..., data={"format": fmt})

monkeypatch.undo()          # 真实路径（生产 parse_records，带 max_rows/keep_cells）
resp_fixed = client.post(path, files=..., data={"format": fmt})

assert (resp_fixed.status_code, resp_fixed.json()) == (resp_baseline.status_code, resp_baseline.json())
```

为什么这能等价覆盖两份 consumer：F023 的 `parse_and_validate` 通过 `resource_import.parse_records(...)` 调用（模块属性查找），patch 对两者同时生效；patched 版本在**返回前**完成基线的「裁剪 → 行数 413」，其后 consumer 的表头检查 / `_resolve_template` / 逐行校验与基线完全相同；数据行宽度差异（基线全宽 vs 完成态 14/26）由 C2/C5 证明不可观察，并由 `TD-F038-I14` 的毒值探针独立证明。

**已知覆盖缺口（如实登记）**：基线语义路径的 parse 由参考实现承担，因此**恢复基线代码库**这一操作未被差分覆盖；该风险由 `M2`（参考实现 vs 真实 `/tmp` 基线模块黄金对照）+ `R1`（F037 52 项零修改）+ `S3`（异常面零 diff）共同兜住。

#### TD-8.3 四端点 × 固定输入矩阵（深比较清单）

端点：`/api/v1/imports/resources/validate`、`/api/v1/imports/resources`、`/api/v1/imports/resource-interfaces-ips/validate`、`/api/v1/imports/resource-interfaces-ips`（表头按端点取 BM14 / 26 列）。

| # | 输入 | 期望（两侧一致为唯一判据） |
| --- | --- | --- |
| 1 | F037 输入①（BM14 超长字段，131,229 B） | 422 `IMPORT_INVALID_FILE{unreadable}` |
| 2 | F037 输入①（26 列，131,336 B） | 422 `unreadable` |
| 3 | F037 输入②（sheet 尾损坏 xlsx） | 422 `unreadable` |
| 4 | F037 输入③（`[Content_Types].xml` 损坏） | 422 `unreadable` |
| 5 | 缺 workbook 部件（BE-01） | 422 `unreadable` |
| 6 | `> 5,242,880 B` | 413 `IMPORT_FILE_TOO_LARGE{limit_bytes:5242880}` |
| 7 | 5001 合法行（S-W4 基础形态） | 413 `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows:5000}` |
| 8 | `b""` / 仅表头 | 422 `empty_file` |
| 9 | OLE2 魔数（`format="xlsx"`） | 422 `unsupported_format` |
| 10 | 四类表头错误（`header_missing` / `missing_columns` / `unknown_columns` / `column_order`） | 422 对应 `reason` + 同 `details` 明细 |
| 11 | 行级错误批次（非法枚举 / 非法整数 / 文件内重复 → `related_row`） | 200 + `errors[]` 四键逐元素相等 / 写入 422 `IMPORT_VALIDATION_FAILED` |
| 12 | 正常成功批次（小行数，Cluster/Network 预备） | 200 计数相等 / 写入 201 计数相等 |
| 13 | S-W1、S-W2、S-W3、S-W4、S-W5、S-W6a、S-W6b、S-W7 | 见 TD-7；两侧状态码 + `json()` 深等 |

深比较实现：`assert resp.json() == baseline.json()`（dict 深等，键序无关）+ `assert resp.status_code == baseline.status_code`；对 200/201 额外比较键集合 `set(body) == set(baseline_body)`；对 422/413 额外比较 `set(body["error"]["details"])`。

### TD-9 不可验证项与降级口径

| 项 | 标注 | 理由 / 替代证据 |
| --- | --- | --- |
| 真实内存耗尽（OS 级 OOM / 进程被杀） | **NOT TESTED** | 不在宿主上制造 OOM；S-W2 原规模基线（估算 2.7 GB）不执行，只以**相对倍数 + 规模不敏感**证明有界（product N8 明确「不声称已测得生产内存问题」） |
| S-W2 **原规模基线**峰值 | **NOT TESTED（ESTIMATE）** | 见 TD-6.5；报告须把 2.7 GB 标为外推值 |
| 无 lxml 环境（`openpyxl.LXML=False`，生产镜像形态） | **NOT TESTED** | 本机 `LXML=True`；峰值与异常类均可能不同（ON-4）⇒ 结论不外推，登记 `TD-I-6` |
| 5000 行**写入**端点的等价性与耗时 | **NOT TESTED** | F037 实测该路径 300 s+（TE-6.6），成本不成比例；解析侧等价已由 `I8`（validate）与 `R5`（既有性能用例）覆盖；错误方向（拒绝路径）已由 `I1/I2/I4/I5/I6` 全 4 端点覆盖 |
| `tracemalloc` 统计下 lxml C 层分配 | **NOT TESTED（只报告）** | 以 `ru_maxrss` 交叉参照，不作断言 |
| 时间上界 | **NOT_REQUIRED** | ON-5：本 Feature 只承诺**空间**有界；时间仍线性于展开工作量，仅要求不退化（T-5） |
| 前端 / 界面 | **NOT_REQUIRED** | `layers.frontend=false`；`S1` 守 `frontend/` 零 diff；T116 的前端行为归 F034 `R3` |
| 数据库约束 / Migration | **NOT_REQUIRED** | `layers.database=false`；解析早于任何 `begin_nested()`；`I9` 以 7 表计数复核「拒绝路径零 SQL 效果」 |
| 整体验收（§31–33 跨功能） | **NOT_REQUIRED（本 Feature）** | 归 plan `acceptance` 整体回归（F045）；**不得**用本 Feature 局部 PASS 拼成整体 PASS |
| `S1`/`S6` 的 pytest 化 | **NOT_REQUIRED** | 依赖 Git 状态，以 §2 报告的命令输出为证据（其余 S 项均有 pytest 守卫） |

**降级规则**：任一必需输入缺失（`TEST_DATABASE_URL`、`/tmp` 基线模块、内存余量不足）⇒ 受影响用例标 `NOT TESTED` 并写明已尝试命令，**不得**用 SQLite / Mock / 猜测值代替；结论据此降级为 `PARTIAL TEST ONLY`。

### TD-10 数据完整性映射（data-integrity 口径，复核而非新增）

| 规则依据 | 作用域 / 入口 | 数据库保证 | 业务层保证 | 本 Feature 影响 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §24-2 / T27 / T123 整批原子、拒绝零残留 | 4 端点写入 | 单事务 + 逐行 SAVEPOINT（**不变**） | 解析失败发生在任何 `begin_nested()` 之前 | 无（解析阶段内部改造） | `I9`、`I1`–`I7` 的零写入断言 |
| §22 Audit 同事务 | 4 端点写入 | `audit_logs` append-only | 拒绝路径不写 Audit | 无 | `I9`（`audit_logs` 不变 = Activity 不变） |
| §24.5 / T107–T116 双载体等价 | CSV 文件/文本载体 | — | 载体在字节入口之后汇合 | 无 | `I13`、`R3` |
| §7 部分唯一索引等 | 4 端点 | 三条部分唯一索引（**不变**） | 逐行校验（**不变**） | 无 | `R2`（既有约束用例） |
| 1-based 行号 / `RowError` 形状 | 4 端点 | — | 行号仍建立在裁剪后列表索引上 | **有**（裁剪/上限上移，行号来源不变） | `I7`、`I3`、`I12`、`U2` |
| F014/F023 原因保真 | 4 端点 | — | `except AppError: raise` 先于白名单 | 无（作用域未变） | `I15`、`S3` |

**Database：`NOT_REQUIRED`** —— 零 DDL、零事务边界变化、零 Migration；上表为不变量复核，不主张「新增约束已验证」。

### TD-11 登记项（`TD-I-*`，不阻塞本阶段结论）

| ID | 内容 | Owner | 是否必须修复 |
| --- | --- | --- | --- |
| `TD-I-1` | **U4 探针形态修正**（C-1）：architecture §8.4/§9.3 建议的 `list` 子类 `__getitem__` 探针会被 `_validate_record` / `_cells_for` 的 `list(cells)` 拷贝绕过。本 TD 改为 **毒值探针 + AST 守卫** 双证。语义结论不变（裁剪安全），只是取证方式必须更正 | Tester（已在本 TD 固定）/ Architect 知会 | 否（已按可执行方式落稿） |
| `TD-I-2` | **阈值 T-1 的适用范围收窄**（C-2）：`1.5×peak(N) + 2 MiB` 仅对 xlsx 族成立；CSV 峰值地板是不可避免的解码文本（≤5 MiB）。建议 Architect 在定稿复核时确认该表述，避免 TEST 阶段被误判为「阈值被放宽」 | Architect | 否（口径登记；M3 仍以 T-2/T-3/T-4 覆盖 CSV） |
| `TD-I-3` | **S-W6 的 8× 余量偏薄**：1 字符单元格被 CPython 驻留，实测基线仅 37.8 MB（2.6 MB 输入），`peak ≤ baseline/8` 的实际余量约 1.2–1.5×。TEST 时须实测确认；若实测余量不足 2×，登记实测值交 Architect（**不得**自行改倍数） | Tester → Architect（如触发） | 否（待实测） |
| `TD-I-4` | **参考实现的覆盖缺口**（C-3）：等价性由「测试内参考实现 + 未改动共享件」承担，无法覆盖「恢复基线代码」本身；由 `M2` + `R1` + `S3` 兜住。请 Review 核对措辞，不把差分 PASS 表述为「已在两个代码库之间做过对照运行」 | Tester / Reviewer | 否 |
| `TD-I-5` | `_is_blank_record` 的等价性只对**解析器可产出类型**成立（CSV `str`；xlsx `str/bool/int/float/datetime/date/time/timedelta/None`）。全类型矩阵中非解析器类型（`Decimal`、`bytes`、`nan`）仅作**额外**守卫，不作为业务口径 | Tester | 否 |
| `TD-I-6` | 无 lxml 镜像（生产形态）的峰值与异常类差异未实测（ON-4）；报告须记 `openpyxl.LXML` 且结论不外推 | 协调器 / Architect | 否 |
| `TD-I-7` | S-W2 原规模基线（≈2.7 GB）与 5000 行写入端点等价性**不执行**（`NOT TESTED`）；若 Review 要求，须由协调器提供更大内存/专用环境后另立执行项 | 协调器 | 否（本轮明确不测） |

### TD-12 结论

**`TEST DESIGN READY`**

- **映射完整**：product A1–A14 / B1–B13 / S1–S8 全部落到 **U1–U6（6）· I1–I15（15）· M1–M6（6）· S1–S6（6）+ R1–R6（6）**，每条给出层级、前置夹具、构造方式、断言要点与 T 条目（T28 / T72 / T107–T116 / T124 / T126）；architecture §9.3 的 U1–U5 / I1–I10 / M1 / S1–S5 逐条展开并补齐缺口。
- **基线测量可执行且不污染工作区**：`git show 8e609ca:… > /tmp` + `importlib`（**已实测载入成功**，并记录 `sys.modules` 注册这一必需步骤）；`tracemalloc` 协议固定（`gc.collect()` / 输入预构造 / 同进程固定顺序 / 两次重复 / 取较大值）；阈值由**相对倍数 + 规模不敏感 + 绝对哨兵**组成，禁绝对 MB 硬编码；环境必录项清单已固定（§2 必须逐项填实测值）。附带 `ru_maxrss` 交叉参照并明确不作断言、不计 lxml C 层。
- **样例构造经小规模实测校准**：702 宽 16.4 KB/行、16,384 宽 262.5 KB/行、空 `<row/>` 合成 sheet（5,518 B → 200×16,384）均验证可构造且可展开；据此确认 **S-W2 原规模基线 ≈2.7 GB 必须降级**（登记为 ESTIMATE，不得宣称实测），S-W1 可按原规模执行。
- **ON-1 已独立实证**：用 start_commit 语义实测 **S-W4 → 413 `IMPORT_ROW_LIMIT_EXCEEDED`**、**S-W5 → 422 `ImportInvalidFile{unreadable}`**；S-W5 的期望固定为 422，写成 413 即为错误预期。
- **等价性方案可执行且能覆盖 consumer 改动**：`_baseline_records`（start_commit 语义、含基线的裁剪+行数顺序）+ 单点 `parse_records` monkeypatch 差分 + 四端点固定输入矩阵（13 类输入）深比较；裁剪安全性由**毒值探针**（证明 consumer 不读第 ≥ W 列，含错误路径，带负向对照）+ AST 守卫双证，替代被 `list()` 拷贝绕过的下标探针（`TD-I-1`）。
- **不可验证项已明示**：真实 OOM、S-W2 原规模基线、无 lxml 环境、5000 行写入端点等价性、时间上界、前端 / 数据库 / 整体验收；降级规则与「不得以 Mock/SQLite/猜测值替代」写死。
- **本阶段未执行任何测试、构建或 Git 写操作**；本 TD 只写 `docs/features/F038/test-report.md`。`TEST DESIGN READY` **不是测试通过**、**不批准实现**、**不放行合并**；实现完成后须按本 TD 实际执行并给出 §2 TEST EXECUTION 结论（`READY FOR REVIEW` / `RETURN TO IMPLEMENTATION` / `TEST BLOCKED` / `PARTIAL TEST ONLY`）。

**GIT: NONE**

---

## 2. TEST EXECUTION（TE-F038-1 / TE-F038-2，v2，2026-10-29）

### 2.1 Task / Status / Basis

- **Task**：F038「导入解压 / 解析内存边界加固（R05）」——FEATURE / P1 / M29；阶段 **TEST（独立执行）**；实现基线 `e954537`（实现提交 `3289d39`），语义基线 `8e609ca`；分支 `feature/F038-import-parse-bounds`。
- **Status**：**`READY FOR REVIEW`**（TE-F038-2，判定见 §2.12）。摘要：按 architecture **§14.5 最小复测集与改动白名单**升级 M 层后，定点复测 `-k "m3a or m4b or m4d or m4e or m6"` = **8 passed**，整模块 = **76 passed / 0 failed**；`T-1b′` / `T-1c` / `T-2′`（含新增 S-W6b / S-W6c）与守卫 G-A1 / G-A2 / G-A3 / G-B 全部 PASS；`test_f037_import_parse_errors.py` **零修改 52 passed**；R2–R6 全绿。**生产代码零 diff**（`git diff --stat -- backend/app/services/` 空）。
- **TE-F038-1（v1）历史结论**：`BLOCKED`，3 项 §13.2 CSV 族阈值 FAIL（`DEF-01` / `DEF-02`）。两项缺陷已由 `architecture.md` **§14（repair round 1，TD-I-9 / TD-I-10）** 判定为**阈值口径缺陷、实现侧无缺陷**并修正口径；**实现与契约均未改动**，旧判定作废范围见 §2.12。
- **写入范围（仅本角色）**：① `backend/tests/integration/test_f038_parse_bounds.py`（**仅 §14.5 白名单**：`_SAMPLES` 新增 `S-W6b`/`S-W6c`、新增 `floor_bytes`/`_floor_probe_peak`/`_floor_probe_repeats`/`_floor_probe_once`/`excess(..., floor=)`/`_work`、升级 `m4d`、改期望 `m3a`、重写 `m4b`、新增 `m4e`、改发布列 `m6`）；② 本文件（版本记录 + §2 更新）。**未**改生产代码、`test_f037_import_parse_errors.py`、契约、计划、`CAP_*`、`_measure` 协议、U/I/S/R 任何用例与断言；**未**执行任何 Git 写操作（只读命令见 §2.13）。
- **Basis**：`docs/features/F038/architecture.md` v1 + §13 + **§14（权威，尤其 §14.2 符号定义与「不能证明什么」六条、§14.3 `floor_bytes`/`excess(floor=)`/G-A1/G-A2/G-A3/G-B、§14.4 不主张项、§14.5 白名单、§14.6 TD-I-9/TD-I-10 关闭条件）**；`docs/features/F038/product.md` v1（A1–A14 / B1–B13）；`implementation.md`（BACKEND COMPLETE）；本文件 §1 TD-F038-1；`docs/api/F014.md` v1 / `F023.md` v2（零 diff）。

### 2.2 Environment（M1 实测，`test_td_f038_m1_environment_record`）

| 项 | 实测值 | 命令 / 来源 |
| --- | --- | --- |
| Python | `3.12.7` | `python3 -V` |
| platform | `linux` | `sys.platform` |
| `openpyxl.__version__` | `3.1.5` | 模块属性 |
| **`openpyxl.LXML`** | **`True`** | 模块属性（⇒ 结论**不外推**到无 lxml 镜像，ON-4 / `TD-I-6`） |
| `lxml.__version__` | `5.2.1` | 模块属性 |
| `csv.field_size_limit()` | `131072` | 模块函数 |
| pytest | `7.4.4` | `pytest.__version__` |
| HEAD / start_commit | `e954537` / `8e609ca` | `git rev-parse --short HEAD` / `git show 8e609ca:…` |
| 基线模块 | `/tmp/f038_baseline/resource_import_8e609ca.py`（1061 行，**不入库**） | `git show 8e609ca:backend/app/services/resource_import.py > …` |
| `TEST_DATABASE_URL` | `postgresql+psycopg://csm@127.0.0.1:55432/csm_f037_test`（库名含 `test` ✓、`DATABASE_URL` 未设 ✓ ⇒ DB-D10 双守卫通过） | conftest `_require_test_database_url` |
| PG 版本 / 容器 | `16.15` / `csm-f037-pg`（`postgres:16-alpine`，`0.0.0.0:55432->5432`） | `docker exec … psql -tAc "show server_version"` |
| 物理内存 / CPU / `ulimit -v` | `total 15634 MB / available ≈ 9242 MB`；`nproc=16`；`unlimited` | `free -m` / `nproc` / `ulimit -v` |
| `ru_maxrss`（仅报告，含 lxml C 层） | `925908 KiB` | `resource.getrusage(RUSAGE_SELF)`（M6） |

### 2.3 TD-I-8 勘误落稿（S-W2 期望 = 422 `unknown_columns`）

**依据**：`docs/features/F038/architecture.md` §13.4（CONTRACT 签核）。**作废**本文件 §1 中把 S-W2 写成 413 的表述：

| 作废位置 | 旧表述 | 现行有效表述（本 §2 起） |
| --- | --- | --- |
| §1 TD-4「A3 行」与 §1 TD-5.2 `TD-F038-I2` | 「4 端点差分相等 + **413**」 | **422 `IMPORT_INVALID_FILE{reason:"unknown_columns"}`**（差分相等仍成立） |
| §1 TD-7 `S-W2` 期望列 | 「413」 | 同上；**不得判 413** |
| §1 TD-6.5 / TD-9「S-W2 原规模 ≈2.7 GB」 | 说明不变 | 仍为 **`ESTIMATE`（外推，未实测）** |

**机理**（实测确认）：`dimension A1:XFD{N+1}` 使 openpyxl 把**每一行（含表头行）**补齐到 16,384 格；S-W2 的数据行全为 `<row/>` ⇒ 全属尾部空行被裁掉 ⇒ `total_rows = 0`，**不触发行数 413**；表头 = 14 个真实列名 + 16,370 个空串 ⇒ `unknown_columns` 命中 ⇒ 422。

**数值勘误（文档级）**：§13.4 写的「16,350 个 `None`」与算术不一致，实测 **16,370 = 16,384 − 14**。用例以**构造值**断言（`len(unknown) == 16_384 - len(BM_HEADERS)`，且 `set(unknown) == {""}`），不硬编码任何数字；26 列端点同族（`unknown_columns` 16,370 + `missing_columns` 12，见 `test_td_f038_i2`）。**期望类（422 `unknown_columns`）不变**，仅修正 §13.4 的计数笔误。

### 2.4 验收映射（A1–A14 / B1–B13 → 实测用例 → 结论）

| 验收 | 用例 | 结果 |
| --- | --- | --- |
| A1 同字节逐字一致 | `I1`–`I8`、`I13`、`I15`、`I15b`、`M2`（参考实现 vs `/tmp` 基线黄金对照，7 样例 × `max_rows∈{5000,None}`） | **PASS** |
| A2 峰值有界（相对倍数） | `T-1` PASS（S-W1 1.141→1.868 ≤ 3.711 MiB；S-W2 1.810→1.970 ≤ 4.715 MiB）、**`T-2′`（§14.2）全部 PASS**：S-W1 **11.441×**、S-W2 **155.744×**、S-W6a-4000 **5312.409×**、S-W6b **37.483×**；**`T-1b′` PASS**（0.006 ≤ 2.009 MiB）、**`T-1c` PASS**（1.057 ≤ 3.579 MiB）、`T-3` PASS、`T-4` PASS、`T-6` 报告项 1.970 MiB；守卫 G-A1/G-A2/G-B 全 PASS | **PASS**（TE-F038-2；旧 `T-1b`/`T-2`@S-W6a 的 FAIL 已作废，口径由 §14 重裁） |
| A3 超行数不累积 | `I1`（413）、`I4`（413×2）、`I6b`（413）、`U3`（排空性）、`U5`（保留上界 + 排空 10 万条） | **PASS** |
| A4 尾部空行 / BOM / CRLF | `U1`（21 类型）、`U2`、`I3`（10 万尾部空行 → `total_rows=3`）、`I7`（1000 中间空行 → 行号不位移） | **PASS** |
| A5 上限与 1000 预览 | `I8`（5000 行 200）、`I11`（413 字节 / 413 行数）、`I12`（1100 错误 → `errors` 恰 1000、`errors_truncated=true`、`importable_rows=0`） | **PASS** |
| A6 校验顺序对角 | `I11`（a 413 字节 → b 413 行数 → c 行数先于表头 → d `import_max_rows=1` 仍 413）、`I4`/`I5` 配对（行级错误 413 / 解析异常 422）、`U3` | **PASS** |
| A7 六类 reason 不变；宽表走列类 | `I6a`（651 列宽表 CSV → `unknown_columns`，637 项全空串）、`I15`（四类表头 + `empty_file` + `unsupported_format`） | **PASS** |
| A8 双载体等价 / 粘贴不留痕 | `I13`（S-W3 只读两载体 ×2 端点；S-W6a ×4 端点；重复提交一致）、`I9`（响应体内容保护） | **PASS** |
| A9 零写入 / 零 Audit | `I9`（S-W1/S-W2/S-W4/S-W5/S-W6a × 4 端点后 7 表计数逐表不变）、`I7`/`I12`（写入 422 后计数不变） | **PASS** |
| A10 401 / 403 先行 | `I10`（S-W1/S-W2 字节 × 未登录 = 401 `AUTH_REQUIRED`）、`I10b`（VIEWER = 403 `FORBIDDEN{reason:"permission"}`） | **PASS** |
| A11 F037 52 项 + F034–F036 无回归 | `R1`–`R6`（52 / 70 / 31 / 48 / 4 / 3 全绿） | **PASS** |
| A12 基准证据入库 | `M1`–`M6`（环境、两份重复值、公式与两侧数值、`/tmp` 基线来源、可重复命令） | **PASS** |
| A13 零变更守卫 | `S1`（`docs/api`、`docs/database`、`backend/alembic`、`frontend`、`pyproject.toml`、`Dockerfile`、F037 测试 = 零 diff；模板 BM 14 / VM 10 / 26 列；三常量 5,242,880 / 5000 / 1000）、`S3`（`_PARSE_FAILURES` 8、`except Exception` 仍 2、无 `field_size_limit`/`strict=True`/`csv.QUOTE`、`lxml` 未进 `pyproject.toml`） | **PASS** |
| A14 内容保护 | `S5`（L7″ AST：新增 4 函数无 `try`/`except`/`open(`/`Path(`/`logger.`；`_cell_text` 只在 `_finalise`）、`I9`（响应体 0 命中 marker / `Traceback` / `<worksheet` / `.py` / 首列簇码） | **PASS** |
| B1 5 MiB / 413 | `I11a`（`IMPORT_FILE_TOO_LARGE{limit_bytes:5242880}`，4 端点） | **PASS** |
| B2 5000 行 / 413 | `I1`、`I4`、`I6b`、`I11b/c/d`、`I8`（5000 不触发） | **PASS** |
| B3 尾部空行 / 行号 | `I3`（`total_rows=3`）、`I7`（3 空行 → 末行行号仍 6；1000 空行 → 首错行号 3）、`U1`/`U2` | **PASS** |
| B4 `errors_truncated` / 预览 / `importable_rows` | `I7`（3001 错误 → 1000 条 + `true` + `importable=1`）、`I12`（1100 → 1000 条 + `true` + 0）、`I8`（`false` + `[]`） | **PASS** |
| B5 1-based 行号 / `field` / `related_row` | `I12`（`set(error) == {row,field,reason,related_row}`、`field=="cluster"`、行号 2..1001）、`I7` | **PASS** |
| B6 校验顺序 | `I11`（4 个对角）、`I4`/`I5`（ON-1 配对）、`U3`（`_finalise` spy 计数 0） | **PASS** |
| B7 六类 reason 优先 | `I6a`、`I15`、`I15b`（`details == {"reason":"unreadable"}` 逐字节） | **PASS** |
| B8 F037 收敛仍生效 | `I5`（csv/xlsx 尾部解析异常 → 422）、`I15`/`I15b`（输入①②③ + 缺 workbook 部件 + OLE2 + `b""` + 仅表头）、`R1` 52 项零修改全绿 | **PASS** |
| B9 双载体等价 | `I13` | **PASS** |
| B10 零写入 / 零 Audit | `I9`、`I7`、`I12`（7 表：`clusters/resources/bare_metal_details/virtual_machine_details/interfaces/ip_addresses/audit_logs`） | **PASS** |
| B11 `IMPORT` 权限 / 401 先于 403 | `I10`、`I10b`（有界解析未提前消费请求体：大样例同样 401/403，无 413/422/500） | **PASS** |
| B12 模板 / 端点 / 码 / reason 零变更 | `S1`、`S2`、`U6`（两参数兼容、表头整行保留） | **PASS** |
| B13 内容保护 | `I9`、`S5` | **PASS** |
| S1 解析阶段工作量有界 | 同 A2 | **PASS**（TE-F038-2，同 A2） |
| S2/S4/S5/S6/S8 | 同 A1 / A8 / A5+A6 / B10 | **PASS** |
| S3（product §2.1）超行数仍 413 | `I4`（行级错误/超宽行 → 413）+ `I5`（解析器异常 → 422，§13.3 errata 口径） | **PASS** |
| S7 F037 52 项 | `R1` | **PASS** |

### 2.5 U 层（`pytest tests/integration/test_f038_parse_bounds.py -q`；TE-F038-2 整模块 **76 passed / 0 failed**）

> U 层用例与断言在 TE-F038-2 **零变更**（§14.5 白名单不含 U/I/S/R），故下表结论沿用 TE-F038-1 并已在本轮整模块重跑中全部重执行通过。

| 用例 | 断言要点（实测） | 结果 |
| --- | --- | --- |
| `U1` ×21（含 `parametrize` 20 + 真实解析产物 1） | `_is_blank_record(row) is all(_cell_text(c)=="" …)`：`()`/`[]`/`("",)`/`(None,)`/`(None,)*16384` → True；`(" ",)`/`(0,)`/`(0.0,)`/`(-0.0,)`/`(True,)`/`(False,)`/`Decimal("0")`/`datetime`/`date`/`time`/`timedelta(0)`/`nan`/`("0",)`/`(b"",)` → False 且两侧一致；CSV 空记录 `[]`、xlsx `(None,)*16384` 实测为真 | **PASS** |
| `U2` | `<cap`/`=cap`（`overflow False`，`_finalise` 413）/`>cap`（`overflow True`、`rows==[]`）/中间空行补 `()`→`[]`（位置保持）/尾部 3 空行丢弃（长度不位移）/仅表头/表头 `None`→`[]`/`max_rows=None`/`keep_cells=None`/100 列宽行 → 数据行 14 格 + 表头 100 格 | **PASS** |
| `U3` | 生成器第 3 条抛 `csv.Error`（`consumed==3`，非 `ImportRowLimitExceeded`）；真实 S-W5 路径 `_finalise` **spy 计数 0**、异常 `ImportInvalidFile{unreadable}` 且 `__cause__` 为 `csv.Error`；5003 条（1 表头 + 5002 数据）= 全量消费 `5003` 且 `overflow True` | **PASS** |
| `U4`（静态） | `_validate_record` / `_cells_for` 对 `padded`/`cells` 的下标**只有** `index`，来源为 `enumerate(template.columns)` / `enumerate(COLUMNS)`，无 `[-1]`/`max(`/负索引；`_is_blank_record` 仅在 `_collect_records` 循环内且早于 `record[:keep_cells]` | **PASS** |
| `U4`（毒值 P-1..P-4） | `_Poison` 覆盖 `__getattr__/__eq__/__ne__/__hash__/__bool__/__str__/__repr__/strip`，`__len__` 不抛；BM(W=14) 与 26 列(W=26)：毒值置于第 ≥W 列 → 全程未触发，且 `result_payload()` 与「≥W 列置空」**完全相等**（含错误路径：未知 cluster / `cpu_cores` 非法整数 / 文件内重复 hostname / 网络外地址 / 组内重复）→ P-2②/P-4；同一记录第 **W-1** 列放毒值 → **`_PoisonTouched` 触发**（P-2① 负向对照）；成功路径 3 行 → `importable_rows=3`、`error_count=0` 且与置空一致（P-3 由 `U2-⑩` + `I6a` 补足表头整行） | **PASS** |
| `U5` | 10 万条 `["x"]*200`：`consumed==100000`（排空）、`overflow True`、`rows==[]`、调用峰值 **≤ 8 MiB**（实测值见 `[M]` 同级哨兵，远低于上限）、`_finalise` 抛 `ImportRowLimitExceeded{limit_rows:5000}` | **PASS** |
| `U6` | 签名含 `max_rows` / `keep_cells`（`KEYWORD_ONLY`、默认 `None`）；5 样例两参数 vs 显式 `None` **逐元素相等**、返回 `list`、`records[0]` 为完整表头（含 100 列宽表头）、全单元格为 `str` | **PASS** |

### 2.6 I 层（真实 PostgreSQL + 真实 `create_app`；差分 = 基线语义路径 vs 生产路径）

差分模板（TD-8.2）：先以 `monkeypatch.setattr(resource_import, "parse_records", reference_records)` 跑**基线语义路径**，再跑真实路径，断言 `(status_code, json())` 深等。

| 用例 | 输入 / 规模 | 实测结果 | 结果 |
| --- | --- | --- | --- |
| `I1` | S-W1 xlsx 702 列 × 5001 行（80,013 B）| 4 端点差分相等 + **413** `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows:5000}` | **PASS** |
| `I2` | S-W2 xlsx 16,384 列 × **101 行空 `<row/>`**（5,214 B；规模缩小，理由见下） | 4 端点差分相等 + **422 `unknown_columns`**，`unknown` = **16,370** 个空串；**非** 413 | **PASS** |
| `I3` | S-W3 CSV：表头 + 3 行 + 100,000 个 `\n`（BM14 与 26 列两版） | 两 validate 端点 **200**：`total_rows=3`、`error_count=0`、`importable_rows=3`、`errors=[]`、`errors_truncated=false`；两 write 端点 **201**、`created=3`、`total_rows=3` | **PASS** |
| `I4` ×2 | S-W4 CSV 5001 行 + 末行 `role="NOT_A_ROLE"`；变体末行 200 列 | 4 端点差分相等 + **413**（**不是** 422） | **PASS** |
| `I5` ×2 | S-W5：CSV 末行单字段 131,073 字符；xlsx 5001 行 + sheet 尾损坏 | 4 端点差分相等 + **422**，`details == {"reason":"unreadable"}`，`code != IMPORT_ROW_LIMIT_EXCEEDED` | **PASS** |
| `I6` | S-W6a CSV 651 列 × 4000 空行（2.6 MB）；S-W6b 651 列 × 5001 **非空**行 | a：4 端点差分相等 + **422 `unknown_columns`**（637 项全空串，无新增工作量类拒绝）；b：4 端点差分相等 + **413** | **PASS** |
| `I7` | S-W7 CSV 表头 + 1 合法行 + 1000 空行 + 1 行非法 role | `total_rows=1002`、`error_count=3001`、`errors_truncated=true`、`len(errors)=1000`、`importable_rows=1`、首错行号 **3**；小规模配对（3 空行）行号集 **{3,4,5,6}**（末行不位移）；写入 **422 `IMPORT_VALIDATION_FAILED`** + 7 表不变 | **PASS** |
| `I8` | 合法 5000 行 CSV（485,138 B） | validate 200：`total_rows=5000`、`error_count=0`、`importable_rows=5000`、`errors=[]`、`errors_truncated=false`；差分相等；**5000 行 write 等价性 → `NOT TESTED`**（TD-9 / R-14） | **PASS** |
| `I9` | S-W1 / S-W2 / S-W4 / S-W5 / S-W6a × 4 端点（写入+校验） | 全部 413/422（无 2xx）；7 表计数**逐表不变**；响应体 0 命中 `F038-MARKER-…` / `Traceback` / `<worksheet` / `.py` / `field larger than field limit` / 首个数据簇码 | **PASS** |
| `I10` / `I10b` | S-W1、S-W2 字节 × 未登录 / VIEWER × 4 端点 | 401 `AUTH_REQUIRED`；403 `FORBIDDEN{details:{reason:"permission"}}`；**无** 413/422/500 | **PASS** |
| `I11` | (a) `5,242,880+1` B；(b) 5001 合法行；(c) 5001 行 + 错误表头；(d) `import_max_rows=1` + 2 行 + 错误表头 | (a) 4 端点 **413** `IMPORT_FILE_TOO_LARGE{limit_bytes:5242880}`；(b)(c) 差分相等 + **413 行数**（行数先于表头）；(d) **413** `{limit_rows:1}` | **PASS** |
| `I12` | 1100 行 `cluster="MISSING"`（每行 1 错误） | `total_rows=1100`、`error_count=1100`、`len(errors)=1000`、`truncated=true`、`importable_rows=0`、错误四键集 + `field=="cluster"` + 行号 `2..1001`；写入 422 且 7 表不变 | **PASS** |
| `I13` | S-W3（只读两载体 × 2 端点）、S-W6a（× 4 端点） | 状态码与 `json()` 深等；重复提交一致 | **PASS** |
| `I15` ×2 | F037 输入①②③ + 缺 workbook 部件 + `b""` + 仅表头 + OLE2 + 四类表头错误（csv/xlsx 两版）× 4 端点 | 逐例差分相等；全部 422；无 500 | **PASS** |
| `I15b` ×4 | 输入①②③ + 缺 workbook 部件 | `details == {"reason":"unreadable"}` 逐字节；差分相等 | **PASS** |

**I2 规模说明（不得外推）**：`I2` 用 **101 行**而非 10,001 行——该用例的可观察结果（422 + 16,370 个空串）**与行数无关**（已在用例内断言 `max_column==16384`、表头 `[:14]==BM_HEADERS`、`first[14:]` 全为 `None`）；**10,001 行**的固定侧规模证据在 `T-1`/`T-6`（§2.7）单独实测，基线侧按 §13.4 降级到 1,001 行。**不主张已在原规模（10,001 行 × 16,384 列）执行基线对照**（≈2.7 GB 为 `ESTIMATE`）。

### 2.7 M 层（真实数值，公式与两侧数值同时公布）

协议（TD-6.2 / §14.2）：输入字节在 `tracemalloc.start()` **之前**构造；`gc.collect()` 在 start 之前与取峰值之后各一次；同进程固定顺序；**每样例 2 次重复**，断言取**较大值**。基线 = `/tmp/f038_baseline/resource_import_8e609ca.py`（`git show 8e609ca:`，`importlib` 载入 + `sys.modules` 注册，**不入库**）的 `parse_records(data, fmt)`；完成态 = `parse_records(data, fmt, max_rows=5000, keep_cells=14)`（生产调用形态）。

**TE-F038-2 复测口径（architecture §14）**：以下数值均来自本轮（`a3a2b9c`）**整模块全量重跑**；`F(x)` 为本进程同字节的**地板探针实测峰值**（`decode("utf-8-sig")` → `io.StringIO(text, newline="")` → 遍历丢弃；M6 协议、两次取较大值、按样例缓存）；`work(x) = max(peak − F(x), 0)`。xlsx 族 `floor_bytes` 按定义返回 `len(data)`（`floor=None`），故 `F/B ≡ 1.000`，判定与 §13.2 **逐位一致**。TE-F038-1 的同协议数值（四舍五入后）与本轮一致（例：S-W1-1001 baseline 11.821 / fixed 1.044），差异见两次重复列。

#### 2.7.1 两次重复值 + `B / F / F/B / peak / work`（M6 / G-A3，MiB；`B` 为字节）

| 样例 | 侧 | `B` (bytes) | `F` | `F/B` | run1 | run2 | 取用（max） | `work` | `t_traced` | `t_raw` | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S-W1-1001（702 列 × 1001 行） | baseline | 12,739 | 0.012 | 1.000 | 11.821 | 11.821 | **11.821** | **11.809** | 0.300 s | 0.114 s | ok |
| S-W1-1001 | fixed | 12,739 | 0.012 | 1.000 | 1.044 | 1.044 | **1.044** | **1.032** | 0.187 s | 0.043 s | ok |
| S-W2-1001（16,384 列 × 1001 空行） | baseline | 7,290 | 0.007 | 1.000 | 256.471 | 256.471 | **256.471** | **256.464** | 1.382 s | 1.287 s | ok |
| S-W2-1001 | fixed | 7,290 | 0.007 | 1.000 | 1.654 | 1.654 | **1.654** | **1.647** | 0.725 s | 0.663 s | ok |
| S-W6a-1000（651 列 × 1000 空行 CSV） | fixed | 651,775 | 3.136 | **5.045** | 3.142 | 3.142 | **3.142** | **0.006** | 0.073 s | 0.038 s | ok |
| S-W6a-4000（651 列 × 4000 空行 CSV） | baseline | 2,604,775 | 12.449 | **5.011** | 44.002 | 44.002 | **44.002** | **31.553** | 0.468 s | 0.384 s | ok |
| S-W6a-4000 | fixed | 2,604,775 | 12.449 | **5.011** | 12.455 | 12.455 | **12.455** | **0.006** | 0.236 s | 0.195 s | ok |
| S-W6b（651 列 × 5001 **非空**行 CSV） | baseline | 3,271,429 | 15.628 | **5.009** | 55.235 | 55.235 | **55.235** | **39.608** | 0.637 s | 0.497 s | ok |
| S-W6b | fixed | 3,271,429 | 15.628 | **5.009** | 16.684 | 16.684 | **16.684** | **1.057** | 0.246 s | 0.092 s | **413 `ImportRowLimitExceeded`（期望）** |
| S-W6c（14 列 × 5001 **非空**行 CSV） | fixed | 85,155 | 0.424 | **5.216** | 1.476 | 1.476 | **1.476** | **1.052** | 0.083 s | 0.021 s | **413 `ImportRowLimitExceeded`（期望）** |
| legal-5000（合法 5000 行 CSV） | baseline | 485,138 | 2.331 | **5.039** | 5.590 | 5.590 | **5.590** | **3.259** | 0.124 s | 0.040 s | ok |
| legal-5000 | fixed | 485,138 | 2.331 | **5.039** | 5.514 | 5.514 | **5.514** | **3.183** | 0.183 s | 0.034 s | ok |

**T-1 / T-6 的规模输入（xlsx，`F ≡ B`，仅峰值参与判定）**

| 样例 | 侧 | `B` (bytes) | `F` | `F/B` | run1 | run2 | 取用（max） | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S-W1-N2501（702 列 × 2501 行） | fixed | 24,014 | 24,014 | 1.000 | 1.141 | 1.141 | **1.141** | ok |
| S-W1-4N10001（702 列 × 10001 行） | fixed | 80,011 | 80,011 | 1.000 | 1.868 | 1.868 | **1.868** | **413（期望）** |
| S-W2-N2501（16,384 列 × 2501 空行） | fixed | 11,108 | 11,108 | 1.000 | 1.810 | 1.810 | **1.810** | ok |
| S-W2-4N10001（16,384 列 × 10001 空行） | fixed | 28,913 | 28,913 | 1.000 | 1.970 | 1.970 | **1.970** | ok |

> 说明（不得外推）：① `S-W1-4N10001` 的 verdict 为 `ImportRowLimitExceeded`（413，期望）峰值仍然有效（超额后 `rows.clear()`）；② `legal-5000` 固定侧峰值略低于基线（`ratio 0.9865`）符合预期——合法文件必须把 5000 × 14 单元格保留下来（`T-3` 只要求「无退化」）；③ `S-W6c` 的 `F/B = 5.216` 略高于 5.0–5.02：`io.StringIO` 在 85 KB 小输入上存在增长块过度分配（体积越小偏离越大），仍在 G-A2（≤ 8B + 4 MiB）内；两个宽/窄对照（S-W6b 5.009 / S-W6a 5.011）稳定在 CPython 3.12 的 ≈5.01；④ **基线与完成态两侧并不总是都测**：`S-W6c` 仅作为宽度不敏感对照的完成态（无差分需求），`S-W6a-1000` 的基线侧未在本轮重测（`T-1b′` 只比较完成态 `work`，旧 `legal-*` 参数集已按 §14.5 退役）；不得把未测的一侧当作实测值。

#### 2.7.2 阈值断言（**§14.2 新公式**；乘数 `1.5` / `8` / `2 MiB` / `64 MiB` 全未变更）

| # | 公式（§14.2 原样） | 适用 | 实测数值 | 结果 |
| --- | --- | --- | --- | --- |
| T-1（M4a） | `fixed(4N) ≤ 1.5 × fixed(N) + 2 MiB`，N=2501 / 4N=10001 | S-W1 | 1.868 ≤ 1.5×1.141 + 2 = **3.711** | **PASS** |
| T-1 | 同上 | S-W2 | 1.970 ≤ 1.5×1.810 + 2 = **4.715** | **PASS** |
| **T-1b′（M4b）** | `work(4000) ≤ 1.5 × work(1000) + 2 MiB`（`Δbytes` 配额已删除） | S-W6a（651 列 × 1000 → 4000 行） | work = **0.006** → **0.006**；0.006 ≤ 1.5×0.006 + 2 = **2.009**（余量 **338.2×**） | **PASS** |
| **T-1c（M4e，新增）** | `work(S-W6b) ≤ 1.5 × work(S-W6c) + 2 MiB`；两侧均须 **413** | S-W6b（651 列）/ S-W6c（14 列），均 5001 非空行 | **1.057** ≤ 1.5×**1.052** + 2 = **3.579**（余量 3.39×）；verdicts = `ImportRowLimitExceeded` / `ImportRowLimitExceeded`（`{limit_rows:5000}`，`status_code=413` 由异常类断言） | **PASS** |
| **T-2′（M3a）** | `work(fixed) ≤ work(baseline) / 8`，`work = max(peak − F(x), 0)` | S-W1-1001（`floor=None`⇒1×B） | 1.032 ≤ 11.809/8 = **1.476**（**11.441×**） | **PASS** |
| T-2′ | 同上 | S-W2-1001（`floor=None`⇒1×B） | 1.647 ≤ 256.464/8 = **32.058**（**155.744×**） | **PASS** |
| T-2′ | 同上 | S-W6a-4000（`floor=F`） | 0.006 ≤ 31.553/8 = **3.944**（**5312.409×**） | **PASS** |
| T-2′ | 同上 | S-W6b（`floor=F`，新增参数） | 1.057 ≤ 39.608/8 = **4.951**（**37.483×**） | **PASS** |
| **G-B（M3a）** | `work(baseline) ≥ 1 MiB`（防比值退化） | 上述 4 参数 | 11.809 / 256.464 / 31.553 / 39.608（均 ≥ 1 MiB） | **PASS** |
| **G-A1（M4d）** | `F(x) ≥ B(x)`（防探针空跑） | S-W6a-1000 / -4000 / S-W6b / S-W6c | `F/B` = **5.045 / 5.011 / 5.009 / 5.216**（均 ≥ 1） | **PASS** |
| **G-A2（M4d）** | `F(x) ≤ 8B + 4 MiB`（防判据稀释） | 同上 | 最大 `F/B = 5.216`，上界 `8B + 4 MiB` 对应 `≥ 8` 倍字节 | **PASS** |
| T-3（M3b） | `fixed_peak ≤ 1.2 × baseline_peak` | legal-5000 | 5.514 ≤ 1.2×5.590 = **6.708**（0.9865） | **PASS** |
| T-4（M3c） | `fixed_peak ≤ 64 × len(data) + 64 MiB` | S-W1 1.044 ≤ 64.778；S-W2 1.654 ≤ 64.445；S-W6a 12.455 ≤ 222.983；legal 5.514 ≤ 93.610 | — | **PASS** |
| T-5（M5） | `fixed_time ≤ baseline_time`（无绝对上限） | S-W1 0.187 ≤ 0.300（raw 0.043 ≤ 0.114）；S-W2 0.725 ≤ 1.382（0.663 ≤ 1.287）；S-W6a 0.236 ≤ 0.468（0.195 ≤ 0.384） | — | **PASS** |
| T-6（M4c，报告项不判 FAIL） | `fixed_peak(S-W2, 4N) ≤ 8 MiB` | 1.970 MiB（`within=True`） | — | **报告项** |

**作废与对照（TE-F038-1 → TE-F038-2）**

| 旧判据（§13.2，**作废**） | TE-F038-1 实测 | TE-F038-2 处置 |
| --- | --- | --- |
| `T-1b`：`Δpeak ≤ 1.5 × Δbytes + 2 MiB`（S-W6a、legal） | S-W6a 9.313 > 4.794；legal 3.296 > 2.416 ⇒ **FAIL** | 全文作废（§14.7）；重写为 `T-1b′`（`work` 口径），`legal` 参数退役（改由 `T-3` + `U5` 承担） ⇒ **PASS** |
| `T-2`：`excess = max(peak − 1×B, 0)` 且 ÷8（S-W6a） | 9.970 > 5.190（4.164×）⇒ **FAIL** | `excess(...)` 参数化为 `floor=`；CSV 传入实测 `F(x)` ⇒ **5312.409×** ⇒ **PASS**；xlsx 保持 `floor=None`，数值与判定逐位不变 |
| 无宽度不敏感判据 | — | 新增 **T-1c**（收紧，非放宽）⇒ **PASS** |

#### 2.7.3 地板实证与 §14 处置（`DEF-01` / `DEF-02` 的根因与闭合）

本轮 `test_td_f038_m4d_csv_peak_floor_coefficient_report` 的真实输出（两份可互换：分解行与探针行）：

```text
[floor-probe] bytes=2604775 peaks=[12.449, 12.449]MiB F/B=5.011
[floor-probe] bytes=651775 peaks=[3.136, 3.136]MiB F/B=5.045
[floor-probe] bytes=3271429 peaks=[15.628, 15.628]MiB F/B=5.009
[floor-probe] bytes=85155 peaks=[0.424, 0.424]MiB F/B=5.216
[floor] S-W6a-4000 bytes=2604775 decode_peak=2.485MiB (1.00x) StringIO_peak=9.937MiB (4.00x) reader_loop_peak=9.965MiB (4.01x) verdicts=ok/ok/ok
```

- **地板构成（代码事实，工期未变）**：CSV 路径必然经过 `data.decode("utf-8-sig")`（1×B）+ `io.StringIO(text, newline="")`（CPython 内部 UCS-4 缓冲 4×B），两行都是 **start_commit 基线原样代码**（`_parse_csv` 未被 F038 改写；`S1`/`S6` 零 diff）⇒ `F ≈ 5.01×B`（实测 5.009–5.045，小输入 5.216）。AQ-2=A 下不可消除（消解路径登记为 **ON-6**、范围外）。
- **归属**：`DEF-01` / `DEF-02` = **阈值口径缺陷（Architect）**，不是实现缺陷；`architecture.md` **§14.1** 已独立复核并确认「实现侧无缺陷、本轮不接受任何修改」；**生产代码零变更**（`DR-F038-10`）。
- **口径修正（非放宽）**：`F(x)` 由**实测探针**在同进程同字节标定（公式内无解释器相关常量），并受 G-A1（`F ≥ B`）与 G-A2（`F ≤ 8B + 4 MiB`）双向夹逼 ⇒ 无法抬高地板稀释判据；`1.5` / `8` / `2 MiB` / `64 MiB` **全未变动**，旧 `Δbytes` 配额被**删除**（收紧），并新增 `T-1c`。
- **TE-F038-1 的根因判断被维持**：当时实测的「地板 ≈ 5×len」和「CSV 宽表可达改倍数上限 ≈ 4.16× < 8」均与本轮一致；只是当时的修复方向为「剥离实测地板」而非「调倍数」，与 §14 一致。

### 2.8 S 层（静态守卫，全部 pytest 化 + 命令证据）

| 用例 | 断言 / 证据 | 结果 |
| --- | --- | --- |
| `S1` | 只读 `git diff --stat 8e609ca -- docs/api docs/database backend/alembic frontend backend/pyproject.toml backend/Dockerfile backend/tests/integration/test_f037_import_parse_errors.py` → **空**；模板 `[c["name"] …] == BM_HEADERS`、VM 10 列、`COLUMN_NAMES` == 26 且列序一致；`Settings(_env_file=None)` → `(5242880, 5000, 1000)` | **PASS** |
| `S2`（E-1） | `backend/app/**` AST：`parse_records(` 调用**恰 2 处**（`resource_import.py:980`、`resource_interface_ip_import.py:1199`），`keywords` 均为 `["keep_cells","max_rows"]`，文本含 `_MAX_TEMPLATE_COLUMNS` 与 `len(COLUMN_NAMES)`；`_MAX_TEMPLATE_COLUMNS == max(len(t.columns)) == 14` | **PASS** |
| `S3` | `len(_PARSE_FAILURES) == 8`；`ExceptHandler` 总数 == 基线文件（**21**）、`except Exception` 仍 2 处（`:480` `_close_workbook`、`:1113` `write_import`）；`field_size_limit`/`strict=True`/`csv.QUOTE` 零命中；`lxml` 不在 `pyproject.toml`、`app/**` 仅 `resource_import.py` 命中（可选导入）；`OSError` 只出现在 `_parse_xlsx` 行区间（`:584` 注释、`:591` 白名单） | **PASS** |
| `S4` | `grep -nE 'list\(csv\.reader\|list\(worksheet\.iter_rows'` 两 service **no match**；`_collect_records` 的 `for` 体内无 `break`/`return`（`continue` 存在）；无 `list(record)` | **PASS** |
| `S5`（L7″） | `_is_blank_record` / `_collect_records` / `_finalise` / `parse_records`：无 `try:`/`except`/`open(`/`Path(`/`NamedTemporaryFile`/`logger.`；`_cell_text` 调用只在 `_finalise` | **PASS** |
| `S6` | `git diff --name-only 8e609ca -- backend/app` → 恰 2 文件；`git status --porcelain --untracked-files=all` → 仅 2 个 service 修改 + 新增测试文件 + `docs/features/F038/` | **PASS** |

**命令证据（只读）**

```console
$ git rev-parse --short HEAD
e954537
$ git rev-parse --abbrev-ref HEAD
feature/F038-import-parse-bounds
$ git status --porcelain --untracked-files=all
 M backend/app/services/resource_import.py
 M backend/app/services/resource_interface_ip_import.py
?? backend/tests/integration/test_f038_parse_bounds.py
?? docs/features/F038/implementation.md
$ git diff --stat 8e609ca -- backend/app
 backend/app/services/resource_import.py            | 134 ++++++++++++++++++---
 .../app/services/resource_interface_ip_import.py   |  13 +-
 2 files changed, 120 insertions(+), 27 deletions(-)
$ git diff --stat 8e609ca -- docs/api docs/database backend/alembic frontend backend/pyproject.toml backend/Dockerfile backend/tests/integration/test_f037_import_parse_errors.py
(无输出)
$ git diff --stat -- backend/tests/
(无输出)
$ grep -nE 'list\(csv\.reader|list\(worksheet\.iter_rows' app/services/resource_import.py app/services/resource_interface_ip_import.py
no match
$ grep -rn "parse_records(" app/
app/services/resource_import.py:619:def parse_records(
app/services/resource_import.py:980:    records = parse_records(
app/services/resource_interface_ip_import.py:1199:    records = resource_import.parse_records(
$ grep -cE '^\s+except ' app/services/resource_import.py
21
$ docker exec csm-f037-pg psql -U csm -d csm_f037_test -tAc "show server_version"
16.15
```

**命令证据（只读）—— TE-F038-2 复测（HEAD `a3a2b9c`，2026-10-29，cwd 仓库根）**

```console
$ git rev-parse --short HEAD
a3a2b9c
$ git log --oneline -6
a3a2b9c docs(F038): repair round 1 - CSV threshold re-ruling (probe-based floor, work-set metrics)
3289d39 feat(F038): bounded parse retention (backend) + independent test evidence
e954537 docs(F038): CONTRACT signed READY FOR IMPLEMENTATION (§13 rulings: TD-I-1/2, ON-1, TD-I-8)
9ec4644 docs(F038): ARCHITECTURE READY FOR DESIGN (bounded retention, DR-F038-01..06)
fefb6e7 chore(F038): PRODUCT COMPLETE, enter ARCHITECTURE
0bc1483 docs(F038): PRODUCT READY FOR ARCHITECT (AQ-2=A boundary, B1-B13 invariants)
$ git status --porcelain --untracked-files=all
 M backend/tests/integration/test_f038_parse_bounds.py
 M docs/features/F038/test-report.md        # 本次复测跑完后追加（本报告，属白名单写入范围）
$ git diff --stat -- backend/app/services/
(空)                                          # 生产代码冻结：零 diff
$ git diff --stat -- backend/tests/integration/test_f037_import_parse_errors.py docs/api
(空)                                          # 零 diff
$ git diff --stat -- backend/tests/
 .../tests/integration/test_f038_parse_bounds.py    | 209 +++++++++++++++++----
 1 file changed, 168 insertions(+), 41 deletions(-)
$ git diff --name-only a3a2b9c -- backend/app
(空)
$ grep -cE '^\s+except ' app/services/resource_import.py
21
$ docker ps --filter name=csm-f037-pg --format '{{.Names}}\t{{.Status}}'
csm-f037-pg	Up 4 hours
```

### 2.9 R 层回归（逐条真实输出，未复用开发者结果）

| ID | 套件 | 命令（`cwd backend/`，`TEST_DATABASE_URL` 同上） | TE-F038-2 实测 | 结果 |
| --- | --- | --- | --- | --- |
| R1 | `test_f037_import_parse_errors.py` | `python3 -m pytest tests/integration/test_f037_import_parse_errors.py -q` | **`52 passed in 26.06s`**（文件零 diff：`git diff --stat` 空） | **PASS** |
| R2 | `test_imports.py` + `test_import_tester_acceptance.py` + `test_import_constraints.py` + `test_f023_resource_interface_ip_import.py` | `python3 -m pytest … -q` | **`70 passed in 417.02s`** | **PASS** |
| R3 | `test_f034_csv_text_carrier.py` + `test_f034_csv_text_carrier_scope.py` | 同上 | **`31 passed in 50.38s`** | **PASS** |
| R4 | `test_f035_append_interface_ip_import.py` + `test_f035_append_scope.py` + `test_f035_tester_acceptance.py` + `test_f036_attribution.py` + `test_f036_tester_independent.py` | 同上 | **`48 passed in 66.63s`** | **PASS** |
| R5 | `test_import_performance.py` | 同上 | **`4 passed in 174.78s`** | **PASS** |
| R6 | `test_f030_test_harness.py` | 同上（新模块不触 `access_scope` 符号 ⇒ 无需 `real_scope`） | **`3 passed in 6.60s`** | **PASS** |
| — | 新增模块·**定点复测**（§14.5） | `python3 -m pytest tests/integration/test_f038_parse_bounds.py -q -k "m3a or m4b or m4d or m4e or m6"` | **`8 passed, 68 deselected in 42.87s`** | **PASS** |
| — | 新增模块·**整模块全量** | `python3 -m pytest tests/integration/test_f038_parse_bounds.py -q` | **`76 passed in 189.35s`** | **PASS** |
| — | 新增模块·**全量 + `-s`**（§2.7 数值来源） | `python3 -m pytest tests/integration/test_f038_parse_bounds.py -q -s` | **`76 passed in 180.84s (0:03:00)`** | **PASS** |

### 2.10 Defects

| ID | 级别 | Owner | 复现 | 期望 | 实测 | 状态 / 处置 |
| --- | --- | --- | --- | --- | --- | --- |
| **DEF-01** | HIGH（TE-F038-1 时阻塞放行） | Architect（阈值口径；**非** Backend） | `python3 -m pytest tests/integration/test_f038_parse_bounds.py -q -k m4b` | 旧 §13.2 `T-1b`：`Δpeak ≤ 1.5 × Δbytes + 2 MiB` | TE-F038-1：S-W6a **9.313 > 4.794 MiB**（5.000×）；legal **3.296 > 2.416 MiB**（11.877×） | **CLOSED（口径缺陷已由 architecture §14 修正，实现未变）**。关闭依据：§14.1 独立复核「CSV 地板 = 5×len 成立、实现侧无缺陷」；§14.2 把 `T-1b` 重写为 `T-1b′`（`work` 口径，删 `Δbytes` 配额）→ 本轮 **0.006 ≤ 2.009 MiB（余量 338.2×）PASS**；§14.7 宣告旧 `T-1b` 全文作废；`DR-F038-10` 生产代码零变更 |
| **DEF-02** | HIGH（同上） | Architect（同一根因） | `python3 -m pytest tests/integration/test_f038_parse_bounds.py -q -k m3a` | 旧 §13.2 `T-2`：`excess(fixed) ≤ excess(baseline)/8`（`excess = peak − 1×B`） | TE-F038-1：**9.970 > 5.190 MiB**（4.164×） | **CLOSED（同上）**。关闭依据：§14.2/§14.3 把 `excess` 参数化为 `floor=`，CSV 传入**实测探针** `F(x)`（非硬编码 5×B）⇒ 本轮 S-W6a **0.006 ≤ 3.944 MiB（5312.409×）、S-W6b 1.057 ≤ 4.951 MiB（37.483×）PASS**；xlsx 保持 `floor=None`，S-W1/S-W2 复现 **11.441× / 155.744×**（旧 11.44× / 155.73×）；TD-I-3 维持关闭，依据按 §14.6 改写为 `work` 口径下 ≈5312× |
| — | — | — | 实现侧 | — | 无实现缺陷：A1/A3–A14 与 B1–B13 全绿；`T-1`（xlsx）、`T-3`、`T-4`、`T-5`、`T-6` 全绿；生产代码本轮零 diff | — |

**登记项**

| ID | 内容 | Owner | 状态 |
| --- | --- | --- | --- |
| `TD-I-9` | §13.2 CSV 族阈值（`T-1b`、`T-2`@S-W6a）与 CSV 峰值地板（5×len）矛盾，构造性不可满足 | Architect | **CLOSED**（§14 已签核 + 本轮复测：T-1b′ / T-1c / T-2′ 全 PASS 且公布 `F`/`work` 双侧数值 → 满足 §14.6 三项关闭条件） |
| `TD-I-10` | `excess`/`Δ` 口径未覆盖 `io.StringIO` 的 UCS-4 放大（4×） | Architect | **CLOSED**（地板已由探针式 `F(x)` 显式覆盖 StringIO，无硬编码系数；G-A3 强制公布 `F/B`，本轮 5.009–5.216） |
| `TD-I-3` | S-W6a 的 8× 余量偏薄 | Tester → Architect | **维持关闭，依据改写**（§14.6）：`work` 口径下 S-W6a 实测 **5312.409×**，「≥8×」与「≥2×」同时成立 |
| `R-15`（新） | 地板探针实现不当 ⇒ `F` 偏大 ⇒ 判据稀释 | Tester / Reviewer | **未发生**：G-A1（`F ≥ B`）与 G-A2（`F ≤ 8B + 4 MiB`）均 PASS，实测 `F/B ≤ 5.216`；探针源码仅含 `decode` / `io.StringIO(text, newline="")` / 遍历丢弃（`grep` 可核） |
| `TD-I-8`（勘误，已落稿） | S-W2 期望 = **422 `unknown_columns`**；§13.4 的「16,350」为计数笔误，实测 **16,370 = 16,384 − 14**（见 §2.3） | 已在 §2.3 落稿 | 否（文档级） |
| `TD-I-11` | `S-W2`/`I13` 的写入成功路径双载体/双路径等价性**不做**重复提交（第二次必因唯一性冲突改变响应）⇒ 单侧证据（R-14） | Tester / Reviewer | 未变（不阻塞） |
| `TD-I-6` | 无 lxml 镜像未实测（本机 `openpyxl.LXML=True`）；结论不外推 | 协调器 / Architect | 未变（不阻塞） |
| `TD-I-12`（新） | `ruff check backend/tests/integration/test_f038_parse_bounds.py` → **3× F811**（`role_client_factory` 既从 `f015_helpers` 导入、又作为 fixture 形参名）——**HEAD `a3a2b9c` 已存在同样的 3 条**（对 HEAD 版本跑 `ruff` 同样得 3 errors），**非本轮引入**；属 fixture 复用写法，不影响用例执行（76 passed） | Tester / Reviewer | 否（如实登记，不属 §14.5 白名单，本轮不改） |

### 2.11 未验证项（`NOT TESTED` / `NOT_REQUIRED`）与降级说明

| 项 | 状态 | 理由 / 已尝试命令 |
| --- | --- | --- |
| 真实内存耗尽（OS 级 OOM / 进程被杀） | **NOT TESTED** | 不在宿主制造 OOM（product N8）；以 `T-1`/`T-3`/`T-4`/`T-2′` 的相对证据替代 |
| S-W2 **原规模基线**（10,001 行 × 16,384 列，估算 ≈2.7 GB） | **NOT TESTED（`ESTIMATE`，外推）** | 基线侧按 §13.4 降级到 1,001 行（实测 256.471 MiB）；**不得**表述为已实测 |
| 无 lxml 环境（`openpyxl.LXML=False`，生产镜像形态） | **NOT TESTED** | 本机 `LXML=True`；峰值与异常类可能不同（ON-4）⇒ 结论不外推（`TD-I-6`） |
| `tracemalloc` 统计 lxml C 层分配 | **NOT TESTED（只报告）** | 以 `ru_maxrss=1,029,940 KiB`（TE-F038-2 / M6）交叉参照，不作断言 |
| 5000 行**写入**端点的等价性/耗时 | **NOT TESTED** | F037 实测该路径 300 s+；解析侧等价由 `I8`（validate）与 `R5` 覆盖；错误方向（拒绝路径）已 4 端点覆盖（R-14） |
| S-W2b（XFD 宽 + 10,001 行**非空** → 413） | **NOT TESTED** | §13.4.3 明示「如需覆盖另立」；单侧断言无差分兜底（R-14），本 Feature 不主张 |
| `legal-1000` / `legal-4000` 的 CSV 规模不敏感判据 | **NOT TESTED（已退役）** | §14.5 明示删除 `m4b` 的 `legal` 参数：合法 ≤5000 行族的 `work` 本应等于基线（实测 3.259 → 3.183），改由 `T-3`（无退化）+ `U5`（保留上界）承担；相应 `_SAMPLES` 条目保留未用 |
| `S-W6c` 的**基线侧**（651/14 列对照只比完成态） | **NOT TESTED** | T-1c 只需要两侧完成态的 `work` 对照（同为 413 超额路径）；不把未测的一侧当实测值 |
| 写入成功批次的「基线 vs 完成态」双路径差分 | **NOT TESTED** | 重复提交会因唯一性冲突改变第二次响应（`TD-I-11`/R-14）；以 validate 差分 + `I3` 单侧写入 + `R2` 既有用例覆盖 |
| 时间上界 | **NOT_REQUIRED** | ON-5：只承诺空间有界；`T-5` 仅要求不退化 |
| 前端 / 界面 | **NOT_REQUIRED** | `layers.frontend=false`；`S1` 守 `frontend/` 零 diff；T116 归 F034 R3 |
| 数据库约束 / Migration | **NOT_REQUIRED** | `layers.database=false`；解析早于任何 `begin_nested()`；`I9` 以 7 表计数复核零副作用 |
| 整体验收（§31–33 跨功能） | **NOT_REQUIRED（本 Feature）** | 归 plan `acceptance`（F045）；**不得**用本 Feature 局部 PASS 拼成整体 PASS |

### 2.12 结论

**`READY FOR REVIEW`**（TE-F038-2，2026-10-29，repair round 1 修复复测）

- **定点复测（§14.5 白名单）全绿**：`-k "m3a or m4b or m4d or m4e or m6"` = **8 passed / 68 deselected**；**整模块全量** = **76 passed / 0 failed**（189.35 s；`-s` 版 180.84 s）。新/改判据全部 PASS：`T-1b′`（0.006 ≤ 2.009 MiB，余量 338.2×）、`T-1c`（1.057 ≤ 3.579 MiB，两侧均 413）、`T-2′`（11.441× / 155.744× / 5312.409× / 37.483×）、守卫 `G-A1`/`G-A2`/`G-A3`/`G-B`。**无白名单外 FAIL，且未修改任何 `1.5` / `8` / `2 MiB` / `64 MiB` 数值，未将 CSV 的 `floor` 改回 `None`，未改 U/I/S/R 任何用例与断言，未改 `_measure` 协议与 `CAP_*`，未改期望状态码/reason。**
- **缺陷已闭合、实现未变**：`DEF-01` / `DEF-02` 属**阈值口径缺陷（Architect）**，已由 `architecture.md` **§14** 修正（`DR-F038-07` – `DR-F038-11`），且 `DR-F038-10` 明定**生产代码零变更**——本轮 `git diff --stat -- backend/app/services/` **为空**；`test_f037_import_parse_errors.py` 与 `docs/api` 均零 diff，F037 52 项零修改全绿。
- **回归全绿**：R1 52 / R2 70 / R3 31 / R4 48 / R5 4 / R6 3（本轮逐条重跑）；行为面证据（A1/A3–A14、B1–B13）与 TE-F038-1 一致且本轮整模块重执行通过。
- **TD-I-9 / TD-I-10 关闭**（满足 §14.6 三项条件）：① §14 已落稿并签核；② 本轮 T-1b′ / T-1c / T-2′（含 S-W6b）全 PASS 且公布 `F` 与 `work` 双侧数值；③ 本 §2.7.2 已按新公式重写、§2.10 已标注「口径缺陷已修正、实现未变」、§2.12 转 `READY FOR REVIEW`。

#### 2.12.1 「不能证明什么」（architecture §14.2 原样，必读）

本口径（CSV 族 `work = peak − F(x)` 相对倍数）**不能**证明：

1. **不含地板的绝对峰值有界**：CSV 峰值 ≥ `F ≈ 5B`，结合 B1（5 MiB 输入上界）得继承性绝对上界 ≈ **25.0 MiB + 工作集**，该部分不属本 Feature 成果。
2. **小于灵敏度地板的保留量回归可见**：灵敏度地板 ≈ **2 MiB**（宽度维可见下限 ≈ 70 列）；更小的退化由 `U5` / `U4`（毒值探针）/ `S4` + `IMP-2` 兜底。
3. **时间有界**：仍线性于展开工作量；`T-5` 只要求**不退化**。
4. **地板本身可再优化**：5B 仅是**本解析路径**的下界（`decode` + `io.StringIO`），消解需改 `_parse_csv` 行为面（**ON-6**，范围外且不得作为变通）。
5. **合法 ≤5000 行族的性能收益**：实测仅**无退化**（`T-3` 5.514 vs 5.590，0.9865）。
6. **残余无界面与无 lxml 环境**：R-3 三条（`read_manifest` / `read_strings` / 路由 `file.file.read()`）与 `openpyxl.LXML=False` 镜像均未覆盖。

#### 2.12.2 不主张项（architecture §14.4 ⑥）

- **不主张** CSV 能降到基线以下很多倍：宽表实测 **44.002 → 12.455 MiB（3.53×）**，其余均为继承地板；不得用 `≤ baseline/3` 类绝对倍数作判据。
- **不主张**合法 5000 行族有性能收益（5.590 → 5.514，仅无退化）。
- **不主张**时间有界（仅 T-5 不退化）。
- **不主张**地板已消除：`F/B` 实测 **5.009–5.216**，本轮实测非消除；仅登记为 ON-6。
- **不主张**已在两个代码库之间做过对照运行（差分靠测试内参考实现 + `/tmp` 基线模块，`TD-I-4`）；**不主张**真实 OOM 已测、S-W2 原规模基线已测。
- **不主张**用本 Feature 局部 PASS 拼成整体验收（§31–33 归 F045）。

**本次实际执行的 Git 命令（全部只读；无 `add` / `commit` / 分支切换 / `stash` / `reset` / `clean` / `reflog` 改写）**

```text
GIT: git rev-parse --short HEAD
GIT: git status --short
GIT: git log --oneline -6
GIT: git status --porcelain --untracked-files=all
GIT: git diff --stat -- backend/app/services/
GIT: git diff --stat -- backend/tests/integration/test_f037_import_parse_errors.py docs/api
GIT: git diff --stat -- backend/tests/
GIT: git diff --name-only a3a2b9c -- backend/app
GIT: git diff -U2 -- backend/tests/integration/test_f038_parse_bounds.py
GIT: git diff --stat -- backend/tests/integration/test_f038_parse_bounds.py
```

TE-F038-1 轮次已列出的只读命令（`git show 8e609ca:backend/app/services/resource_import.py > /tmp/f038_baseline/resource_import_8e609ca.py` 等）保留在上一版本记录中；本轮未重新生成基线模块（复用 `/tmp/f038_baseline/resource_import_8e609ca.py`，35,360 B / 1061 行）。

测试模块内部同样只读：`_git()` 封装 `git -C <repo> rev-parse --short HEAD`（M1）、`git -C <repo> diff --stat 8e609ca -- <zero-diff paths>`（S1）、`git -C <repo> diff --name-only 8e609ca -- backend/app` 与 `git -C <repo> status --porcelain --untracked-files=all`（S6）。
