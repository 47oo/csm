# F004 Resource 核心登记 — ARCHITECTURE 阶段报告

- **Task**：F004（FEATURE，P0，M2，deps [F003]）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-07；协调器核验后持久化）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§6、§7、§18、§21–§23、§25、§27–§28、§31、§33、§35.2 Q10-A/Q10-B、§35.3 D01/D02）；F004 product.md（A1–A13）；F003 architecture.md/api/F003.md v2/database/f003-cluster.md v2；d01-conventions.md v2；F002.md v1；plan_revision 4 F004 条目。
- **结论属性**：设计输入，交 DATABASE/TEST_DESIGN；Contract 草案供 CONTRACT 定稿，本阶段不放行编码。

## 1. 方案摘要

### 1.1 Resource 实体

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| cluster | FK→clusters(UUID) | 否 | — | 创建必填；不可改（§6） |
| hostname | string | 否 | — | trim+小写存储（§7）；可改，改后重检唯一 |
| resource_type | enum | 否 | — | 仅 BARE_METAL/VIRTUAL_MACHINE；不可改 |
| role | enum | 否 | OTHER | COMPUTE/LOGIN/MANAGEMENT/STORAGE/SERVICE/GPU/OTHER；显式 null→422；可扩展 |
| status | enum | 否 | UNKNOWN | IDLE/ALLOC/DOWN/UNKNOWN；人工维护 |
| description | string | 是 | null | — |
| metadata | object | 否 | {} | 整值替换 |
| version | int≥1 | 否 | 1 | 乐观锁 |
| created_at/updated_at | timestamptz | 否 | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | 是 | null | 软删 |

- 显式 null 拒绝：cluster/hostname/resource_type/role/status/metadata 显式 null→422；仅 description 可 null（D01 §4）。
- 不可改：PATCH 含 cluster/cluster_id/resource_type/只读字段→422；服务端+DB 触发器双重兜底。
- 不建 BareMetalDetail/VirtualMachineDetail（F005/F006）；Detail 非 Overview 区域占位。

### 1.2 hostname 归一化（D01 §5、§7）

- 归一化：btrim→非空→禁内部空白/控制字符→长度 1–253（PROPOSED）→统一小写。cn001/CN001/" cn001 " 同 Cluster 相同。
- 大小写折叠：沿用 F003-REV-1 **ASCII-only 折叠**原则（locale 无关）：应用对 btrim 后逐码位仅折叠 ASCII A-Z→a-z，非 ASCII 原样；DB 用 `translate(btrim(hostname),'ABC…','abc…')`，不用 lower()（PROPOSED）。
- 存储：hostname 存归一化小写展示值；hostname_key 内部唯一键列受 CHECK 约束，不暴露。
- 唯一性：同 Cluster (cluster_id, hostname_key) **部分唯一 WHERE deleted_at IS NULL**（软删可重用）；跨 Cluster 允许；短名/FQDN 按完整字符串。
- 入口一致：API/导入(F014)/搜索/DB 共用同一归一化。

### 1.3 列表/Detail/搜索/生命周期

- 列表：组合过滤 cluster(code)/cluster_id/type/role/status + q(hostname ILIKE) + 分页/排序。
- Detail Overview（§18）：Hostname/Cluster/Type/Role/Status/Description；其它区域占位（F005+）。
- hostname 基础搜索：`GET /resources?q=<hostname>`（ILIKE，不用 pg_trgm；全局搜索/pg_trgm/GIN 归 F013，沿用 DB-D30）。**F013 errata**：F013 `0013_search_indexes` 已建 `ix_resources_hostname_trgm`（GIN trigram），各域列表 `q` 行为不变。
- 软删/恢复/审计/乐观锁：完全复用 F003 基座；object_type="resource"。
- 引用检查：resource 自身被引用来源在 F007+（空集）；**F004 注册首个反向检查器 cluster←未删除 Resource**（有未删 Resource 时禁止删 Cluster，§21 必然结果，F003 cluster 删除随之收窄）。

## 2. Implementation Layers

database=true；backend=true；frontend=true；api_required=true。

## 3. API 草案（CONTRACT 路径 docs/api/F004.md）

Base /api/v1；JSON；ISO-8601 UTC；错误信封/Cookie/CSRF/操作者上下文复用 F002/F003。

### 3.1 Resource 响应对象

id(UUID)/cluster(id,code,name)/hostname(归一化小写)/resource_type(enum)/role(enum 默认 OTHER)/status(enum 默认 UNKNOWN)/description(null)/metadata({} 整值替换)/version/created_at/updated_at/deleted_at(null)。hostname_key 不暴露。

### 3.2 Endpoints

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/v1/resources | READ | q/cluster/cluster_id/type/role/status/deleted/page/page_size/sort/order；deleted=include\|only 需 VIEW_DELETED |
| POST | /api/v1/resources | WRITE | 创建；201 |
| GET | /api/v1/resources/{id} | READ | 详情；deleted=true 需 VIEW_DELETED |
| PATCH | /api/v1/resources/{id} | WRITE | 部分更新；version 必填；不可改字段→422 |
| DELETE | /api/v1/resources/{id} | DELETE_OBJECT | 软删；version 必填；引用检查（当前空集） |
| POST | /api/v1/resources/{id}/restore | RESTORE | 恢复；version 必填；重检唯一性与依赖 |
| GET | /api/v1/resources/{id}/activity | VIEW_ACTIVITY | 对象 Activity（全角色） |

### 3.3 Query/过滤/排序/分页

cluster=Cluster code（经 code_key 大小写不敏感精确；非法 422；不存在→空）；cluster_id=UUID（非 UUID 422）；type=BARE_METAL|VIRTUAL_MACHINE；role/status=枚举精确；q=hostname 大小写不敏感子串 ILIKE；deleted=exclude|include|only（include/only 需 VIEW_DELETED 否则 403）；page≥1 默认1；page_size 1–100 默认20；sort∈{hostname(按 hostname_key),resource_type,role,status,created_at,updated_at} 默认 created_at；order asc|desc 默认 desc；附 id 升序稳定；非法 422。响应 {items,page,page_size,total}。

### 3.4 请求体语义

POST：cluster(必填, UUID 或 code)、hostname(必填)、resource_type(必填)、role(可选默认 OTHER)、status(可选默认 UNKNOWN)、description(可选 null)、metadata(可选默认 {})；未列/只读字段→422。
PATCH（exclude_unset，省略=保持不重置）：version(必填)、hostname(可选，改后重检唯一)、role/status(可选，显式 null→422)、description(可选，显式 null 清空)、metadata(可选，整值替换，显式 null→422)；含 cluster/cluster_id/resource_type/只读→422。

### 3.5 错误语义

| HTTP | code | 触发/details |
| --- | --- | --- |
| 422 | VALIDATION_ERROR | 枚举非法；role/status/resource_type 显式 null；hostname 空/内部空白/控制字符/超长；metadata 非对象；分页/排序非法；PATCH 含不可改字段；cluster 缺失/不存在/已软删→field:cluster |
| 409 | CONFLICT{unique_conflict, field:"hostname"} | 同 Cluster 重复 hostname（创建）/改名冲突/恢复冲突；并发由部分唯一兜底 |
| 409 | CONFLICT{not_deleted} | 对未删对象 restore |
| 409 | CONFLICT{dependency_deleted, conflicts:[{object_type:"cluster",object_id}]} | 恢复时所属 Cluster 仍软删 |
| 409 | CONFLICT{reference_exists, references} | 删除 Resource 被引用（当前空集，机制级） |
| 409 | VERSION_CONFLICT{current_version} | 乐观锁过期 |
| 404 | NOT_FOUND | 不存在；或已软删且无 VIEW_DELETED |
| 403/401 | FORBIDDEN{reason}/AUTH_REQUIRED | 缺权限/CSRF；无会话 |

校验顺序同 F003：401→403→body(422)→可见性(404)→版本(409)→引用/依赖(409)→写入。cluster 不存在/已软删按 422（PROPOSED，交 CONTRACT 定稿）。

### 3.6 并发/Audit/Activity

乐观锁条件 UPDATE version+1 WHERE version=:expected，rowcount=0→404/409，无静默重试。Audit 四 action 同 Session 同 commit，回滚不留痕；白名单快照 {cluster_id,hostname,resource_type,role,status,description,metadata}；object_type="resource"。Activity 按 (object_type,object_id) 过滤 created_at 升序、同刻 id 升序；全角色只读。

## 4. 数据库影响（交 DATABASE Gate；不建 BareMetalDetail/VM Detail）

### 4.1 resources 表要点

| 列 | 类型 | 空 | 默认 | 约束（草案） |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_resources |
| cluster_id | UUID | NOT NULL | — | FK fk_resources_cluster_id_clusters→clusters.id ON DELETE RESTRICT |
| hostname | varchar(253) | NOT NULL | — | CHECK 非空/trimmed/无空白控制/长度；存小写 |
| hostname_key | varchar(253) | NOT NULL | — | CHECK hostname_key=translate(btrim(hostname),'ABC…','abc…')+非空/长度 |
| resource_type | varchar(32) | NOT NULL | — | CHECK IN ('BARE_METAL','VIRTUAL_MACHINE') |
| role | varchar(16) | NOT NULL | 'OTHER' | CHECK 7 值 |
| status | varchar(16) | NOT NULL | 'UNKNOWN' | CHECK 4 值 |
| description | text | NULL | — | |
| metadata | jsonb | NOT NULL | '{}'::jsonb | CHECK jsonb_typeof='object'（ORM 属性 meta） |
| version | integer | NOT NULL | 1 | CHECK >=1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

禁内部空白/控制字符的 DB CHECK 为 ASCII 范围 backstop（沿用 F003 I-6 已知差异），应用负责 Unicode Cc/Cf。

### 4.2 唯一性与索引

**uq_resources_cluster_id_hostname_key UNIQUE (cluster_id, hostname_key) WHERE deleted_at IS NULL**（部分唯一）：同 Cluster 未删除唯一、软删可重用、跨 Cluster 允许；与 F003 code_key 全量唯一对照，不可互换。索引：ix_resources_cluster_id、ix_resources_resource_type、ix_resources_role、ix_resources_status、ix_resources_deleted_at。pg_trgm/GIN 不在 F004 引入（F013）；**F013 errata**：已由 `0013_search_indexes` 建 `ix_resources_hostname_trgm`。索引最终集合交 Database 裁定（已完成，见 docs/database/f013-search-index.md）。

### 4.3 触发器与迁移

不可改字段 DB 兜底：trg_resources_immutable_fields（BEFORE UPDATE，cluster_id/resource_type 变更抛错），对应应用 422。迁移 0004_resources：down_revision="0003_clusters_audit"，单一 head；up 建表+约束+索引+触发器，down 对称逆序；真库 up/down/up。生产回滚按 F001 全库备份。

### 4.4 数据完整性对应表

| 规则 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §7/§27 hostname 唯一 | POST/PATCH /resources | 部分唯一 (cluster_id,hostname_key) WHERE deleted_at IS NULL + CHECK | 归一化键；冲突 409 unique_conflict | 并发同名唯一索引兜底；软删释放 | 真实 PG |
| §6/§4.1 cluster 归属 | POST/PATCH | FK→clusters RESTRICT | 前置校验存在且未软删否则 422 | Cluster 软删不删行 | 真实 PG |
| §6 不可改 | PATCH | 触发器 trg_resources_immutable_fields | PATCH 含 cluster/resource_type→422 | 软删/恢复不受影响 | 真实 PG |
| §6 枚举/默认 | POST | CHECK+DEFAULT | 省略默认；显式 null→422 | 枚举扩展走迁移 | 真实 PG |
| §21 软删/恢复 | ORM select；DELETE/RESTORE | deleted_at | 默认过滤；恢复重检唯一/依赖 | 不级联；cluster 软删→dependency_deleted | 真实 PG |
| §21 引用检查 | DELETE cluster | 注册表机制 | F004 注册 cluster←resources | 未删 Resource 阻止删 Cluster | 真实 PG |
| §22 Audit | Service 写路径 | append-only audit_logs | 同 Session 同 commit；白名单快照 | 回滚不留 audit | 真实 PG |
| §23 乐观锁 | PATCH/DELETE/restore | version+条件 UPDATE | rowcount=0→404/409 | 真并发 | 真实 PG |

## 5. 验证策略（A1–A13，真实 PG）

A1 同 Cluster 重复 hostname 409、跨 Cluster 201、部分唯一索引断言；A2 软删后同 hostname 201、索引 WHERE 谓词断言；A3 大小写/空白归一化 + hostname_key 与 translate 口径（含非 ASCII 原样）；A4 默认 OTHER/UNKNOWN、role/status 显式 null 422；A5 PATCH cluster/resource_type 422 + DB 触发器；A6 cluster 缺失/不存在/软删→422 field:cluster、hostname 空/内部空白→422；A7 组合过滤 + 分页/排序非法 422；A8 Overview 五要素；A9 默认隐藏软删 + 403、restore not_deleted/unique_conflict/dependency_deleted；A10 四 action 同事务+回滚不留痕+Activity 全角色；A11 权限矩阵；A12 ?q=cn00 ILIKE 命中；A13 D01 引用 + 约束/索引/触发器断言 + 0004 up/down/up。补充：乐观锁两会话并发、并发同 hostname 部分唯一兜底、cluster 引用检查阻断删除、审计快照可序列化、软删过滤覆盖关系加载。

## 6. 技术决策（DR-34–DR-45）

DR-34 Resource 统一实体稳定 UUID（CONFIRMED §4）；DR-35 hostname=btrim+ASCII-only 小写折叠，hostname 存小写展示、hostname_key 内部唯一键，DB translate 不用 lower（PROPOSED §7/D01）；DR-36 (cluster_id,hostname_key) 部分唯一 WHERE deleted_at IS NULL（CONFIRMED+DESIGN）；DR-37 resource_type/role/status varchar+CHECK，role 默认 OTHER、status 默认 UNKNOWN、resource_type 必填，role 显式 null→422（CONFIRMED §6/Q10-A）；DR-38 cluster/resource_type 不可改，PATCH 422+DB 触发器（CONFIRMED+DESIGN）；DR-39 创建 cluster 必须存在且未软删否则 422 field:cluster（PROPOSED）；DR-40 F004 注册 cluster←Resource 引用检查器（PROPOSED §21/DR-30）；DR-41 列表契约 cluster/cluster_id/type/role/status/q+分页/排序+deleted 模式收敛 F003 基线（PROPOSED）；DR-42 响应含嵌套 cluster{id,code,name}（PROPOSED）；DR-43 迁移 0004_resources 对称可逆（PROPOSED）；DR-44 不建 BareMetalDetail/VM Detail，非 Overview 区域占位（CONFIRMED 产品边界）；DR-45 hostname 基础搜索 ILIKE，不引入 pg_trgm/GIN，引入点 F013（PROPOSED）。

## 7. 工作分工

Database：resources Schema/约束/部分唯一/触发器/FK、迁移 0004、索引裁定、hostname 长度字符集。
Backend：models/resource.py、schemas/resource.py、services/resource.py、api/v1/resources.py+router；normalization 增 hostname 函数；注册 cluster 引用检查器；复用 audit/errors/db。
Frontend：Resources 列表（过滤/排序/分页/搜索）、Detail Overview、创建/编辑（version/409/403/422 不静默重试）、ADMIN 已删开关与恢复。
Tester：§5 A1–A13（真实 PG、并发、部分唯一、软删复用、恢复重检、审计同事务回滚）。
Contract：docs/api/F004.md 置 READY，签核 D01 Resource 域字段 + D02 审计/乐观锁。

## 8. 风险与待核对项

交 Database：hostname 长度（PROPOSED 253，可对齐 255）与字符集；ASCII-only 折叠口径；部分唯一索引与 include/only 查询覆盖；不可改字段触发器；FK RESTRICT；metadata object CHECK；0004 真库 up/down/up。
交 Tester：部分唯一在软删/重建/改名行为；恢复依赖（cluster 软删）与唯一重检；并发同 hostname 创建；乐观锁并发；审计同事务回滚；cluster 引用检查端到端。
交 CONTRACT：docs/api/F004.md 置 READY；cluster 缺失/不存在 422（PROPOSED）在 Contract 固定；type 查询参数命名以 §25 示例为准。
待 Product 核对（OPEN §35.3 D01）：hostname 字符集/长度若收紧 ASCII 可能影响命名兼容性，交 Product 在 D01 关闭时核对；本设计不改写业务规则。
跨 Feature 连续性：F004 首次为 cluster 注册引用检查器，F003 cluster 删除行为收窄（有未删 Resource 时禁止删除），属 §21 必然结果。

## 9. 结论与下一步

Status READY FOR DESIGN。无 Blocking Questions。下一步：DATABASE Gate 定稿 docs/database/f004-resource.md；TEST_DESIGN 核对可验证性；CONTRACT 定稿 docs/api/F004.md 并签核 D01 Resource 域字段 + D02 审计/乐观锁；完成后出 READY FOR IMPLEMENTATION。


## 10. 最终设计定稿（CONTRACT Gate 签核）

- **状态**：`READY FOR IMPLEMENTATION`
- **签核**：Architect，2026-10-08；Contract：docs/api/F004.md v1（READY）
- **核对版本**：requirements-v3.md revision 3；F004 product.md（A1–A13）；architecture DR-34–DR-45；docs/database/f004-resource.md v1（Database 2026-10-08）；docs/features/F004/test-report.md TD-1（Tester 2026-10-07）；d01-conventions.md v3；f003-cluster.md v2；api/F003.md v2；api/F002.md v1。
- **DB I-1 关闭**：hostname 长度裁定 1–253（FQDN 表示上限）；字符集宽松（非空、无首尾/内部空白、无 Cc/Cf、允许 Unicode）；折叠仅 ASCII A-Z→a-z（应用/DB 同口径，禁用 str.lower()/lower()）；DB-D37 由 PROPOSED 落为 DESIGN。D01 §5.3 固化。无需 Product 核对。
- **一致性**：A1–A13 与架构/DB-D33–D44/TD-1 逐项核对通过；hostname 部分唯一、不可改字段触发器、cluster 引用检查、CONFLICT/VERSION_CONFLICT、枚举/默认、metadata、time/省略语义一致。
- **D01/D02 签核**：D01 Resource 域字段契约（键列/长度/字符集/部分唯一/枚举默认/422/稳定 ID/时间）与 D02 审计一致性/乐观锁部分（复用 F003 §8 / F002 §6）签核完成。
- **实现分工**：Backend（models/resource.py、schemas/resource.py、services/resource.py、api/v1/resources.py+router；normalization.py 增 hostname 函数 ASCII-only 禁用 str.lower()；注册 cluster←resources 引用检查器；复用 audit/errors/db；迁移 0004 由 Database 设计）；Frontend（Resources 列表/详情/表单/已删恢复）；Tester（§5 A1–A13、TD-1 B1–B46）。
- **遗留（不阻塞实现，TEST Gate 前闭合）**：F004-TD-1-01（TD-1 §0/B5 的 hostname_key 折叠方向笔误，应为小写 translate(...'ABC…','abc…')），由 Tester 升 TD-2 修正后方可执行 B5。
