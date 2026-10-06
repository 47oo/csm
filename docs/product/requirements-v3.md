# CSM V3 一期需求

版本：V3 phase 1 / revision 3。来源：用户于 2026-10-06 提供的《CSM V3 一期需求说明》，对 Q01–Q10 建议的确认，以及本次对剩余六项建议的明确确认：“按照推荐建议修改这6项”。确认范围与修订记录见 §35.1。

本文件是一期范围、产品规则和验收要求的权威来源。原说明正文中的“CSM V1”统一解释为标题指定的“CSM V3 一期”；已确认的 REST 前缀 `/api/v1/` 是独立 API 版本，不随产品版本改成 v3。

明确要求及获批建议标为 CONFIRMED；未获批建议仍为 PROPOSED。本次六项业务问题均已关闭，§35.2 保留决策索引；尚缺专业设计输入见 §35.3。已确认产品规则及技术栈不代表 Feature 计划或应用实施已经获批。以下字段清单表示至少支持的属性，完整字段契约由 D01 在已确认默认值、单位及边界内补齐，不将字段清单直接作为获批 Schema。

## 1. 项目概述

**CSM — Cluster Source Manager** 是面向 HPC / AI 多集群环境的轻量级资源管理与查询平台，定位为 **Resource Source of Truth（资源事实数据源）**。

CONFIRMED：统一维护集群、裸金属服务器、虚拟机、网络接口、IPv4 网络、IP 地址、IP 地址池和服务，解决 Excel / 文档台账分散、关系不清、查询困难及多人维护冲突。第一期不执行服务器部署、配置管理、监控、Slurm 调度或自动化运维。

## 2. 建设目标

CONFIRMED：统一多集群资源；裸金属与 VM 共用 Resource 模型；建立 Resource、Interface、IP、Network、VM Host、Service 关系；每集群多个 IPv4 网络；手动和自动分配 IP；同集群 hostname / IP 唯一；按 hostname、IP、Cluster、Service 查询；多人维护、关键变更记录、逻辑删除和历史追踪；为后续 clusterctl、Ansible、Facts 采集保留扩展能力。

## 3. 一期范围

CONFIRMED 包含：Cluster、Resource、Bare Metal、Virtual Machine、Interface、Network、IP Pool、IP Address、Service、Service Endpoint、Global Search、Audit Log、基础用户权限、CSV / Excel 批量导入。

CONFIRMED 排除：clusterctl、Ansible / ansible-runner、PXE / 操作系统安装、Slurm 自动部署 / 节点加入 / 状态同步、自动硬件发现、Resource Facts 自动采集、Desired State / Actual State、Provisioning、Job / Task 执行系统、n8n Workflow、审批流程、Prometheus / Grafana 监控、自动故障处理、复杂 RBAC、CMDB 采购、固定资产 / 折旧、机房 / 机柜 / U 位、电源和布线管理。这里的“审批流程”指产品功能，不取消工程计划批准和 Review。

## 4. 核心模型

CONFIRMED：裸金属和虚拟机统一为 Resource。

```text
Cluster
├── Resource
│   ├── BareMetalDetail
│   ├── VirtualMachineDetail ── Host Resource
│   ├── Interface ── IPAddress ── Network
│   └── Service ── ServiceEndpoint ── IPAddress
└── Network
    ├── IPPool
    └── IPAddress
```

这是业务关系，不规定表的数量或 Schema 实现方式。

CONFIRMED：内部关联使用稳定 ID，不依赖 hostname、名称或 code 的字符串拼接。时间统一保存，前端按明确时区展示；具体存储/接口表示与展示时区在设计中说明。字段与单位清单由 §35 D01 承接，普通 API 和导入共用。

### 4.1 创建必填项与名称规范

CONFIRMED：对象名称、模型规定的所属对象、Resource 类型、Network CIDR、Pool 起止地址在创建时必填。可选关系沿用对应条款，例如 IPAddress 的 Interface 可空、Interface 的 parent_interface 可空、VM Host 必填。默认值仅用于创建时省略字段，不把省略字段的更新请求解释为重置默认值；具体请求格式由 D01 设计。

CONFIRMED：所有名称去除首尾空白，禁止空字符串和控制字符。hostname 的小写保存及字符规则见 §7；其它名称的唯一性和展示规则如下：

| 名称 | 唯一范围 | 大小写与内部空白 | 删除后复用 |
| --- | --- | --- | --- |
| Interface name | 同 Resource | 区分大小写、保留输入大小写，禁止内部空白 | 允许 |
| Network name | 同 Cluster | 大小写不敏感，允许中文及内部普通空格，不自动合并内部空格 | 允许 |
| IP Pool name | 同 Network | 大小写不敏感，允许中文及内部普通空格，不自动合并内部空格 | 允许 |
| Service name | 同 Resource | 大小写不敏感，允许中文及内部普通空格，不自动合并内部空格 | 允许 |

以上业务名称保留展示形式，唯一性比较使用统一归一化规则，仅未删除对象参与唯一性检查。恢复重新检查冲突，不覆盖已复用名称的对象。Cluster code / name 的例外按 §5；字符长度、数值存储上限及其余格式细节由 D01 统一落实到数据库、API 和导入契约。

## 5. Cluster

CONFIRMED：Cluster 是独立集群资源域，可拥有多个 Resource、Network、IP Address 和 Service。例如 N96、N96P、N1024、B300、山河3、亘聪集群。

至少支持 `name, code, status, description, metadata, created_at, updated_at, deleted_at`。例如 `name=N96P集群, code=N96P, status=ACTIVE`。

CONFIRMED：code 全局唯一，大小写不敏感，创建后不可修改，软删除后不重用；name 为可修改的展示名称，允许中文，不作为关联标识，不强制唯一。状态为 ACTIVE / INACTIVE，默认 ACTIVE。

CONFIRMED：Cluster INACTIVE 仅表达集群已停用，不表示删除或只读。查询、新增、修改、导入、删除及恢复继续按既有权限和完整性规则执行；状态切换不自动修改 Resource / Network / Service 状态，也不释放 IP。默认查询包含未删除的停用集群，支持状态过滤。停止 IP 分配由 Network INACTIVE 控制（§11），不能从 Cluster INACTIVE 推导该限制。

## 6. Resource

CONFIRMED：一期类型仅 `BARE_METAL`、`VIRTUAL_MACHINE`；以后可扩展 STORAGE、SWITCH、APPLIANCE，本期不实现。至少支持 `cluster, hostname, resource_type, role, status, description, metadata, created_at, updated_at, deleted_at`。Role 应可扩展。

CONFIRMED Role：`COMPUTE, LOGIN, MANAGEMENT, STORAGE, SERVICE, GPU, OTHER`。默认 OTHER，不允许显式 null。一个 Resource 记录一个主要 Role；STORAGE 是用途，不代表新增 STORAGE 资源类型。GPU 数量/型号由硬件字段表达，不依据 Role 自动推导。Role 允许后续扩展，一期无需字典管理页面。

CONFIRMED Status：`IDLE, ALLOC, DOWN, UNKNOWN`，默认 UNKNOWN；由人工维护，不表示系统已探测运行状态，不由名称推导 Slurm 同步或自动状态转换。

CONFIRMED：创建后不允许直接修改所属 Cluster 或转换 resource_type。跨集群迁移和类型转换不作为一期直接编辑操作。

## 7. Hostname 唯一性

CONFIRMED：同 Cluster 内 hostname 唯一，不同 Cluster 可同名；逻辑删除后可重用。例如 N96/cn001 与 N96P/cn001 允许并存，同一 N96P 中两个 cn001 不允许。

CONFIRMED：输入去除首尾空白并统一转小写保存；cn001、CN001、` cn001 ` 在同 Cluster 视为相同。支持短主机名和 FQDN，按完整字符串识别，不自动关联为同一机器或合并别名。禁止空值、内部空白和不合法字符；具体字符及长度规则在 API 契约中列明，影响现有命名兼容性时由 Product 核对（§35 D01）。

普通 API、CSV / Excel 导入、搜索和数据库唯一性采用一致的归一化规则。

## 8. Bare Metal

CONFIRMED：公共属性在 Resource，硬件属性在 BareMetalDetail。至少支持 `manufacturer, model, serial_number, cpu_model, cpu_sockets, cpu_cores, memory_mb, gpu_model, gpu_count`。

经常查询、排序、统计的数据必须结构化；厂商特有或低频数据可使用 JSONB。示例 gpu0001：2 × AMD EPYC、192 个物理核心、1536 GiB 内存（memory_mb=1572864）、8 × NVIDIA B300。

CONFIRMED：硬件参数可空，未知值保存为 null，不以 0 表示未知；SN 一期不设置全局唯一约束。数值字段定义如下：

| 字段 | 含义与合法值 |
| --- | --- |
| cpu_sockets | 已安装 CPU 插槽数量；正整数或 null |
| cpu_cores | 整台裸金属的物理核心总数，不含超线程；正整数或 null |
| memory_mb | 保留字段名，单位为 MiB；正整数或 null |
| gpu_count | 非负整数或 null；0 表示明确无 GPU |

CONFIRMED：内存、磁盘统一使用 MiB / GiB 表达二进制容量，1 GiB = 1024 MiB；界面与导入模板明确单位，不混用 MB / GB。完整字段格式和存储上限交 D01，不能改变已确认的单位或用 0 替代未知值。

## 9. Virtual Machine

CONFIRMED：VM 属于 Resource；专有属性至少包括 `host_resource_id, vcpu, memory_mb, disk_gb, hypervisor, metadata`。例如 pve01 下有 vm001、vm002、vm003。

CONFIRMED：VM 容量参数可空。vcpu 表示分配的虚拟 CPU 数，为正整数或 null；memory_mb 单位及范围与 §8 一致；disk_gb 保留字段名，表示分配的虚拟磁盘容量总和，单位 GiB，为非负整数或 null，0 表示明确无磁盘。一期不校验 VM 总 vCPU / 内存是否超过 Host 容量，不承担调度或容量准入。

CONFIRMED：VM 必须关联一个未删除的 BARE_METAL Host，VM 与 Host 必须同 Cluster；禁止 N96P/vm001 指向 N96/cn001。允许在同 Cluster 内更换 Host 并记录审计；此操作只修改资源登记关系，不执行真实 VM 迁移。存在未删除 VM 引用时，Host 不可删除。

## 10. Interface

CONFIRMED：Resource 可有任意数量 Interface，例如 eth0、eth1、ib0、ib1、bond0。至少支持 `resource, name, interface_type, mac_address, speed_mbps, mtu, parent_interface, enabled, description, metadata`。

CONFIRMED Interface Type：`PHYSICAL, VIRTUAL, BOND, BRIDGE, VLAN, LOOPBACK, OTHER`，默认 OTHER，不根据接口名推断。enabled 默认 true，表示登记的启用状态；speed_mbps 表示接口标称速率，单位 Mbps，为正整数或 null，不表示实时流量。类型描述接口本身；不直接定义管理 / 业务 / 存储 / IB 网卡分类，具体 Network 经 IPAddress 关联。

CONFIRMED：Interface Name 的归一化、大小写、唯一性及删除后复用规则见 §4.1。parent_interface 可空；填写时必须属于同 Resource，不能指向自身或形成循环。一期表达基本父子关系，不建设完整 Bond / Bridge / VLAN 拓扑管理。

MAC 允许为空，一期不设置全局唯一约束，避免阻塞不适用该字段的接口登记。

## 11. Network

CONFIRMED：一期只支持 IPv4。每 Cluster 可有多个 Network，例如管理网 10.10.0.0/16、IB 管理网 192.168.0.0/16、业务网 172.16.0.0/16。

至少支持 `cluster, name, cidr, gateway, status, auto_allocate, description, metadata`。PostgreSQL CIDR 为优先存储选择（§26）。以下规则为 CONFIRMED：

* 名称规范、Cluster 内唯一性及删除后复用见 §4.1；同 Cluster 的未删除 Network 不允许 CIDR 重叠，不同 Cluster 允许。INACTIVE 不等于软删除，仍参与重叠检查。
* 已存在未删除 Pool 或 IP 时，禁止直接修改 CIDR 或所属 Cluster；历史引用的保留仍须在数据库设计中说明。
* gateway 可空，填写时必须属于 CIDR，并从可分配地址中排除。
* 状态为 ACTIVE / INACTIVE，默认 ACTIVE。INACTIVE 允许查询和释放已有 IP，禁止新增 IP 分配；释放仍须满足 ADMIN 权限及引用检查。
* auto_allocate 默认 false，仅控制自动分配，不能绕过状态与地址约束。

### 11.1 IPv4 地址边界

CONFIRMED：基础可用地址按 CIDR 前缀确定：

| 前缀 | 基础可用地址 |
| --- | --- |
| /0～/30 | 排除该 CIDR 的网络地址和广播地址 |
| /31 | 两个地址均可用，按点对点网络语义登记 |
| /32 | 唯一地址可用，gateway 必须为空 |

从基础可用地址集合中排除 gateway、RESERVED 池范围及禁用地址，得到可分配集合；自动、手动、恢复与容量统计共用这一边界。gateway 必须属于基础可用地址且不在禁用范围内，设置为某个未删除 IP 的地址时拒绝，包括未绑定 Interface 的占用；冲突处理与并发要求见 §12.1。

CONFIRMED：一期禁止将 `0.0.0.0/8`、`127.0.0.0/8`、`169.254.0.0/16`、`224.0.0.0/4`、`240.0.0.0/4` 用于 IP 分配或 gateway。这是本项目的管理范围选择，不代表回环、链路本地等地址是非法 IPv4。LOOPBACK Interface 仍可登记，但一期不登记其 127.x.x.x 地址。普通私网和公网均可管理，不以是否公网可达作为合法性判断依据。

网络语义参考：[RFC 3021](https://www.rfc-editor.org/rfc/rfc3021) 定义点对点 /31 的两个主机地址；[IANA 特殊用途地址登记表](https://www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xhtml) 说明特殊地址用途。上述一期管理限制以本文件的已确认清单为准。

## 12. IP Pool

CONFIRMED：Network 可以定义一个或多个分配/保留地址池，至少支持 `network, name, start_address, end_address, allocation_mode, description`。

CONFIRMED：Pool 名称规范、Network 内唯一性及删除后复用见 §4.1；起止地址均属于 Network，起始不大于结束。同 Network 的未删除池互不重叠，包括保留池。allocation_mode 默认 MANUAL。

| allocation_mode | 分配行为 |
| --- | --- |
| AUTO | 允许自动或手动分配 |
| MANUAL | 只允许手动分配 |
| RESERVED | 表示保留范围，禁止分配 |

示例：10.10.1.0/24，gateway 10.10.1.1，RESERVED 池 10.10.1.2–10.10.1.49，AUTO 池 10.10.1.50–10.10.1.200。示例不定义统一保留范围。

删除或缩小 Pool 不自动回收已分配 IP，原 IP 记录继续管理占用；分配来源作为历史保留，不能由 Pool 删除隐式删除或释放 IP。这是 §21 引用检查中对分配来源关系的明确例外。

### 12.1 保留范围及网关变更冲突

CONFIRMED：保留已有占用，不静默回收或隐藏冲突。

| 操作 | 行为 |
| --- | --- |
| 新建或扩大 RESERVED 池 | 变更后的范围内存在未删除 IP 时拒绝，包括未绑定 Interface 的占用 |
| AUTO / MANUAL 改为 RESERVED | 范围内存在未删除 IP 时拒绝 |
| 将已占用 IP 设为 gateway | 拒绝，包括未绑定 Interface 的占用 |
| AUTO 与 MANUAL 相互切换 | 满足其它约束后允许，不改变已有 IP |
| 删除或缩小 Pool | 满足其它约束后允许，已有 IP 继续占用并保留分配来源历史 |
| RESERVED 改为 AUTO / MANUAL | 满足其它约束后允许 |

拒绝时返回冲突数量及可查询的冲突明细。需要改变地址用途时，先按正常权限处理 Endpoint、释放 IP，再重试。冲突检查与变更必须具备并发保护，不能在检查后被并发分配绕过；具体事务、约束及锁方案由 D02 设计。恢复对象同样遵循适用完整性规则（§21），不能通过恢复保留池或网关配置绕过占用检查。

## 13. IP Address

CONFIRMED：IPAddress 是独立于 Interface 的对象，通过 Network → IPAddress → Interface 关联；Resource 可有多接口，一个 Interface 可有多个 IP。Interface 允许为空，表示 IP 已占用但尚未绑定；未绑定并不代表可再次分配。

### 13.1 自动分配

CONFIRMED：Network 为 ACTIVE、auto_allocate 开启、指定 Pool 为 AUTO 时才能自动分配。按地址升序选择符合全部约束的可用地址；并发请求不能分配出重复 IP。指定池耗尽时返回“无可用地址”，不自动改用其它池。

### 13.2 手动分配

CONFIRMED：用户输入 IPv4，系统检查合法性和冲突。允许在 AUTO / MANUAL 池内或池外手动分配，但必须属于 ACTIVE Network，不能分配 gateway、RESERVED 池范围或其它禁用地址。auto_allocate 控制自动分配，不代替手动分配校验。

### 13.3 解绑与释放

CONFIRMED：解绑只移除 Interface 关系，IP 记录继续占用；释放是软删除 IP 记录，按 ADMIN 删除权限控制。解绑、转移或释放 IP 前必须先处理引用它的 Endpoint。删除后的 IP 可重新分配；恢复旧 IP 时重新检查冲突，不覆盖新占用记录。

## 14. IP 完整性

CONFIRMED：IP 必须属于关联 Network 的 CIDR。同 Cluster 全局 IP 唯一，即使经不同 Network / Pool 分配也不能重复；不同 Cluster 可使用相同 IP。

所有 IP 必须满足 `IPAddress.cluster == Network.cluster`；绑定 Interface 时还必须满足 `IPAddress.cluster == Interface.Resource.cluster`，禁止跨 Cluster 分配。未绑定 IP 不免除 Network / Cluster 一致性、唯一性和地址合法性校验。自动、手动分配及恢复均遵循适用完整性规则。

## 15. Service

CONFIRMED：Resource 维护其运行的 Service，如 SSH、slurmd、node_exporter、DCGM Exporter；至少支持 `resource, name, status, description, metadata`。登记 slurmd 不包含 Slurm 自动部署或状态同步。

CONFIRMED：Service 名称规范、Resource 内唯一性及删除后复用见 §4.1。状态为 RUNNING / STOPPED / UNKNOWN，默认 UNKNOWN，由人工维护，不表示系统已探测实际进程状态。

## 16. Service Endpoint

CONFIRMED：监听地址和端口独立建模，Resource → Service → ServiceEndpoint。至少支持 `service, ip_address, protocol, port, description`；一个 Service 可有多个 Endpoint，例如 Web 的 TCP/80、TCP/443，Grafana 的 10.10.1.20:3000。

Endpoint 的 IP 必填、未删除，且必须绑定在 Service 所属 Resource 的 Interface 上。协议仅 TCP / UDP，端口为 1–65535。同一有效 IP 上的 protocol + port 不允许重复登记监听入口，包括同一 Service 的重复 Endpoint；不同 Cluster 的同值 IP 是不同 IP 对象。

一期不支持 0.0.0.0、空监听地址、Unix Socket 或跨资源共享 VIP。IP 解绑、转移或释放前须先处理引用它的 Endpoint。

## 17. 全局搜索

CONFIRMED：首页统一搜索入口，至少支持 hostname、IP、Cluster、Service，并能找到对应 Resource。搜索框与下拉选择均允许输入和模糊搜索，如 gpu07 匹配 gpu0701、gpu0702、gpu0725。

SN、MAC、Role、GPU Model 搜索为后续扩展，本期不强制。数据库使用 pg_trgm（§26）；GIN Index 为建议方案，具体索引在数据库设计中签核。

## 18. Resource Detail

CONFIRMED：核心详情页包含 Overview、Hardware、Interfaces、IP Addresses、Virtual Machines、Services、Activity。

Overview 显示 Hostname / Cluster / Type / Role / Status / Description；Hardware 显示 CPU / Memory / GPU / Manufacturer / Model / SN；Interfaces 显示 Interface / MAC / Speed / MTU / IP / Network。裸金属展示其 VM；VM 展示 Host，例如 pve01。具体不适用区域的展示方式由前端设计说明。

## 19. Cluster Detail

CONFIRMED：展示 Resources、Networks、IP Addresses、Virtual Machines、Services；按 Resource Type、Role、Status、Hostname 过滤，支持组合条件，例如 N96P + COMPUTE + IDLE。

## 20. Dashboard

CONFIRMED：简单展示 Cluster / Resource / BareMetal / VM / Network 数量及 IP 使用情况，同时提供全局搜索。不是监控面板，不承担 Grafana 职责。

分别展示 Network 可分配地址总量、已占用量、剩余可用量，以及 AUTO 池可分配总量和剩余可用量。占用按未删除 IP 记录计算，包含尚未绑定 Interface 的 IP；软删除 IP 不计占用。Network 口径包括允许手动分配的池外地址，AUTO 池口径仅计该池范围，不以整个 CIDR 大小替代池容量。gateway、RESERVED 及禁用地址从可分配范围排除。

CONFIRMED：基础可用地址及禁用范围按 §11.1，容量公式为：

```text
可分配集合 = 基础可用地址集合 − gateway − RESERVED 池范围 − 禁用地址
可分配总量 = 可分配集合中的地址数量
已占用量 = 该 Network 下未删除 IP 数量（包含未绑定 Interface 的 IP）
剩余可用量 = 可分配总量 − 已占用量
AUTO 池可分配总量 = 该池范围与 Network 可分配集合的交集数量
AUTO 池剩余可用量 = AUTO 池可分配总量 − 当前位于该交集的未删除 IP 数量
```

排除项按集合去重，gateway 同时位于 RESERVED 池时不重复扣减；池占用按当前地址所在范围计算，不按历史分配来源计算。容量与 ACTIVE / INACTIVE、auto_allocate 的操作许可分别展示，停用不会把容量或占用清零。

## 21. 逻辑删除

CONFIRMED：Cluster、Resource、Interface、Network、IPPool、IPAddress、Service、ServiceEndpoint 使用 `deleted_at` 逻辑删除，默认查询隐藏已删除数据。删除后 hostname、IP Address 可重用，并保留历史追踪。Interface / Network / IP Pool / Service 名称复用按 §4.1；Cluster code 不重用（§5）。

CONFIRMED：一期 ADMIN 可以查看并恢复已删除对象，替代原文“未来恢复”的表述。删除与恢复规则如下：

* 有未删除的依赖对象引用时禁止删除，返回引用列表；一期不做隐式级联删除。例如有 VM 的 Host、有 IP 的 Interface、有 Endpoint 的 Service 或 IP 须先处理引用。
* BareMetalDetail / VirtualMachineDetail 跟随 Resource 生命周期，不提供独立删除入口；这些类型专有明细不作为阻止 Resource 删除的独立子对象。
* IPPool 的分配来源关系按 §12 例外处理：删除池不删除或释放已经分配的 IP。
* 恢复只恢复当前对象，不自动恢复相关对象；重新检查唯一性、所属对象有效性和关系约束。标识已被重用或依赖对象仍被删除时恢复失败，不能覆盖新对象。
* Audit Log 保留，不纳入业务对象软删；用户账号采用停用，保留历史操作者身份。

## 22. Audit Log

CONFIRMED：关键数据修改记录 `operator, action, object_type, object_id, before_data, after_data, created_at`，操作类型至少包括 CREATE、UPDATE、DELETE、RESTORE。例如 user01 将 cn001.status 从 IDLE 改为 DOWN。

CONFIRMED：一期恢复按 §21 执行并记录 RESTORE；同集群更换 VM Host 等关键关系变更也须记录。资源 Activity 展示业务字段变化，所有基础角色均可查看；完整 Audit 查询限 ADMIN。不得展示或记录密码、令牌等敏感认证内容，保留历史操作者身份，具体脱敏/事务实现由架构设计说明。

CONFIRMED：一期 Audit 持续保留，不设置到期自动清理；不提供修改、删除或批量清空入口，包括 ADMIN。业务对象删除、恢复、名称复用和用户停用不影响已有审计；数据库备份必须包含 Audit。后续有容量压力时，归档和保留期限作为独立变更确认后实施，不在一期预建清理任务或归档系统。

## 23. 用户与权限

CONFIRMED：一期仅基础角色，不实现 Cluster 级复杂 RBAC。

| 操作 | VIEWER | EDITOR | ADMIN |
| --- | --- | --- | --- |
| 查询、搜索、详情 | 允许 | 允许 | 允许 |
| 查看资源变更记录 | 允许 | 允许 | 允许 |
| 新增、修改业务对象，分配及解绑 IP | 不允许 | 允许 | 允许 |
| CSV / Excel 资源导入 | 不允许 | 允许 | 允许 |
| 删除、释放 IP、查看已删除对象、恢复 | 不允许 | 不允许 | 允许 |
| 用户、角色、系统设置、完整审计查询 | 不允许 | 不允许 | 允许 |

CONFIRMED：一期本地账号登录，部署时初始化首个 ADMIN，不开放自行注册。业务对象指一期范围内的 Cluster、Resource、Interface、Network、IPPool、IPAddress、Service、ServiceEndpoint；权限仍受对象状态、不可变字段和关系约束限制。删除及 IP 释放统一按 ADMIN 权限，EDITOR 的解绑不能隐式释放地址。

CONFIRMED：多人编辑使用版本冲突检查。提交的版本过期时拒绝覆盖，提示刷新后重新修改；前端不能静默用新版本重试覆盖。具体认证、版本标识、错误码及审计一致性由 Architect 在契约中设计，服务端必须执行鉴权和冲突检查。

## 24. 批量导入

CONFIRMED：支持 CSV 和 Excel `.xlsx`，一期只做资源新增导入，不按 hostname 自动更新或覆盖现有资源。提供固定模板与逐列说明；示例列 `cluster, hostname, resource_type, role, status, manufacturer, model, cpu_model, cpu_cores, memory_mb, gpu_model, gpu_count`，VM 模板须含 Host 引用，完整模板由 §35 D03 承接。

Interface、IPAddress、Network 导入为后续扩展。导入必须走与普通 API 相同的 Service Layer 业务校验，禁止跳过服务层直接写数据库。

CONFIRMED 导入流程：

1. 校验并展示错误行，再由用户确认导入；文件内重复、现存资源冲突、非法字段/关系均报错。错误至少含行号、字段、原因。
2. 正式写入时再次校验，防止预校验后状态变化。整批成功或整批回滚，不产生部分成功；回滚不能留下未成功创建对象的业务变更记录。
3. VM Host 必须已存在且满足 §9；首次迁移先导入裸金属，再导入 VM，不在同一批次隐式创建 Host。
4. 一期同步处理，设置文件大小和行数上限；具体上限由部署资源和性能验证确定并记入契约。预校验与写入同样执行 §23 的权限检查。

## 25. API

CONFIRMED：REST API，Resource 支持组合过滤，不按每种查询场景另建接口。

CONFIRMED：统一前缀 `/api/v1/`，核心路径为 `/api/v1/clusters`、`resources`、`interfaces`、`networks`、`ip-pools`、`ip-addresses`、`services`、`search`、`audit`（均沿用同一前缀）。示例 `GET /api/v1/resources?cluster=N96P&type=BARE_METAL&role=COMPUTE&status=IDLE`。

路径示例不是完整 Contract；Endpoint、用户管理、导入等能力也必须有相应契约。分页、排序、错误、nullable 与权限由已签核 Contract 明确。

## 26. 数据库

CONFIRMED：PostgreSQL、SQLAlchemy 2.x、Alembic；扩展信息用 JSONB，模糊搜索用 pg_trgm。IP / 网段字段优先使用 PostgreSQL INET / CIDR，偏离需有明确设计依据；GIN 索引仍为建议。

数据库与技术栈已经确认；具体约束、索引和 Migration 仍需正式设计，不能把需求字段直接当成获批 Schema。GIN 等具体索引选择由数据库角色按查询和验证结果签核。

## 27. 数据完整性

CONFIRMED：数据库与业务层共同保证 §5–16、§21 的唯一性、关系与生命周期规则；关键唯一性由 PostgreSQL 兜底，不只前端检查。必须保障 hostname 归一化后的唯一性、自动 IP 分配不重复、VM Host 类型及所属 Cluster 正确、IP 属于 CIDR、绑定前后 Cluster 一致性、Network/Pool 不重叠、Endpoint 归属与监听唯一性，以及删除后标识按对象规则重用。

具体数据库约束方案由设计决定，并在真实 PostgreSQL 上验证。

## 28. 前端

CONFIRMED：运维资源查询与维护控制台，强调快速、清晰、高效查询与低操作成本。主要页面 Dashboard、Search、Clusters / Cluster Detail、Resources / Resource Detail、Networks / IPAM、Services、Audit、System。

列表页至少分页、排序、过滤、模糊搜索；不追求复杂视觉效果。

## 29. 技术栈

CONFIRMED：前端 React / TypeScript / Vite；后端 Python / FastAPI / Pydantic；测试 pytest；入口代理 Nginx。

CONFIRMED：数据库相关选型按 §26，Docker Compose 部署按 §30。一期暂不引入 Redis、RabbitMQ、Kafka、ElasticSearch、Kubernetes、Celery。具体软件版本、目录结构、连接池、索引和锁策略由 Architect / Database 在已确认边界内设计签核，不作为待用户重复确认的技术栈问题；替换已确认选型仍按变更控制处理。

## 30. 部署

CONFIRMED：第一阶段通过 `docker compose up -d` 启动基础服务，采用 Nginx → Frontend / FastAPI → PostgreSQL 的部署方案。配置、建库 / Migration、首个 ADMIN 初始化与凭据传入方式等由后续设计说明；不在仓库保存真实初始凭据。

## 31. 测试

CONFIRMED：除 API 基础测试，至少验证以下业务用例。

| ID | 用例及预期 |
| --- | --- |
| T01 | 同 Cluster hostname 重复创建失败 |
| T02 | 不同 Cluster 同 hostname 允许 |
| T03 | Soft Delete 后 hostname 可重新创建 |
| T04 | 同 Cluster 重复 IP 失败 |
| T05 | 不同 Cluster 同 IP 允许 |
| T06 | 不属于 Network CIDR 的 IP 分配失败 |
| T07 | 自动 IP 分配不会冲突，包含并发验证 |
| T08 | VM Host 为 VM 时创建失败 |
| T09 | VM / Host 跨 Cluster 创建失败 |
| T10 | Interface 跨 Cluster 绑定 IP 失败 |
| T11 | hostname 大小写及首尾空白归一化；API 与导入不能绕过同一唯一性规则 |
| T12 | 同 Resource Interface 名称重复失败；删除后 IP / Interface Name 可重用 |
| T13 | Cluster code 大小写不敏感、全局唯一且删除后不能重用；创建后不可直接修改 |
| T14 | 同 Cluster Network 重叠失败，不同 Cluster 允许；有 Pool / IP 时不能直接修改 CIDR / Cluster |
| T15 | Pool 越界、起止逆序、有效池重叠失败；AUTO / MANUAL / RESERVED 分配行为符合 §12 |
| T16 | INACTIVE Network 禁止新增分配；关闭 auto_allocate 禁止自动分配；指定池耗尽不切换其它池 |
| T17 | 手动池外合法地址允许，gateway / RESERVED 地址分配失败；AUTO 按升序选择可用地址 |
| T18 | 未绑定 IP 仍占用；解绑不释放；删除/缩小 Pool 不回收已有 IP；容量按 Network / AUTO 池分别计算 |
| T19 | VM 缺失/引用已删除 Host 失败；同 Cluster 换 Host 记录审计；Resource 不能直接改 Cluster / 类型 |
| T20 | parent_interface 跨 Resource、自引用或环路失败；MAC 为空不阻塞合法接口登记 |
| T21 | Service 名称归一化后同 Resource 重复失败；状态默认值及人工维护行为符合 §6、§15 |
| T22 | Endpoint 空 IP、其它资源 IP、非法协议/端口或重复监听入口失败；有 Endpoint 引用时不能解绑/转移/释放 IP |
| T23 | 存活引用阻止删除并返回引用列表；无隐式级联；类型明细跟随 Resource，Pool 来源关系按明确例外处理 |
| T24 | ADMIN 可查看及恢复已删除对象；恢复不自动恢复关联对象；标识重用或依赖仍被删除时恢复失败 |
| T25 | 权限矩阵在服务端执行；EDITOR 可导入/解绑，不能删除/释放/恢复；VIEWER 可查看资源 Activity，不能查询完整 Audit |
| T26 | 过期版本编辑被拒绝，无静默覆盖；审计保留历史操作者，不记录或展示密码/令牌 |
| T27 | CSV / .xlsx 新增导入先校验后确认并再次校验；任一写入失败整批回滚，重复/非法行返回行号、字段、原因 |
| T28 | VM 导入 Host 必须已存在；导入不更新/覆盖现存资源；文件/行数上限按签核契约验证 |
| T29 | Cluster INACTIVE 下仍按既有权限允许查询、新增、修改、导入、删除及恢复；默认查询包含停用集群且可过滤；切换状态不级联改变对象状态或释放 IP，Network 自身停用仍阻止分配 |
| T30 | /0～/30 排除本 CIDR 网络/广播地址；/31 两地址按点对点语义可用；/32 唯一地址可用且禁止 gateway；自动、手动及恢复共用边界 |
| T31 | §11.1 每个禁用范围的边界地址均禁止分配及用作 gateway；普通合法私网/公网允许；LOOPBACK 接口可登记但 127.x.x.x 不进入 IP 台账 |
| T32 | Network / AUTO 池容量按集合计算；gateway 与 RESERVED 重叠不重复扣减；未绑定 IP 计占用，池外手动 IP 计 Network 占用；当前池内占用不依赖分配来源；停用不清零容量或占用 |
| T33 | 新建/扩大 RESERVED 池、AUTO/MANUAL 改为 RESERVED、设置已占用 gateway 均拒绝并返回冲突数量与可查询明细，包含未绑定 IP；合法释放后可重试 |
| T34 | AUTO/MANUAL 互换、RESERVED 改为 AUTO/MANUAL 满足约束后允许；删除/缩小池不回收 IP 且保留来源历史；恢复不能绕过保留范围/网关占用检查 |
| T35 | 保留范围或 gateway 变更与并发 IP 分配不能同时成功形成冲突；事务失败不能留下部分变更或错误容量 |
| T36 | Audit 不自动过期；包括 ADMIN 在内均无修改、删除、清空入口；业务对象删除/恢复/名称复用及账号停用不改变旧审计；备份覆盖 Audit |
| T37 | §6、§10–12 默认值在创建省略字段时生效；Role 显式 null 被拒绝；接口类型不由名称推断；API 与资源导入按各自适用字段采用相同规则 |
| T38 | §4.1 必填项缺失失败；硬件和 VM 容量未知为 null；正整数、非负整数规则及零值含义符合 §8–10；memory_mb / disk_gb 的单位、转换、展示和导入一致 |
| T39 | cpu_cores 表示整机物理核心总数，不含超线程；VM 登记不因总 vCPU/内存超过 Host 容量而被拒绝；speed_mbps 表示标称速率而非实时流量 |
| T40 | 名称去首尾空白，空名/控制字符失败；Interface 内部空白失败且名称区分大小写；Network/Pool/Service 大小写不敏感，保留中文和内部普通空格，不自动合并内部空格 |
| T41 | Network/Pool/Service 删除后名称可复用，作用域内存活对象仍保证唯一；名称被复用时旧对象恢复失败且新对象不被覆盖；Cluster code 仍不可复用 |

还须覆盖查询关系、列表交互、本地登录和初始 ADMIN、时间契约及真实 Compose 部署。D01–D03 专业设计完成后细化对应测试步骤与数据，不把尚未执行的预期写成 PASS。本节定义必须执行的用例，不是已经执行的测试报告。

## 32. 上线验收

CONFIRMED：能创建 Cluster、BareMetal、VM 并关联 Host，维护 Interface / Network / Pool / Service，手动和自动分配 IP；按 hostname / IP / Cluster / Service 找到 Resource；详情显示 Cluster / 硬件 / Interface / IP / Network / VM 或 Host / Service。

能阻止重复 hostname / IP、跨 Cluster Host / IP 绑定及非法 CIDR 地址；提供逻辑删除及 ADMIN 恢复、Audit Log、基础权限、本地登录、编辑版本冲突检查和 CSV / .xlsx 整批新增导入。Network / Pool、Endpoint 及恢复行为满足本 revision 的约束，包括地址边界与容量、保留范围/网关并发冲突、Cluster 停用维护、字段单位与名称规则；审计持续保留且纳入备份。一期范围内的全部必需能力不能因优先级低而从上线验收中删除。§31 与以上验收都需真实证据；上线条件不等于自动发布授权。

## 33. 目标查询场景

CONFIRMED：能够快速可靠地回答：hostname 属于哪个集群；某 IP 是哪台机器；cn001 的管理网和 IB 地址；vm001 的宿主机；pve01 下有哪些 VM；Network 剩余可用 IP；IP 是否被使用；机器运行哪些 Service；谁修改了服务器信息。

## 34. 后续扩展

未来可由 clusterctl 经 Resource API 使用 CSM 数据，再通过 ansible-runner 操作节点；Ansible / Agent 可回传 Resource Facts。CSM 作为 Source of Truth，clusterctl 作为 Automation Engine。本期仅保持合理扩展能力，不实现这些功能，也不预建 Job / Workflow / Facts 子系统。

## 35. 确认记录与设计输入

### 35.1 本次确认记录

确认者：用户。对象路径：`docs/product/requirements-v3.md`。以下记录仅批准相应产品规则，不包含 Feature 计划批准或应用实施授权。

| revision / 日期 | 确认范围与来源 |
| --- | --- |
| revision 2 / 2026-10-06 | 用户在收到 Q01–Q10 推荐规则后回复“按照推荐的建议进行修改”；替代 revision 1 中对应建议/冲突条款 |
| revision 3 / 2026-10-06 | 用户在收到剩余六项逐项建议后回复“按照推荐建议修改这6项”；确认 Q02-A、Q04-A、Q04-B、Q07-A、Q10-A、Q10-B，替代 revision 2 对这些问题的 OPEN 描述；具体决策索引见 §35.2 |

| 原 ID | 已确认内容所在条款 | 尚需处理的部分 |
| --- | --- | --- |
| Q01 | §7 归一化、短名/FQDN、入口一致性 | D01 字符/长度契约，不再询问是否大小写敏感 |
| Q02 | §5–6、§10–11、§15 枚举、主要 Role、状态默认及人工维护 | Q02-A / Q10-A 已在 revision 3 确认；完整字段契约交 D01 |
| Q03 | §12、§21 一期恢复、软删清单、引用检查及例外、恢复冲突 | 本轮列出的删除/恢复规则已确认 |
| Q04-NETWORK | §11 名称唯一、CIDR 重叠、网关及停用限制 | Q04-A / Q04-B 已在 revision 3 确认 |
| Q04-POOL | §12 范围、互不重叠、AUTO / MANUAL / RESERVED | Q04-B 已确认；并发机制交 D02 |
| Q04-ALLOCATION | §13.1–13.2 自动条件、升序、耗尽、手动池外分配 | Q04-A 地址边界已确认 |
| Q04-RELEASE | §13.3 未绑定占用、解绑/释放、Endpoint 引用、池变更不回收 | 已确认，不将解绑等同释放 |
| Q04-CAPACITY | §20 Network / AUTO 池独立口径、未绑定占用 | Q04-A / Q04-B 已确认，完整计数公式见 §20 |
| Q05 | §6、§9–10 Host 必填/换宿主、所属 Cluster/类型不可直接改、父接口约束 | 本轮列出的关系规则已确认 |
| Q06 | §15–16 Service 名称、Endpoint IP 归属/必填、协议/端口/重复、一期排除项 | 已确认 |
| Q07 | §21–23 本地账号、初始 ADMIN、权限矩阵、Activity / Audit、敏感认证内容、编辑版本冲突 | Q07-A 已确认；认证/版本机制及备份方案交 D02 |
| Q08 | §24 CSV / .xlsx 新增、预校验/再次校验、整批事务、Host 已存在、同步处理 | D03 模板/性能上限 |
| Q09 | §25–26、§29–30 API 前缀、技术栈、Compose 部署方案 | D02 软件版本/架构设计；不重复请求选型批准 |
| Q10 | §4–5、§8、§10–12 稳定 ID、code/name、名称作用域、未知值、SN/MAC、时间 | Q10-A / Q10-B 已确认；完整字段契约交 D01 |

### 35.2 六项业务决策（CONFIRMED）

本次六项业务问题均已关闭，当前无登记中的 OPEN 业务问题。以下仅保存决策与正文、验收的映射，不复制完整规则。新发现的业务歧义按变更控制处理，不能静默改写本基线或将专业设计输入等同于新的业务待决项。

| ID | 状态 / 权威条款 | 验收映射 |
| --- | --- | --- |
| Q02-A | CONFIRMED；§5 Cluster 停用仅表达状态，继续按既有规则维护 | T29 |
| Q04-A | CONFIRMED；§11.1 IPv4 边界、禁用清单与 gateway；§20 容量公式 | T30–T32 |
| Q04-B | CONFIRMED；§12.1 保留范围/网关占用冲突及并发保护 | T33–T35 |
| Q07-A | CONFIRMED；§22 Audit 持续保留、无清理入口及备份要求 | T36 |
| Q10-A | CONFIRMED；§4.1、§6、§8–12 必填、默认值、数值含义及单位 | T37–T39 |
| Q10-B | CONFIRMED；§4.1、§21 名称规范、唯一性、复用与恢复 | T40–T41 |

### 35.3 专业设计输入（OPEN，按职责签核）

以下为已确认范围内尚未完成的技术设计，不要求用户逐项重新批准。设计发现新的业务限制或重大架构变化时，才返回相应裁定。

| ID | 待交付内容 | 责任 |
| --- | --- | --- |
| D01 | 完整字段字典、hostname 字符/长度、数值存储上限及其它格式契约、时间存储/接口表示/展示时区；落实已确认 Q10-A / Q10-B，生成统一 API 与导入校验规则 | Architect / Database；涉及命名兼容或业务口径时由 Product 核对 |
| D02 | 软件具体版本、模块/目录、认证与初始账号、版本冲突及错误语义、敏感字段处理、审计一致性与备份方案、约束/索引/连接池/锁策略与 Migration；覆盖分配与保留范围/网关变更的并发保护 | Architect / Database 在确认技术栈内专业签核 |
| D03 | CSV / .xlsx 固定模板、VM Host 引用列和逐列说明、同步导入的大小/行数上限及性能验证依据 | Architect / Backend / Tester，业务字段依 D01 |

## 36. 文档建立状态

本次更新需求基线至 revision 3，关闭六项业务问题并同步流程引用；D01–D03 仍为 OPEN 专业设计输入。领域文档提供本文件的规则索引；架构 ADR、数据库 Schema、API Contract、部署实现和完整 Feature 计划尚未建立。项目计划为未批准空骨架，引用需求 revision 3，派生视图由脚本生成并标明尚未规划；不标 READY / DONE，不回查旧版本补齐。§31 的 T01–T41 是未来验收要求，尚未运行应用测试。
