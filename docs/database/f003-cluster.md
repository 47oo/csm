# F003 Cluster 管理与持久化横切首落地 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-06）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§5、§21、§22、§23、§27、§35.3 D01/D02）；docs/features/F003/product.md；docs/features/F003/architecture.md（§4、§8、DR-17–DR-33）；docs/database/f001-baseline.md v1（DB-D1–D12）；docs/database/f002-auth.md v1（DB-D13–D19）
- **覆盖**：clusters / audit_logs 实体、约束、索引；迁移 0003_clusters_audit；四项交核裁定；Backend 可依赖保证与测试项。不覆盖 F004+ 关系表/通用部分唯一、F015 完整审计查询、docs/api/F003.md（Architect）。

## 1. 设计决策汇总

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D20 | clusters.id/audit_logs.id 用 PG 原生 UUID gen_random_uuid()（沿用 DB-D13） | DESIGN |
| DB-D21 | clusters.status varchar(16)+CHECK（不用原生 ENUM） | DESIGN |
| DB-D22 | Cluster 存展示列 code + 归一化键 code_key=upper(btrim(code))；code_key **全量唯一（无 deleted_at 谓词）** | CONFIRMED（§5/§21） |
| DB-D23 | code 字符集按 D01：去首尾空白、非空、无空白/控制字符、char_length≤64；大小写不敏感由 code_key 承载（**不含 ASCII 限制，保留中文**——见 §8 I-1） | DESIGN（D01） |
| DB-D24 | name 允许中文、保留展示，trim/非空/无控制字符、≤255、无唯一 | CONFIRMED（§5/§4.1） |
| DB-D25 | metadata jsonb NOT NULL DEFAULT '{}' + jsonb_typeof='object' CHECK | DESIGN |
| DB-D26 | deleted_at 软删列 + ix_clusters_deleted_at；SoftDeleteMixin 仅用于业务对象 | DESIGN（D02） |
| DB-D27 | audit_logs 多态 (object_type, object_id) 无对象 FK；operator_user_id FK→users.id ON DELETE RESTRICT（可空）+ operator_username 快照 | CONFIRMED（§22/§21） |
| DB-D28 | audit_logs append-only 由 DB 行级触发器强制；无 deleted_at、无 version | DESIGN（§22/§6） |
| DB-D29 | audit_logs before/after JSONB 至少一方非空；非空时必须 object | DESIGN（§22） |
| DB-D30 | pg_trgm GIN 不在 F003 引入；F004/F013 评估后追加（扩展已由 0001 启用） | DESIGN（§26/plan F013） |
| DB-D31 | 迁移 0003_clusters_audit 追加，对称可逆、单一 head、真库 up/down/up | DESIGN（DB-D7） |
| DB-D32 | clusters.updated_at 应用维护无触发器；code 不可改由 DB 触发器 trg_clusters_code_immutable + 应用 422 双重保证 | CONFIRMED（§5）+ DESIGN |

## 2. clusters 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_clusters |
| code | varchar(64) | NOT NULL | — | 展示列(trim)；ck_clusters_code_not_blank/trimmed/no_ws_control/length |
| code_key | varchar(64) | NOT NULL | — | ck_clusters_code_key_matches(code_key=upper(btrim(code)))+not_blank/length |
| name | varchar(255) | NOT NULL | — | ck_clusters_name_not_blank/trimmed/no_control |
| status | varchar(16) | NOT NULL | 'ACTIVE' | ck_clusters_status IN ('ACTIVE','INACTIVE') |
| description | text | NULL | — | |
| metadata | jsonb | NOT NULL | '{}'::jsonb | ck_clusters_metadata_object |
| version | integer | NOT NULL | 1 | ck_clusters_version >=1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

唯一/索引：**uq_clusters_code_key UNIQUE(code_key) 全量唯一（含软删）** 实现 §5 code 不重用 + §27 DB 兜底；ix_clusters_status；ix_clusters_deleted_at；不建 pg_trgm GIN（DB-D30）。

code 不可改（DB-D32）：触发器 trg_clusters_code_immutable 在 NEW.code/code_key IS DISTINCT FROM OLD 时抛异常；应用层 PATCH code 仍返 422。软删/恢复仅改 deleted_at/version 不受影响。

## 3. audit_logs 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_audit_logs |
| operator_user_id | UUID | NULL | — | FK fk_audit_logs_operator_user_id_users → users.id ON DELETE RESTRICT |
| operator_username | varchar(64) | NOT NULL | — | 快照；ck_audit_logs_operator_username_not_blank |
| action | varchar(16) | NOT NULL | — | ck_audit_logs_action IN ('CREATE','UPDATE','DELETE','RESTORE') |
| object_type | varchar(64) | NOT NULL | — | 非空 |
| object_id | UUID | NOT NULL | — | 多态，无对象 FK |
| before_data | jsonb | NULL | — | 非空时必须 object |
| after_data | jsonb | NULL | — | 非空时必须 object |
| created_at | timestamptz | NOT NULL | now() | UTC |

约束/索引：ck_audit_logs_at_least_one_snapshot（before IS NOT NULL OR after IS NOT NULL）；ix_audit_logs_object_type_object_id(object_type,object_id,created_at)；ix_audit_logs_operator_user_id；ix_audit_logs_created_at。**无 deleted_at、无 version**。

append-only：DB 行级触发器 trg_audit_logs_append_only（BEFORE UPDATE OR DELETE 抛 restrict_violation）；不拦截 TRUNCATE/DROP（测试 teardown/downgrade 可用）；§22 归档属独立变更需显式 DISABLE。

多态与引用：object_type/object_id 无对象 FK（审计须在对象删除/恢复/名称复用/用户停用后继续存在，§21/§22）；operator_user_id RESTRICT 保证持有审计的用户不可物理删除；operator_username 快照保留历史身份；系统/CLI 操作用空 operator_user_id + 非空快照。

## 4. 四项交核裁定

① **code_key 全量唯一 vs 通用部分唯一**：Cluster code 全量唯一（含软删，永久预约，恢复无 code 冲突）；通用对象（hostname/Network/Pool/Service/Interface name）部分唯一 WHERE deleted_at IS NULL（可复用，恢复须重查冲突）。两者不可互换。
② **pg_trgm GIN**：F003 不引入（低基维表；§26 为建议；plan F013 定为引入点）；`q` 用 ILIKE/contains，正确性不依赖索引；需要时追加迁移不改表结构。
③ **audit append-only**：DB 触发器强制（F001 DB-D11 允许 Compose 单角色，REVOKE 对 owner 不可靠；触发器跨角色一致）。
④ **软删过滤**：DB 只提供列/索引，可见性语义归 ORM；with_loader_criteria/do_orm_execute 仅作用于 SoftDeleteMixin 模型（users/audit_logs 无 deleted_at，不得全局注入）；F004+ 关系加载须验证 criteria 传播；不引入 RLS。

## 5. 迁移 0003_clusters_audit

revision="0003_clusters_audit"、down_revision="0002_users_sessions"；单一 head。upgrade：先建 clusters（+索引+code 不可改触发器），后建 audit_logs（FK→users 需 0002；+索引+append-only 触发器）。downgrade：逆序 drop 触发器/函数/索引/表。命名按 DB-D6，约束/触发器名显式全给（autogenerate 不识别 CHECK/触发器，手写）。新表无回填，迁移只建 Schema。
**downgrade 数据安全策略**：部署后表内已有 Cluster 与持续保留的 Audit（§22），downgrade 会破坏审计历史；生产回滚不得用 downgrade，须以 F001 全库备份恢复；downgrade 仅用于开发/测试 up/down/up。结构可逆≠数据可逆。

## 6. 数据完整性对应表

| 规则 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §5/§27 | code 唯一 | uq_clusters_code_key 全量 + ck_*_matches | 归一化生成 code_key；冲突 409 unique_conflict | 并发同名 UNIQUE 兜底；软删不释放 | V-DB-9/10 |
| §5 | code 不可改 | 触发器 trg_clusters_code_immutable | PATCH code→422 | 软删/恢复不改 code | V-DB-11 |
| §5/§4.1 | code 格式 | ck_clusters_code_* | API/导入同规则 | — | V-DB-11 |
| §4.1/§5 | name 规范 | ck_clusters_name_* | 应用 trim 写入 | 无唯一 | V-DB-12 |
| §5 | status | ck_clusters_status 默认 ACTIVE | 枚举映射 | 切换不级联 | V-DB-13 |
| §4.1 | metadata | ck_clusters_metadata_object 默认 {} | 整值替换 | — | V-DB-14 |
| §23 | 乐观锁 | version + ck>=1 | 条件 UPDATE rowcount=0→409 | 真并发 | V-DB-15 |
| §21 | 软删/恢复 | deleted_at | 默认过滤、ADMIN 恢复、依赖重检 | 恢复无 code 冲突；不级联 | V-DB-9 |
| §22 | Audit 记录 | action/at_least_one/object CHECK；FK RESTRICT | 同 Session 同 commit；白名单快照 | 回滚连 Audit 回滚 | V-DB-16 |
| §22 | Audit 不可变 | 触发器 append-only | 无修改/删除入口 | 持续保留 | V-DB-16 |
| §21/§22 | 审计不随对象删除 | 无对象 FK | Activity 按 (type,id) 查 | 对象删除后审计仍在 | V-DB-16 |
| §27 | 真实 PG | 上列全部 | — | — | V-DB-8 up/down/up |

## 7. Backend 可依赖保证与测试项

保证：code_key 全量唯一且 code 不可改；code/name trim/非空/无空白或控制字符/长度由 CHECK 保证；status 仅 ACTIVE/INACTIVE 默认 ACTIVE；metadata 必为 object 默认 {}；version ≥1 默认 1；audit 至少一方快照、action 受 CHECK、operator FK RESTRICT、UPDATE/DELETE 被触发器拒绝；audit 无 deleted_at/version 不随对象删除；0003 有真实 downgrade。
计划测试项（真实 PG）：V-DB-8 up/down/up；V-DB-9 重复 code（含大小写/空白）与软删后重建拒绝；V-DB-10 code_key 不一致拒绝；V-DB-11 code 空/空白/控制/超长拒绝 + UPDATE code 被触发器拒绝；V-DB-12 name 空/控制/带首尾空白拒绝；V-DB-13 非法 status 拒绝 + 默认 ACTIVE；V-DB-14 非 object metadata 拒绝 + 默认 {}；V-DB-15 version 默认 1/<1 拒绝；V-DB-16 audit 非法 action/双空快照/非 object 快照拒绝 + UPDATE/DELETE 抛异常 + 有审计用户 DELETE 被 RESTRICT + TRUNCATE 可用；V-DB-17 约束/索引/触发器/函数存在断言。

## 8. 未验证项与风险（含交核事项）

- **I-1（MEDIUM，交 Architect，契约对齐）**：architecture DR-24 建议 code ASCII 正则 `^[A-Z0-9][A-Z0-9._-]{0,63}$`，会拒绝 §5 示例中的中文集群标识（山河3/亘聪集群）。本设计按 D01 采用宽松规则（trim/非空/无空白控制字符/≤64，大小写不敏感由 code_key 承载），保留中文可能。需 Architect 在 docs/api/F003.md 的 code 校验与本设计一致；若 Product 确认 code 仅 ASCII 则改严格正则（无数据，迁移低成本）。**属 §35.3 D01 专业设计输入，非新业务规则。**
- I-2（LOW）：code varchar(64)/name varchar(255)/operator_username varchar(64) 长度口径需 API 契约镜像。
- I-3（LOW）：触发器受控禁用流程写入运维/迁移说明。
- I-4（NOTE）：pg_trgm GIN 延后，F004/F013 决定。
- I-5（NOTE）：软删可见性非 DB 保证，with_loader_criteria 按 Mixin 作用域注入，列 Backend 集成测试。
- 只读签核，全部为计划验证无 PASS。
