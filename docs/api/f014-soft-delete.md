# F014 API 契约 — 逻辑删除（Cluster 删除路径）

> Status: **READY**
> Feature: F014（ENABLER，E07，P0）
> Author Role: architect
> Date: 2026-09-16
> Source: `docs/api/api-conventions.md`（`READY`）、`docs/architecture/adr/adr-0003-resource-identity-and-api-contract.md`、`docs/architecture/adr/adr-0004-soft-delete-and-uniqueness-release.md`（均 `ACCEPTED`）、`docs/architecture/f014-soft-delete-handoff.md`、`docs/product/handoffs/f014-soft-delete.md`
> 本文件是 F014 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 **F014 逻辑删除**的产品 API，共 **1 个端点**（§3）。
2. 通用约定（`/api` 前缀、复数资源名、`snake_case`、错误信封、状态码、Empty / Not Found 语义）一律遵循 `docs/api/api-conventions.md`，本文件**不重复定义**，只做删除语义上的具体化。
3. Cluster 资源的**读取 / 创建 / 更新**（`POST` / `GET` / `GET` / `GET by-name` / `PATCH`）与本契约无关，其权威正文为 `docs/api/f001-cluster.md`。本契约**不修改**该文件。
4. 本契约是 `DELETE /api/clusters/{cluster_id}` 的**唯一权威来源**（`docs/api/f001-cluster.md` §1.3 / §10 已显式将 DELETE 排除并归属 F014）。
5. 本 Feature **不新增 / 不修改**任何领域对象、字段、状态或唯一性规则。
6. 本 Feature **不需要**`Schema` / migration 变更；删除语义所需结构（`clusters.deleted_at`、`ux_clusters_name_active`）已由 F012 基线冻结。
7. 认证边界遵循 ADR-0005：所有 `/api/*`（登录端点除外）要求认证；V1 仅「已认证 / 未认证」两态，**不引入角色 / 权限 / RBAC**。

---

## 2. 删除的语义（资源无关）

1. **逻辑删除而非物理删除**：删除是把目标行的 `deleted_at` 置为非空（服务器时间），行**仍然物理存在**（R-DELETE-001；§25 History Preservation）。
2. **已删不出现在常规查询**：删除成功后，该资源不再出现在列表 `items` 与 `total`，按 `id` 读取与 `by-name` 解析均返回 `404 NOT_FOUND`（R-DELETE-002）。
3. **无恢复**：V1 不提供 undelete / restore；`deleted_at` 一旦写入不再回退（R-DELETE-003）。
4. **父删子拦**：父资源存在活跃子资源时，删除被拒（`409 CONFLICT`），且**不产生任何写入**（R-DELETE-004）。
5. **不级联**：删除只修改目标行；不修改、不删除任何其他行（R-DELETE-005）。
6. **释放唯一性**：已删资源不再占用正常业务唯一性；同一名称可重新创建（R-DELETE-006）。
7. **保存前阻止**：删除相关的关键冲突由**后端**裁决，不依赖 UI（§21）。绕过界面直接调用本端点，结果与界面操作一致。

---

## 3. 端点

### 3.1 `DELETE /api/clusters/{cluster_id}` — 逻辑删除 Cluster

| 项 | 值 |
|---|---|
| Method | `DELETE` |
| Path | `/api/clusters/{cluster_id}` |
| Path parameter | `cluster_id`（integer） |
| Query parameter | 无 |
| Request body | 无（**不定义**；客户端不得发送请求体） |
| 认证 | **必需**（§5） |

**Response 204**

- 无响应体（`Content-Type` / body 均不承诺）。
- 目标 Cluster 的 `deleted_at` 被置为服务器时间；`updated_at` 相应更新。
- 该行仍物理存在。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `cluster_id` 非整数 | `400` | `VALIDATION_ERROR` | `[{ "field": "cluster_id", "code": "INVALID", ... }]` |
| `cluster_id` 不存在**或**已被逻辑删除 | `404` | `NOT_FOUND` | `[]`（空数组） |
| 目标 Cluster 存在**活跃**子资源 | `409` | `CONFLICT` | `[{ "field": null, "row": null, "code": "ACTIVE_CHILDREN_EXIST", "message": "..." }]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

- **`404` 同时覆盖「不存在」与「已被逻辑删除」，两者不做区分**（`api-conventions.md` §6）。重复删除同一 `id` 因此返回 `404`。
- **`409` 不产生任何写入**：目标行 `deleted_at` 仍为空（无部分写入）。
- **`401` 不改变任何数据**。

**Empty / Not Found 语义**

- 本端点为单资源写操作，**无 Empty 语义**。
- **Not Found**：`cluster_id` 不存在或已被逻辑删除 → `404 NOT_FOUND`。

**不提供的能力**

- **不提供** `DELETE /api/clusters/by-name/{cluster_name}`：写操作一律走 `id`（ADR-0003 §2）；`by-name` 仅为只读别名。
- **不提供** 批量删除 / 条件删除 / 恢复 / 查看已删资源。

---

## 4. 错误信封

本端点复用 `docs/api/api-conventions.md` §5 的统一信封，并沿用 `app/common/errors.py` / `app/common/error_handlers.py` 的实现。**不另立一套。**

### 4.1 `409 CONFLICT`（父资源存在活跃子资源）

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "父资源存在活跃子资源，无法删除",
    "details": [
      {
        "row": null,
        "field": null,
        "code": "ACTIVE_CHILDREN_EXIST",
        "message": "资源仍存在活跃子资源，无法删除"
      }
    ]
  }
}
```

| 字段 | 值 | 稳定？ |
|---|---|---|
| `error.code` | `"CONFLICT"` | **稳定**（`api-conventions.md` §6） |
| `details[].code` | `"ACTIVE_CHILDREN_EXIST"` | **稳定**：R-DELETE-004 的机器可读判别值 |
| `details[].field` | `null` | 稳定（资源级冲突，无单一字段） |
| `details[].row` | `null` | 稳定（`row` 仅导入等行式请求使用） |
| `error.message` / `details[].message` | 人类可读 | **不构成契约**，可随文案调整 |

前端与调用方必须按 `error.code`（必要时结合 `details[].code`）分支，**不得解析 `message`**。

### 4.2 其他错误

| 情形 | HTTP | `error.code` | `details` |
|---|---|---|---|
| `cluster_id` 非整数 | `400` | `VALIDATION_ERROR` | `details[].field == "cluster_id"` |
| 不存在或已删 | `404` | `NOT_FOUND` | `[]` |
| 未认证 | `401` | `UNAUTHENTICATED` | `[]` |
| 未预期错误 | `500` | `INTERNAL_ERROR` | `[]` |

---

## 5. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本端点 → `401 UNAUTHENTICATED`，且**不改变任何数据**（R-AUTH-001/002；ADR-0005）。
- 认证成功即可删除；**不需要**任何角色 / 权限（R-AUTH-003；V1 无 RBAC，`403 FORBIDDEN` 无触发路径）。
- 本端点位于 `/api` 前缀下，由既有认证中间件自动覆盖，**无需白名单成员**。

---

## 6. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `204` | 删除成功（无响应体） | — |
| `400` | `cluster_id` 非整数 | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | 资源不存在**或**已被逻辑删除 | `NOT_FOUND` |
| `409` | 存在活跃子资源 | `CONFLICT` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |

`error.message` 为人类可读描述，**不构成契约**。

---

## 7. 明确不在本契约中（非目标）

- Cluster 的读取 / 创建 / 更新端点（**权威正文**：`docs/api/f001-cluster.md`）。
- BareMetal 及其他任何资源端点（F002 / F004 / F005 / F006 / F007 / F008），及其删除端点。
- **Undelete / Restore / 回收站 / 已删资源查看 / 批量删除**（R-DELETE-003；`project-plan.yaml > out_of_scope`）。
- 删除操作人 / 时间 / 原因等审计信息（无已确认需求）。
- 影响面预览（「该集群下有 N 台裸金属」）——V1 仅承诺 `409` 语义，不承诺预览。
- 物理删除 / 数据清理 / purge（R-DELETE-001；§23）。
- API versioning、游标分页（无需求）。

---

## 8. 与非契约请求路径的关系

- `DELETE /api/clusters/by-name/{name}`：**不存在**该端点（`by-name` 仅只读别名，且 `DELETE` 写操作一律走 `id`）。此类请求不属于本契约，将得到路由层的非成功状态（`404` / `400` 等），前端**不得**构造。
- `DELETE /api/clusters/by-name`（单段、被解析为 `cluster_id = "by-name"`）：`cluster_id` 非整数 → `400 VALIDATION_ERROR`，不属于本契约的删除语义。
- 对不存在路径的 `405`（方法不允许）错误信封的 `code` 不在本契约承诺范围（沿用 `f001-cluster-handoff.md` Open #5 / F001 Review F-01 的既有状态）。