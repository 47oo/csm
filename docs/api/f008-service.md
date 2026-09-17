# F008 API 契约 — Service 登记与管理

> Feature: F008 ｜ Author Role: architect ｜ Status: **`READY`**
> Source: `docs/architecture/f008-service-handoff.md`、`docs/product/handoffs/f008-service.md`（AC-01~AC-54）、`docs/api/api-conventions.md`、`docs/api/f007-container.md`（载体词汇先例）、`docs/api/f014-soft-delete.md`、ADR-0002/0003/0004/0005、`requirements.md` §14/§21/§22
> 本文件是 F008 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 定义 **Service 资源**的产品 API，共 **5 个端点**（§4）。按载体限定读取通过列表端点的**成对 query 参数**表达，不新增端点。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty/Not Found、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件不重复。
3. Service **必须绑定 ≥1 个运行载体**（BareMetal / VirtualMachine / Container，R-SVC-005）；载体身份 = `(carrier_type, carrier_id)`，类型为**封闭三值集合**，字面量与 F007 一致并扩展 `CONTAINER`。
4. **不持久化** Cluster 归属：请求体 / 响应体 / 表结构 / 查询参数中**均无** `cluster_id` / `cluster` / `cluster_name`。
5. Service 在 V1 **不设状态**（Q-002=B）：无 `status` 字段 / 枚举 / 默认值 / 过滤参数 / 读写路径。
6. 6 个可选字段 `service_type / url / port / protocol / owner / description` 全部**可选、纯文本、允许 `null`、不结构化**。
7. `name` 为**必填身份标识**，在**所有当前有效 Service 范围内全局唯一**、比较**区分大小写**；已逻辑删除的 Service **释放**该唯一性。唯一性边界**不按 Cluster、不按载体、不按载体类型**。
8. **绑定在登记时一次确定、登记后不可变**（NQ-01 用户确认）。**不存在**任何解绑 / 追加 / 替换载体集合的端点或参数。
9. `name` 与 6 个可选字段的长度 / trim / 空串 / 字符 / `/` / URL 格式 / 端口数字属**未定义约束**，本契约**不承诺其行为**（§8）。`/` 禁令**仅**适用于 Cluster 名称。
10. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无 RBAC**。
11. **不提供** `by-name` 别名、`name` 重命名、restore / undelete / purge / 批量删除 / `include_deleted`、Cluster 维度过滤、Cluster → Service 视图（F010）。
12. 本契约**不修改**任何既有契约。

## 2. Service 资源表示

所有返回单个 Service 的端点（§4.1 / §4.3 / §4.4）使用**同一个对象结构**：

```json
{
  "id": 7,
  "name": "mon",
  "service_type": "自研",
  "url": "这不是一个 URL",
  "port": "8080-8090",
  "protocol": "自定义协议",
  "owner": "ops",
  "description": "第一行\n第二行",
  "carriers": [
    { "carrier_type": "BARE_METAL", "carrier_id": 3 },
    { "carrier_type": "VIRTUAL_MACHINE", "carrier_id": 5 },
    { "carrier_type": "CONTAINER", "carrier_id": 11 }
  ],
  "created_at": "2026-09-20T10:00:00Z",
  "updated_at": "2026-09-20T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）；写操作一律使用该值 |
| `name` | string | 否 | 身份标识；**全局**活跃唯一、大小写敏感；原样存取，不 trim / 不归一 |
| `service_type` | string | **是** | 未登记为 `null`；不强制分类 |
| `url` | string | **是** | 纯文本，**不**校验 URL 格式 |
| `port` | string | **是** | 纯文本，**不**校验数字 / 范围 |
| `protocol` | string | **是** | 纯文本，**不是**封闭枚举 |
| `owner` | string | **是** | 纯文本 |
| `description` | string | **是** | 纯文本（含换行不处理） |
| `carriers` | array\<CarrierRef\> | 否 | **至少 1 项**；每项 = `{carrier_type, carrier_id}`；**顺序稳定**（见下） |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间（应用层维护；**不是**并发控制依据） |

**`CarrierRef` 对象**（封闭，恰 2 字段）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `carrier_type` | string（枚举） | 是 | 封闭三值：`"BARE_METAL"` \| `"VIRTUAL_MACHINE"` \| `"CONTAINER"` |
| `carrier_id` | integer | 是 | 该类型表中的 `id`；与 `carrier_type` 共同构成载体身份 |

**`carriers` 的顺序稳定性（契约级保证）**：响应中的 `carriers` **恒按 `(carrier_type rank, carrier_id)` 升序**排列，`rank = BARE_METAL < VIRTUAL_MACHINE < CONTAINER`。该顺序**不依赖**请求顺序、插入顺序或数据库行序，因此同一 Service 的多次读取结果逐字节一致。前端可依赖该顺序，但**不得**据此实现业务语义。

**该字段集合是封闭的**（`ServiceRead` 恰 **11** 字段）：

- 不存在 `deleted_at`（不对外暴露）；
- 不存在 `status` 或任何状态字段（Q-002=B）；
- 不存在 `cluster_id` / `cluster` / `cluster_name`（归属仅由载体推导）；
- 不存在凭据 / 密钥 / 外部平台 id 字段；
- 不存在健康 / 监控 / 最后上报字段；
- 不存在 DataCenter / 园区 / 机房 / 机柜 / U 位字段。

**载体表示的固定形态**：API 层**不暴露** `bare_metal_id` / `virtual_machine_id` / `container_id` 三个原始存储列名；存储形态（`service_carriers` 三列可空 FK）由 `carrier_type` / `carrier_id` 派生。

## 3. 载体与唯一性语义（跨端点）

| 语义 | 规则 |
|---|---|
| 载体身份 | `(carrier_type, carrier_id)` 二元组；类型不同即载体不同 |
| 绑定集合语义 | **集合**：同一 Service 内不产生重复 `(carrier_type, carrier_id)`；同一请求内重复给出同一载体 → `400` |
| 载体必须存在且活跃 | 任一载体不存在 / 已逻辑删除 / 类型与标识不一致 → `404 NOT_FOUND`（`details == []`，NQ-07 裁定） |
| `name` 唯一性边界 | **全局**（跨 Cluster、跨载体、跨载体类型）；大小写敏感；软删释放 |
| `name` 重复 | `409 CONFLICT` + `details[].field == "name"` + `details[].code == "DUPLICATE"` |
| Cluster 归属 | 不持久化、不返回、不能过滤；仅能经载体推导 |
| 绑定变更 | **不提供**（NQ-01）；释放的唯一途径是逻辑删除该 Service |

## 4. 端点

### 4.1 `POST /api/services` — 登记 Service

| 项 | 值 |
|---|---|
| Method | `POST` ｜ Path `/api/services` ｜ Path/Query parameter 无 ｜ 认证 **必需** |

**Request body**

```json
{ "name": "mon",
  "carriers": [ { "carrier_type": "BARE_METAL", "carrier_id": 3 },
                { "carrier_type": "CONTAINER", "carrier_id": 11 } ],
  "service_type": "自研", "url": null, "port": null, "protocol": null,
  "owner": "ops", "description": null }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `name` | string | **是** | 否 | 全局唯一、大小写敏感；**不校验长度 / trim / 空串 / 字符**（§8） |
| `carriers` | array\<CarrierRef\> | **是** | 否 | **至少 1 项**（`min_length=1`）；空数组 / 缺失 → `400`；每项 `carrier_type` 必填且属封闭三值、`carrier_id` 必填整数 |
| `service_type` … `description` | string | 否 | 是 | 不提供或 `null` 均存为 `null`，响应返回 `null` 而非省略 |

- 请求 schema **封闭**（`extra="forbid"`，含嵌套 `CarrierRef`）。**不接受**顶层 `carrier_type` / `carrier_id`、`bare_metal_id` / `virtual_machine_id` / `container_id`、`cluster_id` / `status` / `deleted_at` / `id` 或任何未识别字段。
- **不接受**以 Cluster / NetworkInterface / IPAddress 作为载体，也不接受三值以外的 `carrier_type`（AC-09）。

**Response 201**：§2 的 `ServiceRead`。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 缺少 `name` / 非字符串 | `400` | `VALIDATION_ERROR` | `"name"` | `"INVALID"` |
| 缺少 `carriers` / 空数组 | `400` | `VALIDATION_ERROR` | `"carriers"` | `"INVALID"` |
| `carrier_type` 非字符串 / 不在封闭三值 | `400` | `VALIDATION_ERROR` | `"carriers.<i>.carrier_type"` | `"INVALID"` |
| 缺少 `carrier_id` / 非整数 | `400` | `VALIDATION_ERROR` | `"carriers.<i>.carrier_id"` | `"INVALID"` |
| **同一请求内重复给出同一 `(carrier_type, carrier_id)`** | `400` | `VALIDATION_ERROR` | `"carriers"` | `"DUPLICATE"` |
| 未识别字段（含 `id` / 顶层 `carrier_type` / `bare_metal_id` / `cluster_id` / `status` / `deleted_at`） | `400` | `VALIDATION_ERROR` | 该字段名（嵌套为 `carriers.<i>.<name>`） | `"INVALID"` |
| **任一载体不存在 / 已逻辑删除 / 类型与标识不一致** | `404` | `NOT_FOUND` | — | —（`details == []`） |
| `name` 已存在活跃同名 Service（大小写敏感） | `409` | `CONFLICT` | `"name"` | `"DUPLICATE"` |
| 未认证 | `401` | `UNAUTHENTICATED` | — | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**（无 Service 行、无绑定行）。
- `carriers.<i>` 的 `<i>` 为请求数组下标（0 起）。
- 实现：同一事务内按 §7.1 的**全序**对每个载体行执行 `SELECT … WHERE id = :id AND deleted_at IS NULL FOR SHARE`；任一未命中 → `404`（非 5xx、无写入）。
- 若同名 `name` 属于**已逻辑删除**的 Service，本次登记**成功**（`201`）。

### 4.2 `GET /api/services` — 列出活跃 Service（含按载体限定读取）

| 项 | 值 |
|---|---|
| Method | `GET` ｜ Path `/api/services` ｜ 认证 **必需** |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50）、`carrier_type`（string，可选）、`carrier_id`（integer，可选） |

**语义**

- **未提供** `carrier_type` / `carrier_id`：返回全部活跃 Service。
- **同时提供**：**按载体限定**返回绑定到该载体的活跃 Service —— 这是 R-QUERY-003 的 **canonical 能力**，**F010 必须复用（不得另写过滤）**。
  - 载体不存在 / 已逻辑删除 / 类型与标识不一致 → `404 NOT_FOUND`；
  - 载体存在但无活跃 Service 绑定 → `200` + `items == []` + `total == 0`（**Empty**）；
  - 对三种载体类型**均**成立。
- **仅提供其一** → `400 VALIDATION_ERROR`。
- 已逻辑删除的 Service 不出现在 `items`，也不计入 `total`。

**Response 200**

```json
{ "items": [ { "id": 7, "name": "mon", "service_type": "自研", "url": null, "port": null,
  "protocol": null, "owner": "ops", "description": null,
  "carriers": [ { "carrier_type": "BARE_METAL", "carrier_id": 3 } ],
  "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-20T10:00:00Z" } ],
  "total": 1, "page": 1, "page_size": 50 }
```

- `items`：`ServiceRead` 数组，按 `id` 升序；每项的 `carriers` 按 §2 的稳定顺序。
- `total`：**活跃** Service 总数（受载体过滤时为该过滤域内的活跃数）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| `carrier_type` 非字符串 / 不在封闭三值 | `400` | `VALIDATION_ERROR` | `"carrier_type"` |
| `carrier_id` 非整数 | `400` | `VALIDATION_ERROR` | `"carrier_id"` |
| **仅提供 `carrier_type` 或仅提供 `carrier_id`** | `400` | `VALIDATION_ERROR` | 缺失的那一个 |
| 载体不存在 / 已逻辑删除 / 类型与标识不一致 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Empty / Not Found 语义**

| 情形 | 响应 |
|---|---|
| 无活跃 Service（未给载体过滤） | `200`，`items == []`，`total == 0`（**Empty**） |
| 载体存在但无活跃 Service 绑定 | `200`，`items == []`（**Empty**） |
| 载体不存在 / 已逻辑删除 / 类型与标识不一致 | `404 NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

### 4.3 `GET /api/services/{service_id}` — 按 id 读取

| 项 | 值 |
|---|---|
| Method | `GET` ｜ Path `/api/services/{service_id}` ｜ Path parameter `service_id`（integer） ｜ 认证 **必需** |

**Response 200**：§2 的 `ServiceRead`（含**全部**载体绑定，无遗漏、无截断）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `service_id` 非整数 | `400` | `VALIDATION_ERROR` | `"service_id"` |
| `service_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

### 4.4 `PATCH /api/services/{service_id}` — 更新可选字段

| 项 | 值 |
|---|---|
| Method | `PATCH` ｜ Path `/api/services/{service_id}` ｜ Path parameter `service_id`（integer） ｜ 认证 **必需** |

**Request body**（部分更新）

```json
{ "port": "8080", "owner": "ops2", "description": null }
```

**可变字段（封闭集合，恰 6 个）**：`service_type`、`url`、`port`、`protocol`、`owner`、`description`。

**不可变字段**：`id`、`name`、`carriers`（载体绑定）、`carrier_type` / `carrier_id`、`created_at`、`deleted_at`，以及任何未识别字段 → `400 VALIDATION_ERROR`。

**关键语义**

- 请求体**至少**需包含一个可变字段；空 body（`{}`）→ `400`。
- 未提供的字段保持不变；提供 `null` 的字段被清空。
- 无乐观锁；并发更新为**最后提交生效**；`updated_at` **不是**并发控制依据。
- **无状态**：`status` 既非可变字段，也不得出现在请求体中（`400`）。
- 6 个可选字段**不参与**任何唯一性。
- **载体绑定不可变且无替代写路径**：不存在 `PATCH`/`PUT`/`POST …/carriers`/解绑端点（AC-48）。

**Response 200**：§2 的 `ServiceRead`；`id`、`name`、`carriers`、`created_at` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| 含未识别 / 不可变字段（含 `name` / `carriers` / `carrier_type` / `carrier_id` / `id` / `deleted_at` / `cluster_id` / `status`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| 请求体无可变字段（含 `{}`） | `400` | `VALIDATION_ERROR` | — |
| 可选字段非字符串（且非 `null`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| 目标不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | — |
| `service_id` 非整数 | `400` | `VALIDATION_ERROR` | `"service_id"` |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

### 4.5 `DELETE /api/services/{service_id}` — 逻辑删除

| 项 | 值 |
|---|---|
| Method | `DELETE` ｜ Path `/api/services/{service_id}` ｜ Request body **无**（客户端不得发送） ｜ 认证 **必需** |

**Response 204**

- 无响应体。
- 目标 Service 的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新；该行**仍物理存在**。
- 删除**只修改目标行**，不级联；其**载体绑定行不被修改、不被删除**（绑定行的活跃性由 `services.deleted_at` 派生），所有载体资源行逐字段不变（AC-38）。
- 删除后：该 `name` 释放全局唯一性（可重新登记）；其原载体**不再**因该 Service 被拦截（AC-39）。
- 删除委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`），显式传入 `SERVICE_ACTIVE_CHILD_CHECKS`（当前显式空元组——Service 无子资源）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `service_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "service_id", "code": "INVALID" }]` |
| 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- `404` 同时覆盖「不存在」与「已被逻辑删除」；重复删除同一 `id` → `404`。
- Service 删除**不产生 `409`**（无子资源）。
- **不提供**：`by-name` 删除、批量删除、条件删除、恢复、查看已删资源。

## 5. 错误信封

复用 `docs/api/api-conventions.md` §5 的统一信封与既有 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 实现，不另立一套。

### 5.1 `409 CONFLICT` — 全局活跃 `name` 重复

```json
{ "error": { "code": "CONFLICT", "message": "Service 名称已存在",
  "details": [ { "field": "name", "code": "DUPLICATE",
    "message": "已存在活跃的同名 Service" } ] } }
```

### 5.2 `409 CONFLICT` — 载体存在活跃 Service（载体删除，本 Feature 起可达）

```json
{ "error": { "code": "CONFLICT", "message": "父资源存在活跃子资源，无法删除",
  "details": [ { "row": null, "field": null, "code": "ACTIVE_CHILDREN_EXIST",
    "message": "资源仍存在活跃子资源，无法删除" } ] } }
```

（出现在 `DELETE /api/bare-metals/{id}`、`DELETE /api/virtual-machines/{id}`、`DELETE /api/containers/{id}` 三处；权威正文见各自契约与 `docs/api/f014-soft-delete.md`。）

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定** |
| `details[].code` | `"DUPLICATE"` / `"ACTIVE_CHILDREN_EXIST"` | **稳定**（机器可读判别值） |
| `details[].field` | 唯一性冲突为 `"name"`；父子冲突为 `null` | 稳定 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约** |

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

### 5.3 载体引用不存在 / 已删 / 类型不一致

`404 NOT_FOUND`，`details == []`。**不**为多态载体另立错误码。

### 5.4 `400 VALIDATION_ERROR` — 载荷级错误

`details[].code` 取 `"INVALID"`（字段级校验，含框架自动产生的嵌套字段路径 `carriers.<i>.<name>`）或 `"DUPLICATE"`（同一请求内重复载体）。`details[].field` 为字段路径或缺失字段名。

## 6. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（AC-53）。
- 认证成功即可执行全部操作；**不需要**任何角色 / 权限（V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

## 7. 并发与一致性语义

### 7.1 登记：多载体确定性加锁（AC-47）

1. 对请求 `carriers` 去重检查（重复 → `400`）。
2. 按 **`(carrier_type_rank, carrier_id)` 升序**排序，`rank = {BARE_METAL:0, VIRTUAL_MACHINE:1, CONTAINER:2}`。
3. 按该顺序逐载体执行：

```python
select_active(Model).where(Model.id == carrier_id).with_for_update(read=True)   # FOR SHARE（单表、无 JOIN、无 OF）
```

   未命中（不存在 / 已软删 / 类型与标识不一致）→ `404`，**在任何 INSERT 之前**抛出。

4. 再执行 `name` 全局唯一预检（命中 → `409`）。
5. 插入 1 行 `services` + N 行 `service_carriers`（同一事务），`flush`；数据库约束为最终权威。

### 7.2 载体删除对自身加排他锁

`DELETE /api/bare-metals/{id}` / `virtual-machines/{id}` / `containers/{id}` 在同一事务内对自身行 `FOR UPDATE`，再执行声明的活跃子检查；命中 → `409`，**不写 `deleted_at`**。

### 7.3 并发结果不变式（AC-46）

「登记 Service（绑定载体 X）」与「删除载体 X」并发时**恰有一个成功**；结束后下列查询**必须为 0 行**：

```sql
SELECT count(*) FROM services s
JOIN service_carriers sc ON sc.service_id = s.id
JOIN bare_metals bm ON bm.id = sc.bare_metal_id
WHERE s.deleted_at IS NULL AND bm.deleted_at IS NOT NULL;            -- 必须为 0 行

SELECT count(*) FROM services s
JOIN service_carriers sc ON sc.service_id = s.id
JOIN virtual_machines vm ON vm.id = sc.virtual_machine_id
WHERE s.deleted_at IS NULL AND vm.deleted_at IS NOT NULL;            -- 必须为 0 行

SELECT count(*) FROM services s
JOIN service_carriers sc ON sc.service_id = s.id
JOIN containers c ON c.id = sc.container_id
WHERE s.deleted_at IS NULL AND c.deleted_at IS NOT NULL;             -- 必须为 0 行
```

### 7.4 AC-49 零载体不变式（回归断言）

```sql
SELECT count(*) FROM services s
WHERE s.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM service_carriers sc WHERE sc.service_id = s.id);  -- 必须为 0 行
```

### 7.5 释放语义（AC-39 / AC-48）

- 绑定行**只在登记时 INSERT**，**永不 UPDATE / DELETE**，**无 `deleted_at`**。
- Service 软删后，其绑定行仍在，但「绑定到某载体的**活跃** Service」检查立即为假 → 该载体不再被此 Service 拦截；绑定事实作为历史保留。
- 因此**绑定写入路径恰为一条**（登记 INSERT）；「释放」是派生效果，**不产生任何写入**，也不引入第二条写 `deleted_at` 的代码路径。

### 7.6 唯一性

- 应用层 `409` 预检为体验优化；`ux_services_name_active`（partial `WHERE deleted_at IS NULL`，**无 `COLLATE`、无 `lower()`**）为**最终权威**（绕过应用层直插 → `23505`）。
- 绑定集合语义由 3 条 partial unique 保证（绕过应用层直插重复绑定 → `23505`）。
- 4 条 FK 的 `RESTRICT` 为参照完整性第二道防线（载体无物理删除路径，产品路径不触发）。

## 8. 明确不承诺的行为（`undefined_constraints`）

| 事项 | 本契约的承诺 |
|---|---|
| 长度上限 / 下限（`name` 与 6 个可选字段） | **无承诺**。不校验、不拒绝 |
| 首尾空白是否保留 / 去除（trim） | **无承诺**。实现不做变换；**原样存取** |
| 空字符串是否允许 | **无承诺**。既不声明合法也不声明非法 |
| Unicode NFC / NFD 归一化 | **无承诺**。不做归一化 |
| 是否禁止 `/` 或其他字符 | **不禁止**（`/` 禁令**仅**针对 Cluster 名称） |
| `url` 是否为合法 URL | **不要求**；纯文本 |
| `port` 是否为数字 / 范围 | **不要求**；纯文本（如 `"abc"`、`"8080-8090"` 原样存取） |
| `protocol` 是否为封闭枚举 | **不是**；纯文本 |
| 大小写折叠 | **不做**：仅在**唯一性**上确认大小写敏感；无 `lower(name)` 唯一索引 |
| 6 个可选字段的结构化拆分 | **不做**：纯文本，不拆分 / 不归一 |
| `name` 的重命名 | **不提供**（NQ-02） |
| 载体的追加 / 解除 / 替换 | **不提供**（NQ-01 用户确认） |

**明确后果声明（是事实，不是规则）**：在现有已确认规则下，空字符串、含首尾空白的 `name` 与任意 `url` / `port` **不会**被本 API 拒绝。这**不得**被解读为 CSM 已确认「空 `name` 合法」或「任意 URL / 端口合法」。若要拒绝，属**新增产品规则**。

## 9. 逐条 AC → 端点 / 断言映射（AC-01~AC-54）

> 保证主体：**契约** = HTTP 层协议；**Backend** = 应用逻辑；**DB** = 数据库约束 / 索引；**Guard** = 可失败静态 / 结构测试；**测试** = 端到端 / 并发；**前端** = UI。**全部 54 条可实现，无一条需修改产品需求。**

| AC | 保证主体 | 端点 / 断言 |
|---|---|---|
| AC-01/02/03 | 契约 | `POST` 以 BARE_METAL / VIRTUAL_MACHINE / CONTAINER 之一为唯一载体 → `201`；`ServiceRead` 恰 11 字段；6 可选字段返 `null` |
| AC-04 | 契约 + Backend | `POST` 三载体 → `201`；响应 `carriers` 三项全在、无截断、顺序稳定 |
| AC-05/06/07 | 契约 | 缺 `name` → `400` `field=name`；缺 `carriers` / `carriers: []` → `400`；均无写入 |
| AC-08 | 契约 + Backend | 多载体中任一无效 → `404`；Service 行 0、绑定行 0；非 5xx |
| AC-09 | 契约 | Cluster / NIC / IP 或三值以外类型 → `400`（enum 封闭） |
| AC-10 | Backend | 类型与标识不一致 → 按类型分派查不到 → `404`；无写入；非 5xx（第二形式不适用，见 Handoff Open #7） |
| AC-11 | Backend | 校验在 Backend / DB；绕过 UI 结果一致；无绕过校验的写入路径 |
| AC-12 | 契约 + DB + Guard | 四个 schema 字段封闭；`services` 11 列 + `service_carriers` 5 列封闭；无 `status`/`cluster*`/凭据/健康/位置列（`deleted_at` 仅存储不暴露） |
| AC-13/14 | 契约 + Backend | 6 可选字段全缺 → `201` 各为 `null`；中文 / `"这不是一个 URL"` / `"abc"` / `"8080-8090"` / `"自定义协议"` / 含换行长文本原样往返 |
| AC-15 | Guard + Backend | 7 字段无长度 / trim / 空串 / 字符 / 格式约束；`services` 恰 1 约束（PK）、无 CHECK；空串与首尾空白 `name` 不被拒绝 |
| AC-16 | 契约 + DB | 详情返回**全部**载体绑定，数量与登记一致 |
| AC-17 | DB（partial unique） | 载体 X 被 S1、S2 先后绑定 → 均 `201`；按 X 反查返回两条 |
| AC-18 | Backend + DB + 测试 | 同名活跃 Service 行数恰 1；载体跨 ≥2 Cluster；Cluster 集合 = 各载体归属并集（由载体推导，**不得**按 Cluster 复制） |
| AC-19 | Backend | 对每个载体反查含 S；对无关载体 C′ 不含；跨 ≥2 Cluster 同时成立 |
| AC-20/21 | 契约 + Guard + DB | 请求 / 响应 / 两表列 / 查询参数无 `cluster_id`/`cluster`/`cluster_name`；无读写 Cluster 归属的路径；详情只暴露 `carriers` |
| AC-22 | 契约 + Backend | 跨 Cluster 载体上同名活跃 Service → `409`，`field=name`；活跃记录仍 1 |
| AC-23/24 | DB（独立表 / 索引） | Service 全局唯一与 Container 载体内唯一并存互不削弱；与 Cluster / BM / VM / Container 的名称唯一性各自独立 |
| AC-25/26/27 | DB | `mon` 与 `MON` 共存；绕应用层直插重复活跃名 → `23505`；软删后可重登记，旧行 `deleted_at` 未改写 |
| AC-28 | 契约 + Guard + DB | 请求 / 响应 / 两表 / 端点无 `status` 字段、枚举、默认值、过滤参数 |
| AC-29/30 | 契约 | 列表 `200` + 空信封非 404；不存在 / 已删 `id` → `404`（不区分） |
| AC-31/32 | 契约 + Backend | 三载体类型：载体活跃但无绑定 → `200` 空集；载体不存在 / 已删 → `404`；仅给一个参数 → `400` |
| AC-33 | Backend（`active_filter`） | 预置 `deleted_at` 非空的 Service 不出现在列表 / `total` / 按载体结果；按 `id` → `404` |
| AC-34/35/36 | 契约 + DB | `PATCH` 6 字段子集 → `200`；`null` 清空；不可变 / 未识别 → `400`；`{}` → `400`；6 字段不参与唯一性 |
| AC-37/38 | 契约 + 软删服务 | `DELETE` → `204` 无体；行仍物理存在且 `deleted_at` 非空；载体行与绑定行逐字段不变 |
| AC-39 | Backend（派生失效）+ 测试 | 软删 Service 后其原载体不再因该 Service 被拦截 → 载体删除 `204`（满足其它活跃子检查前提下） |
| AC-40 | 契约 + Guard | 无 restore / undelete / purge / 批量 / `include_deleted` |
| AC-41/42/43 | Backend（检查）+ 测试 | BM / VM / Container 有活跃 Service → `DELETE` 对应载体 → `409 ACTIVE_CHILDREN_EXIST`；载体 `deleted_at` 仍 NULL；AC-43 使 `CONTAINER_ACTIVE_CHILD_CHECKS` 非空 |
| AC-44 | Guard + Backend | BM 保留 VM/NIC/Container 并追加 Service；VM 保留 Container 并追加 Service；Container 由 `()` 变非空；三者均经 `active_children=` 真实传入 |
| AC-45 | Backend + Guard | 拦截仅针对**直接绑定**；不做传递性 Service 检查；`CLUSTER_ACTIVE_CHILD_CHECKS` 保持不变 |
| AC-46 | DB + 并发测试 | §7.3 三条查询 = 0 行（真实并发） |
| AC-47 | Backend + 测试 | §7.1：同事务对每个载体 `FOR SHARE` + 确认活跃；确定性全序；任一未命中 → 拒绝且无 Service / 无绑定行 |
| AC-48 | Guard + Backend | 无解绑 / 替换 / 批量改绑端点或参数；绑定写入路径**恰一条 INSERT**；`ServiceUpdate` 不含 `carriers` |
| AC-49/50 | 测试（回归）+ 设计 | §7.4 查询 = 0 行；结构上可表达零载体但不做 DB 硬约束 / 触发器 |
| AC-51/52 | Guard + DB | 不注册 / 不修改其它资源端点；两表无位置字段；无 Cluster → Service 视图；无监控 / 健康 / 凭据 / 密钥 / 外部 id / 自动发现 / 同步的字段或端点 |
| AC-53 | 中间件 | 未认证 → `401` 且不改变数据；已认证可执行全部操作 |
| AC-54 | 前端 + 测试 | 三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`（必要时 `details[].code`）；`409`/`404`/`401` 分别处理；不实现业务守卫；登记表单仅三种载体类型且至少选一项 |

## 10. 明确不在本契约中（非目标）

- Cluster / BareMetal / VirtualMachine / Container / NetworkInterface / IPAddress 的端点（权威正文见各自契约）。
- 删除语义总则与 `DELETE /api/clusters/{id}`（`docs/api/f014-soft-delete.md`）。
- Cluster → Service 视图与关联聚合（F010）；F010 **必须复用**本契约 §4.2 的按载体限定读取能力。
- `Service` 状态（Q-002=B）、`service.cluster_id` 或任何 Cluster 维度字段 / 过滤。
- 凭据引用、健康信息、监控 / 健康检查接入、自动发现 / 服务发现 / 外部同步。
- 绑定变更 / 解绑 / 载体替换（NQ-01 用户确认不做）。
- `name` 重命名、`by-name` 别名、`name` 与 6 字段的最小字符约束。
- 物理删除、Undelete / Restore / 回收站 / 已删资源查看 / 批量删除。
- DataCenter / 位置模型、复杂 RBAC、Excel 导入（F011）、审计 / 历史 / 导出 / 统计 / 标签 / 批量操作。
- API versioning、游标分页（无需求）。

GIT: NONE
