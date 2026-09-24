# Product Handoff — F021 IP 地址自动 / 手动分配

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager（协调器持久化）
> Date: 2026-09-21
> Feature: **F021 — IP 地址自动 / 手动分配**（E02，P1，`depends_on: [F020, F005, F004, F002]`，均已 DONE）
> Product Source: `requirements.md` §12（**R-IP-001~004 保持不变，新增 R-IP-005 ~ R-IP-010**）；§9、§15、§17、§21、§22、§23、§25、§29；`domain-model.md` §5.7 / §8 / §9 及 `domain-model.yaml`；`docs/product/handoffs/f020-ip-address-range.md`；`docs/architecture/f020-ip-address-range-handoff.md`；`docs/api/f005-ip-address.md`；`docs/api/f020-ip-address-range.md`；ADR-0002 / ADR-0003 / ADR-0004 / ADR-0005；`docs/project/v1/project-plan.yaml` `decisions_required[DEC-023].resolution`（第 7~13 项，用户 2026-09-20 裁定，RESOLVED）；用户 2026-09-21 对 **PR-01** 的补充裁定（采纳 A：手动分配规范化写入；非法格式不允许输入）

---

## Feature

IP 地址自动 / 手动分配（F021）— 在 F020 已登记的某个 Cluster 的 IP 地址范围段（地址池）之上，**为指定 NetworkInterface 创建一条绑定该 NIC 的 IPAddress**：自动分配选取该 Cluster 全部活跃范围段并集内**数值最小的未占用 IPv4**；手动分配要求输入 IP 落在某个活跃范围内且未占用。**不新建分配 / 预留实体。**

## Problem

F020 交付了「每个 Cluster 有哪些合法地址段」，但**只做到范围段的登记与维护**，F020 契约与 F005 契约均**显式排除**「IP 分配与回收工作流 / 自动生成 IP」。因此今天运维人员仍要人工翻查范围段、手工挑一个「没被占用」的 IP、再手工到 F005 端点建 IPAddress 并绑定 NIC，多人协作时凭经验避免撞号。

**谁在什么情况下使用**：HPC / AI 集群运维人员与基础设施管理员，在给某台机器的某张网络接口配置地址、需要快速取「该 Cluster 下一个可用 IP」或按规划手动指定一个地址时使用。

**产品价值**：把「选地址 + 建 IPAddress」从人工脑力活变成系统可判定、可重复、可并发安全的操作，同时**保持在既有 R-IP-001 唯一性边界内**，不引入第二套分配事实。

**本 Feature 只新增产品规则 R-IP-005 ~ R-IP-010；不修改任何既有规则（R-IP-001 ~ R-IP-004 原样保留）。**

---

## Confirmed Requirements

来源：`decisions_required[DEC-023].resolution`（用户 2026-09-20 裁定）中**属 F021 的第 7~13 项**，固化为 `requirements.md` §12 R-IP-005 ~ R-IP-010；以及用户 2026-09-21 对 **PR-01** 的裁定。

1. **分配产物（DEC-023 第 7 项）**：分配（自动 / 手动）的**唯一产物**是创建一条**现有 IPAddress**（沿用 F005）；**不新建**分配 / 预留实体、分配表 / 字段 / 状态。
2. **目标 NIC（DEC-023 第 8 项）**：分配**必须**指定**恰好一个活跃 NetworkInterface**；Cluster 由 `NIC → BareMetal → Cluster` **受控推导**；请求与响应均**不含** `cluster_id`。
3. **自动分配（DEC-023 第 9 项）**：在目标 Cluster **全部活跃范围段的并集**中取**数值最小的未占用 IPv4**（**跨范围段全局最小**）。
4. **已占用判定（DEC-023 第 10 项）**：目标 Cluster 内存在**活跃（未软删）**且 `ip_address` **字面相同**的 IPAddress ⇒ 占用；**软删释放**；**无隐式保留地址**。
5. **手动分配（DEC-023 第 11 项）**：手动给出的 IP 必须**合法 IPv4**、**落在某个活跃范围内**且**未占用**；**范围外的字面 IP 仍走现有 F005 登记端点**（向后兼容）。
6. **耗尽（DEC-023 第 12 项）**：无可用 IP → 明确的**非 500** 错误；**不创建任何 IP**。
7. **唯一性 / 并发（DEC-023 第 13 项）**：**不新增**超出 R-IP-001 的唯一性；以 R-IP-001 partial unique 索引为**最终权威**。
8. **规范化与字面边界**：自动 / 手动分配选中的地址以**规范化 dotted-quad** 写入；**占用判定仍按字面相等**。故活跃字面 `010.0.0.1` / `10.0.0.1/16` **不阻止**分配 `10.0.0.1`（字面不同，R-IP-001 不冲突）。
9. **手动分配格式（PR-01，用户 2026-09-21 裁定 A）**：合法但非规范输入**规范化后再写入**；**地址格式不合法则不允许输入**（拒绝，不创建记录）。仅作用于分配路径，F005 登记路径不受影响。
10. **推导活跃性（沿用 F005）**：目标 NIC 不存在 / 已软删，或其宿主 BareMetal 不活跃 → 分配被拒（**非 5xx**），不创建 IP。
11. **字段集合封闭**：分配请求**不接受** `cluster_id` / `status` / CIDR / 保留地址开关 / 分配对象 / 分配时间 / 回收状态 等未确认字段；响应使用 F005 既有 IPAddress 表示。

---

## Confirmed Domain Rules

| 规则 / 原则 | 内容 | 来源 |
|---|---|---|
| R-IP-001 | 同一 Cluster 内 `ip_address` **字面唯一**；partial unique index 为最终权威 | §12（**保持**不变） |
| R-IP-002 | 不同 Cluster 之间允许相同 IP | §12（**保持**不变） |
| R-IP-003 | V1 不考虑 VRF / 网络命名空间 | §12（**保持**不变） |
| R-IP-004 | 范围段（地址池）语义：start–end / 恰属一个活跃 Cluster / 同 Cluster 活跃不重叠、跨 Cluster 可重复 / 无状态 / 软删 / 范围含活跃 IP 时禁删 | §12（**保持**不变） |
| **R-IP-005 ~ R-IP-010（新增）** | 分配产物与目标 NIC、自动分配、已占用判定与比较边界、手动分配与格式拒绝、耗尽、唯一性与并发 | §12（本 Feature 落地） |
| IP 地址 → NIC 必选 | IP 地址必须绑定在网络接口上（N:1 Mandatory） | §15；`domain-model.md` §5.7 / §6 |
| 网络接口 → 裸金属必选 | NIC 绑定到 BareMetal；Cluster 经 BareMetal 推导 | §15；`domain-model.md` §6；R-NIC-003 |
| Q-002=B | IPAddress 无状态 | `domain-model.md` §7.2 |
| §9 / R-DELETE-001~006 | 逻辑删除、不物理删、无 Undelete、父有活跃子不得删、不级联、软删释放唯一性 | §17；ADR-0004 |
| §21 | 关键冲突（含同 Cluster IP 重复）必须在保存前阻止，不得只依赖 UI | §21 |
| §22 | 大小写敏感为默认立场 | §22 |
| 寻址与状态码 | 写走 `id`；`204` / `404 NOT_FOUND` / `409 CONFLICT` / `400 VALIDATION_ERROR` | ADR-0003 |
| 唯一性冲突落地 | partial unique index（predicate `deleted_at IS NULL`）为最终权威 | ADR-0002；ADR-0004 |
| Cluster 归属受控推导 | `cluster_id` 由单一受控写入路径推导，调用方不可指定 / 不可读 | ADR-0002 §2；F005 契约 §2 / §6 |
| 认证 | 所有 `/api/*`（登录除外）要求认证；V1 仅两态，无 RBAC | ADR-0005 |

---

## Scope

### 本次包含

1. **自动分配**：对指定活跃 NIC，在其推导出的 Cluster 的**全部活跃范围段并集**内取**数值最小未占用 IPv4**，创建一条绑定该 NIC 的 IPAddress，写入规范化 dotted-quad。
2. **手动分配**：调用方给定一个 IP；合法 IPv4 + 数值落在该 Cluster 某活跃范围内 + 未占用 → 创建 IPAddress；输入非规范则规范化后写入；非法格式被拒。
3. **目标 NIC 语义**：必选且恰好一个活跃 NIC；NIC 不存在 / 已软删 / 宿主 BareMetal 不活跃 → 拒绝（非 5xx）。
4. **Cluster 受控推导**：复用 F005 的 `NIC → BareMetal → Cluster` 推导；请求 / 响应均不含 `cluster_id`。
5. **已占用判定**：同 Cluster 活跃且**字面相同**的 `ip_address`；软删释放；**无隐式保留地址**。
6. **耗尽错误**：无可用 IP → 明确非 500 错误，不创建任何 IP。
7. **不新增唯一性**：唯一性仍为 R-IP-001；partial unique index 为最终权威。
8. **请求字段封闭**：拒绝一切未确认字段。
9. **前端**：分配入口与结果呈现；三态与错误的 `error.code` 分支；不在客户端实现分配业务校验（§21）。
10. **契约一致性**：本 Feature 契约须持久化且 `status = READY`，不得「契约禁止、实现却有」的分裂。

### 本次明确不包含

1. **新分配 / 预留实体 / 分配表 / 分配字段 / 分配状态**（产物是 IPAddress）。
2. **DHCP / DNS / 外部平台同步 / 自动资产发现**（§23）。
3. **CIDR 与 IPv6**（R-IP-004）。
4. **保留地址跳过**：不自动跳过网络 / 广播 / 网关；无「保留地址」开关。
5. **新增唯一性约束 / VRF**：不得绕过 R-IP-001。
6. **无 NIC 的分配**、多父 / 载体选择器。
7. **修改 F005 的 `ip_address` 自由文本登记语义**。
8. **修改 R-IP-001 ~ R-IP-004 的任何一条**。
9. **分配回收 / 解绑 / 分配历史 / 审计**：释放唯一途径是既有 F005 对 IPAddress 的逻辑删除。
10. **使用率统计 / 冲突扫描 / 导出 / 批量分配**。

### 本次未涉及

- 分配的分配对象语义（给谁分配、原因 / 备注）；批量分配；审计 / 历史 / 操作人；自动分配的范围遍历策略配置；保留地址 / 排除表；与 F010 / F018 的整合呈现。

---

## Acceptance Criteria

### 认证与契约

- **AC-01（认证）**：未认证访问任何分配端点 → `401 UNAUTHENTICATED`，不返回资源数据、不产生写入。
- **AC-02（分配产物为 IPAddress，字段封闭）**：成功分配 → `201`，响应结构**恰为** F005 IPAddress 表示 `{id, network_interface_id, ip_address, created_at, updated_at}`；无 `cluster_id` / `status` / `deleted_at` 等。
- **AC-03（请求字段封闭）**：未确认字段（`cluster_id` / `status` / `deleted_at` / `reserved_addresses` / 用途 / 分配对象 等）→ `400 VALIDATION_ERROR`，不产生记录。
- **AC-29（契约一致性）**：F021 契约已持久化且 `contract.status = READY`；无「契约禁止、实现却有」分裂。

### 目标 NIC 与 Cluster 推导

- **AC-04（NIC 必选）**：缺失 `network_interface_id` 或非整数 → `400 VALIDATION_ERROR` + `details[].field`，不产生记录。
- **AC-05（NIC 须活跃，宿主须活跃）**：引用不存在 / 已软删 NIC，或宿主 BareMetal 不活跃 → 分配被拒、不产生记录、**不得 5xx**（建议 `404 NOT_FOUND`，取值由 Architecture 定稿）。
- **AC-06（Cluster 受控推导，请求 / 响应无 cluster_id）**：请求不接受 `cluster_id`；直连 DB 校验新建 IP 的 `cluster_id` = 其 NIC 宿主 BareMetal 的 `cluster_id`；响应无 `cluster_id`。
- **AC-07（推导一致性）**：分配后 F005 §6.3 `cluster_id` 漂移查询（IP 的 cluster_id ≠ 宿主 BareMetal 的 cluster_id）仍为 **0 行**。

### 自动分配

- **AC-08（并集全局最小未占用）**：Cluster 有多个活跃范围段（如 `[10.0.0.10,10.0.0.12]` 与 `[10.0.0.1,10.0.0.3]`）且无占用 → 自动分配返回 `10.0.0.1`（跨范围段数值全局最小）。
- **AC-09（跳过已占用取下一个最小）**：`10.0.0.1` 已活跃占用 → 自动分配返回 `10.0.0.2`，依此类推。
- **AC-10（写入规范化 dotted-quad）**：写入值为 canonical dotted-quad（无前导零、无前缀长度），再次读取得同一规范值。
- **AC-11（无隐式保留地址）**：范围 `[10.0.0.0,10.0.0.255]` 且无占用时返回 `10.0.0.0`（网络地址不被跳过）；不跳过广播 / 网关。

### 已占用判定与比较边界

- **AC-12（字面相等占用）**：同 Cluster 活跃且**字面相同**的 `ip_address` 判为占用，自动分配跳过。
- **AC-13（字面不同不占用）**：不存在活跃且字面相同的 `ip_address` ⇒ 未占用。
- **AC-14（软删释放）**：同 Cluster 该字面的 IPAddress 已软删 ⇒ 不再占用，可再次分配。
- **AC-15（字面 vs 数值边界）**：同 Cluster 活跃字面 `010.0.0.1` 或 `10.0.0.1/16` **不阻止**自动分配选中并写入 `10.0.0.1`；范围归属按数值、占用按字面，二者不混用。
- **AC-16（跨 Cluster 边界）**：Cluster A 已占用某字面时，Cluster B 可取得相同数值 / 字面（R-IP-002）。

### 手动分配

- **AC-17（范围内且未占用 → 成功）**：合法 IPv4、数值落在某活跃范围内且未占用 → `201`。
- **AC-17b（非规范输入规范化写入）**：输入 `010.0.0.5` → 写入并返回 `10.0.0.5`（PR-01 A）。
- **AC-18（范围外被拒）**：合法 IPv4 但不落在任何活跃范围内 → 被拒、非 5xx、不创建记录（取值由 Architecture 定稿）。
- **AC-19（范围内已占用被拒）**：落在范围内但被同 Cluster 活跃 IPAddress 字面占用 → 被拒（R-IP-001）、非 5xx、不创建记录。
- **AC-20（非法 IPv4 被拒，不允许输入）**：`10.0.0.256`、`10.0.0`、`abc`、`1.2.3.4/24`、`2001:db8::1`、空串、含空白 → `400 VALIDATION_ERROR`，不创建记录。
- **AC-21（范围外不拦截 F005）**：F005 既有 `POST /api/ip-addresses` 保持原样，范围外字面仍可登记（`201`）；F021 不替换、不改版 F005 端点。

### 耗尽

- **AC-22（并集耗尽 → 非 500，无写入）**：并集内全部 IPv4 均被活跃占用 → 自动分配返回明确非 500 错误（建议 `409 CONFLICT` + `details[].code="NO_AVAILABLE_IP"`），不创建任何 IPAddress。
- **AC-23（无活跃范围段 → 同耗尽语义）**：无活跃范围段时同样返回非 500 耗尽错误，不创建记录、不跨 Cluster 取址。

### 唯一性与并发

- **AC-24（不新增唯一性）**：不存在超出 R-IP-001 的唯一性约束；无新增唯一索引 / 第二维度列。
- **AC-25（并发同一 IP → 至多一条成功）**：两条并发选中同一 IP → 至多一条 `201`，另一条以既有 `409 CONFLICT`（`details[].code="DUPLICATE"`）返回、非 5xx；结束后同 Cluster 该字面活跃行 ≤ 1。
- **AC-26（最终权威为 partial unique）**：绕过应用层直连插入同 Cluster 活跃重复字面 → 触发 R-IP-001 partial unique，经通用映射 → `409`（永不 500）。

### 既有语义不变（逐条）

- **AC-27（R-IP-001 ~ R-IP-004 不变）**：四条规则的语义与实现均不被本 Feature 修改。
- **AC-28（`ip_address` 自由文本立场不变）**：F005 既有行为保持不变（字面精确比较、不实现 / 不承诺格式校验与归一化、无状态、IP→NIC 必选）；R-IP-008 的「拒绝非法格式」仅作用于分配路径。

### 边界

- **AC-30（不引入分配实体）**：不存在分配 / 预留表、列、状态或独立端点；分配产物只是 IPAddress 行。
- **AC-31（不引入 CIDR / IPv6 / 保留地址开关）**。
- **AC-32（不引入 DHCP / DNS / 外部同步 / 自动发现）**。
- **AC-33（前端三态与错误分支）**：三态互异；错误按 `error.code`（结合 `details[].code`）渲染，不解析 `message`，不在客户端重复实现业务校验。

---

## Assumptions

- A-1：分配成功响应复用 F005 IPAddress 表示，**不含** `cluster_id`。
- A-2：自动 / 手动分配写入的规范化形式与 F020 范围字段一致（canonical dotted-quad）。
- A-3：分配请求的 NIC 活跃性判定沿用 F005（NIC 与宿主 BareMetal 均须活跃）。
- A-4：认证 / 错误信封 / 前端三态沿用既有约定。
- A-5：自动分配「并集内最小」按 IPv4 无符号 32 位整数**数值**比较。

## Proposed Rules

无。PR-01 已由用户 2026-09-21 裁定（采纳 A：手动分配规范化写入；非法格式不允许输入），已固化为 R-IP-008，不再是 PROPOSED。

---

## Open Questions

### Blocking

**无。** DEC-023 已 RESOLVED，PR-01 已裁定；依赖 F020 / F005 / F004 / F002 均 DONE。

### Non-blocking（归 Architecture 定稿）

- **NQ-A（分配契约形态）**：端点 URI / 方法、自动与手动是同一端点带模式还是两个端点、请求体字段与分派、响应形态。
- **NQ-C（错误码具体取值）**：耗尽（建议 `409` + `NO_AVAILABLE_IP`）、手动范围外、手动已占用（是否沿用 `DUPLICATE`）、NIC 不存在 / 已删（建议 `404 NOT_FOUND`）的精确取值。
- **NQ-D（并发实现）**：并发自动分配不产生重复 / 耗尽判定与插入原子性 / 锁序 / 是否重试；不得新增 R-IP-001 之外的唯一性或第二维度。
- **NQ-E（layers 复核）**：`database` 层是否需变更 / 辅助索引。
- **NQ-F（比较边界实现）**：复用 F020 的 `ipv4` 纯函数与 R-IP-001 partial unique。
- **NQ-G（前端组织）**：分配入口落点与结果呈现。

---

## Dependencies

- **F020（DONE，merge e4291a1）**：提供分配地址范围段。
- **F005（DONE）**：提供 IPAddress 登记模型、R-IP-001 唯一性、受控 `cluster_id` 推导、软删立场、自由文本 `ip_address` 立场。
- **F004（DONE）**：目标 NIC；**F002（DONE）**：NIC → BareMetal → Cluster 推导链；**F001（DONE）**：Cluster 归属对象。
- **F014（DONE）**：软删唯一路径。
- **F021 契约（REQUIRED，待 Architecture 落 READY）**：新建 `docs/api/f021-ip-address-allocation.md`；`docs/api/f005-ip-address.md` §非目标中「分配与回收工作流 / 自动生成 IP」一句由 Architecture 精确修订（`ip_address` 自由文本立场不变）。

---

## Architecture Handoff

以下问题**由 Architecture 解决**，Product 不代为决定：

1. **分配契约形态**：端点 URI / 方法 / 请求响应 schema / 字段封闭集合；自动与手动是同一端点还是两个端点。
2. **错误码定稿**：耗尽、手动范围外、手动已占用、NIC 不存在 / 已删的精确取值与 `details[]` 形态。
3. **并发与原子性**：并发自动分配 / 并发手动分配同一地址的实现（锁序 / 串行化 / 重试 / SAVEPOINT）；耗尽判定与插入必须原子；不得引入 R-IP-001 之外的新唯一性或新死锁序。
4. **复用既有推导与守卫**：分配必须经 F005 的**单一受控 `cluster_id` 写入路径**；不得新增写 `deleted_at` 的路径（仍唯一为 `soft_delete`）。
5. **范围枚举与比较实现**：活跃范围段并集的数值枚举与活跃 IPAddress 字面比较；复用 `app/ip_address_ranges/ipv4.py` 纯函数，不复制第二份解析。
6. **`database` 层复核**：是否需新表 / 新列 / 新索引；产物复用 `ip_addresses` 表时 migration 需求；在 project-plan `layers` 中定稿。
7. **F005 / F020 契约非目标修订位置**：由 Architecture 在 F021 契约中精确修订（仅该立场）。
8. **前端**：分配入口、三态、错误 `error.code` 分支。
9. **漂移 / 一致性回归**：分配后保持 F005 §6.3 漂移查询为 0。

---

## Notes

- 分配语义唯一依据是 DEC-023 第 7~13 项（2026-09-20 用户裁定）与 PR-01 裁定（2026-09-21）；Product 未发明超出裁定的规则。
- **「字面比较」与「范围数值比较」是两个不同层次，不得混用**：范围归属按 IPv4 数值；占用 / 唯一性按 `ip_address` 字面。由此产生的「数值相同但字面不同可共存」是用户裁定的预期行为，不是缺陷。
- 分配**不提供回收工作流**：释放唯一途径是既有 F005 对 IPAddress 的逻辑删除（R-DELETE-006）。
- **同步项**：`requirements.md` §12 R-IP-005~010 + 变更记录（已同步）；`domain-model.md` / `domain-model.yaml` 补充分配说明（不新增领域对象）；`project-plan.yaml` F021.requirements 挂 R-IP-005~010。
- 新建 `docs/api/f021-ip-address-allocation.md` 与 `docs/architecture/f021-*.md`（Architecture 职责）。

---

## Handoff Status

`READY FOR ARCHITECT`