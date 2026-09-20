# Review Report

## Feature

**F019 — 搜索结果聚合视图**（Search Result Aggregation），E05 / M9，`layers = {database: false, backend: true, frontend: true}`。

## Review Status

```text
APPROVED WITH FOLLOW-UP
```

## Scope Reviewed

| 项 | 值 |
|---|---|
| Feature Branch | `feature/F019-search-result-aggregation` |
| Base Branch / SHA | `develop` = `008ecb2780ddabc9d41b6c819e63c84b141249a7` |
| start_commit | `008ecb2780ddabc9d41b6c819e63c84b141249a7` |
| 审查 HEAD | `4524d8e215f4245c354e0e11ea5d0dc2ed4a0dad` |
| merge-base(develop, HEAD) | `008ecb2780ddabc9d41b6c819e63c84b141249a7`（= develop，起点正确，无分叉） |
| 工作区 | `git status --short` 空；`git ls-files --others --exclude-standard` 空；暂存区空 → **clean**，正式 Review 前置满足 |
| Feature 差异 | `git diff --stat develop...HEAD`：21 files, +2771 / −533 |

审查命令：

```text
$ git status --short                         → (空)
$ git rev-parse HEAD                         → 4524d8e215f4245c354e0e11ea5d0dc2ed4a0dad
$ git rev-parse develop                      → 008ecb2780ddabc9d41b6c819e63c84b141249a7
$ git merge-base develop HEAD                → 008ecb2780ddabc9d41b6c819e63c84b141249a7
$ git log --oneline develop..HEAD            → 4524d8e test / 9df3293 chore / 5c278ee feat / b8d732e docs / 0631c13 docs / e499a61 chore
$ git diff --stat develop...HEAD             → 21 files changed, 2771 insertions(+), 533 deletions(-)
$ git diff ; git diff --cached               → (空)
$ git ls-files --others --exclude-standard   → (空)
```

差异文件与任务预期一致：`backend/app/search/{router,schemas,service}.py`、`tests/test_search_api.py`、`tests/test_search_guards.py`、`frontend/src/{api/search.ts,pages/SearchResultsPage.vue,App.vue}`、`frontend/tests/search{Api,ResultsPage,Shell}.spec.ts`、`docs/api/{f018-cluster-keyword-search,f019-search-result-aggregation}.md`、`docs/architecture/f019-...-handoff.md`、`docs/product/requirements.md`、`docs/product/handoffs/f019-....md`、`docs/test-reports/f019-....md`、`docs/project/project-plan.yaml` 及由计划生成的 `backlog.md` / `milestones.md` / `dependency-map.md`。无无关文件、无自动格式化、无新增依赖（`requirements*.txt` / `package.json` 未变更）。

**未审查内容**：生产实例 `http://192.168.10.221/` 人工核验；~10⁵ 规模性能压测；生产库 locale 下的 §22 语义。见 Unreviewed Areas。

## Product Compliance

对照 `docs/product/handoffs/f019-...md`（AC-01~08 / AC-A1~A8）与 `requirements.md` §16 R-QUERY-006（新）/ R-QUERY-005（修订）：

- **AC-01 只读 / AC-02 软删 / AC-03 认证 / AC-04 Not Found vs Empty / AC-05 既有语义 / AC-06 契约一致 / AC-07 三态 / AC-08 范围边界**：逐条有实现与测试证据，独立复跑全绿。
- **AC-A1 扁平单列表**：`SearchAggregationPage.items` 为扁平行列表，行内 `group_key` 表达单元；无多张并列列表。
- **AC-A2 命中/关联标注 + 推导路径**：`role` ∈ {HIT, RELATED}，HIT `derivation_path == null` 且 `matched_fields` 非空；RELATED 路径首=命中项、末=本行。
- **AC-A3 关系扩展**：独立探针确认「输入 IP 片段 → HIT=IP + RELATED=NIC/BM（后二者 `matched_fields==[]`）」。
- **AC-A4 仅搜索涉及资源**：独立探针确认无关 BM 不出现；不上全量倾销。
- **AC-A5 跨单元不去重**：独立探针确认同一 BM 在两个命中项单元各出现一次（`group_key` 不同）。
- **AC-A6 标识字段优先排序**：探针/测试确认。
- **AC-A7 取代 F018 扁列表**：f018 契约 §3 响应与结果顺序已加「被 f019 取代」标注，grep 无第二形态。
- **AC-A8 单元组织顺序**：单元级分页下单元不被拆散（探针 `page_size=1`）。
- **范围控制**：未引入相似度/跨 Cluster/统计/导出/状态筛选/自动发现；`backend/app/search/**` 无越界 token（guard G-018-7 通过）。

**结论：满足产品需求，无 Scope Creep。**

## Architecture Compliance

- 端点 / method / path / query 参数不变（`GET /api/clusters/{cluster_id}/search`，参数恰 `{cluster_id, keyword, page, page_size}`，无 requestBody）；仅取代 Response 200 形态 —— 与 Architecture Decisions #1 一致。
- 关联推导**唯一经** `app.resource_views.service.get_related_resources`：`service.py` 仅导入并调用该入口，`G(B)={B}∪R(B)` 缓存；未自写 FK / 载体并集 / 间接谓词。
- 排序键 = 命中类别 → `resource_type` 固定序 → `id`；单元内 `(type rank, id)`；`total` = 单元数；单元级切片 —— 与 Decisions #3/#4 一致。
- `derivation_path` 确定性：仅用单元内已物化 `*Read` 与 domain-model §6 已确认方向，不判定成员资格、不额外 DB 查询；实现与 Architecture §6 公式 `pathUp(H) ++ reverse(pathUp(M))[1:]` 一致（独立探针以多锚定 Service 验证）。
- `layers.database = false` 成立：`backend/migrations/versions/` 仍 8 个 revision，head = `0008_f008_services` 未变。
- 无新框架 / 依赖；未破坏 App 外壳导航（`App.vue` 仅注释，无功能改动）。

## Database Review

无 schema / migration / index / extension 变更。Alembic head 未变（`0008_f008_services`）。软删过滤仅在真实 PostgreSQL、raw psycopg 绕过应用层下复核（独立探针 + Tester P7 + 证伪实验②）。`database: false` 正确。

## Backend Review

- 分层清晰：router 仅做参数校验 + 404 网关顺序（400 先于 404）；聚合 / 排序 / 路径推导在 service；无业务逻辑堆入 router。
- search 模块**无 `deleted_at`**（guard G-018-3/G-018-4 通过）；无第二条软删路径。
- 复用 canonical `*Read`：`resource` 为六类 `*Read` 联合，逐字段深等（`test_t19_11`）。
- 错误语义 / 状态优先级（401 > 400 > 404 > 200）与 Empty/Not Found 区分正确。
- `_snapshot` 完整快照不静默截断：独立探针以 205 台 BM 验证跨页取全。

## Frontend Review

- 严格使用单一端点，**单请求**无浏览器端拼接 / 关联推导（自写探针与 spec 均验证；证伪实验④可失败）。
- 三态互不相同；Empty 非错误、不触发全局会话失效；错误按 `error.code` 分支，不解析 `message`。
- 命中行/关联行徽标与缩进可区分；`derivation_path` 文案由 `derivation_path` 生成；`matched_fields` 原样渲染。
- 分页按 `total`（单元数）驱动；`page_size` 选项 [10,20,50,100] 均在契约合法区间 [1,200]。
- 依赖未新增。

## Test Review

测试**不是**「实现的新形态」的镜像：覆盖了 AC-A1~A8 与 AC-01~08 的用户示例、头尾路径、跨单元不去重、仅涉及资源、单元级分页、软删（raw psycopg）、只读、四态优先级、canonical 深等、匹配语义、字段封闭。无 `.skip` / `.todo` / 恒真断言。guard 只增不减（`EXPECTED_GET_ROUTES`、`F009_CLUSTER_PATHS` 追加而非替换，且断言可失败）。

**测试质量下降点**（见 Findings 1/2）：F018 的 FK 非匹配用例与「五类资源软删参数化」用例被删除且未等价替代，属覆盖回退，非功能缺陷。

## Independent Re-verification（独立复验，未采信 Tester）

```text
# 环境：一次性 PostgreSQL 容器 f019-review-pg（postgres:16, 端口 55433, 库 csm_review），
#       CSM_TEST_DATABASE_URL 指向该容器；未触碰 csm-prod-* / csm-dev-*；跑后已 docker rm -f。

$ .venv/bin/ruff check backend tests              → All checks passed!
$ .venv/bin/ruff format --check backend tests     → 173 files already formatted

$ CSM_TEST_DATABASE_URL=…csm_review pytest -q tests/test_search_api.py tests/test_search_guards.py
  → 54 passed (35 + 19), 2 warnings in 51.65s

$ CSM_TEST_DATABASE_URL=…csm_review pytest -q
  → 1021 passed, 2 warnings in 1042.96s (0:17:22)   # 0 skipped

$ cd frontend && npm run typecheck  → exit 0
$ cd frontend && npm run test       → 43 files / 645 passed
$ cd frontend && npm run build      → ✓ built in 6.16s (exit 0)

$ ls backend/migrations/versions/   → 0001…0008（8 个）；head 0008_f008_services 未变
```

**Reviewer 自写对抗探针**（`/tmp/f019-probe/probe.py`，跑后删除；一次性 PG）：

1. **多锚定 Service**：S 经 `BARE_METAL(bm1)` 与 `CONTAINER(ctr2→vm2→bm2)` 双载体。搜 `probez` → `total=1`、HIT=SERVICE，单元内含 BM1/NIC1/IP1/BM2/VM2/Ctr2，无关 BM 不出现；各 RELATED 路径首=命中项、末=本行，且 `S→BM1→NIC1→IP1`、`S→Ctr2`、`S→BM1`、`S→Ctr2→VM2→BM2` 与 Architecture §6 公式一致。**通过**（唯一「失败」是我最初对路径的错误预期，实现符合公式）。
2. **`_snapshot` 跨页**：205 台 BM 的 Cluster，搜唯一 token 命中最后一台；搜公共前缀 → `total=205`，page1 行数 200、page2 行数 5，无截断。**通过**。
3. **状态优先级**：不存在 Cluster → 404；raw 软删 Cluster → 404；与探针 1 的 200 并存。**通过**。

**结论：Tester 报告的核心数字（1021 / 645 / ruff）经独立复现一致。**

## Findings

### REV-1

```
Severity: LOW
Layer:    Test
Location: tests/test_search_api.py（对照 develop 版 test_t18_04_foreign_key_values_do_not_match）
Problem:  F018 的「关系外键值不参与匹配」用例被删除，F019 未提供等价替代；且
          SEARCHABLE_FIELDS 未有任何 guard 断言外键字段（cluster_id / bare_metal_id /
          network_interface_id / carrier_type / carrier_id）不在匹配字段清单中。
Evidence: `git diff develop...HEAD -- tests/test_search_api.py` 显示 DEL:
          test_t18_04_foreign_key_values_do_not_match，无对应 ADD；
          `grep "foreign|SEARCHABLE_FIELDS" tests/test_search*.py` 无匹配。
Impact:   契约 §2「明确不参与匹配：关系外键」在交付测试集中不再被证伪；
          若未来有人误将外键加入 SEARCHABLE_FIELDS，测试不会失败。
          当前实现正确（_matched_fields 仅遍历 SEARCHABLE_FIELDS），功能性风险可忽略。
Expected: 新增（a）断言 SEARCHABLE_FIELDS 不含任何外键字段的 guard，或
          （b）以真实 cluster_id / bare_metal_id 的文本形式搜索并断言 total==0。
Suggested Owner: Tester
```

### REV-2

```
Severity: LOW
Layer:    Test
Location: tests/test_search_api.py（对照 develop 版 test_t18_09_soft_deleted_resource_excluded 参数化）
Problem:  F018 对「五类关联资源软删后不出现」的参数化用例被替换为仅覆盖 NIC（RELATED）
          与 BM（HIT）两条；IP / VM / Container / Service 关联行的软删过滤在已提交测试中
          未被直接断言。
Evidence: diff 中 DEL: test_t18_09_soft_deleted_resource_excluded(...resource_type)
          与 test_t18_09_soft_deleted_bare_metal_removed_from_scope，
          ADD: 仅 test_t19_07_soft_deleted_related_resource_excluded（NIC）、
          test_t19_07_soft_deleted_hit_resource_excluded（BM）。
Impact:   软删过滤逻辑经 get_related_resources/repository 统一传递、路径一致，
          功能风险低；但覆盖率较 F018 下降，且 AC-02「关联行均过滤软删」的全类型化证据不足。
Expected: 恢复对五类关联资源（NIC/IP/VM/Container/Service）的软删参数化断言。
Suggested Owner: Tester
```

### REV-3

```
Severity: LOW
Layer:    Project metadata
Location: docs/project/project-plan.yaml features[F019].git.head_commit
Problem:  head_commit 记为 "5c278ee…"（实现提交），而 branch 实际 HEAD 为 "4524d8e…"
          （test report 提交）。字段名 implies 分支尖端，自动消费者会漏掉 test-report 提交。
Evidence: 4524d8e 的提交信息明确标注「实现提交 5c278ee」，但仍将 current_stage 改为 REVIEW；
          HEAD 为 4524d8e。本次 Review 的证据锁定在 4524d8e。
Impact:    协调元数据与实际 HEAD 不一致；不影响代码正确性，但影响后续 Merge Gate 的 SHA 锚定。
Expected: Review 批准 / merge 前将 head_commit 更新为 4524d8e（或明确该字段为「实现提交」语义）。
Suggested Owner: Coordinator / PM
```

### REV-4

```
Severity: NOTE
Layer:    Contract / Architecture
Location: backend/app/search/service.py::_derivation_path / docs/architecture/f019-...-handoff.md §6
Problem:  contract §4.3 未明确多锚定行取根的集合；Architecture §6「取 id 最小的 B*」措辞
          对「从哪个集合取」有歧义。实现取 `min(anchors(hit) ∩ anchors(row))`。
Evidence: 自写探针场景 1（多锚定 Service）验证结果为确定性且满足「首=命中项、末=本行」，
          并与 Architecture §6 公式 pathUp(H)++reverse(pathUp(M))[1:] 完全一致。
Impact:    无功能缺陷；仅文档精度问题。
Expected: 可选：在契约 §4.3 明确「根 = 同时锚定命中项与本行的最小 BareMetal id」。
Suggested Owner: Architect（可选，非阻塞）
```

无 BLOCKER / HIGH / 必须当前修复的 MEDIUM。

## Existing Defects

Tester 报告 **Defects: None**。Reviewer 独立复核后**同意**：不存在 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND 层缺陷。Tester 的严重程度评估合理；REV-1/REV-2 属测试覆盖回退，与 Tester「无缺陷」并不矛盾（其自写探针覆盖了 NIC/BM 软删与聚合主路径），但作为长期质量项记录。

## Non-blocking Follow-ups

1. REV-1：补 FK 非匹配 guard/用例。
2. REV-2：恢复五类关联资源软删参数化。
3. REV-3：更新 F019 的 `head_commit` 为当前 HEAD。
4. REV-4（可选）：明确多锚定 `derivation_path` 取根规则。
5. 架构 NQ-A：单 Cluster BM 达 ~10³ 台时评估集合式推导（本 Feature 明确不预先泛化）。

## Unreviewed Areas

- 生产实例 `http://192.168.10.221/` 人工核验（本机不可替代，NOT TESTED）。
- 10⁵ 资源 / 50 并发规模下的性能与 SLA（本 Feature 无性能验收项，NOT TESTED）。
- 生产库 locale 下的 §22 行为（本机已由既有套件验证 `cluster-a != Cluster-A`，生产库未核验）。

---

## 最终 Verdict

```text
APPROVED WITH FOLLOW-UP
```

依据：无 BLOCKER/HIGH、无必须当前修复的 MEDIUM；AC-01~08 与 AC-A1~A8 全部满足且可由独立证据支撑；实现忠实、未超范围；`database: false` 正确；测试可信且 guard 只增不减。存在 3 项 LOW（测试覆盖回退 + 元数据 SHA）与 1 项 NOTE，作为 Follow-up 处理，不阻塞 Merge。

本批准仅对以下证据有效：**Base `008ecb2` / merge-base `008ecb2` / 审查 HEAD `4524d8e`**。后续任何代码、契约或 Base 变化须重新测试与 Review。
