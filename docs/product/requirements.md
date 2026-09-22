# CSM V1 产品需求

> Status: CONFIRMED BASELINE
> Document Type: Product Requirements
> Target: CSM V1
> Audience: Product Manager / Project Manager / Architect / Database / Backend / Frontend / Tester / Reviewer
>
> 变更记录：
>
> - **2026-09-15 — 依用户明确决策修订基线**
>   - 移除 **Rack / U 位**：删除原 4 条 Rack 规则（R-RACK 序列），影响 §2、§5、§13、§16、§18、§21、§25、§26。
>   - 新增 **R-CLUSTER-005**：Cluster 名称不得包含 `/`（§7）。
>   - 新增 **R-SVC-005 / R-SVC-006**：Service 必选绑定运行载体，Cluster 关联由载体归属推导（§14、§15）。
>   - 澄清 **Q-002=B**：仅 BareMetal 拥有状态；VirtualMachine / Container / Service / NetworkInterface / IPAddress 在 V1 不设状态。
>   - **OPEN-006 关闭**为「已确认排除」（§29）。
>   - 决策来源：`docs/product/domain-conflict-handoff.md`（Q-001=C、Q-002=B、Q-003=A、Rack-1、S-2、D-1、D-2）。
>
> - **2026-09-15 — 架构阶段产品裁定**
>   - **OPEN-005 关闭**：Excel 批量导入采用 **All-or-Nothing**，不采用 Partial Success；固化为 R-IMPORT-004（§18）。
>   - 决策来源：`docs/architecture/csm-v1-foundation-architecture.md` BQ-3。
>
> - **2026-09-15 — 数据库阶段产品裁定（消歧）**
>   - **`IPAddress → NetworkInterface` 关系必选**：IP 地址**必须**绑定在 NetworkInterface 上，该关系为 **Mandatory**（N:1）。此裁定解决了一项文档歧义：`domain-model.yaml` 原已记为 `binding_state: CONFIRMED` / `mandatory: true`，而 §15 写的是「必选性须由对应 Feature 确认」。**以本次用户裁定为准，§15 的「须由 Feature 确认」不再适用于该关系。** 受影响规则：R-IP-001 ~ R-IP-003。
>   - **NIC 枚举为封闭集合（受控枚举）**：R-NIC-001 的 `technology_type` 即为 **Ethernet / InfiniBand / RoCE / Other 四种，无其他取值**；R-NIC-002 的 `purpose` 同属封闭集合。原文「至少能够表达」现解释为「内部枚举固定，中文展示可另定」，而非「允许任意扩展」。新增取值须重新走需求确认流程（同 R-BM-003 对状态集合的处理）。
>   - 决策来源：用户 2026-09-15 对 `docs/database/csm-v1-schema-design.md` Open Questions #11 / #12 的裁定。
>
> - **2026-09-15 — 认证阶段产品裁定（新增 3 条规则）**
>   - 新增 **R-AUTH-004**：口令长度至少 8 位（§19）。
>   - 新增 **R-AUTH-005**：用户名唯一性与登录匹配**区分大小写**（§19）。
>   - 新增 **R-AUTH-006**：登录失败**统一响应**，不区分「用户名不存在」与「口令错误」（§19）。
>   - 规则总数：**46 → 49**。
>   - 决策来源：用户 2026-09-15 对 `docs/product/handoffs/f013-auth.md` 中 PROPOSED-1 / PROPOSED-2 / PROPOSED-3 的裁定。
>
> - **2026-09-16 — BareMetal 阶段产品裁定（新增 1 条规则）**
>   - **OPEN-004 关闭**：BareMetal 硬件字段采用「全部可选 + 纯文本 + 允许 NULL」，固化为 **R-BM-007**（§8）。
>   - **Serial Number 不参与唯一性**（既不全局唯一，也不按 Cluster 唯一）。
>   - 决策来源：用户 2026-09-16 对 F002 OPEN-004 的裁定。
>   - 规则总数：**49 → 50**。
>
> - **2026-09-16 — VirtualMachine 阶段产品裁定（新增 3 条规则）**
>   - **OPEN-001 关闭**：VirtualMachine 标识为 `name`，**全局唯一**、比较区分大小写；新增 **R-VM-004**（§9）。
>   - **DEC-004 关闭**：VirtualMachine → BareMetal 绑定为**必选**；宿主有活跃 VM 时不得删除宿主，VM 软删不级联；新增 **R-VM-005**（§9）。
>   - VirtualMachine 可选配置字段（CPU / Memory / Disk / OS / Hypervisor / Owner）全部可选、纯文本、允许 NULL；新增 **R-VM-006**（§9）。
>   - 决策来源：用户 2026-09-16 对 F006 OPEN-001 / DEC-004 的裁定。
>   - 规则总数：**50 → 53**。
>
> - **2026-09-16 — Container 阶段产品裁定（新增 5 条规则）**
>   - **OPEN-002 关闭**：登记粒度为**仅长期服务型 Container**，不登记短生命周期 / 临时容器，不引入 K8s workload 等更高层对象；新增 **R-CONTAINER-001**（§10）。
>   - **DEC-005 关闭**：Container → 运行载体（BareMetal 或 VirtualMachine）绑定为**必选且恰好一个**，Cluster 由载体推导；新增 **R-CONTAINER-002**。
>   - 标识 `name` 同一载体内唯一、比较区分大小写；新增 **R-CONTAINER-003**。
>   - 可选字段（image / cpu / memory / owner）全部可选、纯文本、允许 NULL；新增 **R-CONTAINER-004**。
>   - 生命周期：载体有活跃 Container 时不得删除载体；软删不级联；新增 **R-CONTAINER-005**。
>   - 决策来源：用户 2026-09-16 对 F007 OPEN-002 / DEC-005 的裁定。
>   - 规则总数：**53 → 58**。
>
> - **2026-09-16 — Service 阶段产品裁定（新增 3 条规则）**
>   - **OPEN-003 关闭**：Service 字段范围定为 name（必填）+ service_type / url / port / protocol / owner / description（均可选、纯文本、允许 NULL）；**credential_reference 与 health_information 不属 V1**；新增 **R-SVC-007**（§14）。
>   - Service `name` **全局唯一**、比较区分大小写；已软删释放唯一性；新增 **R-SVC-008**。
>   - 被活跃 Service 绑定的运行载体**不得删除**；Service 软删不级联；新增 **R-SVC-009**。
>   - 决策来源：用户 2026-09-16 对 F008 OPEN-003 的裁定。
>   - 规则总数：**58 → 61**。
>
> 本文件为 CSM V1 的 Primary Requirements Source；与 `docs/product/domain-model.md` 的同步另行维护，冲突优先级见 `AGENTS.md` §3。
>
> - **2026-09-18 — Resource Query 阶段产品裁定（新增 1 条规则）**
>   - 新增 **R-QUERY-005**：Cluster 内关键字搜索（前置须选定单个 Cluster；范围为该 Cluster 下 BareMetal + R-QUERY-003 五类关联资源「含间接」；匹配为**子串包含 + 不区分大小写 + 单关键字**；结果为混合列表并显示命中字段；无命中复用 R-QUERY-004 Empty）。
>   - 显式边界：不区分大小写**仅限搜索匹配**，不改变 §22 / `by-name` / 登录语义；「模糊」定义为**子串包含**，非容错/相似度。
>   - **未修改任何既有规则**（R-QUERY-001 ~ 004、§22、§17、§19 等原样保留）。
>   - 决策来源：用户 2026-09-18 对 `DEC-021` 与 `NQ-1 ~ NQ-5` 的裁定（`docs/project/project-plan.yaml` `features[F018].open_questions`）。
>   - 规则总数：**61 → 62**。
>
> - **2026-09-20 — 搜索结果聚合阶段产品裁定（修订 1 条 + 新增 1 条规则）**
>   - **修订 R-QUERY-005**：删除 / 改写与聚合裁定冲突的「不承诺结果排序」及「不提供统计（按类型计数、**聚合**、仪表盘）」条款；其结果形态与排序条款改为**引用新增的 R-QUERY-006**。搜索的范围、匹配字段、匹配语义、只读 / 软删 / 认证 / Not Found-Empty / 大小写 / 单关键字 / 空关键字边界**全部保留不变**。
>   - **新增 R-QUERY-006「搜索结果聚合视图（关联链展开）」**：结果为单一扁平混合列表，以「命中项 + 其关联链」为组织单元；**做**关系扩展（关联链资源即使自身未命中关键字也纳入）；呈现为「命中行 + 缩进关联行」，命中行标「命中」、关联行标「关联」及推导路径；未关联到 BareMetal 的命中资源**仅显示搜索涉及的资源**（命中项 + 其关联链）；跨组**不去重**；排序按**字段优先级**（标识字段 `hostname` / `name` / `ip_address` 优先于描述性字段）；**取代** F018 的扁平列表行为。关联推导**引用** R-QUERY-003（含间接），不另立权威。
>   - **未由用户指定**：同优先级结果之间的确定性 **tie-break** 属可实现性选择，留给 Architecture，不写入产品规则。
>   - 决策来源：用户 2026-09-20 对 `DEC-022`（`NQ-1 ~ NQ-8`）的裁定。
>   - 规则总数：**62 → 63**。
>
> - **2026-09-20 — IP 地址范围段阶段产品裁定（新增 1 条规则）**
>   - **DEC-023 关闭（RESOLVED）**：为每个 Cluster 引入多个 **IP 地址范围段（地址池）**；新增 **R-IP-004**（§12）。
>   - 固化 DEC-023 中属 F020 的结论：以 **start–end（含两端，IPv4 dotted-quad）** 表示，**V1 仅 IPv4**；字段**至少** `id / cluster_id / start_ip / end_ip / created_at / updated_at`；`start_ip <= end_ip`；恰属一个**活跃** Cluster（`cluster_id` 必选）；**同 Cluster 活跃范围段不重叠、跨 Cluster 可重复**；**逻辑删除**；**范围内有活跃 IP 时禁止删除**；删除**不级联**；**不设状态**；范围字段须为**合法 IPv4 并规范化**。
>   - 显式边界：**不改变**既有 `ip_addresses.ip_address` 的**自由文本登记语义**；**R-IP-001 ~ R-IP-003 保持不变**。
>   - **IP 自动 / 手动分配不属本阶段**：属 F021（DEC-023 第 7~13 项），当前 BLOCKED，待 F020 DONE 后另行落产品规则。
>   - 未由产品裁定、留 Architecture：同 Cluster「不重叠」的强制方式（应用层校验 + 漂移查询 vs Postgres 排它约束）、契约形态、错误码具体取值、`database` 层判定、并发实现。
>   - 决策来源：用户 2026-09-20 对 `DEC-023` 的裁定（`docs/project/project-plan.yaml` `decisions_required[DEC-023].resolution`）。
>   - 规则总数：**63 → 64**。
>
> - **2026-09-21 — IP 自动 / 手动分配阶段产品裁定（新增 6 条规则）**
>   - **DEC-023 关闭（RESOLVED，2026-09-20）** 中属 F021 的第 7~13 项落地：新增 **R-IP-005 ~ R-IP-010**（§12）。
>   - 固化：分配产物为**一条现有 IPAddress**（不新建分配 / 预留实体）；**必选一个活跃 NetworkInterface**、Cluster 由 NIC→BareMetal **受控推导**（请求不指定 Cluster）；自动分配在 Cluster **全部活跃范围段并集**内取**数值最小的未占用 IPv4**（跨范围段全局最小）；**已占用判定为同 Cluster 内活跃、字面相同的 IPAddress**（软删释放、**无隐式保留地址**）；手动分配须**落在某活跃范围内且未占用**，**范围外字面 IP 仍走 F005 登记端点**；**耗尽**返回明确**非 500** 错误且不创建 IP；**不新增超出 R-IP-001 的唯一性**。
>   - **2026-09-21 用户补充裁定（PR-01）**：手动分配与自动分配一致，对**合法但非规范**的 IPv4 输入先**规范化**再写入 `ip_address`；**地址格式不合法则不允许输入**（拒绝，不创建记录）。占用与唯一性仍按 `ip_address` **字面**比较。
>   - 显式边界：自动 / 手动分配写入值规范化为 dotted-quad，但**占用判定仍按字面相等**——故活跃字面 `010.0.0.1` / `10.0.0.1/16` **不阻止**分配 `10.0.0.1`。
>   - **未修改任何既有规则**：R-IP-001、R-IP-002、R-IP-003、R-IP-004 **原样保留**。
>   - 未由产品裁定、留 Architecture：分配契约形态、错误码具体取值、并发实现、`database` 层复核。
>   - 决策来源：用户 2026-09-20 对 `DEC-023` 的裁定（第 7~13 项）与 2026-09-21 对 **PR-01** 的裁定（采纳 A，并明确非法格式拒绝输入）。
>   - 规则总数：**64 → 70**。
>
> - **2026-09-21 — 网段元数据阶段产品裁定（修订 1 条规则）**
>   - **DEC-024 关闭（RESOLVED，2026-09-21）**：为 IP 地址范围段（网段）新增 3 个**可选**元数据字段
>     `name` / `subnet_mask` / `vlan`，并据此**修订 R-IP-004**（§12）。
>   - 固化：`name` 可选（可空）、**同一 Cluster 内活跃范围段唯一**、**区分大小写**（§22）、
>     **软删释放**（R-DELETE-006）、跨 Cluster 可重复；`subnet_mask` **可选**、**dotted-quad IPv4 合法掩码**
>     （连续 1 后连续 0）、**V1 仅 IPv4**（不用 CIDR 前缀）、**不强制**与 start–end 自洽（描述性元数据，
>     用户示例跳 `/24` 边界允许）；`vlan` **可选整数 1–4094**（0 / 4095 保留）、**不唯一**。
>   - **仅新增**「name 同 Cluster 活跃唯一」一条唯一性；**不新增 VLAN 唯一性**；其余仍以 R-IP-001 为唯一性边界。
>   - 显式边界：**扩展既有 `ip_address_ranges` 表**（加 3 个可空列）；**精确修订 f020 契约（纯增量）**；
>     **不推翻** F020 / F021 既有结论；**V1 分配不按掩码 / VLAN 过滤**；
>     R-IP-001 ~ R-IP-003 与 R-IP-005 ~ R-IP-010 **原样保留保持不变**。
>   - 未由产品裁定、留 Architecture：`name` 的长度 / trim / 空串 / 字符集（**不实现、不承诺**）、
>     掩码存储表示、`PATCH` 可变语义、错误码 `details[]` 具体取值、
>     migration `0010_f022_ip_range_metadata` 形态。
>   - 决策来源：用户 2026-09-21 对 `DEC-024` 的裁定（`docs/project/project-plan.yaml`
>     `decisions_required[DEC-024].resolution`）。
>   - 规则总数：**70 → 70**（**修订既有 R-IP-004，不新增规则编号**）。

---

# 1. 产品定位

CSM 是面向 HPC / AI 运维场景的内部资源管理平台。

主要目标是替代目前通过 Excel、分散文档等方式维护资源信息的模式，为运维人员提供统一的：

* 资源登记；
* 资源查询；
* 资源关系维护；
* 资源状态维护；
* 网络地址管理；
* 虚拟资源管理；
* 服务资源管理；
* ~~批量数据导入~~（**2026-09-18 用户取消，不在 V1 交付范围内**）。

CSM V1 的重点是：

> 建立一个统一、清晰、可查询、可维护的资源事实库。

CSM V1 **不是完整 CMDB**。

---

# 2. 核心问题

当前资源管理主要存在以下问题：

1. 资源信息分散在多个 Excel 或文档中；
2. 同一资源相关信息需要跨多个表查询；
3. IP 地址容易重复分配；
4. 资源与集群之间的关系不够清晰；
5. 裸金属、虚拟机、网络接口、IP、服务等缺少统一查询入口；
6. 多个集群共享服务时容易产生重复登记；
7. 资源历史需要保留，但 Excel 很难维护资源生命周期。

---

# 3. 用户

V1 主要面向：

* HPC / AI 集群运维人员；
* 基础设施管理员；
* 平台管理员。

V1 不以普通计算用户作为主要操作对象。

---

# 4. Resource 概念

CSM 将平台管理对象统一称为：

`Resource`

Resource 是产品领域中的统一概念。

Resource **仅表示资源分类体系**。

它不意味着：

* 必须存在数据库 `resources` 通用表；
* 必须存在 Resource ORM 基类；
* 必须采用数据库继承；
* 所有资源必须拥有完全相同的字段；
* 所有资源必须拥有统一状态模型。

不同资源可以拥有独立：

* 数据模型；
* 属性；
* 状态；
* 生命周期；
* 约束。

---

# 5. Resource Taxonomy

CSM V1 的资源分类为：

```text
Resource
│
├── 基础设施资源 Infrastructure Resource
│   ├── Cluster
│   └── BareMetal
│
├── 虚拟资源 Virtual Resource
│   ├── VirtualMachine
│   └── Container
│
├── 网络资源 Network Resource
│   ├── NetworkInterface
│   └── IPAddress
│
└── 服务资源 Service Resource
    └── Service
```

分类的作用是帮助：

* 产品组织；
* 页面导航；
* 查询；
* 领域理解。

分类本身不自动产生数据库关系。

---

# 6. DataCenter

CSM V1 **不建立 DataCenter 资源层级**。

不得自动创建：

```text
DataCenter
  ↓
Cluster
```

的关系。

Cluster 直接作为当前基础设施资源中的顶层管理对象。

如果未来确实需要数据中心、园区、机房等物理位置模型，应作为新的产品需求重新设计。

---

# 7. Cluster

Cluster 表示一组由 CSM 统一管理的计算资源。

Cluster 不要求一定对应某一种具体调度系统。

例如一个 Cluster 可以表示：

* HPC 集群；
* GPU 集群；
* CPU 集群；
* 由运维人员划分的一组独立服务器。

因此：

> Cluster 是 CSM 中资源组织与隔离的重要边界。

---

## R-CLUSTER-001

Cluster 必须拥有能够被运维人员识别的名称。

---

## R-CLUSTER-002

Cluster Name 在所有当前有效 Cluster 中全局唯一。

名称比较区分大小写。

---

## R-CLUSTER-003

Cluster 当前不设置统一运行状态。

不得为了与 BareMetal 字段统一而给 Cluster 自动增加状态字段。

---

## R-CLUSTER-004

Cluster 可以包含多个 BareMetal。

---

## R-CLUSTER-005

Cluster 名称不得包含 `/`。

理由：Cluster 名称用于 URL 路径寻址（如按集群名称定位其下资源的查询路径）。
包含 `/` 会破坏路径分段，导致该集群无法通过路径寻址。

Cluster 登记的写入路径必须校验本规则，拒绝包含 `/` 的 Cluster 名称。

除 `/` 外的其他字符规则（长度、首尾空白、其他非法字符等）当前仍为**未定义**，不得自行假设。

---

# 8. BareMetal

BareMetal 表示 CSM 管理的物理服务器或物理计算节点。

---

## R-BM-001

每个 BareMetal 必须属于一个 Cluster。

即：

```text
Cluster
  1
  │
  └── N BareMetal
```

当前 V1 不支持完全脱离 Cluster 存在的 BareMetal。

对于没有调度平台的独立服务器，可以通过 Cluster 作为管理分组进行管理。

---

## R-BM-002

BareMetal 必须拥有 hostname。

同一个 Cluster 内：

`hostname`

必须唯一。

不同 Cluster 可以存在相同 hostname。

hostname 比较区分大小写。

---

## R-BM-003

BareMetal 当前运行状态定义为：

* `IDLE`
* `ALLOC`
* `DOWN`
* `UNKNOWN`

含义：

### IDLE

当前资源处于空闲状态。

### ALLOC

当前资源已经被分配或正在使用。

### DOWN

当前资源不可正常使用。

### UNKNOWN

当前无法确定资源状态。

---

## R-BM-004

BareMetal 新建时默认状态：

`IDLE`

---

## R-BM-005

BareMetal 状态不能为空。

对于历史数据无法确定状态时，应明确设置：

`UNKNOWN`

不得使用 `NULL` 代替 UNKNOWN。

---

## R-BM-006

当前 V1 的 BareMetal 状态允许由运维人员人工维护。

不得因为存在状态字段就自动推导必须接入 Slurm、Prometheus、虚拟化平台或其他实时状态源。

---

## R-BM-007

BareMetal 在 V1 **可选**记录以下硬件规格字段：

* Vendor（厂商）；
* Model（型号）；
* Serial Number（序列号）；
* CPU；
* Memory（内存）；
* GPU；
* Storage（存储）。

约束：

* 上述字段均为**可选**；未登记时允许为空（`NULL`），不构成登记阻断条件；
* 上述字段在 V1 均以**文本**记录，不拆分为结构化子字段（例如不以独立字段表达 CPU 型号 / 核数、GPU 型号 / 数量、Memory 单位、Storage 单位）；
* **Serial Number 不参与唯一性约束**（既不全局唯一，也不按 Cluster 唯一）；
* 不得因为存在这些字段而引入自动资产发现或外部平台同步。

---

# 9. VirtualMachine

VirtualMachine 属于 Virtual Resource。

主要用于登记实际存在的虚拟机资源。

---

## R-VM-001

V1 应支持人工登记和查询 VirtualMachine。

---

## R-VM-002

V1 不要求自动接入：

* VMware；
* PVE；
* OpenStack；
* 其他虚拟化平台 API。

虚拟化平台自动发现属于后续扩展能力。

---

## R-VM-003

VirtualMachine 与物理宿主之间的具体关系模型应能够表达实际运行位置。

但如果当前需求无法确定其强制性或生命周期规则，不得由 Agent 自行推导。

应在对应 Feature 的 Product 阶段进一步明确。

---

## R-VM-004

VirtualMachine 必须拥有 `name`（虚拟机名称），作为其身份标识。

`name` 在**所有当前有效 VirtualMachine 范围内全局唯一**（不区分归属的 Cluster 或 BareMetal）。

`name` 比较**区分大小写**（与 Cluster / BareMetal 一致，§22）。

已逻辑删除的 VirtualMachine 不再占用该唯一性（R-DELETE-006）。

---

## R-VM-005

VirtualMachine → BareMetal 的绑定为**必选**：每个 VirtualMachine 必须属于恰好一个 BareMetal 宿主。

VirtualMachine 的 Cluster 归属由其宿主 BareMetal 的 Cluster 归属推导，不单独记录。

生命周期：

* 宿主 BareMetal 存在活跃 VirtualMachine 时，**不得删除该宿主**（R-DELETE-004）；
* 逻辑删除 VirtualMachine **不得自动级联**删除其宿主或其他资源（R-DELETE-005）。

---

## R-VM-006

VirtualMachine 在 V1 **可选**记录以下配置字段：

* CPU；
* Memory（内存）；
* Disk（磁盘）；
* OS（操作系统）；
* Hypervisor（虚拟化平台名称，仅记录，不接入）；
* Owner（负责人，纯文本）。

约束：

* 上述字段均为**可选**；未登记时允许为空（`NULL`），不构成登记阻断条件；
* 上述字段在 V1 均以**文本**记录，不拆分为结构化子字段；
* 不得因为存在这些字段而引入自动资产发现或虚拟化平台同步。

---

# 10. Container

Container 属于 Virtual Resource。

V1 需要允许领域模型表达 Container 资源。

Container 可能运行于：

* BareMetal；
* VirtualMachine。

不得因为存在 Container 类型就自动引入：

* Kubernetes；
* Docker API；
* Container Runtime 自动发现。

---

## R-CONTAINER-001

V1 的 Container 登记粒度为**长期服务型 Container 实例**：

* 只登记长期运行、具有运维意义的容器实例；
* 不登记短生命周期 / 临时容器（如作业型、调试型容器）；
* **不引入** Kubernetes workload（Pod / Deployment / DaemonSet 等）或其他更高层对象作为登记单位。

---

## R-CONTAINER-002

Container → 运行载体的绑定为**必选**：每个 Container 必须属于**恰好一个**运行载体。

运行载体可以是：

* BareMetal；或
* VirtualMachine。

Container 的 Cluster 归属由其运行载体的 Cluster 归属推导，不单独记录（BareMetal → 其 Cluster；VirtualMachine → 其宿主 BareMetal → 其 Cluster）。

---

## R-CONTAINER-003

Container 必须拥有 `name`，作为其身份标识。

`name` 在**同一运行载体内唯一**；不同载体可以存在相同 `name`。

`name` 比较**区分大小写**（与 Cluster / BareMetal / VirtualMachine 一致，§22）。

已逻辑删除的 Container 不再占用该唯一性（R-DELETE-006）。

---

## R-CONTAINER-004

Container 在 V1 **可选**记录以下字段：

* Image（镜像）；
* CPU；
* Memory（内存）；
* Owner（负责人，纯文本）。

约束：

* 上述字段均为**可选**；未登记时允许为空（`NULL`），不构成登记阻断条件；
* 上述字段在 V1 均以**文本**记录，不拆分为结构化子字段；
* 不得因为存在这些字段而引入自动资产发现或容器运行时同步。

---

## R-CONTAINER-005

生命周期：

* 运行载体（BareMetal 或 VirtualMachine）存在活跃 Container 时，**不得删除该载体**（R-DELETE-004）；
* 逻辑删除 Container **不得自动级联**删除其载体或其他资源（R-DELETE-005）。

---

# 11. NetworkInterface

NetworkInterface 表示资源上的网络接口。

---

## R-NIC-001

网络接口需要记录：

`technology_type`

技术类型为**封闭集合**，取值为：

* Ethernet；
* InfiniBand；
* RoCE；
* Other。

**该集合无其他取值**（2026-09-15 用户裁定）。原文「至少能够表达」理解为「内部枚举固定」，而非允许任意扩展。新增技术类型须先经需求确认。

中文展示可以根据 UI 规范确定。

内部枚举应保持稳定。

---

## R-NIC-002

网络接口需要记录：

`purpose`

用途为**封闭集合**，取值为：

* BMC；
* Management；
* Business；
* Compute；
* Storage；
* DataTransfer；
* Other。

中文展示可以根据 UI 规范确定。

内部枚举应保持稳定。

同 R-NIC-001，该集合无其他取值，新增取值须先经需求确认。

---

## R-NIC-003

NetworkInterface 必须能够与其所属资源建立明确关系。

当前最核心对象为：

BareMetal。

未来 VirtualMachine 等资源是否拥有独立 NetworkInterface，应根据对应 Feature 需求确定，不得自动推导。

---

# 12. IPAddress

IPAddress 是独立的 Network Resource。

其核心目标之一是：

> 防止同一个 Cluster 中出现重复 IP 分配。

---

## R-IP-001

在同一个 Cluster 中：

IP 地址必须唯一。

不得存在两个当前有效资源同时占用完全相同 IP。

---

## R-IP-002

不同 Cluster 之间允许存在相同 IP。

例如：

```text
Cluster-A
10.0.0.10

Cluster-B
10.0.0.10
```

是合法情况。

因此 IP 唯一性边界为：

`Cluster`

而不是整个 CSM 系统。

---

## R-IP-003

当前不考虑 VRF 等网络命名空间造成的同 Cluster IP 重复情况。

V1 可以按：

```text
cluster + ip_address
```

理解唯一性。

如果以后需要 VRF，应重新扩展模型。

---

## R-IP-004

CSM V1 允许为**每个 Cluster** 设定多个 **IP 地址范围段（地址池）**。

范围段规则（来源：用户 2026-09-20 对 `DEC-023` 的裁定；可选元数据字段部分来源：用户 2026-09-21 对 `DEC-024` 的裁定）：

### 表示与字段

* 范围段用**起止地址 `start_ip` – `end_ip`（含两端）** 表示，均为 **IPv4 dotted-quad**；
  **V1 仅支持 IPv4**，不支持 IPv6，也不使用 CIDR 等其它表示。
* 范围段字段为：`id`、`cluster_id`、`start_ip`、`end_ip`、`created_at`、`updated_at`，
  以及本节新增的 **3 个可选元数据字段** `name`、`subnet_mask`、`vlan`。
* **除上述字段外没有其它已确认字段**；不得自行新增 description / 用途 / 网关 / CIDR / IPv6 /
  DHCP / DNS / 使用率 等字段。
* 必须满足 `start_ip <= end_ip`。
* `start_ip` / `end_ip` 必须是**合法 IPv4**，并在存储时**规范化**。

### 可选元数据字段（2026-09-21 修订新增）

来源：用户 2026-09-21 对 `DEC-024` 的裁定。三个字段均为**可选**（未登记时允许为空 `NULL`），
不构成登记阻断条件。

#### `name`（网段自定义名称）

* **可选**（可空）。
* **同一 Cluster 内活跃范围段唯一**：同一 Cluster 中不得存在两个活跃范围段具有相同 `name`。
* `name` 比较**区分大小写**（§22；与 Cluster / BareMetal / VirtualMachine / Container / Service 一致）。
* 已逻辑删除的范围段**不再占用**该唯一性（R-DELETE-006）。
* **跨 Cluster 可重复**。
* 长度 / 首尾空白（trim）/ 空串 / 字符集等最小字符约束**本规则未定义**：不实现、不承诺
  （沿用 F005 `ip_address`、F007 Container `name` 的既有先例）。

#### `subnet_mask`（子网掩码）

* **可选**（可空）。
* 表示为 **dotted-quad IPv4 掩码**（例如 `255.255.255.0`）；**V1 仅 IPv4**，
  **不使用 CIDR 前缀长度**（不接受 `/24`）。
* 必须是**合法 IPv4 掩码**：其二进制形式为**连续 1 后连续 0**。
* **不强制** `subnet_mask` 与 `start_ip`–`end_ip` 自洽；掩码为**描述性元数据**，
  不校验范围是否落在该掩码对应的子网内。用户示例 `10.1.1.1` 到 `10.1.2.10`、掩码
  `255.255.255.0`（跨 `/24` 边界）**允许**。

#### `vlan`（VLAN 标注）

* **可选**（可空）。
* 取值为**整数 `1`–`4094`**（`0` / `4095` 为保留值，不接受）。
* **不唯一**：同一 Cluster 内多个活跃范围段可共用同一 `vlan`。

### 归属

* 每个范围段**恰属于一个 Cluster**（`cluster_id` 必选），**不跨 Cluster 共享**。
* 范围段所属 Cluster 必须是**活跃** Cluster。

### 重叠

* **同一 Cluster 内的活跃范围段不得重叠。**
* **跨 Cluster 允许相同范围**（与 R-IP-002 一致）。

### 生命周期与删除

* 范围段支持修改 `start_ip` / `end_ip`。
* 范围段采用**逻辑删除**，**不得物理删除**。
* **当范围内仍有活跃 IP（同 Cluster、活跃、字面落在该范围内）时，禁止删除该范围段。**
* 删除范围段**不级联**删除已分配 / 已登记的 IP。

### 无状态

* 范围段**不设状态**；其活跃 / 失效状态仅由逻辑删除表达（沿用 Q-002=B）。

### 与既有语义的关系（2026-09-21 修订补充）

* 新增的 `name` / `subnet_mask` / `vlan` **不改变** R-IP-004 原有的任何语义：
  **重叠判定、逻辑删除与软删释放、删除守卫、无状态、IPv4 合法性与规范化逐条不变**。
* 范围段的引入**不改变**既有 `ip_addresses.ip_address` 的**自由文本登记语义**。
* 新增字段**不改变** F021 的分配行为：V1 分配**不按** `subnet_mask` / `vlan` 过滤。
* **唯一性边界**：本规则**仅新增**「同一 Cluster 内活跃范围段 `name` 唯一」一条；
  **不新增 VLAN 唯一性**，也不新增其它超出 R-IP-001 的唯一性。
* R-IP-001、R-IP-002、R-IP-003 以及 R-IP-005 ~ R-IP-010 **保持不变**。

---

## R-IP-005

IP **分配**（自动或手动）的**唯一产物**是创建一条现有 **IPAddress**（沿用 F005），**不新建**分配 / 预留实体（不存在分配表、分配字段、分配状态或独立的分配资源）。

来源：用户 2026-09-20 对 `DEC-023` 的裁定（第 7~8 项）。

### 目标 NetworkInterface

* 每次分配**必须恰指定一个活跃 NetworkInterface**；**不存在无 NIC 的分配**。
* 不接受以 BareMetal / VirtualMachine / Container / Cluster / Service 为父，也不提供载体类型选择器（IP 地址 → NIC 的绑定为必选，§15）。
* IPAddress 的 Cluster 归属由 `NetworkInterface → BareMetal → Cluster` **受控推导**（复用 F005 既有推导）；分配请求**不指定 Cluster**，请求与响应**均不含** `cluster_id`。
* 目标 NIC 不存在 / 已逻辑删除，或其宿主 BareMetal 不活跃 → 分配**被拒**（**非 5xx**），不创建任何 IP。
* 本规则**不改变** F005 对 IPAddress 的字段封闭集合与 `ip_address` 自由文本登记语义。

---

## R-IP-006

**自动分配**在目标 Cluster（由目标 NIC 推导）**全部活跃范围段的并集**中，选取**数值最小**的**未占用** IPv4。

* 取**跨范围段的全局最小**，**不**按范围段登记顺序 / 范围段内顺序取「第一个」。
* 选中的地址以**规范化 dotted-quad**（去前导零、无前缀长度）写入 `ip_addresses.ip_address`，与 R-IP-004 对范围字段的规范化一致。
* **不引入任何隐式保留地址**：**不**自动跳过网络地址 / 广播地址 / 网关 / 范围端点或任何其它地址；范围边界完全由用户登记的范围段给定。
* 「未占用」的确切含义见 R-IP-007。

来源：用户 2026-09-20 对 `DEC-023` 的裁定（第 9~10 项）。

---

## R-IP-007

### 已占用判定

在目标 Cluster 内，当存在**活跃（未逻辑删除）**且 `ip_address` **字面相同**的 IPAddress 时，该字面值判为**已占用**。

* **字面相等**：区分大小写、不做 trim、不做归一化、不做大小写折叠；与 R-IP-001 / §22 及 F005 既有立场一致。
* **软删释放**：已逻辑删除的 IPAddress **不再占用**该字面值（R-DELETE-006），可被再次分配。

### 比较边界（两个层次，不得混用）

* **范围归属 / 合法性**（「是否落在某个范围内」）按 IPv4 **数值**比较；范围字段已由 R-IP-004 规范化为 canonical dotted-quad。
* **占用 / 唯一性**（「是否已被占用」）按 `ip_address` **字面**比较（R-IP-001）。
* 由此推论（**用户裁定，不是缺陷**）：同 Cluster 内存在活跃字面 `010.0.0.1`（非规范写法）或 `10.0.0.1/16`（带前缀）时，其字面与 `10.0.0.1` **不同**，因此**不构成对 `10.0.0.1` 的占用**，自动分配**可以**选中并写入 `10.0.0.1`；二者字面不同，R-IP-001 不冲突。同理，`010.0.0.1` 与 `10.0.0.1` 可在同一 Cluster 内共存。
* 本规则**不改变** `ip_address` 的自由文本登记立场：范围归属的数值比较与占用判定的字面比较，都**不**对 F005 的写入路径新增格式约束或归一化。

来源：用户 2026-09-20 对 `DEC-023` 的裁定（第 10 项）。

---

## R-IP-008

**手动分配**要求调用方给出的 IP 同时满足：

1. 是**合法 IPv4**（否则**不允许输入**，拒绝且不创建记录）；
2. 其**数值**落在该 Cluster **某个活跃范围段**内；
3. 该地址**未被占用**（判定同 R-IP-007）。

满足后，经**与自动分配相同的分配写入路径**创建一条绑定目标 NIC 的 IPAddress。

### 写入规范化（用户 2026-09-21 裁定 PR-01，采纳 A）

* 手动分配的输入若为**合法但非规范**的 IPv4（如 `010.0.0.5`），先**规范化**为 canonical dotted-quad（`10.0.0.5`）再写入 `ip_address`，与 R-IP-006 / R-IP-004 一致。
* **地址格式不合法则不允许输入**：非法 IPv4（如 `10.0.0.256`、`10.0.0`、`abc`、`1.2.3.4/24`、`2001:db8::1`、空串、含空白）在手动分配路径被**拒绝**，不创建记录。
* 占用与唯一性仍按**规范化后的字面**比较（R-IP-007）；范围归属按数值比较。

### 与 F005 直接登记的关系

* 手动分配是**受范围约束**的分配操作；它**不替换、不改版** F005 既有的 IP 登记端点。
* **范围外**的任意字面 IP **不经**手动分配能力；仍按 F005 既有的 `POST /api/ip-addresses` 登记（**向后兼容**），不受 F021 范围约束拦截，也不因 F021 而收紧。
* F005 端点的 `ip_address` 自由文本登记语义**保持不变**（R-IP-004 显式边界）；R-IP-008 的「拒绝非法格式」仅作用于**分配路径**，不适用于 F005 登记路径。

来源：用户 2026-09-20 对 `DEC-023` 的裁定（第 11 项）；2026-09-21 对 PR-01 的裁定。

---

## R-IP-009

当目标 Cluster 在**全部活跃范围段的并集**中**不存在任何未被占用的 IPv4** 时（含「该 Cluster 没有任何活跃范围段」的情形），自动分配必须返回一个**明确的、非 500** 的错误，并**不创建任何 IPAddress**。

* 建议采用 `409 CONFLICT`，并以 `details[].code = "NO_AVAILABLE_IP"` 作为稳定判别值；**具体状态码与判别值由 Architecture 在契约中定稿**。
* 耗尽**不得**导致部分写入，**不得**隐式扩大范围 / 跨 Cluster 取址，**不得**回退到「任意地址」。

来源：用户 2026-09-20 对 `DEC-023` 的裁定（第 12 项）。

---

## R-IP-010

IP 分配**不新增**超出 R-IP-001 的唯一性约束：

* 唯一性边界仍为「**同一 Cluster 内 `ip_address` 字面唯一**」（R-IP-001）；跨 Cluster 仍允许相同（R-IP-002）；仍不考虑 VRF / 网络命名空间（R-IP-003）。
* **最终权威**为 R-IP-001 的 partial unique 索引（predicate `deleted_at IS NULL`，F005 既有 `ux_ip_addresses_cluster_ip_active`）。分配**不得**通过新增唯一索引、第二维度列、应用层「独立预留表」等方式绕过 R-IP-001 或与之并存。
* 并发分配（两条请求选中同一地址）：**至多一条成功**；冲突方以既有 `409 CONFLICT`（`details[].code = "DUPLICATE"`）语义返回，**永不 5xx**。
* 并发的**具体实现**（锁序 / 串行化 / 重试）由 **Architecture 定稿**，且不得引入 R-IP-001 之外的新约束或新的死锁序。
* Cluster 归属的**受控推导**（R-IP-005）不得被分配路径绕过：不存在第二处写 `cluster_id` 的路径。

来源：用户 2026-09-20 对 `DEC-023` 的裁定（第 13 项）。

### R-IP-005 ~ R-IP-010 与既有规则的关系

* R-IP-005 ~ R-IP-010 **建立在** R-IP-001 ~ R-IP-004 之上，**不修改其中任何一条**：
  * 「是否在范围内」的范围约束来自 **R-IP-004**（活跃范围段）；
  * 「是否已占用 / 唯一性」来自 **R-IP-001**（同 Cluster 字面唯一）与 **R-IP-002 / R-IP-003**（跨 Cluster 可重复、不考虑 VRF）；
  * 分配产物与目标 NIC 语义引用 **§15**（IP 地址 → NIC 必选）与 F005 的受控 `cluster_id` 推导。
* 释放（回收）**不新增规则**：唯一途径是既有 **R-DELETE-006**（对 IPAddress 逻辑删除后不再占用唯一性）。
* 分配**不改变** §22 大小写语义、§21 保存前阻止、§23 V1 不做清单。

---

# 13. Rack

CSM V1 **不管理 Rack 与 U 位**。

原 4 条 Rack 规则（R-RACK 序列，已全部删除）涵盖：Rack 登记、BareMetal 的 Rack / U Position、同一 Rack 内 U 位冲突硬阻断、多 U 范围表达。该内容已于 2026-09-15 依用户明确决策从 V1 范围移除，**不再作为 V1 产品规则**。

因此：

* BareMetal 在 V1 中不记录 Rack 与 U Position；
* V1 不提供机柜位置管理与 U 位冲突校验。

如果未来恢复机柜位置管理，应作为**新的产品需求**重新设计。

---

# 14. Service

Service 表示运维需要统一管理的服务资源。

Service 类型不预设固定分类。

---

## R-SVC-001

Service Name / Type 等产品字段应允许根据实际服务自由登记。

不得强制只能从固定服务类别中选择。

---

## R-SVC-002

一个 Service 可以被多个 Cluster 共享。

例如：

```text
Service-A
  ├── Cluster-A
  ├── Cluster-B
  └── Cluster-C
```

---

## R-SVC-003

共享服务只能登记一次。

不得因为多个 Cluster 使用同一个 Service，就复制建立多个完全独立的 Service。

正确模型应能够表达：

```text
Service
N ↔ N
Cluster
```

或者其他能够满足相同业务语义的关系模型。

具体数据库实现由 Architecture / Database 决定。

---

## R-SVC-004

Service 不要求必须属于唯一一个 Cluster。

不得设计成强制：

```text
service.cluster_id
```

除非后续产品需求明确改变这一规则。

---

## R-SVC-005

Service 必须绑定运行载体。

可绑定的运行载体为：

* BareMetal；
* VirtualMachine；
* Container。

一个 Service 可以绑定多个运行载体。

绑定为**必选**：不允许存在未绑定任何运行载体的 Service。

---

## R-SVC-006

Service 与 Cluster 的关联通过其**运行载体的 Cluster 归属推导**，而不是通过 `service.cluster_id` 直接绑定。

因此：

* R-SVC-002 的「一个 Service 可以被多个 Cluster 共享」通过绑定跨 Cluster 的多个运行载体实现；
* R-SVC-003 的「共享服务只能登记一次」保持不变；
* R-SVC-004 的「不得强制 `service.cluster_id`」保持不变。

---

## R-SVC-007

Service 在 V1 记录以下字段：

* `name`（服务名称）：**必填**，自由文本（R-SVC-001）；
* `service_type`（服务类型）：可选，自由文本（R-SVC-001，不强制固定分类）；
* `url`、`port`、`protocol`、`owner`、`description`：均为**可选**、纯文本、允许为空（`NULL`）。

**不属 V1**：

* **Credential reference**（凭据引用）——系统无密钥管理，不记录凭据引用，避免变相存储密钥；
* **Health information**（健康信息）——V1 无监控接入且 Service 不设状态（Q-002=B）。

---

## R-SVC-008

Service 必须拥有 `name`；`name` 在所有当前有效 Service 范围内**全局唯一**。

`name` 比较**区分大小写**（与 Cluster / BareMetal / VirtualMachine 一致，§22）。

已逻辑删除的 Service 不再占用该唯一性（R-DELETE-006）。

---

## R-SVC-009

生命周期：

* 绑定了活跃 Service 的运行载体（BareMetal / VirtualMachine / Container），在其仍被该 Service 绑定时**不得删除**（R-DELETE-004 的泛化）；需**先删除该 Service**；
* **V1 不提供「解除绑定」能力**（2026-09-16 确认）：Service 的运行载体绑定在**登记时一次确定、登记后不可变**——既不能追加、也不能解除或替换；因此释放运行载体的**唯一**途径是逻辑删除该 Service。
* 由此推出：活跃 Service **必须**始终绑定至少一个运行载体（R-SVC-005），且**不存在任何使已有活跃 Service 变为零载体的产品路径**；删除 Service 后其原载体不再受该 Service 约束（R-DELETE-006 的绑定侧表现），且删除 Service **不级联**删除载体（下条）。
* 逻辑删除 Service **不得自动级联**删除其运行载体或其他资源（R-DELETE-005）。

---

# 15. Resource Relationship

CSM 不只是资源列表。

平台必须能够查询资源之间的关系。

当前已经明确的核心关系包括：

```text
Cluster
  │
  └── BareMetal
```

以及：

```text
BareMetal
  │
  └── NetworkInterface
         │
         └── IPAddress
```

以及：

```text
Cluster
  N
  │
  └── N Service
```

虚拟资源相关关系：

```text
BareMetal
   │
   └── VirtualMachine

BareMetal / VirtualMachine
   │
   └── Container
```

服务资源相关关系：

```text
Service
   │
   └── BareMetal / VirtualMachine / Container
```

其中 Service 的运行载体绑定为**必选**（R-SVC-005）；Service 与 Cluster 的关联由载体归属推导（R-SVC-006）。

`IPAddress` 对 `NetworkInterface` 的绑定为**必选**（Mandatory）：IP 地址必须绑定在网络接口上。该关系已于 2026-09-15 由用户明确裁定，见顶部变更记录。

对于其他关系，具体是否：

* Mandatory；
* Optional；
* 1:N；
* N:N；

必须以对应 Product Feature 的确认结果为准。

不得仅根据资源分类自动产生关系。

---

# 16. Resource Query

平台必须解决原 Excel 场景中：

> 跨多个表才能查到完整资源信息

的问题。

---

## R-QUERY-001

用户应能够从 Cluster 视角查看其所属资源。

---

## R-QUERY-002

至少应支持查看：

```text
Cluster
↓
BareMetal
```

以及 BareMetal 的状态。

---

## R-QUERY-003

后续资源模型建立后，应能够继续查询与 BareMetal 相关的：

* NetworkInterface；
* IPAddress；
* VirtualMachine；
* Container；
* Service。

具体页面组织由 Frontend 设计，但不得要求用户为了获得一个资源的基本信息手工跨多个独立 Excel 式页面拼接信息。

### 「与 BareMetal 相关」的确切含义（2026-09-18 确认）

「相关」按**已确认关系链推导**判定，不是只看「直接挂在机器上的列」：

| 资源 | 「与 BareMetal B 相关」的判定 |
|---|---|
| NetworkInterface | 其 `bare_metal_id` = B |
| IPAddress | 其所属 NetworkInterface 的 `bare_metal_id` = B（**间接**：IP → NIC → B；IP 无 `bare_metal_id`） |
| VirtualMachine | 其 `bare_metal_id` = B |
| Container | 其运行载体 = B，**或**其运行载体为 **B 上的活跃 VirtualMachine**（**含间接**） |
| Service | 其运行载体集合与「B 的相关载体集合 R(B)」有交集（**含间接**） |

其中 **R(B)** = {B} ∪ {B 上的活跃 VirtualMachine} ∪ {
运行载体为 B 或 B 上活跃 VirtualMachine 的活跃 Container }。

因此：一个绑定在「B 上某台 VM」上的 Service、以及一个跑在「B 上某台 VM 里的 Container」的 Service，
**都算与 B 相关**；同一 Service 因多个载体与 B 相关时**只出现一次**。

**本裁定仅适用于「查询相关性」，不改变任何删除拦截语义**：R-DELETE-004 / R-SVC-009 的父删子拦
始终以**直接绑定**为准，不因本条而新增传递性拦截。

---

## R-QUERY-004

查询结果必须能够区分：

### Resource Not Found

资源不存在。

### Empty Relationship

资源存在，但当前没有关联子资源。

两者在产品语义上不同。

---

## R-QUERY-005

在**单个已选定 Cluster** 范围内，用户应能够通过**一段关键字**快速定位资源。

### 前置条件与范围

* 搜索**必须先选定一个 Cluster**；**未选定 Cluster 时不可发起搜索**。
* 搜索范围**恒为该 Cluster**，**不得跨 Cluster**。
* 命中对象为该 Cluster 下的活跃 BareMetal，**以及**与之相关联的活跃 NetworkInterface / IPAddress / VirtualMachine / Container / Service。
* 「相关联」的判定**直接引用 R-QUERY-003 已确认的「与 BareMetal 相关」定义（含“含间接”推导）**；本条**不重述**该定义，以避免产生第二份权威。
* Cluster 本身是搜索的**范围前置**，**不作为搜索结果行**（2026-09-18 已确认；`Cluster.name` 不参与结果命中）。
* 已逻辑删除的资源**不出现**在搜索结果中（R-DELETE-002）。

### 匹配字段

* 参与匹配的是每类结果的**标识字段 + 已登记的描述性字段**。
* 字段清单以本次裁定（`docs/project/project-plan.yaml` `features[F018].open_questions[NQ-2].resolved_to`）为准；字段本身的定义以 `docs/product/domain-model.yaml` 为**权威来源**，本条**不复制**字段清单。
* **不参与匹配**：资源之间的关系外键、状态字段、系统管理字段（如创建 / 更新时间）。
* 字段值一律按**文本**参与子串匹配（字段清单已包含 `port` / `cpu` / `memory` / `disk` 等数值型字段；这是“子串包含”的直接含义，非新增规则）。

### 匹配语义

* **模糊搜索在本条中定义为“子串包含”**：输入关键字是目标字段值的**一段连续子串**即命中。
* **不区分大小写**：输入 `ABC` 与 `abc` 命中同一结果。
* **单关键字**：不拆分 AND / OR、不分词、不做拼写纠错或相似度匹配。

### 两条必须遵守的边界

1. **「不区分大小写」是搜索专属语义**，**仅用于本条的搜索匹配**。它**不改变** §22 的名称唯一性比较（仍区分大小写）、`by-name` 的字面值等值解析、以及用户名查找禁止 `lower()/ILIKE` 的既有规则。
2. **「模糊」在本条中仅指“子串包含”**，**不是**容错 / 相似度 / 拼写纠错级模糊。若需要后者，属另一条产品规则，须另行确认。

### 结果与 Empty 语义

* 结果为**单一扁平混合列表**（**不按资源类型分区**）；其聚合组织、关系扩展、呈现与排序语义见 **R-QUERY-006**，本条不重复定义。
* 每条结果**显示其命中字段**（命中原因）。
* **无命中时复用 R-QUERY-004 的 Empty 语义**：资源（Cluster）存在但无命中 → `200` + 空结果 + **Empty** 态，**不得**返回 `404`；且与「Cluster 不存在 / 已逻辑删除」的 **Not Found**（`404`）**可区分**。

### 本条明确不承诺 / 不做

* **排序**：仅 R-QUERY-006 规定的「标识字段优先于描述性字段」这一**字段优先级**；不承诺按类型 / 时间排序，**不做**相似度 / 打分式相关性排序。
* **不支持多关键字 / AND / OR 拆分 / 分词**。
* **除结果总数外不提供统计**（按类型计数、仪表盘）；R-QUERY-006 的**关联链组织不是**统计式聚合（按类型计数 / 汇总），二者不得混用。
* **不提供导出**（CSV / Excel）。
* **不提供状态筛选**或任何结构化筛选。
* **不提供跨 Cluster 搜索**。
* **不引入自动资产发现 / 外部平台同步**（§23；R-VM-002 / R-BM-007 / §10）。
* **不改变任何既有唯一性、大小写、软删或登录语义**。
* **空 / 仅空白关键字不构成有效搜索**：在无有效关键字时**不可发起搜索**（前端不发起请求 / 搜索动作不可用）；
  后端对空或仅空白的关键字返回 `400 VALIDATION_ERROR`。**不得**把空关键字解释为「返回该 Cluster 的全部资源」——
  那会使搜索与「列表浏览」无法区分，不是本条承诺的行为。

---

## R-QUERY-006

在 R-QUERY-005 的搜索范围、匹配字段与匹配语义之上，搜索结果的**呈现**采用**关联链聚合视图**（2026-09-20，`DEC-022` 裁定）。

### 与 R-QUERY-005 的关系

* 本条**只定义搜索结果的聚合组织 / 关系扩展 / 呈现 / 排序**；搜索的**范围、匹配字段、匹配语义**（子串包含 + 不区分大小写 + 单关键字）**仍以 R-QUERY-005 为准**，本条不重复。
* 本条**取代** R-QUERY-005 原「单一混合列表（不按资源类型分组）」与「不承诺排序 / 不提供聚合」中与聚合冲突的旧表述；R-QUERY-005 已相应修订为引用本条。
* 关联推导**直接引用 R-QUERY-003 已确认的「与 BareMetal 相关」定义（含「含间接」推导）**；本条**不重述**该定义，以避免产生第二份权威。

### 结果形态与聚合单元

* 结果仍是**一张单一扁平混合列表**，**不按资源类型分区**。
* 聚合（组织）单位为**命中项的关联链**：以每一个**命中项**（其自身至少一个字段命中关键字的资源）为单位，展开其关联链；顶层列表按「**命中项 + 其关联链**」为一个组织单元排列。
* **命中项**与**关联资源**出现在同一张扁平列表中；**不以资源类型作为分区维度**。

### 关系扩展

* **做关系扩展**：命中项的**关联链资源**（即使其自身字段**未**命中关键字）也纳入结果。
* 「关联链」的判定**引用 R-QUERY-003**（含「含间接」推导）；**不得**另写一份关联推导。

### 呈现（方案 A：命中行 + 缩进关联行）

* 每一**行**对应**一个资源**。
* **命中行**：该资源自身字段命中关键字，标注为「**命中**」。
* **关联行**：该资源因处于某命中项的关联链中而出现，标注为「**关联**」，并显示其**推导路径**（例如 `IP → NIC → BareMetal`）。
* 关联行在视觉上与命中行可区分（如缩进 / 标记）；具体排版由 Frontend 决定。

### 未关联到任何 BareMetal 的命中资源

* 仅显示**搜索涉及的资源**：命中项 **+** 其关联链资源（**解读 (a)**）。
* **不做全量倾销**：不因一次搜索而展示该 Cluster 的全部资源。

### 跨组去重

* **不去重**：同一资源若因**命中多条关联链**而出现在多个组织单元中，则**重复出现**。
* 本条**不改变** R-QUERY-003 的**成员判定**（「哪些资源属于搜索结果集」）；本条处理的是「同一资源在多个命中链下重复呈现」，二者是不同层次，不得混用。

### 排序

* 排序按「**关键字最靠近**」，具体采用**字段优先级**：**标识字段（`hostname` / `name` / `ip_address`）优先于描述性字段**。
* **不承诺**此字段优先级之外的其他排序（不按类型 / 时间排序）；**不提供**相似度 / 打分式相关性排序。
* **同优先级结果之间的确定性兜底顺序（tie-break）**：**未由用户指定**，属**可实现性选择**，由 Architecture 在契约定稿；本条**不规定**。
* 分页形态（条目级 vs 组级）**未由产品规定**，由 Architecture 在契约中定稿；其**不得改变**本条与 R-QUERY-005 已确认的行为。

### 与 F018 扁平列表的关系

* 本条语义**取代** R-QUERY-005 原先（F018）的扁平列表行为；二者**不同时并存**。

### 边界（继承 R-QUERY-005，不改变）

* 搜索仍**只读**；**已逻辑删除的资源不出现**；未认证 → **401**；**Not Found / Empty 可区分**（R-QUERY-004）；**不区分大小写仅限搜索匹配**；**单关键字 / 子串包含**；**不跨 Cluster**；**不引入自动资产发现 / 外部同步**；**不新增 / 不修改任何唯一性约束**。
* **空 / 仅空白关键字不构成有效搜索**（同 R-QUERY-005）。
* **除结果总数外不提供统计**（按类型计数、仪表盘）；本条的关联链组织**不是**统计式聚合。

---

# 17. Soft Delete

CSM 需要保留资源历史。

因此资源默认采用逻辑删除语义。

---

## R-DELETE-001

正常产品操作不得直接物理删除核心资源记录。

---

## R-DELETE-002

已逻辑删除资源默认不出现在正常查询结果中。

---

## R-DELETE-003

V1 不提供 Undelete / Restore 功能。

如果以后需要恢复，应作为独立 Feature 设计。

---

## R-DELETE-004

父资源仍然存在有效子资源时：

不得删除父资源。

例如：

Cluster 仍然存在有效 BareMetal：

不能删除 Cluster。

---

## R-DELETE-005

逻辑删除不得自动级联删除所有子资源。

必须显式处理依赖关系。

---

## R-DELETE-006

已经逻辑删除的资源不继续占用正常业务唯一性。

因此在满足其他业务规则情况下，可以重新创建同名资源。

---

# 18. Excel Import

> ⚠️ **本节的规则（R-IMPORT-001 ~ R-IMPORT-004）不在 CSM V1 的交付范围内。**
> 用户于 **2026-09-18** 明确决定取消对应功能（计划中的 F011「Excel 模板与批量导入」，状态 CANCELLED）。
> 以下规则文本**按原样保留**（已确认的规则不因下线功能而删除），但 **V1 不实现、不交付**，且不作为任何验收基准。
> 若未来重新需要批量导入，应作为**新的产品需求**重新确认，而非直接沿用本节作为已交付承诺。

CSM 的重要目标之一是替代现有 Excel 管理方式。

因此需要支持从标准 Excel Template 批量导入资源。

---

## R-IMPORT-001

系统应提供明确的 Excel 导入模板。

---

## R-IMPORT-002

导入过程必须执行与页面人工录入一致的业务校验。

不得通过 Excel 导入绕过：

* 唯一性；
* 必填字段；
* 资源关系；
* IP 冲突；
* 合法状态值。

---

## R-IMPORT-003

导入失败时应明确指出：

* 哪一行；
* 哪一个字段；
* 什么原因。

不能只返回：

`Import Failed`

---

## R-IMPORT-004

Excel 批量导入采用 **All-or-Nothing**（全或无）语义。

即：

* 只要有任意一行校验失败，**整个导入不产生任何写入**；
* 不能采用「部分成功导入」（不得先写入合法行再报告错误行）；
* 失败时必须一次性报告**全部**失败行，而不是遇到首行错误即中止；
* 全部行通过校验时，必须在单一事务内完成写入。

该语义于 2026-09-15 由用户明确裁定（原为待确认项 OPEN-005）。

如果未来需要「跳过错误行继续导入」，应作为新的产品需求重新设计。

---

# 19. Authentication

CSM 是内部运维平台。

---

## R-AUTH-001

V1 使用系统本地账号进行登录认证。

---

## R-AUTH-002

V1 不要求接入：

* LDAP；
* AD；
* OAuth；
* 企业 SSO。

这些能力可以后续扩展。

---

## R-AUTH-003

更复杂的 RBAC 权限模型如果当前没有明确产品需求，不得由 Architect 自行扩大 V1 范围。

---

## R-AUTH-004

口令长度**至少 8 位**。

低于 8 位的口令不得被接受。

该规则适用于**任何建立或修改口令的路径**（当前为初始账号初始化；未来的口令修改 / 重置路径同样适用）。

除长度下限外，V1 不对口令提出其他强度要求（不要求大小写混合、数字、符号，也不做弱口令黑名单）。

---

## R-AUTH-005

用户名的**唯一性与登录匹配均区分大小写**。

即 `admin` 与 `Admin` 是两个不同的用户名，且登录时必须按原样精确匹配。

不得使用 `lower(username)` 唯一索引或其他大小写折叠实现。

该规则与 R-CLUSTER-002 / §22 对资源标识的处理方式一致。

---

## R-AUTH-006

登录失败时，**不得区分「用户名不存在」与「口令错误」**。

两种情况必须返回**完全相同**的响应（状态码、`error.code`、文案），使调用方无法据此判断某用户名是否存在。

该规则是为了避免账号枚举，属**安全下的产品行为要求**，不是实现建议。

---

# 20. Deployment

---

## R-DEPLOY-001

CSM V1 部署在独立内网虚拟机。

---

## R-DEPLOY-002

系统主要通过内网访问。

---

## R-DEPLOY-003

V1 可以使用：

```text
Internal IP + HTTP
```

不要求因为互联网 Web 最佳实践自动增加：

* 公网入口；
* 域名；
* HTTPS；
* Internet exposure。

如果后续网络安全要求改变，再单独设计。

---

# 21. Data Consistency

系统必须优先保证：

> 资源事实数据的一致性。

关键冲突必须在保存前阻止。

包括但不限于：

* 同 Cluster IP 重复；
* 同 Cluster hostname 重复；
* 全局 Cluster Name 重复；
* 非法资源关系；
* 非法状态值。

不能只依赖 UI 校验。

Backend / Database 必须具有必要的数据一致性保护。

具体实现由 Architecture / Database 决定。

---

# 22. Case Sensitivity

当前已经确认：

以下名称唯一性比较区分大小写：

* Cluster Name；
* BareMetal hostname。

例如：

```text
cluster-a
Cluster-A
```

从业务唯一性规则角度可以被认为是不同值。

如果未来希望改成大小写不敏感，需要明确修改产品规则。

---

# 23. V1 不做什么

以下能力不应因为“资源管理系统通常都有”而自动加入 CSM V1：

* 完整 CMDB；
* DataCenter 层；
* 自动资产发现；
* VMware / PVE / OpenStack 自动同步；
* Kubernetes 自动同步；
* Slurm 集成；
* 自动拓扑发现；
* Prometheus 监控平台替代；
* 告警平台；
* 工单系统；
* 采购系统；
* 财务系统；
* 自动容量预测；
* 复杂 RBAC；
* 微服务化；
* 通用 Resource EAV 模型。

如果后续需要，应重新进入 Product Planning。

---

# 24. Resource Taxonomy 与数据库设计

以下是明确产品规则：

```text
Resource
├── Infrastructure
├── Virtual
├── Network
└── Service
```

它是：

`Product Taxonomy`

不是：

`Database Inheritance Model`

因此 Architecture / Database Agent 不得仅因为存在统一 Resource 概念，就默认采用：

```text
resources
  id
  type
  name
  attributes JSONB
```

或者：

* EAV；
* Single Table Inheritance；
* ORM polymorphic inheritance。

是否需要共享基础模型必须根据真实业务需求单独论证。

---

# 25. 产品核心原则

CSM V1 应坚持：

### Explicit Resource Types

资源类型应该明确，而不是全部抽象成一个万能 Resource。

### Explicit Relationships

资源关系必须明确建模。

### Explicit Constraints

IP、hostname 等关键规则应明确表达。

### History Preservation

资源删除不能破坏历史事实。

### Simple First

优先选择简单、可理解、可维护的设计。

不得为了“未来可能需要”进行大规模抽象。

---

# 26. 当前明确的 V1 能力范围

根据目前已经确认的需求，Project Planning 至少需要覆盖以下产品能力域：

* Cluster 管理；
* BareMetal 管理；
* Resource 查询；
* NetworkInterface 管理；
* IPAddress 管理；
* VirtualMachine 管理；
* Container 资源模型；
* Service 管理；
* Cluster 与 Service 关联；
* ~~Excel 批量导入~~（**2026-09-18 用户取消，不在 V1 交付范围内**）；
* 本地账号认证；
* 逻辑删除和数据一致性。

这里描述的是：

`Capability Scope`

不是已经拆好的 Feature Backlog。

`/project` 应根据依赖关系和交付价值重新拆分 Feature。

---

# 27. Project Planning 要求

`/project` 在读取本文档后必须：

1. 建立 Requirement Coverage；
2. 建立 Epic；
3. 将需求拆成可交付 Feature；
4. 为 Feature 分配稳定 ID；
5. 每个 Feature 关联对应 Requirement ID；
6. 建立 Feature Dependency DAG；
7. 识别 Shared Foundation / Enabler；
8. 识别项目级 Blocking Decision；
9. 检查项目中已有实现；
10. 不重复规划已经完成的能力；
11. 生成 Project Plan；
12. 生成 Backlog；
13. 生成 Dependency Map；
14. 生成 Milestone。

不得把：

* Database Table；
* Backend Endpoint；
* Frontend Page；

机械拆成三个独立产品 Feature。

这些通常属于同一个 Feature 的不同实现层。

---

# 28. 已有实现识别

当前项目已经存在部分代码和 Feature 工作成果。

`/project` 必须扫描：

* `docs/product/`
* `docs/architecture/`
* `docs/database/`
* `docs/api/`
* Backend；
* Frontend；
* Test；
* Review；
* Git History。

如果某能力已经：

```text
Reviewer = APPROVED
```

或者：

```text
Reviewer = APPROVED WITH FOLLOW-UP
```

才能判断对应 Feature：

`DONE`

不得因为存在代码文件就判断 Feature 已完成。

---

# 29. 当前未确认项

以下内容不应被 `/project` 自动当成已确认产品规则。

需要时应在具体 Feature Product 阶段进一步确认。

---

## OPEN-001 VirtualMachine 字段与标识规则（已关闭）

VirtualMachine 字段、标识与绑定规则已于 2026-09-16 由用户裁定：

* 标识字段 `name`，必填，**全局唯一**，比较区分大小写；
* 绑定 BareMetal 为**必选**；Cluster 归属由宿主推导；
* 可选配置字段（CPU / Memory / Disk / OS / Hypervisor / Owner）全部可选、纯文本、允许 NULL；
* 宿主有活跃 VM 时不得删除宿主；VM 软删不级联。

已固化为 **R-VM-004 / R-VM-005 / R-VM-006**（§9），不再是待确认项。

---

## OPEN-002 Container 管理粒度（已关闭）

Container 登记粒度与绑定已于 2026-09-16 由用户裁定：

* 粒度为**长期服务型 Container 实例**，不登记短生命周期 / 临时容器，不引入 K8s workload 等更高层对象；
* 绑定运行载体（BareMetal 或 VirtualMachine）为**必选且恰好一个**；Cluster 由载体推导；
* 标识 `name`，同一载体内唯一、区分大小写；
* 可选字段（image / cpu / memory / owner）全部可选、纯文本、允许 NULL；
* 载体有活跃 Container 时不得删除载体；软删不级联。

已固化为 **R-CONTAINER-001 ~ R-CONTAINER-005**（§10），不再是待确认项。

---

## OPEN-003 Service 字段（已关闭）

Service 字段范围已于 2026-09-16 由用户裁定：

* `name` 必填；`service_type` / `url` / `port` / `protocol` / `owner` / `description` 均可选、纯文本、允许 NULL；
* **Credential reference 与 Health information 不属 V1**；
* `name` 全局唯一、区分大小写；
* 被活跃 Service 绑定的载体不得删除。

已固化为 **R-SVC-007 / R-SVC-008 / R-SVC-009**（§14），不再是待确认项。

---

## OPEN-004 BareMetal Hardware 字段（已关闭）

BareMetal 硬件字段范围已于 2026-09-16 由用户裁定：

* **全部可选**：Vendor / Model / Serial Number / CPU / Memory / GPU / Storage；
* **纯文本**记录，V1 不结构化；
* 允许为空（`NULL`）；
* **Serial Number 不参与唯一性**。

已固化为 **R-BM-007**（§8），不再是待确认项。

---

## OPEN-005 Excel Partial Import（已关闭）

Excel 批量导入发生部分错误时的语义已于 2026-09-15 由用户裁定（**注：该功能已于 2026-09-18 取消，不在 V1 交付范围内；此条仅作历史记录保留**）：

* **采用 All-or-Nothing**；
* 不采用 Partial Success。

已固化为 **R-IMPORT-004**，不再是待确认项。

---

## OPEN-006 Virtual Resource Runtime Integration（已关闭）

原文将该项列为「当前未确认项」。经 2026-09-15 澄清，该项**已由已确认规则排除**，不属于未确认范围。

依据：

* **R-VM-002**：V1 不要求自动接入 VMware / PVE / OpenStack 或其他虚拟化平台 API；
* **§10**：不得因为存在 Container 类型就自动引入 Kubernetes / Docker API / Container Runtime 自动发现；
* **§23**：V1 不做清单已包含「自动资产发现」「VMware / PVE / OpenStack 自动同步」「Kubernetes 自动同步」「Slurm 集成」。

因此该项从「当前未确认项」移出，判定为**已确认排除**。

V1 以**人工登记**为基础。运行时自动集成若未来需要，应作为新的产品需求重新设计。

---

# 30. Product Source of Truth

本文档是：

`CSM V1 Project Planning 的主要产品需求入口`

更详细的资源模型可以同时参考：

`docs/product/domain-model.yaml`

以及：

`docs/product/domain-model.md`

资源领域 Agent 使用规则可以参考：

`.pi/skills/resource-domain/SKILL.md`

如果内容冲突，优先级按照项目 `AGENTS.md` 定义执行。

