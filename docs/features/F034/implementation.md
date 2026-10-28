# F034 导入 CSV 文本载体 — IMPLEMENTATION 阶段报告

- **状态**：FRONTEND COMPLETE；BACKEND NOT_REQUIRED（零改动，见 §2）；DATABASE NOT_REQUIRED（见 §2）
- **版本**：v1（2026-10-26）
- **上游依据**：
  - `docs/features/F034/architecture.md` v1（§12 定稿 `READY FOR IMPLEMENTATION`，2026-10-26）
  - `docs/api/F014.md` / `docs/api/F023.md` §「CSV 文本载体（加法引用）」增补节 v1（**READY**，Architect 签核 2026-10-26，含 3 条解释性裁定附注）
  - `docs/features/F034/test-report.md` §1 TEST DESIGN v1.1（`TEST DESIGN READY`）
  - `docs/product/requirements-v3.md` revision 13 §24.5、§31 T107–T116；CHG012-BQ01 = A、CHG012-BQ02 = A
  - plan_revision 20；分支 `feature/F034-csv-text-import`（start_commit `33d8a03`）

## 1. 前端实现（FRONTEND COMPLETE）

| 文件 | 动作 | 要点 |
| --- | --- | --- |
| `frontend/src/components/importCarrier.ts` | 新增（纯逻辑，无 JSX/React/antd） | `ImportCarrier`；`PASTED_CSV_FILE_NAME="csm-pasted-import.csv"`；`PASTED_CSV_MIME_TYPE="text/csv;charset=utf-8"`；`pastedCsvFile`；`utf8ByteLength`（TextEncoder，非 `String.length`）；`isBlankImportText`；`importTextDigest`（同步 FNV-1a + djb2，不使用 `crypto.subtle`）；`fileImportTargetKey`（`file:<format>:<name>:<size>:<lastModified>`）；`textImportTargetKey`（`text:csv:<digest>:<byteLength>`） |
| `frontend/src/components/importForm.ts` | 扩展 | 表单值 `{carrier, format, file, text}`；`emptyImportFormValues` 默认 `carrier:"file"`、`text:""`；`parseImportFormValues` 返回 `{ok:true,file}` / `{ok:false,errors}`；`importCarrierPatch`；指纹载体感知；错误键 `carrier/format/file/text`；**既有文件载体三条本地校验与 `importFormFieldFromPath` 未改** |
| `frontend/src/components/resourceInterfaceIpImportForm.ts` | 扩展 | 同上镜像（`resourceInterfaceIpImportCarrierPatch`、`resourceInterfaceIpImportTargetKey`）；26 列表头常量与 `canConfirmResourceInterfaceIpImport` 未改 |
| `frontend/src/components/ResourceImportPanel.tsx` | UI | 载体 `Select`（上传文件 / 粘贴 CSV 文本）；文件分支原样；文本分支共享 `TextArea`（`rows={10}`、`spellCheck={false}`）+ 提示（仅逗号分隔、须含与模板逐字逐序一致表头、可先查看/下载模板表头、不自动补表头、不识别制表符）+ 非权威 UTF-8 字节计数（`/ 5,242,880`）；`carrier==="text"` 时 format `Select` 只读且值恒 `csv`；写入时按当前载体重新构造 `File` |
| `frontend/src/components/ResourceInterfaceIpImportPanel.tsx` | UI | 同上（提示按 26 列宽模板；列数取自 `RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS.length`） |
| `frontend/src/index.css` | 追加 26 行 | 仅 `.import-carrier-textarea` / `.import-carrier-hint` / `.import-carrier-counter`，使用 `--csm-*` token，无 `.ant-*` 选择器，未触碰 F033/F014/F023 既有规则 |
| `frontend/scripts/smoke-client.mjs` | 追加 + 最小修订 | 新增 F034 段 9 条机制级用例（文本→`File` 的 name/type/UTF-8 字节、`FormData` part 带 filename、载体与内容变化必换指纹、文件载体指纹等价回归、空/纯空白与上限 −1/=/+1 判定、`format` 防御、`canConfirm` 门控）；既有用例仅补 `carrier:"file"` 字面量，断言条数与强度不变 |

**零改动（已用 diff 证明）**：`frontend/src/api/imports.ts`（逻辑）、`ImportErrorsTable.tsx`、`ui/controls.tsx`、`ResourcesPage.tsx`、模板常量、上限常量、`package.json` / `package-lock.json`；无 `crypto.subtle`；粘贴内容不写 console / storage / URL / 错误受控文案。

## 2. 后端与数据库（NOT_REQUIRED）

- **BACKEND NOT_REQUIRED**：`layers.backend=false`（`docs/features/F034/architecture.md` §5/§10）。文本→CSV 字节后复用既有 multipart 端点（`file` binary + `format`），服务端解析、校验、事务、审计、范围与上限全部沿用 F014/F023 已交付实现；`backend/app/**`、`backend/alembic/**` **零 diff**（本报告 §4 命令证据）。不存在「只有设计却无人实现」的 Schema 变更。
- **DATABASE NOT_REQUIRED**（F034-DB-01）：无表 / 列 / 索引 / 约束 / Migration 变更（architecture §5/§10；plan `implementation.not_required.database`）。

## 3. 与设计的一致性

- 严格按 architecture §3.1–§3.6 实现，未自创规则：本地只拦截空/纯空白、UTF-8 字节严格大于上限、`text` 载体下 `format !== "csv"` 防御、非法载体值；**不镜像行数上限**、**不做任何 CSV 解析**（表头、分隔符、引号、枚举、重复、冲突一律交服务端）。
- 两步流程与门控不变：`error_count === 0` + 指纹一致 + 本次未成功才可「确认导入」；载体/格式/文件/文本任一变化经既有 `changeInput` 重置 `localErrors`/`validateState`/`importState`/`validatedKey`。
- 契约零改动：端点、字段、响应 Schema、`RowError`、错误码与 `reason` 集合、模板、上限、权限、原子性均未触碰（仅新增前端载体语义）。

## 4. 实际执行的验证

| 命令 | 结果 |
| --- | --- |
| `cd frontend && npm run typecheck` | 通过（`tsc --noEmit` 无错误） |
| `cd frontend && npm run build` | 通过（`✓ built`；仅有既存 chunk >500 kB 警告） |
| `cd frontend && npm run smoke:client` | **337 passed, 0 failed**（基线 328 + 新增 9 条；既有断言未删未弱化） |
| `git diff --name-only -- backend/ docs/api/ docs/database/ docs/project/ docs/product/ frontend/package.json` | 空（零改动） |
| `grep -rn "crypto" frontend/src/components/importCarrier.ts` | 仅注释中的禁令，无 `crypto.subtle` 调用 |
| `grep -rn "localStorage\|sessionStorage\|console\.\|location\.\|history\." <受影响文件>` | 无命中 |

**浏览器侧（前端自证，非真实后端）**：Playwright + Chromium，1440 / 1024 / 768 / 375 px，受控响应注入；无横向溢出、文本域固定高 214px 内部滚动、`format` 在文本载体下 `disabled` 且 Tab 跳过、label 关联聚焦、空内容本地报错不发请求且 `role="alert"`、改字符后结果区重置、两个面板均具备载体选择、控制台无 error。截图在 `/tmp/f034-ui/`（未入仓）。临时预览挂载文件已删除，`main.tsx` 逐字节还原（`md5sum` 前后一致）。

## 5. 未验证项（交 TEST 阶段）

1. 真实后端等价性（T108 / T114 / T115 服务端部分）、`/validate` 与写入端到端、服务端 413 —— 由 Tester 在 `-p csmtest` 测试栈执行。
2. 真实剪贴板粘贴的 CRLF→LF 呈现（ON-1）未在剪贴板路径实证；等价性判据以「实际发送字节」为准。
3. 截图未做人眼像素复核（生成本轮的执行环境无图像输入能力），结论来自 DOM 几何、计算样式与对比度计算。

## 6. 已知边界（NOTE，不阻塞）

- **F034-FE-01**：`"\uFEFF".trim() === ""`，故「仅 BOM 且无其它内容」的文本在本地被判纯空白并拦截（不发请求、无写入）；同字节文件载体走服务端 422 `IMPORT_INVALID_FILE`。两者均拒绝且无残留，属 architecture §3.3「空/纯空白用 `trim()` 判定」的直接推论；Architect 已在定稿记录中说明「不作缺陷、不改契约，TEST 照录分支」。若需改判须由 Architect 裁定。
- **F034-FE-02**：`format` 在文本载体下为 `disabled`，其说明通过可见文本呈现，但禁用控件不在焦点路径上；字段本身只读且值恒为 CSV，影响轻微。
