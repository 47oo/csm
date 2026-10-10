# F010 IP 地址分配与容量 — ARCHITECTURE 阶段报告

- **Task**：F010（FEATURE，P0，M4 网络与 IPAM，deps [F007, F008, F009]）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-09）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12、§12.1、§13/§13.1/§13.2/§13.3、§14、§16、§18、§20、§21、§22、§23、§25、§27、§28、§31 T04–T07/T10/T16/T17/T18/T22/T23/T24/T25/T26/T30/T31/T32/T34/T35/T37/T38/T40/T41、§35.2 Q04-A/Q04-B/Q07-A/Q10-A/Q10-B、§35.3 D01/D02）；docs/features/F010/product.md（A1–A26、I-1–I-10）；docs/api/F007.md v1、docs/database/f007-interface.md v1；docs/api/F008.md v1、docs/database/f008-network.md v1（DB-D80–D94）；docs/api/F009.md v1、docs/database/f009-ip-pool.md v1（DB-D95–D110）；docs/features/F009/architecture.md（DR-102–DR-117）；docs/features/F009/review-report.md（F009-CON-01/02）；docs/architecture/d01-conventions.md v8；docs/api/F004.md v3、F003.md v2、F002.md §1.2/§1.2.1；plan_revision 4 F010

## 1. 方案摘要

### 1.1 IPAddress 实体（独立表，PK=UUID）
IPAddress 是独立可寻址对象（§21 软删清单含 IPAddress；自身 UUID/version/软删/恢复/Activity），非 Interface 或 Network 的 1:1 明细，故 PK 为自身 UUID。`network_id` 与**冗余 `cluster_id`** 为普通 FK（RESTRICT），分别支撑 CIDR 归属与「同 Cluster 未删地址唯一」。IPAddress 是 Endpoint（F012）的引用目标与 §20 容量口径的占用来源。

| 字段 | 类型 | 空 | 默认 | 语义 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | gen_random_uuid() | PK pk_ip_addresses |
| network_id | UUID | 否 | — | FK→networks(id) ON DELETE RESTRICT；创建必填；引用须存在未软删；创建后不可改（DR-120） |
| cluster_id | UUID | 否 | — | **冗余** FK→clusters(id) ON DELETE RESTRICT；创建时取自锁定 Network 的 cluster；不可改；同 Cluster 唯一载体（I-1/DR-119） |
| address | inet | 否 | — | 单个 IPv4 主机地址（family=4、masklen=32）；属 Network CIDR；创建必填；创建后不可改（DR-120） |
| interface_id | UUID | 是 | null | FK→interfaces(id) ON DELETE RESTRICT；可空=占用未绑定；非空须 Resource.cluster==ip.cluster；绑定/解绑/转移可变（DR-121） |
| ip_pool_id | UUID | 是 | null | FK→ip_pools(id) ON DELETE RESTRICT；分配来源历史；自动=指定池、手动=地址所属未删池或 null；创建后不可改（DR-122） |
| description | text | 是 | null | 描述性自由文本，无长度上限 |
| version | integer | 否 | 1 | 乐观锁 CHECK ≥1 |
| created_at/updated_at | timestamptz | 否 | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | 是 | null | 软删（释放） |

省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；PATCH 省略=保持（exclude_unset）；显式 null 仅清空 nullable（interface/description）；必填/非 nullable（network/address）显式 null→422；不可变/只读字段→422；未知字段→422。不落字段：metadata（I-3）、name/status。

### 1.2 关系
- IPAddress 多对一 Network（`network_id`）；多对一 Cluster（`cluster_id`，冗余，恒等于 Network.cluster）。
- IPAddress 多对一（可空）Interface；绑定/转移时须 `Interface.Resource.cluster == IPAddress.cluster`。
- IPAddress 多对一（可空）IPPool（分配来源历史，§12/§21 例外：Pool 删除/缩小不回收）。
- Endpoint（F012）多对一 IPAddress；解绑/转移/释放前须先处理。
- 一个 Interface 可多 IP；一个 Resource 可多 Interface；未绑定 IP 仍占用（§13）。

## 2. Domain / Data Impact

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| IPAddress | 多对一 Network/Cluster；多对一(可空) Interface；多对一(可空) IPPool；被 Endpoint 引用 | 地址唯一=同 Cluster | 创建(自动/手动)/绑定/解绑/转移/软删(释放)/恢复 | §13/§14/§21 | network/address 不可改（DR-120） |
| 同 Cluster 未删地址唯一 | 未删 IP 整个 Cluster 唯一（含未绑定、跨 Network/Pool） | Cluster | 创建/恢复重检 | §13.3/§14/§27 | 冗余 `cluster_id` + 部分唯一（DR-119） |
| 绑定一致性 | IP→Interface 时 Resource.cluster==Network.cluster | Cluster | 绑定/转移重检 | §14/§10 | 应用主校验 + 触发 backstop（DR-121） |
| 自动分配 | ACTIVE Network + auto_allocate + AUTO 池；升序；耗尽不切换 | Network/Pool | 请求期 | §13.1/§11 | `_lock_network`+升序+唯一（DR-126） |
| 手动分配 | 池内/池外；禁 gateway/RESERVED/禁用/网络广播 | Network | 请求期 | §13.2/§11.1 | 可分配集合校验（DR-124） |
| 解绑/转移/释放 | 解绑不释放；释放=软删（ADMIN）；Endpoint 引用先处理 | IPAddress | 关系变更/软删 | §13.3/§16/§23 | 引用检查器挂钩（DR-127） |
| IPPool↔IPAddress | IP 记录保留来源；池软删/缩小不回收 | 同 Network | — | §12/§21 | `ip_pool_id` FK RESTRICT；来源历史（DR-122） |
| 引用检查 | Network/Interface←未删 IP 阻止删除/改 cidr/cluster；IPPool 例外 | Cluster/Network | 删除/改 CIDR/cluster 前 | §21/§11 | 引用检查器（DR-127） |
| 容量 | §20 Network 与 AUTO 池口径 | 随 Network/Pool | 查询期 | §20 | 容量数据接口供 F013（DR-130） |

**数据完整性对应表**（引用 `.pi/skills/data-integrity/SKILL.md`，精简；Database/Backend/Tester 补保证与证据）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §14/§27 同 Cluster 未删 IP 唯一 | 手动/自动分配/恢复 | 部分唯一 `(cluster_id,address) WHERE deleted_at IS NULL`（DR-119） | 409 `unique_conflict{field:"address"}` | 索引仲裁；软删释放；恢复重检 | V-DB-TBD（F010） |
| §13.1/§27 自动分配不重复、升序 | 自动分配 | 唯一兜底 + 行锁 | `_lock_network`+升序选择；耗尽不切换 | T07 双会话；T35 与保留/网关互斥 | V-DB-TBD/F010 |
| §11.1/§13.2/§14 属 CIDR、非 gateway/RESERVED/禁用/网络广播 | 手动分配 | CIDR 触发 backstop（DR-120）；gateway/RESERVED 为跨表应用主校验 | 422 field="address" | — | V-DB-TBD |
| §14 绑定 Cluster 一致 | 绑定/转移 | 触发 backstop（DR-121） | 422 field="interface" | — | V-DB-TBD |
| §13.3/§16 Endpoint 引用 | 解绑/转移/释放 | — | 引用检查器→409 `reference_exists` | F012 注册挂钩 | F010 桩 + F012 端到端 |
| §12.1/§11.1 保留范围/网关 vs 并发分配 | 池/gateway 变更 + 分配 | 无（跨表） | 共享 `_lock_network`+`IpAddressOccupancyProvider` | T35 双会话 | F010 端到端 |
| §11.1/§21/§27 软删/恢复 | 释放/恢复 | `deleted_at`+部分唯一 | 恢复重检唯一/依赖/CIDR/可分配边界（gateway/RESERVED/禁用），不覆盖 | 不级联 | V-DB-TBD |
| §23 乐观锁 | PATCH/释放/恢复 | version + 条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-TBD |

## 3. Frontend / Backend Work

**Backend（`layers.backend=true`）**
- `app/models/ip_address.py`：ORM 映射（inet、可空 FK、部分唯一索引）。
- `app/schemas/ip_address.py`：POST（手动）/PATCH/自动分配/响应 schema；exclude_unset；点路径 422。
- `app/services/ip_address.py`：手动分配（可分配集合校验）、自动分配（升序选择）、绑定/解绑/转移、释放、恢复、软删过滤、乐观锁、Activity、审计。
- **共享锁**：复用 `_lock_network`（DB-D90/DB-D93）；手动/自动分配与恢复事务内先取锁。
- **占用提供者真实实现**：`app/services/ip_occupancy.py` 注册 `IpAddressOccupancyProvider`（shape 同 F009 DR-109），替换 F009 `NullIpOccupancyProvider`；使 F009/F008 的 RESERVED/网关占用检查真实生效。
- **引用检查器注册**：F010 注册 Network 引用集 `ip_address`、Interface 引用集 `ip_address`；IPPool 来源不注册（§21 例外）。
- **Endpoint 挂钩（预留）**：`app/services/ip_address_reference.py` 提供 `register_ip_address_reference_checker(...)`；F010 默认空集；F012 注册真实 Endpoint 检查器。
- **容量服务**：`app/services/ip_capacity.py`（`IpCapacityProvider.network_capacity`）实现 §20；供容量端点与 F013。
- **审计白名单**：`ip_address` 快照 `{network_id,cluster_id,address,interface_id,ip_pool_id,description}`；`object_type="ip_address"`；CREATE/UPDATE/DELETE/RESTORE 同事务。
- `app/api/v1/ip_addresses.py` + router；容量端点 `networks/{id}/capacity`；迁移 `0010_ip_addresses`。

**Frontend（`layers.frontend=true`）**
- Networks / IPAM 区域内 IP 列表与详情；列表过滤（network/cluster/interface/pool/bound/address/deleted）、排序、分页。
- 手动分配表单；自动分配动作（选 Network + AUTO 池）。
- 绑定/解绑/转移控件；释放（ADMIN，二次确认）；恢复（ADMIN）；Activity。
- 409 冲突呈现：`unique_conflict`/`reference_exists`/`allocation_not_allowed`/`no_available_address` 与未知 reason 通用呈现。
- **容量显示归 F013**（本 Feature 不建 Dashboard 页面）。

**Database（`layers.database=true`，由 Database 承担）**：见 §7 与 `docs/database/f010-ip-address.md`。

## 4. API 裁定与 Contract 要点
裁定（DR-129）：新建独立端点 `/api/v1/ip-addresses` + 独立 Contract `docs/api/F010.md`；容量数据端点 `GET /api/v1/networks/{id}/capacity` 归本 Contract（供 F013）。

端点（9）：`GET/POST /api/v1/ip-addresses`；`POST /api/v1/ip-addresses/auto-allocate`；`GET/PATCH/DELETE /api/v1/ip-addresses/{id}`；`POST /api/v1/ip-addresses/{id}/restore`；`GET /api/v1/ip-addresses/{id}/activity`；`GET /api/v1/networks/{id}/capacity`。

响应 IPAddress：id、network{id,name,cidr}、cluster{id,code,name}、address、interface{id,name,resource{id,hostname}}|null、ip_pool{id,name}|null、description|null、version、created_at/updated_at、deleted_at。列表 {items,page,page_size,total}。不含 metadata。

错误码：新增 CONFLICT reason `allocation_not_allowed`（condition:`network_inactive`/`auto_allocate_disabled`/`pool_not_auto`）、`no_available_address`；复用 `unique_conflict{field:"address"}`、`reference_exists`、`dependency_deleted`、`not_deleted`、`address_in_use`；登记 F002 §1.2.1。

审计白名单：`{network_id,cluster_id,address,interface_id,ip_pool_id,description}`；`object_type="ip_address"`。

## 5. 同 Cluster 唯一、地址边界与不可变（I-1/I-4，DR-119/DR-120）
### 5.1 同 Cluster 未删唯一（I-1）
冗余 `cluster_id`（创建时取自锁定 Network 的 cluster）+ 部分唯一 `UNIQUE(cluster_id,address) WHERE deleted_at IS NULL`。理由：唯一作用域是 Cluster、跨 Network/Pool，`network_id` 无法表达；PG 唯一索引不能跨表取 `networks.cluster_id`；备选 `UNIQUE(network_id,address)` 不满足 §14，纯触发器有并发窗口且 §27 要求 PostgreSQL 兜底。一致性：`cluster_id` 恒等于 `networks.cluster_id`；创建先取 `_lock_network`；有未删 IP 时 Network 不可改 cluster（引用检查器）；DB BEFORE 触发 backstop（`FOR KEY SHARE`，同 F009 模式）。软删释放索引项；恢复重检冲突 409 `unique_conflict{field:"address"}`，不覆盖新占用。
### 5.2 地址边界与 CIDR 归属（DR-120）
`address` 属 Network CIDR（应用主校验 + 触发 backstop）；/0–/30 排网络/广播、/31 两址可用、/32 唯一地址；禁用 5 段不得分配或作 gateway；自动、手动、恢复、容量共用同一可分配集合（基础可用地址 − gateway − RESERVED 池范围 − 禁用地址，§11.1/§20）。恢复重检必须与手动分配（DR-124）复用同一集合：除唯一与 CIDR 外，还需重检 gateway/RESERVED/禁用排除，命中 → 422 `field:"address"`；该对齐由 §11.1 CONFIRMED「恢复与容量统计共用这一边界」与 §31 T34 产生（F010-REV-01 订正）。
### 5.3 network/address 不可变（I-4）
创建必填、创建后不可改（PATCH 含 network/address→422）；改地址=新建；改 Network 会破坏 CIDR 归属与 Cluster 唯一。

## 6. 分配、并发与引用（I-2/I-5/I-6/I-9）
### 6.1 手动分配（DR-124）
须属 ACTIVE Network、属 CIDR、非网络/广播、非禁用、非 gateway、不在 RESERVED 池范围；AUTO/MANUAL 池内或池外允许；auto_allocate 不参与手动校验。`ip_pool_id` 服务端推导（地址所属未删池，否则 null）。占用→409 `unique_conflict{field:"address"}`；INACTIVE→409 `allocation_not_allowed{condition:"network_inactive"}`。
### 6.2 自动分配（DR-125/DR-126）
条件：Network ACTIVE + auto_allocate=true + 指定池存在、属该 Network、`allocation_mode=AUTO`、未软删；否则 409 `allocation_not_allowed`，不降级为手动。算法：事务内先取 `_lock_network`，在指定池范围 ∩ Network 可分配集合内按地址升序选第一个未占用地址；池耗尽→409 `no_available_address`，不切换。并发：共享 `_lock_network` 串行化同 Network 分配与 F009/F008 变更；部分唯一为跨 Network/Cluster 兜底。
### 6.3 绑定/解绑/转移与释放（DR-121/DR-128）
绑定/转移=改 `interface`（PATCH）；interface 非空须存在、未软删、`Resource.cluster == ip.cluster`，否则 422 field="interface"；解绑=interface 显式 null，仅移除关系、IP 继续占用。释放=软删（DELETE，RELEASE_IP/ADMIN）。解绑/转移/释放前调用 IP 引用检查器；失败→409 `reference_exists`。
### 6.4 INACTIVE 下关系编辑（I-5，DR-136）
绑定/解绑/转移属关系编辑，不受 INACTIVE 限制；仅新建 IP 要求 ACTIVE；恢复不要求 ACTIVE（仍重检完整性）。
### 6.5 分配来源（I-6，DR-122）
自动=`指定 AUTO 池`；手动=地址所属未删池或 null；创建后不可改；Pool 删除/缩小不回收、不改来源。
### 6.6 分配与绑定分离（I-9，DR-137）
POST 仅分配、创建未绑定 IP（POST 体出现 interface→422）；绑定是独立 PATCH。

## 7. 引用检查、跨 Feature 与容量（I-7/I-10，DR-127/DR-130/DR-135）
### 7.1 引用检查器（DR-127）
- Network←未删 IPAddress（F010 注册）：Network 删除/改 cidr/cluster 被阻→409 `reference_exists`。
- Interface←未删 IPAddress（F010 注册）：删除 Interface 被阻→409 `reference_exists`。
- IPPool 来源例外：不注册、不阻止、不回收。
- Endpoint←IPAddress：F010 提供注册函数（默认空集）；F012 注册真实检查器；解绑/转移/释放前调用。
- DB 侧 FK 均 ON DELETE RESTRICT（物理删兜底）；软删引用保护由应用检查器承担。
### 7.2 真实占用提供者
F010 实现 `IpAddressOccupancyProvider` 注册到 F009 注册表；供 F009 Pool 与 F008 gateway 检查消费；命中→409 `address_in_use`（形状同 F009 DR-110）。使 F009-CON-01 的 F008 gateway 路径真实可达。
### 7.3 容量（DR-130）
`GET /api/v1/networks/{id}/capacity` 与内部 `IpCapacityProvider` 实现 §20：
- 可分配集合 = 基础可用地址 − gateway − RESERVED 池范围 − 禁用地址（去重）。
- Network：`allocatable_total`、`occupied`（未删 IP 计数，含未绑定、含池外手动）、`remaining = total − occupied`。
- 每 AUTO 池：`allocatable_total=|池范围 ∩ 可分配集合|`；`occupied=当前位于该交集的未删 IP 数`（按地址不按来源）；`remaining`。
- 停用不清零。NOTE：`remaining` 直接相减，存量 IP 落入现已保留范围时可能为负，是否下限 0 待 CONTRACT 裁定。
### 7.4 F009-CON-01/02 与 F008 errata（I-10，DR-135）
F010 使 F008 gateway `address_in_use` 路径可达；`docs/api/F008.md` §1.2/§6.4/§7 错误集未含该 reason。订正建议：Architect 出 Contract errata 补入并交叉引用；是否本 Feature 一并改 F008/F003 Contract 由协调器裁定。F008-REV-01/02 Database errata 由协调器择机处理，不阻塞 F010。

## 8. D01 v8→v9 补齐（DR-133）
新增 §5.9 IPAddress 字段口径：address（单个 IPv4 主机地址，属 CIDR，非网络/广播/禁用/gateway/RESERVED）；interface（可空，非空须同 Cluster，可 PATCH）；ip_pool（可空来源，自动/手动口径）；network/address 不可改；description 可空无上限；不落 metadata；无 name/status。交 CONTRACT/D01 签核。

## 9. 验证策略（A1–A26，真实 PG）
- 唯一/Cluster：同 Cluster 重复→409 unique_conflict；不同 Cluster 同址允许（A14）；部分唯一双会话；软删重用；恢复重检不覆盖（A13/A22）。
- 手动分配：非法/越界/网络广播/禁用/gateway/RESERVED→422；池内/池外合法→201（A1–A4）。
- 自动分配：条件不满足→409 allocation_not_allowed；升序；耗尽→409 no_available_address 不切换；并发不重复（A5–A8/T07）。
- 占用/未绑定：未绑定占用、不再分配（A9）；解绑不释放（A10）。
- 绑定/转移：跨 Cluster→422（A11/A15）。
- 释放/恢复：仅 ADMIN；可重用；恢复重检唯一/依赖/CIDR/gateway/RESERVED 可分配边界（A12/A13/A16/A22/T30/T34）。
- 引用：未删 IP 阻止 Network/Interface 删除（A19）；Endpoint 引用阻止解绑/转移/释放（A18，F010 契约/空挂钩 + 桩，端到端 F012）。
- 并发：保留范围/网关变更 vs 分配互斥、事务不残留（A21/T35）。
- 容量：§20 集合公式、去重、未绑定计入、池外计入 Network、按当前地址、停用不清零（A23 计算；显示 F013）。
- API/D01：必填/省略/不可变/未知字段（A25）；乐观锁（A26）；权限/审计/Activity（A24）。
- 迁移：`0010_ip_addresses` up/down/up、单 head、无回填、约束/索引/触发断言。
- **F010 独立**：唯一/Cluster、手动/自动分配、边界/禁用、绑定/转移、释放/恢复、Network/Interface 引用、容量计算、T07/T35、T33/T34 真实占用部分。
- **留待 F012**：Endpoint 端到端 T22/T23；**留待 F013**：Dashboard 显示 T32。

## 10. 技术决策（DR-118–DR-139，接续 F009 DR-117）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-118 | IPAddress 独立表 PK=UUID；`network_id` FK→networks(id) ON DELETE RESTRICT；`cluster_id` 冗余 FK→clusters(id) RESTRICT | CONFIRMED+DESIGN |
| DR-119 | 同 Cluster 未删唯一 = 冗余 `cluster_id` + 部分唯一 `UNIQUE(cluster_id,address) WHERE deleted_at IS NULL`；一致性由 `_lock_network` + 触发 backstop；软删释放、恢复重检 | PROPOSED→CONTRACT/DATABASE（I-1） |
| DR-120 | `address` PG `inet` 主机地址（CHECK family=4、masklen=32）；属 Network CIDR；`network`/`address` 创建必填、创建后不可改 | PROPOSED→CONTRACT/DATABASE（I-4） |
| DR-121 | `interface_id` 可空 FK→interfaces(id) RESTRICT；非空须 `Resource.cluster == ip.cluster`；可 PATCH 变更 | CONFIRMED（§14）+DESIGN |
| DR-122 | `ip_pool_id` 可空 FK→ip_pools(id) RESTRICT；自动=指定 AUTO 池、手动=所属未删池或 null；创建后不可改；池删除/缩小不回收 | PROPOSED→CONTRACT（I-6） |
| DR-123 | 不落 metadata（I-3）；`description` text 可空无上限；无 name/status | PROPOSED→CONTRACT/D01（I-3） |
| DR-124 | 手动分配：属 ACTIVE Network、属 CIDR、非网络/广播/禁用/gateway/RESERVED；AUTO/MANUAL 池内或池外允许；越界/禁用→422；占用→409 unique_conflict | PROPOSED→CONTRACT |
| DR-125 | 自动分配：ACTIVE + auto_allocate + AUTO 池；不满足→409 `allocation_not_allowed{condition}`；升序；耗尽→409 `no_available_address`，不切换 | PROPOSED→CONTRACT |
| DR-126 | 并发：手动/自动分配与恢复事务内取 `_lock_network`；部分唯一兜底；与 F009/F008 变更互斥 | PROPOSED→CONTRACT/DATABASE（I-2/I-8） |
| DR-127 | 引用检查：注册 Network←未删 IP、Interface←未删 IP；IPPool 例外；预留 `Endpoint←IPAddress` 注册点 | CONFIRMED（§21/§16）+DESIGN |
| DR-128 | 释放=软删（RELEASE_IP/ADMIN）；解绑不释放；恢复仅自身、重检唯一/依赖（Network/Interface）/CIDR 包含/可分配边界（非 gateway、非 RESERVED、非禁用）；可分配边界与手动分配（DR-124）共用同一 §11.1 集合；失败不覆盖 | CONFIRMED（§13.3/§11.1/§21/§31 T34）+DESIGN |
| DR-129 | API 独立 `/api/v1/ip-addresses`（8 端点）+ 容量端点 `GET /api/v1/networks/{id}/capacity`；新建 `docs/api/F010.md` | PROPOSED→CONTRACT |
| DR-130 | §20 容量数据接口（`IpCapacityProvider`+端点）；显示归 F013；`remaining` 负值 NOTE 交 CONTRACT | CONFIRMED（§20）+DESIGN |
| DR-131 | 审计白名单 `{network_id,cluster_id,address,interface_id,ip_pool_id,description}`；`object_type="ip_address"`；四类 action 同事务 | CONFIRMED（§22）+DESIGN |
| DR-132 | 迁移 `0010_ip_addresses`（down_revision=`0009_ip_pools`）；全表新建无回填、对称可逆、单 head | DESIGN→DATABASE |
| DR-133 | D01 v8→v9 新增 §5.9 IPAddress 字段口径；§3/§5 同步 | PROPOSED→CONTRACT/D01（I-3/I-4/I-6） |
| DR-134 | D02 关闭项：`ip_addresses` 部分唯一/索引、`_lock_network` 复用、`IpAddressOccupancyProvider` 真实实现、T07/T35 方案；CONTRACT/DATABASE 签核 | PROPOSED→CONTRACT/DATABASE（I-8） |
| DR-135 | F009-CON-01 订正：F008 gateway 错误集补 `address_in_use{field:"gateway"}`；F009-CON-02 交叉引用订正；是否本 Feature 改 F008 Contract 由协调器裁定 | PROPOSED→协调器裁定（I-10） |
| DR-136 | Network INACTIVE 不限制绑定/解绑/转移；仅新建分配要求 ACTIVE；恢复不要求 ACTIVE | PROPOSED→CONTRACT（I-5） |
| DR-137 | 分配与绑定分离：POST 创建未绑定 IP（interface 出现→422）；绑定为独立 PATCH | PROPOSED→CONTRACT（I-9） |
| DR-138 | 注册真实 `IpAddressOccupancyProvider` 到 F009 注册表（替换空集） | CONFIRMED（DR-109/DR-110）+DESIGN |
| DR-139 | F010 提供 `register_ip_address_reference_checker` 挂钩（默认空集）；解绑/转移/释放前调用 | PROPOSED→CONTRACT（I-7） |

## 11. 裁定 I-1–I-10（PROPOSED→设计决定）
- **I-1（DR-119）**：采纳冗余 `cluster_id` + 部分唯一 `(cluster_id,address) WHERE deleted_at IS NULL`；替代方案已排除；软删释放、恢复重检不覆盖。交 Database 签核一致性触发与索引表达式。
- **I-2（DR-125/DR-126）**：共享 `_lock_network` + 部分唯一 + 升序；T07/T35；耗尽不切换。
- **I-3（DR-123）**：不落 metadata。
- **I-4（DR-120）**：network/address 创建必填、不可改。
- **I-5（DR-136）**：绑定/解绑/转移不受 INACTIVE 限制；仅新建分配要求 ACTIVE；恢复不要求。
- **I-6（DR-122）**：自动=指定池、手动=所属未删池或 null、不可改、池变更不影响。
- **I-7（DR-127/DR-130/DR-139）**：F010 交付引用检查器、Endpoint 挂钩、§20 容量数据接口。
- **I-8（DR-134）**：给出唯一/索引/锁/IPAM 并发方案供 D02 关闭。
- **I-9（DR-137）**：分配与绑定分离。
- **I-10（DR-135）**：F008 gateway `address_in_use` 订正建议，交协调器裁定。

## 12. 风险与待核对项
- **交 DATABASE**：`cluster_id` 冗余一致性触发 backstop 与不可变性；`address inet` 唯一索引表达式与 `masklen=32`；CIDR 包含触发 backstop；索引集合（建议 `uq_ip_addresses_cluster_id_address`、`ix_ip_addresses_network_id/_cluster_id/_interface_id/_ip_pool_id/_deleted_at`，无 pg_trgm）；迁移 `0010` up/down/up；恢复重检与约束交互；`IpAddressOccupancyProvider` 查询索引支撑。
- **交 TEST_DESIGN**：A1–A26 的 F010 独立判据与 F012/F013 分界；T07/T35 并发双会话；真实 PG 约束证据。
- **交 CONTRACT**：新 reason 登记 F002 §1.2.1；`remaining` 负值口径；D01 v9 §5.9；I-9 与 INACTIVE 恢复口径。
- **协调器裁定（I-10）**：F008/F003 Contract errata 与 F008 Database errata 是否在 F010 CONTRACT 一并订正。
- **跨 Feature**：F010 未复用 `_lock_network` 或未注册真实占用提供者则 T33/T35 无法闭合；F012 未注册 Endpoint 检查器则 T22/T23 端到端无法闭合（记录 ISSUES，非 DESIGN BLOCK）。
- **性能**：大范围池升序扫描用键集/整数区间扫描，避免 `generate_series` 全量展开。
- **负值容量**：存量 IP 落入现已保留范围时 `remaining` 可能为负（NOTE，交 CONTRACT）。

## 13. Layers 与分工
```yaml
layers:
  database: true
  backend: true
  frontend: true
api_required: true
```
- **Database**：`docs/database/f010-ip-address.md`（表/CHECK/部分唯一/索引/FK/触发 backstop/迁移 0010/真 PG 验证项）；裁定 DR-119/DR-120/DR-126/DR-132/DR-134。
- **Backend**：models/schemas/services `ip_address`；`services/ip_address.py`、`ip_capacity.py`、`ip_occupancy.py`（真实提供者）、`ip_address_reference.py`（挂钩）；注册 Network/Interface 引用检查器；`api/v1/ip_addresses.py`+router；容量端点；审计白名单；迁移 0010。
- **Frontend**：IPAM 内 IP 列表/详情/手动—自动分配/绑定—解绑—转移/释放/恢复/Activity；冲突呈现（容量显示归 F013）。
- **Contract**：`docs/api/F010.md` 置 READY；登记 `allocation_not_allowed`/`no_available_address` 至 F002 §1.2.1；签核 D01 v9 §5.9；固定 DR-119/121/122/124/125/129/130/131。

## 14. 结论与下一步
无 Blocking Questions；I-1…I-10 已裁定（PROPOSED→设计决定），不调整 Feature 顺序或范围。**Status：`READY FOR DESIGN`**。

下一步：
1. **DATABASE** 出 `docs/database/f010-ip-address.md`（部分唯一/触发 backstop/索引/迁移 0010/真 PG 验证），签核 DR-119/DR-120/DR-126/DR-132/DR-134。
2. **TEST_DESIGN** 依 §9 给判据（F010 独立 vs F012/F013）。
3. **CONTRACT** 定稿 `docs/api/F010.md`、登记 F002 §1.2.1、签核 D01 v9 §5.9 → `READY FOR IMPLEMENTATION`。
4. **协调器** 裁定 I-10 的 F008/F003 Contract errata。