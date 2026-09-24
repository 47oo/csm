# Product Handoff — F018 集群内资源关键字搜索

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-18
> Feature: **F018 — 集群内资源关键字搜索**（Cluster-scoped Keyword Search）
> 上游决策：用户 2026-09-18 对 `DEC-021` 裁定「做」，并逐条裁定 `NQ-1 ~ NQ-5`（详见 `docs/project/v1/project-plan.yaml` `features[F018].open_questions` 各条 `resolved_to`）。

## Feature

**F018 — 集群内资源关键字搜索**（Cluster-scoped Keyword Search）

- Epic：E05「资源查询与视图」；Milestone：M8
- 层级：`{database: false（待 Architecture 裁定索引后可能变 true）, backend: true, frontend: true}` — **全栈**
- Contract：`REQUIRED`（必须新增 / 修订契约；三份既有契约当前明确禁止关键字参数）
- **本阶段核心交付**：在 `docs/product/requirements.md` §16 新增已确认产品规则 **R-QUERY-005**（= 计划中的 NQ-8），使本 Feature 可挂 requirement ID。规则原文见 §16。

## Problem

**谁在什么情况下使用**：CSM 的内部运维人员在生产实例（`http://192.168.10.221/`，设计规模 10⁵ 资源 / 并发 50）上维护与排查资源。

**实际问题**：替代 Excel 之后，运维人员仍常处于「已在脑子里定位到某个集群、想凭一段关键词（机器名片段、IP 片段、镜像名、服务 URL、负责人等）快速找到那条记录」的场景。当前系统只能**逐类资源列表逐页翻找**——后端无任何搜索能力，前端 7 个 `*ListPage.vue` 也没有搜索输入框。要跨 BareMetal / NIC / IP / VM / Container / Service 六类对象定位一个片段，用户必须分别打开多个页面逐页人工比对。

**本 Feature 解决的是「在**一个已选定 Cluster** 范围内，用一段关键字快速定位资源」的查询效率问题**；**不改变**任何资源的登记、关系、状态、唯一性或生命周期行为。关键词搜索是**新的产品能力**：§16 现有 R-QUERY-001 ~ R-QUERY-004 **均不涉及关键字 / 模糊 / 全文搜索**，故必须先新增 R-QUERY-005。

## Confirmed Requirements

1. **前置条件**：搜索必须先选定**一个** Cluster；未选定 Cluster 时不可发起搜索。（NQ-5）
2. **范围**：恒为所选 Cluster，**不跨 Cluster**。命中对象 = 该 Cluster 下活跃 BareMetal **及**与之相关（按 **R-QUERY-003 的「与 BareMetal 相关」定义，含「含间接」推导**）的活跃 NetworkInterface / IPAddress / VirtualMachine / Container / Service。（NQ-1）
3. **匹配字段**：标识字段 + 已登记的描述性字段；字段本身的定义以 `docs/product/domain-model.yaml` 为权威。（NQ-2）
4. **匹配语义**：**模糊 = 子串包含**；**不区分大小写**；**单关键字**（不做 AND / OR、不做分词 / 拼写纠错 / 相似度）。（NQ-3）
5. **结果呈现**：**单一混合列表**（不分组）；每条结果**显示其命中字段**；**无命中复用 R-QUERY-004 的 Empty 语义**。（NQ-4）
6. **入口**：位于**应用外壳**（`frontend/src/App.vue`），并承载「当前选定 Cluster」上下文。（NQ-5）
7. **只读**：不创建 / 修改 / 删除任何资源，无写端点、无写副作用。（AC-01）
8. **软删过滤**：已逻辑删除的资源不出现在任何搜索结果中。（AC-02；R-DELETE-002；ADR-0004）
9. **认证**：未认证 → `401 UNAUTHENTICATED` 且不返回资源数据。（AC-03）
10. **错误渲染**：前端按 `error.code` 渲染，不解析 `message`、不重复实现业务校验；Loading / Empty / Error 三态互不相同。（AC-07）

## Confirmed Domain Rules

| 来源 | 内容 | 对本 Feature 的含义 |
| --- | --- | --- |
| §16 **R-QUERY-001 / 002** | 从 Cluster 视角查看其所属资源 | 搜索的**范围边界**来自「Cluster 视角」这一既有定位 |
| §16 **R-QUERY-003**（含 2026-09-18「与 BareMetal 相关」的确切含义） | 与 BareMetal 相关的五类资源，**含间接推导** | 搜索范围**直接引用**，**不得重述后产生第二份权威** |
| §16 **R-QUERY-004** | 区分 Resource Not Found 与 Empty Relationship | 无命中 = Empty（200 + 空结果）；Cluster 不存在 / 已软删 = Not Found（404），二者**可区分** |
| §16 **R-QUERY-005（本次新增）** | Cluster 内关键字搜索 | 本 Feature 的**直接产品依据** |
| §22 Case Sensitivity | 名称唯一性比较**区分大小写** | 搜索的「不区分大小写」**仅限搜索匹配** |
| §17 R-DELETE-002 | 已逻辑删除资源不出现在正常查询结果 | 搜索须过滤软删 |
| §19 R-AUTH-001/003 | 本地账号认证；V1 无 RBAC | 搜索端点仅需认证 |
| §4 / §24 | Resource 仅表示分类体系；不得引入通用 `resources` 表 / EAV / STI | 搜索**不改变**各资源独立数据模型 |
| §23 / §10 / R-VM-002 / R-BM-007 | V1 不做自动资产发现 / 外部同步 | 搜索**不引入**任何发现 / 同步能力 |
| `domain-model.md` §8 Uniqueness | 各类唯一性边界 | 搜索**不新增、不修改**任何唯一性约束 |
| `f001-cluster.md` / `f014-soft-delete.md` | `by-name` 字面值大小写敏感解析；软删无恢复 | 「不区分大小写」**不适用于** `by-name` 解析 |

**冲突核查**：R-QUERY-005 与上述规则**均不冲突**——它在四条边界上被显式约束：(a) 大小写不敏感**仅限搜索匹配**；(b) 模糊**仅指子串包含**；(c) 搜索结果**不改**唯一性 / 软删 / `by-name` / 登录语义；(d) 搜索**只读、不跨 Cluster、不引入发现 / 同步**。

**一处已识别的字段清单不一致（非阻塞，未静默选择）**：`NQ-2.resolved_to` 的字段清单以 `Cluster.name` 开头，而 `NQ-1` / `AC-D1` 限定结果只含 BareMetal + 五类资源。本 Handoff 依 `AC-D1`（更具体且已裁定）判定 **Cluster 自身不产生结果行**，故 R-QUERY-005 未把 `Cluster.name` 列为可命中字段。**已列入 Non-blocking NQ-A 请用户确认**（详见下文）。

## Scope

### 本次包含

1. `requirements.md` §16 新增 **R-QUERY-005**（已完成）。
2. **后端**：只读关键字搜索，限定单个 Cluster，覆盖 BareMetal + R-QUERY-003 五类关联资源。
3. **前端**：应用外壳内全局搜索入口 + 「当前选定 Cluster」上下文；结果为**单一混合列表**并**显示命中字段**；三态。
4. **匹配**：子串包含 + 不区分大小写 + 单关键字。
5. **契约**：新增搜索契约，并**同步修订**三份既有契约的「关键字禁止」立场。
6. 软删过滤与认证成立；Not Found / Empty 可区分。

### 本次明确不包含

1. **跨 Cluster 搜索**（NQ-1 / AC-D1）。
2. **多关键字 / AND / OR / 分词**（NQ-3）。
3. **容错 / 相似度 / 拼写纠错级模糊**（NQ-3 二次确认）。
4. **自动资产发现 / 外部平台同步**（§23；R-VM-002；R-BM-007）。
5. **写操作**（AC-01）。
6. **改变既有语义**：不改 §22 大小写、`by-name` 解析、登录语义、软删语义、任何唯一性约束（AC-05）。
7. **物理删除 / Undelete / 查看已删资源**（R-DELETE-001/003）。

### 本次未涉及

结果排序、结果总数之外的统计、导出、状态筛选、搜索历史 / 保存查询、关键词高亮、分页形态与页大小取值、跨 Cluster / 全局搜索、性能 SLA、**空关键字输入的明细行为**（见 PROPOSED-1）。
> 以上均**不得据此推断为永远不需要**。

## Acceptance Criteria

**通用 AC**

- **AC-01（只读）**：任何一次搜索都不创建 / 修改 / 删除资源；不存在可用的搜索写端点，搜索路径无写副作用（可核验：搜索后相关记录 `updated_at` 与数据内容不变）。
- **AC-02（软删过滤）**：已逻辑删除的六类资源**不出现**在任何搜索结果（`items` 与 `total` 均不含），即使其字段值正好命中。
- **AC-03（认证）**：未认证访问搜索相关端点 → `401 UNAUTHENTICATED`，响应体不含任何资源数据。
- **AC-04（Not Found / Empty 区分）**：目标 Cluster 不存在或已软删 → `404 NOT_FOUND`；Cluster 存在且活跃但无命中 → `200` + 空结果 + Empty 态。二者界面互不相同、可独立断言。
- **AC-05（不改既有语义）**：不新增唯一性约束；不改 §22 比较、`by-name` 字面值解析、用户名查找禁止 `lower()/ILIKE`。可核验：`cluster-a` 与 `Cluster-A` 仍被视为不同值；`by-name` 仍精确匹配。
- **AC-06（契约一致）**：搜索契约已持久化且 `contract.status = READY`；`f005:129` / `f009:181` / `f010:172` 及 `f002:454` 中「不存在关键字参数 / 不得构造 / 排除筛选」的立场已按 `DEC-021` 同步修订；**不得存在「契约禁止、实现却有」的分裂**。
- **AC-07（前端三态）**：Loading / Empty / Error 互不相同；错误按 `error.code` 渲染、不解析 `message`、不重复实现业务校验。
- **AC-08（范围边界）**：不引入自动资产发现 / 外部同步 / 未确认的排序 / 导出 / 状态筛选（可核验：无相应入口、无相应参数）。

**裁定 AC（取自用户 NQ-1 ~ NQ-5 答案）**

- **AC-D1（NQ-1=(b) 范围）**：结果只包含**选定 Cluster 下**的 BareMetal 及其 R-QUERY-003 五类关联资源（含「含间接」推导）；不含其他 Cluster 的资源，不含该 Cluster 之外的任何命中。
- **AC-D2（NQ-2=(b) 字段）**：命中**只由**标识字段 + 描述性字段（清单见 `features[F018].open_questions[NQ-2].resolved_to`）产生；未列出的字段不参与匹配。
- **AC-D3（NQ-3 匹配）**：**子串包含**即命中；**不区分大小写**（`ABC` 与 `abc` 命中同一结果）；该不区分大小写**仅适用于搜索匹配**，不改 §22 / `by-name` / 登录语义。**不支持多关键字拆分**。
- **AC-D4（NQ-4 呈现）**：**单一混合列表**（不分组），**每条结果显示其命中字段**；**无命中复用 Empty 语义**（200 + 空结果 + Empty 态，**不得 404**，且与 Cluster 不存在 / 已删可区分）。
- **AC-D5（NQ-5 入口）**：入口位于**应用外壳**；**未指定 Cluster 时不可发起搜索**；指定后范围恒为该 Cluster。

## Assumptions

（不阻塞、可安全暂用；**不得**当作 CONFIRMED）

- **A-1**：搜索结果沿用既有分页信封 `{items, total, page, page_size}`（属**实现一致性选择**，非新产品规则）；最终形态由 Architecture 在契约中定稿。
- **A-2**：字段清单中**数值型**字段（`port` / `cpu` / `memory` / `disk`）按**文本**参与子串匹配——「子串包含 + 任意关键字」对已列字段的直接含义，**非新增规则**。
- **A-3**：应用外壳的「当前选定 Cluster」上下文可复用既有 `resourceView` 的集群上下文（`clusterId` / `returnClusterId`）；是否复用归 Architecture 裁定。
- **A-4**：「命中字段」至少以**字段名**告知命中原因；具体展示形态（徽标 / 文本 / 高亮）由 Frontend 决定，不在 AC 中规定。

## Proposed Rules

**非 CONFIRMED，不得实现为既定需求：**

- **PROPOSED-1**：**空 / 仅空白关键字不构成有效搜索**——前端在无有效关键字时不发起请求（或禁用搜索动作），后端对空关键字返回 `400 VALIDATION_ERROR`；即**不把空关键字解释为「返回该 Cluster 全部资源」**。理由：用户需求是「按关键字查询」，空串返回全量会造成与「列表浏览」混淆的意外行为。**需用户裁定后方可写入 R-QUERY-005。**
- **PROPOSED-2**：当一条结果有**多个字段**命中时，「命中字段」展示全部命中字段（而非仅第一个）。属呈现建议。

除上述外，本 Feature **不提出任何其他产品规则**。

## Open Questions

### Blocking

**无。**

### Non-blocking

- **NQ-A（字段清单与范围的一致性，建议用户确认）**：`NQ-2.resolved_to` 含 `Cluster.name`，但 `NQ-1` / `AC-D1` 限定结果只含 BareMetal + 五类资源。本 Handoff 依 AC-D1 判定 **Cluster 自身不产生结果行**（推荐 (a)）；备选 (b) 搜索也返回所选 Cluster 自身的行（若是，需相应调整 NQ-1 范围与 AC-D1）。**会改变一条用户可见行为。**
- **NQ-B**：契约形态——新增独立搜索端点 vs 既有 per-resource 列表端点追加 `keyword` 参数（NQ-7，归 Architecture）。
- **NQ-C**：索引 / 性能——10⁵ 规模下 `ILIKE '%kw%'` 无 B-tree 可用，是否引入 `pg_trgm` GIN / tsvector（NQ-6，归 Architecture / Database；可能使 `layers.database` 由 false 变 true）。
- **NQ-D**：应用外壳「当前选定 Cluster」上下文与既有 `resourceView` 上下文的复用方式（归 Architecture）。
- **NQ-E**：搜索结果排序规则（本条不承诺排序）。
- **NQ-F**：分页形态与页大小取值（建议沿用既有信封，见 A-1）。

## Architecture Handoff

1. **契约修订（`DEC-021` 已授权）**：移除 / 限定三处「关键字禁止」立场（`f005:129`、`f009:181`、`f010:172`）并处理 `f002:454` 的「筛选」排除项。不得出现「契约禁止、实现却有」的分裂（AC-06）。
2. **契约形态（NQ-7）**：独立搜索端点 vs 既有列表端点追加 `keyword`。须**复用**既有 canonical 过滤（F002 `?cluster_id=`、F004 `?bare_metal_id=`、F005 `?network_interface_id=`、F007/F008 `carrier_type+carrier_id`、F009/F010 的 Cluster 视角与关联过滤），**不得另写一份**。
3. **索引与性能（NQ-6）**：为「子串包含、不区分大小写、跨多表多列、10⁵ 规模、并发 50」选定索引方案；据此确认 `layers.database` 是否由 false 变 true，并生成必要的 migration。
4. **语义到查询的映射**：如何覆盖 BareMetal + R-QUERY-003 五类（含间接推导），并在 `R(B)` / Cluster 归属推导上**引用而非重写** R-QUERY-003。
5. **「命中字段」的表达**：结果如何携带每条记录的命中字段信息。
6. **Empty / Not Found 映射**：无命中 → Empty；Cluster 不存在 / 已软删 → Not Found；与 `401` 边界不混淆。
7. **分页信封**：确认沿用既有 `{items, total, page, page_size}`（A-1）。
8. **应用外壳入口（NQ-5）**：入口 + 「当前选定 Cluster」上下文在 `App.vue` 的落法；与既有 `resourceView` 的复用边界。**注：F017 已 merge，`App.vue` 的所有权冲突已解除。**
9. **大小写与唯一性的实现隔离**：确保搜索的不区分大小写实现**不触及** §22 唯一性、`by-name` 解析、用户名查找的既有实现（AC-05）。

## Handoff Status

`READY FOR ARCHITECT`

---

## 产品规则声明（新增 / 修改了什么）

- **新增 1 条产品规则**：**R-QUERY-005「Cluster 内关键字搜索」**，写入 `docs/product/requirements.md` §16。编号取 R-QUERY-005（§16 既有 4 条顺延，同属 Resource Query 域，保持 §16 扁平编号，不新建 §16.x 以避免产生新的权威位置）。
- **未修改任何既有产品规则**：R-QUERY-001 ~ 004、§22、§17、§19、§8/§9/§10/§11/§12/§14 等**全部保持不变**。R-QUERY-005 以「引用 R-QUERY-003 / R-QUERY-004 / §22 / R-DELETE-002」的方式成立，**不重述**其内容。
- **须由他人修订的既有立场（非产品规则）**：三份 API 契约与 `f002:454` 的「不存在关键字参数」立场，由 **Architecture / Contract** 按 `DEC-021` 修订。
- 规则总数：**61 → 62**。
