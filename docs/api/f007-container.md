# F007 API 契约 — Container 登记与管理

> Status: **READY**
> Feature: F007（E03，P1，`depends_on: [F006, F002]` 均 DONE）
> Author Role: architect
> Source: `docs/architecture/adr/adr-0002..0005`（均 `ACCEPTED`）、`docs/api/api-conventions.md`（`READY`）、`docs/architecture/f007-container-handoff.md`、`docs/api/f002-bare-metal.md`、`f004-network-interface.md`、`f005-ip-address.md`、`f006-virtual-machine.md`、`f014-soft-delete.md`、`docs/product/handoffs/f007-container.md`
> 本文件是 F007 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **Container 资源**的产品 API，共 **5 个端点**（§4；按载体限定读取是通过 query 参数表达的同一列表端点，不新增端点）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty / Not Found 语义、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件不重复定义。
3. Container **必属恰好一个运行载体**，载体为 **BareMetal 或 VirtualMachine 二选一**（R-CONTAINER-002）。Cluster 归属**只能由载体推导**，**不持久化**：请求体、响应体、表结构、查询参数**均无** `cluster_id` / `cluster` / `cluster_name`。
4. Container 在 V1 **不设状态**（Q-002=B）：无 `status` 字段、枚举、默认值、过滤参数或读写路径。
5. R-CONTAINER-004 可选字段 `image / cpu / memory / owner` 全部**可选、纯文本、允许 `null`、不结构化**。
6. `name` 为**必填身份标识**，**同一载体内唯一**、不同载体可重名、比较**区分大小写**（R-CONTAINER-003、§22）；已逻辑删除的 Container **不再占用**该唯一性（R-DELETE-006）。载体身份 = `(carrier_type, carrier_id)` 二元组。
7. `name` 与四个可选字段的长度 / 首尾空白 / 空串 / 非法字符 / `/` / 格式属**未定义约束**：本契约**不承诺其行为**（§8）。
8. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无角色 / 权限 / RBAC**（ADR-0005）。
9. 本契约**不包含** Cluster / BareMetal / VM / NIC / IP / Service 端点、删除语义总则（F014）、Cluster 视角（F009）、关联聚合（F010）。不修改任何既有契约。
10. **不提供**全局 `by-name` 别名（`name` 仅载体内唯一，全局不可判定）。
11. **不提供** `name` 重命名与载体迁移（登记后不可变；NQ-1）。变更由「软删 + 重新登记」替代。
12. **不提供** restore / undelete / purge / 批量删除 / `include_deleted`。

---

## 2. Container 资源表示

所有返回单个 Container 的端点（§4.1、§4.3、§4.4）使用**同一个对象结构**：

```json
{
  "id": 11,
  "carrier_type": "BARE_METAL",
  "carrier_id": 3,
  "name": "web",
  "image": "registry/nginx:1.25",
  "cpu": "8 vCPU",
  "memory": "4G",
  "owner": "ops",
  "created_at": "2026-09-18T10:00:00Z",
  "updated_at": "2026-09-18T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）。写操作一律使用该值 |
| `carrier_type` | string（枚举） | 否 | 载体类型，封闭集合 `"BARE_METAL"` \| `"VIRTUAL_MACHINE"`（R-CONTAINER-002） |
| `carrier_id` | integer | 否 | 载体在该类型表中的 `id`；与 `carrier_type` 共同构成载体身份 |
| `name` | string | 否 | 身份标识；**同一载体内**活跃唯一、大小写敏感（R-CONTAINER-003）；原样存取，不做 trim / 归一化 |
| `image` | string | **是** | R-CONTAINER-004，未登记为 `null`；纯文本不拆分 |
| `cpu` | string | **是** | R-CONTAINER-004，纯文本不拆数量与单位 |
| `memory` | string | **是** | R-CONTAINER-004 |
| `owner` | string | **是** | R-CONTAINER-004 |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间（应用层维护；不是并发控制依据） |

**该字段集合是封闭的**（恰 **10** 字段）：

- 不存在 `deleted_at`（不对外暴露）；
- 不存在 `status` 或任何状态字段（Q-002=B）；
- 不存在 `cluster_id` / `cluster` / `cluster_name` 等 Cluster 维度字段（R-CONTAINER-002）；
- 不存在 NIC / IP / Service 相关字段；
- 不存在 K8s / Docker / Container Runtime / 自动发现 / 外部平台 id / 凭据字段（R-CONTAINER-001；§23）；
- 不存在 DataCenter / 园区 / 机房 / 机柜 / U 位等位置字段（§6、§13）。

**载体表示的固定形态**：`carrier_type` ∈ `{"BARE_METAL", "VIRTUAL_MACHINE"}` 且 `carrier_id` 必须在该类型内解析。存储层由两列可空 FK（`bare_metal_id` / `virtual_machine_id`，恰好一个非空）承载；**响应中的 `carrier_type` / `carrier_id` 由非空列派生，不由客户端写入**。API 层**不暴露** `bare_metal_id` / `virtual_machine_id` 两个原始列名。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递。

---

## 3. 载体与唯一性语义（跨端点）

| 语义 | 规则 |
|---|---|
| 载体身份 | `(carrier_type, carrier_id)` 二元组；类型不同即载体不同（AC-15） |
| 恰好一个 | 请求只能表达一对 `carrier_type` + `carrier_id`；多载体（列表 / 同时给两类）在 schema 层不可表达 → `400` |
| 载体必须存在且活跃 | 载体不存在 / 已逻辑删除 / 类型与标识不一致 → `404 NOT_FOUND`（NQ-2 裁定；`details == []`） |
| `name` 唯一性边界 | **载体内**（非全局、非按 Cluster）；大小写敏感；软删释放 |
| `name` 重复 | `409 CONFLICT` + `details[].field == "name"` + `details[].code == "DUPLICATE"` |
| Cluster 归属 | 不持久化、不返回、不能过滤；仅能经载体推导 |

---

## 4. 端点

### 4.1 `POST /api/containers` — 登记 Container

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/containers` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§6） |

**Request body**

```json
{ "carrier_type": "BARE_METAL", "carrier_id": 3, "name": "web",
  "image": "registry/nginx:1.25", "cpu": "8 vCPU", "memory": "4G", "owner": "ops" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `carrier_type` | string（枚举） | **是** | 否 | `"BARE_METAL"` 或 `"VIRTUAL_MACHINE"`；其它值 → `400` |
| `carrier_id` | integer | **是** | 否 | 载体 id；必须存在且活跃（R-CONTAINER-002） |
| `name` | string | **是** | 否 | **载体内**活跃唯一、大小写敏感；**不校验长度 / trim / 空串 / 字符规则**（§8） |
| `image` … `owner` | string | 否 | 是 | R-CONTAINER-004；不提供时为 `null` |

- 请求 schema **封闭**（`extra="forbid"`）。**不接受** `bare_metal_id` / `virtual_machine_id` / `cluster_id` / `status` / `deleted_at` / `id` 或任何未识别字段 → `400 VALIDATION_ERROR`。
- **不接受**以 Cluster / Service / NIC / IP 作为载体，也不接受载体类型值以外的字符串（R-CONTAINER-002；AC-06）。
- 四个可选字段缺省 / `null` 均存为 `null`，响应中**返回 `null` 而非省略**。

**Response 201**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 缺少 `name` / 非字符串 | `400` | `VALIDATION_ERROR` | `"name"` | — |
| 缺少 `carrier_type` / 非字符串 / 不在封闭集合 | `400` | `VALIDATION_ERROR` | `"carrier_type"` | — |
| 缺少 `carrier_id` / 非整数 | `400` | `VALIDATION_ERROR` | `"carrier_id"` | — |
| 请求体表达多于一个载体（载体列表 / 同时携带 `bare_metal_id` 与 `virtual_machine_id` 或其它载体字段） | `400` | `VALIDATION_ERROR` | 该字段名 | — |
| 载体不存在 / 已逻辑删除 / 类型与标识不一致 | `404` | `NOT_FOUND` | — | —（`details == []`） |
| **载体内**已存在活跃同名 `name`（大小写敏感） | `409` | `CONFLICT` | `"name"` | `"DUPLICATE"` |
| 未识别字段 | `400` | `VALIDATION_ERROR` | 该字段名 | — |
| 未认证 | `401` | `UNAUTHENTICATED` | — | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- **引用不存在 / 已删载体返回 `404 NOT_FOUND`**（NQ-2 裁定）。实现：同一事务内按 `carrier_type` 分派对载体行执行 `SELECT … WHERE id = :carrier_id AND deleted_at IS NULL FOR SHARE`；未命中即拒绝，**非 5xx**。
- 若同名 `name` 属于**同一载体内已逻辑删除**的 Container，本次登记**成功**（`201`，R-DELETE-006）。

**并发语义**：登记对**被选中载体行**取共享锁；与载体逻辑删除并发时，二者恰有一个成功（§7）。

---

### 4.2 `GET /api/containers` — 列出活跃 Container

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/containers` |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50）、`carrier_type`（string，可选）、`carrier_id`（integer，可选） |
| 认证 | **必需**（§6） |

**语义**

- **未提供** `carrier_type` 与 `carrier_id`：返回系统中全部活跃 Container。
- **同时提供** `carrier_type` 与 `carrier_id`：**按载体限定**返回该载体的活跃 Container（R-QUERY-003 的 F007 侧 canonical 能力；**供 F010 复用**，F010 不得另写一份过滤）。
  - 载体**不存在或已逻辑删除** → `404 NOT_FOUND`；
  - 载体**存在但无活跃 Container** → `200` + `items == []`（**Empty**）。
  - 对 `BARE_METAL` 与 `VIRTUAL_MACHINE` **均**成立。
- **仅提供其一** → `400 VALIDATION_ERROR`（两个参数必须成对出现）。
- 已逻辑删除的 Container **不出现**在 `items`，也不计入 `total`。

**Response 200**

```json
{ "items": [ { "id": 11, "carrier_type": "BARE_METAL", "carrier_id": 3, "name": "web",
  "image": "registry/nginx:1.25", "cpu": "8 vCPU", "memory": "4G", "owner": "ops",
  "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z" } ],
  "total": 1, "page": 1, "page_size": 50 }
```

- `items`：`Container` 对象数组（§2），按 `id` 升序。
- `total`：**活跃** Container 总数（受载体过滤时为该过滤域内的活跃数）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| `carrier_type` 非字符串 / 不在封闭集合 | `400` | `VALIDATION_ERROR` | `"carrier_type"` |
| `carrier_id` 非整数 | `400` | `VALIDATION_ERROR` | `"carrier_id"` |
| 仅提供 `carrier_type` 或仅提供 `carrier_id` | `400` | `VALIDATION_ERROR` | 缺失的那一个 |
| 载体不存在 / 已逻辑删除 / 类型与标识不一致 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Empty / Not Found 语义**：

| 情形 | 响应 |
|---|---|
| 无活跃 Container（未给载体过滤） | `200`，`items == []`，`total == 0`（**Empty**） |
| 载体存在但无活跃 Container | `200`，`items == []`（**Empty**） |
| 载体不存在 / 已逻辑删除 / 类型与标识不一致 | `404 NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

### 4.3 `GET /api/containers/{container_id}` — 按 id 读取

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/containers/{container_id}` |
| Path parameter | `container_id`（integer） |
| 认证 | **必需**（§6） |

**Response 200**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `container_id` 非整数 | `400` | `VALIDATION_ERROR` | `"container_id"` |
| `container_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：`404` 同时覆盖「不存在」与「已被逻辑删除」，两者不做区分。

---

### 4.4 `PATCH /api/containers/{container_id}` — 更新可选字段

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/api/containers/{container_id}` |
| Path parameter | `container_id`（integer） |
| 认证 | **必需**（§6） |

**Request body**（部分更新）

```json
{ "cpu": "16 vCPU", "memory": null, "owner": "ops2" }
```

**可变字段（封闭集合，恰 4 个）**：`image`、`cpu`、`memory`、`owner`（R-CONTAINER-004）。

**不可变字段**：`id`、`carrier_type`、`carrier_id`（载体绑定）、`name`、`created_at`、`deleted_at` **不接受**修改（NQ-1）。请求体中出现不可变字段或任何未识别字段 → `400 VALIDATION_ERROR`。

**关键语义**

- 请求体**至少**需包含一个可变字段；空 body（`{}`）→ `400 VALIDATION_ERROR`。
- 未提供的字段保持不变；提供 `null` 的字段被清空。
- 本资源无乐观锁；并发更新为**最后提交生效**；`updated_at` **不是**并发控制依据。
- 本资源**无状态**：`status` 既非可变字段，也不得出现在请求体中（`400`）。
- 可变字段在唯一性边界内**不参与**唯一性（唯一性只针对 `name`），更新路径**不涉及**唯一性冲突。

**Response 200**：§2 的单对象结构；`id`、`carrier_type`、`carrier_id`、`name`、`created_at` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| 请求体含未识别 / 不可变字段（含 `name` / `carrier_type` / `carrier_id` / `bare_metal_id` / `virtual_machine_id` / `id` / `deleted_at` / `cluster_id` / `status`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| 请求体无可变字段（含 `{}`） | `400` | `VALIDATION_ERROR` | — |
| 可选字段非字符串（且非 `null`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| 目标不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | — |
| `container_id` 非整数 | `400` | `VALIDATION_ERROR` | `"container_id"` |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

- 上述 `400` / `404` 情形**不得产生任何写入**。

---

### 4.5 `DELETE /api/containers/{container_id}` — 逻辑删除

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/api/containers/{container_id}` |
| Path parameter | `container_id`（integer） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§6） |

**Response 204**

- 无响应体。
- 目标 Container 的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新；该行**仍物理存在**（R-DELETE-001）。
- 删除**只修改目标行**，不级联；**载体（BareMetal 或 VM）的 `deleted_at` / `updated_at` / 各字段逐字段不变**（R-DELETE-005）。
- 已删 Container 不再占用载体内 `name` 唯一性；同一载体可重新登记同名（R-DELETE-006）。
- 删除委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`），显式传入 `CONTAINER_ACTIVE_CHILD_CHECKS`（当前显式空元组，代表「Service 表尚不存在」，F008 追加「活跃 Service」）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `container_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "container_id", "code": "INVALID" }]` |
| 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| 目标存在**活跃**子资源 | `409` | `CONFLICT` | `[{ "field": null, "row": null, "code": "ACTIVE_CHILDREN_EXIST" }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- `404` 同时覆盖「不存在」与「已被逻辑删除」；重复删除同一 `id` 返回 `404`。
- `409` **不产生任何写入**：目标行 `deleted_at` 仍为空。
- 当前 Container **没有**活跃子资源（Service 表尚不存在），故 `409` 在本 Feature 内**不可达**；该分支由 `CONTAINER_ACTIVE_CHILD_CHECKS` 声明点承接，**F008** 落地时追加「活跃 Service」检查。**不得**因此认为「Container 永远无子资源」。

**不提供的能力**

- **不提供** `DELETE …/by-name/…`（写操作一律走 `id`）。
- **不提供** 批量删除 / 条件删除 / 恢复 / 查看已删资源。

---

## 5. 错误信封

本资源复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 的实现。不另立一套。

### 5.1 `409 CONFLICT` — 载体内活跃 `name` 重复

```json
{ "error": { "code": "CONFLICT", "message": "Container 名称已存在",
  "details": [ { "field": "name", "code": "DUPLICATE",
    "message": "同一载体内已存在活跃的同名 Container" } ] } }
```

### 5.2 `409 CONFLICT` — 目标存在活跃子资源（Container 删除，F008 起可达）

```json
{ "error": { "code": "CONFLICT", "message": "父资源存在活跃子资源，无法删除",
  "details": [ { "row": null, "field": null, "code": "ACTIVE_CHILDREN_EXIST",
    "message": "资源仍存在活跃子资源，无法删除" } ] } }
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定** |
| `details[].code` | `"DUPLICATE"` / `"ACTIVE_CHILDREN_EXIST"` | **稳定**：机器可读判别值 |
| `details[].field` | 唯一性冲突为 `"name"`；父子冲突为 `null` | 稳定 |
| `error.message` / `details[].message` | 人类可读 | **不构成契约** |

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

### 5.3 载体引用不存在 / 已删 / 类型不一致

`404 NOT_FOUND`，`details == []`，`error.message` 人类可读。**不**为多态载体另立错误码。

---

## 6. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（ADR-0005）。
- 认证成功即可执行全部操作；**不需要**任何角色 / 权限（V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点均位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 7. 并发与一致性语义

1. **创建按载体类型分派对载体行加共享锁**：`POST` 在同一请求事务内，按 `carrier_type` 选择 `bare_metals` 或 `virtual_machines`，执行 `SELECT … WHERE id = :carrier_id AND deleted_at IS NULL FOR SHARE`；未命中 → `404`。
2. **载体删除对自身加排他锁**：`DELETE /api/bare-metals/{id}` / `DELETE /api/virtual-machines/{id}`（F014）在同一事务内对自身行 `FOR UPDATE`，再检查活跃子资源；F007 后 `BARE_METAL_ACTIVE_CHILD_CHECKS` 含活跃 Container，`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 亦含活跃 Container。
3. **并发结果**：「登记 Container」与「删除其载体」并发时，二者**恰有一个**成功；结束后不存在「载体已删 + Container 活跃」的记录：

   ```sql
   SELECT count(*) FROM containers c
   JOIN bare_metals bm ON bm.id = c.bare_metal_id
   WHERE c.deleted_at IS NULL AND bm.deleted_at IS NOT NULL;         -- 必须为 0

   SELECT count(*) FROM containers c
   JOIN virtual_machines vm ON vm.id = c.virtual_machine_id
   WHERE c.deleted_at IS NULL AND vm.deleted_at IS NOT NULL;         -- 必须为 0
   ```

4. **Container 删除**：委托系统内唯一软删写入路径，在同一事务内先锁目标行、再执行声明的活跃子资源检查，命中即 `409` 且不写 `deleted_at`。
5. **唯一性**：应用层 `409` 预检为体验优化；两条 partial unique index 为**最终权威**（`23505`），且两 FK 的 `RESTRICT` 为参照完整性第二道防线（载体无物理删除路径，产品路径不触发）。

---

## 8. 明确不承诺的行为（`undefined_constraints`）

以下 `name` 与四个可选字段的取值行为在 CSM 中**当前未定义**，**不得假设**（Product Handoff NQ-4 / NQ-5）：

| 事项 | 本契约的承诺 |
|---|---|
| 长度上限 / 下限 | **无承诺**。不校验、不拒绝 |
| 首尾空白是否保留 / 去除（trim） | **无承诺**。实现不做变换；**原样存取** |
| 空字符串是否允许 | **无承诺**。本契约既不声明其合法，也不声明其非法 |
| Unicode NFC / NFD 归一化 | **无承诺**。实现不做归一化 |
| 是否禁止 `/` 或其他字符 | **不禁止**（`/` 禁令**仅针对 Cluster 名称** R-CLUSTER-005） |
| 大小写折叠 | **不做**：仅在**唯一性**上确认大小写敏感（R-CONTAINER-003、§22）；无 `lower(name)` 唯一索引 |
| 四个可选字段的结构化拆分 | **不做**：纯文本，不拆分 / 不归一（R-CONTAINER-004） |
| 「长期服务型 vs 短生命周期」判别字段 | **不引入**：R-CONTAINER-001 是登记口径约束，无可判别字段（NQ-5） |

**明确后果声明（是事实，不是规则）**：在现有已确认规则下，空字符串、含首尾空白的 `name` **不会**被本 API 拒绝。这**不得**被解读为 CSM 已确认「空 `name` 合法」。若用户确认需要拒绝空串 / 空白 / 超长，属**新增产品规则**。

---

## 9. 逐条 AC 到端点 / 断言的映射（AC-01~AC-44）

| AC | 保证主体 | 端点 / 断言 |
|---|---|---|
| AC-01 | 契约 | `POST` with `carrier_type=BARE_METAL` → `201`；`ContainerRead` 恰 10 字段，无 `deleted_at`/`status`/`cluster_id`/K8s/位置 |
| AC-02 | 契约 | `POST` with `carrier_type=VIRTUAL_MACHINE` → `201`，同字段集合 |
| AC-03 | 契约 | 缺 `name` → `400 VALIDATION_ERROR`，`details[].field=="name"`；无记录 |
| AC-04 | 契约 | 缺 `carrier_type` / `carrier_id` → `400`，`field` 指向载体字段；无记录 |
| AC-05 | 契约 | 多载体（列表 / 同时给两类）schema 层不可表达 → `400`；无记录 |
| AC-06 | 契约 | 以 Cluster/Service/NIC/IP 为载体或含其字段 → `400`（schema 封闭） |
| AC-07 | 契约 + Backend | 类型与标识不一致 → 按类型分派查不到 → `404`，无记录，非 5xx |
| AC-08 | 契约 + Backend | 载体不存在 / 已软删 → `404`，无记录，非 5xx |
| AC-09 | 契约 | 无可选字段 → `201`，各字段返回 `null`（非省略） |
| AC-10 | 契约 + Backend | 中文 / `"8 vCPU"` / `"registry/nginx:1.25"` / `"4G"` 原样往返 |
| AC-11 | Guard + Backend | 无长度 / trim / 空串 / 字符 / `/` 校验；空串与首尾空白不被拒绝 |
| AC-12 | 契约 + DB | 同载体重复活跃 `name` → `409`，`field=="name"`；DB partial unique index 兜底 |
| AC-13 | DB（两索引） | 不同载体 **类型** 同名 → 均 `201` |
| AC-14 | DB | 同类型不同 `carrier_id` 同名 → 均 `201` |
| AC-15 | DB | 跨类型同数值 `carrier_id` 同名 → 均 `201`（不同类型即不同载体） |
| AC-16 | 契约 + DB | Container 无全局唯一；不与 VM `name` 唯一性混用 |
| AC-17 | DB（无 `COLLATE` / 无 `lower()`） | 同载体 `web` 与 `WEB` 共存 |
| AC-18 | DB | 绕过应用层直插 → `23505`；应用路径同一 `409` |
| AC-19 | DB（partial predicate） | 软删后同载体可重登记；旧行 `deleted_at` 未改写 |
| AC-20 | DB（索引按载体列，非 Cluster） | 同 Cluster 不同 BM 同名 → 均 `201` |
| AC-21 | 契约 + Guard + DB | 请求 / 响应 / 表 / query 无 `cluster_id`/`cluster`/`cluster_name` |
| AC-22 | 契约 + DB | 详情仅暴露载体绑定；不持久化 Cluster 归属 |
| AC-23 | 契约 + Guard + DB | 无 `status` 字段 / 枚举 / 默认值 / 过滤参数 |
| AC-24 | 契约 | 列表 `200` + `{items,total,page,page_size}`；空 → `items==[]`/`total==0`，非 404 |
| AC-25 | 契约 | 不存在 / 已删 `id` → `404 NOT_FOUND`（不区分） |
| AC-26 | 契约 + Backend | `?carrier_type=&carrier_id=`：载体存在但无活跃 → `200` 空集；载体不存在 / 已删 → `404`；两类型均成立 |
| AC-27 | Backend（活跃过滤） | 已删不出现在列表 / 按载体结果 / `total`；按 `id` → `404` |
| AC-28 | 契约 | `PATCH` 合法可选字段 → `200` 新值；`null` 清空；缺省不变；再读一致 |
| AC-29 | 契约 | `PATCH` 未识别 / 不可变字段 → `400`；空 body → `400`；`name` 与载体绑定不可变 |
| AC-30 | 契约 + 软删服务 | `DELETE` → `204`；行仍物理存在且 `deleted_at` 非空；不再出现在列表 / 详情 |
| AC-31 | 契约 + Backend | 删除不级联；载体与其它资源行逐字段不变 |
| AC-32 | 契约 + Guard | 无 restore / undelete / purge / 批量 / `include_deleted` |
| AC-33 | Backend（检查）+ 测试 | BM 有活跃 Container → `DELETE /api/bare-metals/{id}` → `409` `ACTIVE_CHILDREN_EXIST`；BM `deleted_at` 仍 NULL |
| AC-34 | Backend（检查）+ 测试 | VM 有活跃 Container → `DELETE /api/virtual-machines/{id}` → `409`；VM `deleted_at` 仍 NULL |
| AC-35 | 测试 | 软删该载体全部活跃 Container（及其它活跃子资源）后 → 删除载体 `204` |
| AC-36 | DB + 并发测试 | BM 载体孤立记录查询 = 0 行 |
| AC-37 | DB + 并发测试 | VM 载体孤立记录查询 = 0 行 |
| AC-38 | Backend + 测试 | 创建对**被选中载体行** `FOR SHARE` 并同事务确认活跃；未命中 → 拒绝 |
| AC-39 | Guard + 测试 | `BARE_METAL_ACTIVE_CHILD_CHECKS` 非空且含 VM / NIC / Container；删除路径真实消费 |
| AC-40 | Guard + 测试 | `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 非空且含 Container；VM 删除路径真实消费 |
| AC-41 | Guard + 测试 | `CONTAINER_ACTIVE_CHILD_CHECKS` 显式声明（当前 `()`）且删除路径真实传入 |
| AC-42 | Guard | 无 K8s / Docker / Runtime / 外部平台 / 同步字段与端点 |
| AC-43 | Guard + DB | 不注册其它资源端点；`containers` 表无 Cluster / NIC / IP / Service / 位置结构 |
| AC-44 | 前端 + 测试 | 三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`；不重复实现业务守卫 |

> 全部 AC 均**可实现**；无一条需要修改产品需求。

---

## 10. 明确不在本契约中（非目标）

- Cluster / BareMetal / VM / NIC / IP / Service 的端点（权威正文见各自契约）。
- `DELETE /api/clusters/{id}` 与一切软删语义总则（权威正文：`docs/api/f014-soft-delete.md`）。
- Cluster 视角别名与关联聚合视图（F009 / F010）；F010 **必须复用**本契约的按载体限定读取能力，不得另写一份过滤。
- **Container 的状态**（Q-002=B）。
- Container 自身存储 `cluster_id` / Cluster 维度字段 / 过滤参数（R-CONTAINER-002）。
- **Kubernetes workload（Pod / Deployment / DaemonSet 等）/ Docker API / Container Runtime 接入 / 自动发现 / 同步 / 凭据 / 外部平台 id**（R-CONTAINER-001；§23）。
- DataCenter / 园区 / 机房 / 机柜 / U 位等位置模型（§6、§13）。
- 四个可选字段的结构化拆分、统计 / 报表 / 高级筛选 / 排序 / 批量 / 标签。
- `name` 重命名与载体迁移（NQ-1）、全局 `by-name` 别名（NQ-7）、`name` 与可选字段的最小字符约束（NQ-4）。
- 物理删除、Undelete / Restore / 回收站 / 已删资源查看 / 批量删除（R-DELETE-001/003；ADR-0004）。
- Excel 批量导入（F011）、审计 / 历史 / 导出、认证 / 会话端点（F013）。
- API versioning、游标分页（无需求）。

GIT: NONE
