# Architecture Handoff — F001 Cluster 登记与管理

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Date: 2026-09-15
> Feature: F001（E01，P0，`depends_on: [F012]`）
> Git: `feature/F001-cluster`，base `develop` = `7a99745f`
> 配套契约：`docs/api/f001-cluster.md`（`READY`）

---

## Feature

Cluster 登记与管理（F001）。

## Product Source

- `docs/product/handoffs/f001-cluster.md`（`READY FOR ARCHITECT`，主要输入）
- `docs/product/requirements.md`（§7 R-CLUSTER-001~005、§15、§16 R-QUERY-004、§17 R-DELETE-001~006、§21、§22、§24、§25、§26）
- `docs/product/domain-model.md` / `domain-model.yaml`（`undefined_constraints`、`uniqueness_rules`、`lifecycle`）
- `.pi/skills/resource-domain/SKILL.md`
- `docs/architecture/csm-v1-foundation-architecture.md`（`READY FOR IMPLEMENTATION`）
- `docs/architecture/f012-project-foundation-handoff.md`（Q1/Q2/Q5/Q8 边界裁定）
- `docs/architecture/adr/adr-0001` ~ `adr-0005`（全部 `ACCEPTED`）
- `docs/api/api-conventions.md`（`READY`）、`docs/api/f012-project-foundation.md`（`READY`）
- `docs/database/csm-v1-schema-design.md`、`docs/database/f012-baseline-migration.md`（`clusters` 表与约束已冻结）
- `docs/reviews/f012-project-foundation.md`（F-03 MEDIUM：自检面 fail-open）
- `docs/project/v1/project-plan.yaml`（F001 条目）

## Architecture Summary

**当前系统状态（已核实，非空项目）**

| 项 | 现状 |
|---|---|
| Backend | **已存在** `backend/app/**`：应用工厂、`/api/health`、统一错误信封 + 全局 handler、通用 SQLSTATE→HTTP 映射、分页、请求级事务边界（`api/deps.py`）、活跃行过滤原语（`db/active.py`）、非产品自检面 `/_foundation/*`、Alembic 基线 `0001_f012_baseline` |
| Frontend | **已存在** `frontend/src/**`：Vue 3 + TS + Vite + Element Plus 骨架、`api/http.ts`（错误归一）、`components/ListStates.vue` / `ErrorState.vue`、`composables/useAsyncQuery.ts`、dev-only `pages/DevSelfCheckPage.vue` |
| Database | **已存在** `clusters` 表 + `ck_clusters_name_no_slash` + `ux_clusters_name_active`，由 `0001_f012_baseline` 建立并冻结 |
| API | 产品面仅 `GET /api/health`；`/_foundation/*` 为非产品自检面 |
| 相关领域对象 | `Cluster`（ORM 模型 `app/models/cluster.py`，仅作基座验证载体） |
| 相关架构决策 | ADR-0001 ~ 0005 全部 `ACCEPTED`；F012 交接已裁定机制/原语归 F012、领域语义归 F014 |

**方案要点**

1. **F001 不新增表、不新增列、不新增同类数据库约束、不新增 migration**。直接消费 F012 基线的 `clusters` 表、`ck_clusters_name_no_slash`、`ux_clusters_name_active`。
2. **产品 API 面 = 5 个端点**：`POST /api/clusters`、`GET /api/clusters`、`GET /api/clusters/{cluster_id}`、`GET /api/clusters/by-name/{cluster_name}`、`PATCH /api/clusters/{cluster_id}`。**不注册** `DELETE /api/clusters/{id}`。
3. **F001 不实现任何软删写入路径**：`DELETE` 端点整体推迟到 F014；读取路径直接复用 F012 的 `app/db/active.py` 原语（`active_filter` / `select_active`），该原语是 ADR-0004 §3「由数据访问层统一提供」的唯一承载点，因此**不产生第二条软删路径**。
4. **彻底移除 `/_foundation/*`**（非降级为夹具）：删除运行时挂载、`backend/app/foundation/` 整个模块、`Settings.foundation_enabled`、Vite dev proxy、`.env.example` / README 相关说明、dev-only 前端自检页与 `api/foundation.ts`。F012 架构判据 4 / 5 / 6 与 T8 / T9 / T12 / T13 的验证力**全部由产品端点 + 数据层直写接管**（见核心问题 2）。
5. **R-CLUSTER-005 双保险落地**：应用层唯一一份领域校验函数在**数据库 CHECK 之前**校验 `name` 是否含 `/`，返回 `400 VALIDATION_ERROR` + `details[].field = "name"`；数据库 `ck_clusters_name_no_slash` 仅作后盾（通用映射 `23514 → 400`，永不 500）。不改基线、不新增同类约束。
6. **「未定义约束不实现」落成可失败测试**（4 条 guard，见核心问题 8），而不是口头约定。
7. 不引入任何新框架 / 中间件 / 依赖；不实现认证、F014 领域语义、任何其他资源、任何为 R-CLUSTER-004 预留的结构。

## Domain Impact

**使用已有领域对象**：`Cluster`（R-CLUSTER-001/002/003/005）。**不新增、不修改任何领域对象、字段、关系、状态或唯一性规则。**

- R-CLUSTER-004（Cluster 可包含多个 BareMetal）在本 Feature 内**不产生任何结构**：不建 `bare_metals` 表、不加 `cluster_id` 列、不加裸金属计数字段、不加嵌套端点。其可验证方向归 F002（N:1 mandatory）与 F009（Cluster 视角）。
- R-DELETE-001 ~ 006 的**领域语义唯一归属 F014**。F001 只消费「已删不参与常规查询与名称解析」这一**读取侧后果**（R-DELETE-002 / 006）。
- Cluster **无状态**（R-CLUSTER-003）：不新增状态列、枚举、默认值或推导。
- 无 DataCenter / 位置 / Rack / U 位（§6、§13）。
- `name` 的长度 / 首尾空白 / 空字符串 / Unicode NFC 属 `undefined_constraints`：**不实现、不承诺、不由架构补齐**。

## Data Layer Impact

**数据层不需要任何问题的重新解决，也不需要任何变更。** `database: false`。

F001 依赖以下**已由 F012 基线保证**的事实（Backend 可直接假设，不必重新验证）：

- `clusters.name` 非空且一定不含 `/`；
- 「同一时刻至多一条 `deleted_at IS NULL` 的 `clusters.name`，且大小写敏感」（`ux_clusters_name_active`，partial unique，predicate = `deleted_at IS NULL`）；
- `deleted_at IS NULL` 是「活跃」的唯一判定条件；
- 数据库与连接为 UTF-8。

数据层需要新增的**唯一**内容是**测试断言**（不是 Schema）：

1. **CHECK 集合 guard**：`alembic upgrade head` 后 `clusters` 的 CHECK 约束集合必须**恰好**为 `{ck_clusters_name_no_slash}`（防「顺手补一个 `name <> ''` / 长度 / `trim` CHECK」）。
2. **AC-07 的预置数据**：测试用**原始数据库连接（绕过应用层）**写入一条 `deleted_at` 非空的行，再断言 API 行为。

**明确不做**：schema 变更、migration、索引、`COLLATE`、触发器、`version` / `created_by` / `audit_log` 列、`bare_metals` 相关任何对象。

> 若未来产品确认 PROPOSED-1（拒绝空串 / 空白 / 超长），属**新增产品规则**，须走需求确认 + **增量** revision（`0006+`，不改基线），归属该次变更，不属 F001。

## Backend Work

Backend Agent 需交付以下**能力**（不含实现细节）：

### 1. Cluster 模块（新）

`backend/app/clusters/`，与 `foundation/` 同构的分层（router → schema → service → repository），路由挂载到 `/api`：

| 文件 | 职责 |
|---|---|
| `router.py` | 5 个端点的 HTTP 编排；`by-name` 路由**声明在** `/{cluster_id}` 之前 |
| `schemas.py` | `ClusterCreate` / `ClusterUpdate`（仅 `name: str`，仅类型必填校验） / `ClusterRead`（`id`/`name`/`created_at`/`updated_at`，无 `deleted_at`） |
| `validation.py` | **唯一一份**领域校验入口（`/` 禁令 + 活跃唯一性预检）；供 POST / PATCH 复用，并作为 F011 Excel 导入复用的同一入口 |
| `service.py` | create / list / get_by_id / get_by_name / update；维护 `updated_at`（SQLAlchemy `onupdate` 已覆盖） |
| `repository.py` | 活跃查询，**必须**使用 `app/db/active.py` 的 `active_filter` / `select_active` |

### 2. 行为要求

1. **唯一性**：应用层先预检（返回友好 `409`），数据库 partial unique index 为最终权威（ADR-0004 §7）。预检被绕过时 `23505` 仍必须经 F012 通用映射返回 `409 CONFLICT` + `details[].field` 含 `name`（**必须有一条测试证明这条路径**）。
2. **`/` 禁令**：在 `validation.py` 中校验，抛 `app/common/errors.ValidationError`（`details=[{"field": "name", "code": "INVALID_CHARACTER", ...}]`）。**只实现一次**，POST / PATCH 共享，且位于任何数据库写入之前。
3. **404**：`GET /{id}`、`GET /by-name/{name}`、`PATCH /{id}` 对「不存在」与「已逻辑删除」**一律** `404 NOT_FOUND`（不区分，`api-conventions.md` §6）。
4. **Empty**：`GET /api/clusters` 无活跃行 → `200` + `items: []`，**不得** 404。
5. **无状态 / 无上级字段**：请求与响应 schema 中不得出现 `status` / `data_center` / `rack` / `u_position` 等字段。
6. **`name` 不做任何变换**：不 `strip`、不 `lower`、不做 NFC 归一化；写入即读出。

### 3. 移除 `/_foundation/*`（本次交付的一部分）

1. 删除 `backend/app/foundation/`（`router.py` / `repository.py` / `schemas.py`）。
2. `app/main.py`：移除 `foundation_router` 的 import 与条件挂载，仅保留 `health_api`。
3. `app/config.py`：移除 `foundation_enabled` 属性及其 docstring。
4. 删除 `tests/test_foundation_roundtrip.py`、`tests/test_foundation_isolation.py`（由新的产品端点测试与「自检面已彻底移除」guard 取代）。
5. `tests/test_error_envelope.py` 中依赖 `/_foundation/*` 的触发点改接产品端点（`POST /api/clusters`、`GET /api/clusters?page=0`）。
6. `.env.example`、`README.md`、`frontend/vite.config.ts`、`frontend/src/App.vue`、`frontend/src/api/foundation.ts` 中的 `/_foundation` 引用一并清理（前端文件由 Frontend 分支负责，见文件所有权）。
7. **同步文档**：`docs/api/f012-project-foundation.md` 顶部加「§4 已于 F001 移除」说明（保留 §4 正文作为历史记录，不删除）；`docs/architecture/f012-project-foundation-handoff.md` 的 Risk #1 / Non-blocking #2 标注 RESOLVED（owner F001）。这两处由协调器统一落盘。

### 4. 明确不做

Cluster 的 `DELETE`、软删领域服务、父删子拦、并发加锁、`ip_address.cluster_id` 治理、认证 / 会话 / `current_user` 桩、任何其他资源、为 R-CLUSTER-004 预留的任何结构、任何 `name` 未定义约束。

## Frontend Work

Frontend Agent 完成：

1. **`frontend/src/api/clusters.ts`**（新）：`listClusters(params)` / `getCluster(id)` / `getClusterByName(name)` / `createCluster(body)` / `updateCluster(id, body)`，类型 `ClusterRead`（`id:number`、`name:string`、`created_at:string`、`updated_at:string`）。复用 `api/http.ts`，**不新建**请求层。
2. **`frontend/src/pages/ClusterListPage.vue`**（新，产品页）：调用 `GET /api/clusters`，展示 `id` / `name` / `created_at` / `updated_at` 与分页（`page` / `page_size`）。
   - **Loading**：请求进行中（复用 `useAsyncQuery`）。
   - **Empty**：`200` 且 `items === []` → 空态（「暂无集群」）。
   - **Error**：请求失败 → 按 `error.code` 分支渲染（复用 `ErrorState.vue`），**不解析 `message`**。
   - 三态必须**互不相同**且可被测试断言（AC-14）。
3. **`frontend/src/pages/ClusterDetailPage.vue`**（新，骨架）：调用 `GET /api/clusters/{id}`（或 `by-name`），**仅呈现 Cluster 自身字段**。
   - **Not Found**：`404 NOT_FOUND` → 独立于 Empty 的「资源不存在或已被删除」态（R-QUERY-004）。
   - **不**呈现 BareMetal 列表 / 状态（F009）、**不**呈现跨资源视图（F010）、**不**呈现删除入口（NQ-2）。
4. **三态基座改接产品端点**：删除 `frontend/src/pages/DevSelfCheckPage.vue` 与 `frontend/src/api/foundation.ts`；`ListStates.vue` / `ErrorState.vue` / `useAsyncQuery.ts` **保留**为可复用基座，由产品 Cluster 页与其测试使用。F012 架构判据 6 的验证力因此由 `GET /api/clusters` 承载（不再需要 `/_foundation/error`：Error 态改由 `GET /api/clusters?page=0` 的确定性 `400` 或桩件驱动）。
5. **页面切换（PROPOSED）**：本次**不引入 `vue-router`**（避免为单资源页面引入新依赖，且受「不得引入新框架 / 中间件」约束）。`App.vue` 用极简视图状态在列表 / 详情间切换；前端路由方案作为 OPEN 非阻塞项，在 F009/F010 出现多资源导航前决策。详情页的 404 态由组件级 404 桩件测试覆盖。
6. **登记 / 改名 UI（PROPOSED，不构成 AC）**：`POST` / `PATCH` 的表单可一并交付（复用同一套 API 与错误渲染）；F001 的 AC 只覆盖 AC-14 的三态与 Empty/Not Found 区分。
   > **更正注记（2026-09-18，F016）**：本条与下方决策 §7 相互矛盾（此处「**可**一并交付」是可选，§7「随本次交付」却是确定交付），且两处都附加「不构成 AC」——结果该表单**既未被 AC 要求、也未被实现**，Review 无据可查，且从未被登记为遗留项；用户在已部署生产实例上实测「找不到登记集群的地方」才暴露该缺口。**已由 F016 补做**（`feature/F016-cluster-registration-ui`，见 `docs/product/handoffs/f016-cluster-registration-ui.md`）。教训：给一个交付物标注「不构成 AC」时，必须同时说明它是否仍属本次交付范围，否则它会在 Gate 中被静默丢弃。
7. **不做**：登录页（F013）、任何业务校验的重复实现（§21：前端不重复实现业务规则）、BareMetal 相关内容。

**文件所有权（并行安全）**：Frontend 拥有 `frontend/**`；Backend 拥有 `backend/**`、`tests/**`、`.env.example`、`README.md`。共享文档（`docs/**`）由协调器统一落盘。

## API Contract

### Status

```text
READY
```

### Contract

完整正文见 `docs/api/f001-cluster.md`。契约遵循并**不修改** `docs/api/api-conventions.md`；它是该通用规范在 Cluster 资源上的具体化。字段/状态码/Empty/Not Found 语义已固定，Frontend 与 Backend 可据此**并行**开发。

## Test Work

Testing Agent 应验证的最小集合（映射 AC-01 ~ AC-14 与 Q8 的 guard）：

| # | 测试 | 层次 | AC |
|---|---|---|---|
| A01 | `POST /api/clusters {"name":"cluster-a"}` → `201`，body 键集合**恰为** `{id,name,created_at,updated_at}`；DB 中新增 1 行活跃行 | API + DB | AC-01、AC-09 |
| A02 | `POST` `{}` 与 `{"name":123}` 与 `{"name":null}` → `400 VALIDATION_ERROR` 且 `details[].field == "name"`，且**无任何写入** | API | AC-02 |
| A03 | `POST {"name":"a/b"}` → `400 VALIDATION_ERROR`、`field=="name"`、无写入、**不得 500**；`PATCH` 同名同样 | API | AC-03、Q10 |
| A04 | 预检被绕过（monkeypatch 预检为空操作）后写重复活跃名 → `409 CONFLICT` + `field=="name"`；证明 **DB 仍是权威**（ADR-0004 §7） | API + DB | AC-04、Q6 |
| A05 | 常规重复活跃名 → `409 CONFLICT` + `field` 含 `name`，活跃行数仍为 1 | API + DB | AC-04 |
| A06 | `cluster-a` 与 `Cluster-A` 均可 `201`；`by-name/Cluster-A` 只命中后者；列表含两条 | API | AC-05、AC-11 |
| A07 | `by-name` 命中时返回与 `GET /api/clusters/{id}` **同一资源**（`id` 与全字段一致）；`by-name` 不存在 → `404 NOT_FOUND` | API | AC-06 |
| A08 | **绕应用层**预置 `deleted_at` 非空行后：不出现在 `GET /api/clusters.items`；`GET /{id}` → `404`；`by-name` → `404`；且该名称可被重新 `201`（R-DELETE-006） | API + DB | **AC-07** |
| A09 | 空库 `GET /api/clusters` → `200` + `items==[]` + `total==0` + `page==1` + `page_size==50`，**不得 404**；写入 3 行后 `page_size=2` 分页正确；`page=0` / `page_size=0` / `page_size=201` / `page=x` → `400` + `field` 为 `page`/`page_size` | API | AC-08 |
| A10 | `clusters` 表无状态列（`Base.metadata` 与 `information_schema` 双断言）；所有请求 / 响应体无 `status` 键 | DB 元数据 + API | AC-09 |
| A11 | `clusters` 表无 DataCenter / 位置 / Rack / U 位列；请求与响应 schema 无对应字段 | DB 元数据 + API | AC-10 |
| A12 | 中文名 `高性能计算集群-A`：`201` → 列表按字面值读出 → `by-name` 精确命中 | API | AC-11 |
| A13 | `PATCH` 改名为新值 → `200` 且返回新值；旧名可再 `201`；改到活跃重复名 → `409`；改成含 `/` → `400`；改到不存在 / 已软删 id → `404`；**改成自身当前名 → `200`（不得误报 409）** | API | AC-12 |
| A14 | 自检面已彻底移除：**dev 与 prod** 两个 app 实例对全部 `/_foundation/*` 路径均 `404`；`backend/app/**` 中不存在 `_foundation` 字符串、`app/foundation/` 目录不存在、`Settings` 无 `foundation_enabled` | API + 静态 guard | AC-13 |
| A15 | `DELETE /api/clusters/{id}` **不执行软删**（返回 `405`/`404`），返回后该行仍为活跃；`backend/app/**` 中不存在任何 `deleted_at` 赋值语句（当前应为 0 处，F014 落地后由 F014 更新该 guard） | API + 静态 guard | AC-13、ADR-0004 |
| A16 | 前端 `ClusterListPage` 三态互不相同（Loading / Empty / Error）；`ClusterDetailPage` 的 `404` 态与列表 Empty 态**渲染不同文本与不同状态**；Error 由 `error.code` 驱动 | 前端组件 | AC-14 |
| G1 | **schema guard**：`ClusterCreate` / `ClusterUpdate` 的 `name` 字段**无** `min_length` / `max_length` / `pattern`（`/` 校验在领域层，不在 schema）/ `strip_whitespace` / NFC 归一化 validator。新增任一即失败 | 单元（内省 Pydantic 字段） | Q8、NQ-1 |
| G2 | **DB guard**：`alembic upgrade head` 后 `clusters` 的 CHECK 集合恰好为 `{ck_clusters_name_no_slash}`（不得新增 `<> ''` / 长度 / `trim` CHECK） | DB | Q8、NQ-1 |
| G3 | **无静默归一化（canary）**：`name = " cn-a "`、`name = "\u00e9"` 与 `"e\u0301"` 经 `POST` 后，`GET` / `by-name` 返回的值与输入**逐字节相同**。docstring 必须声明：本用例断言「实现不做变换」，**不**断言这些名称在业务上合法；PROPOSED-1 被确认时必须由产品决策同步修改本用例 | API | Q8、NQ-1 |
| T8′ | **F012 判据 4 维持**：错误信封 `400` + `details[].field` 由产品端点驱动（`POST /api/clusters {}`、`GET /api/clusters?page=0`） | API | F012 判据 4 |
| T9′ | **F012 判据 5 维持**：`create → list → get → update` 由产品端点完成；`soft delete` 一段由 A08 的「绕应用层预置 `deleted_at` → API 读取被排除」承接 | API + DB | F012 判据 5 |
| T13′ | **F012 T13 调整**：从「生产 404」升级为「**任何配置下均不存在**」（并入 A14） | API + 静态 guard | F012 T13 |

**F012 既有测试的处置**：`tests/database/*`（T1~T7）**全部保留不变**（绕应用层的数据库权威断言，与 API 无关）；`test_structure_guard.py`、`test_health.py`、`test_lint.py` 保留，`test_structure_guard.py` 的 `test_only_expected_tables_registered` 断言 `{"clusters"}` 仍成立；`test_foundation_roundtrip.py` / `test_foundation_isolation.py` 删除并由 A08 / A14 / T8′ / T9′ 取代。

**明确不在 F001 测试范围**：删除 Cluster 的产品语义、父删子拦、不级联、并发父子完整性、`ip_address.cluster_id` 漂移、认证、BareMetal 及一切 F002+ 内容。

## Technical Decisions

### CONFIRMED

- 技术栈、PostgreSQL、BIGINT identity 主键、`deleted_at` + partial unique index、错误信封 / 状态码 / Empty & Not Found 语义、`by-name` 只读别名（ADR-0001 ~ 0005，全部 `ACCEPTED`）。
- `clusters` 表 + `ck_clusters_name_no_slash` + `ux_clusters_name_active` 由 F012 基线建立并冻结；**F001 不新建表、不改基线**。
- `/_foundation/*` 的 `Removal owner: F001`（`docs/api/f012-project-foundation.md` §4）。
- R-CLUSTER-005 保留并强制（ADR-0003「与 R-CLUSTER-005 的关系」）。
- `name` 的长度 / 空白 / 空串 / NFC 为 `undefined_constraints`，**不得自行假设**。

### REQUIRED

1. **F001 不得注册 `DELETE /api/clusters/{id}`**，且**不得存在任何写入 `deleted_at` 的产品代码路径**（ADR-0004 §1/§3；AC-13）。F001 结束时该路径数**恰好为 0**。
2. 读取路径的软删过滤**必须**通过 `app/db/active.py` 的 `active_filter` / `select_active` 实现，**不得**在 Cluster 模块内重写 `deleted_at.is_(None)` 的第二份谓词（ADR-0004 §3）。
3. `/` 禁令在**应用层先于数据库**执行，唯一实现于 `app/clusters/validation.py`，`POST` 与 `PATCH` 共享；不得依赖数据库 CHECK 产生友好错误，也不得在 schema 层重复实现。
4. 唯一性冲突必须以 `409 CONFLICT` 呈现，且**数据库 partial unique index 为最终权威**；必须有一条测试证明预检被绕过时数据库仍拦截。
5. `/_foundation/*` 必须**彻底移除**（含模块、挂载、配置开关、dev proxy、文档引用）；移除后**任何配置**下不可达。
6. 「未定义约束不实现」必须由可失败的测试保证（G1 / G2 / G3）。
7. 所有 `/api/clusters*` 端点必须位于 `/api` 前缀下，使 F013 的 `/api/*` 认证中间件**无需额外白名单**即可覆盖。
8. `updated_at` 由应用层维护，**不得**作为审计或并发控制依据。
9. DB / API 契约单一权威；代码中不得另立约定。

### PROPOSED

1. 采用「**彻底删除**」而非「降级为测试夹具」处理 `/_foundation/*`（理由见核心问题 2）。
2. `by-name` 路由声明顺序先于 `/{cluster_id}`（防御性；`int` 路径参数本身已消除歧义）。
3. 请求体的未知字段**被忽略**（沿用 F012 基座 Pydantic 默认行为），不视为错误；该行为不构成产品规则。
4. `PATCH` 请求体**必须**包含 `name`（它是唯一可变字段；缺失即 `400`）。
5. `GET /api/clusters/by-name/{cluster_name}/bare-metals` 归属 **F009**（Cluster 视角查询），实体归 F002。
6. 前端不引入 `vue-router`，用极简视图状态切换列表 / 详情。
7. 前端 `POST` / `PATCH` 表单随本次交付（不构成 AC）。
   > **更正注记（2026-09-18，F016）**：本条与上方 Frontend Work §6（「**可**一并交付」）矛盾，且实际**未交付**——`createCluster` / `updateCluster` 被写入 API 客户端但零调用者。已由 F016 补做并纳入 AC 覆盖。详见 §6 的注记。
8. 分页上限沿用 F012 的 `page_size` 默认 50 / 上限 200。

### OPEN

1. `name` 的未定义约束（NQ-1）——**不阻塞本次实现**；若 PROPOSED-1 被确认，属新增产品规则 + 增量 migration。
2. Cluster 名称是否允许修改（NQ-5 / PROPOSED-2）——本次按假设 3 纳入 `PATCH`；若确认为不可变，F001 缩减 AC-12 与契约中的 `PATCH`。
3. 前端路由方案（`vue-router`）何时引入。
4. F014 是否把 `DELETE /api/clusters/{id}` 注册在 `app/clusters/router.py` 还是独立模块（不影响 F001 交付面）。
5. `name` 的 `by-name` 路径段编码边界（空名称段）——未定义、不承诺。

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | **移除 `/_foundation/*` 使 F012 的架构判据 4 / 5 / 6 与 T8 / T9 / T12 / T13 失去触发面**，若不做接管会静默丢失验证力（F012 交接 Risk #4） | 明确接管方案：T8′（产品端点驱动错误信封）、T9′（产品 CRUD + 绕应用层软删 + API 读取排除）、A16（产品列表页三态）、A14（自检面彻底不存在）。**这些是本次的必做项，不是可选优化** |
| R2 | 测试 G3 被误读为「CSM 已确认空名称 / 空白名称合法」 | G3 的 docstring 强制声明「断言的是实现不做变换，不是业务合法性」；契约正文**不承诺**这些取值行为；NQ-1 保留 |
| R3 | 应用层唯一性预检与数据库唯一索引语义漂移（「查得到却写不进」或反之） | 预检与 `ux_clusters_name_active` 使用同一谓词（活跃）；A04 强制证明 DB 权威；F012 T4/T5 保留 |
| R4 | `DELETE /api/clusters/{id}` 被后续开发者「顺手」补上，产生第二条软删路径 | A15 静态 guard：`backend/app/**` 中 `deleted_at` 赋值数必须为 0；DELETE 路由存在性断言 |
| R5 | 前端「Empty 与 Not Found 可区分」在仅有组件级 404 桩件时被弱化（无 URL 路由可直达 404） | A16 断言两种状态渲染不同；文档明确 F001 不引入路由是该限制的来源（OPEN #3） |
| R6 | F012 Review 的 F-03（自检面 fail-open）若本次不移除会持续存在 | 本裁定**彻底移除**该面，F-03 随之消解（`foundation_enabled` 不复存在） |
| R7 | 技术约定名（模块路径 / 约束名）被误当产品规则 | 全部约定在文档中标注为工程约定，不改变领域语义 |

## Constraints

1. 不得修改 `0001_f012_baseline`；不得新增同类数据库约束或新列（当前无产品依据）。
2. 不得为 `name` 引入长度 / `trim` / 非空串 / NFC 校验，也不得在契约、前端文案或 AC 中承诺其行为。
3. 不得实现任何写入 `deleted_at` 的路径；不得实现 F014 的删除语义、父删子拦、并发加锁、`ip_address.cluster_id` 治理。
4. 不得实现认证 / 会话 / 权限（F013），不得添加 `current_user` 桩或占位用户。
5. 不得实现 BareMetal 或其他资源（F002+）；不得为 R-CLUSTER-004 预留表 / 列 / 端点。
6. 不得引入新框架 / 中间件 / 新依赖；不得引入 EAV / 通用 `resources` 表 / STI / ORM 多态 / JSONB 万能模型。
7. 不得把 UNCONFIRMED / PROPOSED 固化为必选。
8. 不得偏离 `api-conventions.md` 的信封、状态码与 Empty / Not Found 语义；不得另立第二套 SQLSTATE 映射。
9. 不得让 `/_foundation/*` 以任何形式残留在运行时或源码中。
10. 不引入 ADR（本次裁定为 Feature 级范围决策，记录于本 Handoff 与同步的 F012 文档）。

## Open Technical Questions

### Blocking

**无。**

### Non-blocking

1. `name` 的未定义约束（NQ-1 / PROPOSED-1）：不改变 F001 任一 AC；建议在真实数据录入前由用户确认。
2. Cluster 名称可变性（NQ-5 / PROPOSED-2）：若确认不可变，删除契约中的 `PATCH` 与 AC-12。
3. 前端路由方案（OPEN #3）。
4. F014 端点注册位置（OPEN #4）。
5. F012 Review 遗留 F-01（未映射 4xx 统一标为 `INTERNAL_ERROR`，使 `405` 语义误导）：**F001 不修改**通用映射表（超出产品范围，且会改动已批准契约映射）；`DELETE` 的 405 断言因此只断状态码。该项继续作为 Backend follow-up 记录。
6. F012 Review 遗留 F-02（FK 违规字段回退解析截断多词列名）：F001 无 FK 路径，不触发、不修复。

## Implementation Layers

```text
database: false
backend:  true
frontend: true
```

- **database = false**：无 Schema 变更 / 索引 / migration。基线与数据库设计已 `READY`；`clusters` 表结构直接使用。数据库相关交付仅为**测试断言**（G2 / A08 / A10 / A11），由 Backend 承担。
- **backend = true**：Cluster 模块（5 端点、领域校验、活跃查询、唯一性预检）+ 彻底移除 `/_foundation/*` + 契约与文档同步 + 后端测试集。
- **frontend = true**：Cluster 列表页（三态 + 分页）、Cluster 详情页骨架（Not Found 态）、`api/clusters.ts`、删除 dev 自检页与 foundation client、清理 Vite proxy。

## Implementation Order

```text
Architecture + API Contract（本 Handoff + docs/api/f001-cluster.md，均 READY）
  ├─ Frontend（只需契约稳定：api/clusters.ts → 列表页三态 → 详情页骨架 → 移除自检页与 vite proxy）
  └─ Backend（先移除 /_foundation，再建 clusters 模块，最后补测试）
                 ↓ 两个必需分支完成
              Tester → Reviewer
```

- **无 Database Design 分支**（`database: false`）；无需等待数据库 Agent。
- Backend 与 Frontend 可**直接并行**（无 DB 变更、契约已 READY）。
- 文件所有权：Backend = `backend/**` + `tests/**` + `.env.example` + `README.md`；Frontend = `frontend/**`；共享 docs 由协调器落盘。

## Verification Strategy

1. **契约层（AC-01 ~ AC-06、AC-08、AC-11、AC-12）**：API 行为断言，含字段集合、状态码、`error.code`、`details[].field`。
2. **软删读取侧（AC-07）**：**绕过应用层**用原始数据库连接预置 `deleted_at`，再断言 list / `{id}` / `by-name` 三者均排除；并断言同名可重建（R-DELETE-006）。
3. **单一路径（AC-13）**：运行时 guard（任何配置下 `/_foundation/*` 均 404）+ 静态 guard（源码中无 `_foundation`，`backend/app/**` 中 `deleted_at` 赋值数为 0，`DELETE /api/clusters/{id}` 不软删）。
4. **数据结构否定性（AC-09、AC-10、G2）**：`Base.metadata` 与 `alembic upgrade head` 后的实际 Schema 双断言：无状态列、无上级 / 位置列、CHECK 集合恰为 `{ck_clusters_name_no_slash}`。
5. **未定义约束不实现（G1 / G3）**：schema 内省 guard + 无静默归一化 canary。
6. **数据库权威性（A04 + F012 T3/T4/T5/T6 保留）**：绕应用层的唯一性 / `/` / 软删释放断言不变。
7. **F012 判据保持（T8′ / T9′ / T13′ / T12→A16）**：确保移除自检面**不降低**基座验证力。
8. **前端（AC-14）**：组件级三态与 Empty / Not Found 区分；前端构建成功、既有 UI 基座测试（`listStates` / `errorState` / `useAsyncQuery` / `http`）通过（路径引用改接产品端点）。
9. **工程门禁**：lint 通过；`alembic upgrade head` ×2 与 `downgrade base && upgrade head` 仍成功（未被本次改动影响）。
10. **中文（AC-11 + F012 T7）**：HTTP 与数据库双层往返。

---

## 核心问题逐条回应（Product Handoff #1 ~ #9）

### 问题 1 — F001 ↔ F014 删除边界与端点归属（NQ-2）

**裁定：`DELETE /api/clusters/{id}` 整体推迟到 F014；F001 不注册该路由、不实现任何软删写入路径。**

理由（均为已确认依据）：

1. ADR-0004 §1/§3 要求软删写入由**统一逻辑删除领域服务**提供、禁止各模块各写一套。若 F001 暴露该端点而不具备 F014 的语义（父删子拦、同事务加锁），它会成为一条**语义不完整的第二条路径**，且在 F014 落地时必须重做。
2. R-DELETE-004 的 Cluster 示例在 F001 阶段**不可验收**（`bare_metals` 属 F002），F014 在同一阶段才具备完整语义。
3. Product Handoff 已判定「删除不进入 F001 的产品 AC」；AC-13 只要求「不存在未经 F014 统一软删领域服务的 `deleted_at` 写入路径」——**最简且唯一满足该条的方式是 F001 内该路径数 = 0**。
4. F012 的 `/_foundation/*` 的 `DELETE` 明确**不是**产品软删除语义，本次随该面一并移除（问题 2），不留下「看似夹具、实可复用」的写入路径。

**F001 的读取路径如何获得软删过滤**：**复用 F012 的 `app/db/active.py` 原语**（`active_filter` / `select_active`），**不等** F014 的统一领域服务。依据：

- ADR-0004 §3 的主语是「**数据访问层统一提供**」。F012 已交付该唯一承载点（`app/db/active.py`），其 docstring 明确「不是领域服务」。F014 交付的是**写入侧**的统一领域服务（含删除时的父子一致性），并将**组合**同一原语，而不会替换谓词。
- 因此 F001 的读取不产生第二份 `deleted_at IS NULL` 谓词，满足「只有一条软删路径」。
- 若 F014 将来引入更高层的读取服务，Cluster 仓储可改为调用该服务，但**谓词来源不变**，属无害重构。

**AC-07 在 F001 内的验证方式**：测试用**原始数据库连接（绕过应用层）**写入一行并把 `deleted_at` 置为非空，然后断言：(a) 不出现在 `GET /api/clusters.items`；(b) `GET /api/clusters/{id}` → `404 NOT_FOUND`；(c) `by-name` → `404 NOT_FOUND`；(d) 该名称可被重新登记（R-DELETE-006）。**完全不依赖任何产品删除端点**，与 F012 的「绕过应用层断言」取向一致。

**前端**：F001 **不提供删除入口**（与 Product NQ-2 建议一致）。

**待 F014 的接缝（记录，不在本次实现）**：F014 将在同一 `app/clusters` 模块（或独立模块）注册 `DELETE /api/clusters/{id}`，委托统一软删领域服务；届时 A15 的静态 guard（`deleted_at` 赋值数 = 0）由 F014 更新为「仅允许出现在统一领域服务模块中」。

### 问题 2 — `/_foundation/*`：彻底删除 vs 降级。移除后的四项连带问题

**裁定：彻底删除（PROPOSED，采纳）。** 不保留模块、不保留开关、不保留「仅测试可见」的运行时面。

理由：

- 该面的存在价值只有「在 F001 之前证明全栈贯通」。F001 交付产品端点后，价值归零，而**风险不为零**：F012 Review 的 **F-03（MEDIUM）** 指出 `CSM_ENVIRONMENT` 未设置时 `foundation_enabled` 默认 `True`，自检面 fail-open 可达，且提供对 `clusters` 的**未认证写端点**（POST/PATCH/DELETE），并刻意位于 `/api` 之外，不受 F013 认证覆盖。
- 「降级为测试夹具」会保留这条 fail-open 面与其未认证写路径，与 AC-13「不存在未经 F014 统一软删领域服务的 `deleted_at` 写入路径」直接冲突（夹具的 `soft_delete` 就是这样一个写入）。
- 彻底删除可**同时消解 F-03**，并使 `Settings.foundation_enabled`、Vite proxy、`.env.example`、README 的整条非产品分支消失，降低长期维护面。

**连带问题逐条回答：**

| 问题 | 结论 |
|---|---|
| F012 判据 5（端到端往返）与 T9 如何维持？ | **拆成两条继续成立**：<br>(a) `create → list → get → update` 由**产品端点**完成（A01/A06/A08/A13）；<br>(b) `soft delete` 一段**改为绕应用层写入 `deleted_at`**，再经产品 API 断言「已删不出现在 list / 不可 get / 不可 by-name」（**A08**，即 AC-07 的验证）。这保留了判据 5 的可观察断言「删除后不出现在 list 中」，且**不引入任何删除端点**。<br>另：F012 既有的数据库层 T5（软删后同名可重建、已删行不出现在活跃查询）**原样保留**。 |
| 前端 dev 三态基座改接哪个端点？ | 改接**产品端点** `GET /api/clusters`：Loading / Empty 直接由其驱动（Empty = `200` + `items == []`）；Error 态改由**确定性产品错误**驱动，推荐 `GET /api/clusters?page=0` → `400 VALIDATION_ERROR`（或组件测试桩件）。同时**删除** `pages/DevSelfCheckPage.vue` 与 `api/foundation.ts`；`ListStates.vue` / `ErrorState.vue` / `useAsyncQuery.ts` 保留为基座。F012 判据 6 的验证力由产品 Cluster 列表页承载（A16）。 |
| 如何保证移除后不残留任何未受 F014 约束的 `deleted_at` 写入路径？ | **A15 双重 guard**：<br>(1) **静态**：扫描 `backend/app/**/*.py`，断言不存在对 `.deleted_at` 的赋值（正则 `\.deleted_at\s*=`），当前必须为 **0 处**；F014 落地后由 F014 收窄为「仅允许在统一软删领域服务模块内」；<br>(2) **运行时**：`DELETE /api/clusters/{id}` 必须不执行软删（`405`/`404`），返回后该行仍活跃。<br>此外 `app/foundation/` 目录整体删除，`soft_delete` 实现随之消失（该实现是当前唯一写入点）。 |
| F012 的 T13（生产 404）如何调整？ | **升级为更强的断言并改名**：从「生产配置下 404」改为「**任何配置（dev / test / prod）下 `/_foundation/*` 全部 404**」+ 静态断言「`backend/app/**` 中不存在 `_foundation` 字符串、`app/foundation/` 目录不存在、`Settings` 无 `foundation_enabled`」（**A14**）。原 T13 的意图（非产品面隔离）被**更彻底**地满足。 |

**文档同步**（由协调器落盘）：`docs/api/f012-project-foundation.md` 顶部标注「§4 已于 F001 移除，正文保留为历史记录」，`docs/architecture/f012-project-foundation-handoff.md` 的 Risk #1 与 Non-blocking #2 标注 RESOLVED。

### 问题 3 — `clusters` 资源表示与契约落点（AC-01 / AC-09 / AC-10）

**契约落点：新建 `docs/api/f001-cluster.md`**，作为 Cluster 资源的产品契约；`docs/api/api-conventions.md` **不修改**（F001 不新增任何通用规则）。

**对外字段（完全封闭集合，恰好 4 个，全部 `nullable: false`）**：`id`（integer）、`name`（string）、`created_at`（RFC 3339）、`updated_at`（RFC 3339）。

**明确不存在**：`deleted_at`（不对外暴露）、任何状态字段（AC-09）、任何 DataCenter / 园区 / 机房 / 机柜 / U 位字段（AC-10）、任何 BareMetal 相关字段或计数（问题 7）。响应中不存在可空字段，因此「可选字段返回 `null` 而不省略」的通用约定在本资源上不触发。

### 问题 4 — `by-name` 别名的路由与解析（NQ-3）

1. **canonical vs alias**：`/api/clusters/{cluster_id}`（`id`，integer）为**规范路径**，写操作一律走 `id`；`GET /api/clusters/by-name/{cluster_name}` 为**只读别名**，**不存在**对应的写别名。
2. **路由声明顺序**：`by-name` 路由**先于** `/{cluster_id}` 声明（防御性约定）。由于 `{cluster_id}` 为 `int` 路径参数，`by-name` 不会被误当作 `id`。
3. **大小写敏感匹配**：直接按字面值等值比较（数据库默认 collation，大小写敏感），**不得** `lower()` / `ILIKE` / 归一化。
4. **已删不参与解析**：解析带活跃谓词 → 命中不到即 `404 NOT_FOUND`。
5. **编码处理**：`{cluster_name}` 为单个 URL 路径段；中文字符与空格、`#`、`?`、`%` 等按 RFC 3986 百分号编码（UTF-8）传输，服务端解码为字面值后参与等值比较。名称含 `/` 不可能存在（R-CLUSTER-005 同时是「别名路径不会因名称而分段错乱」的技术保障）。名称为纯数字（如 `"123"`）时走 `by-name` 可无歧义解析，这正是别名前缀存在的理由。
6. **`by-name/{cluster_name}/bare-metals` 不在 F001**：裁定归属 **F009**（Cluster 视角资源查询，R-QUERY-001/002），其数据依赖 F002 交付的 BareMetal 实体。F002 只交付 BareMetal 实体与自身 CRUD，不交付该嵌套读端点。

### 问题 5 — `/_foundation/*` 方案

见**问题 2**（彻底删除 + 四项连带的完整结论）。

### 问题 6 — 名称更新的并发与冲突语义

1. **唯一性判定**：`PATCH` 与 `POST` 复用**同一**领域校验路径（`app/clusters/validation.py`）。应用层先预检活跃唯一性 → 命中则 `409 CONFLICT` + `details[].field` 含 `name`。
2. **数据库为最终权威**：两个并发 `PATCH`（或 `PATCH` 与 `POST` 竞争）间，预检存在竞态窗口；此时 `ux_clusters_name_active` 抛 `23505`，经 F012 的通用映射 → `409 CONFLICT`。**必须有一条测试（A04）证明该路径**，防止「只靠预检」的实现。
3. **改成自身当前名**：必须 `200`（唯一索引对同一行不冲突），不得误报 `409`（A13）。
4. **无乐观锁**：`clusters` 无 `version` 列（数据库设计决策 7），不引入。并发对**同一行**修改不同名称时**最后一次提交生效**（last-write-wins）；这是当前规模（10⁵ 资源 / 50 并发 / 低频 CRUD）与「无明确收益不引入」原则下的明确取舍，不是缺陷，也**不得**用 `updated_at` 冒充并发控制（DB 设计决策 8）。
5. **F001 不承担 F014 的并发职责**：不在本 Feature 内实现行锁 / 父子完整性协议；`PATCH` 单行更新不需要行锁（唯一索引已提供并发正确性）。
6. **`PATCH` 不修改 `created_at`**；`updated_at` 由应用层（SQLAlchemy `onupdate`）更新。

### 问题 7 — AC 归属的架构对齐（NQ-3 / NQ-4 / 问题 D）

| 规则 / 需求 | F001 内的处理 | 归属 |
|---|---|---|
| R-CLUSTER-004（Cluster 可包含多个 BareMetal） | **不实现**：不建表、不加列、不加计数字段、不加嵌套端点 | F002（R-BM-001 的 N:1 方向）+ F009（R-QUERY-002 的 Cluster 视角方向） |
| R-QUERY-001 / R-QUERY-002 | **不实现**：F001 只交付 Cluster 自身的列表 / 详情 | F009 |
| R-QUERY-003 | 不涉及 | F010 |
| `GET /api/clusters/by-name/{cluster_name}/bare-metals` | **不实现** | F009（实体依赖 F002） |
| R-QUERY-004（Empty vs Not Found） | **部分实现**：Cluster 自身的 Empty（列表 200 空集）与 Not Found（`{id}` / `by-name` 404）可区分 | F001（Cluster 维度）；父子关系维度归 F009 |
| R-DELETE-001 ~ 006 | 只实现**读取侧后果**（已删不参与查询 / 解析） | F014 |
| R-DELETE-004 的 Cluster 示例 | 不可验收，不实现 | F014（+ F002 提供子实体） |

### 问题 8 — 「未定义约束不实现」的可审查保障（NQ-1）

落成 **3 条可失败测试 + 1 条 Review 检查项**，不依赖口头约定：

| 编号 | 类型 | 断言 | 会在什么情况下失败 |
|---|---|---|---|
| **G1** | 单元（Pydantic 字段内省） | `ClusterCreate.model_fields["name"]` / `ClusterUpdate` 的字段元数据中**不存在** `min_length` / `max_length` / `pattern` / `strip_whitespace`；并断言不存在对 `name` 施加 trim / NFC / 非空串的 validator | 任何人添加长度 / 空白 / 空串 / NFC 约束 |
| **G2** | 数据库 | `alembic upgrade head` 后 `clusters` 的 CHECK 约束集合**恰为** `{ck_clusters_name_no_slash}`；列集合**恰为** `{id,name,created_at,updated_at,deleted_at}` | 任何人新增 `name <> ''` / 长度 / `trim` CHECK 或新列 |
| **G3** | API（canary） | `name` 为 `" cn-a "`、`"\u00e9"`、`"e\u0301"` 时，`GET` / `by-name` 返回与输入**逐字节相同** | 任何人添加 trim / NFC 归一化 / 大小写折叠等静默变换 |
| **G4** | 文档（间接） | 契约正文 §7 明确列出「不承诺」清单 | 由 **Reviewer 检查项**保证：`docs/api/f001-cluster.md` 不得出现 `min_length` / `max_length` / `trim` / NFC / 「非空」「不允许空串」等承诺性措辞 |

**边界声明**（必须写入 G3 的 docstring 与契约 §7）：G3 断言的是「**实现不做任何变换**」，**不是**「这些名称在业务上合法」。`undefined_constraints` 当前既不确认合法也不确认非法；若用户确认 PROPOSED-1，**必须由产品决策同步修改 G1 / G2 / G3**，不得由实现方静默补校验。

### 问题 9 — 认证边界（NQ-6）

1. F001 **不实现**认证 / 会话 / 口令 / 中间件，**不添加** `current_user` 桩、占位用户或伪权限。
2. `POST/GET/PATCH /api/clusters*` 在 F013 落地前**临时无需认证**——显式、临时、已记录。
3. **为 F013 预留标准保护位**：全部端点位于 `/api` 前缀下，因此 F013 的 `/api/*` 认证中间件**自动覆盖**，**无需**任何白名单成员。**不得**把任何 Cluster 端点放到 `/api` 之外（`/_foundation` 的教训）。
4. 本 Feature **不**触碰 `GET /api/health` 的认证豁免问题（F012 Non-blocking #1，属 F013 决策）。
5. 部署期网络可达性限制属 F015，不在本 Feature。

### 问题 10 — 其他 NQ

| NQ | 架构侧结论 |
|---|---|
| NQ-1 | 见问题 8；非阻塞 |
| NQ-2 | 见问题 1；非阻塞 |
| NQ-3 | 见问题 4 / 问题 7：`by-name/{name}/bare-metals` 归 **F009** |
| NQ-4 | 见问题 7：F001 不验收 R-CLUSTER-004，不为其预留结构 |
| NQ-5 | 本次按假设 3 纳入 `PATCH`；若确认不可变则删除契约中 `PATCH` 与 AC-12（属**范围缩减**，非规则修改）。OPEN 非阻塞 |
| NQ-6 | 见问题 9 |
| NQ-7 | 详情页只呈现 Cluster 自身字段（问题 3 / 问题 7） |
| NQ-8 | 沿用 `page_size` 默认 50 / 上限 200（F012 PROPOSED #3），不固化为产品规则 |

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

**放行依据**：所有输入均为 `READY` / `ACCEPTED` / `CONFIRMED`；Product Handoff 无 Blocking 问题；`database: false`（无 Schema 不确定性）；API Contract = `READY`；两个实现分支（Backend / Frontend）均有可直接开工的依据。需用户确认的长期技术决策：**无**。