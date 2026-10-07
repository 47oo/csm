# F002 认证、初始账号与权限横切 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据，TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-2
- **日期**：2026-10-06
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§21–§23、§25–§27、§29–§31、§35.2/§35.3 D02）
  - `docs/features/F002/product.md`（READY FOR ARCHITECT；A1–A7 与边界）
  - `docs/features/F002/architecture.md`（READY FOR DESIGN；§1 方案、§5 表草案、§6 验证策略、§7 交 Tester 事项、R1/R2/R3）
  - `docs/database/f002-auth.md` v1（**DATABASE Gate 定稿**；DB-D13–DB-D19、§3/§4 表与约束、§5 迁移 0002、§7 计划测试项 V-DB-1–V-DB-7）
  - `docs/features/F001/test-report.md`（TD-2/TE-1 基线与 fixture 约定：DB-D10 独立测试库 + 安全护栏、会话级重建 schema、函数级 savepoint、并发真实提交）
  - `docs/database/f001-baseline.md` v1（DB-D4/D5/D6/D7/D8/D10/D11）
  - `docs/project/project-plan.yaml` plan_revision 4，F002 条目（已批准，IN_PROGRESS）
  - `docs/project/implementation-rules.md`（验证与交付）、`AGENTS.md`（数据安全、Git）、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：READY 仅表示 A1–A7 可映射到可观察判据、边界场景可执行；**不表示测试已运行、不批准实现或合并、不表示 T25/T26 完整通过**。F002 为请求级横切，完整 T25/T26 回归归 F003。
- **前置状态说明**：DATABASE Gate 已定稿 `docs/database/f002-auth.md` v1，本 TD-2 已据此复核 V/B 判据（数据库层约束、UUID 默认、FK RESTRICT、索引与迁移可逆性均由 DB-D13–DB-D19 关闭，见 §8）。CONTRACT Gate（`docs/api/F002.md`，错误码/CSRF/bootstrap CLI 形态）尚未定稿；TEST 执行前仍须以 CONTRACT 定稿逐项核对，差异处再升 TD 版本。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-06 | 初版：A1–A7 映射 V1–V9，边界 B1–B17，夹具/环境设计，T25/T26 子集映射，不适用项；对 DATABASE/CONTRACT Gate 保留 5 项待复核假设（依赖 architecture.md §5 表草案）。 |
| TD-2 | 2026-10-06 | 对照 DATABASE Gate 定稿 `docs/database/f002-auth.md` v1 复核并升级。关闭 TD-1 §8 第 1、2 项（DB-D13 UUID 原生 gen_random_uuid、DB-D14 username 单列归一化 + UNIQUE + CHECK、DB-D15 role/status varchar+CHECK、DB-D16 FK RESTRICT + 显式索引、DB-D17 迁移 0002 对称可逆、其他 CHECK 名称）；同步 §0 完整性表、V9、B15/B16，新增 B18–B21（UUID 默认、FK RESTRICT、索引/唯一约束存在、其余 CHECK 与迁移 up/down/up）；§8 第 3–5 项（错误码、CSRF、bootstrap CLI 调用形态）仍待 CONTRACT。第 1、2 项旧判据失效，以本版为准。 |

> 复核基线：`docs/database/f002-auth.md` v1（2026-10-06，DATABASE 签核）；TD-1 对 DATABASE Gate 的 PROPOSED 假设已由 DB-D13–DB-D19 关闭。TD-1 的 DB 层预期（未命名约束、`gen_random_uuid()` 待定、username 归一化键列假设）被本节取代。

### 0. 数据完整性对应表（F002 范围）

仅列 F002 已确认且在实现后需验证的认证/权限/持久化项；业务对象约束留待 F003+。方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列以 DATABASE Gate 定稿 `docs/database/f002-auth.md` v1（DB-D13–DB-D19）为准，列名/约束名与 §3/§4 一致。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证（DB-Dx） | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §23 revision 3（角色枚举与权限矩阵，服务端执行） | `require_permission` 依赖；`users.role` | `role varchar(16) NOT NULL` + `ck_users_role: role IN ('VIEWER','EDITOR','ADMIN')`（DB-D15）拒绝非法值 | `ROLE_PERMISSIONS` 显式 frozenset；未认证 401 / 越权 403 | 无继承隐式授权 | V4/B11/B15；计划验证 |
| §23 / §21（账号停用保留操作者身份，不软删） | `users.status`、会话解析 | `status varchar(16) DEFAULT 'ACTIVE'` + `ck_users_status: status IN ('ACTIVE','DISABLED')`（DB-D15）；**无 deleted_at**；`fk_user_sessions_user_id_users ON DELETE RESTRICT`（DB-D16） | 每次请求 join users 校验 `status='ACTIVE'`；停用即 401；停用时显式删会话 | 停用不删行、旧审计操作者保留；带会话用户删除被 RESTRICT 拒绝 | V8/B3/B19；计划验证 |
| DR-14（username 归一化小写、大小写不敏感唯一） | 登录/bootstrap/用户创建 | **单列**已归一化（小写、去首尾空白）值 + `uq_users_username`（DB-D14）；`ck_users_username_format: username ~ '^[a-z0-9._-]{3,64}$'`；不用 citext、无独立归一化键列 | 服务层归一化后比较 | 停用账号仍占唯一名 | B16；计划验证 |
| §23 / DR-08（服务端不透明会话，令牌仅存哈希） | 登录创建会话；Cookie | `user_sessions.token_hash varchar(64) NOT NULL` + `uq_user_sessions_token_hash` + `ck_user_sessions_token_hash_format: ^[0-9a-f]{64}$`（SHA-256 hex）；`fk_user_sessions_user_id_users`（DB-D16） | 请求时哈希查询 + 过期判定 | 登出删除行；`ck_user_sessions_expires_after_created: expires_at > created_at`；过期惰性判定，不预建清理（DB-D18） | V8/B4/B5/B6/B18/B21；计划验证 |
| §22 / §30（密码、令牌不记录不展示；真实凭据不入仓） | 日志 Filter；响应 Schema；`.env` | 仅存 `password_hash`/`token_hash`；`ck_users_password_hash_nonempty: length(btrim(password_hash)) > 0` | `SENSITIVE_FIELDS` 脱敏；auth 端点不记录请求体；响应不含 `password_hash` | 错误日志脱敏后输出 | V5/B12/B21；计划验证 |
| §26 / §27（真实 PG 验证；新表 Migration 可逆） | Alembic 迁移 0002_users_sessions（DB-D17） | up/down 对称（先 users 后 user_sessions，downgrade 逆序 drop）；约束显式命名，CHECK 生效 | N/A | 新表无历史数据，downgrade 对称 drop；单一 head | V9/B20/B21；计划验证 |
| DR-12（bootstrap 幂等、迁移不写业务数据） | 应用侧一次性 CLI `python -m app.cli.bootstrap_admin`（**非迁移**） | `uq_users_username` 兜底并发 | 事务内“存在任何用户（含停用）→ no-op”；空表缺凭据非零退出 | 并发 bootstrap 唯一性由约束兜底 | V2/B7/B8/B9；计划验证 |

### 1. 验收映射（product.md A1–A7 → 验证项）

执行环境：`Compose` = 干净环境 `docker compose up -d`（含 `migrate`/`bootstrap` 一次性服务）；`真实 PG` = 经 Compose `db` 或本机 PostgreSQL 的独立测试库（DB-D10，库名含 `test`）；`后端集成` = ASGI 应用 + 真实 PG 测试库（非 SQLite）；`静态` = 仓库/路由清单静态检查；`前端` = 构建 + client 机制级用例。

| 验收（product.md） | 验证项 | 执行环境 | 可观察判据（PASS / FAIL） |
| --- | --- | --- | --- |
| A1 初始 ADMIN 登录成功得会话语义；凭据错误鉴权失败（非 5xx）；响应/日志无凭据明文 | **V1** 登录流程 | 真实 PG + 后端集成 | PASS：bootstrap 后 `POST /api/v1/auth/login` 正确凭据 → 200，body 含 `user{id,username,role=ADMIN,status=ACTIVE,permissions[]}` 与 `expires_at`，且 `Set-Cookie: csm_session=...`；错误密码 → 401 `AUTH_INVALID_CREDENTIALS`（非 5xx）；响应体与捕获日志无密码明文。FAIL：登录返回 5xx、无 Cookie、body 泄露凭据、错误凭据返回 2xx |
| A2 干净环境初始化唯一首个 ADMIN；重复启动不重复创建；仓库无真实初始凭据 | **V2** bootstrap 幂等 + **V9** 迁移 | 真实 PG + Compose + 静态 | PASS：干净库 bootstrap → `users` 恰 1 行 role=ADMIN、status=ACTIVE、version=1；再次运行 → 退出码 0 且用户数不变（no-op）；空表 + 变量缺失 → 非零退出并有明确提示、不写入半行；`git ls-files`/全文检索无真实初始凭据、`.env` 未被跟踪。FAIL：产生 2 个 ADMIN、重复运行报错或新建、缺凭据时静默退出 0、仓库存在真实凭据 |
| A3 无任何自行注册路径 | **V3** 无注册端点 | 后端集成 + 静态 | PASS：路由清单（`app.routes`）无 register/signup 路径；`POST /api/v1/auth/register` 与 `/api/v1/auth/signup` 返回 404（或 405，取决于是否与其他方法同路径）；OpenAPI 无注册 operation。FAIL：存在可用注册入口或创建用户的匿名端点 |
| A4 受保护端点服务端鉴权：未认证 401、越权 403，可复现 | **V4** 鉴权执行 | 真实 PG + 后端集成 | PASS：无 Cookie 调用受保护路由 → 401 `AUTH_REQUIRED`；VIEWER/EDITOR 持有效会话调用 `require_permission(USER_ADMIN)`（及 §1.4 各 ADMIN-only 能力）→ 403 `FORBIDDEN`；ADMIN → 通过。判据详见 B11。**R1 口径**：403 证据来自测试挂载**生产依赖** `require_permission` 的路由（见 §3），首个真实 ADMIN-only 业务端点留 F003。FAIL：未认证返回 403/2xx、越权返回 2xx、鉴权仅在前端实现 |
| A5 登录/鉴权请求的日志与响应无密码、令牌明文 | **V5** 敏感内容扫描 | 后端集成 + 日志捕获 | PASS：响应体（含错误响应）扫描无 `password`/`password_hash`/会话令牌明文；捕获的 auth 端点日志无请求体凭据、无令牌、无 `Set-Cookie` 明文；`SENSITIVE_FIELDS` 过滤生效。判据详见 B12。FAIL：任一响应或日志出现密码/令牌明文 |
| A6 过期版本编辑被 409 语义拒绝，返回可识别冲突信号；无静默重试覆盖 | **V6** 版本冲突机制级 | 真实 PG + 后端集成 + 前端机制级 | PASS：错误信封对过期版本返回 409 `VERSION_CONFLICT` 且 `details.current_version` 可识别；机制级路径可复现（测试挂载抛出版本冲突的路由，或对 `users.version` 的真实条件更新）；前端 client 收到 409 时**不自动重试**并明确呈现冲突。业务端到端（真实业务对象过期编辑）归 F003/T26。FAIL：过期版本被静默覆盖或返回 2xx、无 `current_version`、客户端自动重试 |
| A7 T25/T26 认证与权限部分有可执行用例映射；完整回归 F003 后通过 | **V7** T25/T26 子集映射 | 文档 + 后端集成 | PASS：§5 子集映射表存在，F002 内断言可执行且分别归 V4/V5/V6/B11；明确列出留待 F003 的断言。FAIL：无映射、把完整 T25/T26 通过记入 F002 |
| （A1/A4 支撑）会话生命周期与 Cookie 属性 | **V8** 会话/Cookie | 真实 PG + 后端集成 + Compose | PASS：Cookie 含 `HttpOnly`、`SameSite=Lax`、`Path=/`（生产 `Secure`）；令牌不出现在响应体；过期会话 401；登出后原 Cookie 立即 401。判据详见 B4/B5/B6。FAIL：缺 HttpOnly/SameSite、登出后仍可用、令牌出现在 body |
| （数据层支撑 A2/A4） | **V9** Schema / 约束 / Migration | 真实 PG | PASS：`alembic upgrade head` → `users`/`user_sessions` 建表（DB-D17）；`id` server_default `gen_random_uuid()` 自动生成 UUID；`ck_users_role`/`ck_users_status`/`ck_users_version`/`ck_users_username_format`/`ck_users_password_hash_nonempty`/`ck_user_sessions_token_hash_format`/`ck_user_sessions_expires_after_created` 名称与行为均与 DATABASE 定稿一致且拒绝非法值（B15/B18/B21）；`uq_users_username`、`uq_user_sessions_token_hash` UNIQUE 生效；`fk_user_sessions_user_id_users ON DELETE RESTRICT` 拒绝删除带会话用户（B19）；`ix_user_sessions_user_id`、`ix_user_sessions_expires_at` 存在（B20）；`downgrade 0001_baseline` 对称可逆（新表无历史数据）→`upgrade head` 收敛。FAIL：约束/索引缺失或名称不符、downgrade 残留表、CHECK 允许非法枚举、UUID 未自动生成、FK 误用 CASCADE |

### 2. 边界与并发场景（B 编号，TEST 阶段执行）

| 编号 | 场景 | 步骤 | 判据 |
| --- | --- | --- | --- |
| B1 | 登录成功 | bootstrap ADMIN 后 POST `/auth/login` 正确凭据 | 200；`Set-Cookie csm_session`；body user 含 role 与 permissions 集合；`expires_at` 与 DB 会话行 `expires_at` 一致；DB 新增 1 条 `user_sessions`，`token_hash` 为 64 位 hex 且不等于 Cookie 明文 |
| B2 | 登录失败（凭据错误） | POST 错误密码；POST 不存在用户名 | 均 401 `AUTH_INVALID_CREDENTIALS`；**两类响应 body 与耗时语义一致**（不泄露账号是否存在）；非 5xx；无会话行写入 |
| B3 | 停用账号登录与即时失效 | 将 ADMIN `status` 置非 ACTIVE：①再登录；②持有旧会话请求 `/auth/me` | ①401 `AUTH_INVALID_CREDENTIALS`；②既存有效会话立即 401（请求时 join users 校验）；账号行保留（无 deleted_at） |
| B4 | 会话过期 | 将会话 `expires_at` 置过去（直接改测试库）后请求 `/auth/me` | 401 `AUTH_REQUIRED`；**不做滑动续期**（不因请求更新 `expires_at`/`last_seen_at` 作为续期依据）；过期会话不返回用户数据 |
| B5 | 登出即时失效 | 登录 → POST `/auth/logout` → 用原 Cookie 请求 `/auth/me` | logout 204 且 `Set-Cookie` 清除；DB 对应 `user_sessions` 行被删除；后续 `/auth/me` 401；无 Cookie 调用 logout → 401 |
| B6 | Cookie 属性 | 检查 login 响应 `Set-Cookie` 头 | 含 `HttpOnly`、`SameSite=Lax`、`Path=/`；生产配置下含 `Secure`；会话令牌不出现在 JSON body；`csm_session` 名符合 Contract |
| B7 | bootstrap 重复运行 no-op | 干净库首次 bootstrap 成功后再次运行 | 第二次退出码 0；`users` 行数与内容不变；无新增 `user_sessions`；日志含 no-op 说明 |
| B8 | bootstrap 空表缺凭据 | 干净空库、`INITIAL_ADMIN_USERNAME/PASSWORD` 缺失或为空 | 非零退出；输出明确缺凭据提示；`users` 仍为空（无部分写入）；不泄露任何默认凭据 |
| B9 | 并发 bootstrap 唯一性兜底 | 两条独立连接/进程并发执行 bootstrap（真实提交） | 最终 `users` 恰 1 个 ADMIN；`username` UNIQUE 使竞争方失败/收敛为 no-op，不产生重复或乱码数据；多次重跑仍稳定 |
| B10 | 401/403/409 错误信封形状 | 分别触发未认证、越权、版本冲突 | 均为 `{"error":{"code","message","details"}}`；401 `AUTH_REQUIRED`/`AUTH_INVALID_CREDENTIALS`、403 `FORBIDDEN`、409 `VERSION_CONFLICT`；409 `details.current_version` 为整数；404/422/500 形态一致且 500 不含堆栈/凭据 |
| B11 | 权限矩阵逐行 × 角色 | 以生产 `require_permission` 依赖挂载各能力测试路由；对 VIEWER/EDITOR/ADMIN 各持有效会话遍历 §23 六行 | 逐格断言：①查询/搜索/详情（READ）三角色 200；②查看变更记录（VIEW_ACTIVITY）三角色 200；③新增修改/分配解绑（WRITE）EDITOR/ADMIN 200、VIEWER 403；④导入（IMPORT）EDITOR/ADMIN 200、VIEWER 403；⑤删除/释放/查看已删除/恢复（DELETE_OBJECT/RELEASE_IP/VIEW_DELETED/RESTORE）仅 ADMIN 200、VIEWER/EDITOR 403；⑥用户/角色/系统设置/完整审计（USER_ADMIN/AUDIT_READ）仅 ADMIN 200、VIEWER/EDITOR 403。共 6 行 × 3 角色，且未认证均为 401（先于 403）。**R1**：测试路由必须复用生产依赖工厂，不得重写鉴权逻辑 |
| B12 | 敏感内容扫描（响应 + 日志） | 触发登录成功/失败、`/auth/me`、bootstrap 缺凭据等路径，收集响应体与后端日志 | 响应体、错误信封、容器日志（`docker compose logs`）均无密码、`password_hash`、令牌明文字符串；日志无 `Set-Cookie` 值、无请求体凭据；bootstrap 失败提示不含凭据值 |
| B13 | 无注册端点 | 遍历 `app.routes` 与 OpenAPI；请求候选注册路径 | 无 register/signup/创建用户匿名路由；`/api/v1/auth/register` 非 2xx（404/405）；无 `POST /api/v1/users` 匿名创建入口 |
| B14 | 版本冲突机制级 | 经测试挂载的生产版本冲突抛出点（或对 `users.version` 条件更新）提交过期 version | 返回 409 `VERSION_CONFLICT` + `current_version`；数据库未被过期写入覆盖（当前值保持）；前端 client 对 409 不自动重试（机制级用例，业务端到端归 F003） |
| B15 | users CHECK 拒绝非法角色/状态/版本（DB 层） | 以 raw SQL 直插 `role='SUPERUSER'`、`status='BOGUS'`、`version=0`；另试合法枚举 | 真实 PG 抛 `IntegrityError`（CHECK `ck_users_role`/`ck_users_status`/`ck_users_version`）；合法 `VIEWER/EDITOR/ADMIN`、`ACTIVE/DISABLED`、`version>=1` 通过；约束名与 DATABASE 定稿（DB-D15）一致 |
| B16 | username 归一化与唯一性（DB-D14） | 创建用户名含大小写/首尾空白变体（`Admin`、` admin `）；直插大写/短于 3/非法字符/重复用户名 | 服务层归一化为小写并去空白后比较；大小写不敏感重复被 `uq_users_username` 拒；**单列归一化，无独立归一化键列**；绕过应用直插 `'Admin'`、`'ab'`、`'bad name'` 均被 `ck_users_username_format` 拒绝；停用账号仍占用其用户名 |
| B17 | CSRF 同源校验（PROPOSED 纵深） | 携带 Cookie 的不安全方法（POST login/logout）分别带/不带同源 `Origin`/`Sec-Fetch-Site` | 按 CONTRACT 定稿：异源不安全请求被拒；同源正常。**PROPOSED**，若 CONTRACT 未签核则记 NOT_TESTED 并说明 |
| B18 | UUID 主键默认生成（DB-D13） | 不显式传 `id` 插入 `users`/`user_sessions`（ORM 与 raw SQL 各一次） | 两表 `id` 均为合法 UUID（version 4）；`server_default = gen_random_uuid()`；无 `pgcrypto`/`uuid-ossp` 扩展依赖（断言 `pg_extension` 无二者，依据 f001-baseline §3）；F003 沿用形态（记录至 D01 约定，F002 仅核对不回归） |
| B19 | FK ON DELETE RESTRICT（DB-D16） | 对有会话用户的 `users` 行执行 `DELETE`（raw SQL）；再删无会话用户 | 前者抛 `IntegrityError`/`ForeignKeyViolation`（`fk_user_sessions_user_id_users ON DELETE RESTRICT`），会话行与用户行均保留（不静默丟弃历史身份）；后者成功；**不得为 CASCADE** |
| B20 | 索引与唯一约束存在断言（DB-D16/DB-D17） | 查询 `pg_indexes`/`pg_constraint` 与 SQLAlchemy `inspector` | 存在 `ix_user_sessions_user_id`、`ix_user_sessions_expires_at`、`uq_users_username`、`uq_user_sessions_token_hash`、`pk_users`/`pk_user_sessions`；名称与 DB-D6 命名一致；重复 `token_hash` 插入被 `uq_user_sessions_token_hash` 拒绝 |
| B21 | 其余 CHECK 与迁移可逆性（DB-D17） | ①raw SQL 直插 `token_hash` 非 64 hex、`expires_at <= created_at`、空 `password_hash`；②`alembic downgrade 0001_baseline` 后再 `upgrade head` | ①依次被 `ck_user_sessions_token_hash_format`、`ck_user_sessions_expires_after_created`、`ck_users_password_hash_nonempty` 拒绝；②downgrade 后 `users`/`user_sessions` 与索引均不存在，upgrade 后重建收敛，单一 head，行为对称（新表无数据） |

并发说明：B9 与 B14 需真实并发/真实提交，使用 `committed_engine`（F001 fixture）而非 savepoint 回滚；断言最终持久化状态，不仅“未抛异常”。B15/B18/B19/B20/B21 必须在真实 PostgreSQL 执行（SQLite 不作 CHECK/UUID 默认/FK/索引证据）。

### 3. 夹具 / 环境设计

**复用 F001 `backend/tests/conftest.py`（不改其护栏语义）**：
- `test_database_url`：DB-D10 独立测试库 + 安全护栏（库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`）；未设置则 skip 并告警，不静默改 SQLite。
- `pg_engine`：会话级 `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `alembic upgrade head`，会话结束清理。
- `db_session`：函数级外层事务 + savepoint，回滚不跨用例污染。
- `committed_engine`：真实提交用例（B9/B14），teardown `TRUNCATE`（排除 `alembic_version`）。

**F002 新增认证 fixture（建议置于 `backend/tests/conftest.py` 或 `backend/tests/auth/conftest.py`；实现阶段由 Backend 落地，Tester 可调整测试侧）**：
- `bootstrap_admin`：以测试环境变量（`INITIAL_ADMIN_USERNAME/PASSWORD`，测试专用、git-ignored）运行 `app.cli.bootstrap_admin`（直接调用入口函数或 subprocess），返回凭据与 user 行；覆盖 V2/B7/B8。
- `make_user(role, status=ACTIVE, password=...)`：ORM 工厂直接插入 VIEWER/EDITOR/ADMIN 与停用账号，供 B11/B3；密码用与生产同一 argon2id 哈希函数生成，避免伪造语义。
- `anon_client` / `auth_client`：`httpx.Client(transport=ASGITransport(app))` 或 `TestClient`。**Cookie 处理**：`auth_client` 复用同一 `cookies` 罐以携带 `csm_session`；断言通过解析 `response.headers["set-cookie"]` 属性而非仅 `client.cookies` 值。
- `login(client, username, password)`：辅助函数，登录并返回响应 + 会话。
- `log_capture`：`pytest` `caplog`（或注入 handler 到应用 logger）捕获 auth 路径日志；Compose 冒烟另用 `docker compose logs` 扫描（V5/B12）。
- 测试应用构造：以 `create_app()` 为基础按需 `app.include_router`/临时挂载测试路由；**R1 的 403 证据路由必须使用生产 `require_permission` 依赖工厂**，仅路由声明位于测试侧，鉴权实现不得在测试内重写。
- 前端机制级：client 对 401/403/409 的处理用例，以受控响应对 `src/api/client.ts` 断言（401 清态、403/409 明确呈现、不自动重试）；真实浏览器 DOM 渲染不作 F002 必要判据（同 F001 E.5）。

**环境**：Docker / Compose 可用（F001 TE-1 已证）；真实 PG 经 Compose `db`（`postgres:16`）。宿主机无 `psql`/`pg_dump` 不影响本 Feature（无备份脚本需求；DB 断言经 SQLAlchemy/容器内 psql）。若 Compose 不可用，V1/V2 的 Compose 子项记 BLOCKED，真实 PG 后端集成可经本机 PG 补测；不得以 SQLite 替代约束证据。

### 4. 可验证性检查

| 项 | 判定 | 说明 |
| --- | --- | --- |
| A1 可观察 | 可验证 | 登录响应、Cookie、错误码、日志均可断言 |
| A2 可观察 | 可验证 | bootstrap 退出码、行数、静态检索 |
| A3 可观察 | 可验证 | 路由/OpenAPI 清单 |
| A4 机制级 | 可验证（限定口径） | 依赖工厂 401/403 可在测试挂载路由上完整验证；**真实业务端点鉴权端到端归 F003** |
| A5 可观察 | 可验证 | 响应体 + 日志捕获/容器日志扫描 |
| A6 机制级 | 可验证（限定口径） | 409 信封 + 异常映射 + 无自动重试可验证；**真实业务过期编辑端到端归 F003/T26** |
| A7 映射 | 可验证 | 见 §5 |
| 权限矩阵 | 可验证（R1） | 测试挂载生产依赖路由；真实路径 F003。此口径为 MEDIUM 风险，须在 Test Report 显式标注证据边界 |
| bootstrap 并发 | 可验证 | `committed_engine` 真实并发提交 + `uq_users_username` 兜底断言 |
| users/user_sessions CHECK（DB 层） | 可验证（DB 定稿） | 真实 PG raw SQL 断言 `ck_users_role`/`ck_users_status`/`ck_users_version`/`ck_users_username_format`/`ck_users_password_hash_nonempty`/`ck_user_sessions_token_hash_format`/`ck_user_sessions_expires_after_created` 拒绝非法值 |
| UUID 默认 / FK RESTRICT / 索引（DB 层） | 可验证（DB 定稿） | `gen_random_uuid()` 自动生成 UUID；`ON DELETE RESTRICT` 拒绝删除带会话用户；`ix_user_sessions_user_id`/`ix_user_sessions_expires_at` 与唯一约束存在断言；均在真实 PG |
| 迁移 0002 可逆性 | 可验证（DB 定稿） | 真库 up/down/up 对称，单一 head；新表无历史数据 |

口径明确记录：**A4/A6 在 F002 只验证机制级**；不将测试挂载路由或机制用例视为业务端到端通过。等价地，F002 Test Report 不得将 T25/T26 标为整体 PASS。

### 5. T25/T26 子集映射（F002 vs F003）

| 来源用例 | F002 覆盖的断言 | 验证项 | 留待 F003 的断言 |
| --- | --- | --- | --- |
| **T25** 权限矩阵在服务端执行；EDITOR 可导入/解绑，不能删除/释放/恢复；VIEWER 可查看资源 Activity，不能查询完整 Audit | 服务端权限矩阵逐行 × 角色执行（§23 六行 × 三角色）、未认证 401 / 越权 403、EDITOR 与 VIEWER 对 ADMIN-only 能力 403、VIEWER/EDITOR 对 WRITE/IMPORT 的允许/拒绝 | V4 / B11 | 真实业务端点的矩阵行为：EDITOR 导入（F009/F010）、EDITOR 解绑 IP、EDITOR/VIEWER 删除/释放/恢复结果、VIEWER 查看资源 Activity、VIEWER 不能查询完整 Audit（F003/F016）。**完整 T25 在 F003 交付后回归** |
| **T26** 过期版本编辑被拒绝，无静默覆盖；审计保留历史操作者，不记录或展示密码/令牌 | 409 `VERSION_CONFLICT` 信封与 `current_version`、过期版本不被覆盖、前端不自动重试、认证响应与日志不含密码/令牌明文 | V5 / V6 / B10 / B12 / B14 | 真实业务对象过期编辑端到端（乐观锁持久化）、审计写入保留历史操作者、审计不记录/不展示密码令牌、审计写入一致性（F003）。**完整 T26 在 F003 交付后回归** |

### 6. 不适用项与边界声明

- **业务对象矩阵回归**（Cluster/Resource/Interface/Network/IPPool/IPAddress/Service/ServiceEndpoint 的权限与约束端到端）：F002 无业务对象与业务端点；归 F003–F013。
- **Audit 写路径**（operator/before/after、Activity 展示）：F002 仅注入操作者上下文骨架，不写 Audit；归 F003/F016。
- **用户管理 UI 与账号管理流程**（用户列表、改密、启停界面）：归 F015；F002 仅有最小登录壳与后端账号模型。
- **已删除对象查看/恢复**：F002 无软删业务对象；归 F003/F015。
- **持久化横切端到端**（deleted_at/Audit/乐观锁端到端/归一化）：随 F003 首落地。
- **登录限流**：本期不实现（§29 无 Redis，架构记 NOTE）→ NOT_REQUIRED；若后续引入记独立变更。
- **完整 CSRF 防护**：仅 SameSite=Lax + Origin/Sec-Fetch-Site 同源校验（PROPOSED，R2）；B17 视 CONTRACT 定稿执行，否则 NOT_TESTED。
- **§32 整体上线验收**：归 F016；Feature 通过 ≠ 上线授权。
- **真实浏览器 DOM 渲染**：非 F002 必要判据（同 F001 E.5），前端以构建 + client 机制级用例为准。

### 7. 环境可执行性评估与风险（R1/R2/R3）

| 项 | 评估 | 处理 |
| --- | --- | --- |
| V1/V2（Compose + 真实 PG） | Docker/Compose 可用（F001 TE-1 已证）；**可执行** | 若镜像拉取/端口冲突 → 记 BLOCKED 并说明，不降验收 |
| V4/B11（R1：403 证据依赖测试挂载路由） | **MEDIUM**：F002 无真实 ADMIN-only 业务端点 | 测试路由复用生产 `require_permission`；Test Report 显式标注“机制级证据、真实业务端点归 F003”，不得表述为完整 T25 通过 |
| V6/B14（A6 机制级） | **限定口径**：409 机制与无重试可验证，端到端归 F003 | 同 §5 T26 行 |
| B9 并发 bootstrap | 需真实并发提交 fixture | 复用 `committed_engine`；断言最终唯一 ADMIN |
| V5/B12 日志捕获 | 应用日志 Filter + caplog + 容器日志 | 覆盖响应与日志两处；auth 端点绝不记录请求体 |
| R2 CSRF 残余 / 无登录限流 | LOW；PROPOSED 纵深 | B17 依赖 CONTRACT；限流 NOT_REQUIRED 并记录 |
| R3 argon2-cffi 依赖锁定 | LOW | 由实现报告/Review 核对依赖锁定；Tester 检查可导入与哈希参数可升级（PHC 串） |

### 8. OPEN 复核结果（对照 TD-1 §8 ↔ DATABASE Gate / CONTRACT Gate）

| # | TD-1 假设 | TD-2 结论 | 依据 |
| --- | --- | --- | --- |
| 1 | 约束与列定稿（`varchar+CHECK`、`ck_` 命名、`username`/`token_hash` UNIQUE、FK 删除行为） | **CLOSED（DATABASE）** | `docs/database/f002-auth.md` §3/§4：DB-D15（varchar+CHECK，名称 `ck_users_role`/`ck_users_status` 等）、DB-D14（`uq_users_username` + `ck_users_username_format`）、`uq_user_sessions_token_hash`、DB-D16（FK RESTRICT）；V9/B15/B16/B18–B21 已按定稿更新 |
| 2 | users.id UUID 形态与 D01/F003 对齐 | **CLOSED（DATABASE）** | DB-D13：PG 原生 UUID + `gen_random_uuid()`，F003 沿用；B18 核对（含 F003 对齐仅记录，不在 F002 回归） |
| 3 | 错误码定稿（`AUTH_REQUIRED`/`AUTH_INVALID_CREDENTIALS`/`FORBIDDEN`/`VERSION_CONFLICT`/`VALIDATION_ERROR`/`NOT_FOUND`/`INTERNAL_ERROR`、`details.current_version`） | **OPEN（待 CONTRACT）** | `architecture.md` §1.6/DR-10 仍为 PROPOSED；TD-2 暂按草案口径写 V6/B10/B14；`docs/api/F002.md` 定稿后逐项核对，差异则升 TD-3 |
| 4 | CSRF 口径（Origin/Sec-Fetch-Site 是否强制） | **OPEN（待 CONTRACT）** | `architecture.md` §1.1/DR-08 仍为 PROPOSED 纵深；B17 视 CONTRACT 定稿执行，否则 NOT_TESTED |
| 5 | bootstrap CLI 调用形态与退出码 | **部分 CLOSED / 部分 OPEN** | DATABASE 已确认 bootstrap 为**应用侧 CLI、非迁移**（DB-D17/DR-12，迁移只建 Schema）；但 CLI 函数入口 vs subprocess、退出码约定仍待 CONTRACT/实现核对，影响 V2/B8 fixture 实现方式 |

TD-1 对 DATABASE Gate 的 5 项假设中第 1、2 项已由 `docs/database/f002-auth.md` v1 关闭，旧预期（未命名约束、UUID 形态待定、username 归一化键列）失效；第 3–4 项与第 5 项细化部分仍待 CONTRACT Gate 定稿。上述未关闭项不影响 READY 结论（方案可验证）；TEST 执行前必须逐项关闭并核对 CONTRACT 定稿差异。

---

## Test Execution

### TE-1 版本记录

- **版本**：TE-1
- **日期**：2026-10-07
- **角色**：Tester（TEST 模式，独立执行）
- **结论**：`READY FOR REVIEW`
- **被测版本**：`git rev-parse --short HEAD` = `30feb0f`（实现提交 `4ce9841`；`git diff --stat 4ce9841..HEAD -- backend frontend compose.yaml .env.example` 为空，被测代码与实现提交一致）
- **依据**：TD-2；`docs/api/F002.md` v1（CONTRACT READY）；`docs/features/F002/architecture.md`（最终设计定稿）；`docs/database/f002-auth.md` v1（DB-D13–DB-D19）；`docs/features/F002/implementation.md`。TD-2 §8 第 3–5 项已由 CONTRACT 定稿关闭（错误码 7 项、CSRF 同源校验、bootstrap CLI 形态与退出码），本版按定稿口径执行 B17。
- **范围声明**：A4/A6 仍为机制级证据（测试挂载生产 `require_permission` 依赖路由、409 信封机制），**不构成完整 T25/T26 通过**；真实业务端点与端到端乐观锁归 F003。

### 环境

| 项 | 值 |
| --- | --- |
| Docker / Compose | 29.8.0 / v5.5.1（可用） |
| Node / npm | v22.23.2 / 12.0.2 |
| 宿主 psql / pg_dump | 不存在（符合预期，本 Feature 不依赖） |
| 后端测试镜像 | `backend/Dockerfile` target `test` 构建自被测源（Python 3.12.15、pytest 8.4.2、httpx、argon2-cffi） |
| 真实 PostgreSQL（集成） | `postgres:16.15`，独立库 `csm_test`（DB-D10 护栏：库名含 `test`、`TEST_DATABASE_URL != DATABASE_URL`） |
| 真实 PostgreSQL（CLI/并发/迁移探针） | 同上，独立库 `csm_cli_test`、`csm_conc_test` |
| Compose 全链路 | 独立项目名 `f002te`、入口端口 `18080`、`postgres:16`、`APP_ENV=development`；结束 `docker compose -p f002te down -v` 清理 |
| 未执行环境 | 生产/未知数据库（未使用）；本机 venv（宿主不可用，改用容器） |

### 执行命令与输出摘要（独立执行，未复制开发者结果）

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `docker build --target test -t csm-backend-f002te:latest ./backend` | 构建成功 |
| 2 | `pytest tests -v`（容器内、真实 PG `csm_test`） | **47 passed, 1 skipped, 1 warning**（skip = F001 V3b 非 superuser 扩展，环境限制） |
| 3 | `python -m app.cli.bootstrap_admin` 真实 CLI（缺凭据 / 正常 / 重复 / 不可达） | 退出码 **2 / 0 / 0 / 1**；缺凭据无写行；重复 no-op |
| 4 | 两个并发 CLI 进程（`csm_conc_test`，真实提交） | 两进程均 exit 0，最终 `users` 恰 1 行 ADMIN；重跑稳定 no-op |
| 5 | `psql` 直插非法值（raw SQL，非 SQLAlchemy） | role/version/username/token_hash/expires/password_hash 均被对应 CHECK 拒绝；UUID 自动生成；FK RESTRICT 拒绝删除带会话用户（`confdeltype='r'`，两行保留）；DISABLED 账号仍占 `uq_users_username` |
| 6 | `alembic downgrade 0001_baseline` → `upgrade head`；`alembic heads` | 对称可逆、单一 head `0002_users_sessions` |
| 7 | 静态：`git ls-files` / `git check-ignore` / `git grep` | 无跟踪 `.env`（已被忽略）；无真实初始凭据/hardcoded 密码（仅测试夹具口令） |
| 8 | `docker compose -p f002te up -d --build`（18080） | `db→migrate(exit 0)→bootstrap(exit 0, created opsadmin)→backend(healthy)→nginx` |
| 9 | 经入口 Nginx：login→/auth/me→logout→/auth/me；错误/注册/CSRF 探针 | 见 A/V/B 映射与 D-TE-1 |
| 10 | `docker compose -p f002te exec backend python -m app.cli.bootstrap_admin` | 已有用户 → no-op exit 0，用户数不变（幂等，且先于凭据校验） |
| 11 | Compose 日志敏感扫描 `docker compose logs` | 无密码/口令/`password_hash`/argon2 串/`Set-Cookie` 值/`csm_session` 明文 |
| 12 | 前端 `npm run smoke:client`（宿主 Node 22） | **10 passed, 0 failed**（401 清态、403/409 呈现且不重试、204、信封回退） |

### 验收映射（A1–A7）

| 验收 | 结果 | 证据 |
| --- | --- | --- |
| A1 初始 ADMIN 登录成功、错误凭据鉴权失败、响应/日志无凭据明文 | **PASS** | 集成 `test_login_success_creates_session`/`test_login_failures_are_indistinct`；Compose 入口 login 200 + Cookie，错误口令/未知用户均 401 `AUTH_INVALID_CREDENTIALS`，无 5xx；日志扫描无凭据 |
| A2 干净环境唯一首个 ADMIN、重复不重复创建、仓库无真实凭据 | **PASS** | CLI 退出码 2/0/0/1；两个并发进程 → 1 ADMIN；Compose bootstrap exit 0；静态检查无跟踪 `.env`、无真实凭据 |
| A3 无自行注册路径 | **PASS** | `app.routes`/OpenAPI 无 register/signup；`POST /auth/register`→404、`/signup`→404 |
| A4 受保护端点服务端鉴权（未认证 401、越权 403） | **PASS（机制级，R1）** | 生产 `require_permission` 依赖挂载测试路由：未认证 401 `AUTH_REQUIRED`；§23 六行 × VIEWER/EDITOR/ADMIN 逐格断言；越权 403 `FORBIDDEN{reason:permission}`。真实业务端点归 F003 |
| A5 日志与响应无密码/令牌明文 | **PASS** | 集成响应体扫描 + caplog；Compose 容器日志扫描；令牌仅出现在 `Set-Cookie`，不出现在 JSON |
| A6 过期版本 409 语义、无静默重试覆盖 | **PASS（机制级）** | 409 `VERSION_CONFLICT` + `details.current_version`（整数）；前端 client 对 409 明确呈现且不重试（smoke 用例）。业务端到端归 F003/T26 |
| A7 T25/T26 认证/权限子集有可执行映射 | **PASS** | TD-2 §5 映射表；F002 内断言分别落 V4/V5/V6/B11，明确列留待 F003 项；**不宣称完整 T25/T26** |

### 验证项 V1–V9 结果

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| V1 登录流程 | PASS | 集成 + Compose 入口：200、`user{id,username,role,status,permissions}`、`expires_at` 与 DB 会话行一致；错误密码 401 非 5xx；无明文 |
| V2 bootstrap 幂等 + V9 迁移 | PASS | CLI 退出码、并发唯一、Compose 一次性服务、迁移 up/down/up（见 B7–B9/B20/B21） |
| V3 无注册端点 | PASS | 路由/OpenAPI 清单 + 404 |
| V4 鉴权执行 | PASS（机制级） | B11 六行 × 三角色 |
| V5 敏感内容扫描 | PASS | 响应 + caplog + Compose 日志 |
| V6 版本冲突机制级 | PASS | B14 |
| V7 T25/T26 子集映射 | PASS | §5 映射 |
| V8 会话/Cookie | PASS | B4–B6；Compose 入口 Cookie 属性；生产 `Secure` 由集成用例证明 |
| V9 Schema/约束/迁移 | PASS | B15–B21（真实 PG，raw SQL 复核） |

### 边界场景 B1–B21 结果

| 编号 | 结果 | 证据摘要 |
| --- | --- | --- |
| B1 登录成功 | PASS | 200；`Set-Cookie csm_session`；DB 1 条会话，`token_hash`=SHA-256(Cookie)、64 hex，token_hash≠明文；`expires_at` 一致 |
| B2 登录失败不可区分 | PASS | 错误口令与未知用户 body 完全相同（401 `AUTH_INVALID_CREDENTIALS`，`details={}`），无会话写入。**说明**：耗时以未知用户 dummy-hash 机制均衡，未做统计显著性测量 |
| B3 停用账号登录与即时失效 | PASS | 持旧会话 `/auth/me`→401 `AUTH_REQUIRED`；再登录→401 `AUTH_INVALID_CREDENTIALS`；用户行保留（无 `deleted_at`） |
| B4 会话过期、不滑动续期 | PASS | 将 `expires_at` 置过去→401 `AUTH_REQUIRED`；`/auth/me` 前后 `expires_at` 不变 |
| B5 登出即时失效 | PASS | logout 204 + `Max-Age=0`；会话行删除；后续 `/auth/me` 401；无 Cookie 调 logout 401 |
| B6 Cookie 属性 | PASS | `HttpOnly; SameSite=lax; Path=/`；development 无 `Secure`、`APP_ENV=production` 含 `Secure`（集成）；令牌不出现在 body；名 `csm_session` |
| B7 bootstrap 重复 no-op | PASS | 二次运行 exit 0，行数与内容不变 |
| B8 空表缺凭据 | PASS | CLI exit 2、stderr 明确提示、`users` 仍 0 行、无默认凭据 |
| B9 并发 bootstrap 唯一性 | PASS | 两独立进程并发，均 exit 0，最终恰 1 ADMIN；重跑稳定 |
| B10 401/403/409 错误信封 | PASS | `{"error":{code,message,details}}`；401 `AUTH_REQUIRED`/`AUTH_INVALID_CREDENTIALS`、403 `FORBIDDEN`、409 `VERSION_CONFLICT`（`details.current_version` 整数）、404 `NOT_FOUND`、405 `METHOD_NOT_ALLOWED`、422 `VALIDATION_ERROR`、500 `INTERNAL_ERROR`（无堆栈/凭据） |
| B11 权限矩阵 × 角色 | PASS（R1 机制级） | §23 六行 × 三角色逐格断言，未认证 401 先于 403；测试路由复用生产依赖工厂 |
| B12 敏感内容扫描 | PASS | 响应、caplog、Compose 容器日志均无密码/令牌/`Set-Cookie` 值 |
| B13 无注册端点 | PASS | 路由 + OpenAPI + 候选路径 404 |
| B14 版本冲突机制级 | PASS | 409 + `current_version`；过期写入不覆盖；前端不自动重试 |
| B15 users CHECK（DB 层） | PASS | raw SQL 拒绝 `role='SUPERUSER'`、`version=0`（集成含 `status='BOGUS'`）；约束名与 DB-D15 一致 |
| B16 username 归一化与唯一 | PASS | 服务层 `'  Admin  '`→`admin`；raw SQL 拒绝 `'Admin'`/`'ab'`/`'bad name'`；重复被 `uq_users_username` 拒；停用账号仍占名 |
| B17 CSRF 同源校验 | PASS（应用层）；入口非默认端口见 D-TE-1 | ASGI：异源 `Origin`/`Sec-Fetch-Site: cross-site` → 403 `{reason:csrf}`；`Sec-Fetch-Site: same-origin`、`AUTH_ALLOWED_ORIGINS` 放行。Compose 入口 18080：异源 403；同源 `Origin: http://localhost:18080` 亦 403（D-TE-1） |
| B18 UUID 主键默认生成 | PASS | raw SQL 不传 id 两表均得合法 UUID v4；`pg_extension` 仅 `pg_trgm`,`plpgsql`，无 `pgcrypto`/`uuid-ossp` |
| B19 FK ON DELETE RESTRICT | PASS | 删除带会话用户抛 FK 违规，用户/会话行均保留；无会话用户可删；`confdeltype='r'`（非 CASCADE） |
| B20 索引与唯一约束存在 | PASS | 目录核对：`pk_users`/`uq_users_username`/五个 `ck_users_*`/`pk_user_sessions`/`uq_user_sessions_token_hash`/`fk_user_sessions_user_id_users`/两个 `ck_user_sessions_*`；`ix_user_sessions_user_id`、`ix_user_sessions_expires_at`；重复 `token_hash` 被拒 |
| B21 其余 CHECK 与迁移可逆 | PASS | 非 64-hex `token_hash`、`expires_at<=created_at`、空 `password_hash` 均被拒；`downgrade 0001_baseline` 后两表与索引消失、`upgrade` 重建、单一 head |

### 数据库层核对（对照 DB-D13–D19）

- 约束名、FK 删除行为、索引、UUID 默认、迁移 up/down/up 与 `docs/database/f002-auth.md` v1 逐项一致（raw SQL 与 `pg_constraint`/`pg_indexes` 独立核对，非仅 ORM）。
- 无历史数据：迁移 0002 为新表，`downgrade` 对称 drop 可接受（DB-D7）。
- 真实 PostgreSQL 执行（SQLite/Mock 未作为约束证据）。

### 接口 / 前端 / 集成结果

- **接口**：经入口 Nginx `/api/v1/*` 全链路（login `/auth/me` logout）返回内容、类型、业务边界与错误语义符合 Contract §1/§4；只读 `/auth/me` 无写副作用；无注册入口。
- **前端**：构建产物经入口 200、SPA fallback `/login` 200、asset 200；client 对 401 清态、403/409 明确呈现、无静默重试（`npm run smoke:client` 10/10）。真实 API 集成经入口 Nginx 验证，未以 Mock 代替。
- **Compose**：`db→migrate→bootstrap→backend→nginx` 链路按 `depends_on` 条件依次完成；bootstrap 幂等；入口健康 `/healthz` 200、后端 `health/ready` 200。

### Defects

| ID | Severity | Layer | Location | 证据 / 复现 | 期望 vs 实际 | 影响 | Owner | 是否必须修复 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D-TE-1 | MEDIUM | 部署/集成（F002 CSRF × F001 入口 Nginx） | `deploy/nginx/nginx.conf`（`proxy_set_header Host $host`）+ `backend/app/core/csrf.py` `_is_same_origin` | Compose 项目 `f002te` 端口 18080：login 成功后 `POST /api/v1/auth/logout` + `Cookie` + `Origin: http://localhost:18080` → `403 FORBIDDEN{"reason":"csrf"}`；后端实际看到 `Host: localhost`（无端口）。对照：显式 `Host: localhost` + `Origin: http://localhost` → 204 | 同源不安全请求应放行；非默认入口端口下被拒 | 当 `NGINX_HTTP_PORT != 80`（F001 架构标注“主机 80（可配置）”）时，浏览器同源写请求（logout 及 F003+ 写端点）会被 CSRF 纵深守卫误拒；默认 80/443 部署不受影响；不构成跨站放行（安全性未削弱） | Backend（CSRF Host 处理）/ 协调器（Nginx `Host` 传递，可用 `$http_host` 或改用 `X-Forwarded-Host`） | 否（不阻塞默认部署验收；缓解：设置 `AUTH_ALLOWED_ORIGINS=http://<host>:<port>`。建议随本 Feature 或紧随修复并补集成用例） |

### 未验证 / 边界项

- **完整 T25/T26**：不在 F002 范围，未声称通过；A4/A6 为机制级。
- **真实业务对象过期编辑端到端、Audit 写路径、持久化横切**：归 F003/F016。
- **登录限流**：本期 NOT_REQUIRED（§29 无 Redis），未实现未测。
- **B2 耗时等同**：以 dummy-hash 机制保证，未做统计测量。
- **F001 V3b（非 superuser 扩展安装）**：测试 PG 角色为 superuser，1 skipped（F001 既有环境限制，非 F002 回归）。
- **前端真实浏览器 DOM 渲染**：非 F002 必要判据；以构建 + client 机制级 + 真实 API 集成覆盖。
- **生产 `Secure` Cookie 仅经 ASGI 集成用例验证**，未在 TLS 入口端到端验证（本期无 TLS 入口要求）。

### Git 声明（TE-1）

```text
GIT: git status --short
GIT: git rev-parse --short HEAD
GIT: git rev-parse --short 4ce9841
GIT: git diff --stat 4ce9841..HEAD
GIT: git diff --stat 4ce9841..HEAD -- backend frontend compose.yaml .env.example
GIT: git ls-files
GIT: git check-ignore -v .env
GIT: git grep -n -Ei '...'
GIT: git log --oneline -5
GIT: git branch --show-current
```

以上均为只读命令；未执行 `git add`/commit/branch/merge，工作区在测试期间保持干净。

---

## Test Execution — 修复循环第 1 轮

### TE-2 版本记录（修复轮次 1 重测）

- **版本**：TE-2
- **日期**：2026-10-07
- **角色**：Tester（TEST 模式，独立重测，未复制 Backend 结果）
- **结论**：`READY FOR REVIEW`
- **被测版本**：分支 `feature/F002-auth-permissions`，`git rev-parse --short HEAD` = `f66562d`；被测修复为**工作区未提交修改** `M deploy/nginx/nginx.conf`（新增 `map $http_host $csm_host` + `/api/`、`/` 的 `proxy_set_header Host/X-Forwarded-Host $csm_host`）。`git status --short` 仅此一项，后端 `backend/app/core/csrf.py` 与其余源文件未改动，确认修复边界未扩及业务实现。
- **依据**：TE-1；TD-2（B17）；`docs/api/F002.md` v1 §2.1（同源校验口径）；`docs/features/F002/architecture.md`（最终设计定稿）；Backend 修复交接（D-TE-1）。
- **范围声明**：本轮只重测受影响项 **D-TE-1（B17 入口非默认端口同源写）** 及相关回归；A4/A6 仍为机制级证据，不构成完整 T25/T26 通过。

#### 重测范围与逐项结论

| # | 重测项 | 判据（Contract §2.1） | 结果 |
| --- | --- | --- | --- |
| 1 | 非默认端口同源写（D-TE-1 本体）：入口 `:18081`，带会话 Cookie 的 `POST /auth/logout` + `Origin: http://localhost:18081` | 同源放行 | **PASS / FIXED**（204） |
| 2 | 非默认端口异源 Origin `http://evil.example.com` | 拒绝 403 csrf | **PASS**（403，`details.reason=csrf`） |
| 3 | 非默认端口 `Sec-Fetch-Site: cross-site` | 拒绝 403 csrf | **PASS**（403 csrf） |
| 4 | 非默认端口 `Sec-Fetch-Site: same-origin` | 放行 | **PASS**（204） |
| 5 | 非默认端口无 Origin/Sec-Fetch-Site（非浏览器客户端） | 放行 | **PASS**（204） |
| 6 | 负向对照：Origin 端口不符 `localhost:9999` | 拒绝（证明比较对端口敏感） | **PASS**（403 csrf） |
| 7 | 负向对照：Origin 无端口 `http://localhost` 访问 `:18081`（旧缺陷行为） | 拒绝 | **PASS**（403 csrf，符合预期，证明分析正确） |
| 8 | 默认端口 `:80` 同源 `Origin: http://localhost` | 放行 | **PASS**（204，行为不变） |
| 9 | 默认端口 `:80` 异源 | 拒绝 403 csrf | **PASS**（403） |
| 10 | 入口回归：`/healthz`=200、前端 `/`=200、SPA fallback `/login`=200、`/auth/me` 携带 Cookie=200 | 正常 | **PASS** |

**D-TE-1 复核结论：FIXED。** 入口 Nginx 现以 `$csm_host`（=`$http_host`，保留客户端 Host 含端口）转发，后端 CSRF 守卫将 `Origin` authority 与含端口的 `Host` 比较，非默认端口同源写请求由 TE-1 的 403 变为 204；异源/`cross-site` 仍 403；负向对照（端口不符、缺端口）仍 403，安全性未削弱。

#### B17 判据说明（是否升 TD）

Contract §2.1 与 TD-2 B17 的判据本身未改变（存在 Origin → authority 须等于请求 Host；`Sec-Fetch-Site` 须 same-origin；皆缺放行）。本轮修复是使**入口部署**符合既有判据，而非变更判据；因此**不升 TD，保留 TD-2**，仅在 TE-2 明确 B17 证据必须覆盖入口非默认端口场景（TE-1 仅覆盖 ASGI 应用层，入口端口场景为本轮补入的 B17 证据）。

#### 回归结果

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量（真实 PG，独立测试库 `csm_test`，独立容器/网络） | `docker build --target test -t csm-backend-f002te2:latest ./backend` → `pytest tests -v`（`TEST_DATABASE_URL` 指向新建 `postgres:16` 容器） | **47 passed, 1 skipped, 1 warning**（skip = F001 V3b 非 superuser 扩展，环境限制，同 TE-1） |
| 前端机制级 | `npm run smoke:client`（宿主 Node 22.23.2） | **10 passed, 0 failed** |
| Compose 全链路（非默认端口 `:18081`） | `docker compose -p f002te2 up -d --build` | `db→migrate(exit 0)→bootstrap(exit 0)→backend(healthy)→nginx`；healthz 200 |
| Compose 默认端口（`:80`，仅重建 nginx） | `docker compose -p f002te2 up -d --no-deps nginx`（`NGINX_HTTP_PORT=80`） | nginx 启动、healthz 200、默认端口行为不变 |

#### 执行命令与输出摘要（独立执行）

| # | 命令（摘要） | 输出摘要 |
| --- | --- | --- |
| 1 | 独立 `postgres:16` 容器 `csm_test` + `docker run … pytest tests -v` | 47 passed, 1 skipped |
| 2 | `npm run smoke:client` | 10 passed, 0 failed |
| 3 | `docker compose -p f002te2 up -d --build`（`NGINX_HTTP_PORT=18081`、`INITIAL_ADMIN_USERNAME=opsadmin`） | 各服务 0/healthy |
| 4 | `curl` 登录 → Cookie；上述 10 项 curl 探针 | 探针 1/4/5/8 =204；2/3/6/7/9 =403 csrf；入口回归全 200 |
| 5 | `docker compose -p f002te2 down -v` + 删除自建 db/网络 | 测试资源已清理，无遗留 |

#### 数据库 / 接口 / 前端 / 集成结果（本轮）

- **数据库**：本轮无 Schema/迁移变更；后端全量含真实 PG 约束/迁移用例，47 passed 覆盖 B15–B21/V9 回归。
- **接口/集成**：经入口 Nginx（`:18081` 与 `:80`）login→Cookie→logout/me 全链路；`/auth/me` 只读无写副作用；错误语义与 Contract §2.1 一致。
- **前端**：本轮修复不触及前端；`npm run smoke:client` 10/10 作为回归。

#### Defects

| ID | Severity | Layer | Location | 状态 | Owner |
| --- | --- | --- | --- | --- | --- |
| D-TE-1 | MEDIUM | 部署/集成（F002 CSRF × F001 入口 Nginx） | `deploy/nginx/nginx.conf`（修复：`map $http_host $csm_host` + `Host/X-Forwarded-Host $csm_host`） | **FIXED（TE-2 独立复核）** | Backend（已完成） |

无新发现缺陷；无仍存在的必须修复问题。

#### 未验证 / 边界项（本轮新增）

- 修复文件在 TE-2 时**尚未提交**（工作区 `M deploy/nginx/nginx.conf`）；提交后 Review 基线应对该文件执行 `git diff HEAD` 核对与本轮被测内容一致。
- 生产 TLS 入口（HTTPS/443）下的同源行为未端到端验证；本轮以 HTTP 默认/非默认端口覆盖（本期无 TLS 入口要求）。
- TE-1 既有未验证项（完整 T25/T26、真实业务端到端、登录限流 NOT_REQUIRED、B2 耗时不作统计测量、浏览器 DOM、生产 `Secure` 仅 ASGI 验证）继续有效，未因本轮修复改变。

### Git 声明（TE-2，只读）

```text
GIT: git status --short
GIT: git branch --show-current
GIT: git rev-parse --short HEAD
GIT: git log --oneline -8
GIT: git diff --stat
GIT: git diff deploy/nginx/nginx.conf
```

以上均为只读命令；本轮未执行 `git add`/commit/branch/merge，测试自建容器与网络已清理，工作区仅保留 Backend 的 `deploy/nginx/nginx.conf` 修复修改。