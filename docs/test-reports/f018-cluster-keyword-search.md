# Test Report — F018 集群内资源关键字搜索

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验证；实现方与协调器结论**未被采信**）
> Date: 2026-09-18
> Feature: F018（E05，P1）｜Branch `feature/F018-cluster-keyword-search`
> start_commit `e59cfd9`（= develop）｜候选 HEAD `6aa7c2156679d12097f9a96a5b30dce2441d6263`（feat `79f5590` + 计划检查点 `6aa7c21`）｜工作树 clean

---

## Feature

F018 — Cluster 内资源关键字搜索（Cluster-scoped Keyword Search）。在**单个已选定 Cluster** 范围内，以**单关键字 + 子串包含 + 不区分大小写**定位该 Cluster 的活跃 BareMetal 及 R-QUERY-003 五类关联资源（含间接），返回**单一混合列表**，每条携带 `matched_fields`。`layers = {database:false, backend:true, frontend:true}`，无 Database Design 分支。

## Test Basis

- `AGENTS.md`（§6 数据库安全、§7 未验证不得声称正确、§9 Git 纪律）
- `docs/product/handoffs/f018-cluster-keyword-search.md`（**AC-01~AC-08 + AC-D1~AC-D5**）
- `docs/product/requirements.md` §16 **R-QUERY-005**（空/仅空白关键字规则、两条边界）、R-QUERY-003（含间接）、R-QUERY-004、§17 R-DELETE-002、§19、§22
- `docs/architecture/f018-cluster-keyword-search-handoff.md`（Test Work T-18-01~14 / G-018-1~8；**必须独立证伪的声明 1~7**；Verification Strategy）
- `docs/api/f018-cluster-keyword-search.md`（**契约，唯一权威，`READY`**）
- ADR-0003 / 0004 / 0005（`ACCEPTED`）；`docs/project/git-workflow.md`

## Environment

| 项 | 值 |
|---|---|
| OS / Python | Linux，Python **3.12.7**（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 真实实例，Unix socket `/tmp/f018-test/pgdata`，**本次新建**） |
| Node / npm | **v24.14.0 / 11.9.0**（Vitest 5.0.1，Vite） |
| 测试库（每类独立） | `csm_f018_main`（全量 1019）、`csm_f018_probe`（F018 专项 + 自写探针）、`csm_f018_int`（**真实前后端集成**） |
| 大小写敏感实测 | `SELECT ('cluster-a'='Cluster-A')` → **False**（`zh_CN.UTF-8` locale，§22 语义成立） |
| 前端集成 | 真实 `uvicorn 127.0.0.1:8799`（本次新建，PID 757957/757958，已按 **PID 精确 kill**） |

**全新性**：PG 实例、3 个测试库、账号、uvicorn 均为本次新建；pytest 每次 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 从空库重建。实现方「1019 / 642×2」结论**未被复用**——下表全部结果均来自本次独立执行。

> **测试者操作披露（非交付物改动，但如实记录）**：执行 `alembic upgrade head` 时首次未显式设置 `CSM_DATABASE_URL`，**误对默认 DSN `postgresql+psycopg://csm:csm@localhost:5432/csm`（本机 dev 实例）执行了一次向前的 `upgrade head`**（该实例现为 `0008_f008_services`）。该操作**非破坏性**（无 `DROP`、无数据删除、仅补建/前进 schema），未触及任何测试库；此后所有 alembic 调用均显式指向 `/tmp/f018-test/pgdata` 的独立测试库。**不构成对交付代码或产品的任何改动。**

---

## 独立执行摘要（真实命令与数字）

```text
# 工程门禁
$ .venv/bin/ruff check backend tests            → All checks passed!
$ .venv/bin/ruff format --check backend tests   → 173 files already formatted

# 后端全量（真实 PG，独立库 csm_f018_main）
$ CSM_TEST_DATABASE_URL=…csm_f018_main .venv/bin/python -m pytest -q
  1019 passed, 2 warnings in 1250.47s           # 无 skipped；与协调器基线一致

# F018 专项（独立库 csm_f018_probe）
$ … pytest -q tests/test_search_api.py          → 34 passed in 57.13s
$ … pytest -q tests/test_search_guards.py       → 18 passed in  1.92s

# Tester 自写独立探针（独立库 csm_f018_probe；非复用实现方断言）
$ PYTHONPATH=backend:. … .venv/bin/python /tmp/f018-test/independent_check.py
  → TOTAL 85 checks, 0 failures

# 前端
$ npm run typecheck                             → exit 0
$ npm run test                                  → 43 files / 642 passed（连续 3 次均 43/642）
$ npx vitest run tests/app*Navigation.spec.ts   → 7 files / 26 passed
$ npm run build                                 → ✓ built in 8.98s

# 真实前后端集成（真实 uvicorn :8799 + 真实 PG csm_f018_int；临时 spec，跑后删除）
$ npx vitest run tests/__f018_integration_tmp.spec.ts → 4 passed in 8.56s
```

**既有前端用例计数核验**：全量 642 − F018 新增 spec 24（`searchApi` 8 + `searchResultsPage` 11 + `searchShell` 5，已实跑 3 files / 24 passed）= **既有 618 条一条不少**。

---

## Acceptance Criteria Mapping

| AC | Test / Evidence | Result |
|---|---|---|
| **AC-01** 只读 | 自写探针 **P7**（搜索前后 6 类行 `updated_at` 快照逐一不变、行数非零）；实现方 `test_t18_10_search_is_read_only` 已**独立重跑**（含于 34 passed） | **PASS** |
| **AC-02** 软删过滤 | 自写探针 **P6**（raw `psycopg` 绕过应用层逐类置 `deleted_at`：该类消失、BareMetal 不受影响；BM 软删后整范围消失）；`test_t18_09_*` 独立重跑 | **PASS** |
| **AC-03** 认证 | 自写探针 **P5**（无 Cookie 客户端 → `401 UNAUTHENTICATED`，响应体无 `items`）；`test_t18_08` 独立重跑 | **PASS** |
| **AC-04** Not Found / Empty 区分 | 自写探针 **P5**（不存在 Cluster → 404；raw 软删 Cluster → 404；活跃无命中 → 200 + `items==[]` + `total==0`）；`test_t18_05/06` 独立重跑 | **PASS** |
| **AC-05** 不改既有语义 | 独立重跑 `test_a06_case_sensitive_uniqueness_and_lookup`、`test_a07_by_name_matches_get_by_id`、`test_t14_username_case_sensitive_login`、`test_clusters_guards.py`、`test_deletion_api.py` → **35 passed**；**变异 #2** 证明大小写折叠越界会触发 G-018-5，还原后全绿 | **PASS** |
| **AC-06** 契约一致 | `git diff e59cfd9 6aa7c21 -- docs/api/f002,f005,f009,f010` 实证四处立场已按 `DEC-021` 修订并**指向 F018 契约**；F018 契约 `status = READY`；无「契约禁止、实现却有」分裂 | **PASS** |
| **AC-07** 前端三态 | `searchResultsPage.spec` 11 用例 + 自写前端探针 + **真实集成**（Empty `data-state=empty` 非错误；404 `data-error-code=NOT_FOUND`；VALIDATION_ERROR / NETWORK_ERROR 按 `error.code`）；恒跑 | **PASS** |
| **AC-08** 范围边界 | G-018-7 守卫（源码无 `export/csv/order_by/sort_by/status_filter/relevance/tsvector/trigram/…`；请求面恰 `{cluster_id,keyword,page,page_size}`；无 `requestBody`；既有端点无 `keyword`）；`test_search_guards` 18 passed | **PASS** |
| **AC-D1** 范围（含间接） | 自写探针 **P1/P8**（六类混合；其它 Cluster 即使命中不出现；Cluster 名称不产生结果行）；**变异 #1** 证明关联类由 `get_related_resources` 派生；`test_t18_11/12` 独立重跑 | **PASS** |
| **AC-D2** 字段封闭 | 自写探针 **P1**（所有结果 `matched_fields` ⊆ 契约字段、且**不含**任何 FK/`status`/时间戳）+ **P4**（`status=DOWN`、`created_at`、`updated_at` 单独搜索均 0 命中）；`test_t18_04_*` 独立重跑 | **PASS** |
| **AC-D3** 子串包含 + 不区分大小写 | `test_t18_02`（`zshared`==`ZSHARED` 同结果集）、`test_t18_03`（连续子串命中、非连续不命中）**独立重跑**（含于 34 passed） | **PASS** |
| **AC-D4** 混合列表 + 命中字段 + Empty | 自写探针 **P1/P2/P3**（单一混合列表 6 类；`matched_fields` 非空、契约顺序 `['hostname','vendor','cpu']`；`resource` 与 canonical `*Read` **深等**、无 `deleted_at`）+ 真实集成；`test_t18_01/14` 独立重跑 | **PASS** |
| **AC-D5** 应用外壳入口 / 未选不可发起 | `searchShell.spec`（未选 Cluster / 空白关键字按钮禁用、点击 0 请求；懒加载仅一次）+ 自写前端探针（每次恰 1 个 `/search` 请求） | **PASS** |

**每条 AC 均有结果，无遗漏、无 BLOCKED。**

---

## Tester 自写探针清单

探针源码：`/tmp/f018-test/independent_check.py`（**未入仓**，交付面零改动）。

| 探针 | 覆盖 | 关键断言 |
|---|---|---|
| **P1** 单一混合列表 + 命中字段封闭 | AC-D1/D2/D4 | `total==6`、六类齐全；每条 `matched_fields` ⊆ 契约 §2 字段且 **∩ `{FK, status, created_at, updated_at, deleted_at, id} == ∅`**；`id == resource.id` |
| **P2** `matched_fields` 顺序/多字段 | AC-D4 / 契约 §2 | `['hostname','vendor','cpu']`（契约声明顺序、多字段全部列出） |
| **P3** canonical 深等 | AC-D4 / 契约 §3 | 六类逐类 `item["resource"] == GET canonical`（深等）、无 `deleted_at` |
| **P4** 字段封闭负例 | AC-D2 / 契约 §2 | `status=DOWN`、`created_at`、`updated_at` 单独搜索均 `total==0`；对照 hostname 命中 |
| **P5** Empty/404/400/401 四态 + 优先级 | AC-03/04/R-QUERY-005 | 不存在/软删 Cluster→404；无命中→200 Empty；**空/空白 keyword 对不存在 Cluster 仍 400（先于 404）**；缺 keyword→400；`page_size∈{0,201}`→400；未认证→401 无数据 |
| **P6** 真实 PG 逐类软删（raw 绕过应用层） | AC-02 | 每类独立场景：软删前该类可见、BM 可见；软删后该类消失、**BM 仍可见**；BM 软删后整范围消失 |
| **P7** 只读 | AC-01 | 搜索前后 6 类 `updated_at` 快照不变 |
| **P8** 范围不越界 + Cluster 名称不产生行 | AC-D1 | 其它 Cluster 命中不出现在本 Cluster 结果；Cluster 名 token → `total==0` |
| **P9** 分页不重不漏 | 契约 §3 | `total/page/page_size` 回显；跨页并集 == 全集且无重复；越界页空 |
| **前端探针**（临时 `__f018_probe_tmp.spec.ts`，跑后删除） | AC-D4/D5 | 一次点击 → **恰 1 个 `/search` 请求**；`/api/{resources}?` per-resource 列表请求数 **== 0**；命中字段标签渲染 |
| **真实集成探针**（临时 `__f018_integration_tmp.spec.ts`，跑后删除） | AC-07/D4 + Integration | 真实 uvicorn + 真实 PG，无响应桩：真实组件渲染真实混合列表（`int-node-gpu`/`int-eth0`、标签「裸金属」「网络接口」、`hostname`/`name`）；真实 Empty → `data-state=empty`；真实 404 → `data-error-code=NOT_FOUND`；真实空关键字 → 400 |

**结果：`85 checks, 0 failures`（后端）+ 前端探针 1 passed + 集成 4 passed。**

---

## 自写变异记录（证明「复用」与「guard 可失败」）

> 两处变异均**逐字节还原**，SHA-256 前后一致，工作树 clean。

### 变异 #1：令 `get_related_resources` 的关联类一律置空

| 项 | 值 |
|---|---|
| 目标 | `backend/app/resource_views/service.py::get_related_resources`（与实现者/协调器的变异目标不同） |
| 变异内容 | 在唯一 404 网关之后插入 `return RelatedResourcesRead(五类 RelatedSet(items=[], total=0))` |
| 锚点是否命中 | 是（断言 anchor 存在后替换） |
| 变异后 SHA | `c86e3a71e7e448b54676959c05382535b29b7a69ec96daf1d838639c08e760d5` |
| 观察到 | 探针 **P1：`total==6` 实得 `1`；六类实得 `{'BARE_METAL'}`；TOTAL 85→60 checks / 13 failures** → **关联类消失、BareMetal 仍在**，证明 `search` 确由该入口派生范围（**复用而非重写**） |
| 还原后 SHA | **`2664b72d2cd6a3194daacbcca3948b33bdc5e3d7d899942b599d653f587dd1f2`**（== 变异前，`diff -q` byte-identical） |

### 变异 #2：向资源 repository 注入大小写折叠 `.lower()`

| 项 | 值 |
|---|---|
| 目标 | `backend/app/bare_metals/repository.py::list_active`（**与实现者所用 `clusters/repository.py` 不同**） |
| 变异内容 | 等值比较 `BareMetal.cluster_id == cluster_id` → `… == int(str(cluster_id).lower())` |
| 锚点是否命中 | 是 |
| 变异后 SHA | `bf60e447e966ef46e05746995533a61fb17566b132998febdbbf2fd7bc927cc8` |
| 观察到 | `pytest -k g018_5` → **2 failed, 1 passed**：`test_g018_5_case_folding_calls_only_in_search_module`、`test_g018_5_resource_and_auth_repositories_are_case_preserving` **变红**；`test_g018_5_search_module_actually_folds_case`（防恒真）仍绿 → guard **可失败、非恒真** |
| 还原后 SHA | **`50dd43487d697761e6100dff5d6d6b5ca611662339efaebdcad27648e4b8c251`**（== 变异前，byte-identical） |
| 还原后复验 | `test_search_guards + test_resource_views_guards + test_auth_guards` → **45 passed** |

---

## Database / Migration

- **无 schema 变更、无 migration**（`layers.database = false`，Database 分支 `NOT_REQUIRED`）。
- `git diff e59cfd9 6aa7c21 -- backend/migrations/` → **空**；`git diff --name-only | grep -i migrat` → **none**。
- `alembic heads` → **`0008_f008_services (head)`**；`versions/` 仍 **8** 个 revision 文件；`alembic history` 末条为 `0008_f008_services`，无新增 revision。
- 真实 PG 上重复 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 均成功达到 `0008_f008_services`。
- 软删过滤在**真实 PostgreSQL**、`raw psycopg` **绕过应用层**置 `deleted_at` 下逐类验证（探针 P6）——非 ORM Mock。

## Backend / API

- 全量 `pytest` **1019 passed / 0 skipped**；F018 专项 `test_search_api` 34、`test_search_guards` 18。
- 端点面封闭：OpenAPI 中搜索路径恰 `GET /api/clusters/{cluster_id}/search`，参数恰 `{cluster_id, keyword, page, page_size}`，无 `requestBody`，既有端点**无** `keyword`（G-018-2/7）。
- 状态优先级实测：`401 > 400（空/空白，先于 404）> 404 > 200（含 Empty）`（探针 P5）。
- `resource` 与 canonical `*Read` **逐字段深等**、无 `deleted_at`（探针 P3）。
- 字段封闭：外键 / `status` / `created_at` / `updated_at` / `carriers` 均不参与匹配（探针 P1/P4）。
- 范围推导复用 F010（G-018-4 AST 守卫 + **变异 #1** 行为证伪）。

## Frontend

- `typecheck` exit 0；`npm run test` **连续 3 次 43 files / 642 passed**；`build` ✓ 8.98s。
- 既有 **618** 条一条不少（642 − 新增 24）。
- 既有 **7 个 `app*Navigation.spec.ts`（26 tests）全绿**：外壳搜索控件位于 `<nav>` 之后，按钮文本「搜索」、输入 placeholder「关键字」、选择器「搜索范围」、标签「资源搜索」，均不含 `集群/裸金属/虚拟机/网络接口/IP 地址/容器/服务`，未被 `findButton()` 首个子串匹配选中。
- 三态互不相同；Empty 不渲染错误、不触发全局 401；错误按 `error.code` 渲染（不解析 `message`）。
- **恰一个请求**：自写探针证明一次搜索只发一个 `/search` 请求、per-resource 列表请求为 0。

## Integration

**真实前后端集成已执行（非 Mock/Fixture）**：真实 `uvicorn 127.0.0.1:8799` + 真实 PostgreSQL `csm_f018_int` + 真实 `SearchResultsPage.vue`；相对 URL 经 `node:http` 直连后端并透传会话 Cookie，**无任何响应 fetch 桩**。结果 **4 passed**：
1. 真实混合列表（BareMetal + NetworkInterface）渲染真实数据与命中字段标签；
2. 真实无命中 → Empty 态（`data-state=empty`），非错误；
3. 真实不存在 Cluster → `data-error-code=NOT_FOUND`；
4. 真实空关键字端点 → `400 VALIDATION_ERROR`。

临时 spec 运行后**已删除**，`git status` 保持 clean。

---

## Defects

**None.** 未发现 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND DEFECT（BLOCKER / HIGH / MEDIUM / LOW 均无）。

## Unverified Areas

1. **生产实例人工核验未执行**（`http://192.168.10.221/`）：架构 Handoff Verification Strategy 要求的人工核验（未选 Cluster 不可发起、单一混合列表呈现、命中字段、Empty 非错误、404 文案、未登录 `/api/...` → 401、既有 7 个导航入口不受影响）**本机无法替代**，**NOT TESTED**。本地等价项已由真实集成探针 + 前端 spec 覆盖，但**不等价于生产实例确认**。
2. **性能 / 规模**：架构 Handoff 的失效阈值（单 Cluster ~10³ BM）与 QPS/p95 未在真实 10⁵ 规模下压测——不属本 Feature 验收项（无性能 SLA），**NOT TESTED**。
3. **生产实例 locale / 排序统计语义**：本机 `zh_CN.UTF-8`（大小写敏感）下 §22 成立；生产库 locale 未核验。

## Test Status

**READY FOR REVIEW**

判定依据：全部 AC-01~AC-08 / AC-D1~AC-D5 均有结果且**无 BLOCKED/FAIL**；无 BLOCKER/HIGH/须修复的 MEDIUM Defect；`database: false`（无必需 DB 分支）；Backend + Frontend 两分支 COMPLETE；**真实前后端集成已验证**。

---

## Test Handoff

### Status

`READY FOR REVIEW`（独立测试通过；实现方与协调器结论未被采信，所有数字均本次独立复现）。

### Verified

- 后端全量 **1019 passed**（真实 PG、独立库、无 skipped）；F018 专项 34 + 18。
- 自写探针 **85 checks / 0 failures**：字段封闭、`matched_fields` 顺序/多字段、canonical 深等、Empty/404/400/401 四态与优先级、真实 PG 逐类软删、只读、范围不越界、Cluster 名称不产生行、分页。
- 两处**自写变异**（`get_related_resources` 置空 → 关联类消失而 BM 保留；`bare_metals/repository.py` 注入 `.lower()` → G-018-5 变红），均 **SHA-256 逐字节还原**。
- 前端 `typecheck` / `build` 通过；`test` **3×642**；既有 **618** 条一条不少；**7 个导航 spec 全绿**。
- **恰一个搜索请求**（自写前端探针）。
- **真实前后端集成 4 passed**（真实 uvicorn + 真实 PG，无响应桩）。
- 无 migration（head 仍 `0008_f008_services`）；`backend/migrations/**` 未改。
- 既有 guard **只增不减**（`EXPECTED_GET_ROUTES` 追加 search；F010 `F009_CLUSTER_PATHS` 追加且保留 F009 四条；无删除既有断言、无 `.skip`、无恒真——G-018-5「必须真的折叠」防恒真用例存在且可区分）。
- 工程门禁：`ruff check` = All checks passed；`ruff format --check` = 173 files already formatted。

### Not Verified

- 生产实例 `http://192.168.10.221/` 人工核验（**本机无法替代**）。
- 规模/性能失效阈值压测（无验收 SLA）。
- 生产库 locale 下的 §22 语义（本机已验证 `cluster-a != Cluster-A`）。

### Blocking Issues

**None.**

### Defect Owner

**None.**

---

## Git 声明

本次仅执行**只读** Git 命令，**未**执行任何 `git add` / commit / 分支切换 / merge 或其他改变 Git 状态的命令。逐条如下：

```text
GIT: git status
GIT: git log --oneline -8
GIT: git rev-parse HEAD
GIT: git show --stat 79f5590
GIT: git diff e59cfd9 6aa7c21 -- tests/test_auth_guards.py tests/test_resource_views_guards.py
GIT: git diff e59cfd9 6aa7c21 -- backend/app/main.py
GIT: git diff --stat e59cfd9 6aa7c21
GIT: git diff e59cfd9 6aa7c21 -- backend/migrations/
GIT: git diff e59cfd9 6aa7c21 --name-only
GIT: git diff e59cfd9 6aa7c21 -- docs/api/f002-bare-metal.md docs/api/f005-ip-address.md docs/api/f009-cluster-resource-view.md docs/api/f010-resource-detail.md
GIT: git status --short
```
