# F003 Cluster 管理与持久化横切首落地 — ARCHITECTURE 阶段报告

- **Task**：F003（FEATURE，P0，M2）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-06；协调器核验后持久化）
- **Basis**：requirements-v3.md revision 3（§4、§4.1、§5、§19、§21–§23、§25、§27–§28、§31、§35.2 Q02-A/Q07-A/Q10-A/Q10-B、§35.3 D01/D02）；F003 product.md（A1–A11）；F001 工程基线+DB-D1–D12；F002 错误信封/权限/操作者上下文/DR-11；docs/api/F002.md；docs/database/f002-auth.md（DB-D13 UUID 已落地，F003 沿用）；plan_revision 4 F003 条目。
- **结论属性**：设计输入，交 DATABASE/TEST_DESIGN；Contract 草案供 CONTRACT 定稿，本阶段不放行编码。

## 1. 方案摘要

### 1.1 Cluster 实体与 API

- `/api/v1/clusters` CRUD + 恢复 + Activity；列表组合过滤（status/code/q）、排序、分页；默认含未删除停用集群。
- 详情交付基础字段；§19 关联区域（Resources/Networks/IPs/VMs/Services）随 F004+ 接入，本 Feature 预留结构不虚构数据。
- 错误信封/401/403/409/权限/操作者上下文复用 F002 Contract，仅新增 `CONFLICT`(409) 用于唯一性/引用/恢复冲突。
- 前端：Clusters 列表+详情基线、状态过滤、ADMIN 已删除查看/恢复入口；Loading/Success/Empty/Error 齐全。

### 1.2 持久化横切基座（首次落地，后续复用）

| 能力 | 设计 |
| --- | --- |
| 软删与默认过滤 | deleted_at 列 + SoftDeleteMixin + Session 级 do_orm_execute/with_loader_criteria 注入 deleted_at IS NULL；execution_options(include_deleted=True) 显式绕过 |
| 已删除可见/恢复 | 查询参数 deleted=exclude\|include\|only（include/only 需 VIEW_DELETED）；恢复端点 POST /clusters/{id}/restore（RESTORE） |
| 引用检查框架 | object_type→checkers 注册表；删除前检查未删除引用，命中 409 CONFLICT+references；不隐式级联；F003 中 cluster 引用集为空，F004+ 注册 |
| Audit 表与写路径 | 独立 audit_logs 表；Service 层显式 AuditService.record，同一 Session 同一次 commit；before/after JSON 快照；operator 取 request.state.operator→operator_user_id(users.id)+operator_username 快照 |
| 端到端乐观锁 | version 列；条件 UPDATE WHERE id AND version=:expected SET version=version+1；rowcount=0→404 或 409 VERSION_CONFLICT(current_version)；无静默重试 |
| 稳定 ID | 沿用 PG 原生 UUID gen_random_uuid()（DB-D13） |
| 名称归一化 | 共享 app/services/normalization.py；Cluster code 归一化键列+全量唯一，name 仅 trim/校验不唯一 |

### 1.3 D01 共享约定基座（建议单一权威文档 docs/architecture/d01-conventions.md，F003 CONTRACT 签核）

- **稳定 ID**：业务对象 PK = PG UUID gen_random_uuid()；内部关联用 UUID，不用字符串拼接（§4）。
- **时间契约**：timestamptz/UTC 存储；接口 ISO-8601 带 +00:00；前端按 DISPLAY_TIMEZONE 展示（默认 UTC）。
- **单位/数值**：`*_mb`=MiB、`*_gb`=GiB（整数）；未知=null 不以 0 表示；integer 共用上限 0..2147483647，各域收窄（F005/F006）。
- **nullable/PATCH 省略语义**：默认仅创建省略时生效；更新省略=保持原值不重置；Pydantic exclude_unset；显式 null 仅清空 nullable，对必填/nullable 违规→422；metadata 整值替换。
- **必填**：Cluster 创建必填 code/name；status 省略默认 ACTIVE；description/metadata 可选。
- **名称归一化口径**：

| 对象 | 唯一范围 | 大小写 | 内部空白 | 归一化键 | 删除后复用 |
| --- | --- | --- | --- | --- | --- |
| **Cluster code** | 全局（含软删） | 不敏感 | 不允许 | code_key=upper(trim(code))，全量唯一 | 否 |
| **Cluster name** | 无唯一 | 保留 | 保留 | 仅 trim+校验 | n/a |
| Resource hostname | 同 Cluster（未删除） | 小写 | 不允许 | 部分唯一 WHERE deleted_at IS NULL | 是 |
| Interface name | 同 Resource | 区分大小写保留 | 不允许 | 部分唯一 | 是 |
| Network/IPPool/Service name | 各自作用域 | 不敏感保留展示 | 允许单个普通空格 | 归一化键+部分唯一 | 是 |

### 1.4 D02 审计一致性（本 Feature 签核）

- 同事务：AuditService.record 在业务 Service 内同 Session 调用，一并 commit；异常一起 rollback，回滚不留 Audit（§22/A7）。
- 敏感内容不记录：快照走白名单 auditable_fields，排除 password/token/secret；日志脱敏沿用 F002。
- Activity 来源：audit_logs 按 (object_type, object_id) 过滤、created_at 排序；全角色可见（VIEW_ACTIVITY）；完整跨对象审计归 F015。F003 提供 GET /clusters/{id}/activity。

## 2. Implementation Layers

database=true；backend=true；frontend=true；**api_required=true**（有业务 API，需 Contract）。

## 3. API 草案（CONTRACT 定稿路径 docs/api/F003.md）

Base /api/v1；JSON；时间 ISO-8601 UTC；错误信封复用 F002。code_key 为内部列不暴露。

### 3.1 Cluster 响应对象

id(UUID) / code(string) / name(string,允许中文,t trim保留大小写) / status(enum ACTIVE|INACTIVE) / description(string|null) / metadata(object 默认{}) / version(int≥1) / created_at / updated_at / deleted_at(nullable)。均按该 nullable 语义。

### 3.2 Endpoints

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/v1/clusters | READ | 列表：q/code/status/deleted/page/page_size/sort(白名单 code,name,status,created_at,updated_at)/order；deleted=include\|only 需 VIEW_DELETED |
| POST | /api/v1/clusters | WRITE | 创建；201 |
| GET | /api/v1/clusters/{id} | READ | 详情；deleted=true 需 VIEW_DELETED |
| PATCH | /api/v1/clusters/{id} | WRITE | 部分更新；必带 version；code 不可改(422) |
| DELETE | /api/v1/clusters/{id} | DELETE_OBJECT | 软删；必带 version；引用检查 |
| POST | /api/v1/clusters/{id}/restore | RESTORE | 恢复；必带 version；重检唯一性/依赖 |
| GET | /api/v1/clusters/{id}/activity | VIEW_ACTIVITY | 对象 Activity（全角色） |

列表响应 {items, page, page_size, total}；page_size 1–100 默认 20；sort 白名单非法 422。
错误：422 VALIDATION_ERROR；409 CONFLICT{reason: unique_conflict|reference_exists|not_deleted|dependency_deleted, field?, references?, conflicts?}；409 VERSION_CONFLICT{current_version}（复用 F002）；404 NOT_FOUND（不存在或已删无权限）；403。

补充：软删默认过滤对 ORM select 含关系加载；Activity 无审计修改/删除入口。

## 4. 数据库影响（交 DATABASE Gate）

### 4.1 clusters

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_clusters |
| code | varchar(64) | NOT NULL | — | 展示形式(trim) |
| code_key | varchar(64) | NOT NULL | — | CHECK ck_clusters_code_key_format ^[A-Z0-9][A-Z0-9._-]{0,63}$；CHECK ck_clusters_code_key_matches code_key=upper(btrim(code)) |
| name | varchar(255) | NOT NULL | — | CHECK 非空/trim/无控制字符 |
| status | varchar(16) | NOT NULL | 'ACTIVE' | CHECK ck_clusters_status IN ('ACTIVE','INACTIVE') |
| description | text | NULL | — | |
| metadata | jsonb | NOT NULL | '{}' | CHECK jsonb_typeof='object' |
| version | integer | NOT NULL | 1 | CHECK >=1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

索引：**UNIQUE uq_clusters_code_key 全量（不含 deleted_at 谓词）**实现 §5 code 不重用；ix_clusters_status、ix_clusters_deleted_at；q 模糊搜索 pg_trgm GIN 是否 F003 引入交 Database 裁定。

### 4.2 audit_logs

id UUID PK；operator_user_id UUID NULL FK→users.id ON DELETE RESTRICT（系统/CLI 可空）；operator_username varchar(64) NOT NULL（快照保留历史身份）；action varchar(16) CHECK IN (CREATE,UPDATE,DELETE,RESTORE)；object_type varchar(64)；object_id UUID；before_data/after_data jsonb NULL；created_at timestamptz now()；CHECK before_data IS NOT NULL OR after_data IS NOT NULL。索引 ix_audit_logs_object_type_object_id(object_type,object_id,created_at)、ix_audit_logs_operator_user_id、ix_audit_logs_created_at。无 deleted_at，append-only，无修改/删除 API。

### 4.3 code 全量唯一 vs 通用部分唯一

Cluster code 唯一含软删行（永久不重用）；通用对象（hostname/Network/Pool/Service/Interface name）为部分索引 WHERE deleted_at IS NULL（可复用）。两者不可互换。恢复重检：通用对象需重查部分唯一冲突；Cluster 全量唯一故恢复无 code 冲突。

### 4.4 Migration

0003_clusters_audit（down_revision=0002_users_sessions），先 clusters 后 audit_logs；up/down 对称、单一 head、真库 up/down/up（DB-D7）；F003 首业务表，本期空表可 drop，记录数据安全策略。

## 5. 验证策略（A1–A11 → 方法；真实 PG）

A1 code 大小写重复/软删后重建均 409、PATCH code 422、code_key=upper(trim) SQL 校验；A2 name 中文/重名/trim、空/控制字符 422+DB CHECK；A3 默认 ACTIVE、切换不级联、INACTIVE 仍可写/删；A4 列表过滤/排序/分页/模糊与非法排序 422；A5 默认隐藏软删、VIEWER/EDITOR include/only 403、ADMIN 可见；A6 ADMIN 恢复、not_deleted 409、unique_conflict/dependency_deleted 以夹具验证、不级联；A7 四类 action 各写 audit、强制失败回滚不留 audit、Activity 全角色、无敏感字段；A8 两会话并发同 version 一方成功一方 409；A9 改名 id 不变；A10 归一化/稳定 ID 固化 D01 且 Contract 引用；A11 CONTRACT 记录 D01/D02 签核。补充：0003 真库 up/down/up；软删过滤覆盖关系加载；审计快照 JSON 可序列化。

## 6. 技术决策

| ID | 决策 | 类别 |
| --- | --- | --- |
| DR-17 | 业务对象稳定 ID 沿用 PG UUID gen_random_uuid()，不启用 pgcrypto/uuid-ossp | CONFIRMED（DB-D13+§4） |
| DR-18 | 软删默认过滤 SoftDeleteMixin + Session do_orm_execute/with_loader_criteria，include_deleted 显式绕过 | PROPOSED(D02) |
| DR-19 | deleted=exclude\|include\|only；include/only 需 VIEW_DELETED | PROPOSED(D02) |
| DR-20 | 恢复端点 POST /{resource}/{id}/restore；统一重检、失败 409 CONFLICT；不级联 | PROPOSED(D02) |
| DR-21 | Audit 由 Service 层显式 AuditService.record 写入，同 Session 同 commit（非 flush 事件） | PROPOSED(D02) |
| DR-22 | audit_logs operator_user_id(users.id,RESTRICT)+operator_username 快照；before/after JSONB；append-only | PROPOSED(D02) |
| DR-23 | 端到端乐观锁条件 UPDATE version+1 WHERE version=:expected，rowcount=0→404/409 | CONFIRMED 机制（§23+F002 DR-11） |
| DR-24 | Cluster code 展示列+归一化 code_key=upper(trim)；uq 全量含软删；code 不可改 | CONFIRMED（§5） |
| DR-25 | Cluster name 仅 trim+校验，保留大小写内部空格，无唯一 | CONFIRMED（§5/§4.1） |
| DR-26 | PATCH exclude_unset；省略≠重置；显式 null 仅清空 nullable；不可变/必填 null 或 code 出现→422 | CONFIRMED 语义（§4.1） |
| DR-27 | 时间 timestamptz/UTC、ISO-8601 接口、DISPLAY_TIMEZONE 展示 | CONFIRMED（F001 DR-06/D01） |
| DR-28 | 单位 *_mb=MiB/*_gb=GiB、整数、未知=null；metadata JSONB 整值替换 | PROPOSED(D01) |
| DR-29 | 新增 CONFLICT(409,reason) 覆盖唯一/引用/恢复冲突；VERSION_CONFLICT 复用；信封复用 F002 | PROPOSED(D02) |
| DR-30 | 引用检查框架 object_type→checkers 注册表；F003 cluster 为空集 | PROPOSED(D02) |
| DR-31 | 迁移 0003_clusters_audit | PROPOSED |
| DR-32 | 列表契约基线（分页/排序白名单/过滤/模糊）在 F003 Contract 固化供后续收敛 | PROPOSED |
| DR-33 | Cluster 页面列表+详情基础字段；§19 关联区域占位 F004+ 接入 | PROPOSED |

## 7. 工作分工

- Backend：models/base.py 增 SoftDeleteMixin；models/cluster.py、audit_log.py；core/db.py 注册软删过滤；core/errors.py 增 Conflict；services/normalization.py、audit.py、cluster.py；schemas/cluster.py；api/v1/clusters.py+router 挂载；迁移 0003。
- Frontend：Clusters 列表/详情/创建编辑表单（version、409/403/422 处理不静默重试）、ADMIN 已删除开关与恢复；复用 client.ts。
- Database：§4 Schema/约束/索引/迁移；pg_trgm 引入点、append-only DB 强制裁定。
- Tester：§5 用例（真实 PG、并发、同事务回滚、软删过滤、归一化）。

## 8. 风险与待核对项

交 Database：clusters/audit_logs Schema、code_key 全量唯一 vs 部分唯一、code_key CHECK、metadata object CHECK、pg_trgm GIN 引入点、audit append-only DB 强制、软删过滤对关系加载覆盖。
交 Tester：audit 同事务回滚、乐观锁真并发、软删默认过滤、名称/code 归一化可执行用例与 fixture。
交 CONTRACT：docs/api/F003.md 置 READY，签核 D01 基座+D02 审计一致性。
其它：code 字符集/长度与 name 上限属 D01 专业设计；若影响既有命名兼容性需 Product 核对（§35 D01）。§19 关联区域随 F004+ 接入，F003 不宣称完整 §19。
