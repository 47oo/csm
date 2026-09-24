# Test Report — F009 Cluster 视角资源查询

> Status: **READY FOR REVIEW**
> Author Role: tester
> Date: 2026-09-18
> Feature: F009（E05，P0，`depends_on: [F001, F002]`，二者均 DONE）
> 分支：`feature/F009-cluster-resource-view`
> base `develop` = `c6565545286bcabd4984de549dec13122941ed3e`
> 实现 HEAD = `07b656db8244828f3b11163471cf9ec0111c4eb6`（其后 `0fd601d` 为计划元数据检查点）
> layers：database=false / backend=true / frontend=false；contract READY、backend COMPLETE、test PENDING

---

## Feature

Cluster 视角资源查询（F009）— 在 F002 已有的「按 Cluster 限定读取 BareMetal」能力之上，交付 ADR-0003 §2 已确认但尚无认领者的只读名称别名 `GET /api/clusters/by-name/{cluster_name}/bare-metals`，并把「Cluster 不存在/已删 → 404」与「Cluster 存在但无活跃成员 → 200 Empty」的一致性、软删过滤复用、以及「不越界到 NIC/IP/VM/Container/Service」落成可审查的 guard 与测试。F009 不新增领域对象 / 字段 / 关系 / 状态，不新增第二套前端视图。

## Test Basis

- `AGENTS.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/handoffs/f009-cluster-resource-view.md`（Product Handoff，`READY FOR ARCHITECT`，AC-01 ~ AC-16 + 假设 / NQ-1 ~ NQ-5）
- `docs/architecture/f009-cluster-resource-view-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，Test Work T-01 ~ T-17 / G-009-1 ~ G-009-6 / T-FE-09 ~ T-FE-11、REQUIRED、Constraints）
- `docs/api/f009-cluster-resource-view.md`（API 契约 **READY**，F009 唯一权威）、`docs/api/f002-bare-metal.md` §2/§3.2、`docs/api/f001-cluster.md`、`docs/api/api-conventions.md`
- ADR-0003 / ADR-0004 / ADR-0005（均 `ACCEPTED`）
- `docs/project/v1/project-plan.yaml > F009`（18 条 acceptance_criteria，即本报告 AC-01 ~ AC-18）
- 报告格式先例：`docs/test-reports/f002-bare-metal.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f009-test/pgdata`，本次新建） |
| collation | `zh_CN.UTF-8` / `zh_CN.UTF-8`；实测 `'abc' = 'ABC'` → `false`（**大小写敏感**，满足 T-10 前提） |
| 测试库 | `csm_f009`（pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 重建）、`csm_mig`（迁移 / 直连 schema 检查）、`csm_api`（真实 uvicorn + 前端真实 client 集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn`（真实 PG `csm_api`）：`127.0.0.1:8797` |
| Node / npm | v24.14.0 / 11.9.0（Vite 7.3.6，Vitest 5.0.1，happy-dom） |
| ruff / psycopg | 0.16.7 / 3.3.5 |
| 前端测试 | `npm run typecheck` / `npm run test` / `npm run build` |

**是否全新**：PG 实例、三个测试库、管理员账号、集成探针均为本次测试新建；pytest 每次从空库重建。实现方结论**未被复用** —— 下表所有结果均来自本次独立执行（实现方 `311 passed` 与本次独立重跑一致，但结论以本次执行为准）。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量测试（独立重跑，无 skip 伪造）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f009?host=/tmp/f009-test/pgdata" \
  .venv/bin/python -m pytest -q
311 passed, 2 warnings in 201.05s

F009 专项子集（API + 静态 guard + 既有 auth guard）：
$ .venv/bin/python -m pytest tests/test_cluster_views_api.py \
    tests/test_cluster_views_guards.py tests/test_auth_guards.py -q
46 passed, 2 warnings in 21.99s
```

无 `skipped`。既有 F001/F002/F012/F013/F014/F015 全部保持通过。

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 90 files already formatted  exit 0
```

### 3. 迁移与 Schema（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head → 0001_f012_baseline → 0002_f013_auth → 0003_f002_bare_metals
$ alembic current      → 0003_f002_bare_metals (head)
$ alembic check        → No new upgrade operations detected.（无漂移）
$ git diff base..HEAD -- backend/migrations/ → 空（0 行；database=false 无迁移）
```

直连 `information_schema` / `pg_indexes` / `pg_constraint`：

```text
tables: ['alembic_version', 'bare_metals', 'clusters', 'sessions', 'users']  （无新表）
ix_bare_metals_cluster_id            btree(cluster_id)
ux_bare_metals_cluster_hostname_active UNIQUE(cluster_id, hostname) WHERE deleted_at IS NULL
ux_clusters_name_active              UNIQUE(name) WHERE deleted_at IS NULL
deleted_at 列: bare_metals, clusters（无新增）
约束: ck_bare_metals_status / ck_clusters_name_no_slash / fk_bare_metals_cluster / pk_*（无变更）
```

索引访问路径（`SET enable_seqscan=off`）：

```text
名称解析 → Index Scan using ux_clusters_name_active (name = 'cluster-a')
成员读取 → Index Scan using ux_bare_metals_cluster_hostname_active (cluster_id = N)
```

### 4. 真实后端 HTTP 集成（真实 uvicorn + 真实 PG，原始 httpx）

```text
$ .venv/bin/python /tmp/f009-test/integration.py → 35/35 passed
覆盖：未认证 401（且无 items）/ 登录 200 / alias 200 / alias 与 canonical 深等 /
  信封键恰 {items,total,page,page_size} / total==2 / id 升序 / 字段集合恰 13 且无 deleted_at /
  status 非空属于封闭集合 / 只含本 Cluster / 大小写敏感命中与未命中 404 /
  不存在 → 404 不得 200 空集 / 存在无成员 → 200 items==[] 无 error /
  已软删 Cluster（绕过应用层置 deleted_at）alias 与 canonical 均 404 /
  已软删 BareMetal 被排除 / DELETE 204 后消失 / 非法 page/page_size → 400 + details[].field /
  OpenAPI alias 200 schema == canonical 200 schema / GET 前后 status+updated_at 不变（只读无副作用）/
  中文名称百分号编码往返 / 无 restore/undelete/include_deleted 路由 / PATCH 后 status 反映最新事实
```

### 5. 真实前后端集成（**前端真实 API client** + 真实 uvicorn + 真实 PG；临时 vitest 探针，运行后已删除）

使用 `frontend/src/api/auth.ts::login`、`src/api/bareMetals.ts::listBareMetals`/`createBareMetal`、`src/api/clusters.ts::createCluster`、`src/api/http.ts::ApiError`，经 happy-dom 同源（`http://127.0.0.1:8797`）管理真实 HttpOnly 会话 Cookie：

```text
$ npx vitest run tests/zzTmpF009Integration.spec.ts → Test Files 1 passed | Tests 4 passed
- 未认证 listBareMetals({clusterId}) → ApiError{status:401, code:'UNAUTHENTICATED'}
- login → 200（username='tester'）
- 存在无成员 Cluster → 200 + items==[] + total==0（Empty，不抛错）
- 不存在 Cluster → ApiError{status:404, code:'NOT_FOUND'}（与 Empty 不同）
- 有成员 Cluster → total==2，每条 hostname 为 string、status ∈ 封闭集合
```

探针文件 `frontend/tests/zzTmpF009Integration.spec.ts` 与临时 Python 脚本运行后已删除（见「新增/修改文件」）。

### 6. 对抗注入（证明 guard 真实可失败，逐字节还原）

对 G-009-1 ~ G-009-6 逐条注入，运行对应 guard，确认 FAILED，再以备份逐字节还原（`sha256sum -c` 全部「成功」）：

| 注入 | 目标 guard | 结果 |
|---|---|---|
| 从 `test_auth_guards.py::EXPECTED_GET_ROUTES` 删除 alias 路径 | G-009-1 | **FAILED**（`1 failed`） |
| 向 `cluster_views/router.py` 追加 `GET /virtual-machines` 越界路由 | G-009-2 / G-009-6 | **FAILED**（两条 guard 均 `1 failed`） |
| 把 alias `response_model` 由 `Page[BareMetalRead]` 改为 `list[BareMetalRead]` | G-009-3 | **FAILED** |
| 在 `cluster_views/service.py` 注入 `rack` 字段 token | G-009-4 | **FAILED** |
| 在 `cluster_views/service.py` 注入 `deleted_at` 写入表达式 | G-009-5 | **FAILED** |

还原校验：

```text
$ sha256sum -c /tmp/f009-test/bak/orig.sha256
backend/app/cluster_views/router.py: 成功
backend/app/cluster_views/service.py: 成功
tests/test_auth_guards.py: 成功
$ git status --short → 仅 1 个新增测试文件（无生产代码改动）
```

### 7. 前端

```text
$ cd frontend && npm run typecheck → exit 0
$ npm run test → Test Files 16 passed (16)，Tests 176 passed (176)
                 （171 既有 + 本次新增 frontend/tests/f009ClusterResourceView.spec.ts 5 个）
$ npm run build → vue-tsc 通过 + vite build 成功
                  dist/assets/index-Vga-AvX0.js 1,033.95 kB（仅 chunk 体积告警）
```

---

## Acceptance Criteria Mapping

AC 编号采用 `docs/project/v1/project-plan.yaml > F009.acceptance_criteria` 顺序（18 条）。

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** Cluster 视角可见其下活跃 BareMetal 清单及状态 | T-01 + 真实 HTTP + 前端 client | **PASS** | 2 台机器均在 alias 结果内；`total==2`；前端 client `total==2` |
| **AC-02** 每条含 hostname 与 status，非空且属封闭集合 | T-02 + 真实 HTTP | **PASS** | `hostname` 非空 string；`status ∈ {IDLE,ALLOC,DOWN,UNKNOWN}` 且非 `null` |
| **AC-03** 只含本 Cluster，不含其他 Cluster | T-03 + 真实 HTTP | **PASS** | `cluster-a` 只返回 `a1`，`cluster-b` 只返回 `b1`；`cluster_id` 一致 |
| **AC-04** 状态修改后重新查询可见最新值 | T-04 + 真实 HTTP | **PASS** | `PATCH DOWN` 后目标 `status=='DOWN'`，其他机器仍 `IDLE` |
| **AC-05** 中文名称 / hostname 字面往返 | T-05 + 真实 HTTP | **PASS** | 「高性能计算集群-A」/「计算节点-甲」百分号编码往返逐字节一致 |
| **AC-06** 不存在 → 404，不得 200 空清单；界面不渲染为「暂无机器」 | T-06 + 真实 HTTP + T-FE-09 | **PASS** | `404 NOT_FOUND`、`details==[]`、无 `items`；组件 404 → `data-state=error` + `data-error-code=NOT_FOUND`「未找到资源」 |
| **AC-07** 已软删 Cluster 同为 404 | T-07 + 真实 HTTP + 直连预置 | **PASS** | 绕过应用层置 `deleted_at` → alias 与 canonical 均 `404 NOT_FOUND` |
| **AC-08** 存在但无活跃 BareMetal → 200 空集 Empty | T-08 + T-09 + 真实 HTTP + T-FE-09 | **PASS** | `200 {items:[],total:0}`，无 `error`；前端 `data-state=empty`「该集群暂无裸金属」 |
| **AC-09** Empty / Not Found / Error 界面互不相同 | T-FE-09（新增回归）+ 既有 `bareMetalListPage.spec.ts` | **PASS** | `empty` / `error(NOT_FOUND)` / `error(INTERNAL_ERROR)` 三态标记与文案互相独立断言 |
| **AC-10** Empty 不呈现错误、不触发全局会话失效 | T-FE-09 | **PASS** | Empty 无 `[role=alert]`；注册的全局未认证处理器 `not.toHaveBeenCalled()` |
| **AC-11** 已软删 BareMetal（绕应用层）不出现 | T-11 + 真实 HTTP + 直连预置 | **PASS** | 预置 `deleted_at` 行后 alias 与 canonical 均 `total==1`，仅活跃那台 |
| **AC-12** 软删某 BareMetal 后不再出现，其余不受影响 | T-12 + 真实 HTTP | **PASS** | `DELETE 204` 后 `total` 减 1、被删 id 消失；Cluster `name/created_at/updated_at/deleted_at` 全不变 |
| **AC-13** 无 restore / undelete / include_deleted / 回收站入口或参数 | T-13 + T-FE-11 | **PASS** | OpenAPI `/api/clusters*` 无匹配路由；alias 无删除相关参数；前端源码扫描无越界 token |
| **AC-14** 无 NIC / IP / VM / Container / Service 列表 / 计数 / 占位 / 关系入口 | T-13 + G-009-2 + G-009-6 + OpenAPI 检查 | **PASS** | 全部 OpenAPI path 无边界 token；alias 路由集合恰 1 条；`cluster_views` 模块无相关 token |
| **AC-15** 无 Cluster 状态 / DataCenter / 位置 / 自动发现字段 | G-009-3 + G-009-4 + OpenAPI 检查 | **PASS** | `BareMetalRead` 恰 13 字段；alias 参数恰 `{cluster_name,page,page_size}`、无 `requestBody`；源码无越界字段 token |
| **AC-16** 未认证 → 401 UNAUTHENTICATED 且无资源数据 | T-14 + 真实 httpx + 前端 client | **PASS** | `401 UNAUTHENTICATED`；响应无 `items`；前端 `ApiError{status:401,code:'UNAUTHENTICATED'}` |
| **AC-17** alias 与 canonical 同一结果集（同字段 / 同排序 / 同分页信封）；名称不存在/已删 → 404；无活跃成员 → 200 Empty；大小写敏感；未认证 → 401 | T-01 / T-06 / T-08 / T-10 / T-16 / T-17 + 真实 HTTP + OpenAPI | **PASS** | `alias.json()==canonical.json()`；`id` 升序；OpenAPI 200 schema 相等；大小写命中/未命中；404 vs 200 Empty；401 |
| **AC-18** 边界封闭：端点集合恰 1 条；软删过滤仍恰 1 条写入路径与统一读取原语（G-009-1 ~ G-009-6） | G-009-1 ~ G-009-6 + 对抗注入 | **PASS** | 6 条 guard 全部存在且经注入证明真实可失败；`cluster_views` 无 `deleted_at` 写入（AST Name/attr 节点为 0）；全局 allow-list 未变 |

**说明**：AC-01 ~ AC-18 全部有结果，**无 FAIL、无 BLOCKED、无 NOT TESTED**。

---

## Test Work 覆盖（T-01 ~ T-17 / G-009-1 ~ G-009-6 / T-FE-09 ~ T-FE-11）

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | alias == canonical 深等；信封 / 字段集合逐字段一致 |
| T-02 | PASS | hostname / status 存在、非空、属封闭集合 |
| T-03 | PASS | 只含本 Cluster |
| T-04 | PASS | PATCH 后 status 最新 |
| T-05 | PASS | 中文往返 |
| T-06 | PASS | 不存在 404（alias + canonical），非 200 空集 |
| T-07 | PASS | 已软删 Cluster 404（alias + canonical） |
| T-08 | PASS | 存在无成员 200 Empty |
| T-09 | PASS | 空集不含 `error` |
| T-10 | PASS | 大小写敏感命中 / 未命中 |
| T-11 | PASS | 已软删 BareMetal 被排除 |
| T-12 | PASS | DELETE 后消失，Cluster 与其余机器不变 |
| T-13 | PASS | 无 restore / undelete / include_deleted 路由与参数 |
| T-14 | PASS | 未认证 401 无数据 |
| T-15 | PASS | 非法 page / page_size → 400 + `details[].field` |
| T-16 | PASS | 分页正确（total / page / page_size 回显，跨 Cluster 不串） |
| T-17 | PASS | alias 与 canonical 对同一 Cluster 深等 |
| G-009-1 | PASS | `EXPECTED_GET_ROUTES` 追加而非替换；既有成员全保留（注入删除 → FAILED） |
| G-009-2 | PASS | 全部 OpenAPI path 无边界 token（注入越界路由 → FAILED） |
| G-009-3 | PASS | alias 200 schema == canonical；`BareMetalRead` 恰 13 字段（注入改 response_model → FAILED） |
| G-009-4 | PASS | `cluster_views` 源码无越界字段 token（注入 `rack` → FAILED） |
| G-009-5 | PASS | `scan_deleted_at_writes(cluster_views)=={}`；全局 allow-list 未变（注入写入 → FAILED） |
| G-009-6 | PASS | alias 路由集合恰 1 条 GET（注入第二路由 → FAILED） |
| T-FE-09 | PASS | clusterId 限定下 Empty / Not Found / Error 三态可分；Empty 不触发全局 401 |
| T-FE-10 | PASS | `ClusterDetailPage`「查看裸金属」→ `emit openBareMetals(clusterId)` |
| T-FE-11 | PASS | Cluster 视角源码无 restore / undelete / include_deleted / 回收站 |

**既有测试与 guard 演进核查（是否被削弱）**：`tests/test_auth_guards.py::EXPECTED_GET_ROUTES` 仅**追加** alias 一行（`git diff` 确认 +2 行、无删除）；`tests/test_deletion_guards.py` / `tests/test_bare_metals_guards.py` / `tests/test_structure_guard.py` 原样保留；无测试被删除后不补、无验证力削弱。

---

## Database / Migration

- database 层 `false` 独立确认：`git diff base..HEAD -- backend/migrations/` **为空**；无新表 / 列 / 索引 /约束 / migration。
- 真实库 `csm_mig`：`alembic upgrade head` 成功，`current = 0003_f002_bare_metals (head)`，`alembic check` 无漂移。
- 直连 schema 断言：表集合仍为 5（含 `alembic_version`）；`clusters` / `bare_metals` 的 `deleted_at` 列未变；partial unique 索引 `ux_clusters_name_active` / `ux_bare_metals_cluster_hostname_active` 与 `ix_bare_metals_cluster_id` 未变；约束集合未变。
- 索引访问路径：名称解析走 `ux_clusters_name_active`，成员读取走 `ux_bare_metals_cluster_hostname_active`（`enable_seqscan=off` 下 EXPLAIN 确认）。
- 软删语义绕应用层直连验证：预置 `deleted_at` 的 Cluster → 解析不命中（404）；预置 `deleted_at` 的 BareMetal → 列表与 `total` 均排除。

## Backend / API

- 5 个类别断言经真实 uvicorn + 真实 PG 全量复核（35/35）：契约字段集合封闭（13 字段、无 `deleted_at`）、分页信封一致、`id` 升序、Empty vs Not Found、大小写敏感、中文往返、只读无副作用、非法分页 400 + `details[].field`、未认证 401。
- 判定顺序（REQUIRED #2）经实现与测试共同确认：先名称解析（未命中 → 404），后委托 `list_bare_metals(cluster_id=...)`（空 → 200 Empty）；`service.py` 只做 `get_cluster_by_name` → `list_bare_metals`，无自写过滤谓词。
- 软删单一性（REQUIRED #1 / ADR-0004）：`cluster_views` 模块源码 AST 中 `deleted_at` 的 Name/Attribute 节点数均为 0；`scan_deleted_at_writes` 为空；全局 allow-list 恰 `{backend/app/deletion/service.py}`。
- 未发现任何 AC 层面的后端契约违约。

## Frontend

- `typecheck` / `test`（176 passed / 16 files）/ `build` 全绿。
- 新增回归 `frontend/tests/f009ClusterResourceView.spec.ts`：T-FE-09（三态 + Empty 不触发全局 401）、T-FE-10（Cluster 详情入口）、T-FE-11（无恢复入口 token）。
- 复用既有 F002 交付物：`BareMetalListPage` 在 `clusterId` 限定下 Empty（「该集群暂无裸金属」）与 Not Found（`data-error-code=NOT_FOUND`「未找到资源」）渲染不同状态；`ClusterDetailPage` 提供「查看裸金属」入口；`App.vue` 以 `clusterId` 上下文切换。
- 前端源码扫描（`BareMetalListPage.vue` / `ClusterDetailPage.vue` / `App.vue` / `api/bareMetals.ts`）无 restore / undelete / include_deleted / 回收站 / 恢复 入口（「不可恢复」「返回时恢复该上下文」为合法措辞，已排除）。
- 未发现 FRONTEND 缺陷。

## Integration

**真实前后端集成 = PASS（实际执行，非 Mock / Fixture）**：

1. 真实 uvicorn（真实 PG `csm_api`）+ 原始 httpx：alias 与 canonical 成功与错误路径共 **35/35** 断言通过。
2. **前端真实 API client**（`auth.ts` / `bareMetals.ts` / `clusters.ts` / `http.ts`）经 happy-dom 同源管理真实 HttpOnly 会话 Cookie，对接真实后端完成未认证 401 → 登录 → Empty → Not Found → 有成员计数的完整路径，临时探针 **4/4** 通过，运行后已删除。

**说明**：仅 Mock / Fixture 不足以判定集成通过；本 Feature 已用真实后端 + 真实 PG + 真实前端 client 覆盖契约的主要成功与错误路径。

---

## Defects

**None。**

- 未发现 BLOCKER / HIGH / MEDIUM / LOW 缺陷。
- 未发现 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND 缺陷。

**测试过程观察（非缺陷，不计入 Defect）**：首次全量 pytest 与本次对抗注入**并行**运行时，`tests/test_lint.py::test_lint_is_executable_and_clean` 一度失败（ruff 扫到注入窗口内的临时越界代码）；注入逐字节还原后单独重跑该测试 2 passed，随后干净环境下重跑全量 pytest 得 `311 passed`。此为测试编排自干扰，与 F009 实现无关。

## Unverified Areas

1. **浏览器级 E2E / 视觉 / 真实 DOM**：无浏览器自动化环境；前端行为经 vitest（happy-dom）组件测试与真实 API client 集成验证，未在真实浏览器观察渲染 / 网络 / 视觉。
2. **并发软删竞态的实际交错**：契约 REQUIRED #3 要求并发下不返回「已删 Cluster 的成员」。本次经「委托 `list_bare_metals` 内部父活跃复检」的静态结构与 T-07 的软删读取验证确认，但未构造真实的「解析成功 → 并发软删 → 读取」逐时刻交错压测（无专用并发夹具；属低风险，读取不写数据无需加锁）。
3. **多 uvicorn worker / 跨进程并发**：未做多 worker 压测（无产品需求，V1 单机内网）。
4. **`by-name` 空名称段 / 缺失段**：架构 OPEN（不承诺），未验证；不属任何 AC。

## Test Status

`READY FOR REVIEW`

依据：AC-01 ~ AC-18 全部有结果、无 FAIL / BLOCKED / NOT TESTED；Architecture Test Work T-01 ~ T-17、G-009-1 ~ G-009-6、T-FE-09 ~ T-FE-11 全部 PASS，无 skipped；真实前后端集成已**实际执行**（真实 uvicorn + 真实 PG + 前端真实 API client）；工程门禁（ruff / format / 全量 pytest 311 / 前端 typecheck + test 176 + build）全绿；既有测试与 guard 随增表演进而非削弱；六条结构 guard 经对抗注入确认真实可失败并逐字节还原。无 BLOCKER / HIGH / MEDIUM / LOW 缺陷。

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-18 全部 PASS（无 FAIL / BLOCKED / NOT TESTED）。
- Architecture Test Work T-01 ~ T-17 / G-009-1 ~ G-009-6 / T-FE-09 ~ T-FE-11 全部 PASS。
- 后端全量 `311 passed`（无 skipped）；F009 专项 `46 passed`。
- alias 与 canonical 深等（字段 / 排序 / 分页信封 / total）；OpenAPI 200 schema 相等。
- 名称解析大小写敏感；已软删 Cluster 不参与解析（绕应用层）→ 404；不存在 → 404（非 200 空集）；存在无成员 → 200 Empty。
- 已软删 BareMetal（绕应用层）被排除；DELETE 后消失；Cluster 与其余机器不变。
- 未认证 401 且无数据；非法分页 400 + `details[].field`。
- 软删单一性：`cluster_views` 无 `deleted_at` 表达式；全局 allow-list 未变。
- 六条 guard 经对抗注入证明真实可失败，逐字节还原（`git status` 干净）。
- 前端 typecheck / test（176）/ build 全绿；三态可分、Empty 不触发全局 401、入口正确、无恢复入口。
- 真实前后端集成实际执行（真实 uvicorn + 真实 PG + 前端真实 client）。

### Not Verified

- 浏览器级 E2E / 视觉 / 真实 DOM。
- 并发软删竞态的逐时刻交错（仅静态结构 + 软删读取路径验证）。
- 多 worker / 跨进程并发。
- `by-name` 空名称段边界（架构 OPEN，不属 AC）。

### Blocking Issues

None。

### Defect Owner

None。

### 新增 / 修改文件

- 新增（仅测试）：`frontend/tests/f009ClusterResourceView.spec.ts`（T-FE-09 ~ T-FE-11 回归）。
- 未修改任何业务实现（`backend/app/**`、`frontend/src/**`、`backend/migrations/**`）或产品 / 架构 / 契约文档；对抗注入已逐字节还原。
- 临时文件（`/tmp/f009-test/**`、`frontend/tests/zzTmpF009Integration.spec.ts`）运行后已删除。

---

GIT: NONE
