# Test Report — F012 项目基础框架与运行环境

> Status: **READY FOR REVIEW**
> Author Role: tester
> Date: 2026-09-15
> Feature: F012（ENABLER，E07，P0）
> 分支：`feature/F012-project-foundation`，实现 HEAD `9764326`，起点 `develop` `2c2a753`

---

## Feature

F012 — 项目基础框架与运行环境：资源 Feature 的共享基座（可运行骨架、显式资源建模、统一校验 / 错误信封 / 冲突映射、分页、事务边界、`deleted_at IS NULL` 过滤原语、Alembic 基线、前端三态基座、非产品自检面 `/_foundation/*`）。

## Test Basis

- `docs/product/handoffs/f012-project-foundation.md`（AC-01 ~ AC-09）
- `docs/architecture/f012-project-foundation-handoff.md`（`## Test Work` T1 ~ T14、REQUIRED、Constraints）
- `docs/api/f012-project-foundation.md`（契约，`READY`）
- `docs/api/api-conventions.md`（`READY`）
- `docs/database/csm-v1-schema-design.md`、`docs/database/f012-baseline-migration.md`（`READY FOR DATABASE IMPLEMENTATION`）
- `docs/product/requirements.md` §4/§5/§20/§21/§22/§23/§24/§25、`docs/product/domain-model.md`、`.pi/skills/resource-domain/SKILL.md`
- ADR-0001 ~ ADR-0005（`ACCEPTED`）

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（`.venv`） |
| PostgreSQL | **16.2**（pgserver 启动的真实实例，Unix socket） |
| 数据库 locale | `datcollate = zh_CN.UTF-8`，`datctype = zh_CN.UTF-8` |
| 数据库 encoding | `UTF8`（`pg_encoding_to_char(encoding)`） |
| Node / npm | v24.14.0 / 11.9.0 |
| Backend 启动 | `uvicorn app.main:app --app-dir backend`（dev:8000 / prod:8766，真实 PG） |
| Frontend 启动 | `npm run dev -- --port 5199`（vite 反向代理 `/api` + `/_foundation`） |
| 测试库 | `CSM_TEST_DATABASE_URL=postgresql+psycopg://postgres:@/postgres?host=…`；另建 `csm_raw` / `csm_api` / `csm_f012` 隔离验证 |

**locale 说明（重点）**：本机环境 locale 为 `zh_CN.UTF-8`，pgserver 实例即取此 locale；架构 Handoff Q5 推荐 dev provisioning 使用 `C.UTF-8` / `en_US.UTF-8`。实测 `zh_CN.UTF-8` 为**大小写敏感** locale，`SELECT ('cluster-a' = 'Cluster-A')` 返回 `false`，§22 语义成立。统计与排序语义不属 F012 验收范围。locale 固定要求须由 F015 部署文档承载（F012 未交付，见「未验证」）。

---

## 独立执行摘要（真实命令与输出）

### 1. 后端实现方测试（独立重跑）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/postgres?host=/tmp/f012-test/pgdata" \
  .venv/bin/python -m pytest -v
...
collected 38 items
=============================== 38 passed, 2 warnings in 15.19s ===============================
```

38 项全部通过（含 `tests/database/*` 的原始 psycopg 断言、结构 guard、自检面隔离）。此后所有对抗性验证均**另起原始连接 / 另建数据库**独立完成，不复用实现方结论。

### 2. 前端（独立重跑）

```text
$ cd frontend && npm run typecheck   → exit 0
$ npm run test                       → Test Files 5 passed (5)，Tests 32 passed (32)
$ npm run build                      → vue-tsc 通过 + vite build 成功（dist/index-*.js 1,010.10 kB）
```

### 3. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests      → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 40 files already formatted  exit 0
```

### 4. 迁移（真实库，独立执行）

```text
$ alembic upgrade head        → Running upgrade  -> 0001_f012_baseline
$ alembic upgrade head        → （no-op，无 DDL）
$ alembic current             → 0001_f012_baseline (head)
$ alembic downgrade base      → Running downgrade 0001_f012_baseline -> （clusters 消失，仅剩 alembic_version）
$ alembic upgrade head        → 重建成功
$ alembic check               → No new upgrade operations detected.（模型与库无漂移）
```

迁移后实际 schema（`csm_raw`）：

```text
tables:      ['alembic_version', 'clusters']
columns:     id bigint NOT NULL / name text NOT NULL / created_at timestamptz NN DEFAULT now() /
             updated_at timestamptz NN DEFAULT now() / deleted_at timestamptz NULL
constraints: ck_clusters_name_no_slash = CHECK (strpos(name,'/') = 0); pk_clusters = PRIMARY KEY (id)
indexes:     ux_clusters_name_active = UNIQUE (name) WHERE (deleted_at IS NULL)
collation:   datcollate/datctype = zh_CN.UTF-8, encoding = UTF8
```

与 Database Handoff §4 DDL 逐项一致；无 extension、无触发器、无 `COLLATE`、无额外表。

### 5. 真实服务集成（dev + prod uvicorn）

```text
GET  /api/health                          → 200 {"status":"ok","database":"ok"}
POST /_foundation/clusters {"cluster-a"}  → 201 {"id":1,"name":"cluster-a",...}   （无 deleted_at）
POST /_foundation/clusters {"Cluster-A"}  → 201 {"id":2,...}                      （与 cluster-a 共存）
GET  /_foundation/clusters                → 200 total=2
POST /_foundation/clusters {"cluster-a"}  → 409 CONFLICT  details[field=name]
POST /_foundation/clusters {"a/b"}        → 400 VALIDATION_ERROR details[field=name]
POST /_foundation/clusters {}             → 400 VALIDATION_ERROR details[field=name]
```

通过 vite dev proxy（`http://127.0.0.1:5199`）访问真实后端：

```text
GET http://127.0.0.1:5199/api/health            → 200 {"status":"ok","database":"ok"}
GET http://127.0.0.1:5199/_foundation/clusters  → 200 {items:[...],total:3,...}
GET http://127.0.0.1:5199/_foundation/error     → 500 {"error":{"code":"INTERNAL_ERROR",...}}
```

并用**前端真实 API client**（`src/api/foundation.ts` + `src/api/http.ts`，临时 vitest 探针，运行后删除）对接真实后端：

```text
listFoundationClusters() → page=1, page_size=50, items 字段恰为 {id,name,created_at,updated_at}
getFoundationError()     → reject ApiError{status:500, code:"INTERNAL_ERROR"}
→ Tests 2 passed
```

---

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
|---|---|---|---|
| AC-01 可运行骨架与文档 | 按 README 从 3.1 到 3.6 逐步执行：建库、装依赖、alembic、uvicorn、前端 dev | **PASS**（计时未独立测量） | `alembic upgrade head` 成功；`GET /api/health` 200；`vite` ready 后 `GET /` 200。README + `frontend/README.md` + `.env.example` + `Makefile` + `docker-compose.dev.yml` 齐全；步骤可复现。**未**从 pristine checkout 计时（`node_modules`、`.venv`、PG 已存在） |
| AC-02 可运行证明 | 真实 uvicorn `GET /api/health` | **PASS** | 200 `{"status":"ok","database":"ok"}`；DB 不可达（offline DSN）→ 500 `INTERNAL_ERROR` 信封 |
| AC-03 显式资源建模 | T2 白名单 + T10 结构 guard（含对抗注入） | **PASS** | 迁移后仅 `alembic_version` + `clusters`；`Base.metadata.tables == {"clusters"}`。对抗注入 `resources` 表 / JSON 列 / EAV 形态均被 guard 捕获失败 |
| AC-04 冲突保存前被阻止（不依赖 UI） | 原始 psycopg 直连，绕应用层 | **PASS** | 直插活跃重名 → `23505`；直插含 `/` → `23514`；直插 NULL name → `23502`。均被数据库拒绝 |
| AC-05 大小写敏感在数据层成立 | 原始 psycopg + 真实连接 | **PASS** | `SELECT ('cluster-a'='Cluster-A')` → `false`；两值可共存；第二活跃同名 → `23505` |
| AC-06 错误可见具体字段与原因 | API + 真实 uvicorn | **PASS** | 400 均含 `error.code=VALIDATION_ERROR` + `details[].field`：缺失/类型错/`page=0`/`page_size=0`/`page_size=201`/`page_size=abc`/`23514` 全部给出正确字段；`23505` → 409 `CONFLICT` + `field=name` |
| AC-07 中文往返正确 | 原始 psycopg + API | **PASS** | DB：`高性能计算集群-A` 写入/读出/等值命中；API：POST 201 回显一致、list 命中；`server_encoding=UTF8` |
| AC-08 基座可复用、契约单一权威 | 代码审阅 + grep | **PASS** | 错误信封仅由 `common/errors.py:error_envelope` 构造，所有 handler 复用；分页 / 事务边界 / active 过滤均单点。F012 尚无其他资源 Feature，多 Feature 复用只能待 F001+ 验证 |
| AC-09 不承载资源业务规则 | 代码审阅 + guard | **PASS** | `/_foundation` 无 `/` 校验、无唯一性预检、无 `by-name`、无状态、无父删子拦；`clusters` 仅载体。guard 保证无其他资源表 |

---

## Test Work T1 ~ T14

| # | 测试 | Result | 证据 / 说明 |
|---|---|---|---|
| T1 | 迁移可应用 / 可重复 / 可重建 | **PASS** | `upgrade head` ×2、`downgrade base && upgrade head` 全部成功；`alembic check` 无漂移 |
| T2 | 表集合白名单 + 约束/索引存在 | **PASS** | 独立查询 `information_schema` / `pg_indexes` / `pg_constraint`：仅 2 表，约束与 partial predicate 正确，列级无 collation |
| T3 | 直 SQL 大小写敏感共存 | **PASS** | 原始 psycopg：共存 + 等值 `false` |
| T4 | 直 SQL 活跃同名 → 23505 | **PASS** | 原始 psycopg 捕获 `UniqueViolation.sqlstate == "23505"` |
| T5 | 直 SQL 软删后可重建 / 已删不入活跃查询 / 多条已删同名 | **PASS** | 原始 psycopg。历史保留、活跃视图不返回已删行 |
| T6 | 直 SQL 含 `/` → 23514 | **PASS** | 原始 psycopg 捕获 `CheckViolation.sqlstate == "23514"` |
| T7 | 中文往返（DB + 应用） | **PASS** | DB 与 HTTP 两侧均验证 |
| T8 | 字段校验 → 400 + field | **PASS** | 真实 uvicorn 逐项验证（含分页 4 种非法） |
| T9 | 自检面 create→list→get→update→soft-delete | **PASS** | curl 全链路；删除后 list 不含该项、get/PATCH/DELETE 再操作 → 404 |
| T10 | 结构 guard 有效性 | **PASS** | 除实现方用例通过外，对抗式向 `Base.metadata` 注入违规结构，guard 均正确失败（非空转） |
| T11 | lint 可执行 + 真实数据库断言测试 | **PASS** | ruff check/format exit 0；`tests/database/test_constraints.py` 用原始 psycopg 断言 23505/23514 |
| T12 | 前端三态 + Error 由 code 驱动 | **PASS** | 32 前端测试通过；另用临时对抗探针证明「同 message 不同 code → 不同标题」；`ErrorState` switch 仅依赖 `props.error.code` |
| T13 | 生产配置下自检面不可达 | **PASS** | 真实 `CSM_ENVIRONMENT=prod` uvicorn：6 个端点 × 4 方法（GET/POST/PATCH/DELETE）共 12 请求全部 404 `NOT_FOUND` |
| T14 | `GET /api/health` → 200 | **PASS** | 真实服务与 TestClient 均 200；DB 不可达 → 500 信封 |

### 对抗性 / 边界检查（实现方测试之外的补充）

| 检查 | 结果 | 证据 |
|---|---|---|
| `details[].field` 各 SQLSTATE 分支 | 部分缺陷 | 23502→`name`、23514→`name`、23505→`name` 正确；23503 在表不在 `Base.metadata` 时回退逻辑给出 `field="cluster"`（实际列 `cluster_id`）→ Finding F-02 |
| 错误信封在所有错误路径一致 | 结构一致，1 处语义问题 | 404 未匹配路由 → `NOT_FOUND`；500 → `INTERNAL_ERROR`；**405 → `code=INTERNAL_ERROR`**（语义错配）→ Finding F-01 |
| `deleted_at` 是否出现在对外响应 | 未出现 | 创建/列表/读取/PATCH 响应键恰为 `{id,name,created_at,updated_at}`；前端真实 client 也断言字段集合 |
| 分页非法参数 | 全部 400 | `page=0`、`page=-1`、`page_size=0`、`page_size=201`、`page_size=abc` 均 400 + 正确 field；`page_size=200` 边界 200 OK；`page=100` → 200 空 items、total 不变。分页切片 `page=2/3 size=2` 数学正确 |
| 只读无副作用 | 无写入 | GET 前后逐行比较 `updated_at` / `deleted_at` / row count，完全一致 |
| 空列表 vs 404 | 区分正确 | 无活跃行 → 200 `items=[]`；不存在 / 已软删 id → 404 `NOT_FOUND` |
| 中文经 HTTP 往返 | 正确 | POST 回显 + list 逐字一致，无乱码 |
| `page_size` 默认 / 上限 | 符合契约 | 默认 50；200 接受；201 拒绝（架构 PROPOSED 上限 200） |

---

## Database / Migration

见上。结论：与 Database Handoff 一致，无额外 Schema，约束 / 索引 / 默认值 / 时序均正确；`downgrade base` 可清空并重建。**注意**：`downgrade` 为破坏性（DROP），Per Handoff 生产禁用，测试仅在专用库执行，未触碰任何未知或生产数据库。

## Backend / API

- 产品端点仅 `GET /api/health`，行为与契约 §2.1 一致。
- 非产品面 `/_foundation/*` 六个端点行为与契约 §4 一致（含 404/409/400 语义、`deleted_at` 不暴露）。
- 统一 SQLSTATE 映射：23502/23514 → 400；23505/23503 → 409；未识别 SQLSTATE → 500 `INTERNAL_ERROR` 信封（用注入路由验证）。
- 未处理异常 → 500 `INTERNAL_ERROR` 信封（用注入路由验证）。

## Frontend

- `typecheck` / `test`(32) / `build` 全部通过。
- `ErrorState` 分支**只**读 `error.code`（源码 switch 确认；对抗探针证明同 message 不同 code 渲染不同标题；message 仅作展示）。
- `ListStates` 对 Loading / Error / Empty / content 互斥；404 `NOT_FOUND` 与 Empty 渲染不同文案。
- 生产构建 `App.vue` 用 `import.meta.env.DEV` 静态替换，自检页不在生产渲染。

## Integration

**已验证（真实前后端）**：vite dev proxy → 真实 dev 后端 → 真实 PostgreSQL；并用前端真实 API client 对接真实 500 / 分页响应解析成功（临时探针，运行后已删除）。

**NOT TESTED**：浏览器级 E2E（无 Playwright 等工具，未在真实浏览器中观察 DOM / 网络 / 视觉）；生产构建产物在真实 nginx 下的部署（属 F015）。

---

## Defects

无 BLOCKER / HIGH / MEDIUM。

### F-01 — 未映射状态码统一标为 `INTERNAL_ERROR`（LOW）

- **Layer / Owner**：Backend
- **Location**：`backend/app/common/error_handlers.py:21-27, 61-64`（`_HTTP_STATUS_CODE_MAP.get(exc.status_code, "INTERNAL_ERROR")`）
- **现象**：HTTP 405（Method Not Allowed）返回 `{"error":{"code":"INTERNAL_ERROR","message":"Method Not Allowed","details":[]}}`。前端 `ErrorState` 会将其渲染为「服务器内部错误」，误导用户。
- **复现**：`curl -X POST http://127.0.0.1:8765/api/health` → HTTP 405，`error.code=INTERNAL_ERROR`。
- **期望**：4xx 客户端错误不应标为 `INTERNAL_ERROR`（契约 §6 未定义 405；建议补充映射或对未知 4xx 使用 `VALIDATION_ERROR` / 通用客户端码）。
- **实际**：`INTERNAL_ERROR`。
- **影响**：仅影响非前端正常流程的畸形请求；不违反已定义契约条目，故 LOW。

### F-02 — FK 违规字段回退解析截断多词列名（LOW）

- **Layer / Owner**：Backend
- **Location**：`backend/app/common/sqlstate.py`（`_field_from_constraint_name` 仅返回 `tokens[0]`）
- **现象**：当违规表不在 `Base.metadata` 时，`23503` 的 `details[].field` 由约束名回退推断。对约束 `…_cluster_id_fkey` / `fk_…_cluster_id` 返回 `"cluster"`（实际列 `cluster_id`）。同理 `…_bare_metal_id` 等会截断。
- **复现**：原始 psycopg 在 `clusters` 上建引用子表并制造 23503，经 `map_integrity_error` → `field='cluster'`；而列名为 `cluster_id`。
- **期望**：`details[].field` 给出真实列名（`cluster_id`），或至少完整列名。
- **实际**：返回首词 `cluster`。
- **影响**：F012 无 FK 表，API 不可达，故 LOW；但对 F002/F004/F005 是潜在风险。真实项目 FK 命名下通常先命中 `_field_from_metadata`（表在 metadata 中）可正确得到 `cluster_id`，仅当表未进入 metadata 时暴露。

### F-03 — `CSM_ENVIRONMENT` 未设置时自检面默认挂载（LOW，风险提示）

- **Layer / Owner**：Architect / Backend（默认值设计）
- **现象**：`Settings.environment` 默认 `"dev"`，`foundation_enabled` 因此在未显式设置时返回 True。若生产部署遗漏 `CSM_ENVIRONMENT=prod`，`/_foundation/*` 将可达（fail-open）。
- **复现**：不设 `CSM_ENVIRONMENT` 启动 → `GET /_foundation/clusters` 可达（200，非 404）。
- **期望**：生产配置下不可达；默认值策略上建议 fail-closed 或部署层强制显式设置。
- **实际**：默认 dev，fail-open。
- **影响**：契约以「生产配置」为条件，实现与契约字面一致，故不作为契约违约，仅记为部署风险 LOW；F015 需确保显式 `prod`。

### F-04 — 测试夹具对 DSN 执行 `DROP SCHEMA … CASCADE` 且可回退到 `CSM_DATABASE_URL`（LOW，TEST INFRA）

> **状态：已修复（RESOLVED）** —— 由协调器在同批提交 `dbff989` 中处理。本节描述的是修复前的代码，保留以供追溯。
> 修复内容：`get_dsn()` 不再回退到 `CSM_DATABASE_URL`（测试库必须显式指定）；新增 `assert_safe_to_reset()` 纵深防御，当测试 DSN 与应用 DSN 相同时直接拒绝 reset，除非显式设置 `CSM_ALLOW_DESTRUCTIVE_TEST_RESET=1`。修复后重跑：有 DSN 时 38 passed，无 DSN 时 20 passed / 18 skipped。

- **Layer / Owner**：TEST INFRA（主协调器）
- **Location**：`tests/database/helpers.py`（`get_dsn` 优先 `CSM_TEST_DATABASE_URL`，回退 `CSM_DATABASE_URL`；`reset_schema` 执行 `DROP SCHEMA IF EXISTS public CASCADE`）
- **现象**：若开发者仅导出 `CSM_DATABASE_URL`（例如其开发库）而未设 `CSM_TEST_DATABASE_URL`，测试会**清空该库 public schema**。
- **期望**：测试只作用于显式测试库，或在 DSN 未显式标记为测试库时拒绝 reset。
- **实际**：静默回退并破坏性 reset。
- **影响**：属测试基础设施安全，不影响产品行为；LOW。

---

## Unverified Areas

1. **AC-01 的「30 分钟」计时**：未从 pristine checkout（全新 machine / 全新 DB / 无 `node_modules`、`.venv`）计时。仅验证文档步骤逐一可执行并最终可运行。
2. **F015 部署 locale 固定**：F012 未交付部署文档；「locale 不得被静默改变」的持续推进要求只能待 F015。本环境在 `zh_CN.UTF-8`（非推荐的 `C.UTF-8`）下语义仍成立。
3. **浏览器级前端 E2E / 视觉验证**：无浏览器自动化环境；前端行为通过 vitest（happy-dom）与真实 HTTP 集成验证，未在真实浏览器观察 DOM。
4. **生产构建产物的真实部署（nginx + 内网）**：属 F015。
5. **`23502` / `23503` 经 API 的端到端路径**：F012 无 FK 表、且 `name` 由 schema 强制，故只能做映射函数级验证，API 层不可达。
6. **多资源 Feature 对基座的实际复用（AC-08 后半）**：F012 尚无其他资源 Feature，只能验证基座存在且为单一权威，无法验证真实复用。
7. **未映射状态码（405 等）的契约期望**：契约未定义，F-01 按「语义错配」而非「契约违约」记录。

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-09 全部 PASS；T1 ~ T14 全部 PASS。
- 数据库层（绕应用层原始连接）：大小写敏感、活跃唯一性（23505）、CHECK（23514）、NOT NULL（23502）、软删释放唯一性、中文往返、无 `COLLATE`、表/约束/索引与 Database Handoff 一致。
- 迁移：可应用 / 可重复 / 可重建 / 模型无漂移。
- API：health、自检面六端点语义、分页边界、错误信封结构、`details[].field`（23502/23505/23514）、read-only 无副作用、`deleted_at` 不暴露。
- 生产隔离：`CSM_ENVIRONMENT=prod` 下 12 条请求全部 404。
- 结构 guard：对抗注入证明其会真实失败，非空转。
- 前端：typecheck / 32 测试 / build 通过；Error 态由 `error.code` 驱动；三态互斥。
- 真实前后端集成：vite proxy → 真实后端 → 真实 PG，且前端真实 client 解析真实响应成功。

### Not Verified

见「Unverified Areas」：30 分钟计时、F015 部署 locale 文档、浏览器 E2E、生产部署、23502/23503 API 路径、多 Feature 复用。

### Blocking Issues

None。

### Defect Owner

F-01 → Backend；F-02 → Backend；F-03 → Architect / Backend（风险提示）；F-04 → TEST INFRA（主协调器）。

处置：F-01 / F-02 / F-03 为 Review follow-up（F-03 经 Reviewer 复核上调为 MEDIUM，不阻塞 F012，归属 F015）；**F-04 已在本批提交中修复**。

---

## Test Status

`READY FOR REVIEW`

---

GIT: git log --oneline -5
GIT: git status --short
GIT: git branch --show-current