# Architecture Handoff — F023 自动分配时指定 IP 地址范围段

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-22
> Feature: **F023 — 自动分配时指定 IP 地址范围段**（E02，P1，`depends_on: [F020, F021]`，均已 DONE）
> Product Source: `docs/product/handoffs/f023-ip-range-selection.md`（`READY FOR ARCHITECT`）；`requirements.md` §12 **R-IP-006 / R-IP-009（修订）**，R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010 不变；`domain-model.md`
> 依赖 ADR: `adr-0002`（数据库最终权威 / 受控 `cluster_id` 写入路径 / 无触发器）、`adr-0003`（标识与寻址 / 错误契约）、`adr-0004`（软删与唯一性释放）、`adr-0005`（认证）
> 同级权威：`docs/api/f021-ip-address-allocation.md`（**已修订**，Status = READY，2026-09-22）
> 被修订契约：`docs/api/f021-ip-address-allocation.md`（§1 / §3.1 / §4.1 / 新 §4.6 / §6.1 / §6.5 / §8 / §9 / §10 与文件头）

---

## Feature

把自动分配从「目标 Cluster **全部活跃范围段并集**内取全局最小未占用 IPv4」改为「**必须显式指定一个活跃范围段**；**仅在该所选单个范围段内**取数值最小未占用 IPv4；所选范围段耗尽则 `409 CONFLICT + NO_AVAILABLE_IP` 且**不回退**」。请求新增**必填**字段 `ip_address_range_id`；产物仍是一条现有 IPAddress；手动分配与 F005 登记端点不变；**无数据库变更**。

- `layers = {database: false, backend: true, frontend: true}`
- `Contract = REQUIRED` → 本次修订 `docs/api/f021-ip-address-allocation.md`，**Status = READY**

---

## 范围与前提

**本次包含**
1. 自动分配请求新增必填 `ip_address_range_id`（integer；请求 schema 仍封闭）。
2. 所选范围段校验：必须存在、**活跃**、且**恰属于**目标 NIC 推导出的 Cluster；不满足 → 非 5xx、无写入。
3. 单范围取最小：仅在所选范围段内取数值最小未占用 IPv4。
4. 耗尽硬失败：`409 CONFLICT + NO_AVAILABLE_IP`，不回退、不跨 Cluster、无部分写入。
5. 前端：自动分配入口必须**必选**一个范围段；三态与错误按 `error.code` / `details[].code` 分支。
6. 契约一致性：修订后的 f021 契约持久化为 READY。

**本次明确不包含**
- 修改 `/allocate-manual`（用户明确排除）或 F005 `POST /api/ip-addresses`。
- 修改 R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010 的任何一条。
- 新增唯一性 / 新增数据库 Schema / migration。
- CIDR / IPv6 / 保留地址 / 排除表 / 使用率；范围段自动选择 / 默认范围 / 记忆 / 按掩码 / VLAN 过滤。
- 新的分配 / 预留实体、回收工作流、审计 / 历史。

**前提**（均已核实于 HEAD `dd159f3`）
- F020 / F021 已 DONE；`app/ip_allocations/**`、`app/ip_addresses/**`、`app/ip_address_ranges/**` 已存在；`IpAddressRangeRepository.get_active(range_id)` 已存在并可复用。
- migration head = `0010_f022_ip_range_metadata`。
- 前端已存在分配对话框与范围段 / BareMetal / NIC 客户端读取函数。

---

## 契约修订摘要

`docs/api/f021-ip-address-allocation.md`（Status = READY，2026-09-22）实际修改小节：文件头、§1（新增「必须指定范围段」条，改写「单范围取最小 / 耗尽不回退」）、§3.1（请求新增必填 `ip_address_range_id`；语义与错误表修订）、§4.1（耗尽限定所选范围段）、新增 §4.6（范围段不可用）、§6.1（校验顺序）、§6.5（并发窗口措辞）、§8 / §9（状态码与 Not Found / Empty）、§10（交叉引用编号）。§2 / §3.2 / §5 / §7 / §4.2 / §4.3 / §4.4 / §4.5 不变。

定稿稳定判别值：

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| 缺 / 非整数 / `null` `ip_address_range_id` | `400` | `VALIDATION_ERROR` | `field == "ip_address_range_id"` |
| 范围段不存在 / 已逻辑删除 | `404` | `NOT_FOUND` | `field == "ip_address_range_id"`，`code == "IP_ADDRESS_RANGE_UNAVAILABLE"` |
| 范围段活跃但属于其它 Cluster | `409` | `CONFLICT` | `field == "ip_address_range_id"`，`code == "IP_ADDRESS_RANGE_UNAVAILABLE"` |
| 所选范围段耗尽 | `409` | `CONFLICT` | `field == null`，`code == "NO_AVAILABLE_IP"` |
| 并发落败 | `409` | `CONFLICT` | `field == "ip_address"`，`code == "DUPLICATE"` |
| 目标 NIC 不存在 / 已删 / 宿主不活跃 | `404` | `NOT_FOUND` | `[]`（与范围段 404 以 `details[].code` 区分） |

「非 5xx」「任何 4xx / 409 均无写入」由「全部拒绝发生在 `create_ip_address` 之前」保证；数据库 partial unique 仍为最终权威（唯一不新增）。

---

## Domain Impact

- **不新增领域对象**：产物仍是一条现有 IPAddress（R-IP-005）。
- **不新增资源关系**：仍为 `IPAddress → NetworkInterface`（N:1 必选）与 `Cluster 1─N IPAddressRange`；本 Feature 仅在分配时**读取**一个既有范围段并校验其归属。
- **不修改**任何既有领域对象、状态模型、唯一性规则；R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010 原样不变；仅 R-IP-006 / R-IP-009 语义按 DEC-025 修订。
- 比较边界（R-IP-007）不变：范围归属按 IPv4 **数值**，占用 / 唯一性按 `ip_address` **字面**。

---

## Data Layer Impact

**无需任何数据库设计 / Schema 变更，`database: false`，无 migration。**

- 表复用：产物写入既有 `ip_addresses`；所选范围段读取既有 `ip_address_ranges`。不新增表 / 列。
- 唯一性复用：R-IP-010 禁止新增超出 R-IP-001 的唯一性；既有 `ux_ip_addresses_cluster_ip_active` 即最终权威。
- 读取面：`GET` / `SELECT` 单条活跃范围段按主键（`ip_address_ranges.id`），活跃占用按 `ix_ip_addresses_cluster_id`——已确认规模（10⁵ / 50 并发）内无需新索引。
- migration head 仍 **`0010_f022_ip_range_metadata`**（单一线性 head）。
- `project-plan.yaml` `features[F023].layers.database` 复核确认 **`false`**。

---

## Backend Work

改动集中在 `backend/app/ip_allocations/**`（既有 F021 模块），**不改** `app/ip_addresses/**` 与 `app/ip_address_ranges/**` 的源码语义。

1. **请求 schema（`schemas.py`）**
   - `IpAddressAutoAllocateRequest` 字段集合由恰 `{network_interface_id}` 改为恰 `{network_interface_id: int, ip_address_range_id: int}`（**两字段均必填**）；继续 `extra="forbid"`。
   - `IpAddressManualAllocateRequest` **不变**。
2. **数据访问（`repository.py`）**
   - 复用既有 `app.ip_address_ranges.repository.IpAddressRangeRepository.get_active(range_id)` 读取所选范围段（返回 ORM 行含 `cluster_id` / `start_ip` / `end_ip`；活跃过滤经既有活跃谓词）。无需为 F023 新增仓库方法。`list_active_ranges` 仍供手动分配使用；`active_ip_literals(cluster_id)` 仍供占用集合读取。
3. **领域服务（`service.py::allocate_ip_auto`）——校验顺序（稳定、可测、任何拒绝先于写入）**
   1. `cluster_id = derive_cluster_id(session, payload.network_interface_id)`；未命中 → `404 NOT_FOUND`（`details == []`）。
   2. `range = IpAddressRangeRepository(session).get_active(payload.ip_address_range_id)`；
      - `None`（不存在或已逻辑删除）→ `NotFoundError` + `details[{field: "ip_address_range_id", code: "IP_ADDRESS_RANGE_UNAVAILABLE"}]`；
      - `range.cluster_id != cluster_id` → `ConflictError` + 同一 `code`（跨 Cluster）。
   3. `occupied = repository.active_ip_literals(cluster_id)`。
   4. `candidate = select_first_free([(range.start_ip, range.end_ip)], occupied)`（复用既有纯函数，仅传**单个**范围段）；`None` → `ConflictError` + `details[].code = "NO_AVAILABLE_IP"`（任何写入之前）。
   5. `return create_ip_address(session, IpAddressCreate(network_interface_id=..., ip_address=format_ipv4(candidate)))`（**既有单一受控写入路径**）。
   - 新增一个模块常量 `_RANGE_UNAVAILABLE_DETAIL`（`field="ip_address_range_id"`、`code="IP_ADDRESS_RANGE_UNAVAILABLE"`）。
4. **复用与禁止**
   - **复用** `derive_cluster_id`、`create_ip_address`、`IpAddressRangeRepository.get_active`、`app.ip_address_ranges.ipv4` 的 `format_ipv4`。
   - **不复制**第二份 IPv4 解析 / 枚举器；`select_first_free` 保持既有语义，仅以上界为单个范围段。
   - **不改** `cluster_id` 写入路径（仍唯一经 `create_ip_address` → `IpAddressRepository.create`）；**不改**软删写入路径（仍唯一 `app/deletion/service.py::soft_delete`）。
   - **不新增** SQLSTATE 键（`SQLSTATE_MAP` 不变）、不新增唯一索引 / 触发器 / CASCADE / 第二维度列。
   - `router.py` 与 `/allocate-manual` **不变**（仅请求模型字段变化，路由签名与响应模型不变）。
5. **测试同步（若静态 guard 断言请求字段集合）**：按新合法字段集合**精确演进**，不得放宽断言语义。

---

## Frontend Work

复用既有外壳（`IpAddressListPage.vue` / `IpAddressAllocateDialog.vue` / `api/ipAddresses.ts` / `ApiError` 分支），新增**范围段选择**与结果 / 错误呈现。

### 关键：前端如何在选定 NIC 后获得该 Cluster 的可选范围段

**采用方案 1（复用既有只读端点，不新增任何后端读取面）：**

```
选定 NIC
  → 已有 NIC 的 bare_metal_id（NetworkInterfaceRead.bare_metal_id，F004 §2）
  → GET /api/bare-metals/{bare_metal_id}  （F002 §3.3，响应含 cluster_id）
  → GET /api/ip-address-ranges?cluster_id={cluster_id}&page_size=200 （F020 §3.2，仅返回活跃范围段）
  → 渲染「目标地址范围」下拉（展示 name/start_ip/end_ip 等既有字段）
  → 提交 POST /api/ip-addresses/allocate { network_interface_id, ip_address_range_id }
```

论证：F004 已在 `NetworkInterfaceRead` 暴露 `bare_metal_id`，F002 已在 `BareMetalRead` 暴露 `cluster_id`，F020 已提供按 `cluster_id` 限定且仅返回活跃范围段的列表端点。三处均为**已冻结契约中的既有能力**，本 Feature 无需新增端点或参数，也无需扩展任何响应 schema。代价是 NIC 上下文下最多 2 次额外只读请求（BM 详情 + 范围段列表），在 V1 规模与内网环境下可接受。

**不采用方案 2（新增后端读取面）**：从 NIC 直接解析其 Cluster 的活跃范围段可用「新增 `?network_interface_id=` 参数到 `/api/ip-address-ranges`」或新增专用端点实现，但两者都会：① 扩大 F020 契约的参数面（该契约明文「不存在 status / CIDR / 关键字 / 排序等第二维度查询参数」，新增 NIC 维度属新契约面）；② 要求新的 Backend 只读实现与测试；③ 对当前需求无额外收益。既有端点组合已能确定 Cluster 与活跃范围段，因此**不需要**新增读取面、不影响本次契约。

### 交互与状态
- **范围段选择**：`mode === 'auto'` 时新增必选下拉「目标地址范围」。加载中显示 Loading；加载失败按 `error.code` 分支（`404` 表示 NIC / BM 已失效，`401` 交全局会话处理）；目标 Cluster 无活跃范围段 → Empty 态（提示「该集群暂无可用地址范围段」）且**禁用自动分配提交**（客户端提示，非业务守卫）。
- **提交**：自动模式仅发送 `{ network_interface_id, ip_address_range_id }`；手动模式**不变**。
- **不改**手动分配入口与逻辑。
- **不做**：客户端 IPv4 / 范围 / 占用 / 唯一性预检；不解析 `message`；不客户端回填 `cluster_id`（`cluster_id` 仅用于查询范围段，且不作为分配请求字段发送）。

### 错误分支（按稳定判别值）
- `400 VALIDATION_ERROR`（`details[].field`，含 `ip_address_range_id`）→ 字段级提示。
- `404 NOT_FOUND` + `details[].code === "IP_ADDRESS_RANGE_UNAVAILABLE"` → 「所选地址范围段不存在或已删除，请重新选择」。
- `404 NOT_FOUND`（`details == []`）→ 「目标网络接口不存在或已停用」。
- `409 CONFLICT` + `IP_ADDRESS_RANGE_UNAVAILABLE` → 「所选地址范围段不属于该集群，请重新选择」。
- `409 CONFLICT` + `NO_AVAILABLE_IP` → 「所选地址范围段已无可用 IP」（文案不再表述「整个集群并集」）。
- `409 CONFLICT` + `DUPLICATE` → 「该地址已被占用或并发冲突，可重试」。
- `401` → 既有全局会话失效处理。前端**不得**解析 `message`。

---

## Database 结论

- `layers.database = false`；**无 migration**；head 仍 `0010_f022_ip_range_metadata`。
- 不新增 / 不修改任何表、列、约束、索引或触发器；仅读取既有 `ip_address_ranges`（活跃）与 `ip_addresses`。
- 唯一性仍以 `ux_ip_addresses_cluster_ip_active`（R-IP-001，predicate `deleted_at IS NULL`）为最终权威。

---

## Required Implementation Branches

- **backend: true** — `app/ip_allocations/schemas.py`（新增必填字段）、`app/ip_allocations/service.py`（范围段校验 + 单范围枚举 + 错误映射）、必要时 `app/ip_allocations/repository.py`；并按新增合法字段精确演进相关静态 guard 与测试。
- **frontend: true** — `api/ipAddresses.ts`（`IpAddressAutoAllocateBody` 新增 `ip_address_range_id`）、`IpAddressAllocateDialog.vue`（范围段选择 / 空态 / 错误分支 / 引导文案）；必要时新增范围段加载组合逻辑。
- **database: false** — 无数据库设计与变更分支。

---

## Constraints（不得违反的既有契约 / ADR / 规则）

1. 不得新增表 / 列 / 索引 / 唯一约束 / 排他约束 / 触发器 / CASCADE；不得新增 migration（`database: false`）。
2. 不得出现第二处写 `cluster_id`；分配写入只能经 `app/ip_addresses/service.py::create_ip_address`（`IpAddressRepository.create`）。
3. 不得新增写 `deleted_at` 的路径；释放唯一途径为 F005 `DELETE /api/ip-addresses/{ip_address_id}`。
4. 不得复制 IPv4 解析 / 规范化实现；必须复用 `app/ip_address_ranges/ipv4.py`（及既有 `select_first_free`）。
5. **不得修改 `/allocate-manual` 语义，不得修改 F005 `POST /api/ip-addresses` 与 F005 其它端点行为**；`ip_address` 自由文本登记立场不变。
6. 不得修改 `ip_addresses` / `ip_address_ranges` 的表结构、既有端点行为、R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010。
7. 不得超过 R-IP-001 新增唯一性；不得新增 SQLSTATE 映射键（`SQLSTATE_MAP` 不变）。
8. 不得在分配中对既有 `ip_address` 字面做归一化 / trim / 折叠；占用判定按字面，范围归属按数值，二者不得混用。
9. 不得实现 CIDR / IPv6 / 保留地址跳过 / 回收 / 审计 / 批量 / DHCP / DNS / 外部同步；不得引入范围段自动选择 / 默认范围 / 掩码 / VLAN 过滤。
10. 不得在客户端实现 IPv4 校验 / 范围 / 占用 / 唯一性预检（§21），不得客户端回填 `cluster_id` 到分配请求。
11. 静态 guard 只增勿弱：允许按新合法成员**精确演进**期望集合，禁止放宽为子集 / 前缀 / 包含式断言。
12. 契约一致性：`docs/api/f021-ip-address-allocation.md` 修订落盘且 `Status: READY`；手动分配与 F005 端点对应章节逐字未改。

---

## Risks

1. **并发窗口（记录，不消除）**：范围段校验与范围段软删不互相串行（沿用 F020 §6.4 / DEC-023 第 6 项）；极端并发下可能出现「所选范围段校验后被并发软删、本轮仍写入成功」，或耗尽判定读快照后并发软删占用导致瞬时 `NO_AVAILABLE_IP`。均为可重试瞬态，不引入额外锁（R-IP-010 禁止新约束）。
2. **前端读取链**：方案 1 需 2 次额外只读请求；任一失败需按 `error.code` 正确分支。已由既有 `error.code` 语义覆盖，无新错误语义。
3. **静态 guard 精确演进**：断言自动分配请求字段集合 / `derive_cluster_id` 调用点的 guard 必须按完整新集合演进，不得放宽，否则削弱保护。
4. **客户端误当作「无范围段即可自动成功」**：Empty 态必须禁用自动提交，且服务端独立校验（§21），不得只依赖 UI。

---

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

- **TQ-1（范围段是否锁定）**：当前不锁定范围段行（沿用 F020 §6.4 立场）。若未来要求校验与写入串行，属新增并发约束，需重评 R-IP-010 边界。
- **TQ-2（并发落败是否自动重试）**：当前不重试，落败方 `409 DUPLICATE`（与 F021 一致）。
- **TQ-3（前端读取链优化）**：若未来 NIC 读取面提供 Cluster 归属的直接读取能力，可减少一跳；当前无此需求。

---

## Implementation Layers

```text
database: false   # 复用 ip_addresses / ip_address_ranges；无新列 / 新索引 / 新约束 / migration（head 仍 0010_f022_ip_range_metadata）
backend:  true    # app/ip_allocations/**：请求新增必填 ip_address_range_id + 范围段校验 + 单范围枚举 + 错误映射
frontend: true    # 自动分配对话框新增必选范围段选择器 + 空态 + error.code / details[].code 分支
```

---

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f021-ip-address-allocation.md 修订，Status READY）
  ├─ Frontend（仅需 READY 契约，可与 Backend 并行）
  └─ Backend（无需 Database Design：database=false）
        ↓ 所有必需实现分支完成
     Tester → Reviewer
```

无数据库分支，Backend 与 Frontend 可直接并行；Frontend 的三态与错误分支由契约稳定判别值确定，可先行。

---

## Verification Strategy

1. **契约一致性**：修订后 `docs/api/f021-ip-address-allocation.md` 落盘且 `Status: READY`；`ip_address_range_id` 明确为必填；`/allocate-manual` 与 F005 端点章节逐字未改。
2. **请求字段封闭**：缺 / 非整数 / `null` `ip_address_range_id` → `400` 且 `details[].field == "ip_address_range_id"` 无写入；未识别字段 → `400`。
3. **范围段校验**：不存在 → `404 + IP_ADDRESS_RANGE_UNAVAILABLE`；已逻辑删除 → `404 + IP_ADDRESS_RANGE_UNAVAILABLE`；活跃但其它 Cluster → `409 + IP_ADDRESS_RANGE_UNAVAILABLE`；三者均无写入、非 5xx；并与 NIC `404`（`details == []`）可区分。
4. **单范围取最小**：多活跃范围段下，仅在所选段内取数值最小未占用地址；不取其它段更小值；跳过所选段内已占用取下一个。
5. **耗尽不回退**：所选段耗尽 → `409 + NO_AVAILABLE_IP`，无写入、不跨段 / 跨 Cluster；填满后 `ip_addresses` 行数不变。
6. **既有语义不变**：写入 canonical dotted-quad；无隐式保留地址；字面 vs 数值边界（`010.0.0.1` / `10.0.0.1/16` 不阻止选中并写入 `10.0.0.1`）；软删释放；`/allocate-manual` 全量回归通过；F005 `POST /api/ip-addresses` 对范围外字面仍 `201`。
7. **并发（真实线程）**：并发自动 / 手动 / 与 F005 竞争同一地址 → 至多一条 `201`，其余 `409 DUPLICATE`，无 5xx，最终该字面活跃行 ≤ 1。
8. **结构证伪（绕应用层）**：`information_schema` / `pg_indexes` / `pg_constraint` 证明未新增表 / 列 / 唯一索引 / 排他约束 / 触发器；`ip_addresses` 唯一索引集合仍恰为 `{ux_ip_addresses_cluster_ip_active}`；migration head 仍 `0010_f022_ip_range_metadata`；`SQLSTATE_MAP` 键集合不变。
9. **不变式**：`cluster_id` 漂移 = 0；`deleted_at` 写入路径唯一。
10. **静态 guard**：相关 guard 按完整新集合精确演进且仍可失败（注入式复证）。
11. **前端**：范围段必选、Empty（目标 Cluster 无活跃范围段）禁用提交、三态互异、错误按 `error.code` / `details[].code` 渲染（含新 `IP_ADDRESS_RANGE_UNAVAILABLE`），不解析 `message`。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

（API Contract Status = `READY`；无 Blocking Open Technical Question。）