# F002 认证、初始账号与权限横切 — Test Report

本文件同时承载 TEST_DESIGN 与 TEST（TEST 阶段在同一文件追加执行结果）。两阶段分别记录版本、结论与证据，TEST_DESIGN 不填充执行 PASS。

---

## Test Design

- **版本**：TD-1
- **日期**：2026-10-06
- **角色**：Tester（TEST_DESIGN 模式）
- **结论**：`TEST DESIGN READY`
- **依据**：
  - `docs/product/requirements-v3.md` revision 3（§21–§23、§25–§27、§29–§31、§35.2/§35.3 D02）
  - `docs/features/F002/product.md`（READY FOR ARCHITECT；A1–A7 与边界）
  - `docs/features/F002/architecture.md`（READY FOR DESIGN；§1 方案、§5 表草案、§6 验证策略、§7 交 Tester 事项、R1/R2/R3）
  - `docs/features/F001/test-report.md`（TD-2/TE-1 基线与 fixture 约定：DB-D10 独立测试库 + 安全护栏、会话级重建 schema、函数级 savepoint、并发真实提交）
  - `docs/database/f001-baseline.md` v1（DB-D4/D5/D8/D10/D11）
  - `docs/project/project-plan.yaml` plan_revision 4，F002 条目（已批准，IN_PROGRESS，current_stage=DATABASE）
  - `docs/project/implementation-rules.md`（验证与交付）、`AGENTS.md`（数据安全、Git）、`.pi/skills/data-integrity/SKILL.md`
- **状态属性**：READY 仅表示 A1–A7 可映射到可观察判据、边界场景可执行；**不表示测试已运行、不批准实现或合并、不表示 T25/T26 完整通过**。F002 为请求级横切，完整 T25/T26 回归归 F003。
- **前置状态说明**：F002 Database 设计仍在 DATABASE Gate 进行中，本 TD-1 依据 `architecture.md` §1.1/§1.4/§1.6/§5 的 PROPOSED（D02 认证部分、DR-07–DR-16）起草。TEST 执行前必须与 DATABASE Gate 定稿、CONTRACT Gate 定稿（`docs/api/F002.md`）逐项复核；若约束名、列名、错误码或版本机制定稿与本文判据不同，TD-1 升版并注明失效范围（见 §8 OPEN）。

### 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| TD-1 | 2026-10-06 | 初版：A1–A7 映射 V1–V9，边界 B1–B17，夹具/环境设计，T25/T26 子集映射，不适用项；对 DATABASE/CONTRACT Gate 保留 5 项待复核假设。 |

### 0. 数据完整性对应表（F002 范围）

仅列 F002 已确认且在实现后需验证的认证/权限/持久化项；业务对象约束留待 F003+。方法依据 `.pi/skills/data-integrity/SKILL.md`。数据库列为 `architecture.md` §5 草案（待 DATABASE Gate 签核）。

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证与证据 |
| --- | --- | --- | --- | --- | --- |
| §23 revision 3（角色枚举与权限矩阵，服务端执行） | `require_permission` 依赖；`users.role` | `role varchar(16)+CHECK`（草案）拒绝非法值 | `ROLE_PERMISSIONS` 显式 frozenset；未认证 401 / 越权 403 | 无继承隐式授权 | V4/B11/B15；计划验证 |
| §23 / §21（账号停用保留操作者身份，不软删） | `users.status`、会话解析 | `status varchar(16) DEFAULT 'ACTIVE'+CHECK`；**无 deleted_at** | 每次请求 join users 校验 `status='ACTIVE'`；停用即 401 | 停用不删行、旧审计操作者保留 | V8/B3；计划验证 |
| DR-14（username 归一化小写、大小写不敏感唯一） | 登录/bootstrap/用户创建 | `username varchar(64) NOT NULL UNIQUE` | 服务层归一化后比较 | 停用账号仍占唯一名 | B16；计划验证 |
| §23 / DR-08（服务端不透明会话，令牌仅存哈希） | 登录创建会话；Cookie | `user_sessions.token_hash varchar(64) UNIQUE`（SHA-256 hex）；`FK→users.id` | 请求时哈希查询 + 过期判定 | 登出删除行；过期惰性判定，不预建清理 | V8/B4/B5/B6；计划验证 |
| §22 / §30（密码、令牌不记录不展示；真实凭据不入仓） | 日志 Filter；响应 Schema；`.env` | N/A | `SENSITIVE_FIELDS` 脱敏；auth 端点不记录请求体；响应不含 `password_hash` | 错误日志脱敏后输出 | V5/B12；计划验证 |
| §26 / §27（真实 PG 验证；新表 Migration 可逆） | Alembic Migration `users`/`user_sessions` | up/down/up；CHECK 生效 | N/A | 新表无历史数据，downgrade 对称 drop | V9；计划验证 |
| DR-12（bootstrap 幂等、迁移不写业务数据） | 一次性 CLI `app.cli.bootstrap_admin` | `username` UNIQUE 兜底并发 | 事务内“存在任何用户→no-op”；空表缺凭据非零退出 | 并发 bootstrap 唯一性由约束兜底 | V2/B7/B8/B9；计划验证 |

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
| （数据层支撑 A2/A4） | **V9** Schema / 约束 / Migration | 真实 PG | PASS：`alembic upgrade head` → `users`/`user_sessions` 建表；`users.role`/`status` CHECK 拒绝非法值（B15）；`username`、`token_hash` UNIQUE 生效；`downgrade base` 对称可逆（新表无历史数据）；`upgrade head` 收敛。FAIL：约束缺失或未生效、downgrade 残留表、CHECK 允许非法枚举 |

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
| B15 | users CHECK 拒绝非法角色/状态（DB 层） | 以 raw SQL 直插 `role='SUPERUSER'`、`status='BOGUS'` 及非法枚举值 | 真实 PG 抛 `IntegrityError`（CHECK 约束）；合法 `VIEWER/EDITOR/ADMIN`、`ACTIVE/...` 通过；约束名与 DATABASE Gate 定稿一致 |
| B16 | username 归一化与唯一性 | 创建用户名含大小写/首尾空白变体（`Admin`、` admin `）；重复创建 | 服务层归一化为小写并去空白后比较；大小写不敏感重复被拒（DB UNIQUE 兜底）；停用账号仍占用其用户名 |
| B17 | CSRF 同源校验（PROPOSED 纵深） | 携带 Cookie 的不安全方法（POST login/logout）分别带/不带同源 `Origin`/`Sec-Fetch-Site` | 按 CONTRACT 定稿：异源不安全请求被拒；同源正常。**PROPOSED**，若 CONTRACT 未签核则记 NOT_TESTED 并说明 |

并发说明：B9 与 B14 需真实并发/真实提交，使用 `committed_engine`（F001 fixture）而非 savepoint 回滚；断言最终持久化状态，不仅“未抛异常”。B15 必须在真实 PostgreSQL 执行（SQLite 不作 CHECK 证据）。

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
| bootstrap 并发 | 可验证 | `committed_engine` 真实并发提交 + UNIQUE 兜底断言 |
| users CHECK（DB 层） | 可验证 | 真实 PG raw SQL 断言 IntegrityError |

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

### 8. OPEN（交 DATABASE / CONTRACT Gate 复核，TD-1 假设）

1. **约束与列定稿**：`users.role/status` 的 `varchar+CHECK` 及 `ck_` 命名、`users.username UNIQUE`、`user_sessions.token_hash UNIQUE`/FK 删除行为，以 DATABASE Gate 定稿为准；B15/V9 判据随之核对。
2. **users.id UUID 形态**：与 D01/F003 稳定 ID 对齐；若变更，B1/B5 断言相应调整。
3. **错误码定稿**：`AUTH_REQUIRED`/`AUTH_INVALID_CREDENTIALS`/`FORBIDDEN`/`VERSION_CONFLICT` 及 `details.current_version` 以 `docs/api/F002.md` 为准；与本文差异则升 TD 版本。
4. **CSRF 口径**：Origin/Sec-Fetch-Site 校验是否为 CONTRACT 强制项，决定 B17 执行或 NOT_TESTED。
5. **bootstrap CLI 接口**：一次性 CLI 的调用形态（函数入口 vs subprocess）与退出码约定，影响 V2/B8 fixture 实现方式。

上述不影响 READY 结论（方案可验证）；TEST 执行前必须逐项关闭，并核对 DATABASE/CONTRACT 定稿差异。

---

## Test Execution

*（预留：待 F002 DATABASE/CONTRACT Gate 定稿、实现完成且本 TD-1 与最终设计核对后，追加 TEST 阶段版本、环境、验收映射执行结果、B1–B17 结果、Defects 与未验证项。）*

---

### Git 声明

```text
GIT: NONE
```