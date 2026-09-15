# Architecture Handoff — F012 项目基础框架与运行环境

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-15
> Feature: F012（ENABLER，E07，P0，无 `depends_on`）
> Git: `feature/F012-project-foundation`，base `develop`
> 配套契约：`docs/api/f012-project-foundation.md`（`READY`）

---

## Feature

F012 — 项目基础框架与运行环境（ENABLER，E07，P0，无 `depends_on`）。

## Product Source

- `docs/product/handoffs/f012-project-foundation.md`（`READY FOR ARCHITECT`，主要输入）
- `docs/product/requirements.md`（CONFIRMED BASELINE；§4、§5、§17、§20、§21、§22、§23、§24、§25、§26）
- `docs/product/domain-model.yaml` / `docs/product/domain-model.md`
- `.pi/skills/resource-domain/SKILL.md`
- `docs/architecture/csm-v1-foundation-architecture.md`（`READY FOR IMPLEMENTATION`）
- `docs/architecture/adr/adr-0001` ~ `adr-0005`（全部 `ACCEPTED`）
- `docs/api/api-conventions.md`（`READY`）
- `docs/database/csm-v1-schema-design.md`、`docs/database/f012-baseline-migration.md`（`READY FOR DATABASE IMPLEMENTATION`）
- `docs/project/project-plan.yaml`（F012 条目）

## Architecture Summary

**当前系统状态（已核实）**：仓库仅有 `AGENTS.md`、`README.md`、`docs/`、`.pi/`、`.gitignore`。**不存在** `backend/`、`frontend/`、`tests/`、任何应用代码、任何数据库对象、任何 API 实现。这是 greenfield 的第一次落地。

F012 的目标是交付**所有资源 Feature 复用的基座**，并在投入资源建模前证明两处最难回退的语义成立。方案要点：

1. **产品 API 只有 `GET /api/health`**。F012 **不交付任何资源（Cluster 等）的产品 API** —— Cluster 的领域校验 / CRUD / `by-name` 属 F001（Product Handoff 明确划定），F012 不得预置。
2. **两处最难回退的验证留在 F012，且在数据库层完成**：大小写敏感 collation（`SELECT ('cluster-a' = 'Cluster-A') = false`）与「软删不占唯一性」（partial unique index predicate）由**绕过应用层、直接对数据库操作**的测试固定。这两项**不依赖任何产品 API**，因此不受本次裁定影响。
3. **全栈贯通通过「非产品自检面」证明**：一个 dev/test-only、默认关闭、生产不挂载、且不含任何 Cluster 领域规则的最小载体往返（`clusters` 仅作验证载体），用于证明 HTTP → 校验 → 数据访问 → DB → 响应契约链路，并让前端渲染 Loading / Empty / Error 三态。
4. **横切基座**：统一错误信封 + 通用 SQLSTATE→HTTP 映射机制；分页约定；`deleted_at IS NULL` 过滤基座；事务边界基座；Alembic 框架与 `0001_f012_baseline`。
5. **不引入任何新框架 / 中间件**；技术栈、数据库、标识、软删持久化、认证机制、API 规范全部沿用已批准决策，不重新论证。

## 核心问题 1 裁定：F012 的「端到端验证面」交付什么

### 裁定

采用 **选项 (d)：混合方案**，分三层：

| 层 | F012 交付 | 归属 |
|---|---|---|
| **产品 API** | **仅 `GET /api/health`** | F012（AC-02） |
| **全栈贯通验证（架构判据 5）** | 通过**测试/dev-only 非产品自检面**（`/_foundation/*`）+ 后端集成测试完成 `create → list → get → update → soft-delete` 往返；**该面不含任何 Cluster 领域规则** | F012（临时/非产品） |
| **前端三态（架构判据 6）** | 前端三态**基座**在 dev 下调用 `/_foundation/*` 渲染 Loading / Empty / Error；产品页面接线属 F001 | F012 基座 / F001 接线 |
| **Cluster 领域校验 / CRUD / `by-name`** | **不在 F012** | F001 |
| **产品软删除领域服务 / 父删子拦 / 唯一冲突的产品语义** | **不在 F012** | F014 |

### 为什么不是纯 (a)

(a) 会让 F012 交付一个 `clusters` 的**产品**创建/读取面，这与 Product Handoff「本次明确不包含 #2：Cluster 的领域校验、CRUD API、`by-name` 别名——属 F001」及 **AC-09**（F012 交付物不包含任何具体资源的字段定义）直接冲突。**产品文档优先级高于架构判据**（`AGENTS.md` §3），故 (a) 不能原样采用。

### 为什么不是纯 (c)

(c) 把判据 5 / 6 整体移交 F001，会使**架构判据 4（统一错误信封 400 + `details[].field`）失去触发点**（F012 只剩无参数的 `/api/health`），并使整条 HTTP→领域→数据访问链路直到 M2 才被首次贯通。这是真实的去风险缺口。(c) 单独使用**过度**。(c) 的**边界精神**（F012 无产品资源 API）被吸收进裁定。

### 为什么不是纯 (b)

(b) 只做测试内数据层往返，前端三态用非产品路径——这正是本裁定的核心机制；但 (b) 若**只**做数据层往返、不提供任何运行时可调用的非产品面，则判据 6「调用该 API 渲染三态」无法观察。本裁定包含一个运行时自检面来补齐。

### 该裁定为什么满足三条硬约束

1. **不与已批准 Product Handoff 冲突**：产品 API 面只有 `/api/health`；自检面被明确定义为**非产品、dev/test-only、生产不挂载**，且**不含 Cluster 领域规则**（无 `/` 校验、无唯一性预检、无 `by-name`、无状态、无父删子拦），因此不构成「Cluster CRUD API」。
2. **最难回退的验证不推迟**：collation 与 soft-delete/unique 交互由 `tests/database/` 的**直接 SQL 断言**在 F012 内完成（已确认该路径不依赖 API）。
3. **前后端契约明确**：产品契约 = `GET /api/health`；非产品自检面契约在 `docs/api/f012-project-foundation.md` 单列，标注「非产品、F001 落地后可移除」。

### 是否需要产品裁定

**不需要。** 本冲突是**架构范围**问题（如何在同一套已批准文档内同时满足判据与产品边界），不改变任何产品规则、唯一性、删除语义或状态定义。Product Handoff 已把该边界问题列为 Non-blocking（NQ-1）并交由 Architecture 划分。故**不输出 `RETURN TO PRODUCT`**。

## Domain Impact

**无。** 不新增、不修改任何领域对象、关系、状态或唯一性规则。F012 仅依赖已确认规则；`clusters` 表按已 READY 的数据库设计建立，作为基座验证载体。**不创建** `virtual_machines` / `containers` / `services` 表或任何关系列，**不固化** VM→BareMetal、Container→载体（UNCONFIRMED）。

## Data Layer Impact

数据层需要解决的问题（详细 Schema 已由 Database Agent 交付，不重复）：

1. **基线 migration 框架**：Alembic 目录结构、`env.py`（从应用配置读 DSN）、`NAMING_CONVENTION`、线性单 head。
2. **`0001_f012_baseline`**：`clusters`（`id` / `name` / `created_at` / `updated_at` / `deleted_at`）+ `ck_clusters_name_no_slash` + `ux_clusters_name_active`（partial unique index，`WHERE deleted_at IS NULL`）。基线一经合入冻结。
3. **不需要** extension、触发器、`COLLATE` 声明、CASCADE、数据迁移（空库）。
4. **可应用 / 可重复应用 / 可从空库重建**（`upgrade head` ×2；`downgrade base && upgrade head`）。
5. 后续 `0002`~`0005`（F013 / F002 / F004 / F005）各自建表，**不改基线**；F001 **不新建表**。
6. **生产环境禁止 downgrade**（会 `DROP` 并丢失资源历史）。

## Backend Work

Backend Agent 提供以下**能力**（不含资源业务规则、不含认证、不含软删除领域服务）：

1. **应用骨架与配置**：FastAPI 应用工厂、分层结构、环境变量配置、DB 连接池、`GET /api/health`。
2. **模块边界基座**：每类资源 = 独立模块 + 独立表；仅允许 `id` / `created_at` / `updated_at` / `deleted_at` 的 mixin 复用；**不建立通用 Resource ORM 基类或通用资源路由**；`common/` 只放横切关注点。
3. **统一请求校验 + 统一错误信封**：按 `api-conventions.md`，含 `error.code` 与 `details[].field`。
4. **通用冲突错误处理机制**：单一 `IntegrityError` → 信封翻译层，按 SQLSTATE 映射（见下），资源无关。
5. **分页约定**（`page` / `page_size`）与**事务边界基座**（unit-of-work）。
6. **`deleted_at IS NULL` 过滤基座**（数据访问层可复用原语，**非**领域服务）。
7. **Alembic 框架 + `0001_f012_baseline`**（数据库实现由 Backend 承担）。
8. **非产品自检面** `/_foundation/*`（dev/test-only，生产不挂载；不含 Cluster 领域规则）。

**明确不做**：任何 Cluster/资源 CRUD、`by-name`、`/` 的 API 层校验、唯一性产品预检、软删除端点、父删子拦、认证/会话、`users`/`sessions` 表、生产部署打包。

## Frontend Work

Frontend Agent 完成：

1. **前端骨架**：Vue 3 + TypeScript + Vite + Element Plus，API client 基座，统一错误渲染（按 `error.code` 分支，**不解析 `message`**）。
2. **列表三态基座**：Loading / Empty / Error 可复用组件或 composable；Error 态由后端 `error.code` + `error.details` 渲染。三态基座须可容纳未来的 Not Found / Forbidden（F012 不实现认证，Forbidden 暂不触发）。
3. **dev 验证**：在 dev 配置下调用 `/_foundation/clusters`（列表）与 `/_foundation/error`（确定性错误）渲染三态，仅用于验证基座；**产品页面接线（`/api/clusters`）属 F001**。
4. **不做**：登录页、资源管理页、业务校验、任何 Cluster 领域逻辑。

## API Contract

### Status

```text
READY
```

### Contract

产品契约只有 `GET /api/health`；另有一个**非产品、dev/test-only 的自检面** `/_foundation/*`，不属产品契约。完整正文见 `docs/api/f012-project-foundation.md`。

## Product Handoff 七问回应

### Q1 — F012 ↔ F013 / F014 / F015 边界（回应 NQ-1）

| 能力 | 提供者 | 复用者 | 边界细则 |
|---|---|---|---|
| 统一错误信封 | F012 | F013/F014/F001~F011 | F012 定义信封、序列化、全局 handler |
| **通用 SQLSTATE→HTTP 映射机制** | **F012** | F014/F001 | 资源无关，按 SQLSTATE；F012 AC-03「通用冲突错误处理基座」的自然落地 |
| 唯一冲突 / 父删子拦的**产品语义** | **F014** | — | 应用层预检、friendly `code`/`field`、父有活跃子→409、软删交互不被误判 |
| 事务边界基座 | F012 | F013/F014/F001~F011 | 单事务协议；F014 的加锁协议建立其上 |
| `deleted_at IS NULL` 过滤基座 | F012（**原语**） | F014 | F014 交付**统一软删除领域服务**（禁止各模块各写，ADR-0004）；F012 不交付领域服务 |
| 软删除领域服务、并发父子完整性 | F014 | — | F012 不实现 |
| 认证 / 会话 / 口令 / 中间件 | F013 | F015 | F012 不实现、不占位 |

**划分依据**：F012 提供**机制与原语**（深且稳定、资源无关），F014 提供**领域语义**（浅、随资源规则增长）。这样 F014 不需要在 F012 之外再造一套信封或过滤，且不改变任何产品行为。

### Q2 — 基线 migration 与 F001 衔接；`23514` / `23505` → `400` / `409`（回应 NQ-2）

**衔接**：
- `0001_f012_baseline` 由 F012 建立 `clusters` + `ck_clusters_name_no_slash` + `ux_clusters_name_active`，一经合入**冻结**。
- **F001 不新建表**；F001 交付 Cluster 的领域校验 / CRUD / `by-name`，直接使用基线的表与约束。若 F001 确需新增列 → **增量** revision（可空或带默认值），不改基线。
- F001 的 `by-name` 只读别名、大小写敏感匹配、已删不参与解析，均落在基线的 `ux_clusters_name_active` 语义上。

**SQLSTATE → HTTP 映射（契约语义，现在即固定）**：

| SQLSTATE | 含义 | HTTP | `error.code` | `details[].field` |
|---|---|---|---|---|
| `23502` | NOT NULL 违反 | 400 | `VALIDATION_ERROR` | 违规列（若可判定） |
| `23514` | CHECK 违反 | 400 | `VALIDATION_ERROR` | 违规列（至少 `name`） |
| `23505` | partial unique index 违反 | 409 | `CONFLICT` | 违规列（至少 `name`） |
| `23503` | FK 违反 | 409 | `CONFLICT` | 违规列 |

- **F012 拥有机制 + 上表的通用语义**（资源无关，直接由 `api-conventions.md` §6 推导；这是 F012 AC-03「通用数据校验与冲突错误处理基座」的最低要求）。
- **F014 / F001 拥有产品语义叠加**：应用层预检、`details[].message` 的具体文案、父有活跃子→409 的领域判定；**不得另立一套信封或映射**。
- 该划分是对 Product Handoff NQ-1 的边界细化，**不改变任何产品行为，也不修改任何 ADR**。

**R-CLUSTER-005 双保险分工（回应 NQ-2）**：
- **数据库层（权威）**：F012 基线的 `ck_clusters_name_no_slash`。即使 API 层预检缺失，含 `/` 的写入也会被数据库拒绝，经通用映射返回 `400 VALIDATION_ERROR`（**不会**是 500）。
- **产品 API 层（体验）**：F001 负责在写入路径先校验并返回 `400` + `details[].field = "name"`，使错误具备字段级、友好文案。
- **F012 不实现** API 层的 `/` 校验，避免与 F001 重复。

### Q3 — 结构上防止通用 `resources` 表 / EAV / STI / JSONB 万能模型

| 手段 | 层级 | 强制方式 |
|---|---|---|
| 每类资源 = 独立模块 + 独立表；`common/` 不含资源列 | 代码结构 | Review + 目录约定 |
| 只允许 `id` / `created_at` / `updated_at` / `deleted_at` 的 **mixin** 复用；**禁止**带 `type` 判别列的 ORM 基类 | ORM | 约束声明 |
| 禁止 `polymorphic_on` / `polymorphic_identity` / 多态 `__mapper_args__` | ORM | **元数据 guard 测试** |
| 禁止任何 JSON / JSONB 列类型 | Schema | **元数据 guard 测试** |
| 禁止 EAV 形态（通用 `attribute` / `value` 表 + 通用 owner FK） | Schema | **元数据 guard 测试** |
| 禁止名为 `resources` / `resource_*` 的通用表 | Schema | **元数据 guard 测试 + 迁移后表集合白名单断言** |

- guard 测试直接检查 `Base.metadata`（无 `resources` 表、无 JSON/JSONB 列、无多态 mapper、无 EAV 模式）以及 `alembic upgrade head` 后的实际表集合，使 §4 / §24 / §25 的**产品规则变成会失败的测试**，而非仅靠文档约定。
- **REQUIRED**：这是 AC-03 的验证方法，不是可选优化。

### Q4 — 可运行环境的验收口径（回应 NQ-3、NQ-4）

**F012 内（本地 / 开发）**：
- **AC-01 计时口径**：从 F012 分支的**干净 checkout** 开始，到「`GET /api/health` 返回 200 **且** 前端 dev server 可访问列表页」为止。**包含**依赖安装、数据库准备（本机 PostgreSQL 或 dev 容器）、migration、前端安装与 dev 启动。**不含**操作系统安装、公司代理 / 镜像配置、生产部署。
- 步骤必须写入仓库文档（README 或等价文档），未接触过仓库的开发者可仅依文档完成。
- **AC-02**：`GET /api/health` → 200，且响应表明数据库连接可用。

**F012 不自带**生产部署打包。允许一个**仅用于开发、只含 PostgreSQL** 的 provisioning 指引或 compose 片段（明确标注非生产、非 F015 交付物）；**生产**内网虚拟机 + docker-compose（nginx + 应用 + PostgreSQL）+ locale/encoding 文档属 **F015**。

### Q5 — collation 与 UTF-8 基座落地

- **DDL**：不写任何 `COLLATE`；`clusters.name` 为 `TEXT`；使用数据库默认 collation（ADR-0002 选项 1）。
- **Locale**：数据库以 **UTF8 encoding + 大小写敏感 locale**（如 `C.UTF-8` / `en_US.UTF-8`）初始化；dev provisioning 显式固定 `LANG` / `LC_ALL`，避免镜像默认漂移。
- **连接**：客户端编码 UTF8；不依赖应用层做大小写折叠，**禁止** `lower(name)` 索引。
- **测试位置**：`tests/database/`（或等价目录）使用**原始数据库连接（绕开应用 session）**直接执行：
  - `SELECT ('cluster-a' = 'Cluster-A')` 必须为 `false`；
  - `cluster-a` 与 `Cluster-A` 可共存；活跃同名第二行 → `23505`；
  - 软删后同名可重建（`deleted_at` 更新后 insert 成功）；
  - 中文 `高性能计算集群-A` 写入 / 读出 / 等值命中。
- **F015 落地**：部署文档记录 `datcollate` / `datctype` / `encoding`、PostgreSQL 大版本与连接池上限，并把上述大小写敏感断言作为「locale 未被静默改变」的持续回归（架构 Risk #1）。

### Q6 — F013 认证落地前 `/api/*` 的临时行为

- F012 **不挂载任何认证中间件**，不创建 `users` / `sessions` 表，不实现会话 / 口令 / 登录 / 登出。
- F012 期间：`/api/health` 与（被显式启用时的）`/_foundation/*` **均可未认证访问**。这是**显式、临时、已记录**的状态，**不是**隐式的「先不要认证」。
- F012 **不引入**占位用户、伪权限或请求上下文中的 `current_user` 桩，以免在 F013 落地时产生语义歧义。
- F013 落地后：认证中间件保护 `/api/*`，除登录端点外一律 `401 UNAUTHENTICATED`。
- **PROPOSED（非阻塞）**：`GET /api/health` 作为**运维端点**，建议由 F013 的公开白名单显式豁免，使其永久可被健康检查访问。该建议使 ADR-0005「所有 `/api/*`（登录端点除外）要求认证」增加一个白名单成员，需在 F013 实现时确认；备选方案是把健康检查同时挂到 `/api` 之外的路径。**不影响 F012 实现**。

### Q7 — UNCONFIRMED 关系不被固化

- F012 **不创建** `virtual_machines` / `containers` / `services` 表，**不创建**任何 host-binding / relationship 列或通用关系表。
- F012 的分层与校验基座**不引入**任何「父资源 / 承载者」的通用抽象或必填假设；不为其定义状态或枚举。
- 结构 guard 测试（Q3）同时保证不会有漏网的通用关系表。
- 文档化约束：VM→BareMetal、Container→载体在 F012 的任何产物中**不得**表现为必选或既成事实。

## Test Work

Testing Agent 应验证（**最小集合**，F012 范围）：

| # | 测试 | 层次 | 对应 AC / 判据 |
|---|---|---|---|
| T1 | Alembic `upgrade head` → 重复应用 no-op → `downgrade base && upgrade head` 成功 | 数据库 | AC-01；架构判据 2；DB Verification #13 |
| T2 | 迁移后表集合白名单断言（仅 `alembic_version` + 预期表）；`ux_clusters_name_active` / `ck_clusters_name_no_slash` 存在 | 数据库 | AC-03；架构判据 3；DB Verification #12 |
| T3 | **直接 SQL**：`cluster-a` 与 `Cluster-A` 可共存；`SELECT ('cluster-a'='Cluster-A') = false` | 数据库（绕应用） | AC-05；架构判据 3；DB Verification #1 |
| T4 | **直接 SQL**：活跃同名第二行 → `23505` | 数据库（绕应用） | AC-04 / AC-05；§21；DB Verification #1 |
| T5 | **直接 SQL**：软删后同名可重建；已删行不出现在活跃查询 | 数据库 | 架构判据 3；支撑 R-DELETE-006（F014，**非 F012 产品 AC**）；DB Verification #3 |
| T6 | **直接 SQL**：`name` 含 `/` → `23514` | 数据库 | R-CLUSTER-005 数据库层；架构判据 3；DB Verification #6 |
| T7 | 中文写入 / 读出 / 等值比较往返（数据库 + 应用） | 数据库 + 应用 | AC-07；架构 Verification #6；DB Verification #11 |
| T8 | 字段校验失败 → `400` + `VALIDATION_ERROR` + `details[].field` | API | AC-06；架构判据 4 |
| T9 | 非产品自检面 `create → list → get → update → soft-delete` 往返；删除后不出现在 list | API（非产品） | 架构判据 5 |
| T10 | 结构 guard：无通用 `resources` 表 / EAV / STI / 多态 mapper / JSONB 列 | 元数据 | AC-03；§4 / §24 / §25 |
| T11 | lint 可执行 + 至少一个真实断言数据库约束的测试 | 工程 | AC-08；架构判据 8 |
| T12 | 前端三态基座渲染 Loading / Empty / Error；Error 由 `error.code` 驱动 | 前端 | 架构判据 6；AC-06 |
| T13 | 生产配置不挂载 `/_foundation/*`（返回 404） | API | 约束（非产品面隔离） |
| T14 | `GET /api/health` → 200 | API | AC-02；架构判据 1 |

**明确不在 F012 测试范围**（属 F001 / F014）：Cluster 产品 CRUD、`by-name`、API 层 `/` 校验、唯一冲突的领域预检文案、父删子拦、不级联、并发父子完整性、`ip_address.cluster_id` 漂移、认证。

## Technical Decisions

### CONFIRMED

- 技术栈：Python + FastAPI + Pydantic + SQLAlchemy 2.x + Alembic；Vue 3 + TS + Vite + Element Plus；PostgreSQL（ADR-0001，已批准）。
- 数据库默认 collation、不写 `COLLATE`（ADR-0002）。
- `deleted_at TIMESTAMPTZ NULL` + partial unique index（ADR-0004）。
- BIGINT identity 代理主键 + 名称寻址只读别名（ADR-0003）。
- 本地账号 + 服务端会话 + HttpOnly Cookie + Argon2id（ADR-0005，F013 实现）。
- 禁止 EAV / 通用 `resources` 表 / STI / ORM 多态 / JSONB 万能模型（§4、§24）。
- 禁止微服务 / 消息队列 / Redis / Event Bus / CQRS / Kubernetes / Elasticsearch（§23）。
- `clusters` 表与 `ck_clusters_name_no_slash` / `ux_clusters_name_active` 由 F012 基线建立；F001 不新建表。
- 错误信封、状态码、Empty / Not Found 语义（`api-conventions.md`，`READY`）。

### REQUIRED

- F012 **不得**交付 Cluster（或其他资源）的产品 API、领域校验、`by-name`、状态或生命周期逻辑（Product Handoff + AC-09）。
- F012 **不得**实现认证、会话或 `users` / `sessions` 表（F013）。
- F012 **不得**实现软删除领域服务、父删子拦、并发加锁、唯一冲突的领域预检（F014）。
- 大小写敏感与「软删不占唯一性」必须由**绕过应用层、直接对数据库**的测试固定（§21、§22）。
- `clusters.name` 的 `/` 禁令必须由数据库 CHECK 保证（R-CLUSTER-005 数据库层）。
- 关键约束不得只依赖 UI / 应用层（§21）。
- 数据库与连接必须支持中文（UTF-8）。
- 不得在 Schema 中固化 VM→BareMetal、Container→载体（UNCONFIRMED）。
- DB / API 契约是单一权威来源；代码中不得另立约定（架构 Constraints #9）。
- 非产品自检面必须在生产配置下不可达。
- `updated_at` 由应用层维护，**不得**作为审计或并发控制依据（DB 设计决策 8）。

### PROPOSED

1. 采用**运行时可调用的、dev/test-only 的非产品自检面** `/_foundation/*` 作为架构判据 5 / 6 的落地机制（本裁定的具体实现形式；边界裁定本身为 REQUIRED）。
2. `GET /api/health` 作为运维端点，建议在 F013 落地后**豁免认证**（白名单成员）。
3. 分页 `page_size` 默认 50、上限 **200**（`api-conventions.md` §9 留待确定，此处给出基座默认，F001 可重申）。
4. 自检面路径使用 `/api` 之外的 `/_foundation` 前缀，避免与 `api-conventions` 的资源约定及 ADR-0005 的 `/api/*` 认证范围产生任何交互。

### OPEN

- 见 Open Technical Questions（均非阻塞）。

## Risks

1. **`/_foundation` 自检面被误当作产品契约长期保留**（中）：它触碰 `clusters` 载体表。缓解：显式标注非产品、生产不挂载、F001 落地后移除或降为测试夹具；T13 guard 测试。
2. **collation 依赖部署 locale**（中高，继承架构 Risk #1）：缓解同 Q5（固定 locale + 直接 SQL 回归断言 + F015 文档）。
3. **非产品自检面的 `simulate` / 删除动作被误解为 F014 软删除语义**（低）：缓解：命名与文档明确「fixture-only」，不实现父删子拦。
4. **F012 未贯通 HTTP 写路径会掩盖链路问题**（低）：已通过自检面 + 集成测试缓解；若采用者选择移除自检面，则该风险上升，需在 F001 首次贯通时重点验证。

## Constraints

1. 不得引入新框架 / 中间件（§23、架构 Constraints #1）。
2. 不得新增 / 修改任何领域对象、唯一性、状态或删除语义。
3. 不得预先实现 F001 / F013 / F014 / F015 的能力。
4. 不得固化 UNCONFIRMED 关系。
5. 不得在 Schema 中隐藏产品规则（唯一性必须显式、可查、可测）。
6. 不得使用违反大小写敏感的唯一性实现。
7. 不得让非产品自检面在生产可达；不得让它成为产品契约。
8. 不得修改 `0001_f012_baseline`（合入后冻结）。
9. 数据库 / API 契约单一权威，代码不另立约定。

## Open Technical Questions

### Blocking

无。

### Non-blocking

1. **`/api/health` 的认证豁免**（PROPOSED）：需在 F013 实现时确认白名单成员；备选是把健康检查另挂到 `/api` 外路径。不影响 F012。
2. **`/_foundation` 自检面的最终形态与移除时点**：由 F001 Architecture Handoff 决定移除 / 降为测试夹具。
3. **`page_size` 上限具体值**（PROPOSED 200）。
4. **dev 数据库 provisioning 是否提供 compose 片段**：F012 可选，不得演变为 F015 的生产 compose。
5. **前端组件库最终选型**（组织若有标准可替换 Element Plus）。

## Implementation Layers

```text
database: true
backend:  true
frontend: true
```

- **database**：Alembic 框架 + `0001_f012_baseline`（`clusters` + CHECK + partial unique index）；无数据迁移。数据库实现由 Backend 承担。
- **backend**：应用骨架、`/api/health`、统一校验与错误信封、通用 SQLSTATE 映射、分页、事务边界基座、`deleted_at IS NULL` 过滤基座、非产品自检面、lint + 数据库级测试。
- **frontend**：前端骨架、API client、三态基座、dev 下对自检面的三态渲染验证。

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f012-project-foundation.md）
  ├─ Frontend（骨架与三态基座，只需契约稳定）
  └─ Database Design（已 COMPLETE：docs/database/f012-baseline-migration.md）
        └─ Backend（含基线 migration 实现）
                 ↓ 必需分支完成
              Tester → Reviewer
```

Database Design 已 `READY FOR DATABASE IMPLEMENTATION` 且 `implementation.database_design: COMPLETE`；Backend 无需等待再次设计。Frontend 与 Database→Backend 可并行。

## Verification Strategy

1. **数据库层（绕应用，权威）**：T2 / T3 / T4 / T5 / T6 / T7 —— 大小写敏感、软删释放唯一性、`/` 禁令、约束存在性、中文往返。
2. **迁移机制**：T1 —— 可应用 / 可重复应用 / 可从空库重建。
3. **契约层**：T8 / T9 / T14 —— 错误信封、Empty / Not Found、往返。
4. **结构约束**：T10 —— 显式资源建模，无通用 / EAV / STI / JSONB。
5. **工程门禁**：T11 —— lint + 真实数据库断言。
6. **前端基座**：T12 —— 三态渲染。
7. **非产品面隔离**：T13 —— 生产不可达。