# Product Handoff

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-22
> Feature: **F023 — 自动分配时指定 IP 地址范围段**（E02，P1，`depends_on: [F020, F021]`，均已 DONE）
> Product Source: `requirements.md` §12（**修订 R-IP-006 / R-IP-009，R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010 保持不变**）；§15、§21、§22、§23；`domain-model.md` §IP 分配 / §6 / §7.2 / §8；`domain-model.yaml`；`docs/api/f021-ip-address-allocation.md`（现有契约，待 Architecture 修订）；`docs/product/handoffs/f021-ip-address-allocation.md`；`docs/api/f005-ip-address.md`；ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005；`docs/project/v1/project-plan.yaml` `decisions_required[DEC-025].resolution`（用户 2026-09-22 裁定，RESOLVED）

## Feature

自动分配时指定 IP 地址范围段（F023）— 把 `POST /api/ip-addresses/allocate` 的自动分配从「在目标 Cluster **全部活跃范围段并集**内取全局最小」改为「**必须显式指定一个活跃范围段**，仅在该**所选单个范围段**内取数值最小未占用 IPv4；所选范围段耗尽则硬失败且**不回退**」。这是对已确认 **R-IP-006 / R-IP-009** 的**修订**，不新增分配实体、不新增领域对象。

## Problem

F021 交付的自动分配在目标 Cluster 有**多套活跃范围段**时，调用方**无法选择使用哪一套**：契约请求字段恰为 `{network_interface_id}`，规则为「全部活跃范围段并集取全局最小」。

**谁在什么情况下使用**：HPC / AI 集群运维人员与基础设施管理员，在同一 Cluster 内按用途（如业务网 / 存储网 / 管理网）登记了多个地址范围段，需要为某张网络接口**在指定的一套范围内**取下一个可用 IP 时使用。

**产品价值**：让「用哪套范围」从**隐式并集**变为**调用方显式、系统可判定的选择**，消除跨范围段误取地址的运维风险；同时**严格保持**占用判定、唯一性、手动分配等既有语义不变。

**本 Feature 只修订 R-IP-006 / R-IP-009；不修改任何其它既有规则。**

## Confirmed Requirements

来源：`decisions_required[DEC-025].resolution`（用户 2026-09-22 裁定，RESOLVED），固化为 `requirements.md` §12 R-IP-006 / R-IP-009（修订）。

1. **必填范围段**：自动分配**必须显式指定**一个 IP 地址范围段；`POST /api/ip-addresses/allocate` 新增**必填**字段 `ip_address_range_id`；**不再**存在「全部活跃范围段并集取全局最小」的隐式行为。
2. **范围归属与活跃性**：所选范围段必须**活跃**，且**恰属于**目标 NIC 推导出的 Cluster；否则分配被拒（**非 5xx**），**不创建任何 IP**。
3. **单范围取最小**：在**所选单个范围段**内取**数值最小**的未占用 IPv4。
4. **耗尽不回退**：所选范围段耗尽 → `409 CONFLICT + NO_AVAILABLE_IP`，**不回退**到其它范围段，**不跨 Cluster 取址**，**不创建任何 IP**。
5. **手动分配不变**：`/allocate-manual` 语义与本次之前一致（由输入 IP 自身决定范围）。
6. **既有边界不变**：占用判定按字面、范围归属按数值、R-IP-001 partial unique 为唯一性最终权威、无隐式保留地址、无部分写入、F005 登记端点不变；**不新增任何唯一性**、**不新增数据库 Schema**。

## Confirmed Domain Rules

| 规则 / 原则 | 与 F023 的关系 | 来源 |
|---|---|---|
| **R-IP-006（修订）** | 自动分配必须显式指定活跃范围段、单范围内取最小、耗尽不回退 | §12；DEC-025 |
| **R-IP-009（修订）** | 耗尽判定限定为**所选活跃范围段** | §12；DEC-025 |
| R-IP-001 | 同一 Cluster 内 `ip_address` 字面唯一；partial unique 为最终权威 | §12（**保持**不变） |
| R-IP-002 / R-IP-003 | 跨 Cluster 可重复；不考虑 VRF | §12（**保持**不变） |
| R-IP-004 | 范围段语义：start–end / 恰属一个**活跃** Cluster / 同 Cluster 活跃不重叠 / 无状态 / 软删 | §12（**保持**不变；F023 的归属校验复用其「活跃」+「恰属一个 Cluster」语义） |
| R-IP-005 | 分配产物为一条现有 IPAddress；必选一个活跃 NIC；Cluster 由 NIC→BareMetal 受控推导 | §12（**保持**不变） |
| R-IP-007 | 占用按 `ip_address` **字面**；范围归属按 IPv4 **数值**；软删释放；无保留地址 | §12（**保持**不变） |
| R-IP-008 | 手动分配：合法 IPv4 + 落在某活跃范围内 + 未占用；规范化写入；非法拒绝；范围外仍走 F005 | §12（**保持**不变） |
| R-IP-010 | 不新增超出 R-IP-001 的唯一性；并发至多一条成功 | §12（**保持**不变） |
| IP → NIC 必选 / NIC → BareMetal 必选 | Cluster 经受控推导，请求 / 响应不含 `cluster_id` | §15；`domain-model.md` §6 |
| §21 | 关键冲突须在服务端保存前阻止，不得只依赖 UI | §12 / §21 |
| §23 | 不引入 DHCP / DNS / 自动发现 / 保留地址等 | §23 |

## Scope

### 本次包含

1. **自动分配请求新增必填字段 `ip_address_range_id`**（字段名以 DEC-025 裁定为准；请求 schema 仍封闭）。
2. **所选范围段校验**：必须存在、**活跃**、且**恰属于**目标 NIC 推导出的 Cluster；不满足 → 非 5xx 拒绝、无写入。
3. **单范围取最小**：仅在所选范围段内取数值最小未占用 IPv4。
4. **耗尽硬失败**：所选范围段耗尽 → `409 CONFLICT + NO_AVAILABLE_IP`，不回退、不跨范围段 / 跨 Cluster、无部分写入。
5. **前端**：自动分配入口必须要求**选择范围段**（必选）；三态与错误按 `error.code` / `details[].code` 分支；不在客户端替代服务端业务校验（§21）。
6. **契约一致性**：修订后的 f021 契约须持久化为 `READY`，不得「契约禁止、实现却有」分裂。

### 本次明确不包含

1. **修改手动分配**（`/allocate-manual`）：语义完全不变（用户明确排除）。
2. **修改 R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010 的任何一条**。
3. **新增唯一性** / 新增数据库 Schema：无新表、新列、新索引、新 migration（`layers.database = false`）。
4. **CIDR / IPv6 / 保留地址 / 排除表 / 使用率**：均不引入（R-IP-004 / §23）。
5. **修改 F005 `POST /api/ip-addresses` 端点**：不变。
6. **范围段自动选择 / 默认范围 / 记忆上次选择 / 按掩码 / VLAN 过滤**：无此需求。
7. **新增分配 / 预留实体、回收工作流、审计 / 历史**。

### 本次未涉及

- 自动分配的默认范围段策略；批量分配 / 多次分配；多范围段并集回退作为可配置开关；分配历史 / 操作人；范围段使用率统计；与 F010 / F018 的整合呈现。以上本次未要求，但**不得推断为永远不需要**。

## Acceptance Criteria

### 契约与请求字段

- **AC-01（请求字段闭环）**：自动分配成功响应仍**恰为** F005 IPAddress 表示 `{id, network_interface_id, ip_address, created_at, updated_at}`；请求新增必填 `ip_address_range_id`，响应**不新增**任何字段（无 `ip_address_range_id` / `cluster_id` / `status` 等回显扩展）。
- **AC-02（必填校验）**：缺少 `ip_address_range_id` / 非整数 / `null` → `400 VALIDATION_ERROR`，`details[].field == "ip_address_range_id"`，**不产生记录**。
- **AC-03（字段封闭，无隐式行为）**：请求仍拒绝一切未识别字段（含 `cluster_id` / `status` / `mode` / 保留地址开关等）→ `400`；**不存在**任何「未指定范围段也成功」的路径。
- **AC-19（契约一致）**：修订后的 `docs/api/f021-ip-address-allocation.md` 已持久化且 `status = READY`，`ip_address_range_id` 明确为**必填**；无「契约禁止、实现却有」分裂。

### 范围归属与活跃性

- **AC-04（必须活跃）**：`ip_address_range_id` 引用**已逻辑删除**的范围段 → 分配被拒、**非 5xx**、**不创建记录**（具体状态码由 Architecture 定稿）。
- **AC-05（必须恰属目标 Cluster）**：引用**其它 Cluster** 的（活跃）范围段 → 分配被拒、**非 5xx**、**不创建记录**；不跨 Cluster 取址。
- **AC-06（必须存在）**：`ip_address_range_id` 引用**不存在**的范围段 → 分配被拒（建议 `404 NOT_FOUND`，取值由 Architecture 定稿）、**不创建记录**，**永不 5xx**。

### 单范围取最小

- **AC-07（所选范围内取最小）**：目标 Cluster 有多个活跃范围段，选择范围段 R 且 R 内无占用 → 返回 **R 内数值最小**的未占用 IPv4。
- **AC-08（不取其它范围段的最小）**：目标 Cluster 另有活跃范围段 Q 含比 R 更小的数值，但**未被选择** → 自动分配**不得**选中 Q 中的地址（无并集行为）。
- **AC-09（跳过已占用取下一个）**：所选范围段内最小地址已被活跃占用 → 返回该段内**下一个**数值最小的未占用地址，依此类推。

### 耗尽

- **AC-10（所选范围段耗尽 → 不回退）**：所选范围段内全部 IPv4 均被活跃占用 → `409 CONFLICT` + `details[].code = "NO_AVAILABLE_IP"`，**不回退**到其它范围段，**不创建任何 IPAddress**。
- **AC-11（无部分写入 / 不跨 Cluster）**：上述耗尽路径**不得**产生任何写入，**不得**隐式扩大范围或跨 Cluster 取址。

### 既有分配语义不变

- **AC-12（写入规范化 dotted-quad）**：写入值为 canonical dotted-quad（无前导零、无前缀长度），再次读取得同一规范值。
- **AC-13（无隐式保留地址）**：所选范围段含网络地址且其未被占用时，可被选中（不自动跳过网络 / 广播 / 网关 / 端点）。
- **AC-14（占用按字面 / 软删释放 / 字面 vs 数值边界）**：同 Cluster 活跃且**字面相同**者判为占用并跳过；软删后释放；活跃字面 `010.0.0.1` / `10.0.0.1/16` **不阻止**选中并写入 `10.0.0.1`（范围归属按数值、占用按字面，不得混用）。
- **AC-15（手动分配不变）**：`/allocate-manual` 语义与 F021 一致——合法 IPv4 + 数值落在该 Cluster **某活跃范围内** + 未占用 → `201`；非规范输入规范化写入；非法格式被拒；**不受 `ip_address_range_id` 影响**。
- **AC-16（F005 登记端点不变）**：`POST /api/ip-addresses` 保持原样，范围外字面仍可登记（`201`）；F023 不替换、不改版 F005 端点。
- **AC-17（唯一性 / 并发不变）**：不存在超出 R-IP-001 的唯一性；R-IP-001 partial unique 仍为最终权威；两条并发选中同一地址 → 至多一条 `201`，另一条 `409 CONFLICT + DUPLICATE`，**永不 5xx**；且**不新增写 `cluster_id` 的第二路径**。

### 前端与数据库

- **AC-18（前端必选范围段）**：自动分配 UI **必须**要求用户选择一个范围段方可提交；未选时不发起请求（客户端提示）；服务端仍独立校验（§21，不得只依赖 UI）；错误按 `error.code`（结合 `details[].code`）渲染，不解析 `message`。
- **AC-20（无数据库变更）**：本 Feature **无**新表 / 新列 / 新索引 / 新 migration；`project-plan` `layers.database = false` 经复核确认；`ip_address_ranges`、`ip_addresses` 结构不变。

## Assumptions

- A-1：字段名 `ip_address_range_id` 与「必填」由 DEC-025 直接给定，非产品新增。
- A-2：所选范围段引用字段的类型 / 错误状态码具体取值沿用既有分配契约约定，由 Architecture 定稿（产品仅要求「非 5xx 拒绝、无写入、稳定判别值」）。
- A-3：范围段活跃性即「未逻辑删除」（R-IP-004 无状态），与 R-IP-004 一致。
- A-4：所选范围段的 Cluster 归属校验复用 R-IP-005 的 NIC→BareMetal→Cluster 受控推导结果，不新增第二处推导。
- A-5：`ip_address_range_id` 唯一取自 F020 已交付的 `/api/ip-address-ranges` 资源。

## Proposed Rules

无。DEC-025 已由用户 2026-09-22 裁定，全部要点已固化为 R-IP-006 / R-IP-009 修订正文，无遗留 PROPOSED。

## Open Questions

### Blocking

**无。** DEC-025 已 RESOLVED；依赖 F020 / F021 均已 DONE。

### Non-blocking（归 Architecture 定稿）

- **NQ-1（契约修订形态）**：`ip_address_range_id` 的字段类型与在请求 schema 中的位置；契约 `status` 由 READY 的修订方式。
- **NQ-2（错误码取值）**：范围段不存在 / 非活跃 / 非目标 Cluster 的精确 HTTP 状态码与 `details[].code`（产品要求：**非 5xx、无写入、稳定判别值**）；耗尽沿用 `NO_AVAILABLE_IP`。
- **NQ-3（校验顺序）**：范围段校验与 NIC / Cluster 推导的先后顺序（须稳定可测、无写入）。
- **NQ-4（并发 / 锁序）**：在「单范围取最小」下的并发实现；不得新增写 `cluster_id` 的第二路径，不得新增 R-IP-001 之外的唯一性或新死锁序。
- **NQ-5（前端交互）**：范围段选择控件形态、空态（目标 Cluster 无活跃范围段时不可提交）、三态与错误分支。
- **NQ-6（`layers` 复核）**：确认 `database = false`（无 Schema 变更）。

> 边界说明（供 Architecture 判断，不改变规则）：原 R-IP-009 括号中「该 Cluster 没有任何活跃范围段」的情形，在新语义下发生于**范围段选择 / 校验阶段**（无可选活跃范围段 → 拒绝，非 5xx、无写入）；其时序归类由 Architecture 在契约中定稿，产品不新增规则。

## Architecture Handoff

以下问题**由 Architecture 解决**，Product 不代为决定技术细节：

1. **契约修订**：在 `docs/api/f021-ip-address-allocation.md` 中把自动分配请求 `ip_address_range_id` 定为**必填**，并修订 §1.6 / §3.1 中「全部活跃范围段并集 / 跨范围段全局最小」的表述为「所选单个活跃范围段内取最小」；契约 `status` 维持 / 重定稿 `READY`。
2. **错误码定稿**：范围段不存在 / 非活跃 / 非目标 Cluster 的精确取值与 `details[]` 形态（须**非 5xx、无写入、稳定判别值**）；耗尽沿用 `409 CONFLICT + NO_AVAILABLE_IP`。
3. **校验顺序与原子性**：范围段校验、NIC / Cluster 推导、单范围内枚举最小、写入的先后与原子性；耗尽与冲突在任何写入之前判定。
4. **复用既有推导与守卫**：分配仍须经 F005 的**单一受控 `cluster_id` 写入路径**；不得新增写 `cluster_id` / `deleted_at` 的第二路径。
5. **范围枚举实现**：在**所选单个范围段**上枚举未占用数值并复用既有 `app/ip_address_ranges/ipv4.py` 纯函数；不复制第二份解析。
6. **`database` 层复核**：确认无需新表 / 新列 / 新索引 / migration（`layers.database = false`）。
7. **前端**：范围段选择必选、空态与错误分支、`error.code` 分支呈现；不在客户端重复实现业务校验。
8. **文档同步**：修订后的 R-IP-006 / R-IP-009 语义已由协调器同步到 `domain-model.md`（现含「并集」表述已修订）与 `requirements.md`；f021 契约与 F021 Product Handoff 中的「并集」历史表述是否需要加注由 Architecture 决定。

## Handoff Status

`READY FOR ARCHITECT`

---

GIT: NONE