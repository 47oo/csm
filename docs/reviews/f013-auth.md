# Review Report — F013 本地账号认证与会话

> Status: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer
> Date: 2026-09-16
> Feature: F013（ENABLER，E07，P0，`depends_on: [F012]`）
> Feature Branch: `feature/F013-auth`
> Base Branch: `develop` = `6e7338c49d341664e7bd1ee914042b193a2cfe43`
> Reviewed HEAD: `46c6d8a3dd2defd26c32cf283b1b4afe550c00f2`
> merge-base(develop, HEAD): `6e7338c49d341664e7bd1ee914042b193a2cfe43`（= start_commit，HEAD 为其后代）
> Tester Test Report: `docs/test-reports/f013-auth.md`（`READY FOR REVIEW`）

---

## Feature

本地账号认证与会话（F013）— CSM V1 认证基座：本地账号、服务端会话、全 `/api/*` fail-closed 认证边界、初始管理员 CLI、前端登录页与会话失效处理。

## Review Status

**`APPROVED WITH FOLLOW-UP`**

不存在 BLOCKER / HIGH；不存在必须在当前 Feature 修复的 MEDIUM。存在 2 项 LOW（均不阻塞 Merge）与 2 项 NOTE。AC-01 ~ AC-15 核心验收满足，测试可信，实现未超范围、未引入未经确认的能力。

## Scope Reviewed

### Git 证据（Reviewer 独立核对）

```text
git status --short                → 空（工作区 clean；无未暂存 / 未跟踪交付物）
git ls-files --others --exclude-standard → 空
git diff / git diff --cached --stat      → 空
git rev-parse HEAD               → 46c6d8a3dd2defd26c32cf283b1b4afe550c00f2
git rev-parse develop            → 6e7338c49d341664e7bd1ee914042b193a2cfe43
git merge-base develop HEAD      → 6e7338c49d341664e7bd1ee914042b193a2cfe43
git log --oneline develop..HEAD  → 3192507 / b41fce2 / 6d0c814 / db437ec / 1b91098 / 01335ee / 46c6d8a
git reflog                       → 与上述提交一致，起点为 develop @ 6e7338c 的 checkout
```

- Feature HEAD 与 Base SHA 与协调器输入一致，`start_commit` 为 HEAD 祖先，未发现工作起点缺失或分叉。
- 审查范围为 `git diff develop...HEAD` 全量 53 个文件（+4431 / −140），含实现、测试、迁移、契约与文档；非仅未提交改动。
- Reviewer 未执行任何 `add` / `commit` / `switch` / `merge` / `stash`，未修改 Git 状态。

### 独立执行的验证（不采信 Tester 结论）

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量测试 | `.venv/bin/python -m pytest -q`（真实 PostgreSQL 16.2，本轮新建 `csm_rev013`） | **133 passed, 2 warnings in 72.43s**（与 Tester 报告一致） |
| 认证专项 | `pytest tests/test_auth_api.py tests/test_auth_guards.py tests/database/test_auth_schema.py tests/test_auth_cli.py tests/test_health.py tests/test_error_envelope.py -q` | **62 passed** |
| lint / format | `.venv/bin/ruff check backend tests` / `ruff format --check backend tests` | All checks passed / 60 files formatted |
| 迁移漂移 | `alembic upgrade head` + `alembic check` | `No new upgrade operations detected.` |
| 前端 | `npm run test` | **11 files / 83 tests passed** |
| 认证边界对抗 | 自建 app + TestClient：DB 不可达且携 Cookie、`/api/unknown`、`/API/clusters`、`/openapi.json` 等 | 见 Findings |

实际检查内容：Migration `0002_f013_auth`、`users` / `sessions` ORM 与约束、认证模块（`passwords` / `policy` / `tokens` / `repository` / `service` / `router` / `schemas` / `middleware` / `cli`）、`main.py` 挂载、错误处理、前端 `http.ts` / `auth.ts` / `LoginPage.vue` / `App.vue`、全部新增测试与 F001 既有测试调整、依赖与文档。

未审查内容见「Unreviewed Areas」。

## Product Compliance

**结论：满足 AC-01 ~ AC-15，且未引入 Scope Creep。**

逐项复核（Reviewer 独立确认，非引用 Tester）：

- **AC-01 / AC-12**：5 个 `/api/clusters*` 端点未认证 → `401 UNAUTHENTICATED`，body 仅含 `error` 键（不含资源数据），非 404 / 405 / 500。由 ASGI 中间件在路由前统一返回。
- **AC-02**：已认证 `GET /api/clusters` → 200，`POST` 201、`PATCH` 200。
- **AC-03 / R-AUTH-006**：用户名不存在 / 口令错误 / 账号停用三情形由**同一** `UnauthenticatedError` 产生响应；测试对 `response.content` 做逐字节比较，并断言三情形均不设置 Cookie、`sessions` 行数为 0。
- **AC-04**：登出物理删除会话行，同 token 复用 → 401；重复登出 → 401。
- **AC-05 / AC-06**：`App.vue` 全局 401 handler 切回 `login` 并清空 `currentUser` / `selectedClusterId`（不保留资源数据）；`LoginPage` 三态由 `data-state` 区分。
- **AC-07**：绕过应用层 `UPDATE users SET active = FALSE` 后，既有会话立即 401、停用账号统一 401。
- **AC-08**：无注册端点 / 页面；`POST /api/auth/register`、`/api/users`、`/api/auth/signup` 未认证 → 401；结构 guard 固定「无注册路由 / 页面」。
- **AC-09**：无角色 / 权限 / RBAC 表列端点；`403 FORBIDDEN` 仅存在于通用状态码映射表，无触发路径。
- **AC-10**：`password_hash` 以 `$argon2id$` 开头；DB / 日志 / 错误响应均无明文；登录请求体校验错误仅回显字段名与 `msg`，不回显输入值。
- **AC-11**：README §5.1 记录 `python -m app.auth.cli create-initial-admin`（口令走 stdin），可复现、幂等。
- **AC-13**：`GET /api/health` 未认证 → 401；已认证 → 200（F012 AC-02 仍成立）。**未新增豁免**。
- **AC-14 / R-AUTH-004**：`policy.validate_password`（`MIN_PASSWORD_LENGTH = 8`，唯一实现）由 CLI 调用；7 位拒绝且不建号，8 位纯小写接受；`LoginRequest` 无 `min_length`（登录路径不校验长度，符合契约 §8）。
- **AC-15 / R-AUTH-005**：绕过应用层插入 `admin` 与 `Admin` 均成功、重复 `admin` → 23505、`('admin' = 'Admin')` 为 false；登录按字面值等值匹配（无 `lower()` / `ILIKE`）。

**Scope 复核**：未发现 RBAC / LDAP / AD / OAuth / SSO / 自助注册 / 口令找回 / MFA / 审计 / 频率限制 / 多设备会话 / CORS / 状态改变型 GET / 资源软删语义。前端无注册页、无账号管理页、未引入 vue-router。`User` / `Session` 未被建模为 Resource。

**结论**：实现忠实满足已确认产品需求；未把「能实现更多」当优点。

## Architecture Compliance

- **fail-closed 边界**：`app/main.py` 在 `include_router` 之前 `add_middleware(AuthMiddleware)`；中间件为纯 ASGI，在路由前按 `scope["path"]` / `scope["method"]` 拦截，`is_protected_path` = `path == "/api"` 或 `path.startswith("/api/")`。
- **唯一豁免**：`EXEMPT = {("POST", "/api/auth/login")}`（精确元组匹配，runtime 断言 + guard 固定）。`GET /api/auth/login`、`/api/auth/login/`、未知 `/api/*`、`/api`、`/api/health` 未认证均 401。
- **无路由依赖型 fail-open**：以中间件而非逐路由依赖实现；G-B 在 app 上动态追加新 `/api` 路由，未认证仍 401。
- **中间件与路由使用同一 `scope["path"]`**：不存在二者判定不一致导致的绕过路径；`/API/...`（大写）不一致地返回 404，但该路径不匹配任何产品路由，无数据暴露（见 REV-04）。
- **不引入新框架 / 中间件 / CORS**；`requirements.txt` 仅新增 `argon2-cffi>=23.1`（ADR-0005 已批准 Argon2id，Python 标准库无 Argon2）。
- **API Contract 一致性**：3 个端点路径 / 方法 / body / 响应字段与 `docs/api/f013-auth.md` 一致；`AuthenticatedUser` 字段封闭为 `{id, username}`；登出 / 会话端点在 `/api` 下且受保护；错误信封复用 `common/errors.error_envelope`。
- **会话生命周期记录**：8h 绝对有效、不滑动、`last_seen_at` 不写入、登出物理删除、登录成功惰性清理——与契约 §7 逐项一致。
- **Cookie**：`csm_session` + `HttpOnly` + `SameSite=Lax` + `Path=/api` + host-only + `Max-Age=28800` + **不设 Secure**；登出 `Max-Age=0`。token 不入响应体 / 日志。
- **F014 / F015 接缝**：认证表无 `deleted_at`；生产探针 / 部署记录留给 F015（PROPOSED-4）。

**结论**：符合 Architecture Handoff REQUIRED / Constraints 与 ADR-0001 ~ 0005。

## Database Review

- **增量 migration `0002_f013_auth`**：`down_revision = 0001_f012_baseline`；仅创建 `users` / `sessions`，**未修改** `0001_f012_baseline`（`git diff` 为空）。
- 与 `docs/database/csm-v1-schema-design.md` 逐项一致：
  - `users`：`id` BIGINT identity PK、`username TEXT NOT NULL`、`password_hash TEXT NOT NULL`、`active BOOLEAN NOT NULL DEFAULT true`、`created_at` / `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`；`ux_users_username UNIQUE (username)`；`pk_users`。
  - `sessions`：`id` BIGINT identity PK、`user_id BIGINT NOT NULL`、`token_hash TEXT NOT NULL`、`created_at TIMESTAMPTZ NOT NULL DEFAULT now()`、`expires_at TIMESTAMPTZ NOT NULL`、`last_seen_at TIMESTAMPTZ NULL`；`ux_sessions_token_hash UNIQUE`；`fk_sessions_user → users(id) ON DELETE RESTRICT ON UPDATE RESTRICT`；`ix_sessions_user_id`、`ix_sessions_expires_at`；`pk_sessions`。
- **无** `deleted_at`；`sessions` **无** `updated_at`（未误用 `TimestampMixin`）；**无**角色 / 权限列；**无** `lower(username)` 表达式索引；**无** `COLLATE`；**无**额外 extension / 触发器 / CASCADE。
- **ORM 与 migration 无 drift**：`alembic check` → `No new upgrade operations detected.`（Reviewer 独立执行）。
- **大小写敏感唯一性**：依赖 PostgreSQL `text` 默认 collation + 普通 UNIQUE；绕应用层验证 `admin` / `Admin` 可共存、重复 `admin` → 23505。
- **迁移可应用 / 可重复 / 可重建**：`upgrade head` ×2、`downgrade base && upgrade head` 通过（含于全量测试）。

**结论**：数据库与迁移忠实于 Database Handoff，未把 PROPOSED / OPEN 静默实现为不可逆规则。

## Backend Review

- **API 层职责 / Service 边界**：router 仅处理 HTTP 与 Cookie；`service` 承担统一失败语义、会话建立、登出、初始账号；`repository` 承担数据访问；`passwords` / `policy` / `tokens` 各自单一职责。
- **认证边界**：ASGI 中间件，见 Architecture Compliance；认证成功写 `request.state.current_user`，`GET /api/auth/session` 再读回。
- **登录失败三情形**：均抛 `UnauthenticatedError`，不建立会话、不设 Cookie；用户名不存在时执行 `verify_dummy` 等价 Argon2 校验，关闭计时侧信道。
- **口令安全**：仅写 `password_hash`；无请求体 / 响应体日志；异常信息不含明文；`User.__repr__` / `Session.__repr__` 不暴露 hash。Argon2id 参数 `time_cost=3 / memory_cost=65536 / parallelism=1 / hash_len=32 / salt_len=16` 为常量并与 Handoff 一致。
- **会话校验**：`get_active_user_by_session_token_hash` = `token_hash` 命中 **AND** `expires_at > now()` **AND** `users.active = true`（JOIN）；账号停用即时生效。
- **登出**：物理 `DELETE`；失效会话由中间件返回 401（不产生副作用），符合契约幂等语义。
- **DB 不可用**：中间件 DB 异常由全局异常处理返回 `500 INTERNAL_ERROR` JSON 信封（Reviewer 独立复现），无 fail-open、无明文泄漏。
- **错误语义**：登录请求体非法 → `400 VALIDATION_ERROR`（仅依赖 body 合法性，不泄露账号存在性）；凭据失败 → `401 UNAUTHENTICATED`；未认证未知 `/api/*` → 401；已认证未知路径 → 404。不同业务情况被正确区分。
- **逻辑删除过滤**：认证表无 `deleted_at`，未错误套用 `deleted_at IS NULL` 原语。

**结论**：无明显正确性 / 安全缺陷；未发现 F013 引入的 F013-F-01 之外问题。

## Frontend Review

- **严格使用契约**：`api/auth.ts` 三个端点、`AuthenticatedUser {id, username}`、原样提交（不 trim）；不读不写令牌。
- **`http.ts`**：仅按 `error.code === 'UNAUTHENTICATED'` 且未 `suppressAuthRedirect` 触发全局 handler；不解析 `message`；`login` / 启动期 `getCurrentSession` 抑制跳转。
- **`LoginPage`**：username / password 仅必填；`type=password` + `autocomplete=current-password`；三态 `default / loading / error` 互异；提交中禁重复提交；`401` 停留 + 固定失败提示；无 Empty 态；无长度 / 复杂度校验。
- **`App.vue`**：`bootstrap → login → app`（未引入 vue-router）；启动探测、全局 401 切回登录页并清除身份与资源视图状态；登出把 `204` 与 `401` 归一为同一处理。
- **无 Scope Creep**：无注册页 / 账号管理页 / 口令修改 / 找回 / 路由库；未重复实现业务规则。
- 未发现错误展示领域状态或混淆 Empty / Error；`useAsyncQuery` 既有三态语义未被改变。

**结论**：前端符合契约与 Architecture Handoff Frontend Work。

## Test Review

- **覆盖 Acceptance Criteria**：AC-01 ~ AC-15 均有对应测试（T-01 ~ T-19 / G-A ~ G-F），映射逐项成立。
- **真实验证数据库约束（绕应用层）**：`tests/database/test_auth_schema.py` 用原始 psycopg 验证列集合、无 `deleted_at`、无 RBAC 列、无 `lower(username)` 索引、无 `COLLATE`、23505 / 23503 / 默认值；`test_auth_api.py` 用 `*_and_raw` 夹具绕过应用层直写 `active` / `expires_at` / 大小写用户。
- **guard 可失败**：G-A（唯一豁免集合）、G-B（新端点自动受保护）、G-C（列集合 / 无 COLLATE）、G-D（策略单一实现 / schema 无 `min_length`）、G-E（无 `deleted_at` 赋值 / 无 `_foundation` / 日志无声口令）、G-F（GET 路由集合）均为会失败的断言。
- **未迎合实现**：T-03 / T-04 对 `response.content` 逐字节比较并断言 `sessions` 行数为 0，而非仅断言状态码；T-14 绕应用层验证。
- **F001 既有测试调整**：仅将 `app_client*` 夹具替换为 `auth_client*`，**领域断言语义未削弱**（AC-01 ~ AC-13 断言原样保留）。`test_health.py` 将「DB 不可达 → 500」拆分为「未认证 → 401」与「已认证 + 断链 → 500」，未掩盖原判据。表集合 / revision 期望按 Handoff 更新。
- **无顺序依赖 / 无 skip 伪造**：DB 测试在未配置 DSN 时 `skip`（不伪造通过）；Reviewer 以真实 PostgreSQL 全量重跑通过。
- Tester 新增测试属 Review 范围，未发现「测试错误的东西」或削弱断言的调整。

**结论**：测试可信，可作为 Review 证据。

## Findings

### REV-01

**Severity**：LOW（不阻塞本 Feature）

**Layer**：Backend / Security（文档边界）

**Location**：`backend/app/main.py:34`（FastAPI 未关闭默认文档面）；`docs/api/f013-auth.md` §2

**Problem**：`/openapi.json`、`/docs`、`/redoc` 位于 `/api` 前缀之外，因此**未认证可达**（Reviewer 实测均返回 `200`）。它们是框架默认挂载的非产品面。

**Evidence**：

```text
GET /openapi.json → 200
GET /docs         → 200
GET /redoc        → 200
（同一 app 下 GET /api/... 未认证均 401）
```

**Impact**：在受控内网内暴露完整 API schema（端点、字段、示例），扩大信息面；但不泄露资源数据。契约 §2 明确受保护范围为 `/api` 前缀，故**不是契约违约**，F013 未引入新面（F012 起即为框架默认）。

**Expected**：保持现状可接受（内网取舍）；建议在 F015 生产部署中显式关闭或限制文档面，并在部署文档记录。**不得**因此在本 Feature 修改契约或扩大 `/api` 边界。

**Suggested Owner**：Architect / F015（记录与部署决策），Backend（如决定关闭）。

---

### REV-02

**Severity**：LOW（不阻塞 Merge）

**Layer**：Documentation / Project Plan

**Location**：`docs/project/project-plan.yaml` F013 `git.head_commit`

**Problem**：`head_commit` 记为 `01335eea10540f5a115030bb7b0c0cf2a2340118`，但 Feature 当前 HEAD 为 `46c6d8a`（测试提交 `test(F013): add acceptance and regression coverage`），元数据与真实 HEAD 不符。

**Evidence**：

```text
git rev-parse HEAD → 46c6d8a3dd2defd26c32cf283b1b4afe550c00f2
project-plan.yaml  → head_commit: 01335eea10540f5a115030bb7b0c0cf2a2340118
（Test Report header 亦以 01335ee 为「实现 HEAD」，本身可接受）
```

**Impact**：仅影响计划文档准确性；不影响代码 / 契约 / 测试。与 F012 Review 的 D-03 同类。

**Expected**：在合并前的状态提交中更新 `head_commit` 为最终 HEAD（或在 Merge Gate 记录 merge_commit）。

**Suggested Owner**：Coordinator。

---

### REV-03

**Severity**：NOTE

**Layer**：Backend / Test Guard

**Location**：`tests/test_auth_guards.py::test_g_e_no_password_in_logging_calls`

**Problem**：该 guard 逐行扫描含 `logger.` / `logging.` / `log.` 标记且同一行含 `password` 的调用。若未来出现跨行构造、变量重命名或在 `logger` 别名上记录口令，可能漏检。

**Evidence**：guard 逻辑基于单行子串匹配（`tests/test_auth_guards.py`）。

**Impact**：当前实现无口令日志路径，guard 不误报；仅属纵深防御强度问题。

**Expected**：可作为后续 hardening（例如 AST 级检测或对 `/api/auth/*` 请求体日志的额外断言）。不要求本 Feature 修改。

**Suggested Owner**：Backend（Follow-up）。

---

### REV-04

**Severity**：NOTE

**Layer**：Backend / API 边界

**Location**：`backend/app/auth/middleware.py::is_protected_path`

**Problem**：大写路径 `/API/clusters` 未认证返回 `404 NOT_FOUND` 而非 `401`（Reviewer 实测）。

**Evidence**：`is_protected_path` 与 Starlette 路由均大小写敏感，且 `/API/clusters` 不匹配任何产品路由——该路径既不暴露数据也不进入受保护面。

**Impact**：无数据暴露；与契约 §2 对受保护范围的**大小写敏感**定义一致，非契约违约。

**Expected**：保持现状。仅记录为边界行为，供后续若要统一 401 语义时参考。

**Suggested Owner**：Architect（认知记录）。

## Existing Defects

### F013-F-01（Tester 报告：已认证访问不支持的方法 → 405 且 `error.code = INTERNAL_ERROR`）

**Reviewer 判定：LOW（同意 Tester 的严重程度），继承自 F012 F-01，非 F013 引入，不阻塞本 Feature。**

- **Layer / Owner**：Backend / `backend/app/common/error_handlers.py`（`_HTTP_STATUS_CODE_MAP.get(exc.status_code, "INTERNAL_ERROR")` 未映射 405）。
- **Reviewer 独立确认**：`create_app` + `TestClient`，中间件在路由前拦截：**未认证** `PUT /api/clusters` → `401 UNAUTHENTICATED`（fail-closed 正确）；**已认证**的不支持方法才会落到路由并返回 `405` + `INTERNAL_ERROR`。
- **是否 F013 引入**：否。该映射来自 F012 基线，F012 Review 已记录为 F-01（LOW）。F013 反而使未认证请求更早被 401 拦截，**缩小**了该路径的暴露面。
- **是否符合契约**：契约 §6 未定义 405；不构成 F013 契约违约。
- **结论**：不在本 Feature 修复；与 F012 的 F-01 合并为 Backend Follow-up。

### 其他继承 follow-up 与 F013 的关系

- **F012 F-02（FK 违规字段回退解析截断）**：F013 引入首个真实 FK `fk_sessions_user`。但 F013 **无任何 API 路径**可产生 `sessions` FK 违规（`user_id` 来自已认证用户或登录时同事务读取的用户行，且无删除账号路径），故该缺陷在 F013 中**不可达**，未被引入或放大。
- **F012 F-03（`/_foundation` fail-open）**：F001 已移除该非产品自检面；F013 的 G-E guard（`test_g_e_no_foundation_face` 等）固定其不再出现。**已关闭，未回归。**

## Non-blocking Follow-ups

1. **REV-01**：由 F015 决定是否在生产部署中关闭 / 限制 `/docs`、`/redoc`、`/openapi.json`，并记录为内网信息面取舍。
2. **REV-02**：合并前更新 `project-plan.yaml` 的 F013 `head_commit` / `merge_commit`。
3. **REV-03**：将口令日志 guard 强化为 AST 级或增加对 `/api/auth/*` 请求体日志的显式断言。
4. **F013-F-01 / F012 F-01**：为未映射的 4xx（如 405）补充客户端错误码映射，避免落入 `INTERNAL_ERROR`。
5. **F012 F-02**：FK 违规字段回退解析返回完整列名（对 F002 / F004 / F005 有潜在价值）。
6. **F015 承接**：`/api/health` 不豁免的探针替代方案（PROPOSED-4）、「仅限受控内网 / 无 HTTPS / Cookie 无 Secure」部署记录。

## Unreviewed Areas

- 浏览器级前端 E2E / 真实 DOM / 视觉验证（本轮以 vitest（happy-dom）与独立真实 HTTP / 真实前端 client 探针为准；环境无浏览器自动化）。
- 生产构建产物在真实 nginx + 内网下的部署（属 F015）。
- 多 uvicorn worker / 多进程并发下的会话竞态与共享存储（V1 单机内网，无产品需求）。
- F014 统一软删领域服务对认证表「不作用」的实际实现（F014 未实现；本轮仅验证 F013 未引入 `deleted_at` / `SoftDeleteMixin`）。
- F015 探针路径与企业部署配置（F013 不交付）。
- 跨数据库方言行为（V1 固定 PostgreSQL）。

---

## Review Verdict

不存在 BLOCKER / HIGH；不存在必须在本 Feature 修复的 MEDIUM。AC-01 ~ AC-15 核心验收满足；测试可信（Reviewer 以真实 PostgreSQL 独立全量重跑 133 passed、前端 83 passed、ruff 干净、`alembic check` 无漂移）；实现未超范围、未引入未经确认的能力；Migration 与 Schema 忠实于 Database Handoff；认证边界 fail-closed 且豁免唯一。

存在 2 项 LOW（REV-01 文档面暴露、REV-02 计划元数据陈旧）与 2 项 NOTE，均不阻塞 Merge。

**`APPROVED WITH FOLLOW-UP`** — 可进入 Merge Gate；Merge 前建议由 Coordinator 处理 REV-02 元数据更新，其余 Follow-up 可并入后续批次。

---

GIT: NONE
