# CSM V2 领域模型

> Status: **DRAFT — DECISIONS APPLIED (2026-09-24)**
> Document Type: Domain Model
> Target: CSM V2
> 创建日期：2026-09-24
> 来源：`docs/product/requirements-v2.md`（DRAFT — PENDING USER CONFIRMATION）

本文件是 CSM V2 领域规则的权威来源。状态标记：`CONFIRMED` / `PROPOSED` / `OPEN`，定义见 `docs/product/requirements-v2.md`。

> ⚠ 本文件为部分确认稿：结构骨架已由需求正文明确，但若干关键规则仍为 `OPEN`，不得当作既定事实，也不得在实现中自行补全。开放项见第 7 节。

---

## 1. 资源概念与分类 `CONFIRMED`

- “资源（Resource）”是统一业务概念，**不是单一实体或单张表**。
- 计算资源（ComputeResource）：共用实体，`resource_type ∈ {bare_metal, virtual_machine}`，具有稳定 `resource_id` 及公共属性（所属集群、名称、资源类型、创建/更新时间、逻辑删除状态）。
- P0 采用独立模型（不并入计算资源公共表）：Cluster、NetworkSegment、IP、NetworkInterface、Service、DeploymentInstance。
- `resource_type` 创建后不可直接修改。
- `OPEN`：展示口径与存储口径的一致性策略。

---

## 2. 实体与关键属性

| 实体 | 关键属性 | 状态 |
| --- | --- | --- |
| Cluster | `code`（稳定编号，如 `N96P`）、名称、用途 | `CONFIRMED`（属性集） |
| ComputeResource | `resource_id`、所属集群、`name`、`resource_type`、状态（`IDLE`/`ALLOC`/`DOWN`/`UNKNOWN`，默认 `ALLOC`）、管理 IP（引用已登记网卡 IP，nullable）、逻辑删除 | `CONFIRMED` |
| BareMetalDetail | SN、CPU、内存、GPU、其他硬件信息 | `CONFIRMED` 存在；必填范围 `OPEN` |
| VirtualMachineDetail | 宿主 `resource_id`、vCPU、内存 | `CONFIRMED` 存在；必填范围 `OPEN` |
| NetworkInterface | 所属计算资源、接口名、网段、IP 集合 | `CONFIRMED` |
| NetworkSegment | 所属集群、名称、规范化 CIDR、用途、技术类型、VLAN、网关、状态、自动分配范围、保留地址 | `CONFIRMED` |
| IP | IPv4 值、所属接口/资源 | `CONFIRMED`；语义细节 `OPEN` |
| Service | 编号（全局唯一）、名称、类型、关联集群 | `CONFIRMED` |
| DeploymentInstance | 所属服务、目标计算资源、角色、监听地址/端口 | `CONFIRMED` |
| 访问入口（AccessEndpoint） | 服务访问入口（VIP / 域名 / 端口） | `CONFIRMED`；按“服务 × 关联集群”各自配置 |
| 保留地址（ReservedAddress） | 单个地址或起止范围 | `CONFIRMED` |

---

## 3. 关系与基数 `CONFIRMED`（访问入口归属 `OPEN`）

- Cluster 1 — N ComputeResource。
- Cluster 1 — N NetworkSegment。
- ComputeResource 1 — N NetworkInterface。
- NetworkInterface 0 — N IP。
- NetworkInterface N — 1 NetworkSegment（P0 单网段）。
- VirtualMachine N — 1 BareMetal（宿主；须同集群且有效；不得为 VM 或自身）。
- Service N — N Cluster（每条关联各带一个访问入口 AccessEndpoint）。
- Service 1 — N DeploymentInstance。
- DeploymentInstance N — 1 ComputeResource（须有效；其实例所属集群须在服务关联集群内）。
- AccessEndpoint 归属 Service×Cluster 关联（2026-09-24 裁定，Q4）。

---

## 4. 状态模型

- 计算资源（裸金属与 VM 共用）：`IDLE` / `ALLOC` / `DOWN` / `UNKNOWN`，默认 `ALLOC`；由维护人员更新，展示状态来源及更新时间。`CONFIRMED`（2026-09-24 修订，BQ-A）
- 网段：无“停用”状态（2026-09-24 裁定，BQ-C）；停止使用通过逻辑删除实现。
- 计算资源生命周期：登记 → 维护 → 逻辑删除 / 恢复。`CONFIRMED`
- `OPEN`：“状态来源”的具体语义（操作者还是来源系统）。

---

## 5. 唯一性与完整性 `CONFIRMED`（“有效”口径 `OPEN`）

- 同集群内有效计算资源 `name` 唯一（跨裸金属与 VM 统一），跨集群允许重复。
- 同集群内有效 IPv4 地址全局唯一，跨集群允许重复；VM IP 同规则。
- 同一有效计算资源下接口名唯一。
- 同集群内有效网段名称、规范化 CIDR 分别唯一；跨集群允许相同 CIDR。
- 服务编号全局唯一。
- “有效”= 未被逻辑删除（2026-09-24 裁定，BQ-C）。
- `REQUIRED`（依据 `requirements-v2.md` §9.3）：上述唯一性必须由数据库/后端最终保证；具体实现交架构与数据库设计。

---

## 6. 生命周期

- 计算资源登记、维护、逻辑删除、恢复。`CONFIRMED`
- 删除主机时其网卡/IP 不再占用有效唯一性；存在 VM 或服务部署关联时须先处理关联再删除；恢复时重新检查名称、IP 与关联约束。`CONFIRMED`
- IP 分配 / 释放 / 保留生命周期（含手动、自动、保留、网关、网络/广播地址排除、`/31`、`/32`、耗尽、释放重用）。`CONFIRMED`，详见 `requirements-v2.md` §5。
- 网段被有效网卡引用时禁止直接删除；存在已分配 IP 时禁止修改 CIDR。`CONFIRMED`
- 无“停用”状态；“有效”仅取决于是否逻辑删除（2026-09-24 裁定，BQ-C）。

---

## 7. 开放项汇总（阻塞领域稳定性）

| 编号 | 开放项 | 影响 |
| --- | --- | --- |
| Q3 | 专有属性（CPU/内存/GPU/SN/vCPU）必填范围 | 类型详情字段约束 |
| Q5 | 网段重叠仅提示还是禁止写入 | 写校验 |
| — | “状态来源”语义 | 状态展示 |
| BQ-E | 服务类型 / 节点角色枚举 | 枚举 |
| BQ-F | 认证源、备份/审计保留、延迟目标 | 部署 |

---

## 8. 明确暂不建立

- 不建立物理表 / DTO / 具体枚举编码。
- 已裁定项（管理 IP、计算资源状态、访问入口归属）已按 2026-09-24 裁定写入模型；未裁定项不得写入。