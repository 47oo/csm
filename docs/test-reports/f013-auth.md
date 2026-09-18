# Test Report — F013 本地账号认证与会话

> Status: **READY FOR REVIEW**
> Author Role: tester
> Date: 2026-09-16
> Feature: F013（ENABLER，E07，P0，`depends_on: [F012]`）
> 分支：`feature/F013-auth`，起点 `develop` = `6e7338c49d341664e7bd1ee914042b193a2cfe43`，实现 HEAD = `01335eea10540f5a115030bb7b0c0cf2a2340118`

---

## Feature

本地账号认证与会话（F013）— CSM V1 认证基座：本地账号、服务端会话、全 `/api/*` fail-closed 认证边界、初始管理员初始化 CLI、前端登录页与会话失效处理。

## Test Basis

- `docs/product/handoffs/f013-auth.md`（Product Handoff，`READY FOR ARCHITECT`，含 2026-09-15 用户裁定补充）
- `docs/product/requirements.md` §19（R-AUTH-001 ~ R-AUTH-006）/ §20 / §21 / §23
- `docs/product/domain-model.yaml > authentication`（`CONFIRMED`）
- `docs/architecture/f013-auth-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，T-01 ~ T-19 / G-A ~ G-F、REQUIRED、Constraints）
- `docs/api/f013-auth.md`（API Contract，`READY`，单一权威）
- `docs/api/api-conventions.md`（`READY`）
- `docs/architecture/adr/adr-0005-local-authentication-and-session.md`（`ACCEPTED`）
- `docs/database/csm-v1-schema-design.md`（`users` / `sessions`）、`docs/database/f012-baseline-migration.md`
- `docs/project/project-plan.yaml` F013 AC-01 ~ AC-15
- `.pi/skills/resource-domain/SKILL.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f013-test/pgdata`） |
| 数据库 locale / encoding | `datcollate = datctype = zh_CN.UTF-8`，`UTF8` |
| Node / npm | v24.14.0 / 11.9.0（Vite 7.3.6，Vitest 5.0.1） |
| 测试库 | `csm_f013`（pytest）、`csm_mig`（迁移）、`csm_cli`（CLI）、`csm_api`（真实服务集成），均本次新建 |
| 后端真实服务 | `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8799 --app-dir backend`（真实 PG `csm_api`） |
| 前端测试 | `npm run typecheck` / `npm run test` / `npm run build` |

**是否全新**：数据库实例、各测试库、测试账号均为本次测试新建；后端 pytest 从 `DROP SCHEMA public CASCADE` 后的空库经 `alembic upgrade head` 重建。实现方结论**未被复用**，下表所有结果均来自本次独立执行。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端测试（独立重跑，未 skip 伪造）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f013?host=/tmp/f013-test/pgdata" \
  .venv/bin/python -m pytest -q
133 passed, 2 warnings in 69.83s
```

认证专项子集（含数据库层绕过应用层断言）：

```text
$ .venv/bin/python -m pytest tests/test_auth_api.py tests/test_auth_cli.py \
    tests/test_auth_guards.py tests/database/test_auth_schema.py -q
55 passed, 2 warnings in 26.60s
```

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests        → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 60 files already formatted  exit 0
```

### 3. 前端

```text
$ cd frontend && npm run typecheck → exit 0
$ npm run test                     → Test Files 11 passed (11)，Tests 83 passed (83)
$ npm run build                    → vue-tsc 通过 + vite build 成功
                                     dist/assets/index-*.js 1,013.89 kB（仅有 chunk 体积告警）
```

### 4. 迁移（真实库 `csm_mig`，独立执行）

```text
$ alembic upgrade head   → 0001_f012_baseline → 0002_f013_auth
$ alembic upgrade head   → no-op（无 DDL）
$ alembic current        → 0002_f013_auth (head)
$ alembic check          → No new upgrade operations detected.（模型与库无漂移）
$ alembic downgrade base → 0002→0001→（空）
$ alembic upgrade head   → 重建成功
$ git diff <base>..HEAD -- backend/migrations/versions/0001_f012_baseline.py → 空（基线未被修改）
```

### 5. 真实服务集成（真实 uvicorn + 真实 PG）

```text
未认证：GET /api/health, GET /api/clusters, POST /api/clusters, GET /api/auth/login,
        POST /api/auth/login/, GET /api/unknown, GET /api  → 全部 401 UNAUTHENTICATED
登录成功 → 200 {"id":1,"username":"admin"}
  Set-Cookie: csm_session=…; HttpOnly; Max-Age=28800; Path=/api; SameSite=lax
  （无 Secure、无 Domain；响应体不含 token）
已认证：GET /api/clusters → 200；GET /api/health → 200 {"status":"ok","database":"ok"}；
        GET /api/auth/session → 200；GET /api/unknown → 404 NOT_FOUND
登出   → 204 + Max-Age=0 清 Cookie；再访问 → 401；重复登出 → 401
三情形 401 响应体逐字节相同（用户名不存在 / 口令错误 / 账号停用），均不设 Cookie
```

### 6. 真实前端 client ↔ 真实后端（临时 vitest 探针，运行后已删除）

用 `frontend/src/api/auth.ts` + `http.ts` 对接真实 uvicorn（`http://127.0.0.1:8799`）：

```text
Tests 6 passed (6)
- login() 真实返回 AuthenticatedUser 字段恰为 {id, username}
- 口令错误 → ApiError{status:401, code:'UNAUTHENTICATED'} 且 suppressAuthRedirect 不触发全局 handler
- 未登录 getCurrentSession() → UNAUTHENTICATED 且不触发全局 handler
- 未抑制的 /api/clusters 未认证 → 全局 handler 恰好触发 1 次
- 全流程（login → getCurrentSession → clusters → logout → 再 getCurrentSession 401）
  经 happy-dom 管理 HttpOnly Cookie 真实走通
```

---

## Acceptance Criteria Mapping

| AC | Test（Architecture Test Work / 独立验证） | Result | Evidence |
|---|---|---|---|
| AC-01 未认证不得访问受保护端点 | T-01 + 真实 HTTP 逐端点 | **PASS** | 5 个 `/api/clusters*`、`/api/health`、`GET /api/auth/login`、未知 `/api/*`、`/api` 未认证均 401 且 `error.code=UNAUTHENTICATED`、`details=[]`、body 仅含 `error` 键；**不是** 404/405/500 |
| AC-02 登录成功后获得访问能力 | T-02 + 真实 HTTP | **PASS** | 登录 200 后 GET `/api/clusters` 200；POST 201 / PATCH 200 |
| AC-03 口令错误不建立会话且失败响应统一 | T-03/T-04 + 真实 HTTP 逐字节比较 | **PASS** | 用户名不存在 / 口令错误 / 账号停用三者 `status`、`content`（含 `error.code`、`message`、`details`）**逐字节相同**，均 401、均不设 Cookie、`sessions` 行数 0；日志与响应无明文（见 T-10） |
| AC-04 登出使会话失效 | T-05 + 真实 HTTP + 原始 SQL | **PASS** | 登出 204 + `Max-Age=0`；同一 token 再访问 → 401（15/15 次）；重复登出 → 401；会话行物理删除 |
| AC-05 会话失效时前端回到登录页 | T-18/T-19（组件）+ 真实 client 探针 | **PASS** | App 收到未抑制 `UNAUTHENTICATED` → 切 `login` 且 DOM 不再含表格/行/标题/旧身份；登出 204 与 401 归一为同一处理 |
| AC-06 登录页拦截未登录访问 | T-17（组件） | **PASS** | `LoginPage` 三态（`default`/`loading`/`error`）`data-state` 互不相同；`401` 停留 + 固定失败提示（按 `error.code` 分支）；成功 emit `success` |
| AC-07 账号禁用即时生效 | T-07/T-04 + 真实 HTTP + 绕过应用层 `UPDATE users SET active=FALSE` | **PASS** | 停用后既有会话 → 401；停用账号登录 → 统一 401；重新置 `active=TRUE` 后可再登录 |
| AC-08 不存在自助注册入口 | T-08（API 401 + 静态） | **PASS** | `POST /api/auth/register`（及 `/api/users`、`/api/auth/signup`）未认证 → 401；`backend/app/**` 无注册路由，`frontend/src/**` 无注册页面 |
| AC-09 仅两态、无 403 触发路径 | T-09（元数据 + information_schema + 静态） | **PASS** | `Base.metadata` 表集合 `{clusters,users,sessions}`，无角色/权限列；真实库 `information_schema` 扫描 role/permission/rbac/grant/acl → 空；路由无 `/role`\|`/permission`；`403 FORBIDDEN` 仅存在于通用状态码映射表，无触发路径 |
| AC-10 口令不以明文存储或泄露 | T-10（DB + 日志捕获）+ 真实日志 grep | **PASS** | `password_hash` 以 `$argon2id$` 开头、全表无明文；uvicorn 日志对全部集成请求 grep 明文口令 → 0 次命中；登录失败响应体不含口令值 |
| AC-11 初始账号可建立且可登录 | T-11（README 文档化步骤 + CLI） | **PASS** | `PYTHONPATH=backend .venv/bin/python -m app.auth.cli create-initial-admin --username admin`（口令 stdin）→ 创建成功，随后可登录并访问 `/api/clusters`；重复执行 → 「已存在，未修改」exit 0（幂等） |
| AC-12 `/api/clusters*` 行为变更为认证保护且已记录 | T-01 + 文档检查 | **PASS** | 未认证访问 5 个端点均 401 `UNAUTHENTICATED`；变更记录于 `f013-auth-handoff.md` §6 / API 契约 §2 / README §5.1 |
| AC-13 `/api/health` 认证行为 | T-12 + 真实 HTTP | **PASS** | 未认证 → 401 `UNAUTHENTICATED`；已认证 → 200 `{"status":"ok","database":"ok"}`（F012 AC-02 仍成立） |
| AC-14 口令长度下限（R-AUTH-004） | T-13（CLI + DB） | **PASS** | 7 位口令 → 命令 exit 1（「口令长度至少 8 位」），`users` 无新增行；8 位纯小写口令 → 接受且可登录；`LoginRequest` schema 无 `min_length`（登录路径不校验长度） |
| AC-15 用户名区分大小写（R-AUTH-005） | T-14（原始 SQL + API） | **PASS** | 绕过应用层直插 `admin` 与 `Admin` 均成功；重复 `admin` → `23505`；`SELECT ('admin' = 'Admin')` → `false`；`Admin` 凭证不能登录 `admin`；无 `lower(username)` 表达式索引、列无 `COLLATE` |

**说明**：AC-01 ~ AC-15 全部有结果，无遗漏。

## Test Work（T-01 ~ T-19 / G-A ~ G-F）覆盖

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | 5 个 endpoints 未认证 401，非 404/405/500，body 无资源数据 |
| T-02 | PASS | 已认证读 200、写 201、PATCH 200 |
| T-03 | PASS | 不存在 vs 错口令 `content` 逐字节相同 |
| T-04 | PASS | 停用 vs 错口令 `content` 逐字节相同 |
| T-05 | PASS | 登出 204、清 Cookie、复用 token 401、重复登出 401 |
| T-06 | PASS | `GET /api/auth/session` 已认证 200（字段恰 `{id,username}`）/ 未认证 401 |
| T-07 | PASS | 绕过应用层置 `active=FALSE` → 既有会话立即 401 |
| T-08 | PASS | 注册类端点未认证 401；前后端无注册入口 |
| T-09 | PASS | 无 RBAC 表/列/路由/403 路径 |
| T-10 | PASS | `$argon2id$` 前缀、无明文落库/日志/响应 |
| T-11 | PASS | README 文档化 CLI 建立、可登录、幂等 |
| T-12 | PASS | health 未认证 401 / 已认证 200 |
| T-13 | PASS | 7 位拒绝且不建号；8 位小写接受 |
| T-14 | PASS | 大小写共存 + 23505 + `'admin'='Admin'` false |
| T-15 | PASS | Cookie 属性恰为 HttpOnly / SameSite=Lax / Path=/api / Max-Age=28800，无 Secure / Domain |
| T-16 | PASS | 过期会话 401；登录成功惰性清理过期行 |
| T-17 | PASS | LoginPage 三态互异 |
| T-18 | PASS | 全局 401 handler、login/session 抑制跳转、切回登录页不渲染资源数据 |
| T-19 | PASS | 登出（204/401 归一）切换；列表不显示旧数据 |
| G-A | PASS | `EXEMPT == {("POST","/api/auth/login")}`；`GET /api/auth/login` 未认证 401 |
| G-B | PASS | **独立探针**：中间件注册后动态 `include_router` 新 `/api/__tester_probe__` → 未认证 401 |
| G-C | PASS | `users` / `sessions` 列集合恰如 Handoff；无 `deleted_at`、无 RBAC 列、无 `lower(username)` 索引、无 `COLLATE` |
| G-D | PASS | 长度校验仅 `policy.py`、Argon2 仅 `passwords.py`；schema 无 `min_length` |
| G-E | PASS | `backend/app/**` 无 `.deleted_at` 赋值、无 `_foundation`、logging 调用无声口令 |
| G-F | PASS | 真实 OpenAPI GET 路由集合恰为 `{/api/health, /api/clusters, /api/clusters/by-name/{cluster_name}, /api/clusters/{cluster_id}, /api/auth/session}` |

---

## Database / Migration

**迁移**：`0002_f013_auth`（`down_revision = 0001_f012_baseline`）可应用、可重复（第二次 no-op）、可从 `base` 重建；`alembic check` 无漂移；`0001_f012_baseline` **未被修改**（git diff 为空）。

**独立 Schema 检查**（真实 PG 16.2，绕应用层原始 psycopg）：

```text
tables:      ['alembic_version', 'clusters', 'sessions', 'users']
users    列: id bigint NN (identity) / username text NN / password_hash text NN /
             active boolean NN DEFAULT true / created_at timestamptz NN DEFAULT now() /
             updated_at timestamptz NN DEFAULT now()
sessions 列: id bigint NN (identity) / user_id bigint NN / token_hash text NN /
             created_at timestamptz NN DEFAULT now() / expires_at timestamptz NN /
             last_seen_at timestamptz NULL
constraints: pk_users / ux_users_username(UNIQUE username) /
             pk_sessions / ux_sessions_token_hash(UNIQUE) /
             fk_sessions_user FK(user_id)→users(id) ON UPDATE RESTRICT ON DELETE RESTRICT
indexes:     ix_sessions_user_id, ix_sessions_expires_at（+ 各 PK/UNIQUE）
collation:   username 列 collation_name = NULL（默认 collation，大小写敏感）
extensions:  仅 plpgsql；triggers: 无；expression/collate 索引: 无
deleted_at:  仅 clusters 有该列；users / sessions 无
```

**约束对抗验证**（绕过应用层）：

```text
直插 'admin' 与 'Admin' 均成功（共存 count=2）
重复 'admin'                     → 23505
NULL username / NULL password_hash / 缺 password_hash → 23502
active 列默认值                   → true
session FK 指向不存在 user        → 23503
NULL token_hash / 重复 token_hash → 23502 / 23505
DELETE 仍有会话的 user            → 23503（ON DELETE RESTRICT）
SELECT ('admin' = 'Admin')        → false
```

与 Database Handoff / `csm-v1-schema-design.md` 逐项一致，无额外 Schema、无 COLLATE、无触发器、无 CASCADE。

## Backend / API

- 认证边界为 **ASGI 中间件**（`app.add_middleware(AuthMiddleware)`，`include_router` 前），路由前 fail-closed；豁免为精确 `(method, path)`，唯一成员 `("POST","/api/auth/login")`。
- 3 个契约端点行为与 `docs/api/f013-auth.md` 一致：登录 200 + `Set-Cookie`；登出 204 + 清 Cookie（失效 → 401）；会话校验 200/401。字段集合封闭为 `{id, username}`。
- 登录失败三情形由同一 `UnauthenticatedError` 产生**逐字节一致**响应；无会话建立；无明文泄露。
- 会话校验条件 = `token_hash` 命中 AND `expires_at > now()` AND `users.active = true`；`last_seen_at` 实测保持 `NULL`（不写入）；登录成功惰性物理清理过期行（实测过期行消失）。
- Cookie 属性与契约 §3 完全一致（无 `Secure`、无 `Domain`，`Max-Age` 登录 28800 / 登出 0）。
- 数据库不可达时（认证请求）由全局异常处理返回 `500 INTERNAL_ERROR` JSON 信封，未泄露口令。
- 未发现 F013 契约违约。

## Frontend

- `typecheck` 0、`test` 83 passed、`build` 成功。
- `LoginPage`：username/password 仅必填，无长度/复杂度校验（R-AUTH-004 不属登录路径）；password `type=password` + `autocomplete=current-password`；三态互异；401 按 `error.code` 分支、固定失败提示、不解析 `message`。
- `http.ts`：全局 `setUnauthenticatedHandler`；仅按 `error.code === 'UNAUTHENTICATED'` 且未 `suppressAuthRedirect` 时触发；`login` / 启动期 `getCurrentSession` 抑制跳转。
- `App.vue`：`bootstrap → login → app`；全局 401 切回登录页并清除身份与资源视图状态；登出 204/401 归一。
- 未发现 F013 契约违约。

## Integration

**已验证（真实前后端）**：

1. 真实 uvicorn（真实 PG）经 httpx 完成认证边界、登录、会话、登出、停用、失败统一等全套 HTTP 验证。
2. 使用**前端真实 API client**（`src/api/auth.ts` + `src/api/http.ts`）在临时 vitest 探针中对接真实后端，6/6 通过：登录返回结构、`UNAUTHENTICATED` 归一与抑制、全局 handler 触发、完整会话流（含 HttpOnly Cookie 由 happy-dom 真实管理）。临时探针运行后已删除。

**说明**：浏览器级 E2E（真实浏览器 DOM / 视觉）与生产构建产物在 nginx 下的部署未验证，属 F015 / 非本 Feature 范围，见「Unverified Areas」。

## Defects

### F013-F-01 — 已认证访问不支持的方法返回 `405` 且 `error.code = INTERNAL_ERROR`（LOW，pre-existing）

- **Severity**：LOW
- **Layer / Owner**：Backend
- **Location**：`backend/app/common/error_handlers.py`（`_HTTP_STATUS_CODE_MAP.get(exc.status_code, "INTERNAL_ERROR")`；405 未映射）
- **复现步骤**：登录取得会话后 `PUT /api/clusters`（或 `OPTIONS /api/clusters`）→ HTTP `405`，body `{"error":{"code":"INTERNAL_ERROR","message":"Method Not Allowed","details":[]}}`。
- **期望**：4xx 客户端错误不应标为 `INTERNAL_ERROR`（契约未定义 405；建议补充映射或对未知 4xx 使用客户端错误码）。
- **实际**：`error.code = INTERNAL_ERROR`。
- **影响**：**非 F013 引入**——这是 F012 报告已记录的 `F-01`（LOW，Owner Backend），F013 未触及；不影响任何 F013 AC，未认证请求仍 fail-closed 返回 401。仅作承接记录，供协调器决定是否随 F013 或后续批次处理。

**除上述 pre-existing LOW 外，未发现 F013 引入的 BLOCKER / HIGH / MEDIUM / LOW 缺陷。**

## Unverified Areas

1. **浏览器级前端 E2E / 视觉验证**：无浏览器自动化环境；前端行为经 vitest（happy-dom）与真实 HTTP 集成验证，未在真实浏览器观察 DOM/网络/视觉。
2. **生产构建产物在真实 nginx + 内网下的部署**：属 F015。
3. **F015 探针路径**（`/api/health` 不豁免的运维探测替代方案）：F013 不实现，属 F015（PROPOSED-4）。
4. **F014 统一软删领域服务对认证表的「不作用」**：F014 尚未实现，仅验证 F013 未引入 `deleted_at` / `SoftDeleteMixin` 到认证表（G-C/G-E）。
5. **跨进程 / 多 worker 并发**：未做多 uvicorn worker 并发会话竞态压测（无产品需求，V1 单机内网）。
6. **登出提交的事务时序**：`get_db_session` 在响应发送后提交（F012 事务边界）。观测到一次原始连接在登出响应后瞬时仍读到会话行，但 15/15 次「登出后立即复用同一 token」均返回 401，**未能复现用户可见的失效窗口**；记录为信息性观察，不作为缺陷。

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-01 ~ AC-15 全部 PASS；T-01 ~ T-19、G-A ~ G-F 全部 PASS。
- 数据库层（绕过应用层原始连接）：大小写敏感共存 + `23505`、NOT NULL `23502`、FK `23503`、`ON DELETE RESTRICT`、`token_hash` 唯一、列/约束/索引/默认值与 Handoff 一致、无 COLLATE / 触发器 / 多余 extension。
- 迁移：可应用 / 可重复 / 可重建 / 无漂移；基线 `0001_f012_baseline` 未修改。
- 认证边界 fail-closed（含中间件后动态挂载新端点的独立对抗验证）；登录失败三情形逐字节一致；会话生命周期（登出、过期、惰性清理）；账号停用即时生效；口令安全；Cookie 契约；无注册入口；无 RBAC / 403 路径。
- 前端：typecheck / 83 测试 / build 通过；三态、全局 401 归一、登出切换、抑制跳转。
- 真实前后端集成：真实 uvicorn + 真实 PG，且前端真实 API client 对接真实后端 6/6 通过。

### Not Verified

见「Unverified Areas」：浏览器级 E2E、生产 nginx 部署、F015 探针、F014 接缝实现、多 worker 并发压测。

### Blocking Issues

None。

### Defect Owner

F013-F-01 → Backend（**pre-existing F012 F-01**，LOW，非 F013 引入，不阻塞本 Feature）。

---

## Test Status

`READY FOR REVIEW`

---

GIT: NONE