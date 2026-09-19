# Architecture Handoff — F018 集群内资源关键字搜索

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-18
> Feature Branch: `feature/F018-cluster-keyword-search` ｜ start_commit `e59cfd9`

## Feature

**F018 — 集群内资源关键字搜索**（Cluster-scoped Keyword Search）

- Epic E05 / Milestone M8；`layers = {database: false, backend: true, frontend: true}`；`Contract = REQUIRED`（本次已落盘为 `READY`）。

## Product Source

- `docs/product/handoffs/f018-cluster-keyword-search.md`（`READY FOR ARCHITECT`，无 Blocking Open Questions）
- `docs/product/requirements.md` §16 **R-QUERY-005**（直接产品依据，含「空 / 仅空白关键字不构成有效搜索」）、R-QUERY-003（含「含间接」）/ R-QUERY-004、§17 R-DELETE-002、§19、§22、§23、§4 / §24
- `docs/project/project-plan.yaml` `features[F018]`（NQ-1 ~ NQ-5 已裁定；NQ-6 / NQ-7 归 Architecture；`DEC-021 = RESOLVED`）
- ADR-0003 / ADR-0004 / ADR-0005（均 `ACCEPTED`）
- 复用依据：`docs/architecture/f010-resource-detail-handoff.md`、`f009-cluster-resource-view-handoff.md`、`docs/api/f010-resource-detail.md`

## Architecture Summary

**目标**：在**一个已选定 Cluster** 范围内，用**单关键字**（子串包含、不区分大小写）一次性定位该 Cluster 的活跃 BareMetal + R-QUERY-003 五类关联资源（含「含间接」），返回**单一混合列表**且每条携带**命中字段**。

**对现有系统的影响（已核实）**：

- **已有**：`backend/app/resource_views/**`（F010 只读聚合模块，含 R-QUERY-003 推导的**唯一实现**）、各资源 canonical 过滤（F002 `?cluster_id=`、F004 `?bare_metal_id=`、F005 `?network_interface_id=`、F007 / F008 `carrier_type+carrier_id`、F009 `by-name` 别名、F010 `.../related`）、`app/db/active.py`、`app/deletion/service.py`、`tests/test_*_guards.py`、迁移 head `0008_f008_services`。
- **不存在**：任何搜索能力（后端无端点、前端无输入框）、任何 `pg_trgm` / `tsvector` / extension / 搜索表 / 索引。

**方案要点**

1. **契约形态 NQ-7 选 (a)：新增单一独立只读端点 `GET /api/clusters/{cluster_id}/search?keyword=`**，返回异构混合列表（见「裁定 1」）。
2. **范围推导复用 F010**：命中范围 = Cluster 内每台活跃 BareMetal `B` 的 `{B} ∪ get_related_resources(B)`。复用入口 = **`app.resource_views.service.get_related_resources`**（唯一公开推导入口），不另写一份。
3. **匹配在已物化候选集上执行**（Python 大小写折叠子串包含），因此**不接受索引加速**，`layers.database` 保持 **`false`**（见「裁定 2」）。
4. **新模块 `backend/app/search/`**（不放进 `resource_views`，避免击穿 F010 的源码 token guard）；资源表示**逐字段复用** canonical `*Read`，不构成第二份 canonical 读取实现。
5. **Empty / Not Found / 400 / 401 四态分离**：401（中间件最先）→ 400（空 / 仅空白 keyword，先于 404）→ 404（Cluster 不存在 / 已软删，唯一网关）→ 200（含无命中 Empty）。
6. **大小写不敏感实现隔离**：仅在 `backend/app/search/**` 做 `.lower()` 子串匹配；§22 / `by-name` / 用户名查找的既有实现零改动，并以**可失败**的静态 guard + 行为 guard 固定。
7. **前端**：应用外壳（`App.vue`）承载「当前选定 Cluster」选择器 + 关键字输入 + 搜索按钮（未选 Cluster / 空关键字时不可发起），结果页为混合列表 + 命中字段标签 + 详情导航 + 三态；错误按 `error.code` 渲染。

---

## 关键技术裁定 1 — 契约形态（NQ-7）

| 维度 | (a) **新增独立搜索端点** ✅ 选定 | (b) 既有 per-resource 端点追加 `keyword` | (c) 前端编排多请求拼接 |
|---|---|---|---|
| 满足「单一混合列表」(AC-D4) | 天然是**一次请求**的单一列表 | 需 6+ 次请求再在浏览器端拼接 | 同 (b)，且需前端自算 R(B) 关联 |
| 与 F010「不要浏览器端拼接」取向 | 一致 | **冲突** | **冲突**（F010 已否决：无事务一致性、无法端点级独立验证、并发软删下自相矛盾） |
| 异构「命中字段」表达 | 统一在结果封装里逐条携带 | 每类型各定一套，前端再合并 | 前端合并 |
| 分页语义 | 单一混合列表的 `page/page_size/total` | **跨 6 个列表无法定义统一分页** | 无法定义 |
| 与既有 canonical 过滤复用 | 后端复用（F010 + repositories） | 表面成立，但关联范围（含间接）仍需前端推导 | 前端重新推导 |
| 契约 / guard 面 | 1 个端点 | 5~6 个端点各加参数 + OpenAPI 变更 | 无端点，但前端承担业务逻辑 |
| 只读可验证性 (AC-01 / 02) | 端点级可验证 | 分散 | 不可独立验证 |

**裁定：(a)。** R-QUERY-005 明确要求「**单一混合列表**」；AC-D1 要求的范围（BareMetal **及** R-QUERY-003 五类，**含间接**）必须由**后端**的 F010 推导给出——前端无 canonical 直连端点可算（IP 无 `bare_metal_id`、Service 载体是 N:M）。故 (a) 是唯一能在**端点级**同时满足「单一混合列表」「命中字段」「统一分页」「范围推导复用」的形态。

端点：**`GET /api/clusters/{cluster_id}/search`**（首段 `clusters` 已在 `APPROVED_API_PREFIXES` 中 → **allow-list 不需新增**）。

---

## 关键技术裁定 2 — 索引与性能（NQ-6）

```text
layers.database 保持 false（不变为 true）
无 migration、无 extension、无新索引、无新表
匹配在「已物化的 Cluster 候选集」上执行（Python 大小写折叠子串包含）
```

**论证**

1. **匹配无索引可用，是设计使然。** 范围 = 「Cluster 下每台 BareMetal `B` 的 `{B} ∪ Related(B)`」。`Related(B)` 的判定（含间接）**必须**经 F010 推导（多表、按父集合并、Service 为 N:M 载体并集）——这不是一条可加 `keyword` 谓词的 SQL。因此后端**必须先物化候选集再匹配**；一旦如此，`pg_trgm` GIN 无法参与该查询（keyword 不进 SQL），加索引无收益。
2. **`tsvector` 语义不匹配。** R-QUERY-005 明确「模糊 = **子串包含**」，不是词元 / 前缀检索；`tsvector` / `tsquery` 只匹配成词词元（或词元前缀），**无法**表达任意子串——**排除**。
3. **`pg_trgm` GIN 的代价与收益不成立**：需 `CREATE EXTENSION pg_trgm`（f012 基线明确「不创建任何 extension」，且属运维 / 权限变更）+ 跨 6 表约 30 个 GIN 索引（写放大、存储）；而选 (a) 后**它用不上**。按 `AGENTS.md §2.6`，无明确收益即**不引入**。
4. **规模量化**：设计规模 10⁵ 为**全平台总量**；搜索候选集被**单个 Cluster** 截断。设单 Cluster 活跃资源量 `S`：匹配成本 ≈ `O(S × 字段数)` 次 `str.lower()` 子串比较（约 10 字段 / 行）；`S = 10⁴` 时 ≈ 10⁵ 次比较 / 请求，Python 级毫秒量。真正的成本是**候选集物化**（见 R1），随**单 Cluster 的 BareMetal 数**增长，而非随 10⁵ 总量增长。
5. **失效阈值（须重估）**：单 Cluster 活跃 BareMetal 达 **~10³ 台**，或搜索 QPS 显著上升、p95 逼近上限，或出现跨 Cluster / 全平台搜索需求。届时须**新开架构 / 产品决策**：
   - **路径 A（保留语义、批量化推导）**：在 `resource_views` 内新增**集合式**推导入口，把逐 BareMetal 的 N+1 降为按 Cluster 的常数次查询；仍 `database: false`。
   - **路径 B（下推 + 索引）**：把 keyword 下推到各 canonical 查询并引入 `pg_trgm GIN`（需用户批准 extension 与新索引）或搜索专用物化表——**属长期技术 / 运维决策，非本 Feature**。

> 本方案匹配不下推，故 (a) 下引入 extension 是纯负担，**不需要**用户当场裁定，`READY FOR IMPLEMENTATION` 成立。

---

## 关键技术裁定 3 — 搜索结果 schema 与「非第二份 canonical 读取」

```json
{
  "items": [
    { "resource_type": "BARE_METAL", "id": 101, "matched_fields": ["hostname"], "resource": { /* BareMetalRead */ } },
    { "resource_type": "IP_ADDRESS", "id": 41,  "matched_fields": ["ip_address"], "resource": { /* IpAddressRead */ } }
  ],
  "total": 2, "page": 1, "page_size": 50
}
```

- `resource_type`：封闭六值 `BARE_METAL | NETWORK_INTERFACE | IP_ADDRESS | VIRTUAL_MACHINE | CONTAINER | SERVICE`（判别字段）。
- `id`：资源主键（与 `resource.id` 一致）。
- `matched_fields`：**非空**字符串数组，元素为 NQ-2 允许的字段名（确定性顺序 = 该类型字段声明顺序）。
- `resource`：**逐字段复用** canonical `*Read`，不新增字段。
- 分页信封：**复用** `{items,total,page,page_size}`。
- 顺序：按 `(resource_type rank, id)` 物化以保分页稳定。**这不是产品排序承诺**，也不构成「分组」。

**为何不是「第二份 canonical 读取实现」（F010 核心约束）**

| 维度 | 交付 | 是否新实现 |
|---|---|---|
| 范围推导（B + 五类，含间接） | 调 **`resource_views.service.get_related_resources`** | **否**（复用 F010 唯一推导） |
| 资源表示 | 复用 canonical `*Read` | **否** |
| 活跃 / 软删过滤 | 经 F010 与既有 repository 传递（`app/db/active.py`） | **否**；search 模块**不得出现任何 `deleted_at` 表达式** |
| Cluster 404 网关 | 复用 `clusters.service.get_cluster_by_id` | **否** |
| 新增内容 | 仅「关键字匹配 + 命中字段 + 混合列表封装 + 分页」 | 搜索专属职责，非 canonical 读取 |

- **模块归属**：新建 `backend/app/search/`，**不放进** `resource_views`——F010 的 `FORBIDDEN_SOURCE_TOKENS` 禁止 `resource_views/**` 出现 `cluster_id` / `status` / `state` 等 token，而搜索需要 `cluster_id` 过滤；放进去会直接击穿 F010 的 G-010-6。
- **依赖方向**：`search → resource_views`（单向），`resource_views` 不感知 `search`。

## 关键技术裁定 4 — 范围推导的复用入口

**唯一入口**：`app.resource_views.service.get_related_resources(session, bare_metal_id) -> RelatedResourcesRead`。

| 类 | 来源 |
|---|---|
| BareMetal | 既有 `BareMetalRepository.list_active(cluster_id=...)`（canonical 过滤）枚举该 Cluster 的活跃 `B` |
| NetworkInterface / IPAddress / VirtualMachine / Container / Service | **`get_related_resources(session, B.id)`** 返回的五类 `RelatedSet` |

汇总 = `⋃_{B ∈ Cluster} ({B} ∪ Related(B))`，与 R-QUERY-003「含间接」定义**同源**。一条 Service 可能关联同 Cluster 多台 `B`：按 `(resource_type, id)` **去重**。**search 模块不得自写任何 BK / 软删 / 载体并集谓词**；guard 以 AST / 文本断言其导入并调用 `get_related_resources`（可失败）。

---

## Domain Impact

**无新增、无修改**领域对象 / 字段 / 关系 / 状态 / 唯一性 / 生命周期。使用 `Cluster`（范围前置，**不产生结果行**）、`BareMetal`、`NetworkInterface`、`IpAddress`、`VirtualMachine`、`Container`、`Service`（含 `service_carriers`）。

`NQ-A`（字段清单一致性）：依 `AC-D1` 与 R-QUERY-005 正文（「Cluster 本身…**不作为搜索结果行**」「`Cluster.name` 不参与结果命中」）判定 **Cluster 不产生结果行**——已由产品文档定稿。

**匹配字段（NQ-2，权威清单见契约 §2）**

| 类型 | 字段 |
|---|---|
| BareMetal | `hostname` `vendor` `model` `serial_number` `cpu` `memory` `gpu` `storage` |
| NetworkInterface | `name` `technology_type` `purpose` |
| IPAddress | `ip_address` |
| VirtualMachine | `name` `cpu` `memory` `disk` `os` `hypervisor` `owner` |
| Container | `name` `image` `cpu` `memory` `owner` |
| Service | `name` `service_type` `url` `port` `protocol` `owner` `description` |

**明确不参与匹配**：关系外键（`cluster_id` / `bare_metal_id` / `network_interface_id` / `carrier_type` / `carrier_id`）、`status`、`created_at` / `updated_at`、`carriers`、`deleted_at`。

## Data Layer Impact

**无 schema 变更、无 migration。** 全部读取复用既有索引（`ix_bare_metals_cluster_id`、各 `*_bare_metal_id`、`ip_addresses.network_interface_id`、`service_carriers` 载体列索引等）；活跃过滤统一经 `app/db/active.py`。`0001`–`0008` 原样不变；head 仍为 `0008_f008_services`。**不引入 extension / 表 / 列 / 索引 / 约束 / 触发器。**

## Backend Work

新增 `backend/app/search/`：

1. `schemas.py`
   - `SearchResourceType(StrEnum)`（六值）。
   - `SearchResultItem`：`resource_type` / `id` / `matched_fields: list[str]` / `resource: <六类 Read 的联合>`。
   - `SearchResultsPage = Page[SearchResultItem]`（复用 `app.common.pagination.Page`）。
2. `fields.py`：`SEARCHABLE_FIELDS: dict[SearchResourceType, tuple[str, ...]]`，**仅**上表字段（顺序即 `matched_fields` 顺序）。
3. `service.py`：`search_cluster_resources(session, cluster_id, keyword, params) -> tuple[list[SearchResultItem], int]`
   1. `clusters_service.get_cluster_by_id(session, cluster_id)` → 未命中 / 已删 → `NotFoundError`（**唯一 404 网关**，先于派生）。
   2. `BareMetalRepository.list_active(cluster_id=...)` **分页取全**（完整快照，仿 F010 `_snapshot`，不静默截断）。
   3. 每台 `B`：按 `SEARCHABLE_FIELDS[BARE_METAL]` 匹配 → 命中则产出；再 `get_related_resources(session, B.id)`，对五类 `RelatedSet.items` 按各自字段集匹配。
   4. 匹配：`keyword.lower() in str(value).lower()`（`value is None` 跳过）；`matched_fields` 为命中字段名，按声明顺序。
   5. `(resource_type, id)` 去重；按 `(resource_type rank, id)` 物化；切片分页；`total` = 全量命中数。
   - **模块内不得出现 `deleted_at`、不得写自建 SQL 过滤谓词、不得重写 R-QUERY-003 推导。**
4. `router.py`：`APIRouter(prefix="/clusters", tags=["search"])`，**恰一条** `@router.get("/{cluster_id}/search", response_model=Page[SearchResultItem])`；参数 `cluster_id: int`（Path）、`keyword: str`（Query，**必填**）、`page` / `page_size`（复用 `page_params`）。
   - **空 / 仅空白 keyword 校验**：`if keyword.strip() == "": raise ValidationError(..., details=[{"field":"keyword","code":"INVALID",...}])`（与 FastAPI 缺参 400 同码同 field）。校验**先于** Cluster 查库。
5. `app/main.py`：`app.include_router(search_router, prefix="/api")`。

**明确不做**：无写 / 删除 / 恢复端点；无 `keyword` 追加到任何既有列表端点；无排序 / 导出 / 状态筛选 / 多关键字 / 分词 / 相关性参数；无跨 Cluster；无 extension / index / migration。

## Frontend Work

1. `frontend/src/api/search.ts`（新增）：`searchClusterResources(clusterId, { keyword, page, page_size })` → `Paginated<SearchResultItem>`；类型复用既有 `api/*.ts` 的 Read 类型。
2. `frontend/src/App.vue`（**唯一外壳改动点**；F017 已 merge，冲突已解除）：
   - 新增 shell 状态：`searchClusterId: number | null`、`searchKeyword: string`。
   - 侧边栏在 `<nav>` **之后**、会话区之前，新增搜索区：Cluster 选择器（`el-select`，选项**懒加载**：首次展开时 `listClusters`）、关键字输入、`data-testid="shell-search"` 按钮。**未选定 Cluster 或关键字仅空白时按钮禁用、不可发起**。
   - 触发搜索 → `resourceView = { kind: 'search', clusterId, keyword }`；新增 `ResourceView` 分支 `{ kind: 'search'; clusterId: number; keyword: string }` 与 `openSearchResults(...)`。
   - 结果行进入详情复用既有 `open*Detail` 导航，并把 `search` 视图作为返回目标（仿 F010 `returnView`，新增 `SearchReturn`）。
3. `frontend/src/pages/SearchResultsPage.vue`（新增）：props `clusterId` / `keyword`；`useAsyncQuery` + `ListStates` + `ErrorState`。
   - **混合列表**：每行展示 `resource_type` 标签 + 资源标识字段 + `matched_fields` 标签（命中原因）+ 「查看」入口。
   - **三态互不相同**：Loading / Empty（「无匹配结果」）/ Error（按 `error.code`，`NOT_FOUND` → 「未找到资源」，`VALIDATION_ERROR` → 校验失败）。Empty **不得**渲染为错误、不得触发全局 401。
   - **单请求**：只调用**一个**搜索端点；**禁止**浏览器端拼接。
4. **既有导航定位约束（F017 Risks #1）**：外壳搜索区新增的可点击元素**不得**位于 7 个 `nav-*` 之前，且不可见文本**不得**含 `集群` / `裸金属` / `虚拟机` / `网络接口` / `IP 地址` / `容器` / `服务`——否则 `findButton()` 的「首个子串匹配」会选中搜索控件，击穿既有 7 个 `app*Navigation.spec.ts`。

## API Contract

```text
READY
```

权威正文：**`docs/api/f018-cluster-keyword-search.md`**（本次落盘）。同批修订 `f005-ip-address.md:129`、`f009-cluster-resource-view.md:181`、`f010-resource-detail.md:172`、`f002-bare-metal.md:454` 的「关键字 / 筛选」禁止立场（按 `DEC-021`），指向本契约。

## Test Work

### API + DB（真实 PostgreSQL）

| # | 测试 | AC |
|---|---|---|
| T-18-01 | Cluster 内构造 B（含 NIC / IP / VM / 直接+间接 Container / 多载体 Service）；关键字命中各类 → 单一列表含对应 `resource_type` 与 `matched_fields` | AC-D1/D2/D4 |
| T-18-02 | 大小写不敏感：`ABC` 与 `abc` 命中同一结果集 | AC-D3 |
| T-18-03 | 子串包含：连续子串命中；非连续 / 非子串不命中 | AC-D3 |
| T-18-04 | 字段封闭负例：仅 `status`（如 `DOWN`）、`created_at`、外键值可命中却不应命中时**不出现** | AC-D2 |
| T-18-05 | Cluster 不存在 / 已软删（绕过应用层置 `deleted_at`）→ `404 NOT_FOUND` | AC-04 |
| T-18-06 | Cluster 活跃、无命中 → `200` + `items==[]` + `total==0`（**Empty**，不得 404） | AC-04 |
| T-18-07 | 空 / 仅空白 keyword → `400 VALIDATION_ERROR`（`details[].field == "keyword"`）；**优先于**不存在 Cluster 的 404 | R-QUERY-005 |
| T-18-08 | 未认证 → `401 UNAUTHENTICATED`，响应体无资源数据 | AC-03 |
| T-18-09 | 软删过滤：逐类绕过应用层预置 `deleted_at` → 该类不出现，其余不受影响 | AC-02 |
| T-18-10 | 只读：搜索前后相关行 `updated_at` 与内容不变 | AC-01 |
| T-18-11 | Cluster 本身不产生结果行：搜索该 Cluster 名称 → Empty | AC-D1 |
| T-18-12 | 范围不越界：其它 Cluster 的资源即使命中也不出现 | AC-D1 |
| T-18-13 | 分页：`page`/`page_size` 回显；`total` 为全量命中数；跨页不重不漏 | 契约 |
| T-18-14 | 响应元素 `resource` 与对应 canonical `*Read` **逐字段一致** | 契约 |
| G-018-1 | `EXPECTED_GET_ROUTES` **追加** search 路径；既有成员全保留 | AC-06 |
| G-018-2 | `search` 路由集合恰 `{GET /clusters/{cluster_id}/search}` | AC-08 |
| G-018-3 | `scan_deleted_at_writes(APP_DIR/"search") == {}`；全局 allow-list 仍恰 `{backend/app/deletion/service.py}` | ADR-0004 |
| G-018-4 | `search/service.py` AST 断言：导入 `app.resource_views.service` 且调用 `get_related_resources`；源码无 `deleted_at` | AC-D1 |
| G-018-5 | **大小写隔离**：各资源 `repository.py` 与 `auth/repository.py` 不含 `lower(` / `casefold(` / `ilike`；全仓 `.lower()` 仅出现在 `backend/app/search/**` | AC-05 |
| G-018-6 | 响应 schema：`resource` 的 anyOf 恰为六个 canonical `*Read` ref；`resource_type` 枚举恰六值；`matched_fields` 存在 | AC-D4 |
| G-018-7 | 源码无越界 token（`export` / `csv` / `order_by` / `sort_by` / `status_filter` / `relevance` / `tsvector` / `trigram` / `cross_cluster` 等） | AC-08 |
| G-018-8 | F010 guard `F009_CLUSTER_PATHS` **追加** search 路径（保留 F009 四条）；`resource_views` 既有 G-010 全绿 | AC-06 |
| T-FE-18-1 | 未选 Cluster 时搜索按钮禁用、不发请求 | AC-D5 |
| T-FE-18-2 | 关键字仅空白时不发请求 | R-QUERY-005 |
| T-FE-18-3 | 三态互不相同；Empty 不渲染错误、不触发全局 401 | AC-07 |
| T-FE-18-4 | 错误按 `error.code` 渲染（`NOT_FOUND` / `VALIDATION_ERROR` / `NETWORK_ERROR`） | AC-07 |
| T-FE-18-5 | 一次搜索**恰一个**请求（无浏览器端拼接） | AC-D4 |
| T-FE-18-6 | 命中字段标签按 `matched_fields` 渲染；结果行可进入详情并返回搜索 | AC-D4 |

### Testing Agent 必须独立证伪的声明

1. **确为复用而非重写**：临时变异（把 `get_related_resources` 返回置空，或让其派生五类为空）→ 关联类结果消失、BareMetal 结果仍在；随即逐字节还原。
2. **大小写隔离生效**：临时把 `clusters/repository.py::get_active_by_name` 改为 `.ilike` → `G-018-5` **变红**；还原后 `by-name` 行为不变。
3. **Empty / 404 / 400 三者分离**且可独立断言。
4. **软删过滤为真**（raw 连接预置 `deleted_at` 后该条消失）。
5. **只读为真**（`updated_at` 不变）。
6. **前端单请求为真**（断言请求计数）。
7. **既有 guard 只增不减**（无删除既有断言、无 skip、无恒真）。

## Technical Decisions

### CONFIRMED
R-QUERY-005（含「空 / 仅空白 = 400 且不可发起」）；R-QUERY-003「含间接」；R-QUERY-004 区分 404 / Empty；§22「不区分大小写仅限搜索匹配」；R-DELETE-002；§19 认证无 RBAC；ADR-0003 / 0004 / 0005。F010 的推导为**唯一实现**，F018 必须复用。`DEC-021 = RESOLVED`：四处契约立场**必须修订**。

### REQUIRED
1. 端点形态 (a)：单一只读 `GET /api/clusters/{cluster_id}/search`；返回单一混合列表。
2. 范围推导**必须**经 `resource_views.service.get_related_resources`；`search` 模块不得出现 `deleted_at`、不得写第二份 R-QUERY-003 推导或软删 / FK 谓词。
3. 唯一 404 网关 = `clusters.service.get_cluster_by_id`，先于派生；子资源缺失绝不诱发 404。
4. 请求参数封闭：`cluster_id`（path）+ `keyword`（必填）+ `page` / `page_size`；**无**排序 / 状态 / 多关键字 / 载体 / `include_deleted` 参数。
5. 状态语义：401 → 400（空 / 仅空白 keyword，先于 404）→ 404 → 200（含 Empty）。
6. 元素 `resource` **逐字段复用** canonical `*Read`；`resource_type` 封闭六值；`matched_fields` 非空。
7. 大小写折叠**仅**出现在 `backend/app/search/**`；§22 / `by-name` / 用户名查找零改动。
8. 既有 guard 只增不减：`EXPECTED_GET_ROUTES` 追加；F010 `F009_CLUSTER_PATHS` 追加（保留 F009 四条）；新增 G-018 系列。
9. 既有契约必须修订，且**不得留「契约禁止、实现却有」的分裂**（AC-06）。
10. 新端点位于 `/api` 前缀下，由 F013 中间件自动覆盖；`APPROVED_API_PREFIXES` **不需新增**。

### PROPOSED
1. 新建 `backend/app/search/`（不放 `resource_views`）。
2. 结果物化顺序 `(resource_type rank, id)`——仅为分页稳定，非排序承诺、非分组。
3. 契约落点：`docs/api/f018-cluster-keyword-search.md`。
4. 前端：shell 搜索区 + `SearchResultsPage.vue`；Cluster 选择器懒加载；`searchClusterId` 与既有 `resourceView` 集群上下文**相互独立**。
5. `SearchReturn` 返回目标仿 F010 `returnView`。
6. layers = `{database:false, backend:true, frontend:true}`。

### OPEN（非阻塞）
1. 排序 / 导出 / 状态筛选 / 多关键字 / 分词 / 相关性：属**新增产品规则**，须另立。
2. 规模触发失效阈值时的路径 A / B（分别需架构 / 用户确认）。
3. 搜索历史 / 保存查询 / 关键词高亮：未承诺。
4. `searchClusterId` 是否随导航预填：PROPOSED（可选）。
5. search 视图的 `navSection` 高亮策略：PROPOSED。

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 逐 BareMetal 调 F010 推导造成 N+1，随**单 Cluster BareMetal 数**放大 | 已量化并给出失效阈值；路径 A 为预留演进；不擅自批量化（避免违反复用约束） |
| R2 | 搜索被写成第二份 R-QUERY-003 推导 / 第二条软删过滤 | REQUIRED #2 + G-018-3/4 + 强制委托 |
| R3 | 大小写折叠越界改动 §22 / `by-name` / 登录 | REQUIRED #7 + G-018-5 + 行为 guard（证伪 #2） |
| R4 | `search` 放进 `resource_views` 击穿 F010 token guard | PROPOSED #1 + G-018-8 |
| R5 | 契约仍禁止关键字但实现已存在（AC-06 分裂） | REQUIRED #9：同批修订四处契约立场 |
| R6 | 触碰 F010 `G-010-8` 造成既有 guard 变红 | 明确**追加**修改（保留 F009 四条），列入回归面 |
| R7 | 前端外壳新增按钮击穿 `findButton()` 导航定位 | Frontend Work #4 |
| R8 | 「混合列表」被实现为分组或承诺排序 | 契约固定「不分组、不承诺排序」；G-018-6/7 |
| R9 | 未认证 401 与 400 / 404 混淆 | REQUIRED #5：中间件先于路由 |
| R10 | 现有 618 前端用例计数回归 | 只新增 spec；不改既有断言 |

## Constraints

1. 不新增 / 修改任何领域对象、字段、关系、状态、唯一性规则。
2. 无 schema 变更：不改 `0001`–`0008`；不新增表 / 列 / 索引 / 约束 / extension / 触发器 / migration。
3. 只读：无写 / 删除 / 恢复端点或参数；不新增第二条 `deleted_at` 写入路径。
4. 不引入自动资产发现 / 外部同步 / 排序 / 导出 / 状态筛选 / 多关键字 / 分词 / 相关性排序 / 跨 Cluster 搜索。
5. 不引入新框架 / 新依赖 / `vue-router` / EAV / JSONB / ORM 多态 / STI / 通用表。
6. `search` 模块不得含 `deleted_at`；不得重写 R-QUERY-003 推导。
7. 大小写折叠仅限 `backend/app/search/**`；§22 / `by-name` / 用户名查找零改动。
8. 既有 guard 只增不减；`EXPECTED_GET_ROUTES` 与 F010 `F009_CLUSTER_PATHS` **追加而非替换**。
9. 外壳搜索控件不得置于 `nav-*` 之前，且可见文本不得含 `集群` / `裸金属` / `虚拟机` / `网络接口` / `IP 地址` / `容器` / `服务`。
10. 新端点必须在 `/api` 前缀下，不新增认证白名单。

## Implementation Layers

```text
database: false
backend:  true
frontend: true
```

- **database: false** — 无 schema 变更、无 migration、无 extension（Database Design 分支 `NOT_REQUIRED`）。
- **backend: true** — 新增 `backend/app/search/**`、`main.py` 挂载、`EXPECTED_GET_ROUTES` 与 F010 `F009_CLUSTER_PATHS` 追加、G-018 与全测试集。
- **frontend: true** — `api/search.ts`、`App.vue` 外壳搜索区 + 视图、`SearchResultsPage.vue`、新 spec。

**文件所有权**

| 分支 | 文件 |
|---|---|
| Backend | `backend/app/search/{__init__,schemas,fields,service,router}.py`（新）；`backend/app/main.py`（改）；`tests/test_search_*.py`、`tests/test_search_guards.py`（新）；`tests/test_auth_guards.py`（改：追加路由）；`tests/test_resource_views_guards.py`（改：追加 cluster 路径） |
| Frontend | `frontend/src/api/search.ts`（新）；`frontend/src/pages/SearchResultsPage.vue`（新）；`frontend/src/App.vue`（改）；`frontend/tests/search*.spec.ts`（新） |
| Docs（协调器统一落盘） | `docs/api/f018-cluster-keyword-search.md`（新）；`docs/api/f005-ip-address.md`、`f009-cluster-resource-view.md`、`f010-resource-detail.md`、`f002-bare-metal.md`（改）；`docs/architecture/f018-cluster-keyword-search-handoff.md`（本文件） |
| Migrations | **无** |

## Implementation Order

```text
Architecture + API Contract（均 READY）
  ├─ Frontend（依契约并行，写 api/search.ts + SearchResultsPage + App.vue 外壳）
  └─ Backend（search 模块 → main.py 挂载
              → EXPECTED_GET_ROUTES / F009_CLUSTER_PATHS 追加 + G-018 guard
              → 全测试集）
                 ↓ 所有必需实现分支完成
              Tester → Reviewer
```

`database: false`，无 Database 分支；Backend 与 Frontend 可依契约**并行**。

## Verification Strategy

- **门禁**：后端 `pytest`（真实 PostgreSQL，`CSM_TEST_DATABASE_URL`）+ `ruff check` / `ruff format --check`；前端 `npm run typecheck` + `npm run test` **连续 2 次** + `npm run build`。
- **数据库层（真实 PostgreSQL）**：无 schema 变更，但 **Tester 必须在真实 PG 上**执行 T-18-01 / 04 / 05 / 09 / 10（软删用 raw `psycopg` 绕过应用层预置 `deleted_at`），确认活跃过滤与子串匹配在真实 DB 行为下成立；确认 `alembic upgrade head` 仍停在 `0008_f008_services` 且无新 revision。
- **必须独立证伪**：见「Test Work > Testing Agent 必须独立证伪的声明」1–7。
- **生产实例 `http://192.168.10.221/`（人工核验）**：未选 Cluster 时搜索不可发起；选定后输入关键字得到**单一混合列表**、每条显示命中字段、可进入详情并返回；无命中显示 Empty（非错误）；不存在 Cluster 显示「未找到资源」；空关键字不可发起；未登录访问 `/api/...` → 401；既有 7 个导航入口与页面加载不受影响。
