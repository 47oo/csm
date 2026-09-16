# Architecture Handoff — F009 Cluster 视角资源查询

> Status: `READY FOR IMPLEMENTATION`
> Author Role: architect
> Feature: F009（E05，P0，`depends_on: [F001, F002]`，二者均已 DONE）
> Product Source: `docs/product/handoffs/f009-cluster-resource-view.md`（`READY FOR ARCHITECT`，无 Blocking）
> 配套契约: `docs/api/f009-cluster-resource-view.md`（`READY`，另文）

---

## Feature

Cluster 视角资源查询（F009）— 在既有的「按 Cluster 限定读取 BareMetal」能力之上，交付 ADR-0003 §2 已确认但尚无认领者的只读名称别名 `GET /api/clusters/by-name/{cluster_name}/bare-metals`，并把「Cluster 不存在/已删 → 404」与「Cluster 存在但无活跃 BareMetal → 200 Empty」的一致性、软删过滤复用与「不越界到 NIC/IP/VM/Container/Service」落成**可审查的 guard 与测试**。F009 **不新增**领域对象、字段、关系、状态、唯一性规则，也**不新增**任何 Cluster 视角的第二套前端视图。

## Product Source

- `docs/product/handoffs/f009-cluster-resource-view.md`（AC-01 ~ AC-16、NQ-1 ~ NQ-5、Architecture Handoff 1~8）
- `docs/product/requirements.md` §7 / §8 / §15 / §16 / §17 / §21 / §22 / §23
- ADR-0001 ~ ADR-0005（全部 `ACCEPTED`；重点 ADR-0003 §2/§6、ADR-0004、ADR-0005）
- `docs/api/api-conventions.md`、`docs/api/f001-cluster.md`、`docs/api/f002-bare-metal.md`、`docs/api/f014-soft-delete.md`
- `docs/architecture/f001-cluster-handoff.md`（PROPOSED #5）、`f002-bare-metal-handoff.md`（问题 4）、`f014-soft-delete-handoff.md`

## 现状核实（只读检查结论）

| 项 | 现状（已核实） |
|---|---|
| 按 Cluster 限定读取 | **已存在** `GET /api/bare-metals?cluster_id={id}`；`cluster_id` 给定时先以 `select_active(Cluster)` 确认父活跃，未命中 → `404 NOT_FOUND`，命中但无活跃子 → `200` + `items==[]` |
| Cluster 名称解析 | **已存在** `clusters.service.get_cluster_by_name` → `repository.get_active_by_name`（`select_active(Cluster).where(Cluster.name == name)`：字面值、大小写敏感、仅活跃，未命中 `404`） |
| 只读别名 | `GET /api/clusters/by-name/{cluster_name}`（F001）**已存在**；`GET /api/clusters/by-name/{cluster_name}/bare-metals`（ADR-0003 §2）**不存在**，F001/F002 均排除并指向 F009 |
| 软删过滤 | 统一原语 `app/db/active.py`（`active_filter` / `select_active`）；唯一写入路径 `app/deletion/service.py`；`scan_deleted_at_writes` allow-list 恰为 `{backend/app/deletion/service.py}` |
| 认证 | F013 纯 ASGI 中间件 fail-closed 保护全部 `/api/*`（唯一豁免 `POST /api/auth/login`）；新增 `/api` 路径自动覆盖 |
| 前端 Cluster 视角视图 | **已存在**：`ClusterDetailPage`「查看裸金属」→ `App.vue` `openClusterBareMetals(clusterId)` → `BareMetalListPage` 以 `clusterId` 限定；三态互不相同，Empty 与 Not Found 可区分，错误按 `error.code` 分支 |
| 数据库 | `clusters`（`0001`）、`users`/`sessions`（`0002`）、`bare_metals`（`0003`）。名称解析复用 `ux_clusters_name_active`；按 Cluster 读取复用 `ix_bare_metals_cluster_id`。**无需任何 schema 变更** |

**结论**：F009 是在非空、已具完整基座与 F002 既有 Cluster 限定读取之上的**增量读取面 + 收口**。不需要数据库变更，不需要新的前端实现，但需要一条新的只读后端路由与配套 guard。

---

## Architecture Summary

**目标**：让「站在一个集群上，看清它有哪些机器、各自什么状态」成为经过契约固定、且可在同一条读取路径上被验证的事实；并把 ADR-0003 §2 已确认的只读名称别名落地。

**对现有系统的影响**：
- 新增 F009 模块 `backend/app/cluster_views/`（`router.py` + `service.py`），只注册**一条**路由 `GET /api/clusters/by-name/{cluster_name}/bare-metals`，挂载到 `/api`。
- **改** `backend/app/main.py`：`include_router(cluster_views_router, prefix="/api")`。
- **改** `tests/test_auth_guards.py > EXPECTED_GET_ROUTES`：**追加**新路径（不删除既有成员）。
- 新增边界/一致性 guard（`tests/test_cluster_views_guards.py`，**只增不减**）。
- **不改** 任何既有契约正文、数据库、前端实现、`app/clusters/**` / `app/bare_metals/**` 现有行为（只被复用）。

**方案要点**：
1. **交付面**：复用 F002 的 `GET /api/bare-metals?cluster_id=` 作为 canonical；F009 的正面交付物是**只读名称别名端点** + 语义收口 guard + 测试。前端复用 F002 已交付的集群限定列表，不新增视图。
2. **别名语义**：解析 `cluster_name`（字面值、大小写敏感、仅活跃）→ 未命中 `404`；命中后**委托** `bare_metals.service.list_bare_metals(..., cluster_id=cluster.id)`，其内部**再次**执行 F002 的父存在性检查 —— 由此获得 404-vs-Empty 的一致判定与并发稳定性。不引入任何第二条 `deleted_at IS NULL` 谓词（ADR-0004）。
3. **返回契约**：别名返回的信封与字段集合与 F002 列表**逐字段一致**（`Page[BareMetalRead]`），以 guard 断言两者 OpenAPI response schema 相等。
4. **边界守卫**：把「不越界到 NIC/IP/VM/Container/Service」落成路由集合 guard + 响应 schema 封闭 guard + 静态 token guard。
5. 无新框架 / 新依赖 / 新中间件 / 新表 / 新列 / 新索引；不引入 `vue-router`；不动认证白名单。

---

## Domain Impact

**使用**已有领域对象 `Cluster`（名称解析）与 `BareMetal`（成员与状态）。

**新增**领域对象 / 字段 / 关系 / 状态 / 唯一性规则：**无**。`Cluster → BareMetal` 是已确认的 N:1 关系（R-BM-001 / R-CLUSTER-004）；F009 只交付其 **Cluster 视角读取**。R-QUERY-003 的 NIC/IP/VM/Container/Service 关系归 F010，F009 不建模、不预留（§15）。

**明确不引入**：Cluster 状态（R-CLUSTER-003）、DataCenter / 位置 / Rack / U 位（§6、§13）、自动发现 / 外部状态源（§23、R-BM-006）。

---

## Data Layer Impact

**无需数据库变更**。

1. **名称解析**：`clusters.name` 的活跃范围等值匹配，由既有 `ux_clusters_name_active`（partial unique, `WHERE deleted_at IS NULL`）与默认（大小写敏感）collation 支撑，不新增索引/列/`COLLATE`。
2. **按 Cluster 读取成员**：由既有 `ix_bare_metals_cluster_id` 与 `ux_bare_metals_cluster_hostname_active` 支撑。
3. **活跃过滤**：统一复用 `app/db/active.py`；`cluster_views` 模块**不含**任何 `deleted_at` 表达式。
4. **不做**：不改 `0001`/`0002`/`0003`；不新增 migration；不新增表/列/索引/CASCADE/触发器。

---

## Backend Work

### 1. F009 模块 `backend/app/cluster_views/`
- `service.py`：`list_cluster_bare_metals_by_name(session, params, cluster_name) -> tuple[list[BareMetal], int]`
  1. `cluster = clusters.service.get_cluster_by_name(session, cluster_name)`；`None` → `NotFoundError`（`404`）。
  2. `return bare_metals.service.list_bare_metals(session, params, cluster_id=cluster.id)`（**复用** F002 的父存在性检查与活跃过滤；不复制谓词）。
- `router.py`：`APIRouter(prefix="/clusters", tags=["cluster-views"])`
  - `@router.get("/by-name/{cluster_name}/bare-metals", response_model=Page[BareMetalRead])`
  - 复用 `page_params` 依赖（`page` / `page_size`，默认 50 / 上限 200）。
  - 路径参数名 `cluster_name`（string，单段）。
- **禁止**在该模块出现 `deleted_at`（写入或过滤表达式）；filter 只能来自 `app/db/active.py` 与既有 service。

### 2. 路由挂载
- `app/main.py`：`app.include_router(cluster_views_router, prefix="/api")`。
- 路径形状（5 段）与 F001 `/clusters/by-name/{cluster_name}`（4 段）、`/clusters/{cluster_id}`（3 段）不同，无匹配歧义。

### 3. 明确不做
- 不新增任何其它路由；不注册 NIC/IP/VM/Container/Service 端点或占位。
- 不修改 `app/clusters/**` / `app/bare_metals/**` 既有行为；不新增第二处 `deleted_at` 写入/过滤路径。
- 不提供 `include_deleted` / restore / undelete / 回收站 / 批量。
- 不新增字段、不新增状态、不新增关系。

---

## Frontend Work

**无需新增前端实现。**

依据：AC-01 ~ AC-05、AC-08 ~ AC-13 的 UI 行为已由 F002 交付物完全满足：`ClusterDetailPage.vue` 入口携带 `clusterId`；`BareMetalListPage.vue` 三态 + Empty/NotFound 区分 + `error.code` 分支已实现；`frontend/tests/bareMetalListPage.spec.ts` 与 `appBareMetalNavigation.spec.ts` 已覆盖。

F009 不得新建第二套 Cluster 视角页面或内联重复成员列表。F009 对前端的义务是**验证 / 收口**（回归测试），归入 Test Work，由 Test agent 在 `frontend/tests/**` 内完成；**不新增** `frontend/src/**` 实现文件。

---

## Database Work

**无需**。无 schema 变更、无 migration、无新表/列/索引/约束。`database: false`。

---

## Contract

```text
READY
```

完整正文见 `docs/api/f009-cluster-resource-view.md`（F009 唯一权威）。该契约只定义 `GET /api/clusters/by-name/{cluster_name}/bare-metals`，并把 canonical 明确指向 F002 `GET /api/bare-metals?cluster_id={id}`；通用规范引用 `api-conventions.md`，不重复定义；`f001-cluster.md` / `f002-bare-metal.md` / `f014-soft-delete.md` 正文不修改。

---

## Test Work

以「canonical（`?cluster_id=`）」与「alias（`by-name/.../bare-metals`，新增）」两条路径分别/组合验证。

### API + DB 行为

| # | 测试 | 层次 | AC |
|---|---|---|---|
| **T-01** | 活跃 Cluster C（2 台活跃 BareMetal）：alias 与 canonical 均返回这 2 台（id 升序），信封与字段集合与 F002 §3.2 **逐字段一致** | API | AC-01、AC-02 |
| **T-02** | 每条记录含 `hostname` 与 `status`；`status ∈ {IDLE,ALLOC,DOWN,UNKNOWN}` 且非 `null` | API+DB | AC-02 |
| **T-03** | C1/C2 各有机器：C1 视角不含 C2 的机器；反之亦然 | API+DB | AC-03 |
| **T-04** | `PATCH /api/bare-metals/{id}` 置 `DOWN` 后，重新查询该台 `status=="DOWN"`，其余不变 | API+DB | AC-04 |
| **T-05** | Cluster 名与 `hostname` 含中文：alias 路径百分号编码命中；结果按字面值读出 | API | AC-05 |
| **T-06** | Cluster **不存在**：alias 与 canonical 均 `404 NOT_FOUND`（不得 200 空集） | API | AC-06 |
| **T-07** | Cluster **已软删**（绕过应用层置 `deleted_at`）：alias → `404`；canonical → `404` | API+DB | AC-07 |
| **T-08** | Cluster 存在且活跃但无活跃 BareMetal：alias 与 canonical 均 `200`、`items==[]`（Empty） | API+DB | AC-08 |
| **T-09** | alias `200` 空集不是错误：响应无 `error`，状态码 200 | API | AC-08、AC-10 |
| **T-10** | alias 大小写敏感：`by-name/Cluster-A` 不命中 `cluster-a`；命中结果与 canonical 对 `Cluster-A` 的 id 结果一致 | API | AC-05、§22 |
| **T-11** | 已软删 BareMetal（绕过应用层预置，同 Cluster 另有活跃）：alias 与 canonical 只返回活跃那台 | API+DB | AC-11 |
| **T-12** | `DELETE /api/bare-metals/{id}` 后重新查询：该台不再出现，其余与 Cluster 自身不变 | API+DB | AC-12 |
| **T-13** | Cluster 视角路径与 alias 上不存在 `include_deleted` / restore / undelete / 回收站参数或路由（负向断言） | API | AC-13 |
| **T-14** | 未认证访问 alias（无 Cookie）→ `401 UNAUTHENTICATED`，且不返回任何资源数据 | API | AC-16 |
| **T-15** | alias `page` / `page_size` 非法（`0`、`201`、非整数）→ `400 VALIDATION_ERROR`，`details[].field` 为 `page` / `page_size` | API | 契约 §5 |
| **T-16** | alias 分页正确：`total` 为该 Cluster 活跃总数，`page`/`page_size` 回显与请求一致 | API | 契约 §3 |
| **T-17** | alias 命中结果与 canonical 对同一 Cluster **深等**（`items` 字段与值、`total` 一致） | API | 契约 §2 |

### 结构 / 静态 guard（只增不减）

| # | guard | 说明 | 关联 |
|---|---|---|---|
| **G-009-1** | `EXPECTED_GET_ROUTES` **追加** alias 路径；既有成员**全部保留** | 路由封闭 | AC-14、AC-16 |
| **G-009-2** | **边界 token guard**：遍历全部 OpenAPI path，断言不含 `network-interface` / `network_interface` / `ip-address` / `ip_address` / `virtual-machine` / `virtual_machine` / `container` / `service` 等 token | 路由封闭 | AC-14、§15 |
| **G-009-3** | **响应 schema 封闭**：alias 200 content schema 与 `paths["/api/bare-metals"].get.responses.200` **相等**；`BareMetalRead` 字段集合恰为 F002 §2 的 13 字段 | 字段封闭 | AC-14、AC-15 |
| **G-009-4** | `cluster_views` 模块源码与 OpenAPI 请求/响应中不含 Cluster 状态字段、DataCenter/位置字段、自动发现/实时状态源字段 | 字段封闭 | AC-15 |
| **G-009-5** | `scan_deleted_at_writes(APP_DIR / "cluster_views") == {}`；全局 allow-list 仍恰为 `{backend/app/deletion/service.py}` | 软删单一性 | ADR-0004、AC-11 |
| **G-009-6** | alias 路由集合恰为 `{GET /api/clusters/by-name/{cluster_name}/bare-metals}` | 交付面封闭 | AC-14 |

### 既有测试的演进（必须演进，不得删除）

- `tests/test_auth_guards.py::EXPECTED_GET_ROUTES` → **追加** alias 路径；其余断言原样保留。
- `tests/test_deletion_guards.py` → 原样保留；可扩展覆盖 alias（追加，不替换）。
- `tests/test_structure_guard.py::test_only_expected_tables_registered` → 不改（无新表）。
- `tests/test_bare_metals_guards.py` → 原样保留。

### 前端验证（Test Work，非前端实现）

| # | 测试 | 说明 | AC |
|---|---|---|---|
| **T-FE-09** | 回归：`BareMetalListPage` 在 `clusterId` 限定下，Empty（200 空集）与 Not Found（父 404，Error 态）渲染不同状态；Empty 不触发全局会话失效 | 复用/补强既有 `bareMetalListPage.spec.ts` | AC-08、AC-09、AC-10 |
| **T-FE-10** | 回归：`ClusterDetailPage`「查看裸金属」→ 进入 `clusterId` 限定的成员列表 | 复用既有 | AC-01 |
| **T-FE-11** | 负向：Cluster 视角视图源码不含 restore / undelete / 回收站 / `include_deleted` 入口 | 静态/组件 | AC-13、AC-14 |

---

## Technical Decisions

### CONFIRMED
- **ADR-0003 §2（ACCEPTED）**：`id` 为规范路径；只读名称别名包含 `GET /api/clusters/by-name/{cluster_name}` 与 `GET /api/clusters/by-name/{cluster_name}/bare-metals`；`{cluster_name}` 大小写敏感；已删 Cluster 不参与名称解析。
- **ADR-0003 §6 / `api-conventions.md §7`**：父资源不存在/已删 → `404`；父存在但无子 → `200` + `items==[]`；前端必须区分渲染。
- **ADR-0004**：软删单一写入路径；读取统一经 `active_filter` / `select_active`；无 undelete。
- **ADR-0005 / F013**：所有 `/api/*`（除登录）要求认证；无白名单。
- **F002 契约 §3.2**：`GET /api/bare-metals?cluster_id=` 的 canonical 语义与 `Page[BareMetalRead]` 信封/字段集合。
- R-QUERY-003 归 **F010**；F009 不建模、不预留（§15）。

### REQUIRED
1. alias 必须复用 F002 的 `list_bare_metals`（含其父存在性检查）作为唯一子列表路径；`cluster_views` 模块不得出现任何 `deleted_at` 表达式或第二条活跃过滤谓词（ADR-0004）。
2. 判定顺序固定：先名称解析（未命中 → `404`），后子列表（空 → `200` Empty）。
3. alias 的响应信封与字段集合必须逐字段等于 F002 列表；以 guard（G-009-3）固定。
4. 无数据库变更；名称解析与成员读取只能复用既有索引/约束。
5. `EXPECTED_GET_ROUTES` 必须演进（追加而非替换）；不得删除既有断言。
6. 边界 guard（G-009-2 ~ G-009-6）必须存在。
7. 所有新路径位于 `/api` 前缀下，不新增白名单。

### PROPOSED
1. 交付面 = 复用 + 别名。
2. 交付 `GET /api/clusters/by-name/{cluster_name}/bare-metals`。
3. 模块布局：新建 `backend/app/cluster_views/`（`router.py` + `service.py`）。
4. alias 支持分页，默认 50 / 上限 200。
5. 契约落点：新建 `docs/api/f009-cluster-resource-view.md`。
6. layers：`database: false` / `backend: true` / `frontend: false`。
7. 前端验证归属：Test agent 在 `frontend/tests/**` 以回归测试固定。

### OPEN（非阻塞）
1. NQ-1（Cluster 级状态汇总/计数）：F009 不实现、不承诺。
2. NQ-4 / PROPOSED-2（展示字段范围）：沿用 F002 `BareMetalRead` 全字段集合。
3. 独立的「Cluster 为主语成员页 / 内联区」：属展示决策，需产品确认。
4. 前端路由方案（`vue-router`）：仍不引入。
5. `by-name` 空名称段 / 缺失段等边界未定义，不承诺。

---

## Risks

| # | 风险 | 缓解 |
|---|---|---|
| R1 | alias 被实现为自写 `deleted_at IS NULL` 的第二条软删路径 | REQUIRED #1 + G-009-5 + 强制委托 `list_bare_metals` |
| R2 | alias 与 canonical 语义漂移 | G-009-3 断言两者 schema 相等；T-01/T-06/T-08/T-17 深等断言 |
| R3 | 交付 alias 被误视为新领域能力而顺手加字段/状态 | G-009-2 ~ G-009-4 |
| R4 | 既有 `EXPECTED_GET_ROUTES` 被删旧换新 | REQUIRED #5 + G-009-1 |
| R5 | 并发软删下返回已删 Cluster 的成员 | 单事务内委托 `list_bare_metals` 的父活跃复检；T-07 |
| R6 | 前端出现第二套 Cluster 视角视图 | F009 不新增 `frontend/src/**` |

---

## Constraints

1. 不新增领域对象 / 字段 / 关系 / 状态 / 唯一性规则；不越界到 R-QUERY-003 的资源类型（§15）。
2. 无数据库变更：不改 `0001`/`0002`/`0003`；不新增表/列/索引/`COLLATE`/CASCADE/触发器/migration。
3. 软删单一路径：不改写 `deleted_at`；不引入第二条 `deleted_at IS NULL` 谓词；不提供 undelete / restore / 回收站 / `include_deleted` / 批量。
4. 不改既有已批准契约语义；alias 契约唯一正文在 `docs/api/f009-cluster-resource-view.md`。
5. 不引入新框架 / 新依赖 / 新中间件 / `vue-router` / EAV / 通用表 / STI / ORM 多态 / JSONB。
6. 前端不得重复实现业务守卫（§21）。
7. 新端点必须在 `/api` 前缀下，不新增白名单。
8. 既有 guard 只增不减；`EXPECTED_GET_ROUTES` 追加而非替换。
9. `cluster_views` 模块不得定义任何路由/字段/参数涉及 NIC / IP / VM / Container / Service，也不得为其预留占位。

---

## Open Technical Questions

### Blocking

**无。**

### Non-blocking
1. NQ-1（状态汇总/计数）。
2. NQ-4 / PROPOSED-2（展示字段范围）。
3. 独立 Cluster 成员页 / 内联区。
4. `by-name` 空段边界。
5. 前端路由（`vue-router`）引入时机。

---

## Implementation Layers

```text
database: false
backend:  true
frontend: false
```

- **database: false** — 无 schema 变更。
- **backend: true** — 新增 `backend/app/cluster_views/**`、`main.py` 挂载、`EXPECTED_GET_ROUTES` 演进、边界/一致性 guard 与全测试集。
- **frontend: false** — F002 已交付的集群限定 `BareMetalListPage` 即 F009 的 Cluster 视角视图；前端义务仅为验证。

**文件所有权**：Backend = `backend/**` + `tests/**`；Test = `tests/**` + `frontend/tests/**`（仅测试）；共享 `docs/**` 由协调器统一落盘。

---

## Implementation Order

```text
Architecture + API Contract（均 READY）
  └─ Backend（cluster_views 模块 → main.py 挂载
              → EXPECTED_GET_ROUTES 演进 + 边界/一致性 guard
              → 全测试集）
        ↓ 所有必需实现分支完成
     Tester（含前端回归）→ Reviewer
```

- `database: false`、`frontend: false`，故无 Database / Frontend 分支；Backend 完成后进入 Tester → Reviewer。

---

## Verification Strategy

1. **契约层**：alias 与 canonical 深等断言；`404` vs `200` Empty；大小写敏感；中文往返。
2. **软删读取侧**：绕过应用层预置 `deleted_at` 后，alias 名称解析不命中、成员列表排除；`DELETE` 后消失。
3. **一致性**：判定顺序与并发稳定；T-06/T-07/T-08。
4. **边界**：G-009-2 ~ G-009-6。
5. **认证**：未认证访问 alias → `401`。
6. **Guard 演进**：`EXPECTED_GET_ROUTES` 追加；既有断言零删除。
7. **前端回归**：`bareMetalListPage.spec.ts` / `appBareMetalNavigation.spec.ts` 保持全绿并补强。
8. **工程门禁**：lint 通过；既有测试全绿；静态 guard allow-list 不退化。

---

## Handoff Status

```text
READY FOR IMPLEMENTATION
```

无阻塞问题。API Contract Status = `READY`。

GIT: NONE
