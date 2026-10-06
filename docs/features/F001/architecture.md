# F001 工程与部署底座 — ARCHITECTURE 阶段报告

- **Task**：F001 工程与部署底座（ENABLER，P0，M1）— Architect，Feature 设计模式
- **Status**：`READY FOR DESIGN`（2026-10-06；协调器核验后持久化）
- **Basis**：`docs/product/requirements-v3.md` revision 3（§17、§22、§25–§31、§35.3 D02）；`docs/features/F001/product.md`（READY FOR ARCHITECT）；`docs/project/project-plan.yaml` plan_revision 4 F001 条目（已批准）；首次规划全局评估结论（时间方向 timestamptz/UTC、ISO-8601、可配置展示时区，正式签核在 F003）。
- **结论属性**：本报告为 Architect 设计输入；最终设计签核在 CONTRACT 阶段记录。版本选型与扩展策略为 PROPOSED，交 DATABASE Gate 联合确认。

## 1. 方案摘要

### 1.1 仓库与目录结构（供后续 Feature 复用）

```
csm/
├── compose.yaml                     # docker compose up -d 入口
├── .env.example                     # 占位符，无真实凭据（入仓）
├── .env                             # 真实凭据（.gitignore 排除，不入仓）
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── alembic/
│   │   ├── env.py                   # 读取 Settings.DATABASE_URL；target_metadata=Base.metadata
│   │   └── versions/0001_baseline.py
│   ├── app/
│   │   ├── main.py                  # create_app()；include api_v1_router；健康检查
│   │   ├── api/v1/                  # api_v1_router = APIRouter(prefix="/api/v1")
│   │   │   ├── health.py            # 运维端点
│   │   │   └── router.py            # 聚合各域 router（后续 Feature 挂载）
│   │   ├── core/config.py           # pydantic-settings Settings
│   │   ├── core/db.py               # engine / SessionLocal / get_db
│   │   ├── models/base.py           # DeclarativeBase + 命名约定（无业务实体）
│   │   ├── schemas/                 # 占位
│   │   └── services/                # Service Layer 占位（F003 起承接）
│   └── tests/
│       ├── conftest.py              # 真实 PG fixture：建 schema/迁移/事务清理/多连接
│       ├── integration/             # test_migrations / test_health / test_db_concurrency
│       └── smoke/                   # SQLite 纯逻辑冒烟（不作约束证据）
├── frontend/
│   ├── Dockerfile                   # 多阶段：build dist → nginx:alpine 静态服务
│   ├── nginx.conf                   # SPA history fallback
│   └── src/api/client.ts            # fetch 封装，base=/api/v1；无业务页面
└── deploy/
    ├── nginx/nginx.conf             # 入口代理：/api/→backend；/→frontend
    └── backup/                      # pg_dump.sh / restore.sh / README.md（恢复文档+冒烟）
```

约定要点：
- 后端按 `api / core / models / schemas / services` 分层；**业务规则集中在 `services/`，路由不直连 ORM**（§24）。
- 前端 `src/api/` 统一客户端，base path `/api/v1`。
- 迁移单一 Alembic 版本链；后续 Feature 追加 revision，不修改已发布 revision。
- 部署文件集中 `deploy/`，凭据仅经 `.env` / `env_file` 注入。

### 1.2 服务组成与交互（§30）

`docker compose up -d` 启动五个服务：

| 服务 | 职责 | 对外 |
| --- | --- | --- |
| `db` | PostgreSQL 16.x，独立数据卷 | 仅内网 |
| `migrate` | 一次性 `alembic upgrade head`（复用 backend 镜像） | 无 |
| `backend` | FastAPI/uvicorn，`/api/v1/*` | 仅内网 8000 |
| `frontend` | 构建产物静态服务（SPA fallback） | 仅内网 80 |
| `nginx` | 入口代理，唯一对外端口 | 主机 80（可配置） |

依赖链：`db`(pg_isready) → `migrate`(service_completed_successfully) → `backend`(/api/v1/health) → `nginx`（同时依赖 frontend）。

请求路径：`/api/v1/*` → backend；其余 → frontend 静态 SPA。同源经 Nginx 统一入口，无需 CORS。

### 1.3 配置管理

- 分层：`.env`（不入仓）→ Compose `env_file` → 环境变量 → `pydantic-settings.Settings`。
- Settings 字段（示意）：`APP_ENV`、`DATABASE_URL`、`API_PORT`、`LOG_LEVEL`、`DISPLAY_TIMEZONE`（展示时区配置位，正式契约 F003/D01）。
- 凭据边界：仓库仅 `.env.example` 占位符；初始 ADMIN 与认证属 F002，本 Feature 不创建账号；日志/错误响应不输出连接串、密码、令牌。
- 扩展启用由 Alembic 基线迁移执行（版本化、可审计），非 initdb 脚本。

### 1.4 健康检查（运维端点，非业务 Contract）

| 方法 | 路径 | 语义 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | liveness，不触库 | `200 {"status":"ok","service":"csm-backend"}` |
| GET | `/api/v1/health/ready` | readiness，`SELECT 1` | 就绪 200 / 失败 503 `{"status":"not_ready","db":"down"}` |

两端点无需认证（F002 后仍公开）；数据库不可达返回 503，不伪造 200、不泄露连接串。

## 2. 技术决策

| ID | 决策 | 类别 | 依据 |
| --- | --- | --- | --- |
| DR-01 | 同步 SQLAlchemy 2.x + psycopg 3（`def` 路径，FastAPI 线程池），不用 async ORM | PROPOSED | §26 未要求 async；轻量控制台负载低，同步事务/锁语义直观（§12.1 IPAM）；改 async 属重大架构变更 |
| DR-02 | 迁移作为独立 `migrate` 一次性服务 | PROPOSED | 建库/Migration 显式可测，避免多副本竞态 |
| DR-03 | `/api/v1/` 前缀集中单一 `api_v1_router` 挂载 | PROPOSED | §25；后续域 router 只注册不改前缀 |
| DR-04 | pg_trgm 基线必启；btree_gist 建议不启用，推迟到首个排他约束 Feature（F008/F009） | PROPOSED（DATABASE Gate 签核） | 不预建无需求支撑；最小权限；避免未采用的扩展依赖 |
| DR-05 | frontend 容器 nginx:alpine 静态服务；入口代理独立 `nginx` 服务 | PROPOSED | §30 拓扑 |
| DR-06 | 时间基线：timestamptz 存储 UTC、ISO-8601 接口、DISPLAY_TIMEZONE 可配置 | PROPOSED（D01 正式签核 F003） | F001 仅预留配置位 |

### 2.1 软件版本选型（D02 基础部分，交 DATABASE Gate 联合确认；精确补丁版本由锁文件固定）

| 组件 | 建议版本 |
| --- | --- |
| Python | 3.12.x |
| FastAPI | 0.115.x |
| Pydantic / pydantic-settings | 2.9.x / 2.x |
| SQLAlchemy | 2.0.x |
| Alembic | 1.14.x |
| psycopg | 3.x（`psycopg[binary]`） |
| Uvicorn | 0.34.x（`[standard]`） |
| PostgreSQL | 16.x |
| pytest | 8.x（httpx 0.27.x） |
| Node.js | 22 LTS |
| React | 18.3.x（保守线；React 19 为前端实施次要待核对项，不阻塞） |
| TypeScript / Vite | 5.x / 5.x |
| Nginx | 1.27.x-alpine |

## 3. Implementation Layers

- `layers.database = true`（Alembic 基线、扩展启用、迁移环境）
- `layers.backend = true`（FastAPI 骨架、配置、DB 会话、健康检查、测试 fixture）
- `layers.frontend = true`（React/TS/Vite 脚手架与静态服务接线）
- `api_required = false`（无业务 API；健康检查为运维端点，见 §1.4）

## 4. Contract 引用与状态

- `api_required = false` → Contract 状态 `NOT_REQUIRED`（理由：无业务对象/业务 API，健康检查为运维端点在本文档定义，不建 `docs/api/F001.md`）。最终设计签核仍在 CONTRACT 阶段进行。
- 错误信封、409 冲突等通用错误语义由 F002 起在 Contract 明确，F001 不预建通用错误框架。

## 5. 数据库影响（详细交 DATABASE Gate）

- `0001_baseline.py`：`CREATE EXTENSION IF NOT EXISTS pg_trgm`（btree_gist 待裁定）；**不创建业务表**；downgrade 对称 drop 扩展（或按 DATABASE Gate 裁定记录非对称性）。
- 迁移环境：`env.py` 从 Settings 读 URL；`target_metadata = Base.metadata`；`compare_type`；离线/在线均支持。
- 连接管理方向：`pool_pre_ping=True`、池参数/statement_timeout/lock_timeout/隔离级别在 F008–F010 定稿，F001 提供可配置骨架与默认值；同步 psycopg3；不引入连接池中间件。
- 命名约定（`MetaData(naming_convention)`）：表 snake_case 复数、`pk_/fk_/uq_/ix_/ck_` 前缀。通用列（id/created_at/updated_at/deleted_at、稳定 ID 形态）由 F003/D01 裁定，F001 不预设。

## 6. 验证策略（实现/测试阶段执行）

| # | 验证项 | 方法 | 映射 |
| --- | --- | --- | --- |
| V1 | Compose 冒烟全链路 + Nginx 健康检查 + 前端可达 | 干净环境 Compose | 验收 1 |
| V2 | 迁移 up/down/up 一致性（真实 PG） | test_migrations.py | 验收 2 |
| V3 | 扩展显式启用断言 | 迁移后查 pg_extension | 验收 3 |
| V4 | pytest 集成 fixture 可重复、无残留 | 连续两次运行一致 | 验收 4 |
| V5 | 备份骨架 pg_dump + 按文档恢复（冒烟） | 脚本 + 文档 | 验收 5 |
| V6 | 凭据不入仓、不落日志 | 静态检查 + 冒烟 | 验收 6 |
| V7 | 多连接并发提交可见、最终持久化断言 | test_db_concurrency.py | T07/T35 前提 |

Fixture 要点：`TEST_DATABASE_URL` 指向真实 PG 独立测试库（不引入 Testcontainers）；会话级建库+upgrade head；函数级外层事务+savepoint 回滚；并发用例真实提交+teardown TRUNCATE（排除 alembic_version）、新连接断言最终状态；SQLite 仅 smoke。

## 7. 风险与待核对项

交 DATABASE Gate：①扩展清单与 btree_gist 裁定（首要）；②基线形态（空 schema+扩展）；③连接池/超时/隔离级别骨架参数；④测试库供给与 superuser 权限、恢复文档。
交 Tester：①真实 PG fixture 可执行性/可重复；②并发 fixture 支撑 T07/T35 最终持久化断言；③备份恢复冒烟判据。
其它：React 18 vs 19（次要）；时间契约正式签核 F003；稳定 ID/软删/审计基础设施属 F003。

**边界声明**：不实现认证/初始 ADMIN（F002）；不建业务对象；不执行 T01–T41；不宣称 Audit 备份覆盖（F016/T36）；容器可启动≠生产上线验收（§32）。

## 8. Issues / Next

1. 协调器已持久化本报告并设 `implementation.architecture = COMPLETE`。
2. DATABASE Gate：基线迁移形态、扩展清单（btree_gist 裁定）、迁移环境与连接池方向、备份脚本与恢复文档设计。
3. TEST_DESIGN Gate：V1–V7 可执行性、真实 PG fixture 与并发前提、备份恢复冒烟判据。
4. 二者完成后 Architect 定稿 `READY FOR IMPLEMENTATION`（contract=NOT_REQUIRED + 理由）。

## 最终设计定稿（CONTRACT Gate）

- 签核者：Architect；日期：2026-10-06
- 设计结论：`READY FOR IMPLEMENTATION`
- 核对的 Database Design：`docs/database/f001-baseline.md` v1（DB-D1–DB-D12）
- 核对的 Test Design：`docs/features/F001/test-report.md` TD-2（V1–V8+V3b / B1–B11）
- 上游依据：requirements-v3.md revision 3；project-plan.yaml plan_revision 4（F001 已批准）
- 覆盖范围：F001 D02 基础部分——软件版本、目录结构、迁移基线、扩展策略、测试基线、连接池/超时/隔离骨架、备份骨架与恢复文档、验证策略定稿。

### Contract

`api_required = false` → Contract = **NOT_REQUIRED**（无业务 API；健康检查为运维端点，见 §1.4）。

### 一致性核对（摘要）

- 扩展：架构 DR-04 ↔ DB-D2 一致（pg_trgm 必启，btree_gist 推迟 F008/F009）。
- downgrade：DB-D4 非对称 ↔ TD-2 V2/B1/B4 一致（不 drop 扩展，仅清 alembic_version，再 upgrade 幂等）。
- 健康检查：架构 §1.4 ↔ TD-2 V1/B7/B8 完全对齐。
- 版本选型：架构 §2.1 由本定稿升为 DESIGN 基线。
- 验证策略：架构 V1–V7 由 TD-2 扩展为 V1–V8+V3b，7 项验收 7/7 映射。
- 连接池与 IPAM：DB-D8/D9 骨架 + 事务级锁在 F008–F010 定稿，一致。
- 备份边界：三方一致，不宣称 Audit 覆盖（T36 归 F016）。

### 差异与采纳口径

- A1（MEDIUM，Tester/TEST 阶段）：TD-2 V3/B3 断言口径改为"基线声明扩展集合 = {pg_trgm}，pg_trgm 存在、btree_gist 不存在，忽略 plpgsql 等 PG 默认扩展"，避免误判 FAIL。
- A2（LOW，Database/Backend 实现核对）：命名约定 pk 模板按 `pk_%(table_name)s`。
- A3（NOTE）：备份/恢复脚本须支持容器内执行（宿主机无 pg_dump）。
- A4（NOTE）：备份判据以 DB-D12 5 项为设计口径、TD-2 V5 枚举为执行口径。
- A5（NOTE）：验证编号以 TD-2 为执行权威（V1–V8+V3b）。

### D02 基础部分签核（Architect + Database 联合）

软件版本、目录结构、迁移基线、扩展策略、测试基线：**签核完成**。D02 其余部分（认证、版本冲突/错误语义、审计一致性、约束/索引/锁/IPAM 并发）在 F002/F003/F008–F010 各自 Gate 关闭，本次不提前签核。

### 实现范围

- Backend：FastAPI 骨架/配置/DB 会话/健康检查/Alembic 基线/pytest fixture/备份脚本后端侧。
- Frontend：Vite 脚手架/api client(base=/api/v1)/nginx 静态服务接线。
- Database 实现：由 Backend 承担（无业务表）。

### 边界

不实现认证/初始 ADMIN（F002）；不建业务对象；不执行 T01–T41；不宣称 Audit 备份覆盖（F016/T36）；容器可启动≠生产上线验收（§32）。
