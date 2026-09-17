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
* 批量数据导入。

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

---

## R-QUERY-004

查询结果必须能够区分：

### Resource Not Found

资源不存在。

### Empty Relationship

资源存在，但当前没有关联子资源。

两者在产品语义上不同。

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
* Excel 批量导入；
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

Excel 批量导入发生部分错误时的语义已于 2026-09-15 由用户裁定：

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

