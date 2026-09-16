# Architecture Handoff — F015 内网部署与运行环境

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-17
> Feature: F015（ENABLER，E07，P0，`depends_on: [F012, F013]`）
> Git: `feature/F015-deployment`，base `develop`，`start_commit` = `5c9ca84f94134c9bcc87c61a47fd9280ff99d411`
> 配套契约：**无需**（F015 不新增产品 API；见 API Contract）

---

## Feature

内网部署与运行环境（F015）— CSM V1 的**可运行生产部署产物**：`docker-compose`（nginx + 应用 + PostgreSQL）、生产前端构建接线、`prod` 环境硬化、存活/就绪探测、部署文档与运行约束。

## Product Source

- `docs/product/handoffs/f015-deployment.md`（Status `READY FOR ARCHITECT`，无 Blocking，AC-01 ~ AC-12）— **最终产品输入，本次不重新定义范围**
- `docs/product/requirements.md` §20 / §21 / §22 / §23 / §25 / §26
- ADR-0001（技术栈 / 模块边界 / 部署形态：docker-compose nginx+app+postgres）、ADR-0002（PostgreSQL / 默认 collation / 版本化向前 migration）、ADR-0003（错误信封 / 状态码，F015 不改）、ADR-0004（软删，F015 不改）、ADR-0005（HTTP 明文 / Cookie 无 `Secure` / 单进程会话 / `/api/*` 认证边界）
- `docs/architecture/csm-v1-foundation-architecture.md`（部署、规模假设 10⁵ / 50 并发、连接池、Risk #1 / #3）
- `docs/architecture/f012-project-foundation-handoff.md`（Q4 / Q5 / Q6）、`docs/architecture/f013-auth-handoff.md`（PROPOSED-4 探针、`/api/health` 不豁免、Constraints #10）、`docs/architecture/f014-soft-delete-handoff.md`
- `docs/reviews/f012-project-foundation.md`（Follow-up 1：强制 prod + 部署断言）、`docs/reviews/f013-auth.md`（REV-01 文档面）
- `docs/database/csm-v1-schema-design.md`（决策 1：locale / 部署文档须记录项）、`docs/database/f012-baseline-migration.md`（§9；§6 决策「生产禁止 downgrade」）
- 现有产物（只读核实）：`docker-compose.dev.yml`、`README.md`、`.env.example`、`backend/app/config.py`、`backend/app/main.py`、`backend/app/common/error_handlers.py`、`backend/app/api/health.py`、`backend/migrations/env.py`、`alembic.ini`、`frontend/vite.config.ts`、`frontend/package.json`、`frontend/src/api/*.ts`

---

## 现状核实（只读检查结论）

| 项 | 现状（已核实） |
|---|---|
| 生产编排 | **不存在**。仓库内无 `docker-compose.prod.yml`，无任何 `Dockerfile`，无 nginx 配置，无 `.dockerignore`（`find` 全仓库仅命中 `docker-compose.dev.yml`）。 |
| 生产前端产物 | **不存在接线**。`frontend/package.json` 有 `build`（`vue-tsc --noEmit && vite build`），但 `dist/` 被 `.gitignore` 忽略；无静态服务器与 `/api` 反向代理配置。 |
| 部署文档 | **不存在**。无 `docs/deployment/`；`docs/project/repository-structure.md` 未定义该目录职责。 |
| `docker-compose.dev.yml` | 仅 PostgreSQL；顶部已显式声明「不是 F015 的生产交付物」；把 `5432:5432` 发布到宿主（**dev 专用**）。 |
| `CSM_ENVIRONMENT` | 已存在（`config.py:27`，默认 `"dev"`），**当前仅作标签**：`main.py` 未读取任何文档面开关（`grep` 仅命中 `config.py:27`）。 |
| 框架文档面 | FastAPI 默认开启：`create_app` 未传 `docs_url` / `redoc_url` / `openapi_url`，故 `/docs`、`/redoc`、`/openapi.json` 未认证可达（F013 REV-01 实测均 `200`）。 |
| 认证边界 | 已存在且 fail-closed：`AuthMiddleware` 在路由前保护全部 `/api/*`，`EXEMPT = {("POST", "/api/auth/login")}`；`/api/health` **不豁免**。 |
| dev-only 自检面 | **已由 F001 彻底删除**（`_foundation` 不存在；F013 G-E 有 guard 固定）。 |
| 后端运行形态 | dev 用 `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend`；`requirements.txt` 已含 `uvicorn[standard]`、`alembic`、`psycopg[binary]`、`argon2-cffi`。 |
| 连接池 | `config.py` 默认 `pool_size=5`、`max_overflow=10`、`pool_timeout=30`、`pool_recycle=1800`、`pool_pre_ping=True`（`db/session.py`）。 |
| Alembic | `alembic.ini` 的 `script_location = backend/migrations`，DSN 由 `migrations/env.py` 从 `CSM_DATABASE_URL` 读取，**不在仓库硬编码**。 |
| 前端 API 形态 | `frontend/src/api/*.ts` 全部使用**同源相对路径** `/api/...`（无 `VITE_API_BASE` / 无绝对 host），浏览器 `fetch` 默认 `credentials: 'same-origin'` → 由 nginx 同源 `/api` 反代即可，**无需改前端源码**。 |
| Database / 领域 | `clusters`（`0001`）+ `users` / `sessions`（`0002`）已存在并冻结；无子资源表。F015 无 Schema 变更。 |
| 相关架构决策 | ADR-0001 ~ ADR-0005 全部 `ACCEPTED`；DEC-016（docker-compose 打包）`RESOLVED`。**F015 不改任何 ADR、领域规则、契约。** |

**结论**：F015 是在**非空、已具备 F012/F013/F014 基座**的项目上的增量交付；所需的结构基座（认证边界、`prod` 标签、迁移链、持久化表）**已齐备**，缺的是**生产交付层**。

---

## Architecture Summary

**目标**：把 CSM 从「开发者本机能跑」变成「运维可部署、可登录、可运维、可升级的内网系统」，且不扩大任何访问面（认证边界、公共数据面、暴露端口）。

**对现有系统的影响**

| 模块 | 影响 |
|---|---|
| 领域对象 / 数据模型 | 无 |
| 数据库 Schema / migration | **无变更**（`database: false`） |
| 后端源码 | **1 处行为变更**：`create_app` 在 `environment == "prod"` 时关闭框架文档面（`docs_url` / `redoc_url` / `openapi_url = None`）。无其他行为变更 |
| 前端源码 | **无变更**（同源相对 `/api`；生产构建由部署层镜像完成） |
| API 契约 | **无新增 / 无修改**；不新增 `/api/*` 认证豁免 |
| 新增交付层 | **部署产物**：`docker-compose.prod.yml`、`backend/Dockerfile`、`frontend/Dockerfile`、`deploy/nginx/default.conf`、`deploy/env.prod.example`、`.dockerignore`、`docs/deployment/*` |

**方案要点**

1. **生产编排独立文件** `docker-compose.prod.yml`（与 `docker-compose.dev.yml` 分离）：三服务 `postgres` / `app` / `nginx`；命名卷；仅 nginx 发布端口；`restart: unless-stopped`；健康检查驱动的启动顺序。
2. **`prod` 环境双重落实**（F012 Follow-up 1）：编排**硬编码** `CSM_ENVIRONMENT=prod`（非运维可遗漏项），后端据此**关闭** `/docs` / `/redoc` / `/openapi.json`；并以「可失败断言」固定（后端测试 + 编排静态 guard）。
3. **探针选 (a) 容器 / 运行时级（传输层）**：`postgres` 用 `pg_isready`，`app` 用 TCP 连接 `:8000`，`nginx` 用 TCP 连接 `:80`。**不新增任何 HTTP 路径、不新增 `/api/*` 豁免、不返回任何产品数据**；健康状态经 `docker compose ps` / `docker inspect` 对运维与编排可见。
4. **凭据外部注入**：生产凭据 / DSN 一律由**仓库外**的环境文件或环境变量提供；编排使用 Compose 的**必填变量语法** `${VAR:?…}`，缺失即启动失败；仓库内**无任何可认证的生产口令字面量**。
5. **数据持久化**：PostgreSQL 数据落**命名卷** `csm-prod-pgdata`；升级文档**禁止** `down -v`。
6. **迁移执行点 = 显式运维步骤**（非 entrypoint 自动执行）：`docker compose run --rm app alembic upgrade head`，幂等；生产**禁止** `alembic downgrade`（文档与产物双重约束）。
7. **locale / 版本固定**：`postgres:16` + `POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale=C.UTF-8"` + `LANG` / `LC_ALL=C.UTF-8`（与 dev 一致），部署文档记录 `datcollate` / `datctype` / `encoding` / PG 大版本，并把「大小写敏感」直连 SQL 断言作为持续回归。
8. **连接池上限**：`pool_size=5` + `max_overflow=10` = 单进程上限 **15** 条连接，远低于 PostgreSQL `max_connections=100`；在编排中显式写出并文档化算术依据。
9. **部署文档单一权威**：新增 `docs/deployment/csm-v1-internal-deployment.md`；`README.md` 保留开发流程并指向该文档。
10. **不引入任何§23 排除项**（HTTPS / 域名 / 公网入口 / K8s / 多机 / 监控告警 / MQ / Redis / ES）。

---

## Domain Impact

**无。**

- 不新增、不修改任何领域对象、资源关系、状态模型、唯一性规则或生命周期语义。
- 不创建任何资源表 / 关系列；不固化 VM→BareMetal、Container→载体（UNCONFIRMED）。
- `User` / `Session` 仍不是 Resource。
- 部署形态**不得使**以下已确认语义在部署环境中静默失效：大小写敏感唯一性（§22 / ADR-0002）、已删不占唯一性（ADR-0004）、历史保留（§25 / R-DELETE-001）、两态认证边界（ADR-0005 / R-AUTH-003）。F015 的 locale / 版本 / 卷 / 端口 / 环境标签配置均以「不改变上述语义」为约束，并以测试 / 断言固定。

---

## Data Layer Impact

**不需要任何 Schema、索引、约束或 migration 变更。`database: false`（判定标准 = 是否需要 schema 变更）。**

数据层需要被**部署产物保证**的事实（不是新增设计）：

1. **数据持久化**：PostgreSQL 数据目录挂载到**命名卷**（`csm-prod-pgdata → /var/lib/postgresql/data`），容器删除 / 重建不丢数据（AC-07）。
2. **locale / encoding 在 initdb 时固定**：命名卷首次初始化即决定 `datcollate` / `datctype` / `encoding`；该事实必须被文档化并提供可复现的直连断言（AC-09⑥）。**注意**：已存在的卷不会被新 `POSTGRES_INITDB_ARGS` 修正 —— 文档必须要求「录入生产数据前先校验 locale，不符则重建卷」。
3. **PG 大版本固定**：镜像 tag 固定到 PostgreSQL `16`（与 `0001` / `0002` 迁移和本地测试一致）。
4. **迁移可重复应用**：`alembic upgrade head` 在 head 处为 no-op（AC-08）。
5. **无 Schema 破坏性动作**：生产编排 / 文档不得出现 `alembic downgrade`、`down -v`（会 DROP 并丢历史）。

数据层**唯一**新增内容为**测试 / 部署断言**（非 Schema），由 Backend / Tester 承担。

---

## Backend Work

Backend Agent 需交付：

1. **`prod` 关闭框架文档面（唯一的后端行为变更，REQUIRED）**
   - 在 `create_app`（`backend/app/main.py`）按 `settings.environment` 传参：`environment == "prod"` → `docs_url=None`、`redoc_url=None`、`openapi_url=None`；`dev` / `test` 保持现状（默认开启）。
   - 不改动 `AuthMiddleware`、`EXEMPT`、错误处理、路由、`/api/health` 实现或任何 `/api/*` 语义。
   - 不给 `config.py` 增加新的「文档开关」环境变量（避免多重真相；`CSM_ENVIRONMENT` 已足够）。
2. **生产镜像 `backend/Dockerfile`（新）**
   - 基础镜像 `python:3.12-slim`（与 `README.md` §2 的 3.12 一致）；`pip install -r requirements.txt`（**不含** `requirements-dev.txt`）。
   - 构建上下文 = **仓库根**（需要 `requirements.txt` + `alembic.ini` + `backend/`）；镜像内含 `backend/app`、`backend/migrations`、`alembic.ini`，使 `alembic upgrade head` 与 `python -m app.auth.cli ...` 可直接在容器内运行。
   - 运行命令：`uvicorn app.main:app --host 0.0.0.0 --port 8000`（**无 `--reload`**）。
   - 以**非 root** 用户运行；不写死任何凭据 / DSN；不在镜像内设置 `CSM_ENVIRONMENT`（由编排注入）。
3. **`.dockerignore`（新，仓库根）**：排除 `.git`、`.venv`、`node_modules`、`frontend/node_modules`、`frontend/dist`、`tests`、`docs`、缓存目录等，缩小构建上下文。
4. **不新增依赖**（`argon2-cffi` 等已存在；生产镜像只用 `requirements.txt`）。

**明确不做**：不改 Schema / migration；不改 `/api/*` 行为；不新增探针 HTTP 端点；不新增 `/api/*` 豁免；不实现备份 / 恢复；不实现 CI/CD。

---

## Frontend Work

**`None`。**

理由（REQUIRED 判定，含被拒绝替代）：

- 前端所有 API 调用使用**同源相对路径** `/api/...`（`frontend/src/api/auth.ts`、`clusters.ts`），浏览器 `fetch` 默认 `credentials: 'same-origin'`；nginx 同源提供 SPA 并反代 `/api` 后，**无需改动任何前端源码 / 配置**（Vite 默认 `base: '/'`，`vite.config.ts` 的 `server.proxy` 仅作用于 dev）。
- 前端**生产构建**（`npm run build` → `dist/`）在部署层由 `frontend/Dockerfile` 的多阶段构建完成，产物由 nginx 直接服务。这属于**部署产物**，不构成前端源码分支。
- **被拒绝的替代**：(i) 显式新增 `frontend: true` 并要求一次「前端接线」改动 —— 无实际待改内容，会制造空分支与空验收；(ii) 增加 `VITE_API_BASE` 等构建期配置 —— 无需求支撑，且会引入「部署时前端配置」这一新失败面（`Simple First`）。
- **边界说明**：若实现过程中发现**确有必要**的前端改动（例如生产构建路径 / 同源假设不成立），应视为前端分支被重新打开，并回到本 Handoff 修订 `frontend` 层判定；当前证据不支持该必要性的存在。

---

## Deployment Work

Deployment Agent（可由 Backend 承担）需交付：

1. **`docker-compose.prod.yml`（新，仓库根）** — 与 `docker-compose.dev.yml` 对称、互相独立：
   - 服务：`postgres`（`postgres:16`）、`app`（build `backend/Dockerfile`，context `.`）、`nginx`（build `frontend/Dockerfile`，context `.`，`dockerfile: frontend/Dockerfile`；因该 Dockerfile 需 `COPY deploy/nginx/default.conf`，仓库根上下文是唯一自洽解）。
   - **仅 nginx 发布端口**：`ports: ["${CSM_HTTP_PORT:-80}:80"]`；`app` 与 `postgres` 只用 `expose`（`8000` / `5432`），**不发布到宿主 / 内网**。
   - **命名卷**：`csm-prod-pgdata → /var/lib/postgresql/data`。
   - **启动顺序**：`app depends_on postgres: condition: service_healthy`；`nginx depends_on app: condition: service_healthy`。
   - **`restart: unless-stopped`**（三个服务；NQ-2 收口 —— 工程默认，非产品验收项）。
   - **健康检查（容器 / 运行时级，不发起 HTTP）**：`postgres` = `pg_isready`；`app` = TCP 连接 `127.0.0.1:8000`；`nginx` = TCP 连接 `127.0.0.1:80`。
   - **环境**：`app` 硬编码 `CSM_ENVIRONMENT: "prod"`；`CSM_DATABASE_URL` 与数据库凭据使用**必填变量语法**从外部注入；显式写出 `CSM_DB_POOL_SIZE` / `CSM_DB_MAX_OVERFLOW`；`postgres` 固定 `POSTGRES_INITDB_ARGS` / `LANG` / `LC_ALL`。
   - 不得包含：TLS / 证书 / 域名 / 公网入口 / `5432` 或 `8000` 的宿主发布。
2. **`deploy/nginx/default.conf`（新）**：监听 `80`；`root` 指向镜像内的前端 `dist`；`location / { try_files $uri $uri/ /index.html; }`；`location /api/ { proxy_pass http://app:8000; ... }`（保留路径 / 方法 / Cookie / `Host`）；**对 `/docs`、`/redoc`、`/openapi.json` 显式 `return 404`**（在 SPA fallback 之前）；无任何 TLS / 证书 / 域名指令。
3. **`frontend/Dockerfile`（新，多阶段）**：builder 阶段 `node:22-alpine`（满足 `package.json` engines `^20.19 || >=22.12`）执行 `npm ci` + `npm run build`；运行阶段 `nginx:stable-alpine` 复制 `dist` 与 `deploy/nginx/default.conf`。
4. **`deploy/env.prod.example`（新）**：**只含变量名与说明，值为空**（不能认证任何实例），列出 `CSM_POSTGRES_USER` / `CSM_POSTGRES_PASSWORD` / `CSM_POSTGRES_DB` / `CSM_DATABASE_URL` / `CSM_HTTP_PORT` 等。**不含任何默认口令**。
   > 命名说明：`.gitignore` 的 `.env.*` 会忽略 `.env.prod.example`（白名单只有 `.env.example` / `.env.sample` / `.env.template`），故模板命名为 `deploy/env.prod.example`。如团队偏好 `.env.prod.example`，需同时把 `.gitignore` 白名单加入 `!.env.prod.example`（替代方案，非必需）。
5. **`docs/deployment/csm-v1-internal-deployment.md`（新，唯一权威部署文档）**：前置条件、部署命令序列、首次初始化（迁移 + 初始管理员）、端到端验证、升级步骤、locale / encoding / PG 大版本、连接池上限依据、内网 HTTP 约束、探测方式、账号停用与运维约束 —— 覆盖 AC-09 的 10 项。
6. **`README.md` 更新**：保留 §3 本地开发流程；新增「生产内网部署」入口指向 `docs/deployment/csm-v1-internal-deployment.md`；修正 `docker-compose.dev.yml` 的用途表述（从「属 F015」改为「指向 `docker-compose.prod.yml` 与部署文档」）。
7. **`docs/project/repository-structure.md` 同步（PROPOSED，协调器落盘）**：新增 `docs/deployment/` 与 `deploy/` 的职责说明。
8. **不做**：一键部署脚本（产品 PROPOSED-4 未承诺）；备份 / 恢复步骤（PROPOSED-1）；CI/CD / 内网 registry；开机自启的 systemd 单元；宿主防火墙 / 磁盘 / VM 规格。

**文件所有权（并行安全）**：Backend = `backend/**` + `tests/**` + `backend/Dockerfile` + `.dockerignore`；Deployment = `docker-compose.prod.yml` + `deploy/**` + `frontend/Dockerfile` + `README.md` + `docs/deployment/**`；`docs/**`（architecture / project / product）由协调器统一落盘。

---

## API Contract

### Status

```text
NOT_REQUIRED
```

### Contract

**F015 不新增、不修改任何产品 API 端点；不新增任何 `/api/*` 认证豁免。**

理由与边界（REQUIRED）：

1. F015 是 ENABLER；`project-plan.yaml > F015.requirements` 仅 `R-DEPLOY-001 ~ 003`，无端点需求。
2. **探针走 (a) 容器 / 运行时级（传输层）机制**，因此**根本不引入 HTTP 路径**：既无 `/api/*` 成员，也无 `/api` 之外的 `/healthz` 式路径。F013 PROPOSED-4 的 (b) 分支（`/healthz`）**未被采纳**（见技术决策 Q4）。
3. 现有产品端点（`/api/health`、`/api/clusters*`、`/api/auth/*`）语义**完全不变**：
   - 未认证访问除 `POST /api/auth/login` 外的全部 `/api/*` → `401 UNAUTHENTICATED`（含 `/api/health`）；
   - 已认证 `GET /api/health` → `200 {"status":"ok","database":"ok"}`。
   - `EXEMPT` 集合保持 `{("POST", "/api/auth/login")}`。
4. **因此不存在「API Contract BLOCKED」的可能**：本 Feature 不需要新的协议决策。

> 若实现阶段出现「必须用 HTTP 路径做探测」的结论，则属对本 Handoff 的偏离，须先回到 Architecture 修订（不得自行新增 `/api` 之外路径或 `/api/*` 豁免）。

---

## Architecture Handoff — 12 问逐条回应

### Q1 — 交付层判定（含部署产物记录方式）

**结论**

```text
database:   false
backend:    true
frontend:   false
deployment: true     # 新增键（PROPOSED，请协调器/PM 写入 project-plan.yaml > F015.layers）
```

- `database: false`：无 Schema / 索引 / 约束 / migration 变更。判定标准是「是否需要 schema 变更」，不是「是否存在数据库断言」（与 F001 / F014 同标准）。`implementation.database_design` 应为 `NOT_REQUIRED`。
- `backend: true`：`prod` 关闭文档面（1 处行为变更）+ `backend/Dockerfile` + `.dockerignore` + 相关测试与 guard。
- `frontend: false`：无 `frontend/src/**` 改动（见 Frontend Work 的理由）。生产前端构建属 `deployment` 层。
- **部署产物记录方式（本问要求明确者）**：`layers` 现有键不足以表达。**建议新增 `deployment: true`**，并在 `implementation` 中增加 `deployment` 状态字段（如 `deployment: COMPLETE`）。若 PM 坚持不扩展 `layers` schema，则退而求其次：在 `F015.implementation` 下用 `deployment: COMPLETE` + 备注文件清单记录，**但**这会丢失「有独立实现分支」这一信息；不推荐。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 把部署产物塞进 `backend: true` | 语义错误：部署产物不是后端代码；Frontend/Backend Reviewer 都不会覆盖 compose / nginx / 部署文档 |
| 把部署产物塞进某一现有层并在 `contract.doc` 记录 | `contract` 字段语义是 API 契约，不是部署产物清单；会污染既有字段含义 |
| 新增整层 `frontend: true` 以「占有」前端构建 | 会制造空实现分支（无源码改动），违反「层 = 需要实现的分支」语义 |
| 不记录部署产物（仅存在于 diff 中） | 违反 AGENTS §4「重要规则不能只存在于源代码中」；后续 Feature 无法从计划看出部署产物归属 |

### Q2 — 生产编排形态

**结论**

- **文件落点**：新增 `docker-compose.prod.yml`（仓库根，与 `docker-compose.dev.yml` 并列）。
- **镜像构建**：`app` 用 `backend/Dockerfile`（context = 仓库根）；`nginx + 前端` 用 `frontend/Dockerfile`（**context = 仓库根**，`dockerfile: frontend/Dockerfile`；该 Dockerfile 需要 `COPY deploy/nginx/default.conf`，该路径在 `frontend/` 之外，故仓库根上下文是唯一自洽解）。**不从本机构建前端后挂载目录**。
- **服务依赖 / 启动顺序**：`postgres`（healthy）→ `app`（healthy）→ `nginx`；由 `depends_on: condition: service_healthy` 表达（解析 NQ-6）。
- **数据卷命名**：`csm-prod-pgdata`（命名卷，非 bind mount）。
- **端口发布**：仅 `nginx` 的 `"${CSM_HTTP_PORT:-80}:80"`；`app` / `postgres` 仅 `expose`。
- **`restart` 策略**：`unless-stopped`（三个服务）。NQ-2 收口为**工程默认**，写入部署文档，**不作为产品验收项**。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 在单个 `docker-compose.yml` 内用 `profiles:` 区分 dev / prod | 会把「dev 专用 PostgreSQL（发布 5432）」与「生产编排」混进同一文件，增加误操作（`--profile` 遗漏 / 组合错误）风险；`docker-compose.dev.yml` 已显式声明自身用途，分离更安全（`Simple First`） |
| 修改 `docker-compose.dev.yml` 使其成为通用文件 | 会破坏 F012 已交付、已 Review 的本地开发路径，违反 Product Handoff「开发形态保持有效」 |
| 应用镜像内自动构建前端并单容器交付 | 违反 ADR-0001 的三容器组成（nginx 为入口）；把静态服务与 ASGI 进程耦合，无法独立重启 / 观察 |
| bind mount 源码 / `dist` 进容器 | 生产形态不应依赖宿主目录结构；与「环境可复现」相悖 |
| 发布 `app` / `postgres` 端口以便排查 | 直接违反 AC-10 / AC-03 与 R-DEPLOY-003；排查走 `docker compose exec` |
| 引入 `depends_on` 之外的等待脚本 / wait-for-it | 无需求支撑；`condition: service_healthy` 已是 Compose 原生能力 |

### Q3 — `prod` 环境与 dev-only 面关闭的落实与可失败验证

**结论**

1. **强制 `prod`（落实 F012 Follow-up 1）**：`docker-compose.prod.yml` 的 `app` 服务**硬编码** `CSM_ENVIRONMENT: "prod"`。它是生产部署的组成，不是可遗漏的运维输入。**不**把 `CSM_ENVIRONMENT` 放进「必填变量」——那会引入「运维漏填 → 退回 dev」的 fail-open。
2. **关闭方式**：`create_app` 在 `environment == "prod"` 时传 `docs_url=None, redoc_url=None, openapi_url=None` → 三个路径在应用层返回 `404`。`dev` / `test` 保持不变（本地开发不受影响）。
3. **入口层纵深**：`deploy/nginx/default.conf` 对 `/docs`、`/redoc`、`/openapi.json` 显式 `return 404`（在 SPA fallback 之前）。
4. **可失败验证（三处，均映射 AC-05）**：
   - **T-01（应用层）**：`create_app(Settings(environment="prod", ...))` + `TestClient`：`GET /docs`、`/redoc`、`/openapi.json` **均 404**（不是 200；不是 401）。
   - **T-02（dev 保留）**：`environment="dev"` 下 `GET /openapi.json` → `200`（证明变更被 `prod` 条件限定，不是全局删除能力）。
   - **G-01（部署断言）**：静态 guard 读取 `docker-compose.prod.yml`，断言 `app.environment.CSM_ENVIRONMENT == "prod"`；`G-06` 断言 nginx conf 含三条显式 404。
   - **T-06（E2E）**：部署后 `curl -o /dev/null -w '%{http_code}' http://<IP>/openapi.json` → `404`（经 nginx）。
5. **不复活任何 dev-only 自检面**：`_foundation` 已由 F001 删除；F013 的 G-E guard 继续覆盖；F015 不新增任何等价面（T-04）。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 保持 `CSM_ENVIRONMENT` 仅作标签（现状） | 直接违反 F012 Follow-up 1 与 AC-05；文档面对未认证访问者暴露完整 API schema |
| 把 `environment` 默认值从 `dev` 改为 `prod`（review 曾提的 fail-closed 默认） | 会改变 F012 的本地开发默认语义（既有 dev 流程 / 测试假设 `dev`），属跨 Feature 行为变更，收益不足以支撑；F015 已有「编排硬编码 prod + 部署断言」这一更强且局部的落实 |
| 新增 `CSM_DOCS_ENABLED` 之类独立开关 | 引入第二个真相来源，可能与 `CSM_ENVIRONMENT` 冲突；无需求 |
| 让 `/docs` 等返回 `401`（纳入认证面） | 会扩大 `/api/*` 之外的认证语义，违反 F013 Constraints #10 与 REV-01「不得扩大 `/api` 边界」 |
| 保留在线文档但仅限已认证 | 属产品 NQ-3 的可选项，**当前裁定为关闭**；如需变更须用户显式裁定并同步 AC |

### Q4 — 探针设计（选 (a) 还是 (b)）

**结论：选 (a) 容器 / 运行时级（传输层）探测。**

| 服务 | 探测方式 | 说明 |
|---|---|---|
| `postgres` | `pg_isready -U <user> -d <db>`（PostgreSQL 原生协议） | 反映数据库可接受连接（含就绪） |
| `app` | **TCP 连接** `127.0.0.1:8000`（不发送任何 HTTP 请求） | 反映 ASGI 进程正在监听 |
| `nginx` | **TCP 连接** `127.0.0.1:80` | 反映入口监听 |

落在各服务的 Compose `healthcheck`，状态经 `docker compose ps` / `docker inspect` 对**运维与编排**可见，并被 `depends_on: condition: service_healthy` 直接消费。

**为什么不选 (b)（`/api` 之外的 HTTP 路径，如 `/healthz`）**

1. 产品明确倾向 (a)：不新增任何无收益的 HTTP 暴露面（`requirements.md` §25 Simple First；F015 产品 #14）。
2. (b) 会创建一个**未认证可达的 HTTP 面**，必须永久以「非产品契约」身份维护；其边界（不检查数据库、不返回产品数据、仅 GET）需要额外 guard 才能防止漂移。
3. (a) 天然满足「不返回任何产品数据 / 会话 / 凭据 / 数据库内容」——TCP 探测**没有任何响应体**。
4. (a) **完全不触碰** `/api/*` 与 ADR-0005 白名单，F013 AC-01 / AC-13 不受任何影响。

**REQUIRED 不变量（探针）**

- 不新增 `/api/*` 认证豁免；`EXEMPT` 保持 `{("POST", "/api/auth/login")}`。
- 探针**不发起任何 HTTP 请求**；不引用 `/api`；**不返回任何数据**。
- 探针不得成为访问产品数据的路径。
- `/api/health` 保持受保护：未认证 `401`，已认证 `200`。

**可失败测试（映射 AC-06）**

- **T-03**：未认证 `GET /api/health` → `401 UNAUTHENTICATED`；未认证任一 `/api/clusters*` → `401` 且 body 不含资源数据；已认证 `GET /api/health` → `200 {"status":"ok","database":"ok"}`；`EXEMPT` 集合断言不变（**F013 AC-01 / AC-13 不回归**）。
- **G-07**：静态 guard 扫描 `docker-compose.prod.yml` 与 `backend/Dockerfile` 的 `healthcheck`：断言**不含** `curl` / `wget` / `http://` / `/api`（即探针不是 HTTP 且不触及产品面）。
- **G-01**：断言三个服务均声明 `healthcheck`（「探测必须存在」），且 `app` / `nginx` 的探测为 TCP 形式。
- **T-06（E2E）**：`docker compose ps` 三个服务 `healthy`；对 `:80` 的 TCP / HTTP 入口可达。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| (b) `/healthz` HTTP 路径 | 制造未认证 HTTP 面与永久「非契约」负担；与产品倾向相反 |
| 用 `/api/health` 做探针（新增豁免） | 直接违反 F013 REQUIRED #8 / AC-01 / AC-13 与 AC-06 |
| 用 `/api/health` 做探针（携带凭据） | 探针会接触会话 / 凭据，违反「探测不含凭据」；且把凭据引入编排 |
| 不设任何探测（仅靠进程存在） | 违反产品 #14 / AC-06；`depends_on` 与运维观察失去依据 |
| 应用层实现 `/healthz` 但仅监听内部端口 | 仍新增 HTTP 面与代码路径；(a) 已足够，无收益 |
| 用 nginx `curl http://127.0.0.1/`（HTTP 到静态页）自检 | 与 (a) 的「不发起 HTTP」相悖；TCP 检查已足够 |

### Q5 — 生产凭据 / DSN 外部注入与「产物内无生产默认口令」验证

**结论**

- **注入方式**：运行 `docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env up -d`（或等价的外部环境变量导出）。仓库内**不包含**任何可认证的生产口令 / DSN。
- **编排使用必填变量语法**：所有凭据类变量写作 `${VAR:?VAR 必须由部署环境提供}`，使**缺失即启动失败**（fail-closed，无静默默认）。
- **仓库内提供的模板**：`deploy/env.prod.example`，**只有变量名与注释、值为空**（空值不能认证任何实例）。
- **变量集合（PROPOSED 具体形态）**：`CSM_POSTGRES_USER` / `CSM_POSTGRES_PASSWORD` / `CSM_POSTGRES_DB`；`CSM_DATABASE_URL` 由编排以这些变量插值组装（避免同一口令在两处手工重复）。密码须为 URL-safe 字符或 URL 编码（写入部署文档）。
- **`.env.example` 与 `docker-compose.dev.yml` 的 `csm:csm` 明确属 dev-only**，不是生产产物，不作为 AC-10 的违反项；guard 的范围严格限定为**生产产物**。

**可失败验证（映射 AC-10）**

- **G-02**：静态 guard 扫描 `docker-compose.prod.yml`、`deploy/**`、`backend/Dockerfile`、`frontend/Dockerfile`：
  - 不存在字面量凭据（如 `csm:csm`、`POSTGRES_PASSWORD: <非插值值>`）；
  - 凭据类变量出现形态只能是 `${...}`；
  - 不存在带凭据默认值的 `${VAR:-<value>}`。
- **G-01**：断言 `postgres` / `app` 的凭据注入是外部化的（无 `ENV` 硬编码）。
- **T-06（运行时）**：在未提供环境文件时执行 `docker compose -f docker-compose.prod.yml config` → **失败**（证明没有内置默认）；提供后成功。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 在 compose 内提供 `${VAR:-csm}` 之类默认口令 | 直接违反 AC-10 / 产品 #19 |
| 提交真实 `.env.prod`（或含口令的示例） | 违反 `.gitignore` 首要目标与 AGENTS §6；且 `.env.*` 本就会被忽略 |
| 使用 Docker secrets（Swarm 专属） | 单机 `docker compose` 不提供该机制；引入 Swarm 违反 R-DEPLOY-001 与 §23 |
| 把口令写入镜像 `ENV` / 构建参数 | 会把凭据烘焙进镜像层，违反 AC-10 |
| 只提供 `CSM_DATABASE_URL` 而不提供 `POSTGRES_*` | PostgreSQL 容器需独立初始化账号；二者必须一致，故同时提供并由编排插值 |

### Q6 — 数据持久化与可复现验证

**结论**

- **命名卷** `csm-prod-pgdata` → `/var/lib/postgresql/data`（AC-07 明确要求命名持久卷）。
- 数据的存续与容器生命周期**解耦**：容器停止 / 删除 / 重建不影响卷内数据。
- 升级 / 排障文档**禁止** `down -v`、`docker volume rm`（会丢历史，与 §25 / R-DELETE-001 的意图相悖）。

**可复现验证（映射 AC-07，T-06 的一部分）**

1. `up -d` → 迁移 → 建立初始管理员 → 登录 → 登记一条 Cluster `persist-check`。
2. `docker compose stop` / `start` → 仍可查到该 Cluster。
3. `docker compose up -d --force-recreate`（容器被替换）→ 仍可查到。
4. 卷证据：`docker volume ls | grep csm-prod-pgdata` 存在；`docker compose down`（**不带 `-v`**）后 `up -d` → 数据仍在。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| bind mount 宿主目录 | 依赖宿主目录结构与权限，削弱可复现性；AC-07 明确命名卷 |
| 无卷（容器可写层） | 容器重建即丢数据，直接违反 AC-07 / §25 |
| 用 `down -v` 作为「干净重来」步骤写入文档 | 会销毁历史事实，违反 R-DELETE-001 的精神与 §25 |

### Q7 — migration 执行点与升级流程；生产禁止 downgrade

**结论**

- **执行点 = 显式运维步骤**（非 entrypoint 自动迁移）：
  ```bash
  # 1) 先起数据库并等待就绪
  docker compose -f docker-compose.prod.yml up -d postgres
  docker compose -f docker-compose.prod.yml ps                # 等待 postgres healthy
  # 2) 迁移（幂等；可在升级时重复执行）
  docker compose -f docker-compose.prod.yml run --rm --no-deps app alembic upgrade head
  # 3) 启动全栈
  docker compose -f docker-compose.prod.yml up -d
  ```
- **可重复应用**：`alembic upgrade head` 在 head 处为 no-op（AC-08）。文档要求升级流程**先**执行迁移**再**替换应用镜像。
- **生产禁止 downgrade**：部署文档与所有生产产物中**不得**出现 `alembic downgrade`；`downgrade` 仅存在于 F012 基线的 migration 文件中（供 dev / test 从空库重建），生产文档明确禁止使用（会 `DROP` 并丢历史）。
- **初始管理员**（首次初始化的一部分）：
  ```bash
  docker compose -f docker-compose.prod.yml run --rm app \
    python -m app.auth.cli create-initial-admin --username admin
  ```
  口令经 **stdin** 读取（TTY 无回显）；命令幂等（README §5.1）。文档**不得**给出示例口令。

**可失败验证（映射 AC-08）**

- **G-04**：静态 guard 断言生产产物（`docker-compose.prod.yml`、`deploy/**`）与部署文档中**不存在** `alembic downgrade`，且**不存在** `down -v`。
- **T-06**：对已部署数据库连续执行两次 `alembic upgrade head` → 均成功且第二次为 no-op（`alembic current` 稳定在 head）。
- （继承 F012 的 `tests/database/test_migrations.py`：`upgrade head` ×2 与 `downgrade base && upgrade head` 仍覆盖 dev / test 的迁移机制，不因此次变更回归。）

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 在 `app` entrypoint 里自动 `alembic upgrade head` | 隐式副作用、每次容器重启都触发、并发 / 部分失败难审计；且 AC-08 明确要求「部署 / 升级步骤包含」该命令 |
| 把迁移做成独立 `migrate` 服务并靠 `depends_on` 串联 | 相比 `run --rm` 多一个长期存在的服务定义，收益不足（`Simple First`） |
| 提供 `alembic downgrade` 作为回滚流程 | 生产禁止；会 DROP 并丢历史（ADR-0002 迁移策略「向前」） |
| 迁移与「创建初始管理员」合并为一条命令 | 两者失败语义与幂等性不同；应分步可观察 |

### Q8 — locale / encoding / PG 版本的固定方式与「大小写敏感」回归断言

**结论**

- **PG 大版本固定**：镜像 tag `postgres:16`（不用 `latest` / 不用浮动 major）。
- **locale / encoding 在 initdb 固定**：`POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale=C.UTF-8"` + `LANG=C.UTF-8` + `LC_ALL=C.UTF-8`（与 `docker-compose.dev.yml` 一致，避免 dev / prod 语义分叉）。
- **部署文档必须记录**（AC-09⑥）：目标库的 `datcollate` / `datctype` / `encoding` 与 PostgreSQL 大版本，并给出可复现断言：
  ```sql
  SELECT datname, datcollate, datctype, pg_encoding_to_char(encoding) AS encoding
  FROM pg_database WHERE datname = current_database();     -- 期望 C.UTF-8 / C.UTF-8 / UTF8
  SELECT ('cluster-a' = 'Cluster-A') AS case_sensitive;    -- 期望 false
  ```
- **持续回归**：`tests/database/` 的既有「绕应用层直连」断言继续作为「locale 未被静默改变」的权威回归（架构 Risk #1 / ADR-0002 §1）。F015 在部署文档中提供**对已部署库执行同一断言**的命令（T-05）。
- **重要运维事实（必须写入文档）**：locale 只在**卷首次初始化**时生效；对已存在命名卷修改 `POSTGRES_INITDB_ARGS` **不会**改变既有 cluster 的 locale。因此文档要求：**录入生产数据前先执行上述断言；若不符，删除卷重建（此时尚无历史数据）**。这是本次部署中唯一允许「删卷」的时点。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 依赖 `postgres` 镜像默认 locale | 会随镜像 / 宿主漂移，可能在无告警的情况下破坏 §22 大小写敏感（架构 Risk #1） |
| 用 `COLLATE "C"` / 列级 collation | ADR-0002 已裁定不采用（会改变中文排序语义）；F015 不得反向修改 |
| 用 `en_US.UTF-8` | 架构允许，但与 dev 使用的 `C.UTF-8` 不一致，会造成 dev / prod 语义分叉；统一为 `C.UTF-8` |
| 只测「中文往返」不测「大小写敏感」 | 二者正交；大小写敏感才是 §22 的断言对象 |
| 在 migration 内创建 database / 角色 / extension | F012 数据库设计明确由部署层负责；migration 保持不涉及实例级对象 |

### Q9 — 连接池上限的确定与记录

**结论**

- 取值：`CSM_DB_POOL_SIZE=5`、`CSM_DB_MAX_OVERFLOW=10`（沿用 `config.py` 默认，在 `docker-compose.prod.yml` 中**显式写出**）。
- **应用可同时持有的数据库连接上限 = `pool_size + max_overflow` = 15**（单进程单池；本项目 V1 单 ASGI 进程）。
- PostgreSQL `max_connections` 默认 `100`。余量 `100 − 15 = 85`，足以容纳迁移（`NullPool` 单连接）、`psql` 排障与运维。
- 不调整 PostgreSQL `max_connections`（无需求；避免「提前调优」）。
- 部署文档记录：数值、算术依据（`5 + 10 = 15 < 100`）、规模依据（DEC-015：总量约 10⁵、并发约 50）。

**可失败验证（映射 AC-09⑦）**

- **G-08**：静态 guard 读取 `docker-compose.prod.yml`，断言 `CSM_DB_POOL_SIZE` / `CSM_DB_MAX_OVERFLOW` 已显式设置，且 `pool_size + max_overflow < 100`（文档化的 `max_connections`）。
- **G-05**：部署文档内容清单包含「连接池上限依据」一项。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 依赖 `config.py` 默认而不在编排显式写出 | 上限不可见、不可断言；「文档必须明确连接池上限」要求配置显式 |
| 把池设为 50（≈并发数） | 50 + overflow 会逼近 `max_connections`，失去运维余量；无需求支撑 |
| 提高 PostgreSQL `max_connections` | 无需求；属「生产数据库参数调优」，产品明确排除 |
| 用 PgBouncer 等连接池中间件 | 引入额外基础设施，违反 ADR-0001 Constraints #1 与 §23 |

### Q10 — 部署文档落点与权威来源

**结论**

- **唯一权威部署文档**：新增 `docs/deployment/csm-v1-internal-deployment.md`（运维向：前置条件 → 部署 → 初始化 → 验证 → 升级 → 约束与记录）。
- **`README.md` 的职责**：保留 §3 本地开发流程（继续有效），新增「生产内网部署」小节**指向** `docs/deployment/...`；不在 README 复制部署正文（满足 AGENTS §4「同一份详细信息只维护一个权威来源」）。
- **目录职责同步**：`docs/project/repository-structure.md` 需新增 `docs/deployment/` 与 `deploy/` 两项（PROPOSED，协调器落盘）。
- **`docker-compose.dev.yml` 用途表述**：其顶部「属 F015」的措辞在 F015 交付后**已过时**；应改为指向 `docker-compose.prod.yml` 与部署文档，并保留「dev 专用、非生产」的定性。**仅改措辞与指向，不改其行为**（仍只发布 `5432`，仍只提供本地开发数据库）。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 只写 README（不建 `docs/deployment/`） | 部署文档会与开发流程混在同一文件，篇幅与读者不同；且 README 已有 8 节，继续膨胀不利于维护 |
| 只建 `docs/deployment/` 而不更新 README | 新运维人员的第一入口是 README；不更新会使其只看到开发流程 |
| 把部署文档放进 `docs/architecture/` | 架构目录承载设计决策，非运维操作步骤；会混淆读者与职责 |
| 保留 `docker-compose.dev.yml` 的「属 F015」措辞 | 交付后成为误导性描述（F015 已有独立生产 compose） |

### Q11 — 端到端验收方法与所需证据层级

**证据层级（按可复现性分三层；不允许把低层证据当作高层结论）**

| 层 | 内容 | 可覆盖的 AC |
|---|---|---|
| **L1 静态 / 结构证据**（仓库内可失败断言） | G-01 ~ G-08：编排、nginx、文档、凭据、越界能力、探针不变量 | AC-03、AC-05、AC-08、AC-09、AC-10（静态面）、AC-11 |
| **L2 等价环境 E2E**（有 Docker 的机器 / CI，`docker compose -f docker-compose.prod.yml`） | 构建 → 迁移（×2）→ 建管理员 → 经 `:80` 登录 → 登记 / 查询 Cluster → 未认证 `401` → `/docs` `404` → 端口暴露检查 → 重启 / 重建后数据仍在 | AC-01（等价）、AC-04、AC-05、AC-06、AC-07、AC-08、AC-10（运行时） |
| **L3 真实内网虚拟机 + 另一台内网机器** | 干净 VM 上按**仅文档**部署，另一台机器浏览器访问 `http://<Internal IP>/` | AC-01、AC-02、AC-12（完整形式） |

**L2 的可行性与 NOT TESTED 规则**

- L1 与 L2 应在实现 / 测试阶段实际执行并提供输出证据（`docker compose ps`、`curl` 状态码、`pg_database` 查询、`docker volume ls`）。
- **L3 在 Agent 环境中通常不可得**：不得声称通过。必须在测试报告中**显式标注 `NOT TESTED`**，并给出可直接执行的 L3 复核清单（由用户 / 运维执行），同时以 L2 作为等价证据（明确其为「等价环境」而非「真实内网」）。
- 若连 L2 也无法执行（无 Docker），则 F015 的 E2E 部分整体标 `NOT TESTED`，仅以 L1 交付 —— 这必须在报告中明确，不得以 L1 冒充端到端可用。

**AC-12（文档可复现性）的口径**：对标 F012 AC-01 的「干净 checkout + 仅依文档」。可复现性的**可判定代理证据** = 文档步骤在 L2 环境中**逐条照抄执行**（不看源码、不补口头说明）即可达成 AC-01 ~ AC-04 的观察项；若 L3 不可得，AC-12 记为「L2 层面满足，真实 VM 未验证」。

**测试范围（最小集合）**：见 Test Work（T-01 ~ T-08、G-01 ~ G-08）。

**NQ-5 / NQ-7 收口**

- **NQ-5（探针机制二选一）** → 取 (a)（Q4）。
- **NQ-7（升级 / 回滚）** → 升级 = 迁移 + 替换应用镜像（文档化）；**镜像层面的回滚流程不在本 Feature**（无已确认规则；与 CI/CD 同属「本次未涉及」），文档不得暗示支持应用镜像降级（可能造成 schema 与代码不匹配）。

**被拒绝的替代**

| 方案 | 拒绝理由 |
|---|---|
| 仅做静态 guard，不做任何运行时验证 | 无法证明「可登录 / 可访问资源 / 数据持久化」；AC-04 / AC-07 不可判定 |
| 把 L2 结果表述为「已在独立内网虚拟机验证」 | 虚假陈述，违反 AGENTS §7 |
| 编写一键部署脚本作为验收前提 | 产品 PROPOSED-4 未承诺；AC-12 只要求文档可复现 |
| 用 dev compose 冒充生产验证 | dev compose 发布 `5432`、无 nginx、无 prod 标签，无法覆盖 AC-03 / AC-05 / AC-10 |

### Q12 — 显式边界声明（不在本 Feature）

F015 **不引入、不文档化、不暗示**：

1. HTTPS / TLS / 证书 / 域名 / 公网入口 / 外部网关（R-DEPLOY-003；§20）。
2. Kubernetes / 微服务化 / 多机部署 / 高可用 / 负载均衡 / 多 worker 横向扩展（R-DEPLOY-001；ADR-0001 Constraints #1；§23）。
3. 监控平台替代 / 告警平台 / 工单系统（§23）。
4. 消息队列 / Redis / Event Bus / CQRS / Elasticsearch（ADR-0001 Constraints #1；§23）。
5. RBAC / LDAP / AD / OAuth / SSO / MFA / 自助注册 / 口令找回（R-AUTH-002 / 003；ADR-0005 §1）。
6. 任何新业务功能、新 API、领域规则 / 状态 / 唯一性 / 生命周期变更（F015 是 ENABLER）。
7. 替换或删除开发形态：`docker-compose.dev.yml` 与 `README.md` §3 的本地开发流程保持有效（仅修正过时措辞与指向）。
8. 备份 / 恢复 / 灾备演练（产品 PROPOSED-1 / NQ-1；**不实现、不承诺**）。
9. 数据归档 / 清理 / 保留期限（与 F014 PROPOSED-3 同一悬空问题）。
10. CI/CD、内网镜像仓库、自动化发布与镜像回滚（NQ-4 / NQ-7）。
11. 宿主机运维：Docker / Compose 安装、开机自启（systemd）、防火墙与网络策略、VM 规格与磁盘容量。
12. 集中式日志采集 / 访问日志归档 / 审计日志；多环境（staging）；发布窗口与审批；用户手册 / 培训材料；生产数据库参数调优（除连接池上限外）。

**F015 只做**：CSM 自身组件（nginx + 应用 + PostgreSQL）的单机内网部署产物与运行约束。

---

## Test Work

Testing Agent 应验证以下**最小集合**，逐条映射 AC-01 ~ AC-12。

| # | 测试 | 层次 | AC |
|---|---|---|---|
| **T-01** | `create_app(Settings(environment="prod"))` → `GET /docs` / `/redoc` / `/openapi.json` **均 404**（非 200、非 schema 内容） | API / 配置 | AC-05 |
| **T-02** | `environment="dev"` → `GET /openapi.json` → `200`（prod 变更被正确限定，能力未被全局删除） | API / 配置 | AC-05 支撑 |
| **T-03** | 未认证 `GET /api/health` → `401 UNAUTHENTICATED`；未认证任一 `/api/clusters*` → `401` 且 body 不含资源数据；已认证 `GET /api/health` → `200 {"status":"ok","database":"ok"}`；`auth.middleware.EXEMPT == {("POST","/api/auth/login")}` | API | AC-06、AC-04④（并证 F013 AC-01 / AC-13 不回归） |
| **T-04** | 静态 guard：`backend/app/**` 中不存在 `_foundation` 或任何 dev-only 自检面；无新增非 `/api` 产品路由 | 静态 | AC-05 |
| **T-05** | 对**已部署**数据库直连（绕应用）执行：`datcollate` / `datctype` = `C.UTF-8`、`encoding` = `UTF8`；`SELECT ('cluster-a'='Cluster-A')` = `false` | DB（直连） | AC-09⑥、架构 Risk #1 |
| **T-06** | **等价环境 E2E**：`docker compose -f docker-compose.prod.yml up -d --build` → 迁移 ×2（幂等）→ `create-initial-admin` → 经 `http://127.0.0.1/` 登录 → `POST`/`GET /api/clusters` 往返 → 未认证 `401` → `/docs` `404` → 仅 `80` 端口发布（`ss -ltn` / `compose ps`）→ `stop`/`start`、`up --force-recreate`、`down`+`up` 后数据仍在 | 部署 E2E | AC-01（等价）、AC-04、AC-05、AC-06、AC-07、AC-08、AC-10 |
| **T-07** | 未认证访问入口 `http://<IP>/` → 返回 SPA（HTML）而非 401 JSON，浏览器呈现登录页 | E2E / 前端集成 | AC-04① |
| **T-08** | **真实内网虚拟机 + 另一台内网机器**：仅依文档部署，另一台机器访问 `http://<Internal IP>/` 完成 AC-01 ~ AC-04 观察项 | 人工 / 运维 | AC-01、AC-02、AC-12（**L3 不可得时标 `NOT TESTED`**） |
| **G-01** | `docker-compose.prod.yml`：`app.environment.CSM_ENVIRONMENT == "prod"`；仅 `nginx` 有 `ports`（`8000` / `5432` 仅 `expose`）；三个服务有 `healthcheck` 且 `app`/`nginx` 为 TCP 形式；命名卷存在；`restart: unless-stopped`；`app.depends_on postgres: service_healthy`；`nginx.depends_on app: service_healthy` | 静态（编排） | AC-03、AC-05、AC-06、AC-07、AC-10 |
| **G-02** | 生产产物（`docker-compose.prod.yml`、`deploy/**`、两个 `Dockerfile`）**无字面量凭据**；凭据变量只以 `${VAR:?...}` 出现；无带默认值的 `${VAR:-...}` | 静态 | AC-10 |
| **G-03** | 生产产物与部署文档**不存在** HTTPS / 证书 / 域名 / 公网入口 / `k8s` / 多机 / 高可用 / 监控告警 / 工单 / 消息队列 / Redis / Elasticsearch 的配置或指引 | 静态 | AC-11 |
| **G-04** | 生产产物与部署文档**不存在** `alembic downgrade`、`down -v`、`docker volume rm` | 静态 | AC-08 |
| **G-05** | 部署文档内容清单（AC-09 的 10 项）逐项存在：前置条件 / 部署命令序列 / 首次初始化（迁移 + 初始管理员）/ 端到端验证 / 升级步骤 / locale·encoding·PG 版本 / 连接池上限依据 / 内网 HTTP 与 Cookie 无 `Secure` 约束 / 探测方式 / 账号停用与运维约束（或指向 `README.md` §5.1） | 静态（文档） | AC-09、AC-12 支撑 |
| **G-06** | `deploy/nginx/default.conf`：监听 `80`；`root` 为前端 `dist`；`/api/` 反代到 `app:8000`；`/docs`、`/redoc`、`/openapi.json` 显式 `return 404`；无 TLS / 证书 / 域名指令 | 静态 | AC-03、AC-05、AC-11 |
| **G-07** | 探针不变量：`docker-compose.prod.yml` 与 `backend/Dockerfile` 的 healthcheck **不含** `curl` / `wget` / `http://` / `/api`；未新增 `/api/*` 豁免（`EXEMPT` 不变） | 静态 | AC-06 |
| **G-08** | 连接池：`docker-compose.prod.yml` 显式设置 `CSM_DB_POOL_SIZE` / `CSM_DB_MAX_OVERFLOW`，且二者之和 < 文档化的 `max_connections`（100） | 静态 | AC-09⑦ |

**必测但不新增的继承回归**：F012 的迁移 / 约束测试（`tests/database/`）、F013 的认证边界与「唯一豁免」guard、F014 的软删 guard —— 均**不得**因 F015 出现回归。

**明确不在 F015 测试范围**：真实 HTTPS / 域名；多机 / K8s；备份 / 恢复；镜像回滚；CI/CD；宿主机防火墙 / systemd；集中日志；其他资源 Feature 的部署行为。

---

## Technical Decisions

### CONFIRMED

- 部署打包方式 = **docker-compose（nginx + 应用 + PostgreSQL）**；单台独立内网虚拟机；Internal IP + HTTP；不引入公网入口 / 域名 / HTTPS（ADR-0001 `ACCEPTED`、DEC-016、R-DEPLOY-001 ~ 003）。
- 技术栈 = Python + FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL；前端 Vue 3 + TS + Vite + Element Plus（ADR-0001）。
- PostgreSQL、默认 collation、版本化**向前** migration；生产禁止破坏性变更（ADR-0002）。
- `deleted_at` + partial unique index；历史保留（ADR-0004、§25）。
- 服务端会话 + HttpOnly Cookie + `SameSite=Lax` + **不设 `Secure`**（HTTP 取舍）；全部 `/api/*`（除登录）要求认证；V1 单进程（ADR-0005）。
- 错误信封 / 状态码语义（ADR-0003、`api-conventions.md`）——F015 不改。
- 禁止 EAV / 通用 `resources` 表 / STI / ORM 多态 / JSONB 万能模型（§4、§24）。
- 禁止微服务 / MQ / Redis / Event Bus / CQRS / K8s / Elasticsearch（§23、ADR-0001 Constraints #1）。
- `clusters`（`0001`）+ `users` / `sessions`（`0002`）Schema 与迁移链已冻结；F015 不改。
- `CSM_ENVIRONMENT` 已存在；`/docs` / `/redoc` / `/openapi.json` 生产关闭（F015 产品 #15）。

### REQUIRED

1. **`prod` 强制 + dev-only 面不可达**：生产编排硬编码 `CSM_ENVIRONMENT=prod`；后端在 `prod` 下关闭三个框架文档面；且此事实必须有**部署断言**（静态 guard）与**行为断言**（T-01 / T-02）。不得影响 dev / test。
2. **探针走产品认证面之外的机制**：容器 / 运行时级（传输层），**不新增 `/api/*` 豁免**、**不发起 HTTP**、**不返回任何资源 / 会话 / 凭据 / 数据库内容**；探针必须存在且可被运维与编排观察。
3. **认证边界不变**：除 `POST /api/auth/login` 外全部 `/api/*` 未认证一律 `401 UNAUTHENTICATED`；`/api/health` 不豁免；`EXEMPT` 集合不得扩大。
4. **凭据 / DSN 外部注入**：生产产物**不得**包含任何可用于生产的硬编码口令 / 连接串；缺失配置必须**启动失败**（fail-closed）。
5. **仅 nginx 对外**：`postgres` / `app` 端口不得发布到宿主 / 内网。
6. **数据持久化于命名卷**；容器停止 / 重建 / 删除后资源数据仍在；升级文档禁止 `down -v`。
7. **迁移显式、幂等、向前**：部署 / 升级步骤包含 `alembic upgrade head`，可重复应用；生产**禁止** `alembic downgrade`。
8. **locale / encoding / PG 版本固定并有回归**：UTF8 + 大小写敏感 locale（`C.UTF-8`）；文档记录 `datcollate` / `datctype` / `encoding` / PG 大版本；`SELECT ('cluster-a' = 'Cluster-A') = false` 有可执行断言。
9. **连接池上限显式且低于 `max_connections`**：`pool_size + max_overflow = 15 < 100`，并在文档记录依据。
10. **部署文档单一权威**：`docs/deployment/csm-v1-internal-deployment.md`；README 指向而不复制；`docker-compose.dev.yml` 用途定性保持「dev 专用」。
11. **无 Schema / migration / 领域规则 / 产品 API 变更**；不改任何 ADR；不改任何 API 契约正文。
12. **不复活任何 dev-only 自检面**。
13. **不越界**（Q12 全部条目），并以负向断言（G-03、G-04）固定。

### PROPOSED

1. **交付层记录方式**：`layers` 新增 `deployment: true`（另建议 `implementation.deployment`）。
2. **探针取 (a)**：`postgres` = `pg_isready`；`app` / `nginx` = TCP 连接（Q4）。
3. **nginx 对三个框架文档路径显式 `return 404`**（纵深防御，使 AC-05 的 E2E 观察无歧义）。
4. **文件落点**：`docker-compose.prod.yml`（根）、`backend/Dockerfile`、`frontend/Dockerfile`（nginx 服务 `build.context: .` + `dockerfile: frontend/Dockerfile`；见 Q2 修正）、`deploy/nginx/default.conf`、`deploy/env.prod.example`、`.dockerignore`（根）、`docs/deployment/csm-v1-internal-deployment.md`。
5. **凭据注入形态**：单一 `CSM_POSTGRES_PASSWORD`（+ user / db），DSN 由编排插值组装（密码须 URL-safe 或 URL 编码）。
6. **`restart: unless-stopped`**（三个服务；工程默认，非产品验收项 —— NQ-2）。
7. **`CSM_HTTP_PORT` 默认 `80`**（`${CSM_HTTP_PORT:-80}`）。
8. **迁移执行形态**：`docker compose run --rm --no-deps app alembic upgrade head`；初始管理员同法运行 CLI（TTY）。
9. **`docs/deployment/` 与 `deploy/` 记入 `repository-structure.md`**；`docker-compose.dev.yml` 顶部措辞改为指向生产 compose 与部署文档。
10. **`deploy/env.prod.example` 采用此命名**（因 `.gitignore` 的 `.env.*` 规则）；如改名为 `.env.prod.example` 则须同步白名单。
11. **前端生产镜像** builder 用 `node:22-alpine`、运行阶段 `nginx:stable-alpine`。

### OPEN（非阻塞）

1. **备份 / 恢复**（产品 PROPOSED-1 / NQ-1）：当前**不实现、不承诺**；无规则前部署文档不宣称备份能力。
2. **生产是否保留需认证的 API 文档面**（产品 PROPOSED-3 / NQ-3）：当前为「关闭」；如需改为「仅认证后可达」，须用户显式裁定并同步 AC 与部署文档（**不得**为此在 `/api/*` 上加豁免）。
3. **镜像获取方式**（NQ-4）：在 VM 上构建 vs 内网 registry 预构建 / 离线导入 —— 属实现与运维选择，不影响 AC。
4. **一键部署脚本**（产品 PROPOSED-4）：不承诺。
5. **镜像层面的升级回滚流程**（NQ-7）：不在本 Feature。
6. 连接池参数是否随实际负载微调：当前 15 已足够，无需求。
7. `Makefile` 是否增加生产便捷目标：非必需；实现方可选。

---

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| DR1 | **真实内网虚拟机不可得**，AC-01 / AC-02 / AC-12 无法端到端验证 | 以 L2 等价环境 E2E 作为等价证据 + 文档化 L3 复核清单；报告中显式 `NOT TESTED`，不得声称通过 |
| DR2 | **locale 在已初始化的卷上无法修正**；若首次 initdb 参数遗漏，大小写敏感可能被静默破坏（架构 Risk #1） | 编排显式固定 `POSTGRES_INITDB_ARGS` / `LANG` / `LC_ALL`；部署文档把「录数据前校验 locale、不符则重建卷」列为强制步骤；T-05 直连断言 |
| DR3 | **nginx SPA fallback 使 `/docs` 等返回 200（index.html）**，使 AC-05 观察歧义 | 后端 prod 关闭 + nginx 显式 `return 404`（双落实，G-06 + T-01 + T-06） |
| DR4 | 静态 guard 可被「运维手工改 compose / 手起 uvicorn」绕过 | 应用层仍按 `CSM_ENVIRONMENT` 关闭文档面；文档明确生产必须使用编排；guard 覆盖仓库内产物 |
| DR5 | 凭据在 DSN 与 `POSTGRES_*` 两处不一致导致应用连不上库 | PROPOSED：由编排用同一变量插值组装 DSN，避免手工重复；部署文档给出校验步骤（`/api/health` 已认证 200） |
| DR6 | 镜像构建依赖外网（pip / npm 源），离线 VM 无法构建 | 记录为 NQ-4 / 运维前置条件；文档说明「可在外网机器构建后转移 / 使用内网 registry」，不改变 CSM 产物 |
| DR7 | TCP 探针只证明监听，不证明数据库可用 | 就绪性由 `postgres` 的 `pg_isready` + `depends_on: service_healthy` 保证；端到端可用性由 T-06 的已完成登录链路断言 |
| DR8 | 升级时误用 `down -v` 丢历史 | 文档禁止 + G-04 断言 + 命名卷与 `restart` 策略减少重建需要 |
| DR9 | 前端生产构建在容器内失败（Node 版本 / 依赖） | 固定 `node:22-alpine` 满足 `package.json` engines；`npm ci` 使用已提交的 `package-lock.json`；T-06 构建阶段暴露 |
| DR10 | 生产环境 `updated_at` 等既有语义被误改 | REQUIRED：F015 不改任何后端行为（除文档面关闭）；Review 检查 diff 范围 |

---

## Constraints

1. 不得引入 HTTPS / TLS / 证书 / 域名 / 公网入口 / 外部网关（R-DEPLOY-003；§20）。
2. 不得引入 Kubernetes / 微服务 / 多机 / 高可用 / 负载均衡 / 多 worker 横向扩展（R-DEPLOY-001；ADR-0001；§23）。
3. 不得引入监控 / 告警 / 工单 / 消息队列 / Redis / Event Bus / CQRS / Elasticsearch（§23；ADR-0001 Constraints #1）。
4. 不得新增 `/api/*` 认证豁免，不得改动 `EXEMPT`；`/api/health` 保持受保护。
5. 不得把任何探测端点放入 `/api`（本 Feature 采用无 HTTP 探针；(b) 分支未采纳）。
6. 不得在生产产物中硬编码任何凭据 / DSN；缺失配置必须启动失败。
7. 不得发布 `postgres` / `app` 端口到宿主 / 内网；仅 nginx 入口可达。
8. 不得修改 `0001_f012_baseline` / `0002_f013_auth`，不得新增 Schema / migration；不得创建 database / 角色 / extension。
9. 不得在生产产物或文档中提供 `alembic downgrade` / `down -v` / `docker volume rm`。
10. 不得修改领域规则、唯一性、状态、删除语义、错误信封、产品 API 契约或任何 ADR。
11. 不得复活任何 dev-only 自检面（`_foundation` 或等价物）。
12. 不得破坏 `docker-compose.dev.yml` 与 `README.md` §3 的本地开发流程（仅允许修正过时措辞与指向）。
13. 不得反向要求引入 HTTPS / 域名 / 公网入口；「仅限受控内网 / 无 HTTPS / Cookie 无 `Secure`」是**已确认取舍**，必须原样记录。
14. DB / API 契约单一权威；代码与部署产物不得另立约定。
15. 不得把 `updated_at` 用作审计或并发控制依据（DB 设计决策 8）。

---

## Open Technical Questions

### Blocking

**无。**

产品输入 `READY FOR ARCHITECT` 且无 Blocking；12 个待决设计问题均已裁定；所需输入（ADR-0001 ~ 0005 `ACCEPTED`、F012 / F013 / F014 Handoff `READY FOR IMPLEMENTATION`、数据库设计 `READY`、产品 AC-01 ~ AC-12）齐备；本 Feature 不需要新的产品决策或架构决策。

### Non-blocking

1. **NQ-1 / PROPOSED-1 备份 / 恢复**：无已确认规则；F015 不实现、不承诺。若用户要求，应作为独立小范围工作。
2. **NQ-3 / PROPOSED-3 生产 API 文档面**：当前裁定「prod 关闭」；若组织需要，需用户显式裁定为「仅认证后可达」，届时同步 AC 与部署文档，**不得**新增 `/api/*` 豁免。
3. **NQ-4 镜像获取方式**：VM 上构建 vs 内网 registry / 离线导入；属实现 / 运维选择。
4. **PROPOSED-4 一键部署脚本**：不承诺；AC-12 只要求文档可复现。
5. **NQ-7 应用镜像回滚流程**：不在本 Feature（无规则；且可能与「向前迁移」冲突）。
6. **PROPOSED-2 重启策略**：`unless-stopped` 作为工程默认；具体取值非产品验收项。
7. **NQ-10 README §8 FAQ 增补**（端口占用 / locale 不符 / 卷权限 / 健康检查失败）：可选，非阻塞。
8. **`Makefile` 生产目标**：可选，非阻塞。

---

## Implementation Layers

```text
database:   false       # 无 Schema / 索引 / 约束 / migration 变更；实现侧仅测试 / 部署断言
backend:    true        # prod 关闭框架文档面（唯一行为变更）+ backend/Dockerfile + .dockerignore + 测试 / guard
frontend:   false       # 无 frontend/src/** 改动（同源相对 /api；生产构建属 deployment 层）
deployment: true        # 新增键（PROPOSED）：docker-compose.prod.yml / frontend/Dockerfile / deploy/nginx / deploy/env 模板 / 部署文档 / README 入口
```

- **database**：`NOT_REQUIRED`（无数据库设计分支；`implementation.database_design: NOT_REQUIRED`）。
- **backend**：`backend/app/main.py` 的文档面开关 + `backend/Dockerfile` + `.dockerignore` + 测试（T-01 ~ T-04）与部署 guard（G-01 ~ G-08，若 Tester 与 Backend 约定归属）。
- **frontend**：无。
- **deployment**：编排、镜像、nginx、环境模板、部署文档、README / `repository-structure.md` / `docker-compose.dev.yml` 措辞同步。

**说明（对 Product Handoff Q1 的回应）**：Product Handoff 预期 `frontend: true`（生产构建产物接线）。本裁定将其归入**新的 `deployment` 层**，并判定 `frontend: false`（无源码改动）。如协调器 / PM 出于簿记需要在计划中保留 `frontend: true`，必须在实现说明中明确「无代码变更、仅构建产物」，避免产生空实现分支。

---

## Implementation Order

```text
Architecture + API Contract（本 Handoff；Contract = NOT_REQUIRED）
  ├─ Backend（prod 文档面开关 + backend/Dockerfile + .dockerignore + 测试）
  └─ Deployment（docker-compose.prod.yml + frontend/Dockerfile + deploy/nginx + deploy/env 模板
                 + docs/deployment/… + README / repository-structure / dev compose 措辞）
        （两者由同一实现方或两名实现方并行；文件所有权互不重叠）
                 ↓ 两个必需分支完成
        Tester（L1 静态 guard + L2 等价环境 E2E；L3 标 NOT TESTED）
                 ↓
             Reviewer → Merge Gate
```

- 无 Database Design 分支（`database: false`），无需等待任何设计。
- 无 API Contract 分支（`NOT_REQUIRED`），Frontend 不参与。
- 文件所有权：Backend = `backend/**`、`tests/**`、`backend/Dockerfile`、`.dockerignore`；Deployment = `docker-compose.prod.yml`、`deploy/**`、`frontend/Dockerfile`、`README.md`、`docs/deployment/**`；共享 `docs/**`（architecture / project / product）由协调器统一落盘。
- 协调器需落盘：本 Handoff；同步 `project-plan.yaml > F015.layers`（新增 `deployment`）、`contract.status = NOT_REQUIRED`、`implementation.database_design = NOT_REQUIRED`；按需更新 `docs/project/repository-structure.md`。

---

## Verification Strategy

1. **prod 环境与信息面（AC-05）**：T-01（应用层 404）、T-02（dev 保留）、G-01（编排强制 `prod`）、G-06（nginx 显式 404）、T-06（经 nginx 的 E2E 404）。
2. **认证边界与探针（AC-06，含 F013 不回归）**：T-03（401 / 200 与 `EXEMPT` 不变）、G-07（探针不变量）、G-01（探测存在）。
3. **暴露面与凭据（AC-10）**：G-01（仅 nginx 发布）、G-02（无字面量凭据 / 必填变量语法）、T-06（缺配置时 `compose config` 失败；`ss -ltn` 仅 80）。
4. **持久化（AC-07）**：T-06（`stop`/`start`、`--force-recreate`、`down`+`up` 后数据仍在；命名卷存在）。
5. **迁移（AC-08）**：G-04（无 downgrade / 无 `down -v`）、T-06（`upgrade head` ×2 幂等）。
6. **locale / 版本（AC-09⑥，架构 Risk #1）**：T-05（直连 `pg_database` + 大小写敏感断言）、G-05（文档记录项存在）。
7. **连接池（AC-09⑦）**：G-08（显式设置且 < `max_connections`）、G-05（文档依据）。
8. **端到端可用（AC-04）**：T-06（登录 → 登记 / 查询 → 已认证 health）、T-07（未认证入口呈现登录页）。
9. **越界能力（AC-11 / AC-03）**：G-03（负向断言）、G-06（无 TLS / 域名）、T-06 端口检查。
10. **文档完整性（AC-09 / AC-12）**：G-05（10 项清单）；L2 逐条照抄执行作为可复现性代理证据。
11. **回归**：F012 数据库 / 迁移测试、F013 认证 guard、F014 软删 guard 全绿。
12. **工程门禁**：ruff 干净；既有后端 / 前端测试全绿；`docker compose -f docker-compose.prod.yml config` 在提供环境文件后通过。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：

1. Product Handoff 为 `READY FOR ARCHITECT`，**无 Blocking**；AC-01 ~ AC-12 明确可判定。
2. 所有输入为 `READY` / `ACCEPTED` / `CONFIRMED`（ADR-0001 ~ 0005；F012 / F013 / F014 Handoff；数据库设计；`api-conventions.md`）。
3. 12 个待决设计问题已逐条裁定（含被拒绝替代方案），且**未新增或修改任何产品规则、领域对象、唯一性 / 状态 / 删除语义、API 契约或 ADR**。
4. `database: false`（无 Schema 不确定性）；`frontend: false`（无源码改动）；`backend: true` 与 `deployment: true` 两个分支均有可直接开工的依据，且文件所有权互不重叠、可并行。
5. **API Contract Status = `NOT_REQUIRED`**：F015 不新增产品 API、不新增 `/api/*` 豁免、探针不引入 HTTP 路径。协调器按 `READY FOR IMPLEMENTATION` 放行（本 Feature 不需要 `API Contract = READY` 这一组合条件）。
6. **需用户确认的长期技术决策：无。** 部署打包方式（docker-compose）、HTTP、认证边界、迁移策略均已由既有 ADR / 产品裁定确定；探针取 (a) 属产品已授权的技术选择；`restart` 策略为工程默认。备份（PROPOSED-1）与生产文档面（PROPOSED-3）为产品侧非阻塞悬空项，**不阻塞**本次实现。