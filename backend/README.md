# CSM 后端（F013 用户与角色管理）

FastAPI + SQLAlchemy 2.0 + PostgreSQL 16（ADR-001/002）。

## 结构

```
app/
  config.py            环境变量配置（数据库、会话 TTL、初始管理员）
  db.py                引擎 / Session / DeclarativeBase
  models.py            5 张表 ORM 映射（users/user_credentials/sessions/reserved_usernames/audit_log）
  schemas.py           Pydantic v2 Schema（字段以 docs/api/F013.md 为准）
  errors.py            application/problem+json 统一错误
  audit.py             append-only 审计写入 app.audit.write(...)
  bootstrap.py         幂等初始化建表 + 首个管理员预置
  main.py              FastAPI app、异常处理、路由挂载（/api/v1）
  security/
    password.py        Argon2id 哈希与口令策略
    principal.py       Principal / get_current_user / require_roles
    tokens.py          会话 token 生成与 SHA-256 哈希
  auth/router.py       /auth/login /logout /me /change-password
  users/router.py      /users 增删改查、disable/enable/reset-password
scripts/init_db.py     幂等初始化入口
tests/                 pytest 集成与数据库约束测试（真实 PostgreSQL）
```

## 本地运行（Docker Compose）

```bash
cd backend
CSM_INITIAL_ADMIN_USERNAME=admin CSM_INITIAL_ADMIN_PASSWORD='ChangeMe1' \
  docker compose up -d --build
# API: http://localhost:8000  OpenAPI: http://localhost:8000/docs
```

- `db`：PostgreSQL 16。
- `init`：执行 `python scripts/init_db.py`，幂等建表并预置首个管理员（`must_change_password=true`）。
  未提供 `CSM_INITIAL_ADMIN_PASSWORD` 时会生成随机口令并打印到 `init` 日志一次。
- `backend`：uvicorn 提供 `/api/v1`。仅 HTTP（ADR-004）。

## 运行测试（真实 PostgreSQL）

```bash
# 1) 准备测试库
docker network create csm-test-net
docker run -d --name csm-pg --network csm-test-net \
  -e POSTGRES_USER=csm -e POSTGRES_PASSWORD=csm -e POSTGRES_DB=csm_test postgres:16

# 2) 构建并运行 pytest
docker build -t csm-backend .
docker run --rm --network csm-test-net \
  -e CSM_DATABASE_URL=postgresql+psycopg://csm:csm@csm-pg:5432/csm_test \
  csm-backend pytest -q
```

测试覆盖场景 72–81，以及数据库约束（用户名唯一/格式、reserved 只增、audit append-only、
CASCADE/SET NULL、乐观锁、会话过期谓词）。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CSM_DATABASE_URL` | `postgresql+psycopg://csm:csm@localhost:5432/csm` | 数据库连接串 |
| `CSM_SESSION_TTL_SECONDS` | `43200`（12h） | 会话绝对 TTL |
| `CSM_SESSION_COOKIE` | `csm_session` | 会话 Cookie 名 |
| `CSM_COOKIE_SECURE` | `false` | ADR-004：HTTP-only，不设 Secure |
| `CSM_INITIAL_ADMIN_USERNAME` | `admin` | 首个管理员用户名 |
| `CSM_INITIAL_ADMIN_PASSWORD` | 空（生成随机） | 首个管理员初始口令 |