# Product Handoff — F010 资源详情与关联查询

> Status: **`READY FOR ARCHITECT`**
> **✅ BQ-1 / BQ-2 已由用户裁定（2026-09-18）：「按建议来」→ 两者均取「含间接」。**
> 该裁定已固化为 `requirements.md` R-QUERY-003 的「『与 BareMetal 相关』的确切含义」小节；AC-05-a / AC-07-a 生效，AC-05-b / AC-07-b 作废。
> Author Role: product-manager
> Feature: F010（E05，P1，`depends_on: [F001, F002, F004, F005, F006, F007, F008]` 均已 DONE）
> Product Source: `requirements.md` §16 R-QUERY-003 / R-QUERY-004、§15、§13、§21、§23、§17、R-DELETE-002/003/005/006；`domain-model.md` §5.2~§5.7 / §6 / §7.2 / §9；`domain-model.yaml > relationships`（全部条目）、`Service-to-Cluster(derived)`；`docs/product/handoffs/f009/f008/f007/f006/f005/f004/f002`；`docs/api/api-conventions.md`、`docs/api/f009-cluster-resource-view.md`、`docs/api/f014-soft-delete.md`；ADR-0002 / ADR-0003 §2 / ADR-0004 / ADR-0005

---

## Problem

F001~F008 已让每一类资源各自成为可信事实。F009 只解决了「Cluster → 其下 BareMetal」这一条视角。

运维人员真正每天要回答的问题仍未解决：**「这台机器上到底挂了什么？」**——它有哪些网卡、每张网卡上占了哪些 IP、跑了哪些虚拟机、哪些长期容器、哪些服务。今天要回答它，必须分别进入 5 个互不相干的资源列表页逐页筛选、再靠人脑把这些片段拼成一张机器视图，正是 §16 引语所描述的 Excel 场景痛点。

产品价值：**让「一台 BareMetal 的关联全貌」成为一个可直接获得、语义明确的事实**，并让「机器不存在」与「机器存在但这类关联为空」成为两种清晰不同的结论（R-QUERY-004）。

---

## Confirmed Requirements

| 编号 | 确认内容 | 来源 |
|---|---|---|
| R-QUERY-003 | 继续查询与 **BareMetal** 相关的 **NetworkInterface / IPAddress / VirtualMachine / Container / Service**；页面组织由 Frontend 设计；**不得要求用户为获得一个资源的基本信息手工跨多个独立 Excel 式页面拼接** | §16 |
| R-QUERY-004 | 必须区分 **Resource Not Found（404）** 与 **Empty Relationship（200 + 空集合）** | §16；ADR-0003 §6；`api-conventions.md` §7 |
| §15 | 关系不得由分类自动产生；未确认关系不得当既成事实；§15 图示给出 `BareMetal → NIC → IP`、`BareMetal → VM`、`BareMetal / VM → Container`、`Service → BareMetal / VM / Container` | §15 |
| R-DELETE-002 / 003 / 005 / 006 | 已逻辑删除资源不出现在常规查询；无 Undelete；软删不级联；已删释放唯一性 | §17；ADR-0004 |
| R-DELETE-004 | 父有活跃子不得删（F004~F008 已落地，F010 只读取不重复实现） | §17 |
| §21 / §23 / §13 | 关键冲突保存前阻止（F010 无写入）；不引入自动拓扑发现 / 监控 / 位置模型 | §21、§23、§13 |
| ADR-0003 §2 | 规范路径走 `id`；`by-name` 仅为只读别名；`deleted_at` 不暴露 | ADR-0003 |
| ADR-0005 | `/api/*`（登录除外）要求认证；未认证 → `401 UNAUTHENTICATED`；V1 无 RBAC | ADR-0005 |

**本 Feature 不新增、不修改任何领域对象、字段、关系、状态或唯一性规则；不含任何写路径。**

---

## Confirmed Domain Rules（F010 依赖的关系事实）

| 关系 | 基数 / 必选性 | F010 的推导链路 | 来源 |
|---|---|---|---|
| NetworkInterface → BareMetal | N:1，必选 | **直接父**（`bare_metal_id`） | R-NIC-003；`relationships[NetworkInterface-to-BareMetal]` |
| IPAddress → NetworkInterface | N:1，必选（2026-09-15 用户裁定） | **间接**：IP → NIC → BareMetal；**IP 无 `bare_metal_id`** | §15 变更记录；`relationships[IPAddress-to-NetworkInterface]` |
| VirtualMachine → BareMetal | N:1，必选 | **直接宿主**（`bare_metal_id`） | R-VM-005；F006 |
| Container → BareMetal / VirtualMachine | N:1，必选且恰好一个载体 | **多态载体**；`Container→VM→BareMetal` 是已确认链路（Cluster 归属推导即走此链） | R-CONTAINER-002；`relationships[Container-to-Hosts]` |
| Service → BareMetal / VM / Container | N:M，必选、多次、登记后不可变 | **多载体绑定**；无 `service.cluster_id` | R-SVC-005/006/009；`relationships[Service-to-Hosts]`；`forbidden_column: service.cluster_id` |
| Service ↔ Cluster | **推导**，非直接绑定 | 由载体归属推导；F010 **不得**要求任何资源新增 `cluster_id` | R-SVC-004/006；`domain-model.yaml` |
| VM / Container Cluster 归属 | 推导，**不单独记录** | F010 **不得**要求新增列 | R-VM-005；R-CONTAINER-002 |

---

## 目标与范围

### 本次包含

1. **以 BareMetal 为主体的五类关联查询**：NIC / IP / VM / Container / Service（R-QUERY-003）。
2. **每类关系的产品语义定义（可判定）**：见「需求条目」§1，含推导链路。
3. **404 与 Empty 的区分**，且**对五类关系分别成立**（R-QUERY-004）。
4. **「一次获得、无需拼接」的产品能力**：在 BareMetal 上下文中可同时获知五类清单及每类的空 / 非空，并可从该上下文进入对应资源详情。**不固化页面组织**。
5. **软删过滤**：五类清单只含活跃资源（R-DELETE-002；ADR-0004 统一过滤原语）。
6. **复用既有 canonical 读取能力，不得另写一份过滤**（F004 / F005 / F006 / F007 / F008 既有义务）。
7. **只读**：无任何写 / 删除 / 恢复 / 解绑路径。
8. **认证边界**（ADR-0005）。

### 本次明确不包含

| 不包含项 | 依据 |
|---|---|
| 新增 **Cluster → BareMetal 之外**的任何 Cluster 视角（含 Cluster→Service / VM / NIC / IP） | F009 已交付该条；F008 AC-51 |
| 任何资源新增 `cluster_id` 类列（**尤其 `service.cluster_id`**）或 Cluster 维度过滤参数 | R-SVC-004/006；R-VM-005；R-CONTAINER-002 |
| 展示 / 返回**推导出的** Cluster 归属 | F006 NQ-7、F007 AC-22、F008 PROPOSED-2 先例（NQ-1） |
| 图数据库 / 通用关系引擎 / 递归（任意深度）查询引擎 / 自动拓扑发现 | §23 |
| 监控 / 健康 / 状态聚合 / 状态计数 | §23；R-SVC-007；Q-002=B |
| 为 NIC / IP / VM / Container / Service 新增状态 | Q-002=B；`status_models.stateless_resources` |
| Undelete / Restore / 回收站 / `include_deleted` / 查看已删资源 | R-DELETE-003 |
| 任何写 / 删除 / 恢复 / 绑定变更能力 | F010 只读；R-SVC-009（无解绑） |
| DataCenter / 机柜 / U 位 / 位置模型 | §6、§13 |
| 页面组织与布局 | R-QUERY-003 末句（归 Frontend） |

### 本次未涉及

- 反向视图（从 IP / Container / Service / VM 出发看其所属 BareMetal）（NQ-2）；
- 五类之外的资源关系（如 VM 是否拥有独立 NIC——R-NIC-003 未确认，F010 **不得假设**）；
- 状态汇总 / 计数（NQ-3）；排序 / 关键字 / 高级筛选 / 导出 / 分页形态（NQ-4）；
- 关系的时间维度（何时建立 / 历史变更 / 审计）；
- 单次请求聚合 vs 多次 canonical 读取（属 Architecture）。

---

## 需求条目

### 1. 「与 BareMetal 相关」的五类可判定定义

设 **B** 为一个**存在且活跃**的 BareMetal。

| 类别 | 「与 B 相关」的可判定定义 | 推导链路 | 是否已由 CONFIRMED 唯一确定 |
|---|---|---|---|
| **NetworkInterface** | 活跃 NIC 且 `nic.bare_metal_id = B.id` | 直接父（1 跳） | ✅ 是 |
| **IPAddress** | 活跃 IP 且 `ip.network_interface_id ∈ {B 的活跃 NIC}` | **间接**（IP → NIC → B，2 跳） | ✅ 是（IP **无** `bare_metal_id`，非间接则子集恒空） |
| **VirtualMachine** | 活跃 VM 且 `vm.bare_metal_id = B.id` | 直接宿主（1 跳） | ✅ 是 |
| **Container** | ✅ **已裁定（含间接）**：活跃 Container 且载体 = B，**或**载体 ∈ {B 的活跃 VM} | 直接载体 / 载体链（1~2 跳） | ✅ BQ-1 = 含间接（AC-05-a 生效） |
| **Service** | ✅ **已裁定（含间接）**：活跃 Service 的载体与「相关载体集合 R(B)」有交集 | 直接绑定 / 载体链（1~3 跳） | ✅ BQ-2 = 含间接（AC-07-a 生效） |

**相关载体集合 R(B)**（用于 Service 的候选 B）：

```
R(B) = {B}
     ∪ {B 的活跃 VirtualMachine}                     -- 若 BQ-2 取「含间接」
     ∪ Container 相关集合                            -- 若 BQ-2 取「含间接」
```

**耦合（已解除）**：原先 BQ-1 与 BQ-2 互相依赖。两项现已**同时裁定为「含间接」**，故 R(B) 的 Container 部分包含「载体为 B 或 B 上活跃 VM」的活跃 Container，耦合消失；AC-05-b / AC-07-b 作废。

**所有候选定义共同排除**：其他 BareMetal / 其他 VM 上的资源；已软删资源；R-QUERY-003 五类之外的任何资源类型。

### 2. 「资源详情」的产品含义（不固化页面组织）

> 站在一个 BareMetal 的上下文中，用户可**一次**获知该机器的五类关联清单（NIC / IP / VM / Container / Service），每类可判定为「有内容 / 空 / 主体不存在」，且每一条目自带「它为什么与这台机器相关」的绑定依据，因而无需先进入其他资源的全局列表页再逐页筛选拼接。

### 3. 404 与 Empty 的判定位置

- **判定主体唯一**：五类的 404 / Empty 均**只**取决于主体 BareMetal 的存在性与活跃性（不存在或已软删 → `404 NOT_FOUND`，与「不存在」不做区分）；与「该类是否有关联」无关。
- **五类分别成立**，且同一主体下不同类**不得**各自产生不同判定（B 活跃但五类皆空 → 五类全为 `200`）。

### 4. Cluster 归属推导

F010 **不展示、不返回**推导出的 Cluster 归属（NQ-1，默认 = 最小范围，与 F006 NQ-7 / F007 AC-22 / F008 PROPOSED-2 一致）。BareMetal 自身的 `cluster_id` 是 F002 既有直接字段，**不属于推导**，F010 不改变其语义。

### 5. 已软删资源

五类清单**只含活跃资源**；已软删子资源不出现（F009 AC-11 先例；R-DELETE-002；ADR-0004 统一过滤原语）。

### 6. 边界

关系类型集合**封闭**为 R-QUERY-003 的五类，主体固定为 BareMetal。见「本次明确不包含」表。

### 7. 与 F011 的边界

F010 为**纯读取**，不含任何导入 / 写校验；F011 负责模板与 All-or-Nothing 导入（R-IMPORT-001~004）。二者唯一接触点：**F011 导入的资源必须自然出现在 F010 的五类清单中**（F010 读的是同一批事实数据），F010 **不新增**任何供 F011 复用的领域校验规则。

---

## Acceptance Criteria

> 响应字段名、端点形态、聚合方式由 Architecture 契约确定；AC 只约束**语义与可观察行为**。
> **AC-05 / AC-07 各有两个分支（依 BQ-1 / BQ-2 裁定）；其余 23 条在两个分支下均成立。**

### A. 五类关系语义

- **AC-01（NIC — 直接父）**：活跃 B 有 2 张活跃 NIC，另一 BareMetal B2 有 1 张；从 B 上下文查询相关 NetworkInterface → 结果**恰为** B 的 2 张（`id` 集合相等），不含 B2 的；每条可观察 `id` 与 `name`。
- **AC-02（IP — 经 NIC 间接）**：B 的 NIC N 有 2 个活跃 IP、N2 有 1 个，B2 的 NIC 有 1 个；查询 B 的相关 IPAddress → 结果**恰为** 3 个，不含 B2 的；每条可观察 `id`、`ip_address`、所属 `network_interface_id`。**判据**：系统中不存在 `ip_addresses.bare_metal_id`，该结果只能由 `IP → NIC → B` 推导得出。
- **AC-03（VM — 直接宿主）**：B 有 2 台活跃 VM → 结果恰为这 2 台；每条可观察 `id`、`name`、宿主标识；不含他机 VM。
- **AC-04（Container — 直接载体）**：载体为 B（`carrier_type=BARE_METAL`, `carrier_id=B.id`）的活跃 Container 出现；条目可观察 `id`、`name`、载体类型与载体标识。
- **AC-05-a（Container — BQ-1 = 含间接）**：另有 Container C2 载体为 B 上活跃 VM V → C2 **同样出现**，载体类型为 `VIRTUAL_MACHINE`、载体标识为 V；C1（直接）与 C2 同现；不含其他 BareMetal / 其他 VM 的 Container。
- **AC-05-b（Container — BQ-1 = 仅直接）**：C2 **不出现**；当 B 只有经 VM 承载的 Container 时，Container 类清单为**空集合**（`200` + `items==[]`，不得判为 404）；不含其他 BareMetal / 其他 VM 的 Container。
- **AC-06（Service — 直接绑定）**：绑定 B 的活跃 Service S1 出现；条目可观察 `id`、`name`，以及使其与 B 相关的载体（类型 + 标识）。
- **AC-07-a（Service — BQ-2 = 含间接）**：绑定 B 上活跃 VM 的活跃 Service 出现（载体类型 `VIRTUAL_MACHINE` + VM 标识）；若 BQ-1 = 含间接，则绑定「载体为 B 上 VM 的 Container」的活跃 Service 亦出现；同一 Service 绑定多个与 B 相关载体时**只出现一次**。
- **AC-07-b（Service — BQ-2 = 仅直接）**：绑定 B 上 VM / Container 的 Service **不出现**；当 B 无直接绑定 Service 时该类清单为**空集合**（`200` + `items==[]`）。
- **AC-08（关系依据可见 — 「无需拼接」的判据）**：每条相关资源条目均可观察到**使其与 B 相关**的直接绑定依据：NIC→`bare_metal_id`；IP→`network_interface_id`；VM→宿主 `bare_metal_id`；Container→载体（类型 + 标识）；Service→至少一个相交的载体绑定（类型 + 标识）。仅凭该清单即可判定任一资源为何出现在 B 的上下文中。
- **AC-09（字面往返）**：含中文 / 特殊字符的 `hostname` / `name` / `ip_address` 按字面值正确读出，不做归一化（§21；§22）。

### B. Resource Not Found（R-QUERY-004）— 五类分别成立

- **AC-10（404 — 五类分别成立）**：对每一类**独立**执行下列两个子情形，均须 `404 NOT_FOUND`（两者不做区分），**不得** `200` + 空清单：(a) NIC (b) IP (c) VM (d) Container (e) Service。
  1. 主体 BareMetal `id` 不存在；
  2. 绕过应用层预置 `deleted_at` 非空的 BareMetal（其关联数据仍指向它）。
  界面须渲染「资源不存在」类状态，不得渲染为「该机器暂无该类资源」。
- **AC-11（Empty — 五类分别成立）**：主体**存在且活跃**、该类无任何活跃关联 → `200` + 空集合（`items == []`、`total == 0`）：(a) 无活跃 NIC (b) NIC 无活跃 IP（含 B 无 NIC） (c) 无活跃 VM (d) 无活跃 Container（两分支下均成立，仅判定范围不同） (e) 无相关 Service。
- **AC-12（404 判定主体唯一）**：B 活跃但五类皆空时，五类查询**全部**为 `200` + 空集合，**任何一类都不得**返回 `404`；反例断言：人为令某类为空不得诱使该类判定主体变成「该类的子资源」。
- **AC-13（Empty / Not Found / Error 三态可区分）**：三态在界面上互不相同（文案、样式或状态标记任一项可被独立断言）；Empty 不呈现错误提示、不呈现 404 / 失败文案、不触发全局会话失效。

### C. 软删语义

- **AC-14（已软删子资源不出现 — 五类分别成立）**：对每一类独立执行：绕过应用层预置一条 `deleted_at` 非空、绑定仍指向活跃 B 的该类子资源 → 该类清单**不含**该条，且不影响同类其他条目：(a) NIC (b) IP (c) VM (d) Container (e) Service。
- **AC-15（删除后消失、不级联）**：对任一类子资源执行既有 `DELETE` 后，重新查询该类清单 → 该条消失；其余条目与其余四类清单均不受影响；B 自身及其各字段不被修改。
- **AC-16（主体软删后五类均 404）**：主体 B 被逻辑删除后，五类查询**全部** `404 NOT_FOUND`（即使其原关联数据行仍存在）。

### D. 「一次获得」与复用

- **AC-17（无需跨页面拼接）**：从 BareMetal 上下文出发，用户可在**不先进入** NIC / IP / VM / Container / Service 全局列表页、且不依赖人工逐页筛选的前提下，获知五类清单及每类的空 / 非空；且可从该上下文直接进入任一相关资源的详情。页面组织形态不在 AC 约束范围。
- **AC-18（复用既有 canonical 过滤语义，不得另写）**：各清单成员集合与既有 canonical 读取结果一致：
  - NIC：`GET /api/network-interfaces?bare_metal_id={B.id}`；
  - IP：B 的全部活跃 NIC 上 `GET /api/ip-addresses?network_interface_id={N.id}` 结果的并集；
  - VM：`GET /api/virtual-machines?bare_metal_id={B.id}`；
  - Container：`carrier_type=BARE_METAL&carrier_id={B.id}`（BQ-1 = 含间接时，另并上 B 各活跃 VM 为 carrier 的结果，去重）；
  - Service：对 R(B) 中每个载体取 `carrier_type` + `carrier_id` 限定读取结果的并集（按 Service 去重）。
  断言方式：对同一数据，F010 各清单与对应 canonical 端点的**成员集合深等**（字段可不同）。

### E. 边界与安全

- **AC-19（只读）**：F010 不存在任何写 / 删除 / 恢复 / 解绑 / 批量端点或参数；发起查询不改变任何数据行（逐字段不变），不新增第二条软删写入路径。
- **AC-20（不新增 Cluster 视角）**：除 F009 已交付的 `GET /api/clusters/by-name/{cluster_name}/bare-metals` 外，不存在任何以 Cluster 为主语的关联清单 / 端点 / 占位（Cluster→Service / VM / NIC / IP 均不存在）。
- **AC-21（不新增 `cluster_id` 类列与 Cluster 过滤）**：不新增任何资源的 `cluster_id` 类列或写入路径（**尤其 `service.cluster_id` 不存在**）；五类读取上不引入 Cluster 维度过滤参数；结果中不出现推导出的 Cluster 归属字段。
- **AC-22（无通用关系引擎）**：不存在图数据库、通用关系引擎、递归 / 任意深度遍历、自动拓扑发现、关系写入或关系配置入口；关系类型集合封闭为五类，主体固定为 BareMetal（不存在「任意资源 → 任意资源」的通用关联端点）。
- **AC-23（无状态 / 监控越界）**：不为 NIC / IP / VM / Container / Service 新增任何状态字段或推导状态；不提供状态计数 / 汇总 / 健康检查；BareMetal `status` 若在上下文中展示，取值仍为 `IDLE / ALLOC / DOWN / UNKNOWN` 且语义不变。
- **AC-24（认证）**：未认证访问 F010 相关端点 → `401 UNAUTHENTICATED`，且不返回任何资源数据、不改变任何数据。
- **AC-25（需求归属）**：F010 不实现 Excel 导入 / 模板（F011）、不重复实现任何资源的 CRUD（F001~F008）、不重复实现删除守卫（F014）。

---

## 与既有 Feature 的边界

| 邻接 Feature | F010 的立场 |
|---|---|
| **F001 Cluster** | 不读写 Cluster 端点；不新增 Cluster 视角。BareMetal 的 `cluster_id` 语义归 F002。 |
| **F002 BareMetal** | 复用 `GET /api/bare-metals?cluster_id=` 与 `/{id}`；不修改其字段 / 状态 / 唯一性。 |
| **F004 NetworkInterface** | 复用 `?bare_metal_id=` canonical 读取，**不得另写过滤**；不实现 NIC 名称唯一性（F004 NQ-2 未确认）。 |
| **F005 IPAddress** | 复用 `?network_interface_id=`；**不得要求 IP 新增 `bare_metal_id`**；不实现 IP 格式 / 归一化。 |
| **F006 VirtualMachine** | 复用 `?bare_metal_id=`；**不返回**推导 Cluster（F006 NQ-7 先例）。 |
| **F007 Container** | 复用 `carrier_type` + `carrier_id` 成对过滤，**不得另写**；保持 Container 无 `cluster_id`。 |
| **F008 Service** | 复用 `carrier_type` + `carrier_id` 过滤（F008 AC-31 / NQ-09）；F010 **自行完成**「Service → 载体 → …」推导，**不得**要求 F008 落 `cluster_id` 或提供 Cluster 过滤；不提供解绑语义。 |
| **F009 Cluster 视角（DONE）** | 只覆盖 Cluster → BareMetal；F010 不扩展，也不要求 F009 变化。两者共享 404-vs-Empty 语义。 |
| **F011 Excel 导入** | 无功能重叠：F010 只读、无导入、无新领域校验。导入后的资源自然出现在 F010 清单中。 |
| **F014 逻辑删除** | 只消费 `deleted_at IS NULL` 统一过滤原语，不实现软删写入、不做父删子拦、不提供恢复入口。 |

---

## Blocking Questions

**None —— 原 2 项均已裁定（2026-09-18）。**

原 BQ-1 / BQ-2 均取「含间接」，已固化为 `requirements.md` R-QUERY-003 的产品规则；AC-05-a / AC-07-a 生效，AC-05-b / AC-07-b 作废。裁定理由：IP 类**只能**经 `IP → NIC → B` 推导（不存在 `ip_addresses.bare_metal_id`），说明 R-QUERY-003 的「相关」对 IP 已非「直接列」语义；若 Container 取「仅直接」须额外解释为何 IP 走链路而 Container 不走载体链。以下为原记录。

### BQ-1 → ✅ 已裁定：**含间接**（2026-09-18）

- **歧义**：R-QUERY-003 只写「与 BareMetal **相关**」，未定义「相关」是否为沿已确认关系链的推导闭包。Container 的载体为多态（BareMetal 或 VirtualMachine），可经 VM 间接挂到 B 上。
- **两种解释的可见差异**：
  - 包含间接 → 载体为「B 上 VM」的 Container 出现在 B 的关联清单中（并可能出现在多个 BareMetal 的清单中）；
  - 仅直接 → 这些 Container 不出现，B 的 Container 清单可能为空。
- **为何不能唯一确定**：§15 关系图只表达「Container 的载体可为 BareMetal 或 VirtualMachine」，未表达「BareMetal 的相关 Container 是否含经 VM 者」；`domain-model.yaml` 亦无该语义；F008 AC-45 显示 CSM 在「直接绑定 vs 传递性」上**不以传递性为默认**（但那一条是关于**删除拦截**的，不是关于**查询相关性**的）。
- **反方证据（必须一并交给用户）**：IP 类**只能**经 `IP → NIC → B` 推导（IP 无 `bare_metal_id`），说明 R-QUERY-003 的「相关」至少对 IP **不是**「直接列」语义；若 Container 取「仅直接」，则必须解释为何 IP 走链路而 Container 不走载体链。
- **建议**：取**「包含间接」**（与 IP 的推导语义一致，且更贴合 F010「资源详情 / 无需拼接」的产品目的）。若用户选择「仅直接」，则 AC-05-b 生效，且该决定必须写成显式产品规则（不得由实现方解释）。
- **影响**：决定 AC-05-a/05-b、AC-18 的 Container 分支、以及 BQ-2 的载体集合范围。

### BQ-2 → ✅ 已裁定：**含间接**（2026-09-18）

- **歧义**：Service 绑定载体（BareMetal / VM / Container，N:M）。「与 B 相关的 Service」可能是「直接绑定 B」，也可能是「绑定到任何与 B 相关的载体」。
- **两种解释的可见差异**：绑定「B 上 VM」或「B 上 Container」的 Service 是否出现在 B 的清单中；一个共享 Service 是否会在多个 BareMetal 的清单中同时出现。
- **为何不能唯一确定**：R-SVC-006 只确认了「Service ↔ Cluster 由载体推导」，**未**确认「Service ↔ BareMetal 的相关性边界」；R-QUERY-003 未细分。F008 AC-45 同样显示项目不默认传递性（同样是关于删除拦截）。
- **耦合**：若取「包含间接」且载体含 Container，则结果依赖 BQ-1（见 R(B)）。**两项裁定必须成对给出。**
- **建议**：取**「包含间接」**（R(B) 定义同上），与 BQ-1 建议保持一致；理由是 Service 的「运行载体」语义本身就是「它跑在这台机器的（某个层次）上」。
- **影响**：决定 AC-07-a/07-b、AC-18 的 Service 分支、以及是否需要多载体并集去重语义。

### 为何它们必须 Blocking（而非仅仅记录）

1. **不确认会导致两种明显不同的用户行为**（同类清单在相同数据下内容不同）。
2. **不确认会改变交付边界**（清单成员集合、以及是否需要跨 2~3 跳推导）。
3. **不得自行裁定成规则**（AGENTS.md §2.2/§2.7；§15「不得仅根据资源分类自动产生关系」）。

**裁定结果（2026-09-18，用户：「按建议来」）**：
- **BQ-1 = 含间接** ✅ —— 载体为「B 上活跃 VM」的活跃 Container 算与 B 相关（AC-05-a 生效）。
- **BQ-2 = 含间接** ✅ —— 载体与 R(B) 有交集的活跃 Service 算与 B 相关（AC-07-a 生效）。

已固化为产品规则：`requirements.md` R-QUERY-003「『与 BareMetal 相关』的确切含义」小节（含 R(B) 定义与「同一 Service 只出现一次」）。
**明确边界**：该裁定**只适用于查询相关性**，**不改变任何删除拦截语义**（R-DELETE-004 / R-SVC-009 的父删子拦仍以**直接绑定**为准，不新增传递性拦截）。

### 为何以下问题**不**是 Blocking

| 候选 | 为何非阻断 |
|---|---|
| NQ-1 推导 Cluster 是否展示 | 采纳默认「不展示」时行为单值，全部 AC 不依赖其答案；展示与否是加性扩展 |
| NQ-2 是否需要反向视图 | R-QUERY-003 句子 1 已把主体固定为 BareMetal；反方向不是本次交付物，不影响任何 AC |
| NQ-3 状态汇总 / 计数 | F009 NQ-1 先例；不实现时为单值 |
| NQ-4 排序 / 筛选 / 导出 / 分页形态 | 无已确认需求；不实现时为单值 |
| NQ-5 单请求聚合 vs 多次 canonical 读取 | 属 Architecture 可裁定项；AC-17/AC-18 只约束可观察结果 |
| NQ-6 计划元数据落盘 | 流程项 |

---

## Open Questions

- **NQ-1（推导 Cluster 归属是否展示）**：**默认**不展示（与 F006 NQ-7 / F007 AC-22 / F008 PROPOSED-2 一致）。影响：加性展示扩展，不改变任何 AC。
- **NQ-2（反向视图）**：从 IP / Container / Service / VM 出发直接看所属 BareMetal。**默认**：本次不交付。若确认需要，属范围新增（且不得要求新增 `cluster_id` 列）。
- **NQ-3（状态汇总 / 计数）**：**默认**不实现。
- **NQ-4（排序 / 关键字 / 筛选 / 导出 / 分页形态）**：**默认**不实现；沿用既有分页约定。
- **NQ-5（聚合形态）**：单一聚合读取 vs 前端调用多条 canonical 读取 —— 属 Architecture 判定；产品只要求 AC-17 成立、AC-18 成员集合一致。
- **NQ-6（VM 是否拥有独立 NetworkInterface）**：R-NIC-003 未确认（F004 NQ-1）。F010 **不得假设**；若未来确认，属新增关系，F010 需重新评审。
- **NQ-7（计划元数据）**：建议 Architecture 阶段把最终 AC 与 BQ 裁定结果落回 `project-plan.yaml > F010`，并确认契约落点（预计新增 `docs/api/f010-resource-detail.md`）。

---

## Assumptions

（不阻塞当前工作、可安全暂时采用；**不得当作 CONFIRMED**）

1. F010 为**只读** Feature：不新增表、不新增列、无 migration（`database: false` 待 Architecture 确认）。
2. 复用 F002 / F004 / F005 / F006 / F007 / F008 既有 canonical 读取与前端错误处理约定，不另立一套。
3. 结果条目最小可观察集合 = 资源 `id` + 身份标识 + 关系依据（AC-08）；完整展示字段范围属展示设计。
4. 分页沿用 `page` / `page_size` 既有约定（不作为产品规则固化）。
5. 前端路由 / 页面组织延续现状（无 `vue-router`）；页面切换形式不构成产品规则。
6. 五类清单的排序规则不构成本次产品规则。

---

## Proposed Rules

- **PROPOSED-1**：若希望在 BareMetal 上下文提供五类关联的**计数 / 汇总**，应作为产品规则显式确认；R-QUERY-003 未要求。F010 不实现。
- **PROPOSED-2**：若希望展示相关资源的**推导 Cluster 归属**，应作为产品规则显式确认；当前默认不展示。
- **PROPOSED-3**：若希望提供**反向关联视图**，应作为产品规则显式确认。

---

## Architecture Handoff

1. **聚合形态裁定（NQ-5）**：确认是「新增只读聚合读取」（则需新建契约文档）还是「前端调用既有 canonical 读取并聚合」。无论哪种必须满足 AC-17 / AC-18，且**不得**形成第二条软删过滤路径（ADR-0004）。
2. **多跳推导的落点（依赖 BQ-1 / BQ-2）**：在既定关系中实现**固定深度（≤3 跳）**推导读取，且**不得**引入通用关系引擎 / 递归引擎 / 图结构（AC-22）；推导必须复用各资源既有过滤原语。
3. **404 / Empty 判定位置与一致性（AC-10~AC-13）**：五类判定主体统一为「BareMetal 存在且活跃」，须在同一读取路径 / 事务内一致；已软删子资源统一经 `app/db/active.py` 过滤。
4. **复用既有 canonical 过滤（AC-18）**：确认各清单直接委托既有过滤语义，不另写谓词；IP 类为多 NIC 并集、Service 类为多载体并集并去重。
5. **前端三态与 Empty / Not Found 可区分（AC-13）**：沿用 `ListStates` / `ErrorState` 既有约定；Empty 不得渲染为错误、不得触发全局 401 处理。
6. **边界守卫（AC-19~AC-23）**：以可失败 guard 固定「无写路径 / 无新软删写入路径」「无 Cluster 视角新增」「无 `cluster_id` 列与 Cluster 过滤」「无任何资源状态新增 / 无状态聚合」「无图数据库 / 通用关系引擎 / 递归遍历 / 拓扑发现」「关系类型集合封闭为 5 类」。
7. **认证边界（AC-24）**：新增路径（若有）位于 `/api` 前缀下、由 F013 中间件自动覆盖。
8. **AC 与计划落盘（NQ-7）**：把最终 AC（含 BQ 裁定后的分支取舍）写入 `project-plan.yaml > F010`，明确契约落点与各层范围。
9. **验证方法**：明确 AC-10（不存在 / 已软删）、AC-11（五类空）、AC-14（绕过应用层预置软删）、AC-16（主体软删）、AC-18（成员集合深等）、AC-24 的验证方式；沿用 F002/F009「数据层直接预置」取向。

---

## 变更影响

**对既有已确认产品规则：None。**

- 不新增、不修改、不废弃任何 CONFIRMED 规则、领域对象、字段、关系、状态或唯一性规则。
- 不要求 Schema / migration 变更（假设 1）；**明确不新增任何 `cluster_id` 类列**（AC-21）。
- 不削弱 F001~F009 / F011 / F014 的任何已确认边界；F009 的 Cluster 视角入口保持为**唯一**的 Cluster 视角关系查询。

需记录的文档 / 计划漂移（不修改，交由对应角色处理）：

1. `project-plan.yaml > F010` 元数据仍为空骨架（`layers: {}`、`contract: NOT_REQUIRED`、`open_questions: []`）→ 待 BQ 裁定后由 Architecture 阶段按 NQ-7 落盘。
2. F010 的既有 AC 已明确「页面组织由 Frontend 设计」——本 Handoff 遵从，未固化页面组织。
3. 各上游 Feature 交接中专为 F010 保留的复用义务（F004 NQ-6、F005 NQ-6、F006 NQ-4、F007 NQ-6、F008 AC-31/NQ-09）在本 Handoff 中由 **AC-18** 集中承接，**无冲突**。

---

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。BQ-1 / BQ-2 已由用户裁定为「含间接」并固化为 R-QUERY-003 的产品规则，AC-05 / AC-07 的分支收敛为 AC-05-a / AC-07-a（AC-05-b / AC-07-b 作废）。五类关系定义、404 / Empty 语义（五类分别成立）、软删过滤、只读与边界均由 AC-01~AC-25 可判定覆盖。

GIT: NONE
