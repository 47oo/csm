# F002 认证、初始账号与权限横切 — 实现报告（Backend / Frontend）

实现提交记录于 feature/F002-auth-permissions。本文件由协调器持久化两份实现交接，作为 implementation 证据。

---

## Backend 实现报告（BACKEND COMPLETE）

### 实现范围（仅 backend/**、compose.yaml、.env.example）

**新增**：`alembic/versions/0002_users_sessions.py`（users/user_sessions、CHECK、FK RESTRICT、索引、对称 downgrade）；`app/models/user.py`（User+UserStatus）、`app/models/session.py`；`app/core/security.py`（argon2id 哈希/校验、令牌生成、SHA-256、SESSION_COOKIE_NAME、未知用户等时耗散列）；`app/core/permissions.py`（Role/Permission、ROLE_PERMISSIONS §23 六行、require_permission 依赖工厂、permissions_for）；`app/core/errors.py`（AppError 族、统一信封处理器 401/403/409/404/422/500、RequestValidationError→422）；`app/core/auth.py`（Operator、get_current_operator：Cookie→哈希→join users ACTIVE+未过期→request.state.operator）；`app/core/csrf.py`（不安全方法+Cookie 同源守卫 Origin/Sec-Fetch-Site/AUTH_ALLOWED_ORIGINS→403 details.reason=csrf）；`app/core/logging.py`（SENSITIVE_FIELDS+SensitiveDataFilter）；`app/services/auth.py`（归一化、登录校验、会话创建/删除）；`app/schemas/auth.py`（LoginRequest/UserOut/LoginResponse/MeResponse，响应不含 password_hash）；`app/api/v1/auth.py`（login/logout/me）；`app/cli/bootstrap_admin.py`（run(settings,session_factory)->int、main；退出码 0/2/1；幂等）；测试 `tests/integration/test_auth.py`、`test_auth_schema.py`、`tests/smoke/test_auth_smoke.py`。

**修改**：pyproject.toml（argon2-cffi>=23.1,<26）；core/config.py（SESSION_TTL_HOURS、INITIAL_ADMIN_*、AUTH_ALLOWED_ORIGINS、is_production）；main.py（错误处理器、CSRF 中间件、日志）；api/v1/router.py；models/__init__.py；tests/conftest.py（auth fixture）；compose.yaml（bootstrap 一次性服务，backend depends_on bootstrap completed）；.env.example（占位符）。

### 设计与 Contract 符合情况

- Endpoint/Schema：/api/v1/auth/login|logout|me 字段、nullable、204、Cookie 属性（csm_session、HttpOnly、SameSite=Lax、Path=/、production Secure、Max-Age 剩余）均按 Contract §2/§4。
- 错误码：7 个 code 与信封一致；登录未知/错密/停用统一 401 且耗时语义一致；未认证先于权限返回 401。
- 权限矩阵：§23 六行逐行映射，require_permission 生产依赖，F002 以测试挂载路由提供机制级 403 证据（R1）。
- 数据设计：约束名与 DB-D13–D19 一致（psql \d 核对），alembic check 无漂移。
- 实现细节偏差（已说明）：①迁移对约束名用 op.f(...)（Alembic 1.14 对命名 CHECK 二次加前缀，op.f 保留设计最终名）；②bootstrap run() 增加可选 session_factory 供测试注入（不改 CLI 形态/退出码）；③expires_at 显式序列化 +00:00。

### 验证证据（实际执行）

- 宿主 venv/pip 不可用（缺 ensurepip），改用 Docker：`docker build --target test` 成功（argon2-cffi==25.1.0）；compileall OK。
- `pytest tests/smoke` → 11 passed；真实 PG `pytest tests/integration` → 36 passed, 1 skipped；`pytest tests`（整体连续两次）→ 47 passed, 1 skipped 且一致无残留。
- 迁移 upgrade head→downgrade 0001_baseline→upgrade head 对称可逆，current=head 0002_users_sessions；`alembic check` 无漂移；psql \d 约束/索引名一致、FK ON DELETE RESTRICT。
- `docker compose config -q` OK；Compose db→migrate→bootstrap 链路：migrate 建表、bootstrap 创建 f002admin、二次运行 no-op exit 0；backend login 200+Set-Cookie（HttpOnly/Lax/Path=/）、/me 200。
- 验收映射：A1(V1/V8)、A2(V2/B7/B8/B9/V9)、A3(B13)、A4(V4/B11)、A5(V5/B12)、A6(V6/B10/B14)、A7(§5)；DB 层 B15–B21/V9 真实 PG 通过。B11/A4/A6 维持机制级口径。

### 未验证项

F001 V3b（非 superuser 扩展安装）跳过（测试 PG 角色 csm 为 superuser，环境限制）；完整 docker compose up -d 含 frontend/nginx 全链路未执行（frontend 并行交付）；F002 前端登录壳未验证（非本角色）；500 处理器以 TestClient(raise_server_exceptions=False) 机制级验证；宿主 venv 不可用改 Docker 替代。

### Issues / Next

R1（MEDIUM，既定口径）403 机制级；NOTE AUTH_ALLOWED_ORIGINS 逗号分隔解析；NOTE 登录限流本期 NOT_REQUIRED；NOTE D01 稳定 ID（PG UUID）首次落地，F003 沿用。

Git 声明（只读）：git status --short、git branch --show-current、git rev-parse --short HEAD、git log --oneline -5、git tag、git ls-files | grep .env（无）、git grep 敏感模式（无）。

---

## Frontend 实现报告（FRONTEND COMPLETE）

### 实现范围（仅 frontend/**）

| 文件 | 内容 |
| --- | --- |
| `src/api/client.ts`（改） | credentials:"include"；统一信封解析→ApiError{status,code,message,details}（形状不符回退 HTTP {status} 不伪造）；setUnauthorizedHandler 全局 401；displayError；无重试 |
| `src/api/auth.ts`（新） | login/logout/me 类型化；User{id,username,role,status,permissions}、LoginResponse、MeResponse 按 Contract |
| `src/pages/LoginPage.tsx`（新） | 表单；Loading/Success/Error 显式三态；422 列出 details.fields；失败清空密码；不回显凭据 |
| `src/pages/HomePage.tsx`（新） | 已登录视图（用户名+角色+登出+permissions 徽章，注明非安全边界）；登出 204→回登录页，401→等效登出，403 CSRF→显式错误不重试 |
| `src/components/HealthPanel.tsx`（新） | F001 健康面板抽取，三态不变，整合进登录态页面 |
| `src/App.tsx`（改） | 启动 GET /auth/me（Loading→已登录/未认证→登录页/非 401 失败→显式错误+重试）；全局 401→清态回登录页；无路由/状态库 |
| `src/index.css`（改）、`scripts/smoke-client.mjs`（新）、`package.json`（改） | 最小样式；client 机制级冒烟 10 用例；`npm run smoke:client` |

Contract 符合：信封/错误码（401 清态、403/409 显式、无静默重试）；Cookie 前端不接触令牌；§4.1–4.3 请求/响应字段；无注册入口；权限矩阵未复制（仅展示，非安全边界）。

### 验证证据（实际执行）

`npm run typecheck` 通过（strict）；`npm run smoke:client` 10 passed（401 清态触发、403/409 不触发且携带 code/details、每用例断言 fetch 恰 1 次无重试、204、信封回退）；`npm run build` 36 modules、dist 148.78 kB JS/1.78 kB CSS；`docker build` 成功；preview+curl：/ =200 含 #root、asset=200、SPA fallback /login=200、产物含三端点路径。

### 未验证项

真实后端集成（login/logout/me 端到端、Set-Cookie）待 Backend F002 端点就绪后 Compose 冒烟（TD-2 V1/V8）；真实浏览器 DOM 渲染（TD-2 §6 非必要）；preview 下 /api/* 由 SPA fallback 返回（部署拓扑由入口 Nginx 代理，非部署行为）；F001 Compose 全链路未重跑。

### Issues / Next

待 Backend F002 端点的 Compose 集成冒烟（登录→me 恢复→登出+Cookie 属性），由协调器在 TEST 阶段安排；403/409 业务页面级呈现归 F003+。

Git 声明（只读）：git branch --show-current、git status --short、git check-ignore -v frontend/dist/index.html、git diff --stat。