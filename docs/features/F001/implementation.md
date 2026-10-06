# F001 工程与部署底座 — 实现报告（Backend / Frontend）

实现提交：`85cbfdb`（feature/F001-engineering-foundation）。本文件由协调器持久化两份实现交接，作为 implementation 证据。

---

## Backend 实现报告（BACKEND COMPLETE）

### 实现范围

文件所有权范围内全部交付（`backend/**`、`deploy/**`、`compose.yaml`、`.env.example`、根 `.gitignore` 追加）；未触碰 `frontend/**`、`docs/**`、`.pi/**`。

| 项 | 交付物 |
| --- | --- |
| 工程依赖 | `backend/pyproject.toml`（fastapi 0.115.x / pydantic 2.9.x / pydantic-settings / sqlalchemy 2.0.x / alembic 1.14.x / psycopg[binary] 3.x / uvicorn[standard] 0.34.x；dev: pytest 8.x、httpx 0.27.x，有界约束可重复安装） |
| 迁移 | `backend/alembic.ini`、`backend/alembic/env.py`、`backend/alembic/versions/0001_baseline.py` |
| 应用骨架 | `app/main.py`、`api/v1/{__init__,router,health}.py`、`core/config.py`、`core/db.py`、`models/base.py`、`schemas/`、`services/` 占位 |
| 测试 | `tests/conftest.py`、`tests/integration/{test_migrations,test_health,test_db_concurrency}.py`、`tests/smoke/` |
| 容器/部署 | `backend/Dockerfile`（python:3.12-slim，runtime 非 root）、`deploy/nginx/nginx.conf`、`deploy/backup/{pg_dump.sh,restore.sh,README.md}`、`compose.yaml`、`.env.example`、`.gitignore` 追加 |

### 设计符合情况

- **DB-D1/D2/D3**：`0001_baseline.py` 手写、仅 `CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public`，无业务表；`btree_gist` 不启用（推迟 F008/F009）。
- **DB-D4**：`downgrade` 非对称 `pass`；测试验证 downgrade 后 `alembic_version` 为空而 `pg_trgm` 仍存在。
- **DB-D5**：`env.py` 从 `Settings.DATABASE_URL` 取 URL、`target_metadata=Base.metadata`、`compare_type=True`、`compare_server_default=False`、迁移引擎 `NullPool`、在线/离线双支持。
- **DB-D6 / 定稿 A2**：`NAMING_CONVENTION` 五键，`pk → "pk_%(table_name)s"`。
- **DB-D8/D9**：engine `pool_pre_ping/pool_size=5/max_overflow=10/recycle=1800/pool_timeout=30`，`connect_args.options` 注入 `statement_timeout=30000 lock_timeout=5000`，默认 READ COMMITTED；`get_db()` 不自动 commit。
- **DB-D10**：独立测试库 + 安全护栏（库名含 test 且 `TEST_DATABASE_URL != DATABASE_URL`）；会话级重建 public + upgrade head；函数级事务回滚；并发用例真实提交 + teardown TRUNCATE（排除 alembic_version）。
- **DB-D12 / 定稿 A3**：`pg_dump -Fc --no-owner --no-privileges`、原子 mv、失败非零；restore 默认全新库、`--clean --if-exists` 仅 `--force`；脚本支持容器内执行。
- **架构 §1.4**：`/api/v1/health` 不触库；`/api/v1/health/ready` 触库，失败 503 `{"status":"not_ready","db":"down"}`，不泄露连接串。
- **架构 §1.2/DR-03**：Compose 五服务 `db/migrate/backend/frontend/nginx`，入口代理分流，`/api/v1` 前缀集中于单一 `api_v1_router`。
- **§2.1 版本线**：实测解析 fastapi 0.115.14、pydantic 2.9.2、sqlalchemy 2.0.54、alembic 1.14.1、psycopg 3.2.13、uvicorn 0.34.3、pytest 8.4.2、httpx 0.27.2。

### 验证证据（实现阶段实际执行）

1. **构建 + 语法**：`docker build --target test -t csm-f001-backend-test ./backend` → BUILD_EXIT=0；`python -m compileall -q app alembic tests` → OK。
2. **冒烟**：`pytest tests/smoke -q` → 4 passed（仅纯逻辑，非约束证据）。
3. **真实 PG 集成**（非 superuser owner 库）：`pytest tests/integration -q` → **10 passed**（up/down/up 一致、扩展断言 pg_trgm 在/btree_gist 不在、幂等 upgrade、503 DB 不可达、并发提交可见与未提交不可见、V3b trusted 扩展非 superuser 安装）。
4. **V4 无残留**：连续两次运行 integration 均 exit 0；运行后 `pg_tables`（public）为空。
5. **V5 备份/恢复**：`pg_dump.sh` 产出 dump；`restore.sh` exit 0；5 项判据满足（SELECT 1 / pg_extension 含 pg_trgm / alembic_version 一致 0001_baseline / current=head 且幂等 / 恢复库 ready 200）。默认拒绝已存在目标库，`--force` 成功。
6. **V6 凭据边界**：`git check-ignore -v .env` 命中；`git ls-files` 无 `.env`；源码无硬编码口令（仅 `__SET_ME__` 占位）。
7. **Compose 校验**：`docker compose config -q` OK；`docker compose run --rm migrate` 成功执行 `alembic upgrade head`。

### 未验证项

- V1 完整 `docker compose up -d` 全链路（含 Nginx→frontend）未执行——frontend 并行交付中，交 TEST 阶段补验。
- V3b 在 Compose 默认 superuser 角色下不适用；已以显式非 superuser DB owner 库执行并通过。
- 并发用例为 T07/T35 前提能力验证，非业务并发正确性；Audit 备份覆盖（T36）不在 F001。

Git 声明（只读）：`git rev-parse --short HEAD`、`git branch --show-current`、`git status --short`、`git status --porcelain --ignored`、`git check-ignore -v .env`、`git ls-files`。

---

## Frontend 实现报告（FRONTEND COMPLETE）

### 实现范围（14 个文件，`frontend/`）

| 文件 | 内容 |
| --- | --- |
| `package.json` / `package-lock.json` | React 18.3.1、TypeScript 5.9.3、Vite 5.4.21、@vitejs/plugin-react 4.7.0（lockfile 固定，均在 §2.1 批准线上）；scripts：dev / build（`tsc --noEmit && vite build`）/ preview / typecheck |
| `vite.config.ts` | 仅 React 插件，无代理目标、无硬编码主机 |
| `tsconfig.json` | 严格模式（strict + noUnusedLocals/Parameters 等） |
| `index.html` / `src/main.tsx` / `src/App.tsx` / `src/index.css` | 极简首页：应用名 CSM + 后端健康状态（`GET /api/v1/health`），Loading/成功/失败三态显式区分，错误原样展示不伪装 |
| `src/api/client.ts` | fetch 封装；`API_BASE_PATH = "/api/v1"`（同源相对路径）；`ApiError`（非 2xx）；类型化 `getHealth()`，`Health = {status, service}` 按架构 §1.4 |
| `Dockerfile` | 多阶段：node:22-alpine（npm ci + build）→ nginx:1.27-alpine 静态产物 |
| `nginx.conf` | SPA history fallback；`/assets/` 长缓存（30d, public, immutable）；`index.html` no-cache；缺失 asset 404 |
| `.gitignore` / `.dockerignore` | node_modules、dist 忽略；构建上下文排除本地产物 |

### 设计符合情况

- **§1.1 目录结构**：与架构树一致，未新增架构外结构。
- **§1.2 / §25**：同源相对路径 `/api/v1`，无 CORS、无硬编码主机。
- **§1.4**：仅调用 liveness，响应类型化；非 2xx/网络错误/非法 JSON 均进入显式失败态。
- **定稿实现范围**：无业务页面、无路由框架、无状态管理库、无 UI 组件库。
- **V6 前端侧**：零密钥、零环境变量注入。

### 验证证据（实现阶段实际执行）

1. `npm install` → OK（esbuild 二进制经 optional dep 就位，`esbuild --version`=0.21.5）。
2. `npm run typecheck` → exit 0。
3. `npm run build` → exit 0；32 modules；产物 dist/index.html + hashed assets（含 tsc 检查）。
4. `npm run preview` + curl：`/` → 200 含 root div；`/some/deep/path` → 200 SPA fallback。
5. `docker build -t csm-frontend-f001 .` → 成功（npm ci 严格按 lockfile + tsc + vite build）。
6. `docker run` + curl：`/` → 200；`/clusters/123` → 200 fallback；`/assets/*.js` → immutable 缓存头；`/index.html` → no-cache；`/assets/nope.js` → 404。测试容器与镜像已清理。
7. `git check-ignore -v frontend/node_modules frontend/dist` → 均命中。

### 未验证项

- 浏览器内 React 运行时渲染与 `/api/v1/health` 真实集成（无浏览器、backend 未本地运行）——交 TEST 阶段 V1。
- Compose 全链路 V1（compose.yaml/deploy 由 Backend 并行负责）——交 TEST 阶段。
- `vite preview` 下 `/api/*` 回落是 preview 服务器行为，非生产路由；生产拓扑由 V1 判定。

Git 声明（只读）：`git branch --show-current`、`git status --short`、`git check-ignore -v frontend/node_modules frontend/dist`。
