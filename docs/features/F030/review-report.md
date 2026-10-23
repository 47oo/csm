# F030 Review Report

## 1. Task / Status

- **Task**：F030「Review 跟进收敛：Contract 签核、边界测试与前端交互修正」— REVIEW Gate 正式只读审查（Reviewer；未修改任何仓库文件）。
- **Status**：**APPROVED WITH FOLLOW-UP**
- 核心验收（P1–P9）满足、必要验证可信、独立复跑关键项通过，无 BLOCKER / HIGH / 必须修复 MEDIUM，无未决产品问题；存在 1 项需协调器在 MERGE 前处理的中等级元数据问题（非必须修复）与若干非阻塞跟进项。

## 2. Basis

| 类别 | 依据 | 版本 / 状态 |
| --- | --- | --- |
| 需求 | `docs/product/requirements-v3.md` | revision 11（§23.2 CONFIRMED、§28、§31 T85–T99、§32、§35.2/§35.3 未改写） |
| 计划批准 | `docs/project/project-plan.yaml` `project.approval`（用户，2026-10-23，plan_revision 16，feature_ids 含 F030，basis「按建议合并」）；`execution.authorization`（plan_revision 16 / SINGLE / F030 / 用户 2026-10-23） | 有效覆盖 F030；`pending_changes: []` |
| 产品设计 | `docs/features/F030/product.md`（P1–P9、§3 边界守卫、§7 N1–N5） | READY FOR ARCHITECT |
| 架构 / 设计签核 | `docs/features/F030/architecture.md` v1 + §16 最终设计定稿（Architect 2026-10-23，READY FOR IMPLEMENTATION） | 已签核 |
| Contract | `docs/api/F026.md` **v3**（READY，Architect 2026-10-21/22/23）+ 12 份域 Contract 增补节 v1 签核行；`docs/api/F027.md` v1 不变 | 已签核 |
| DB 设计 | `docs/database/f026-cluster-authorization.md` v1（Database 2026-10-21，DB-D401–D420） | 无 Schema 变更，继续有效 |
| 实现 / 测试 | `docs/features/F030/implementation.md`、`docs/features/F030/test-report.md`（TD-1 v1 + **TEST-1 v1 READY FOR REVIEW**）、`docs/features/F030/artifacts/*`（17 份已入库） | TEST READY FOR REVIEW |
| 上游 | `docs/features/F029/review-report.md`（RV-01…RV-11、Follow-up 1–7）、`test-report.md`、`implementation.md` | F029 DONE（721/6 skipped、322 smoke 基线） |
| 规范 | `AGENTS.md`、`docs/project/handoff.md`、`git-workflow.md` §4/§5、`project-state.md`、`implementation-rules.md`、`change-control.md`、`.pi/skills/data-integrity/SKILL.md`、`.pi/skills/frontend-ui/SKILL.md` | — |

## 3. Scope Reviewed（完整范围）

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F030-review-followup-closeout` |
| start_commit（= plan `git.start_commit`） | `70db846ca2ed4bad90281ad5f55c1e6a9b2c5300`（`v3.2`） |
| Candidate HEAD | `891206a54aa0d5f1f731e6d9044ac8f98e11be2a` |
| Base | `v3.2` = `70db846ca2ed4bad90281ad5f55c1e6a9b2c5300` |
| merge-base(Base, HEAD) | `70db846ca2ed4bad90281ad5f55c1e6a9b2c5300`（与 start_commit 一致） |
| 完整范围 | `70db846...HEAD`：7 commits、**46 files、+2794 / −87** |
| 历史 | `1fdaa5b` 启动+产品门 / `a8d653a` product / `4335860` architecture / `b1b6ba1` test design / `7c19df8` Contract 落盘 / `56cc6ac` 实现 / `891206a` TEST 证据+报告 |
| 工作区 | `git status --porcelain=v1 --untracked-files=all` 空；暂存区空；无未跟踪文件；无 stash；无 merge/rebase/cherry-pick 进行中 |
| 测试针对性 | `56cc6ac..891206a` 仅新增 `test-report.md` TEST 段、17 份 artifacts 与 plan 元数据；`backend/`、`frontend/`、`docs/api/` 在测试后**零改动** → 测试证据对候选 HEAD 有效 |

## 4. 分层结论

| 层 | 结论 |
| --- | --- |
| 产品 / 领域 | **通过**。F030 严格限于四类工作（批准记载、专业设计输入收敛、测试与测试规范、文档/注释与前端交互）。未新增对象、关系、状态、唯一性、生命周期、权限项、错误码或错误顺序；未新增端点/参数/字段；§23.2 授权与 Audit 语义、F027 范围语义均未变（`backend/app/{models,schemas,core,api}`、`frontend/src/api`、`docs/product`、`docs/database`、`docs/api/F027.md` 全量空 diff）。无范围漂移。 |
| 架构 / 依赖 | **通过**。方案与 §3–§9 落点一致；`layers.database=false`（`not_required.database` 已记理由）、backend/frontend=true、api_required=true，与设计 §2 一致；无新增依赖、无新框架（`package.json`/`pyproject` 依赖未变；`pyproject.toml` 仅 marker 说明文本 1:1 替换）。 |
| 数据 / Migration | **通过（NOT_REQUIRED 成立）**。`backend/alembic/`、DB 设计空 diff；alembic 单 head 仍为 `0015_user_cluster_authorizations`；DB-D401–D420 未受影响。并发与完整性证据在真实 PostgreSQL 上复跑通过（见 §6）。 |
| API / Contract | **通过**。`docs/api/F026.md` v3：头部补「覆盖范围 / 对象」「确认来源」，§5 纯追加「非唯一完整性错误语义」，§12 签名行与 §13 修订记录 v3 行日期一致（2026-10-23）；§5 既有 409/422 映射表**未改写**。12 份域 Contract：删除行 = 0（纯追加），增补节末签核行含批准者/日期/对象路径/覆盖范围/确认来源/上游依据，修订记录各新增 1 行且**单元格数 = 该文件表头列数**（F002 3 列 / 其余 4 列，逐文件复核）。F026 删除 4 行 = 3 行签核记载改写 + 1 行 EOF 换行归一（逐字节可解释），无正文语义变化。 |
| 后端实现 | **通过**。`cluster_authorization.py` 差异**全部为注释行**（`list_authorizations` 注释改为 P-1 路径对象优先，删除与事实相反的 existence-oracle 结论）；`grant_authorization` 的 `except IntegrityError` 收窄（仅部分唯一索引名 → 409，其余 `raise`）为 Base 既有代码，未改。Contract §5 v3 的「原样上抛 → 500 `INTERNAL_ERROR`」与 `app/core/errors.py` 统一处理器一致，且服务层 `rollback` 保证无行/无 Audit。措辞精度见 RV-05 NOTE。 |
| 前端 | **通过（机制级 + 静态核对）**。新增纯逻辑模块 `authorizationCandidates.ts`（仅 1 处 `import type`，无 JSX/React/antd）；面板：`openGrant` 先置 `loading` 再开模态、非 `success` 永不渲染候选且 `canSubmitGrant` 恒 false、加载失败 `ErrorState` + 重试（不置空集）、`truncated` 双路显式提示、集群截断判据改为 `total > items.length`、`already_granted` 保持模态打开+内联错误+重载候选（不当作成功）、`already_revoked` 路径保持 Contract D-5 关闭+提示+刷新。旧符号 `activeGrantIds` / 旧判据命中 0；API 调用计数与 Base 逐项相同。真实浏览器 DOM/焦点/窄屏如实标为 NOT_REQUIRED，未夸大覆盖。 |
| 测试 | **通过（可信）**。独立复跑：q 边界 + 守卫 4 passed；并发 + 非唯一完整性错误 2 passed（`attempt 1: overlap=True`）；`tsc --noEmit` exit 0；`smoke:client` **328 passed / 0 failed**；`--collect-only` **733 + 1 module skip**，与 F029 基线 726 + 7 新例吻合。用例自建数据、不依赖执行顺序；`committed_engine` 逐用例 TRUNCATE 使「残留 0 行」断言不依赖顺序。反空洞性分析成立。 |
| 安全 / 范围 | **通过**。无敏感信息新增（artifacts 凭据已 redaction）；无新增依赖；无生产代码逻辑变更；变更文件全部落在 TD-2 P9.1 白名单内（46 文件中 17 份为本 Feature 自有 artifacts，3 份为派生视图）。 |
| 变更与批准 | **基本通过（1 项 MEDIUM 元数据）**。plan_revision 16 批准覆盖 F030；`pending_changes: []`；BQ18/BQ19 `OPEN → CONFIRMED`，`source/kind/affects/owner` 与 Base 逐键相同，basis 引用 DB 设计 v1（DB-D401–D420、DB-D407）+ F026.md v3 + F027.md v1 + 三份 architecture，签核者/日期不虚构（Database 沿用 2026-10-21）；requirements §35.2/§35.3 正文**零 diff**；`project.approval` / `execution.authorization` 未被改写。`validate_project_state.py`、`render_project_views.py`（只读）、`--feature F030`、`--previous` 全部通过。缺陷见 F030-RV-01。 |
| Git 基线 | **通过**。候选 HEAD / Base / merge-base 与 plan 记录一致，工作区与暂存区 clean，无未跟踪交付物；`git.head_commit` 落后一个交付提交（见 F030-RV-02，MERGE 时更正）。 |

## 5. Findings

| ID | Severity | Layer | Location | 证据 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **F030-RV-01** | **MEDIUM** | Plan / 状态机 | `docs/project/project-plan.yaml` F030 `status`、`execution.current_stage` | F030 `status: IN_PROGRESS` + `current_stage: REVIEW`；`project-state.md` §2 规定「测试放行进入 IN_REVIEW」「IN_REVIEW = 测试放行且候选交付已提交，正式 Review 中」；F029 同类阶段记录为 `IN_REVIEW` + `REVIEW` | 期望：Test READY FOR REVIEW + 候选已提交 → `IN_REVIEW`。实际：仍为 `IN_PROGRESS` | 阶段状态未反映事实；且 `validate_project_state.py` 的转换表不允许 `IN_PROGRESS → DONE`，MERGE 时会被转换检查拒绝，需补一次 `IN_REVIEW` | Coordinator | **否**（不阻塞 Review 结论；MERGE 前必须按状态机补 `IN_REVIEW`） |
| **F030-RV-02** | LOW | Plan / Git 字段 | 同上 `git.head_commit` | 记录 `56cc6ac`，候选 HEAD 为 `891206a`；`git diff --name-only 56cc6ac..HEAD` 显示其后还有 `test-report.md` TEST 段、17 份 artifacts 与 plan 元数据（非纯状态元数据） | 期望：`head_commit` 为最近交付/检查点提交，或仅其后存在状态元数据差异。实际：滞后一个含测试证据的交付提交 | 批准 HEAD 与计划字段存在偏差；Merge Gate 要求写入 approved HEAD | Coordinator | **否**（MERGE 时写 `891206a`，并在最终状态提交核对） |
| **F030-RV-03** | LOW | Frontend / 设计记载 | `frontend/src/components/authorizationCandidates.ts::canSubmitGrant`；`docs/features/F030/architecture.md` §7.2、§16.1 | 设计 §7.2 签核字面为 `canSubmitGrant(active, selectedClusterId, busy)`；实现为 `canSubmitGrant(active, candidates, selectedClusterId, busy)` 并追加「选中集群仍须在候选中」校验；architecture.md 未记录该偏离，§16.1 仍称与最终设计一致 | 期望：实现与签核设计一致，或设计侧留 errata 记载偏离。实际：实现更严格（不放宽行为），但设计正文与实际签名不一致 | 后续维护者按 §7.2 阅读会得到错误签名；不影响运行行为、Contract 或测试有效性 | Architect（补 errata）→ Frontend | 否 |
| **F030-RV-04** | LOW | Frontend / 文案 | `ClusterAuthorizationPanel.tsx` 候选为空分支 `EmptyState description="该账号已拥有全部匹配集群的有效授权"` | 该分支同时覆盖「集群搜索无匹配（`clustersState.total == 0`）」与「系统无 Cluster」情形；Base 为中性文案「没有可授予的集群（已有效授权的集群不会重复出现）」；架构 §7.2 表指定了新字面 | 期望：空态成因表述在两种情形下均成立。实际：无匹配集群时因果不成立 | 仅用户可读文案误导（无契约/权限/数据影响），但相对 Base 属可用性回退 | Architect（文案归属设计）→ Frontend | 否（建议改回因中性文案） |
| **F030-RV-05** | NOTE | Backend / 注释精度 | `backend/app/services/cluster_authorization.py:130-135`（同 architecture §8.1 字面） | 注释称「Typed query params … and undeclared params are rejected by the route **before the handler**」；实际 `_reject_unknown_query(request)` 在 handler 内第一步执行（`app/api/v1/cluster_authorizations.py:95`，先于 `_parse_uuid` 与服务校验） | 期望：注释与实现精确一致。实际：undeclared 参数在 handler 内被拒（「before handler」仅对类型化参数成立），但结论「未知用户亦 422」经集成用例证实成立 | 措辞精度，无行为影响 | Architect（设计字面）→ Backend | 否 |
| **F030-RV-06** | NOTE | Tests 可靠性 | `tests/integration/test_cluster_authorizations.py::test_concurrent_grant_two_connections_single_winner` | 3 次尝试内未观测到请求区间相交即 `assert overlap_observed` 失败（非 skip）；本人两次独立复跑均 `attempt 1: overlap=True` | 期望：并发证据不可被顺序执行冒充（设计选择已满足）。风险：高负载环境下若调度长期串行，用例会红而非降级 | 未来可能出现与实现无关的偶发红灯 | Tester | 否（建议保留失败语义，必要时增加尝试次数并记录） |
| **F030-RV-07** | NOTE | 测试工件 | `docs/features/F030/artifacts/p3-p6-static.log` | 日志含 `backend/app/api/cluster_authorizations.py: 没有那个文件或目录`（实际路径为 `app/api/v1/...`）；该主张实际由集成用例 TD2-P3.4 证明 | 期望：归档日志不含无效命令。实际：一条路径写错，结论未受影响 | 证据可读性 | Tester | 否 |
| **F030-RV-08** | NOTE | Contract 记载 | `docs/api/F026.md` 头部 | 同一头文件内「上游依据 … plan_revision 14」与新增「确认来源 … plan_revision 16」并存 | 期望：历史依据与本次签核依据区分清晰。实际：并存但未注明 14 为历史批准依据 | 可追溯性轻微歧义 | Architect | 否 |
| **F030-RV-09** | NOTE | 追溯引用 | `ClusterAuthorizationPanel.tsx:193`、`smoke-client.mjs`（F030 断言注释）、`test-report.md` F030-T02 | 三处引用「架构评审 I-2」；architecture §16.4 的 I-2 实为「F026.md §12 首条 bullet 修正」，无对应「候选成员校验」条目 | 期望：引用指向真实条目。实际：悬空引用 | 追溯瑕疵 | Architect → Frontend | 否 |
| **F030-RV-10** | NOTE | Tests 守卫范围 | `tests/integration/test_f030_test_harness.py` | AST 扫描仅覆盖 `tests/integration/test_*.py`（设计如此）；`tests/smoke/` 等其它目录若误用真实 scope 符号不受约束 | 设计边界明确、当前无实际风险；未来可评估扩展 | Coordinator / Tester | 否 |

**合计：BLOCKER 0 / HIGH 0 / MEDIUM 1（不阻塞）/ LOW 3 / NOTE 6；必须修复 0。**

## 6. 旧缺陷复核

### 6.1 F029 Review 跟进项

| 项 | 原 Severity | 复核结论 | 证据 |
| --- | --- | --- | --- |
| F029-RV-01 Contract 签核记载缺失 | LOW | **CLOSED**（残留记载瑕疵见 F030-RV-08） | F026 v3 头部五要素 + §12/§13 v3 行；12 份增补节签核行 + 修订记录行；12 份删除行 0，F026 删除 4 行可逐字节解释 |
| F029-RV-02 `q` 两侧断言 | LOW | **CLOSED** | 独立复跑 `test_list_q_boundary_validation` PASS：`""`/`"   "`/`a\x07b`/`a\u200bb`/65 字符 → 422 + `fields=[q]`；正向 `f30q1` → 200/total=1；未知用户 + `q=""`/控制字符 → 404；未知用户 + `unexpected` → 422（`fields=[unexpected]`）。互斥对使删除 `_validate_q` 或调换 P-1 顺序必失败 |
| F029-RV-03 并发与 IntegrityError 未固化 | LOW | **CLOSED** | 独立复跑 2 例 PASS：状态码集合 `{201,409}`、409 `already_granted`、DB ACTIVE=1/总行=1/Audit CREATE=1；非唯一完整性错误抛 `IntegrityError`（`sqlstate=23503`、约束名 `fk_user_cluster_authorizations_granted_by_users`、非 `Conflict`），行/Audit 残留 0，真实操作者归因对照成功 |
| F029-RV-05 前端候选误导性中间态 | NOTE | **CLOSED（机制级）** | `computeGrantCandidates` 非 success 永不返回候选 + `canSubmitGrant` 恒 false + `openGrant` 先置 loading；smoke 6 组断言；DOM 仍未验证且如实声明 |
| F029-RV-07 注释结论与事实相反 | NOTE | **CLOSED**（措辞精度见 F030-RV-05） | `existence oracle` 命中 0，新注释以 P-1 为依据 |
| F029-RV-08 非唯一完整性错误语义未记载 | NOTE | **CLOSED**（依据链为两段） | F026 §5 v3 追加段 + 服务层用例；端到端 500 未串联 |
| F029-RV-09 `real_scope` 默认未声明 | NOTE | **CLOSED** | `conftest.py::auth_app` docstring 三要素 + `pyproject.toml` marker 说明 + AST 守卫；/tmp 探针证明守卫非空洞；扫描 53 模块 |
| F029-RV-04 / Follow-up 4 | LOW | **部分关闭** | F029 `evidence.test` 已含 logs；`project.acceptance` 现为 `PENDING`，须在 F030 完成后恢复 `COMPLETE` 并补 F030 证据 → Follow-up 3 |
| F029-RV-06 / RV-10 / RV-11 | NOTE | **未复发 / 由 F030-RV-02 承接** | 覆盖声明与实际手段已对齐；F028 空行噪声未扩大；Git 字段对齐问题同 RV-02 |

### 6.2 F030 自身缺陷与 Architect 遗留

| 项 | 原判定 | 复核结论 |
| --- | --- | --- |
| F030-TD1-01（TD 引用悬空 I-1/I-3、P3.1 计数 4≠5） | LOW | **CLOSED**：TE-5 以机械可核验判据裁定并逐项执行；TD2-P1.5 列数结论与文件实际一致 |
| F030-T01（空态文案成因歧义） | NOTE | **升级为 LOW（F030-RV-04）**，仍非必须修复 |
| F030-T02（`canSubmitGrant` 签名扩展） | NOTE | **记载升级为 LOW（F030-RV-03）**，仍非必须修复；行为更严格、smoke 逐条覆盖 |
| F030-T03（端到端 500 未串联） | NOTE | **接受为 NOTE**。证据链 = 服务层 FK 违约用例 + `app/core/errors.py` 统一 `Exception → 500 INTERNAL_ERROR` 处理器 + F002 信封用例（全量套件内执行）；Test Report 已如实标注 NOT TESTED，未夸大 |
| F030-T04（`*.log` 被 .gitignore 忽略） | NOTE | **CLOSED**：`git ls-files docs/features/F030/artifacts` = **17** 份，已入库 |
| Architect §16.4 I-1 / I-3 | 遗留 | **CLOSED**（TE-5 裁定）；I-2 / I-4 已同批修正；I-5 维持 PROPOSED 不做；I-6 实地核验通过 |

## 7. Follow-ups（非阻塞，按 Owner 分派）

1. **Coordinator（MERGE 前必须）**：把 F030 `status` 按状态机补为 `IN_REVIEW`（当前 `IN_PROGRESS` + `current_stage: REVIEW`，见 F030-RV-01），否则 `IN_PROGRESS → DONE` 会被转换检查拒绝。
2. **Coordinator**：Merge Gate 写入 approved HEAD = `891206a54aa0d5f1f731e6d9044ac8f98e11be2a`、Base = `70db846`、真实 merge SHA；更正 `git.head_commit`（F030-RV-02）。
3. **Coordinator**：合并后恢复 `project.acceptance.status = COMPLETE`，并把 F030 证据（`docs/features/F030/test-report.md#test-executiontest-12026-10-23v1`、`artifacts/targeted-pytest.log`、`full-pytest.log`、`frontend-smoke.log` 等）加入 `acceptance.evidence`，清除 `pending_reason`。
4. **Architect**：在 `architecture.md` 记录 `canSubmitGrant` 签名偏离（F030-RV-03）、补 I-2 类条目以对齐代码引用（F030-RV-09）、酌情澄清 F026 头部 `plan_revision 14` 的历史属性（F030-RV-08）。
5. **Architect / Frontend**：候选空态文案改回因中性表述（F030-RV-04）。
6. **Backend（下次触碰该文件时）**：把注释中「undeclared params … before the handler」精确化为「在 handler 内先于路径/语义校验」（F030-RV-05）。
7. **Tester**（可选）：并发用例保留失败语义并增加尝试次数/记录；修正 `p3-p6-static.log` 的路径笔误（F030-RV-06/07）；后续可评估把 `real_scope` 守卫扩展到其它测试目录（F030-RV-10）；如需要可补 grant 路径端到端 500 信封用例（T03）。

## 8. 未审查项及原因

| 项 | 原因 |
| --- | --- |
| 全量后端套件（728 passed / 6 skipped）**未由 Reviewer 重跑** | 耗时约 17 分钟；改以「独立复跑 6 个关键新例全 PASS」+「`--collect-only` 实测 733 + 1 module skip」+「计数算术一致性（726+7=733、721+7=728、6 skipped 原因集合与 F029 基线相同）」+「测试后实现零改动」四段证据交叉核对 |
| `npm run build` 未重跑 | 会写 `frontend/dist`；改跑 `npx tsc --noEmit`（exit 0）与 `npm run smoke:client`（328 passed），构建证据沿用归档日志 |
| 真实浏览器 DOM / 焦点 / 窄屏 / 键盘可达性 | 设计 §7.3 排除、仓库无 DOM 测试框架；Test Report 已如实标 NOT_REQUIRED，未声称完成 |
| ACTIVE > 2000 条真实 `truncated` 路径、并发压力/多轮竞态 | 需构造超量数据与真实前端；仅机制断言 + 书面结论 |
| 全量 Compose 启动 | 沿用 F029 记录的环境限制（bootstrap 缺 `INITIAL_ADMIN`），未执行 |
| grant 路径端到端 500 信封 | 未串联（两段证据链），与 Test Report 口径一致 |
| 锚点 slug 的机械有效性 | `validate_project_state.py` 只校验文件存在；按 GitHub slug 规则人工核对 F030 三个锚点形式一致，未用工具解析 |
| 环境事实：pytest 7.4.4 < `pyproject` 要求 `>=8` | 既有环境事实（F029 同版本），不据此判缺陷；仅记录 |

## 9. Verification（Reviewer 实际执行）

**只读 / 基线**
- `git status/HEAD/Base/merge-base/diff --stat/log/diff --cached/untracked/stash/reflog`：工作区 clean、无暂存/未跟踪、无中断操作；HEAD=`891206a`、Base=`70db846`、merge-base 一致；范围 46 文件 +2794/−87、7 commits。
- 逐文件核验：12 份域 Contract `删除行 = 0`；F026 删除 4 行（3 行签核记载 + 1 行 EOF 归一）；F030 修订记录行单元格数 = 各文件表头列数；`docs/product`、`docs/database`、`backend/alembic`、`app/{models,schemas,core,api}`、`frontend/src/api`、`permissions.py`、`docs/api/F027.md` 全量空 diff；Backend 生产代码差异全部为注释行；测试文件纯追加。
- 计划一致性：`validate_project_state.py` → `PROJECT STATE VALID`；`render_project_views.py`（无 `--write`）→ `PROJECT VIEWS VALID`；`--feature F030` → VALID；`--previous`（Base 快照）→ VALID。三次执行后 `git status` 仍为空。
- `git ls-files docs/features/F030/artifacts` = 17（T04 已闭环）。

**独立复跑（真实 PostgreSQL 16.15 @ localhost:55432/csm_test；`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`，输出仅写 `/tmp`）**
- `test_list_q_boundary_validation` + `test_f030_test_harness.py`（3 例）→ **4 passed**。
- `test_concurrent_grant_two_connections_single_winner` + `test_grant_non_unique_integrity_error_is_not_mapped_to_409` → **2 passed**，输出 `attempt 1: statuses=[409,201] overlap=True`。
- `pytest --collect-only` → **733 collected + 1 module skip**（与归档一致）。

**前端**
- `npx tsc --noEmit` → exit 0。
- `npm run smoke:client` → **328 passed / 0 failed**（含 6 条 F030 断言）；执行后 `git status` 仍为空。

**守卫非空洞性（自建 /tmp 探针，未写仓库）**
- 以 /tmp 目录替换 `INTEGRATION_DIR` 后运行守卫 `_scan()`：未打 marker 但使用 `resolve_access_scope` 的模块被列入 `offenders`，模块级 `pytestmark` 被正确识别。

**代码/契约一致性抽查**
- `_reject_unknown_query`（handler 内第一步）先于 `_parse_uuid`；`_get_user_or_404`（136 行）先于 `_validate_q`（143 行）→ 与 P-1 一致。
- `grant_authorization`：`except IntegrityError` 仅在 `uq_user_cluster_authorizations_user_id_cluster_id` 时 `raise Conflict("already_granted")`，其余 `raise`；`rollback` 先执行 → 与 F026 §5 v3 一致；`app/core/errors.py` 全局 `Exception → 500 INTERNAL_ERROR` 无堆栈。
- 前端 `describeClusterAuthorizationError.alreadyGranted` 为 Base 既有（`src/api/clusterAuthorizations.ts` 无 diff）。
- 面板 API 调用计数与 Base 逐项相同（`listClusterAuthorizations` 3=3、`listClusters` 2=2、`grantClusterAuthorization` 2=2、`revokeClusterAuthorization` 2=2）。
- 基线对照：F029 `721/6 skipped`、`322 smoke`、定向 21 → F030 `728/6`、`328`、定向 28（+7 / +6 / +7，与新增用例清单一致）。

## 10. 批准边界

本批准仅对候选 **HEAD `891206a54aa0d5f1f731e6d9044ac8f98e11be2a`** 与 **Base `70db846ca2ed4bad90281ad5f55c1e6a9b2c5300`（`v3.2`）** 有效。候选 HEAD、Base 或 `docs/api/F026.md` v3 / 12 份域 Contract 增补节 / 设计要求版本任一变化即需重新验证与 Review。Merge、DONE 与 `project.acceptance` 恢复由协调器按 Git Workflow §5 判定；本报告中的建议不构成产品或架构决定（F030-RV-03/04/08/09 的具体形态仍需 Architect 在职责内定稿）。

GIT: git status --short
GIT: git branch --show-current
GIT: git rev-parse HEAD
GIT: git rev-parse v3.2
GIT: git rev-parse v3
GIT: git merge-base v3.2 HEAD
GIT: git diff --stat v3.2...HEAD
GIT: git log --oneline v3.2..HEAD
GIT: git diff --cached --stat
GIT: git ls-files --others --exclude-standard
GIT: git diff --stat
GIT: git stash list
GIT: git reflog -5
GIT: git diff v3.2...HEAD -- backend/ frontend/src/components/authorizationCandidates.ts
GIT: git diff v3.2...HEAD -- frontend/src/components/authorizationCandidates.ts frontend/src/components/ClusterAuthorizationPanel.tsx
GIT: git diff v3.2...HEAD -- frontend/scripts/smoke-client.mjs
GIT: git diff v3.2...HEAD -- docs/api/F026.md
GIT: git diff v3.2...HEAD -- docs/api/F002.md docs/api/F003.md docs/api/F004.md docs/api/F007.md docs/api/F008.md docs/api/F009.md docs/api/F010.md docs/api/F011.md docs/api/F012.md docs/api/F013.md docs/api/F014.md docs/api/F023.md
GIT: git diff v3.2...HEAD -- docs/project/project-plan.yaml
GIT: git log -1 --format=%s 1fdaa5b a8d653a 4335860 b1b6ba1 7c19df8 56cc6ac 891206a
GIT: git show --stat --format="" 1fdaa5b a8d653a 4335860 b1b6ba1 7c19df8 56cc6ac 891206a
GIT: git diff --name-only 56cc6ac..HEAD
GIT: git diff --stat 56cc6ac..HEAD -- backend/ frontend/ docs/api/
GIT: git diff 56cc6ac..HEAD -- docs/project/project-plan.yaml
GIT: git diff --name-only v3.2...HEAD
GIT: git diff v3.2...HEAD -- docs/api/F002.md docs/api/F003.md docs/api/F004.md docs/api/F007.md docs/api/F008.md docs/api/F009.md docs/api/F010.md docs/api/F011.md docs/api/F012.md docs/api/F013.md docs/api/F014.md docs/api/F023.md docs/api/F026.md
GIT: git diff v3.2...HEAD --stat -- docs/product/
GIT: git diff --stat v3.2...HEAD -- backend/alembic backend/app/models backend/app/schemas backend/app/core backend/app/api frontend/src/api docs/database
GIT: git diff --stat v3.2...HEAD -- backend/app/core/permissions.py
GIT: git log --oneline -5 v3.2 -- docs/project/project-plan.yaml
GIT: git show f26b641:docs/project/project-plan.yaml
GIT: git log --oneline -3 -S"pending_reason" -- docs/project/project-plan.yaml
GIT: git show 70db846:docs/project/project-plan.yaml
GIT: git show 9d36e6c:docs/project/project-plan.yaml
GIT: git show v3.2:frontend/src/components/ClusterAuthorizationPanel.tsx
GIT: git show 70db846:docs/project/project-plan.yaml > /tmp/csm-plan-base-f030review.yaml
GIT: git ls-files docs/features/F030/artifacts
GIT: git diff v3.2...HEAD -- docs/project/backlog.md docs/project/dependency-map.md docs/project/milestones.md
GIT: git diff v3.2...HEAD -- backend/tests/integration/test_cluster_authorizations.py backend/tests/conftest.py backend/pyproject.toml frontend/scripts/smoke-client.mjs frontend/src/components/ClusterAuthorizationPanel.tsx
GIT: git diff v3.2...HEAD -- backend/tests/integration/test_cluster_authorizations.py
GIT: git status --porcelain=v1 --untracked-files=all
GIT: git diff --shortstat v3.2...HEAD
GIT: git log --oneline v3.2..HEAD
GIT: git for-each-ref --format='%(refname) %(objectname:short)' refs/heads/v3 refs/tags/v3 refs/remotes/*/v3
GIT: git branch --list 'v3*'
GIT: git merge-base --is-ancestor v3.2 v3
GIT: git merge-base --is-ancestor v3 v3.2
GIT: git log --oneline -3 v3
GIT: git branch --contains v3.2
GIT: git rev-parse --short main
