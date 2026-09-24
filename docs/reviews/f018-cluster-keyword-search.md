# Review Report — F018 集群内资源关键字搜索

> Status: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer（独立审查；Developer / Tester 总结未被采信）
> Date: 2026-09-18
> Feature: F018（E05，P1）｜Branch `feature/F018-cluster-keyword-search`
> Layers：`{database: false, backend: true, frontend: true}`
> Contract：`docs/api/f018-cluster-keyword-search.md`（READY）

---

## Feature

F018 — 集群内资源关键字搜索（Cluster-scoped Keyword Search）。在**单个已选定 Cluster** 内，以**单关键字 + 子串包含 + 不区分大小写**定位该 Cluster 的活跃 BareMetal 及 R-QUERY-003 五类关联资源（含间接），返回**单一混合列表**、每条携带 `matched_fields`，只读、无写副作用、无 schema 变更。

## Review Status

```text
APPROVED WITH FOLLOW-UP
```

不存在 BLOCKER / HIGH / 必须在当前 Feature 修复的 MEDIUM；核心验收标准满足；测试可信；未超范围。存在少量 LOW / NOTE，可按 Follow-up 处理。

## Scope Reviewed

**Git 证据（全部只读命令）**

| 项 | 值 |
|---|---|
| Feature Branch | `feature/F018-cluster-keyword-search` |
| `start_commit` | `e59cfd9bc1e15a9b4f16b683a731f180807b3abe`（== `develop`，未漂移） |
| 候选 HEAD（审查对象） | `c79f506188451b3e72608dbdb5d268b1f0d2c029`（`test(F018): record acceptance test report`） |
| Base Branch / SHA | `develop` / `e59cfd9bc1e15a9b4f16b683a731f180807b3abe` |
| merge-base | `e59cfd9bc1e15a9b4f16b683a731f180807b3abe`（== start_commit，线性，无漂移） |
| 范围 | `e59cfd9...HEAD`（完整分支差异） |
| 工作树 | **clean**（`git status --short` 空；无 staged；无 untracked） |

**注意（元数据一致性）**：Test Report 记录的候选 HEAD 为 `6aa7c215...`，而当前协调器给定的候选 HEAD 为 `c79f5061...`（比前者**多一个提交** `test(F018): record acceptance test report`，即测试报告自身落盘提交）。二者为同一 Feature 分支、同一 start_commit，`c79f5061` 是 `6aa7c215` 的后继；本 Report 的批准**仅对 `c79f5061` 的代码状态有效**。该差异为「测试报告落盘」的后继提交，不含代码变更（见逐文件核查）。`6aa7c21..c79f506` 的差异仅 `docs/test-reports/f018-cluster-keyword-search.md` 与 `docs/project/v1/project-plan.yaml`。

**完整差异逐文件结论（`e59cfd9...HEAD`，29 文件）**

| 文件 | 结论 |
|---|---|
| `backend/app/search/__init__.py` | 新增，仅模块 docstring（依赖方向声明）。OK |
| `backend/app/search/fields.py` | 仅 `SEARCHABLE_FIELDS`，字段与契约 §2 **逐项一致**（含顺序）。OK |
| `backend/app/search/schemas.py` | `SearchResourceType` 六值；`SearchResultItem` 四字段；`resource` 联合恰六个 canonical `*Read`。OK |
| `backend/app/search/service.py` | 委托 `get_related_resources`；无 `deleted_at`；无自建 SQL/软删谓词；去重 + `(rank,id)` 物化；分页切片。OK |
| `backend/app/search/router.py` | 恰一条 `GET /clusters/{cluster_id}/search`；空/空白 keyword 先于查库 400；参数封闭。OK |
| `backend/app/main.py` | 仅新增 `include_router(search_router, prefix="/api")` + 注释。OK |
| `tests/test_search_api.py` | 新增，T-18-01~14 + 边界（非整数 cluster_id、page_size 越界）。OK（见 Test Review 的 LOW-1） |
| `tests/test_search_guards.py` | 新增，G-018-1~8（AST/文本/OpenAPI guard，含防恒真用例）。OK |
| `tests/test_auth_guards.py` | `EXPECTED_GET_ROUTES` **追加** search 路径（无删除）。OK |
| `tests/test_resource_views_guards.py` | `F009_CLUSTER_PATHS` **追加** search 路径（保留 F009 四条）；一处注释替换。OK |
| `docs/api/f018-cluster-keyword-search.md` | 新增，契约 READY。OK |
| `docs/api/f002-bare-metal.md` / `f005-ip-address.md` / `f009-cluster-resource-view.md` / `f010-resource-detail.md` | 四处「关键字禁止」立场修订并指向 F018 契约；**无既有语义改动**。OK |
| `docs/architecture/f018-cluster-keyword-search-handoff.md` | 架构 Handoff。OK |
| `docs/product/handoffs/f018-cluster-keyword-search.md` | 产品 Handoff。OK |
| `docs/product/requirements.md` | 新增 R-QUERY-005，未改既有规则（61→62）。OK |
| `docs/project/v1/backlog.md` / `milestones.md` / `dependency-map.md` | 三份**派生视图**由 `project-plan.yaml` 重建（含重建说明）。见 NOTE-1 |
| `docs/project/v1/project-plan.yaml` | F018 元数据 + 派生计数。OK |
| `docs/test-reports/f018-cluster-keyword-search.md` | Test Report（READY FOR REVIEW）。OK |
| `frontend/src/api/search.ts` | 单端点客户端；类型逐字段复用 canonical Read；keyword 原样。OK |
| `frontend/src/pages/SearchResultsPage.vue` | 单请求、三态、命中字段标签、详情导航。OK |
| `frontend/src/App.vue` | 外壳搜索区置于 `<nav>` 之后；搜索视图 + `SearchReturn`；导航未击穿。OK |
| `frontend/tests/searchApi.spec.ts` / `searchResultsPage.spec.ts` / `searchShell.spec.ts` | 新增；**未改既有前端测试**。OK |

- `backend/migrations/**`：**逐字节未改**（`git diff e59cfd9...HEAD -- backend/migrations/` 为空）。
- **无** `package.json` / `package-lock` / `pyproject.toml` / 依赖 / `.env` / Dockerfile 改动。
- **无** 临时文件入库；无密钥 / 环境信息。

**未审查内容**：见文末「Unreviewed Areas」。

---

## 10 项重点核查（逐项判定与依据）

### 1) REQUIRED 10 条 — 逐条核对

| # | REQUIRED | 判定 | 依据 |
|---|---|---|---|
| 1 | 单一只读端点 `GET /api/clusters/{cluster_id}/search`，返回混合列表 | **PASS** | OpenAPI：搜索路径恰 1 条、methods=`{get}`、无 `requestBody`；`test_g018_2` |
| 2 | 范围推导经 `get_related_resources`；`search` 无 `deleted_at` / 第二份推导 / 软删 / FK 谓词 | **PASS** | 源码直读：唯一派生入口；`grep deleted_at backend/app/search/` = 0；AST guard `test_g018_4`；**我的独立 monkeypatch 探针**（见 §4） |
| 3 | 唯一 404 网关 = `clusters.service.get_cluster_by_id`，先于派生；子资源缺失不 404 | **PASS** | `service.search_cluster_resources` 首行调用；`test_t18_05/06`；探针 P5 |
| 4 | 参数封闭：`cluster_id`+`keyword`(必填)+`page`+`page_size`；无排序/状态/多关键字/载体/include_deleted | **PASS** | 独立 OpenAPI dump：params 恰四项；`test_g018_7` |
| 5 | 状态优先级 401 > 400(空/空白，先于 404) > 404 > 200 | **PASS** | 我的探针：未认证 + 空白/缺参 → **401**；空白 + 不存在 Cluster → **400**；不存在/软删 Cluster → 404；活跃无命中 → 200 |
| 6 | `resource` 逐字段复用 canonical `*Read`；`resource_type` 六值；`matched_fields` 非空 | **PASS** | 独立 OpenAPI：`anyOf` 恰六 Read、枚举恰六值；探针逐类深等 canonical GET |
| 7 | 大小写折叠仅 `backend/app/search/**`；§22/`by-name`/用户名查找零改动 | **PASS** | 全 `backend/app/**.py` 扫描：`.lower()/casefold/ilike` 仅 `search/service.py:57,63`；`resource_views/service.py` sha256 未变 |
| 8 | 既有 guard 只增不减 | **PASS** | `EXPECTED_GET_ROUTES`/`F009_CLUSTER_PATHS` 均追加，diff 的删除行仅 1 条注释；无 `.skip`/`xfail` |
| 9 | 既有契约修订，无「禁止却有」分裂 | **PASS** | 四处修订均指向 F018 契约；F018 为独立新端点，未在任何既有端点新增 `keyword`（独立 OpenAPI 核查 = `[]`） |
| 10 | `/api` 前缀自动覆盖；`APPROVED_API_PREFIXES` 无需新增 | **PASS** | 首段 `clusters` 已是白名单；`test_g018_2` 通过 |

### 2) 契约与实现逐项一致

端点 / 参数 / 响应 schema / `matched_fields` 顺序 / `resource_type` 六值 / 分页信封 / 错误表 / `400` 优先于 `404`：**全部一致**。

- `matched_fields` 顺序 = 契约 §2 声明顺序（独立探针：`["hostname","vendor","cpu"]`；`fields.py` 元组顺序即输出顺序）。
- `resource_type` 判别与 `resource` 类型一一对应；`resource_type` 由 `SearchResourceType` 驱动。
- 分页信封复用 `app.common.pagination.Page`；`total` 为全量命中数（探针：跨页并集 == 全集、无重无漏）。

### 3) 字段封闭性（我自写探针，未只读实现者测试）

结果：**PASS**。独立探针逐项验证：

- `matched_fields` 元素**从不**属于 `{id, cluster_id, bare_metal_id, network_interface_id, carrier_type, carrier_id, status, created_at, updated_at, deleted_at, carriers}`。
- 仅 `status=DOWN` → 0 命中；`cluster_id` / `bare_metal_id` 数值文本 → 0 命中；`carrier_type` 字面（如 `BARE_METAL`）→ 0 命中；`created_at`/`updated_at` 预置唯一 token → 0 命中。
- 对照 `hostname` 命中仍有效。

实现机理（源码 + 探针共同证实）：匹配只迭代 `SEARCHABLE_FIELDS[type]`，故 FK / status / 时间戳 / carriers **物理上不进入比较**。

### 4) 范围正确（跨 Cluster / Cluster 自身 / 含间接）

- **跨 Cluster 不越界**：`_candidates` 只枚举 `BareMetalRepository.list_active(cluster_id=...)`，关联经 `get_related_resources(B)`；探针：其它 Cluster 命中不出现在本 Cluster，反向成立。**PASS**
- **Cluster 自身不产生结果行**：`_candidates` 不产出 Cluster；探针：以 Cluster 名称 token 搜索 → `total==0`。**PASS**
- **R-QUERY-003「含间接」由 F010 保证**：源码直读 `service.py` 委托 `app.resource_views.service.get_related_resources`；**独立 monkeypatch 探针**：运行时把 `app.search.service.get_related_resources` 替换为抛异常 → 搜索请求在 `search/service.py::_candidates` 处失败（服务端 500），栈回溯指向被委托入口，证明 search **确经该唯一入口派生范围**（复用而非重写）。还原后 42 checks / 0 failures。**PASS**

### 5) `search` 模块的 `deleted_at` 与软删过滤（独立 raw 连接验证）

- `search/**` 出现 `deleted_at` 次数 = **0**（我的 `grep` 与 AST guard 双重确认）。
- 独立 raw `psycopg`（绕过应用层）逐类置 `deleted_at`：IP 软删后该条从 `items` 消失、`total` 6→5、BareMetal 仍可见；软删 Cluster 后 → 404。**排除来自被调用的既有 repository / F010 传递，而非 search 自过滤**。**PASS**

### 6) 无 schema 变更

- `git diff e59cfd9...HEAD -- backend/migrations/` = **空**。
- `versions/` 仍 **8** 个 revision；`alembic heads` = **`0008_f008_services (head)`**（在审查用全新 PG 上重建亦达同一 head）。
- 无 extension / 表 / 列 / 索引 / 约束 / 触发器。**PASS**

### 7) 前端

- **单请求**：`SearchResultsPage` 仅调 `searchClusterResources`；单测断言 `fetch` 调用数 == 1 且 URL 以 `/api/clusters/3/search` 开头。**PASS**
- **未选 Cluster / 空关键字不可发起**：`searchDisabled` 计算属性 + `handleSearch` 早退；`searchShell.spec` 断言按钮 `disabled` 且点击 0 请求。**PASS**
- **三态互不相同且 Empty 非错误**：`ListStates` 优先级 loading>error>empty>content；`data-state=empty` 不渲染 `[role=alert]`、不触发全局 401 handler。**PASS**
- **错误按 `error.code`**：`ErrorState` 按 code 分支（`NOT_FOUND`→「未找到资源」、`VALIDATION_ERROR`→「请求校验失败」、`NETWORK_ERROR`→「无法连接服务器」）；不解析 message 分支。**PASS**
- **既有 7 个 `app*Navigation.spec.ts` 未击穿**：`npx vitest run tests/app*Navigation.spec.ts` → **7 files / 26 passed**；搜索控件位于 `<nav>` 之后且文案（「资源搜索」「搜索范围」「关键字」「搜索」）不含导航项文案。**PASS**

### 8) 既有 guard 只增不减

- `EXPECTED_GET_ROUTES`：仅 `+` 一条，无 `-`。
- `F009_CLUSTER_PATHS`：追加 search；diff 删除行仅 1 条注释（被替换的说明文字），保留 F009 四条；`test_g018_8` 用独立 `F009_FOUR_PATHS` 固定原四条并断言 `== F009_FOUR_PATHS | {SEARCH_PATH}`（更严）。
- 无删除既有断言、无 `.skip` / `xfail`、无恒真：`test_g018_5_search_module_actually_folds_case` 为**防恒真**用例，且经 Tester 变异与本 Review 的独立扫描共同佐证可失败。**PASS**

### 9) Test Report 操作披露的独立评估

Tester 披露：首次执行 `alembic upgrade head` 未设 `CSM_DATABASE_URL`，误对默认 dev DSN `postgresql+psycopg://csm:csm@localhost:5432/csm` 跑了一次向前 upgrade。我的独立评估：

- 该 DSN 为**本机 dev 实例**，**非**生产实例 `http://192.168.10.221/`（后者为容器内独立 PostgreSQL）。我以**只读**连接核实：dev 库 `alembic_version.version_num = '0008_f008_services'`、`public` 表 11 张——与「已在 head、该 upgrade 为 no-op」一致。
- 即便此前未在 head，`upgrade head` 亦为**非破坏性**（无 `DROP` / 无 `DELETE`，仅补建/前进 schema）；`0001`–`0008` 未改动。
- 结论：**影响面为「无数据的 schema no-op」**，未触及生产实例、未触及任何测试库。**无需**在生产实例上额外校验。该披露真实、无隐瞒。
- 附带观察（非 F018 引入）：alembic 在 `CSM_DATABASE_URL` 缺省时会回落到默认 dev DSN——属既有迁移配置行为，不属本 Feature 缺陷。

### 10) 是否过度声称

| 声明 | 独立判定 |
|---|---|
| 后端全量 1019 | **成立**：我独立在**全新真实 PG**（pgserver，独立库）上跑出 `1019 passed, 2 warnings in 1231.73s`，0 skipped |
| 前端 642 / 既有 618 一条不少 | **成立**：`43 files / 642 passed`；前端 diff **仅新增** 3 个 spec，未改既有测试；7 导航 spec 26 passed |
| 无 migration | **成立**：见 §6 |
| 既有 guard 只增不减 | **成立**：见 §8 |
| 「真实前后端集成 4 passed」 | **未能独立复现**：临时 spec 已删除、未入库；无法重跑。**如实标注为 Reviewer 未复核**（见 Unreviewed Areas） |
| 「85 条自写探针 0 failures」 | **未能独立复核计数**：探针脚本未入库（位于 `/tmp/f018-test/`）。Reviewer **自写 42 条独立探针**（0 failures）另行佐证同类性质 |
| 两处变异逐字节还原 | **部分佐证**：`backend/app/resource_views/service.py` 现 sha256 = `2664b72d2cd6a3194daacbcca3948b33bdc5e3d7d899942b599d653f587dd1f2`，与 Test Report 记录的「还原后 SHA」**一致**，证明该文件现处于未变异状态 |

无发现「未验证却声称已验证」的伪造；未验证项在 Test Report 的 `Unverified Areas` 中**如实标注**。

---

## 工程门禁（本 Review 真实执行）

环境：Linux，仓库 `.venv`（Python 3.12.7）；PostgreSQL 16.2（`pgserver` **本 Review 新建**，socket `/tmp/rev-f018/pgdata`；独立库 `csm_f018_review` / `csm_f018_probe_rev`）；Node v24 / Vitest 5.0.1。

```text
$ .venv/bin/ruff check backend tests          → All checks passed!          (exit 0)
$ .venv/bin/ruff format --check backend tests → 173 files already formatted (exit 0)

# 后端全量（真实 PostgreSQL，独立库 csm_f018_review）
$ CSM_TEST_DATABASE_URL=…csm_f018_review .venv/bin/python -m pytest -q
  1019 passed, 2 warnings in 1231.73s        # 0 skipped；与基线一致

# Reviewer 自写独立探针（独立库 csm_f018_probe_rev；raw 连接 + 运行时 monkeypatch）
$ .venv/bin/python /tmp/rev-f018/probe.py
  TOTAL 42 checks, 0 failures

# 前端
$ npm run typecheck   → exit 0
$ npm run test        → 43 files / 642 passed
$ npx vitest run tests/app*Navigation.spec.ts → 7 files / 26 passed
$ npm run build       → ✓ built in 8.64s
```

**基线核对**：后端 1019 == 基线；前端 642 == 基线（既有 618 一条不少）。

**变异**：本 Review **未**对交付文件做任何变异（`search` 的复用性以运行时 monkeypatch 证伪，不落盘）。全部交付文件字节未变，`git status` clean。

**关键文件 sha256（本 Review 结束时）**

```text
d373e2605e9586fa7fb87bce930ac788687b47237543e94780f0d0ecf4196d6b  backend/app/search/service.py
2664b72d2cd6a3194daacbcca3948b33bdc5e3d7d899942b599d653f587dd1f2  backend/app/resource_views/service.py
468d16a3d19166d4ee93cf994b0e2d51d7b04e04e311daf13eb1a9a19ac45d2c  tests/test_search_guards.py
06398d048c3c054194015fcdab5a5c18de9611677211d05831928b5f2356681c  backend/app/main.py
```

---

## Product Compliance

满足 R-QUERY-005（含空/仅空白关键字规则与两条边界）与 AC-01~AC-08、AC-D1~AC-D5。范围未扩张：无跨 Cluster、无多关键字 / 分词 / 相似度、无排序 / 导出 / 状态筛选、无写端点。R-QUERY-005 在 `requirements.md` §16 已落盘，未改任何既有规则（61→62）。Cluster 不产生结果行、Cluster 名称不参与命中，与 AC-D1 及 NQ-A 裁定一致。**PASS**

## Architecture Compliance

符合 Architecture Handoff 的 REQUIRED 1~10 与裁定 1~4：契约形态 (a)、复用 F010 唯一推导、唯一 404 网关、参数封闭、状态优先级、`resource` 逐字段复用、大小写隔离、guard 只增不减、契约修订、无需新增前缀白名单。`layers.database = false` 得到保持（无 migration / extension / 索引）。**PASS**

## Database Review

无 schema 变更。`0001`–`0008` 逐字节未改；`alembic heads` 仍 `0008_f008_services`；无新 revision、无 extension。软删过滤在**真实 PostgreSQL**、raw 连接绕过应用层下逐类验证成立，且来自既有 repository / F010 传递。**PASS**

## Backend Review

API 层（router）仅做参数封闭与空关键字校验；Service 层承担匹配与分页；复用 `BareMetalRepository.list_active` 与 `resource_views.get_related_resources`。无写副作用、无重复软删谓词、无第二份 R-QUERY-003 推导。错误语义与状态优先级正确。`N+1`（逐 BM 调 F010）为架构 R1 已量化并接受的风险，不属缺陷。**PASS**

## Frontend Review

严格使用唯一搜索端点；Loading / Empty / Error 三态互不相同；Empty 不渲染为错误、不触发全局 401；错误按 `error.code` 分支；未选 Cluster / 空白关键字不可发起；无浏览器端拼接；未改既有 618 用例；外壳导航未击穿。**PASS**

## Test Review

后端 T-18-01~14 覆盖 AC 主要路径，含真实 PG、raw 绕过程序层软删、只读 `updated_at` 快照、分页不重不漏、canonical 深等；G-018-1~8 以 OpenAPI / AST / 文本 guard 固定结构性质，含防恒真用例。前端三份 spec 覆盖单请求、三态、错误分支、导航。测试自身**未**为迎合实现而弱化（guard 比原 F009 断言更严）。既有 guard 只增不减。**PASS**（例外见 LOW-1）。

## Findings

### LOW-1

**Severity:** LOW

**Layer:** Tests / Backend

**Location:** `tests/test_search_api.py::test_t18_04_foreign_key_values_do_not_match`

**Problem:** 该用例的断言实际是**空转**：它搜索 `"clusterref-{cluster_id}"` 这一在任何字段中都不存在的字符串，无论实现是否排除外键值都会返回 `total == 0`，无法证伪「外键值参与匹配」。

**Evidence:** 用例正文仅 `keyword = f"clusterref-{cluster}"; assert _search(...).json()["total"] == 0`；而真正验证外键封闭的是 Reviewer 自写探针（搜索 `cluster_id` / `bare_metal_id` 的**数值文本** → 0 命中）与 `matched_fields` 封闭断言。

**Impact:** 该条测试提供虚假覆盖信号；若未来实现误把 FK 纳入匹配，此用例不会变红。不构成本 Feature 的正确性缺陷（实现正确，另有 Tester 探针与 Reviewer 探针覆盖）。

**Expected:** 以「数值 FK 值的文本」为关键字（如 `str(cluster_id)`）验证 0 命中，或直接依赖 `matched_fields ⊆ 契约字段` 的封闭断言。

**Suggested Owner:** Tester（可选 Follow-up）

### NOTE-1

**Severity:** NOTE

**Layer:** Project Docs

**Location:** `docs/project/v1/backlog.md` / `milestones.md` / `dependency-map.md`

**Problem:** 本分支同时携带三份**派生视图重建**（数百行）与 `project-plan.yaml` 更新，超出「F018 实现」的直觉范围。

**Evidence:** `git diff --stat` 显示三文件大范围改写，正文自述「由 `project-plan.yaml` 重新生成（经用户决定）」。

**Impact:** 无功能/正确性影响；属计划维护。已记录授权来源（用户决定按计划重建），派生视图以 `project-plan.yaml` 为唯一真源。

**Expected:** 无需改动；仅提示后续 Review 注意此类「随分支携带的管理性提交」。

**Suggested Owner:** Coordinator / Product

### NOTE-2

**Severity:** NOTE

**Layer:** Backend / Guard

**Location:** `tests/test_search_guards.py::test_g018_5_case_folding_calls_only_in_search_module`

**Problem:** Handoff 的 G-018-5 措辞为「**全仓** `.lower()` 仅出现在 `backend/app/search/**`」，而实现把「全仓」落为 `backend/app/**` 的 AST 扫描。

**Evidence:** 我独立核查：仓库内**除 `backend/app/**` 与 `tests/**` / `backend/migrations/**` 外不存在其他 `.py`**；全 `backend/app/**.py` 中 `.lower()/casefold/ilike` **仅**出现于 `search/service.py`。因此该 guard 对**全部生产源码**的覆盖是**完整**的。

**Impact:** 非范围放松；AC-05 得到充分支撑。措辞与实现范围存在字面差异，但实现范围恰为生产源码全集。

**Expected:** 无需改动；如需精确，可将 guard 注释由「全仓」改为「生产源码 `backend/app/**`」。

**Suggested Owner:** Tester（可选）

### NOTE-3

**Severity:** NOTE

**Layer:** Backend

**Location:** `backend/app/search/service.py::_snapshot`

**Problem:** `_snapshot` 与 `backend/app/resource_views/service.py::_snapshot` 为近乎同构的分页枚举辅助，存在轻度重复。

**Evidence:** 两处实现逐行可对照；均以 `MAX_PAGE_SIZE` 循环取全。

**Impact:** 无正确性影响；不违反复用约束（该函数是分页工具，非 R-QUERY-003 推导）。共享可能引入跨模块耦合，反而违背「search 不放进 resource_views」的隔离取向。

**Expected:** 保持现状即可；如后续第三处出现再考虑抽取共用工具。

**Suggested Owner:** Backend（可选）

### NOTE-4

**Severity:** NOTE

**Layer:** Backend / Concurrency

**Location:** `backend/app/search/service.py::_candidates` → `get_related_resources`

**Problem:** `_candidates` 先按 `list_active` 枚举活跃 BM，再对每台 BM 调 `get_related_resources`（其内部以 `get_bare_metal_by_id` 复核主体）。若某 BM 在两调用之间被并发软删，复核会抛 `NotFoundError` → 404，瞬时违反「子资源缺失绝不诱发 404」。

**Evidence:** 源码路径直读；该 N+1 与「复核主体」为 F010 既有模式，非 F018 新引入。

**Impact:** 仅并发软删窗口内成立、概率极低；不属当前 Feature 验收缺陷（架构 R1 已接受 N+1 形态）。

**Expected:** 记录为已知并发边界；路径 A（集合式推导）演进时一并消除。

**Suggested Owner:** Architect（Follow-up）

### NOTE-5

**Severity:** NOTE

**Layer:** Frontend

**Location:** `frontend/src/App.vue::loadSearchClusterOptions`

**Problem:** Cluster 选项以 `page_size: 200` 单次取全，若活跃 Cluster > 200 则选择器被截断（无法选择更多 Cluster，从而无法对其发起搜索）。

**Evidence:** `listClusters({ page: 1, page_size: 200 })`；目录内其他登记对话框亦用同一取法。

**Impact:** 非本 Feature 验收项；Cluster 规模远超设计预期（10⁵ 为**资源**总量，非 Cluster 数）前无实际影响。

**Expected:** 如 Cluster 数增长，改为分页/可搜索下拉。

**Suggested Owner:** Frontend（Follow-up）

## Existing Defects

Tester 报告 **None**。Reviewer 独立复评：

- 未发现 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND 层缺陷达到 BLOCKER / HIGH / 必须修复的 MEDIUM。
- Tester 未报告缺陷，故无「严重程度是否合理」需重评项；本 Review 新增的 5 项均为 LOW / NOTE，非 Tester 已报告项，不构成对 Tester 结论的推翻。

## Non-blocking Follow-ups

- LOW-1：修正 `test_t18_04_foreign_key_values_do_not_match`（并入 Tester 后续回归面）。
- NOTE-2/3：可选措辞 / 去重整理。
- NOTE-4：并发软删窗口在架构演进（路径 A）时消除。
- NOTE-5：Cluster 数增长时改进选择器。

## Unreviewed Areas

1. **Test Report 声称的「真实前后端集成 4 passed」**：临时 spec 已删除且未入库，Reviewer **无法独立复现**；其结论**未由本 Review 复核**。本地等价项（前端 spec + 后端 API 测试 + Reviewer 探针）已覆盖同类性质。
2. **Tester「85 条自写探针」的计数与逐条内容**：脚本位于 `/tmp/f018-test/`（未入库），未逐条复核；Reviewer 以**自写 42 条独立探针**另行覆盖字段封闭 / 软删 / 复用 / 状态优先级 / 范围 / canonical 深等。
3. **生产实例 `http://192.168.10.221/` 的人工核验**：本机无法替代，**NOT TESTED**（Test Report 已如实标注）。
4. **规模 / 性能**：失效阈值（单 Cluster ~10³ BM）与 QPS / p95 未在真实 10⁵ 规模下压测；无验收 SLA。
5. **生产库 locale 下的 §22 语义**：仅在本机（大小写敏感 locale）验证。
6. `backend/app/search/fields.py` 字段清单与 `domain-model.yaml` 的**逐字段域来源比对**仅在契约 §2 层面核对，未逐字段回溯领域模型定义。

---

## 只读 Git 命令清单（本 Review 实际执行）

```text
GIT: git status --short
GIT: git rev-parse HEAD
GIT: git rev-parse develop
GIT: git merge-base develop HEAD
GIT: git rev-parse --abbrev-ref HEAD
GIT: git log --oneline --decorate -15
GIT: git log --oneline e59cfd9..HEAD
GIT: git diff --stat e59cfd9...HEAD
GIT: git diff --cached --stat
GIT: git ls-files --others --exclude-standard
GIT: git diff e59cfd9...HEAD -- backend/migrations/
GIT: git diff e59cfd9...HEAD -- tests/test_auth_guards.py tests/test_resource_views_guards.py backend/app/main.py
GIT: git diff e59cfd9...HEAD -- docs/api/f002-bare-metal.md docs/api/f005-ip-address.md docs/api/f009-cluster-resource-view.md docs/api/f010-resource-detail.md
GIT: git diff e59cfd9...HEAD -- docs/product/requirements.md
GIT: git diff e59cfd9...HEAD -- docs/project/v1/backlog.md docs/project/v1/milestones.md docs/project/v1/dependency-map.md
GIT: git diff e59cfd9...HEAD -- frontend/src/App.vue
GIT: git diff e59cfd9...HEAD -- tests/
GIT: git diff e59cfd9...HEAD --name-only
GIT: git diff e59cfd9...HEAD --name-only -- frontend/
GIT: git diff e59cfd9...HEAD --name-only --  # 过滤非预期目录
```

**未执行**任何 `git add` / `commit` / `checkout` / `switch` / `merge` / `reset` / `stash` 或其他改变 Git 状态的命令。审查结束时 `git status --short` 为空。

---

## Verdict

```text
APPROVED WITH FOLLOW-UP
```

依据：不存在 BLOCKER / HIGH / 必须当前修复的 MEDIUM；AC-01~AC-08 与 AC-D1~AC-D5 全部满足；后端 1019 / 前端 642 门禁在**独立真实 PostgreSQL 与全新环境**下复现一致；三条关键性质（复用 F010、大小写隔离、契约一致）均经**源码 + guard + Reviewer 自写探针**独立证实；未超范围、无 schema 变更、无新依赖、无既有语义改动。存在的 LOW / NOTE 不阻塞合入。

> 批准仅对候选 HEAD `c79f506188451b3e72608dbdb5d268b1f0d2c029`、Base `e59cfd9bc1e15a9b4f16b683a731f180807b3abe` 的当前差异有效。此后任何代码 / 契约 / Base 变化须重新测试与 Review。

---

GIT: git status --short
GIT: git rev-parse HEAD
GIT: git rev-parse develop
GIT: git merge-base develop HEAD
GIT: git rev-parse --abbrev-ref HEAD
GIT: git log --oneline --decorate -15
GIT: git log --oneline e59cfd9..HEAD
GIT: git diff --stat e59cfd9...HEAD
GIT: git diff --cached --stat
GIT: git ls-files --others --exclude-standard
GIT: git diff e59cfd9...HEAD -- backend/migrations/
GIT: git diff e59cfd9...HEAD -- tests/test_auth_guards.py tests/test_resource_views_guards.py backend/app/main.py
GIT: git diff e59cfd9...HEAD -- docs/api/f002-bare-metal.md docs/api/f005-ip-address.md docs/api/f009-cluster-resource-view.md docs/api/f010-resource-detail.md
GIT: git diff e59cfd9...HEAD -- docs/product/requirements.md
GIT: git diff e59cfd9...HEAD -- docs/project/v1/backlog.md docs/project/v1/milestones.md docs/project/v1/dependency-map.md
GIT: git diff e59cfd9...HEAD -- frontend/src/App.vue
GIT: git diff e59cfd9...HEAD -- tests/
GIT: git diff e59cfd9...HEAD --name-only
GIT: git diff e59cfd9...HEAD --name-only -- frontend/

---

## 协调器 Merge Gate（2026-09-18）

| # | 条件 | 结果 |
|---|---|---|
| 1 | 必需测试通过、真实集成已验证 | 后端 **1019 passed**（协调器与 Reviewer 各自在**全新 PostgreSQL** 上独立重跑）；前端 **642 passed**（协调器 ×2、Tester ×3）；ruff 干净；typecheck / build 通过。**真实集成**：Tester 以真实 uvicorn + 真实 PostgreSQL、**无响应桩**完成（4 passed，临时 spec 已删）；Reviewer 声明**无法复现**该条（临时文件已删）——已如实记录，未重复声称。 |
| 2 | 无 BLOCKER / HIGH / 必须修复的 MEDIUM | 成立（LOW-1 + NOTE-1~5，均非阻塞） |
| 3 | 所有 Subagent 已结束、工作区 clean | 成立 |
| 4 | HEAD 与批准候选一致、develop 与审查 base 一致 | 成立（`c79f506` / `e59cfd9`） |

**Merge**：`git switch develop` → `git merge --no-ff --no-commit feature/F018-cluster-keyword-search` → `git commit -F`。
结果：**merge_commit = `f1ac71b1515156d97789ac8da1d859d552c031e1`**；父提交 = `e59cfd9`（Base）+ `c79f506`（批准 HEAD）；**集成树与已审阅候选树逐字节一致**。

### 协调器独立复核（不采信 Agent 声明）

| 复核项 | 结果 |
|---|---|
| 后端全量（协调器，全新真实 PostgreSQL） | **1019 passed**，20:54 |
| 前端（协调器） | typecheck 干净；**642 passed 连续 2 次**；build ✓ |
| F018 专项（协调器另起新库复跑） | **52 passed** |
| `backend/app/search/service.py` | `deleted_at` 出现 **0** 次；`get_related_resources` **4** 次（确为委托 F010） |
| 越界改动 | 未触碰 `backend/migrations/**`、`deletion/service.py`、`resource_views/**`、`package.json`、`docs/api/**` |
| Tester 变异是否还原 | `resource_views/service.py` = `2664b72d2cd6a319…`、`bare_metals/repository.py` = `50dd43487d697761…`，**与基线逐字节一致** |

### 关于 Tester 的操作披露

Tester 主动报告：执行 alembic 时首次未设 `CSM_DATABASE_URL`，误对**默认 dev DSN**（`localhost:5432/csm`）跑了一次 `alembic upgrade head`。Reviewer 独立核实为**非破坏性 no-op**（该 dev 库已在 head `0008`）；且与生产实例的**容器内独立 PostgreSQL**无关。**结论：影响面为零，无需对生产实例做补偿校验。** 记录在案——按 §9.1 的要求，如实申报比事后被发现更有价值。

### 部署后人工核验

F018 已重建并滚动替换生产前端。人工核验见部署记录：侧边栏内出现搜索区（Cluster 选择器 + 关键字 + 搜索按钮），未选 Cluster 或关键字为空时不可发起；选定后得到单一混合列表且每条显示命中字段。**AC-D5 与 R-QUERY-005 的前置条件由此在真实实例上闭合。**
