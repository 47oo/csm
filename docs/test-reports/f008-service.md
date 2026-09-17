# Test Report — F008 Service 资源管理与 Cluster 共享关联

> Status: **READY FOR REVIEW**
> Author Role: tester（独立验收）
> Date: 2026-09-18
> Feature: F008（E04，P1）
> 基线: branch `feature/F008-service`，HEAD **ca75a1c**（实现提交 `6d09994`）；`database_design` / `backend` / `frontend` 均 COMPLETE
> `git status --porcelain` 全程为空

---

## Test Basis

- `docs/product/handoffs/f008-service.md`（**AC-01~AC-54**）
- `docs/architecture/f008-service-handoff.md`（§1 绑定表裁定 / §2 释放机制 / §3 锁序 / §5 检查点 / §7 / §9 guard 演进 / §10 guard）
- `docs/api/f008-service.md`（**契约，唯一权威**）
- `docs/database/f008-service-migration.md`（§5 / §7）
- `AGENTS.md`、`docs/project/git-workflow.md`、ADR-0002 / ADR-0004
- 实现：`backend/app/services/**`、`models/service{,_carrier}.py`、`migrations/versions/0008_f008_services.py`、三载体 `deletion.py`、`frontend/src/api/services.ts`、`Service*.vue`、`tests/**`

---

## Environment

| 项 | 值 |
|---|---|
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 真实实例，本次**新建**数据目录 `/tmp/f008-test/pgdata`，与既有 `/tmp/f008-pg`、`/tmp/f008-be`、`/tmp/csm_review_pgdata` 不冲突） |
| Collation | `zh_CN.UTF-8`；**大小写敏感实测**：`select 'abc' = 'ABC'` → **false** |
| Backend | 真实 PostgreSQL，DSN `postgresql+psycopg://…`；每类运行**独立数据库**（full / adv / adv2 / adv3 / conc / mig / db / db2）避免 `DROP SCHEMA` 竞态 |
| Frontend | Node v24.14.0 / npm 11.9.0；vitest 5.0.1 |
| 真实集成 | 真实 uvicorn（127.0.0.1:8971）+ 真实 PG + 真实前端 api 层（非 mock） |
| 进程清理 | PG（PID 397730 及 launcher 397724/397726）、uvicorn（PID 397787/397789）按 **PID 精确 kill**；既有 `csm_review_pgdata`(12223) / 8797(55732) 未触碰 |

**是否全新**：PG 实例、全部测试库、独立脚本、集成探针均为本次新建。实现方与协调器结论**未被复用**。

---

## 独立执行摘要（真实命令与数字）

| 执行 | 命令 | 结果 |
|---|---|---|
| 全量后端 | `pytest -q`（`csm_f008_full`） | **935 passed**，2 warnings，928.21s |
| F008 专测收集 | `pytest --collect-only`（5 个 F008 文件） | **136 tests collected** |
| 并发模块（独立库） | `pytest -q tests/test_services_concurrency.py` | **8 passed**，18.49s（真实线程） |
| **独立 DB 脚本** | `/tmp/f008-test/db_independent2.py`（直连 DB） | **28/28 PASS** |
| **独立 API 脚本** | `/tmp/f008-test/api_independent.py` | **34/34 PASS** |
| **独立 API 补充** | `/tmp/f008-test/api_supplement.py` | **51/51 PASS** |
| Guard 对抗注入 | `/tmp/f008-test/inject_guards.py` | **11/11 检出，11/11 逐字节还原** |
| Migration | `alembic upgrade×2` / `downgrade 0007` / `check` | 全部 PASS |
| deleted_at allow-list | `scan_deleted_at_writes()` | 恰为 `{backend/app/deletion/service.py}` |
| 前端 typecheck | `npm run typecheck` | exit **0** |
| 前端测试 ×2 | `npm run test` | 36 files / **546 passed**，**两次均全绿** |
| 前端构建 | `npm run build` | 1691 modules，build success |
| **真实数据层集成** | vitest(node) 实连 uvicorn+PG | **3/3 PASS**；uvicorn 日志记录真实 `201/401/200/409/404/204` |

---

## Acceptance Criteria Mapping（AC-01~AC-54）

图例：[D]=独立 DB 脚本　[A]=独立 API 脚本　[A2]=独立 API 补充　[F]=全量套件　[C]=并发模块　[G]=guard 注入　[M]=migration　[FE]=前端　[I]=真实集成

| AC | Result | 证据 |
|---|---|---|
| AC-01/02/03 | PASS | [A] 三类型各自 `201`；[F] |
| AC-04 | PASS | [A] 三载体全保留、稳定序 `[BM,CT,VM]` |
| AC-05 | PASS | [A2] 缺 name → 400 `field=name`，写入 0 |
| AC-06 | PASS | [A2] 缺 carriers → 400，写入 0 |
| AC-07 | PASS | [A2] `carriers:[]` → 400，写入 0 |
| AC-08 | PASS | [A2] 3 载体含 1 无效 → 404；Service 行 0 / 绑定行 0；非 5xx |
| AC-09 | PASS | [A2] `CLUSTER/NETWORK_INTERFACE/IP_ADDRESS/HOST/BARE_METALS` → 400，写入 0 |
| AC-10 | PASS | [A2] `VIRTUAL_MACHINE` + 不存在 id → 404；一致性由类型分派保证 |
| AC-11 | PASS | [A]/[A2] 全部经 API 直呼（绕 UI）结果一致；无绕过校验路径 |
| AC-12 | PASS | [A] `ServiceRead` 恰 11 字段；[A2] 未知 / `status` / `cluster_id` / `deleted_at` / `id` / `credential_reference` → 400；[D] `services` 11 列 |
| AC-13 | PASS | [A2] 6 字段返回 `null` 而非省略 |
| AC-14 | PASS | [A2] `"  共享存储服务  "` / `"这不是一个 URL"` / `"abc"` / `"自定义协议"` / 含换行原样往返 |
| AC-15 | PASS | [A2] 空串 name → 201；[D] 空串 / 首尾空白 / 任意 url/port 接受；`services` **恰 1 约束（PK）、0 CHECK** |
| AC-16 | PASS | [A] 详情 carriers 数量与登记一致、无截断 |
| AC-17 | PASS | [A] 同一载体被 2 Service 绑定；[D] 不同 Service 绑同一载体成功 |
| AC-18 | PASS | [A] 跨 Cluster 载体 → 同名活跃行 **恰 1**；[F] |
| AC-19 | PASS | [A] 对每载体反查含 S、无关载体不含；跨 ≥2 Cluster 成立 |
| AC-20 | PASS | [A2]/[D] 无 `cluster_id`；[G] 注入 `cluster_id` 被 guard 检出 |
| AC-21 | PASS | [A] 详情只含 carriers；[G] `test_g4_no_cluster_tokens...` |
| AC-22 | PASS | [A2] 跨 Cluster 同名 → 409 `field=name, code=DUPLICATE`，活跃仍 1 |
| AC-23 | PASS | 独立：Container 同载体重名 → **409**、异载体同名 → **201**、Service 与 Container 同名 → **201** |
| AC-24 | PASS | 独立：Cluster/BM/VM/Container/Service 同名 `same-name-ac24` 全部 **201** |
| AC-25 | PASS | [A2] `mon`/`MON` 共存 201/201；[D] DB 层共存 |
| AC-26 | PASS | [D] 绕应用层重复活跃 name → **23505**；[A2] 应用路径 → 409（同一权威） |
| AC-27 | PASS | [A2] 软删后可重登记 201；旧行 `deleted_at` **未被改写** |
| AC-28 | PASS | [A2] `status` 入请求 → 400，响应无 status；[D] 无 status 列；[G] 注入被检出 |
| AC-29 | PASS | [A2] 空库列表 200 `{items:[],total:0}`，非 404 |
| AC-30 | PASS | [A2] 不存在 / 已删 id → 404 |
| AC-31 | PASS | [A] 三类型逐一：活跃无绑定 → 200 空集；不存在 → 404；软删 VM → 404；结果只含绑定该载体的活跃 Service |
| AC-32 | PASS | [A] 仅给 carrier_type → 400；仅给 carrier_id → 400 |
| AC-33 | PASS | 独立：绕应用层预置 `deleted_at` → 列表 / 载体查询排除、详情 404 |
| AC-34 | PASS | [A2] PATCH 6 字段子集 → 200、`null` 清空、name/carriers 不变 |
| AC-35 | PASS | [A2] `name` / `carriers` / `{}` / `status` / `cluster_id` → 400 |
| AC-36 | PASS | [A2] 改可选字段不触发唯一性冲突 |
| AC-37 | PASS | [A2] DELETE → 204 空体；行物理存在且 `deleted_at` 非空；读取排除 |
| AC-38 | PASS | [A2] 删除后绑定行数不变、无级联；[D] 各列逐字段不变 |
| AC-39 | PASS | [A] 软删 Service 后原载体 DELETE → 204；[D] 拦截查询 = 0 |
| AC-40 | PASS | [A2] `restore/undelete/batch/by-name/carriers` 端点均 404/405 |
| AC-41 | PASS | [A] BM 被活跃 Service 绑定 → DELETE 409 `ACTIVE_CHILDREN_EXIST`，`deleted_at` 仍 NULL |
| AC-42 | PASS | [A] VM 同上 → 409，`deleted_at` NULL |
| AC-43 | PASS | [A] Container 同上 → 409（**F007 追加点落地**） |
| AC-44 | PASS | [A] 常量逐名核对：BM 保留 VM/NIC/Container + 追加 Service；VM 保留 Container + 追加；Container `()` → 非空；[G] 移除 / 清空即失败 |
| AC-45 | PASS | [A] `CLUSTER_ACTIVE_CHILD_CHECKS == (has_active_bare_metals,)` **未变**、无传递性；[G] 注入 Service 检查即失败 |
| AC-46 | PASS | [C] 三载体 × 两交错 6 例真实并发全绿；[D] 三条孤立记录查询 = 0 |
| AC-47 | PASS | [C] `FOR UPDATE` 阻塞、任一未命中 404 且写 0；**相反请求顺序**两笔均成功（确定性全序，无死锁） |
| AC-48 | PASS | [A2] 无解绑 / 替换端点；[G] 注入 `session.delete(ServiceCarrier)` 与 `update(ServiceCarrier)` 均被检出；[D] 绑定表 **无 `deleted_at` 列**；写入仅 INSERT |
| AC-49 | PASS | [D]/[A2] 经产品路径操作后零载体活跃 Service = **0**（回归 SQL 可重复执行） |
| AC-50 | PASS | [D] 数据层**可**表达零载体（人工直插即出现）→ 未加 DB 硬约束；产品路径兑现 AC-49 且有回归断言 |
| AC-51 | PASS | [A2]/[G] 越界端点注入被 allow-list 检出；[F] 表集合 / 字段封闭 guard |
| AC-52 | PASS | [F] `test_g4_no_forbidden_tokens_in_service_module_source` 无凭据 / 健康 / 监控 / 发现 / 位置 token |
| AC-53 | PASS | [A] 5 端点未认证全 **401**、数据行数不变；[I] 实连后端 401 |
| AC-54 | PASS | [FE] 546 用例 ×2 全绿；源码核对 `ListStates` 三态 `data-state`、`ErrorState` 按 `error.code` 分支、`ServiceFormDialog` 仅 `SERVICE_CARRIER_TYPES` 三值且 `submitDisabled` 要求 ≥1 完整载体行；[I] |

**54/54 有结果，全部 PASS，无 FAIL，无 NOT TESTED 的 AC。**

---

## 对抗注入记录（注入 → 期望 → 实际 → 还原）

所有注入后以 **sha256 校验还原**，结束后 `git status` 干净。

| # | 注入 | 检出 guard | 期望 | 实测 |
|---|---|---|---|---|
| A | `main.py` 增加未批准 `POST /api/datacenters` | `test_structure_guard.py::test_product_api_surface_is_closed`（**`APPROVED_API_PREFIXES` allow-list**） | fail | **fail** |
| A′ | 同上，deny-list 测试 | `test_cluster_views_guards.py::test_g009_2`（`BOUNDARY_TOKENS=()`） | pass（**恒真，不由它检出**） | pass |
| B | `ServiceRead` 注入 `status` | `test_g1_service_read_schema_is_closed` | fail | fail |
| B2 | `ServiceRead` 注入 `cluster_id` | 同上 | fail | fail |
| C | `app/services/repository.py` 注入第 2 处写 `deleted_at` | `test_g8_deleted_at_writer_allowlist_unchanged` | fail | fail |
| D | 注入 `session.delete(ServiceCarrier)` | `test_g9_binding_writes_are_insert_only` | fail | fail |
| D2 | 注入 `update(ServiceCarrier)` | 同上 | fail | fail |
| E | 从 `BARE_METAL_ACTIVE_CHILD_CHECKS` 移除 Service 检查 | `test_g10_carrier_checks_contain_service_checks` | fail | fail |
| F | `CONTAINER_ACTIVE_CHILD_CHECKS` 清回 `()` | 同上 | fail | fail |
| G | 删除 `active_children=SERVICE_ACTIVE_CHILD_CHECKS` 实参 | `test_g10_service_active_child_checks_explicitly_empty_and_consumed` | fail | fail |
| H | `CLUSTER_ACTIVE_CHILD_CHECKS` 注入 Service 检查 | `test_g10_cluster_checks_unchanged` | fail | fail |

> **越界端点结论（F006-T-01 / F004-T-02 的同源风险点，本 Feature 必验）**：`BOUNDARY_TOKENS` 已清空 → `test_g009_2` **恒真**。注入 A/A′ 证明：真正的、**可独立失败**的防线是 **`APPROVED_API_PREFIXES` allow-list**（`test_product_api_surface_is_closed`）。该防线**仍生效**，且扫描范围**未被收窄**。（`test_g009_2` 仍保留并在遍历全部 OpenAPI path，只是不再有 token 可拒。）

---

## Database / Migration

- **三 partial unique 互不干扰（本设计核心不变式）**：[D] 同一 Service 同时绑定 **BM / VM / Container 的同数值 id=100** → **3 行成功**。**机制**（独立验证）：`CHECK (num_nonnulls(...) = 1)` 迫使另两列为 NULL；唯一索引键含 NULL 恒不参与冲突（temp-table 实测：同 `(u,v)` 两行各含 NULL 均可插入；非 NULL 重复 → `23505`）。三条索引定义经 `pg_indexes` 核对。
- **集合语义**：[D] 重复绑定同一载体（三类型各一）→ **`23505`**；不同 Service 绑同一载体 → **成功**。
- **`23514`**：[D] 三列全 NULL（0 个）/ 任两列非空（BM+VM、BM+CT、VM+CT）/ 三列全非空 → **全部 `23514`**。
- **FK / RESTRICT**：[D] 不存在载体 id → **`23503`**；**物理删除被绑定的载体 / 被绑定的 Service → `23503`**（证明 `RESTRICT` 而非 CASCADE）。
- **「释放不是写入」（AC-39 / AC-48 的承重证明）**：[D] 软删一个绑定着多个载体的 Service 后，`service_carriers` **行数与各列逐字段不变**；原载体拦截查询 = 0；`service_carriers` **无 `deleted_at` 列**；`scan_deleted_at_writes()` allow-list 恰为 `{backend/app/deletion/service.py}`。
- **列集合**：[M] `services` **11** 列 / `service_carriers` **5** 列；无 `status` / `cluster*` / （绑定表）`deleted_at`。
- **Migration**：[M] `upgrade head` ×2 幂等；`downgrade 0007` → 两表消失、rev = `0007_f007_containers`；再 `upgrade head` 一致；`alembic check` → **No new upgrade operations detected**。`git log … --name-only -- backend/migrations/versions/` **仅 `0008`**；**`0001`–`0007` 逐字节未改**（`git diff --stat` 为空）。

---

## Backend / API

- 独立 API 脚本 **34/34** + 补充 **51/51** 全绿。
- **反查的对抗性验证**：载体 X 只被 S1 绑定、S2 绑定另一载体 Y 时，按 X 查**不得**返回 S2 —— 通过，证实实现用的是**相关**子查询（实现方曾在初版写出非相关子查询，会产生**静默错误结果**，已自行修复；本次独立复验该语义）。
- 并发 8 例真实线程：三载体、两交错、**相反请求顺序**，全部通过；失败登记后 Service / 绑定行均为 0。
- 无写入语义：AC-05/06/07/08/09/10 拒绝后行数不变。

## Frontend

- `typecheck` exit 0；**546 用例连续两次全绿**；build 成功（1691 modules）。
- 三态 `data-state`（loading / empty / error / content）互不相同；**Empty**（`empty` + 「该载体暂无服务」）与 **Not Found**（`error` + `data-error-code=NOT_FOUND` + 「未找到资源」）渲染**不同状态与不同文案**；错误按 `error.code`（必要时 `details[].code`）分支，**不解析 `message`**；登记表单仅三种载体类型且 **≥1 完整载体行**方可提交。

## Integration（真实前后端数据层）

- 真实 uvicorn(8971) + 真实 PostgreSQL + 真实 `frontend/src/api/{http,services}.ts`（node 环境，仅做 base-url / cookie 传输适配，**未伪造响应**）。
- **3/3 PASS**：未认证真实 `401`；登记 → 详情 → 按载体查询 → PATCH；重复 name 真实 `409 DUPLICATE`；无效载体真实 `404`；`DELETE 204` 后详情 `404`。
- uvicorn 访问日志确认真实 HTTP 往返：`201/401/200/409/404/204`。

---

## Defects

**None.** 未发现 BLOCKER / HIGH / MEDIUM / LOW。

---

## Unverified Areas（NOT TESTED）

1. **浏览器 DOM 级 E2E**（真实浏览器渲染 Vue 页面并交互）——无浏览器自动化工具；已由「**前端真实数据层 ↔ 真实后端**」集成 + 组件级 DOM 测试替代，残余风险低。
2. 负载 / 性能、长时间运行稳定性——不在本 Feature 验收范围。
3. F011 Excel 导入对 Service 的复用（属 F011）。

---

## Test Status

`READY FOR REVIEW`

54/54 AC 有结果且全 PASS；无缺陷；数据库 / 迁移 / API / 并发 / guard / 前端 / 真实数据层集成均以独立证据验证。

---

## Test Handoff

### Status
`READY FOR REVIEW`

### Verified
- AC-01~AC-54 全部（证据见上表）。
- 三 partial unique 互不干扰、集合语义、`23514`、**释放非写入**、唯一性、未定义约束、Cluster 共享推导、三载体父删子拦、AC-46/47 真实并发、AC-48/49 不变式、migration 可逆与 `0001`–`0007` 未改、前端三态与表单、真实数据层集成。

### Not Verified
- 浏览器 DOM 级 E2E（NOT TESTED）。

### Blocking Issues
None.

### Defect Owner
None.

---

GIT（本次实际执行的只读命令，未改变任何 Git 状态）：
```
GIT: git rev-parse --short HEAD
GIT: git status --porcelain
GIT: git branch --show-current
GIT: git log --oneline -8
GIT: git log --oneline 9ec1e1e..ca75a1c --name-only -- backend/migrations/versions/
GIT: git diff --stat 9ec1e1e^..ca75a1c -- backend/migrations/versions/0001_f012_baseline.py 0002…0007
```
