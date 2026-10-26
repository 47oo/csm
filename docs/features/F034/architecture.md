# F034 导入 CSV 文本载体 — ARCHITECTURE 阶段报告

- **状态**：READY FOR DESIGN
- **版本**：v1（2026-10-26）
- **上游依据**：
  - `docs/product/requirements-v3.md` **revision 13**：§24.5（CONFIRMED，全节）、§24 / §24.1（两种导入模板与两步流程，未改动）、§23 / §23.2（`IMPORT` 权限与集群范围行级校验）、§22（Audit）、§31 验收表 **T107–T116** 及修订后的 T28、§32、§35.1 revision 13 确认记录。
  - 用户裁定（CONFIRMED，记录于 `docs/project/project-plan.yaml` `decisions_required`）：**CHG012-BQ01 = A**（F014 资源导入与 F023 资源+网卡+IP 导入两个入口**并列**新增「粘贴 CSV 文本」载体，文件上传保留、不替换）；**CHG012-BQ02 = A**（文本须自带与冻结模板逐字逐序一致的表头、仅逗号分隔、不做分隔符嗅探、不自动补表头、不做列名映射）。
  - 计划与授权：`docs/project/project-plan.yaml` plan_revision 20（`project.approval` 用户 2026-10-26 批准；`execution.authorization.feature_ids=[F034]`）；F034 `depends_on` F014 / F023（均 DONE）；分支 `feature/F034-csv-text-import`，base `v3.3`，start_commit `33d8a03`。
  - PRODUCT：`docs/features/F034/product.md` v1（READY FOR ARCHITECT；A 项与 T107–T116 映射，Blocking Questions = None）。
  - 提案与既有评估：`docs/project/proposals/CHG-012-csv-text-import.md` §3.2 / §4（Architect 前一轮评估：文本 → CSV 字节复用既有 multipart，服务端零代码变更；两契约各加「加法引用」增补节）。
  - 消费的既有 Contract（只读，不改正文版本）：`docs/api/F014.md` v1（§1.1 权限、§1.2 错误码与 `reason` 集合、§2 请求形状、§3/§4 两步端点、§6 模板、§7 解析与行号、§8 原子性与再校验、§10 上限）、`docs/api/F023.md` v1（§1–§4、§6 26 列、§7 行号、§12 原子性/锁序）、两文件既有「F027 范围语义（加法引用）」增补节先例。
  - 代码基线（只读核对，零改动）：`frontend/src/api/imports.ts`、`frontend/src/components/{ResourceImportPanel.tsx,ResourceInterfaceIpImportPanel.tsx,importForm.ts,resourceInterfaceIpImportForm.ts,ImportErrorsTable.tsx,ui/controls.tsx}`、`frontend/scripts/smoke-client.mjs`、`frontend/src/index.css`、`backend/app/api/v1/imports.py`、`backend/app/services/resource_import.py`、`backend/app/services/resource_interface_ip_import.py`。
- **范围**：仅前端输入载体维度 + `docs/api/F014.md` / `docs/api/F023.md` 两份「加法引用」增补节。不改后端、数据库、权限、Audit、模板、上限与错误码。

---

## 1. 方案摘要

文本载体不产生任何新的数据路径。它只决定 multipart `file` 部分**由谁生成**：

| 维度 | 文件载体（既有，不变） | 文本载体（新增） |
| --- | --- | --- |
| `file` 部分来源 | `<input type="file">` 选中的 `File` | `new File([text], "<固定常量名>", { type: "text/csv;charset=utf-8" })` |
| `format` 部分 | 用户选择 `csv` \| `xlsx` | 恒 `csv`（UI 只读） |
| 端点 | `/imports/resources{/validate}`、`/imports/resource-interfaces-ips{/validate}` | 同一端点、同一方法、同一 multipart 形状 |
| 解析 / 表头 / 行号 / 错误 / 上限 / 权限 / 范围 / Audit / 原子性 | 服务端权威，不变 | 完全一致（同字节 ⇒ 同响应） |
| 前端职责边界 | 非权威前置提示（空输入、超上限、扩展名） | 非权威前置提示（空/纯空白、UTF-8 字节超上限）；**不做 CSV 解析、不补表头、不嗅探、不改行尾、不加 BOM** |
| 陈旧结果防护 | 指纹 `format:文件名:大小:修改时间` | 指纹扩展为 `carrier:format:<payload>`，文本 payload = 内容摘要 + UTF-8 字节长度 |

因此 layers 判定为 `frontend=true` / `backend=false` / `database=false`，`api_required=true` 但**只以增补节形式存在**，且本阶段为 **PROPOSED**（CONTRACT 阶段在 Test Design 到位后签核为 READY）。

---

## 2. 模块边界

| 边界 | 文件 | 动作 |
| --- | --- | --- |
| 载体原语（纯逻辑，无 JSX/React/antd） | `frontend/src/components/importCarrier.ts` | **新增**：载体类型、固定文件名/MIME 常量、文本→`File` 构造、UTF-8 字节计量、摘要、载体感知指纹组合 |
| F014 表单纯逻辑 | `frontend/src/components/importForm.ts` | 扩展：表单值加 `carrier` / `text`；`parseImportFormValues` 返回构造后的 `File`；`importTargetKey` 改走载体感知指纹；新增 `importCarrierPatch` |
| F023 表单纯逻辑 | `frontend/src/components/resourceInterfaceIpImportForm.ts` | 同上（保持两模块既有「各自镜像」的写法，共享原语来自 `importCarrier.ts`） |
| F014 面板 UI | `frontend/src/components/ResourceImportPanel.tsx` | 载体选择、条件渲染文件 / 文本域、format 只读、字节计数提示、切换重置、写入时按当前载体取 `File` |
| F023 面板 UI | `frontend/src/components/ResourceInterfaceIpImportPanel.tsx` | 同上（文案与模板提示按 26 列宽模板调整） |
| 样式 | `frontend/src/index.css` | 追加少量语义类（文本域高度/等宽、字节计数、载体说明），沿用 `--csm-*` token，不新增 `.ant-*` 选择器 |
| 机制级冒烟 | `frontend/scripts/smoke-client.mjs` | 追加 F034 段（纯逻辑断言 + `File`/`FormData` 断言）与文件头说明 |
| API 客户端 | `frontend/src/api/imports.ts` | **零逻辑改动**：不新增函数、不改签名、不改 wire 形状（允许纯注释引用增补节，不得改变类型或行为） |
| 错误呈现 | `frontend/src/components/ImportErrorsTable.tsx`、`describeImportError` | **零改动**（`RowError` 形状、reason 文案、整批回滚文案不变） |
| 共享 UI 适配层 | `frontend/src/components/ui/controls.tsx` | **零改动**（复用现有 `Button` / `Input` / `Select` / `TextArea` / `DataTable`，不新增 Radio/Segmented 适配） |
| 权限入口 | `frontend/src/pages/ResourcesPage.tsx` | **零改动**（两面板的 `IMPORT` 门控与 `onImported` 刷新不变） |

---

## 3. 前端设计（逐文件工作项）

### 3.1 载体模型与表单值

`importForm.ts` / `resourceInterfaceIpImportForm.ts` 的表单值统一扩为：

```ts
export type ImportCarrier = "file" | "text";          // 定义在 importCarrier.ts，两模块复用

export interface ImportFormValues {
  carrier: ImportCarrier;   // 默认 "file"
  format: ImportFormat;     // carrier="text" 时恒为 "csv"
  file: File | null;        // carrier="file" 时有效
  text: string;             // carrier="text" 时有效；原始粘贴内容，不 trim
}

export type ImportFormFieldKey = "carrier" | "format" | "file" | "text";
```

- 服务端 422 点路径映射**不变**：`importFormFieldFromPath("format") === "format"`，其余返回 `null`；不新增字段映射（本地 `text` 错误只在本地出现）。
- 本地错误文案归属：文本载体的空输入/超限错误落在 `errors.text`，文件载体仍落 `errors.file`；`errors.carrier` 仅用于防御非法载体值。

### 3.2 文本 → `File` 构造与 UTF-8 字节计量（`importCarrier.ts`）

```ts
export const PASTED_CSV_FILE_NAME = "csm-pasted-import.csv";
export const PASTED_CSV_MIME_TYPE = "text/csv;charset=utf-8";

export function pastedCsvFile(text: string): File            // new File([text], PASTED_CSV_FILE_NAME, { type: PASTED_CSV_MIME_TYPE })
export function utf8ByteLength(text: string): number         // 同步；TextEncoder 编码后长度（非 String.length）
export function isBlankImportText(text: string): boolean     // text.trim() === ""
export function importTextDigest(text: string): { digest: string; byteLength: number }
export function fileImportTargetKey(format: ImportFormat, file: File): string
export function textImportTargetKey(text: string): string
```

必须点：

1. **必须带 filename**：`FormData.append("file", file, file.name)` 缺 filename 会让 FastAPI 把该 part 解析成普通表单字段，得到 422 `VALIDATION_ERROR{field:"file"}`（语义错误、误导用户）。固定常量名，不掺时间戳、用户输入或内容摘要。
2. 服务端**不读取 filename**（`resource_import.py` 只按 `data` + `format` 解析），固定名不进入任何错误文案或行号口径。
3. **UTF-8 字节**而非字符数：`utf8ByteLength` 用于本地 gate 与文档展示；`File.size` 与之一致，但 gate 显式走 `utf8ByteLength` 以避免依赖隐式编码假设，测试须含中文/emoji 用例。
4. **不加 BOM**：不主动插入 `\uFEFF`；若粘贴内容本身以 `\uFEFF` 开头则原样提交（服务端 `utf-8-sig` 解码，与文件载体同口径）。
5. **不做本地归一化**：不 trim payload、不改行尾、不转义、不合并空白、不补尾部换行。文本域控件可能把行尾呈现为 LF（浏览器行为），服务端按同一逻辑记录切分口径处理 CRLF/LF/混用，两种载体行号一致。
6. 构造是**确定性的**：同一 `text` 每次都得到同一字节序列，因此写入阶段重新构造即为「重新提交同一内容」。

### 3.3 本地前置拦截边界（非权威）

```ts
export function parseImportFormValues(values: ImportFormValues):
  | { ok: true; file: File }
  | { ok: false; errors: ImportFormErrors };

export function importCarrierPatch(
  values: ImportFormValues, carrier: ImportCarrier,
): Partial<ImportFormValues>;   // → { carrier, format: carrier === "text" ? "csv" : values.format }
```

| 载体 | 本地拦截 | 明确**不**拦截 |
| --- | --- | --- |
| `text` | ① 载体非法值（防御）；② `isBlankImportText(text)`（空 / 纯空白）→ 不发请求；③ `utf8ByteLength(text) > IMPORT_MAX_FILE_BYTES`（严格大于，等于放行）→ 不发请求；④ `format !== "csv"`（防御） | 表头存在性 / 列集 / 列序、分隔符、行数、CSV 语法、引号闭合、BOM、行尾、枚举与整数合法性、批内重复与现存冲突 |
| `file` | 既有三条不变：未选文件、`file.size > IMPORT_MAX_FILE_BYTES`、`format=xlsx` 且扩展名非 `.xlsx` | 同上 |

- 字节上限语义值唯一来源为 `api/imports.ts` 的 `IMPORT_MAX_FILE_BYTES`（5,242,880，F014 §10 签核值）；**不新增常量、不新增配置项、不改值**。
- `IMPORT_MAX_ROWS` **不在前端镜像**：两种载体都不做本地行数拦截，行数超限由服务端 413 `IMPORT_ROW_LIMIT_EXCEEDED` 权威判定（面板说明文字可继续陈述该上限，但不作为 gate）。
- 空/纯空白判定用 `trim()`，**payload 不 trim**。

### 3.4 指纹扩展算法（T116）

```ts
// file 载体：carrier 前缀 + 原有三要素（语义等价，不新增字段）
fileImportTargetKey(format, file) => `file:${format}:${file.name}:${file.size}:${file.lastModified}`

// text 载体：carrier + 固定 format + 内容摘要 + UTF-8 字节长度
textImportTargetKey(text) => `text:csv:${digest}:${byteLength}`
```

- **摘要算法（PROPOSED 实现选择）**：同步双 32 位非加密哈希（FNV-1a 与 djb2，均按 UTF-16 code unit 迭代），输出 `${fnv1a.toString(36)}-${djb2.toString(36)}`，与 UTF-8 字节长度拼接。**禁止** `crypto.subtle`（异步会破坏既有同步校验路径与门控时机）；不新增 npm 依赖。
- 门控不变：`validatedKey !== null && validatedKey === currentKey` 且 `error_count === 0` 且本次导入未成功，才允许「确认导入」。文本载体下**改 1 个字符（含非 ASCII）必换指纹**（测试强制项）。
- 摘要碰撞为理论风险（R-4）：正常编辑路径上任何文本变化都经 `changeInput` 重置全部结果态，指纹是第二道防线；写入端点始终服务端完整再校验，权威结论不依赖前端指纹。

### 3.5 `format` 只读与切换重置

- `carrier === "text"` 时：format `Select` 设为 `disabled`，值恒 `"csv"`，选项文案同现有 CSV 项；不渲染 `.xlsx` 语义提示。
- 载体切换：`changeInput(importCarrierPatch(values, next))`。切到 `text` 强制 `format="csv"`；切回 `file` 保持 `"csv"`（**不回填**历史 `xlsx`，避免「以为在上传 xlsx 实际是文本」类误判）。
- `changeInput`（既有）继续承担重置：任何 `carrier` / `format` / `file` / `text` 变化 → `localErrors = {}`、`validateState = idle`、`importState = idle`、`validatedKey = null`。
- 两个载体的输入内容（已选文件、已粘贴文本）**保留在组件 state**（切换不丢内容），但结果失效、必须重新预校验；面板卸载即丢失全部内容与结果，不做任何持久化。

### 3.6 UI 结构（两面板一致）

1. **载体选择**：复用现有 `Select`（`importCarrierField`，不引入 Radio/Segmented），选项「上传文件（CSV / .xlsx）」「粘贴 CSV 文本（仅 CSV）」，`disabled={busy}`。
2. **文件分支**：现有 `<input type="file">` + `accept` 逻辑原样保留。
3. **文本分支**：
   - `<TextArea id=... rows={10} spellCheck={false} placeholder=... />`（`ui/controls.tsx` 现有适配层；`rows={10}` 使 `minRows === maxRows === 10`，固定高度、内部滚动，不改适配层）。
   - 提示：**仅逗号分隔**；**必须包含与模板逐字逐序一致的表头**（可先用「查看模板与逐列说明 / 下载 CSV 模板（表头行）」取得表头）；不自动补表头、不识别制表符分隔（从 Excel 直接复制可能失败，属已确认口径）。
   - 字节计数（非权威、纯展示）：`UTF-8 字节数 / 5,242,880`，超限时以 `errors.text` 明确「不发请求」并说明服务端同口径 413。
4. **结果区**：预校验/写入四态、`ImportErrorsTable`、整批回滚文案**零改动**。
5. **无障碍**：`label htmlFor` 关联文本域、错误 `role="alert"`、请求中保持 `disabled`、字节计数经 `aria-describedby` 关联（不替代错误播报）。

---

## 4. 技术决策

| ID | 决策 | 状态 | 依据 |
| --- | --- | --- | --- |
| **DR-F034-01** | 载体维度进入两个面板的表单值与 UI：`carrier: "file" \| "text"`，文本载体与文件载体**并列**（文件上传递 `.xlsx` 行为零改动） | CONFIRMED | 需求 §24.5；CHG012-BQ01=A；T107 |
| **DR-F034-02** | 文本 → `File` 后走**既有** multipart 端点（`file` binary + `format`），不新增端点、查询参数或请求字段 | CONFIRMED | 需求 §24.5「不新增平台 API」；F014 §2、F023 §2 |
| **DR-F034-03** | 构造 `File` 必须带固定常量文件名 `csm-pasted-import.csv` 与 `text/csv;charset=utf-8`；常量集中在 `importCarrier.ts` | CONFIRMED（REQUIRED：缺 filename 会退化为 422 `VALIDATION_ERROR`） | F014 §1.2/§2；`backend/app/api/v1/imports.py` |
| **DR-F034-04** | 字节计量按 **UTF-8 编码字节**（`utf8ByteLength`），严格大于 `IMPORT_MAX_FILE_BYTES` 才拦截；上限值复用既有常量 | CONFIRMED | 需求 §24.5；T111；F014 §10 |
| **DR-F034-05** | 本地只拦截：载体非法值、空/纯空白（`trim` 判定）、字节超限、`text` 载体下 `format !== "csv"`；其余交服务端；payload 不 trim | CONFIRMED | T110 / T111；需求 §24.5 |
| **DR-F034-06** | 前端不镜像行数上限、不做任何 CSV 解析（表头/分隔符/引号/行尾/BOM/枚举） | CONFIRMED | 需求 §24.5；CHG012-BQ02=A；T112–T114 |
| **DR-F034-07** | `text` 载体强制 `format="csv"` 且 UI 只读；切回 `file` 不回填历史 `xlsx` | CONFIRMED（text⇒csv）/ PROPOSED（不回填） | 需求 §24.5；T107 |
| **DR-F034-08** | 指纹扩展为 `carrier:format:<payload>`；file payload 保留 `name:size:lastModified`，text payload = `digest:byteLength` | CONFIRMED | T116 |
| **DR-F034-09** | 摘要实现：同步双 32 位哈希（FNV-1a + djb2），禁止异步 `crypto.subtle`，不新增依赖 | PROPOSED | 实现选择；见 R-4 |
| **DR-F034-10** | 载体/格式/文件/文本任一变化 → 复用既有 `changeInput` 重置结果态；已输入内容保留、结果失效 | CONFIRMED（重置结果）/ PROPOSED（保留内容） | T116 |
| **DR-F034-11** | 写入阶段由当前载体**重新构造/重取** `File`，不缓存字节；同一 `text` ⇒ 同一字节 ⇒ 服务端完整再校验 | CONFIRMED | F014 §4/§8、F023 §12.2；T108 |
| **DR-F034-12** | 不新增 npm 依赖、不改 `ui/controls.tsx`、不改 Ant 主题：文本域用现有 `TextArea`（`rows={10}`），载体选择复用现有 `Select` | PROPOSED | `frontend-ui` skill；`frontend/package.json` |
| **DR-F034-13** | 粘贴内容仅存组件 state；禁止写入 storage/URL/console/错误文案；不新增响应字段或错误码 | CONFIRMED | 需求 §24.5「不持久化」；T115 |
| **DR-F034-14** | 契约以 F014 / F023 各一节「CSV 文本载体（加法引用）」增补节 v1 承载，正文版本不提升（照 F027 先例）；CONTRACT 阶段签核 READY | CONFIRMED（形式）/ PROPOSED（当前未签核） | CHG-012 §3.2 |
| **DR-F034-15** | 载体原语集中到新纯逻辑模块 `importCarrier.ts`，两调用方共享；不建通用导入框架 | PROPOSED | AGENTS.md §2.3/§2.6 |
| **DR-F034-16** | 文本域旁必须写明「仅逗号分隔、须含模板一致表头、可先下载模板表头、不自动补表头/不嗅探」，并显示非权威 UTF-8 字节计数 | PROPOSED | CHG012-BQ02=A 的用户可操作性；T112 |
| **DR-F034-17** | 机制级冒烟采用纯逻辑断言（不引入 DOM 环境）：`FormData` 中 `file` 的 `name`/`size`/`type`、文本字节数（含中文）、改 1 字符换指纹、空/纯空白与超限返回 `ok:false` 且不构造请求 | PROPOSED | 既有 `smoke:client` 基线 |
| **ON-1** | 文本域行尾由浏览器控件呈现（通常 LF）；「等价性」以**实际发送的字节**为准，不以剪贴板原始 CRLF 字节为准；不因此新增前端归一化 | OPEN（记录，不构成验收判据） | 需求 §24.5 等价性 + 浏览器行为 |
| **ON-2** | 「不落盘」沿用既有文件上传边界（>1 MiB 请求体由 Starlette 溢写匿名临时文件后即抛）；F034 不改变该层，不新增保证 | OPEN（沿用既有边界） | CHG-012 §4.4 LOW 风险 |

---

## 5. `layers`、`api_required` 与 Contract 状态

```yaml
layers:
  database: false    # 无 Schema / Migration / 索引 / 约束变更
  backend:  false    # 无后端源码变更（端点已按 multipart 接收任意 CSV 字节）
  frontend: true
api_required: true   # 仅 F014 / F023 各加一节「加法引用」增补节；正文版本不提升
```

| Contract 对象 | 本阶段状态 | 说明 |
| --- | --- | --- |
| `docs/api/F014.md` §「CSV 文本载体（加法引用）」 | **PROPOSED**（待 CONTRACT 阶段签核 READY） | 草案见该文件增补节 |
| `docs/api/F023.md` §「CSV 文本载体（加法引用）」 | **PROPOSED**（待 CONTRACT 阶段签核 READY） | 草案见该文件增补节 |
| 端点 / 字段 / `RowError` / `reason` 集合 / 上限 / 权限矩阵 / F027 范围语义 | **不变** | 无新增、无删改 |

---

## 6. 明确不改动的面

| 面 | 结论 | 核对依据 |
| --- | --- | --- |
| 后端路由 `backend/app/api/v1/imports.py` | 零改动：两端点签名为 `file: UploadFile = File(...)` + `format: str = Form(...)`，直接 `file.file.read()` | 文件实读 |
| 后端服务 `resource_import.py` / `resource_interface_ip_import.py` | 零改动：`_parse_csv` 用 `utf-8-sig` + `csv.reader(newline="")`；上限按 `len(data)` 字节；表头精确匹配；行号表头第 1 行 | 文件实读 |
| 数据库 / Migration / 索引 / 约束 | 零改动 | 无 Schema 影响 |
| 权限（`IMPORT` / `READ`）与 §23.2 集群范围行级校验 | 零改动：VIEWER 仍 403、未认证 401、范围外行整批失败 | F014 §1.1、F023 §1.1 |
| Audit（§22）与整批原子性 | 零改动：按对象 CREATE，回滚无残留；文本内容不进 Audit / 日志 / 错误响应 | F014 §4、F023 §4/§12 |
| 模板（BM 14 / VM 10 / 统一 26 列）、`format` 语义、上限值、错误码与 `reason` 集合 | 零改动 | F014 §1.2/§6/§10、F023 §1.2/§6/§14 |
| `api/imports.ts`、`ImportErrorsTable.tsx`、`describeImportError`、`ui/controls.tsx`、`ResourcesPage.tsx` | 零改动 | §2 模块边界 |
| 采集脚本 `scripts/collect_host_info.py`、`deploy/**` | 零改动 | CHG-012 §4.1 |

---

## 7. 事务与并发口径（沿用，服务端权威）

1. **两步流程不变**：文本载体同样「预校验 → 用户确认 → 写入端点重新提交同一内容并完整再校验」；前端不提供跳过预校验的路径。
2. **不引入前端事务概念**：写入时重新构造 `File` 并重发全部字节（DR-F034-11）；服务端在同一 DB 事务内完成解析、再校验、写入、Audit 与 commit/rollback。
3. **并发与锁序不变**：F014 的 hostname 唯一兜底 + VM Host `FOR UPDATE`、F023 的确定性锁序与 40P01 兜底均不受载体影响；预校验只读、不加锁。
4. **重复确认语义不变**：导入成功后按钮禁用；同一内容再次导入由服务端按 unique / 现存冲突整批拒绝。
5. **超限/失败零残留**：本地拦截不发请求（无写入、无 Audit）；服务端 413/422 仍整批拒绝。

---

## 8. 验证策略

| 组 | 断言 | 映射 |
| --- | --- | --- |
| 载体并列与文件零回归 | 两面板同时提供文件与文本载体；文件载体 `.xlsx`、模板查看/下载、四态呈现、扩展名与大小本地提示不变 | T107、T27、T28、T72、T89 |
| 文本两步流程 | 合法文本预校验返回 `total_rows` / `importable_rows` / `error_count`；仅 0 错误可确认；写入时重新提交同一字节并再校验；行号表头第 1 行 | T108 |
| 行错误同形状 | 枚举/整数/长度/批内重复/现存冲突/集群范围外 → `row` / `field` / `reason` / `related_row` 与文件载体一致，不 fail-fast | T109 |
| 本地前置拦截 | 空/纯空白：`parse*` 返回 `ok:false` 且不发请求；仅表头无数据行 → 服务端 422 `IMPORT_INVALID_FILE{empty_file}`；无写入、无 Audit | T110 |
| 上限 | UTF-8 字节超 5,242,880 → 本地拦截（不发请求）；等值放行；行数 > 5000 不在本地拦截、服务端 413 `IMPORT_ROW_LIMIT_EXCEEDED`；超限无部分导入 | T111、T28 |
| 表头严格性 | 缺表头 / 缺列 / 未定义列 / 列序不符 → 422 对应 reason；制表符分隔被拒（不嗅探）；不补表头 | T112 |
| 编码与行尾 | 无 BOM 生成；粘贴内容自带 `U+FEFF` 原样提交（服务端 `utf-8-sig`）；CRLF/LF/混用与尾部空行按服务端口径 | T113 |
| CSV 字段边界 | 逗号/双引号/引号内换行按标准 CSV 解析且不改写；引号未闭合 → 既有文件级错误 | T114 |
| 权限 / 范围 / 审计 / 不留痕 | VIEWER 403、未认证 401；含未授权集群行整批失败并行号+权限原因；Audit 同口径；文本不进 Audit/日志/错误响应/storage/URL/console | T115 |
| 陈旧结果防护 | 改文本 1 字符、文件↔文本互切、改 format → `validatedKey !== currentKey`，「确认导入」不可用；同一内容重复预校验结果一致 | T116 |
| 等价性 | 同一 CSV 字节分别以文件载体与文本载体提交，`/validate` 与写入响应逐字段一致（真实后端） | T108、T114 |
| 静态守卫 | `api/imports.ts` / `ui/controls.tsx` / 后端 / 数据库 / 模板常量零 diff；无新增 npm 依赖；无 `crypto.subtle` | CHG-012 §4.1；AGENTS.md §5 |

执行命令（Frontend 实施后必跑）：`cd frontend && npm run typecheck && npm run build && npm run smoke:client`；端到端仅在 `compose.test.yaml` + `-p csmtest`（`http://localhost:18080`）使用只读 `/validate` 与受控写入用例，环境不可用时由 Test 明确标 `NOT TESTED`，不得以单测或构建代替。

**Test 输入要点（交 Tester）**：
1. 两套模板各一份合法文本（BM 14 列、VM 10 列、统一 26 列混排），并各配一份**逐字节相同的 `.csv` 文件**用于等价性对照。
2. 必须包含：无 BOM 文本、含 `U+FEFF` 开头文本、CRLF 文本、尾部多空行文本、引号内换行文本、未闭合引号文本、制表符分隔文本（预期 422）、缺表头文本、列序交换文本、多余列文本。
3. 字节上限：构造 >5,242,880 字节文本验证本地拦截不发请求；限额−1 / 限额 / 限额+1 验证严格大于口径。
4. 行数上限：5000 与 5001 行文本验证仅服务端 413，且无部分写入、无 Audit 残留。
5. 非 ASCII 计量：含中文/emoji 的小文本对照 `String.length` 与 UTF-8 字节数差异，验证 gate 用字节、且指纹随 1 个非 ASCII 字符变化。
6. 陈旧结果：预校验通过后（i）改 1 字符（ii）切换载体（iii）切换 format（防御分支），均断言「确认导入」不可用。
7. 权限：VIEWER 会话调 `/validate` 与写入均 403；未认证 401；含未授权集群行的文本整批失败。
8. 浏览器行为（E2E 或人工留证）：文本域行尾呈现、字节计数显示、错误 `role="alert"`、`disabled` 请求态、切换载体后结果区回到空态。

---

## 9. 风险与兼容性

| ID | 风险 | 级别 | 处理 |
| --- | --- | --- | --- |
| R-1 | 指纹未扩展 → 改了文本仍可确认导入 | HIGH | DR-F034-08/10 + smoke「改 1 字符必换指纹」+ T116 必测 |
| R-2 | 用字符数而非 UTF-8 字节计量 → 含中文文本误拦/误放 | HIGH | DR-F034-04；测试必须含非 ASCII 用例 |
| R-3 | `File` 缺 filename → 用户看到无关 422 `VALIDATION_ERROR{field:"file"}` | MEDIUM | DR-F034-03；smoke 断言 `FormData.get("file").name` 等于常量 |
| R-4 | 摘要碰撞使理论上的旧结果被沿用 | MEDIUM | DR-F034-09：双哈希 + 字节长度；编辑即重置；服务端再校验为权威 |
| R-5 | 浏览器把粘贴的 CRLF 呈现为 LF，视觉相同但字节不同 | MEDIUM | ON-1：等价性按发送字节判定；测试以构造的字节序列为准 |
| R-6 | 文本载体下仍尝试 `.xlsx` | MEDIUM | DR-F034-07：format 固定只读 + 切换即重置 |
| R-7 | 从 Excel 复制得到制表符分隔文本，BQ02=A 下反复失败 | MEDIUM | DR-F034-16：UI 明示「仅逗号分隔、须含表头、可先下载模板表头」；嗅探需求另立变更 |
| R-8 | 「不落盘」表述夸大 | LOW | ON-2：如实沿既有边界，不加新保证 |
| R-9 | 两面板重复实现导致漂移 | MEDIUM | DR-F034-15 载体原语单点 + 两侧 smoke 同一组断言 |
| R-10 | 长文本粘贴导致文本域高度/内存问题 | LOW | `rows={10}` 固定高内部滚动；5 MiB gate 约束 |
| R-11 | 增补节未签核即被视为实施依据 | MEDIUM | 增补节显式标 PROPOSED；CONTRACT 签核后才放行实现 |

**明确不改**：F014/F023 端点、字段、模板、上限、错误码与 `reason`、权限矩阵、F027 范围语义、CSRF、审计；后端/数据库/部署；`ui/controls.tsx` 与 Ant 主题；既有 F014/F023 test/review 证据。

---

## 10. 工作分工与 Implementation Layers

| 层 | 值 | 负责角色 | 交付 |
| --- | --- | --- | --- |
| 数据库 | `false` | Database（`NOT_REQUIRED` 签核） | 仅出具 `NOT_REQUIRED` 结论 |
| 后端 | `false` | Backend（零改动确认） | 在 implementation 报告中确认 `backend/app/**` 零 diff；无 Schema 变更需承接 |
| 前端 | `true` | Frontend | `importCarrier.ts`（新增）、`importForm.ts`、`resourceInterfaceIpImportForm.ts`、两面板 `.tsx`、`index.css`；`api/imports.ts` 零逻辑改动 |
| 测试 | — | Tester | `frontend/scripts/smoke-client.mjs` F034 段（协调器划定文件所有权）+ 真实后端 `/validate` 对照与权限用例 |
| 契约 | `api_required=true` | Architect | 两节在 CONTRACT 阶段签核 READY，并将签核记录写入两份契约的增补节与修订表 |

**Implementation Layers**：`L1` 纯逻辑（`importCarrier.ts` + 两 form 模块 + smoke）→ `L2` UI（两面板 + `index.css`）→ `L3` 契约签核（依赖 Test Design）→ `L4` 实现后验证与回归。`L1` 与 `L3` 可并行，`L2` 依赖 `L1`。

---

## 11. 结论

方案完全落在 §24.5 与 T107–T116 的已确认边界内：不新增业务规则、不新增端点/字段/错误码/上限、不改后端与数据库，`format` 语义与模板冻结不变；两入口并列新增文本载体且文件载体零回归。**READY FOR DESIGN**。

## 12. 定稿签核

- **状态**：待 CONTRACT 阶段填写（取得 Database `NOT_REQUIRED` 结论与 Test Design 后，由 Architect 核对一致性并签署 `READY FOR IMPLEMENTATION`，同时把两份契约增补节由 PROPOSED 签核为 READY）。
- **变更边界**：定稿后若 T107–T116、模板、上限、错误码或权限语义变化，本设计与契约增补节需重新核对并重新签核。
