# F002 API 契约 — BareMetal 登记与管理

> Status: **READY**
> Feature: F002（E01，P0）
> Author Role: architect
> Date: 2026-09-16
> Source: `docs/api/api-conventions.md`（`READY`）、`docs/architecture/adr/adr-0002-database-selection-and-uniqueness.md`、`adr-0003-resource-identity-and-api-contract.md`、`adr-0004-soft-delete-and-uniqueness-release.md`（均 `ACCEPTED`）、`docs/architecture/f002-bare-metal-handoff.md`、`docs/architecture/f014-soft-delete-handoff.md`、`docs/product/handoffs/f002-bare-metal.md`
> 本文件是 F002 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **BareMetal 资源**的产品 API，共 **5 个端点**（§3）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty / Not Found 语义、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件**不重复定义**，只做 BareMetal 资源上的具体化。
3. BareMetal **必属恰好一个 Cluster**（R-BM-001，N:1 mandatory）；**无** DataCenter / 园区 / 机房 / 机柜 / U 位等上级或位置（§6、§13）；**无**自动发现 / 外部同步（§23）。
4. BareMetal 是 V1 **唯一有状态资源**；`status` 取值集合为**封闭集合** `{IDLE, ALLOC, DOWN, UNKNOWN}`（R-BM-003），新建默认 `IDLE`（R-BM-004），永不为空（R-BM-005），人工维护（R-BM-006）。
5. R-BM-007 硬件字段 `vendor / model / serial_number / cpu / memory / gpu / storage` 全部**可选、纯文本、允许 `null`**；`serial_number` **不参与唯一性**。
6. `hostname` 的长度 / 首尾空白 / 空字符串 / 非法字符等属**未定义约束**：本契约**不承诺其行为**（§7）。
7. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无角色 / 权限 / RBAC**（ADR-0005）。
8. 本契约**不包含** Cluster CRUD（`docs/api/f001-cluster.md`）、Cluster 删除（`docs/api/f014-soft-delete.md`）或 Cluster 视角别名 `GET /api/clusters/by-name/{name}/bare-metals`（F009）。F002 **不提供**全局 `by-name` 别名（PROPOSED-1；ADR-0003 §2 未授予）。

---

## 2. BareMetal 资源表示

所有返回单个 BareMetal 的端点（§3.1、§3.3、§3.4）使用**同一个对象结构**：

```json
{
  "id": 1,
  "cluster_id": 3,
  "hostname": "cn001",
  "status": "IDLE",
  "vendor": null,
  "model": null,
  "serial_number": null,
  "cpu": null,
  "memory": null,
  "gpu": null,
  "storage": null,
  "created_at": "2026-09-16T10:00:00Z",
  "updated_at": "2026-09-16T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）。写操作一律使用该值 |
| `cluster_id` | integer | 否 | 所属 Cluster 的 `id`（R-BM-001，必选） |
| `hostname` | string | 否 | 主机名，同 Cluster 内区分机器（R-BM-002）；原样存取，不做 trim / 归一化 |
| `status` | string（枚举） | 否 | `IDLE` / `ALLOC` / `DOWN` / `UNKNOWN`（R-BM-003）；永不为 `null`（R-BM-005） |
| `vendor` | string | **是** | R-BM-007，未登记为 `null` |
| `model` | string | **是** | R-BM-007，未登记为 `null` |
| `serial_number` | string | **是** | R-BM-007；**不参与唯一性** |
| `cpu` | string | **是** | R-BM-007，纯文本不拆分 |
| `memory` | string | **是** | R-BM-007，纯文本不拆分 |
| `gpu` | string | **是** | R-BM-007，纯文本不拆分 |
| `storage` | string | **是** | R-BM-007，纯文本不拆分 |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间（应用层维护；不是并发控制依据） |

**该字段集合是封闭的**：

- 不存在 `deleted_at`（不对外暴露，`api-conventions.md` §4）；
- 不存在 DataCenter / 园区 / 机房 / 机柜 / U 位等上级或位置字段（§6、§13）；
- 不存在自动发现 / 外部平台同步相关字段（§23）；
- 不存在 NIC / IP / VM / Container / Service 相关字段。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递，不得假设固定时区偏移量，也不得把字符串解析结果用于业务判断。

---

## 3. 端点

### 3.1 `POST /api/bare-metals` — 登记 BareMetal

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/bare-metals` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**（`Content-Type: application/json`）

```json
{
  "cluster_id": 3,
  "hostname": "cn001",
  "status": "IDLE",
  "vendor": "Dell",
  "model": "R750",
  "serial_number": "SN-001",
  "cpu": "2 x Xeon 6338",
  "memory": "512 GB",
  "gpu": "4 x A100 80G",
  "storage": "2 x 3.84TB NVMe"
}
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `cluster_id` | integer | **是** | 否 | 父 Cluster 的 `id`；必须存在且活跃（R-BM-001） |
| `hostname` | string | **是** | 否 | 同 Cluster 内唯一、大小写敏感（R-BM-002）；**不校验长度 / 首尾空白 / 空串 / 字符规则**（§7） |
| `status` | string（枚举） | 否 | 否 | 缺省 `IDLE`（R-BM-004）；提供时必须在封闭集合内（R-BM-003） |
| `vendor` | string | 否 | 是 | R-BM-007；不提供时为 `null` |
| `model` | string | 否 | 是 | R-BM-007 |
| `serial_number` | string | 否 | 是 | R-BM-007；不参与唯一性 |
| `cpu` | string | 否 | 是 | R-BM-007 |
| `memory` | string | 否 | 是 | R-BM-007 |
| `gpu` | string | 否 | 是 | R-BM-007 |
| `storage` | string | 否 | 是 | R-BM-007 |

- 未识别字段 → `400 VALIDATION_ERROR`（请求 schema 封闭）。
- 硬件字段缺省 / `null` 均存为 `null`，响应中**返回 `null` 而非省略**（`api-conventions.md` §4）。

**Response 201**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 缺少 `hostname`（含 `{}`）/ 非字符串 | `400` | `VALIDATION_ERROR` | `"hostname"` | 非契约 |
| 缺少 `cluster_id` / 非整数 | `400` | `VALIDATION_ERROR` | `"cluster_id"` | 非契约 |
| `cluster_id` 引用**不存在或已逻辑删除**的 Cluster | `404` | `NOT_FOUND` | — | —（`details == []`） |
| 同 Cluster 内已存在**活跃**同名 `hostname`（大小写敏感） | `409` | `CONFLICT` | `"hostname"` | `"DUPLICATE"` |
| `status` 提供但不在封闭集合内（含 `null` / 空串 / `RUNNING` / `idle`） | `400` | `VALIDATION_ERROR` | `"status"` | `"INVALID"` 或非契约 |
| 未识别字段 | `400` | `VALIDATION_ERROR` | 该字段名 | 非契约 |
| 未认证 | `401` | `UNAUTHENTICATED` | — | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- **引用不存在 / 已删 Cluster 返回 `404 NOT_FOUND`**（ADR-0004 §5 创建协议；`api-conventions.md §7` 的父资源不存在语义）。该判定在同一事务内以「对父 Cluster 行取 `FOR SHARE` 并确认 `deleted_at IS NULL`」实现；未命中即拒绝，**非 5xx**。
- 若同名 `hostname` 属于**已逻辑删除**的 BareMetal（同一 Cluster），本次登记**成功**（`201`，R-DELETE-006）。

**Empty / Not Found 语义**：不适用（单资源写操作）。

**并发语义**：登记对父 Cluster 行取共享锁；与 Cluster 逻辑删除并发时，二者恰有一个成功（见 §6）。

---

### 3.2 `GET /api/bare-metals` — 列出活跃 BareMetal

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/bare-metals` |
| Path parameter | 无 |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50）、`cluster_id`（integer，可选） |
| 认证 | **必需**（§5） |

**语义**

- 未提供 `cluster_id`：返回系统中全部活跃 BareMetal。
- 提供 `cluster_id`：**按 Cluster 限定**返回该 Cluster 的活跃 BareMetal（R-CLUSTER-004 的 F002 侧；供 F009 复用）。
  - Cluster **不存在或已逻辑删除** → `404 NOT_FOUND`；
  - Cluster **存在但无活跃 BareMetal** → `200` + `items == []`（**Empty**）。
- 已逻辑删除的 BareMetal **不出现**在 `items`，也不计入 `total`（R-DELETE-002）。

**Response 200**

```json
{
  "items": [
    {
      "id": 1, "cluster_id": 3, "hostname": "cn001", "status": "IDLE",
      "vendor": null, "model": null, "serial_number": null,
      "cpu": null, "memory": null, "gpu": null, "storage": null,
      "created_at": "2026-09-16T10:00:00Z", "updated_at": "2026-09-16T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

- `items`：`BareMetal` 对象数组（§2），按 `id` 升序。
- `total`：**活跃** BareMetal 总数（受 `cluster_id` 过滤时为该过滤域内的活跃数，不受本页限制）。

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
| 无活跃 BareMetal（未给 `cluster_id`） | `200`，`items == []`，`total == 0`（**Empty**） |
| `cluster_id` 存在但无活跃 BareMetal | `200`，`items == []`（**Empty**） |
| `cluster_id` 不存在或已逻辑删除 | `404 NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004；`api-conventions.md` §7）。

---

### 3.3 `GET /api/bare-metals/{bare_metal_id}` — 按 id 读取 BareMetal

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/bare-metals/{bare_metal_id}` |
| Path parameter | `bare_metal_id`（integer） |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Response 200**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `bare_metal_id` 非整数 | `400` | `VALIDATION_ERROR` | `"bare_metal_id"` |
| `bare_metal_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：`404` **同时**覆盖「不存在」与「已被逻辑删除」，两者**不做区分**（`api-conventions.md` §6）。

---

### 3.4 `PATCH /api/bare-metals/{bare_metal_id}` — 更新状态 / 硬件字段

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/api/bare-metals/{bare_metal_id}` |
| Path parameter | `bare_metal_id`（integer） |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**（部分更新）

```json
{ "status": "ALLOC", "gpu": "8 x H100 80G", "memory": null }
```

**可变字段（封闭集合）**：`status` + R-BM-007 七字段 `vendor / model / serial_number / cpu / memory / gpu / storage`。

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `status` | string（枚举） | 否 | 提供时必须在封闭集合内（R-BM-003）；**不得为 `null`**（R-BM-005） |
| `vendor` … `storage` | string | 是 | 提供 `null` 表示清空该字段；缺省表示不修改 |

**不可变字段**：`id`、`cluster_id`、`hostname`、`created_at`、`deleted_at` **不接受**修改（`hostname` / `cluster_id` 的登记后可变性未确认，见 Product Handoff NQ-1 / PROPOSED-3；F002 不提供）。请求体中出现不可变字段或任何未识别字段 → `400 VALIDATION_ERROR`。

**关键语义**

- 请求体**至少**需包含一个可变字段；空 body（`{}`）→ `400 VALIDATION_ERROR`。
- 未提供的字段保持不变；提供 `null` 的硬件字段被清空。
- 修改 `status` 后，后续列表 / 详情读取返回同一值（R-BM-006）。
- `hostname` 唯一性在更新路径无需处理（不可变）。
- 本资源无乐观锁；并发更新为**最后提交生效**；`updated_at` **不是**并发控制依据。

**Response 200**：§2 的单对象结构，`updated_at` 为更新后的值；`id`、`created_at`、`cluster_id`、`hostname` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 请求体含未识别字段（含 `hostname` / `cluster_id` / `id` / `deleted_at`） | `400` | `VALIDATION_ERROR` | 该字段名 | 非契约 |
| 请求体无可变字段（含 `{}`） | `400` | `VALIDATION_ERROR` | — | 非契约 |
| `status` 提供为 `null` / 非字符串 / 不在封闭集合内 | `400` | `VALIDATION_ERROR` | `"status"` | `"INVALID"` 或非契约 |
| 硬件字段非字符串（且非 `null`） | `400` | `VALIDATION_ERROR` | 该字段名 | 非契约 |
| 目标 `bare_metal_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | — | — |
| `bare_metal_id` 非整数 | `400` | `VALIDATION_ERROR` | `"bare_metal_id"` | 非契约 |
| 未认证 | `401` | `UNAUTHENTICATED` | — | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 上述 `400` / `404` 情形**不得产生任何写入**。
- 状态约束由数据库 `ck_bare_metals_status` 作为**最终权威**；应用层预检给出字段级 `400`；若预检被绕过，`23514` 经通用映射返回 `400 VALIDATION_ERROR`（**永不返回 500**）。

**Empty / Not Found 语义**：不适用（单资源写操作）。

---

### 3.5 `DELETE /api/bare-metals/{bare_metal_id}` — 逻辑删除 BareMetal

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/api/bare-metals/{bare_metal_id}` |
| Path parameter | `bare_metal_id`（integer） |
| Query parameter | 无 |
| Request body | 无（**不定义**；客户端不得发送请求体） |
| 认证 | **必需**（§5） |

**Response 204**

- 无响应体。
- 目标 BareMetal 的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新；该行**仍物理存在**（R-DELETE-001）。
- 删除**只修改目标行**，不级联、不修改任何其他行（R-DELETE-005）。
- 已删资源不再占用正常业务唯一性；同一 Cluster 内同 `hostname` 可重新登记（R-DELETE-006）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `bare_metal_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "bare_metal_id", "code": "INVALID", ... }]` |
| `bare_metal_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| 目标 BareMetal 存在**活跃**子资源 | `409` | `CONFLICT` | `[{ "field": null, "row": null, "code": "ACTIVE_CHILDREN_EXIST", ... }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- `404` 同时覆盖「不存在」与「已被逻辑删除」，两者不区分；重复删除同一 `id` 返回 `404`。
- `409` **不产生任何写入**：目标行 `deleted_at` 仍为空。
- 当前 BareMetal **没有**活跃子资源（NIC / VM / Container / Service 表尚不存在），故 `409` 在本 Feature 内**不可达**；该分支由 F002 建立的 `BARE_METAL_ACTIVE_CHILD_CHECKS` 声明点承接（当前显式空元组），F004 / F006 / F007 / F008 落地时追加检查（Product Handoff NQ-7）。**不得**因此认为「BareMetal 永远无子资源」。

**不提供的能力**

- **不提供** `DELETE /api/bare-metals/by-name/...`（`by-name` 仅只读别名且 F002 不提供任何 `by-name`；写操作一律走 `id`）。
- **不提供** 批量删除 / 条件删除 / 恢复 / 查看已删资源。

---

## 4. 错误信封

本资源复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 的实现。**不另立一套。**

### 4.1 `409 CONFLICT` — 同 Cluster 活跃 hostname 重复

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "同一 Cluster 内 hostname 已存在",
    "details": [
      { "field": "hostname", "code": "DUPLICATE", "message": "同一 Cluster 内已存在活跃的同名 hostname" }
    ]
  }
}
```

### 4.2 `409 CONFLICT` — 父资源存在活跃子资源（BareMetal 删除）

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "父资源存在活跃子资源，无法删除",
    "details": [
      { "row": null, "field": null, "code": "ACTIVE_CHILDREN_EXIST", "message": "资源仍存在活跃子资源，无法删除" }
    ]
  }
}
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定**（`api-conventions.md` §6） |
| `details[].code` | `"DUPLICATE"` / `"ACTIVE_CHILDREN_EXIST"` | **稳定**：机器可读判别值 |
| `details[].field` | 唯一性冲突为 `"hostname"`；父子冲突为 `null` | 稳定 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约**，可随文案调整 |

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

---

## 5. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（R-AUTH-001/002；ADR-0005）。
- 认证成功即可执行全部操作；**不需要**任何角色 / 权限（R-AUTH-003；V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点均位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 6. 并发与一致性语义

1. **创建对父加共享锁**：`POST` 在同一请求事务内对父 Cluster 行执行 `SELECT … WHERE id = :cluster_id AND deleted_at IS NULL FOR SHARE`；未命中 → `404`。
2. **删除对父加排他锁**：`DELETE /api/clusters/{id}`（F014）在同一事务内对 Cluster 行 `FOR UPDATE`，再检查活跃 BareMetal（`CLUSTER_ACTIVE_CHILD_CHECKS`）。
3. **并发结果**：「登记 BareMetal」与「删除其 Cluster」并发时，二者**恰有一个**成功；结束后不存在「父已删 + 子活跃」的记录：
   ```sql
   SELECT count(*) FROM bare_metals bm
   JOIN clusters c ON c.id = bm.cluster_id
   WHERE bm.deleted_at IS NULL AND c.deleted_at IS NOT NULL;   -- 必须为 0
   ```
4. **BareMetal 删除**：委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`），在同一事务内先锁目标行、再执行声明的活跃子资源检查，命中即 `409` 且不写 `deleted_at`。

---

## 7. 明确不承诺的行为（`undefined_constraints`）

以下 `hostname` 取值行为在 CSM 中**当前未定义**，**不得假设**（Product Handoff 假设 5 / NQ-4）：

| 事项 | 本契约的承诺 |
|---|---|
| 长度上限 / 下限 | **无承诺**。不校验、不拒绝 |
| 首尾空白是否保留 / 去除（trim） | **无承诺**。实现不做变换；`hostname` **原样存取** |
| 空字符串是否允许 | **无承诺**。本契约既不声明其合法，也不声明其非法 |
| Unicode NFC / NFD 归一化 | **无承诺**。实现不做归一化 |
| 是否禁止 `/` 或其他字符 | **不禁止**（R-CLUSTER-005 的 `/` 禁令**仅针对 Cluster 名称**，不适用于 BareMetal `hostname`） |
| 大小写折叠 | **不做**：仅在**唯一性**上确认大小写敏感（R-BM-002、§22） |
| `serial_number` 唯一性 | **无**：既不全局唯一，也不按 Cluster 唯一（R-BM-007） |

**明确后果声明（是事实，不是规则）**：在现有已确认规则下，空字符串、含首尾空白的 `hostname` **不会**被本 API 拒绝。这**不得**被解读为 CSM 已确认「空 hostname 合法」。若用户确认需要拒绝空串 / 空白 / 超长（Product Handoff PROPOSED-4），属**新增产品规则**，将带来契约与数据库的增量变更。

前端与调用方**不得**基于上述任一未定义项编写业务分支（例如信任 `hostname` 非空、或依赖其已被 trim）。

---

## 8. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取 / 列表成功（含空列表）/ 更新成功 | — |
| `201` | 登记成功 | — |
| `204` | 删除成功（无响应体） | — |
| `400` | 请求格式或字段校验失败（含缺字段、非整数参数、非法 `status`、未识别字段、空 PATCH） | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | 资源不存在或已被逻辑删除；引用的父 Cluster 不存在或已删除（`POST` / `?cluster_id=`） | `NOT_FOUND` |
| `409` | 同 Cluster 活跃 hostname 重复；父资源存在活跃子资源 | `CONFLICT` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态，无授权判断；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**；前端必须按 `error.code` 分支，不解析 `message`。

---

## 9. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `GET /api/bare-metals`：无活跃 BareMetal | `200`，`items == []`，`total == 0`（**Empty**） |
| `GET /api/bare-metals?cluster_id={id}`：Cluster 存在但无活跃 BareMetal | `200`，`items == []`（**Empty**） |
| `GET /api/bare-metals?cluster_id={id}`：Cluster 不存在 / 已删 | `404` `NOT_FOUND` |
| `GET /api/bare-metals/{bare_metal_id}`：不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `PATCH /api/bare-metals/{bare_metal_id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `DELETE /api/bare-metals/{bare_metal_id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `POST /api/bare-metals`：引用的 Cluster 不存在 / 已删 | `404` `NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004；`api-conventions.md` §7）。

---

## 10. 明确不在本契约中（非目标）

- Cluster 的读取 / 创建 / 更新端点（**权威正文**：`docs/api/f001-cluster.md`）。
- `DELETE /api/clusters/{id}` 与一切软删语义（**权威正文**：`docs/api/f014-soft-delete.md`）。
- **`GET /api/clusters/by-name/{cluster_name}/bare-metals`**（Cluster 视角别名，属 F009）。
- BareMetal 的**全局 `by-name` 别名**（`hostname` 仅按 Cluster 唯一，全局不可判定；ADR-0003 §2 未授予）。
- NIC / IP / VM / Container / Service 端点（F004 / F005 / F006 / F007 / F008）。
- Rack / U 位、DataCenter / 园区 / 机房等上级或位置模型（§6、§13）。
- 自动资产发现、硬件自动采集、外部平台同步（R-BM-006、R-BM-007、§23）。
- 实时状态源接入与状态自动推导（R-BM-006）。
- 硬件字段的结构化拆分、统计 / 报表 / 结构化硬件筛选（R-BM-007）。**Cluster 内关键字搜索不属于本契约**——其权威正文为 `docs/api/f018-cluster-keyword-search.md`（F018 独立只读端点），本契约不新增 `keyword` 参数。
- 物理删除、Undelete / Restore、回收站、已删资源查看、批量删除（R-DELETE-001/003；ADR-0004）。
- `hostname` / `cluster_id` 的登记后修改与跨 Cluster 迁移（未确认；Product Handoff NQ-1 / PROPOSED-3）。
- Excel 批量导入（F011）、审计 / 历史 / 导出、认证 / 会话端点（F013）。
- API versioning、游标分页（无需求）。