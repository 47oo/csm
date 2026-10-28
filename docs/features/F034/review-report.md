# F034 导入 CSV 文本载体 — REVIEW 阶段报告

- **状态**：`APPROVED WITH FOLLOW-UP`
- **版本**：v1（2026-10-26）；Reviewer 独立审查
- **上游依据**：`docs/product/requirements-v3.md` revision 13（§24.5 CONFIRMED、§31 T107–T116、修订后 T28、§32、§35.1 revision 13）；`docs/api/F014.md` / `docs/api/F023.md` §「CSV 文本载体（加法引用）」增补节 v1（READY，2026-10-26，含解释性裁定附注 1–3）；`docs/features/F034/{product.md, architecture.md(§12), implementation.md, test-report.md(§1 v1.1 / §2 TEST-1)}`；CHG-012（BQ-01/BQ-02 = A）；plan_revision 20、`pending_changes: []`
- **审查基线**：Feature Branch `feature/F034-csv-text-import`；start_commit `33d8a037dcef81a138d29389ff1e021ddc30271f`；**候选 HEAD `753166524e723f745ef71699be85bf4bde5d1b62`**；Base `v3.3`（采用 `refs/heads/v3.3` = start_commit `33d8a03`；`refs/tags/v3.3` = `79e1bec` 为过期同名标签，不采用）；merge-base = `33d8a03`；完整范围 `33d8a03..7531665` = 5 提交 / 103 文件 / +8970 −516；工作区 clean、无未跟踪产物

## 1. Scope Reviewed

| 项 | 值 |
| --- | --- |
| 提交 | `7b5493b`(start) `bbc9e91`(arch) `cf83ab5`(test design+contract+T114) `717385b`(feat, 18 文件) `7531665`(test, 87 文件) |
| 实现面 | `frontend/src/components/{importCarrier.ts, importForm.ts, resourceInterfaceIpImportForm.ts, ResourceImportPanel.tsx, ResourceInterfaceIpImportPanel.tsx}`、`frontend/src/index.css`(+26 行)、`frontend/scripts/smoke-client.mjs`(+9 用例) |
| 契约面 | `docs/api/F014.md` / `docs/api/F023.md` 各 +26 行（仅新增「加法引用」增补节 v1 + 签核记录 + 3 条附注） |
| 文档面 | `docs/features/F034/**`、`docs/project/project-plan.yaml`、派生视图、`docs/product/requirements-v3.md`（4 行 T114 澄清 + §35.1） |
| 零改动（自证） | `backend/app/**`、`backend/alembic/**`、`frontend/src/api/imports.ts`(0 行)、`ui/controls.tsx`、`ImportErrorsTable.tsx`、`ResourcesPage.tsx`、`package.json`/`package-lock.json`、模板与上限常量、`.gitignore`、其它页面 |

## 2. 分层结论

| 层 | 结论 |
| --- | --- |
| 产品与领域（T107–T116） | 通过；两入口并列载体、严格表头/不嗅探/不补表头/不重排、UTF-8 字节上限、等价性、不留痕均实现并可复核；无静默新增或放宽业务规则；无前端 CSV 解析、无行数镜像、无 `.xlsx` 文本载体 |
| 契约与 API | 通过；端点/字段/Schema/`reason` 集合/模板/上限/权限/原子性零变更，无新增错误码、字段或上限 |
| 数据与 Migration | `NOT_REQUIRED` 成立（无 Schema 变更；写入入口集合不变） |
| 数据完整性（skill） | 通过；TD-11 映射成立，真实 PG 复跑验证唯一性冲突整批拒绝、行级范围拒绝不泄露、回滚零残留、每对象 CREATE、`pg_tables` 不变 |
| 前端 | 通过，1 项非阻塞 UX 缺陷（RV-01）；载体并列、`format` 只读恒 csv、切换/编辑全量重置结果态、错误四态与 `role="alert"` 未削弱、无 storage/URL/console 泄露 |
| 安全与范围 | 通过；VIEWER 403 / 未认证 401（401 先于 403）、集群范围行级拒绝、marker 在响应/audit/容器日志命中 0、≤1 MiB 无应用层临时文件、无新增依赖 |
| 测试充分性 | 可信；独立复现 typecheck、build、smoke 337、F034 集成 31、既有导入回归 81（合计 112），等价性 I 层 60 例重跑后观测文件 md5 不变 |
| 交付物与 Git | 通过，2 项记录性问题（RV-04、RV-05）；文档链与计划/派生视图自洽，状态与视图校验 VALID |

## 3. Verification（Reviewer 实际执行）

| 命令 | 结果 |
| --- | --- |
| `git status --porcelain=v1 -uall` / `git rev-parse HEAD` / `git merge-base` / `git diff --stat 33d8a03..HEAD` / `git log --oneline` | 基线核对见 §1；工作区 clean |
| `git diff --name-only 33d8a03..HEAD -- backend/app backend/alembic \| wc -l` | 0 |
| `git diff 33d8a03..HEAD -- frontend/src/api/imports.ts \| wc -l`；`-- frontend/package.json frontend/package-lock.json \| wc -l` | 0 / 0 |
| `cd frontend && npm run typecheck` | exit 0 |
| `cd frontend && npm run build` | exit 0（仅既存 chunk >500 kB 警告） |
| `cd frontend && npm run smoke:client` | **337 passed, 0 failed**（基线 328 + 9；删除的 10 条 assert 均以 `carrier:"file"` 等价重写，未弱化） |
| `pytest tests/integration/test_f034_csv_text_carrier.py tests/integration/test_f034_csv_text_carrier_scope.py`（真实 PG 16.15，`csm_test`） | **31 passed** |
| `pytest tests/integration/{test_imports,test_import_tester_acceptance,test_f023_resource_interface_ip_import,test_import_constraints,test_f027_access_scope}.py` | **81 passed**（合计 112，与报告一致） |
| 观测文件 md5 前后比（跑测试前/后） | 3 个 artifacts 字节不变；工作区仍 clean |
| `python3 scripts/validate_project_state.py` / `render_project_views.py`（无 `--write`） | `PROJECT STATE VALID` / `PROJECT VIEWS VALID` |
| `grep -rniE "crypto\.\|localStorage\|sessionStorage\|document\.cookie\|console\.\|location\.(href\|search)"` 于载体/表单/面板 | 仅 `importCarrier.ts` 注释内禁令，无实现调用 |
| 结构化产物复核 | 等价性 I 层 30 语料 × 2 入口 = 60 例全部 deep-equal；F-13 未闭合引号 200/1 行/1 错误；F-14 制表符 reason ∈ 已签核集合；F-24 BOM-only 422 `empty_file`；B 层 18 条断言 0 失败；H 层 60 例 0 失败 |

## 4. Findings

| ID | Severity | Layer | Location | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F034-RV-01 | MEDIUM | 前端/UX | 两面板 file 分支（`ResourceImportPanel.tsx:287-332`、`ResourceInterfaceIpImportPanel.tsx:313-359`） | 载体切换回 file 时 `values.file` 保留但原生 input 重挂载为空、界面无文件名回显 | 可能在界面上看不到文件时提交切换前的旧文件；不违反 T116/T107 | Architect + Frontend | 否（Follow-up 1） |
| F034-RV-02 | MEDIUM | 变更控制/需求正文 | `requirements-v3.md` §31 T114、§35.1（`cf83ab5`） | CONFIRMED 验收口径被就地改写、revision 未提升、无用户追认，仅有 Architect 裁定 + §35.1 + 契约附注 | 裁定方向与 §24.5 一致且无可替代实现，但形式留痕不足 | 协调器 + PM | 否（Follow-up 2） |
| F034-RV-03 | LOW | 前端文案 | 两面板 `TextArea placeholder` | 占位符给的是片段/带省略号的「假表头」，照抄必 422 | 可操作性小损失（两载体同口径） | Frontend | 否 |
| F034-RV-04 | LOW | 证据/文档精度 | `test-report.md` §2.10 | 报告称 logs 被 `.gitignore:125` 忽略，实际 12 个 logs 已入库 | 后续读者误判入库范围 | Tester/协调器 | 否 |
| F034-RV-05 | LOW | 项目状态 | `project-plan.yaml` F034 `git.head_commit: null` | 前例 F033 进入 REVIEW 已写 head_commit；本处为 null | Merge Gate 前须补候选 HEAD（已在最终状态提交中补记 `7531665`） | 协调器 | 否 |
| F034-RV-06 | NOTE | 性能 | 两面板 `importTargetKey(values)` / `pastedByteLength` | 每次渲染做全量双哈希 + `TextEncoder` | 大文本编辑可能可感知延迟 | Frontend | 否 |
| F034-RV-07 | NOTE | Git 基线 | refs（`v3.3` 分支/标签/origin 三值不一） | 按标签口径 `git diff v3.3...HEAD` 会误含 F032/F033 | 建议以完整 SHA 记录 Base（本次已用 `33d8a03` 完整 SHA） | 协调器 | 否 |
| F034-RV-08 | NOTE | 既有信息暴露面 | 表头级 `details.unknown_columns` / `missing_columns` | 会回显「被当作表头的那一行」原文；属既有 schema、两载体逐字段相同 | 与 T115 字面表述有张力，F034 无法改变 | Architect/PM | 否 |
| F034-RV-09 | NOTE | 测试副作用 | `test_f034_csv_text_carrier.py` 写回 `artifacts/*.json` | 跑测试会写被跟踪文件（实测确定性一致、工作区 clean） | 影响重复验证洁净纪律 | Tester | 否 |

## 5. 旧缺陷复核

TD-I-1（T114 等价性裁定，含 F-13 实测 200/1 行/1 错误）、TD-I-2（制表符 reason ∈ 已签核集合）、TD-I-3（文件所有权）、TD-I-4（不夸大「不落盘」）、TD-I-5（BOM-only 两分支）全部复核成立；DEV-1（F-15 → `unknown_columns`）、DEV-2（F-10/F-10b 拆分）、DEV-3（F-11 另有 manufacturer 控制字符错误）、NOTE-1/2/3 描述准确；NOTE-4（74 未跟踪）已由候选 HEAD 入库消解。未发现被下调的真实缺陷，也未发现报告隐去 FAIL。

## 6. Follow-ups（非阻塞）

1. **F034-RV-01**（Architect + Frontend）：载体切离文件时清空 `file` 或显式回显已选文件名；补一条浏览器断言（切 text→file 后界面状态与 `values.file` 一致）。
2. **F034-RV-02**（协调器 + PM）：为 T114 编辑性澄清补记产品/用户追认来源，或明确登记为 revision 13 的解释性裁决引用（不改行为）；如需严格拒绝另立 CHG。
3. **F034-RV-04**（Tester）：更正 test-report §2.10 的 logs 入库状态描述。
4. **F034-RV-03 / RV-06 / RV-09**（Frontend / Tester）：placeholder 措辞、`importTargetKey` 与字节计数 `useMemo`、测试产物写回策略。
5. **F034-RV-08**（Architect / PM）：决定是否另立变更收紧表头级 `details` 回显（既有 F014/F023 行为，两载体一致）。

## 7. 未审查项

全量后端 pytest（backend 零 diff，已跑导入相关 81 + 31）、H 层 live 脚本与 B 层浏览器脚本未由 Reviewer 独立重跑（改为核对产物 + 亲自重跑 I 层等价性 60 例）、5 MiB 端到端、`>1 MiB` 溢写路径、真实剪贴板 CRLF 呈现、像素级视觉复核（均与 TD-12 一致登记 `NOT TESTED`）；`.xlsx` 文本载体 `NOT_REQUIRED`。

## 8. 结论

`APPROVED WITH FOLLOW-UP`。批准仅对候选 HEAD `7531665` 与 Base `33d8a03`（`refs/heads/v3.3`）的有效范围内成立；基线或 HEAD 变化须重新验证/Review。Merge 与 DONE 由协调器按 Git Workflow §5 判定；本报告建议不自行成为产品或架构决定。

## 9. Merge 记录（协调器补记）

- Merge：`git switch v3.3` → `git merge --no-ff feature/F034-csv-text-import`，Merge SHA **`d2a847af733ebf55f292d8c966a038c8aee14ba4`**，父提交 `33d8a03`（批准 Base）与 `7531665`（批准 HEAD），与审查范围一致，无冲突。
- 批准 HEAD 与 Merge 后的集成树一致（`--no-ff` 直接合并批准候选，无额外实现改动）。
