# F034 导入 CSV 文本载体 — Test Report

> 本文件同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本、结论与证据。
> 当前**只有 TEST DESIGN（v1.1，2026-10-26）**。`TEST DESIGN READY` 仅表示方案可验证，**不是测试通过**，不批准实现或合并。
> 编写时分支 HEAD `bbc9e91`（`33d8a03..bbc9e91` 仅含 docs 变更，无前端/后端实现），因此本阶段只做设计检查，未执行任何验收。

---

## Test Design（TD-1，2026-10-26，v1 / v1.1）

**版本记录（本阶段）**

- **v1（2026-10-26）**：首次 TEST DESIGN —— TD-1–TD-14、56 条 `TD3-*` 用例、夹具 `F-01`–`F-26`、等价性判据 TD-5、原子性 TD-6、降级边界 TD-12。该版内容保留，除下列 v1.1 修订点外不改动。
- **v1.1（2026-10-26）**：依 Architect §12 裁定收窄 TD3-T115.5①、落定 T114 判据、TD-I-2 记录为仅固定 reason 类别集合；同版仅更新上游**状态事实**（architecture v1 §12 = `READY FOR IMPLEMENTATION`；`docs/api/F014.md` / `docs/api/F023.md` 增补节 = **READY** 并附 3 条解释性裁定附注；requirements revision 13 §31 T114 已作编辑性澄清），**未放宽任何判据、未新增或删除验收项**。

### TD-1 Task / Status / Basis

- **Task**：F034「导入 CSV 文本载体」（P1 / M25）；分支 `feature/F034-csv-text-import`（base `v3.3`，start_commit `33d8a03`，TD v1 编写时 HEAD `bbc9e91`）；`plan_revision` 20；阶段 **TEST_DESIGN**；Tester 只读分析 + 仅写本文件。
- **Status**：`TEST DESIGN READY (v1.1)`（见 TD-14；TD-I-1 / TD-I-2 已由 Architect 于 architecture §12 裁定，不再是「需裁定」项）。
- **Basis（版本与上游依据）**：

| 对象 | 版本 / 状态 | 本 TD 的使用方式 |
| --- | --- | --- |
| `docs/product/requirements-v3.md` | **revision 13**（2026-10-26）；§24.5 CONFIRMED；§31 **T107–T116** CONFIRMED（**T114 已作编辑性澄清**：字段边界按等价性口径判定，见 §35.1 revision 13 记录）；修订后的 T28；§32 措辞 | 验收映射的唯一上游（TD-3） |
| `docs/features/F034/product.md` | v1（READY FOR ARCHITECT） | §3 验收映射、§4 边界与风险（文本/文件必须同结论） |
| `docs/features/F034/architecture.md` | **v1**（`READY FOR DESIGN`；**§12 定稿签核 2026-10-26 = `READY FOR IMPLEMENTATION`**，含 TD-I-1 / TD-I-2 裁定与 TD3-T115.5① 收窄要求） | §3 前端设计（载体模型/`importCarrier.ts` 接口/指纹/UI）、§8 验证策略与「Test 输入要点 1–8」、§9 R-1–R-11、§10 分工、§4 DR-F034-01–17（§12 已将原 PROPOSED 的实现选择提升为 CONFIRMED） |
| `docs/api/F014.md` §「CSV 文本载体（加法引用）」（增补节 v1） | **READY**（2026-10-26 签核生效；正文 v1 不变，附 3 条**解释性裁定附注**） | 见证 wire 形状与不变项，并作为实施/测试依据；解释性附注 1 = T114 按等价性口径、附注 2 = 制表符分隔的 `reason` 只固定类别、附注 3 = 表头级明细属既有 schema |
| `docs/api/F023.md` §「CSV 文本载体（加法引用）」（增补节 v1） | **READY**（同上，附 3 条解释性裁定附注） | 同上（26 列模板、§8 分组、§9 Network、§12 原子性不变） |
| 消费的既有 Contract | `docs/api/F014.md` v1（READY）、`docs/api/F023.md` v1（READY）、`docs/api/F027.md` v1（范围语义）、`docs/api/F002.md` | 上限 5,242,880 B / 5000 行 / 1000 预览；`IMPORT_INVALID_FILE.reason` 集合；`RowError` 形状；401/403；F027 行级范围拒绝 |
| 代码基线（只读核对） | `frontend/src/api/imports.ts`、`frontend/src/components/{importForm.ts,resourceInterfaceIpImportForm.ts,ResourceImportPanel.tsx,ResourceInterfaceIpImportPanel.tsx,ImportErrorsTable.tsx,ui/controls.tsx}`、`frontend/scripts/smoke-client.mjs`、`backend/app/api/v1/imports.py`、`backend/app/services/{resource_import.py,resource_interface_ip_import.py}`、`backend/tests/conftest.py`、`backend/tests/integration/{test_imports.py,test_import_tester_acceptance.py,test_f023_resource_interface_ip_import.py,test_import_performance.py,test_f027_access_scope.py}` | 判定可复用点、既有口径与实际可实现断言 |
| 规则 | `docs/project/handoff.md`、`docs/project/implementation-rules.md`、`AGENTS.md` §5–§9、`.pi/skills/data-integrity/SKILL.md`、`.pi/skills/frontend-ui/SKILL.md` | 交接/缺陷格式、验证纪律、完整性方法、前端可验证性 |
| 计划 | `docs/project/project-plan.yaml`（F034：`layers database=false / backend=false / frontend=true`，`api_required=true`，`implementation.test_design=PENDING`） | 层级一致 |

- **复用声明**：F014 / F023 的既有 import 集成套件（下称「既有导入套件」）作为**回归与口径参照**复用执行，但**不复用其 PASS 代替 F034 验收**；F034 的每条 T107–T116 均在 TD-3 独立映射到用例。F014/F023 历史 test/report 证据不改写。

### TD-2 层级记号与可验证性前提

| 记号 | 层次 | 载体 | 说明 |
| --- | --- | --- | --- |
| **U** | 纯逻辑单元 | `node`（type stripping 直接加载 `src/**/*.ts`，经 `frontend/scripts/smoke-client.mjs`；脚本无 DOM） | 断言 `importCarrier.ts` / `importForm.ts` / `resourceInterfaceIpImportForm.ts` 语义 |
| **M** | smoke-client 机制级 | 同上，`globalThis.fetch` 以受控响应替换 | 断言真实 `api/imports.ts` 的 `FormData`（`file` 的 `name`/`size`/`type`、`format`）与「不发请求」 |
| **I** | 真实后端集成 | pytest + **真实 PostgreSQL 16.15** + 真实 `create_app`/`TestClient` | 双载体同字节提交、等价性深比较、回滚/Audit/范围/权限/上限 |
| **H** | 真实 HTTP 直连测试栈（无浏览器） | Node 脚本 + `fetch` → `http://localhost:18080`（`-p csmtest`） | 用**真实前端载体原语** `pastedCsvFile()` 产出字节投给**真实服务端**，主要跑只读 `/validate` 与认证用例 |
| **S** | 静态核对 | `git diff` / `grep` / AST 级否定断言 | 零改动守卫、wiring、无 `crypto.subtle`、无 payload 持久化 |
| **B** | 浏览器 | 无框架（`frontend/package.json` 无 DOM/E2E 依赖；AGENTS §2.6 不新增） | 仅「人工留证」路径；Tester 不可执行 → 见 TD-12 |

**可验证性前提（如实声明）**：

1. **B 层不可由 Tester 执行**：仓库无 Playwright/Vitest/jsdom，本 Feature 不引入。因此 T107/T116 中「界面上真的能看到、真的点了会失效」这类断言只能由 S+M 组合证据 + 人工留证覆盖；无留证即 `NOT TESTED`，不得以构建通过宣称交互正确（`frontend-ui` SKILL.md「验证」节）。
2. **符号名以架构 §3.2 为准**：`pastedCsvFile` / `utf8ByteLength` / `isBlankImportText` / `importTextDigest` / `fileImportTargetKey` / `textImportTargetKey` / `parseImportFormValues` / `importCarrierPatch` 等为架构 v1 §3.2–§3.4 声明的接口。若实现采用等价改名，TEST 按**语义**断言（不因改名判 FAIL），但不得缺少同一组语义；改名或语义偏离须在报告登记。
3. **两层拼合成端到端等价链**（无浏览器）：U/M 证明「前端原语产出的字节 == corpus 文件字节」；I/H 证明「该字节经文本载体与文件载体提交得到逐字段相同响应」。两条链合起来即 §24.5「等价性」的可执行证据；缺口是「用户真实粘贴 → 文本域控件 → state」这一环，归 B 层（NOT TESTED 或人工留证）。
4. **服务端零改动是可验证事实**：`33d8a03..候选 HEAD` 中 `backend/app/**`、`backend/alembic/**` 必须空 diff（TD-REG.2）；因此任何「文件 vs 文本」差异都只可能来自前端构造字节，判据清晰。

### TD-3 验收映射（T107–T116 → 用例 ID / 层次 / 可观察断言）

记法：用例 ID = `TD3-<验收>.<序号>`；TEST 阶段逐条标 `PASS / FAIL / BLOCKED / NOT TESTED` 并附命令与证据路径。

#### T107 — 两入口并列载体、文件载体零回归

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T107.1 | S | `ResourceImportPanel.tsx` 与 `ResourceInterfaceIpImportPanel.tsx` 均存在：载体选择控件（`Select`，两项文案「上传文件（CSV / .xlsx）」「粘贴 CSV 文本（仅 CSV）」）+ 文件分支 `<input type="file">` 保留 + 文本分支 `TextArea`。禁止「删除文件输入或用文本域替换文件输入」（grep 命中数 ≥1 且 `<input` 命中 ≥1） |
| TD3-T107.2 | U | `importCarrierPatch(values,"text").format === "csv"`；`importCarrierPatch(textValues,"file").format === "csv"`（不回填 `xlsx`，DR-F034-07，架构 §12 已提升为 CONFIRMED）；两 form 模块各一组 |
| TD3-T107.3 | S | `frontend/src/api/imports.ts` diff **仅注释**（逐行 `+` 行 strip 后以 `*`/`//`/空开头）；`ImportErrorsTable.tsx`、`ui/controls.tsx`、`ResourcesPage.tsx` 空 diff |
| TD3-T107.4 | M | 模板表头生成函数输出逐字节不变：`buildTemplateCsv(BM)`/`buildTemplateCsv(VM)`/`buildResourceInterfaceIpTemplateHeaderCsv()` 与改造前基线（14 / 10 / 26 列列序）逐字节相等（守卫：F034 不得改模板） |
| TD3-T107.5 | U+M | 文件载体 `.xlsx` 路径仍在：`parse*` 对 `format="xlsx"` + 非 `.xlsx` 扩展名返回 `ok:false`（errors.file 含 `.xlsx` 说明）；`format="xlsx"` 且 `.xlsx` 名 → `ok:true`；M 层 `importResources(file,"xlsx")` 的 `FormData.format === "xlsx"` 与 F014 既有断言一致 |
| TD3-T107.6 | M | 既有 F014/F023 smoke 段全部保持 PASS（`npm run smoke:client` 0 failed，计数 == 基线 + F034 新增，新增用例名须逐一列出） |
| TD3-T107.7 | B | 两面板在浏览器中同时呈现两种载体、切换后结果区回空态 —— **无浏览器环境 → `NOT TESTED`**（降级证据：TD3-T107.1 + TD3-T107.2 + TD3-T116.4/6；人工留证可选） |

#### T108 — 合法文本两步流程与行号口径

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T108.1 | U+M | `pastedCsvFile(text)`：`name === "csm-pasted-import.csv"`（固定常量，不含时间戳/内容摘要）、`type === "text/csv;charset=utf-8"`、`size === utf8ByteLength(text)`、`await file.text() === text`；写入 `FormData` 后 `get("file") instanceof File`、`get("format") === "csv"`、未手工设置 `Content-Type` |
| TD3-T108.2 | I | 合法文本（F-01 BM / F-02 VM / F-03 26 列混排）→ `POST /validate` 200，`format="csv"`，`total_rows` / `importable_rows` / `error_count` 逐值等于期望（如 2/2/0） |
| TD3-T108.3 | I | 含错误行（`error_count>0`）时写入端点仍整批拒绝：422 `IMPORT_VALIDATION_FAILED`，`details.error_count` 与预校验一致，DB 计数不变 |
| TD3-T108.4 | U+M | 门控：F023 `canConfirmResourceInterfaceIpImport` — `validated=null`→false；`errorCount=1`→false；`validatedKey !== currentKey`→false；`validatedKey===currentKey && errorCount===0 && !importSucceeded`→true；F014 面板内联判据（S：`error_count === 0 && validatedKey === currentKey`）存在且未被削弱 |
| TD3-T108.5 | I | **写入时重新校验同一内容**：`/validate` 通过 → 外部建同 `(cluster,hostname)` 冲突 → 以**同字节**文本写入 → 422 + 零残留（resources / `*_details` / audit_logs 计数与基线相等） |
| TD3-T108.6 | I | 行号口径：表头为第 1 行；第 3 个数据行错误 → `errors[].row === 3`；与文件载体同值 |
| TD3-T108.7 | I | 同一内容连续两次 `/validate` → 响应体 `json` 深比较相等，且无写副作用（资源/Audit 计数不变） |
| TD3-T108.8 | I | 26 列写入成功信封：`created` / `total_rows` / `interfaces_created` / `ip_addresses_created` 与文件载体逐字段相等（文本载体不改变成功响应形状） |

#### T109 — 行错误同形状同内容、不 fail-fast

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T109.1 | I | 错误矩阵（F-20）：非法枚举、非法整数、长度 >255、批内重复（含 `related_row` 指首现行）、现存冲突、集群范围外 —— 每条 `RowError` 四字段齐备且类型正确（`row` int、`field` 为模板列名、`reason` 非空 str、`related_row` int 或 null） |
| TD3-T109.2 | I | **不 fail-fast**：同一请求中 ≥3 类错误同时出现在 `errors`（`error_count` == 期望条数，`errors` 条数 == min(error_count, 1000)），且 `importable_rows === total_rows − 出错行数` |
| TD3-T109.3 | I | F023 变体：`(cluster,ip)` 批内重复（`related_row`）、Network 无法解析（`field="network"`）、行类型适用性冲突（`field` 为该列名）同形状出现 |
| TD3-T109.4 | I | 每条错误响应与文件载体响应 `json` 深比较相等（等价性，TD-5） |

#### T110 — 空 / 纯空白 / 仅表头

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T110.1 | U+M | `parse*` 对 `""`、`"   "`、`"\n\n"`、`" \t\r\n "` 返回 `ok:false` 且 `errors.text` 非空（两个模块各 4 条） |
| TD3-T110.2 | M | 上述 4 条均 **不发请求**：`calls.length === 0`（无 fetch 调用、无重试） |
| TD3-T110.3 | I | 仅表头文本（BM 14 列 / 26 列各一，`F-06`）→ 422 `IMPORT_INVALID_FILE`，`details.reason === "empty_file"` |
| TD3-T110.4 | I | 两种情况后全表计数不变：`resources`、`bare_metal_details`、`virtual_machine_details`、`interfaces`、`ip_addresses`、`audit_logs`（无写入、无 Audit 残留） |
| TD3-T110.5 | I | 边界观察（不作 T110 判据）：`,` 或 `\n` 等非空白但无有效表头（`F-05b`）→ 422 `header_missing`；与文件载体一致 |
| TD3-T110.6 | U+I | 仅 BOM 文本 `"\uFEFF"`（`F-24`）：允许「本地拦截、不发请求」或「服务端 422 empty_file」**二者之一**，不得写入（记录实际分支，见 TD-I-5） |

#### T111 — UTF-8 字节上限与行数上限

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T111.1 | U | `utf8ByteLength` 与 `new TextEncoder().encode(s).length` 对 ASCII / 中文（3 字节）/ emoji（4 字节，代理对）/ 混合串逐例相等；至少 1 例证明 `utf8ByteLength(s) !== s.length` |
| TD3-T111.2 | U | 严格大于口径：UTF-8 字节 == **5,242,879** → `ok:true`；== **5,242,880** → `ok:true`；== **5,242,881** → `ok:false`（errors.text 含上限值与「不发请求」语义）。构造成本用一行表头 + 填充行实现，仅为本地 gate，不发请求 |
| TD3-T111.3 | U | **反空洞（R-2）**：构造 `s.length < 5,242,880` 但 UTF-8 字节 > 5,242,880（多字节填充，如 `"中".repeat(k)` 前缀+精确补齐）→ 必须 `ok:false`。若实现用字符数计量，此条必 FAIL |
| TD3-T111.4 | M | 超限时无请求：`calls.length === 0` |
| TD3-T111.5 | I | 服务端字节口径一致：monkeypatch `import_max_file_bytes` 为小值（如 200，复用 F014 既有 pattern），文本字节 = limit+1 → 413 `IMPORT_FILE_TOO_LARGE` 且 `details.limit_bytes == limit`；字节 == limit 且内容合法 → **非 413**。理由：仅注入配置数值，不改被测比较代码路径（服务端零改动），且避免 5 MiB 真实载荷。5 MiB 端到端真实请求记 `NOT TESTED`（TD-12） |
| TD3-T111.6 | I | 行数上限权威：**5001** 数据行文本（`F-23`）→ 413 `IMPORT_ROW_LIMIT_EXCEEDED`、`details.limit_rows == 5000`；DB 计数不变（无部分导入） |
| TD3-T111.7 | I | 读侧边界：**5000** 数据行文本 `/validate` → 200、`total_rows == 5000`、`errors_truncated === true`、`errors.length == 1000`（错误矩阵用不存在的 cluster，使 5000 行全部产生行错误，避免建 5000 条真实资源） |
| TD3-T111.8 | S+M | 行数不在前端镜像：`parse*`/`importCarrier.ts` 源码对 `IMPORT_MAX_ROWS` 引用命中 **0**；M：5001 行的**小字节**文本（如空值行）`parse*` 仍 `ok:true`（不在本地拦截） |
| TD3-T111.9 | I | 非 ASCII 端到端：含中文 + emoji 字段值文本（`F-26`）→ 200、`error_count == 0`；`utf8ByteLength(text)` 与 `File.size` 相等；写入后回读字段值与原文逐字节相等（UTF-8 往返不变） |

#### T112 — 表头严格性（不补、不重排、不嗅探、不折叠）

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T112.1 | I | 缺表头（首行为空行或数据行，`F-15`）→ 422 `IMPORT_INVALID_FILE`、`reason === "header_missing"` |
| TD3-T112.2 | I | 缺列（去 `hostname`，`F-16`）→ 422、`reason === "missing_columns"`、`details.missing_columns === ["hostname"]`（26 列模板另一例） |
| TD3-T112.3 | I | 多余未定义列（追加 `interface_name`，`F-17`）→ 422、`reason === "unknown_columns"`、`details.unknown_columns === ["interface_name"]` |
| TD3-T112.4 | I | 列序不符（完全逆序 `F-18a`、仅交换前两列 `F-18b`）→ 422、`reason === "column_order"`；**不得 200、不得按名重排** |
| TD3-T112.5 | I | 不做大小写折叠（`HOSTNAME` 替 `hostname`，`F-19`）→ 422；`reason ∈ {missing_columns, unknown_columns}`，**不得为 200/201** |
| TD3-T112.6 | I | 制表符分隔（`F-14`，每行 `\t` 连接、内容其余同 `F-01`）→ 422 `IMPORT_INVALID_FILE`，`reason ∈` 已签核集合（契约仅固定**类别集合**，不固定具体取值，见 TD-I-2 裁定），且无写入 |
| TD3-T112.7 | I | 不自动补表头：仅数据行文本 → 422（同 TD3-T112.1）且**不得以人工补出的表头解析成功** |
| TD3-T112.8 | I | 以上每条均双载体提交并深比较响应（等价性） |

#### T113 — BOM / 行尾 / 尾部空行

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T113.1 | U+M | 文本无 BOM 时 `pastedCsvFile` 生成字节的首三字节 ≠ `EF BB BF`（前端**不添加** BOM）；payload 不做 trim（首尾字节保留，含尾部换行） |
| TD3-T113.2 | I | 文本以 `U+FEFF` 开头（`F-07`）→ 与「同字节含 BOM 的 `.csv` 文件」响应逐字段相等；表头首列不被污染（`F-01` 与 `F-07` 的 `total_rows`/`error_count`/`errors` 相同，`resource_type` 等枚举不错位） |
| TD3-T113.3 | I | CRLF（`F-08`）/ LF（`F-01`）/ 混用（`F-09`）三份同逻辑内容 → `total_rows` 与 `errors[].row` 完全一致；且各自与文件载体一致 |
| TD3-T113.4 | U+M | 不做本地归一化：`pastedCsvFile("a,b\r\nc,d\r\n").arrayBuffer()` 与源串 UTF-8 字节**逐字节相等**（CRLF 未被改写为 LF，未补尾部换行，未转义） |
| TD3-T113.5 | I | 尾部空行 / 尾部换行（`F-10`，尾随 3 个空行 + 末尾换行）→ `total_rows` 与 `F-01` 相同；第 3 个数据行错误仍报 `row === 4`（真实数据行号不移动） |

#### T114 — CSV 字段边界

> **口径（v1.1 落定）**：requirements revision 13 §31 T114 已作**编辑性澄清** —— 原表述「引号未闭合等字段边界错误按既有文件级错误呈现，不静默修补」澄清为「与既有文件载体同口径（等价性）：逐字节相同的 CSV 经两种载体提交，行为、错误码与行号完全一致；既有 CSV 解析行为不变，本 Feature 不新增字段边界错误判定」。裁定见 `docs/features/F034/architecture.md` §12（TD-I-1）与两份契约增补节「解释性裁定附注 1」。本组用例一律按**等价性**判定，**不要求 422**。

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T114.1 | I | 含逗号字段（引号包裹 `"Dell, Inc."`，`F-12`）→ 解析值不改写：预校验 `error_count === 0`；写入后回读 `manufacturer === "Dell, Inc."` |
| TD3-T114.2 | I | 含双引号转义（`"Manu""facturer"`）→ 回读值 `Manu"facturer`（标准 CSV 解转义，非静默改写原文） |
| TD3-T114.3 | I | 引号内换行（`F-11`）→ `total_rows` 按**逻辑记录**计（2 条数据），后续错误行 `row === 3`（表头 1 行 + 逻辑记录 1 行） |
| TD3-T114.4 | I | 未闭合引号（`F-13`）→ **已由 Architect 裁定（architecture §12）：T114 按等价性口径判定，不要求 422**。**PASS 判据** = 同一字节（逐字节相同）经文本载体与文件载体提交后 `status` 相等 **且** 响应体深比较一致；同时**实际观测如实记录**（`status`、`status_code`、`total_rows`、`error_count`、`details.reason`（若有）、行为描述）。**不得**以「未返回 422」判 FAIL；仅当两载体出现差异时才判 FAIL |
| TD3-T114.5 | U+S | 前端不解析 CSV：`pastedCsvFile` 对含引号/换行文本逐字节原样（无转义、无重排、无 `trim`）；载体模块内无 CSV 解析实现（`split(",")` / `split(/\r?\n/)` / 引号状态机等命中 **0**） |

#### T115 — 权限 / 集群范围 / Audit / 不留痕

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T115.1 | I | VIEWER 会话：两入口 `/validate` 与写入端点均 403 `FORBIDDEN{reason:"permission"}`（文本字节 + 固定文件名，4 次请求全 403） |
| TD3-T115.2 | I | 未认证（无 Cookie / 无 API Key）：两入口两端点均 401 `AUTH_REQUIRED`，且 401 先于 403 |
| TD3-T115.3 | I | 含未授权集群行（F027 形状，`F-20` 范围内）：`/validate` 200、`errors[0].row` 正确、`field === "cluster"`、响应体不含该未授权 Cluster 码（不泄露）；写入 → 422 整批失败 + 零残留（resources/audit 计数不变） |
| TD3-T115.4 | I | 成功写入 Audit 同口径：每成功对象恰 1 条 `CREATE`；`operator` 为当前用户；Audit 字段集合与文件载体同一用例逐字段相等（除 `id`/时间戳/id 类按既有比较口径归一） |
| TD3-T115.5 | I | 不留痕（DB 与响应）：以唯一标记 `F034-MARKER-<uuid>` 作为某合法字段值写入；①错误响应体不**回显整段**粘贴内容（不出现整段 CSV 原文；表头级 `details.unknown_columns` / `missing_columns` 属 F014/F023 §1.2 **既有 schema**，两载体逐字段相同，**不得**据此判 FAIL——依据契约增补节「解释性裁定附注 3」与 architecture §12）；②`audit_logs` 全表不出现「整段 CSV 原文」子串；③库里不存在新增的导入暂存/临时表（`pg_tables` 对比基线集合） |
| TD3-T115.6 | I+H | 日志不留痕：同一标记文本请求后 `docker logs csmtest-backend-1 --since <ts>`（或 pytest `caplog`）中 marker 命中 **0** |
| TD3-T115.7 | S | 前端不持久化 / 不泄出：`importCarrier.ts`、两 form、两 panel 中 `localStorage` / `sessionStorage` / `document.cookie` / `console.log|warn|error` 引用命中 **0**（既有非 payload 用途如无则一并 0）；载体不把内容拼进 URL/查询串（`grep` 命中 0） |
| TD3-T115.8 | B | 真实浏览器 storage/console/network 面板核对 → **`NOT TESTED`**（无浏览器栈）；降级证据 = TD3-T115.7 静态断言 |
| TD3-T115.9 | I | 「不落盘」边界如实：≤1 MiB 路径断言「应用层无残留临时文件/记录」（对比既有测试栈目录与 DB 无新增）；>1 MiB 由 Starlette 溢写匿名临时文件属既有边界（架构 ON-2）→ **不声称全路径不落盘**，该子项记 `NOT TESTED`（不是缺陷） |

#### T116 — 陈旧结果防护

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-T116.1 | U | 改 1 字符必换指纹：至少 6 组（首字符、中间、末字符、增/删空格、中文 1 字替换、emoji 替换）→ `textImportTargetKey` 前后不相等 |
| TD3-T116.2 | U | 稳定性与载体隔离：同一 `text` 两次调用相等；file 载体 key 以 `file:` 开头、text 载体以 `text:csv:` 开头；**同一字节**在两种载体下 key **不相等**（载体维度确实进入指纹） |
| TD3-T116.3 | U | payload 不 trim 的守卫：`"a,b\n"` vs `"a,b \n"` vs `"a,b\n\n"` 三者 key 两两不相等 |
| TD3-T116.4 | U+S | 切载体失效：`importCarrierPatch` 产出新 values，其 key ≠ 切换前 key；面板 `changeInput`（载体/格式/文件/文本任一变化）重置 `localErrors={}`、`validateState=idle`、`importState=idle`、`validatedKey=null`（S：重置语句命中，且四条 input 均走 `changeInput`） |
| TD3-T116.5 | S+U | format 分支：text 载体下 format `Select` 有 `disabled`（S）；`parse*` 对 `carrier="text" && format!=="csv"` 返回 `ok:false`（防御分支，U）；file 载体 `format` 变化 → key 变化（U）。注：text 载体下 UI 无法切 format（DR-F034-07），故「切 format」在文本载体上是**不可达路径**，以防御断言 + `disabled` 静态证据覆盖，不伪造浏览器操作 |
| TD3-T116.6 | U/M | 门控失效：`validatedKey !== currentKey` → `canConfirm*` false；F014 内联判据同义（S+U）；`importState.kind === "success"` 后不可再确认 |
| TD3-T116.7 | I | 同一内容重复预校验一致、无副作用（= TD3-T108.7） |
| TD3-T116.8 | I | 服务端兜底不依赖前端指纹：预校验通过后外部状态变化 → 同字节写入被 422 拒绝（= TD3-T108.5） |
| TD3-T116.9 | B | 浏览器中「文本域编辑 → 结果区立即失效 → 确认导入变灰」→ **`NOT TESTED`**（无浏览器）；降级证据 = TD3-T116.1/4/6 |

#### 回归与零改动守卫（T27 / T28 / T72 / T89 + `layers` 一致性）

| ID | 层 | 可观察断言 |
| --- | --- | --- |
| TD3-REG.1 | S | `git diff --name-only 33d8a03..候选HEAD` ⊆ 白名单：`docs/features/F034/*`、`docs/api/F014.md`、`docs/api/F023.md`、`docs/project/project-plan.yaml` + 派生视图、`frontend/src/components/{importCarrier.ts,importForm.ts,resourceInterfaceIpImportForm.ts,ResourceImportPanel.tsx,ResourceInterfaceIpImportPanel.tsx}`、`frontend/src/index.css`、`frontend/scripts/smoke-client.mjs`、`backend/tests/integration/test_f034_csv_text_carrier.py`（Tester 新建）；任何额外文件须解释 |
| TD3-REG.2 | S | `backend/app/**` 与 `backend/alembic/**` 空 diff（服务端与 Schema 零改动 = `layers.backend=false` / `database=false` 的直接证据） |
| TD3-REG.3 | S | `frontend/src/api/imports.ts` diff 仅注释；导出符号集合与签名不变（`typecheck` + smoke 导入即证） |
| TD3-REG.4 | S | `ui/controls.tsx`、`ImportErrorsTable.tsx`、`ResourcesPage.tsx`、`describeImportError` 空 diff |
| TD3-REG.5 | S | `frontend/package.json` 无新增依赖/脚本、`package-lock.json` 无新增包（diff 空或仅描述性变更） |
| TD3-REG.6 | S | 无 `crypto.subtle`（命中 0）；`importCarrier.ts` 无 React/antd/JSX 依赖（可被 Node type stripping 加载；`import type` 之外无 import 除 `api/imports.ts` 常量） |
| TD3-REG.7 | I | 既有导入套件全 PASS：`test_imports.py`、`test_import_tester_acceptance.py`、`test_f023_resource_interface_ip_import.py`、`test_import_constraints.py`、`test_import_performance.py`（可选：耗时）与 `test_f027_access_scope.py` 的导入用例；0 failed |
| TD3-REG.8 | M | 前端：`npm run typecheck` exit 0；`npm run build` exit 0；`npm run smoke:client` **0 failed**，计数 == **基线 328** + F034 新增数（TD 编写时于 `bbc9e91` 只读复现的基线为 `328 passed, 0 failed`）；新增用例名逐条列出并映射 T107–T116 |
| TD3-REG.9 | P | 项目状态一致性：`python3 scripts/validate_project_state.py` → `PROJECT STATE VALID`；`python3 scripts/render_project_views.py`（**不带 `--write`**）→ `PROJECT VIEWS VALID`（结构通过不等于批准或 Git 证据有效） |

### TD-4 边界与异常场景夹具清单（corpus）

夹具为**文本 + 期望**清单；每份同时存在逐字节相同的 `.csv` 文件（构造见 TD-8）。`BM` = F014 14 列表头，`VM` = F014 10 列表头，`W26` = F023 26 列表头。

| ID | 内容 / 构造 | 字节特征 | 期望（文本载体） | 期望（文件载体） |
| --- | --- | --- | --- | --- |
| F-01 | `BM` + 2 条合法 BM 行，LF | UTF-8 无 BOM | 200；`total_rows=2,importable_rows=2,error_count=0` | 同 |
| F-02 | `VM` + 1 条合法 VM 行（`host` 为批外已存在 BM） | 同 | 200；`error_count=0` | 同 |
| F-03 | `W26` + BM/VM 混排 2 行（不同 `(cluster,ip)`、同一资源多 IP 混合） | 同 | 200；分组响应字段齐备 | 同 |
| F-04 | `""`（0 字节） | 0 字节 | **本地拦截**，不发请求 | 文件载体：0 字节 → 422 `empty_file`（层不同，记录） |
| F-05 | `"   "`、`"\n\n"`、`" \t\r\n "` | 纯空白 | **本地拦截**，不发请求 | 文件载体 → 422 `header_missing`/`empty_file`（记录差异层） |
| F-05b | `",,,\n"`、`"\nN96P,cn001,BARE_METAL\n"` | 非空白、无有效表头 | 422 `header_missing` | 同 |
| F-06 | 仅表头（`BM` 一份、`W26` 一份，无数据行） | | 422 `IMPORT_INVALID_FILE{empty_file}` | 同 |
| F-07 | `U+FEFF` + `F-01` | BOM 前缀 EF BB BF | 200，同 `F-01` | 同 |
| F-08 | `F-01` 全部行尾改 CRLF | CRLF | 200，同 `F-01` | 同 |
| F-09 | `F-01` 混用行尾（表头 CRLF、第 1 行 LF、第 2 行 CRLF） | 混合 | 200，`total_rows` 与 `error_count` 同 `F-01` | 同 |
| F-10 | `F-01` + 尾部 3 个空行 + 末尾换行 | 尾随空记录 | 200，`total_rows=2`，错误行号不移动 | 同 |
| F-11 | `manufacturer` 为引号内换行 `"Manu\nal"`；第 2 条数据行 `hostname` 非法 | 引号内 `\n` | 200；`total_rows=2`；`hostname` 错误 `row=3` | 同 |
| F-12 | `"Dell, Inc."`、`"Manu""facturer"` | 逗号 + 双引号转义 | 200；回读值不改写 | 同 |
| F-13 | 末字段引号未闭合（`…,"Manu`） | 未闭合引号 | **等价性判据**（Architect §12 已裁定：按等价性判定、**不要求 422**，见 TD-I-1）；实际观测照录 | 同 |
| F-14 | `F-01` 的逗号全替换为 `\t` | 制表符分隔 | 422 `IMPORT_INVALID_FILE`（reason ∈ 集合），无写入 | 同 |
| F-15 | 首行为数据行（无表头） | | 422 `header_missing` | 同 |
| F-16 | `BM` 去 `hostname`（`W26` 去 `ip`） | | 422 `missing_columns` + 列表精确 | 同 |
| F-17 | `BM` 追加 `interface_name`（`W26` 追加 `hardware_model`） | | 422 `unknown_columns` + 列表精确 | 同 |
| F-18 | (a) 表头完全逆序 (b) 仅交换前两列 | | 422 `column_order` | 同 |
| F-19 | `HOSTNAME` / `Cluster` 大小写变形 | | 422（reason ∈ `{missing_columns,unknown_columns}`），不得 200 | 同 |
| F-20 | 6 类行错误矩阵：`role=FOO`、`memory_mb=abc`、`manufacturer` 256 字符、批内重复 `hostname`（含 `related_row`）、现存冲突 `hostname`、未授权/不存在 cluster | | 200 + 全量 `errors`（不 fail-fast） | 同 |
| F-21 | 字节边界三份：UTF-8 字节 **5,242,879 / 5,242,880 / 5,242,881**（表头行 + ASCII 填充行） | 仅本地 gate 断言 | `ok:true / ok:true / ok:false`（严格大于） | 文件载体侧改由 TD3-T111.5 的小 limit 注入验证 |
| F-22 | 多字节反空洞：`"中".repeat(k)`（使 `length < limit` 但字节 > limit） | | `ok:false`（若按字符数计量必 FAIL） | — |
| F-23 | 行数边界：**5001** 行（任意可解析表头 + 5001 数据行）；**5000** 行（数据行全部 `cluster` 不存在） | | 5001 → 413 `IMPORT_ROW_LIMIT_EXCEEDED` + 零残留；5000 → `/validate` 200、`total_rows=5000`、`errors_truncated=true`、`errors.length=1000` | 同 |
| F-24 | 仅 `U+FEFF` | BOM 单字符 | 本地拦截 **或** 422 `empty_file`（二者之一，无写入；见 TD-I-5） | 文件载体 422 |
| F-25 | `F-01` 加唯一标记 `F034-MARKER-<uuid>`（落在合法字段） | 留痕探针 | 写入成功；响应/日志/Audit 不含整段原文 | 同 |
| F-26 | 中文字段值 + emoji（`manufacturer="戴尔, Inc."`、`gpu_model="A100-🚀"`） | 非 ASCII | 200；回读逐字节不变；`File.size == utf8ByteLength(text)` | 同 |

**场景覆盖对照**（任务清单 → 夹具）：空/纯空白 `F-04`/`F-05`；仅表头 `F-06`；BOM `F-07`/`F-24`；CRLF/LF/混用 `F-01`/`F-08`/`F-09`；尾部空行 `F-10`；引号内换行 `F-11`；未闭合引号 `F-13`；制表符分隔 `F-14`；缺表头 `F-15`；列序交换 `F-18`；多余列 `F-17`；字节 −1/=/+1 `F-21`；5000/5001 行 `F-23`；非 ASCII 字节计量 `F-22`/`F-26`；陈旧结果三分支 `TD3-T116.1/4/5`。

### TD-5 等价性判据（F034 的核心判据）

需求 §24.5 把「等价性」定为 CONFIRMED：**逐字节相同的 CSV 字节，经两种载体提交，行为与错误完全一致**。F034 不改服务端，因此该判据可机械执行：

1. **字节层（U/M）**：`Buffer.from(text,"utf8")` 与 corpus `.csv` 文件字节 `compare === 0`；`pastedCsvFile(text)` 的 `arrayBuffer()` 与之 `compare === 0`。
2. **响应层（I）**：对**每一份** corpus（`F-01`–`F-26` 全部适用者），分别以
   - 文件载体：`files={"file": ("resources.csv", bytes, "text/csv")}`，`data={"format":"csv"}`
   - 文本载体：`files={"file": ("csm-pasted-import.csv", bytes, "text/csv;charset=utf-8")}`，`data={"format":"csv"}`

   提交同一端点，断言 **status 相等 且 `resp.json()` 深比较相等**（`format` 回显、`total_rows`、`importable_rows`、`error_count`、`errors` 全字段、`errors_truncated`、`IMPORT_INVALID_FILE.details` 的 `reason`/`missing_columns`/`unknown_columns`、`IMPORT_*` 的 `details` 常量）。
3. **写入层（I）**：成功路径断言 `201` 返回体逐字段相等（`created`/`total_rows`/`interfaces_created`/`ip_addresses_created`），且两次运行的 Audit 计数相等（用不同 fixture 数据避免互相冲突）。
4. **H 层补充**：Node 用真实 `pastedCsvFile()` 直连 `http://localhost:18080` 打 `/validate`（只读），响应与同一字节的 Python 结果逐字段相等；证明「真实前端产物 + 真实部署」同口径。

任一层出现差异即判 **FAIL**（产品 §4：任何「文件失败、文本成功」或反向差异都视为缺陷），即使差异看起来"更宽容"也不接受。

### TD-6 并发与原子性场景

| ID | 层 | 断言 |
| --- | --- | --- |
| TD3-ATOM.1 | I | **整批回滚无残留（文本载体）**：F014 3 行含 1 个不存在 cluster → 422；`resources`/`bare_metal_details`/`audit_logs` 计数与基线相等（复用 `_counts` 口径）；F023 变体断言 `interfaces`/`ip_addresses` 同样零残留 |
| TD3-ATOM.2 | I | **重复导入整批拒绝**：同字节文本先成功 201 → 立即再写入 → 422 `IMPORT_VALIDATION_FAILED`（`(cluster,hostname)` 或 `(cluster,ip)` 现存冲突），零新增、Audit 不增；不静默覆盖、无 UPDATE Audit |
| TD3-ATOM.3 | I | **集群范围外行整批失败**：非 ADMIN 仅授权 A/B，文本含 C 集群行 → `/validate` 200 且 `row`/`field="cluster"` 正确、响应不含 C 码；写入 422、零残留（TD3-T115.3 的实现主体） |
| TD3-ATOM.4 | I | **并发同字节提交**（HTTP 级真并发）：两个独立 EDITOR `TestClient` + `threading.Barrier(2)`、`join(timeout=30)` 且两线程 `not is_alive()`，同时写入同一 hostname 文本批 → ①恰一方 201；另一方 4xx（F014 路径要求 422 `IMPORT_VALIDATION_FAILED`，**出现 500 视为 FAIL 并记缺陷**；F023 路径允许契约 §12.4 的 500 `INTERNAL_ERROR` 兜底但不静默重试，须记录）；②DB 该 hostname 行 == 1、无重复、Audit 数 == 成功对象数；③记录请求时间区间是否相交（至少 1 次相交；未相交则允许换新 hostname 重试 ≤3 次并写明尝试次数） |
| TD3-ATOM.5 | I+M | **本地拦截零副作用**：`F-04`/`F-05`/`F-21` 超限三类均 `calls.length === 0`（无请求、无重试），DB 计数不变 |
| TD3-ATOM.6 | I | **超限无部分导入**：`F-23` 5001 行 413 后计数不变（与 TD3-T111.6 合并执行） |

### TD-7 环境与可执行命令

**TD 阶段只读核对到的环境事实（2026-10-26）**

| 项 | 事实 | 核对方式 |
| --- | --- | --- |
| 测试栈 | `-p csmtest` 四容器 Up/healthy（`csmtest-{db,backend,frontend,nginx}-1`）；`GET http://localhost:18080/api/v1/health` → **200** | `docker ps`、`curl` |
| 测试栈 DB | `csmtest-db-1` 的 `5432/tcp` **未映射到宿主**（H 层只能走 HTTP，不能直连该库） | `docker inspect` |
| 后端集成 PG | 本地独立测试实例 `postgres:16`（容器 `csm-f026-pg`，`127.0.0.1:55432`），库 **`csm_test`** 可连（`PostgreSQL 16.15`）；`conftest._require_test_database_url` 强制库名含 `test` 且 ≠ `DATABASE_URL`（DB-D10） | 只读 `psycopg` 连接 + `conftest.py` 源码 |
| 账号 | `admin` / `testadmin`（`.env.test` 的 `INITIAL_ADMIN_*`；`.env.test` 被 gitignore，凭据不进报告与日志） | `.env.test`（只读） |
| 工具链 | Node **v22.23.3**（原生 `File`/`FormData`，可 type stripping 加载 `.ts`）；Python **3.12.7**；pytest **7.4.4**；SQLAlchemy **2.0.34**；`frontend/node_modules` 就绪 | 命令输出 |
| 缺失 | 无浏览器/DOM 框架（`package.json` 无 Playwright/Vitest/jsdom）；宿主无 `psql` 客户端 | 文件 + `which` |
| 前端基线 | `npm run smoke:client` = **328 passed / 0 failed**（`bbc9e91`，实现前基线） | 实际运行（只读，不改文件） |
| 工作区 | `git status --porcelain=v1 -uall` 为空（TD 编写前） | `git status` |

**命令（TEST 阶段执行；日志归档到 `docs/features/F034/artifacts/`，写权已确认，见 TD-14「TEST 阶段文件所有权」）**

1. 前端三项（必跑）：`cd frontend && npm run typecheck && npm run build && npm run smoke:client`
2. 后端定向（真实 PG，F034 新增文件）：
   `cd backend && TEST_DATABASE_URL=postgresql+psycopg://csm:<本地测试口令>@127.0.0.1:55432/csm_test PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/integration/test_f034_csv_text_carrier.py`
3. 后端回归（既有导入套件 + 范围）：
   `… python3 -m pytest -q -p no:cacheprovider tests/integration/test_imports.py tests/integration/test_import_tester_acceptance.py tests/integration/test_f023_resource_interface_ip_import.py tests/integration/test_import_constraints.py tests/integration/test_f027_access_scope.py`
4. 收集数核对：同上加 `--collect-only`（记录新增用例数与名称）
5. H 层真实 HTTP（Node 脚本，只用只读 `/validate` 与认证）：
   `node docs/features/F034/artifacts/f034-live-validate.mjs`（登录 `admin` → 取 Cookie → 以 `pastedCsvFile()` 产物 POST `/api/v1/imports/resources/validate` 与 `/api/v1/imports/resource-interface-ips/validate`）
6. 日志留痕核对：`docker logs --since <ts> csmtest-backend-1 2>&1 | grep -c F034-MARKER`（期望 0）
7. 静态与范围守卫：`git diff --stat 33d8a03..<候选 HEAD>`；`git diff --name-only …`；`git diff … -- backend/app backend/alembic`（期望空）；`git diff … -- frontend/src/api/imports.ts`（仅注释）；`git diff … -- frontend/package.json`；`grep -rn "crypto.subtle\|localStorage\|sessionStorage" frontend/src/components/importCarrier.ts …`
8. 计划一致性：`python3 scripts/validate_project_state.py`；`python3 scripts/render_project_views.py`（不带 `--write`）

**写入路径纪律**

- **真实写入只在 `csm_test`（pytest）**：每会话 fixture 重建 `public` + `alembic upgrade head`，函数级事务回滚，`committed_engine` teardown `TRUNCATE` 除 `alembic_version` 外全部表；不在生产库/未知库执行。
- **`csmtest` 测试栈只用只读 `/validate` 与认证**（T115.1/2 亦可），不向该库写入业务数据；若必须写（不计划），须先记录基线计数并在结束后核对归零。
- 所有用例自建数据（`make_user` / 唯一 cluster code 前缀 `F034`），禁止复用其它用例的 Cluster code 或依赖执行顺序。

### TD-8 夹具构造与数据清理策略

1. **语料单一来源，避免跨语言漂移**：`F-01`–`F-26` 以 `.txt`（UTF-8 无 BOM，除 `F-07`/`F-24` 显式带 BOM）存放于 `docs/features/F034/artifacts/corpus/`；`.csv` 对照文件由 Node 侧 `Buffer.from(text,"utf8")` **写一次**生成（`F-xx.csv`）。
   - Python 侧「文本载体」= `Path(f).read_bytes().decode("utf-8")` 再 `encode("utf-8")`（对合法 UTF-8 恒等，含 `U+FEFF` 首字符亦然）；「文件载体」= 直接读 `.csv` 字节。二者同源，天然逐字节相同。
   - Node 侧断言 `Buffer.compare(Buffer.from(text,"utf8"), csvBytes) === 0`，闭合 TD-5 第 1 层。
2. **二进制/边界夹具程序化生成**（不入库语料）：`F-21`/`F-22` 的精确字节数由 `"a".repeat(n)` 与 `"中".repeat(k)` + 精确补齐构造，断言前先校验 `utf8ByteLength` 实得值（避免"以为造对了"）。
3. **不写业务库即可验证的部分（优先）**：字节计量、指纹、门控、本地拦截、模板表头守卫、无 `crypto.subtle`、无 payload 持久化、`FormData` 形状 —— 全部为 U/M/S 层，零 DB 接触。
4. **必须写入时的受控数据与清理**：写入类用例（T108.5/8、T109、T110.4、T111.6、T115.3–5、ATOM.1/2/4）一律在 `csm_test`，用 `auth_session_factory` 真提交、`committed_engine` teardown `TRUNCATE`；每例前置记录 `_counts`（resources / `*_details` / interfaces / ip_addresses / audit_logs）并在断言后复核，禁止跨用例共享 hostname/IP。
5. **`csmtest` 栈不产生业务数据**：H 层只打 `/validate`；登录只产生会话（无 Audit 业务对象）。若登录残留 session 行，记录并说明属既有 F002 行为、非 F034 写入。
6. **语料与 artifact 的版本库状态**须在 TEST 阶段核实（F030 TE-8 同源注意事项：`.gitignore` 可能忽略 `*.log`），报告须写明哪些证据文件被忽略、哪些需由协调器决定是否纳入。

### TD-9 PASS / FAIL 判定标准

| 判定 | 定义 |
| --- | --- |
| **PASS** | 该用例的**全部**断言在执行证据中成立；证据可定位（命令 + 日志/文件 + 用例名）；不依赖其它用例的残留状态 |
| **FAIL** | 任一断言不成立（含「文件与文本结论不一致」「字段/类型/枚举值不符」「计数出现残留」「应为 422 实为 200」「应为 200 实为 422/500」）；须给出可复现步骤 |
| **BLOCKED** | 缺少必要输入（如契约增补节仍未签核为 READY、实现未完成、文件写权未划）或环境不可用；不得降级为 PASS |
| **NOT TESTED** | 无执行条件（无浏览器、无 E2E 框架、成本与收益不匹配、明确不在范围），须写原因与替代证据边界 |

专有判据：

- **等价性判据（强制）**：`F-01`–`F-26` 中适用的每一份语料，文件载体与文本载体的 **status + 响应体深比较必须完全一致**。任一不一致 → 该语料用例 FAIL（即使差异方向"更宽容"）。
- **不可用环境时的替代证据边界**：B 层（浏览器）不可执行时，只能以「S 静态断言 + M 机制断言」作为**部分**证据，验收项标 `NOT TESTED`（或人工留证后标 PASS 并注明证据来源与执行人）；构建/类型检查通过**不得**替代交互验证。
- **不得复用旧结论**：F014/F023 的既有 PASS 只作为回归与口径参照；T107–T116 每条须有 F034 阶段的独立执行证据。
- **TEST 阶段前置条件**（不满足则相关项 BLOCKED，不得直接判实现 FAIL）：
  (a) F034 前端实现落地（`importCarrier.ts` 存在且两面板接线）；
  (b) `docs/api/F014.md` / `docs/api/F023.md` 两份增补节由 Architect 签核为 **READY** —— **已满足**（2026-10-26 签核生效，含 3 条解释性裁定附注，见 architecture §12）；
  (c) 协调器划定测试文件所有权（TD-I-3）—— **已确认**（见 TD-14「TEST 阶段文件所有权」）。

### TD-10 反空洞设计

1. **T107（"两个入口都提供"）** 不能只看「文件存在」：要求两面板各自命中载体控件 + 文件输入 + 文本域，且 `ui/controls.tsx` 零 diff；否则"只改了一个入口"或"顺手重写适配层"都会漏掉。
2. **T111 字节计量** 用**互斥对**消除实现歧义：`F-21`（精确等于 limit 必须放行）杀掉 `>=` 的 off-by-one；`F-22`（`length < limit` 但字节 > limit 必须拦截）杀掉 `.length` 实现。两条同时通过才证明"按 UTF-8 字节、严格大于"。
3. **T111 行数** 用「本地不拦 + 服务端 413」双向：`TD3-T111.8`（5001 行小字节仍 `ok:true`）证明前端**没有**偷偷镜像行数上限；`TD3-T111.6`（服务端 413）证明权威仍在服务端。
4. **T110「不发请求」** 不靠文案，靠 `calls.length === 0`（fetch 计数），并同时断言 `errors.text` 非空（有本地提示）。
5. **T116 指纹** 三重反空洞：改 1 字符必换（含非 ASCII、含空白差异）；同内容必稳；同字节跨载体必不同（证明 carrier 维度真的进了 key）。R-4 摘要碰撞不做"证明"，只记理论风险 + 服务端再校验兜底（TD3-T116.7/8）。
6. **T112 表头** 不只测「拒绝」，还测**具体 reason 与数组内容**（`missing_columns === ["hostname"]`、`column_order`），避免"一律 422 蒙对"；再用 `F-19` 大小写变形确保没有静默折叠。
7. **T115 不留痕** 用唯一 marker 做**可搜索探针**（响应体 / audit_logs / 容器日志三处 grep 计数 0），而不是"看起来没记"。
8. **零改动守卫** 用 `backend/app`、`backend/alembic` 目录级空 diff 证明"服务端零改动"，从而使所有差异可归因到前端；`imports.ts` 用"diff 仅注释"筛选而非人工判断。
9. **回归计数** 不用"差不多"：`smoke:client` 须 == 基线 328 + 新增（新增用例名逐一列出）；后端套件 0 failed 且收集数一致。

### TD-11 数据完整性对照（`data-integrity` SKILL.md 方法）

本 Feature `layers.database=false`、`backend=false`，**无新写入入口、无 Schema/Migration/约束变更**。按技能表填写适用行：

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据（本 TD 计划） |
| --- | --- | --- | --- | --- | --- |
| requirements rev13 §24.5「口径一致」+ F014 §8 / F023 §12 | `/imports/resources{,/validate}`、`/imports/resource-interfaces-ips{,/validate}`（**载荷来源**由文件变为前端粘贴文本，入口集合不变） | 不变：`uq_resources_cluster_id_hostname_key`、`uq_interfaces_resource_id_name`、`uq_ip_addresses_cluster_id_address`、触发器函数等全部沿用，本次零变更 | 不变：Service Layer 校验复用；前端只做非权威前置提示（空/超限） | 不变：单事务 + SAVEPOINT 整批回滚；F023 确定性锁序与 40P01 兜底；预校验只读不加锁 | `TD3-REG.2`（`backend/app`、`backend/alembic` 空 diff）+ `TD3-ATOM.1/2/4` + `TD3-REG.7`（既有套件真实 PG 回归） |
| requirements rev13 §22 + §24.5「审计口径一致」 | 同上（写入端点） | 不变（Audit 由同一事务写） | 不变 | 不变：回滚无 Audit 残留 | `TD3-T115.4/5`、`TD3-ATOM.1` |
| requirements rev13 §23.2 / F027 | 同上（行级范围校验） | 不变 | 不变：范围校验先于唯一性，不泄露 | 不变 | `TD3-T115.3`、`TD3-ATOM.3` |
| requirements rev13 §24.5「不持久化」 | 前端载体 + 请求体 | 不适用（无新表/列） | 前端不写 storage/URL/console；服务端不落盘（沿用 ON-2 边界） | — | `TD3-T115.5/6/7/9` |

**结论（计划）**：无新增完整性约束需验证；完整性证据全部落在「不改变既有保证」的回归一侧，且必须用**真实 PostgreSQL**（SQLite/Mock 不作为证据）。

### TD-12 未验证项 / 降级声明（预登记）

| 项 | 原因 | 处理 |
| --- | --- | --- |
| 浏览器交互（B 层全部）：两载体可见、切换、文本域行尾呈现、字节计数展示、`role="alert"`、`disabled` 请求态、结果区回空态、storage/console | 仓库无 DOM/E2E 框架；F034 不引入（AGENTS §2.6） | `NOT TESTED`；降级证据 = S+M；可选人工留证（`http://localhost:18080`，用 `admin`/`testadmin`，步骤：两入口各粘贴 `F-01` → 预校验 → 改 1 字符 → 观察按钮禁用 → 切载体 → 预校验 → 确认导入（仅测试栈））；留证须注明执行人与时间 |
| 真实 5 MiB 端到端请求（`F-21` 上限值本身） | 载荷过大、构造与解析成本高，且服务端零改动 | `NOT TESTED`；改以小 limit 注入（TD3-T111.5）+ 本地精确边界（TD3-T111.2/3）覆盖比较语义 |
| `>1 MiB` 请求体的磁盘落盘路径 | Starlette 既有溢写行为（架构 ON-2），F034 不改变 | `NOT TESTED`，不声称"全路径不落盘" |
| 摘要（FNV-1a+djb2）碰撞可能性 | 数学性质，非可穷举验证 | 不作证明；仅记 R-4 + 依赖重置与"服务端再校验" |
| 压力/持续并发（>2 连接、多轮冲突） | 仓库无压力设施；F034 无并发机制变更 | 单次真并发（≤3 次尝试）为证；压力 `NOT TESTED` |
| 全量后端 pytest（约 19 分钟） | 仅在确实需要证明全局无回归时执行 | 默认执行 TD-REG.7 定向套件；如协调器要求全量则记实际计数与耗时 |
| `.xlsx` 文本载体 | 明确不做（§24.5） | `NOT_REQUIRED`（不是未验证）：不提供该入口，故无验收项 |

### TD-13 缺陷与需裁定项（v1.1：TD-I-1 / TD-I-2 / TD-I-3 均已裁定，见各行末列）

| ID | Severity | Layer | Location | 证据 / 复现 | 期望 vs 实际 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TD-I-1** | MEDIUM | 需求 / 契约可验证性 | 需求 T114 后半句 vs `backend/app/services/resource_import.py::_parse_csv`（第 419–425 行）与 `_validate_record` 的单元格填充（第 596 行） | `_parse_csv` 使用 `csv.reader(io.StringIO(text, newline=""))`（默认 `strict=False`）；`_validate_record` 只对短行补空、忽略超出表头长度的多余单元格。故 `F-13`（未闭合引号）会被"读到 EOF"**静默接纳**（可能吞掉后续行）而不产生文件级错误 | T114 **原表述**「引号未闭合等字段边界错误按既有文件级错误呈现，**不静默修补**」；实际既有行为是不报错。F034 `layers.backend=false` 无法满足该字面表述（requirements revision 13 已对 §31 T114 作**编辑性澄清**：字段边界按等价性口径判定） | **Architect**（设计/契约解释）+ **Product Manager**（需求措辞） | **已裁定 / RESOLVED（2026-10-26，architecture §12 + 契约增补节「解释性裁定附注 1」）**：采用方案 ①——T114 按 §24.5「等价性」口径判定，**不要求 422**。T114 相关用例的 PASS 判据 = 同字节两载体 `status` 与响应体深比较一致 + 实际观测如实记录。方案 ②（服务端 strict 解析、复用 `unreadable`）仍须另立变更提案（`change-control.md`），不在 F034 范围 |
| TD-I-2 | LOW | 契约明确度 | `docs/api/F014.md` / `F023.md` 增补节「表头与分隔符」 | 制表符分隔被拒时的具体 `IMPORT_INVALID_FILE.details.reason` 未固定（既有实现由 `_resolve_template` 决定，可能是 `missing_columns` 或 `unknown_columns`） | TD 断言为「reason ∈ 已签核集合 + 非 200/201」 | Architect | **已裁定 / RESOLVED（2026-10-26，architecture §12 + 增补节「解释性裁定附注 2」）**：**仅固定类别集合**（422 `IMPORT_INVALID_FILE`、`reason ∈` §1.2 已签核集合 `header_missing` / `missing_columns` / `unknown_columns`、非 2xx 成功、无写入、与同字节文件载体响应逐字段相同），**不固定具体取值**；TEST 记录实际观测值即可 |
| TD-I-3 | LOW | 测试基础设施 | 文件所有权 | TEST 需写入：`backend/tests/**`（含新建 `tests/integration/test_f034_csv_text_carrier.py`）、`docs/features/F034/artifacts/**`（语料与日志）、`docs/features/F034/test-report.md` | 架构 §10 已授权 Tester 出集成用例与验证产物，但需协调器在并行实现阶段明确文件所有权；否则 I/M 层用例无法落地 | 协调器 | **已确认（RESOLVED，TEST 阶段文件所有权）**：Tester = `backend/tests/**`、`docs/features/F034/artifacts/**`、`docs/features/F034/test-report.md`；`frontend/scripts/smoke-client.mjs` 归 **Frontend** 修改，Tester **只运行、不改**（Tester 在 `TD3-REG.8` 只断言 0 failed、计数与新增用例名，不新增/编辑 smoke 用例）；额外夹具仅限上述目录内（见 TD-14） |
| TD-I-4 | NOTE | 边界表述 | 需求 §24.5「不落盘」/ 架构 ON-2 | 既有 Starlette 对 >1 MiB 请求体溢写匿名临时文件即抛 | TD 只断言应用层无残留，不主张"全路径不落盘"；不作为缺陷 | Architect（如需改写措辞则走变更） | 否 |
| TD-I-5 | NOTE | 前端/服务端层差 | 仅 BOM 文本（`F-24`） | JS `trim()` 把 `U+FEFF` 视为空白 → 前端本地拦截、不发请求；服务端则会判 `empty_file` | 两者均**拒绝且无写入**，只是拦截层不同；TD 允许二者之一，不作缺陷；若产品要求提示文案一致可另行调整 | Architect / Frontend（文案） | 否 |

### TD-14 结论

**Status：`TEST DESIGN READY (v1.1)`**

- T107–T116 每条均已映射到具体用例 ID、层次（U/M/I/H/S/B）与可观察断言，可用现有环境（Node 22 + pytest + 真实 PostgreSQL 16.15 + `csmtest` 栈 18080）执行；等价性有机械可判据（TD-5），并发与原子性有真实 PG 方案（TD-6），数据完整性无新增约束需验证（TD-11）。
- READY 的**含义与限制**：仅表示方案可验证，**不**表示测试通过、**不**批准实现或合并；B 层（浏览器）与 5 MiB 真实载荷等项已如实预登记为 `NOT TESTED`（TD-12）。
- **进入 TEST 的三项前置**（TD-9）：实现落地、两份契约增补节签核 READY（**已满足**）、测试文件写权确认（**已确认**）。
- **已裁定（2026-10-26，替代 v1 的「需裁定」结论）**：
  - **TD-I-1 → RESOLVED**：依 architecture §12，T114 按**等价性口径**判定，**不要求 422**（requirements revision 13 §31 T114 已作编辑性澄清，§35.1 有记录）。`TD3-T114.4` / 夹具 `F-13` 的 **PASS 判据 = 同字节两载体 `status` 与响应体深比较一致 + 实际观测如实记录**，不得以「未返回 422」判 FAIL。
  - **TD-I-2 → RESOLVED**：制表符分隔的 `IMPORT_INVALID_FILE.details.reason` **仅固定类别集合**（见增补节附注 2），不固定具体取值；TEST 记录实际观测值。
  - 本 TD 不再产出「待裁定」结论；TEST 阶段逐项给出 PASS / FAIL / BLOCKED / NOT TESTED。

### TD-15 TEST 阶段文件所有权（确认）

| 路径 | Owner | Tester 行为 |
| --- | --- | --- |
| `backend/tests/**`（含新建 `tests/integration/test_f034_csv_text_carrier.py`、按需的 fixtures 辅助模块） | **Tester** | 可新建/修改 |
| `docs/features/F034/artifacts/**`（`corpus/`、日志、H 层 Node 脚本、证据文件） | **Tester** | 可新建/写入 |
| `docs/features/F034/test-report.md` | **Tester** | 可写入（本报告唯一输出） |
| `frontend/scripts/smoke-client.mjs` | **Frontend** | **只运行、不改**（`npm run smoke:client`）；不以修改该文件取证，若用例不满足判据则记缺陷并退回 Frontend |
| `frontend/src/**`、`backend/app/**`、`backend/alembic/**`、`docs/api/**`、`docs/product/**`、`docs/project/**` | Frontend / Architect / 协调器 | Tester 不写入 |

**需要的额外夹具文件（均限于 `docs/features/F034/artifacts/` 下，不跨目录）**：

1. `docs/features/F034/artifacts/corpus/F-01.txt` … `F-26.txt`（+ `F-05b`）：UTF-8 语料单一来源（TD-8.1）。
2. `docs/features/F034/artifacts/corpus/F-xx.csv`：由 Node 侧 `Buffer.from(text,"utf8")` 一次性生成的逐字节对照文件。
3. `docs/features/F034/artifacts/corpus/gen-corpus.mjs`：语料生成/校验脚本（含 `F-21`/`F-22` 程序化边界构造）。
4. `docs/features/F034/artifacts/f034-live-validate.mjs`：H 层真实 HTTP 只读脚本（复用 `pastedCsvFile()`）。
5. `docs/features/F034/artifacts/logs/`：pytest / smoke / typecheck / build / `docker logs` 归档（若被 `.gitignore` 忽略须在 TEST 报告声明）。

以上文件如协调器要求入版，均由协调器统一暂存提交；Tester 不执行任何改变 Git 状态的命令。

---

## Test Execution（TEST-1）

未开始。本阶段未执行任何验收（工作区无实现产物：`33d8a03..bbc9e91` 仅 docs 变更），因此不填写任何 PASS。

---

GIT: git rev-parse --short HEAD
GIT: git rev-parse --abbrev-ref HEAD
GIT: git status --porcelain
GIT: git log --oneline 33d8a03..HEAD
GIT: git diff --stat 33d8a03..HEAD
GIT: git status --porcelain=v1 --untracked-files=all
