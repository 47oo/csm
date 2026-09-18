# Architecture Handoff — F013 本地账号认证与会话

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-15
> Feature: F013（ENABLER，E07，P0，`depends_on: [F012]`）
> Git: `feature/F013-auth`，base `develop` = `6e7338c49d341664e7bd1ee914042b193a2cfe43`，candidate HEAD = `6d0c814`
> 配套契约：`docs/api/f013-auth.md`（`READY`）

---

## Feature

本地账号认证与会话（F013）— CSM V1 认证基座：本地账号、服务端会话、全 `/api/*` 认证边界、初始管理员初始化、前端登录页与会话失效处理。

## Product Source

- `docs/product/handoffs/f013-auth.md`（`READY FOR ARCHITECT`，主要输入，含 2026-09-15 用户裁定补充）
- `docs/product/requirements.md`（§19 R-AUTH-001~006；§20 R-DEPLOY-001~003；§21；§23；§26）
- `docs/product/domain-model.yaml > authentication`（`CONFIRMED`）
- `docs/architecture/adr/adr-0005-local-authentication-and-session.md`（`ACCEPTED`，直接依据）
- `docs/architecture/csm-v1-foundation-architecture.md`、`docs/architecture/f012-project-foundation-handoff.md`（Q1 / Q6 / Non-blocking #1）
- `docs/architecture/f001-cluster-handoff.md`（问题 9）
- `docs/api/api-conventions.md`、`docs/api/f001-cluster.md`、`docs/api/f012-project-foundation.md`
- `docs/database/csm-v1-schema-design.md`（`users` / `sessions` 已 `READY`）、`docs/database/f012-baseline-migration.md`
- `docs/project/project-plan.yaml`（F013，AC-01 ~ AC-15）

## Architecture Summary

**已核实的当前系统状态（非空项目）**

| 项 | 现状 |
|---|---|
| Backend | **已存在** `backend/app/**`：应用工厂、`/api/health`、统一错误信封 + 全局 handler（`common/errors.py`、`error_handlers.py`）、通用 SQLSTATE→HTTP 映射（`sqlstate.py`）、分页、请求级事务边界（`api/deps.py`）、`deleted_at IS NULL` 过滤原语（`db/active.py`）、`clusters` 模块 5 个产品端点 |
| Frontend | **已存在** `frontend/src/**`：Vue 3 + TS + Vite + Element Plus；`api/http.ts`（错误归一）、`components/ListStates.vue` / `ErrorState.vue`、`composables/useAsyncQuery.ts`、`pages/ClusterListPage.vue` / `ClusterDetailPage.vue`、`App.vue` 极简视图切换（**无 vue-router**） |
| Database | **已存在** `clusters` 表 + `ck_clusters_name_no_slash` + `ux_clusters_name_active`，由 `0001_f012_baseline` 建立（冻结） |
| API | 产品面 6 个端点（`/api/health` + `/api/clusters*`），**全部未认证**（显式临时状态） |
| 认证相关实现 | **当前不存在**：无 `users` / `sessions` 表、无认证模块、无中间件、无登录页 |
| 相关领域对象 | **无**。`User` / `Session` 不是 Resource |

**方案要点**

1. **认证边界 = 全 `/api/*` 默认保护 + fail-closed**：单个 ASGI 中间件在**路由之前**拦截 `path == "/api"` 或 `path.startswith("/api/")`。豁免名单**唯一成员为 `POST /api/auth/login`**（精确 method+path 匹配）。未认证访问任何 `/api/*`（含未来新增端点、含不存在的路径）→ `401 UNAUTHENTICATED`。`GET /api/health` **不豁免**。
2. **认证模块**：新增 `backend/app/auth/`（`passwords` / `policy` / `tokens` / `repository` / `service` / `router` / `schemas` / `middleware` / `cli`），与既有 `clusters` 模块同构。**不引入新框架 / 新中间件**；仅新增一项**必需密码学依赖** `argon2-cffi`。
3. **初始管理员 = 运维 CLI 命令**（`python -m app.auth.cli create-initial-admin`），口令从 **stdin** 读取（不走 argv / 不落 shell history）；**幂等**；**不存在任何未认证可达的注册端点或页面**。
4. **会话生命周期（记录 ADR-0005 §5 委托的决策）**：绝对有效期 **8 小时**，**不滑动续期**，`sessions.last_seen_at` **不写入**；校验条件 = `token_hash` 命中 **AND** `expires_at > now()` **AND** `users.active = true`；过期行由**登录成功时的惰性物理删除**清理。
5. **Cookie**：`csm_session`，`HttpOnly` + `SameSite=Lax` + **不设 `Secure`** + `Path=/api` + host-only，`Max-Age=28800`。CSRF 实际缓解 = `SameSite=Lax` + 仅 JSON 写请求 + **不启用 CORS** + **不存在状态改变型 GET**。
6. **既有 `/api/clusters*` 行为变更**：F013 后未认证一律 `401 UNAUTHENTICATED`（不是 404 / 405 / 500）。F001 既有测试**必须调整**。
7. **认证表**：新增**增量** migration `0002_f013_auth`（down_revision = `0001_f012_baseline`），创建 `users` / `sessions`，**不改基线**、**不引入角色 / 权限 / RBAC**、**不引入 `deleted_at`**。`username` 大小写敏感由**数据库默认 collation + 普通 `UNIQUE`** 落实（R-AUTH-005），**不使用 `lower(username)`**。
8. **F014 / F015 接缝**：F014 统一软删服务**不作用**认证表；F013 **不实现任何资源软删语义**。F015 承接部署文档与探针路径选择。

## Domain Impact

**无。** 不新增、不修改任何领域对象、资源关系、状态或唯一性规则。

- `User` / `Session` **不是** Resource：不进入资源分类体系、不建通用 `resources` 表、不适用资源逻辑删除语义（§4、§17、§24）。
- 权限模型**仅两态**；不引入角色、权限表、RBAC（R-AUTH-003）。`403 FORBIDDEN` **无任何触发路径**（AC-09）。

## Data Layer Impact

**详细 Schema 已由 Database Agent 交付并 `READY`，本 Feature 不重新设计**；迁移实现由 Backend 承担。

1. **增量 migration `0002_f013_auth`**（down_revision = `0001_f012_baseline`）：
   - `users`：`id`（BIGINT identity PK）、`username TEXT NOT NULL`、`password_hash TEXT NOT NULL`、`active BOOLEAN NOT NULL DEFAULT TRUE`、`created_at` / `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`；`ux_users_username UNIQUE (username)`。
   - `sessions`：`id`（BIGINT identity PK）、`user_id BIGINT NOT NULL`、`token_hash TEXT NOT NULL`、`created_at TIMESTAMPTZ NOT NULL DEFAULT now()`、`expires_at TIMESTAMPTZ NOT NULL`、`last_seen_at TIMESTAMPTZ NULL`；`ux_sessions_token_hash UNIQUE (token_hash)`；`fk_sessions_user → users(id) ON DELETE RESTRICT`；`ix_sessions_user_id`、`ix_sessions_expires_at`。
2. **不使用** `deleted_at`；**不使用** `SoftDeleteMixin`；`sessions` **不使用** `TimestampMixin`（无 `updated_at` 列）。
3. **不引入**角色 / 权限列或表；**不引入** `lower(username)` 表达式索引或任何 `COLLATE` 子句。
4. **R-AUTH-005 的落点**：唯一性与登录匹配都依赖 PostgreSQL `text` 的**默认 collation 等值比较（本身大小写敏感）** + 普通 `UNIQUE`；与 R-CLUSTER-002 / ADR-0002 一致。
5. **不修改** `0001_f012_baseline`；**不新增** extension / 触发器 / CASCADE。
6. **测试断言 + 夹具更新**（非 Schema 变更）：
   - `tests/database/helpers.py`：`MIGRATION_HEAD` → `0002_f013_auth`。
   - `tests/database/test_migrations.py`：期望 revision 更新，并断言 `users` / `sessions` 存在。
   - `tests/database/test_schema.py`：`EXPECTED_TABLES = {"alembic_version", "clusters", "users", "sessions"}`。
   - `tests/test_structure_guard.py::test_only_expected_tables_registered`：`{"clusters", "users", "sessions"}`。

## Backend Work

### 1. 新增依赖（唯一一处）

`requirements.txt` 增加 **`argon2-cffi>=23.1`**。理由：ADR-0005 已批准 Argon2id（`ACCEPTED`），Python 标准库不提供 Argon2。除该依赖外**不得新增任何依赖**。

### 2. `backend/app/auth/` 模块（新）

| 文件 | 职责 |
|---|---|
| `passwords.py` | **唯一** Argon2id 实现：`hash_password` / `verify_password`；含进程内常量 dummy hash 供「用户不存在时等价耗时校验」 |
| `policy.py` | **唯一**口令策略实现 `validate_password`：R-AUTH-004（长度 ≥ 8），失败抛 `ValidationError`；**不得**在前端或 CLI 另写一份 |
| `tokens.py` | `generate_session_token()`（`secrets.token_urlsafe(32)`，256-bit）与 `hash_session_token()`（SHA-256 hex） |
| `repository.py` | `get_user_by_username`（**字面值等值，禁止 `lower()` / `ILIKE`**）、`get_active_user_by_session_token_hash`（JOIN `users.active`）、`create_session`、`delete_session_by_token_hash`、`delete_expired_sessions` |
| `service.py` | `authenticate`（统一失败语义）、`establish_session`、`logout`、`create_initial_admin`（幂等） |
| `schemas.py` | `LoginRequest`（`username` / `password` 均必填 `str`，**无 `min_length`**）、`AuthenticatedUser`（`id: int`、`username: str`） |
| `router.py` | 3 个端点挂载于 `/api`：`POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/session` |
| `middleware.py` | `AuthMiddleware`（ASGI）+ 豁免常量 `EXEMPT = {(POST, "/api/auth/login")}`；认证成功后写 `request.state.current_user` |
| `cli.py` | `python -m app.auth.cli create-initial-admin --username <u>`；口令从 stdin（TTY → 无回显提示；非 TTY → 读一行）；调用 `policy.validate_password` 与 `passwords.hash_password`；**幂等**：已存在则输出「已存在，未修改」并退出 0 |

### 3. 认证边界机制（核心问题 #1，REQUIRED）

1. `app/main.py` 中 `app.add_middleware(AuthMiddleware, ...)`，在 `include_router` 之前注册；中间件按 **ASGI 层**拦截。
2. 豁免判定为**精确 `(method, path)` 元组匹配**，唯一成员 `("POST", "/api/auth/login")`。因此 `GET /api/auth/login`、`/api/auth/login/`、未知 `/api/*` 未认证时均为 **401**（fail-closed；已认证后未知路径才是 404）。
3. 未携带 Cookie / 无对应会话 / 会话过期 / 账号已停用 → 中间件**直接**返回 `401` + 统一错误信封。
4. 认证成功 → 写 `request.state.current_user`。
5. **不修改** `app/common/sqlstate.py` 与错误信封结构；复用 `error_envelope`。
6. **不引入** CORS 中间件。

### 4. `/api/health`（AC-13）

保持 `app/api/health.py` **实现不变**；由中间件统一拦截 → 未认证 `401`，已认证 `200`。**不新增豁免**。F015 探针方案见 PROPOSED-4。

### 5. 登录 / 登出 / 会话端点行为

- **登录成功**：`200` + `AuthenticatedUser` + `Set-Cookie`。
- **登录失败统一**：用户名不存在、口令错误、账号停用 → **完全相同**的 `401`（同状态码、同 `error.code`、同 `message`、`details == []`、不设 Cookie）。用户名不存在时仍执行一次 dummy Argon2 校验，避免以耗时区分。
- **登出**：删除当前会话行（物理 DELETE），`204` + 清 Cookie。登出**不是**豁免端点；会话已失效时返回 `401`（幂等语义见契约 §5.2）。
- **会话校验**：`GET /api/auth/session` 返回当前用户；无有效会话 → `401`。
- 登录成功时执行一次**惰性清理** `DELETE FROM sessions WHERE expires_at <= now()`。

### 6. Cookie（核心问题 #5）

名称 `csm_session`；值 = 原始随机 token（URL-safe base64）。属性：`HttpOnly`、`SameSite=Lax`、**不设 `Secure`**、`Path=/api`、**不设 `Domain`**、`Max-Age=28800`。登出时 `Max-Age=0`。**不把 token 放入响应体 / 日志**。**不得**反向要求 HTTPS。

### 7. 口令安全落实（核心问题 #3，REQUIRED）

- Argon2id 参数、哈希与校验路径见 Technical Decisions。
- **明文不落库**：只写 `password_hash`。
- **明文不落日志**：应用**不得**记录 `/api/auth/*` 的请求体或响应体；**不得**在任何 log 调用中出现 `password` 变量；新增**静态 guard 测试**扫描 `backend/app/**`。
- **明文不落错误信息**：短口令校验失败的错误 message **不得**回显口令值。
- **R-AUTH-004 校验层**：`auth/policy.py::validate_password`（**单一实现**），被 CLI 调用；**不在前端**、**不在 HTTP schema**。**F013 不存在任何 HTTP 建口令 / 改口令路径**，因此不存在对应 `400` 语义；若未来新增，必须映射为 `400 VALIDATION_ERROR` + `details[].field = "password"`。

### 8. 既有 `/api/clusters*` 回归与测试调整（AC-01 / AC-12）

**F001 既有测试的调整（必须显式处理）**：

| 文件 | 调整 |
|---|---|
| `tests/conftest.py` | 新增 `auth_client` 夹具：建立账号 → `POST /api/auth/login` 取得 Cookie → 返回**已认证** `TestClient`；保留 `offline_client`（无 Cookie） |
| `tests/test_clusters_api.py`、`tests/test_clusters_guards.py` | 全部改用 `auth_client`，原有领域断言语义不变 |
| `tests/test_error_envelope.py` | 改用 `auth_client`（`400` 参数校验发生在认证**之后**） |
| `tests/test_health.py` | `200` 用例改用 `auth_client`；原「DB 不可达 → 500」用例改为：① `offline_client` → `401`；② `auth_client` + monkeypatch engine 抛错 → `500` |
| `tests/database/**` | 保持「绕过应用层」直连，**与认证无关，不改断言**；仅更新表集合 / revision 期望 |
| `tests/test_structure_guard.py` | 更新期望表集合 |

**新增测试**：5 个 `/api/clusters*` 端点未认证 → `401 UNAUTHENTICATED`（断言**不是** 404 / 405 / 500，body 不含资源数据）。

### 9. 账号禁用路径（AC-07）

运维停用路径为**文档化的直接数据库操作**：

```sql
UPDATE users SET active = FALSE, updated_at = now() WHERE username = '<name>';
```

**即时生效**：会话校验 JOIN `users.active`，因此**无需删除会话行**即失效；`login` 对 `active=false` 与凭据错误返回**相同**的统一 `401`。须写入 README / 运维文档。

### 10. 明确不做

LDAP/AD/OAuth/SSO；角色 / 权限 / RBAC；自助注册；口令找回 / 重置；MFA；登录审计；登录频率限制 / 账号锁定；多设备会话管理；IP / UA 记录；HTTPS / 域名 / 公网入口；生产部署打包（F015）；资源软删语义（F014）；任何其他资源（F002+）；`DELETE /api/clusters/{id}`。

## Frontend Work

文件所有权：`frontend/**`。

1. **`frontend/src/api/auth.ts`**（新）：`login(body)`、`logout()`、`getCurrentSession()`；类型 `AuthenticatedUser`（`id: number`、`username: string`）；复用 `api/http.ts`，**不新建请求层**。`login` 与启动期 `getCurrentSession` **必须抑制全局 401 跳转**。
2. **`frontend/src/api/http.ts`**（改）：新增 `setUnauthenticatedHandler(handler)`；收到 `code === 'UNAUTHENTICATED'` 且本次请求未抑制时调用 handler。`RequestOptions` 增加 `suppressAuthRedirect?: boolean`。**仍不解析 `message`**。
3. **`frontend/src/pages/LoginPage.vue`**（新，产品页）：`username` + `password`（`type="password"`，`autocomplete="current-password"`）；两者仅做**必填**校验，**不做长度 / 复杂度校验**（R-AUTH-004 不属登录路径）。**Loading**（提交中禁止重复提交）/ **Error**（`401` → 停留并显示固定失败提示，按 `error.code` 分支）/ **成功**（进入系统）。无 Empty 态。
4. **`frontend/src/App.vue`**（改）：极简视图状态扩展为 `bootstrap → login → app`（**仍不引入 vue-router**）：挂载时 `getCurrentSession()`；注册 `setUnauthenticatedHandler` → 切回 `login` 并**清除当前视图状态（不保留任何资源数据）**；`app` 视图头部增加**登出按钮**（`logout()`，无论 `204` 还是 `401` 都切到 `login`）。
5. **不做**：注册页 / 注册表单；账号管理页；口令修改 / 找回；路由库；业务规则重复实现；任何资源删除入口。

## API Contract

```text
READY
```

完整正文见 `docs/api/f013-auth.md`。覆盖 `POST /api/auth/login`（**唯一豁免端点**）、`POST /api/auth/logout`、`GET /api/auth/session`；含 path / query 参数、request / response schema、字段类型、nullable、Cookie 契约、错误语义、Empty / Not Found 语义、会话生命周期记录与**「不承诺」清单**。

## Test Work

Testing Agent 应验证的最小集合（映射 AC-01 ~ AC-15；`T-xx` 为测试编号，`G-x` 为 guard）：

| # | 测试 | 层次 | AC |
|---|---|---|---|
| **T-01** | 未认证访问全部 5 个 `/api/clusters*` 端点 → `401` 且 `error.code == "UNAUTHENTICATED"`，body **不含资源数据**，**不是** 404 / 405 / 500 | API | AC-01、AC-12 |
| **T-02** | `auth_client` 登录后 `GET /api/clusters` → `200`；`POST` / `PATCH` 同样可写 | API | AC-02 |
| **T-03** | **口令错误** 与 **用户名不存在** 的登录响应：状态码、`error.code`、完整 JSON body **逐字节相同**、均不设 Cookie；随后同一客户端访问 `/api/clusters` → `401` | API | AC-03、R-AUTH-006 |
| **T-04** | 账号停用账号登录 → 与 T-03 **完全相同**的响应 | API | AC-07、R-AUTH-006 |
| **T-05** | 登录 → `logout` → `204` + 清 Cookie；同一客户端再访问 → `401`；重复 logout → `401` | API | AC-04 |
| **T-06** | `GET /api/auth/session` 已认证 `200`；未认证 → `401` | API | 会话校验 |
| **T-07** | **绕应用层**置 `users.active = FALSE`：停用前建立的会话再访问 → `401`；停用账号无法登录（见 T-04） | DB 直写 + API | AC-07 |
| **T-08** | **不存在自助注册入口**：`POST /api/auth/register` 等未认证 → `401`/`404`；静态 guard：`backend/app/**` 无注册路由，`frontend/src/**` 无注册页面 | API + 静态 | AC-08 |
| **T-09** | **无 RBAC**：`Base.metadata` 与 `information_schema` 无角色 / 权限表与列；路由表无 `/role`\|`/permission`；全项目无触发 `403` 的产品路径 | DB 元数据 + API + 静态 | AC-09 |
| **T-10** | **无明文泄露**：`users.password_hash` 以 `$argon2id$` 开头且全表无明文；登录成功 / 失败的日志中口令明文**不出现**；短口令失败响应 body **不含**口令值 | DB + 日志捕获 + API | AC-10 |
| **T-11** | 按 **README 文档化步骤**运行 `create-initial-admin` → 可登录并访问 `/api/clusters`；重复执行 → 幂等无副作用 | CLI + API | AC-11 |
| **T-12** | 未认证 `GET /api/health` → `401`；已认证 → `200` `{"status":"ok","database":"ok"}`（F012 AC-02 仍成立） | API | AC-13、AC-12 |
| **T-13** | **R-AUTH-004**：7 位口令 → 拒绝、`users` 无新增行；8 位纯小写口令 → 接受并可登录 | CLI/domain + DB | AC-14 |
| **T-14** | **R-AUTH-005**：**绕应用层**插入 `admin` 与 `Admin` 均成功；重复 `admin` → `23505`；`SELECT ('admin' = 'Admin')` 为 `false`；用 `Admin` 凭证登录 `admin` 账号失败 | DB + API | AC-15 |
| **T-15** | **Cookie 属性**：登录 `Set-Cookie` 含 `HttpOnly`、`SameSite=Lax`、`Path=/api`，且**不含 `Secure`** | API | Cookie 契约 |
| **T-16** | **会话生命周期**：绕应用层插入 `expires_at` 已过的会话 → 访问 → `401`；登录成功后过期行被惰性清理 | DB + API | 会话决策记录 |
| **G-A** | **唯一豁免 guard**：`auth.middleware.EXEMPT` 恰为 `{("POST", "/api/auth/login")}`；`GET /api/auth/login` 未认证 → `401` | 单元 + API | 核心问题 #1 |
| **G-B** | **新端点自动受保护**：在测试 app 上动态 `include_router` 一个 `/api/__probe__` 端点 → 未认证 `GET` → `401` | API | 核心问题 #1、AC-01 |
| **G-C** | **认证表结构 guard**：`users` 列集合恰为 `{id, username, password_hash, active, created_at, updated_at}`，`sessions` 列集合恰为 `{id, user_id, token_hash, created_at, expires_at, last_seen_at}`；两表**无** `deleted_at`、无角色 / 权限列；无 `lower(username)` 表达式索引；无 `COLLATE` | DB | AC-09、核心问题 #7 |
| **G-D** | **口令策略单一实现**：`policy.validate_password` 为唯一长度校验点；schema 未设 `min_length`；Argon2 仅在 `auth/passwords.py` 被 import | 静态 | AC-14 |
| **G-E** | **静态 guard**：`backend/app/**` 中 `deleted_at` 赋值路径数仍为 **0**；无 `_foundation`；无 `password` 出现在 logging 调用中 | 静态 | AC-10、F014 接缝 |
| **G-F** | **无状态改变型 GET**：路由表中所有 GET 路由集合恰为契约所列只读端点 | 静态 | Cookie / CSRF |
| **T-17** | **前端**：`LoginPage` 三态（默认 / 提交 Loading / `401` 失败提示）互不相同；成功进入系统 | 前端组件 | AC-06 |
| **T-18** | **前端**：`http.ts` 收到 `UNAUTHENTICATED` 调用注册的 handler；`login` / 启动期 `getCurrentSession` **不**触发跳转；`App` 在 handler 触发后切回登录页且**不渲染任何资源数据** | 前端单元/组件 | AC-05 |
| **T-19** | **前端**：登出按钮 → 切回登录页；列表页在 401 后不显示旧数据 | 前端组件 | AC-05 |

**明确不在 F013 测试范围**：账号管理 / 口令修改 / 找回；频率限制 / 锁定；审计；多设备会话；MFA；LDAP/SSO；RBAC；资源软删语义（F014）；其他资源（F002+）；HTTPS。

## Technical Decisions

### CONFIRMED

- 本地账号认证；不接 LDAP / AD / OAuth / SSO；不扩大为 RBAC（R-AUTH-001~003；ADR-0005）。
- 服务端会话表 + 随机不可预测 session id；Cookie `HttpOnly` + `SameSite=Lax`，HTTP 下**不设 `Secure`**；口令 **Argon2id**（ADR-0005，`ACCEPTED`）。
- 账号由管理员初始化 / 种子创建，**不开放自助注册**（ADR-0005 §1）。
- 明文口令不落库、不落日志、不出现在错误信息中（ADR-0005 §2）。
- 权限仅两态；除登录端点外全部 `/api/*` 要求认证（ADR-0005 §4）。
- 登出使服务端会话失效；会话可即时作废（ADR-0005 §5 / Consequences）。
- **R-AUTH-004**（≥8 位）、**R-AUTH-005**（大小写敏感）、**R-AUTH-006**（统一失败响应）（requirements §19，用户 2026-09-15 裁定）。
- `401 UNAUTHENTICATED` / `403 FORBIDDEN` 语义；错误信封（`api-conventions.md` §5/§6）。
- `users` / `sessions` Schema（数据库设计 `READY`）；认证表无 `deleted_at`。
- 全部 `/api/*` 位于 `/api` 前缀下，认证中间件**自动覆盖，无需白名单**。
- `/api/health` **不豁免**（Product 问题 C，AC-13）。
- 技术栈、PostgreSQL、BIGINT identity、错误映射、分页、事务边界（ADR-0001~0005）。

### REQUIRED

1. **fail-closed 默认保护**：认证边界必须在**路由之前**生效；豁免必须为**精确 `(method, path)` 匹配且唯一成员为登录端点**；任何其他 `/api/*`（含不存在路径、未来端点）未认证一律 `401`。
2. **登录失败三情形**（用户名不存在 / 口令错误 / 账号停用）必须返回**完全相同**的响应，且**不建立会话**（R-AUTH-006 + AC-07）。
3. **R-AUTH-004 校验不得只在前端，也不得只靠 schema**：单一实现位于服务端领域层，被初始账号路径调用；不足 8 位**不得产生可登录账号**。
4. **R-AUTH-005**：`username` 唯一性与登录匹配均大小写敏感；**禁止** `lower(username)` 索引 / 折叠 / `ILIKE`；必须由**绕过应用层**的数据库测试固定。
5. **明文口令不得**进入数据库、日志、错误响应或异常堆栈；日志 guard 必须可失败。
6. **认证表不得**有 `deleted_at`；**不得**有角色 / 权限 / RBAC 结构；F013 不得写入任何 `deleted_at`（`backend/app/**` 赋值数 = 0）。
7. **不得修改** `0001_f012_baseline`；新表走**增量** revision `0002_f013_auth`。
8. **不新增豁免成员**（`/api/health` 不豁免）；F015 探针须走**产品认证面之外**的机制。
9. **不得引入**新框架 / 中间件 / CORS / 消息队列 / Redis / 后台 worker；除 `argon2-cffi` 外不得新增依赖。
10. **不得引入**状态改变型 GET。
11. 登出 / 会话端点必须位于 `/api` 前缀下且受认证保护。
12. DB / API 契约单一权威；代码不得另立约定。

### PROPOSED

1. **Argon2id 参数**：`memory_cost = 65536 KiB (64 MiB)`、`time_cost = 3`、`parallelism = 1`、`hash_len = 32`、`salt_len = 16`（RFC 9106 第二推荐档的可落地版本）。参数为**实现常量**（非环境变量），记录于本 Handoff。
2. **会话令牌哈希用 SHA-256（hex）**：token 为 256-bit 随机值，无字典风险，无需慢哈希。
3. **统一失败时执行 dummy Argon2 校验**：关闭计时侧信道（R-AUTH-006 的安全意图）。
4. **F015 探针方案**：存活 / 就绪探测**不经过产品 API 认证面**，二选一由 F015 记录：(a) 容器 / 运行时级探测（TCP / 进程级，不发起 HTTP）；(b) 一个**挂载在 `/api` 之外**的非产品生存性路径（如 `/healthz`，不检查数据库、不属产品 API、不进入任何契约）。两者均**不修改 ADR-0005 的 `/api/*` 规则**。F013 **不实现**任一方案，仅记录。
5. **前端不引入 `vue-router`**：`App.vue` 用 `bootstrap / login / app` 视图状态切换。
6. **登出幂等语义**：不做第二个豁免端点；已失效会话调用登出返回 `401`，客户端将其与 `204` 归一为同一终态。
7. **无状态改变型 GET 的静态 guard（G-F）**：把 CSRF 缓解前提变成可失败测试。
8. **惰性清理过期会话**：登录成功时执行；不引入 cron / worker。

### OPEN

1. Argon2 参数是否随硬件调整——不影响本次 AC；变更只需改常量（无 rehash 路径）。
2. 是否引入**滑动续期**——当前明确**不引入**；若未来需要须重新记录（ADR-0005 §5 允许）。
3. 账号管理能力无产品需求，不实现。
4. 前端路由方案（多资源导航出现时决策）。
5. `/api/health` 豁免：**当前不豁免**；若未来用户明确批准，属对 ADR-0005 白名单的**有意扩展**，须同步修订 AC-13 与契约。
6. CSRF 残余面：受控内网内同站攻击 / XSS 不在本 Feature 处理范围。

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| AR1 | **认证边界实现为「路由依赖」而非中间件**会导致 fail-open：新端点忘记挂依赖即匿名可达 | 结构上强制为 ASGI 中间件（路由前生效）；G-A / G-B 把「唯一豁免」与「新端点自动受保护」变成可失败测试 |
| AR2 | **登录失败响应被后端框架改写而不一致** | T-03 / T-04 逐字节比较三者 body；实现上三情形走同一 `AuthenticateError` → 同一 `UNAUTHENTICATED` |
| AR3 | **Argon2 参数过重**拖慢内网单机 VM | 64 MiB / t=3 / p=1；登录频率极低；参数为常量，必要时单点调整 |
| AR4 | **明文口令进入日志 / 异常** | 禁止记录 `/api/auth/*` body；G-E 静态 guard + T-10 日志捕获断言 |
| AR5 | **HTTP 明文 + 无 `Secure` Cookie** | 已确认产品取舍（R-DEPLOY-003）；F015 部署文档必须记录「仅限受控内网」；不反向要求 HTTPS |
| AR6 | **CSRF**：无 HTTPS，浏览器对 Cookie 的处理是主要防线 | `SameSite=Lax` + 仅 JSON 写请求 + 不启用 CORS + 禁止状态改变型 GET（G-F）；残余风险记录于契约 §3 |
| AR7 | **既有 F001 测试未调整**导致行为变更被误判为回归或被静默掩盖 | Backend Work §8 列出逐文件调整；T-01 明确断言 `401` 而非 404/405/500 |
| AR8 | **认证表被后续 Feature 误当作资源** | G-C / G-E guard；F014 接缝在 Handoff 与契约中显式声明 |
| AR9 | **初始账号初始化文档泄露默认口令** | CLI 从 stdin 读取（不走 argv）；README 仅给命令，不给示例口令 |
| AR10 | **绕过应用层的停用路径**误改生产数据 | 属运维步骤，文档明确「仅限停用账号」；验证在测试库用原始连接执行 |

## Constraints

1. 不得引入角色 / 权限 / RBAC（表、列、端点、403 路径）（R-AUTH-003、AC-09）。
2. 不得实现 LDAP / AD / OAuth / SSO（R-AUTH-002）。
3. 不得实现自助注册入口（端点或页面）（ADR-0005 §1、AC-08）。
4. 不得为 `users` / `sessions` 引入 `deleted_at` 或资源软删语义（§17；F014 边界）。
5. 不得修改 `0001_f012_baseline`；不得新增 extension / 触发器 / CASCADE。
6. 不得使用 `lower(username)` 索引 / 大小写折叠 / `ILIKE` 实现用户名匹配（R-AUTH-005）。
7. 不得只在前端实现 R-AUTH-004；不得引入除「≥8 位」以外的任何口令强度规则；不得在契约 / 前端文案 / AC 中承诺其行为。
8. 不得新增除 `argon2-cffi` 以外的依赖；不得引入新框架 / 中间件 / CORS / 后台 worker / 消息队列 / Redis。
9. 不得新增 `/api/*` 认证豁免成员；`/api/health` 保持受保护。
10. 不得把任何端点放到 `/api` 之外（F015 探针除外，且不得属产品契约）。
11. 不得引入状态改变型 GET。
12. 不得反向要求 HTTPS / 域名 / 公网入口（R-DEPLOY-003）。
13. 不得把 `User` / `Session` 建模为 Resource 或纳入通用资源表（§4、§24）。
14. 不得实现 F014 的软删领域服务、父删子拦、并发加锁；不得实现任何其他资源（F002+）。
15. DB / API 契约单一权威；代码中不得另立约定。

## Open Technical Questions

### Blocking

**无。** F013 的产品范围、边界（AC-01 ~ AC-15）与架构方案均可由 `READY FOR ARCHITECT` 的 Product Handoff、`CONFIRMED` 的 §19 / ADR-0005、`READY` 的数据库设计与既有 `READY` 契约完整确定。R-AUTH-004 / 005 / 006 已由用户裁定。

### Non-blocking

1. Argon2 参数微调（OPEN #1）。
2. 是否引入滑动续期（OPEN #2）——当前明确不做。
3. F015 探针采用 (a) 还是 (b)（PROPOSED-4）——由 F015 决策。
4. 前端路由方案（OPEN #4）。
5. `/api/health` 豁免（OPEN #5）——当前不豁免。
6. CSRF 残余面（OPEN #6）。
7. `sessions.last_seen_at` 保留但**不写入**：列成本极低，避免未来加列迁移；现记录为「本 Feature 不使用」。

## Implementation Layers

```text
database: true
backend:  true
frontend: true
```

- **database = true**：增量 migration `0002_f013_auth`（`users` / `sessions` + 约束 / 索引）；详细 Schema **已 `READY`**，migration 实现由 Backend 承担；**不改 `0001_f012_baseline`**。
- **backend = true**：`app/auth/` 模块、`argon2-cffi` 依赖、认证边界、既有 `/api/clusters*` 行为变更与测试调整、README / `.env.example` 文档。
- **frontend = true**：`api/auth.ts`、`api/http.ts` 全局 401 处理、`LoginPage.vue`、`App.vue` 会话态与登出。

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f013-auth.md，均 READY）
  ├─ Frontend（只需契约稳定）
  └─ Database Design（✅ 已 COMPLETE：users / sessions 设计 READY）
        └─ Backend
             1. 增量 migration 0002_f013_auth（先建表，不改基线）
             2. app/auth/（passwords → policy → tokens → repository → service → schemas → router）
             3. AuthMiddleware + main.py 挂载（fail-closed）
             4. CLI create-initial-admin
             5. 既有 F001 测试调整 + 新增认证测试 / guard
                 ↓ 两个必需分支完成
              Tester → Reviewer → Merge Gate
```

- 无「等待 Database Design」阻塞；Frontend 与 Backend 可**直接并行**。
- 文件所有权：Frontend = `frontend/**`；Backend = `backend/**` + `tests/**` + `.env.example` + `README.md` + `requirements.txt`；`docs/**` 由协调器统一落盘。

## Verification Strategy

1. **认证边界**：G-A（唯一豁免）+ G-B（新端点自动受保护）+ 所有既有端点未认证 401（T-01）。
2. **口令安全**：Argon2id 哈希前缀断言、明文不出现于 DB / 日志 / 错误响应（T-10）、短口令拒绝且不建账号（T-13）、单一实现 guard（G-D）。
3. **账号枚举防护**：三情形逐字节相同（T-03 / T-04）。
4. **会话生命周期**：登出失效（T-05）、过期会话拒绝与惰性清理（T-16）、停用即时生效（T-07）。
5. **Cookie 契约**：属性断言（T-15）。
6. **大小写敏感**：**绕过应用层**直接对数据库插入 / 查询（T-14）。
7. **数据库层（绕应用，权威）**：迁移可应用 / 可重复 / 可从空库重建；表集合与列集合 guard（G-C）。
8. **结构否定性**：无注册入口（T-08）、无 RBAC 表列端点与 403 路径（T-09）。
9. **既有行为变更**：`/api/clusters*` 未认证 401（T-01）、`/api/health` 未认证 401（T-12），且 F001 测试已按 §8 调整。
10. **前端**：登录页三态与失败提示、全局 401 会话失效跳转、登出（T-17 ~ T-19）。
11. **工程门禁**：ruff 干净；`alembic upgrade head` ×2 与 `downgrade base && upgrade head` 成功；无新增框架 / 依赖（除 `argon2-cffi`）。

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：Product Handoff `READY FOR ARCHITECT` 且无 Blocking；ADR-0005 `ACCEPTED`；`users` / `sessions` Schema 设计 `READY`；API Contract = `READY`；`database: true`（设计已完成，migration 实现由 Backend 承担）→ Backend / Frontend 两个实现分支均有可直接开工的依据，且可并行。需用户确认的长期技术决策：**无**。