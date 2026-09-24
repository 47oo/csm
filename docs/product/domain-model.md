# CSM V2 领域模型

> Status: **DRAFT — DECISIONS APPLIED (2026-09-24)**
> Document Type: Domain Model
> Target: CSM V2
> 创建日期：2026-09-24
> 来源：`docs/product/requirements-v2.md`（DRAFT — PENDING USER CONFIRMATION）

本文件是 CSM V2 领域规则的权威来源。状态标记：`CONFIRMED` / `PROPOSED` / `OPEN`，定义见 `docs/product/requirements-v2.md`。

> 本文件整体仍为 DRAFT，用户本轮确认的 BQ-H 规则已应用；尚未裁定的问题不得自行补全，见第 7 节。领域事实以 `requirements-v2.md` 对应章节为准。

---

## 1. 资源概念与分类 `CONFIRMED`

- “资源（Resource）”是统一业务概念，**不是单一实体或单张表**。
- 计算资源（ComputeResource）：共用实体，`resource_type ∈ {bare_metal, virtual_machine}`，具有稳定 `resource_id` 及公共属性（所属集群、名称、资源类型、创建/更新时间、逻辑删除状态）。
- P0 采用独立模型（不并入计算资源公共表）：Cluster、NetworkSegment、IP、NetworkInterface、Service、DeploymentInstance。
- `resource_type` 创建后不可直接修改。
- 计算资源所属集群在 P0 创建后不可通过普通编辑修改；集群 `code` 全局唯一且不可改，名称/用途可修改（BQ-H）。
- 展示口径与存储口径的一致性策略属于架构待决事项，不新增产品约束。

---

## 2. 实体与关键属性

| 实体 | 关键属性 | 状态 |
| --- | --- | --- |
| Cluster | `code`（全局唯一、创建后不变，如 `N96P`）、名称、用途（可修改） | `CONFIRMED`（BQ-H） |
| ComputeResource | `resource_id`、所属集群、`name`、`resource_type`、状态（`IDLE`/`ALLOC`/`DOWN`/`UNKNOWN`，默认 `ALLOC`）、管理 IP（引用已登记网卡 IP，nullable）、逻辑删除 | `CONFIRMED` |
| BareMetalDetail | SN、CPU、内存、GPU、其他硬件信息 | `CONFIRMED` 存在；必填范围 `OPEN` |
| VirtualMachineDetail | 宿主 `resource_id`、vCPU、内存 | `CONFIRMED` 存在；必填范围 `OPEN` |
| NetworkInterface | 所属计算资源、接口名、可选网段（0..1）、IP 集合 | `CONFIRMED`（BQ-H） |
| NetworkSegment | 所属集群、名称、规范化 CIDR、用途、技术类型、VLAN、网关、逻辑删除、自动分配范围、保留地址 | `CONFIRMED` |
| IP | IPv4 值、所属接口/资源；仅以平台记录判定分配可用性 | `CONFIRMED`；单独删除/恢复与历史表达等仍 `OPEN`（§7） |
| Service | 编号（全局唯一）、名称、类型、关联集群；允许暂时零部署 | `CONFIRMED`（BQ-H）；最少关联集群数 `OPEN` |
| DeploymentInstance | 所属服务、目标计算资源、角色、实际监听地址/端口（不强制引用节点 IP） | `CONFIRMED`（BQ-H）；端口校验 `OPEN` |
| 访问入口（AccessEndpoint） | 服务访问入口（VIP / 域名 / 端口），与网卡 IP 分开记录 | `CONFIRMED`；每个服务×集群关联允许 0..N 条（BQ-H） |
| 保留地址（ReservedAddress） | 单个地址或起止范围 | `CONFIRMED` |

---

## 3. 关系与基数 `CONFIRMED`

- Cluster 1 — N ComputeResource。
- Cluster 1 — N NetworkSegment。
- ComputeResource 1 — N NetworkInterface。
- NetworkInterface 0 — N IP。
- NetworkInterface N — 0..1 NetworkSegment（P0 可不选网段；分配 IP 前必选）。
- VirtualMachine N — 1 BareMetal（宿主；须同集群且有效；不得为 VM 或自身）。
- Service N — N Cluster（关联可有 0..N AccessEndpoint；服务至少关联几个集群仍 `OPEN`）。
- Service 1 — 0..N DeploymentInstance。
- DeploymentInstance N — 1 ComputeResource（须有效；其实例所属集群须在服务关联集群内）。
- AccessEndpoint 归属 Service×Cluster 关联（Q4、BQ-H）；VIP 不自动生成 IP 分配记录。

---

## 4. 状态模型

- 计算资源（裸金属与 VM 共用）：`IDLE` / `ALLOC` / `DOWN` / `UNKNOWN`，默认 `ALLOC`；由维护人员更新，展示状态来源及更新时间。`CONFIRMED`（2026-09-24 修订，BQ-A）
- 网段：无“停用”状态（2026-09-24 裁定，BQ-C）；停止使用通过逻辑删除实现。
- 计算资源生命周期：登记 → 维护 → 逻辑删除 / 恢复。`CONFIRMED`
- `OPEN`：“状态来源”的具体语义（操作者还是来源系统）。

---

## 5. 唯一性与完整性 `CONFIRMED`

- 同集群内有效计算资源 `name` 唯一（跨裸金属与 VM 统一），跨集群允许重复。
- 同集群内有效 IPv4 地址全局唯一，跨集群允许重复；VM IP 同规则。
- 同一有效计算资源下接口名唯一。
- 同集群内有效网段名称、规范化 CIDR 分别唯一；跨集群允许相同 CIDR。
- 服务编号、集群 `code` 各自全局唯一；集群 `code` 创建后不可改。
- 同集群重叠网段允许登记但提示风险；同集群各重叠网段的保留地址/网关均阻止该地址被分配，且须位于其所属 CIDR；详见 `requirements-v2.md` §4.6、§5。
- “有效”= 未被逻辑删除（2026-09-24 裁定，BQ-C）。
- `REQUIRED`（依据 `requirements-v2.md` §9.3）：上述唯一性必须由数据库/后端最终保证；具体实现交架构与数据库设计。

---

## 6. 生命周期

- 计算资源登记、维护、逻辑删除、恢复。`CONFIRMED`
- 删除主机时其网卡/IP 不再占用有效唯一性；存在 VM 或服务部署关联时须先处理关联再删除，不级联删除 VM/部署。资源恢复只恢复随本次资源删除的网卡/IP，先单独删除者不恢复；校验名称、IP 分配、网段有效性与归属、管理 IP 引用及关联约束，整体成功或失败。`CONFIRMED`（BQ-H）
- IP 分配 / 释放 / 保留生命周期（含手动、自动、保留、网关、网络/广播地址排除、`/31`、`/32`、耗尽、释放重用）。`CONFIRMED`，详见 `requirements-v2.md` §5。
- 网段被有效网卡引用时禁止直接删除；存在已分配 IP 时禁止修改 CIDR。`CONFIRMED`
- 无“停用”状态；“有效”仅取决于是否逻辑删除（2026-09-24 裁定，BQ-C）。
- 已登记计算资源无论是否已有网卡/IP，均可通过同一表单追加/修改网卡或 IP；原有接口按原记录编辑，新增 IP 必须满足 §5 全部可分配规则。同名新增不自动覆盖，须由用户确认进入既有资源编辑。`CONFIRMED`（BQ-G、BQ-H）
- 编辑仍有效资源时移除管理 IP 或其网卡，须同次显式清空或重选，否则整单拒绝；删除整个资源不要求预先清空。并发编辑冲突须提示、保留输入，不静默覆盖。`CONFIRMED`（BQ-H）
- 集群仍有有效资源/网段/服务关联时不允许删除；服务或服务—集群关联存在对应部署实例时不允许删除或解除，不隐式级联实例。`CONFIRMED`（BQ-H）

---

## 7. 尚未裁定的领域事项

本轮已确认重叠网段仅提示允许（Q5），不再列为待决。下列事项不阻塞本次文档更新，但须在受影响设计/验收前确认；完整清单和时点见 `requirements-v2.md` §11.2。

| 编号 | 开放项 | 影响 |
| --- | --- | --- |
| Q3 | 专有属性必填范围、含义与单位 | 类型详情字段约束 |
| STATUS-SOURCE | 状态来源及状态时间语义 | 状态展示 |
| NAME-COMPARISON | 名称/code 的唯一性比较和规范化口径 | 唯一性约束 |
| IP-LIFECYCLE | 网卡/IP 单独删除恢复与历史表达；展示/存储一致性策略交架构 | 生命周期设计 |
| SEGMENT-RETENTION | 已删除网段保留/网关的作用寿命与重叠网段计数 | 分配/展示 |
| SERVICE-DETAILS / BQ-E | 服务最少关联数、入口删除恢复、端口校验及服务类型/节点角色枚举 | 服务设计 |
| BQ-F | 认证源、备份/审计保留、延迟目标 | 部署 |

---

## 8. 明确暂不建立

- 不建立物理表 / DTO / 具体枚举编码。
- 已裁定的管理 IP、状态、访问入口归属与基数及 BQ-H 规则已按 `requirements-v2.md` 落稿；未裁定项不得代填。