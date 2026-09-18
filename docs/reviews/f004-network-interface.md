# Review Report — F004 NetworkInterface 登记与管理

> Reviewer Role: reviewer（独立审查）
> Date: 2026-09-18
> Feature: F004（E02，P1，`depends_on: [F002]` = DONE）
> Feature Branch: `feature/F004-network-interface`
> Base Branch: `develop` @ `cf03e014a9abbd0dad88a00da57947e731778513`
> start_commit: `cf03e014a9abbd0dad88a00da57947e731778513`
> 已审查 HEAD: `8958252acc26579eb515e73038cc5318af26904d`
> merge-base(develop, HEAD): `cf03e014a9abbd0dad88a00da57947e731778513`（与 start_commit、base 一致，祖先关系成立）
> Test Report: `docs/test-reports/f004-network-interface.md`（末节 `New Test Status: READY FOR REVIEW`，含 Re-verification）

## Feature

NetworkInterface 管理（F004）— CSM V1 网络资源的第一个资源：网络接口的登记、查询
（含按宿主限定读取）、`technology_type` / `purpose` 两个封闭枚举的维护与逻辑删除，
以及 **NetworkInterface → BareMetal 必选绑定**的真实落地与 F014「宿主有活跃
VirtualMachine 或活跃 NetworkInterface → 不得删宿主」端到端。NetworkInterface
**无状态、无 IP / MAC / 速率 / MTU 字段、无载体多态、无名称唯一性、无 `cluster_id`**。

## Review Status

**APPROVED WITH FOLLOW-UP**

可进入 Merge Gate。不存在 BLOCKER / HIGH / 需在当前 Feature 修复的 MEDIUM；
AC-01 ~ AC-34 全部满足；生产代码变更严格限于 F004 范围；测试经 Reviewer 独立复跑可信；
Tester 报告的 2 项缺陷（F004-T-01 MEDIUM / F004-T-02 LOW）经 Reviewer **独立复现并确认已修复**。
仅存 2 条 LOW 与若干 NOTE 级 Follow-up（见 Findings），均不阻塞合并且不涉及运行时缺陷。

## Scope Reviewed

**独立复现的 Git 证据**

```text
git status --short                        → （空；工作区 clean，无未跟踪交付物）
git rev-parse HEAD                        → 8958252acc26579eb515e73038cc5318af26904d
git rev-parse develop                     → cf03e014a9abbd0dad88a00da57947e731778513
git merge-base develop HEAD               → cf03e014a9abbd0dad88a00da57947e731778513（== base == start_commit）
git log --oneline develop..HEAD           → 10 提交
    8958252 test(F004): re-verify the two fixes
    1af0bbe chore(F004): record the fix checkpoint
    5c63168 fix(F004): remove the nondeterminism and close the guard gap
    f3a1590 test(F004): independent acceptance finds two fixable defects
    e22e234 chore(F004): record the implementation checkpoint
    6ec3b9e feat(F004): implement network interface management
    8defe6c docs(F004): define database design
    dc37cb2 docs(F004): define architecture and API contract
    966c44e docs(F004): define requirements
    fa42a56 chore(F004): initialize feature branch
git diff --stat develop...HEAD            → 60 files changed, 8263 insertions(+), 165 deletions(-)
git diff --cached --stat                  → （空）
git ls-files --others --exclude-standard  → （空）
backend/migrations/versions/0001..0004 diff → （空；基线未被改）
```

候选实现（`6ec3b9e`）、测试验收（`f3a1590`）、修复（`5c63168`）、复验（`8958252`）
均已提交，工作区 clean、无未跟踪交付物，Test Report 末节为 `READY FOR REVIEW`，
满足正式 Review 的 Gate 前提，**非 PARTIAL REVIEW**。

**实际检查范围**

- 完整分支差异 `git diff develop...HEAD`（60 文件）：Backend（`app/network_interfaces/**`、
  `app/models/network_interface.py`、`app/models/__init__.py`、`app/bare_metals/deletion.py`、
  `app/main.py`）、迁移 `0005`、测试（新增 NIC API / 并发 / 约束 / schema guard + 既有 guard 演进）、
  前端（API 客户端 / 列表 / 详情 / 表单 / 删除 composable / `App.vue` / `BareMetalDetailPage.vue`）、
  契约 / 架构 / 产品 / 数据库文档、README、`project-plan.yaml`、前端测试基础设施。
- 独立**重跑**关键测试与工程门禁（真实 PostgreSQL 16.2，临时实例 `/tmp/f004-review-pg`，非复用 Tester 结论）：
  - F004 专项 + 演进 guard（NIC API / guards / concurrency / DB constraints / DB schema guard /
    F009 边界 guard / BareMetal 检查点 guard / migrations / schema）：`179 passed`。
  - 后端**全量**：`551 passed, 2 warnings`（无 skip）。
  - `ruff check backend tests` → All checks passed；`ruff format --check` → 117 files already formatted。
  - `alembic current` → `0005_f004_network_interfaces (head)`；`alembic check` → No new upgrade operations detected。
  - 前端：`npm run test` → `24 files / 307 tests passed`；`npm run typecheck` exit 0；`npm run build` 成功。
- 独立**对照实验**（复现 F004-T-01）：以临时 config（`/tmp`，未改动仓库）停用 `setupFiles`，
  单文件 8 次运行 **4 次失败**；启用 setup 时全量 **307 passed**。
- 独立**时钟看门狗**：90s 内记录 **6 次向后跳变**（最大 601ms），与 Tester 所述宿主机时钟异常一致。
- 独立**源码核实**：`@vue/runtime-dom` `createInvoker`（`e._vts <= invoker.attached` 静默丢事件）
  与 `@vue/test-utils` `trigger()`（`event._vts = Date.now() + 1`）。
- 独立**对抗注入**（内存构造 app，未改动仓库文件）：`test_t29` 扫描检出 `POST /api/nics` 与
  `POST /api/containers`；`test_g009_2` 检出 `POST /api/containers`（不含 `nic` token，符合其 IP/容器/服务边界语义）。

## Product Compliance

**满足。** AC-01 ~ AC-34 逐项对照实现与测试，无 FAIL / BLOCKED / NOT TESTED。

- 字段集合封闭恰 7 字段（无 `deleted_at` / `status` / `cluster_id` / IP / MAC / 速率 / MTU / 载体字段，AC-01/13/31/32/33）。
- `name` 必填（AC-02）；两个封闭枚举字面精确匹配、非法值 `400` + `details[].field`（AC-03/04/05）；
  父宿必选且存在/活跃（AC-06/07/08）；同宿主同名多张均 `201`（AC-09/12）；纯文本原样往返、
  未定义约束**不实现**（AC-10/11）；列表分页与 Empty、详情 Not Found、按宿主 Empty-vs-NotFound（AC-14/15/16/17）。
- 维护仅两枚举、schema 封闭、空 body `400`（AC-18/19/20）；删除 `204` 行保留、不级联、无恢复/批量（AC-21/22/23）；
  软删不产生任何唯一性行为（AC-24）。
- F014 端到端：宿主有活跃 NIC → `409 ACTIVE_CHILDREN_EXIST` 且宿主 `deleted_at` 仍 NULL、
  软删后可删、并发孤立记录不变式 0 行、创建侧 `FOR SHARE`、检查点同时含 VM+NIC 且 NIC 自身检查点显式声明并真实传入
  （AC-25~AC-30）。
- **未越界**：无 IP 端点 / 表 / 字段 / `cluster_id`；无 VM / Container / Service / Cluster 结构与载体选择器；
  无 MAC / 速率 / MTU / 自动发现 / 外部同步；前端三态与 Empty-vs-NotFound 可分、按 `error.code` 分支、
  不重复实现业务守卫（AC-31~AC-34）。

## Architecture Compliance

**符合。** 5 端点与契约一致（`POST` / `GET` / `GET {id}` / `PATCH {id}` / `DELETE {id}`）；
资源表示恰 7 字段；`?bare_metal_id=` 提供 canonical 宿主限定读取（与 F002 `?cluster_id=`、
F006 `?bare_metal_id=` 对称），宿主不存在 / 已删 → `404 NOT_FOUND`，存在但无活跃 NIC → `200 + items==[]`；
`PATCH` 仅两枚举且 `extra="forbid"`；创建对宿主 `FOR SHARE` 并同事务确认活跃；删除委托系统内唯一软删服务。
全部复用 F012/F013/F014/F002/F006 基座，无新框架 / 新依赖 / vue-router / EAV / 多态 / CASCADE / 触发器 / COLLATE。
与 ADR-0002（`TEXT + CHECK`）/ 0003（`id` 路径）/ 0004（单一软删 + 活跃子检查）/ 0005（认证自动覆盖）一致。
**未为 NQ-1（VM 载体）或 NQ-2（名称唯一）预留任何字段 / 参数 / 分支 / 常量。**

## Database Review

**符合 Database Handoff 逐项要求。**

- migration `0005_f004_network_interfaces`（`down_revision = "0004_f006_virtual_machines"`，单一线性 head）：
  一条 `CREATE TABLE` 建齐 **8 列**；`id` `Identity(always=True)`；`bare_metal_id NOT NULL` +
  `fk_network_interfaces_bare_metal` `ON DELETE RESTRICT ON UPDATE RESTRICT`；`name NOT NULL`（无长度 / trim / 字符 / `/` 约束）；
  `technology_type` / `purpose` `NOT NULL` + 两个**逐字匹配** R-NIC-001/002 的 CHECK；时间列 `server_default now()`；
  `deleted_at NULL`；`ix_network_interfaces_bare_metal_id` 存在。
- **唯一索引集合为空**（无 `UNIQUE`、无 `ux_` 前缀、无 partial unique）；
  **无 `status` / IP / MAC / 速率 / MTU / 载体 / `cluster_id` 列**；无 CASCADE / 触发器 / `COLLATE`；无数据迁移。
- `0001` ~ `0004` **diff 为空**，未被改；既有表结构断言（V-15）通过；ORM 模型与 migration 一致
  （`alembic check` 无漂移）。
- 文档同步：`csm-v1-schema-design.md` NIC 段补 `0005` 与「无唯一性约束」；
  `f012-baseline-migration.md` 修订号序列 `0003 → 0004_f006 → 0005_f004 → 0006_f005` 正确。

## Backend Review

**符合。**

- 分层清晰：`router` 仅 HTTP 接线；`service` 承载业务（宿主 `FOR SHARE` 活跃预检、枚举校验、更新、删除）；
  `repository` 读取统一经 `active_filter` / `select_active`，**无第二份 `deleted_at IS NULL` 谓词**，
  无写 `deleted_at` 的方法，**无任何名称唯一性查询方法**。
- 枚举校验**唯一一份**（`validation.py`），创建 / 更新共用；`frozenset` 取值与 R-NIC-001/002 逐字一致；
  DB `CHECK` 为最终权威，`23514` 经通用映射返回 `400`（永不 500，经独立测试验证）。
- 错误语义正确区分「宿主不存在 / 已删 → 404」「Empty → 200」「枚举非法 → 400」，
  未把不同情况塌缩为 `[]` 或 `500`。
- 删除委托 `app/deletion/service.soft_delete()`；`app/bare_metals/deletion.py` 将
  `BARE_METAL_ACTIVE_CHILD_CHECKS` **追加** `has_active_network_interfaces` 并**保留**
  `has_active_virtual_machines`；`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 显式 `= ()` 并由 NIC 删除路径
  `active_children=` 真实传入（AST 可验证）。跨模块依赖无循环导入。

## Frontend Review

**符合。** 列表 / 详情 / 登记 / 维护 / 删除入口齐全；列表页 `loading / empty / error / content` 四态互不相同；
Empty（200 + `items==[]`，文案按是否带宿主过滤区分）与 Not Found（宿主 `404 → ErrorState`，
`data-state="not-found"`）可区分；一律按 `error.code`（必要时 `details[].code`）分支，**不解析 `message`**；
`409 / 404 / 401` 分别处理；表单不对 `name` 做长度 / 空串 / 字符 / trim 校验，也不做唯一性预检，
空 name / 同名仍提交由后端裁决；删除入口不对任何行预判（§21）；`name` / `bare_metal_id` 不可编辑；
无状态展示 / 编辑 / 筛选；无 IP / VM / Container / Service / 平台同步 UI；未引入新依赖。
`App.vue` 视图切换与 BareMetal 详情入口接线正确并保留返回上下文。

## Test Review

**可信，且对抗验证充分。**

- 测试真正覆盖 AC：真实 `TestClient` + 真实 PostgreSQL，且大量断言**绕过应用层**直连 psycopg
  （V-10 直插非法枚举 → `23514`、无效宿主 → `23503`、V-11 同宿主同名两行直插成功、直查
  `information_schema` / `pg_constraint` / `pg_indexes`），非仅验证实现自身逻辑。
- 并发测试（T-26/T-27）使用真实行锁（`FOR UPDATE NOWAIT` 断言持锁），两种交错均验证孤立记录不变式 = 0 行。
- 对抗注入（G-1 ~ G-14 + 跨模块越界路由）由 Tester 证明 19/19 可失败；Reviewer 独立注入复证
  `test_t29` 现可检出 `POST /api/nics`（修复闭合）与 `/api/containers`。
- 未见「迎合实现」的断言：错误分支用与展示无关的 `message` 证明前端不解析 `message`；空 name / 同名仍提交；
  删除守卫不预判。
- 既有 guard 的演进为**增补 / 加强**而非删除：`EXPECTED_TABLES` / `EXPECTED_GET_ROUTES` / 表集合 / 检查点
  均只增；`BOUNDARY_TOKENS` 与 `test_t29` 仅移除已成为合法路由前缀的 NIC token（`nic` 保留），
  `test_t29` 的列集合与 `by-name` 断言保留；`test_migrations` 新增 downgrade 断言。

## Findings

### REV-1

Severity:
LOW

Layer:
Project metadata / Coordinator

Location:
`docs/project/project-plan.yaml`（F004 块 `git.head_commit`）

Problem:
`git.head_commit` 仍为 base commit `cf03e014a9abbd0dad88a00da57947e731778513`，
等于 `start_commit`，未指向候选 HEAD `8958252acc26579eb515e73038cc5318af26904d`；
同块 `implementation.test: COMPLETE` / `backend: FIX_COMPLETE` / `frontend: FIX_COMPLETE`
已就绪，HEAD 字段与之不匹配。

Evidence:
`git diff develop...HEAD -- docs/project/project-plan.yaml` 中 `head_commit: cf03e014...`；
`git rev-parse HEAD` → `8958252a...`。

Impact:
仅计划元数据陈旧，不影响代码、契约、数据库或运行时行为；但会误导后续对「已审查 HEAD」的追溯。

Expected:
由协调器在 Merge Gate 前把 `git.head_commit` 更新为已审查 HEAD（或合并提交），保持一致。

Suggested Owner:
coordinator

### REV-2

Severity:
LOW

Layer:
Backend / Test guards

Location:
`tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns`、
`tests/test_cluster_views_guards.py::BOUNDARY_TOKENS`

Problem:
F004 使 `network-interface` / `network_interface` 成为合法路由 `/api/network-interfaces`
的前缀，故两条 guard 必须移除这两个 token。移除后，以该前缀开头但**并非**合法路由的变体
（如 `POST /api/network-interface`（单数）或 `/api/network-interfaces-extra`）不再被
两条 guard 检出（`nic` 为独立 token，不覆盖此形态）。

Evidence:
Reviewer 独立注入：`test_t29` 扫描检出 `['/api/containers', '/api/nics']`，`test_g009_2` 检出
`['/api/containers']`；两者对 `POST /api/network-interface`（单数）均无覆盖。前缀匹配为
F009 / F002 既有 approach；F006 移除 `virtual-machine` token 时亦存在同类单数缺口。

Impact:
该前缀变体的越界路由回归防线削弱；非 GET 越界路由的缩写形态（`/api/nics`）已由 `nic` 覆盖。
当前无功能性影响。

Expected:
记录为已知边界；如需彻底闭合，可在后续 Feature 将前缀 token 匹配升级为「路由段精确匹配」
（要求同时保持全局扫描，不得收窄范围）。属 Follow-up，不阻塞本 Feature。

Suggested Owner:
backend（后续）

### REV-3

Severity:
NOTE

Layer:
Frontend / Test infrastructure

Location:
`frontend/tests/setup/monotonic-date-now.ts`、`frontend/vite.config.ts`（`setupFiles`）

Problem:
setup 在测试进程内将 `Date.now()` 全局单调化，对**全部**前端 spec 生效。若未来某用例潜藏
「仅当真实时钟回拨时才失败」的时序缺陷，该补丁会使其在异常时钟下仍通过。

Evidence:
- Reviewer 独立对照实验：停用 `setupFiles` 时单文件 8 次运行 **4 次失败**；启用时全量 `307 passed`。
- Reviewer 独立时钟看门狗：90s 内 **6 次**向后跳变（最大 601ms）。
- Reviewer 源码核实：`createInvoker` 的去重分支仅在事件**已带 `_vts`** 时触发（`if (!e._vts){…} else if (…)`），
  真实浏览器事件的 `_vts` 为空，故该分支只在 VTU `trigger()`（`_vts = Date.now()+1`）下可达 →
  **不掩盖产品缺陷**（被丢弃的点击发生在业务 handler 之前）。
- 全套件无任何用例断言 `Date.now` / `performance.now` / fake timers；断言完整性未变。

Impact:
无当前影响与已知被掩盖用例。为可接受的环境（宿主机时钟）归一化；残余风险限于未来编写的
墙钟依赖用例。

Expected:
保留该修复；可在 setup 头注或测试文档中固定「本补丁仅归一化宿主时钟、时钟正常时恒等、
不得据其掩盖时序缺陷」的边界，以便后续维护。

Suggested Owner:
frontend / tester

### REV-4

Severity:
NOTE

Layer:
Frontend / Test configuration

Location:
`frontend/vite.config.ts`（`testTimeout: 20000`）及既有 spec 的 `waitForUi` 超时 `1s/5s → 10s`

Problem:
单用例超时上限与 `vi.waitFor` 轮询上限被放宽（全局 20s / 10s）。

Evidence:
`git diff develop...HEAD -- frontend/tests frontend/vite.config.ts`：被修改的既有 spec
除 timeout / `waitForUi` 包装 / 注释外**无任何断言增删**；F004-T-01 的 flaky 用例在 10s
上限下仍失败，反证该改动并非「放宽到通过」。

Impact:
仅延长真实故障的暴露时间，不改变断言语义；无功能影响。

Expected:
F004-T-01 修复后可将超时回收至更合理上限（Follow-up，不在本 Feature 阻塞）。

Suggested Owner:
frontend

### REV-5

Severity:
NOTE

Layer:
Backend / Test guards（F005 演进点）

Location:
`tests/test_network_interfaces_guards.py::test_g9_nic_active_child_checks_explicitly_declared`

Problem:
该 guard 断言 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS == ()`。当前正确，但 F005 追加
「活跃 IPAddress」检查后此断言必然失效，需随 Feature 演进。

Evidence:
`tests/test_network_interfaces_guards.py` G-9；`app/network_interfaces/deletion.py` 显式空元组。

Impact:
无当前影响；属预期内的 F005 演进点（与 F006 REV-3 同构），记录以防被误当回归或遗漏。

Expected:
F005 落地时将其演进为「tuple 且含活跃 IPAddress 检查」的正向断言，并补非空子检查的端到端 `409`。

Suggested Owner:
backend（F005）

## Existing Defects

对 Tester 已知缺陷逐项独立复核：

- **F004-T-01（MEDIUM，前端 `networkInterfaceListPage.spec.ts` 非确定性失败）→ 已彻底修复（agree）。**
  Reviewer 独立停用 `setupFiles` 后单文件 8 次运行 4 次失败（失败用例在多个用例间漂移），
  启用后全量 `307 passed`；独立看门狗证实宿主机时钟 90s 内 6 次向后跳变；源码核实 Vue invoker
  去重与 VTU `_vts` 的组合机制。修复（`submitWhenEnabled` + 单调 setup）**未删改任何断言**，
  且**不掩盖产品缺陷**（被吞事件发生在业务 handler 前，真实浏览器事件不带 `_vts`）。
  Tester 对严重程度（MEDIUM，测试缺陷而非产品缺陷）的评估合理。
- **F004-T-02（LOW，`test_t29` 移除 `nic` token）→ 已修复（agree）。**
  `forbidden_prefixes` 已加回 `"nic"`（`nic, ip, container, service`），扫描范围仍为**全部** `/api/*`；
  Reviewer 独立注入 `POST /api/nics` 现被 `test_t29` 检出。Tester 的严重程度（LOW）合理。

Reviewer 独立判定：Tester 对两项缺陷的严重程度评估合理，修复后无残余阻塞项；
未发现 Tester 遗漏的、与其报告冲突的缺陷。

## Non-blocking Follow-ups

1. REV-1：协调器在 Merge Gate 前同步 `project-plan.yaml > F004.git.head_commit`。
2. REV-2：后续 Feature 可将前缀 token 匹配升级为路由段精确匹配（保持全局扫描），闭合
   `network-interface` 前缀变体缺口。
3. REV-3：在 setup 或测试文档中固定 monotonic `Date.now()` 补丁的适用边界说明。
4. REV-4：F004-T-01 修复后回收 `testTimeout` / `waitForUi` 超时至合理上限。
5. REV-5：F005 落地时演进 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 相关 guard 与端到端。
6. （承 F014 / F006 已知项）静态 guard 对动态构造 SQL / 动态注册路由的穷举覆盖仍有限。

## Unreviewed Areas

- 浏览器真实 DOM / 视觉 / 网络层渲染（无浏览器自动化环境；前端行为经 vitest + happy-dom 组件测试
  与 Tester 的真实 API client 集成覆盖）。
- 多 uvicorn worker / 跨进程并发压测（无产品需求；并发以真实行锁单机验证）。
- NIC 自身非空子检查 `409` 分支的真实触发（当前 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 为空，契约明示不可达）。
- 静态 guard 对「动态构造 SQL / 动态注册路由」的穷举覆盖（已知残余风险）。

---

## Reviewer 独立判定摘要

- **Guard 质量：通过。** F009 `BOUNDARY_TOKENS` 与 F002 `test_t29` 均**保持全 `/api/*` 全局扫描**，
  仅移除已成为合法路由前缀的 NIC token；`nic` 已加回并被 Reviewer 独立注入复证；既有断言未被净删除。
  未重犯 F006-T-01 的收窄缺陷（残余的前缀变体缺口属固有边界，见 REV-2，LOW）。
- **测试基础设施改动：通过，非掩盖。** 全局 monotonic `Date.now()` 补丁与超时放宽均经 Reviewer 独立
  对照实验与源码核实：补丁有效且必要，不改变断言语义，不掩盖产品缺陷；既有 spec 改动仅放宽时序、未改断言。
- **是否可进入 Merge Gate：可以**（APPROVED WITH FOLLOW-UP）。无 BLOCKER / HIGH / 需当前修复的 MEDIUM；
  AC-01~AC-34 全部满足；实现未超范围；测试可信；后端全量 551 passed、前端 307 passed、
  ruff / alembic check / typecheck / build 全绿。

GIT: NONE
