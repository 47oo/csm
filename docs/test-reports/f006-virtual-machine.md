# Test Report — F006 VirtualMachine 登记与管理

> Status: **RETURN TO IMPLEMENTATION**
> Author Role: tester
> Date: 2026-09-18
> Feature: F006（E03，P1，`depends_on: [F002]` = DONE）
> 分支：`feature/F006-virtual-machine`
> base `develop` = `f74e7ddbf369910e6f83b99758b672019b4fe4c9`
> 实现 HEAD = `5d87d207d92c06e2b8d0e7e34d0b7436064bf992`（其后 `03db90a` 为计划元数据检查点）
> layers：database/backend/frontend 均 true；contract READY、backend COMPLETE、frontend COMPLETE、test PENDING

---

## Feature

VirtualMachine 登记与管理（F006）— CSM V1 虚拟资源的第一个资源：虚拟机的人工登记、查询、可选配置维护与逻辑删除，以及 **VirtualMachine → BareMetal 必选绑定** 的真实业务落地，并作为 F014「宿主有活跃子 VM → 不得删宿主」的第二个真实端到端。

## Test Basis

- `AGENTS.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/handoffs/f006-virtual-machine.md`（Product Handoff，`READY FOR ARCHITECT`，AC-01 ~ AC-32）
- `docs/architecture/f006-virtual-machine-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，Test Work T-01 ~ T-30 / G-1 ~ G-11 / REQUIRED / Constraints）
- `docs/database/f006-virtual-machine-migration.md`（Database Handoff，V-1 ~ V-14）
- `docs/api/f006-virtual-machine.md`（API 契约 **READY**，唯一权威）、`docs/api/api-conventions.md`
- ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005（均 `ACCEPTED`）
- 报告格式先例：`docs/test-reports/f002-bare-metal.md`、`docs/test-reports/f009-cluster-resource-view.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f006-test/pgdata`，本次新建） |
| collation | `zh_CN.UTF-8` / `zh_CN.UTF-8`；实测 `'abc' = 'ABC'` → `false`（**大小写敏感**，满足 R-VM-004 / AC-11 前提） |
| 测试库 | `csm_f006`（pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 重建）、`csm_mig`（迁移 / 直连 schema 检查）、`csm_api`（真实 uvicorn + 前端真实 client 集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn`（真实 PG `csm_api`）：`127.0.0.1:8796` |
| Node / npm | v24.14.0 / 11.9.0（Vite 7.3.6，Vitest 5.0.1，happy-dom 20.14.5） |
| ruff / psycopg | 0.16.7 / 3.3.5 |

**是否全新**：PG 实例、三个测试库、管理员账号、集成探针均为本次测试新建；pytest 每次从空库重建。实现方结论**未被复用** — 下表所有结果均来自本次独立执行。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端全量测试（独立重跑，无 skip）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f006?host=/tmp/f006-test/pgdata" \
  .venv/bin/python -m pytest -q
400 passed, 2 warnings in 267.96s（无 skipped）

F006 专项：tests/test_virtual_machines_{api,guards,concurrency}.py +
  tests/database/test_virtual_machines_{constraints,schema_guard}.py
  → 30 + 16 + 4 + 7 + 14，全部通过
```

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 103 files already formatted  exit 0
```

### 3. 迁移（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head   → 0001 → 0002 → 0003 → 0004_f006_virtual_machines
$ alembic current        → 0004_f006_virtual_machines (head)
$ alembic upgrade head   → no-op（无 DDL）
$ alembic check          → No new upgrade operations detected.（无漂移）
$ alembic downgrade 0003_f002_bare_metals → 成功（virtual_machines 删除）
$ alembic upgrade head   → 重建成功
$ git diff base..HEAD -- 0001_f012_baseline.py 0002_f013_auth.py 0003_f002_bare_metals.py → 空（基线未改）
```

### 4. 独立 Schema 直连检查（真实 PG 16.2，`csm_mig`）

```text
tables: [alembic_version, bare_metals, clusters, sessions, users, virtual_machines]
virtual_machines 列（恰 12）: id bigint NN(identity) / bare_metal_id bigint NN / name text NN /
  cpu,memory,disk,os,hypervisor,owner text NULL / created_at,updated_at timestamptz NN DEFAULT now() /
  deleted_at timestamptz NULL
约束: pk_virtual_machines / fk_virtual_machines_bare_metal(FK confdeltype='r', confupdtype='r')
索引: ux_virtual_machines_name_active UNIQUE(name) WHERE deleted_at IS NULL /
      ix_virtual_machines_bare_metal_id
列级 collation: [] ; 非内部触发器: [] ; 全库 confdeltype='c' 外键: [] ; VM CHECK: []
```

与 Database Handoff V-1 ~ V-8 逐项一致。

### 5. 直连约束行为（绕过应用层，`csm_mig`）

```text
重复活跃 name → SQLSTATE 23505
大小写敏感：vm1 与 VM1 可并存
指向不存在宿主 → SQLSTATE 23503
soft delete 后同名可重新插入活跃行（释放唯一性）
空串 / 首尾空白 / 含 "/" 的 name 原样接受
```

### 6. 真实后端 HTTP 集成（真实 uvicorn + 真实 PG，原始 httpx）

```text
$ .venv/bin/python /tmp/f006-test/integration.py → 116/116 passed
覆盖：未认证 5 端点 401（无 items）/ 登录 / Empty(全局)/ 201 字段集合恰 11 /
  status·cluster_id·deleted_at 缺席 / 六可选字段 null 不省略 / 中文与 "8 vCPU" 原样往返 /
  name 缺失·非串 → 400 field=name / 宿主缺失·非整数 → 400 field=bare_metal_id /
  宿主不存在·已软删 → 404 且无写入非 5xx / 多宿主·VM·Container 作宿主·类型选择器 → 400 /
  空串·首尾空白·"/" name 不被拒绝 / 跨宿主·跨 Cluster 重名 → 409 name/DUPLICATE /
  大小写敏感共存 / 直插重复 → 23505 / 软删释放且旧行 deleted_at 未被改写 /
  详情 404（不存在·已删不区分）/ 绕应用层预置已删行被排除 /
  按宿主过滤：不存在·已删 404 vs 存在但空 200+[]；非整数 400；只返回该宿主子集 /
  PATCH 200 新值·null 清空·缺省不变·不可变/未知字段 400·空 body 400·404 /
  DELETE 204 空 body·行保留·不级联（宿主三元组不变）/
  无 restore/undelete/purge/batch 路由 / 宿主有活跃 VM → 409 ACTIVE_CHILDREN_EXIST 无部分写入 /
  软删全部子后宿主 204 / 孤立记录不变式 0 行 /
  无平台列·端点 / 无越界列·路由 / OpenAPI schema 无 status·cluster_id /
  GET 参数恰 {page,page_size,bare_metal_id} / GET 前后行快照不变（只读无副作用）
```

### 7. 真实前后端集成（**前端真实 API client** + 真实 uvicorn + 真实 PG；临时 vitest 探针，运行后已删除）

使用 `frontend/src/api/{auth,clusters,bareMetals,virtualMachines,http}.ts`，经 happy-dom 同源（`http://127.0.0.1:8796`）管理真实 HttpOnly 会话 Cookie：

```text
$ npx vitest run tests/zzTmpF006Integration.spec.ts → Test Files 1 passed | Tests 1 passed
- 未认证 listVirtualMachines() → ApiError{status:401, code:'UNAUTHENTICATED'}
- login → 创建 Cluster / BareMetal → 宿主无 VM 列表 200 + items==[]
- createVirtualMachine → 字段键恰 11、cpu='8 vCPU'、memory=null
- 重复 name → ApiError{status:409, code:'CONFLICT', details 含 name/DUPLICATE}
- 不存在宿主列表 → ApiError{status:404, code:'NOT_FOUND'}（与 Empty 不同）
- PATCH → 200 新值；getVirtualMachine → 200；deleteVirtualMachine → resolve undefined(204)
- 删除后详情 404；软删后同名可重新登记（新 id）；真实 client 列表 total==1
```

探针文件 `frontend/tests/zzTmpF006Integration.spec.ts` 与临时 Python 脚本运行后已删除；`git status --short` 为空。

### 8. 对抗注入（证明 guard 真实可失败，逐字节还原）

对 G-1 ~ G-11（外加 G-6 删除路径）逐条注入 → 运行对应 guard → 还原（`sha256sum -c` 校验）：

| 注入 | 目标 guard | 结果 |
|---|---|---|
| 模型加 `status` 列 | G-1 `test_g1_model_metadata_columns_exact` | **FAILED** |
| 模型 FK `RESTRICT`→`CASCADE` | G-2 `test_g2_model_indexes_and_fk` | **FAILED** |
| `EXPECTED_TABLES` 删除 `virtual_machines` | G-3 `test_expected_table_whitelist` | **FAILED** |
| `EXPECTED_GET_ROUTES` 删除 VM 两条 | G-4 | **FAILED** |
| `BARE_METAL_ACTIVE_CHILD_CHECKS = ()` | G-5 / T-26 | **FAILED** |
| VM 检查点改为 `tuple()`（非显式 `= ()`） | G-6 / T-27 | **FAILED** |
| 从 `service.py` 删除 `active_children=VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 实参 | G-6b / T-27 删除路径 | **PASSED (未检出)** → Defect F006-T-02 |
| schema 加 `str_strip_whitespace` | G-7 | **FAILED** |
| migration FK 改 `CASCADE` | G-8 `test_g8_no_cascade_foreign_keys_globally` | **FAILED** |
| 新增第二个写 `deleted_at` 文件 | G-9 allow-list | **FAILED** |
| 模型加 JSON 列 | G-10 | **FAILED** |
| `MIGRATION_HEAD` 改回 `0003` | G-11 | **FAILED** |

即 **11/12** 注入被判失败；G-6b（VM 删除路径「真实传入」）未被静态 guard 检出（见 Defects）。

还原校验：`git status --short` 为空，所有被改文件 `sha256sum -c` 成功。

### 9. 前端

```text
$ cd frontend && npm run typecheck → exit 0
$ npm run test → Test Files 20 passed (20)，Tests 242 passed (242)
$ npm run build → vue-tsc 通过 + vite build 成功
                  dist/assets/index-B8mECZbk.js 1,049.38 kB（仅 chunk 体积告警）
```

---

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 登记成功、字段集合恰 11、无 deleted_at/status/cluster_id | T-01 + 真实 HTTP + 前端 client | **PASS** | `set(body)==READ_FIELDS`；`deleted_at/status/cluster_id` 缺席 |
| **AC-02** `name` 必填 / 非字符串 → 400 field=name 无写入 | T-02 | **PASS** | `{}/123` → 400 + `details[].field=="name"` |
| **AC-03** 宿主必选 / 非整数 → 400 field 指向 | T-03 | **PASS** | 缺字段/`"abc"`/`null` → 400 + `field=="bare_metal_id"` |
| **AC-04** 宿主不存在 / 已删 → 阻止写入、非 5xx | T-03 | **PASS** | `404 NOT_FOUND`，行数不变（真实 HTTP 前后对比） |
| **AC-05** 恰好一个宿主；列 NOT NULL + FK RESTRICT | T-04 + G-1 | **PASS** | 多宿主/VM/Container/选择器 → 400；`fk…` `confdeltype='r'/'r'` |
| **AC-06** 可选字段缺失不阻断，返回 null 不省略 | T-05 | **PASS** | 六字段均 `in body and is None` |
| **AC-07** 纯文本往返（中文 / "8 vCPU"） | T-06 + V-11 | **PASS** | 中文 / `"8 vCPU"` 原样存取 |
| **AC-08** 未定义约束不实现（空串 / 空白 / `/`） | T-07 + G-7 | **PASS** | 空串 / 首尾空白 / `/` 均 201 且原样；无 CHECK / schema 约束 |
| **AC-09** 全局唯一跨宿主 → 409 name/DUPLICATE | T-08 | **PASS** | 宿主 B 重名 → 409 + `{field:name,code:DUPLICATE}` |
| **AC-10** 全局唯一跨 Cluster | T-08 | **PASS** | 不同 Cluster 宿主重名同样 409 |
| **AC-11** 大小写敏感 | T-09 + V-9 | **PASS** | `vm1`/`VM1` 并存；无 `lower()` 索引 |
| **AC-12** 保存前阻止；DB 为最终权威 | T-08 + V-9 | **PASS** | API 409；直插重复 → `23505` |
| **AC-13** soft delete 释放唯一性，旧行不被改写 | T-11 | **PASS** | 软删后任意宿主重新登记 201；旧行 `deleted_at` 不变 |
| **AC-14** 列表 / 分页 / Empty | T-12 | **PASS** | `{items:[],total:0,page:1,page_size:50}` 非 404 |
| **AC-15** 详情 Not Found（不区分） | T-13 | **PASS** | 不存在与已删均 `404 NOT_FOUND` |
| **AC-16** 列表 / 详情排除已删（绕应用层） | T-14 | **PASS** | 预置 `deleted_at` 行不在 items/total；按 id 404 |
| **AC-17** 宿主绑定以 `bare_metal_id` 可观察；无 cluster 维度 | T-15 + T-30 | **PASS** | 响应含 `bare_metal_id`；无 `cluster_id/cluster_name`；GET 参数封闭 |
| **AC-18** 无状态（请求/响应/表/端点无 status） | T-16 + G-1 | **PASS** | OpenAPI schema / 列 / 参数均无 status |
| **AC-19** 可选字段可更新 / null 清空 / 缺省不变 | T-17 | **PASS** | PATCH 200 新值；再次读取一致 |
| **AC-20** PATCH schema 封闭；空 body 400 | T-18 | **PASS** | `name/bare_metal_id/id/deleted_at/status/cluster_id/{}` → 400 |
| **AC-21** VM 逻辑删除 204、行保留 | T-19 | **PASS** | 204 空 body；行仍在且 `deleted_at` 非空 |
| **AC-22** 删除不级联 | T-20 | **PASS** | 宿主三元组与其它 VM 行不变 |
| **AC-23** 无恢复 / 批量 / include_deleted | T-21 | **PASS** | OpenAPI 无相关路由 / 参数 |
| **AC-24** 宿主有活跃 VM → 409 + 无部分写入 | T-22 + 真实 HTTP | **PASS** | `ACTIVE_CHILDREN_EXIST`；宿主 `deleted_at` 仍 NULL |
| **AC-25** 软删全部活跃 VM 后宿主可删 | T-23 | **PASS** | 全部 204 后宿主 DELETE 204 |
| **AC-26** 并发孤立记录不变式 = 0 | T-24（两种交错） | **PASS** | 建先 / 删先交错；不变式查询 0 行 |
| **AC-27** 创建侧对宿主行取共享锁并确认活跃 | T-25 | **PASS** | `FOR SHARE` + `deleted_at IS NULL`；`FOR UPDATE NOWAIT` 验证持锁；未命中拒绝 |
| **AC-28** `BARE_METAL_ACTIVE_CHILD_CHECKS` 非空且被消费 | T-26 + G-5 + 注入 | **PASS** | 元组含 `has_active_virtual_machines`；删除路径传入；空元组注入 → guard FAILED |
| **AC-29** `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 显式声明且被真实传入 | T-27 + G-6 | **PASS*** | 实现确实显式声明并传入；但静态 guard 可被绕过（Defect F006-T-02） |
| **AC-30** 不接入虚拟化平台 | T-28 | **PASS** | 无平台列 / 端点 / 凭据 / 外部 id |
| **AC-31** 不越界其它资源 / 位置结构 | T-29 | **PASS** | 表无相关列；无相关路由 |
| **AC-32** 前端三态 / Empty vs Not Found / error.code / 不重复守卫 | T-FE-01 + 前端测试 + 真实 client | **PASS** | `loading/empty/error/content` 互异；详情独立 not-found；按 code 分支；空 name/重复 name 仍提交 |

**说明**：AC-01 ~ AC-32 全部有结果，**无 FAIL、无 BLOCKED、无 NOT TESTED**（功能语义全部满足）。`*` AC-29 的实现行为正确，但对应静态 guard 存在可绕过性，计入 Defect。

## Test Work（T-01 ~ T-30 / G-1 ~ G-11 / T-FE-01）覆盖

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | 11 字段封闭；无 deleted_at / status / cluster_id |
| T-02 | PASS | name 缺失/非串 → 400 + field，无写入 |
| T-03 | PASS | 类型 400 / 不存在·已删宿主 404，无写入、非 5xx |
| T-04 | PASS | schema 封闭：多宿主 / VM / Container / 选择器 → 400 |
| T-05 | PASS | 六字段 null 不省略 |
| T-06 | PASS | 中文 / "8 vCPU" 往返 |
| T-07 | PASS | 空串 / 首尾空白 / "/" 不被拒绝 |
| T-08 | PASS | 跨宿主·跨 Cluster 409 + name/DUPLICATE |
| T-09 | PASS | 大小写共存；无 lower() 索引 |
| T-10 | PASS | 直插重复 → 23505；API → 409 |
| T-11 | PASS | 软删释放唯一性，旧行不改写 |
| T-12 | PASS | Empty 200+[]；分页 |
| T-13 | PASS | 404（不存在 / 已删不区分） |
| T-14 | PASS | 绕应用层预置已删行排除 |
| T-15 | PASS | bare_metal_id 可观察；无 cluster 字段 |
| T-16 | PASS | 请求 / 响应 / 表 / 端点 / 参数无 status |
| T-17 | PASS | PATCH 200 / null 清空 / 缺省不变 |
| T-18 | PASS | 未知·不可变字段 400；空 body 400 |
| T-19 | PASS | 204 空 body + 行保留 |
| T-20 | PASS | 不级联（宿主不变） |
| T-21 | PASS | 无 restore/undelete/purge/batch/include_deleted |
| T-22 | PASS | 409 ACTIVE_CHILDREN_EXIST 无部分写入 |
| T-23 | PASS | 软删子后宿主 204 |
| T-24 | PASS | 两种交错不变式 0 行 |
| T-25 | PASS | FOR SHARE 持锁 + 未命中拒绝 |
| T-26 | PASS | 非空且被消费（注入可失败） |
| T-27 | PASS* | 显式声明 + 传入；静态 guard 可绕过（F006-T-02） |
| T-28 | PASS | 无平台接入 |
| T-29 | PASS | 不越界其它资源 / 位置 |
| T-30 | PASS | Empty vs Not Found；只返回宿主子集 |
| T-FE-01 | PASS | 三态 / Empty vs NotFound / error.code / 不重复守卫 |
| G-1 | PASS | 12 列；无 status/cluster_id；FK RESTRICT/RESTRICT；CHECK 空 |
| G-2 | PASS | partial unique predicate + 宿主索引（ORM + DB 双查） |
| G-3 | PASS | 表集合 guard 演进（加 virtual_machines / 0004），非删除 |
| G-4 | PASS | EXPECTED_GET_ROUTES 追加 VM 两条 |
| G-5 | PASS | BARE_METAL 检查非空且含 VM 检查（注入 FAILED） |
| G-6 | PASS | VM 检查显式声明 + 删除路径传入（G-6b 注入未检出，见 Defect） |
| G-7 | PASS | 无长度 / trim / 字符 / "/" 约束（注入 FAILED） |
| G-8 | PASS | 无 CASCADE / 无 collation / 无触发器（注入 FAILED） |
| G-9 | PASS | 唯一软删写入路径 allow-list 不变（注入第二路径 FAILED） |
| G-10 | PASS | 无 EAV / JSON(B) / 多态（注入 JSON 列 FAILED） |
| G-11 | PASS | MIGRATION_HEAD = 0004；可应用 / 可重复 / 可重建 |

---

## Database / Migration

- database 层 `true` 独立确认：新增 `0004_f006_virtual_machines`；`0001` / `0002` / `0003` **diff 为空**、未被改。
- 真实库 `csm_mig`：`upgrade head` ×2（第二次 no-op）、`current = 0004_f006_virtual_machines (head)`、`alembic check` 无漂移、`downgrade 0003` + `upgrade head` 重建成功。
- 直连 `information_schema` / `pg_constraint` / `pg_indexes` 与 Database Handoff V-1 ~ V-8 逐项一致（12 列、FK `RESTRICT`/`RESTRICT`、partial unique predicate `WHERE (deleted_at IS NULL)`、`ix_virtual_machines_bare_metal_id`、无 CHECK / collation / 触发器 / CASCADE）。
- 约束行为绕应用层验证（V-9 / V-10）：重复活跃 name → `23505`；无效宿主 → `23503`；大小写敏感；软删释放；空串 / 空白 / `/` 原样存取。

## Backend / API

- 5 端点行为经真实 uvicorn + 真实 PG 全量复核（116/116）：契约字段集合封闭、null 不省略、必填校验 400、宿主存在性 / 活跃性 404、全局唯一 409 + 稳定 code、Empty vs Not Found、按宿主过滤、PATCH 封闭、DELETE 204 行保留、无越界路由 / 参数、GET 无写副作用。
- 创建侧 `_lock_active_host` 对宿主行 `SELECT … WHERE deleted_at IS NULL FOR SHARE`；并发 T-24 / T-25 以真实 PostgreSQL 行锁验证两种交错与阻塞，孤立记录不变式 0 行。
- F014 接线：`app/bare_metals/deletion.BARE_METAL_ACTIVE_CHILD_CHECKS = (has_active_virtual_machines,)`，被 `app/bare_metals/service.py::delete_bare_metal` 消费；宿主有活跃 VM → 409 无部分写入。
- 删除委托系统内唯一软删路径 `app/deletion/service.soft_delete()`；VM 模块无第二写入路径（G-9 注入可失败）。
- **未发现任何 AC 层面的后端功能违约**；但 guard 演进存在削弱（见 Defects）。

## Frontend

- `typecheck` 0；`test` 242 passed（20 文件）；`build` 成功。
- 列表页 `VirtualMachineListPage`：`loading / empty / error / content` 四态互不相同；Empty（200 + `items==[]`）与 Not Found（宿主 404 → ErrorState `NOT_FOUND`）可区分；删除二次确认 + 提交中 Loading 防重复；登记入口。
- 详情页 `VirtualMachineDetailPage`：独立 `not-found` 态；展示全部 11 字段，六可选字段 null 渲染「—」；编辑仅六字段，`name` / `bare_metal_id` 无输入；无状态展示 / 编辑。
- 错误一律按 `error.code`（必要时 `details[].code`）分支；组件测试使用「与展示无关」的 message 证明前端不解析 message。
- 未重复实现业务守卫：空 name、重复 name、宿主存在性、删除守卫均直接提交由后端裁决（组件测试断言「仍提交」「删除入口不预判」）。
- 真实 API client 对接真实后端通过（见摘要 7）。
- 未发现 FRONTEND 缺陷。

## Integration

**真实前后端集成 = PASS（实际执行，非 Mock / Fixture）**：

1. 真实 uvicorn（真实 PG `csm_api`）+ 原始 httpx：116 项断言全部通过。
2. **前端真实 API client** + happy-dom 真实 HttpOnly 会话 Cookie：未认证 401 → 登录 → Empty → 201 → 409 → 404 → PATCH → DELETE 204 → 404 → 软删后重登记，临时探针 1/1 通过，运行后删除。

---

## Defects

### F006-T-01 — F009/F002 边界 guard 由「全 OpenAPI 扫描」收窄为「仅本模块」，跨模块越界路由覆盖被实质削弱（MEDIUM）

- **ID**：F006-T-01
- **Severity**：MEDIUM
- **Layer**：Backend / Test guards（`tests/test_cluster_views_guards.py`、`tests/test_bare_metals_api.py`）
- **Location**：
  - `tests/test_cluster_views_guards.py::test_g009_2_no_forbidden_resource_tokens_in_any_path`：由 `_openapi()["paths"]` 全量扫描改为 `cluster_views_router.routes` 单模块扫描。
  - `tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns`：由 `path.startswith("/api/")` 全量扫描改为 `path.startswith("/api/bare-metals")`。此改动后断言恒真（任何 `/api/bare-metals*` 路径都不会以 `nic/ip/vm/virtual/container/service` 开头），实际已成失效测试。
- **复现步骤**：
  1. 临时新增一条越界路由（如 `POST /api/containers`）挂到 `app.main`（非 cluster_views 模块）；
  2. 运行 `tests/test_structure_guard.py tests/test_auth_guards.py tests/test_cluster_views_guards.py tests/test_bare_metals_guards.py tests/test_virtual_machines_guards.py tests/test_deletion_guards.py` 及 F002/F006 的 T-29 边界测试。
- **期望**：越界资源路由（非 GET）应被跨模块边界 guard 检出并失败。
- **实际**：**68 项 guard 全部通过**，无任何 guard 检出该越界 `POST /api/containers`；已逐字节还原注入（`git status` 为空）。以原逻辑重建扫描：`OLD G-009-2 offenders: ['/api/virtual-machines/{virtual_machine_id}', '/api/virtual-machines', '/api/containers']`、`OLD T-29 offenders: [...] '/api/containers'`——即收窄前会命中，收窄后漏检。
- **独立判定**：**构成跨模块守卫覆盖的实质削弱。** 使测试通过的最小必要改动应是「从 token/prefix 集合中移除已成为合法资源的 `virtual-machine`/`vm`/`virtual`，保留对全部 `/api/*` 路径的 nic/ip/container/service 扫描」；实际却把扫描范围整体收窄到本模块，导致其它模块新增越界 **非 GET** 路由（GET 仍由 `EXPECTED_GET_ROUTES` 全局覆盖）不再被任何 guard 发现。
- **影响**：产品级规则「不越界到其它资源」的回归防线削弱；V1 内无功能性影响（当前无越界路由）。
- **Owner**：backend（F006 实现对 `tests/**` 的演进负责）
- **依据**：Architecture Handoff REQUIRED #10「既有 guard 必须演进而非删除」、问题 9「无越界资源 guard」。

### F006-T-02 — VM 删除路径「真实传入活跃子检查」静态 guard 可被绕过（LOW）

- **ID**：F006-T-02
- **Severity**：LOW
- **Layer**：Backend / Test guards
- **Location**：`tests/test_virtual_machines_guards.py::test_g6_t27_vm_delete_path_passes_active_child_checks`（同类：`tests/test_virtual_machines_guards.py::test_t26_bare_metal_delete_path_consumes_declared_checks`）
- **复现步骤**：临时从 `backend/app/virtual_machines/service.py` 删除 `from … import VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 与 `active_children=VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS,` 实参，仅保留 docstring 中的名字；运行该 guard。
- **期望**：guard 失败（常量未被真实传入 `soft_delete`）。
- **实际**：guard **通过**——断言仅检查源码子串 `"soft_delete(" in source` 与 `"VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS" in source`，而该名字仍出现在模块 docstring 中。注入已逐字节还原。
- **影响**：仅削弱回归保护；实现当前确实显式传入常量（`soft_delete(..., active_children=VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS)`），AC-29 功能语义满足，无运行时缺陷。
- **建议**：改为 AST 检查 `soft_delete` 调用含 `active_children` 关键字并解析到该常量（与 F014 已知「静态扫描器 AST 化」同源）。
- **Owner**：backend

### F006-T-03 — `delete_bare_metal` docstring 陈述已过期（LOW / NOTE）

- **ID**：F006-T-03
- **Severity**：LOW
- **Layer**：Backend（注释）
- **Location**：`backend/app/bare_metals/service.py::delete_bare_metal` docstring：「（`BARE_METAL_ACTIVE_CHILD_CHECKS`，当前显式空元组）」
- **复现步骤**：阅读该 docstring，并读取 `app/bare_metals/deletion.py`（现为 `(has_active_virtual_machines,)`）。
- **期望**：注释与实现一致。
- **实际**：注释仍写「显式空元组」，F006 已使其非空。仅文档漂移，无功能影响。
- **Owner**：backend

**除上述 3 项外，未发现 BLOCKER / HIGH / PRODUCT / ARCHITECTURE / DATABASE / FRONTEND 缺陷；未发现任何 AC 功能性违约。**

---

## Unverified Areas

1. **浏览器级前端 E2E / 视觉 / 真实 DOM**：无浏览器自动化环境；前端行为经 vitest（happy-dom）组件测试与真实 API client 集成验证，未在真实浏览器观察渲染 / 网络 / 视觉。
2. **多 uvicorn worker / 跨进程并发压测**：并发端到端以独立连接 / 线程验证行锁协议，未做多 worker 压测（无产品需求，V1 单机内网）。
3. **静态 guard 对动态 SQL / 动态路由构造的穷举覆盖**：承 F014 已知残余风险；本次已证明 VM 删除路径 guard 可绕过（F006-T-02）。
4. **VM 自身活跃子检查 409 分支的真实触发**：当前 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 为空，该分支在本 Feature 内不可达（契约 §3.5 明示）；未构造非空注入下的端到端 409 行为断言（功能语义由 `soft_delete` 既有 F014 测试覆盖）。
5. **全局非 GET 越界路由 guard 的缺失**：见 F006-T-01，属已发现缺陷而非未验证。

## Test Status

`RETURN TO IMPLEMENTATION`

依据：AC-01 ~ AC-32 全部有结果并全部满足功能语义；真实前后端集成已实际执行；工程门禁全绿（ruff / format / 全量 pytest 400 / 前端 typecheck + test 242 + build）。但本 Feature 对既有边界 guard 的处理构成跨模块覆盖的**实质削弱**（F006-T-01，MEDIUM，经对抗注入证明：新增越界 `POST /api/containers` 后 68 项 guard 全部通过），且 VM 删除路径静态 guard 可被绕过（F006-T-02，LOW）。二者与 Architecture REQUIRED #10「既有 guard 必须演进而非删除」不符，需实现方修复后再审。**无 BLOCKER / HIGH，无功能性缺陷。**

---

## Test Handoff

### Status

`RETURN TO IMPLEMENTATION`

### Verified

- AC-01 ~ AC-32 全部 PASS（功能语义）；无 FAIL / BLOCKED / NOT TESTED。
- Architecture Test Work T-01 ~ T-30 / G-1 ~ G-11 / T-FE-01 全部 PASS（G-6 见 F006-T-02）。
- 数据库：`virtual_machines` 12 列 / FK RESTRICT / partial unique predicate / 无 CHECK / 无 CASCADE / 无触发器 / 无 COLLATE 与 Database Handoff 一致；`0001`~`0003` 基线未改；migration 可应用 / 可重复 / 可重建；`alembic check` 无漂移。
- 后端：5 端点契约行为、全局唯一、Empty vs Not Found、按宿主过滤、PATCH 封闭、DELETE 204 行保留、无越界 / 无 status / 无 cluster_id；创建侧 `FOR SHARE` + 并发不变式 0 行；F014 端到端 409 / 204。
- 前端：三态互异、Empty vs Not Found 可分、`error.code` 分支、不解析 message、不重复实现业务守卫；typecheck / test(242) / build 全绿。
- 真实前后端集成实际执行（真实 uvicorn + 真实 PG + 前端真实 client）。
- G-1 ~ G-11 中 11 条经对抗注入证明真实可失败并逐字节还原；G-6 删除路径注入未被检出（F006-T-02）。
- 独立判定：F009 `test_g009_2` 与 F002 `test_t29` 的收窄**构成跨模块守卫覆盖的实质削弱**（注入证据见 F006-T-01）。

### Not Verified

- 浏览器级 E2E / 视觉 / 真实 DOM。
- 多 worker / 跨进程并发压测。
- 静态 guard 对动态构造的穷举覆盖（已发现 VM 删除路径 guard 可绕过）。
- VM 自身非空子检查 409 分支的真实触发（当前不可达）。

### Blocking Issues

- F006-T-01（MEDIUM，Backend/Test guards）：跨模块边界 guard 覆盖被削弱，需修复（恢复对全部 `/api/*` 的 nic/ip/container/service 非 GET 路由扫描，仅移除已合法化的 VM token）。

### Defect Owner

- F006-T-01（MEDIUM）→ backend
- F006-T-02（LOW）→ backend
- F006-T-03（LOW）→ backend

### 新增 / 修改文件

- 本次测试**未新增 / 未修改仓库内任何文件**：报告为唯一产出；临时集成脚本（`/tmp/f006-test/**`）、临时 vitest 探针（`frontend/tests/zzTmpF006Integration.spec.ts`）运行后已删除；对抗注入已逐字节还原，`git status --short` 为空。
- 未修改任何业务实现（`backend/app/**`、`backend/migrations/**`、`frontend/src/**`）或产品 / 架构 / 契约 / 数据库设计文档。

---

# Re-verification（修复复验）

> 复验角色：tester（独立）
> 复验日期：2026-09-18
> base `develop` = `f74e7ddbf369910e6f83b99758b672019b4fe4c9`
> 上一轮实现 HEAD = `5d87d207d92c06e2b8d0e7e34d0b7436064bf992`（其后 `03db90a` 计划检查点）
> 修复后 HEAD = `7844a173394a5249d9267598c1c76363dc6c5b5e`（`4ec20c5` 独立验收 + `7844a17` 修复）
> 复验范围：F006-T-01 / F006-T-02 / F006-T-03，并独立验证修复未削弱其它 guard。

原报告内容全部保留；本小节为追加。

## 修复差异（`git diff f74e7dd..7844a17 -- tests/... backend/app/bare_metals/service.py`）

| 文件 | 修复内容 |
|---|---|
| `tests/test_cluster_views_guards.py` | `BOUNDARY_TOKENS` **仅**移除已合法化的 `virtual-machine` / `virtual_machine`；`test_g009_2` 扫描范围**恢复为全部 OpenAPI path**（`_openapi()["paths"]`），注释明确非 GET 越界路由仍须检出 |
| `tests/test_bare_metals_api.py` | `forbidden_prefixes` = `(nic, ip, network-interface, network_interface, container, service)`（**仅**移除 `vm`/`virtual`，保留 `nic`/`ip`/`container`/`service` 并新增两种 `network-interface` 写法）；扫描范围**保持全部 `/api/*` path** |
| `tests/test_virtual_machines_guards.py` | 新增 AST 辅助 `_soft_delete_active_children_args`，`test_g6_t27_vm_delete_path_passes_active_child_checks` 与 `test_t26_bare_metal_delete_path_consumes_declared_checks` 改为断言 `soft_delete(...)` 调用中 `active_children=` 关键字**真实解析到常量** |
| `backend/app/bare_metals/service.py` | `delete_bare_metal` docstring 由「当前显式空元组」改为「F006 起包含『是否存在活跃 VirtualMachine』检查」 |

**功能性变更集**：`git diff 03db90a..7844a17 -- backend/app/` 仅含上述 docstring（零行为变更）。

## 环境

| 项 | 值 |
|---|---|
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 真实实例，socket `/tmp/f006-reverify/pgdata`，本次新建） |
| 测试库 | `csm_f006_rv`（pytest 每夹具重建）、`csm_mig_rv`（迁移 / schema 检查）、`csm_api_rv`（预留） |
| Node / npm | v24.14.0 / 11.9.0（Vitest 5.0.1） |
| ruff | 0.16.7 |

## F006-T-01 复验（跨模块边界 guard）→ **Re-verified**

**注入**：临时向 `backend/app/main.py`（**非** cluster_views / bare_metals 模块）追加 `POST /api/containers` 与 `POST /api/network-interfaces`，随后运行两条原判缺陷 guard：

```text
$ CSM_TEST_DATABASE_URL=...csm_f006_rv... .venv/bin/python -m pytest -q \
    "tests/test_cluster_views_guards.py::test_g009_2_no_forbidden_resource_tokens_in_any_path" \
    "tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns"
FAILED tests/test_cluster_views_guards.py::test_g009_2_no_forbidden_resource_tokens_in_any_path
FAILED tests/test_bare_metals_api.py::test_t29_no_other_resource_endpoints_or_columns
2 failed
```

T-29 报错明细证明其命中的是**跨模块越界路由**：

```text
AssertionError: F002 不得注册其它资源端点：['/api/network-interfaces', '/api/containers']
```

**通过**（`5d87d20` 旧的收窄实现下同一注入漏检：68 项 guard 全通过）。

**全局覆盖确认**：
- `test_g009_2`：`for path in _openapi()["paths"]`，遍历整个 OpenAPI 文档的全部 path，非单模块 `router.routes`。
- `test_t29`：`for path in paths if path.startswith("/api/") and path[len("/api/"):].startswith(prefix)`，遍历全部 `/api/*` path，非 `startswith("/api/bare-metals")`。

两条 guard 均恢复为跨模块全局扫描，仅合法化 VM token。

**还原**：`sha256sum backend/app/main.py` = `80d5d063…84`（注入前后一致），`git status --short` 为空。

## F006-T-02 复验（VM 删除路径静态 guard）→ **Re-verified**

**注入**：临时从 `backend/app/virtual_machines/service.py` 删除 `from app.virtual_machines.deletion import VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 与 `active_children=VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS,` 实参，仅保留 docstring 中的常量名（`grep` 确认文件中该名字只剩第 107 行 docstring）：

```text
$ CSM_TEST_DATABASE_URL=... .venv/bin/python -m pytest -q \
    "tests/test_virtual_machines_guards.py::test_g6_t27_vm_delete_path_passes_active_child_checks"
FAILED tests/test_virtual_machines_guards.py::test_g6_t27_vm_delete_path_passes_active_child_checks
tests/test_virtual_machines_guards.py:177: AssertionError
1 failed
```

失败点即 AST 断言第 177 行 `assert "VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS" in _soft_delete_active_children_args(source)`，证明「仅注释 / docstring 出现常量名」不再误判通过。

**还原**：`sha256sum backend/app/virtual_machines/service.py` = `b75fcae6…31`，`git status --short` 为空。

## F006-T-03 复验（docstring 漂移）→ **Re-verified**

`backend/app/bare_metals/service.py::delete_bare_metal` docstring 现为「…（`BARE_METAL_ACTIVE_CHILD_CHECKS`，F006 起包含『是否存在活跃 VirtualMachine』检查）并**显式传入**…」，与 `backend/app/bare_metals/deletion.py` 的 `BARE_METAL_ACTIVE_CHILD_CHECKS: tuple[ActiveChildCheck, ...] = (has_active_virtual_machines,)` 一致。文档漂移已消除。

## 修复未削弱其它 guard（独立验证）

1. **全量 tests diff 逐行核对**（排除本 Feature 新增文件）：`git diff f74e7dd..7844a17 -- tests/` 中被删行仅 15 行，全部为**受控演进**，无断言被净删除：
   - `MIGRATION_HEAD` / `alembic_current` / `EXPECTED_TABLES` / `Base.metadata.tables` / `table_names` 断言：`0003`→`0004`、表集合**追加** `virtual_machines`；
   - `BOUNDARY_TOKENS`：仅删 `virtual-machine` / `virtual_machine`（已合法资源）；
   - `forbidden_prefixes`：仅删 `vm` / `virtual`，`nic`/`ip`/`container`/`service` 保留并新增 `network-interface`/`network_interface`；
   - `BARE_METAL_ACTIVE_CHILD_CHECKS`：由 `== ()` **加强**为 `len(...) >= 1` 且必须含 `has_active_virtual_machines`（由 fail-open 改为 fail-closed）；
   - 其余为断言 message / 注释文本更新。
2. **抽查另一条被演进 guard 的真实可失败性**：临时把 `BARE_METAL_ACTIVE_CHILD_CHECKS` 改回 `()` 后：

```text
$ .venv/bin/python -m pytest -q \
    tests/test_bare_metals_guards.py::test_t22_bare_metal_active_child_checks_explicitly_declared \
    tests/test_virtual_machines_guards.py::test_g5_t26_bare_metal_active_child_checks_contain_vm_check
FAILED tests/test_bare_metals_guards.py::test_t22_bare_metal_active_child_checks_explicitly_declared
FAILED tests/test_virtual_machines_guards.py::test_g5_t26_bare_metal_active_child_checks_contain_vm_check
2 failed
```

   `sha256sum backend/app/bare_metals/deletion.py` = `7d141846…d4` 还原一致，`git status --short` 为空。
3. 结论：未发现修复把任何 guard 改成无法失败的形式，也未一并削弱其它 guard（另有 F006-T-01 注入的跨模块反证）。

## 工程门禁（真实执行）

```text
$ alembic upgrade head（真实 PG csm_mig_rv）→ 0001 → 0002 → 0003 → 0004_f006_virtual_machines
$ alembic current                            → 0004_f006_virtual_machines (head)
$ alembic upgrade head（重复）                → no-op
$ alembic check                              → No new upgrade operations detected.
$ CSM_TEST_DATABASE_URL=...csm_f006_rv... .venv/bin/python -m pytest -q
  400 passed, 2 warnings in 267.16s（无 skipped）
$ .venv/bin/ruff check backend tests          → All checks passed!
$ .venv/bin/ruff format --check backend tests → 103 files already formatted
$ cd frontend && npm run typecheck            → exit 0
$ npm run test                                → Test Files 20 passed，Tests 242 passed
$ npm run build                               → vite build 成功（dist/assets/index-B8mECZbk.js 1,049.38 kB，仅 chunk 体积告警）
```

## 集成（Integration）

修复 commit（`03db90a..7844a17`）对 `backend/app/**` 的唯一改动是 docstring，**零功能性变更**；因此上一轮已实际执行的真实前后端集成行为不受影响。本轮以真实 PostgreSQL 重新执行了后端全量套件（`400 passed`，含 F006 API / 约束 / 并发），前端 `typecheck + test(242) + build` 全绿。跨进程 uvicorn + 前端真实 client 探针**未在本轮重跑**（无功能性差异，不构成新的验证面）。

## 复验结论

| Defect | Severity | 复验结果 |
|---|---|---|
| F006-T-01 跨模块边界 guard 收窄 | MEDIUM | **Re-verified / Fixed** — 全局扫描已恢复，注入越界 `POST /api/containers` 后两条 guard 均 FAILED |
| F006-T-02 VM 删除路径静态 guard 可绕过 | LOW | **Re-verified / Fixed** — AST 检查真实解析 `active_children=` 实参，仅 docstring 出现常量名时 FAILED |
| F006-T-03 `delete_bare_metal` docstring 过期 | LOW | **Re-verified / Fixed** — 注释与实际 `BARE_METAL_ACTIVE_CHILD_CHECKS` 内容一致 |

无新增缺陷；无 BLOCKER / HIGH；修复未削弱其它 guard。

## New Test Status

`READY FOR REVIEW`

依据：上一轮 3 个缺陷全部独立复验修复（每项均以真实注入证明 guard 可失败并逐字节还原，`git status` 干净）；AC-01 ~ AC-32 在上一轮已全部 PASS 且功能语义不变（修复对 `backend/app/**` 仅 docstring）；全量后端 `400 passed`（无 skipped）、ruff / format 全绿、前端 `typecheck + 242 passed + build` 全绿；无 BLOCKER / HIGH / 必须修复的 MEDIUM，无新增缺陷。

---

GIT: NONE
