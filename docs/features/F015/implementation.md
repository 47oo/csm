# F015 Audit 查询、已删除对象管理与系统功能 — IMPLEMENTATION 阶段记录

- **状态**：BACKEND COMPLETE；FRONTEND COMPLETE
- **Contract**：docs/api/F015.md v1（READY，Architect 2026-10-14）
- **Database**：docs/database/f015-audit-admin.md v1（NOT_REQUIRED，DB-D167–D172）
- **D01/D02**：无变更
- **角色**：Backend（backend/**）；Frontend（frontend/**）

## 1. Backend 改动文件清单
新增：`app/api/v1/audit.py`（`GET /api/v1/audit`，AUDIT_READ）、`deleted.py`（`GET /api/v1/deleted`，VIEW_DELETED）、`users.py`（`/api/v1/users` list/detail/create/patch，USER_ADMIN）；`app/schemas/{audit,deleted,users}.py`；`app/services/{audit_query,deleted,user}.py`；`tests/integration/{test_audit_query,test_deleted,test_users,test_f015_constraints}.py`、`f015_helpers.py`。
修改：`app/services/audit.py`（登记 `"user":("username","role","status")`）；`app/api/v1/router.py`（挂载）。

## 2. Contract/设计符合性
- `/audit`：operator trim+小写归一精确、object_type 9 类含 user、object_id 须与 object_type 同现、action、created_from/to 闭区间（from>to 422）、分页、sort=created_at、order、AND、同刻 id 升序、空结果 200、只读幂等；AuditRow 不含密码/令牌。
- `/deleted`：8 类 `deleted_at IS NOT NULL` UNION ALL、object_type 过滤、分页、sort=deleted_at、同刻 type/id 升序；DeletedItem 含 label/cluster/version/deleted_at；恢复复用各域既有端点（无统一写端点）。
- `/users`：list(role/status/q/sort/order)、detail(非 UUID→404)、create(201，username 归一+正则、password 8–128、argon2、重复 409 unique_conflict)、PATCH(version 乐观锁、role/status 至少一个、额外字段 forbid、角色即时生效、DISABLED 同事务删 user_sessions、旧 Cookie 401 AUTH_REQUIRED/登录 401 AUTH_INVALID_CREDENTIALS)；无 DELETE/改密/注册；UserRow 永不含 password_hash。
- 不新增 error code/reason；401→403→422 顺序（依赖注入在参数校验前）；database=false，迁移链单 head `0013_search_indexes` 不变。
- 账号审计 `object_type="user"`，白名单无密码，同事务；停用不改旧审计、历史身份保留。

## 3. Migration 影响
无（NOT_REQUIRED）；未新增索引，未改 audit_logs 结构；head 保持 `0013_search_indexes`。

## 4. Frontend 改动文件清单
新增：`api/{audit,deleted,users}.ts`；`components/auditQueryForm.ts`；`components/AuditQueryPanel.tsx`、`AccountManagementPanel.tsx`、`DeletedObjectsPanel.tsx`；`pages/AuditPage.tsx`、`pages/SystemPage.tsx`。
修改：`pages/HomePage.tsx`（按 permissions 显示 Audit/System 导航）；`index.css`；`scripts/smoke-client.mjs`（+22 F015 用例）。
恢复路由：`restoreDeletedItem` 按 object_type 逐一映射 8 域 `POST /api/v1/{object}/{id}/restore?version=`；失败 reason 明确呈现；无 Audit 修改/删除/清空 UI。

## 5. 验证证据
- Backend（真实 PG，容器内安装依赖）：`pytest tests -q` → **565 passed, 1 skipped**（skip=环境性 superuser）；F015 专属 36 passed。覆盖权限矩阵/401先于403、AND/非法参数/时间闭区间/分页排序/空结果/只读幂等、append-only DB UPDATE/DELETE 被拒、无 Audit 变更端点、8 类已删聚合/标签/cluster/version、恢复复用、用户创建/重复 409/角色即时/停用删会话+401/启用/无注册无删除、PATCH 乐观锁、账号审计白名单无密码/停用不改旧审计/历史身份保留、FK RESTRICT/无 enum CHECK/迁移 head 与索引存在性。
- Frontend：`typecheck` 通过；`build` 通过（91 modules）；`smoke:client` → **264 passed, 0 failed**（+22）。

## 6. 未验证项
- PATCH /users 乐观锁未做双连接并发用例（契约未要求；恢复并发归各域既有 TE）。
- 真实 API 端到端集成与浏览器 E2E（机制级 + 真 PG；集成由 TEST 阶段验证）。
- 密码长度 8–128、q 上限 64、naive ISO-8601 视为 UTC：Contract §8 可实施默认。
- F015-OPEN-1（最后一个 ACTIVE ADMIN 保护）：本期不保护（风险 NOTE）。