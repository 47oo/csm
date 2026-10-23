# F030 Review 跟进收敛 — Test Report

> 本文件同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本与结论。
> 当前只有 TEST DESIGN。**TEST DESIGN READY 仅表示方案可验证，不是测试通过，不批准实现或合并。**

## Test Design（TD-1，2026-10-23，v1）

- **Task**：F030（ENABLER，P2，M21）；分支 `feature/F030-review-followup-closeout`；plan_revision 16；阶段 TEST_DESIGN。
- **Status**：TEST DESIGN READY（Tester，只读分析，未修改任何仓库文件）。
- **依据**：`docs/features/F030/product.md`（P1–P9、§3 边界守卫、§7 N1–N5）；`docs/features/F030/architecture.md` v1（§3–§9、§10–§14）；`docs/api/F026.md` v2（目标 v3）、`docs/api/F027.md` v1；`docs/product/requirements-v3.md` revision 11（§23.2、§31 T85–T99、§32、§35.2/§35.3）；`docs/features/F029/review-report.md`（RV-01…RV-11）；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`。

### TD-1 输入基线

| 项 | 值 | 说明 |
| --- | --- | --- |
| 需求基线 | revision 11 | F030 不新增条款；§23.2/T85–T99 全部 CONFIRMED |
| 分支 / 基线提交 | `feature/F030-review-followup-closeout`；Base=`v3.2`=`70db846`（merge-base 一致）；TD 编写时 HEAD `4335860` | 差异范围 `70db846..候选 HEAD` |
| 层级 | database=false、backend=true、frontend=true、api_required=true | Database NOT_REQUIRED（无 Schema/Migration）；Contract 需落盘 v3 + 12 份增补行 |
| 后端基线 | **721 passed / 6 skipped**（F029 `artifacts/full-pytest.log`，1114.77s）；`--collect-only` = **726 + 1 module skip** | TD 复现收集数一致（726 + module skip） |
| 后端跳过集合基线 | F016 acceptance（module 级 1）、F028 acceptance（4）、migrations V3b superuser（1） | TEST 必须仍为这 6 条，原因集合不变 |
| 前端基线 | `smoke:client` **322 passed / 0 failed**（TD 复现）；`tsc --noEmit`、`vite build` 由 TEST 执行 | — |
| 数据库 | PostgreSQL **16.15**，`csm_test`（容器 `csm-f026-pg`，127.0.0.1:55432），public 表数 0 | fixture 会 `DROP/CREATE public` 后 `alembic upgrade head`；不在未知/生产库执行 |
| 工具链 | Python 3.12.7；SQLAlchemy 2.0.34；psycopg 3.2.13；pytest 7.4.4；Node v22.23.3；PyYAML 6.0.1 | pytest 7.4.4 低于 `pyproject` 的 `>=8`（既有环境事实，F029 同版本）；不据此判缺陷 |
| 复用结论 | F026/F027 A 系列行为不变（P8）、DB-D401–D420 继续有效（无 DB 变更）、F029 TD/TEST 结论仅作回归对照，不复用其 PASS 代替 F030 验收 | — |

### TD-2 验收映射（P1–P9 → 可执行验证项）

统一记法：**层级** = D(文档/差异核对) / S(静态代码核对) / I(真实 PostgreSQL 集成) / F(前端机制级) / P(计划一致性)。
所有项在 TEST 阶段逐条标 PASS / FAIL / BLOCKED / NOT TESTED，并附命令与证据路径（`docs/features/F030/artifacts/`）。

#### P1 — Contract 签核完整（13 份正文）

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P1.1 | D | Contract 落盘 | `docs/api/F026.md` 头部含 `- **覆盖范围 / 对象**` 与 `- **确认来源**` 两行；`签核` 行含 `v3`、`2026-10-23`、`Architect` | 逐文件核对表 + `signoff-check.log` |
| TD2-P1.2 | D | 同上 | 12 份域 Contract **末行**（F027 增补节末）含 `签核：Architect`、`2026-`、`对象：docs/api/<Fxxx>.md`、`覆盖范围`、`确认来源`、`上游依据` 六个 token | 同上（逐文件 grep 记录） |
| TD2-P1.3 | D | 同上 | 版本一致：F026 头部 `版本 v3` == §13 修订记录末行 `v3` == §12 存在 v3 行且日期与 §13 一致。§12 既有 `版本 v1` 按 Issue I-1 口径记为既有滞后，不计 FAIL | `F026.md` 行号引用 |
| TD2-P1.4 | D | 同上 | 12 份文件 `git diff` **删除行数 == 0**（纯追加）；F026.md 删除行仅 `状态/版本/签核` 三行 | `git diff 70db846..HEAD -- docs/api/` 归档 |
| TD2-P1.5 | D | 同上 | 12 份文件修订记录各新增 1 行：单元格数 == 表头单元格数（F002 3 列 / 其余 4 列），且含 `F030` 或 `F029-RV-01`；未改写既有行与表头 | 逐文件核对表（→ Issue I-3） |
| TD2-P1.6 | D | 同上 | 「端点/字段/错误码/权限不变」声明在三处可查：F026 头部签核行、12 份签核行、各增补节既有句；12 份增补行引用的 `docs/api/F026.md` 版本与 F026 实际头部版本一致（v3） | `grep -c` 计数 |
| TD2-P1.7 | D | 同上 | 13 份正文未出现新增端点/字段/错误码/权限项（对 `git diff` 新增行做关键词反查：`POST`/`GET`/`PATCH`/`DELETE` 路径模板、`reason:`、`permission`、`ROLE_PERMISSIONS` 均不得新增） | diff 反查记录 |

#### P2 — 设计输入收敛（BQ18 / BQ19）

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P2.1 | P | 计划落盘 | `python3 scripts/validate_project_state.py` → `PROJECT STATE VALID`；`python3 scripts/render_project_views.py`（**不带 `--write`**）→ `PROJECT VIEWS VALID` | `plan-validate.log` |
| TD2-P2.2 | P | 同上 | 机器可读校验（TD-3 §5 脚本）：`CHG010-BQ18`/`BQ19` 的 `status == CONFIRMED`，且 `source/kind/affects/owner` 与 Base 版本**逐键相同**，`basis` 含必备 token（BQ18：`f026-cluster-authorization.md`、`v1`、`DB-D401`、`D420`、`2026-10-21`、`Architect`、`F026/architecture.md`、`F027/architecture.md`、`F026.md`；BQ19：`F026.md`、`D-7`、`D-8`、`2026-10-23`、`Architect`、`F026/architecture.md`） | `p2-decisions.log` |
| TD2-P2.3 | P | 同上 | `git diff 70db846..HEAD -- docs/product/requirements-v3.md` **为空**（§35.2/§35.3 正文未改写） | diff 输出（空） |
| TD2-P2.4 | P | 同上 | `pending_changes == []`；`project.approval`/`execution.authorization` 未被改写（与 Base 逐键比较）；basis 不虚构签核者（不出现 Backend/Frontend 作为签核者，Database 日期仅 2026-10-21） | 同上 + 正则反查 |

#### P3 — `q` 边界断言（真实 PostgreSQL + 真实 HTTP）

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P3.1 | I | 实现完成 | 已知用户（本用例自建）四条：`q=""`→422、`q="   "`→422、`q="a\x07b"`→422、`q="a\u200bb"`→422、`q`=65 字符→422；每条断言 `error.code == "VALIDATION_ERROR"` 且 `details.fields[0].field == "q"` | `targeted-pytest.log` |
| TD2-P3.2 | I | 同上 | **正向对照**：已知用户 `q = <本用例自建 cluster code 小写>` → 200、`total == 1`、`items[0].cluster.id` 为该 Cluster | 同上 |
| TD2-P3.3 | I | 同上 | 未知用户组：`q=""`→404、`q="a\x07b"`→404（`code == "NOT_FOUND"`，P-1 路径对象优先） | 同上 |
| TD2-P3.4 | I | 同上 | 未声明参数组：未知用户 + `unexpected="x"` → 422 且 `details.fields` 含 `field == "unexpected"`；未知用户 + `unexpected` + `q=""` → 422（仍非 404） | 同上 |
| TD2-P3.5 | I | 同上 | 用例不得依赖其它用例的数据或执行顺序：`make_user` 自建账号、`create_cluster` 自建唯一 code（禁止复用 `f26g` 等既有码） | 代码核对 |
| TD2-P3.6 | I | 终态 | 反空洞由 TD-4.2 的互斥对承担（不在交付分支做变异改动） | 分析记录 |

#### P4 — 并发授予与非唯一完整性错误

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P4.1 | I | 实现完成 | **真并发（HTTP 级，首选）**：两个独立 ADMIN 客户端（`role_client_factory("ADMIN")` ×2，各自独立 `TestClient` + 独立 session → `NullPool` 两条真实连接）、`threading.Barrier(2)`、`join(timeout=30)` 且两线程均 `not is_alive()`、收集结果数 == 2；状态码集合 **== {201, 409}**；409 体 `error.code == "CONFLICT"` 且 `details.reason == "already_granted"`；201 体 `status == "ACTIVE"` | `targeted-pytest.log` |
| TD2-P4.2 | I | 同上 | DB 断言（`auth_session_factory` 真查询）：该 `(user_id, cluster_id)` **ACTIVE 行 == 1**、**总行数 == 1**（无撤销残留）；`audit_logs` 中 `object_type="user_cluster_authorization"` 且 `object_id == 201 返回的 id` 的行 **== 1**、`action == "CREATE"`；DB 中 ACTIVE 行的 id == 201 的 id | 同上 |
| TD2-P4.3 | I | 同上 | **重叠证据**（防顺序执行空洞）：记录每条请求 `time.monotonic()` 起止，断言两区间相交；首次尝试未观测到相交时，允许换新 `(user, cluster)` 重试（最多 3 次），PASS 要求「至少 1 次观测到相交」且「每次尝试均满足状态码集合与 DB 不变量」；报告须写明尝试次数 | 同上（打印尝试记录） |
| TD2-P4.4 | I | 同上 | **回退形态仅在有证据时启用**（架构 R1）：若 HTTP 并发两次以上观测不稳定，改用服务层两连接 + `Barrier`（同 DB 断言 + 「一方成功、一方 `core.errors.Conflict` 且 `details.reason == "already_granted"`」）；**不得**用顺序调用替代；报告须写明采用形态与证据 | 同上 |
| TD2-P4.5 | I | 同上 | **非唯一完整性错误**（服务层，无 monkeypatch）：真实 VIEWER 目标 + 真实 Cluster，`Operator(user_id=uuid.uuid4(), username="f030.ghost", role=ADMIN)`；断言抛 `sqlalchemy.exc.IntegrityError` 且**不是** `core.errors.Conflict`；`exc.orig.sqlstate == "23503"`；`exc.orig.diag.constraint_name == "fk_user_cluster_authorizations_granted_by_users"` | 同上 |
| TD2-P4.6 | I | 同上 | 残留：该 `(user, cluster)` 授权行 **== 0**、`audit_logs` 中 `object_type="user_cluster_authorization"` 行 **== 0**（服务层 `rollback` 生效） | 同上 |
| TD2-P4.7 | I | 同上 | **归因对照（防空洞）**：同一 `(user, cluster)` 改用**真实**操作者再授予 → 成功（行 1 + Audit 1）；证明前一步失败由幽灵 FK 引起，而非其它校验 | 同上 |
| TD2-P4.8 | I | 可选 | 端到端 500 信封（可选）：`TestClient(auth_app, raise_server_exceptions=False)` + **测试专用路由**（F002 先例）调用上述服务 → 500 `{"error":{"code":"INTERNAL_ERROR",...}}`，响应不含堆栈；未执行时在「未验证」注明证据链为「TD2-P4.5 + F002 `test_version_conflict_and_internal_error_envelopes`」 | 可选日志 |

#### P5 — 前端交互（机制级 + 静态核对；浏览器 DOM NOT_REQUIRED）

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P5.1 | F | 实现完成 | 纯逻辑模块 `authorizationCandidates.ts` 存在且**无 React/antd/JSX**（`import type` 之外无 import；文件不含 JSX 标记），可被 Node type stripping 加载 | `smoke-client.log`（导入成功即证） |
| TD2-P5.2 | F | 同上 | `computeGrantCandidates` 不变量：`active` 为 `idle`/`loading` → `{kind:"loading"}` 且**无 clusters**；`active` 为 `error` → `{kind:"error"}`；`clusters` 非 `success` → 不返回候选；仅两者均 `success` 时按 `ids` 过滤；`truncated = active.truncated || clusters.total > clusters.clusters.length`（两条独立断言） | `smoke-client.log`（用例名） |
| TD2-P5.3 | F | 同上 | `canSubmitGrant`：`active` 非 `success`（idle/loading/error 三态各一条）恒 `false`；`success + 已选 + !busy → true`；`busy → false`；`selectedClusterId === "" → false` | 同上 |
| TD2-P5.4 | S | 同上 | **布线（wiring）**：`ClusterAuthorizationPanel.tsx` 实际使用 `computeGrantCandidates` 与 `canSubmitGrant`（import + 使用点各 ≥1）；旧的 `activeGrantIds.has(...)` 内联过滤已移除（命中 0）；错误判据 `clustersState.total > candidates.length + activeGrantIds.size` 已移除（命中 0） | `grep` 记录（`wiring-check.log`） |
| TD2-P5.5 | S | 同上 | 加载失败：存在「重试」入口且绑定重新加载（≥1）；失败分支**不置空集**（不得出现 `setActiveGrantIds(new Set())` 于 catch 中）；加载中呈现 LoadingState 且不渲染可选列表 | `grep` + 代码引用行号 |
| TD2-P5.6 | S | 同上 | 409 分支：`already_granted` 时**不当作成功**（不 `setGrantOpen(false)`、不写成功 notice）、内联呈现错误、并重新加载候选；`already_revoked` 时关闭 + notice + `reloadToken+1`（Contract D-5 不变） | 代码引用行号 + `smoke` 分类断言 |
| TD2-P5.7 | D+S | 同上 | 超大 ACTIVE 授权量**书面结论**存在（架构 §7.2 + DR-F030-07）：保留分页安全上限、`truncated` 显式提示、服务端唯一约束与 409 为最终事实；代码实现 `truncated` 传播 + 提示文案 | 架构引用 + `grep` |
| TD2-P5.8 | F | 同上 | `npx tsc --noEmit` exit 0；`npm run build` 成功；`npm run smoke:client` **322 + 新增（≥4）**，0 failed | `typecheck.log`/`frontend-build.log`/`frontend-smoke.log` |
| TD2-P5.9 | — | — | 真实浏览器 DOM/焦点/窄屏 **NOT_REQUIRED**：理由 = 架构 §7.3 明确排除 + 仓库无 DOM 测试框架（AGENTS §2.6 不引入）；不得声称已完成浏览器验证（F029-RV-06 教训） | 记入「未验证」 |

#### P6 — 注释与 Contract 现状语义

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P6.1 | S | 实现完成 | `backend/app/services/cluster_authorization.py` 中 `list_authorizations` 注释：与事实相反的结论（`existence oracle`）**命中 0**；新注释含 P-1 依据（路径对象优先、`q` 在账号存在后校验、类型化/未声明参数在路由前 422、非信息泄露加固因端点仅 USER_ADMIN） | `grep` + 行号引用 |
| TD2-P6.2 | S | 同上 | 该文件 `git diff` 的 `+`/`-` 行 **全部为注释行**（strip 后以 `#` 或空开头）——证明未改代码语义 | diff 过滤日志 |
| TD2-P6.3 | S+I | 同上 | 注释主张与实测一致：TD2-P3.3（未知用户 + 非法 q → 404）与 TD2-P3.1（已知用户 → 422）同时成立 | 交叉引用 |
| TD2-P6.4 | D | Contract 落盘 | `docs/api/F026.md` §5 含「非唯一完整性错误语义」补记：仅 `uq_…_user_id_cluster_id` 映射 409；其他完整性失败原样上抛 → 500 `INTERNAL_ERROR`，不新增授权行、不写 Audit；**§5 既有 409/422 映射表行未被修改**（diff 中该表无删除/改写行），未新增 error code/reason | diff + 引用 |
| TD2-P6.5 | I | 实现完成 | 上述语义与实现一致：TD2-P4.5（不被映射为 409）+ F002 500 信封用例（既有证据，注明为复用而非新执行） | 交叉引用 |

#### P7 — `real_scope` 默认规则约束

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P7.1 | I | 实现完成 | **legacy canary**（`test_f030_test_harness.py`，本模块**不打** marker）：`get_access_scope in auth_app.dependency_overrides` 且其返回 `AccessScope(unrestricted=True, cluster_ids=frozenset())` | `targeted-pytest.log` |
| TD2-P7.2 | I | 同上 | **marked canary**（`test_cluster_authorizations.py`，已打 marker）：`get_access_scope not in auth_app.dependency_overrides` | 同上 |
| TD2-P7.3 | I | 同上 | **AST 扫描守卫**：扫描 `tests/integration/test_*.py`，凡出现 `AccessScope`/`resolve_access_scope`/`get_access_scope` 的模块必须有模块级 `pytestmark` 或装饰器标记 `real_scope`；`offenders == []`；唯一豁免为守卫自身（`Path(__file__).name`，不得使用通配/名单） | 同上 + 代码引用 |
| TD2-P7.4 | I | 同上 | **反空洞**：`len(scanned) >= 20`（架构下限）且 `{"test_cluster_authorizations.py","test_f027_access_scope.py"} <= marked`；报告须记录实际 `scanned` 数与 `marked` 集合 | 同上（断言/打印） |
| TD2-P7.5 | S | 同上 | `tests/conftest.py` 的 `auth_app` docstring 明确「默认 legacy unrestricted / 真实 scope 必须 `real_scope` / 守卫文件位置」三要素；`backend/pyproject.toml` 的 `real_scope` marker 说明同步为 F030 口径 | `grep` + 行号 |
| TD2-P7.6 | S | 同上 | 生产行为未变：`conftest.py` 的 `auth_app` **运行逻辑**未修改（diff 仅 docstring 行），`pyproject.toml` diff 仅 marker 说明字符串 | diff 过滤 |

#### P8 — 无回归

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P8.1 | I | 实现完成 | 定向套件：`test_cluster_authorizations.py` + `test_f027_access_scope.py` + `test_f030_test_harness.py` 全 PASS；F026 A1–A33 / F027 A1–A23 相关既有用例（21 例基线 + 新增）无 FAIL | `targeted-pytest.log` |
| TD2-P8.2 | I | 同上 | 全量后端：`skipped == 6` 且**跳过原因集合与基线完全一致**（F016 module、F028 ×4、migrations V3b）；`passed == 721 + 新增用例数`，新增用例名须逐一列出并映射 P3/P4/P7（预期下限：`test_cluster_authorizations.py` ≥4 + `test_f030_test_harness.py` = 3，合计 ≥7 → 预期 `passed ≥ 728`）；计数与预期不符必须解释 | `full-pytest.log` |
| TD2-P8.3 | F | 同上 | 前端：`tsc --noEmit` 0 error；`vite build` 成功；`smoke:client` 322 + 新增（≥4）0 failed | 3 份日志 |
| TD2-P8.4 | I | 同上 | 无 Schema/Migration 变更：`git diff --name-only 70db846..HEAD` 中 `backend/alembic/` **为空**；库内 `alembic_version` 仍为 `0015_user_cluster_authorizations`；`user_cluster_authorizations` 的索引/触发器集合不变 | diff + 只读 SQL |
| TD2-P8.5 | I | — | 不产生仓库残留：每次写型验证后 `git status --porcelain=v1 --untracked-files=all` 为空（`-p no:cacheprovider`、`PYTHONDONTWRITEBYTECODE=1`） | 逐次记录 |

#### P9 — 范围不漂移

| ID | 层级 | 前置 | 断言 | 证据 |
| --- | --- | --- | --- | --- |
| TD2-P9.1 | D | 实现完成 | `git diff --name-only 70db846..HEAD` ⊆ 白名单：`docs/api/F026.md`、12 份域 Contract、`docs/project/project-plan.yaml` + 3 份派生视图、`docs/features/F030/*`、`backend/app/services/cluster_authorization.py`（仅注释）、`backend/tests/conftest.py`、`backend/pyproject.toml`、`backend/tests/integration/test_cluster_authorizations.py`、`backend/tests/integration/test_f030_test_harness.py`、`frontend/src/components/authorizationCandidates.ts`、`frontend/src/components/ClusterAuthorizationPanel.tsx`、`frontend/scripts/smoke-client.mjs`、`docs/features/F030/artifacts/*`；任何额外文件须解释 | `scope-check.log` |
| TD2-P9.2 | S | 同上 | 不新增业务规则/授权语义/范围过滤/Audit：`backend/app/{models,schemas,core,api}/` 无 diff；`ROLE_PERMISSIONS`/`Permission` 无 diff；`frontend/src/api/` 无 diff（不新增端点/参数）；面板无新增 API 调用（`listClusterAuthorizations`/`listClusters`/`grantClusterAuthorization` 调用计数不增） | diff + `grep` 计数 |
| TD2-P9.3 | P | 协调器 | `project.acceptance` 只在 F030 验证通过后由协调器恢复 `COMPLETE`；TEST 阶段不得预先置 COMPLETE（TEST 只报告，不改计划） | 计划读取 |

### TD-3 环境、夹具与命令

**环境**

- 后端集成：真实 PostgreSQL 16.15，库 `csm_test`（本地容器 `csm-f026-pg`，`127.0.0.1:55432`）；`TEST_DATABASE_URL` 由本地注入（凭据取自本地未纳入版本库的测试环境文件，**不在报告中记录真实凭据**）；`conftest._require_test_database_url` 强制库名含 `test` 且 ≠ `DATABASE_URL`（DB-D10）。SQLite/Mock 不作为约束/并发证据。
- 每个集成会话由 fixture 重建 `public` 并 `alembic upgrade head`；`auth_session_factory` 走 `committed_engine`（`NullPool`，真提交），测试后 `TRUNCATE`。并发用例因此天然获得**两条独立连接**。
- 前端：Node v22.23.3（type stripping 直接加载 `src/**/*.ts`），`node_modules` 已存在；`smoke:client` 仅替换 `globalThis.fetch`。

**命令（按序执行，均归档到 `docs/features/F030/artifacts/`）**

1. 定向后端（真实 PG，约 40–60s）：
   `cd backend && TEST_DATABASE_URL=<本地 csm_test URL> PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/integration/test_cluster_authorizations.py tests/integration/test_f027_access_scope.py tests/integration/test_f030_test_harness.py > ../docs/features/F030/artifacts/targeted-pytest.log 2>&1`
2. 收集数核对：同上命令加 `--collect-only`（期望 733 collected + 1 module skip）。
3. 全量后端（约 19 分钟）：`cd backend && TEST_DATABASE_URL=… PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider > ../docs/features/F030/artifacts/full-pytest.log 2>&1`
4. 前端：`cd frontend && npx tsc --noEmit`（→ `typecheck.log`）；`npm run build`（→ `frontend-build.log`，写入 `dist/`，须确认 `.gitignore` 覆盖）；`npm run smoke:client`（→ `frontend-smoke.log`）。
5. 计划一致性 + BQ18/BQ19 机器校验（只读）：
   `python3 scripts/validate_project_state.py`；`python3 scripts/render_project_views.py`（**不带 `--write`**）；
   追加只读脚本：用 `yaml.safe_load` 读当前计划，用 `git show 70db846:docs/project/project-plan.yaml` 读 Base，对 `CHG010-BQ18`/`BQ19` 断言 `status=="CONFIRMED"`、`source/kind/affects/owner` 与 Base 逐键相同、`basis` 含 TD2-P2.2 列出的 token；并断言 `pending_changes == []`。
6. 差异与范围核对：`git diff --stat 70db846...<candidate HEAD>`；`git diff --name-only …`；`git diff 70db846...<HEAD> -- docs/api/`（P1.4/P1.5/P1.7）；`git diff … -- backend/app/services/cluster_authorization.py`（P6.2）；`git diff --stat … -- backend/alembic/`（P8.4）；`git status --porcelain=v1 --untracked-files=all`（P8.5）。
7. 只读 DB 核对：`alembic_version`、`pg_tables`/`pg_indexes`/`pg_trigger` 中 F026 对象集合（P8.4）。
8. 静态锚点核对：`grep -c "entity oracle"`/`grep -n "computeGrantCandidates|canSubmitGrant|activeGrantIds.has|clustersState.total > candidates.length"`（P5/P6）。

**夹具与数据纪律**

- 所有用例自建数据（`make_user` / `create_cluster` 唯一 code），禁止复用其它用例的 Cluster code 或依赖执行顺序（F028-R2 教训）。
- 并发/真提交用例必须使用 `committed_engine` 关联的 `auth_session_factory`；不使用 `db_session`（外层事务 + savepoint）做并发证据。
- 线程用例必须 `join(timeout=…)` 并断言线程已结束，避免挂起；数据库断言为主判据。

### TD-4 反空洞与边界设计

**4.1 P1/P2（文档与计划）**：不靠「文件存在」判定。①12 份文件用「删除行 == 0」证明纯追加；②F026.md 删除行限定三行；③修订记录行做列数一致性校验；④计划侧用「与 Base 逐键比较 source/kind/affects/owner + basis token 集合」防止只改 `status` 不写依据；⑤`requirements-v3.md` 用空 diff 证明需求正文未改写。

**4.2 P3（`q` 边界）**：三组互斥——
- 「已知用户 `q` 合法 → 200」与「已知用户 `q` 空/控制字符/超长 → 422」构成第一对：移除 `_validate_q` 时后者变 200 → FAIL；对所有 `q` 一律 422 时前者变 422 → FAIL。
- 「未知用户 + `q=""` → 404」与「已知用户 + `q=""` → 422」构成第二对：调换「路径 404 / 语义 422」顺序时前者变 422 → FAIL。
- 「未知用户 + 未声明参数 → 422」：移除 `_reject_unknown_query` 时变 404 → FAIL。
不需在交付分支做变异改动。

**4.3 P4（并发 / 完整性）**
- 顺序执行空洞：仅断言 `{201,409}` 无法区分「真并发」与「先 201 后 409（预检/唯一索引均可）」。**对策**：`Barrier(2)` + 线程存活断言 + **请求区间相交断言**（TD2-P4.3），以及 DB 端「ACTIVE=1 / 总行数=1 / Audit=1」。
- 路径空洞：实现**没有**既有行预检，重复授予恒经 `IntegrityError` → 无法用「异常类型」区分并发与否（已在只读核对中确认），因此**不把 `__cause__` 当作并发证据**，只把 `sqlstate/constraint_name` 用作用例 P4.5 的「未被映射为 409」证据。
- 归因空洞：P4.7 用同一 `(user, cluster)` 的真实操作者授予成功作对照，排除「失败其实来自其它校验」。
- 迁移/证据空洞：不 mock 生产函数（DR-F030-04）；FK 非 DEFERRABLE，`flush()` 即报 23503，可重复。
- 回退纪律：只有在**观测到** HTTP 并发不稳定（≥2 次）时才退回服务层两连接，并在报告写明；不得凭偏好降级为顺序调用（Product N3）。

**4.4 P5（前端）**：模块不变量逐条对应架构 §7.2 的每条规则（1 条规则 ≥1 断言），直接断言而不做变异；**wiring 检查**（TD2-P5.4）防止「模块测通、面板未用」的空洞；旧判据/旧内联过滤必须「命中 0」；浏览器行为明确 NOT_REQUIRED，避免夸大覆盖。

**4.5 P6/P7**：注释以「与事实相反的结论命中 0」+「diff 仅注释」+「主张与 P3 实测互证」三重约束；`real_scope` 用**双向 canary**（unmarked 有 override / marked 无 override）+ AST offenders 为空 + 扫描数与被标记集合反空洞；守卫唯一豁免仅自身文件名，禁止通用名单。

**4.6 P8/P9**：计数不用「看起来差不多」——收集数、passed=721+新增、skipped 原因集合、前端新增用例名均须逐条列出；范围用文件白名单 + 目录级空 diff（`models/schemas/core/api`、`alembic/`、`frontend/src/api/`）+ `ROLE_PERMISSIONS`/`Permission` 无 diff。

### TD-5 未验证项（计划阶段声明；TEST 阶段按实际执行结果更新）

| 项 | 原因 | 处理 |
| --- | --- | --- |
| 真实浏览器 DOM / 焦点 / 窄屏 / 键盘可达性 | 架构 §7.3 明确不在范围；仓库无 DOM 测试框架（AGENTS §2.6） | P5 记「机制级 + 静态核对」；不得声称完成浏览器验证 |
| ACTIVE 授权 > 2000 条的真实加载（`truncated` 真机路径） | 需构造超量数据与真实前端；成本与收益不匹配 | 书面结论 + 机制断言（`truncated` 传播）；真实超量场景 NOT TESTED |
| 并发压力/持续竞态（>2 连接、重复多轮） | 仓库无压力测试设施；F030 只需 201+409 的确定性证据 | 单次真并发（可重试 ≤3 次）为证；压力 NOT TESTED |
| 全量 Compose 成功启动 | 沿用 F029 已记录的环境限制（镜像源/bootstrap 凭据） | NOT TESTED，不写成成功 |
| 端到端 500 信封（P4.8） | 可选；服务层 + F002 信封已构成证据链 | 未执行则记 NOT TESTED + 证据链说明 |
| 生产库/未知库行为 | 安全约束（DB-D10） | 不执行 |
| Windows 路径语义（`auth_app` 路径归一） | 当前环境为 Linux | 不执行 |

**Status（TD-1）：TEST DESIGN READY**

---

## Test Execution（TEST-1，2026-10-23，v1）

### TE-1 Task / Status / Basis

- **Task**：F030（ENABLER，P2，M21）TEST 模式独立验证；分支 `feature/F030-review-followup-closeout`；plan_revision 16；阶段 TEST。
- **Status**：`READY FOR REVIEW`（见 TE-9）。
- **Basis**：`docs/product/requirements-v3.md` revision 11（§23.2、§31 T85–T99、§32、§35.2/§35.3）；`docs/features/F030/product.md`（P1–P9）；`docs/features/F030/architecture.md` v1 + §16 最终设计定稿（READY FOR IMPLEMENTATION）；本文件 TD-1；`docs/features/F030/implementation.md`；`docs/api/F026.md` v3（Architect 2026-10-23）+ 12 份域 Contract 增补节 v1 + `docs/api/F027.md` v1；`docs/database/f026-cluster-authorization.md` v1（DB-D401–D420）；`docs/features/F029/review-report.md`（RV-01…RV-11）；`docs/project/implementation-rules.md`；`.pi/skills/data-integrity/SKILL.md`。

### TE-2 输入与范围（自核）

| 项 | 值 | 核对方式 |
| --- | --- | --- |
| 候选 HEAD | `56cc6ac`（`feat(F030): implement contract and interaction follow-ups`） | `git rev-parse --short HEAD`；工作区 clean |
| Base | `70db846`（`v3.2`）= `git merge-base v3.2 HEAD` | 与 TD-1 记录的 Base 一致 |
| 差异范围 | `70db846..56cc6ac`，6 commits，29 files，+1744/−86 | `git log/diff --stat` → `artifacts/scope-check.log` |
| 层级 | database=false、backend=true、frontend=true、api_required=true；`implementation.database=NOT_REQUIRED` | 计划读取核对，一致 |
| Database Gate | NOT_REQUIRED（`backend/alembic/`、`backend/app/models`、`schemas`、`core`、`api` 均空 diff） | `artifacts/scope-check.log` |
| 前序 Gate | Product / Architecture（§16 定稿）/ Test Design TD-1 / Contract（F026 v3 + 12 份）/ Backend+Frontend 实现 | 正文核对 + `implementation.md` |

### TE-3 Environment

| 项 | 值 |
| --- | --- |
| 数据库 | PostgreSQL **16.15**（容器 `csm-f026-pg`，`localhost:55432`），库 `csm_test`；凭据未写入本报告与任何日志（`artifacts/*.log` 全文 grep 凭据命中 0） |
| 会话重建 | fixture 每会话 `DROP/CREATE public` + `alembic upgrade head`；`auth_session_factory` 走 `committed_engine`（`NullPool`，真提交） |
| Python / 库 | Python 3.12.7；pytest 7.4.4；SQLAlchemy 2.0.34；psycopg 3.2.13；PyYAML 6.0.1 |
| 前端 | Node v22.23.3 / npm 10.9.9；`node_modules` 就绪 |
| 执行纪律 | 后端一律 `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`；未在未知库/生产库执行；SQLite/Mock 未用作约束或并发证据 |
| 环境日志 | `docs/features/F030/artifacts/environment.log` |

### TE-4 命令与结果

| # | 命令 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | `pytest -q -s -p no:cacheprovider tests/integration/test_cluster_authorizations.py tests/integration/test_f027_access_scope.py tests/integration/test_f030_test_harness.py`（真实 PG） | **28 passed**，42.12s，0 failed | `artifacts/targeted-pytest.log` |
| 2 | 同上 `--collect-only` | 定向 28 collected；全量 **733 collected + 1 module skip（F016）** | `artifacts/collect.log` |
| 3 | `pytest -q -p no:cacheprovider`（全量） | **728 passed / 6 skipped**，1014.14s | `artifacts/full-pytest.log` |
| 4 | `npx tsc --noEmit` | exit 0，0 error | `artifacts/typecheck.log` |
| 5 | `npm run build`（tsc + vite build） | exit 0；3214 modules；仅既有 chunk >500 kB 告警 | `artifacts/frontend-build.log` |
| 6 | `npm run smoke:client` | **328 passed / 0 failed** | `artifacts/frontend-smoke.log` |
| 7 | `python3 scripts/validate_project_state.py` / `render_project_views.py`（不带 `--write`） | `PROJECT STATE VALID` / `PROJECT VIEWS VALID`，exit 0 | `artifacts/plan-validate.log` |
| 8 | BQ18/BQ19 机器校验（`yaml.safe_load` 现计划 vs `git show 70db846:…`）+ requirements 空 diff | **PASS** | `artifacts/p2-decisions.log` |
| 9 | 13 份 Contract 签核结构核对（token / 版本一致 / 修订记录列数 / 尾部位置 / 无新增端点·reason·权限） | **PASS** | `artifacts/signoff-check.log` |
| 10 | 纯追加性核对（`git diff` 增删行） | 12 份删除行 = 0；F026 删除 4 行（见 TE-5 口径） | `artifacts/append-only-check.log` |
| 11 | 范围白名单 + 目录级空 diff + 注释性 diff + API 调用计数 | **PASS** | `artifacts/scope-check.log` |
| 12 | 静态 wiring / 注释 / marker 核对 | **PASS** | `artifacts/wiring-check.log`、`artifacts/p3-p6-static.log` |
| 13 | `real_scope` 守卫扫描清单（read-only 复现） | `scanned=53`、`marked={test_cluster_authorizations.py, test_f027_access_scope.py}`、`offenders=[]` | `artifacts/p7-guard-scan.log` |
| 14 | 新增 7 例单独运行（`-k` 排除基线 21 例），验证不依赖其它用例/顺序 | **7 passed**，6.21s，`attempt 1: overlap=True` | `artifacts/independence.log` |
| 15 | 只读 DB / Migration 核对 | `alembic heads` 单 head = `0015_user_cluster_authorizations`；`backend/alembic/` 空 diff；会话结束 fixture 清空 public（与 F029 记录一致，表数 0） | `artifacts/db-schema-check.log` |
| 16 | 每次写型验证后 `git status --porcelain=v1 --untracked-files=all` | 仅本报告修改为跟踪变更；`artifacts/*.log` 命中 `.gitignore:124 *.log`（见 TE-8 交付注意事项） | `artifacts/scope-check.log` 段末 |

### TE-5 TD-1 待澄清项的口径裁定（Architect I-1 / I-3）

TD-1 引用了未定义的「Issue I-1 / I-3」，且 TD2-P3.1 文案计数有误。本 TEST 阶段按下列口径判定，口径一律以**可机械核验的文本事实**为准，不因文案瑕疵判实现 FAIL：

| TD 项 | 原 TD 文案 | 本报告口径 | 实际观测 |
| --- | --- | --- | --- |
| TD2-P1.3 | 「§12 既有 `版本 v1` 按 Issue I-1 口径记为既有滞后，不计 FAIL」（I-1 未定义） | 判据 = ①头部 `版本：v3` ②§13 存在且仅 1 行 `v3` 修订记录 ③§12 存在 `v3（2026-10-23，Architect）` 行 ④§12 与 §13 的 v3 日期一致 ⑤§12 首条 bullet 已改为 v1/v2/v3 历史记载（I-2 已修）。历史版本行不得被改写为「仅 v3」 | ①–⑤ 全部成立：§12 =「状态 READY；签核者 Architect；v1 2026-10-21 / v2 2026-10-22 / v3 2026-10-23」+ v3 明细行；§13 = v1/v2/v3 三行，v3 日期 2026-10-23。**PASS** |
| TD2-P1.5 | 「单元格数 == 表头单元格数（F002 3 列 / 其余 4 列）」并指向未定义的 Issue I-3 | 判据 = 逐文件读「修订记录」表头实际列数，再核对该文件新增的 F030 行单元格数与之相等（不预设列数）；行内须含 `F030` 或 `F029-RV-01`；既有行与表头不得改写（12 份删除行 = 0） | 表头实测 F002 = 3 列，F003/F004/F007–F014/F023 = 4 列；12 份 F030 行单元格数分别 = 3 / 4，与各自表头一致；均含 `F030 P1`+`F029-RV-01`。**PASS** |
| TD2-P3.1 | 「已知用户（本用例自建）**四条**：`q=""`→422、`q="   "`→422、`q="a\x07b"`→422、`q="a\u200bb"`→422、`q`=65 字符→422」 | 「四条」为 TD 文案笔误，实际列出 **5** 条用例；判据取 5 条全测（承架构 §5 的 5 行 422 场景表）。任一缺失即 FAIL | 5 条全部断言 422 + `code=VALIDATION_ERROR` + `details.fields == [{field:"q"}]`。**PASS（5 条）** |
| TD2-P3.2 | 「正向对照：`q = <本用例自建 cluster code 小写>`」（架构 §5 字面为 `q="f26g"`） | 采用 TD-1 的细化口径（自建码）而非架构 §5 的示例字面：跨用例共享固定码会引入数据耦合（F028-R2 教训）；`q` 只与**本用例**该账号的授权集合求交，故必须用本用例自建码才能稳定得到 `total==1` | 用例自建 `F30Q1`，`q="f30q1"` → 200、`total==1`、`items[0].cluster.id` = 该 Cluster。**PASS** |

补充口径（同属「非内容变化」的 diff 解释）：

- **TD2-P1.4**：12 份域 Contract 删除行 = 0（纯追加）。F026.md 删除 **4** 行，其中 3 行为获授权的签核记载改写（`- **版本**：v2`、`- **签核**：…v2…`、§12 `版本 v1；日期 2026-10-21` 行），第 4 行是 `| v2 | 2026-10-22 | …` 修订记录行：Base 文件该行**无行尾换行**，追加 v3 行时同一被「重写」为逐字节相同文本（base 158 B vs head 159 B，diff 仅 `\ No newline at end of file` 标记）。→ 判 **PASS**（无内容变化），记 NOTE 供 Review 复核。
- **P1.7 反查命中说明**：新增行中 `CONFLICT{reason:"already_granted"}` 与 `INTERNAL_ERROR` 各 1 次，均为对**既有** code 的复述（Base F026 已分别出现 7 次 / 1 次），`http_method_path` 与 `permission` 命中 0 → 无新增端点/字段/错误码/权限。

### TE-6 验收映射（P1–P9 / TD2-P1.1–P9.3 逐项）

图例：**PASS** = 已实际执行并核对输出；FAIL = 不满足；BLOCKED = 缺输入/环境；NOT TESTED / NOT_REQUIRED = 未执行或按设计排除。

#### P1 — Contract 签核完整

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P1.1 | **PASS** | F026 头部含 `覆盖范围 / 对象`、`确认来源`、`版本：v3`，签核行含 Architect/v3/2026-10-23 |
| TD2-P1.2 | **PASS** | 12/12 份增补节末行含 6 个 token（`签核：Architect`/`2026-`/``对象：`docs/api/<Fxxx>.md` ``/`覆盖范围`/`确认来源`/`上游依据`）；均位于「F027 范围语义」节末且其后无正文 |
| TD2-P1.3 | **PASS** | 口径见 TE-5；§12/§13 版本与日期一致 |
| TD2-P1.4 | **PASS** | 12 份删除行 0；F026 删除 4 行且第 4 行为 EOF 换行归一（逐字节比对，TE-5） |
| TD2-P1.5 | **PASS** | 列数实测：F002 3 列 / 其余 4 列；各新增 1 行且列数相符；含 `F030`+`F029-RV-01`；既有行未被改写 |
| TD2-P1.6 | **PASS** | 「端点/字段/错误码/权限/错误顺序不变」在 F026 头部签核行与 12 份签核行（`保持不变`）均可查；12 份引用的 `` `docs/api/F026.md` v3 `` 与 F026 头部实际 v3 一致 |
| TD2-P1.7 | **PASS** | 新增行反查：HTTP 方法+路径模板 0、`ROLE_PERMISSIONS`/`permission:` 0；`already_granted`/`INTERNAL_ERROR` 为既有 code 复述（TE-5） |

#### P2 — 设计输入收敛（BQ18/BQ19）

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P2.1 | **PASS** | `PROJECT STATE VALID` / `PROJECT VIEWS VALID`（`artifacts/plan-validate.log`） |
| TD2-P2.2 | **PASS** | BQ18/BQ19 `status: OPEN → CONFIRMED`；`source/kind/affects/owner` 与 Base 逐键相同；basis token 全命中（BQ18 9 个、BQ19 6 个，missing=[]）；`decisions_required` 条数 38→38（未增删条目） |
| TD2-P2.3 | **PASS** | `git diff 70db846...56cc6ac -- docs/product/requirements-v3.md` 为空；§35.2 表中 BQ18/BQ19 仍为 `DESIGN_INPUT` 原句（619–625 行） |
| TD2-P2.4 | **PASS** | `pending_changes: []`；`project.approval` 与 Base 逐键相同；basis 无「Backend/Frontend 签核」「Database 2026-10-23」等虚构 token；`project.acceptance.status` 仍为 `PENDING`（未由 TEST 提前置 COMPLETE） |

#### P3 — `q` 边界断言（真实 PostgreSQL + 真实 HTTP）

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P3.1 | **PASS** | 5 条（`""` / `"   "` / `a\x07b` / `a\u200bb` / 65 字符）全部 422 + `VALIDATION_ERROR` + `fields == [q]`（`targeted-pytest.log`，`test_list_q_boundary_validation`） |
| TD2-P3.2 | **PASS** | 自建 `F30Q1` → `q="f30q1"` = 200、`total==1`、`items[0].cluster.id` 相符（口径见 TE-5） |
| TD2-P3.3 | **PASS** | 未知用户 + `q=""` / `a\x07b` → 404 `NOT_FOUND`（P-1 路径对象优先） |
| TD2-P3.4 | **PASS** | 未知用户 + `unexpected="x"` → 422 且 `fields == [unexpected]`；`unexpected`+`q=""` → 422（仍非 404） |
| TD2-P3.5 | **PASS** | 代码核对：`make_user` 自建账号、`create_cluster("F30Q1")` 自建码，无 `f26g` 等跨用例复用；**另以 `-k` 单独运行 7 例（不含基线 21 例）仍 7 passed** 证明无顺序依赖（`artifacts/independence.log`） |
| TD2-P3.6 | **PASS** | 反空洞由互斥对承担：`q="f30q1"`=200 与 5 条 422 互斥（移除 `_validate_q` → 后者变 200）；未知用户 404 与已知用户 422 互斥（调换路径/语义顺序 → 未知组变 422）。静态核对 `_get_user_or_404`（136 行）先于 `_validate_q`（143 行）。未在交付分支做变异改动（TD-4.2） |

#### P4 — 并发授予与非唯一完整性错误

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P4.1 | **PASS** | **采用形态 = HTTP 级真并发**（架构 §6.1）：两个独立登录 ADMIN `TestClient`（`f030.race.admin.a/b`）+ `Barrier(2, timeout=30)` + 双线程 `join(30)` 且断言 `not is_alive()`；结果数 2；状态码集合 `== {201, 409}`；409 `code=CONFLICT`/`details.reason=already_granted`；201 `status=ACTIVE`（`targeted-pytest.log`） |
| TD2-P4.2 | **PASS** | DB 断言（`auth_session_factory` 真查询，`committed_engine`/`NullPool`）：`(user, cluster)` 总行数 1、ACTIVE 1、`active[0].id == 201 返回 id`；`audit_logs` 该 object_id 行 1 且 `action=CREATE` |
| TD2-P4.3 | **PASS** | 请求区间相交断言存在且**实测命中**：正式定向运行 `attempt 1: statuses=[409, 201] overlap=True spans=[(702801.1568,702801.1987),(702801.1561,702801.2131)]`；独立复跑（`independence.log`）同样 `attempt 1 … overlap=True` → **尝试次数 = 1**（未触发 ≤3 次重试），每次尝试均断言状态码集合与 DB 不变量 |
| TD2-P4.4 | **PASS** | 未启用回退形态：HTTP 并发在两次独立运行中均 `attempt 1` 观测到相交，未出现不稳定；未使用顺序调用替代（Product N3） |
| TD2-P4.5 | **PASS** | 服务层、无 monkeypatch：幽灵 `Operator(user_id=uuid4, username="f030.ghost", role=ADMIN)` → 抛 `sqlalchemy.exc.IntegrityError` 且 `not isinstance(..., Conflict)`；`exc.orig.sqlstate == "23503"`；`constraint_name == fk_user_cluster_authorizations_granted_by_users` |
| TD2-P4.6 | **PASS** | 残留：该 `(user, cluster)` 行 0、`audit_logs` 中 `object_type="user_cluster_authorization"` 行 0（服务层 rollback 生效） |
| TD2-P4.7 | **PASS** | 归因对照：同一 `(user, cluster)` 改用真实操作者 → 成功（行 1、`granted_by == admin.id`、`revoked_at IS NULL`、Audit `CREATE` 1 条） |
| TD2-P4.8 | **NOT TESTED（可选）** | 端到端 500 信封未执行（TD-1 标为可选，且需新增测试专用路由）。证据链 = TD2-P4.5（服务层不被映射为 409）+ F002 `test_version_conflict_and_internal_error_envelopes`（本次全量套件内实际执行并通过，返回 `INTERNAL_ERROR` 信封且不含堆栈）。未写成「已完成端到端验证」 |

#### P5 — 前端交互（机制级 + 静态核对）

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P5.1 | **PASS** | `frontend/src/components/authorizationCandidates.ts` 仅 1 处 `import type { Cluster }`，无 React/antd/JSX；`smoke-client.mjs` 通过 Node type stripping 直接 import 成功（`frontend-smoke.log` 6 条 F030 断言全 PASS 即证） |
| TD2-P5.2 | **PASS** | smoke 断言：`idle`/`loading` → `{kind:"loading"}` 且 `"clusters" in result === false`；`error` → `{kind:"error"}` 保留文案且无 clusters；`clusters` 非 success → `loading`/`error`；仅双 success 过滤（`c1,c3`，排除 `c2`）；`truncated` 两路独立（active 路 `2000/2001`、clusters 路 `total=50` vs 1 项）+ 双 false 才 false |
| TD2-P5.3 | **PASS** | `canSubmitGrant`：`active` 三态（idle/loading/error）恒 false；`success+已选+!busy` → true；`busy` → false；`""` → false；另含候选成员校验（已授权 `c2` / 搜索收窄后旧选中 `c1` → false）与候选非 success → false |
| TD2-P5.4 | **PASS** | 布线：import（14–16 行）+ 使用点（191/196/498 行）；`activeGrantIds.has` 命中 0；旧判据 `clustersState.total > candidates.length` 命中 0；旧符号 `activeGrantIds` 全文件命中 0（`wiring-check.log`） |
| TD2-P5.5 | **PASS** | 加载失败分支 = `activeGrants.kind==="error"` 的 `ErrorState` + 「重试」按钮（`setGrantReloadToken`），集群列表失败另有独立「重试」（`setClustersReloadToken`）；`setActiveGrantIds` 命中 0（不存在置空集）；加载中渲染 `LoadingState`（文案「加载完成前不可提交」）且**不渲染** `Select`/`option`（候选仅在 `candidates.kind==="success"` 分支呈现） |
| TD2-P5.6 | **PASS** | `already_granted`：`setGrantError(...)` 内联呈现 + `setGrantReloadToken+1` 重载候选 + 清空选择，**未** `setGrantOpen(false)`、未写成功 notice（成功分支在 try 内且仅 201 路径执行）；`already_revoked`：关闭 `revokeTarget` + notice + `reloadToken+1`（Contract D-5 不变） |
| TD2-P5.7 | **PASS** | 书面结论存在于架构 §7.2 与 DR-F030-07；代码 `truncated` 传播（`loadActiveGrants` → `ids.size < total`）+ `InfoState` 显式提示文案（443 行「有效授权数量为 N（已加载 M）…409 already_granted 拒绝」）+ 集群列表截断提示（498 行） |
| TD2-P5.8 | **PASS** | `tsc --noEmit` exit 0；`npm run build` exit 0；`smoke:client` **328 passed / 0 failed** = 322 基线 + 6 新增（新增用例名见 TE-7） |
| TD2-P5.9 | **NOT_REQUIRED** | 真实浏览器 DOM/焦点/窄屏：架构 §7.3 明确排除，仓库无 DOM 测试框架（AGENTS §2.6 不引入）。本报告只声明「机制级 + 静态核对」，不声称浏览器验证 |

#### P6 — 注释与 Contract 现状语义

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P6.1 | **PASS** | `existence oracle` 命中 0；新注释（130–135 行）含 4 要素：路径对象优先 404、`q` 在账号存在后校验、类型化/未声明参数在路由前 422、非信息泄露加固（仅 USER_ADMIN） |
| TD2-P6.2 | **PASS** | `backend/app` 全目录 diff 的非注释变更行 = 0（过滤 `^[+-]\s*#` 后为空）；`backend/app` 仅 `cluster_authorization.py` 一个文件变更 |
| TD2-P6.3 | **PASS** | 注释主张与实测互证：未知用户 + 非法 `q` → 404（TD2-P3.3）与已知用户 → 422（TD2-P3.1）同时成立 |
| TD2-P6.4 | **PASS** | F026 §5 含「非唯一完整性错误语义（v3 补记…）」段：仅 `uq_…_user_id_cluster_id` → 409；其他完整性失败原样上抛 → 500 `INTERNAL_ERROR`、不新增行/不写 Audit；**§5 既有错误映射表 diff 无增删改行**；未新增 error code/reason（TE-5 反查） |
| TD2-P6.5 | **PASS** | 语义与实现一致：TD2-P4.5（服务层不被映射为 409）+ F002 500 信封用例（本次全量实际执行并通过）。端到端 grant→500 未串联（见 TD2-P4.8 NOT TESTED） |

#### P7 — `real_scope` 默认规则约束

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P7.1 | **PASS** | `test_unmarked_module_gets_legacy_scope`：`get_access_scope in auth_app.dependency_overrides` 且返回 `AccessScope(unrestricted=True, cluster_ids=frozenset())`（守卫模块自身未打 marker） |
| TD2-P7.2 | **PASS** | `test_marked_module_has_no_legacy_scope_override`：`get_access_scope not in auth_app.dependency_overrides` |
| TD2-P7.3 | **PASS** | AST 扫描 `tests/integration/test_*.py`：`offenders == []`；`_scope_symbols_used` 走 `Name`/`Attribute`/`Import`/`ImportFrom`，不匹配注释与 docstring；唯一豁免 `Path(__file__).name`（`test_f030_test_harness.py`），无通配/名单（代码核对 30–63 行） |
| TD2-P7.4 | **PASS** | 反空洞：`len(scanned) == 53 >= 20`；`marked == {test_cluster_authorizations.py, test_f027_access_scope.py}` ⊇ KNOWN_MARKED（`artifacts/p7-guard-scan.log`） |
| TD2-P7.5 | **PASS** | `conftest.py::auth_app` docstring 三要素齐备（默认 legacy unrestricted / 真实 scope 必须 `pytestmark = pytest.mark.real_scope` / 守卫文件路径，194–201 行）；`pyproject.toml` `real_scope` marker 说明同步为 F030 §9.1 口径（41 行） |
| TD2-P7.6 | **PASS** | `conftest.py` diff 全在 docstring 内（运行逻辑行未变）；`pyproject.toml` diff 仅 marker 说明字符串一行 |

#### P8 — 无回归

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P8.1 | **PASS** | 定向三文件 **28 passed / 0 failed**（基线 21 + 新增 7）；F026 A1–A33 / F027 A1–A23 相关既有用例无 FAIL |
| TD2-P8.2 | **PASS** | 全量 **728 passed / 6 skipped**（1014.14s）；`skipped` 原因集合与基线完全一致：F016 acceptance module（1）、F028 acceptance ×4（`F016_ACCEPTANCE=1` 未启用）、migrations V3b superuser（1）；`passed = 721 + 7`，新增 7 例逐一列出（TE-7）；收集数 733 + 1 module skip = 726 + 7 + 1，与 F029 基线一致 |
| TD2-P8.3 | **PASS** | 前端三项见 TD2-P5.8；`smoke` 328 = 322 + 6 |
| TD2-P8.4 | **PASS** | `backend/alembic/` 空 diff；`alembic heads` 单 head `0015_user_cluster_authorizations`（无 0016）；F026 脚本对象断言（`trg_user_cluster_authorizations_immutable`、`trg_user_cluster_authorizations_no_delete`、`uq_user_cluster_authorizations_user_id_cluster_id`，594–615 行）在本次定向运行中实际执行并通过（含 down/up 对称）。**口径**：会话结束后 fixture 清空 `public`（表数 0），故「库内 alembic_version」无法在会话外直接读取；以单 head + 空 diff + 已执行的 0015 对象断言三段证据替代，未据此声称实际读到了 `alembic_version` 行 |
| TD2-P8.5 | **PASS** | 后端全程 `-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`；每次写型验证后 `git status --porcelain=v1 --untracked-files=all` 无跟踪文件残留（唯一跟踪变更为本报告）；`frontend/dist` 由 `.gitignore:2` 覆盖；`artifacts/*.log` 命中 `.gitignore:124 *.log`（TE-8） |

#### P9 — 范围不漂移

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD2-P9.1 | **PASS** | 29 个变更文件全部落在 TD-2 P9.1 白名单内（含 3 份派生视图 `backlog/dependency-map/milestones` 与 `project-plan.yaml`）；无白名单外文件 |
| TD2-P9.2 | **PASS** | `backend/app/{models,schemas,core,api}`、`frontend/src/api`、`backend/app/services/audit.py`、`docs/api/{F015,F017,F027}`、`docs/product`、`docs/database` 均空 diff；`permissions.py` 空 diff（`ROLE_PERMISSIONS`/`Permission` 未变）；面板 4 个 API 调用计数与 Base 逐项相同（`listClusterAuthorizations` 3=3、`listClusters` 2=2、`grantClusterAuthorization` 2=2、`revokeClusterAuthorization` 2=2）；`activeGrantIds.has`/旧截断判据命中 0 |
| TD2-P9.3 | **PASS** | 计划 `project.acceptance.status = PENDING`（`pending_reason` 保留）；TEST 未修改计划或任何业务/Contract 文件 |

### TE-7 新增用例与基线对照

后端新增 7 例（`passed 721 → 728`，`collected 726 → 733`）：

| # | 用例 | 覆盖 |
| --- | --- | --- |
| 1 | `test_cluster_authorizations.py::test_list_q_boundary_validation` | P3.1–P3.6 |
| 2 | `test_cluster_authorizations.py::test_concurrent_grant_two_connections_single_winner` | P4.1–P4.4 |
| 3 | `test_cluster_authorizations.py::test_grant_non_unique_integrity_error_is_not_mapped_to_409` | P4.5–P4.7 |
| 4 | `test_cluster_authorizations.py::test_marked_module_has_no_legacy_scope_override` | P7.2 |
| 5 | `test_f030_test_harness.py::test_unmarked_module_gets_legacy_scope` | P7.1 |
| 6 | `test_f030_test_harness.py::test_real_scope_usage_requires_marker` | P7.3 |
| 7 | `test_f030_test_harness.py::test_scope_scan_is_not_vacuous` | P7.4 |

前端新增 6 条 smoke 断言（`322 → 328`）：`computeGrantCandidates` idle/loading、`active error`、双 success 过滤 + `truncated` 双路传播、`clusterListTruncated`、`canSubmitGrant` 非 success 三态、`canSubmitGrant` success/busy/空选/旧选中/候选收窄。

### TE-8 数据完整性对应表（引用 implementation-rules / data-integrity Skill）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| requirements rev11 §23.2 有效授权唯一 | `POST /users/{id}/cluster-authorizations` | 部分唯一索引 `uq_user_cluster_authorizations_user_id_cluster_id`（0015，**本次无变更**） | 捕获 `IntegrityError`，仅该约束 → 409 `already_granted` | **真并发**：两独立连接 + Barrier，恰一方 201、另一方 409；ACTIVE=1/总行=1/Audit=1 | `targeted-pytest.log`（attempt 1 overlap=True）；`independence.log` 复现 |
| §23.2 撤销保留历史、不物理删除 | 撤销/生命周期 | 成对 CHECK + 单向 UPDATE/DELETE 触发器（F029 已断言 23514/23001） | 条件 UPDATE，`rowcount==0 → 409 already_revoked` | 本次未改；沿用 F026 既有用例 | 定向套件 28 passed 含 `test_soft_deleted_cluster_history_and_restore`、downgrade 对称性用例 |
| F026 §5 v3 非唯一完整性错误语义（原样上抛 → 500，无行/Audit 残留） | 授予端点（校验后兜底） | FK RESTRICT `fk_u…_granted_by_users`（无 Schema 变化） | `except` 仅在唯一索引名精确匹配时映射 409 | 真实 FK 违约（幽灵操作者），`23503` 精确断言 | `test_grant_non_unique_integrity_error_is_not_mapped_to_409`：异常类型 + SQLSTATE + 约束名 + 行 0 + Audit 0 + 真实操作者归因对照成功 |
| §23.2 范围逐请求解析、不缓存 | 全部业务路由 | — | 每请求 `get_access_scope` | 测试口径：未打 marker = legacy unrestricted（仅测试 shim） | `test_f030_test_harness.py` 三例 + marked canary；扫描 53 模块 offenders 0 |

### TE-9 Defects

| ID | Severity | Layer | Location | 证据 / 复现 | 期望 vs 实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F030-TD1-01 | LOW | Test Design（文档） | 本文件 TD-1：TD2-P1.3 / TD2-P1.5 / TD2-P3.1 | TD2-P1.3/P1.5 引用未定义的「Issue I-1 / I-3」；TD2-P3.1 文案写「四条」但实际列出 5 条 | 期望：TD 项使用可机械核验的判据且计数与列举一致。实际：引用悬空 + 计数 4≠5 | 无实现影响；仅测试判据可读性。已在 TE-5 裁定口径并逐项执行 | Tester（本报告已修正口径） | 否 |
| F030-T01 | NOTE | Frontend（文案） | `frontend/src/components/ClusterAuthorizationPanel.tsx` 候选为空分支（`EmptyState description="该账号已拥有全部匹配集群的有效授权"`） | 该分支同时覆盖「集群搜索无匹配（`clustersState.total == 0`）」与「系统无 Cluster」子情形；Base 文案为因中性表述「没有可授予的集群（已有效授权的集群不会重复出现）」 | 期望：空态文案在两种成因下均准确。实际：无匹配集群时断言「已拥有全部匹配集群」的因果不成立 | 仅文案误导风险，无数据/契约/权限影响；行为与已批准设计一致（架构 §7.2 指定该字面），实现方未偏离设计 | Architect / Frontend（文案归属设计） | 否（建议后续文案改为因中性） |
| F030-T02 | NOTE | Frontend（接口细节） | `frontend/src/components/authorizationCandidates.ts::canSubmitGrant(active, candidates, selectedClusterId, busy)` | 架构 §7.2 签名草案为 `canSubmitGrant(active, selectedClusterId, busy)` | 期望：按签核设计签名。实际：多一个 `candidates` 参数，追加「选中集群仍须在候选中」校验（更严格，对应架构评审 I-2） | 无 Contract/行为放宽；smoke 逐条覆盖两种签名共同语义 + 新增严格性 | Frontend | 否 |
| F030-T03 | NOTE | Tests | TD-1 TD2-P4.8（可选端到端 500 信封） | 未执行；无测试专用路由注入 | 期望（可选）：grant 路径端到端 500 信封。实际：仅服务层 + F002 信封用例 | Contract §5 v3 的 500 语义由两段证据链支撑，未做单链端到端 | Tester / Coordinator（如需，可后续补） | 否 |
| F030-T04 | NOTE | 交付/基础设施 | `docs/features/F030/artifacts/*.log` | `.gitignore:124 *.log` 使本次全部日志为 ignored 未跟踪文件（F029 artifacts 属已跟踪文件，历史以 `git add -f` 纳入） | 期望：证据可随 Feature 提交。实际：`git status` 不显示这些文件 | 协调器提交时须对本 Feature 的 artifacts 显式 `git add -f`，否则计划 `evidence.test` 指向的日志不会入库 | Coordinator | 否（提交时处理） |

**无 BLOCKER / HIGH / 必须修复 MEDIUM**。

### TE-10 未验证项

| 项 | 原因 | 状态 |
| --- | --- | --- |
| grant 路径端到端 500 信封（TD2-P4.8） | 可选；需注入测试专用路由 | NOT TESTED（证据链：服务层用例 + F002 信封用例本次实际执行） |
| 真实浏览器 DOM / 焦点 / 窄屏 / 键盘可达性 | 架构 §7.3 排除；仓库无 DOM 测试框架（AGENTS §2.6） | NOT_REQUIRED（只声明机制级 + 静态核对） |
| ACTIVE 授权 > 2000 条的真实加载（`truncated` 真机路径） | 需构造超量数据 + 真实前端；成本与收益不匹配 | NOT TESTED（机制断言 + 显式提示文案已核） |
| 并发压力 / >2 连接 / 多轮持续竞态 | 仓库无压力测试设施；F030 只需 201+409 确定性证据 | NOT TESTED（单次真并发、两次独立运行均 attempt 1 相交） |
| 全量 Compose 成功启动 | 环境限制（沿用 F029 记录：`bootstrap` 缺 `INITIAL_ADMIN`） | NOT TESTED，不写成成功 |
| 生产库 / 未知库行为 | 安全约束（DB-D10） | 不执行 |
| 会话语境外的 `alembic_version` 行直读 | fixture 会话结束清空 `public`（表数 0） | 以单 head + 空 diff + 0015 对象断言替代（TD2-P8.4 口径） |
| 前端 409 时序的真实后端联调 | 需要运行中的后端 + 浏览器；smoke 仅替换 `fetch` | NOT TESTED（机制级：`describeClusterAuthorizationError` 分类 + 面板分支静态核对） |

### TE-11 Issues / Next

- **Next（协调器）**：按 Git Workflow / project-state 写 `implementation.test=COMPLETE`、`evidence.test` 指向本报告与 `artifacts/`（注意 TE-9 F030-T04 的 `git add -f`），随后进 REVIEW Gate；`project.acceptance` 仍为 `PENDING`，只在 F030 验证与 Review 通过后恢复 `COMPLETE`。
- **Review 关注点**：F026.md 第 4 行「删除」（EOF 换行归一，TE-5）；`canSubmitGrant` 签名扩展（F030-T02）；空态文案成因歧义（F030-T01）；`*.log` 入库方式（F030-T04）。
- **建议（非阻塞）**：F029-RV-04 同类的「证据锚点」问题——本报告 TEST 段标题为 `## Test Execution（TEST-1，2026-10-23，v1）`，计划 `evidence.test` 建议使用 `#test-executiontest-12026-10-23v1` 或直接引用 `artifacts/*.log`。
- **无剩余阻塞项**。

### TE-12 结论

- 全部 TD-1 验证项（TD2-P1.1–P9.3，共 **53** 项：P1 7 / P2 4 / P3 6 / P4 8 / P5 9 / P6 5 / P7 6 / P8 5 / P9 3）判定：**PASS 51 / NOT TESTED 1（可选 TD2-P4.8）/ NOT_REQUIRED 1（TD2-P5.9）/ FAIL 0 / BLOCKED 0**。
- 无 BLOCKER / HIGH / 必须修复缺陷；证据均为本次独立执行的命令输出，未复用 Backend / Frontend 报告的结论。

**Status（TEST-1）：READY FOR REVIEW**

GIT: git rev-parse --short HEAD
GIT: git status --porcelain=v1 --untracked-files=all
GIT: git branch --show-current
GIT: git rev-parse v3.2
GIT: git merge-base v3.2 HEAD
GIT: git log --oneline 70db846..HEAD
GIT: git diff --stat 70db846...HEAD
GIT: git diff --name-only 70db846...HEAD
GIT: git diff --name-only 70db846...HEAD -- backend/alembic
GIT: git diff --name-only 70db846...HEAD -- frontend/src/api
GIT: git diff --name-only 70db846...HEAD -- backend/app/models backend/app/schemas backend/app/core backend/app/api
GIT: git diff 70db846...HEAD -- backend/app/services/cluster_authorization.py backend/pyproject.toml
GIT: git diff 70db846...HEAD -- backend/tests/conftest.py
GIT: git diff 70db846...HEAD -- docs/api/F026.md
GIT: git diff 70db846...HEAD -- docs/api/F002.md … docs/api/F023.md（逐文件：for 循环 12 份，统计增删行）
GIT: git diff 70db846...HEAD -- docs/api/  （append-only / No-newline marker 统计）
GIT: git diff --stat 70db846...HEAD -- docs/product/requirements-v3.md
GIT: git diff 70db846...HEAD -- backend/app  （注释性 diff 过滤）
GIT: git diff 70db846...HEAD -- backend/app/core/permissions.py
GIT: git diff 70db846...HEAD -- docs/database
GIT: git diff 70db846...HEAD -- docs/api/F027.md docs/api/F015.md docs/api/F017.md backend/app/services/audit.py
GIT: git show 70db846:docs/api/F026.md
GIT: git show 70db846:docs/api/F026.md | tail -1
GIT: git show 70db846:frontend/src/components/ClusterAuthorizationPanel.tsx
GIT: git show 70db846:docs/project/project-plan.yaml
GIT: git check-ignore -v frontend/dist/index.html
GIT: git check-ignore -v docs/features/F030/artifacts/targeted-pytest.log
GIT: git ls-files docs/features/F029/artifacts
