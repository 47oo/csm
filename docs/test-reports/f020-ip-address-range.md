# Test Report — F020 IP 地址范围段（地址池）管理

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验收）
> Date: 2026-09-21
> Feature: F020（E02，P1，`depends_on: [F001, F005]` = DONE）
> 分支：`feature/F020-ip-address-range`
> base `develop` = `0fe65f4`
> 实现提交 = `ca9ae73`（Backend + Frontend 并行完成）
> 测试 HEAD = `abea25d`
> layers：database/backend/frontend 均 COMPLETE；`implementation.test = NOT_STARTED`（本次补齐）

---

## Feature

IP 地址范围段（地址池）管理（F020）— 为每个 Cluster 登记、查询、修改、逻辑删除多个 IPv4 `start_ip`–`end_ip`（含两端）范围段；**不含 IP 分配**（F021，BLOCKED）。

- 新增 `ip_address_ranges` 表（7 列）+ 排它约束不重叠（`btree_gist` / `EXCLUDE`）；
- `app/ip_address_ranges/**` CRUD + 自有严格 IPv4 解析 + 删除守卫（范围内活跃 IP）；
- `frontend`：范围段列表 / 详情 / 登记 / 修正 / 删除 + 三态 / Empty vs Not Found / `error.code` 分支。

## Test Basis

- `AGENTS.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/requirements.md` §12（R-IP-001~003 不变；**R-IP-004** 新增）
- `docs/product/domain-model.md` §5.7 / §8 / §9
- `docs/product/handoffs/f020-ip-address-range.md`（Product Handoff，AC-01 ~ AC-29）
- `docs/architecture/f020-ip-address-range-handoff.md`（Architecture Handoff `READY FOR IMPLEMENTATION`，Test Work + Verification Strategy）
- `docs/database/f020-ip-address-range-migration.md`（Database Handoff `READY FOR DATABASE IMPLEMENTATION`，V-1 ~ V-26）
- `docs/api/f020-ip-address-range.md`（API 契约 **READY**，单一权威）、`docs/api/api-conventions.md`
- ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005
- 先例：`docs/test-reports/f005-ip-address.md`、`docs/reviews/f005-ip-address.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.15**（容器 `csm-f020-test-pg`，`0.0.0.0:55432`，含 `btree_gist`，alembic head `0009_f020_ip_address_ranges`） |
| 测试库 | `csm`（pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head`）、`csm_tester`（本次新建，直连绕应用层证伪 + migration 反复重建）、`csm_integration`（本次新建，真实 uvicorn 集成） |
| 后端真实服务 | `.venv/bin/uvicorn app.main:app`（真实 PG `csm_integration`）：`127.0.0.1:8799` |
| Node / npm | v24.14.0 / 11.9.0（Vite 7.3.6，Vitest 5.0.1，happy-dom） |
| 客户端库 | psycopg 3.3.5 / httpx 0.28.1 |
| collation | `C.UTF-8`；`'abc' = 'ABC'` → `false`（大小写敏感） |

**是否全新**：`csm_tester` / `csm_integration` 及真实 uvicorn、管理员账号均为本次测试新建；pytest 每次从空库重建。**实现方数字未被复用** —— 下表后端 / 前端结果均来自本次独立重跑。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量测试（独立重跑）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://csm:csm@localhost:55432/csm" .venv/bin/python -m pytest -q
11 failed, 1123 passed, 2 warnings in 1103.15s (0:18:23)
```

11 个失败**全部**为其它 Feature 的 concurrency 测试，且失败原因为环境级 DSN 密码丢失
（`psycopg.OperationalError: fe_sendauth: no password supplied`），与 F020 无关，
亦与任何业务断言无关（见 §Defects DEF-01）。**F020 测试无一失败**。

```text
$ .venv/bin/python -m pytest tests/test_ip_address_ranges_api.py tests/test_ip_address_ranges_guards.py \
    tests/test_ip_address_ranges_concurrency.py tests/database/test_ip_address_ranges_schema_guard.py -q
112 passed, 2 warnings in 114.24s
```

### 2. lint / typecheck / build

```text
$ .venv/bin/ruff check backend tests                  → All checks passed!
$ cd frontend && npm run typecheck                    → exit 0（vue-tsc --noEmit）
$ cd frontend && npm run build                        → vue-tsc 通过 + vite build 成功
     dist/assets/index-DcrXBn5T.js 1,149.30 kB（仅 chunk 体积告警）
```

### 3. 前端全量测试（独立重跑）

```text
$ cd frontend && npm test
Test Files  47 passed (47)
     Tests  729 passed (729)   （Duration 63.38s）

$ npx vitest run tests/ipAddressRangesApi.spec.ts tests/ipAddressRangeListPage.spec.ts \
    tests/ipAddressRangeDetailPage.spec.ts tests/appIpAddressRangeNavigation.spec.ts
Test Files  4 passed (4)
     Tests  84 passed (84)
```

### 4. Migration（真实库 `csm_tester`）

```text
$ alembic upgrade head        → 0009（head）；再次 upgrade head → no-op
$ alembic current             → 0009_f020_ip_address_ranges (head)
$ alembic check               → No new upgrade operations detected.
$ alembic downgrade 0008_f008_services
    → to_regclass('public.ip_address_ranges') = None（表被删）
    → btree_gist 仍在；clusters 列不变；既有表 {bare_metals,clusters,containers,ip_addresses,
      network_interfaces,service_carriers,services,sessions,users,virtual_machines} 完好
$ alembic upgrade head        → 重建成功；4 条约束（pk/fk/ck/ex）齐备
$ git diff 0fe65f4..abea25d -- backend/migrations/versions/0001..0008 → 空（基线未改）
```

### 5. 直连数据库证伪（绕过应用层，`csm_tester`；脚本 `assets/f020/raw_db_probe.py`）

| # | 原始 SQL / 操作 | 期望 | 实测输出 | 结果 |
|---|---|---|---|---|
| 1 | `INSERT ... (c,20,30)`，同 Cluster 已有 `[10,20]` | `23P01` | `ExclusionViolation sqlstate=23P01` | PASS |
| 2 | 跨 Cluster 直插完全相同 `[100,200]` | 成功 | `inserted id=4` | PASS |
| 3 | `INSERT ... (30,10)`（start>end） | `23514` | `CheckViolation sqlstate=23514` | PASS |
| 4 | `INSERT ... (-1,10)` / `(0,4294967296)` | `23514` | 均 `sqlstate=23514` | PASS |
| 5 | 先软删 `[300,400]`，再插 `[350,450]` | 成功 | `deleted_id=8 new_active_id=9` | PASS |
| 5b | 相邻闭区间 `[1,10]`/`[11,20]` | 不重叠 | 均插入 | PASS |
| 6 | `information_schema.columns` | 恰 7 列，无 status/name/description/CIDR/IPv6 | `[id, cluster_id, start_ip, end_ip, created_at, updated_at, deleted_at]` | PASS |
| 7 | `pg_constraint` / `information_schema.triggers` | `ex_...`(`x`) + `ck_...`(`c`) 存在、0 触发器 | `[('ck_ip_address_ranges_bounds','c'),('ex_ip_address_ranges_active_no_overlap','x'),('fk_...','f'),('pk_...','p')] triggers=0` | PASS |
| 8 | 不重叠漂移查询 | 0 行 | `rows=[]` | PASS |
| 9 | 活跃范围挂已软删 Cluster 漂移查询 | 检测有效（非 vacuous） | 注入 `raw_orphan_id=12`，查询 `detected_count=1` | PASS |
| E1 | `INSERT ... cluster_id=999999999` | `23503` | `sqlstate=23503` | PASS |
| E2 | 全库 CASCADE FK / 唯一索引 | 无 CASCADE、无 `ux_` | `cascades=[]`；索引 `pk_...` / `ex_...` / `ix_ip_address_ranges_cluster_id` | PASS |
| E3 | `pg_extension` | `btree_gist` | `('btree_gist',)` | PASS |

> 第 9 项说明：数据库**不保证**「活跃范围必挂在活跃 Cluster 下」（FK 只看物理存在），这正是
> Database Handoff §7.2 记录的非 DB invariant；漂移查询真实检出，证明回归断言非 vacuous。

### 6. 静态 guard（第 3.10 项）

```text
$ python -c "from tests.deletion_guard_helpers import scan_deleted_at_writes, ALLOWED_DELETED_AT_WRITER, ..."
global deleted_at writers: {'backend/app/deletion/service.py'}
ip_address_ranges module writers: set()          # 范围段模块零 deleted_at 赋值
$ grep -rn "ip_address_ranges\|parse_ipv4\|extract_ipv4_for_guard" backend/app/ip_addresses/  → NONE
```

`ip_addresses.ip_address` 未新增解析 / 校验 / 归一化（模块零耦合；既有 `test_ip_addresses_guards.py`
保持通过）。既有 guard 套件在 F020 提交中仅做**加法式**演进（新增表名到白名单、head 更新为
`0009`、`CLUSTER_ACTIVE_CHILD_CHECKS` 由精确等值放宽为「成员存在」断言以容纳追加的检查）——
F002 的 BareMetal 检查仍被断言保留，无删除、无弱化业务断言。

### 7. 对抗注入（证明测试可失败，逐字节还原）

| 注入 | 目标 | 结果 | 还原 |
|---|---|---|---|
| `csm_tester` 中 `DROP CONSTRAINT ex_ip_address_ranges_active_no_overlap`，再插同 Cluster 重叠 | 证伪项 #1 | 重叠插入**成功**（探针将 FAIL）→ 排它约束确为真正权威 | 重新 `ADD CONSTRAINT`（同 DDL），复测重叠 → `23P01` |
| `backend/app/ip_address_ranges/deletion.py` 将 `IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS = (...)` 临时改为 `()` | `test_g_f020_5_child_checks_wired` | guard **FAILED ×1**（随后正常） | `cp` 备份回填，`sha256sum` = `d406d214…ed2293` 前后一致，**逐字节还原**；复测 18 passed |

### 8. 真实 HTTP 集成（真实 uvicorn + 真实 PG `csm_integration`；脚本 `assets/f020/integration_http.py`）

```text
===== HTTP INTEGRATION RESULT: PASS 60 FAIL 0 =====
```

覆盖：未认证 5 端点 401 UNAUTHENTICATED / 全局 Empty / AC-02 字段集合恰 6 / AC-09 前导零规范化并落库为
canonical 数值 / AC-03 未识别字段 400 且无写入 / AC-04~08 / AC-10 重叠 409 `OVERLAP`（含共享端点）/
AC-11 跨 Cluster 相同范围 201 / AC-12 PATCH 重叠 409 无部分写入 / AC-13 / AC-14 204 空体 + 立即 404 +
行仍物理存在 `deleted_at` 非空 / AC-15 软删释放重叠 / AC-16 409 `ACTIVE_CHILDREN_EXIST` 且目标
`deleted_at` 仍 NULL / 守卫 `10.0.1.1`、`10.0.1.1/16` 命中、`abc`/空串/前导空白/`not-an-ip`/IPv6 跳过且不 500 /
AC-17 软删范围内全部活跃 IP 后可删 204 / AC-18 删除不级联（Cluster/BM/NIC/IP 逐字段不变）/
AC-19 无状态 / AC-20 Empty vs 404 / AC-21 / AC-22 / 只读 GET 无副作用 / 三项不变式回归 = 0。

### 9. 真实前后端集成（**前端真实 API client** + 真实 uvicorn + 真实 PG）

临时 vitest 探针 `frontend/tests/zzTmpF020Integration.spec.ts`（运行后已删除，`git status` 为空），
使用真实 `frontend/src/api/{auth,clusters,bareMetals,networkInterfaces,ipAddresses,ipAddressRanges}.ts`
经 cookie 罐直连 `127.0.0.1:8799`：

```text
Test Files  1 passed (1)
     Tests  1 passed (1)
```

- 未认证 `listIpAddressRanges()` → `ApiError{401, UNAUTHENTICATED}`；
- `login` → `createCluster` → 存在集群空列表 `items==[]`；缺失集群 → `ApiError{404, NOT_FOUND}`（Empty 与 Not Found 可区分）；
- `createIpAddressRange` 201，键集合**恰为** `{id, cluster_id, start_ip, end_ip, created_at, updated_at}`；
- 重叠 → `ApiError{409, CONFLICT, details 含 OVERLAP}`；跨 Cluster 同范围 → 不同 `id`（201）；
- `getIpAddressRange` / `updateIpAddressRange`（`cluster_id`/`created_at` 不变）/ 删除；
- 真实链路 BM→NIC→IP 后删除范围段 → `ApiError{409, CONFLICT, details 含 ACTIVE_CHILDREN_EXIST}` 且仍可读（无部分写入）；
- 软删 IP 后删除 → resolve `undefined`（204）；再读 → `ApiError{404, NOT_FOUND}`。

---

## Acceptance Criteria Mapping

> 结果仅取 PASS / FAIL / BLOCKED / NOT TESTED。证据以本次独立执行为准。

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 未认证端点 401 且无数据 | HTTP-integration | **PASS** | 5 端点均 401 + `UNAUTHENTICATED`；F020 后端 API `test_ac01` 通过 |
| **AC-02** 登记 201；响应字段恰 `{id, cluster_id, start_ip, end_ip, created_at, updated_at}` | API test + HTTP + 前端 client | **PASS** | `set(body)==READ_FIELDS`；无 deleted_at/status/name |
| **AC-03** 请求未识别字段 400 且无写入 | API test + HTTP | **PASS** | `name/description/status/deleted_at/id/created_at/cidr/prefix_length/usage` → 400，行数 0 |
| **AC-04** `cluster_id` 必填 / 非整数 400 + field | API test + HTTP | **PASS** | 缺失 / `"x"` / `null` → 400 + `field=="cluster_id"`，行数 0 |
| **AC-05** `cluster_id` 须活跃（不存在 / 已删）→ 非 5xx | API test + HTTP | **PASS** | 均 `404 NOT_FOUND`，无写入 |
| **AC-06** `start_ip`/`end_ip` 必填 / 非字符串 400 | API test + HTTP | **PASS** | 缺失 / 非串 → 400 |
| **AC-07** `start_ip <= end_ip` | API test + HTTP + DB V-13 | **PASS** | `start>end` → 400；DB CHECK `23514` |
| **AC-08** IPv4 合法性 | API test + HTTP | **PASS** | `10.0.0.256`/`10.0.0`/`abc`/`1.2.3.4/24`/`2001:db8::1`/空串 → 400 |
| **AC-09** 规范化（前导零） | API test + HTTP + 直连 | **PASS** | `010.000.000.001`→`10.0.0.1`；落库 `167772161` |
| **AC-10** 同 Cluster 活跃重叠保存前拒绝 409 `OVERLAP` 非 5xx | API test + HTTP + DB V-11 | **PASS** | 409 `CONFLICT`+`details[].code=="OVERLAP"`；绕预检直插 → `23P01`→409；共享端点也拒绝；相接不拒绝 |
| **AC-11** 跨 Cluster 相同范围 201 两条 | API test + HTTP + DB V-12 | **PASS** | A/B 各自 `[10.0.0.1,10.0.0.255]` 均 201 |
| **AC-12** PATCH 重叠被阻止无部分写入 | API test + HTTP | **PASS** | 409；PATCH 前后 DB 行逐字节不变 |
| **AC-13** PATCH start/end 200，`cluster_id`/`created_at` 不变 | API test + HTTP | **PASS** | 新值可再读；不可变字段不变 |
| **AC-14** DELETE 204 空体、行保留 `deleted_at` 非空、列表/详情排除 | API test + HTTP + DB V-16 | **PASS** | 204 `content==b""`；`deleted_at` 非空；立即 404 |
| **AC-15** 软删释放重叠 | API test + HTTP + DB V-14 | **PASS** | 软删后同 Cluster 重叠新登记 201 |
| **AC-16** 范围内有活跃 IP 禁止删除 409 `ACTIVE_CHILDREN_EXIST` 无部分写入 | API test + HTTP + 守卫专项 | **PASS** | 409 + code；目标 `deleted_at` 仍 NULL |
| **AC-17** 范围内无活跃 IP（或已软删）可删 204 | API test + HTTP | **PASS** | 范围内全部活跃 IP 软删后 DELETE 204 |
| **AC-18** 删除不级联 | API test + HTTP | **PASS** | Cluster/BM/NIC/IP 逐字段不变；无其它行改动 |
| **AC-19** 无状态（字段/枚举/默认/过滤/端点） | guard G-F020-1/2 + HTTP | **PASS** | 列集 / Read schema / OpenAPI 查询参数均无 `status` |
| **AC-20** 列表 + Empty（不得 404） | API test + HTTP | **PASS** | `{items:[],total:0,...}`；父 Cluster 不存在 → 404（与 Empty 区分）|
| **AC-21** 详情 Not Found（不存在 / 已删不区分） | API test + HTTP | **PASS** | 均 404 `NOT_FOUND` |
| **AC-22** 已删排除（列表 items/total、按 id 404） | API test + HTTP | **PASS** | 已删不在 items/total；`.../{id}` → 404 |
| **AC-23** `ip_address` 自由文本登记逐条不变 | F005 全量测试 + guard G-F020-8 | **PASS** | `test_ip_addresses_api/guards/consistency` 全通过；`ip_addresses` 模块零 F020 耦合、无新增 CHECK |
| **AC-24** R-IP-001~003 不变 | F005 全量测试 + guard | **PASS** | 唯一性 / 跨 Cluster / 无 VRF 语义未改 |
| **AC-25** 不引入分配语义 | guard G-F020-3 + HTTP OpenAPI | **PASS** | 恰 2 个 path / 5 个端点；无 allocate/assign/usage |
| **AC-26** 不引入 CIDR / IPv6 | API test + guard | **PASS** | `1.2.3.4/24`、`2001:db8::1` → 400；无前缀列 / 参数 |
| **AC-27** 无未确认能力（使用率 / 扫描 / 同步 / 导出） | guard G-F020-3 + HTTP | **PASS** | 端点 / 参数 / 列集合封闭 |
| **AC-29** 契约已落盘且 `status=READY`，无契约分裂 | guard G-F020-10 | **PASS** | `docs/api/f020-ip-address-range.md` 存在且 `Status: **READY**` |

**说明**：AC-01 ~ AC-29（含 AC-23/24）全部有结果，**无 FAIL、无 BLOCKED、无 NOT TESTED**。

## Test Work（Architecture Handoff）覆盖

| 项 | 结果 | 独立证据 |
|---|---|---|
| AC-01~AC-22 契约 / 功能 | PASS | API test + HTTP-integration（60/60） |
| 响应字段恰 6（无 status/deleted_at/name） | PASS | `set(body)` 断言 + OpenAPI schema |
| 请求未识别字段 400 无写入 | PASS | 行数前后对比 |
| 重叠 409 `OVERLAP`；删除 409 `ACTIVE_CHILDREN_EXIST` 且目标 `deleted_at` NULL | PASS | HTTP + DB 直读 |
| 证伪 1~9（绕应用层） | PASS | `raw_db_probe.py` 全项 |
| 静态 guard（唯一软删路径 / `ip_address` 无新增校验 / guard 不减弱） | PASS | 摘要 §6 + 注入 |
| Migration 幂等 / downgrade-upgrade / 既有表不变 / `0001-0008` 未改 | PASS | 摘要 §4 |
| 契约 `READY` 无分裂 | PASS | G-F020-10 |
| 删除守卫语义（含前缀命中 / 不可解析跳过不 500） | PASS | HTTP 守卫专项 |
| 并发 V-21 / V-22 | PASS | `tests/test_ip_address_ranges_concurrency.py`（真实 PG + 线程）通过 |

---

## Database / Migration

- 结构断言 V-1 ~ V-10：`tests/database/test_ip_address_ranges_schema_guard.py` **全通过**；本次直连复验列集恰 7、PK/FK/CHECK/EXCLUDE 精确、`btree_gist` 存在、无触发器、无 CASCADE、无显式 collation。
- 约束证伪 V-11 ~ V-16：排它约束 `23P01`、CHECK `23514`、FK `23503`、RESTRICT 非 CASCADE、软删 predicate 生效、软删行保留且回填 `deleted_at`——均通过。
- 不变式回归 V-17 ~ V-19：重叠漂移 = 0、活跃范围挂已删 Cluster = 0、F005 漂移 = 0。
- Migration：`upgrade head` 幂等；`downgrade 0008_f008_services` 删表且保留 `btree_gist`、既有表完好；再 `upgrade head` 一致重建；`alembic check` 无漂移；`0001`–`0008` 逐字节未改。
- 未在生产库执行任何 Migration；所有操作限于一次性测试库。

## Backend / API

- F020 专项后端 112 passed（API / guards / concurrency / schema-guard）。
- 真实 HTTP 集成 60/60 PASS，覆盖状态码、`error.code`、`details[].code`、Empty vs Not Found、只读无副作用、无部分写入、不级联。
- 未认证 401、`VALIDATION_ERROR` / `NOT_FOUND` / `CONFLICT` 分支与契约一致；`23P01` 经 `app/common/sqlstate.py` 单一映射 → 409，无 5xx。
- 删除委托唯一软删路径 `app/deletion/service.py`；`DELETE` 无部分写入。

## Frontend

- `npm run typecheck` exit 0；`npm run build` 成功；前端全量 **729 passed / 47 files**；F020 专项 **84 passed / 4 files**。
- 列表页三态互异（Loading / Empty / Error），Empty 与 Not Found 独立渲染；详情页 `not-found` 独立态；提交 / 删除按 `error.code`（必要时 `details[].code`）分支，不解析 message。
- 仅 `start_ip`/`end_ip` 提供修正入口，`cluster_id` 只读；前端不做 IPv4 校验 / 归一化 / `start<=end` 预判 / 重叠预检（结构性测试验证）。
- 字段集合封闭为 6 字段，无 `status` / `deleted_at` / `name`。

## Integration

- **真实后端 HTTP 集成（真实 uvicorn + 真实 PostgreSQL）**：`PASS 60 FAIL 0`。
- **真实前后端集成**：以真实 `frontend/src/api/**` client 直连真实 uvicorn；契约字段、Empty vs Not Found、`OVERLAP`、`ACTIVE_CHILDREN_EXIST`、404 分支全部验证通过（临时 vitest 探针，运行后删除）。
- 未使用 Mock / Fixture 替代；前端 `/api` 前缀经真实客户端发出。

## Defects

按 Severity 从高到低：

### DEF-01 — TEST INFRA DEFECT（MEDIUM，非 F020）

- **ID**：DEF-01
- **Severity**：MEDIUM
- **Layer**：Test Infra
- **Location**：`tests/test_bare_metals_concurrency.py`、`tests/test_containers_concurrency.py`、`tests/test_ip_addresses_concurrency.py`、`tests/test_network_interfaces_concurrency.py`、`tests/test_services_concurrency.py`、`tests/test_virtual_machines_concurrency.py`（均非 F020 新增 / 修改文件）
- **复现步骤**：以带口令的 TCP DSN（`postgresql+psycopg://csm:csm@localhost:55432/csm`）运行后端全量 pytest。
- **期望**：并发测试建立第二条原始连接成功。
- **实际**：11 个测试失败于 `psycopg.OperationalError: fe_sendauth: no password supplied`。根因：这些测试用 `psycopg.connect(raw_connection_dsn(conn.info.dsn))` 建连，而 `conn.info.dsn` 出于安全**不含口令**（实测 `info.dsn = user=csm dbname=csm host=localhost ...`，无 password）。既有测试按「Unix socket / peer / trust 无口令」环境编写。
- **Owner**：主协调器（测试基础设施 / 夹具；非 Backend / Database 生产实现）
- **影响**：不影响 F020 的任何验收结论；F020 自身并发测试不使用该模式且通过。仅影响「全量 pytest 全绿」的环境表述。

### DEF-02 — 测试文档交叉引用失效（LOW，非功能）

- **ID**：DEF-02
- **Severity**：LOW
- **Layer**：Test Infra
- **Location**：`tests/test_ip_address_ranges_api.py` 文件头 docstring
- **复现步骤**：按 docstring 指向 `tests/database/test_ip_address_ranges_constraints.py` 查找文件。
- **期望**：指向实际存在的约束证伪文件。
- **实际**：实际文件名为 `tests/database/test_ip_address_ranges_schema_guard.py`；引用文件不存在（仅注释，无功能影响）。
- **Owner**：主协调器 / Backend（测试注释）

无 BLOCKER、无 HIGH，无任何 F020 生产实现 / 契约 / 数据库缺陷。

## Unverified Areas

- **其它 Feature 的 11 个 concurrency 测试**在本口令 DSN 环境下因 DEF-01 无法完整执行其阻塞断言；这些测试与 F020 无交集，其结论**不用于** F020 验收。
- 未在 `csm` / `csm_tester` / `csm_integration` 之外的数据库执行任何操作；未对生产库（`csm-prod-postgres-1`）执行任何 Migration 或写入。
- F021（IP 分配）不在本 Feature 范围，未测试。

## Test Status

```text
READY FOR REVIEW
```

依据 tester.md §20：全部 Acceptance Criteria 有结果；无 BLOCKER / HIGH / 必须修复的 MEDIUM；真实前后端集成已验证。DEF-01 / DEF-02 为测试基础设施问题（Owner = 主协调器），非 F020 缺陷，不阻塞本 Feature。

## Test Handoff

### Status
`READY FOR REVIEW`

### Verified
- AC-01 ~ AC-29（逐条 PASS）；Architecture Test Work 全项；Database V-1 ~ V-26 关键项。
- 直连 DB 证伪 1~9 + FK/CASCADE/extension；静态 guard（唯一软删路径、`ip_address` 零耦合、guard 不减弱）。
- Migration 幂等 / downgrade-upgrade / 既有表不变 / `0001-0008` 未改。
- 真实 HTTP 集成 60/60；真实前后端 client 集成通过；真实线程并发 V-21/V-22 通过。
- 对抗注入证明约束与 guard 可失败，且逐字节还原（工作区 `git status --porcelain` 为空）。

### Not Verified
- 其它 Feature 的 11 个 concurrency 测试（DEF-01，与本 Feature 无关）。

### Blocking Issues
无。

### Defect Owner
- DEF-01：主协调器（Test Infra）
- DEF-02：主协调器 / Backend（测试注释）

---

## 本次新增 / 使用的测试资产与命令

- `docs/test-reports/assets/f020/raw_db_probe.py` — 直连 DB 证伪（绕过应用层）。
  命令：`.venv/bin/python docs/test-reports/assets/f020/raw_db_probe.py "postgresql://csm:csm@localhost:55432/csm_tester"`
- `docs/test-reports/assets/f020/integration_http.py` — 真实 uvicorn + 真实 PG HTTP 契约集成。
  命令：`.venv/bin/python docs/test-reports/assets/f020/integration_http.py http://127.0.0.1:8799 "postgresql://csm:csm@localhost:55432/csm_integration"`
- 临时前端集成探针 `frontend/tests/zzTmpF020Integration.spec.ts`（真实前端 client → 真实后端，运行后已删除，未残留）。
- 环境准备命令：
  - `CREATE DATABASE csm_tester` / `CREATE DATABASE csm_integration`；`alembic upgrade head`。
  - `echo "…" | python -m app.auth.cli create-initial-admin --username tester`。
  - `uvicorn app.main:app --host 127.0.0.1 --port 8799`（`CSM_DATABASE_URL=csm_integration`）。
- 未修改任何生产实现代码；唯一临时改动为对抗注入，已 `sha256sum` 校验逐字节还原。

---

GIT: NONE