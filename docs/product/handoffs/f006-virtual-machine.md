# Product Handoff — F006 VirtualMachine 登记与管理

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-16
> Feature: F006（E03，P1，`depends_on: [F002]` = DONE）
> Product Source: `requirements.md` §9 / §10 / §13 / §15 / §17 / §21 / §22 / §23 / Q-002、R-DELETE-004/005/006、R-QUERY-003/004；`domain-model.md` §3/§5.3/§6/§7.2/§9；`domain-model.yaml > resources[VirtualMachine]`

---

## Feature

VirtualMachine 登记与管理（F006）— CSM V1 虚拟资源的第一个资源：虚拟机的人工登记、查询、可选配置维护与逻辑删除，以及 **VirtualMachine → BareMetal 必选绑定** 的真实业务落地。

## Problem

F001/F002 已让「集群 → 机器」成为可信事实；但运维人员日常还有一类**没有物理位置、却必须知道它跑在哪台机器上**的资源：虚拟机。

当前 Excel 场景的痛点：VM 与宿主机器、宿主机器的集群之间的对应关系靠另一张表 / 口头维护；VM 名称在不同表格里重名、大小写混用，无法确定是否同一台；VM 下线时直接删行，宿主关系与历史一并丢失；「自动同步虚拟化平台」的冲动会引入 V1 明确排除的运行时集成（R-VM-002、§23）。

使用者：HPC / AI 集群运维人员、基础设施管理员（§3）。产品价值：**让「一台虚拟机叫什么、跑在哪台机器上、属于哪个集群（由宿主推导）」成为可信、唯一、可维护的事实**，并让 R-DELETE-004 获得**第二个真实业务端到端**（宿主有活跃 VM → 不得删除宿主）。

---

## Confirmed Requirements

1. V1 支持**人工登记与查询** VirtualMachine（R-VM-001）。
2. V1 **不要求自动接入** VMware / PVE / OpenStack 或任何其他虚拟化平台 API（R-VM-002；§23；OPEN-006 已关闭为「已确认排除」）。`hypervisor` 只是**记录**字段，不触发任何外部调用。
3. VirtualMachine **必须拥有 `name`**，作为身份标识（R-VM-004）。
4. `name` 在**所有当前有效 VirtualMachine 范围内全局唯一**——不区分宿主、不区分 Cluster（R-VM-004）。与 Container 的「同一载体内唯一」（R-CONTAINER-003）是不同的唯一性边界，不得混用。
5. `name` 比较**区分大小写**（R-VM-004、§22）。
6. 已逻辑删除的 VirtualMachine **不再占用**该唯一性（R-VM-004 引 R-DELETE-006）。
7. VirtualMachine → BareMetal 绑定为**必选**：恰好一个宿主（R-VM-005）。
8. VirtualMachine 的 **Cluster 归属由其宿主 BareMetal 推导，不单独记录**（R-VM-005）。VM **不存 `cluster_id`**。
9. 宿主 BareMetal 存在活跃 VirtualMachine 时，**不得删除该宿主**（R-VM-005、R-DELETE-004）。
10. 逻辑删除 VirtualMachine **不得自动级联**（R-VM-005、R-DELETE-005）。
11. VirtualMachine 在 V1 **可选**记录：CPU / Memory / Disk / OS / Hypervisor / Owner；全部**可选**、**纯文本**、允许 `NULL`、不结构化（R-VM-006）。
12. VirtualMachine 在 V1 **不设状态**（Q-002=B）。
13. 关键冲突必须**在保存前阻止**，不能只依赖 UI 校验（§21）。
14. 资源采用**逻辑删除**；无 Undelete / Restore（§17、R-DELETE-001/002/003）。
15. 父资源存在活跃子资源时不得删除父资源；逻辑删除**不自动级联**（R-DELETE-004/005）。
16. 查询结果必须区分 **Resource Not Found（404）** 与 **Empty Relationship（200 + 空集合）**（R-QUERY-004）。
17. API 契约按已批准约定：规范路径用 `id`、写操作走 `id`、列表 `{items,total,page,page_size}`、可选字段空值返回 `null` 不省略、错误信封含 `error.code`、`deleted_at` 不对外暴露（ADR-0003、`api-conventions.md` §2~§7）。
18. 唯一软删机制：单一 `deleted_at` + partial unique index（predicate `deleted_at IS NULL`）+ 统一软删写入路径 + 父删子拦同事务加锁、不级联、无 undelete（ADR-0004）。
19. **F014 交接义务**：F006 必须向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 追加「BareMetal 下是否存在活跃 VirtualMachine」检查，并交付真实端到端（`409 ACTIVE_CHILDREN_EXIST`、软删后可删、并发孤立记录 0 行、创建侧对宿主取 `FOR SHARE`）。
20. F006 同时是 **F007 的父资源方**：VM 删除路径须以显式声明的活跃子资源检查点承接「活跃 Container」（R-CONTAINER-005），当前显式为空元组。
21. 认证：所有 `/api/*` 由 F013 中间件自动覆盖；未认证 → `401`（ADR-0005）。

---

## Confirmed Domain Rules

| 规则 | 内容 | 来源 |
|---|---|---|
| R-VM-001 | V1 支持人工登记与查询 VirtualMachine | §9 |
| R-VM-002 | V1 不要求自动接入任何虚拟化平台 API | §9、§23 |
| R-VM-003 | VM 与物理宿主的关系模型应能表达实际运行位置 | §9（已由 R-VM-005 落定） |
| R-VM-004 | `name` 必填、**全局唯一（所有活跃 VM，跨宿主跨 Cluster）**、区分大小写；已软删释放唯一性 | §9、§22 |
| R-VM-005 | VM → BareMetal **必选**（恰好一个宿主）；Cluster 归属由宿主推导、不单独记录；宿主有活跃 VM 不得删；VM 软删不级联 | §9 |
| R-VM-006 | 可选字段 `cpu / memory / disk / os / hypervisor / owner`：全部可选、纯文本、允许 `NULL`、不结构化 | §9 |
| Q-002=B | V1 仅 BareMetal 有状态；VirtualMachine 不设状态 | 变更记录；`domain-model.md` §7.1/§7.2 |
| §21 | 唯一性冲突与非法资源关系必须在保存前由后端 / 数据库阻止 | §21 |
| §22 | 名称唯一性比较区分大小写 | §22、R-VM-004 |
| §17 / R-DELETE-001..006 | 软删不物理删；无恢复；父有活跃子不得删；不级联；已删释放唯一性 | §17 |
| §23 / OPEN-006 | 自动资产发现 / 平台同步不属 V1 | §23、§29 |
| ADR-0002 | 默认 collation 大小写敏感；partial unique index；受控写入 + 一致性测试 | ADR-0002 |
| ADR-0003 | `id` 为规范路径；分页 / 错误信封 / Empty-vs-NotFound | ADR-0003 |
| ADR-0004 | 单一 `deleted_at`；统一软删服务；父删子拦同事务加锁；不级联；无 undelete；活跃子检查由资源模块显式声明 | ADR-0004 |

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。**

---

## 已确认冲突 / 文档漂移（必须记录，不得静默选择）

1. **`domain-model.md` §6 仍把 VM→BareMetal 列为「尚未确认」**，与自身 §5.3（关系为必选 R-VM-005）矛盾。以 §5.3 + R-VM-005 为准。
2. **`domain-model.md` §8 Uniqueness Rules 未收录 VM 名称全局唯一**，需补录。
3. **`domain-model.yaml > relationships[VirtualMachine-to-BareMetal]` 仍为 UNCONFIRMED**，`open_questions > OPEN-001` 仍 OPEN，`must_not_assume` 仍含「虚拟机绑定裸金属是必选的」，与同文件 `resources[VirtualMachine].binding_to_host.mandatory: true` 矛盾。待同步。
4. **`docs/database/csm-v1-schema-design.md`** 仍写「VM→BareMetal 未确认 → 不得固化为 `NOT NULL`」与「VM 需要同 Cluster 唯一名称可按反规范化 `cluster_id` 落地」。二者均已被 R-VM-005 取代（NOT NULL 必选 FK；名称**全局**唯一，**不需要** `cluster_id`）。
5. **`project-plan.yaml > F006` 元数据待更新**（layers / contract / open_questions）。

**F002 交接义务的复核（F006 侧）**：`BARE_METAL_ACTIVE_CHILD_CHECKS` 现为**显式空元组**。F006 必须完成「VM 部分」的追加，不得保持空元组。

---

## Scope

### 本次包含

1. **登记**：`name` + 宿主 BareMetal 必填；六个可选字段可选（R-VM-001、R-VM-004/005/006）。
2. **查询**：列表（分页）+ 详情；Empty / Not Found 按 R-QUERY-004 区分。
3. **可选配置字段维护**：`PATCH` 修改六个可选字段（R-VM-006）。
4. **逻辑删除**：委托 F014 统一软删服务，并声明自身活跃子资源检查点。
5. **R-VM-005 关系写入**：创建时校验宿主存在且活跃（对宿主行取 `FOR SHARE` 并同事务确认），不产生无主 / 指向已删宿主的 VM（§21；ADR-0004 §5）。
6. **R-VM-004 唯一性落地**：全局活跃 `name` 唯一、大小写敏感、已删释放；应用层 `409` + DB partial unique index 作为最终权威。
7. **F014 端到端义务**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 注入「活跃 VirtualMachine」检查。
8. **F007 的父资源侧义务**：显式声明 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS`（当前空元组）并在 VM 删除路径真实传入。
9. **前端**：列表 / 详情 / 登记表单 / 可选字段修改 / 删除入口；三态与 Empty / Not Found 可区分。
10. **读取路径软删过滤**：复用既有活跃过滤原语。

### 本次明确不包含

1. **VM 的状态**（Q-002=B）。
2. **任何虚拟化平台 API 接入 / 自动发现 / 同步 / 凭据**（R-VM-002；§23；OPEN-006）。
3. **VM 自身存储 `cluster_id`**（R-VM-005）。
4. **可选配置字段的结构化拆分**（R-VM-006）。
5. **物理删除、Undelete / Restore、回收站、软删级联**。
6. **VM 级别的 NetworkInterface / IPAddress**（R-NIC-003 的 VM 部分未确认，归属 F004）。
7. **Container / Service / NIC / IP 的实体、端点与页面**。
8. **R-QUERY-003 关联查询视图**（归 F010）；Cluster 视角成员视图（F009）。
9. **Cluster CRUD / 命名**（F001）、**BareMetal 实体 / 状态 / 端点**（F002）。
10. **Excel 批量导入**（F011）、**认证**（F013）。
11. **DataCenter / 位置 / Rack 等模型**（§6、§13）。

### 本次未涉及

- `name` 重命名与跨宿主迁移（NQ-1 / PROPOSED-1；默认不提供）；
- VM 全局 `by-name` 只读别名（NQ-3 / PROPOSED-2；默认不提供）；
- 「按宿主查看 VM」的读取方向（NQ-4；R-QUERY-003 归 F010）；
- 排序 / 筛选 / 导出 / 审计 / 批量 / 标签 / 统计报表。

---

## Acceptance Criteria

### 登记

- **AC-01（登记成功）**：`POST /api/virtual-machines` 携带 `name` 与「存在且活跃的宿主 BareMetal 标识」→ `201`；响应字段集合**恰为** `{id, <宿主标识>, name, cpu, memory, disk, os, hypervisor, owner, created_at, updated_at}`；不含 `deleted_at`、`status`、`cluster_id` / `cluster`、NIC / 位置 / 自动发现字段（R-VM-001/004/005/006；Q-002=B；§13）。
- **AC-02（`name` 必填）**：缺失或非字符串 → `400 VALIDATION_ERROR` + `details[].field == "name"`，不产生记录（R-VM-004；§21）。
- **AC-03（宿主必选）**：缺失或非整数宿主标识 → `400 VALIDATION_ERROR` + `details[].field` 指向该字段，不产生记录（R-VM-005）。
- **AC-04（宿主必须有效且活跃）**：引用不存在或已逻辑删除的 BareMetal → 写入被阻止、不产生记录、不得 5xx（R-VM-005；精确响应码见 NQ-2）。
- **AC-05（绑定恰好一个宿主）**：请求 schema 封闭——不接受多宿主、不接受以 VM / Container 作为宿主、不接受载体类型选择器；DB 宿主列 `NOT NULL` 且 FK `ON DELETE RESTRICT`（无 CASCADE）（R-VM-005；R-DELETE-005）。
- **AC-06（可选字段缺失不阻断）**：不提供任何 R-VM-006 字段 → `201`，各字段响应为 `null`（返回 `null` 而非省略）。
- **AC-07（纯文本往返）**：含中文的 `name` 与可选字段可登记、按字面值读出；`cpu = "8 vCPU"` 等原样存取，不拆分 / 不归一。
- **AC-08（未定义约束不实现）**：`name` 无长度 / 首尾空白 / 空串 / 字符 / `/` 禁令校验；空串与含首尾空白的 `name` 不被本 API 拒绝。不得被解读为已确认「空 name 合法」。

### 唯一性

- **AC-09（全局唯一，跨宿主）**：宿主 A 已有活跃 `vm1` 时，宿主 B 登记 `vm1` → `409 CONFLICT` + `details[].field` 含 `"name"`。
- **AC-10（全局唯一，跨 Cluster）**：宿主分属不同 Cluster 时跨 Cluster 重名同样被拒绝。
- **AC-11（大小写敏感）**：`vm1` 与 `VM1` 可共存；不存在 `lower(name)` 唯一索引或大小写折叠（R-VM-004、§22；ADR-0002 §2）。
- **AC-12（保存前阻止，DB 为最终权威）**：绕过界面直接调用 API 得到同一 `409`；绕过应用层直接对 DB 插入重复活跃 `name` 被数据库拒绝（§21；ADR-0002 §3）。
- **AC-13（soft delete 释放唯一性）**：软删 `vm1` 后可在任意宿主重新登记 `vm1` → `201`；旧已删行保留且 `deleted_at` 未被改写（R-DELETE-006）。

### 查询

- **AC-14（列表、分页、Empty）**：`GET /api/virtual-machines` → `200` + `{items,total,page,page_size}`；无活跃 VM 时 `items == []`，不得 404（R-QUERY-004）。
- **AC-15（详情 Not Found）**：`GET /api/virtual-machines/{id}` 对不存在或已逻辑删除 `id` → `404 NOT_FOUND`（不区分）。
- **AC-16（列表 / 详情排除已删）**：绕过应用层预置 `deleted_at` 非空 VM 后，该行不出现在列表 `items` / `total`；按 `id` 读取 → `404`（R-DELETE-002）。
- **AC-17（宿主绑定可观察）**：读回 VM 可观察宿主绑定（以宿主 `id` 表示）；请求 / 响应 / 表 / 查询参数中不存在 `cluster_id` / `cluster_name` 等 Cluster 维度字段或过滤参数（R-VM-005）。

### 无状态

- **AC-18（无状态）**：VM 的请求体、响应体、表结构与端点上不存在 `status` 字段、状态枚举、默认值或状态过滤参数；不存在任何读写 VM 状态的路径（Q-002=B）。

### 维护

- **AC-19（可选字段可更新）**：`PATCH /api/virtual-machines/{id}` 提供合法可选字段 → `200` 且返回新值；`null` 表示清空；缺省字段不变；再次读取一致。
- **AC-20（更新 schema 封闭）**：`PATCH` 含未识别字段（含 `id` / `deleted_at` / `cluster_id` / `status`）→ `400 VALIDATION_ERROR`；`name` 与宿主绑定默认不可变（NQ-1）；空 body `{}` → `400 VALIDATION_ERROR`。

### 删除与生命周期

- **AC-21（VM 逻辑删除）**：`DELETE /api/virtual-machines/{id}`（活跃行）→ `204` 且无响应体；该行仍物理存在且 `deleted_at` 非空；不出现在列表 / 详情。
- **AC-22（删除不级联）**：删除 VM 后，其宿主 BareMetal 的 `deleted_at` / `updated_at` / 各字段不变；无任何其它资源行被修改或物理删除（R-DELETE-005）。
- **AC-23（不提供恢复 / 批量能力）**：不存在 restore / undelete / purge / 批量删除 / `include_deleted` 查询参数。
- **AC-24（宿主有活跃 VM → 拒绝删除宿主）**：`DELETE /api/bare-metals/{id}` → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`；该 BareMetal 行 `deleted_at` 仍为 NULL（无部分写入）（R-DELETE-004；R-VM-005）。
- **AC-25（软删 VM 后宿主可删）**：先软删该宿主下全部活跃 VM，再 `DELETE /api/bare-metals/{id}` → `204`。
- **AC-26（并发孤立记录不变式 = 0 行）**：并发「创建 VM」与「删除其宿主」结束后，`SELECT count(*) FROM virtual_machines vm JOIN bare_metals bm ON bm.id = vm.<host_column> WHERE vm.deleted_at IS NULL AND bm.deleted_at IS NOT NULL` 必须为 **0**（ADR-0004 §5）。
- **AC-27（创建侧对宿主行取共享锁）**：创建 VM 时必须对宿主 BareMetal 行取共享锁并在同事务确认活跃；未命中活跃宿主 → 拒绝创建（不留无主 VM）。
- **AC-28（BareMetal 活跃子检查点非空且被真实消费）**：`BARE_METAL_ACTIVE_CHILD_CHECKS` 非空且包含「BareMetal 下是否存在活跃 VirtualMachine」检查；断言被 BareMetal 删除路径真实消费（F014 NOTE-01 同类）。
- **AC-29（VM 自身检查点显式声明）**：`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 为显式声明的元组（当前空），且 VM 删除路径真实传入它；F007 落地时须追加「活跃 Container」检查。

### 边界与前端

- **AC-30（不接入虚拟化平台）**：不存在 VMware / PVE / OpenStack / 其他平台 API 客户端、凭据字段、外部平台 id、同步 / 发现字段或端点；`hypervisor` 仅作为文本登记字段。
- **AC-31（不越界到其它资源）**：F006 不注册 NIC / IP / Container / Service 端点；`virtual_machines` 表不含指向这些实体的结构，也不含 DataCenter / 位置字段；VM 不拥有独立 NetworkInterface。
- **AC-32（前端三态与 Empty / Not Found 可区分）**：VM 列表页 Loading / Empty / Error 三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code` 分支（不解析 `message`）；`409` / `404` / `401` 分别处理；前端不得自行实现业务守卫（§21；R-QUERY-004）。

---

## Assumptions

1. F006 复用 F012/F013/F014/F002 已交付基座，不在 VM 模块另立一套。
2. F006 **新增** `virtual_machines` 表与增量 migration（当前 head `0003_f002_bare_metals`；若 F004/F005 先落地则顺延），**不改**既有基线 migration；`database: true`。
3. `PATCH` 可变字段仅为 R-VM-006 六个可选字段；不含 `name` 与宿主绑定（NQ-1）。
4. 宿主 BareMetal 引用在请求中以宿主 `id` 表达；VM 不提供 `by-name` 写别名（ADR-0003 §2）。
5. 「缺省」与「显式 `null`」均落为 `NULL`，响应返回 `null` 而非省略。
6. `name` 的长度 / 首尾空白 / 空串 / 非法字符 / `/` 等**未定义**；F006 不实现、不承诺任何此类校验，也不引入 `/` 禁令（该禁令仅针对 Cluster 名称）。
7. 系统当前不存在 VirtualMachine 数据，F006 不涉及历史数据迁移。
8. 前端沿用无 `vue-router` 现状。
9. `page_size` 默认 50 / 上限 200 沿用既有约定。
10. 契约落点为**新增** `docs/api/f006-virtual-machine.md`（唯一权威）。

---

## Proposed Rules

**PROPOSED-1（需用户裁定）**：VM 的 `name` 与宿主绑定在登记后是否可变（重命名 / 跨宿主迁移）。F006 默认**不提供**；运营上可由「软删 + 重新登记」替代。若需，属范围新增。

**PROPOSED-2（需用户裁定）**：是否为 VM 提供全局 `by-name` 只读别名。ADR-0003 §2 只为全局唯一的 Cluster 名称授予；F006 默认不实现。

**PROPOSED-3（需用户裁定）**：建议明确 `name` 与可选字段的最小字符约束。当前未定义，F006 不得实现。

---

## Open Questions

### Blocking

**无。** F006 范围由 R-VM-001~006 + R-DELETE-* + R-QUERY-004 + 已批准 ADR / 交接完全确定；AC-01~AC-32 全部可判定，不依赖 NQ-1 ~ NQ-7 任何一项。与 F001 / F002 已接受先例一致。

### Non-blocking

- **NQ-1（`name` / 宿主绑定可变性）**：UNCONFIRMED；默认不提供（PROPOSED-1）。
- **NQ-2（引用不存在 / 已软删宿主的响应码）**：写入必须被阻止且不得 5xx；建议沿用 F002 的 `404 NOT_FOUND`。由 Architecture 在 F006 契约内裁定。
- **NQ-3（VM 全局 `by-name` 只读别名）**：需求未要求；默认不实现（PROPOSED-2）。
- **NQ-4（「按宿主查看 VM」读取方向的归属）**：R-QUERY-003 已归 F010。F006 是否同时提供可复用的「按宿主限定读取」能力未明确，PM 不自行发明。建议由协调器 / Architecture 确认：若 F006 提供 canonical 宿主限定读取（与 F002 `?cluster_id=` 先例对称），F010 必须复用；若归 F010，则 F006 只交付全局列表 + 详情。任何按宿主限定读取都必须满足 R-QUERY-004。
- **NQ-5（`name` 与可选字段未定义约束）**：不实现、不承诺。
- **NQ-6（文档与计划元数据同步）**：见「已确认冲突 / 文档漂移」1~5。
- **NQ-7（VM 读路径是否附加推导出的 Cluster）**：未要求；按最小范围不返回 Cluster 字段。

---

## Architecture Handoff

1. **`virtual_machines` Schema 与增量 migration**：宿主列 `NOT NULL` + FK `ON DELETE RESTRICT ON UPDATE RESTRICT`（禁止 CASCADE）；`name NOT NULL`（无长度 / trim / 字符约束）；六个可空 `TEXT` 列；`deleted_at`；**无 `status` 列**；**无 `cluster_id` 列**。唯一性为 **`name` 上的全局 partial unique index**（predicate `deleted_at IS NULL`，大小写敏感，不声明 `COLLATE`）。宿主检索索引由 Architecture 判定。不改既有基线 migration；同步 `docs/database/**`。
2. **端点集合与契约落点**：确认端点（预期 5 个），确认资源表示封闭字段集合（AC-01），并新建 `docs/api/f006-virtual-machine.md`。是否提供宿主限定读取、是否提供 `by-name` 取决于 NQ-4 / NQ-3。
3. **创建路径的宿主存在性 / 活跃性与并发协议**：落实「对宿主 BareMetal 行取 `FOR SHARE` 并确认活跃」、FK 违规与「宿主不存在 / 已删」的响应码（NQ-2），以及并发孤立记录不变式（AC-26/27）。
4. **R-VM-004 全局唯一性落地**：应用层 `409`（`details[].code = "DUPLICATE"`、`field = "name"`）+ partial unique index；不引入任何大小写折叠（`lower()`）。
5. **F014 端到端义务落点**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 注入「活跃 VirtualMachine」检查（AC-28）；演进既有 schema / 表集合 guard 加入 `virtual_machines`（增表，不得删测试）。
6. **VM 自身活跃子检查声明位置**：建立 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS`（显式空元组）与统一软删服务接线；明确 F007 追加机制。
7. **无状态与字段边界的结构性保障**：以可失败 guard 固定 VM 无 `status` 列 / 无状态端点 / 无状态过滤，且六个字段不被结构化拆分。
8. **未定义约束的「不实现」保障**：确认 schema / ORM 层不隐式引入 `name` 校验，也不引入 `/` 禁令，并以可失败 guard 固定。
9. **未接入外部平台的保障**：确认不存在任何平台客户端 / 凭据 / 同步字段或端点（AC-30）。
10. **删除端点注册与依赖方向**：VM 模块注册 `DELETE` 并委托 F014 统一软删服务；不引入 restore / 批量。
11. **读取路径活跃过滤**：复用 `app/db/active.py`，不新写谓词；列表 / 详情 Empty 与 Not Found 判定位置。
12. **前端接线**：列表 / 详情 / 登记 / 可选字段修改 / 删除入口；错误按 `error.code`；不重复实现业务守卫。
13. **交付层判定与既有 guard 演进**：确认 `database: true` 与 backend / frontend 层；同步 `project-plan.yaml > F006`；表集合 guard 随新表**演进**而非删除。
14. **NQ-4 归属澄清**：在契约中明确「按宿主查看 VM」读取方向是否属 F006；若属，须与 F002 `?cluster_id=` 先例对称、供 F010 复用，并满足 R-QUERY-004。

---

## 变更影响

**对既有已确认规则：None。**

结构性影响：`BARE_METAL_ACTIVE_CHILD_CHECKS` 从显式空元组演进；新增 `virtual_machines` 表 → 表集合 guard 增表演进；`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 为 F007 预留追加位置。

文档漂移需同步：`domain-model.md` §6/§8、`domain-model.yaml`、`docs/database/csm-v1-schema-design.md`、`project-plan.yaml > F006`。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。NQ-1 判定为 Non-blocking；NQ-4 已明确「不自行发明」。

GIT: NONE
