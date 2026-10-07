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
| TD-2 | 2026-10-07 | 依 DATABASE v2 / Contract v2 / D01 v2 对齐 F003-REV-1：`ck_clusters_code_key_matches` 表达式由 `upper(btrim(code))` 改为 `translate(btrim(code),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')`（仅 ASCII 字母折叠）。TD-1 §0/V1/A1/V10 中 `code_key=upper(btrim(code))` / `upper(trim)` 的**失效范围为「归一化表达式文本」**，验收判据（code 大小写不敏感全量唯一、软删不重用、创建后不可改）不变，并细化为「仅 ASCII 字母折叠、非 ASCII 原样」；DB 约束名对照见 TE-1「TD-2 对齐」。 |

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

- **版本**：TE-1
- **日期**：2026-10-07
- **角色**：Tester（TEST 模式，独立执行）
- **基线提交**：`6615eff`（HEAD；backend `ca00d47`/`0a1d303`、frontend `9ce1ee1`、CONTRACT `75ba32f`）
- **结论**：`READY FOR REVIEW`
- **依据**：TD-1（本文件 Test Design）；`docs/api/F003.md` v1（Contract 定稿）；`docs/database/f003-cluster.md` v1；`docs/features/F003/architecture.md` §9（READY FOR IMPLEMENTATION，I-1 裁定）；`docs/features/F003/implementation.md`；`docs/project/implementation-rules.md`

### TD-2 对齐（architecture §9.2；仅测试侧口径修订，不改业务实现）

TD-1 在 DATABASE/CONTRACT 定稿前引用的是架构 §4 草案约束名，与 `docs/database/f003-cluster.md` v1 实际名称不一致；TEST 以实际名称（下方 V12/B 逐项）核对，TD-1 旧名**失效范围**为「名称文本」，验收判据（约束行为）不变：

| TD-1 旧名（草案） | 实际名称（DB v1） | 说明 |
| --- | --- | --- |
| `ck_clusters_code_key_format` | 不存在（I-1 已移除） | ASCII 正则被 D01 宽松字符集取代；实际为 `ck_clusters_code_key_not_blank` / `ck_clusters_code_key_length` / `ck_clusters_code_key_matches` |
| `ck_clusters_metadata_is_object` | `ck_clusters_metadata_object` | 行为一致（`jsonb_typeof='object'`） |
| `ck_audit_logs_has_data` | `ck_audit_logs_at_least_one_snapshot` | 行为一致（before/after 至少一方非空） |
| `members.version`（TD-1 §0 笔误） | `clusters.version` + `ck_clusters_version` | F003 无 members 表 |

另：TD-1 V5 判据表述「软删详情 `deleted=true` 无权限返回 404」与 Contract §5 措辞冲突，Contract §6.3 明确定稿口径为「`deleted=true` 需 `VIEW_DELETED`，否则 **403**」；无参数默认详情对软删对象返回 **404**（不泄露存在性）。实现遵循 Contract §6.3；TEST 以 Contract 为准（见 Defect D-TE（NOTE））。

**TD-2（2026-10-07，REV-1 修复轮）**：DATABASE v2 / Contract v2 / D01 v2 将 `ck_clusters_code_key_matches` 由 `upper(btrim(code))` 改为 `translate(btrim(code),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')`。TD-1 §0/V1/A1/V10 中 `code_key=upper(btrim(code))` / `upper(trim)` 的失效范围为「归一化表达式文本」，验收判据（大小写不敏感全量唯一）不变并细化为「仅 ASCII 字母折叠、非 ASCII 原样保留」；对应重测见 TE-2。

### 环境

| 项 | 值 |
| --- | --- |
| 后端镜像 | `docker build --target test ./backend`（Python 3.12，pytest 8.4.2） |
| 数据库 | 独立容器 `f003-test-db`（`postgres:16`，网络 `f003-test-net`，端口 55433，测试库 `csm_test`/`csm_verify`） |
| 集成 | `TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f003-test-db:5432/csm_test`（DB-D10 护栏：库名含 `test`、≠ `DATABASE_URL`） |
| 前端 | Node v22.23.2 / npm 12.0.2；`npm run build`、`npm run smoke:client` |
| Compose 全链路 | `docker compose -p f003test`（独立项目名/卷），入口 Nginx `127.0.0.1:18099`（非默认端口，验证同源 CSRF 端口保留） |
| 清理 | `compose -p f003test down -v`、`docker rm -f f003-test-db`、`docker network rm f003-test-net`、删临时镜像；工作区 `git status --short` 为空 |

### 实际执行的命令与输出摘要

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `docker build --target test -t csm-backend-test:f003 ./backend` | 成功（层缓存命中，源码与 HEAD 一致） |
| 2 | `docker run … pytest tests -v`（真实 PG） | **76 passed, 1 skipped**（skip=`test_trusted_extension_installed_by_non_superuser`，连接角色为 superuser，环境限制，非 F003 缺陷） |
| 3 | 独立库 `alembic upgrade head` / `alembic heads` | `0003_clusters_audit (head)`，单一 head |
| 4 | 自研独立校验脚本（raw SQL + 两条真实连接真实提交） | **21 / 21 PASS**（见 B34/B36–B39/B31/B27） |
| 5 | `alembic upgrade head → downgrade 0002 → upgrade head → downgrade base` | 各步 0；down 后 `clusters`/`audit_logs` 消失、`users`/`user_sessions` 保留；re-up 后对象集合逐项一致（表 5、索引 15、非内部触发器 2、约束集合相同）；`alembic_version` 随步骤回退/前进 |
| 6 | `npm run build`（tsc --noEmit + vite build） / `npm run smoke:client` | build 成功；smoke **26 passed, 0 failed** |
| 7 | Compose 全链路 curl（登录→创建→列表→PATCH→DELETE→include/only→restore→activity；VIEWER/EDITOR 权限；CSRF 跨源） | 全部符合 Contract（详见 A 映射） |
| 8 | `python3 scripts/validate_project_state.py` | `PROJECT STATE VALID`（结构校验；批准/证据另行核对） |

### V1–V14 执行结果（TD-1 → TE-1）

| 验证项 | 结果 | 证据 / 说明 |
| --- | --- | --- |
| V1 code 规则 + V12 DB 约束 | **PASS** | 用例 2、4、5、7；`N96P` vs `n96p`/` N96P ` → 409 `CONFLICT{unique_conflict,field:code}`；软删后重建同 code → 409；PATCH `code`/只读字段 → 422；`uq_clusters_code_key` 全量唯一 |
| V2 name 规则 | **PASS** | 用例 2；中文/重名成功、trim 落库、空/控制字符 422（API）+ raw CHECK 拒绝 |
| V3 status 规则 | **PASS** | 用例 2；省略默认 ACTIVE、切换仅 `status/version/updated_at`、INACTIVE 仍可 PATCH/DELETE |
| V4 列表契约 | **PASS** | 用例 2、7；默认含 ACTIVE+INACTIVE 未删、过滤/组合/排序/分页/模糊、非法参数 422 |
| V5 软删可见性 | **PASS**（口径按 Contract §6.3） | 用例 2、7；默认隐藏、include/only 越权 403、ADMIN 200、软删详情无 `deleted` 参数 → 404（不泄露）、显式 `deleted=true` 无权限 → 403 |
| V6 恢复语义 | **PASS**（冲突路径机制级） | 用例 2、7；ADMIN 恢复 200 + RESTORE audit、`not_deleted` 409；`unique_conflict`/`dependency_deleted` 经注册检查器机制级（B23/B24），非自然端到端 |
| V7 Audit/Activity | **PASS**（完整跨对象审计为 NOT_REQUIRED） | 用例 2、4；四 action 各一行、同事务回滚不留痕、白名单无敏感键、Activity 全角色且按对象隔离；完整跨对象审计端点未交付（B30） |
| V8 端到端乐观锁 | **PASS** | 用例 2、4；两条真实连接同 version 并发提交，一方成功一方 409 `VERSION_CONFLICT{current_version}`，最终库值来自成功方 |
| V9 稳定 ID | **PASS** | 用例 2；改名后 `id`/`created_at` 不变、`audit_logs.object_id` 恒等 UUID |
| V10 归一化/ID 基座 | **PASS** | `app/services/normalization.py` 单一实现；`gen_random_uuid()` 默认；无 pgcrypto/uuid-ossp |
| V11 签核核对 | **PASS**（文档） | `docs/api/F003.md` v1 + `docs/database/f003-cluster.md` v1 + architecture §9 记录 D01/D02；与实现一致 |
| V12 Schema/约束/索引/迁移 | **PASS** | 用例 4、5；约束/索引/触发器名称与 DB v1 一致，非法值被拒，FK `confdeltype='r'` |
| V13 迁移 up/down/up | **PASS** | 用例 5；对称可逆、单一 head、对象集合一致 |
| V14 Cluster 页面基线 | **PASS** | 用例 6；build + client 机制级 26 项；源码核对 Loading/Success/Empty/Error、过滤/搜索、`version` 随表单、409 不静默重试、`canViewDeleted`/`canRestore` 门控 |

### B1–B42 执行结果

| 编号 | 结果 | 证据摘要 |
| --- | --- | --- |
| B1 code 大小写/空白重复 | PASS | 用例 2、7；`n96p`/`N96P`/` N96P ` → 409 unique_conflict；`code_key='N96P'` |
| B2 软删后重建同 code | PASS | 用例 2、4；软删行仍占 key，重建 409 |
| B3 PATCH code 不可变 | PASS | 用例 2、4、7；API 422 + DB 触发器拒绝，库值/version 不变 |
| B4 name 中文 + 重名 | PASS | 用例 2；同 name 多次创建成功，无唯一冲突 |
| B5 name trim 保留 | PASS | 用例 2；`  N96P集群  ` → `N96P集群` |
| B6 name 空/纯空白 | PASS | 用例 2、4；API 422 + raw CHECK 拒绝 |
| B7 name 控制字符 | PASS | 用例 2、4；`\x00`/`\n`/`\x1f` → 422 + raw CHECK 拒绝 |
| B8 status 默认 ACTIVE | PASS | 用例 2、4、7；响应与库默认均 ACTIVE |
| B9 status 切换不级联、INACTIVE 可维护 | PASS | 用例 2；切换仅动 `status/version/updated_at`；INACTIVE 下 PATCH/DELETE 成功 |
| B10 默认列表含 ACTIVE+INACTIVE 未删 | PASS | 用例 2、7；默认 total 排除软删 |
| B11 status 过滤 | PASS | 用例 2；`status=INACTIVE`/`ACTIVE` 正确，非法枚举 422 |
| B12 组合过滤 | PASS | 用例 2、7；`q`+`status` AND 生效 |
| B13 排序白名单与 order | PASS（部分字段静态核对） | 用例 2；`sort=code` asc/desc 端到端；其余 4 字段由 `Literal` 白名单 + `_SORT_COLUMNS` 映射，未逐字段单独排序断言 |
| B14 非法排序 422 | PASS | 用例 2；`sort=id`/`;DROP`、`order=random` → 422，无 500/注入 |
| B15 分页边界 | PASS | 用例 2；缺省 1/20，1..100 接受，0/101 等 → 422，`total` 准确 |
| B16 模糊搜索 q | PASS | 用例 2、7；`q=gpu07` 命中 `gpu0701/0702`，不匹配项排除（ILIKE，未用 pg_trgm，符合 DB-D30） |
| B17 软删默认隐藏 | PASS | 用例 2、7 |
| B18 include/only 越权 | PASS | 用例 2、7；VIEWER/EDITOR → 403 `FORBIDDEN{reason:permission}` |
| B19 include/only 授权 | PASS | 用例 2、7；ADMIN include=未删+已删、only=仅已删 |
| B20 已删详情可见性 | PASS | 用例 2、7；无参数 → 404 不泄露；`deleted=true` 无权限 → 403（Contract §6.3）；ADMIN → 200 |
| B21 ADMIN 恢复成功 | PASS | 用例 2、7；200、`deleted_at=null`、`version+1`、RESTORE audit |
| B22 恢复 not_deleted | PASS | 用例 2、7；409 `CONFLICT{reason:not_deleted}` |
| B23 恢复 unique_conflict（机制级） | PASS（机制级） | 用例 2；注册检查器注入使重检报告冲突 → 409、目标保持软删；**Cluster 全量唯一无自然路径** |
| B24 恢复 dependency_deleted（机制级） | PASS（机制级） | 用例 2；注册依赖检查器 → 409、目标不恢复；F003 引用集为空，F004+ 注册 |
| B25 恢复不级联 | PASS | `restore_cluster` 仅条件 UPDATE 目标行；无级联语句（源码核对） |
| B26 Audit 四 action | PASS | 用例 2；恰 CREATE/UPDATE/DELETE/RESTORE，CREATE 无 before、DELETE 无 after |
| B27 强制失败回滚不留 audit | PASS | 用例 2、4；注入非法 action，业务与 audit 同事务双回滚 |
| B28 Activity 全角色 + 隔离 | PASS | 用例 2、7；三角色 200、按 `(object_type,object_id)` 且按 `created_at` 排序 |
| B29 Audit 无敏感字段 | PASS | 用例 2；白名单仅 cluster 业务字段，无 password/token/secret |
| B30 完整审计限 ADMIN | **NOT_REQUIRED**（机制级） | 无完整跨对象审计端点（归 F015/F016）；`AUDIT_READ` 在权限矩阵中 ADMIN-only（F002 §3） |
| B31 乐观锁两会话并发 | PASS | 用例 4；两条真实连接真实提交，一方 200 一方 409，无丢失更新 |
| B32 无静默重试覆盖 | PASS | 用例 6；client 对 409 明确呈现、fetch 仅调用一次 |
| B33 改名 id 不变 | PASS | 用例 2；`id`/`created_at` 不变、`version` 递增 |
| B34 DB code_key 全量唯一 | PASS | 用例 4、5；软删行占位、索引定义无 `deleted_at` 谓词、`ck_clusters_code_key_matches` 拒绝不一致 |
| B35 全量唯一 vs 部分唯一 | PASS | 仅建 Cluster 全量唯一；未误建部分唯一；通用部分唯一属 F004+ 未实现 |
| B36 metadata object CHECK | PASS | 用例 4、5；`[]`/`"x"`/`null` 被 `ck_clusters_metadata_object` 拒；`{}`/对象通过 |
| B37 audit action CHECK | PASS | 用例 4、5；`PURGE`/`delete` 被 `ck_audit_logs_action` 拒；四合法 action 通过 |
| B38 audit FK RESTRICT + append-only | PASS | 用例 4、5；持有审计的 user DELETE 被拒（`confdeltype='r'`）、UPDATE/DELETE 触发 `restrict_violation`、`operator_user_id` 可空 |
| B39 其余 CHECK | PASS | 用例 4、5；`status='BOGUS'`、`version=0`、空/带首尾空白 name 均被拒 |
| B40 迁移 up/down/up | PASS | 用例 5；各步 0、对象集合对称、单一 head |
| B41 软删过滤覆盖关系加载 | **NOT TESTED**（无适用对象） | F003 无 ORM 关系；`with_loader_criteria(include_aliases=True)` 已注册，关系加载传播待 F004+ 有真实关系时回归；非 FAIL |
| B42 迁移顺序与依赖 | PASS | `0003` `down_revision=0002_users_sessions`；先建 `clusters` 后 `audit_logs`（FK→`users`） |

### 验收映射 A1–A11

| # | 结论 | 证据 |
| --- | --- | --- |
| A1 code 大小写不敏感唯一、软删不重用、创建后不可改 | **PASS** | V1/V12、B1–B3/B34；用例 2、4、7 |
| A2 name 中文/可改/不唯一/trim/空与控制字符拒绝 | **PASS** | V2、B4–B7；用例 2、4 |
| A3 status 默认 ACTIVE、可切换、不级联、INACTIVE 可维护 | **PASS** | V3、B8/B9；用例 2、7 |
| A4 默认列表含停用、过滤/排序/分页/模糊 | **PASS** | V4、B10–B16；用例 2、7 |
| A5 默认隐藏软删、ADMIN 可见、EDITOR/VIEWER 不可见 | **PASS** | V5、B17–B20；用例 2、7 |
| A6 ADMIN 恢复、冲突不覆盖、不级联 | **PASS**（`unique_conflict`/`dependency_deleted` 机制级，B23/B24） | V6、B21–B25；用例 2、7 |
| A7 四 action 同事务 Audit、Activity 全角色、完整 Audit 限 ADMIN、不记敏感 | **PASS**（完整跨对象审计 NOT_REQUIRED） | V7、B26–B30；用例 2、4 |
| A8 过期版本 409、无静默覆盖/重试 | **PASS** | V8、B31/B32；用例 2、4、7 |
| A9 code/name 变更不改身份、稳定 ID | **PASS** | V9、B33；用例 2 |
| A10 归一化与稳定 ID 固化为共享契约 | **PASS** | V10；`normalization.py` 单一实现、`gen_random_uuid()`、无 pgcrypto/uuid-ossp；D01 §5.1 口径一致 |
| A11 D01/D02 在本 Feature CONTRACT 签核 | **PASS** | V11；`docs/api/F003.md` v1 + `docs/database/f003-cluster.md` v1 + architecture §9 |

### 数据库 / 接口 / 前端 / 集成结果

- **数据库（真实 PG）**：约束/索引/触发器/函数与 DB v1 逐项一致；`uq_clusters_code_key` 全量唯一（索引定义无 `deleted_at`）；`trg_clusters_code_immutable`、`trg_audit_logs_append_only` 生效；`fk_audit_logs_operator_user_id_users` RESTRICT；`gen_random_uuid()` 默认；迁移 0003 对称可逆、单一 head；F003 空表 drop 数据安全策略已在 DB v1 §5 记录。**PASS**
- **接口（ASGI + 全链路 Nginx）**：7 端点响应内容、类型、nullable、业务边界、非法输入、错误语义均符合 Contract；错误信封 `CONFLICT`（reason 枚举 4 项齐全）/`VERSION_CONFLICT`/`VALIDATION_ERROR`/`FORBIDDEN`/`NOT_FOUND`/`AUTH_REQUIRED`；只读端点（列表/详情/activity）无业务写副作用（`activity` 只读、无审计修改入口）。**PASS**
- **前端**：`npm run build` 通过；client 机制级 26 项通过；V14 状态/交互/错误/未知值处理经源码核对。真实浏览器 DOM 非本 Feature 必要判据。**PASS**
- **集成（Compose 经入口 Nginx，端口 18099）**：登录→创建（含 CJK code/name trim）→列表→PATCH→DELETE→ADMIN include/only→restore→activity 全链路 200/201/204；非 ADMIN 软删可见性 403、详情默认 404；EDITOR 写 201、VIEWER 写 403、EDITOR restore 403；跨源 CSRF 写 403；未认证 401。**PASS**

### Defects

| ID | Severity | Layer | Location | 证据 / 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D-TE-F003-1 | NOTE | Contract 文档 | `docs/api/F003.md` §5 vs §6.3；本文件 TD-1 V5 | TD-1 V5 写「无权限 `deleted=true` 返回 404」，Contract §6.3 定稿为 403；实现在显式 `deleted=true` 且无权限时返回 403、默认详情返回 404（不泄露）。Contract 为权威，实现一致 | 文档内部措辞不一致，无实现缺陷 | Architect | 否 |

未发现 BLOCKER/HIGH/MEDIUM/LOW 实现缺陷。

### 未验证项与边界（不声称完整通过）

- **A4/A6/T24/T25/T26 机制级口径**：`unique_conflict`/`dependency_deleted` 恢复冲突因 Cluster 全量唯一且 F003 引用集为空，仅经注册检查器机制级验证（B23/B24），**不表述为完整 T24/T25/T26 通过**；完整跨 Feature 回归归 F004+ / 上线验收。
- **完整跨对象审计查询**：B30 `NOT_REQUIRED`（未交付，归 F015/F016）；`AUDIT_READ` ADMIN-only 仅矩阵级验证。
- **B41**：F003 无 ORM 关系，`with_loader_criteria` 关系加载传播 `NOT TESTED`，待 F004+ 有真实关系回归。
- **B13 其余排序字段**：仅 `code` 端到端排序断言，其余 4 字段为白名单 + 映射静态核对。
- **V3b skip**：`test_trusted_extension_installed_by_non_superuser` 因测试连接角色为 superuser 而 skip（环境限制，非 F003 缺陷，承接 F001 TE-1）。
- **§19 关联区域、CSV/Excel 导入、用户管理 UI、真实浏览器 DOM**：按 product/architecture 明确不属 F003 范围，未执行。
- **生产/未知数据库**：未使用；所有集成/约束/迁移/并发证据均来自独立 `postgres:16` 测试库（库名含 `test`）。

---

## Test Execution — 修复循环第 1 轮（F003-REV-1）

- **版本**：TE-2
- **日期**：2026-10-07
- **角色**：Tester（TEST 模式，独立重测；修复循环第 1 轮）
- **基线提交**：`933fae4`（HEAD；修复提交 `f39e6b5`、Review `7c6cd84`、上一轮候选 `c959013`）
- **结论**：`READY FOR REVIEW`
- **依据**：`docs/features/F003/review-report.md`（F003-REV-1/REV-2/REV-3）；`docs/api/F003.md` v2；`docs/architecture/d01-conventions.md` v2；`docs/database/f003-cluster.md` v2；`docs/features/F003/implementation.md`；本文件 TD-2

### 重测范围（受影响项 + 必要回归）

本轮仅针对 F003-REV-1 修复（`code_key` 仅 ASCII 折叠）及其影响面；未变更的 A2–A9/A11 验收项以 TE-1 为历史证据、本轮不做全量重跑，但通过 R-1/R-2 全量 `pytest` 与 R-5 Compose 全链路覆盖回归。

| 类型 | 项 | 说明 |
| --- | --- | --- |
| 受影响重测 | REV-1 `code_key` 归一化一致性；A1/A10、V1/V10/V12、B1/B34、F003-REV-1 修复回归 | 服务层 + RAW SQL + HTTP/Compose 三路径 |
| 必要回归 | 全量真实 PG `pytest tests`；迁移 0003 up/down/up；约束/触发器（code 不可改、audit append-only、FK RESTRICT）；Compose 运行时全链路 + CSRF | 见 R-1…R-5 |
| 文档/非阻塞复核 | F003-REV-2（DB `[:space:][:cntrl:]` backstop 已知差异）、F003-REV-3（Contract §5/§6.3 措辞） | 关闭状态核对 |

### 环境

| 项 | 值 |
| --- | --- |
| 测试镜像 | `docker build --target test -t csm-backend-f003te2 ./backend`（Python 3.12，pytest 8.4.2；源码 = HEAD `933fae4`） |
| 独立测试库 | 独立容器 `f003te2-db`（`postgres:16`，网络 `f003te2-net`，端口 55434，库 `csm_test` / `csm_verify`） |
| 集成库 URL | `TEST_DATABASE_URL=postgresql+psycopg://csm:change-me@f003te2-db:5432/csm_test`（DB-D10 护栏：库名含 `test`、≠ `DATABASE_URL`） |
| Compose 全链路 | `docker compose -p f003te2`（独立项目名/卷），入口 Nginx `127.0.0.1:18098`（非默认端口） |
| 清理 | `compose -p f003te2 down -v`；`docker rm -f f003te2-db`；`docker network rm f003te2-net`；删测试镜像；残留对象核对为空 |

### 命令与输出摘要

| # | 命令 | 结果 |
| --- | --- | --- |
| R-1 | `pytest tests -v`（真实 PG，独立库） | **78 passed, 1 skipped**（skip=`test_migrations.py:101` 非 superuser 扩展，环境限制，非 F003 缺陷） |
| R-2 | 独立校验脚本 `/work/verify.py`（服务层 + RAW SQL + ASGI 三路径） | **24 / 24 PASS**（见下） |
| R-3 | 独立校验脚本 `/work/constraints.py`（RAW SQL 约束/触发器/FK/索引） | **31 / 31 PASS** |
| R-4 | `alembic heads / upgrade head / downgrade 0002 / upgrade head` + `psql` 表清单 | 单一 head；down 后 `clusters`/`audit_logs` 消失、`users`/`user_sessions` 保留；re-up 恢复；`current=0003_clusters_audit (head)` |
| R-5 | Compose 全链路 curl（登录→创建→列表→CSRF；真实运行时镜像 + Nginx） | **10 / 10 PASS** |

### F003-REV-1 复核结论：**FIXED**

| 判据 | 路径 | 结果 |
| --- | --- | --- |
| `straße` 创建成功，`code_key='STRAßE'` | 服务层 | PASS |
| `ﬁle` 创建成功，`code_key='ﬁLE'` | 服务层 | PASS |
| `山河3` 创建成功，`code_key='山河3'` | 服务层 | PASS |
| `straße-http` / `ﬁle-http` / `山河3-http` POST → **201**（修复前为 500） | ASGI HTTP | PASS |
| 上述行的库中 `code_key` 分别为 `STRAßE-HTTP` / `ﬁLE-HTTP` / `山河3-HTTP` | ASGI + raw SQL | PASS |
| `N96P` 后 `n96p` → **409** `CONFLICT{reason:unique_conflict,field:code}` | 服务层 + HTTP + Compose | PASS |
| 不变量 `code_key = translate(btrim(code),'a..z','A..Z')`（全表 violations=0） | RAW SQL | PASS |
| `pg_get_constraintdef('ck_clusters_code_key_matches')` 含 `translate(`、不含 `upper(` | RAW SQL | PASS |
| raw 插入 `Weiß`/`WEIß` 成功；`WeißX`/`WEISSX` 被 CHECK 拒；重复 key 被 UNIQUE 拒 | RAW SQL | PASS |
| `STRASSE` 与 `Straße` 为**不同** key（`ß` 保留、不折叠为 `SS`） | RAW SQL | PASS |
| `IntegrityError` 映射：`uq_clusters_code_key`→409 `CONFLICT`；其它 CHECK→422 `VALIDATION_ERROR`（不再 500） | 服务层单元 | PASS |
| Compose 运行时库中 `ﬁle|ﬁLE`、`straße|STRAßE`、`山河3|山河3`、`N96P|N96P` | Compose + `psql` | PASS |

结论：应用（`str.maketrans` ASCII 折叠）与 DB（`translate(btrim(code),…)`）在同一 ASCII-only 口径，且与 locale/Unicode 大小写表解耦；多码位 Unicode 合法输入不再触发 CheckViolation/500。**F003-REV-1 已修复**，修复提交仅改动归一化/约束表达式/错误映射与对应测试及 v2 设计文档（`git show --stat f39e6b5`）。

### 回归结果（R-4 迁移与约束独立证据）

- 约束/触发器 RAW SQL（R-3，31/31）：`ck_clusters_code_not_blank/trimmed/no_ws_control/length`、`ck_clusters_status`、`ck_clusters_version`、`ck_clusters_metadata_object`、name CHECK 均拒绝非法值；`trg_clusters_code_immutable` 拒 `UPDATE code` 与 `UPDATE code_key`、放行 name/status/deleted_at；`trg_audit_logs_append_only` 拒 `UPDATE`/`DELETE`；`fk_audit_logs_operator_user_id_users` 为 RESTRICT（`confdeltype='r'`）且 `operator_user_id` 可空；`uq_clusters_code_key` 全量唯一（索引定义**无** `WHERE deleted_at`）；五索引与两触发器存在。
- 迁移（R-4）：`0003_clusters_audit` 单一 head，up/down/up 对称，`down_revision=0002_users_sessions`。
- 全量 `pytest`（R-1）：78 passed / 1 skipped；含新增 F003-REV-1 回归用例（多码位 Unicode ASCII-only key、IntegrityError 映射）及约束/迁移/并发/前端机制级既有用例。
- Compose（R-5）：真实运行时镜像经入口 Nginx 完成登录/创建/列表/CSRF，`straße`/`ﬁle`/`山河3` 均 201，`n96p` 409，跨源写 403。

### F003-REV-2 / F003-REV-3 复核

- **REV-2（LOW，非阻塞）→ 已作为已知差异闭合**：实测 `ck_clusters_code_no_ws_control` 定义为 `!~ '[[:space:][:cntrl:]]'`、`ck_clusters_name_no_control` 为 `!~ '[[:cntrl:]]'`（POSIX 类，locale 下仅 ASCII/有限范围），弱于应用 Unicode Cc/Cf 校验；`docs/database/f003-cluster.md` v2 §8 **I-6** 已将其记录为「DB backstop 已知差异，不阻塞」。API 路径由应用拦截，无绕过。**非实现缺陷，不再要求修复。**
- **REV-3（NOTE，非阻塞）→ 已闭合**：`docs/api/F003.md` v2 §5 与 §6.3 措辞已统一——显式 `deleted=true` 且无 `VIEW_DELETED` → 403 `FORBIDDEN{reason:permission}`；默认视图（无参数）对软删对象 → 404（不泄露存在性）。TE-1 记录的 D-TE-F003-1 措辞冲突消除。

### Defects（本轮）

| ID | Severity | Layer | Location | 证据 / 期望与实际 | 影响 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | 未发现 F003-REV-1 残留缺陷 | — | — | — |
| D-TE-F003-2 | NOTE | 文档（实现报告） | `docs/features/F003/implementation.md` Backend 报告 | 修复提交 `f39e6b5` 未同步更新该报告，其「归一化」仍写 `code_key=upper(trim)`（v1 口径），与 D01 v2/Contract v2/DB v2/实际实现不符 | 追溯性文档陈旧，不影响运行时行为；Review 依据权威设计文档（v2）判定 | Backend / 协调器 | 否 |

### 未验证项（本轮）

- **未变更验收项不重复取证**：A2–A9/A11、B2/B4–B33/B35–B42 未逐一重跑，沿用 TE-1 历史 PASS；本轮通过 R-1…R-5 覆盖回归风险。
- **B41**（软删过滤覆盖关系加载）仍 `NOT TESTED`（F003 无 ORM 关系），待 F004+ 回归。
- **B13** 其余 4 个排序字段仍为白名单 + 映射静态核对。
- **完整跨对象审计查询（B30）/T24/T25/T26/T40** 机制级口径不变，不声明整体通过。
- **真实浏览器 DOM** 未执行（非 F003 必要判据）。
- 未验证其它 collation/locale 变体；本轮 `postgres:16` 默认 locale（en_US.utf8 容器），因新口径与 locale 解耦，结果应一致但未逐一枚举。

### 正式结果

**`READY FOR REVIEW`**：F003-REV-1 **FIXED**，回归无 FAIL，REV-2/REV-3 关闭。D-TE-F003-2 为 NOTE 级文档陈旧，不阻塞。Merge/DONE 由协调器按 Git Workflow 判定。

### Git 声明

```text
GIT: git branch --show-current
GIT: git log --oneline -8
GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git rev-parse HEAD
GIT: git show --stat --oneline f39e6b5
GIT: git show --stat --oneline 933fae4
GIT: git diff --name-only c959013..HEAD
GIT: git diff --stat c959013..HEAD
GIT: git show f39e6b5 -- backend/app/services/normalization.py backend/alembic/versions/0003_clusters_audit.py backend/app/models/cluster.py
```

以上均为只读命令；未执行 `git add`/commit/branch/merge 或任何改变 Git 状态的操作。
