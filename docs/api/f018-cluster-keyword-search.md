# API Contract — F018 集群内资源关键字搜索

> Status: **READY**
> Feature: F018（E05，P1）
> Author Role: architect
> Source: `docs/product/requirements.md` §16 R-QUERY-005（直接产品依据）、R-QUERY-003 / R-QUERY-004、§17 R-DELETE-002、§19、§22；`docs/api/api-conventions.md`（READY）；ADR-0003 / ADR-0004 / ADR-0005（ACCEPTED）；`docs/architecture/f010-resource-detail-handoff.md`、`docs/api/f010-resource-detail.md`、`docs/product/handoffs/f018-cluster-keyword-search.md`
> 本文件是 F018 前后端与测试的**共同协议与单一权威**。

---

## 1. 范围与前提

1. 本契约定义 F018 唯一新增的产品 API：**`GET /api/clusters/{cluster_id}/search`**（Cluster 内关键字搜索），共 **1 个端点**（§3）。
2. 本契约不重新定义分页信封、错误信封、状态码、认证边界或通用 Empty / Not Found 语义，一律遵循 `docs/api/api-conventions.md`；各资源对象表示**复用**其 canonical `*Read` schema（f002 / f004 / f005 / f006 / f007 / f008）。
3. **范围（R-QUERY-005）**：恒为**单个已选定 Cluster**；命中对象 = 该 Cluster 下的活跃 BareMetal，**以及**与之相关联的活跃 NetworkInterface / IPAddress / VirtualMachine / Container / Service。「相关联」的判定**直接引用** R-QUERY-003 已确认的「与 BareMetal 相关」定义（**含「含间接」推导**），本契约不重述、不重建该推导。
4. **Cluster 本身不产生结果行**（R-QUERY-005）；`Cluster.name` 不参与命中。
5. **只读**：本端点不改动任何数据；无写 / 删除 / 恢复 / 批量端点或参数，无写副作用。
6. 认证：`/api/*`（除 `POST /api/auth/login`）要求认证；未认证 → `401 UNAUTHENTICATED`（ADR-0005）。
7. 本 Feature **不新增 / 不修改**任何领域对象、字段、关系、状态、唯一性规则。

---

## 2. 匹配语义

| 项 | 值 |
|---|---|
| 关键字数量 | **单关键字**（不拆分 AND / OR、不分词） |
| 模糊定义 | **子串包含**：输入是目标字段值的一段**连续子串**即命中（`contains` / `LIKE %kw%` 语义） |
| 大小写 | **不区分大小写**（`ABC` 与 `abc` 命中同一结果）。**该语义仅用于本端点搜索匹配**，**不改变** §22 名称唯一性比较、`by-name` 字面值解析、用户名查找禁止 `lower()/ILIKE` 的既有规则 |
| 容错 / 相似度 | 本 Feature **不做**容错 / 相似度 / 拼写纠错级模糊（属另一条产品规则） |
| 关键字处理 | 通过「非空白」校验后，关键字**原样**参与匹配（不 trim、不做归一化） |

**匹配字段（唯一权威清单）**

| `resource_type` | 参与匹配的字段 |
|---|---|
| `BARE_METAL` | `hostname`、`vendor`、`model`、`serial_number`、`cpu`、`memory`、`gpu`、`storage` |
| `NETWORK_INTERFACE` | `name`、`technology_type`、`purpose` |
| `IP_ADDRESS` | `ip_address` |
| `VIRTUAL_MACHINE` | `name`、`cpu`、`memory`、`disk`、`os`、`hypervisor`、`owner` |
| `CONTAINER` | `name`、`image`、`cpu`、`memory`、`owner` |
| `SERVICE` | `name`、`service_type`、`url`、`port`、`protocol`、`owner`、`description` |

- 字段值一律按**文本**参与子串匹配（含 `port` / `cpu` / `memory` / `disk` 等数值型字段，这是「子串包含」的直接含义）。
- **明确不参与匹配**：资源之间的关系外键（`cluster_id` / `bare_metal_id` / `network_interface_id` / `carrier_type` / `carrier_id`）、`status`、`created_at` / `updated_at`、`carriers`、`deleted_at`。

---

## 3. 端点

### `GET /api/clusters/{cluster_id}/search` — 在单个 Cluster 内按关键字搜索

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/clusters/{cluster_id}/search` |
| Path parameter | `cluster_id`（integer，Cluster 代理主键） |
| Query parameter | `keyword`（string，**必填**）、`page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§6） |

**语义**

1. 先校验 `keyword`：缺失 → `400`（FastAPI 参数校验）；存在但为**空串或仅空白** → `400 VALIDATION_ERROR`（`details[].field == "keyword"`）。**不把空关键字解释为「返回该 Cluster 全部资源」。**
2. 再解析 `{cluster_id}`：Cluster **不存在或已逻辑删除** → `404 NOT_FOUND`（两者不区分）。
3. Cluster 活跃时，返回该 Cluster 的**活跃** BareMetal 及其 R-QUERY-003 五类关联资源中，**任一匹配字段的子串包含关键字**（不区分大小写）的对象，汇总为**单一混合列表**（**不按资源类型分组**）。
4. 每条结果携带其**命中字段**（`matched_fields`）。
5. **无命中** → `200` + `items == []` + `total == 0`（**Empty**，不得 `404`）。
6. 已逻辑删除的任一资源**不出现**在 `items`，也不计入 `total`（R-DELETE-002）。
7. 结果为非跨 Cluster：绝不返回其它 Cluster 的资源。

**Response 200**（`Page[SearchResultItem]`）

```json
{
  "items": [
    {
      "resource_type": "BARE_METAL",
      "id": 101,
      "matched_fields": ["hostname", "vendor"],
      "resource": {
        "id": 101,
        "cluster_id": 3,
        "hostname": "cn001-gpu",
        "status": "IDLE",
        "vendor": "NVIDIA",
        "model": null,
        "serial_number": null,
        "cpu": null,
        "memory": null,
        "gpu": null,
        "storage": null,
        "created_at": "2026-09-18T10:00:00Z",
        "updated_at": "2026-09-18T10:00:00Z"
      }
    },
    {
      "resource_type": "IP_ADDRESS",
      "id": 41,
      "matched_fields": ["ip_address"],
      "resource": {
        "id": 41,
        "network_interface_id": 12,
        "ip_address": "10.0.1.1/16",
        "created_at": "2026-09-18T10:00:00Z",
        "updated_at": "2026-09-18T10:00:00Z"
      }
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 50
}
```

- `resource_type`：**封闭枚举**，取值 `BARE_METAL` | `NETWORK_INTERFACE` | `IP_ADDRESS` | `VIRTUAL_MACHINE` | `CONTAINER` | `SERVICE`。
- `id`：该资源的主键（与 `resource.id` 一致）。
- `matched_fields`：**非空**字符串数组，元素取自 §2 对应类型的字段清单，顺序为 §2 声明顺序；至少 1 个（否则不构成命中）。
- `resource`：该类型的 canonical `*Read` 对象，字段集合**恰为**对应契约定义，逐字段复用；不存在 `deleted_at`，不新增字段。
- `total`：全量命中数（不受本页限制）。
- `page` / `page_size`：与请求回显一致。
- **结果顺序**：实现按 `(resource_type, id)` 物化以保证分页稳定。**本契约不承诺任何排序语义**（不承诺默认排序、按类型 / 时间 / 相关性排序）；`(resource_type, id)` 仅为分页稳定性，不构成「分组」，调用方不得据此承诺顺序。

**Error Semantics**

| 情形 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|
| `keyword` 缺失 | `400` | `VALIDATION_ERROR` | `"keyword"` |
| `keyword` 为空串 / 仅空白 | `400` | `VALIDATION_ERROR` | `"keyword"` |
| `cluster_id` 非整数 | `400` | `VALIDATION_ERROR` | `"cluster_id"` |
| `page` 非整数 / `< 1` | `400` | `VALIDATION_ERROR` | `"page"` |
| `page_size` 非整数 / `< 1` / `> 200` | `400` | `VALIDATION_ERROR` | `"page_size"` |
| `cluster_id` 不存在**或**对应 Cluster 已被逻辑删除 | `404` | `NOT_FOUND` | —（`details == []`） |
| 未认证 | `401` | `UNAUTHENTICATED` | — |
| 未预期错误 | `500` | `INTERNAL_ERROR` | — |

- `404` **同时**覆盖「Cluster 不存在」与「Cluster 已逻辑删除」，两者**不做区分**（`api-conventions.md` §6；与 F001 / F009 一致）。
- `403 FORBIDDEN` **不存在触发路径**（V1 仅两态；码值仅为通用契约保留）。

**状态判定优先级（REQUIRED）**

```text
401（认证中间件，先于路由） > 400（keyword / 分页参数校验） > 404（Cluster 解析） > 200
```

- 空 / 仅空白 keyword 的 `400` **先于** Cluster 的 `404`：请求本身无效时不做资源解析。

**Empty / Not Found 语义**

| 情形 | 响应 |
|---|---|
| Cluster 不存在 | `404 NOT_FOUND` |
| Cluster 已逻辑删除 | `404 NOT_FOUND`（与不存在不区分） |
| Cluster 活跃、关键字有效、无任何命中 | `200`，`items == []`，`total == 0`（**Empty**） |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**的状态（R-QUERY-004），并与 `400`（校验失败）互不相同。

**范围推导与复用（REQUIRED）**

1. 判定顺序固定：**先** `clusters.service.get_cluster_by_id` 确认 Cluster 活跃（未命中 → `404`，**唯一 404 网关**），**后**派生范围并匹配；子资源缺失绝不诱发 `404`。
2. 命中范围 = 「该 Cluster 下每台活跃 BareMetal `B` 的 `{B} ∪ R-QUERY-003 关联集合`」。关联集合的判定**必须**经 **`app.resource_views.service.get_related_resources`**（F010 的 R-QUERY-003 推导**唯一实现**）取得，**不得另写一份**。
3. 活跃过滤统一经 `app/db/active.py`；本端点实现**不得**引入第二条 `deleted_at` 过滤 / 写入路径（ADR-0004）。

---

## 4. 错误信封

复用 `docs/api/api-conventions.md` §5 的统一信封与 `app/common/errors.py` / `error_handlers.py`，不另立一套。前端按 `error.code` 分支，**不得解析 `message`**。

`404 NOT_FOUND` 示例：

```json
{ "error": { "code": "NOT_FOUND", "message": "资源不存在或已被逻辑删除", "details": [] } }
```

`400 VALIDATION_ERROR`（空关键字）示例：

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "请求校验失败",
  "details": [ { "field": "keyword", "code": "INVALID", "message": "关键字不能为空" } ] } }
```

---

## 5. 状态码汇总（本契约范围）

| 状态码 | 何时出现 | `error.code` |
|---|---|---|
| `200` | 搜索成功（含空列表） | — |
| `400` | `keyword` 缺失 / 空 / 仅空白；分页参数非法 | `VALIDATION_ERROR` |
| `401` | 未认证 | `UNAUTHENTICATED` |
| `404` | Cluster 不存在或已被逻辑删除 | `NOT_FOUND` |
| `500` | 未预期服务端错误 | `INTERNAL_ERROR` |
| `403` | **不存在触发路径**（V1 仅两态） | `FORBIDDEN` |

---

## 6. 认证边界

- 所有 `/api/*`（除登录）要求认证；未认证访问本端点 → `401 UNAUTHENTICATED`，且不返回任何资源数据、不改变任何数据（R-AUTH-001/002；ADR-0005）。
- 认证成功即可访问；无需任何角色 / 权限（R-AUTH-003；V1 无 RBAC）。
- 本端点在 `/api` 前缀下，由既有 F013 中间件自动覆盖，无需白名单成员。

---

## 7. 明确不提供（非目标）

- 写 / 删除 / 恢复 / 批量端点或参数；`include_deleted` / 回收站 / 查看已删资源。
- **跨 Cluster / 全局搜索**；「当前选定 Cluster」为**前置条件**。
- **多关键字 / AND / OR 拆分 / 分词 / 拼写纠错 / 相似度 / 相关性排序**。
- **排序参数**（本契约不承诺排序）；**状态筛选 / 结构化筛选**；**导出**（CSV / Excel）；除 `total` 外的统计 / 按类型计数 / 仪表盘。
- 在既有 per-resource 列表端点追加 `keyword` 参数（本 Feature 由**单一独立端点**提供；f005 / f009 / f010 / f002 的「关键字禁止」立场已按 `DEC-021` 同步修订并指向本契约）。
- 在空关键字时返回「该 Cluster 全部资源」（明确禁止）。
- 自动资产发现 / 外部平台同步 / 实时状态源（§23；R-VM-002 / R-BM-007 / §10）。
- API versioning / 游标分页。

---

## 8. 与既有契约的关系

| 契约 | 关系 |
|---|---|
| `docs/api/api-conventions.md` | 通用规范来源；**不修改** |
| `docs/api/f001-cluster.md` | Cluster 表示与 `by-name` 解析语义来源；**不修改** |
| `docs/api/f002-bare-metal.md` | `BareMetalRead`、`?cluster_id=` canonical、分页 / Empty-Not Found 语义来源；**立场修订**：有关「筛选」排除项按 `DEC-021` 限定并指向本契约 |
| `docs/api/f004-network-interface.md` / `f005-ip-address.md` / `f006-virtual-machine.md` / `f007-container.md` / `f008-service.md` | 各资源 canonical `*Read` 与过滤语义来源；`f005` 的「关键字禁止」立场按 `DEC-021` 修订并指向本契约 |
| `docs/api/f009-cluster-resource-view.md` / `f010-resource-detail.md` | Cluster 视角与 R-QUERY-003 推导先例；**立场修订**：「关键字」排除项按 `DEC-021` 修订并指向本契约；F010 的 `get_related_resources` 被本契约**复用**（不修改其正文） |
| `docs/api/f014-soft-delete.md` | 软删过滤与无恢复语义来源；**不修改** |
| `docs/api/f018-cluster-keyword-search.md` | **本文件**：F018 唯一新增端点的权威正文 |
