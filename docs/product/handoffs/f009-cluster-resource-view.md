# Product Handoff — F009 Cluster 视角资源查询

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Feature: F009（E05，P0，`depends_on: [F001, F002]`，二者均已 DONE）
> 依据基线：`docs/product/requirements.md`（CONFIRMED BASELINE）、`docs/product/domain-model.md`（CONFIRMED）、`docs/product/domain-model.yaml`、`docs/api/api-conventions.md`（READY）、ADR-0003 / ADR-0004（ACCEPTED）、`docs/product/handoffs/f002-bare-metal.md`、`docs/api/f001-cluster.md`、`docs/api/f002-bare-metal.md`、`docs/api/f014-soft-delete.md`、`docs/project/project-plan.yaml`

---

## Problem

CSM 的核心动因之一是解决 Excel 场景中「同一资源信息要跨多个表 / 页面才能拼出来」的问题（`requirements.md` §1、§2、§16 引语）。F001 已让 Cluster 名称成为可信、唯一、可寻址的事实；F002 已让每台 BareMetal 的「属于哪个 Cluster、叫什么、当前什么状态」成为可信且可查询的事实。

但用户的问题还没完全解决：**运维人员站在「一个集群」的位置上，仍无法一眼回答「这个集群现在有哪些机器、各自什么状态」。**

使用者：HPC / AI 集群运维人员、基础设施管理员（§3）。典型场景：

- 巡检：进入集群，确认该集群的机器清单与状态分布（哪台 DOWN、哪台 IDLE）；
- 交接：按集群把一个集群的资源整体看清楚，而不是先跳到全局裸金属列表再筛选；
- 处置：发现某集群机器异常后，从集群视角定位到具体机器。

产品价值：**把「Cluster → 其所属资源（V1 实际可用的只有 BareMetal）及其状态」变成 Cluster 上下文内可直接获得的查询结果**，并保证「集群不存在」与「集群存在但没有机器」是两种清晰不同的结论（R-QUERY-004）。

---

## Confirmed Requirements

1. 用户应能够**从 Cluster 视角查看其所属资源**（R-QUERY-001，§16）。
2. 至少应支持查看 **Cluster → BareMetal，以及 BareMetal 的状态**（R-QUERY-002，§16）。
3. 查询结果必须能够区分 **Resource Not Found（资源不存在）** 与 **Empty Relationship（资源存在，但当前没有关联子资源）**；两者在产品语义上不同（R-QUERY-004）。
4. Cluster **不设状态**，不得为 Cluster 增加状态字段（R-CLUSTER-003；`domain-model.yaml > status_models.stateless_resources`）。
5. Cluster 可包含多个 BareMetal（R-CLUSTER-004 的 Cluster 视角方向）。每个 BareMetal **必属恰好一个 Cluster**（R-BM-001）。
6. BareMetal 是 V1 **唯一有状态资源**；状态为封闭集合 `IDLE / ALLOC / DOWN / UNKNOWN`（R-BM-003），**永不为空**（R-BM-005），由运维人员**人工维护**（R-BM-006）。
7. 已逻辑删除资源**默认不出现在正常查询结果中**（R-DELETE-002）；**不提供 Undelete / Restore**（R-DELETE-003）。
8. 已逻辑删除的 Cluster **不参与名称解析**，读取返回 `404 NOT_FOUND`（R-DELETE-002/006；`api-conventions.md` §2/§7）。
9. F001 契约已确认：`GET /api/clusters`、`GET /api/clusters/{cluster_id}`、`GET /api/clusters/by-name/{cluster_name}`、Empty 与 Not Found 的区分要求（`docs/api/f001-cluster.md` §2/§9）。
10. F002 契约已确认：`GET /api/bare-metals?cluster_id={id}` —— Cluster 不存在或已逻辑删除 → `404 NOT_FOUND`；Cluster 存在但无活跃 BareMetal → `200` + `items == []`（Empty）；已软删 BareMetal 不出现在 `items` / `total`（`docs/api/f002-bare-metal.md` §3.2）。
11. 通用契约（`api-conventions.md`，READY）：字段类型、列表信封、错误信封与稳定 `error.code`、`deleted_at` 不暴露、Empty/Not Found 前端必须渲染**不同**状态（§3/§4/§5/§6/§7）。
12. 所有 `/api/*`（登录端点除外）要求认证；未认证 → `401 UNAUTHENTICATED`（ADR-0005）。
13. `project-plan.yaml` 已固定需求归属：**R-QUERY-001 / R-QUERY-002 / R-QUERY-004 属 F009**；**R-QUERY-003 归属 F010**；R-CLUSTER-004 `covered_by: [F002, F009]`。

---

## Confirmed Domain Rules

| 规则 | 内容 | 来源 |
|---|---|---|
| R-QUERY-001 | 可从 Cluster 视角查看其所属资源 | `requirements.md` §16 |
| R-QUERY-002 | 至少支持 Cluster → BareMetal 及 BareMetal 状态 | `requirements.md` §16 |
| R-QUERY-004 | 必须区分 Resource Not Found 与 Empty Relationship | `requirements.md` §16；ADR-0003 §6；`api-conventions.md` §7 |
| R-CLUSTER-003 | Cluster 不设状态 | `requirements.md` §7；`domain-model.yaml > status_models` |
| R-CLUSTER-004 | Cluster 可包含多个 BareMetal（Cluster 视角方向由 F009 验收） | `requirements.md` §7；`project-plan.yaml > requirement_coverage` |
| R-BM-001 | 每个 BareMetal 必属恰好一个 Cluster（N:1 mandatory） | `requirements.md` §8 |
| R-BM-002 | 同 Cluster 内 `hostname` 唯一、大小写敏感；跨 Cluster 可重 | `requirements.md` §8、§22 |
| R-BM-003 / 005 / 006 | 状态封闭集合、永不为空、人工维护 | `requirements.md` §8 |
| R-DELETE-002 | 已逻辑删除资源默认不出现在正常查询结果中 | `requirements.md` §17 |
| R-DELETE-003 | V1 不提供 Undelete / Restore | 同上 |
| R-DELETE-004 / 005 | 父有活跃子不得删；软删不级联 | `requirements.md` §17；ADR-0004 |
| §15 Resource Relationship | 不得仅根据资源分类自动产生关系；未确认关系不得当作既成事实 | `requirements.md` §15 |
| §6 / §13 | 不建立 DataCenter 层级；不管理 Rack / U 位 | `requirements.md` §6、§13 |
| §23 | 不得引入自动资产发现、外部状态源、完整 CMDB 能力 | `requirements.md` §23 |
| ADR-0003 | `id` 为规范路径；Empty vs Not Found 全项目统一；`deleted_at` 不暴露 | ADR-0003（ACCEPTED） |
| ADR-0004 | 软删单一写入路径；`deleted_at IS NULL` 统一过滤；无 undelete | ADR-0004（ACCEPTED） |

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。**

---

## 需求条目

- **R-QUERY-001**：Cluster 视角资源查询（F009 主责）。
- **R-QUERY-002**：Cluster → BareMetal 及 BareMetal 状态（F009 主责）。
- **R-QUERY-004**：Resource Not Found vs Empty Relationship（F009 必须在其 Cluster 视角查询路径上完整成立；F010 亦覆盖）。
- **R-CLUSTER-004**：Cluster 视角方向（F009 侧验收；N:1 写入方向归 F002）。
- **R-QUERY-003**：**不属 F009**。NIC / IPAddress / VirtualMachine / Container / Service 关系查询归 **F010**。F009 不得发明尚未确认或尚未实现的关系（§15）。
- **R-DELETE-002 / 003**：已软删 Cluster / BareMetal 在 F009 视图中的可见性；无恢复入口。

---

## 目标与范围

### 本次包含

1. **Cluster 视角成员查询与展示**：从某个 Cluster 出发，查看该 Cluster 的活跃 BareMetal 清单及其状态（R-QUERY-001、R-QUERY-002、R-CLUSTER-004）。
2. **Not Found 与 Empty 的产品语义区分**（R-QUERY-004；`api-conventions.md` §7）：Cluster 不存在或已逻辑删除 → Not Found；Cluster 存在但无活跃 BareMetal → Empty。
3. **状态展示**：视图中每台 BareMetal 呈现当前 `status`；取值来自 `IDLE / ALLOC / DOWN / UNKNOWN`，永不为空（R-BM-003/005）；人工维护的状态重新查询后可见（R-BM-006）。
4. **软删过滤**：视图只呈现活跃 BareMetal（`deleted_at IS NULL`，复用统一过滤原语）；已软删 Cluster 的视图不可达（R-DELETE-002；ADR-0004）。
5. **从 Cluster 上下文可达**：用户可在 Cluster 视角内获得查询结果，无需先进入全局裸金属列表再筛选（R-QUERY-001）。
6. **前端状态渲染要求**：Loading / Empty / Error(NotFound 及其他) 三态互不相同；Empty 与 Not Found 可被用户区分；错误按 `error.code` 分支渲染（R-QUERY-004；`api-conventions.md` §5/§7）。
7. **认证边界**：视图相关请求受 F013 中间件保护；未认证 → `401 UNAUTHENTICATED`（ADR-0005）。

### 本次明确不包含

1. **R-QUERY-003 对应的 NIC / IPAddress / VirtualMachine / Container / Service 关系查询与展示** —— 归 F010。F009 不得提前建模任何上述关系（§15）。
2. **BareMetal 的实体、字段、状态写入与 CRUD** —— 归 F002。
3. **Cluster 自身的展示与 CRUD / `by-name` 详情别名** —— 归 F001。
4. **Cluster 与 BareMetal 的删除语义** —— 归 F014。
5. **任何 Cluster 状态字段或状态推导** —— 明确排除（R-CLUSTER-003）。
6. **Undelete / Restore / 已删资源查看出口 / 回收站** —— 明确排除（R-DELETE-003）。
7. **DataCenter / 园区 / 机房 / 机柜 / U 位等位置或上级模型** —— 明确排除（§6、§13）。
8. **自动资产发现、外部平台 / 实时状态源接入** —— 明确排除（R-BM-006；§23）。
9. **状态自动推导或状态源接入** —— 明确排除（R-BM-006）。

### 本次未涉及

当前需求没有要求，但不能推断为永远不需要：

- **状态汇总 / 计数**（见 NQ-1）；
- 视图内的排序规则、关键字搜索、按状态筛选、按硬件字段筛选；
- 导出（CSV / Excel）；
- 视图内的分页形态 / 每页条数（沿用 F002 既定分页即可，不作为产品规则）；
- 视图内直接进入 BareMetal 详情、或从视图发起状态修改；
- 展示字段的完整范围（最小要求为 `hostname` + `status`，见 AC-02）；
- 视图的页面组织形态（**明确由 Frontend 设计**，见 NQ-2）；
- 状态变更历史 / 审计 / 时间线；
- 资源使用率 / 容量 / 监控指标。

---

## Acceptance Criteria

**查询与展示**

- **AC-01（Cluster 视角可见其 BareMetal）**：存在活跃 Cluster C 且其下有 2 台活跃 BareMetal 时，从 Cluster 视角查询/查看该 Cluster 的成员，结果包含**这 2 台**记录（R-QUERY-001、R-QUERY-002、R-CLUSTER-004）。
- **AC-02（展示 hostname 与状态）**：每一条成员记录中，用户可观察到该 BareMetal 的 `hostname` 与 `status`；`status` 取值属于 `IDLE / ALLOC / DOWN / UNKNOWN` 且**不为空 / 不为 `null`**（R-QUERY-002；R-BM-003/005）。
- **AC-03（只含本 Cluster 的机器）**：Cluster C1 与 C2 各有 BareMetal 时，Cluster C1 视角的结果**不含** C2 的任何 BareMetal；反之亦然（R-BM-001；R-CLUSTER-004）。
- **AC-04（状态反映最新事实）**：对某台 BareMetal 执行既有状态修改（F002 `PATCH`）为 `DOWN` 后，重新从 Cluster 视角查询，该台 `status` 显示为 `DOWN`；其他机器状态不受影响（R-BM-006；R-QUERY-002）。
- **AC-05（中文往返）**：Cluster 名称与 BareMetal `hostname` 含中文时，在 Cluster 视角结果中按字面值正确读出（§21）。

**R-QUERY-004：Not Found vs Empty（本 Feature 关键产品语义）**

- **AC-06（Resource Not Found）**：Cluster **不存在**时，从 Cluster 视角查询其成员 → `404 NOT_FOUND`；**不得**返回 `200` + 空清单；界面渲染为「资源不存在」类状态，**不得**渲染为「该集群暂无机器」（R-QUERY-004；`api-conventions.md` §7）。
- **AC-07（已软删 Cluster 同为 Not Found）**：数据层直接置入 `deleted_at` 非空的 Cluster 后，从 Cluster 视角访问该 Cluster → `404 NOT_FOUND`，与「不存在」不做区分；界面同样渲染 Not Found 态（R-DELETE-002/006）。
- **AC-08（Empty Relationship）**：Cluster 存在且活跃、但其下**没有任何活跃 BareMetal** 时 → `200` + 空集合，界面渲染为「该集群暂无裸金属」类 **Empty** 态（R-QUERY-004）。
- **AC-09（Empty 与 Not Found 界面可区分）**：AC-08 的 Empty 态与 AC-06/AC-07 的 Not Found 态在界面上互不相同（文案、样式或状态标记任一项可被独立断言）；同时与请求失败（Error）态也不同（R-QUERY-004）。
- **AC-10（Empty 不是错误）**：AC-08 情形下界面不呈现错误提示、不呈现 404 / 失败文案，也不触发全局会话失效处理（R-QUERY-004）。

**软删语义**

- **AC-11（已软删 BareMetal 不出现）**：数据层**绕过应用层**预置一条 `deleted_at` 非空的 BareMetal（同一 Cluster 下另有一台活跃 BareMetal）后，从 Cluster 视角查询 → 仅返回活跃那台（R-DELETE-002；ADR-0004）。
- **AC-12（删除后从视图消失）**：对某台 BareMetal 执行既有 `DELETE`（F002 → F014 统一软删）后，重新从 Cluster 视角查询 → 该台不再出现；其余机器与 Cluster 自身不受影响（R-DELETE-002/005）。
- **AC-13（无恢复入口）**：Cluster 视角视图中不存在 restore / undelete / 查看已删资源 / 回收站 / `include_deleted` 类入口或参数（R-DELETE-003；ADR-0004）。

**边界**

- **AC-14（不越界到 R-QUERY-003 的资源类型）**：F009 的 Cluster 视角视图与其查询路径中，不存在 NetworkInterface / IPAddress / VirtualMachine / Container / Service 的列表、计数、占位区或方向性关系入口；也不存在任何为此预留的字段或占位（R-QUERY-003 归属 F010；§15）。
- **AC-15（不新增领域字段）**：Cluster 视角视图的请求 / 响应中不存在 Cluster 状态字段、DataCenter / 位置字段，也不存在任何自动发现 / 实时状态源相关字段（R-CLUSTER-003；§6、§13；R-BM-006；§23）。
- **AC-16（认证边界）**：未认证访问 Cluster 视角相关端点 → `401 UNAUTHENTICATED`，且不返回任何资源数据（ADR-0005）。

**明确不进入 F009 AC**：R-QUERY-003 的跨资源关系查询（F010）；Cluster / BareMetal 的登记、修改、删除本身（F001/F002/F014）；状态变更历史；状态计数汇总（NQ-1）；导出 / 高级筛选 / 审计 / 批量操作。

---

## 与既有 Feature 的边界

| 邻接 Feature | 边界（F009 的立场） |
|---|---|
| **F001 Cluster** | F009 不重复实现 Cluster CRUD、`by-name` 详情别名、Cluster 字段展示。复用 F001 已确认的「Cluster 不存在 / 已删 → `404 NOT_FOUND`」判定语义。不为 Cluster 增加任何字段（R-CLUSTER-003）。 |
| **F002 BareMetal** | F002 已交付 BareMetal 实体、`hostname`、`status`，以及**按 Cluster 限定读取**能力 `GET /api/bare-metals?cluster_id={id}`，并已实现其 Empty / Not Found 语义。**F009 不需要新的 BareMetal 领域能力**。F009 不修改任何 BareMetal 字段 / 唯一性 / 状态规则。 |
| **F014 软删** | F009 只消费 `deleted_at IS NULL` 过滤结果（ADR-0004 统一过滤原语），不实现任何软删写入路径、不做父删子拦、不提供删除入口。 |
| **F010 资源详情与关联查询** | **R-QUERY-003 归 F010**。F009 只做 Cluster → BareMetal 这一条 V1 实际已实现且已确认的关系。任何其他关系在本 Feature 中不存在，也不预留结构（§15）。 |
| **F004 / F005 / F006 / F007 / F008** | 未 DONE。其实体 / 表 / 端点目前不存在。F009 不得假设其存在、不得发明关系、不得为它们预留展示位。 |

### 聚合展示 vs 新后端查询能力（正面回答）

**产品立场：F009 的确认目标是「Cluster 视角的查询结果与展示语义」，不是新增 BareMetal 领域能力。**

- F009 不要求新增领域对象、字段、关系或状态。
- F002 既有的「按 Cluster 限定读取」能力已具备满足 R-QUERY-001/002/004 所需的数据与 Empty/Not Found 语义；因此 F009 在功能上可以落在纯聚合 / 展示层。
- **但** `adr-0003` §2 与 `api-conventions.md` §2 列出的只读名称别名 `GET /api/clusters/by-name/{cluster_name}/bare-metals` **当前无 Feature 认领**：F001 明确排除，F002 明确排除并指明「属 F009」。该别名一旦由 F009 交付，F009 就不只是纯前端聚合。是否交付、路由形态与归属由 Architect 裁定（NQ-3）。
- **页面组织由 Frontend 设计**（R-QUERY-003 末句）。

### 已确认交付重叠（必须记录，不得静默选择）

F002 的前端已经实现了一个从 Cluster 进入、按 `cluster_id` 限定的裸金属列表：

- `frontend/src/pages/ClusterDetailPage.vue` 提供「查看裸金属」入口（注释明示「Cluster 视角成员视图属 F009」）；
- `frontend/src/pages/BareMetalListPage.vue` 支持 `clusterId` 过滤，并已实现 Empty / Not Found / Loading 三态；
- `frontend/src/App.vue` 的 `ResourceView` 已含 `bare-metal-list` + `clusterId` 上下文。

这意味着 R-QUERY-001/002/004 的一部分已经由 F002 的前端交付物实际满足。F009 与 F002 的差异边界必须显式澄清（NQ-2），否则可能出现「同一 Cluster 视角存在两个入口」或「F009 无实际交付物」两种情况。按 `AGENTS.md` §3，本文不改写任何已确认规则。

---

## Assumptions

（不阻塞当前工作、可安全暂时采用；**不得当作 CONFIRMED**）

1. F009 不新增 / 不修改任何领域对象、字段、关系、状态、唯一性规则；不新增数据库表或列；无 migration 需求。
2. F009 复用 F001/F002 既有 API 契约与前端组件，不另立约定。
3. 视图的**最小展示字段**为每台 BareMetal 的 `hostname` 与 `status`；其余属展示设计。
4. 视图沿用 F002 既有的分页约定（`page` / `page_size`），不作为产品规则固化。
5. 前端路由 / 页面组织延续现状（无 `vue-router`），页面切换形式不构成产品规则。
6. F009 的交付层归属（frontend-only 或 frontend + backend 只读别名）由 Architecture 判定。

---

## Proposed Rules

**PROPOSED-1（需用户裁定，非 CONFIRMED）**：若希望在 Cluster 视角提供**状态汇总 / 计数**，应作为产品规则显式确认。当前 R-QUERY-001/002 未要求聚合计数。F009 不实现、不承诺该能力（NQ-1）。

**PROPOSED-2（需用户裁定，非 CONFIRMED）**：若希望 Cluster 视角视图**默认同时展示 R-BM-007 硬件字段**（而不是仅 `hostname` + `status`），建议显式确认展示范围。不改变 R-QUERY-002 的成立。

---

## Open Questions

### Blocking

**无。**

判定依据：F009 的范围由 R-QUERY-001/002/004 + R-CLUSTER-004 + R-DELETE-002/003 + 已批准 ADR / 契约完全确定；R-QUERY-003 的归属已固定为 F010。全部 AC 均为单值、可判定，不依赖 NQ-1 ~ NQ-5 中任何一项。沿用 F001 / F002 的先例。

### Non-blocking

- **NQ-1（状态汇总 / 计数）**：UNCONFIRMED。F009 不实现、不承诺（PROPOSED-1）。不阻塞架构设计。
- **NQ-2（F009 与 F002 既有前端交付物的重叠）**：需澄清 F009 的正面交付物：**(a)** 复用 / 承接 F002 的该入口与页面，F009 主要落在语义验证与必要收口；还是 **(b)** 由 F009 提供一个新的、以 Cluster 为主语的成员视图（并决定是否与既有入口合并）。两种选择都满足全部 AC。建议在 Architecture 阶段显式裁定。
- **NQ-3（`by-name/{name}/bare-metals` 只读别名的归属与形态）**：F001 明确排除，F002 明确排除并指明「属 F009」。建议由 Architect 裁定：(a) 由 F009 交付该只读别名；或 (b) 明确降级 / 移除该别名。不阻塞 F009 主体 AC。
- **NQ-4（展示字段范围）**：见 PROPOSED-2 / 假设 3。不阻塞。
- **NQ-5（`project-plan.yaml` 元数据同步）**：建议 Architecture 阶段把 AC-01 ~ AC-16 与 NQ-2/NQ-3 的裁定结果落回 `project-plan.yaml > F009`。

---

## 变更影响

**无产品规则变更。**

- 不新增、不修改、不废弃任何 CONFIRMED 规则、领域对象、字段、关系、状态或唯一性规则。
- 不要求任何数据库 Schema / migration 变更（假设 1）。
- F009 是 R-QUERY-001/002/004 与 R-CLUSTER-004 Cluster 视角方向的读取侧落地；不削弱 F001/F002/F014/F010 的任何已确认边界。

**需记录的文档 / 计划漂移（不修改，交由对应角色处理）：**

1. **F002 → F009 交付重叠**（NQ-2）。不构成产品规则冲突。
2. **`by-name/{name}/bare-metals` 无认领者**（NQ-3）。不构成产品规则冲突。
3. **`project-plan.yaml > F009` 元数据为空骨架**（NQ-5）。

---

## Architecture Handoff

1. **F009 的交付面裁定（NQ-2）**：确认 F009 是「复用 / 承接 F002 既有 Cluster 限定读取与前端入口」还是「新增一个 Cluster 视角成员视图」。F009 不得为此退化成新增 BareMetal 领域能力。
2. **`by-name/{cluster_name}/bare-metals` 别名归属与契约正文（NQ-3）**：裁定交付或降级；若交付，明确 canonical / alias 关系、大小写敏感匹配、已删 Cluster 不参与解析、Empty 与 Not Found 判定位置，并确定权威契约落点。不得让该别名成为第二条软删过滤路径（ADR-0004）。
3. **Cluster 存在性 / 活跃性与聚合读取的一致性**：确认「Cluster 不存在 / 已删 → 404」与「无活跃 BareMetal → 200 Empty」的判定在同一事务 / 同一读取路径内一致；保证已软删 BareMetal 过滤复用统一原语。
4. **前端三态与 Empty/Not Found 渲染（AC-09/AC-10）**：沿用 F001/F002 既有 `ListStates` / `ErrorState` / Empty 判定约定；确认 Not Found 与 Empty 在 UI 上可被独立断言，且不把 Empty 渲染为错误、不触发全局 401 处理。
5. **AC 与计划的落盘（NQ-5）**：把 AC-01 ~ AC-16 与 NQ-2/NQ-3 的裁定结果写入 `project-plan.yaml > F009` 的 `acceptance_criteria` / `layers` / `contract`；明确 `database: false` 与 backend / frontend 层范围。
6. **边界守卫（AC-14）**：确认 F009 的视图 / 端点不注册、不预留、不占位 NIC / IP / VM / Container / Service 的类型、字段或路由（§15）。
7. **测试与验证方法**：明确 AC-06/07、AC-08、AC-11、AC-12、AC-16 的验证方式；沿用 F002 的「数据层直接预置」取向，不依赖未完成 Feature。
8. **认证边界**：确认 F009 新增路径（若有）位于 `/api` 前缀下、由 F013 中间件自动覆盖，无需白名单。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。

GIT: NONE
