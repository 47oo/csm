# F004 Resource 核心登记 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-08）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§6、§7、§18、§21–§23、§25、§27、§35.3 D01/D02）；docs/features/F004/product.md；docs/features/F004/architecture.md（§4、§8、DR-34–DR-45）；docs/database/f001-baseline.md v1（DB-D1–D12）；docs/database/f002-auth.md v1（DB-D13）；docs/database/f003-cluster.md v2（模式参考）；docs/architecture/d01-conventions.md v2
- **覆盖**：resources 表、约束、索引、触发器、迁移 0004；六项交核裁定；Backend 可依赖保证与测试项。不覆盖 F005/F006 明细、F013 trgm、docs/api/F004.md（Architect）。

## 1. 设计决策汇总（DB-D33–DB-D44）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D33 | resources.id 用 PG 原生 UUID gen_random_uuid()（沿用 DB-D13） | DESIGN |
| DB-D34 | resource_type/role/status varchar+CHECK（不用原生 ENUM）；resource_type 无默认（必填），role 默认 OTHER，status 默认 UNKNOWN | CONFIRMED（§6）+DESIGN |
| DB-D35 | 物理列名 metadata（ORM 属性 meta），jsonb NOT NULL DEFAULT '{}' + jsonb_typeof='object' CHECK | DESIGN |
| DB-D36 | hostname 存 trim 后 ASCII-only 小写展示值；hostname_key=translate(btrim(hostname),'A-Z','a-z')，CHECK 锁定口径，**不用 lower()**（沿用 F003-REV-1，locale 无关非 ASCII 原样） | CONFIRMED（§7/D01）+DESIGN |
| DB-D37 | hostname/hostname_key 长度 ≤253（Unicode code point），字符集按 D01 宽松规则 + ASCII 范围空白/控制 backstop | DESIGN（长度 PROPOSED，待 D01/CONTRACT 核对） |
| DB-D38 | uq_resources_cluster_id_hostname_key UNIQUE(cluster_id, hostname_key) WHERE deleted_at IS NULL 部分唯一（同 Cluster 未删唯一、软删可重用、跨 Cluster 允许） | CONFIRMED（§7/§21）+DESIGN |
| DB-D39 | fk_resources_cluster_id_clusters → clusters.id ON DELETE RESTRICT | DESIGN |
| DB-D40 | 不可改字段 DB 兜底触发器 trg_resources_immutable_fields（cluster_id/resource_type 变更抛错），应用层 422 | CONFIRMED（§6）+DESIGN |
| DB-D41 | 索引：ix_resources_cluster_id/resource_type/role/status/deleted_at/hostname_key；**不引入 pg_trgm GIN**（沿用 DB-D30，F013） | DESIGN |
| DB-D42 | 迁移 0004_resources（down_revision=0003_clusters_audit），对称可逆、单一 head、真实 PG up/down/up | DESIGN（DB-D7） |
| DB-D43 | version int≥1 默认 1；created_at/updated_at timestamptz NOT NULL now()、updated_at 应用维护无触发器；deleted_at 软删列 | DESIGN |
| DB-D44 | cluster←resource 引用检查由应用层注册；DB 仅 FK RESTRICT 保证物理删除完整性 | DESIGN（§21，DR-40） |

## 2. resources 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK pk_resources |
| cluster_id | UUID | NOT NULL | — | FK fk_resources_cluster_id_clusters → clusters.id ON DELETE RESTRICT；ix_resources_cluster_id |
| hostname | varchar(253) | NOT NULL | — | ck_resources_hostname_not_blank/trimmed/no_ws_control/length/ascii_lower |
| hostname_key | varchar(253) | NOT NULL | — | ck_resources_hostname_key_matches/not_blank/length |
| resource_type | varchar(32) | NOT NULL | — | ck_resources_resource_type IN ('BARE_METAL','VIRTUAL_MACHINE') |
| role | varchar(16) | NOT NULL | 'OTHER' | ck_resources_role IN (COMPUTE,LOGIN,MANAGEMENT,STORAGE,SERVICE,GPU,OTHER) |
| status | varchar(16) | NOT NULL | 'UNKNOWN' | ck_resources_status IN (IDLE,ALLOC,DOWN,UNKNOWN) |
| description | text | NULL | — | |
| metadata | jsonb | NOT NULL | '{}'::jsonb | ck_resources_metadata_object(jsonb_typeof='object')；ORM 属性 meta |
| version | integer | NOT NULL | 1 | ck_resources_version >=1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；updated_at 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

关键 CHECK：
- `ck_resources_hostname_ascii_lower`：`hostname = translate(hostname,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')`（落实 §7 "存小写"，非 ASCII 原样）。
- `ck_resources_hostname_key_matches`：`hostname_key = translate(btrim(hostname),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')`。
- 因已禁内部/首尾空白且强制 ASCII 小写，实际 hostname_key = hostname；key 列为刻意冗余（口径锁+唯一载体）。
- 禁内部空白/控制字符的 CHECK 为 ASCII 范围 backstop（沿用 F003 I-6 已知差异），应用负责 Unicode Cc/Cf。

## 3. 唯一性与索引

- `uq_resources_cluster_id_hostname_key UNIQUE(cluster_id, hostname_key) WHERE deleted_at IS NULL`（部分唯一）。
- 与 F003 uq_clusters_code_key 全量唯一差异：code 软删不重用；hostname 软删可重用；恢复置空 deleted_at 重新进入索引，冲突由部分唯一直接拒绝。
- 索引：ix_resources_cluster_id、ix_resources_resource_type、ix_resources_role、ix_resources_status、ix_resources_deleted_at、ix_resources_hostname_key。cluster_id 全量 btree 必须保留（FK RESTRICT 校验父删除时不尊重部分索引谓词）。不建 pg_trgm GIN（DB-D30，引入点 F013）。include/only 无专用索引，延后。

## 4. 触发器

`resources_immutable_fields()` + `trg_resources_immutable_fields`（BEFORE UPDATE FOR EACH ROW）：NEW.cluster_id IS DISTINCT FROM OLD.cluster_id OR NEW.resource_type IS DISTINCT FROM OLD.resource_type 时 RAISE ERRCODE='restrict_violation'。软删/恢复仅改 deleted_at/version 不受影响；hostname/role/status/description/metadata 可改。

## 5. 迁移 0004_resources

revision="0004_resources"、down_revision="0003_clusters_audit"，单一 head。upgrade：建表→CHECK/PK/FK→部分唯一+索引→触发器/函数；downgrade 逆序 drop。约束/触发器名按 DB-D6 显式手写（autogenerate 不识别 CHECK/触发器/表达式索引）。新表无回填。生产回滚用 F001 全库备份（结构可逆≠数据可逆）。

## 6. 数据完整性对应表

| 规则 | 作用域 | DB 保证 | 业务层保证 | 并发/生命周期 | 验证 |
| --- | --- | --- | --- | --- | --- |
| §7/§27 hostname 唯一 | POST/PATCH | 部分唯一+key CHECK | 归一化键；冲突 409 unique_conflict | 并发同名部分唯一兜底；软删释放；恢复冲突被索引拒 | V-DB-19/20/21 |
| §6/§4.1 cluster 归属 | POST | FK RESTRICT | 校验存在且未软删否则 422 | Cluster 软删不删行 | V-DB-25 |
| §6 不可改 | PATCH | trg_resources_immutable_fields | 422 | 软删/恢复不受影响 | V-DB-24 |
| §6 枚举/默认 | POST | CHECK+DEFAULT+NOT NULL | 省略默认；显式 null→422 | 枚举扩展走迁移 | V-DB-22 |
| §4.1 metadata | POST/PATCH | object CHECK+默认{} | 整值替换 | — | V-DB-23 |
| §21 软删/恢复 | DELETE/RESTORE | deleted_at+部分唯一 | 默认过滤；恢复重检唯一/依赖 | 不级联；cluster 软删→dependency_deleted | V-DB-19 |
| §21 引用检查 | DELETE cluster | 注册表机制（非 DB） | 未删 Resource 阻止删 Cluster | — | V-DB-25 |
| §23 乐观锁 | PATCH/DELETE/restore | version CHECK+条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-22 |
| §22 Audit | Service 写路径 | 复用 audit_logs（0003） | 同 Session 同 commit；object_type='resource' | 回滚不留痕 | F003 已验 |

## 7. Backend 可依赖保证与测试项

保证：cluster_id/resource_type 不可改；部分唯一与 translate 同口径；hostname 存 trim+ASCII 小写、key CHECK 一致；枚举合法值、role/status 默认、resource_type 必填；metadata object 默认 {}；version≥1 默认 1；FK RESTRICT 物理删除完整；hostname ILIKE 无索引（正确性保证）；0004 有真实 downgrade。
计划测试项（真实 PG）：V-DB-18 up/down/up；V-DB-19 部分唯一（同 cluster 冲突/跨 cluster 允许/软删后重建/恢复冲突）；V-DB-20 直接插入非归一化被 CHECK 拒、key 不一致拒；V-DB-21 多码位 Unicode 按 ASCII-only 原样且 key 与 translate 一致；V-DB-22 非法枚举/默认值/version/NOT NULL；V-DB-23 非 object metadata 拒+默认 {}；V-DB-24 UPDATE cluster_id/resource_type 被触发器拒、其它字段放行；V-DB-25 物理 DELETE 有 Resource 的 cluster 被 RESTRICT 拒；V-DB-26 约束/索引/触发器/部分唯一谓词存在断言；V-DB-27 hostname 253 通过/254 拒；V-DB-28 resources 无 pg_trgm GIN 断言。

## 8. 未验证项与风险

- I-1（MEDIUM，交 Architect/CONTRACT）：hostname 长度 253（PROPOSED）与字符集口径须在 D01/CONTRACT 镜像；若 Product 收紧 ASCII-only（§35.3 D01）需按变更控制评审命名兼容性。非本 Gate 阻塞。
- I-2（LOW）：hostname_key 在强制小写+trim 下恒等于 hostname，属刻意冗余，实现不得省略任一 CHECK。
- I-3（LOW，交 Backend）：归一化函数必须 ASCII-only，禁用 str.lower()（ß/İ 映射不一致会触发 CheckViolation）；列入代码 Review。
- I-4（LOW，已知差异，沿用 I-6）：no_ws_control 为 ASCII 范围 backstop，弱于应用 Unicode Cc/Cf；API 由应用拦截。
- I-5（NOTE，交 Tester）：软删可见性为 ORM 责任（F003 I-5），relationship 加载须验证 criteria 传播。
- I-6（NOTE）：resources 属生产表，downgrade 数据不可逆，生产回滚用全库备份。
- 只读签核，全部为计划验证无 PASS。

## 9. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-08 | 初次签核（DB-D33–D44）；resources 首次建表、部分唯一、触发器、迁移 0004；6 项交核裁定。 |
