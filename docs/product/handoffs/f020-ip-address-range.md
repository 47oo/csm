# Product Handoff — F020 IP 地址范围段（地址池）管理

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-20
> Feature: F020（E02，P1，`depends_on: [F001, F005]`，均已 DONE）
> Product Source: `requirements.md` §12（R-IP-001~003 保持不变，新增 R-IP-004）；§9、§15、§17、§21、§22；`domain-model.md` §5.7 / §8 / §9；`docs/api/f005-ip-address.md`；ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005；`docs/project/project-plan.yaml` `decisions_required[DEC-023].resolution`

---

## Feature

IP 地址范围段（地址池）管理（F020）— 为每个 Cluster 登记、查询、维护、逻辑删除多个 IP 地址范围段（start–end），**不包含 IP 分配**。

## Problem

今天运维人员用 Excel / 分散文档登记 IP，只能登记「某条 IP 被谁占用」，无法表达「这个 Cluster 定义了哪些合法地址段」。这导致：

- 分配新 IP 前没有权威的地址边界可供查询；
- 「可用地址空间」只存在于个人头脑或表格约定中；
- 地址池与已占用 IP 之间缺乏可查询的对应关系。

F005 已交付单条 IP 字面值的登记与唯一性，但**显式排除**「IP 池 / 网段 / 子网 / 分配与回收工作流」（`docs/product/handoffs/f005-ip-address.md` §Scope；`docs/api/f005-ip-address.md` §非目标）。

**谁在什么情况下使用**：HPC / AI 集群运维人员与基础设施管理员，在维护某个 Cluster 的地址规划时，登记 / 查看 / 修改 / 删除该 Cluster 的地址范围段，作为后续 IP 分配的权威依据。

**产品价值**：让「每个 Cluster 有哪些合法地址段」成为统一、可查询、可维护的资源事实，为 F021（自动 / 手动分配）提供基础。F020 本身**不产生分配行为**。

**本 Feature 只新增产品规则 R-IP-004；不修改任何既有规则。**

---

## Confirmed Requirements

来源：`decisions_required[DEC-023].resolution`（用户 2026-09-20 裁定）中**属 F020 的第 1~6 项**，固化为 `requirements.md` §12 R-IP-004。

1. **表示与字段**：范围段用 **start–end（含两端，IPv4 dotted-quad）** 表示；字段**至少** `id / cluster_id / start_ip / end_ip / created_at / updated_at`；`start_ip <= end_ip`；**V1 仅 IPv4**；范围字段须为合法 IPv4 并**规范化**；**现有 `ip_addresses.ip_address` 的自由文本登记保持不变**。
2. **重叠**：**同一 Cluster 内的活跃范围段不得重叠**；**跨 Cluster 允许相同范围**（与 R-IP-002 一致）。
3. **归属**：每个范围段**恰属于一个活跃 Cluster**（`cluster_id` 必选），**不跨 Cluster 共享**。
4. **生命周期 / 删除**：支持修改 `start_ip` / `end_ip`；**逻辑删除**（不物理删除）；**当范围内仍有活跃 IP（同 Cluster、活跃、字面落在该范围内）时，禁止删除该范围段**；删除范围段**不级联**删除已分配 / 已登记 IP。
5. **无状态**：范围段**不设状态**；活跃 / 失效仅由逻辑删除表达（沿用 Q-002=B）。
6. **不新增 DB 层一致性硬约束**：不新增「范围必须覆盖已分配 IP」的数据库级硬约束；漂移检测查询作为交付建议（归 Architecture / 测试，见下）。
7. **字段集合封闭**：**没有** name / description / 用途 等其它已确认字段；不得自行新增。

---

## Confirmed Domain Rules

| 规则 / 原则 | 内容 | 来源 |
|---|---|---|
| R-IP-001 | 同一 Cluster 内 IP 必须唯一 | §12（**保持**不变） |
| R-IP-002 | 不同 Cluster 之间允许相同 IP（唯一性边界为 Cluster） | §12（**保持**不变） |
| R-IP-003 | V1 不考虑 VRF / 网络命名空间 | §12（**保持**不变） |
| **R-IP-004（新增）** | 范围段语义（表示 / 字段 / 归属 / 重叠 / 生命周期 / 无状态） | §12（本 Feature 落地） |
| Q-002=B | 无状态资源不含状态 | `domain-model.md` §7.2；变更记录 |
| §9 / R-DELETE-001~006 | 逻辑删除、不物理删、无 Undelete、父有活跃子不得删、不级联、软删释放唯一性 | §17；ADR-0004 |
| §21 | 关键冲突必须在保存前阻止，不得只依赖 UI | §21 |
| §22 | 大小写敏感为默认立场 | §22 |
| 寻址与状态码 | 写走 `id`；`204` / `404 NOT_FOUND` / `409 CONFLICT` / `400 VALIDATION_ERROR` | ADR-0003 |
| 唯一性冲突落地 | partial unique index（predicate `deleted_at IS NULL`）为最终权威 | ADR-0002；ADR-0004 |
| Cluster 名称不得含 `/` | Cluster 寻址约束 | R-CLUSTER-005（§7） |

---

## Scope

### 本次包含

1. **范围段 CRUD（不含分配）**：为 Cluster 登记 / 查询 / 修改 / 逻辑删除 IP 地址范围段。
2. **字段与表示**：`cluster_id` + `start_ip` + `end_ip`；请求与响应 schema 封闭（不接受 name / description / 用途 / status / deleted_at 等）。
3. **`start_ip <= end_ip`** 与 **IPv4 合法性与规范化**。
4. **归属校验**：`cluster_id` 必选，且必须是**活跃** Cluster。
5. **同 Cluster 活跃范围段不重叠**（保存前阻止，非 5xx）；**跨 Cluster 同范围可共存**。
6. **修改 start/end** 并重新执行重叠校验。
7. **逻辑删除**：委托既有统一软删路径；软删后不出现在常规查询、不参与重叠判定、不占用。
8. **删除守卫**：同 Cluster 存在活跃 IP 字面落在范围内时**禁止删除**范围段（明确冲突错误、无部分写入）；删除**不级联**。
9. **无状态落地**：无 `status` 字段 / 枚举 / 默认值 / 过滤 / 端点。
10. **前端**：范围段列表 / 详情 / 登记 / 修正 / 删除入口；三态与 Empty / Not Found 可区分；错误按 `error.code`。

### 本次明确不包含

1. **IP 分配（自动 / 手动、「最小 IP」选取、占用判定、耗尽行为）** —— 属 **F021**，当前 BLOCKED，不在 F020 范围。
2. **CIDR 表示**（DEC-023 明确采用 start–end）。
3. **IPv6**（V1 仅 IPv4）。
4. **使用率统计 / 冲突扫描 / 外部同步 / 自动资产发现 / DHCP / DNS / 导出**。
5. **除 `id / cluster_id / start_ip / end_ip / created_at / updated_at` 之外的字段**（name / description / 用途 等均未确认）。
6. **物理删除 / Undelete / 恢复 / 回收站 / 软删级联 / 批量删除**。
7. **修改 `ip_addresses.ip_address` 的自由文本语义**（保持 F005 立场：不实现格式校验、不实现归一化）。
8. **VRF / 网络命名空间**（R-IP-003）。
9. **范围段的状态**（Q-002=B，R-IP-004 明确无状态）。

### 本次未涉及

当前需求没有要求，但**不能推断为永远不需要**：

- 范围段的使用率 / 剩余地址展示；
- 按 Cluster 视角聚合展示范围段（页面组织）；
- 范围段的导出 / 高级筛选 / 排序 / 审计历史；
- 范围段与已登记 IP 的对应视图（哪些 IP 落在哪些范围段内）；
- 范围段耗尽 / 容量预警；
- Cluster 移出 / 迁移对范围段的影响。

---

## Acceptance Criteria

### 认证

- **AC-01（认证）**：未认证访问任何范围段端点 → `401 UNAUTHENTICATED`，且不返回任何资源数据。

### 登记与字段

- **AC-02（登记成功，字段集合封闭）**：`POST` 携带活跃 `cluster_id` + 合法 `start_ip` + `end_ip`（`start_ip <= end_ip`）→ `201`；响应字段集合**恰为** `{id, cluster_id, start_ip, end_ip, created_at, updated_at}`；**不含** `deleted_at` / `status` / `name` / `description` / 用途 等字段。
- **AC-03（请求字段封闭）**：请求体携带未确认字段（如 `name` / `description` / `status` / `deleted_at`）→ `400 VALIDATION_ERROR`，不产生记录。
- **AC-04（`cluster_id` 必填）**：缺失或非整数 → `400 VALIDATION_ERROR` + `details[].field`，不产生记录。
- **AC-05（`cluster_id` 须为活跃 Cluster）**：引用不存在**或已逻辑删除**的 Cluster → 写入被阻止、不产生记录、**不得 5xx**。
- **AC-06（`start_ip` / `end_ip` 必填）**：缺失或非字符串 → `400 VALIDATION_ERROR`，不产生记录。
- **AC-07（`start_ip <= end_ip`）**：`start_ip > end_ip` → `400 VALIDATION_ERROR`，不产生记录。
- **AC-08（IPv4 合法性）**：非法 IPv4（如 `10.0.0.256`、`10.0.0`、`abc`、`1.2.3.4/24`、`2001:db8::1`）→ `400 VALIDATION_ERROR`，不产生记录。
- **AC-09（规范化）**：合法但非规范写法的 IPv4（如含前导零 `010.000.000.001`）被**规范化**后存储与返回；再次读取得同一规范值（例如 `10.0.0.1`）。

### 重叠

- **AC-10（同 Cluster 重叠保存前拒绝）**：同一 Cluster 内存在活跃范围段与请求区间**交集非空**（含共享端点）→ 写入被阻止、不产生记录、**非 5xx**（`409 CONFLICT`，`details[].code` 由 Architecture 定稿）。
- **AC-11（跨 Cluster 同范围可共存）**：Cluster A 与 Cluster B 各自登记完全相同的 `[start_ip, end_ip]` → 均 `201`，两条不同记录。
- **AC-12（修改后重校验）**：`PATCH` 修改 `start_ip` / `end_ip` 使其与同 Cluster 其它活跃范围段重叠 → 被阻止、**无部分写入**（原值不变）。

### 生命周期

- **AC-13（修改 start/end）**：`PATCH` 携带新的合法 `start_ip` / `end_ip` → `200` 返回新值；再次读取得同一值；`cluster_id` / `created_at` 不变。
- **AC-14（软删）**：`DELETE`（活跃行）→ `204` 无响应体；该行**仍物理存在**且 `deleted_at` 非空；不出现在列表 / 详情。
- **AC-15（软删释放「占用」意义）**：软删某范围段后，可在同一 Cluster 内登记与之重叠的新范围段 → `201`；证明已删范围段不再参与重叠判定。
- **AC-16（范围内有活跃 IP 时禁止删除）**：同 Cluster 存在**活跃** `IPAddress`，其字面地址落在 `[start_ip, end_ip]` 内 → `DELETE` 该范围段 → **明确冲突错误**（建议 `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"` 类；具体取值由 Architecture 定稿），且该范围段 `deleted_at` **仍为 NULL**（无部分写入）。
- **AC-17（范围内无活跃 IP 可删）**：范围内无活跃 IP，或范围内 IP 均已软删 → `DELETE` → `204`。
- **AC-18（删除不级联）**：删除范围段后，其所属 Cluster、相关 BareMetal / NetworkInterface / IPAddress 的字段**逐条不变**；无任何其它行被修改或物理删除。

### 无状态

- **AC-19（无状态）**：请求 / 响应 / 数据表 / 端点 / 查询参数中不存在 `status` 字段、枚举、默认值或过滤。

### 查询

- **AC-20（列表 + Empty）**：`GET` 列表 → `200` + `{items,total,page,page_size}`；无活跃范围段时 `items == []`、`total == 0`，**不得 404**。
- **AC-21（详情 Not Found）**：不存在或已逻辑删除的 `id` → `404 NOT_FOUND`（不区分）。
- **AC-22（排除已删）**：已软删范围段不出现在列表 `items` / `total`，按 `id` 读取 → `404`。

### 既有语义不变（逐条）

- **AC-23（`ip_address` 自由文本登记逐条不变）**：F005 既有行为**保持不变**，包括：同 Cluster 内 IP 字面唯一 / 跨 Cluster 可重复 / 字面精确比较（不折叠、不 trim、不归一化）/ **不实现、不承诺** `ip_address` 格式校验与归一化 / IPAddress 无状态 / 无 VRF / 软删释放唯一性 / IP→NIC 必选绑定。范围段的引入**不新增**对 `ip_address` 的格式约束。
- **AC-24（R-IP-001~003 不变）**：同 Cluster 内 IP 唯一、跨 Cluster 可重复、不考虑 VRF 的语义与实现均不被本 Feature 修改。

### 边界

- **AC-25（不引入分配语义）**：不存在自动 / 手动分配端点或行为，不存在「第一个最小 IP」选取、占用判定、耗尽错误等 —— 均属 F021。
- **AC-26（不引入 CIDR / IPv6）**：不接受 CIDR（`1.2.3.4/24`）表示，不接受 IPv6。
- **AC-27（不引入未确认能力）**：不存在使用率统计 / 冲突扫描 / 外部平台同步 / 自动资产发现 / 导出端点或能力。
- **AC-29**（若采纳 F005 的契约一致性做法）：本 Feature 契约已持久化且 `contract.status=READY`，不得存在「契约禁止、实现却有」的分裂。

---

## Assumptions

以下为**不阻塞当前工作、可安全暂时采用**的假设；**不是 CONFIRMED 领域规则**：

- A-1：范围段的重叠判定按 `[start_ip, end_ip]` 闭区间的**数值交集非空**（含共享端点）理解；「不重叠」不含「相接」。
- A-2：IPv4「规范化」暂按去掉前导零的 canonical dotted-quad、不含前缀长度理解（最终形式由 Architecture 定稿）。
- A-3：删除守卫对「字面落在范围内」的判定，需要将活跃 `ip_address` 字面解析为 IPv4 后与范围做数值比较；对无法解析为 IPv4 的既有自由文本 `ip_address` 如何处理，属 Architecture 实现细节（见 Open Questions / Non-blocking）。
- A-4：认证 / 只读 / 错误信封 / 前端三态沿用既有约定（F020 NQ-9 非阻塞项，按既有立场）。

---

## Proposed Rules

（本 Feature 无新增 PROPOSED 产品规则；DEC-023 已由用户裁定，规则以 R-IP-004 固化。）

---

## Open Questions

### Blocking

**无。** DEC-023 已由用户于 2026-09-20 裁定为 RESOLVED（`decisions_required[DEC-023].resolution`），F020 所需产品语义均已确定，可进入架构设计。

### Non-blocking

- **NQ-A（重叠边界的精确语义，Architecture）**：区间「相接」（如 `[1,10]` 与 `[11,20]`）是否算重叠？Product 假设为**不算**（交集为空）。若实现有不同理解，须回到 Product 确认。
- **NQ-B（规范化形式，Architecture）**：`start_ip` / `end_ip` 规范化的确切形式（前导零、是否保留前缀长度）——由 Architecture 定稿，产品仅要求「合法 IPv4 且规范化」。
- **NQ-C（删除守卫对自由文本 `ip_address` 的处理，Architecture）**：既有 `ip_address` 允许任意自由文本（F005 明确不实现格式校验）。当某活跃 `ip_address` 无法解析为 IPv4 时，是否/如何参与「字面落在范围内」判定，属实现细节；但**不得**因此对 `ip_address` 新增格式拒绝（AC-23）。
- **NQ-D（列表查询维度，Architecture）**：是否支持按 `cluster_id` 限定读取、分页形态与路由，由 Architecture 定稿。

---

## Dependencies

- **F001（Cluster，DONE）**：范围段的归属对象；`cluster_id` 活跃性校验依赖 Cluster 模型。
- **F005（IPAddress，DONE）**：提供既有 `IPAddress` 登记 / 唯一性（R-IP-001~003）/ 受控 `cluster_id` 推导 / 软删立场；范围段的删除守卫建立在其模型之上。
- **F021（IP 自动 / 手动分配，BLOCKED）**：下游 Feature，依赖 F020 DONE；其分配语义（DEC-023 第 7~13 项）**不在本次落规则**。

---

## Architecture Handoff

以下问题**由 Architecture 解决**，Product 不代为决定：

1. **数据承载方式**：范围段是新表 / 新列 / migration 的具体形态；`database` 层判定（project-plan 中为初步判断 `true`，待复核）。
2. **同 Cluster「不重叠」的强制方式**：应用层校验 + 漂移查询 vs Postgres 排它约束（如 `btree_gist` / `EXCLUDE`）；ADR-0002 / ADR-0004 下的取舍。
3. **规范化与解析**：IPv4 规范化函数、比较方式（数值 vs 字面）。
4. **契约形态**：范围段 CRUD 端点、字段、分页、按 Cluster 限定读取的路由；`contract.status` 定稿为 READY。
5. **错误码具体取值**：重叠冲突、范围含活跃 IP 的删除冲突（建议 `409` + `ACTIVE_CHILDREN_EXIST` 类）、非法 IPv4 / `start > end` 的 `400` details。
6. **F014 父删子拦集成**：范围段是否纳入既有「活跃子资源」删除守卫声明点，以及范围段删除路径自身如何消费「活跃 IP」守卫（无部分写入 / 并发不变式）。
7. **漂移检测查询（DEC-023 第 6 项建议交付）**：范围段与活跃 IP 一致性/漂移检测查询，以及其回归断言（Product 不将其列为产品 AC）。
8. **并发**：创建 / 修改范围段与并发创建 IP 的隔离与锁序，不得引入新死锁序。

---

## Notes

- 本 Handoff **不覆盖 F021**：分配（自动 / 手动、「最小 IP」、占用判定、耗尽）**不属于 F020**，其产品规则待 F020 DONE 后另行在 §12 落地。
- **需同步项（交协调器，Agent 不得自行修改）**：
  - `docs/product/domain-model.md` §5.7 / §8 / §9 及 `docs/product/domain-model.yaml`：范围段（IPAddressRange / 地址池）作为新领域对象、唯一性（同 Cluster 活跃不重叠）、软删与删除守卫、无状态，需与 R-IP-004 同步。
  - `docs/project/project-plan.yaml` `features[F020].requirements`（当前为 `[]`）：可挂 `R-IP-004`。
- `docs/api/f005-ip-address.md` §非目标与 `docs/product/handoffs/f005-ip-address.md` §Scope 中「IP 池 / 网段 / 子网 / 分配与回收工作流」的排除立场，**仅就范围段部分**由本 Feature 修订；`ip_address` 自由文本登记立场不变。

---

## Handoff Status

`READY FOR ARCHITECT`
