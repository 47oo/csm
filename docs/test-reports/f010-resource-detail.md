# Test Report — F010 资源详情与关联查询

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验证，未采信实现方 / 协调器结论）
> Date: 2026-09-18
> Feature: F010（E05，P1）
> 分支 `feature/F010-resource-detail`；实现基线 **HEAD = `90e5207`**（实现提交 `6109d4c`；契约 `READY`；`database_design` = NOT_REQUIRED）

---

## Test Basis

`AGENTS.md`；`docs/product/handoffs/f010-resource-detail.md`（AC-01~AC-25；BQ-1/BQ-2 裁定「含间接」）；`requirements.md` §16 R-QUERY-003（含「『与 BareMetal 相关』的确切含义」/ R(B)）与 R-QUERY-004；`docs/architecture/f010-resource-detail-handoff.md`（REQUIRED 1~8、R1~R7）；`docs/api/f010-resource-detail.md`（**契约，唯一权威**）；`docs/project/git-workflow.md`；ADR-0003/0004/0005。

## Environment

| 项 | 值 |
|---|---|
| OS / Python | Linux，Python **3.12.7**（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 真实实例，socket `/tmp/f010-test/pgdata`，本次新建；与 `/tmp/f010-pg`、`/tmp/f010-be` 隔离） |
| Node / npm | **v24.14.0 / 11.9.0**（Vite 7.3.6，Vitest 5.0.1） |
| 独立 DB（每类运行单独库） | `csm_f010_full`（全量）、`csm_f010_adv`（F010 子集 + guards）、`csm_f010_dq`（Tester 自写 106 项检查）、`csm_f010_int`（真实前后端集成） |
| 大小写敏感实测 | `SELECT ('cluster-a'='Cluster-A')` → **False**（locale `zh_CN.UTF-8`） |

**全新性**：PG 实例、4 个测试库、账号均为本次新建；pytest 每次 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 重建。实现方结论未被复用。
结束时仅按 **PID** kill 自己启动的进程（postgres `480805`、uvicorn `498505/498506`）；未触碰无关进程 `uvicorn 55732(:8797)`；未使用 `pkill -f`。

---

## 独立执行摘要（真实命令与数字）

```text
# 后端全量（全新库 csm_f010_full）
$ ... .venv/bin/python -m pytest -q
965 passed, 2 warnings in 1026.79s          # 无 skipped

# F010 专项（独立库 csm_f010_adv）
$ ... pytest -q tests/test_resource_views_api.py tests/test_resource_views_guards.py
30 passed in 34.46s

# Tester 自写独立验收（独立库 csm_f010_dq；自跑 canonical 端点集合深等 + 对抗构造）
$ PYTHONPATH=backend:. ... .venv/bin/python /tmp/f010-adv/independent_check.py
TOTAL 106 checks, 0 failures

# 前端
$ npm run typecheck                → exit 0
$ npm run test                     → 38 files / 562 tests passed（连续 2 次均 562）
$ npx vitest run tests/bareMetalDetailPageRelated.spec.ts tests/appBareMetalRelatedNavigation.spec.ts
                                   → 16 passed（连续 2 次均 16）
$ npm run build                    → ✓ built in 7.01s

# 工程门禁
$ .venv/bin/ruff check backend tests         → All checks passed!
$ .venv/bin/ruff format --check backend tests → 166 files already formatted

# 真实前后端集成（真实 uvicorn :8799 + 真实 PG csm_f010_int；临时 spec，跑后删除）
$ npx vitest run tests/__f010_integration_tmp.spec.ts → 1 passed in 3.54s
```

---

## Acceptance Criteria Mapping（AC-01~AC-25）

| AC | 证据 | Result |
|---|---|---|
| AC-01 NIC 直接父 | independent_check：NIC 集合 == {n1,n2}，B2 的 NIC 排除；canonical 深等 | **PASS** |
| AC-02 IP 经 NIC 间接 | independent_check：IP == {i1,i2,i3}；DB 内 `ip_addresses` **无 `bare_metal_id`**；canonical 并集深等 | **PASS** |
| AC-03 VM 直接宿主 | independent_check：VM == {v1,v2}；canonical 深等 | **PASS** |
| AC-04 Container 直接载体 | independent_check：`(BARE_METAL,B)` 的 cd 出现，载体二元组可见 | **PASS** |
| AC-05-a Container 含间接 | independent_check：经 VM 的 ci 出现；其他主机 / 其他 VM 的 Container 排除 | **PASS** |
| AC-05-b（仅直接） | 用户裁定后**作废** | NOT TESTED（分支作废，不适用） |
| AC-06 Service 直接绑定 | independent_check：s_b 出现；carriers 可见 | **PASS** |
| AC-07-a Service 含间接 | independent_check：s_v1/s_v2/s_ctr 出现；s_multi 多载体**只出现一次**；其他主机 4 个 service 排除 | **PASS** |
| AC-07-b（仅直接） | 作废 | NOT TESTED（作废分支） |
| AC-08 关系依据可见 | independent_check：逐类断言 `bare_metal_id` / `network_interface_id` / 载体二元组 / carriers 交集 | **PASS** |
| AC-09 字面往返 | independent_check：`网卡-α / eth0`、`地址-特殊#1`、`虚机·β`、`容器/γ`、`服务—δ` 逐字面相等 | **PASS** |
| AC-10 404 主体唯一 | independent_check：不存在 B(999999) → 404 `NOT_FOUND` `details==[]`；**raw SQL 置 `deleted_at`（子行仍在）→ 404** 且非 200/500 | **PASS** |
| AC-11 Empty 五类分别成立 | independent_check：B 活跃空关联 → 五类 `{items:[],total:0}`；repo `test_t10_04_*`（含 NIC-only） | **PASS** |
| AC-12 空类不诱使 404 | independent_check：**REQ#1 两情形均 200**；某类空 / 子资源软删均未产生 404 | **PASS** |
| AC-13 三态可区分 | 前端：类级 `data-state=empty`（「该裸金属暂无××」）vs 页面级 `data-state=not-found`（「未找到资源」）；ErrorState 按 `error.code`；Empty **不触发**全局会话失效 | **PASS** |
| AC-14 已软删子资源不出现（逐类） | independent_check：逐类 raw 软删 → 该类不含、其余不受影响（NIC/VM 软删还正确移除其 IP / 其 Service） | **PASS** |
| AC-15 删除后消失、不级联 | independent_check：对无活跃子资源目标逐类 `DELETE`（204）→ 消失，其余类与 canonical 深等恒成立，B 整行逐字段不变 | **PASS** |
| AC-16 主体软删 → 五类 404 | independent_check：raw 软删 B（子行仍在）→ 404 | **PASS** |
| AC-17 无需跨页面拼接 / 可入详情 | 前端：一次聚合请求 + 五类渲染 + 从条目进入 5 个详情并返回（含 cluster 上下文）；真实后端集成页面渲染通过 | **PASS** |
| AC-18 复用 canonical、成员集合深等 | independent_check：**自跑 canonical 端点**逐类集合深等（NIC / IP 并集 / VM / Container 并集 / Service R(B) 并集去重）全部相等；`id` 升序、`total==len` | **PASS** |
| AC-19 只读 | independent_check：查询前后 8 表行数 + B 整行快照相等；OpenAPI 中 `/related` 仅 GET、无 body | **PASS** |
| AC-20 不新增 Cluster 视角 | OpenAPI：`/api/clusters*` 恰为 F009 四路径 | **PASS** |
| AC-21 无 `cluster_id` 类列 / Cluster 过滤 | `git diff c5cb68a..HEAD -- backend/migrations/` 空；`services` 无 `cluster_id`；`/related` 无 query 参数；响应无推导 Cluster 字段 | **PASS** |
| AC-22 无通用关系引擎 | OpenAPI：`/api/bare-metals/{id}/` 二段路径**恰为** `{related}`；五个子资源端点均 404；G-010-2/6/7 + 注入 M2/M5 均失败 | **PASS** |
| AC-23 无状态 / 监控越界 | OpenAPI：五类 `*Read` 无 `status/state`；无状态计数端点或字段 | **PASS** |
| AC-24 认证 | independent_check：未认证 → 401 `UNAUTHENTICATED` 且响应体无资源数据 | **PASS** |
| AC-25 需求归属 | diff 范围仅 `resource_views/**`、`main.py` 挂载、前端关联区 / 导航、契约 / 测试；无 CRUD / 导入 / 删除守卫重复实现 | **PASS** |

---

## 对抗注入记录

`/tmp` 副本注入，逐字节还原；仓库工作区全程 clean。Baseline（pristine 副本）`44 passed`。

| # | 注入点 | 期望 guard | 实测失败 guard | 结果 |
|---|---|---|---|---|
| M1 | `main.py` 加未批准路由 `/api/vpns` | allow-list guard | **`test_product_api_surface_is_closed`（`APPROVED_API_PREFIXES` allow-list）** + `test_g_f_only_read_only_get_routes` | ✅ DETECTED |
| M2 | `resource_views/router.py` 加 `/{id}/network-interfaces` | G-010-7/2 | `test_g010_7`、`test_g010_2`、`test_g_f_only_read_only_get_routes` | ✅ DETECTED |
| M3 | `resource_views/service.py` 注 `deleted_at` 写入 | G-010-5 | `test_g010_5_resource_views_writes_no_deleted_at`、`test_g010_5_global_deleted_at_write_allowlist_unchanged`、`test_g009_5_*` | ✅ DETECTED |
| M4a | `schemas.py` 注 `cluster_id` 响应字段 | G-010-3 | `test_g010_3`、`test_g010_6_source_has_no_forbidden_tokens` | ✅ DETECTED |
| M4b | `service.py` 注 `status` token | G-010-6 | `test_g010_6_source_has_no_forbidden_tokens` | ✅ DETECTED |
| M4c | `service.py` 注 `cluster_id` token | G-010-6 | 同上 | ✅ DETECTED |
| M5 | `service.py` 注自递归函数 | G-010-6 | `test_g010_6_no_self_recursive_function` | ✅ DETECTED |
| M5b | `service.py` 注 `graph/traverse/recursive` token | G-010-6 | `test_g010_6_source_has_no_forbidden_tokens` | ✅ DETECTED |
| M6 | 从 `EXPECTED_GET_ROUTES` **删除**既有成员 `/api/containers` | G-010-1 | `test_g010_1_expected_get_routes_appended_not_replaced`、`test_g_f_only_read_only_get_routes` | ✅ DETECTED |

> **关键说明**：`BOUNDARY_TOKENS` 现为 `()`，其 deny-list guard `test_g009_2` 在 M1 下**未失败**（恒真）；检出未批准路由的是 **`APPROVED_API_PREFIXES` allow-list** 与精确 GET 路由集 guard。与 Architecture Handoff 的裁定一致。

---

## Database / Migration

- `database_design = NOT_REQUIRED`：`git diff c5cb68a..HEAD -- backend/migrations/` **为空**；`0001`–`0008` 与 `backend/app/deletion/service.py` **逐字节未改**。
- `grep deleted_at backend/app/resource_views/` → **无匹配**（无第二条软删过滤 / 写入路径，ADR-0004）。
- 活跃过滤经既有 repository（`*.repository.list_active`）传递；`get_related_resources` 的**唯一 404 网关**为 `bare_metals.service.get_bare_metal_by_id`。
- 关键约束在真实 PostgreSQL 验证（软删过滤、404/Empty、并集去重、`ip_addresses` 无 `bare_metal_id`、`services` 无 `cluster_id`）。

## Backend / API

- **契约字面值修正已核实**：`docs/api/f010-resource-detail.md` 现为 `"technology_type": "Ethernet"` / `"purpose": "Business"`；canonical（F004 `validation.py`）为大小写敏感封闭集，**实测大写 `ETHERNET`/`BUSINESS` → `400 VALIDATION_ERROR`**，实现返回 canonical 字面值。
- 顶层字段封闭恰为五类；元素 schema **逐一复用** canonical `*Read`；`total==len(items)`；`id` 升序；404 覆盖「不存在」与「已软删」且 `details==[]`；非整数 id → 400 `VALIDATION_ERROR(field=bare_metal_id)`。
- **完整快照不截断**（210 NIC 用例通过）。

## Frontend

- **只调用聚合端点**：`BareMetalDetailPage.vue` 只 import `getBareMetal` / `getBareMetalRelated`；组件 spec 证明初始渲染仅 2 个 GET（详情 + `…/related`），**无任何 canonical 列表端点调用、无浏览器端 IP/Container/Service 推导**。
- 三态可区分、`error.code` 分支、Empty 不触发全局会话失效、从条目进入 5 个详情并可返回（保留 cluster 上下文）。
- `typecheck` / `test`（×2，562 passed）/ `build` 全绿。

## Integration（真实前后端）

真实 `uvicorn :8799` + 真实 PostgreSQL 驱动**真实 Vue 组件**（`node:http` 直连替换相对 URL、透传会话 Cookie，**无 fetch 桩**）：五类关联区渲染出真实数据（`int-eth0` / `10.2.0.1` / `int-vm` / `int-ctr` / `int-svc`）；不存在的 BareMetal 渲染页面级 `not-found`（与 Empty 不同）——**1 passed**。临时 spec 运行后**已删除**，仓库 `git status` 保持 clean。

---

## Defects

**None.** 未发现需实现方修复的缺陷。

> 说明（非缺陷）：对「有活跃子资源」的 NIC / VM 直接 `DELETE` 会按 R-DELETE-004 返回 `409`（父删子拦），这是既有正确行为；AC-15 的验证使用了无活跃子资源的合理目标。

---

## Unverified Areas

- **完整浏览器级 E2E**（真实浏览器 + 真实后端）：**NOT TESTED**（无 Playwright / 浏览器自动化）。已以「真实后端 + 真实 Vue 组件渲染」集成替代，覆盖 AC-13 / AC-17 的行为路径。
- **AC-05-b / AC-07-b**：**NOT TESTED**（用户裁定后作废的分支）。
- **聚合规模远大于 210 项的性能 / 聚合分页**（Architecture OPEN #6）：**NOT TESTED**（无已确认需求）。
- 其余全部 AC 均有本次真实执行证据。

---

## Test Status

```text
READY FOR REVIEW
```

## Test Handoff

### Status
`READY FOR REVIEW`（无 BLOCKER / HIGH / 待修 MEDIUM）

### Verified
- AC-01~AC-25（作废分支除外）全部 PASS，均有本次独立证据。
- **AC-18 由 Tester 自跑 canonical 端点逐类集合深等**，证明「复用而非重实现」。
- **REQUIRED #1「唯一 404 网关」对抗验证**：「主机活跃但某类为空」「主机活跃但子资源已软删」均 **200**，未误判 404。
- 404/Empty、逐类软删、逐类 DELETE、认证、只读一致性、契约字面值、迁移零变更。
- **G-010-1~8 经 9 组对抗注入证明可失败**；未批准路由由 `APPROVED_API_PREFIXES` allow-list 检出（`BOUNDARY_TOKENS` deny-list 恒真）。

### Not Verified
- 真实浏览器级 E2E；作废分支 AC-05-b / AC-07-b；超大规模性能。

### Blocking Issues
None.

### Defect Owner
None.

```text
GIT: git rev-parse --short HEAD
GIT: git rev-parse --abbrev-ref HEAD
GIT: git status --short
GIT: git log --oneline -5
GIT: git show --stat --oneline 90e5207
GIT: git diff --stat c5cb68a..HEAD
GIT: git diff --name-only c5cb68a..HEAD -- backend/migrations/ backend/app/deletion/service.py
GIT: git diff c5cb68a..HEAD -- docs/api/f010-resource-detail.md
```
（全部为只读命令；最终 `git status --short` 为空；未执行任何写入 / 暂存 / 提交 / 切分支 / stash / reset / clean。）
