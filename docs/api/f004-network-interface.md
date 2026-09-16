# F004 API 契约 — NetworkInterface 登记与管理

> Status: **READY**
> Feature: F004（E02，P1，`depends_on: [F002]` = DONE）
> Author Role: architect
> Source: `docs/api/api-conventions.md`（`READY`）、ADR-0002 / 0003 / 0004 / 0005（均 `ACCEPTED`）、`docs/architecture/f004-network-interface-handoff.md`、`docs/api/f002-bare-metal.md`、`docs/api/f006-virtual-machine.md`、`docs/api/f014-soft-delete.md`、`docs/product/handoffs/f004-network-interface.md`
> 本文件是 F004 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **NetworkInterface 资源**的产品 API，共 **5 个端点**（§3）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty / Not Found 语义、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件不重复定义。
3. NetworkInterface **必属恰好一个 BareMetal**（R-NIC-003，N:1 mandatory）；**Cluster 归属由宿主推导、不单独记录**，本资源**无 `cluster_id`**、无 Cluster 维度过滤参数。
4. NetworkInterface **不设状态**（Q-002=B）。
5. `technology_type` 必填且**封闭集合** `Ethernet / InfiniBand / RoCE / Other`（R-NIC-001）；`purpose` 必填且**封闭集合** `BMC / Management / Business / Compute / Storage / DataTransfer / Other`（R-NIC-002）。**字面精确匹配，不做大小写折叠 / trim / 归一 / 中文映射**。新增取值须重新走需求确认流程。
6. `name` 为**必填登记字段**。其长度 / 首尾空白 / 空字符串 / 非法字符等属**未定义约束**：本契约**不承诺其行为**（§7）。
7. NetworkInterface **无已确认的唯一性规则**：本契约**不存在**任何名称唯一性校验，也**不存在** `409 DUPLICATE` 分支（NQ-2 未确认）。这不表示「同名合法」是已确认规则。
8. 本契约**不含** IP 语义（无 IP 字段 / 端点 / `ip_addresses` 表 / 为 IP 唯一性服务的 `cluster_id` 列）——归 F005。
9. 本契约**不含** VM / Container / Service / Cluster 载体绑定；请求 schema **封闭**，不接受多父、不接受载体类型选择器（NQ-1 未确认，不予预留）。
10. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无角色 / 权限 / RBAC**（ADR-0005）。
11. 本契约**不包含** Cluster CRUD、BareMetal 端点、删除语义总则、Cluster 视角 / 关联查询视图（F009 / F010）。不修改任何既有契约。
12. **不提供** `by-name` 别名（`name` 唯一性未确认，全局不可判定）。
13. **不提供** `name` 重命名与父绑定变更（登记后不可变；NQ-3）。变更由「软删 + 重新登记」替代。

---

## 2. NetworkInterface 资源表示

所有返回单个 NetworkInterface 的端点（§3.1、§3.3、§3.4）使用**同一个对象结构**：

```json
{
  "id": 12,
  "bare_metal_id": 3,
  "name": "eth0",
  "technology_type": "Ethernet",
  "purpose": "Business",
  "created_at": "2026-09-17T10:00:00Z",
  "updated_at": "2026-09-17T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）。写操作一律使用该值 |
| `bare_metal_id` | integer | 否 | 宿主 BareMetal 的 `id`（R-NIC-003，恰好一个宿主） |
| `name` | string | 否 | 接口名（`eth0` / `ib0` …）；**原样存取**，不做 trim / 归一化；**无唯一性承诺** |
| `technology_type` | string（枚举） | 否 | 封闭集合（R-NIC-001） |
| `purpose` | string（枚举） | 否 | 封闭集合（R-NIC-002） |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间（应用层维护；不是并发控制依据） |

**该字段集合是封闭的**：不存在 `deleted_at`；不存在 `status`（Q-002=B）；不存在 `cluster_id` 等 Cluster 维度字段；不存在 MAC / 速率 / MTU / 光模块 / 端口号等未确认字段（§23）；不存在 IP 语义字段（F005）；不存在 `vm_id` / `container_id` / `service_id` / 载体类型选择器（NQ-1）；不存在自动发现 / 外部平台同步 / 平台 id / 凭据字段（§23）。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递。

---

## 3. 端点

### 3.1 `POST /api/network-interfaces` — 登记 NetworkInterface

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/network-interfaces` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**

```json
{ "bare_metal_id": 3, "name": "eth0", "technology_type": "Ethernet", "purpose": "Business" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `bare_metal_id` | integer | **是** | 否 | 宿主 `id`；必须存在且活跃 |
| `name` | string | **是** | 否 | 接口名；**不校验长度 / trim / 空串 / 字符规则**（§7）；**不校验唯一性** |
| `technology_type` | string（枚举） | **是** | 否 | 必须**逐字**属于封闭集合 |
| `purpose` | string（枚举） | **是** | 否 | 必须**逐字**属于封闭集合 |

- 未识别字段 → `400 VALIDATION_ERROR`（请求 schema 封闭）。**不接受**多父字段、载体类型选择器，也不接受以 VM / Container / Cluster / Service 为父。
- `Other` **是枚举的普通合法成员**，不是自由填写入口；schema **不存在** `other_text` / `description` / 备注类伴随字段。

**Response 201**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 缺少 `name`（含 `{}`）/ 非字符串 | `400` | `VALIDATION_ERROR` | `"name"` | `INVALID` 或非契约 |
| 缺少 `bare_metal_id` / 非整数 | `400` | `VALIDATION_ERROR` | `"bare_metal_id"` | 非契约 |
| `bare_metal_id` 引用不存在 / 已逻辑删除的 BareMetal | `404` | `NOT_FOUND` | — | —（`details == []`） |
| 缺少 `technology_type` | `400` | `VALIDATION_ERROR` | `"technology_type"` | 非契约 |
| `technology_type` 非字符串 / 不在封闭集合内（含 `null` / 空串 / `ethernet` / `FibreChannel` / `"Other "`） | `400` | `VALIDATION_ERROR` | `"technology_type"` | `INVALID` |
| 缺少 `purpose` | `400` | `VALIDATION_ERROR` | `"purpose"` | 非契约 |
| `purpose` 非字符串 / 不在封闭集合内 | `400` | `VALIDATION_ERROR` | `"purpose"` | `INVALID` |
| 未识别字段 / 多父 / 载体类型选择器 | `400` | `VALIDATION_ERROR` | 该字段名 | 非契约 |
| 未认证 | `401` | `UNAUTHENTICATED` | — | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 上述 `400` / `404` 情形**不得产生任何写入**。
- **引用不存在 / 已删宿主返回 `404 NOT_FOUND`**（NQ-5 裁定，与 F002 / F006 一致）；由 `FOR SHARE` 预检给出，**非 5xx**。
- 同宿主同名 `name` 的第二次登记**成功**（`201`），返回不同 `id`。
- 枚举约束由数据库 `CHECK` 作为**最终权威**；`23514` 经通用映射返回 `400`（**永不返回 500**）。

**并发语义**：登记对宿主 BareMetal 行取共享锁；与宿主逻辑删除并发时，二者恰有一个成功（见 §6）。

---

### 3.2 `GET /api/network-interfaces` — 列出活跃 NetworkInterface

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/network-interfaces` |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50）、`bare_metal_id`（integer，可选） |
| 认证 | **必需**（§5） |

**语义**

- 未提供 `bare_metal_id`：返回系统中全部活跃 NetworkInterface。
- 提供 `bare_metal_id`：**按宿主限定**返回该 BareMetal 的活跃 NetworkInterface（R-QUERY-003 的 F004 侧 canonical 能力；**供 F010 复用**，F010 不得另写一份过滤）。宿主**不存在或已逻辑删除** → `404 NOT_FOUND`；宿主**存在但无活跃 NetworkInterface** → `200` + `items == []`（**Empty**）。
- 已逻辑删除的 NetworkInterface **不出现**在 `items`，也不计入 `total`。

**Response 200**

```json
{ "items": [ { "id": 12, "bare_metal_id": 3, "name": "eth0",
  "technology_type": "Ethernet", "purpose": "Business",
  "created_at": "2026-09-17T10:00:00Z", "updated_at": "2026-09-17T10:00:00Z" } ],
  "total": 1, "page": 1, "page_size": 50 }
```

- `items`：按 `id` 升序。
- `total`：**活跃** NetworkInterface 总数（受 `bare_metal_id` 过滤时为该过滤域内的活跃数）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| `bare_metal_id` 非整数 | `400` | `VALIDATION_ERROR` | `"bare_metal_id"` |
| `bare_metal_id` 引用不存在 / 已逻辑删除的 BareMetal | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Empty / Not Found 语义**：

| 情形 | 响应 |
|---|---|
| 无活跃 NetworkInterface（未给 `bare_metal_id`） | `200`，`items == []`，`total == 0`（**Empty**） |
| `bare_metal_id` 存在但无活跃 NetworkInterface | `200`，`items == []`（**Empty**） |
| `bare_metal_id` 不存在或已逻辑删除 | `404 NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

### 3.3 `GET /api/network-interfaces/{network_interface_id}` — 按 id 读取

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/network-interfaces/{network_interface_id}` |
| Path parameter | `network_interface_id`（integer） |
| 认证 | **必需**（§5） |

**Response 200**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `network_interface_id` 非整数 | `400` | `VALIDATION_ERROR` | `"network_interface_id"` |
| `network_interface_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：`404` 同时覆盖「不存在」与「已被逻辑删除」，两者不做区分。

---

### 3.4 `PATCH /api/network-interfaces/{network_interface_id}` — 更新技术类型 / 用途

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/api/network-interfaces/{network_interface_id}` |
| Path parameter | `network_interface_id`（integer） |
| 认证 | **必需**（§5） |

**Request body**（部分更新）

```json
{ "technology_type": "InfiniBand", "purpose": "Compute" }
```

**可变字段（封闭集合）**：`technology_type`、`purpose`（NQ-7）。两者提供时必须在封闭集合内，**不得为 `null`**。

**不可变字段**：`id`、`bare_metal_id`、`name`、`created_at`、`deleted_at` **不接受**修改。请求体中出现不可变字段或任何未识别字段 → `400 VALIDATION_ERROR`。

**关键语义**

- 请求体**至少**需包含一个可变字段；空 body（`{}`）→ `400 VALIDATION_ERROR`。
- 未提供的字段保持不变；修改后后续读取返回同一值。
- 无乐观锁；并发更新为**最后提交生效**；`updated_at` **不是**并发控制依据。
- 本资源**无状态**（`status` 出现在请求体 → `400`）；**无唯一性**（更新路径不涉及唯一性冲突）。

**Response 200**：§2 的单对象结构；`id`、`created_at`、`bare_metal_id`、`name` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 请求体含未识别 / 不可变字段（含 `name` / `bare_metal_id` / `id` / `deleted_at` / `status` / `cluster_id`） | `400` | `VALIDATION_ERROR` | 该字段名 | 非契约 |
| 请求体无可变字段（含 `{}`） | `400` | `VALIDATION_ERROR` | — | 非契约 |
| 枚举字段为 `null` / 非字符串 / 不在封闭集合内 | `400` | `VALIDATION_ERROR` | 该字段名 | `INVALID` |
| 目标不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | — | — |
| `network_interface_id` 非整数 | `400` | `VALIDATION_ERROR` | `"network_interface_id"` | 非契约 |
| 未认证 | `401` | `UNAUTHENTICATED` | — | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 上述 `400` / `404` 情形**不得产生任何写入**。
- 枚举约束由数据库 `CHECK` 作为**最终权威**；`23514` → `400`（**永不 500**）。

---

### 3.5 `DELETE /api/network-interfaces/{network_interface_id}` — 逻辑删除

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/api/network-interfaces/{network_interface_id}` |
| Path parameter | `network_interface_id`（integer） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§5） |

**Response 204**

- 无响应体。
- 目标 NetworkInterface 的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新；该行**仍物理存在**（R-DELETE-001）。
- 删除**只修改目标行**，不级联；**宿主 BareMetal 的 `deleted_at` / `updated_at` / 各字段不变**（R-DELETE-005）。
- 已删资源不出现在常规查询；本资源**无已确认唯一性规则**，删除不产生任何「释放唯一性」行为，`deleted_at` 一旦写入不再回退（R-DELETE-003）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `network_interface_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "network_interface_id", "code": "INVALID" }]` |
| 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| 目标存在**活跃**子资源 | `409` | `CONFLICT` | `[{ "field": null, "row": null, "code": "ACTIVE_CHILDREN_EXIST" }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- `404` 同时覆盖「不存在」与「已被逻辑删除」；重复删除同一 `id` 返回 `404`。
- `409` **不产生任何写入**：目标行 `deleted_at` 仍为空。
- 当前 NetworkInterface **没有**活跃子资源（`ip_addresses` 表尚不存在），故 `409` 在本 Feature 内**不可达**；该分支由 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 声明点承接（当前显式空元组），**F005** 落地时追加「活跃 IPAddress」检查。**不得**因此认为「NetworkInterface 永远无子资源」。

**不提供的能力**：不提供 `by-name` 删除（写操作一律走 `id`）；不提供批量删除 / 条件删除 / 恢复 / 查看已删资源。

---

## 4. 错误信封

本资源复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 的实现。不另立一套。

### 4.1 `409 CONFLICT` — 目标存在活跃子资源（NetworkInterface 删除）

```json
{ "error": { "code": "CONFLICT", "message": "父资源存在活跃子资源，无法删除",
  "details": [ { "row": null, "field": null, "code": "ACTIVE_CHILDREN_EXIST",
    "message": "资源仍存在活跃子资源，无法删除" } ] } }
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定** |
| `details[].code` | `"ACTIVE_CHILDREN_EXIST"` | **稳定**：机器可读判别值 |
| `details[].field` | `null`（资源级冲突，无单一字段） | 稳定 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约** |

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

### 4.2 本契约**不含**的唯一性冲突

本资源**无已确认唯一性规则**（NQ-2 未确认），因此本契约**不存在** `409 CONFLICT` + `details[].code = "DUPLICATE"` 的分支。任何实现都**不得**为 `name` 引入唯一性校验、唯一索引或该错误码。

> 补充：宿主不存在 / 已删的 FK 违规（`23503`）经**既有通用** `sqlstate.py` 映射返回 `409 CONFLICT` + `details[].code = "REFERENCE"`；该路径在产品路径下不可达，不为本资源另立映射。

---

## 5. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（ADR-0005）。
- 认证成功即可执行全部操作；**不需要**任何角色 / 权限（V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点均位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 6. 并发与一致性语义

1. **创建对宿主加共享锁**：`POST` 在同一请求事务内对宿主 BareMetal 行执行 `SELECT … WHERE id = :bare_metal_id AND deleted_at IS NULL FOR SHARE`；未命中 → `404`。
2. **宿主删除对自身加排他锁**：`DELETE /api/bare-metals/{id}`（F002 / F014）在同一事务内对 BareMetal 行 `FOR UPDATE`，再检查活跃子资源（`BARE_METAL_ACTIVE_CHILD_CHECKS`，F004 后**同时**包含「活跃 VirtualMachine」与「活跃 NetworkInterface」检查）。
3. **并发结果**：「登记 NetworkInterface」与「删除其宿主 BareMetal」并发时，二者**恰有一个**成功；结束后不存在「宿主已删 + NIC 活跃」的记录：

   ```sql
   SELECT count(*) FROM network_interfaces nic
   JOIN bare_metals bm ON bm.id = nic.bare_metal_id
   WHERE nic.deleted_at IS NULL AND bm.deleted_at IS NOT NULL;   -- 必须为 0
   ```

4. **NetworkInterface 删除**：委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`），在同一事务内先锁目标行、再执行声明的活跃子资源检查，命中即 `409` 且不写 `deleted_at`。

---

## 7. 明确不承诺的行为（`undefined_constraints`）

以下 `name` 取值行为在 CSM 中**当前未定义**，**不得假设**（假设 6 / NQ-8）：

| 事项 | 本契约的承诺 |
|---|---|
| 长度上限 / 下限 | **无承诺**。不校验、不拒绝 |
| 首尾空白是否保留 / 去除（trim） | **无承诺**。实现不做变换；**原样存取** |
| 空字符串是否允许 | **无承诺**。既不声明其合法，也不声明其非法 |
| Unicode NFC / NFD 归一化 | **无承诺**。实现不做归一化 |
| 是否禁止 `/` 或其他字符 | **不禁止**（`/` 禁令**仅针对 Cluster 名称** R-CLUSTER-005） |
| 大小写折叠 | **不做**。本资源无唯一性，亦无大小写语义 |
| **同宿主内名称唯一性** | **无承诺，且明确不实现**（NQ-2 未确认）。不承诺拒绝重复名称，也不承诺允许；任何唯一性规则属**新增产品规则** |
| `Other` 的伴随自由文本 | **无**：`Other` 是枚举的普通合法成员；无伴随字段、无自由填写入口（NQ-4） |

**明确后果声明（是事实，不是规则）**：在现有已确认规则下，空字符串、含首尾空白的 `name` **不会**被本 API 拒绝；同宿主内同名 NetworkInterface **不会**被本 API 拒绝。这**不得**被解读为 CSM 已确认「空 `name` 合法」或「同名合法」。若用户确认需要上述任一约束，属**新增产品规则**。

前端与调用方**不得**基于上述任一未定义项编写业务分支。

---

## 8. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取 / 列表成功（含空列表）/ 更新成功 | — |
| `201` | 登记成功 | — |
| `204` | 删除成功（无响应体） | — |
| `400` | 请求格式或字段校验失败（含缺字段、非整数参数、非法枚举、未识别字段、空 PATCH） | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | 资源不存在或已被逻辑删除；引用的宿主 BareMetal 不存在或已删除（`POST` / `?bare_metal_id=`） | `NOT_FOUND` |
| `409` | 目标存在活跃子资源（当前不可达；F005 触发） | `CONFLICT` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**；前端必须按 `error.code` 分支，不解析 `message`。

---

## 9. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `GET /api/network-interfaces`：无活跃 NetworkInterface | `200`，`items == []`，`total == 0`（**Empty**） |
| `GET /api/network-interfaces?bare_metal_id={id}`：宿主存在但无活跃 NetworkInterface | `200`，`items == []`（**Empty**） |
| `GET /api/network-interfaces?bare_metal_id={id}`：宿主不存在 / 已删 | `404` `NOT_FOUND` |
| `GET /api/network-interfaces/{id}`：不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `PATCH /api/network-interfaces/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `DELETE /api/network-interfaces/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `POST /api/network-interfaces`：引用的宿主 BareMetal 不存在 / 已删 | `404` `NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

## 10. 明确不在本契约中（非目标）

- Cluster 的端点与删除（权威正文：`docs/api/f001-cluster.md` / `docs/api/f014-soft-delete.md`）。
- BareMetal 的端点与删除（权威正文：`docs/api/f002-bare-metal.md`）。
- Cluster 视角别名与关联查询视图（F009 / F010）；F010 **必须复用**本契约的 `?bare_metal_id=` 能力，不得另写一份过滤。
- **NetworkInterface 的状态**（Q-002=B）。
- IP 地址字段 / 端点 / 表 / `cluster_id` 反规范化列 / `IPAddress → NetworkInterface` 绑定（F005）。
- **MAC / MAC 地址 / 速率 / MTU / 光模块 / 端口号**等未确认字段（§23）。
- **VM / Container / Cluster / Service 作为 NIC 载体**（NQ-1 未确认）；不提供载体类型选择器。
- 自动资产发现 / 外部平台同步 / 外部平台 id / 凭据（§23）。
- NIC `name` 同宿主唯一性（NQ-2），以及任何 `409 DUPLICATE` 分支。
- `name` 重命名与父绑定变更（NQ-3）、`by-name` 别名、`name` 的最小字符约束（NQ-8）。
- 物理删除、Undelete / Restore / 回收站 / 已删资源查看 / 批量删除（R-DELETE-001/003；ADR-0004）。
- Excel 批量导入（F011）、审计 / 历史 / 导出、认证 / 会话端点（F013）。
- API versioning、游标分页（无需求）。

GIT: NONE
