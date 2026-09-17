# Test Report — F007 Container 资源模型与登记

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验收）
> Date: 2026-09-17
> Feature: F007（E03，P1，`depends_on: [F006, F002]` 均 DONE）
> 分支：`feature/F007-container`
> 实现基线 HEAD = `e5d0b75`（实现提交 `0fb1419`；其后 `81a603e` / `e5d0b75` 为计划元数据提交）
> layers：database / backend / frontend 均 true；database_design / backend / frontend 均 COMPLETE

---

## Feature

Container 资源模型与登记（F007）— 长期服务型 Container 实例的人工登记、查询、可选字段维护与逻辑删除，以及 **Container → 运行载体（BareMetal 或 VirtualMachine，恰好一个）** 的多态必选关系落地，与 F014 双载体父删子拦端到端。

## Test Basis

- `AGENTS.md`、`docs/project/git-workflow.md`、`.pi/skills/resource-domain/SKILL.md`
- `docs/product/handoffs/f007-container.md`（AC-01 ~ AC-44）
- `docs/architecture/f007-container-handoff.md`（§1 多态载体、§7 guard、§10 演进清单、Verification Strategy）
- `docs/api/f007-container.md`（**READY**，唯一权威）
- `docs/database/f007-container-migration.md`（§7 验证清单）
- ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005（均 `ACCEPTED`）
- 格式先例：`docs/test-reports/f004-network-interface.md`

---

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 真实实例，数据目录 `/tmp/f007-test/pgdata`，本次新建，与协调器的 `/tmp/f007-pg` 不同路径） |
| collation | `datcollate = zh_CN.UTF-8`；**实测 `select 'abc' = 'ABC'` → `f`（大小写敏感）** |
| 测试库 | `csm_test` / `csm_f007b`（F007 专项）、`csm_conc`（并发隔离）、`csm_full`（全量）、`csm_mig`（迁移 / 直连 schema）、`csm_api`（真实 uvicorn 集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn`（真实 PG `csm_api`）：`127.0.0.1:8907` |
| Node / npm | v24.14.0 / 11.9.0（Vitest 5.0.1，happy-dom） |
| ruff | 0.16.7 |

**是否全新**：PG 实例、六个测试库、管理员账号、集成探针均为本次测试新建；pytest 每夹具 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 重建。**实现方结论未被复用。**

**测试基础设施说明（非产品缺陷）**：首次把全量 suite 与专项 suite 指向同一 `csm_test` 库**并行**运行，导致 `DROP SCHEMA` 竞态使并发用例报 `alembic upgrade head failed`。改为**每类运行独立数据库**后复现全绿；以下结果均来自隔离运行。

---

## 独立执行摘要（真实命令与关键输出）

```text
# 全量后端（隔离库 csm_full）
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_full?host=/tmp/f007-test/pgdata" \
  .venv/bin/python -m pytest -q
798 passed, 2 warnings in 805.24s (0:13:25)          # 无 skipped

# F007 专项（独立库 csm_f007b，重跑两次）
$ ... pytest -q tests/test_containers_api.py tests/test_containers_guards.py \
    tests/test_containers_concurrency.py tests/database/test_containers_constraints.py \
    tests/database/test_containers_schema_guard.py
111 passed, 2 warnings in 129.17s

# 并发专项（隔离库 csm_conc）
$ ... pytest tests/test_containers_concurrency.py -v
6 passed   # AC-36×2 / AC-37×2 / AC-38×2

# lint
$ .venv/bin/ruff check backend tests           → All checks passed!
$ .venv/bin/ruff format --check backend tests  → 146 files already formatted

# 迁移（真实库 csm_mig）
$ alembic upgrade head        → 0001 → ... → 0007_f007_containers
$ alembic current             → 0007_f007_containers (head)
$ alembic upgrade head        → no-op（幂等）
$ alembic check               → No new upgrade operations detected.
$ alembic downgrade 0006_f005_ip_addresses → 成功（containers 表消失：count=0）
$ alembic upgrade head        → 重建，current 回到 0007 (head)

# 前端
$ cd frontend && npm run typecheck → exit 0
$ npm run test (第 1 次) → Test Files 32 passed / Tests 460 passed
$ npm run test (第 2 次) → Test Files 32 passed / Tests 460 passed
$ npm run build → vue-tsc + vite build 成功（仅 chunk 体积告警）
```

**独立探针结果**：

```text
直连 DB 探测（/tmp/f007-test/dbprobe.py，绕过应用层，csm_mig）      → 30 passed / 30
真实 HTTP 探测（/tmp/f007-test/httpprobe.py，真实 uvicorn + PG）    → 43 passed / 43
真实前端 client 集成（临时 vitest 探针，运行后删除）                → 8 passed / 8
对抗注入（8 组，逐条还原）                                          → 全部被对应 guard 检出
```

---

## Acceptance Criteria Mapping

证据代号：`TGT`=F007 专项 111；`FULL`=全量 798；`DB`=直连 DB 探针 30/30；`HTTP`=真实 uvicorn 探针 43/43；`FEI`=前端真实 client 集成 8/8；`FE`=前端 460×2 + typecheck + build；`INJ`=对抗注入。

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** BM 载体登记成功，字段集合恰 10 | TGT `test_create_returns_closed_field_set[BARE_METAL]` + HTTP + DB | **PASS** | HTTP：字段键恰 10，无 `deleted_at`/`status`/`cluster_id`/`bare_metal_id` |
| **AC-02** VM 载体登记成功，同字段集合 | 同上 `[VIRTUAL_MACHINE]` | **PASS** | `carrier_type=VIRTUAL_MACHINE` → 201，字段集合同 |
| **AC-03** `name` 必填 → 400 field=name | TGT + HTTP | **PASS** | 缺失 / 非串 → 400 `VALIDATION_ERROR` + `details[].field=="name"`，无写入 |
| **AC-04** 载体必填（都不给 / 缺一） | TGT + HTTP | **PASS** | `field` 指向 `carrier_type`/`carrier_id`；无写入 |
| **AC-05** 拒绝多载体（两者都给 / 列表） | TGT + HTTP | **PASS** | schema 封闭：`bare_metal_id`/`virtual_machine_id`/`carriers` 额外字段 → 400 |
| **AC-06** 拒绝其它资源类型为载体 | TGT + HTTP | **PASS** | `carrier_type=CLUSTER`/`SERVICE`、`cluster_id`/`service_id`/`nic`/`ip`/`rack` → 400 |
| **AC-07** 类型与标识必须一致 | HTTP + TGT | **PASS** | `carrier_type=VIRTUAL_MACHINE, carrier_id=<BM-only id=2>` → 404 `NOT_FOUND`，无写入、非 5xx |
| **AC-08** 载体必须存在且活跃 | TGT + HTTP | **PASS** | 不存在 / 已软删（BM 与 VM）→ 404 `NOT_FOUND`，`details==[]` |
| **AC-09** 可选字段缺失不阻断（返回 null） | TGT + HTTP | **PASS** | 四字段均存在且为 `null`（非省略） |
| **AC-10** 纯文本原样往返 | TGT + HTTP | **PASS** | `容器-甲` / `registry/nginx:1.25` / `8 vCPU` / `4G` 原样读出 |
| **AC-11** 未定义约束不实现 | DB + TGT + HTTP | **PASS** | DB 直插 `""` / `"  padded  "` / `"has/slash"` 全部接受；**表恰 1 个 CHECK**（`ck_containers_carrier_exactly_one`），无隐性约束 |
| **AC-12** 同载体内唯一，保存前 409 | TGT + HTTP + DB | **PASS** | 409 `CONFLICT` + `details[]={field:name,code:DUPLICATE}`；DB 直插 → `23505` |
| **AC-13** 跨载体类型可重名 | DB + TGT | **PASS** | BM 与 VM 同名 `web` 均成功 |
| **AC-14** 同类型不同标识可重名 | DB + TGT + HTTP | **PASS** | 同 Cluster 下 B1/B2 各 `web` → 201 |
| **AC-15** 跨类型同数值 id 不冲突（**核心不变式**） | **DB（绕应用层）** | **PASS** | `OVERRIDING SYSTEM VALUE` 令 BM id=5 与 VM id=5，同名 `web` **同时存在 2 行**；机制：CHECK 保证另一载体列为 NULL，而唯一索引中 **NULL 互不相等**，故两条 partial unique index 互不干扰（证据：BM 行 `virtual_machine_id IS NULL`） |
| **AC-16** 不与 R-VM-004 混用 | TGT `test_same_name_on_bare_metal_and_its_vm_succeeds` | **PASS** | VM 名 `web` 与该 VM 上 Container `web` 均 201；Container 无全局唯一 |
| **AC-17** 大小写敏感 | DB + TGT + HTTP | **PASS** | 同载体 `web` 与 `WEB` 共存；`select 'abc'='ABC'`=false；无 `lower()`/`COLLATE` |
| **AC-18** 保存前阻止，DB 最终权威 | DB + HTTP | **PASS** | API 409；绕应用层直插重复活跃 `(载体,name)` → `23505`（BM 与 VM 各验） |
| **AC-19** 软删释放唯一性，旧行不改写 | DB + TGT + HTTP | **PASS** | 软删后可重登记同名；旧行 `deleted_at` 逐字节不变；总行数 2 |
| **AC-20** 唯一性边界是载体而非 Cluster | DB + TGT + HTTP | **PASS** | 同 Cluster 两台 BM 各 `web` → 201 |
| **AC-21** 不存 `cluster_id` / Cluster 维度 | DB + TGT + HTTP + FULL | **PASS** | 表 11 列无 `cluster_id`/`cluster`；schema / 响应 / query 均无；源码无 token |
| **AC-22** 归属仅由载体表达、不持久化 | TGT + HTTP | **PASS** | 详情暴露 `carrier_type`+`carrier_id`；无任何 Cluster 归属字段 |
| **AC-23** 无状态 | DB + TGT + HTTP | **PASS** | 表 / 请求 / 响应 / 端点 / query 均无 `status`/`state`；`status` 入 body → 400 |
| **AC-24** 列表、分页、Empty | TGT + HTTP | **PASS** | `{items:[],total:0,page:1,page_size:50}` 非 404；分页 400 边界校验 |
| **AC-25** 详情 Not Found（不区分） | TGT + HTTP | **PASS** | 不存在与已软删均 404 `NOT_FOUND` |
| **AC-26** 按载体读取，Empty vs Not Found，两类型均成立 | TGT + HTTP + FEI | **PASS** | 载体不存在/已删 → 404；存在但空 → 200 `items==[]`；只返回该载体；仅给一参数 → 400；BM 与 VM 均验 |
| **AC-27** 列表/详情排除已删 | TGT | **PASS** | 绕应用层预置软删行 → 不在 `items`/`total`/按载体结果；按 id → 404 |
| **AC-28** 可选字段可更新 | TGT + HTTP + FEI | **PASS** | PATCH → 200 新值；`null` 清空；缺省不变；再读一致 |
| **AC-29** 更新 schema 封闭 | TGT + HTTP | **PASS** | `name`/载体字段/`id`/`deleted_at`/`cluster_id`/`status` → 400；空 body → 400 |
| **AC-30** Container 逻辑删除 | TGT + HTTP | **PASS** | DELETE → 204 空体；行仍物理存在且 `deleted_at` 非空；重复删除 404 |
| **AC-31** 删除不级联（两类型） | TGT | **PASS** | 载体逐字段（含 `updated_at`/`deleted_at`）不变；其它行不变 |
| **AC-32** 无 restore/undelete/purge/批量/include_deleted | TGT + HTTP + FULL | **PASS** | OpenAPI 恰 2 path / 5 method；无相关 token / 参数 |
| **AC-33** BM 有活跃 Container → 409，BM `deleted_at` 仍 NULL | HTTP + TGT + DB | **PASS** | `DELETE /api/bare-metals/{id}` → 409 `ACTIVE_CHILDREN_EXIST`；DB 实测 `bm1_deleted_at_is_null=true`（无部分写入） |
| **AC-34** VM 有活跃 Container → 409，VM `deleted_at` 仍 NULL | HTTP + TGT + DB | **PASS** | `DELETE /api/virtual-machines/{id}` → 409；DB 实测 `vm1_deleted_at_is_null=true` |
| **AC-35** 软删全部 Container 后载体可删（两类型） | TGT `test_carrier_deletable_after_container_soft_deleted` | **PASS** | 软删 Container 后 BM / VM 均 DELETE 204 |
| **AC-36** 并发孤立记录 = 0（BM 载体） | 并发专项 + 实时 HTTP 库 | **PASS** | 先建后删 / 先删后建两种交错；不变式 SQL = **0 行**；`csm_api` 全操作后 `bm_orphans=0` |
| **AC-37** 并发孤立记录 = 0（VM 载体） | 并发专项 + 实时 HTTP 库 | **PASS** | 同上；`vm_orphans=0` |
| **AC-38** 创建对载体行取共享锁 | 并发专项 `test_ac38_*`（2 例） | **PASS** | 载体行被 `FOR UPDATE` 时创建阻塞；持锁期间他人 `FOR UPDATE NOWAIT` 失败；未命中 → 拒绝且不留无主 Container |
| **AC-39** BM 检查点含 VM+NIC+Container 且被消费 | TGT guard + **INJ** | **PASS** | 元组含三检查；删除路径 AST 真实传入；**注入删除 Container 检查 → 2 guard FAILED** |
| **AC-40** VM 检查点非空且含 Container 且被消费 | TGT guard + **INJ** | **PASS** | 由显式空元组演进为非空含 Container；AST 真实传入；**注入清空 → 2 guard FAILED** |
| **AC-41** Container 自身检查点显式声明且被传入 | TGT guard + **INJ** | **PASS** | `CONTAINER_ACTIVE_CHILD_CHECKS = ()` 显式；AST 真实传入；**注入 `tuple()` / 删除实参 → guard FAILED** |
| **AC-42** 无 K8s / Docker / 运行时 | TGT guard + 全局 DB | **PASS** | 全局 OpenAPI path 与容器模块源码无 forbidden token；全库无 CASCADE / 触发器 / 生成列 / 额外 extension |
| **AC-43** 不越界到其它资源 | DB + TGT guard + 全局 DB | **PASS** | `containers` 仅两条 FK（→ `bare_metals`/`virtual_machines`），无 Cluster/NIC/IP/Service/位置结构；无越界端点 |
| **AC-44** 前端三态 / Empty vs NotFound / `error.code` / 不重复守卫 | FE + FEI | **PASS** | 列表 `data-state` ∈ {loading,empty,error,content}，详情 ∈ {loading,not-found,error,content}；404 渲染「未找到资源」与 Empty「该载体暂无容器」**状态与文案均不同**；按 `error.code`（+`details[].code`）分支，唯一 `.message` 用法为展示；真实 client 集成 8/8 |

**AC-01 ~ AC-44 全部 PASS，无 FAIL / BLOCKED / NOT TESTED。**

---

## 对抗注入记录（注入 → 期望 → 实际 → 还原）

每组均先 `cp` 备份、注入、运行对应 guard、`cp` 回写并比对 `sha256`；结束后 `git status --short` 为空。

| # | 注入内容 | 目标 guard | 期望 | 实际 | 还原 |
|---|---|---|---|---|---|
| A | `main.py` 追加未批准 `POST /api/services` | `test_g009_2_no_forbidden_resource_tokens_in_any_path`、`test_t29` | FAIL | **FAILED**（g009_2 报 `['/api/services']`；t29 报同）；`BOUNDARY_TOKENS=("service",)` 保留、`for path in _openapi()["paths"]` **全局扫描未收窄** | ✅ sha256 一致 |
| B | `ContainerRead` 加 `status` 字段 | `test_g1_container_read_schema_is_closed` | FAIL | **FAILED** | ✅ |
| C | `ContainerRead` 加 `cluster_id` 字段 | 同上 | FAIL | **FAILED** | ✅ |
| D | `containers/repository.py` 加第二处 `deleted_at` 写入 | `test_g8_container_module_writes_no_deleted_at`、`test_g8_deleted_at_writer_allowlist_unchanged` | FAIL | **2 FAILED**（allow-list 变为 `{repository.py, deletion/service.py}`） | ✅ |
| E | 从 `BARE_METAL_ACTIVE_CHILD_CHECKS` 删除 Container 检查 | `test_g10_active_child_checks_are_wired`、vm `test_g5_t26` | FAIL | **2 FAILED** | ✅ |
| F | `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 置空 | `test_g10_active_child_checks_are_wired`、vm `test_g6_t27` | FAIL | **2 FAILED** | ✅ |
| G | `CONTAINER_ACTIVE_CHILD_CHECKS` 改为 `tuple()`（非显式） | `test_g10_active_child_checks_are_wired` | FAIL | **FAILED** | ✅ |
| H | `containers/service.py` 删除 `active_children=` 实参 | `test_g10_delete_paths_consume_declared_checks`（AST） | FAIL | **FAILED** | ✅ |

注入 A 特别确认：`service` token 仍在扫描内，扫描范围仍为**全部 OpenAPI path**（未收窄到单模块），非 GET 越界路由可被检出。

---

## Database / Migration

- `containers` 列集合**恰 11 列**；无 `status` / `state` / `cluster_id` / `carrier_type` 判别列（绕应用层 `information_schema` 断言）。
- 约束恰 4：`pk_containers`、`ck_containers_carrier_exactly_one`（`num_nonnulls(...)=1`）、`fk_containers_bare_metal`、`fk_containers_virtual_machine`（均 `confdeltype='r'`/`confupdtype='r'`，**RESTRICT**）。
- 索引恰 4：两条 partial unique（predicate `deleted_at IS NULL`，无 `lower()`）+ 两条载体普通索引。
- 无列级 collation、无触发器、无生成列、无 JSON/JSONB、无额外 extension；**全库 `confdeltype='c'` 外键数 = 0**。
- 约束行为（绕应用层）：重复活跃 → `23505`；0 / 2 个载体 → `23514`；不存在载体 → `23503`；**物理删除有活跃 Container 的载体 → `23503`（证明 RESTRICT 而非 CASCADE）**；空串 / 空白 / `/` 原样接受。
- 迁移：`upgrade head` 幂等；`downgrade 0006` 可逆（表消失）后 `upgrade head` 重建；`alembic check` 无漂移；**`0001`–`0006` 未改**（实现提交仅新增 `0007_f007_containers.py`，工作区 diff 为空）。

## Backend / API

- 真实 uvicorn + 真实 PG：43/43 断言通过；字段集合封闭、400/404/409/401 信封逐字段断言、Empty vs Not Found、按载体过滤（两类型）、PATCH 封闭、DELETE 204 行保留、无越界路由/参数。
- 创建侧对**被选中载体行** `SELECT … WHERE deleted_at IS NULL FOR SHARE`；删除侧对自身行 `FOR UPDATE` 再查活跃子；并发两种交错孤立记录不变式 = 0。
- 删除委托系统内唯一软删路径 `app.deletion.soft_delete`；容器模块无第二写入路径（注入 D 反证）。
- DB `23505`/`23514`/`23503` 为最终权威，产品路径经 `FOR SHARE` 预检返回 404，永不 5xx。

## Frontend

- `typecheck` 0；`build` 成功；`npm run test` **连续 2 次 460 passed**（无偶发失败，`monotonic-date-now` setup 生效）。
- 列表 / 详情三态互异；Empty 与 Not Found 状态与文案可区分；错误按 `error.code`（+`details[].code`）分支；唯一 `.message` 引用为展示。不重复实现业务守卫（载体存在性 / 唯一性 / 删除守卫均交由后端裁决）。

## Integration

**真实前后端集成 = PASS（实际执行，非 Mock / Fixture）**：

1. 真实 uvicorn（真实 PG `csm_api`）+ 原始 httpx：43 项断言，覆盖登记 / 唯一性 / 404 / 409 / Empty / PATCH / DELETE / 越界。
2. **前端真实 API client**（`containers.ts` + `http.ts` + `auth.ts`）+ 真实 HttpOnly 会话 Cookie → 真实 uvicorn：未认证 401 → 登录 → Empty → 404 Not Found → 201（字段恰 10）→ 409 DUPLICATE → VM 载体重名 201 → PATCH → DELETE 204 → 404 → BM 删除 409 `ACTIVE_CHILDREN_EXIST`；临时探针 **8/8 通过**，运行后删除。

---

## Defects

**None.**

无 BLOCKER / HIGH / MEDIUM / LOW。未发现任何 AC 功能性违约；guard 演进均为**必要且增演**（仅移除已合法化的 `container` token、保留 `service`、空元组断言演进为非空、表集合增表），未削弱既有 F004/F006/F009 guard（注入 A 反证全局扫描保持）。

---

## Unverified Areas

1. **浏览器级 E2E / 视觉 / 真实 DOM**：无浏览器自动化环境；前端行为经 vitest（happy-dom）组件测试 + 真实 API client 集成验证，未在真实浏览器观察渲染 / 网络 / 视觉。
2. **多 uvicorn worker / 跨进程并发压测**：并发以多连接 / 线程验证行锁协议，未做多 worker 压测（无产品需求，V1 单机内网）。
3. **Container 自身活跃子检查 409 分支的真实触发**：`CONTAINER_ACTIVE_CHILD_CHECKS` 为空，该分支在本 Feature 内不可达（契约明示）；仅以静态 / AST guard + 注入证明声明与传入真实可失败，未构造非空注入下的端到端 409 断言（由 `soft_delete` 既有 F014 测试覆盖）。
4. **静态 guard 对动态 SQL / 动态路由构造的穷举覆盖**：承 F014 已知残余风险；本次 8 组注入均以静态 / DB 注入证明可失败，对运行期动态构造无覆盖。

---

## Test Status

`READY FOR REVIEW`

依据：AC-01 ~ AC-44 全部有结果并全部 **PASS**（无 FAIL / BLOCKED / NOT TESTED）；真实前后端集成已实际执行；数据库结构 / Migration / 约束与 Database Handoff 一致；后端全量 `798 passed`（无 skipped）、F007 专项 111 passed（重跑两次）、并发 6 passed（隔离库）、ruff / format 全绿；前端 `typecheck + 460×2 passed + build` 全绿；8 组对抗注入全部被对应 guard 检出并逐字节还原；NQ-8 文档漂移（`domain-model.yaml`、`domain-model.md`、`csm-v1-schema-design.md`、`f012-baseline-migration.md`）已同步。**无任何缺陷。**

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-44 全部 PASS；无 FAIL / BLOCKED / NOT TESTED。
- 数据库：11 列 / 4 约束（含唯一 CHECK）/ 4 索引 / FK RESTRICT / 无 CASCADE / 无触发器 / 无生成列 / 无 COLLATE；`0001`–`0006` 未改；migration 可应用 / 可重复 / 可重建；`alembic check` 无漂移。
- **AC-15 承重不变式**：绕应用层直连 DB，证明 BM id=5 与 VM id=5 同名 Container 同时存在，并给出机制（CHECK → 另一列 NULL；唯一索引中 NULL 互不相等）。
- 后端：真实 HTTP 契约行为、`FOR SHARE` 载体锁、并发孤立记录不变式 0 行（BM 与 VM）；F014 双载体端到端 409 / 204，载体 `deleted_at` 仍 NULL。
- 前端：三态互异、Empty vs Not Found 可分、`error.code` 分支、不解析 message、不重复实现业务守卫；连续 2 次 460 passed + build 成功。
- 真实前后端集成实际执行（真实 uvicorn + 真实 PG + 前端真实 client）。
- 8 组对抗注入（含未批准 `POST /api/services` 全局边界检出、`ContainerRead` 字段封闭、第二处 `deleted_at` 写入、三处活跃子检查与删除路径消费）全部证明 guard 可失败并逐字节还原。

### Not Verified

- 浏览器级 E2E / 视觉 / 真实 DOM。
- 多 worker / 跨进程并发压测。
- Container 自身非空子检查 409 分支的真实触发（当前不可达）。
- 静态 guard 对动态构造的穷举覆盖。

### Blocking Issues

- None.

### Defect Owner

- None.

### 新增 / 修改文件

- 本次测试**未新增 / 未修改仓库内任何业务文件**：报告为唯一产出；临时前端集成探针（`frontend/tests/zzTmpF007Integration.spec.ts`）运行后已删除；8 组对抗注入均已逐字节还原（`sha256` 比对一致），`git status --short` 为空。
- 临时脚本（`/tmp/f007-test/**`）均在仓库之外。测试启动的 PG（PID 334479）与 uvicorn（PID 337586）已按 **PID 精确 kill**，未使用 `pkill -f`，未触碰既有 `csm_review_pgdata` / 8797 进程。

GIT: git status
GIT: git log --oneline -5
GIT: git rev-parse --short HEAD
GIT: git status --short
GIT: git show --stat 0fb1419
GIT: git diff --stat 81a603e 0fb1419
GIT: git diff --stat 0fb1419^ 0fb1419 -- backend/migrations/versions/
GIT: git diff --name-only HEAD -- backend/migrations/versions/
GIT: git diff --name-only develop feature/F007-container
