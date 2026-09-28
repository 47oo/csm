# F008 统一模糊搜索与下拉交互 — 架构方案

> Status: **READY FOR IMPLEMENTATION**
> Document Type: Feature Architecture
> Feature: F008（Epic E6，P0，M2）
> 依据：`requirements-v2.md` §7.5（搜索下拉部分）/§8（8.1/8.2/8.3）/§9.2/§9.4/§2.1、§10 场景 41/37/38/35/36/39/56，§11.1 BQ-H/BQ-W；
>      `domain-model.md` §1/§2/§3/§5/§6；ADR-001…ADR-005；
>      复用 `docs/architecture/F001-cluster-registry.md` §2/§3、`docs/architecture/F002-resource-registration.md` §2/§3/§4、`docs/architecture/F003-resource-list-detail.md` §2/§3/§4、`docs/architecture/F005-network-segments.md` §2/§3/§4、`docs/architecture/F006-ip-allocation.md` §2/§3/§4、`docs/architecture/F013-user-role-management.md` §2.2/§2.3；
>      `docs/api/F001.md`/`F002.md`/`F003.md`/`F005.md`/`F006.md`/`F013.md`；
>      `docs/project/project-plan.yaml` F008
> 关联 Contract：`docs/api/F008.md`（§8 搜索参数与匹配规则的唯一字段清单）
> 创建日期：2026-09-26

本文件只记录实现层架构方案。产品/领域事实以 `docs/product/` 为准；技术栈、数据库、API、部署、历史审计载体以 ADR 为准。标记：`CONFIRMED` / `PROPOSED` / `OPEN`。

**范围边界（严格）**：F008 定义统一搜索/下拉规范的基础能力，并覆盖其 DONE 时已交付对象（集群、计算资源、网段、固定枚举、页面搜索）。宿主选择（F004）、服务/服务实例目标（F007）、全局 IP 查询（F010）只在同一规范上留**适配点**，不在本 Feature 实现；§8 全量覆盖（场景 37/38）与竞态端到端复核（场景 39）由 F011（M4）闭环。F008 **不新增业务规则**，`layers.database=false`。

---

## 1. 方案摘要

F008 在 ADR 既定架构与既有对象基础上交付「通用检索与下拉」的能力基线：

1. **匹配规则统一实现**（§8.2）：去首尾空格、英文不区分大小写、完全 > 前缀 > 包含、同级稳定排序、IPv4 部分匹配、`%`/`_` 按字面量；**服务端全量匹配 + 分页**（不得只匹配当前页）。
2. **各已交付对象 list 端点的 `q` 语义补齐**：集群（名称/编号）、计算资源（名称/资源 ID/已分配 IPv4）、网段（名称/CIDR/用途/技术类型）、已分配 IP（地址/资源名/接口名）。复用既有 `GET /clusters`、`GET /resources`、`GET /network-segments`、`GET /network-segments/{id}/allocated-ips`，**不新增端点**。
3. **统一搜索/下拉交互规范**（§8.3）前端实现：约 300ms 防抖、回车立即、加载态、旧请求不覆盖新请求、键盘上下/回车/Esc/清空、无结果提示、清空回到初始候选；提供**可复用组件与组合式函数**（本文件只约定职责边界与 Props/Events，不含实现代码）。
4. **固定枚举下拉**：中文展示名/英文代码均可输入匹配（代码内枚举映射，无后端）。
5. **关联对象下拉**：最终提交稳定 ID（如 `resource_id`），未匹配输入**不创建对象**（对齐场景 41）。
6. **仅匹配仍存对象**：真实删除即删行，列表/下拉天然不返回已删除对象；无软删/停用过滤分支。
7. 为 F004/F007/F010 提供同一规范的**适配点**，由 F011 完成全量覆盖闭环。

**复用既有能力（不复制实现，`CONFIRMED`）**：
- 既有 list 端点与分页（`page`/`page_size` 1–100、`total`、`sort`）、`application/problem+json`、Cookie 会话与三角色鉴权（F013 经 F001 集成）。
- F002/F003/F005/F006 既有响应结构（`ClusterListItem`、`ResourceListItem`、`NetworkSegmentListItem`、`AllocatedIpItem`）直接作为下拉/页面搜索结果数据源。
- 前端 `api/client.ts` 错误归一化、`useClusterStore` 选择记忆、`useResourceList`/`useSegmentAllocatedIps` 已实现的防抖与竞态防护可抽取为通用组合式函数（`PROPOSED`，不改变既有语义）。

---

## 2. 现状核对：现有各 list `q` 语义与 §8.1/§8.2 的差距

> 核对对象为当前分支实际实现（`backend/app/{clusters,network_segments,resources,users}/router.py`）与既有 Contract。结论：**四个 list 端点均已有 `q`**；资源端点已符合 §8.2，集群/网段缺少「完全 > 前缀 > 包含」权重排序，交互层不统一。

| 对象 / 端点 | 现有 `q` 语义（实现） | §8.1/§8.2 要求 | 差距 | 处理 |
| --- | --- | --- | --- | --- |
| 集群 `GET /clusters` | `q` 去空格后对 `code`、`name` 做 `ILIKE %q%`（`\`/`%`/`_` 转义）；SQL 过滤 + offset 分页 + `total`；默认 `sort=code` | 匹配**名称、编号**；完全 > 前缀 > 包含；同级稳定排序 | 仅「包含」，**无权重优先级**；排序按 `sort`（默认 `code`）+ `id` | 复用端点，**补齐 rank 排序**；下拉适配传 `sort=name` 以满足同级按名称 |
| 计算资源 `GET /resources` | `q` 去空格降级匹配 `name`、集群内该资源**已登记 IPv4**；`q` 纯数字且等于 `id` 时 ID 精确；权重「完全 > 前缀 > ID 精确 > 包含」；集群作用域内**全量匹配** + 分页 + `total` | 匹配**名称、资源 ID、已分配 IPv4**；完全 > 前缀 > 包含；IPv4 部分匹配；服务端全量 | **基本符合 §8.2**（无实质功能差距） | 复用；抽取公共 rank 纯函数，保持行为不变（回归） |
| 网段 `GET /network-segments` | `q` 去空格后对 `name`、`cidr`、`purpose`、`technology` 做 `ILIKE %q%`（转义）；SQL 过滤 + 分页 + `total`；默认 `sort=name` | 匹配**网段名称、CIDR、用途、技术类型**；完全 > 前缀 > 包含 | 仅「包含」，**无权重优先级** | 复用端点，**补齐 rank 排序** |
| 已分配 IP `GET /network-segments/{id}/allocated-ips`（F006） | `q` 去空格后匹配地址、资源名、接口名（包含，转义）；分页 | §8.1「页面搜索：资源页面包含 IPv4」的网段子视图 | 无权重优先级（与 §8.2 完全/前缀一致化可选） | 复用；**可选**补齐 rank（不改变既有语义） |
| 用户 `GET /users`（F013） | `q` 匹配 `username`（包含，转义）；分页 | 页面搜索（用户名） | 无 | **不在 F008 覆盖对象**；保持现状，交互基线可后续对齐 |
| 固定枚举 | 前端 `RESOURCE_TYPE_OPTIONS`/`RESOURCE_STATUS_OPTIONS`、角色等 label/code 映射已存在 | 中文展示名/英文代码匹配 | 无统一 matcher | 新增前端 `enumSearch` + `EnumSelect`（无后端） |
| 页面搜索（交互） | 资源页：300ms 防抖 + 回车 + 竞态 token + 空态；集群/网段页：显式「查询」按钮，无防抖 | §8.3 全项 | 交互不一致；缺统一防抖/键盘/清空回初始 | 抽取统一组合式函数并接入各页；下拉统一组件 |

**明确复用点**：既有 list 端点已具备鉴权、分页、`total`、转义与「仅仍存对象」语义，可直接作为下拉数据源；**无需新增 lookup 端点**（详见 §7）。

---

## 3. 匹配规则统一实现（`CONFIRMED` 规则 + `PROPOSED` 机制）

### 3.1 规则（`CONFIRMED`，依据 §8.2）

1. **归一**：`needle = q.strip()`；`needle` 为空（含仅空白）视为**不搜索**，返回该作用域下的初始候选（未过滤列表）。
2. **大小写**：英文不区分大小写（DB `ILIKE` / Python `lower()`）。
3. **权重**：完全匹配 > 前缀匹配 > 包含匹配。多列命中取**最小（最优）rank**。
   - 文本列 rank：`完全=1`、`前缀=2`、`包含=4`。
   - 计算资源 ID（`q` 为纯数字且等于 `id`）额外 rank：`=3`（沿用 F003 既有定义，位于前缀与包含之间）。
   - 计算资源 IPv4 列与名称、网段 CIDR 等文本列使用同一 rank 阶梯，从而实现 IPv4 的完全/前缀（如 `192.168`）/部分匹配。
4. **同级稳定排序**：rank 相同者，按请求 `sort`（各端点默认见 §5.3）升序/降序，最后按 `id` 升序稳定。下拉适配统一传 `sort=name`，从而满足 §8.2「同级按名称及 ID 稳定排序」。
5. **IPv4 部分匹配**：地址按字符串子串匹配即可（如 `168.1.` 命中 `192.168.1.10`）；资源端点固定在本集群 `ip_addresses` 内匹配。
6. **特殊字符**：`%`、`_`、`\` 作为**普通字符**（转义为 `LIKE` 字面量，`ESCAPE '\'`；顺序先转义 `\`）。
7. **服务端全量匹配与分页**：过滤与排序在服务端完成，分页基于完整结果集（`total` 为匹配总数），**不得只匹配当前页**（§8.3）。各端点在各自作用域内全量匹配（资源页限当前集群，网段页限当前集群，集群页/全局 list 为该端点既有作用域）。

### 3.2 统一实现机制（`PROPOSED`，最小共享，不预建框架）

依据 AGENTS §2.3/§2.6，只抽取「匹配 + 排序」这一确有重复收益的能力，不引入通用查询框架：

- **后端共享模块** `app/search/matching.py`（纯函数，无 DB 依赖）：
  - `normalize_query(q) -> str | None`：去首尾空格，空返回 `None`；
  - `escape_like(needle) -> str`：按 `\`→`%`→`_` 顺序转义；
  - `like_pattern(needle) -> str`：返回 `%escaped%`；
  - `match_rank(value, needle) -> int | None`：完全/前缀/包含；供需要物化匹配的路径（资源端点）复用，替换现有 `_match_weight`；
  - `rank_case(*columns, needle)`：返回 SQLAlchemy `case()` 表达式，对每列计算 rank 并取最小值（`完全=1 / 前缀=2 / else 4`），供集群、网段端点用 SQL 排序而不物化全表。
- **端点接入**（仅排序，过滤条件与既有 `ILIKE` 不变）：
  - `app.clusters.router.list_clusters`：`q` 非空时 `ORDER BY rank, <sort>, id`；
  - `app.network_segments.router.list_segments`：同上，rank 覆盖 `name/cidr/purpose/technology`；
  - `app.resources.service.list_resources`：沿用既有 Python 权重逻辑（改为调用共享 `match_rank`），行为不变；
  - `app.network_segments` 的 `allocated-ips` 只读端点：**可选**接入同一 rank（不改变既有包含语义）。
- 无 Schema/索引更动（`database=false`）。**性能**：`ILIKE %q%` 不使用 btree；约 1,000/集群规模下集群/网段/资源页在 §9.2 目标（列表 P95 < 1s、搜索 P95 < 1.5s）内可接受；资源端点全量物化候选也存在相同量级上界。若实测超目标，另立**独立 Database 变更**评估索引或匹配策略（`OPEN`，非阻塞，见 §9）。

### 3.3 排序解释（`PROPOSED`，不含新业务规则）

§8.2「同级按名称及 ID 稳定排序」与「页面显式选择 `sort`」并存：**rank 为第一排序键**；rank 相同时应用请求的 `sort`（各端点默认 `name`/`code`），再以 `id` 稳定；**下拉适配统一请求 `sort=name`** 以满足 §8.2。页面保留用户显式排序能力（不静默改写用户选择）。此为对既有 §8.2 与 F003 既有 `PROPOSED` 排序的技术统一，不新增业务规则。

---

## 4. 统一搜索 / 下拉交互规范（§8.3）

### 4.1 行为契约（`CONFIRMED`，依据 §8.3）

| # | 行为 | 说明 |
| --- | --- | --- |
| 1 | 防抖 | 输入后约 **300ms** 触发一次查询；连续输入重置计时。 |
| 2 | 回车立即 | 回车跳过防抖立即查询；若下拉有高亮项则确认选中该项。 |
| 3 | 加载态 | 请求进行中显示加载指示（组件内），不阻塞其它交互。 |
| 4 | 竞态 | **旧请求响应不得覆盖较新请求**：以递增请求序号（token）判定，过期响应丢弃。 |
| 5 | 键盘 | 上/下移动高亮；回车确认；Esc 关闭下拉（保留已选值）；清空（clearable/清除键）清除选择。 |
| 6 | 无结果 | 显示统一文案「没有匹配项」。 |
| 7 | 清空回初始 | 清空关键词后回到**当前其它筛选条件下**的初始候选（无 `q` 的第一页候选）。 |
| 8 | 服务端全量 | 大量资源（计算资源、服务、IP 等）走服务端模糊查询 + 分页，不得只匹配当前页。 |
| 9 | 仍存对象 | 候选仅包含仍存对象；已真实删除对象不出现在候选中（真实删除即删行）。 |
| 10 | 稳定 ID | 选中即绑定稳定 ID；提交只提交 ID，不提交展示文本。 |
| 11 | 未匹配不创建 | 输入未被任何候选匹配时不提交、不创建对象；失焦/关闭后回退到上次有效选择或清空。 |

### 4.2 前端可复用单元与职责边界（`PROPOSED` 命名，接口约定，不含实现）

**组合式函数 `useRemoteOptions<T>`**（`frontend/src/composables/useRemoteOptions.ts`）
- 职责：持有 `query`/`options`/`total`/`loading`/`error`/`hasMore`/`page`；防抖（默认 300ms）、立即查询、清空回初始、请求序号竞态、显式错误态（不伪装空列表）。
- 输入：`fetcher: (query: string, page: number) => Promise<{ items: T[]; total: number }>`、`pageSize`（默认 20）、`debounceMs`（默认 300）、`immediateInitial`（默认 true）。
- 输出：`options, loading, error, query, total`，方法 `search(q)`（防抖）、`searchNow()`、`clear()`、`loadInitial()`、`retry()`、`setPage(n)`；`hasNoMatch = !loading && !error && query非空 && options为空`。

**组件 `FuzzySelect.vue`**（`frontend/src/components/FuzzySelect.vue`，基于 Element Plus `el-select filterable remote`）
- Props：`modelValue`（稳定 ID：`number|string|null`）、`fetcher`（`(q) => Promise<{items: SearchOption[]; total: number}>`，由页面注入对象适配器）、`initialOptions?`、`debounceMs?=300`、`pageSize?=20`、`placeholder?`、`clearable?=true`、`disabled?=false`、`multiple?=false`、`emptyText?='没有匹配项'`、`loadingText?`。
- Events：`update:modelValue`、`change`、`select(option|null)`、`clear`、`no-match`、`error(error)`。
- 行为：输入→防抖查询；回车立即；上下/回车/Esc 交由 `el-select` 处理并由本组件对齐规范；清空→清除选择并 `loadInitial()`；展示文本来自选中的 `label`，**提交值恒为 `value`（稳定 ID）**；未匹配文本不产生 `update:modelValue`。
- `SearchOption = { value: number|string; label: string; keywords?: string; disabled?: boolean }`；`keywords` 仅用于客户端本地过滤的枚举场景。
- Exposed：`focus()`、`blur()`、`clear()`、`reload()`、`open()`。

**组件 `EnumSelect.vue` + 工具 `enumSearch.ts`**（固定枚举，无后端）
- `EnumSelect` Props：`modelValue`、`options: { value: string; label: string }[]`、`disabled?`、`clearable?`、`placeholder?`；Events：`update:modelValue`、`change`；内部用 `filter-method` 本地匹配。
- `enumSearch.match(label, code, input)`：去空格、英文不区分大小写；命中**中文展示名**或**英文代码**即匹配（含/前缀/完全共用同一 rank，用于本地排序）。适用于 `resource_type`、`status`、角色等已有映射。

**页面搜索组合式函数 `useSearchInput`**（`frontend/src/composables/useSearchInput.ts`，`PROPOSED`）
- 从既有 `useResourceList` 抽取：`q`、防抖 300ms、回车立即、竞态 token、清空回初始；供集群页、网段页、以及后续页面搜索统一接入，替换现有「显式查询按钮」的重复实现（保留按钮作为可访问性补充亦可）。

**对象适配器（页面/`api/*.ts`）**
- 每个对象提供一个 `SearchOption` 映射：集群 `{value:id, label:`${code} ${name}`, keywords:code+name}`；计算资源 `{value:id, label:name, keywords:name + management_ip + cluster_code}`；网段 `{value:id, label:`${name} · ${cidr} · ${purpose}`, keywords:name+CIDR+purpose+technology}`。适配器**只做展示映射**，不复制业务校验。

---

## 5. 各对象下拉数据源与参数建议

### 5.1 直接复用为下拉数据源（`CONFIRMED` 复用 / `PROPOSED` 参数）

| 下拉对象 | 数据源端点 | 建议参数 | 说明 |
| --- | --- | --- | --- |
| 集群 | `GET /clusters` | `q`、`page_size` 小值（如 20，≤100）、`sort=name` | 复用；集群选择器缓存全量仍可用于头部（小数据集） |
| 计算资源（宿主目标等） | `GET /resources` | `cluster_id`（必填作用域）、`q`、`page_size`、`sort=name` | 复用；名称/资源 ID/已分配 IPv4 匹配；F004 负责宿主有效性 |
| 网段 | `GET /network-segments` | `cluster_id`、`q`、`page_size`、`sort=name` | 复用；名称/CIDR/用途/技术类型 |
| 已分配 IP | `GET /network-segments/{id}/allocated-ips` | `q`、`page_size` | 复用；地址/资源名/接口名 |
| 固定枚举 | 无（前端枚举映射） | — | 中文/英文代码本地匹配 |
| 服务 / 服务实例目标 | F007 交付 | — | **适配点**：同一 `FuzzySelect`/`useRemoteOptions` 规范 |
| 全局 IP 查询 | F010 交付 | — | **适配点**：同一页面搜索规范 |
| 用户 | `GET /users`（F013） | `q`、`page_size` | 既有；F008 不改变语义 |

### 5.2 是否需要新增轻量 lookup 端点

**结论：`NOT_REQUIRED`（不需要新增）。** 理由：
1. 既有 list 端点已支持 `q` + `page`/`page_size` + `total` + `sort` + 服务端鉴权，且仅返回仍存对象；下拉所需字段（稳定 ID + 名称 + 必要的展示字段）均在既有响应内，可直接以适配器映射。
2. 新增 `/lookup` 会复制字段定义、制造字段漂移与第二套鉴权/错误语义，违反 AGENTS §2.6 与「同一份详细信息只维护一个权威来源」。
3. 唯一需要改变的是**排序权重**（集群/网段）与**交互层**，不改变资源字段模型。

若实现中发现某下拉需要当前 list 响应未包含的展示字段，处理方式为：在**该对象所属 Feature** 的 Contract 上以附加字段扩展（不改变既有语义），或在前端适配器中省略该展示项；**不**在本 Feature 新建聚合端点。

### 5.3 各端点默认排序（保持既有，不静默改动）

| 端点 | 默认 `sort` | 备注 |
| --- | --- | --- |
| `GET /clusters` | `code` | 下拉适配传 `sort=name` 以满足 §8.2 同级名称排序 |
| `GET /resources` | `name` | 已符合 |
| `GET /network-segments` | `name` | 已符合 |
| `GET /network-segments/{id}/allocated-ips` | 地址数值升序（F006） | 保持 |
| `GET /users` | `username` | 保持 |

### 5.4 固定枚举下拉

- 中文展示名/英文代码匹配在**前端代码内枚举映射**（`RESOURCE_TYPE_LABELS`、`RESOURCE_STATUS_LABELS`、角色 `roleLabel` 等），无需后端；值集来自已确认产品定义，F008 不新增取值。
- 展示恒含中文文字（§9.4「状态必须含文字，不能只靠颜色」）。

### 5.5 关联对象下拉提交语义（对齐场景 41）

- 下拉 **`value` 为稳定 ID**（如集群 `id`、资源 `resource_id`、网段 `id`、IP `ip_id`、服务 `id`）；表单提交该 ID。
- 自由输入未匹配任何候选时：**不提交、不创建对象**；失焦/关闭后回退至上次有效选择或清空。
- 服务端在写入端点按 ID 校验存在性/归属/权限（复用 F002/F005/F006 既有校验）；本 Feature **不新增写入端点、不引入“输入即创建”路径**。
- 计算资源侧稳定 ID 归属由 F002 已有 `resource_id` 语义保证（场景 41 的 F002 participant）。

---

## 6. 仅匹配仍存对象

- 全部受管对象真实删除即删行（无可用的 `deleted_at`/`status=停用` 语义），既有 list 查询天然只返回仍存对象；F008 **不新增**任何「包含已删除」的查询分支。
- 真实删除后对象不再出现在下拉候选与页面搜索结果中；历史仅存于 `resource_history`/`audit_log`（管理员查询属 F012），**不参与搜索候选**。
- 不因本 Feature 把历史记录引入候选或匹配。

---

## 7. 模块边界与 F004/F007/F010/F011 关系

### 7.1 模块边界（`PROPOSED` 机制 / `CONFIRMED` 规则）

| 模块 | 职责 | 非职责 |
| --- | --- | --- |
| 后端 `app/search/matching.py`（新增，纯函数） | 归一、转义、rank 计算（含 SQL rank 表达式） | 不访问 DB、不写业务规则、不做端点编排 |
| 后端 `app.clusters` / `app.network_segments` / `app.resources`（既有，扩展排序） | 在既有 list 端点接入 rank 排序；其余过滤/分页/鉴权/响应结构不变 | 不新增端点、不改字段模型、不改删除/校验 |
| 前端 `composables/useRemoteOptions.ts` | 防抖、竞态、加载/错误/初始候选状态 | 不承载对象业务规则 |
| 前端 `composables/useSearchInput.ts` | 页面搜索防抖/回车/竞态/回初始 | 同上 |
| 前端 `components/FuzzySelect.vue` / `EnumSelect.vue` | 交互渲染、键盘、稳定 ID 提交 | 不创建对象、不做业务校验 |
| 前端 `utils/enumSearch.ts` / 对象适配器 | 枚举与对象展示匹配/映射 | 不复制后端匹配/唯一性规则 |

模块依赖方向：`clusters/network_segments/resources → search.matching`（纯函数）；前端 `views → composables/components/utils`。均不新增跨 Feature 反向依赖。

### 7.2 与 F004/F007/F010/F011 的适配/闭环（`CONFIRMED`）

| Feature | F008 提供 | 对方闭环 |
| --- | --- | --- |
| F004（类型详情与宿主） | `FuzzySelect` + `useRemoteOptions` 输入能力、资源名称/IP 匹配规则、稳定 `resource_id` 提交约定 | 宿主机有效性（同集群裸金属、非 VM/自身）、`主机名称 · 管理 IP · 集群` 展示、多 IP 命中按资源去重（场景 35/36） |
| F007（服务与部署实例） | 同一规范（服务/实例目标下拉、页面搜索交互） | 服务名称/编号/类型匹配、实例目标资源选择与业务约束 |
| F010（聚合计数与全局 IP 查询） | 页面搜索与下拉交互规范、跨集群相同 IP 分别列示的候选约定 | 全局 IP 查询入口、结果含集群/资源/接口、与资源页作用域区分（场景 56） |
| F011（终局复核） | 已交付对象基础搜索/下拉与 §8.2 规则 | 场景 37/38 全量覆盖、场景 39 竞态端到端复核 |

---

## 8. 数据影响（Database NOT_REQUIRED）

- **无 Schema 变更、无 Migration、无新索引**（F008 `layers.database=false`）。F008 只读既有 `clusters`/`resources`/`ip_addresses`/`network_segments`，并在既有端点上调整 `q` 的排序。
- **性能**（`OPEN`，非阻塞）：§9.2 目标约 1,000 台/集群、列表 P95 < 1s、搜索 P95 < 1.5s。`ILIKE %q%` 不吃 btree；若实测超目标，须按 AGENTS §6 另立**独立 Database 设计**评估索引或匹配策略（此时 `layers.database` 届时为 true），本 Feature 不预置、不越权修改 Schema。
- 查询不做 N+1；管理 IP/集群列等以 JOIN/批量查询一次取回（沿用 F003 既有实现）。

---

## 9. 技术决策与风险

**已确认（依据）**：匹配规则与交互全部来自 §8.1/§8.2/§8.3（`CONFIRMED`）；服务端全量匹配 + 分页、稳定 ID、未匹配不创建、仅仍存对象、状态/错误含文字（§9.4）；栈与 API 风格 ADR-001/ADR-003；不新增业务规则、不新增端点、无 Schema 变更（project-plan F008）。

**PROPOSED（实现建议，不阻塞，不新增业务规则）**：
1. 后端共享 `app/search/matching.py`（纯函数 + SQL rank 表达式），最小共享、不预建框架；
2. rank 阶梯：完全 1 / 前缀 2 / （资源 ID 精确 3） / 包含 4；多列取最小；
3. rank 相同按请求 `sort`（各处默认）再 `id`；下拉适配统一 `sort=name` 以满足 §8.2；
4. 下拉复用既有 list 端点（`NOT_REQUIRED` 新增 lookup），建议小 `page_size`（≤100）并 `sort=name`；
5. 前面前端单元命名与 Props/Events（§4.2）；
6. 小数据集（集群、固定枚举、表单内 IP 候选）允许本地过滤，大数据集（资源、服务、IP、跨集群查询）要求服务端远程查询；
7. 集群页/网段页搜索接入统一防抖与竞态，保留可访问性查询按钮。

**OPEN / 关注（非阻塞）**：
- 性能：`ILIKE %q%` 在大集群的实测；若超 §9.2 目标另立 Database 变更（§8）。
- **协调项（非阻塞）**：集群与网段端点的 `q` 排序由 F008 补齐，F001/F005 Contract 现有「包含匹配」描述需在合并前补充「排序以 F008 为准」的交叉引用（由协调器执行；不改变既有字段与包含语义）。
- F004/F007/F010 在同一规范上的适配字段命名须在各自架构阶段与 `docs/api/F008.md` 协调，避免漂移。

**风险**：
- 排序行为变更（集群/网段 `q` 从「仅包含」变为「权重优先」）会改变既有页面结果顺序；需回归 F001/F005 既有测试并核对 Contract 交叉引用（行为兼容：包含语义不变，仅新增优先级与稳定次排序）。
- 远程下拉的竞态与请求量：由请求序号与防抖兜底，避免旧响应覆盖（场景 39 端到端复核归 F011）。

---

## 10. Frontend / Backend 工作拆分

**Backend**（`layers.backend=true`）：
- 新增 `app/search/matching.py`（`normalize_query`/`escape_like`/`like_pattern`/`match_rank`/`rank_case`）。
- `app.clusters.router.list_clusters`、`app.network_segments.router.list_segments` 接入 rank 排序；`app.resources.service.list_resources` 改调共享 `match_rank`（行为不变）；可选接入 `allocated-ips`。
- 不新增端点；不改删除/校验/鉴权；补 pytest + httpx 测试。

**Frontend**（`layers.frontend=true`）：
- 新增 `composables/useRemoteOptions.ts`、`composables/useSearchInput.ts`。
- 新增 `components/FuzzySelect.vue`、`components/EnumSelect.vue`、`utils/enumSearch.ts` 及对象 `SearchOption` 适配器。
- 集群页/网段页接入统一防抖/竞态/清空回初始/无结果文案；资源页保持既有防抖与作用域；固定枚举下拉切换为 `EnumSelect`（中文/英文代码匹配）。
- 保持只读/写入口可见性由现有角色逻辑控制；前端不作为安全边界。
- Vitest 单测。

**Database**：`NOT_REQUIRED`（无设计、无脚本、无索引变更）。

---

## 11. Test Work

**后端集成（pytest + httpx）**：
- 匹配规则：去首尾空格；英文大小写不敏感；`%`/`_`/`\` 作为字面量；空 `q` 返回初始候选。
- 权重与稳定排序：集群 `q` 完全（code/name）> 前缀 > 包含，同级按 `sort`（下拉 `sort=name` 时为名称）+ `id`；网段 `q` 对名称/CIDR/用途/技术类型同理（如 `192.168` 命中 CIDR；`管理` 命中用途；`InfiniBand` 命中技术类型）。
- 计算资源回归：名称/资源 ID（纯数字）/本集群已登记 IPv4 部分匹配；权重完全 > 前缀 > ID 精确 > 包含；跨集群同 IP/同名只返回本集群（场景 56 资源页侧）。
- 服务端全量 + 分页：`total` 为匹配总数；`page`/`page_size` 边界；跨页无重复/遗漏（不依赖当前页匹配）。
- 仅仍存对象：真实删除后对象不再出现在 `q` 结果与候选中。
- 端点/字段不变式：确认未新增写/查端点；集群/网段既有字段与错误码不变。

**前端（Vitest）**：
- `useRemoteOptions`：300ms 防抖只发一次；回车立即；旧请求响应不覆盖新请求；清空回初始；错误态显式；无结果 `hasNoMatch`。
- `FuzzySelect`：Props/Events；选中提交稳定 ID；未匹配自由文本不提交、失焦回退；Esc 关闭；清空清除选择；无结果显示「没有匹配项」。
- `EnumSelect`/`enumSearch`：中文展示名与英文代码均可匹配、大小写不敏感、去空格。
- 页面搜索：集群页/网段页防抖 + 竞态 + 回初始 + 无结果文案；资源页既有行为回归（作用域、筛选、分页、排序、竞态）。
- 只读角色：下拉/搜索可用，写入口隐藏由既有逻辑保证。

**联验（非本 Feature 闭环）**：宿主查找与去重（F004，场景 35/36）；服务/实例（F007）；全局 IP 查询与作用域区分（F010，场景 56 全局侧）；§8 全量覆盖（场景 37/38）与竞态端到端复核（场景 39）由 F011 闭环。

**未验证项声明**：本角色为只读 Architect，**未实际运行任何测试、构建或基准**；以上为 Backend/Frontend 实现后必须执行的验证清单。架构完成不等于实现或验证完成。

---

## 12. Implementation Layers

| Layer | 需要 | 说明 |
| --- | --- | --- |
| database | **false** | 只读既有表；无 Schema/Migration/索引变更；`docs/database/F008.md` 不产出 |
| backend | **true** | 共享匹配/排序模块；集群、网段端点补齐 rank 排序；资源端点复用共享纯函数（行为不变）；无新增端点 |
| frontend | **true** | 统一搜索/下拉组合式函数与组件、固定枚举匹配、页面搜索防抖/竞态/回初始接入 |

结论：**READY FOR IMPLEMENTATION**（无未决架构/产品阻塞；实现仍须满足独立 Contract Gate；本 Feature 无 Database 层，故无 Database Design Gate 依赖）。无 Blocking Questions。