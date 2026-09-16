# CSM

面向 HPC / AI 运维场景的内部资源管理平台。目标是替代分散维护的 Excel，提供统一的资源登记、查询、维护、关联、状态查看与资源使用情况查看。

CSM **不以建设完整 CMDB 为目标**；具体产品范围与业务规则以 `docs/product/` 中已确认的文档为准。

> 当前里程碑：**F006 — VirtualMachine 登记与管理**（继承 F012 基座、F001 Cluster、F009 视角、F013 认证、F014 软删、F002 BareMetal）。
> 已交付 F012 基座、F001 Cluster 的 5 个产品端点、F009 Cluster 视角只读别名、F013 认证、
> F002 BareMetal 的 5 个产品端点，以及 F006 VirtualMachine 的 5 个产品端点：
> 登记（必选绑定宿主 BareMetal）、查询（含按宿主限定）、R-VM-006 可选字段维护、逻辑删除，
> 并落地 F014「宿主有活跃 VM → 拒删宿主」端到端与创建侧 `FOR SHARE` 并发协议。
> 技术栈与关键决策见 `docs/architecture/adr/`（ADR-0001 ~ ADR-0005，全部 `ACCEPTED`）。

---

## 1. 技术栈

| 层 | 选型 | 依据 |
| --- | --- | --- |
| 后端 | Python 3.12 + FastAPI + Pydantic + SQLAlchemy 2.x + Alembic | ADR-0001 |
| 数据库 | PostgreSQL（UTF-8，默认 collation，不写 `COLLATE`） | ADR-0002 |
| 前端 | Vue 3 + TypeScript + Vite + Element Plus | ADR-0001 |

不引入微服务 / 消息队列 / Redis / Elasticsearch 等任何额外基础设施（`requirements.md` §23）。

---

## 2. 环境要求

- **Python 3.12+**
- **Node.js `^20.19.0 || >=22.12.0`**（Vite 7 要求）与 npm —— 仅前端需要
- **PostgreSQL 16**（本地实例或 Docker）—— 见下选择一种
- 可选：**Docker / Docker Compose**（提供本地 PostgreSQL 的最简方式）

---

## 3. 快速开始（30 分钟内可启动）

以下步骤假设从**干净 checkout** 开始。目标：`GET /api/health` 返回 200，且前端 dev server 可访问集群列表页（调用 `GET /api/clusters`）。

### 3.1 准备数据库（二选一）

**方式 A（推荐）：Docker Compose 本地 PostgreSQL**

```bash
docker compose -f docker-compose.dev.yml up -d
```

- 该 compose **仅用于本地开发 / 测试**，是 **dev 专用**，不用于生产。
  生产内网部署使用 `docker-compose.prod.yml`，步骤见 `docs/deployment/csm-v1-internal-deployment.md`。
- 它以 `C.UTF-8` locale + UTF8 encoding 初始化数据库，固定了「大小写敏感」语义（ADR-0002）。

**方式 B：已有本地 PostgreSQL 16**

创建一个 UTF-8、大小写敏感 locale（如 `C.UTF-8` / `en_US.UTF-8`）的数据库与账号：

```bash
createdb -E UTF8 --locale=C.UTF-8 csm
# 并按需创建账号 / 授权；随后在 .env 中填写对应 DSN。
```

> ⚠️ **不要**使用大小写不敏感的 locale（如某些平台默认的 `en_US.UTF-8` 若被改成 `..._ci`）。
> 若 locale 不正确，「`cluster-a` 与 `Cluster-A` 是不同值」（§22）的回归测试会失败。

### 3.2 配置后端环境变量

```bash
cp .env.example .env
```

`.env` 默认指向方式 A 的数据库（`postgresql+psycopg://csm:csm@localhost:5432/csm`）。
`.env` 已被 `.gitignore` 忽略，**不得提交真实密码**。

可配置项（前缀 `CSM_`）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CSM_ENVIRONMENT` | `dev` | `dev` / `test` / `prod`（运行环境标签） |
| `CSM_DATABASE_URL` | `postgresql+psycopg://csm:csm@localhost:5432/csm` | SQLAlchemy URL（psycopg 3 驱动） |
| `CSM_DB_POOL_SIZE` | `5` | 连接池尺寸 |
| `CSM_DB_MAX_OVERFLOW` | `10` | 连接池溢出上限 |
| `CSM_DB_POOL_TIMEOUT` | `30` | 获取连接超时（秒） |
| `CSM_DB_POOL_RECYCLE` | `1800` | 连接回收（秒） |
| `CSM_DB_ECHO` | `false` | 是否打印 SQL |

### 3.3 安装后端依赖

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

（也可使用 `uv`：`uv venv .venv && uv pip install -r requirements-dev.txt`。）

### 3.4 应用数据库迁移

```bash
.venv/bin/alembic upgrade head
```

应创建 `clusters` 表、`ck_clusters_name_no_slash` 约束与 `ux_clusters_name_active`
partial unique index，F013 的 `users` / `sessions` 表，F002 的 `bare_metals` 表
（`fk_bare_metals_cluster` RESTRICT、`ck_bare_metals_status`、`ux_bare_metals_cluster_hostname_active`
partial unique index），以及 F006 的 `virtual_machines` 表（`fk_virtual_machines_bare_metal`
RESTRICT、`ux_virtual_machines_name_active` partial unique index）；见
`docs/database/f012-baseline-migration.md`、`docs/database/f002-bare-metal-migration.md`、
`docs/database/f006-virtual-machine-migration.md`、`docs/database/csm-v1-schema-design.md`）。

### 3.5 启动后端 API

```bash
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
```

验证：

```bash
# F013 后 /api/health 不再豁免认证 → 未认证返回 401
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health   # 401

# 先建立初始管理员（口令从 stdin 读取，见 §5.1），再登录并访问
curl -s -c /tmp/csm-cookie.txt -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<你的口令>"}'
curl -s -b /tmp/csm-cookie.txt http://127.0.0.1:8000/api/health
# {"status":"ok","database":"ok"}
```

### 3.6 启动前端 dev server

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173/`。dev server 会把 `/api` 反向代理到
`http://127.0.0.1:8000`（详见 `frontend/README.md`）。

### 3.7 运行测试与 lint

```bash
# 数据库测试需要 DSN（未设置时相关用例会明确 skip，不会伪造通过）
export CSM_TEST_DATABASE_URL="postgresql+psycopg://csm:csm@localhost:5432/csm"
.venv/bin/python -m pytest

.venv/bin/ruff check backend tests
.venv/bin/ruff format --check backend tests
```

也可使用 Makefile：`make install && make db-up && make migrate && make run`，
`make check` 运行 lint + 格式 + 测试。

### 3.8 生产内网部署（F015）

以上为**本地开发流程**。生产部署（独立内网虚拟机、Internal IP + HTTP、
nginx + 应用 + PostgreSQL 三容器、迁移与初始管理员、locale / 连接池 / 内网 HTTP
约束、升级步骤）使用仓库根目录的 `docker-compose.prod.yml`，完整权威步骤见：

> **[`docs/deployment/csm-v1-internal-deployment.md`](docs/deployment/csm-v1-internal-deployment.md)**

- `docker-compose.dev.yml` 仍是 **dev 专用**（仅本地 PostgreSQL）；生产编排与它相互独立。
- 生产凭据由部署环境**外部注入**（`deploy/env.prod.example` 仅含变量名与说明，值为空）。
- 生产环境关闭框架默认文档面（`/docs` / `/redoc` / `/openapi.json`）。

---

## 4. F012 交付范围与边界

**交付**（所有资源 Feature 复用的基座）：

1. FastAPI 应用工厂 + 分层结构 + 环境变量配置 + DB 连接池 + `GET /api/health`（含轻量 DB 探测）。
2. 模块边界基座：每类资源独立模块 + 独立表；仅允许 `id` / `created_at` / `updated_at` / `deleted_at` 的 mixin 复用；**不建立通用 Resource ORM 基类或通用资源路由**。
3. 统一请求校验 + 统一错误信封（`error.code` + `details[].field`，遵循 `docs/api/api-conventions.md`）。
4. 通用 SQLSTATE → HTTP 映射层（`23502` / `23514` → 400 `VALIDATION_ERROR`；`23505` / `23503` → 409 `CONFLICT`），资源无关、单一实现。
5. 分页约定（`page` 默认 1；`page_size` 默认 50、上限 200）与事务边界基座。
6. `deleted_at IS NULL` 过滤基座（数据访问层**原语**，不是领域服务）。
7. Alembic 框架 + revision `0001_f012_baseline`。

**明确不做**（属后续 Feature）：

- Cluster 的领域校验 / CRUD / `by-name` 别名 —— F001；
- 认证 / 会话 / `users` / `sessions` —— F013；
- 软删除领域服务 / 父删子拦 / 并发加锁 —— F014；
- `virtual_machines` / `containers` / `services` 表或任何关系列 —— F006 已交付 `virtual_machines`；`containers` / `services` 仍属后续 Feature；
- 生产部署打包（nginx + 生产 compose + locale 文档）—— F015。

AC-09：F012 交付物**不包含任何具体资源的字段定义、唯一性规则实现、状态流转或生命周期逻辑**；`clusters` 表仅作为基座验证载体。

---

## 5. 产品 API

| Method | Path | 认证 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | **豁免**（唯一） | 登录；成功 `200` + `Set-Cookie: csm_session` |
| `POST` | `/api/auth/logout` | 需要 | 登出（物理删除会话行）→ `204` + 清 Cookie；会话失效时 `401` |
| `GET` | `/api/auth/session` | 需要 | 返回当前身份 `{"id","username"}`；无有效会话 → `401` |
| `GET` | `/api/health` | 需要 | 存活 + 数据库连接可用性；成功返回 `{"status":"ok","database":"ok"}` |
| `POST` | `/api/clusters` | 需要 | 登记 Cluster（`{"name":"..."}`）；`201` |
| `GET` | `/api/clusters` | 需要 | 列出活跃 Cluster（分页 `page` / `page_size`）；空集合返回 `200` + `items: []` |
| `GET` | `/api/clusters/{cluster_id}` | 需要 | 按 id 读取；不存在 / 已逻辑删除 → `404 NOT_FOUND` |
| `GET` | `/api/clusters/by-name/{cluster_name}` | 需要 | 只读名称别名（大小写敏感）；未命中 → `404 NOT_FOUND` |
| `GET` | `/api/clusters/by-name/{cluster_name}/bare-metals` | 需要 | Cluster 视角只读名称别名（F009）；按名称寻址活跃 BareMetal（分页 `page` / `page_size`）；未命中 / 已删 Cluster → `404`；存在但无活跃成员 → `200` + `items: []` |
| `PATCH` | `/api/clusters/{cluster_id}` | 需要 | 更新名称（复用创建时的同一套领域校验） |
| `DELETE` | `/api/clusters/{cluster_id}` | 需要 | 逻辑删除（F014）→ `204` 无响应体；不存在 / 已删除 → `404`；存在活跃子资源 → `409` |
| `POST` | `/api/bare-metals` | 需要 | 登记 BareMetal（`cluster_id` + `hostname` 必填）；同 Cluster 活跃同名 → `409`；父不存在 / 已删 → `404`；`201` |
| `GET` | `/api/bare-metals` | 需要 | 列出活跃 BareMetal（分页 `page` / `page_size`，可选 `cluster_id`）；空集合 `200` + `items: []`；`cluster_id` 不存在 / 已删 → `404` |
| `GET` | `/api/bare-metals/{bare_metal_id}` | 需要 | 按 id 读取；不存在 / 已逻辑删除 → `404 NOT_FOUND` |
| `PATCH` | `/api/bare-metals/{bare_metal_id}` | 需要 | 更新 `status` + R-BM-007 七字段；`hostname` / `cluster_id` 不可变；非法 `status` → `400` |
| `DELETE` | `/api/bare-metals/{bare_metal_id}` | 需要 | 逻辑删除 → `204`；不存在 / 已删 → `404`；存在活跃子资源（如活跃 VM）→ `409`（委托统一软删服务） |
| `POST` | `/api/virtual-machines` | 需要 | 登记 VirtualMachine（`bare_metal_id` + `name` 必填）；全局活跃同名 → `409`；宿主不存在 / 已删 → `404`；`201` |
| `GET` | `/api/virtual-machines` | 需要 | 列出活跃 VirtualMachine（分页 `page` / `page_size`，可选 `bare_metal_id`）；空集合 `200` + `items: []`；`bare_metal_id` 不存在 / 已删 → `404` |
| `GET` | `/api/virtual-machines/{virtual_machine_id}` | 需要 | 按 id 读取；不存在 / 已逻辑删除 → `404 NOT_FOUND` |
| `PATCH` | `/api/virtual-machines/{virtual_machine_id}` | 需要 | 更新 R-VM-006 六字段（`cpu` / `memory` / `disk` / `os` / `hypervisor` / `owner`）；`name` / `bare_metal_id` 不可变；空 body → `400` |
| `DELETE` | `/api/virtual-machines/{virtual_machine_id}` | 需要 | 逻辑删除 → `204`；不存在 / 已删 → `404`（委托统一软删服务） |

- 契约正文见 `docs/api/f001-cluster.md`、`docs/api/f002-bare-metal.md`、`docs/api/f006-virtual-machine.md`、`docs/api/f009-cluster-resource-view.md`、`docs/api/f013-auth.md`、
  `docs/api/f014-soft-delete.md`；通用约定见 `docs/api/api-conventions.md`。
- **F006 后** `virtual-machines` 端点可用：VirtualMachine 必属恰好一个宿主 BareMetal（无 `cluster_id`、无 `status` 字段），`name` 在所有活跃 VM 范围内**全局唯一**（跨宿主、跨 Cluster，大小写敏感，软删释放），`GET /api/virtual-machines?bare_metal_id={id}` 为按宿主限定的 canonical 读取能力（供 F010 复用）。
- **F006 后** `DELETE /api/bare-metals/{bare_metal_id}` 在宿主有活跃 VirtualMachine 时返回 `409 CONFLICT`（`details[].code == "ACTIVE_CHILDREN_EXIST"`）；软删全部活跃 VM 后可删。
- **F009 后** `GET /api/clusters/by-name/{cluster_name}/bare-metals` 可用：按 Cluster 名称寻址其活跃 BareMetal，与 canonical `GET /api/bare-metals?cluster_id={id}` 逐字段一致；只读、复用同一软删过滤路径，不提供写 / 删除 / 恢复别名。
- **F014 后** `DELETE /api/clusters/{cluster_id}` 可用：逻辑删除（行仍物理存在）、已删不占唯一性可同名重建、不提供 `by-name` 删除别名、无恢复能力。删除经系统内唯一的软删领域服务 `app/deletion/service.py`（ADR-0004）。

### 5.1 认证边界与初始账号

- **F013 后行为变更**：除 `POST /api/auth/login` 外，**全部 `/api/*`**（含 `/api/health`、
  既有 `/api/clusters*`、未来新增端点、以及 `/api` 下不存在的路径）在未认证时一律返回
  `401 UNAUTHENTICATED`。豁免名单**唯一成员**是登录端点，新增端点**无需**白名单登记（fail-closed）。
- **初始管理员**（唯一的账号建立路径；**不存在**自助注册端点 / 页面）：

  ```bash
  # 口令从 stdin 读取，不进入 argv / shell history；命令幂等
  PYTHONPATH=backend .venv/bin/python -m app.auth.cli create-initial-admin --username admin
  ```

  口令长度**至少 8 位**（R-AUTH-004）；不足 8 位命令失败且不产生账号。重复执行仅提示
  「已存在，未修改」并退出 0。
- **会话**：绝对有效期 **8 小时**，**不滑动续期**；登出 / 过期直接物理删除会话行；
  登录成功时惰性清理过期会话（无后台 worker）。
- **Cookie**：`csm_session` + `HttpOnly` + `SameSite=Lax` + **不设 `Secure`** + `Path=/api`
  + host-only + `Max-Age=28800`。V1 为内网 HTTP，`Secure` 会让浏览器丢弃 Cookie。
- **账号停用**（无管理界面，运维直接操作数据库；即时生效）：

  ```sql
  UPDATE users SET active = FALSE, updated_at = now() WHERE username = '<name>';
  ```

- **约束**：无角色 / 权限 / RBAC；无 LDAP / AD / OAuth / SSO；无口令找回 / MFA / 审计 /
  频率限制；认证表无 `deleted_at`（不适用资源逻辑删除语义）。
- **仅限受控内网**：内网明文 HTTP + Cookie 无 `Secure` 是已确认取舍（R-DEPLOY-003），
  生产部署须记录于 F015 文档。

---

## 6. 目录结构

```text
backend/
├── app/
│   ├── api/            # 产品 HTTP 路由（health）+ 请求依赖（事务边界）
│   ├── auth/           # F013 认证：passwords / policy / tokens / repository / service / router / middleware / cli
│   ├── clusters/       # F001/F014 Cluster 模块：router / schemas / validation / service / repository / deletion
│   ├── cluster_views/  # F009 Cluster 视角只读名称别名：router / service（复用 F001 名称解析 + F002 成员读取）
│   ├── bare_metals/    # F002 BareMetal 模块：router / schemas / validation / service / repository / deletion
│   ├── virtual_machines/ # F006 VirtualMachine 模块：router / schemas / service / repository / deletion
│   ├── common/         # 横切关注点：错误信封、SQLSTATE 映射、分页
│   ├── db/             # Declarative Base、mixin、引擎/会话、deleted_at 过滤原语
│   ├── deletion/       # F014 统一软删领域服务（唯一写 deleted_at 的路径）+ 活跃子检查声明类型
│   ├── models/         # 每类资源一个独立模块、一张独立表（cluster / bare_metal / virtual_machine + users / sessions）
│   ├── schemas/        # Pydantic schema
│   ├── config.py       # 环境变量配置
│   └── main.py         # 应用工厂（挂载 AuthMiddleware）
└── migrations/         # Alembic（env.py + versions/0001_f012_baseline.py + 0002_f013_auth.py + 0003_f002_bare_metals.py + 0004_f006_virtual_machines.py）

tests/
├── database/           # 绕过应用层、直接对 PostgreSQL 的约束 / 迁移 / 认证表测试
├── test_auth_api.py
├── test_auth_cli.py
├── test_auth_guards.py
├── test_clusters_api.py
├── test_clusters_guards.py
├── test_cluster_views_api.py
├── test_cluster_views_guards.py
├── test_deletion_api.py
├── test_deletion_guards.py
├── test_error_envelope.py
├── test_health.py
├── test_lint.py
├── test_structure_guard.py
├── test_virtual_machines_api.py
├── test_virtual_machines_concurrency.py
└── test_virtual_machines_guards.py

frontend/               # Vue 3 + TS + Vite + Element Plus（见 frontend/README.md）
docs/                   # 产品 / 架构 / 数据库 / API 契约（权威来源）
alembic.ini
docker-compose.dev.yml  # 仅 dev 的 PostgreSQL（dev 专用；生产见 docker-compose.prod.yml）
docker-compose.prod.yml # 生产内网编排（nginx + 应用 + PostgreSQL）
deploy/                 # 生产 nginx 配置与 env 模板
Makefile
pyproject.toml
requirements*.txt
```

---

## 7. 数据一致性（不可回退的基座语义）

以下两点由**绕过应用层、直接对数据库操作**的测试固定（`tests/database/`）：

1. **大小写敏感**：`cluster-a` 与 `Cluster-A` 是不同值；`SELECT ('cluster-a' = 'Cluster-A')` 为 `false`（§22）。
2. **软删不占唯一性**：`ux_clusters_name_active` 的 predicate 为 `deleted_at IS NULL`，已软删行不占用唯一性（ADR-0004 / R-DELETE-006）；BareMetal `hostname` 同 Cluster 唯一与 VirtualMachine `name` 全局唯一同理（`ux_bare_metals_cluster_hostname_active` / `ux_virtual_machines_name_active`）。

部署文档（F015）必须记录数据库的 `datcollate` / `datctype` / `encoding` 与 PostgreSQL 大版本，并把上述断言作为「locale 未被静默改变」的持续回归。
`updated_at` 由应用层维护，**不得**作为审计或并发控制依据。

---

## 8. 常见问题

- **`GET /api/health` 返回 500 `INTERNAL_ERROR`**：数据库不可达或 DSN 配置错误。检查 `.env` 与数据库是否已启动（`docker compose -f docker-compose.dev.yml ps`）。
- **数据库测试被 skip**：未设置 `CSM_TEST_DATABASE_URL`。这是**明确 skip**，不会伪造通过。
  > 测试库必须**显式**指定：测试夹具不再回退到 `CSM_DATABASE_URL`，因为它会对目标库执行 `DROP SCHEMA ... CASCADE`（见 Review follow-up D-02）。
- **`alembic upgrade head` 报 DSN 错误**：Alembic 从 `CSM_DATABASE_URL` / `.env` 读取连接串，不在 `alembic.ini` 硬编码。
- **中文乱码 / 大小写不敏感**：数据库 locale / encoding 不正确，需以 UTF-8 + 大小写敏感 locale 重建（见 §3.1）。