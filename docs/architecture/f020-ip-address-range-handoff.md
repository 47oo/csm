# Architecture Handoff — F020 IP 地址范围段（地址池）管理

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-20
> Feature: **F020 — IP 地址范围段（地址池）管理**（E02，P1，`depends_on: [F001, F005]`，均 DONE）
> Product Source: `docs/product/handoffs/f020-ip-address-range.md`（`READY FOR ARCHITECT`）；`requirements.md` §12 **R-IP-004**；`domain-model.md` §5.7 / §8 / §9；`decisions_required[DEC-023].resolution`（第 1~6 项）
> 依赖 ADR: `adr-0002`（数据库选型 / 唯一性 / 无触发器）、`adr-0003`（标识与寻址）、`adr-0004`（软删与唯一性释放）、`adr-0005`（认证）
> 同级权威：`docs/api/f020-ip-address-range.md`（本 Feature API），`docs/database/f020-ip-address-range-migration.md`（数据库设计）

---

## Feature

IP 地址范围段（地址池）管理：为每个 Cluster 登记、查询、修改、逻辑删除多个 `start–end`（含两端，IPv4）范围段。**不含 IP 分配**（F021，BLOCKED）。

- `layers = {database: true, backend: true, frontend: true}`
- `Contract = REQUIRED` → 本次落盘 `docs/api/f020-ip-address-range.md`，**Status = READY**
- 依赖 F001（Cluster 归属与活跃性）、F005（既有 IPAddress 模型 / 字面精确比较立场 / 受控 `cluster_id` 推导）

---

## Context

### 目标

把「每个 Cluster 有哪些合法地址段」变成统一、可查询、可维护的资源事实，替代分散的 Excel 约定，并为 F021 提供基础。F020 只做**范围段 CRUD + 删除守卫 + 不重叠强制**，**不产生任何分配行为**。

### 对现有系统的影响（已核实）

- **已有**：`backend/app/ip_addresses/**`（IPAddress CRUD、`derive_cluster_id` 受控推导、`ux_ip_addresses_cluster_ip_active`）；`backend/app/deletion/service.py::soft_delete`（系统内**唯一**写 `deleted_at` 的路径）；`backend/app/deletion/checks.py::ActiveChildCheck`；`backend/app/ip_addresses/deletion.py`（`has_active_ip_addresses` / 空元组声明）；`backend/app/clusters/deletion.py::CLUSTER_ACTIVE_CHILD_CHECKS`；`backend/app/db/active.py`；`backend/app/common/pagination.py`；`backend/app/common/sqlstate.py`（SQLSTATE → HTTP 单一映射）；`backend/app/common/errors.py`；migration head `0008_f008_services`；`frontend/src/api/**`、既有 `*Page.vue` / `*FormDialog.vue` 套件；既有 guard 测试套件。
- **不存在**：任何 IP 池 / 范围段 / 网段 / CIDR 表、列、端点或前端入口；`ip_addresses` 无范围外键、无状态、无格式约束。
- **本次新增**：新表 `ip_address_ranges`；`app/ip_address_ranges/**` 模块；契约 `docs/api/f020-ip-address-range.md`；`btree_gist` 扩展；SQLSTATE `23P01` 映射；`CLUSTER_ACTIVE_CHILD_CHECKS` 追加范围段检查。
- **本次不修改**：`ip_addresses` 表结构 / 语义、R-IP-001~003、§22 大小写语义、F005 契约的 `ip_address` 自由文本立场（仅 §非目标「IP 池 / 网段」一句按 Deliverable 4 精确修订）。

### 方案要点

1. **新表 `ip_address_ranges`**：`cluster_id` + 数值化 `start_ip`/`end_ip`（`BIGINT`，IPv4 canonical 数值）+ 时间戳 + `deleted_at`；**无 status**。
2. **同 Cluster 不重叠**由 **Postgres 排它约束**（`EXCLUDE USING gist (cluster_id WITH =, int8range(start_ip,end_ip,'[]') WITH &&) WHERE deleted_at IS NULL`）作为**最终权威**（需 `btree_gist`），应用层预检仅用于返回友好 `409`。**不引入触发器**（ADR-0002）。
3. **删除守卫**复用 `soft_delete` 的 `ActiveChildCheck` 机制（唯一软删写路径），以派生条件「同 Cluster 活跃 IP 字面落在范围内」表达，**无部分写入**。
4. **IPv4 解析 / 规范化**为独立纯函数模块；**不触碰** `ip_addresses.ip_address`（R-IP-004 显式边界）。
5. API 为 `POST/GET/GET{id}/PATCH{id}/DELETE{id}` `/api/ip-address-ranges`，字段封闭为 `{id, cluster_id, start_ip, end_ip, created_at, updated_at}`。

---

## Domain Impact

- **新增领域对象**：`IPAddressRange`（IP 地址范围段 / 地址池），归属 `Cluster`（N:1 必选，不跨 Cluster 共享）。无状态（Q-002=B）。
- **不使用**既有 `IPAddress` 的任何字段变更；范围段**不建立**到 `IPAddress` 的外键或载体关系（判定是派生条件，非 FK）。
- **新增资源关系**：`Cluster 1 ── N IPAddressRange`（由 `ip_address_ranges.cluster_id` 表达）。
- **不修改**任何既有领域对象、状态模型、唯一性规则（R-IP-001~003 不变）。

---

## Data Layer Impact

需要新增**一张表** + **一个扩展** + migration `0009`：

- `ip_address_ranges`（7 列：`id` / `cluster_id` / `start_ip` / `end_ip` / `created_at` / `updated_at` / `deleted_at`；无 status / name / description）。
- 同 Cluster 活跃不重叠：**排它约束**（最终权威）。
- `start_ip <= end_ip`：DB `CHECK`（最终权威）+ 应用层预检（400）。
- IPv4 合法性：**应用层严格解析**（400）；DB 以 `BIGINT` + `CHECK (0 <= x <= 4294967295)` 兜底数值范围。
- 软删：`deleted_at TIMESTAMPTZ NULL`，复用 F014 唯一写路径；排它约束带 `WHERE deleted_at IS NULL` predicate（已删范围不参与重叠）。
- **无数据迁移**（首次建表）；**无 CASCADE**；FK `RESTRICT`。
- 完整规格见 `docs/database/f020-ip-address-range-migration.md`。

---

## Backend Work

新增 `backend/app/ip_address_ranges/**`（`model` / `schemas` / `repository` / `service` / `router` / `deletion` / `ipv4`），并做三处既有集成：

1. **CRUD 领域服务**
   - `POST`：对父 Cluster 行取 `FOR SHARE` 并确认活跃（未命中 → 404）；严格解析 `start_ip`/`end_ip` 为数值并校验 `start <= end`（否则 400）；应用层重叠预检 → 友好 `409 OVERLAP`；插入；`ex_...` 排它约束为最终权威（`23P01` → `409 OVERLAP`）。
   - `GET` 列表：`page`/`page_size` + 可选 `?cluster_id=`；给定 `cluster_id` 时先确认活跃 Cluster（不存在 / 已删 → 404；存在但无活跃范围段 → 200 空集）。
   - `GET {id}` / `PATCH {id}`（仅 `start_ip`/`end_ip`，重跑解析 + 重叠校验，无部分写入）/ `DELETE {id}`。
   - 所有读取经 `app/db/active.py` 的活跃过滤。
2. **软删删除守卫**（§决策 3）：`app/ip_address_ranges/deletion.py` 提供
   - `has_active_ip_addresses_in_range(session, range_id)`（本表删除前检查）；
   - `has_active_ip_address_ranges(session, cluster_id)`（供 Cluster 删除前检查）。
   - `IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS = (has_active_ip_addresses_in_range,)`；`DELETE` 委托 `soft_delete(..., active_children=IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS)`。
   - `app/clusters/deletion.py::CLUSTER_ACTIVE_CHILD_CHECKS` 追加 `has_active_ip_address_ranges`。
3. **通用映射扩展**：`app/common/sqlstate.py::SQLSTATE_MAP` 追加 `"23P01": SqlStateMapping(409, "CONFLICT", "OVERLAP", "范围段重叠")`（**additive**，无既有分支使用 23P01）。
4. `app/ip_address_ranges/ipv4.py`：`parse_ipv4` / `format_ipv4` / `extract_ipv4_for_guard` 三个**纯函数**（单一实现，不含 DB / HTTP）。
5. `app/main.py` 挂载 `ip_address_ranges.router`（`/api` 前缀下，认证中间件自动覆盖）。

**不实现**：任何分配 / 占用 / 耗尽 / 使用率 / CIDR / IPv6 语义；不写 `ip_addresses`；不新增第二条 `deleted_at` 写入路径。

---

## Frontend Work

新增范围段管理 UI（沿用既有 `*Page.vue` / `*FormDialog.vue` / `src/api` 模式）：

- **入口**：Cluster 上下文中的「IP 地址范围段」页（或列表），以及全局 `/ip-address-ranges` 列表。
- **列表页**：调用 `GET /api/ip-address-ranges?cluster_id=...&page=...`；展示 `start_ip – end_ip`、`cluster_id`、`created_at`/`updated_at`（作为不透明字符串）。
- **详情 / 登记（`POST`）/ 修正（`PATCH`）/ 删除（`DELETE`）**：字段仅 `cluster_id`（登记时）/ `start_ip` / `end_ip`；**不出现** `status` / `name` / `description`。
- **三态**：
  - Loading：加载骨架 / 指示器；
  - Empty：父 Cluster 存在但无活跃范围段 → 列表空态（**不得**渲染为错误）；
  - Not Found：`?cluster_id=` 对应的 Cluster 不存在 / 已删 → 独立错误态（与 Empty **不同**）。
- **错误按 `error.code` 分支**（不解析 `message`）：
  - `VALIDATION_ERROR` → 表单字段级提示（`details[].field`）；
  - `NOT_FOUND` → 资源 / 父不存在或已删；
  - `CONFLICT + details[].code == "OVERLAP"` → 「与该 Cluster 已有范围段重叠」；
  - `CONFLICT + details[].code == "ACTIVE_CHILDREN_EXIST"` → 「范围内仍有活跃 IP，无法删除」；
  - `UNAUTHENTICATED` → 既有登录跳转。
- **不在客户端实现** IPv4 范围重叠预判 / start<=end 业务校验（由服务端裁决，§21）；客户端只做基础类型/必填提示。

---

## API Contract

### Status

```text
READY
```

### Contract

完整契约正文：**`docs/api/f020-ip-address-range.md`**（Status = READY）。摘要：

| 端点 | Method | 摘要 |
|---|---|---|
| `/api/ip-address-ranges` | `POST` | 登记范围段；`201`，字段封闭 `{cluster_id,start_ip,end_ip}` 入参 |
| `/api/ip-address-ranges` | `GET` | 列表 + 分页（`page`/`page_size`）+ 可选 `?cluster_id=` |
| `/api/ip-address-ranges/{id}` | `GET` | 按 `id` 读取；不存在 / 已删 → `404` |
| `/api/ip-address-ranges/{id}` | `PATCH` | 修正 `start_ip`/`end_ip`；重跑重叠校验 |
| `/api/ip-address-ranges/{id}` | `DELETE` | 逻辑删除；范围内有活跃 IP → `409 ACTIVE_CHILDREN_EXIST` |

资源表示（封闭，恰 6 字段）：

```json
{ "id": 7, "cluster_id": 3, "start_ip": "10.0.0.1", "end_ip": "10.0.0.255",
  "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-20T10:00:00Z" }
```

稳定错误判别值：`VALIDATION_ERROR` / `NOT_FOUND` / `CONFLICT`（`details[].code ∈ {OVERLAP, ACTIVE_CHILDREN_EXIST}`）/ `UNAUTHENTICATED`。

---

## Test Work

Testing Agent 必须验证（至少）：

**功能与契约**
- AC-01~AC-22 逐条（认证 / 字段封闭 / `cluster_id` 活跃性 / `start<=end` / IPv4 合法性与规范化 / 同 Cluster 重叠拒绝 / 跨 Cluster 同范围共存 / PATCH 重校验 / 软删 / 软删释放重叠 / 删除守卫 / 无状态 / 列表 Empty / 详情 404 / 已删排除）。
- 响应字段集合**恰为** `{id, cluster_id, start_ip, end_ip, created_at, updated_at}`（无 `status`/`deleted_at`/`name`）。
- 请求携带未确认字段 → `400`，且**不产生记录**。
- 重叠 `409` 的 `details[].code == "OVERLAP"`；删除守卫 `409` 的 `details[].code == "ACTIVE_CHILDREN_EXIST"` 且目标行 `deleted_at IS NULL`（无部分写入）。

**必须独立证伪项（绕过应用层直连数据库）**
1. 直连插入同 Cluster 两条**活跃**重叠范围 → 必须抛 `23P01`（证明排它约束是真正权威，而非应用层）。
2. 直连插入跨 Cluster 完全相同范围 → **成功**（证明唯一性边界是 Cluster）。
3. 直连插入 `start_ip > end_ip` → 抛 `23514`（证明 DB CHECK）。
4. 直连插入 `start_ip < 0` 或 `end_ip > 4294967295` → 抛 `23514`。
5. 软删一条范围后，可插入与之重叠的活跃范围（证明 predicate `deleted_at IS NULL` 生效）。
6. `information_schema.columns`：`ip_address_ranges` 列集合**恰为 7 列**，**不含** `status` / `name` / `description` / CIDR / IPv6 列。
7. `pg_constraint`：存在排它约束 `ex_ip_address_ranges_active_no_overlap`（`contype='x'`）、`ck_ip_address_ranges_bounds`（`contype='c'`）；**无触发器**（`information_schema.triggers` 0 行）。
8. 漂移回归（恒 0）：同 Cluster 活跃范围两两不重叠

   ```sql
   SELECT a.id AS a_id, b.id AS b_id
   FROM ip_address_ranges a
   JOIN ip_address_ranges b
     ON a.cluster_id = b.cluster_id AND a.id < b.id
    AND a.deleted_at IS NULL AND b.deleted_at IS NULL
    AND a.start_ip <= b.end_ip AND a.end_ip >= b.start_ip;   -- 期望 0 行
   ```
9. 不变式回归（恒 0）：「活跃范围段挂在已软删 Cluster 下」不得出现：

   ```sql
   SELECT count(*) FROM ip_address_ranges r JOIN clusters c ON c.id = r.cluster_id
   WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL;  -- 期望 0
   ```
10. 静态 guard：系统内写 `deleted_at` 的代码路径**仍唯一**（`app/deletion/service.py`）；`ip_address_ranges` 模块不出现 `deleted_at =` 赋值；`ip_addresses.ip_address` 未新增解析 / 校验 / 归一化（既有 guard 套件 + 新增 F020 guard）。
11. `alembic upgrade head` 幂等、`downgrade 0008_f008_services` / `upgrade head` 可重建；既有表结构不变。
12. 契约一致性：`docs/api/f020-ip-address-range.md` 已落盘且 `status=READY`，实现与契约无分裂（AC-29）。

**删除守卫语义专项**
- 同 Cluster 活跃 IP 字面落在范围内 → `DELETE` → `409`，行未变；软删该 IP 后 → `DELETE` → `204`。
- `ip_address` 为 `10.0.1.1/16`（含前缀）且地址部分落在范围内 → 视为命中（守卫语义，见决策 4）。
- `ip_address` 为 `abc` / 空串 / 含前导空白 → 守卫**跳过**、**不得 500**；范围可删。

**并发**
- 并发「登记范围段」×「删除其 Cluster」：恰好一个成功；结束后不变式 9 = 0。
- 并发同 Cluster 两条重叠范围：至多一条成功（一条 `409 OVERLAP`），无 5xx。

---

## Technical Decisions

### CONFIRMED

- **C-01 新表承载**：范围段为独立资源表 `ip_address_ranges`，`cluster_id` FK → `clusters(id)` `RESTRICT`（R-IP-004：恰属一个活跃 Cluster；DEC-023 第 3 项）。
- **C-02 字段封闭**：`{id, cluster_id, start_ip, end_ip, created_at, updated_at}`；无 status / name / description（R-IP-004；DEC-023 第 1/5/7 项）。
- **C-03 无状态**：无 `status` 列 / 枚举 / 过滤（Q-002=B；DEC-023 第 5 项）。
- **C-04 软删**：`deleted_at`，复用 `soft_delete` 唯一写路径，不物理删、无 undelete、不级联（R-DELETE-001/003/005；ADR-0004）。
- **C-05 跨 Cluster 可重复、同 Cluster 不重叠**（R-IP-004；DEC-023 第 2 项）。
- **C-06 不新增 DB 层「范围必须覆盖已分配 IP」硬约束**（DEC-023 第 6 项）。
- **C-07 `ip_address` 自由文本登记语义不变**（R-IP-004；AC-23）。
- **C-08 V1 仅 IPv4、无 CIDR、无 IPv6**（DEC-023 第 1 项；AC-26）。
- **C-09 分配不属本 Feature**（F021，BLOCKED）。

### REQUIRED

- **R-01**：父 Cluster 必须在写入前确认**活跃**（不存在 / 已删 → 404，非 5xx）；范围段写入对 Cluster 行取 `FOR SHARE`。
- **R-02**：`start_ip <= end_ip` 必须有 DB `CHECK` 兜底 + 应用层 `400`（§21：保存前阻止，不依赖 UI）。
- **R-03**：同 Cluster 不重叠必须由**数据库**最终保证（§6；ADR-0002「数据库为最终权威」），不得仅靠应用层。实现方式见决策 2。
- **R-04**：范围段是 Cluster 的活跃子资源，**Cluster 删除守卫必须包含**「存在活跃范围段」（R-DELETE-004 泛化）。
- **R-05**：系统内写 `deleted_at` 的路径必须仍**唯一**（ADR-0004）；范围段删除只能经 `soft_delete`。
- **R-06**：`sqlstate.py` 是**唯一** SQLSTATE 映射；`23P01` 只能追加到该表，不得另立映射。
- **R-07**：`ip_addresses.ip_address` **不得**新增格式校验 / 归一化 / trim（R-IP-004 显式边界；AC-23）。

### PROPOSED

- **P-01 数值化存储**：`start_ip` / `end_ip` 以 `BIGINT` 存储 IPv4 的 canonical 数值（`0..4294967295`），API 层渲染为 dotted-quad。理由：使排它约束可直接用 `int8range`，消除「文本 ↔ 数值」第二份事实；规范化由解析函数保证。**代价**：DB 内不可直读 dotted-quad（以列注释与文档补偿）。**备选**：存 canonical `TEXT` + `BIGINT` 两列（需额外一致性 CHECK），不采用。
- **P-02 排它约束 + `btree_gist`**（决策 2）：采用 Postgres `EXCLUDE` 作为不重叠权威。**代价**：① 新增扩展 `btree_gist`；② migration 用户需有 `CREATE EXTENSION` 权限（部署风险，见 Risks）；③ 追加 `23P01` 映射。
- **P-03 IPv4 解析为自有严格函数**，不依赖 `ipaddress.IPv4Address`（其拒绝前导零，与 AC-09 冲突）。
- **P-04 列表按 `?cluster_id=` 限定**（与 F004/F005 父限定读取一致），而非新增 `/clusters/{id}/ip-address-ranges` 子路由。
- **P-05 重叠 `details[].code = "OVERLAP"`；删除守卫 `details[].code = "ACTIVE_CHILDREN_EXIST"`**（后者复用既有稳定值）。
- **P-06 删除守卫对 `ip_address` 的解析语义**（决策 4）：取 `/` 之前的地址部分严格解析为 IPv4；解析失败则**跳过**（不阻断、不 500）。

### OPEN

- 见 §Open Technical Questions（均 **Non-blocking**）。

---

## Risks

- **风险 1（部署）**：`btree_gist` 需 migration 用户具备扩展创建权限；若部署环境的应用 DB 用户非 superuser 且未预装扩展，`alembic upgrade` 会失败。**缓解**：部署文档记录「由 DBA 预执行 `CREATE EXTENSION btree_gist`，或授予应用用户 `CREATE` on database」；migration 用 `IF NOT EXISTS`。此风险由选择 P-02 引入（见 Open TQ-1 的退化路径）。
- **风险 2（删除守卫的并发窗口）**：范围段删除与「在其 Cluster 内登记落在范围中的新 IP」不互相串行；极端并发下可能出现「活跃 IP 存在、其范围已被删」。**这不违反任何已确认产品规则**（DEC-023 第 6 项明确不要求 DB 硬约束覆盖一致性），且由漂移检测发现。**不得**为此修改 F005 的 IP 创建路径或引入触发器。
- **风险 3（守卫覆盖率）**：非 IPv4 或非 `A.B.C.D` 前导形式的 `ip_address` 自由文本不参与守卫判定（决策 4）。若用户实际大量使用此类字面值，守卫可能「漏判」。见 Open TQ-2。
- **风险 4（性能，低）**：删除守卫在应用层读取该 Cluster 的全部活跃 `ip_address` 字面值并解析。规模 10⁵ 总量、50 并发下可接受；若单 Cluster 活跃 IP 达 10⁴~10⁵ 且删除频繁，需改为批量 / 下推。当前不优化。

---

## Constraints

- **不得**引入触发器；**不得**使用 `ON DELETE CASCADE`；**不得**新增第二套软删 / SQLSTATE 映射（ADR-0002 / ADR-0004 / F012）。
- **不得**修改 `ip_addresses` 表结构、R-IP-001~003、§22 大小写语义、F005 契约的 `ip_address` 自由文本立场（仅按 Deliverable 4 精确修订 §非目标一句）。
- **不得**实现任何分配 / 占用判定 / 耗尽错误 / CIDR / IPv6 / 使用率 / 冲突扫描（AC-25~27；F021 范围）。
- **不得**为「不重叠」引入除 `EXCLUDE` 外的隐藏机制；**不得**在范围段模块出现第二处 `deleted_at` 赋值。
- **不得**在客户端实现业务校验（§21）。
- 本 Feature 的迁移编号必须为 `0009_f020_ip_address_ranges`，`down_revision = "0008_f008_services"`（维持单一线性 head）。

---

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

- **TQ-1（`btree_gist` 可接受性）**：若用户 / 部署方不接受新增扩展或无法授予权限，可退化为 **Degraded Design B**：去掉 `EXCLUDE`，改为「对父 Cluster 行取 `FOR UPDATE`（或 `pg_advisory_xact_lock` on `cluster_id`）串行化同 Cluster 范围段写入 + 应用层重叠校验 + SQL 漂移查询」。该退化**保留全部 API 契约与错误语义**，仅把不重叠的最终权威从 DB 移到「串行化的受控写入路径 + 回归查询」。触发条件：部署环境无法安装 `btree_gist`。**默认按 P-02 实施**；Database / Backend 阶段如遇扩展不可用，可启用退化路径而**无需重新定契约**。
- **TQ-2（守卫解析语义确认）**：P-06 对 `ip_address` 的「取 `/` 前地址部分」解释属 Architecture 对 NQ-C 的定稿。若用户认为「含前缀的 `ip_address` 不应视为落在范围内」或反之，应回到 Product 确认；**不阻塞**当前实现（当前语义已明确、可测试、不 500）。
- **TQ-3（列表默认范围）**：`GET /api/ip-address-ranges` 无 `cluster_id` 时返回全量活跃范围段（与 F005 列表一致）。未来若需「必须选定 Cluster」，属新的产品 / UX 选择，不在此定稿。

---

## Implementation Layers

```text
database: true    # 新表 + EXCLUDE 约束 + btree_gist + migration 0009
backend:  true    # 范围段 CRUD、IPv4 解析、重叠校验、删除守卫集成、sqlstate 映射
frontend: true    # 范围段列表 / 详情 / 登记 / 修正 / 删除 + 三态
```

分支范围：

- **database**：仅 `ip_address_ranges` 表 + 1 个扩展 + migration `0009`；**不改**既有表。
- **backend**：`app/ip_address_ranges/**` 新模块；`app/clusters/deletion.py` 追加 1 行检查；`app/common/sqlstate.py` 追加 1 条映射；`app/main.py` 挂载路由。
- **frontend**：范围段页面与 `src/api/ipAddressRanges.ts` 新增；沿用既有外壳 / 表格 / 对话框模式；不改其它资源页面。

---

## Implementation Order

```text
Architecture + API Contract (READY, 本文 + docs/api/f020-ip-address-range.md)
  ├─ Frontend（依契约先行，可与数据库/后端并行）
  └─ Database Design（docs/database/f020-ip-address-range-migration.md）
        → Backend（migration 0009 + app/ip_address_ranges/** + 集成）
                 ↓ 所有必需分支完成
              Tester → Reviewer
```

- Frontend 只需契约（Status = READY）即可开工。
- Backend 依赖数据库设计（本 Handoff 已给出，Database Agent 复核 migration）。
- 无数据库变更阻塞 Frontend；三态与 `error.code` 分支均由契约确定。

---

## Verification Strategy

1. **结构验证**（直连 DB）：列集合恰 7、无 status、排它约束 / CHECK 存在、无触发器、扩展存在。
2. **约束证伪**（绕过应用层）：重叠 → `23P01`；跨 Cluster 同范围成功；`start>end` / 越界 → `23514`；软删释放重叠。
3. **契约验证**：全部端点状态码与 `error.code` / `details[].code` 与 `docs/api/f020-ip-address-range.md` 一致；字段封闭；Empty 与 Not Found 可区分。
4. **不变式回归**：重叠漂移查询 = 0；「活跃范围挂已删 Cluster」= 0；`ip_addresses` 漂移查询（F005 既有）仍 = 0。
5. **守卫语义**：活跃 IP 命中 → 409 无部分写；软删后 → 204；不可解析字面值不 500。
6. **既有语义不变**：F005 全量测试与 guard 套件保持通过；`ip_addresses` 无新增格式约束。
7. **迁移**：upgrade 幂等、downgrade/upgrade 可重建、既有表不变。

---

## Handoff Status

`READY FOR IMPLEMENTATION`

（API Contract Status = `READY`；无 Blocking Open Technical Question。）
