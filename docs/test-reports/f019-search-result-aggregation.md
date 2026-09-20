# Test Report — F019 搜索结果聚合视图

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验证；实现方与协调器结论**未被采信**，所有数字均本次独立复现）
> Date: 2026-09-20
> Feature: F019 — Search Result Aggregation（E05，P1）｜`layers = {database:false, backend:true, frontend:true}`
> 依赖 F018（已 DONE）与 F010 `get_related_resources`

---

## Feature

F019 把 F018「仅自身字段命中关键字的资源」扁平列表，改为以「**命中项 + 其关联链**」为组织单元的**单一扁平混合列表**：命中行标「命中」、关联行标「关联」并携带 `derivation_path`；做关系扩展；跨单元不去重；按标识字段优先排序；取代 F018 扁列表。关联推导**复用** `app.resource_views.service.get_related_resources`（R-QUERY-003 唯一实现）。无 schema 变更（`database: false`）。

## Test Basis

- `AGENTS.md`（§6 数据库安全、§7 未验证不得声称正确、§9 Git 纪律）
- `docs/product/handoffs/f019-search-result-aggregation.md`（**AC-01~AC-08 + AC-A1~A8**）
- `docs/product/requirements.md` §16 **R-QUERY-006（新增）/ R-QUERY-005（修订）**、R-QUERY-003（含间接）、R-QUERY-004、§17 R-DELETE-002、§19、§22
- `docs/architecture/f019-search-result-aggregation-handoff.md`（Test Work T-19-01~12、G-019-1~5、T-FE-19-1~3；「必须独立证伪」六条）
- `docs/api/f019-search-result-aggregation.md`（**契约，唯一权威，`READY`**）；`docs/api/f018-cluster-keyword-search.md`（§2 匹配语义仍权威；响应形态已被 f019 取代）
- ADR-0003 / 0004 / 0005

## Environment

| 项 | 值 |
|---|---|
| OS / Python | Linux，Python **3.12.7**（仓库 `.venv`） |
| PostgreSQL | **16**（本次新建**一次性** docker 容器 `f019-pg`，独立端口 **55432**，**已删除**；未触碰 `csm-prod-*` / `csm-dev-postgres`） |
| Node / npm | **v24.14.0 / 11.9.0**（Vitest 5.0.1，Vite 7） |
| 测试库（各自独立） | `csm_f019_main`（全量 1021）、`csm_f019_probe`（自写探针）、`csm_f019_int`（**真实前后端集成**） |
| 大小写敏感实测 | 测试库 locale `en_US.utf8`（大小写敏感）；F019 搜索「不区分大小写」与 §22 大小写敏感**并存**（见 AC-05） |
| 前端集成 | 真实 `uvicorn 127.0.0.1:8791`（本次新建，**已 stop**）+ 真实 PG `csm_f019_int` |

**全新性**：PG 容器、3 个测试库、账号、uvicorn 均为本次新建；pytest 每次 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 从空库重建。设置 `CSM_TEST_DATABASE_URL` 指向独立容器；**未**将其设为 `CSM_DATABASE_URL`（app 库 DSN 仅用于 uvicorn 指向独立集成库）。实现方「1021 / 645×2」结论**未被复用**——下表全部数字均来自本次独立执行。

> **测试者操作披露（非交付物改动，但如实记录）**：① 首次运行后，协调器/实现方脚本曾对**本机 dev 实例**执行过一次向前 `alembic upgrade head`（F018 报告已披露的历史操作），本次**未重复**任何对非测试库的写操作。② 在**首轮**全量套件运行期间，Tester 为证伪临时改动了 5 个生产文件并随即逐字节还原；**该首轮结果因存在与变异窗口重叠而被 Tester 主动作废并丢弃**，最终 1021 结果来自**全部变异还原后**重启的干净全量运行（见「证伪实验」）。交付代码最终状态经 SHA-256 与原文件比对确认无差异。

---

## 独立执行摘要（真实命令与数字）

```text
# 工程门禁
$ .venv/bin/ruff check backend tests            → All checks passed!
$ .venv/bin/ruff format --check backend tests   → 173 files already formatted

# 后端全量（真实 PG，独立库 csm_f019_main；全部变异还原后重启的干净运行）
$ CSM_TEST_DATABASE_URL=…csm_f019_main PGPASSWORD=csmtest .venv/bin/python -m pytest -q
  → 1021 passed, 2 warnings in 1058.10s        # 无 skipped

# F019 专项（独立库 csm_f019_probe）
$ … pytest -q tests/test_search_api.py          → 35 passed in 50.34s
$ … pytest -q tests/test_search_guards.py       → 19 passed in  1.89s

# Tester 自写独立探针（独立库 csm_f019_probe；不复用实现方断言）
$ PYTHONPATH=backend:. .venv/bin/python /tmp/f019-probe/independent_check.py
  → TOTAL 100 checks, 0 failures

# 前端
$ npm run typecheck                             → exit 0
$ npm run test                                  → 43 files / 645 passed（连续多次一致）
$ npm run build                                 → ✓ built in 6.04s

# 真实前后端集成（真实 uvicorn :8791 + 真实 PG csm_f019_int；临时 spec，跑后删除）
$ npx vitest run tests/__f019_integration_tmp.spec.ts → 3 passed in 3.20s

# Tester 自写前端独立探针（临时 spec，跑后删除）
$ npx vitest run tests/__f019_probe_tmp.spec.ts       → 2 passed in 3.49s
```

> **关于协调器基线 1021 / 645**：本次独立复现结果与之**一致**（1021 passed、645 passed × 多轮）。未直接采信其数字，均为本次实跑所得。

---

## Acceptance Criteria Mapping

| AC | Test / Evidence | Result |
|---|---|---|
| **AC-01** 只读 | 自写探针 **P8**（搜索前后 3 类行 `SELECT *` 快照逐字节不变）；`test_t19_08_search_is_read_only` 独立重跑 | **PASS** |
| **AC-02** 软删过滤 | 自写探针 **P7**（raw psycopg 绕过应用层：软删 NIC → 关联行消失、BM 保留；软删命中 BM → total=0）；`test_t19_07_*`；**证伪实验②** | **PASS** |
| **AC-03** 认证 | 自写探针 **P9**（无 Cookie → `401 UNAUTHENTICATED`，响应体无 `items`）；`test_t19_09_unauthenticated_returns_401` | **PASS** |
| **AC-04** Not Found / Empty 区分 | 自写探针 **P9/P9b**（不存在 Cluster → 404；raw 软删 Cluster → 404；活跃无命中 → 200 + `items==[]` + `total==0`；空关键字先于 404）；`test_t19_09_*` | **PASS** |
| **AC-05** 不改既有语义 | 全量 1021 含 `test_clusters_*` / `test_resource_views_*` / `test_deletion_*` 全绿；guard `test_g018_5_*`（大小写折叠仅限 `backend/app/search/**`）；`grep` 确认 `app/search/**` 无 `deleted_at`、`app/**`（search 外）无 `lower()/casefold()/ilike` | **PASS** |
| **AC-06** 契约一致 | f019 契约 `status=READY` 且为响应权威；f018 §3/排序段/§7 加「已由 f019 取代」横幅；`requirements.md` §16 含 R-QUERY-006 与修订后 R-QUERY-005；guard G-019-2/3/5（路由与 schema 封闭、既有 guard 只增不减）；**证伪实验⑤** | **PASS** |
| **AC-07** 前端三态 | `searchResultsPage.spec` + 自写前端探针 + **真实集成**（真实 Empty → `data-state=empty` 且「无匹配结果」；真实 404 → `data-error-code=NOT_FOUND`）；错误按 `error.code` 分支 | **PASS** |
| **AC-08** 范围边界 | guard G-018-7（源码无 `export/csv/order_by/sort_by/status_filter/relevance/tsvector/trigram/cross_cluster/include_deleted/...`）；请求面恰 `{cluster_id,keyword,page,page_size}`、无 `requestBody`、既有端点无 `keyword` | **PASS** |
| **AC-A1** 扁平 + 单列表 | 自写探针 **P1/P2**（顶层恰 `{items,total,page,page_size}`；每行恰一资源、封闭字段集）；`test_t19_03_single_flat_list_and_unit_order` | **PASS** |
| **AC-A2** 命中/关联标注 + 推导路径 | 自写探针 **P1/P2**（`role` ∈ {HIT,RELATED}；HIT `derivation_path=null`、`matched_fields` 非空；RELATED 路径首=命中项、末=本行）；前端探针 + 真实集成（徽标「命中/关联」、缩进、路径文案） | **PASS** |
| **AC-A3** 关系扩展 | 自写探针 **P1**（输入 IP 片段 → HIT IP + RELATED NIC/BM，后两者 `matched_fields==[]` 仍出现）；`test_t19_01`；**证伪实验①** | **PASS** |
| **AC-A4** 仅搜索涉及资源 | 自写探针 **P6**（无关 BM 不出现）；`test_t19_06_*`（Cluster 名不产生结果行） | **PASS** |
| **AC-A5** 不去重 | 自写探针 **P4**（同一 BM 在两个命中单元各出现一次，`group_key` 不同）；`test_t19_04` | **PASS** |
| **AC-A6** 标识字段优先排序 | 自写探针 **P3**（描述性命中先建、id 更小，仍排在标识命中之后）；`test_t19_03_identity_field_hits_rank_before_descriptive_hits`；**证伪实验③** | **PASS** |
| **AC-A7** 取代 F018 扁列表 | 契约裁定「同一端点、取代响应、不并存」；OpenAPI 响应仅聚合形态、无 `mode`/第二端点（G-018-2 / G-018-7） | **PASS** |
| **AC-A8** 单元组织顺序 | 自写探针 **P5**（单元级分页：`page_size=1` 时单元整体不被拆散、跨页不重不漏、`total`=单元数）；`test_t19_10`；前端探针（命中行恒首行、关联行紧随缩进） | **PASS** |

**每条 AC 均有结果，无遗漏、无 BLOCKED、无 FAIL。**

---

## Tester 自写探针清单

探针源码：`/tmp/f019-probe/independent_check.py`（**未入仓**，交付面零改动）。共 **100 checks / 0 failures**。

| 探针 | 覆盖 | 关键断言 |
|---|---|---|
| **P1** 用户示例 | T-19-01 / AC-A3 | `total==1`；行序 `IP(HIT), BM(RELATED), NIC(RELATED)`；BM/NIC `matched_fields==[]`；路径 `IP→NIC→BM` 与 `IP→NIC` |
| **P2** 路径与封闭字段 | T-19-02 / AC-A2 | 每行封闭字段集、`group_key` 恰 `{resource_type,id}`；RELATED 路径长 ≥2、首=命中项、末=本行；HIT `path=None` |
| **P3** 标识优先排序 | AC-A6 | 描述性命中（低 id）仍排在标识命中之后 |
| **P4** 跨单元不去重 | AC-A5 | 同一 BM 在两单元各一行、`group_key` 不同、单元序正确 |
| **P5** 单元级分页 | 契约 §3 | 全集 10 行（2 单元×5）；`page_size=1` 单元不拆散；跨页无重复；越界页空且 `total` 保持 |
| **P6** 仅涉及资源 | AC-A4 | 结果集恰 `{命中项 ∪ 关联链}`，无关 BM 不出现 |
| **P7** 真实 PG 逐类软删 | AC-02 | raw 置 `deleted_at`：关联 NIC 消失而 BM 保留；命中 BM 软删后 `total=0` |
| **P8** 只读 | AC-01 | 搜索前后 3 类行 `SELECT *` 快照逐字节相等 |
| **P9 / P9b** 状态优先级 | AC-03/04 | 401（无数据）> 400（空/仅空白，先于 404）> 404（不存在 / 软删 Cluster）> 200 Empty |
| **P10** canonical 逐字段 | T-19-11 | 六类 `item["resource"] == GET canonical *Read`（深等）、无 `deleted_at` |
| **P11** 匹配语义 | 契约 §2 | 大小写不敏感同结果集；子串命中；`status` 不参与匹配 |
| **P12** Cluster 名不产生行 | AC-A4 | Cluster 名 token → `items==[]` |

**前端探针**（`frontend/tests/__f019_probe_tmp.spec.ts`，跑后删除）独立构造响应，验证：单请求（一次挂载恰一个 `/search` 请求）、命中/关联徽标与缩进可区分、推导路径文案、三态互不相同。**2 passed**。

**真实集成探针**（`frontend/tests/__f019_integration_tmp.spec.ts`，跑后删除）：真实 `uvicorn` + 真实 PG，相对 URL 经 `node:http` 直连后端并透传会话 Cookie、**无任何响应桩**。**3 passed**：真实 IP 搜索渲染 HIT+RELATED 行与真实推导路径文案；真实无命中 → Empty（非错误）；真实不存在 Cluster → `NOT_FOUND` 错误态。

---

## 证伪实验（均实际执行并逐字节还原）

> 所有变异均先用 SHA-256 记录变异前哈希，还原后用 `diff -q` 确认 **byte-identical**。**首轮全量套件在变异窗口内运行已作废**；最终 1021 来自全部还原后的干净重启。

### 实验①：复用而非重写（令 `get_related_resources` 派生为空）

| 项 | 值 |
|---|---|
| 目标 | `backend/app/resource_views/service.py::get_related_resources`（派生唯一入口） |
| 变异前 SHA | `2664b72d…d1f2` |
| 变异内容 | 在唯一 404 网关后 `.replace` 注入 `return RelatedResourcesRead(五类 RelatedSet(items=[], total=0))`（锚点断言命中） |
| 变异后 SHA | `f5b7475c…025e` |
| 观察到 | 搜索 BM `hostname` → `total=1`，仅剩 `('BARE_METAL', 1, 'HIT')`——**关联 NIC 行消失、命中行仍在**（与架构 Handoff 预期一致）。另：搜索 IP 时 IP 命中行本身也消失（IP 本就在 `R(B)` 内）→ **更强地证明候选集与关联链均来自该唯一入口**，搜索模块未自写推导 |
| 还原后 SHA | **`2664b72d…d1f2`（byte-identical）**；`test_search_guards + test_resource_views_guards` → **32 passed** |

### 实验②：软删过滤为真（放开活跃过滤）

| 项 | 值 |
|---|---|
| 目标 | `backend/app/db/active.py::active_filter`（数据访问层活跃过滤基座） |
| 变异前 SHA | `869f1aa8…a02` |
| 变异内容 | `model.deleted_at.is_(None)` → `model.deleted_at.is_not(None) \| model.deleted_at.is_(None)`（恒真） |
| 变异后 SHA | `04d5729a…1fd5` |
| 观察到 | 自写探针 **100 checks → 4 failures**：软删 NIC 出现在 `items`（关联行泄漏）、软删 BM 命中行仍返回（`total=2`）、软删 Cluster 返回 **200** 而非 404 → 证明软删过滤真实生效（命中行与关联行均过滤，含 Cluster 网关） |
| 还原后 SHA | **`869f1aa8…a02`（byte-identical）** |

### 实验③：排序（移除标识字段优先）

| 项 | 值 |
|---|---|
| 目标 | `backend/app/search/service.py::_hit_category` |
| 变异前 SHA | `eb5b0204…a846` |
| 变异内容 | `return 0 if …identity… else 1` → `return 1 if …identity… else 0`（反转类别） |
| 观察到 | 自写探针 P3 → **`expected [4, 3], got [3, 4]`**（1 failure）；实现方 `test_t19_03_identity_field_hits_rank_before_descriptive_hits` → **1 failed**。说明 AC-A6 用例可失败、非恒真 |
| 还原后 SHA | **`eb5b0204…a846`（byte-identical）** |

### 实验④：前端单请求（注入浏览器端第二次请求）

| 项 | 值 |
|---|---|
| 目标 | `frontend/src/pages/SearchResultsPage.vue::onMounted` |
| 变异前 SHA | `56825221…fdc3` |
| 变异内容 | 在 `void run()` 后追加 `void fetch('/api/bare-metals/1')`（模拟浏览器端拼接） |
| 观察到 | 自写前端探针 → **1 failed**：`expected [ …(2) ] to have a length of 1 but got 2`——单请求断言可失败 |
| 还原后 SHA | **`56825221…fdc3`（byte-identical）** |

### 实验⑤：既有 guard 只增不减 + allow-list 可失败

| 项 | 值 |
|---|---|
| 结构核验 | `tests/test_auth_guards.py::EXPECTED_GET_ROUTES` 含 `/api/clusters/{cluster_id}/search`，F009/F010/F018 既有成员**全部保留**；`tests/test_resource_views_guards.py::F009_CLUSTER_PATHS` 含 F009 四条 + search，**无删除、无 `.skip`、无恒真** |
| 目标 | `backend/app/search/router.py`（追加未批准路由） |
| 变异前 SHA | `8b74d207…5019` |
| 变异内容 | 追加 `@router.get("/{cluster_id}/search/unapproved")` |
| 观察到 | `test_g018_2_search_router_registers_exactly_one_get`、`test_g018_8_openapi_cluster_paths_match_evolution_set` → **2 failed**（allow-list 检出未批准路由） |
| 还原后 SHA | **`8b74d207…5019`（byte-identical）** |

---

## Database / Migration

- **无 schema 变更、无 migration**（`layers.database = false`）。`backend/migrations/versions/` 仍 **8** 个 revision（`0001`–`0008`）；`MIGRATION_HEAD = 0008_f008_services` 未变。
- 真实 PG 上 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 在 3 个独立库上均成功达到 `0008_f008_services`。
- 软删过滤在**真实 PostgreSQL**、`raw psycopg` **绕过应用层**置 `deleted_at` 下验证（探针 P7 + 证伪实验②）——非 ORM Mock。

## Backend / API

- 全量 `pytest` **1021 passed / 0 skipped**；F019 专项 `test_search_api` **35**、`test_search_guards` **19**。
- 端点面封闭：唯一搜索路径 `GET /api/clusters/{cluster_id}/search`，参数恰 `{cluster_id, keyword, page, page_size}`，无 `requestBody`，既有端点无 `keyword`（G-018-2/7）。
- 状态优先级实测：`401 > 400（空/空白，先于 404）> 404 > 200（含 Empty）`（探针 P9）。
- `resource` 与 canonical `*Read` **逐字段深等**、无 `deleted_at`（探针 P10）。
- `app/search/**` 无 `deleted_at`；`app/**`（search 外）无 `lower()/casefold()/ilike`（源码核验）。

## Frontend

- `typecheck` exit 0；`npm run test` **43 files / 645 passed**（多轮一致，含全部变异还原后的复跑）；`build` ✓。
- 命中行 / 关联行徽标与缩进可区分；`derivation_path` 文案由前端生成（首=命中项、末=本行）；三态互不相同，Empty 非错误、不触发全局 401，错误按 `error.code` 渲染。
- **恰一个请求**：自写前端探针证明一次挂载只发一个 `/search` 请求；证伪实验④证明该断言可失败。

## Integration

**真实前后端集成已执行（非 Mock/Fixture）**：真实 `uvicorn 127.0.0.1:8791` + 真实 PostgreSQL `csm_f019_int` + 真实 `SearchResultsPage.vue`，相对 URL 经 `node:http` 直连后端并透传会话 Cookie，**无任何响应桩**。结果 **3 passed**：
1. 真实 IP 片段搜索渲染 HIT（`10.10.10.1/16`）+ 关联行（`int-cn001` / `int-eth0`），推导路径文案 `IP 地址 10.10.10.1/16 → 网络接口 int-eth0 → 裸金属 int-cn001`；
2. 真实无命中 → Empty（`data-state=empty`、「无匹配结果」，非错误）；
3. 真实不存在 Cluster → `data-error-code="NOT_FOUND"`。

临时集成 spec 与 uvicorn 运行后**已删除 / 已停止**。

---

## Defects

**None.** 未发现 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND DEFECT（BLOCKER / HIGH / MEDIUM / LOW 均无）。

## Unverified Areas

1. **生产实例人工核验未执行**（`http://192.168.10.221/`）：架构 Handoff Verification Strategy 要求的人工核验（输入 IP 片段得到命中行 + 缩进关联行与推导路径、标识字段优先、Empty 非错误、404 文案、未登录 `/api/...` → 401、既有导航入口不受影响）**本机无法替代**，**NOT TESTED**。本地等价项已由真实集成 + 前端 spec 覆盖，但**不等价于生产实例确认**。
2. **性能 / 规模**：架构 Handoff 的失效阈值（单 Cluster ~10³ BM）与 QPS/p95 未在真实 10⁵ 规模下压测——不属本 Feature 验收项（无性能 SLA），**NOT TESTED**。
3. **生产库 locale 下的 §22 语义**：本机测试库 locale 为 `en_US.utf8`（大小写敏感），搜索「不区分大小写」与 §22 并存已在本机验证；生产库 locale 未核验。

## Test Status

**READY FOR REVIEW**

判定依据：全部 AC-01~AC-08 / AC-A1~AC-A8 均有结果且**无 BLOCKED / FAIL**；无 BLOCKER / HIGH / 须修复的 MEDIUM Defect；`database: false`（无必需 DB 分支）；Backend + Frontend 两分支 COMPLETE；**真实前后端集成已验证**；六条「必须独立证伪」（复用而非重写 / 软删 / 排序 / 前端单请求 / guard 只增不减）均已实际执行并逐字节还原。

---

## Test Handoff

### Status

`READY FOR REVIEW`（独立测试通过；实现方与协调器结论未被采信，所有数字均本次独立复现）。

### Verified

- 后端全量 **1021 passed**（真实一次性 PG、独立库、无 skipped）；F019 专项 35 + 19。
- 自写探针 **100 checks / 0 failures**：用户示例、路径头尾、标识优先排序、跨单元不去重、单元级分页、仅涉及资源、真实 PG 软删、只读、四态优先级、canonical 深等、匹配语义、Cluster 名不产生行。
- **5 处自写变异**（`get_related_resources` 置空 / `active_filter` 放开软删 / `_hit_category` 反转 / 页面注入第二次请求 / 路由注入未批准端点），均可被检出并 **SHA-256 逐字节还原**。
- 前端 `typecheck` / `build` 通过；`test` **645 passed**；单请求与三态断言可失败（实验④）。
- **真实前后端集成 3 passed**（真实 uvicorn + 真实 PG，无响应桩）。
- 无 migration（head 仍 `0008_f008_services`）。
- 既有 guard **只增不减**（`EXPECTED_GET_ROUTES` 保留全部既有成员并追加 search；F009 四条保留；allow-list 可失败）。
- 工程门禁：`ruff check` = All checks passed；`ruff format --check` = 173 files already formatted。
- 测试环境清理：一次性容器 `f019-pg` 已删除；uvicorn 已停止；`csm-prod-*` / `csm-dev-postgres` **未触碰**；临时测试文件已删除。

### Not Verified

- 生产实例 `http://192.168.10.221/` 人工核验（**本机无法替代**，NOT TESTED）。
- 规模 / 性能失效阈值压测（无验收 SLA，NOT TESTED）。
- 生产库 locale 下的 §22 语义（本机已由既有套件验证 `cluster-a != Cluster-A`）。

### Blocking Issues

**None.**

### Defect Owner

**None.**

---

## Git 声明

本次**未执行任何 Git 命令**（包括只读命令）：本任务明确禁止执行 git 命令，Tester 全程遵守。文件状态由 SHA-256 / `diff` 核验，非 git。

```text
GIT: NONE
```
