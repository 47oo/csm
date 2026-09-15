# CSM V1 产品需求

> Status: CONFIRMED BASELINE
> Document Type: Product Requirements
> Target: CSM V1
> Audience: Product Manager / Project Manager / Architect / Database / Backend / Frontend / Tester / Reviewer

---

# 1. 产品定位

CSM 是面向 HPC / AI 运维场景的内部资源管理平台。

主要目标是替代目前通过 Excel、分散文档等方式维护资源信息的模式，为运维人员提供统一的：

* 资源登记；
* 资源查询；
* 资源关系维护；
* 资源状态维护；
* 网络地址管理；
* 机柜位置管理；
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
6. 机柜 U 位可能因为人工维护产生冲突；
7. 多个集群共享服务时容易产生重复登记；
8. 资源历史需要保留，但 Excel 很难维护资源生命周期。

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
│   ├── BareMetal
│   └── Rack
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

# 10. Container

Container 属于 Virtual Resource。

V1 需要允许领域模型表达 Container 资源。

Container 可能运行于：

* BareMetal；
* VirtualMachine。

具体登记粒度、生命周期和运行关系应由对应 Feature 根据实际产品需求进一步确认。

不得因为存在 Container 类型就自动引入：

* Kubernetes；
* Docker API；
* Container Runtime 自动发现。

---

# 11. NetworkInterface

NetworkInterface 表示资源上的网络接口。

---

## R-NIC-001

网络接口需要记录：

`technology_type`

技术类型至少能够表达：

* Ethernet；
* InfiniBand；
* RoCE；
* Other。

---

## R-NIC-002

网络接口需要记录：

`purpose`

用途至少能够表达：

* BMC；
* Management；
* Business；
* Compute；
* Storage；
* DataTransfer；
* Other。

中文展示可以根据 UI 规范确定。

内部枚举应保持稳定。

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

Rack 用于登记服务器在机柜中的实际位置。

---

## R-RACK-001

系统应支持登记 Rack。

---

## R-RACK-002

BareMetal 可以记录其所在：

* Rack；
* U Position。

---

## R-RACK-003

同一 Rack 中不能存在 U 位冲突。

如果新的资源位置与已有有效资源占用范围发生冲突：

> 禁止保存。

不能只显示 Warning 后继续保存。

---

## R-RACK-004

如果未来存在多 U 服务器，应支持表达资源占用的实际 U 范围。

具体字段设计由 Architecture / Database 阶段决定。

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

具体关系是否：

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
* Service；
* Rack Position。

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
* Rack U 位冲突；
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

是否支持部分成功导入，需要在 Excel Import Feature 的 Product 阶段明确。

在未确认之前不得自行决定。

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
* Rack U 位冲突；
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

IP、hostname、Rack U 位等关键规则应明确表达。

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
* Rack / U 位管理；
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

## OPEN-001 VirtualMachine 字段

例如：

* CPU；
* Memory；
* Disk；
* OS；
* Hypervisor；
* Owner。

具体字段尚需根据使用场景确认。

---

## OPEN-002 Container 管理粒度

需要进一步确认：

* 是否登记每个 Container；
* 是否仅登记长期服务型 Container；
* 是否需要 Kubernetes workload 等更高层对象。

---

## OPEN-003 Service 字段

Service 的：

* URL；
* Port；
* Protocol；
* Owner；
* Description；
* Credential reference；
* Health information；

哪些属于 V1 尚需按真实业务确认。

---

## OPEN-004 BareMetal Hardware 字段

例如：

* CPU；
* Memory；
* GPU；
* Storage；
* Vendor；
* Model；
* Serial Number。

实际 V1 必填和可选字段应在 BareMetal Feature 中确认。

---

## OPEN-005 Excel Partial Import

Excel 批量导入发生部分错误时：

* All-or-Nothing；
* Partial Success；

尚需确认。

---

## OPEN-006 Virtual Resource Runtime Integration

V1 当前以人工登记为基础。

未来是否自动接入虚拟化平台或容器平台不属于当前确认范围。

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

