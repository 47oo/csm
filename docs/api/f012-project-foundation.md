# F012 API 契约 — 项目基础框架与运行环境

> Status: **READY**
> Feature: F012（ENABLER，E07，P0）
> Author Role: architect
> Date: 2026-09-15
> Source: `docs/api/api-conventions.md`（`READY`）、`docs/architecture/adr/adr-0003-resource-identity-and-api-contract.md`（`ACCEPTED`）、`docs/architecture/csm-v1-foundation-architecture.md`、`docs/architecture/f012-project-foundation-handoff.md`、`docs/product/handoffs/f012-project-foundation.md`
> 本文件是 F012 前后端与测试的共同协议。

---

## 1. 范围与前提

1. **产品 API：仅 `GET /api/health`。** F012 不交付任何资源（Cluster / BareMetal / …）的产品 API。
2. **非产品自检面：`/_foundation/*`**（见 §4）。仅用于贯通技术栈与验证前端三态基座，**不属于产品契约**，生产配置下不可达。
3. Cluster 的领域校验、CRUD API、`GET /api/clusters/by-name/{cluster_name}` 别名**属 F001**，不在本文件。
4. 通用约定（`/api` 前缀、复数资源名、`snake_case`、分页、字段类型、错误信封、状态码、Empty / Not Found）一律遵循 `docs/api/api-conventions.md`，本文件不重复定义。
5. F012 **不挂载认证中间件**。本文件所有端点当前**无需认证**（临时状态，F013 落地后变更，见 §6）。

---

## 2. 产品端点

### 2.1 `GET /api/health`

**用途**：存活 + 数据库连接可用性的健康检查（AC-02、架构判据 1 的可观察部分）。

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/health` |
| Path parameter | 无 |
| Query parameter | 无 |
| Request body | 无 |
| 认证 | 当前无需（见 §6） |

**Response 200**

```json
{
  "status": "ok",
  "database": "ok"
}
```

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `status` | string（枚举 `"ok"`） | 否 | 应用存活 |
| `database` | string（枚举 `"ok"`） | 否 | 数据库探测（轻量查询）成功 |

- 端点会执行一次轻量数据库探测（如 `SELECT 1`）；成功才返回 `200`。
- 响应不使用集合信封（health 不是集合资源）。

**Error Semantics**

| 情形 | HTTP | `error.code` | Body |
|---|---|---|---|
| 数据库不可达 / 探测失败 | `500` | `INTERNAL_ERROR` | 统一错误信封（见 `api-conventions.md` §5） |

**Empty / Not Found 语义**：不适用。

---

## 3. 通用错误与冲突映射（F012 拥有的机制与通用语义）

所有错误响应使用 `api-conventions.md` §5 的统一信封。F012 提供**资源无关**的数据库完整性错误翻译层，按 SQLSTATE 映射：

| SQLSTATE | 数据库条件 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|---|
| `23502` | NOT NULL 违反 | `400` | `VALIDATION_ERROR` | 违规列（若可判定） |
| `23514` | CHECK 约束违反 | `400` | `VALIDATION_ERROR` | 违规列（至少 `name`） |
| `23505` | 唯一索引违反 | `409` | `CONFLICT` | 违规列（至少 `name`） |
| `23503` | 外键违反 | `409` | `CONFLICT` | 违规列 |

- 请求体 / 查询参数的 schema 校验失败 → `400` `VALIDATION_ERROR`，`details[].field` 必填。
- **边界**：上表是 F012 提供的**通用机制**。资源级的产品冲突语义（应用层预检、友好文案、父有活跃子→409）由 F001 / F014 在其上叠加，**不得另立第二套信封或映射**。
- `error.message` 人类可读，不构成契约；前端按 `error.code` 分支，不解析 `message`。

---

## 4. 非产品自检面 `/_foundation/*`

> **这不是产品契约。**
> - 仅在 dev / test 配置下挂载；生产配置下**不存在**（请求返回 `404`）。
> - 不含任何资源领域规则（无 `/` 校验、无唯一性预检、无 `by-name`、无状态、无父删子拦）。
> - `clusters` 表在此**仅作为基座验证载体**使用。
> - F001 交付产品 Cluster API 后，本面应被移除或降级为测试夹具；`Removal owner: F001`。
> - 前缀刻意置于 `/api` 之外，避免与 `api-conventions.md` 的资源约定及 ADR-0005 的 `/api/*` 认证范围产生交互。

### 4.1 `POST /_foundation/clusters`

创建一条载体行。**仅做通用 schema 校验，不实现 Cluster 领域规则。**

| 项 | 值 |
|---|---|
| Method | `POST` |
| Path | `/_foundation/clusters` |

**Request**

```json
{ "name": "cluster-a" }
```

| 字段 | 类型 | 必填 | nullable | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | 否 | 通用字符串；无 `/` 校验、无唯一性预检、无长度 / 空白规则 |

**Response 201**

```json
{
  "id": 1,
  "name": "cluster-a",
  "created_at": "2026-09-15T10:00:00Z",
  "updated_at": "2026-09-15T10:00:00Z"
}
```

| 字段 | 类型 | nullable |
|---|---|---|
| `id` | integer | 否 |
| `name` | string | 否 |
| `created_at` | string（RFC 3339） | 否 |
| `updated_at` | string（RFC 3339） | 否 |

`deleted_at` **不对外暴露**（`api-conventions.md` §4）。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `name` 缺失 / 非字符串 | `400` | `VALIDATION_ERROR` | `"name"` |
| 活跃同名（数据库 `23505`） | `409` | `CONFLICT` | `"name"` |
| `name` 含 `/`（数据库 `23514`） | `400` | `VALIDATION_ERROR` | `"name"` |

### 4.2 `GET /_foundation/clusters`

列出**活跃**载体行（`deleted_at IS NULL`），分页。

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/_foundation/clusters` |
| Query | `page`（int，从 1 起，默认 1）、`page_size`（int，默认 50，上限 200） |

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

**Empty 语义**：无活跃行 → `200`，`items` 为 `[]`，`total` 为 `0`。

**Error Semantics**

| 情形 | HTTP | `error.code` |
|---|---|---|
| `page` / `page_size` 非法（如 `page < 1`） | `400` | `VALIDATION_ERROR` |

### 4.3 `GET /_foundation/clusters/{id}`

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/_foundation/clusters/{id}` |
| Path param | `id`（integer） |

- `200`：同 §4.1 的单对象结构。
- **Not Found**：`id` 不存在或已软删 → `404` `NOT_FOUND`。

### 4.4 `PATCH /_foundation/clusters/{id}`

| 项 | 值 |
|---|---|
| Method | `PATCH` |
| Path | `/_foundation/clusters/{id}` |

Request：`{ "name": "<string>" }`（仅通用 schema 校验）。

- `200`：更新后的单对象结构。
- `404` `NOT_FOUND`：不存在或已软删。
- `409` `CONFLICT` / `400` `VALIDATION_ERROR`：同 §4.1。

### 4.5 `DELETE /_foundation/clusters/{id}`

**仅作自检夹具**：写入 `deleted_at`（**不是**产品软删除语义；不实现父删子拦、不实现并发加锁）。

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/_foundation/clusters/{id}` |

- `204`：成功（无 body）。
- `404` `NOT_FOUND`：不存在或已软删。

删除后的行**不得**出现在 §4.2 的列表中。

### 4.6 `GET /_foundation/error`

**仅作前端 Error 态的自检触发器**（确定性失败）。

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/_foundation/error` |

- 始终返回 `500` `INTERNAL_ERROR`，body 为统一错误信封。

---

## 5. Empty / Not Found 语义汇总（本 Feature 范围）

| 情形 | 响应 |
|---|---|
| `/_foundation/clusters` 无活跃行 | `200`，`items = []`（Empty） |
| `/_foundation/clusters/{id}` 不存在或已软删 | `404` `NOT_FOUND` |
| `GET /api/health` | 不适用 |

前端必须为 Empty 与 Not Found 渲染**不同**状态（`api-conventions.md` §7 / R-QUERY-004）。

---

## 6. 认证边界（临时状态）

- F012 **不实现认证**。本文件所有端点当前**无需认证**。
- 这是**显式、临时**状态，不得被解释为「产品不需要认证」。
- F013 落地后：认证中间件保护 `/api/*`，除登录端点外返回 `401 UNAUTHENTICATED`。
- **PROPOSED（非阻塞）**：`GET /api/health` 建议被 F013 白名单豁免，作为运维端点永久可访问。该建议需在 F013 实现时确认。
- `/_foundation/*` 位于 `/api` 之外，且生产不挂载，不参与 F013 的认证范围。

---

## 7. 明确不在本契约中（非目标）

- `GET/POST/PATCH/DELETE /api/clusters`、`GET /api/clusters/by-name/{cluster_name}`（属 F001）。
- 其他任何资源端点（属 F002 / F004 / F005 / F006 / F007 / F008）。
- 登录 / 登出 / 会话端点（属 F013）。
- Excel 导入端点（属 F011）。
- API versioning、游标分页（当前无需求）。