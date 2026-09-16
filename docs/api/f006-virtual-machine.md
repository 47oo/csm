# F006 API 契约 — VirtualMachine 登记与管理

> Status: **READY**
> Feature: F006（E03，P1，`depends_on: [F002]` = DONE）
> Author Role: architect
> Source: `docs/api/api-conventions.md`（`READY`）、ADR-0002 / 0003 / 0004 / 0005（均 `ACCEPTED`）、`docs/architecture/f006-virtual-machine-handoff.md`、`docs/api/f002-bare-metal.md`、`docs/api/f014-soft-delete.md`、`docs/product/handoffs/f006-virtual-machine.md`
> 本文件是 F006 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **VirtualMachine 资源**的产品 API，共 **5 个端点**（§3）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty / Not Found 语义、`deleted_at` 不暴露）一律遵循 `docs/api/api-conventions.md`，本文件不重复定义。
3. VirtualMachine **必属恰好一个宿主 BareMetal**（R-VM-005，N:1 mandatory）；**Cluster 归属由宿主推导、不单独记录**，本资源**无 `cluster_id`**、无 Cluster 维度过滤参数。
4. VirtualMachine 在 V1 **不设状态**（Q-002=B）。无 `status` 字段、状态枚举、默认值、过滤参数或读写路径。
5. R-VM-006 可选字段 `cpu / memory / disk / os / hypervisor / owner` 全部**可选、纯文本、允许 `null`、不结构化**。`hypervisor` 仅是**文本登记字段**，不触发任何虚拟化平台调用（R-VM-002）。
6. `name` 为**必填身份标识**，在**所有当前活跃 VirtualMachine 范围内全局唯一**（跨宿主、跨 Cluster，R-VM-004），比较**区分大小写**（§22）；已逻辑删除的 VirtualMachine **不再占用**该唯一性（R-DELETE-006）。
7. `name` 的长度 / 首尾空白 / 空字符串 / 非法字符等属**未定义约束**：本契约**不承诺其行为**（§7）。
8. 认证：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**无角色 / 权限 / RBAC**（ADR-0005）。
9. 本契约**不包含** Cluster CRUD、BareMetal 端点、删除语义总则、Cluster 视角 / 关联查询视图（F009 / F010）。不修改任何既有契约。
10. **不提供**全局 `by-name` 别名（Product Handoff NQ-3）。
11. **不提供** `name` 重命名与跨宿主迁移（登记后不可变；NQ-1 / PROPOSED-1）。变更由「软删 + 重新登记」替代。

---

## 2. VirtualMachine 资源表示

所有返回单个 VirtualMachine 的端点（§3.1、§3.3、§3.4）使用**同一个对象结构**：

```json
{
  "id": 7,
  "bare_metal_id": 3,
  "name": "vm1",
  "cpu": "8 vCPU",
  "memory": "32 GB",
  "disk": "500 GB",
  "os": "Ubuntu 22.04",
  "hypervisor": "PVE",
  "owner": "ops",
  "created_at": "2026-09-16T10:00:00Z",
  "updated_at": "2026-09-16T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）。写操作一律使用该值 |
| `bare_metal_id` | integer | 否 | 宿主 BareMetal 的 `id`（R-VM-005，恰好一个宿主） |
| `name` | string | 否 | 身份标识（R-VM-004）；**全局**活跃唯一、大小写敏感；原样存取，不做 trim / 归一化 |
| `cpu` | string | **是** | R-VM-006，未登记为 `null`；纯文本不拆分 |
| `memory` | string | **是** | R-VM-006 |
| `disk` | string | **是** | R-VM-006 |
| `os` | string | **是** | R-VM-006 |
| `hypervisor` | string | **是** | R-VM-006，纯文本；**仅登记字段**，不代表平台接入 |
| `owner` | string | **是** | R-VM-006 |
| `created_at` | string（RFC 3339） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339） | 否 | 最近更新时间（应用层维护；不是并发控制依据） |

**该字段集合是封闭的**：

- 不存在 `deleted_at`（不对外暴露）；
- 不存在 `status`、状态枚举或任何状态字段（Q-002=B）；
- 不存在 `cluster_id` / `cluster` / `cluster_name` 等 Cluster 维度字段（R-VM-005）；
- 不存在 NIC / IP / Container / Service 相关字段；
- 不存在 DataCenter / 园区 / 机房 / 机柜 / U 位等位置字段；
- 不存在自动发现 / 虚拟化平台同步 / 平台 id / 凭据字段（R-VM-002）。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递。

---

## 3. 端点

### 3.1 `POST /api/virtual-machines` — 登记 VirtualMachine

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/virtual-machines` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | **必需**（§5） |

**Request body**

```json
{ "bare_metal_id": 3, "name": "vm1", "cpu": "8 vCPU", "memory": "32 GB",
  "disk": "500 GB", "os": "Ubuntu 22.04", "hypervisor": "PVE", "owner": "ops" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `bare_metal_id` | integer | **是** | 否 | 宿主 `id`；必须存在且活跃（R-VM-005） |
| `name` | string | **是** | 否 | **全局**活跃唯一、大小写敏感（R-VM-004）；**不校验长度 / trim / 空串 / 字符规则**（§7） |
| `cpu` … `owner` | string | 否 | 是 | R-VM-006；不提供时为 `null` |

- 未识别字段 → `400 VALIDATION_ERROR`（请求 schema 封闭）。**不接受**多宿主字段、载体类型选择器，也不接受以 VM / Container 作为宿主。
- 六个可选字段缺省 / `null` 均存为 `null`，响应中**返回 `null` 而非省略**。

**Response 201**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 缺少 `name`（含 `{}`）/ 非字符串 | `400` | `VALIDATION_ERROR` | `"name"` | — |
| 缺少 `bare_metal_id` / 非整数 | `400` | `VALIDATION_ERROR` | `"bare_metal_id"` | — |
| `bare_metal_id` 引用**不存在或已逻辑删除**的 BareMetal | `404` | `NOT_FOUND` | — | —（`details == []`） |
| 全局已存在**活跃**同名 `name`（大小写敏感） | `409` | `CONFLICT` | `"name"` | `"DUPLICATE"` |
| 未识别字段 / 多宿主字段 / 载体类型选择器 | `400` | `VALIDATION_ERROR` | 该字段名 | — |
| 未认证 | `401` | `UNAUTHENTICATED` | — | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 上述 `400` / `404` / `409` 情形**不得产生任何写入**。
- **引用不存在 / 已删宿主返回 `404 NOT_FOUND`**（NQ-2 裁定）。该判定在同一事务内以「对宿主 BareMetal 行取 `FOR SHARE` 并确认 `deleted_at IS NULL`」实现；未命中即拒绝，**非 5xx**。
- 若同名 `name` 属于**已逻辑删除**的 VirtualMachine，本次登记**成功**（`201`，R-DELETE-006）。

**并发语义**：登记对宿主 BareMetal 行取共享锁；与宿主逻辑删除并发时，二者恰有一个成功（见 §6）。

---

### 3.2 `GET /api/virtual-machines` — 列出活跃 VirtualMachine

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/virtual-machines` |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50）、`bare_metal_id`（integer，可选） |
| 认证 | **必需**（§5） |

**语义**

- 未提供 `bare_metal_id`：返回系统中全部活跃 VirtualMachine。
- 提供 `bare_metal_id`：**按宿主限定**返回该 BareMetal 的活跃 VirtualMachine（R-QUERY-003 的 F006 侧 canonical 能力；**供 F010 复用**，F010 不得另写一份过滤）。
  - 宿主**不存在或已逻辑删除** → `404 NOT_FOUND`；
  - 宿主**存在但无活跃 VirtualMachine** → `200` + `items == []`（**Empty**）。
- 已逻辑删除的 VirtualMachine **不出现**在 `items`，也不计入 `total`。

**Response 200**

```json
{ "items": [ { "id": 7, "bare_metal_id": 3, "name": "vm1", "cpu": "8 vCPU",
  "memory": "32 GB", "disk": "500 GB", "os": "Ubuntu 22.04", "hypervisor": "PVE",
  "owner": "ops", "created_at": "2026-09-16T10:00:00Z", "updated_at": "2026-09-16T10:00:00Z" } ],
  "total": 1, "page": 1, "page_size": 50 }
```

- `items`：`VirtualMachine` 对象数组（§2），按 `id` 升序。
- `total`：**活跃** VirtualMachine 总数（受 `bare_metal_id` 过滤时为该过滤域内的活跃数）。

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
| 无活跃 VirtualMachine（未给 `bare_metal_id`） | `200`，`items == []`，`total == 0`（**Empty**） |
| `bare_metal_id` 存在但无活跃 VirtualMachine | `200`，`items == []`（**Empty**） |
| `bare_metal_id` 不存在或已逻辑删除 | `404 NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

### 3.3 `GET /api/virtual-machines/{virtual_machine_id}` — 按 id 读取

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/virtual-machines/{virtual_machine_id}` |
| Path parameter | `virtual_machine_id`（integer） |
| 认证 | **必需**（§5） |

**Response 200**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `virtual_machine_id` 非整数 | `400` | `VALIDATION_ERROR` | `"virtual_machine_id"` |
| `virtual_machine_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：`404` 同时覆盖「不存在」与「已被逻辑删除」，两者不做区分。

---

### 3.4 `PATCH /api/virtual-machines/{virtual_machine_id}` — 更新可选配置字段

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/api/virtual-machines/{virtual_machine_id}` |
| Path parameter | `virtual_machine_id`（integer） |
| 认证 | **必需**（§5） |

**Request body**（部分更新）

```json
{ "cpu": "16 vCPU", "memory": null, "owner": "ops2" }
```

**可变字段（封闭集合）**：R-VM-006 六字段 `cpu / memory / disk / os / hypervisor / owner`。

**不可变字段**：`id`、`bare_metal_id`、`name`、`created_at`、`deleted_at` **不接受**修改（NQ-1；F006 不提供）。请求体中出现不可变字段或任何未识别字段 → `400 VALIDATION_ERROR`。

**关键语义**

- 请求体**至少**需包含一个可变字段；空 body（`{}`）→ `400 VALIDATION_ERROR`。
- 未提供的字段保持不变；提供 `null` 的字段被清空。
- 本资源无乐观锁；并发更新为**最后提交生效**；`updated_at` **不是**并发控制依据。
- 本资源**无状态**：`status` 既非可变字段，也不得出现在请求体中（`400`）。

**Response 200**：§2 的单对象结构；`id`、`created_at`、`bare_metal_id`、`name` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| 请求体含未识别 / 不可变字段（含 `name` / `bare_metal_id` / `id` / `deleted_at` / `cluster_id` / `status`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| 请求体无可变字段（含 `{}`） | `400` | `VALIDATION_ERROR` | — |
| 可选字段非字符串（且非 `null`） | `400` | `VALIDATION_ERROR` | 该字段名 |
| 目标不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | — |
| `virtual_machine_id` 非整数 | `400` | `VALIDATION_ERROR` | `"virtual_machine_id"` |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

- 上述 `400` / `404` 情形**不得产生任何写入**。
- 本资源无可变唯一性字段（`name` 不可变），更新路径**不涉及**唯一性冲突。

---

### 3.5 `DELETE /api/virtual-machines/{virtual_machine_id}` — 逻辑删除

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/api/virtual-machines/{virtual_machine_id}` |
| Path parameter | `virtual_machine_id`（integer） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§5） |

**Response 204**

- 无响应体。
- 目标 VirtualMachine 的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新；该行**仍物理存在**（R-DELETE-001）。
- 删除**只修改目标行**，不级联；**宿主 BareMetal 的 `deleted_at` / `updated_at` / 各字段不变**（R-DELETE-005）。
- 已删资源不再占用正常业务唯一性；其 `name` 可在**任意**宿主重新登记（R-DELETE-006）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `virtual_machine_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "virtual_machine_id", "code": "INVALID" }]` |
| 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]` |
| 目标存在**活跃**子资源 | `409` | `CONFLICT` | `[{ "field": null, "row": null, "code": "ACTIVE_CHILDREN_EXIST" }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- `404` 同时覆盖「不存在」与「已被逻辑删除」；重复删除同一 `id` 返回 `404`。
- `409` **不产生任何写入**：目标行 `deleted_at` 仍为空。
- 当前 VirtualMachine **没有**活跃子资源（Container 表尚不存在），故 `409` 在本 Feature 内**不可达**；该分支由 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 声明点承接（当前显式空元组），**F007** 落地时追加「活跃 Container」检查（R-CONTAINER-005）。**不得**因此认为「VirtualMachine 永远无子资源」。

**不提供的能力**

- **不提供** `DELETE …/by-name/…`（写操作一律走 `id`）。
- **不提供** 批量删除 / 条件删除 / 恢复 / 查看已删资源。

---

## 4. 错误信封

本资源复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `error_handlers.py` / `sqlstate.py` 的实现。不另立一套。

### 4.1 `409 CONFLICT` — 全局活跃 `name` 重复

```json
{ "error": { "code": "CONFLICT", "message": "VirtualMachine 名称已存在",
  "details": [ { "field": "name", "code": "DUPLICATE",
    "message": "已存在活跃的同名 VirtualMachine" } ] } }
```

### 4.2 `409 CONFLICT` — 目标存在活跃子资源（VirtualMachine 删除）

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

> 补充：宿主不存在 / 已删的 FK 违规（`23503`）经**既有通用** `sqlstate.py` 映射返回 `409 CONFLICT` + `details[].code = "REFERENCE"`；该路径在产品路径下不可达（`FOR SHARE` 预检先给出 `404`，且宿主无物理删除），不为本资源另立映射。

---

## 5. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本契约任何端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（ADR-0005）。
- 认证成功即可执行全部操作；**不需要**任何角色 / 权限（V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本契约端点均位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 6. 并发与一致性语义

1. **创建对宿主加共享锁**：`POST` 在同一请求事务内对宿主 BareMetal 行执行 `SELECT … WHERE id = :bare_metal_id AND deleted_at IS NULL FOR SHARE`；未命中 → `404`。
2. **宿主删除对自身加排他锁**：`DELETE /api/bare-metals/{id}`（F002/F014）在同一事务内对 BareMetal 行 `FOR UPDATE`，再检查活跃子资源（`BARE_METAL_ACTIVE_CHILD_CHECKS`，F006 后包含「活跃 VirtualMachine」检查）。
3. **并发结果**：「登记 VirtualMachine」与「删除其宿主 BareMetal」并发时，二者**恰有一个**成功；结束后不存在「宿主已删 + VM 活跃」的记录：

   ```sql
   SELECT count(*) FROM virtual_machines vm
   JOIN bare_metals bm ON bm.id = vm.bare_metal_id
   WHERE vm.deleted_at IS NULL AND bm.deleted_at IS NOT NULL;   -- 必须为 0
   ```

4. **VirtualMachine 删除**：委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`），在同一事务内先锁目标行、再执行声明的活跃子资源检查，命中即 `409` 且不写 `deleted_at`。

---

## 7. 明确不承诺的行为（`undefined_constraints`）

以下 `name` 与六个可选字段的取值行为在 CSM 中**当前未定义**，**不得假设**（Product Handoff 假设 6 / NQ-5）：

| 事项 | 本契约的承诺 |
|---|---|
| 长度上限 / 下限 | **无承诺**。不校验、不拒绝 |
| 首尾空白是否保留 / 去除（trim） | **无承诺**。实现不做变换；**原样存取** |
| 空字符串是否允许 | **无承诺**。本契约既不声明其合法，也不声明其非法 |
| Unicode NFC / NFD 归一化 | **无承诺**。实现不做归一化 |
| 是否禁止 `/` 或其他字符 | **不禁止**（`/` 禁令**仅针对 Cluster 名称** R-CLUSTER-005，不适用于 VirtualMachine `name`） |
| 大小写折叠 | **不做**：仅在**唯一性**上确认大小写敏感（R-VM-004、§22）；无 `lower(name)` 唯一索引 |
| 六个可选字段的结构化拆分 | **不做**：纯文本，不拆分 / 不归一（R-VM-006） |

**明确后果声明（是事实，不是规则）**：在现有已确认规则下，空字符串、含首尾空白的 `name` **不会**被本 API 拒绝。这**不得**被解读为 CSM 已确认「空 `name` 合法」。若用户确认需要拒绝空串 / 空白 / 超长（PROPOSED-3），属**新增产品规则**。

前端与调用方**不得**基于上述任一未定义项编写业务分支。

---

## 8. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取 / 列表成功（含空列表）/ 更新成功 | — |
| `201` | 登记成功 | — |
| `204` | 删除成功（无响应体） | — |
| `400` | 请求格式或字段校验失败（含缺字段、非整数参数、未识别字段、空 PATCH） | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | 资源不存在或已被逻辑删除；引用的宿主 BareMetal 不存在或已删除（`POST` / `?bare_metal_id=`） | `NOT_FOUND` |
| `409` | 全局活跃 `name` 重复；目标存在活跃子资源 | `CONFLICT` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） | `FORBIDDEN` |

---

## 9. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `GET /api/virtual-machines`：无活跃 VirtualMachine | `200`，`items == []`，`total == 0`（**Empty**） |
| `GET /api/virtual-machines?bare_metal_id={id}`：宿主存在但无活跃 VirtualMachine | `200`，`items == []`（**Empty**） |
| `GET /api/virtual-machines?bare_metal_id={id}`：宿主不存在 / 已删 | `404` `NOT_FOUND` |
| `GET /api/virtual-machines/{id}`：不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `PATCH /api/virtual-machines/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `DELETE /api/virtual-machines/{id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `POST /api/virtual-machines`：引用的宿主 BareMetal 不存在 / 已删 | `404` `NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

## 10. 明确不在本契约中（非目标）

- Cluster 的端点（权威正文：`docs/api/f001-cluster.md`）。
- BareMetal 的端点与删除（权威正文：`docs/api/f002-bare-metal.md`）。
- `DELETE /api/clusters/{id}` 与一切软删语义总则（权威正文：`docs/api/f014-soft-delete.md`）。
- Cluster 视角别名与关联查询视图（F009 / F010）；F010 **必须复用**本契约的 `?bare_metal_id=` 能力，不得另写一份过滤。
- **VirtualMachine 的状态**（Q-002=B）。
- VirtualMachine 自身存储 `cluster_id` 或任何 Cluster 维度字段 / 过滤参数（R-VM-005）。
- NIC / IP / Container / Service 端点（F004 / F005 / F007 / F008）；VirtualMachine **不拥有**独立 NetworkInterface。
- DataCenter / 园区 / 机房 / 机柜 / U 位等位置模型（§6、§13）。
- **虚拟化平台接入 / 自动发现 / 同步 / 凭据 / 外部平台 id**（R-VM-002；§23；OPEN-006 已关闭为「已确认排除」）；`hypervisor` 仅为文本登记字段。
- 六个可选字段的结构化拆分、统计 / 报表 / 筛选。
- `name` 重命名与跨宿主迁移（NQ-1）、全局 `by-name` 别名（NQ-3）、`name` 与可选字段的最小字符约束（NQ-5）。
- 物理删除、Undelete / Restore、回收站、已删资源查看、批量删除（R-DELETE-001/003；ADR-0004）。
- Excel 批量导入（F011）、审计 / 历史 / 导出、认证 / 会话端点（F013）。
- API versioning、游标分页（无需求）。

GIT: NONE
