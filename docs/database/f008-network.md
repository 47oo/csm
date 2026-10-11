# F008 Network 网络管理 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§11、§11.1、§12.1、§20、§21、§26、§27、§31 T14/T16/T24/T29/T30/T37/T38/T40/T41、§35.2 Q02-A/Q04-A/Q04-B/Q10-A/Q10-B、§35.3 D01/D02）；docs/features/F008/product.md（A1–A22、I-1–I-6）；docs/features/F008/architecture.md（§3/§4、DR-89–DR-101）；docs/database/f001-baseline.md（DB-D2 btree_gist/DB-D7）；docs/database/f007-interface.md（模式）；docs/architecture/d01-conventions.md v6
- **覆盖**：networks 表、字段/约束/索引、CIDR 不重叠排他约束、部分唯一、gateway 取值域、依赖检查器落点、迁移 0008、I-1/I-2/I-4 落地裁定。不覆盖 docs/api/F008.md、D01 v7 §5.7、TEST 执行与实现。

## 1. 设计决策汇总（DB-D80–DB-D94）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D80 | networks 独立对象表，id UUID PK pk_networks 默认 gen_random_uuid()；cluster_id UUID NOT NULL FK fk_networks_cluster_id_clusters→clusters(id) ON DELETE RESTRICT + ix_networks_cluster_id | CONFIRMED（§11/§21/DR-89）+DESIGN |
| DB-D81 | name varchar(255) NOT NULL + trim/非空/ASCII 控制 backstop/长度 1–255 CHECK；name_key varchar(255) NOT NULL，ASCII_lower(btrim(name)) translate 口径 CHECK（I-2） | PROPOSED→CONTRACT(1–255)+DESIGN |
| DB-D82 | 部分唯一 uq_networks_cluster_id_name_key UNIQUE(cluster_id,name_key) WHERE deleted_at IS NULL | CONFIRMED（§4.1/§27/DR-90）+DESIGN |
| DB-D83 | cidr PG 原生 cidr NOT NULL；ck_networks_cidr_ipv4 family(cidr)=4；host 位由 cidr 类型归一化为网络地址 | CONFIRMED（§11/§26/DR-91）+DESIGN |
| DB-D84 | gateway inet NULL + 纯 SQL CHECK（属 CIDR 基础可用地址、非 §11.1 禁用）；应用先校验 422，CHECK 为 backstop | PROPOSED→DATABASE+DESIGN |
| DB-D85 | status varchar(16) NOT NULL DEFAULT 'ACTIVE' + CHECK IN('ACTIVE','INACTIVE')；auto_allocate boolean NOT NULL DEFAULT false | CONFIRMED（§11/DR-94）+DESIGN |
| DB-D86 | metadata jsonb NOT NULL DEFAULT '{}' + object CHECK；Network 自有 | CONFIRMED（§11/DR-95）+DESIGN |
| DB-D87 | version integer NOT NULL DEFAULT 1 CHECK≥1；created_at/updated_at（updated_at 应用维护）；deleted_at | DESIGN |
| DB-D88 | CIDR 不重叠排他约束 excl_networks_cluster_id_cidr EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE (deleted_at IS NULL)；cluster_id WITH = 需 btree_gist（0008 首次启用） | PROPOSED→DATABASE（I-1/DR-92）+DESIGN |
| DB-D89 | 索引仅 ix_networks_cluster_id、ix_networks_status、ix_networks_deleted_at；不建 pg_trgm/GIN、不建 cidr 单列 B-tree（F013 交叉引用：`networks` 不在 §17 搜索目标，F013 `0013_search_indexes` 未建 networks 索引；见 docs/database/f013-search-index.md §7-E2） | DESIGN |
| DB-D90 | 依赖检查器落点：应用注册表（F008 初始空集，F009/F010 注册）+ networks 行 FOR UPDATE；DB 仅 FK RESTRICT；不建软删引用触发器（子表尚不存在，I-4） | PROPOSED→DATABASE（I-4/DR-96）+DESIGN |
| DB-D91 | 迁移 0008_networks，down_revision=0007；首次 CREATE EXTENSION IF NOT EXISTS btree_gist；建表→约束/排他→索引；对称可逆、单一 head、无回填、真库 up/down/up | DESIGN（DR-100） |
| DB-D92 | I-1/I-2/I-4 落地见 §3 | DESIGN |
| DB-D93 | 不建 cluster_id/cidr 不可变触发器（需求允许无子对象时改 cidr/cluster）；改 cidr/cluster 由应用引用检查 + FOR UPDATE 承担 | DESIGN（I-4） |
| DB-D94 | 100% 新建对象；downgrade 丢弃 networks 数据不可逆，生产回滚用 F001 全库备份 | DESIGN |

## 2. networks 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_networks |
| cluster_id | UUID | NOT NULL | — | FK fk_networks_cluster_id_clusters→clusters(id) ON DELETE RESTRICT；ix_networks_cluster_id |
| name | varchar(255) | NOT NULL | — | ck_networks_name_not_blank/_trimmed/_no_control/_length |
| name_key | varchar(255) | NOT NULL | — | ck_networks_name_key_matches（translate 口径） |
| cidr | cidr | NOT NULL | — | ck_networks_cidr_ipv4：family(cidr)=4 |
| gateway | inet | NULL | — | ck_networks_gateway：NULL 或属 CIDR 基础可用地址且非禁用 |
| status | varchar(16) | NOT NULL | 'ACTIVE' | ck_networks_status：IN('ACTIVE','INACTIVE') |
| auto_allocate | boolean | NOT NULL | false | — |
| description | text | NULL | — | — |
| metadata | jsonb | NOT NULL | '{}'::jsonb | ck_networks_metadata_object；ORM 属性 meta |
| version | integer | NOT NULL | 1 | ck_networks_version：≥1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

CHECK：ck_name_not_blank `btrim(name)<>''`；ck_name_trimmed `name=btrim(name)`；ck_name_no_control `name !~ '[[:cntrl:]]'`（ASCII backstop；允许内部普通空格）；ck_name_length `char_length(name) BETWEEN 1 AND 255`；ck_name_key_matches `name_key = translate(btrim(name),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')`（不得用 lower()）；ck_cidr_ipv4 `family(cidr)=4`；ck_gateway 见 §3.3；ck_status/ck_metadata_object/ck_version。

约束/索引：uq_networks_cluster_id_name_key UNIQUE(cluster_id,name_key) WHERE deleted_at IS NULL；excl_networks_cluster_id_cidr EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE (deleted_at IS NULL)；ix_networks_cluster_id、ix_networks_status、ix_networks_deleted_at。

## 3. 交核裁定

### 3.1 I-1 CIDR 不重叠（DB-D83/DB-D88）
表示 PG 原生 cidr；host 位归一化为网络地址（'10.0.0.5/24'→'10.0.0.0/24'）。不重叠 EXCLUDE USING gist (cluster_id WITH =, cidr WITH &&) WHERE (deleted_at IS NULL)：cidr WITH && 由 PG core GiST inet/cidr opclass；cluster_id WITH = 需 btree_gist（0008 首次 IF NOT EXISTS 启用，F001 DB-D2 预定）。谓词仅 deleted_at IS NULL → INACTIVE 参与、软删排除；恢复置 null 重新受约束，重叠 409 range_overlap。并发由约束原子兜底。CIDR 唯一属主为 Network；F009/F010 经 network_id 关联。

### 3.2 I-2 名称与 CIDR 口径（DB-D81）
name 长度 1–255（镜像 Cluster name）；仅 ASCII A-Z→a-z 折叠，非 ASCII 原样；内部普通空格保留不合并。name_key=ASCII_lower(btrim(name))，DB 用 translate，应用逐码位，同口径；DB CHECK 锁定。cidr host 位归一化；gateway 见 §3.3。

### 3.3 gateway 取值域（DB-D84；可纯 SQL，DB CHECK 为 backstop）
应用先校验 422（field="gateway"）；DB CHECK：
```sql
gateway IS NULL OR (
  family(gateway)=4 AND masklen(cidr)<=31 AND gateway << cidr::inet
  AND ( masklen(cidr)=31 OR (gateway <> network(cidr)::inet AND gateway <> broadcast(cidr)) )
  AND NOT ( gateway << '0.0.0.0/8'::inet OR gateway << '127.0.0.0/8'::inet
         OR gateway << '169.254.0.0/16'::inet OR gateway << '224.0.0.0/4'::inet OR gateway << '240.0.0.0/4'::inet )
)
```
/0–/30 排网络/广播；/31 两址可用；/32 必空；禁用 5 段为 §11.1 CONFIRMED。函数均 immutable 可作 CHECK。不校验 gateway 是否已占用 IP（归 F009/F010，I-5）。禁用清单变更属业务变更须迁移同步。

### 3.4 I-4 依赖检查器落点（DB-D90/DB-D93）
DB 层：physical delete 一旦 F009/F010 建子表，FK network_id ON DELETE RESTRICT 阻断；F008 建表时子表不存在无法预置。应用层：依赖检查器注册表——F008 注册 Network 引用集调用点（初始空集），F009/IPPool、F010/IPAddress 后续注册；有未删引用时禁改 cidr/cluster_id、禁删，409 reference_exists + 引用列表。并发：改 cidr/cluster 事务内对 networks 行 SELECT ... FOR UPDATE；F009/F010 创建子对象须取同 Network 行锁。不建 cluster_id/cidr 不可变触发器（需求允许无子对象时修改）；不建软删引用触发器。

## 4. 迁移 0008_networks
revision="0008_networks"、down_revision="0007_interfaces"；单一 head。
upgrade：①CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public（幂等；不重复启用 pg_trgm）→②create_table（列+PK+FK+全部 CHECK，op.f 显式名）→③部分唯一索引（postgresql_where=sa.text("deleted_at IS NULL")）→④ix_networks_cluster_id/_status/_deleted_at→⑤op.execute 添加 excl_networks_cluster_id_cidr。无回填。
downgrade 逆序：DROP 排他约束→三索引→部分唯一索引→DROP TABLE networks；**不 DROP btree_gist**（同 F001 DB-D4）。
校验计划：真库 up→down→up；alembic heads 唯一=0008_networks；对象齐全；btree_gist 在 0008 后 pg_extension 存在且幂等。

## 5. 数据完整性对应表（精简）

| 规则 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §11/§27/DR-92 CIDR 同 Cluster 未删不重叠 | POST/PATCH/restore | EXCLUDE gist WHERE deleted_at IS NULL + btree_gist | 先查冲突→409 range_overlap+conflicts | 约束原子兜底；INACTIVE 参与；软删排除；恢复重检 | V-DB-71/75/80 |
| §4.1/§27/DR-90 name 同 Cluster 未删唯一 | POST/PATCH | 部分唯一 (cluster_id,name_key)；name_key CHECK | trim；折叠；409 unique_conflict{name} | 索引仲裁；软删释放；恢复冲突拒 | V-DB-68/69/70 |
| §4.1/T40 name 规范 | POST/PATCH | ck_name_*（ASCII backstop） | trim→非空→禁 Cc/Cf→1–255；内部空格保留 | Cc/Cf 应用责任 | V-DB-68 |
| §11 仅 IPv4 CIDR | POST/PATCH | cidr 类型 + ck_cidr_ipv4 | 非法/非 IPv4→422；host 位归一化 | — | V-DB-72 |
| §11/§11.1/T30 gateway | POST/PATCH | ck_networks_gateway | 取值域→422 field="gateway" | /32 必空；占用检查归 F009/F010 | V-DB-73 |
| §11/DR-94 status/auto_allocate | POST/PATCH | NOT NULL+DEFAULT+CHECK | 省略默认；非法 422；INACTIVE 禁新增分配 | 枚举扩展走迁移 | V-DB-74 |
| §11/DR-95 metadata | POST/PATCH | object CHECK+DEFAULT | 整值替换；非 object/null 422 | — | V-DB-76 |
| §4.1/§21 cluster 归属 | POST | cluster_id NOT NULL+FK RESTRICT | 引用存在未软删否则 422 | cluster 软删不删 networks 行；物理删 RESTRICT | V-DB-77 |
| §21/§27 有未删 Pool/IP 禁改/禁删 | PATCH/DELETE | 无（子表缺失） | 引用检查器→409 reference_exists+列表 | FOR UPDATE 串行；F009/F010 取同锁 | F009/F010 集成 |
| §21 软删/恢复 | DELETE/restore | deleted_at+部分唯一+排他约束 | 默认过滤；恢复重检 name/cluster/CIDR，失败不覆盖 | 不级联 | V-DB-75/78 |
| §23 乐观锁 | PATCH/DELETE/restore | version CHECK+条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-79 |
| §26/§27 真实 PG | 迁移/约束 | 0008 up/down/up、单一 head、无回填、btree_gist 幂等 | — | — | V-DB-81 |

## 6. Backend 可依赖保证与测试项

保证：id 唯一（PK）；cluster_id 非空指向存在 Cluster（FK）；物理删被引用 Cluster 被 RESTRICT 拒；同 Cluster 未删 name 大小写不敏感唯一（name_key 部分唯一），跨 Cluster 允许，软删释放、恢复冲突拒；name 已 trim 非空 1–255 无 ASCII 控制字符；cidr 恒 IPv4 网络地址（类型归一化）；gateway NULL 或属 CIDR 基础可用地址且非 §11.1 禁用；status 恒 2 值默认 ACTIVE；auto_allocate 默认 false；metadata 恒 object 默认 {}；version ≥1 默认 1；同 Cluster 未删 CIDR 两两不重叠（排他约束）；索引 ix_networks_cluster_id/_status/_deleted_at；0008 有真实 downgrade、单一 head、无回填、btree_gist 幂等。

不保证：软删下 Pool/IP 引用保护（应用注册表）；改 cidr/cluster 与子对象创建并发串行化（应用 FOR UPDATE）；name 的 Unicode Cc/Cf（ASCII backstop）；gateway 与已占用 IP 冲突（F009/F010）；metadata 语义（仅 object）；CIDR 是否完全落在 §11.1 禁用范围（I-3）。

计划测试项（真实 PG，V-DB-68–V-DB-81）：V-DB-68 name 边界与内部普通空格保留；V-DB-69 name_key CHECK 与 translate 一致；V-DB-70 部分唯一（大小写重名 409/跨 Cluster/软删重建/存活同名拒/恢复冲突/并发）；V-DB-71 排他约束（重叠/相同拒/跨 Cluster/INACTIVE 参与/软删后插入）；V-DB-72 cidr 非 IPv4 拒、host 位归一化；V-DB-73 gateway 边界（空/网络/广播/禁用/非本 CIDR//32//31）；V-DB-74 status/auto_allocate；V-DB-75 恢复重检；V-DB-76 metadata object；V-DB-77 FK RESTRICT/软删 Cluster；V-DB-78 软删/恢复；V-DB-79 version/乐观锁；V-DB-80 并发双会话；V-DB-81 迁移 up/down/up、单一 head、btree_gist 幂等、对象/不存在断言。

## 7. 未验证项与风险
- I-1（已闭合）：排他约束闭环；btree_gist 置于 0008。
- I-2（LOW，交 CONTRACT/D01 v7）：name 1–255 与 cidr/gateway 口径待 docs/api/F008.md 与 D01 §5.7 固定。
- I-4（MEDIUM，交 Backend/Architect）：DB 无法在 F008 单独闭软删引用保护与改 cidr/cluster 并发；须 F009/F010 注册检查器并取同 Network 行锁。
- I-3（NOTE，交 Product/用户）：不禁止创建 CIDR 完全落在 §11.1 禁用范围的 Network；是否收紧属新增业务限定。
- I-5（NOTE，交 F009/F010）：gateway 与已占用 IP 冲突检测不在 F008。
- I-6（已闭合）：metadata 归 Network 自有。
- I-7（NOTE）：down 丢弃 networks 数据不可逆。
- 只读签核，全部为计划验证无 PASS。

## 8. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D80–D94）；networks 首次建表、部分唯一 (cluster_id,name_key)、EXCLUDE gist CIDR 不重叠（btree_gist 首次启用）、gateway 纯 SQL CHECK、索引裁定、迁移 0008、I-1/I-2/I-4 落地。 |