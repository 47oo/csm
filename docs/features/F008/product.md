# F008 Network 网络管理 — PRODUCT 阶段报告

- **Feature**：F008 Network 网络管理（FEATURE，P0，M4 网络与 IPAM，deps [F003]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-09）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12.1、§13、§18、§20、§21、§22、§23、§25、§27、§28、§31 T14/T16/T24/T25/T29/T30/T37/T38/T40/T41、§35.2 Q02-A/Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）；plan_revision 4 F008；d01-conventions.md v6。

## 1. 目标与范围

### 1.1 目标
在 F003 Cluster 基础上，提供 Network 实体登记与维护：表达某 Cluster 下的 IPv4 网络（CIDR、网关、状态、自动分配开关），作为 IPPool（F009）与 IPAddress（F010）的父域，并定义 CIDR/网关边界语义供地址分配与容量统计（F010/F013）共用。

### 1.2 本次范围（CONFIRMED）
- 字段（§11）：cluster、name、cidr、gateway、status、auto_allocate、description、metadata。
- 仅 IPv4（§11）；CIDR 优先使用 PostgreSQL CIDR 存储（§11/§26）。
- 所属（§11）：Network 属一个 Cluster；一个 Cluster 可有多个 Network。
- 名称（§4.1）：同 Cluster 内唯一、大小写不敏感（保留展示）、允许中文及内部普通空格（不自动合并）、删除后可复用。
- CIDR 重叠（§11）：同 Cluster 未删除 Network 不允许 CIDR 重叠；不同 Cluster 允许；INACTIVE 仍参与重叠检查。
- 变更限制（§11）：已存在未删除 Pool 或 IP 时，禁止直接修改 CIDR 或所属 Cluster；历史引用保留须在数据库设计中说明。
- gateway（§11/§11.1）：可空；填写时必须属于 CIDR 的基础可用地址且不在禁用范围内，并从可分配集合排除。
- 状态（§11）：ACTIVE/INACTIVE，默认 ACTIVE；INACTIVE 允许查询与释放已有 IP，禁止新增 IP 分配；释放仍须 ADMIN 权限及引用检查。
- auto_allocate（§11）：默认 false，仅控制自动分配，不能绕过状态与地址约束。
- 生命周期（§21）：软删；默认查询隐藏；ADMIN 恢复/查看已删；有未删除 Pool/IP 引用时禁删并返回引用列表，不隐式级联；恢复重检唯一性、所属对象有效性与关系约束。
- 权限/审计（§22/§23）：EDITOR 增改；ADMIN 删/恢复/查看已删；VIEWER 只读；CREATE/UPDATE/DELETE/RESTORE 写 Audit。

### 1.3 使用者
EDITOR 登记维护；ADMIN 删除/恢复；VIEWER 查询。

## 2. 字段契约（Network，补齐 D01）

| 字段 | 类型 | 可空 | 创建必填 | 单位 | 合法值/语义 |
| --- | --- | --- | --- | --- | --- |
| cluster | UUID | 否 | 是 | — | 引用存在、未软删的 Cluster（§4.1/§11）；有未删除 Pool/IP 时不可改（I-4） |
| name | string | 否 | 是 | — | trim 首尾；非空；禁控制字符（Cc/Cf）；大小写不敏感；允许中文及内部普通空格、不自动合并；同 Cluster 未删除内唯一；长度交 D01（I-2） |
| cidr | IPv4 CIDR | 否 | 是 | — | 合法 IPv4 CIDR；同 Cluster 未删除不重叠；有未删除 Pool/IP 时不可改（I-1/I-4） |
| gateway | IPv4 | 是 | 否 | — | 可空；填写时属该 CIDR 基础可用地址且不在禁用范围（§11.1）；从可分配集合排除 |
| status | enum | 否 | 否 | — | ACTIVE\|INACTIVE；默认 ACTIVE；INACTIVE 禁新增分配，仍参与重叠检查 |
| auto_allocate | boolean | 否 | 否 | — | 默认 false；仅控自动分配，不绕过状态与地址约束 |
| description | string | 是 | 否 | — | 描述性；长度交 D01 |
| metadata | object (JSONB) | 是 | 否 | — | 整值替换；归属交 CONTRACT（PROPOSED：Network 自有） |

补充：
- 省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；更新省略=保持；显式 null 仅清空 nullable；必填显式 null→422；不可变/只读字段→422。
- 名称归一化（§4.1/D01 §5）：trim→非空→禁控制字符；唯一比较用归一化键；仅未删除对象参与唯一；恢复重检冲突。
- gateway 不得为网络地址/广播地址（/0～/30 基础可用地址排除）及 §11.1 禁用地址；/31 按点对点、/32 时 gateway 必须为空（§11.1）。
- 不落字段（§11）：Network 不存 VLAN ID、网络分类（管理/业务/存储/IB）、地址池或 IP 列表；VLAN 仅 Interface 枚举值，非 Network 数值字段。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 未决 |
| --- | --- | --- | --- | --- | --- |
| Network | 多对一依附 Cluster；1:N IPPool（F009）、1:N IPAddress（F010） | 名称唯一=同 Cluster；CIDR 不重叠=同 Cluster | 创建/CIDR 或 Cluster 变更（受限）/软删/恢复 | §11、§21 | 字段口径交 D01（I-2） |
| CIDR 不重叠 | 同 Cluster 未删除 Network 两两不重叠；INACTIVE 参与 | Cluster | 创建/改 CIDR/恢复重检 | §11/§27 | 表示与并发兜底（I-1） |
| name 唯一 | 同 Cluster 未删除，大小写不敏感 | Cluster | 软删后复用；恢复重检 | §4.1/§21/Q10-B | 归一化键列（I-2） |
| gateway | 属 CIDR 基础可用地址、非禁用、排除可分配 | 本 Network | 可空；改 CIDR 时须重检 | §11/§11.1 | 占用地址设为 gateway 归 F009/F010（I-5） |
| Network←IPPool/IPAddress | 子对象引用 Network | 同 Cluster | 有未删除引用禁删/禁改 CIDR/Cluster；恢复重检 | §11/§21/§27 | 引用检查器落点（I-4） |
| 展示 | §18 经 IP 展示 IP/Network；§20 容量口径 | 随 Resource/Network | — | §18/§20 | 聚合归 F010/F013 |

## 4. 必须遵守的已确认约束
- §11：字段清单；仅 IPv4；CIDR 优先 PostgreSQL CIDR；同 Cluster 未删除 CIDR 不重叠（INACTIVE 参与）；有未删除 Pool/IP 时禁改 CIDR/Cluster；gateway 属 CIDR 且排除；status 默认 ACTIVE、INACTIVE 禁新增分配；auto_allocate 默认 false。
- §4.1：Network CIDR 创建必填；名称 trim、禁空/控制字符、大小写不敏感、允许中文与内部普通空格且不自动合并、同 Cluster 唯一、删除后复用。
- §11.1：gateway 须属基础可用地址（排除网络/广播），排除 §11.1 禁用范围；容量/分配共用同一边界。
- §21：软删默认隐藏；ADMIN 恢复/查看；有未删除依赖禁删并返回引用列表；不隐式级联；恢复重检唯一性、所属对象有效性与关系约束，失败不覆盖新对象。
- §22：CREATE/UPDATE/DELETE/RESTORE 写 Audit；Activity 全角色；不记敏感内容。
- §23：EDITOR 增改；VIEWER 只读；删除/查看已删/恢复 ADMIN。
- §27：同 Cluster 名称唯一与 CIDR 不重叠由 PostgreSQL 兜底，真实 PG 验证；引用检查 DB+业务共同保证。
- §4/D01 §1：内部关联用稳定 UUID；D01 §4 省略语义与 422 口径。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | 同 Cluster 创建大小写不敏感重名 Network（如 MGMT / mgmt）被拒（409 CONFLICT{reason:"unique_conflict",field:"name"}） | §4.1/T40 |
| A2 | 不同 Cluster 同名 Network 允许并存 | §4.1 |
| A3 | 名称首尾空白 trim；空名/控制字符拒；内部普通空格允许且不自动合并 | §4.1/T40 |
| A4 | 软删后同名可重建；存活同名存在时创建失败；名称被复用时旧对象恢复失败且不覆盖新对象 | §4.1/§21/T41 |
| A5 | 同 Cluster 与未删除 Network 的 CIDR 重叠（含完全相同）被拒；不同 Cluster 允许 | §11/T14 |
| A6 | INACTIVE Network 仍参与 CIDR 重叠检查 | §11/T14/T29 |
| A7 | 非 IPv4 或非法 CIDR 输入被拒（422） | §11/§4.1 |
| A8 | 缺失 cluster 或 cidr 创建失败（422）；cluster 不存在/已软删时创建失败 | §4.1/§11/§21 |
| A9 | 存在未删除 Pool 或 IP 时改 CIDR 或所属 Cluster 被拒并返回相关引用信息；无引用时按重叠/名称约束允许修改并重检目标 Cluster | §11/T14 |
| A10 | gateway 为空允许；gateway 不属于 CIDR 基础可用地址或落在禁用范围被拒（422） | §11/§11.1/T30 |
| A11 | gateway 从可分配集合排除，容量不将其计入可用 | §11.1/§20 |
| A12 | status 省略→ACTIVE；显式设置按值保存；非法值→422 | §11/T37 |
| A13 | auto_allocate 省略→false；显式设置按值保存；不能绕过状态与地址约束 | §11/T37 |
| A14 | INACTIVE Network 允许查询与释放已有 IP、禁止新增分配，auto_allocate 开启不能绕过 | §11/T16/T29 |
| A15 | 存在未删除 Pool/IP 引用时删除被拒并返回引用列表；不隐式级联；无引用可软删 | §21/§27/T23 |
| A16 | 恢复重检同 Cluster 名称唯一、Cluster 有效性、CIDR 不重叠与引用有效性；失败不覆盖新对象 | §21/§27/T24 |
| A17 | 权限：VIEWER 只读；EDITOR 增改；删除/查看已删/恢复 ADMIN | §23/T25 |
| A18 | CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务；Activity 全角色可见 | §22 |
| A19 | 默认列表隐藏软删、包含 INACTIVE 并可状态过滤；分页/排序/过滤/模糊符合列表基线 | §21/§28 |
| A20 | DB 对同 Cluster 未删除名称（归一化键）唯一与 CIDR 不重叠兜底，真实 PG 验证 | §27/T14 |
| A21 | 名称归一化在 API、导入（F014）、搜索（F013）与 DB 间一致；仅未删除参与唯一 | §4.1/§27 |
| A22 | Network 建立后，其 CIDR/网关边界作为 Pool 越界、IP 属于 CIDR、容量统计的共同输入（下游 F009/F010/F013 执行） | §11/§11.1/§14/§20 |

## 6. 明确排除项
- 不做 IPPool 起止地址、allocation_mode、池互不重叠与保留范围冲突（F009）。
- 不做 IP 的自动/手动分配、解绑、释放、IP 唯一性、地址边界执行与容量数值（F010）；F008 仅提供 CIDR/网关边界语义。
- 不做「将已占用 IP 设为 gateway」的冲突检测与冲突明细（§12.1 → F009/F010，见 I-5）。
- 不做 Interface（F007）、Service/ServiceEndpoint（F011/F012）。
- 不做 CSV/Excel 导入（F014）；全局搜索/Dashboard/列表聚合（F013）；完整 Audit 查询页（F015）。
- 不做 IPv6；不做 DHCP / 路由 / 防火墙 / VLAN 划分 / 网段自动发现。
- Network 不存 VLAN ID、网卡分类、Pool 或 IP 列表；不由 CIDR 推断 gateway 或分类，不自动分配地址。
- 不做实时网络状态、流量、可达性监控（§3 排除项）。

## 7. 依赖与未决问题
依赖（CONFIRMED）：F003（Cluster 实体与生命周期）、F001（PostgreSQL 基线、CIDR/btree_gist 扩展、真实 PG 测试基线）、D01 共享约定（v6+）。F009/F010 依赖本 Feature 落地 CIDR/网关语义；F008 的引用检查为 F009/F010 子对象预留。

BLOCKING：无。

CONFIRMED：§11 全部；§11.1 gateway 边界；§4.1 名称规范与唯一；§21 软删/恢复/引用检查；§22；§23；§27；§28；Q02-A/Q04-A/Q04-B/Q10-A/Q10-B。

PROPOSED/OPEN（非阻塞）：
- I-1（OPEN，Database/D02）：CIDR 不重叠的表示与并发兜底（PostgreSQL CIDR + btree_gist 排除约束或等价）、软删参与范围；跨表 CIDR 归属与软删引用限制、恢复重检落点在 DATABASE Gate 签核。Owner：Architect/Database。
- I-2（OPEN，D01）：D01 未界定 Network name 长度、大小写折叠口径与 CIDR 规范化（含 host 位时接受归一化还是拒绝）；CONTRACT 补 Network 字段口径。Owner：Architect/Database。
- I-3（OPEN，产品/设计，非阻塞观察）：§11 未禁止创建 CIDR 完全落在 §11.1 禁用范围内的 Network；基线不据此新增建网限制，是否收紧属新业务限定须用户裁定。Owner：Product/用户→D01。
- I-4（OPEN，Architect/Database）：有未删除 Pool/IP 时禁改 CIDR/所属 Cluster 的引用检查落点与并发语义；F008 建表时 F009/F010 子表尚未存在，需预留可扩展检查器。Owner：Architect/Database。
- I-5（OPEN，产品/设计边界）：「已占用 IP 设为 gateway 拒绝（含未绑定）」归 F009/F010（T33）；F008 须保证 gateway 语义可被下游复用。Owner：Architect。
- I-6（PROPOSED）：metadata 归 Network 自有（§11 字段清单），CONTRACT 确认；与 Resource 公共 metadata 无合并。

## 8. 交 Architect 的输入
1. 实体方案：Network 独立表 PK=UUID，FK cluster_id→Cluster(id)；字段同 §2；CIDR 依 §11/§26 用 PostgreSQL CIDR。
2. 约束：cluster_id NOT NULL；同 Cluster 未删除 CIDR 不重叠（I-1）；同 Cluster 未删除名称归一化键部分唯一（I-2）；gateway 属基础可用地址、非禁用、排除可分配；status NOT NULL DEFAULT 'ACTIVE'；auto_allocate NOT NULL DEFAULT false；有未删除 Pool/IP 时禁改 cidr/cluster（I-4）。
3. 生命周期与引用：软删/恢复；删除前检查未删除 Pool/IP 引用返回引用列表；恢复重检名称唯一、Cluster 有效性与 CIDR 不重叠。
4. API：/api/v1/networks 契约，创建/更新/详情/列表；CIDR 与 gateway 校验口径；沿用 F004/D01 省略语义与 422 口径。
5. 审计：CREATE/UPDATE/DELETE/RESTORE 写 Audit（before/after）；Activity 全角色。
6. D01 补齐：新增 Network 字段口径小节（name 长度与折叠、CIDR 规范化、gateway 取值域、description 长度），CONTRACT 签核。
7. 边界语义：向 F009/F010/F013 暴露可分配集合与容量边界（基础可用地址 − gateway − RESERVED − 禁用），不在本 Feature 实现分配。
8. 待裁定/记录：I-1（重叠表示与并发）、I-2（D01 字段口径）、I-3（禁用范围建网）、I-4（引用检查落点）、I-5（占用 gateway 归属）、I-6（metadata 归属）。

## 9. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：Network 实体/依赖方案、layers、api_required；CONTRACT 签核 /api/v1/networks 与 D01 Network 字段口径；DATABASE 依 D01 签核 CIDR 不重叠表示（btree_gist/排除约束）、名称归一化键部分唯一、软删引用限制与恢复重检、真实 PostgreSQL 验证方案。