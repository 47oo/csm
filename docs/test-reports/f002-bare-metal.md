# Test Report — F002 BareMetal 登记与管理

> Status: **READY FOR REVIEW**
> Author Role: tester
> Date: 2026-09-17
> Feature: F002（E01，P0，`depends_on: [F001]`）
> 分支：`feature/F002-bare-metal`
> base `develop` = `c8e5d910b057f96cc4864959ac802d15b75abc67`
> 实现 HEAD = `d964263908784ab905eaa12746a473292e0f368c`（其后 `861d067` 为计划元数据检查点）
> 分支状态：database COMPLETE、backend COMPLETE、frontend COMPLETE、test PENDING、review PENDING

---

## Feature

BareMetal 登记与管理（F002）— CSM V1 唯一有状态资源的登记、查询、状态人工维护、R-BM-007 硬件字段维护与逻辑删除，并承接 R-CLUSTER-004 的 N:1 方向、F014「父删子拦」真实端到端与创建侧 `FOR SHARE` 并发协议。

## Test Basis

- `AGENTS.md`
- `docs/product/handoffs/f002-bare-metal.md`（Product Handoff，`READY FOR ARCHITECT`，AC-01 ~ AC-30）
- `docs/product/requirements.md` §8 / §13 / §17 / §21 / §22 / §23；`docs/product/domain-model.md` / `domain-model.yaml`
- `docs/architecture/f002-bare-metal-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，Test Work T-01 ~ T-30 / G-1 ~ G-7、问题 1~12、REQUIRED、Constraints）
- `docs/architecture/f014-soft-delete-handoff.md`、ADR-0001 ~ ADR-0005（均 `ACCEPTED`）
- `docs/database/f002-bare-metal-migration.md`（Database Handoff，V-1 ~ V-14）
- `docs/api/f002-bare-metal.md`（API 契约 **READY**，唯一权威）、`docs/api/api-conventions.md`
- `docs/project/v1/project-plan.yaml > F002`
- `.pi/skills/resource-domain/SKILL.md`
- 报告格式先例：`docs/test-reports/f014-soft-delete.md`、`docs/test-reports/f015-deployment.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f002-test/pgdata`，本次新建） |
| 测试库 | `csm_f002`（pytest）、`csm_mig`（迁移 / 直连 schema 检查）、`csm_api`（真实前端 client 集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn`（真实 PG `csm_api`）：`127.0.0.1:8797` |
| Node / npm | v24.14.0 / 11.9.0（Vite 7.3.6，Vitest 5.0.1，happy-dom 20.14.5） |
| ruff / psycopg | 0.16.7 / 3.3.5 |
| 前端测试 | `npm run typecheck` / `npm run test` / `npm run build` |

**是否全新**：PG 实例、三个测试库、管理员账号、集成探针均为本次测试新建；pytest 每次经 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 从空库重建。实现方结论**未被复用**——下表所有结果均来自本次独立执行。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端测试（独立重跑，无 skip 伪造）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f002?host=/tmp/f002-test/pgdata" \
  .venv/bin/python -m pytest -q
279 passed, 2 warnings in 223.74s（无 skipped）

F002 专项子集（API + 并发 + 静态 guard + DB 约束 + schema guard + 既有软删 guard）：
$ .venv/bin/python -m pytest tests/test_bare_metals_api.py tests/test_bare_metals_guards.py \
    tests/test_bare_metals_concurrency.py tests/database/test_bare_metals_constraints.py \
    tests/database/test_bare_metals_schema_guard.py tests/database/test_deletion_schema_guard.py \
    tests/test_deletion_guards.py -q
96 passed, 2 warnings in 89.48s
```

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 85 files already formatted  exit 0
```

### 3. 迁移（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head   → 0001_f012_baseline → 0002_f013_auth → 0003_f002_bare_metals
$ alembic current        → 0003_f002_bare_metals (head)
$ alembic upgrade head   → no-op（无 DDL）
$ alembic check          → No new upgrade operations detected.（模型与库无漂移）
$ alembic downgrade base → 三个版本逆序 downgrade 成功
$ alembic upgrade head   → 重建成功，current = 0003_f002_bare_metals (head)
$ git diff base..HEAD -- backend/migrations/versions/0001_f012_baseline.py \
      backend/migrations/versions/0002_f013_auth.py → 空（基线未改）
```

### 4. 独立 Schema 直连检查（真实 PG 16.2，绕应用层原始 psycopg，`csm_mig`）

```text
tables: ['alembic_version', 'bare_metals', 'clusters', 'sessions', 'users']
bare_metals 列（14）: id bigint NN(identity) / cluster_id bigint NN / hostname text NN /
  status text NN DEFAULT 'IDLE' / vendor,model,serial_number,cpu,memory,gpu,storage text NULL /
  created_at,updated_at timestamptz NN DEFAULT now() / deleted_at timestamptz NULL
约束: ck_bare_metals_status(CHECK status=ANY(IDLE,ALLOC,DOWN,UNKNOWN)) /
      fk_bare_metals_cluster(FK confdeltype='r', confupdtype='r') / pk_bare_metals
索引: pk_bare_metals / ux_bare_metals_cluster_hostname_active UNIQUE(cluster_id,hostname)
      WHERE deleted_at IS NULL / ix_bare_metals_cluster_id
列级 collation: [] ; 非内部触发器: [] ; 全库 confdeltype='c' 外键: []
```

与 Database Handoff / Architecture `0003` 规格逐项一致：**14 列、FK RESTRICT / RESTRICT、CHECK 四值、partial unique predicate、无 CASCADE / 触发器 / COLLATE / 额外列**。

### 5. 真实后端 HTTP 集成（真实 uvicorn + 真实 PG，原始 httpx，38/38）

```text
$ .venv/bin/python /tmp/f002-test/integration.py → 38/38 passed
覆盖：未认证 401（GET/POST/DELETE，不改数据）/ 登录 200 / 空列表 200+[] /
  create 201 字段集合恰 13（无 deleted_at）/ 默认 IDLE / 硬件七字段 null 不省略 /
  缺 hostname 400 field=hostname / 缺 cluster_id 400 / 不存在 Cluster 404 /
  重复 hostname 409 field=hostname code=DUPLICATE / 跨 Cluster 201 / 大小写 N1 201 /
  中文 hostname 往返 / 非法 status(RUNNING,idle,"",null) 400 field=status /
  按 cluster_id 只返回该 Cluster / 分页 total=4 / 存在但无子 200+[] vs 不存在 404 /
  PATCH status 200 持久化 / PATCH 非法 400 / PATCH 空 body 400 / PATCH hostname 400 /
  详情 404 / DELETE 204 空 body / 已删详情 404 / 重复 DELETE 404 / 软删后同名重建 201 新 id /
  无 restore/undelete/purge/batch/deleted/by-name 路由 / Cluster 有活跃 bm → 409 ACTIVE_CHILDREN_EXIST /
  GET 前后 status/updated_at 不变（只读无副作用）
```

### 6. 生命周期 / F014 端到端 HTTP 复核（真实 uvicorn + 原始 psycopg，`csm_api`）

```text
$ .venv/bin/python /tmp/f002-test/integration2.py → 9/9 passed
AC-23 有活跃子 → DELETE cluster 409 / AC-24 软删全部子 → 204 /
AC-17 绕应用层预置 deleted_at 行 → 列表 total=0、items=[]、详情 404 /
AC-18 行仍物理存在且 deleted_at 非空 / AC-19 软删后同名重建 201 且旧行 deleted_at 未改写 /
AC-20 删除 bm 后所属 Cluster name/updated_at/deleted_at 全不变
```

### 7. 真实前后端集成（**前端真实 API client** + 真实 uvicorn + 真实 PG；临时 vitest 探针，运行后已删除）

使用 `frontend/src/api/bareMetals.ts`（`createBareMetal` / `listBareMetals` / `getBareMetal` / `updateBareMetal` / `deleteBareMetal`）、`src/api/auth.ts::login`、`src/api/http.ts::ApiError`，经 happy-dom 管理真实 HttpOnly 会话 Cookie，对接 `127.0.0.1:8797`：

```text
$ npx vitest run tests/zzTmpF002Integration.spec.ts → Tests 2 passed (2)
- 未认证 listBareMetals() → ApiError{status:401, code:'UNAUTHENTICATED'}
- login → 201 创建（字段集合恰 13、无 deleted_at、默认 IDLE）
- 重复 hostname → 409 CONFLICT，details 含 {field:'hostname', code:'DUPLICATE'}
- 非法 status → 400；不存在父 Cluster → 404 NOT_FOUND
- listBareMetals({clusterId}) → total=1 / items[0].hostname='fe-n1'；不存在 cluster → 404
- updateBareMetal(status=ALLOC, gpu) → 200 新值；getBareMetal → ALLOC
- deleteBareMetal → resolves undefined（204）；此后 getBareMetal → 404 NOT_FOUND
```

探针文件（`frontend/tests/zzTmpF002Integration.spec.ts`、调试用 `zzdbg.spec.ts`）与临时 Python 脚本**运行后已删除**；`git status --short` 为空。

### 8. 对抗注入（证明 guard 真实可失败，逐字节还原）

```text
注入 1  app/clusters/deletion.py: CLUSTER_ACTIVE_CHILD_CHECKS = (has_active_bare_metals,) → ()
        → FAILED tests/test_bare_metals_guards.py::test_t27_cluster_active_child_checks_is_not_empty
        还原：sha256sum -c → 「成功」
注入 2  新增 backend/app/__tester_inject__.py 写 deleted_at（新文件，非改动源码）
        → FAILED tests/test_bare_metals_guards.py::test_g4_deleted_at_writer_allowlist_unchanged
        删除临时文件后 git status --short 为空
```

即 fail-open 守卫（T-27）与唯一软删写入路径 allow-list（G-4）均**真实可失败**，且本次注入被逐字节还原（未触碰任何受版本控制的源码内容）。

### 9. 前端

```text
$ cd frontend && npm run typecheck → exit 0
$ npm run test → Test Files 15 passed (15)，Tests 171 passed (171)（其后两次全量重跑同样全绿）
$ npm run build → vue-tsc 通过 + vite build 成功
                  dist/assets/index-Vga-AvX0.js 1,033.95 kB（仅 chunk 体积告警）
```

**首次全量前端运行**出现 **1 个既有用例偶发失败**（`appAuth.spec.ts` 全局 401 用例，`vi.waitFor` 超时），隔离运行与后续两次全量重跑均通过——见 Defects `F002-T-01`。

---

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 登记成功，字段集合恰 13、无 deleted_at | T-01 / `test_t01_create_returns_closed_field_set` + 真实 HTTP + 前端 client | **PASS** | `set(body)==READ_FIELDS`；`deleted_at` 不出现；`POSITION_FIELDS` 无交集；DB active count +1 |
| **AC-02** hostname 必填 / 非字符串 | T-02 | **PASS** | `MISSING/123/None` → `400 VALIDATION_ERROR`，`field=hostname`，`bare_metals` 行数 0 |
| **AC-03** cluster_id 必填 / 有效；不存在 / 已删 → 无写入非 5xx | T-03 | **PASS** | `MISSING/abc/None/1.5` → `400 field=cluster_id`；不存在 / 已软删 → `404 NOT_FOUND`，无写入、非 5xx |
| **AC-04** 同 Cluster hostname 唯一 | T-04 | **PASS** | 重复 → `409 CONFLICT` + `details=hostname/DUPLICATE`；active count=1 |
| **AC-05** 跨 Cluster 可重名 | T-05 | **PASS** | A/B 各 `n1` → 均 `201`，id 不同 |
| **AC-06** 大小写敏感 | T-06 + V-6 | **PASS** | 同 Cluster `n1`/`N1` 并存为 2 条；DB 直插小写 `cn001` 后再插 `cn001` → `23505` |
| **AC-07** 默认状态 IDLE | T-07 + V-8 | **PASS** | 未提供 → 响应与库均 `IDLE`；显式 `DOWN` 被接受（NQ-3 PROPOSED 7） |
| **AC-08** 硬件缺失不阻断，返回 null 不省略 | T-08 | **PASS** | 七字段均 `in body and is None` |
| **AC-09** 中文 hostname 往返 | T-09 + V-11 | **PASS** | 「计算节点-甲」登记、列表、详情逐字节一致 |
| **AC-10** 状态封闭集合（POST + PATCH） | T-10 + V-8 | **PASS** | `RUNNING/idle/""/null` → `400 field=status`，不写入；DB 直插非法 → `23514` |
| **AC-11** 状态非空、UNKNOWN 可写、无 NULL 路径 | T-11 + V-8 + 直连 schema | **PASS** | `status` 列 `NOT NULL DEFAULT 'IDLE'`；`UNKNOWN` 可写；裸插 `NULL` → `23502`；`validate_status(None)` 拒绝 |
| **AC-12** 人工维护状态 | T-12 | **PASS** | `PATCH` → `200` 新值；详情 / 列表一致；`id`/`created_at` 不变 |
| **AC-13** 列表、分页、Empty | T-13 + 真实 HTTP | **PASS** | 无活跃 → `200 {items:[],total:0,page:1,page_size:50}`，非 404；分页正确 |
| **AC-14** 详情 Not Found（不区分不存在 / 已删） | T-14 | **PASS** | 不存在与软删行均 `404 NOT_FOUND` |
| **AC-15** 按 Cluster 读取；Empty vs Not Found 可区分 | T-15 + 真实 HTTP | **PASS** | 不存在 / 已删 Cluster → `404`；存在但无子 → `200 items==[]`；只返回该 Cluster 活跃子集；非整数 → `400 field=cluster_id` |
| **AC-16** R-CLUSTER-004 N:1 方向 | T-16 | **PASS** | 同 Cluster 连续 2 台 `201`；`cluster_id` 相同、`id` 不同 |
| **AC-17** 列表 / 详情排除已删（绕应用层预置） | T-17 + 真实 HTTP | **PASS** | 原始 SQL 预置 `deleted_at` 行 → 不在 `items`/`total`；按 id `404` |
| **AC-18** 逻辑删除而非物理删除 | T-18 + 真实 HTTP | **PASS** | `204` 空 body；行仍物理存在、`deleted_at` 非空；列表 / 详情排除 |
| **AC-19** 已删释放唯一性、旧行不被改写 | T-19 + 真实 HTTP | **PASS** | 软删后同名重建 `201` 新 id；旧行仍保留、`deleted_at` 与删除时一致 |
| **AC-20** 删除不级联 | T-20 + 真实 HTTP | **PASS** | 删除 bm 后 Cluster `name/updated_at/deleted_at` 不变；其它 bm 行不变；总行数不变 |
| **AC-21** 无恢复 / 批量 / include_deleted | T-21 + 真实 HTTP | **PASS** | OpenAPI 无 `restore/undelete/purge/trash/batch/deleted/by-name`；列表无删除相关 param；重复 DELETE → `404` |
| **AC-22** BareMetal 活跃子检查点显式声明 | T-22 | **PASS** | `BARE_METAL_ACTIVE_CHILD_CHECKS == ()` 显式空元组；`delete_bare_metal` 显式传入；注入命中检查 → `409` 且不写 |
| **AC-23** Cluster 有活跃 BareMetal → 拒绝删除、无部分写入 | T-23 + 真实 HTTP | **PASS** | `DELETE /api/clusters/{id}` → `409 CONFLICT` + `ACTIVE_CHILDREN_EXIST`；Cluster `deleted_at` 仍 `NULL` |
| **AC-24** 软删全部子后 Cluster 可删 | T-24 + 真实 HTTP | **PASS** | 两个子软删 `204` 后 → Cluster `DELETE 204` |
| **AC-25** 并发孤立记录不变式 = 0 | T-25（两种交错） | **PASS** | 建先 / 删先两交错；不变式查询均 0 行；失败方无部分写入 |
| **AC-26** 创建侧对父行取共享锁并确认活跃 | T-26 | **PASS** | 父 `FOR UPDATE` 时创建阻塞；父删提交后创建 `NotFoundError`（无主机器）；`FOR UPDATE NOWAIT` 验证创建持父行共享锁 |
| **AC-27** `CLUSTER_ACTIVE_CHILD_CHECKS` 非空且被真实消费 | T-27 + 对抗注入 | **PASS** | 元组 ≥1 且含 `has_active_bare_metals`；`clusters/service.py` 消费；空元组注入 → guard FAILED |
| **AC-28** 无位置 / 上级 / 自动发现结构 | T-28 + 直连 schema | **PASS** | 表 / ORM / 响应 / OpenAPI 路径均无位置 / 上级 / 自动发现字段 |
| **AC-29** 不越界其它资源 | T-29 + 真实 HTTP | **PASS** | 无 NIC/IP/VM/Container/Service 端点；`bare_metals` 无相关列；无 `by-name/{hostname}` |
| **AC-30** 前端三态 + Empty/Not Found 区分 + error.code + 不重复守卫 | T-FE-01 + 前端组件测试 + 真实 client 集成 | **PASS** | 列表 `loading/empty/error/content` 互不相同；Empty「该集群暂无裸金属」vs NotFound「未找到资源」；详情独立 `not-found` 态；删除 / 修改按 `CONFLICT/NOT_FOUND/UNAUTHENTICATED` 分支；重复 hostname / 空 hostname 仍提交由后端裁决 |

**说明**：AC-01 ~ AC-30 全部有结果，**无 FAIL、无 BLOCKED、无 NOT TESTED**。

## Test Work（T-01 ~ T-30 / G-1 ~ G-7 / T-FE-01）覆盖

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | 13 字段封闭集合；无 `deleted_at` / 位置字段 |
| T-02 | PASS | hostname 缺失 / 非字符串 → 400 + field，无写入 |
| T-03 | PASS | 类型 400 / 不存在父与已删父 404，无写入、非 5xx |
| T-04 | PASS | 409 + `hostname`/`DUPLICATE` |
| T-05 | PASS | 跨 Cluster 同名 201 |
| T-06 | PASS | 同 Cluster 大小写共存；DB 直插重复 23505 |
| T-07 | PASS | 默认 IDLE；显式合法状态接受 |
| T-08 | PASS | 七字段 null 不省略 |
| T-09 | PASS | 中文往返 |
| T-10 | PASS | POST/PATCH 非法状态均 400 |
| T-11 | PASS | NOT NULL / UNKNOWN / NULL→23502 |
| T-12 | PASS | PATCH 200 持久化 |
| T-13 | PASS | Empty 200+[]；分页 |
| T-14 | PASS | 404（不存在 / 已删不区分） |
| T-15 | PASS | Empty vs Not Found 可区分 |
| T-16 | PASS | N:1 多台 |
| T-17 | PASS | 绕应用层预置已删行排除 |
| T-18 | PASS | 204 + 行保留 |
| T-19 | PASS | 软删释放唯一性 |
| T-20 | PASS | 不级联 |
| T-21 | PASS | 无恢复 / 批量 / by-name |
| T-22 | PASS | 显式空元组 + 被真实消费 |
| T-23 | PASS | 409 ACTIVE_CHILDREN_EXIST 无部分写入 |
| T-24 | PASS | 软删后可删 |
| T-25 | PASS | 两种交错不变式 0 行 |
| T-26 | PASS | 共享锁 + 活跃确认 |
| T-27 | PASS | 非空且被消费（注入可失败） |
| T-28 | PASS | 无位置 / 自动发现结构 |
| T-29 | PASS | 不越界其它资源 |
| T-FE-01 | PASS | 三态 / Empty vs NotFound / error.code / 不重复守卫 |
| G-1 | PASS | 全库 `confdeltype='c'` 计数 0；bare_metals FK RESTRICT |
| G-2 | PASS | 列 14 / CHECK 恰 `{ck_bare_metals_status}` / partial unique predicate / `ix_bare_metals_cluster_id` |
| G-3 | PASS | 表集合 guard 演进（加 `bare_metals` / `0003`），非删除后不补 |
| G-4 | PASS | allow-list 恰 `{backend/app/deletion/service.py}`；注入第二写入路径 → FAILED |
| G-5 | PASS | 无 `<>''`/长度/trim/`/` CHECK；schema 无 `min_length/pattern/strip`；空串 / 空白 / `/` 原样存取 |
| G-6 | PASS | migration 可应用 / 可重复 / downgrade+upgrade 重建；head `0003`；`alembic check` 无漂移 |
| G-7 | PASS | 无通用表 / EAV / STI / 多态 / JSON(B) 列 |

**既有测试演进核查（是否被削弱）**：`test_migrations` / `test_schema.EXPECTED_TABLES` / `test_structure_guard.test_only_expected_tables_registered` 由「3 表」**演进而非删除**为「4 表」；`test_auth_guards.EXPECTED_GET_ROUTES` 增加两个 bare-metals GET 路由；`test_deletion_schema_guard` / `test_deletion_guards` 原样保留。`clusterDetailPage.spec.ts` 对「不呈现裸金属」的既有断言演进为「无裸金属数据表」（F002 起「查看裸金属」为导航入口，非数据呈现）。**无测试被删除后不补、无验证力削弱。**

## Database / Migration

- database 层 `true` 独立确认：`backend/migrations/versions/0003_f002_bare_metals.py` 新增；`0001` / `0002` 基线 **diff 为空**、未被改。
- 真实库 `csm_mig`：`upgrade head` ×2（第二次 no-op）、`current = 0003_f002_bare_metals (head)`、`alembic check` 无漂移、`downgrade base` + `upgrade head` 重建成功。
- 直连 `pg_constraint` / `pg_indexes` / `information_schema` 断言与 Database Handoff V-1 ~ V-5 逐项一致（14 列、CHECK / FK / PK 精确、FK RESTRICT / RESTRICT、partial unique predicate、无 collation / 触发器 / CASCADE）。
- 约束行为绕应用层直连验证（V-6 ~ V-11）：唯一性大小写敏感 / 跨 Cluster 可重 / 软删释放；status 默认 / UNKNOWN / NULL→23502 / 非法→23514；无效 FK→23503；父有子（含已软删）物理删除→23503；七列缺省 NULL；中文 / 空串 / 空白 / `/` 原样存取。

## Backend / API

- 5 端点行为经真实 uvicorn + 真实 PG 全量复核（见摘要 5 / 6）：契约字段集合、默认 IDLE、null 返回、必填校验、父存在性 404、唯一性 409 + 稳定 code、Empty / Not Found 区分、软删过滤、PATCH 可变字段封闭、PATCH 空 body / 不可变字段 400、DELETE 204 行保留、重复删除 404、无越界路由 / 参数、GET 无写副作用。
- 删除委托系统内唯一软删路径 `app/deletion/service.soft_delete()`（G-4 静态 + T-22 正向断言 + 注入可失败）。
- 创建侧 `_lock_active_parent` 对父 Cluster 行 `SELECT ... WHERE deleted_at IS NULL FOR SHARE` 并确认活跃；未命中 → `404`。T-25 / T-26 以真实 PostgreSQL 行锁验证两种交错与阻塞行为。
- F014 接线：`app/bare_metals/deletion.has_active_bare_metals` 提供检查，`app/clusters/deletion.CLUSTER_ACTIVE_CHILD_CHECKS = (has_active_bare_metals,)`，被 `clusters/service.delete_cluster` 消费。
- 未发现任何 AC 层面的后端契约违约。F012 / F013 / F014 / F015 既有测试全量保持全绿。

## Frontend

- `typecheck` 0；`test` 171 passed（15 文件，其后两次全量重跑一致）；`build` 成功。
- 列表页（`BareMetalListPage`）：`loading / empty / error / content` 四态互不相同；Empty（200 + `items==[]`，文案「该集群暂无裸金属」）与 Not Found（父 Cluster 404 → ErrorState「未找到资源」，`data-error-code=NOT_FOUND`）可区分；每行详情 / 删除入口（`ElPopconfirm` 二次确认，提交中 Loading 且禁重复）；登记入口。
- 详情页（`BareMetalDetailPage`）：独立 `not-found` 态与实际内容 / 其他 Error 区分；展示 13 字段，硬件 null 渲染「—」；编辑（PATCH）仅 status + 七硬件字段，**无 hostname / cluster_id 输入**；删除入口。
- 错误一律按 `error.code`（必要时 `details[].code`）分支渲染固定文案；组件测试显式使用「与展示无关」的 `message` 证明前端**不解析 message**。
- `useResourceDelete` / `BareMetalFormDialog` **未重复实现业务守卫**：重复 hostname、空 hostname、父存在性、状态合法性均直接提交由后端裁决；组件测试断言「重复 hostname 仍提交」「空 hostname 仍提交」「删除入口不预判 / 不禁用 / 不隐藏」。
- 前端真实 API client 对接真实后端 2/2 通过（见摘要 7）。

## Integration

**真实前后端集成 = PASS（实际执行，非 Mock / Fixture）**：

1. 真实 uvicorn（真实 PG `csm_api`）+ 原始 httpx：5 端点、分页、`cluster_id` 过滤、404/409/400/401、生命周期与 F014 端到端共 47 项断言全部通过。
2. **前端真实 API client**（`bareMetals.ts` / `auth.ts` / `http.ts`）经 happy-dom 管理真实 HttpOnly 会话 Cookie，对接真实后端完成：401 → 登录 → 登记 → 409 → 400 → 404 → 过滤 → PATCH → DELETE 204 → 404。临时探针运行后已删除。

**说明**：仅 Mock / Fixture 不足以判定集成通过；本 Feature 已用真实后端 + 真实前端 client 覆盖契约的主要成功与错误路径。

## Defects

### F002-T-01 — 既有前端用例在并行全量运行时偶发超时（LOW，Test Infra，非 F002 引入）

- **ID**：F002-T-01
- **Severity**：LOW（偶发、时序敏感；不削弱任何 AC 结论）
- **Layer / Owner**：Test Infra（`frontend/tests/appAuth.spec.ts`，F013 时代既有用例）→ 主协调器
- **Location**：`frontend/tests/appAuth.spec.ts`（全局 401 用例，`vi.waitFor` 默认 1000ms 超时）；`frontend/vite.config.ts` 已注释已知并行时序敏感并设 `maxWorkers: 4`
- **复现步骤**：`cd frontend && npm run test` 全量并行运行（首次运行触发一次）。
- **期望**：全部用例稳定通过。
- **实际**：首次全量运行 `1 failed | 170 passed`，失败于 `appAuth.spec.ts:189`（`expect(viewOf(wrapper)).toBe('login')` 超时）；随后 `npx vitest run tests/appAuth.spec.ts` 隔离运行 7/7 通过，且两次全量重跑均 `171 passed`。
- **影响**：纯测试时序抖动，与 F002 业务实现无关（该用例位于集群列表全局 401 路径，F002 未改动其依赖的 `ClusterListPage` / `resetToLogin`）；不影响任何 AC 判定。建议后续统一收紧 `vi.waitFor` 超时或进一步限制 worker 并发。
- **Owner**：主协调器（Test Infra）。

**除 F002-T-01（LOW，Test Infra）外，未发现 BLOCKER / HIGH / MEDIUM 缺陷。未发现 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND 缺陷。**

## Unverified Areas

1. **浏览器级前端 E2E / 视觉 / 真实 DOM**：无浏览器自动化环境；前端行为经 vitest（happy-dom）组件测试与真实 API client 集成验证，未在真实浏览器观察渲染 / 网络 / 视觉。
2. **NQ-9（`cluster_id` FK 违规的字段回退解析）**：创建路径因 `FOR SHARE` 预检**不会**触发 `23503`，应用路径不可达；DB 层直插无效 `cluster_id` → `23503` 已验证，但经应用映射后 `details[].field` 是否会被 F012 F-02 截断为 `cluster` **未验证**（属 Non-blocking Open Question，不属任何 AC）。
3. **多 uvicorn worker / 跨进程并发**：并发端到端以独立连接 / 线程验证行锁协议，未做多 worker 压测（无产品需求，V1 单机内网）。
4. **`POST` 显式非 `IDLE` 状态（NQ-3）**：Architecture PROPOSED 7 允许并已按此实现与验证；属产品侧 PROPOSED，未经用户最终裁定——不影响 AC-07（缺省 IDLE）的判定。
5. **静态 guard 的动态 SQL 绕过**：承 F014 已知残余风险，未穷举所有动态构造方式。

## Test Status

`READY FOR REVIEW`

依据：AC-01 ~ AC-30 全部有结果、无 FAIL / BLOCKED / NOT TESTED；Architecture Test Work T-01 ~ T-30 与 G-1 ~ G-7 全部 PASS，无 skipped；真实前后端集成已**实际执行**（真实 uvicorn + 真实 PG + 前端真实 API client）；工程门禁（ruff / format / 全量 pytest 279 / 前端 typecheck + test + build）全绿；既有测试随增表演进而非削弱；fail-open 与唯一软删路径 guard 经对抗注入确认真实可失败并逐字节还原。无 BLOCKER / HIGH / 需实现方修复的 MEDIUM 缺陷（仅 1 个 LOW Test Infra 偶发项）。

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-30 全部有结果并 **PASS**（无 FAIL / BLOCKED / NOT TESTED）。
- Architecture Test Work T-01 ~ T-30 / G-1 ~ G-7 / T-FE-01 全部 PASS（96 项专项 + 279 项全量，无 skipped）。
- 数据库：`bare_metals` 14 列 / FK RESTRICT / CHECK 四值 / partial unique predicate / 无 CASCADE / 无触发器 / 无 COLLATE 与 Database Handoff 一致；`0001` / `0002` 基线未改；migration 可应用 / 可重复 / 可重建；`alembic check` 无漂移。
- 后端：5 端点契约行为（字段封闭、默认 IDLE、null 返回、校验 400、父 404、唯一 409、Empty vs Not Found、软删过滤、PATCH 封闭、DELETE 204 行保留、无越界）；创建侧 `FOR SHARE` + 并发不变式 0 行；F014 端到端 409 / 204。
- 前端：三态互不相同、Empty vs Not Found 可区分、`error.code` 分支、不解析 message、不重复实现业务守卫；`typecheck` / `test` / `build` 全绿。
- 真实前后端集成实际执行：真实 uvicorn + 真实 PG + 前端真实 API client。
- guard 真实可失败：T-27 fail-open 与 G-4 allow-list 对抗注入均 FAILED，逐字节还原（`git status` 干净）。
- 既有 guard 随增表演进而非削弱。

### Not Verified

- 浏览器级 E2E / 视觉 / 真实 DOM。
- NQ-9 应用层 `23503` 的 `cluster_id` 字段回退解析（应用路径不可达）。
- 多 worker / 跨进程并发压测。
- 静态 guard 对动态 SQL 构造的穷举覆盖（承 F014 已知残余风险）。

### Blocking Issues

None。

### Defect Owner

- F002-T-01（LOW，Test Infra 偶发时序）→ 主协调器。

---

GIT: NONE
