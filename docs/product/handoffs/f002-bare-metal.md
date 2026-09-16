# Product Handoff — F002 BareMetal 登记与管理

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-16
> Feature: F002（E01，P0，`depends_on: [F001]`）
> Git: `feature/F002-bare-metal`，base `develop` = `c8e5d910b057f96cc4864959ac802d15b75abc67`

---

## Feature

BareMetal 登记与管理（F002）— CSM V1 唯一有状态资源：物理服务器 / 计算节点的登记、查询、状态人工维护与逻辑删除，并承接 R-CLUSTER-004 的 N:1 方向与 F014 的「父删子拦」真实业务验收。

## Problem

CSM 要替代分散维护的 Excel（`requirements.md` §1、§2）。F001 已让 Cluster 名称成为可信、唯一、可寻址的事实；但集群本身只是组织边界，**运维人员真正每天要维护和查询的是机器**：哪台机器在哪个集群、叫什么、现在能不能用（`domain-model.md` §4.2：状态仅 BareMetal 拥有）。

当前 Excel 场景的痛点：
- 同一台机器被重复登记 / 换集群后留下两份；
- 机器状态散落在不同表，无法一眼回答「这个集群现在有多少台机器可用」；
- 删机器时直接把行删掉，历史丢失，或反过来把还有机器的集群误删，产生「无主机器」。

使用者：HPC / AI 集群运维人员、基础设施管理员（§3）。场景：新机器上架登记、日常状态维护（IDLE/ALLOC/DOWN）、按集群盘机器、机器退役下线。

F002 的产品价值：**让「一台机器属于哪个集群、叫什么、当前什么状态」成为可信、唯一、可维护的事实**，并为 F004/F006/F007/F008/F009 提供可复用的节点基础。

## Confirmed Requirements

仅列已确认内容，来源见括号。

1. 每个 BareMetal **必须属于恰好一个 Cluster**；V1 不支持脱离 Cluster 存在的 BareMetal（R-BM-001；`domain-model.yaml > relationships[BareMetal-to-Cluster]` N:1 mandatory CONFIRMED）。
2. BareMetal **必须拥有 `hostname`**，是其在列表中区分机器的身份标识（R-BM-002；`domain-model.yaml > resources[BareMetal].fields[hostname]` `required:true, is_identifier:true`）。
3. 同一 Cluster 内 `hostname` **唯一**；**不同 Cluster 可存在相同 hostname**；比较**区分大小写**（R-BM-002、§22；`domain-model.yaml > uniqueness_rules[R-BM-002]` `scope: per_cluster, case_sensitive: true, cross_scope_allowed`）。
4. 关键冲突必须在保存前阻止，**不能只依赖 UI 校验**；「同 Cluster hostname 重复」与「非法资源关系」「非法状态值」均属必须阻止项（§21）。
5. 状态取值集合为 **`IDLE` / `ALLOC` / `DOWN` / `UNKNOWN`**（R-BM-003）；**新建默认 `IDLE`**（R-BM-004）。
6. 状态**不得为空**；历史无法确定状态时必须使用 `UNKNOWN`，**不得用 `NULL` 代替**（R-BM-005）。
7. 状态**允许运维人员人工维护**（R-BM-006）；不得因存在状态字段而自动接入 Slurm / Prometheus / 虚拟化平台等实时状态源。
8. 可选硬件规格字段：**Vendor、Model、Serial Number、CPU、Memory、GPU、Storage**；全部**可选**、**纯文本**、未登记时允许为空（`NULL`），**不构成登记阻断条件**；**Serial Number 不参与唯一性**；不得因此引入自动资产发现或外部平台同步（R-BM-007，用户 2026-09-16 裁定，关闭 OPEN-004）。
9. BareMetal 的**直接上级只有 Cluster**；V1 不记录 Rack / U Position（§13）。
10. 资源采用逻辑删除，不物理删除；已逻辑删除默认不出现在常规查询；已逻辑删除**不继续占用业务唯一性**，可重建同名（§17、R-DELETE-001/002/006）。
11. **父资源存在活跃子资源时不得删除父资源**；逻辑删除**不自动级联**（R-DELETE-004/005）。
12. API 契约按已批准约定：规范路径用 `id`，写操作走 `id`；列表 `{items,total,page,page_size}`；可选字段空值返回 `null` 不省略；错误信封含 `error.code` 与 `details[].field`/`details[].code`；`deleted_at` 不对外暴露；**Resource Not Found（404）与 Empty（200 + 空集合）必须可区分**（`adr-0003`、`api-conventions.md` §2/§3/§4/§5/§6/§7 —— `READY`）。
13. **F014 交接义务（已有计划归属）**：F002 必须向 `CLUSTER_ACTIVE_CHILD_CHECKS` 注入「Cluster 下是否存在活跃 BareMetal」检查，并交付真实端到端：「Cluster 存在活跃 BareMetal → `DELETE /api/clusters/{id}` → `409 CONFLICT`（`details[].code = "ACTIVE_CHILDREN_EXIST"`）；软删该 BareMetal 后删除成功」；并发「创建 BareMetal vs 删除 Cluster」结束后**孤立记录不变式 = 0 行**；创建 BareMetal 必须对父 Cluster 行取 `FOR SHARE` 并确认活跃（`f014-soft-delete-handoff.md` 问题 3/7；`project-plan.yaml > F002.acceptance_criteria`）。
14. 节点资源在删除前必须对活跃子资源做检查（NIC / VM / Container / Service），机制由 F014 提供、检查点由资源模块声明（ADR-0004 §5；`f014-soft-delete-handoff.md` 问题 2/7）。
15. 认证：所有 `/api/*` 端点由 F013 中间件自动覆盖，无白名单（ADR-0005）。

## Confirmed Domain Rules

| 规则 | 内容 | 来源 |
|---|---|---|
| R-BM-001 | 每个 BareMetal 必属一个 Cluster（N:1 mandatory，不得存无主机器） | `requirements.md` §8；`domain-model.md` §5.2/§6；`domain-model.yaml > resources[BareMetal].binding_to_parent`、`relationships[BareMetal-to-Cluster]` |
| R-BM-002 | 同 Cluster 内 `hostname` 唯一，跨 Cluster 可重，比较区分大小写 | `requirements.md` §8、§22；`domain-model.yaml > uniqueness_rules[R-BM-002]` |
| R-BM-003 | 状态取值 `IDLE / ALLOC / DOWN / UNKNOWN`，**封闭集合**（不得自行新增 / 合并 / 重命名） | `requirements.md` §8；`domain-model.yaml > status_models.stateful_resources` |
| R-BM-004 | 新建默认状态 `IDLE` | 同上（`default: IDLE`） |
| R-BM-005 | 状态非空；历史未知用 `UNKNOWN`，不用 `NULL` | 同上（`nullable: false, null_substitute: UNKNOWN`） |
| R-BM-006 | 状态由人工维护，不接实时状态源 | 同上（`maintained_by: manual`） |
| R-BM-007 | 七个硬件字段可选、纯文本、允许 NULL；Serial Number 不参与唯一性；不引入自动发现 | `requirements.md` §8；`domain-model.md` §5.2（OPEN-004 已关闭） |
| R-CLUSTER-004 | Cluster 可包含多个 BareMetal；**F002 负责 N:1 方向**（F009 负责 Cluster 视角读取） | `requirements.md` §7；`project-plan.yaml > requirement_coverage[R-CLUSTER-004]` |
| §21 Data Consistency | 同 Cluster hostname 重复、非法资源关系、非法状态值必须在保存前阻止 | `requirements.md` §21；`domain-model.yaml > data_consistency` |
| §22 Case Sensitivity | BareMetal hostname 唯一性比较区分大小写 | `requirements.md` §22 |
| §17 / R-DELETE-002/004/006 | 软删不出现在常规查询；父有活跃子不得删；已删释放唯一性 | `requirements.md` §17；`domain-model.yaml > lifecycle` |
| §13 / R-BM「不记录 Rack」 | 不记录 Rack / U Position；无 DataCenter 上级 | `requirements.md` §6、§13；`domain-model.yaml > excluded_from_v1` |
| §23 / must_not_assume | 不假设所有机器都有 GPU / 同配置；不引入自动资产发现 | `requirements.md` §23；`domain-model.yaml > must_not_assume` |
| ADR-0003 / api-conventions | `id` 为规范路径；写走 `id`；List/分页/字段类型/错误信封/状态码/Empty-vs-NotFound | `adr-0003`（ACCEPTED）、`api-conventions.md`（READY） |
| ADR-0004 / F014 | `deleted_at` 单一删除标记；唯一写入路径为统一软删服务；父删子拦同事务加锁；不级联；无 undelete | `adr-0004`；`f014-soft-delete-handoff.md` |

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。** 明确依赖但不属于 F002 的：Cluster 自身 CRUD（F001）、Cluster 视角资源查询视图（F009）、NIC/IP/VM/Container/Service 实体（F004/F005/F006/F007/F008）、Excel 导入（F011）、认证（F013）、软删机制本身（F014）。

### 已确认冲突 / 文档漂移（必须记录，不得静默选择）

按 `AGENTS.md` §3 优先级（`requirements.md` / `domain-model.md` > 数据库设计文档 > 代码）：

1. `docs/database/csm-v1-schema-design.md` §`bare_metals`「**不设计**：CPU / Memory / GPU / Storage / Vendor / Model / Serial Number（OPEN-004 未确认，不得自行发明）」与 `requirements.md` R-BM-007、`domain-model.md` §5.2（用户 2026-09-16 已裁定并关闭 OPEN-004）**冲突**。以 CONFIRMED 的 R-BM-007 为准：F002 **需要**在 `bare_metals` 上新增这七个硬件列。该数据库设计文档行已陈旧，需由 Architecture / Database 同步（不属本 Handoff 的修改范围，但必须显式记录）。
2. `docs/product/domain-model.yaml > open_questions > OPEN-004` 仍为 `status: OPEN`，与同文件 `resources[BareMetal].fields`（已含七个硬件字段、`rule_ids: [R-BM-007]`）及 `domain-model.md` §10（OPEN-004 已关闭）**自相矛盾**。以 `requirements.md` + `domain-model.md` 为准；YAML 条目待同步。
3. `project-plan.yaml > F002.requirements` 未列出 `§21`、`R-DELETE-004`、`R-DELETE-006`（其 AC 与 `requirement_coverage` 已覆盖），属计划元数据同步项，非产品规则冲突。

## Scope

### 本次包含

1. **BareMetal 登记（创建）**：在指定 Cluster 下登记一台机器；`cluster_id` + `hostname` 必填，状态默认 `IDLE`，R-BM-007 字段可选（`POST /api/bare-metals`）。
2. **BareMetal 查询**：
   - 列表（分页）`GET /api/bare-metals`，**支持按 Cluster 限定范围**（供 F009 复用；具体路径形态见 Architecture Handoff）；
   - 详情 `GET /api/bare-metals/{id}`；
   - 空集 / 不存在语义按 R-QUERY-004 区分。
3. **状态人工维护**：`PATCH /api/bare-metals/{id}` 修改状态（R-BM-006）；状态值校验为四值封闭集合（§21、R-BM-003）；状态永不为空（R-BM-005）。
4. **R-BM-007 硬件字段的登记与维护**：创建时可选、更新时可修正；纯文本、允许 `NULL`、不参与唯一性、不阻断登记。
5. **BareMetal 逻辑删除**：`DELETE /api/bare-metals/{id}`（委托 F014 统一软删服务），并声明自身的活跃子资源检查点。
6. **R-BM-001 的关系写入**：创建时必须校验父 Cluster 存在且活跃（对父行取 `FOR SHARE` 并在同一事务内确认），不产生无主机器。
7. **R-CLUSTER-004 的 F002 侧**：同一 Cluster 下可登记并读回多台 BareMetal。
8. **F014 交接的端到端义务**：把「Cluster 下是否存在活跃 BareMetal」注入 `CLUSTER_ACTIVE_CHILD_CHECKS`；交付 `409` 端到端、软删后可删、并发孤立记录不变式（见 AC）。
9. **前端**：BareMetal 列表页（Loading / Empty / Error / Not Found 可区分）、详情页、登记表单、状态修改入口、删除入口（二次确认，失败按 `error.code` 渲染）。
10. **读取路径的软删过滤**：列表 / 详情一律排除已逻辑删除的 BareMetal，复用既有活跃过滤原语，不新写谓词。

### 本次明确不包含

（用户明确排除或 CONFIRMED 规则排除）

1. Rack / U 位、DataCenter / 园区 / 机房等上级或位置模型（§6、§13）。
2. 自动资产发现、硬件自动采集、外部平台（Slurm / Prometheus / Docker / K8s / VMware / PVE / OpenStack）同步（R-BM-006、R-BM-007、§23）。
3. 实时状态源接入与状态自动推导（R-BM-006）。
4. 硬件字段的结构化拆分（CPU 型号/核数、GPU 型号/数量、Memory/Storage 单位等一律不拆；R-BM-007）。
5. 物理删除、Undelete / Restore、软删级联（R-DELETE-001/003/005；ADR-0004）。
6. NIC / IP / VM / Container / Service 的实体、端点与页面（F004/F005/F006/F007/F008）。
7. Cluster 视角资源查询页面与 `by-name/{name}/bare-metals` 只读别名（F009；`f001-cluster-handoff.md` PROPOSED #5）。
8. Cluster 自身的 CRUD 与删除语义（F001 / F014）。
9. Excel 批量导入（F011）。
10. 认证 / 会话 / 权限（F013）。
11. BareMetal 的**全局 `by-name` 只读别名**：`hostname` 仅按 Cluster 唯一（R-BM-002），全局别名不可判定；ADR-0003 §2 未授予该别名（见 Proposed Rules P-1）。

### 本次未涉及

当前需求没有要求，但不能推断为永远不需要：

- **登记后修改 `hostname` / `cluster_id`（跨 Cluster 迁移）**——UNCONFIRMED，见 Open Questions NQ-1；
- 列表排序规则、关键字 / 状态 / 硬件字段筛选（如按 GPU 型号、状态筛选）、高级筛选；
- 导出（CSV / Excel）；
- 状态变更历史 / 审计 / 时间线；
- 批量登记 / 批量改状态 / 批量删除；
- 机器负责人、标签、备注、业务用途等附加字段；
- 已删资源查看出口 / 回收站；
- 硬件字段的统计 / 报表（GPU 总数、型号分布等）。

## Acceptance Criteria

每条均可判定，描述用户可观察到的行为。与 `project-plan.yaml > F002.acceptance_criteria` 对齐且**不削弱**，并细化为可测形式。测试可用数据层直接预置（不依赖其它 Feature）。

**登记**

- **AC-01（登记成功）**：`POST /api/bare-metals` 携带 `cluster_id`（存在且活跃的 Cluster）与唯一 `hostname` → `201`，响应字段集合**恰为** `{id, cluster_id, hostname, status, vendor, model, serial_number, cpu, memory, gpu, storage, created_at, updated_at}`；**不含** `deleted_at`、**不含** Rack / U 位 / DataCenter 字段（R-BM-001/007；§13；`api-conventions.md` §4）。
- **AC-02（hostname 必填）**：缺失或非字符串 `hostname` → `400 VALIDATION_ERROR` + `details[].field == "hostname"`，**不产生记录**（R-BM-002；§21）。
- **AC-03（cluster_id 必填且必须有效）**：缺失或非整数 `cluster_id` → `400 VALIDATION_ERROR` + `details[].field == "cluster_id"`；引用**不存在或已逻辑删除**的 Cluster → 写入被阻止、**不产生记录**、**不得返回 5xx**（R-BM-001；§21；响应码归属见 NQ-2）。
- **AC-04（同 Cluster hostname 唯一，保存前阻止）**：同一 Cluster 内已存在活跃 `n1` 时再登记 `n1` → `409 CONFLICT` + `details[].field` 含 `"hostname"`，不产生第二条活跃记录（R-BM-002；§21）。
- **AC-05（跨 Cluster 可重名）**：Cluster A 与 Cluster B 下各自登记 `n1` → 均 `201`，两条不同记录（R-BM-002 `cross_scope_allowed`）。
- **AC-06（大小写敏感）**：同一 Cluster 下 `n1` 与 `N1` 可作为**两条**记录共存；按名称精确等值区分的查询 / 校验不得把二者混同（R-BM-002；§22）。
- **AC-07（默认状态）**：登记请求未提供状态时，响应与数据库中 `status == "IDLE"`（R-BM-004）。
- **AC-08（登记不因硬件字段缺失而阻断）**：不提供任何 R-BM-007 字段 → `201`，各字段在响应中为 `null`（**返回 `null` 而非省略**）（R-BM-007；`api-conventions.md` §4）。
- **AC-09（中文 hostname 往返）**：含中文的 `hostname` 可登记、可在列表 / 详情按字面值正确读出（§21；沿用 F012/F001 的 UTF-8 往返取向）。

**状态**

- **AC-10（状态封闭集合）**：`status` 取 `IDLE / ALLOC / DOWN / UNKNOWN` 之一时为合法；取其它值（如 `RUNNING`、`idle`、空串、`null`）→ `400 VALIDATION_ERROR` + `details[].field == "status"`，且不写入（R-BM-003/005；§21）。
- **AC-11（状态非空，不得以 NULL 代替 UNKNOWN）**：数据库中 `status` 恒为 `NOT NULL`；`UNKNOWN` 是合法且可被显式写入的值；不存在任何把 `status` 写成 `NULL` 的路径（R-BM-005）。
- **AC-12（人工维护状态）**：`PATCH /api/bare-metals/{id}` 携带合法 `status` → `200` 且返回新值；再次读取（列表 / 详情）得到同一值（R-BM-006）。

**查询**

- **AC-13（列表、分页、Empty）**：`GET /api/bare-metals` 返回 `200` + `{items,total,page,page_size}`；系统内无活跃 BareMetal 时返回 `200` 且 `items == []`，**不得**返回 `404`（R-QUERY-004；`api-conventions.md` §3/§7）。
- **AC-14（详情 Not Found）**：`GET /api/bare-metals/{id}` 对不存在或已逻辑删除的 `id` → `404 NOT_FOUND`（不区分两者）（R-DELETE-002；`api-conventions.md` §6/§7）。
- **AC-15（按 Cluster 限定读取，Empty 与 Not Found 可区分）**：按 Cluster 读取其 BareMetal 时——Cluster **不存在或已逻辑删除** → `404 NOT_FOUND`；Cluster **存在但无活跃 BareMetal** → `200` + `items == []`；只返回该 Cluster 的活跃 BareMetal（R-QUERY-004；`domain-model.yaml > lifecycle.parent_deletion`；路由形态见 Architecture Handoff）。
- **AC-16（R-CLUSTER-004 的 N:1 方向）**：同一 Cluster 下连续登记 2 台 BareMetal → 均 `201`；按该 Cluster 读取可见 2 条，且两行 `cluster_id` 相同、`id` 不同（R-CLUSTER-004；R-BM-001）。
- **AC-17（列表 / 详情排除已删）**：测试在数据层**绕过应用层**预置一条 `deleted_at` 非空的 BareMetal 后——该行不出现在列表 `items` 与 `total` 中；按 `id` 读取 → `404`（R-DELETE-002）。

**删除与生命周期**

- **AC-18（BareMetal 逻辑删除）**：`DELETE /api/bare-metals/{id}`（活跃行）→ `204` 且无响应体；该行**仍物理存在**且 `deleted_at` 非空；不出现在列表 / 详情（R-DELETE-001/002；ADR-0004）。
- **AC-19（已删释放唯一性）**：软删 Cluster 内的 `n1` 后，可在**同一 Cluster** 重新登记 `n1` → `201`；旧已删行保留且 `deleted_at` 未被改写（R-DELETE-006）。
- **AC-20（删除不级联）**：删除 BareMetal 后，其所属 Cluster 的 `deleted_at` / `name` / `updated_at` 不变；无任何其它资源行被修改或物理删除（R-DELETE-005）。
- **AC-21（不提供恢复 / 批量能力）**：不存在 restore / undelete / purge / 批量删除 / `include_deleted` 查询参数（R-DELETE-003；负向路由 / 参数断言）。
- **AC-22（BareMetal 活跃子检查点显式声明）**：BareMetal 的删除路径消费一个**显式声明的**活跃子资源检查元组（当前为空——NIC / VM / Container / Service 表尚不存在）；不得由统一软删服务「假定 BareMetal 无子资源」（ADR-0004 §5；`f014-soft-delete-handoff.md` 问题 2/7）。

**F014 父删子拦真实业务端到端（R-DELETE-004，F002 义务）**

- **AC-23（Cluster 有活跃 BareMetal → 拒绝删除）**：Cluster 下存在活跃 BareMetal 时，`DELETE /api/clusters/{id}` → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`；该 Cluster 行 `deleted_at` **仍为 NULL**（无部分写入）（R-DELETE-004；`f014-soft-delete-handoff.md` 问题 7）。
- **AC-24（软删 BareMetal 后 Cluster 可删）**：先软删该 Cluster 下全部 BareMetal，再 `DELETE /api/clusters/{id}` → 成功（`204`）（同上）。
- **AC-25（并发孤立记录不变式 = 0）**：并发「创建 BareMetal」与「删除其 Cluster」结束后，下列查询结果必须为 **0 行**：
  ```sql
  SELECT count(*) FROM bare_metals bm
  JOIN clusters c ON c.id = bm.cluster_id
  WHERE bm.deleted_at IS NULL AND c.deleted_at IS NOT NULL;
  ```
  即不存在「父已删 + 子活跃」的记录（ADR-0004 §5；`f014-soft-delete-handoff.md` 问题 3/7）。
- **AC-26（创建侧对父行取共享锁）**：创建 BareMetal 时必须对父 Cluster 行取**共享锁**并在同一事务内确认父行活跃；未命中活跃父 → 拒绝创建（不留无主机器）（`f014-soft-delete-handoff.md` 问题 3）。
- **AC-27（活跃子检查非空断言，F014 NOTE-01）**：`CLUSTER_ACTIVE_CHILD_CHECKS` **非空**且包含「Cluster 下是否存在活跃 BareMetal」的检查；断言其被 Cluster 删除路径真实消费（`docs/reviews/f014-soft-delete.md` NOTE-01）。

**边界与前端**

- **AC-28（无位置 / 上级 / 自动发现结构）**：BareMetal 的请求、响应、表结构与端点上不存在 DataCenter / 园区 / 机房 / 机柜 / U 位字段，也不存在任何自动发现 / 外部平台同步相关字段或端点（§6、§13、R-BM-007、§23）。
- **AC-29（不越界到其它资源）**：F002 不注册 NIC / IP / VM / Container / Service 端点；`bare_metals` 表不含指向这些实体的结构；Cluster 视角专用端点（`by-name/{name}/bare-metals`）不属 F002（F004 ~ F009）。
- **AC-30（前端三态与 Empty/Not Found 可区分）**：BareMetal 列表页在 Loading / Empty / Error 三种情形渲染**互不相同**的状态；Empty（无活跃 BareMetal）与 Not Found（资源不存在或已删）在界面上可被用户区分；错误按 `error.code` 分支渲染，不解析 `message`；删除 / 修改失败按 `409` / `404` / `401` 分别处理，前端**不得**自行实现业务守卫（§21；R-QUERY-004）。

**明确不进入 F002 AC**：Cluster 自身的 CRUD / 命名规则（F001）；Cluster 成员列表页面与状态汇总视图（F009）；硬件字段的筛选 / 统计；导出；审计 / 历史；导入（F011）；认证（F013）。

## Assumptions

（不阻塞当前工作、可安全暂时采用；**不得当作 CONFIRMED**）

1. F002 复用 F012/F013/F014 已交付基座（统一错误信封、SQLSTATE→HTTP 映射、分页、请求级事务边界、活跃过滤原语、统一软删服务），不在 BareMetal 模块另立一套。
2. F002 **新增** `bare_metals` 表（含 R-BM-007 七列）与增量 migration（`0003+`，不改 `0001`/`0002` 基线）；`database: true`（由 Architecture 确认）。
3. `PATCH /api/bare-metals/{id}` 的可变字段为 `status`（R-BM-006，CONFIRMED 依据）与 R-BM-007 硬件字段（登记事实的修正，依据 `domain-model.md` §9「资源记录仅支持更新」）；**不包含** `hostname` / `cluster_id`（见 Scope「本次未涉及」与 NQ-1）。
4. 创建时不接受显式 `status` 时按 R-BM-004 默认 `IDLE`；是否允许登记时显式指定非 `IDLE` 状态见 NQ-3（PROPOSED P-2）。
5. `hostname` 的长度 / 首尾空白 / 空字符串 / 非法字符等**未定义**（`domain-model.yaml` 对 BareMetal hostname 未列 `undefined_constraints`，但同样未确认任何字符规则）；F002 **不实现、不承诺**任何此类校验，也不引入类似 R-CLUSTER-005 的 `/` 禁令（该禁令仅针对 Cluster 名称）。
6. 系统当前不存在 BareMetal 数据（`bare_metals` 表尚不存在），F002 不涉及历史数据迁移 / 清洗。
7. 前端路由方案沿用 F001 现状（无 `vue-router`），页面切换形式不构成产品规则。
8. `page_size` 默认 50 / 上限 200 沿用 F012/F001 约定，不固化为产品规则。
9. BareMetal 删除入口在列表页与详情页均提供（与 F014 对 Cluster 的处理一致），交互形式（二次确认样式）不构成产品规则。

## Proposed Rules

**PROPOSED-1（需用户裁定，非 CONFIRMED）**：**不为 BareMetal 提供全局 `by-name` 只读别名**（如 `GET /api/bare-metals/by-name/{hostname}`）。理由：`hostname` 仅按 Cluster 唯一（R-BM-002），全局别名不可判定；ADR-0003 §2 只为全局唯一的 Cluster 名称授予了 `by-name`。若未来需要按名称寻址，必须是 **Cluster 限定**的读路径（与 F009 的 Cluster 视角一致）。F002 不实现、不承诺该别名。

**PROPOSED-2（需用户裁定，非 CONFIRMED）**：建议允许 `POST /api/bare-metals` **可选**携带 `status`（缺省 `IDLE`）。依据 R-BM-004 的「默认」措辞暗示可指定非默认值，便于「登记一台已知 DOWN 的机器」。当前按假设 4 处理（缺省 IDLE）；若确认允许显式指定，属**范围扩展**，不改动任何已确认规则。若确认「登记时只能 IDLE」，则 F002 的 POST 请求体不含 `status`。

**PROPOSED-3（需用户裁定，非 CONFIRMED）**：建议明确 `hostname` 的**登记后可变性**，以及是否允许 **BareMetal 跨 Cluster 迁移**（改变 `cluster_id`）。当前二者均为 UNCONFIRMED，F002 按假设 3 不作为 PATCH 能力（见 NQ-1）。若确认允许，需明确：迁移后 `hostname` 的目标 Cluster 唯一性如何重校验、迁移是否受「父有活跃子资源」约束。

**PROPOSED-4（需用户裁定，非 CONFIRMED）**：建议明确 `hostname` 的最小字符约束（是否拒绝空字符串 / 首尾空白 / 长度上限）。当前为未定义，F002 不得实现。

其余无产品建议。本 Feature 不新增任何领域对象、关系、状态或唯一性规则，也不修改任何已有规则。

## Open Questions

### Blocking

**无。**

**逐一对照 Blocking 判定标准（含 NQ-1 为何不构成 Blocking）：**

- **不确认就无法确定本次功能范围？** 否。F002 的范围（登记 / 查询 / 状态维护 / 硬件字段维护 / 逻辑删除 / F014 端到端）完全由 R-BM-001 ~ R-BM-007、R-DELETE-* 与已批准 ADR / 交接确定。`hostname` / `cluster_id` 的登记后可变性不在任何已确认要求之内，归入「本次未涉及」，不阻塞范围界定。
- **是否导致两种明显不同的用户行为？** 对**被排除的迁移 / 改名操作**是（可原地修正 vs 需删除重建）。但由于该操作不属 F002，F002 的行为是单值的：其 AC 全部可判定且不依赖该答案。该问题的解决是**未来的范围新增**，不是对 F002 的规则修改（可逆、加性）。
- **是否改变核心领域关系？** 否。只要不实现迁移，R-BM-001 的 N:1 mandatory 关系与其唯一性边界保持不变。
- **是否导致验收标准无法定义？** 否。AC-01 ~ AC-30 全部可判定。

该结论与已接受的 F001 先例一致：`Cluster 名称是否可变` 在 F001 被列为 **非阻塞 OPEN（NQ-5 / PROPOSED-2）+ 假设**，而非 Blocking（`docs/product/handoffs/f001-cluster.md`；`docs/architecture/f001-cluster-handoff.md` OPEN #2）。

### Non-blocking

- **NQ-1（hostname / cluster_id 的登记后可变性）**：UNCONFIRMED。当前 F002 不提供该能力（Scope「本次未涉及」；假设 3）。建议在真实数据录入前由用户确认，见 PROPOSED-3。**不阻塞架构设计。**
- **NQ-2（引用不存在 / 已软删 Cluster 的响应码）**：写入必须被阻止且不得 5xx，但应返回 `400 VALIDATION_ERROR + details[].field="cluster_id"`（字段级请求校验失败）还是 `404 NOT_FOUND`（父资源不存在），`api-conventions.md` 未固定。建议由 Architecture 在 api-conventions 内裁定并写入 F002 契约；不影响 AC-03 的可判定性（「被阻止 + 无写入 + 非 5xx」）。
- **NQ-3（登记时是否可显式指定状态）**：见 PROPOSED-2。
- **NQ-4（`hostname` 未定义约束）**：见 PROPOSED-4 / 假设 5。与 F001 NQ-1 同类，**不实现、不承诺**。
- **NQ-5（按 Cluster 读取的路由归属）**：`GET /api/clusters/by-name/{name}/bare-metals` 已由 `f001-cluster-handoff.md` PROPOSED #5 判归 **F009**。F002 必须提供可复用的「按 Cluster 限定读取」能力（`GET /api/bare-metals?cluster_id=` 或等价），但**具体路径形态与归属**由 Architecture 裁定；F002 不实现 Cluster 视角的专用别名端点。
- **NQ-6（R-BM-007 硬件列与文档同步）**：见「已确认冲突 / 文档漂移」1、2。需由 Architecture / Database / 协调器同步 `docs/database/csm-v1-schema-design.md` 与 `domain-model.yaml`，使其与 CONFIRMED 的 R-BM-007 一致。**不阻塞 F002**（以 R-BM-007 为准即可开工）。
- **NQ-7（后续 Feature 的 BareMetal 子资源删除守卫）**：F004 / F006 / F007 / F008 落地时，必须向 BareMetal 的活跃子资源检查声明追加各自检查，并补「BareMetal 有活跃 NIC/VM/Container/Service → `DELETE /api/bare-metals/{id}` → `409`」的端到端验收。F002 建立该检查点与声明位置，并记入 `project-plan.yaml` 的对应 Feature 义务。**不阻塞 F002。**
- **NQ-8（project-plan 元数据同步）**：F002 `requirements` 列表建议补 `§21`、`R-DELETE-004`、`R-DELETE-006`；F002 `open_questions` 承接本 Handoff 的 NQ-1 ~ NQ-4。属计划元数据修正。
- **NQ-9（F012 F-02 潜在相关）**：`sqlstate.py` 的 FK 违规字段回退解析可能把 `cluster_id` 截断为 `cluster`（`docs/reviews/f012-project-foundation.md` F-02），F002 是首个真实 FK 场景。建议 Backend 在 F002 阶段验证并在真实 FK 违规路径上给出正确字段名；**不改变任何产品行为**。

## Architecture Handoff

以下为 Architect 需解决的技术设计问题（本 Handoff 不选择框架、不设计表、不定义 API 细节）：

1. **`bare_metals` Schema 与增量 migration**：R-BM-007 已确认，需为 `bare_metals` 设计并新增硬件列（`vendor` / `model` / `serial_number` / `cpu` / `memory` / `gpu` / `storage`，纯文本可空）与既有已设计部分（`cluster_id` NOT NULL FK `ON DELETE RESTRICT`、`hostname` NOT NULL、`status` NOT NULL DEFAULT `'IDLE'` + CHECK 四值、`deleted_at`）。`ck_bare_metals_status`、`ux_bare_metals_cluster_hostname_active`（predicate `deleted_at IS NULL`）、`ix_bare_metals_cluster_id` 已在数据库设计中给出，需与 R-BM-007 一并纳入 `0003+` migration；**不改 `0001`/`0002` 基线**。同步 `docs/database/csm-v1-schema-design.md`（见 NQ-6）。
2. **端点集合与契约落点**：确认 5 个端点（`POST /api/bare-metals`、`GET /api/bare-metals`、`GET /api/bare-metals/{id}`、`PATCH /api/bare-metals/{id}`、`DELETE /api/bare-metals/{id}`）与资源表示（字段集合见 AC-01；`deleted_at` 不暴露；无位置 / 上级字段），并决定新建 `docs/api/f002-bare-metal.md` 作为唯一权威契约。
3. **创建路径的父存在性 / 活跃性与并发协议**：落实「对父 Cluster 行取 `FOR SHARE` 并确认活跃」、FK 违规与「父不存在 / 已删」的响应码（NQ-2）、以及并发「创建 vs 删父」的孤立记录不变式（AC-25/26）。与 F014 的锁序协议对齐。
4. **按 Cluster 限定读取的路由形态**：决定 `GET /api/bare-metals?cluster_id=` 与 / 或 Cluster 嵌套路径，明确 Empty（200 空）与 Not Found（404）的判定位置与归属（F002 能力 vs F009 别名，见 NQ-5），保证 R-QUERY-004 语义成立且 F009 可复用。
5. **BareMetal 的活跃子资源检查声明位置**：建立 `BARE_METAL_ACTIVE_CHILD_CHECKS`（当前显式空元组）与统一软删服务的接线；明确后续 Feature 追加检查的机制（ADR-0004 §5；AC-22；NQ-7）。
6. **F014 端到端义务的落点**：在 `CLUSTER_ACTIVE_CHILD_CHECKS` 注入 BareMetal 检查（AC-23/27）、提供 `409` + `ACTIVE_CHILDREN_EXIST` 端到端与并发不变式测试（AC-23/24/25/26），并处理 `docs/reviews/f014-soft-delete.md` NOTE-01（活跃子检查非空断言）。
7. **状态与硬件字段的可变性接线**：`PATCH` 仅接受 `status` + R-BM-007 字段（假设 3）；`hostname` / `cluster_id` 不在 PATCH 契约内（NQ-1）；状态校验复用唯一一份领域校验并保证 `23514` → `400` 而非 500；更新路径的 `hostname` 唯一性不需要处理（不可变假设下）。
8. **未定义约束的「不实现」保障**：确认 schema 层不会隐式引入 `hostname` 的长度 / trim / 非空串 / 字符校验，也不会引入类似 R-CLUSTER-005 的 `/` 禁令（假设 5 / NQ-4），并以可失败 guard 固定。
9. **删除端点注册与依赖方向**：`DELETE /api/bare-metals/{id}` 由其资源模块注册并委托 F014 统一软删服务（只允许一条 `deleted_at` 写入路径）；确认不引入第二条软删路径、不引入 restore / 批量能力。
10. **前端接线**：BareMetal 列表 / 详情 / 登记 / 状态维护 / 删除入口，三态与 Empty/Not Found 区分，错误按 `error.code` 渲染，前端不重复实现业务守卫（§21；AC-30）。
11. **交付层判定**：确认 `database: true`（新增表 / 列 / migration）与 backend / frontend 层范围；确认 `project-plan.yaml` 的 `layers` / `contract` / `implementation` 同步与 NQ-7 / NQ-8 的义务落盘。
12. **既有测试的演进**：F002 引入首个真实 FK 与首个非 Cluster 资源表；确认 F012/F014 的 schema guard（`test_only_expected_tables_registered` 断言集合、无 CASCADE guard、唯一软删写入路径 guard）随 `bare_metals` 增表而**演进而非删除**。

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。F002 的端点集合与字段边界、R-CLUSTER-004 的 F002 侧、状态语义、唯一性、删除与生命周期承诺均已在本 Handoff 中给出可判定的产品边界；NQ-1（`hostname` / `cluster_id` 登记后可变性）经逐条对照判定为 **Non-blocking**（不属已确认要求、已被显式移出本次范围、F002 全部 AC 不依赖其答案，且与已接受的 F001 先例一致）。