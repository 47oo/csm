# F026 集群范围授权基座与 ADMIN 授权管理 — Architecture

- 状态：READY FOR DESIGN（交 Database / Test Design；未放行编码）
- 版本：v1
- 需求：`docs/product/requirements-v3.md` revision 11（§3、§5、§21–§25、§27、§28、§31 T85–T99、§32、§35.1–§35.3）
- 批准：`docs/project/proposals/CHG-010-cluster-access.md`；plan_revision 14（用户 2026-10-21「批准并实施」）
- Product：`docs/features/F026/product.md`（A1–A33）
- 既有设计：D01 v11；F002 / F015 / F017 Contract 与 Database 设计

## 1. 方案摘要与边界

在既有「基础角色 + Cookie/API Key 认证」之上新增：

1. 新表 `user_cluster_authorizations`（账号 × Cluster，授予/撤销时间与操作者，撤销保留历史，有效行唯一）；
2. Alembic `0015_user_cluster_authorizations` + 幂等回填（既有非 ADMIN × 既有 Cluster，含软删）；
3. 三个仅 `USER_ADMIN` 的端点：按用户查询 / 授予 / 撤销；
4. Audit：授予 `CREATE`、撤销 `UPDATE`，与业务写同事务；
5. `AccessScope` + 独立依赖 `get_access_scope`，**F026 不解引用**；
6. System 页「集群授权」Tab（仅 ADMIN），复用 Ant Design / Tailwind 基线与 `ConfirmDialog`。

**不做**：对既有业务域端点施加范围过滤（F027）；新增角色/权限项；资源实例级授权；组织/租户；API Key scope-down；物理删除授权历史；修改 F001–F025 行为与证据。

**F026 ↔ F027 边界**：

| 项 | F026 | F027 |
| --- | --- | --- |
| `AccessScope` 类型 | 交付 `unrestricted` / `cluster_ids` | 消费，不重定义 |
| 解析入口 | `app/core/access_scope.py` + `get_access_scope` | 不得新增第二套解析 |
| 谓词 | `cluster_predicate(column)`：unrestricted→true，空集→false，否则 IN | 列表与 total 复用同一谓词 |
| 生命周期 | 逐请求解析、同请求稳定、不跨请求缓存 | 不得引入缓存 |
| 解引用 | **无**（不注入既有路由） | 读写/聚合/搜索/导入全路径一次性接入 |
| 错误 | 不产生越权 404 | 越权对象统一 404 |

判据：F026 合并后 `git grep "get_access_scope\|AccessScope" backend/app/api backend/app/services` 只命中 `core/access_scope.py` 与 F026 测试。

## 2. 数据行为（Database 签核 CHG010-BQ18）

表 `user_cluster_authorizations`，**不继承 `SoftDeleteMixin`、无 `deleted_at`**（避免 `db.py` 全局软删谓词注入）：

| 列 | 行为 |
| --- | --- |
| `id UUID` | PK，`gen_random_uuid()` |
| `user_id UUID NOT NULL` | FK → users，`ON DELETE RESTRICT` |
| `cluster_id UUID NOT NULL` | FK → clusters，`ON DELETE RESTRICT` |
| `granted_at timestamptz NOT NULL DEFAULT now()` | 授予时间 |
| `granted_by UUID NULL` | FK → users RESTRICT；NULL = 迁移系统回填 |
| `revoked_at timestamptz NULL` | 撤销时间 |
| `revoked_by UUID NULL` | FK → users RESTRICT |

约束/索引：

- 部分唯一索引 `(user_id, cluster_id) WHERE revoked_at IS NULL`：有效行唯一，并发重复授予的唯一权威兜底。
- `CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))`；`CHECK (revoked_at >= granted_at)`。
- 索引 `(user_id) WHERE revoked_at IS NULL`（scope 解析主路径）；`(cluster_id)`（FK / 反查）。
- 归属列不可修改；撤销只允许单向写 `revoked_at`/`revoked_by`（建议 BEFORE UPDATE 触发器，Database 定）。
- 不新增 `version` 乐观锁列（无 PATCH，无读改写覆盖）。

生命周期：

- Cluster ACTIVE ⇄ INACTIVE：授权行与解析集合不变。
- Cluster 软删：行保留，解析 join `clusters.deleted_at IS NULL` 后移除。
- Cluster 恢复：行不变，自动重新生效；软删期间撤销的恢复后仍不生效。
- 新建 Cluster：无自动授权。
- ADMIN 降级：立即按既有行解析（可能为空）；升级为 ADMIN：不受限，行保留不参与。
- 账号停用：行不变；无法认证；启用后按既有行解析。
- 撤销后重新授予：新行，旧行保持已撤销。

回填（迁移内）：

- `{users role<>'ADMIN'} × {clusters}`，含软删 Cluster 与 DISABLED 账号；ADMIN 零行。
- `INSERT … SELECT … ON CONFLICT (user_id, cluster_id) WHERE revoked_at IS NULL DO NOTHING`，幂等。
- 迁移内计数断言：有效行 = 非 ADMIN 用户数 × Cluster 数，失败即 upgrade 报错。
- 不写业务 Audit（A-3 默认）；`granted_by=NULL`；不改变 users/clusters/audit_logs。
- `downgrade` 丢弃本表；生产回滚用全库备份（DB-D7）。

AccessScope 解析：

```
ADMIN -> AccessScope(unrestricted=True, cluster_ids=frozenset())
非 ADMIN ->
  SELECT DISTINCT a.cluster_id
  FROM user_cluster_authorizations a
  JOIN clusters c ON c.id=a.cluster_id AND c.deleted_at IS NULL
  WHERE a.user_id=:uid AND a.revoked_at IS NULL
```

非 ADMIN 零授权 = 空 frozenset（默认拒绝）。同一请求内复用 `request.state.access_scope`。

## 3. Backend 设计

### 3.1 AccessScope（D-4）

新文件 `app/core/access_scope.py`：

```python
@dataclass(frozen=True)
class AccessScope:
    unrestricted: bool
    cluster_ids: frozenset[UUID]
    def allows(self, cluster_id) -> bool
    def cluster_predicate(self, column)  # true()/false()/in_(...)
    def sorted_cluster_ids(self) -> list[UUID]

def resolve_access_scope(db, operator) -> AccessScope
def get_access_scope(request, operator=Depends(get_current_operator), db=Depends(get_db)) -> AccessScope
```

**不修改** `get_current_operator`、`Operator`、`require_permission`。不缓存、不入 Session、不写 Token。F026 无生产路由依赖 `get_access_scope`。

### 3.2 授权 Service 与事务

新文件 `app/services/cluster_authorization.py`：

- `list_authorizations(...)`：只读；status/cluster_id/q/sort/order/page/page_size 白名单；`total` 与列表同 filters；`order_by(sort, id.asc())` 稳定。
- `grant(...)`：单事务：校验（用户存在且非 ADMIN、Cluster 存在且未软删）→ INSERT → `audit.record` → commit。`IntegrityError` → rollback → 409 `already_granted`。
- `revoke(...)`：单事务：SELECT 404；已撤销 → 409 `already_revoked` 且不写 Audit；条件 `UPDATE ... WHERE id=:id AND revoked_at IS NULL`，rowcount=0 → 409；成功后 `refresh` + Audit → commit。
- 视图 join users（username/role/status）与 clusters（code/name/status/deleted_at，含软删），避免 N+1。
- 事务归属沿用 `get_db` 不提交、Service commit/rollback（与 F015/F017 一致）。

### 3.3 API（D-1/D-2）

新文件 `app/api/v1/cluster_authorizations.py`，挂载到 `api_v1_router`。

| 方法 | 路径 | 权限 | 结果 |
| --- | --- | --- | --- |
| GET | `/api/v1/users/{user_id}/cluster-authorizations` | `USER_ADMIN` | 200 列表 |
| POST | `/api/v1/users/{user_id}/cluster-authorizations` | `USER_ADMIN` | 201 授予 |
| POST | `/api/v1/cluster-authorizations/{authorization_id}/revoke` | `USER_ADMIN` | 200 撤销 |

不提供 PATCH/DELETE/detail/batch/restore。

列表参数：`status=ACTIVE|REVOKED`、`cluster_id`、`q`（Cluster code/name 子串，trim 后空或 >64 → 422）、`page>=1`、`page_size 1..100`、`sort=granted_at|revoked_at`、`order=asc|desc`；同刻 `id` 升序。空结果 200 `{items:[],page,page_size,total:0}`。

响应 `ClusterAuthorizationRow`：

`id`、`user{id,username,role,status}`、`cluster{id,code,name,status,deleted_at}`、`status=ACTIVE|REVOKED`、`effective`（有效且 Cluster 未软删）、`granted_at`、`granted_by`（nullable）、`granted_by_username`（nullable）、`revoked_at`、`revoked_by`、`revoked_by_username`。

授予请求：`{"cluster_id": "<uuid>"}`，`extra=forbid`；成功 201 `{"cluster_authorization": Row}`。

撤销：无请求体；成功 200 `{"cluster_authorization": Row}`；已软删 Cluster 上的有效授权允许撤销。

错误顺序：401 → 403 → 422 → 404 → 409。

- 401 `AUTH_REQUIRED`：未认证/失效 Key/停用账号。
- 403 `FORBIDDEN{reason:"permission"|"csrf"}`：非 ADMIN / CSRF。
- 422 `VALIDATION_ERROR{fields}`：`cluster_id` 非 UUID/不存在/已软删；目标账号为 ADMIN；分页/排序/q/未知字段非法。
- 404 `NOT_FOUND`：路径 `user_id`（E1/E2）或 `authorization_id`（E3）非 UUID/不存在。
- 409 `CONFLICT`：`already_granted` / `already_revoked`。

> P-1 分解：**路径对象不存在 → 404；请求体/语义 → 422**。即 E1/E2 的路径 user 不存在 → 404；目标账号为 ADMIN → 422；Cluster 软删/不存在 → 422。Contract 记录该口径。

### 3.4 权限 / Audit

- 三端点复用 `require_permission(Permission.USER_ADMIN)`，不新增 Permission / ROLE_PERMISSIONS。
- Audit `object_type="user_cluster_authorization"`、`object_id=row.id`；授予 CREATE、撤销 UPDATE（不是 DELETE）；白名单 `user_id, cluster_id, granted_at, granted_by, revoked_at, revoked_by`；时间 ISO-8601 UTC；无敏感字段；与业务同事务。
- 更新 `services/audit.py` 的 `AUDITABLE_FIELDS`；`schemas/audit.py` 的 `AuditObjectType` 加 `user_cluster_authorization`（否则审计查询 422）。
- 文档 errata：`docs/api/F002.md` → v3 增加 `already_granted`，扩展 `already_revoked` 语义；`docs/api/F015.md` → v3 增加 object_type；F017 无变更。

### 3.5 迁移 / 模型

- `backend/alembic/versions/0015_user_cluster_authorizations.py`，`down_revision="0014_api_keys"`，单 head；手写 DDL（部分唯一索引/`gen_random_uuid()`）。
- `backend/app/models/user_cluster_authorization.py` 不继承 SoftDeleteMixin；`models/__init__.py` 注册。

### 3.6 不改变既有端点

- 不改 auth/permissions；不改既有 services；无范围过滤注入；仅 `GET /audit` object_type 枚举加法。
- 回归：真实 PG 全量 `pytest backend/tests`；前端 typecheck/build/smoke；F028 做 Compose 级。

## 4. Frontend 设计

- `SystemPage.tsx` 新增 `authorizations` Tab「集群授权」，门控 `USER_ADMIN`。
- 新增 `components/ClusterAuthorizationPanel.tsx` + `api/clusterAuthorizations.ts`。
- 复用 `controls`、`feedback`、`surfaces`、`ConfirmDialog`、`api/client`；不新增路由库/状态库/组件库。
- 左：用户列表（`GET /users`，role/status/q/分页）；ADMIN 行提示「不受集群范围限制」，禁用授予。
- 右：授权列表（E1），列 Cluster code/name/status、授权状态、effective（Cluster 已删提示「授权暂不生效」）、授予/撤销时间与人；过滤 status/q；服务端分页。
- 授予：AntD Modal + Cluster 搜索选择（`GET /clusters?deleted=exclude&q=`，取前 50 并提示不静默截断）；前端隐藏已有效授权；成功刷新；422/409/403/404/500 内联呈现，不自动重试。
- 撤销：`ConfirmDialog(danger, okText="确认撤销")`，含账号、Cluster、后果与历史保留说明；提交中不可重复；409 `already_revoked` → 关闭并刷新提示。
- Loading/Empty/Error 三态显式；Empty 文案说明默认拒绝不会回退全量；Error 不伪装为空。
- 恒定 `InfoState`：ADMIN 不受限且不建行；F027 前范围尚未对既有业务数据生效。
- 前端隐藏不替代服务端鉴权。

## 5. Layers / Contract / 文件规划

layers：database=true、backend=true、frontend=true；api_required=true。

Contract：`docs/api/F026.md`（DRAFT→CONTRACT Gate 定稿），含通用约定、Row 字段、列表基线、三端点、错误/reason、权限、Audit、DB 依赖、业务边界、F002 v3 / F015 v3 errata、签核与待决。

文件：

- DB：`docs/database/f026-cluster-authorization.md`、`backend/alembic/versions/0015_user_cluster_authorizations.py`
- BE：`models/user_cluster_authorization.py` + `models/__init__.py`、`core/access_scope.py`、`services/cluster_authorization.py`、`services/audit.py`、`schemas/cluster_authorizations.py`、`schemas/audit.py`、`api/v1/cluster_authorizations.py`、`api/v1/router.py`
- FE：`api/clusterAuthorizations.ts`、`components/ClusterAuthorizationPanel.tsx`、`pages/SystemPage.tsx`
- 文档：`docs/api/F026.md`、`docs/api/F002.md`（v3）、`docs/api/F015.md`（v3）
- 测试：`backend/tests/integration/test_cluster_authorizations*.py`、`test_f026_migrations.py`、`test_access_scope.py`、`test_f026_tester_acceptance.py`

## 6. Test Work（F026）

验收映射：A1–A33 → T-F026-01…34（覆盖：授予/重复/并发、ADMIN 拒绝、撤销/重授、权限/401-403、分页过滤、404/409、软删/恢复/INACTIVE、新建 Cluster、降级/升级、停用/启用、scope 精确/空集/ADMIN/同请求复用/跨请求即时、既有回归、迁移 up/down/up、回填计数/幂等/不改变业务数据、审计同事务/可查询/无敏感、无 DELETE 语义）。

策略：

- 真实 PostgreSQL 必需（`TEST_DATABASE_URL`；`pg_engine`/`committed_engine`/`db_session`/`alembic_runner`）；SQLite/Mock 不作约束证据。
- 并发：两真实连接同时授予同一 `(user,cluster)`，断言最终有效行 ≤1、失败方 409、无 Audit 残留。
- 迁移/回填：用例内 `downgrade("0014_api_keys")` → 预置 users/clusters（含软删/DISABLED）→ `upgrade head` → 断言；结束恢复 head。
- 软删：同一用例完成「软删 → 撤销 → 恢复」三段断言。
- 审计：直接查 `audit_logs` + 通过 `GET /audit` 覆盖 A32。
- 前端：typecheck/build/smoke；A9–A11 的浏览器/Compose 证据归 F028。
- F028 承接：T85–T99 端到端（T87/T88/T89/T91/T94/T95/T97/T98）、T01–T84 关键回归、真实 Compose。

## 7. 技术决策

- D-1 端点：用户子资源 GET/POST + `POST /cluster-authorizations/{id}/revoke`；无 PATCH/DELETE/detail/batch。
- D-2 reason：新增 `already_granted`；复用 `already_revoked`；路径 404 / 语义 422；顺序不变。
- D-3 Audit：`user_cluster_authorization`；CREATE/UPDATE；白名单 6 键。
- D-4 AccessScope：新模块 + 独立依赖 + `request.state`；不改认证 seam。
- D-5 撤销 UI：`ConfirmDialog` 危险样式 + 后果说明。
- D-6 回填：迁移内单条 `INSERT…SELECT…ON CONFLICT DO NOTHING` + 计数断言；不写 Audit；`granted_by=NULL`。

A-1：停用账号保留授权、无法认证、启用后恢复、允许授予、回填含 DISABLED。A-2：升级 ADMIN 行保留不参与，降级按既有行。A-3：回填不写审计（PROPOSED，Contract 记录）。

## 8. 待核对

Database：表/列/类型、部分唯一索引与 `ON CONFLICT` 推断、索引与 EXPLAIN、CHECK、归属不可变触发器、迁移内断言、downgrade 边界、单 head、audit 无 Schema 变更。

Test Design：迁移夹具顺序、并发双连接、预置数据最小集、前端验证方式。

Product/用户：P-1 路径/语义错误分解、P-2 回填不写 Audit、P-3 A-1/A-2 记录（Contract 关闭）。

风险：误继承 SoftDeleteMixin；回填口径错误；F026 误引入范围过滤；AccessScope 缓存；audit 枚举加法被忽略；前端误称范围已生效。

## 9. Gate 声明

本阶段只读分析，未修改文件，不放行编码。Database / Test Design 核对后，Contract Gate 签核 `docs/api/F026.md` 与 F002 v3 / F015 v3 errata，再进入实现。

**Status：READY FOR DESIGN**
## 10. 最终设计签核（CONTRACT / FINAL DESIGN）

- 状态：READY FOR IMPLEMENTATION
- 签核者：Architect；日期：2026-10-21；覆盖 Feature：F026
- 契约：`docs/api/F026.md` v1（READY）；`docs/api/F002.md` v3、`docs/api/F015.md` v3（加法 errata）；F017 无变更
- 上游依据：requirements revision 11（§3/§5/§21–§23.2/§24/§25/§27/§28/§31 T85–T99/§32/§35.1）；CHG-010；plan_revision 14；F026 product v1；architecture v1；`docs/database/f026-cluster-authorization.md` v1（DB-D401–D420，含 DB-D407）；F026 test-report TD-1
- 核对结论：需求条款、Product 验收、Architecture 决策、Database 设计、TD-1 判据与 Contract 三端点/字段/错误字面一致；事务边界（业务写 + Audit 同事务）、并发保护（部分唯一索引 + 条件更新）、生命周期（软删/INACTIVE/停用/升降级）无冲突。无阻塞。
- 关闭项：OBS-F026-1（DB-D407 全量 `(user_id)` 索引取代部分索引，无接口影响）；OBS-F026-2（`docs/api/F026.md` v1 定稿）；OBS-F026-4（P-1 字面化：路径 404 / 语义 422）；A-1/A-2/A-3 记录于 Contract §9.3/§9.1/§9.7。
- 放行：自本签发起进入实现；实现以 `docs/api/F026.md` v1（含 F002 v3 / F015 v3 errata）为唯一契约判据，TD-2 复核不改变已冻结字面。

**Status：READY FOR IMPLEMENTATION**
