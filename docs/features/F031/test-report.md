# F031 F030 Review 非阻塞项收尾 — Test Report

> 本文件同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本与结论。
> **TEST DESIGN READY 仅表示方案可验证，不是测试通过，不批准实现或合并。** TD-1 段保留原文；TEST 执行结论见文末 `## Test Execution（TEST-1，2026-10-23，v1）`。

## Test Design（TD-1，2026-10-23，v1）

### T1 Task / Status / Basis

- **Task**：F031（ENABLER，P2，M22）；分支 `feature/F031-review-closeout`；plan_revision 17；阶段 TEST_DESIGN。
- **Status**：**TEST DESIGN READY**。
- **Basis**：`docs/product/requirements-v3.md` revision 11；`docs/features/F031/product.md`、`docs/features/F031/architecture.md`；`docs/features/F030/review-report.md`（F030-RV-03…RV-10、F030-T03）；`docs/features/F030/architecture.md` v1 + §16；`docs/api/F026.md` v3；`docs/database/f026-cluster-authorization.md` v1；`docs/features/F030/test-report.md` TD-1/TEST-1。

### T2 输入基线与层级

| 项 | 值 |
| --- | --- |
| 分支 / 提交 | `feature/F031-review-closeout`；start_commit `2c827fb`；TD HEAD `54615d0`；工作区 clean |
| 层级 | database=false、backend=true、frontend=true、api_required=false；Database/Contract NOT_REQUIRED |
| 后端基线 | `--collect-only` = 733 + 1 module skip；定向 3 文件 = 28 |
| 前端基线 | smoke 328 passed；tsc/build 由 TEST 执行 |
| 数据库 | PostgreSQL 16.15，`csm_test`，`localhost:55432`（`.env.test` 的 5432 不可达，TEST 必须显式覆盖） |
| 计划基线 | `validate_project_state.py` / `render_project_views.py` 双 VALID |

### T3 Environment

- 真实 PostgreSQL 16.15（容器 `csm-f026-pg` → `localhost:55432/csm_test`）；fixture 重建 public + alembic head。
- 后端 `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`；SQLite/Mock 不作约束/并发证据。
- 前端 Node v22.23.3；`tsc --noEmit` 不落盘；`npm run build` 写 gitignored `dist/`。
- 证据目录 `docs/features/F031/artifacts/*.log`（`.gitignore` 覆盖，协调器须 `git add -f`）。

### T4 验收映射

图例：D 文档/差异、S 静态/结构、I 真实 PostgreSQL、F 前端机制、P 计划一致性。

#### P1 — RV-03 errata（D）
- A1 F030 architecture diff 删除行 0（纯追加）。
- A2 前 467 行 sha256 与 base 相同。
- A3 `## 17. F031 errata` 与 `### 17.1`…`### 17.5` 存在。
- A4 §17.1 签名/规则与实际 `canSubmitGrant(active, candidates, selectedClusterId, busy)` 逐参一致。
- A5 交叉核对 `authorizationCandidates.ts` 实参名/顺序一致。
- A6 §17.2 新空态字面、§17.3 覆盖三处引用、§17.4 `_reject_unknown_query`、§17.5 以 §17 为准。
- A7 头部指针含 F031 与 §17。

#### P2 — RV-04 文案（S+F）
- A1 `frontend/src` 新字面命中 1，且为 `EmptyState description`。
- A2 `frontend/src` 旧字面命中 0。
- A3 新字面与 `56cc6ac^` 基线同字面。
- A4 该文件 diff 仅空态 description 行 + RV-09 注释行；无按成因分支。
- A5 `canSubmitGrant` 调用行与 base 字节相同。
- A6 `smoke` 328、`tsc` exit 0、`build` exit 0。

#### P3 — RV-05 注释（S）
- A1 base/HEAD AST dump sha256 相等（零可执行变化）。
- A2 新 token：`_reject_unknown_query`、`handler's first step`、`before path and semantic validation`、`not an information-leak`、`USER_ADMIN only`。
- A3 旧歧义短语命中 0；`existence oracle` 命中 0。
- A4 三条结论保留。
- A5 diff 新增/删除行全为 `#` 行。

#### P4 — RV-06 并发（I）
- A1 `MAX_ATTEMPTS = 5`、`range(1, MAX_ATTEMPTS + 1)`、输出 `attempts used: n/5`。
- A2 `assert overlap_observed` 保留，无 skip/xfail。
- A3 全部原有 assert 与 base 逐字节相同；DB 五项断言齐全。
- A4 运行 1 passed，`overlap=True`、`[201,409]`、409 reason `already_granted`。
- A5 无顺序调用替代。

#### P5 — RV-07 日志（D）
- A1 base 全文 sha256 == HEAD 前 37 行（纯追加）。
- A2 errata 块含路径笔误说明、正确路径、TD2-P3.4 结论引用、可复现 grep。
- A3 错误路径仅历史 1 处；正确路径 ≥1。
- A4 `grep -n "_reject_unknown_query" backend/app/api/v1/cluster_authorizations.py` 输出粘入日志。
- A5 F030 test-report diff 空。

#### P6 — RV-08 F026 头部（D）
- A1 `git diff --numstat -- docs/api/F026.md` = `1 0`。
- A2 新行含历史依据说明/14/历史批准依据/16/v3/不改变正文。
- A3 版本行与签核行字节不变。
- A4 `docs/api/` 仅 F026 变更（其余 15 份空 diff）。
- A5 既有 code/reason 出现次数不变。

#### P7 — RV-09 引用（S+F）
- A1 `frontend/` 中「架构评审 I-2 / 架构 I-2」命中 0。
- A2 三处新引用含 `§17.1` 与真实函数名。
- A3 `await test(` 计数不变；smoke 328。
- A4 tsc/build exit 0。
- A5 F030 test-report 历史措辞保留；本报告登记取代关系。

#### P8 — RV-10 接受边界（S+I）
- A1 守卫文件 diff 空；`INTEGRATION_DIR` 不变；conftest legacy shim 条件仍为 `tests/integration`。
- A2 `tests/smoke` 等范围外 scope 符号命中 0。
- A3 守卫用例（含非空洞）通过。
- A4 接受边界与 reopen 条件写入本报告 T9 与 architecture §3.8。

#### P9 — T03 500 信封（I）
- A1 用例位于 `real_scope` 模块；无生产逻辑改动。
- A2 未 override 时同一请求 → 401 `AUTH_REQUIRED`。
- A3 override 后 500 精确信封 `INTERNAL_ERROR`。
- A4 响应不含 Traceback/约束名/23503/幽灵用户名。
- A5 无授权行、无 Audit 残留。
- A6 真实操作者同 pair → 201 + 行 1 ACTIVE + Audit 1 CREATE。
- A7 `auth_app.routes` 无 `/_test*`。
- A8 override `try/finally` 清理。
- A9 docstring 明示绕过认证、不作为 401/403 证据。
- A10 若采用 F002 式回退路由，记录形态；不得改生产代码。

#### P10 — 不新增端点/字段/错误码/权限/Schema（S+D）
- A1 变更文件白名单。
- A2 `backend/app/{api,schemas,models,core}`、`backend/alembic`、`frontend/src/api`、`docs/product`、`docs/database` 空 diff。
- A3 `create_app()` 无 `/_test*`；router 装饰器计数不变。
- A4 `permissions.py` 空 diff；新增行无 `ROLE_PERMISSIONS`/`permission:`。
- A5 新增 code/reason token ⊆ base 既有集合。
- A6 `alembic heads` 单 head 0015。
- A7 前端 API 调用计数不变。
- A8 需求正文空 diff。

#### TD-PROD / TD-REG / TD-PLAN

| ID | 断言 |
| --- | --- |
| TD-PROD-1 | P1–P10 全 PASS 或 NOTE 有书面接受理由 |
| TD-PROD-2 | P10 + 定向/全量回归 + P9(A3/A5) + P4(A4)：授权/Audit/错误顺序/权限不变 |
| TD-PROD-3 | F030 P1–P9 以重跑回归，不复用旧 PASS |
| TD-PROD-4 | TEST 阶段 `project.acceptance` 仍 PENDING；Review 后由协调器恢复 |
| TD-REG-1 | 定向 29 passed；全量 729 passed / 6 skipped（skip 集合不变） |
| TD-REG-2 | 前端 tsc/build exit 0；smoke 328 |
| TD-REG-3 | P10 A1–A8 + P6 |

### T5 命令与预期计数

| # | 命令 | 预期 |
| --- | --- | --- |
| 1 | 定向 3 文件（真实 PG） | **29 passed** |
| 2 | `-k "test_concurrent_grant_two_connections_single_winner or test_grant_path_internal_error_envelope_end_to_end"` | **2 passed**（不要用宽泛 `-k "concurrent_grant or internal_error_envelope"`，会命中 F002 用例得 3） |
| 3 | `pytest --collect-only -q` | **734 + 1 module skip** |
| 4 | `pytest -q` 全量 | **729 passed / 6 skipped** |
| 5 | 前端 tsc / build / smoke | exit 0 / exit 0 / **328** |
| 6 | 计划校验（不带 --write） | 双 VALID |
| 7 | diff/grep/sha256/AST 核对 | 见 T4 |

### T6 反空洞与边界

| 项 | 反制 |
| --- | --- |
| P1 | errata 与实现签名逐参比对 |
| P2 | diff 行白名单 + 调用行字节不变 + smoke/tsc/build |
| P3 | AST 哈希相等 + 非注释行增删 0 |
| P4 | 失败语义保留 + assert 行逐字节比对 |
| P5 | 前 37 行 sha256 == base |
| P6 | 单文件 +1/−0 + 其余空 diff |
| P7 | 新引用解析到真实 §17.1 与函数名 |
| P8 | 范围外符号 0 + 守卫非空洞 |
| P9 | 真实路径 + 无 `/_test*` + 401 对照 + 真实 23503 + 归因 201 + 零残留 |
| P10 | 目录级空 diff + token 集合包含 + 单 head |

### T9 接受边界与 Reopen 条件（RV-10）

- 接受边界：`real_scope` 守卫仅覆盖 `tests/integration/test_*.py`；`tests/smoke` 不使用 scope 符号，无 override 时走真实依赖，不存在静默 legacy 通过。
- Reopen 条件：若 conftest legacy shim 扩展到 `tests/integration` 以外，必须同步扩展守卫 `INTEGRATION_DIR` 与 AST 扫描范围。

### T10 Defects（Tester 设计阶段）

| ID | Severity | Location | 说明 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- |
| F031-TD1-01 | LOW | architecture §6 第 2 条 | `-k "concurrent_grant or internal_error_envelope"` 会命中 F002 用例得 3；T5 已给精确命令 | Architect/Tester | 否 |
| F031-TD1-02 | LOW | architecture §3.7 Panel 注释 | 注释只描述「不可提交」，相邻行为「选择框不呈现脏值」；建议同时覆盖 | Architect/Frontend | 否 |
| F031-TD1-03 | NOTE | architecture §3.10/§4 | 「其余 12 份」应为「除 F026 的 15 份」 | Architect | 否 |
| F031-TD1-04 | NOTE | `.env.test` | TEST_DATABASE_URL 5432 不可达；TEST 显式覆盖为 55432 | Coordinator/Tester | 否 |
| F031-TD1-05 | NOTE | artifacts | `*.log` 被 gitignore；协调器 `git add -f` | Coordinator | 否 |
| F031-TD1-06 | NOTE | plan scope ⑨ | 「测试专用路由」与设计 override 手段描述差异；正断言为无 `/_test*` 路由 | Coordinator | 否 |
| F031-TD1-07 | NOTE | project.acceptance | F031 TEST 只作适用回归；恢复口径由协调器说明 | Coordinator | 否 |

**无 BLOCKER / HIGH / 必须修复 MEDIUM。**

### T11 Issues / Next

- Architect 最终签核时处置 F031-TD1-01/02/03。
- 实现完成后启动 TEST，追加 TEST-1 段。
- TEST 证据日志注意 `git add -f`。

### T12 结论

**TEST DESIGN READY**：10 项跟进均可机械核验；环境与计数基线已确认；无阻塞。本结论不构成测试通过或实现批准。

---

## Test Execution（TEST-1，2026-10-23，v1）

### TE-1 Task / Status / Basis

- **Task**：F031（ENABLER，P2，M22）；分支 `feature/F031-review-closeout`；plan_revision 17；阶段 TEST（独立验证；仅写本报告 TEST 段与 `docs/features/F031/artifacts/`）。
- **Status**：**READY FOR REVIEW**（P1–P10 与 TD-PROD / TD-REG / TD-PLAN 全部 PASS；无必须修复缺陷；3 项 TD-1 断言口径与本 1 项历史证据署名以 NOTE 记录）。
- **Basis（版本绑定）**：
  - 需求 `docs/product/requirements-v3.md` revision 11（§23.2、§31、§32、§35）；
  - `docs/features/F031/product.md`（READY FOR ARCHITECT，协调器产物 `c0308a5`）；
  - `docs/features/F031/architecture.md` v1 + §10 最终设计签核（CONTRACT Gate：READY FOR IMPLEMENTATION；Database/Contract NOT_REQUIRED）——本段核对的即为该版本，未发现差异；
  - `docs/features/F031/test-report.md` TD-1 v1（TEST DESIGN READY）；
  - `docs/features/F031/implementation.md`（BACKEND COMPLETE / FRONTEND COMPLETE / 文档修订完成）；
  - 上游缺陷源 `docs/features/F030/review-report.md`（F030-RV-03…RV-10、F030-T03）；`docs/features/F030/architecture.md` v1 + §16 + §17 errata；`docs/api/F026.md` v3 头部；`docs/database/f026-cluster-authorization.md` v1（DB-D401–D420，本次无变更）。
- **复用声明**：TD-1 的 PASS 判定一律由本次实际执行产生，未复用 Backend / Frontend 报告中的结论；F030 的 P1–P9 以本次定向 + 全量重跑覆盖（TD-PROD-3），未引用 F030 旧 PASS 代替执行。

### TE-2 输入基线（本段绑定的代码版本）

| 项 | 值 |
| --- | --- |
| 分支 | `feature/F031-review-closeout` |
| Base / start_commit | `2c827fb`（`docs(plan): approve revision 17 with F031 review closeout`） |
| TEST 输入 HEAD | **`bf384c8`**（`feat(F031): close remaining review follow-ups`）；核对时工作区 clean |
| 实现提交序列 | `c0308a5`（product+plan）→ `54615d0`（architecture）→ `bdda84f`（TD-1+§10 签核）→ `bf384c8`（实现与文档修订） |
| 变更文件数 | 15（base..HEAD）：F031 文档 4 + 计划/派生视图 4 + 目标修订 7；无跟踪文件之外的残留 |
| layers / api_required | backend=true、frontend=true、database=false；api_required=false；Database / Contract NOT_REQUIRED |

### TE-3 Environment

- 后端：Python 3.12.7（WSL2），真实 PostgreSQL **16.15**（容器 `csm-f026-pg`，`postgres:16`，宿主 `localhost:55432` → 5432），库 `csm_test`，角色 `csm`（**superuser** → `test_migrations.py` V3b 用例按既有条件 skip）。
- 显式覆盖 `TEST_DATABASE_URL=postgresql+psycopg://csm:<pw>@localhost:55432/csm_test`（`.env.test` 的 5432 不可达，本段未使用）；每次 session fixture 重建 `public` + alembic head（`0015_user_cluster_authorizations`）。
- 后端运行参数：`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`（全段一致，无 `.pyc`/缓存落盘）。
- 前端：Node **v22.23.3**；`npx tsc --noEmit` 不落盘；`npm run build`（tsc + vite build，3214 modules，仅既有 >500 kB chunk 告警）写 gitignored `dist/`。
- 证据：`docs/features/F031/artifacts/*.log`（`.gitignore:124 *.log` 覆盖，协调器需 `git add -f`）；已核查 artifacts 中 **无凭据字符串**（`grep -rl csmtestpw` = 0），日志内引擎 URL 由 SQLAlchemy 掩码为 `csm:***`。
- SQLite / Mock 未用于任何约束或并发证据。

### TE-4 命令与实际结果

| # | 命令（均以真实 PG、`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider` 执行） | 预期 | 实际 | 证据 |
| --- | --- | --- | --- | --- |
| 1 | 定向 3 文件：`tests/integration/test_cluster_authorizations.py tests/integration/test_f027_access_scope.py tests/integration/test_f030_test_harness.py` | 29 passed | **29 passed**（51.89s） | `targeted-pytest.log` |
| 1b | 同上按文件收集数 | 15+11+3 | 15 + 11 + 3 = 29（base 为 14+11+3 = 28） | `collect.log`、`targeted-file-counts.log` |
| 2 | `-k "test_concurrent_grant_two_connections_single_winner or test_grant_path_internal_error_envelope_end_to_end"`（`-s`） | 2 passed | **2 passed**（4.79s）；`attempt 1: statuses=[409, 201] overlap=True`、`attempts used: 1/5` | `targeted-two-new-cases.log` |
| 3 | `pytest --collect-only -q` | 734 + 1 module skip | **734 collected**；`SKIPPED [1] test_f016_acceptance.py:50`（F016 acceptance module disabled） | `collect.log` |
| 4 | 全量 `pytest -q` | 729 passed / 6 skipped | **729 passed / 6 skipped**（1166.19s）；skip 集合与基线完全一致（F016 module ×1、F028 ×4 因 `F016_ACCEPTANCE=1` 未启用、`test_migrations.py:105` superuser V3b ×1） | `full-pytest.log` |
| 5 | `npx tsc --noEmit` | exit 0 | **exit 0**，0 error（日志 0 行） | `frontend-typecheck.log` |
| 6 | `npm run build` | exit 0 | **exit 0**；3214 modules；仅既有 chunk 体积告警 | `frontend-build.log` |
| 7 | `npm run smoke:client` | 328 passed | **328 passed, 0 failed**；`await test(` 计数 base/HEAD 均 328 | `frontend-smoke.log`、`p7-rv09-references.log` |
| 8 | `python3 scripts/validate_project_state.py` | VALID | **PROJECT STATE VALID**（exit 0） | `plan-validation.log` |
| 9 | `python3 scripts/render_project_views.py`（不带 `--write`） | VALID | **PROJECT VIEWS VALID**（exit 0）；执行后工作区无跟踪改动 | `plan-validation.log` |
| 10 | P1/P5/P6 追加性与 sha256、P2/P3/P4/P7/P8/P10 的 diff/grep/AST/token 核对、`alembic heads` | 见 TE-5 | 全部符合 | `p1-p5-p6-doc-diff.log`、`p1-errata-signature.log`、`p2-rv04-copy.log`、`p2-rv04-wiring.log`、`p3-rv05-comment.log`、`p4-rv06-concurrency-static.log`、`p5-rv07-static-log.log`、`p6-rv08-f026-header.log`、`p7-rv09-references.log`、`p8-rv10-guard.log`、`p8-guard-and-f017-file.log`、`p10-scope-nodrift.log`、`environment.log` |

**执行过程披露（证据完整性）**

- 首次全量运行被我方并发触发的用例 fixture（重建 `public`）干扰，产生 4 个伪失败，**主动中止并整份作废**，作废日志仅保留在工作区（未入库），不作为证据。
- 第二次全量运行运行至 ~28% 时 `test_f017_tester_acceptance.py::test_concurrent_revoke_yields_single_success` 失败一次（728 passed / 1 failed / 6 skipped），作废日志仅保留在工作区（未入库）；隔离复跑 3/3 pass（`f017-flake-rerun.log`）、同文件 15 passed（`p8-guard-and-f017-file.log`），根因判定见 TE-9 `F031-TEST1-01`（F031 范围外）。
- 第三次（最终）全量运行干净通过：**729 passed / 6 skipped**，即为 TD-REG-1 的判定依据（`full-pytest.log`）。三次运行均落在 `localhost:55432/csm_test`，未触碰生产或未知数据库。

### TE-5 验收映射（TD-1 P1–P10 逐项判定）

图例：D 文档/差异、S 静态/结构、I 真实 PostgreSQL、F 前端机制、P 计划一致性。

#### P1 — RV-03 errata（D）→ 全部 PASS

| A | 判定 | 证据（实际执行） |
| --- | --- | --- |
| A1 F030 architecture 删除行 0 | **PASS** | `git diff --numstat 2c827fb..bf384c8` = `39 0`；diff 中 `-` 行 0；仅 2 个 hunk：`@@ -11,0 +12 @@`（头部指针 1 行）与 `@@ -467,0 +469,38 @@`（文末 §17） |
| A2 前 467 行与 base 相同 | **PASS（等价强化口径）** | 字面口径与设计 §3.1/§3.7 的「头部 +1 行指针」互斥；改为逐 hunk 回放：`base + 插入行(11→+1, 467→+38)` 与 HEAD **逐字节相同**（sha256 `a632bed6…`）；base 全文 sha256 `30a9cf13…`、长度 38518 bytes 未变。口径差异记 `F031-TD1-08`（NOTE） |
| A3 §17 与 17.1–17.5 存在 | **PASS** | `## 17. F031 errata` ×1、`### 17.1`…`### 17.5` 各 ×1 |
| A4 §17.1 签名/规则与实现逐参一致 | **PASS** | §17.1 code block 形参与顺序 = `authorizationCandidates.ts:86-91`（`active, candidates, selectedClusterId, busy`）；规则短句与 92–96 行五条判据一一对应（含 `candidates.clusters` 成员校验） |
| A5 调用端实参名/顺序一致 | **PASS** | `ClusterAuthorizationPanel.tsx:196` `canSubmitGrant(activeGrants, candidates, selectedClusterId, grantBusy)`；文件内无其它调用点（`grep` 命中 1 调用 + 1 import） |
| A6 §17.2/§17.3/§17.4/§17.5 内容 | **PASS** | 新空态字面在 §17.2 与 Panel 各 ×1；§17.3 三处引用改指 `canSubmitGrant` / §17.1；§17.4 含 `_reject_unknown_query`、handler 第一步、先于路径与语义校验、`USER_ADMIN`；§17.5 明确「以 §17 为准」且不改变 Contract |
| A7 头部指针含 F031 与 §17 | **PASS** | 第 12 行 `- F031 errata（2026-10-23）：… 以 §17 为准（依据 plan_revision 17、F030-RV-03/04/05/09）` |

#### P2 — RV-04 文案（S+F）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 新字面命中 1 且为 `EmptyState description` | **PASS** | `frontend/src` 唯一命中 `ClusterAuthorizationPanel.tsx:483`，行内容即 `<EmptyState description="没有可授予的集群（已有效授权的集群不会重复出现）" />` |
| A2 旧字面命中 0 | **PASS** | `grep -rn 该账号已拥有全部匹配集群的有效授权 frontend/src` = 0 |
| A3 与 `56cc6ac^` 基线同字面 | **PASS** | `56cc6ac^` 命中 1、F031 base `2c827fb` 命中 0、HEAD 命中 1（恢复因中性字面） |
| A4 diff 仅 2 行语义位 | **PASS** | Panel diff 恰 2 个 hunk：193 行注释（RV-09）、483 行空态 description；无按成因分支、无门控逻辑改动 |
| A5 `canSubmitGrant` 调用行字节相同 | **PASS** | base 与 HEAD 该行 sha256 均 `572dd04d…` |
| A6 smoke 328 / tsc 0 / build 0 | **PASS** | `frontend-smoke.log`、`frontend-typecheck.log`、`frontend-build.log` |

附加（Product ② 「核对 wiring」）：`grantSubmittable` 仍由 `canSubmitGrant` 计算并驱动 `disabled={!grantSubmittable}`（508 行）与提交守卫（215 行），`visibleSelectedClusterId` 仍用于 `Select value`（488 行）→ 空态/门控接线未变（`p2-rv04-wiring.log`）。

#### P3 — RV-05 注释（S）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 AST dump sha256 相等 | **PASS** | base / HEAD 均 `61e10340c0ff…`（`ast.dump(..., include_attributes=False)`） |
| A2 新 token 齐全 | **PASS（按换行归一）** | 注释块拼接后含 `_reject_unknown_query`、`handler's first step`、`before path and semantic validation`、`not an information-leak`、`USER_ADMIN only`；且该注释块与设计 §3.3 code block **逐字节相同**。字面 grep 因设计自身的换行断词失效，记 `F031-TD1-10`（NOTE） |
| A3 旧歧义短语 0、`existence oracle` 0 | **PASS** | base 含「and undeclared params are rejected by the route…」=True，HEAD=False；`existence oracle` / `存在性预言机` base/HEAD 均 0 |
| A4 三条结论保留 | **PASS** | `404 before any semantic query validation`、`` `q` is only validated after the account exists ``、`hence 422 even for an unknown account` base/HEAD 均存在 |
| A5 diff 增删行全为 `#` 行 | **PASS** | 8 行增删全部 `#` 注释行；非注释增删行 = 0（5+/3−） |

#### P4 — RV-06 并发（I）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 `MAX_ATTEMPTS=5` / `range(1, MAX_ATTEMPTS+1)` / `attempts used: n/5` | **PASS** | 三处均 ×1；运行输出 `attempts used: 1/5` |
| A2 `assert overlap_observed` 保留、无 skip/xfail | **PASS** | `assert overlap_observed, attempts` 保留；模块内无 `skip`/`xfail`（仅注释文字含该词）；无顺序调用替代（仍为双线程 + Barrier 相交断言） |
| A3 原 assert 与 base 逐字节相同；DB 五项断言齐 | **PASS** | AST 抽取函数内 16 条 `assert` 行，base/HEAD **多重集完全相等**（删 0 增 0）；DB 断言齐：总行 1 / ACTIVE 1 / `active[0].id == 201 id` / Audit 1 / Audit `object_id` 对齐且 `action=CREATE` |
| A4 运行 1 passed，overlap=True，[201,409]，409 `already_granted` | **PASS** | `attempt 1: statuses=[409, 201] overlap=True spans=[(706501.4979,706501.5471),(706501.4987,706501.5737)]`；`2 passed`（另 1 例为 T03）；`already_granted` 由用例断言并通过 |
| A5 无顺序调用替代 | **PASS** | `_run_concurrent_grant` 仍为双 `TestClient` + `threading.Barrier(2)` 模式，未退化为顺序调用 |

#### P5 — RV-07 日志（D）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 base 全文 sha256 == HEAD 前 37 行 | **PASS** | 均 `3ce6f1f24223e…`；base 37 行 / HEAD 49 行，diff `12 0`，删除行 0 |
| A2 errata 块要素齐全 | **PASS** | 含路径笔误说明、正确路径 `backend/app/api/v1/cluster_authorizations.py`、`集成用例 TD2-P3.4` 结论引用、可复现只读 grep 命令与输出 |
| A3 错误路径 1 处 / 正确路径 ≥1 | **PASS（口径细化）** | F030 原文区域（前 37 行）错误路径 **1 处**（第 8 行）；HEAD 全文 2 处 = 原文 1 + errata 对历史报错的**引述** 1；正确路径 3 处。记 `F031-TD1-09`（NOTE） |
| A4 grep 输出已粘入 | **PASS** | 粘贴 `_reject_unknown_query` 51/95 行与 `_parse_uuid(user_id)` 98/129 行；我方独立重跑 `grep -n _reject_unknown_query backend/app/api/v1/cluster_authorizations.py` 得到 51/95，与粘贴一致 |
| A5 F030 test-report diff 空 | **PASS** | `git diff --numstat 2c827fb..HEAD -- docs/features/F030/test-report.md` 无输出 |

#### P6 — RV-08 F026 头部（D）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 `1 0` | **PASS** | `git diff --numstat -- docs/api/F026.md` = `1 0` |
| A2 新行要素 | **PASS** | 单一新增行含「历史依据说明」「plan_revision 14」「历史批准依据」「plan_revision 16」「v3」「不改变正文」 |
| A3 版本行/签核行字节不变 | **PASS** | `- **版本**：v3`、`- **签核**：Architect，…（v3，F030 跟进…）`、`- **状态**：READY` 三行 base/HEAD 完全相同；HEAD 去掉该新增行与 base 逐字节相同 |
| A4 `docs/api/` 仅 F026 变更 | **PASS** | `docs/api/` 共 16 份，15 份 diff 空；变更仅 `docs/api/F026.md` |
| A5 既有 code/reason 出现次数不变 | **PASS** | 大写 code token 集合 base/HEAD 均 32 且相同；`already_granted` 9/9、`already_revoked` 7/7；`reason:` 值多重集相等；无新增 code/reason |

#### P7 — RV-09 引用（S+F）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 `frontend/` 中悬空引用 0 | **PASS** | `grep -rn "架构评审 I-2\|架构 I-2" frontend/` = 0（仓库其余命中均为设计/计划/历史证据文本与本次 F031 报告自身，符合接受边界） |
| A2 三处新引用含 §17.1 与真实函数名 | **PASS（口径细化）** | Panel:193 含 `canSubmitGrant` + `§17.1`；smoke:280 含 `canSubmitGrant` + `§17.1`；smoke:8589 断言注释含 `canSubmitGrant`（设计 §3.7 原文亦未要求 §17.1）。字面口径记 `F031-TD1-10`（NOTE） |
| A3 `await test(` 计数不变、smoke 328 | **PASS** | base/HEAD 均 328；运行 328 passed / 0 failed |
| A4 tsc/build exit 0 | **PASS** | 见 TE-4 #5/#6 |
| A5 F030 test-report 历史措辞保留；本报告登记取代 | **PASS** | F030 test-report diff 空；F030-T02 中「架构评审 I-2」按历史证据保留，本报告 TE-5 P7 与架构 §17.3 登记正确指向 |

#### P8 — RV-10 接受边界（S+I）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 守卫文件 diff 空；`INTEGRATION_DIR` 不变；shim 条件仍 `tests/integration` | **PASS** | `test_f030_test_harness.py`、`tests/conftest.py`、`tests/smoke/` diff 均空（唯一测试改为 `test_cluster_authorizations.py`）；`INTEGRATION_DIR = Path(__file__).resolve().parent`；`conftest.py:211` `"tests/integration" in path and … real_scope is None` |
| A2 范围外 scope 符号 0 | **PASS** | `tests/smoke/` 中 `get_access_scope`/`access_scope`/`real_scope` 命中 0（4 个 smoke 模块）；`get_access_scope` 仅出现在 `conftest.py` 与 3 个 `tests/integration` 模块 |
| A3 守卫用例（含非空洞）通过 | **PASS** | `test_unmarked_module_gets_legacy_scope`、`test_real_scope_usage_requires_marker`、`test_scope_scan_is_not_vacuous` 3 passed（`p8-guard-and-f017-file.log`），并计入定向 29 |
| A4 接受边界与 reopen 条件落文档 | **PASS** | TD-1 T9 + architecture §3.8 均已写明：守卫维持 `tests/integration`；若 legacy shim 扩展到其它目录，必须同步扩展 `INTEGRATION_DIR` 与 AST 扫描范围。本段 TE-11 复述并确认 |

#### P9 — T03 500 信封（I）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 位于 `real_scope` 模块；无生产逻辑改动 | **PASS** | 模块 `pytestmark = pytest.mark.real_scope`（第 21 行）；生产侧唯一改动为注释（AST 相等） |
| A2 未 override → 401 `AUTH_REQUIRED` | **PASS** | 用例先发对照请求断言 401 + `AUTH_REQUIRED`，实跑通过 |
| A3 override 后 500 精确信封 | **PASS** | 断言响应体 **完全等于** `{"error":{"code":"INTERNAL_ERROR","message":"Internal server error","details":{}}}`；实跑通过 |
| A4 无泄漏 | **PASS** | 对 `Traceback`、`fk_user_cluster_authorizations_granted_by_users`、`23503`、`IntegrityError`、幽灵用户名、幽灵 UUID 六个 token 断言不在响应体中（真实 23503 由服务端日志产生，未进入响应）；实跑通过 |
| A5 无授权行、无 Audit 残留 | **PASS** | 500 后该 (user, cluster) 行 0、`user_cluster_authorization` Audit 0；实跑通过 |
| A6 真实操作者同 pair → 201 + 行 1 ACTIVE + Audit 1 CREATE | **PASS** | 201、`granted_by == admin.id`、行数 1、`revoked_at is None`、Audit `["CREATE"]`；实跑通过 |
| A7 `auth_app.routes` 无 `/_test*` | **PASS** | 用例断言通过；另有静态核对 `grep '/_test' backend/app` = 0 |
| A8 override `try/finally` 清理 | **PASS** | `dependency_overrides[get_current_operator] = lambda: ghost` 后 `finally: auth_app.dependency_overrides.pop(get_current_operator, None)` |
| A9 docstring 明示绕过认证、不作 401/403 证据 | **PASS** | docstring 原文含「deliberately bypasses authentication… not evidence for 401/403 semantics」 |
| A10 回退形态记录 | **PASS（未启用回退）** | 采用设计主路径（真实 Contract 路由 + 测试级 dependency override），未引入 F002 式测试专用路由；无 `/_test*` 路由 |

#### P10 — 不新增端点/字段/错误码/权限/Schema（S+D）→ 全部 PASS

| A | 判定 | 证据 |
| --- | --- | --- |
| A1 变更文件白名单 | **PASS** | 15 个变更文件全部在设计 §1/§5 声明范围内：`backend/app/services/cluster_authorization.py`、`backend/tests/integration/test_cluster_authorizations.py`、`docs/api/F026.md`、`docs/features/F030/{architecture.md,artifacts/p3-p6-static.log}`、`docs/features/F031/*`（4）、`docs/project/{project-plan.yaml,backlog.md,dependency-map.md,milestones.md}`（协调器计划/派生视图字段）、`frontend/{scripts/smoke-client.mjs,src/components/ClusterAuthorizationPanel.tsx}` |
| A2 受保护目录空 diff | **PASS** | `backend/app/{api,schemas,models,core}`、`backend/alembic`、`frontend/src/api`、`docs/product`、`docs/database` 均 0 变更文件 |
| A3 无 `/_test*`；router 装饰器计数不变 | **PASS** | `grep '/_test' backend/app` = 0；router 装饰器 base/HEAD 均 83 |
| A4 `permissions.py` 空 diff；新增行无权限 token | **PASS** | diff 空；`backend/app` 新增行中 `ROLE_PERMISSIONS`/`permission:` 命中 0 |
| A5 新增 code/reason ⊆ base 既有集合 | **PASS** | 生产代码与 Contract 新增行无新 code/reason（`backend/app`+`frontend/src` 新增非注释行仅 1 条 JSX 文案 + 1 条 `//` 注释）；测试新增字面中 `INTERNAL_ERROR` 为 base 既有（F002/F026/`errors.py`） |
| A6 单 head 0015 | **PASS** | `ScriptDirectory.get_heads() == ['0015_user_cluster_authorizations']`，count 1 |
| A7 前端 API 调用计数不变 | **PASS** | `apiFetch`/`from "../api"` 计数 base/HEAD 均 133 |
| A8 需求正文空 diff | **PASS** | `docs/product/requirements-v3.md`、`docs/product/domain-model.md` diff 空 |

### TE-6 横切 Gate

| ID | 判定 | 证据 |
| --- | --- | --- |
| TD-PROD-1 | **PASS** | P1–P10 全 PASS；3 项口径差异以书面 NOTE 接受（`F031-TD1-08/09/10`），无行为/证据强度下降 |
| TD-PROD-2 | **PASS** | P10 A1–A8 + 定向 29 + 全量 729/6 + P9(A3/A5) + P4(A4)：端点/字段/错误码/权限/错误顺序（401→403→422→404→409→500）/Audit 均无变化（认证顺序由 `test_f017_tester_acceptance.py::test_auth_error_responses_are_equivalent_and_401_before_403`、`test_f027_access_scope.py::test_error_precedence_and_admin_deleted_behavior` 在全量中实际执行并通过） |
| TD-PROD-3 | **PASS** | F030 P1–P9 以重跑覆盖：定向 3 文件含 F026/F030 相关用例，全量 729 含 F026–F030 全部套件，未复用 F030 旧 PASS |
| TD-PROD-4 | **PASS** | 计划快照：`project.acceptance.status=PENDING`（`pending_reason`：F031 完成后重新执行适用验证并恢复 COMPLETE）、`F031.status=IN_PROGRESS`、`current_stage=TEST`、`implementation.test=PENDING`（`plan-f031-snapshot.log`） |
| TD-REG-1 | **PASS** | 定向 29 passed；全量 729 passed / 6 skipped，skip 原因集合与基线逐条一致 |
| TD-REG-2 | **PASS** | tsc exit 0、build exit 0、smoke 328 passed / 0 failed |
| TD-REG-3 | **PASS** | P10 A1–A8 + P6 全 PASS |
| TD-PLAN | **PASS** | `validate_project_state.py` = PROJECT STATE VALID；`render_project_views.py`（无 `--write`）= PROJECT VIEWS VALID；执行后无跟踪改动（结构通过不代表批准或 Git 证据有效，`plan.git.head_commit` 仍为 `2c827fb`，由协调器在 DONE 前更新） |

### TE-7 数据完整性对应表（`.pi/skills/data-integrity/SKILL.md`）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（真实 PostgreSQL 16.15） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| requirements rev11 §23.2；`docs/database/f026-cluster-authorization.md` v1（0015） | `POST /api/v1/users/{id}/cluster-authorizations` | 部分唯一索引 `uq_user_cluster_authorizations_user_id_cluster_id` + 单向触发器；**本次零 Schema 变更**（`backend/alembic` 空 diff、单 head 0015） | 唯一索引名精确匹配 → 409 `CONFLICT{already_granted}`；其它 IntegrityError 原样上抛 → 500 `INTERNAL_ERROR` | 双连接真并发、跨度相交（`overlap=True`），恰一方 201、另一方 409；ACTIVE=1/总行=1/Audit=1 | `targeted-two-new-cases.log`（attempt 1，attempts 1/5）；`full-pytest.log` |
| F026 §5 v3（非唯一完整性错误现状语义） | 同上 | FK `fk_user_cluster_authorizations_granted_by_users`（无变化） | 仅唯一索引名匹配时映射 409，其余上抛 | 真实 23503（幽灵 `granted_by`）→ 500 精确信封、零行/零 Audit；真实操作者同 pair 201 归因对照 | `test_grant_path_internal_error_envelope_end_to_end` 实跑通过（`targeted-two-new-cases.log`） |
| §22/§23.2 Audit 一致性 | 授予/撤销端点 | 同事务写入 `audit_logs` | 失败回滚零残留 | 500 路径无 Audit 残留；成功路径 Audit=1 `CREATE` | 同上（P9 A5/A6） |
| F027 范围/越权语义 | 全部业务路由 | — | 每请求 `get_access_scope` 解析，不缓存 | `real_scope` 守卫维持 `tests/integration`；无范围外静默 legacy 通过 | `test_f030_test_harness.py` 3 passed（含非空洞扫描）；`tests/smoke` scope 符号 0（`p8-rv10-guard.log`） |
| Migration / 已有数据影响 | — | 本次无 Migration：`backend/alembic` 空 diff、`alembic heads` 单 head 0015，无回填/回滚需求 | — | — | `p10-scope-nodrift.log`；session fixture 在 `csm_test` 上 `upgrade head` 成功（0001→0015 全链执行） |

### TE-8 数据库 / 接口 / 前端 / 集成结果

- **数据库**：真实 PostgreSQL 16.15（`csm_test@localhost:55432`）执行；无 Schema/Migration/索引/约束/触发器变更；`alembic heads` 单 head `0015_user_cluster_authorizations`；会话结束后 `public` 表数 0（fixture 清理口径，与 F030 一致，未据此声称读到 `alembic_version` 行）；superuser 角色使 V3b 用例按既有条件 skip（集合不变）。
- **接口**：无端点/参数/请求体/响应 Schema/错误码/reason/错误顺序/权限变化；T03 在真实 Contract 路由上验证 500 信封、零泄漏、零残留与真实操作者 201 归因；401 对照请求为真实未认证路径结果；用例本身绕过认证（override），**不作为 401/403 语义证据**。
- **前端**：`tsc --noEmit` 0 error、`vite build` 成功、`smoke:client` 328 passed；无状态机/API 调用/JSX 结构调整（空态文案 1 处 + 注释 1 处）；真实前后端集成按本合同无需新增（本 Feature 无 API 行为变化，写 NOT_REQUIRED，理由：仅文案/注释/测试修订，无契约与调用变更）。
- **集成/回归**：定向 29 + 全量 729/6 + 前端三项 + 计划双脚本；F030 范围以重跑覆盖。

### TE-9 Defects

| ID | Severity | Layer | Location | 证据 / 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F031-TEST1-01 | LOW | Backend 测试/环境（**F031 范围外，既有**） | `backend/tests/integration/test_f017_tester_acceptance.py::test_concurrent_revoke_yields_single_success` | run-1 全量失败一次：`outcomes == []`，线程内 `CheckViolation: ck_api_keys_revoked_after_created`（23514）；失败行 `created_at=03:25:03.336476Z`（create 事务 `now()`，`expires_at` 由其 +90d 推出）、`revoked_at=03:25:03.304899Z`（revoke 事务 `now()`）→ 后者早 31.6 ms。期望：两并发吊销恰一成功一 409。实际：双方 UPDATE 均违约，异常逸出线程 | 该用例为时钟敏感断言：`revoked_at`/`created_at` 各自取所在事务的 `now()`，在容器时钟步进/回拨（本环境 5 次采样漂移 ≈ 0.41→−3.92 ms）时「创建后立即吊销」可违约；隔离复跑 3/3 pass、同文件 15 passed，**与 F031 改动无交集**（`api_keys` 服务/模型/该测试均无 diff） | Backend（F017 归属）/ Coordinator 另立 follow-up | 否（不阻塞 F031；建议后续以单调时钟或放宽 CHECK 语义收敛） |
| F031-TD1-08 | NOTE | Test Design 口径 | TD-1 T4 / P1-A2 | TD-1「前 467 行 sha256 与 base 相同」与已签核设计 §3.1/§3.7 的「头部 +1 行指针」互斥，字面不可满足 | 无；本段以更强的逐 hunk 回放（去掉唯一插入行后与 base 逐字节相同）替代 | Tester（本报告已登记） | 否 |
| F031-TD1-09 | NOTE | Test Design 口径 | TD-1 P5-A3 | 「错误路径仅历史 1 处」实测 2 处（原文 1 + errata 引述 1） | 无；F030 原文区域仍为 1 处且逐字节保留 | Tester | 否 |
| F031-TD1-10 | NOTE | Test Design 口径 | TD-1 P3-A2 / P7-A2 | `handler's first step` 等在注释中被设计原文换行断词，字面 grep 会假阴性（TD-1 L3 已预警）；三处引用中仅两处含 `§17.1`（与设计 §3.7 原文一致） | 无；按拼接归一口径与设计原文逐字节比对通过 | Tester | 否 |
| F031-TEST1-02 | NOTE（CLOSED） | 文档署名 | `docs/features/F030/artifacts/p3-p6-static.log` errata 首行 | 原署名「Tester」已在候选 HEAD `137d8e6` 修正为「Coordinator」（符合设计 §5 L1 协调器独占）；本条 CLOSED | 无 | Coordinator | 否 |
| F031-TEST1-03 | NOTE | 测试过程 | 工作区 `artifacts/discarded/`（未入库） | 首次全量被我方并发用例的 session fixture（重建 `public`）干扰产生 4 个伪失败，已中止作废；run-1 的 F017 失败单独作废并隔离 | 无；最终判定仅基于干净的第 3 次全量运行 | Tester | 否 |

**无 BLOCKER / HIGH / 必须修复 MEDIUM；F031 范围内无实现缺陷。**

### TE-10 未验证项 / NOT TESTED

| 项 | 判定 | 原因 |
| --- | --- | --- |
| 真实浏览器 DOM/焦点/窄屏与面板端到端点选 | **NOT TESTED** | 沿用 F030 接受边界；本 Feature 只改空态文案与注释，无浏览器级行为变更 |
| ACTIVE > 2000 真机路径、并发压力测试、Compose 启动 | **NOT TESTED** | 架构 §6 明确不可声明；本 Feature 无相关变更 |
| T03 的 401/403 语义证据 | **NOT TESTED（明确不作证据）** | override 绕过认证；401 对照仅证明未 override 时走真实鉴权，403/422/404 顺序由既有 F002/F017/F027 用例覆盖 |
| F028 acceptance ×4 | **NOT TESTED（沿用既有 skip）** | 需 `F016_ACCEPTANCE=1`，skip 集合与基线一致；本 Feature 未启用 |
| `test_migrations.py` V3b superuser 分支 | **NOT TESTED（沿用既有 skip）** | 连接角色为 superuser；本 Feature 无 Migration |
| 整体项目验收（需求 §31–33 跨功能） | **NOT TESTED** | F031 为 ENABLER；`project.acceptance` 保持 PENDING，整体验收由协调器在 F031 完成后另启 |
| 前端真实 API 集成（本 Feature） | **NOT_REQUIRED** | 无契约/端点/调用变更，仅空态文案与注释 |

### TE-11 接受边界确认（RV-10，与 TD-1 T9 / architecture §3.8 一致）

- `real_scope` 守卫范围维持 `tests/integration`：`conftest.py:211` 的 legacy shim 仅在路径含 `tests/integration` 且无 `real_scope` marker 时生效；`tests/smoke` 不使用 scope 符号，未 override 时走真实依赖 → 不存在静默 legacy 通过。本次实测：`tests/smoke/` 相关符号命中 0，守卫 3 例（含非空洞扫描）通过。
- **Reopen 条件**：若未来 legacy shim 扩展到 `tests/integration` 以外，必须同步扩展守卫 `INTEGRATION_DIR` 与 AST 扫描范围；届时 F031 的接受边界失效，需重新评估。
- 其他边界照录：T03 绕过认证仅作 500 信封/零残留证据；空态按成因分文案不在本 Feature 范围；F030 test-report 历史措辞不改写（由本报告登记正确指向）。

### TE-12 Issues / Next

- 协调器：`git add -f docs/features/F031/artifacts/*.log`（不含 `discarded/`，作废运行不入库），提交本报告 TEST 段；F031 交 Reviewer；DONE 前更新 `plan.git.head_commit` 与 evidence 指针（`#test-executiontest-12026-10-23v1`）。
- 协调器/Architect：处置 `F031-TEST1-02`（errata 署名）；F034/后续 Feature 可考虑收敛 `F031-TEST1-01`（F017 时钟敏感并发用例）。
- 恢复 `project.acceptance=COMPLETE` 的口径需在 F031 完成后由协调器说明（`pending_reason` 已写明）。
- TD-1 的 `F031-TD1-04/05/06/07` 已在本次落实：55432 显式覆盖、`*.log` 需 `git add -f`、T03 采用 dependency override 主路径（未用测试专用路由）、acceptance 保持 PENDING。

### TE-13 结论

**Status：READY FOR REVIEW**

- P1–P10 共 60 项断言（7+6+5+5+5+5+5+4+10+8）全部 PASS（其中 3 项按书面 NOTE 采用更严格或更精确的等价口径，无证据强度下降）。
- 定向 29 passed、两新例 2 passed（`overlap=True`、`attempts used: 1/5`）、收集 734 + 1 module skip、全量 **729 passed / 6 skipped**（skip 集合不变）、前端 tsc/build exit 0 与 smoke 328 passed、计划双脚本 VALID。
- 无 BLOCKER / HIGH / 必须修复 MEDIUM；F031 范围内无实现缺陷，所有非阻塞观察均已登记 Owner，不改变 Contract / Schema / 权限 / 错误顺序。
- 本结论不批准合并；Review 与 DONE 由协调器按 `docs/project/git-workflow.md` 推进。

### TE-14 Evidence Index

| 文件 | 内容 |
| --- | --- |
| `artifacts/targeted-pytest.log` | 定向 3 文件 29 passed（51.89s） |
| `artifacts/targeted-two-new-cases.log` | 两新例 `-s` 输出：2 passed、`overlap=True`、`attempts used: 1/5`、真实 23503 服务端日志 |
| `artifacts/collect.log` | `--collect-only`：734 collected + 1 module skip（F016） |
| `artifacts/targeted-file-counts.log` | 定向文件级计数 15/11/3 |
| `artifacts/full-pytest.log` | 最终全量：729 passed / 6 skipped（1166.19s） |
| （作废日志） | 两次作废运行仅保留在工作区 `artifacts/discarded/`，**未入库**，不作为判定依据；正式判定见 `full-pytest.log` |
| `artifacts/f017-flake-rerun.log` | 该用例隔离复跑 3/3 pass |
| `artifacts/p8-guard-and-f017-file.log` | 守卫 3 passed（含非空洞）；F017 acceptance 文件 15 passed |
| `artifacts/frontend-typecheck.log` / `frontend-build.log` / `frontend-smoke.log` | tsc 0 error / build exit 0 / smoke 328 passed |
| `artifacts/p1-p5-p6-doc-diff.log` | P1/P5/P6 追加性、numstat、sha256、逐 hunk 回放 |
| `artifacts/p1-errata-signature.log` | §17.1 签名与实现逐参比对、§17.2 字面、17.3/17.4/17.5 关键词 |
| `artifacts/p2-rv04-copy.log` / `p2-rv04-wiring.log` | 新/旧文案 grep、基线同字面、diff 白名单、调用行 sha256、wiring |
| `artifacts/p3-rv05-comment.log` | AST sha256 相等、注释行白名单、token/旧短语归一比对、与设计 §3.3 逐字节相同 |
| `artifacts/p4-rv06-concurrency-static.log` | MAX_ATTEMPTS、无 skip/xfail、16 条 assert 多重集相等、DB 五项断言 |
| `artifacts/p5-rv07-static-log.log` | 前 37 行 sha256、errata 要素、路径计数、F030 test-report 空 diff、grep 复现 |
| `artifacts/p6-rv08-f026-header.log` | F026 `1 0`、头部行字节比对、其余 15 份空 diff、code/reason 计数 |
| `artifacts/p7-rv09-references.log` | 悬空引用 0、三处新引用、`await test(` 计数 328/328 |
| `artifacts/p8-rv10-guard.log` | 守卫文件/shim 条件、范围外 scope 符号 0 |
| `artifacts/p10-scope-nodrift.log` | 变更文件白名单、受保护目录空 diff、router 计数、权限 token、前端调用计数、需求空 diff、单 head |
| `artifacts/plan-validation.log` / `plan-f031-snapshot.log` | 计划双脚本 VALID；F031 字段与 `project.acceptance=PENDING` |
| `artifacts/environment.log` | PG 16.15 / Node v22.23.3 / Python 3.12.7 / 容器与端口 / superuser 说明 |
| `artifacts/clock-skew-evidence.log` | DB 与宿主时钟偏移采样（F017 flake 归因依据） |


### TE-15 F031 Review Follow-up Closeout（RV-03…RV-06，2026-10-23）

| ID | 处理 |
| --- | --- |
| F031-RV-03 | Evidence Index 已移除未入库的 `discarded/` 文件引用，并明确两次作废运行仅保留在工作区、不作为判定依据；正式判定依据 `full-pytest.log`（已入库）。 |
| F031-RV-04 | `F031-TEST1-02` 已标记 CLOSED：errata 署名已在 `137d8e6` 修正为 Coordinator。 |
| F031-RV-05 | `clock-skew-evidence.log` 追加 errata：`created_at`/`revoked_at` 均为 DB `func.now()`，非 app clock；F017 flake 归因方向不变。 |
| F031-RV-06 | `docs/api/F026.md` §5 证据行增列 F031 T03 端到端用例（真实 Contract 路径 + 真实 FK 23503 → 500 信封、零残留；不作为 401/403 证据）。 |
