# API Contract — F009 Cluster 视角资源查询

> Status: **READY**
> Feature: F009（E05，P0）
> Author Role: architect
> Source: `docs/api/api-conventions.md`（`READY`）、ADR-0003 §2/§6（`ACCEPTED`）、ADR-0004（`ACCEPTED`）、ADR-0005（`ACCEPTED`）、`docs/api/f001-cluster.md`、`docs/api/f002-bare-metal.md`、`docs/api/f014-soft-delete.md`、`docs/architecture/f009-cluster-resource-view-handoff.md`
> 本文件是 F009 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 F009 唯一新增的产品 API：**`GET /api/clusters/by-name/{cluster_name}/bare-metals`**（Cluster 视角成员的**只读名称别名**），共 **1 个端点**（§3）。
2. 本契约不重新定义 BareMetal 资源表示、分页信封、错误信封、状态码或 Empty/Not Found 通用语义，一律遵循 `docs/api/api-conventions.md` 与 `docs/api/f002-bare-metal.md` §2/§3.2；本文件只做「Cluster 视角 + 名称别名」的具体化。
3. **canonical 与 alias**：
   - **canonical（成员读取）**：`GET /api/bare-metals?cluster_id={id}`（F002 §3.2）。F009 不新增成员读取实现，只交付别名。
   - **alias（本契约）**：`GET /api/clusters/by-name/{cluster_name}/bare-metals`，按名称寻址同一结果集，返回与 canonical 逐字段一致的信封与条目。
   - 写操作（POST / PATCH / DELETE）一律走 `id`；不存在按名称的写别名（ADR-0003 §2）。
4. **只读**：本端点不改动任何数据，不提供任何写 / 删除 / 恢复能力。
5. 认证：`/api/*`（除登录）要求认证；未认证 → `401 UNAUTHENTICATED`（ADR-0005）。
6. 无新领域对象 / 字段 / 关系 / 状态 / 唯一性规则；不涉及 NIC / IP / VM / Container / Service（R-QUERY-003 归 F010）。

---

## 2. Canonical / Alias 关系

| 项 | 值 |
|---|---|
| canonical | `GET /api/bare-metals?cluster_id={id}`（F002 §3.2） |
| alias | `GET /api/clusters/by-name/{cluster_name}/bare-metals`（本契约） |
| 关系 | alias 对 `{cluster_name}` 做**活跃、字面值、大小写敏感**名称解析得到 Cluster，再**委托**同一成员读取路径；返回结果与对该 Cluster `id` 调用 canonical **深等** |
| 结果等价 | `items`（字段与值、按 `id` 升序）、`total`、`page`、`page_size` 与 canonical 完全一致 |
| 软删过滤 | 与 canonical **共用** `deleted_at IS NULL` 统一原语；alias 不引入第二条过滤路径（ADR-0004） |
| 名称解析 | 复用 F001 `by-name` 的解析语义：字面值等值、大小写敏感、已删 Cluster 不参与解析 |

---

## 3. 端点

### `GET /api/clusters/by-name/{cluster_name}/bare-metals` — 按 Cluster 名称列出其活跃 BareMetal（只读别名）

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/clusters/by-name/{cluster_name}/bare-metals` |
| Path parameter | `cluster_name`（string，单个 URL 路径段） |
| Query parameter | `page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§7） |

**语义**

1. `{cluster_name}` 按**字面值等值**、**大小写敏感**匹配（R-CLUSTER-002、§22）。实现不得做大小写折叠、`trim` 或 Unicode 归一化。
2. 已**逻辑删除**的 Cluster **不参与名称解析**（R-DELETE-006）→ 视为不存在。
3. 命中后返回该 Cluster 的**活跃** BareMetal（`deleted_at IS NULL`，R-DELETE-002）；已逻辑删除的 BareMetal 不出现在 `items`，也不计入 `total`。
4. `{cluster_name}` 为单个 URL 路径段；中文 / 保留字符按 RFC 3986 百分号编码（UTF-8）传输，服务端解码后参与等值比较。名称不可能含 `/`，故路径不会因名称而分段错乱。
5. 名称为纯数字（如 `"123"`）时，`by-name/123/bare-metals` 与按 id 的 canonical 语义不同 —— 这正是 `by-name` 前缀存在的理由（ADR-0003 §2）。

**Response 200**

返回 F002 §3.2 的**同一分页信封**：

```json
{
  "items": [
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
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

- `items`：`BareMetal` 对象数组，字段集合**恰为** F002 §2 的 13 字段（`id, cluster_id, hostname, status, vendor, model, serial_number, cpu, memory, gpu, storage, created_at, updated_at`），按 `id` 升序。
- `total`：该 Cluster 的**活跃** BareMetal 总数（不受本页限制）。
- **该字段集合是封闭的**：不存在 `deleted_at`、Cluster 状态字段、DataCenter / 位置字段、自动发现 / 实时状态源字段，也无 NIC / IP / VM / Container / Service 相关字段。
- 可选硬件字段空值**返回 `null` 而非省略**（`api-conventions.md` §4）。
- 时间字段为 RFC 3339 字符串，前端作为**不透明字符串**处理。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `{cluster_name}` 不存在**或**对应 Cluster 已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

- `404` **同时**覆盖「名称不存在」与「对应 Cluster 已被逻辑删除」，两者**不做区分**（`api-conventions.md` §6；与 F001 §3.4 一致）。
- `cluster_name` 为字符串路径参数，**不存在**「非整数 → 400」的情形；`{cluster_name}` 未命中一律 `404`。

**Empty / Not Found 语义**

| 情形 | 响应 |
|---|---|
| 名称不存在或对应 Cluster 已逻辑删除 | `404 NOT_FOUND` |
| Cluster 存在且活跃，但其下无活跃 BareMetal | `200`，`items == []`，`total == 0`（**Empty**） |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004；`api-conventions.md` §7）。

**判定顺序与一致性（REQUIRED）**

1. **先**解析名称并确认 Cluster 活跃（未命中 → `404`）；**后**读取该 Cluster 的活跃 BareMetal（空 → `200` Empty）。
2. 成员读取**委托** F002 的同一读取路径（含其父 Cluster 存在性检查），从而与 canonical 共用同一 `deleted_at` 过滤与同一 404-vs-Empty 判定。
3. 读取在单一请求事务内完成；若 Cluster 在解析与读取之间被并发逻辑删除，成员读取的父活跃复检将命中不到 → `404`，**绝不**返回「已删 Cluster 的成员列表」。读取不写数据，无需加锁。

---

## 4. 错误信封

本端点复用 `docs/api/api-conventions.md` §5 的统一信封与 `app/common/errors.py` / `error_handlers.py` 实现，不另立一套。前端按 `error.code` 分支，**不得解析 `message`**。

`404 NOT_FOUND` 示例：

```json
{ "error": { "code": "NOT_FOUND", "message": "资源不存在", "details": [] } }
```

---

## 5. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 读取成功（含空列表） | — |
| `400` | `page` / `page_size` 非法 | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | 名称不存在或对应 Cluster 已被逻辑删除 | `NOT_FOUND` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） | `FORBIDDEN` |

`error.message` 为人类可读描述，可随文案调整，**不构成契约**。

---

## 6. Empty / Not Found 语义汇总（本契约范围）

| 情形 | 响应 |
|---|---|
| `{cluster_name}` 不存在 | `404` `NOT_FOUND` |
| `{cluster_name}` 对应 Cluster 已逻辑删除 | `404` `NOT_FOUND`（与不存在不区分） |
| Cluster 存在且活跃、无活跃 BareMetal | `200`，`items == []`，`total == 0`（**Empty**） |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004）。

---

## 7. 认证边界

- 所有 `/api/*`（除登录端点）要求认证；未认证访问本端点 → `401 UNAUTHENTICATED`，且不返回任何资源数据、不改变任何数据（R-AUTH-001/002；ADR-0005）。
- 认证成功即可访问；无需任何角色 / 权限（R-AUTH-003；V1 无 RBAC）。
- 本端点在 `/api` 前缀下，由既有 F013 中间件自动覆盖，无需白名单成员。

---

## 8. 明确不提供（非目标）

- **写 / 删除 / 恢复**别名：本端点只读；写操作一律走 `id`（ADR-0003 §2）。
- `include_deleted` / `?deleted=true` / 回收站 / 查看已删资源（R-DELETE-003；ADR-0004）。
- restore / undelete / purge / 批量操作。
- 全局 BareMetal `by-name` 别名（`hostname` 仅按 Cluster 唯一，全局不可判定；ADR-0003 §2 未授予）。
- NIC / IPAddress / VirtualMachine / Container / Service 的列表、计数、占位或关系入口（**R-QUERY-003 归 F010**；§15）。
- Cluster 状态 / 状态汇总 / 计数（R-CLUSTER-003；NQ-1）。
- DataCenter / 园区 / 机房 / 机柜 / U 位字段（§6、§13）。
- 自动资产发现 / 外部状态源 / 实时状态（§23、R-BM-006）。
- 分页之外的排序 / 状态筛选 / 导出（无已确认需求）；**Cluster 内关键字搜索不属于本端点**——其权威正文为 `docs/api/f018-cluster-keyword-search.md`（F018 独立只读端点 `GET /api/clusters/{cluster_id}/search`），本契约不新增 `keyword` 参数。
- API versioning / 游标分页（无需求）。

---

## 9. 与既有契约的关系

| 契约 | 关系 |
|---|---|
| `docs/api/api-conventions.md` | 通用规范来源；**不修改** |
| `docs/api/f001-cluster.md` | `by-name` 名称解析语义来源（字面值、大小写敏感、已删不参与）；本契约不修改其正文 |
| `docs/api/f002-bare-metal.md` | 成员资源表示、分页信封、`?cluster_id=` canonical、Empty/Not Found 语义的**权威**；本契约不修改其正文，只引用 |
| `docs/api/f014-soft-delete.md` | 软删过滤与无恢复语义来源；**不修改** |
| `docs/api/f009-cluster-resource-view.md` | **本文件**：F009 唯一新增端点的权威正文 |

GIT: NONE
