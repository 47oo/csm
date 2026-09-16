# CSM 领域模型

> Status: CONFIRMED
> Document Type: Domain Model
> Baseline: `docs/product/requirements.md`（Primary Requirements Source）
>
> 变更记录：
>
> - **2026-09-15 — 与已确认需求基线同步**
>   - 移除 **DataCenter**（原 §3/§5.1/§6/§7.4/§8/§9）：V1 不建立 DataCenter 层级，Cluster 为基础设施顶层对象。
>   - 移除 **Rack / U 位**：V1 不管理机柜位置（见 `requirements.md` §13）。
>   - 状态模型收敛：**V1 仅 BareMetal 拥有状态**；VirtualMachine / Container / Service / NetworkInterface / IPAddress 在 V1 不设状态（原 §7.2 / §7.3 已删除）。
>   - **Cluster 名称不得包含 `/`** 确认为已确认规则（R-CLUSTER-005）。
>   - **Service 运行载体绑定**（§5.5 / §6）确认为 CONFIRMED；Service 与 Cluster 的关联由载体归属推导（R-SVC-005 / R-SVC-006）。
>   - 「通用 `status` 字段」建模方式（原 §4.2）转由 Architecture / Database 决定，不再是产品规则。
>   - 决策来源：`docs/product/domain-conflict-handoff.md`。

---

## 1. 文档定位

本文档是 CSM 的权威领域模型，完整定义资源分类、资源定义、资源关系、状态模型、唯一性规则和生命周期规则。

CSM 是面向 HPC / AI 运维场景的内部资源管理平台。

涉及资源类型、资源分类、资源关系、状态模型、唯一性规则和生命周期时，必须优先读取本文档。

`.pi/skills/resource-domain/SKILL.md` 仅提供面向 Agent 的精简领域知识和分析规则，不重复维护完整领域模型。

---

## 2. 产品定位

CSM 的主要目标是逐步替代分散维护的 Excel 表格，提高以下工作的效率和可靠性：

* 资源登记；
* 资源查询；
* 资源关联；
* 状态维护；
* 资源可用情况查询。

CSM 第一阶段是资源管理平台。

当前不以建设完整 CMDB 为目标。

---

## 3. Resource Taxonomy

第一版已确认资源可按业务含义分为：

```text
Resource
├── Infrastructure Resource
│   ├── Cluster
│   └── BareMetal
├── Virtual Resource
│   ├── VirtualMachine
│   └── Container
├── Network Resource
│   ├── NetworkInterface
│   └── IPAddress
└── Service Resource
    └── Service
```

该分类用于产品和领域理解，不要求数据库或代码必须采用继承、通用 `resources` 表、EAV 或 JSONB 通用资源模型。

---

## 4. 静态信息和动态信息

CSM 中应明确区分两类信息：静态信息与动态信息。

### 4.1 静态信息（登记信息）

静态信息描述：

> “我们拥有什么资源，以及这些资源是什么。”

例如：

```text
集群
裸金属
虚拟机
容器
服务
GPU 型号
GPU 数量
CPU 型号
CPU 核心数
内存配置
裸金属所属集群
服务所属运行载体
网络接口
IP 地址
```

### 4.2 动态信息

动态信息描述：

> “资源当前处于什么状态。”

**V1 中只有裸金属 BareMetal 拥有状态**（见 §7.1）。

Cluster、VirtualMachine、Container、Service、NetworkInterface、IPAddress 在 V1 **不设状态**。

状态仅用于表达状态，不得将静态信息（登记事实、生命周期信息等）写入状态字段。

> 具体持久化形式（是否采用通用 `status` 字段、各资源如何存储状态）属于**架构与数据库设计问题**，不是产品规则，由 Architecture / Database 决定。
> 约束：`requirements.md` §4 明确不同资源可以拥有独立数据模型与状态，§24 禁止 EAV / 通用 `resources` 表 / STI / JSONB 万能资源模型。

---

## 5. Resource Definitions

### 5.1 集群 Cluster

集群属于第一版资源范围。

**集群不绑定数据中心。** CSM V1 不建立 DataCenter 资源层级，集群直接作为基础设施资源中的顶层管理对象（`requirements.md` §6）。

集群没有状态。

登记字段：

* 集群名称。集群名称全局唯一，是集群的唯一标识。

字符约束：

* 集群名称不得包含 `/`。
* 理由：集群名称用于 URL 路径寻址（如按集群名称定位其下资源的查询路径），包含 `/` 会破坏路径分段，导致该集群无法通过路径寻址。
* 写入校验要求：集群登记的写入路径必须校验本规则，拒绝包含 `/` 的集群名称。当前尚未实现集群登记写入路径，该校验**待后续「集群登记」Feature 落地**。
* 除 `/` 外的其他字符规则（长度、首尾空白、大小写、其他非法字符等）当前仍为**未定义**，不得自行假设。

### 5.2 裸金属 BareMetal

裸金属属于第一版资源范围。

裸金属绑定到集群（必选）。

一台裸金属可以拥有多张网络接口。

登记字段：

* 主机名称。主机名称是裸金属的身份标识，用于在列表中区分具体机器。

同一集群内主机名称唯一。

**可选硬件规格字段（R-BM-007，2026-09-16 用户裁定）**：Vendor（厂商）、Model（型号）、Serial Number（序列号）、CPU、Memory（内存）、GPU、Storage（存储）。均为可选、纯文本、允许为空（`NULL`）；**Serial Number 不参与唯一性**。这些字段不构成登记阻断条件，也不得因此引入自动资产发现或外部平台同步。

### 5.3 虚拟机 VirtualMachine

虚拟机属于第一版资源范围。

虚拟机与物理宿主（裸金属）之间的关系模型应能够表达实际运行位置。

**关系为必选（R-VM-005）**：每个 VirtualMachine 必须属于一个 BareMetal；Cluster 归属由宿主推导。宿主存在活跃 VirtualMachine 时不得删除宿主；VirtualMachine 软删不级联。

登记字段：

* 虚拟机名称（`name`）：身份标识，必填，**全局唯一**、比较区分大小写（R-VM-004）。
* 可选配置字段（R-VM-006）：CPU / Memory / Disk / OS / Hypervisor / Owner，均为可选、纯文本、允许为空（`NULL`）。

VirtualMachine 在 V1 不设状态（Q-002=B）。

### 5.4 容器 Container

容器属于第一版资源范围。

容器的运行载体可以是：

* 虚拟机；
* 裸金属。

**绑定为必选且恰好一个（R-CONTAINER-002）**：每个 Container 必须属于恰好一个运行载体；Cluster 归属由载体推导。

**登记粒度为长期服务型 Container 实例（R-CONTAINER-001）**：不登记短生命周期 / 临时容器，不引入 Kubernetes workload 等更高层对象。

登记字段：

* 容器名称（`name`）：身份标识，必填，**同一运行载体内唯一**、比较区分大小写（R-CONTAINER-003）。
* 可选字段（R-CONTAINER-004）：Image / CPU / Memory / Owner，均为可选、纯文本、允许为空（`NULL`）。

生命周期（R-CONTAINER-005）：载体存在活跃 Container 时不得删除载体；Container 软删不级联。

Container 在 V1 不设状态（Q-002=B）。

### 5.5 服务 Service

服务属于第一版资源范围。

服务绑定到：

* 虚拟机；
* 容器；
* 裸金属。

服务可以绑定多个运行载体，绑定为必选（R-SVC-005）。

服务与集群的关联不是直接绑定，而是通过其运行载体的集群归属推导（R-SVC-006）。

登记字段（R-SVC-007）：`name` 必填；`service_type` / `url` / `port` / `protocol` / `owner` / `description` 均可选、纯文本、允许为空（`NULL`）。**不属 V1**：Credential reference 与 Health information。

标识与唯一性（R-SVC-008）：`name` 在所有活跃 Service 范围内**全局唯一**、比较区分大小写；已软删释放唯一性。

生命周期（R-SVC-009）：绑定了活跃 Service 的运行载体在绑定期间不得删除；Service 软删不级联。

服务在 V1 不设状态（Q-002=B）。

### 5.6 网络接口 NetworkInterface

网络接口属于第一版资源范围。

网络接口属于非节点资源。

网络接口绑定到裸金属（必选）。

一个裸金属可以拥有多张网络接口。

登记字段：

* 网络接口名称（例如 `eth0`、`ib0` 等）。

### 5.7 IP 地址 IPAddress

IP 地址属于第一版资源范围。

IP 地址属于非节点资源。

IP 地址绑定到网络接口（必选）。

一个网络接口可以挂多个 IP 地址。

同一集群内 IP 地址唯一。

登记字段：

* IP 地址（例如 `10.0.1.1/16` 等）。

---

## 6. Resource Relationships

资源之间的绑定关系如下：

```text
服务 → 虚拟机 / 容器 / 裸金属（可绑定多个，必选）
容器 → 虚拟机 / 裸金属
虚拟机 → 裸金属
裸金属 → 集群
IP 地址 → 网络接口
网络接口 → 裸金属
```

服务与集群的关联不是直接绑定，而是通过其运行载体的集群归属推导（R-SVC-006）。

以下绑定已确认：

* 裸金属 → 集群：必选（R-BM-001）；
* 网络接口 → 裸金属：必选（R-NIC-003）；
* IP 地址 → 网络接口：必选（`requirements.md` §15）；
* 服务 → 虚拟机 / 容器 / 裸金属：必选，可绑定多个（R-SVC-005）。

以下**尚未确认**，必须由对应 Feature 的 Product 阶段确定，**不得自行推导**：

* 容器 → 虚拟机 / 裸金属 的绑定强制性、登记粒度与生命周期（`requirements.md` §10）。

（虚拟机 → 裸金属的绑定强制性与生命周期已于 2026-09-16 由 R-VM-005 确认为必选，见上「关系规则」。）

不得仅根据资源分类自动产生关系。

---

## 7. Status Models

CSM 中统一使用“状态”一词，不再使用“资源状态”“当前状态”等其他说法。

“状态”特指资源当前所处状态的值，不包括资源容量、使用率、实时监控指标等。

状态不得为空。历史数据中状态为空的资源，统一以 `UNKNOWN`（未知）表示；`UNKNOWN` 是状态化资源的合法状态取值之一。

### 7.1 有状态资源：仅裸金属 BareMetal

**V1 中只有裸金属拥有状态。**

裸金属状态：

```text
IDLE
ALLOC
DOWN
UNKNOWN   未知（历史空状态）
```

裸金属登记完成后默认为 `IDLE`。

### 7.2 无状态资源

V1 中**不设状态**的资源：

* 集群 Cluster；
* 虚拟机 VirtualMachine；
* 容器 Container；
* 服务 Service；
* 网络接口 NetworkInterface；
* IP 地址 IPAddress。

不得为上述资源自动增加状态字段或推导状态模型。

> 原文档曾为虚拟机 / 容器 / 服务定义 `IDLE/RUNNING/DOWN/UNKNOWN`，为网络接口 / IP 地址定义 `IDLE/ALLOC/SAVE/UNKNOWN`。
> 该内容已于 2026-09-15 依据 `requirements.md` 确认结果删除，**不属于 V1 规则**。

### 7.3 状态维护规则

状态流转由人工维护。

不得自行新增、合并或重命名状态取值。若确需调整状态集合，必须经过需求确认。

---

## 8. Uniqueness Rules

* 集群名称全局唯一（大小写敏感），集群以集群名称唯一识别（R-CLUSTER-002）；
* 同一集群内主机名称唯一（R-BM-002）；
* 同一集群内 IP 地址唯一（R-IP-001）；
* 虚拟机名称在所有活跃 VirtualMachine 范围内**全局唯一**（跨宿主、跨集群），大小写敏感（R-VM-004）；
* 集群名称不得包含 `/`（R-CLUSTER-005，用于 URL 路径寻址）。

---

## 9. Lifecycle Rules

资源采用逻辑删除，不做物理删除。

被逻辑删除的记录不参与常规查询结果，但其历史信息保留。

不支持对已逻辑删除记录进行恢复（undelete）；资源记录仅支持更新。

父对象（如集群）在其仍存在活跃子对象时，不允许逻辑删除。

具体持久化方式（如删除标记字段）由数据库设计决定。

---

## 10. 当前待确认事项

以下问题当前不得自行假设答案：

* 所有裸金属都具有 GPU；
* 所有裸金属都具有相同配置；
* 一个裸金属只能属于一种业务用途；
* 一个 IP 地址在任何场景下都全局唯一；
* 一个服务只能属于一个集群；
* 所有实时状态都需要永久保存；
* 虚拟化平台必须在第一版接入；
* CSM 必须具备传统 CMDB 的全部能力。

以下项目在 `requirements.md` §29 中已明确为待确认，其确认属于对应 Feature 的 Product 阶段：

* OPEN-005：Excel 部分成功导入策略。

OPEN-004（裸金属硬件字段）已于 2026-09-16 由用户裁定，固化为 R-BM-007；OPEN-001（虚拟机字段与绑定）已于 2026-09-16 由用户裁定，固化为 R-VM-004 / R-VM-005 / R-VM-006；OPEN-002（容器粒度与绑定）已于 2026-09-16 由用户裁定，固化为 R-CONTAINER-001 ~ R-CONTAINER-005；OPEN-003（服务字段）已于 2026-09-16 由用户裁定，固化为 R-SVC-007 / R-SVC-008 / R-SVC-009；均不再是待确认项。

OPEN-006（虚拟资源运行时集成）已由已确认规则排除，不再是待确认项。

如果这些内容会影响设计，应进入需求确认流程。
