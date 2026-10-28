# F034 导入 CSV 文本载体 — Test Report

> 本文件同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本、结论与证据。
> **当前状态**：§1 TEST DESIGN 为 **v1.1（2026-10-26，`TEST DESIGN READY`）**；§2 **TEST EXECUTION（TEST-1，v1，2026-10-26，候选 HEAD `717385b`）= `READY FOR REVIEW`**（见 §2.11）。`TEST DESIGN READY` 仅表示方案可验证，不是测试通过；§2 的 READY 也不批准合并或替代正式 Review / Merge Gate。
> §1 的编写基线为 HEAD `bbc9e91`（`33d8a03..bbc9e91` 仅含 docs 变更），该阶段只做设计检查；§2 记录实际执行（真实 PG 集成、真实栈 HTTP、真实浏览器、静态守卫）。

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

## 2 TEST EXECUTION（TEST-1，v1，2026-10-26）

> 本节由 Tester 独立执行产出，**不修改 §1 TEST DESIGN 与 v1.1 记录**。上一版占位节「Test Execution（TEST-1）未开始」已被本节取代（该占位内容写于设计阶段，头 `bbc9e91`，当时无实现产物）。
> 结论：**READY FOR REVIEW**（见 §2.9）。READY 仅表示本 Feature 的验收项按 TEST DESIGN 全部执行通过、无必须修复缺陷、未验证项已如实登记；不替代正式 Review 与 Merge Gate。

### 2.1 Task / Status / 版本与基线

- **Task**：F034「导入 CSV 文本载体」（P1 / M25）；分支 `feature/F034-csv-text-import`，base `v3.3`，`start_commit` `33d8a03`，`plan_revision` 20。
- **候选 HEAD（被验证对象）**：`717385b`（`feat(F034): frontend CSV text import carrier for both import panels`）；执行时 `git rev-parse --short HEAD` = `717385b`，工作区无已跟踪文件改动（新增文件全部为 Tester 本阶段产物，见 §2.10）。
- **模式**：TEST（独立执行验证）；上游输入 = TEST DESIGN v1.1（§1）+ `docs/features/F034/implementation.md` v1 + `docs/features/F034/architecture.md` v1（§12 定稿，TD-I-1 / TD-I-2 裁定）+ `docs/api/F014.md` / `docs/api/F023.md` §「CSV 文本载体（加法引用）」增补节 v1（READY，含 3 条解释性裁定附注）+ requirements revision 13 §24.5、§31 T107–T116。
- **执行时间**：2026-10-26 06:2x–06:5x UTC（环境快照 `2026-10-26T06:43:59Z`，见 `artifacts/logs/environment.log`）。
- **Tester 写入范围**（TD-15 确认）：`backend/tests/**`、`docs/features/F034/artifacts/**`、本文件。**未修改** `frontend/**`、`backend/app/**`、`backend/alembic/**`、`docs/api/**`、`docs/product/**`、`docs/project/**`。

### 2.2 Environment（实测）

| 项 | 事实 | 证据 |
| --- | --- | --- |
| 测试栈 | compose 项目 `csmtest`：`csmtest-backend-1`(healthy) / `csmtest-db-1`(healthy) / `csmtest-frontend-1` / `csmtest-nginx-1`；`GET /api/v1/health` 与 `/health/ready` 均 200 | `artifacts/logs/environment.log` |
| 后端集成数据库 | **真实 PostgreSQL 16.15**，容器 `csm-f026-pg`（`127.0.0.1:55432`），库 `csm_test`；DB-D10 双守卫通过（库名含 `test`、`DATABASE_URL` 已 unset）；执行后 `public` 表数 = **0**（fixture teardown 无残留） | `artifacts/logs/environment.log`、`artifacts/logs/pytest-f034-targeted.log` |
| 工具链 | Node v22.23.3、Python 3.12.7、pytest 7.4.4、Playwright(Python)+Chromium（宿主既有，**未新增仓库依赖**） | 命令输出（本报告 §2.5–§2.7） |
| `csmtest-frontend-1` | 运行**实现之前**的旧前端镜像 → 不用作 F034 UI 证据；B 层改以「`npm run build` 产物 + 本机静态服务 + 真实后端 API」执行（§2.7） | §2.7 |
| 写入纪律 | 真实写业务数据**仅**在 `csm_test`（pytest，`committed_engine` teardown TRUNCATE）；`csmtest` 栈只发**只读** `/validate` 与认证请求（另有 `GET /clusters`、登录会话），**未向该库写入任何业务数据** | `artifacts/logs/live-validate.log`、`artifacts/logs/backend-logs-since-marker.log` |
| 凭据 | 未写入仓库与任何 artifact（`grep testadmin\|*** docs/features/F034/artifacts/` = 0；脚本改为从环境变量读取，缺失即退出） | 本报告 §2.10 |

### 2.3 语料与夹具（TD-8）

- 单一来源：`docs/features/F034/artifacts/corpus/gen-corpus.mjs` 生成 **30 份**夹具（`F-01`–`F-26` + `F-03f` / `F-05b` / `F-06a` / `F-06b` / `F-10b` / `F-15a` / `F-18a` / `F-18b` / `F-20w`），每份同时产出 `.txt`（用户粘贴文本）与 `.csv`（逐字节相同的「文件载体」对照）。
- 逐字节校验：`Buffer.compare(txt, csv) === 0` 且 UTF-8 往返恒等 → **30/30 OK，0 失败**；边界算术落盘于 `corpus/boundary.json`（ASCII `5,242,879 / 5,242,880 / 5,242,881`；反空洞 `"中"×2,621,441`：`String.length` 2,621,441 < 上限但 UTF-8 字节 7,864,323 > 上限）。
- 语料枚举取值按**冻结模板**构造（`status ∈ {IDLE, ALLOC, DOWN, UNKNOWN}`、`interface_type ∈ {PHYSICAL, VIRTUAL, …}`、`role ∈ {COMPUTE, …}`），未自创领域值。

### 2.4 验收映射 T107–T116（逐用例结论）

记号：**I** 真实 PG 集成 / **H** 真实栈 HTTP（无浏览器）/ **B** 真实浏览器 / **U·M** Node 机制级 / **S** 静态。
证据缩写：`T`=`artifacts/logs/pytest-f034-targeted.log`（31 passed）、`R`=`artifacts/logs/pytest-import-regression.log`（112 passed）、`L`=`artifacts/logs/live-validate.log`（108 checks / 0 fail）、`U`=`artifacts/logs/boundary-check.log`（36 checks / 0 fail）、`B`=`artifacts/logs/browser-check.log`（18 checks / 0 fail）、`S`=`artifacts/logs/smoke-client.log`（337 passed / 0 failed）、`E`=`artifacts/equivalence-observations*.json`、`G`=`artifacts/logs/gen-corpus.log`。

#### T107 — 两入口并列载体、文件载体零回归

| 用例 | 层 | 结论 | 证据 / 断言摘要 |
| --- | --- | --- | --- |
| TD3-T107.1 | S | **PASS** | 两面板均含载体 `Select`（`option` = 「上传文件（CSV / .xlsx）」「粘贴 CSV 文本（仅 CSV）」）、文件分支 `<Input type="file">` 保留、文本分支 `<TextArea>`；`ResourceImportPanel.tsx:252-253,289,322`、`ResourceInterfaceIpImportPanel.tsx:277-278,316,352` |
| TD3-T107.2 | U | **PASS** | `importCarrierPatch(values,"text").format === "csv"`、切回 file **不回填** xlsx（S：「F034 importCarrierPatch / resourceInterfaceIpImportCarrierPatch：切 text 强制 csv，切回 file 不回填 xlsx（DR-F034-07）」） |
| TD3-T107.3 | S | **PASS** | `frontend/src/api/imports.ts` diff **0 行**（比 TD 允许的「仅注释」更严）；`ImportErrorsTable.tsx` / `ui/controls.tsx` / `ResourcesPage.tsx` diff 均 0 行 |
| TD3-T107.4 | M+S | **PASS** | 模板生成函数与列常量（`buildTemplateCsv` / BM·VM 列常量 / `RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS`）在两 form 模块的 diff 中**零命中**（定向 `grep -nE "^[-+]…(buildTemplateCsv|TEMPLATE_COLUMNS|…)` → 无输出；`IMPORT_MAX_FILE_BYTES` 仅被引用、其定义在零 diff 的 `api/imports.ts`），输出由构造不变；既有 F014/F023 模板 smoke 用例继续 PASS（S） |
| TD3-T107.5 | U+M | **PASS** | `format=xlsx` + 非 `.xlsx` 名 → `parse*` `ok:false`（U：`T107.5 file carrier format=xlsx with a non-.xlsx name still rejected locally`）；`.xlsx` 正常路径与既有断言保持（S:250、S:319） |
| TD3-T107.6 | M | **PASS** | `npm run smoke:client` = **337 passed / 0 failed**（基线 328 + F034 新增 9，见 §2.6） |
| TD3-T107.7 | B | **PASS**（原计划 NOT TESTED，本轮取得真实浏览器证据） | 两面板各自可打开并**并列**展示两种载体；切换载体后结果区回到「尚未预校验」空态（B：`TD3-T107.7 …` 6 条） |

#### T108 — 合法文本两步流程与行号口径

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-T108.1 | U+M+B | **PASS** | `pastedCsvFile`：`name="csm-pasted-import.csv"`、`type="text/csv;charset=utf-8"`、`size === utf8ByteLength(text)`、字节与 corpus 逐字节相等（L：30/30 `pastedCsvFile(...) reproduces corpus bytes`）；`FormData` 带固定 filename + `format=csv`（S）；浏览器真实 multipart 请求 200（B） |
| TD3-T108.2 | I | **PASS** | `F-01` → 200 `total_rows=2/importable_rows=2/error_count=0`；`F-02` → 1/1/0；`F-03`(26 列) → 3/3/0；`format="csv"`（T：`test_td3_t108_2_valid_text_validate`） |
| TD3-T108.3 | I | **PASS** | `F-20` 写入 → 422 `IMPORT_VALIDATION_FAILED`，`details.error_count` == 预校验 `error_count`(6)，`importable_rows` 一致，六表计数不变（T：`test_td3_t108_3_error_batch_rejected_on_write`） |
| TD3-T108.4 | U+B | **PASS** | 门控（`validatedKey === currentKey && error_count === 0 && !importSucceeded`）：S 用例 + B 观察（预校验前「确认导入」disabled；有行错误时仍 disabled；改字符后仍 disabled） |
| TD3-T108.5 | I | **PASS** | 预校验绿 → 外部建同 `(cluster,hostname)` → 同字节写入 422（`row=2, field=hostname`）+ 零残留（T：`test_td3_t108_5_t116_8_…`） |
| TD3-T108.6 | I | **PASS** | 表头为第 1 行；第 3 个数据行错误 → `errors[].row === 4`（`F-10b`）；两载体同值（T） |
| TD3-T108.7 | I | **PASS** | 同一内容连续两次 `/validate` → 响应体深比较相等，六表计数不变（T：`test_td3_t108_7_t116_7_…`） |
| TD3-T108.8 | I | **PASS** | 26 列写入信封：文本 `F-03` 与文件 `F-03f` 均 `{created:2, total_rows:3, interfaces_created:3, ip_addresses_created:3}`，字段集合相同；实际增量 resources +4 / interfaces +6 / ip_addresses +6（T：`test_td3_t108_8_26col_write_envelope_parity`） |

#### T109 — 行错误同形状同内容、不 fail-fast

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-T109.1 | I | **PASS** | `F-20` 六类错误（非法枚举 / 非法整数 / 长度 >255 / 批内重复含 `related_row` / 现存冲突 / 不存在 cluster）：每条 `{row:int≥2, field∈BM 模板列名, reason:非空 str, related_row:int\|null}`，键集合恰为四字段（T） |
| TD3-T109.2 | I | **PASS** | 不 fail-fast：`error_count=6` 且 `errors` 长度 6，`importable_rows=1 = 7−6`（T） |
| TD3-T109.3 | I | **PASS** | F023 变体 `F-20w`：`(cluster,ip)` 批内重复 `field=ip / related_row=2`、Network 无法解析 `field=network`、行类型适用性冲突 `field=vcpu`，四条数据行 3 条错误（T：`test_td3_t109_3_f023_error_matrix`） |
| TD3-T109.4 | I+H | **PASS** | 全部语料（含 `F-20` / `F-20w`）两载体 `status` 相等且响应体深比较相等（T：`test_td5_equivalence_matrix_all_corpus`；L：60 例 live 等价） |

#### T110 — 空 / 纯空白 / 仅表头

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-T110.1 | U | **PASS** | `""`、`"   "`、`"\n\n"`、`" \t\r\n "` 两模块各返回 `ok:false` 且 `errors.text` 非空（U：4 条 `T110.1 blank …`；F023 模块同口径见 S） |
| TD3-T110.2 | M | **PASS** | 上述四类均**不发请求**（S：`F034 parseImportFormValues 文本载体：空 / 纯空白不发请求…`、`F034 parseResourceInterfaceIp…同一拦截口径`；U 层 `ok:false` 即请求前置失败） |
| TD3-T110.3 | I | **PASS** | 仅表头（`F-06a` BM / `F-06b` 26 列）→ 422 `IMPORT_INVALID_FILE`，`details == {"reason":"empty_file"}`，两入口两载体一致（T） |
| TD3-T110.4 | I | **PASS** | `resources` / `bare_metal_details` / `virtual_machine_details` / `interfaces` / `ip_addresses` / `audit_logs` 计数与基线相等（T：`test_td3_t110_header_only_empty_file_no_residue`） |
| TD3-T110.5 | I | **PASS** | `F-05b`（`,,,\n`）→ 422 `header_missing`，两载体相同（T + E） |
| TD3-T110.6 | U+I | **PASS**（分支已记录） | 仅 BOM `F-24`：**本地拦截**（`trim()` 视 `U+FEFF` 为空白，F034-FE-01）**且**服务端分支为 422 `empty_file`（实测两载体一致、无写入）；符合 TD-I-5「二者之一、无写入」 |

#### T111 — UTF-8 字节上限与行数上限

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-T111.1 | U | **PASS** | `utf8ByteLength` == `TextEncoder` 字节：ASCII 3 / 中文 6 / emoji 4 / 混合 8；且 `utf8ByteLength !== String.length`（U、L 各一组） |
| TD3-T111.2 | U | **PASS** | 严格大于：`5,242,879` → accepted、`5,242,880` → accepted、`5,242,881` → rejected（U：两 form 模块各 3 例） |
| TD3-T111.3 | U | **PASS**（反空洞） | 构造 `String.length=2,621,441 < 上限` 而 UTF-8 字节 `7,864,323 > 上限` → **rejected**（U；`corpus/boundary.json` 记录算术） |
| TD3-T111.4 | M | **PASS** | 超限无请求（S：`上限−1/＝/+1 严格大于口径` 用例断言无 fetch；U：`ok:false` 提前返回） |
| TD3-T111.5 | I | **PASS** | 服务端按字节、严格大于：注入 `import_max_file_bytes = len(F-01)−1 = 355` → 413 `{code:IMPORT_FILE_TOO_LARGE, details:{limit_bytes:355}}`；`= 356` → 200 且 `error_count=0`；两载体一致（T） |
| TD3-T111.6 | I | **PASS** | 5001 数据行文本（两载体）→ 413 `{code:IMPORT_ROW_LIMIT_EXCEEDED, details:{limit_rows:5000}}`，六表计数不变（T） |
| TD3-T111.7 | I | **PASS** | 5000 数据行（cluster 全部不存在）→ 200，`total_rows=5000`、`error_count=5000`、`importable_rows=0`、`errors_truncated=true`、`errors.length=1000`；文件载体响应逐字段相等（T） |
| TD3-T111.8 | S+U | **PASS** | 前端源码对 `IMPORT_MAX_ROWS` 无引用（S+M：5001 行小字节文本 `ok:true`，**不在本地拦截**；U） |
| TD3-T111.9 | I | **PASS** | `F-26`（`戴尔, Inc.` / `A100-🚀`）→ 200 `error_count=0`；写入后回读 `hardware.manufacturer="戴尔, Inc."`、`hardware.gpu_model="A100-🚀"`（API 与 DB 直读双证）（T） |

#### T112 — 表头严格性（不补、不重排、不嗅探、不折叠）

| 用例 | 层 | 结论 | 证据 / 实际观测 |
| --- | --- | --- | --- |
| TD3-T112.1 | I | **PASS** | `F-15a`（首行为空行）→ 422 `header_missing`；`F-05b`（`,,,\n`）同。**观测**：`F-15`（首行即数据行）→ 422 但 `reason="unknown_columns"`（附 `missing_columns`），见 **DEV-1**（TD 断言过窄，非实现缺陷） |
| TD3-T112.2 | I | **PASS** | `F-16`（去 `hostname`）→ `{"reason":"missing_columns","missing_columns":["hostname"]}`（精确相等） |
| TD3-T112.3 | I | **PASS** | `F-17`（追加 `interface_name`）→ `{"reason":"unknown_columns","unknown_columns":["interface_name"]}` |
| TD3-T112.4 | I | **PASS** | `F-18a`（完全逆序）/ `F-18b`（交换前两列）→ 422 `column_order`；**未**按名重排、未 200 |
| TD3-T112.5 | I | **PASS** | `F-19`（`HOSTNAME`）→ 422，`reason="unknown_columns"`（`∈ {missing_columns, unknown_columns}`，附 `missing_columns:["hostname"]`）；无大小写折叠 |
| TD3-T112.6 | I | **PASS** | `F-14`（制表符分隔）→ 422 `IMPORT_INVALID_FILE`，实测 `reason="unknown_columns"`（`∈` 已签核集合，符合 TD-I-2「只固定类别」）；写入端点同样 422 且零残留 |
| TD3-T112.7 | I | **PASS** | 仅数据行文本不被当作合法导入（422，未自动补表头） |
| TD3-T112.8 | I | **PASS** | 上述每条均双载体提交并深比较一致（T：`assert_equivalent`；E 全量记录） |

#### T113 — BOM / 行尾 / 尾部空行

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-T113.1 | U+M | **PASS** | 无 BOM 文本的首 3 字节 ≠ `EF BB BF`（L：`F-01` 352 字节逐字节复现且不含 BOM）；payload 不 trim（U：T116.3 三连指纹互异） |
| TD3-T113.2 | I | **PASS** | `F-07`（`U+FEFF`+`F-01`）→ 200 且响应体与 `F-01` **完全相等**（表头首列未被污染）；两载体一致 |
| TD3-T113.3 | I | **PASS** | `F-08`(CRLF) / `F-09`(混用) 与 `F-01`(LF) 的 `total_rows`/`error_count`/`errors` 全等；各自与文件载体一致 |
| TD3-T113.4 | U | **PASS** | `pastedCsvFile("…\r\n…")` 字节与源 UTF-8 逐字节相等（L：`F-08` 355 字节 `reproduces corpus bytes`）→ CRLF 未被改写、未补/删尾换行 |
| TD3-T113.5 | I | **PASS** | `F-10`（`F-01` + 尾随 3 空行 + 末尾换行）→ `total_rows=2` 与 `F-01` 相同；`F-10b`（3 数据行 + 尾随空行）→ 第 3 数据行错误仍报 `row=4`（见 **DEV-2**：TD 把两件事写在一条里，本轮拆成 `F-10` / `F-10b` 分别断言） |

#### T114 — CSV 字段边界（**等价性口径**，TD-I-1 裁定）

| 用例 | 层 | 结论 | 证据 / 实际观测 |
| --- | --- | --- | --- |
| TD3-T114.1 | I | **PASS** | `F-12` 预校验 `error_count=0`；写入 201 后回读 `hardware.manufacturer="Dell, Inc."`（逗号未改写） |
| TD3-T114.2 | I | **PASS** | 双引号转义 `"Manu""facturer"` → 回读 `Manu"facturer`（标准 CSV 解转义） |
| TD3-T114.3 | I | **PASS** | `F-11`（引号内换行）→ `total_rows=2`（按逻辑记录），后续错误 `row=3`。**观测**：该行另有 `manufacturer` 控制字符拒绝（`row=2`），属既有 F014 规则（见 **DEV-3**），两载体一致 |
| TD3-T114.4 | I | **PASS**（等价性判据） | `F-13`（未闭合引号，位于文件中部）：两载体 `status` 相等且响应体深比较一致。**实际观测**：200 / `total_rows=1` / `error_count=1`（`row=2, field=manufacturer, reason="hardware.manufacturer must not contain control characters"`）——既有 `csv.reader` 把后续物理行并入同一字段（吞并），F034 未改变该行为，按 architecture §12「不改、不新增判定」判 PASS（记录：`artifacts/t114-unclosed-quote-observation.json`） |
| TD3-T114.5 | U+S | **PASS** | `pastedCsvFile` 对含引号 / 换行文本逐字节原样（L 全语料字节相等）；载体模块内无 CSV 解析实现（`split(",")`/`split(/\r?\n/)`/引号状态机 命中 **0**） |

#### T115 — 权限 / 集群范围 / Audit / 不留痕

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-T115.1 | I | **PASS** | VIEWER：两入口 × 两端点共 4 次请求全部 403 `{"code":"FORBIDDEN","message":"Forbidden","details":{"reason":"permission"}}`（T） |
| TD3-T115.2 | I+H | **PASS** | 未认证 4 次请求全部 401 `AUTH_REQUIRED`（T）；live 栈同样 401（L 两条），401 先于 403（无 Cookie 时不会进入权限判定） |
| TD3-T115.3 | I（`real_scope`） | **PASS** | 仅授权 A/B 的 EDITOR：含 C 集群行 → `/validate` 200、`errors[0]={row:3, field:"cluster"}`、响应体与错误体均不含 `F34SC`（不泄露）；写入 422 整批失败 + 零残留；两入口（F014 / F023）两载体一致（T：`test_f034_csv_text_carrier_scope.py` 2 例） |
| TD3-T115.4 | I | **PASS** | 成功写入：每成功对象恰 1 条 `CREATE`（2 行 → audit +2），`operator_username` = 当前用户，`before_data IS NULL` / `after_data` 非空；文件载体用例的 audit 字段元组完全一致（T） |
| TD3-T115.5 | I | **PASS**（按 §12 收窄的措辞） | `F-25` 写入 201：响应体**不含整段粘贴文本**、不含完整表头行；`audit_logs.after_data` 不含表头行；`pg_tables` 集合不变（无新增暂存 / 临时表）。表头级 `details.unknown_columns` 回显属既有 schema（附注 3），见 **NOTE-2** |
| TD3-T115.6 | I+H | **PASS** | 标记 `F034-MARKER-8a1f4c0d-…` 请求后 `docker logs --since 15m csmtest-backend-1`（299 行）：marker 命中 **0**、表头行命中 **0**（另：live 响应体亦不含 marker） |
| TD3-T115.7 | S | **PASS** | `importCarrier.ts` / 两 form / 两 panel：`localStorage` / `sessionStorage` / `document.cookie` / `console.log\|warn\|error` 命中 **0**；无把内容拼入 URL / 查询串（B：所有请求 URL 不含载荷） |
| TD3-T115.8 | B | **PASS** | 浏览器实测：登录后 `localStorage`/`sessionStorage` 为空、`document.cookie` 为空（会话 Cookie 为 HttpOnly）、载荷 / marker 不出现在任何存储；登录后控制台 **0 error** |
| TD3-T115.9 | I | **PASS**（≤1 MiB）+ **NOT TESTED**（>1 MiB 子项） | ≤1 MiB：两次 `/validate` 前后 `tempfile.gettempdir()` 中无新增 import/csv/tsv 产物（T：`test_td3_t115_9_no_application_temp_files`）；>1 MiB 的 Starlette 溢写路径沿用既有边界（ON-2），**不声称全路径不落盘**（TD-12 预登记） |

#### T116 — 陈旧结果防护

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-T116.1 | U | **PASS** | 7 组变异（首字符 / 中间 / 末字符 / 增空格 / 删空格 / 中文替换 / emoji 替换）全部换指纹（U：7 条 `T116.1 …`；另 L 一条） |
| TD3-T116.2 | U | **PASS** | 同内容指纹稳定；file 键前缀 `file:`、text 键前缀 `text:csv:`；**同一字节两载体 key 不相等**（`file:csv:x.csv:352:…` vs `text:csv:2zicfq-1ftim6a:352`） |
| TD3-T116.3 | U | **PASS** | `"a,b\n"` / `"a,b \n"` / `"a,b\n\n"` 三者 key 两两不等（证明 payload 不 trim） |
| TD3-T116.4 | U+S+B | **PASS** | `importCarrierPatch` 后 key 变化；`changeInput` 统一重置 `localErrors`/`validateState`/`importState`/`validatedKey`，且载体/格式/文件/文本四个输入均走 `changeInput`；B：切载体后结果区回空态 |
| TD3-T116.5 | S+U+B | **PASS** | text 载体下 `format` 为 `ant-select-disabled`（B 实测 class 含 `ant-select-disabled`）；`carrier="text" && format!=="csv"` → `ok:false`（U）；file 载体下 format 变化换指纹（S） |
| TD3-T116.6 | U+B | **PASS** | `validatedKey !== currentKey` → 不可确认；F014 内联判据未削弱（S 用例 + 代码核对）；成功后不可再确认；B：「预校验前 / 有行错误 / 改字符后」三种情况「确认导入」均 disabled |
| TD3-T116.7 | I | **PASS** | = TD3-T108.7（重复预校验一致、无副作用） |
| TD3-T116.8 | I | **PASS** | = TD3-T108.5（服务端写入前再校验，不依赖前端指纹） |
| TD3-T116.9 | B | **PASS**（原计划 NOT TESTED，本轮取得真实浏览器证据） | 文本域改 1 字符 → 结果区立刻回「尚未预校验」、「确认导入」保持 disabled（B 两条） |

#### 回归与零改动守卫

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-REG.1 | S | **PASS**（含 1 项已解释的额外文件） | `33d8a03..717385b` 改动 18 个文件，全部落在白名单内；唯一白名单外文件 `docs/product/requirements-v3.md`（4 行）为 **revision 13 的 T114 编辑性澄清 + §35.1 记录**（CONTRACT Gate 已批准、architecture §12 引用），属变更控制范围，非实现越界（见 **NOTE-3**） |
| TD3-REG.2 | S | **PASS** | `git diff --name-only 33d8a03..717385b -- backend/app backend/alembic` → **空**（0 文件）；`-- backend/` 整体 → **空** |
| TD3-REG.3 | S | **PASS** | `frontend/src/api/imports.ts` diff **0 行**（比「仅注释」更严）；导出符号与签名不变（`npm run typecheck` exit 0 + smoke 导入即证） |
| TD3-REG.4 | S | **PASS** | `ui/controls.tsx` / `ImportErrorsTable.tsx` / `ResourcesPage.tsx` diff 均 0 行 |
| TD3-REG.5 | S | **PASS** | `frontend/package.json` / `package-lock.json` diff 0 行（无新增依赖/脚本） |
| TD3-REG.6 | S | **PASS** | `crypto.subtle` 调用命中 **0**（唯一命中为 `importCarrier.ts` 注释中的禁令文本）；`importCarrier.ts` 仅 `import type { ImportFormat } from "../api/imports.ts"`，无 React/antd/JSX |
| TD3-REG.7 | I | **PASS** | 既有导入套件 + F034 新套件合跑：**112 passed / 0 failed**（`test_imports.py` + `test_import_tester_acceptance.py` + `test_f023_resource_interface_ip_import.py` + `test_import_constraints.py` + `test_f027_access_scope.py` = 81 collected；F034 = 31 collected） |
| TD3-REG.8 | M | **PASS** | `npm run typecheck` exit 0；`npm run build` exit 0（`✓ built in 15.20s`，仅既存 chunk >500 kB 警告）；`npm run smoke:client` **337 passed / 0 failed**（基线 328 + 9，新增用例名见 §2.6） |
| TD3-REG.9 | P | **PASS** | `python3 scripts/validate_project_state.py` → `PROJECT STATE VALID`；`python3 scripts/render_project_views.py`（**不带** `--write`）→ `PROJECT VIEWS VALID`（结构通过 ≠ 批准或 Git 证据有效） |

#### 原子性与并发（TD-6）

| 用例 | 层 | 结论 | 证据 |
| --- | --- | --- | --- |
| TD3-ATOM.1 | I | **PASS** | F014：3 行含 1 个不存在 cluster → 422（`row=4, field=cluster`），六表计数不变、`f34-ok-%` 残留 0；F023：26 列变体同样零残留（resources / interfaces）（T：`test_td3_atom1_…`） |
| TD3-ATOM.2 | I | **PASS** | `F-01` 写入 201 → 再次同字节写入 422（`error_count=2`, `field=hostname`），计数与 audit 不增，且 `audit_logs` 中 `action <> 'CREATE'` 计数 = 0（无 UPDATE Audit、不静默覆盖） |
| TD3-ATOM.3 | I（`real_scope`） | **PASS** | 见 TD3-T115.3（范围外行整批失败 + 零残留） |
| TD3-ATOM.4 | I | **PASS** | 两个独立 EDITOR `TestClient` + `threading.Barrier(2)`、`join(timeout=30)` 且线程均已结束：结果 `[201, 422]`（**无 500**）；DB 该 hostname 行数 = **1**，该对象 audit 数 = **1**（T：`test_td3_atom4_concurrent_same_bytes`） |
| TD3-ATOM.5 | U+M+I | **PASS** | 本地拦截三类（空 / 纯空白 / 超限）均 `ok:false` → 无请求（S + U）；I 侧无请求即无写入（相关用例前后计数不变） |
| TD3-ATOM.6 | I | **PASS** | 5001 行 413 后六表计数不变（与 TD3-T111.6 合跑） |

### 2.5 数据库 / 接口 / 集成结果

- **数据库**：F034 无 Schema / Migration / 约束变更（`backend/app`、`backend/alembic` 空 diff）。本轮在**真实 PostgreSQL 16.15**（`csm_test`，fixture 从 `DROP SCHEMA` + `alembic upgrade head` 起）验证「不变量仍成立」：唯一性冲突（重复导入 422）、行级范围拒绝、整批回滚零残留、Audit 每对象 CREATE、`pg_tables` 集合不变。**未验证**「F034 引入的新约束」—— 不存在此类约束（`layers.database=false`）。执行后 `public` 表数 0，无残留。
- **接口**：响应内容 / 类型 / 业务边界 / 非法输入 / 错误语义逐项核对：`format`/`total_rows`/`importable_rows`/`error_count`/`errors[].{row,field,reason,related_row}`/`errors_truncated`；写入 `created`/`total_rows`/`interfaces_created`/`ip_addresses_created`；错误码 `IMPORT_INVALID_FILE`（6 个 `reason` 实测：`empty_file` / `header_missing` / `missing_columns` / `unknown_columns` / `column_order`）、`IMPORT_FILE_TOO_LARGE`、`IMPORT_ROW_LIMIT_EXCEEDED`、`IMPORT_VALIDATION_FAILED`、`AUTH_REQUIRED`、`FORBIDDEN{permission}`。**只读功能无业务写副作用**：`/validate` 前后六表计数不变、无 Audit、无锁。
- **请求形状不变**：仅发送 `file`（binary，含 filename）+ `format=csv`，未手工设置 `Content-Type`（浏览器真实 multipart 成功即证 cannonical 形状）。
- **等价性（核心）**：三层证据闭合 —— ①字节层：30/30 corpus `.txt` 与 `.csv` 逐字节相等，且 `pastedCsvFile()` 产物与之逐字节相等；②响应层：H 层 60 例 + I 层 60 例（30 语料 × 2 入口）`status` 与响应体深比较**全部相等**，`0` 差异；③写入层：成功信封逐字段相等、audit 元组相同、拒绝路径 `IMPORT_VALIDATION_FAILED.details` 逐字段相等。

### 2.6 前端结果

| 命令 | 结果 | 日志 |
| --- | --- | --- |
| `npm run typecheck` | **exit 0**（`tsc --noEmit` 无输出） | `artifacts/logs/typecheck.log` |
| `npm run build` | **exit 0**（`✓ built in 15.20s`；仅既存 chunk >500 kB 警告） | `artifacts/logs/build.log` |
| `npm run smoke:client` | **337 passed / 0 failed**（基线 328 + F034 新增 **9**） | `artifacts/logs/smoke-client.log` |
| `node artifacts/f034-boundary-check.mjs`（Tester 新增，只读运行既有前端源码） | **36 checks / 0 fail** | `artifacts/logs/boundary-check.log` |
| `node artifacts/f034-live-validate.mjs`（真实栈，只读 `/validate`） | **108 checks / 0 fail**（含 60 例 live 等价 + 30 例字节复现 + 认证） | `artifacts/logs/live-validate.log` |
| `python3 artifacts/f034-ui-browser-check.py`（真实浏览器 + 真实后端） | **18 checks / 0 fail** | `artifacts/logs/browser-check.log`（截图 `artifacts/logs/browser-text-carrier.png`，git-ignored） |

**F034 新增的 9 条 smoke 用例**（`npm run smoke:client` 输出原文，均已逐条 PASS）：① `pastedCsvFile / utf8ByteLength / isBlankImportText`；② `文本载体 multipart`（固定 filename / `format=csv` / 缺 filename 退化 422）；③ `指纹：file 载体与改动前等价`；④ `文本指纹：改 1 字符必换`；⑤ `importCarrierPatch / resourceInterfaceIpImportCarrierPatch`；⑥ `parseImportFormValues 文本载体`（空/空白、上限 −1/=/+1、format 与载体防御）；⑦ `parseResourceInterfaceIpImportFormValues 文本载体`；⑧ `两入口文本载体提交`（F023 URL/method/format/文件名一致）；⑨ `陈旧结果防护（T116）`。映射 T107–T116 见 §2.4（②→T108.1、④⑨→T116、⑤→T107.2/116.4、⑥⑦→T110/T111、⑧→T108/T109）。

### 2.7 B 层（真实浏览器）方法与边界（补充说明）

- 为什么不用 `npm run dev`：`frontend/vite.config.ts` **未配置** `/api/v1` 代理（注释明确「不配置任何代理目标」），dev server 无法真实打到后端；`csmtest-frontend-1` 运行的是实现前镜像。因此改为：`npm run build` 产物 → 本机静态服务（`127.0.0.1:4173`）→ Playwright/Chromium → `/api/v1/**` 由测试 harness 转发到**真实后端** `http://localhost:18080`。
- **不是 Mock**：所有响应来自真实后端；harness 仅做两件事：转发、并在转发时剥离浏览器 `Origin`/`Sec-Fetch-*`（后端 CSRF 中间件对「无这两个头的非浏览器客户端」放行，`app/core/csrf.py`）。该剥离已在脚本注释中声明。
- 边界（如实）：①`csmtest` 库无 Cluster，因此浏览器里的预校验返回**行级错误**而非 0 错误（`确认导入` 因此保持 disabled，符合两步流程）；本轮**未**在真实浏览器中完成一次成功写入（写入路径由 I 层覆盖）；②未做像素级视觉复核（截图仅留档）。
- 因此 TD3-T107.7 / TD3-T115.8 / TD3-T116.9 由「计划 NOT TESTED」升级为 **PASS（有真实浏览器证据）**；TD3-T115.8 的「网络面板核对」以「所有请求 URL 不含载荷 + 存储无载荷」实现。

### 2.8 Defects（缺陷清单）

| ID | Severity | Layer | Location | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | **未发现实现缺陷**：T107–T116 全部适用验收项通过；等价性 0 差异；无 FAIL 用例 | — | — | — |

**需记录但不构成必须修复项**（缺陷格式保留，`必须修复 = 否`）：

| ID | Severity | Layer | Location | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **DEV-1** | NOTE（测试文档精度） | TEST DESIGN / 断言过窄 | `test-report.md` §1 TD3-T112.1 与夹具 `F-15` | TD 断言「首行为数据行 → `reason === "header_missing"`」；实际既有实现返回 `unknown_columns`（附 `missing_columns`）。本次以 `F-15a`（首行空行）验证 `header_missing`、以 `F-15` 记录实际值 | 无产品影响：T112 只要求「422 + 对应原因 + 不静默忽略 + 不补表头」，两载体一致 | Tester（TD 措辞，已在本节修正记录） | 否 |
| **DEV-2** | NOTE（测试文档精度） | TEST DESIGN | TD3-T113.5 与夹具 `F-10` | TD 把「`total_rows` 与 `F-01` 相同」与「第 3 数据行错误报 row 4」写在同一条，但 `F-01` 只有 2 个数据行。本次拆为 `F-10`（尾随空行，`total_rows=2`）与 `F-10b`（3 数据行 + 尾随空行，错误 `row=4`）分别断言 | 无 | Tester | 否 |
| **DEV-3** | NOTE（既有行为观察） | 服务端已有规则 | `F-11`：引号内换行落在 `manufacturer` | TD 只预期 `hostname@row3` 一条错误；实际另有 `manufacturer@row2`「must not contain control characters」（既有 F014 字段规则，F034 未改） | 无产品影响（两载体一致）；提示「引号内换行」在既有实现中不被接受为合法字段值 | Architect / Product（如认为需支持，另立变更） | 否 |
| **NOTE-1** | NOTE | 前端本地拦截层 | `F-24`（仅 `U+FEFF`） | 前端 `trim()` 视 `U+FEFF` 为空白 → 本地拦截（不发请求）；服务端分支为 422 `empty_file` | 两者均拒绝且无写入；已由 Frontend 记为 `F034-FE-01`，TD-I-5 允许二者之一 | Architect（如需统一文案） | 否 |
| **NOTE-2** | LOW（信息暴露面，既有） | 服务端错误响应 | `IMPORT_INVALID_FILE.details.unknown_columns` / `missing_columns`（表头级） | 表头不合规时响应会回显「被当作表头的那一行单元格」，例如制表符分隔时 `unknown_columns` 含整行制表符拼接的表头文本；「首行即数据行」时含该数据行单元格 | 属 F014/F023 §1.2 **既有 schema**，两载体逐字段相同（契约附注 3 明确不得据此判 FAIL）；F034（前端-only）无法改变。仅影响「表头错误」这一路径，正常/判错行路径不回显内容 | Architect（如收紧，需另行变更提案） | 否 |
| **NOTE-3** | NOTE（范围说明） | 变更范围 | `docs/product/requirements-v3.md`（4 行） | 出现在 `33d8a03..717385b` 的 diff 中，超出 TD3-REG.1 白名单字面列举 | 内容为 revision 13 的 T114 编辑性澄清 + §35.1 确认记录，已由 CONTRACT Gate 批准并被 architecture §12 引用，属变更控制范围；建议由协调器在交接说明中确认，不需实现侧修改 | 协调器 / Architect | 否 |
| **NOTE-4** | NOTE（可验证性） | 测试设施 | `git status` 中 **74** 个未跟踪文件 | 全部为 Tester 本阶段新增（2 个测试模块 + corpus 62 个 + 7 个 artifact 脚本/JSON + 3 个顶层 artifact 脚本/JSON），日志目录被 `.gitignore` 忽略（见 §2.10） | 是否入库由协调器决定；不影响结论 | 协调器 | 否 |

### 2.9 未验证项 / 降级（如实登记）

| 项 | 状态 | 原因 / 替代证据 |
| --- | --- | --- |
| 真实 5 MiB 端到端请求（`F-21` 上限值本身的两载体实测） | **NOT TESTED** | 已在 TD-12 预登记；以「本地精确边界（U：−1/=/+1 与反空洞）」+「服务端小 limit 注入（I：355/356 字节）」覆盖比较语义 |
| `>1 MiB` 请求体 Starlette 匿名临时文件溢写路径 | **NOT TESTED** | 沿用既有边界（架构 ON-2），F034 未改变；**不声称「全路径不落盘」** |
| 摘要（FNV-1a+djb2）碰撞 | 不作证明（非可穷举） | 仅记 R-4；编辑路径已重置全部结果态 + 服务端写入前完整再校验（TD3-T116.7/8 已证） |
| 真实浏览器中的一次**成功写入**（确认导入 → 201） | **NOT TESTED** | `csmtest` 库无 Cluster，且按 TD-7 纪律不向该栈写业务数据；写入路径由 I 层（含并发、Audit、整批回滚）覆盖 |
| 像素级视觉复核（布局细节、字号、对比度） | **NOT TESTED** | 本轮结论来自 DOM/属性/几何断言；截图 `artifacts/logs/browser-text-carrier.png` 供人眼复核（Frontend 已另做过 1440/1024/768/375 多分辨率自测） |
| 真实剪贴板粘贴的 CRLF→LF 呈现（ON-1） | **NOT TESTED** | 等价性以「实际发送字节」为准，已用 `F-08`（CRLF）逐字节验证；浏览器剪贴板路径未实证 |
| 压力 / 持续并发（>2 连接、多轮冲突） | **NOT TESTED** | 仓库无压力设施；F034 无并发机制变更；以单次真并发（TD3-ATOM.4）为证 |
| 全量后端 pytest | **NOT TESTED**（按 TD-12 默认不跑） | 执行 TD-REG.7 定向套件（81 例既有 + 31 例 F034）；如需全量请协调器指示后补 |
| `.xlsx` 文本载体 | **NOT_REQUIRED** | 明确不做（§24.5），不提供该入口，故无验收项 |

### 2.10 证据文件与版本库状态（含 `.gitignore` 声明）

| 路径 | 类型 | 是否被忽略 |
| --- | --- | --- |
| `backend/tests/integration/test_f034_csv_text_carrier.py` | 新增集成用例（29 例） | 否（建议入库） |
| `backend/tests/integration/test_f034_csv_text_carrier_scope.py` | 新增 `real_scope` 用例（2 例，TD3-T115.3 / ATOM.3） | 否（建议入库；TD-15 允许的「按需 fixtures 辅助模块」范围） |
| `docs/features/F034/artifacts/corpus/{gen-corpus.mjs, F-*.txt, F-*.csv, boundary.json, corpus-manifest.json}` | 语料与生成脚本（62 文件） | 否（建议入库，否则测试不可复现） |
| `docs/features/F034/artifacts/{equivalence-observations.json, equivalence-observations-interface-ips.json, t114-unclosed-quote-observation.json, live-validate-results.json, browser-check-results.json}` | 结构化证据 | 否 |
| `docs/features/F034/artifacts/{f034-live-validate.mjs, f034-boundary-check.mjs, f034-ui-browser-check.py}` | 可重跑的验证脚本（凭据一律取自环境变量） | 否 |
| `docs/features/F034/artifacts/logs/**`（environment / typecheck / build / smoke-client / gen-corpus / pytest-f034-targeted / pytest-import-regression / live-validate / boundary-check / browser-check / backend-logs-since-marker / browser-text-carrier.png） | 命令原始输出 | **是**：`.gitignore:125 logs/`（另 `*.log`）。关键结论已内联进本节，若需入库须由协调器单独处理 |

- 未跟踪文件合计 **74** 个，全部为 Tester 本阶段产物；**未执行任何改变 Git 状态的命令**（无 `add` / `commit` / 分支 / merge / stash / reset）。
- 凭据核查：`grep -rn "testadmin\|***" docs/features/F034/artifacts/` → **0 命中**。

### 2.11 结论

**Status：`READY FOR REVIEW`**

- T107–T116 的**全部适用验收项 PASS**；TD3-REG.1–REG.9 与 TD3-ATOM.1–.6 PASS；**等价性 0 差异**（I 层 60 例 + H 层 60 例 + 字节层 30 例）。
- **无必须修复缺陷**；另有 3 条 TD 措辞偏差（DEV-1/2/3，均为测试文档精度，非实现缺陷）与 4 条 NOTE（含 1 条既有服务端信息暴露面 NOTE-2，建议由 Architect 决定是否另立变更）。
- 5 项 NOT TESTED 与 1 项 NOT_REQUIRED 已如实登记并附替代证据边界；`>1 MiB` 落盘路径与 5 MiB 端到端为**预登记的降级项，非缺陷**。
- 建议协调器：①按 `docs/project/git-workflow.md` 决定 artifacts（尤其 `corpus/`）与 2 个测试模块入库；②确认 NOTE-3（`requirements-v3.md` 4 行）属 CONTRACT Gate 批准范围；③把 NOTE-2 转交 Architect 评估是否需要在后续变更提案中收紧表头级 `details` 回显。

---

**Git 声明（TEST DESIGN 阶段，v1.1，保留原记录）**

GIT: git rev-parse --short HEAD
GIT: git rev-parse --abbrev-ref HEAD
GIT: git status --porcelain
GIT: git log --oneline 33d8a03..HEAD
GIT: git diff --stat 33d8a03..HEAD
GIT: git status --porcelain=v1 --untracked-files=all

**Git 声明（TEST 阶段，本阶段实际执行的只读命令，逐条列出）**
```text
GIT: git rev-parse --short HEAD
GIT: git status --short | head -50
GIT: git log --oneline -8
GIT: git diff --stat 33d8a03..HEAD
GIT: git diff --name-only 33d8a03..HEAD
GIT: git diff 33d8a03..HEAD -- docs/product/requirements-v3.md frontend/src/api/imports.ts frontend/package.json backend/ | head -60
GIT: git diff --stat 33d8a03..HEAD -- backend/app backend/alembic | wc -l
GIT: git diff --name-only 33d8a03..HEAD -- backend/ | wc -l
GIT: git diff 33d8a03..HEAD -- frontend/src/api/imports.ts | head -20
GIT: git diff --name-only 33d8a03..HEAD -- frontend/src/components/ImportErrorsTable.tsx frontend/src/components/ui/controls.tsx frontend/src/pages/ResourcesPage.tsx | wc -l
GIT: git diff --name-only 33d8a03..HEAD -- frontend/package.json frontend/package-lock.json | wc -l
GIT: git diff 33d8a03..HEAD -- frontend/src/components/importForm.ts | grep -E "^[-+]" | grep -vE "^[-+][-+]" | head -80
GIT: git diff 33d8a03..HEAD -- frontend/src/components/importForm.ts | grep -E "^[-+]" | grep -vE "^[-+][-+]" | sed -n '80,200p'
GIT: git diff 33d8a03..HEAD -- frontend/src/components/importForm.ts | grep -nE "^[-+].*(buildTemplateCsv|TEMPLATE_COLUMNS|BM_COLUMNS|VM_COLUMNS|IMPORT_MAX_ROWS|IMPORT_MAX_FILE_BYTES)"
GIT: git diff 33d8a03..HEAD -- frontend/src/components/resourceInterfaceIpImportForm.ts | grep -nE "^[-+].*(TEMPLATE|resourcetype|buildResourceInterfaceIp|canConfirm|IMPORT_MAX)"
GIT: git diff --name-only 33d8a03..HEAD
GIT: for f in frontend/src/api/imports.ts frontend/src/components/ImportErrorsTable.tsx frontend/src/components/ui/controls.tsx frontend/src/pages/ResourcesPage.tsx frontend/package.json frontend/package-lock.json; do git diff 33d8a03..HEAD -- "$f" | wc -l; done
GIT: git status --porcelain=v1 --untracked-files=all | head -60
GIT: git status --porcelain=v1 --untracked-files=all | tail -15
GIT: git status --porcelain=v1 --untracked-files=all | wc -l
GIT: git status --porcelain=v1 --untracked-files=all
GIT: git check-ignore -v docs/features/F034/artifacts/logs/smoke-client.log docs/features/F034/artifacts/corpus/F-01.csv docs/features/F034/artifacts/live-validate-results.json
GIT: git rev-parse --short HEAD
GIT: git rev-parse --abbrev-ref HEAD
```

（上列命令均为只读；本阶段**未**执行 `git add` / `commit` / 分支切换 / `merge` / `stash` / `reset` / `clean` 等任何改变 Git 状态的命令，工作区 74 个未跟踪文件全部为本阶段新增产物（另 `docs/features/F034/test-report.md` 为已跟踪文件的修改）。）
