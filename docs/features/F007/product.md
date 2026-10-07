# F007 Interface 接口管理 — PRODUCT 阶段报告

- **Feature**：F007 Interface 接口管理（FEATURE，P0，M3 虚拟化与接口，deps [F004]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-09）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§10、§13、§18、§21、§22、§23、§27、§31 T12/T20/T23/T37/T39/T40/T41、§35.2 Q10-B、§35.3 D01）；plan_revision 4 F007；d01-conventions.md v5。

## 1. 目标与范围

### 1.1 目标
在 F004 统一 Resource 基础上，提供 Interface 实体登记与维护：表达 Resource 的物理/虚拟网络接口、类型、标称速率、父接口与启用状态，作为 IP Address 的绑定端（§13），支撑 §18 详情 Interfaces 区域与 §33 查询场景。

### 1.2 本次范围（CONFIRMED）
- 所属（§10）：Interface 属一个 Resource；一个 Resource 可有任意数量 Interface；适用于 BARE_METAL 与 VIRTUAL_MACHINE。
- 字段（§10）：resource、name、interface_type、mac_address、speed_mbps、mtu、parent_interface、enabled、description、metadata。
- 类型枚举（§10）：PHYSICAL/VIRTUAL/BOND/BRIDGE/VLAN/LOOPBACK/OTHER，默认 OTHER，**不据名称推断**。
- enabled（§10）：默认 true，登记状态非实时探测。
- speed_mbps（§10/T39）：标称速率，Mbps，正整数或 null。
- 名称（§4.1/§10）：同 Resource 唯一、**区分大小写保留输入**、禁内部空白、删除后可复用。
- parent_interface（§10）：可空；必须同 Resource，禁自引用/循环；一期不做完整拓扑。
- MAC（§10）：可空；一期无全局唯一。
- 生命周期（§21）：软删；ADMIN 恢复/查看已删；有未删除 IP 引用时禁删并返回引用列表，不隐式级联。
- 与 IP 基数（§13）：一个 Interface 可关联多个 IPAddress；IP 的 interface 可空；Interface 不拥有 IP，删除不释放 IP。
- 权限/审计（§22/§23）：EDITOR 增改；ADMIN 删/恢复；VIEWER 只读；关键变更写 Audit。

### 1.3 使用者
EDITOR 登记维护；ADMIN 删除/恢复；VIEWER 查询。

## 2. 字段契约（Interface，补齐 D01）

| 字段 | 类型 | 可空 | 创建必填 | 单位 | 合法值/语义 |
| --- | --- | --- | --- | --- | --- |
| resource | UUID | 否 | 是 | — | 引用存在、未软删的 Resource；归属基线创建后不可直接改（I-4） |
| name | string | 否 | 是 | — | trim 首尾；非空；禁内部空白/Cc/Cf；区分大小写保留；同 Resource 未删除内唯一；长度交 D01 |
| interface_type | enum | 否 | 否 | — | PHYSICAL\|VIRTUAL\|BOND\|BRIDGE\|VLAN\|LOOPBACK\|OTHER；默认 OTHER；不由名称推断 |
| mac_address | string | 是 | 否 | — | 可空；一期无全局唯一；格式/长度交 D01（I-1） |
| speed_mbps | int | 是 | 否 | Mbps | 正整数或 null；0/负非法；标称速率非实时 |
| mtu | int | 是 | 否 | 字节 | 可空；范围交 D01（I-2） |
| parent_interface | UUID | 是 | 否 | — | 引用同 Resource 未删除 Interface；禁自引用/循环 |
| enabled | boolean | 否 | 否 | — | 默认 true；登记状态非实时探测 |
| description | string | 是 | 否 | — | 描述性；长度交 D01 |
| metadata | object (JSONB) | 是 | 否 | — | 整值替换；归属见 I-5（PROPOSED：Resource 公共） |

补充：
- 省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；更新省略=保持；显式 null 仅清空 nullable；必填显式 null→422；不可变/只读字段→422。
- 名称归一化（D01 §5）：仅 trim+非空+禁控制字符，**不做大小写折叠**；唯一比较用 trim 后原值；name_key 是否独立列由 Database 决定（I-3）。
- 无新增全局唯一：除「同 Resource 未删除 name 唯一」外无 MAC 唯一等。
- 不落字段（§4/§10/§13）：Interface 不存 IP/CIDR、VLAN ID、所属 Network 或管理/业务/存储分类；VLAN 仅枚举值非数值字段。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 未决 |
| --- | --- | --- | --- | --- | --- |
| Interface | 多对一依附 Resource；1:N 关联 IPAddress（IP 侧持引用） | 随 Resource 的 Cluster；名称唯一=同 Resource | 创建/软删/恢复；有未删除 IP 引用禁删 | §10、§13、§21 | 字段口径交 D01（I-1/I-2） |
| Interface→parent_interface | 自关联多对一 | 同 Resource | 可空；改父重检同 Resource/无环 | §10/T20 | 环检测落点（I-4） |
| name 唯一 | 同 Resource 未删除，区分大小写 | Resource | 软删后复用；恢复重检 | §4.1/§21/Q10-B | 归一化键列（I-3） |
| Interface←IPAddress | IP 引用 Interface，1:N | 同 Cluster | 删除前处理未删除 IP 引用 | §13/§21/§27 | IP 侧归 F010 |
| 展示 | §18 Interfaces：Interface/MAC/Speed/MTU/IP/Network | 随 Resource | — | §18 | 页面聚合归 F013 |

## 4. 必须遵守的已确认约束
- §10：字段清单；类型枚举默认 OTHER 不推断；enabled 默认 true；speed_mbps 标称 Mbps 正整数/null；parent_interface 同 Resource 禁自引用/循环；MAC 可空无全局唯一；类型不定义网卡分类。
- §4.1：名称去首尾空白、禁空/内部空白；Interface name 区分大小写保留、同 Resource 唯一、删除后复用；resource 创建必填。
- §13/§27：Interface 与 IP 为 1:N；删除 Interface 先处理 IP 引用。
- §21：软删默认隐藏；ADMIN 恢复；有未删除依赖禁删并返回引用列表；不隐式级联；恢复重检名称唯一与 Resource 有效性，失败不覆盖新对象。
- §22：CREATE/UPDATE/DELETE/RESTORE 写 Audit；Activity 全角色；不记敏感内容。
- §23：EDITOR 增改；VIEWER 只读；删除/查看已删/恢复 ADMIN。
- §27：同 Resource 名称唯一由 PG 兜底；parent_interface 与依赖约束 DB+业务共同保证，真实 PG 验证。
- §4/D01 §1：内部关联用稳定 UUID。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | 同 Resource 创建重名 Interface（大小写完全相同）被拒（422） | §4.1/T12 |
| A2 | 同 Resource 内 eth0 与 ETH0 视为不同名称并存（区分大小写） | §4.1/Q10-B/T40 |
| A3 | 名称含内部空白被拒；首尾空白 trim；空名/控制字符拒 | §4.1/T40 |
| A4 | 软删后同名可重建；存活同名存在时创建失败 | §4.1/§21/T12/T41 |
| A5 | interface_type 省略→OTHER；name=bond0 但类型省略仍 OTHER，不推断 BOND | §10/T37 |
| A6 | enabled 省略→true；显式设置按值保存 | §10/T37 |
| A7 | speed_mbps 正整数接受、0/负拒（422）、可空 null | §10/T39 |
| A8 | parent_interface 空允许；指向其它 Resource 的 Interface 拒（422） | §10/T20 |
| A9 | parent_interface 自引用拒；A→B→A 环路拒（422） | §10/T20 |
| A10 | mac_address 空可登记；两 Interface 同 MAC 均允许 | §10/T20 |
| A11 | resource 缺失/不存在/已软删时创建失败（422） | §4.1/§21 |
| A12 | 存在未删除 IP 引用时删除被拒并返回引用列表；不隐式级联；无引用可软删 | §21/§13/T23 |
| A13 | 恢复重检名称唯一与 Resource 有效性；名称被复用/Resource 仍删时恢复失败不覆盖 | §21/T24 |
| A14 | 权限：EDITOR 增改；VIEWER 只读；删除/恢复 ADMIN | §23/T25 |
| A15 | CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务；Activity 全角色 | §22 |
| A16 | 一个 Interface 可绑定多个 IPAddress；解绑仅移除关系不释放（关系承载，执行 F010） | §13 |
| A17 | 类型不定义网卡分类；管理/业务/存储/IB 经 IPAddress→Network 表达；Interface 不存 IP/CIDR/VLAN ID | §4/§10/§13 |
| A18 | DB 对同 Resource 未删除 name 部分唯一兜底，真实 PG 验证 | §27/T12 |
| A19 | Resource Detail Interfaces 区域可展示 Interface/MAC/Speed/MTU/IP/Network | §18 |

## 6. 明确排除项
- 不改 Resource 基础字段与 hostname 唯一性（F004）。
- 不做 Network/IP Pool/IP Address 分配/绑定/解绑/释放/容量（F008–F010）；Interface 仅提供绑定端与被引用关系。
- 不做 Service/ServiceEndpoint（F011–F012）。
- 不做 CSV/Excel 导入（F014）；列表/搜索/Dashboard/Cluster Detail 聚合（F013）；完整 Audit 查询页（F015）。
- 不做 Bond/Bridge/VLAN 完整拓扑/链路聚合/VLAN 划分建模。
- 不做 MAC 全局唯一、自动发现、实时速率/流量/状态采集与监控。
- 不据接口名推断 interface_type，也不由类型推导网卡分类或 IP 归属。

## 7. 依赖与未决问题

依赖（CONFIRMED）：F004（统一 Resource、稳定 ID、软删/恢复、引用检查、Audit、权限、DB 唯一基座、D01）。Interface 对 Resource 无类型限制，不依赖 F005/F006；IP 绑定端 F010 落地。

BLOCKING：无。

CONFIRMED：§10 全部；§4.1；§13 与 IP 的 1:N 及「删除前处理 IP 引用」；§18；§21；§22；§23；§27；Q10-B。

PROPOSED/OPEN（非阻塞）：
- I-1（OPEN，D01）：D01 未界定 name 长度、mac_address 格式、speed_mbps 上限；CONTRACT 补 Interface 字段口径小节。Owner：Architect/Database。
- I-2（OPEN，产品/设计）：需求未定义 mtu 语义与范围；基线可空正整数、未知 null、原样存储，范围交 D01。若限定取值域属新业务限定，须用户裁定。Owner：Product/用户→D01。
- I-3（OPEN，Database）：name 区分大小写仅 trim，是否需独立归一化键列由 Database 决定；唯一以同 Resource 未删除 name 部分唯一兜底，恢复重检。
- I-4（OPEN，Database/D02）：parent_interface 环检测落点（应用/触发器）与并发语义；归属固定是否允许 PATCH 改 resource（基线创建后不可直接改，须 Architect/Database 确认）。Owner：Architect/Database。
- I-5（PROPOSED）：metadata 归 Resource 公共字段，Interface 不新增独立列；CONTRACT 确认。Owner：Architect。

## 8. 交 Architect 的输入
1. 实体方案：Interface 独立表 PK=UUID，FK resource_id→Resource(id)；字段同 §2。
2. 约束：resource_id NOT NULL；同 Resource 未删除 name 部分唯一（区分大小写 trim）；parent_interface 自关联 FK，校验同 Resource/禁自引用/禁循环（I-4）；mac_address/speed_mbps/mtu 可空；enabled NOT NULL DEFAULT true；无 MAC 全局唯一。
3. 生命周期与引用：软删/恢复；删除前检查未删除 IPAddress 引用返回引用列表；恢复重检名称唯一与 Resource 有效性。
4. API：/api/v1/interfaces 契约，创建/更新/详情/列表；扩展 F004 契约，不新增绕过 Service Layer 的写路径；D01 省略语义与 422 口径。
5. 审计：CREATE/UPDATE/DELETE/RESTORE 写 Audit（before/after），Activity 全角色。
6. D01 补齐：新增 Interface 字段口径小节（name 长度、mac_address 格式、mtu 范围、speed_mbps 上限），CONTRACT 签核。
7. 待裁定/记录：I-2（MTU 范围）、I-4（环检测落点与归属可改性）、I-5（metadata 归属）。

## 9. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：Interface 实体/依赖方案、layers、api_required；CONTRACT 签核 /api/v1/interfaces 与 D01 Interface 字段口径；DATABASE 依 D01 签核 name 部分唯一、parent_interface 约束与环检测缺口、真实 PostgreSQL 验证方案。