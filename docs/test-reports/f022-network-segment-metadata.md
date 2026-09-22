# Test Report — F022 网段自定义名称 / 子网掩码 / VLAN 标注

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验收）
> Date: 2026-09-22
> Feature: **F022 网段自定义名称 / 子网掩码 / VLAN 标注**（E02，P1，`depends_on: [F020]` = DONE）
> 分支：`feature/F022-network-segment-metadata`；start `dae7fe9`（= develop base）
> 实现提交 = `65e0cce`（Backend + Frontend）；候选 HEAD = `38e8792`
> migration head = `0010_f022_ip_range_metadata`
> `implementation.test = NOT_STARTED`（本次由 Tester 独立补齐）
> layers：database / backend / frontend 均 COMPLETE（全部必需实现分支）+ 真实前后端集成已执行

---

## Feature

在 F020 已交付的 IP 地址范围段（地址池，`ip_address_ranges`）上**新增 3 个可选元数据字段** `name` / `subnet_mask` / `vlan`，并精确修订 R-IP-004 与 F020 契约（纯增量）。**不新建实体、不改变既有范围段语义、不改变 F021 分配行为。**

- Database：migration `0010_f022_ip_range_metadata`（3 个可空列 + `name` partial unique + `vlan` CHECK）；无回填。
- Backend：`app/ip_address_ranges/**` 增量（新增掩码纯函数、create/update schema、service 校验、repository 查询），**无新端点**。
- Frontend：列表 / 详情 / 登记 / 编辑呈现与录入三字段；错误按 `error.code`（结合 `details[].code`）分支。

## Test Basis

- `AGENTS.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/requirements.md` §12（**修订后的 R-IP-004**，DEC-024 裁定）
- `docs/product/domain-model.md` §5.7 / §8 / §9
- `docs/product/handoffs/f022-network-segment-metadata.md`（Product Handoff，AC-01 ~ AC-30）
- `docs/architecture/f022-network-segment-metadata-handoff.md`（Architecture Handoff `READY FOR IMPLEMENTATION`，Test Work / Verification Strategy）
- `docs/database/f022-ip-address-range-metadata-migration.md`（Database Handoff，V-1 ~ V-34）
- `docs/api/f020-ip-address-range.md`（**纯增量修订后的契约，Status `READY`**，单一权威）
- ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005
- 先例：`docs/test-reports/f020-ip-address-range.md`

## Environment

| 项 | 值 |
|---|---|
| 分支 / HEAD | `feature/F022-network-segment-metadata`，start `dae7fe9`，候选 HEAD `38e8792`，实现提交 `65e0cce` |
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.15**（容器 `csm-f020-test-pg`，`0.0.0.0:55432`，含 `btree_gist`） |
| 测试库（pytest） | `csm`（pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head`） |
| 测试库（直连证伪 / Migration / 对抗） | `csm_f022_tester`（本次新建，独立于 pytest） |
| 测试库（集成） | `csm_f022_integration`（本次新建，真实 uvicorn） |
| 后端真实服务 | `.venv/bin/uvicorn app.main:app --app-dir backend`（真实 PG `csm_f022_integration`）：`127.0.0.1:8799` |
| Node / npm | v24.14.0 / 11.9.0（Vitest 5.0.1、happy-dom；集成探针以 `@vitest-environment node` 运行） |
| 客户端库 | psycopg 3.3.5 / httpx 0.28.1 |
| ruff | `.venv/bin/ruff check backend tests` → All checks passed! |

**是否全新**：`csm_f022_tester` / `csm_f022_integration`、真实 uvicorn、管理员账号均为本次测试新建；pytest 每次从空库重建。**实现方数字未被复用** —— 下表所有结果均来自本次独立重跑。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量测试（独立重跑，含 PGPASSWORD=csm 使并发测试可运行）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://csm:csm@localhost:55432/csm" PGPASSWORD=csm \
    .venv/bin/python -m pytest -q
1228 passed, 2 warnings in 1407.55s (0:23:27)
```

**0 failed**。2 条 warning 均为第三方库 Deprecation（`fastapi.testclient` / `starlette`），与 F022 无关。

```text
$ CSM_TEST_DATABASE_URL="...csm" .venv/bin/python -m pytest -q \
    tests/test_ip_address_range_metadata_guards.py tests/test_ip_address_ranges_api.py \
    tests/test_ip_address_ranges_guards.py tests/test_ip_address_ranges_concurrency.py \
    tests/database/test_ip_address_ranges_schema_guard.py
136 passed, 2 warnings in 153.33s (0:02:33)
```

Tester 补充的独立回归测试（DB 兜底路径）：

```text
$ .venv/bin/python -m pytest -q tests/test_f022_metadata_extra.py
2 passed, 2 warnings in 3.59s
```

### 2. lint / typecheck / build

```text
$ .venv/bin/ruff check backend tests                         → All checks passed!
$ cd frontend && npm run typecheck                           → exit 0（vue-tsc --noEmit）
$ cd frontend && npm run build                               → exit 0（vue-tsc + vite build 成功）
```

### 3. 前端全量测试（独立重跑）

```text
$ cd frontend && npm test
Test Files  51 passed (51)
     Tests  784 passed (784)   （Duration 82.70s）
```

### 4. 直连数据库证伪（绕过应用层，`csm_f022_tester`；脚本 `assets/f022/raw_db_probe.py`）

```text
$ .venv/bin/python docs/test-reports/assets/f022/raw_db_probe.py \
    "postgresql://csm:csm@localhost:55432/csm_f022_tester"
===== RAW DB PROBE RESULT: PASS 32 FAIL 0 =====
```

| # | 原始 SQL / 查询 | 期望 | 实测 | 结果 |
|---|---|---|---|---|
| V-11 | 同 Cluster 直插两条活跃同名 `name` | `23505` | `UniqueViolation sqlstate=23505` | PASS |
| V-12 | 同 Cluster 直插 `web` / `Web` | 均成功 | `ids=3,4` | PASS |
| V-13a | 软删一条后直插同名 | 成功 | `new_active_id=6` | PASS |
| V-13b | 直插两条 `name IS NULL` | 均成功 | `ids=7,8` | PASS |
| V-14 | 跨 Cluster 直插相同 `name` | 均成功 | `ids=9,10` | PASS |
| V-15 | 直插 `vlan=0/4095/5000/-1` | 均 `23514` | 四个 `sqlstate=23514` | PASS |
| V-16 | 直插 `vlan=1/4094/NULL` | 均成功 | `ids=15,16,17` | PASS |
| V-17 | 直插空串 / 含空白 / 超长 `name` | 均成功（无 CHECK） | `ids=18,19,20` | PASS |
| V-18 | 直插非法 / 任意 `subnet_mask` | 均成功（仅应用层） | `ids=21,22` | PASS |
| V-19 | 直插不存在 `cluster_id` | `23503` | `sqlstate=23503` | PASS |
| V-20 | 软删释放 `name` + 重叠 | 成功 | `new_active_id=25` | PASS |
| V-1 | `information_schema.columns` | 恰 10 列，无 status/description/cidr/gateway/dhcp/dns… | `[id,cluster_id,start_ip,end_ip,created_at,updated_at,deleted_at,name,subnet_mask,vlan]` | PASS |
| V-2a | 三列可空、无 default | 均 `YES` / `None` | `[('YES',None)×3]` | PASS |
| V-2b | 三列类型 | `text,text,integer` | 一致 | PASS |
| V-3 | PK | 恰 `pk_ip_address_ranges` | 一致 | PASS |
| V-4 | CHECK 集合 | 恰 `{bounds, vlan_range}`，vlan def 含 1/4094/IS NULL | 一致 | PASS |
| V-5 | FK | 恰 `fk_ip_address_ranges_cluster`（RESTRICT/RESTRICT） | 一致 | PASS |
| V-6 | unique 索引（排除 PK 隐式索引） | 恰 `{ux_ip_address_ranges_cluster_name_active}`；`indexdef` 含 `(cluster_id, name)`、谓词、**无 COLLATE / lower** | 一致 | PASS |
| V-7 | 排它约束 | 恰 `{ex_ip_address_ranges_active_no_overlap}` | 一致 | PASS |
| V-8 | 普通索引 | `ix_ip_address_ranges_cluster_id` 仍在 | 一致 | PASS |
| V-9 | 全库 CASCADE | 无 | `cascades=[]` | PASS |
| V-10a | 触发器 | 0 | `triggers=[]` | PASS |
| V-10b | 所有列 `collation_name` | 均 NULL | 一致 | PASS |
| V-26 | 三列省略时取 NULL（无回填） | `(None,None,None)` | 一致 | PASS |
| R-1 | 同 Cluster 活跃重叠漂移 | 0 行 | `rows=[]` | PASS |
| R-2 | 活跃范围挂已软删 Cluster | 0 | `count=0` | PASS |
| R-3 | F005 漂移 | 0 行 | `rows=[]` | PASS |
| R-4 | 同 Cluster 活跃同名重复 | 0 行 | `rows=[]` | PASS |
| R-5 | vlan 越界 | 0 行 | `rows=[]` | PASS |

> V-11 证伪：应用层预检被绕过时，partial unique index 仍是最终权威，返回 `23505`。
> V-15 证伪：显式构造 `vlan` 越界，DB CHECK 是最终兜底。

### 5. Migration（真实库 `csm_f022_tester`）

```text
$ alembic upgrade head            → 0010_f022_ip_range_metadata（head）
$ alembic upgrade head            → 二次 no-op（无新操作）
$ alembic current                 → 0010_f022_ip_range_metadata (head)
$ alembic check                   → No new upgrade operations detected.（无漂移）
$ alembic downgrade 0009_f020_ip_address_ranges
    → 列集合回退为 7 列；索引回退为 {pk, ix, ex}；CHECK 回退为 {ck_..._bounds}（名称/掩码/vlan 对象被删）
$ alembic upgrade head            → 一致重建（10 列 + ux_..._cluster_name_active）
```

- `alembic_version.version_num` 列宽仍为 `character varying(32)`（本 Feature 未改基础设施列）。
- `git diff dae7fe9..38e8792 -- backend/migrations/versions/` 仅新增 `0010_f022_ip_range_metadata.py`（+72）；**`0001`–`0009` 逐字节未改**。
- migration 不含 `UPDATE` / `server_default` / 回填；既有行三列取 `NULL`（V-26 佐证）。

### 6. 静态 guard（不减弱）

```text
deleted_at writers: {'backend/app/deletion/service.py'}     # 唯一软删写入路径
ip_address_ranges module writers: {}                        # 范围段模块零 deleted_at 赋值
SQLSTATE keys: ['23502','23503','23505','23514','23P01']     # 键集合不变（未新增）
23505 → 409 CONFLICT DUPLICATE
```

- 唯一 IPv4 / 掩码解析实现仍在 `backend/app/ip_address_ranges/ipv4.py`（`parse_ipv4` / `format_ipv4` / `parse_subnet_mask` / `extract_ipv4_for_guard`），由 G-F022-5 断言。
- 既有 head guard 的演进为**纯 head 字符串更新**（`0009` → `0010`）与断言集合收紧（F020 unique 索引集合由「无 ux_」改为「恰为 `{ux_...}`」），**未删除任何业务断言**。
- 「不实现未确认能力」guard（G-F022-9）：不出现 `name` 长度 / trim / 空串 / 字符集校验、掩码自洽校验、VLAN 唯一性、CIDR / IPv6 / 网关 / DHCP / DNS / 使用率字段或端点。

### 7. 对抗注入（证明关键测试可失败；DB 级，脚本 `assets/f022/adversarial_probe.py`）

```text
BEFORE indexdef: CREATE UNIQUE INDEX ux_ip_address_ranges_cluster_name_active ... WHERE ((deleted_at IS NULL) AND (name IS NOT NULL))
BEFORE checkdef: CHECK (((vlan IS NULL) OR ((vlan >= 1) AND (vlan <= 4094))))
1) DROP INDEX 后直插同名：SUCCEEDED    -> 探针 V-11 会 FAIL（partial unique 确为权威）
   恢复 indexdef：与原定义一致
2) DROP CHECK 后直插 vlan=0：SUCCEEDED -> 探针 V-15 会 FAIL（CHECK 确为权威）
   恢复 checkdef：与原定义一致
3a) 恢复后直插同名 -> 23505；3b) 恢复后 vlan=0 -> 23514
RESTORE VERIFIED（indexdef + checkdef 与原始逐字节一致）。
```

- 注入均为**测试库 DDL 级**，未触碰任何生产实现代码；注入行在恢复前删除；恢复后再次验证约束生效。

### 8. 真实 HTTP 集成（真实 uvicorn + 真实 PG `csm_f022_integration`；脚本 `assets/f022/integration_http.py`）

```text
$ .venv/bin/python docs/test-reports/assets/f022/integration_http.py \
    "http://127.0.0.1:8799" "postgresql://csm:csm@localhost:55432/csm_f022_integration"
===== HTTP INTEGRATION RESULT: PASS 91 FAIL 0 =====
```

覆盖：未认证 5 端点 401 + 无写入 / 全局 Empty / 9 字段封闭 / 未知字段 400 无写入 / 三字段缺失 201 且 `null` / 往返一致 /
`name` 409 `DUPLICATE`（`field=name`，无写入）/ 跨 Cluster 201 / `web`·`Web` 201 / 软删释放 / 空串·空白 name 当前被接受 /
合法掩码原样回读 / 非法掩码 400`field=subnet_mask`（`255.0.255.0`/`255.255.255.1`/`255.255.255.256`/`10.0.0.1`/`abc`/`/24`/IPv6/空串/空白）/
掩码不自洽仍 201 / `vlan` 1·4094 201、`0`·`4095`·`4096`·`-1`·`100.5`·`"100"`·`true`·`1.0` 400`field=vlan` / 共用 vlan 201 /
PATCH 三字段修正·`null` 清空·`start/end` 的 `null` 400·空 body 400·改同 Cluster 已用 name 409`DUPLICATE` 无部分写入·改自身 name 200 /
重叠 409 `OVERLAP` / 软删释放重叠 / 删除守卫 409 `ACTIVE_CHILDREN_EXIST` 且 `deleted_at` 仍 NULL /
无 status / IPv4 规范化 / F005 自由文本原样 / Empty vs Not Found / 404 / 只读 GET 无副作用。

### 9. 真实前后端集成（真实前端 API client + 真实 uvicorn + 真实 PG）

临时 vitest 探针（`@vitest-environment node`）使用真实
`frontend/src/api/{auth,clusters,ipAddressRanges,http}.ts` 经 cookie 罐直连 `127.0.0.1:8799`：

```text
Test Files  1 passed (1)
     Tests  5 passed (5)     （连续重跑 5 次均 5 passed）
```

覆盖：未认证 `listIpAddressRanges()` → `ApiError{401, UNAUTHENTICATED}`；登录后 Empty（`items==[]`）与
不存在 Cluster（`404, NOT_FOUND`）可区分；`createIpAddressRange` 201 且键集合**恰为 9 字段**，三字段值回读一致；
`updateIpAddressRange` 以 `null` 清空；同 Cluster 同名 → `ApiError{409, CONFLICT, details 含 DUPLICATE}`；
非法掩码 → `ApiError{400, VALIDATION_ERROR, details 含 field=subnet_mask}`；越界 VLAN → 400 含 `field=vlan`；
不存在 id → `404, NOT_FOUND`；软删后读取 → 404。运行后探针已删除（`git status` 无残留源码改动）。

### 10. 并发同名登记（真实 HTTP）

```text
12 个并发 POST /api/ip-address-ranges 使用同一 name：
codes: [201, 409 ×11]   → 201:1 409:11 5xx:0
```

「同 Cluster 活跃 `name` 唯一」在并发下至多一条成功，其余 409，**无 5xx**（partial unique 为最终权威）。

---

## Acceptance Criteria Mapping

> 结果仅取 PASS / FAIL / BLOCKED / NOT TESTED。证据以本次独立执行为准。

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 未认证端点 401 且无数据 / 无写入 | HTTP integration | **PASS** | 5 端点均 401 + `UNAUTHENTICATED`；写入前后行数不变 |
| **AC-02** 登记 201；响应字段恰 9 | HTTP + guard G-F022-1/2 | **PASS** | `set(body)==READ_FIELDS`；无 `deleted_at`/`status`/`description`/用途 |
| **AC-03** 未识别字段 400 且无写入 | HTTP + API test | **PASS** | `description/status/deleted_at/id/created_at/updated_at/gateway/cidr/prefix_length/purpose` → 400；行数 0 |
| **AC-04** 三字段可选，缺失不阻断 | HTTP | **PASS** | 仅 3 字段 → 201，三字段响应均 `null`（键存在） |
| **AC-05** 三字段往返一致 | HTTP + 前端 client | **PASS** | 登记后 `GET /{id}` 与创建响应逐字段一致 |
| **AC-06** 同 Cluster 活跃唯一，保存前阻止 | HTTP + DB V-11 + 兜底测试 | **PASS** | 409 `CONFLICT` + `details[].code=="DUPLICATE"` + `field=="name"`，无写入；直插 `23505`；绕过预检仍 409 |
| **AC-07** 跨 Cluster 可重复 | HTTP + DB V-14 | **PASS** | A/B 同名均 201；直插同名均成功 |
| **AC-08** 区分大小写 | HTTP + DB V-12 | **PASS** | `web`/`Web` 均 201；`indexdef` 无 `COLLATE`/`lower(` |
| **AC-09** 软删释放 | HTTP + DB V-13a/V-20 | **PASS** | 软删后同名再登记 201 |
| **AC-10** 未定义约束不实现 | HTTP + guard G-F022-9 + DB V-17 | **PASS** | 空串 / 含首尾空白 name 当前均为 201；无 trim / 长度 / 字符集校验（**未断言为空 name 合法**） |
| **AC-11** 合法掩码接受并原样回读 | HTTP + G-F020-7 | **PASS** | `255.255.255.0`/`255.255.0.0`/`255.0.0.0`/`0.0.0.0`/`255.255.255.255` → 201 且原样 |
| **AC-12** 非法掩码拒绝 | HTTP + API test | **PASS** | `255.0.255.0`/`255.255.255.1`/`255.255.255.256`/`10.0.0.1`/`abc`/`/24`/IPv6/空串/空白 → 400 + `field=subnet_mask`，无写入 |
| **AC-13** 不强制与 start–end 自洽 | HTTP | **PASS** | `10.1.1.1`–`10.1.2.10` + `255.255.255.0` → 201 |
| **AC-14** V1 仅 IPv4，不用 CIDR | HTTP + guard | **PASS** | 掩码 `/24`、IPv6 被拒；无前缀列 / 参数 |
| **AC-15** vlan 1 / 4094 → 201 | HTTP + DB V-16 | **PASS** | 均 201；直插 1/4094/NULL 均成功 |
| **AC-16** 保留值 / 越界 / 非整数拒绝 | HTTP + DB V-15 | **PASS** | `0`/`4095`/`4096`/`-1`/`100.5`/`"100"`/`true`/`1.0` → 400 + `field=vlan`；直插越界 `23514` |
| **AC-17** vlan 不唯一 | HTTP | **PASS** | 同 Cluster 两段共用 vlan → 均 201 |
| **AC-18** 仅新增 name 唯一性 | DB V-6 / G-F022-9 | **PASS** | unique 索引恰 `{ux_ip_address_ranges_cluster_name_active}`；无 VLAN / 复合 / 其它唯一 |
| **AC-19** 重叠判定不变 | HTTP + DB R-1 | **PASS** | 409 `OVERLAP`；跨 Cluster 同范围 201；漂移 = 0 |
| **AC-20** 软删释放不变 | HTTP + DB V-20 | **PASS** | 软删后同 Cluster 重叠新登记 201 |
| **AC-21** 删除守卫不变 | HTTP + API test | **PASS** | 409 `ACTIVE_CHILDREN_EXIST`，目标 `deleted_at` 仍 NULL；软删 IP 后 204 |
| **AC-22** 无状态不变 | HTTP + DB V-1 + guard | **PASS** | 表 / 响应 / 请求均无 `status`（请求含 status → 400） |
| **AC-23** IPv4 规范化不变 | HTTP + API test | **PASS** | `010.020.000.001` → `10.20.0.1` |
| **AC-24** R-IP-001~003 / R-IP-005~010 不变 | 全量 + guard | **PASS** | F005 / F021 全量测试通过；`ip_allocations` 与 F021 契约自 `dae7fe9` 未改 |
| **AC-25** 分配不按掩码 / VLAN 过滤 | 全量 + 静态检查 | **PASS** | `app/ip_allocations/**` 无 `subnet_mask`/`vlan` 引用；F021 guard 通过 |
| **AC-26** F005 `ip_address` 立场不变 | HTTP + guard G-F020-8 | **PASS** | 自由文本 `"  weird literal  "` 原样存取；`ip_addresses` 模块零耦合 |
| **AC-27** 不引入 CIDR / IPv6 / 网关 / DHCP / DNS / 使用率 / 自动发现 / 外部同步 | guard G-F022-2/3/9 + DB V-1 | **PASS** | 列集合、OpenAPI 路径 / 参数封闭 |
| **AC-28** 前端三态与错误分支 | 前端全量 + 专项 | **PASS** | Loading / Empty / Not Found 互异；错误按 `error.code`（+`details[].code`）分支，含 `DUPLICATE`；不解析 message；客户端无 name / 掩码 / VLAN 业务校验 |
| **AC-29** 契约一致性（`status=READY`，无分裂） | guard G-F020-10 / G-F022-2 | **PASS** | `docs/api/f020-ip-address-range.md` 存在且 `Status: **READY**`；实现与契约一致 |
| **AC-30** 迁移形态 | Migration + DB V-1~V-10 | **PASS** | `0010_f022_ip_range_metadata`（`down_revision=0009`），3 可空列 + `name` partial unique；无回填；未改其它表 / 列 |

**说明**：AC-01 ~ AC-30 **全部有结果，无 FAIL、无 BLOCKED、无 NOT TESTED**。

## Test Work（Architecture Handoff）覆盖

| 项 | 结果 | 独立证据 |
|---|---|---|
| 契约 / 功能 AC-01~AC-30 | PASS | HTTP integration 91/91 + 后端专项 136 |
| 响应恰 9 字段；请求字段封闭；三字段缺失 → 201 null；往返一致 | PASS | HTTP + guard G-F022-1/2 |
| `name` 唯一 / 大小写 / 软删 / 跨 Cluster | PASS | HTTP + DB V-11~V-14 |
| 掩码合法 / 非法 / 不自洽 | PASS | HTTP + G-F020-7 |
| `vlan` 边界 / 非整数 / 不唯一 | PASS | HTTP + DB V-15/V-16 |
| PATCH 专项（修正 / 清空 / null / 空 body / 冲突无部分写入 / 自身名） | PASS | HTTP integration |
| 既有语义不变（重叠 / 软删 / 守卫 / 无状态 / 规范化 / R-IP-001~003/005~010 / 分配 / F005） | PASS | HTTP + 全量 1228 + guard |
| 证伪 1~9（绕应用层） | PASS | raw_db_probe 32/32 |
| 静态 guard（唯一软删路径 / 唯一解析 / SQLSTATE 键 / 不实现未确认能力） | PASS | 摘要 §6 |
| Migration 幂等 / downgrade-upgrade / 无漂移 / `0001`–`0009` 未改 | PASS | 摘要 §5 |
| 并发同名登记至多一条成功，无 5xx | PASS | 摘要 §10 |
| 契约 `READY` 无分裂 | PASS | G-F020-10 |
| 对抗注入证明测试可失败且逐字节还原 | PASS | 摘要 §7 |

---

## Database / Migration

- 结构断言 V-1 ~ V-10：直连 `csm_f022_tester` 全通过（10 列、可空无默认、PK/FK/CHECK×2/EXCLUDE/partial unique/普通索引精确、无触发器、无 CASCADE、无显式 collation、`indexdef` 无 `COLLATE`/`lower(`）。
- 约束证伪 V-11 ~ V-20：`23505`（同名）、`23514`（vlan 越界 / bounds）、`23503`（FK）、大小写敏感、软删释放 name 与重叠、任意 `name`/`subnet_mask` 不设 DB CHECK——均通过。
- 不变式回归 R-1 ~ R-5：重叠 / 活跃范围挂已删 Cluster / F005 漂移 / 同名重复 / vlan 越界 = 0。
- 无回填：migration 无 `UPDATE`/`server_default`，V-26 佐证三列省略取 NULL。
- Migration：`upgrade head` 幂等；`downgrade 0009` / `upgrade head` 一致重建；`alembic check` 无漂移；`alembic_version.version_num` 仍 `varchar(32)`；`0001`–`0009` 逐字节未改。
- 未对生产库执行任何 Migration / 写入；所有操作限于一次性测试库。

## Backend / API

- 后端全量 `1228 passed / 0 failed`；F022 专项 `136 passed`；Tester 新增 DB 兜底回归 `2 passed`；ruff `All checks passed!`。
- 真实 HTTP 集成 `91/91 PASS`，覆盖状态码、`error.code`、`details[].code`/`field`、Empty vs Not Found、只读无副作用、无部分写入、DB 兜底路径。
- `23505` 经既有 `app/common/sqlstate.py` 单一映射 → 409 `CONFLICT`/`DUPLICATE`，**无 5xx**（SQLSTATE 键集合未新增）。
- 删除委托唯一软删路径 `app/deletion/service.py`；`ip_address_ranges` 模块零 `deleted_at` 赋值。

## Frontend

- `npm run typecheck` exit 0；`npm run build` exit 0；前端全量 **784 passed / 51 files**。
- 列表页三态互异（Loading / Empty / Error），Empty 与 Not Found 独立渲染；详情页 `not-found` 独立态。
- 三个可选字段在列表 / 详情 null → `—` 占位；登记 / 编辑对话框录入三字段，清空即提交 `null`，快照式提交 5 个可变字段。
- 提交 / 删除按 `error.code`（必要时结合 `details[].code`）分支，含 `CONFLICT + DUPLICATE`「该集群已存在同名网段」；**不解析 message**；客户端不实现 name 唯一 / 掩码 / VLAN 业务校验。

## Integration

- **真实后端 HTTP 集成（真实 uvicorn + 真实 PostgreSQL）**：`PASS 91 FAIL 0`。
- **真实前后端集成**：以真实 `frontend/src/api/**` client 直连真实 uvicorn，覆盖三字段往返、`null` 清空、`409 DUPLICATE`、`400`（mask/vlan）、`404`、`401`、Empty/Not Found：`5 passed`（连续 5 次）。
- **并发真实 HTTP**：同名登记 1×201 / 11×409 / 0×5xx。
- 未使用 Mock / Fixture 替代；前端 `/api` 前缀经真实客户端发出。

## Defects

**None。**

无 BLOCKER / HIGH / MEDIUM / LOW 的产品、架构、数据库、后端、前端缺陷。

### 观察项（非缺陷，不计入缺陷清单）

- **O-01（实现方测试覆盖，LOW，已由 Tester 补齐）**：实现方测试未覆盖「绕过应用层 `name` 预检后，partial unique `23505` → 409 `DUPLICATE`」这一契约 §4.2 明确记录的应用层兜底路径。Tester 新增 `tests/test_f022_metadata_extra.py`（`monkeypatch` 预检返回 `False` → 断言 409 + `DUPLICATE`，通过）。功能正确，仅测试覆盖缺口；Owner 建议 backend（补同款回归），**不阻塞**。
- **O-02（Tester 探针一次性抖动，无功能影响）**：前端集成探针首次运行有 1 次「刚创建的 Cluster 在紧接的 POST 中 404」；随后连续 5 次重跑 5/5 通过，直接用 httpx / curl 复现亦正常。判定为临时探针（cookie 包装 / 环境切换）的一次性抖动，**非后端竞态**（后端 201 响应在 commit 之后返回；全量 1228 测试与并发测试均无此现象），不计为缺陷。

## Unverified Areas

- 其它 Feature 未被本 Feature 触及的行为不在本次验收范围（全量测试通过已间接覆盖）。
- F021（IP 分配）不在本 Feature 范围，仅验证「分配不按掩码 / VLAN 过滤」与「F021 契约 / 代码未改」；其自身语义由既有 F021 测试负责。
- 未在生产库或未知数据库执行任何操作。

## Test Status

```text
READY FOR REVIEW
```

依据 `.pi/agents/tester.md` §20：全部 Acceptance Criteria（AC-01 ~ AC-30）有结果且为 PASS；无 BLOCKER / HIGH / 必须修复的 MEDIUM；真实前后端集成已验证（真实 uvicorn + 真实 PostgreSQL + 真实前端 client）。观察项 O-01 / O-02 不阻塞。

## Test Handoff

### Status
`READY FOR REVIEW`

### Verified
- AC-01 ~ AC-30 逐条 PASS；Architecture Test Work 全项。
- Database V-1 ~ V-26 关键项直连证伪（32/32）；不变式 R-1 ~ R-5 恒 0。
- Migration 幂等 / downgrade-upgrade 重建 / `alembic check` 无漂移 / `version_num` 仍 `varchar(32)` / `0001`–`0009` 未改 / 无回填。
- 静态 guard：唯一软删写入路径、唯一 IPv4 / 掩码解析、`SQLSTATE_MAP` 键集合不变、既有 guard 只增不弱。
- 真实 HTTP 集成 91/91；真实前后端 client 集成 5/5；并发同名 1×201 / 11×409 / 0×5xx。
- 对抗注入证明 partial unique 与 vlan CHECK 确为权威，且 indexdef / checkdef **逐字节还原**。

### Not Verified
- F021 分配语义自身的细节（范围外，未测试）。

### Blocking Issues
无。

### Defect Owner
- 无缺陷。
- O-01（测试覆盖建议）：backend（非阻塞）。
- O-02（探针抖动）：tester 探针，无 Owner 动作。

---

## 本次新增 / 使用的测试资产与命令

- `docs/test-reports/assets/f022/raw_db_probe.py` — 直连 DB 证伪（绕过应用层，V-1 ~ V-26 + R-1 ~ R-5）。
  命令：`.venv/bin/python docs/test-reports/assets/f022/raw_db_probe.py "postgresql://csm:csm@localhost:55432/csm_f022_tester"`
- `docs/test-reports/assets/f022/adversarial_probe.py` — 对抗注入（DROP partial unique / vlan CHECK → 证伪 → 逐字节还原）。
  命令：`.venv/bin/python docs/test-reports/assets/f022/adversarial_probe.py "postgresql://csm:csm@localhost:55432/csm_f022_tester"`
- `docs/test-reports/assets/f022/integration_http.py` — 真实 uvicorn + 真实 PG HTTP 契约集成。
  命令：`.venv/bin/python docs/test-reports/assets/f022/integration_http.py "http://127.0.0.1:8799" "postgresql://csm:csm@localhost:55432/csm_f022_integration"`
- `tests/test_f022_metadata_extra.py` — Tester 新增：DB 兜底路径（绕过预检 → 23505 → 409 `DUPLICATE`）回归。
- 临时前端集成探针（真实 `frontend/src/api/**` → 真实后端；`@vitest-environment node`；运行后已删除，无源码残留）。
- 环境准备：`CREATE DATABASE csm_f022_tester` / `csm_f022_integration`；`alembic upgrade head`；
  `PYTHONPATH=backend python -m app.auth.cli create-initial-admin --username tester`；
  `CSM_DATABASE_URL=...csm_f022_integration CSM_ENVIRONMENT=dev uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8799`。
- **未修改任何生产实现代码**（`backend/app/**`、`frontend/src/**`、`docs/product|architecture|api|database` 均未改动）；新增仅测试代码与测试资产。

---

GIT: NONE（本次仅执行只读 git 命令，逐条列出）：
- `git rev-parse --short HEAD`
- `git status --short`
- `git status --porcelain`
- `git status --porcelain --untracked-files=all`
- `git log --oneline -8`
- `git show --stat 65e0cce`
- `git diff --stat dae7fe9..38e8792 -- <paths>`（multiple pathspecs）
- `git diff dae7fe9..38e8792 -- <paths>`（multiple pathspecs）