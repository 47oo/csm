# F038 导入解压 / 解析内存边界加固（R05）— PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-29）；FEATURE / P1 / M29 导入解析加固；分支 `feature/F038-import-parse-bounds`，交付线 `v3.4`，start_commit `8e609ca2e5b88c30804b6f6ad54a8a57d7906556`；**plan revision 25**；**requirements revision 16**。
- **角色产物**：product-manager 只读产出，协调器持久化。
- **Basis**：用户 2026-10-29 裁定 **AQ-2 = A**（仅实现侧有界解析，零可观察差异；选项 B「新增可观察上限」不纳入，须另立变更）；`docs/product/requirements-v3.md` revision 16 §24 / §24.1 / §24.5 / §24.6 / §22 / §23 / §23.2 / §31（T28、T72、T107–T116 含 T114 追认、T124、T126）/ §32；`docs/api/F014.md` v1 §2 / §7 / §10 / §13；`docs/api/F023.md` v2 §2 / §7 / §14 / §17；`docs/features/F037/{product,architecture,implementation,test-report}.md`（尤其 §15.4 / §15.10 白名单与 context manager、§15.10.4 L7′、§11 R-1/R-12、§12 OPEN-T3）；CHG-015 §2 不变项 / §3 R05 处置 / §5；来源 `/tmp/csm-review-2026-10-29.md` §R05（静态路径分析，未执行耗尽内存实验）；plan revision 25 F038 条目（`layers={database:false,backend:true,frontend:false}`、`api_required=false`、`blocking_decisions: []`、`depends_on` F014/F023/F037 均 DONE）。

## 1. 性质：实现层资源加固，不新增业务规则

### 1.1 问题与目标（代码事实）

- `.xlsx` 解析当前全量物化单元格（`list(worksheet.iter_rows(values_only=True))`），CSV 同样全量物化为 `list[list[str]]`；**5000 行上限在解析完成之后**才检查（解析 → 尾部空行裁剪 → 行数 → 表头/列 → 逐行）。
- 5 MiB **上传字节**上限只约束压缩后体积，不约束解压 / 展开后的工作量：异常宽表或大使用区域可在「行数上限拒绝」前消耗大量内存。
- 目标：为解析（含解压 / 展开）建立可验证的工作量边界——同字节输入解析阶段内存峰值相对于输入规模有界，且不随展开工作量无界增长。
- **性质**：既有已签核契约（上限、校验顺序、错误口径）之下的实现层资源约束，不产生新的业务可见规则、拒绝条件、上限数值或响应差异。

### 1.2 AQ-2 = A 的边界

| 维度 | 口径 |
| --- | --- |
| 可观察行为 | **零差异**：同一字节输入在 `8e609ca` 基线与 F038 完成态，四端点返回的 HTTP 状态码、错误码、`details.reason`、`message`、行号、`field` / `related_row`、`total_rows` / `importable_rows` / `error_count` / `errors` / `errors_truncated` 逐字段一致；不新增任何拒绝 |
| 允许改变的量 | 仅服务端资源消耗（解析阶段内存峰值及可能的时间特征），且必须有可重复测量证据 |
| 上限数值 | 5,242,880 B / 5000 行 / 1000 预览不变；不新增「解压后字节数 / 列数 / 单元格数」等上限或配置项 |
| 契约面 | `docs/api/F014.md` / `docs/api/F023.md` 零 diff；错误码与 `reason` 集合、`details` 键、响应字段、模板、端点、`format`、权限零变更 |
| 需求面 | 需求 revision 16 零正文变更；领域模型无影响 |

### 1.3 为什么 AQ-2=B 被排除

选项 B（新增解压后字节 / 列数等可观察上限）会新增一类用户可见拒绝，构成新增业务规则：须落稿需求 revision 17、契约升版（新增 `reason` / `details` 键 / 上限参数），并重新评估 `api_required` 与前端提示与等价性口径。因此不属本 Feature，须用户另立变更；本报告不宣告该能力被永久排除。

**Gate 条件（非阻塞问题）**：若 Architect 结论是「必须引入可观察拒绝才能达成内存有界」，本 Feature 不得自行实现，须停下按 AQ-2=B 另立变更；在 AQ-2=A 下任何检查只能在实现层消化，不得改变任何响应。

## 2. 需求映射

### 2.1 覆盖范围

| # | 范围 | 可验收表述 |
| --- | --- | --- |
| S1 | 解析 / 解压阶段工作量有界 | 入库的宽表与大使用区域基准样例上，解析阶段峰值不随展开工作量（行数 × 宽度 × 使用区域）无界增长；方法与阈值由 Architect / Test 定义并入库 |
| S2 | 同字节输入逐字一致 | 基线与完成态 4 端点响应（状态码 + JSON 深比较）逐字段相同；无新增拒绝、无状态码迁移 |
| S3 | 超行数（>5000）仍完整遍历但不累积 | 5001 行且尾部存在**行级错误或超宽行**的输入仍返回 413 `IMPORT_ROW_LIMIT_EXCEEDED`（不得变 422 / 500）；5000/5001 边界不变。**S3 措辞解释（ON-1 errata，2026-10-29）**：尾部**解析器异常**（`csv.Error`、zip/XML 结构错误、`LxmlError`、`_parse_xlsx` 局部 `OSError`）按 B6「解析 422 先于行数 413」返回 **422 `IMPORT_INVALID_FILE{reason:"unreadable"}`**，与基线一致（依据 `architecture.md` §11 + §13.3、`test-report.md` TD-3.3 实测）。本解释属 Feature 报告级澄清，不改需求正文、不改契约、不需用户裁定 |
| S4 | 双载体一致 | 同字节 CSV 两载体响应逐字段相同；`.xlsx` 仍仅文件载体；前端零改动 |
| S5 | 既有限额、预览与行号语义不变 | 见 B1–B5 |
| S6 | 校验顺序与既有 reason 优先级不变 | 见 B6–B7 |
| S7 | F037 的 422 `unreadable` 收敛继续生效 | F037 的 52 项用例在全绿；损坏输入仍 422 而非 500 |
| S8 | 拒绝路径零副作用 | 见 B10 |

### 2.2 必须不变量（任一项变化即失败）

| # | 不变量 | 验收断言 |
| --- | --- | --- |
| B1 | 5 MiB 上限与 413 `IMPORT_FILE_TOO_LARGE{limit_bytes:5242880}` | `> 5,242,880` B 仍在解析前 413；不得把拦截挪到解析后，不得新增第二道字节拦截 |
| B2 | 5000 行上限与 413 `IMPORT_ROW_LIMIT_EXCEEDED{limit_rows:5000}` | 5001 → 413；5000 → 不触发；行数在解析之后、表头/列之前判定 |
| B3 | 尾部空行不计入行数、不移动真实行号（BOM / CRLF / LF / 混用） | `total_rows` 不含尾部空行；真实数据行 1-based 行号不位移；`.xlsx` 尾部空使用区域行同样不计入 |
| B4 | `errors_truncated` 与 1000 条预览 | `error_count > 1000` 时 `errors` 恰 1000 且 `errors_truncated=true`；否则 `false`；`importable_rows` 口径不变 |
| B5 | 1-based 行号；`field` 取模板列名；`related_row` 语义不变 | 行级错误 `row` / `field` / `related_row` 与基线逐字段相同（含引号内换行按逻辑记录计行） |
| B6 | 校验顺序：401 → 403 → `format` 422 → 大小 413 → 解析 422 → 行数 413 → 表头/列 422 → 逐行 | 对角用例逐项断言顺序不变（尤其「行数上限先于表头类」与「解析错误先于行数」） |
| B7 | `empty_file` / `unsupported_format` / 表头四类 reason 触发与优先级不变 | 六类原因逐项断言；宽表仍按既有列类原因处理，不得改写成工作量类拒绝 |
| B8 | F037 的解析异常收敛继续生效（含 `LxmlError` 条件条目与 `_parse_xlsx` 局部 `OSError`） | 损坏输入仍 422 `unreadable`，`details` 恰 `{"reason":"unreadable"}`；`MemoryError` / `RecursionError` / 未识别异常仍 500 |
| B9 | 双载体逐字节等价（T114 revision 15 追认） | 两载体状态码、错误码、reason、行号、`field`、`related_row` 完全一致；不新增字段边界判定；粘贴内容不留痕 |
| B10 | 零写入 / 零 Audit / 无部分成功 | 4 端点拒绝路径后 7 表计数不变（无 activity 表，由 `audit_logs` 派生） |
| B11 | `IMPORT` 权限与 §23.2 范围；401 先于 403 | 未认证 401、VIEWER 403 先于解析（有界解析不得提前消费请求体改变顺序）；含未授权集群行整批失败 |
| B12 | 模板 / 端点 / 响应字段 / 错误码 / reason 集合零变更 | BM 14 / VM 10 / 26 列与列序不变；4 端点与 `format` 不变；契约零 diff |
| B13 | 内容保护 | 错误响应与日志 0 命中样例 marker、字段值、`filename`、堆栈（允许 `error=<Class>`） |

### 2.3 明确不覆盖

| # | 不覆盖 |
| --- | --- |
| N1 | 不新增可观察上限（解压后字节 / 列数 / 单元格数 / 展开工作量）及其拒绝（AQ-2=B 专属） |
| N2 | 不新增配置项、上限数值、错误码、reason、details 键、响应字段、端点、查询参数、权限项、Schema / Migration |
| N3 | 不改模板与列序；不改 `format` 语义；无前端改动 |
| N4 | 不引入 lxml 或任何新运行时依赖；不改 `pyproject.toml` / `Dockerfile`；lxml 维持可选加速依赖 |
| N5 | 不改 `csv.field_size_limit`、不启用严格 CSV 引号规则、不新增字段边界判定 |
| N6 | 不改两步流程、整批原子回滚、Service Layer 同源校验、各计数口径 |
| N7 | 不改权限矩阵、§23.2 范围、Audit 口径、CSRF 与 401/403 语义 |
| N8 | 不声称已测得生产内存问题或已修复崩溃（R05 为静态路径分析）；只承诺相对输入规模有界 + 可重复基准证据 |
| N9 | 不收紧 `MemoryError` / `RecursionError` / 未识别异常的 500 语义 |
| N10 | 不重写、不回填 F014 / F023 / F037 的 DONE 证据与历史判定 |

## 3. 领域与数据影响

无新对象 / 关系 / 状态 / 唯一性 / 生命周期 / 权限项 / 范围语义变化。`layers.database=false` → Database NOT_REQUIRED（解析发生在任何 `begin_nested()` 之前）。受影响面仅限解析阶段的服务端资源消耗，不改变任何可观察结果。

## 4. Blocking Questions

**无 Blocking Questions。** 目标行为由已签核契约与 AQ-2=A 完全确定；范围分岔已裁定（B 不纳入、C 未采纳）；无新对象 / 状态 / 权限冲突；残留歧义（流式形态与 `parse_records` 兼容、测量方法与阈值、超限后继续遍历策略、context manager 复用、L7′ 重评）均属技术设计，交 ARCHITECTURE / CONTRACT Gate 签核。已登记的 Gate 条件见 §1.3（设计越界即回退变更控制，非阻塞问题）。

## 5. Non-blocking 观察（交 Architect / Tester）

| ID | 观察 | 归属 |
| --- | --- | --- |
| ON-1 | 流式实现与 `parse_records` 返回形态的兼容：F037 §2.1-3 曾要求「不引入流式包装」，并把该改造列为 F038 范围（OPEN-T3：须复用 context manager 并保持语义或走变更控制）。两 `parse_and_validate` 依赖物化结果做「尾部空行裁剪 → 行数 → 表头 → 逐行」，行号建立在索引上。须明确保留物化返回值而内部有界迭代，或改迭代器并同步改造调用方（后者须显式裁定并保证 B3/B5/B6 不变） | Architect |
| ON-2 | 流式化后必须继续复用 `_invalid_file_on_parse_failure` + `_PARSE_FAILURES`（含 `LxmlError` 与 `OSError`），白名单作用域不得漂移，否则 B8 失守 | Architect / Backend |
| ON-3 | L7′ 重评触发点：若流式化引入临时文件 / 路径读取 / 请求流直喂 `load_workbook`，`OSError` 条目须重新裁定并重评 R-12 | Architect |
| ON-4 | 内存测量方法与阈值：建议 `tracemalloc` 峰值 + 入库样例构造脚本，阈值以相对倍数上界表述，不以绝对 MB 硬编码 | Architect / Tester |
| ON-5 | 「空间有界 vs 时间线性」：S3 要求超行数后继续迭代，意味着时间仍随输入线性增长（空间有界）；设计须显式说明该残余特征，不得用「完全有界」表述；若时间侧也须设界只能走 AQ-2=B | Architect |
| ON-6 | 基准须先于优化：先做基线测量、修复后同法复测，不用推测值代替实测 | Architect / Tester |
| ON-7 | Database NOT_REQUIRED 复核与契约零 diff 守卫（`git diff -- docs/api/`） | Database / Architect |

## 6. 验收映射草案（供 TEST DESIGN 承接）

| ID | 断言 |
| --- | --- |
| A1 | 同字节输入逐字一致：固定输入矩阵（F037 的 8 例 + 输入③ + 缺 workbook 部件 + 413 字节 / 413 行数 / `empty_file` / `unsupported_format` / 表头四类 / 行级错误 / 正常成功批次）在基线与完成态分别提交 4 端点，状态码与 JSON 深比较完全相等 |
| A2 | 内存峰值有界（相对倍数）：宽表与大使用区域样例上峰值 ≤ 设计上界且不随展开工作量无界增长；同输入仍产出 A1 响应 |
| A3 | 超行数后继续迭代但不累积：5001 行 + 尾部损坏 / 超宽行仍 413；5000 行不触发；该路径峰值同样有界 |
| A4 | 尾部空行 / BOM / CRLF / 混用：`total_rows` 与行号不位移；`.xlsx` 尾部空行不计入 |
| A5 | 上限与预览：两 413 数值不变；`error_count > 1000` 时 `errors` 恰 1000 且 `errors_truncated=true` |
| A6 | 校验顺序对角用例与基线一致 |
| A7 | 既有 reason（六类）逐项不变；宽表走列类原因 |
| A8 | 双载体等价逐字段一致；粘贴内容不留痕 |
| A9 | 零写入 / 零 Audit；混合批次整批回滚 |
| A10 | 401 / 403 先行；未授权集群行整批失败 |
| A11 | F037 的 52 项全绿；F034 / F035 / F036 套件无回归 |
| A12 | 基准证据入库：脚本、样例构造、基线值与修复后值、环境（`openpyxl.__version__` / `openpyxl.LXML` / `lxml.__version__`）、可重复命令 |
| A13 | 零变更守卫：`docs/api/` 零 diff；模板 / 端点 / 错误码 / 上限常量 / `pyproject.toml` / `Dockerfile` / `frontend/` 零 diff；grep 无新增 `except Exception` / `except SyntaxError`、无 `field_size_limit` 变更、无 lxml 依赖声明 |
| A14 | 内容保护 grep 级守卫 |

**不在验收范围**：任何新增可观察上限（AQ-2=B）、严格引号拒绝、`field_size_limit` 调整、前端改动、真实内存耗尽（`NOT TESTED`）、F001–F037 历史证据回溯、整体验收（归 F045）。

## 7. 后续文档更新

| 文档 | 建议 |
| --- | --- |
| `docs/product/requirements-v3.md` | 无正文变更；§36 状态记录按事实维护 |
| `docs/product/domain-model.md` | 无变更 |
| `docs/api/F014.md` / `docs/api/F023.md` | 零 diff（`api_required=false`） |
| `docs/database/*` | 无变更（NOT_REQUIRED 继续成立） |
