# CSM V3 一期需求

版本：V3 phase 1 / revision 1。来源：用户于 2026-10-06 提供的《CSM V3 一期需求说明》及本次文档更新指令。

本文件是一期范围、产品规则和验收要求的权威来源。原说明正文中的“CSM V1”统一解释为标题指定的“CSM V3 一期”；REST 路径的 `/api/v1/` 是建议的 API 版本，不随产品版本改成 v3。

明确要求标为 CONFIRMED；原文“建议”保留为 PROPOSED；冲突和影响行为的缺项汇总于 §35，状态为 OPEN。本次确认的是需求文档维护，不代表项目计划、建议方案或应用实施已经获批。以下字段清单表示至少支持的属性，不自行确定 nullable、默认值或数据库表结构。

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

## 5. Cluster

CONFIRMED：Cluster 是独立集群资源域，可拥有多个 Resource、Network、IP Address 和 Service。例如 N96、N96P、N1024、B300、山河3、亘聪集群。

至少支持 `name, code, status, description, metadata, created_at, updated_at, deleted_at`。示例 `name=N96P集群, code=N96P, status=ACTIVE` 不意味着完整状态枚举或默认值已确定。

## 6. Resource

CONFIRMED：一期类型仅 `BARE_METAL`、`VIRTUAL_MACHINE`；以后可扩展 STORAGE、SWITCH、APPLIANCE，本期不实现。至少支持 `cluster, hostname, resource_type, role, status, description, metadata, created_at, updated_at, deleted_at`。Role 应可扩展。

PROPOSED Role：`COMPUTE, LOGIN, MANAGEMENT, STORAGE, SERVICE, GPU, OTHER`。其中 STORAGE 是用途建议，不代表新增 STORAGE 资源类型。

PROPOSED Status：`IDLE, ALLOC, DOWN, UNKNOWN`，后续可扩展；不由这些名称推导 Slurm 同步或自动状态转换。

## 7. Hostname 唯一性

CONFIRMED：同 Cluster 内 hostname 唯一，不同 Cluster 可同名；逻辑删除后可重用。例如 N96/cn001 与 N96P/cn001 允许并存，同一 N96P 中两个 cn001 不允许。

PROPOSED：hostname 不区分大小写，cn001 与 CN001 在同 Cluster 视为相同。该建议须确认后才能成为永久校验规则，见 Q01。

## 8. Bare Metal

CONFIRMED：公共属性在 Resource，硬件属性在 BareMetalDetail。至少支持 `manufacturer, model, serial_number, cpu_model, cpu_sockets, cpu_cores, memory_mb, gpu_model, gpu_count`。

经常查询、排序、统计的数据必须结构化；厂商特有或低频数据可使用 JSONB。示例 gpu0001：2 × AMD EPYC、192 cores、1536 GB、8 × NVIDIA B300；展示单位与 `memory_mb` 的换算应由契约说明，不由示例推导精度规则。

## 9. Virtual Machine

CONFIRMED：VM 属于 Resource；专有属性至少包括 `host_resource_id, vcpu, memory_mb, disk_gb, hypervisor, metadata`。例如 pve01 下有 vm001、vm002、vm003。

VM Host 必须为 BARE_METAL，VM 与 Host 必须同 Cluster；禁止 N96P/vm001 指向 N96/cn001。Host 是否允许暂空等细节见 Q05。

## 10. Interface

CONFIRMED：Resource 可有任意数量 Interface，例如 eth0、eth1、ib0、ib1、bond0。至少支持 `resource, name, interface_type, mac_address, speed_mbps, mtu, parent_interface, enabled, description, metadata`。

PROPOSED Interface Type：`PHYSICAL, VIRTUAL, BOND, BRIDGE, VLAN, LOOPBACK, OTHER`。类型描述接口本身；不直接定义管理 / 业务 / 存储 / IB 网卡分类，具体 Network 经 IPAddress 关联。

CONFIRMED：同 Resource 的 Interface Name 唯一，不同 Resource 可同名；删除后名称可重用（§21）。父接口的范围和拓扑约束见 Q05。

## 11. Network

CONFIRMED：一期只支持 IPv4。每 Cluster 可有多个 Network，例如管理网 10.10.0.0/16、IB 管理网 192.168.0.0/16、业务网 172.16.0.0/16。

至少支持 `cluster, name, cidr, gateway, status, auto_allocate, description, metadata`。PostgreSQL CIDR 为优先存储选择（§26）；名称唯一范围、CIDR 重叠及 gateway 规则见 Q04。

## 12. IP Pool

CONFIRMED：Network 可以定义一个或多个可分配地址池，至少支持 `network, name, start_address, end_address, allocation_mode, description`。

示例：10.10.1.0/24，gateway 10.10.1.1，保留范围 10.10.1.2–10.10.1.49，自动池 10.10.1.50–10.10.1.200。示例不定义统一保留范围；池重叠、保留地址和 allocation_mode 语义见 Q04。

## 13. IP Address

CONFIRMED：IPAddress 是独立于 Interface 的对象，通过 Network → IPAddress → Interface 关联；Resource 可有多接口，一个 Interface 可有多个 IP。是否允许未绑定的 IP 记录见 Q04。

分配支持 AUTO / MANUAL：AUTO 从指定 IP Pool 查找可用地址分配；MANUAL 由用户输入 IPv4，系统检查合法性与冲突。

## 14. IP 完整性

CONFIRMED：IP 必须属于关联 Network 的 CIDR。同 Cluster 全局 IP 唯一，即使经不同 Network / Pool 分配也不能重复；不同 Cluster 可使用相同 IP。

必须满足 `IPAddress.cluster == Network.cluster == Interface.Resource.cluster`，禁止跨 Cluster 分配。自动分配也必须满足这些规则并防止并发重复。

## 15. Service

CONFIRMED：Resource 维护其运行的 Service，如 SSH、slurmd、node_exporter、DCGM Exporter；至少支持 `resource, name, status, description, metadata`。登记 slurmd 不包含 Slurm 自动部署或状态同步。

## 16. Service Endpoint

CONFIRMED：监听地址和端口独立建模，Resource → Service → ServiceEndpoint。至少支持 `service, ip_address, protocol, port, description`；一个 Service 可有多个 Endpoint，例如 Web 的 TCP/80、TCP/443，Grafana 的 10.10.1.20:3000。IP 归属、协议集合和重复规则见 Q06。

## 17. 全局搜索

CONFIRMED：首页统一搜索入口，至少支持 hostname、IP、Cluster、Service，并能找到对应 Resource。搜索框与下拉选择均允许输入和模糊搜索，如 gpu07 匹配 gpu0701、gpu0702、gpu0725。

SN、MAC、Role、GPU Model 搜索为后续扩展，本期不强制。数据库使用 pg_trgm（§26）；GIN Index 为建议方案，具体索引在数据库设计中签核。

## 18. Resource Detail

CONFIRMED：核心详情页包含 Overview、Hardware、Interfaces、IP Addresses、Virtual Machines、Services、Activity。

Overview 显示 Hostname / Cluster / Type / Role / Status / Description；Hardware 显示 CPU / Memory / GPU / Manufacturer / Model / SN；Interfaces 显示 Interface / MAC / Speed / MTU / IP / Network。裸金属展示其 VM；VM 展示 Host，例如 pve01。具体不适用区域的展示方式由前端设计说明。

## 19. Cluster Detail

CONFIRMED：展示 Resources、Networks、IP Addresses、Virtual Machines、Services；按 Resource Type、Role、Status、Hostname 过滤，支持组合条件，例如 N96P + COMPUTE + IDLE。

## 20. Dashboard

CONFIRMED：简单展示 Cluster / Resource / BareMetal / VM / Network 数量及 IP 使用情况，同时提供全局搜索。不是监控面板，不承担 Grafana 职责。IP 使用与可用量的分母 / 保留地址口径见 Q04。

## 21. 逻辑删除

CONFIRMED：核心对象使用 `deleted_at` 逻辑删除，默认查询隐藏已删除数据。删除后 hostname、IP Address、Interface Name 可重用，并保留历史追踪。

原文称“管理员未来可以支持查看和恢复已删除对象”，与 §22 RESTORE 审计、§23 ADMIN 删除/恢复权限存在一期范围歧义。恢复入口、冲突处理及删除关联行为见 Q03；不得默认级联删除、永久删除或重用后恢复覆盖新对象。

## 22. Audit Log

CONFIRMED：关键数据修改记录 `operator, action, object_type, object_id, before_data, after_data, created_at`，操作类型至少包括 CREATE、UPDATE、DELETE、RESTORE。例如 user01 将 cn001.status 从 IDLE 改为 DOWN。

RESTORE 的执行功能范围以 Q03 裁定为准，审计类型要求不能独自证明恢复流程已确定。审计可见范围、保留与敏感字段处理见 Q07。

## 23. 用户与权限

CONFIRMED：一期仅基础角色，不实现 Cluster 级复杂 RBAC。

| 角色 | 权限 |
| --- | --- |
| VIEWER | 查询、搜索、查看详情 |
| EDITOR | 新增/修改资源、新增 Interface、维护 Network、分配 IP、维护 VM、维护 Service |
| ADMIN | EDITOR 能力及用户管理、权限管理、删除/恢复、系统设置 |

删除属于 ADMIN 权限；恢复上线时间见 Q03。登录方案、初始管理员、各对象和导入等完整操作矩阵见 Q07；不自行扩展角色或省略服务端鉴权。

## 24. 批量导入

CONFIRMED：支持 CSV 和 Excel，初期至少资源导入；示例列 `cluster, hostname, resource_type, role, status, manufacturer, model, cpu_model, cpu_cores, memory_mb, gpu_model, gpu_count`。

Interface、IPAddress、Network 导入为后续扩展。导入必须走与普通 API 相同的 Service Layer 业务校验，禁止跳过服务层直接写数据库。重复、更新、失败回滚粒度和 VM Host 列等见 Q08。

## 25. API

CONFIRMED：REST API，Resource 支持组合过滤，不按每种查询场景另建接口。

PROPOSED 统一前缀 `/api/v1/`，核心路径为 `/api/v1/clusters`、`resources`、`interfaces`、`networks`、`ip-pools`、`ip-addresses`、`services`、`search`、`audit`（均沿用同一前缀）。示例 `GET /api/v1/resources?cluster=N96P&type=BARE_METAL&role=COMPUTE&status=IDLE`。

路径示例不是完整 Contract；Endpoint、用户管理、导入等能力也必须有相应契约。分页、排序、错误、nullable 与权限由已签核 Contract 明确。

## 26. 数据库

CONFIRMED：PostgreSQL、SQLAlchemy 2.x、Alembic；扩展信息用 JSONB，模糊搜索用 pg_trgm。IP / 网段字段优先使用 PostgreSQL INET / CIDR，偏离需有明确设计依据；GIN 索引仍为建议。

这些明确要求不因 §29 的整体技术栈标题带“建议”而降回未选定。数据库仍需正式设计约束、索引和 Migration，不能把需求字段直接当成获批 Schema。

## 27. 数据完整性

CONFIRMED：数据库与业务层共同保证 §7、§9、§10、§14、§21 的唯一性、关系与生命周期规则；关键唯一性由 PostgreSQL 兜底，不只前端检查。必须保障自动 IP 分配不重复、VM Host 类型正确、VM/Host 同集群、IP 属于 CIDR、IP/Network/Interface 同集群及删除后标识可重用。

具体数据库约束方案由设计决定，并在真实 PostgreSQL 上验证。

## 28. 前端

CONFIRMED：运维资源查询与维护控制台，强调快速、清晰、高效查询与低操作成本。主要页面 Dashboard、Search、Clusters / Cluster Detail、Resources / Resource Detail、Networks / IPAM、Services、Audit、System。

列表页至少分页、排序、过滤、模糊搜索；不追求复杂视觉效果。

## 29. 技术栈

PROPOSED：前端 React / TypeScript / Vite；后端 Python / FastAPI / Pydantic；测试 pytest；入口代理 Nginx。

CONFIRMED：数据库相关选型按 §26，Docker Compose 部署按 §30。一期暂不引入 Redis、RabbitMQ、Kafka、ElasticSearch、Kubernetes、Celery。建议项的版本与具体架构应经确认/签核，不能通过模板默认获批。

## 30. 部署

CONFIRMED：第一阶段通过 `docker compose up -d` 启动基础服务。原文给出的 Nginx → Frontend / FastAPI → PostgreSQL 架构为待确认技术选型对应的部署方案；最终方案必须满足 Compose 启动要求。配置、建库 / Migration、初始账号等部署细节由后续设计说明。

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

还须依据已确认规则覆盖同 Resource Interface Name 唯一、删除后 IP / Interface Name 重用、导入与 API 一致校验、权限与审计、查询关系、列表交互和部署。OPEN 行为待裁定后补充，不能将自定预期当成业务验收。

## 32. 上线验收

CONFIRMED：能创建 Cluster、BareMetal、VM 并关联 Host，维护 Interface / Network / Pool / Service，手动和自动分配 IP；按 hostname / IP / Cluster / Service 找到 Resource；详情显示 Cluster / 硬件 / Interface / IP / Network / VM 或 Host / Service。

能阻止重复 hostname / IP、跨 Cluster Host / IP 绑定及非法 CIDR 地址；提供逻辑删除、Audit Log、基础权限和 CSV / Excel 导入。一期范围内的全部必需能力不能因优先级低而从上线验收中删除。§31 与以上验收都需真实证据；上线条件不等于自动发布授权。

## 33. 目标查询场景

CONFIRMED：能够快速可靠地回答：hostname 属于哪个集群；某 IP 是哪台机器；cn001 的管理网和 IB 地址；vm001 的宿主机；pve01 下有哪些 VM；Network 剩余可用 IP；IP 是否被使用；机器运行哪些 Service；谁修改了服务器信息。

## 34. 后续扩展

未来可由 clusterctl 经 Resource API 使用 CSM 数据，再通过 ansible-runner 操作节点；Ansible / Agent 可回传 Resource Facts。CSM 作为 Source of Truth，clusterctl 作为 Automation Engine。本期仅保持合理扩展能力，不实现这些功能，也不预建 Job / Workflow / Facts 子系统。

## 35. 待确认与设计输入

以下问题不阻止本次文档维护；进入受影响 Feature 的设计/实现前必须消解其阻塞项。仅缺失普通技术细节时由专业角色在已批准范围内签核，无需把每个实现细节交用户。

| ID | 状态 / 问题 | 影响与责任 |
| --- | --- | --- |
| Q01 | PROPOSED：hostname 大小写不敏感；空白、字符和归一化细则未定 | Product / 用户确认；影响唯一性与导入 |
| Q02 | PROPOSED：Role、Resource Status、Interface Type 建议集合；Cluster / Network / Service 状态与默认值、扩展维护方式未定 | Product / 用户确认；Architecture 设计存储方式 |
| Q03 | OPEN：恢复是一期还是后续；核心软删对象清单、关联对象删除/解绑策略、重用后的恢复冲突 | Product / 用户裁定；影响删除、权限、审计、数据库 |
| Q04 | OPEN：Network 重叠、Pool 范围/重叠、保留/网关/网络/广播地址、/31 /32、自动分配开关与池模式、耗尽/释放/重用、手动池外分配、未绑定 IP、使用率和可用量口径 | Product / 用户确定行为；Database / Architect 设计并发实现 |
| Q05 | OPEN：Host 必填性、换宿主机/迁移 Cluster、父接口归属/环路、对象删除或转移时的关系维护 | Product / 用户确定行为；不能由 FK 默认动作裁定 |
| Q06 | OPEN：Endpoint IP 是否必须属于 Service 的 Resource、可否空地址、协议/端口与重复规则、Service 名称唯一范围 | Product / 用户；影响关系及搜索 |
| Q07 | OPEN：认证与初始管理员、完整操作权限矩阵、Audit 查看与保留/敏感字段、多人并发编辑冲突策略 | Product / 用户定行为；Architect 设计认证、并发和审计机制 |
| Q08 | OPEN：导入模板必填项/VM Host、重复行与现存记录处理、整批或逐行事务、错误反馈 | Product / 用户；导入不得绕过 API 业务校验 |
| Q09 | PROPOSED：§25 API 前缀、§29 剩余技术栈；版本与具体契约待架构设计 | 用户确认重大选型；Architect 签核普通设计 |
| Q10 | OPEN：Cluster name/code、Network 名称等未给唯一性/修改规则；字段必填/默认/合法范围需按影响分别澄清 | Product 确认业务边界，Architect / Database 定技术细节 |

## 36. 文档建立状态

本次建立需求基线与流程入口。领域文档提供本文件的规则索引；架构 ADR、数据库 Schema、API Contract、部署实现和完整 Feature 计划尚未建立。项目计划为未批准空骨架，不标 READY / DONE，不回查旧版本补齐。
