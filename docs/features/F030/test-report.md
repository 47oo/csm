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
