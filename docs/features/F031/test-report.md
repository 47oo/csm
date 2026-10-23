# F031 F030 Review 非阻塞项收尾 — Test Report

> 本文件同一份报告承载 TEST_DESIGN 与 TEST 两阶段，分开记录版本与结论。
> 当前只有 TEST DESIGN。**TEST DESIGN READY 仅表示方案可验证，不是测试通过，不批准实现或合并。**

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
