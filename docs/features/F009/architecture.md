# F009 IP Pool 地址池 — ARCHITECTURE 阶段报告

- **Task**：F009（FEATURE，P0，M4 网络与 IPAM，deps [F008]）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-09）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12、§12.1、§14、§20、§21、§22、§23、§25、§26、§27、§28、§31 T15/T16/T17/T18/T23/T24/T25/T26/T30/T31/T32/T33/T34/T35/T37/T40/T41、§35.2 Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）；docs/features/F009/product.md（A1–A23、I-1–I-6）；docs/features/F008/architecture.md（DR-89–DR-101）；docs/api/F008.md v1；docs/database/f008-network.md v1（DB-D80–D94）；docs/features/F008/review-report.md（F008-REV-01/02/03）；docs/architecture/d01-conventions.md v7；docs/api/F004.md v3、F003.md v2、F002.md §1.2；plan_revision 4 F009
- **结论属性**：设计输入，交 DATABASE/TEST_DESIGN；Contract 草案供 CONTRACT 定稿（新建 docs/api/F009.md）。**不放行编码**。

## 1. 方案摘要

### 1.1 IPPool 实体（独立表，PK=UUID）
IPPool 是独立可寻址对象（§21 软删清单含 IPPool；自身 UUID/version/软删/恢复/Activity），非 Network 的 1:1 明细，故 PK 为自身 UUID，`network_id` 为普通 FK（RESTRICT）。IPPool 是 F010 IPAddress 分配来源与 F013 容量口径的地址范围输入。

| 字段 | 类型 | 空 | 默认 | 语义 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | gen_random_uuid() | PK pk_ip_pools |
| network_id | UUID | 否 | — | FK→networks(id) ON DELETE RESTRICT；创建必填；引用须存在未软删；创建后不可改（I-2/DR-107） |
| name | varchar(255) | 否 | — | trim→非空→禁 Cc/Cf；允许中文及内部普通空格、不合并；大小写不敏感；同 Network 未删唯一；删除后复用（DR-103） |
| name_key | varchar(255) | 否 | — | ASCII_lower(btrim(name))；部分唯一载体（DR-103） |
| start_address | inet | 否 | — | 单个 IPv4 主机地址（非 CIDR/掩码）；属该 Network CIDR；start ≤ end |
| end_address | inet | 否 | — | 同上；end ≥ start；起=止为单地址池 |
| address_range | int8range | 否 | 生成列 | int8range(start_address-'0.0.0.0'::inet, end_address-'0.0.0.0'::inet,'[]')；闭区间；排他约束载体（DR-106） |
| allocation_mode | varchar(16) | 否 | 'MANUAL' | MANUAL\|AUTO\|RESERVED；CHECK∈3 值（DR-105） |
| description | text | 是 | null | 描述性自由文本，无长度上限（I-4） |
| version | integer | 否 | 1 | 乐观锁 CHECK ≥1 |
| created_at/updated_at | timestamptz | 否 | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | 是 | null | 软删 |

省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；PATCH 省略=保持（exclude_unset）；显式 null 仅清空 nullable（description）；必填/非 nullable（network/name/start_address/end_address/allocation_mode）显式 null→422；不可变/只读字段→422。不落字段：metadata（I-6）、status、auto_allocate、IP 列表、容量数值（归 F010/F013）。

### 1.2 关系
IPPool 多对一依附 Network；1:N 分配来源（IPAddress，F010）。名称唯一与范围不重叠作用域均为同 Network；跨 Network CIDR 不重叠已由 F008 保证。Pool 向 F010 暴露范围与 allocation_mode，向 F013 暴露 AUTO 池范围供 §20 容量。

## 2. Domain / Data Impact

| 对象 | 关系 | 作用域 | 生命周期 | 依据 | 裁定 |
| --- | --- | --- | --- | --- | --- |
| IPPool | 多对一 Network；1:N 分配来源（F010） | 名称唯一=同 Network | 创建/改范围或模式（受限）/软删/恢复 | §12、§21 | network 不可改（DR-107） |
| 池范围互不重叠 | 同 Network 未删除池两两不重叠（含 RESERVED）；INACTIVE Network 的池参与 | Network | 创建/改起止/恢复重检 | §12/§27 | 闭区间 `int8range` 排他约束（DR-106） |
| name 唯一 | 同 Network 未删除，大小写不敏感 | Network | 软删后可复用；恢复重检 | §4.1/§21/Q10-B | name 1–255，ASCII 折叠（DR-103/D01 §5.8） |
| allocation_mode | MANUAL/AUTO/RESERVED 决定地址可否分配 | 本 Pool | 改模式受 §12.1 约束 | §12/§12.1 | 分配执行在 F010；F009 保存并暴露 |
| IPPool↔IPAddress | IP 记录引用分配来源 Pool | 同 Network | Pool 删除/缩小不回收 IP；来源历史保留 | §12/§21 | Pool 软删不阻止、不回收；FK RESTRICT 仅物理删（DR-108） |
| RESERVED / gateway 占用冲突 | 变更后范围内存在未删除 IP（含未绑定 Interface）时拒绝 | 本 Network | 新建/扩大 RESERVED、改为 RESERVED、设 gateway | §11.1/§12.1 | 占用提供者注册表 + Network 行锁（DR-109） |
| gateway | 属 CIDR 基础可用、非禁用、排除可分配 | 本 Network | Network PATCH 时重检占用 | §11/§11.1 | F009 提供 gateway 占用检查挂钩（DR-109/DR-110） |
| 展示/容量 | §20 Network 与 AUTO 池容量口径；列表 | 随 Network | — | §20/§28 | 容量数值 F010/F013；F009 不返回 |

**数据完整性对应表**（引用 `.pi/skills/data-integrity/SKILL.md`，精简；Database/Backend/Tester 分别补保证与证据）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §4.1/§27/DR-103 Pool 名称同 Network 未删唯一 | POST/PATCH/restore | 部分唯一 (network_id,name_key) WHERE deleted_at IS NULL；name_key CHECK | trim；折叠；409 unique_conflict{name} | 索引仲裁；软删释放；恢复冲突拒 | V-DB-TBD（F009） |
| §4.1/T40 名称规范 | POST/PATCH | ck_*（ASCII backstop） | trim→非空→禁 Cc/Cf→1–255；内部空格保留 | Cc/Cf 应用责任 | 同上 |
| §12/§27 池范围同 Network 不重叠 | POST/PATCH/restore | EXCLUDE USING gist (network_id=, address_range &&) WHERE deleted_at IS NULL | 先查冲突→409 range_overlap+conflicts | 约束原子兜底；软删排除；恢复重检 | V-DB-TBD |
| §12/§14 起止属 Network CIDR | POST/PATCH | FK 仅保证 Network 存在；CIDR 包含为跨表规则（应用 + 触发 backstop 待 Database 裁定） | 应用校验→422 | — | V-DB-TBD |
| §12 起 ≤ 止 | POST/PATCH | CHECK start ≤ end（同 row） | 应用 422 | — | V-DB-TBD |
| §12.1/T33 占用冲突 | POST/PATCH(Network gateway) | 无（IP 数据在 F010） | 占用提供者注册表；409 address_in_use+数量+明细 | Network 行锁串行化；F010 真实占用 | F009 stub + F010 端到端 |
| §21/§27 软删/恢复/来源例外 | DELETE/restore | deleted_at；排他/部分唯一致；FK RESTRICT | 恢复重检 name/network/overlap/(RESERVED)占用；Pool 删除不做 IP 引用检查 | 不级联；不回收 | V-DB-TBD |

## 3. Frontend / Backend Work

**Backend（`layers.backend=true`）**
- `app/models/ip_pool.py`：ORM 映射（含生成列 `address_range`，ORM 侧只读；`name_key` 应用生成）。
- `app/schemas/ip_pool.py`：POST/PATCH/响应 schema；exclude_unset；点路径 422。
- `app/services/ip_pool.py`：name_key 归一化（逐码位 ASCII 折叠）、起止格式/CIDR 包含/start≤end 校验、范围重叠映射 `range_overlap`、占用检查映射 `address_in_use`、软删过滤、`_lock_network` 调用、乐观锁、Activity。
- **注册引用检查器**：`cluster_service.register_reference_checker("network", _undeleted_ip_pool_references)`（未删 Pool 阻止 Network 删除/改 cidr/cluster → `references:[{object_type:"ip_pool",object_id,label}]`）；扩充 F008 预留点 `network._undeleted_network_child_references`。
- **占用提供者注册表（新）**：`app/services/ip_occupancy.py`，注册 `NullIpOccupancyProvider`（返回空集，F009 默认）；F010 注册真实 `IpAddressOccupancyProvider`。
- **Network gateway 占用挂钩**：`network.update_network` 在 gateway 变更且非空时，先 `_lock_network` 再调用 occupancy provider；占用→409 `address_in_use{field:"gateway"}`（F009 空集不触发，F010 端到端）。
- **审计白名单**：`ip_pool` 快照 `{network_id,name,start_address,end_address,allocation_mode,description}`；`object_type="ip_pool"`；CREATE/UPDATE/DELETE/RESTORE 同事务。
- `app/api/v1/ip_pools.py` + router 挂载；迁移 `0009_ip_pools`（down_revision=`0008_networks`）。

**Frontend（`layers.frontend=true`）**
- Networks / IPAM 区域内的 Pool 子列表与详情（F013 聚合消费）。
- Pool 创建/编辑表单：Network 选择器（不可改）、起止 IPv4、allocation_mode 选择器、description；422 点路径展示。
- 409 冲突呈现：`range_overlap` 明细致命池；`address_in_use` 冲突数量与明细预览。
- 已删开关与 ADMIN 恢复入口。

**Database（`layers.database=true`，由 Database 承担）**：见 §6 与 `docs/database/f009-ip-pool.md`。

## 4. API 裁定与 Contract 要点
裁定（DR-111）：新建独立端点 `/api/v1/ip-pools` + 独立 Contract `docs/api/F009.md`；不并入 F008 Network 嵌套。理由：§25 明确该路径；IPPool 自身 ID/version/软删/恢复/Activity，可独立寻址；归属经 network_id 关联。

7 端点：`GET/POST /api/v1/ip-pools`；`GET/PATCH/DELETE /api/v1/ip-pools/{id}`；`POST /api/v1/ip-pools/{id}/restore`；`GET /api/v1/ip-pools/{id}/activity`。响应 IPPool：id、network{id,name,cidr}、name、start_address、end_address、allocation_mode、description|null、version、created_at/updated_at、deleted_at。列表 {items,page,page_size,total}。

过滤/排序：network_id、allocation_mode、q（name 大小写不敏感子串）、deleted∈{exclude,include,only} 默认 exclude；page/page_size/sort∈{name,start_address,end_address,allocation_mode,created_at,updated_at}/order。

错误码：复用 F002/F003/F008；新增 reason `address_in_use`（注册 F002 §1.2）；复用 `range_overlap`（object_type ip_pool）、`unique_conflict`、`not_deleted`、`dependency_deleted`。校验顺序见 Contract §6。

审计白名单：{network_id,name,start_address,end_address,allocation_mode,description}；object_type="ip_pool"；CREATE/UPDATE/DELETE/RESTORE 同事务。

Contract 状态：草案 `BLOCKED`→目标 `READY`；D01 v8 §5.8、`address_in_use`、`range_overlap` 复用登记待 CONTRACT 签核，待 Database 出 `f009-ip-pool.md`。前后端以同一份 `docs/api/F009.md` 为准。

## 5. 范围不重叠、名称唯一与变更限制
### 5.1 范围不重叠（I-1，DR-106）
表示：start/end 为 PG inet；闭区间 int8range 生成列（或不可变表达式）。约束：`EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)`。`network_id WITH =` 需 btree_gist（F008 0008 已启用）。软删由谓词排除；INACTIVE Network 的池参与；恢复置 null 重新受约束，重叠→409 range_overlap。并发由约束原子兜底。
### 5.2 名称唯一（I-4，DR-103）
name_key=ASCII_lower(btrim(name))：仅 ASCII A-Z→a-z，非 ASCII 原样，locale 无关（D01 §5.1/§5.3/§5.8）。部分唯一 UNIQUE(network_id,name_key) WHERE deleted_at IS NULL。内部普通空格允许且不合并。长度 1–255。
### 5.3 network 不可改与来源例外（I-2/DR-107、DR-108）
创建必填、创建后不可改（PATCH 含 network→422）。Pool 删除/缩小不回收 IP、不级联；分配来源引用保留（F010 ip_pool_id FK RESTRICT）；Pool 删除引用集为空。
### 5.4 CIDR 包含与起≤止（DR-104）
起止均属 Network CIDR（应用主校验 + 待裁定的 DB 触发 backstop）；CHECK start≤end；family=4。

## 6. 占用冲突与跨 Feature 落点（I-5，DR-109/110）
- 接口：`IpOccupancyProvider`（`occupancy(session, network_id, start, end, limit) -> {total, items}`）。
- 注册表：F009 注册 `NullIpOccupancyProvider`（空集）；F010 注册真实 IPAddress 提供者。
- 冲突返回：409 `address_in_use{field, conflict_count, conflicts:[{object_type:"ip_address",object_id,address,bound,interface_id,resource_id,resource_hostname}], conflicts_truncated}`；含未绑定（bound=false）。完整明细由 F010 `GET /api/v1/ip-addresses` 范围过滤分页。
- 锁域：`_lock_network`（networks 行 FOR UPDATE）复用于 RESERVED/范围/gateway 变更与 F010 分配。
- Network gateway 占用挂钩：`network.update_network` gateway 变更且非空时先锁后查；占用→409 address_in_use{field:"gateway"}。
- F009 独立验证（桩）：A10–A12/A22 结构与数量、并发互斥；F010 端到端：A10–A12/A14/A22/T33/T34/T35、容量 T32。

## 7. 数据库影响（交 DATABASE）
表 ip_pools：id UUID PK pk_ip_pools；network_id NOT NULL FK fk_ip_pools_network_id_networks ON DELETE RESTRICT + ix_ip_pools_network_id；name varchar(255) NOT NULL + ck trim/非空/ASCII 控制 backstop/长度；name_key varchar(255) NOT NULL + ck translate 口径；start_address inet NOT NULL；end_address inet NOT NULL；address_range int8range 生成列 NOT NULL；allocation_mode varchar(16) NOT NULL DEFAULT 'MANUAL' + ck IN 3 值；description text NULL；version integer NOT NULL DEFAULT 1 CHECK≥1；created_at/updated_at；deleted_at。
约束/索引：EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)；uq_ip_pools_network_id_name_key UNIQUE(network_id,name_key) WHERE deleted_at IS NULL；ck start≤end、family=4；ix_ip_pools_network_id、ix_ip_pools_allocation_mode、ix_ip_pools_deleted_at；不建 pg_trgm GIN。
跨表 CIDR 包含：FK 仅保证 Network 存在，不含 CIDR 包含；应用主校验 + 触发 backstop（Database 裁定）。
迁移 0009_ip_pools，down_revision=0008_networks，单一 head；btree_gist 已由 0008 启用（可幂等再断言）；全表新建无回填，对称可逆（downgrade 逆序 drop，不 drop 扩展）；真库 up/down/up。
F009 注册 Network 引用检查器（未删 Pool 阻止 Network 删除/改 cidr/cluster），承接 DR-96。

## 8. D01 v7→v8 补齐（I-4，DR-113）
新增 §5.8 IPPool 字段口径（name 1–255 仅 ASCII 折叠、内部普通空格不合并；start/end 单主机 IPv4 属 CIDR 且起≤止；allocation_mode 默认 MANUAL 与取值；description text 无上限）；§3 追加地址字段引用；§5.2 追加 IPPool name 255；§5 表 IPPool 行措辞一致化（“允许内部普通空格（不自动合并）”）；§8 记 v8。交 CONTRACT/D01 签核。

## 9. 验证策略（A1–A23，真实 PG）
- 范围/格式：POST/PATCH 起止非 IPv4、越界、逆序 →422（A5/A6）；start=end 允许（A6）。
- 重叠：创建/改起止与未删池闭区间相交（含完全相同、共享端点）→409 `range_overlap{field,conflicts:[ip_pool]}`（A7）；软删释放范围；恢复重检（A15/A16）；排他约束并发双会话兜底（A20）。
- 名称：trim/空/控制字符→422；中文与内部普通空格保留不合并（A1）；同 Network 大小写不敏感重名→409 `unique_conflict{name}`；跨 Network 允许（A2）；软删复用/存活同名失败/恢复不覆盖（A3/A16）；name_key 归一化 API/DB 一致（A21）。
- 必填/引用：缺 network/name/start/end→422；network 不存在/已软删→422（A4）。
- allocation_mode：省略→MANUAL；非法/null→422；保存并暴露（A8/A9）。
- 占用冲突：桩 provider 下 A10–A12/A22 结构与数量（含未绑定）；真实端到端留 F010。
- 不改 IP：AUTO↔MANUAL、RESERVED→AUTO/MANUAL 允许且不改已有 IP（A13）。
- 软删/恢复：删除/缩小不回收（结构层；真实 IP 端到端 F010）（A14/A15）；权限 A17；Audit A18；列表 A19；乐观锁 A23。
- 迁移：0009 up/down/up、单一 head、无回填、排他/部分唯一/CHECK/索引断言（A20）。
- **F009 独立**：A1–A9、A13、A15 范围/名称部分、A16–A21、A23；T15、T40、T41。
- **F009 + 桩 provider**：A10–A12、A22 的冲突结构与数量、并发互斥。
- **留待 F010/F009+F010 集成**：A10–A12/A14/A22/T33/T35/T34 真实 IP 占用端到端与容量 T32。

## 10. 技术决策（DR-102–DR-117，接续 F008 DR-101）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-102 | IPPool 独立表 PK=UUID；`network_id` FK→networks(id) ON DELETE RESTRICT | CONFIRMED+DESIGN |
| DR-103 | name varchar(255) trim/非空/禁 Cc/Cf、允许内部普通空格不合并、大小写不敏感；`name_key=ASCII_lower(btrim(name))`；部分唯一 `(network_id,name_key) WHERE deleted_at IS NULL` | PROPOSED→CONTRACT(1–255)/D01 §5.8 |
| DR-104 | start_address/end_address 用 PG `inet`（单主机地址）；CHECK `start<=end`；均属 Network CIDR（应用主校验，DB 触发 backstop 待 Database 裁定）；CHECK `family()=4` | PROPOSED→DATABASE |
| DR-105 | allocation_mode varchar(16) NOT NULL DEFAULT 'MANUAL' CHECK∈{MANUAL,AUTO,RESERVED} | CONFIRMED+DESIGN |
| DR-106 | 范围不重叠 = `EXCLUDE USING gist (network_id WITH =, address_range WITH &&) WHERE (deleted_at IS NULL)`；`address_range` 为 `int8range(...,'[]')`（生成列或不可变表达式）；闭区间；软删排除；恢复重检；btree_gist 已由 F008 0008 启用 | PROPOSED→DATABASE（I-1） |
| DR-107 | `network_id` 创建后不可改（PATCH 含 network/network_id→422），采纳 I-2 PROPOSED | PROPOSED→CONTRACT（I-2） |
| DR-108 | Pool 软删不做 IP 分配来源引用检查、不级联、不回收 IP；来源引用历史保留（F010 持 `ip_pool_id` FK RESTRICT，软删后仍有效） | CONFIRMED（§12/§21）+DESIGN |
| DR-109 | 占用检查接口与锁域：`IpOccupancyProvider` 注册表（F009 注册空集 `NullIpOccupancyProvider`，F010 注册真实提供者）；RESERVED/范围/gateway 变更与 IP 分配共用 `_lock_network`（networks 行 FOR UPDATE） | PROPOSED→CONTRACT/DATABASE（I-5） |
| DR-110 | 新增 CONFLICT reason `address_in_use`（注册 F002 §1.2）：`field`∈{start_address,end_address,allocation_mode,gateway}；`conflict_count`+`conflicts`（含未绑定）；网关占用同 reason | PROPOSED→CONTRACT（I-5） |
| DR-111 | API 独立 `/api/v1/ip-pools` + 新建 `docs/api/F009.md`；7 端点（列表/详情/创建/更新/删除/恢复/activity） | PROPOSED→CONTRACT |
| DR-112 | 软删/恢复；恢复重检名称唯一、Network 有效（未软删）、范围不重叠、RESERVED 另检占用；失败不覆盖新对象 | CONFIRMED（§21）+DESIGN |
| DR-113 | D01 v7→v8 新增 §5.8 IPPool 字段口径；§5 表 IPPool 行措辞一致化；§3/§5.2 同步 | PROPOSED→CONTRACT/D01（I-4） |
| DR-114 | 迁移 `0009_ip_pools`（down_revision=`0008_networks`）；首次引入 IPPool；不重复启用扩展；对称可逆、单一 head、无回填 | DESIGN→DATABASE |
| DR-115 | 审计白名单 `{network_id,name,start_address,end_address,allocation_mode,description}`；`object_type="ip_pool"` | CONFIRMED（§22）+DESIGN |
| DR-116 | F009 注册 Network 引用检查器（未删 Pool 阻止 Network 删除/改 cidr/cluster）；Pool 自身删除引用集为空（§21 例外） | CONFIRMED（§21/DR-96 承接）+DESIGN |
| DR-117 | I-3：不新增建池范围限制（仅属 CIDR 与起≤止）；禁用/网络/广播/gateway 在 §11.1/§20 可分配集合与 F010 分配中排除；收紧属新业务限定，本 Feature 不实现，记录待用户裁定 | PROPOSED（记录） |

## 11. 裁定 I-1–I-6（PROPOSED→设计决定）
- **I-1（DR-104/106/108）**：推荐生成列 `address_range int8range` + 排他约束；拒绝对 `inet` 直接 `&&`（无区间重叠语义）；闭区间含共享端点冲突；软删仅由谓词排除；INACTIVE 参与；恢复重检。来源保留：F010 `ip_addresses.ip_pool_id` FK RESTRICT；pool 软删保行；删池不检查 IP 引用、不回收。交 Database 签核不可变性与跨表 CIDR backstop。
- **I-2（DR-107）**：采纳 network 不可改（镜像 Resource.cluster）。
- **I-3（DR-117）**：采纳不新增建池范围限制；收紧属新业务限定，记录待用户裁定，不实现。
- **I-4（DR-113）**：见 §8 D01 v8 草案。
- **I-5（DR-109/110，关键）**：F009 交付占用接口/注册表（空集）、冲突返回结构、`_lock_network` 锁域、gateway 占用挂钩；F009 用桩验证结构与并发互斥，真实 IP 占用端到端留 F010。不认为需要调整 Feature 顺序或范围，故非 `DESIGN BLOCKED`。
- **I-6**：采纳 Pool 无 metadata，请求含 metadata→422，响应不含。

## 12. 风险与待核对项
- **交 DATABASE**：`int8range` 排他约束的表达式/生成列选择与 `inet - inet` 不可变性；跨表 CIDR 包含是否加触发 backstop（§27）；部分唯一/CHECK/索引集合；0009 up/down/up；恢复重检与约束交互。
- **交 TEST_DESIGN**：A10–A12/A22/T33/T35 的桩 provider 判据与 F010 端到端分界；并发双会话（重叠插入、保留范围/gateway 变更 vs 分配）。
- **交 CONTRACT**：新 reason `address_in_use` 的 `field` 映射与 details 形状；`range_overlap` 复用登记（F008-REV-03 顺带闭合 F002/F003 §1.2）；`address_in_use` 明细预览上限 `CONFLICT_PREVIEW_LIMIT`（建议默认 100）与 `conflicts_truncated`；D01 v8 §5.8 签核。
- **跨 Feature（I-5）**：F009 交付接口/锁域/结构，F010 落地真实占用查询与端到端；F010 须复用 `_lock_network` 并注册 provider。若 F010 未按此协议落地，T33/T35 端到端将无法在 F009 闭合（记录 ISSUES，非本 Feature DESIGN BLOCK）。
- **F008 承接**：F008-REV-01（gateway CHECK 示例 SQL 与 DB-D83 措辞订正）影响 gateway 语义复用；F008-REV-03（range_overlap 注册）本 Feature 可顺带闭合。

## 13. Layers 与分工
```yaml
layers:
  database: true
  backend: true
  frontend: true
api_required: true
```
- Database：docs/database/f009-ip-pool.md（表/CHECK/部分唯一/排他约束/生成列/索引/FK/触发裁定/迁移 0009）；裁定 I-1/I-5 落地；真 PG 验证项。
- Backend：models/ip_pool.py；schemas/ip_pool.py；services/ip_pool.py；services/ip_occupancy.py（注册表 + NullIpOccupancyProvider）；注册 Network 引用检查器；network.update_network gateway 占用挂钩；audit 白名单扩 ip_pool；api/v1/ip_pools.py+router；迁移 0009。
- Frontend：Networks/IPAM 区域 Pool 列表与详情；创建/编辑表单（network 不可改、起止 IPv4、allocation_mode、description、422 点路径）；range_overlap/address_in_use 冲突呈现；已删开关与 ADMIN 恢复。
- Contract：docs/api/F009.md 置 READY；签核 D01 v8 §5.8；固定 DR-103/106/110/111/113。

## 14. 结论与下一步
无 Blocking Questions，I-1…I-6 已给出技术方案与裁定（PROPOSED→设计决定），不调整 Feature 顺序或范围。**Status：`READY FOR DESIGN`**。

下一步：
1. **DATABASE** 出 `docs/database/f009-ip-pool.md`（排他约束/部分唯一/CHECK/触发裁定/迁移 0009/真 PG 验证），签核 DR-104/106/108/109/114。
2. **TEST_DESIGN** 依 §9 给判据（F009 独立 vs F010 端到端）。
3. **CONTRACT** 定稿 `docs/api/F009.md` 并签核 D01 v8 §5.8、`address_in_use`、`range_overlap` 复用 → `READY FOR IMPLEMENTATION`。

- **方案摘要**：独立 `ip_pools` 表 + 7 端点 `/api/v1/ip-pools`；`int8range` 排他约束保证同 Network 未删池闭区间不重叠；名称部分唯一；`network` 不可改；软删/恢复；占用提供者注册表 + Network 行锁承载 §12.1 冲突（F010 落地真实占用）。
- **Contract 引用与状态**：`docs/api/F009.md` 草案，目标 `READY`。
- **Implementation Layers**：database=true、backend=true、frontend=true、api_required=true。

GIT: NONE