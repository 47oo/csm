# Architecture Handoff — F019 搜索结果聚合视图

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-20
> Feature: **F019 — 搜索结果聚合视图**（Search Result Aggregation）
> 上游：`docs/product/handoffs/f019-search-result-aggregation.md`（`READY FOR ARCHITECT`，无 blocking）；`DEC-022` 用户裁定（8 项）

## Feature

**F019 — 搜索结果聚合视图**

- Epic E05 / Milestone M9；`layers = {database: false, backend: true, frontend: true}`
- `Contract = REQUIRED`（本次落盘 `docs/api/f019-search-result-aggregation.md`，Status = **READY**）
- 依赖 F018（已 DONE，merge `f1ac71b`）与 F010 `get_related_resources`（唯一关联推导实现）

## Context

**目标**：把 F018「仅自身命中字段的资源」的扁平列表，改为以**命中项 + 其关联链**为组织单元的单一扁平混合列表：命中行标「命中」、关联行标「关联」并携带推导路径；做关系扩展；跨组不去重；按字段优先级排序；取代 F018 扁列表。

**对现有系统的影响（已核实）**

- **已有**：`backend/app/search/**`（F018 只读搜索，端点 `GET /api/clusters/{cluster_id}/search`）、`backend/app/resource_views/service.py::get_related_resources`（R-QUERY-003 推导唯一实现）、各资源 canonical `*Read`、`app/db/active.py`、`app/common/pagination.py`、`docs/api/f018-cluster-keyword-search.md`、`docs/api/api-conventions.md`、`frontend/src/api/search.ts`、`frontend/src/pages/SearchResultsPage.vue`、`frontend/src/App.vue` 外壳搜索入口、既有 guard 套件。
- **不存在**：任何聚合 / 分组 / 关系扩展 / 排序能力；F018 响应为纯扁列表。
- **不新增 / 不修改**任何领域对象、字段、关系、状态、唯一性规则（与 Product Handoff 一致）。

**方案要点**

1. 复用同一端点，**取代其响应形态**为「单元级分页的扁平聚合行列表」。
2. 关联链成员判定**复用 `get_related_resources`**：为命中项找到其 R-QUERY-003 锚定 `BareMetal`，取其 `{B} ∪ R(B)`；不另写关联推导。
3. 匹配语义、字段清单、只读、软删、认证、404/Empty/400 **全部沿用 F018**；search 模块**不得出现 `deleted_at`**。
4. 排序、聚合、去重、路径推导全部在 Python 侧完成，**无 schema 变更**。

## Decisions

### 1. 契约形态（NQ-B）— 取代 F018 响应，不新增端点 / 参数

**裁定**：保持**同一端点** `GET /api/clusters/{cluster_id}/search`（method / path / query 参数不变），**取代其 Response 200 的语义**。

**理由**

- DEC-022 第 8 点：聚合语义**取代** F018 扁列表行为，**二者不同时并存**（AC-A7）。新增端点或 `mode` 参数会让两套互相冲突的结果形态并存，违反该点。
- DEC-022 第 1 点要求顶层仍是**一张单一扁平混合列表**（AC-A1）；在同一端点内改响应形态即可表达，无需第二端点。
- 前端入口（`App.vue` 外壳）与「先选定 Cluster」前置不变（NQ-9 沿用 F018）；换端点会迫使入口分叉，无收益。
- 契约落盘：**新增权威契约 `docs/api/f019-search-result-aggregation.md`**（Status = READY）。`docs/api/f018-cluster-keyword-search.md` **不再持有响应定义**：其 §3「Response 200 / 结果顺序」与 §7 中与排序相关的排除项改为指向 f019；其 **§2 匹配字段与匹配语义仍是唯一权威，未被取代**（避免重复维护）。

**拒绝的替代方案**

| 方案 | 拒绝理由 |
|---|---|
| 新增独立聚合端点（如 `/search/aggregated`） | 与「取代、不并存」冲突；前端入口 / 前置分叉；契约面 ×2 |
| 加 `?expand=true` / `mode=` 参数 | 同一端点两种响应形态并存，调用方与 guard 需双分支；AC-A7 否决 |
| 前端多请求拼接 / 前端推导关联 | 与 F010 已否决「浏览器端拼接」立意冲突；违反搜索模块复用 R-QUERY-003 唯一推导的约束 |

### 2. 关联链展开映射（NQ-D）— 按 R-QUERY-003 锚定，复用 `get_related_resources`

**定义（Architecture 裁定，Product 未规定）**

- 对每个活跃 `BareMetal B`，其**锚定组** `G(B) = {B} ∪ R(B)`，其中 `R(B)` = R-QUERY-003「与 B 相关」集合（含间接），**唯一来源**为 `app.resource_views.service.get_related_resources(session, B)`。
- 命中的资源 `H` 的**锚定集** `A(H) = { B : H ∈ G(B) }`（在 F018 已做的「按 B 物化候选集」过程中天然可得）。
- 命中项 `H` 的**关联链** `chain(H) = ⋃_{B ∈ A(H)} G(B)`；**单元内按 `(resource_type, id)` 去重**。
- **组织单元** = 一个**不同的命中项** `H`（`(resource_type, id)` 唯一）。同一 `H` 关联多个 `B` 时合并为一个单元（union）。跨单元**不去重**。
- **复用而非重写**：`G(B)` 由 `get_related_resources` 产出（每个 `B` 恰好调用一次并缓存）；搜索模块**不得**自写任何 FK / 软删 / 载体并集 / 间接传递谓词，**不得**出现 `deleted_at`。

**逐资源类型映射（命中项 → 其关联链成员 / 锚定）**

| 命中项类型 | 锚定 `B`（`A(H)`）来源 | `chain(H)` 内容 | 推导路径示例（命中 → 关联） |
|---|---|---|---|
| `BARE_METAL` | `B = H` | `{H} ∪ R(H)`（其 NIC / IP / VM / Container / Service） | `BareMetal cn001 → NetworkInterface eth0` |
| `NETWORK_INTERFACE` | `B = H.bare_metal_id` | `{B} ∪ R(B)` | `NIC eth0 → BareMetal cn001` |
| `IP_ADDRESS` | `B = B(NIC(H))`（经上游 NIC） | `{B} ∪ R(B)` | `IP 10.0.1.1 → NIC eth0`、`IP 10.0.1.1 → NIC eth0 → BareMetal cn001` |
| `VIRTUAL_MACHINE` | `B = H.bare_metal_id` | `{B} ∪ R(B)` | `VM v1 → BareMetal cn001` |
| `CONTAINER` | `B` = 其载体（BM，或 VM 的 BM）所属 BM | `{B} ∪ R(B)` | `Container c1 → VM v1 → BareMetal cn001`（或 `→ BareMetal cn001`） |
| `SERVICE` | 其载体集合所触达的 BM（可多个） | `⋃_{B∈A(H)} G(B)` | `Service s1 → Container c1 → VM v1 → BareMetal cn001` |

**用户示例复现（强制）**：输入某 IP 片段 → 命中 `IP_ADDRESS 10.0.1.1/16`，其锚定 `B = cn001`；`G(cn001)` 含 `NetworkInterface eth0` 与 `BareMetal cn001`，故结果包含 **该 IP、其 NIC（eth0）、其 BareMetal（cn001）**，且 NIC 与 BM **即使自身字段未命中关键字**也出现（标注「关联」）。**该唯一自洽推导与用户示例语义一致 → 不触发 `RETURN TO PRODUCT`。**

**为什么不采用「仅祖先路径」**：只列 `IP → NIC → BM` 的祖先路径需要额外遍历 FK / 载体关系来自行判定关联，属**第二份关联推导**，违反 Product Handoff 的复用约束；且会使「命中 BareMetal 自身」时无任何上下文，语义不对称。锚定组方案同时满足复用约束、示例与对称性。

### 3. tie-break（确定性兜底顺序）

命中项（组织单元）排序键，**字典序**：

1. **命中类别**：`0` = 命中字段含**标识字段**（`hostname` / `name` / `ip_address`）之一；`1` = 仅命中**描述性字段**（AC-A6）。
2. **`resource_type` 固定序**（内部确定性，非产品排序承诺）：`BARE_METAL < NETWORK_INTERFACE < IP_ADDRESS < VIRTUAL_MACHINE < CONTAINER < SERVICE`。
3. **`id` 升序**。

单元内关联行排序键：`(resource_type 固定序, id)` 升序。命中行恒为该单元**第一行**。

- 该 tie-break 保证**可复现、可测试、跨页稳定**；产品仅承诺「标识字段优先于描述性字段」，其余为**实现稳定性**，不构成「按类型 / 时间排序」的产品承诺（与 R-QUERY-005 一致）。

### 4. 分页形态 — 条目级（组织单元级）

- `page` / `page_size` **按组织单元（= 命中项）计数**，默认 `page_size=50`、上限 `200`、最小 `1`（沿用 `app/common/pagination.py`）。
- **同一单元的「命中行 + 其关联行」绝不被分页拆散**（满足 AC-A8：关联资源紧随命中行）。
- `total` = **组织单元全量数**（= 不同命中项数；与 F018 `total` 的「命中数」语义一致）。
- `items` 为该页单元的**扁平行**（命中行 + 关联行）；因此 `len(items)` **可大于** `page_size`（每单元 ≥ 1 行）。
- 跨页不重不漏：单元按第 3 节排序键全序化后，按 `[offset, offset+limit)` 切片。

### 5. `layers.database` — `false`

- **无 schema 变更、无 migration、无 extension、无新索引、无新表**。`database_design: NOT_REQUIRED`。
- 理由（沿用并强化 F018 裁定 2）：候选集必须经 `get_related_resources`（多表 + N:M 载体并集）**在 Python 侧物化**；`keyword` 不下推 SQL，故 `pg_trgm` / `tsvector` **用不上**。F019 新增的「按命中项分组 / 去重 / 字段优先级排序 / 路径推导」全部发生在已物化候选集上，访问模式与 F018 **完全相同**（每 `BareMetal` 一次推导，缓存 `G(B)`）。
- 失效阈值：单 Cluster 活跃 BareMetal 达 **~10³ 台**或搜索 QPS 显著上升时重估（预留「集合式推导」路径 A，仍 `database: false`）。本 Feature 不引入批量化。

### 6. 响应信封（JSON Schema 与字段）

顶层信封（取代 f018 §3 Response）：

```json
{
  "items": [ /* SearchResultRow，扁平列表；单元内命中行紧随其关联行 */ ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

`SearchResultRow` 字段：

| 字段 | 类型 | nullable | 说明 |
|---|---|---|---|
| `resource_type` | string（封闭六值） | 否 | 本行资源类型（判别字段） |
| `id` | integer | 否 | 本行资源主键（与 `resource.id` 一致） |
| `role` | string（`HIT` \| `RELATED`） | 否 | 本行在**本单元**的角色；每单元首行为 `HIT` |
| `group_key` | object `{resource_type, id}` | 否 | 本行所属**组织单元**的命中项身份；同单元各行共享同一值 |
| `matched_fields` | string[] | 否（可为 `[]`） | 本行**自身**命中字段；`HIT` 恒非空；`RELATED` 可为空或非空（该行自身也命中时） |
| `derivation_path` | object[] \| null | **是** | `HIT` → `null`；`RELATED` → 非空，首元素 = 本单元命中项、末元素 = 本行，中间为途经资源 |
| `resource` | object | 否 | 本行类型的 canonical `*Read`（逐字段复用，不新增字段、不含 `deleted_at`） |

`derivation_path` 元素（`ResourceRef`）：`{ "resource_type": <六值>, "id": <integer> }`，长度 ≥ 2，两端分别为命中项与本行。

**`derivation_path` 确定性推导（REQUIRED）**：以单元的锚定 `B*`（若本行属于多个锚定组，取 **`id` 最小的 `B*`**）为根，用**单元内已物化的 `*Read` 对象**的 canonical 标识字段建立父指针：

- `BARE_METAL → 无`；`NETWORK_INTERFACE → bare_metal_id`；`IP_ADDRESS → network_interface_id`；`VIRTUAL_MACHINE → bare_metal_id`；
- `CONTAINER → (carrier_type, carrier_id)`（若载体为 VM，再经该 VM 的 `bare_metal_id`）；
- `SERVICE → carriers` 中**位于本组内**、且 `(carrier_type rank: BARE_METAL<VIRTUAL_MACHINE<CONTAINER, carrier_id)` 最小者。

路径 = `pathUp(H) ++ reverse(pathUp(M))[1:]`，其中 `pathUp(X) = [X, parent(X), …, B*]`。该计算**仅使用单元内已有对象与 domain-model §6 已确认关系方向**，**不判定成员资格**（成员资格来自 `get_related_resources`），**不发起额外 DB 查询**。

**`HIT` 行是否携带命中字段（NQ-F）**：**携带**——`HIT` 行 `matched_fields` 非空（沿用 F018 PROPOSED-2 取向：多字段命中显示全部命中字段，按契约 §2 声明顺序）。`RELATED` 行携带其**自身**命中字段（通常为 `[]`；若该行自身也命中则非空，见 PROPOSED-1）。

**示例（复现用户场景）**：`cn001`（id 101）仅挂 `eth0`（id 12）与 `10.0.1.1/16`（id 41），搜索 `10.0.1`：

```json
{
  "items": [
    { "resource_type": "IP_ADDRESS", "id": 41, "role": "HIT",
      "group_key": { "resource_type": "IP_ADDRESS", "id": 41 },
      "matched_fields": ["ip_address"], "derivation_path": null,
      "resource": { "id": 41, "network_interface_id": 12, "ip_address": "10.0.1.1/16",
                    "created_at": "…", "updated_at": "…" } },
    { "resource_type": "BARE_METAL", "id": 101, "role": "RELATED",
      "group_key": { "resource_type": "IP_ADDRESS", "id": 41 },
      "matched_fields": [],
      "derivation_path": [ { "resource_type": "IP_ADDRESS", "id": 41 },
                           { "resource_type": "NETWORK_INTERFACE", "id": 12 },
                           { "resource_type": "BARE_METAL", "id": 101 } ],
      "resource": { "id": 101, "cluster_id": 3, "hostname": "cn001", "…": "…" } },
    { "resource_type": "NETWORK_INTERFACE", "id": 12, "role": "RELATED",
      "group_key": { "resource_type": "IP_ADDRESS", "id": 41 },
      "matched_fields": [],
      "derivation_path": [ { "resource_type": "IP_ADDRESS", "id": 41 },
                           { "resource_type": "NETWORK_INTERFACE", "id": 12 } ],
      "resource": { "id": 12, "bare_metal_id": 101, "name": "eth0", "…": "…" } }
  ],
  "total": 1, "page": 1, "page_size": 50
}
```

> 注：canonical 枚举字面值为大小写敏感的 `technology_type = Ethernet / InfiniBand / RoCE / Other`、`purpose = BMC / Management / Business / Compute / Storage / DataTransfer / Other`（见 f004 契约）；示例若需展开请按 canonical 字面值。

### 7. 软删 / 认证 / 错误语义 / Empty（沿用 F018）

- **只读**：无写 / 删除 / 恢复端点或参数（AC-01）。
- **软删**：命中行**与关联行**均过滤软删；过滤**仅经 `get_related_resources` 与既有 repository** 传递，`backend/app/search/**` **不得出现 `deleted_at`**（沿用 G-018-3 / G-018-4 的 token guard 精神，ADR-0004）。
- **认证**：`/api/*` 认证中间件自动覆盖；未认证 → `401 UNAUTHENTICATED`（AC-03）。
- **错误语义 / 状态优先级**（不变）：`401`（中间件）> `400`（`keyword` 缺失 / 空 / 仅空白、分页参数非法）> `404`（Cluster 不存在 / 已软删，唯一网关）> `200`。
- **Not Found / Empty**（R-QUERY-004）：Cluster 不存在或已软删 → `404 NOT_FOUND`；Cluster 活跃但无命中 → `200` + `items == []` + `total == 0`（**Empty**，不得 404）。
- **大小写**：不区分大小写**仅限搜索匹配**（仅 `backend/app/search/**` 做 `.lower()`）；§22 / `by-name` / 用户名查找零改动。
- **不跨 Cluster**；**单关键字 / 子串包含**；**不引入自动发现 / 外部同步 / 导出 / 状态筛选 / 统计式聚合**。

### 8. 前端契约

- 复用同一端点 `GET /api/clusters/{cluster_id}/search`；**单请求**，不做浏览器端拼接 / 关联推导。
- **渲染**：按 `items` 顺序遍历；连续的相同 `group_key` 为一个组织单元：
  - `role == "HIT"` 行 → 渲染为**命中行**，徽标「命中」，展示 `matched_fields` 标签与资源标识字段；
  - `role == "RELATED"` 行 → 渲染为**缩进关联行**，徽标「关联」，展示 `derivation_path` 文案（如 `IP 10.0.1.1 → 网卡 eth0 → 裸金属 cn001`，由 `resource_type` 序列 + 各行标识字段生成，具体文案由 Frontend 决定）。
- **三态**：Loading / Empty（`200` + `items == []`，「无匹配结果」，不得渲染为错误、不得触发全局 401）/ Error（按 `error.code` 分支，不解析 `message`：`NOT_FOUND` → 「未找到资源」；`VALIDATION_ERROR` → 校验失败）。
- **入口**：沿用 F018 `App.vue` 外壳搜索区与「先选定 Cluster / 非空白关键字方可发起」；外壳控件不得破坏既有导航定位约束（沿用 F018 Constraints #9）。
- `total` 显示为**命中项数**（组织单元数）；分页控件按单元翻页。

## Contract Status

```text
READY
```

权威正文：`docs/api/f019-search-result-aggregation.md`（本次落盘）。`docs/api/f018-cluster-keyword-search.md` 的响应 / 结果顺序 / 排序排除项被其取代（见「既有契约立场同步清单」）；f018 §2 匹配字段与匹配语义**未**被取代。

## Domain Impact

**无新增、无修改**领域对象 / 字段 / 关系 / 状态 / 唯一性 / 生命周期。使用 `Cluster`（范围前置，不产生结果行）、`BareMetal`、`NetworkInterface`、`IpAddress`、`VirtualMachine`、`Container`、`Service`（含 `service_carriers`）。关联链成员判定**引用** R-QUERY-003，不产生新的领域事实。

## Data Layer Impact

**无 schema 变更、无 migration、无 extension、无新索引 / 表 / 列 / 约束。** 全部读取复用既有索引与 `get_related_resources`；活跃过滤统一经 `app/db/active.py`。Alembic head 保持不变。

## Backend Work

改造 `backend/app/search/**`（不新建第二套搜索）：

1. `schemas.py`：
   - 新增 `SearchResultRole(StrEnum)` = `HIT` | `RELATED`。
   - 新增 `ResourceRef`：`{resource_type: SearchResourceType, id: int}`。
   - 将 `SearchResultItem` 替换为 `SearchResultRow`：`{resource_type, id, role, group_key: ResourceRef, matched_fields: list[str], derivation_path: list[ResourceRef] | None, resource: <六类 Read 联合>}`。
   - 分页信封：`SearchAggregationPage`（`items: list[SearchResultRow]`, `total`, `page`, `page_size`）。不新增统计字段。
2. `service.py`：
   1. `clusters_service.get_cluster_by_id`（唯一 404 网关，先于派生）。
   2. 按 `BareMetalRepository.list_active(cluster_id=…)` 全量快照（仿既有 `_snapshot`，不静默截断）。
   3. 对每台 `B`：`G = get_related_resources(session, B.id)`，缓存 `G(B)` 与 `B`；构建 `anchor_of[(type,id)] = set[B.id]`（含 `B` 自身）。
   4. 对候选集中每个资源按 `SEARCHABLE_FIELDS` 计算 `matched_fields`（沿用 F018 大小写折叠子串匹配）。
   5. 命中项集合 = 有 `matched_fields` 的资源（按 `(type,id)` 唯一）。
   6. 每个命中项 `H` 生成单元：`chain = 去重(⋃_{B∈A(H)} G(B))`；首行 `HIT`，其余 `RELATED`（排除 `H` 自身），关联行按 `(type rank, id)` 排序并计算 `derivation_path`。
   7. 单元按第 3 节排序键全序化 → 单元级切片分页；`total` = 单元全量数；展平为本页 `items`。
   - **不得**出现 `deleted_at`；**不得**重写 R-QUERY-003 推导（仅调用 `get_related_resources`）；避免源码 token `order_by` / `sort_by` / `rank_by` / `relevance` / `status` / `state`（沿用 G-018-7 对越界 token 的约束）。
3. `router.py`：端点 / 参数 / 校验（空关键字 400、分页）保持不变；`response_model` 改为 `SearchAggregationPage`。
4. 同步更新 `tests/test_search_*` 与 `tests/test_search_guards.py`（见「既有契约立场同步清单」与 Verification Strategy）。

## Frontend Work

1. `frontend/src/api/search.ts`：把 `SearchResultItem` 更新为 `SearchResultRow`（含 `role` / `group_key` / `derivation_path`）；`searchClusterResources` 返回 `Paginated<SearchResultRow>`；导出 `SearchResultRole` / `ResourceRef` 类型。
2. `frontend/src/pages/SearchResultsPage.vue`：
   - 单请求渲染；按 `group_key` 连续段分组（不改动后端形态、不做关联推导）。
   - 命中行：徽标「命中」+ 标识字段 + `matched_fields` 标签 + 详情入口。
   - 关联行：缩进 + 徽标「关联」+ `derivation_path` 文案 + 详情入口。
   - 三态互不相同；错误按 `error.code`。
   - 分页按 `total`（单元数）驱动；`page_size` 语义为**单元数**。
3. `frontend/src/App.vue`：入口与前置不变（F019 预计无需改动入口逻辑，仅在类型随 `search.ts` 变化时同步）。
4. 新增 / 更新 `frontend/tests/search*.spec.ts`：命中 / 关联行区分、推导路径渲染、不去重、三态、单请求、分页。

## Test Work

Testing Agent 必须验证（真实 PostgreSQL）：

| # | 测试 | AC |
|---|---|---|
| T-19-01 | 输入 IP 片段 → 结果含该 IP（`HIT`）、其 NIC 与 BareMetal（`RELATED`），后者自身未命中 | AC-A3 / 用户示例 |
| T-19-02 | 关联行携带正确 `derivation_path`（首 = 命中项、末 = 本行） | AC-A2 |
| T-19-03 | 单元组织顺序 = 命中类别 → 类型序 → id；标识字段命中排在仅描述性字段命中之前 | AC-A6 |
| T-19-04 | 跨单元不去重：同一关联资源在两个不同命中项单元中各出现一次 | AC-A5 |
| T-19-05 | 同一单元内命中行恒为首行，关联行紧随 | AC-A8 |
| T-19-06 | 仅搜索涉及资源：无命中项关联链之外资源不出现；不做全量倾销 | AC-A4 |
| T-19-07 | 关联行过滤软删（raw `psycopg` 预置 `deleted_at`） | AC-02 |
| T-19-08 | 只读（搜索前后 `updated_at` / 内容不变） | AC-01 |
| T-19-09 | 未认证 → `401`；空 / 仅空白 keyword → `400`（先于 404）；Cluster 不存在 / 已软删 → `404`；无命中 → `200` Empty | AC-03 / AC-04 |
| T-19-10 | 单元级分页：跨页不重不漏，单元不被拆散；`total` = 单元数 | 契约 |
| T-19-11 | `resource` 逐字段等于对应 canonical `*Read` | 契约 |
| T-19-12 | 大小写隔离：仅 search 模块含 `.lower()`；§22 / `by-name` 行为不变 | AC-05 |
| G-019-1 | `search/service.py` AST 断言调用 `get_related_resources`；源码无 `deleted_at` | AC-A3 |
| G-019-2 | 路由集合仍恰 `{GET /clusters/{cluster_id}/search}`（无新端点 / 参数）；请求参数仍恰 `{cluster_id, keyword, page, page_size}` | AC-06 |
| G-019-3 | 响应 schema 恰含 `resource_type/id/role/group_key/matched_fields/derivation_path/resource`；`resource` anyOf 恰六个 canonical `*Read`；`group_key` / `derivation_path` 元素恰 `{resource_type,id}` | 契约 |
| G-019-4 | 源码无越界 token（保留 `relevance/similarity/tsvector/trigram/cross_cluster/status_filter/include_deleted` 等），且**不得**因新增排序而放开对「相似度 / 跨集群 / 软删」的禁止 | AC-08 |
| G-019-5 | `EXPECTED_GET_ROUTES` 与 F010 `F009_CLUSTER_PATHS` **只增不减** | AC-06 |
| T-FE-19-1 | 命中行 / 关联行徽标与缩进可区分；`derivation_path` 渲染 | AC-A2 |
| T-FE-19-2 | 三态互不相同；错误按 `error.code` | AC-07 |
| T-FE-19-3 | 一次搜索恰一个请求（无浏览器端拼接） | AC-06 |

**必须独立证伪**：① 复用而非重写（临时让 `get_related_resources` 派生为空 → 关联行消失、命中行仍在，随即还原）；② 软删过滤为真；③ 只读为真；④ 分页不拆单元；⑤ 前端单请求；⑥ 既有 guard 只增不减（无删除断言、无 skip、无恒真）。

## Technical Decisions

### CONFIRMED
- R-QUERY-006（新）/ R-QUERY-005（修订）/ R-QUERY-003（含间接）/ R-QUERY-004；§17 R-DELETE-002；§19；§22「不区分大小写仅限搜索匹配」。
- DEC-022 8 项裁定：扁平混合列表 / 命中项关联链为单元 / 关系扩展 / 方案 A / 仅搜索涉及资源 / 不去重 / 标识字段优先 / 取代 F018 扁列表。
- F010 `get_related_resources` 为 R-QUERY-003 推导**唯一实现**，必须复用。
- 只读、软删过滤、认证 401、Not Found/Empty 区分、单关键字子串包含、不跨 Cluster。

### REQUIRED
1. 端点 / method / path / query 参数**不变**；响应形态**取代**为聚合行列表（条目级 = 单元级分页）。
2. 关联链成员判定**必须**经 `get_related_resources`；search 模块不得含 `deleted_at`，不得自写 FK / 软删 / 载体并集谓词。
3. `total` = 组织单元数；同单元命中行 + 关联行**不得跨页拆散**。
4. 排序键 = 命中类别 → `resource_type` 固定序 → `id`；单元内关联行按 `(type rank, id)`。
5. `derivation_path` 确定性（命中项 → … → 本行），仅用单元内已有对象与已确认关系方向。
6. `resource` 逐字段复用 canonical `*Read`；`role` 封闭两值；`group_key` / `derivation_path` 元素封闭为 `{resource_type,id}`。
7. 大小写折叠仅限 `backend/app/search/**`；§22 / `by-name` / 用户名查找零改动。
8. 既有 guard 只增不减：`EXPECTED_GET_ROUTES`、F010 `F009_CLUSTER_PATHS` 追加而非替换。

### PROPOSED
1. **PROPOSED-1（呈现建议，非 CONFIRMED）**：一条资源自身命中、同时是另一命中项的关联资源时，**两处都出现**（既作 `HIT` 行、又作他单元 `RELATED` 行）。与「不去重」方向一致。
2. **PROPOSED-2**：一条资源多字段命中时显示全部命中字段（沿用 F018 取向）。
3. `derivation_path` 采用类型 + id 的结构化步骤（可由 Frontend 直接生成文案）。
4. 契约落点：新增 `docs/api/f019-search-result-aggregation.md`，f018 响应部分改为指向。

### OPEN（非阻塞）
1. 单 Cluster BareMetal 达 ~10³ 台时的批量化推导（路径 A，需架构决策）。
2. 前端推导路径的具体文案 / 缩进层级（Frontend）。
3. 搜索历史 / 保存查询 / 关键字高亮：未承诺。

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 关联链被实现为「全量倾销」或「第二份关联推导」 | REQUIRED #2 + G-019-1；成员仅来自 `get_related_resources`；`chain(H)` 受锚定组界定 |
| R2 | 单元被分页拆散（AC-A8 破坏） | REQUIRED #3：单元级分页；T-19-10 / T-FE |
| R3 | 契约与实现分裂（f018 仍写扁列表响应） | 契约 Status = READY + f018 响应段指向 f019（同步清单） |
| R4 | 既有 G-018-6/7 guard 因新 schema / 排序变红 | 明确要求**更新** guard（schema 断言改写、越界 token 保留对相似度 / 跨集群 / 软删的禁止，不放开） |
| R5 | tie-break 被误当作产品排序承诺（违反 R-QUERY-005「不承诺按类型排序」） | Decisions #3 明确为**内部确定性**；契约标注 |
| R6 | `derivation_path` 被实现为额外 DB 遍历 | REQUIRED #5：仅用单元内已物化对象；不判定成员资格 |
| R7 | 嵌套 / 分组响应被误实现为多张列表（AC-A1） | 契约固定顶层**扁平 `items`**；单元仅以 `group_key` + 连续段表达 |
| R8 | 既有 F018 测试因响应形态变化而失效 | Verification：更新响应形态断言，保留边界断言（401/404/400/软删/只读/大小写） |

## Constraints

1. 不新增 / 修改任何领域对象、字段、关系、状态、唯一性规则。
2. 无 schema 变更 / migration / extension / 新索引 / 新表。
3. 只读；不新增第二条 `deleted_at` 写入或读取谓词；search 模块不得出现 `deleted_at`。
4. 必须复用 `get_related_resources`；不得另写关联推导。
5. 不引入相似度 / 打分 / 跨 Cluster / 导出 / 状态筛选 / 统计式聚合 / 自动发现。
6. 不引入新框架 / 新依赖 / `vue-router` / EAV / JSONB / ORM 多态 / 通用表。
7. 顶层响应必须是**单一扁平列表**（`items`）；不得输出多张并列列表。
8. 既有 guard 只增不减；`EXPECTED_GET_ROUTES` 与 F010 `F009_CLUSTER_PATHS` 追加而非替换。
9. 大小写折叠仅限 `backend/app/search/**`。
10. 修改 `App.vue` 时不得破坏既有导航定位约束（沿用 F018 Constraints #9）。

## Open Technical Questions

### Blocking

无。

### Non-blocking

- NQ-A（性能失效阈值）：单 Cluster BareMetal ~10³ 台时的批量化推导属未来架构决策，本 Feature 不预先泛化。
- NQ-E：推导路径文案 / 缩进层级（Frontend 决定）。
- NQ-F：已裁定——`HIT` 行携带 `matched_fields`；`RELATED` 行携带其自身命中字段（可空）。

## 既有契约立场同步清单

| 文档 | 处置 |
|---|---|
| `docs/api/f018-cluster-keyword-search.md` | **修订**：§3「Response 200 / 结果顺序」与 §7 中「排序参数（本契约不承诺排序）」改为指向 f019；加「响应被 f019 取代」横幅。**§2 匹配字段 / 匹配语义保持权威** |
| `docs/api/f019-search-result-aggregation.md` | **新增**（本次落盘，Status = READY，权威） |
| `docs/api/api-conventions.md`、`f001`–`f010`、`f014` | **不修改** |
| `docs/architecture/f018-cluster-keyword-search-handoff.md` | 历史文档，**不修改**（其裁定 2 的 `database:false` 结论被 F019 延续） |
| `tests/test_search_guards.py`（G-018-6/7） | **更新**：schema 断言改为新行结构；越界 token 列表保留「相似度 / 跨集群 / 软删 / 统计」禁止项，**不**因新增排序放开对它们的禁止 |
| `tests/test_search_api.py`（响应形态用例） | **更新**：断言新聚合形态；保留边界用例 |
| `frontend/src/api/search.ts`、`SearchResultsPage.vue`、`App.vue`、`frontend/tests/search*.spec.ts` | **更新 / 新增**（Frontend 分支） |
| `docs/project/project-plan.yaml` `features[F019]` | 由协调器 / PM 更新（`contract.doc`、`layers.database=false`、`implementation.database_design=NOT_REQUIRED`）；**本阶段不修改** |

## Implementation Layers

```text
database: false
backend:  true
frontend: true
```

- **database: false** — 无 schema / migration / extension；Database Design 分支 `NOT_REQUIRED`。
- **backend: true** — `backend/app/search/{schemas,service,router}.py`（改）、`tests/test_search_*.py`（改 / 增）。
- **frontend: true** — `frontend/src/api/search.ts`（改）、`frontend/src/pages/SearchResultsPage.vue`（改）、`frontend/src/App.vue`（如类型联动需要）、`frontend/tests/search*.spec.ts`（改 / 增）。

**文件所有权**

| 分支 | 文件 |
|---|---|
| Backend | `backend/app/search/schemas.py`、`backend/app/search/service.py`、`backend/app/search/router.py`、`backend/app/search/fields.py`（如需要）；`tests/test_search_api.py`、`tests/test_search_guards.py` |
| Frontend | `frontend/src/api/search.ts`、`frontend/src/pages/SearchResultsPage.vue`、`frontend/src/App.vue`、`frontend/tests/search*.spec.ts` |
| Docs（协调器统一落盘） | `docs/api/f019-search-result-aggregation.md`（新）、`docs/api/f018-cluster-keyword-search.md`（改）、本文件 |
| Migrations | **无** |

## Implementation Order

```text
Architecture + API Contract（均 READY）
  ├─ Frontend（依 f019 契约并行）
  └─ Backend（search 模块聚合改造 → guard 更新 → 全测试集）
                 ↓ 所有必需实现分支完成
              Tester → Reviewer
```

`database: false`，无 Database 分支；Backend 与 Frontend 可依 f019 契约**并行**。

## Verification Strategy

- **门禁**：后端 `pytest`（真实 PostgreSQL + `ruff check` / `ruff format --check`）；前端 `npm run typecheck` + `npm run test`（连续 2 次）+ `npm run build`。
- **真实 PG**：执行 T-19-01 / 07 / 08 与分页用例；确认 `alembic upgrade head` 无新 revision。
- **必须独立证伪**：见「Test Work」六条。
- **生产实例 `http://192.168.10.221/`（人工核验）**：输入 IP 片段得到命中行 + 缩进关联行与推导路径；标识字段命中排在描述性字段命中之前；无命中显示 Empty（非错误）；不存在 Cluster 显示「未找到资源」；未登录 `/api/...` → 401；既有导航入口不受影响。
