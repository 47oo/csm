# Test Report — F014 逻辑删除与数据一致性治理

> Status: **READY FOR REVIEW**
> Author Role: tester
> Date: 2026-09-16
> Feature: F014（ENABLER，E07，P0，`depends_on: [F012]`）
> 分支：`feature/F014-soft-delete`
> base `develop` = `897b32539927c137b933aa0ebed700d3bc26be5b`
> 实现 HEAD = `592e96e2cce091b481e13ad030462546b387d6a1`（其后 `a87ff04` 为计划元数据检查点）
> 分支状态：database: false（NOT_REQUIRED）、backend COMPLETE、frontend COMPLETE

---

## Feature

逻辑删除与数据一致性治理（F014）— CSM V1 的逻辑删除领域基座：系统内**唯一**软删写入路径、删除守卫（父删子拦 / 不级联 / 单事务加锁）、`clusters` 产品删除路径 `DELETE /api/clusters/{cluster_id}`，以及前端删除入口与状态接线。

## Test Basis

- `AGENTS.md`
- `docs/product/handoffs/f014-soft-delete.md`（Product Handoff，`READY FOR ARCHITECT`，AC-01 ~ AC-13；NQ-1 / NQ-2 归属细化）
- `docs/product/requirements.md` §17（R-DELETE-001 ~ R-DELETE-006）、§21、§22、§23、§25
- `docs/product/domain-model.yaml > lifecycle / data_consistency / uniqueness_rules`
- `docs/architecture/f014-soft-delete-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，T-01 ~ T-13 / G-1 ~ G-4 / T-FE-01、REQUIRED、Constraints、问题 7 的 F002 交接）
- `docs/api/f014-soft-delete.md`（API 契约，`READY`，单一权威）
- `docs/api/api-conventions.md`（`READY`）
- `docs/architecture/adr/adr-0004-soft-delete-and-uniqueness-release.md`（`ACCEPTED`）、ADR-0003、ADR-0005
- `docs/database/csm-v1-schema-design.md`、`docs/database/f012-baseline-migration.md`
- `docs/project/project-plan.yaml > F014`
- `.pi/skills/resource-domain/SKILL.md`
- 报告格式先例：`docs/test-reports/f001-cluster.md`、`docs/test-reports/f013-auth.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f014-test/pgdata`，本次新建） |
| Node / npm | v24.14.0 / 11.9.0（Vite 7.3.6，Vitest 5.0.1） |
| 测试库 | `csm_f014`（pytest）、`csm_mig`（迁移）、`csm_api`（真实服务集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn`（真实 PG `csm_api`）：正常实例 `127.0.0.1:8797`；409 探针实例 `127.0.0.1:8798`（仅在进程内 monkeypatch 声明点，见 Integration） |
| 前端测试 | `npm run typecheck` / `npm run test` / `npm run build` |

**是否全新**：数据库实例、各测试库、测试账号均为本次测试新建；pytest 每次经 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 从空库重建。实现方结论**未被复用**，下表所有结果均来自本次独立执行。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端测试（独立重跑，无 skip 伪造）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f014?host=/tmp/f014-test/pgdata" \
  .venv/bin/python -m pytest -q
155 passed, 2 warnings in 83.86s

F014 专项子集（含数据库层绕过应用层断言）：
$ .venv/bin/python -m pytest tests/test_deletion_api.py tests/test_deletion_guards.py \
    tests/database/test_deletion_schema_guard.py -v
23 passed, 2 warnings in 15.34s
（T-01 ~ T-13 / G-1 / G-3 / G-4 全部 PASSED，无 skipped）
```

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 68 files already formatted  exit 0
```

### 3. 迁移（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head   → 0001_f012_baseline → 0002_f013_auth
$ alembic upgrade head   → no-op（无 DDL）
$ alembic current        → 0002_f013_auth (head)
$ alembic check          → No new upgrade operations detected.（模型与库无漂移）
$ git diff 897b325..HEAD -- backend/migrations/  → 空
$ git log 897b325..HEAD -- backend/migrations/   → 无提交
```

即：**无新增 migration**，head 仍为 `0002_f013_auth`，基线 `0001_f012_baseline` 未被修改。

### 4. 前端

```text
$ cd frontend && npm run typecheck → exit 0
$ npm run test                     → Test Files 11 passed (11)，Tests 105 passed (105)
$ npm run build                    → vue-tsc 通过 + vite build 成功
                                     dist/assets/index-DV787Yk3.js 1,016.56 kB（仅 chunk 体积告警）
```

### 5. 对抗注入（证明 G-3 allow-list guard 真的可失败）

在 `backend/app/` 临时新增两个越权写入文件（新文件，非改动既有源码）后运行 guard：

```text
AssertionError: 写入 deleted_at 的文件集合异常：
  {'backend/app/deletion/service.py', 'backend/app/__tester_inject_a__.py', 'backend/app/__tester_inject_b__.py'}
FAILED tests/test_deletion_guards.py::test_g3_deleted_at_writers_are_allowlisted
FAILED tests/test_deletion_guards.py::test_g3_no_undelete_path
FAILED tests/test_clusters_guards.py::test_a15_deleted_at_write_paths_are_allowlisted
3 failed, 21 passed
```

删除临时文件后（`git status --short` 为空）重跑：`38 passed`。即 allow-list guard 与「无 undelete」guard 均**真实可失败**，且本次注入被逐字节还原（未触碰任何受版本控制文件）。

扫描器形态覆盖抽测（`tests/deletion_guard_helpers.py`）：

```text
命中：a.deleted_at = x
      session.execute(update(T).values(deleted_at=now()))
      setattr(obj, "deleted_at", now())
      session.execute("UPDATE clusters SET deleted_at = now() ...")
不命中（正确）：x.deleted_at == None；T.deleted_at.is_(None)； WHERE 过滤
```

### 6. 真实前后端集成（真实 uvicorn + 真实 PG；临时 vitest 探针，运行后已删除）

用**前端真实 API client**（`src/api/clusters.ts::deleteCluster` / `createCluster`、`src/api/auth.ts::login`、`src/api/http.ts::ApiError`）经 happy-dom 管理 HttpOnly 会话 Cookie，对接真实后端：

```text
Tests 3 passed (3)
- 未认证 deleteCluster(1) → ApiError{status:401, code:'UNAUTHENTICATED'}，
  并触发一次全局未认证 handler
- 已认证 createCluster → 201；deleteCluster → resolves undefined（204，无响应体）；
  重复 deleteCluster → ApiError{status:404, code:'NOT_FOUND', details: []}
- 对带注入活跃子检查的真实后端（8798）deleteCluster → ApiError{status:409,
  code:'CONFLICT'}，details[] 含 ACTIVE_CHILDREN_EXIST
```

独立原始 HTTP 复核（`.venv` httpx + 原始 psycopg，绕过前端）：

```text
unauth DELETE            → 401 UNAUTHENTICATED
401 后目标行 deleted_at   → None（未认证不改数据）
DELETE                   → 204，body=b''，行仍物理存在，deleted_at 已置非空
重复 DELETE              → 404 NOT_FOUND
注入活跃子后 DELETE      → 409 CONFLICT，details[].code=ACTIVE_CHILDREN_EXIST，
                           且 deleted_at 仍为 None（无部分写入）
```

---

## Acceptance Criteria Mapping

| AC | Test（Architecture Test Work / 独立验证） | Result | Evidence |
|---|---|---|---|
| AC-01 逻辑删除而非物理删除（R-DELETE-001） | T-01 + 真实 HTTP | **PASS** | `DELETE` → `204`、`content==b""`；原始连接断言 `clusters` 行数不变、该行仍存在、`deleted_at` 非空；不存在其它物理删除产品端点（负向路由 T-12） |
| AC-02 已删不出现在常规查询（R-DELETE-002） | T-02 + T-09 | **PASS** | 删除后列表 `items`/`total` 不含该行；`GET /{id}` 与 `GET /by-name/{name}` 均 `404 NOT_FOUND`；删空后列表仍 `200 + items==[]`（Empty ≠ Not Found） |
| AC-03 无恢复能力（R-DELETE-003） | T-03 + G-3 静态 | **PASS** | 重复删除 → `404` 且 `deleted_at` 不被改写；无 restore/undelete 路由（T-12）；扫描器对 `deleted_at = None` 可失败（对抗注入已验证）；生产实现中不存在 `deleted_at = None` 写入 |
| AC-04 父有活跃子资源时不得删除（R-DELETE-004） | T-05 + T-06（机制） | **PASS**（F014 可验证形态） | 注入返回 True 的 `ActiveChildCheck` → `409 CONFLICT`、`details[].code=="ACTIVE_CHILDREN_EXIST"`、目标行 `deleted_at` 仍 NULL（无部分写入）；检查在父行 `FOR UPDATE` 之后同事务内执行（第二连接 `NOWAIT` 失败）。真实 Cluster+BareMetal 端到端 **NOT TESTED**（无子资源表，见 Unverified Areas / NQ-1） |
| AC-05 不级联、只改目标行（R-DELETE-005） | T-07 + G-1 | **PASS** | 删除 A 后 `clusters` 全表快照比对：仅 A 的 `deleted_at` 变化，B 的 `deleted_at`/`name`/`updated_at` 逐字段不变，无行被物理删除；`pg_constraint` 中 `confdeltype='c'` 计数 = 0 |
| AC-06 已删释放唯一性（R-DELETE-006） | T-08 | **PASS** | 删 `name=X` 后 `POST {"name":X}` → `201`（新 id）；列表只见新行；旧已删行仍保留且 `deleted_at` 未被改写；同名 2 行并存 |
| AC-07 关键冲突在保存前阻止、不只依赖 UI（§21） | T-04 + G-3 | **PASS** | 无任何前端参与、直接调用 `DELETE` 即触发后端守卫（注入检查 → `409`；移除检查 → `204`）；前端仅按 `error.code` 分支、不做业务预判（见 Frontend）；唯一写入路径被静态 allow-list 约束（真实可失败） |
| AC-08 唯一软删写入路径（ADR-0004） | G-3 | **PASS** | `backend/app/**` 中写 `deleted_at` 的文件集合恰为 `{backend/app/deletion/service.py}`；`clusters` 删除委托 `soft_delete()`（正向断言）；`deleted_at=None` 路径为空。**注**：扫描器未覆盖 Handoff G-3 明列的「mappings（dict）写入形态」，见 Defect F014-T-01（LOW） |
| AC-09 并发正确性（ADR-0004 §5） | T-06 + T-13（F014 可验证形态） | **PASS**（F014 可验证形态） | T-06 证明检查在父行加锁后、同事务内执行；T-13 证明第二连接持父行 `FOR UPDATE` 时 `DELETE` **阻塞等待**（>1.5s 未完成），释放后 `204`——使用阻塞行锁而非 MVCC 快照直更。完整「创建子 vs 删除父」端到端与孤立记录不变式 **NOT TESTED**（F002 义务，见 Unverified Areas） |
| AC-10 前端删除动作与状态（T-FE-01） | 前端组件测试 + 真实集成 | **PASS** | 列表 / 详情均有删除入口（`ElPopconfirm` 二次确认）；`204` → 刷新、被删行消失、当前页变空 → Empty 态；详情 → 独立 Not Found 态；`409`/`404` 按 `error.code` 渲染且断言不解析 `message`；提交中 Loading 且重复确认不产生第二个 DELETE；前后端均未在前端重复实现守卫 |
| AC-11 无越界能力 | T-12 | **PASS** | OpenAPI 路径不含 restore/undelete/purge/trash/batch/deleted；列表端点无 `include_deleted` 等查询参数 |
| AC-12 认证边界（R-AUTH-003） | T-10 + 真实集成 | **PASS** | 未认证 `DELETE` → `401 UNAUTHENTICATED` 且 `deleted_at` 仍 NULL（不改数据）；已认证普通用户即可删除，无角色 / 权限依赖；真实前端 client 亦得 `401 UNAUTHENTICATED` 并触发全局会话失效 |
| AC-13 非资源表不受影响 | G-4 + T-11 + F013 既有测试 | **PASS** | `users` / `sessions` 列集合无 `deleted_at`；`app/auth/**` 无 `deleted_at` 写入；`User` / `Session` 模型无该属性；F013 认证测试全绿 |

**说明**：AC-01 ~ AC-13 全部有结果，无遗漏、无 FAIL、无 BLOCKED。AC-04 / AC-09 为 F014 可验证形态 PASS，真实业务子场景（BareMetal）按 Product Handoff 澄清 1 / NQ-1 归 F002，已在 Unverified Areas 显式记录，避免静默丢失。

## Test Work（T-01 ~ T-13 / G-1 ~ G-4 / T-FE-01）覆盖

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | `204` + 空 body；行数不变、行仍在、`deleted_at` 非空 |
| T-02 | PASS | 列表 / 按 id / by-name 均排除；删空列表 `200 + []` |
| T-03 | PASS | 重复删除 `404`，`deleted_at` 不变；无 restore 路由 |
| T-04 | PASS | 直接 API（无 UI）触发后端守卫，`409` / `204` 随检查切换 |
| T-05 | PASS | 注入检查 `409` + 稳定 code + `deleted_at` 仍 NULL + 检查确被调用 |
| T-06 | PASS | 检查执行时第二连接 `FOR UPDATE NOWAIT` 失败（父行已锁） |
| T-07 | PASS | 全表快照：仅目标行 `deleted_at` 变化，无物理删除 |
| T-08 | PASS | 删除后同名重建 `201`，旧行保留 |
| T-09 | PASS | Empty（200 + []）与 Not Found（404 + details==[]）可区分 |
| T-10 | PASS | 未认证 `401` 且数据不变；已认证无需角色 |
| T-11 | PASS | 认证表无 `deleted_at` 列 / 属性 / 写入 |
| T-12 | PASS | 无非整数路径 DELETE 别名（`400 VALIDATION_ERROR`）；无越界路由 / 参数 |
| T-13 | PASS | 持锁期间 `DELETE` 阻塞，释放后完成 |
| G-1 | PASS | `confdeltype='c'` 外键计数 = 0；全部 FK 为 RESTRICT / NO ACTION |
| G-2 | PASS | `clusters` 列 / CHECK / `ux_clusters_name_active` predicate 与 F012 基线一致（`tests/database/test_g2_schema_guard.py` 全绿） |
| G-3 | PASS | allow-list 恰好 `{app/deletion/service.py}`；无 undelete；真实可失败（对抗注入验证）。覆盖面缺 mappings 形态 → F014-T-01 |
| G-4 | PASS | `users` / `sessions` 无 `deleted_at` |
| T-FE-01 | PASS | 见 Backend / Frontend / Integration 小节 |

**既有测试演进核查（是否被削弱）**：

| 旧断言 | 处置 | Tester 判定 |
|---|---|---|
| `test_a15_no_deleted_at_assignment_in_app_source`（写入数 = 0） | 演进为 G-3 allow-list（`test_a15_deleted_at_write_paths_are_allowlisted` / `test_g3_*`） | **未削弱**：由「0 处」演进为「恰好 1 处文件」，并新增可失败性（对抗注入验证）与正向「服务确被使用」断言 |
| `test_g_e_no_deleted_at_assignment_in_app_source`（扫描全部 app = 0） | 收窄为 `app/auth/**`；全量 app 由 G-3 allow-list 覆盖 | **未削弱**：全量扫描能力由 G-3 承接，收窄仅保留「认证代码不写」原意；F013 G-F 既有断言仍在 |
| `test_a15_delete_endpoint_does_not_soft_delete`（DELETE 不软删） | 语义反转，由 T-01 取代（DELETE **确实**软删、行仍在） | **未削弱**：F001 该断言的前提（F014 未落地）已被 F014 取代；替代断言更强（204 + 行保留 + `deleted_at` 非空）。前端 `clusterDetailPage` 中「无删除入口」断言同理反转，属 Feature 语义演进 |

除以上三处（+ 前端详情页一处）外，既有测试文件仅新增，无其它删除或弱化。

---

## Database / Migration

**迁移**：`database: false` 得到独立确认。真实库 `csm_mig` 上 `alembic upgrade head` 可应用、第二次为 no-op、`current` = `0002_f013_auth (head)`、`check` 无漂移；`897b325..HEAD` 对 `backend/migrations/` **无任何 diff / 提交**。

**独立 Schema 检查**（真实 PG 16.2，绕应用层原始 psycopg，`csm_mig`）：

```text
tables:      ['alembic_version', 'clusters', 'sessions', 'users']
clusters 列: id bigint NN (identity) / name text NN / created_at timestamptz NN DEFAULT now() /
             updated_at timestamptz NN DEFAULT now() / deleted_at timestamptz NULL
clusters 约束: pk_clusters(PK id) / ck_clusters_name_no_slash CHECK(strpos(name,'/')=0)
clusters 索引: pk_clusters / ux_clusters_name_active UNIQUE(name) WHERE deleted_at IS NULL
含 deleted_at 列的表: 仅 clusters
confdeltype='c' 外键计数: 0
```

与 F012 基线 / Database Handoff 逐项一致：**`clusters` 结构未变**、无额外 Schema、无 CASCADE、唯一索引 predicate 未变、大小写语义未变。

**约束对抗（G-1/G-4）**：真实库 `pg_constraint` 无 CASCADE；`users`/`sessions` 无 `deleted_at`。

## Backend / API

- 统一软删服务 `app/deletion/service.py::soft_delete()` 行为与契约一致：`select_active(...).with_for_update()` 锁活跃行（未命中 → 404）→ 执行声明的 `ActiveChildCheck`（命中 → 409 且不写）→ 仅目标行 `deleted_at = now()`。
- `app/clusters/deletion.py` 显式声明 `CLUSTER_ACTIVE_CHILD_CHECKS = ()`（不硬编码于服务）；`service.delete_cluster` 委托 `soft_delete`。
- `DELETE /api/clusters/{cluster_id}` 注册于 `app/clusters/router.py`，`status_code=204`、无 `response_model`；`by-name` 只读别名先于 `/{cluster_id}`，无 by-name 删除。
- 契约行为（真实 HTTP 复核）：`204`（空 body）/ `404 NOT_FOUND`（不存在或已删，不区分）/ `409 CONFLICT`（`details[].code=ACTIVE_CHILDREN_EXIST`，无部分写入）/ `401 UNAUTHENTICATED`（不改数据）/ 非整数 `400 VALIDATION_ERROR`。
- 读取侧过滤复用 `app/db/active.py` 原语（F014 未重写），删除后列表 / 按 id / by-name 均排除。
- 未发现任何 AC 层面的后端契约违约。F013 认证、F012 数据库测试全部保持全绿（155 passed）。

## Frontend

- `typecheck` 0、`test` 105 passed（11 文件）、`build` 成功。
- `api/clusters.ts::deleteCluster` 走 `DELETE /api/clusters/{id}`，不发送请求体，`204` 归一为 `undefined`；错误经 `http.ts` 归一为 `ApiError`。
- `useClusterDelete`：仅按 `error.code`（必要时 `details[].code`）分支；`204` 与 `404` 同构刷新；`401` 交给全局会话失效、本层不渲染；`409` 渲染由稳定 code 生成的固定文案；提交中 `deletingId` 非空 → 重复提交被拦截。
- `ClusterListPage`：每行 `ElPopconfirm` 删除入口；成功刷新、当前页变空 → Empty 态；409 保留行并显示冲突提示；提交中 Loading / 其余行禁用。
- `ClusterDetailPage`：内容态删除入口；成功后重新读取 → 服务端 `404` → 既有独立 Not Found 态；409 保留详情并显示冲突提示。
- 前端**未**重复实现删除守卫（不禁用 / 不隐藏任何行的删除入口来替代后端裁决）。组件测试显式断言后端返回的 `message` 文案不参与渲染（证明不解析 message）。

## Integration

**已验证（真实前后端）**：

1. 真实 uvicorn（真实 PG `csm_api`）+ 原始 httpx：`401`（不改数据）/ `204`（行保留、`deleted_at` 置位）/ 重复 `404` / `409`（稳定 code + 无部分写入）全部符合契约。
2. 使用**前端真实 API client** 的临时 vitest 探针对接真实后端 3/3 通过：`401` 归一 + 全局 handler、`204`→`undefined`、重复 `404 NOT_FOUND`、`409 CONFLICT`（`details[].code` 可见、可见于可渲染结构）。会话 Cookie 由 happy-dom 真实管理。探针运行后已删除。
3. `409` 路径因 F014 无真实子资源表，通过**进程内 monkeypatch `CLUSTER_ACTIVE_CHILD_CHECKS`** 的独立 uvicorn 实例触发；端点、错误信封、真实 PG 均为生产代码，未修改业务实现（仅测试进程内替换声明点，与 `tests/test_deletion_api.py` 的注入手法等价）。

**说明**：仅 Mock / Fixture 的开发期做法不足以判定集成通过；本 Feature 已用真实后端 + 真实前端 client 验证删除端点的四类结果。未覆盖真实浏览器 DOM / 视觉，见 Unverified Areas。

## Defects

### F014-T-01 — G-3 静态扫描器未覆盖 Handoff 明列的 mappings（dict）写入形态（LOW，Follow-up）

- **ID**：F014-T-01
- **Severity**：LOW（较小问题，可 Follow-up；不削弱任何 AC 的当前结论）
- **Layer / Owner**：Test / Guard（`tests/**`，Backend 交付物）→ backend
- **Location**：`tests/deletion_guard_helpers.py::scan_deleted_at_writes`（`_WRITE_RE`）；`docs/architecture/f014-soft-delete-handoff.md` 问题 1 / G-3
- **复现步骤**：在 `backend/app/**` 放入含 `session.execute(update(T).values({"deleted_at": now()}))` 或 `values(**{"deleted_at": now()})` 的文件后运行 `pytest tests/test_deletion_guards.py::test_g3_deleted_at_writers_are_allowlisted`。
- **期望**：Handoff G-3 明列扫描「`.deleted_at =`、`values(deleted_at=`、`setattr(...)`、`mappings 中的 deleted_at`」；dict / `**` 映射写入应被识别为第二写入路径，guard 失败。
- **实际**：`_WRITE_RE` 只覆盖 `.deleted_at =`、`values(...deleted_at=`、`setattr(...,"deleted_at")`；`values({"deleted_at": ...})` / `values(**{"deleted_at": ...})` / 裸 dict 形态**不命中**，guard 不会失败（实测）。
- **影响**：当前生产代码不存在此类写入（G-3 实际通过，无第二路径），因此**不影响任何 AC 的当前结果**；但若未来新增 dict 形态的第二软删写入路径，静态 guard 会静默漏检，AC-08 的验证力出现缺口。行为测试（T-01 / T-07）仍是运行时兜底。
- **建议**：扩展扫描器覆盖 dict-key 形态（如正则匹配字符串字面量 `"deleted_at"`/`'deleted_at'` 出现在 `values(` / `update(` 调用参数中的情况），或将 G-3 改为基于 AST 的扫描。

**除 F014-T-01（LOW，Follow-up）外，未发现 BLOCKER / HIGH / MEDIUM 缺陷。** 未发现产品、架构或数据库层面的 Defect。

## Unverified Areas

1. **AC-09 / AC-04 的真实业务端到端（Cluster + 活跃 BareMetal）**：`bare_metals` 表属 F002（尚未落地），F014 时点无真实子资源实体。已按 Architecture Handoff 问题 7 验证机制（T-05 / T-06 / T-13）；「有活跃 BareMetal → 409」「并发创建子 vs 删除父的孤立记录不变式 = 0」及创建侧 `FOR SHARE` 协议为 **NOT TESTED**，是 F002 的显式义务（Product Handoff 澄清 1 / NQ-1）。
2. **`ip_addresses.cluster_id` 一致性治理**（F005，表不存在）：F014 仅交付可复用的统一领域服务机制，未验证（Architecture Handoff 问题 10 / NQ-2）。
3. **浏览器级前端 E2E / 视觉验证**：无浏览器自动化环境；前端行为经 vitest（happy-dom）与真实 HTTP 集成验证，未在真实浏览器观察 DOM/网络/视觉。
4. **生产构建产物在真实 nginx + 内网下的部署**：属 F015。
5. **多 uvicorn worker / 跨进程并发**：未做多 worker 并发压测（无产品需求，V1 单机内网）。
6. **静态 guard 的动态 SQL 绕过**：Handoff R2 已知残余风险；本次对抗注入覆盖 ORM 赋值 / 裸 SQL 形态，未穷举所有动态构造方式（见 F014-T-01）。

## Test Status

`READY FOR REVIEW`

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-13 全部有结果，全部 PASS（AC-04 / AC-09 为 F014 可验证形态）。
- Architecture Test Work T-01 ~ T-13 / G-1 ~ G-4 / T-FE-01 全部 PASS，无 skipped。
- 数据库：`clusters` 结构 / CHECK / partial unique index 与 F012 基线一致；无 CASCADE；`users`/`sessions` 无 `deleted_at`；无新增 migration，基线未改。
- 后端：唯一软删路径（allow-list 真实可失败）；单事务先锁后检查；无部分写入；不级联、只改目标行；已删释放唯一性；未认证 401 不改数据；无越界能力。
- 前端：三态 + 删除入口 + 成功刷新 / Empty / 独立 Not Found / 409 / 404 / 401 按 `error.code` 渲染 + 防重复提交；未重复实现守卫。
- 真实前后端集成：真实 uvicorn + 真实 PG + 前端真实 API client，`204`/`404`/`409`/`401` 全部符合契约。
- 既有 A15 / G-E / `test_a15_delete_endpoint_does_not_soft_delete` guard 均**演进未削弱**。
- 对抗注入证明 G-3 allow-list guard 真实可失败，并已逐字节还原。

### Not Verified

- F002 真实子资源（BareMetal）场景的 AC-04 / AC-09 端到端与孤立记录不变式。
- F005 `ip_addresses.cluster_id` 一致性治理。
- 浏览器级 E2E / 视觉、生产 nginx 部署、多 worker 并发压测。
- G-3 扫描器的 dict / `**` mappings 形态（F014-T-01）。

### Blocking Issues

None。

### Defect Owner

- F014-T-01（LOW，Follow-up，guard 覆盖面）→ backend。

---

GIT: NONE