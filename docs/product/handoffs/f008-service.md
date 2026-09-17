# Product Handoff — F008 Service 资源管理与 Cluster 共享关联

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-16
> Feature: F008（E04，P1，`depends_on: [F001, F002, F006, F007]` 均已 DONE）
> Product Source: `requirements.md` §14 / R-SVC-001~009、§13/§15/§17/§21/§22/§23/Q-002、R-DELETE-001~006、R-QUERY-003/004；`domain-model.md` §3/§5.5/§6/§7.2/§8/§9；`domain-model.yaml > resources[Service]`、`relationships[Service-to-Hosts / Service-to-Cluster]`；ADR-0002/0003/0004/0005

---

## Feature

Service 资源管理与 Cluster 共享关联（F008）— V1 服务资源的**人工登记、查询、可选字段维护与逻辑删除**，其 **Service → 运行载体（BareMetal / VirtualMachine / Container，N:M，必选）** 绑定关系的产品落地，以及 **Cluster 共享语义（由运行载体归属推导、不落 `service.cluster_id`）** 与 **F014 三载体父删子拦端到端**。

## Problem

F001~F007 完成后，集群、裸金属、网络接口 / IP、虚拟机、容器都已是可信事实，但「**运维需要统一管理的服务**」（调度服务、存储服务、监控采集服务、共享推理服务等）仍只存在于口头约定或额外表格中。运维人员无法回答：这个服务叫什么、谁负责、访问地址与端口是什么？跑在哪些机器 / VM / 容器上？某个服务被哪些集群共用？

**痛点**：服务与运行载体的对应关系靠额外表格维护；多个集群共用同一服务时被**重复建多条互不相干的记录**，导致「同一个服务」在系统里被拆成多份事实；服务下线时直接删行，历史丢失；「服务」这个词又极易触发「接入监控 / 健康检查 / 凭据管理 / 状态采集」的惯性（R-SVC-007、Q-002=B、§23 明确排除）。

**产品价值**：让「**一个服务叫什么、跑在哪些载体上、因此被哪些集群共用**」成为可信、可维护、**只登记一次**的事实；并为 R-DELETE-004 增加一条**三载体类型**的真实业务端到端，把 F007 预留的 `CONTAINER_ACTIVE_CHILD_CHECKS` 追加点真正落地。

---

## Confirmed Requirements

### 字段与登记（R-SVC-001 / R-SVC-007 / Q-002=B）

| 项 | 确认内容 |
|---|---|
| `name` | **必填**，自由文本，服务名称 / 身份标识 |
| `service_type` | 可选、自由文本；**不强制固定分类**（R-SVC-001 / R-SVC-007） |
| `url` / `port` / `protocol` / `owner` / `description` | 均为**可选、纯文本、允许 `NULL`** |
| 字段集合 | **恰为** `name` + 上述 6 个字段；**不含** `credential_reference`、`health_information` |
| 状态 | Service 在 V1 **不设状态**（Q-002=B） |
| Cluster 归属 | **不存 `service.cluster_id`**；关联由运行载体的 Cluster 归属**推导**（R-SVC-004 / R-SVC-006） |

### 绑定关系（R-SVC-002 ~ R-SVC-006）

- Service **必须绑定运行载体**：不允许存在未绑定任何运行载体的 Service（R-SVC-005）。
- 可绑定载体为 **BareMetal / VirtualMachine / Container** 三类。
- 一个 Service **可以绑定多个**运行载体；一个 Service **可以被多个 Cluster 共享**，通过绑定跨 Cluster 的多个运行载体实现（R-SVC-002 / R-SVC-006）。
- **共享服务只能登记一次**；不得因多个 Cluster 使用而复制成多条独立 Service（R-SVC-003）。
- Service 与 Cluster 的关联**不是直接绑定**，而是推导；模型须能表达 N:N Cluster 或等价语义（R-SVC-003；具体实现由 Architecture 决定）。

### 唯一性与生命周期（R-SVC-008 / R-SVC-009 / R-DELETE-*）

- `name` 在所有**当前有效 Service** 范围内**全局唯一**、比较**区分大小写**（R-SVC-008、§22）；已逻辑删除的 Service 释放该唯一性（R-DELETE-006）。
- 绑定了**活跃 Service** 的运行载体（BareMetal / VirtualMachine / Container），在其仍被该 Service 绑定时**不得删除**（R-SVC-009 = R-DELETE-004 的泛化）。
- 逻辑删除 Service **不自动级联**删除其运行载体或其它资源（R-DELETE-005）。

### 一致性与查询（§21 / §22 / R-QUERY-004）

- 非法资源关系、唯一性冲突必须在**保存前**由 Backend / Database 阻止，不能只依赖 UI（§21）。
- 查询必须区分 **Resource Not Found（404）** 与 **Empty Relationship（200 + 空集合）**（R-QUERY-004）。
- 名称比较区分大小写（§22）。

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。** 存储表示（`services` 表与 N:M 绑定表形态）、端点形态与契约词汇属 Architecture。

**重要对照（防止实现者混用）**：`Service.name` 唯一性边界是 **全局**（跨 Cluster、跨载体、跨载体类型），与 **`Container.name` 的「同一载体内唯一」**（R-CONTAINER-003）**语义相反**，与 `VirtualMachine.name`（全局唯一，R-VM-004）、`Cluster.name`（全局唯一，R-CLUSTER-002）同类。不得对 Service 施加「载体内唯一」「按 Cluster 唯一」的任何变体。

---

## 目标与范围

### 本次包含

1. **登记（含必选绑定）**：`name` 必填 + **至少一个运行载体**（BareMetal / VirtualMachine / Container，均须存在且活跃），可选字段 6 个。
2. **N:M 绑定语义**：同一 Service 绑定多个载体；同一载体被多个 Service 绑定；跨 Cluster 的载体集合 = 该 Service 被多个 Cluster 共享的落地方式，且**只登记一条 Service**。
3. **查询**：列表（分页）+ 详情 + **按载体限定读取**（三种载体类型均成立），Empty / Not Found 按 R-QUERY-004 区分。按载体限定读取为 F010 履行 R-QUERY-003 的**复用前提**。
4. **可选字段维护**：`PATCH` 修改 6 个可选字段。
5. **逻辑删除**：委托 F014 统一软删服务；软删**不级联**；软删后释放 `name` 唯一性、且**不再阻止**其原载体删除。
6. **R-SVC-008 唯一性落地**：全局活跃 `name` 唯一、大小写敏感、软删释放；应用层 `409` + DB partial unique index 为最终权威。
7. **Cluster 归属推导语义落地**：不落 `service.cluster_id`，不返回、不可过滤 Cluster 维度。
8. **F014 三载体端到端义务**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS`、`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS`、`CONTAINER_ACTIVE_CHILD_CHECKS` **三者**注入「被活跃 Service 绑定」检查（保留既有检查），并交付三载体类型的 `409` 端到端与并发孤立记录不变式。
9. **前端**：列表 / 详情 / 登记（含载体选择，可多选，至少一项）/ 可选字段修改 / 删除入口；三态与 Empty / Not Found 可区分。

### 本次明确不包含

1. **Service 的状态**（Q-002=B）。
2. **`credential_reference`（凭据引用）**（R-SVC-007 明确不属 V1）。
3. **`health_information`（健康信息）**（R-SVC-007；Q-002=B）。
4. **Service 自身存储 `cluster_id` / Cluster 维度字段 / 过滤参数**（R-SVC-004 / R-SVC-006）。
5. **Cluster → Service 视角视图**（R-QUERY-003 归 F010）。
6. **监控 / 健康检查接入、告警、实时状态采集**。
7. **自动资产发现 / 服务发现 / 外部平台同步**（§23）。
8. **Service 与 Cluster 的直接绑定**。
9. **物理删除、Undelete / Restore、回收站、软删级联**。
10. **DataCenter / 位置模型**；**复杂 RBAC**；**Excel 批量导入**（F011）；**审计 / 历史 / 导出 / 统计 / 标签 / 批量操作**。

### 本次未涉及

1. **绑定变更**（登记后追加 / 解除 / 替换运行载体）—— 含「解除全部绑定」与「零载体 Service」的边界（**范围敏感，NQ-01**）。本次按项目先例（F002 NQ-3 / F006 NQ-1 / F007 NQ-1）默认**不提供**。
2. **`name` 登记后重命名**（NQ-02）。
3. **`by-name` 只读别名**（NQ-03）。
4. **同一请求内重复给出同一载体**的去重 / 拒绝语义（NQ-04）。
5. **读取中返回推导出的 Cluster 归属**（NQ-05）。
6. **数据层对「零载体活跃 Service」的硬约束机制**（触发器 / 跨行约束，NQ-06）。
7. **排序 / 高级筛选 / 搜索**；**Excel 模板中的 Service 行与 N:M 载体表达**（F011，NQ-08）。
8. **Service 与 NetworkInterface / IPAddress 的关联**（§15 未定义该关系）。

---

## Acceptance Criteria

> 响应字段名与路由形态由 Architecture 契约确定，AC 只约束**语义**；但载体表达必须使用**类型 + 标识**二元组，且类型取值为**封闭三值集合**（与 F007 `carrier_type` 词汇一致并扩展 `CONTAINER`）。

### A. 登记与「必选绑定」

- **AC-01（以 BareMetal 为载体登记成功）**：`POST` 携带 `name` + 一个存在且活跃的 BareMetal 载体 → `201`；响应含 `name` 与该载体绑定（类型 + 标识）；6 个可选字段未提供时返回 `null`（不省略）。
- **AC-02（以 VirtualMachine 为载体登记成功）**：同上，载体为活跃 VM → `201`。
- **AC-03（以 Container 为载体登记成功）**：同上，载体为活跃 Container → `201`。
- **AC-04（多载体登记成功）**：一次请求给出 **3 个载体**（分属三种类型）→ `201`；响应中 3 个载体绑定**全部保留**，无遗漏、无截断。
- **AC-05（`name` 必填）**：缺失或非字符串 → `400 VALIDATION_ERROR` + `details[].field == "name"`；不产生 Service 行、不产生绑定行。
- **AC-06（载体必填——完全不提供载体）**：请求未表达任何载体 → `400`；**不产生 Service 行、不产生绑定行**（R-SVC-005 在登记路径上的落地）。
- **AC-07（载体必填——空集合）**：请求表达空载体集合（如空数组）→ `400`；不产生任何写入。
- **AC-08（某一载体无效则整请求失败，无部分绑定）**：3 个载体中**任一**不存在 / 已逻辑删除 → 写入被拒绝、**不产生 Service 行、不产生任何绑定行**、不得 5xx（响应码见 NQ-07）。
- **AC-09（拒绝非载体资源类型）**：以 Cluster / NetworkInterface / IPAddress 作为载体，或载体类型取值不在封闭三值集合内 → `400`（请求 schema 封闭）；不产生写入。
- **AC-10（载体类型与标识必须一致）**：任何指代载体的输入必须无歧义解析为**恰好一个类型明确、存在且活跃**的载体。类型与标识不一致 → 被拒绝、无写入、**不得 5xx**。可测形式（取决于 Architecture 选定的载体表达方式）：断言为 VM 却传入真实 BareMetal 的标识 → 拒绝；两个互斥字段同时给出 → 拒绝。
- **AC-11（合法资源关系保存前阻止，不依赖 UI）**：绕过界面直接调用 API，AC-05~AC-10 的拒绝结果一致；不存在任何绕过校验写入非法绑定的产品路径（§21）。

### B. 字段集合与「未定义约束不实现」

- **AC-12（字段集合封闭）**：请求体、响应体与 `services` 表**恰**包含 `id` + `name` + `service_type / url / port / protocol / owner / description` + 载体绑定 + `created_at` / `updated_at`；**不存在** `deleted_at`（不暴露）、`status`、`cluster_id` / `cluster` / `cluster_name`、凭据 / 密钥字段、健康 / 监控字段、位置字段。请求体出现任何未识别字段 → `400`。
- **AC-13（可选字段缺失不阻断）**：6 个可选字段全部不提供 → `201`，各字段响应为 `null`。
- **AC-14（纯文本往返，不做结构化）**：`name = "共享存储服务"`、`service_type = "自研"`、`url = "这不是一个 URL"`、`port = "abc"` / `"8080-8090"`、`protocol = "自定义协议"`、`owner = "ops"`、`description` 含换行的长文本 → 均按字面值原样存取；**不拆分 / 不归一 / 不校验格式**。
- **AC-15（未定义约束不实现）**：`name` 与 6 个可选字段**无**长度 / trim / 空串 / 字符 / `/` 禁令 / 格式校验：`url` **不要求**是合法 URL；`port` **不要求**是数字、**不校验**范围；`protocol` **不是**封闭枚举；空串与含首尾空白的 `name` **不被拒绝**。AC-15 是**事实陈述**，**不得**被解读为已确认「空 `name` 合法」「任意 `url` / `port` 合法」。`/` 禁令**仅针对 Cluster 名称**。

### C. N:M 绑定语义与 Cluster 共享

- **AC-16（同一 Service 绑定多个载体）**：同一 Service 的详情可观察到其**全部**载体绑定，数量与登记时一致；任一绑定均可读到载体类型与载体标识。
- **AC-17（同一载体被多个 Service 绑定）**：载体 X（任一类型）先被 S1 绑定、再被 S2 绑定 → 二者均 `201`；按载体 X 限定读取返回 **S1 与 S2 两条**。
- **AC-18（跨 Cluster 载体 = 被多个 Cluster 共享，且只登记一次）**：登记 Service S，其载体集合包含**至少两个属于不同 Cluster 的载体** →
  - `201`，且载体绑定数量正确；
  - **系统中名为 S.name 的活跃 Service 行数恰为 1**（**不得**按 Cluster 复制成多条，R-SVC-003）；
  - S 所关联的 Cluster 集合 = 其全部载体的 Cluster 归属之并集，且**至少含 2 个不同 Cluster**，可由「S 的载体列表 + 逐个载体资源的 Cluster 归属」推导得出。
- **AC-19（从任一 Cluster 视角可推导该 Service）**：对 S 的每一个载体 C，**按载体 C 限定读取**的结果中包含 S；对与 S 无绑定关系的载体 C′，该结果中**不包含** S。因此对任一「含有 S 的至少一个载体」的 Cluster，S 均可由该 Cluster 的成员载体推导出现；且这一推导在**两个以上** Cluster 上同时成立（R-SVC-002 的共享语义）。
- **AC-20（不存 `cluster_id`）**：请求体、响应体、`services` 表结构与查询参数中**不存在** `cluster_id` / `cluster` / `cluster_name` 字段或过滤参数；不存在任何读写 Service Cluster 归属的路径。
- **AC-21（归属仅由载体推导，不持久化）**：Service 详情只暴露**载体绑定**；系统**不持久化** Service 的 Cluster 归属。

### D. 唯一性

- **AC-22（全局唯一，保存前阻止）**：已存在活跃 Service `mon`（载体位于 Cluster A）；再登记活跃 Service `mon`（载体位于 **Cluster B**）→ `409 CONFLICT` + `details[].field == "name"`；不产生第二条活跃记录。
- **AC-23（全局 vs 载体范围——与 Container 的对照）**：存在活跃 Service `mon`（载体为 BareMetal B）时，在**同一载体 B** 上登记名为 `mon` 的 **Container** → `201`；在**不同载体**上登记多个同名 **Container** → 均 `201`。该「不冲突」**不得**被解读为削弱 R-CONTAINER-003，也**不得**把 Container 的载体内唯一性套用到 Service。反向同理：Service 的全局唯一性**不按 Cluster、不按载体、不按载体类型**限定。
- **AC-24（不与其它资源类型的名称冲突）**：已存在名为 `mon` 的 Cluster / BareMetal / VirtualMachine / Container 时，登记名为 `mon` 的 **Service** → `201`；各资源类型的名称唯一性**各自独立**。
- **AC-25（大小写敏感）**：`mon` 与 `MON` 可作为两条活跃 Service 共存；不存在 `lower(name)` 唯一索引或任何大小写折叠。
- **AC-26（保存前阻止，DB 为最终权威）**：绕过应用层直接对数据库插入第二条同名活跃 Service 被数据库拒绝；应用路径返回同一 `409`。
- **AC-27（软删释放唯一性）**：软删活跃 Service `mon` 后，可重新登记 `mon` → `201`；旧已删行的 `deleted_at` **未被改写**。

### E. 无状态

- **AC-28（无状态）**：请求体、响应体、`services` 表与端点上**不存在** `status` 字段、枚举、默认值或状态过滤参数。

### F. 查询

- **AC-29（列表、分页、Empty）**：列表端点 → `200` + `{items,total,page,page_size}`；无活跃 Service 时 `items == []`、`total == 0`，不得 `404`。
- **AC-30（详情 Not Found）**：不存在或已逻辑删除的 `id` → `404 NOT_FOUND`（不区分）。
- **AC-31（按载体限定读取，Empty 与 Not Found 可区分，三种载体类型均成立）**：给定载体 X（三选一）：
  - X **存在且活跃**但无活跃 Service 绑定 → `200` + `items == []`（**Empty**）；
  - X **不存在或已逻辑删除** → `404 NOT_FOUND`；
  - 结果**只含**绑定到 X 的活跃 Service；对**三种载体类型均成立**。（路由 / 参数形态见 NQ-09；须保证 F010 可复用。）
- **AC-32（载体过滤参数成对约束）**：只提供载体类型或只提供载体标识（缺一）→ `400 VALIDATION_ERROR`。
- **AC-33（列表 / 详情 / 载体限定读取排除已删）**：绕过应用层预置 `deleted_at` 非空的 Service 后——不出现在列表 `items` / `total`，不出现在任何按载体限定读取结果中；按 `id` → `404`。

### G. 维护

- **AC-34（可选字段可更新）**：`PATCH` 提供合法可选字段（6 个中的任意子集）→ `200` 返回新值；`null` 表示清空；缺省字段不变；再次读取一致。
- **AC-35（更新 schema 封闭）**：`PATCH` 含未识别或不可变字段（含 `id`、`name`、载体绑定、`cluster_id`、`status`、`deleted_at`、凭据、健康）→ `400`；空 body `{}` → `400`；`name` 与**载体绑定**默认不可变（NQ-01 / NQ-02）。
- **AC-36（更新不涉及唯一性）**：6 个可选字段**不参与**任何唯一性；更新它们不会触发唯一性冲突。

### H. 删除与生命周期

- **AC-37（Service 逻辑删除）**：删除活跃 Service → `204` 无响应体；该行仍物理存在且 `deleted_at` 非空；不再出现在列表 / 详情 / 按载体限定读取。
- **AC-38（删除不级联）**：删除 Service 后，其全部载体的 `deleted_at` / `updated_at` / 各字段**逐字段不变**；无其它资源行被修改或物理删除。
- **AC-39（软删后释放载体）**：软删 Service S 后，S 的原载体不再因 S 而被拦截——在满足该载体**其它**活跃子资源检查的前提下，删除该载体 → `204`。即 R-SVC-009 的绑定解除效果由「软删 Service」达成。
- **AC-40（不提供恢复 / 批量能力）**：不存在 restore / undelete / purge / 批量删除 / `include_deleted`。

### I. F014 三载体父删子拦真实端到端

- **AC-41（BareMetal 被活跃 Service 绑定 → 拒绝删除）**：BareMetal B 被至少一个活跃 Service 直接绑定 → `DELETE /api/bare-metals/{B.id}` → `409 CONFLICT` + `details[].code == "ACTIVE_CHILDREN_EXIST"`；B 的 `deleted_at` **仍为 NULL**。
- **AC-42（VirtualMachine 被活跃 Service 绑定 → 拒绝删除）**：同上，对 `DELETE /api/virtual-machines/{id}`。
- **AC-43（Container 被活跃 Service 绑定 → 拒绝删除）**：同上，对 `DELETE /api/containers/{id}`。**本条即 F007 AC-41 的落地**：`CONTAINER_ACTIVE_CHILD_CHECKS` 由显式空元组变为**非空**并包含「活跃 Service」检查，且被删除路径真实消费。
- **AC-44（检查点保留既有检查，只做追加）**：
  - `BARE_METAL_ACTIVE_CHILD_CHECKS` 仍含活跃 VirtualMachine（F006）+ 活跃 NetworkInterface（F004）+ 活跃 Container（F007），并**追加**「活跃 Service」；
  - `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 仍含活跃 Container（F007），并**追加**「活跃 Service」；
  - `CONTAINER_ACTIVE_CHILD_CHECKS` 由 `()` 变为含「活跃 Service」（F008 追加点）。
  三者删除路径均**真实消费**对应检查。
- **AC-45（拦截仅针对直接绑定；不重复实现传递性拦截）**：删除拦截以 R-SVC-009 的**直接绑定**为准。例如「Service 只绑定某 Container，该 Container 在某 VM 上，该 VM 在某 BareMetal 上」时，删除该 BareMetal 的拦截由**既有活跃 VM 检查**达成，**不得**新增「传递性 Service 检查」。`CLUSTER_ACTIVE_CHILD_CHECKS` **保持不变**：删除 Cluster 仍只被活跃 BareMetal 拦截，**不得**因存在「由载体推导关联到该 Cluster 的活跃 Service」而拦截。
- **AC-46（并发孤立记录不变式 = 0 行，三种载体类型）**：并发「登记 Service（绑定载体 X）」与「删除载体 X」后，下列查询**均为 0 行**：
  ```
  存在活跃 Service，且其绑定指向 deleted_at IS NOT NULL 的 BareMetal
  存在活跃 Service，且其绑定指向 deleted_at IS NOT NULL 的 VirtualMachine
  存在活跃 Service，且其绑定指向 deleted_at IS NOT NULL 的 Container
  ```
- **AC-47（登记侧对载体行加锁并同事务确认活跃）**：登记 Service 时必须在**同一事务内**对请求中的**每一个**载体行取共享锁并确认其活跃；任一未命中 → 拒绝登记（不留无主 Service、不留部分绑定）。多载体时的锁获取顺序必须确定（避免死锁）——机制由 Architecture 决定。

### J. 绑定写入路径唯一性与「≥1 载体」不变式

- **AC-48（不存在解绑路径）**：不存在任何可移除 Service 绑定的端点 / 操作 / 参数（含替换载体集合、批量改绑）；绑定关系的写入路径**恰有两条**：登记时建立、Service 软删时释放（AC-39）。R-SVC-009 中「需先解除绑定或删除 Service」在本 Feature 中由**「删除 Service」**这一条达成。
- **AC-49（零载体不变式，产品路径）**：经过任何产品路径操作后，
  ```
  SELECT count(*) FROM 活跃 Service，且其活跃绑定数为 0   -- 必须为 0
  ```
  此即 R-SVC-005 在全产品路径上的落地：登记路径拒绝零载体（AC-06/07），且无任何路径可把已有活跃 Service 变为零载体（AC-48）。
- **AC-50（零载体在数据层可表达这一事实必须被显式对待）**：N:M 绑定表在结构上**可以**表达「活跃 Service 且绑定行数为 0」。产品要求：
  1. 所有**产品写入路径**必须兑现 AC-49；
  2. 必须存在一条**可重复执行的一致性查询 / 测试**（AC-49 的 SQL）作为回归断言；
  3. **不要求**在产品层面承认「零载体活跃 Service 是合法状态」——是否允许该状态存在属**未确认**（NQ-01），本 Feature **不裁定**，也**不**据此引入触发器 / 跨行约束。是否追加数据库层硬约束由 Architecture 裁定（NQ-06）。

### K. 边界、安全与前端

- **AC-51（不越界到其它资源）**：不注册 / 不修改 Cluster、BareMetal、VirtualMachine、NetworkInterface、IPAddress 的资源端点；`services` 表不含 DataCenter / 位置字段；不新增 Cluster → Service 视图（归 F010）。
- **AC-52（无监控 / 凭据 / 发现）**：不存在监控 / 健康检查 / 告警客户端或字段、不存在凭据 / 密钥 / 外部平台 id 字段或端点、不存在自动发现 / 同步 / 服务发现字段或端点。
- **AC-53（认证）**：未认证访问任一 Service 端点 → `401 UNAUTHENTICATED` 且**不改变任何数据**；已认证用户可执行全部操作（V1 无角色 / 权限）。
- **AC-54（前端三态与 Empty / Not Found 可区分）**：列表 / 详情 / 按载体限定读取页面的 Loading / Empty / Error 三态互不相同；Empty 与 Not Found 可区分；错误按 `error.code`（必要时结合 `details[].code`）分支，不解析 `message`；`409` / `404` / `401` 分别处理；前端不得自行实现业务守卫；载体选择在登记表单中**仅**提供三种载体类型且**至少选择一项**才能提交。

---

## 与既有 Feature 的边界

| Feature | 边界 |
|---|---|
| **F001 Cluster** | Service 的 Cluster 关联为推导，**不落 `cluster_id`**；F008 不读写 `clusters` 表结构。删除 Cluster 的拦截条件**不变**（仍只被活跃 BareMetal 拦截，AC-45）。F009 交付的 `by-name` 视图不含 Service。 |
| **F002 BareMetal** | 可作为 Service 载体。向 `BARE_METAL_ACTIVE_CHILD_CHECKS` **追加**活跃 Service（保留活跃 VM / NIC / Container）。BareMetal 名称的「同 Cluster 内唯一」与 Service 的全局唯一**严格分离**。 |
| **F004 NetworkInterface / F005 IPAddress** | 与 Service **无关系**；§15 未将其与 Service 相连。不得把 NIC / IP 作为 Service 载体。 |
| **F006 VirtualMachine** | 可作为载体。向 `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` **追加**活跃 Service（保留活跃 Container）。VM 与 Service 的 `name` 唯一性**都是**全局唯一但**各自独立**（AC-24），不得合并为一张跨资源唯一索引。 |
| **F007 Container** | 可作为载体。F008 **落地 F007 预留的追加点**：`CONTAINER_ACTIVE_CHILD_CHECKS` 由 `()` 变为含活跃 Service（F007 AC-41 / F007 NQ-9）。Container 的「载体内唯一」与 Service 的「全局唯一」**严格分离，不得混用**（AC-23）。 |
| **F009 Cluster 视角查询（DONE）** | 只覆盖 Cluster → BareMetal；F008 **不扩展**该视图。 |
| **F010 资源详情与关联查询（BLOCKED，`depends_on` 含 F008）** | R-QUERY-003 中「查询与 BareMetal 相关的 Service」归 F010。F008 提供**按载体限定读取**这一 canonical 能力（AC-31），F010 **必须复用**、不得另写过滤；F010 必须自行完成「Service → 载体 → Cluster」推导，**不得**要求 F008 落 `cluster_id` 或提供 Cluster 维度过滤。 |
| **F011 Excel 导入** | 若导入模板包含 Service 行，必须**复用 F008 同一套领域校验**（R-IMPORT-002）；N:M 载体在行式模板中的表达属 F011 待确认项（NQ-08）。 |
| **F014 逻辑删除** | 机制归 F014；F008 是**消费方 + 义务方**（AC-37~AC-47），并新增绑定表释放规则（Service 软删即释放绑定）。 |

---

## Blocking Questions

**None.**

1. **不确认就无法确定本次功能范围？** 否。F008 的范围由 R-SVC-001~009 + R-DELETE-001~006 + R-QUERY-004 + §21/§22 + Q-002=B + 已批准 ADR 完全确定；AC-01~AC-54 全部可判定。**没有任何 CONFIRMED 规则要求「登记后变更绑定」**（NQ-01）。
2. **是否导致两种明显不同的用户行为？** 在本 Feature 交付范围内否——每条 AC 均为单值。唯一潜在的二分（「解除最后一个绑定」被拒绝还是被允许）**只能经由「绑定变更」路径到达**，而该路径未被任何 CONFIRMED 规则要求、且按项目先例默认不提供（AC-48）。
3. **是否改变核心领域关系？** 否。`Service → BareMetal / VirtualMachine / Container`（N:M、必选）与 `Service ↔ Cluster`（推导、无列）均已在 `domain-model.yaml > relationships` 中 `binding_state: CONFIRMED`。
4. **是否导致验收标准无法定义？** 否。

### 关于「必选绑定 / 零载体」为何当前不构成 Blocking——以及它何时会变成 Blocking

- **已可判定部分（已给出产品要求与 AC）**：创建 Service **必须同时提供至少一个运行载体**（R-SVC-005）；不提供 / 空集合 / 任一载体无效 → 整请求拒绝且无任何写入（AC-06/07/08）。**这是本次的确定产品要求**。
- **未确认部分（保持开放，本 Handoff 不裁定为规则）**：一个**已存在**的 Service 是否允许被减少到「零载体」。记为 **NQ-01，默认「不可」**。**未对「零载体 Service 是否合法」下任何结论**；只声明两件事实：(a) 本次交付**不提供任何**可以把活跃 Service 变为零载体的产品路径（AC-48）；(b) N:M 绑定表在**数据层固有地可表达**零载体活跃 Service（AC-50），产品要求所有产品路径兑现 AC-49 并保留回归断言，**是否追加数据库层硬约束不由本 Handoff 裁定**（NQ-06）。
- **已消解（2026-09-16 用户确认）**：原本唯一可能使其转为 Blocking 的条件是「登记后变更绑定」被要求纳入 F008。用户已明确裁定：**必须先删除，不做解绑功能**。因此 R-SVC-009 中「需先解除绑定或删除 Service」按**「删除 Service」**这一支理解，且该理解已写入 `requirements.md` §14。AC-48 / AC-49 与端点范围**无需重做**，本 Feature 可继续进入 Architecture。

---

## Open Questions

- **NQ-01（绑定变更与零载体）→ ✅ 已由用户确认（2026-09-16）**：**必须先删除，不做解绑功能**。
  - **确认内容**：V1 **不提供任何解除绑定能力**（不追加、不解除、不替换）。Service 的载体绑定在**登记时一次确定、登记后不可变**。释放运行载体的**唯一**途径是**逻辑删除该 Service**。
  - **已固化为规则**：R-SVC-009 已据此更正（`requirements.md` §14）——「需**先删除该 Service**」，并新增「V1 不提供解除绑定能力」条目。
  - **对 AC 的影响**：AC-48（不存在解绑路径：绑定写入路径恰两条）、AC-49（零载体不变式 = 0 行）、AC-35（`PATCH` 不接受载体绑定）**由「默认」转为「已确认规则」**，不再需要升级条件。
  - **不再是范围敏感项**；「零载体活跃 Service 是否合法」这一歧义随本确认**消解**（不存在到达该状态的路径）。
- **NQ-02（`name` 登记后可变性）**：先例不一致（F001 允许 Cluster 重命名；F002 / F006 / F007 默认不可变）。**默认**：不可变。
- **NQ-03（`by-name` 只读别名）**：技术上可判定但无规则要求。**默认**：不提供。
- **NQ-04（同一请求内重复给出同一载体）**：**默认**：以 `(载体类型, 载体标识)` 为集合元素，不产生重复绑定行；**建议**拒绝（`400`）。
- **NQ-05（读取是否附加推导出的 Cluster 归属）**：**默认**：不返回（AC-21；沿用 F006 NQ-7 / F007 AC-22 的最小范围口径）。
- **NQ-06（「零载体活跃 Service」的数据库层硬约束）**：属 Architecture / Database 判定。产品只要求 AC-49 的产品路径不变式与 AC-50 的回归断言（ADR-0002 明确避免触发器）。**建议**：不引入触发器 / 跨行约束。
- **NQ-07（载体无效时的响应码）**：写入必须被阻止且不得 5xx 已是确定要求；`400` 还是 `404` 未固定。**建议**：沿用 F002 / F004 / F006 / F007 已确立的 `404 NOT_FOUND` 先例。
- **NQ-08（F011 义务）**：若 Excel 模板包含 Service 行，导入必须复用同一套领域校验；N:M 载体集合在行式模板中的表达属 F011 待确认项。
- **NQ-09（按载体限定读取的路由 / 参数形态）**：由 Architecture 裁定；须与 F007 已确立的 `carrier_type` + `carrier_id` 成对语义保持一致（扩展 `CONTAINER`），且必须保证 F010 可复用、Empty / Not Found 判定位置明确。
- **NQ-10（文档与计划元数据漂移，需同步）**：
  1. `domain-model.yaml > open_questions[OPEN-003]` 仍 `status: OPEN` → 应标记 `CLOSED_RESOLVED`（R-SVC-007/008/009，2026-09-16）。
  2. `domain-model.md` **§8 Uniqueness Rules 未收录「Service `name` 全局唯一」** → 应补录（R-SVC-008）。
  3. `docs/database/csm-v1-schema-design.md` 第 439 / 440 / 697 / 894 行仍记载「Service → Host/Container **本次不设计**」/「`0008+` 字段待 Product 阶段确认」→ 应同步（`services` 表 + N:M 绑定表设计）。
  4. `docs/project/project-plan.yaml > F008` 的 `open_questions`（当前 `[]`）/ `contract.status` / `layers` 待按本 Handoff 落盘；同时关闭 F007 NQ-9（F008 追加 `CONTAINER_ACTIVE_CHILD_CHECKS`）。

---

## Assumptions

> 不阻塞当前工作、可安全暂时采用；**不得**当作 CONFIRMED。

- ~~**A-1（范围假设，最重要）**~~ → **已升格为 CONFIRMED 规则（2026-09-16，NQ-01 用户确认）**：运行载体绑定在登记时一次确定、登记后不可变；F008 不提供解绑路径，零载体活跃 Service 不可由产品路径产生。依据：用户 2026-09-16 明确裁定「必须先删除，不做解绑功能」，已写入 `requirements.md` R-SVC-009。
- **A-2（载体表达假设）**：载体以「载体类型 + 载体标识」二元组表达，类型为封闭三值集合，词汇与 F007 既有 `carrier_type` 保持一致并扩展 `CONTAINER`。具体字段名与枚举字面量由 Architecture 契约确定，但**必须**保证三值封闭、类型与标识一致、非载体资源类型不可表达。
- **A-3（请求 schema 封闭假设）**：写请求 schema 封闭（`extra="forbid"`），未识别字段一律 `400`。
- **A-4（错误信封与状态码假设）**：复用 `docs/api/api-conventions.md` 的统一信封与 `404` / `409` / `401` 语义；不另立一套。
- **A-5（时间与字段暴露假设）**：响应含 `created_at` / `updated_at`（RFC 3339），不暴露 `deleted_at`。

---

## Proposed Rules

> 明确标记为 **PROPOSED**，**不得**混入 CONFIRMED。需要用户确认后才能成为规则。

- **PROPOSED-1**：绑定集合语义为**集合**——同一 Service 内不产生重复的 `(载体类型, 载体标识)` 绑定；同一请求重复给出同一载体按非法输入处理（`400`）。（见 NQ-04）
- **PROPOSED-2**：Service 读取响应只暴露载体绑定，**不返回**推导出的 Cluster 归属。（见 NQ-05）
- ~~**PROPOSED-3**：绑定变更应作为独立 Feature 设计~~ → **已由用户确认升格为规则（2026-09-16）**：V1 不做解绑。若未来需要「绑定变更 / 解绑」，属**新增产品规则**，必须作为独立 Feature 并在其 Product 阶段先确认 R-SVC-005 在「零载体」上的确切含义。（见 NQ-01）
- **PROPOSED-4**：`Service.name` 登记后不可变；变更由「软删 + 重新登记」替代。（见 NQ-02）
- **PROPOSED-5**：CLUSTER 删除拦截**不**因推导关联的活跃 Service 而增加。理由：Service↔Cluster 是推导关系而非子资源关系；该 Cluster 下的 BareMetal 未删尽前 Cluster 本就不可删，而 BareMetal 删除已被活跃 Service 直接拦截。（见 AC-45）

---

## Architecture Handoff

> 只列出 Architect 需要解决的技术设计问题；不替 Architect 选型、定表、定 API 细节。

1. **N:M 绑定关系的技术表示**：在 Schema 与契约层表达 `Service ↔ {BareMetal | VirtualMachine | Container}` 的 N:M 绑定。需保证：载体身份 = `(载体类型, 载体标识)`、类型封闭三值；无 `CASCADE`（`ON DELETE RESTRICT`）；**不新增 `service.cluster_id` 列**；绑定表自身是否需要 `deleted_at`（或采用「Service 软删即释放」的等价语义）由 Architecture 裁定——产品只要求 AC-39 / AC-48 / AC-49 成立。多态载体如何落列由 Architecture 决定。
2. **`services` Schema 与增量 migration**：`name NOT NULL`（无长度 / trim / 字符约束）；6 个可空 `TEXT`；`deleted_at`；**无 `status` 列**；**无 `cluster_id` 列**；**无凭据 / 健康 / 位置列**。唯一性为 `services.name` 上的 partial unique index（predicate `deleted_at IS NULL`，大小写敏感，不声明 `COLLATE`，不用 `lower()`）。不改既有基线 migration；同步 `docs/database/**`（含 NQ-10 漂移）。
3. **端点集合与契约落点**：确认端点集合（预期：创建、列表、详情、更新可选字段、删除；按载体限定读取为列表端点的 query 参数或独立只读路径——NQ-09），资源表示的**封闭字段集合**（AC-12），并新建 `docs/api/f008-service.md` 作为唯一权威。明确 `PATCH` 可变字段（恰 6 个可选字段）与不可变字段（`name` / 载体绑定）。
4. **登记路径的多载体存在性 / 活跃性 / 类型一致性与并发协议**：请求中**每一个**载体必须存在且活跃（`SELECT … WHERE id = :carrier_id AND deleted_at IS NULL FOR SHARE`，按类型分派）；需要**确定性锁顺序**以避免多载体请求的死锁（AC-47）；「载体不存在 / 已删 / 类型不一致」的响应码（NQ-07）；并发孤立记录不变式（AC-46）与「不留部分绑定」（AC-08）。
5. **R-SVC-008 唯一性落地**：应用层 `409`（`details[].code = "DUPLICATE"`、`field = "name"`）+ partial unique index 为最终权威；不引入大小写折叠；与 F001/F006 的全局唯一索引**相互独立**（AC-24）。
6. **F014 三载体端到端义务落点**：向 `BARE_METAL_ACTIVE_CHILD_CHECKS`（追加，保留 VM / NIC / Container）、`VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS`（追加，保留 Container）、`CONTAINER_ACTIVE_CHILD_CHECKS`（由 `()` 演进为非空）**三者**注入「被活跃 Service 绑定」检查，并交付 AC-41~AC-47 的端到端与并发测试。**明确不修改 `CLUSTER_ACTIVE_CHILD_CHECKS`**（AC-45）。
7. **「≥1 载体」不变式的落点**：登记路径校验（AC-06/07）+ 唯一软删写入路径的释放语义（AC-39）+ AC-49 回归查询。是否追加数据库层硬约束不由产品裁定（NQ-06）；如选择追加，须说明与 ADR-0002「避免触发器」的关系。
8. **按载体限定读取的路由形态与归属**：决定 query 参数或嵌套路径，明确 Empty / Not Found 判定位置（NQ-09），保证 R-QUERY-004 且 **F010 可复用**。
9. **释放语义与删除路径**：Service 软删须委托系统内**唯一**软删写入路径（`app/deletion/service.soft_delete`），并在同一事务内完成「释放其绑定」，使 AC-39 成立且不产生第二条 `deleted_at` 写入路径。
10. **边界保障（可失败 guard）**：无 `status` 列 / 无状态端点 / 无状态过滤（AC-28）；无 `cluster_id` 列 / 无 Cluster 维度过滤 / 无 `service.cluster_id` 写入路径（AC-20 / AC-51）；无凭据 / 健康 / 监控 / 发现 / 位置字段与端点（AC-52）；6 个可选字段不被结构化拆分（`port` 不解析为整数、`protocol` 不建枚举、`url` 不校验）；不存在解绑 / 替换载体路径（AC-48）；表集合 guard、`CLUSTER_ACTIVE_CHILD_CHECKS` 不变 guard 应**增表演进**而非删除既有断言。
11. **未定义约束的「不实现」保障**：确认 schema / ORM / 契约层不隐式引入 `name` 与 6 个可选字段的长度 / trim / 空串 / 字符 / `/` / URL 格式 / 端口数字校验（AC-15），并以可失败 guard 固定。
12. **读取路径活跃过滤**：复用 `app/db/active.py`，不新写谓词。
13. **前端接线**：列表 / 详情 / 登记（三种载体类型选择，**至少一项**）/ 可选字段修改 / 删除入口；错误按 `error.code`；不重复实现业务守卫。
14. **交付层判定**：确认 `database: true` 与 backend / frontend 层；新增 `services` 表（及绑定结构）→ 表集合 guard 增表演进；同步 `docs/project/project-plan.yaml > F008`（含 NQ-10 漂移）与 `docs/api/f008-service.md`。

---

## 变更影响

**对既有已确认规则：None。**

结构性影响：

1. `BARE_METAL_ACTIVE_CHILD_CHECKS` 从「活跃 VM（F006）+ 活跃 NIC（F004）+ 活跃 Container（F007）」**追加**「活跃 Service」。
2. `VIRTUAL_MACHINE_ACTIVE_CHILD_CHECKS` 从「活跃 Container（F007）」**追加**「活跃 Service」。
3. `CONTAINER_ACTIVE_CHILD_CHECKS` 从**显式空元组**变为**非空**，包含「活跃 Service」——落实 F007 AC-41 / F007 NQ-9。
4. `CLUSTER_ACTIVE_CHILD_CHECKS` **保持不变**（AC-45）。
5. 新增 `services` 表与 N:M 绑定结构 → 表集合 guard、无 CASCADE guard、唯一软删写入路径 guard 应**增表演进**；新增一处 `services.name` 全局 partial unique index。
6. 新增「绑定关系的写入路径恰为两条（登记建立 + Service 软删释放）」这一可失败 guard（AC-48）。

文档漂移需同步（详见 NQ-10）：`domain-model.yaml > open_questions[OPEN-003]`、`domain-model.md` §8、`docs/database/csm-v1-schema-design.md` 第 439/440/697/894 行、`docs/project/project-plan.yaml > F008`（含 F007 NQ-9 关闭）、新增 `docs/api/f008-service.md`。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。字段集合、必选绑定（登记时 ≥1 载体）、N:M 绑定语义、Cluster 归属推导（无 `service.cluster_id`）、全局唯一性与「与 Container 载体内唯一」的对照、无状态、三载体删除拦截义务、以及「零载体」的**开放**边界均已给出**可判定**的产品边界与 AC-01~AC-54；NQ-01~NQ-10 均为 Non-blocking。

**⚠️ NQ-01 为范围敏感项，且是本 Feature 唯一需要用户注意的开放点**：若用户要求「登记后变更绑定」纳入 F008，则立即升级为 Blocking，本 Handoff 须重做后再进入 Architecture。

GIT: NONE
