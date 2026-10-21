# F026 实现报告

- Feature：F026 集群范围授权基座与 ADMIN 授权管理
- 阶段：IMPLEMENTATION
- 依据：`docs/api/F026.md` v1；F026 architecture v1；`docs/database/f026-cluster-authorization.md` v1；TD-1
- 结论：Backend COMPLETE；Frontend COMPLETE（本地验证通过，待独立 TEST）

## 1. Backend

### 1.1 数据与迁移

- 新增 `backend/app/models/user_cluster_authorization.py`（不继承 `SoftDeleteMixin`；无 `deleted_at`/`version`；部分唯一索引 `(user_id, cluster_id) WHERE revoked_at IS NULL`；两个 CHECK）。
- `models/__init__.py` 注册。
- 新增 `backend/alembic/versions/0015_user_cluster_authorizations.py`：
  - `down_revision="0014_api_keys"`，单 head；建表 + 4 FK RESTRICT + 2 CHECK + 3 索引（含部分唯一）；
  - `BEFORE UPDATE` 归属不可变/撤销单向触发器；`BEFORE DELETE` 禁止物理删除触发器；
  - 回填既有非 ADMIN × 既有 Cluster（含软删、DISABLED）；`NOT EXISTS` + `ON CONFLICT DO NOTHING` 幂等；`granted_by=NULL`；不写业务 Audit；
  - 迁移内计数断言（ADMIN=0、missing=0、duplicate_active=0；首次回填 total=active=期望乘积），失败整体回滚；
  - downgrade 逆序删除。

### 1.2 授权服务与端点

- 新增 `app/core/access_scope.py`：`AccessScope`（unrestricted / cluster_ids / allows / cluster_predicate / sorted_cluster_ids）、`resolve_access_scope`、`get_access_scope`（request.state 同请求复用，不跨请求缓存）。F026 **未**在既有业务路由引用。
- 新增 `app/services/cluster_authorization.py`：列表（status/cluster_id/q/sort/order/分页、同 filters 的 total、join 已软删 Cluster）、授予（账号存在且非 ADMIN、Cluster 存在且未软删、同事务 Audit、唯一冲突 409）、撤销（404/409、条件 UPDATE、保留历史、同事务 Audit）。
- 新增 `app/schemas/cluster_authorizations.py`：`ClusterAuthorizationRow`/UserRef/ClusterRef/ListResponse/Envelope/CreateRequest（`extra=forbid`）。
- 新增 `app/api/v1/cluster_authorizations.py` 并挂载：
  - `GET /api/v1/users/{user_id}/cluster-authorizations`
  - `POST /api/v1/users/{user_id}/cluster-authorizations`
  - `POST /api/v1/cluster-authorizations/{authorization_id}/revoke`
  - 全部 `USER_ADMIN`；路径非 UUID/不存在 404；语义/请求体非法 422；未知查询参数 422；401→403→422→404→409。
- `services/audit.py` 增加 `user_cluster_authorization` 白名单（6 键）；`schemas/audit.py` 增加 `AuditObjectType` 值。
- 同步 `docs/api/F002.md` v3（`already_granted`、`already_revoked` 扩义）与 `docs/api/F015.md` v3（object_type 加法）。

### 1.3 既有测试的迁移 head 维护

新增 `0015` 后，既有约束/迁移测试中硬编码的 head `0014_api_keys` 更新为 `0015_user_cluster_authorizations`（仅 head/current 断言；F017 增量测试仍从 `0013` 窄降级验证其对象）。未修改任何 DONE Feature 的交付证据或业务断言。

## 2. Frontend

- 新增 `frontend/src/api/clusterAuthorizations.ts`：三端点 client、类型、409/422/403/404 错误描述。
- 新增 `frontend/src/components/ClusterAuthorizationPanel.tsx`：账号列表（搜索/分页上限提示）、授权列表（状态过滤、effective、已软删 Cluster 提示、授予人/撤销人）、授予 Modal（Cluster 候选来自 `GET /clusters?deleted=exclude`，排除已有效授权，50 条提示）、撤销 `ConfirmDialog`（danger、后果与历史保留说明、409 提示刷新）、Loading/Empty/Error 三态、恒定 InfoState（ADMIN 不建行、F027 前范围未对既有数据生效）。
- `SystemPage.tsx` 新增「集群授权」Tab（`USER_ADMIN` 门控）。
- `scripts/smoke-client.mjs` 新增 F026 机制级用例（列表 URL/方法、授予/撤销路径与请求体、错误描述）。

## 3. 本地验证

真实 PostgreSQL 16（docker 临时库 `csm_test`）：

```
python3 -m pytest -q   # 708 passed, 2 skipped (16m)
```

- 新增 F026 测试 `tests/integration/test_cluster_authorizations.py`：8 passed。
- 覆盖：权限矩阵/401 先于 403、授予/列表/重复 409/撤销/重授/Audit、ADMIN/软删/INACTIVE 目标校验、软删/恢复/软删期间撤销、AccessScope 精确/空集/ADMIN/API Key 继承/下一请求即时、列表过滤与非法参数、迁移 up/down/up/回填计数/幂等/触发器/部分唯一。
- 跳过：F016 acceptance module（既有开关）；DB-D11 非 superuser 用例（测试库为 superuser，既有原因）。

Frontend：

```
npm run typecheck       # pass
npm run build           # pass (vite build)
npm run smoke:client    # 322 passed, 0 failed
```

## 4. 偏差与说明

- Database 签核的 DB-D407 以全量 `(user_id)` 索引取代 architecture 草案的部分索引；不改变接口。
- 回填不写业务 Audit（A-3，Contract §9.7），以迁移计数断言与 T99 为证据。
- F026 **未**对既有业务端点施加范围过滤；F027 才会端到端生效。F026 合并后至 F027 合并前，非 ADMIN 可见范围仍是现状。
- 迁移测试需串行；临时 PostgreSQL 容器与前端 `node_modules` 软链为本地测试环境，不入仓。

## 5. 未验证 / 后续

- 独立 Tester 的 TEST Gate（TD-2 复核后执行）与 Reviewer 正式 Review 尚未进行。
- F028 承接真实 Compose 的 T85–T99 端到端与 T01–T84 关键回归。