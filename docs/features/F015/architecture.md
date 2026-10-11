# F015 Audit 查询、已删除对象管理与系统功能 — ARCHITECTURE 阶段报告

- **Task**：F015（FEATURE，P1，M6 检索、导入与系统功能，deps F002–F012）— Architect，Feature 设计模式
- **阶段**：ARCHITECTURE；**结论**：`READY FOR DESIGN`（2026-10-14）
- **Basis**：requirements-v3.md revision 3（§21、§22、§23、§25、§28、§31 T24/T25/T26/T36/T41、§35.2 Q07-A/Q10-B、§35.3 D01/D02）；`docs/features/F015/product.md`（A1–A31、I-1–I-15、OPEN O-1–O-8）；`docs/api/F002.md` v1（§1.1–§1.3、§2.1、§3、§5）；`docs/api/F003.md` v2 §6.5/§6.6/§6.7/§8；各域 `docs/api/F004.md`/`F007.md`/`F008.md`/`F009.md`/`F010.md`/`F011.md`/`F012.md`；`docs/database/f002-auth.md` v1（DB-D13–D19）；`docs/database/f003-cluster.md` v2 §3（DB-D27–D29）；实现 `backend/app/services/audit.py`、`app/services/auth.py`、`app/core/permissions.py`、`app/core/auth.py`、`app/api/v1/auth.py`、`app/services/cluster.py`、`app/core/errors.py`、`app/cli/bootstrap_admin.py`、`app/models/{user,audit_log,session,base}.py`；`.pi/skills/data-integrity/SKILL.md`。DR 接续 F014 DR-212，自 **DR-213** 起。

## 1. 方案摘要

在已交付资源域之上新增三项 ADMIN 系统能力，全部挂同一 `api_v1_router`，不新增业务实体、字段、状态或写入路径语义：

1. **完整 Audit 查询**（§22/§25）：`GET /api/v1/audit`，仅 `AUDIT_READ`；只读消费既有 `audit_logs`，支持操作者/对象类型/对象 ID/action/时间范围过滤、分页、排序。
2. **已删除对象统一查看**（§21）：`GET /api/v1/deleted`，仅 `VIEW_DELETED`；跨 8 类对象聚合 `deleted_at IS NOT NULL`；**恢复不新增统一写端点**，前端按 `object_type` 复用各域既有 restore（O-3）。
3. **用户与账号管理**（§23）：`/api/v1/users`（list/detail/create/patch），仅 `USER_ADMIN`；停用即时失效会话；无自行注册、无物理删除、无改密。
4. **System / Audit 页面**（§28）：Audit 独立页；System 页承载账号管理与已删除对象管理入口。

### 1.1 边界
- 不改 F003–F012 已交付语义（I-15/A31）。
- 不实现 Audit 归档/清理/TTL、自行注册、Cluster 级 RBAC、改密/重置、首登强制改密。
- 不新增业务对象；`object_type="user"` 仅为既有 `audit_logs` 多态值登记。

## 2. Design Requirements（DR-213–DR-227，接续 F014 DR-212）

| ID | 决策 | 状态 |
| --- | --- | --- |
| DR-213 | 新增 `GET /api/v1/audit`（`app/api/v1/audit.py`）；仅 `AUDIT_READ`；只读、不写 Audit、幂等 | CONFIRMED+DESIGN |
| DR-214 | Audit 参数：`operator`（`operator_username` 精确匹配 trim+小写归一）、`object_type`（含 `user`）、`object_id`（须与 object_type 同现）、`action`、`created_from`/`created_to`（闭区间）、分页、`sort=created_at`、`order`；AND 组合；非法 422 | PROPOSED→CONTRACT + CONFIRMED |
| DR-215 | Audit 响应 `{items:[AuditRow],page,page_size,total}`；`AuditRow={id,action,object_type,object_id,operator_user_id,operator_username,before_data,after_data,created_at}`；同刻 `id` 恒升序；空结果 200 | PROPOSED→CONTRACT + CONFIRMED |
| DR-216 | 新增 `GET /api/v1/deleted`（`app/api/v1/deleted.py`）；仅 `VIEW_DELETED`；跨 8 类 UNION ALL 只读聚合；不新增统一恢复写端点 | CONFIRMED+DESIGN |
| DR-217 | 已删参数：`object_type`（8 类，不含 user）、分页、`sort=deleted_at`、`order`；`DeletedItem={object_type,object_id,version,label,cluster,deleted_at}`；同刻 type/id 升序；version 供既有 restore | PROPOSED→CONTRACT + DESIGN |
| DR-218 | 用户端点 `/api/v1/users`：list/detail/create(201)/patch；全部 `USER_ADMIN`；无 DELETE/改密/注册 | CONFIRMED+DESIGN |
| DR-219 | 账号规则：username 归一 `^[a-z0-9._-]{3,64}$`；重复 409 `unique_conflict`；password 创建必填 argon2 存 hash 不入响应/Audit；role 必填枚举；PATCH 按 version 乐观锁 | CONFIRMED + PROPOSED→CONTRACT |
| DR-220 | 停用/启用：DISABLED 同事务删该 user_id 全部 user_sessions；旧 Cookie 401 AUTH_REQUIRED、登录 401 AUTH_INVALID_CREDENTIALS；角色变更即时生效；无物理删除（FK RESTRICT） | CONFIRMED+DESIGN |
| DR-221 | 账号事件 Audit `object_type="user"`，CREATE/UPDATE，快照白名单 `{username,role,status}` 不含 password；同 Session 同事务 | CONFIRMED + PROPOSED→CONTRACT |
| DR-222 | `object_type` 值登记：既有 8 值 + `user`；`varchar(64)` 无 CHECK → 无需迁移 | CONFIRMED+DESIGN |
| DR-223 | 不新增 error code / CONFLICT reason；复用 F002；恢复沿用各域 reason；未定义 404/405 | CONFIRMED+DESIGN |
| DR-224 | 前端落点：新增 AuditPage 与 SystemPage（账号管理 + 已删对象管理 Tab）；权限门控；列表四态；无 Audit 修改/删除 UI | PROPOSED→CONTRACT + CONFIRMED |
| DR-225 | 恢复路由表：各域 `POST /api/v1/{object}/{id}/restore?version=`（RESTORE）；F015 不复制语义 | CONFIRMED+DESIGN |
| DR-226 | 计划字段：`layers.backend=true`、`frontend=true`、`api_required=true`；`layers.database` PROPOSED true（仅索引，Database 可降级 NOT_REQUIRED） | PROPOSED→CONTRACT |
| DR-227 | 索引建议：`ix_audit_logs_operator_username`（btree audit_logs(operator_username)）；既有 ix 覆盖 object_type/object_id/created_at/operator_user_id；不改 audit_logs 结构 | PROPOSED→DATABASE |

## 3. 裁定 O-1–O-8

| OPEN | 裁定 | 依据 |
| --- | --- | --- |
| O-1 System 页面内容 | 账号管理 + 已删对象管理入口；完整 Audit 独立页；不新增系统设置项 | §28/DR-224 |
| O-2 已删对象管理落点 | System 页 Tab/区域 | DR-216/DR-224 |
| O-3 统一恢复 API | 不新增统一写端点；只读 `GET /api/v1/deleted` + 前端按 type 调各域 restore | DR-216/DR-225 |
| O-4 Audit 参数/响应 | operator 精确匹配、object_type/object_id 组合、action、闭区间时间、分页、created_at/order | DR-214/215/227 |
| O-5 初始凭据/改密 | ADMIN 设初始密码；改密/重置/首登强制改密一期不实现 | DR-218/219 |
| O-6 账号事件登记 | object_type="user"，CREATE/UPDATE，白名单无密码；无需迁移 | DR-221/222 |
| O-7 已删列表字段 | object_type/object_id/version/label/cluster/deleted_at；删除操作者不返回（OPEN） | DR-217/§4.2 |
| O-8 计划字段 | api_required=true；backend/frontend=true；database PROPOSED true（仅索引） | DR-226/227 |

## 4. Domain / Data Impact 与形态

### 4.1 Audit 映射（只读消费既有表）
| AuditRow 字段 | 来源 |
| --- | --- |
| id/created_at | audit_logs.id/created_at |
| action | action |
| object_type/object_id | object_type/object_id |
| operator_user_id | operator_user_id（可空，FK RESTRICT） |
| operator_username | operator_username（快照） |
| before_data/after_data | JSONB object\|null |

### 4.2 已删标签与 cluster 映射
| object_type | 表 | label | cluster |
| --- | --- | --- | --- |
| cluster | clusters | code | null |
| resource | resources | hostname | clusters(cluster_id) |
| interface | interfaces | name | resource.cluster_id |
| network | networks | name | clusters(cluster_id) |
| ip_pool | ip_pools | name | network.cluster_id |
| ip_address | ip_addresses | address | clusters(cluster_id) |
| service | services | name | resource.cluster_id |
| service_endpoint | service_endpoints | "{protocol}:{port}" | ip_address.cluster_id（未绑定 null） |

### 4.3 数据完整性对应表
| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 验证 |
| --- | --- | --- | --- | --- |
| §22 / f003 DB-D28 | audit_logs | trg_audit_logs_append_only | 无修改/删除/清空端点或 UI | 真 PG UPDATE/DELETE 被拒 |
| §22 / f003 DB-D27 | operator_* | FK RESTRICT + username 快照 | 停用不动审计 | 停用后旧 Audit 不变 |
| §21 / 各域契约 | restore | 既有唯一/排他/FK 约束 | 复用各域 restore | 逐类恢复失败 |
| §21/§23 / f002 DB-D16 | user | 无 deleted_at；FK RESTRICT；uq_users_username | 停用代替删除；停用删会话 | 停用/启用/重复 |
| §22/§23 | 账号事件 | 无对象 FK 多态 | object_type="user" + 白名单 + 同事务 | CREATE/UPDATE 无密码 |
| §23 | 权限 | 无 | require_permission；401 先于 403 | 三角色矩阵 |

## 5. Frontend / Backend Work 与 Layers

**Backend**：`app/api/v1/{audit,deleted,users}.py` + router 挂载；`app/schemas/{audit,deleted,users}.py`；`app/services/audit_query.py`；`app/services/user.py`；`app/services/audit.py` 登记 `"user":("username","role","status")`；`app/core/errors.py` 复用；迁移（若采纳 DR-227）：仅新增 btree 索引。
**Frontend**：`pages/AuditPage.tsx`、`pages/SystemPage.tsx`；`components/{AuditQueryPanel,AccountManagementPanel,DeletedObjectsPanel}.tsx`；`api/{audit,users,deleted}.ts`；导航按 permissions；无 Audit 修改/删除 UI。

```yaml
layers:
  database: true    # PROPOSED：仅 ix_audit_logs_operator_username；Database 可改 NOT_REQUIRED
  backend: true
  frontend: true
api_required: true  # /audit · /deleted · /users（restore 复用各域）
```

## 6. 验证策略（真实 PostgreSQL）
- Audit 权限/顺序（A1/A29/T25）；过滤/分页/排序（A3/A4/I-13）；只读/不可变（A5/A8/A10/I-1/T36）。
- 已删列表（A12/A13/O-7）；恢复复用一致性与不级联/不覆盖（A15–A19/T24/T41）；失败无 Audit 残留。
- 用户管理（A20–A26/I-9/I-10/T26）；账号审计脱敏/身份保留（A11/A24/I-2/I-4）。
- 索引（若采纳 DR-227）：EXPLAIN 命中；真库 up/down/up。
- 前端权限门控/四态；恢复 409 reason 明确呈现；无 Audit 修改/删除入口。

## 7. Blocking / OPEN
- Blocking：无。
- PROPOSED→CONTRACT：O-1–O-8 默认（DR-214/215/217/219/221/224/226）；密码长度策略；operator 精确匹配。
- PROPOSED→DATABASE：ix_audit_logs_operator_username；object_type="user" 登记无 Schema 变更复核。
- OPEN（product，非阻塞）：O-5 改密/重置；O-7 删除操作者/`q`。
- OPEN（新，非阻塞，风险）F015-OPEN-1：是否阻止停用/降级最后一个 ACTIVE ADMIN（无已确认规则；PROPOSED 默认不加保护）。
- NOTE：Audit/已删 total 为过滤后计数；无跨对象全局合计。

## 8. 结论与下一步
无 Blocking Questions。DR-213–DR-227 覆盖三端点、恢复路由复用、账号审计登记、前后端落点与验证。**Status：`READY FOR DESIGN`。**

下一步：TEST_DESIGN 出 A1–A31/I-1–I-15 判据；Database 复核 DR-227 索引与 DR-222 登记（NOT_REQUIRED 或小迁移）→ CONTRACT 定稿 `docs/api/F015.md` → `READY FOR IMPLEMENTATION`。
