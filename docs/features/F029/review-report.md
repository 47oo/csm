# F029 Review Report

## Task / Status

- **Task**：F029「Review 低优先级跟进项：安全加固、契约回写与测试固化」正式 Review（REVIEW Gate），只读审查，不修改任何仓库文件。
- **Status**：`APPROVED WITH FOLLOW-UP`

---

## Basis

| 类别 | 依据 |
| --- | --- |
| 需求基线 | `docs/product/requirements-v3.md` revision 11（§23/§23.2 集群范围授权、§22 Audit、§31 测试、§32 上线验收、§35.1/§35.2 确认记录；CHG010-BQ01–BQ17 CONFIRMED，BQ18/BQ19 DESIGN_INPUT） |
| 计划/批准 | `docs/project/project-plan.yaml` plan_revision 15，`project.approval`（approved_by 用户、2026-10-22、feature_ids 含 F029、basis 用户「将 review 的低优先级跟进项完成一下」）；`execution.authorization` plan_revision 15 / SINGLE / F029 |
| 变更控制 | `docs/project/change-control.md` §1–§5；`docs/project/project-state.md` §1–§5 |
| 上游 Review | `docs/features/F026/review-report.md`（APPROVED WITH FOLLOW-UP，F026-RV-01…09）、`docs/features/F027/review-report.md`（R1 已关闭，R2/R3/R5/R6/R7 跟进）、`docs/features/F028/review-report.md`（R1 关闭，其余跟进） |
| Contract | `docs/api/F026.md` v2（2026-10-22 修订）、`docs/api/F027.md` v1（READY，Architect）、F002 v3、F003/F004/F007–F014/F023 追加 F027 范围引用 |
| 阶段报告 | `docs/features/F029/implementation.md`、`docs/features/F029/test-report.md`（Status：READY FOR REVIEW）、`docs/features/F029/artifacts/*` |
| 规则 | `AGENTS.md`、`.pi/agents/reviewer.md`、`docs/project/handoff.md`、`docs/project/git-workflow.md` §4/§5、`docs/project/implementation-rules.md`、`.pi/skills/data-integrity/SKILL.md`、`.pi/skills/frontend-ui` 基线（Ant Design + Tailwind） |

---

## Scope Reviewed

| 项 | 值 |
| --- | --- |
| Feature Branch | `feature/F029-review-followups` |
| start_commit | `4f83a0eb8fc0c7b0a3ae2db64d3249ca45f159cf` |
| candidate HEAD | `6e8abdb23ba2399efb6bb0a76eb30b7eaed4d5fc` |
| Base | `v3.2` = `4f83a0eb8fc0c7b0a3ae2db64d3249ca45f159cf` |
| merge-base | `4f83a0eb8fc0c7b0a3ae2db64d3249ca45f159cf` |
| 完整范围 | `4f83a0e..6e8abdb`，5 commits，44 files，+1224/−78 |
| 提交序列 | `0e5d8fc`（实现+契约+测试+报告）→ `f26b641`（证据日志 + test-report + plan）→ `cd7681a`（测试加固 + F026.md 措辞 + F026 product 标签）→ `de527f9`（targeted/full 日志归档 + plan）→ `6e8abdb`（**仅 8 个 `.pi/agents/*.md` 的 `model` 行**，用户授权配置变更） |
| 工作区 | clean；无暂存、无未跟踪文件；无进行中 merge/rebase（`git status --short`、`git diff --cached`、`git ls-files --others` 均为空） |
| 基线可信性 | HEAD/Base/merge-base 与协调器给定值一致；`start_commit..HEAD` 历史已逐提交核对，未发现基线外变更 |

**关于 `6e8abdb`**：已逐文件核对，8 个文件中每份只有 1 行 `model:` 变更（`local/… → local-29000/DeepSeek-V4.1-Flash-1017:high`），**不夹带任何业务、测试、契约、Schema 或计划改动**，与 F029 实现无关，属用户明确授权的工具配置变更。唯一提示：该提交将随 F029 一并合入 `v3.2`（见 F029-RV-11）。

---

## 分层结论

| 层 | 结论 |
| --- | --- |
| 产品/领域 | **通过**。F029 未新增对象、关系、状态、唯一性或生命周期规则；F026 product A-3 由 PROPOSED 改为「已按 Contract §9.7 记录」属文档同步（§9.7 与 §23.2 均已 CONFIRMED，非新裁定）。CHG010-BQ19「授权列表分页/排序与 System UI 口径」为 DESIGN_INPUT，前端候选过滤/409 行为在其设计自由度内，无需产品裁定。 |
| 架构/依赖 | **通过**。无新依赖（`backend/pyproject.toml` 仅新增 pytest marker 注册）、无新端点/权限项/中间件；`scope_filters` 谓词重命名与既有 `service_parent_predicate`/`pool_predicate` 命名约定一致。 |
| 数据 / Migration | **不适用变更**（复核性通过）。本 Feature 无 Schema、Migration 改动；F026 迁移 0015 的 `downgrade()` 与 `upgrade()` 对象对称（触发器→函数→索引→表），触发器 `ERRCODE check_violation/restrict_violation` 与新增断言 `23514/23001` 精确对应，部分唯一冲突 `23505` 亦断言到 SQLSTATE。 |
| API / Contract | **基本符合**。F026 v2 的 P-1 顺序与实现一致：`q` 由服务层在 `_get_user_or_404` 之后校验（未知用户 → 404）；`status/cluster_id/page/page_size/sort/order` 为 FastAPI 类型化参数，在 handler 前 422。域 Contract 追加的 F027 引用与 `docs/api/F027.md` §2–§4 语义一致，未改端点/字段/错误码/权限。签发记录完整性见 F029-RV-01；非唯一完整性错误语义见 F029-RV-08。 |
| 后端 | **通过**。`list_authorizations` 404 前置符合 P-1；`grant_authorization` 仅在 `diag.constraint_name == uq_user_cluster_authorizations_user_id_cluster_id` 时映射 409，其余原样抛出（重复授予 409 路径由既有测试真实覆盖）；`interface_parent_predicate` 重命名无残留（全仓仅 `implementation.md` 提及旧名）；`normalize(None)` 由 HTTP 路由依赖静态断言兜底。 |
| 前端 | **通过（有 NOTE）**。撤销 409 `already_revoked` 现按 Contract D-5「关闭并刷新」执行（关闭 `revokeTarget`、提示、`reloadToken+1`），其他错误仍内联呈现；候选排除改为分页拉取该用户全部 ACTIVE 授权（page_size 100、上限 20 页）并在授予后增量加入。交互细节见 F029-RV-05。 |
| 测试 | **可信但不完全覆盖**。定向 21 例已由本人独立重跑通过；全量 721 passed / 6 skipped 的**计数**与当前收集数一致（726 collected + 1 module 级 skip = 727 = 721+6）；SMOKE 与 typecheck 独立复现。缺口见 F029-RV-02/RV-03/RV-06。 |
| 安全 | **通过**。错误顺序未放宽、未授权/Audit/凭据语义未变；404 优先与 F027「不泄露未授权对象」规则同向；无敏感信息进入日志或响应；无破坏性数据操作、无新增外部输入面。 |
| 变更与批准 | **通过（有 LOW）**。plan_revision 15 覆盖 F029；`pending_changes: []`；F026/F027/F028 均 DONE（依赖满足）；`project.acceptance.status=PENDING` + `pending_reason` 未被提前置 COMPLETE；`scripts/validate_project_state.py` 与 `render_project_views.py`（只读）均通过。Contract v2 与 12 份域 Contract 的签核/版本记载偏弱（RV-01）。 |

**数据完整性对应表（F029 适用项）**

| 规则依据 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §23.2 / F026 §9「有效授权唯一」 | `POST /users/{id}/cluster-authorizations` | 部分唯一索引 `uq_…_user_id_cluster_id`（0015）；迁移级断言 `23505` | 插入后捕获 IntegrityError，仅该约束映射 409 `already_granted` | 并发竞态由唯一索引兜底；**无真并发用例**（RV-03） | 真实 PG 定向 21 passed（本人复跑）；重复授予 409 reason 断言 |
| §23.2「撤销保留历史，不物理删除」 | `POST /cluster-authorizations/{id}/revoke` | 不可变触发器 `check_violation` + append-only 触发器 `restrict_violation` | 条件 UPDATE + `rowcount==0 → 409 already_revoked` | 同事务 Audit；down/up 对象对称 | SQLSTATE `23514/23001` 精确断言；`test_f026_0015_downgrade_removes_only_f026_objects` |
| §23.2「ADMIN 降级后按既有授权解析；停用不删授权」 | 用户角色/状态变更 | 授权行独立于 `users.status/role` | `resolve_access_scope` 逐请求解析 | 停用保留行、升级不受限、降级恢复集合 | 新增 `test_admin_upgrade_downgrade_and_disabled_account`（真实 `resolve_access_scope`） |
| F027 §1「范围逐请求解析，不缓存」 | 全部业务路由 | — | 每路由依赖 `get_access_scope` | — | `test_every_business_route_depends_on_real_scope`：本人独立枚举确认 **64 条业务路由全部命中**，20 条豁免项与设计一致（health/auth/users/api-keys/audit/deleted/cluster-authorizations/templates） |

---

## Findings

### F029-RV-01 · LOW · Contract/批准记录

- **Location**：`docs/api/F026.md`（v2 头部「签核」行）、`docs/api/F002/F003/F004/F007–F014/F023.md` 末章「F027 范围语义（加法引用）」
- **证据**：`git diff v3.2...HEAD -- docs/api/` 显示 F026.md 升 v2 并改写 P-1 顺序与 `q` 控制字符规则；12 份域 Contract 各追加一节引用，均**无版本表行、日期与签核主体**。F026 v2 仅在「签核」行写「Architect，2026-10-21（v1）；F029 跟进修订 v2（2026-10-22，P-1/q 顺序澄清）」，未记录 v2 的确认来源；F029 `implementation.md` 未记录 Architect 对 v2 的签核。
- **期望 vs 实际**：change-control §2 要求「批准者、日期、对象版本、覆盖范围、确认来源」记录于权威正文；实际由实现提交一并写入，签核来源不可独立核验。
- **影响**：批准可追溯性偏弱；不致行为风险（正文明确「端点/字段/错误码/权限不变」，且新增引用与 F027.md 已签核内容一致）。
- **是否必须修复**：否（可归入 change-control §2「纯链接/编辑维护」范畴，但需补齐记载）。
- **Owner**：Architect（确认 v2 与 12 份追加章节）→ Coordinator 记录。

### F029-RV-02 · LOW · Tests

- **Location**：`backend/tests/integration/test_cluster_authorizations.py:381`
- **证据**：新增断言仅 `_list(admin, uuid.uuid4(), q="") → 404`；同文件无「已知用户 + `q=""`/控制字符 → 422」断言，也无「未知用户 + 未知查询参数 → 422」（`_reject_unknown_query` 先于路径校验）。全仓 grep 无 `_validate_q` / `must not contain control` 相关用例。
- **期望 vs 实际**：Contract v2 首次书面化「`q` 含控制字符 → 422」并明确列表校验顺序；实际只锁定了顺序的一侧，若 `_validate_q` 被移除或再次调整顺序，新增断言仍会通过。
- **影响**：回归保护不足，非当前功能缺陷。
- **是否必须修复**：否。
- **Owner**：Tester。

### F029-RV-03 · LOW · Tests / 完整性

- **Location**：`docs/features/F029/implementation.md` §1（F026-RV-03 行）、`backend/tests/integration/test_cluster_authorizations.py`
- **证据**：plan scope ⑩ 要求「补充 F026 并发/升降级/停用等可重复回归测试」，实际新增为升降级/停用、SQLSTATE、downgrade 对称性、路由覆盖；**无并发授予用例**，也**无非唯一 IntegrityError 原样抛出的用例**。`implementation.md` 以「F027/F028 已有并发证据」解释，但 F027 T-F027-27 是范围/请求边界并发（快照、锁序），不含 F026 授予竞态。
- **期望 vs 实际**：以两条真实连接固化「并发重复授予 → 201 + 409」与数据库唯一兜底。
- **影响**：授予竞态的正确性目前只由迁移级 `23505` 与顺序用例间接证明。
- **是否必须修复**：否（F026-RV-03 原评级为「非阻塞」）。
- **Owner**：Tester / Backend。

### F029-RV-04 · LOW · Plan/Evidence

- **Location**：`docs/project/project-plan.yaml`（F029 `evidence.test` / `evidence.test_design`）
- **证据**：`evidence.test` 仅 `test-report.md#test-executiontest-12026-10-22`、`run.log`、`pytest.log`、`t36.log`，未列 `de527f9` 归档的 `targeted-pytest.log`、`full-pytest.log`、`frontend-build.log`、`frontend-smoke.log`；`evidence.test_design` 指向 `implementation.md` 而非 `test-report.md` 的 TD-1；锚点 `#test-executiontest-12026-10-22` 与标题「## Test Execution（TEST-1，2026-10-22）」的标准 slug（`…test-1-2026-10-22`）不一致（校验器只校验文件存在，故未报错）。
- **影响**：全量回归与前端证据在计划层不可直达；不影响实现正确性。
- **是否必须修复**：否（DONE 状态提交时一并补齐）。
- **Owner**：Coordinator。

### F029-RV-05 · NOTE · Frontend 交互

- **Location**：`frontend/src/components/ClusterAuthorizationPanel.tsx`（`openGrant`/`loadActiveGrantIds`/`candidates`）
- **证据**：`openGrant` 先 `setGrantOpen(true)` 再 `await loadActiveGrantIds(...)`；加载期间 `activeGrantIds` 为上一轮值或空集，候选列表会短暂包含已授权 Cluster；加载失败时置空集并显示错误，用户仍可提交并收到服务端 409 `already_granted`；`page <= 20` 上限使 ACTIVE 授权 >2000 条时排除不完整。
- **期望 vs 实际**：期望加载完成后再呈现候选或提交按钮门控；实际依赖服务端 409 兜底。
- **影响**：仅为交互瑕疵，无数据风险（唯一约束 + 409 如实呈现，错误未被隐藏）。
- **是否必须修复**：否。
- **Owner**：Frontend。

### F029-RV-06 · NOTE · Tests

- **Location**：`docs/features/F029/test-report.md` TD-1「覆盖」
- **证据**：TD-1 声明覆盖「撤销 409 UI」「候选跨分页」，但仓库无组件级/DOM 测试；`smoke:client` 只覆盖 `describeClusterAuthorizationError` 的 409 分类（322 passed 中可见），不覆盖组件反应。报告「未验证」段只提真实浏览器 DOM，未把这两项标注为「仅静态核对」。
- **影响**：覆盖声明与实际验证手段不完全对齐。
- **是否必须修复**：否。
- **Owner**：Tester。

### F029-RV-07 · NOTE · Backend 注释准确性

- **Location**：`backend/app/services/cluster_authorization.py:128-133`
- **证据**：注释称「This also removes the 422-vs-404 existence oracle for unknown users combined with an invalid q」。改动前该组合对未知/已知用户一律 422（更难区分），改动后未知用户恒 404。真正的依据是 Contract P-1「路径对象优先」，而非消除 oracle（且该端点仅 USER_ADMIN 可访问，探测风险本就有限）。
- **影响**：注释结论方向与事实不符，可能误导后续维护者。
- **是否必须修复**：否（建议改写为「遵循 P-1 路径对象优先」）。
- **Owner**：Backend。

### F029-RV-08 · NOTE · Contract 语义完整性

- **Location**：`backend/app/services/cluster_authorization.py` `grant_authorization` except 分支；`docs/api/F026.md` §5
- **证据**：收窄后非唯一完整性错误（如提交瞬间 Cluster 被软删引发 FK 冲突）由 409 变为未处理的 IntegrityError → 500 `INTERNAL_ERROR`；Contract 未记录该语义。
- **影响**：极端竞态下响应码与 Contract 的 422（cluster 不存在）不一致；符合 F026-RV-07 既定跟进决定，无静默行为放宽。
- **是否必须修复**：否（建议 Architect 在 F026.md 补一句语义说明）。
- **Owner**：Architect / Backend。

### F029-RV-09 · NOTE · 测试夹具设计

- **Location**：`backend/tests/conftest.py::auth_app`
- **证据**：改为显式 `real_scope` marker 后，集成测试的**默认**仍是「unrestricted AccessScope 覆盖」；仅 `test_cluster_authorizations.py`、`test_f027_access_scope.py` 打标记（已核对，无其他集成模块依赖真实 scope）。`test_f028_acceptance.py` 走真实 HTTP，无需 marker，其 `pytestmark = skipif` 也不受影响。
- **影响**：未来新增的集成测试若忘记 marker，会以无范围限制静默运行并可能假 PASS；现有 docstring 只说明「Pre-F027 suites」。
- **是否必须修复**：否（当前覆盖集合与改前等价，风险为前瞻性）。
- **Owner**：Coordinator / Backend。

### F029-RV-10 · NOTE · 无关变更

- **Location**：`backend/tests/integration/test_f028_acceptance.py:40-42`
- **证据**：`cd7681a` 仅新增两个空行（形成 3 个连续空行），无功能作用；仓库未配置 lint（无 ruff/flake8 段），故未触发 E303。
- **影响**：噪音，无功能影响。
- **是否必须修复**：否。
- **Owner**：Tester。

### F029-RV-11 · NOTE · 分支内容与 git 字段

- **Location**：`6e8abdb`、`docs/project/project-plan.yaml` F029 `git.head_commit`
- **证据**：候选 HEAD 为 `6e8abdb`（配置），计划 `git.head_commit: cd7681a`。按 Git Workflow §2，「head_commit 为最近已记录的交付/检查点提交」可接受，但 §5 要求合并时把 **approved HEAD（6e8abdb）** 写入 `head_commit`，并确认 `.pi/agents` 配置变更随 F029 合入 `v3.2` 是用户本意。
- **影响**：状态字段与合并动作的对齐属协调器义务。
- **是否必须修复**：否（合并时处理）。
- **Owner**：Coordinator。

---

## 旧缺陷复核（F026 / F027 / F028 follow-up 关闭情况）

| 旧项 | 原 Severity | 复核结论 | 依据 |
| --- | --- | --- | --- |
| F026-RV-01 未知用户+非法 q 的 404/422 顺序；q 规则未入 Contract | LOW | **CLOSED（测试侧部分保留，见 RV-02）** | 服务层 404 前置；F026.md v2 写入 q 控制字符规则与顺序；回归断言 404 |
| F026-RV-02 撤销 409 未关闭刷新 | LOW | **CLOSED（无自动化回归，见 RV-06）** | `confirmRevoke` 命中 `alreadyRevoked` 时关闭 + 提示 + 刷新；与 Contract D-5 对齐；`describeClusterAuthorizationError` 分类被 smoke 覆盖 |
| F026-RV-03 TD-1 用例未固化 | MEDIUM（非阻塞） | **PARTIALLY CLOSED** | 升降级/停用/SQLSTATE/downgrade/路由覆盖已固化；并发仍未固化（RV-03） |
| F026-RV-04 CHG-010 状态与计划锚点 | LOW | **CLOSED** | 计划/CHG-010/§23.2 已在批准落地时同步；本轮补 F026 product A-3 标签 |
| F026-RV-05 evidence.test 指向旧 RETURN | LOW | **CLOSED（同类问题再现于 F029 自身，见 RV-04）** | 计划 F026 `evidence.test` 现指向 `#repair-verification-1`（已在 F027 test-report 中确认该锚点存在） |
| F026-RV-06 候选排除仅当前分页 | LOW | **CLOSED（实现正确，交互待优化）** | `loadActiveGrantIds` 分页拉全量 ACTIVE 并排除；授予后增量加入 |
| F026-RV-07 grant IntegrityError 统一 409 | NOTE | **CLOSED** | 仅 `uq_user_cluster_authorizations_user_id_cluster_id` → 409；其余 `raise`；既有重复授予用例真实命中该分支 |
| F026-RV-08 触发器 SQLSTATE / downgrade 对称性 | LOW | **CLOSED** | `23514/23001/23505` 精确断言；`test_f026_0015_downgrade_removes_only_f026_objects` 断言 down 后表/函数/触发器/索引全消失、users/clusters/audit_logs 保留、up 后恢复；与 0015 `downgrade()` 实现对称 |
| F026-RV-09 Product A-1/A-2/A-3 标签滞后 | NOTE | **CLOSED** | A-1 §9.3、A-2 §2.1/§9.1、A-3 §9.7 均已在 product.md 标注并可在 F026.md 找到对应正文 |
| F027-R1 隐藏 Interface 错误文案泄露 | MEDIUM（首轮 must-fix） | **CLOSED（未回退）** | 定向套件独立复跑 21 passed 含 `test_hidden_interface_error_is_indistinguishable_from_missing` |
| F027-R2 探针未入库 | 非阻塞 | **CLOSED** | 新增路由依赖覆盖、SQLSTATE、生命周期用例入库；探针关键断言由 F026/F027/F028 仓库测试覆盖 |
| F027-R3 各域 Contract 未回写 | 非阻塞 | **CLOSED（签核记载待补，见 RV-01）** | 12 份域 Contract 已追加 F027 引用，F013 强调 Dashboard counts/networks，F014/F023 强调导入行错误与整批失败，与 F027.md §2–§4 一致 |
| F027-R5 `normalize(None)` unrestricted 默认 | 非阻塞 | **CLOSED** | docstring 明确「HTTP 路由必须传真实 scope」+ 静态路由依赖断言（本人独立枚举 64/64 命中） |
| F027-R6 `auth_app` 按文件名放行 | 非阻塞 | **CLOSED（前瞻风险见 RV-09）** | 改为 `real_scope` marker + pyproject 注册；两个真实 scope 模块已打标记 |
| F027-R7 `resource_predicate` 命名偏窄 | 非阻塞 | **CLOSED** | 重命名 `interface_parent_predicate`，两处调用点同步，全仓无旧名残留 |
| F027-R4 Plan git 基线字段 | MEDIUM（DONE 前） | **CLOSED** | F027 计划 git 字段已存在；F029 自身字段齐全 |
| F028-R1 验收未绑定已提交 HEAD | MEDIUM（首轮 must-fix） | **CLOSED（未回退）** | F029 日志 `run.log` 记录 `HEAD=0e5d8fc`；`0e5d8fc..cd7681a` 经核对仅测试/文档，生产代码一致 |
| F028-R2 Dashboard 断言依赖顺序 | 非阻塞 | **CLOSED** | `test_f028_acceptance.py` 使用本用例 A/B Cluster 局部计数 + C 不可见断言 |
| F028-R3 缺 smoke 日志 / R4 Compose 失败表述 / R5 Plan git 字段 / R7 IN_REVIEW / R8 bootstrap stderr / R9 `headers_none` | 非阻塞 | **CLOSED** | F028 artifacts 已归档 smoke；F029 `compose-up.log` 显示 `service "bootstrap" didn't complete successfully: exit 2`（`run.log` 记 `compose exit=1` 为 docker compose 汇总码，两处一致、未夸大为成功）；F028 计划字段与 DONE 状态齐全 |
| F028-R6 整体验收锚点 | 非阻塞 | **CLOSED（锚点选择可优化，见 RV-04）** | `project.acceptance.evidence` 现含 `docs/features/F027/test-report.md#repair-verification-1`；该文件 TE-4 载有 T87/T89/T96/T99 PASS 映射。建议补 `#te-4-…` 直链 |

**新增回归检查**：本 Feature 未发现新的行为回归（改前/改后语义等价或按既定跟进项收窄）；前端 smoke 322 passed、typecheck 0 error 独立复现。

---

## Follow-ups

1. **Architect**：确认 `docs/api/F026.md` v2 与 12 份域 Contract 追加章节，并在正文记录签核者/日期/版本（或由 Coordinator 按 change-control §2 记为「编辑维护」）。（RV-01）
2. **Tester**：补 `q` 两侧断言（已知用户 `q=""` / 控制字符 → 422；未知用户 + 未知查询参数 → 422）。（RV-02）
3. **Tester/Backend**：固化 F026 授予真并发（201+409）与非唯一 IntegrityError 原样抛出的用例。（RV-03）
4. **Coordinator**：DONE 状态提交时补齐 F029 证据（`targeted-pytest.log`、`full-pytest.log`、`frontend-*.log`）、修正 `test_design` 证据指向与锚点 slug，并在 `project.acceptance` 增加 `docs/features/F027/test-report.md#te-4-…` 直链后恢复 `COMPLETE`。（RV-04、F028-R6 遗留）
5. **Frontend**：候选加载期间门控提交/提示，或加载完成后再呈现列表；评估超大授权量下的排除完整性。（RV-05）
6. **Backend**：修正 `list_authorizations` 注释表述；**Architect** 在 F026.md 补记「非唯一完整性错误 → 500」语义。（RV-07、RV-08）
7. **Coordinator/Backend**：在 conftest/测试规范中显式声明「集成测试默认为 legacy unrestricted 覆盖，真实 scope 需 `real_scope` marker」。（RV-09）

---

## 未审查项及原因

| 项 | 原因 |
| --- | --- |
| 全量后端 `pytest -q`（721 passed / 6 skipped） | 未重跑（归档日志显示 18 分 34 秒）；改为核对**收集数一致性**（726 collected + 1 module 级 skip = 727 = 721 + 6）与归档日志内容，并独立重跑定向 21 例 |
| F028 真实等价栈 `4 passed`、T36 B1–B7 | 未重跑（需拉起 Compose 等价栈、备份/恢复容器）；仅核对 `run.log`/`t36.log`/`compose-up.log` 的内部一致性与 alembic head `0015_user_cluster_authorizations` |
| 前端 `vite build` | 未重跑（会写入 `frontend/dist`，违反只读约束）；`tsc --noEmit` 与 `smoke:client` 已独立复现 |
| 真实浏览器 DOM/焦点/窄屏、Compose 成功启动 | 环境限制，Tester 已如实记录，未计入 PASS |
| 并发压力测试 | 仓库既无该用例（RV-03），非本次遗漏 |
| `6e8abdb` 模型配置的可用性 | 属工具配置，不属产品/代码审查范围；已确认仅 `model` 行 |
| v3.2 基线既有实现（F026/F027/F028 生产代码） | 仅就 F029 触及范围抽查（`list_authorizations`、`grant/revoke`、`scope_filters`、`interface.py`、前端面板）；未做基线全面再审 |

**基线说明（非 F029 缺陷）**：`git-workflow.md` §1/§4 以 `v3` 为集成分支，本 Feature 记录 `base_branch: v3.2`，沿用的是 F026–F028 已记录的版本集成分支基线，非本 Feature 引入。

---

## Verification

| # | 命令 / 动作 | 结果 |
| --- | --- | --- |
| 1 | `git rev-parse --show-toplevel` / `git branch --show-current` / `git status --porcelain=v1 --untracked-files=all` / `git rev-parse HEAD` / `git branch -a` | 仓库 `…/csm`；分支 `feature/F029-review-followups`；工作区 clean；HEAD `6e8abdb` |
| 2 | `git status --short` / `git rev-parse v3.2` / `git merge-base v3.2 HEAD` / `git log --oneline v3.2..HEAD` / `git diff --stat v3.2...HEAD` / `git diff --stat` / `git diff --cached --stat` / `git ls-files --others --exclude-standard` | Base=merge-base=`4f83a0e`；5 commits；44 files +1224/−78；无未暂存/暂存/未跟踪改动（等价于完整 `git diff v3.2...HEAD` 为空工作区差异） |
| 3 | `git diff v3.2...HEAD -- backend/app/services/cluster_authorization.py backend/app/services/interface.py backend/app/services/scope_filters.py backend/pyproject.toml backend/tests/conftest.py` 等逐文件 diff（实现、前端、测试、Contract、计划） | 变更范围与 F029 scope 一致；无 Schema/Migration/端点/权限变更 |
| 4 | `git show --stat 6e8abdb`、`git show 6e8abdb` | 8 files × 1 line（仅 `model:`），无业务/测试/契约夹带 |
| 5 | `git show cd7681a -- …`、`git show de527f9 -- …`、`git show --stat 0e5d8fc f26b641` | `0e5d8fc..cd7681a` 仅测试/文档，生产代码未变；证据日志绑定已提交 HEAD |
| 6 | `git show v3.2:backend/…/test_cluster_authorizations.py`、`git show v3.2:backend/app/services/cluster_authorization.py` | 确认 `_validate_q` 控制字符规则系改前既有实现（F029 仅写入契约），非行为新增 |
| 7 | `PYTHONDONTWRITEBYTECODE=1 python3 scripts/render_project_views.py` | `PROJECT VIEWS VALID` |
| 8 | `PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_project_state.py` | `PROJECT STATE VALID`（结构/Gate/文件/授权元数据/统计） |
| 9 | 自建只读脚本 `python3 /tmp/route_scope_check.py` 遍历 `api_v1_router.routes` | **checked 64 / skipped 20，64 条全部依赖 `get_access_scope`**；豁免项均为 health/auth/users/api-keys/audit/deleted/cluster-authorizations/templates，与设计一致 → 路由覆盖断言非空洞 |
| 10 | `TEST_DATABASE_URL=… /csm_test PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/integration/test_cluster_authorizations.py tests/integration/test_f027_access_scope.py`（真实 PostgreSQL 16.15 @127.0.0.1:55432，输出 `/tmp/f029-review-targeted.log`） | **21 passed in 35.21s**（独立复现 Tester 结论，含 404 顺序、升降级/停用、SQLSTATE、downgrade 对称性、路由覆盖） |
| 11 | `… pytest -q -p no:cacheprovider --collect-only` | **726 tests collected**（+1 module 级 skip），与归档 `721 passed + 6 skipped` 完全吻合 |
| 12 | `cd frontend && npx tsc --noEmit`（输出 `/tmp/f029-review-typecheck.log`） | exit 0，无错误 |
| 13 | `cd frontend && npm run smoke:client`（输出 `/tmp/f029-review-smoke.log`） | **322 passed, 0 failed**（含 F026 409 `already_granted`/`already_revoked` 分类断言） |
| 14 | 每次写入型验证后 `git status --porcelain=v1 --untracked-files=all`；`git check-ignore -v backend/.pytest_cache/CACHEDIR.TAG` | 全程 clean；`.pytest_cache` 为 2026-10-15 既有产物，本次未被写入（`-p no:cacheprovider` 生效），无仓库文件产生/修改 |
| 15 | 只读查询 `csm_test` 库状态（`select version(), alembic_version, count(pg_tables)`） | PostgreSQL 16.15；`alembic_version` 不存在（上次测试会话已清空 schema），确认本次重跑未破坏既有测试数据 |

**验收项 ①–⑩ 映射**

| # | 验收 | 结论 | 证据 |
| --- | --- | --- | --- |
| ① | 未知用户 + 非法 q 返回 404（含撤销 409 关闭并刷新其一） | 满足 | 服务层 404 前置；`test_list_filters_and_invalid_query:381`；F026.md v2 |
| ② | 撤销 409 关闭并刷新 | 满足（无自动化回归） | `confirmRevoke` + Contract D-5；RV-06 |
| ②b | 候选排除覆盖全部有效授权 | 满足 | `loadActiveGrantIds` 分页全量 + 增量加入 |
| ③ | grant 仅唯一冲突映射 409 | 满足 | `diag.constraint_name` 精确匹配；重复授予用例走该分支 |
| ④ | 触发器 SQLSTATE 与 downgrade 对象对称性断言 | 满足 | `23514/23001/23505` + down/up 对称用例（本人复跑） |
| ⑤ | 各域 Contract 含 F027 交叉引用 | 满足（签核记载待补） | 12 份 Contract 追加章节；RV-01 |
| ⑥ | scope 测试使用 `real_scope` marker | 满足 | pyproject marker + conftest + 2 模块 `pytestmark` |
| ⑦ | `resource_predicate` 命名清晰 | 满足 | 重命名且无残留 |
| ⑧ | `normalize(None)` 风险有说明 + 路由覆盖断言通过 | 满足 | docstring + 64/64 路由断言 |
| ⑨ | `project.acceptance` 含 F027 锚点 | 满足（建议改用 TE-4 直链） | `#repair-verification-1`；RV-04 |
| ⑩ | 新增回归测试通过；全量无回归 | 部分满足 | 21 定向复跑通过；全量以归档日志 + 收集数一致性核对；并发缺口 RV-03 |

**裁定**：无 BLOCKER / HIGH / 必须修复 MEDIUM，无未决产品问题；存在明确非阻塞问题与跟进安排 → **APPROVED WITH FOLLOW-UP**。批准仅对候选 HEAD `6e8abdb23ba2399efb6bb0a76eb30b7eaed4d5fc` 与 Base/merge-base `4f83a0eb8fc0c7b0a3ae2db64d3249ca45f159cf` 有效；Merge / DONE 由协调器按 Git Workflow §5 判定（含把 approved HEAD 写入 `git.head_commit`、恢复 `project.acceptance=COMPLETE`）。

GIT: git rev-parse --show-toplevel
GIT: git branch --show-current
GIT: git status --porcelain=v1 --untracked-files=all
GIT: git rev-parse HEAD
GIT: git branch -a
GIT: git status --short
GIT: git rev-parse v3.2
GIT: git merge-base v3.2 HEAD
GIT: git log --oneline v3.2..HEAD
GIT: git diff --stat v3.2...HEAD
GIT: git diff --stat
GIT: git diff --cached --stat
GIT: git ls-files --others --exclude-standard
GIT: git diff v3.2...HEAD -- backend/app/services/cluster_authorization.py backend/app/services/interface.py backend/app/services/scope_filters.py backend/pyproject.toml backend/tests/conftest.py
GIT: git diff v3.2...HEAD -- frontend/src/components/ClusterAuthorizationPanel.tsx
GIT: git diff v3.2...HEAD -- docs/api/F026.md docs/api/F002.md docs/api/F013.md
GIT: git diff v3.2...HEAD -- backend/tests/integration/test_cluster_authorizations.py
GIT: git diff v3.2...HEAD -- backend/tests/integration/test_f027_access_scope.py backend/tests/integration/test_f028_acceptance.py
GIT: git diff v3.2...HEAD -- docs/features/F026/product.md docs/project/backlog.md docs/project/milestones.md
GIT: git diff v3.2...HEAD --stat -- docs/api/
GIT: git diff v3.2...HEAD -- docs/api/F003.md
GIT: git diff v3.2...HEAD -- docs/api/F004.md
GIT: git diff v3.2...HEAD -- docs/api/F007.md
GIT: git diff v3.2...HEAD -- docs/api/F008.md
GIT: git diff v3.2...HEAD -- docs/api/F009.md
GIT: git diff v3.2...HEAD -- docs/api/F010.md
GIT: git diff v3.2...HEAD -- docs/api/F011.md
GIT: git diff v3.2...HEAD -- docs/api/F012.md
GIT: git diff v3.2...HEAD -- docs/api/F014.md
GIT: git diff v3.2...HEAD -- docs/api/F023.md
GIT: git show v3.2:backend/tests/integration/test_cluster_authorizations.py | sed -n 340,385p
GIT: git show v3.2:backend/app/services/cluster_authorization.py | sed -n 88,140p
GIT: git diff v3.2...HEAD -- docs/project/project-plan.yaml | head -160
GIT: git show 6e8abdb --stat
GIT: git show 6e8abdb | head -80
GIT: git show 6e8abdb | sed -n 80,140p
GIT: git show --stat --oneline 0e5d8fc | head -25
GIT: git show --stat --oneline f26b641 | head -25
GIT: git show --stat --oneline cd7681a | head -25
GIT: git show --stat --oneline de527f9 | head -25
GIT: git show cd7681a -- backend/tests/integration/test_cluster_authorizations.py docs/api/F026.md docs/features/F026/product.md
GIT: git show de527f9 -- docs/project/project-plan.yaml docs/features/F029/test-report.md | head -60
GIT: git check-ignore -v backend/.pytest_cache/CACHEDIR.TAG
