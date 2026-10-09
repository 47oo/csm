# F009 IP Pool 地址池 — PRODUCT 阶段报告

- **Feature**：F009 IP Pool 地址池（FEATURE，P0，M4 网络与 IPAM，deps [F008]）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`
- **依据**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12、§12.1、§14、§20、§21、§22、§23、§25、§26、§27、§28、§31 T15/T16/T17/T18/T23/T24/T25/T26/T30/T31/T32/T33/T34/T35/T37/T40/T41、§35.2 Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02/D03）；plan_revision 4 F009；`docs/features/F008/product.md`（F008 DONE）；d01-conventions.md v7；database/f008-network.md v1；api/F008.md v1。

## 1. 目标与范围

### 1.1 目标
在 F008 Network 基础上，提供 IPPool 实体登记与维护：在某个 Network 内表达一段 IPv4 起止地址范围及其分配模式（AUTO / MANUAL / RESERVED），作为 F010 IPAddress 分配与 F013 容量统计的地址范围输入，并定义保留范围与网关变更的占用冲突语义。

### 1.2 本次范围（CONFIRMED）
- 字段（§12）：network、name、start_address、end_address、allocation_mode、description。
- 归属与范围（§12/§14）：Pool 属一个 Network；一个 Network 可有多个 Pool；start_address、end_address 均属于该 Network 的 CIDR；start_address 不大于 end_address（含相等，单地址池）。
- 名称（§4.1）：同 Network 内未删除唯一、大小写不敏感（保留展示）、允许中文及内部普通空格（不自动合并）、删除后可复用、恢复重检。
- 互不重叠（§12）：同 Network 的未删除池两两不重叠，包括 RESERVED 池；不同 Network 不受本 Feature 约束（跨 Network CIDR 已在 F008 保证不重叠）。
- allocation_mode（§12）：MANUAL / AUTO / RESERVED，默认 MANUAL；AUTO=允许自动或手动；MANUAL=仅手动；RESERVED=禁止分配。
- 保留范围与网关变更冲突（§12.1）：新建或扩大 RESERVED、AUTO/MANUAL 改为 RESERVED、将已占用地址设为 gateway 均拒绝，并返回冲突数量与可查询明细（含未绑定 Interface 的占用）；AUTO↔MANUAL 互换、RESERVED→AUTO/MANUAL 满足约束后允许；冲突检查须并发保护（D02）。
- 池变更不回收（§12/§21）：删除或缩小 Pool 不删除、不释放已分配 IP，原 IP 继续占用；分配来源作为历史保留，不能由 Pool 删除隐式删除或释放（§21 引用检查对分配来源关系的明确例外）。
- 生命周期（§21）：软删；默认查询隐藏；ADMIN 恢复/查看已删；无隐式级联；恢复重检名称唯一、所属 Network 有效性与范围重叠（RESERVED 恢复还须重检占用冲突）。
- 权限/审计（§22/§23）：EDITOR 增改；ADMIN 删/恢复/查看已删；VIEWER 只读；CREATE/UPDATE/DELETE/RESTORE 写 Audit。

### 1.3 使用者
EDITOR 登记与维护地址池范围/模式；ADMIN 删除、恢复、查看已删；VIEWER 查询。运维人员据地址池范围理解哪些地址可自动、可手动或保留。

## 2. 字段契约（IPPool，补齐 D01）

| 字段 | 类型 | 可空 | 创建必填 | 单位 | 合法值/语义 |
| --- | --- | --- | --- | --- | --- |
| network | UUID | 否 | 是 | — | 引用存在、未软删的 Network（§4.1/§12）；创建后可否修改见 I-2（PROPOSED 不可改） |
| name | string | 否 | 是 | — | trim 首尾；非空；禁控制字符（Cc/Cf）；仅 ASCII A-Z→a-z 折叠、非 ASCII 原样、保留展示；允许中文及内部普通空格、不自动合并；同 Network 未删除内唯一；长度交 D01（PROPOSED 1–255，同 Network/Cluster；见 I-4） |
| start_address | IPv4 | 否 | 是 | — | 合法 IPv4 地址；属于该 Network 的 CIDR（越界→拒绝）；start_address ≤ end_address |
| end_address | IPv4 | 否 | 是 | — | 合法 IPv4 地址；属于该 Network 的 CIDR（越界→拒绝）；end_address ≥ start_address |
| allocation_mode | enum | 否 | 否 | — | MANUAL\|AUTO\|RESERVED；默认 MANUAL；分配行为见 §3/§4；显式 null/非法→422 |
| description | string | 是 | 否 | — | 描述性自由文本；长度交 D01（现状 DB 为 text、无长度上限，同 F003/F004/F007/F008） |
| id / version / created_at / updated_at / deleted_at | 标准 | — | — | — | 稳定 UUID；version 乐观锁（§23）；timestamptz UTC（D01 §2）；deleted_at 软删（§21） |

补充：
- 省略语义（§4.1 / D01 §4）：创建省略非必填→默认/null；更新（PATCH）省略=保持（exclude_unset）；显式 null 仅清空 nullable（description）；必填/非 nullable（network/name/start_address/end_address/allocation_mode）显式 null→422；未知/只读字段→422。
- 名称归一化（§4.1 / D01 §5）：trim→非空→禁控制字符；唯一比较用归一化键（PROPOSED name_key=ASCII_lower(btrim(name))，应用逐码位、DB translate、禁 lower()/str.lower()）；仅未删除对象参与唯一；软删后复用；恢复重检冲突不覆盖新对象。
- start/end 地址：为单个 IPv4 主机地址（非 CIDR/掩码）。是否额外要求落在 §11.1「基础可用地址」内由 I-3 记录（PROPOSED：仅要求属 CIDR，不额外限制；网络/广播/gateway/禁用地址由 §11.1 在可分配集合与 F010 分配校验中排除）。
- 不落字段（§12）：Pool 不存 metadata、不存 status/启用开关、不存 auto_allocate（自动分配开关在 Network 级，§11）；Pool 不持有 IP 列表，也不做容量数值计算（F013）。

## 3. 领域影响分析

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 未决 |
| --- | --- | --- | --- | --- | --- |
| IPPool | 多对一依附 Network；1:N 分配来源（IPAddress，F010） | 名称唯一=同 Network | 创建/改范围或模式（受限）/软删/恢复 | §12、§21 | network 可变性（I-2） |
| 池范围互不重叠 | 同 Network 未删除池两两不重叠（含 RESERVED）；INACTIVE Network 的池参与 | Network | 创建/改起止/恢复重检 | §12/§27 | 重叠表示、闭区间语义与并发（I-1） |
| name 唯一 | 同 Network 未删除，大小写不敏感 | Network | 软删后复用；恢复重检 | §4.1/§21/Q10-B | D01 长度（I-4） |
| allocation_mode | MANUAL/AUTO/RESERVED 决定地址可否分配 | 本 Pool | 改模式受 §12.1 约束 | §12/§12.1 | 分配执行在 F010（I-5） |
| IPPool↔IPAddress | IP 记录引用分配来源 Pool | 同 Network | Pool 删除/缩小不回收 IP；来源历史保留 | §12/§21 | 来源引用在软删后如何保留（I-1） |
| RESERVED / gateway 占用冲突 | 变更后范围内存在未删除 IP（含未绑定）时拒绝 | 本 Network | 新建/扩大 RESERVED、改为 RESERVED、设 gateway | §11.1/§12.1 | 占用数据源为 F010（I-5）、并发（D02） |
| gateway | 属 CIDR 基础可用、非禁用、排除可分配 | 本 Network | Network PATCH 时重检占用 | §11/§11.1 | 占用 gateway 冲突归属（I-5） |
| 展示/容量 | §20 Network 与 AUTO 池容量口径；列表 | 随 Network | — | §20/§28 | 容量数值归 F010/F013 |

## 4. 必须遵守的已确认约束
- §12：字段清单；Pool 属 Network；起止均属 Network；起≤止；同 Network 未删除池互不重叠（含 RESERVED）；allocation_mode 默认 MANUAL 及三种模式分配行为；删除/缩小池不回收已分配 IP 且保留来源历史（§21 引用检查例外）。
- §12.1：新建/扩大 RESERVED、AUTO/MANUAL→RESERVED、已占用地址设 gateway 均拒绝并返回冲突数量与可查询明细（含未绑定占用）；AUTO↔MANUAL、RESERVED→AUTO/MANUAL、删除/缩小在满足约束后允许；冲突检查与变更须并发保护；恢复不得绕过保留范围/网关占用检查。
- §4.1：Pool 起止地址创建必填；名称 trim、禁空/控制字符、大小写不敏感、允许中文与内部普通空格且不自动合并、同 Network 唯一、删除后复用、恢复重检。
- §11.1/§20：可分配集合 = 基础可用地址 − gateway − RESERVED 池范围 − 禁用地址；自动、手动、恢复与容量共用边界；AUTO 池容量取池范围与可分配集合交集。
- §14：IP 必须属于关联 Network 的 CIDR；同 Cluster IP 唯一（执行在 F010）。
- §21：软删默认隐藏；ADMIN 恢复/查看已删；有未删除依赖禁删并返回引用列表，但 Pool 的分配来源关系为例外（不阻止删除、不回收 IP）；恢复重检唯一性、所属对象有效性与关系约束，失败不覆盖新对象。
- §22：CREATE/UPDATE/DELETE/RESTORE 写 Audit；Activity 全角色；不记敏感内容。
- §23：EDITOR 增改；VIEWER 只读；删除/查看已删/恢复 ADMIN；乐观锁版本冲突检查。
- §27：同 Network 池范围不重叠与名称唯一由 PostgreSQL 兜底，真实 PG 验证；引用检查 DB+业务共同保证。
- §4/D01：内部关联用稳定 UUID；D01 §4 省略语义与 422 口径；F008 约定 F009 创建子对象须取同 Network 行锁（F008 I-4/DB-D90）。

## 5. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | Pool 名称首尾空白 trim；空名/控制字符拒；中文与内部普通空格允许且不自动合并 | §4.1/T40 |
| A2 | 同 Network 创建大小写不敏感重名 Pool（如 WEB / web）被拒（409 CONFLICT{reason:"unique_conflict",field:"name"}）；不同 Network 同名允许 | §4.1/T40 |
| A3 | 软删后同名 Pool 可重建；存活同名存在时创建失败；名称被复用时旧 Pool 恢复失败且不覆盖新对象 | §4.1/§21/T41 |
| A4 | 缺失 network/name/start_address/end_address 创建失败（422）；network 不存在/已软删时创建失败（422） | §4.1/§12 |
| A5 | 起止地址任一不属于该 Network CIDR（越界）被拒（422）；非 IPv4/非法地址被拒（422） | §12/§14/T15 |
| A6 | start_address > end_address（逆序）被拒（422）；start=end（单地址池）允许 | §12/T15 |
| A7 | 同 Network 与未删除 Pool 范围重叠（闭区间相交，含完全相同、共享端点）被拒（409 CONFLICT{reason:"range_overlap",field:"start_address/end_address",conflicts}） | §12/T15 |
| A8 | allocation_mode 省略→MANUAL；显式设置按值保存；非法值/显式 null→422 | §12/T15/T37 |
| A9 | allocation_mode 语义：AUTO 允许自动与手动；MANUAL 仅手动；RESERVED 禁止分配；F009 正确保存并暴露该属性，分配执行由 F010 依此判定 | §12/T15 |
| A10 | 新建或扩大 RESERVED 池，变更后范围内存在未删除 IP（含未绑定 Interface）时拒绝，返回冲突数量与可查询明细 | §11.1/§12.1/T33 |
| A11 | AUTO/MANUAL 改为 RESERVED，范围内存在未删除 IP 时拒绝，返回冲突数量与明细 | §12.1/T33 |
| A12 | 将某已占用地址设为 gateway（Network PATCH）被拒，含未绑定 Interface 的占用，返回冲突数量与明细 | §12.1/T33 |
| A13 | AUTO↔MANUAL 互换、RESERVED→AUTO/MANUAL 在满足其它约束后允许，不改变已有 IP | §12.1/T34 |
| A14 | 删除或缩小 Pool（含 RESERVED）成功；已分配 IP 继续占用、不删除不释放，IP 记录保留分配来源历史 | §12/§21/T34 |
| A15 | RESERVED 恢复重新检查范围重叠与占用冲突，AUTO/MANUAL 恢复重检范围重叠；恢复不自动恢复 IP；失败不覆盖新对象 | §21/§12.1/T24 |
| A16 | Pool 恢复重检名称唯一、Network 有效性、范围不重叠；失败不覆盖新对象 | §21/T24 |
| A17 | 权限：VIEWER 只读；EDITOR 增改；删除/查看已删/恢复 ADMIN | §23/T25 |
| A18 | CREATE/UPDATE/DELETE/RESTORE 写 Audit 且同事务；Activity 全角色可见 | §22 |
| A19 | 默认列表隐藏软删、按 network 与 allocation_mode 过滤；分页/排序/过滤/模糊符合列表基线 | §21/§28 |
| A20 | DB 对同 Network 未删除名称（归一化键）唯一与池范围不重叠兜底，真实 PG 验证 | §27/T15 |
| A21 | 名称归一化在 API、导入（F014 适用时）、搜索（F013）与 DB 间一致；仅未删除对象参与唯一 | §4.1/§27 |
| A22 | 保留范围/网关变更与并发 IP 分配不能同时成功形成冲突；事务失败不留部分变更或错误容量 | §12.1/T35 |
| A23 | 乐观锁：过期版本编辑被拒（409 VERSION_CONFLICT），无静默覆盖 | §23/T26 |

说明：A10–A12、A22 的占用数据来源于 F010 IPAddress；F009 交付冲突检查契约、网络行锁域与模式/范围校验，含 IP 占用的端到端验证在 F009/F010 集成（T33/T35）完成，见 §7 I-5。

## 6. 明确排除项
- 不做 IP 地址的自动/手动分配、解绑、释放、绑定 Interface、IP 唯一性与地址合法性执行（F010）；F009 仅提供池范围与 allocation_mode。
- 不做 Network/AUTO 池容量数值计算与可分配/占用/剩余展示（F010 数据、F013 汇总）；F009 不返回容量数值。
- 不做 Endpoint、Service 及其与 IP 的关系（F011/F012）。
- 不做 CSV/Excel 导入（F014，接口/Network/Pool/IP 导入为后续扩展）；全局搜索/Dashboard/列表聚合（F013）；完整 Audit 查询页（F015）。
- 不做 IPv6；不做 DHCP、路由、防火墙、VLAN 划分、网段自动发现、实时监控。
- Pool 不存 metadata、status、auto_allocate 与 IP 列表；不由名称或范围推断地址分类；不自动分配地址；不因 RESERVED 池自动创建 IP 或 Endpoint。
- 不改动 F008 已交付的 Network 语义（CIDR 存储、gateway 取值域、CIDR 不重叠）；F009 只新增 Pool 与占用冲突检查。

## 7. 依赖与未决问题
依赖（CONFIRMED）：F008（Network 实体、CIDR/网关/禁用边界语义、可分配集合定义、引用检查器与网络行锁协议，DONE）；F001（PostgreSQL 基线、btree_gist 预置、真实 PG 测试基线）；D01 共享约定（v7+）。F010 依赖本 Feature 的池范围与模式；F013 依赖本 Feature 的 AUTO 池范围与模式。

BLOCKING：无。

CONFIRMED：§12 全部；§11.1 边界与禁用清单；§12.1 冲突操作与并发要求；§4.1 名称规范与唯一；§21 软删/恢复/引用检查及 Pool 例外；§22；§23；§27；§28；Q04-A/Q04-B/Q10-A/Q10-B。

PROPOSED/OPEN（非阻塞）：
- **I-1（OPEN，Database/D02）**：同 Network 池范围不重叠的表示与并发兜底（PG 范围类型/inet+btree_gist 排除约束或等价）、闭区间相交语义、软删参与范围、恢复重检落点；IP 分配来源引用在 Pool 软删后如何保留（soft FK/历史字段）、软删引用限制。Owner：Architect/Database → DATABASE Gate。
- **I-2（OPEN，产品/设计，非阻塞）**：§12 未说明 Pool 的 network 是否可改。**PROPOSED**：创建必填、创建后不可直接修改（改名范围需以删除重建表达），与 Resource.cluster 口径一致。若确认可变，则须重检起止是否属目标 Network CIDR 与目标 Network 内不重叠。Owner：Product/用户 → Architect/CONTRACT。
- **I-3（OPEN，产品/设计，非阻塞观察）**：§12 仅要求起止「属于 Network」，未禁止池范围包含网络/广播/禁用地址。**PROPOSED**：F009 不新增范围限制，仅校验属 CIDR 与起≤止；网络/广播/gateway/RESERVED/禁用地址经 §11.1/§20 在可分配集合与 F010 分配校验中排除。是否收紧属新业务限定，须用户裁定。Owner：Product/用户 → D01。
- **I-4（OPEN，D01）**：D01 尚未界定 IPPool name 长度（PROPOSED 1–255、仅 ASCII 折叠、内部普通空格不合并）与 description 长度（PROPOSED 沿用 text 无上限，同 F003/F004/F007/F008）；D01 §5 表 IPPool/Service 行「允许单个普通空格」与 §4.1「内部普通空格不自动合并」措辞需一致化。Owner：Architect/Database → CONTRACT/D01。
- **I-5（OPEN，跨 Feature 边界）**：§12.1 的占用冲突（RESERVED vs 未删除 IP、已占用地址设 gateway）依赖 IPAddress 数据。F009 在 F010 之前交付，无法单独形成/验证 IP 占用数据。F008 已将「已占用 IP 设为 gateway」标为 F009/F010（F008 I-5，F008 未实现）。**PROPOSED**：F009 定义冲突检查契约、返回冲突数量/明细结构、Network 行锁域，并预留 IP 占用查询接口；IP 占用执行与 T33/T35 端到端验证在 F010 及 F009/F010 集成完成。Owner：Architect/协调器。
- **I-6（PROPOSED，非阻塞）**：Pool 不落 metadata（§12 字段清单无该字段），与 Network 自有 metadata 区分；CONTRACT 明确响应不含 metadata。

## 8. 交 Architect 的输入
1. 实体方案：IPPool 独立表 PK=UUID，FK network_id→Network(id)；字段同 §2；start_address/end_address 依 §26 用 PostgreSQL INET。
2. 约束：network_id NOT NULL；start_address/end_address NOT NULL 且属 Network CIDR（应用 + DB 校验）；CHECK start_address ≤ end_address；同 Network 未删除名称归一化键部分唯一（I-4）；同 Network 未删除池范围不重叠（I-1）；allocation_mode NOT NULL DEFAULT 'MANUAL' CHECK∈3 值；description text NULL。
3. 生命周期与引用：软删/恢复；删除 Pool 不阻止、不级联、不回收 IP（§12 例外）；恢复重检名称唯一、Network 有效性、范围不重叠、（RESERVED）占用；IP 分配来源引用须在软删后保留（I-1）。
4. 冲突契约：新建/扩大 RESERVED、改为 RESERVED、设已占用 gateway 拒绝并返回冲突数量与可查询明细结构（含未绑定占用）。
5. 并发：与 F008/F010 共用 Network 行锁域（F008 DB-D90/DB-D93）；RESERVED/网关变更与并发 IP 分配互斥（D02/T35）。
6. API：/api/v1/ip-pools 契约，创建/更新/详情/列表；沿用 F004/F008 与 D01 §4 省略语义、422/409 错误口径、乐观锁。
7. 审计：CREATE/UPDATE/DELETE/RESTORE 写 Audit（before/after）；Activity 全角色。
8. D01 补齐：新增 IPPool 字段口径小节（name 长度与折叠、start/end 地址域与越界/逆序口径、allocation_mode 默认与取值、description 长度），CONTRACT 签核（I-4）。
9. 边界语义：向 F010 暴露池范围与 allocation_mode（AUTO 供自动分配、RESERVED 禁分配、MANUAL 仅手动），向 F013 暴露 AUTO 池范围供 §20 容量；不在本 Feature 分配地址或计算容量数值。
10. 待裁定/记录：I-1（重叠表示与并发/来源历史）、I-2（network 可变性）、I-3（禁用/网络地址范围限制）、I-4（D01 字段口径）、I-5（占用冲突跨 Feature 落点与验证）、I-6（metadata 排除）。

## 9. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE：IPPool 实体/依赖方案、layers、api_required；CONTRACT 签核 /api/v1/ip-pools 与 D01 IPPool 字段口径。DATABASE 依 D01 签核池范围不重叠表示（范围类型/inet+btree_gist 排除约束）、名称归一化键部分唯一、软删引用限制与分配来源历史保留、恢复重检、与 F008/F010 共用的 Network 行锁域及真实 PostgreSQL 验证方案。