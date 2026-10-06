# F003 计算资源统一列表、详情与服务端分页 — 架构方案

> Status: **READY FOR IMPLEMENTATION**
> Document Type: Feature Architecture
> Feature: F003（Epic E2，P0）
> 依据：`requirements-v2.md` §2.1/§4.3/§6.2/§6.3/§8/§9.2/§9.4、§10 场景 8/32、§11.1 BQ-AA/BQ-W；`domain-model.md` §1/§2/§3/§5/§6；ADR-001…ADR-005；
>      复用 `docs/architecture/F001-cluster-registry.md` §2.3、`docs/architecture/F002-resource-registration.md` §2/§3/§8、`docs/architecture/F005-network-segments.md` §2.4/§9、`docs/architecture/F006-ip-allocation.md` §2/§3；
>      `docs/api/F001.md`、`docs/api/F002.md`、`docs/api/F005.md`、`docs/api/F006.md`；`docs/database/F002.md` §2.1/§2.2、`docs/database/F006.md` §2.1/§2.2；
>      `docs/project/project-plan.yaml` F003
> 关联 Contract：`docs/api/F003.md`（唯一字段清单）
> 创建日期：2026-09-26

本文件只记录实现层架构方案。产品/领域事实以 `docs/product/` 为准；技术栈、数据库、API、部署、历史审计载体以 ADR 为准。标记：`CONFIRMED` / `PROPOSED` / `OPEN`。

---

## 1. 方案摘要

F003 在 ADR 既定架构与 F002/F006 已交付基础上，交付「计算资源」的**只读呈现层**：

1. **统一资源列表**：`GET /resources`（与 F002 `POST /resources` 同路径、不同方法），按**当前已确认集群**作用域返回仍存计算资源；支持全部 / 裸金属 / 虚拟机切换、状态筛选、名称与已登记 IPv4 搜索、**服务端分页（offset）**、默认按资源名称排序；普通列表仅显示仍存对象（真实删除即删行，`resources` 表无软删列）。
2. **列表公共列**：资源名称、集群、资源类型、状态（含展示文字）、管理 IP、更新时间。类型/状态的展示文字由服务端在响应中给出（§6.2「状态必须包含文字」、§9.4）。
3. **资源公共详情**：**复用** F002/F006 `GET /resources/{resource_id}` 返回的 `ResourceFormDetail`，不新增只读详情端点；详情页展示名称、集群、类型、状态、状态来源（操作者 + 状态更新时间）、更新时间、网卡/IP，并预留「服务」占位（由 F007 扩展）。
4. **搜索作用域**：资源列表搜索限定当前集群，响应回显 `scope`，前端显式展示作用域；**不隐式切换作用域**；跨集群全局 IP 查询是 F010 的独立入口，不在本 Feature。
5. **权限**：列表与详情对任意已登录用户（`viewer`/`maintainer`/`admin`）可读，复用 F013 交付、经 F001 集成的会话与角色解析；集群选择只改变查询作用域，不改变角色权限（§2.1、BQ-H）。
6. **不新增写端点**：本 Feature 无新增/编辑/删除；所有写入仍由 F002/F006 的资源表单端点承载。本 Feature **不引入任何数据库 Schema 变更**（`layers.database=false`）。

**复用既有能力（不复制实现，`CONFIRMED`）**：
- `app.security.principal.get_current_user` → `Principal{user_id, username, role, must_change_password, status}`；越权 403。
- `app.errors.problem(...)` / problem+json 统一错误体；`app.db.get_db`。
- F002/F006 资源模型 `Resource`/`NetworkInterface`/`IpAddress`（只读查询）、`NetworkInterfaceResource`/`ManagementIpSummary` 等已有响应结构；F006 `ManagementIpSummary` 直接复用于列表管理 IP 列。
- F001 `useClusterStore`（`clusters` 列表缓存 + `currentClusterId`，`localStorage` 选择记忆与失效回退）。
- 前端 `api/resources.ts` 的 `ResourceFormDetail`/`ManagementIpSummary` 类型。

---

## 2. 模块边界

### 2.1 后端模块（Python 3.12 + FastAPI，ADR-001）

| 模块 | 职责 | 明确的非职责 |
| --- | --- | --- |
| `app.resources`（F002 既有模块，本 Feature 扩展只读查询） | 新增 `GET /resources` 列表查询：集群作用域过滤、类型/状态筛选、`q` 名称/IP 搜索、排序、offset 分页、`total`、管理 IP 列与类型/状态展示文字；集群作用域回显；分页/排序/参数校验与 problem+json 错误 | 不实现新增/编辑/删除（F002/F006）；不实现类型摘要/宿主（F004）；不实现服务关联（F007）；不实现聚合计数与跨集群全局 IP 查询（F010）；不提供资源历史查询（F012）；不改动 F002 既有写端点与表结构 |
| `app.resources.service`（扩展） | 新增只读查询函数（按集群 + 过滤 + 排序 + 分页；搜索匹配与排序权重）；只读 JOIN `clusters`、`ip_addresses`（管理 IP 与 IP 搜索） | 不承载 HTTP 层；不写库、不写审计/历史（本 Feature 全为读） |
| `app.resources.router`（扩展） | 注册 `GET ""`（列表）。既有 `GET /{resource_id}` 详情端点不变，供详情页复用 | 不新增写路由 |
| 复用 `app.security.principal` / `app.errors` / `app.db` | 会话/角色与统一错误体 | — |

模块依赖方向：`resources → security.principal`、`resources → clusters(models only, 只读)`、`resources → ip_addresses(models only, 只读)`。不新增模块、不引入通用查询框架；列表查询落在既有 `app.resources` 内（`PROPOSED`，AGENTS §2.6：无需求支撑不预建抽象）。

### 2.2 与 F002 / F006 的关系（`CONFIRMED`）

- **列表路径**：F002 已占用 `POST /resources`、`GET /resources/{resource_id}`、`PATCH /resources/{resource_id}`、`DELETE /resources/{resource_id}`；F003 仅新增 `GET /resources`（集合级只读），**方法不同、无冲突**，不改写 F002/F006 的任何端点与字段。
- **详情复用**：F003 详情页消费 F002/F006 `GET /resources/{resource_id}`（权限「任意已登录」），返回 `ResourceFormDetail`，已含名称、集群、类型、状态、状态来源操作者（`status_updated_by`/`status_updated_by_username`）、状态更新时间、`updated_at`、网卡（含 `ips`、`segment` 摘要）、`management_ip`。**不新增只读详情端点**（取舍见 §5.1）。
- **列表只读**：`GET /resources` 只 SELECT，不触发审计/历史写入（历史/审计在本 Feature 无变更事件可写）。
- **写入边界**：新增/编辑（含网卡/IP/管理 IP）仍为 F002/F006 的 `POST`/`PATCH`；真实删除仍为 `DELETE`。F003 不提供任何写入口。

### 2.3 与 F004 / F007 / F010 / F012 的边界（`out_of_scope`，`CONFIRMED`）

| Feature | 边界 |
| --- | --- |
| F004（类型详情与宿主关系） | 列表 CPU/vCPU/内存摘要列、详情类型专有字段（SN/CPU/内存/GPU/vCPU/宿主机/宿主 VM）由 F004 在**同一列表与详情**上扩展；F003 交付公共框架与公共列，类型摘要列在 F004 DONE 前空缺（交付分段，非产品限制）。 |
| F007（服务与部署实例） | 详情「服务」关联展示由 F007 在同一详情页扩展；F003 仅交付「服务」占位与详情框架。 |
| F010（聚合计数与全局 IP 查询） | 集群入口聚合计数、跨集群全局 IP 查询入口、全局 IP 结果含所属集群的列示由 F010 交付；F003 的资源列表搜索**仅在当前集群作用域内**，不提供跨集群结果，也不静默切换作用域（§6.2、场景 56）。 |
| F012（资源历史查询） | 真实删除/变更历史查询（仅平台管理员）由 F012 交付；F003 普通列表不显示已删除对象（真实删除即删行，无软删）。 |
| F008（通用检索规范） | 列表 `q` 复用 §8 匹配口径与稳定排序；F008 负责全站搜索框/下拉的通用规范与其它对象适配（如宿主、服务、全局 IP）。F003 先按 §8 交付资源页搜索，不预建通用搜索框架。 |

---

## 3. 数据影响（Database NOT_REQUIRED）

> F003 只读既有表，**无 Schema 变更、无 Migration、无新索引**。本节声明只读查询依赖的既有结构；列/约束由 F002/F005/F006 的 Database 设计定义。

### 3.1 读取对象（`CONFIRMED`）

- `resources`（F002）：`id`、`cluster_id`、`name`、`resource_type`、`status`、`status_updated_by`、`status_updated_at`、`management_ip_id`、`updated_at`。
- `network_interfaces`（F002）：`id`、`resource_id`、`name`、`segment_id`（详情复用 F002 端点，列表不展开网卡）。
- `ip_addresses`（F006）：`id`、`interface_id`、`resource_id`、`cluster_id`、`segment_id`、`ip`（管理 IP join 与 IP 搜索）。
- `clusters`（F001）：`id`、`code`、`name`（列表集群列/作用域回显）。
- `users`（F013）：`id`、`username`（详情状态来源操作者名，已由 F002 端点提供）。

### 3.2 依赖的既有约束/索引（无需新增，`CONFIRMED`）

| 查询 | 依赖既有结构 | 来源 |
| --- | --- | --- |
| 按集群过滤 + 默认按名称排序 | `uq_resources_cluster_name (cluster_id, name)` 隐式 btree、`ix_resources_cluster_id (cluster_id)` | `docs/database/F002.md` §2.1 |
| 类型/状态筛选（集群内） | `ix_resources_cluster_id` 前缀 + 行内过滤（千节点/集群规模） | 同上 |
| IP 搜索限定集群 | `uq_ip_addresses_cluster_ip (cluster_id, ip_key)` 隐式 btree；`ix_ip_addresses_resource_id (resource_id)` | `docs/database/F006.md` §2.1 |
| 管理 IP 列 join | `resources.management_ip_id` 引用 `ip_addresses(resource_id, id)`、`ix_resources_management_ip_id` | `docs/database/F006.md` §2.2 |
| 集群作用域回显/集群列 | `pk_clusters` | `docs/database/F001.md` |

### 3.3 性能与索引（`PROPOSED`，非阻塞）

- 需求 §9.2 基线约 1,000 台/集群、常用列表 P95 < 1s、搜索 P95 < 1.5s。现有 `(cluster_id, name)` 唯一索引可服务「集群作用域 + 名称排序」；类型/状态筛选为集群内行过滤，规模可接受。
- **`OPEN`（性能，非阻塞）**：若实测类型/状态筛选在最大集群下超目标，可后续以**独立 Database 变更**评估新增 `resources(cluster_id, status)` / `(cluster_id, resource_type)` 索引；本 Feature 不预置，且任何新增索引须按 AGENTS §6 走 Database 设计记录（`layers.database` 此时为 false）。
- `q` 为包含匹配（§8.2），不假设可用 btree 索引；服务端全量匹配（§8「不能只匹配当前页」）在集群内执行。列表查询不做 N+1：管理 IP 与集群列以 JOIN/批量查询一次取回（`PROPOSED`）。

### 3.4 Database 设计与 Backend 实现分工

- **Database**：本 Feature `NOT_REQUIRED`，不出 `docs/database/F003.md`，不新增/修改任何表、约束、索引或迁移脚本。
- **Backend**：在既有表上实现只读查询；不新增建表脚本。若 §3.3 性能项最终需要索引，须另立 Database 设计并由 Backend 以增量、向前兼容脚本落地（不在本 Feature 范围）。

---

## 4. 查询语义与字段（`CONFIRMED` 规则 + `PROPOSED` 机制）

### 4.1 集群作用域 `CONFIRMED`（§6.2、BQ-H）
- 资源页搜索与列表**限定当前已确认集群**，不隐式切换作用域（§6.2、场景 56）。
- `PROPOSED`：使 `GET /resources` 的 `cluster_id` **必填**，服务端以该值作为唯一作用域；缺失或非法 → `400 INVALID_REQUEST`（`errors[].code=CLUSTER_ID_REQUIRED` / `CLUSTER_ID_INVALID`）。理由：把「首屏必须选择或确认集群」「不隐式切换作用域」落到服务端，避免前端遗漏导致跨集群结果；这也是 F010 独立全局入口与资源页区分的基础。备选（`cluster_id` 可选、省略即跨集群）被否：违反「不隐式切换作用域」并可能与 F010 重叠。
- `cluster_id` 存在但无资源 → `200` + `items: []`、`total: 0`。`PROPOSED`：不存在的 `cluster_id` 亦返回 `200` + 空列表（与 F005 `GET /network-segments` 的筛选语义一致，筛选无结果不报 404）。

### 4.2 类型切换与状态筛选 `CONFIRMED`（§6.2）
- 类型：`resource_type ∈ {bare_metal, virtual_machine}`；省略 = 全部（对应「全部 / 裸金属 / 虚拟机」切换）。
- 状态：`status ∈ {IDLE, ALLOC, DOWN, UNKNOWN}`；省略 = 全部。
- 非法值 → `400 INVALID_REQUEST`（`errors[].code=RESOURCE_TYPE_INVALID` / `STATUS_INVALID`）。

### 4.3 名称 / IP 搜索 `q` `CONFIRMED`（§6.2、§8.1/§8.2）
- `q` 去首尾空格；空串 = 不搜索。英文不区分大小写；`%`、`_` 按普通字符处理（转义为字面量）；IPv4 允许部分字符串。
- 匹配对象（§8.1「资源名称、资源 ID、已分配 IPv4」）：资源 `name`、资源 `id`（当 `q` 为纯数字）、本资源**已登记 IP**（`ip_addresses.ip`，限定 `cluster_id` 作用域）。
- `PROPOSED` 匹配与排序权重（依据 §8.2「完全匹配优先、其次前缀、再其次包含；同级按名称及 ID 稳定排序」）：
  1. 名称或 IP 完全匹配（不区分大小写）；
  2. 名称或 IP 前缀匹配；
  3. 资源 ID 精确匹配（`q` 为纯数字且等于 `id`）；
  4. 名称或 IP 包含匹配。
  结果先按权重升序，再按 `sort`（默认 `name`）升序，最后按 `id` 稳定排序。
- **不**因 `q` 命中 IP 而返回其它集群资源：IP 子查询固定 `ip_addresses.cluster_id = :cluster_id`（与资源 `cluster_id` 一致）。

### 4.4 排序 `sort` `CONFIRMED`（§6.2 默认按名称）
- 允许值：`name`/`-name`/`updated_at`/`-updated_at`/`created_at`/`-created_at`/`status`/`-status`；`-` 前缀降序。
- 默认 `name`（升序）；无 `q` 时按 `sort` + `id` 稳定排序。非法 `sort` → `400 INVALID_REQUEST`（`errors[].code=INVALID_SORT`）。

### 4.5 分页 `CONFIRMED`（§6.2、§9.2、ADR-003）
- offset 分页：`page`（int，默认 1，≥1）、`page_size`（int，默认 20，1–100）；返回 `total`（当前集群作用域与过滤条件下匹配总数）、`page`、`page_size`。
- 非法 `page`/`page_size` → `400 INVALID_REQUEST`。
- 服务端全量匹配与分页，不得只匹配当前页（§8.3）。

### 4.6 类型 / 状态展示文字 `PROPOSED`（依据 §6.2、§9.4）
- 列表项同时返回代码与展示文字，避免各客户端各自维护映射：`resource_type_label`（`bare_metal→裸金属`、`virtual_machine→虚拟机`）、`status_label`（`IDLE→空闲`、`ALLOC→已分配`、`DOWN→宕机`、`UNKNOWN→未知`）。
- 文字取值直接来自 §1.3、§4.3 已确认定义，不新增业务规则；`PROPOSED` 为「由服务端统一给出」的机制选择。前端仍可据此做颜色/图标，但**状态不得只靠颜色**（§9.4）。
- 时间列（`updated_at` 等）以 `string(date-time)`（RFC 3339 UTC）返回，由前端按时区显示（§9.4）。

---

## 5. 详情展示与扩展点

### 5.1 详情端点取舍（`PROPOSED`，依据 F002 §2.2 边界）
- **选择：复用 F002/F006 `GET /resources/{resource_id}`，不新增只读详情端点。**
- 理由：该端点已返回 `ResourceFormDetail`，公共详情所需字段（名称、集群、类型、状态、状态来源操作者、状态更新时间、`updated_at`、网卡 + IP + 管理 IP）**全部齐备**；同一份公共信息同时服务「表单加载」与「展示详情」，避免两套字段定义漂移，符合 AGENTS §4「同一份详细信息只维护一个权威来源」与 §2.6「无需求不新增抽象」。
- 备选（新增 `GET /resources/{resource_id}/overview` 等只读端点）被否：与既有端点字段重复、存在不一致风险，且 F004/F007 的扩展应作用于同一资源详情对象，而非再分叉。
- 扩展方式（`PROPOSED`，交 F004/F007）：类型专有字段（F004）与服务关联（F007）以**附加字段**扩展同一 `ResourceFormDetail`（或统一的资源详情响应），不改变 F002/F006 既有字段语义；F003 详情页为这些扩展预留容器。

### 5.2 详情页内容 `CONFIRMED`（§6.3）
- 公共信息：名称、集群、类型、状态、状态来源（`status_updated_by_username`）、状态更新时间（`status_updated_at`）、更新时间（`updated_at`）。
- 网卡/IP：网卡名、关联网段（只读带出）、各 IP 地址；无 IP 网卡正常显示 `ips: []`（场景 8）；管理 IP 标识（`is_management`/`management_ip`）。
- 「服务」：**占位**，由 F007 扩展（`out_of_scope`）。
- 类型专有（CPU/内存/GPU/SN/宿主 VM/vCPU/宿主机）：由 F004 扩展，本 Feature 不交付。

---

## 6. API Contract（摘要；唯一字段清单见 `docs/api/F003.md`）

Contract 状态 **READY**。Base：`/api/v1`；错误统一 `application/problem+json`。

| # | Method | Path | 说明 | 角色 |
| --- | --- | --- | --- | --- |
| 1 | GET | `/resources` | 资源列表：当前集群作用域、类型/状态筛选、名称/IP 搜索、服务端分页、默认按名称排序（**本 Feature 新增**） | 任意已登录 |
| 2 | GET | `/resources/{resource_id}` | 资源公共详情（**复用 F002/F006，不重定义**） | 任意已登录 |

- F003 **不新增写端点**（`POST`/`PATCH`/`DELETE` 归 F002/F006）。
- 错误：`401 UNAUTHENTICATED`、`400 INVALID_REQUEST`（`CLUSTER_ID_REQUIRED`/`CLUSTER_ID_INVALID`/`RESOURCE_TYPE_INVALID`/`STATUS_INVALID`/`INVALID_SORT`/`INVALID_PAGE`/`INVALID_PAGE_SIZE`）。列表为只读，无 403（任意已登录可读），无 404（空结果与不存在集群均返回空列表，`PROPOSED`）。

---

## 7. Frontend / Backend 工作拆分

**Backend**：
- `app.resources`：新增 `GET /resources` 路由与只读查询 service；集群作用域必填校验；类型/状态筛选；`q` 名称/IP/ID 匹配与 §8.2 权重排序；排序白名单与默认 `name`；offset 分页与 `total`；管理 IP 与集群列 JOIN；类型/状态展示文字；problem+json 错误；pytest + httpx 测试。
- 不改 F002/F006 写端点；不改任何表/索引（Database `NOT_REQUIRED`）。

**Frontend**：
- 资源列表页 `/clusters/:clusterId/resources`（`PROPOSED` 新增路由，`name: cluster-resources`）：首屏确认集群（复用 `useClusterStore`，未选择时要求选择，不隐式切换）、全部/裸金属/虚拟机切换、类型与状态筛选、搜索框（限当前集群并**显式展示作用域**）、服务端分页、默认按名称排序、状态含文字（含颜色/图标）、窄屏表格横向滚动（§9.4）。
- 资源详情页 `/clusters/:clusterId/resources/:resourceId`（`PROPOSED` 新增路由，`name: resource-detail`）：公共信息 + 网卡/IP 表格 + 管理 IP 标识 + 「服务」占位；复用 `api/resources.ts` 的 `getResource` 与 `ResourceFormDetail` 类型。
- `PROPOSED`：新增 `useResourcePageScope` 组合式函数（对齐 F005 `useSegmentPageScope`），统一「集群作用域 + 列表刷新」；选择只改变作用域，不改变角色权限。
- axios 复用全局拦截；前端权限仅用于导航/隐藏，不作安全边界。

**Database**：`NOT_REQUIRED`（无设计、无脚本、无索引变更）。

---

## 8. Test Work

**后端集成（pytest + httpx）**：
- 作用域：`GET /resources` 缺 `cluster_id` → `400`；仅返回该集群仍存资源，不返回其它集群数据（场景 56 的「当前集群」侧；全局入口归 F010）。
- 类型/状态：全部/裸金属/虚拟机切换；状态筛选；非法值 → `400`。
- 分页/排序：`page`/`page_size` 边界；`total` 正确；默认按 `name` 升序、`id` 稳定；非法 `sort` → `400`；跨页无重复/遗漏。
- 搜索：按名称匹配（部分、大小写不敏感、`%`/`_` 字面量）；按 IP 部分匹配且**只在本集群**；同名 IP 跨集群时只返回本集群资源（场景 56 的资源页侧）；`q` 命中资源 `id`；匹配权重（完全 > 前缀 > 包含）与稳定排序。
- 列表列：管理 IP 有值/`null`；类型/状态展示文字正确；`updated_at` RFC 3339 UTC。
- 详情（复用端点回归）：无 IP 网卡显示 `interfaces[].ips: []`（场景 8）；状态来源操作者用户名；`management_ip` 有值/`null`。
- 权限：viewer/maintainer/admin 均可读列表与详情；未登录 → `401`；确认 F003 未新增写端点。
- 边界：空集群列表 `200 items: []`；不存在 `cluster_id` 的 `PROPOSED` 空列表行为；极大 `page` 返回空 `items` 且 `total` 不变。

**前端（Vitest）**：
- 列表页：首屏集群确认、类型切换、类型/状态筛选、分页/排序、搜索限当前集群与作用域展示、不隐式切换；状态文字与颜色；时间显示；横向滚动配置。
- 详情页：公共信息渲染、网卡/IP（含无 IP 网卡）渲染、管理 IP 标识、「服务」占位；复用 `ResourceFormDetail` 类型。
- 作用域：`useClusterStore` 选择变化刷新列表而不改角色权限；选择失效回退。

**联验（非本 Feature 闭环）**：类型摘要/宿主（F004，场景 1/33）；详情服务关联（F007）；全局 IP 查询与聚合计数（F010，场景 56 全局侧）；管理员历史查询（F012，场景 48/61/64）；跨对象权限一致性（F009）。

**未验证项声明**：本角色为只读 Architect，**未实际运行任何测试或建表**；以上为 Backend/Frontend 实现后必须执行的验证清单。架构完成不等于实现或验证完成。

---

## 9. 技术决策与风险

**已确认（依据）**：栈 ADR-001；PostgreSQL、真删无软删 ADR-002；REST/problem+json/offset 分页/稳定排序 ADR-003；HTTP-only ADR-004；状态含文字（§9.4）、状态来源仅操作者与单一状态时间 BQ-AA；名称口径 BQ-W；当前集群作用域且不隐式切换 §6.2/BQ-H；列表/详情公共列 §6.2/§6.3；服务端分页与 P95 目标 §9.2；F001/F002/F005/F006/F013 复用基础；F003 `layers.database=false`（project-plan F003）。

**PROPOSED（实现建议，不阻塞，不新增业务规则）**：
1. `GET /resources` 的 `cluster_id` 必填，作为唯一作用域；
2. 不存在 `cluster_id` 返回 `200` 空列表；
3. 列表项由服务端返回 `resource_type_label`/`status_label` 展示文字；
4. `q` 匹配名称/资源 ID/IP，权重「完全 > 前缀 > ID 精确 > 包含」，再按 `sort` + `id`；
5. 详情复用 `GET /resources/{resource_id}`，F004/F007 以附加字段扩展；
6. 前端新增 `cluster-resources` / `resource-detail` 路由与 `useResourcePageScope`；
7. 列表查询 JOIN 一次取回管理 IP 与集群列，避免 N+1。

**OPEN / 关注（非阻塞）**：
- 性能：类型/状态筛选在最大集群的实测；如需索引，另立 Database 设计（§3.3）；
- F004/F007 对同一 `ResourceFormDetail` 的附加字段命名与扩展方式，须在各自架构阶段与本 Contract 协调，避免字段冲突；
- F008 通用搜索规范落地后，`q` 的权重/交互可与本 Feature 对齐（本 Feature 已按 §8 设计，不预建通用框架）。

**风险**：详情页与表单共用 `GET /resources/{resource_id}`，若未来某字段仅表单需要（如 `version`），对详情页为冗余但无害；若未来详情需要与表单分叉的字段集，应在 F004/F007 阶段评估是否拆分，本 Feature 不做预建。

---

## 10. Implementation Layers

| Layer | 需要 | 说明 |
| --- | --- | --- |
| database | **false** | 只读既有 `resources`/`network_interfaces`/`ip_addresses`/`clusters`；无 Schema/Migration/索引变更；`docs/database/F003.md` 不产出 |
| backend | **true** | `app.resources` 新增 `GET /resources` 列表查询与作用域/筛选/搜索/排序/分页，复用详情端点；参数校验与 problem+json |
| frontend | **true** | 资源列表页、资源详情页、集群作用域与筛选/分页/排序/搜索、状态文字、详情网卡/IP 与服务占位 |

结论：**READY FOR IMPLEMENTATION**（实现仍须满足独立的 Contract Gate；本 Feature 无 Database 层，故无 Database Design Gate 依赖）。Contract 状态：**READY**。