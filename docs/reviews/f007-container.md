# Review Report — F007 Container 资源模型与登记

> Status: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer（独立评审）
> Date: 2026-09-17
> Feature: F007（E03，P1，`depends_on: [F006, F002]`）
> Base Branch / SHA: `develop` / `06b3c5b6bbd36b2be48f7810b6d08a1612ef3b84`
> Feature Branch: `feature/F007-container`
> 审阅 HEAD: `2c383a96f232fd824384e4aeb4efba649a8dc0ee`
> merge-base: `06b3c5b…`（= Base，线性分支）
> 审阅范围: 50 个文件，+8560 / −106（`git diff --stat 06b3c5b 2c383a9`）
> 工作区: clean（`git status --short` 与 `git ls-files --others` 均为空）

Feature 提交链：`8a847bf` → `6cae5a1` → `30592ec` → `85963ce` → `dfa34c4` → `0fb1419`（实现）→ `81a603e` → `e5d0b75` → `2c383a9`（测试）

---

## 关于已知过程事件

- **F007-INC-2**（`30592ec` 提交信息被反引号截断）：核对 `30592ec` 与 `85963ce`，两者对 `docs/architecture/f007-container-handoff.md` 的树内容**逐字节相同**（均 365 行，`git diff 30592ec 85963ce -- <file>` 为空），差异仅在提交信息。**未造成内容错误**，HEAD 内容正确。按要求不作为新缺陷。
- **F007-INC-1**（Backend 违规 `git stash -u`）：协调器已在真实 PostgreSQL 16.2 独立重跑；本次评审亦在全新真实实例独立复跑关键测试。

---

## 独立执行摘要（真实命令与输出）

### 环境（真实，非 mock）

```text
.venv/bin/python + pgserver 起真实 PostgreSQL 16.2，数据目录 /tmp/f007-rev/pgdata
postgres PID 347589（结束按 PID 精确 kill，未用 pkill -f）
datcollate / datctype = zh_CN.UTF-8
select 'abc' = 'ABC'  →  False   （大小写敏感确认）
```

### 迁移（真实库 `csm_rev`）

```text
alembic upgrade head  → 0001 → … → 0006 → 0007_f007_containers
alembic current       → 0007_f007_containers (head)
alembic check         → No new upgrade operations detected.
```

`0001`–`0006` 与 Base **逐字节相同**（sha256 比对全部 `IDENTICAL`）；本 Feature 仅新增 `backend/migrations/versions/0007_f007_containers.py`。

### 评审自己的直连 DB 探针（绕过应用层，非复述 Tester）

```text
containers 列 = 11：id, bare_metal_id, virtual_machine_id, name, image, cpu, memory, owner,
                      created_at, updated_at, deleted_at      （无 status / carrier_type / cluster*）
CHECK 个数 = 1：ck_containers_carrier_exactly_one = CHECK (num_nonnulls(bare_metal_id, virtual_machine_id) = 1)
FK 个数 = 2：fk_containers_bare_metal / fk_containers_virtual_machine，confdeltype='r', confupdtype='r'
partial unique: (bare_metal_id,name) WHERE deleted_at IS NULL / (virtual_machine_id,name) WHERE deleted_at IS NULL
全库 confdeltype='c' 外键数 = 0；触发器 = 0；生成列 = 0；extension = ['plpgsql']

AC-15（核心不变式）: OVERRIDING SYSTEM VALUE 令 BM id=500 与 VM id=500
  BM insert (bare_metal_id=500, name='web')      → OK
  VM insert (virtual_machine_id=500, name='web') → OK
  两行并存：[(1, 500, None, 'web'), (2, None, 500, 'web')]
  机制：CHECK 保证另一载体列必为 NULL，而唯一索引中 NULL 互不相等 → 两条 partial unique index 互不干扰
同载体重复活跃 name：bare_metal_id → 23505 ux_containers_bare_metal_name_active
                    virtual_machine_id → 23505 ux_containers_virtual_machine_name_active
0 个载体 → 23514 ck_containers_carrier_exactly_one
2 个载体 → 23514 ck_containers_carrier_exactly_one
不存在载体 → 23503 fk_containers_bare_metal
物理删除有活跃 Container 的载体行 → 23503（证明 RESTRICT 而非 CASCADE）
大小写：同载体 'web' 与 'WEB' 共存
软删释放：软删后可同载体重建 'web'，旧行 deleted_at 仍非空且未改写
AC-11：'' / '  padded  ' / 'has/slash' 全部被接受且原样存储
```

### 后端测试（真实 PG `csm_rev`）

```text
$ .venv/bin/python -m pytest -q（F007 全部 + 受影响 guard / 迁移 / 认证，13 个文件）
  → 263 passed, 2 warnings in 217.48s
$ .venv/bin/python -m pytest tests/test_containers_concurrency.py -v
  → 6 passed in 14.78s   （AC-36 ×2 / AC-37 ×2 / AC-38 ×2，含 FOR UPDATE NOWAIT 互斥与孤立记录=0）
$ .venv/bin/ruff check backend tests         → All checks passed!
$ .venv/bin/ruff format --check backend tests → 146 files already formatted
```

### F014 单一软删写入路径（评审直接运行扫描器）

```text
scan_deleted_at_writes(整个 backend/app)      → {backend/app/deletion/service.py}   （持久态，恰为 allow-list）
scan_deleted_at_writes(backend/app/containers) → {}                                （容器模块 0 处写 deleted_at）
```

Tester 报告注入态出现 `{repository.py, deletion/service.py}` 系**对抗注入态**，非持久态；当前持久态正确。

### 前端（真实执行）

```text
$ cd frontend && npm run typecheck  → exit 0
$ npm run test                      → Test Files 32 passed (32) / Tests 460 passed (460)
$ npm run build                     → vue-tsc + vite build 成功（仅 chunk 体积告警）
```

### Guard 演进（对 diff 逐一确认）

```text
BOUNDARY_TOKENS: ("container","service") → ("service",)   仅移除 container，保留 service
  全局扫描未收窄：test_cluster_views_guards.py 仍 `for path in _openapi()["paths"]`
EXPECTED_TABLES / APPROVED_API_PREFIXES / EXPECTED_GET_ROUTES / MIGRATION_HEAD：均「增演」
VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS：显式 () → (has_active_containers_on_virtual_machine,)（非空），guard 同步由 ==() 改为非空断言
CONTAINER_ACTIVE_CHILD_CHECKS == () 且源码含 "= ()"（显式）
被删除 / 放宽的既有 guard 测试数：0
  唯一条目差 test_g5_migration_head_is_0006 → 重命名为 test_g5_migration_head_is_0007（head 演进，非删覆盖）
```

---

## 需求与领域规则符合性（AC-01~AC-44）

证据代号：`DB-PROBE`=评审自己的直连 DB 探针；`PY`=评审运行的 263 用例；`CODE`=阅读实现；`GUARD`=阅读 guard 源码；`FE`=评审运行的前端三连；`MIG`=alembic + 字节比对。

| AC | 结论 | 证据 |
|---|---|---|
| AC-01 BM 登记、字段恰 10 | PASS | PY `test_create_returns_closed_field_set[BARE_METAL]`；CODE `ContainerRead` 恰 10 字段；DB-PROBE 表 11 列 |
| AC-02 VM 登记、同字段集 | PASS | PY `…[VIRTUAL_MACHINE]` |
| AC-03 name 必填 → 400 field=name | PASS | PY `test_invalid_name_returns_400_without_write` |
| AC-04 载体必填 → 400 | PASS | PY `test_missing_carrier_returns_400`；DB-PROBE 0 载体 → 23514 |
| AC-05 拒多载体 | PASS | PY `test_unknown_or_overreaching_create_fields_rejected`（`carriers`/两原始列）；DB-PROBE 2 载体 → 23514 |
| AC-06 拒其它类型为载体 | PASS | PY 同上（CLUSTER/SERVICE/NIC/IP）；CODE `extra="forbid"` + 封闭枚举 |
| AC-07 类型与标识一致 | PASS | PY `test_carrier_type_and_id_mismatch_returns_404`（显式 id 500/900）→ 404，无写入 |
| AC-08 载体存在且活跃 | PASS | PY `test_missing_or_deleted_carrier_returns_404`；DB-PROBE 不存在 → 23503 |
| AC-09 可选字段缺失 → null | PASS | PY `test_missing_optional_fields_return_null` |
| AC-10 纯文本往返 | PASS | PY `test_chinese_name_and_text_roundtrip` |
| AC-11 未定义约束「不实现」 | PASS | **DB-PROBE** '' / '  padded  ' / 'has/slash' 均被接受；**表恰 1 CHECK**；GUARD 两项 |
| AC-12 同载体唯一 409 | PASS | PY `test_duplicate_name_on_same_carrier_returns_409`；DB-PROBE 23505 |
| AC-13 跨类型可重名 | PASS | DB-PROBE BM/VM 同名并存 |
| AC-14 同类型不同 id 可重名 | PASS | PY `test_same_name_on_different_carriers_same_type_succeeds` |
| AC-15 跨类型同数值 id 不冲突 | PASS | **DB-PROBE 核心不变式**（BM id=500 与 VM id=500 同名并存） |
| AC-16 不与 R-VM-004 混用 | PASS | PY `test_same_name_on_bare_metal_and_its_vm_succeeds` |
| AC-17 大小写敏感 | PASS | DB-PROBE web/WEB 共存；`'abc'='ABC'`=False；无 lower()/COLLATE |
| AC-18 保存前阻止、DB 权威 | PASS | PY 409；DB-PROBE 绕应用层 23505 |
| AC-19 软删释放唯一性 | PASS | DB-PROBE 软删后重建成功，旧行 deleted_at 未改写 |
| AC-20 唯一性边界是载体非 Cluster | PASS | PY `test_same_name_on_different_carriers_same_type_succeeds` |
| AC-21 不存 cluster_id | PASS | DB-PROBE 11 列无 cluster*；GUARD `test_g2/g3/g4`；CODE schemas 无 |
| AC-22 归属仅由载体表达 | PASS | PY；CODE `carrier_of` 由非空列派生 |
| AC-23 无状态 | PASS | DB-PROBE 列无 status；GUARD `test_g2/g3`；PY `test_no_cluster_or_status_fields` |
| AC-24 列表分页 Empty | PASS | PY `test_empty_list_is_200_empty_items` / `test_pagination` |
| AC-25 详情 404 不区分 | PASS | PY `test_detail_not_found` |
| AC-26 按载体读取 Empty vs 404（两类型） | PASS | PY `test_list_by_carrier_semantics` / `…_requires_both_params` / `…_invalid_params` |
| AC-27 列表/详情排除已删 | PASS | PY `test_soft_deleted_row_excluded_from_reads` |
| AC-28 可选字段可更新 | PASS | PY `test_patch_optional_fields_and_clear` |
| AC-29 更新 schema 封闭 | PASS | PY `test_patch_rejects_unknown_and_immutable`；CODE `model_fields_set` 空 → 400 |
| AC-30 逻辑删除 204 | PASS | PY `test_delete_returns_204_and_row_survives` |
| AC-31 删除不级联（两类型） | PASS | PY `test_delete_does_not_cascade[BARE_METAL/VIRTUAL_MACHINE]` |
| AC-32 无恢复/批量/include_deleted | PASS | GUARD `test_g11_no_out_of_scope_container_routes_or_params`；CODE router 恰 5 端点 |
| AC-33 BM 有活跃 Container → 409 | PASS | PY `test_bare_metal_with_active_container_cannot_be_deleted`；CODE 检查点含容器检查 |
| AC-34 VM 有活跃 Container → 409 | PASS | PY `test_virtual_machine_with_active_container_cannot_be_deleted` |
| AC-35 软删后可删载体 | PASS | PY `test_carrier_deletable_after_container_soft_deleted` |
| AC-36 并发孤立记录=0（BM） | PASS | **评审独立运行** `test_ac36_*`（2 例）：持锁阻塞 + `_invariant_bm == 0` |
| AC-37 并发孤立记录=0（VM） | PASS | **评审独立运行** `test_ac37_*`（2 例）：`_invariant_vm == 0` |
| AC-38 创建对载体行取共享锁 | PASS | **评审独立运行** `test_ac38_create_gate_uses_row_lock`：`FOR UPDATE NOWAIT` 得 `LockNotAvailable` |
| AC-39 BM 检查点含 VM+NIC+Container 且被消费 | PASS | CODE 元组 3 项；GUARD `test_g10_active_child_checks_are_wired` + AST 消费 |
| AC-40 VM 检查点由空变非空且含 Container 且被消费 | PASS | CODE 非空；GUARD `test_g6_t27_…` 已演进 |
| AC-41 Container 自身检查点显式声明且传入 | PASS | CODE `= ()`；GUARD `== ()` + 源码 `= ()` + AST 消费 |
| AC-42 无 K8s/Docker/运行时 | PASS | GUARD `test_g4_*`；DB-PROBE 无相关列 / 触发器 / extension |
| AC-43 不越界其它资源 | PASS | DB-PROBE 仅 2 FK；GUARD `test_g11_container_router_registers_exactly_five_endpoints` |
| AC-44 前端三态 / Empty vs NotFound / error.code / 不重复守卫 | PASS | **FE**；CODE 按 `error.code`（+`details[].code`）分支，`message` 仅展示，无前端业务守卫 |

**AC-01~AC-44 全部 PASS，无 FAIL / NOT VERIFIED。**

---

## 架构符合性

1. **多态载体裁定（§1）— 忠实落地**。两列可空 FK + `num_nonnulls` CHECK + 每载体列一条 partial unique index，与 Handoff §1 一致；**保留两条真实 FK（RESTRICT/RESTRICT）**，未走被否决的「判别列 + 无 FK」。以真实 PG 直连证明「恰好一个」与参照完整性均由 DB 保证、无 CASCADE。无生成列 / 触发器 / EAV / ORM 多态（结构 guard 保持通过）。
2. **加锁协议（§2）**。创建按 `carrier_type` 分派、单表 `with_for_update(read=True)`（`FOR SHARE`，无 `OF`），未命中 → `NotFoundError`；与 F005 先例同形。
3. **检查点演进（§3）**。BM 由 2 项增为 3 项（保留 VM/NIC，追加 Container）；VM 由显式 `()` 变非空；新增 `CONTAINER_ACTIVE_CHILD_CHECKS = ()`；三者均由各自删除路径以 `active_children=` 真实传入（AST guard + 注入 F/G/H）。统一软删服务核心零改动。
4. **guard 演进（§7/§10）** — 全部为**增演**，无收窄伪装：`BOUNDARY_TOKENS` 仅移除 `container`、保留 `service`、**保持对全部 OpenAPI path 的全局扫描**；head / 表集合 / 路由集合 / 前缀集合均增演；F006 REV-3 空元组断言被正确演进；**无任何既有 guard 测试被删除**。与 F006-T-01 / F004-T-02 两次 MEDIUM 的教训相符。
5. **NQ-2 / NQ-6 落实**。NQ-2 → `404 NOT_FOUND` + `details == []`；NQ-6 → 请求/响应/query 统一 `carrier_type` + `carrier_id`，成对校验。

---

## 契约符合性

- **端点集合**：恰 5 个，无 by-name / restore / 批量 / include_deleted。
- **字段集合**：`ContainerRead` 恰 10 字段，无 `deleted_at` / `status` / `cluster_id` / 原始载体列 / K8s / 位置字段。
- **载体表达**：`carrier_type`（封闭枚举）+ `carrier_id`；响应由非空列派生，API 不暴露 `bare_metal_id`/`virtual_machine_id`。
- **错误码与 `details`**：`400 VALIDATION_ERROR`、`404 NOT_FOUND`（`details == []`）、`409 CONFLICT`（`details[].code = DUPLICATE` / `ACTIVE_CHILDREN_EXIST`）、`401 UNAUTHENTICATED`；信封逐字段断言通过。DB `23505/23514/23503` 为最终权威，产品路径经 `FOR SHARE` 预检返回 404 / 409，不至 500。
- **Empty vs Not Found**：载体存在但空 → `200 + items==[]`；载体不存在/已删/类型不一致 → 404；两类型均成立。
- **PATCH**：可变字段恰 `{image, cpu, memory, owner}`，空 body → 400，`name`/载体绑定不可变；`null` 清空。
- **DELETE 204** 无体，行保留。

**关于「`?carrier_type=&carrier_id=` 是否构成 F010 可复用的 canonical 过滤」**：**成立**。它是 F004/F006 `?bare_metal_id=` 先例在多态场景下的**统一泛化**：单一 `(类型, 标识)` 对覆盖两种载体，无需 XOR 校验分支；语义（父存在→404、父存在但空→200 empty、只返回该载体子集）与先例逐条等价。可复用单元为 repository 层 `list_active(..., carrier_type=, carrier_id=)` + service 层载体存在性判定。未发现矛盾或不可复用点。

---

## 数据库与 Migration

- Schema 与 `docs/database/f007-container-migration.md` **逐项一致**（以 `information_schema` / `pg_constraint` / `pg_indexes` 独立断言）：11 列 / 4 约束（1 PK + 1 CHECK + 2 FK）/ 4 索引（2 partial unique + 2 普通）/ 0 CASCADE / 0 触发器 / 0 生成列 / 0 COLLATE。
- `name` 与四个可选字段无长度 / trim / 空串 / 字符 / 格式 CHECK；空串与首尾空白不被数据库拒绝（AC-11 正向 + 「恰 1 CHECK」反向双证）。
- **Migration**：`0007_f007_containers`，`down_revision = "0006_f005_ip_addresses"`；`upgrade` 幂等；`downgrade` 严格逆序；`alembic check` 无漂移；`0001`–`0006` 逐字节未改。
- **文档漂移 NQ-8**：`domain-model.yaml` 已为 `mandatory: true / selector: exactly_one / binding_state: CONFIRMED`；`OPEN-002` 已 `CLOSED_RESOLVED`；`must_not_assume` 已更正；`csm-v1-schema-design.md` 与 `f012-baseline-migration.md` 已同步。**残留两处见 REV-2 / REV-3。**

---

## 可维护性与测试充分性

- `backend/app/containers/**` 结构对齐 `virtual_machines/**`，无第二套业务规则、无未使用代码；读取一律经 `app/db/active.py`，无重复 `deleted_at IS NULL` 谓词；删除委托唯一软删路径。
- 测试为**真实**验收：直连 DB 约束（含 AC-15 核心不变式）、结构 guard（ORM + 实际 Schema 双层）、真实并发（`FOR SHARE` 与 `FOR UPDATE` 互斥 + 孤立记录=0 + `FOR UPDATE NOWAIT` 反证）、真实 API 契约逐字段断言、真实前端三连。测试**未迎合实现**：AC-11 同时正向（接受空串）与反向（恰 1 CHECK）验证；并发测试断言「阻塞」而非只断言最终状态，能识别丢锁。
- 评审独立复跑受影响范围 **263 passed**；前端 typecheck / 460 / build 全绿；ruff 全绿。

---

## Findings

### REV-1

```text
Severity: LOW
Owner: 协调器 / project-manager（元数据）
Location: docs/project/v1/project-plan.yaml > F007.git.head_commit
Problem: head_commit 记录为 0fb1419（实现提交），而 Feature 分支真实 HEAD 与本次审阅基线为 2c383a9
         （其后含 81a603e / e5d0b75 状态提交与 2c383a9 测试交付提交）。
Evidence: git rev-parse HEAD = 2c383a96f232fd824384e4aeb4efba649a8dc0ee；plan 中 head_commit: 0fb1419dfcd64fbe312966ca5d8f7e9d45ccec1d。
          对照 F006（DONE）head_commit = 3bd2da2 即其分支 tip（最终测试提交），而非实现提交。
Impact: 审批基线与 Merge Gate 以 head_commit 为锚；该字段与实际审阅 HEAD 不一致，可能使合并时不察觉基线漂移。
        不影响产品行为。
Expected: 将 F007.git.head_commit 记录为已批准 Feature SHA（2c383a9…）；在此之前明确本 Review 仅对 2c383a9 有效。
```

### REV-2

```text
Severity: LOW
Owner: Database / 协调器（文档同步）
Location: docs/product/domain-model.md §6 Resource Relationships
Problem: §6 仍把「容器 → 虚拟机 / 裸金属 的绑定强制性、登记粒度与生命周期」列在「以下尚未确认」下，
         与 §5.4、R-CONTAINER-002、以及 domain-model.yaml（已 mandatory/exactly_one/CONFIRMED）矛盾。
Evidence: 该条位于「尚未确认」段；domain-model.yaml > relationships[Container-to-Hosts] 已 CONFIRMED。
          Product Handoff NQ-8 第 4 项曾要求同步 §6。
Impact: 后续 Agent 可能读到过时的「未确认」事实，误判关系约束强度。§5.4 为权威，实现正确，无行为影响。
Expected: 将 §6 该条移入「已确认」段（与 VM→BareMetal 的处理一致），或显式标注以 §5.4 为准。
```

### REV-3

```text
Severity: NOTE
Owner: Database（文档措辞）
Location: docs/database/csm-v1-schema-design.md 第 442 行（Container → 载体 行「数据库实现」列）
Problem: 同一单元格内既写「恰好一个非空，由 ck_containers_carrier_exactly_one 保证」，
         又写「两列均 NULL 允许」，可被误读为「两列同时为 NULL 合法」，与 CHECK 及同格内容自相矛盾。
Evidence: 该行原文；DB-PROBE 显示 0 个载体 → 23514（不允许）。
Impact: 仅文档可读性；数据库与实现均正确。
Expected: 改为「两列均**可空**（列级 nullable），但由 CHECK 保证恰一列非空」。
```

### REV-4

```text
Severity: NOTE
Owner: 无（无需动作）
Location: docs/product/domain-model.yaml > must_not_assume
Problem: 「容器绑定运行载体是必选的」仍保留于 must_not_assume，仅追加「…已确认为必选且恰好一个；本条不再适用」。
Evidence: diff 该行。与同列表既有惯例（如「Excel 导入支持部分成功（已裁定为 All-or-Nothing）」）一致。
Impact: 无；不构成缺陷。
Expected: 保持现状即可。
```

---

## Existing Defects

Tester 报告 `Defects: None`。逐项复核：**无 Tester 已报告但被低估或漏判的缺陷**。Tester 的严重程度评定与本次独立结论一致；本次额外发现的仅为文档 / 元数据层面的 LOW/NOTE（REV-1~REV-4），均不影响产品行为。

---

## Non-blocking Follow-ups

1. 将 `project-plan.yaml > F007.git.head_commit` 更新为已批准 SHA（REV-1）。
2. 同步 `domain-model.md §6`（REV-2）。
3. 修正 `csm-v1-schema-design.md` 第 442 行措辞（REV-3）。
4. F008 落地时向 `CONTAINER_ACTIVE_CHILD_CHECKS` 追加「活跃 Service」检查并补端到端（NQ-9）；F011 复用同一套领域校验（NQ-10）。
5. 承 F014 已知残余风险：静态 guard 对运行期动态 SQL / 动态路由构造无穷举覆盖。

---

## Unreviewed Areas

1. **多 uvicorn worker / 跨进程并发压测**：并发以多连接 / 线程度量行锁协议，未做多 worker 压测（无产品需求）。
2. **浏览器级 E2E / 真实 DOM / 视觉**：无浏览器自动化环境；前端经 vitest（happy-dom）+ 本次三连验证，未在真实浏览器观察网络与渲染。
3. **全量后端 798 用例**：本次运行受影响范围 263 用例（含全部 F007 与受影响 guard / 迁移），**未**重跑完整 798。
4. **Container 自身非空子检查 409 分支的真实触发**：`CONTAINER_ACTIVE_CHILD_CHECKS` 为空，本 Feature 内不可达（契约明示），仅以静态 / AST guard 证明声明与传入可失败。

---

## 结论

```text
APPROVED WITH FOLLOW-UP
```

**理由**：

- 不存在 BLOCKER / HIGH / 必须当前修复的 MEDIUM；存在的 LOW / NOTE 均为**文档与计划元数据**层面，不影响产品行为、领域规则、数据库安全或质量门。
- AC-01~AC-44 **全部 PASS**，且关键不变式（多态载体「恰好一个」、AC-15 跨类型同数值 id 不冲突、载体内唯一 / 大小写敏感 / 软删释放、双载体父删子拦、并发孤立记录=0）由评审**独立直连真实 PostgreSQL + 独立运行并发用例**证实，未采信 Tester 措辞。
- 测试可信（真实 DB / 真实并发 / 结构 guard 双层、无迎合实现、无删减既有 guard 测试）；实现未超范围；guard 演进的收窄仅为已合法化 token 的移除，全局扫描范围未收窄。
- 批准**仅对** Feature HEAD `2c383a9`、Base `06b3c5b`、merge-base `06b3c5b` 有效。上述 LOW 项由协调器 / Database 在最终状态提交中修正。后续代码、契约或 Base 变化须重新测试 / Review。

GIT: NONE
