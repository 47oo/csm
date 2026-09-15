# Product Handoff — F001 Cluster 登记与管理

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-15
> Feature: F001（E01，P0，`depends_on: [F012]`）
> Git: `feature/F001-cluster`，base `develop`（`7a99745`）

---

## Feature

Cluster 登记与管理（F001）— CSM V1 基础设施顶层资源的登记、维护与查询。

## Problem

CSM 要替代分散维护的 Excel，前提是**集群这一层事实先可信、可查**（`requirements.md` §1、§2、§5）。当前 Excel 场景里，集群信息散落在多张表、多处命名不一致，且「同一个集群被重复登记」无法阻止；而 Cluster 在 CSM 中是**资源组织与隔离的边界**（§7）：BareMetal、IP 唯一性边界（§12）、Service 的归属推导（R-SVC-006）、查询入口（§16 R-QUERY-001）都挂在它上面。Cluster 名称一旦重复或命名不可寻址，后面所有资源的归属与唯一性都会连带失真。

使用者：HPC / AI 集群运维人员、基础设施管理员（§3）。他们在「新建一个集群」「查有哪些集群」「按集群名字定位」时使用本功能。

因此 F001 的产品价值是：**让 Cluster 的名称成为可信、唯一、可寻址的事实**，并把这一层做成后续 F002 / F009 / F010 / F011 可直接依赖的基础。

## Confirmed Requirements

仅列已确认内容，来源见括号。

1. 集群属于 V1 资源范围；Cluster 是基础设施资源中的**顶层管理对象**，不绑定数据中心（§5、§7、§6）。
2. Cluster 必须拥有能够被运维人员识别的**名称**；名称是 Cluster 的标识，登记字段即为集群名称（R-CLUSTER-001；`domain-model.md` §5.1）。
3. Cluster Name 在**所有当前有效 Cluster 中全局唯一**；名称比较**区分大小写**（R-CLUSTER-002、§22）。
4. Cluster **不设置统一运行状态**，不得为了与 BareMetal 字段统一而增加状态字段（R-CLUSTER-003）。
5. Cluster 名称**不得包含 `/`**，登记写入路径必须校验并拒绝（R-CLUSTER-005）；该规则不因 API 改用 `id` 为规范路径而取消（`adr-0003`「与 R-CLUSTER-005 的关系」，用户 2026-09-15 裁定**保留**）。
6. 关键冲突必须在保存前阻止，**不能只依赖 UI 校验**；全局 Cluster Name 重复属必须阻止项（§21）。
7. 已逻辑删除的 Cluster **默认不出现在正常查询结果中**，且**不参与名称解析**（R-DELETE-002、R-DELETE-006；`api-conventions.md` §2）。
8. 只读名称寻址别名 `GET /api/clusters/by-name/{cluster_name}` 属本 Feature；`{cluster_name}` **大小写敏感**匹配（`adr-0003` §2、`api-conventions.md` §2）。
9. 查询必须区分 **Resource Not Found（404）** 与 **Empty Relationship（200 + 空集合）**（R-QUERY-004；`api-conventions.md` §7）。
10. 资源标识与 API 契约按已批准约定：规范路径使用 `id`，写操作走 `id`；列表 `{items,total,page,page_size}`；错误信封含 `error.code` 与 `details[].field`；`deleted_at` 不对外暴露（`api-conventions.md` §2、§3、§4、§5、§6 —— `READY`）。
11. F012 基线已建立 `clusters` 表及 `ck_clusters_name_no_slash` / `ux_clusters_name_active`；**F001 不新建表**，不修改基线 migration（`docs/database/f012-baseline-migration.md` §2；`docs/database/csm-v1-schema-design.md` §`clusters`）。
12. **R-CLUSTER-005 采用「数据库 + API」双保险分工**（`f012-project-foundation-handoff.md` Q2）：数据库层 `CHECK` 为权威、已在 F012 基线落地且冻结；F001 负责在写入路径先校验，返回 `400 VALIDATION_ERROR` + `details[].field = "name"`，避免用户看到 `500`。
13. F012 的非产品自检面 `/_foundation/*` 的**移除 / 降级责任属 F001**（`docs/api/f012-project-foundation.md` §4「`Removal owner: F001`」）；它不是产品契约，生产不可达。
14. F001 的交付面在 F012 交接中已划定：Cluster 的**领域校验 / CRUD / `by-name` 别名属 F001**，F012 不得预置（`docs/product/handoffs/f012-project-foundation.md`「本次明确不包含 #2」；`docs/architecture/f012-project-foundation-handoff.md` Q2）。

## Confirmed Domain Rules

| 规则 | 内容 | 来源 |
|---|---|---|
| R-CLUSTER-001 | Cluster 必须拥有可被运维人员识别的名称 | `requirements.md` §7；`domain-model.yaml > resources[Cluster].fields[name]`（`required: true`, `is_identifier: true`） |
| R-CLUSTER-002 | 名称在所有当前有效 Cluster 中全局唯一，比较区分大小写 | `requirements.md` §7、§22；`domain-model.yaml > uniqueness_rules` |
| R-CLUSTER-003 | Cluster 不设置统一运行状态 | `requirements.md` §7；`domain-model.yaml > status_models.stateless_resources` |
| R-CLUSTER-004 | Cluster 可以包含多个 BareMetal | `requirements.md` §7；`domain-model.yaml > relationships[BareMetal-to-Cluster]`（N:1, mandatory） |
| R-CLUSTER-005 | 名称不得包含 `/`；写入路径必须校验 | `requirements.md` §7；`domain-model.yaml > fields[name].constraints[must-not-contain-slash]`（`enforcement_feature: F001`） |
| §21 Data Consistency | 全局 Cluster Name 重复等关键冲突必须在保存前阻止，不能只依赖 UI | `requirements.md` §21；`domain-model.yaml > data_consistency` |
| §22 Case Sensitivity | Cluster Name 唯一性比较区分大小写 | `requirements.md` §22 |
| §17 + R-DELETE-002 / R-DELETE-006 | 已逻辑删除默认不出现在正常查询；已删不占正常业务唯一性 | `requirements.md` §17；`domain-model.yaml > lifecycle` |
| §6 / §13 | 不建立 DataCenter 层级；不管理 Rack / U 位 | `requirements.md` §6、§13；`domain-model.yaml > excluded_from_v1` |
| 名称的 `undefined_constraints` | 长度、首尾空白、空字符串、Unicode NFC 规范化**当前未定义，不得自行假设** | `domain-model.yaml > resources[Cluster].fields[name].undefined_constraints`；`requirements.md` R-CLUSTER-005；`domain-model.md` §5.1 |

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。** 明确依赖但不属于 F001 的规则：R-DELETE-001 ~ R-DELETE-006 的删除语义（F014）、R-BM-*（F002）、R-QUERY-001/002/003（F009/F010）、R-NIC-*/R-IP-*（F004/F005）、R-SVC-*（F008）。

## Scope

### 本次包含

1. **Cluster 登记（创建）**：登记一个新 Cluster，名称为其标识（R-CLUSTER-001）。
2. **Cluster 名称的写入校验**（F001 承担的 API 层那一半双保险）：必填、不得含 `/`、活跃范围内全局唯一且区分大小写（R-CLUSTER-002/005、§21、§22）。
3. **Cluster 查询**：列表（分页）、按 `id` 读取详情、`GET /api/clusters/by-name/{cluster_name}` 名称别名（大小写敏感、已删不参与解析）。
4. **Cluster 维护（名称更新）**：按 F012 交接已划定的 `CRUD` 边界（`docs/product/handoffs/f012-project-foundation.md`「明确不包含 #2」；`docs/architecture/f012-project-foundation-handoff.md` Q2），对已有 Cluster 的名称更新，复用与创建**同一套**校验。
5. **读取路径的软删过滤**：列表 / 详情 / by-name 一律排除已逻辑删除的 Cluster（R-DELETE-002、R-DELETE-006），复用 F012 的 `deleted_at IS NULL` 过滤原语（不在 F001 内新建一套）。
6. **前端**：Cluster 列表页（Loading / Empty / Error / Not Found 可区分，R-QUERY-004）与 Cluster 详情页骨架；**详情页内的 BareMetal 列表与状态不属本 Feature**（见下）。
7. **移除 / 降级 `/_foundation/*`**：按 F012 交接的 `Removal owner: F001`，使非产品自检面不再作为产品契约，生产不可达，前端 dev 三态基座改接产品端点。

### 本次明确不包含

（用户/已确认规则明确排除，或已由 CONFIRMED 归属划定）

1. **Cluster 的删除能力与其领域语义**（R-DELETE-001 ~ R-DELETE-006）——已由项目计划归属 **F014**（`project-plan.yaml > F014`），且逐条见下「删除边界」说明。
2. **BareMetal 实体、BareMetal↔Cluster 关系写入、嵌套端点** `GET /api/clusters/by-name/{cluster_name}/bare-metals`——属 F002（BareMetal）与 F009（Cluster 视角查询）。
3. **Cluster 视角资源查询 / 关系视图 / 跨资源拼接**——属 F009 / F010（R-QUERY-001/002/003/004 的视图部分）。
4. **任何状态字段或状态推导**（R-CLUSTER-003）。
5. **DataCenter / 园区 / 机房 / Rack / U 位等位置或上级模型**（§6、§13；`domain-model.yaml > excluded_from_v1`）。
6. **Excel 批量导入**——属 F011。
7. **认证 / 会话 / 权限**——属 F013。F001 不实现登录、不实现权限模型（R-AUTH-003 禁止擅自扩大 RBAC）。
8. **`name` 的长度 / 首尾空白 / 空字符串 / Unicode NFC 规范化约束**——`undefined_constraints`，**F001 不得新增任何此类校验，也不得就此作出行为承诺**（见 NQ-1）。
9. **物理删除、Undelete / Restore、软删级联、父删子拦的实现**（R-DELETE-001/003/004/005；ADR-0004）。
10. **导出、高级筛选、历史审计**——当前无已确认需求；不得因「系统通常都有」而加入（§23、§25）。

### 本次未涉及

当前需求没有要求，但不能推断为永远不需要：

- Cluster 名称变更是否应有历史记录 / 时间线；
- 列表排序规则、关键字搜索、按名称前缀筛选；
- 批量创建、复制 Cluster；
- Cluster 级别的备注 / 负责人 / 标签等附加字段；
- 名称的展示归一化（如统一大小写显示）。

### 问题 B 的正面回答：删除边界

**结论：F001 的产品验收范围不包含「删除 Cluster」这一用户能力；删除的语言与实现归属 F014。**

理由（均为已确认依据，非新规则）：

1. R-DELETE-001 ~ R-DELETE-006 已由 `project-plan.yaml > F014` 完整归属 F014，且 F014 状态为 `READY`、`depends_on: [F012]`。
2. `adr-0004` 要求软删过滤与删除语义由**统一逻辑删除领域服务**提供，**禁止各模块各写一套**；在 F001 内实现删除即产生第二条删除路径。
3. R-DELETE-004 的 Cluster 示例（「还有有效 BareMetal 时不能删除 Cluster」）**在 F001 阶段不可验收**——`bare_metals` 表与 BareMetal 实体属 F002。若把删除塞进 F001，它必然是一个语义不完整、且随后需要重做的删除。
4. F012 已明确 `/_foundation/*` 的 `DELETE` 是「**不是**产品软删除语义」的夹具（`docs/api/f012-project-foundation.md` §4.5），不得被升级为产品能力。

**对 AC 的影响**：

- 删除**不进入** F001 的 Acceptance Criteria（F001 的 AC 不依赖删除能力）；
- 「已删不参与查询 / 名称解析」（R-DELETE-002、R-DELETE-006）仍需在 F001 的读取路径成立，其验证方式见 **AC-07**：由测试在**数据层直接预置**一条 `deleted_at` 非空的行，再断言 API 行为——不依赖任何产品删除端点；
- **若** Architecture 选择在 F001 的 cluster 模块暴露 `DELETE /api/clusters/{id}`，它必须是对 F014 统一软删领域服务的**委托**，其行为**不构成 F001 的产品 AC**，AC 仍归 F014。该端点归属选择属架构决策（见 Architecture Handoff #1）。

### 问题 C 的正面回答：Cluster 无状态

**确认：F001 不得引入任何状态字段、状态枚举、状态默认值或状态推导。**

依据 R-CLUSTER-003 与 `domain-model.yaml > status_models`：Cluster 属 `stateless_resources`；「V1 中只有 BareMetal 拥有状态」。`clusters` 表已无状态列（`docs/database/csm-v1-schema-design.md` §`clusters`「不设计：状态列」），F001 不得为其新增列。对应的可判定验收见 **AC-09**。

### 问题 D 的正面回答：Cluster↔BareMetal 在本 Feature 的边界

**确认：F001 不需要任何跨 Feature 的关系查询或展示；完全留给 F002 / F009 / F010。**

- R-CLUSTER-004（「Cluster 可以包含多个 BareMetal」）是**关系描述**，其可验证的两个方向分别落在：
  - **F002**：每个 BareMetal 必属于一个 Cluster（R-BM-001，N:1 mandatory）；
  - **F009**：从 Cluster 视角查看其下 BareMetal 及其状态（R-QUERY-001/002）。
- 在 F001 阶段，**该规则不产生任何用户可观察行为**：`bare_metals` 表与实体都不存在，`/by-name/{name}/bare-metals` 别名也无数据可返回。
- 因此 F001 **不得**：提前建 `bare_metals` 表、为 Cluster 增加裸金属计数字段、实现嵌套 bare-metals 端点，或为了让该 AC 可验收而做任何跨 Feature 的关系实现。
- 注意：`project-plan.yaml > F001` 的 AC 列表含「Cluster 可包含多个 BareMetal（R-CLUSTER-004）」，但该条**在 F001 内不可判定**。这是计划与 Feature 边界的归属问题，不是产品规则变更（见 NQ-4）。

### 问题 B 的正面回答：`by-name` 只读别名语义

**确认（产品语义，来源 `adr-0003` §2 与 `api-conventions.md` §2/§7）：**

1. `GET /api/clusters/by-name/{cluster_name}` 是**只读别名**；规范路径仍是 `/api/clusters/{cluster_id}`，写操作一律走 `id`。
2. `{cluster_name}` 按**大小写敏感**匹配（与 R-CLUSTER-002 / §22 一致）。
3. **已逻辑删除的 Cluster 不参与名称解析**：命中不到 → `404 NOT_FOUND`（与 R-DELETE-006、`api-conventions.md` §7 一致）。
4. 名称中含 `/` 的 Cluster 不存在（R-CLUSTER-005），因此别名路径不会因名称而分段错乱——这正是保留 R-CLUSTER-005 的现存技术理由（`adr-0003`）。
5. `GET /api/clusters/by-name/{cluster_name}/bare-metals` **不属 F001**（属 F002 / F009）。

### 已确认冲突 / 边界重叠（需记录，不静默选择）

- `docs/architecture/f012-project-foundation-handoff.md` 与 `docs/product/handoffs/f012-project-foundation.md` 中「F001 交付 Cluster 的领域校验 / **CRUD** / `by-name`」的表述与「F014 拥有 R-DELETE-*」存在**表述重叠**。**本 Handoff 的立场（依 `AGENTS.md` §3 优先级，产品文档与 CONFIRMED 规则优先）**：删除的领域语义唯一归属 F014；F001 不实现第二条软删路径。端点归属由 Architect 裁定（Architecture Handoff #1）。
- `project-plan.yaml > F001` 把 R-CLUSTER-004 列为 F001 AC，与 F001 无 BareMetal 的事实冲突 → 以 NQ-4 记录并交 Project Manager / Architect 处理，**不改产品规则**。

## Acceptance Criteria

每条均为可判定（是 / 否），描述**用户可观察到的行为**。测试状态可由数据层直接预置，不依赖尚未存在的产品删除端点（写法沿用 F012 的「绕过应用层断言」取向）。

- **AC-01（登记成功）**：`POST /api/clusters` 携带合法名称 → `201`，响应含 `id`、`name`、`created_at`、`updated_at`；响应**不含** `deleted_at`，**不含**任何状态字段。
- **AC-02（名称必填）**：不提供 `name` 或 `name` 非字符串 → `400 VALIDATION_ERROR`，`details[].field == "name"`，且**不产生任何新记录**（R-CLUSTER-001、§21）。
- **AC-03（`/` 在 API 层被拒，且不是 500）**：名称含 `/` 的登记请求 → `400 VALIDATION_ERROR`，`details[].field == "name"`，无记录写入；不得返回 `500`（R-CLUSTER-005 的 F001 侧；数据库 `ck_clusters_name_no_slash` 为第二道保险）。
- **AC-04（活跃名称全局唯一）**：已存在活跃 Cluster `cluster-a` 时，再登记 `cluster-a` → `409 CONFLICT`，`details[].field` 至少含 `"name"`，且不产生第二条活跃记录（R-CLUSTER-002、§21）。
- **AC-05（大小写敏感）**：`cluster-a` 与 `Cluster-A` 可作为**两个不同** Cluster 同时存在；按 `Cluster-A` 查询只命中该条，不会命中 `cluster-a`（R-CLUSTER-002、§22）。
- **AC-06（by-name 别名）**：`GET /api/clusters/by-name/{cluster_name}` 命中时返回 `200` 且指向与 `GET /api/clusters/{id}` **同一资源**；名称不存在时返回 `404 NOT_FOUND`（`adr-0003`、`api-conventions.md` §2/§7）。
- **AC-07（已删不参与查询与解析）**：测试在数据层直接置入一条 `deleted_at` 非空的 Cluster 后——该行**不出现**在 `GET /api/clusters` 的 `items` 中；其名称经 `by-name` 解析返回 `404 NOT_FOUND`；按 `id` 读取返回 `404 NOT_FOUND`（R-DELETE-002、R-DELETE-006；`api-conventions.md` §2/§7）。
- **AC-08（列表、分页与 Empty 语义）**：`GET /api/clusters` 返回 `200` + `{items,total,page,page_size}`；当系统内**不存在活跃 Cluster** 时返回 `200` 且 `items == []`（Empty），**不得**返回 `404`——Empty 与 Not Found 是两种不同响应（R-QUERY-004、`api-conventions.md` §3/§7）。
- **AC-09（无状态）**：Cluster 的任何请求体与响应体都不含状态字段；`clusters` 表不存在状态列（R-CLUSTER-003）。
- **AC-10（无上级 / 无位置）**：Cluster 的登记、查询与响应中不存在 DataCenter / 园区 / 机房 / 机柜 / U 位等上级或位置字段（§6、§13）。
- **AC-11（中文名称往返正确）**：含中文的 Cluster 名称（如 `高性能计算集群-A`）可登记，可在列表中按字面值正确读出，并可通过 `by-name` 精确命中（§21；F012 AC-07 的延续，UTF-8）。
- **AC-12（更新名称复用同一套规则）**：`PATCH /api/clusters/{id}` 修改名称 → `200` 并返回新值；改后旧名称不再被占用（可作为其他 Cluster 的名称登记成功）；违反 `/` 规则或活跃唯一性时分别按 AC-03 / AC-04 返回 `400` / `409`；对不存在或已逻辑删除的 `id` → `404 NOT_FOUND`。
- **AC-13（不存在第二条删除路径 / 自检面已清理）**：F001 交付后，非产品自检面 `/_foundation/*` **不再作为产品契约存在**——生产配置下不可达（`404`），且不存在未经 F014 统一软删领域服务的、写入 `deleted_at` 的产品路径（F012 交接 `Removal owner: F001`；ADR-0004）。
- **AC-14（前端三态与 Not Found 可区分）**：Cluster 列表页在 Loading / Empty / Error 三种情形下渲染**互不相同**的状态；Empty（无活跃 Cluster）与 Not Found（资源不存在或已删）在界面上可被用户区分（R-QUERY-004；`api-conventions.md` §7）。

**明确不进入 F001 AC 的内容**（归属见括号）：删除 Cluster 及其全部语义（F014）；Cluster → BareMetal 列表与状态（F009）；`by-name/{name}/bare-metals`（F002/F009）；跨资源关联视图（F010）；Excel 导入校验复用（F011）；认证后访问控制（F013）。

## Assumptions

（不阻塞当前工作、可安全暂时采用；**不得当作 CONFIRMED**）

1. **F001 使用 F012 已交付基座**（统一错误信封、SQLSTATE→HTTP 映射、分页、事务边界、`deleted_at IS NULL` 过滤原语），不在 Cluster 模块另立一套约定（`api-conventions.md` §9 与架构 Constraints #9）。
2. **F001 不修改 `0001_f012_baseline`**。Cluster 既有列足够表达 R-CLUSTER-001/002/005；本 Feature 无任何产品依据需要新增列。
3. **名称更新属于 F001 范围**，依据是 F012 交接已划定的「F001 = 领域校验 / CRUD / `by-name`」边界（见 Confirmed Requirements #14）。若用户确认「Cluster 名称不可变更」，那是范围缩减（删去 AC-12），**不是**对已确认规则的修改。
4. **系统当前不存在任何 Cluster 数据**（F012 仅以 `clusters` 作验证载体，且该表在 F012 内即为空库基线），因此 F001 不涉及数据迁移或历史数据清洗。
5. **F013 尚未落地**，`/api/*` 在 F001 期间可未认证访问；这是显式、临时状态，不表示产品不需要认证（`docs/api/f012-project-foundation.md` §6）。
6. 「`/_foundation/*` 移除 / 降级」的具体形式（彻底删除 vs 降级为测试夹具）属架构决策，不改变任何产品行为。

## Proposed Rules

**PROPOSED-1（需用户裁定，非 CONFIRMED）**：建议后续将 Cluster 名称的「不得为空字符串」「首尾空白不得保留（trim）」「长度上限」确认为产品规则。当前这些属 `undefined_constraints`，F001 **不得**实现。若确认，属**新增产品规则**，需走需求确认流程，并随之决定是否新增数据库 CHECK（增量 revision）。

**PROPOSED-2（需用户裁定，非 CONFIRMED）**：建议明确「Cluster 名称是否允许被修改」。若不希望标识变更，应显式确认为产品规则（F001 相应缩减 AC-12），而不是由实现默认允许。

其余无产品建议。本 Feature 不新增任何产品规则，也不修改任何已有规则。

## Open Questions

### Blocking

**无。**

**关于问题 A（`name` 的未定义约束）为何不构成 Blocking —— 逐条对照判定标准：**

- **是否无法确定本次功能范围？** 否。F001 的范围（登记 / 维护 / 查询 / by-name）与边界（删除归 F014、关系归 F002/F009）完全由 CONFIRMED 规则与已批准交接确定。
- **是否导致两种明显不同的用户行为？** 在**抽象层面**是（空字符串被接受 vs 被拒绝）。但 `domain-model.yaml` 明确把「长度、首尾空白、空字符串、其他非法字符」列为 `undefined_constraints`，并附有 **standing instruction：「当前未定义，不得自行假设」**（`requirements.md` R-CLUSTER-005 同义）。数据库设计据此**故意不加 CHECK**（`docs/database/csm-v1-schema-design.md` §`clusters`「不添加：`name <> ''`、长度上限、`trim(name) = name`」）。因此**允许的行为只有一种**：不新增约束。这不是「PM 替用户做决定」，而是权威文档已经规定的「不做决定」；确定这一点的依据本身就是 CONFIRMED。
- **是否改变核心领域关系？** 否。这些约束不改变任何关系、基数或唯一性边界。
- **是否导致验收标准无法定义？** 否。AC-01 ~ AC-14 全部可判定，且**没有任何一条依赖**这些未定义约束。

**据此的明确行为边界（对 Architect / Backend 是硬约束）**：

- F001 **不得**为 `name` 增加长度、`trim`、非空串、NFC 规范化等任何校验，也**不得**在数据库层新增此类约束（基线已冻结）。
- F001 **不得**在 API 契约、前端文案或 AC 中**承诺**这些取值的行为。
- **后果声明（不是规则）**：在现有已确认规则下，空字符串 / 含首尾空白的名称**不会**被 F001 拒绝。这是「未定义且不得假设」的直接后果，必须记入 NQ-1，**不得**被解读为 CSM 已确认「空名称合法」。
- 若用户希望拒绝空串 / 空白 / 超长，属**新增产品规则**（见 PROPOSED-1），并会带来数据库 CHECK 的增量 revision；这是可逆的**收紧**，不影响 F001 当前 AC 的成立。

**结论：不输出 `FEATURE BLOCKED AT PRODUCT`。** 若后续用户明确要求把空串 / 空白 / 长度纳入 F001，则应作为产品变更重新进入 Product 阶段。

### Non-blocking

- **NQ-1（Problem A：`name` 的未定义约束）**：长度、首尾空白、空字符串、Unicode NFC 规范化当前未定义（`domain-model.yaml > undefined_constraints`；数据库 Open Question #5）。F001 不实现、不承诺（见上「行为边界」）。建议在 F001 投入使用真实数据**之前**由用户确认是否拒绝空串 / 空白 / 超长，以避免产生难以识别的「空名集群」事实数据。
- **NQ-2（Cluster 删除端点的归属与接线）**：F001 委托 F014 服务暴露 `DELETE /api/clusters/{id}`，还是整体推迟由 F014 暴露？两者产品行为一致（删除语义唯一来自 F014），但影响 F001 的模块边界与前端是否显示删除入口。建议在 F014 落地前，前端**不**提供删除入口。
- **NQ-3（`by-name/{name}/bare-metals` 别名归属）**：`adr-0003` §2 列出该别名，但它需要 BareMetal（F002）与 Cluster 视角查询（F009）。本 Handoff 判定其**不属 F001**；需 Architect 确认由 F002 还是 F009 交付。
- **NQ-4（R-CLUSTER-004 的 AC 归属）**：`project-plan.yaml > F001` 的 AC 含「Cluster 可包含多个 BareMetal」，但 F001 内无 BareMetal，不可判定。建议把该条 AC 移入 F002（N:1 mandatory 的方向）与 F009（Cluster 视角列表）。属计划归属修正，不改产品规则。
- **NQ-5（名称是否可变）**：见 PROPOSED-2。当前按假设 3 纳入 F001；若确认不可变，F001 缩减 AC-12。
- **NQ-6（F013 落地前的访问控制）**：F001 期间 `/api/clusters*` 未认证可访问，属临时状态（`docs/api/f012-project-foundation.md` §6）。是否需要在此期间限制部署网络可达性，属 F015 部署范畴。
- **NQ-7（前端 Cluster 详情页范围）**：F001 交付详情页骨架，其中 BareMetal 列表与状态属 F009。建议 F001 详情页只呈现 Cluster 自身字段，避免为「可看」而提前实现 F002/F009 的能力。
- **NQ-8（`page_size` 上限）**：F012 的 PROPOSED 默认值为 50 / 上限 200。F001 沿用该默认，不作为产品规则固化。

## Architecture Handoff

以下为 Architect 需要解决的技术设计问题（本 Handoff 不选择框架、不设计表、不定义 API 细节）：

1. **F001 ↔ F014 的删除边界与端点归属**：确认 F001 不实现软删领域语义；裁定 `DELETE /api/clusters/{id}` 是由 F001 的 cluster 模块委托 F014 的服务，还是整体推迟到 F014；并明确 F001 的读取路径如何获得软删过滤（复用 F012 原语 vs 等待 F014 的统一领域服务），保证**只有一条删除路径**（ADR-0004）。回应 NQ-2。
2. **R-CLUSTER-005 双保险分工的技术落实**：确认 API 层校验在数据库 CHECK 之前触发，使含 `/` 的写入稳定返回 `400 VALIDATION_ERROR` + `details[].field = "name"`，而数据库 `ck_clusters_name_no_slash` 仅作后盾（`23514` → 400，不得成为 500）。**F001 不得修改基线 migration，也不得再新增同类数据库约束。**
3. **`clusters` 资源表示与契约落点**：对外字段仅 `id` / `name` / `created_at` / `updated_at`（`deleted_at` 不暴露；无状态字段；无上级 / 位置字段），并明确这些字段落在 `docs/api/` 的哪份契约（新建 F001 契约文件还是扩展约定）。回应 AC-01、AC-09、AC-10。
4. **`by-name` 别名的路由与解析**：大小写敏感匹配、已删不参与解析、与 `id` 路径的关系（canonical vs alias），以及路径参数在含中文 / 特殊字符时的编码处理；并确认 `by-name/{name}/bare-metals` 不在 F001 交付。
5. **`/_foundation/*` 的移除 / 降级方案**：决定彻底删除还是降级为测试夹具；确认生产不可达、前端 dev 三态基座改接产品端点、且移除后**不留下任何未受 F014 约束的 `deleted_at` 写入路径**。回应 AC-13。
6. **名称更新路径的并发与冲突语义**：`PATCH` 名称时的唯一性判定与 `23505` → `409 CONFLICT` 映射；并明确 F001 不承担 F014 的并发父子完整性职责。
7. **AC 归属的架构对齐**：确认 R-CLUSTER-004、R-QUERY-001/002 分别由 F002 / F009 验收，F001 不为其预留表、列或端点（回应 NQ-3、NQ-4、问题 D）。
8. **未定义约束的「不实现」保障**：确认骨架 / 校验层不会隐式引入长度、trim、非空串或 NFC 校验（含 Pydantic schema 与前端输入组件层面），使「未定义即不做」成为可审查的事实，而非口头约定（回应 NQ-1）。
9. **认证边界**：确认 F001 不实现认证，`/api/clusters*` 在 F013 落地前保持临时无认证状态，并为 F013 预留标准的 `/api/*` 保护位（回应 NQ-6）。

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。Problem A 经判定为 Non-blocking（依据 `undefined_constraints` 的「不得自行假设」指令，且 F001 全部 AC 均可判定）；Problem B / C / D 已在本 Handoff 中给出明确的产品边界裁定。