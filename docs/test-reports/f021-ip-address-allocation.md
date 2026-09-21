# Test Report — F021 IP 地址自动 / 手动分配

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验收）
> Date: 2026-09-21
> Feature: F021（E02，P1，`depends_on: [F020, F005, F004, F002]` = DONE）
> 分支：`feature/F021-ip-address-allocation`
> start `1942ec4`；`develop` base = `1942ec4`
> 实现提交 = `f480ecc`；候选 HEAD = `ae10140`
> layers：`database: false`（无 migration）、`backend: true`、`frontend: true`
> `implementation.test = NOT_STARTED`（本次补齐）

---

## Feature

IP 地址自动 / 手动分配（F021）— 在 F020 已登记的某 Cluster 的**活跃 IP 地址范围段并集**之上，为**指定活跃 NetworkInterface** 创建一条绑定该 NIC 的**现有 IPAddress**：

- `POST /api/ip-addresses/allocate`：自动取并集内**数值最小的未占用 IPv4**（跨范围段全局最小，**不跳过**网络 / 广播 / 网关）；
- `POST /api/ip-addresses/allocate-manual`：手动输入**合法 IPv4**、其**数值**落在某活跃范围内且**字面未占用**；合法非规范输入先规范化再写入，非法格式拒绝；
- **不新建**分配 / 预留实体；唯一产物是现有 IPAddress；唯一性仍为 R-IP-001 partial unique（最终权威）。

## Test Basis

- `AGENTS.md`、`.pi/agents/tester.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/requirements.md` §12（R-IP-001 ~ R-IP-010）、`docs/product/domain-model.md` §5.7 / §8 / §9
- `docs/product/handoffs/f021-ip-address-allocation.md`（Product Handoff，AC-01 ~ AC-33）
- `docs/architecture/f021-ip-address-allocation-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，Test Work / Verification Strategy）
- `docs/api/f021-ip-address-allocation.md`（**API 契约，Status = READY，单一权威**）、`docs/api/f005-ip-address.md`（§10 已按附录 B 修订）
- ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005
- 先例：`docs/test-reports/f020-ip-address-range.md`、`docs/test-reports/f005-ip-address.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.15**（Docker `csm-f020-test-pg`，`0.0.0.0:55432`，含 `btree_gist`） |
| 后端测试库 | `csm`（`CSM_TEST_DATABASE_URL`；pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head`）；本轮设 `PGPASSWORD=csm` 解决 F020 记录的 `fe_sendauth` |
| 证伪库 | `csm_f021_tester`（本次新建；直连原始 SQL + migration 检查） |
| 集成库 | `csm_f021_integration`（本次新建；真实 uvicorn + 真实 PG） |
| 真实后端服务 | `.venv/bin/uvicorn app.main:app`（`CSM_DATABASE_URL=csm_f021_integration`）`127.0.0.1:8798` |
| Node / npm | v24.14.0 / 11.9.0（Vite 7.3.6，Vitest 5.0.1，happy-dom） |
| 客户端库 | psycopg 3.3.5 / httpx 0.28.1；ruff 0.16.7 |
| migration head | `0009_f020_ip_address_ranges`（未变） |

**是否全新**：`csm_f021_tester` / `csm_f021_integration`、真实 uvicorn、管理员账号均为本次新建；pytest 每夹具从空库重建。**实现方数字未被采信**——下列后端 / 前端 / 集成结果均来自本次独立重跑。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量测试（独立重跑）

```text
$ PGPASSWORD=csm CSM_TEST_DATABASE_URL="postgresql+psycopg://csm:csm@localhost:55432/csm" \
    .venv/bin/python -m pytest -q
1204 passed, 2 warnings in 1375.29s (0:22:55)
```

> 全量 **1204 passed / 0 failed**（2 条 warning 为 fastapi/starlette 弃用告警，与 F021 无关）。
> 设 `PGPASSWORD=csm` 后，F020 报告的 11 个 concurrency `fe_sendauth` 失败**全部消失**（详见 Defects）。

### 2. F021 专项后端测试（独立重跑）

```text
$ .venv/bin/python -m pytest tests/test_ip_allocations_api.py tests/test_ip_allocations_guards.py -q
70 passed, 2 warnings in 88.54s
```

### 3. 既有守卫 / 一致性 / schema / migration 套件（独立重跑）

```text
$ .venv/bin/python -m pytest tests/test_ip_addresses_guards.py tests/test_ip_addresses_api.py \
    tests/test_ip_address_ranges_guards.py tests/test_structure_guard.py \
    tests/database/test_ip_addresses_schema_guard.py tests/database/test_ip_address_ranges_schema_guard.py \
    tests/database/test_ip_addresses_constraints.py tests/database/test_migrations.py \
    tests/test_ip_addresses_concurrency.py tests/test_ip_addresses_consistency.py -q
188 passed, 2 warnings in 194.34s
```

### 4. lint / typecheck / build / 前端全量（独立重跑）

```text
$ .venv/bin/ruff check backend tests                  → All checks passed!
$ cd frontend && npm run typecheck                    → exit 0（vue-tsc --noEmit）
$ cd frontend && npm run build                        → vue-tsc 通过 + vite build 成功
     dist/assets/index-D4S5E9wW.js 1,157.27 kB（仅 chunk 体积告警）
$ cd frontend && npm test
     Test Files  51 passed (51)
     Tests       769 passed (769)   （Duration 78.09s）
$ npx vitest run tests/ipAddressAllocateDialog.spec.ts tests/ipAddressAllocationApi.spec.ts \
    tests/ipAddressAllocationNoClientValidation.spec.ts tests/ipAddressListPageAllocation.spec.ts \
    tests/ipAddressesApi.spec.ts
     Test Files 5 passed (5) / Tests 61 passed (61)
```

### 5. 直连数据库证伪（绕应用层，`csm_f021_tester`；脚本 `assets/f021/raw_db_probe.py`）

```text
$ .venv/bin/python docs/test-reports/assets/f021/raw_db_probe.py \
    "postgresql://csm:csm@localhost:55432/csm_f021_tester"
===== RAW DB PROBE: PASS 13 FAIL 0 =====
```

| # | 原始 SQL / 操作 | 期望 | 实测输出 | 结果 |
|---|---|---|---|---|
| 1 | 同 Cluster 两条活跃且字面相同 `10.0.0.1` | `23505` | `UniqueViolation sqlstate=23505` | PASS |
| 2 | 同 Cluster `010.0.0.1` 与 `10.0.0.1`（数值同、字面异） | 均成功 | `ids=1,2 active=2` | PASS |
| 2b | 同字面软删后再插活跃 | 成功 | `second active insert ok` | PASS |
| 3 | 「活跃 IP 挂已软删 NIC」不变式查询（注入 orphan） | 检出 1（非 vacuous） | `detected=1` | PASS |
| 4 | `cluster_id` 漂移查询（一致数据） | 0 行 | `rows=[]` | PASS |
| 5 | `information_schema.tables` 全表集合 | 与基线一致，无分配 / 预留表 | `diff=set()` | PASS |
| 6 | `ip_addresses` 列集合 | 恰 7 列（无 status / 新列） | `[id, network_interface_id, cluster_id, ip_address, created_at, updated_at, deleted_at]` | PASS |
| 7 | `ip_addresses` **非 PK** 唯一索引集合 | 恰 `{ux_ip_addresses_cluster_ip_active}` | 同 | PASS |
| 8 | 排它约束集合 | 恰 `{ex_ip_address_ranges_active_no_overlap}` | 同 | PASS |
| 9 | `information_schema.triggers` | 0 | `triggers=0` | PASS |
| 10 | `pg_extension` | `btree_gist` 存在 | `{plpgsql, btree_gist}` | PASS |
| 11 | `alembic_version` | `0009_f020_ip_address_ranges` | 同 | PASS |
| 12 | 全库 `ON DELETE CASCADE` FK | 无 | `[]` | PASS |

### 6. migration（无 Schema 变更）

```text
$ alembic current   → 0009_f020_ip_address_ranges (head)
$ alembic check     → No new upgrade operations detected.
$ git diff --stat 1942ec4..ae10140 -- backend/migrations/   → 空
```

### 7. 真实 HTTP 集成（真实 uvicorn + 真实 PG `csm_f021_integration`；脚本 `assets/f021/integration_http.py`）

```text
$ .venv/bin/python docs/test-reports/assets/f021/integration_http.py \
    http://127.0.0.1:8798 "postgresql+psycopg://csm:csm@localhost:55432/csm_f021_integration"
===== HTTP INTEGRATION RESULT: PASS 44 FAIL 0 =====
```

覆盖：未认证 401 `UNAUTHENTICATED` / 自动分配跨范围段全局最小（范围乱序）/ 响应字段恰 5 且无 `cluster_id` /
跳过已占用 / 手动成功 + `010.0.0.5→10.0.0.5` 规范化并落库 / 非法格式 8 例 → 400 `INVALID` 且无写入 /
范围外 409 `OUT_OF_RANGE` / 已占用 409 `DUPLICATE` / 未识别字段（`cluster_id`/`status`/`deleted_at`/
`reserved_addresses`/`mode`）→ 400 且无写入 / NIC 不存在 / 已软删 / 宿主 BM 不活跃 → 404 /
`cluster_id` 直连 DB 推导一致 + 漂移 0 / 耗尽 → 409 `NO_AVAILABLE_IP` 且行数前后不变（原子）/
无活跃范围段 → 同耗尽 / F005 对范围外字面仍 201 / 多范围段跳过已占用取下一全局最小 /
广播地址 `10.0.0.255` 不被跳过 / **真实并发线程**两条自动分配 → 恰 `[201, 409]`、落败方 409 `DUPLICATE`、
无 5xx、同字面活跃行 ≤ 1 / 「活跃 IP 挂已软删 NIC」= 0。

真实线程并发关键输出：

```text
[PASS] 19. concurrent auto: exactly one 201 + one 409, no 5xx [201, 409]
[PASS] 19. loser is 409 DUPLICATE {'error': {'code': 'CONFLICT', 'message': '数据完整性冲突',
        'details': [{'field': 'ip_address', 'code': 'DUPLICATE', 'message': '唯一性冲突'}]}}
[PASS] 19. same literal active rows <= 1 1
```

> 「落败方」文案来自 `app/common/sqlstate.py` 对 `23505` 的通用映射，说明**数据库 partial unique 为真正的最终权威**，而非仅应用层预检。

### 8. 真实前后端集成（真实 `frontend/src/api/**` 客户端 + 真实 uvicorn + 真实 PG）

临时 vitest 探针 `frontend/tests/zzTmpF021Integration.spec.ts`（运行后已删除）：

```text
$ F021_BASE=http://127.0.0.1:8798 npx vitest run tests/zzTmpF021Integration.spec.ts
     Test Files 1 passed (1) / Tests 7 passed (7)
```

用真实 `api/auth.ts`（`logout`/`login`）、`api/clusters.ts`、`api/bareMetals.ts`、`api/networkInterfaces.ts`、
`api/ipAddressRanges.ts`、`api/ipAddresses.ts` 经 cookie 罐直连真实后端：

- 未认证 `allocateIpAddress` → `ApiError{401, UNAUTHENTICATED}`；
- 自动分配 201，键集合**恰为** `{id, network_interface_id, ip_address, created_at, updated_at}`，无 `cluster_id`，选中 `10.0.0.1`；
- 手动 `010.0.0.5` → 201 `10.0.0.5`（规范化）；
- `NO_AVAILABLE_IP` / `OUT_OF_RANGE` / `DUPLICATE`（`details[].code`）/ 非法格式 400（`details[].field=ip_address`）/ 404 `NOT_FOUND` 分支均按 `error.code` 命中。

### 9. 对抗注入（证明关键测试可失败，逐字节还原）

| 注入 | 目标 | 结果 | 还原 |
|---|---|---|---|
| `csm_f021_tester` 中 `DROP INDEX ux_ip_addresses_cluster_ip_active`，再跑 raw_db_probe | 证伪项 #1 | `[FAIL] 1. duplicate active literal -> 23505: insert unexpectedly succeeded` → partial unique 确为真正权威 | 依 `pg_indexes.indexdef` 原 DDL 重建，`indexdef` 前后逐字符相同，复跑 raw_db_probe **13 PASS / 0 FAIL** |
| `backend/app/ip_allocations/router.py` 临时注释 `@router.post("/allocate-manual", ...)` 装饰器 | `test_g_f021_1_*` | 两个 G-F021-1 guard **FAILED ×2** → 端点面 guard 可失败 | `cp` 备份回填，`sha256sum` = `b6c59e08…b9312d` 前后一致（**逐字节还原**）；复跑 `test_ip_allocations_guards.py` **12 passed** |

---

## Acceptance Criteria Mapping

> 结果仅取 PASS / FAIL / BLOCKED / NOT TESTED。每条均以本次独立执行为准。

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 未认证 → 401 且无数据 | HTTP step1 + 后端 test_ac01 + 前端探针 | **PASS** | 两分配端点 401 `UNAUTHENTICATED`；`ApiError{401}` |
| **AC-02** 成功 201；响应恰 `{id, network_interface_id, ip_address, created_at, updated_at}` | HTTP step3 + test_ac02 + 前端 | **PASS** | `set(body)==READ_FIELDS`；无 cluster_id/status/deleted_at |
| **AC-03** 请求未识别字段 → 400 且无写入 | HTTP step10 + test_ac03 | **PASS** | `cluster_id/status/deleted_at/reserved_addresses/mode/purpose` → 400；行数不变 |
| **AC-04** `network_interface_id` 必填 / 非整数 → 400 + field | test_ac04 | **PASS** | 缺失/`"abc"`/`null`/`1.5` → 400 + `field=="network_interface_id"`，行数 0 |
| **AC-05** NIC 不存在 / 已软删 / 宿主 BM 不活跃 → 非 5xx | HTTP step11 + test_ac05 | **PASS** | 三情形均 `404 NOT_FOUND`，无写入 |
| **AC-06** Cluster 受控推导；请求 / 响应无 `cluster_id` | HTTP step12 + test_ac06/07 + 前端 | **PASS** | 直连 DB 新 IP `cluster_id` = NIC 宿主 BM `cluster_id`；响应无该字段 |
| **AC-07** 分配后 `cluster_id` 漂移查询 = 0 | HTTP step12 + test_ac06/07 | **PASS** | 漂移 `rows=[]`；「活跃 IP 挂已软删 NIC」= 0 |
| **AC-08** 并集全局最小未占用（乱序多段） | HTTP step3/17 + test_ac08 | **PASS** | `[10.0.0.10-12]`+`[10.0.0.1-3]` → `10.0.0.1`；三段混排占 1,2 → `10.0.0.3` |
| **AC-09** 跳过已占用取下一最小 | HTTP step4/17 + test_ac09 | **PASS** | `10.0.0.1` 占用 → `10.0.0.2`；`10.0.0.1,2` 占用 → `10.0.0.3` |
| **AC-10** 写入 canonical dotted-quad | HTTP step6 + test_ac10 | **PASS** | 范围 `010.000.000.001–003` → 写入 `10.0.0.1`；DB 读回一致 |
| **AC-11** 无隐式保留地址 | HTTP step5/18 + test_ac11 | **PASS** | 范围含 `10.0.0.0` 返回 `10.0.0.0`；广播 `10.0.0.255` 按序选出 |
| **AC-12** 字面相同活跃 ⇒ 占用 | HTTP step4 + test_ac12 | **PASS** | 跳过字面 `10.0.0.1` |
| **AC-13** 字面不同 ⇒ 不占用 | test_ac13 + raw probe #2 | **PASS** | 活跃 `010.0.0.1` 不阻止 `10.0.0.1` |
| **AC-14** 软删释放 | test_ac14 + raw probe #2b | **PASS** | 软删后可再分配同字面 |
| **AC-15** 字面 vs 数值边界 | test_ac15 + raw probe #2 | **PASS** | 活跃 `10.0.0.1/16` 不阻止选 `10.0.0.1`；数值同字面异可共存 |
| **AC-16** 跨 Cluster 相同字面允许 | test_ac16 | **PASS** | Cluster B 取得 A 已占用的 `10.0.0.1` |
| **AC-17** 范围内且未占用 → 201 | HTTP step6 + test_ac17 | **PASS** | `10.0.0.5` → 201，字段恰 5 |
| **AC-17b** `010.0.0.5` → 写入 / 返回 `10.0.0.5` | HTTP step6 + test_ac17b + 前端 | **PASS** | 响应与 DB 均为 `10.0.0.5` |
| **AC-18** 范围外被拒、非 5xx、无写入 | HTTP step8 + test_ac18 | **PASS** | `10.9.9.9` → 409 `OUT_OF_RANGE`；无活跃范围段 → 同 |
| **AC-19** 范围内已占用 → 409 `DUPLICATE` | HTTP step9 + test_ac19 + 前端 | **PASS** | 409 `CONFLICT` + `details[0].code=="DUPLICATE"` |
| **AC-20** 非法 IPv4 → 400 且不创建 | HTTP step7 + test_ac20 + 前端 | **PASS** | `10.0.0.256`/`10.0.0`/`abc`/`1.2.3.4/24`/`2001:db8::1`/空串/含空白 → 400 `INVALID`，行数不变 |
| **AC-21** F005 对范围外字面仍 201 | HTTP step15 + test_ac21 | **PASS** | `POST /api/ip-addresses` 范围外字面 201 |
| **AC-22** 并集耗尽 → 非 500、无写入 | HTTP step13 + test_ac22 | **PASS** | 409 `NO_AVAILABLE_IP`；`ip_addresses` 行数前后不变（原子） |
| **AC-23** 无活跃范围段 → 同耗尽语义 | HTTP step14 + test_ac23 | **PASS** | 409 `NO_AVAILABLE_IP`，无写入，不跨 Cluster |
| **AC-24** 不新增唯一性 / 第二维度 | raw probe #5/#7/#8 + guard G-F021-5/7 | **PASS** | 表/列/唯一索引/排它约束/触发器集合不变；`SQLSTATE_MAP` 键集合不变 |
| **AC-25** 并发同一 IP → 至多一条 201 | HTTP step19 + test_ac25（×2 轮） | **PASS** | 真实线程 `[201, 409]`、落败方 409 `DUPLICATE`、无 5xx、活跃行 ≤ 1 |
| **AC-26** 最终权威为 partial unique（`23505`） | raw probe #1 + test_ac26 | **PASS** | 直插重复活跃 → `23505`；并发落败方经通用映射 → 409（永不 500） |
| **AC-27** R-IP-001 ~ R-IP-004 不变 | F005/F020 全量 + 结构 | **PASS** | `git diff 1942ec4..ae10140 -- backend/app/ip_addresses backend/app/ip_address_ranges` 为空；既有套件全通过 |
| **AC-28** `ip_address` 自由文本立场不变 | F005 全量 + 源码 diff | **PASS** | F005 端点行为不变（AC-21）；`ip_addresses` 源码零改动，无新增格式约束 |
| **AC-29** F021 契约已落盘且 `Status = READY`，无分裂 | 文档检查 + guard | **PASS** | `docs/api/f021-ip-address-allocation.md` `Status: **READY**`（`45f92ef`，先于实现 `f480ecc`）；F005 §10 两处已修订 |
| **AC-30** 不引入分配 / 预留实体 | raw probe #5 + guard G-F021-7 | **PASS** | 全表集合无 allocation/reservation/assigned；无端点带 mode |
| **AC-31** 不引入 CIDR / IPv6 / 保留地址开关 | HTTP step5/7/18 + 结构 | **PASS** | `1.2.3.4/24`、`2001:db8::1` → 400；无前缀 / 保留开关列或端点；网络 / 广播不跳过 |
| **AC-32** 不引入 DHCP / DNS / 外部同步 / 自动发现 | OpenAPI surface guard | **PASS** | 分配面恰 2 个 POST；无其它路径 |
| **AC-33** 前端三态互异 + 按 `error.code`/`details[].code` 分支 + 不解析 message + 不做客户端业务校验 | 前端全量 + 专项 | **PASS** | `data-state` Empty/Loading/Error/Success 互异；`data-error-code`/`data-error-detail-code` 分支；零校验测试通过 |

**说明**：AC-01 ~ AC-33 全部有结果，**无 FAIL、无 BLOCKED、无 NOT TESTED**。

## Architecture Test Work（`Verification Strategy`）覆盖

| 项 | 结果 | 独立证据 |
|---|---|---|
| 契约逐字（状态码 / `error.code` / `details[].code`） | PASS | HTTP 集成 44/44 + 前端探针 |
| AC-01 ~ AC-33 逐条 | PASS | 上表 |
| 响应字段集合恰 5 | PASS | HTTP step3 + OpenAPI + 前端 |
| 请求未识别字段 400 无写入 | PASS | HTTP step10 |
| 绕应用层证伪（重复活跃字面 / 数值同字面异 / 无新结构） | PASS | raw probe 13/13 + §9 注入 |
| 真实线程并发（自动 / 自动+手动 / 与 F005） | PASS | HTTP step19 + test_ac25（×2） |
| 不变式回归（漂移 = 0 / 活跃 IP 挂已软删 NIC = 0 / 结果落于范围） | PASS | HTTP step12/16 + test_ac06/07 |
| 既有语义不变（F005 / F020 全量 + 无新增格式约束） | PASS | 全量 1204 + 源码 diff 空 |
| 静态 guard（F021 新 guard 可失败 / 写入路径唯一） | PASS | 70 passed + §9 注入 |
| migration 无新 head（仍 0009） | PASS | §6 + guard G-F021-6 |
| 文档一致性（契约 READY / F005 §10） | PASS | AC-29 |

---

## Database / Migration

- **无 Schema 变更**：`layers.database = false`；`git diff 1942ec4..ae10140 -- backend/migrations/` 为空；head 仍 `0009_f020_ip_address_ranges`；`alembic check` 无漂移。
- 直连 `csm_f021_tester` 复验：`ip_addresses` 列恰 7、非 PK 唯一索引恰 `{ux_ip_addresses_cluster_ip_active}`、排它约束恰 `{ex_ip_address_ranges_active_no_overlap}`、0 触发器、无 `ON DELETE CASCADE`、`btree_gist` 存在、全表集合与基线一致（无分配 / 预留表）。
- 约束证伪：R-IP-001 partial unique predicate `deleted_at IS NULL` 生效（`23505`）；数值同字面异可共存（R-IP-007）；软删释放。
- 未对生产库（`csm-prod-postgres-1`）执行任何操作；所有破坏性操作限于一次性测试库，且注入后逐字符还原。

## Backend / API

- F021 专项 70 passed；既有守卫 / schema / migration / 一致性套件 188 passed；全量 1204 passed / 0 failed。
- 真实 HTTP 集成 44/44 PASS：状态码、`error.code`、`details[].code`、字段封闭、Empty vs Not Found、无部分写入、耗尽原子性、只读无副作用（无异常写入）。
- **证伪要点**：绕应用层直插重复活跃字面 → `23505`；并发落败方错误文案来自 `sqlstate.py` 通用映射（非预检）→ DB 为最终权威；耗尽在任何写入之前判定（行数不变）。
- `ruff check backend tests` → All checks passed。

## Frontend

- `npm run typecheck` exit 0；`npm run build` 成功；前端全量 **769 passed / 51 files**；F021 专项 **61 passed / 5 files**。
- 分配对话框 `data-state` 覆盖 Empty / Loading / Error / Success 四态互异；错误按 `error.code`（`VALIDATION_ERROR` / `NOT_FOUND` / `CONFLICT`，后者结合 `details[].code` 的 `NO_AVAILABLE_IP` / `OUT_OF_RANGE` / `DUPLICATE`）分支；不解析 `message`。
- 结构性测试证明：手动输入原样提交，不做 IPv4 校验 / trim / 范围 / 占用预检；分配写入路径唯一化（提交逻辑仅在分配对话框）；接线页面不引用分配写函数。
- 真实前端 client 集成见 §8。

## Integration

- **真实后端 HTTP 集成（真实 uvicorn + 真实 PostgreSQL）**：`PASS 44 FAIL 0`。
- **真实前后端集成**：以真实 `frontend/src/api/**` 客户端经 cookie 罐直连真实 uvicorn，覆盖自动 / 手动成功、`010.0.0.5` 规范化、`NO_AVAILABLE_IP`、`OUT_OF_RANGE`、`DUPLICATE`、404、400、401 分支（`7 passed / 1 file`，临时探针运行后删除）。
- **未使用 Mock / Fixture 替代**后端；前端 `/api` 前缀经真实客户端发出。

## Defects

按 Severity 从高到低：

**None.**

- 未发现任何 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND DEFECT。
- F020 报告中的 `DEF-01`（Test Infra，`fe_sendauth`）在本轮以 `PGPASSWORD=csm` 环境变量消除：后端全量 **1204 passed / 0 failed**。该问题属测试环境（Owner = 主协调器），非 F021 缺陷。
- 测试脚本一处**探针自身**问题（持久 psycopg 连接快照滞后导致耗尽行数断言一度误报）已定位并改为全新连接计数；隔离复现确认实现**原子性正确**（`before==after`）。这是测试探针问题，不计为产品缺陷。

## Unverified Areas

- 未在 `csm` / `csm_f021_tester` / `csm_f021_integration` 之外的数据库执行任何操作；未对生产库执行任何 Migration 或写入。
- 已知并发窗口（契约 §6.5：耗尽判定的读快照竞态、分配与范围段删除不互相串行）不在本 Feature 承诺范围，未做专项复现；契约已明确记录，不阻塞。
- 未验证契约明确排除的能力（IPv6 / CIDR / 保留地址开关 / DHCP / DNS / 回收工作流 / 批量 / 审计），因其不在范围内。

## Test Status

```text
READY FOR REVIEW
```

依据 tester.md §20：全部 Acceptance Criteria 有结果；无 BLOCKER / HIGH / 必须修复的 MEDIUM；真实前后端集成已验证（非 Mock）；对抗注入证明关键约束与 guard 可失败且逐字节还原。

## Test Handoff

### Status
`READY FOR REVIEW`

### Verified
- AC-01 ~ AC-33 逐条 PASS；Architecture Test Work 全项。
- 后端全量 1204 passed / 0 failed；F021 专项 70 passed；既有守卫 / schema / migration / 一致性 188 passed；ruff 通过。
- 直连 DB 证伪 13/13（partial unique `23505` / 字面 vs 数值 / 结构不变 / 漂移 / orphan 非 vacuous / head 0009）。
- 真实 HTTP 集成 44/44；真实前后端 client 集成 7/7；真实线程并发恰 `[201, 409]` 且无 5xx、活跃行 ≤ 1。
- 前端全量 769 passed、typecheck、build；F021 专项 61 passed；三态与 `error.code` 分支。
- 对抗注入（DROP partial unique / 注释分配端点）证明测试可失败并逐字节还原。

### Not Verified
- 契约 §6.5 记录的已知瞬态并发窗口（可重试的正常分支，不在产品规则内）。

### Blocking Issues
无。

### Defect Owner
无缺陷。F020 遗留 `DEF-01`（Test Infra）本轮以 `PGPASSWORD` 消除，Owner = 主协调器。

---

## 本次新增 / 使用的测试资产与命令

- `docs/test-reports/assets/f021/raw_db_probe.py` — 直连 DB 证伪（绕过应用层）。
  命令：`.venv/bin/python docs/test-reports/assets/f021/raw_db_probe.py "postgresql://csm:csm@localhost:55432/csm_f021_tester"`
- `docs/test-reports/assets/f021/integration_http.py` — 真实 uvicorn + 真实 PG HTTP 契约 / 并发集成。
  命令：`.venv/bin/python docs/test-reports/assets/f021/integration_http.py http://127.0.0.1:8798 "postgresql+psycopg://csm:csm@localhost:55432/csm_f021_integration"`
- 临时前端集成探针 `frontend/tests/zzTmpF021Integration.spec.ts`（真实前端 client → 真实后端，运行后**已删除**，未残留；工作区 `git status` 仅剩本目录未跟踪资产）。
- 环境准备：`CREATE DATABASE csm_f021_tester / csm_f021_integration`；`CSM_DATABASE_URL=<db> alembic upgrade head`；`uvicorn app.main:app --host 127.0.0.1 --port 8798`（`CSM_DATABASE_URL=csm_f021_integration`）。
- 未修改任何生产实现代码；唯一临时改动为对抗注入（DB 索引 DDL 逐字符还原、`router.py` `sha256sum` 逐字节还原）。

---

GIT: NONE