# Review Report — F008 Service 资源管理与 Cluster 共享关联

> Status: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer（独立评审）
> Date: 2026-09-18
> Feature: F008（E04，P1）
> Base（develop）: `68d8e115085fbca7b1bfeb62719b4b815cc3459f`
> Reviewed HEAD: `f5ed0e41459898124703817cea0436780f4ebaec`
> merge-base: `68d8e11…`（= Base，线性分支）
> Diff: `git diff 68d8e11 f5ed0e4 --stat` = **53 files, +9562 / −82**
> 工作区: `git status --short` / `git diff --cached` / `git ls-files --others` **全部为空**
> 测试证据: **评审独立重跑**（真实 PostgreSQL 16 + 真实前端），未采信 Tester 结论

Feature 提交链：docs `5acd256` / `cc62317` / `8f27496` / `1983b9a` / `49f439c` → 实现 `6d09994` → 检查点 `ca75a1c` → 测试 `f5ed0e4`

---

## 独立执行摘要（真实命令与数字）

| 验证 | 命令 | 结果 |
|---|---|---|
| 真实 PG | `pgserver` 数据目录 `/tmp/f008-rev/pgdata`；大小写敏感实测 `'abc'='ABC'` → false | 启动成功 |
| Migration | `alembic upgrade head` ×2 / `alembic check` | 幂等；**No new upgrade operations detected** |
| 独立 DB 脚本 | `/tmp/f008-rev/verify_db.py`（评审自写，直连 psycopg） | **26/26 PASS** |
| 独立 API 脚本 | `probe_api.py` + `probe2.py` + `probe3.py` + `probe_empty.py` | **36 + 12 + 4 PASS**（1 项为评审自身用例错误，已修正） |
| Guard 注入 | 注入未批准路由 `/api/vpns` + 3 处实现改动 | **全部被检出，逐字节还原（sha256 校验）** |
| 后端 guard 套件 | `pytest`（services/structure/cluster_views/containers/virtual_machines/auth/ip_addresses/network_interfaces guards） | **150 passed, 1 skipped** |
| F008 API/DB | `pytest tests/test_services_api.py tests/database/test_services_constraints.py tests/database/test_services_schema_guard.py` | **102 passed**（127s） |
| 并发 / Migration | `pytest tests/test_services_concurrency.py tests/database/test_migrations.py` | **15 passed**（38s） |
| BM API | `pytest tests/test_bare_metals_api.py`（带 DSN） | **44 passed** |
| 前端 | `npm run typecheck` / `npm run test` / `npm run build` | exit 0；**36 files / 546 passed**；build success |

---

## AC-01~AC-54 逐条结果

证据均为评审本人执行。PASS = 独立复现；PASS(suite) = 评审重跑的契约级测试。

| AC | 结果 | 证据 |
|---|---|---|
| AC-01/02/03 | PASS | 三类型各自登记 `201` |
| AC-04 | PASS | 一次 3 载体 `201`，3 项全保留，稳定序 `[BM,VM,CT]`（**请求序为 CT,BM,VM**，证明排序不依赖请求序） |
| AC-05 | PASS | 缺 name → `400 field=name`，写入 0 |
| AC-06/07 | PASS | 缺 / 空 `carriers` → `400`，行数不变 |
| AC-08 | PASS | 含无效载体 → `404`，`(services, carriers)` 计数不变，非 5xx |
| AC-09 | PASS | `CLUSTER/NETWORK_INTERFACE/IP_ADDRESS/HOST/bare_metal` → `400` |
| AC-10 | PASS | `VIRTUAL_MACHINE` + BM 的 id → `404`，无写入 |
| AC-11 | PASS | 全部经 API 直呼（绕 UI），后端 / DB 裁决一致 |
| AC-12 | PASS | `ServiceRead` 恰 11 字段；`services` 恰 11 列；载体在独立表；无 `status` / `cluster*` / 凭据 |
| AC-13 | PASS | 6 可选字段返 `null`（非省略） |
| AC-14 | PASS | `url="这不是一个 URL"`、`port="abc"`、`protocol="自定义"`、空白 `name` 原样往返 |
| AC-15 | PASS | DB：`services` **恰 1 约束（PK）、0 CHECK**；空串 / 首尾空白 name 被接受 |
| AC-16 | PASS | 详情 carriers 数量与登记一致 |
| AC-17 | PASS | 同载体被多 Service 绑定均成功；按该载体查询返回多条 |
| AC-18 | PASS(suite) | 跨 Cluster 载体 → 同名活跃行恰 1 |
| AC-19 | PASS | 按 X 查不含无关 S；按各载体分别命中 |
| AC-20 | PASS | DB 列集合无 `cluster*`；guard 通过；源码无 `cluster_id` 写入 |
| AC-21 | PASS | 详情只暴露 `carriers`；无 Cluster 归属 |
| AC-22 | PASS | 重复活跃 name → `409 field=name code=DUPLICATE` |
| AC-23/24 | PASS | DB：独立表 / 独立索引；Service 与 Container 唯一性互不干扰；与其它资源同名均 `201` |
| AC-25 | PASS | DB：`mon` / `MON` 共存 |
| AC-26 | PASS | DB：绕应用层重复活跃 name → **`23505`**；应用路径 → `409` |
| AC-27 | PASS | DB：软删后可重登记；旧行 `deleted_at` 未改写 |
| AC-28 | PASS | DB 无 status 列；`PATCH {status}` → `400` |
| AC-29 | PASS | 空库 `200 {items:[],total:0}` |
| AC-30 | PASS | 删后按 id → `404` |
| AC-31 | PASS | 活跃无绑定 → `200` 空集；不存在 / 软删 → `404`；三类型均验 |
| AC-32 | PASS | 仅给其一 → `400`，`field` 为缺失项 |
| AC-33 | PASS(suite) | 预置 `deleted_at` 的 Service 被列表 / 载体查询排除、详情 `404` |
| AC-34/35/36 | PASS | PATCH 6 字段 `200`；`{}` / `carriers` / `name` / `status` → `400`；name / carriers 不变 |
| AC-37 | PASS | `DELETE` → `204` 空体；行仍存在、`deleted_at` 非空；读取排除 |
| AC-38 | PASS | DB：软删后绑定行逐字段不变；无级联 |
| AC-39 | PASS | DB：软删后原载体拦截查询 = 0 行 |
| AC-40 | PASS | guard：无 restore / undelete / batch / by-name / include_deleted |
| AC-41/42/43 | PASS | 三载体 `DELETE` → `409 ACTIVE_CHILDREN_EXIST`；`deleted_at` 仍 NULL |
| AC-44 | PASS | 三常量逐名核对：BM=(VM,NIC,Container,Service)；VM=(Container,Service)；CT=(Service,) **非空** |
| AC-45 | PASS | `clusters/deletion.py` **sha256 与 Base 完全相同**；`CLUSTER_ACTIVE_CHILD_CHECKS == (has_active_bare_metals,)`；无传递性 Service 检查 |
| AC-46 | PASS | **真并发**（`threading` + `is_alive()` 阻塞断言）三载体 × 两交错 6 例；孤立记录查询 = 0 |
| AC-47 | PASS | 真并发：多载体 `FOR SHARE`；任一未命中 → `404` 且写 0；**相反请求顺序两笔均成功**（确定性全序，无死锁） |
| AC-48 | PASS | `/api/services*` 路径恰 2（5 端点）；`ServiceUpdate` 不含 `carriers`；全 `backend/app/**` 无 `update/delete(ServiceCarrier)`；绑定表无 `deleted_at` |
| AC-49 | PASS | 回归 SQL 可重复执行；产品路径后零载体活跃 Service = 0 |
| AC-50 | PASS | DB 结构允许零载体；`pg_trigger` 无用户触发器 |
| AC-51/52 | PASS | guard + DB 列封闭；无监控 / 凭据 / 发现 / 位置字段或端点 |
| AC-53 | PASS | 未认证 5 端点 `401 UNAUTHENTICATED`，行数前后不变 |
| AC-54 | PASS | 前端 typecheck 0 / 546 passed / build success；三态、Empty ≠ Not Found、按 `error.code` 分支、不解析 `message` |

**AC-01~AC-54 全部 PASS，无 FAIL / NOT VERIFIED。**

---

## 架构符合性

- **§1 多态 N:M 绑定 —— 正确**。单表三可空 FK + `CHECK num_nonnulls=1` + 3 条 partial unique + 4 条 `RESTRICT` FK。**评审独立证明机制**：CHECK 迫使恰一列非空，partial unique 键含 NULL 不参与冲突，故同一 Service 可同时绑定 BM/VM/Container 的**同数值 id=100**（`OVERRIDING SYSTEM VALUE` 构造），3 行共存；重复绑定同一载体 → `23505`。
- **§2「释放不是写入」—— 成立且已验证**。`service_carriers` 无 `deleted_at` / 时间戳；全 `app/**` 无任何 UPDATE / DELETE 绑定行；软删 Service 后绑定行逐字段不变、原载体拦截 EXISTS 立即为 0；allow-list 经 guard 断言**恰为** `{backend/app/deletion/service.py}`。**该裁定未掩盖任何 AC**：AC-38 / 39 / 48 / 49 全部由可失败测试与独立 DB 脚本证成，AC-48 的「无解绑路径」意图被真实兑现。
- **§3 锁序**：`(rank, carrier_id)` 升序，`FOR SHARE` 单表无 JOIN；并发脚本以**相反顺序**验证无死锁。
- **§5 检查点**：三载体追加、`CLUSTER` 不变，均由 `active_children=` 真实消费（AST guard）。
- **§9 guard 演进（只增不减）**：**无测试函数被删除**（各 guard 文件 test 数 base == head；仅 `0007→0008` 重命名）；仅有一处断言按 Handoff §9 明确许可演进（`CONTAINER_ACTIVE_CHILD_CHECKS == ()` → 非空且含 service 检查）。
- **§10 guard**：AC-15 / 20 / 21 / 28 / 48 / 51 / 52 均有可失败测试。

### 边界 guard 现状（F006-T-01 / F004-T-02 同源风险）

- `BOUNDARY_TOKENS = ()` → `test_g009_2` **确实恒真**（注入 `/api/vpns` 后该测试仍 pass），但测试**保留**且仍遍历全部 OpenAPI path。
- **真正的防线 `APPROVED_API_PREFIXES`（`test_product_api_surface_is_closed`）仍可独立失败**：注入未批准 `GET /api/vpns` 后该测试 **FAILED**（`不得注册未批准资源端点：['/api/vpns']`），随后逐字节还原（sha256 一致，工作区 clean）。扫描范围**未收窄**。

## 契约符合性

逐条对照 `docs/api/f008-service.md`：`ServiceRead` 恰 11 字段含 `carriers`；`carrier_type` 三值封闭；`carriers` **稳定按 `(rank,id)` 升序、不依赖请求 / 插入 / 行序**；`400 VALIDATION_ERROR`（含框架 422→400 映射，`field` 正确）、`401 UNAUTHENTICATED`、`404 NOT_FOUND details==[]`、`409 CONFLICT details[].code=DUPLICATE / ACTIVE_CHILDREN_EXIST`；Empty（`200`+`[]`）vs Not Found（`404`）区分；PATCH 可变恰 6 字段；DELETE 204。

**`?carrier_type=&carrier_id=` 构成 F010 可复用的 canonical 过滤 —— 通过**：canonical 落于 `repository.list_active_services_by_carrier`，封闭三值 + 成对约束 + Empty / Not-Found 判定位置明确。

## 数据库与 Migration

- `services` 恰 1 约束（PK）、0 CHECK、11 列；`service_carriers` 5 列、1 PK + 1 CHECK + 4 FK 全 `RESTRICT/RESTRICT`、**无 `deleted_at`**；`ux_services_name_active` partial `WHERE deleted_at IS NULL`，无 `lower` / `collate`。**DB 实测全部确认**。
- `23514`（0 / 任二 / 全非空的五种组合）、`23503`（不存在载体、物理删被绑定载体、物理删被绑定 Service）全部实测。
- Migration `0008_f008_services`：`upgrade` 幂等、`downgrade 0007` 可逆、`alembic check` 无漂移、与 ORM 无 drift。
- **`0001`–`0007` 逐字节未改**；**`app/deletion/service.py` 逐字节未改**（sha256 base == head）。

## 未定义约束「不实现」

7 字段无长度 / trim / 空串 / 字符 / URL / 端口 / validator（guard 字段约束标志为空、`services` 0 CHECK、`information_schema` 无长度）。实测空串 name、`url="这不是一个 URL"`、`port="abc"`、空白 `service_type` **均被接受并原样存取**。

## 可维护性与测试充分性

- `app/services/**` 无第二套业务规则、无 TODO / FIXME / print、无未使用代码；沿用 `common/errors`、`common/pagination`、`db/active`、`deletion.soft_delete`，与 F007 模式一致。
- **对抗注入（评审抽查 3 组，全部可失败并逐字节还原）**：`session.delete(ServiceCarrier)` → G-9 fail；`ServiceRead` 注入 `status` → G-1 fail；从 `BARE_METAL_ACTIVE_CHILD_CHECKS` 移除 service 检查 → G-10 fail。
- 并发测试为**真实线程**，非顺序模拟。`tests/test_services_api.py` 为纯 API 级（无内部实现 import）。

---

## Findings

| ID | Severity | Owner | 描述 | 证据 | 建议 |
|---|---|---|---|---|---|
| **REV-F008-1** | **LOW** | Coordinator | `project-plan.yaml > F008.git.head_commit` = `6d09994`（**实现提交**），与真实分支 HEAD `f5ed0e4` 不符。此为 F004/F005/F006/F007/F009 反复出现的同类元数据漂移。 | `git rev-parse HEAD` = `f5ed0e4…`；plan 中 `head_commit: 6d09994…`。 | 合并前将 `head_commit` 修正为已批准 SHA `f5ed0e4`（并记录 merge commit）。 |
| **REV-F008-2** | **NOTE** | Backend / Coordinator | `tests/test_bare_metals_api.py` T-29 上方历史注释仍称「`service` 必须保持全局覆盖」「`service` 仍须被全局检出」，与紧随其后的 F008 注释及 `forbidden_prefixes=("nic",)` **矛盾**。 | `sed -n '688,706p'`；`git diff` 显示仅改了 tuple，未同步旧注释。 | 删除 / 标注过时注释；实际防线已由 allow-list 承担。 |
| **REV-F008-3** | **NOTE** | Tester / Coordinator | Tester 报告基线标注 `HEAD ca75a1c`，而候选 HEAD 为 `f5ed0e4`；但 `git diff --stat ca75a1c f5ed0e4` = **仅 2 个 docs**，代码零变更，故**测试证据对候选代码仍然有效**。 | `git diff --stat ca75a1c f5ed0e4`。 | 报告基线标注可更精确；无功能影响。 |

**无 BLOCKER / HIGH / MEDIUM。**

## Existing Defects

Tester 报告 Defects = None。评审逐项重新评估后**同意**：无缺陷需重定级；其「NOT TESTED」条目（浏览器 DOM 级 E2E）合理且不阻塞。

## Non-blocking Follow-ups

1. **REV-F008-1**（plan `head_commit` 同步，合并前）。
2. **REV-F008-2**（过时注释）。
3. 承 F004/REV-2：`BOUNDARY_TOKENS=()` 后单数变体路由（如 `/api/service`）依赖 allow-list 而非 deny-list —— 本次 allow-list 经注入证实有效，属既有设计边界，无需本 Feature 处理。

## Unreviewed Areas

- 浏览器真实渲染 / DOM 交互级 E2E。
- 性能 / 长时间稳定性。
- F011 Excel 导入对 Service 校验的复用（属 F011）。
- 负载下大规模并发（仅验证 2 笔交错）。

---

## 结论

```text
APPROVED WITH FOLLOW-UP
```

**理由**：核心架构风险（多态 N:M 绑定）与最易误判的裁定（「释放不是写入」）均经评审**独立真实数据库**验证成立；AC-01~AC-54 全部 PASS；无 BLOCKER / HIGH / MEDIUM；无范围蔓延；guard 未收窄、无既有测试被删除，且经对抗注入证实可失败；Migration 与 `0001`–`0007`、`app/deletion/service.py` 逐字节未改；前后端测试与构建全绿。仅 1 项 LOW 计划元数据漂移与 2 项 NOTE。

批准**仅对** Feature HEAD `f5ed0e4`、Base `68d8e11`、merge-base `68d8e11` 有效。上述 LOW / NOTE 由协调器在最终状态提交中处理。

GIT: NONE
