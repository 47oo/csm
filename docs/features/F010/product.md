# F010 IP 地址分配与容量 — PRODUCT 阶段报告

- **Feature**：F010 IP 地址分配与容量（FEATURE，P0，M4 网络与 IPAM，deps [F007, F008, F009]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`
- **依据**：requirements-v3.md revision 3（§4、§4.1、§10、§11、§11.1、§12、§12.1、§13、§13.1、§13.2、§13.3、§14、§16、§18、§20、§21、§22、§23、§25、§27、§28、§31 T04–T07/T10/T16/T17/T18/T22/T23/T24/T25/T26/T30/T31/T32/T34/T35/T37/T38/T40/T41、§35.2 Q04-A/Q04-B/Q07-A/Q10-A/Q10-B、§35.3 D01/D02）；plan_revision 4 F010；`docs/architecture/d01-conventions.md` v8；F007（Interface 实体、`resource` 归属、`interface←IPAddress` 引用预留点）；F008（Network 实体、CIDR/网关/禁用边界、`_lock_network` 与 Network 引用检查点，DB-D90/D93）；F009（IPPool 范围与 allocation_mode、`address_in_use` reason、`IpOccupancyProvider` 注册表、`_lock_network` 锁域，DB-D95–D110/DR-109/110）

## 1. 目标与范围

### 1.1 目标
在 F007 Interface、F008 Network、F009 IPPool 基础上，提供 IPAddress 独立对象的登记与维护，实现 IPv4 地址的自动分配、手动分配、解绑、转移与释放，并给出 §20 Network 与 AUTO 池容量口径的计算输入，作为 Network→IPAddress→Interface 关系与集群级 IP 事实数据的权威来源。

### 1.2 本次范围（CONFIRMED，除标注 PROPOSED 外）
- 实体（§13/§4）：IPAddress 独立对象，经 Network→IPAddress→Interface 关联；Interface 可空（未绑定仍占用）；一个 Interface 可多 IP，一个 Resource 可多 Interface。
- 字段契约（§13/§14/§4.1 + D01 补齐）：network、address、interface、分配来源（ip_pool）、description；标准 id/version/created_at/updated_at/deleted_at（字段状态见 §2）。
- 自动分配（§13.1）：条件 = Network ACTIVE + auto_allocate 开启 + 指定池 allocation_mode=AUTO；在指定池内按地址升序选择符合全部约束的可用地址；并发不重复；指定池耗尽返回“无可用地址”，不切换其它池。
- 手动分配（§13.2）：用户输入 IPv4；须属 ACTIVE Network CIDR；允许 AUTO/MANUAL 池内或池外；禁 gateway、RESERVED 池范围及 §11.1 禁用地址；auto_allocate 不代替手动校验。
- 解绑/转移/释放（§13.3）：解绑只移除 Interface 关系、IP 继续占用；转移为改绑（同 Cluster）；释放为软删 IP 记录、按 ADMIN 权限；解绑/转移/释放前须先处理引用它的 Endpoint；删除后地址可重用；恢复重检冲突、不覆盖新占用。
- IP 完整性（§14）：IP 必须属关联 Network CIDR；同 Cluster 全局唯一（未删除）即使经不同 Network/Pool；不同 Cluster 可重复；绑定 Interface 时 Resource 与 Network 必须同 Cluster；未绑定不豁免一致性/唯一性/合法性；自动、手动、恢复共用同一规则。
- IPv4 地址边界与禁用网段（§11.1）：/0–/30 排网络/广播、/31 两址可用、/32 唯一地址可用且 gateway 必空；禁用 5 段（0.0.0.0/8、127.0.0.0/8、169.254.0.0/16、224.0.0.0/4、240.0.0.0/4）不得分配或作 gateway。
- 容量（§20）：Network 可分配总量/已占用/剩余、AUTO 池可分配总量/剩余按集合公式计算，作为 F013 Dashboard 的输入（显示归 F013）。
- 生命周期与引用（§21）：软删；默认查询隐藏；ADMIN 恢复/查看已删；有未删除 Endpoint 引用时禁解绑/转移/释放；有未删除 IP 引用时阻止 Network/Interface 删除并返回引用列表；IPPool 分配来源关系为例外（删除/缩小池不回收、不阻止）。
- 并发与完整性（§12.1/§27）：保留范围/网关变更与并发 IP 分配不能同时成功形成冲突；同 Cluster IP 唯一与自动分配不重复由 PostgreSQL 兜底；复用 `_lock_network` 锁域；D02 约束/索引/锁/IPAM 并发部分在本 Feature CONTRACT 后关闭（PROPOSED，待 Architect/Database）。
- 权限/审计（§22/§23）：EDITOR 分配/解绑/转移；ADMIN 释放/查看已删/恢复；VIEWER 只读；CREATE/UPDATE（含绑定/解绑/转移）/DELETE（释放）/RESTORE 写 Audit 且同事务。
- 跨 Feature 协议：注册真实 `IpAddressOccupancyProvider`（F009 在 F009 注册空集的真实实现）；注册 Network/Interface 引用检查器；预留 `Endpoint←IPAddress` 引用检查挂钩（由 F012 注册）。

### 1.3 使用者
EDITOR 执行分配、解绑、转移与绑定；ADMIN 执行释放、查看已删与恢复；VIEWER 查询 IP 与占用；运维人员据 IP 归属回答“某 IP 是哪台机器”“Network 剩余可用 IP”“IP 是否被使用”等 §33 场景。

## 2. 字段契约（IPAddress，补齐 D01）

| 字段 | 类型 | 可空 | 创建必填 | 状态 | 合法值/语义 |
| --- | --- | --- | --- | --- | --- |
| network | UUID | 否 | 是 | CONFIRMED | 引用存在、未软删 Network（§13/§4）；IP 必须属其 CIDR（§14）；新增分配要求 ACTIVE（§11/§13.1/§13.2）；创建后可否修改见 I-4（PROPOSED 不可改） |
| address | IPv4 | 否 | 是 | CONFIRMED | 单个 IPv4 主机地址（非 CIDR/掩码）；属该 Network CIDR（越界→拒绝）；非 gateway；不在 RESERVED 池范围与禁用范围（手动校验；自动在可分配集合内选择）；同 Cluster 未删除全局唯一；创建后可否修改见 I-4（PROPOSED 不可改） |
| interface | UUID | 是 | 否 | CONFIRMED | 可空=已占用未绑定；非空须引用存在、未软删 Interface，且 Interface.Resource.cluster == Network.cluster（跨 Cluster→拒绝）；可解绑/转移（绑定关系可变） |
| ip_pool（分配来源） | UUID | 是 | 否 | CONFIRMED（来源保留）/PROPOSED（字段与设置口径） | 记录分配来源 IPPool；自动分配=指定 AUTO 池；手动分配=地址所属池或 null（池外）；仅历史保留，Pool 删除/缩小不回收、不删除；设置与可变性见 I-6 |
| description | string | 是 | 否 | PROPOSED | 描述性自由文本；长度交 D01 §5.9（PROPOSED 沿用 text 无上限，同 F003/F004/F007/F008/F009） |
| metadata | object (JSONB) | — | — | PROPOSED（倾向不落） | §13 未列举；PROPOSED 不落 metadata（同 F009 Pool）；请求含 metadata→422、响应不含；是否新增见 I-3 |
| id / version / created_at / updated_at / deleted_at | 标准 | — | — | CONFIRMED | 稳定 UUID；version 乐观锁（§23）；timestamptz UTC（D01 §2）；deleted_at 软删（§21） |

补充：
- 省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；更新（PATCH）省略=保持（exclude_unset）；显式 null 仅清空 nullable（interface/description）；必填/非 nullable（network/address）显式 null→422；不可变/只读字段→422；未知字段→422。
- IPAddress 无“名称”字段，§4.1 名称归一化表不适用；不因名推断地址分类。
- address 与 network 的关系：本 Feature 不新增网络地址/广播地址之外的范围限制；§11.1/§20 已将网络/广播/gateway/RESERVED/禁用排除于可分配集合。
- 分配来源（ip_pool）作为历史保留，属 §21 引用检查例外（§12/§21）。

**建议 D01 新增 §5.9 IPAddress 字段口径**（PROPOSED）：address=单个 IPv4 主机地址（PG inet，family=4、masklen=32），属 Network CIDR；interface 可空、同 Cluster；ip_pool 可空来源、历史保留；description 可空无上限；不落 metadata（I-3）。交 CONTRACT/D01 签核。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 未决 |
| --- | --- | --- | --- | --- | --- |
| IPAddress | 多对一 Network；多对一（可空）Interface；可空来源 IPPool；被 Endpoint 引用（F012） | 地址唯一=同 Cluster；来源=同 Network | 创建（自动/手动）/绑定/解绑/转移/软删（释放）/恢复 | §13、§14、§21 | network/address 可变性（I-4） |
| 同 Cluster IP 唯一 | 未删除 IP 在整个 Cluster 内唯一（含未绑定、跨 Network/Pool） | Cluster | 创建/恢复重检 | §13.3、§14、§27 | 表示法与并发兜底（I-1） |
| 绑定一致性 | IP→Interface 时 Resource.cluster == Network.cluster | Cluster | 绑定/转移重检 | §14、§10 | 无 |
| 自动分配 | ACTIVE Network + auto_allocate + AUTO 池；升序；耗尽不切换 | Network/Pool | 请求期 | §13.1、§11 | 并发选地址实现（I-2） |
| 手动分配 | 池内/池外；禁 gateway/RESERVED/禁用 | Network | 请求期 | §13.2、§11.1 | INACTIVE 下绑定/解绑是否受限（I-5） |
| 解绑/转移/释放 | 解绑不释放；释放=软删（ADMIN）；Endpoint 引用先处理 | IPAddress | 关系变更/软删 | §13.3、§16、§23 | Endpoint 挂钩跨 Feature（I-7） |
| IPPool↔IPAddress | IP 记录保留来源 Pool；池软删/缩小不回收 | 同 Network | — | §12/§21 | 来源字段设置口径（I-6） |
| 引用检查 | Network/Interface←未删 IP 阻止删除；IPPool 为例外 | Cluster/Network | 删除/改 CIDR/改 cluster 前 | §21、§11 | F009-CON-01 订正（I-10） |
| 容量 | §20 Network 与 AUTO 池口径 | 随 Network/Pool | 查询期 | §20 | 数据接口归 F013（I-7） |

数据完整性对应表（引用 `.pi/skills/data-integrity/SKILL.md`，精简；Database/Backend/Tester 补保证与证据）：

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §14/§27 同 Cluster 未删 IP 唯一 | 分配/恢复 | 部分唯一（cluster 或 network→cluster 口径，I-1） | 409 conflict | 索引仲裁；软删释放；恢复重检 | V-DB-TBD（F010） |
| §13.1/§27 自动分配不重复、升序 | 自动分配 | 唯一兜底 + 行锁 | `_lock_network`+升序选择 | T07 双会话 | V-DB-TBD/F010 |
| §11.1/§14 IP 属 CIDR、非 gateway/RESERVED/禁用 | 手动/自动 | 跨表（Network/Pool）应用主校验（DB backstop 待 Database 裁定） | 422/409 | — | V-DB-TBD |
| §14 绑定 Cluster 一致 | 绑定/转移 | 应用主校验（跨 Resource/Network） | 422 | — | V-DB-TBD |
| §13.3/§16 Endpoint 引用 | 解绑/转移/释放 | — | 引用检查器 → 409 reference_exists | F012 注册挂钩 | F010 桩 + F012 端到端 |
| §12.1/§11.1 保留范围/网关 vs 并发分配 | 池/gateway 变更 + 分配 | — | 共享 `_lock_network` + `IpAddressOccupancyProvider` | T35 双会话 | F010 端到端 |
| §21/§27 软删/恢复 | 释放/恢复 | deleted_at + 唯一 | 恢复重检 CIDR/唯一/Cluster/引用 | 不级联 | V-DB-TBD |
| §23 乐观锁 | PATCH/释放/恢复 | version + 条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-TBD |

## 4. 必须遵守的已确认约束
- §13：IPAddress 独立于 Interface；Network→IPAddress→Interface；Interface 可空且未绑定仍占用；一个 Interface 可多 IP。
- §13.1：仅 Network ACTIVE + auto_allocate 开启 + 指定 Pool AUTO 可自动分配；按地址升序选择符合全部约束的可用地址；并发不重复；指定池耗尽返回“无可用地址”且不切换其它池。
- §13.2：手动分配须属 ACTIVE Network；池内或池外合法；禁 gateway、RESERVED 池范围、禁用地址；auto_allocate 不代替手动校验。
- §13.3：解绑只移除 Interface 关系、IP 继续占用；释放=软删、按 ADMIN 删除权限；解绑/转移/释放前先处理 Endpoint；删除后 IP 可重用；恢复重检冲突、不覆盖新占用记录。
- §14：IP 属 Network CIDR；同 Cluster 全局唯一（未删除）；不同 Cluster 可重复；绑定需 IPAddress.cluster==Interface.Resource.cluster；未绑定不豁免一致性/唯一性/合法性；自动、手动、恢复共用。
- §11：Network INACTIVE 禁止新增 IP 分配（释放仍按权限与引用检查）；有未删除 Pool/IP 时禁改 CIDR/Cluster。
- §11.1/§20：基础可用地址与禁用范围；可分配集合=基础可用−gateway−RESERVED−禁用；自动/手动/恢复/容量共用；/31、/32 语义；禁用 5 段。
- §12/§12.1：删除/缩小 Pool 不回收、不释放已分配 IP、来源历史保留；保留范围/网关变更与并发分配互斥，拒绝返回冲突数量与可查询明细（含未绑定）。
- §16/§21：有 Endpoint 引用时禁解绑/转移/释放；有未删除依赖时禁删并返回引用列表、不隐式级联；恢复只恢复自身、重检唯一性/所属对象有效性/关系约束，失败不覆盖。
- §20：容量公式（可分配集合、已占用量含未绑定、AUTO 池交集口径、排除去重、按当前范围不按来源、停用不清零）。
- §22：CREATE/UPDATE（绑定/解绑/转移）/DELETE（释放）/RESTORE 写 Audit；Activity 全角色；不记敏感内容。
- §23：EDITOR 分配/解绑/转移；VIEWER 只读；释放/查看已删/恢复 ADMIN；乐观锁版本冲突。
- §27：同 Cluster IP 唯一与自动分配不重复由 PostgreSQL 兜底并在真实 PG 验证；引用检查 DB+业务共同保证。
- §4/D01：内部关联用稳定 UUID；D01 §4 省略语义与 422 口径；D01 §2 时间；F008 约定 F010 创建子对象须取同 Network 行锁（F008 DB-D90/DB-D93）。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | 手动分配合法 IPv4 且属 ACTIVE Network CIDR 的可分配地址（AUTO/MANUAL 池内或池外）成功；创建未删除 IP 记录并占用 | §13.2/T06/T17/T30 |
| A2 | 手动分配地址不属 Network CIDR 或地址非法/非 IPv4 → 拒绝（422） | §13.2/§14/T06 |
| A3 | 手动分配 gateway、RESERVED 池范围或 §11.1 禁用地址 → 拒绝，不创建 | §11.1/§13.2/T17/T31 |
| A4 | auto_allocate 关闭或地址属 MANUAL 池时手动分配仍允许；AUTO 池亦允许手动 | §13.2/T17 |
| A5 | 自动分配仅在 Network ACTIVE 且 auto_allocate=true 且指定池 allocation_mode=AUTO 时成功；其余条件返回明确拒绝，不降级为手动 | §13.1/T16 |
| A6 | 自动分配在指定池内按地址升序选第一个符合全部约束的可用地址（属 CIDR、非 gateway、非 RESERVED、非禁用、未占用、同 Cluster 唯一） | §13.1/T17 |
| A7 | 指定 AUTO 池无可用地址 → 返回“无可用地址”，不改用其它池或其它 Network | §13.1/T16 |
| A8 | 并发自动分配不产生重复 IP，最终持久化状态无重复占用 | §13.1/§27/T07 |
| A9 | interface 为空（未绑定）的 IP 仍占用，不作为可用地址再次分配 | §13/§20/T18 |
| A10 | 解绑只移除 Interface 关系，IP 记录继续占用、不释放 | §13.3/T18/T22 |
| A11 | 转移=改绑到另一 Interface（同 Cluster）允许；改绑到不属 Network Cluster 的 Interface 被拒 | §13.3/§14/T10 |
| A12 | 释放=软删 IP 记录，仅 ADMIN；EDITOR 解绑不能隐式释放 | §13.3/§23/T22/T25 |
| A13 | 释放后同一地址可在同 Cluster 重新分配；恢复旧 IP 重检冲突，不覆盖新占用记录 | §13.3/§21 |
| A14 | 同 Cluster 重复 IP（含经不同 Network/Pool、未绑定）失败；不同 Cluster 同 IP 允许 | §14/T04/T05 |
| A15 | 绑定 Interface 时 Resource 与 Network 不同 Cluster 被拒；未绑定 IP 仍校验 CIDR/唯一/Cluster 一致性 | §14/T10 |
| A16 | /0–/30 排网络/广播；/31 两址可用；/32 唯一地址可用且 gateway 必空；自动、手动、恢复共用同一边界 | §11.1/T30 |
| A17 | 禁用 5 段边界地址禁止分配及作 gateway；普通合法私网/公网允许；LOOPBACK 接口可登记但 127.x.x.x 不入 IP 台账 | §11.1/T31 |
| A18 | IP 被未删除 Endpoint 引用时解绑/转移/释放被拒并返回引用列表，无隐式级联（F010 交付检查契约与 `Endpoint←IPAddress` 挂钩；端到端随 F012） | §16/§21/T22 |
| A19 | 有未删除 IP 引用时 Network/Interface 删除被拒并返回引用列表；IPPool 分配来源为例外，删除/缩小池不阻止、不回收 | §21/§12/T23 |
| A20 | IP 记录保留分配来源 Pool；删除/缩小池不删除/不释放已分配 IP，来源历史保留 | §12/§21/T34 |
| A21 | 保留范围/网关变更与并发 IP 分配不能同时成功形成冲突；事务失败不留部分变更或错误容量 | §12.1/§11.1/T35 |
| A22 | ADMIN 恢复已删 IP；恢复只恢复自身、不自动恢复 Interface/Endpoint 关系；重检属 CIDR、同 Cluster 唯一、Cluster 一致性、引用有效性；失败不覆盖新对象 | §21/T24 |
| A23 | Network 可分配总量/已占用/剩余与 AUTO 池可分配总量/剩余按 §20 集合公式；gateway 与 RESERVED 重叠不重复扣减；未绑定计占用、池外手动 IP 计 Network 占用；池内占用按当前地址范围不按来源；停用不清零 | §20/T32 |
| A24 | 权限：VIEWER 只读；EDITOR 分配/解绑/转移；释放/查看已删/恢复 ADMIN；分配/解绑/转移/释放/恢复写 Audit 且同事务，Activity 全角色可见 | §22/§23/T25 |
| A25 | 创建缺失 network/address → 422；省略非必填→默认/null；PATCH 省略=保持；不可变/只读/未知字段→422 | §4.1/D01/T37/T38 |
| A26 | 同 Cluster 未删 IP 唯一由 PostgreSQL 兜底、真实 PG 验证；过期版本编辑 409 无静默覆盖 | §27/§23/T04/T26 |

说明：A18 的 Endpoint 引用数据来源于 F012；F010 交付引用检查契约与预留挂钩，含 Endpoint 的端到端验证在 F010/F012 集成（T22/T23）完成，见 §7 I-7。T40/T41（名称规则/复用）针对 Network/Pool/Service/Interface 名称；IPAddress 无名称字段，地址复用由 A13、Cluster code 除外项由各自 Feature 承载，本 Feature 不重复。

## 6. 明确排除项
- 不做 Endpoint/Service 实体与其校验（F011/F012）；F010 仅预留 `Endpoint←IPAddress` 引用检查挂钩，不实现 Endpoint 监听唯一性、协议/端口校验。
- 不做 IPPool 范围/模式/重叠与保留范围-网关占用冲突本体（F009）；F010 只注册真实占用提供者并消费其冲突契约。
- 不做 Network CIDR/网关/状态/auto_allocate 本体与 CIDR 重叠（F008）；不做 Interface 本体与父接口规则（F007）。
- 不做 Dashboard 展示与全局搜索（F013）；F010 提供 §20 容量数据口径，不建 Dashboard 页面。
- 不做 CSV/Excel 导入（F014）；完整 Audit 查询页（F015）；一期集成验收（F016）。
- 不做 IPv6、DHCP、路由、防火墙、VLAN 划分、网段自动发现、实时可达性/流量监控。
- 不由地址推断 Resource/Service/角色/网络分类；不自动创建 Endpoint 或 Service；不进行 DNS 登记。
- 不落 metadata（PROPOSED，I-3）；不落实时探测状态字段；IPAddress 无 name/status 字段。

## 7. 依赖与未决问题
依赖（CONFIRMED）：F007（Interface 实体、Resource 归属、`interface←IPAddress` 引用检查预留点，DONE）；F008（Network 实体、CIDR/网关/禁用边界、`_lock_network` 与 Network 引用检查点，DONE）；F009（IPPool 范围与 allocation_mode、`address_in_use` reason、`IpOccupancyProvider` 注册表、`_lock_network` 锁域，DONE）；F001（PostgreSQL 基线、btree_gist、真实 PG 测试基线）；D01 共享约定（v8+）。下游 F012（Endpoint）依赖本 Feature 的 IPAddress 与引用挂钩；F013 依赖本 Feature 的容量数据；F015 依赖本 Feature 的删除/恢复规则。

BLOCKING：无。

CONFIRMED：§13 全部；§13.1/§13.2/§13.3；§14；§11.1；§20 容量公式；§12.1 并发保护要求；§21 软删/恢复/引用检查及 Pool 例外；§22；§23；§27；Q04-A/Q04-B/Q07-A/Q10-A/Q10-B。

PROPOSED/OPEN（非阻塞，待 Architect/Database/Product 确认或签核）：
- **I-1（OPEN，Database/D02）**：同 Cluster 未删 IP 全局唯一的表示与并发兜底（是否在 `ip_addresses` 冗余 `cluster_id` 支撑部分唯一索引，或经 Network 关联的部分唯一/触发兜底）、软删参与范围、恢复重检落点。Owner：Architect/Database → DATABASE Gate。
- **I-2（OPEN，Architect/Database/D02）**：自动分配的地址选择在并发下的实现（共享 `_lock_network` + 唯一约束 + 升序选择/键集扫描或 advisory lock），保证 T07 不重复且 T35 与保留范围/gateway 变更互斥。Owner：Architect/Database → CONTRACT/DATABASE。
- **I-3（OPEN，Product/D01，非阻塞）**：§13 未列举 IPAddress 字段，是否含 metadata。**PROPOSED**：不落 metadata（同 F009 Pool），仅 description 可空；请求含 metadata→422，响应不含。Owner：Product/用户 → D01 §5.9。
- **I-4（OPEN，产品/设计，非阻塞）**：§13 未说明 network/address 是否可改。**PROPOSED**：两者创建必填、创建后不可改（改地址等同新建；改 network 会破坏 CIDR 归属与 Cluster 唯一），镜像 Interface.resource 与 F009 network 不可改口径。Owner：Product/用户 → Architect/CONTRACT。
- **I-5（OPEN，产品/设计，非阻塞）**：§11 仅规定 INACTIVE Network「禁止新增 IP 分配、允许查询与释放」，未明示是否允许对已有 IP 绑定/解绑。**PROPOSED**：绑定/解绑/转移为关系编辑、非“新增分配”，不受 Network INACTIVE 限制；仅新建 IP 记录（自动/手动分配）要求 ACTIVE。Owner：Product/用户 → D01/CONTRACT。
- **I-6（OPEN，产品/设计，非阻塞）**：分配来源 ip_pool 的设置与可变性。**PROPOSED**：自动分配必填=指定 AUTO 池；手动分配=地址所属池（若有）或 null（池外，含跨多池时取含该地址的池）；创建后不可改（历史保留）；Pool 删除/缩小不影响。Owner：Architect/Database → CONTRACT。
- **I-7（OPEN，跨 Feature 边界）**：T22/T23 的 Endpoint 引用数据来自 F012，T32 容量显示归 F013。**PROPOSED**：F010 交付 `Endpoint←IPAddress` 引用检查注册点（随 F012 注册）、Network/Interface 引用检查器、§20 容量数据接口；含 Endpoint 的端到端与 Dashboard 显示在 F012/F013 集成完成。Owner：Architect/协调器。
- **I-8（OPEN，D02 关闭点）**：D02 的约束/索引/锁/IPAM 并发在本 Feature CONTRACT 后关闭。**PROPOSED**：由 Architect 在 CONTRACT、Database 在 DATABASE Gate 签核 `ip_addresses` 唯一/索引、`_lock_network` 复用、`IpOccupancyProvider` 真实实现与 T07/T35 方案后关闭 D02 相应部分。Owner：Architect/Database。
- **I-9（OPEN，设计，非阻塞）**：自动分配请求是否可同时绑定 Interface。**PROPOSED**：分配与绑定分离（分配创建未绑定 IP，绑定单独操作）；是否允许一次请求内绑定交 CONTRACT。Owner：Architect/CONTRACT。
- **I-10（OPEN，订正，非阻塞）**：F009-CON-01——F010 落地真实占用后，F008 错误集需补 `address_in_use{field:"gateway"}`（Network PATCH 设已占用 gateway）；F009-CON-02/F008-REV-01/02 errata 一并按协调器裁定订正。Owner：Architect/协调器。

## 8. 交 Architect 的输入
1. 实体方案：IPAddress 独立表 PK=UUID；FK network_id→networks(id)（RESTRICT）；interface_id 可空 FK→interfaces(id)；ip_pool_id 可空 FK→ip_pools(id)（承接 F009 DB-D105 的来源历史）；address 依 §26 用 PostgreSQL INET 主机地址；cluster 归属表示见 I-1。
2. 约束：network_id NOT NULL、address NOT NULL；address 属 Network CIDR；非 gateway/RESERVED/禁用（手动）；同 Cluster 未删除 address 唯一（I-1）；interface_id 可空且绑定/转移须 Cluster 一致；CHECK family=4/masklen=32；description 可空（I-3）。
3. 生命周期与引用：软删/恢复；恢复重检 CIDR/唯一/Cluster/引用；注册 `network←未删 IPAddress`、`interface←未删 IPAddress` 引用检查器；预留 `endpoint←未删 IPAddress` 挂钩（F012）；IPPool 来源为例外不阻止。
4. 分配：自动分配（条件/升序/耗尽不切换/并发不重复）与手动分配（池内/池外、禁 gateway/RESERVED/禁用）契约；API 建议 `/api/v1/ip-addresses`（创建=手动、自动分配端点、绑定/解绑/转移、释放、恢复、详情/列表、Activity）。
5. 并发：复用 F008/F009 `_lock_network`（networks 行 FOR UPDATE）；注册真实 `IpAddressOccupancyProvider`（F009 DR-109/110）；保证 §12.1/§11.1 保留范围/网关变更与并发分配互斥（T33/T35）；D02 约束/索引/锁/IPAM 并发在本 CONTRACT 闭合（I-8）。
6. 容量：实现 §20 Network 与 AUTO 池容量数据口径（可分配/占用/剩余），供 F013 消费；不建 Dashboard 页面。
7. API/错误口径：沿用 F002/F003/F008/F009 CONFLICT reason（`address_in_use`、`range_overlap`、`unique_conflict`、`reference_exists`、`dependency_deleted`、`not_deleted`），未认证先于权限；D01 §4 省略语义、422/409 口径、乐观锁。
8. 审计：CREATE（分配）/UPDATE（绑定/解绑/转移/字段）/DELETE（释放）/RESTORE 写 Audit（before/after）；Activity 全角色。
9. D01 补齐：新增 §5.9 IPAddress 字段口径（address 主机 IPv4 属 CIDR、interface 同 Cluster 可空、ip_pool 来源可空、description、是否 metadata），CONTRACT 签核（I-3/I-4/I-5/I-6）。
10. 待裁定/记录：I-1（唯一表示与并发）、I-2（自动分配并发）、I-3（metadata 与字段）、I-4（network/address 可变性）、I-5（INACTIVE 下绑定/解绑）、I-6（来源设置）、I-7（Endpoint/容量跨 Feature）、I-8（D02 关闭）、I-9（分配即绑定）、I-10（F009-CON-01 订正）。

## 9. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：IPAddress 实体/依赖方案、layers、api_required；CONTRACT 定稿 `/api/v1/ip-addresses` 与 D01 §5.9 IPAddress 字段口径，签核 I-3/I-4/I-5/I-6 并关闭 D02 约束/索引/锁/IPAM 并发；DATABASE 依 D01 签核同 Cluster 唯一/索引、`_lock_network` 复用、`IpAddressOccupancyProvider` 真实实现、软删/恢复重检与真实 PostgreSQL 验证方案。