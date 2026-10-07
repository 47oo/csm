# F003 Cluster 管理与持久化横切首落地 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据，TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-06
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§4、§4.1、§5、§19、§21–§23、§25、§27–§28、§31、§35.2/§35.3 D01/D02）
  - `docs/features/F003/product.md`（READY FOR ARCHITECT；A1–A11 与边界）
  - `docs/features/F003/architecture.md`（READY FOR DESIGN；§1 方案、§3 API 草案、§4 Schema 草案、§5 验证策略、§6 DR-17–DR-33、§7 分工、§8 交 Tester）
  - `docs/features/F001/test-report.md`（TD-2/TE-1 fixture 约定：DB-D10 独立测试库 + 安全护栏、会话级重建 schema、函数级 savepoint、并发真实提交 `committed_engine`、teardown 排除 `alembic_version`）
  - `docs/features/F002/test-report.md`（TD-2/TE-1/TE-2 认证/权限/错误信封机制级口径：`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`；A4/A6 机制级边界；D-TE-1 入口 CSRF 端口）
  - `docs/api/F002.md` v1（错误信封、权限枚举、`VERSION_CONFLICT`/`FORBIDDEN` 语义、`current_version`）
  - `docs/project/project-plan.yaml` plan_revision 4，F003 条目（已批准，IN_PROGRESS；`current_stage=DATABASE`）
  - `docs/project/implementation-rules.md`（验证与交付）、`AGENTS.md`（数据安全、Git）、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：READY 仅表示 A1–A11 可映射到可观察判据、边界/并发场景可执行、夹具与可验证性已核对；**不表示测试已运行、不批准实现或合并、不表示 T25/T26/T40/T24 完整通过**。F003 为“首个业务对象 + 持久化横切首落地”，完整 T24/T40/T41/T25/T26 跨 Feature 回归归后续 Feature（见 §6）。
- **前置状态说明**：DATABASE Gate（`docs/database/f003-*.md`）与 CONTRACT Gate（`docs/api/F003.md`）**尚未定稿**。本 TD-1 以 `architecture.md` 的 Schema 草案（§4）与 API 草案（§3）、DR-17–DR-33（多数 PROPOSED）为设计输入核对可验证性。TEST 执行前必须以两 Gate 定稿逐项核对；差异处升 TD-2 并注明失效范围（见 §8 OPEN）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-06 | 初版：A1–A11 映射 V1–V14，边界/并发 B1–B42，夹具/环境设计，可验证性检查（§19 占位、D01/D02、A4/A7 边界），不适用项；对 DATABASE/CONTRACT Gate 保留 6 项待复核假设（见 §8）。 |

> 复核基线：`docs/features/F003/architecture.md`（ARCHITECTURE Gate，2026-10-06）。DATABASE/CONTRACT 定稿前的约束名、错误 reason、恢复重检机制均以架构草案为准，标记为待闭合。

### 0. 数据完整性对应表（F003 范围）

仅列 F003 已确认且在实现后需验证的完整性/持久化项；方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列以架构草案 §4 为准（待 DATABASE Gate 定稿核对）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（草案，待 DB Gate） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §5 / §27（code 全局唯一、大小写不敏感、软删不重用、创建后不可改） | POST/PATCH `/clusters` | `clusters.code` 展示列 + `code_key=upper(btrim(code))`；`uq_clusters_code_key` **全量唯一（不含 deleted_at 谓词）**；`ck_clusters_code_key_format`、`ck_clusters_code_key_matches` | `normalization.py` 归一化键；PATCH 出现 code → 422 | 软删行仍占 code；并发创建由唯一约束兜底；恢复无 code 冲突（全量唯一） | V1/V12、B1–B3/B34/B40；计划验证 |
| §5 / §4.1（name 允许中文、可改、不唯一、trim、禁空/控制字符） | POST/PATCH `/clusters` | `clusters.name varchar(255)` + CHECK 非空/trim/无控制字符 | trim + 校验；无唯一比较 | 重名允许；改名不改 id | V2/V9、B4–B7/B33/B39；计划验证 |
| §5（status 默认 ACTIVE、人工维护、不级联、不释放 IP） | POST/PATCH `/clusters` | `status varchar(16) NOT NULL DEFAULT 'ACTIVE'` + `ck_clusters_status IN ('ACTIVE','INACTIVE')` | 省略默认 ACTIVE；切换仅改 status/version/updated_at | 不级联其它对象（F003 无关联表）；INACTIVE 仍可写/删 | V3、B8/B9/B39；计划验证 |
| §21（软删 deleted_at 默认隐藏；ADMIN 查看/恢复；引用检查；不隐式级联；code 不重用） | ORM `select`；DELETE/RESTORE `/clusters/{id}` | `deleted_at timestamptz NULL`；`ix_clusters_deleted_at`；Session 级 `with_loader_criteria` 注入 | `deleted=exclude\|include\|only`；恢复重检唯一性/依赖，失败 409 CONFLICT{reason} | 恢复只恢复自身；不覆盖新对象；引用集 F003 为空（F004+ 注册） | V5/V6/V12、B17–B25/B41；计划验证 |
| §22（Audit 四 action、同事务、不记敏感、持续保留） | Service 层 `AuditService.record`（同 Session 同 commit） | `audit_logs` append-only；无 `deleted_at`；`ck_audit_logs_action IN (CREATE,UPDATE,DELETE,RESTORE)`；`before_data/after_data` JSONB；`ck` 至少一侧非空；`ix_audit_logs_object_type_object_id` | 白名单 `auditable_fields`；`operator_user_id(username 快照)` | 异常一起 rollback，回滚不留 audit；并发不可能产生半行 | V7/V12、B26–B30/B37/B38；计划验证 |
| §23 / §23 CONFIRMED（读全角色、写 EDITOR/ADMIN、删除/看已删除/恢复 ADMIN；乐观锁） | `/clusters*` 各端点 | `members.version integer NOT NULL DEFAULT 1 CHECK >=1`；条件 UPDATE `WHERE id AND version=:expected` | `require_permission` 服务端执行；`rowcount=0`→404/409 `VERSION_CONFLICT` | 两会话同 version 仅一成功；无静默重试 | V8、B31/B32；计划验证 |
| §4（稳定 ID；内部关联用 UUID） | 全部写入 | `id UUID PK DEFAULT gen_random_uuid()`（沿用 DB-D13，不启用 pgcrypto/uuid-ossp） | 关联以 UUID | 改名/code 变更不改 id | V9/V10、B33/B18F；计划验证 |

---

## 1. 验收映射（product.md A1–A11 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`（含 `migrate`/`bootstrap` 一次性服务）；`真实 PG` = 经 Compose `db` 或本机 PostgreSQL 的独立测试库（DB-D10，库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG 测试库（非 SQLite）；`静态` = 仓库/路由清单静态检查；`文档` = 签核记录核对；`前端` = 构建 + client 机制级用例（与真实 API 集成时以入口 Nginx 为准）。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 code 大小写不敏感唯一、软删后不重用、创建后不可改；全量唯一索引兜底 | **V1** code 规则 + **V12** DB 约束 | 后端集成 + 真实 PG | PASS：创建 `N96P` 后创建 `n96p`/` N96P ` → 409 `CONFLICT{reason:unique_conflict, field:code}`；软删后再创建同 code → 409；`PATCH` 请求体含 `code` → 422 `VALIDATION_ERROR`；`code_key=upper(btrim(code))`，`uq_clusters_code_key` 为全量唯一（B34）。FAIL：大小写变体创建成功、软删后 code 可重用、PATCH code 被接受、唯一索引含软删谓词或不存在 |
| A2 name 允许中文/可改/不强制唯一；去首尾空白；空名/控制字符拒绝 | **V2** name 规则 | 后端集成 + 真实 PG | PASS：`name="山河3集群"` 创建成功；两个集群同名成功（无唯一冲突）；`"  N96P集群  "` 落库为 `N96P集群`；空串/纯空白/含 `\x00`/控制字符 → 422；`PATCH name` 成功且 `version` 递增。FAIL：中文被拒、重名冲突、首尾空白留存、空/控制字符被接受 |
| A3 status 默认 ACTIVE、可切换、不级联、INACTIVE 仍可按权限维护 | **V3** status 规则 | 后端集成 + 真实 PG | PASS：创建省略 status → `ACTIVE`；`PATCH status=INACTIVE` 成功且仅 `status/version/updated_at` 变化（无其它对象受影响）；INACTIVE 集群仍可 `PATCH`/`DELETE`（EDITOR 可 PATCH、ADMIN 可 DELETE）。FAIL：默认非 ACTIVE、切换报错、切换级联修改其它对象、INACTIVE 下维护被拒 |
| A4 默认列表含未删除停用集群；状态过滤；组合过滤/排序/分页/模糊搜索 | **V4** 列表契约 | 后端集成 + 前端 | PASS：默认列表返回含 ACTIVE 与 INACTIVE 的未删除集群；`status=INACTIVE` 过滤正确；`q`/`code`/`status` 组合过滤正确；`sort∈{code,name,status,created_at,updated_at}`+`order=asc\|desc` 生效；`page_size∈1..100` 默认 20，`total/page/page_size` 正确；`q` 模糊匹配（如 `gpu07` 前缀/子串）。FAIL：默认漏掉 INACTIVE、过滤/排序/分页错误、page_size 越界被接受 |
| A5 默认隐藏软删；ADMIN 可列出并查看；EDITOR/VIEWER 不可见 | **V5** 软删可见性 | 后端集成 + 前端 | PASS：默认 `deleted=exclude` 隐藏软删行；`deleted=include\|only`：ADMIN（`VIEW_DELETED`）200 可见，EDITOR/VIEWER 403 `FORBIDDEN{reason:permission}`；软删详情 `deleted=true` 需 `VIEW_DELETED`，无权限返回 404（不泄露存在性）；软删过滤覆盖关系加载（B41）。FAIL：默认返回软删行、EDITOR/VIEWER 可见、无权限详情返回 200 或 403 泄露存在性 |
| A6 ADMIN 恢复；code 被重用或依赖仍删除时恢复失败不覆盖；不自动恢复关联 | **V6** 恢复语义 | 后端集成 + 真实 PG | PASS：ADMIN `POST /clusters/{id}/restore`（带 version）→ 200 且 `deleted_at=null`、写 RESTORE audit；对未删除集群恢复 → 409 `CONFLICT{reason:not_deleted}`；`unique_conflict`/`dependency_deleted` 经**注册检查器机制级**返回 409 且不修改目标（B23/B24）；恢复不自动恢复关联对象。FAIL：恢复覆盖新对象、未删除可恢复、冲突未返回 409、隐式级联 |
| A7 四类 action 写 Audit 且同事务；回滚不留痕；Activity 全角色；完整 Audit 限 ADMIN；不记敏感内容 | **V7** Audit/Activity | 后端集成 + 真实 PG + 前端 | PASS：CREATE/UPDATE/DELETE/RESTORE 各产生一行 `audit_logs`，字段 `operator_user_id/operator_username/object_type/object_id/before_data/after_data/created_at` 齐全；强制业务失败后同一事务回滚，`audit_logs` 无残留行（B27）；`GET /clusters/{id}/activity` VIEWER/EDITOR/ADMIN 均 200 且仅含该对象（B28）；快照白名单不含 password/token/secret（B29）；完整跨对象审计查询（`AUDIT_READ`）VIEWER/EDITOR 403（若 F003 交付该端点，否则记机制级/NOT_REQUIRED，见 §4）。FAIL：缺任一 action 审计、回滚留 audit、Activity 越权/跨对象、快照含敏感字段 |
| A8 过期版本更新 409 且无静默覆盖/重试 | **V8** 端到端乐观锁 | 后端集成 + 真实 PG + 前端 | PASS：两个真实会话以同一 `version` 并发 PATCH/DELETE/RESTORE，先提交者 200、后提交者 409 `VERSION_CONFLICT{current_version}`；最终库中为目标版本且无过期覆盖；前端收到 409 明确呈现、不自动重试。FAIL：过期版本被静默覆盖、返回 2xx、无 `current_version`、客户端自动重试 |
| A9 code/name 变更不改对象身份；内部关联用稳定 ID | **V9** 稳定 ID | 后端集成 + 真实 PG | PASS：`PATCH name`（及任何允许字段）后 `id`、`created_at` 不变；`audit_logs.object_id` 恒等于对象 `id`（UUID）；无字符串拼接关联。FAIL：改名生成新 id、审计 object_id 非稳定 ID |
| A10 名称归一化与稳定 ID 固化为共享契约（D01 基座），API 与后续导入共用 | **V10** 归一化/ID 基座核对 | 文档 + 后端集成 | PASS：`normalization.py` 提供 Cluster code 归一化键（`upper(btrim(code))`）并被 Service/查询引用；`id` 为 PG UUID `gen_random_uuid()`；无重复/分叉归一化实现；契约文档记录 code/name 作用域表。FAIL：归一化散落多处、API 与 DB 键不一致、启用 pgcrypto/uuid-ossp |
| A11 D01 基座与 D02 审计一致性在本 Feature CONTRACT 由 Architect/Database 签核 | **V11** 签核核对 | 文档 | PASS：CONTRACT（`docs/api/F003.md`）记录 D01（Cluster 域字段契约、code 归一化键列与全量唯一、稳定 ID、时间契约、nullable/省略语义）与 D02（同事务写路径、乐观锁版本列、错误语义）签核；DATABASE（`docs/database/f003-*.md`）记录 Schema/约束/索引/迁移；均有 Gate 记录且与实现一致。FAIL：任一签核缺失或与实现不符 |
| （数据层支撑 A1/A3/A5/A6/A7） | **V12** Schema / 约束 / 索引 / 迁移 | 真实 PG | PASS：`clusters`/`audit_logs` 建表与 DB Gate 定稿一致；`uq_clusters_code_key` 全量唯一、`ck_clusters_code_key_matches`、`ck_clusters_metadata_is_object`（`jsonb_typeof='object'`）、`ck_clusters_status`、`ck_clusters_version`、name CHECK、`ck_audit_logs_action`、`ck_audit_logs_has_data`、`fk_audit_logs_operator_user_id_users ON DELETE RESTRICT` 均拒绝非法值/引用；索引 `ix_clusters_status`/`ix_clusters_deleted_at`/`ix_audit_logs_object_type_object_id`/`ix_audit_logs_operator_user_id`/`ix_audit_logs_created_at` 存在；迁移 `0003_clusters_audit` up/down/up 对称、单一 head（V13）。FAIL：约束/索引缺失或名称不符、CHECK 允许非法值、FK 误用 CASCADE、迁移不可逆 |
| （数据层支撑） | **V13** 迁移 up/down/up | 真实 PG | PASS：`alembic upgrade head` 建两表、`downgrade 0002_users_sessions` 后两表消失且 `alembic_version` 回退、再 `upgrade head` 收敛 `0003_clusters_audit` 单一 head；F003 为空表（drop 可接受，数据安全策略记录，承接 DB-D7）。FAIL：任一步报错、非对称残留、多头 |
| （A4/A5/A8 前端） | **V14** Cluster 页面基线（前端） | 前端 + Compose | PASS：Clusters 列表分页/排序/过滤/模糊输入可用；Loading/Success/Empty/Error 状态齐全；集群详情展示基础字段、未知值不伪装为空；创建/编辑表单携带 `version`；409 冲突明确提示且不静默重试；ADMIN 已删除开关与恢复入口可见、非 ADMIN 不呈现且服务端仍 403。FAIL：状态缺失、错误伪装空列表、409 静默覆盖、仅前端隐藏而不鉴权 |

---

## 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | code 大小写/首尾空白重复创建 | 创建 `N96P`；分别创建 `n96p`、`n96P`、` N96P ` | 均 409 `CONFLICT{reason:unique_conflict, field:code}`；`clusters.code_key` 归一化为 `N96P` |
| B2 | 软删后重建同 code | 软删 `N96P` 后 `POST` 同 code（大小写变体） | 409 unique_conflict；证明全量唯一索引含软删行（code 不重用） |
| B3 | PATCH code 不可变 | `PATCH /clusters/{id}` body 含 `code`（任意值/同值） | 422 `VALIDATION_ERROR`；库中 `code`/`code_key` 不变，`version` 不变 |
| B4 | name 中文 + 重名 | 创建 `name="山河3集群"`；再创建两个 `name="N96P集群"` | 全部成功；不触发任何唯一约束（Cluster name 无唯一） |
| B5 | name trim 保留展示 | 创建 `name="  N96P集群  "` | 落库 `name="N96P集群"`（首尾空白去除，内部空白/大小写保留） |
| B6 | name 空/纯空白拒绝 | 创建或 PATCH `name=""`、`"   "` | 422（业务层）+ raw SQL 直插被 CHECK 拒绝 |
| B7 | name 控制字符拒绝 | 创建 `name="bad\x00name"` / 含 `\n`/`\x1f` 等控制字符 | 422（业务层）+ raw SQL 直插被 CHECK 拒绝 |
| B8 | status 默认 ACTIVE | `POST` 省略 `status` | 响应 `status=ACTIVE`；库默认 `'ACTIVE'` |
| B9 | status 切换不级联、INACTIVE 仍可维护 | `PATCH status=INACTIVE` 后再 PATCH name、ADMIN DELETE | 切换仅改 `status/version/updated_at`；无其它表被触碰；INACTIVE 下 name 修改与删除按权限成功 |
| B10 | 默认列表含 ACTIVE+INACTIVE 未删除 | 建 ACTIVE/INACTIVE/软删各一；默认 GET 列表 | 返回 ACTIVE+INACTIVE 两行，不含软删 |
| B11 | status 过滤 | GET `?status=INACTIVE` / `?status=ACTIVE` / 非法枚举 | 正确过滤；非法枚举 422 |
| B12 | 组合过滤 | GET `?q=...&code=...&status=...` 组合 | 各条件 AND 生效，结果集正确 |
| B13 | 排序白名单与 order | GET `?sort=code&order=asc` 等 5 个白名单字段 × asc/desc | 排序结果正确、稳定 |
| B14 | 非法排序 422 | GET `?sort=id`、`?sort=;DROP`、`?order=random` | 422 `VALIDATION_ERROR`；无 500、无 SQL 注入 |
| B15 | 分页边界 | `page`/`page_size`：1、100、0、101、负数、非整数、缺省 | 缺省 page=1/page_size=20；1..100 接受；0/101/负/非法 → 422；`total` 准确 |
| B16 | 模糊搜索 q | 建 `gpu0701`、`gpu0702`（code/name）；GET `?q=gpu07` | 返回匹配项（pg_trgm 或等价），不匹配项排除 |
| B17 | 软删默认隐藏（含关系加载） | 软删对象后默认列表/详情 | 默认不含/不可见；`with_loader_criteria` 对 eager 关系加载同样生效（B41） |
| B18 | include/only 越权 | VIEWER/EDITOR GET `?deleted=include`、`?deleted=only` | 403 `FORBIDDEN{reason:permission}` |
| B19 | include/only 授权 | ADMIN GET `?deleted=include`、`?deleted=only` | 200；`include` 含软删+未删，`only` 仅软删 |
| B20 | 已删详情可见性 | 直接按 id GET 软删对象：无 `VIEW_DELETED` vs ADMIN `?deleted=true` | 无权限 404（不泄露存在性）；ADMIN 可见 |
| B21 | ADMIN 恢复成功 | ADMIN `POST /{id}/restore`（带 version） | 200；`deleted_at=null`、`version+1`；写 RESTORE audit |
| B22 | 恢复 not_deleted | 对未删除集群 restore | 409 `CONFLICT{reason:not_deleted}` |
| B23 | 恢复 unique_conflict（机制级） | 经注册检查器使恢复重检报告 code/唯一冲突（Cluster 全量唯一故无自然路径，见 §4） | 409 `CONFLICT{reason:unique_conflict}`；目标保持软删、不覆盖 |
| B24 | 恢复 dependency_deleted（机制级） | 经注册检查器报告依赖仍软删（F003 引用集为空，F004+ 注册，见 §4） | 409 `CONFLICT{reason:dependency_deleted}`；目标不被恢复 |
| B25 | 恢复不级联 | 恢复一个软删集群，库中存在其它软删/关联对象 | 仅目标恢复；关联对象状态不变 |
| B26 | Audit 四 action | 依次 CREATE/UPDATE/DELETE/RESTORE 一个集群 | 恰 4 行 audit（+任何额外 UPDATE），action 与对象匹配，`before_data`/`after_data` 语义正确（CREATE 无 before、DELETE 无 after） |
| B27 | 强制失败回滚不留 audit | 在业务事务内触发强制异常（约束/注入失败）使 commit 失败 | 业务变更与 audit 行**均**回滚，`audit_logs` 无该对象残留行 |
| B28 | Activity 全角色 + 隔离 | VIEWER/EDITOR/ADMIN GET `/{id}/activity`；再查其它对象 activity | 三角色均 200；仅返回该 `(object_type, object_id)` 记录，按 `created_at` 排序 |
| B29 | Audit 无敏感字段 | 检查 CREATE/UPDATE 快照 JSON | 白名单仅业务字段；无 password/token/secret 等敏感键或值 |
| B30 | 完整审计查询限 ADMIN | 调用完整跨对象审计端点（若 F003 交付） | VIEWER/EDITOR 403；ADMIN 允许。若未交付 → 记 NOT_REQUIRED/机制级（§4） |
| B31 | 乐观锁两会话并发 | `committed_engine` 两独立连接均读同 `version`，各自 PATCH 后真实提交 | 一方 200 且 `version+1`；另一方 409 `VERSION_CONFLICT{current_version}`；最终库值来自成功方，无丢失更新 |
| B32 | 无静默重试覆盖 | 前端 client 对 409 的处理 | 不自动重试、不覆盖；明确呈现冲突 |
| B33 | 改名 id 不变 | 记录 `id`/`created_at`；PATCH name（及 status/description/metadata） | `id`/`created_at` 不变；`version` 递增 |
| B34 | DB：code_key 全量唯一 | raw SQL 直插两行同 `code_key`（一行软删）；检查索引谓词 | 唯一约束在含软删行时仍拒绝重复；索引**不含** `WHERE deleted_at IS NULL`；`ck_clusters_code_key_matches` 拒绝与 `code` 不一致的 `code_key`；`ck_clusters_code_key_format` 拒绝非法字符 |
| B35 | DB：全量唯一 vs 部分唯一差异 | 对比 F003 `uq_clusters_code_key`（全量）与 D01 表中通用对象部分唯一（`WHERE deleted_at IS NULL`） | F003 仅建 Cluster 全量唯一；不得误建为部分唯一（否则 code 可重用）；通用对象部分唯一属 F004+，F003 不实现不回归（§6） |
| B36 | DB：metadata object CHECK | raw SQL 直插 `metadata='[]'`、`'"x"'`、`'null'` | 被 `jsonb_typeof(metadata)='object'` CHECK 拒绝；`'{}'`/合法对象通过 |
| B37 | DB：audit action CHECK | raw SQL 直插 `action='PURGE'`/`'delete'` | 被 `ck_audit_logs_action` 拒绝；四合法 action 通过 |
| B38 | DB：audit FK RESTRICT | 删除 audit 引用的 `users` 行 | 被 `fk_audit_logs_operator_user_id_users ON DELETE RESTRICT` 拒绝（`confdeltype='r'`）；审计与用户行保留。另行验证 `operator_user_id` 可空（系统/CLI） |
| B39 | DB：其余 CHECK | raw SQL 直插 `status='BOGUS'`、`version=0`、空 name、含控制字符 name | 分别被 `ck_clusters_status`、`ck_clusters_version`、name CHECK 拒绝 |
| B40 | 迁移 up/down/up | `upgrade head` → `downgrade 0002_users_sessions` → `upgrade head` | 每步退出码 0；down 后两表消失、up 后重建且对象集合一致；单一 head `0003_clusters_audit`；空表 drop 记录数据安全策略 |
| B41 | 软删过滤覆盖关系加载 | 对象带 eager/loader 关系时软删过滤仍生效 | `with_loader_criteria` 对关系加载同样注入，无软删行泄出 |
| B42 | 迁移顺序与依赖 | 检查 `0003_clusters_audit` `down_revision=0002_users_sessions`，先建 clusters 后 audit_logs | 迁移顺序正确；`audit_logs.operator_user_id` FK 依赖已存在的 `users` |

并发说明：B27/B31 及任何“失败不留痕/并发不重复”用例必须使用 `committed_engine`（真实连接真实提交）或显式事务控制，断言**最终持久化状态**，不仅“未抛异常”。V12/B34–B39 必须在真实 PostgreSQL 执行（SQLite 不作 CHECK/唯一/FK/UUID 证据）。

---

## 3. 夹具 / 环境设计

**复用 F001 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：DB-D10 独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`（含 0003），会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染（用于 B1–B26 等单事务用例）。
- `committed_engine`：真实提交用例（B27/B31），teardown `TRUNCATE` 清理（**排除 `alembic_version`**；F003 追加 `clusters`/`audit_logs` 到清理清单），新开连接断言最终持久化。
- `alembic_runner`：迁移 up/down/up 用例（V13/B40）。

**复用 F002 认证/权限 fixture（`auth_session_factory`/`auth_app`/`api_client`/`bootstrap_admin`/`make_user`/`login`）**：
- `make_user(role, status=ACTIVE)` 生成 VIEWER/EDITOR/ADMIN；`login` 复用同一 Cookie 罐获得 `csm_session`；`api_client` 命中真实 ASGI 应用。
- F003 的权限/审计证据使用**真实业务端点** `/api/v1/clusters*`（不再是 F002 的测试挂载路由），A4/A5/A6/A7 的权限与审计在 F003 为端到端（见 §4 边界）。

**F003 新增 Cluster fixture（建议置于 `backend/tests/clusters/conftest.py`；实现阶段由 Backend 落地，Tester 可调整测试侧）**：
- `cluster_factory`：ORM/API 工厂，参数 `code/name/status/description/metadata`，返回对象与 `version`；供 A1–A9、B1–B30 复用。
- `soft_deleted_cluster`：软删后返回实体，供 B2/B17–B25/B41。
- `audit_rows(object_type, object_id)`：按 `(object_type, object_id)` 查询 `audit_logs`，断言 action/快照/顺序；供 A7/B26–B29。
- `assert_no_audit_side_effect`：业务失败后断言 `audit_logs` 行数不增；供 B27。
- `two_session_version_conflict`：基于 `committed_engine` 开两条独立连接读取同一 `version`，暴露“各自提交/最终断言”助手；真实提交 + teardown 清理（删除 F003 测试行，排除 `alembic_version`）；供 A8/B31。
- `D01_NORMALIZATION_CASES`：表驱动数据（Cluster code `upper(btrim)` 变体、name trim/中文/控制字符），供 A2/A10/B1/B5–B7 共用，确保 API 与后续导入共用归一化口径。
- `raw_sql(engine)`：以 raw SQL 直插非法值验证 CHECK/唯一/FK/UUID 默认（B34/B36–B39），不依赖 ORM 校验。

**环境**：Docker / Compose 可用（F001 TE-1、F002 TE-1/TE-2 已证）；真实 PG 经 Compose `db`（`postgres:16`）。宿主机无 `psql`/`pg_dump` 不影响本 Feature（DB 断言经 SQLAlchemy 或容器内 psql）。前端 V14 以构建 + client 机制级为主；若要求真实前后端集成，经入口 Nginx 验证，不以 Mock 代替（§4）。**环境风险（承 F002 D-TE-1）**：若以非默认入口端口运行 Compose，F003 写端点（POST/PATCH/DELETE/restore）需覆盖同源 CSRF 行为；应在与 TE-2 修复一致的 Nginx 配置下执行，或在报告标注该环境限制。

### 3.1 当前环境可执行性评估

| 验证项 | 环境要求 | 当前评估 | 降级/替代 |
| --- | --- | --- | --- |
| V1–V9/V12/V13、B1–B42 | 真实 PostgreSQL 实例 + 后端集成 | 经 Compose `db` 可满足（F001/F002 已证） | 无 PG 时 skip 并标 BLOCKED，**不得**用 SQLite 替代约束/并发证据 |
| V13/B40 迁移 up/down/up | Alembic + 真实 PG（空表） | 可执行；依赖 0003 定稿 | 迁移未定稿则相关断言 BLOCKED，不降验收 |
| V14 前端 | Node 22 + 构建 | 可执行（F002 smoke:client 已证） | 真实浏览器 DOM 渲染非必要判据（同 F001/F002） |
| Compose 冒烟 | Docker 可用、端口可用 | 可执行 | 镜像/端口问题记 BLOCKED 并说明 |

---

## 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| §19 关联区域（Resources/Networks/IPs/VMs/Services） | **不在 F003 范围（占位，不判 FAIL）** | F003 仅交付 Cluster 基础详情与页面/接口基线；架构 DR-33 明确关联区域占位、F004+ 接入。TD-1 不对关联区域断言，F003 不宣称完整 §19；A4 仅验证 Cluster 基础列表契约与搜索入口，不含关联组合（N96P+COMPUTE+IDLE 属 F004+）。 |
| A4/A7 权限与审计：机制级 vs 端到端 | **端到端（真实业务端点）+ 限定项** | 与 F002 不同，F003 有真实业务端点：读/写/删除/恢复/已删除可见/Activity 均可在 `/api/v1/clusters*` 端到端验证。**限定项**：①完整跨对象审计查询（`AUDIT_READ`）端点若 F003 未交付，则该行记机制级/NOT_REQUIRED 并注明归 F016（B30）；②`unique_conflict`/`dependency_deleted` 恢复冲突因 Cluster 全量唯一且 F003 引用集为空，无自然路径，只能经**注册检查器机制级**验证（B23/B24），须在报告中显式标注证据边界，不得表述为完整 T24 通过。 |
| D01 签核核对 | **可验证（文档）** | CONTRACT 定稿需记录 code/name 作用域表、code 归一化键、稳定 ID、时间契约、nullable/省略语义（A10/A11、V10/V11）；核对实现 `normalization.py` 与 DB `code_key` 一致。 |
| D02 审计一致性签核核对 | **可验证（文档 + 端到端）** | 同事务写路径、乐观锁版本列、错误语义（`CONFLICT`/`VERSION_CONFLICT`）需在 CONTRACT/DATABASE 记录；端到端由 V7/V8、B26/B27/B31 验证。 |
| code_key 全量唯一 vs 部分唯一 | **可验证（DB）** | B34/B35 明确 F003 只建 Cluster 全量唯一、通用对象部分唯一归后续 Feature；防止误用部分唯一导致 code 重用。 |
| metadata JSONB object / audit action / FK RESTRICT | **可验证（DB）** | B36–B38 raw SQL 断言，真实 PG。 |
| 软删过滤对关系加载 | **可验证** | B41 覆盖 `with_loader_criteria` 对 eager 关系的注入；关系对象本身在 F004+，F003 以基座机制 + 现有可加载关系验证。 |
| Audit 快照 JSON 可序列化 | **可验证** | B26/B29 断言 `before_data/after_data` 可 JSON 序列化且无敏感键。 |
| Cluster 详情未知值处理 | **可验证（前端）** | V14 断言未知/空值不伪装为空列表或 0；`description=null`、`metadata={}` 展示符合契约。 |

口径明确记录：**F003 的权限与审计为真实业务端点端到端**，但恢复冲突的 `unique_conflict`/`dependency_deleted` 与完整审计查询为**机制级/跨 Feature**；不得以局部 PASS 拼成完整 T24/T25/T26/T40 通过。

---

## 5. 范围与前置核对（交 CONTRACT/DATABASE 定稿）

| 项 | TD-1 假设（据 architecture.md 草案） | 待定稿核对 |
| --- | --- | --- |
| 错误信封与 reason | 复用 F002 信封；新增 `CONFLICT(409,{reason:unique_conflict\|reference_exists\|not_deleted\|dependency_deleted})`（DR-29） | `docs/api/F003.md` 定稿确认 reason 枚举、`field`/`references`/`conflicts` 字段 |
| 软删查询参数 | `deleted=exclude\|include\|only`（DR-19）；include/only 需 `VIEW_DELETED` | CONTRACT 确认默认值与权限映射 |
| 恢复端点 | `POST /api/v1/clusters/{id}/restore`（DR-20），必带 version | CONTRACT 确认路径、方法、错误语义 |
| DB 约束名/索引名 | `uq_clusters_code_key`、`ck_clusters_code_key_format`/`_matches`、`ck_clusters_metadata_is_object`、`ck_clusters_status`、`ck_clusters_version`、`ck_audit_logs_action`、`ck_audit_logs_has_data`、`fk_audit_logs_operator_user_id_users` | `docs/database/f003-*.md` 定稿确认名称/行为；不一致则升 TD-2 |
| 迁移 0003 | `0003_clusters_audit`，`down_revision=0002_users_sessions`，先 clusters 后 audit_logs | DATABASE 确认单 head、数据安全策略 |
| 乐观锁 rowcount=0 语义 | 404 或 409 `VERSION_CONFLICT`（DR-23/DR-29） | CONTRACT 明确区分 404（已删/不存在）与 409（版本过期） |
| 引用检查框架 | `object_type→checkers` 注册表；F003 cluster 引用集为空（DR-30） | DATABASE/CONTRACT 确认空集行为与 B23/B24 机制级口径 |
| pg_trgm GIN 引入点 | 模糊搜索索引是否 F003 引入交 Database 裁定 | DATABASE 定稿确认；影响 B16 证据强度 |

---

## 6. 不适用项与边界声明

- **其它对象软删/审计回归**：Resource/Interface/Network/IPPool/IPAddress/Service/ServiceEndpoint 的软删、恢复、审计端到端归 F004–F013；F003 仅落地横切基座于 Cluster 首个对象，**不回归其它对象**。
- **完整 T24/T40/T41/T25/T26**：F003 仅覆盖 Cluster 首个对象的子集（T13 全量、T29 相关、T24 首对象、T26 部分、T40 部分）；完整跨 Feature 回归归后续 Feature/上线验收，**不声明整体通过**。
- **§19 关联区域与组合过滤线**：Resources/Networks/IPs/VMs/Services 关联区域随 F004+ 接入；F003 不宣称完整 §19（见 §4）。
- **用户管理 UI 与账号管理流程**：归 F015。
- **CSV/Excel 导入**：名称归一化口径由 A10/D01 固化供后续复用，但导入本身归 F009/F010；F003 不执行导入用例。
- **完整跨对象 Audit 查询界面**：归 F016；F003 仅提供 Cluster 对象 Activity（B28）与被删除可见性。
- **登录限流、CSRF 完整防护**：承 F002（NOT_REQUIRED / 同源纵深）；F003 不新增。
- **§32 整体上线验收**：归 F016；Feature 通过 ≠ 上线授权。
- **真实浏览器 DOM 渲染**：非 F003 必要判据（同 F001/F002），前端以构建 + client 机制级 +（如要求）入口真实 API 集成为准。

---

## 7. 环境可执行性评估与风险

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1–V9/V12/V13（真实 PG + 后端集成） | Docker/Compose 可用（F001/F002 已证）；**可执行** | 无 PG 时相关项 BLOCKED，不降验收 |
| V13/B40 迁移（0003 定稿） | 依赖 DATABASE Gate | 未定稿 → BLOCKED，不降验收 |
| A8/B31 乐观锁并发 | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终持久化与 `current_version` |
| A6/B23/B24 恢复冲突 | Cluster 全量唯一 + 引用集为空 → 无自然 unique/dependency 路径 | 机制级（注册检查器）；报告显式标注，不表述为完整 T24 |
| A7/B27 同事务回滚 | 需可注入的业务失败点 | 以约束冲突/异常注入制造 commit 失败，断言业务与 audit 双回滚 |
| V14 前端 | 构建 + client 机制级 | 若真实前后端集成要求，经入口 Nginx 验证；CSRF 端口风险承 F002 D-TE-1 |
| DATABASE/CONTRACT 未定稿 | **MEDIUM**：约束名/reason/恢复语义可能微调 | TEST 执行前逐项核对 §5；差异升 TD-2 并注明失效范围 |

---

## 8. OPEN 复核项（TD-1 → 待 DATABASE/CONTRACT 定稿闭合）

| # | TD-1 假设 | 状态 | 依据 / 影响 |
| --- | --- | --- | --- |
| 1 | `clusters`/`audit_logs` 列、约束名、索引（§0/V12/B34–B38） | OPEN（待 DATABASE） | architecture §4 草案；定稿后核对，差异升 TD-2 |
| 2 | `code_key` 全量唯一 vs 通用部分唯一 | OPEN（待 DATABASE） | DR-24 明确 Cluster 全量唯一；确认无部分索引误用 |
| 3 | 迁移 `0003_clusters_audit` 对称可逆与空表 drop 策略 | OPEN（待 DATABASE） | DR-31；空表无历史数据，需记录数据安全策略 |
| 4 | `CONFLICT` reason 枚举与 `VERSION_CONFLICT` 复用 | OPEN（待 CONTRACT） | DR-29；错误语义端到端判据（V1/V5/V6/V8） |
| 5 | 恢复端点路径/方法/必带 version | OPEN（待 CONTRACT） | DR-20 |
| 6 | pg_trgm GIN 是否 F003 引入（影响 B16） | OPEN（待 DATABASE） | architecture §4.1 交 Database 裁定 |

上述未闭合项不影响 READY 结论（方案可验证、判据可观察）；TEST 执行前必须逐项关闭并核对定稿差异，若实现或 Contract 变更导致判据差异，升 TD-2 并注明 TD-1 失效范围。

---

## Test Execution

（预留：TEST 阶段在本节追加执行环境、验收映射结果、数据库/接口/前端/集成结果、Defects 与未验证项；TEST_DESIGN 不填充执行 PASS。）