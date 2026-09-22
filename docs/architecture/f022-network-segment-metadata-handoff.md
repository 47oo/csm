# Architecture Handoff — F022 网段自定义名称 / 子网掩码 / VLAN 标注

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect（协调器持久化）
> Date: 2026-09-21
> Feature: **F022 — 网段自定义名称 / 子网掩码 / VLAN 标注**（E02，P1，`depends_on: [F020]` = DONE）
> Product Source: `docs/product/handoffs/f022-network-segment-metadata.md`（`READY FOR ARCHITECT`）；`requirements.md` §12 **修订后的 R-IP-004**（2026-09-21 DEC-024 裁定）；`domain-model.md` §5.7 / §8 / §9；`decisions_required[DEC-024].resolution`
> 依赖 ADR: `adr-0002`（数据库 / 大小写敏感唯一性 / 无触发器）、`adr-0003`（标识与寻址）、`adr-0004`（软删与唯一性释放）、`adr-0005`（认证）
> 同级权威：`docs/api/f020-ip-address-range.md`（**纯增量修订**，仍 `READY`）；`docs/database/f022-ip-address-range-metadata-migration.md`（数据库设计）

---

## Feature

为 F020 已交付的 **IP 地址范围段（地址池，`ip_address_ranges`）** 新增 **3 个可选元数据字段** `name` / `subnet_mask` / `vlan`，并据此**精确修订** R-IP-004 与 F020 契约。**不新建实体，不改变既有范围段语义，不改变 F021 分配行为。**

- `layers = {database: true, backend: true, frontend: true}`
- Contract = **REQUIRED** → 修订 `docs/api/f020-ip-address-range.md`（纯增量），**Status 维持 `READY`**。
- 依赖 F020（DONE，merge `e4291a1`）。F021（DONE，merge `011d05d`）**非前置**；本 Feature 不触碰分配路径。

---

## Context

### 目标

让范围段具备**业务可读标识（名称）与网络参数（掩码 / VLAN）**，同时不引入第二套事实、不改变重叠 / 软删 / 删除守卫 / 无状态 / IPv4 规范化 / R-IP-001 / F021 分配语义。仅新增一条唯一性：`name` 同 Cluster 活跃唯一。

### 对现有系统的影响（已核实于 HEAD `4f0bfa9`）

- **已有**：`backend/app/ip_address_ranges/**`（6 文件）；`backend/app/models/ip_address_range.py`；migration head `0009_f020_ip_address_ranges`；`app/common/sqlstate.py`；`app/deletion/service.py::soft_delete`；前端范围段 API / 表单 / 列表 / 详情；既有 guard 套件（含 `tests/database/helpers.py::MIGRATION_HEAD`）。
- **不存在**：任何 `name` / `subnet_mask` / `vlan` 列、索引、端点、查询参数、前端输入；任何掩码 / VLAN 校验函数。
- **本次新增**：`ip_address_ranges` 的 3 个可空列 + `name` partial unique index + `vlan` CHECK；migration `0010`；`ipv4.py` 掩码专用纯函数；`schemas.py` / `service.py` / `repository.py` 增量；前端三字段接线；F020 契约纯增量修订；F022 guard 新增 + 既有 head guard 受控演进。
- **本次不修改**：`0001`–`0009`、其它表 / 列 / 约束 / 索引；`ip_addresses.ip_address` 自由文本立场；R-IP-001~003、R-IP-005~010；F021 契约与分配路径；重叠 / 软删 / 删除守卫 / 无状态语义。

### 方案要点

1. **扩展既有表**（`ALTER TABLE … ADD COLUMN`），3 个可空列，既有行取 `NULL`，**无回填**。
2. `name` 唯一性：**应用层预检（友好 409）+ partial unique index（最终权威）**，大小写敏感（不 `COLLATE` / 不 `lower()`），软删释放，跨 Cluster 可重复。
3. `subnet_mask`：**dotted-quad TEXT，原样存取**；合法性由 `ipv4.py` 新增掩码纯函数裁决（复用 `parse_ipv4`，**不复制第二份解析**）；**不强制**与 start–end 自洽。
4. `vlan`：`INTEGER NULL` + DB `CHECK (vlan IS NULL OR vlan BETWEEN 1 AND 4094)`；应用层整数 + 范围校验；**不唯一**。
5. 契约纯增量修订，`contract.status` 维持 `READY`；不推翻 F020 / F021。
6. **不实现、不承诺** `name` 的长度 / trim / 空串 / 字符集；不实现 CIDR / IPv6 / 网关 / DHCP / DNS / 使用率 / 分配过滤。

---

## Domain Impact

- **使用**既有对象 `IPAddressRange`，归属 `Cluster`（N:1 Mandatory）。**不新增领域对象**。
- **新增字段**（R-IP-004 2026-09-21 修订）：`name` / `subnet_mask` / `vlan`，均**可选**。
- **新增唯一性**：仅「同 Cluster 内活跃范围段 `name` 唯一」（区分大小写、软删释放、跨 Cluster 可重复）。**不新增 VLAN 唯一性**。
- **资源关系 / 状态模型 / 生命周期**不变。

---

## Data Layer Impact

一次**纯增量 migration** `0010_f022_ip_address_range_metadata`（完整规格见 `docs/database/f022-ip-address-range-metadata-migration.md`）：

- `ALTER TABLE ip_address_ranges ADD COLUMN` 3 个可空列：`name TEXT NULL` / `subnet_mask TEXT NULL` / `vlan INTEGER NULL`；既有行取 `NULL`，无回填。
- `CREATE UNIQUE INDEX ux_ip_address_ranges_cluster_name_active ON ip_address_ranges (cluster_id, name) WHERE deleted_at IS NULL AND name IS NOT NULL`（大小写敏感，不声明 `COLLATE`、不用 `lower()`）——「同 Cluster 活跃 name 唯一」的**最终权威**（ADR-0002 / ADR-0004）。
- `ALTER TABLE ip_address_ranges ADD CONSTRAINT ck_ip_address_ranges_vlan_range CHECK (vlan IS NULL OR (vlan BETWEEN 1 AND 4094))`；**不**对 `name` / `subnet_mask` 加格式 CHECK。
- **不改** `0001`–`0009`、既有列 / 约束 / 索引、其它表；**无** extension / 触发器 / CASCADE / 数据迁移 / 第二条 `deleted_at` 写入路径。

---

## Backend Work

在 `backend/app/ip_address_ranges/**` 内增量修改（**无新端点**）：

1. **`ipv4.py`**：新增掩码专用纯函数 `parse_subnet_mask(value: str) -> int`（先 `parse_ipv4`，再校验二进制连续 1 后连续 0：`m == 0 or ((m | (m - 1)) & 0xFFFFFFFF) == 0xFFFFFFFF`）；允许 `0.0.0.0` / `255.255.255.255`；非法 → `ValueError`。**复用**既有 `parse_ipv4`，不复制解析。
2. **`schemas.py`**：`IpAddressRangeCreate` 增 3 个可选字段（`name: str | None`、`subnet_mask: str | None`、`vlan: StrictInt | None`；`extra="forbid"` 不变）；`IpAddressRangeUpdate` 可变字段集合扩为 `{start_ip, end_ip, name, subnet_mask, vlan}`（可空以表达清空）；`IpAddressRangeRead` 增 3 字段。
3. **`repository.py`**：新增 `active_name_exists(cluster_id, name, *, exclude_id=None) -> bool`（活跃、同 Cluster、字面等值、排除自身，仅用于友好 409）；`create` / `update` 支持新字段。
4. **`service.py`**：`create` 校验 mask / vlan / name 唯一后插入；`update` 按 `model_fields_set` 判定（`start/end` 的 `null` → 400；`name`/`subnet_mask`/`vlan` 的 `null` → 清空；空 body → 400），重跑对应校验，无部分写入。
5. **`router.py`**：**无新端点、无新查询参数**；`response_model=IpAddressRangeRead` 自动带出新字段。
6. **不实现**：`name` 长度 / trim / 空串 / 字符集约束；掩码自洽校验；VLAN 唯一性；分配过滤；CIDR / IPv6 / 网关 / DHCP / DNS / 使用率。

---

## Frontend Work

在既有范围段 UI 增量接线：

- **API 类型**：`IpAddressRangeRead` 加三字段；`CreateBody` 三字段可选；`UpdateBody` 三字段可选且可 `null`（清空）。
- **列表页**：新增「名称 / 子网掩码 / VLAN」列；`null` 显示占位（`—`）；**不新增筛选 / 排序参数**。
- **详情页**：展示三字段（`null` → `—`）。
- **登记 / 编辑对话框**：三个可选输入（名称文本、掩码文本、VLAN 数字）；create 缺省即空；edit 预填，清空即提交 `null`；快照式提交 5 个可变字段。
- **三态**：Loading / Empty / Not Found 语义不变（Empty 与 Not Found 仍可区分）。
- **错误按 `error.code`（结合 `details[].code`）**：`VALIDATION_ERROR` 字段级（`field ∈ {name, subnet_mask, vlan, start_ip, end_ip}`）；`CONFLICT + OVERLAP` 范围重叠；`CONFLICT + DUPLICATE` 同名网段；`CONFLICT + ACTIVE_CHILDREN_EXIST` 删除守卫；`NOT_FOUND` / `UNAUTHENTICATED` 不变。**不解析 `message`**。
- **不在客户端实现** name 唯一 / 掩码合法性 / VLAN 范围业务校验（§21）。

---

## API Contract

### Status

```text
READY
```

### Contract

完整契约：**`docs/api/f020-ip-address-range.md`**（纯增量修订后，Status 维持 `READY`）。修订要点：

- 端点集与路径**不变**（5 个端点）。
- 资源表示**扩为 9 字段**：`{id, cluster_id, start_ip, end_ip, name, subnet_mask, vlan, created_at, updated_at}`。
- `POST` request 增 3 个**可选**字段；`PATCH` 可变字段集合扩为 `{start_ip, end_ip, name, subnet_mask, vlan}`（`null` 清空三个可选字段）。
- 新增稳定判别值：`409 CONFLICT` + `details[].code = "DUPLICATE"`（`field = "name"`，应用层路径）；非法掩码 / VLAN → `400 VALIDATION_ERROR` + `details[].field ∈ {"subnet_mask","vlan"}` + `code = "INVALID"`。
- `23505` 经**既有** `app/common/sqlstate.py` 通用映射（**不新增 SQLSTATE 键**）→ `409 CONFLICT / DUPLICATE`，**永不 500**。

稳定错误判别值汇总（本资源）：`VALIDATION_ERROR` / `NOT_FOUND` / `CONFLICT`（`details[].code ∈ {OVERLAP, DUPLICATE, ACTIVE_CHILDREN_EXIST}`）/ `UNAUTHENTICATED`。

---

## Test Work

Testing Agent 必须验证（至少）：

**契约与功能（逐条对应 AC-01 ~ AC-30）**
- 认证；响应字段集合**恰为** 9 字段；请求字段封闭；三字段缺失 → `201` 且响应为 `null`；三字段往返一致。
- `name`：同 Cluster 活跃同名 → 非 5xx、不产生记录、`409` + `details[].code == "DUPLICATE"`（应用层路径 `field == "name"`）；跨 Cluster 同名均 `201`；`web` / `Web` 均 `201`（§22）；软删释放；空串 / 含首尾空白当前被接受（**不得**断言为合法）。
- `subnet_mask`：合法掩码接受并原样回读；非法掩码 → `400` + `field == "subnet_mask"`；掩码与 start–end 不自洽仍 `201`；不接受 CIDR / IPv6。
- `vlan`：`1` / `4094` → `201`；`0` / `4095` / `4096` / `-1` / `100.5` / `"100"` / `true` → `400` + `field == "vlan"`；同 Cluster 不同范围段共用 `vlan` 均 `201`；唯一性恰为 `name` 一条。
- 既有语义逐条不变：重叠 `409 OVERLAP`、软删释放、删除守卫 `409 ACTIVE_CHILDREN_EXIST`、无 `status`、IPv4 规范化、R-IP-001~003 / R-IP-005~010、分配不按掩码 / VLAN 过滤、F005 `ip_address` 立场。
- **PATCH 专项**：三字段可修正；以 `null` 清空；`start_ip`/`end_ip` 提供 `null` → `400`；空 body `{}` → `400`；修改 `name` 为同 Cluster 已用名 → `409 DUPLICATE`，无部分写入；修改为自己当前 `name` → `200`。

**必须独立证伪项（绕过应用层直连 DB）**
1. 直插同 Cluster 两条**活跃同名** `name` → `23505`。
2. 同 Cluster `web` / `Web` 直插 → 均成功（大小写敏感，无 `COLLATE` / `lower()`）。
3. 软删一条后直插同名 → 成功（predicate `deleted_at IS NULL`）。
4. 直插 `vlan = 0` / `4095` / `5000` → `23514`（DB CHECK）。
5. `information_schema.columns`：`ip_address_ranges` 列集合**恰为 10 列**（7 + 3），不含 `status` / `description` / `cidr` / `prefix_length` / `gateway` / `dhcp` / `dns`。
6. `pg_indexes`：unique 索引集合**恰为** `{ux_ip_address_ranges_cluster_name_active}`；CHECK 集合**恰为** `{ck_ip_address_ranges_bounds, ck_ip_address_ranges_vlan_range}`；排它约束仍恰为 `{ex_ip_address_ranges_active_no_overlap}`；**无触发器**。
7. `indexdef` 的 `ux_ip_address_ranges_cluster_name_active` **不含** `COLLATE` / `lower(`，谓词含 `deleted_at IS NULL` 与 `name IS NOT NULL`。
8. 静态 guard：写 `deleted_at` 路径仍唯一（`app/deletion/service.py`）；`ip_address_ranges` 模块仍无 `deleted_at` 赋值。
9. 既有重叠 / 删除守卫 / R-IP-001 / F021 行为不变（F020 / F021 全量测试与 guard 通过）。
10. migration `upgrade head` 幂等；`downgrade 0009` / `upgrade head` 可重建；`alembic check` 无漂移；`0001`–`0009` 未改。
11. 无新增不属于本 Feature 的表 / 列 / 索引 / 触发器 / CASCADE / SQLSTATE 键。
12. 静态 guard「不实现」：不出现 name 长度 / trim / 空串 / 字符集校验、掩码自洽校验、VLAN 唯一性、CIDR / IPv6 / 网关 / DHCP / DNS / 使用率字段或端点。

**Guard 受控演进（只增不弱）**：`tests/database/helpers.py` `MIGRATION_HEAD` → `0010…`；各 head 断言 `0009` → `0010`；`EXPECTED_COLUMNS` / `READ_FIELDS` / `TABLE_COLUMNS` +3；`FORBIDDEN_TOKENS` 仅移除本 Feature 已确认合法的 `name` / `vlan`（保留 `status` / `description` / `cidr` / `gateway` / `dhcp` / `dns` / 容量）；约束 / 索引集合断言更新；新增 `tests/test_ip_address_range_metadata_guards.py` 可失败 guard。

---

## Technical Decisions

### CONFIRMED

- **C-01 扩展既有表**：`ip_address_ranges` 加 3 个可空列；不新建实体 / 表。
- **C-02 字段封闭**：9 字段；无 `description` / `status` / CIDR / IPv6 / 网关 / DHCP / DNS / 使用率。
- **C-03 `name`**：可选；同 Cluster 活跃唯一；区分大小写；软删释放；跨 Cluster 可重复；长度 / trim / 空串 / 字符集未定义（不实现、不承诺）。
- **C-04 `subnet_mask`**：可选；dotted-quad IPv4 合法掩码；V1 仅 IPv4、不用 CIDR；不强制与 start–end 自洽。
- **C-05 `vlan`**：可选；整数 `1`–`4094`；不唯一。
- **C-06 唯一性边界**：仅新增 name 同 Cluster 活跃唯一。
- **C-07 既有语义不变**。
- **C-08 契约纯增量修订**，`Status = READY`。

### REQUIRED

- **R-01**：`name` 同 Cluster 活跃唯一必须由**数据库**最终保证（partial unique index）。
- **R-02**：`name` 比较**大小写敏感**；**不得** `COLLATE`、**不得** `lower()`。
- **R-03**：`vlan` `1`–`4094` 必须由 DB `CHECK` 兜底 + 应用层 `400`。
- **R-04**：`23505` 只能经既有 `app/common/sqlstate.py` 单一映射；不得新增 SQLSTATE 键。
- **R-05**：写 `deleted_at` 路径仍唯一（`app/deletion/service.py`）。
- **R-06**：IPv4 / 掩码解析**只有一份实现**（`app/ip_address_ranges/ipv4.py`）。
- **R-07**：三字段修改经既有 `PATCH` 并重跑校验；无部分写入。
- **R-08**：migration `0010_f022_ip_address_range_metadata`，`down_revision = "0009_f020_ip_address_ranges"`。
- **R-09**：既有 guard 受控演进而非删除。
- **R-10**：`ip_addresses.ip_address` 无新增格式校验 / 归一化。

### PROPOSED

- **P-01** `subnet_mask` 存 `TEXT`、原样存取（不归一化），合法性仅应用层（描述性元数据）。
- **P-02** `vlan` 存 `INTEGER` + CHECK 限域。
- **P-03** `name` 唯一性 = 应用层预检（`field == "name"`）+ DB partial unique（最终权威）。
- **P-04** `PATCH` 三字段可修正、`null` 清空（与 F007 先例一致）；`start_ip` / `end_ip` 仍不可为 `null`。
- **P-05** 掩码纯函数 `parse_subnet_mask` 置于 `ipv4.py`，复用 `parse_ipv4`。
- **P-06** `name` 重复复用既有 `DUPLICATE`；掩码 / VLAN 非法用 `VALIDATION_ERROR` + `details[].field` + `code="INVALID"`。
- **P-07** 编辑对话框快照式提交 5 个可变字段。
- **P-08** `StrictInt` 校验 `vlan`（拒绝 bool / float / str）。

### OPEN

- 见 Open Technical Questions（均 Non-blocking）。

---

## Risks

- **风险 1**：空串 / 含首尾空白 `name` 当前被接受，可能与运维直觉不符；不违反已确认规则（§22 / F005 / F007 先例），契约 §7.3 明确「不承诺」。
- **风险 2**：DB 兜底 `23505` 路径的 `details[].field` 为 best-effort；应用层预检先行，产品路径 `field == "name"`。
- **风险 3**：多个既有 head guard 硬编码 `0009`，遗漏一处会红；Test Work 列出完整清单。
- **风险 4**：`alembic check` 与 partial unique index 漂移；ORM 显式 `Index(..., postgresql_where=...)` 并断言。
- **风险 5**：掩码无 DB 格式保证（仅应用层）；属描述性元数据，写入路径唯一。

---

## Constraints

- **不得**修改 `0001`–`0009`、其它表 / 列 / 约束 / 索引、既有排他约束。
- **不得**新增 SQLSTATE 键、第二条 `deleted_at` 写入路径、触发器、`CASCADE`、extension。
- **不得**实现 name 长度 / trim / 空串 / 字符集、掩码自洽、VLAN 唯一、CIDR / IPv6 / 网关 / DHCP / DNS / 使用率。
- **不得**在客户端实现 name 唯一 / 掩码 / VLAN 业务校验。
- **不得**新增超出本 Feature 的端点 / 查询参数 / 筛选 / 排序。
- **不得**复制第二份 IPv4 / 掩码解析。
- **不得**删除既有 guard 断言（只做受控演进）。
- **不得**修改 `docs/test-reports/**` 与 F021 契约。

---

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

- **TQ-1（掩码归一化）**：本 Feature 原样存取；若未来确认 canonical 化，属契约承诺变更（新 Feature）。
- **TQ-2（按名称 / 掩码 / VLAN 查询）**：本 Feature 不做筛选 / 排序 / `by-name`；`name` 非全局唯一。
- **TQ-3（`name` 最小字符约束）**：未确认即不实现、不承诺。

---

## Implementation Layers

```text
database: true    # ALTER TABLE 3 列 + name partial unique + vlan CHECK + migration 0010
backend:  true    # schemas / service / repository / ipv4 掩码纯函数（无新端点）
frontend: true    # 范围段列表 / 详情 / 登记 / 修正三字段呈现与录入 + 错误分支
```

---

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f020-ip-address-range.md 纯增量修订，READY）
  ├─ Frontend（依契约先行，可与 Database/Backend 并行；契约 Status = READY 即可开工）
  └─ Database Design（docs/database/f022-ip-address-range-metadata-migration.md）
        → Backend（migration 0010 + app/ip_address_ranges/** 增量）
                 ↓ 所有必需分支完成
              Tester → Reviewer
```

---

## Verification Strategy

1. **契约验证**：全部端点状态码、字段集合、`error.code` / `details[].code` / `details[].field` 与修订后的契约一致；三字段往返与 `null` 清空；`Status: READY` 已落盘。
2. **结构验证**（直连 DB）：列集合恰 10、CHECK 集合恰 2、unique 索引恰 1、排它约束不变、无触发器 / CASCADE / COLLATE。
3. **约束证伪**：直插同名 → `23505`；大小写不同共存；软删释放；`vlan` 越界 → `23514`。
4. **不变式回归**：既有 R-1 / R-2 / R-3 漂移查询恒 0。
5. **既有语义不变**：F020 全量 + F021 全量 + 各 head guard 通过。
6. **并发**：并发同名登记至多一条成功（另一条 `409 DUPLICATE`），无 5xx。
7. **迁移**：upgrade 幂等、downgrade 0009 / upgrade 可重建、`alembic check` 无漂移、`0001`–`0009` 未改。
8. **静态 guard**：F022 新 guard 可失败；既有 guard 受控演进；唯一软删写入路径与唯一 IPv4 解析实现保持。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

（API Contract Status = `READY`；无 Blocking Open Technical Question。）