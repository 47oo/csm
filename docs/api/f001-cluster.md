# F001 API 契约 — Cluster 登记与管理

> Status: **READY**
> Feature: F001（E01，P0）
> Author Role: architect
> Date: 2026-09-15
> Source: `docs/api/api-conventions.md`（`READY`）、`docs/architecture/adr/adr-0003-resource-identity-and-api-contract.md`、`docs/architecture/adr/adr-0004-soft-delete-and-uniqueness-release.md`（均 `ACCEPTED`）、`docs/architecture/f001-cluster-handoff.md`、`docs/product/handoffs/f001-cluster.md`
> 本文件是 F001 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 Cluster 资源的产品 API，共 **5 个端点**（§3）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页信封、字段类型、错误信封、状态码、Empty / Not Found 语义）一律遵循 `docs/api/api-conventions.md`，本文件**不重复定义**，只做 Cluster 资源上的具体化。
3. **本契约不包含 `DELETE /api/clusters/{id}`**。删除的领域语义统一归属 F014（ADR-0004）；F001 内**不存在**任何软删除端点。见 §10。
4. Cluster **无状态**（R-CLUSTER-003），**无上级 / 位置**（§6、§13）。请求与响应中不存在状态字段、DataCenter / 机柜 / U 位字段。
5. F001 **不实现认证**。本契约所有端点当前**无需认证**（临时状态，见 §8）。
6. `name` 的长度 / 首尾空白 / 空字符串 / Unicode NFC 规范化属 `undefined_constraints`：**本契约不承诺其行为**，见 §7。

---

## 2. Cluster 资源表示

所有返回单个 Cluster 的端点（§3.1、§3.3、§3.4、§3.5）使用**同一个对象结构**：

```json
{
  "id": 1,
  "name": "cluster-a",
  "created_at": "2026-09-15T10:00:00Z",
  "updated_at": "2026-09-15T10:00:00Z"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `id` | integer | 否 | 不可变代理主键（ADR-0003）。写操作一律使用该值 |
| `name` | string | 否 | 集群名称，Cluster 的标识（R-CLUSTER-001） |
| `created_at` | string（RFC 3339，含时区偏移） | 否 | 登记时间 |
| `updated_at` | string（RFC 3339，含时区偏移） | 否 | 最近更新时间（应用层维护） |

**该字段集合是封闭的**：

- 不存在 `deleted_at`（不对外暴露，`api-conventions.md` §4）；
- 不存在任何状态字段（R-CLUSTER-003）；
- 不存在 DataCenter / 园区 / 机房 / 机柜 / U 位等上级或位置字段（§6、§13）；
- 不存在 BareMetal 相关字段或计数（R-CLUSTER-004 在 F001 内不产生任何用户可观察行为）。

时间字段为 RFC 3339 字符串，示例使用 UTC（`Z`）。前端应作为**不透明字符串**展示 / 传递，不得假设固定时区偏移量，也不得把字符串解析结果用于业务判断。

---

## 3. 端点

### 3.1 `POST /api/clusters` — 登记 Cluster

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/api/clusters` |
| Path parameter | 无 |
| Query parameter | 无 |
| 认证 | 当前无需（§8） |

**Request body**（`Content-Type: application/json`）

```json
{ "name": "cluster-a" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | 否 | 名称；不得包含 `/`（R-CLUSTER-005）。**不校验长度 / 首尾空白 / 空串 / Unicode 规范化**（§7） |

**Response 201**

§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 请求体缺少 `name`（含 `{}`） | `400` | `VALIDATION_ERROR` | `"name"` | 非契约 |
| `name` 为 `null` / 非字符串 | `400` | `VALIDATION_ERROR` | `"name"` | 非契约 |
| `name` 含 `/` | `400` | `VALIDATION_ERROR` | `"name"` | `"INVALID_CHARACTER"` |
| 已存在**活跃**同名 Cluster（大小写敏感） | `409` | `CONFLICT` | `"name"` | `"DUPLICATE"` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

- 含 `/` 的名称**必须**返回 `400`，**不得**返回 `500`（数据库 `ck_clusters_name_no_slash` 仅为第二道保险，见 §6）。
- 上述 `400` / `409` 情形**不得产生任何写入**。
- 若同名 Cluster 已被**逻辑删除**，本次登记**成功**（`201`，R-DELETE-006）。

**Empty / Not Found 语义**：不适用。

---

### 3.2 `GET /api/clusters` — 列出活跃 Cluster

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/clusters` |
| Path parameter | 无 |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50） |
| 认证 | 当前无需（§8） |

**Response 200**

```json
{
  "items": [
    {
      "id": 1,
      "name": "cluster-a",
      "created_at": "2026-09-15T10:00:00Z",
      "updated_at": "2026-09-15T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

- `items`：`Cluster` 对象数组（§2），按 `id` 升序。
- `total`：**活跃** Cluster 总数（不受本页限制）。
- 已逻辑删除的 Cluster **不出现**在 `items`，也不计入 `total`（R-DELETE-002）。

**Empty 语义**：系统中不存在活跃 Cluster → `200`，`items == []`，`total == 0`。**不得**返回 `404`（R-QUERY-004；`api-conventions.md` §7）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：不适用（集合端点不存在「父资源不存在」的情形）。

---

### 3.3 `GET /api/clusters/{cluster_id}` — 按 id 读取 Cluster

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/clusters/{cluster_id}` |
| Path parameter | `cluster_id`（integer） |
| Query parameter | 无 |
| 认证 | 当前无需（§8） |

**Response 200**：§2 的单对象结构。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `cluster_id` 非整数 | `400` | `VALIDATION_ERROR` | `"cluster_id"` |
| `cluster_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | —（`details` 为空数组） |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Not Found 语义**：`404` **同时**覆盖「不存在」与「已被逻辑删除」两种情况，两者**不做区分**（`api-conventions.md` §6）。

---

### 3.4 `GET /api/clusters/by-name/{cluster_name}` — 按名称读取 Cluster（只读别名）

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/clusters/by-name/{cluster_name}` |
| Path parameter | `cluster_name`（string，单个 URL 路径段） |
| Query parameter | 无 |
| 认证 | 当前无需（§8） |

**语义**

1. 这是**只读别名**。规范路径是 §3.3 的 `/api/clusters/{cluster_id}`；**不存在**按名称的写端点。
2. `{cluster_name}` 按**字面值等值**、**大小写敏感**匹配（R-CLUSTER-002、§22）。实现**不得**做大小写折叠、`trim` 或 Unicode 归一化。
3. 已**逻辑删除**的 Cluster **不参与名称解析**（R-DELETE-006）。
4. `{cluster_name}` 是单个 URL 路径段；含中文或保留字符时按 RFC 3986 百分号编码（UTF-8）传输，服务端解码后参与等值比较。名称**不可能**含 `/`（R-CLUSTER-005），因此别名路径不会因名称而分段错乱。
5. 名称为纯数字（如 `"123"`）时，`by-name/123` 与 `/123`（按 id）语义不同——这正是 `by-name` 前缀存在的理由（ADR-0003 §2）。

**Response 200**：§2 的单对象结构。命中结果与 `GET /api/clusters/{id}` 对同一 Cluster 的返回**逐字段一致**（AC-06）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| 名称不存在**或**对应 Cluster 已被逻辑删除 | `404` | `NOT_FOUND` | 空数组 |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

**Empty / Not Found 语义**：本端点无 Empty 语义；未命中一律 `404 NOT_FOUND`。

---

### 3.5 `PATCH /api/clusters/{cluster_id}` — 更新 Cluster 名称

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/api/clusters/{cluster_id}` |
| Path parameter | `cluster_id`（integer） |
| Query parameter | 无 |
| 认证 | 当前无需（§8） |

**Request body**

```json
{ "name": "cluster-b" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | 否 | 与 §3.1 **完全相同**的规则与校验（`/` 禁令、活跃唯一性） |

`name` 是当前唯一可变字段，因此**必须提供**；两者共用同一套领域校验（同一实现入口），不得出现创建与更新规则不一致的情况。

**Response 200**：§2 的单对象结构，`name` 与 `updated_at` 为更新后的值；`id`、`created_at` 不变。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` | `details[].code` |
|---|---|---|---|---|
| 请求体缺少 `name`（含 `{}`） | `400` | `VALIDATION_ERROR` | `"name"` | 非契约 |
| `name` 为 `null` / 非字符串 | `400` | `VALIDATION_ERROR` | `"name"` | 非契约 |
| `name` 含 `/` | `400` | `VALIDATION_ERROR` | `"name"` | `"INVALID_CHARACTER"` |
| 目标 `cluster_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | — | — |
| `cluster_id` 非整数 | `400` | `VALIDATION_ERROR` | `"cluster_id"` | 非契约 |
| 改后名称与**其他活跃** Cluster 重复（大小写敏感） | `409` | `CONFLICT` | `"name"` | `"DUPLICATE"` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — | — |

**关键语义**

- **改为自身当前名称** → `200`（不得误报 `409`）。
- `409` 与 `400` 情形**不得产生任何写入**。
- 改名成功后，**旧名称立即释放**，可作为其他 Cluster 的名称登记成功。
- **并发语义**：本资源无乐观锁（无 `version` 列）。对同一行的并发更新为**最后提交生效**；对名称的并发唯一性竞争由数据库 partial unique index 兜底，冲突方返回 `409 CONFLICT`。`updated_at` **不是**并发控制依据。

**Empty / Not Found 语义**：不适用。

---

## 4. 路径与路由解析规则

1. **canonical 与 alias**：`/api/clusters/{cluster_id}` 是规范路径；`/api/clusters/by-name/{cluster_name}` 是只读别名。写操作（`POST` / `PATCH`）**一律走 `id`**。
2. **`by-name` 路由先于 `/{cluster_id}` 声明**（防御性约定）。`cluster_id` 为整数路径参数，因此字符串 `by-name` 永远不会被解析为 `id`。
3. **路径参数非法**（如 `/api/clusters/abc`）→ `400 VALIDATION_ERROR`，`details[].field == "cluster_id"`，**不得**返回 `500`。
4. **`by-name` 路径段**为单个路径段，按 RFC 3986 百分号编码（UTF-8）传输。
5. 本契约**不定义**以下请求的行为（既非 Empty 也非 Not Found）：`/api/clusters/by-name`（缺少名称段）、`/api/clusters/by-name/`（名称段为空）。前端不得构造此类请求。

---

## 5. 状态码汇总（本资源）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取成功 / 更新成功 / 列表成功（含空列表） | — |
| `201` | 登记成功 | — |
| `400` | 字段校验失败（含 `name` 含 `/`、参数非法、路径参数非整数） | `VALIDATION_ERROR` |
| `404` | 资源不存在**或**已被逻辑删除（`{id}`、`by-name`） | `NOT_FOUND` |
| `409` | 活跃名称重复 | `CONFLICT` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `401` | **F013 落地后**：未认证访问本资源任何端点 → `401 UNAUTHENTICATED`（含 `GET /api/health` 与全部 `/api/clusters*`） | `UNAUTHENTICATED` |
| `403` | **不存在触发路径**（V1 仅两态，无授权判断；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**；前端必须按 `error.code` 分支，不解析 `message`。

---

## 6. 数据库权威性与 `/` 禁令的双保险分工

- **应用层（体验与字段级错误）**：`name` 含 `/` 时，写入路径在**数据库 CHECK 之前**拒绝，返回 `400 VALIDATION_ERROR` + `details[].field = "name"`。该校验**只有一份实现**，`POST` 与 `PATCH` 共用（后续 Excel 导入 F011 也复用同一入口，R-IMPORT-002）。
- **数据库层（最终权威）**：`ck_clusters_name_no_slash`（F012 基线，**已冻结**）。若应用层预检被绕过，含 `/` 的写入被数据库拒绝，经通用 SQLSTATE 映射（`23514`）返回 `400 VALIDATION_ERROR`，`details[].field` 至少含 `name`，**永不返回 500**。
- **唯一性同理**：应用层预检提供友好 `409`；`ux_clusters_name_active`（partial unique，`WHERE deleted_at IS NULL`）为最终权威，违反时 `23505 → 409 CONFLICT`。
- 本契约**不得**导致新增任何数据库约束或列；若未来产品确认新的名称规则，属新增产品规则 + **增量** migration（不改 `0001_f012_baseline`）。

---

## 7. 明确不承诺的行为（`undefined_constraints`）

以下 `name` 取值行为在 CSM 中**当前未定义**，**不得假设**（`docs/product/domain-model.yaml > undefined_constraints`；`requirements.md` R-CLUSTER-005）：

| 事项 | 本契约的承诺 |
|---|---|
| 长度上限 / 下限 | **无承诺**。不校验、不拒绝 |
| 首尾空白是否保留 / 去除（trim） | **无承诺**。实现不做变换；`name` **原样存取** |
| 空字符串是否允许 | **无承诺**。本契约既不声明其合法，也不声明其非法 |
| Unicode NFC / NFD 归一化 | **无承诺**。实现不做归一化 |
| 大小写折叠 | **不做**：仅在**唯一性与名称匹配**上确认大小写敏感（R-CLUSTER-002、§22） |

**明确后果声明（是事实，不是规则）**：在现有已确认规则下，空字符串、含首尾空白的名称**不会**被本 API 拒绝。这**不得**被解读为 CSM 已确认「空名称合法」。若用户确认需要拒绝空串 / 空白 / 超长（Product Handoff PROPOSED-1），属**新增产品规则**，将带来契约与数据库的增量变更。

前端与调用方**不得**基于上述任一未定义项编写业务分支（例如信任 `name` 非空、或依赖 `name` 已被 trim）。

---

## 8. 认证边界（临时状态）

- F001 **不实现认证 / 会话 / 权限**。本契约所有端点当前**无需认证**。
- 这是**显式、临时**状态，不得被解释为「产品不需要认证」。
- F013 落地后：认证中间件保护 `/api/*`，除登录端点外返回 `401 UNAUTHENTICATED`。本契约的全部端点在 `/api` 前缀下，因此**自动被覆盖**，**无需**任何白名单成员。
- 本契约不涉及 `GET /api/health` 的认证豁免问题。

---

## 9. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `GET /api/clusters`：无活跃 Cluster | `200`，`items == []`，`total == 0`（**Empty**） |
| `GET /api/clusters/{cluster_id}`：不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `GET /api/clusters/by-name/{cluster_name}`：不存在或已逻辑删除 | `404` `NOT_FOUND` |
| `PATCH /api/clusters/{cluster_id}`：目标不存在或已逻辑删除 | `404` `NOT_FOUND` |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004；`api-conventions.md` §7）。

---

## 10. 明确不在本契约中（非目标）

- **`DELETE /api/clusters/{id}` 及一切软删除语义**（属 F014；ADR-0004）。F001 内不存在该端点，也不存在任何写入 `deleted_at` 的路径。
- **`GET /api/clusters/by-name/{cluster_name}/bare-metals`**（属 F009，实体依赖 F002）。
- BareMetal 及其他任何资源端点（F002 / F004 / F005 / F006 / F007 / F008）。
- Cluster 的状态字段（R-CLUSTER-003）、DataCenter / 位置字段（§6、§13）。
- Cluster → BareMetal 关系查询、跨资源关联视图（F009 / F010）。
- Excel 批量导入（F011）、登录 / 会话端点（F013）、导出 / 高级筛选 / 审计（无已确认需求）。
- API versioning、游标分页（无需求）。
- 非产品自检面 `/_foundation/*`：**已于 F001 彻底移除**，任何配置下均不可达。