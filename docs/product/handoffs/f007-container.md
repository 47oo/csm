# Product Handoff — F007 Container 资源模型与登记

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-16
> Feature: F007（E03，P1，`depends_on: [F006, F002]` 均已 DONE）
> Product Source: `requirements.md` §10 / R-CONTAINER-001~005、§13/§15/§17/§21/§22/§23/Q-002、R-DELETE-004/005/006、R-QUERY-003/004；`domain-model.md` §3/§5.4/§6/§7.2/§8/§9；`domain-model.yaml > resources[Container]`、`relationships[Container-to-Hosts]`；ADR-0002/0003/0004/0005

---

## Feature

Container 资源模型与登记（F007）— V1 虚拟资源的第二个资源：**长期服务型 Container 实例**的人工登记、查询、可选字段维护与逻辑删除，以及 **Container → 运行载体（BareMetal 或 VirtualMachine，恰好一个）** 这一**多态必选关系**的产品落地与 F014 **双载体**父删子拦端到端。

## Problem

F002/F006 已让「集群 → 机器 → 虚拟机」成为可信事实，但运维人员日常运行的服务中有相当一部分**直接跑在裸金属或虚拟机上的长期容器实例**（如 `nginx`、`redis`、数据预处理服务）：它们不属于任何一台物理机也不等同于一台 VM，却必须能被回答「这个容器叫什么、跑在哪台机器 / 哪台 VM 上、属于哪个集群（由载体推导）」。

痛点：容器与载体、载体与集群的对应关系靠额外表格或口头维护；容器名在不同机器上重名时无法界定是「不同实例」还是「记录冲突」；容器下线时删行，历史一并丢失；「容器」这个词很容易触发「接入 K8s / Docker API / 运行时自动发现」的惯性（R-CONTAINER-001、§10、§23 明确排除）。

产品价值：**让「一个长期容器实例叫什么、跑在哪个载体上、属于哪个集群（推导）」成为可信、可维护的事实**，并为 R-DELETE-004 增加一条**多态载体**的真实业务端到端（BareMetal 与 VirtualMachine 两类载体都必须被活跃 Container 拦截），同时为 F008（Service 绑定 Container）提供唯一合法挂载点与删除守卫检查点。

---

## Confirmed Domain Rules

| 规则 | 内容 |
|---|---|
| R-CONTAINER-001 | V1 登记粒度为**长期服务型 Container 实例**；不登记短生命周期 / 临时容器；**不引入** Kubernetes workload（Pod / Deployment / DaemonSet 等）或更高层对象作为登记单位 |
| R-CONTAINER-002 | Container → 运行载体绑定**必选且恰好一个**；载体为 **BareMetal 或 VirtualMachine** 二选一；Cluster 归属由载体推导（BareMetal → 其 Cluster；VM → 其宿主 BareMetal → 其 Cluster），**不单独记录** |
| R-CONTAINER-003 | `name` 必填、身份标识；**同一运行载体内唯一**、不同载体可重名、比较**区分大小写**；已逻辑删除释放唯一性 |
| R-CONTAINER-004 | 可选字段 `image / cpu / memory / owner`：全部**可选**、**纯文本**、允许 `NULL`、**不结构化**、不构成登记阻断；不得因此引入自动资产发现或运行时同步 |
| R-CONTAINER-005 | 载体（BareMetal **或** VirtualMachine）存在活跃 Container 时**不得删除该载体**（R-DELETE-004）；逻辑删除 Container **不自动级联**（R-DELETE-005） |
| Q-002=B | Container **不设状态** |
| §21 | 非法资源关系、唯一性冲突必须在**保存前**由后端 / 数据库阻止 |
| §22 | 名称唯一性比较**区分大小写** |
| §17 / R-DELETE-001..006 | 软删不物理删；无恢复；父有活跃子不得删；不级联；已删释放唯一性 |
| R-QUERY-004 | 必须区分 **Resource Not Found（404）** 与 **Empty Relationship（200 + 空集合）** |
| ADR-0002/0003/0004/0005 | 大小写敏感 collation；partial unique index 为最终权威；`id` 为规范路径 + 列表信封 + `deleted_at` 不暴露；单一软删写入路径 + 父删子拦同事务加锁 + 活跃子检查由资源模块显式声明；`/api/*` 认证 |

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。** **存储表示（多态载体如何持久化）属 Architecture，不在本 Handoff 决定。**

---

## 目标与范围

### 本次包含

1. **登记**：`name` 必填 + **恰好一个**运行载体（BareMetal 或 VirtualMachine，存在且活跃）必填；四个可选字段。
2. **查询**：列表（分页）+ 详情；**按载体限定读取**（两种载体类型均成立），Empty / Not Found 按 R-QUERY-004 区分。
3. **可选字段维护**：`PATCH` 修改 `image / cpu / memory / owner`。
4. **逻辑删除**：委托 F014 统一软删服务，显式声明 `CONTAINER_ACTIVE_CHILD_CHECKS`。
5. **多态载体关系写入**：创建时校验载体**存在且活跃**、**类型与标识一致**、**恰好一个**。
6. **R-CONTAINER-003 唯一性落地**：同一载体内活跃 `name` 唯一、大小写敏感、软删释放；应用层 `409` + DB partial unique index 为最终权威。
7. **F014 双载体端到端义务**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 与 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` **同时**注入「活跃 Container」检查，交付两个载体类型的 `409` 端到端与并发孤立记录不变式。
8. **F008 父资源侧义务**：显式声明 `CONTAINER_ACTIVE_CHILD_CHECKS`（当前空元组）并在删除路径真实传入。
9. **前端**：列表 / 详情 / 登记 / 可选字段修改 / 删除入口；三态与 Empty / Not Found 可区分。
10. **读取路径软删过滤**：复用既有活跃过滤原语。

### 本次明确不包含

1. **Container 的状态**（Q-002=B）。
2. **Kubernetes / Docker API / Container Runtime 自动发现 / 同步 / 凭据 / 外部平台 id**（R-CONTAINER-001；§23）。
3. **K8s workload（Pod / Deployment / DaemonSet 等）**作为登记单位。
4. **Container 自身存储 `cluster_id`**（R-CONTAINER-002）。
5. **可选字段的结构化拆分**（`image` 不拆 registry/repo/tag；`cpu`/`memory` 不拆数量与单位；`owner` 不关联用户实体）。
6. **BareMetal / VirtualMachine 以外的载体**（Cluster / Service / NIC / IP 不得作为载体）。
7. **多载体绑定**（R-CONTAINER-002 `exactly_one`）。
8. **物理删除、Undelete / Restore、回收站、软删级联**。
9. **Container 的全局 `by-name` 只读别名**（`name` 仅载体内唯一，全局不可判定）。
10. **Container 级别的 NIC / IP / 状态 / 监控 / 健康**。
11. **R-QUERY-003 关联聚合视图**（F010）；**Cluster 视角成员视图**（F009）。
12. 其它资源自身的实体与端点（F001/F002/F004/F005/F006/F008）。
13. **Excel 批量导入**（F011）；**认证**（F013）。
14. **DataCenter / 位置模型**（§6、§13）。
15. **审计 / 历史 / 导出 / 排序 / 高级筛选 / 批量 / 标签 / 统计**。

### 本次未涉及

- `name` 与载体绑定的登记后可变性（NQ-1，默认不可变）；
- `name` 与可选字段的最小字符 / 格式约束（NQ-4，不实现）；
- 「长期服务型 vs 短生命周期」的可判别字段（NQ-5，**不引入**）；
- 宿主 BareMetal 改属 Cluster 后对推导归属的影响（NQ-3）；
- 按 Cluster 视角查看 Container（F009）；按 Service 反向查看 Container（F008 / F010）。

---

## Acceptance Criteria

### 登记（多态载体）

- **AC-01（以 BareMetal 为载体登记成功）**：`POST /api/containers` 携带 `name` + 一个存在且活跃的 BareMetal 载体（可附带可选字段）→ `201`；响应字段集合**恰为** `{id, <载体类型标识>, <载体标识>, name, image, cpu, memory, owner, created_at, updated_at}`；**不含** `deleted_at` / `status` / `cluster_id` / Cluster 维度字段 / K8s / Docker / 运行时 / 位置字段。
- **AC-02（以 VirtualMachine 为载体登记成功）**：同 AC-01，载体为一个存在且活跃的 VM → `201`，字段集合相同。
- **AC-03（`name` 必填）**：缺失或非字符串 → `400 VALIDATION_ERROR` + `details[].field == "name"`，不产生记录。
- **AC-04（载体必填——两者都不给）**：请求未表达任何载体 → `400 VALIDATION_ERROR` + `details[].field` 指向载体字段，不产生记录。
- **AC-05（拒绝多载体——两者都给）**：请求表达多于一个载体（同时给出 BareMetal 与 VM 载体，或给出载体列表）→ `400`，不产生记录。
- **AC-06（拒绝其它资源类型为载体）**：以 Cluster / Service / NIC / IP 作为载体，或请求体含指向这些实体的载体字段 / 载体类型选择值 → `400`（请求 schema 封闭），不产生记录。
- **AC-07（载体类型与载体标识必须一致）**：任何指代载体的输入都必须无歧义解析为**恰好一个类型明确、存在且活跃**的 BareMetal 或 VM。类型与标识不一致（标识实际指向另一类型）→ 写入被拒绝、不产生记录、**不得 5xx**。可测形式（取决于 Architecture 选定的载体表达方式）：
  - 以「载体类型 + 载体标识」表达：断言 VM 载体却传入真实 BareMetal 的标识 → 拒绝；
  - 以两个互斥字段表达：传入的标识必须在其断言类型集合内解析成功；仅存在于另一类型表的标识 → 拒绝。
- **AC-08（载体必须存在且活跃）**：引用不存在或已逻辑删除的载体（任一类型）→ 写入被拒绝、不产生记录、不得 5xx（响应码见 NQ-2）。
- **AC-09（可选字段缺失不阻断）**：不提供任何可选字段 → `201`，各字段响应为 `null`（返回 `null` 而非省略）。
- **AC-10（纯文本往返）**：含中文的 `name` 与可选字段按字面值读出；`cpu = "8 vCPU"`、`image = "registry/nginx:1.25"`、`memory = "4G"` 原样存取，**不拆分 / 不归一 / 不校验格式**。
- **AC-11（未定义约束不实现）**：`name` 与可选字段**无**长度 / trim / 空串 / 字符 / `/` 禁令 / 格式校验；空串与含首尾空白的 `name` **不被拒绝**。不得被解读为已确认「空 `name` 合法」或「`image` 格式合法」。`/` 禁令仅针对 Cluster 名称。

### 唯一性（同一载体内）

- **AC-12（同一载体内唯一，保存前阻止）**：载体 C 已有活跃 `web`，再在同一载体登记活跃 `web` → `409 CONFLICT` + `details[].field` 含 `"name"`，不产生第二条活跃记录。
- **AC-13（不同载体可重名——跨载体类型）**：BareMetal B 上登记 `web`，其某台 VM V 上登记 `web` → 均 `201`，不冲突。
- **AC-14（不同载体可重名——同类型不同标识）**：B1 与 B2（或 V1 与 V2）各自登记 `web` → 均 `201`。
- **AC-15（跨载体类型即使标识数值相同也不冲突）**：BareMetal `id=5` 与 VM `id=5` 上各登记 `web` → 均 `201`。**载体身份 = （类型, 标识）二元组**；类型不同即载体不同。
- **AC-16（唯一性边界不得与 R-VM-004 混用）**：存在名为 `web` 的 VM 时，在该 VM 上登记名为 `web` 的 Container → `201`；在多个不同载体上登记同名 Container → 均 `201`（Container 无全局唯一）。该「不冲突」不得被解读为削弱 R-VM-004：VM 名称仍全局唯一。
- **AC-17（大小写敏感）**：同一载体内 `web` 与 `WEB` 可共存为两条活跃记录；不存在 `lower(name)` 唯一索引或大小写折叠。
- **AC-18（保存前阻止，DB 为最终权威）**：绕过界面直接调用 API 得到同一 `409`；绕过应用层直接对 DB 插入同一载体上重复的活跃 `(载体, name)` 被数据库拒绝。
- **AC-19（soft delete 释放唯一性）**：软删载体 C 上的 `web` 后，可在同一载体 C 重新登记 `web` → `201`；旧已删行保留且 `deleted_at` 未被改写。
- **AC-20（唯一性边界是载体而非 Cluster）**：同一 Cluster 下两台不同 BareMetal 上各自登记 `web` → 均 `201`；唯一性**不按 Cluster**限定。

### Cluster 归属推导

- **AC-21（不存 `cluster_id`）**：Container 的请求体、响应体、表结构与查询参数中**不存在** `cluster_id` / `cluster` / `cluster_name` 字段或过滤参数；不存在任何读写 Container Cluster 归属的路径。
- **AC-22（归属由载体决定，且仅以载体表达）**：读取详情可观察到其**载体绑定（类型 + 标识）**；Cluster 归属**只能**由载体推导，系统**不持久化** Container 的 Cluster 归属。正向的「按 Cluster 列出 Container」视图归 F009 / F010。

### 无状态

- **AC-23（无状态）**：请求体、响应体、表结构与端点上**不存在** `status` 字段、枚举、默认值或状态过滤参数。

### 查询

- **AC-24（列表、分页、Empty）**：`GET /api/containers` → `200` + `{items,total,page,page_size}`；无活跃 Container 时 `items == []`、`total == 0`，不得 `404`。
- **AC-25（详情 Not Found）**：不存在或已逻辑删除的 `id` → `404 NOT_FOUND`（不区分）。
- **AC-26（按载体限定读取，Empty 与 Not Found 可区分，两种载体类型均成立）**：载体**存在**但无活跃 Container → `200` + `items == []`（**Empty**）；载体**不存在或已逻辑删除** → `404 NOT_FOUND`；只返回该载体的活跃 Container。对 BareMetal 与 VM 载体**均**成立。（路由形态见 NQ-6；须供 F010 复用。）
- **AC-27（列表 / 详情排除已删）**：绕过应用层预置 `deleted_at` 非空 Container 后——不出现在列表 `items` / `total` 与按载体限定读取结果中；按 `id` → `404`。

### 维护

- **AC-28（可选字段可更新）**：`PATCH` 提供合法可选字段 → `200` 返回新值；`null` 表示清空；缺省字段不变；再次读取一致。
- **AC-29（更新 schema 封闭）**：`PATCH` 含未识别字段（含 `id` / `deleted_at` / `cluster_id` / `status` / 载体字段 / `name`）→ `400`；空 body `{}` → `400`；`name` 与载体绑定**默认不可变**（NQ-1）。

### 删除与生命周期

- **AC-30（Container 逻辑删除）**：`DELETE`（活跃行）→ `204` 无响应体；该行仍物理存在且 `deleted_at` 非空；不出现在列表 / 详情。
- **AC-31（删除不级联，两种载体类型）**：删除 Container 后，其载体（BareMetal **或** VM）的 `deleted_at` / `updated_at` / 各字段**逐字段不变**；无其它资源行被修改或物理删除。
- **AC-32（不提供恢复 / 批量能力）**：不存在 restore / undelete / purge / 批量删除 / `include_deleted`。

### F014 父删子拦真实端到端（两个载体类型）

- **AC-33（BareMetal 有活跃 Container → 拒绝删除宿主）**：`DELETE /api/bare-metals/{id}` → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`；该 BareMetal 行 `deleted_at` **仍为 NULL**。
- **AC-34（VirtualMachine 有活跃 Container → 拒绝删除 VM）**：`DELETE /api/virtual-machines/{id}` → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`；该 VM 行 `deleted_at` **仍为 NULL**。
- **AC-35（软删 Container 后载体可删，两种类型）**：先软删该载体下全部活跃 Container（及其它活跃子资源），再删除载体 → `204`；可证明 Container 是阻断来源之一。
- **AC-36（并发孤立记录不变式 = 0 行，BareMetal 载体）**：并发「创建 Container」与「删除其 BareMetal 载体」后，`SELECT count(*) FROM containers c JOIN bare_metals bm ON <Container 指向 BareMetal 的载体引用> = bm.id WHERE c.deleted_at IS NULL AND bm.deleted_at IS NOT NULL` = **0**。
- **AC-37（并发孤立记录不变式 = 0 行，VM 载体）**：同上，JOIN `virtual_machines vm` = **0**。
- **AC-38（创建侧对载体行取共享锁）**：创建 Container 时必须对**被选中的载体行**（按类型）取共享锁并同事务确认活跃；未命中 → 拒绝创建（不留无主 Container）。
- **AC-39（BareMetal 活跃子检查点包含 Container 且被真实消费）**：`BARE_METAL_ACTIVE_CHILD_CHECKS` 非空且**同时包含**活跃 VM（F006）、活跃 NIC（F004）与**活跃 Container（F007）**；被删除路径真实消费。
- **AC-40（VM 活跃子检查点由空变非空且包含 Container）**：`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` **非空**且包含「活跃 Container」检查；被 VM 删除路径真实消费（F006 AC-29 的预留追加位置由此落地）。
- **AC-41（Container 自身检查点显式声明）**：存在显式声明的 `CONTAINER_ACTIVE_CHILD_CHECKS`（当前空元组——代表「Service 表尚不存在」而非「Container 无子资源」），且删除路径**真实传入**；F008 须追加「活跃 Service」检查。

### 边界与前端

- **AC-42（不引入 K8s / Docker / 运行时）**：不存在 Kubernetes / Docker API / Runtime 客户端、凭据、外部平台 id、同步 / 发现字段或端点；表与契约中不存在 Pod / Deployment / DaemonSet 等 workload 对象或归属字段。
- **AC-43（不越界到其它资源）**：不注册 Cluster / BareMetal / VM / NIC / IP / Service 端点；`containers` 表不含指向 Cluster / NIC / IP / Service 的载体或归属结构（Service↔Container 绑定表归 F008），也不含 DataCenter / 位置字段；请求 schema 不接受以这些实体为载体（AC-06）。
- **AC-44（前端三态与 Empty / Not Found 可区分）**：三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`（必要时结合 `details[].code`）分支，不解析 `message`；`409`/`404`/`401` 分别处理；前端不得自行实现业务守卫。

---

## 与既有 Feature 的边界

| Feature | 边界 |
|---|---|
| F001 Cluster | Container 的 Cluster 归属通过载体推导，不单独记录；F007 不读写 Cluster。 |
| F002 BareMetal | F007 只消费「存在且活跃」判定，并向 `BARE_METAL_ACTIVE_CHILD_CHECKS` **追加**活跃 Container 检查（保留 F006 活跃 VM、F004 活跃 NIC 检查）。 |
| F004 NetworkInterface | 无直接关系；两者的删除守卫并列存在于 `BARE_METAL_ACTIVE_CHILD_CHECKS`，互不影响。 |
| F006 VirtualMachine | Container **可以**以 VM 为载体；F007 使 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 由显式空元组变为非空。VM 全局名称唯一（R-VM-004）与 Container 载体内唯一**严格分离，不得混用**。 |
| F008 Service | Service **可绑定 Container** 作为运行载体，属 F008。F007 只提供 Container 实体与 `CONTAINER_ACTIVE_CHILD_CHECKS` 声明点；F008 落地时追加「活跃 Service」，使「Container 被活跃 Service 绑定时不得删除」生效。F007 不定义 Service 与绑定表。 |
| F009 Cluster 视角查询 | 归 F009；F007 不提供 Cluster 视角与 `by-name` 别名。 |
| F010 关联查询 | 聚合视图归 F010；F010 **必须复用** F007 的按载体限定读取能力（AC-26），不得另写一份过滤。 |
| F011 Excel 导入 | 归 F011；导入 Container 行须复用 F007 同一套领域校验。 |
| F014 逻辑删除 | 机制归 F014；F007 是**消费方 + 义务方**（AC-30~AC-41）。 |

---

## Blocking Questions

**None.**

- **不确认就无法确定范围？** 否。F007 的范围由 R-CONTAINER-001~005 + R-DELETE-* + R-QUERY-004 + 已批准 ADR / 交接完全确定；AC-01~AC-44 全部可判定，不依赖 NQ-1~NQ-10 任何一项。
- **是否导致两种明显不同的用户行为？** 各项 NQ 在未确认时 F007 的行为均为**单值**（默认不实现 / 不预留 / 由 Architecture 在契约内裁定并保持既有先例），不产生 F007 内部行为分叉；若被裁定，都是**未来范围的加性扩展**。
- **是否改变核心领域关系？** 否。`Container → 载体`（两张表二选一、恰好一个）已由 R-CONTAINER-002 确认。
- **是否导致 AC 无法定义？** 否。

---

## Open Questions

- **NQ-1（`name` 与载体绑定的登记后可变性）**：UNCONFIRMED。默认**不提供**（AC-29 声明不可变）；变更由「软删 + 重新登记」替代。属未来范围新增。
- **NQ-2（引用不存在 / 已软删载体的响应码）**：写入必须被阻止且不得 5xx 已是确定要求；`400` 还是 `404` 未固定。**建议**：由 Architecture 裁定，与 F002 / F006 / F004 已确立的 `404 NOT_FOUND` 先例一致。AC-08 表述为「被阻止 + 无写入 + 非 5xx」。
- **NQ-3（宿主 BareMetal 改属 Cluster）**：若载体的 Cluster 归属在登记后可变（该能力本身未确认），Container 推导出的归属将随之改变；但 R-CONTAINER-002 明确 Container **不存 `cluster_id`**，F007 无任何持久化字段需要维护。**不自行裁定**；保持「不持久化」，连带影响待相关能力确认时另行裁定。
- **NQ-4（`name` 与可选字段的未定义约束）**：长度 / trim / 空串 / 非法字符 / `/` 禁令 / 格式均未定义。**不实现、不承诺**（AC-11）。
- **NQ-5（「长期服务型」无判别字段）**：R-CONTAINER-001 是**登记粒度规则**，当前**未确认任何可判别字段**。F007 **不引入**任何判别字段或校验。
- **NQ-6（按载体限定读取的路由形态与归属）**：形态由 Architecture 裁定；须保证 F010 可复用。
- **NQ-7（Container `by-name` 只读别名）**：默认**不提供**。
- **NQ-8（文档与计划元数据漂移，需同步；非产品规则冲突）**：
  1. `domain-model.yaml > relationships[Container-to-Hosts]` 仍 `binding_state: UNCONFIRMED` / `cardinality: UNCONFIRMED` / `must_not_assume: 不得默认绑定为必选` → 应更新为 `mandatory: true`、`selector: exactly_one`、`binding_state: CONFIRMED`。
  2. `open_questions[OPEN-002]` 仍 `status: OPEN` → 应标记 `CLOSED_RESOLVED`（2026-09-16，R-CONTAINER-001~005）。
  3. `must_not_assume` 仍含「容器绑定运行载体是必选的」→ 应移除。
  4. `domain-model.md` §8 未收录「Container `name` 载体内唯一」→ 建议补录；§6 仍将 Container→载体列为未确认，与 §5.4 矛盾，以 §5.4 为准。
  5. `csm-v1-schema-design.md` 第 442/731/892 行「Container → 载体 未确认 / **不得**固化为 `NOT NULL`」→ 已被 R-CONTAINER-002 取代（载体必选且恰好一个；**具体表示法**仍由 Architecture 决定）。
  6. `project-plan.yaml > F007` 元数据待补。
- **NQ-9（F008 义务）**：F008 须向 `CONTAINER_ACTIVE_CHILD_CHECKS` 追加「活跃 Service」检查并补端到端。
- **NQ-10（F011 复用校验）**：F011 导入 Container 行须复用同一套领域校验。

---

## Architecture Handoff

1. **多态载体关系的技术表示**：如何在 Schema 与契约层表达「恰好一个载体，且为 BareMetal 或 VirtualMachine 二选一」——例如类型判别列 + 载体标识（配合「两列择一非空」的约束），或两个可空 FK 加 CHECK 等。需保证：多载体**不可表达 / 不可写入**、载体类型与标识一致、**无 CASCADE**（`ON DELETE RESTRICT`）、且**不新增 `cluster_id` 列**。**具体表示由 Architecture 决定**；本 Handoff 只给出必达语义（AC-04~AC-08）。
2. **`containers` Schema 与增量 migration**：`name NOT NULL`（无长度 / trim / 字符约束）；`image / cpu / memory / owner` 四个可空 `TEXT`；载体引用按 §1 表示；`deleted_at`；**无 `status` 列**；**无 `cluster_id` 列**。唯一性为 **(载体类型, 载体标识, name) 上的 partial unique index**（predicate `deleted_at IS NULL`，大小写敏感，不声明 `COLLATE`，不用 `lower()`）。不改既有基线 migration；同步 `docs/database/**`（含 NQ-8 漂移）。
3. **端点集合与契约落点**：确认端点集合（预期 5 个）与资源表示的**封闭字段集合**（AC-01/02/21/23），新建 `docs/api/f007-container.md` 作为唯一权威；明确 `PATCH` 可变字段（四个可选字段）与不可变字段（`name` / 载体绑定）。
4. **创建路径的载体存在性 / 活跃性 / 类型一致性与并发协议**：对**被选中载体行**（BareMetal 或 VM）取 `FOR SHARE` 并同事务确认活跃；「载体不存在 / 已删 / 类型不一致」的响应码（NQ-2）；并发孤立记录不变式（AC-36/37/38）。
5. **R-CONTAINER-003 唯一性落地**：应用层 `409`（`details[].code = "DUPLICATE"`、`field = "name"`）+ partial unique index（含载体类型维度）；不引入大小写折叠。
6. **F014 双载体端到端义务落点**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS` 与 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` **同时**追加活跃 Container 检查（保留既有检查），交付 AC-33~AC-38 的端到端与并发测试；处理 F014 NOTE-01 的非空断言演进（`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 由空变非空）。
7. **Container 自身活跃子检查声明位置**：建立 `CONTAINER_ACTIVE_CHILD_CHECKS`（显式空元组）与统一软删服务接线；明确 F008 追加机制（AC-41）。
8. **按载体限定读取的路由形态与归属**：决定 `?carrier_*` / `?bare_metal_id=` / `?virtual_machine_id=` 或嵌套路径，明确 Empty / Not Found 判定位置（NQ-6），保证 R-QUERY-004 且 F010 可复用。
9. **无状态与字段 / 边界保障**：以可失败 guard 固定「无 `status` 列 / 无状态端点 / 无状态过滤」「无 `cluster_id` 列 / 无 Cluster 维度过滤」「无 K8s / Docker / 运行时 / 位置字段」「四个可选字段不被结构化拆分」。
10. **未定义约束的「不实现」保障**：确认 schema / ORM / 契约层不隐式引入 `name` 或可选字段的长度 / trim / 空串 / 字符 / `/` 校验，也不引入「长期服务型」判别字段（NQ-4/NQ-5），并以可失败 guard 固定。
11. **删除端点注册与依赖方向**：Container 模块注册 `DELETE` 并委托 F014 统一软删服务；不引入 restore / 批量 / 第二条软删路径。
12. **读取路径活跃过滤**：复用 `app/db/active.py`，不新写谓词。
13. **前端接线**：列表 / 详情 / 登记（含载体选择）/ 可选字段修改 / 删除入口；错误按 `error.code`；不重复实现业务守卫。
14. **交付层判定与既有 guard 演进**：确认 `database: true` 与 backend / frontend 层；新增 `containers` 表 → 表集合 guard **增表演进**（不得删测试）；同步 `project-plan.yaml > F007`。

---

## 变更影响

**对既有已确认规则：None。**

结构性影响：
1. `BARE_METAL_ACTIVE_CHILD_CHECKS` 从「活跃 VM（F006）+ 活跃 NIC（F004）」**追加**「活跃 Container」检查。
2. `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 从**显式空元组**变为**非空**，包含「活跃 Container」检查。
3. 新增 `CONTAINER_ACTIVE_CHILD_CHECKS`（显式空元组），作为 F008 追加位置。
4. 新增 `containers` 表 → 表集合 guard、无 CASCADE guard、唯一软删写入路径 guard 应**增表演进**而非删除。
5. 新增一处含载体类型的 partial unique index（载体内 `name` 唯一）。

文档漂移需同步（详见 NQ-8）：`domain-model.yaml`（relationship / OPEN-002 / must_not_assume）、`domain-model.md` §6/§8、`csm-v1-schema-design.md` 第 442/731/892 行、`project-plan.yaml > F007`。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。多态载体语义、载体内唯一性的跨载体类型边界、Cluster 归属推导、字段集合、载体绑定与 `name` 的登记后默认不可变性、以及 F014 双载体义务均已给出**可判定**的产品边界与 AC；NQ-1~NQ-10 均为 Non-blocking（未确认时行为单值，且均为未来范围的加性扩展）。

GIT: NONE
