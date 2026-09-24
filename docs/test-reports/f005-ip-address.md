# Test Report — F005 IPAddress 管理

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验收）
> Date: 2026-09-18
> Feature: F005（E02，P1，`depends_on: [F004]` = DONE）
> 分支：`feature/F005-ip-address`
> base `develop` = `881ee230851c1234c705ac7e3367938f243e31ef`
> 实现 HEAD = `6dadc73f9d0f2f9899e32a3b09efbb5ef315aed1`（其后 `512e92c` 为计划元数据检查点）
> layers：database/backend/frontend 均 true；contract READY、backend COMPLETE、frontend COMPLETE、test PENDING

---

## Feature

IPAddress 管理（F005）— CSM V1 网络资源链的末端资源：IP 地址的人工登记、查询、字面值修正、逻辑删除；**IPAddress → NetworkInterface 必选绑定**落地；**Cluster 内 IP 唯一性**的保存前阻止；**`cluster_id` 受控推导与漂移归零**；以及 **F014 父删子拦**在 `NetworkInterface` 上的端到端。

## Test Basis

- `AGENTS.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/handoffs/f005-ip-address.md`（Product Handoff `READY FOR ARCHITECT`，AC-01 ~ AC-42）
- `docs/architecture/f005-ip-address-handoff.md`（Architecture Handoff `READY FOR IMPLEMENTATION`，Test Work T-01 ~ T-42 / G-1 ~ G-17 / REQUIRED / Constraints / 决策 5~9）
- `docs/database/f005-ip-address-migration.md`（Database Handoff，V-1 ~ V-18）
- `docs/api/f005-ip-address.md`（API 契约 **READY**，单一权威）、`docs/api/api-conventions.md`
- ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005（均 `ACCEPTED`）
- 报告格式先例：`docs/test-reports/f006-virtual-machine.md`、`docs/test-reports/f004-network-interface.md`（含 Re-verification 小节）

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f005-test/pgdata`，本次新建） |
| collation | `zh_CN.UTF-8` / `zh_CN.UTF-8`；实测 `'abc' = 'ABC'` → `false`（**大小写敏感**，满足 §22 / AC-10 前提） |
| 测试库 | `csm_f005`（pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 重建）、`csm_mig`（迁移 / 直连 schema 检查）、`csm_api`（真实 uvicorn + 原始 httpx / 前端真实 client 集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn`（真实 PG `csm_api`）：`127.0.0.1:8796` |
| Node / npm | v24.14.0 / 11.9.0（Vite，Vitest 5.0.1，happy-dom） |
| ruff / psycopg / httpx | 0.16.7 / 3.3.5 / 0.28.1 |

**是否全新**：PG 实例、三个测试库、管理员账号、集成探针均为本次测试新建；pytest 每次从空库重建。实现方结论**未被复用** — 下表所有结果均来自本次独立执行。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量测试（独立重跑，无 skip）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f005?host=/tmp/f005-test/pgdata" \
  .venv/bin/python -m pytest -q
686 passed, 2 warnings in 629.28s (0:10:29)（无 skipped）

F005 专项：
$ .venv/bin/python -m pytest -q tests/test_ip_addresses_api.py tests/test_ip_addresses_guards.py \
    tests/test_ip_addresses_concurrency.py tests/test_ip_addresses_consistency.py \
    tests/database/test_ip_addresses_constraints.py tests/database/test_ip_addresses_schema_guard.py
133 passed, 2 warnings in 120.29s
```

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 133 files already formatted  exit 0
```

### 3. 迁移（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head   → 0001 → 0002 → 0003 → 0004_f006 → 0005_f004 → 0006_f005_ip_addresses
$ alembic current        → 0006_f005_ip_addresses (head)
$ alembic upgrade head   → no-op（无 DDL）
$ alembic check          → No new upgrade operations detected.（无漂移）
$ alembic downgrade 0005_f004_network_interfaces → 成功
    → to_regclass('public.ip_addresses') = None（表被删）
    → 既有表 {clusters, users, sessions, bare_metals, virtual_machines, network_interfaces} 完好
$ alembic upgrade head   → 重建成功，current 回到 0006（head）
$ git diff 881ee23..6dadc73 -- backend/migrations/versions/0001..0005 → 空（基线未改）
```

### 4. 独立 Schema 直连检查（真实 PG 16.2，`csm_mig`）

```text
列（恰 7）：id bigint NN(identity) / network_interface_id bigint NN / cluster_id bigint NN /
  ip_address text NN / created_at,updated_at timestamptz NN DEFAULT now() / deleted_at timestamptz NULL
PK：pk_ip_addresses
FK：fk_ip_addresses_network_interface(r/r)、fk_ip_addresses_cluster(r/r)
CHECK：[]（空）
索引：ux_ip_addresses_cluster_ip_active UNIQUE(cluster_id, ip_address) WHERE (deleted_at IS NULL)
      + ix_ip_addresses_cluster_id + ix_ip_addresses_network_interface_id
列级 collation：[]；非内部触发器：[]；全库 confdeltype='c' 外键：[]
```

与 Database Handoff V-1 ~ V-10 逐项一致。

### 5. 直连约束行为（绕过应用层，`csm_mig`）

```text
同 Cluster 重复活跃字面值 → SQLSTATE 23505；跨 Cluster 相同字面值 → 成功
空串 / 首尾空白 / not-an-ip / 超长(5000) / 2001:DB8::1 / 2001:db8::1 → 均成功（无格式约束）
cluster_id 与链路不一致的行可直插（DB 不保证），漂移查询能查出
软删后同 Cluster 可再次插入相同活跃字面值
'abc' = 'ABC' → false（大小写敏感）
```

即 V-11 ~ V-14 真实可执行。

### 6. 真实后端 HTTP 集成（真实 uvicorn + 真实 PG，原始 httpx）

```text
$ .venv/bin/python /tmp/f005-test/integration.py → RESULT: PASS 72 FAIL 0
覆盖：未认证 5 端点 401 UNAUTHENTICATED / 登录 / Empty(全局) 200+[]+total0 /
  AC-01 201 字段集合恰 5（无 deleted_at/status/cluster_id/vrf/备注）/
  AC-07 请求携带 cluster_id → 400 /
  AC-02 缺 ip_address → 400 field=ip_address / AC-03 缺 network_interface_id → 400 /
  AC-04 父不存在 → 404 无写入非 5xx / AC-06 同 NIC 两个 IP 均 201 /
  AC-08 同 Cluster 跨 NIC 重复 → 409 + DUPLICATE / AC-09 跨 Cluster 均 201 /
  AC-10 IPv6 十六进制大小写不同可共存 /
  AC-12 空串 / 首尾空白 / not-an-ip / 超长 均 201 且原样往返 /
  AC-16 列表 200 / AC-18 按 NIC 过滤：存在非空 200、缺失 404、存在但空 200+[]、非整数 400 /
  AC-17 详情 404 / AC-20 PATCH 200 新值且 network_interface_id 不变 /
  AC-21 PATCH 重复 → 409 DUPLICATE / AC-22 PATCH 封闭字段/空 body/null → 400 /
  AC-23 DELETE 204 空体 / 删除后 404 / 重复删除 404 / AC-24 软删后同 Cluster 可重登记 201 /
  AC-27 NIC 有活跃 IP → 409 ACTIVE_CHILDREN_EXIST 且 NIC 仍活跃 /
  AC-29 BareMetal 有活跃 IP → 409（链条闭合）/
  AC-26 OpenAPI 恰 2 个 IP path、GET 参数恰 {page,page_size,network_interface_id}、无 by-name /
  AC-13/42 OpenAPI IpAddressRead 恰 5 字段且无 cluster_id/status/deleted_at/vrf /
  AC-16 分页 page=0 / page_size=201 → 400
```

真实 DB 侧复算：`DRIFT_QUERY` **0 行**、孤立记录不变式 **0 行**、全部行 `cluster_id == 宿主 BareMetal.cluster_id`（0 行漂移）、已删行仍物理存在。

### 7. 真实前后端集成（**前端真实 API client** + 真实 uvicorn + 真实 PG；临时 vitest 探针，运行后已删除）

使用 `frontend/src/api/{auth,clusters,bareMetals,networkInterfaces,ipAddresses,http}.ts` 真实 client，经 node 环境重写 fetch 的 Cookie 罐直连 `127.0.0.1:8796`：

```text
$ npx vitest run tests/zzTmpF005Integration.spec.ts → Test Files 1 passed | Tests 1 passed
- 未认证 listIpAddresses() → ApiError{401, UNAUTHENTICATED}
- login → createCluster / BareMetal / NetworkInterface → createIpAddress 201 字段键恰 5（无 cluster_id）
- ip_address='  not-an-ip  ' 原样提交 / 原样返回（不进前端格式校验）
- 同 Cluster 重复 → ApiError{409, CONFLICT, details 含 DUPLICATE}
- 跨 Cluster 同字面值 → 不同 id（201）
- 按 NIC 过滤：空 NIC → 200 + items==[]；缺失 NIC → 404（Empty 与 Not Found 区分）
- PATCH → 200 新值，network_interface_id 不变；getIpAddress → 200
- deleteIpAddress → resolve undefined(204)；删除后详情 404；重复删除 404
- NIC 有活跃 IP → 真 DELETE → 409 + ACTIVE_CHILDREN_EXIST
```

探针文件 `frontend/tests/zzTmpF005Integration.spec.ts` 运行后已删除；`git status --short` 为空。

### 8. 对抗注入（证明 guard / 漂移三件套真实可失败，逐字节还原）

**漂移三件套与 `cluster_id` 受控推导（最高优先）**

| 注入 | 目标 | 结果 |
|---|---|---|
| 临时移除 `ux_ip_addresses_cluster_ip_active` 的 `WHERE deleted_at IS NULL`（模型 + migration） | ORM G-4 / DB V-7 / 行为 T-24 | **FAILED ×3** |
| 临时让 `derive_cluster_id` 返回 `cluster_id + 1` | T-33（推导正确）/ T-34（产品路径漂移 0 行）/ T-36 | **FAILED ×3**（T-35 独立 raw 反例仍通过，符合预期） |
| 临时新增第二条写 `cluster_id` 路径（service 内 `setattr(ip, "cluster_id", …)`） | G-9 断言 1（写路径唯一） | **FAILED** |
| 临时新增第二个 `derive_cluster_id` 调用点 | G-9 断言 3（调用点唯一） | **FAILED** |
| 临时把 `DRIFT_QUERY` 弱化为恒不命中（`AND ip.id < 0`） | T-35 / T-36 | **FAILED ×2**（证明二者非 vacuous） |
| 临时给 `IpAddressCreate` 加 `str_strip_whitespace=True` | G-10（无格式 / 归一化） | **FAILED** |

**独立 raw psycopg 反例（不使用测试夹具）**

```text
baseline drift: []
after raw bypass INSERT (stored cluster_id=B, derived=A): [(1, 2, 1)]   ← DRIFT_QUERY 真实查出
# 逐字采用 AC-34 SQL：WHERE ip.cluster_id <> bm.cluster_id
```

**guard 演进与新增 allowlist**

| 注入路由（`backend/app/main.py`，非资源模块） | F009 G-009-2（`ip-address` token 已移除） | F002 T-29（`ip` token 已移除） | NIC G-7 | 新增 allowlist |
|---|---|---|---|---|
| `POST /api/vpns` | pass（不覆盖） | pass（不覆盖） | pass | **FAILED（检出）** |
| `POST /api/ip-pools` | pass（不覆盖） | pass（不覆盖） | pass | **FAILED（检出）** |
| `POST /api/nics` | pass | **FAILED（全局检出）** | pass | **FAILED** |
| `POST /api/containers` | **FAILED（全局检出）** | **FAILED（全局检出）** | pass | **FAILED** |

**其它 guard**

| 注入 | 目标 | 结果 |
|---|---|---|
| `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS = ()` | NIC G-9 / F005 G-8 | **FAILED ×2** |
| 从 NIC 删除路径删除 `active_children=…` 实参 | NIC G-9（AST 真实消费） | **FAILED** |
| `BOUNDARY_TOKENS` 加回 `ip-address` | F009 G-7 / F005 G-7 | **FAILED ×2** |

还原校验：所有被改文件 `git status --short` 为空，注入前备份 `sha256sum -c` 逐字节一致。

### 9. 前端

```text
$ cd frontend && npm run typecheck → exit 0
$ npm run test → Test Files 28 passed (28)，Tests 380 passed (380)（连续两次均全绿）
$ npm run build → vue-tsc 通过 + vite build 成功
                  dist/assets/index-BRREY-vs.js 1,079.78 kB（仅 chunk 体积告警）
```

---

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 登记 201、字段集合恰 5、无 cluster_id/deleted_at/status | T-01 + 真实 HTTP + 前端 client | **PASS** | `set(body)==READ_FIELDS`；`cluster_id` 缺席 |
| **AC-02** `ip_address` 必填 / 非字符串 → 400 field=ip_address 无写入 | T-02 | **PASS** | `{}/123/null/dict/list` → 400 + `field=="ip_address"`，行数 0 |
| **AC-03** 父 NIC 必填 / 非整数 → 400 + field | T-03 | **PASS** | 缺失/`"abc"`/`null` → 400 + `field=="network_interface_id"` |
| **AC-04** 父不存在 / 已删 → 阻止写入、非 5xx | T-04 | **PASS** | `404 NOT_FOUND`，无写入 |
| **AC-05** 恰好一个 NIC；多父 / 选择器 → 400；列 NOT NULL + FK RESTRICT | T-05 + schema | **PASS** | 多父/载体/选择器 → 400；`fk…` `r/r`、`NOT NULL` |
| **AC-06** 一个 NIC 多个 IP | T-06 | **PASS** | 同 NIC 两个不同字面值均 201 |
| **AC-07** 请求携带 `cluster_id`/VRF 选择字段 → 400 | T-07 + T-33 + 真实 HTTP | **PASS** | `cluster_id` → 400，行数不变 |
| **AC-08** 同 Cluster 内跨 BM / 跨 NIC 重复 → 409 DUPLICATE 无第二条活跃 | T-08 | **PASS** | 409 + `field=ip_address`+`code=DUPLICATE`；活跃数 1 |
| **AC-09** 跨 Cluster 可重复 | T-09 | **PASS** | A / B 各自 `10.0.0.10` 均 201 |
| **AC-10** 字面精确；IPv6 大小写可共存；无 lower() / COLLATE | T-10 + 直连 | **PASS** | `2001:DB8::1` 与 `2001:db8::1` 均 201；indexdef 无 `lower(`/`COLLATE` |
| **AC-11** DB 最终权威；23505 → 409 永不 500；predicate 一致 | T-11 + V-11 | **PASS** | 绕预检 → 409 CONFLICT + DUPLICATE；直插 → 23505；predicate `deleted_at IS NULL` |
| **AC-12** 格式规则不实现，按字面往返 | T-12 + V-12 | **PASS** | 空串/空白/not-an-ip/超长 均 201 且原样往返；DB 无 CHECK |
| **AC-13** 无状态 | T-13 + G-1 | **PASS** | schema / 列 / OpenAPI 参数 / 端点无 status |
| **AC-14** 无 VRF / 命名空间 | T-14 + G-11 | **PASS** | 无 vrf/tenant/namespace 列、字段、参数、端点 |
| **AC-15** 无未确认字段 / 无 DHCP/DNS/自动发现 | T-14/T-15 + G-11 | **PASS** | 无 purpose/note/owner/pool/dhcp/dns外 场或端点 |
| **AC-16** 列表、分页、Empty | T-16 | **PASS** | `{items:[],total:0,page:1,page_size:50}` 非 404；非法分页 400 |
| **AC-17** 详情 Not Found（不区分）；重复删除 404 | T-17 | **PASS** | 不存在与已删均 404；重复删除 404 |
| **AC-18** 按 NIC 限定读取 Empty vs Not Found | T-18 + 真实 HTTP | **PASS** | 缺失/已删 404；存在但空 200+[]；非整数 400；仅返回该 NIC |
| **AC-19** 列表 / 详情排除已删 | T-19 | **PASS** | 绕应用层预置已删行不在 items/total；按 id 404 |
| **AC-20** `ip_address` 可修正；不可变字段不变 | T-20 | **PASS** | PATCH 200 新值；`network_interface_id`/`created_at` 不变；无 cluster_id |
| **AC-21** 修正后重校验唯一性 | T-21 | **PASS** | 目标 Cluster 已占用 → 409 无部分写入；另一 Cluster → 200 |
| **AC-22** 更新 schema 封闭；父绑定不可变 | T-22 | **PASS** | `id/deleted_at/network_interface_id/cluster_id/created_at/status/vrf` → 400；空 body / null → 400 |
| **AC-23** IP 逻辑删除 204、行保留 | T-23 | **PASS** | 204 空体；行物理存在且 `deleted_at` 非空 |
| **AC-24** 软删释放唯一性、旧行不改写 | T-24 | **PASS** | 软删后同 Cluster 重登记 201；旧行 `deleted_at` 不变 |
| **AC-25** 删除不级联 | T-25 + 真实 HTTP | **PASS** | NIC / BareMetal / Cluster 逐字段不变 |
| **AC-26** 无 restore/批量/include_deleted | T-26 | **PASS** | OpenAPI 无相关路由 / 参数 |
| **AC-27** NIC 有活跃 IP → 409 ACTIVE_CHILDREN_EXIST 无部分写入 | T-27 + 真实 HTTP | **PASS** | 409 + code；NIC `deleted_at` 仍 NULL |
| **AC-28** 软删全部活跃 IP 后 NIC 可删 | T-28 | **PASS** | 逐个软删后 NIC DELETE 204 |
| **AC-29** 链条闭合 Cluster→BM→NIC→IP | T-29 | **PASS** | BM / Cluster DELETE → 409；逐层软删后逐层释放 |
| **AC-30** NIC 检查点非空且被真实消费 | T-30 + G-8 + 注入 | **PASS** | 元组含 `has_active_ip_addresses`；AST 确认删除路径传入；空元组 / 删实参注入 → guard FAILED |
| **AC-31** 并发孤立记录不变式 = 0 | T-31（两种交错） | **PASS** | 真实 PG 行锁；不变式 0 行且漂移 0 行 |
| **AC-32** 创建对父 NIC 行取共享锁并确认活跃 | T-32 | **PASS** | `FOR UPDATE NOWAIT` 验证持锁；父删先提交 → 创建 404；未引入反向持锁 |
| **AC-33** 推导正确（非请求提供） | T-33 | **PASS** | 直读 DB `cluster_id == 宿主 BareMetal.cluster_id`；携带 cluster_id → 400 |
| **AC-34** 漂移检测回归 = 0 行 | T-34 | **PASS** | 全产品路径 0 行；软删 IP / NIC、跨 Cluster 重复后仍 0 行；推导错误注入 → FAILED |
| **AC-35** 反例证明检测有效 | T-35 + 独立 raw 反例 | **PASS** | 绕领域服务直插 → DRIFT_QUERY 返回 1 行；弱化查询 → FAILED |
| **AC-36** 漂移即唯一性静默漏洞 | T-36 | **PASS** | 真实属于 A 但存 B 的 `10.0.0.10` 不被唯一索引阻止（A 内 active 计数 2）→ 漂移查询发现 |
| **AC-37** `cluster_id` 写入路径唯一 | T-37 + G-9 + 注入 | **PASS** | PATCH 前后 cluster_id 逐字节不变；第二写路径 / 第二调用点注入 → guard FAILED |
| **AC-38** 不越界 F009/F010/F011 | T-38 | **PASS** | IP path 恰 2；无 cluster/aggregate/count/excel/import |
| **AC-39** 无格式 / 无自动发现的结构性 guard | G-10 + T-12 | **PASS** | 源码无格式符号；schema 无约束 / validator；行为原样往返；注入 → FAILED |
| **AC-40** 认证边界 | T-40 + 真实 HTTP | **PASS** | 5 端点未认证 401 且不改数据；已认证可增改删（无角色要求） |
| **AC-41** 前端三态 / Empty vs Not Found / error.code / 不重复守卫 | T-FE + 前端测试 + 真实 client | **PASS** | `loading/empty/error/content` 互异；详情独立 not-found；按 code 分支；空串 / 重复字面值仍提交由后端裁决 |
| **AC-42** 不得预留未确认能力 | T-42 + G-11/G-15 | **PASS** | schema / 契约 / 前端无 VRF / 状态 / IP 池 / 多态父 / cluster_id 可写 / 归一化预留 |

**说明**：AC-01 ~ AC-42 全部有结果，**无 FAIL、无 BLOCKED、无 NOT TESTED**。

## Test Work（T-01 ~ T-42 / G-1 ~ G-17）覆盖

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | 5 字段封闭；无 deleted_at/status/cluster_id |
| T-02 | PASS | ip_address 缺失/非串 → 400 field，无写入 |
| T-03 | PASS | network_interface_id 缺失/非整数 400 field |
| T-04 | PASS | 父不存在/已删 404 无写入非 5xx |
| T-05 | PASS | schema 封闭；NOT NULL + FK RESTRICT |
| T-06 | PASS | 同 NIC 多 IP |
| T-07 | PASS | cluster_id / vrf / status / pool 等 → 400 |
| T-08 | PASS | 跨 BM / NIC 同 Cluster 重复 409 DUPLICATE |
| T-09 | PASS | 跨 Cluster 相同字面值均 201 |
| T-10 | PASS | IPv6 大小写共存；无 lower()/collation |
| T-11 | PASS | 绕预检 → 409；直插 → 23505；predicate 精确 |
| T-12 | PASS | 空串/空白/not-an-ip/超长 原样往返 |
| T-13 | PASS | 无 status |
| T-14/T-15 | PASS | 无 VRF / 未确认字段 / 自动发现 |
| T-16 | PASS | Empty 200；分页；非法参数 400 |
| T-17 | PASS | 详情 404；重复删除 404 |
| T-18 | PASS | 按 NIC Empty vs NotFound；非整数 400 |
| T-19 | PASS | 绕应用层预置已删行排除 |
| T-20 | PASS | PATCH 200；不可变字段不变；无 cluster_id |
| T-21 | PASS | 修正后重校验；无部分写入 |
| T-22 | PASS | 未知/不可变字段 400；空 body / null 400 |
| T-23 | PASS | 204 空体；行保留 |
| T-24 | PASS | 软删释放唯一性；旧行不改写 |
| T-25 | PASS | 不级联（NIC/BM/Cluster 不变） |
| T-26 | PASS | 无 restore/批量/include_deleted/by-name |
| T-27/T-28 | PASS | 409 ACTIVE_CHILDREN_EXIST 无部分写入；软删后可删 |
| T-29 | PASS | 链条闭合；逐层释放 |
| T-30 | PASS | 检查点非空 + AST 消费（注入可失败） |
| T-31 | PASS | 两种交错不变式 0 行 + 漂移 0 行 |
| T-32 | PASS | FOR SHARE 持锁；父删先提交 → 拒绝 |
| T-33 | PASS | 推导正确（非请求值） |
| T-34 | PASS | 漂移回归 0 行（推导错误注入 → FAILED） |
| T-35 | PASS | 反例证明（弱化查询 → FAILED） |
| T-36 | PASS | 唯一性静默漏洞证明 |
| T-37 | PASS | PATCH 前后 cluster_id 逐字节不变；G-9 注入可失败 |
| T-38 | PASS | 不越界 F009/F010/F011 |
| T-39 | PASS | 无格式 / 无自动发现 guard（注入可失败） |
| T-40 | PASS | 未认证 401 不改数据；已认证无需角色 |
| T-41 | PASS | 前端三态 / Empty vs NotFound / error.code / 不重复守卫 |
| T-42 | PASS | 无预留字段 / 参数 / 分支 |
| G-1 ~ G-17 | PASS | 列 / CHECK / FK / 索引 / 表集合 / 路由 / 唯一软删写入路径 / 前端封闭，均有注入反证（G-9、漂移三件套见摘要 8） |

---

## Database / Migration

- database 层 `true` 独立确认：新增 `0006_f005_ip_addresses`；`0001` ~ `0005` **diff 为空**、未被改。
- 真实库 `csm_mig`：`upgrade head` ×2（第二次 no-op）、`current = 0006_f005_ip_addresses (head)`、`alembic check` 无漂移、`downgrade 0005` 后 `ip_addresses` 被删且既有 6 表完好、`upgrade head` 重建成功。
- 直连 `information_schema` / `pg_constraint` / `pg_indexes` 与 Database Handoff V-1 ~ V-10 逐项一致（7 列、0 CHECK、2 FK `RESTRICT`/`RESTRICT`、partial unique predicate `WHERE (deleted_at IS NULL)`、无 COLLATE / 触发器 / CASCADE、另两索引存在）。
- 约束行为绕应用层验证（V-11 ~ V-14）：同 Cluster 重复 → `23505`；跨 Cluster 成功；空串 / 空白 / not-an-ip / 超长原样接受；漂移行可直插且被漂移查询发现；软删释放唯一性。

## Backend / API

- 5 端点行为经真实 uvicorn + 真实 PG 全量复核（72/72）：契约字段集合封闭、必填/未识别字段 400、父存在性/活跃性 404、同 Cluster 唯一 409 + 稳定 `DUPLICATE`、跨 Cluster 允许、Empty vs Not Found、按 NIC 过滤、PATCH 封闭与重校验、DELETE 204 行保留、无越界路由/参数、无 status / cluster_id / VRF。
- 创建侧 `derive_cluster_id` 对父 NIC 行 `SELECT … FOR SHARE` 且同语句确认 NIC 与宿主 BareMetal 活跃；并发 T-31 / T-32 以真实 PostgreSQL 行锁验证两种交错与阻塞，孤立不变式 0 行、漂移 0 行。
- F014 接线：`app/network_interfaces/deletion.NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS = (has_active_ip_addresses,)`，被 `delete_network_interface` 经 AST 确认真实消费；NIC 有活跃 IP → 409 无部分写入；软删全部 IP 后 NIC 可删。
- 删除委托系统内唯一软删路径 `app/deletion/service.soft_delete()`；`app/ip_addresses/**` 写 `deleted_at` 的位置为 0（G-14）。
- `cluster_id` 单一写入路径：`derive_cluster_id`（唯一读链路）+ `IpAddressRepository.create`（唯一写）+ 唯一调用点 `create_ip_address`；PATCH 不触碰 `cluster_id` / `network_interface_id`。
- **未发现任何 AC 层面的后端功能违约**。

## Frontend

- `typecheck` 0；`test` 380 passed（28 文件，连续两次全绿）；`build` 成功。
- 列表页 `IpAddressListPage`：`loading / empty / error / content` 四态互不相同；Empty（200 + `items==[]`）与 Not Found（父 NIC 404 → Error 态）可区分；删除二次确认 + 提交中 Loading 防重复；登记入口；无状态列 / 无 Cluster 列。
- 详情页 `IpAddressDetailPage`：独立 `not-found` 态；展示全部 5 字段；编辑仅 `ip_address`，`network_interface_id` 只读；删除入口。
- 表单 `IpAddressFormDialog`：create = NIC 选择 + `ip_address` 文本；edit = 仅 `ip_address`；`ip_address` **无长度 / 空白 / 空串 / 格式 / 正则校验，无归一化**；`submitDisabled` 仅要求 create 模式已选 NIC；失败按 `error.code`（结合 `details[].code`）渲染固定文案，不解析 message。
- 未重复实现业务守卫：空串、首尾空白、重复字面值均直接提交由后端裁决（组件测试断言「仍提交」）。
- 真实 API client 对接真实后端通过（见摘要 7）。
- 未发现 FRONTEND 缺陷。

## Integration

**真实前后端集成 = PASS（实际执行，非 Mock / Fixture）**：

1. 真实 uvicorn（真实 PG `csm_api`）+ 原始 httpx：72 项断言全部通过；DB 侧漂移 0 行、孤立不变式 0 行。
2. **前端真实 API client** + 真实 Cookie：未认证 401 → 登录 → 201 → 409 DUPLICATE → 跨 Cluster 201 → Empty vs 404 → PATCH → DELETE 204 → 404 → NIC 409 ACTIVE_CHILDREN_EXIST，临时探针 1/1 通过，运行后删除。

---

## Defects

### F005-T-01 — `delete_network_interface` docstring 仍称 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 为「显式空元组」（LOW，非阻塞）

- **ID**：F005-T-01
- **Severity**：LOW
- **Layer**：Backend（注释 / 文档漂移）
- **Location**：`backend/app/network_interfaces/service.py::delete_network_interface` docstring（L104-105）：「`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`，当前显式空元组）并**显式传入**，不假定「无子资源」（F005 追加位置）。」
- **复现步骤**：阅读该 docstring，并读取 `backend/app/network_interfaces/deletion.py`（现为 `(has_active_ip_addresses,)`）。
- **期望**：注释与实现一致（F005 起非空且含活跃 IPAddress 检查）。
- **实际**：注释仍写「当前显式空元组」「F005 追加位置」，与已落地的非空元组矛盾。
- **影响**：仅文档漂移，无功能影响（与 F006-T-03 同类）。F005 已正确更新 `deletion.py` 自身 docstring，但未同步该消费方 docstring。
- **Owner**：backend

### F005-T-02 — `docs/database/f012-baseline-migration.md` F005 小节标题 revision 号笔误 `0005_f005_ip_addresses`（LOW，非阻塞，**预存在**）

- **ID**：F005-T-02
- **Severity**：LOW
- **Layer**：Database / 文档
- **Location**：`docs/database/f012-baseline-migration.md` L182 标题 `### `0005_f005_ip_addresses`（F005）`；同文件 L57 revision 链与 L692 revision 表均写 `0006_f005_ip_addresses`。
- **复现步骤**：`grep -n "0005_f005\|0006_f005" docs/database/f012-baseline-migration.md`。
- **期望**：小节标题 revision 号与实际 `0006_f005_ip_addresses` 一致。
- **实际**：标题写 `0005`（该笔误由提交 `f3dbc6c`「docs(database): add V1 schema design and F012 baseline migration spec」引入，**早于 F005 且不在 F005 diff 内**）。
- **影响**：纯文档，无功能影响；F005 未改动该文件（其 revision 链已在 base 含 0006）。
- **Owner**：database / 协调器

**除上述 2 项 LOW / 文档漂移外，未发现 BLOCKER / HIGH / MEDIUM，未发现 PRODUCT / ARCHITECTURE / DATABASE（实现）/ BACKEND / FRONTEND 功能缺陷；未发现任何 AC 功能性违约。**

### 独立判定：guard 演进与漂移三件套（不构成缺陷）

1. **漂移三件套（T-34 / T-35 / T-36）真实有效、未降级**：`DRIFT_QUERY` 逐字采用 AC-34 SQL（不加 `deleted_at` 过滤）；T-35 / T-36 以**真实 raw psycopg**（`conn.execute("INSERT …")`）绕过应用层写反例，无 mock。独立注入证明：推导错误 → T-33/T-34 FAILED；弱化 `DRIFT_QUERY` → T-35/T-36 FAILED；移除唯一索引 predicate → G-4 / V-7 / T-24 FAILED。独立 raw 复算确认 `DRIFT_QUERY` 能查出漂移行。
2. **`cluster_id` 受控推导**：请求携带 `cluster_id` → 400；响应无 `cluster_id`；`PATCH` 前后 `cluster_id` / `network_interface_id` 逐字节不变；G-9 四条断言（写路径唯一 / 链路读取唯一 / 调用点唯一 / schema-router-前端无 `cluster_id`）经**注入第二写路径与第二调用点**证明真实可失败。
3. **guard 演进而非收窄**：F009 `BOUNDARY_TOKENS`、F002 `test_t29`、F004 NIC G-7/G-9、F006 G-11、NIC `test_t30` 的改动**仅移除已合法化的 token / 更新 head 字符串 / 将空元组断言加强为非空断言**，全局扫描范围（全部 OpenAPI path / 全部 `/api/*`）**保持**（以 `POST /api/nics`、`POST /api/containers` 跨模块注入反证：分别被 F002 T-29、F009 G-009-2 检出）。逐行核对 `git diff` 未发现任何**断言被净删除**（见「Test Handoff / Verified」）。
4. **新增 allowlist `test_product_api_surface_is_closed` 真可失败且补足覆盖**：注入 `POST /api/vpns` / `POST /api/ip-pools`（denylist 已不覆盖）→ 该 guard FAILED；注入 `POST /api/nics` / `POST /api/containers` → 该 guard FAILED。即 allowlist 恰好补足了「移除 `ip` / `ip-address` token」后 denylist 失去的非 GET 越界路由覆盖。

---

## Unverified Areas

1. **浏览器级前端 E2E / 视觉 / 真实 DOM**：无浏览器自动化环境；前端行为经 vitest（happy-dom）组件测试与真实 API client 集成验证，未在真实浏览器观察渲染 / 网络 / 视觉。
2. **多 uvicorn worker / 跨进程并发压测**：并发端到端以独立连接 / 线程验证行锁协议，未做多 worker 压测（无产品需求，V1 单机内网）。
3. **静态 guard 对动态 SQL / 动态路由构造的穷举覆盖**：承 F014 已知残余风险；本次所有 guard 均以静态 / DB / 路由注入证明可失败，但对运行期动态构造无覆盖。
4. **嵌套在已批准前缀下的未批准子路由**（如 `POST /api/ip-addresses/pools`）：新增 allowlist 以「首段」判定，不覆盖此类嵌套路径；denylist 移除 `ip-address` token 后亦不再覆盖。当前无此路由，未发现功能性影响（仅记录残余边界）。
5. **计划元数据一致性**：`docs/project/v1/project-plan.yaml > F005.git.head_commit` 仍为 base `881ee23`（未随实现前进更新）。属协调器元数据，不影响本次验收判定，仅记录。

## Test Status

`READY FOR REVIEW`

依据：AC-01 ~ AC-42 全部有结果并全部 PASS（无 FAIL / BLOCKED / NOT TESTED）；Architecture Test Work T-01 ~ T-42 / G-1 ~ G-17 全部通过；真实前后端集成已实际执行（真实 uvicorn + 真实 PG + 原始 httpx 72/72，前端真实 client 1/1）；数据库结构 / Migration / 约束与 Database Handoff V-1 ~ V-18 一致，`0001`~`0005` 基线未改；后端全量 **686 passed**（无 skipped）、ruff / format 全绿、前端 `typecheck + 380 passed + build` 全绿；漂移三件套与 `cluster_id` 受控推导、guard 演进 / 新增 allowlist 均经对抗注入证明真实可失败并逐字节还原。仅余 2 项 **LOW 文档漂移**（F005-T-01 消费方注释、F005-T-02 预存在文档 revision 笔误），**无 BLOCKER / HIGH / 必须修复的 MEDIUM**，不阻塞 Review。

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-42 全部 PASS；无 FAIL / BLOCKED / NOT TESTED。
- Architecture Test Work T-01 ~ T-42 / G-1 ~ G-17 全部 PASS。
- 数据库：`ip_addresses` 恰 7 列 / 0 CHECK / 2 FK `RESTRICT` / partial unique `(cluster_id, ip_address) WHERE deleted_at IS NULL` / 无 COLLATE / 无触发器 / 无 CASCADE / 无第二唯一索引；`0001`~`0005` 基线未改；migration 可应用 / 可重复 / 可重建 / `alembic check` 无漂移 / `downgrade 0005` 精确删除本表且既有表完好。
- 后端：5 端点契约行为（真实 HTTP 72/72）、同 Cluster 唯一 409 + `DUPLICATE`、跨 Cluster 允许、IPv6 大小写共存、Empty vs Not Found、PATCH 封闭与重校验、DELETE 204 行保留、无越界 / 无 status / 无 cluster_id / 无 VRF / 无未确认字段；DB `23505 → 409` 永不 500。
- 推导与漂移：`cluster_id` 唯一受控写入路径；`PATCH` 不触碰；T-34 回归 0 行、T-35 / T-36 真实 raw 反例证明有效。
- 并发与 F014：创建对父 NIC 行 `FOR SHARE`；两种交错孤立不变式 0 行；NIC 有活跃 IP → 409 `ACTIVE_CHILDREN_EXIST` 无部分写入；软删后可删；链条 `Cluster→BareMetal→NIC→IP` 闭合；检查点非空且经 AST 真实消费。
- 前端：三态互异、Empty vs Not Found 可分、按 `error.code` 分支、不解析 message、不重复实现业务守卫；typecheck / test(380) / build 全绿。
- 真实前后端集成实际执行（真实 uvicorn + 真实 PG + 前端真实 client）。
- 漂移三件套、`cluster_id` 受控推导、`BOUNDARY_TOKENS` / NIC G-7/G-9 / allowlist 等共 15 项注入全部被对应 guard / 测试检出，并逐字节还原；**未发现既有断言被净删除**（逐行核对：被删行仅为 head 字符串更新、已合法 token 移除、NIC T-30 由「无 IP」反转为「NIC 无 IP 字段」、NIC G-9 由 `== ()` 加强为非空断言）。

### Not Verified

- 浏览器级 E2E / 视觉 / 真实 DOM。
- 多 worker / 跨进程并发压测。
- 静态 guard 对动态构造的穷举覆盖。
- 嵌套在已批准前缀下的未批准子路由（见 Unverified #4）。

### Blocking Issues

- None。（F005-T-01 / F005-T-02 为 LOW 文档漂移，非阻塞，建议后续一并修正。）

### Defect Owner

- F005-T-01（LOW）→ backend
- F005-T-02（LOW，预存在）→ database / 协调器

### 新增 / 修改文件

- 本报告 `docs/test-reports/f005-ip-address.md` 为唯一产出。
- 临时集成脚本（`/tmp/f005-test/**`）、临时 vitest 探针（`frontend/tests/zzTmpF005Integration.spec.ts`）运行后已删除；对抗注入已逐字节还原，`git status --short` 为空。
- 未修改任何业务实现（`backend/app/**`、`backend/migrations/**`、`frontend/src/**`）或产品 / 架构 / 契约 / 数据库设计文档。

---

GIT: NONE
