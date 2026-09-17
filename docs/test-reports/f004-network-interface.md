# Test Report — F004 NetworkInterface 登记与管理

> Status: **RETURN TO IMPLEMENTATION**
> Author Role: tester（独立验收）
> Date: 2026-09-17
> Feature: F004（E02，P1，`depends_on: [F002]` = DONE）
> 分支：`feature/F004-network-interface`
> base `develop` = `cf03e014a9abbd0dad88a00da57947e731778513`
> 实现 HEAD = `6ec3b9ea388c89e74a270fb416bf1bddb8652646`（其后 `e22e234` 为计划元数据检查点）
> layers：database/backend/frontend 均 true；contract READY、backend COMPLETE、frontend COMPLETE、test PENDING

---

## Feature

NetworkInterface 管理（F004）— CSM V1 网络资源的第一个资源：网络接口的**人工登记、查询、用途与技术类型维护、逻辑删除**，以及 **NetworkInterface → BareMetal 必选绑定** 的真实落地与 F014 父删子拦端到端。

## Test Basis

- `AGENTS.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/handoffs/f004-network-interface.md`（Product Handoff，`READY FOR ARCHITECT`，AC-01 ~ AC-34）
- `docs/architecture/f004-network-interface-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，Test Work T-01 ~ T-32 / G-1 ~ G-14 / REQUIRED / Constraints）
- `docs/database/f004-network-interface-migration.md`（Database Handoff，V-1 ~ V-15）
- `docs/api/f004-network-interface.md`（API 契约 **READY**，单一权威）、`docs/api/api-conventions.md`
- ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005（均 `ACCEPTED`）
- 报告格式先例：`docs/test-reports/f006-virtual-machine.md`（含 Re-verification 小节）

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f004-test/pgdata`，本次新建） |
| collation | `zh_CN.UTF-8`；实测 `'abc' = 'ABC'` → `false`（大小写敏感，满足 R-NIC-001/002 字面精确匹配前提） |
| 测试库 | `csm_f004`（pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 重建）、`csm_mig`（迁移 / 直连 schema 检查）、`csm_api`（真实 uvicorn + 前端真实 client 集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn`（真实 PG `csm_api`）：`127.0.0.1:8796` |
| Node / npm | v24.14.0 / 11.9.0（Vite，Vitest 5.0.1，happy-dom） |
| ruff / httpx | 0.16.7 / 0.28.1 |

**是否全新**：PG 实例、三个测试库、管理员账号、集成探针均为本次测试新建；pytest 每次从空库重建。实现方结论**未被复用** — 下表所有结果均来自本次独立执行。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量测试（独立重跑，无 skip）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f004?host=/tmp/f004-test/pgdata" \
  .venv/bin/python -m pytest -q
551 passed, 2 warnings in 507.62s (0:08:27)（无 skipped）

F004 专项（独立单独重跑）：
$ .venv/bin/python -m pytest -q tests/test_network_interfaces_api.py \
    tests/test_network_interfaces_guards.py tests/test_network_interfaces_concurrency.py \
    tests/database/test_network_interfaces_constraints.py \
    tests/database/test_network_interfaces_schema_guard.py
150 passed, 2 warnings in 153.51s
```

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 117 files already formatted  exit 0
```

### 3. 迁移（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head   → 0001 → 0002 → 0003 → 0004_f006_virtual_machines → 0005_f004_network_interfaces
$ alembic current        → 0005_f004_network_interfaces (head)
$ alembic upgrade head   → no-op（无 DDL）
$ alembic check          → No new upgrade operations detected.（无漂移）
$ alembic downgrade 0004_f006_virtual_machines → 成功（network_interfaces 删除）
$ alembic upgrade head   → 重建成功，current 回到 0005（head）
```

### 4. 独立 Schema 直连检查（真实 PG 16.2，`csm_mig`）

```text
tables: [alembic_version, bare_metals, clusters, network_interfaces, sessions, users, virtual_machines]
network_interfaces 列（恰 8）: id bigint NN(identity) / bare_metal_id bigint NN / name text NN /
  technology_type text NN / purpose text NN / created_at,updated_at timestamptz NN DEFAULT now() /
  deleted_at timestamptz NULL
约束: pk_network_interfaces / fk_network_interfaces_bare_metal(FK confdeltype='r', confupdtype='r') /
      ck_network_interfaces_technology_type(Ethernet/InfiniBand/RoCE/Other) /
      ck_network_interfaces_purpose(BMC/Management/Business/Compute/Storage/DataTransfer/Other)
索引: ix_network_interfaces_bare_metal_id（外加主键 pk_network_interfaces）；无 ux_ 前缀；无额外唯一索引
列级 collation: [] ; 非内部触发器: [] ; 全库 confdeltype='c' 外键: [] ; 列 length: 无
```

与 Database Handoff V-1 ~ V-9 逐项一致。

### 5. 直连约束行为（绕过应用层，`csm_mig`）

```text
非法 technology_type / purpose（FibreChannel / ethernet / "Other " / 空串）→ SQLSTATE 23514
technology_type=NULL → 23502；指向不存在宿主 → 23503
同宿主同名两行直插 → 成功（第 2 行 OK；同名行数 = 2）  ← 无唯一性
name 空串 / 首尾空白 / "a/b" / "网卡-0.1" → 原样接受
四个 technology_type / 七个 purpose 逐一可插入
```

### 6. 真实后端 HTTP 集成（真实 uvicorn + 真实 PG，原始 httpx）

```text
$ .venv/bin/python /tmp/f004-test/probe.py → PASS 100  FAIL 0
覆盖：5 端点未认证 401（UNAUTHENTICATED）/ 登录 / Empty(全局) 200+[]+total0 /
  AC-01 201 字段集合恰 7（无 deleted_at/status/cluster_id/mac/ip_address/vm_id）/
  AC-03 四值 201；FibreChannel·ethernet·"Other "·空串·null → 400 field=technology_type /
  AC-04 七值 201；bogus·"Compute "·空串·null → 400 field=purpose /
  AC-02 name 缺失/非串 → 400 field=name /
  AC-06 bare_metal_id 缺失/非整数 → 400 field /
  AC-07 不存在·已删宿主 → 404 且总数不变（无写入、非 5xx）/
  AC-08 vm_id/container_id/cluster_id/carrier_type/owner_type/选择器 → 400 /
  AC-05 "Other" → 201 字面值；other_text → 400 /
  AC-09 同宿主同名两次均 201 且 id 不同 /
  AC-10 中文·点号·连字符原样往返 / AC-11 空串·首尾空白·"a/b" 不被拒绝 /
  AC-13 item 无 status / AC-14 分页 + page=0/page_size=0/201 → 400 /
  AC-15/17 详情 404（不存在·已删）/ AC-16 宿主存在但空 → 200+[]；不存在 → 404；非整数 → 400 /
  AC-18 PATCH 200 新值·缺省不变 / AC-19 非法枚举 400 无写入 /
  AC-20 PATCH name/bare_metal_id/id/created_at/deleted_at/status/null/{}/→400 /
  AC-21 DELETE 204 空体 / AC-23 无 restore/undelete/批量/include_deleted /
  AC-25 宿主有活跃 NIC → 409 ACTIVE_CHILDREN_EXIST 且宿主 deleted_at 仍空 /
  AC-26 软删全部 NIC 后宿主 204 / AC-31/32 无 ip-address(s)/containers/services/by-name /
  OpenAPI：NIC 恰 2 path、4 method；GET 参数恰 {page,page_size,bare_metal_id}
```

### 7. DB CHECK 最终权威映射（独立绕过应用层预检）

在独立进程中把 `app.network_interfaces.service.validation` 两个校验替换为 no-op（仅测试进程），令非法值直达 DB：

```text
DB CHECK violation technology_type → HTTP 400 VALIDATION_ERROR（details[].code=CHECK_VIOLATION）
DB CHECK violation purpose        → HTTP 400
PASS: 23514 经通用映射返回 400（永不 500）
```

### 8. F014 端到端 + 并发（真实 PostgreSQL）

- 真实 HTTP（摘要 6）：宿主有活跃 NIC → `409` + `ACTIVE_CHILDREN_EXIST`，宿主 `deleted_at` 仍 NULL；软删全部 NIC 后宿主可删 `204`。
- `tests/test_network_interfaces_concurrency.py` 在真实 PG 上验证：建先 / 删先两种交错的行锁阻塞与结果；`SELECT count(*) … nic.deleted_at IS NULL AND bm.deleted_at IS NOT NULL` 恒为 **0 行**；创建路径对宿主行取 `FOR SHARE`（外部 `FOR UPDATE NOWAIT` 在事务持锁期间失败）；`BARE_METAL_ACTIVE_CHILD_CHECKS` 同时含 VM 与 NIC 检查。
- 本次 `csm_api` 全部操作后孤立不变式复算 = **0 行**；20 行 NIC 记录全部物理保留、`deleted_at` 非空（无物理删除）。

### 9. 对抗注入（证明 guard 真实可失败，逐字节还原）

**跨模块越界路由注入**（最重要）：临时向 `backend/app/main.py`（非任何资源模块）追加 `POST /api/containers` 与 `POST /api/ip-addresses`：

```text
FAILED tests/test_cluster_views_guards.py::test_g009_2_no_forbidden_resource_tokens_in_any_path
       AssertionError: 不得注册其它资源端点：['/api/containers', '/api/ip-addresses']
FAILED tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns
       AssertionError: F002 不得注册其它资源端点：['/api/containers', '/api/ip-addresses']
```

两条 guard 均为**全部 `/api/*` / 全部 OpenAPI path 全局扫描**（F009 `_openapi()["paths"]`；F002 `path.startswith("/api/")` + prefix），**仅移除 NIC token、未收窄扫描范围**，与 F006-T-01 的缺陷模式不同。

**G-1 ~ G-14 注入**（每条运行对应 guard 后还原）：

| 注入 | 目标 guard | 结果 |
|---|---|---|
| 模型加 `status` 列 | G-1 `test_g1_model_metadata_columns_exact` | **FAILED** |
| 模型加唯一索引 `ux_...` | G-4 `test_g4_no_unique_index_in_orm` | **FAILED** |
| 从 `BARE_METAL_ACTIVE_CHILD_CHECKS` 删除 NIC 检查 | G-8 / T-22 | **FAILED** |
| 从 NIC 删除路径删除 `active_children=NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 实参 | G-9 `test_g9_nic_delete_path_passes_active_child_checks`（AST） | **FAILED** |
| `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 改为非显式 `tuple()` | G-9b | **FAILED** |
| schema `name` 加 `min_length` | G-10 `test_g10_nic_schemas_have_no_undefined_constraints` | **FAILED** |
| 新增第二个写 `deleted_at` 文件 | G-12 allow-list | **FAILED** |
| NIC router 增 `GET /by-name/{name}` | G-14 恰 5 端点 | **FAILED** |
| `EXPECTED_TABLES` 删除 `network_interfaces` | G-5 | **FAILED** |
| `BOUNDARY_TOKENS` 加回 `network-interface` | G-7 | **FAILED** |
| `TECHNOLOGY_TYPE_VALUES` 加 `FibreChannel` | G-2 | **FAILED** |
| 模型 FK `RESTRICT`→`CASCADE` | G-11 `test_g11_no_cascade_in_orm` | **FAILED** |
| 模型删除 `ix_network_interfaces_bare_metal_id` | G-3 | **FAILED** |
| migration 加 `status` 列 | DB V-1 `test_v1_column_set_is_exactly_eight` | **FAILED** |
| migration 加唯一索引 | DB V-7 `test_v7_unique_index_set_is_empty` | **FAILED** |
| migration FK 改 `CASCADE` | DB G-11 `test_g11_no_cascade_foreign_keys_globally` | **FAILED** |
| migration 加 `name <> ''` CHECK | DB G-10 `test_g10_no_undefined_name_checks` | **FAILED** |

**19/19 注入全部被对应 guard 检出**。还原校验：`git status --short` 为空，被改文件哈希逐一比对一致。

**残留覆盖缺口（见 Defect F004-T-02）**：临时追加 `POST /api/nics`（缩写路径）后，`test_g009_2`、`test_t29`、`test_g7`、`test_structure_guard` **9 passed**（未被检出）。原因是 F004 在 `test_t29` 的 `forbidden_prefixes` 中一并移除了 `nic` token。

### 10. 前端

```text
$ cd frontend && npm run typecheck → exit 0
$ npm run build → vue-tsc 通过 + vite build 成功
                  dist/assets/index-SImFp6qX.js 1,065.05 kB（仅 chunk 体积告警）
$ npm run test → Test Files 1 failed | 23 passed (24)，Tests 1 failed | 306 passed (307)
```

**全量前端测试未真实通过**：`tests/networkInterfaceListPage.spec.ts` 存在非确定性失败（见 Defect F004-T-01）。单文件独立重跑 5 次：1、4 次通过，2、3、5 次失败；`npm run test` 连续两次均失败（失败用例在「401 UNAUTHENTICATED」与「提交中：提交按钮 Loading」之间漂移，同一根因）。详情页 `networkInterfaceDetailPage.spec.ts` 独立 3 次均 18 passed，稳定。

### 11. 真实前后端集成（**前端真实 API client** + 真实 uvicorn + 真实 PG；临时 vitest 探针，运行后已删除）

`// @vitest-environment node` 下使用 `frontend/src/api/{auth,networkInterfaces,bareMetals,clusters,http}.ts` 真实 client，经重写 fetch 的 Cookie 罐直连 `127.0.0.1:8796`：

```text
$ npx vitest run tests/zzTmpF004Integration.spec.ts → Test Files 1 passed | Tests 1 passed
- 未认证 listNetworkInterfaces() → ApiError{401, UNAUTHENTICATED}
- login → createCluster → 宿主存在但无 NIC → items==[] total==0（Empty）
- createNetworkInterface → 字段键恰 7；同宿主同名再次 201（不同 id，无 409 DUPLICATE）
- technology_type='ethernet'（大小写变体）→ ApiError{400, VALIDATION_ERROR}
- 不存在宿主列表 → ApiError{404, NOT_FOUND}（与 Empty 区分）
- updateNetworkInterface → 200 新值；getNetworkInterface → 200
- listBareMetals → 选项含本宿主 / 宿主 DELETE 409 + ACTIVE_CHILDREN_EXIST
- deleteNetworkInterface → resolve undefined(204)；删除后详情 404、列表不再包含
```

探针文件运行后已删除；`git status --short` 为空。

---

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 登记成功、字段集合恰 7 | T-01 + 真实 HTTP + 前端 client | **PASS** | `set(body)==7`；无 deleted_at/status/cluster_id/mac/ip_address/vm_id |
| **AC-02** `name` 必填 / 非字符串 → 400 field=name 无写入 | T-02 | **PASS** | `{}/123` → 400 + `details[].field=="name"` |
| **AC-03** technology_type 必填封闭、字面匹配 | T-03 + 直连 23514 | **PASS** | 四值 201；FibreChannel/ethernet/"Other "/空串/null → 400 field；DB 直插 → 23514 |
| **AC-04** purpose 必填封闭 | T-04 + 直连 23514 | **PASS** | 七值 201；非法值 → 400 field；DB 直插 → 23514 |
| **AC-05** Other 是合法成员、无伴随字段 | T-05 | **PASS** | `"Other"` → 201 读回字面值；`other_text` → 400 |
| **AC-06** 父 BareMetal 必填 | T-06 | **PASS** | 缺失/非整数 → 400 + field=bare_metal_id |
| **AC-07** 父必须有效且活跃、非 5xx | T-07 | **PASS** | 不存在 / 已删 → `404 NOT_FOUND`，无写入 |
| **AC-08** 绑定恰好一个 BareMetal | T-08 + G-1/G-3 | **PASS** | 多父/VM/Container/Cluster/选择器 → 400；`bare_metal_id NOT NULL` + FK RESTRICT |
| **AC-09** 一个 BareMetal 多张 NIC | T-09 | **PASS** | 同宿主同名两次均 201，id 不同 |
| **AC-10** 纯文本往返 | T-10 + 直连 | **PASS** | 中文 / 点号 / 连字符 / 枚举字面值原样 |
| **AC-11** 未定义 name 约束不实现 | T-11 + G-10 | **PASS** | 空串/首尾空白/"a/b" 均 201 原样；无 CHECK / schema 约束 |
| **AC-12** 名称唯一性不由本 Feature 裁定 | T-09/T-23 + G-4 | **PASS** | 无唯一索引、无预检、无 409 DUPLICATE |
| **AC-13** 无状态 | T-12 + G-1 | **PASS** | 请求/响应/表/端点/参数均无 status |
| **AC-14** 列表、分页、Empty | T-13 | **PASS** | `{items:[],total:0,page:1,page_size:50}` 非 404；分页 400 校验 |
| **AC-15** 详情 Not Found（不区分） | T-14/17 | **PASS** | 不存在与已删均 `404 NOT_FOUND` |
| **AC-16** 按宿主限定读取 Empty vs Not Found | T-15 | **PASS** | 宿主不存在/已删 404；存在但空 200+[]；只返回该宿主子集；非整数 400 |
| **AC-17** 列表/详情排除已删 | T-16 | **PASS** | 已删行不在 items/total；按 id 404 |
| **AC-18** 枚举字段可维护 | T-17 | **PASS** | PATCH 200 新值；缺省不变；再次读取一致 |
| **AC-19** 维护路径枚举校验等同创建；DB 最终权威 | T-18 + 绕过预检探针 | **PASS** | 非法枚举 400 field 无写入；DB CHECK → 400（永不 500） |
| **AC-20** 更新 schema 封闭 | T-19 | **PASS** | name/bare_metal_id/id/created_at/deleted_at/status/null/{} → 400 |
| **AC-21** NIC 逻辑删除 204、行保留 | T-20 | **PASS** | 204 空体；行仍物理存在且 `deleted_at` 非空 |
| **AC-22** 删除不级联 | T-21 | **PASS** | 宿主逐字段不变；无其它行被改/物理删除 |
| **AC-23** 无恢复/批量 | T-22 | **PASS** | OpenAPI 无 restore/undelete/purge/批量/include_deleted |
| **AC-24** 已删释放唯一性（适用性） | T-23 + G-4 | **PASS** | 同名两行各自软删成功；旧行 deleted_at 不被改写；无唯一性行为 |
| **AC-25** 宿主有活跃 NIC → 拒绝删除 | T-24 + 真实 HTTP | **PASS** | 409 + `ACTIVE_CHILDREN_EXIST`；宿主 deleted_at 仍 NULL（无部分写入） |
| **AC-26** 软删 NIC 后宿主可删 | T-25 + 真实 HTTP | **PASS** | 全部子软删后宿主 DELETE 204 |
| **AC-27** 并发孤立记录不变式 = 0 | T-26（两种交错） | **PASS** | 建先/删先；不变式查询 0 行（真实 PG 行锁） |
| **AC-28** 创建对父行取共享锁 | T-27 | **PASS** | `FOR SHARE` + 活跃确认；`FOR UPDATE NOWAIT` 验证持锁；未命中拒绝 |
| **AC-29** 宿主检查点含 VM+NIC 且被消费 | T-28 + G-8 + 注入 | **PASS** | 元组含两检查；删除路径 AST 传入；删除 NIC 检查注入 → guard FAILED |
| **AC-30** NIC 自身检查点显式声明并真实传入 | T-29 + G-9 + 注入 | **PASS** | 显式 `= ()`；删除路径经 AST 确认真实传入；注入 → guard FAILED |
| **AC-31** 不承载 IP 语义 | T-30 | **PASS** | 无 IP 端点/表/字段/cluster_id；NIC 删除当前不被 IP 拦截 |
| **AC-32** 不越界 VM/Container/Service/Cluster | T-31 + 注入 | **PASS** | 无相关端点/列/载体；跨模块越界注入被两条全局 guard 检出 |
| **AC-33** 无未确认字段/无自动发现 | T-32 + G-1/G-10 | **PASS** | 无 MAC/速率/MTU/端口/自动发现/同步字段或端点 |
| **AC-34** 前端三态 / Empty vs Not Found / error.code / 不重复守卫 | T-FE-01 + 组件 + 真实 client | **PASS\*** | 三态互异、详情独立 not-found、按 code 分支、不解析 message、不预判业务守卫；功能行为独立复核正确，但对应用例存在非确定性失败（F004-T-01） |

**说明**：AC-01 ~ AC-34 全部有结果，**无 FAIL、无 BLOCKED、无 NOT TESTED**（功能语义全部满足）。`*` AC-34 的产品行为正确，但覆盖它的 F004 前端测试存在 flaky 缺陷（F004-T-01），导致「全量前端测试真实通过」不成立。

## Test Work（T-01 ~ T-32 / G-1 ~ G-14 / T-FE-01）覆盖

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | 7 字段封闭；无 deleted_at / status / IP / 硬件 / 载体字段 |
| T-02 | PASS | name 缺失/非串 → 400 field，无写入 |
| T-03/T-04 | PASS | 四/七合法值通过；非法值 400 field；DB 23514 |
| T-05 | PASS | Other 普通成员；other_text 400 |
| T-06 | PASS | bare_metal_id 缺失/非整数 400 field |
| T-07 | PASS | 宿主不存在/已删 404 无写入非 5xx |
| T-08 | PASS | 多父/VM/Container/Cluster/选择器 400 |
| T-09 | PASS | 同宿主同名两次 201 |
| T-10/T-11 | PASS | 中文/点号/连字符；空串/空白/"/" 原样 |
| T-12 | PASS | 无 status |
| T-13/T-14 | PASS | Empty 200；详情 404 |
| T-15/T-16 | PASS | 宿主过滤 Empty vs 404；已删排除 |
| T-17/T-18/T-19 | PASS | PATCH 正常/非法/封闭 |
| T-20/T-21/T-22 | PASS | 204 行保留/不级联/无恢复批量 |
| T-23 | PASS | 同名各自软删；无 409 DUPLICATE |
| T-24/T-25 | PASS | 409 ACTIVE_CHILDREN_EXIST / 软删后可删 |
| T-26/T-27 | PASS | 两种交错不变式 0 行；FOR SHARE 持锁 |
| T-28/T-29 | PASS | 检查点显式声明并被消费（注入可失败，AST） |
| T-30/T-31/T-32 | PASS | 无 IP / 越界 / 未确认字段 |
| T-FE-01 | PASS* | 三态/Empty vs NotFound/error.code/不重复守卫（*见 F004-T-01） |
| G-1 ~ G-14 | PASS | 19 条注入逐一证明 guard 可失败并逐字节还原；G-7 全局扫描保持（跨模块注入反证） |

---

## Database / Migration

- database 层 `true` 独立确认：新增 `0005_f004_network_interfaces`；`0001` ~ `0004` **diff 为空**、未被改。
- 真实库 `csm_mig`：`upgrade head` ×2（第二次 no-op）、`current = 0005_f004_network_interfaces (head)`、`alembic check` 无漂移、`downgrade 0004` + `upgrade head` 重建成功。
- 直连 `information_schema` / `pg_constraint` / `pg_indexes` 与 Database Handoff V-1 ~ V-9 逐项一致（8 列、FK `RESTRICT`/`RESTRICT`、两个 CHECK 取值逐字匹配、`ix_network_interfaces_bare_metal_id`、无额外唯一索引、无 CHECK 之外约束、无 collation / 触发器 / CASCADE）。
- 约束行为绕应用层验证（V-10 / V-11）：非法枚举 → `23514`；不存在宿主 → `23503`；同宿主同名两行直插成功；空串 / 空白 / `/` 原样存取。
- 既有表结构未被本 migration 改变（V-15；`clusters` / `virtual_machines` 列集合断言通过）。

## Backend / API

- 5 端点行为经真实 uvicorn + 真实 PG 全量复核（100/100）：契约字段集合封闭、必填/枚举 400 + `details[].field`、宿主存在性/活跃性 404、同宿主同名 201（无 409 DUPLICATE）、Empty vs Not Found、按宿主过滤、PATCH 封闭、DELETE 204 行保留、无越界路由/参数。
- 创建侧 `_lock_active_host` 对宿主行 `SELECT … WHERE deleted_at IS NULL FOR SHARE`；并发 T-26/T-27 以真实 PostgreSQL 行锁验证两种交错与阻塞，孤立记录不变式 0 行。
- F014 接线：`app/bare_metals/deletion.BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines, has_active_network_interfaces)`，被 `app/bare_metals/service.py::delete_bare_metal` 消费；宿主有活跃 NIC → 409 无部分写入。
- 删除委托系统内唯一软删路径 `app/deletion/service.py::soft_delete()`；NIC 模块无第二写入路径（G-12 注入可失败）。
- 应用层枚举校验唯一一份，创建/更新共用；绕过预检直达 DB 的 `23514` 经通用映射返回 **400（非 500）**。
- **未发现任何 AC 层面的后端功能违约**；guard 演进仅遗留 F004-T-02 的 `nic` token 覆盖缺口（LOW）。

## Frontend

- `typecheck` 0；`build`（vue-tsc + vite build）成功。
- 列表页 `NetworkInterfaceListPage`：`loading / empty / error / content` 四态互不相同；Empty（200 + `items==[]`）与 Not Found（宿主 404 → ErrorState `NOT_FOUND`）可区分；删除二次确认 + 提交中 Loading 防重复；登记入口；**无状态列 / 状态筛选**。
- 详情页 `NetworkInterfaceDetailPage`：独立 `not-found` 态；展示全部 7 字段（时间不透明字符串）；编辑仅 `technology_type` / `purpose`，`name` / `bare_metal_id` 无输入；删除入口。
- 表单 `NetworkInterfaceFormDialog`：create = 宿主下拉 + name + 两个枚举；edit = 仅两个枚举；无 name 长度/空串/字符校验、无唯一性预检；失败按 `error.code` 分支（`VALIDATION_ERROR` 展示 `details[].field`）。
- 组件测试使用「与展示无关」的 message 证明前端不解析 message；不重复实现业务守卫（同名 name、空 name、宿主存在性、删除守卫均直接提交由后端裁决）。
- **但 `npm run test` 未通过**：`networkInterfaceListPage.spec.ts` 存在非确定性失败（F004-T-01）。详情页测试稳定。

## Integration

**真实前后端集成 = PASS（实际执行，非 Mock / Fixture）**：

1. 真实 uvicorn（真实 PG `csm_api`）+ 原始 httpx：100 项断言全部通过。
2. **前端真实 API client** + 真实 HttpOnly 会话 Cookie：未认证 401 → 登录 → Empty → 201（字段恰 7）→ 同宿主同名 201 → 400 → 404 → PATCH → GET → 宿主 409 → DELETE 204 → 404，临时探针 1/1 通过，运行后删除。

---

## Defects

### F004-T-01 — 前端 `networkInterfaceListPage.spec.ts` 登记流程用例非确定性失败，`npm run test` 无法通过（MEDIUM）

- **ID**：F004-T-01
- **Severity**：MEDIUM
- **Layer**：Frontend / Test（`frontend/tests/networkInterfaceListPage.spec.ts`）
- **Location**：`NetworkInterfaceListPage 登记入口` 描述块中的「401 UNAUTHENTICATED …」用例（约 L869-892）与「提交中：提交按钮 Loading …」用例（约 L900-930）。两者均在 `selectHost` / `selectEnums` 之后**未等待提交按钮 DOM 解除 disabled** 就 `trigger('click')`。
- **复现步骤**：
  1. `cd frontend && npx vitest run tests/networkInterfaceListPage.spec.ts`（单独文件，无其它负载）；
  2. 或 `npm run test`（全量）。
- **期望**：`npm run test` 稳定全绿（Tests 307 passed）。
- **实际**：
  - 单文件独立重跑 5 次：第 1、4 次 28 passed；第 2、3、5 次 `1 failed | 27 passed`，失败用例为「401 UNAUTHENTICATED」（`expect(unauthenticated).toHaveBeenCalledTimes(1)` → got 0，超时 10s）。
  - `npm run test` 连续两次均 `Test Files 1 failed | 23 passed`、`Tests 1 failed | 306 passed`；失败用例在「401」与「提交中」（`expect(createCalls(fetchMock)).toBe(1)` → got 0）之间漂移，**同一根因**。
  - 独立诊断（临时探针，运行后删除）：在 `trigger('click')` 前加 `await nextTick()` 并 `waitForUi` 等待 `nic-form-submit` 的 `disabled` 属性消失，同一序列 **5/5 passed**。根因确认：`update:modelValue` 通过 `vm.$emit` 同步更新表单状态，但提交按钮的 `disabled`（绑定 `submitDisabled` 计算属性）要到下一个 tick 才反映到 DOM；未 await 即点击时按钮仍处 disabled，点击不触发事件 → 无 POST、无 401、无刷新。
- **影响**：F004 新增前端测试存在非确定性；「全量前端测试真实通过」不成立，构成 CI 不稳定。**非产品缺陷**（真实用户不会点击 disabled 按钮；产品行为经独立验证正确。
- **建议**：提交前 `await waitForUi(() => expect(submitButton.attributes('disabled')).toBeUndefined())`，或对按钮组件直接 `vm.$emit('click')` / `await nextTick()`。
- **Owner**：frontend

### F004-T-02 — F002 `test_t29` 的 `forbidden_prefixes` 一并移除 `nic` token，非 GET 缩写越界路由 `/api/nics` 不再被任何 guard 覆盖（LOW）

- **ID**：F004-T-02
- **Severity**：LOW
- **Layer**：Backend / Test guards（`tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns`）
- **Location**：`forbidden_prefixes` 由 `(nic, ip, network-interface, network_interface, container, service)` 改为 `(ip, container, service)`。
- **复现步骤**：临时向 `backend/app/main.py`（非资源模块）追加 `POST /api/nics`，运行 `test_g009_2` / `test_t29` / `test_g7` / `test_structure_guard`。
- **期望**：缩写越界资源路由（非 GET）应被边界 guard 检出并失败。
- **实际**：**9 passed**，无任何 guard 检出 `POST /api/nics`；已逐字节还原（`git status` 为空）。`GET /api/nics` 仍会被 `tests/test_auth_guards.py::test_g_f_only_read_only_get_routes` 全局 GET 白名单检出，缺口仅限**非 GET**。
- **独立判定**：`nic` 并非 `/api/network-interfaces` 的前缀（`"network-interfaces".startswith("nic") == false`），不存在必须移除的正当理由；F006 复验时曾刻意保留 `nic` 并追加 `network-interface` token，本 Feature 一并删除构成相对上一状态的**非必要覆盖收窄**。相较 F006-T-01（把全局扫描收窄到单模块），本项范围小得多（仅缩写 token），且全局扫描范围保持。
- **影响**：非 GET 缩写越界路由的回归防线削弱；当前无功能性影响。
- **建议**：在 `forbidden_prefixes` 中保留 `"nic"`（与已合法化的 `network-interfaces` 不冲突）。
- **Owner**：backend

**除上述 2 项外，未发现 BLOCKER / HIGH / PRODUCT / ARCHITECTURE / DATABASE / FRONTEND（产品实现）缺陷；未发现任何 AC 功能性违约。**

### 独立判定：前端超时改动是否构成测试削弱

**结论：不构成测试削弱。** 证据（`git diff cf03e01..6ec3b9e`，仅统计已存在的 spec 与 `vite.config.ts`）：

- 变更仅包含：`vi.waitFor` 超时 `1000/5000 → 10000`、新增 `waitForUi` 包装函数（其函数体亦仅调用 `vi.waitFor(..., {timeout:10000})`）、`vite.config.ts` 新增 `testTimeout: 20000`；**所有既有断言语义逐条未变**（对被修改的既有 spec，diff 中除 timeouts / `waitForUi` 包装 / 注释外无任何加减行；见「摘要 12/证据」）。
- 该改动不会让失败断言变为通过（仅延长轮询上限）；本次 F004 的 flaky 用例在 10s 上限下**仍然失败**，反证其并非“放宽到通过”。
- 附注（非缺陷）：超时放宽会延长真实故障的暴露时间，且本次 flaky 用例的失败正是以「10s 超时」形式呈现，掩盖了根因（F004-T-01），建议在修复 F004-T-01 后回收至合理上限。

---

## Unverified Areas

1. **浏览器级前端 E2E / 视觉 / 真实 DOM**：无浏览器自动化环境；前端行为经 vitest（happy-dom）组件测试与真实 API client 集成验证，未在真实浏览器观察渲染 / 网络 / 视觉。
2. **多 uvicorn worker / 跨进程并发压测**：并发端到端以独立连接 / 线程验证行锁协议，未做多 worker 压测（无产品需求，V1 单机内网）。
3. **NIC 自身活跃子检查 409 分支的真实触发**：当前 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 为空，该分支在本 Feature 内不可达（契约明示）；仅以静态 AST guard 覆盖声明与传入，未构造非空注入下的端到端 409 断言（功能语义由 `soft_delete` 既有 F014 测试覆盖）。
4. **静态 guard 对动态 SQL / 动态路由构造的穷举覆盖**：承 F014 已知残余风险；本次 G-1 ~ G-14 均以静态 / DB 注入证明可失败，但对运行期动态构造无覆盖。

## Test Status

`RETURN TO IMPLEMENTATION`

依据：AC-01 ~ AC-34 全部有结果并全部满足**功能语义**；真实前后端集成已实际执行；数据库结构 / Migration / 约束与 Database Handoff 一致；后端全量 `551 passed`（无 skipped）、ruff / format 全绿；19/19 对抗注入证明 NIC guard 与跨模块边界 guard 真实可失败并逐字节还原；前端 `typecheck + build` 全绿，前端真实 client 集成通过。但 **`npm run test` 未真实通过**（F004-T-01，MEDIUM，非确定性失败，独立诊断已定位根因），且 F002 边界 guard 遗留 `nic` token 覆盖缺口（F004-T-02，LOW）。二者属需实现方修复的 Defect。**无 BLOCKER / HIGH，无功能性缺陷。**

---

## Test Handoff

### Status

`RETURN TO IMPLEMENTATION`

### Verified

- AC-01 ~ AC-34 全部 PASS（功能语义）；无 FAIL / BLOCKED / NOT TESTED。
- Architecture Test Work T-01 ~ T-32 / G-1 ~ G-14 / T-FE-01 全部 PASS（T-FE-01 见 F004-T-01）。
- 数据库：`network_interfaces` 8 列 / FK RESTRICT / 两个封闭枚举 CHECK / `ix_network_interfaces_bare_metal_id` / 无额外唯一索引 / 无 CASCADE / 无触发器 / 无 COLLATE 与 Database Handoff 一致；`0001`~`0004` 基线未改；migration 可应用 / 可重复 / 可重建；`alembic check` 无漂移。
- 后端：5 端点契约行为（100/100 真实 HTTP）、无唯一性 / 无 409 DUPLICATE、Empty vs Not Found、按宿主过滤、PATCH 封闭、DELETE 204 行保留、无越界 / 无 status / 无 IP / 无未确认字段；创建侧 `FOR SHARE` + 并发不变式 0 行；F014 端到端 409 / 204；DB `23514 → 400`（永不 500）。
- 前端：三态互异、Empty vs Not Found 可分、`error.code` 分支、不解析 message、不重复实现业务守卫；`typecheck` / `build` 全绿。
- 真实前后端集成实际执行（真实 uvicorn + 真实 PG + 前端真实 client）。
- G-1 ~ G-14 + 跨模块越界路由共 19 条注入全部被对应 guard 检出并逐字节还原；F009 `BOUNDARY_TOKENS` / F002 `test_t29` **保持全局扫描**（跨模块注入反证）。
- 独立判定：前端超时改动**不构成测试削弱**（仅超时/包装，断言语义未变）。

### Not Verified

- 浏览器级 E2E / 视觉 / 真实 DOM。
- 多 worker / 跨进程并发压测。
- NIC 自身非空子检查 409 分支的真实触发（当前不可达）。
- 静态 guard 对动态构造的穷举覆盖。

### Blocking Issues

- F004-T-01（MEDIUM，Frontend/Test）：`npm run test` 非确定性失败，需修复测试的提交前等待。
- F004-T-02（LOW，Backend/Test guards）：`test_t29` 移除 `nic` token，非 GET `/api/nics` 越界路由无 guard 覆盖。

### Defect Owner

- F004-T-01（MEDIUM）→ frontend
- F004-T-02（LOW）→ backend

### 新增 / 修改文件

- 本次测试**未新增 / 未修改仓库内任何业务文件**：报告为唯一产出；临时集成脚本（`/tmp/f004-test/**`）、临时 vitest 探针（`frontend/tests/zzTmpF004Integration.spec.ts` / `zzTmpDiag.spec.ts`）运行后已删除；对抗注入已逐字节还原（多份备份哈希比对一致）。
- 未修改任何业务实现（`backend/app/**`、`backend/migrations/**`、`frontend/src/**`）或产品 / 架构 / 契约 / 数据库设计文档。

---

GIT: NONE

---

# Re-verification（修复复验）

> 复验角色：tester（独立）
> 复验日期：2026-09-18
> base `develop` = `cf03e014a9abbd0dad88a00da57947e731778513`
> 上一轮实现 HEAD = `6ec3b9ea388c89e74a270fb416bf1bddb8652646`（其后 `e22e234` 计划检查点）
> 修复后 HEAD = `1af0bbeba9eac87148b19f4af8b978538a629b2d`（`5c63168` 修复 + `1af0bbe` 计划检查点）
> 复验范围：F004-T-01（MEDIUM，前端测试非确定性）/ F004-T-02（LOW，`test_t29` `nic` token 覆盖缺口），并独立判断修复未掩盖其它问题。

原报告内容全部保留；本小节为追加。

## 修复差异（`git diff 6ec3b9e..1af0bbe -- frontend/tests frontend/vite.config.ts tests/test_bare_metals_api.py`）

| 文件 | 修复内容 | 性质 |
|---|---|---|
| `frontend/tests/networkInterfaceListPage.spec.ts` | 新增 `submitWhenEnabled(wrapper)` 辅助：先 `waitForUi` 等 `nic-form-submit` 的 `disabled` 消失再 `trigger('click')`；7 处提交点击由裸 `trigger('click')` 改为 `await submitWhenEnabled(...)` | 测试加固（等待 DOM 就绪），**无断言被删** |
| `frontend/tests/setup/monotonic-date-now.ts` | **新增** 测试进程 `Date.now()` 单调化 setup（幂等、时钟正常时恒等） | 测试基础设施补丁 |
| `frontend/vite.config.ts` | 新增 `test.setupFiles: ['tests/setup/monotonic-date-now.ts']` | 启用上述 setup |
| `tests/test_bare_metals_api.py` | `test_t29` 的 `forbidden_prefixes` **加回** `"nic"`（`(nic, ip, container, service)`） | guard **加强** |

**功能代码零改动**：`git diff 6ec3b9e..1af0bbe -- backend/app backend/migrations frontend/src` 为**空**。修复仅涉及测试代码与测试配置。

## 环境

| 项 | 值 |
|---|---|
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 真实实例，Unix socket `/tmp/f004-rev/pgdata`，本次新建） |
| 测试库 | `csm_f004`（pytest 每夹具 `DROP SCHEMA` + `alembic upgrade head` 重建）、`csm_mig`（迁移 / schema 检查），本次新建 |
| Node / npm | v24.14.0 / 11.9.0（Vitest 5.0.1，happy-dom） |
| ruff | 0.16.7 |

环境全新；实现方结论未被复用，以下所有结果均来自本次独立执行。

## F004-T-01 复验（前端 `networkInterfaceListPage.spec.ts` 非确定性）→ **Re-verified / Fixed**

### 启用修复的 setup（默认配置）

```text
$ cd frontend && for i in 1..8: npx vitest run tests/networkInterfaceListPage.spec.ts
  8 / 8 次：Test Files 1 passed (1) / Tests 28 passed (28)
$ cd frontend && for i in 1..3: npm run test
  3 / 3 次：Test Files 24 passed (24) / Tests 307 passed (307)
```

单文件 8/8、全量 3/3 全绿。

### 关键独立判断：临时禁用 monotonic setup 后再测（仅临时配置文件，验证后删除）

创建临时 `frontend/zz-tmp-nosetup.config.ts`（与 `vite.config.ts` 完全一致，**仅去掉 `setupFiles`**），运行后已删除（`git status` 干净）：

```text
$ npx vitest run --config zz-tmp-nosetup.config.ts tests/networkInterfaceListPage.spec.ts
  20 次：8 次 1 failed | 27 passed，12 次 28 passed   → 约 40% 失败
  失败用例在「打开登记对话框」/「填表提交」/「404 NOT_FOUND」/「空 name 提交」/
  「同名提交」之间漂移，均以 waitForUi 轮询 ~10s 超时结束（无 POST / 无对话框）
$ npx vitest run --config zz-tmp-nosetup.config.ts   （全量，4 次）
  4 次中 1 次失败：Test Files 4 failed | 20 passed，Tests 4 failed | 303 passed
  失败横跨 4 个**不同** spec 文件：
    tests/bareMetalListPage.spec.ts / tests/networkInterfaceDetailPage.spec.ts /
    tests/networkInterfaceListPage.spec.ts / tests/virtualMachineListPage.spec.ts
```

对比结论：**启用后稳定、禁用后不稳定** → `monotonic-date-now` 补丁**有效且必要**。

### 根因独立核实（非采信注释）

1. **宿主机时钟确实会向后跳变**：本次独立看门狗（2ms 采样，`node -e` 进程）在 292.7s 内记录 **20 次回拨**，幅度 **195~526ms**，约每 15s 一次（`/tmp/clockwatch.log`）。这与注释声称的「每 10~30s、0.5~2.5s」量级一致（幅度略小）。
2. **Vue / VTU 两处代码确认**（`frontend/node_modules`，非推测）：
   - `@vue/runtime-dom` `createInvoker`：`if (!e._vts) { e._vts = Date.now(); } else if (e._vts <= invoker.attached) { return; }`（`invoker.attached` 挂载时取 `getNow()`，即 `Date.now()`）；
   - `@vue/test-utils` `trigger()`：`event._vts = Date.now() + 1`。
   
   当时钟在「invoker 挂载」与「trigger」之间回拨超过 1ms，`_vts <= attached` 成立 → Vue **静默吞掉该点击**，无异常、无 handler 调用。这与观测到的「点击对话框/提交后无任何请求、10s 超时」症状吻合。
3. 另注：VTU `trigger()` 还有 `if (this.element && !this.isDisabled())` 分支——这是上一轮定位的「未等 disabled 解除即点击」竞态，本次修复以 `submitWhenEnabled` 处理。**两者是两条独立触发路径**：本次实验证明，即便已有 `submitWhenEnabled`，去掉 monotonic setup 后仍约 40% 失败，说明时钟回拨路径真实存在且未被前者覆盖。

### 独立判定：该补丁是否掩盖真实缺陷？

**结论：不掩盖产品缺陷，不构成验证削弱；判定该补丁为必要且正当的测试基础设施修复。** 理由：

- 被吞掉的点击发生在 **Vue 事件分发层**（在业务 handler 之前）。失败时产品代码根本没有执行，故不存在「绕过业务逻辑让错误实现通过」的情形；这是**环境（宿主机时钟）异常**导致的事件丢失，而非产品缺陷。
- 失败**横跨 4 个不同 spec 文件**，其中 `bareMetalListPage` / `virtualMachineListPage` / `networkInterfaceDetailPage` 的用例**本次修复未触碰**。即：该时钟异常是**全前端测试套件级**的，setup 是全局归一化，而非只针对 F004 spec 的定向掩盖。
- 补丁**不改断言、不放宽超时、不重试、不跳过、不改 `src/**`**；时钟正常时对 `Date.now()` 恒等。断言完整性已逐行核对（见下）。
- **残余风险（报告但不判缺陷）**：setup 对**全部**前端 spec 生效。若某用例潜藏「仅当真实时钟回拨时才失败」的时序缺陷，补丁会使其在异常时钟下仍「通过」。但 (a) 该类失败由宿主环境触发、不代表产品行为；(b) 本次全量套件在启用下 3/3 全绿、禁用下亦有整轮全绿（说明无该 spec 每次都依赖回拨），未观测到被掩盖的用例。

### 断言完整性（未被削弱）

`networkInterfaceListPage.spec.ts` 的 diff 仅：新增 `submitWhenEnabled` 函数体（其内部为真实断言 `expect(button.attributes('disabled')).toBeUndefined()`）、把 7 处裸 `trigger('click')` 替换为 `await submitWhenEnabled(...)`、更新 1 行注释。**无任何 `expect` 被删除或放宽**；测试数量仍为 28，与上一轮稳定运行时的数量一致。

## F004-T-02 复验（`test_t29` `nic` token 覆盖缺口）→ **Re-verified / Fixed**

修复后 `forbidden_prefixes = ("nic", "ip", "container", "service")`，且扫描逻辑仍为**全部 `/api/*` path**（`path.startswith("/api/") and remaining.startswith(prefix)`），未收窄范围。

**注入**：临时向 `backend/app/main.py`（非任何资源模块，`create_app` 内 `return app` 前）追加 `POST /api/nics` / `POST /api/containers` / `POST /api/ip-addresses`，运行：

```text
FAILED tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns
  AssertionError: F002 不得注册其它资源端点：['/api/ip-addresses', '/api/nics', '/api/containers']
FAILED tests/test_cluster_views_guards.py::test_g009_2_no_forbidden_resource_tokens_in_any_path
  AssertionError: 不得注册其它资源端点：['/api/containers', '/api/ip-addresses']
```

**隔离验证（仅注入 `POST /api/nics`）**，以区分两条 guard 各自的覆盖：

```text
FAILED tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns
PASSED tests/test_cluster_views_guards.py::test_g009_2_no_forbidden_resource_tokens_in_any_path
PASSED tests/test_network_interfaces_guards.py::test_g7_boundary_tokens_narrowed_but_global
1 failed, 2 passed
```

**对 `test_g009_2` 表现的记录与理由**：`test_g009_2` 的 `BOUNDARY_TOKENS`（F009，`(ip-address, ip_address, container, service)`）**不含** `nic`，故对 `/api/nics` 本就不覆盖；上面全量三路由注入时它之所以 FAILED，是命中了 `/api/containers` 与 `/api/ip-addresses`（其报错明细亦只列出这两条）。因此 `/api/nics` 的检出**由 `test_t29` 独立承担**，修复后该缺口已闭合；`test_g009_2`/`test_g7` 的 F009 token 列表无需变动（其语义是 IP/容器/服务边界，非 NIC 缩写）。

**还原**：`cp` 备份回写后 `sha256sum backend/app/main.py` = `0b80f8a27f9027971b390f7cabc791ee774c83f8a0999d2e48db66d3de673362`（注入前备份一致），`git status --short` 为空。

## 修复未削弱其它 guard（独立验证）

1. **guard 代码 diff 逐行核对**：`git diff 6ec3b9e..1af0bbe` 中唯一触碰 guard 的行是 `tests/test_bare_metals_api.py` **新增** `"nic"` token——**纯加强**，无断言删除。
2. **未把 guard 改成恒真**：`test_t29` 仍保留完整 offenders 计算、列集合断言、`/api/bare-metals/by-name/{hostname}` 断言；无 `or True` / 提前 `return` / 断言删除。
3. **抽查 F006 guard 仍可失败**：临时给 `VirtualMachineCreate.name` 加 `min_length=1` 后：

```text
FAILED tests/test_virtual_machines_guards.py::test_g7_vm_schemas_have_no_undefined_constraints
  AssertionError: assert {'min_length'} == set()
```

   `sha256sum backend/app/virtual_machines/schemas.py` = `0919a53e...57a7` 还原一致，`git status` 干净。
4. **抽查 F009 guard 仍可失败**：见上（`test_g009_2` 对越界 `containers` / `ip-addresses` FAILED）。
5. **无新增/删除测试文件**：F004 前端 spec 数仍为 1（28 用例），全量 24 spec 文件 / 307 用例，与上一轮稳定基线一致。

## 工程门禁（真实执行）

```text
$ CSM_TEST_DATABASE_URL=.../csm_f004... .venv/bin/python -m pytest -q
  551 passed, 2 warnings in 444.33s (0:07:24)（无 skipped）
$ .venv/bin/ruff check backend tests           → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests  → 117 files already formatted  exit 0

# 迁移（真实 PG 16.2，csm_mig，本次新建）
$ alembic upgrade head   → 0001 → 0002 → 0003 → 0004_f006_virtual_machines → 0005_f004_network_interfaces
$ alembic current        → 0005_f004_network_interfaces (head)
$ alembic upgrade head   → no-op
$ alembic check          → No new upgrade operations detected.

# 前端
$ cd frontend && npm run typecheck   → exit 0
$ npm run build                      → vue-tsc + vite build 成功
                                       dist/assets/index-SImFp6qX.js 1,065.05 kB（仅 chunk 体积告警）
```

## Integration

修复 commit（`5c63168`）对 `backend/app/**`、`backend/migrations/**`、`frontend/src/**` 的改动为**零**（`git diff 6ec3b9e..1af0bbe` 该范围为空），故上一轮**已实际执行**的真实前后端集成（真实 uvicorn + 真实 PG + 前端真实 API client）在契约层面**字节不变、仍然有效**；本轮未重复启动跨进程 uvicorn + 前端 client 探针。后端全量套件（真实 PG，含全部 F004 API / 约束 / 并发）本轮 **551 passed**，前端全量 **307 passed**。

## 复验结论

| Defect | Severity | 复验结果 |
|---|---|---|
| F004-T-01 前端 `networkInterfaceListPage.spec.ts` 非确定性失败 | MEDIUM | **Re-verified / Fixed** — 启用 setup 单文件 8/8、全量 3/3；禁用 setup 单文件 8/20 失败、全量 1/4 轮失败（跨 4 个 spec 文件）。monotonic `Date.now()` 补丁有效且必要，且经独立核实（宿主时钟 20 次回拨 + Vue/VTU 源码）不掩盖产品缺陷。 |
| F004-T-02 `test_t29` `nic` token 覆盖缺口 | LOW | **Re-verified / Fixed** — `nic` 已加回，全局扫描保持；注入 `/api/nics` 后 `test_t29` FAILED（隔离验证），逐字节还原、`git status` 干净。 |

无新增缺陷；无 BLOCKER / HIGH；修复未削弱其它 guard；产品代码零改动。

## New Test Status

`READY FOR REVIEW`

依据：上一轮 2 个缺陷（F004-T-01 MEDIUM / F004-T-02 LOW）均**独立复验修复**，每项以真实注入 / 对照实验证明并逐字节还原；AC-01 ~ AC-34 在上一轮已全部 PASS，且本轮确认修复对产品代码**零改动**，功能语义不变；真实 PG 16.2 全量后端 `551 passed`（无 skipped）、ruff / format 全绿、migration head 一致无漂移；前端 `typecheck + 307 passed + build` 全绿。无 BLOCKER / HIGH / 必须修复的 MEDIUM，无新增缺陷。

---

GIT: NONE
