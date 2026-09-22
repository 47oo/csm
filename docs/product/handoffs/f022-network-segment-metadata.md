# Product Handoff — F022 网段自定义名称 / 子网掩码 / VLAN 标注

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager（协调器持久化）
> Date: 2026-09-21
> Feature: **F022 — 网段自定义名称 / 子网掩码 / VLAN 标注**（E02，P1，`depends_on: [F020]` = DONE；分支 `feature/F022-network-segment-metadata`，start `dae7fe9`）
> Product Source: `requirements.md` §12（**修订 R-IP-004**；R-IP-001~003 / R-IP-005~010 保持不变）；`domain-model.md` §5.7 / §8 / §9；`docs/product/handoffs/f020-ip-address-range.md`；`docs/product/handoffs/f021-ip-address-allocation.md`；`docs/api/f020-ip-address-range.md`；`docs/database/f020-ip-address-range-migration.md`；ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005；`docs/project/project-plan.yaml` `decisions_required[DEC-024].resolution`（**权威裁定，RESOLVED 2026-09-21**）

---

## Feature

网段自定义名称 / 子网掩码 / VLAN 标注（F022）— 在 F020 已交付的 **IP 地址范围段（地址池，`ip_address_ranges`）** 上**新增 3 个可选元数据字段**（`name` / `subnet_mask` / `vlan`），并据此**修订 R-IP-004**。**不新建实体，不改变既有范围段语义，不改变 F021 分配行为。**

## Problem

F020 交付后，每个 Cluster 可以有多个地址范围段，但范围段只能靠 `start_ip`–`end_ip` 辨认，运维人员无法为「业务网 / 存储网 / 管理网」这类**业务含义**命名，也无法像在网络规划表里那样标注**子网掩码**与 **VLAN**。结果是地址规划的业务语义仍停留在个人脑袋或外部表格里。

**谁在什么情况下使用**：HPC / AI 集群运维人员与基础设施管理员，在登记 / 查看 / 维护某个 Cluster 的地址规划时，为每个网段填写可读名称（如「业务网」）、子网掩码与 VLAN 标注。

**产品价值**：让网段具备**业务可读标识与网络参数**，而**不引入第二套事实**、不改变既有唯一性 / 重叠 / 软删 / 删除守卫 / 分配语义。

**本 Feature 只修订产品规则 R-IP-004（新增 3 个可选字段）；不新增规则编号；不修改 R-IP-001~003 与 R-IP-005~010。**

---

## Confirmed Requirements

来源：`decisions_required[DEC-024].resolution`（用户 2026-09-21 裁定，RESOLVED）逐条落地（NQ-1 ~ NQ-8）。

1. **新增 3 个可选元数据字段（NQ-1）**：`name` / `subnet_mask` / `vlan`，**均为可选**（未登记允许 `NULL`）。其它字段（`description` / 用途等）仍不新增。
2. **`name`（NQ-2）**：可选（可空）；**同一 Cluster 内活跃范围段唯一**；**区分大小写**（§22）；**软删释放**（R-DELETE-006）；**跨 Cluster 可重复**。
3. **`subnet_mask`（NQ-3）**：**dotted-quad IPv4**（如 `255.255.255.0`），可选；**V1 仅 IPv4**，**不使用 CIDR 前缀长度**；必须是**合法 IPv4 掩码**（二进制**连续 1 后连续 0**）。
4. **掩码一致性（NQ-4）**：**不强制** `subnet_mask` 与 `start_ip`–`end_ip` 自洽；掩码为**描述性元数据**。用户示例 `10.1.1.1` 到 `10.1.2.10`、掩码 `255.255.255.0`（跨 `/24` 边界）**允许**。
5. **`vlan`（NQ-5）**：**整数 `1`–`4094`**（`0` / `4095` 保留，不接受），可选；**不唯一**（同 Cluster 多网段可共用同一 VLAN）。
6. **唯一性边界（NQ-6）**：**仅**新增「`name` 同 Cluster 活跃唯一」一条；**不新增 VLAN 唯一性**；其余仍以 **R-IP-001** 为唯一性边界。
7. **承载方式与既有影响（NQ-7）**：**扩展既有 `ip_address_ranges` 表**（加 3 个可空列）；**精确修订 f020 契约（纯增量）**；**不推翻** F020 / F021 既有结论；**V1 分配不按掩码 / VLAN 过滤**（F021 语义不变）。
8. **迁移（NQ-8）**：migration `0010_f022_ip_range_metadata`（`down_revision = "0009_f020_ip_address_ranges"`），**3 个可空列 + `name` 的 partial unique**（`WHERE deleted_at IS NULL AND name IS NOT NULL`）；**无数据回填**（既有行取 `NULL`）。
9. **字段集合封闭**：`id` / `cluster_id` / `start_ip` / `end_ip` / `created_at` / `updated_at` + 3 个可选字段 `name` / `subnet_mask` / `vlan`。**不接受** `description` / 用途 / `status` / `deleted_at`（客户端）/ CIDR / IPv6 / 网关 / DHCP / DNS / 使用率 等任何未确认字段。
10. **既有语义逐条不变**：重叠判定、软删释放、删除守卫、无状态、IPv4 合法性与规范化、R-IP-001~003、F021 分配行为。

## Confirmed Domain Rules

| 规则 / 原则 | 内容 | 来源 |
|---|---|---|
| **R-IP-004（本次修订）** | 范围段：`start_ip`–`end_ip` IPv4 / 恰属一个活跃 Cluster / 同 Cluster 活跃不重叠、跨 Cluster 可重复 / 无状态 / 软删 / 范围含活跃 IP 时禁删；**新增可选 `name`（同 Cluster 活跃唯一、大小写敏感、软删释放）/ `subnet_mask`（dotted-quad IPv4 合法掩码，不强制自洽）/ `vlan`（整数 1–4094，不唯一）** | §12（本 Feature 修订） |
| R-IP-001 | 同一 Cluster 内 `ip_address` 字面唯一；partial unique index 为最终权威 | §12（**保持不变**） |
| R-IP-002 / R-IP-003 | 跨 Cluster 可重复；不考虑 VRF / 网络命名空间 | §12（**保持不变**） |
| R-IP-005 ~ R-IP-010 | 分配语义 | §12（**保持不变**；分配不按掩码 / VLAN 过滤） |
| §22 | 大小写敏感为默认立场 | §22（`name` 比较适用） |
| §17 / R-DELETE-001~006 | 逻辑删除、不物理删、无 Undelete、父有活跃子不得删、不级联、**软删释放唯一性** | §17；ADR-0004 |
| §21 | 关键冲突必须在保存前阻止，不得只依赖 UI | §21 |
| 寻址与状态码 | 写走 `id`；`204` / `404` / `409` / `400` | ADR-0003 |
| 唯一性落地 | partial unique index（predicate `deleted_at IS NULL`）为最终权威；大小写敏感不声明 `COLLATE` / 不用 `lower()` | ADR-0002；ADR-0004 |
| 认证 | 所有 `/api/*`（登录除外）要求认证；V1 仅两态，无 RBAC | ADR-0005 |
| 字段封闭先例 | 未确认即不实现、不承诺（F005 `ip_address`、F007 Container `name`） | F005 / F007 |

## Scope

### 本次包含

1. 新增 3 个可选字段 `name` / `subnet_mask` / `vlan`，登记（POST）可写入、响应回读。
2. 可选性：缺失不阻断登记；未登记为空（`NULL`）。
3. `name` 语义与唯一性：同 Cluster 活跃唯一、区分大小写、软删释放、跨 Cluster 可重复；后端 + 数据库 partial unique 共同保证（保存前阻止）。
4. `subnet_mask` 合法性：dotted-quad IPv4 合法掩码（连续 1 后连续 0）；非法拒绝；**不强制**与 start–end 自洽。
5. `vlan` 取值：整数 `1`–`4094`；`0` / `4095` / 越界 / 非整数拒绝；**不唯一**。
6. 字段集合封闭：请求 / 响应恰为 6 个既有字段 + 3 个可选字段；拒绝其它字段。
7. 既有语义不变。
8. 前端：范围段列表 / 详情 / 登记 / 修正处呈现与录入三字段；三态与 Empty / Not Found 可区分；错误按 `error.code`（结合 `details[].code`）分支。
9. 契约增量修订：在既有 `docs/api/f020-ip-address-range.md`（现 READY）上**纯增量**追加三字段与错误语义。

### 本次明确不包含

1. CIDR 表示；2. IPv6；3. 掩码与 start–end 自洽校验；4. VLAN 唯一性；5. `description` / 用途 / `status` / `deleted_at`（客户端）/ 网关 / DHCP / DNS / 使用率 等未确认字段；6. 分配行为变更（不按掩码 / VLAN 过滤）；7. 自动资产发现 / 外部同步 / 拓扑 / 使用率 / 冲突扫描 / 导出 / 审计；8. 新实体（不新建网段 / VLAN / 子网表）；9. 修改 R-IP-001~003、R-IP-005~010、F005 `ip_address` 立场；10. 物理删除 / Undelete / 恢复 / 批量删除。

### 本次未涉及

- 网段使用率 / 剩余地址展示；按 VLAN / 掩码 / 名称的筛选 / 排序 / 导出；网段与已登记 IP 的对应视图；掩码从 start–end 自动推导；VLAN 全局规划 / 冲突检测；`name` 的 `by-name` 别名寻址。

---

## Acceptance Criteria

### 认证
- **AC-01（认证）**：未认证访问任何范围段端点 → `401 UNAUTHENTICATED`，不返回资源数据、不产生写入。

### 字段与可选性
- **AC-02（登记成功，字段集合封闭）**：`POST` 携带活跃 `cluster_id` + 合法 `start_ip` / `end_ip` + 三个新字段的合法值 → `201`；响应字段集合**恰为** `{id, cluster_id, start_ip, end_ip, name, subnet_mask, vlan, created_at, updated_at}`；无 `deleted_at` / `status` / `description` / 用途。
- **AC-03（请求字段封闭）**：未确认字段（`description` / 用途 / `status` / `deleted_at` / `id` / `created_at` / `updated_at` / `gateway` 等）→ `400 VALIDATION_ERROR`，不产生记录。
- **AC-04（三字段可选，缺失不阻断）**：仅携带 `cluster_id` / `start_ip` / `end_ip` → `201`，三字段响应均为 `null`（返回 `null` 而非省略）。
- **AC-05（三字段往返一致）**：携带合法三字段登记后再次读取 → 返回相同值。

### `name` 语义与唯一性
- **AC-06（同 Cluster 活跃唯一，保存前阻止）**：同 Cluster 已存在活跃 `name = "业务网"`，再登记相同 `name` → 写入被阻止、不产生记录、非 5xx（建议 `409 CONFLICT`；`details[].code` 由 Architecture 定稿，建议 `DUPLICATE`）。
- **AC-07（跨 Cluster 可重复）**：Cluster A 与 B 各登记 `name = "业务网"` → 均 `201`。
- **AC-08（区分大小写）**：同 Cluster 内 `name = "web"` 与 `name = "Web"` → 均 `201`（§22）。
- **AC-09（软删释放）**：`name = "业务网"` 的范围段软删后，同 Cluster 可再登记 → `201`（R-DELETE-006）。
- **AC-10（未定义约束不实现）**：`name` 无长度 / trim / 空串 / 字符集 / `/` 禁令约束；空串与含首尾空白当前被接受。**不得**解读为「空 `name` 合法」已确认（NQ-A）。

### `subnet_mask` 合法性与不强制自洽
- **AC-11（合法掩码接受）**：`255.255.255.0`、`255.255.0.0`、`255.0.0.0` 等连续 1 后连续 0 的 dotted-quad → `201` 并原样回读。
- **AC-12（非法掩码拒绝）**：`255.0.255.0`（非连续）、`255.255.255.1`、`255.255.255.256`、`10.0.0.1`（非掩码）、`abc`、`/24`、`2001:db8::1`、空串、含空白 → `400 VALIDATION_ERROR` + `details[].field`，不产生记录。
- **AC-13（不强制与 start–end 自洽）**：`start_ip = 10.1.1.1`、`end_ip = 10.1.2.10`、`subnet_mask = 255.255.255.0` → `201`。
- **AC-14（V1 仅 IPv4，不用 CIDR）**：不接受前缀长度形式；IPv6 掩码被拒。

### `vlan` 范围与不唯一
- **AC-15（边界接受）**：`vlan = 1` 与 `vlan = 4094` → 均 `201`。
- **AC-16（保留值 / 越界 / 非整数拒绝）**：`vlan = 0` / `4095` / `4096` / `-1` / `100.5` / `"100"` / `true` → `400 VALIDATION_ERROR` + `details[].field`，不产生记录。
- **AC-17（不唯一）**：同 Cluster 两个不同范围段共用同一 `vlan` → 均 `201`；不存在 VLAN 唯一约束。

### 唯一性边界
- **AC-18（仅新增 name 唯一性）**：唯一性约束恰为「同 Cluster 活跃范围段 `name` 唯一」；不存在 VLAN 唯一 / 复合唯一 / 其它第二维度唯一。

### 既有语义不变（逐条）
- **AC-19（重叠判定不变）**：同 Cluster 活跃范围段重叠仍被保存前阻止（`409 CONFLICT`，`details[].code == "OVERLAP"`）；新字段不参与重叠；跨 Cluster 同范围仍可共存。
- **AC-20（软删释放不变）**：软删后同 Cluster 可登记重叠的新范围段 → `201`。
- **AC-21（删除守卫不变）**：范围内有活跃 IP → `DELETE` 仍 `409` + `ACTIVE_CHILDREN_EXIST`，`deleted_at` 仍 `NULL`；新字段不影响。
- **AC-22（无状态不变）**：请求 / 响应 / 表 / 端点 / 查询参数仍无 `status`。
- **AC-23（IPv4 规范化不变）**：`start_ip` / `end_ip` 仍按 canonical dotted-quad 规范化（`010.000.000.001` → `10.0.0.1`）。
- **AC-24（R-IP-001~003 与 R-IP-005~010 不变）**：同 Cluster IP 字面唯一、跨 Cluster 可重复、不考虑 VRF，以及 F021 分配语义均不被修改。
- **AC-25（分配不按掩码 / VLAN 过滤）**：不存在按 `subnet_mask` / `vlan` 过滤 / 约束分配的功能；F021 契约逐条不变。
- **AC-26（F005 `ip_address` 立场不变）**：F005 端点 / 自由文本登记语义不变。

### 边界与前端
- **AC-27（不引入 CIDR / IPv6 / 网关 / DHCP / DNS / 使用率 / 自动发现 / 外部同步）**。
- **AC-28（前端三态与错误分支）**：三态互异；Empty 与 Not Found 可区分；错误按 `error.code`（结合 `details[].code`）渲染，不解析 `message`，不重复实现业务校验。
- **AC-29（契约一致性）**：F022 修订后的契约已持久化且 `contract.status = READY`；无「契约禁止、实现却有」分裂。
- **AC-30（迁移形态）**：migration `0010_f022_ip_range_metadata`（`down_revision = "0009_f020_ip_address_ranges"`）新增 3 个可空列 + `name` partial unique（`WHERE deleted_at IS NULL AND name IS NOT NULL`）；**无回填**；不改其它表 / 列 / 约束。

## Assumptions

- A-1：新字段可经既有 `PATCH` 修正路径维护；`null` 清空与「至少一个可变字段」的交互由 Architecture 定稿（NQ-C）。若最终裁定不可变，属移除一条能力，不改变 AC 判定。
- A-2：未登记时三字段在响应中返回 `null`（沿用 F007 Container 可选字段先例）。
- A-3：`name` 唯一冲突应用层先行检查返回 `409`，partial unique index 为最终权威（ADR-0004）。
- A-4：掩码与 `vlan` 校验在保存路径执行，拒绝返回 `400` + `details[].field`；契约形态由 Architecture 定稿。

## Proposed Rules

**无。** DEC-024 已由用户裁定，规则以修订后的 R-IP-004 固化。`name` 的长度 / trim / 空串 / 字符集属**未确认即不实现、不承诺**，不是 PROPOSED 行为规则。

## Open Questions

### Blocking

**无。** DEC-024 已 RESOLVED；依赖 F020 已 DONE。

### Non-blocking（归 Architecture 定稿）

- **NQ-A（`name` 未定义约束）**：不实现、不承诺（沿用 F005 / F007 先例）；空串当前被接受但不得解读为已确认合法。
- **NQ-B（掩码存储表示与校验实现）**：TEXT dotted-quad vs 数值；由 Architecture 定稿。
- **NQ-C（`PATCH` 可变语义）**：三字段可变性、`null` 清空、空 body 交互，由 Architecture 定稿。
- **NQ-D（`name` 唯一冲突错误码）**：建议 `409 CONFLICT` + `details[].code = "DUPLICATE"`。
- **NQ-E（掩码 / VLAN 校验错误形态）**：建议 `400 VALIDATION_ERROR` + `details[].field`。
- **NQ-F（`name` partial unique 落地）**：索引命名、大小写敏感（不声明 `COLLATE` / 不用 `lower()`）、ORM 与 `alembic check` 一致。
- **NQ-G（迁移细节）**：三列类型（`vlan` 整数 + `CHECK` 1–4094）、`down_revision`、`downgrade`。
- **NQ-H（前端呈现）**：字段呈现；`name` 非全局唯一，默认不提供 `by-name` 别名。

## Dependencies

- **F020（DONE，merge `e4291a1`）**：范围段模型——真实前置，已满足。
- **F005（DONE）**：`ip_address` 自由文本立场不变；`name` 未定义约束先例。
- **F014（DONE）**：统一软删路径；partial unique 语义。
- **F001（DONE）**：Cluster 归属（`name` 唯一性边界）。
- **F021（DONE，merge `011d05d`）**：非本 Feature 依赖；分配不按掩码 / VLAN 过滤，F021 语义 / 契约不变。

## Architecture Handoff

须由 Architecture 解决：

1. **契约修订（纯增量）**：在 `docs/api/f020-ip-address-range.md` 追加 `name` / `subnet_mask` / `vlan`（§2 资源表示扩为 9 字段；§3.1 POST request 增加 3 个可选字段；§3.4 PATCH 可变字段集合扩展；错误语义新增 name 重复 `409`、mask/vlan 非法 `400`）；`contract.status` 维持 READY。
2. **migration `0010_f022_ip_range_metadata`**：`down_revision = "0009_f020_ip_address_ranges"`；`ALTER TABLE ip_address_ranges ADD COLUMN` 3 个可空列 + `name` partial unique（`WHERE deleted_at IS NULL AND name IS NOT NULL`，大小写敏感）；无回填；`downgrade` 逆序；不改 `0001`–`0009` 与其它表。
3. **`name` 唯一性落地与最终权威**：应用层 `409` + partial unique index（`23505` 经既有 `sqlstate.py` → `409`，永不 500）。
4. **掩码 / VLAN 校验实现**：掩码合法性（连续 1 后连续 0）与 dotted-quad 解析、`vlan` 整数范围；复用 / 扩展 `app/ip_address_ranges/ipv4.py`，不复制第二份解析。
5. **`PATCH` 语义定稿**。
6. **ORM 元数据一致性**：`alembic check` 无漂移；partial unique 不被 autogenerate 误删。
7. **分配不变式保障**：可失败 guard / 回归断言固定「分配不按掩码 / VLAN 过滤」，F021 零改动。
8. **前端接线**。
9. **错误码定稿**。
10. **「不实现」的结构性保障**：可失败 guard 固定不存在 name 长度 / trim / 空串 / 字符集校验、掩码自洽校验、VLAN 唯一性、CIDR / IPv6 / 网关 / DHCP / DNS / 使用率字段或端点。

## Notes

- 本 Handoff 严格落地 DEC-024（2026-09-21 用户裁定，RESOLVED）；Product 未发明超出裁定的规则。
- `name` 未定义约束按 F005 / F007 先例处理：未确认即不实现、不承诺。
- 本 Feature 仅新增「name 同 Cluster 活跃唯一」；`ip_address` 唯一性仍为 R-IP-001，范围段重叠仍为 R-IP-004 原有语义。
- 同步项：`requirements.md` §12 修订 R-IP-004 + 变更记录；`domain-model.md` / `.yaml` 补充；`project-plan.yaml` F022 requirements 挂 R-IP-004。

## Handoff Status

`READY FOR ARCHITECT`