# Review Report — F009 Cluster 视角资源查询

> Reviewer Role: reviewer（独立审查）
> Date: 2026-09-18
> Feature: F009（E05，P0，`depends_on: [F001, F002]`，二者均已 DONE）
> Feature Branch: `feature/F009-cluster-resource-view`
> Base Branch: `develop` @ `c6565545286bcabd4984de549dec13122941ed3e`
> start_commit: `c6565545286bcabd4984de549dec13122941ed3e`
> 已审查 HEAD: `ac693d71084e80fd55c0d29fe2165453bd6f7a0d`
> merge-base(develop, HEAD): `c6565545286bcabd4984de549dec13122941ed3e`（与 start_commit、base 一致，祖先关系成立）
> Test Report: `docs/test-reports/f009-cluster-resource-view.md`（`READY FOR REVIEW`）

## Feature

Cluster 视角资源查询（F009）— 在 F002 已有的「按 Cluster 限定读取 BareMetal」能力之上，
交付 ADR-0003 §2 已确认、F001 / F002 均排除并指向 F009 的**只读名称别名**
`GET /api/clusters/by-name/{cluster_name}/bare-metals`，并把「Cluster 不存在 / 已删 → `404`」
与「Cluster 存在但无活跃成员 → `200` Empty」的一致性、软删过滤复用，以及
「不越界到 NIC / IP / VM / Container / Service」落成可审查的 guard 与测试。
F009 不新增领域对象 / 字段 / 关系 / 状态，不新增第二套前端视图，无数据库变更。

## Review Status

**APPROVED WITH FOLLOW-UP**

可进入 Merge Gate。不存在 BLOCKER / HIGH / 需在当前 Feature 修复的 MEDIUM；AC-01 ~ AC-18
全部满足；测试经 Reviewer 独立复跑可信；实现未超范围。仅存 1 条 LOW 与若干 NOTE 级
Follow-up（见 Findings），均不阻塞合并。

## Scope Reviewed

**独立复现的 Git 证据**

```text
git branch --show-current                 → feature/F009-cluster-resource-view
git status --short                        → （空；工作区 clean）
git rev-parse HEAD                        → ac693d71084e80fd55c0d29fe2165453bd6f7a0d
git rev-parse develop                     → c6565545286bcabd4984de549dec13122941ed3e
git merge-base develop HEAD               → c6565545286bcabd4984de549dec13122941ed3e（== base == start_commit）
git log --oneline develop..HEAD           → 7 提交
    ac693d7 test(F009): add acceptance and regression coverage
    0fd601d chore(F009): record the implementation checkpoint
    07b656d feat(F009): implement the cluster member read alias
    0959638 docs(F009): define architecture and API contract
    ba44ff2 docs(F009): fix duplicated acceptance criteria in the plan
    d2faf09 docs(F009): define requirements
    96cd19f chore(F009): initialize feature branch
git diff --stat develop...HEAD            → 14 files changed, 1986 insertions(+), 9 deletions(-)
git diff --cached --stat                  → （空）
git ls-files --others --exclude-standard  → （空）
git diff develop...HEAD -- backend/migrations/   → （空）
```

候选实现（`07b656d`）与测试（`ac693d7`）均已提交，工作区 clean、无未跟踪交付物，
Test Report 与 Test Handoff 就绪，满足正式 Review 的 Gate 前提，**非 PARTIAL REVIEW**。

**实际检查范围**

- 完整分支差异 `git diff develop...HEAD`（14 文件）：Backend、测试、契约与架构 / 产品交接、
  测试报告、项目计划、README。无前端实现、无迁移、无依赖文件。
- `backend/app/cluster_views/{__init__,router,service}.py`、`backend/app/main.py`、
  `tests/test_auth_guards.py`、`tests/test_cluster_views_api.py`、`tests/test_cluster_views_guards.py`、
  `frontend/tests/f009ClusterResourceView.spec.ts`。
- 被复用的既有实现（只读核对，非变更）：`app/clusters/{service,repository,validation}.py`、
  `app/bare_metals/{service,router}.py`、`app/db/active.py`、`app/common/pagination.py`、
  `app/models/cluster.py`、`tests/deletion_guard_helpers.py`。
- 契约与文档：`docs/api/f009-cluster-resource-view.md`、`docs/api/{api-conventions,f001-cluster,f002-bare-metal}.md`、
  ADR-0003 / ADR-0004 / ADR-0005、`docs/product/handoffs/f009-cluster-resource-view.md`、
  `docs/architecture/f009-cluster-resource-view-handoff.md`、`docs/project/v1/project-plan.yaml`、README。

**独立复跑的测试 / 门禁证据（Reviewer 亲执行，非引用 Tester 结论）**

```text
# 复用本机 pgserver PostgreSQL 16.2 实例（/tmp/csm_review_pgdata），新建独立库 csm_review_f009
CSM_TEST_DATABASE_URL=.../csm_review_f009 pytest tests/test_cluster_views_api.py \
    tests/test_cluster_views_guards.py tests/test_auth_guards.py -q
  → 46 passed, 2 warnings（无 skipped）
CSM_TEST_DATABASE_URL=.../csm_review_f009 pytest -q
  → 311 passed, 2 warnings in 182.67s（无 skipped；含 F001/F002/F012/F013/F014/F015 既有测试）
.venv/bin/ruff check backend tests     → All checks passed!（exit 0）
.venv/bin/ruff format --check backend tests → 90 files already formatted
cd frontend && npm run test            → Test Files 16 passed (16)，Tests 176 passed (176)
cd frontend && npm run typecheck       → exit 0
```

**未审查内容**：见 Unreviewed Areas。

## Product Compliance

对照 `docs/product/handoffs/f009-cluster-resource-view.md`（AC-01 ~ AC-16）与
`docs/project/v1/project-plan.yaml > F009.acceptance_criteria`（AC-01 ~ AC-18）。

| AC | 结论 | 独立核对依据 |
|---|---|---|
| AC-01 Cluster 视角可见其下活跃 BareMetal | PASS | `test_t01` alias 返回 2 台、`total==2`；入口 T-FE-10 |
| AC-02 hostname + status 非空且属封闭集合 | PASS | `test_t02`；`VALID_STATUSES == {IDLE,ALLOC,DOWN,UNKNOWN}` |
| AC-03 只含本 Cluster | PASS | `test_t03`；`cluster_id` 唯一 |
| AC-04 状态修改后反映最新值 | PASS | `test_t04` PATCH→DOWN，其他不变 |
| AC-05 中文往返 | PASS | `test_t05`（Cluster 名 + hostname 百分号编码） |
| AC-06 不存在 → 404，不得 200 空集 | PASS | `test_t06`；`details==[]`；`"items" not in text` |
| AC-07 已软删 Cluster 同为 404 | PASS | `test_t07`（绕过应用层直插 `deleted_at`） |
| AC-08 存在无成员 → 200 Empty | PASS | `test_t08`/`test_t09` |
| AC-09 Empty / Not Found / Error 界面互异 | PASS | T-FE-09 三态标记独立断言 |
| AC-10 Empty 不是错误、不触发全局 401 | PASS | T-FE-09 `unauthenticated not.toHaveBeenCalled()` |
| AC-11 已软删 BareMetal 不出现 | PASS | `test_t11`（绕应用层预置） |
| AC-12 软删后从视图消失、其余不变 | PASS | `test_t12`（Cluster 行快照前后一致） |
| AC-13 无 restore / undelete / include_deleted | PASS | `test_t13` + T-FE-11 |
| AC-14 无 NIC/IP/VM/Container/Service 越界 | PASS | G-009-2 / G-009-6 |
| AC-15 无 Cluster 状态 / 位置 / 自动发现字段 | PASS | G-009-3 / G-009-4 |
| AC-16 未认证 → 401 且无数据 | PASS | `test_t14` |
| AC-17 alias 与 canonical 同一结果集 | PASS | `test_t01`/`test_t17`（`alias.json()==canonical.json()`）；G-009-3 schema 相等 |
| AC-18 边界封闭 / 软删单一路径 | PASS | G-009-1 ~ G-009-6 |

**范围控制**

- 未越界：OpenAPI 全路径无 NIC / IP / VM / Container / Service token（G-009-2 复核通过）；
  `cluster_views` 源码无 Cluster 状态 / DataCenter / 位置 / 自动发现字段（G-009-4 复核通过）。
- 未新增领域对象 / 字段 / 关系 / 状态：`BareMetalRead` 仍恰 13 字段、无 `deleted_at`（G-009-3）。
- 未重复实现前端视图：`frontend/src/**` 零改动（`git diff --stat` 确认），前端义务仅为回归测试。
- 未新增 Cluster 状态 / 计数汇总（NQ-1 / PROPOSED-1 明确不实现）。

**产品结论**：AC-01 ~ AC-18 全部满足，无越界、无未经确认能力、无 Scope Creep。

## Architecture Compliance

- 交付面与 Architecture Handoff 一致：只新增 `backend/app/cluster_views/`（`router.py` + `service.py`）
  与一条只读别名路由，`main.py` 以 `/api` 挂载，F013 中间件自动覆盖，无白名单。
- **判定顺序（REQUIRED #2）成立**：`service.py` 先 `clusters.service.get_cluster_by_name`
  （未命中 / 已删 → `NotFoundError` → 404），后委托 `bare_metals.service.list_bare_metals(cluster_id=...)`
  （其内部再次执行父活跃复检；空 → 200 Empty）。
- **契约等价（REQUIRED #3）**：alias 与 canonical 均返回 `Page[BareMetalRead]`；G-009-3 断言
  OpenAPI 200 content schema 相等，`test_t01`/`test_t17` 深等。
- 名称解析复用 F001 的 `get_active_by_name`（`select_active(Cluster).where(Cluster.name == name)`）：
  字面值、大小写敏感、仅活跃，未命中 → 404。与 ADR-0003 §2 一致。
- 无新框架 / 新依赖 / 新中间件 / `vue-router`；`frontend/package.json`、`pyproject.toml` 零改动。
- 只读无副作用：`cluster_views` 模块仅做查询，无任何写语句。

## Database Review

- **无数据库变更**：`git diff develop...HEAD -- backend/migrations/` 为空；无新表 / 列 / 索引 /
  约束 / CASCADE / 触发器 / `COLLATE`。`project-plan.yaml > F009.layers.database == false` 属实。
- 复用既有索引：名称解析走 `ux_clusters_name_active`（partial unique `WHERE deleted_at IS NULL`）；
  成员读取走 `ix_bare_metals_cluster_id` / `ux_bare_metals_cluster_hostname_active`。
- 名称寻址安全性（§22 / §12）：`ck_clusters_name_no_slash`（DB 最终权威）+
  `app/clusters/validation.py` 双双禁止名称含 `/`，故 `{cluster_name}` 恒为单个 URL 路径段，
  契约 §3.4 的「路径不会因名称而分段错乱」成立；中文 / 保留字符按 RFC 3986 百分号编码往返
  经 `test_t05` 验证。未发现 Path Identifier 字符集问题，无需 PRODUCT DECISION。
- 未把任何 PROPOSED / OPEN 规则静默实现为数据库强约束。

## Backend Review

- 职责边界清晰：Router（HTTP 装配）→ Service（判定顺序 + 委托）→ 复用既有领域服务；
  无业务逻辑堆入 Router，无重复查询谓词，无无意义抽象。
- **软删单一路径（ADR-0004 / REQUIRED #1）**：
  - `cluster_views` 模块**不含**任何 `deleted_at` 表达式（G-009-5 `scan_deleted_at_writes == {}`）。
  - 成员读取**委托** `list_bare_metals`，与 canonical 共用同一 `active_filter` / `select_active`；
    未出现第二条软删过滤或写入路径。
  - 全局 `deleted_at` 写入 allow-list 仍恰为 `{backend/app/deletion/service.py}`
    （`test_g009_5_global_deleted_at_write_allowlist_unchanged` 复核通过）。
- 错误语义正确区分：不存在 / 已删 → 404 `NOT_FOUND`；存在无成员 → 200 Empty；
  非法分页 → 400 `VALIDATION_ERROR` + `details[].field`；未认证 → 401 `UNAUTHENTICATED`。
- 事务边界复用既有 `get_db_session`；读取不写、无需加锁，符合契约 REQUIRED #3。
- 路由无歧义：`/clusters/by-name/{cluster_name}`（F001）与
  `/clusters/by-name/{cluster_name}/bare-metals`（F009）段数不同，Starlette 精确匹配不冲突。
- 无 SQL 注入风险（全部经 SQLAlchemy 参数化；`cluster_name` 仅作等值参数）。

## Frontend Review

- `frontend/src/**` 零改动：F009 复用 F002 已交付的 `clusterId` 限定 `BareMetalListPage`，
  未新建第二套 Cluster 视角视图。
- 唯一前端变更 `frontend/tests/f009ClusterResourceView.spec.ts`：T-FE-09（Empty / Not Found /
  Error 三态互异 + Empty 不触发全局 401）、T-FE-10（Cluster 详情入口 emit）、
  T-FE-11（无恢复入口 token）。
- 严格按 `error.code` 分支渲染（`data-error-code`），未解析 `message`；Empty 与 Error 未混淆。
- 无新增依赖、无越界 CRUD、无领域状态错误展示。

## Test Review

- **覆盖度**：AC-01 ~ AC-18 逐条有对应测试（`tests/test_cluster_views_api.py` T-01 ~ T-17、
  `tests/test_cluster_views_guards.py` G-009-1 ~ G-009-6、前端 T-FE-09 ~ T-FE-11），
  且含负向断言（`"items" not in text`、`requestBody` 缺失、参数集合封闭）。
- **真实性**：Reviewer 独立复跑后端全量 311 passed、F009 专项 46 passed、前端 176 passed，
  无 skipped，与 Tester 结论一致。
- **未迎合实现**：深等断言 `alias.json()==canonical.json()` 对照真实响应，而非实现内部状态；
  软删场景**绕过应用层**直插 `deleted_at`，不复制业务规则。
- **Guard 可失败性**：G-009-1 ~ G-009-6 逻辑均可由 Tester 的对抗注入（逐字节还原）证明会失败；
  Reviewer 复核其判定机制（路由集合相等 / OpenAPI schema 相等 / AST 写入扫描 / allow-list）
  确属真实断言，非空壳。
- **既有断言未被削弱**：`tests/test_auth_guards.py::EXPECTED_GET_ROUTES` 仅**追加**一行
  （`git diff` 确认 +2 行、无删除）；`test_g_f_only_read_only_get_routes` 仍断言实际路由
  == EXPECTED_GET_ROUTES；`test_deletion_guards.py` / `test_bare_metals_guards.py` /
  `test_structure_guard.py` 原样保留。F001/F002/F012/F013/F014/F015 既有测试全绿。
- 无执行顺序依赖、无真实数据库约束的伪造通过（数据库级断言经真实 psycopg 直连）。

## Findings

### REV-F009-1

```text
Severity: LOW
Layer: Project Plan / Git metadata
Location: docs/project/v1/project-plan.yaml > features[F009].git.head_commit
Problem: head_commit 被记录为 c656554（== base == start_commit），未反映当前已审查 HEAD
         ac693d7。对比其它 Feature（F001/F012/F013/F014/F015）的 head_commit 均指向
         真实实现 / 测试 HEAD。
Evidence: 计划文件 F009.git = { start_commit: c656554..., head_commit: c656554..., merge_commit: null }；
          实际 git rev-parse HEAD = ac693d7...。
Impact: 仅影响计划元数据准确性；不改变已审查范围（本次 Review 以显式提供的 base/start/HEAD
        为准并已独立核验祖先关系），不阻塞 Merge。
Expected: 在 merge 后的 DONE 步骤把 F009.git.head_commit 更新为最终 HEAD 并回填 merge_commit
          （与既有 DONE Feature 的元数据惯例一致）。
Suggested Owner: Coordinator / Architect
```

### REV-F009-2

```text
Severity: NOTE
Layer: Contract / Traceability
Location: docs/product/handoffs/f009-cluster-resource-view.md vs docs/project/v1/project-plan.yaml > F009
Problem: 产品交接定义 AC-01 ~ AC-16；项目计划新增 AC-17（alias 等价）与 AC-18（边界封闭），
         本次任务按 AC-01 ~ AC-18 描述。
Evidence: 两文档 AC 编号不一致；计划 AC-17/18 内容为既有 R-QUERY-004 / ADR-0003 §2 / guard 的
          重述，未引入新需求。
Impact: 无产品缺口，仅追踪口径差异。
Expected: 无需在当前 Feature 修改；后续如需统一，可在计划中标注 AC-17/18 为「别名/边界」派生项。
Suggested Owner: Architect / Product Manager
```

### REV-F009-3

```text
Severity: NOTE
Layer: Test / Guard maintainability
Location: tests/test_cluster_views_guards.py（G-009-3 十三字段锁定；G-009-2 / G-009-4 token 子串匹配）
Problem: G-009-3 把 BareMetalRead 恰锁定为 13 字段；G-009-2 / G-009-4 以子串匹配 token 列表。
Evidence: BARE_METAL_READ_FIELDS 常量、BOUNDARY_TOKENS / FORBIDDEN_FIELD_TOKENS 元组。
Impact: 未来若合法地为 BareMetal 增字段或向 cluster_views 增代码，这些 guard 会失败，需显式更新；
        属「强制显式变更」的有意设计，非缺陷。
Expected: 保持现状；未来扩展时同步评审并更新对应 guard。
Suggested Owner: Architect / Backend
```

### REV-F009-4

```text
Severity: NOTE
Layer: Backend / Contract
Location: app/clusters/repository.py::get_active_by_name（F001，F009 复用）
Problem: 大小写敏感名称解析依赖数据库默认 collation，而非显式 COLLATE。
Evidence: 契约 f009 §3.1 / f001 §3.4 要求大小写敏感；测试环境 collation 为 zh_CN.UTF-8（实测
          'abc' = 'ABC' → false）。ADR-0003 明确不新增 COLLATE。
Impact: 若生产库使用非确定性 / 大小写不敏感 collation，可能出现非预期命中。此为 F001 既有约束，
        非 F009 引入，且 ADR 已固化为「不新增 COLLATE」。
Expected: 保持 ADR 决策；部署侧应确保使用的 collation 与 ADR-0003 假设一致（F015 部署范畴）。
Suggested Owner: Architect / Deployment
```

### REV-F009-5

```text
Severity: NOTE
Layer: Backend
Location: backend/app/cluster_views/service.py::list_cluster_bare_metals_by_name
Problem: 命中路径执行两次父 Cluster 活跃查询（get_cluster_by_name + list_bare_metals 内部复检）。
Evidence: service.py 两处调用；list_bare_metals 内部 select_active(Cluster) 复检。
Impact: 一次额外只读查询，成本可忽略。
Expected: 保持现状——该冗余是 REQUIRED #2 为换取并发稳定性与 404-vs-Empty 一致性的有意取舍。
Suggested Owner: Backend / Architect
```

## Existing Defects

Tester 报告 `Defects: None`。Reviewer 逐项复核：

- 报告中的「测试过程观察」（首次全量 pytest 与对抗注入并行时 `test_lint.py` 一度失败，还原后
  2 passed / 全量 311 passed）审定为**测试编排自干扰**，非代码缺陷；Reviewer 在干净工作区
  独立复跑全量 311 passed，未复现。
- 严重程度评估：无 DEFECT 需要重新分级。Tester 的 PASS 与无缺陷结论经独立复跑与代码核对**成立**。

## Non-blocking Follow-ups

1. REV-F009-1：merge 后 DONE 时更新 `project-plan.yaml > F009.git.head_commit` / `merge_commit`。
2. REV-F009-3 / REV-F009-4 / REV-F009-5：保持现状，仅在后续 Feature 扩展时留意 guard 更新、
   部署 collation 假设与两查一问的取舍。
3. 并发软删竞态与浏览器级 E2E（Tester 已声明 Unverified）：本次以静态结构 + 软删读取路径 +
   真实前后端集成为证；属低风险，可作为后续增强，不阻塞本 Feature。

## Unreviewed Areas

- 真实浏览器级 E2E / 视觉 / DOM 渲染（无浏览器自动化环境；前端以 vitest + happy-dom 组件测试
  与真实 API client 集成覆盖）。
- 并发软删的逐时刻交错压测与多 worker / 跨进程并发（无专用夹具；读取不写、无锁需求）。
- `by-name` 空名称段 / 缺失段边界（架构 OPEN，不属任何 AC）。
- 生产部署环境的实际 collation（见 REV-F009-4）。

## Verdict

**APPROVED WITH FOLLOW-UP**

- 不存在 BLOCKER / HIGH / 必须在当前 Feature 修复的 MEDIUM。
- 核心验收标准 AC-01 ~ AC-18 全部满足。
- 测试可信（Reviewer 独立复跑：后端 311 / F009 专项 46 / 前端 176，无 skipped）。
- 实现未超范围，无数据库变更，软删单一路径与 guard 演进均成立。
- 唯一 LOW（REV-F009-1）为计划元数据，可在 merge 后的 DONE 步骤处理，不阻塞 Merge Gate。

可进入 Merge Gate。

GIT: NONE
