# Test Report — F023 自动分配时指定 IP 地址范围段

> Status: `READY FOR REVIEW`
> Author Role: tester
> Date: 2026-09-23
> Feature: **F023 — 自动分配时指定 IP 地址范围段**（E02，P1，`depends_on: [F020, F021]`）
> Branch: `feature/F023-ip-range-selection`；HEAD: `608a695`（实现提交 `baea9ec`）
> 结论依据：Product Handoff AC-01 ~ AC-20；`requirements.md` §12 修订 **R-IP-006 / R-IP-009**；修订后 `docs/api/f021-ip-address-allocation.md`（Status `READY`）；`docs/architecture/f023-ip-range-selection-handoff.md`

---

## Feature

把 `POST /api/ip-addresses/allocate` 的自动分配从「目标 Cluster **全部活跃范围段并集**取全局最小」改为「**必须显式指定一个活跃范围段**，**仅在该所选单个范围段内**取数值最小未占用 IPv4；所选范围段耗尽 → `409 CONFLICT + NO_AVAILABLE_IP` 且**不回退**」。请求新增**必填** `ip_address_range_id`；手动分配与 F005 `POST /api/ip-addresses` 不变；**无数据库变更**。

---

## Test Basis

| 类别 | 文件 |
|---|---|
| 产品验收标准 | `docs/product/handoffs/f023-ip-range-selection.md`（AC-01 ~ AC-20，唯一来源） |
| 产品需求 | `docs/product/requirements.md` §12 R-IP-006 / R-IP-009（修订）、R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010（保持不变） |
| API 契约 | `docs/api/f021-ip-address-allocation.md`（Status **READY**，2026-09-22 F023 修订；§1 / §3.1 / §4.1 / 新增 §4.6 / §6.1 / §6.5 / §8 / §9） |
| 架构 | `docs/architecture/f023-ip-range-selection-handoff.md`（Verification Strategy §1~§11） |
| 项目计划 | `docs/project/v1/project-plan.yaml` `features[F023].layers.database = false`；`decisions_required[DEC-025]`（RESOLVED） |
| 领域 Skill | `.pi/skills/resource-domain/SKILL.md` |

---

## Environment

| 项 | 值 |
|---|---|
| 数据库 | 真实 PostgreSQL 16.15（`csm-f020-test-pg`，`localhost:55432`），`PGPASSWORD=csm` |
| 测试库 | `csm`（pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 从空库重建） |
| 集成库 | `csm_f023_integration`（本次新建；真实 uvicorn + 真实 PG） |
| 后端 | `.venv/bin/python` / `pytest`；`ruff 0`（`.venv/bin/ruff`） |
| 前端 | Node/Vitest 5.0.1 + happy-dom；`npm test` / `npm run typecheck` / `npm run build` |
| migration head | `0010_f022_ip_range_metadata`（未变） |

**是否全新**：集成库 `csm_f023_integration`、真实 uvicorn（端口 8800）、管理员账号均为本次新建；pytest 每次从空库重建。**开发 Agent 的测试结论未被采信**——下表结果均来自本次独立重跑；另新增独立探针 `tests/test_f023_tester_probe.py`（29 例）与 `frontend/tests/f023TesterProbe.spec.ts`（7 例），**未修改任何生产实现代码**。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量回归（独立重跑）

```text
$ PGPASSWORD=csm CSM_TEST_DATABASE_URL="postgresql+psycopg://csm:csm@localhost:55432/csm" \
    .venv/bin/python -m pytest -q
1239 passed, 2 warnings in 1174.41s (0:19:34)
```

> 结果为 HEAD `608a695` 上既有测试集（含 F005/F020/F021/F022 全部）。新增探针在其后加入、单独运行。

### 2. F023 专项 + Tester 独立探针 + F021 分配全量（合并重跑）

```text
$ .venv/bin/python -m pytest tests/test_f023_ip_range_selection.py tests/test_f023_tester_probe.py \
    tests/test_ip_allocations_api.py tests/test_ip_allocations_guards.py -q
108 passed, 2 warnings in 145.27s (0:02:25)
```

其中：`tests/test_f023_ip_range_selection.py` → 9 passed；`tests/test_f023_tester_probe.py` → 29 passed。

### 3. Lint

```text
$ .venv/bin/ruff check backend tests
All checks passed!
```

### 4. 前端全量 + 类型 + 构建

```text
$ cd frontend && npm test          →  Test Files 52 passed (52) / Tests 809 passed (809)
$ npm run typecheck                →  无错误（vue-tsc --noEmit）
$ npm run build                    →  ✓ built in 5.35s
```

（809 = 开发方 802 + 本次新增探针 7。）

### 5. Migration / 结构证伪（绕应用层直连 DB）

```text
$ alembic heads → 0010_f022_ip_range_metadata (head)   # 单一 head

information_schema.tables (public BASE TABLE) =
  {alembic_version, bare_metals, clusters, containers, ip_address_ranges,
   ip_addresses, network_interfaces, service_carriers, services, sessions, users, virtual_machines}
ip_addresses  非主键唯一索引 = {ux_ip_addresses_cluster_ip_active}
pg_constraint contype='x'   = {ex_ip_address_ranges_active_no_overlap}   # 仅 F020 既有，无新增
information_schema.triggers (public) = 0
alembic_version.version_num = 0010_f022_ip_range_metadata
cluster_id 漂移查询 = 0 行（每次自动分配后复验）
```

### 6. 真实前后端集成（真实 `frontend/src/api/**` 客户端 → 真实 uvicorn + 真实 PG）

临时 vitest 探针（`@vitest-environment node`，cookie 罐直连 `127.0.0.1:8800`；运行后已从 `frontend/tests/` 删除，副本归档于 `docs/test-reports/assets/f023/zzTmpF023Integration.spec.ts`）：

```text
$ F023_BASE=http://127.0.0.1:8800 npx vitest run tests/zzTmpF023Integration.spec.ts
Test Files  1 passed (1) / Tests  1 passed (1)     （连续 3 次 exit=0）
```

覆盖（全部经真实 `api/auth|clusters|bareMetals|networkInterfaces|ipAddressRanges|ipAddresses` 模块）：未认证 `allocateIpAddress` → `ApiError{401 UNAUTHENTICATED}`；登录后建链；`listIpAddressRanges({cluster_id})` 只读链；自动分配响应键集合**恰 5 字段**（无 `cluster_id` / `ip_address_range_id`）；选 high 段取 `10.0.0.10`（不取 low 更小值）；跳过已占用取下一个；手动 `010.000.000.002` → `10.0.0.2`；跨 Cluster `409 + IP_ADDRESS_RANGE_UNAVAILABLE`；不存在 / 已软删范围段 `404 + IP_ADDRESS_RANGE_UNAVAILABLE`；缺字段 `400 + field=ip_address_range_id`；耗尽 `409 + NO_AVAILABLE_IP`；F005 范围外字面 `201`。

### 7. 契约一致性 / 最小变更面（只读 git）

```text
$ git diff --name-only dd159f3..HEAD -- backend/app frontend/src
backend/app/common/errors.py
backend/app/ip_allocations/schemas.py
backend/app/ip_allocations/service.py
frontend/src/api/ipAddresses.ts
frontend/src/components/IpAddressAllocateDialog.vue
frontend/src/pages/IpAddressListPage.vue
```

- `backend/migrations`、`backend/app/models`、`backend/app/ip_addresses/**`、`backend/app/ip_address_ranges/**`（含 `router.py`）**零改动**。
- `backend/app/common/sqlstate.py` **零改动** → `SQLSTATE_MAP` 键集合仍为 `{23502, 23514, 23505, 23503, 23P01}`。
- 契约 §3.2 `allocate-manual` 段 `base..HEAD` 逐字节相同；F005 章节未改。
- 静态 guard `G-F021-2` 仅按新合法字段集合**精确演进**为 `{network_interface_id, ip_address_range_id}`（未放宽为子集 / 前缀）。

---

## Acceptance Criteria Mapping

> 结果仅取 PASS / FAIL / BLOCKED / NOT TESTED。每条均由本次独立执行（探针 / 真实集成 / 直连 DB）得出。

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 成功响应恰 F005 五字段；请求不回显扩展 | `test_t23_ac01_response_closed_fields` + 集成 | **PASS** | `set(body)=={id,network_interface_id,ip_address,created_at,updated_at}`；无 `ip_address_range_id`/`cluster_id`/`status` |
| **AC-02** 缺 / 非整数 / `null` `ip_address_range_id` → 400 `field`，无写入 | `test_t23_ac02_*`（missing/`abc`/`null`/`1.5`/`[]`/`{}`）+ 集成 | **PASS** | 均 `400 VALIDATION_ERROR`，`details[].field=="ip_address_range_id"`，`_total_ip_count==0`；实际信封 `code=="INVALID"` |
| **AC-03** 字段封闭（含 `cluster_id`），无「未指定也成功」路径 | `test_t23_ac03_*`（`cluster_id`/`status`/`mode`/`reserved_addresses`/`ip_address`） | **PASS** | 均 `400`，行数 0；缺范围段 → 400 |
| **AC-04** 已逻辑删除范围段 → 非 5xx、无写入 | `test_t23_ac04_soft_deleted_range_404` | **PASS** | `404 NOT_FOUND` + `details[0]={field:"ip_address_range_id", code:"IP_ADDRESS_RANGE_UNAVAILABLE"}`，行数 0 |
| **AC-05** 其它 Cluster 活跃范围段 → 非 5xx、无写入 | `test_t23_ac05_*` | **PASS** | `409 CONFLICT` + 同 code/field，行数 0；与 NIC 404（`details==[]`）可区分 |
| **AC-06** 不存在范围段 → 非 5xx、无写入 | `test_t23_ac06_nonexistent_range_404` | **PASS** | `404 NOT_FOUND` + 同 code/field，行数 0；**永不 5xx** |
| **AC-07** 所选段内取数值最小 | `test_t23_ac07_08_09_*` | **PASS** | 选 high(`10.0.0.10-12`) → `10.0.0.10` |
| **AC-08** 不取未选段更小值 | 同上 | **PASS** | low 段有更小 `10.0.0.1`，仍返回所选 high 段的最小值 |
| **AC-09** 跳过所选段内已占用取下一个 | 同上 | **PASS** | high 段占用 `.10` → 返回 `.11` |
| **AC-10** 所选段耗尽 → 409 `NO_AVAILABLE_IP`，不回退 | `test_t23_ac10_11_*` | **PASS** | 另一活跃段仍有可用，仍 `409 CONFLICT` + `details[0].code=="NO_AVAILABLE_IP"`、`field==null` |
| **AC-11** 无部分写入 / 不跨 Cluster | `test_t23_ac10_11_*`、`test_t23_readonly_rejection_*` | **PASS** | `_total_ip_count` 前后不变；既有行 `(id,ip_address,updated_at,deleted_at)` 完全一致 |
| **AC-12** 写入 canonical dotted-quad | `test_t23_ac12_canonical_write` + 集成 | **PASS** | `010.007.000.001` → `10.7.0.1`；再次 `GET` 得同一规范值 |
| **AC-13** 无隐式保留地址 | `test_t23_ac13_no_implicit_reserved_skip` | **PASS** | 网络地址 `10.8.0.0` 被选中（未跳过）；占后取 `.1` |
| **AC-14** 占用按字面 / 归属按数值；软删释放 | `test_t23_ac14_*` | **PASS** | 活跃 `010.9.0.1` / `10.9.0.1/16` 不阻止写入 `10.9.0.1`；同字面占用则跳过；软删后释放 |
| **AC-15** 手动分配不变 | `test_t23_ac15_manual_unchanged` + `test_ip_allocations_api.py` 全量 | **PASS** | 范围内 201；`010.011.000.006`→`10.11.0.6`；非法 400 `INVALID`；携带 `ip_address_range_id` → 400；范围外 409 `OUT_OF_RANGE` |
| **AC-16** F005 `POST /api/ip-addresses` 不变 | `test_t23_ac16_*` + 集成 | **PASS** | 范围外字面 `203.0.113.9/32` → 201；端点章节逐字未改 |
| **AC-17** 唯一性 / 并发不变（真实线程） | `test_t23_ac17_auto_manual_f005_race`、`test_t23_ac17_repeated_auto_race`（真实 uvicorn 集成亦含登录态） | **PASS** | auto/manual/F005 三方竞争同一地址：至多一条 201，其余 `409 CONFLICT + DUPLICATE`，无 5xx；同字面活跃行 ≤1；漂移 0；重复 3 轮稳定 |
| **AC-18** 前端必选范围段 / Empty 禁用 / 三态互异 / 错误分支不解析 message | `frontend/tests/f023TesterProbe.spec.ts`（7 例）+ 开发方 802 例 | **PASS** | 未选范围段提交禁用且 0 次 POST；Empty 禁用；`empty/loading/error/success` 互异；`IP_ADDRESS_RANGE_UNAVAILABLE`（404/409）/`NO_AVAILABLE_IP`/NIC 404 分支文案互异；哨兵 `message` 未渲染（不解析 message） |
| **AC-19** 契约落盘且 READY、字段必填、无分裂 | `test_t23_ac19_contract_*` + §7 最小变更面 | **PASS** | 文件头 `Status: **READY**`；`ip_address_range_id` 注明 `**是**`（必填）；旧并集表述已删除 |
| **AC-20** 无新表 / 列 / 索引 / migration | `test_t23_ac20_*` + §5 | **PASS** | 表集合不变；`ip_addresses` 列集合恰 7；非主键唯一索引恰 `{ux_ip_addresses_cluster_ip_active}`；排他约束仅 F020 既有；无触发器；head 仍 `0010`；`SQLSTATE_MAP` 不变；`layers.database=false` |

**说明**：AC-01 ~ AC-20 **全部有结果，无 FAIL、无 BLOCKED、无 NOT TESTED**。

---

## Database / Migration

- `layers.database = false` 复核**成立**：`backend/migrations/**`、`backend/app/models/**` 自 `dd159f3` **零改动**；`alembic heads` 单一 head `0010_f022_ip_range_metadata`。
- 直连 DB（绕应用层）：表集合不变；`ip_addresses` 列恰 7；`ip_address_ranges` 列恰 10；`ip_addresses` 非主键唯一索引恰 `{ux_ip_addresses_cluster_ip_active}`；排他约束恰 `{ex_ip_address_ranges_active_no_overlap}`（F020 既有）；`information_schema.triggers` = 0。
- `cluster_id` 漂移查询恒为 0 行（写入路径仍唯一经 `create_ip_address`）。
- 结论：**无新表 / 列 / 唯一索引 / 排他约束 / 触发器 / migration**，与 Database Handoff 一致。

---

## Backend / API

- 请求字段封闭：接受集合恰 `{network_interface_id, ip_address_range_id}`；任何未识别字段（含 `cluster_id`/`status`/`mode`/`ip_address`）→ 400；缺 / `null` / 非整数（`abc`、`1.5`）→ 400 + `details[].field=="ip_address_range_id"`，无写入。
- 范围段校验三态稳定且非 5xx、无写入：不存在 / 已逻辑删除 → `404 + IP_ADDRESS_RANGE_UNAVAILABLE`；活跃但跨 Cluster → `409 + 同 code`；与 NIC `404`（`details == []`）可区分。
- 单范围取最小 / 不取未选段 / 跳过占用 / 耗尽硬失败不回退：全部 PASS（见 AC-07~AC-11）。
- 既有语义：手动分配全量回归通过；F005 范围外字面 201；占用按字面、归属按数值（含 `010.x` / `x/16` 边界）；软删释放；无隐式保留地址。
- 并发（真实线程）：auto vs manual vs F005 同一地址至多一条 201，其余 `409 DUPLICATE`，无 5xx。

---

## Frontend

- `IpAddressAllocateDialog.vue` 自动模式新增**必选**「目标地址范围」下拉（NIC → BareMetal → `GET /api/ip-address-ranges?cluster_id=…` 只读链）；未选 / Empty / Loading / Error 状态下提交按基础必填禁用。
- 三态互异：`empty`（引导文案）/ `loading`（提交中拦截重复）/ `error`（按 `error.code` + `details[].code` 固定文案）/ `success`（结果区）。
- 新错误码分支（`IP_ADDRESS_RANGE_UNAVAILABLE` 404 与 409、`NO_AVAILABLE_IP`）文案互异；以哨兵 `message` 验证**不解析 message**。
- 请求体恰 `{network_interface_id, ip_address_range_id}`（集成验证）；`cluster_id` 仅用于范围段查询参数，绝不回填分配请求。

---

## Integration

**真实前后端集成已验证**（非 Mock）：以真实 `frontend/src/api/**` 客户端经 cookie 罐直连真实 uvicorn（`127.0.0.1:8800`）+ 真实 PostgreSQL，覆盖未认证 / 登录 / 只读链 / 自动与手动分配 / 耗尽 / 跨 Cluster / 不存在 / 已软删 / 缺字段 / F005 登记，`1 file / 1 test passed`（连续 3 次）。临时探针已从源码树删除并归档为资产。

---

## Defects

**None**（无 BLOCKER / HIGH / MEDIUM / LOW 级需实现方修复的缺陷）。

### 观察项（不阻塞，非 F023 引入）

- **O-01（LOW，pre-existing）**：`ip_address_range_id` 使用 Pydantic lax `int`，因此 JSON 数值字符串 `"7"`、整数值浮点 `1.0`、布尔 `true` 会被**强制转换**（`"7"`→7、`true`→1）后进入范围段查找（实测分别返回 `404 NOT_FOUND`）。这与既有 `network_interface_id`（同 schema）及平台全部 id 字段的既有行为**完全一致**，非 F023 引入，且不产生数据完整性风险。契约 AC-02 的「非整数」（`abc`、`1.5`）均正确 `400`。若后续要求对 id 字段严格拒绝字符串 / 布尔，应作为跨端点契约决策（F020 的 `vlan` 已选用 `StrictInt`），超出 F023 范围。**不作为缺陷交回**。

---

## Unverified Areas

- **浏览器全栈 E2E**：未以真实浏览器加载 Vue 应用并人工点击。集成在「真实前端 API client + 真实后端」层完成，组件行为由 `@vue/test-utils` 真实挂载覆盖；此为项目既有验证标准（F021/F022 同）。非阻塞。
- 无其它未验证项。

---

## Test Status

```text
READY FOR REVIEW
```

All Acceptance Criteria（AC-01 ~ AC-20）均有结果且为 PASS；无 BLOCKER / HIGH / 必须修复的 MEDIUM；真实前后端集成已验证；`layers.database=false` 经 §5 直连 DB 复核。

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-20 全部 PASS（请求字段封闭、范围段三态校验、单范围取最小、耗尽不回退、既有语义不变、并发、结构证伪、前端、无 DB 变更）。
- 全量后端 1239 passed；F023 专项 + 探针 + F021 分配 108 passed；前端 809 passed；typecheck / build / ruff 干净。
- migration head 仍 `0010_f022_ip_range_metadata`；无新表 / 列 / 唯一索引 / 排他约束 / 触发器；`SQLSTATE_MAP` 与 `/allocate-manual`、F005 均未改。
- 真实前后端集成 1/1（连续 3 次）。

### Not Verified

- 真实浏览器人工 E2E（见 Unverified Areas，非阻塞）。

### Blocking Issues

- None。

### Defect Owner

- None（O-01 为 pre-existing 观察项，不交回）。

### 本次新增测试资产（仅测试代码，未改生产实现）

- `tests/test_f023_tester_probe.py` — 29 例独立后端验收探针。
- `frontend/tests/f023TesterProbe.spec.ts` — 7 例独立前端验收探针。
- `docs/test-reports/assets/f023/zzTmpF023Integration.spec.ts` — 真实前后端集成探针归档（源码树内临时副本已删除）。
- 集成环境：`csm_f023_integration` 库 + 真实 uvicorn `127.0.0.1:8800`（已停止）。

---

GIT: NONE