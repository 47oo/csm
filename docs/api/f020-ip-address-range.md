# F020 API 契约 — IP 地址范围段（地址池）管理

> Status: **READY**
> Feature: F020（E02，P1，`depends_on: [F001, F005]` = DONE）
> Author Role: architect
> Source: `docs/product/handoffs/f020-ip-address-range.md`（`READY FOR ARCHITECT`）；`requirements.md` §12 **R-IP-004**；`decisions_required[DEC-023].resolution`；`docs/architecture/f020-ip-address-range-handoff.md`（`READY FOR IMPLEMENTATION`）；`docs/api/api-conventions.md`；`docs/api/f005-ip-address.md`；`docs/api/f004-network-interface.md`；`docs/api/f014-soft-delete.md`；ADR-0002 / 0003 / 0004 / 0005；`docs/database/f020-ip-address-range-migration.md`
> 本文件是 F020 前后端与测试的**共同协议与单一权威**。
> **F022 纯增量修订（2026-09-21）**：依 `requirements.md` §12 修订后的 **R-IP-004**（DEC-024 裁定）新增 3 个可选元数据字段 `name` / `subnet_mask` / `vlan`（本文件 §1 / §2 / §3.1 / §3.4 / §4 / §7 / §8 / §10 相应修订）。本修订**不推翻** F020 既有结论（重叠 / 软删 / 删除守卫 / 无状态 / IPv4 规范化逐条不变），也不改变 F021 分配语义（分配不按掩码 / VLAN 过滤）。Status 维持 **READY**。

---

## 1. 范围与前提

1. 本契约定义 **IPAddressRange 资源**的产品 API，共 **5 个端点**（§3）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty / Not Found 语义、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件不重复定义。
3. IPAddressRange **恰属一个活跃 Cluster**（`cluster_id` 必选、N:1 Mandatory）。跨 Cluster 允许相同范围；同一 Cluster 内活跃范围段**不得重叠**。
4. **V1 仅 IPv4**，表示法为 **`start_ip`–`end_ip`（含两端，dotted-quad）**；**不接受 CIDR**（`10.0.0.0/24`）与 **IPv6**。
5. 范围段**无状态**（Q-002=B）：不存在 `status` 字段 / 枚举 / 默认值 / 过滤。
6. 范围段采用**逻辑删除**；**范围内仍有活跃 IP 时禁止删除**；删除**不级联**；无 undelete / 恢复 / 批量删除。
7. **本契约不含 IP 分配**（自动 / 手动、「最小 IP」、占用判定、耗尽）：属 **F021**，当前 BLOCKED。**不提供**任何分配端点或语义。
8. **不改变** F005 既有 `ip_addresses.ip_address` 的**自由文本登记语义**：本契约**不新增**对 `ip_address` 的格式校验 / 归一化 / trim；R-IP-001~003 不变。
9. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无角色 / 权限 / RBAC**（ADR-0005）。任何已认证用户即可登记 / 修正 / 删除。
10. **不提供** `by-name` 别名、审计 / 历史 / 导出 / 高级筛选 / 排序 / 批量操作、API versioning、游标分页。
11. 本 Feature 的范围段排除立场**取代** `docs/api/f005-ip-address.md` §非目标中「IP 池 / 网段 / 子网」一句（仅该句；`ip_address` 自由文本立场不变）。范围段**不是** IPAddress 的字段，而是**独立资源**。
12. `name` / `subnet_mask` / `vlan` 为 **3 个可选元数据字段**（未登记为 `null`）：`name` **同一 Cluster 内活跃唯一**（区分大小写、软删释放、跨 Cluster 可重复；长度 / 首尾空白 / 空串 / 字符集属未定义约束，见 §7.3）；`subnet_mask` 为 **dotted-quad IPv4 合法掩码**（二进制连续 1 后连续 0），**不强制**与 `start_ip`–`end_ip` 自洽，**V1 仅 IPv4、不使用 CIDR**；`vlan` 为**整数 `1`–`4094`**，**不唯一**。三者**不改变**重叠 / 软删 / 删除守卫 / 无状态 / IPv4 规范化。

---

## 2. IPAddressRange 资源表示

所有返回单个范围段的端点（§3.1、§3.3、§3.4）使用**同一个对象结构**：

```json
{
  "id": 7,
  "cluster_id": 3,
  "start_ip": "10.0.0.1",
  "end_ip": "10.0.0.255",
  "name": "业务网",
  "subnet_mask": "255.255.255.0",
  "vlan": 100,
  "created_at": "2026-09-20T10:00:00Z",
  "updated_at": "2026-09-20T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）。写操作一律使用该值 |
| `cluster_id` | integer | 否 | 归属 Cluster 的 `id`（N:1 Mandatory，恰好一个）；**登记后不可变** |
| `start_ip` | string | 否 | 范围下界，**规范化 dotted-quad IPv4**（如 `10.0.0.1`） |
| `end_ip` | string | 否 | 范围上界，**规范化 dotted-quad IPv4**（如 `10.0.0.255`） |
| `name` | string | **是** | 可选网段自定义名称；**同一 Cluster 内活跃唯一**、区分大小写（R-IP-004）；未登记为 `null`；**原样存取，不做 trim / 归一化**（长度 / 空串 / 字符集未定义，§7.3） |
| `subnet_mask` | string | **是** | 可选 dotted-quad IPv4 掩码（如 `255.255.255.0`）；服务端校验为**合法掩码**（连续 1 后连续 0）、**不强制**与 `start_ip`–`end_ip` 自洽；未登记为 `null`；**原样存取**（不做归一化） |
| `vlan` | integer | **是** | 可选 VLAN 标注，取值 `1`–`4094`；**不唯一**；未登记为 `null` |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间（应用层维护；不是并发控制依据） |

**该字段集合是封闭的**：

- 不存在 `deleted_at`（不对外暴露）；
- 不存在 `status`、状态枚举或任何状态字段（Q-002=B）；
- 不存在 `description` / 用途 / 负责人 等未确认字段；
- 不存在 CIDR / 前缀长度 / 网络地址 / 广播地址 / 网关 / DHCP / DNS / IPv6 字段（`subnet_mask` 为 dotted-quad，**不是** CIDR）；
- 不存在使用率 / 剩余地址 / 容量字段；
- 不存在分配对象 / 分配时间 / 回收状态字段（F021 范围）。

**规范化**：`start_ip` / `end_ip` 在**存储时**即被规范化为 canonical dotted-quad（去前导零、无前缀长度）；再次读取返回同一规范值。例子：入参 `010.000.000.001` → 返回 `10.0.0.1`。

**Cluster 归属的可达方式**：`cluster_id` 是范围段的登记事实，**直接在响应中返回**（与 F005 的 IPAddress 不同——后者的 `cluster_id` 是推导值、不对外暴露）。

**可选元数据字段语义（F022）**：

- `name`：**同一 Cluster 内活跃范围段唯一**；比较**区分大小写**、按**字面等值**（不做 trim / 归一化 / 大小写折叠）；跨 Cluster 可重复；已逻辑删除的范围段**不再占用**该唯一性（R-DELETE-006）。
- `subnet_mask`：必须为**合法 IPv4 掩码**（dotted-quad，二进制连续 1 后连续 0，如 `255.255.255.0`）。**原样存取**（不做归一化）。**不校验**其与 `start_ip`–`end_ip` 是否落在同一子网（描述性元数据）。
- `vlan`：取值 `1`–`4094`（`0` / `4095` 保留）；**不唯一**，同 Cluster 多范围段可共用。
- 三字段均**不参与**重叠判定、删除守卫、`cluster_id` 归属与 IPv4 规范化；登记后**可经 `PATCH` 修正 / 清空**（§3.4）。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递。

---

## 3. 端点

### 3.1 `POST /api/ip-address-ranges` — 登记范围段

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/ip-address-ranges` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**

```json
{ "cluster_id": 3, "start_ip": "10.0.0.1", "end_ip": "10.0.0.255",
  "name": "业务网", "subnet_mask": "255.255.255.0", "vlan": 100 }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `cluster_id` | integer | **是** | 否 | 归属 Cluster 的 `id`；必须存在且**活跃** |
| `start_ip` | string | **是** | 否 | 合法 IPv4；规范化后作为范围下界 |
| `end_ip` | string | **是** | 否 | 合法 IPv4；规范化后作为范围上界；须满足 `start_ip <= end_ip` |
| `name` | string | 否 | **是** | 可选网段名称；**同 Cluster 活跃唯一**、区分大小写；不提供 / 提供 `null` 均视为未登记 |
| `subnet_mask` | string | 否 | **是** | 可选 dotted-quad IPv4 合法掩码；非法 → `400` |
| `vlan` | integer | 否 | **是** | 可选 VLAN，取值 `1`–`4094`；越界 / 非整数 → `400` |

- 请求 schema **封闭**（`extra="forbid"`）。接受字段**恰为** `{cluster_id, start_ip, end_ip, name, subnet_mask, vlan}`；**不接受** `description` / 用途 / `status` / `deleted_at` / `id` / `created_at` / `updated_at` / CIDR / 前缀长度 / 网关 等任何未识别字段（→ `400`）。

**Response 201**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| 缺少 `cluster_id` / 非整数 / `null` | `400` | `VALIDATION_ERROR` | `field == "cluster_id"` |
| `cluster_id` 引用**不存在或已逻辑删除**的 Cluster | `404` | `NOT_FOUND` | `[]` |
| 缺少 `start_ip` / `end_ip` / 非字符串 / `null` | `400` | `VALIDATION_ERROR` | `field == "start_ip"` / `"end_ip"` |
| `start_ip` 或 `end_ip` 非法 IPv4（`10.0.0.256`、`10.0.0`、`abc`、`1.2.3.4/24`、`2001:db8::1`、空串、含空白等） | `400` | `VALIDATION_ERROR` | 对应 `field` |
| `start_ip > end_ip`（数值比较） | `400` | `VALIDATION_ERROR` | `field == "start_ip"`（或 `end_ip`，best-effort；不构成契约） |
| `subnet_mask` 非法（非 dotted-quad、非连续掩码如 `255.0.255.0`、`10.0.0.1`、`255.255.255.256`、`/24`、`2001:db8::1`、空串、含空白） | `400` | `VALIDATION_ERROR` | `[{ "field": "subnet_mask", "code": "INVALID", ... }]` |
| `vlan` 非整数 / 布尔 / 浮点 / 越界（`0`、`4095`、`>4094`、`<1`） | `400` | `VALIDATION_ERROR` | `[{ "field": "vlan", "code": "INVALID", ... }]` |
| 同 Cluster 已存在**活跃同名** `name`（大小写敏感、软删释放） | `409` | `CONFLICT` | `[{ "field": "name", "code": "DUPLICATE", ... }]` |
| 目标 Cluster 内已有活跃范围段与请求区间**交集非空**（含共享端点） | `409` | `CONFLICT` | `[{ "code": "OVERLAP", ... }]` |
| 未识别字段 | `400` | `VALIDATION_ERROR` | 该字段名 |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- `cluster_id` 不存在 / 已删返回 `404 NOT_FOUND`（NQ 裁定，与 F002 / F004 / F005 一致）：由同一事务内「对 Cluster 行取 `FOR SHARE` 并确认活跃」给出，**非 5xx**。
- 跨 Cluster 允许相同范围（R-IP-002 类比）；不同的合法 IPv4 字面值经规范化后若数值相同，视为同一地址（见 §7 规范化承诺）。

**并发语义**：登记对父 Cluster 行取共享锁；排它约束（`EXCLUDE`，仅活跃行）为**不重叠的最终权威**；与 Cluster 逻辑删除并发时，二者恰有一个成功（§6）。

---

### 3.2 `GET /api/ip-address-ranges` — 列出活跃范围段

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/ip-address-ranges` |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50）、`cluster_id`（integer，可选） |
| 认证 | **必需**（§5） |

**语义**

- 未提供 `cluster_id`：返回系统中全部活跃范围段。
- 提供 `cluster_id`：**按 Cluster 限定**返回该 Cluster 的活跃范围段。父 Cluster **不存在或已逻辑删除** → `404 NOT_FOUND`；父 Cluster **存在但无活跃范围段** → `200` + `items == []`（**Empty**）。
- 已逻辑删除的范围段**不出现**在 `items`，也不计入 `total`。
- **不存在** `status` / CIDR / 关键字 / 排序 / 分配状态等第二维度查询参数；本契约不定义此类参数，前端与调用方**不得构造**。

**Response 200**

```json
{ "items": [ { "id": 7, "cluster_id": 3, "start_ip": "10.0.0.1", "end_ip": "10.0.0.255",
  "name": "业务网", "subnet_mask": "255.255.255.0", "vlan": 100,
  "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-20T10:00:00Z" } ],
  "total": 1, "page": 1, "page_size": 50 }
```

- `items`：按 `id` 升序。
- `total`：**活跃**范围段总数（受 `cluster_id` 过滤时为该过滤域内的活跃数）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| `cluster_id` 非整数 | `400` | `VALIDATION_ERROR` | `"cluster_id"` |
| `cluster_id` 引用不存在 / 已逻辑删除的 Cluster | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Empty / Not Found 语义**：

| 情形 | 响应 |
|---|---|
| 无活跃范围段（未给 `cluster_id`） | `200`，`items == []`，`total == 0`（**Empty**） |
| `cluster_id` 存在但无活跃范围段 | `200`，`items == []`（**Empty**） |
| `cluster_id` 不存在或已逻辑删除 | `404 NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

### 3.3 `GET /api/ip-address-ranges/{ip_address_range_id}` — 按 id 读取

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/ip-address-ranges/{ip_address_range_id}` |
| Path parameter | `ip_address_range_id`（integer） |
| 认证 | **必需**（§5） |

**Response 200**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `ip_address_range_id` 非整数 | `400` | `VALIDATION_ERROR` | `"ip_address_range_id"` |
| `ip_address_range_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：`404` 同时覆盖「不存在」与「已被逻辑删除」，两者不做区分。

---

### 3.4 `PATCH /api/ip-address-ranges/{ip_address_range_id}` — 修正范围

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/api/ip-address-ranges/{ip_address_range_id}` |
| Path parameter | `ip_address_range_id`（integer） |
| 认证 | **必需**（§5） |

**Request body**（部分更新）

```json
{ "start_ip": "10.0.0.1", "end_ip": "10.0.1.255", "name": "业务网",
  "subnet_mask": "255.255.255.0", "vlan": 100 }
```

**可变字段（封闭集合）**：**恰为 `{start_ip, end_ip, name, subnet_mask, vlan}`**。

**不可变字段**：`id`、`cluster_id`、`created_at`、`deleted_at`。请求体中出现任何不可变字段或未识别字段 → `400 VALIDATION_ERROR`。

**关键语义**

- 请求体**至少**需包含一个可变字段；空 body（`{}`）→ `400 VALIDATION_ERROR`。
- **缺席**的可变字段保持不变。
- **`null` 语义**：`start_ip` / `end_ip` 为必填非空，提供 `null` → `400`（不变）；`name` / `subnet_mask` / `vlan` 提供 `null` → **清空为 `null`**（未登记）。
- 修正后**重新执行** IPv4 解析与 `start_ip <= end_ip` 校验，并**重新执行重叠校验**：新区间若与**同 Cluster 其它活跃范围段**交集非空 → `409` + `details[].code == "OVERLAP"`，**无部分写入**（原值不变）。
- 提供非空 `name` 时**重新执行同 Cluster 活跃唯一校验**（排除自身）：与同 Cluster 其它活跃范围段 `name` 字面相同 → `409` + `details[].code == "DUPLICATE"`；`name` 置 `null` 不触发唯一性冲突。
- 提供 `subnet_mask` 时**重新执行掩码合法性校验**（非法 → `400`）；提供 `vlan` 时**重新执行范围校验**（越界 → `400`）。
- `cluster_id` **不可变**：范围段不能迁移到其它 Cluster。
- 无乐观锁；并发更新为**最后提交生效**；`updated_at` **不是**并发控制依据。
- 本资源**无状态**（`status` 出现在请求体 → `400`）。

**Response 200**：§2 的单对象结构；`id`、`cluster_id`、`created_at` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[]` |
|---|---|---|---|
| 请求体含未识别 / 不可变字段（含 `id` / `cluster_id` / `created_at` / `deleted_at` / `status` / `description`） | `400` | `VALIDATION_ERROR` | `field` = 该字段名 |
| 请求体无可变字段（含 `{}`） | `400` | `VALIDATION_ERROR` | 非契约 |
| `start_ip` / `end_ip` 为 `null` / 非字符串 / 非法 IPv4 | `400` | `VALIDATION_ERROR` | 对应 `field` |
| `subnet_mask` 为 `null` 以外但非法（非 dotted-quad / 非连续掩码 / CIDR / IPv6 / 空串 / 含空白） | `400` | `VALIDATION_ERROR` | `field == "subnet_mask"` |
| `vlan` 非整数 / 布尔 / 浮点 / 越界（`0` / `4095` / `>4094` / `<1`） | `400` | `VALIDATION_ERROR` | `field == "vlan"` |
| `start_ip > end_ip` | `400` | `VALIDATION_ERROR` | best-effort |
| 与同 Cluster 其它活跃范围段重叠 | `409` | `CONFLICT` | `[{ "code": "OVERLAP", ... }]` |
| 提供的非空 `name` 与同 Cluster 其它活跃范围段重复 | `409` | `CONFLICT` | `[{ "field": "name", "code": "DUPLICATE", ... }]` |
| 目标不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| `ip_address_range_id` 非整数 | `400` | `VALIDATION_ERROR` | `field == "ip_address_range_id"` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- 排它约束为**最终权威**；`23P01` 经 `app/common/sqlstate.py` 通用映射 → `409`（**永不 500**）。

---

### 3.5 `DELETE /api/ip-address-ranges/{ip_address_range_id}` — 逻辑删除

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/api/ip-address-ranges/{ip_address_range_id}` |
| Path parameter | `ip_address_range_id`（integer） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§5） |

**Response 204**

- 无响应体。
- 目标范围段的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新；该行**仍物理存在**（R-DELETE-001）。
- 删除**只修改目标行**，不级联；**不修改**其 Cluster、相关 BareMetal / NetworkInterface / IPAddress 的任一字段（R-DELETE-005）。
- 已删范围段不再参与重叠判定：同一 Cluster 内可重新登记与之重叠的活跃范围段。
- 旧已删行保留且 `deleted_at` **不被改写**（无 undelete，R-DELETE-003）。

**删除守卫**：**当同 Cluster 存在活跃（`deleted_at IS NULL`）IPAddress，且其字面地址落在 `[start_ip, end_ip]` 内时，禁止删除**该范围段。命中时返回 `409`，且目标范围段的 `deleted_at` **仍为 NULL**（无部分写入）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `ip_address_range_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "ip_address_range_id", "code": "INVALID" }]` |
| 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| 范围内仍有活跃 IP（无需删除这些 IP，须先软删） | `409` | `CONFLICT` | `[{ "row": null, "field": null, "code": "ACTIVE_CHILDREN_EXIST", "message": "资源仍存在活跃子资源，无法删除" }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- `404` 同时覆盖「不存在」与「已被逻辑删除」；重复删除同一 `id` 返回 `404`。

**不提供的能力**：不提供 `by-name` 删除；不提供批量删除 / 条件删除 / 恢复 / 查看已删资源。

---

## 4. 错误信封

本资源复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 的实现。不另立一套。

### 4.1 `409 CONFLICT` — 同 Cluster 内活跃范围段重叠

```json
{ "error": { "code": "CONFLICT", "message": "范围段重叠",
  "details": [ { "row": null, "field": null, "code": "OVERLAP",
    "message": "同一 Cluster 内已存在与该范围重叠的活跃范围段" } ] } }
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定** |
| `details[].code` | `"OVERLAP"` | **稳定**：机器可读判别值 |
| `details[].field` / `details[].row` | `null` | 不构成契约 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约** |

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

> **DB 兜底路径**：绕过应用层预检写入重叠的活跃范围段时，排它约束 `ex_ip_address_ranges_active_no_overlap` 触发 SQLSTATE `23P01`，经 `app/common/sqlstate.py` 通用映射返回 `409 CONFLICT` + `details[].code = "OVERLAP"`；此路径下 `details[].field` 为 best-effort 解析结果，**不构成契约**。

### 4.2 `409 CONFLICT` — 同 Cluster 活跃 `name` 重复

```json
{ "error": { "code": "CONFLICT", "message": "网段名称已存在",
  "details": [ { "field": "name", "code": "DUPLICATE",
    "message": "同一 Cluster 内已存在活跃的同名范围段" } ] } }
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定** |
| `details[].code` | `"DUPLICATE"` | **稳定**：机器可读判别值 |
| `details[].field` | `"name"` | 应用层路径稳定 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约** |

> **DB 兜底路径**：绕过应用层预检写入同 Cluster 活跃同名 `name` 时，partial unique index `ux_ip_address_ranges_cluster_name_active` 触发 SQLSTATE `23505`，经 `app/common/sqlstate.py` 通用映射返回 `409 CONFLICT` + `details[].code = "DUPLICATE"`；此路径下 `details[].field` 为 best-effort 解析结果，**不构成契约**。

### 4.3 `409 CONFLICT` — 范围内存在活跃 IP（删除守卫）

```json
{ "error": { "code": "CONFLICT", "message": "父资源存在活跃子资源，无法删除",
  "details": [ { "row": null, "field": null, "code": "ACTIVE_CHILDREN_EXIST",
    "message": "资源仍存在活跃子资源，无法删除" } ] } }
```

- 该 `409` **不产生任何写入**：目标范围段的 `deleted_at` 仍为 NULL（无部分写入）。
- 先软删落在该范围内的全部活跃 IP 后，`DELETE` → `204`。
- `ACTIVE_CHILDREN_EXIST` 是本系统**既有稳定判别值**（`app.deletion.service`），本契约沿用，不新增。

### 4.4 其他错误

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| 字段格式 / 必填 / 未识别字段 / 空 PATCH / 必填字段 `null` / 非法 IPv4 / `start > end` / 非法 `subnet_mask` / 越界 `vlan` | `400` | `VALIDATION_ERROR` | `details[].field` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 目标不存在或已删；父 Cluster 不存在或已删 | `404` | `NOT_FOUND` | `[]` |
| 范围段重叠 | `409` | `CONFLICT` | `details[].code = "OVERLAP"` |
| 同 Cluster 活跃 `name` 重复 | `409` | `CONFLICT` | `details[].code = "DUPLICATE"`（`field == "name"`） |
| 范围内有活跃 IP（删除） | `409` | `CONFLICT` | `details[].code = "ACTIVE_CHILDREN_EXIST"` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

> 补充：父 Cluster 不存在 / 已删的 FK 违规（`23503`）经**既有通用** `sqlstate.py` 映射返回 `409 CONFLICT` + `details[].code = "REFERENCE"`；该路径在产品路径下**不可达**（`FOR SHARE` 预检先给出 `404`，且 Cluster 无物理删除），不为本资源另立映射。

---

## 5. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（ADR-0005）。
- 认证成功即可执行全部操作；**不需要**任何角色 / 权限（V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点均位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 6. 并发与一致性语义

### 6.1 登记路径

1. `POST` 在**同一请求事务内**先对父 Cluster 行取共享锁（`SELECT … WHERE id = :id AND deleted_at IS NULL FOR SHARE`）；未命中 → `404 NOT_FOUND`。
2. 应用层严格解析 `start_ip` / `end_ip` 为数值、校验 `start <= end`。
3. 应用层**重叠预检**（活跃范围内判断闭区间交集非空，排除自身）以返回友好 `409 OVERLAP`。
4. 插入；数据库排它约束 `ex_ip_address_ranges_active_no_overlap`（`WHERE deleted_at IS NULL`）为**最终权威**。

### 6.2 修正路径

`PATCH` 对目标范围段行取 `FOR UPDATE`（或经 `soft_delete` 同级的受控路径）后重跑解析 / `start <= end` / 重叠校验；命中冲突 → `409`，**无部分写入**。

### 6.3 删除路径

`DELETE` 委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`）：在同一事务内先对目标行取 `FOR UPDATE`，再执行 `IP_ADDRESS_RANGE_ACTIVE_CHILD_CHECKS`（含「范围内是否有活跃 IP」）；命中即 `409` 且不写 `deleted_at`；否则仅对已锁定目标行赋值 `deleted_at`。

### 6.4 并发结果（不变式）

- 「登记范围段」与「删除其父 Cluster」并发时，二者**恰有一个**成功；结束后不存在「活跃范围段挂在已删 Cluster 下」：

  ```sql
  SELECT count(*) FROM ip_address_ranges r
  JOIN clusters c ON c.id = r.cluster_id
  WHERE r.deleted_at IS NULL AND c.deleted_at IS NOT NULL;   -- 必须为 0
  ```

- 同 Cluster 活跃范围段两两**不重叠**（排它约束的必然结果）：

  ```sql
  SELECT a.id AS a_id, b.id AS b_id
  FROM ip_address_ranges a
  JOIN ip_address_ranges b
    ON a.cluster_id = b.cluster_id AND a.id < b.id
   AND a.deleted_at IS NULL AND b.deleted_at IS NULL
   AND a.start_ip <= b.end_ip AND a.end_ip >= b.start_ip;   -- 期望 0 行
  ```

- **范围段与「已登记 IP」的一致性不是硬约束**（DEC-023 第 6 项）：范围段删除与「在其 Cluster 内登记落在范围中的新 IP」**不互相串行**。极端并发下可能出现「活跃 IP 存在、其范围已被删」；本契约**不承诺**「每个活跃 IP 必被某个活跃范围覆盖」，仅由 §6.5 的检测查询发现。

### 6.5 漂移 / 一致性检测查询（回归用，不提供端点）

- **范围覆盖漂移**（活跃 IP 未被任何活跃范围覆盖；属 DEC-023 第 6 项「建议交付」）：

  在应用层 / 测试侧执行：对该 Cluster 的活跃 IP 字面值逐一按 §7 解析为 IPv4；若其数值不落在该 Cluster 任一活跃范围段内，则为漂移。该查询**不提供 API 端点**，仅作为测试回归断言。

- **删除守卫的并发窗口**：由上述查询检测；本 Feature 不引入额外锁或触发器消除该窗口（符合 DEC-023 第 6 项）。

---

## 7. IPv4 规范化与 `ip_address` 自由文本立场

### 7.1 范围段字段（有承诺）

- `start_ip` / `end_ip` 必须是**合法 IPv4**，解析规则：恰好 4 个以 `.` 分隔的十进制段，每段 1~3 位数字、值 0~255；**允许前导零**（规范化时去除）；**不接受**前缀长度（`/n`）、IPv6、空白、空串、非数字字符。
- 规范化形式 = canonical dotted-quad（无前导零、无前缀长度），如 `010.000.000.001` → `10.0.0.1`。
- 比较按**数值**（IPv4 无符号 32 位整数）。
- 示例（`400`）：`10.0.0.256`、`10.0.0`、`abc`、`1.2.3.4/24`、`2001:db8::1`。

### 7.2 `ip_addresses.ip_address`（**无新承诺**）

- F005 既有的**自由文本登记语义完全不变**：不实现、不承诺其格式校验与归一化；本契约**不新增**对 `ip_address` 的长度 / trim / 空串 / 格式 / CIDR / 归一化约束（R-IP-004；AC-23）。
- **删除守卫对 `ip_address` 的解析语义**（Architecture 定稿 NQ-C）：
  - 取字面值中**第一个 `/` 之前**的部分，按 §7.1 的严格规则尝试解析为 IPv4；
  - 解析成功 → 以数值与该 Cluster 的活跃范围段比较；
  - 解析失败（如 `abc`、空串、含前导空白、IPv6、无地址部分）→ **跳过该行**，视为**不落在任何范围内**，且**不得返回 500**。
  - 该解析**仅用于删除守卫的只读判定**，**不构成**对 `ip_address` 的写入约束；`ip_address` 仍原样存取。
  - 例子：`10.0.1.1` 与 `10.0.1.1/16` 均被视为地址 `10.0.1.1`，若落在范围内则阻止删除；`abc` 不阻止删除。

### 7.3 可选元数据字段（`name` / `subnet_mask` / `vlan`）

- **`name`（未定义约束，不承诺）**：本契约**不承诺** `name` 的长度 / 首尾空白（trim）/ 空串 / 非法字符 / `/` / Unicode 归一化 / 大小写折叠行为。**唯一承诺**：同一 Cluster 内活跃范围段 `name` **字面等值唯一**、**区分大小写**（§22）；**不做** `lower(name)` 唯一索引、**不声明** `COLLATE`。含首尾空白或空字符串的 `name` 在现有规则下**不会被拒绝**——这**不得**解读为「空 `name` 合法」已确认。空串 `""` 满足 `name IS NOT NULL`，按**字面**参与唯一性：同一 Cluster 内两个活跃范围段若都写入 `name = ""`，第二个会被拒绝（`409 CONFLICT` + `details[].code = "DUPLICATE"`）；前端将空输入映射为 `null`（不发送 `""`）。
- **`subnet_mask`**：必须为**合法 IPv4 掩码**（dotted-quad，恰好 4 段 0–255，二进制连续 1 后连续 0；`0.0.0.0` 与 `255.255.255.255` 均合法）。**原样存取**（不做归一化 / trim）。**不校验**与 `start_ip`–`end_ip` 是否同一子网。**V1 仅 IPv4**；**不接受** CIDR 前缀长度（`/24`）与 IPv6。
- **`vlan`**：必须为**整数 `1`–`4094`**；`0` / `4095` / 越界值 / 非整数（含布尔、浮点、字符串）→ `400`。**不唯一**。

---

## 8. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取 / 列表成功（含空列表）/ 更新成功 | — |
| `201` | 登记成功 | — |
| `204` | 删除成功（无响应体） | — |
| `400` | 请求格式或字段校验失败（缺字段、非整数参数、必填字段 `null`、未识别字段、空 PATCH、非法 IPv4、`start > end`、非法 `subnet_mask`、越界 / 非整数 `vlan`） | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | 范围段不存在或已被逻辑删除；父 Cluster 不存在或已删除 | `NOT_FOUND` |
| `409` | 同 Cluster 活跃范围段重叠 | `CONFLICT`（`details[].code = "OVERLAP"`） |
| `409` | 同 Cluster 活跃 `name` 重复 | `CONFLICT`（`details[].code = "DUPLICATE"`） |
| `409` | 范围内仍有活跃 IP，删除被拒 | `CONFLICT`（`details[].code = "ACTIVE_CHILDREN_EXIST"`） |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**；前端必须按 `error.code` 分支，不解析 `message`。

---

## 9. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `GET /api/ip-address-ranges`：无活跃范围段 | `200`，`items == []`，`total == 0`（**Empty**） |
| `GET /api/ip-address-ranges?cluster_id={id}`：Cluster 存在但无活跃范围段 | `200`，`items == []`（**Empty**） |
| `GET /api/ip-address-ranges?cluster_id={id}`：Cluster 不存在 / 已删 | `404` `NOT_FOUND` |
| `GET /api/ip-address-ranges/{id}`：不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `PATCH /api/ip-address-ranges/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `DELETE /api/ip-address-ranges/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `POST /api/ip-address-ranges`：引用的 Cluster 不存在 / 已删 | `404` `NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

## 10. 明确不在本契约中（非目标）

- Cluster / BareMetal / NetworkInterface / IPAddress / VirtualMachine / Container / Service 的端点与删除（权威正文：`docs/api/f001-cluster.md` / `f002-bare-metal.md` / `f004-network-interface.md` / `f005-ip-address.md` / `f006-virtual-machine.md` / `f007-container.md` / `f008-service.md` / `f014-soft-delete.md`）。
- **IP 分配 / 回收工作流**（自动 / 手动、「第一个最小 IP」、占用判定、耗尽错误）：属 **F021**，当前 BLOCKED。
- **CIDR 表示**、**IPv6**、网络地址 / 广播地址 / 网关等保留地址概念。
- **范围段的状态**（Q-002=B）。
- **`ip_addresses.ip_address` 的格式校验与归一化**（F005 NQ-1；§7.2）：不实现、不承诺。
- 使用率统计 / 剩余地址 / 冲突扫描 / 容量预警 / 外部平台同步 / DHCP / DNS / 自动资产发现 / 导出。
- 范围段的 `description` / 用途 / 负责人 / 分配对象等未确认字段；CIDR / IPv6 / 网关 / DHCP / DNS / 使用率 / 容量字段。
- `by-name` 别名；排序 / 关键字 / CIDR / 前缀 / 状态等第二维度查询参数；批量操作。
- `name` / `subnet_mask` / `vlan` **不是**查询 / 筛选 / 排序参数：本契约**不提供**按名称 / 掩码 / VLAN 的过滤或排序；`name` 非全局唯一，**不提供** `by-name` 别名寻址。
- 物理删除、Undelete / Restore / 回收站 / 已删资源查看 / 批量删除（R-DELETE-001/003；ADR-0004）。
- 审计 / 历史 / 操作人 / 导出 / 高级筛选 / 排序（无需求）。
- API versioning、游标分页（无需求）。
