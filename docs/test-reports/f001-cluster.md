# Test Report — F001 Cluster 登记与管理

> Status: **READY FOR REVIEW**
> Author Role: tester
> Date: 2026-09-15
> Feature: F001（E01，P0，`depends_on: [F012]`）
> 分支：`feature/F001-cluster`，实现 HEAD `cb7f992`，起点 `develop` `7a99745`

---

## Feature

F001 — Cluster 登记与管理：Cluster 的登记（`POST`）、列表（`GET` 分页）、按 id 详情、`by-name` 只读别名、名称更新（`PATCH`）、读取路径软删过滤、R-CLUSTER-005 双保险、`/_foundation/*` 彻底移除、前端 Cluster 列表 / 详情页三态。

## Test Basis

- `docs/product/handoffs/f001-cluster.md`（AC-01 ~ AC-14，验收依据）
- `docs/architecture/f001-cluster-handoff.md`（Test Work A01 ~ A16 / G1 ~ G3 / T8′ / T9′ / T13′、REQUIRED、Constraints、核心问题 1/2/8）
- `docs/api/f001-cluster.md`（契约，`READY`）、`docs/api/api-conventions.md`（`READY`）
- `docs/product/handoffs/f012-project-foundation.md`（F012 判据 4/5/6）、`docs/architecture/f012-project-foundation-handoff.md`
- `docs/database/csm-v1-schema-design.md`、`docs/database/f012-baseline-migration.md`
- `docs/product/requirements.md` §7/§17/§21/§22、`docs/product/domain-model.md`
- ADR-0001 ~ ADR-0005（`ACCEPTED`）
- `docs/test-reports/f012-project-foundation.md`（同格式先例）

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（`.venv`） |
| PostgreSQL | **16.2**（`pgserver` 真实实例，Unix socket，目录 `/tmp/f001-test`） |
| 数据库 locale / encoding | `datcollate = datctype = zh_CN.UTF-8`；`server_encoding = UTF8`（`pg_encoding_to_char` = `UTF8`） |
| Node / npm | v24.14.0 / 11.9.0 |
| 测试库 | `CSM_TEST_DATABASE_URL=postgresql+psycopg://postgres:@/postgres?host=/tmp/f001-test`；另建隔离库 `csm_mig` / `csm_adv` / `csm_api` / `csm_live` / `csm_a04` |
| 真实服务 | `uvicorn app.main:app --app-dir backend`（prod 8766、无 `CSM_ENVIRONMENT` 8767，真实 PG） |
| 前端 | `npm run typecheck` / `npm run test`（vitest + happy-dom）/ `npm run build` |

环境为**全新**：`pgserver` 实例由本次测试新建；测试库由 `alembic upgrade head` 从空库建立。所有临时目录 `/tmp/f001-test`、`/tmp/f001-backup` 与 uvicorn / postgres 进程已按 **PID 精确 kill** 并清理，未使用 `pkill -f`。

---

## 独立执行摘要（真实命令与输出）

### 1. 后端实现方测试（独立重跑）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/postgres?host=/tmp/f001-test" \
  .venv/bin/python -m pytest -q
77 passed, 2 warnings in 36.02s
```

77 项全部通过（`tests/database/*` 原始 psycopg 断言 + API 行为 + 结构 / guard）。对抗性验证全部**另起原始连接 / 另建数据库 / 真实 uvicorn**独立完成，未复制实现方结论。

### 2. 前端（独立重跑）

```text
$ cd frontend && npm run typecheck  → exit 0
$ npm run test                       → Test Files 8 passed (8)，Tests 56 passed (56)
$ npm run build                      → vue-tsc 通过 + vite build 成功（dist/assets/index-*.js 1,010.28 kB）
```

### 3. lint / format（工程门禁）

```text
$ .venv/bin/python -m ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/python -m ruff format --check backend tests → 43 files already formatted  exit 0
```

### 4. 迁移（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head   → Running upgrade -> 0001_f012_baseline  （成功）
$ alembic upgrade head   → no-op（无 DDL）
$ alembic current        → 0001_f012_baseline (head)
$ alembic check          → No new upgrade operations detected.
$ alembic downgrade base → Running downgrade 0001_f012_baseline ->
$ alembic upgrade head   → 重建成功
```

迁移后实际 Schema（独立查询）：

```text
tables:      ['alembic_version', 'clusters']
columns:     id bigint NOT NULL / name text NOT NULL / created_at timestamptz NN DEFAULT now() /
             updated_at timestamptz NN DEFAULT now() / deleted_at timestamptz NULL
constraints: ck_clusters_name_no_slash = CHECK (strpos(name,'/'::text)=0); pk_clusters = PRIMARY KEY (id)
indexes:     ux_clusters_name_active = UNIQUE (name) WHERE (deleted_at IS NULL)
extensions:  ['plpgsql']（仅默认）；triggers: []（无）
```

与 Database Handoff §4 逐项一致：无额外表、无额外列、无额外 CHECK、无触发器、无显式 `COLLATE`。

### 5. 真实服务集成（真实 uvicorn）

```text
GET  /api/health                                     → 200 {"status":"ok","database":"ok"}
POST /api/clusters {"name":"cluster-a"}              → 201 {...无 deleted_at / status，键恰为 4 个}
POST /api/clusters {"name":"Cluster-A"}              → 201（与 cluster-a 共存）
POST /api/clusters {"name":"cluster-a"}              → 409 CONFLICT details[field=name,code=DUPLICATE]
GET  /api/clusters/by-name/Cluster-A                 → 200（只命中 Cluster-A）
GET  /api/clusters/by-name/nope                      → 404 NOT_FOUND details=[]
DELETE /api/clusters/1                               → 405（行保持活跃）
POST /api/clusters {"name":"高性能计算集群-A"}         → 201 回显一致；by-name 百分号编码命中
```

**前后端真实集成**：将前端真实 API client（`frontend/src/api/clusters.ts` + `http.ts`）接入真实运行中的后端（127.0.0.1:8767），以临时 vitest 探针（运行后删除）验证：

```text
listClusters()      → 解析真实分页响应，字段集合恰为 {id,name,created_at,updated_at}
getClusterByName()  → 大小写敏感命中；getCluster(id) 逐字段一致
createCluster(重复)  → ApiError{status:409, code:"CONFLICT", details[].field=="name"}
```

---

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
| --- | --- | --- | --- |
| AC-01 登记成功 | A01 + 真实 HTTP | **PASS** | `201`，响应键**恰为** `{id,name,created_at,updated_at}`；无 `deleted_at`、无状态字段；DB 新增 1 活跃行 |
| AC-02 名称必填 | A02 | **PASS** | `{}` / `{"name":123}` / `{"name":null}` → `400 VALIDATION_ERROR`，`details[].field=="name"`（`Field required` / `valid string`），`total_rows==0` |
| AC-03 `/` 在 API 层被拒且非 500 | A03（POST + PATCH） | **PASS** | `400`，`details[].field=="name"`，`details[].code=="INVALID_CHARACTER"`，无写入；未出现 `500` |
| AC-04 活跃名称全局唯一 | A05 + **A04 独立复现** | **PASS** | 常规重复 → `409 CONFLICT` field=name，活跃行数=1；**绕过预检**（monkeypatch 为 no-op）后仍 `409`，且信封 message 变为 `数据完整性冲突`（来自 `integrity_error_handler`），证明是**数据库 `ux_clusters_name_active`** 拦截，非预检 |
| AC-05 大小写敏感 | A06 + 原始 SQL | **PASS** | `cluster-a` 与 `Cluster-A` 均 `201`；`by-name/Cluster-A` 只命中后者；原始连接 `SELECT 'cluster-a'='Cluster-A'` → `false` |
| AC-06 by-name 别名 | A07 + 真实 HTTP | **PASS** | 命中时与 `GET /{id}` 返回体 `==`（逐字段一致）；未命中 `404 NOT_FOUND`，`details==[]` |
| AC-07 已删不参与查询与解析 | A08（**绕应用层**原始连接预置 `deleted_at`） | **PASS** | 不在 `items`、`total==0`；`GET /{id}` 与 `by-name` 均 `404`；同名可重新 `201`（R-DELETE-006） |
| AC-08 列表 / 分页 / Empty | A09 + 真实 HTTP | **PASS** | 空库 `200 {"items":[],"total":0,"page":1,"page_size":50}`（**非 404**）；`page_size=2` 分页切片正确；`page=0`/`page_size=0`/`page_size=201`/`page=x` → `400` field=`page`/`page_size` |
| AC-09 无状态 | A10 + Schema 内省 | **PASS** | `clusters` 列集合**恰为** `{id,name,created_at,updated_at,deleted_at}`；`Base.metadata`、`information_schema`、请求 / 响应体均无 `status`/`state` |
| AC-10 无上级 / 位置 | A11 + Schema 内省 | **PASS** | 列 / `Base.metadata` / schema / 响应体均无 `data_center`/`rack`/`u_position`/`site`/`campus` 等 |
| AC-11 中文往返 | A12 + 原始 SQL + 真实 HTTP | **PASS** | `高性能计算集群-A`：`201` 回显、list 字面值读出、`by-name` 百分号编码精确命中；DB 侧等值比较命中，`server_encoding=UTF8` |
| AC-12 更新复用同一套规则 | A13 + 真实 HTTP | **PASS** | `PATCH` 改名 → `200` 新值、`id`/`created_at` 不变；旧名立即可 `201`；改活跃重复名 `409`；改含 `/` `400`；不存在 / 已软删 id `404`；**改成自身当前名 `200`** |
| AC-13 单一路径 / 自检面清理 | A14 + A15（静态 + 运行时） | **PASS（附 2 项 LOW guard-gap）** | 见下「对抗注入实验」：`backend/app/**` 中 `deleted_at` 赋值数 = 0（静态扫描 0 处）；`app/foundation/` 目录不存在；`Settings` 无 `foundation_enabled`；`/_foundation/*` 在 dev/test/prod 及无 `CSM_ENVIRONMENT` 下**全部 404**；`DELETE /api/clusters/{id}` 不软删 |
| AC-14 前端三态与 Not Found 可区分 | A16 + 对抗探针 | **PASS** | 列表 Loading / Empty / Error `data-state` 互不相同且渲染不同；详情 `not-found` 与列表 `empty` 的 `data-state` 与文案**均不同**；Error 由 `error.code` 驱动 |

**AC 结论：AC-01 ~ AC-14 全部 PASS，无 FAIL / BLOCKED / NOT TESTED。**

---

## Test Work A01 ~ A16 / G1 ~ G3 / T8′ / T9′ / T13′

| # | 结果 | 证据 |
| --- | --- | --- |
| A01 | **PASS** | `201`，键集合恰为 4 个；DB 1 活跃行 |
| A02 | **PASS** | 3 种非法输入均 `400` + field=name，无写入 |
| A03 | **PASS** | POST / PATCH 含 `/` 均 `400 INVALID_CHARACTER`，无写入，非 500 |
| A04 | **PASS** | monkeypatch 预检后 `409`，信封 message=`数据完整性冲突`（DB handler），独立确认数据库为权威 |
| A05 | **PASS** | `409 CONFLICT` field=name，活跃行数不变 |
| A06 | **PASS** | 大小写敏感唯一性 + by-name 精确命中 |
| A07 | **PASS** | by-name 命中 == by-id；不存在 `404`；非整数 id → `400` field=cluster_id（不 500）；纯数字名 `123` 走 by-name 无歧义 |
| A08 | **PASS** | 原始连接预置软删行 → 三读取路径全部排除；同名可重建 |
| A09 | **PASS** | Empty 200 空集；分页正确；4 种非法分页 `400` + 正确 field |
| A10 | **PASS** | 无状态列 / 字段（双断言） |
| A11 | **PASS** | 无位置 / 上级列 / 字段（双断言） |
| A12 | **PASS** | 中文往返 + by-name 命中 |
| A13 | **PASS** | 全部分支见 AC-12 行 |
| A14 | **PASS** | dev / test / prod / 无 env 全部 `/_foundation/*` 404；源码无 `_foundation`；目录不存在；`Settings` 无开关 |
| A15 | **PASS（含 2 项 LOW gap）** | 静态：0 处 `.deleted_at` 赋值；运行时：`DELETE` `405`，行仍活跃。注入实验见下 |
| A16 | **PASS** | 见 AC-14；Error 由 code 驱动（对抗探针：同 message 异 code → 异标题；同 code 异 message → 同标题） |
| G1 | **PASS（有 gap）** | `Field(max_length=10)` 注入被**捕获失败** → guard 有效；但 config 级 `str_max_length` 注入**逃逸**（见 Finding F001-T1） |
| G2 | **PASS** | 迁移注入 `CHECK (name <> '')` 后 guard **失败** → 有效；空库迁移后 CHECK 集合恰为 `{ck_clusters_name_no_slash}` |
| G3 | **PASS** | 注入 `str_strip_whitespace=True` 后 canary **失败** → 有效；不注入时 `" cn-a "` / `é` / `e\u0301` 逐字节原样往返。docstring **明确声明**「断言实现不做变换，**不**断言业务合法」——无边界误读 |
| T8′ | **PASS** | `test_error_envelope.py` 由产品端点驱动（`POST /api/clusters {}`、`GET /api/clusters?page=0`）→ `400` + `details[].field`，维持 F012 判据 4 |
| T9′ | **PASS** | `test_t9_prime_product_crud_roundtrip`（产品端点 create→list→get→update）+ A08（绕应用层软删 + API 读取排除）承接 F012 判据 5 |
| T13′ | **PASS** | 升级为「任何配置下 404」+ 静态断言，并入 A14 |

**F012 既有测试未被削弱**：`tests/database/*`（T1 ~ T7）全部通过且未被改写；`test_structure_guard.py::test_only_expected_tables_registered` 断言 `Base.metadata.tables == {"clusters"}` 仍成立；`test_health.py` / `test_lint.py` 通过。

---

## 对抗注入实验（Guard 是否真的会失败）

所有注入均先备份原文件（`/tmp/f001-backup`，`md5sum` 记录），实验后 `cp` 还原并以 `cmp` 逐一验证**逐字节相同**；全部 7 个源文件 + 迁移文件确认 `OK identical`，无残留。

| 实验 | 注入内容 | 期望 | 实际 | 还原验证 |
| --- | --- | --- | --- | --- |
| G1-a | `ClusterCreate.name: str = Field(max_length=10)` | G1 失败 | **1 failed**（`[ClusterCreate]`）→ guard 有效 | `cmp` 相同 |
| G1-b | `model_config = ConfigDict(str_max_length=10)` | G1 失败 | **2 passed**（**未捕获**）；同时 `ClusterCreate(name='A'*11)` 抛出 `ValidationError`（行为确实改变）→ **Finding F001-T1** | `cmp` 相同 |
| G3 | `model_config = ConfigDict(str_strip_whitespace=True)` | G3 失败 | **1 failed, 2 passed**（`[ cn-a ]`）→ guard 有效 | `cmp` 相同 |
| G2 | 迁移追加 `sa.CheckConstraint("name <> ''", name="name_not_empty")` | G2 失败 | **1 failed**（CHECK 集合断言）→ guard 有效 | `cmp` 相同 |
| A15-a | `repository` 中加入 `cluster.deleted_at = func.now()` | 静态 guard 失败 | **1 failed** → guard 有效 | `cmp` 相同 |
| A15-b | 改为 `session.execute(update(Cluster)....values(deleted_at=func.now()))` | 静态 guard 失败 | **1 passed**（**未捕获**，正则要求 `.deleted_at`）→ **Finding F001-T2** | `cmp` 相同 |

**还原方式**：全部通过 `cp <backup> <target>` 还原，并以 `cmp`（逐字节）+ `md5sum -c` 复核。还原后重跑全量测试：后端 `77 passed`、前端 `56 passed`，`backend/app` 中 `_foundation` 与 `.deleted_at` 赋值均为 0。**工作区未留下任何注入痕迹。**

---

## Database / Migration

- `clusters` 表由 `0001_f012_baseline` 建立，**F001 未新增表 / 列 / 约束 / migration**；`alembic check` 无模型漂移。
- 迁移可应用 / 可重复 / 可从空库重建（`downgrade base && upgrade head`）。
- **绕过应用层原始连接**（独立库 `csm_adv`）验证：
  - `'cluster-a' = 'Cluster-A'` → `false`，两值可共存（活跃 count=2）；
  - 第二活跃同名 → `23505`；含 `/` → `23514`；`NULL` → `23502`；
  - 软删后同名可重建（活跃 1 + 历史 1），再次软删后可重建（2 已删 + 1 活跃）；
  - 中文 / 纯数字名往返正确；
  - **空串 / `"  x  "` / 10 万字符均被数据库接受**——与 `undefined_constraints`「不实现」一致。
- 列集合恰为 `{id,name,created_at,updated_at,deleted_at}`；CHECK 集合恰为 `{ck_clusters_name_no_slash}`；无触发器 / 扩展 / 显式 collation。

## Backend / API

- 5 个产品端点行为与 `docs/api/f001-cluster.md` §2/§3 一致；**无 `DELETE /api/clusters/{id}`**（`405`）。
- 错误信封结构在 `400` / `404` / `409` / `500` 上一致（`{"error":{"code","message","details"}}`）；`details[].field` 正确：
  - 缺 `name` → `name`；`name` 非字符串 → `name`；含 `/` → `name`（`INVALID_CHARACTER`）；`page=0` → `page`；`page_size=201` → `page_size`；非整数 id → `cluster_id`；`409` → `name`（`DUPLICATE`）；`404` → `details==[]`。
  - `500`（DB 不可达）→ `INTERNAL_ERROR` `details==[]`（结构一致）。
  - **`405` → `error.code == "INTERNAL_ERROR"`**（见 F-01，继承自 F012，架构 Handoff 明示 F001 不修改通用映射表）。
- **只读无副作用**：连续 GET（list / by-id / by-name 命中与未命中 / 不存在 id）前后逐行比较 `id,name,updated_at,deleted_at` 与行数，完全一致。
- **`name` 未定义约束实证**：`POST ""` → `201`；`POST "  x  "` → `201` 且 `by-name` 读回原样（含首尾空白）；`POST 50000 字符` → `201`。实现**确实不拒绝**空串 / 空白 / 超长，且**不做任何变换**——符合产品边界，且未被契约承诺为「合法」。
- 未知字段被忽略（PROPOSED #3），`status`/`rack` 注入不影响响应。
- 契约 §4.5 的未定义路径：`GET /api/clusters/by-name`（缺名称段）→ `400` field=`cluster_id`（被当作 `{cluster_id}` 路径）；`/by-name/` → `307`；`/by-name/a%2Fb` → `404`。均在契约「不定义」范围内，前端不构造，**不构成缺陷**。

## Frontend

- `typecheck` / `56 tests` / `build` 全部通过。
- `ErrorState` 分支**只读** `error.code`：对抗探针证明「同 message 异 code → 不同标题」「同 code 异 message → 相同标题」。
- 列表页 `data-state`：Loading / Empty / Error 互斥且渲染不同（骨架 / `el-empty` + 「暂无集群」/ `role=alert`）。
- 详情页 `data-state`：`loading` / `not-found` / `error` / `content`；`404 NOT_FOUND` → `not-found` 态，文案「资源不存在，或已被删除」，与列表 Empty「暂无集群」**渲染不同状态与不同文案**。
- `vite.config.ts` 仅代理 `/api`；无 `/_foundation` 代理；`src/**` 无 foundation 引用（仅注释提及已移除）。

## Integration

**已验证（真实前后端）**：前端真实 API client（`api/clusters.ts` + `http.ts`）→ 真实 uvicorn（8767）→ 真实 PostgreSQL；`listClusters` / `getCluster` / `getClusterByName` / `createCluster` 的解析、大小写匹配、`404` 与 `409` 信封均与契约一致（临时 vitest 探针，运行后已删除）。

**NOT TESTED**：浏览器级 DOM / 视觉 E2E（无 Playwright 等浏览器自动化）；无 `vue-router`，故未验证通过 URL 直达详情 404 的整页导航（F001 架构 OPEN #3，属已知限制，A16 以组件级 404 桩件覆盖）。

---

## Defects

无 BLOCKER / HIGH。两项 MEDIUM 以下 guard 完整性缺口，**均不构成当前实现的产品行为违约**（当前代码无此类约束 / 路径）。

### F001-T1 — G1 未捕获 config 级 `str_max_length` / `str_min_length`（LOW）

- **Layer / Owner**：Backend（测试 guard 加固）
- **Location**：`tests/test_clusters_guards.py::_name_constraint_flags`（仅检查字段 `metadata` 与 `str_strip_whitespace`/`str_to_lower`/`str_to_upper`）
- **现象**：给 `ClusterCreate` 加 `model_config = ConfigDict(str_max_length=10)` 时，G1 **仍然通过**，但 Pydantic 行为确实改变（11 字符名被拒）。该 config 是 Pydantic v2 合法用法，可静默引入「长度约束」这一 `undefined_constraints`。
- **复现**：注入 `model_config = ConfigDict(str_max_length=10)` → `pytest tests/test_clusters_guards.py::test_g1_name_has_no_undefined_constraints` → `2 passed`；`ClusterCreate(name='A'*11)` → `ValidationError`。
- **期望**：G1 覆盖 config 级 `str_max_length` / `str_min_length`（Q8「未定义约束不实现必须可失败」）。
- **实际**：未覆盖。
- **影响**：当前实现无此 config，**无产品违约**；仅削弱 guard 对「较隐蔽注入方式」的保证。建议 G1 增加对 `model_config` 中 `str_max_length` / `str_min_length` 的断言。

### F001-T2 — A15 静态 guard 未捕获非 `.deleted_at =` 形式的软删写入（LOW）

- **Layer / Owner**：Backend（测试 guard 加固）
- **Location**：`tests/test_clusters_guards.py::test_a15_no_deleted_at_assignment_in_app_source`（匹配 `".deleted_at" in line and "=" in line`）
- **现象**：`session.execute(update(Cluster).values(deleted_at=func.now()))`（或 `setattr` / 字典键 `"deleted_at"`）不含字面 `.deleted_at`，静态 guard **通过**。
- **复现**：在 `ClusterRepository` 注入 `values(deleted_at=func.now())` 后，A15 静态用例 `1 passed`。
- **期望**：静态 guard 覆盖 `values(deleted_at=`、`setattr(...,"deleted_at"`、`"deleted_at":` 等常见软删写法。
- **实际**：未覆盖。
- **影响**：运行时 A15 用例（`DELETE` 不软删 + 行仍活跃）可补捉**经 DELETE 路由暴露**的软删路径；但未暴露为端点的软删写路径两者皆漏。当前实现该路径数为 0，**无产品违约**。建议加固正则 / AST 检查。

### F-01（继承自 F012，LOW，非 F001 引入）

- **Layer / Owner**：Backend / F012 follow-up
- **现象**：`405 Method Not Allowed` 的 `error.code` 为 `INTERNAL_ERROR`（`_HTTP_STATUS_CODE_MAP.get(405, "INTERNAL_ERROR")`）。
- **复现**：`DELETE /api/clusters/1` → `405` `{"code":"INTERNAL_ERROR","message":"Method Not Allowed"}`。
- **期望**：4xx 不宜标为 `INTERNAL_ERROR`。
- **实际**：`INTERNAL_ERROR`。
- **影响**：`docs/architecture/f001-cluster-handoff.md`「Open Technical Questions #5」已明示 F001 **不修改**通用映射表，A15 只断状态码，故**不阻塞** F001；继续作为 Backend follow-up。

---

## Unverified Areas

1. **浏览器级前端 E2E / 视觉验证**：无浏览器自动化环境；组件行为经 vitest（happy-dom）+ 真实 HTTP client 验证，未在真实浏览器观察 DOM / 网络 / 视觉。
2. **URL 直达详情 404 的整页导航**：F001 不引入 `vue-router`（架构 OPEN #3），无 URL 路由可直达；A16 以组件级 404 桩件覆盖，属已知限制。
3. **生产部署 locale 固定**：本机 `zh_CN.UTF-8` 下大小写敏感语义成立，但 locale 固定要求属 F015 部署文档。
4. **F013 认证后的访问控制**：F001 显式无认证，`/api/clusters*` 均可匿名访问；F013 落地后由 `/api/*` 中间件覆盖，本次未验证。
5. **`500` 经真实 SQL 异常路径**：本次以 DB 不可达触发 `500` 信封；未构造「应用层未识别 SQLSTATE」的产品可达路径（F001 无此类路径）。
6. **并发名称竞争**：A04 以 monkeypatch 证明数据库权威性，但未做真实多连接并发压测（架构明示 PATCH 单行更新无锁、数据库 partial unique 兜底）。

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-14 **全部 PASS**；A01 ~ A16、G1 ~ G3、T8′ / T9′ / T13′ **全部 PASS**。
- 数据库层（绕应用层原始连接）：大小写敏感、活跃唯一性 `23505`、CHECK `23514`、NOT NULL `23502`、软删释放唯一性、中文 / 数字名往返、Schema 与 Database Handoff 逐项一致、空串 / 空白 / 超长被接受（未定义约束不实现）。
- 迁移：可应用 / 可重复 / 可重建 / 无漂移。
- API：5 端点契约、分页边界、Empty 200、404 不区分不存在与已软删、错误信封与 `details[].field`、只读无副作用、`DELETE` 不软删。
- 单一路径：`/_foundation/*` 在 dev/test/prod/无 env 全部 404；源码无 `_foundation`；`backend/app/**` 中 `deleted_at` 赋值数 = 0。
- Guard 有效性：G1（Field）/ G2（CHECK）/ G3（strip）/ A15（直接赋值）注入后**均真实失败**；G3 docstring 无边界误读；契约 §7 无承诺性措辞。
- 前端：typecheck / 56 测试 / build 通过；三态与 Empty vs Not Found 可区分；Error 由 `error.code` 驱动。
- 真实前后端集成：前端真实 client ↔ 真实后端 ↔ 真实 PG 成功。
- 工程门禁：ruff check / format 通过；F012 既有 `tests/database/*` 与结构 guard 未被削弱。

### Not Verified

见「Unverified Areas」（浏览器 E2E、URL 直达 404、F015 locale、F013 认证、真实并发竞争、除 DB 不可达外的 500 路径）。

### Blocking Issues

None。

### Defect Owner

F001-T1 → Backend（guard 加固，LOW）；F001-T2 → Backend（guard 加固，LOW）；F-01 → Backend / F012 follow-up（继承，LOW）。

处置建议：F001-T1 / F001-T2 为**非阻塞**的测试 guard 加固项，可在本 Feature 或后续 follow-up 处理；不改变当前任何产品行为。

---

## Test Status

`READY FOR REVIEW`

---

GIT: NONE

READY FOR REVIEW