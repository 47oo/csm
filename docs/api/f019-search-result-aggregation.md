# API Contract — F019 搜索结果聚合视图

> Status: **READY**
> Feature: F019（E05，P1）
> Author Role: architect
> Source: `docs/product/requirements.md` §16 **R-QUERY-006**（直接产品依据）/ **R-QUERY-005（修订）** / R-QUERY-003 / R-QUERY-004；`DEC-022`（用户裁定）；`docs/api/api-conventions.md`；ADR-0003 / ADR-0004 / ADR-0005；`docs/api/f018-cluster-keyword-search.md`（匹配语义来源）；`docs/architecture/f019-search-result-aggregation-handoff.md`
> 本文件是 F019 前后端与测试的**共同协议**，并**取代** `docs/api/f018-cluster-keyword-search.md` 的「Response 200 / 结果顺序 / 排序相关排除项」。

---

## 1. 范围与前提

1. 本契约定义**唯一**产品 API：**`GET /api/clusters/{cluster_id}/search`**（Cluster 内关键字搜索的**聚合视图**）；method / path / 请求参数与 F018 **相同**，**仅响应形态被取代**。
2. 本契约不重新定义分页信封、错误信封、状态码、认证边界或通用 Empty / Not Found 语义，一律遵循 `docs/api/api-conventions.md`；各资源对象表示**复用**其 canonical `*Read` schema（f002 / f004 / f005 / f006 / f007 / f008）。
3. **匹配字段与匹配语义**（哪些字段参与、子串包含、不区分大小写、单关键字）**唯一权威仍是** `docs/api/f018-cluster-keyword-search.md` §2，本契约**不重述、不取代**。
4. **范围**：恒为**单个已选定 Cluster**；范围 = 该 Cluster 下每台活跃 BareMetal `B` 的 `{B} ∪ R(B)`，`R(B)` = R-QUERY-003「与 BareMetal 相关」（含间接）。`Cluster` 本身**不产生结果行**。
5. **只读**：无写 / 删除 / 恢复 / 批量端点或参数；无写副作用。
6. 认证：`/api/*`（除登录）要求认证；未认证 → `401 UNAUTHENTICATED`。
7. **不新增 / 不修改**任何领域对象、字段、关系、状态、唯一性规则。

---

## 2. 结果模型（聚合语义）

1. **单一扁平列表**：`items` 是一张**扁平行列表**，每行恰对应一个资源；**不按资源类型分区**。
2. **组织单元**：相邻、`group_key` 相同的行构成一个**组织单元** = 一个**命中项**（其自身至少一个字段命中关键字）及其**关联链**。每单元**首行** `role == "HIT"`，其后 `role == "RELATED"`。
3. **关联链**：命中项 `H` 的关联链 = `⋃_{B : H ∈ ({B}∪R(B))} ({B} ∪ R(B))`，**单元内按 `(resource_type, id)` 去重**。关联链成员判定**必须**经 `app.resource_views.service.get_related_resources`（R-QUERY-003 推导唯一实现）。
4. **关系扩展**：关联链资源**即使自身字段未命中关键字**也出现（`role == "RELATED"`）。
5. **跨单元不去重**：同一资源因属于**多个**命中项的关联链而在多个单元中**重复出现**。
6. **取代**：F018 的原「仅自身命中、无关联行」扁列表行为**不再提供**；两套形态**不并存**。

---

## 3. 端点

### `GET /api/clusters/{cluster_id}/search`

| 项 | 值 |
|---|---|
| Method | `GET` |
| Path | `/api/clusters/{cluster_id}/search` |
| Path parameter | `cluster_id`（integer，Cluster 代理主键） |
| Query parameter | `keyword`（string，**必填**）、`page`（integer，最小 1，默认 1）、`page_size`（integer，最小 1、最大 200，默认 50） |
| Request body | 无（客户端不得发送） |
| 认证 | **必需**（§6） |

**语义**

1. 先校验 `keyword`：缺失 → `400`；存在但为**空串或仅空白** → `400 VALIDATION_ERROR`（`details[].field == "keyword"`）。**不把空关键字解释为「返回该 Cluster 全部资源」。**
2. 再解析 `{cluster_id}`：Cluster **不存在或已逻辑删除** → `404 NOT_FOUND`（不区分）。
3. Cluster 活跃时，按 F018 §2 的匹配字段与匹配语义（子串包含 + 不区分大小写 + 单关键字）找出**命中项**，并为每个命中项展开其**关联链**，输出为 §2 的**单一扁平列表**。
4. `page` / `page_size` **按组织单元（命中项）计数**；同一单元的「命中行 + 关联行」**不相隔、不被分页拆散**。
5. **无命中** → `200` + `items == []` + `total == 0`（**Empty**，不得 `404`）。
6. 已逻辑删除的任一资源**不出现**在 `items`（命中行与关联行皆然），也不计入 `total`。
7. 结果为非跨 Cluster。
8. **`total` = 组织单元（命中项）全量数**；`items` 为该页单元的展平行，故 `len(items)` **可大于** `page_size`。

**结果顺序（REQUIRED）**

- **命中项（组织单元）排序键**（字典序）：
  1. **命中类别**：`0` = 命中字段含**标识字段** `hostname` / `name` / `ip_address` 之一；`1` = 仅命中描述性字段。
  2. `resource_type` 固定序：`BARE_METAL < NETWORK_INTERFACE < IP_ADDRESS < VIRTUAL_MACHINE < CONTAINER < SERVICE`。
  3. `id` 升序。
- **单元内关联行**按 `(resource_type 固定序, id)` 升序；命中行恒为单元首行。
- 该顺序使结果**确定、可复现、跨页稳定**。产品仅承诺「标识字段优先于描述性字段」；其余为**实现稳定性**，**不构成**按类型 / 时间 / 相似度的产品排序承诺（与 R-QUERY-005 一致）。

---

## 4. Response 200

信封：`SearchAggregationPage`。

```json
{
  "items": [ SearchResultRow, ... ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

### 4.1 `SearchResultRow`（封闭字段集合）

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `resource_type` | string，封闭六值 | 否 | `BARE_METAL` \| `NETWORK_INTERFACE` \| `IP_ADDRESS` \| `VIRTUAL_MACHINE` \| `CONTAINER` \| `SERVICE`（判别字段） |
| `id` | integer | 否 | 本行资源主键，与 `resource.id` 一致 |
| `role` | string，封闭两值 | 否 | `HIT`（单元首行）\| `RELATED` |
| `group_key` | `ResourceRef` | 否 | 本行所属单元命中项的身份；同单元各行一致 |
| `matched_fields` | string[] | 否（可为 `[]`） | 本行**自身**命中字段名，元素取自 f018 §2 对应类型字段清单，顺序为 f018 §2 声明顺序。`HIT` 行**非空**；`RELATED` 行可为 `[]`，或非空（该行自身也命中时） |
| `derivation_path` | `ResourceRef[]` \| null | **是** | `HIT` → `null`；`RELATED` → **非空**，长度 ≥ 2，首元素 = 本单元命中项、末元素 = 本行 |
| `resource` | object | 否 | 本行类型的 canonical `*Read`（逐字段复用；无 `deleted_at`、无新增字段） |

### 4.2 `ResourceRef`（封闭字段集合）

| 字段 | 类型 | nullable |
|---|---|---|
| `resource_type` | string，封闭六值 | 否 |
| `id` | integer | 否 |

### 4.3 推导路径

- `derivation_path` 是**从本单元命中项到本行的关系路径**（如 `IP 10.0.1.1 → 网卡 eth0 → 裸金属 cn001` 表示为 3 个 `ResourceRef`）。
- 推导**仅使用单元内已物化的 canonical `*Read` 对象**与 domain-model §6 已确认关系方向；**不判定成员资格**（成员资格来自 `get_related_resources`），**不发起额外 DB 查询**。
- 头部 / 尾部：首元素恒为本单元命中项，末元素恒为本行。

### 4.4 示例（复现用户场景）

`cn001`（id 101）仅挂 `eth0`（id 12）与 `10.0.1.1/16`（id 41），搜索 `10.0.1`：

```json
{
  "items": [
    {
      "resource_type": "IP_ADDRESS",
      "id": 41,
      "role": "HIT",
      "group_key": { "resource_type": "IP_ADDRESS", "id": 41 },
      "matched_fields": ["ip_address"],
      "derivation_path": null,
      "resource": {
        "id": 41, "network_interface_id": 12, "ip_address": "10.0.1.1/16",
        "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z"
      }
    },
    {
      "resource_type": "BARE_METAL",
      "id": 101,
      "role": "RELATED",
      "group_key": { "resource_type": "IP_ADDRESS", "id": 41 },
      "matched_fields": [],
      "derivation_path": [
        { "resource_type": "IP_ADDRESS", "id": 41 },
        { "resource_type": "NETWORK_INTERFACE", "id": 12 },
        { "resource_type": "BARE_METAL", "id": 101 }
      ],
      "resource": {
        "id": 101, "cluster_id": 3, "hostname": "cn001", "status": "IDLE", "vendor": null,
        "model": null, "serial_number": null, "cpu": null, "memory": null, "gpu": null,
        "storage": null, "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z"
      }
    },
    {
      "resource_type": "NETWORK_INTERFACE",
      "id": 12,
      "role": "RELATED",
      "group_key": { "resource_type": "IP_ADDRESS", "id": 41 },
      "matched_fields": [],
      "derivation_path": [
        { "resource_type": "IP_ADDRESS", "id": 41 },
        { "resource_type": "NETWORK_INTERFACE", "id": 12 }
      ],
      "resource": {
        "id": 12, "bare_metal_id": 101, "name": "eth0", "technology_type": "Ethernet",
        "purpose": "Management", "created_at": "2026-09-18T10:00:00Z", "updated_at": "2026-09-18T10:00:00Z"
      }
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

> 注：`technology_type` / `purpose` 为**大小写敏感的封闭枚举**，canonical 字面值为 `Ethernet / InfiniBand / RoCE / Other` 与 `BMC / Management / Business / Compute / Storage / DataTransfer / Other`（见 `docs/api/f004-network-interface.md`）。

### 4.5 跨单元不去重（示意）

若某命中项 `A` 与另一命中项 `B` 的关联链同时包含资源 `X`，则 `X` 在结果中**出现两次**，分属 `A` 的单元与 `B` 的单元（`group_key` 不同），**不合并**。

---

## 5. Error Semantics

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
| — | `403` | `FORBIDDEN` | **不存在触发路径**（V1 仅两态；码值仅为通用契约保留） |

**状态判定优先级（REQUIRED）**

```text
401（认证中间件，先于路由） > 400（keyword / 分页参数校验） > 404（Cluster 解析） > 200
```

- 空 / 仅空白 keyword 的 `400` **先于** Cluster 的 `404`。
- `404` **同时**覆盖「Cluster 不存在」与「Cluster 已逻辑删除」，不区分。

**错误信封**：复用 `api-conventions.md` §5 与 `app/common/errors.py` / `error_handlers.py`；前端按 `error.code` 分支，**不得解析 `message`**。

`404` 示例：

```json
{ "error": { "code": "NOT_FOUND", "message": "资源不存在或已被逻辑删除", "details": [] } }
```

---

## 6. Empty / Not Found 语义

| 情形 | 响应 |
|---|---|
| Cluster 不存在 | `404 NOT_FOUND` |
| Cluster 已逻辑删除 | `404 NOT_FOUND`（与不存在不区分） |
| Cluster 活跃、关键字有效、无任何命中 | `200`，`items == []`，`total == 0`（**Empty**） |

前端必须为 **Empty** 与 **Not Found** 渲染**不同**状态，并与 `400` 互不相同（R-QUERY-004）。

---

## 7. 认证边界

- 所有 `/api/*`（除登录）要求认证；未认证 → `401 UNAUTHENTICATED`，不返回任何资源数据、不改变任何数据。
- 认证成功即可访问；无需角色 / 权限（V1 无 RBAC）。
- 本端点在 `/api` 前缀下，由既有认证中间件自动覆盖，无需白名单成员。

---

## 8. 明确不提供（非目标）

- 写 / 删除 / 恢复 / 批量端点或参数；`include_deleted` / 回收站 / 查看已删资源。
- 跨 Cluster / 全局搜索；「当前选定 Cluster」为前置条件。
- 多关键字 / AND / OR / 拆分 / 分词 / 拼写纠错 / 相似度 / 打分式相关性排序。
- 排序**参数**（本契约的排序为确定性实现，不接受调用方指定排序字段）；状态筛选 / 结构化筛选；导出（CSV / Excel）；除 `total` 外的统计 / 按类型计数 / 仪表盘。
- 在既有 per-resource 列表端点追加 `keyword` 参数。
- 空关键字返回「该 Cluster 全部资源」。
- 自动资产发现 / 外部平台同步 / 实时状态源。
- API versioning / 游标分页。

---

## 9. 与既有契约的关系

| 契约 | 关系 |
|---|---|
| `docs/api/api-conventions.md` | 通用规范来源；**不修改** |
| `docs/api/f018-cluster-keyword-search.md` | **匹配字段与匹配语义**（§2）仍为其唯一权威，本契约引用不重述；其 **§3 Response 200 / 结果顺序**与 **§7 排序相关排除项**被**本契约取代** |
| `docs/api/f001-cluster.md` | Cluster 表示与 `by-name` 解析语义来源；**不修改** |
| `docs/api/f002` / `f004` / `f005` / `f006` / `f007` / `f008` | 各资源 canonical `*Read` 来源；**不修改** |
| `docs/api/f009` / `f010` | F010 的 `get_related_resources` 被本契约**复用**（不修改其正文） |
| `docs/api/f014-soft-delete.md` | 软删过滤与无恢复语义来源；**不修改** |
| `docs/api/f019-search-result-aggregation.md` | **本文件**：聚合响应的权威正文 |
