# Product Handoff — F004 NetworkInterface 管理

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-16
> Feature: F004（E02，P1，`depends_on: [F002]` = DONE）
> Product Source: `requirements.md` §11/§13/§15/§16/§17/§21/§22/§23、R-NIC-001~003、R-DELETE-001~006、R-QUERY-004、Q-002；`domain-model.md` §3/§5.6/§6/§7.2/§8/§9；`domain-model.yaml > resources[NetworkInterface]`

---

## Feature

NetworkInterface 管理（F004）— CSM V1 网络资源的第一个资源：网络接口的**人工登记、查询、用途与技术类型维护、逻辑删除**，以及 **NetworkInterface → BareMetal 必选绑定** 的真实落地与 F014 父删子拦端到端。

## Problem

F001/F002/F006 已让「集群 → 机器 → 虚拟机」成为可信事实。但运维人员面对的还有一类挂在机器上、不构成独立算力、却必须被准确记录的资源：网卡 / 网络接口。

痛点：「这台机器有几张网卡、分别干什么用」只存在于另一张表或口头描述；技术类型与用途被自由填写、同一含义多种写法，无法按用途核对；删机器时不知道还挂着网卡记录；反向地，因「网卡通常还有 MAC / 速率 / MTU / IP」的惯性，很容易在 V1 引入尚未确认的字段与 IP 关系（§23）。

产品价值：**让「某台机器上有哪些网络接口、每个接口的技术类型与用途是什么」成为可信、可查询、可维护的事实**，并为 F005（IP 地址）提供唯一合法挂载点，为 F010 / F011 提供可复用的 NIC 能力。

---

## Confirmed Requirements

1. NetworkInterface 属 Network Resource（§5 Taxonomy），V1 支持**人工登记与查询**（§1、§26）。
2. **必须记录 `technology_type`**，取值为**封闭集合** `Ethernet / InfiniBand / RoCE / Other`，无其他取值；新增取值须先经需求确认（R-NIC-001；2026-09-15 用户裁定）。
3. **必须记录 `purpose`**，取值为**封闭集合** `BMC / Management / Business / Compute / Storage / DataTransfer / Other`；内部枚举固定（R-NIC-002；2026-09-15 用户裁定）。
4. **必须拥有 `name`**（接口名，如 `eth0` / `ib0`），是登记字段（`domain-model.md` §5.6）。
5. NetworkInterface → BareMetal 绑定**必选**：恰好一个 BareMetal；N:1；不存在无主 NIC（R-NIC-003）。
6. **一个 BareMetal 可拥有多张** NetworkInterface。
7. NIC 在 V1 **不设状态**（Q-002=B）。
8. 关键冲突必须在**保存前阻止**，不能只依赖 UI 校验（§21）。
9. 逻辑删除；已删不出现在常规查询；不继续占用业务唯一性；V1 无 Undelete / Restore（§17、R-DELETE-001/002/003/006）。
10. 父资源存在活跃子资源时不得删除父资源；逻辑删除不自动级联（R-DELETE-004/005）。
11. 查询结果必须区分 Resource Not Found（404）与 Empty Relationship（200 + 空集合）（R-QUERY-004）。
12. API 契约按已批准约定（ADR-0003、`api-conventions.md`）。
13. 唯一软删机制（ADR-0004）。
14. **F014 交接义务**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 追加「活跃 NIC」检查 + 真实端到端。
15. F004 是 **F005 的父资源方**：显式声明 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`（当前空元组）。
16. 认证由 F013 中间件自动覆盖（ADR-0005）。

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。**

---

## Confirmed Domain Rules

| 规则 | 内容 |
|---|---|
| R-NIC-001 | `technology_type` 必填，封闭枚举 `Ethernet / InfiniBand / RoCE / Other`（`enum_closed: true`，2026-09-15） |
| R-NIC-002 | `purpose` 必填，封闭枚举 `BMC / Management / Business / Compute / Storage / DataTransfer / Other` |
| R-NIC-003 | NIC 必须与所属资源有明确关系，核心对象为 **BareMetal**；VM 等是否拥有独立 NIC **未确认，不得自动推导** |
| NIC→BareMetal | N:1、必选、CONFIRMED |
| Q-002=B | NIC 在 V1 不设状态 |
| §21 | 非法资源关系 / 非法枚举值必须在保存前由后端 / 数据库阻止 |
| §17 / R-DELETE-001..006 | 软删不物理删；无恢复；父有活跃子不得删；不级联；已删释放唯一性 |
| §15 | `IPAddress → NetworkInterface` 必选；IP 唯一性归 F005 |
| §23 | 不引入自动资产发现 / 外部同步；不假设 NIC 具备 MAC / 速率 / MTU 等未确认字段 |
| ADR-0002/0003/0004 | collation 与 partial unique；`id` 为规范路径与 Empty-vs-NotFound；单一 `deleted_at` + 统一软删服务 + 活跃子检查由资源模块显式声明 |

---

## 目标与范围

### 本次包含

1. **登记**：`bare_metal_id` + `name` + `technology_type` + `purpose` 必填。
2. **查询**：列表（分页）+ 详情；Empty / Not Found 按 R-QUERY-004 区分。
3. **维护**：修改 `technology_type` / `purpose`。
4. **逻辑删除**：委托 F014 统一软删服务，显式声明自身活跃子资源检查点。
5. **关系写入**：创建时对父 BareMetal 取 `FOR SHARE` 并同事务确认活跃。
6. **枚举落地**：应用层 `400` + 数据库 `CHECK` 作为最终权威。
7. **无状态落地**：无状态字段 / 枚举 / 过滤 / 端点。
8. **F014 端到端义务**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 追加「活跃 NIC」检查（保留既有活跃 VM 检查）。
9. **F005 父资源侧义务**：显式声明 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`（当前空元组）并在删除路径真实传入。
10. **前端**：列表 / 详情 / 登记 / 维护 / 删除入口；三态与 Empty / Not Found 可区分。
11. **读取路径软删过滤**：复用既有活跃过滤原语。

### 本次明确不包含

1. **NIC 的状态**（Q-002=B）。
2. **MAC / 速率 / MTU / 光模块 / 端口号等未确认字段**。
3. **IP 字段与 IP 关系**（归 F005）。
4. **NIC 挂到 BareMetal 以外的载体**（VM / Container / Cluster / Service）；VM 拥有独立 NIC 属未确认（NQ-1）。
5. **自动资产发现 / 外部平台同步**（§23）。
6. **物理删除、Undelete / Restore、回收站、软删级联**。
7. **NIC `by-name` 别名**（`name` 唯一性未确认）。
8. **R-QUERY-003 关联查询视图**（归 F010）。
9. **Excel 批量导入**（归 F011）。
10. **Cluster 视角资源查询页面**（归 F009）。
11. **BareMetal / Cluster / VirtualMachine 自身 CRUD 与端点**。
12. **批量操作、导出、审计、标签、排序、筛选与统计报表**。
13. **NIC 名称唯一性校验**（未确认，NQ-2；不得自行发明）。

### 本次未涉及

- `name` 与归属 BareMetal 的登记后可变性（NQ-3）；
- `Other` 是否需伴随自由文本（NQ-4）；
- 枚举的中文展示文案与顺序（UI 规范，不构成产品规则）；
- 按 BareMetal 限定读取的路由归属与形态（NQ-6）；
- 历史 / 审计 / 导出 / 高级筛选 / 负责人 / 备注字段。

---

## Acceptance Criteria

### 登记

- **AC-01（登记成功）**：`POST /api/network-interfaces` 携带活跃 BareMetal 标识 + `name` + 合法 `technology_type` + 合法 `purpose` → `201`；响应字段集合**恰为** `{id, bare_metal_id, name, technology_type, purpose, created_at, updated_at}`；不含 `deleted_at` / `status` / MAC / 速率 / MTU / IP / VM / Container / Cluster 归属字段。
- **AC-02（`name` 必填）**：缺失或非字符串 → `400 VALIDATION_ERROR` + `details[].field == "name"`，不产生记录。
- **AC-03（`technology_type` 必填且封闭）**：缺失 / 非字符串 → `400` + `field == "technology_type"`；四个合法值通过；其它值（`FibreChannel`、`ethernet`、`"Other "`、空串、`null`）→ `400`，不产生记录。**字面精确匹配，不做大小写折叠或 trim**。
- **AC-04（`purpose` 必填且封闭）**：同 AC-03，对七个合法值与非法值分别成立。
- **AC-05（`Other` 是合法成员，不是自由填写入口）**：`"Other"` → `201`，读回字面值 `"Other"`；请求 / 响应 schema **不存在** `other_text` / `description` 类伴随字段；任意非枚举字符串不得被接受。
- **AC-06（父 BareMetal 必填）**：缺失或非整数父标识 → `400` + `details[].field` 指向该字段，不产生记录。
- **AC-07（父必须有效且活跃）**：引用不存在或已逻辑删除的 BareMetal → 写入被阻止、不产生记录、**不得 5xx**（响应码见 NQ-5）。
- **AC-08（绑定恰好一个 BareMetal）**：请求 schema 封闭——不接受多父、不接受以 VM / Container / Cluster / Service 为父、不接受载体类型选择器；DB 父列 `NOT NULL` 且 FK `ON DELETE RESTRICT`。
- **AC-09（一个 BareMetal 多张 NIC）**：同一 BareMetal 下连续登记 2 张 → 均 `201`；`bare_metal_id` 相同、`id` 不同。
- **AC-10（纯文本往返）**：含中文 / 点号 / 连字符的 `name` 按字面值读出；枚举按内部字面值存取，不做中文转换或归一化。
- **AC-11（未定义约束不实现）**：`name` 无长度 / trim / 空串 / 字符 / `/` 校验；空串与含首尾空白不被拒绝。不得被解读为已确认「空 name 合法」。
- **AC-12（NIC 名称唯一性不由本 Feature 裁定）**：F004 不实现、不承诺任何 NIC 名称唯一性校验。该「不实现」是未确认状态的后果，不得被解读为「同名合法」是已确认规则。

### 无状态

- **AC-13（无状态）**：请求 / 响应 / 表 / 端点 / 查询参数中不存在 `status` 字段、枚举、默认值或过滤；不存在读写 NIC 状态的路径。

### 查询

- **AC-14（列表、分页、Empty）**：`GET /api/network-interfaces` → `200` + `{items,total,page,page_size}`；无活跃 NIC 时 `items == []`、`total == 0`，不得 404。
- **AC-15（详情 Not Found）**：不存在或已逻辑删除的 `id` → `404 NOT_FOUND`（不区分）。
- **AC-16（按 BareMetal 限定读取，Empty 与 Not Found 可区分）**：父不存在或已删 → `404`；父存在但无活跃 NIC → `200` + `items == []`；只返回该父的活跃 NIC。
- **AC-17（列表 / 详情排除已删）**：绕过应用层预置 `deleted_at` 后，该行不出现在列表 `items` / `total`；按 `id` → `404`。

### 维护

- **AC-18（枚举字段可维护）**：`PATCH` 携带合法 `technology_type` 和 / 或 `purpose` → `200` 返回新值；再次读取得同一值；缺省字段不变。
- **AC-19（维护路径枚举校验等同创建路径）**：非法枚举 → `400` + `details[].field`，不产生写入；DB `CHECK` 为最终权威——绕过应用层直写非法值被拒。
- **AC-20（更新 schema 封闭）**：`PATCH` 含未识别字段（含 `id` / `deleted_at` / `bare_metal_id` / `name` / `created_at`）→ `400`；空 body `{}` → `400`；`name` 与父绑定本次**不可变**。

### 删除与生命周期

- **AC-21（NIC 逻辑删除）**：`DELETE`（活跃行）→ `204` 无响应体；行仍物理存在且 `deleted_at` 非空；不出现在列表 / 详情。
- **AC-22（删除不级联）**：删除 NIC 后，父 BareMetal 的 `deleted_at` / `hostname` / `cluster_id` / `status` / `updated_at` **逐字段不变**；无其它行被修改或物理删除。
- **AC-23（不提供恢复 / 批量）**：不存在 restore / undelete / purge / 批量删除 / `include_deleted`。
- **AC-24（已删释放唯一性——适用性说明）**：NIC 当前无已确认唯一性规则（NQ-2）；本 AC 仅要求软删后不产生任何新的唯一性约束行为，且已删行 `deleted_at` 不被改写。

### F014 父删子拦真实端到端

- **AC-25（父有活跃 NIC → 拒绝删除宿主）**：`DELETE /api/bare-metals/{id}` → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`；宿主 `deleted_at` 仍为 NULL（无部分写入）。
- **AC-26（软删 NIC 后宿主可删）**：先软删该宿主全部活跃 NIC（及其它活跃子资源），再 `DELETE` → `204`；可证明 NIC 是阻断来源。
- **AC-27（并发孤立记录不变式 = 0 行）**：并发「创建 NIC」与「删除其宿主」后，`SELECT count(*) FROM network_interfaces nic JOIN bare_metals bm ON bm.id = nic.bare_metal_id WHERE nic.deleted_at IS NULL AND bm.deleted_at IS NOT NULL` 必须为 **0**。
- **AC-28（创建侧对父行取共享锁）**：创建 NIC 时必须对父 BareMetal 行取共享锁并同事务确认活跃；未命中 → 拒绝创建。
- **AC-29（宿主活跃子检查点包含 NIC 且被真实消费）**：`BARE_METAL_ACTIVE_CHILD_CHECKS` **非空**且**同时包含**活跃 VM 检查（F006 既有）与活跃 NIC 检查；被宿主删除路径真实消费。
- **AC-30（NIC 自身检查点显式声明）**：存在显式声明的 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`（当前空元组，代表「IPAddress 表尚不存在」而非「NIC 无子资源」），且 NIC 删除路径**真实传入**；F005 须追加「活跃 IPAddress」检查。

### 边界与前端

- **AC-31（不承载任何 IP 语义）**：不注册 IP 端点、不创建 `ip_addresses` 表、NIC 请求 / 响应 / 表结构中不存在 IP 字段或为 IP 唯一性服务的 `cluster_id` 列；NIC 删除当前不被 IP 拦截（归 F005）。不得因此认为「NIC 永远无子资源」。
- **AC-32（不越界到 VM / Container / Service / Cluster 视角）**：不注册这些端点；表不含指向这些实体的结构，也不含 VM 归属列；Cluster 视角与聚合视图归 F009 / F010。
- **AC-33（无未确认字段 / 无自动发现）**：不存在 MAC / 速率 / MTU / 光模块 / 端口 / 自动发现 / 外部平台同步字段或端点。
- **AC-34（前端三态与 Empty / Not Found 可区分）**：三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code` 分支（不解析 `message`）；`409` / `404` / `401` 分别处理；前端不得自行实现业务守卫。

---

## 与既有 Feature 的边界

| Feature | 边界 |
|---|---|
| F001 Cluster | NIC 的 Cluster 归属通过 BareMetal 推导，不单独记录；F004 不读写 Cluster。 |
| F002 BareMetal | F004 只消费「存在且活跃」判定，并向其活跃子检查声明**追加** NIC 检查（保留既有 VM 检查）。 |
| F005 IPAddress | IP 实体 / 字段 / 唯一性 / IP→NIC 绑定 / `cluster_id` 受控写入均归 F005。F004 不定义、不记录任何 IP；只提供挂载点与检查点追加位置。 |
| F006 VirtualMachine | VM 实体归 F006；「VM 是否拥有独立 NIC」为未确认（NQ-1），F004 不裁定，只交付 BareMetal 绑定。 |
| F007 / F008 | 无关系。 |
| F009 Cluster 视角查询 | 归 F009；F004 不提供 Cluster 视角或 `by-name` 别名。 |
| F010 关联查询 | 聚合视图归 F010；F004 交付 NIC 列表 / 详情 + 可复用的按父限定读取（形态见 NQ-6）。 |
| F011 Excel 导入 | 归 F011；导入须复用 F004 的同一套领域校验。 |
| F014 逻辑删除 | 机制归 F014；F004 是消费方 + 义务方。 |

---

## Assumptions

1. F004 复用 F012/F013/F014/F002/F006 已交付基座。
2. F004 **新增** `network_interfaces` 表与增量 migration（当前 head 为 F006 的 migration；实际版本号由 Database 裁定）；`database: true`。
3. `PATCH` 可变字段仅为 `technology_type` 与 `purpose`；`name` 与父绑定默认不可变。
4. 父引用以 BareMetal `id` 表达。
5. NIC 不提供任何 `by-name` 别名。
6. `name` 的未定义约束不实现、不承诺（`/` 禁令仅针对 Cluster 名称）。
7. 系统当前无 NIC 数据，无历史迁移。
8. 前端沿用无 `vue-router` 现状。
9. `page_size` 默认 50 / 上限 200 沿用既有约定。
10. 契约落点为**新增** `docs/api/f004-network-interface.md`。

---

## Proposed Rules

- **PROPOSED-1（需用户裁定）**：NIC `name` 在同一 BareMetal 内是否唯一（若唯一是否区分大小写）。当前未确认且不得设唯一约束；F004 按「不实现」交付（AC-12）。若确认唯一，属新增产品规则。
- **PROPOSED-2（需用户裁定）**：`Other` 是否需要伴随自由文本。R-NIC-001/002 已确认封闭集合且无伴随字段；F004 默认不实现（AC-05）。
- **PROPOSED-3（需用户裁定）**：`name` 与归属 BareMetal 在登记后是否可变。F004 默认不提供（NQ-3）。
- **PROPOSED-4（需用户裁定）**：`name` 的最小字符约束。当前未定义，F004 不得实现（AC-11）。

---

## Open Questions

### Blocking

**None。**

| 候选问题 | 为何不阻塞 F004 |
|---|---|
| NQ-1：VM 等是否拥有独立 NIC | F004 边界由已确认的 `NIC → BareMetal`（N:1 mandatory, CONFIRMED）唯一确定；「VM 拥有独立 NIC」不是已确认关系，若成立也只是**新增**一种载体绑定，不改 NIC→BareMetal 的强制性与基数。F004 不实现、不承诺、不预留多态载体选择器（AC-08 要求拒绝以 VM 为父）。 |
| NQ-2：NIC 名称是否同 BareMetal 内唯一 | `csm-v1-schema-design.md` 已裁定当前无唯一约束且「如需属 F004 产品确认后新增」——未确认时默认行为为「不实现」，行为单值。F004 以 AC-12 显式记录，不发明任何唯一性规则。 |
| NQ-3 name / 父绑定可变性 | 已显式移出本 Feature 范围；AC 不依赖其答案。 |
| NQ-4 `Other` 伴随自由文本 | R-NIC-001/002 已确认封闭集合且无伴随字段；不确认时行为单值。 |
| NQ-5 父不存在 / 已删的响应码 | 写入必须被阻止且不得 5xx 已是确定要求；具体码值属 API 契约可裁定项，AC-07 表述为「被阻止 + 无写入 + 非 5xx」。 |
| NQ-6 按父读取路由形态 / 归属 | F004 承诺提供可复用的按父限定读取并满足 R-QUERY-004；路径形态与 F010 归属由 Architecture / 协调器裁定。 |
| NQ-8 未定义约束 | 未确认时默认「不实现、不承诺」；AC-11 已固定该边界。 |

### Non-blocking

- **NQ-1（VM 等是否拥有独立 NetworkInterface）— 最高关注**：来源 R-NIC-003（`resolve_in_feature: F004`，`must_not_assume: 不得自动推导`）。影响：若确认，需新的载体绑定模型并可能改变唯一性（NQ-2）与 F010 聚合定义。建议由用户裁定「V1 中 NIC 只挂 BareMetal」或「VM 也可拥有独立 NIC」。裁定前 F004 交付 BareMetal 绑定且**不得**在 schema / 契约 / 前端预留 VM 载体字段或选择器。
- **NQ-2（NIC `name` 同宿主唯一性，及是否区分大小写）**：见 PROPOSED-1。F004 按「不实现」交付，并在计划元数据中记录。
- **NQ-3（`name` 与父绑定可变性）**：默认不提供（PROPOSED-3）。
- **NQ-4（`Other` 是否需伴随自由文本 / 中文映射）**：默认不实现；中文展示仅属 UI。
- **NQ-5（父不存在 / 已删的响应码）**：建议由 Architecture 在契约内裁定，与 F002 NQ-2 保持一致。
- **NQ-6（按父限定读取的路由形态与归属）**：由 Architecture / 协调器裁定。
- **NQ-7（PATCH 可变字段集合）**：当前固定为 `technology_type` + `purpose`。
- **NQ-8（`name` 未定义约束）**：不实现、不承诺。
- **NQ-9（F005 义务）**：F005 须向 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 追加「活跃 IPAddress」检查并补端到端。F004 建立该声明点与追加机制。
- **NQ-10（F011 复用 F004 校验）**：导入 NIC 行须复用同一套领域校验。
- **NQ-11（文档与计划元数据同步）**：`project-plan.yaml > F004.requirements` 建议补 `§15` / `§17` / `R-DELETE-004/005` / `§21` / `R-QUERY-004`；`open_questions` 承接 NQ-1~NQ-8；`csm-v1-schema-design.md` 的 NIC migration 版本号与实际对齐。
- **NQ-12（工程约定）**：模块布局、端点注册、路由声明顺序、前端交互形式由 Architecture / Backend / Frontend 决定。

---

## 变更影响

**对既有已确认规则：None。**

结构性影响：
1. `BARE_METAL_ACTIVE_CHILD_CHECKS` 从「仅活跃 VirtualMachine」**追加**「活跃 NetworkInterface」检查（既有 VM 检查必须保留）。
2. 新增 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS`（显式空元组），作为 F005 追加位置。
3. 新增 `network_interfaces` 表 → 表集合 guard、无 CASCADE guard、唯一软删写入路径 guard 应**增表演进**而非删除。
4. 新增两处封闭枚举 CHECK（`technology_type` / `purpose`）。

文档漂移需同步：`project-plan.yaml > F004`（requirements / AC / open_questions）；`domain-model.md` §8 建议显式说明「NIC 名称唯一性未确认」；`csm-v1-schema-design.md` migration 版本号；`requirements.md` §11 建议补 NIC→BareMetal 必选性的交叉引用。

---

## Architecture Handoff

1. **`network_interfaces` Schema 与增量 migration**：父列 `bare_metal_id NOT NULL` + FK `ON DELETE RESTRICT ON UPDATE RESTRICT`；`name TEXT NOT NULL`（无长度 / trim / 字符约束）；`technology_type TEXT NOT NULL` + `CHECK IN (...)`；`purpose TEXT NOT NULL` + `CHECK IN (...)`；`deleted_at`；**无 `status` 列**；**无** IP / MAC / 速率 / MTU 列；**无** VM 归属列；**明确不添加** `UNIQUE (bare_metal_id, name)`（NQ-2）。同步 `csm-v1-schema-design.md` 与实际 migration 版本号。不改既有基线 migration。
2. **端点集合与契约落点**：确认端点集合与封闭字段集合（AC-01），新建 `docs/api/f004-network-interface.md`；明确 `PATCH` 可变字段（NQ-7）与不可变字段（`name` / `bare_metal_id`）。
3. **创建路径的父存在性 / 活跃性与并发协议**：对父 BareMetal 行取 `FOR SHARE` 并确认活跃；FK 违规与「父不存在 / 已删」的响应码（NQ-5）；并发孤立记录不变式（AC-27/28）。
4. **封闭枚举落地与最终权威**：应用层字段级 `400` + DB `CHECK`；绕过应用层直写非法值被拒（`23514` 经通用映射 → `400`，永不 500），并以可失败 guard 固定两个枚举集合。
5. **无状态与字段边界的结构性保障**：可失败 guard 固定无 `status` 列 / 端点 / 过滤，且不存在 MAC / 速率 / MTU / IP / VM 归属字段或端点。
6. **未定义约束的「不实现」保障**：schema / ORM 层不隐式引入 `name` 校验或 `/` 禁令，以可失败 guard 固定。
7. **F014 端到端义务落点**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 追加活跃 NIC 检查（保留活跃 VM 检查）；交付 AC-25~AC-28 的端到端与并发测试；处理 F014 NOTE-01 的非空断言演进。
8. **NIC 自身活跃子检查声明位置**：建立 `NETWORK_INTERFACE_ACTIVE_CHILD_CHECKS` 与统一软删服务接线；明确 F005 追加机制（AC-30）。
9. **按父限定读取的路由形态与归属**：决定 `?bare_metal_id=` 与 / 或嵌套路径，明确 Empty / Not Found 判定位置与归属（NQ-6），保证 R-QUERY-004 且 F010 可复用。
10. **删除端点注册与依赖方向**：委托 F014 统一软删服务；不引入第二条软删路径、restore 或批量能力。
11. **读取路径活跃过滤**：复用 `app/db/active.py`。
12. **前端接线**：列表 / 详情 / 登记 / 维护 / 删除入口；三态与 Empty / Not Found；错误按 `error.code`；不重复实现业务守卫。
13. **交付层判定与既有 guard 演进**：确认 `database: true` 与 backend / frontend 层；同步 `project-plan.yaml > F004`；表集合 guard 随新表演进而非删除。
14. **NQ-1 / NQ-2 的「不预留」保障**：schema / 契约 / 前端不得为「VM 拥有独立 NIC」或「NIC 名称唯一」预留字段、参数或分支；以可失败 guard 记录当前边界。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。NQ-1（VM 是否拥有独立 NIC）与 NQ-2（NIC 名称唯一性）判定为 Non-blocking：未确认时的默认行为均为单值（不实现 / 不预留），不改变 CONFIRMED 的 NIC→BareMetal 关系，全部 AC 不依赖其答案。

GIT: NONE
