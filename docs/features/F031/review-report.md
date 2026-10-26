# F031 Review Report

## 1. Task / Status

- **Task**：F031「F030 Review 非阻塞项收尾」— REVIEW Gate 正式只读审查。
- **Status**：**APPROVED WITH FOLLOW-UP**
- 10 项跟进均已真实关闭或有书面接受边界；独立复跑关键项 PASS；无 BLOCKER / HIGH / 必须修复 MEDIUM。存在 1 项 MEDIUM 元数据问题（状态机，MERGE 前处理）与 2 项 LOW / 4 项 NOTE。

## 2. Basis

| 类别 | 依据 |
| --- | --- |
| 需求 | `docs/product/requirements-v3.md` revision 11（§23.2、§31、§32、§35；`docs/product/**` diff=0） |
| 计划 | plan_revision 17；`project.approval`（用户 2026-10-23，feature_ids 含 F031）；`execution.authorization`（17/SINGLE/F031）；`pending_changes: []` |
| 产品/设计 | `docs/features/F031/product.md`；`docs/features/F031/architecture.md` v1 + §10 READY FOR IMPLEMENTATION |
| 上游 | `docs/features/F030/review-report.md`（F030-RV-03…RV-10、T03）；F030 architecture §17；F030 static log errata |
| Contract | `docs/api/F026.md` v3 头部 +1 行；其余 15 份 `docs/api/` diff=0 |
| 实现/测试 | `docs/features/F031/implementation.md`、`test-report.md`（TD-1 + TEST-1 READY FOR REVIEW）、artifacts |
| 规范 | AGENTS、handoff、git-workflow §4/§5、project-state、implementation-rules |

## 3. Scope Reviewed

| 项 | 值 |
| --- | --- |
| Branch | `feature/F031-review-closeout` |
| start_commit / Base | `2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa`（v3.2） |
| Candidate HEAD | `137d8e6c05a763351bae5f6983c742cec92d2447` |
| merge-base | `2c827fb` |
| 范围 | 5 commits、40 files、+2936/−40 |
| 工作区 | clean |
| 测试针对性 | `bf384c8..HEAD` 仅 docs/plan/artifacts；backend/frontend/docs.api/docs.product/docs.database 在测试输入后零改动 |

## 4. 分层结论

| 层 | 结论 |
| --- | --- |
| 产品/领域 | 通过。无新增业务规则/对象/关系/状态/唯一性/权限/错误码/端点/字段/Schema；空态文案恢复 F030 前既有中性字面。 |
| 架构/依赖 | 通过。errata 仅追加、F026 不升版本、T03 真实路径 + 测试级 override；layers/api_required 与实现一致；无新增依赖。 |
| 数据/Migration | 通过（NOT_REQUIRED）。`backend/alembic`、models/schemas diff=0；单 head 0015；真实 PG 上 T03 真实 23503、零行零 Audit；并发唯一性证据重跑通过。 |
| API/Contract | 通过。F026 `1 0`，仅头部新增行；版本/签核/状态行不变；§1–§13 零 diff；其余 15 份空 diff。 |
| 后端 | 通过。`cluster_authorization.py` AST sha256 相同，差异全为注释；注释主张与 `_reject_unknown_query` 第 95 行、`_parse_uuid` 第 98/129 行一致。 |
| 前端 | 通过。Panel 仅 2 处改动（注释 + 空态 description）；门控/调用/disabled 未变；旧字面 0、新字面 1；I-2 引用 0；tsc/smoke 通过。 |
| 测试 | 通过。独立复跑定向 29、两新例 2（overlap=True、attempts 1/5）、F017 隔离 3/3、tsc 0、smoke 328；全量以归档日志 + 计数一致性核对。 |
| 安全/范围 | 通过。白名单内；受保护目录空 diff；router 83→83；无 `/_test`；artifacts 无凭据；无新增依赖。 |
| 变更/批准 | 基本通过。plan_revision 17 覆盖 F031；需求正文零 diff；批准记录完整。元数据缺陷见 RV-01/02。 |
| Git 基线 | 通过。HEAD/Base/merge-base 一致、工作区 clean；head_commit 滞后一个交付提交（RV-02）。 |

## 5. Findings

| ID | Severity | Layer | 说明 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- |
| **F031-RV-01** | **MEDIUM** | Plan/状态机 | F031 `status: IN_PROGRESS` + `current_stage: REVIEW`，Test READY FOR REVIEW 应为 `IN_REVIEW`；`IN_PROGRESS → DONE` 会被转换检查拒绝（与 F030-RV-01 同根因） | Coordinator | 否（MERGE 前补 `IN_REVIEW`） |
| **F031-RV-02** | LOW | Plan/Git | `git.head_commit` 记录 `bf384c8`，候选 HEAD `137d8e6`；其后含 test-report/artifacts/plan，非纯状态元数据 | Coordinator | 否（MERGE 时写 approved HEAD） |
| **F031-RV-03** | LOW | 证据索引 | test-report TE-14 引用 `artifacts/discarded/*.log`，但 `discarded/` 未入库（gitignore、未 add -f）；判定依据 `full-pytest.log` 已入库，结论不受影响 | Coordinator/Tester | 否 |
| **F031-RV-04** | NOTE | 文档一致性 | F031-TEST1-02 描述旧署名「Tester」，候选 HEAD 已改为「Coordinator」，报告文字未同步 | Coordinator | 否 |
| **F031-RV-05** | NOTE | 证据措辞 | clock-skew 日志写 `created_at (app clock)`，实际 `created_at`/`revoked_at` 均 `func.now()`（DB 时钟）；归因方向仍成立 | Backend/Tester | 否 |
| **F031-RV-06** | NOTE | Contract 指针 | F026 §5 证据行未增列 T03 端到端用例；既有证据仍支撑，设计仅授权改头部 | Architect（后续） | 否 |
| **F031-RV-07** | NOTE | Plan 字段 | F031 `last_result` 为 null，结果记在 execution.last_result | Coordinator | 否 |

**BLOCKER 0 / HIGH 0 / MEDIUM 1（元数据，不阻塞）/ LOW 2 / NOTE 4；必须修复 0。**

## 6. 旧缺陷复核

| 项 | 结论 |
| --- | --- |
| F030-RV-03 签名 errata | **CLOSED**：F030 architecture +39/−0，§17.1 与实现逐参一致 |
| F030-RV-04 空态文案 | **CLOSED**：旧字面 0、新字面 1，与 Base 逐字节相同，门控未变 |
| F030-RV-05 注释 | **CLOSED**：AST 相同，差异全为注释，行号与事实一致 |
| F030-RV-06 并发尝试 | **CLOSED**：MAX_ATTEMPTS=5、失败语义保留、overlap=True、attempts 1/5 |
| F030-RV-07 日志路径 | **CLOSED**：纯追加、正确路径、grep 输出独立复核一致 |
| F030-RV-08 F026 头部 | **CLOSED**：1 0，仅头部新增行，其余 15 份空 diff |
| F030-RV-09 悬空 I-2 | **CLOSED（frontend 范围）**：frontend 命中 0；F030 历史报告不改写 |
| F030-RV-10 守卫范围 | **CLOSED（书面接受）**：守卫/ conftest 未变；范围外符号 0；reopen 条件已记录 |
| F030-T03 500 信封 | **CLOSED**：真实路径、无 `/_test*`、401 对照、真实 23503、精确 500、零泄漏/零残留、201 归因、override 清理 |
| ⑩ 不新增 | **CLOSED**：受保护目录空 diff、router 83/83、permissions 空 diff、单 head 0015 |
| F030-RV-01/02 | **同根因复发**，见 F031-RV-01/02 |
| F031-TEST1-01（F017 flake） | **接受为范围外**：F017 文件/服务/模型零 diff，隔离 3/3 pass，最终全量 729/6 干净；建议另立 follow-up |

## 7. Follow-ups

1. **Coordinator（MERGE 前）**：F031 状态补 `IN_REVIEW`，并补 `last_result`（RV-01/RV-07）。
2. **Coordinator（Merge Gate）**：写 approved HEAD `137d8e6`、Base `2c827fb`、真实 merge SHA；更正 head_commit（RV-02）。
3. **Coordinator**：合并后恢复 `project.acceptance=COMPLETE`、补 F031 证据、清除 pending_reason。
4. **Coordinator/Tester**：`discarded/` 日志入库或从 Evidence Index 标注为仅工作区作废（RV-03）；同步 TEST1-02 状态（RV-04）。
5. **Backend/Coordinator（F017 归属）**：另立 follow-up 收敛 F017 时钟敏感并发用例；校正 clock-skew 措辞（RV-05）。
6. **Architect（后续）**：可将 T03 增列为 F026 §5 证据（RV-06）。

## 8. 未审查项

| 项 | 原因 |
| --- | --- |
| 全量后端套件重跑 | 约 19.5 分钟；以定向 29 + 两新例 2 + F017 隔离 3/3 + 归档全量 729/6 + 测试后代码零改动交叉核对 |
| `npm run build` 重跑 | 会写 dist；改跑 tsc/smoke，build 沿用归档日志 |
| 真实浏览器 DOM/焦点/窄屏 | 设计排除，NOT TESTED |
| ACTIVE>2000、并发压力、Compose | 架构不可声明项 |
| T03 401/403 语义 | override 绕过认证，仅 401 对照 |
| F028×4、migrations V3b | 既有 skip |
| 锚点 slug 机械解析 | 只校验文件存在，人工核对形式 |
| 用户批准来源真实性 | 无法独立核实，仅核对记录完整性 |

## 9. Verification

- Git：HEAD `137d8e6`、Base `2c827fb`、merge-base 一致；工作区 clean；范围 40 files/+2936/−40/5 commits。
- 静态：F026 `1 0`；F030 architecture `39 0`；static log `12 0`；受保护目录空 diff；router 83→83；`/_test` 0；单 head 0015；frontend I-2 0；旧文案 0/新文案 1；tests/smoke scope 符号 0。
- 计划：`validate_project_state.py` VALID；`render_project_views.py` VALID。
- 独立复跑（真实 PG 16.15 @ 55432/csm_test）：定向 29 passed；两新例 2 passed（`overlap=True`、`attempts used: 1/5`）；F017 隔离 3/3；tsc exit 0；smoke 328 passed。
- 凭据扫描：`***` 在 F031 artifacts 命中 0。

## 10. 批准边界

本批准仅对候选 HEAD `137d8e6c05a763351bae5f6983c742cec92d2447` 与 Base `2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa`（v3.2）有效。Merge/DONE/acceptance 恢复由协调器按 Git Workflow §5 判定；本报告建议不构成产品或架构决定。

GIT: git rev-parse --show-toplevel
GIT: git branch --show-current
GIT: git status --porcelain=v1 --untracked-files=all
GIT: git rev-parse HEAD
GIT: git rev-parse v3.2
GIT: git merge-base 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa HEAD
GIT: git diff --stat 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa...HEAD
GIT: git log --oneline 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD
GIT: git diff --cached --stat
GIT: git ls-files --others --exclude-standard
GIT: git ls-files docs/features/F031/artifacts
GIT: git diff 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD -- docs/features/F030/architecture.md docs/api/F026.md docs/features/F030/artifacts/p3-p6-static.log
GIT: git diff 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD -- backend/app/services/cluster_authorization.py
GIT: git diff 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD -- frontend/src/components/ClusterAuthorizationPanel.tsx
GIT: git diff 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD -- backend/tests/integration/test_cluster_authorizations.py
GIT: git diff --name-only 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD -- backend/app/api backend/app/schemas backend/app/models backend/app/core backend/alembic frontend/src/api docs/product docs/database
GIT: git diff --name-only 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD -- docs/api
GIT: git diff --stat 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa..HEAD -- backend/tests/integration/test_f017_tester_acceptance.py backend/app/services/api_key.py backend/app/models/api_key.py
GIT: git diff --name-status bf384c8..HEAD
GIT: git show 2c827fb8a81f54fe6cb0889fd05eb9f12f0ccffa:backend/app/services/cluster_authorization.py
GIT: git show 56cc6ac^:frontend/src/components/ClusterAuthorizationPanel.tsx
