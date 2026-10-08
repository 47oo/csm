# F008 Network 网络管理 — ARCHITECTURE 阶段报告

- **Task**：F008（FEATURE，P0，M4 网络与 IPAM，deps [F003]）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-09；协调器核验后持久化）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12.1、§13、§20、§21–§23、§25–§28、§31 T14/T16/T24/T25/T29/T30/T37/T38/T40/T41、§35.2 Q02-A/Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）；docs/features/F008/product.md（A1–A22、I-1–I-6）；docs/database/f001-baseline.md（DB-D2 btree_gist 推迟）；docs/database/f003-cluster.md v2；docs/api/F003.md、F004.md v3、F007.md v1；docs/architecture/d01-conventions.md v6；plan_revision 4 F008
- **结论属性**：设计输入，交 DATABASE/TEST_DESIGN；Contract 草案供 CONTRACT 定稿（新建 docs/api/F008.md）

## 1. 方案摘要

### 1.1 Network 实体（独立表，PK=UUID）
Network 是独立可寻址对象（§21 软删清单含 Network；自身 UUID/version/软删/恢复/Activity），非 Cluster 的 1:1 明细，故 PK 为自身 UUID，cluster_id 为普通 FK（RESTRICT）。Network 是 IPPool（F009）/IPAddress（F010）的父域。

| 字段 | 类型 | 空 | 默认 | 语义 |
| --- | --- | --- | --- | --- |
| id | UUID | 否 | gen_random_uuid() | PK pk_networks |
| cluster_id | UUID | 否 | — | FK→clusters(id) ON DELETE RESTRICT；创建必填；引用须存在未软删；有未删 Pool/IP 时不可改（I-4） |
| name | varchar(255) | 否 | — | trim→非空→禁 Cc/Cf；允许中文及内部普通空格、不自动合并；大小写不敏感；同 Cluster 未删唯一；删除后复用（I-2） |
| name_key | varchar(255) | 否 | — | ASCII_lower(btrim(name))；部分唯一载体（I-2） |
| cidr | cidr | 否 | — | 合法 IPv4 CIDR；同 Cluster 未删不重叠（INACTIVE 参与）；有未删 Pool/IP 时不可改（I-1/I-4） |
| gateway | inet | 是 | null | 可空 IPv4；属该 CIDR 基础可用地址且非 §11.1 禁用；/32 必空；从可分配集合排除 |
| status | varchar(16) | 否 | 'ACTIVE' | ACTIVE\|INACTIVE；INACTIVE 禁新增分配、仍参与重叠检查 |
| auto_allocate | boolean | 否 | false | 仅控自动分配，不绕过状态与地址约束 |
| description | text | 是 | null | 描述性 |
| metadata | jsonb | 否 | '{}'::jsonb | **Network 自有**；object CHECK；整值替换（I-6） |
| version | integer | 否 | 1 | 乐观锁 CHECK ≥1 |
| created_at/updated_at | timestamptz | 否 | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | 是 | null | 软删 |

省略语义（§4.1/D01 §4）：创建省略非必填→默认/null；PATCH 省略=保持；显式 null 仅清空 nullable（gateway/description）；必填/非 nullable 显式 null→422。**不落字段**：VLAN ID、网络分类、Pool 起止、IP 列表、allocation_mode（§11/§12/§13）。

### 1.2 关系
Network 多对一依附 Cluster；1:N IPPool（F009）、1:N IPAddress（F010）。名称唯一与 CIDR 不重叠作用域均为同 Cluster，跨 Cluster 允许（§11）。gateway 语义供 F009/F010/F013 共用（§11.1/§20）。

## 2. API 裁定与 Contract 要点
**裁定（DR-97）：新建独立端点 /api/v1/networks + 独立 Contract docs/api/F008.md；不并入 F003 Cluster 嵌套。** 理由：§25 明确列出该路径；Network 自身 ID/version/软删/恢复/Activity，可独立寻址；子对象走各自端点经 network_id 关联。

7 端点：GET/POST /api/v1/networks；GET/PATCH/DELETE /api/v1/networks/{id}；POST /api/v1/networks/{id}/restore；GET /api/v1/networks/{id}/activity。
- 响应 Network：id、cluster{id,code,name}、name、cidr、gateway|null、status、auto_allocate、description|null、metadata、version、created_at/updated_at、deleted_at。列表 {items,page,page_size,total}。
- 过滤/排序：cluster_id、status∈{ACTIVE,INACTIVE}、auto_allocate=bool、q（对 name **大小写不敏感子串**，空/纯空白视为未提供）、deleted∈{exclude,include,only} 默认 exclude；page≥1、page_size 1–100、sort∈{name,cidr,status,created_at,updated_at} 默认 created_at、order∈{asc,desc} 默认 desc、附 id 升序稳定。
- 错误码（复用 F002 §1.2 + F003 CONFLICT，F008 只新增 reason）：401；403{permission|csrf}；404；409 VERSION_CONFLICT{current_version}；422 VALIDATION_ERROR{fields}；409 CONFLICT{reason}：unique_conflict(field:"name")；**range_overlap（新 reason，注册 F002 §1.2；field:"cidr"，conflicts:[{object_type:"network",object_id,label}]）**；reference_exists（删除/改 cidr/cluster 被未删 Pool/IP 引用，references:[{object_type:"ip_pool"|"ip_address",object_id,label}]）；not_deleted；dependency_deleted（恢复重检 Cluster 仍软删/缺失）。
- 校验顺序：POST 401→403→body(422)→cluster(422)→name 唯一(409)→cidr 格式/gateway 边界(422)→cidr 重叠(409 range_overlap)→写+Audit→201；PATCH 401→403→body(422)→可见性(404)→version(409)→name 唯一(409)→cidr/gateway(422)→依赖引用(409 reference_exists)→cidr 重叠(409 range_overlap)→写+Audit→200；DELETE 401→403→对象(404)→version 校验(422)→版本(409)→引用(409)→软删；restore 401→403→查找含软删(404)→未删 409 not_deleted→版本(409)→name 唯一(409)→cluster 依赖(409)→cidr 重叠(409 range_overlap)→恢复。name 复用优先于依赖失效。
- 审计白名单：{cluster_id,name,cidr,gateway,status,auto_allocate,description,metadata}；object_type="network"；CREATE/UPDATE/DELETE/RESTORE 同事务。

## 3. CIDR 不重叠、名称唯一与变更限制

### 3.1 CIDR 不重叠（I-1，DR-92）
- 表示：列类型 PostgreSQL 原生 cidr（§11/§26）。
- 约束：`EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE (deleted_at IS NULL)`。cidr WITH && 由 PG core GiST opclass 提供；cluster_id WITH = 需 **btree_gist**（本 Feature 首次启用）。
- 软删参与：谓词仅 deleted_at IS NULL；INACTIVE 未软删故参与；恢复置 deleted_at=null 重新受约束，重叠→409 range_overlap。
- 并发：排除约束写入时原子兜底；违反映射 409 range_overlap，无静默重试。
- 跨表归属：CIDR 唯一属主为 Network；F009/F010 经 network_id 关联，不在子表重复 cidr。

### 3.2 名称唯一（I-2，DR-90）
name_key = ASCII_lower(btrim(name))：仅 ASCII A-Z→a-z，非 ASCII 原样，locale 无关（同 D01 §5.1/§5.3）。部分唯一 UNIQUE(cluster_id,name_key) WHERE deleted_at IS NULL。内部普通空格允许且不合并。

### 3.3 gateway（§11.1，DR-93）
可空 IPv4。填写须①属 CIDR 基础可用地址（/0～/30 排除网络/广播；/31 两地址均可用；/32 必空）②非 §11.1 禁用范围（0.0.0.0/8、127.0.0.0/8、169.254.0.0/16、224.0.0.0/4、240.0.0.0/4）。违反→422。gateway 从可分配集合排除（下游共用）。「已占用 IP 设为 gateway 拒绝」归 F009/F010（I-5）。

### 3.4 变更限制与引用检查（I-4，DR-96）
有未删除 Pool/IP 引用（network_id）时禁改 cidr/cluster_id，返回 409 reference_exists + 引用列表；无引用时按名称/重叠约束允许并重检目标 Cluster。F008 建表时 F009/F010 子表尚不存在，故用**依赖检查器注册表**：F008 注册 Network 引用集调用点（初始空集），F009/IPPool、F010/IPAddress 后续注册。并发：改 cidr/cluster 事务内对 networks 行 SELECT ... FOR UPDATE 串行化；F009/F010 创建子对象须取同 Network 行锁（跨 Feature 协议）。

## 4. 数据库影响（交 DATABASE）
表 networks：id UUID PK pk_networks；cluster_id NOT NULL FK fk_networks_cluster_id_clusters ON DELETE RESTRICT + ix_networks_cluster_id；name varchar(255) NOT NULL + ck trim/非空/Cc-Cf backstop；name_key varchar(255) NOT NULL + ck 与 translate 口径一致；cidr cidr NOT NULL；gateway inet NULL + ck 属 cidr 基础可用地址且非禁用（可行则 DB 表达式，否则应用主导 + backstop）；status varchar(16) NOT NULL DEFAULT 'ACTIVE' + ck IN('ACTIVE','INACTIVE')；auto_allocate boolean NOT NULL DEFAULT false；description text NULL；metadata jsonb NOT NULL DEFAULT '{}' + object CHECK（ORM 属性 meta）；version integer NOT NULL DEFAULT 1 CHECK ≥1；created_at/updated_at；deleted_at。
约束/索引：EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE (deleted_at IS NULL)；uq_networks_cluster_id_name_key UNIQUE(cluster_id,name_key) WHERE deleted_at IS NULL；ix_networks_cluster_id；ix_networks_status；ix_networks_deleted_at；不建 pg_trgm GIN。
迁移 0008_networks，down_revision=0007，单一 head；**首次启用 btree_gist**：CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public（F001 DB-D2 预定启用点），再建表/约束/索引；全表新建无回填，对称可逆（downgrade 逆序 drop，不 drop 扩展，同 F001 DB-D4），真库 up/down/up；生产回滚用 F001 全库备份。

## 5. D01 v6→v7 补齐（DR-101）
新增 **§5.7 Network 字段口径**：name trim→非空→禁 Cc/Cf→长度 1–255（PROPOSED，镜像 Cluster name）；允许中文及内部普通空格不合并；大小写不敏感、保留展示；name_key=ASCII_lower(btrim(name))（仅 ASCII 折叠、locale 无关）；部分唯一 WHERE deleted_at IS NULL。cidr 合法 IPv4 CIDR，含 host 位归一化为网络地址存储/展示（PG cidr 语义）。gateway 可空、取值域见 §3.3，/32 必空。status 2 值默认 ACTIVE；auto_allocate 默认 false；metadata Network 自有。§3 追加 cidr/gateway 引用、§5.2 追加 Network name 255、§5 表 Network 行、§8 记录 v7。

## 6. 验证策略（A1–A22，真实 PG）
A1/A2/A4 部分唯一（同 Cluster 重名 409；跨 Cluster 同名允许；软删后重建；存活同名失败；恢复重检不覆盖）；A3 name trim/空/Cc-Cf 422 + 内部普通空格保留 + CHECK 负例；A5/A6 排除约束（同 Cluster 重叠/相同 409 range_overlap；跨 Cluster 允许；INACTIVE 参与）；A7 非 IPv4/非法 CIDR 422；A8 cluster 缺失/不存在/软删 422；A9 有未删 Pool/IP 改 cidr/cluster →409 reference_exists + 列表，无引用按约束允许并重检；A10/A11 gateway 空允许/越界或禁用 422/从可分配排除；A12/A13 status、auto_allocate 默认与非法值 422；A14 INACTIVE 禁新增分配语义（分配本体归 F010）；A15 删除引用检查 409 + 不级联；A16 恢复重检名称/cluster/CIDR 重叠，失败不覆盖；A17/A18 权限矩阵、四 action 同事务 Audit；A19 列表软删隐藏含 INACTIVE、过滤分页排序；A20 DB 部分唯一 + 排除约束兜底；A21 归一化在 API/导入(F014)/搜索(F013)/DB 一致；A22 CIDR/网关边界作为下游共同输入（交 F009/F010/F013）。补充 DB/集成：0008 真库 up/down/up + 单一 head + btree_gist 幂等启用；部分唯一/排除/CHECK/索引断言；并发双会话（重叠插入、恢复重检、改 cidr 与子对象创建行锁）；乐观锁并发；审计回滚；引用检查端到端。

## 7. 技术决策（DR-89–DR-101）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-89 | Network 独立表 PK=UUID，cluster_id FK RESTRICT | CONFIRMED+DESIGN |
| DR-90 | name varchar(255) trim/非空/禁 Cc/Cf、允许内部普通空格不合并、大小写不敏感；name_key=ASCII_lower(btrim(name))；部分唯一 (cluster_id,name_key) WHERE deleted_at IS NULL | PROPOSED→CONTRACT(1–255) |
| DR-91 | cidr 用 PG 原生 cidr，仅 IPv4；含 host 位归一化为网络地址 | CONFIRMED+I-2 |
| DR-92 | CIDR 不重叠 = EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE deleted_at IS NULL；首次启用 btree_gist | PROPOSED→DATABASE |
| DR-93 | gateway 可空 inet；属 CIDR 基础可用地址、非 §11.1 禁用；/32 必空 | CONFIRMED+I-2 |
| DR-94 | status varchar(16) 默认 ACTIVE 2 值；auto_allocate bool 默认 false | CONFIRMED |
| DR-95 | metadata Network 自有 jsonb 默认 {} object CHECK | CONFIRMED |
| DR-96 | 变更限制：有未删 Pool/IP 引用禁改 cidr/cluster；依赖检查器注册表 + networks 行 FOR UPDATE 串行化 | PROPOSED→DATABASE(I-4) |
| DR-97 | API 独立 /api/v1/networks + 新建 docs/api/F008.md | CONFIRMED |
| DR-98 | 新增 CONFLICT reason range_overlap（注册 F002 §1.2，含 conflicts 明细） | PROPOSED→CONTRACT |
| DR-99 | 软删/恢复；恢复重检名称唯一、cluster 有效、CIDR 不重叠；失败不覆盖 | CONFIRMED |
| DR-100 | 迁移 0008_networks（down_revision=0007），首次启用 btree_gist（IF NOT EXISTS），对称可逆、单一 head、无回填 | DESIGN→DATABASE |
| DR-101 | D01 v6→v7 增 §5.7；§3/§5/§5.2 同步 | PROPOSED→CONTRACT |

## 8. 裁定 I-1–I-6（PROPOSED）
- **I-1**：表示=PG cidr；不重叠=btree_gist 排他约束 (cluster_id=,cidr&&) WHERE deleted_at IS NULL；INACTIVE 参与、软删由谓词排除；并发由约束原子兜底；跨表 CIDR 唯一属主为 Network；恢复重检由约束闭环。
- **I-2**：name 长度 1–255（镜像 Cluster name，PROPOSED）；折叠=仅 ASCII A-Z→a-z（name_key）；CIDR 含 host 位接受并归一化为网络地址（与 PG cidr 一致）；gateway 取值域见 §3.3。
- **I-3**：不新增建网限制——§11 未禁止创建 CIDR 完全落在 §11.1 禁用范围内的 Network；F008 仅拒绝 gateway 落入禁用范围。是否禁止此类建网属新业务限定，须用户裁定，本设计不预建。
- **I-4**：F008 用依赖检查器注册表（初始空集），F009/F010 后续注册；改 cidr/cluster 与删除共用同一引用集；并发用 networks 行 FOR UPDATE 串行化（F009/F010 子对象创建须取同锁）。
- **I-5**：「将已占用 IP 设为 gateway 拒绝（含未绑定）」归 F009/F010（§12.1/T33）；F008 仅保证 gateway 边界语义可被下游复用。
- **I-6**：metadata 为 Network 自有 JSONB 列（§11 字段清单），不并入公共 metadata。

## 9. Layers 与分工
layers.database=true、backend=true、frontend=true、api_required=true。
- Database：docs/database/f008-network.md（表/CHECK/部分唯一/排除约束/索引/FK/依赖检查器落点/迁移 0008 + btree_gist）；裁定 I-1/I-2/I-4 落地；真 PG 验证项。
- Backend：models/network.py；schemas/network.py；services/network.py（name_key 归一化、cidr/gateway 边界、重叠映射 range_overlap、软删过滤、引用检查、FOR UPDATE 锁序）；注册 Network 引用检查器调用点；audit 白名单扩 network；api/v1/networks.py+router；迁移 0008。
- Frontend：Networks 区域（F013 聚合消费）；Network 创建/编辑表单（cluster 选择器、cidr/gateway 校验、status、auto_allocate、422 点路径）；已删开关与 ADMIN 恢复。
- Contract：docs/api/F008.md 置 READY；签核 D01 v7 §5.7；固定 DR-90/92/93/96/97/98/101。

## 10. 风险与待核对项
交 DATABASE：排除约束操作符类与 btree_gist 启用闭环；gateway CHECK 可否纯 SQL 表达（否则应用主导 + backstop）；部分唯一/索引集合；0008 up/down/up。
交 TEST_DESIGN：A1–A22；重叠插入并发双会话；恢复重检与约束交互；改 cidr 与子对象创建行锁协议（跨 F009/F010）；审计回滚；引用检查端到端。
交 CONTRACT：DR-90/92/93/96/97/98/101 固定；range_overlap details 形状；q 大小写不敏感口径；错误码/字段路径；I-1–I-6 记录。
跨 Feature：F009/F010 承接 network←IPPool/IPAddress 引用注册与子对象创建锁；F013 承接容量；F014 复用 name/cidr/gateway 口径。
已知不足：gateway 纯 DB CHECK 若不可行仅应用层主导（DB backstop）；改 cidr/cluster 并发串行化依赖 F009/F010 配合取同 Network 行锁。

## 11. 结论与下一步
无 Blocking Questions。Status **READY FOR DESIGN**。下一步：DATABASE 出 docs/database/f008-network.md（排除约束/部分唯一/依赖检查器/迁移 0008）；TEST_DESIGN 核对 A1–A22；CONTRACT 定稿 docs/api/F008.md + D01 v7 §5.7 并签核 DR-90/92/93/96/97/98/101，完成后出 READY FOR IMPLEMENTATION。
## 12. 最终设计定稿（CONTRACT Gate）

- **Status**：`READY FOR IMPLEMENTATION`（2026-10-09）
- **签核**：Architect；Contract docs/api/F008.md v1；D01 d01-conventions.md v7（§3/§5.2/§5.7）
- **核对版本**：database/f008-network.md v1（DB-D80–D94）；test-report.md TD-1（§8 OPEN-1–15 由本 Contract 闭合，TD-2 由 Tester 发布）。
- **裁定固定**：DR-90（name 1–255，仅 ASCII 折叠）、DR-92（CIDR 排他约束 + btree_gist）、DR-93（gateway 取值域）、DR-96（有未删 Pool/IP 禁改 cidr/cluster + 引用检查器 + FOR UPDATE）、DR-97（独立 /api/v1/networks + 新建 docs/api/F008.md）、DR-98（新增 CONFLICT reason range_overlap）、DR-101（D01 v7 §5.7）；metadata 归 Network 自有；恢复错误码 name 优先。
- **实现前置**：Backend 必须按 DR-96 实现引用检查器注册表（初始空集）+ networks 行 FOR UPDATE；F009/F010 创建子对象须取同 Network 行锁（跨 Feature 协议）。
- **实现分工**：Backend（model/migration 0008、schemas、service name_key/cidr/gateway/重叠/引用检查器/锁序、audit 白名单扩 network、api/v1/networks 7 端点）；Frontend（Networks 区域、创建/编辑表单 cluster 选择器 + cidr/gateway 校验 + status/auto_allocate、422 点路径、已删开关与 ADMIN 恢复）。
- **边界（不宣称）**：IPPool F009、IP 分配/容量 F010/F013、导入 F014、完整 Audit F015；I-3（禁用范围建网）属新业务限定须用户裁定。
