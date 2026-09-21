# F005 API 契约 — IPAddress 登记与管理

> Status: **READY**
> Feature: F005（E02，P1，`depends_on: [F004]` = DONE）
> Author Role: architect
> Source: `docs/api/api-conventions.md`（`READY`）、ADR-0002 / 0003 / 0004 / 0005（均 `ACCEPTED`）、`docs/architecture/f005-ip-address-handoff.md`（`READY FOR IMPLEMENTATION`）、`docs/api/f002-bare-metal.md`、`docs/api/f004-network-interface.md`、`docs/api/f006-virtual-machine.md`、`docs/api/f014-soft-delete.md`、`docs/product/handoffs/f005-ip-address.md`、`docs/database/csm-v1-schema-design.md`
> 本文件是 F005 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **IPAddress 资源**的产品 API，共 **5 个端点**（§3）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty / Not Found 语义、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件不重复定义。
3. IPAddress **必属恰好一个 NetworkInterface**（N:1 Mandatory；用户 2026-09-15 明确裁定，`domain-model.yaml` `binding_state: CONFIRMED` / `confirmed_by: user`）。**不存在无主 IP**、不接受以 BareMetal / VM / Container / Cluster / Service 为父、不提供载体类型选择器。
4. IPAddress 的**登记字段只有 `ip_address`**（`domain-model.md` §5.7；必填、标识字段）。V1 **不设状态**（Q-002=B）。
5. IPAddress 的 **Cluster 归属是推导值**：由领域服务从 `network_interface_id` 沿 `NIC → BareMetal → Cluster` 推导后写入 `ip_addresses.cluster_id`。**调用方永远无法指定或修改该归属**（§2 / §3.1 / §3.4）。
6. **唯一性边界是 Cluster**：同一 Cluster 内活跃 IP 必须**字面唯一**；**不同 Cluster 之间允许相同字面值**（R-IP-001 / R-IP-002）；比较**区分大小写、字面精确**（§22）。已逻辑删除的 IP **不再占用**该唯一性（R-DELETE-006）。
7. **V1 不考虑 VRF / 网络命名空间**（R-IP-003）：不存在 `vrf` / `vrf_id` / `tenant` / `namespace` 列、字段、查询参数、过滤或端点；同 Cluster 内**不存在任何可绕过唯一性的第二维度**。
8. `ip_address` 的长度 / 首尾空白 / 空字符串 / CIDR 前缀语义 / IPv6 十六进制大小写 / 任何格式规则均属**未定义约束**：本契约**不承诺其行为**（§7）。不实现、不承诺格式校验与归一化。
9. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无角色 / 权限 / RBAC**（ADR-0005）；任何已认证用户即可登记 / 修正 / 删除。
10. 本契约**不含**其它资源的端点与删除；不含 Cluster 视角与关联查询视图（F009 / F010，F010 **必须复用**本契约的 `?network_interface_id=` 能力）；不含 Excel 批量导入（F011，其 IP 行校验**必须复用**本契约语义，不得绕过 IP 冲突，R-IMPORT-002）。**不修改**任何既有契约正文。
11. **不提供** `by-name` 只读别名：`ip_address` 仅按 Cluster 唯一、**不是全局唯一**（ADR-0003 §2 只为全局唯一名称授予别名）。
12. **不提供**父绑定变更（NQ-2 未确认，默认不可变）与 `cluster_id` 的任何读写入口（NQ-4 见 §2）。

---

## 2. IPAddress 资源表示

所有返回单个 IPAddress 的端点（§3.1、§3.3、§3.4）使用**同一个对象结构**：

```json
{
  "id": 41,
  "network_interface_id": 12,
  "ip_address": "10.0.1.1/16",
  "created_at": "2026-09-18T10:00:00Z",
  "updated_at": "2026-09-18T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）。写操作一律使用该值 |
| `network_interface_id` | integer | 否 | 直接父 NetworkInterface 的 `id`（N:1 Mandatory，恰好一个父）；**登记后不可变** |
| `ip_address` | string | 否 | IP 地址**字面值**（示例 `10.0.1.1/16`）；**原样存取**，不做 trim / 归一化 / 大小写折叠；在同 Cluster 活跃范围内字面唯一；**无格式承诺**（§7） |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间（应用层维护；不是并发控制依据） |

**该字段集合是封闭的**：

- 不存在 `deleted_at`（不对外暴露）；
- **不存在 `cluster_id`**（Architecture 裁定 NQ-4：Cluster 归属是**内部一致性关键的反规范化推导值**，不是登记事实；其正确性由「唯一受控写入路径 + 漂移检测 0 行」保证，不通过 API 表示，也不由调用方提供）；
- 不存在 `status`、状态枚举或任何状态字段（Q-002=B）；
- 不存在 `vrf` / `vrf_id` / `tenant` / `namespace` / `netns` 等第二维度字段（R-IP-003）；
- 不存在 IP 池 / 网段 / 子网 / 网关 / VLAN / DHCP / DNS / 自动发现 / 外部平台 id / 凭据字段（**IPAddress 资源自身**不含这些字段；**范围段是独立资源**，权威正文 `docs/api/f020-ip-address-range.md`，其引入不改变本字段封闭集合）；
- 不存在 `bare_metal_id` / `virtual_machine_id` / `container_id` / `service_id` / `carrier_type` / `owner_type`（多态父载体）；
- 不存在用途 / 备注 / 负责人 / 分配对象 / 回收状态 / 分配时间等未确认字段。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递。

**Cluster 归属的可达方式（只读、不新增端点）**：需要展示 IP 的 Cluster 归属时，调用方沿既有关联读取：`network_interface_id` → `GET /api/network-interfaces/{network_interface_id}` 的 `bare_metal_id` → `GET /api/bare-metals/{bare_metal_id}` 的 `cluster_id`。聚合呈现归 F010。

---

## 3. 端点

### 3.1 `POST /api/ip-addresses` — 登记 IPAddress

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/ip-addresses` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**

```json
{ "network_interface_id": 12, "ip_address": "10.0.1.1/16" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `network_interface_id` | integer | **是** | 否 | 直接父 NIC 的 `id`；必须存在且活跃，且其宿主 BareMetal 活跃 |
| `ip_address` | string | **是** | 否 | 字面值；**不校验长度 / trim / 空串 / 空白 / 格式 / CIDR / 归一化**（§7）；唯一性由服务端裁决 |

- 请求 schema **封闭**（`extra="forbid"`）。**不接受** `cluster_id`、`status`、`vrf` / `namespace`、`pool_id`、载体类型选择器、多父字段，或任何其它未识别字段（→ `400`）。
- **`cluster_id` 永不被接受**：不存在任何产品路径允许调用方指定 IP 的 Cluster 归属；若请求体携带该字段（或任何 VRF / Cluster 选择字段）→ `400 VALIDATION_ERROR`，不产生记录。

**Response 201**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| 缺少 `ip_address`（含 `{}`）/ 非字符串 / `null` | `400` | `VALIDATION_ERROR` | `field == "ip_address"` |
| 缺少 `network_interface_id` / 非整数 | `400` | `VALIDATION_ERROR` | `field == "network_interface_id"` |
| `network_interface_id` 引用**不存在或已逻辑删除**的 NIC（或其宿主 BareMetal 不活跃） | `404` | `NOT_FOUND` | `[]` |
| 目标 Cluster 内已存在**活跃**且**字面相同**的 `ip_address` | `409` | `CONFLICT` | `[{ "field": "ip_address", "code": "DUPLICATE", … }]` |
| 未识别字段 / `cluster_id` / `status` / `vrf` / 载体选择器 | `400` | `VALIDATION_ERROR` | 该字段名 |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- **引用不存在 / 已删父返回 `404 NOT_FOUND`**（NQ-7 裁定，与 F002 / F004 / F006 一致）：由同一事务内「对父 NIC 行取 `FOR SHARE` 并确认 NIC 与其宿主 BareMetal 均活跃」给出，**非 5xx**。
- 若同名（字面相同）IP 属于**已逻辑删除**的行，本次登记**成功**（`201`，R-DELETE-006）。
- 字面**不同**的字符串（含 IPv6 十六进制大小写不同的写法，如 `2001:DB8::1` 与 `2001:db8::1`）可共存（§22；无 `lower()` 折叠、无 collation 变更）。

**并发语义**：登记对父 NIC 行取共享锁，并在同一事务内推导 `cluster_id`；与父 NIC 逻辑删除并发时，二者恰有一个成功（§6）。

---

### 3.2 `GET /api/ip-addresses` — 列出活跃 IPAddress

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/ip-addresses` |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50）、`network_interface_id`（integer，可选） |
| 认证 | **必需**（§5） |

**语义**

- 未提供 `network_interface_id`：返回系统中全部活跃 IPAddress。
- 提供 `network_interface_id`：**按父 NIC 限定**返回该 NIC 的活跃 IPAddress（R-QUERY-004 的 F005 侧 canonical 能力；**供 F010 复用**，F010 不得另写一份过滤）。父 NIC **不存在或已逻辑删除** → `404 NOT_FOUND`；父 NIC **存在但无活跃 IPAddress** → `200` + `items == []`（**Empty**）。
- 已逻辑删除的 IPAddress **不出现**在 `items`，也不计入 `total`。
- **不存在** `cluster_id` / `vrf` / `status` / IP 前缀 / 排序等第二维度查询参数；本契约不定义此类参数，前端与调用方**不得构造**（Cluster 视角归 F009；**Cluster 内关键字搜索归 F018**，其权威正文为 `docs/api/f018-cluster-keyword-search.md`，由 F018 的独立只读端点提供，**不通过本端点提供**）。

**Response 200**

```json
{ "items": [ { "id": 41, "network_interface_id": 12, "ip_address": "10.0.1.1/16",
  "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z" } ],
  "total": 1, "page": 1, "page_size": 50 }
```

- `items`：按 `id` 升序。
- `total`：**活跃** IPAddress 总数（受 `network_interface_id` 过滤时为该过滤域内的活跃数）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| `network_interface_id` 非整数 | `400` | `VALIDATION_ERROR` | `"network_interface_id"` |
| `network_interface_id` 引用不存在 / 已逻辑删除的 NIC | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Empty / Not Found 语义**：

| 情形 | 响应 |
|---|---|
| 无活跃 IPAddress（未给 `network_interface_id`） | `200`，`items == []`，`total == 0`（**Empty**） |
| `network_interface_id` 存在但无活跃 IPAddress | `200`，`items == []`（**Empty**） |
| `network_interface_id` 不存在或已逻辑删除 | `404 NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

### 3.3 `GET /api/ip-addresses/{ip_address_id}` — 按 id 读取

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/ip-addresses/{ip_address_id}` |
| Path parameter | `ip_address_id`（integer） |
| 认证 | **必需**（§5） |

**Response 200**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `ip_address_id` 非整数 | `400` | `VALIDATION_ERROR` | `"ip_address_id"` |
| `ip_address_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：`404` 同时覆盖「不存在」与「已被逻辑删除」，两者不做区分。

---

### 3.4 `PATCH /api/ip-addresses/{ip_address_id}` — 修正 `ip_address` 字面值

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/api/ip-addresses/{ip_address_id}` |
| Path parameter | `ip_address_id`（integer） |
| 认证 | **必需**（§5） |

**Request body**（部分更新）

```json
{ "ip_address": "10.0.1.2/16" }
```

**可变字段（封闭集合）**：**恰为 `{ip_address}`**。

**不可变字段**：`id`、`network_interface_id`、`created_at`、`deleted_at`，以及 `cluster_id`（后者既不可变、**也不在契约中**）。请求体中出现任何不可变字段或未识别字段 → `400 VALIDATION_ERROR`。

**关键语义**

- 请求体**至少**需包含一个可变字段；空 body（`{}`）→ `400 VALIDATION_ERROR`。
- `ip_address` 提供时**不得为 `null`**（`null` → `400`，`details[].field == "ip_address"`）。
- 修正后**重新执行唯一性校验**：新字面值若在**目标 Cluster**（= 该行已有 `cluster_id`，等于其宿主推导值）内已被另一条活跃 IP 占用 → `409` + `details[].code == "DUPLICATE"`，**无部分写入**；若另一 Cluster 已占用而目标 Cluster 未占用 → 成功。
- 父绑定**不可变**：`network_interface_id` 与推导出的 Cluster 归属在 `PATCH` 后保持不变。
- 无乐观锁；并发更新为**最后提交生效**；`updated_at` **不是**并发控制依据。
- 本资源**无状态**（`status` 出现在请求体 → `400`）。

**Response 200**：§2 的单对象结构；`id`、`network_interface_id`、`created_at` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| 请求体含未识别 / 不可变字段（含 `id` / `deleted_at` / `network_interface_id` / `cluster_id` / `created_at` / `status` / `vrf`） | `400` | `VALIDATION_ERROR` | `field` = 该字段名 |
| 请求体无可变字段（含 `{}`） | `400` | `VALIDATION_ERROR` | 非契约 |
| `ip_address` 为 `null` / 非字符串 | `400` | `VALIDATION_ERROR` | `field == "ip_address"` |
| 目标 Cluster 内已存在活跃且字面相同的另一条 IP | `409` | `CONFLICT` | `[{ "field": "ip_address", "code": "DUPLICATE", … }]` |
| 目标不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| `ip_address_id` 非整数 | `400` | `VALIDATION_ERROR` | `field == "ip_address_id"` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- 唯一索引为**最终权威**；`23505` 经既有通用映射 → `409`（**永不 500**）。

---

### 3.5 `DELETE /api/ip-addresses/{ip_address_id}` — 逻辑删除

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/api/ip-addresses/{ip_address_id}` |
| Path parameter | `ip_address_id`（integer） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§5） |

**Response 204**

- 无响应体。
- 目标 IPAddress 的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新；该行**仍物理存在**（R-DELETE-001）。
- 删除**只修改目标行**，不级联；**父 NIC 的 `deleted_at` / `updated_at` / `name` / `technology_type` / `purpose` / `bare_metal_id` 逐字段不变**；其宿主 BareMetal 与 Cluster 的各字段同样不变（R-DELETE-005）。
- 已删 IP 不再占用同 Cluster 唯一性：同一 Cluster 内可重新登记同一字面值（R-DELETE-006）；旧已删行保留且 `deleted_at` **不被改写**（无 undelete，R-DELETE-003）。
- IPAddress 是 V1 叶子资源（无子资源），删除不被任何活跃子检查阻断。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `ip_address_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "ip_address_id", "code": "INVALID" }]` |
| 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- `404` 同时覆盖「不存在」与「已被逻辑删除」；重复删除同一 `id` 返回 `404`。
- 本端点在 V1 **不存在 `409` 触发路径**（IP 无子资源）。

**不提供的能力**：不提供 `by-name` 删除（写操作一律走 `id`）；不提供批量删除 / 条件删除 / 恢复 / 查看已删资源。

---

## 4. 错误信封

本资源复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 的实现。不另立一套。

### 4.1 `409 CONFLICT` — 同 Cluster 内活跃 `ip_address` 字面重复

```json
{ "error": { "code": "CONFLICT", "message": "IP 地址已存在",
  "details": [ { "field": "ip_address", "code": "DUPLICATE",
    "message": "同一 Cluster 内已存在活跃的相同 IP 地址" } ] } }
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定** |
| `details[].code` | `"DUPLICATE"` | **稳定**：机器可读判别值 |
| `details[].field` | `"ip_address"`（**应用层预检路径**） | 稳定 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约** |

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

> **DB 兜底路径**：绕过应用层预检直写重复活跃字面值时，数据库 `ux_ip_addresses_cluster_ip_active` 触发 `23505`，经既有通用 `sqlstate.py` 映射返回 `409 CONFLICT` + `details[].code = "DUPLICATE"`；此路径下 `details[].field` 为 best-effort 解析结果，**不构成契约**（应用路径不可达）。

### 4.2 `409 CONFLICT` — 父 NIC 存在活跃 IP（**归属 F004 契约，本契约不修改其语义**）

`DELETE /api/network-interfaces/{network_interface_id}` 在目标 NIC 存在活跃 IPAddress 时返回：

```json
{ "error": { "code": "CONFLICT", "message": "父资源存在活跃子资源，无法删除",
  "details": [ { "row": null, "field": null, "code": "ACTIVE_CHILDREN_EXIST",
    "message": "资源仍存在活跃子资源，无法删除" } ] } }
```

- 该分支的权威正文是 `docs/api/f004-network-interface.md` §3.5 / §4.1；**F005 使该分支首次可达**（`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 追加「活跃 IPAddress」检查）。
- 该 `409` **不产生任何写入**：目标 NIC 的 `deleted_at` 仍为 NULL（无部分写入）。
- 先软删该 NIC 的全部活跃 IP 后，`DELETE` NIC → `204`。

### 4.3 其他错误

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| 字段格式 / 必填 / 未识别字段 / 空 PATCH / `null` | `400` | `VALIDATION_ERROR` | `details[].field` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 目标不存在或已删；父 NIC 不存在或已删 | `404` | `NOT_FOUND` | `[]` |
| 唯一性冲突 | `409` | `CONFLICT` | `details[].code = "DUPLICATE"` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

> 补充：父 NIC 不存在 / 已删的 FK 违规（`23503`）经**既有通用** `sqlstate.py` 映射返回 `409 CONFLICT` + `details[].code = "REFERENCE"`；该路径在产品路径下**不可达**（`FOR SHARE` 预检先给出 `404`，且 NIC 无物理删除），不为本资源另立映射。

---

## 5. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（ADR-0005）。
- 认证成功即可执行全部操作；**不需要**任何角色 / 权限（V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点均位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 6. 并发与一致性语义

### 6.1 创建路径

1. `POST` 在**同一请求事务内**执行单条语句：以 `network_interface_id` 定位父 NIC 行，**取共享锁**（`FOR SHARE OF network_interfaces`），并在同一语句内读取 `bare_metals.cluster_id` 作为推导值；`WHERE` 同时要求 NIC 与其宿主 BareMetal 均 `deleted_at IS NULL`。未命中 → `404 NOT_FOUND`。
2. **不额外锁定 BareMetal / Cluster 行**：推导所依赖的 `network_interfaces.bare_metal_id` 与 `bare_metals.cluster_id` 在 V1 均**不可变**（F002 / F004 的 `PATCH` 均不含这两个字段；跨 Cluster 迁移未实现），故持有父 NIC 行共享锁已足以固定推导结果；「活跃 NIC ⇒ 活跃宿主」由宿主删除的活跃子检查（含活跃 NIC）保证。该结论在「上游列可变」能力落地时必须重开。
3. `cluster_id` 由领域服务推导后写入；**任何其它路径不得写该列**（受可失败静态 guard 约束）。
4. 唯一性**先在应用层预检**（活跃范围内 `(cluster_id, ip_address)` 字面等值）以返回友好 `409`；数据库 partial unique index `ux_ip_addresses_cluster_ip_active`（predicate `deleted_at IS NULL`）为**最终权威**（§21 / ADR-0002 §3）。

### 6.2 父资源删除

`DELETE /api/network-interfaces/{id}` 委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`），在同一事务内先锁目标行、再执行声明的活跃子资源检查（`NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`，F005 后含「活跃 IPAddress」）；命中即 `409` 且不写 `deleted_at`。

### 6.3 并发结果（不变式）

- 「登记 IPAddress」与「删除其父 NIC」并发时，二者**恰有一个**成功；结束后不存在「父 NIC 已删 + IP 活跃」的记录：

  ```sql
  SELECT count(*) FROM ip_addresses ip
  JOIN network_interfaces nic ON nic.id = ip.network_interface_id
  WHERE ip.deleted_at IS NULL AND nic.deleted_at IS NOT NULL;   -- 必须为 0
  ```

- **`cluster_id` 一致性**必须持续为 0 行（推导与存储一致）：

  ```sql
  SELECT ip.id, ip.cluster_id AS stored_cluster, bm.cluster_id AS derived_cluster
  FROM ip_addresses ip
  JOIN network_interfaces nic ON nic.id = ip.network_interface_id
  JOIN bare_metals        bm  ON bm.id  = nic.bare_metal_id
  WHERE ip.cluster_id <> bm.cluster_id;   -- 期望 0 行
  ```

  该查询是**唯一**能从数据库侧发现漂移的手段；它是 R-IP-001 的**必需**保障（若 `cluster_id` 漂移，唯一索引会在错误的 Cluster 边界上判断，导致同 Cluster 重复 IP 静默通过）。本契约**不**提供漂移查询端点；一致性由回归测试持续断言。
- 若未来允许 `bare_metals.cluster_id` 或 `network_interfaces.bare_metal_id` 变更，必须**在同一事务内**重推导受影响 IP 的 `cluster_id` 并对目标 Cluster 重校验唯一性；本 Feature **不实现、不预留**该能力。

### 6.4 删除

IPAddress 删除委托系统内**唯一**软删写入路径；不级联、不物理删除、不触碰其它行；`deleted_at` 一旦写入不再回退（R-DELETE-003）。

---

## 7. 明确不承诺的行为（`undefined_constraints`）

以下 `ip_address` 取值行为在 CSM 中**当前未定义**，**不得假设**（NQ-1 / PROPOSED-F005-3/4）：

| 事项 | 本契约的承诺 |
|---|---|
| 长度上限 / 下限 | **无承诺**。不校验、不拒绝 |
| 首尾空白是否保留 / 去除（trim） | **无承诺**。实现不做变换；**原样存取** |
| 空字符串是否允许 | **无承诺**。既不声明其合法，也不声明其非法 |
| 是否为合法 IPv4 / IPv6 字面值 | **无承诺**。**不实现格式校验**；非 IP 字面值不被本 API 拒绝 |
| CIDR 前缀（`10.0.1.1` 与 `10.0.1.1/16`）是否视为同一地址 | **无承诺**。按**字面**比较，二者是不同字面值 |
| IPv6 十六进制大小写（`2001:DB8::1` 与 `2001:db8::1`） | **不折叠**：二者是不同字面值，可共存（§22；`case_sensitive: true`） |
| Unicode NFC / NFD 归一化 | **无承诺**。实现不做归一化 |
| 是否禁止 `/` 或其他字符 | **不禁止**（`/` 禁令**仅针对 Cluster 名称** R-CLUSTER-005） |
| 唯一性比较 | **已确认**：同一 Cluster 内**字面精确、大小写敏感**；跨 Cluster 可重复；软删释放 |
| 是否支持 VRF / 网络命名空间维度 | **明确不支持**（R-IP-003）：不存在该维度字段、参数、端点；不得以任何第二维度绕过唯一性 |

**明确后果声明（是事实，不是规则）**：在现有已确认规则下，`not-an-ip`、空字符串、含首尾空白的字面值、超长字符串**不会**被本 API 拒绝，并按字面值存取与往返。这**不得**被解读为 CSM 已确认「任意字符串都是合法 IP」。若用户确认需要格式校验或归一化，属**新增产品规则**（格式校验会在保存路径引入新的拒绝；归一化会改变唯一性语义并需要数据迁移策略）。

前端与调用方**不得**基于上述任一未定义项编写业务分支，**不得**在客户端实现格式校验、trim、大小写折叠或唯一性预判。

---

## 8. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取 / 列表成功（含空列表）/ 更新成功 | — |
| `201` | 登记成功 | — |
| `204` | 删除成功（无响应体） | — |
| `400` | 请求格式或字段校验失败（含缺字段、非整数参数、`null`、未识别字段含 `cluster_id`、空 PATCH） | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | IP 不存在或已被逻辑删除；父 NIC 不存在或已删除（`POST` / `?network_interface_id=`） | `NOT_FOUND` |
| `409` | 同 Cluster 内活跃 `ip_address` 字面重复 | `CONFLICT`（`details[].code = "DUPLICATE"`） |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**；前端必须按 `error.code` 分支，不解析 `message`。

---

## 9. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `GET /api/ip-addresses`：无活跃 IPAddress | `200`，`items == []`，`total == 0`（**Empty**） |
| `GET /api/ip-addresses?network_interface_id={id}`：父 NIC 存在但无活跃 IPAddress | `200`，`items == []`（**Empty**） |
| `GET /api/ip-addresses?network_interface_id={id}`：父 NIC 不存在 / 已删 | `404` `NOT_FOUND` |
| `GET /api/ip-addresses/{id}`：不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `PATCH /api/ip-addresses/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `DELETE /api/ip-addresses/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `POST /api/ip-addresses`：引用的父 NIC 不存在 / 已删（或其宿主不活跃） | `404` `NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

## 10. 明确不在本契约中（非目标）

- Cluster / BareMetal / NetworkInterface / VirtualMachine / Container / Service 的端点与删除（权威正文：`docs/api/f001-cluster.md` / `f002-bare-metal.md` / `f004-network-interface.md` / `f006-virtual-machine.md` / `f014-soft-delete.md`）。
- Cluster 视角别名与关联查询视图（F009 / F010）；F010 **必须复用**本契约的 `?network_interface_id=` 能力，不得另写一份过滤。
- **IP 的状态**（Q-002=B）。
- **VRF / 网络命名空间 / 租户维度**（R-IP-003）。
- **`ip_address` 的格式校验与归一化**（NQ-1；§7）：不实现、不承诺。若确认，属新增产品规则 + 迁移策略。
- **`cluster_id` 的任何读写入口**：请求侧永不接受；响应侧不暴露（NQ-4 裁定）；其写入只经单一领域服务推导（内部实现，不是 API 能力）。
- **IP 地址范围段（地址池）的管理**已由独立的 F020 特征交付，权威正文为 `docs/api/f020-ip-address-range.md`；范围段是**独立资源**（独立表、独立端点），**不是** IPAddress 的字段。因此本契约**不定义、也不排除**范围段能力。本契约仍**不包含**：CIDR / 子网 / 网关 / 使用率统计 / 冲突扫描。**受 Cluster 活跃范围约束的 IP 自动 / 手动分配**已由独立的 F021 特征交付，权威正文为 `docs/api/f021-ip-address-allocation.md`；分配**不新建**分配 / 预留实体，其唯一产物是一条由本契约资源表示描述的 IPAddress，且**不替换、不改版**本契约的 `POST /api/ip-addresses`。**IP 的回收没有独立工作流**：释放唯一途径是对本契约的 IPAddress 执行 `DELETE /api/ip-addresses/{ip_address_id}`（R-DELETE-006）。`ip_address` 的**自由文本登记立场不变**：范围段与分配能力的引入**不新增**对 `ip_address` 的格式校验 / 归一化 / trim。
- DHCP / DNS / 自动资产发现 / 外部平台同步 / **不受 Cluster 活跃范围约束**的自动生成 IP（§23）；受范围约束的自动分配见上一条（F021，权威正文 `docs/api/f021-ip-address-allocation.md`）。
- **多态父载体**：不接受以 BareMetal / VM / Container / Cluster / Service 为父；不提供载体类型选择器；不存在无主 IP。
- 除 `ip_address` 与父标识外的未确认字段（用途 / 备注 / 负责人 / 分配对象 / 回收状态 / 分配时间）。
- `by-name` 别名（`ip_address` 非全局唯一；PROPOSED-F005-1）。
- 父绑定变更、`cluster_id` 变更、BareMetal 跨 Cluster 迁移的连带重推导（NQ-2 / NQ-5）。
- 物理删除、Undelete / Restore / 回收站 / 已删资源查看 / 批量删除（R-DELETE-001/003；ADR-0004）。
- Excel 批量导入（F011）；**F011 的 IP 行校验必须复用本契约的语义，不得绕过 IP 冲突**（R-IMPORT-002 / NQ-9）。
- 审计 / 历史 / 操作人 / 导出 / 高级筛选 / 排序 / 批量操作。
- API versioning、游标分页（无需求）。

GIT: NONE
