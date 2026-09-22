# F021 API 契约 — IP 地址自动 / 手动分配

> Status: **READY**
> Feature: F021（E02，P1，`depends_on: [F020, F005, F004, F002]` = DONE）
> Author Role: architect
> Source: `docs/product/handoffs/f021-ip-address-allocation.md`（`READY FOR ARCHITECT`）；`requirements.md` §12 **R-IP-005 ~ R-IP-010**（R-IP-001 ~ R-IP-004 不变）；`domain-model.md` §5.7 / §8 / §9；用户 2026-09-20 DEC-023 第 7~13 项裁定与 2026-09-21 PR-01 裁定；`docs/architecture/f021-ip-address-allocation-handoff.md`（`READY FOR IMPLEMENTATION`）；`docs/api/api-conventions.md`；`docs/api/f005-ip-address.md`；`docs/api/f020-ip-address-range.md`；`docs/api/f014-soft-delete.md`；ADR-0002 / 0003 / 0004 / 0005
> **F023 增量修订（2026-09-22）**：依 `requirements.md` §12 修订后的 **R-IP-006 / R-IP-009**（DEC-025 裁定），自动分配请求新增**必填**字段 `ip_address_range_id`；自动分配语义由「目标 Cluster **全部活跃范围段并集**取全局最小」改为「**必须显式指定一个活跃范围段**，**仅在该所选单个范围段内**取数值最小未占用 IPv4；所选范围段耗尽 → `409 NO_AVAILABLE_IP` 且**不回退**」。本修订**不改变** `POST /api/ip-addresses/allocate-manual`、F005 `POST /api/ip-addresses`、R-IP-001 ~ R-IP-005 / R-IP-007 / R-IP-008 / R-IP-010。Status 维持 **READY**。
> 本文件是 F021 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **IP 分配 API**，共 **2 个端点**（§3）。
2. 通用约定（`/api` 前缀、`snake_case`、字段类型、错误信封、状态码、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件不重复定义。
3. **分配不是独立领域对象**：分配（自动或手动）的唯一产物是创建一条**现有 IPAddress**（沿用 `docs/api/f005-ip-address.md`），**不新建**分配 / 预留实体、表、列、状态或独立资源（R-IP-005）。
4. 每次分配**必须恰指定一个活跃 NetworkInterface**；不存在无 NIC 的分配；不接受以 BareMetal / VirtualMachine / Container / Cluster / Service 为父，也不提供载体类型选择器。
5. IPAddress 的 Cluster 归属由 `NetworkInterface → BareMetal → Cluster` **受控推导**（复用 F005 既有推导）；**请求与响应均不含 `cluster_id`**。
6. **自动分配必须显式指定范围段**：请求**必须**携带 `ip_address_range_id`（integer，**必填**，指向 F020 的一个 IP 地址范围段）；**不存在**「未指定范围段也成功」的路径，也**不再**存在「目标 Cluster **全部活跃范围段并集取全局最小**」的隐式行为（该隐式行为已由用户 2026-09-22 `DEC-025` 裁定废止）。该字段是请求 schema 封闭集合的成员；`cluster_id` / `status` / `mode` / `reserved_addresses` 等任何未识别字段仍被拒绝（→ `400`）。
7. **自动分配仅在所选单个活跃范围段内取最小**：所选范围段必须**活跃**（未逻辑删除）且**恰属于**目标 NIC 推导出的 Cluster；分配**仅在所选该范围段内**取**数值最小的未占用 IPv4**；所选范围段耗尽则**硬失败、不回退**（§4.1），不跨范围段、不跨 Cluster 取址；**无隐式保留地址**（不自动跳过网络地址 / 广播地址 / 网关 / 范围端点）。所选范围段的归属 / 活跃性校验细节见 §3.1。
8. **手动分配**要求输入同时满足：合法 IPv4（否则不允许输入，拒绝且不创建记录）、其**数值**落在该 Cluster 某个活跃范围内、且**未被占用**；合法但非规范的输入先**规范化**为 canonical dotted-quad 再写入。手动分配**不受 `ip_address_range_id` 影响**，且**不走**范围段选择。
9. **已占用判定**：目标 Cluster 内存在**活跃（未逻辑删除）**且 `ip_address` **字面相同**的 IPAddress 即为占用；软删释放；**无隐式保留地址**。
10. **比较边界（不得混用）**：范围归属 / 合法性按 IPv4 **数值**；占用 / 唯一性按 `ip_address` **字面**。
11. **不新增**超出 R-IP-001 的唯一性约束；`ux_ip_addresses_cluster_ip_active`（predicate `deleted_at IS NULL`）为唯一性**最终权威**。
12. **V1 仅 IPv4**；不接受 CIDR 表示与 IPv6。
13. 本契约**不替换、不改版** F005 的 `POST /api/ip-addresses`：**范围外**的任意字面 IP 仍按 F005 既有端点登记（R-IP-008），不受本契约范围约束拦截；本契约的「拒绝非法 IPv4」**仅作用于分配路径**。
14. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无角色 / 权限 / RBAC**（ADR-0005）。
15. **不提供**分配回收工作流：释放唯一途径是对该 IPAddress 执行 `DELETE /api/ip-addresses/{ip_address_id}`（R-DELETE-006）。
16. 本契约**取代** `docs/api/f005-ip-address.md` §10 中「IP 分配与回收工作流」与「自动生成 IP」两处非目标立场（仅该两处；F005 的 `ip_address` 自由文本登记立场不变）。

---

## 2. 分配结果资源表示

分配成功返回的单个对象，**复用 F005 的 IPAddress 表示**，结构**恰为**：

```json
{
  "id": 41,
  "network_interface_id": 12,
  "ip_address": "10.0.0.5",
  "created_at": "2026-09-21T10:00:00Z",
  "updated_at": "2026-09-21T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 新创建的 IPAddress 代理主键（ADR-0003） |
| `network_interface_id` | integer | 否 | 目标 NIC 的 `id`（回显请求值；N:1 Mandatory） |
| `ip_address` | string | 否 | **规范化 canonical dotted-quad**（自动 = 选中的最小未占用地址；手动 = 输入规范化后的地址）。分配路径下**有格式承诺**（§7） |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间 |

**该字段集合是封闭的**：不存在 `cluster_id`（受控推导的内部值，不对外暴露）、`status`、`deleted_at`、分配对象 / 分配时间 / 回收状态、保留地址开关、CIDR / 前缀长度等任何字段。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递。

---

## 3. 端点

### 3.1 `POST /api/ip-addresses/allocate` — 自动分配

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/ip-addresses/allocate` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**

```json
{ "network_interface_id": 12, "ip_address_range_id": 7 }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `network_interface_id` | integer | **是** | 否 | 目标 NIC 的 `id`；必须存在且活跃，且其宿主 BareMetal 活跃 |
| `ip_address_range_id` | integer | **是** | 否 | 所选 IP 地址范围段的 `id`（F020 资源）；必须存在、**活跃**、且**恰属于**目标 NIC 推导出的 Cluster |

- 请求 schema **封闭**（`extra="forbid"`）。接受字段**恰为** `{network_interface_id, ip_address_range_id}`；**不接受** `cluster_id`、`status`、`deleted_at`、`ip_address`、`mode`、`reserved_addresses` 或任何其它未识别字段（→ `400 VALIDATION_ERROR`，`details[].field` = 该字段名）。
- 缺少 / 非整数 / `null` 的 `ip_address_range_id` → `400 VALIDATION_ERROR`，`details[].field = "ip_address_range_id"`，**不产生任何记录**。

**语义**

- 校验顺序（**稳定、可测试，且任何拒绝均发生在写入之前**）：
  1. 请求字段形状（缺字段 / 类型 / 未识别字段）→ `400`；
  2. `derive_cluster_id` 从目标 NIC 受控推导 Cluster；NIC 不存在 / 已逻辑删除 / 宿主不活跃 → `404 NOT_FOUND`（`details == []`）；
  3. 读取 `ip_address_range_id` 指向的**活跃**范围段：不存在或已逻辑删除 → `404 NOT_FOUND` + `details[].code = "IP_ADDRESS_RANGE_UNAVAILABLE"`；活跃但其 `cluster_id` 不等于推导出的 Cluster（跨 Cluster）→ `409 CONFLICT` + `details[].code = "IP_ADDRESS_RANGE_UNAVAILABLE"`（见 §4.6）；
  4. 读取目标 Cluster 内活跃占用字面集合，**仅在所选该范围段** `[start_ip, end_ip]` 内取**数值最小**的、其 `format_ipv4(v)` 不在占用字面集合中的 `v`；若该范围段内无可用值 → **耗尽**（§4.1）；
  5. 经 F005 的**单一受控写入路径**（`create_ip_address`）写入规范化 dotted-quad；并发落败方由 `ux_ip_addresses_cluster_ip_active` 裁决（§4.3）。
- 「未占用」按 §7.2：同 Cluster 活跃且 `ip_address` 字面相同者判为占用；候选写为 canonical dotted-quad 后按字面比较。
- **不跳过**网络地址 / 广播地址 / 网关 / 范围端点。
- 所选范围段内全部 IPv4 均被占用 → **耗尽**（§4.1），**不回退**到其它范围段、**不跨 Cluster 取址**，**不创建任何 IPAddress**。
- 目标 Cluster 无任何活跃范围段时，调用方**无法**给出有效的 `ip_address_range_id`；前端不提交（见前端约定），服务端仍**独立**校验：请求缺失该字段 → `400`；引用不存在 / 已删范围段 → `404`。自动分配**不存在**「无活跃范围段也成功」的路径。

**Response 201**：§2 的单对象结构（**不新增任何字段**；不回显 `ip_address_range_id` / `cluster_id` / `status`）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| 缺少 `network_interface_id` / 非整数 / `null` | `400` | `VALIDATION_ERROR` | `field == "network_interface_id"` |
| 缺少 `ip_address_range_id` / 非整数 / `null` | `400` | `VALIDATION_ERROR` | `field == "ip_address_range_id"` |
| 未识别字段（含 `cluster_id` / `status` / `ip_address` / `mode`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| `network_interface_id` 引用**不存在**或**已逻辑删除**的 NIC（或其宿主 BareMetal 不活跃） | `404` | `NOT_FOUND` | `[]` |
| `ip_address_range_id` 引用**不存在**或**已逻辑删除**的范围段 | `404` | `NOT_FOUND` | `[{ "field": "ip_address_range_id", "code": "IP_ADDRESS_RANGE_UNAVAILABLE", ... }]` |
| `ip_address_range_id` 引用**活跃但属于其它 Cluster** 的范围段 | `409` | `CONFLICT` | `[{ "field": "ip_address_range_id", "code": "IP_ADDRESS_RANGE_UNAVAILABLE", ... }]` |
| 所选范围段内无可用 IPv4（耗尽） | `409` | `CONFLICT` | `[{ "field": null, "code": "NO_AVAILABLE_IP", ... }]` |
| 并发选中同一地址的落败方 | `409` | `CONFLICT` | `[{ "field": "ip_address", "code": "DUPLICATE", ... }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- 自动分配**不自动重试**：并发落败方以既有 `409 CONFLICT + DUPLICATE` 返回（§4.3），**永不 5xx**。
- **`POST /api/ip-addresses/allocate-manual`（§3.2）与 F005 `POST /api/ip-addresses` 的行为完全不变**：前者不受 `ip_address_range_id` 影响、不走范围段选择；后者保持 `ip_address` 自由文本登记立场。

---

### 3.2 `POST /api/ip-addresses/allocate-manual` — 手动分配

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/ip-addresses/allocate-manual` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**

```json
{ "network_interface_id": 12, "ip_address": "10.0.0.5" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `network_interface_id` | integer | **是** | 否 | 目标 NIC 的 `id`；必须存在且活跃，且其宿主 BareMetal 活跃 |
| `ip_address` | string | **是** | 否 | 合法 IPv4（dotted-quad，允许前导零）；其数值须落在该 Cluster 某活跃范围内且未占用。非法格式 → `400` |

- 请求 schema **封闭**（`extra="forbid"`）。**不接受** `cluster_id`、`status`、`deleted_at`、`mode`、`reserved_addresses` 或任何其它未识别字段（→ `400`）。

**语义**

- 校验顺序（稳定，可测试）：① 请求字段形状（缺字段 / 类型 / 未识别字段、`ip_address` 非法 IPv4）→ `400`；② 目标 NIC 活跃性与 Cluster 推导 → `404`；③ 范围归属（按数值）→ `409 OUT_OF_RANGE`；④ 占用判定（按规范化后字面）→ `409 DUPLICATE`；⑤ 写入。
- **规范化（PR-01 A）**：合法但非规范的输入（如 `010.0.0.5`）先规范化为 canonical dotted-quad（`10.0.0.5`）再写入；响应 `ip_address` 为规范化值。
- 占用判定使用**规范化后的字面**（R-IP-008）：「范围外」与「已占用」是不同的稳定判别值。

**Response 201**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| 缺少 `network_interface_id` / 非整数 / `null` | `400` | `VALIDATION_ERROR` | `field == "network_interface_id"` |
| 缺少 `ip_address` / 非字符串 / `null` | `400` | `VALIDATION_ERROR` | `field == "ip_address"` |
| `ip_address` 非法 IPv4（`10.0.0.256`、`10.0.0`、`abc`、`1.2.3.4/24`、`2001:db8::1`、空串、含空白等） | `400` | `VALIDATION_ERROR` | `field == "ip_address"`，`code == "INVALID"` |
| 未识别字段（含 `cluster_id` / `status` / `mode`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| NIC 引用**不存在**或**已逻辑删除**（或其宿主 BareMetal 不活跃） | `404` | `NOT_FOUND` | `[]` |
| 合法 IPv4，但其数值**不落在**该 Cluster 任何活跃范围内 | `409` | `CONFLICT` | `[{ "field": "ip_address", "code": "OUT_OF_RANGE", ... }]` |
| 落在范围内，但同 Cluster 已被活跃且**字面相同**的 IPAddress 占用 | `409` | `CONFLICT` | `[{ "field": "ip_address", "code": "DUPLICATE", ... }]` |
| 并发写入同一地址的落败方 | `409` | `CONFLICT` | `[{ "field": "ip_address", "code": "DUPLICATE", ... }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- 范围外请求**不**经 F005 登记端点；如确需登记范围外字面值，调用 F005 `POST /api/ip-addresses`（不受本契约拦截）。

---

## 4. 错误信封与稳定判别值

本契约复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 的实现，不另立一套。

### 4.1 `409 CONFLICT` — 所选范围段耗尽（自动分配）

```json
{ "error": { "code": "CONFLICT", "message": "所选地址范围段已无可用 IP",
  "details": [ { "row": null, "field": null, "code": "NO_AVAILABLE_IP",
    "message": "所选活跃 IP 地址范围段内已无未被占用的 IPv4" } ] } }
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定** |
| `details[].code` | `"NO_AVAILABLE_IP"` | **稳定**：机器可读判别值 |
| `details[].field` / `row` | `null` | 不构成契约 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约** |

- 耗尽判定**限定于所选单个活跃范围段**；**不回退**到其它范围段、**不跨 Cluster 取址**、**不创建任何 IPAddress**（R-IP-009 修订）。

### 4.2 `409 CONFLICT` — 手动分配范围外

```json
{ "error": { "code": "CONFLICT", "message": "地址不在任何活跃范围内",
  "details": [ { "row": null, "field": "ip_address", "code": "OUT_OF_RANGE",
    "message": "该地址不落在目标 Cluster 的任何活跃 IP 地址范围段内" } ] } }
```

`details[].code = "OUT_OF_RANGE"` 为**稳定**判别值。

### 4.3 `409 CONFLICT` — 地址已占用 / 并发落败

```json
{ "error": { "code": "CONFLICT", "message": "IP 地址已存在",
  "details": [ { "row": null, "field": "ip_address", "code": "DUPLICATE",
    "message": "同一 Cluster 内已存在活跃的相同 IP 地址" } ] } }
```

- `details[].code = "DUPLICATE"` 是 F005 既有**稳定**判别值，本契约沿用，不新增。
- 该分支同时覆盖「手动分配命中已有活跃字面」与「自动 / 手动并发落败」。

### 4.4 `400 VALIDATION_ERROR`

- 缺字段 / 非整数 / `null` / 未识别字段（含 `cluster_id` / `status`）：`details[].field` = 相应字段名，`details[].code = "INVALID"`。
- `ip_address` 非法 IPv4：`details[].field = "ip_address"`，`details[].code = "INVALID"`。

### 4.5 其他

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 目标 NIC 不存在 / 已删 / 宿主不活跃 | `404` | `NOT_FOUND` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

### 4.6 所选范围段不可用（自动分配）

```json
{ "error": { "code": "CONFLICT", "message": "所选地址范围段不可用于该集群",
  "details": [ { "row": null, "field": "ip_address_range_id",
    "code": "IP_ADDRESS_RANGE_UNAVAILABLE",
    "message": "所选范围段不存在、已逻辑删除，或不属于目标 Cluster" } ] } }
```

| 情形 | HTTP | `error.code` | `details[].code` | `details[].field` |
|---|---|---|---|---|
| `ip_address_range_id` 引用**不存在**的范围段 | `404` | `NOT_FOUND` | `IP_ADDRESS_RANGE_UNAVAILABLE` | `"ip_address_range_id"` |
| `ip_address_range_id` 引用**已逻辑删除**的范围段 | `404` | `NOT_FOUND` | `IP_ADDRESS_RANGE_UNAVAILABLE` | `"ip_address_range_id"` |
| `ip_address_range_id` 引用**活跃但属于其它 Cluster** 的范围段 | `409` | `CONFLICT` | `IP_ADDRESS_RANGE_UNAVAILABLE` | `"ip_address_range_id"` |

- `details[].code = "IP_ADDRESS_RANGE_UNAVAILABLE"` 为**稳定**判别值；本契约的其余 409 分支（`NO_AVAILABLE_IP` / `OUT_OF_RANGE` / `DUPLICATE`）与之互不混淆。
- 「不存在」与「已逻辑删除」**不做区分**（与 F020 §3.3 对 `GET /api/ip-address-ranges/{ip_address_range_id}` 的 404 立场一致）。
- 三种情形均为**非 5xx**，且**不得产生任何写入**。
- 该分支与「目标 NIC 不存在 / 已删 / 宿主不活跃」的 `404`（`details == []`）通过 `details[].code` 区分。

> 说明：`23505` 经既有 `sqlstate.py` 通用映射 → `409 CONFLICT + DUPLICATE`；`23503` → `409 CONFLICT + REFERENCE`（产品路径不可达，因 `derive_cluster_id` 预检先给出 `404`）。本契约**不新增** SQLSTATE 映射。

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

---

## 5. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（ADR-0005）。
- 认证成功即可执行分配；**不需要**任何角色 / 权限（V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点均位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 6. 并发与一致性语义

### 6.1 自动分配路径（同一请求事务内）

1. `derive_cluster_id` 从目标 NIC 推导 Cluster 归属；对**父 NIC 行**取共享锁（`FOR SHARE OF network_interfaces`）并确认 NIC 与其宿主 BareMetal 均活跃；未命中 → `404 NOT_FOUND`（复用 F005 §6.1 锁语义）。
2. 读取 `ip_address_range_id` 指向的**活跃**范围段（`deleted_at IS NULL`）：不存在 / 已逻辑删除 → `404 NOT_FOUND + IP_ADDRESS_RANGE_UNAVAILABLE`；活跃但 `cluster_id ≠ 推导值` → `409 CONFLICT + IP_ADDRESS_RANGE_UNAVAILABLE`（两种情形均在任何写入之前）。**仅**读取**所选该单个**范围段；不读取其它范围段。
3. 读取该 Cluster 的**活跃占用字面**（`deleted_at IS NULL` 的 `ip_address` 集合）。
4. 在**所选范围段**的 `[start_ip, end_ip]` 上取第一个满足 `format_ipv4(v) ∉ 占用字面集合` 的数值 `v`；无 → `409 NO_AVAILABLE_IP`（在任何写入之前）。**不**在其它范围段回退。
5. 经 F005 `create_ip_address` 写入（内部再次推导 `cluster_id` 并执行唯一性预检）；`ux_ip_addresses_cluster_ip_active` 为**最终权威**；冲突 `23505` → `409 DUPLICATE`。

### 6.2 手动分配路径（同一请求事务内）

1. 严格解析 `ip_address` 为 IPv4 数值；非法 → `400`。
2. `derive_cluster_id`（同上）；未命中 → `404`。
3. 数值落于任一活跃范围段 `[start_ip, end_ip]` 内；否则 `409 OUT_OF_RANGE`。
4. 规范化后字面判占用；命中 → `409 DUPLICATE`。
5. 经 F005 `create_ip_address` 写入（同上，最终权威为 partial unique）。

### 6.3 单一写入路径与锁序

- 分配**不直接写** `ip_addresses`；`cluster_id` 仍只由 `derive_cluster_id` 推导、只经 `IpAddressRepository.create` 写入。**不存在第二处写 `cluster_id` 的路径**（R-IP-010）。
- 锁序与 F005 一致：**父 NIC 行 `FOR SHARE` → 插入 `ip_addresses` 行**；分配不锁定 `ip_address_ranges` / Cluster 行，不新增反向持锁，**不新增死锁序**。
- 分配**不新增**任何锁、唯一索引、第二维度列或触发器；不引入 R-IP-001 之外的新约束（R-IP-010）。

### 6.4 并发结果（不变式）

- 并发分配（自动 / 手动 / 与 F005 登记）选中**同一地址**时：**至多一条成功**（`201`）；其余以既有 `409 CONFLICT + DUPLICATE` 返回，**永不 5xx**；结束后同 Cluster 该字面**活跃行 ≤ 1**。
- 「分配」与「删除其父 NIC」并发时恰有一个成功；结束后下方不变式恒成立：

  ```sql
  SELECT count(*) FROM ip_addresses ip
  JOIN network_interfaces nic ON nic.id = ip.network_interface_id
  WHERE ip.deleted_at IS NULL AND nic.deleted_at IS NOT NULL;   -- 必须为 0
  ```

- **`cluster_id` 一致性**恒为 0 行：

  ```sql
  SELECT ip.id FROM ip_addresses ip
  JOIN network_interfaces nic ON nic.id = ip.network_interface_id
  JOIN bare_metals        bm  ON bm.id  = nic.bare_metal_id
  WHERE ip.cluster_id <> bm.cluster_id;   -- 期望 0 行
  ```

### 6.5 已知并发窗口（记录，不消除）

- 自动分配的「耗尽」判定基于一次读快照：若在读后并发软删了**所选范围段内**某条占用，本次可能瞬时返回 `NO_AVAILABLE_IP`。此为可重试的瞬态，不违反任何产品规则，**不引入额外锁消除**（R-IP-010 禁止新约束）。
- 分配与范围段删除**不互相串行**（沿用 F020 §6.4 的既定立场，DEC-023 第 6 项）：极端并发下可能出现「活跃 IP 存在、其覆盖范围已被软删」，或「所选范围段在校验后被并发软删、本轮仍写入成功」。本契约**不承诺**「每个活跃 IP 必被某活跃范围覆盖」，也不承诺范围段活跃性与写入原子串行；仅由回归查询检测。

---

## 7. IPv4 解析、规范化与比较边界

### 7.1 分配输入（有承诺）

- `ip_address`（手动）必须是合法 IPv4：恰好 4 个以 `.` 分隔的十进制段，每段 1~3 位、值 `0..255`；**允许前导零**；**不接受**前缀长度（`/n`）、IPv6、空白、空串、非数字字符。
- 规范化形式 = canonical dotted-quad（无前导零、无前缀长度）：`010.000.000.005` → `10.0.0.5`。
- 自动分配选中的地址以 canonical dotted-quad 写入。
- 示例（`400`）：`10.0.0.256`、`10.0.0`、`abc`、`1.2.3.4/24`、`2001:db8::1`、空串、含前后空白。

### 7.2 已占用判定（字面）

- 在目标 Cluster 内，只要存在**活跃**且 `ip_address` **字面相同**（区分大小写、不 trim、不归一化、不大小写折叠）的 IPAddress，该字面值即判为已占用；软删释放。
- 范围归属按 IPv4 **数值**，占用 / 唯一性按 `ip_address` **字面**；二者**不得混用**。

### 7.3 与 F005 登记的关系

- 本契约**不改变** `ip_addresses.ip_address` 的自由文本登记立场（F005 §7 不变）；§7.1 的格式承诺**仅适用于分配路径**。
- **范围外**字面 IP 仍走 F005 `POST /api/ip-addresses` 登记，不受本契约拦截、也不因本契约而收紧。

---

## 8. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `201` | 分配成功（自动 / 手动） | — |
| `400` | 请求字段校验失败（缺字段 / 类型 / 非法 IPv4 / 未识别字段含 `cluster_id` / 缺 `ip_address_range_id`） | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | 目标 NIC 不存在 / 已删 / 宿主不活跃 | `NOT_FOUND`（`details == []`） |
| `404` | 自动：所选范围段不存在 / 已逻辑删除 | `NOT_FOUND`（`details[].code = "IP_ADDRESS_RANGE_UNAVAILABLE"`） |
| `409` | 自动：所选范围段属于其它 Cluster | `CONFLICT`（`details[].code = "IP_ADDRESS_RANGE_UNAVAILABLE"`） |
| `409` | 自动：所选范围段耗尽 | `CONFLICT`（`details[].code = "NO_AVAILABLE_IP"`） |
| `409` | 手动分配范围外 | `CONFLICT`（`details[].code = "OUT_OF_RANGE"`） |
| `409` | 已占用 / 并发落败 | `CONFLICT`（`details[].code = "DUPLICATE"`） |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**；前端必须按 `error.code`（必要时结合 `details[].code`）分支，不解析 `message`。

---

## 9. Not Found / Empty 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| 目标 NIC 不存在 / 已逻辑删除 / 宿主不活跃 | `404 NOT_FOUND`（`details == []`） |
| 自动分配：所选范围段不存在 / 已逻辑删除 | `404 NOT_FOUND` + `IP_ADDRESS_RANGE_UNAVAILABLE` |
| 自动分配：所选范围段属于其它 Cluster | `409 CONFLICT` + `IP_ADDRESS_RANGE_UNAVAILABLE` |
| 自动分配：所选范围段内全部占用 | `409 CONFLICT` + `NO_AVAILABLE_IP`（**非** Empty；分配动作不产生集合语义） |
| 手动分配：合法但范围外 | `409 CONFLICT` + `OUT_OF_RANGE` |

> 本契约**不提供列表端点**，故无 Empty 集合语义；`GET /api/ip-addresses` 的 Empty / Not Found 语义仍由 F005 契约定义，不在本契约范围内。
> 「目标 Cluster 无任何活跃范围段」不再是自动分配的一种独立响应：请求缺少 `ip_address_range_id` → `400`；引用不存在 / 已删范围段 → `404`（见 §3.1 / §4.6）。

---

## 10. 明确不在本契约中（非目标）

- IPAddress 的登记 / 列表 / 读取 / 修正 / 删除（权威正文 `docs/api/f005-ip-address.md`）；`POST /api/ip-addresses` 的 `ip_address` 自由文本立场**不变**。
- 范围段（地址池）的 CRUD（权威正文 `docs/api/f020-ip-address-range.md`）。
- **分配实体 / 预留实体 / 分配表 / 分配字段 / 分配状态**（R-IP-005；不得引入）。
- **回收 / 解绑 / 分配历史 / 审计 / 操作人**：释放唯一途径为 F005 `DELETE /api/ip-addresses/{ip_address_id}`（R-DELETE-006）。
- **CIDR 表示**、**IPv6**、网络地址 / 广播地址 / 网关等**保留地址跳过**与保留地址开关（R-IP-006）。
- **新增唯一性约束 / VRF / 网络命名空间 / 租户维度**（R-IP-010 / R-IP-003）。
- **批量分配 / 使用率统计 / 冲突扫描 / 导出 / 容量预警**。
- **DHCP / DNS / 自动资产发现 / 外部平台同步**；受 Cluster 活跃范围约束的自动分配**不属**此类（§1.16）。
- 分配对象 / 原因 / 备注 / 分配时间 / 回收状态等未确认字段。
- `by-name` 别名、分配状态查询 / 排序 / 第二维度查询参数。
- API versioning、游标分页（无需求）。