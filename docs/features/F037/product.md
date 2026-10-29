# F037 导入解析异常统一收敛为 422 IMPORT_INVALID_FILE — PRODUCT 阶段报告

- **状态**：READY FOR ARCHITECT
- **版本**：v1（2026-10-29）；FEATURE / P0 / M28 导入契约修复；分支 `feature/F037-import-parse-error-contract`，交付线 `v3.4`，start_commit `1c0eeaf`；**plan revision 25**；**requirements revision 16**。
- **角色产物**：product-manager 只读产出，协调器持久化（正文未改动实质内容）。
- **Basis（按权威顺序）**：
  1. `docs/api/F014.md` v1 §1.2 / §2 / §7 / §9 / §10（已签核 READY）：`422 IMPORT_INVALID_FILE` 的触发含「不可解码 / 损坏 / 非 `.xlsx` / 空数据行 / 表头或列不符」，`details.reason` ∈ `unreadable` / `unsupported_format` / `header_missing` / `missing_columns` / `unknown_columns` / `column_order` / `empty_file`；§2 冻结校验顺序；§7 冻结 CSV / `.xlsx` 解析方式。
  2. `docs/api/F023.md` **v2** §1.2 / §2 / §7 / §12：错误码与 `reason` 集合**全部复用 F014**、不新增；校验顺序与解析口径同源。
  3. `docs/product/requirements-v3.md` **revision 16**：§24、§24.1、§24.5、§24.6、§22、§23 / §23.2、§31 **T27 / T28 / T72 / T107–T116（含 T114 追认）/ T124 / T126**、§32、§35.1。
  4. 用户裁定（CONFIRMED，2026-10-29）：**AQ-3 = A**（`DERIVED_FROM_CONFIRMED`）——解析阶段失败归入既有 422 `IMPORT_INVALID_FILE{reason:"unreadable"}`；不改 `csv.field_size_limit`、不启用严格 CSV 引号规则、不新增错误码 / `reason` / 字段 / 上限 / 权限 / 端点 / Schema；行级字段长度错误（选项 B）不属本 Feature。
  5. `docs/project/proposals/CHG-015-post-delivery-review-closeout.md`（APPROVED，plan revision 25）§2 不变项、§3 R02 处置、§5 历史保护；来源 `/tmp/csm-review-2026-10-29.md` §R02。
  6. plan revision 25 F037 条目（`layers={database:false,backend:true,frontend:false}`、`api_required=true`、`blocking_decisions: []`、`depends_on` F014 / F023 / F034 / F035 均 DONE）。

## 1. 性质：既有契约内的实现缺陷修正，不是新业务规则

- 请求在**解析阶段已失败**（`csv` 迭代期 `csv.Error`；xlsx 迭代期 XML 解析错误）。按 F014 §1.2，解析失败本就应映射为 **422 `IMPORT_INVALID_FILE`**，`unreadable` 即「不可解码 / 损坏」；F023 v2 §1.2 逐项复用同表。
- 按 F014 §2 / F023 v2 §2 校验顺序（401 → 403 → `format` 422 → 413 大小 → **解析 422** → 413 行数 → 表头/列 422 → 逐行），解析阶段必须落在 422 档位；当前实现逃逸为 `500 INTERNAL_ERROR`，超出契约列举的 500 用途（未预期错误 / 死锁兜底）。
- 因此本 Feature **不扩大可拒绝输入集合、不新增拒绝原因、不改变任何拒绝判定条件**：两类输入修复前后都被拒绝，只是修复后以契约规定的状态码与 `reason` 呈现。用户 2026-10-29 的 AQ-3 确认是对该推导的确认。
- 需求 revision 16 的增量（§28.1 / T127–T129）来自 R04，与本项无关；本项不产生需求正文变更，领域模型无新对象 / 关系 / 状态 / 唯一性 / 生命周期影响。

## 2. 需求映射

### 2.1 覆盖范围

| # | 范围 | 依据 | 可验收表述 |
| --- | --- | --- | --- |
| S1 | 四端点在**解析阶段**的已知解析器异常统一返回 422 `IMPORT_INVALID_FILE` | F014 §1.2/§2/§7；F023 v2 §1.2/§2/§7；AQ-3=A | `POST /api/v1/imports/resources`、`/imports/resources/validate`、`/imports/resource-interfaces-ips`、`/imports/resource-interfaces-ips/validate` 均 422，`error.code == "IMPORT_INVALID_FILE"` |
| S2 | 两类复现输入：①131,082 B CSV（单字段 131,073 字符）；②约 4.8 KiB XLSX（XML 结束标签损坏，`load_workbook` 成功、`iter_rows` 抛错） | 同 S1；R02 复现 A / B | 2 类 × 4 端点 = 8 个请求全部 422，`details.reason == "unreadable"` |
| S3 | 拒绝请求零残留 | §24-2、§24.1 原子性、§22、T27、T68、T123 | 4 条写入路径：无 Resource / Interface / IPAddress 写入、无 Audit / Activity、无部分成功 |
| S4 | 既有原因与顺序零回归 | F014 §2、F023 v2 §2；T27 / T28 / T72 | `empty_file` / `unsupported_format` / `header_missing` / `missing_columns` / `unknown_columns` / `column_order` / 两 413 / `IMPORT_VALIDATION_FAILED` 触发条件与顺序不变 |
| S5 | 双载体等价性不变 | §24.5 等价性；T107 / T108 / T114（revision 15 追认）、T115 | 同字节 CSV 经文件与文本载体提交，状态码 / `code` / `reason` / `row` / `field` / `related_row` 逐字段相同；粘贴内容不落盘、不入库、不写 Audit / 日志 / 错误响应 |
| S6 | 模板 / 端点 / 错误码 / 上限零变更 | T126、CHG-015 §2 不变项 1–6 | 5 MiB / 5000 行 / 预览 1000 不变；BM 14 / VM 10 / 26 列模板与列序不变；端点、`format` 取值、`IMPORT` 权限与 §23.2 范围不变；错误码与 `reason` 集合零新增 |
| S7 | 契约面：F014 §1.2 与 F023 v2 §1.2 各加一条**不升版编辑性澄清附注** | plan revision 25 F037 `scope`；先例 F035-RV-05 | 附注只写「解析阶段解析器异常（CSV 迭代期 `csv.Error`、xlsx 迭代期 XML / zip 结构错误）归入既有 `unreadable`；不启用严格引号、不调整 `csv.field_size_limit`、不新增码 / reason / 字段 / 上限」，不得写成新增拒绝；正文版本不变（F014 v1、F023 v2） |

### 2.2 明确不覆盖（不得作为本 Feature 失败判据）

| # | 不做 | 依据 |
| --- | --- | --- |
| N1 | 行级字段长度错误（AQ-3 选项 B）：不新增行级判定与 `RowError` 归因、不新增 `reason` / 字段 | AQ-3=A；须另立需求变更 |
| N2 | 不调整 `csv.field_size_limit`；**不承诺**单字段 >131,072 字符的合法数据可导入，该输入仍为文件级 `unreadable` | AQ-3=A；CHG-015 §2 不变项 6 |
| N3 | 不启用严格 CSV 引号规则；引号未闭合等字段边界仍按既有 `csv` 行为判定 | T114（revision 15 追认）；F034 architecture §12 TD-I-1 |
| N4 | 不新增错误码 / `reason` / 响应字段 / `details` 键 / 上限数值 / 配置项 / 权限项 / 端点 / 查询参数 / 请求字段 / Schema / Migration | CHG-015 §2 不变项 1–3、8；F023 v2 §1.2 |
| N5 | 不改上限与两 413 语义、两步流程、整批原子回滚、1-based 行号与 `field` / `related_row` 口径、Audit 口径、§23.2 行级校验 | §24、§24.1、§24.5、§24.6；F014 §8/§10；F023 v2 §4/§12/§14 |
| N6 | 不改前端、模板列集与列序、`format` 语义；无界面改动 | plan revision 25 `layers.frontend=false` |
| N7 | 解析内存与解压工作量边界（R05）不属本 Feature；不把内存耗尽类失败归入 `unreadable` | plan revision 25 F038 |
| N8 | 不重写、不回填 F014 / F023 / F034 / F035 的 DONE 证据与历史判定 | CHG-015 §5；change-control |

## 3. 期望错误契约（可观察）

### 3.1 8 个用例目标结果

| 端点 | 输入 ①：131,082 B CSV（单字段 131,073 字符） | 输入 ②：~4.8 KiB XLSX（结束标签损坏） |
| --- | --- | --- |
| `POST /api/v1/imports/resources/validate` | 422 `IMPORT_INVALID_FILE`，`details.reason="unreadable"` | 同左 |
| `POST /api/v1/imports/resources` | 422，`reason="unreadable"`，零写入 | 同左 |
| `POST /api/v1/imports/resource-interfaces-ips/validate` | 422，`reason="unreadable"` | 同左 |
| `POST /api/v1/imports/resource-interfaces-ips` | 422，`reason="unreadable"`，零写入 | 同左 |

共同要求：

1. **422** + `error.code == "IMPORT_INVALID_FILE"` + `details.reason == "unreadable"`；不得出现 500，也不得 2xx。
2. 复用既有错误信封 `{"error":{"code","message","details"}}`；`details` 不新增键。
3. 4 个端点同口径：同一输入在 `validate` 与写入端点状态码、`code`、`reason` 一致。
4. `validate` 无副作用（幂等、不写 Audit、不加锁）；写入端点解析失败即终止，不进入写入分支。
5. 同字节重复提交结果一致，无持久化或审计副作用。

### 3.2 HTTP 顺序保持（不得重排）

`401` → `403` → `format` 形状 422 → 413 `IMPORT_FILE_TOO_LARGE` → **解析 422** → 413 `IMPORT_ROW_LIMIT_EXCEEDED` → 表头/列 422 → 逐行校验。推论：未认证 / 无 `IMPORT` 先返回 401 / 403；超过 5 MiB 仍为 413（不得变 422）；输入 ① 为 131,082 B 必须越过 413 并在解析阶段被拒绝（因此禁止「提高 `csv.field_size_limit`」或「按字节提前拒绝」两种替代实现）。

### 3.3 不留痕与内容保护

- 拒绝请求：无写入、无 Audit / Activity、无部分成功。
- **不得把用户内容写入错误消息、日志或响应**：原始字段值、XML 片段、文件字节片段、整段粘贴内容均不得回显（§24.5、§22）。错误文案只表达「文件无法解析、本次未导入」。

## 4. 边界与不得改变的既有行为

| # | 既有行为 | 要求 |
| --- | --- | --- |
| B1 | 空文件 / 仅表头 → 422 `empty_file` | 不变，不得收敛为 `unreadable`（T110） |
| B2 | 非 OOXML / `.xls` → 422 `unsupported_format` | 不变 |
| B3 | 缺表头 / 缺列 / 未定义列 / 列序不符 → 对应既有 `reason` | 不变（T112） |
| B4 | 超字节 / 超行数 → 413 两码 | 不变（T111、T28） |
| B5 | 行级错误 → 预校验 200 + `errors[]` 或写入 422 `IMPORT_VALIDATION_FAILED`，`RowError` 形状与行号不变 | 不变（T27、T67、T109） |
| B6 | 既有 `ImportInvalidFile`（已带明确 `reason` 的业务拒绝） | 必须原样透传，不得改写为 `unreadable`；原因保真优先 |
| B7 | `MemoryError` / `RecursionError` / `KeyboardInterrupt` / `SystemExit` 及未识别异常 | **不得吞成 `unreadable`**；`MemoryError` / `RecursionError` 是否仍为 500 由 Architect 按既有 500 语义裁定，`KeyboardInterrupt` / `SystemExit` 保持进程 / 中断语义 |
| B8 | 500 `INTERNAL_ERROR`（未预期错误、死锁兜底 40P01） | 保留；本 Feature 只缩小其适用范围 |
| B9 | 双载体等价 | 不变（T108、T114、T115） |
| B10 | `IMPORT` 权限、401 先于 403、§23.2 行级整批失败 | 不变（T72、T89、T115、T124） |
| B11 | 两步流程、写入再校验、整批原子回滚、每对象 CREATE Audit | 不变（§24-1 / §24-2、T68、T69、T118、T123） |
| B12 | 模板、端点、`format` 语义、上限常量、`reason` 集合 | 不变（T126） |

## 5. 领域与数据影响

无新对象 / 关系 / 状态 / 唯一性 / 生命周期规则；无 Schema / Migration / 索引 / 约束 / 事务边界 / 写入顺序变化（`layers.database=false`）；无权限项、角色、范围语义变化。受影响面仅限「导入文件级错误的可观察表达」。

## 6. Blocking Questions

**无 Blocking Questions。**

1. 目标行为由已签核契约与需求共同确定，用户已确认 AQ-3 = A；本 Feature 不新增、不收窄任何业务规则。
2. 范围分岔项已裁定：行级字段长度错误不在本 Feature，且不宣称永久排除（须另立变更）。
3. 无新对象 / 状态 / 唯一性 / 权限，不存在需用户裁定的领域冲突。
4. 残留歧义均属技术设计：异常类别技术清单与捕获落点、错误 `message` 文案与信息粒度、日志级别与脱敏实现，交 Architect / Backend 在 ARCHITECTURE / CONTRACT 阶段签核。

### 6.1 Non-blocking 观察

- **ON-1（Architect）**：`message` 文案与信息粒度；产品硬性要求为「不含上传内容」，是否掩蔽内部异常类名 / 路径 / 堆栈属工程选择（建议掩蔽）。
- **ON-2（Architect）**：需覆盖的解析器异常技术清单（CSV 迭代期 `csv.Error`；xlsx 迭代期 XML / zip 结构错误，含 `load_workbook` 成功后的延迟失败）及统一转换落点（F014 / F023 共用点）。
- **ON-3（Architect / Tester）**：F038 若改动解析路径，本 Feature 的 8 例断言与「同字节输入逐字一致」口径必须继续成立。
- **ON-4（协调器 / 用户后续）**：行级字段长度错误（AQ-3=B）需另立需求变更并升版契约；本 Feature 不预建该能力。

## 7. 验收映射草案（供 TEST DESIGN 承接）

| ID | 断言 | 映射 |
| --- | --- | --- |
| A1–A8 | 4 端点 × 2 输入：422、`code=="IMPORT_INVALID_FILE"`、`reason=="unreadable"`；无 500、无 2xx | S1、S2 |
| A9 | 写入端点 4 例后：目标表零新增、Audit / Activity 零新增、无部分成功 | S3；T27、T68、T123 |
| A10 | 未认证 401、VIEWER 403 均**先于**解析 422 | S4；B10；T72、T115 |
| A11 | >5,242,880 B → 413（不得变 422）；输入 ①（131,082 B）返回 422 而非 413 | S4；B4 |
| A12 | 仅表头 / 空文件 → `empty_file`，不为 `unreadable` | B1；T110 |
| A13 | `.xls` / 非 OOXML → `unsupported_format` | B2 |
| A14 | 表头 / 列类错误 `reason` 不变 | B3；T112 |
| A15 | 5001 行 → 413；无部分导入 | B4；T111 |
| A16 | 行级非法行 → 200 + `errors[]` 或 422 `IMPORT_VALIDATION_FAILED`，形状与行号不变 | B5；T27、T67、T109、T124 |
| A17 | 双载体等价：输入 ① 经两载体响应逐字段相同 | S5；T108、T114、T115 |
| A18 | 错误响应体 / 日志 / Audit 不含上传内容（grep 级守卫） | §3.3；§24.5、§22 |
| A19 | 不吞异常守卫：`ImportInvalidFile` 原因保真；`KeyboardInterrupt` / `SystemExit` 语义不变（构造方式由 Architect / Tester 决定，不可测时标 `NOT TESTED`） | B6、B7 |
| A20 | 同输入重复 `/validate` 一致、无副作用、不加锁 | §3.1-4/5；T116 |
| A21 | 契约与常量守卫：错误码表 / `reason` 集合 / 模板列集与列序 / 上限常量 / 端点清单零 diff；F014 仍 v1、F023 仍 v2（仅 §1.2 附注） | S6、S7；T126 |
| A22 | 回归 T27 / T28 / T72、T107–T116（重点 T114）、T124 / T126 全绿 | S4、S6 |

**不在验收范围**：行级字段长度错误归因、严格引号拒绝、上限调整、解析内存峰值边界（F038）、前端改动、F001–F036 历史证据回溯。

## 8. 未执行项

未运行测试、构建或脚本；本阶段只固化已确认规则与可观察验收标准。技术方案（异常捕获清单与落点、错误文案、日志脱敏、契约附注措辞）交 ARCHITECTURE / CONTRACT Gate 决定并签核。

## 9. 后续文档更新（协调器保存）

| 文档 | 建议 |
| --- | --- |
| `docs/product/requirements-v3.md` | 无正文变更（R02 为既有契约符合性修复）；§36 状态记录按事实维护 |
| `docs/product/domain-model.md` | 无变更 |
| `docs/api/F014.md` / `docs/api/F023.md` | 交付时各在 §1.2 加一条不升版编辑性澄清附注（见 S7），正文版本不变 |
