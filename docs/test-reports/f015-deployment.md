# Test Report — F015 内网部署与运行环境

> Status: **READY FOR REVIEW**
> Author Role: tester
> Date: 2026-09-17
> Feature: F015（ENABLER，E07，P0，`depends_on: [F012, F013]`）
> 分支：`feature/F015-deployment`，base `develop` = `5c9ca84f94134c9bcc87c61a47fd9280ff99d411`
> 实现 HEAD = `056c0547b4001abbda4b3c88c22aff6f2cb2a712`（其后 `c82947f` 为计划元数据检查点）
> 分支状态：database `false`（NOT_REQUIRED）、backend COMPLETE、frontend NOT_REQUIRED、deployment COMPLETE、test PENDING、review PENDING

---

## Feature

内网部署与运行环境（F015）— CSM V1 的可运行生产部署产物：`docker-compose`（nginx + 应用 + PostgreSQL）、生产前端构建接线、`prod` 环境硬化（关闭 `/docs` / `/redoc` / `/openapi.json`）、传输层存活 / 就绪探测、凭据外部注入与命名卷持久化、部署文档与运行约束。

## Test Basis

- `AGENTS.md`（§3 领域权威、§4 文档、§6 数据库安全、§7 测试与 Review、§9 Git 纪律）
- `docs/product/handoffs/f015-deployment.md`（Product Handoff，`READY FOR ARCHITECT`，AC-01 ~ AC-12）
- `docs/architecture/f015-deployment-handoff.md`（Architecture Handoff，`READY FOR IMPLEMENTATION`，Test Work T-01 ~ T-08 / G-01 ~ G-08、REQUIRED、Constraints、证据层级 L1/L2/L3 与 NOT TESTED 规则）
- `docs/deployment/csm-v1-internal-deployment.md`（唯一权威部署文档）
- `docs/product/requirements.md` §20 / §21 / §22 / §23 / §25；`docs/product/domain-model.yaml`
- `docs/architecture/adr/adr-0001`（部署形态 / docker-compose）、`adr-0002`（PostgreSQL / locale / 版本化向前 migration）、`adr-0003`（错误信封）、`adr-0004`（软删）、`adr-0005`（HTTP 明文 / Cookie 无 `Secure` / `/api/*` 认证边界）
- `docs/project/v1/project-plan.yaml > F015`
- 报告格式先例：`docs/test-reports/f013-auth.md`、`docs/test-reports/f014-soft-delete.md`

## Environment

| 项 | 值 |
|---|---|
| 操作系统 / Python | Linux，Python 3.12.7（仓库 `.venv`） |
| PostgreSQL（单元 / 集成） | **16.2**（`.venv` 内 `pgserver` 启动的真实实例，Unix socket `/tmp/f015-test/pgdata`，本次新建；测试库 `csm_f015`） |
| PostgreSQL（L2 E2E 容器） | **16.15**（`postgres:16` 镜像，编排内命名卷 initdb，locale `C.UTF-8`） |
| Docker | Server 29.8.0；Docker Compose v5.5.1 |
| 镜像基础 | `python:3.12-slim`、`postgres:16`（本地已有）；`node:22-alpine`、`nginx:stable-alpine`（本次拉取） |
| L2 端口 | `CSM_HTTP_PORT=18080`（避免默认 80），凭据由 `/tmp/f015-test/csm.env` 外部注入 |
| ruff | 0.16.7 |

**是否全新**：`pgserver` 实例、测试库 `csm_f015`、L2 命名卷、管理员账号、L2 临时 env 均为本次测试新建；pytest 每次经 `DROP SCHEMA public CASCADE` + `alembic upgrade head` 从空库重建。实现方结论**未被复用**——下表所有结果均来自本次独立执行。

**L2 镜像构建说明（独立性披露）**：`docker compose ... build` 命中 Docker 层缓存（Dockerfile 与构建上下文自实现提交后未变，git 工作区本次全程干净），构建**未重新执行** `pip install` / `npm ci`。为消除缓存疑虑，另行**独立删除全部 `csm-prod-*` 镜像后重建**，并直接从运行镜像中断言产物内容与行为（见「独立执行摘要 6 / 7」）。真实 E2E 端到端栈已实际运行。

---

## 独立执行摘要（真实命令与关键输出）

### 1. 后端测试（独立重跑，无 skip 伪造）

```text
$ CSM_TEST_DATABASE_URL="postgresql+psycopg://postgres:@/csm_f015?host=/tmp/f015-test/pgdata" \
  .venv/bin/python -m pytest -q
192 passed, 2 warnings in 104.66s
（无 skipped；含 F012/F013/F014 全部既有测试 + F015 新增 37 项）

F015 专项子集：
$ .venv/bin/python -m pytest tests/test_f015_prod_surface.py \
    tests/test_f015_deployment_guards.py tests/database/test_f015_locale.py -v
37 passed, 2 warnings in 3.94s
（T-01 ~ T-05、G-01 ~ G-08 全部 PASSED，无 skipped）
```

### 2. lint / format（工程门禁）

```text
$ .venv/bin/ruff check backend tests          → All checks passed!  exit 0
$ .venv/bin/ruff format --check backend tests → 71 files already formatted  exit 0
```

### 3. 部署产物静态校验（`docker compose config`）

```text
A) 未提供环境文件        → exit 1（error while interpolating ... required variable
                            CSM_POSTGRES_USER/PASSWORD/DB is missing a value）
B) 直接拷贝空模板         → exit 1（同 A；空值同样 fail-closed）
C) 提供派生 env（有值）   → exit 0；渲染结果仅 nginx published "18080"→80；
                            app/postgres 无 published；命名卷 csm-prod_csm-prod-pgdata；
                            CSM_ENVIRONMENT=prod、CSM_DB_POOL_SIZE=5、CSM_DB_MAX_OVERFLOW=10
```

### 4. 静态 guard 真实可失败（对抗注入，逐字节还原）

对生产产物注入违规后 guard 必须失败，注入前备份、注入后 `sha256sum -c` 校验还原：

```text
注入 1  compose 凭据加默认值 ${CSM_POSTGRES_PASSWORD:-csm}
        → FAILED test_g02_no_literal_credentials_in_production_artifacts
          FAILED test_g02_no_default_value_for_credential_variables
注入 2  健康检查改为 curl http://127.0.0.1/api/health
        → FAILED test_g07_probes_do_not_use_http_or_api
注入 3  app 服务新增 ports: ["8000:8000"]
        → FAILED test_g01_compose_services_and_exposure
注入 4  nginx 首个 return 404 改为 return 200
        → FAILED test_g06_nginx_blocks_framework_docs_before_fallback
注入 5  部署文档追加 "docker compose down -v"
        → FAILED test_g04_no_destructive_commands
还原：docker-compose.prod.yml / deploy/nginx/default.conf /
      docs/deployment/csm-v1-internal-deployment.md  sha256sum -c 全部「成功」；
      git status --short 为空。
```

### 5. L1 静态 guard 全量（G-01 ~ G-08）— 37 passed

关键断言（均 PASSED）：编排仅 nginx 发布端口、`app.environment.CSM_ENVIRONMENT=prod`、命名卷挂载 `/var/lib/postgresql/data`、三服务 `restart: unless-stopped` 与 `depends_on: service_healthy`、三服务均有 healthcheck 且 `app`/`nginx` 为 TCP、`pg_isready`；生产产物无字面量凭据、凭据仅 `${VAR:?…}`；无 HTTPS/域名/K8s/Redis/ES 等越界能力；无 `alembic downgrade` / `down -v` / `docker volume rm`；部署文档含 AC-09 十项；nginx 无 TLS/域名且三文档路径显式 404；探针文本不含 `curl`/`wget`/`http://`/`/api` 且 `EXEMPT == {("POST","/api/auth/login")}`；`5+10=15 < 100`。

### 6. L2 等价环境 E2E（真实三容器栈，实际运行）

```text
$ docker compose -f docker-compose.prod.yml --env-file /tmp/f015-test/csm.env up -d --build
  三服务均 healthy：postgres (postgres:16) / app (csm-prod-app) / nginx (csm-prod-nginx)

迁移（内容与文档一致）：
  run --rm --no-deps app alembic upgrade head  #1 → 0001_f012_baseline → 0002_f013_auth
  run --rm --no-deps app alembic upgrade head  #2 → no-op（无 DDL）
  alembic current → 0002_f013_auth (head)

初始管理员：
  #1 → 「已创建初始管理员账号：admin（id=1）」
  #2 → 「账号 admin 已存在，未修改。」（幂等）
  短口令（3 位）→ exit 1、「口令长度至少 8 位」、不产生账号

经 nginx（http://127.0.0.1:18080）：
  GET /                 → 200 text/html（SPA index.html，非 401 JSON）
  GET /api/health       → 401 {"code":"UNAUTHENTICATED",...}
  GET /api/clusters     → 401 UNAUTHENTICATED（body 不含 items / 资源数据）
  GET /docs /redoc /openapi.json → 404 / 404 / 404
  POST /api/auth/login  → 200 {"id":1,"username":"admin"}（会话 Cookie 落 jar）
  GET /api/health       → 200 {"status":"ok","database":"ok"}
  POST /api/clusters {"name":"persist-check"} → 201 {"id":1,...}
  GET  /api/clusters    → 200 items=[persist-check] total=1

部署库直连断言（docker compose exec postgres psql，绕应用层）：
  datname=csm | datcollate=C.UTF-8 | datctype=C.UTF-8 | encoding=UTF8
  SELECT ('cluster-a' = 'Cluster-A') → f（大小写敏感）
  SHOW server_version → 16.15 ; SHOW max_connections → 100

持久化：
  stop / start                 后 GET /api/clusters → items=[persist-check]
  up -d --force-recreate       后 GET /api/clusters → items=[persist-check]
  down（不带 -v）+ up 后        GET /api/clusters → items=[persist-check]
  docker volume ls → csm-prod_csm-prod-pgdata（down 前后均存在）
  docker volume inspect → /var/lib/docker/volumes/csm-prod_csm-prod-pgdata/_data

暴露面：
  docker port postgres →（空） ; app →（空） ; nginx → 80/tcp -> 0.0.0.0:18080
  ss -ltnp | grep -E ':5432|:8000' → 无匹配（无 docker-proxy 发布）

探针（docker inspect，运行时实测）：
  postgres ["CMD-SHELL","pg_isready -U csmadmin -d csm"]
  app      ["CMD","python","-c","import socket; socket.create_connection(('127.0.0.1', 8000), 2).close()"]
  nginx    ["CMD-SHELL","nc -z 127.0.0.1 80"]
  （均为传输层；无 HTTP、无响应体、不触 /api）

负向 / 边界（经 nginx）：
  未认证 POST /api/clusters → 401，且 clusters 行数 1→1（无写副作用）
  错误口令登录 → 401 UNAUTHENTICATED（用户名或口令不正确）
  已认证 GET /api/clusters/999999 → 404 NOT_FOUND
  已认证 POST {"name":"a/b"} → 400 VALIDATION_ERROR
  已认证 POST {"name":"Persist-Check"} → 201（与 persist-check 大小写区分，证明 §22 在部署库成立）
  已认证重复 {"name":"persist-check"} → 409 CONFLICT
```

### 7. 镜像内容与 app 层纵深（独立删除镜像后重建）

```text
app 镜像（csm-prod-app）：
  /app = alembic.ini + backend(app/migrations) + requirements.txt；无 tests / docs / pytest
  运行用户 uid=10001(csm)（非 root）
  Config.Cmd = ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]（无 --reload）
  Config.Env 无任何 CSM_* / PASSWORD / DATABASE（凭据不烘焙进镜像）

nginx 镜像（csm-prod-nginx）：
  /usr/share/nginx/html = index.html + assets/（前端生产构建产物）
  /etc/nginx/conf.d/default.conf 含 3 处 return 404；无 ssl（grep -c ssl = 0）

app 层纵深（直接从镜像起容器，端口 18099，绕过 nginx）：
  CSM_ENVIRONMENT=prod → /docs /redoc /openapi.json 均 404；/api/health 未认证 401
  ⇒ 证明文档面关闭在应用层同样成立，非仅有 nginx 兜底

清理：docker compose down（不带 -v）→ image rm csm-prod-app / csm-prod-nginx
      → volume rm csm-prod_csm-prod-pgdata；pgserver 按 PID 精确 kill；
      rm -rf /tmp/f015-test；无残留容器 / 镜像 / 卷（未使用 pkill -f）。
```

---

## Acceptance Criteria Mapping

| AC | Test | Result | Evidence |
|---|---|---|---|
| **AC-01** 独立内网虚拟机三组件运行（R-DEPLOY-001） | T-06 | **PASS**（L2 等价） | nginx + app + PostgreSQL 三容器在同一机运行且均 `healthy`；部署仅依赖容器运行时 / 镜像源。/ **真实独立内网虚拟机形式 = NOT TESTED（L3，Agent 环境不可得）** |
| **AC-02** 内网另一台机器经 `http://<IP>/` 访问（R-DEPLOY-002） | T-08 | **NOT TESTED**（L3-only） | 机制等价证据：入口以 HTTP 监听 `0.0.0.0:18080`（发布端口）、`GET /` 返回 SPA、全程无域名 / 公网；但「内网另一台机器」在 Agent 环境不可得，不声称通过（见 Unverified Areas） |
| **AC-03** Internal IP + HTTP，不引入公网入口 / 域名 / HTTPS（R-DEPLOY-003） | G-01 / G-03 / G-06 + T-06 | **PASS** | 生产产物无 TLS / 证书 / `server_name` / 443 / 域名；唯一发布端口为 nginx `${CSM_HTTP_PORT:-80}:80`；nginx 配置无 `ssl`（grep 计数 0） |
| **AC-04** 端到端可用（登录页 / 登录 / Cluster 查询与登记 / 已认证 health） | T-06 / T-07 | **PASS** | `GET /` → 200 HTML SPA；`create-initial-admin` → 登录 200；`POST /api/clusters` 201 + `GET` 列表可见；已认证 `/api/health` → 200 `{"status":"ok","database":"ok"}` |
| **AC-05** prod 环境与 dev-only 面不可达 | T-01 / T-02 / T-04 / G-01 / G-06 + 容器实测 | **PASS** | 编排硬编码 `CSM_ENVIRONMENT=prod`；经 nginx 与 app 层（镜像实测）`/docs` `/redoc` `/openapi.json` 均 404；`/healthz` 亦 404；`dev` 下 `/openapi.json` 仍 200（能力未全局删除）；无 `_foundation` 或等价自检面 |
| **AC-06** 认证边界与探针不越界 | T-03 / G-07 + T-06 | **PASS** | 未认证 `/api/health` 与 `/api/clusters*` → 401 UNAUTHENTICATED 且 body 无资源数据；`EXEMPT == {("POST","/api/auth/login")}`；探针为 `pg_isready` / TCP socket / `nc`（无 HTTP、无响应体、不含资源 / 会话 / 凭据 / 数据库内容） |
| **AC-07** 数据持久化于命名卷 | T-06 | **PASS** | `stop`/`start`、`up --force-recreate`、`down`（不带 `-v`）+`up` 后 Cluster 均可查到；命名卷 `csm-prod_csm-prod-pgdata` 在 `down` 前后均存在 |
| **AC-08** 迁移可重复、生产无 downgrade | G-04 + T-06 | **PASS** | `alembic upgrade head` ×2 均成功且第二次 no-op（`current` 稳定 `0002_f013_auth (head)`）；生产产物与文档无 `alembic downgrade` / `down -v` / `docker volume rm`（guard 真实可失败） |
| **AC-09** 部署文档内容完整（10 项） | G-05 + T-05 + 部署库直连 | **PASS** | 文档 ①~⑩ 经 G-05 逐项命中；部署库直连 `datcollate`/`datctype`=`C.UTF-8`、`encoding=UTF8`、PG 大版本 16；`('cluster-a'='Cluster-A')=false`；连接池依据 `5+10=15<100` |
| **AC-10** 暴露面最小且无默认凭据 | G-01 / G-02 + T-06 | **PASS** | 仅 nginx 发布端口（`docker port` 中 app/postgres 为空，`ss -ltnp` 无 5432/8000）；生产产物无字面量凭据，凭据仅 `${VAR:?…}`；未提供 env → `compose config` exit 1（fail-closed），空模板同样失败；app 镜像 `Config.Env` 无任何凭据 |
| **AC-11** 无越界能力（§23 / R-DEPLOY-003） | G-03 / G-06 | **PASS** | 生产产物与文档无 HTTPS / 域名 / 公网入口 / K8s / 多机 / HA / 监控告警 / 工单 / MQ / Redis / ES 配置或指引（负向断言，真实可失败） |
| **AC-12** 文档可复现性 | G-05 + L2 逐条照抄 | **PASS**（L2 层面） | 文档 §2~§4 步骤在 L2 环境逐条照抄执行即达成 AC-01 / AC-04 观察项（含 §2.2 缺凭据失败、§2.3 起库、§3 迁移与管理员、§4 验证）。/ **真实 VM + 未接触仓库的运维形式 = NOT TESTED（L3）** |

**说明**：AC-01 ~ AC-12 每条均有结果，无 FAIL、无 BLOCKED。AC-02 与 AC-01 / AC-12 的真实内网 VM 形式为 **NOT TESTED（L3）**，系架构 Handoff 预先声明的 Agent 环境约束（DR1），已提供 L3 复核清单；L2 作为等价证据并已明确其「等价环境」性质，未冒充真实内网。

## Test Work（T-01 ~ T-08 / G-01 ~ G-08）覆盖

| # | 结果 | 独立证据摘要 |
|---|---|---|
| T-01 | PASS | `environment="prod"` → `/docs` `/redoc` `/openapi.json` 均 404；镜像内 app 层实测亦 404 |
| T-02 | PASS | `environment="dev"` → `/openapi.json` 200，`paths` 含 `/api/health` |
| T-03 | PASS | 未认证 health/clusters 401 + code=UNAUTHENTICATED；已认证 health 200 `{"status":"ok","database":"ok"}`；`EXEMPT` 不变 |
| T-04 | PASS | 无 `_foundation`；全部产品路由以 `/api` 开头；prod 下 `/healthz` 亦 404 |
| T-05 | PASS | 部署库直连：`C.UTF-8`/`C.UTF-8`/`UTF8`；`('cluster-a'='Cluster-A')=false`（另有 pytest T-05 全绿） |
| T-06 | PASS | 构建 → 迁移 ×2 → 管理员 → 经 nginx 登录 → 资源往返 → 401 → docs 404 → 仅 80 端口 → stop/start / force-recreate / down+up 持久化 |
| T-07 | PASS | `GET /` → 200 `text/html`（SPA `index.html`），非 401 JSON / 空白 |
| T-08 | **NOT TESTED** | 真实独立内网 VM + 另一台内网机器不可得；见 L3 复核清单 |
| G-01 | PASS | 仅 nginx 发布 / prod 标签 / 命名卷 / restart / depends_on / 三 healthcheck / locale |
| G-02 | PASS | 无字面量凭据 / 必填变量语法 / 无凭据默认值 / 模板值全空 / 两 Dockerfile 无凭据 |
| G-03 | PASS | 配置与文档无越界能力（负向） |
| G-04 | PASS | 无 `alembic downgrade` / `down -v` / `docker volume rm` |
| G-05 | PASS | 部署文档 AC-09 十项逐项存在 |
| G-06 | PASS | nginx 80 / SPA / `/api` 反代 / 三文档显式 404 且在 fallback 前 / 无 TLS·域名 |
| G-07 | PASS | 探针不含 `curl`/`wget`/`http://`/`/api`；后端镜像无 healthcheck；`EXEMPT` 不变 |
| G-08 | PASS | `CSM_DB_POOL_SIZE`/`CSM_DB_MAX_OVERFLOW` 显式且 `5+10<100`；文档含依据 |

**必测继承回归**：F012 迁移 / 约束测试、F013 认证边界与「唯一豁免」guard、F014 软删 guard 均**未回归**（全量 `192 passed`，无 skipped）。

## Database / Migration

`database: false` 得到独立确认：`git diff 5c9ca84..056c054 -- backend/migrations/` 为空，head 仍 `0002_f013_auth`。真实库上（pytest `csm_f015` 与 L2 编排库）`alembic upgrade head` 可应用、第二次 no-op、`current` 稳定在 head。L2 部署库 `pg_database` 直连：`C.UTF-8`/`C.UTF-8`/`UTF8`、PG 16.15、`max_connections=100`、大小写敏感成立（§22）。生产**无 downgrade 指引**（G-04）。

## Backend / API

F015 后端唯一行为变更为 `create_app` 在 `environment == "prod"` 时传 `docs_url/redoc_url/openapi_url=None`（`backend/app/main.py`，diff 仅此一处后端源码）。未认证 `/api/health` 与 `/api/clusters*` → 401 UNAUTHENTICATED 且无写副作用；已认证 `/api/health` → 200；Cluster 登记 / 查询 / 409 / 404 / 400 均符合既有契约；`EXEMPT` 保持 `{("POST","/api/auth/login")}`。`AuthMiddleware`、路由、错误信封、`/api/*` 语义未变。

## Frontend

F015 判定 `frontend: false`（无 `frontend/src/**` 改动）。生产前端由 `frontend/Dockerfile` 多阶段构建，`dist/` 由 nginx 静态服务；经 nginx `GET /` 返回真实 SPA HTML（含 `<title>CSM</title>` 与 module script），`/clusters` 路由经 SPA fallback 返回 HTML（200）。前端源码分支不适用。

## Integration

**真实前后端集成（L2 实际运行，非 Mock / Fixture）**：真实 `postgres:16` + 真实 `csm-prod-app`（uvicorn）+ 真实 `csm-prod-nginx` 三容器栈，经发布端口 `18080` 以真实 HTTP 完成：未认证 401 → 登录 → 已认证 health → Cluster 往返 → docs 404 → 端口暴露 → 持久化（stop/start、force-recreate、down+up）。应用层纵深另以独立容器（绕 nginx）验证 prod 下 docs 404。**集成结果 = PASS**。真实浏览器 DOM / 视觉与真实内网 VM 未覆盖（见 Unverified Areas）。

## Defects

**None.** 未发现 PRODUCT / ARCHITECTURE / DATABASE / BACKEND / FRONTEND / TEST_INFRA 缺陷（无 BLOCKER / HIGH / MEDIUM / LOW）。

**实施与 Architecture Handoff 的表述性差异（NOTE，非缺陷）**：Architecture Handoff Q2 文字写「nginx + 前端 用 `frontend/Dockerfile`（context = `./frontend`）」；实现将 `nginx` 服务 `build.context` 设为**仓库根**（`dockerfile: frontend/Dockerfile`）。因该 Dockerfile 需 `COPY deploy/nginx/default.conf`（位于 `frontend/` 之外），`./frontend` 上下文在技术上无法完成该 COPY，实现选择**内部自洽且正确**（compose 与 Dockerfile 一致，`.dockerignore` 已排除无关目录）。不影响任何 AC，无需回退；仅建议后续 Handoff 文字同步为「context = 仓库根」。

## Unverified Areas

1. **L3 真实独立内网虚拟机 + 另一台内网机器（AC-01 完整形式 / AC-02 / AC-12 完整形式，T-08）**：Agent 环境不可得，标 **NOT TESTED**。以 L2 等价环境 E2E 为等价证据（明示其为「等价环境」而非「真实内网」）。复核清单见下。
2. **真实浏览器级 DOM / 视觉 / 网络**：无浏览器自动化环境；SPA 呈现以返回的 HTML 与 SPA fallback 行为判定，未在真实浏览器观察登录页渲染。
3. **镜像从零构建（无 layer cache）的耗时 / 离线可构建性**：本次构建命中层缓存；基础镜像拉取依赖外网，离线 VM 的 pip / npm 源可达性属运维前置（Handoff NQ-4 / DR6），未验证。
4. **应用镜像层面的升级 / 回滚流程**：不在 F015 范围（NQ-7），未验证。

---

## L3 复核清单（供用户 / 运维在真实独立内网虚拟机执行）

> 目标：验证 AC-01 / AC-02 / AC-12 的完整形式。VM 上仅运行 CSM 组件，另需一台内网机器。

1. **前置**：干净内网 VM（仅 Docker Engine + Compose v2、固定 Internal IP、无 CSM 其他实例）；`git clone` 本仓库（或转移镜像）。
2. **仅依文档部署**（不阅读源码）：严格按 `docs/deployment/csm-v1-internal-deployment.md` §2.1 ~ §2.5 执行；确认每一步无需开发者口头补充即可完成（AC-12）。
3. **三组件本机运行**：`docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env ps` → nginx / app / postgres 均在该 VM 且 `healthy`（AC-01）。
4. **首次初始化**：§3.1 `alembic upgrade head`（记录输出）；§3.2 `create-initial-admin`（口令经 stdin，确认无回显、不进 history）。
5. **另一台内网机器**：在该机器浏览器打开 `http://<Internal IP>/` → 呈现登录页（非 401 JSON / 空白）；用 §3.2 凭据登录；完成一次 Cluster 列表查询与登记并在界面看到结果（AC-02 + AC-04）。
6. **认证与信息面**：未认证访问 `/api/health`、`/api/clusters*` → 401；`/docs` `/redoc` `/openapi.json` → 404；已认证 `/api/health` → 200 `{"status":"ok","database":"ok"}`。
7. **暴露面**：VM 上 `ss -ltn` 确认宿主仅监听 `${CSM_HTTP_PORT}`，无 5432 / 8000（AC-10）。
8. **locale 直连**：按 §6 执行 `datcollate`/`datctype`/`encoding` 与 `('cluster-a'='Cluster-A')=false` 断言（录入数据前）。
9. **持久化**：登记一条 Cluster → `stop`/`start`、`up -d --force-recreate`、`down`（**不带 `-v`**）+`up -d` 后数据仍在；`docker volume ls` 有命名卷（AC-07）。
10. **无公网依赖**：确认无 HTTPS / 域名 / 公网入口配置，访问全程仅内网 HTTP（AC-03 / AC-11）。

---

## Test Status

`READY FOR REVIEW`

依据：AC-01 ~ AC-12 每条均有结果，无 FAIL / BLOCKED，无 BLOCKER / HIGH / 须修复 MEDIUM 缺陷；L1 静态 guard 与 L2 等价环境真实集成 E2E 均已**实际执行**（非 Mock）；L3 真实内网 VM 按 Handoff 预先约定标 `NOT TESTED` 并提供复核清单；工程门禁（ruff / format / 全量 pytest）全绿。

---

## Test Handoff

### Status

`READY FOR REVIEW`

### Verified

- AC-03 / AC-04 / AC-05 / AC-06 / AC-07 / AC-08 / AC-09 / AC-10 / AC-11 = PASS；AC-01 / AC-12 = PASS（L2 等价 / L2 层面）。
- Architecture Test Work T-01 ~ T-07 与 G-01 ~ G-08 全部 PASS，无 skipped（T-08 = NOT TESTED，L3）。
- 静态 guard **真实可失败**：5 类对抗注入分别触发对应 guard FAILED，注入后逐字节还原（`sha256sum -c` 成功、`git status` 干净）。
- 凭据 **真正无默认**：未提供 env / 空模板 → `compose config` exit 1；派生 env → 通过，且仅 nginx 发布端口；app 镜像 `Config.Env` 无凭据。
- 探针 **真正不触 HTTP / `/api`**：`pg_isready` / TCP socket / `nc`；`EXEMPT` 未扩大，`/api/health` 保持受保护。
- F012 / F013 / F014 既有测试全量保持通过（`192 passed`，无 skipped）；无 migration 变更，基线未改。
- L2 真实三容器栈 E2E（登录 / 资源往返 / 401 / docs 404 / 端口暴露 / 持久化 / locale 直连）全部达成；app 层纵深（绕 nginx）亦 404。
- 环境已按 PID 精确清理，未使用 `pkill -f`；无残留容器 / 镜像 / 卷 / 临时文件。

### Not Verified

- L3 真实独立内网虚拟机 + 另一台内网机器（AC-02 及 AC-01 / AC-12 的完整形式）。
- 真实浏览器 DOM / 视觉 / 网络。
- 无 layer cache 的从零构建耗时 / 离线可构建性。
- 应用镜像层面的升级 / 回滚流程（不在 F015 范围）。

### Blocking Issues

None。

### Defect Owner

None（无缺陷）。

---

GIT: NONE